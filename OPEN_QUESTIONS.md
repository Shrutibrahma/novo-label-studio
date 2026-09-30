# Open questions

Gaps or ambiguities found while building v1 from `SPEC.md` + `schema.sql`. For each: the question, what was
chosen, and why. None of these change a Decision-log item. One changes the database schema, with your approval:
#75 (migration 0002, faster `search_parts()`); `schema.sql` itself is unchanged.

## M1 — Foundation

1. **Messages missing from 14.2 for account/setup validation.**
   Chose extra codes with plain messages: `USERNAME_INVALID` ("Username can use 3–64 letters, numbers, dots,
   dashes and underscores."), `USERNAME_TAKEN` ("This username is already taken."), `PASSWORD_TOO_SHORT`
   ("Password must be at least 12 characters."), `PASSWORDS_DIFFERENT` ("The passwords don't match."),
   `SERIAL_PREFIX_INVALID` ("Serial prefix can use 1–12 capital letters and numbers."), `SETUP_DONE`
   ("Setup is already complete."), `SIZE_NAME_TAKEN` ("A size with this name already exists.").
   Why: the rules exist in schema.sql/section 15 but have no UI string; these are the shortest literal
   statements of each rule.
2. **What does the 5th failed login return?** Chose `AUTH_LOCKED` on the attempt that triggers the lock
   (attempts 1–4 return `AUTH_INVALID`). Why: the account is locked at that moment; the message tells the user
   what to do. Unknown and inactive usernames return `AUTH_INVALID` and don't count.
3. **Cookie lifetime.** `ls_session` is a browser-session cookie (no Max-Age); the 12 h idle expiry is enforced
   server-side and slides forward on use (touched at most once a minute). Why: section 15 defines the expiry
   server-side; a fixed cookie lifetime would contradict "idle".
4. **Seeded names.** Printer name "ZQ630 Plus" (the name used in the sidebar), agent name "Laptop agent",
   `loaded_label_size_id` NULL until someone confirms what is loaded. Why: section 3 lists the profile but
   not a name; NULL is honest — the app doesn't know what media is in the printer until told.
5. **Default config roles and case.** Seed v1 = `part_number` role primary, `part_name` role secondary,
   `uppercase: false`, no captions. Why: section 5 says the first field is the main line; nothing says
   to uppercase, and part numbers print as entered.
6. **Audit action names not listed.** `serial_sequence` changes are logged as `serial.update`; the printer
   created by /setup is logged as `printer.update`; agent-token rotation is `printer.update`.
   Not audited: login counters/`last_login_at`, printer heartbeat status, and `allocate_serials`
   (the `issued_serial` table is itself the permanent record of every allocation). Why: auditing a heartbeat
   every 10 s or every allocation would flood the log without adding information.
7. **Test label details.** Border 2 dots thick with its outer edge on the 13-dot safe margin; ruler ticks
   0.1 in apart (minor 10 dots, 0.5 in 16 dots, 0 and 1 in 24 dots); Inter Regular starting at 10 pt and
   shrinking to fit; "{loaded size}" rendered as "Large · 4 × 2 in". Printed at the loaded size, or the
   default label's size when none is confirmed. Printer-status rules of 14.1 apply (no size check).
8. **Laptop time zone on the server.** The browser sends its IANA zone in `X-Timezone`; the API uses it for
   `print_date` and the test label's "{date time}". Falls back to UTC. Why: the API renders labels but only
   the browser knows the laptop's zone.
9. **Printer speed values.** Whole numbers 1–14 ips (the ZPL `^PR` range). Why: `speed_ips` is
   `numeric(3,1)` but `^PR` only accepts whole numbers.
10. **Status colour for "Paused".** Danger (red dot/badge). Why: the 11.1 mapping doesn't list Paused, and
    Paused blocks printing like the other danger states.
11. **Ports on this machine.** HTTPS 8443 (dev), 9443 (e2e); plain HTTP 8088/9088 only redirects to HTTPS.
    Port 8080 was already taken by another container. Configurable in `deploy/.env`.
12. **Session expiry while a page is open.** Any API call that returns `SESSION_EXPIRED` sends the browser to
    /login and returns to the same page after sign-in.
13. **`If-Match` precision.** Compared to `updated_at` within 0.5 ms. Why: JSON timestamps carry microseconds;
    allows for float round-trips in clients.

## M2 — Parts

14. **Part images: missing endpoint and messages.** Added `GET /parts/{id}/image` (the table only lists PUT and
    DELETE, but thumbnails must be served). Errors: `IMAGE_UNSUPPORTED` "Upload a PNG, JPEG or WebP image.",
    `IMAGE_TOO_LARGE` "This image is too large. Limit: 10 MB.". Identical images share one asset row (sha256
    unique). The spec has no "remove image" control, so the UI only offers "Change image".
15. **Manual-entry limits.** The import limits of 10.3 also apply to manual entry (part number 64, part name 200,
    description 1000, revision 16); custom text values ≤ 1000. Manual entry uses the 14.2 wording
    ("{Field} is required.", "{Field} is longer than {max} characters."); imports keep 10.3's.
    Date values need a code: `FIELD_NOT_DATE` "{Field} must be a date." (text from 10.3).
16. **Part number equal to another part's label name (manual entry).** Rejected with `PART_NUMBER_IS_ALIAS` and
    10.4's text "This part number is already used as a label name for part {part_number}.".
17. **What "searchable" does for a custom field.** Searchable fields are matched by `GET /parts?q=` as exact
    (score 1.0) or prefix (0.9) matches on the value, merged with `search_parts()` results. `search_parts()`
    itself is unchanged. Why: the flag exists in schema.sql but its behaviour isn't specified.
18. **Search on the Parts screen with Inactive/Archived/All.** `search_parts()` returns active parts only, so
    for those filters the same scoring runs without the active-only condition.
19. **Custom field keys.** Auto-derived from the name (editable until created, fixed after). Reserved keys
    (`part_number`, `part_name`, `description`, `revision`, `label_name`, `serial`, `print_date`, …) are
    rejected with `FIELD_KEY_TAKEN` "A field with this key already exists."; malformed keys with
    `FIELD_KEY_INVALID`. A choice field has 1–100 choices.
20. **Restoring an archived part.** `POST /parts/{id}/restore` exists but 12.8 only names "Archive part"; the
    drawer shows "Restore" (ArchiveRestore icon, 11.5) in that place for archived parts.
21. **Empty filter results.** A filter chip with no matching parts (and no search text) shows the table header
    with no rows; the spec defines only "No parts yet" and "No parts match "{q}"".
22. **After "Add part".** The dialog closes and the list refreshes; the new part's drawer does not open.
23. **Row menus.** Triggered by ChevronDown ("Menu chevron", 11.5); the icon table has no "more" icon.
    Users: inactive users get "Activate" in place of "Deactivate".
24. **List error state.** Every list shows a danger banner with the API message (or "Can't reach the server.
    Printing is paused.") — the spec requires an error state but doesn't define it.
25. **Settings forms.** Each Settings form saves with a "Save" button that is enabled only when something
    changed; there is no success toast (the spec defines none).
26. **Demo data.** `scripts/demo.ps1` adds a searchable text custom field "Material" and 52 parts; it needs
    first-run setup to be done because every row has an owner.

## M3 — Import

27. **Header normalization edge underscores.** After "non-alphanumerics → `_`, collapse repeats", leading and
    trailing `_` are dropped, so "Part No." matches the synonym `part_no`.
28. **Blank and duplicate headers.** A blank header cell becomes "Column {n}"; a repeated header gets
    " (2)", " (3)"… so every column can be mapped.
29. **Choosing a sheet.** Added `PUT /imports/{id}/sheet {sheet_name}` (not in the endpoint table). The "Which
    sheet?" list shows each non-empty sheet with its data-row count (rows below the header).
30. **Part name on existing parts.** "Part name is missing." applies to new parts only — for a matched part an
    empty cell never clears (10.4). Over-long names use "Part name is longer than 200 characters."
    (10.3 lists only the missing case).
31. **Inactive parts that reappear in a file.** Proposed as an update `status: inactive → active`, accepted by
    default. Archived parts follow 10.4: "Restore archived part", not accepted.
32. **Part-number spelling on re-import.** Matching is on the normalized number; an existing part keeps its
    stored spelling.
33. **Audit granularity for imports.** One `import.commit` row per commit with the counts, not one row per part.
34. **Counts after commit.** The batch's new/updated/missing counts are overwritten with what was actually
    committed; the Done screen shows those. "Import {n} parts": n = accepted new + updated rows.
35. **Concurrent change before commit.** If a "new" row's part number was created in the meantime, the whole
    commit is refused with `STALE_WRITE` and nothing is written.
36. **"Fix" editor.** A dialog titled "Row {n}" with an input per mapped field, Cancel / Save. Fixing a
    duplicate re-checks every row that shared the number.
37. **Back from Match columns / Review.** Back from Match columns returns to the upload hero; the unused batch
    simply expires. Back from Review reopens Match columns (re-mapping re-validates the file).
38. **Discard import.** Acts immediately; the spec defines no confirmation.
39. **"+ New custom field…".** Opens the Add field dialog pre-filled with the column's header; the new field is
    then selected for that column.
40. **Where the work runs.** Parsing and validation run as background tasks inside the API process; progress is
    stored on `import_batch`. The 24-hour expiry job also deletes the stored upload.

## M4 — Render + Configure

41. **Tall preset and `qr_top`.** Tall (4 × 6 in) renders at 812 × 1218 dots, exactly H = 1.5 × W, so the rule
    "H ≤ 1.5 × W → qr_side" gives it the side layout; `qr_top` only appears on custom sizes that are taller
    and narrower (e.g. 2 × 4 in). The golden set therefore covers qr_top with a 2 × 4 in size.
42. **PNG bytes across platforms.** Pillow's Windows and Linux wheels bundle different deflate libraries, so
    identical pixels gave different PNG bytes (and sha256). Label PNGs are written by our own 1-bit PNG
    writer using Python's `zlib` (level 9); goldens now match byte-for-byte on Windows and in the container.
43. **Shrink first, then wrap.** 7.5 is applied in order: a line first shrinks in 0.5 pt steps to its minimum;
    only if it is still too wide does a main/second line wrap onto two lines (choosing the break that makes
    the longer line shortest, at the largest size where both lines fit). The height pass then shrinks all
    lines together and re-checks each line's wrap.
44. **Print-time fields need a display name.** Each `manual_fields` entry carries a `label` (the dialog's "Name")
    used in the Print dialog and in messages like "Enter {Field} to print."; the key is derived from it.
    At most one Box sequence field per label.
45. **UPPERCASE and captions.** UPPERCASE applies to the value only; captions print exactly as typed.
46. **Role for a newly added field.** Main line if there is none, else Detail (up to 6), else Second line; when
    all roles are full, "+ Add field" items are disabled with "Limit reached".
47. **Turning serial numbers off while QR = Serial.** QR code switches to None.
48. **Required print-time fields in the editor.** The preview part has no print-time values, so
    `REQUIRED_VALUE_MISSING` doesn't count against "Fits" / "Publish" in the Configure editor (it still blocks
    printing).
49. **Config validation messages not in 14.2.** `CONFIG_INVALID` "This label configuration isn't valid. Reload and
    try again." (malformed spec, bad noun, duplicate keys) and `CONFIG_FIELD_UNKNOWN` "A field on this label no
    longer exists. Remove it and publish again." (e.g. a deleted custom field or a non-printable one).
50. **Extra endpoints.** `GET /configs` (list page data: default + current overrides) and `GET /configs/{id}`.
    Config responses include `next_version` so the editor can show "Publish version {n+1}"; per-part versions
    keep counting after "Use default label" (the next override continues the same config key).
51. **Retiring an override is audited** as `config.publish` with `after = {"retired": true}` (no separate action
    name exists).
52. **Optimistic check for publishing.** `POST /configs` accepts `base_config_id` (the version the editor loaded);
    if another version was published meanwhile the publish fails with `STALE_WRITE` (label_config has no
    `updated_at` for If-Match).
53. **Small static previews.** The Configure card (280 px) and the part drawer show the label scaled *down* to fit
    — at 1× a Large label (812 px) wouldn't fit. The Print and Configure preview panes follow 7.7 exactly
    (integer multiples, minimum 1×, scroll if needed).
54. **Editor layout.** Each field row has two lines (name + remove; role / caption / UPPERCASE) so the 440 px
    panel stays readable. Reordering: drag the grip, or Alt+↑ / Alt+↓ on it.
55. **After publishing** the editor returns to the Configure list.

## M5 — Print

56. **Print request shape.** Beyond the spec's body: `loaded_size_confirmed` (see 61) and, per item,
    `group: {total, start_index, count, group_id}` — `count` = how many boxes from `start_index` ("Print all" =
    total, "Print one box" = 1) and `group_id` continues an existing box set so "Print box {n+1} of {T}" reuses
    the group created by the first print. The response carries the jobs, the serials and the group ids.
57. **Request size limit.** At most 1,000 labels per print request (`PRINT_TOO_LARGE`, "Labels must be between 1
    and 1000."); jobs still split at 200 labels.
58. **Quantity without serials** must be 1 (`FIELD_OUT_OF_RANGE`), because 9.2 only offers Quantity with serials.
59. **Printing a non-active part** is refused (`NOT_FOUND`); Print Labels lists active parts only.
60. **A label that doesn't fit** is refused by `POST /print` before any serial is allocated, with the first
    render warning as the message (the widest-digit placeholder guarantees the real serial fits).
61. **"I've loaded {size} labels" for operators.** Operators can't `PATCH /printers`, so the confirmation is sent
    with the print (`loaded_size_confirmed: true`) and the API records it on `printer.loaded_label_size_id` in the
    same transaction (audited `printer.update`). A batch mixing label sizes can't be confirmed in one go.
62. **Size banner when nothing is confirmed yet.** "The printer has — labels loaded. This label is {size}."
63. **Lease expiry message.** A job failed by the 60 s lease shows AGENT_UNREACHABLE's text.
64. **Serial effects.** `failed` turns only `allocated` serials `unconfirmed`; `sent`/`confirmed` turn `allocated`
    or `unconfirmed` serials `printed` (so a successful reprint of an unconfirmed label marks it printed).
    Status reports that don't fit the 8.3 state machine get `409 INVALID_STATE`.
65. **Simulated printer in a forced error state.** A job it receives while not ready fails with
    "Simulated printer is {status}" (a real spooler would hold it; the API already refuses new prints then).
66. **"Show on label" → QR code / Serial number.** The selection endpoint may only change fields, size and text
    size, so "QR code" is shown ticked/unticked as configured and disabled; "Serial number" toggles the serial
    line and is offered only when the label has serials. A newly ticked field gets the same default role as in
    Configure (#46).
67. **Batch mode** prints each part with its saved label (no per-part "Show on label"); a part with a Box sequence
    prints BOX 1/1 in a batch.
68. **Label counts.** "Print {n} labels" and "{labels} labels · {serials} serials" count physical labels
    (distinct labels × copies); serials count distinct serialized labels.
69. **Print dialog title** is "Print" (single and batch); the spec names none.
70. **Preview pane width.** In the 560 px Print dialog pane a 4-inch label (812 dots) is wider than the pane at 1×;
    7.7 says minimum 1×, so the pane scrolls horizontally; "Actual size" (96 CSS px/in) shows it whole.
71. **"Print test label" result** appears as a toast with the job's status word ("Sent to printer" /
    "Print failed: …").
72. **Cancelling a queued job** exists in the API (`POST /jobs/{id}/cancel`) but the spec defines no control for
    it, so the UI has none.
73. **Agent development extras** (outside the spec's env table): `AGENT_PRINTER_MODE=simulated|usb` (default
    simulated), `AGENT_OUTPUT_DIR`, `AGENT_CA_BUNDLE` (trust the self-signed certificate), `AGENT_HS_READBACK`
    ([SPIKE], off), `AGENT_SIM_CONTROL_PORT` (127.0.0.1:9181, `POST /status`), `AGENT_LOG_DIR`; CLI
    `labelstudio-agent sim-status <status>` and `zpl2png <file.zpl>`.
74. **Service install.** `agent/packaging/build.ps1` (PyInstaller) and `install-service.ps1` (NSSM) are provided
    but not run here: installing a Windows service is left to you on the printer laptop.

## M6 — History + hardening

75. **`search_parts()` performance — approved schema change.** At 50,000 parts the `schema.sql` function took
    85–700 ms (p95 ≈ 540 ms), missing the 150 ms target, and whole-string similarity missed one-word searches in
    long names ("bearing" found nothing in "Bearing 100008 Description…"). With your approval, **migration 0002**
    replaces the function (same signature, columns and 1.0 / 0.9 / similarity ranking): literals inlined so
    indexes are used, index-ordered top-k per branch (new btree `text_pattern_ops` and GiST trigram indexes),
    and word similarity for part name + description, capped at 0.85 so it never outranks exact/prefix matches.
    `schema.sql` is unchanged (0001 still applies it verbatim); searches now take ~30–70 ms at 50,000 parts.
76. **History filters' "no filter" values.** The date-range select adds "All" (the default) before Today / 7 days /
    30 days / Custom; the "Printed by" select's empty choice is labelled "Printed by".
77. **"Printed by" list for operators.** `GET /users` is admin-only, so `GET /history/people` lists the people who
    have printed (id + display name) for any role.
78. **Label detail endpoints.** Added `GET /labels/{id}` (drawer data: snapshot fields with labels, job timeline,
    reprints, serial) and `GET /labels/{id}/bitmap` (the exact stored PNG) — the drawer needs them.
79. **Reprints.** A reprint of a reprint points at the original (`reprint_of` = the original label), so the
    original's drawer lists every reprint. The optional note is stored in the print request body (print_job has
    no note column). Reprints require an `Idempotency-Key` like prints. The reason dialog's button is "Print".
    The printer-status rules of 14.1 apply; the size check does not (the label's size can't change).
80. **Serial status words.** allocated → "Allocated" (neutral), printed → "Printed", unconfirmed → "Unconfirmed",
    voided → "Voided" (11.1 mapping; "Allocated" isn't listed there).
81. **Void reason message.** `VOID_REASON_SHORT` "Reason must be at least 5 characters."; voiding an already voided
    serial returns `SERIAL_VOIDED`.
82. **Exact serial in History search.** When the typed text is an issued serial, the drawer opens on that
    serial's original print.
83. **Bulk writes use COPY.** Staging a 50,000-row import and committing it write rows with PostgreSQL `COPY`
    (updates via a temp table + one `UPDATE … FROM`) instead of batched INSERTs, which cost ~1.5 ms per row
    through Docker Desktop; the 50,000-row check went from 247 s to 36 s. Row triggers still fire.
84. **Renderer text measurement.** Widths are memoized and the ink box is only measured when the advance width is
    within 0.25 em of the column edge (a test proves no bundled glyph overhangs more); output is byte-identical
    (goldens unchanged) and a 4 × 6 in render went from ~440 ms to ~55 ms.
85. **Plain part list at 50,000 parts.** `GET /parts` without a search computes label freshness through the
    `part_label_freshness` view for the whole table (~0.5 s on this laptop). There's no target for it in
    section 15; if it matters on the production machine, the next step is computing freshness only for the page.
86. **Backups.** A `backup` service in Compose runs `deploy/backup.sh` nightly at `BACKUP_AT` (02:00,
    `BACKUP_TZ` default UTC), writing `backups/label-<stamp>.dump` + `assets-<stamp>.tar.gz`, deleting files
    older than 30 days. `scripts/backup-now.ps1` and `scripts/restore.ps1` were added (not in your script list)
    so A12 can be run; restore was tested: wipe → restore gave identical label rows and bitmap hashes.
87. **Brand refresh (D19 changed at the owner's request, 2026-09-30).** Tokens re-coloured to the Novo Lean
    Solutions logo (green `#487037`, warm grey `#847F72`); deep-green sidebar with the logo on a white tile (the
    logo has white knock-outs); engineering line-art backdrop (`web/public/art/`) on sign-in, setup and the import
    hero; faint dot grid behind content; soft card shadows. Styling only — no behaviour changed.
88. **Pictures in spreadsheet cells become part images (owner's request, 2026-09-30).** XLSX only: Excel "Place
    in Cell" pictures (rich values) and floating pictures anchored at a cell's top-left are read from the package
    XML/media (never executed). A new mapping target "Image (pictures in cells)" (key `image`, now reserved;
    auto-suggested for Image/Picture/Photo headers). During validation each picture is re-encoded to PNG ≤ 1024 px
    and stored as an asset (so review can show thumbnails via the new `GET /assets/{id}`); the part links to it
    only on commit. A different picture is an update ("Excel wins", shown as old → new thumbnails); an empty cell
    keeps the current image; a text value in the image column, or an unreadable picture, makes the row invalid.
    Assets staged by a discarded import stay on disk (content-addressed, small). No schema change. Also added
    "NOVO P/N" / "P/N" as part-number header synonyms.
