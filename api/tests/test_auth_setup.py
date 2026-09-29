"""M1 gate: login / setup / role tests."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from sqlalchemy import func, select, text, update

from app.db import sessionmaker
from app.models import AppUser, AuditLog, LabelConfig, LabelSize, Printer, SerialSequence, UserSession
from tests.conftest import PASSWORD, SETUP_BODY, insert_user

V = "/api/v1"


async def test_setup_status_and_first_run(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{V}/setup/status")).json() == {"needs_setup": True}
    r = await client.post(f"{V}/setup", json=SETUP_BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["role"] == "admin" and len(body["agent_token"]) >= 40
    assert "ls_session" in r.cookies
    assert (await client.get(f"{V}/setup/status")).json() == {"needs_setup": False}
    # Signed in straight away.
    assert (await client.get(f"{V}/auth/me")).json()["username"] == "admin"

    async with sessionmaker()() as db:
        sizes = {s.name: (float(s.width_in), float(s.height_in)) for s in (await db.execute(select(LabelSize))).scalars()}
        assert sizes == {"Small": (2, 1), "Medium": (3, 2), "Large": (4, 2), "Tall": (4, 6)}
        seq = (await db.execute(select(SerialSequence))).scalar_one()
        assert (seq.name, seq.prefix, seq.separator, seq.digits, seq.next_value) == ("Default", "NOVO", "-", 8, 1)
        printer = (await db.execute(select(Printer))).scalar_one()
        assert (printer.model, printer.dpi, float(printer.print_width_in), printer.darkness, printer.speed_ips,
                printer.is_default) == ("Zebra ZQ630 Plus", 203, 4.1, None, None, True)
        cfg = (await db.execute(select(LabelConfig))).scalar_one()
        assert (cfg.scope, cfg.version, cfg.qr_mode, cfg.serial_mode) == ("default", 1, "none", "none")
        assert [f["key"] for f in cfg.spec["fields"]] == ["part_number", "part_name"]
        assert cfg.spec["style"] == {"font": "inter", "primary_weight": "bold", "alignment": "left",
                                     "emphasis": "medium", "spacing": "standard", "qr_position": "right"}
        actions = sorted((await db.execute(select(AuditLog.action))).scalars())
        assert actions.count("size.create") == 4 and "user.create" in actions and "config.publish" in actions


async def test_setup_only_once(client: httpx.AsyncClient, new_client: Any) -> None:
    other = new_client()
    results = await asyncio.gather(client.post(f"{V}/setup", json=SETUP_BODY),
                                   other.post(f"{V}/setup", json=SETUP_BODY | {"username": "second"}))
    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409]
    loser = next(r for r in results if r.status_code == 409)
    assert loser.json()["error"]["code"] == "SETUP_DONE"
    async with sessionmaker()() as db:
        assert (await db.execute(select(func.count()).select_from(AppUser))).scalar() == 1


async def test_setup_validation(client: httpx.AsyncClient) -> None:
    r = await client.post(f"{V}/setup", json=SETUP_BODY | {"password": "short", "confirm_password": "short"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "PASSWORD_TOO_SHORT"
    r = await client.post(f"{V}/setup", json=SETUP_BODY | {"confirm_password": PASSWORD + "x"})
    assert r.json()["error"]["code"] == "PASSWORDS_DIFFERENT"
    r = await client.post(f"{V}/setup", json=SETUP_BODY | {"serial_prefix": "no-way"})
    assert r.json()["error"]["code"] == "SERIAL_PREFIX_INVALID"
    r = await client.post(f"{V}/setup", json=SETUP_BODY | {"digits": 13})
    assert r.json()["error"]["code"] == "FIELD_OUT_OF_RANGE"
    assert (await client.get(f"{V}/setup/status")).json() == {"needs_setup": True}


async def test_login_cookie_flags_and_logout(setup_done: dict[str, Any], new_client: Any) -> None:
    c = new_client()
    r = await c.post(f"{V}/auth/login", json={"username": "ADMIN", "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "ls_session=" in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert (await c.get(f"{V}/auth/me")).status_code == 200
    assert (await c.post(f"{V}/auth/logout")).status_code == 204
    r = await c.get(f"{V}/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "SESSION_EXPIRED"
    async with sessionmaker()() as db:
        user = (await db.execute(select(AppUser).where(AppUser.username == "admin"))).scalar_one()
        assert user.last_login_at is not None


async def test_login_errors_and_lockout(setup_done: dict[str, Any], new_client: Any) -> None:
    c = new_client()
    r = await c.post(f"{V}/auth/login", json={"username": "nobody", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["error"] == {"code": "AUTH_INVALID",
                                                         "message": "Username or password is incorrect."}
    for _ in range(4):
        r = await c.post(f"{V}/auth/login", json={"username": "admin", "password": "wrong-password!"})
        assert r.json()["error"]["code"] == "AUTH_INVALID"
    r = await c.post(f"{V}/auth/login", json={"username": "admin", "password": "wrong-password!"})
    assert r.status_code == 423
    assert r.json()["error"]["message"] == "Too many attempts. Try again in 15 minutes."
    # Locked even with the right password.
    r = await c.post(f"{V}/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.json()["error"]["code"] == "AUTH_LOCKED"
    async with sessionmaker()() as db:
        await db.execute(update(AppUser).values(locked_until=func.now() - text("interval '1 second'")))
        await db.commit()
    assert (await c.post(f"{V}/auth/login", json={"username": "admin", "password": PASSWORD})).status_code == 200


async def test_failures_outside_window_do_not_lock(setup_done: dict[str, Any], new_client: Any) -> None:
    c = new_client()
    for _ in range(4):
        await c.post(f"{V}/auth/login", json={"username": "admin", "password": "wrong-password!"})
    async with sessionmaker()() as db:
        await db.execute(update(AppUser).values(first_failed_at=func.now() - text("interval '16 minutes'")))
        await db.commit()
    r = await c.post(f"{V}/auth/login", json={"username": "admin", "password": "wrong-password!"})
    assert r.json()["error"]["code"] == "AUTH_INVALID"


async def test_inactive_user_cannot_login(setup_done: dict[str, Any], new_client: Any) -> None:
    await insert_user("gone", "operator", active=False)
    r = await new_client().post(f"{V}/auth/login", json={"username": "gone", "password": PASSWORD})
    assert r.json()["error"]["code"] == "AUTH_INVALID"


async def test_expired_session(admin: httpx.AsyncClient) -> None:
    async with sessionmaker()() as db:
        await db.execute(update(UserSession).values(created_at=func.now() - text("interval '13 hours'"),
                                                    expires_at=func.now() - text("interval '1 hour'")))
        await db.commit()
    r = await admin.get(f"{V}/auth/me")
    assert r.status_code == 401 and r.json()["error"]["message"] == "Your session expired. Sign in again."


async def test_unauthenticated_requests(client: httpx.AsyncClient) -> None:
    for path in ("/auth/me", "/printers", "/settings", "/sizes"):
        r = await client.get(f"{V}{path}")
        assert r.status_code == 401, path


ADMIN_ONLY: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/users", None),
    ("POST", "/users", {"display_name": "X", "username": "xavier", "role": "operator", "password": PASSWORD}),
    ("PATCH", "/settings", {"company_name": "Evil"}),
    ("POST", "/sizes", {"name": "Custom", "width_in": 3, "height_in": 1}),
]


async def test_operator_role_guards(operator: httpx.AsyncClient, admin: httpx.AsyncClient) -> None:
    printer_id = (await admin.get(f"{V}/printers")).json()[0]["id"]
    size_id = (await admin.get(f"{V}/sizes")).json()[0]["id"]
    user_id = (await admin.get(f"{V}/users")).json()[0]["id"]
    checks = ADMIN_ONLY + [
        ("PATCH", f"/printers/{printer_id}", {"offset_x_dots": 5}),
        ("POST", f"/printers/{printer_id}/agent-token", None),
        ("PATCH", f"/sizes/{size_id}", {"name": "Hacked"}),
        ("PATCH", f"/users/{user_id}", {"role": "operator"}),
    ]
    for method, path, body in checks:
        r = await operator.request(method, f"{V}{path}", json=body)
        assert r.status_code == 403, (method, path, r.text)
        assert r.json()["error"] == {"code": "FORBIDDEN", "message": "You don't have permission to do that."}
    # Operators can read what the shell needs.
    for path in ("/printers", "/settings", "/sizes", "/auth/me"):
        assert (await operator.get(f"{V}{path}")).status_code == 200, path


async def test_last_admin_protection(admin: httpx.AsyncClient) -> None:
    me = (await admin.get(f"{V}/auth/me")).json()
    r = await admin.patch(f"{V}/users/{me['id']}", json={"role": "operator"})
    assert r.status_code == 409 and r.json()["error"]["message"] == "There must be at least one active admin."
    r = await admin.patch(f"{V}/users/{me['id']}", json={"active": False})
    assert r.json()["error"]["code"] == "LAST_ADMIN"
    r = await admin.post(f"{V}/users", json={"display_name": "Bo", "username": "bo", "role": "admin",
                                             "password": PASSWORD})
    assert r.json()["error"]["code"] == "USERNAME_INVALID"  # 3–64 chars per schema.sql
    r = await admin.post(f"{V}/users", json={"display_name": "Bob", "username": "bob", "role": "admin",
                                             "password": PASSWORD})
    assert r.status_code == 201
    r = await admin.patch(f"{V}/users/{me['id']}", json={"role": "operator"})
    assert r.status_code == 200 and r.json()["role"] == "operator"


async def test_user_management(admin: httpx.AsyncClient, new_client: Any) -> None:
    r = await admin.post(f"{V}/users", json={"display_name": "Olive", "username": "olive", "role": "operator",
                                             "password": PASSWORD})
    assert r.status_code == 201
    uid = r.json()["id"]
    r = await admin.post(f"{V}/users", json={"display_name": "O2", "username": "OLIVE", "role": "operator",
                                             "password": PASSWORD})
    assert r.json()["error"]["code"] == "USERNAME_TAKEN"
    c = new_client()
    assert (await c.post(f"{V}/auth/login", json={"username": "olive", "password": PASSWORD})).status_code == 200
    r = await admin.patch(f"{V}/users/{uid}", json={"active": False})
    assert r.json()["active"] is False
    assert (await c.get(f"{V}/auth/me")).status_code == 401  # deactivation ends sessions
    async with sessionmaker()() as db:
        actions = (await db.execute(select(AuditLog.action).where(AuditLog.entity_id == uid))).scalars().all()
        assert actions == ["user.create", "user.update"]


async def test_settings_serial_lock_and_raise_only(admin: httpx.AsyncClient) -> None:
    r = await admin.patch(f"{V}/settings", json={"serial_prefix": "ACME", "serial_digits": 6,
                                                 "company_name": "Acme"})
    assert r.status_code == 200
    assert r.json()["serial"]["example"] == "ACME-000001" and r.json()["company_name"] == "Acme"
    r = await admin.patch(f"{V}/settings", json={"serial_next_value": 500})
    assert r.json()["serial"]["next_value"] == 500
    r = await admin.patch(f"{V}/settings", json={"serial_next_value": 10})
    assert r.json()["error"]["code"] == "FIELD_OUT_OF_RANGE"
    async with sessionmaker()() as db:
        seq = (await db.execute(select(SerialSequence))).scalar_one()
        uid = (await db.execute(select(AppUser.id))).scalar_one()
        await db.execute(text("INSERT INTO part (part_number, part_name, created_by, updated_by) "
                              "VALUES ('P1', 'P', :u, :u)"), {"u": uid})
        pid = (await db.execute(text("SELECT id FROM part"))).scalar_one()
        await db.execute(text("SELECT allocate_serials(:s, :p, 1, :u)"), {"s": seq.id, "p": pid, "u": uid})
        await db.commit()
    r = await admin.patch(f"{V}/settings", json={"serial_prefix": "ZZZ"})
    assert r.status_code == 409 and r.json()["error"]["message"] == "Locked after the first serial is issued."
    assert (await admin.get(f"{V}/settings")).json()["serial"]["locked"] is True


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{V}/health")
    assert r.status_code == 200 and r.json()["db"] == "ok"
