# Build progress — handoff notes

Build of Novo Label Studio v1 from `SPEC.md` + `schema.sql`, milestone by milestone (spec section 17).
M0 (hardware spike) is deferred until the ZQ630 Plus arrives; its script is in `spike/m0/`.

## Status

| Milestone | State | Commit |
| --- | --- | --- |
| M1 Foundation (migration 0001, auth, sessions, roles, setup wizard, app shell, Docker, scripts) | done | `8b4ce40` |
| M2 Parts (CRUD, images, custom fields, label names, search, Settings tabs, demo data) | done | `025aa36` |
| M3 Import (CSV/XLSX/XLS, mapping, validation, diff, commit, hero UI) | done | `15fab18` |
| M4 Render + Configure (engine, goldens, preview, config versions, Configure UI, drawer Label tab) | done | see `git log` |
| M5 Print (serials, jobs, agent + SimulatedPrinter, Print dialog, batch, box sets) | **in progress** | — |
| M6 History, reprint, void, backups, logging, perf, README | not started | — |

Every decision the spec left open is logged in `OPEN_QUESTIONS.md` (#1–40 so far).

## M4 — what exists (uncommitted, on disk)

Done and tested (`api/tests/test_render.py`, `test_configs.py` pass):
- `api/app/configs/spec.py` — spec JSON model + rules (role limits, keys, manual fields, QR needs serial).
- `api/app/render/engine.py` — the pure renderer: canvas, stack / qr_side / qr_top, 7.5 fit + wrap, QR.
- `api/app/render/canvas.py` — **own 1-bit PNG writer using Python zlib** (Pillow's bundled zlib differs
  Windows vs Linux; this makes PNG bytes identical on both — verified 27/27 goldens in the container).
- `api/app/render/snapshot.py`, `render/service.py`, `render/router.py` (POST /render/preview).
- `api/app/configs/router.py` — GET /configs, /configs/default, /configs/{id}, /parts/{id}/config,
  POST /configs, DELETE /parts/{id}/config, PUT /parts/{id}/selection.
- Goldens: `api/tests/goldens/` (regenerate deliberately: `UPDATE_GOLDENS=1 uv run pytest tests/test_render.py`;
  cross-check in Linux: `docker run --rm -v <repo>\api\tests:/srv/api/tests:ro labelstudio-api python -m tests.golden_check`).
- `web/src/components/LabelPreview.tsx` — 7.7 preview component + `usePreview` hook.

Still to do for M4:
1. Configure list page `/configure` and editor `/configure/default`, `/configure/part/:id` (12.11): sections
   Size, What's on the label (drag, role select with "Limit reached" tooltip, caption, UPPERCASE, remove,
   "+ Add field" grouped), Print-time fields dialog, QR code & serial, Style; "Preview with part" combobox;
   fit status; "Publish version {n+1}"; leave guard "Discard your changes?" [Keep editing] [Discard] (useBlocker).
   Add the routes (admin-only) in `web/src/app/router.tsx`.
2. Copy `RobotoCondensed-*.ttf` and `AtkinsonHyperlegible-*.ttf` from `api/fonts` to `web/public/fonts` and add
   @font-face so the Font select can render each option in its font.
3. Part drawer "Label" tab (`web/src/features/parts/PartLabelTab.tsx`): static preview, "Customize for this part",
   ghost "Use default label".
4. Playwright spec `web/e2e/04-configure.spec.ts` for flow 13.9.
5. Add M4 notes to OPEN_QUESTIONS.md (Tall preset = exactly 1.5×W → qr_side; qr_top only for custom sizes;
   manual fields carry a `label`; caption not uppercased; new-field default role; serial off → QR none;
   CONFIG_INVALID / CONFIG_FIELD_UNKNOWN codes; GET /configs and GET /configs/{id} added).
6. Run `scripts/test.ps1`, commit "M4: …".

## M5 / M6 plan (from the user's brief)
- Agent (`agent/`, uv project, Python 3.12): Printer interface → `ZebraUsbPrinter` (win32print RAW, 8.2) and
  `SimulatedPrinter` (writes `./agent-output/{job_id}.zpl` + a PNG per label); `AGENT_PRINTER_MODE=simulated|usb`
  (default simulated); a dev control (local endpoint/CLI) to force offline / out_of_media / head_open / paused;
  `~HS` readback behind a flag, off by default, marked `[SPIKE]` (port code from `spike/m0/m0.py`);
  dev tool that decodes a `.zpl` back to PNG; `scripts/agent.ps1 -Mode simulated|usb`.
- API: POST /print (print_request + jobs ≤200 labels, allocate_serials in the render transaction),
  /agent/jobs/next (FOR UPDATE SKIP LOCKED), /agent/jobs/{id}/status, /agent/heartbeat, 60 s lease in the
  scheduler, box groups, copies vs quantity; 20-way concurrent serial test; A3.
- Web: Preview dialog (12.5), Print dialog incl. batch + box sets (12.6), Eye/Print buttons on Print Labels.
- M6: History + drawer + reprint + void (12.12), backups (pg_dump + assets tar, 30 days) + restore script,
  perf checks (section 15), README, final OPEN_QUESTIONS list, list of hardware checks (A1, A2, A5, A9, A11, ~HS).

## How to run / test
- One-time: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (you run this; not done by Claude).
- `scripts/up.ps1` → https://localhost:8443 (self-signed). `scripts/demo.ps1` after first-run setup.
- `scripts/test.ps1` → API pytest (Testcontainers Postgres 16), web typecheck/build, Playwright against an
  isolated stack on https://localhost:9443. `-SkipE2E` for a quick run.
- The dev DB currently has a setup done by Claude (admin `ada` / `correct-horse-battery`) and demo data;
  run `scripts/reset-db.ps1` to start clean.

## Environment gotchas learned
- New shells don't see uv on PATH: prefix with
  `$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')`.
- PowerShell 5.1 `Set-Content -Encoding utf8` writes a BOM (breaks pyproject.toml) — write files with the editor
  or `[IO.File]::WriteAllText(..., UTF8Encoding($false))`.
- Port 8080 is taken on this machine → HTTP redirect port is 8088.
- Testcontainers' Ryuk fails on Docker Desktop for Windows → `TESTCONTAINERS_RYUK_DISABLED=true` (set in conftest).
- In PS 5.1, native stderr + `$ErrorActionPreference='Stop'` throws; scripts/test.ps1 wraps native calls.
