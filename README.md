# Novo Label Studio

Import your parts once, configure what the label shows, then find any part and print the right label in
seconds — on a Zebra ZQ630 Plus. Built from [`SPEC.md`](SPEC.md) and [`schema.sql`](schema.sql).
Decisions the spec left open are in [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md).

| Part | What it is | Where |
| --- | --- | --- |
| Web UI | React + TypeScript + Vite, Tailwind, TanStack Query | `web/` |
| API | FastAPI, SQLAlchemy 2 (async), Alembic (0001 = `schema.sql` verbatim), renderer, ZPL encoder | `api/` |
| Database | PostgreSQL 16 | Docker volume `pgdata` |
| Print agent | Windows program: pulls jobs from the API, writes RAW ZPL to the printer | `agent/` |
| Deployment | Docker Compose: `db`, `api`, `web` (nginx + HTTPS), `backup` | `deploy/` |

The printer hasn't arrived yet, so the agent runs a **simulated printer** by default: every job's exact ZPL
is written to `agent-output/{job_id}.zpl` with a PNG of each label next to it.

## Setup from zero (Windows 11)

1. Install **Docker Desktop** and start it (wait for "Engine running").
2. Install **uv** (Python tool manager):  `winget install --id astral-sh.uv -e` — then open a new PowerShell.
   uv installs Python 3.12 for the agent and tests by itself.
