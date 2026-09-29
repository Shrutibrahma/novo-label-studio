"""Agent tokens: 32 random bytes, shown once, stored as an argon2id hash (section 15).

argon2 is deliberately slow, and the agent polls every second, so a verified token is remembered by its
sha256 together with the hash it matched. Rotating the token changes print_agent.token_hash, which
invalidates the cached entry on the very next request."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_secret, verify_secret
from app.db import get_db
from app.errors import ApiError
from app.models import PrintAgent

_verified: dict[bytes, tuple[uuid.UUID, str]] = {}


def issue_token() -> tuple[str, str]:
    token = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    return token, hash_secret(token)


async def authenticate_agent(db: AsyncSession, token: str) -> PrintAgent:
    digest = hashlib.sha256(token.encode("utf-8", "replace")).digest()
    cached = _verified.get(digest)
    if cached is not None:
        agent = await db.get(PrintAgent, cached[0])
        if agent is not None and agent.active and agent.token_hash == cached[1]:
            return agent
        _verified.pop(digest, None)
    agents = (await db.execute(select(PrintAgent).where(PrintAgent.active.is_(True)))).scalars().all()
    for agent in agents:
        if verify_secret(agent.token_hash, token):
            _verified[digest] = (agent.id, agent.token_hash)
            return agent
    raise ApiError("FORBIDDEN")


async def current_agent(request: Request, db: Annotated[AsyncSession, Depends(get_db)],
                        authorization: Annotated[str | None, Header()] = None) -> PrintAgent:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError("FORBIDDEN")
    agent = await authenticate_agent(db, authorization[7:].strip())
    request.state.user_id = None
    return agent


CurrentAgent = Annotated[PrintAgent, Depends(current_agent)]
