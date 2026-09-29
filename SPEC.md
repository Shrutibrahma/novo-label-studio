# Novo Label Studio — Build Specification v1

Sep 29, 2026 · @Shruti Brahma

## 0. How to use this spec

This document is the single source of truth for building Novo Label Studio v1. The file `schema.sql` (delivered with this spec) is canonical for the database; where the two disagree, `schema.sql` wins for storage and this doc wins for behaviour.

Rules for any engineer or LLM implementing this:

1. **Do not invent.** Every screen, field, colour, icon, message and rule is specified here. If something is not specified, stop and raise it as an open question. Do not fill gaps with assumptions.
2. **Precedence:** Decision log (section 2) > section-specific rules > examples. Examples illustrate; rules govern.
3. **Non-goals are hard limits.** Anything in section 1's non-goals list must not be built, stubbed or scaffolded.
4. **Exact strings.** UI copy in quotes is literal. Do not rephrase, add punctuation or change capitalisation.
5. **Units.** Physical sizes are inches. Render geometry is printer dots. Never mix them inside one function.
6. **Versions.** No library versions are pinned in this doc. Use the latest stable release at project start and lock them with the lockfile (`uv.lock`, `package-lock.json`). Verify any API you use against the installed version's docs.
7. **Hardware-dependent items** are marked **\[SPIKE\]**. They must be tested on a real Zebra ZQ630 Plus before the related feature is called done.

## 1. Product summary and scope

Novo Label Studio turns a company's parts master into consistent, serialized part labels printed on a Zebra ZQ630 Plus. Promise: **import your parts once, configure what the label shows, then find any part and print the right label in seconds.**

It is parts-master-first: every label comes from a part record. Nobody draws a label at print time: users only tick which fields to show and pick a size and text size; the layout engine places everything.

**Users**

| Role | Can do |
| --- | --- |
| Operator | Search parts, preview, enter print-time values, print, reprint from History, look up serials |
| Admin | Everything an Operator can, plus: import parts, add/edit/archive parts, manage label names, configure labels, custom fields, sizes, serial sequences, printers, users, settings |

**In scope (v1)**

- Parts master from CSV, XLSX, XLS, plus manual entry
- Saved column mappings, validation, import diff and review
- User-defined label names (aliases) that resolve to one part and are searchable
- Custom part fields
- Part images (manual upload)
- Label configuration: global default + optional per-part override, versioned
- Automatic layout; limited styling (font, weight, size emphasis, alignment, spacing)
- Print-time manual fields: text, number, choice, box sequence (BOX 1/3)
- Automatic serial numbers (NOVO-00000001), atomic, never reused
- QR codes (per-part or per-label)
- Pixel-exact preview (same bitmap as the print)
- Batch printing, copies, serialized quantity
- Print history with exact snapshot, exact reprint, serial lookup
- "Label out of date" detection after imports or renames
- Print agent on the laptop, USB to ZQ630 Plus
- Two roles: Admin, Operator

**Non-goals (do not build)**

PDF import · rack/location management · inventory counts · MES/ERP/WMS integration · touchscreen kiosk mode · mobile app · barcode-scanner workflows beyond typing into the search box · RFID · approval workflows · free-form drag-and-drop label designer · analytics dashboards · AI features · multi-language UI · dark mode (except the fixed dark sidebar and import hero) · printers other than ZPL.

## 2. Decision log

These decisions are final for v1. Changing one requires editing this table first.

| # | Decision | Rationale |
| --- | --- | --- |
| D1 | Printer: Zebra ZQ630 Plus, USB to a Windows laptop | Native ZPL, 4.1" print width, rugged; no emulation risk |
| D2 | Printer language: ZPL only | One encoder; the ZQ630 Plus speaks it natively |
| D3 | Render once to a 1-bit bitmap at printer DPI; preview shows that bitmap; ZPL `^GFA` sends that bitmap | Preview and print are the same pixels |
| D4 | No printer-resident fonts; only bundled OFL fonts | Exact preview; no font licensing risk |
| D5 | Backend: FastAPI + PostgreSQL 16 (server), web UI in the browser | Solid multi-user backend; roles; one source of truth |
| D6 | Print agent: Windows service on the laptop, pulls jobs from the API, writes RAW to the Zebra driver queue | Browser can't reach USB; server never talks to the printer |
| D7 | Import formats: CSV, XLSX, XLS only | PDF extraction is unreliable for part numbers |
| D8 | Unique part key: `part_number`, normalized as upper(trim) | Deterministic diff and duplicate detection |
| D9 | Imports never delete parts; parts missing from a file are proposed as `inactive` | No silent data loss |
| D10 | Label names (aliases) live outside imported data; one alias maps to exactly one part; one alias per part is its printable `label_name` | Survives re-import; lookups are unambiguous |
| D11 | Config scope: one global default + optional per-part override; every change creates a new immutable version | Exact reprints; no label "types" to choose |
| D12 | Serial format default `NOVO-` + 8 digits, one global sequence, never reset, never reused | Simplest safe scheme |
| D13 | QR modes: `none`, `part` (encodes part number), `serial` (encodes serial + part). Plain text, no URLs | No resolver exists; scans must be readable offline |
| D14 | Box groups are separate from serials; each label in a group still gets its own serial | A serial identifies one physical label |
| D15 | Copies = identical labels (same serial). Quantity = N distinct serialized labels | Clear separation |
| D16 | Reprint reuses the original snapshot, serial and bitmap | Exact reproduction |
| D17 | Job status is "Sent" unless printer readback confirms; never claim "Printed" without confirmation | Honest status |
| D18 | Direct-thermal synthetic (polypropylene) media | ZQ630 Plus is direct thermal only; paper fades |
| D19 | UI: light theme content, fixed dark navy sidebar, dark hero on Import only | Matches the brief |
| D20 | Icons: lucide-react only | One consistent set |
| D21 | Working product name: "Novo Label Studio" (configurable company name in Settings) | Branding placeholder |

## 3. Hardware

Target printer is the Zebra ZQ630 Plus: 203 dpi direct thermal, 4.1" max print width (832 dots), media 2.0"–4.4" wide, USB, Wi-Fi, Bluetooth. v1 uses USB only.

**Printer profile seeded at install**

| Field | Value |
| --- | --- |
| model | Zebra ZQ630 Plus |
| command\_language | zpl |
| print\_method | direct\_thermal |
| dpi | 203 |
| print\_width\_in | 4.100 (832 dots) |
| media\_min\_width\_in | 2.000 |
| media\_max\_width\_in | 4.400 |
| darkness | NULL (do not send `~SD` unless set by admin; admin range 0–30) |
| speed\_ips | NULL (do not send `^PR` unless set by admin) |
| offsets | 0, 0 dots |

**Label size presets.** Width is across the media; height is along the feed. Dots = inches × 203, rounded down.

| Name | Width × height (in) | Dots (w × h) |
| --- | --- | --- |
| Small | 2.00 × 1.00 | 406 × 203 |
| Medium | 3.00 × 2.00 | 609 × 406 |
| Large | 4.00 × 2.00 | 812 × 406 |
| Tall | 4.00 × 6.00 | 812 × 1218 |

Custom sizes: width 2.00–4.40 in, height 0.50–11.00 in, step 0.01 in. The printable width is min(label width, 4.10 in). A size wider than 4.40 in or narrower than 2.00 in is rejected with "This size doesn't fit the ZQ630 Plus (media 2.0–4.4 in wide)." 1.4 × 6 in and 4.5 × 7 in are therefore not offered.

**Safe margin:** 13 dots (0.064 in) on all four sides. Nothing is drawn inside it.

**Media:** die-cut direct-thermal synthetic (polypropylene) labels with a gap. Media tracking = gap (`^MNY`). Black-mark media is not supported in v1.

**\[SPIKE\] items for this printer**

- USB status readback (`~HS`) from the Windows agent. If it fails, status stays "Sent".
- Media calibration flow on first install (feed button / `~JC`).
- Durability of chosen synthetic DT media on a real rack for 30 days.

## 4. System architecture

Four runtime parts: a browser UI, one API server, PostgreSQL, and a print agent on the laptop wired to the printer. The API renders every label; the agent only moves bytes to USB.

&#91;embedded content: system architecture · 5 components\]

The browser and agent both talk only to the API; the agent pulls finished ZPL and writes it RAW to the printer over USB.

| Component | Runs on | Responsibility |
| --- | --- | --- |
| Web UI | Browser (Chrome/Edge, latest) | All screens; never talks to the printer |
| API | Server (Docker) | Auth, parts, imports, configs, serial allocation, rendering, job queue |
| PostgreSQL 16 | Server (Docker) | All state; schema.sql |
| Asset store | Server volume `/data/assets` | Part images, keyed by sha256 |
| Print agent | Windows laptop (Windows service) | Polls API for queued jobs, writes RAW ZPL to the Zebra driver queue, reports status |

**Tech stack**

