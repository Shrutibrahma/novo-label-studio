"""Agent configuration from environment variables (spec section 4, plus the simulated-printer settings)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def default_log_dir() -> Path:
    base = os.environ.get("PROGRAMDATA") or os.environ.get("ALLUSERSPROFILE")
    return Path(base) / "LabelStudio" if base else Path.cwd() / "agent-output"


@dataclass(frozen=True)
class AgentConfig:
    api_base_url: str
    token: str
    printer_queue: str
    poll_seconds: float
    mode: str  # "simulated" | "usb"
    output_dir: Path
    ca_bundle: str | None
    hs_readback: bool
    log_dir: Path
    sim_control_port: int
    heartbeat_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> AgentConfig:
        mode = os.environ.get("AGENT_PRINTER_MODE", "simulated").strip().lower()
        if mode not in ("simulated", "usb"):
            raise SystemExit(f"AGENT_PRINTER_MODE must be 'simulated' or 'usb', not {mode!r}")
        token = os.environ.get("AGENT_TOKEN", "").strip()
        if not token:
            raise SystemExit("AGENT_TOKEN is not set. Copy the token from setup (or Settings → Printers → New agent token).")
        return cls(
            api_base_url=os.environ.get("API_BASE_URL", "https://localhost:8443/api").rstrip("/"),
            token=token,
            printer_queue=os.environ.get("AGENT_PRINTER_QUEUE", "ZQ630 Plus"),
            poll_seconds=float(os.environ.get("AGENT_POLL_SECONDS", "1")),
            mode=mode,
            output_dir=Path(os.environ.get("AGENT_OUTPUT_DIR", "agent-output")),
            ca_bundle=os.environ.get("AGENT_CA_BUNDLE") or None,
            # [SPIKE] ~HS status readback over USB: off unless explicitly enabled (spec 8.2 step 5).
            hs_readback=_flag("AGENT_HS_READBACK"),
            log_dir=Path(os.environ.get("AGENT_LOG_DIR") or default_log_dir()),
            sim_control_port=int(os.environ.get("AGENT_SIM_CONTROL_PORT", "9181")),
        )
