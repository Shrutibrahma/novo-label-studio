# Open questions

Gaps or ambiguities found while building v1 from `SPEC.md` + `schema.sql`. For each: the question, what was
chosen, and why. None of these change the database schema or a Decision-log item.

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
