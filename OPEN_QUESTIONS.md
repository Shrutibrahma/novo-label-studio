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