| Layer | Choice |
| --- | --- |
| API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic |
| Auth | argon2-cffi for password hashing; server-side sessions in Postgres, HttpOnly Secure SameSite=Lax cookie |
| Import parsing | openpyxl (XLSX), xlrd (XLS), Python `csv` with charset detection via `charset-normalizer` |
| Rendering | Pillow (1-bit images, TrueType), segno (QR) |
| Frontend | React + TypeScript + Vite, React Router, TanStack Query, Tailwind CSS, lucide-react |
| Agent | Python 3.12, `pywin32` (`win32print` RAW jobs), `httpx`; packaged with PyInstaller; installed as a service via NSSM |
| Tests | pytest, httpx test client, Playwright (UI), Testcontainers-Postgres |
| Packaging | Docker Compose: `db`, `api`, `web` (nginx serving the built UI and proxying `/api`) |

**Deployment:** one on-prem Linux or Windows machine runs Docker Compose. The laptop can be that machine. The agent reaches the API over HTTPS at `API_BASE_URL`. If the API is unreachable, printing is blocked and the UI says "Can't reach the server. Printing is paused."

**Configuration (environment variables)**

| Variable | Used by | Example |
| --- | --- | --- |
| DATABASE\_URL | api | postgresql+asyncpg://label:\*\*\*@db:5432/label |
| ASSET\_DIR | api | /data/assets |
| SESSION\_TTL\_HOURS | api | 12 |
| PUBLIC\_BASE\_URL | api | https://labels.local |
| API\_BASE\_URL | agent | https://labels.local/api |
| AGENT\_TOKEN | agent | issued in Settings → Printers |
| AGENT\_PRINTER\_QUEUE | agent | Windows printer name, e.g. "ZQ630 Plus" |
| AGENT\_POLL\_SECONDS | agent | 1 |

**Repository layout**

```
label-studio/
  api/
    app/
      main.py            # FastAPI app, routers mounted under /api
      auth/              # sessions, password hashing, role guards
      parts/             # parts, aliases, custom fields, images
      imports/           # parsing, mapping, validation, diff, commit
      configs/           # label configs + versions
      render/            # layout engine, fonts, QR, bitmap, ZPL encoder
      printing/          # jobs, serials, agent endpoints
      history/
      settings/
      db.py, models.py, schemas.py
    fonts/               # bundled OFL .ttf files (section 7)
    migrations/          # Alembic; 0001 = schema.sql
    tests/
  web/
    src/
      app/ (routes, layout shell)
      features/ (parts, import, configure, print, history, settings, auth)
      components/ (design-system primitives, section 11)
      lib/ (api client, query keys, formatters)
  agent/
    agent/ (main.py, zebra.py, api.py)
  deploy/
    docker-compose.yml, nginx.conf
  schema.sql
  SPEC.md
```

## 5. Data model

`schema.sql` defines 21 tables (including print\_request, user\_session and app\_setting), the part\_label\_freshness view, the search\_parts, allocate\_serials and normalize\_alias functions, and the triggers that enforce the invariants below. Migration `0001` applies it verbatim.

| Table | Holds | Key rules |
| --- | --- | --- |
| app\_user | Users, role, password hash | username unique case-insensitive; role admin/operator |
| asset | Part images (metadata; bytes on disk) | sha256 unique; png/jpeg/webp; ≤ 10 MB |
| custom\_field\_def | Admin-defined part fields | key `^[a-z][a-z0-9_]{0,62}$`; type text/number/date/choice |
| part | Parts master | part\_number\_norm unique; status active/inactive/archived |
| part\_alias | Label names + search aliases | alias\_norm unique; ≤ 1 label name per part; can't equal another part number |
| import\_mapping | Saved column mappings | one per header signature |
| import\_batch / import\_row | Staged imports and their diff | staged → committed/discarded |
| label\_size | Size presets | width across media, height along feed |
| label\_config | Label configuration versions | immutable; one current default; ≤ 1 current per part |
| serial\_sequence | Prefix, digits, next value | counter only moves forward |
| issued\_serial | Every serial ever allocated | never reused; allocated/printed/unconfirmed/voided |
| label\_group | Box sets (BOX n/total) | total 1–999 |
| print\_agent | Laptop agents | token hash; last\_seen\_at |
| printer | Printer profiles | one default; ZPL only |
| print\_job | One print or reprint request | idempotency\_key unique; state machine in section 8 |
| printed\_label | Every label produced | immutable; stores snapshot + exact bitmap |
| audit\_log | Meaningful state changes | append-only |

**Invariants the application must also respect**

1. All writes to `part`, `part_alias`, `label_config`, `serial_sequence`, `printer`, `app_user` and `custom_field_def` write one `audit_log` row in the same transaction. Action names: `part.create`, `part.update`, `part.archive`, `alias.create`, `alias.update`, `alias.delete`, `import.commit`, `config.publish`, `size.create`, `size.update`, `serial.void`, `printer.update`, `user.create`, `user.update`, `field.create`, `field.update`.
2. `printed_label.snapshot.part` keys are exactly the part field keys printed on that label (core column names, custom field keys, and `label_name`), with values in the same JSON type as the source.
3. Allocating serials, inserting `printed_label` rows and setting the job to `rendered` happen in one transaction.
4. Parts are never hard-deleted in v1. "Delete" in the UI means archive.
5. Timestamps are stored UTC and displayed in the laptop's local time zone, format `Sep 29, 2026, 9:34 AM`.

**Seed data (created by /setup)**

- Label sizes: the four presets in section 3.
- Serial sequence "Default" from the setup inputs.
- Printer profile from section 3, linked to the new agent.
- Default label config v1 is only a starting point, not a standard: size Large (4 × 2 in); fields part\_number and part\_name; no print-time fields; serial off; QR off; style Inter, bold, medium, left, standard. Users pick any fields they want (label name, part name, description, revision, custom fields, serial, QR…) and that choice is saved.
- Rule: `whatever field the user puts first is the main line; if it is empty for a part, the next picked field moves up`, so the main line is never empty.

## 6. API specification

REST over HTTPS, JSON bodies, all paths under `/api/v1`. The UI and the agent are the only clients.

**Conventions**

- Auth: session cookie `ls_session` for users; `Authorization: Bearer <AGENT_TOKEN>` for the agent. Agent tokens only reach `/agent/*`.
- Errors: HTTP status + body `{"error": {"code": "PART_NUMBER_TAKEN", "message": "<UI string from section 14>", "fields": {"part_number": "..."}}}`.
- Lists: `?q=&limit=50&cursor=` → `{"items": [...], "next_cursor": "..." | null}`. Max limit 200.
- Writes that change a versioned or shared row accept `If-Match: <updated_at ISO>`; mismatch → 409 `STALE_WRITE`.
- Print requests require header `Idempotency-Key: <uuid>`; the key belongs to one print\_request row, and a repeat returns that request with all its jobs.
- Times: ISO 8601 UTC.

**Endpoints**

| Method | Path | Role | Purpose |
| --- | --- | --- | --- |
| POST | /auth/login | public | `{username, password}` → sets cookie; 5 failures in 15 min locks the user for 15 min (app\_user.failed\_login\_count and locked\_until; last\_login\_at set on success) |
| POST | /auth/logout | any | Ends session |
| GET | /auth/me | any | Current user |
| GET | /setup/status | public | `{needs_setup: bool}` (true when no users exist) |
| POST | /setup | public, once | Creates first admin, company name, default printer profile |
| GET | /parts | any | List/search; `q` uses `search_parts`; filters `status`, `label_state` |
| POST | /parts | admin | Create part |
| GET | /parts/{id} | any | Part + aliases + current config + freshness |
| PATCH | /parts/{id} | admin | Update fields |
| POST | /parts/{id}/archive | admin | Archive |
| POST | /parts/{id}/restore | admin | Back to active |
| PUT | /parts/{id}/image | admin | Multipart upload → asset |
| DELETE | /parts/{id}/image | admin | Remove image link |
| GET | /parts/{id}/aliases | any | Aliases |
| POST | /parts/{id}/aliases | admin | `{alias, is_label_name}` |
| PATCH | /aliases/{id} | admin | Rename / set as label name |
| DELETE | /aliases/{id} | admin | Remove alias |
| GET/POST | /custom-fields | admin (GET any) | List / create |
| PATCH | /custom-fields/{key} | admin | Update label, required, searchable, printable, choices (type is immutable) |
| POST | /imports | admin | Multipart file → parse, stage batch, return headers + suggested mapping |
| PUT | /imports/{id}/mapping | admin | Confirm mapping (+ `save_as` name) → validate + diff |
| GET | /imports/{id}/rows | admin | Paged rows, filter by `action` |
| PATCH | /imports/{id}/rows/{row\_id} | admin | Edit row data or `accepted` |
| POST | /imports/{id}/commit | admin | Apply accepted rows in one transaction |
| POST | /imports/{id}/discard | admin | Discard |
| GET/POST | /sizes | admin (GET any) | Label sizes |
| PATCH | /sizes/{id} | admin | Rename, deactivate (dimensions immutable once used) |
| GET | /configs/default | any | Current default config |
| GET | /parts/{id}/config | any | Effective config (override or default) |
| POST | /configs | admin | Publish new version `{scope, part_id?, label_size_id, spec, qr_mode, serial_mode}` |
| DELETE | /parts/{id}/config | admin | Retire per-part override (falls back to default) |
| POST | /render/preview | any | `{part_id, config (draft or id), manual_values?}` → PNG + `{fits, warnings}`; never allocates serials |
| POST | /print | any | `{printer_id?, items: [{part_id, copies, quantity, manual_values, group?: {total, start_index}}]}` → job |
| GET | /jobs/{id} | any | Job + labels + status |
| POST | /jobs/{id}/cancel | any | Only while `queued` |
| POST | /labels/{id}/reprint | any | `{reason}` → new job, same snapshot/serial/bitmap |
| GET | /history | any | Printed labels; filters `q`, `part_id`, `serial`, `from`, `to`, `user_id` |
| GET | /serials/{value} | any | Serial registry record + its labels |
| POST | /serials/{value}/void | admin | `{reason}` |
| GET/PATCH | /printers, /printers/{id} | admin (GET any) | Profiles, offsets, darkness, loaded size, default |
| POST | /printers/{id}/test | admin | Queue the test label |
| POST | /printers/{id}/agent-token | admin | Issue new agent token (shown once) |
| GET/PATCH | /settings | admin (GET any) | Company name, serial sequence, QR, fonts allowed |
| GET/POST/PATCH | /users, /users/{id} | admin | Manage users; can't demote/deactivate the last active admin |
| GET | /agent/jobs/next | agent | Claims oldest `queued` job for this agent's printer (`FOR UPDATE SKIP LOCKED`) → ZPL payload |
| POST | /agent/jobs/{id}/status | agent | `{status: sent\|confirmed\|failed, error?}` |
| POST | /agent/heartbeat | agent | `{printer_status, host_info}` every 10 s |

