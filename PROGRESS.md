# Build progress

Novo Label Studio v1, built milestone by milestone from `SPEC.md` + `schema.sql` (spec section 17).

| Milestone | State |
| --- | --- |
| M0 Hardware spike | deferred until the ZQ630 Plus arrives — `spike/m0/` |
| M1 Foundation | done |
| M2 Parts | done |
| M3 Import | done |
| M4 Render + Configure | done |
| M5 Print (agent with simulated printer) | done |
| M6 History + hardening (reprint, void, backups, performance, README) | done |

See `README.md` for setup, running, tests and switching the agent to USB, and the hardware checks still to run.
Every decision the spec left open is in `OPEN_QUESTIONS.md` (#1–86). One approved schema change: migration 0002
(faster `search_parts()`), see #75.

Last full run of `scripts/test.ps1`: API 99 passed / 9 skipped (5 need hardware, 4 opt-in performance),
agent 9 passed, web typecheck + build passed, Playwright 6/6 flows passed.

## Environment notes (this laptop)
- New shells may not see uv: `$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + $env:Path`.
- Port 8080 is taken → the HTTP redirect port is 8088. HTTPS: 8443 (dev), 9443 (e2e).
- Testcontainers' Ryuk fails on Docker Desktop for Windows → disabled in `api/tests/conftest.py`.
