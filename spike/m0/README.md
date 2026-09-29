# M0 hardware spike

Gate (spec section 17): A1 and A2 pass on one Large label; the `~HS` readback result is recorded in the decision log.

## Setup (on the laptop wired to the ZQ630 Plus)

1. Install the Zebra ZDesigner driver and connect the printer by USB. Note the Windows printer name (Settings → Printers).
2. `pip install -r requirements.txt`
3. Fonts: download Inter from the official release (https://github.com/rsms/inter/releases, SIL OFL) and copy
   `Inter-Regular.ttf`, `Inter-SemiBold.ttf`, `Inter-Bold.ttf`, `Inter-ExtraBold.ttf` (from `extras/ttf/`) into `api/fonts/`.
4. Load 4 × 2 in die-cut direct-thermal synthetic labels, then calibrate:
   `python m0.py calibrate --queue "ZQ630 Plus"`

## Run

| Step | Command | Record |
| --- | --- | --- |
| Dry run (no printer) | `python m0.py render` | `out/label.png`, `out/label.zpl`; round-trip check passes |
| Spooler status | `python m0.py status --queue "ZQ630 Plus"` | raw status + mapped word; repeat with USB unplugged, cover open, no media |
| Print | `python m0.py print --queue "ZQ630 Plus"` | label prints; `write_ms` |
| Readback | `python m0.py hs` | three `~HS` frames, or the error |
| Confirmed print | `python m0.py print --queue "ZQ630 Plus" --confirm` | `confirm.confirmed`, `seen_busy`, timeline |
| Part-mode QR | `python m0.py print --queue "ZQ630 Plus" --qr part` | A2 for `PN:` |

Every printer command appends to `out/m0_results.jsonl`.

## Checks

- **A1 (preview = print):** scan the printed label at 600 dpi. Scale the scan to 203 dpi, overlay it on `out/label.png`, and check that no element is off by more than 2 dots. If the whole image is shifted, measure the shift and retest with `--offset-x/--offset-y`.
- **A2 (QR scans):** use a phone camera to read `SN:NOVO-00000001|PN:NP-10421` (default) and `PN:NP-10421` (`--qr part`).
- **`~HS` readback:** the spooler is write-only, so `hs` opens the USB printer device (`usbprint`, Zebra VID `0A5F`) directly. Possible outcomes for the decision log:
  - frames returned, and `--confirm` goes busy → idle: the agent can post `confirmed`.
  - frames returned, but `--confirm` never sees busy: the label prints faster than we can poll. `confirmed` is only "printer idle with no errors". Decide whether that's enough.
  - open or read fails: D17 stands, and jobs stay "Sent to printer".

## Known limits (spike only)

- Wrapping (7.5 step 2) isn't implemented. A line that's too wide reports `TEXT_TOO_LONG`.
- Layout is fixed: part number (main line), part name (second line), serial (detail), QR on the right.