3. Install **Node.js LTS** from https://nodejs.org/ (only needed to run the tests).
4. Allow local scripts once (PowerShell, as yourself):
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```
5. From the repository folder:
   ```powershell
   .\scripts\up.ps1
   ```
   This builds and starts everything, waits until healthy and prints the URL — https://localhost:8443.
   The certificate is self-signed (created in `deploy/certs/` on first start); accept it in the browser once.
6. Open the URL → first-run setup: create the admin, company and serial settings. Step 3 shows the **agent
   token once** — copy it.
7. Start the agent (another PowerShell window), pasting the token the first time:
   ```powershell
   .\scripts\agent.ps1 -Token <paste token>
   ```
   Later runs just need `.\scripts\agent.ps1` (the token is kept in `agent/.env`). Setup step 3 then shows
   "Agent connected. Printer: Ready" and "Print test label" works.
8. Optional demo data (about 50 parts, including NP-10421 with the label name "10-32 x 1/2 16"):
   ```powershell
   .\scripts\demo.ps1
   ```

## Everyday commands

| Command | Does |
| --- | --- |
| `.\scripts\up.ps1` | Build + start db, api, web, backup; wait until healthy; print the URL |
| `.\scripts\down.ps1` | Stop everything (data is kept) |
| `.\scripts\agent.ps1` | Start the print agent — simulated printer (default) |
| `.\scripts\agent.ps1 -Mode usb` | Start the agent against the real printer (see below) |
| `.\scripts\agent.ps1 -SimStatus out_of_media` | Force the simulated printer's status: `ready`, `offline`, `out_of_media`, `head_open`, `paused`, `error` |
| `.\scripts\demo.ps1` | Load the demo parts |
| `.\scripts\test.ps1` | Run every test suite (`-SkipE2E` for a quick run) |
| `.\scripts\backup-now.ps1` | Take a backup now (database dump + part images → `backups\`) |
| `.\scripts\restore.ps1` | Restore the newest backup (or `-Stamp <yyyymmdd-HHMMSS>`) |
| `.\scripts\reset-db.ps1` | Wipe the database and images and start fresh (asks for confirmation) |

To check a job's ZPL by eye without a printer: `cd agent; uv run zpl2png ..\agent-output\<job>.zpl`
writes `<job>-1.png`, `<job>-2.png`, … next to it (the simulated printer already does this for every job).

Settings live in `deploy/.env` (created by `up.ps1`): `DB_PASSWORD`, `HTTPS_PORT` (8443), `HTTP_PORT`
(8088, redirects to HTTPS), `SESSION_TTL_HOURS`, `PUBLIC_BASE_URL`, `BACKUP_AT` (02:00), `BACKUP_TZ`.
To reach it from other machines by name, add `EXTRA_SAN=DNS:labels.local` (or `IP:…`) before the first start,
or delete `deploy/certs/` to regenerate the certificate.

## Tests

`.\scripts\test.ps1` runs, in order:

1. **API** — pytest against a throwaway PostgreSQL 16 (Testcontainers): schema triggers, auth/setup/roles,
   parts/search (A8), imports (A6, A7), renderer golden images (27 cases, byte-identical on Windows and in the
   Linux container), fit tests, ZPL round-trip, configs/preview, printing, the 20-way concurrent serial
   allocation, A3, history/reprint (A4), role guards (A10).
2. **Agent** — pytest: ZPL decoder, simulated printer, job loop, status mapping, `~HS` parsing.
3. **Web** — TypeScript check + production build.
4. **End-to-end** — Playwright flows 13.1–13.10 against an isolated stack on https://localhost:9443 with the
   real agent in simulated mode (it never touches your dev data).

Acceptance checks that need the printer are in the suite as skipped tests with the reason "needs hardware".
Performance targets (section 15) are a separate, slower run:

```powershell
cd api; $env:RUN_PERF = "1"; uv run pytest tests/test_performance.py -s
```

Last run on this development laptop (Windows 11, Docker Desktop), 50,000 parts:

| Target (section 15) | Measured | Target |
| --- | --- | --- |
| `search_parts` p95, server side | 26 ms | < 150 ms |
| Preview render p95, 4 × 6 in with QR | 120 ms | < 300 ms |
| Click Print → job queued, p95 | 178 ms | < 500 ms |
| 50,000-row XLSX parsed, validated and diffed | 36 s | < 60 s |

(`search_parts` meets its target through migration 0002 — see OPEN_QUESTIONS.md #75. For information, a whole
`GET /parts?q=` request including label freshness is ~180 ms p95.)

Renderer goldens are committed in `api/tests/goldens/`. After a deliberate renderer change, look at the PNGs
and regenerate:  `cd api; $env:UPDATE_GOLDENS = "1"; uv run pytest tests/test_render.py`.

## When the ZQ630 Plus arrives: switch the agent to USB

1. Install the Zebra **ZDesigner** driver, connect the printer by USB, and note its Windows printer name
   (Settings → Bluetooth & devices → Printers). The default name the agent expects is `ZQ630 Plus`.
2. Load 4 × 2 in die-cut direct-thermal synthetic labels and calibrate (feed button, or once with
   `cd spike\m0; uv run --with pillow --with segno --with pywin32 python m0.py calibrate --queue "ZQ630 Plus"`).
3. Stop the simulated agent (Ctrl+C) and start it in USB mode:
   ```powershell
   .\scripts\agent.ps1 -Mode usb -Queue "ZQ630 Plus"
   ```
4. In the app: Settings → Printers → set **Loaded labels**, then **Print test label**; adjust X/Y offsets if the
   border or rulers are shifted.
5. Optional `~HS` readback (**[SPIKE]**, off by default): `.\scripts\agent.ps1 -Mode usb -HsReadback`. If the
   printer answers, jobs go from "Sent to printer" to "Printed"; if not, they stay "Sent to printer" (D17).
6. To run the agent as a Windows service: `agent\packaging\build.ps1` (PyInstaller), then in an elevated
   PowerShell `agent\packaging\install-service.ps1 -Token <token> -ApiBaseUrl https://<server>:8443/api -Nssm <path to nssm.exe>`
   (download NSSM from https://nssm.cc yourself). Logs: `%ProgramData%\LabelStudio\agent.log` (10 MB × 5).

## Hardware checks still to run

| Check | How | Pass when |
| --- | --- | --- |
| **M0 spike** | `spike\m0\README.md` | one Large label prints; results recorded |
| **A1** Preview = print | Print each preset; scan at 600 dpi; overlay on the preview PNG (History drawer shows the exact bitmap) | no element off by more than 2 dots |
| **A2** QR scans | Configure QR "Part" then "Serial"; print every preset; scan with a phone | `PN:…` and `SN:…\|PN:…` read correctly |
| **A5** Box set | Print Labels → a part with a Box sequence → Total boxes 3 → "Print all 3 boxes" | BOX 1/3, 2/3, 3/3 with 3 distinct serials |
| **A9** Printer errors | Unplug the USB cable while the agent runs in usb mode | sidebar "Offline" within 40 s; Print disabled with "The printer is offline. Check the USB cable and that the printer is on." |
| **A11** Offsets | Settings → Printers → X offset +10 → Print test label | the label visibly shifts about 1.25 mm |
| **~HS readback** | `-HsReadback` as above, print a label | jobs reach "Printed"; record the result in SPEC.md's decision log (D17) |
| Media | 30-day rack test of the chosen synthetic DT media | labels stay legible |

## Backups and restore (A12)

The `backup` service runs every night at `BACKUP_AT` (default 02:00 UTC — set `BACKUP_TZ`, e.g.
`America/Chicago`): `pg_dump` custom format + a tar of the part images into `backups\`, kept 30 days.
To restore on a fresh machine: copy the repository and the `backups\` folder, run `.\scripts\up.ps1` once, then
`.\scripts\restore.ps1` (newest backup) and sign in with the users from the backup.

## Repository layout

```
api/        FastAPI app (app/), Alembic migrations, bundled OFL fonts, tests
web/        React UI (src/), Playwright flows (e2e/)
agent/      print agent (agent/), tests, packaging (PyInstaller + NSSM)
deploy/     docker-compose.yml, nginx.conf, backup.sh, e2e override
scripts/    PowerShell entry points (up, down, agent, demo, test, backup-now, restore, reset-db)
spike/m0/   hardware spike script for the first printer session
schema.sql  database schema (migration 0001 applies it verbatim)
SPEC.md     build specification
```