**Field selection endpoint:** `PUT /parts/{id}/selection` (any role) with `{fields, label_size_id, emphasis}` publishes a new per-part config version that copies everything else from the part's effective config. Only these three keys may differ; all other config changes need admin `POST /configs`.

## 7. Label rendering engine

One pure function produces every label: `render(snapshot, config, size, printer) -> RenderResult {png_1bit, sha256, fits, warnings, width_dots, height_dots}`. Same inputs always give identical bytes. Preview and print both call it.

**7.1 Canvas**

- Width dots W = floor(min(width\_in, printer.print\_width\_in) × dpi). Height dots H = floor(height\_in × dpi).
- Image mode `1` (1-bit). Background white (1), ink black (0). `ImageDraw.fontmode = "1"` so text is never anti-aliased.
- Content box = canvas inset by 13 dots on every side.
- No rotation in v1: every label prints exactly as it reads, width across the media, so preview and print are the same pixels. Rotation is a v2 item.

**7.2 Bundled fonts (all SIL OFL; ship the .ttf files in `api/fonts/`)**

| Style key | Family | Files |
| --- | --- | --- |
| inter | Inter | Regular 400, SemiBold 600, Bold 700, ExtraBold 800 |
| roboto\_condensed | Roboto Condensed | Regular 400, Bold 700 |
| atkinson | Atkinson Hyperlegible | Regular 400, Bold 700 |

Font file sha256 values are recorded at startup; `snapshot.generated.renderer_version` = app version + sha256 of the concatenated font hashes. Missing weight in a family → use the nearest heavier weight.

**7.3 Config spec JSON (stored in `label_config.spec`)**

```json
{
  "fields": [
    {"key": "label_name", "role": "primary", "uppercase": true, "caption": null},
    {"key": "part_number", "role": "secondary", "uppercase": true, "caption": "PN"},
    {"key": "serial", "role": "secondary", "uppercase": true, "caption": null},
    {"key": "revision", "role": "detail", "uppercase": true, "caption": "REV"},
    {"key": "manual.box", "role": "detail", "uppercase": true, "caption": null}
  ],
  "manual_fields": [
    {"key": "box", "type": "box_sequence", "noun": "BOX", "required": true}
  ],
  "style": {
    "font": "inter",
    "primary_weight": "bold",
    "alignment": "left",
    "emphasis": "medium",
    "spacing": "standard",
    "qr_position": "right"
  }
}
```

- Field keys: core columns (`part_number`, `part_name`, `description`, `revision`), `label_name`, custom field keys, generated (`serial`, `print_date`), and `manual.<key>`.
- Roles: 0–1 primary (if none is set, the first field in the list is the main line); 0–2 secondary; 0–6 detail. No field is mandatory. Order in the array is print order within each role.
- `caption` (≤ 8 chars) prints before the value, separated by one space, regular weight.
- Manual field types: `text` (max\_length 1–60), `number` (min, max, integer bool), `choice` (choices: 1–20 strings), `box_sequence` (noun: `^[A-Z]{1,16}$`). `box_sequence` renders as `BOX 1/3`.
- `primary_weight`: regular 400 · bold 700 · extra\_bold 800 (Inter only; other families fall back to Bold). Secondary uses SemiBold 600 (Inter) or Bold; detail uses Regular.
- A field whose value is empty is skipped (its line disappears), except a required manual field, which blocks printing.

**7.4 Layout families (chosen automatically)**

| Condition | Family | Placement |
| --- | --- | --- |
| qr\_mode = none | stack | Text block fills the content box |
| QR on and H ≤ 1.5 × W | qr\_side | QR square on `qr_position` side; side = min(content\_h, 0.40 × content\_w); 16-dot gap; text block in the rest |
| QR on and H > 1.5 × W | qr\_top | QR square centred at top; side = min(0.60 × content\_w, 0.45 × content\_h); 16-dot gap; text block below |

Text block: lines stacked primary → secondary → detail, vertically centred in its area, aligned left or centre per style.

**7.5 Type sizes and fit algorithm**

Start sizes in points (dots = pt × dpi / 72):

| Role | small | medium | large | Minimum |
| --- | --- | --- | --- | --- |
| primary | 14 | 20 | 28 | 10 |
| secondary | 11 | 14 | 18 | 8 |
| detail | 9 | 10 | 12 | 7 |

Line gap = spacing factor × that line's size: compact 0.20, standard 0.35, spacious 0.55.

1. Width pass: for each line, if measured width > text column width, reduce that line's size in 0.5 pt steps to its role minimum.
2. Still too wide: primary and secondary may wrap onto 2 lines at word boundaries (space, `-`, `/`). Detail lines never wrap.
3. Height pass: if total block height > available height, reduce all sizes together in 0.5 pt steps, never below minimums.
4. Still not fitting → `fits = false` with warnings. **Text is never truncated or ellipsised.** Printing is blocked until it fits.

Warning codes: `TEXT_TOO_LONG` (field key), `CONTENT_TOO_TALL`, `QR_TOO_SMALL`, `REQUIRED_VALUE_MISSING` (field key), QR\_PAYLOAD\_TOO\_LONG.

**7.6 QR rendering**

- segno, error correction M, no boost, border drawn by us: quiet zone 4 modules.
- Module size m = floor(qr\_side / (modules + 8)) dots. m < 3 → `QR_TOO_SMALL`, fits = false. The QR is drawn at exactly (modules + 8) × m and centred in its square.
- Payload (section 9): part mode `PN:<part_number>`; serial mode `SN:<serial>|PN:<part_number>`.

**7.7 Preview specifics**

- Preview never allocates a serial. It renders `serial` as the sequence prefix + separator + `one 8 per configured digit (e.g. NOVO-88888888 for 8 digits`), the widest digit, so the real serial always fits. The UI overlays the badge "Serial assigned at print".
- `print_date` in preview = today in the laptop's time zone, format `2026-09-29`.
- `box_sequence` in preview without values renders `BOX 1/1`.
- The UI shows the PNG with CSS `image-rendering: pixelated`, scaled to the largest integer multiple that fits the preview pane (minimum 1×), on a `#E5E7EB` surround, with a 1 px `#9CA3AF` outline at the label edge. A toggle "Actual size" scales it to physical inches using 96 CSS px per inch.

## 8. ZPL encoding, print agent, job states

The API turns stored bitmaps into ZPL; the agent writes those bytes to the Windows print queue unchanged.

**8.1 ZPL per label**

```
~SD{darkness}            (only if printer.darkness is set)
^XA
^MNY
^PW{W}
^LL{H}
^PR{speed}               (only if printer.speed_ips is set)
^FO0,0^GFA,{n},{n},{bpr},{hex}^FS
^PQ{copies}
^XZ
```

- `bpr` = ceil(W / 8) bytes per row; `n` = bpr × H; `hex` = uppercase hex of the packed rows, no line breaks.
- Bit polarity: ZPL prints 1 bits. Pillow mode `1` stores white as 1, so **invert** every byte before hex encoding. Row padding bits are white.
- Printer offsets are applied by translating the bitmap on a new W × H white canvas (clipping what falls outside), never with `^LH`.
- A job's payload = its labels' ZPL concatenated in `seq_in_job` order. Max 200 labels per job; larger batches are split into consecutive jobs under one print\_request.

