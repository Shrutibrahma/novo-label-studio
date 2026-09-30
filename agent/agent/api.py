"""HTTP client for the agent endpoints (spec section 6): /agent/jobs/next, /agent/jobs/{id}/status, /agent/heartbeat."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Job:
    id: str
    printer_id: str
    kind: str
    payload: bytes


class ApiClient:
    def __init__(self, base_url: str, token: str, ca_bundle: str | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        verify: Any = ca_bundle if ca_bundle else True
        self._http = httpx.Client(base_url=f"{base_url}/v1", headers={"Authorization": f"Bearer {token}"},
                                  timeout=httpx.Timeout(15.0, connect=5.0), verify=verify, transport=transport)

    def next_job(self) -> Job | None:
        r = self._http.get("/agent/jobs/next")
        if r.status_code == 204:
            return None
        r.raise_for_status()
        body = r.json()
        return Job(id=body["id"], printer_id=body["printer_id"], kind=body["kind"], payload=body["zpl"].encode("ascii"))

    def report(self, job_id: str, status: str, error: str | None = None) -> None:
        payload: dict[str, Any] = {"status": status}
        if error:
            payload["error"] = error[:500]
        r = self._http.post(f"/agent/jobs/{job_id}/status", json=payload)
        r.raise_for_status()

    def heartbeat(self, printer_status: str, host_info: dict[str, Any]) -> None:
        r = self._http.post("/agent/heartbeat", json={"printer_status": printer_status, "host_info": host_info})
        r.raise_for_status()

    def close(self) -> None:
        self._http.close()
