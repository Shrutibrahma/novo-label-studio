"""FastAPI application; every router is mounted under /api/v1 (section 6)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from sqlalchemy import func, select, text

from app import scheduler
from app.auth.deps import DB
from app.auth.router import router as auth_router
from app.config import APP_VERSION, get_settings
from app.db import dispose_engine, init_engine
from app.errors import install_handlers
from app.logging_setup import RequestLogMiddleware, configure_logging
from app.models import PrintAgent
from app.printing.jobs import router as jobs_router
from app.printing.printers import router as printers_router
from app.render.fonts import record_font_hashes
from app.settings.router import router as settings_router
from app.settings.users import router as users_router
from app.setup_router import router as setup_router
from app.sizes import router as sizes_router

API_PREFIX = "/api/v1"


class Health(BaseModel):
    db: str
    agent_last_seen: datetime | None
    version: str


health_router = APIRouter(tags=["health"])


@health_router.get("/health", response_model=Health)
async def health(db: DB) -> Health:
    await db.execute(text("SELECT 1"))
    last_seen = (await db.execute(select(func.max(PrintAgent.last_seen_at)))).scalar()
    return Health(db="ok", agent_last_seen=last_seen, version=APP_VERSION)


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        record_font_hashes()
        init_engine(database_url)
        task = scheduler.start() if settings.run_scheduler else None
        try:
            yield
        finally:
            if task is not None:
                await scheduler.stop(task)
            await dispose_engine()

    app = FastAPI(title="Novo Label Studio API", version=APP_VERSION, lifespan=lifespan,
                  docs_url=f"{API_PREFIX}/docs", openapi_url=f"{API_PREFIX}/openapi.json", redoc_url=None)
    app.add_middleware(RequestLogMiddleware)
    install_handlers(app)
    for r in (health_router, setup_router, auth_router, users_router, settings_router, sizes_router,
              printers_router, jobs_router):
        app.include_router(r, prefix=API_PREFIX)
    return app


app = create_app()