**8.2 Agent behaviour**

1. Every `AGENT_POLL_SECONDS` call `GET /agent/jobs/next`. `204` = nothing to do.
2. On a job: `OpenPrinter(AGENT_PRINTER_QUEUE)` → `StartDocPrinter("Label Studio job <id>", RAW)` → `StartPagePrinter` → `WritePrinter(bytes)` → `EndPagePrinter` → `EndDocPrinter` → `ClosePrinter`.
3. Success → `POST status sent`. Any exception → `POST status failed` with the exception text (max 500 chars).
4. Every 10 s `POST /agent/heartbeat` with printer status mapped from `GetPrinter(level 2).Status`: OFFLINE → offline, PAPER\_OUT → out\_of\_media, DOOR\_OPEN → head\_open, PAUSED → paused, ERROR → error, PRINTING → printing, 0 → ready, anything else → unknown.
5. **\[SPIKE\]** Status readback over USB (`~HS`). If it works, the agent posts `confirmed` after the printer reports the labels done. If not, jobs stay `sent`.
6. The agent never retries a job on its own. It logs to `%ProgramData%\LabelStudio\agent.log`, rotating at 10 MB × 5 files.

**8.3 Job state machine**

| From | To | Trigger | Serial effect |
| --- | --- | --- | --- |
| (new) | rendered | `POST /print`: serials allocated, labels rendered, rows inserted in one transaction | allocated |
| rendered | queued | Immediately after commit | — |
| queued | cancelled | User cancels | voided, reason "Cancelled before printing" |
| queued | sending | Agent claims it | — |
| sending | sent | Agent `WritePrinter` succeeded | printed |
| sending | failed | Agent error, or no update 60 s after claim | unconfirmed |
| sent | confirmed | **\[SPIKE\]** printer readback | printed |

Terminal states: cancelled, failed, sent (unless readback exists), confirmed. Nothing retries automatically; the user uses Reprint. `schema.sql` adds status `sending` and column `claimed_at` for this.

**UI status words:** rendered/queued → "Waiting for printer" · sending → "Printing…" · sent → "Sent to printer" · confirmed → "Printed" · failed → "Print failed" · cancelled → "Cancelled".

**Stored payload and test labels:** every job stores its complete ZPL in `print_job.payload_zpl` at render time; the agent sends exactly those bytes. A test label is a job with `kind = test`, no `print_request` and no `printed_label` rows.

## 9. Serials, QR, box groups, copies

Every distinct physical label gets its own serial; copies are exact duplicates of one label; box groups only number the labels.

**9.1 Serials**

- Format: `{prefix}{separator}{zero-padded value}`, default `NOVO-00000001`. Prefix `^[A-Z0-9]{1,12}$`, separator `-`, `_` or none, digits 4–12.
- Allocated only by `allocate_serials()` inside the print transaction (section 5, invariant 3). Never in preview.
- Admins may change prefix, separator and digits in Settings only before the first serial is issued; after that they are read-only with the note "Locked after the first serial is issued." `next_value` can only be raised, never lowered.
- Statuses: allocated → printed (delivered to the printer without error) · unconfirmed (job failed after it reached the agent) · voided (cancelled before printing, or voided by an admin with a reason). Voided serials cannot be reprinted.

**9.2 Copies vs quantity**

| Input (Print dialog) | Meaning | Rows created | Serials |
| --- | --- | --- | --- |
| Quantity (1–200) | Distinct labels | quantity × printed\_label | one each |
| Copies of each (1–50) | Identical duplicates of each label | copies stored on the row, sent as `^PQ` | same serial |

Quantity is shown only when the config has `serial_mode = required`. Without serials, only Copies is shown.

**9.3 Box groups**

- Available when the config has a `box_sequence` manual field. The Print dialog then shows "Total boxes" (1–999) and replaces Quantity.
- Two actions: "Print all {T} boxes" (one job, labels 1..T) and "Print box {n} of {T}" (one label). After a single box prints, the dialog offers "Print box {n+1} of {T}" until n = T.
- Each box label is a separate `printed_label` with `group_id` + `group_index` and its own serial. The group row is created on the first print.

**9.4 QR payloads (plain text, UTF-8)**

| qr\_mode | Payload | Example |
| --- | --- | --- |
| none | — | — |
| part | `PN:{part_number}` | `PN:NP-10421` |
| serial | `SN:{serial}\|PN:{part_number}` | `SN:NOVO-00001843\|PN:NP-10421` |

- Always the part number, never the label name, so a scan identifies the part unambiguously.
- Payload over 120 characters → render warning QR\_PAYLOAD\_TOO\_LONG, fits = false, message "This part number is too long for the QR code."

**9.5 Reprint**

- "Reprint exact label" creates a new job with `kind = reprint`, one `printed_label` per original with `reprint_of` set, the same snapshot and serial, and the stored bitmap bytes.
- If the current default printer's DPI differs from the stored label's DPI, the label is re-rendered from the snapshot and the dialog warns "This printer has a different resolution. The label will be re-rendered from the original data."
- Reason picker (required): Damaged · Missing · Print issue · Other.

## 10. Import pipeline

An import is staged, mapped, validated and diffed before anything touches the parts master; commit applies accepted rows in one transaction.

**10.1 Parsing**

- Limits: 20 MB file, 50,000 data rows. Over → "This file is too large. Limit: 20 MB and 50,000 rows."
- CSV: encoding via charset-normalizer; delimiter sniffed from `,` `;` tab; quote `"`. XLSX: openpyxl `read_only=True, data_only=True` (formula results, not formulas). XLS: xlrd.
- Workbook with more than one non-empty sheet → an extra step "Which sheet?" listing sheet names with row counts.
- Header row = first non-empty row. Fully empty rows are skipped and not counted. Merged cells read as blank except the top-left.
- Cell values: strings trimmed; Excel dates → ISO `YYYY-MM-DD`; numeric cells in the part\_number column become integers without decimals when integral (no scientific notation).

**10.2 Mapping**

- Header normalization: lowercase, trim, non-alphanumerics → `_`, collapse repeats. Signature = sha256 of normalized headers sorted and joined by `\n`.
- A saved mapping with the same signature is applied automatically and shown as "Using saved mapping: {name}".
- Otherwise suggestions from synonyms (normalized):

| Target | Synonyms |
| --- | --- |
| part\_number | part\_number, part\_no, partno, pn, part, item, item\_no, item\_number, user\_number, user\_no, novo\_pn |
| part\_name | part\_name, name, item\_name, title, short\_description |
| description | description, desc, desc1, long\_description, details |
| revision | revision, rev, rev\_level, revision\_level |
| custom field | its key or its label, normalized |

- Every column's target is a dropdown: Ignore (default for unmatched), core fields, custom fields, "+ New custom field…".
- Part Number and Part Name must be mapped: "Map a column to Part Number and Part Name to continue." A target can be used by one column only.
- "Save this mapping as" text field (default: file name without extension).

**10.3 Row validation**

| Field | Rule | Message |
| --- | --- | --- |
| part\_number | required, ≤ 64 chars | "Part number is missing." / "Part number is longer than 64 characters." |
| part\_number | unique within file (normalized) | "Duplicate part number in this file (rows {a}, {b})." — all duplicates invalid |
| part\_name | required, ≤ 200 | "Part name is missing." |
| description | ≤ 1000 | "Description is longer than 1000 characters." |
| revision | ≤ 16 | "Revision is longer than 16 characters." |
| number field | parses after removing `,` thousands separators | "{Field} must be a number." |
| date field | ISO, M/D/YYYY, or Excel serial | "{Field} must be a date." |
| choice field | case-insensitive match to a choice (stored as the canonical choice) | "{Field} must be one of: {choices}." |
| required custom field | non-empty for new parts | "{Field} is required." |

**10.4 Diff**

- Match on part\_number\_norm. Actions: new · update (any mapped field differs) · unchanged · invalid · missing (active part not in the file).
- **An empty cell never clears an existing value.** Clearing is done by editing the part.
- Custom data merges: mapped keys overwrite; unmapped keys are kept.
- Default acceptance: new, update → accepted; missing → not accepted ("Mark as inactive" unticked); a row matching an archived part → update with the flag "Restore archived part", not accepted.
- Aliases and label names are never read from or changed by imports. A new part whose number equals another part's alias is invalid: "This part number is already used as a label name for part {part\_number}."

**10.5 Commit**

- One transaction: upsert accepted rows (source = import, last\_import\_batch\_id), set accepted missing parts inactive, write counts, `import.commit` audit row.
- Invalid rows are never committed. Commit is allowed with invalid rows present; the summary shows "{n} rows skipped because of errors."
- Staged batches not committed within 24 hours are discarded by a scheduled task.

## 11. Design system

Light, dense, calm content on a fixed dark navy sidebar; one blue for actions; colour otherwise only means status. Define every token below as a CSS variable in `web/src/styles/tokens.css` and map it into Tailwind's theme. Components never use raw hex.

**11.1 Colour tokens**

