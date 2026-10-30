# Build progress

Novo Smart Labels v1, built milestone by milestone from `SPEC.md` + `schema.sql` (spec section 17).

| Milestone | State |
| --- | --- |
| M0 Hardware spike | deferred until the ZQ630 Plus arrives — `spike/m0/` |
| M1 Foundation | done |
| M2 Parts | done |
| M3 Import | done |
| M4 Render + Configure | done |
| M5 Print (agent with simulated printer) | done |
| M6 History + hardening (reprint, void, backups, performance, README) | done |

## v1.1

Built from the v1.1 addendum (house style, remembered types, industrial presets, quick labels, operations).
Decisions it left open: `OPEN_QUESTIONS.md` § v1.1 (#100–).

| Milestone | State |
| --- | --- |
| H Hardware validation | waiting for the ZQ630 Plus — must pass before v1.1 is done |
| U1 House label style | done |
| U2 Remember the type | done |
| U3 Industrial presets + box options | done |
| U4 Quick labels | done |
| U5 Operations | done (service-on-reboot acceptance needs the laptop: HARDWARE.md) |

See `README.md` for setup, running, tests and switching the agent to USB, and the hardware checks still to run.
Every decision the spec left open is in `OPEN_QUESTIONS.md` (#1–99). One approved schema change: migration 0002
(faster `search_parts()`), see #75.

Last full run of `scripts/test.ps1` (v1.1, 2026-10-30): operations checks passed (backup copy, allowed IPs);
API 149 passed / 9 skipped (5 need hardware, 4 opt-in performance); agent 11 passed; web typecheck + build passed;
Playwright 9/9 flows passed (13.1–13.13). v1.1 is not done until milestone H passes on the printer (HARDWARE.md).

## Environment notes (this laptop)
- New shells may not see uv: `$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + $env:Path`.
- Port 8080 is taken → the HTTP redirect port is 8088. HTTPS: 8443 (dev), 9443 (e2e).
- Testcontainers' Ryuk fails on Docker Desktop for Windows → disabled in `api/tests/conftest.py`.
