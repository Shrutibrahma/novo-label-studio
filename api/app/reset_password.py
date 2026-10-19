"""Set a user's password from the server (scripts/reset-password.ps1): the way back in when the only admin
forgets theirs. Run inside the api container:

    python -m app.reset_password <username>      (the new password is read from stdin, never from argv)

Same rules as the app: at least 12 characters, argon2id hash. It also unlocks the account, reactivates it and
signs out every existing session of that user. Audited as user.password_reset (actor: the user, via the
server console)."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit
from app.auth.passwords import MIN_PASSWORD_LENGTH, hash_secret
from app.db import dispose_engine, init_engine, sessionmaker
from app.models import AppUser, UserSession


class ResetError(Exception):
    def __init__(self, message: str, code: int) -> None:
        super().__init__(message)
        self.code = code


async def reset_in_db(db: AsyncSession, username: str, password: str) -> AppUser:
    """Sets the password, unlocks and reactivates the user, ends their sessions; caller commits."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ResetError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters. Nothing was changed.", 2)
    user = (await db.execute(select(AppUser).where(func.lower(AppUser.username) == username.strip().lower())
                             .with_for_update())).scalar_one_or_none()
    if user is None:
        names = (await db.execute(select(AppUser.username).order_by(AppUser.username))).scalars().all()
        raise ResetError(f"No user named '{username}'. Users: {', '.join(names) or '(none)'}", 3)
    was = {"active": user.active, "locked": user.locked_until is not None}
    user.password_hash = hash_secret(password)
    user.active = True
    user.failed_login_count = 0
    user.first_failed_at = None
    user.locked_until = None
    ended = (await db.execute(delete(UserSession).where(UserSession.user_id == user.id))).rowcount
    audit(db, user.id, "user.password_reset", "app_user", user.id, was,
          {"active": True, "locked": False, "sessions_ended": ended, "via": "server console"})
    return user


async def reset(username: str, password: str) -> int:
    init_engine()
    try:
        async with sessionmaker()() as db:
            try:
                user = await reset_in_db(db, username, password)
            except ResetError as err:
                print(str(err), file=sys.stderr)
                return err.code
            await db.commit()
            print(f"Password for '{user.username}' ({user.role}) was reset. Sign in with the new password.")
            return 0
    finally:
        await dispose_engine()


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not argv[1].strip():
        print("Usage: python -m app.reset_password <username>   (new password on stdin)", file=sys.stderr)
        return 1
    password = sys.stdin.readline().rstrip("\r\n")
    return asyncio.run(reset(argv[1], password))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