| Token | Hex | Use |
| --- | --- | --- |
| --nav-bg | #0B1F3A | Sidebar background |
| --nav-item-hover | #13294B | Sidebar item hover |
| --nav-item-active | #1C3A66 | Sidebar active item background |
| --nav-text | #C9D4E5 | Sidebar item text + icons |
| --nav-text-active | #FFFFFF | Active item text + icon |
| --nav-divider | #1F3558 | Sidebar dividers |
| --hero-bg-from | #0A1B33 | Import hero gradient start (top) |
| --hero-bg-to | #10284A | Import hero gradient end (bottom) |
| --hero-text | #FFFFFF | Hero heading |
| --hero-text-muted | #9FB3CF | Hero body text |
| --hero-drop-border | #3B5B8C | Drop zone dashed border |
| --hero-drop-bg | #0F2544 | Drop zone fill; hover #15305A |
| --bg | #F6F7F9 | App content background |
| --surface | #FFFFFF | Cards, tables, dialogs |
| --surface-subtle | #F9FAFB | Table header, zebra rows, read-only fields |
| --border | #E3E6EB | Card and table borders, dividers |
| --border-strong | #CBD2DC | Input borders |
| --text | #111827 | Primary text |
| --text-secondary | #4B5563 | Secondary text, table cells |
| --text-muted | #6B7280 | Hints, placeholders, timestamps |
| --primary | #2563EB | Primary buttons, links, selected states |
| --primary-hover | #1D4ED8 | Hover |
| --primary-pressed | #1E40AF | Active/pressed |
| --primary-subtle | #EFF6FF | Selected row, active chip background |
| --focus-ring | #93C5FD | 2 px focus outline, 2 px offset |
| --success | #16A34A | Success text/icons; bg #DCFCE7 |
| --warning | #D97706 | Warning text/icons; bg #FEF3C7 |
| --danger | #DC2626 | Errors, destructive buttons; bg #FEE2E2; hover #B91C1C |
| --info | #0284C7 | Info text/icons; bg #E0F2FE |
| --preview-surround | #E5E7EB | Area around the label preview |
| --preview-edge | #9CA3AF | 1 px outline of the label |
| --label-paper | #FFFFFF | Label background in preview |
| --label-ink | #000000 | Label print colour |

