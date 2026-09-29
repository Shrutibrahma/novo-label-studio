"""Test harness: one Postgres 16 container per session (Testcontainers), schema via migration 0001,
tables truncated between tests."""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

os.environ.setdefault("RUN_SCHEDULER", "false")
os.environ.setdefault("ASSET_DIR", tempfile.mkdtemp(prefix="ls-assets-"))
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Ryuk can't get a port mapping on Docker Desktop for Windows; the context manager stops the container.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer

from app.auth.passwords import hash_secret
from app.db import dispose_engine, init_engine, sessionmaker
from app.main import create_app

API_DIR = Path(__file__).resolve().parents[1]
PASSWORD = "correct-horse-battery"
PASSWORD_HASH = hash_secret(PASSWORD)

SETUP_BODY: dict[str, Any] = {
    "display_name": "Ada Admin", "username": "admin", "password": PASSWORD, "confirm_password": PASSWORD,
    "company_name": "Novo", "serial_prefix": "NOVO", "starting_number": 1, "digits": 8,
}


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    external = os.environ.get("TEST_DATABASE_URL")
    if external:
        yield external
        return
    with PostgresContainer("postgres:16", username="label", password="label", dbname="label", driver=None) as pg:
        host = pg.get_container_host_ip()
        port = pg.get_exposed_port(5432)
        yield f"postgresql+asyncpg://label:label@{host}:{port}/label"


@pytest.fixture(scope="session")
def migrated(pg_url: str) -> str:
    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.attributes["database_url"] = pg_url
    cfg.attributes["skip_logging"] = True
    command.upgrade(cfg, "head")
    return pg_url


@pytest.fixture(scope="session")
async def engine(migrated: str) -> AsyncIterator[None]:
    init_engine(migrated)
    yield
    await dispose_engine()


TABLES = ("audit_log, printed_label, print_job, print_request, issued_serial, label_group, printer, print_agent, "
          "label_config, serial_sequence, label_size, part_alias, import_row, part, import_batch, import_mapping, "
          "custom_field_def, asset, app_setting, user_session, app_user")


@pytest.fixture(autouse=True)
async def clean_db(engine: None) -> AsyncIterator[None]:
    async with sessionmaker()() as db:
        await db.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        await db.commit()
    from app.printing import agent_auth
    agent_auth._verified.clear()
    yield


@pytest.fixture(scope="session")
def app(engine: None) -> Any:
    return create_app()


@pytest.fixture
async def client(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
        yield c


@pytest.fixture
async def new_client(app: Any) -> AsyncIterator[Any]:
    """Factory for extra independent clients (separate cookie jars)."""
    clients: list[httpx.AsyncClient] = []

    def make() -> httpx.AsyncClient:
        c = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")
        clients.append(c)
        return c

    yield make
    for c in clients:
        await c.aclose()


async def insert_user(username: str, role: str, active: bool = True) -> uuid.UUID:
    async with sessionmaker()() as db:
        uid = (await db.execute(text(
            "INSERT INTO app_user (username, display_name, role, password_hash, active) "
            "VALUES (:u, :d, :r, :h, :a) RETURNING id"),
            {"u": username, "d": username.title(), "r": role, "h": PASSWORD_HASH, "a": active})).scalar_one()
        await db.commit()
        return uid


@pytest.fixture
async def setup_done(client: httpx.AsyncClient) -> dict[str, Any]:
    """Runs first-run setup; `client` is left signed in as the admin."""
    r = await client.post("/api/v1/setup", json=SETUP_BODY)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
async def operator(setup_done: dict[str, Any], new_client: Any) -> httpx.AsyncClient:
    await insert_user("olive", "operator")
    c = new_client()
    r = await c.post("/api/v1/auth/login", json={"username": "olive", "password": PASSWORD})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def admin(client: httpx.AsyncClient, setup_done: dict[str, Any]) -> httpx.AsyncClient:
    return client
