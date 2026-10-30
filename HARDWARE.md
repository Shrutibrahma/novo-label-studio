# Hardware validation (v1.1 milestone H)

Results of the checks in README "Hardware checks still to run", in that order, once the ZQ630 Plus arrives.
Photos and scans go in `hardware-results/`. Rules (SPEC v1.1 section 3, H): an A1 offset is fixed with the
printer's X/Y offset settings, not in renderer code; any other A1 failure (scaling, dithering, clipped edges) is
raised as an open question before the renderer changes. A1 and A2 are repeated on one label of every preset at
its preset size.

| Check | Result | Date | Notes / evidence |
| --- | --- | --- | --- |
| M0 spike | not run — printer not here yet | | |
| A1 Preview = print | not run | | |
| A2 QR scans | not run | | |
| A5 Box set | not run | | |
| A9 Printer errors | not run | | |
| A11 Offsets | not run | | |
| ~HS readback (D17) | not run | | |
| Media (30-day rack test) | not run | | |
| A1 + A2, preset Part label (Large) | not run | | |
| A1 + A2, preset Bin label (Large) | not run | | |
| A1 + A2, preset Kanban card (Tall) | not run | | |
| A1 + A2, preset Rack location (Large) | not run | | |
| A1 + A2, preset Quality tag (Tall) | not run | | |
| A1 + A2, preset Box label (Tall) | not run | | |
| A1 + A2, preset Workstation sign (Large) | not run | | |
| Agent as a Windows service (v1.1 U5): install with `install-service.ps1`, reboot, sidebar shows the agent online within 60 s without anyone signing in | not run | | |