**Status mapping** (badges, printer indicator, job states): Ready / Printed / Current → success · Sent to printer / Waiting for printer / Printing… → info · Out of date / Unconfirmed / Needs review → warning · Failed / Offline / Out of labels / Head open / Error / Voided → danger · Never printed / Inactive / Unknown → neutral (text #4B5563 on #F3F4F6) · Archived → neutral with strikethrough-free italic text.

**11.2 Typography**

- UI font: Inter (self-hosted woff2), fallback `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`.
- Codes (part numbers, serials, QR payloads): JetBrains Mono, fallback `ui-monospace, Consolas, monospace`, weight 500.
- Scale (size / line-height / weight): Display 32/40/700 (import hero only) · H1 24/32/600 (page titles) · H2 20/28/600 · H3 16/24/600 · Body 14/20/400 · Body-strong 14/20/600 · Small 13/18/400 · Caption 12/16/500 · Button 14/20/600.
- Numbers in tables use `font-variant-numeric: tabular-nums`.

**11.3 Spacing, radius, elevation, layout**

- Spacing scale (px): 4, 8, 12, 16, 20, 24, 32, 40, 48, 64. Page padding 32; card padding 24; table cell padding 12 × 16.
- Radius: 6 inputs/buttons/badges(pill 999), 8 cards/tables, 12 dialogs/drawers, 16 import drop zone.
- Elevation: card none (border only) · dropdown `0 4px 12px rgba(17,24,39,0.08)` · dialog `0 20px 40px rgba(17,24,39,0.18)` · toast same as dropdown.
- Shell: sidebar 240 px fixed; top bar 56 px (page title left, user menu right); content max-width 1440 px, left-aligned.
- Minimum supported window 1280 × 720. No mobile layout.
- Motion: 150 ms ease-out for hover/press; 200 ms for dialog/drawer; `prefers-reduced-motion` disables all.

**11.4 Components**

| Component | Spec |
| --- | --- |
| Button primary | bg --primary, text white, h 36, px 16, radius 6; disabled bg #BFDBFE |
| Button secondary | bg white, border --border-strong, text --text; hover bg #F3F4F6 |
| Button ghost | no border/bg; text --text-secondary; hover bg #F3F4F6 |
| Button danger | bg --danger, text white |
| Big print button | primary, h 48, px 24, text 16/600, icon Printer 20 px |
| Input | h 36, border --border-strong, radius 6, px 12; focus border --primary + ring; error border --danger + message 13 px --danger below |
| Select / Combobox | same as input, ChevronDown 16 px right |
| Checkbox / Switch | 16 px box / 36 × 20 switch, checked --primary |
| Badge | h 22, px 8, radius 999, Caption text, colours per status mapping |
| Table | header bg --surface-subtle, Caption uppercase --text-muted; rows h 52 (h 64 when an image column shows); hover bg #F9FAFB; selected bg --primary-subtle |
| Card | surface, border, radius 8, padding 24 |
| Dialog | width 560 (Print: 960), radius 12, header 20/600, footer right-aligned buttons |
| Drawer | right side, width 520, full height |
| Toast | bottom-right, width 360, auto-dismiss 5 s (errors stay until closed) |
| Empty state | centred icon 40 px --text-muted, H3 title, Body text, one primary button |
| Skeleton | #EEF0F3 blocks, 1.2 s shimmer |

**11.5 Icons (lucide-react, stroke 1.75, 20 px in nav and buttons, 16 px inline)**

| Use | Icon |
| --- | --- |
| Nav: Print Labels | Printer |
| Nav: Parts | Package |
| Nav: Configure | SlidersHorizontal |
| Nav: History | History |
| Nav: Settings | Settings |
| Search | Search |
| Import | Upload |
| Add | Plus |
| Edit | Pencil |
| Archive | Archive |
| Restore | ArchiveRestore |
| Preview | Eye |
| Print | Printer |
| Reprint | RotateCcw |
| QR | QrCode |
| Serial | Hash |
| Label name | Tag |
| Box group | Boxes |
| Image placeholder | ImageOff |
| Upload image | ImagePlus |
| Out of date | RefreshCw |
| Success | CircleCheck |
| Warning | TriangleAlert |
| Error | CircleX |
| Info | Info |
| Close | X |
| Menu chevron | ChevronDown |
| Row link | ChevronRight |
| Copy | Copy |
| Download | Download |
| Filter | ListFilter |
| Drag to reorder | GripVertical |
| Required/locked | Lock |
| User menu | CircleUser |
| Log out | LogOut |
| Printer status dot | none: 8 px circle in status colour |
| File | FileSpreadsheet |

Verify every icon name against the installed lucide-react; some older names (e.g. AlertTriangle, CheckCircle2) were renamed in newer releases.

**11.6 Branding**

- Sidebar top: 56 px area, product mark = Tag icon 20 px white in a 28 px #2563EB rounded-6 square, then "Novo Label Studio" 15/600 white.
- Company name from Settings shows under it in Caption --nav-text.
- Favicon: the same mark, 32 px PNG.
- Browser tab title: "{Page} · Novo Label Studio".

## 12. Screens

Nine screens plus dialogs. Default route after login is Print Labels. Every list screen has loading (skeleton rows ×8), empty, and error states as specified.

**12.1 App shell**

- Sidebar (240 px, --nav-bg): brand block (11.6), then nav items h 40, px 16, icon + label, gap 12, radius 6 inside 8 px side inset. Order: Print Labels, Parts, Configure, History, Settings. Operators see Print Labels, Parts (read-only), History.
- Bottom of sidebar: printer status block: 8 px status dot + "{printer name}" (13/600) + status word (12, --nav-text). Click → popover: status, "Last seen {relative time}", "Loaded labels: {size}", button "Print test label" (admin).
- Agent last seen > 30 s ago → status "Offline" regardless of reported status.
- Top bar (56 px, white, bottom border): page H1 left; right: CircleUser + display name + ChevronDown → menu: "{role}" (caption), "Log out".
- Keyboard: `/` focuses the page search; `Esc` closes dialogs/drawers.

**12.2 Login (/login)**

- Full page --bg, centred card 400 px: brand mark, H2 "Sign in", inputs "Username", "Password", primary button "Sign in" full width.
- Errors: "Username or password is incorrect." · locked: "Too many attempts. Try again in 15 minutes."

**12.3 First-run setup (/setup, only when no users exist)**

Stepper with 3 steps, card 640 px, buttons "Back" (secondary) / "Continue" (primary):

1. "Create the admin account": Display name, Username, Password (min 12 chars), Confirm password.
2. "Your company": Company name (default "Novo"), Serial prefix (default "NOVO"), Starting number (default 1), Digits (default 8). Live example: "First serial: NOVO-00000001".
3. "Connect the printer": shows the agent token once in a mono box with Copy button, the text "Install the Label Studio Agent on the laptop connected to the ZQ630 Plus, then paste this token when asked.", and a live indicator: "Waiting for the agent…" (spinner) → "Agent connected. Printer: {status}" (CircleCheck). Button "Print test label" enabled once connected. "Finish" (primary) always enabled; "Skip for now" allowed.

**12.4 Print Labels (/print)**

- H1 "Print Labels". Search input full width of content (max 720), h 44, Search icon, placeholder "Search part number, label name or description", autofocus, 200 ms debounce.
- Filter chips below (single-select): "All" · "Recently printed" (last 7 days) · "Out of date" · "Never printed". Chip: h 32, radius 999, selected bg --primary-subtle + text --primary.
- Table columns: \[checkbox 40\] · Image 64 (48 × 48 thumb, radius 6, ImageOff on #F3F4F6 when none) · "Label name" (label name 14/600; part name 13 --text-secondary below; if no label name, part name is the bold line) · "Part number" (mono) · "Size" (e.g. "4 × 2 in") · "Label" (freshness badge: Current / Out of date / Never printed) · actions right: ghost icon button Eye (tooltip "Preview") + primary small button "Print" (h 32, Printer 16).
- Sort: search score, then part number. 50 rows per page, infinite scroll.
- Selecting ≥ 1 checkbox shows a sticky bar at the bottom of the content: "{n} selected" · primary "Print selected" · ghost "Clear".
- Pressing Enter in search with exactly one result opens its Print dialog.
- Empty (no parts at all): Package icon, "No parts yet", "Import your parts list to start printing.", button "Import parts" (admin) / text "Ask an admin to import parts." (operator).
- No results: "No parts match "{q}"".

**12.5 Preview dialog (read-only)**

- Width 720. Title = label name or part name; subtitle mono part number.
- Body: the rendered PNG per 7.7; under it a meta row: size · "Config v{n}" · "QR: {mode}" · badge "Serial assigned at print" when serial is on.
- If the preview doesn't fit: TriangleAlert banner (warning) listing the messages from section 14.
- Footer: ghost "Close", primary "Print". No editing controls of any kind.

**12.6 Print dialog**

- Width 960, two columns. Left (560): live preview pane (--preview-surround, padding 24), re-rendered 250 ms after the last input change; spinner overlay while rendering. Right (400): form.
- Right column, top to bottom:
  1. Header: label name (16/600), part number mono, part name 13.
  2. "Show on label": a checklist of every printable field that has a value for this part (Label name, Part number, Part name, Description, Revision, custom fields, Serial number, Print date, QR code), pre-ticked from the part's saved selection, plus "Size" radio cards and "Text size" Small / Medium / Large. Ticking or unticking re-renders the preview. On Print, if the selection differs from the saved one, it is saved automatically as a new per-part config version and the dialog shows "Saved for this part" — next time the same choice is pre-ticked. Any user (operator or admin) can do this. Then print-time fields from the config, in config order. Text → input; Number → numeric input with min/max; Choice → segmented control if ≤ 4 choices, else select. Required fields show a red `*`.
  3. Box sequence (if configured): "Total boxes" stepper (1–999) + radio "Print all {T} boxes" / "Print one box" with "Box number" stepper.
  4. "Quantity" stepper (only with serials, no box sequence) with helper "Each label gets its own serial." and "Copies of each" stepper with helper "Identical copies, same serial."
  5. Printer line: status dot + "{printer name} · {status}".
  6. Size check: if printer.loaded\_label\_size ≠ config size → warning banner "The printer has {loaded} labels loaded. This label is {size}." + secondary button "I've loaded {size} labels".
  7. Total line: "{labels} labels · {serials} serials".
- Footer: ghost "Cancel"; Big print button "Print" (or "Print {n} labels" when n > 1). Disabled when: preview doesn't fit, a required field is empty, printer Offline, or size mismatch unresolved.
- After submit: button shows spinner "Sending…"; on job `sent`: success panel replacing the form: CircleCheck 32 px success, "Sent to printer", serial list (mono, max 5 then "+{n} more"), buttons "Print box {n+1} of {T}" (when applicable), secondary "Print another", ghost "Done". On `failed`: CircleX danger, "Print failed", the error text, button "Try again" (new job with a new idempotency key, same inputs; serials are newly allocated).
- Batch mode (from "Print selected"): the preview pane gets a stepper "‹ 1 of {n} ›"; the form shows a compact list of selected parts, each row: label name, required print-time inputs inline, a Quantity stepper (serialized parts only) and a Copies stepper. Parts that don't fit are listed first with a warning badge and block printing until removed ("Remove" link).

**12.7 Parts (/parts)**

- Toolbar: search (same component as 12.4), status select "Active" (default) / "Inactive" / "Archived" / "All", then right-aligned: secondary "Import" (Upload), primary "Add part" (Plus). Buttons hidden for operators.
- Table columns: Image 64 · "Part number" (mono) · "Part name" · "Label name" (Tag 14 + text, or "—") · "Revision" · "Status" badge · "Updated" (relative, tooltip absolute). Row click → Part drawer.
- Empty: FileSpreadsheet icon, "Your parts list is empty", "Import a CSV or Excel file, or add parts one at a time.", buttons "Import parts" + ghost "Add part".

**12.8 Part drawer**

- Header: 64 px image (click → "Change image" for admin, ImagePlus overlay on hover), label name 20/600 (or part name), part number mono, status badge, freshness badge.
- Tabs: "Details" · "Label names" · "Label".
- Details: form with Part number, Part name, Description (textarea 4 rows), Revision, then custom fields in sort order. Read-only for operators. Footer: "Save" (primary, only enabled when dirty), "Cancel", and left-aligned danger-ghost "Archive part" → confirm dialog "Archive {part number}? It will disappear from Print Labels. Print history is kept." \[Cancel\] \[Archive\].
- Label names: list rows: Tag icon, alias text, a "Label name" badge (primary-subtle) on the one used for printing, row menu: "Use as label name", "Rename", "Remove". Add row: input placeholder "e.g. 10-32 x 1/2 16" + "Add". Checkbox "Use as label name" (checked by default when the part has none). Helper: "Searching any of these names finds this part."
- Label: shows the effective config ("Uses the default label" or "Custom label for this part · v{n}"), a static preview, "Last printed {date}" or "Never printed", buttons "Customize for this part" (opens Configure editor scoped to this part) and, when an override exists, ghost "Use default label".

**12.9 Add part dialog**

- Width 560. Fields: Part number\*, Part name\*, Label name (optional, creates the alias as label name), Description, Revision, custom fields. Primary "Add part". Duplicate part number → field error "A part with this number already exists." with link "Open it".

**12.10 Import (/parts/import) — full page, dark hero**

- Step 1, hero: background vertical gradient --hero-bg-from → --hero-bg-to, full content height. Centred column 720 px: Display text "Give us your parts list", body --hero-text-muted "Upload a CSV or Excel file. We'll match the columns and show you every change before anything is saved.". Drop zone 720 × 240, radius 16, 2 px dashed --hero-drop-border, fill --hero-drop-bg: Upload icon 40 px white, "Drop your file here" 16/600 white, "or" muted, secondary button "Choose file" (white bg). Under it: "CSV · XLSX · XLS · up to 20 MB" Caption muted. Drag-over: border --primary, fill hover colour.
- While parsing: drop zone content swaps to spinner + "Reading {file name}…".
- Steps 2–5 switch to the normal light layout with a stepper at top: "Upload" · "Match columns" · "Review" · "Done".
- Match columns: table with columns "Column in your file" (header, mono) · "Sample values" (first 3 non-empty values, muted, comma-separated, truncated at 60 chars) · "Maps to" (select). Above the table, info banner when a saved mapping applied. Below: "Save this mapping as" input. Footer: "Back", primary "Continue".
- Review: four summary cards in a row (surface, 24 padding): "New" · "Updated" · "Unchanged" · "Need attention" with the count 32/700 and icon (Plus / RefreshCw / CircleCheck / TriangleAlert), plus a fifth muted card "Missing from file" when > 0. Clicking a card filters the table. Table columns: accept checkbox · "Row" · "Part number" · "Part name" · "Changes" (for updates: `field: old → new` chips; old in strikethrough --text-muted, new --text) · "Problem" (danger text for invalid). Invalid rows have an inline "Fix" button opening a small editor for that row. Footer: "Back", "Discard import" (ghost danger), primary "Import {n} parts".
- Done: CircleCheck 40 px success, H2 "Import complete", lines "{n} new · {n} updated · {n} marked inactive", "{n} rows skipped because of errors." when any, buttons "View parts" and "Print out-of-date labels" (goes to Print Labels with the Out of date chip on).

**12.11 Configure (/configure, admin)**

- List page: card "Default label" (static preview left 280 px wide, right: size, fields summary, "Version {n} · published {date} by {name}", primary "Edit default label"). Below: H2 "Custom labels for specific parts" table: Part number · Label name · Size · Version · Published · row → editor. Empty text: "All parts use the default label."
- Editor (/configure/default or /configure/part/{id}): left panel 440 px scrollable with collapsible sections, right sticky preview pane with a "Preview with part" combobox (search parts; default = first active part) and the 7.7 preview.
- Section "Size": radio cards for each active size (name, dimensions, a proportional rectangle icon).
- Section "What's on the label": ordered list of chosen fields, each row: GripVertical, field name, role select (Main line / Second line / Detail), "Caption" input (placeholder "none"), "UPPERCASE" switch, remove X. "+ Add field" menu grouped: Part fields, Custom fields, Generated (Serial number, Print date), Print-time fields. Main line limited to 1, Second line to 2, Detail to 6 (disabled options show tooltip "Limit reached").
- Section "Print-time fields": list + "Add print-time field" → dialog: Name (key auto from name), Type (Text / Number / Choice / Box sequence), type options (max length; min/max/whole numbers; choices list; noun), "Required" switch.
- Section "QR code & serial": "Serial number" switch ("Give every label a unique serial"); "QR code" segmented: "None" / "Part" / "Serial" (Serial disabled unless serial is on, tooltip "Turn on serial numbers first"); "QR position" Left / Right (hidden when none).
- Section "Style": Font select (Inter, Roboto Condensed, Atkinson Hyperlegible, each option rendered in its font); "Main line weight" Regular / Bold / Extra bold; "Text size" Small / Medium / Large; "Alignment" Left / Center; "Spacing" Compact / Standard / Spacious.
- Fit status under the preview: success "Fits" or warning list. Header buttons: ghost "Cancel", primary "Publish version {n+1}" (disabled when nothing changed or doesn't fit for the preview part). Leaving with unsaved changes → confirm "Discard your changes?" \[Keep editing\] \[Discard\].

**12.12 History (/history)**

- Search placeholder "Search serial, part number or label name". Filters: date range (Today / 7 days / 30 days / Custom), "Printed by" select, "Reprints only" switch.
- Table: "Time" · "Label" (label name + part number mono) · "Serial" (mono, or "—") · "Box" (e.g. "2/3") · "Size" · "Copies" · "By" · "Status" badge · action ghost button "Reprint" (RotateCcw). Row → History drawer.
- History drawer: the exact stored bitmap, a key/value list of the snapshot (field label → value), job info (job id mono, printer, status timeline with timestamps), reprints list, serial status. Buttons: primary "Reprint exact label" → reason dialog (radio: Damaged, Missing, Print issue, Other + optional note) → prints. Admin: danger-ghost "Void serial" → dialog requiring a reason (min 5 chars).
- Exact serial typed in search opens its drawer directly.

**12.13 Settings (/settings, admin) — vertical tabs left (200 px)**

- "General": Company name.
- "Serial numbers": Prefix, Separator (Dash / Underscore / None), Digits, Next number (raise only), live example; lock note per 9.1.
- "Label sizes": table (Name, Width, Height, Status, Used by) + "Add size" dialog (Name, Width in, Height in, validation per section 3). Sizes in use cannot change dimensions ("Used by {n} labels").
- "Custom fields": table (Name, Key mono, Type, Required, Searchable, Printable) + "Add field" dialog.
- "Printers": printer card: model, status, last seen, loaded size select, Darkness (0–30, empty = printer default), Speed, X/Y offset (dots, −200 to 200), buttons "Print test label", "New agent token" (confirm: "The old token stops working immediately.").
- "Users": table (Name, Username, Role, Status, Last login) + "Add user" (Display name, Username, Role, temporary Password); row menu: "Reset password", "Change role", "Deactivate".

**Test label content** (printed by "Print test label"): a 13-dot border at the safe margin, a 1-inch ruler along top and left with ticks every 0.1 in, and text lines "Novo Label Studio test", "{printer name} · {dpi} dpi", "{loaded size}", "{date time}", "v{app version}".

## 13. User flows

Each flow lists what the user does and what the system must do. Screens are in section 12.

**13.1 First install (admin)**

1. Admin opens the app URL → redirected to /setup (no users exist).
2. Creates the admin account, company, serial settings.
3. Copies the agent token, installs the agent on the laptop, pastes the token. Setup shows "Agent connected".
4. Clicks "Print test label"; checks alignment; adjusts offsets later in Settings → Printers if needed.
5. Finish → Parts (empty state) → "Import parts".

**13.2 First import**

1. Drops `NovoParts.xlsx` on the hero. System parses, detects one sheet, suggests the mapping.
2. Admin fixes any "Maps to" choices, names the mapping, Continue.
3. Review shows e.g. 1,284 New, 4 Need attention. Admin fixes 2 rows, leaves 2 skipped.
4. "Import 1,282 parts" → Done → "View parts".

**13.3 Re-import after a revision change**

1. Admin drops the new file; the saved mapping applies automatically.
2. Review: 18 Updated (e.g. `revision: C → D`), 3 Missing from file (unticked).
3. Import. Parts whose printed labels include a changed field now show "Out of date".
4. Done → "Print out-of-date labels" → Print Labels filtered → select all → "Print selected".

**13.4 Give a part a label name**

1. Parts → search "NP-10421" → open drawer → "Label names".
2. Type "10-32 x 1/2 16", keep "Use as label name" ticked, Add.
3. System validates (unique, not another part number), saves, audits. Part shows "Out of date" if it was printed before.
4. From now on, Print Labels search for "10-32", "10 32 x 1/2 16" or "NP-104" all find NP-10421.

**13.5 Print one label (operator)**

1. Print Labels → type "bearing" → row "Bearing Housing" → "Print".
2. Dialog shows the preview. No print-time fields → big "Print" enabled.
3. Click Print → job created with Idempotency-Key → serial allocated if configured → agent sends → "Sent to printer" with the serial.

**13.6 Print a box set**

1. Part's config has a Box sequence field. Operator opens Print, sets "Total boxes" 3, chooses "Print all 3 boxes".
2. One job, 3 labels BOX 1/3, 2/3, 3/3, each with its own serial.
3. Alternative: "Print one box" (box 1) → success panel → "Print box 2 of 3" → "Print box 3 of 3".

**13.7 Batch print**

1. Print Labels → tick 12 rows → "Print selected".
2. Dialog lists 12 parts; operator fills required print-time fields per row, sets copies, steps through previews.
3. "Print 12 labels" → one job (or several of ≤ 200 labels).

**13.8 Reprint a damaged label**

1. History → type the serial "NOVO-00001843" → drawer opens.
2. "Reprint exact label" → reason "Damaged" → Print.
3. Same serial, same data, same bitmap; history shows the reprint under the original.

**13.9 Customize the label for one part**

1. Part drawer → Label → "Customize for this part" → editor starts from the current default.
2. Admin adds a Box sequence field, switches QR to Serial, publishes v1 for this part.
3. That part now prints with its override; other parts keep the default. "Use default label" removes the override.

**13.10 Printer problem**

1. Printer runs out of labels. Agent heartbeat reports out\_of\_media; sidebar dot turns red "Out of labels"; Print buttons disabled with tooltip "The printer is out of labels."
2. Operator reloads media; status returns to Ready; printing resumes. Jobs are never auto-retried.

## 14. Validation rules and messages

The API validates everything; the UI mirrors the same rules for instant feedback. The message column is the literal UI string (import row messages are in 10.3).

**14.1 Print blocking**

Printing is disabled when any is true: preview `fits = false`; a required print-time field is empty; printer status is offline, out\_of\_media, head\_open, paused or error; agent last seen > 30 s; loaded size ≠ label size (until confirmed). Status ready, printing or unknown allows printing. The disabled button's tooltip shows the first matching message below.

**14.2 Error codes**

| Code | HTTP | Message |
| --- | --- | --- |
| AUTH\_INVALID | 401 | Username or password is incorrect. |
| AUTH\_LOCKED | 423 | Too many attempts. Try again in 15 minutes. |
| SESSION\_EXPIRED | 401 | Your session expired. Sign in again. |
| FORBIDDEN | 403 | You don't have permission to do that. |
| NOT\_FOUND | 404 | We couldn't find that. It may have been archived. |
| STALE\_WRITE | 409 | Someone else changed this. Reload to see the latest version. |
| PART\_NUMBER\_TAKEN | 409 | A part with this number already exists. |
| ALIAS\_TAKEN | 409 | This name is already used for part {part\_number}. |
| ALIAS\_IS\_PART\_NUMBER | 409 | This name is another part's part number. |
| ALIAS\_EMPTY | 422 | Enter a name with at least one letter or number. |
| FIELD\_REQUIRED | 422 | {Field} is required. |
| FIELD\_TOO\_LONG | 422 | {Field} is longer than {max} characters. |
| FIELD\_NOT\_NUMBER | 422 | {Field} must be a number. |
| FIELD\_OUT\_OF\_RANGE | 422 | {Field} must be between {min} and {max}. |
| FIELD\_NOT\_CHOICE | 422 | {Field} must be one of: {choices}. |
| FILE\_TOO\_LARGE | 413 | This file is too large. Limit: 20 MB and 50,000 rows. |
| FILE\_UNSUPPORTED | 415 | Upload a CSV, XLSX or XLS file. |
| FILE\_UNREADABLE | 422 | We couldn't read this file. Save it again as CSV or XLSX and retry. |
| FILE\_NO\_HEADER | 422 | We couldn't find a header row. The first non-empty row must contain column names. |
| MAPPING\_INCOMPLETE | 422 | Map a column to Part Number and Part Name to continue. |
| MAPPING\_DUPLICATE\_TARGET | 422 | Each field can be mapped from one column only. |
| IMPORT\_EXPIRED | 410 | This import expired. Upload the file again. |
| SIZE\_UNSUPPORTED | 422 | This size doesn't fit the ZQ630 Plus (media 2.0–4.4 in wide). |
| SIZE\_IN\_USE | 409 | This size is used by {n} labels, so its dimensions can't change. |
| CONFIG\_ROLE\_LIMIT | 422 | A label can have 1 main line, 2 second lines and 6 detail lines. |
| CONFIG\_QR\_NEEDS\_SERIAL | 422 | Turn on serial numbers to use a serial QR code. |
| TEXT\_TOO\_LONG | 422 | "{Field}" is too long for this label size. Choose a larger size or a smaller text size. |
| CONTENT\_TOO\_TALL | 422 | Too much information for this label size. Remove a field or choose a larger size. |
| QR\_TOO\_SMALL | 422 | The QR code would be too small to scan. Choose a larger size or move fields. |
| QR\_PAYLOAD\_TOO\_LONG | 422 | This part number is too long for the QR code. |
| REQUIRED\_VALUE\_MISSING | 422 | Enter {Field} to print. |
| PRINTER\_OFFLINE | 409 | The printer is offline. Check the USB cable and that the printer is on. |
| PRINTER\_OUT\_OF\_MEDIA | 409 | The printer is out of labels. |
| PRINTER\_HEAD\_OPEN | 409 | The printer cover is open. |
| PRINTER\_PAUSED | 409 | The printer is paused. Press the pause button on the printer. |
| PRINTER\_ERROR | 409 | The printer reported an error. Check it and try again. |
| AGENT\_UNREACHABLE | 409 | The print agent on the laptop isn't responding. |
| SIZE\_NOT\_LOADED | 409 | Load {size} labels in the printer, then confirm. |
| SERIAL\_VOIDED | 409 | This serial was voided and can't be reprinted. |
| SERIAL\_SETTINGS\_LOCKED | 409 | Locked after the first serial is issued. |
| SERIAL\_EXHAUSTED | 409 | The serial sequence is full. Increase the digit count in Settings. |
| JOB\_NOT\_CANCELLABLE | 409 | This job has already been sent to the printer. |
| LAST\_ADMIN | 409 | There must be at least one active admin. |
| SERVER\_UNREACHABLE | — | Can't reach the server. Printing is paused. |
| INTERNAL | 500 | Something went wrong. Try again; if it keeps happening, contact your admin. (ref {request\_id}) |

## 15. Non-functional requirements

Targets assume 50,000 parts, 5 concurrent users and one printer.

| Area | Requirement |
| --- | --- |
| Search | `search_parts` p95 < 150 ms server-side |
| Preview | Render p95 < 300 ms for a 4 × 6 in label |
| Print | Click Print → job `queued` < 500 ms; agent pickup ≤ poll interval + 200 ms |
| Import | 50,000-row XLSX parsed, validated and diffed < 60 s; runs as a background task with a progress bar ("Checking rows… {n} of {total}") |
| Page load | First meaningful paint < 2 s on the LAN |
| Passwords | argon2id (time 3, memory 64 MiB, parallelism 2); min length 12 |
| Sessions | Random 32-byte token, stored as sha256 in `user_session`; 12 h idle expiry; logout deletes the row |
| Agent token | 32 random bytes, shown once, stored as argon2id hash; rotation invalidates the old one immediately |
| Transport | HTTPS only; nginx with a certificate installed at setup (self-signed allowed on the LAN) |
| Uploads | MIME and extension checked; images re-encoded to PNG ≤ 1024 px long edge; spreadsheets never executed (no macros) |
| Input safety | Parameterized SQL only; CSV export (future) must escape leading `= + - @` |
| Audit | Section 5 invariant 1; audit rows kept forever |
| Backups | Nightly `pg_dump` custom format + tar of `ASSET_DIR` to `/backups`, keep 30 days; restore procedure tested at M6 |
| Logging | JSON logs with request\_id, user\_id, route, status, duration; no passwords, tokens or file contents |
| Health | `GET /api/v1/health` → `{db: ok, agent_last_seen}` |
| Accessibility | Keyboard reachable controls, visible focus ring, WCAG AA contrast for all text tokens, labels on all inputs |
| Browsers | Latest Chrome and Edge on Windows 10/11 |
| Time | All server times UTC; UI shows local time |

## 16. Testing and acceptance

A feature is done only when its automated tests pass and its acceptance checks below pass on the real printer where marked.

**16.1 Automated tests (required)**

- Schema: loads cleanly on Postgres 16; triggers reject config mutation, printed\_label update/delete, reprint mismatch, alias collisions, group index > total.
- Serials: 20 concurrent `allocate_serials` calls of 50 each produce 1,000 distinct consecutive serials; a rolled-back transaction leaves no gap and no rows.
- Renderer golden tests: fixed inputs → byte-identical PNG sha256 for each layout family × each preset size × each font. Goldens are committed; any change requires updating them deliberately.
- Fit tests: long label name wraps to 2 lines then fails with TEXT\_TOO\_LONG; 9 fields on Small fails with CONTENT\_TOO\_TALL; QR on Small with 3 text lines fails or passes per 7.6 math.
- ZPL tests: `^GFA` byte count = bpr × H; decoding the hex back gives the inverted bitmap.
- Import: synonyms map correctly; duplicates flagged; empty cells don't clear; saved mapping reused by signature; commit is all-or-nothing.
- Search: "10-32", "10 32 x 1/2 16", and part-number prefix all return the aliased part first.
- API: every endpoint's role guard; idempotency returns the same job.
- UI (Playwright): flows 13.1–13.9 end to end against a fake agent.

**16.2 Acceptance checks**

| # | Check | Pass when |
| --- | --- | --- |
| A1 | Preview = print | Printed label scanned at 600 dpi and overlaid on the preview PNG: no element off by more than 2 dots **\[printer\]** |
| A2 | QR scans | Phone camera reads `PN:` and `SN:` payloads on every preset size **\[printer\]** |
| A3 | Serial safety | Two browsers printing 20 labels each at the same time: 40 unique serials, no gaps |
| A4 | Reprint | Reprinted label is byte-identical bitmap and same serial |
| A5 | Box set | "Print all 3 boxes" gives BOX 1/3, 2/3, 3/3 with 3 distinct serials **\[printer\]** |
| A6 | Import | 1,000-row file with 10 bad rows: 990 imported, 10 listed with exact messages |
| A7 | Re-import | Revision change marks printed parts Out of date; label names unchanged |
| A8 | Label name search | Every alias form in 13.4 finds the part |
| A9 | Printer errors | Unplug USB → status Offline within 40 s; Print disabled with PRINTER\_OFFLINE message **\[printer\]** |
| A10 | Roles | Operator cannot reach Configure, Settings, Import, or any admin endpoint |
| A11 | Offsets | +10 dot X offset visibly shifts the test label \~1.25 mm **\[printer\]** |
| A12 | Backup | Restore last night's backup to a fresh machine; history and bitmaps intact |

## 17. Build order

Build the riskiest path first: render → ZPL → agent → real printer, before any UI polish. Each milestone ends at its gate; don't start the next until it passes.

1. **M0 Hardware spike.** Script renders one Large label, encodes `^GFA`, sends RAW via win32print to the ZQ630 Plus; test `~HS` readback over USB. Gate: A1 and A2 pass on one label; readback result recorded in the decision log.
2. **M1 Foundation.** Repo, Docker Compose, schema migration 0001, auth, sessions, roles, setup wizard, app shell with design tokens. Gate: login/setup/role tests pass.
3. **M2 Parts.** Parts CRUD, images, custom fields, label names + search. Gate: A8, search tests.
4. **M3 Import.** Parsing, mapping, validation, diff, commit, hero UI. Gate: A6, A7.
5. **M4 Render + Configure.** Full layout engine, golden tests, Configure editor, preview endpoint. Gate: golden + fit tests; A1 on all presets.
6. **M5 Print.** Serials, jobs, agent service, Print dialog, batch, box sets, printer status, test label. Gate: A2, A3, A5, A9, A11.
7. **M6 History + hardening.** History, reprint, void, audit views, backups, logging, performance targets. Gate: A4, A10, A12, section 15 targets.

**Open questions (answer before the milestone that needs them)**

- M0: does `~HS` readback work over USB on Windows? If not, D17's "Sent to printer" is final for v1.
- M4: confirm the default label layout (seed data in section 5) with a real sample part.
- M5: which synthetic direct-thermal media part number to standardise on, after the 30-day rack test.
