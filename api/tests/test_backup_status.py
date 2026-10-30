"""Settings → General "Last backup" line (v1.1 D25): read from the backup container's status file."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.settings import router as settings_router

V = "/api/v1"


def use(monkeypatch: pytest.MonkeyPatch, status_file: Path, copy_enabled: str) -> None:
    fake = SimpleNamespace(backup_status_file=status_file, backup_copy_enabled=copy_enabled)
    monkeypatch.setattr(settings_router, "get_settings", lambda: fake)


def test_status_file_states(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    status = tmp_path / "last-backup.json"
    use(monkeypatch, status, "")
    none_yet = settings_router.backup_status()
    assert none_yet.at is None and not none_yet.copy_enabled and none_yet.copied is None

    use(monkeypatch, status, "yes")
    status.write_text(json.dumps({"at": "2026-10-30T02:00:05Z", "copied": True, "copy_error": ""}))
    ok = settings_router.backup_status()
    assert ok.at is not None and ok.at.year == 2026 and ok.copy_enabled and ok.copied is True and ok.copy_error is None

    status.write_text(json.dumps({"at": "2026-10-31T02:00:05Z", "copied": False, "copy_error": "Read-only file system"}))
    failed = settings_router.backup_status()
    assert failed.copied is False and failed.copy_error == "Read-only file system"

    status.write_text("not json")
    assert settings_router.backup_status().at is None


async def test_settings_include_backup(admin: httpx.AsyncClient) -> None:
    body = (await admin.get(f"{V}/settings")).json()
    assert set(body["backup"]) == {"at", "copy_enabled", "copied", "copy_error"}
