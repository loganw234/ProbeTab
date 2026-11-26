# ProbeTab

Classroom sensors in a browser tab. ProbeTab aims to bring Vernier's LabPro
sensor interface back into everyday use. It is one web app that collects data
over the LabPro's own USB port, or through a small ESP32-S3 bridge over USB,
Wi-Fi or Bluetooth, with nothing to install and no account.

**Status, 2026-11-26: Phase 0, the first contact with a LabPro, is under way.**
A LabPro was first connected on 2026-11-25, to a Windows computer. The bench
script and the browser bench page both talked to it, and the session's 16
recordings are in [protocol/traces/](protocol/traces/FORMAT.md). 30 of the 81
facts about the LabPro are now marked `bench`, each naming the recording that
shows it. The rest are read from Vernier's manual, and marked unverified until a
LabPro confirms them. [docs/phase0.md](docs/phase0.md) is Phase 0's runbook;
some of its steps, and a session on a Mac, are still to come.

## The authority

When two things in this project disagree about how a LabPro behaves, **the
LabPro on the bench is right**, and its recorded traces are the evidence.
Everything else is a claim to be held against them:

- **Vernier's LabPro Technical Reference Manual** (revision dated 08/02/02) is
  where the protocol work starts, not the last word. Each fact taken from it
  lives in [protocol/labpro-facts.toml](protocol/labpro-facts.toml) with:
  - its page;
  - the words on that page that state it;
  - the status `manual`, until a recorded trace confirms it.
- **The simulated LabPros**, in the app's tests and in the bench script's, are
  written from the same manual. Tests that pass against them show that the code
  agrees with our reading of the manual, not with the device.

## What's here

<!-- folders:start (tools/check.py reads this table: every folder needs a row, every row a folder) -->
| Folder | Contents | Licence |
|---|---|---|
| `app/` | The browser app: transports, protocol, sensors, interface | MIT |
| `firmware/` | Bridge firmware for the ESP32-S3 | MIT |
| `hardware/` | Bridge schematics, board files and enclosure | CERN-OHL-P-2.0 |
| `protocol/` | LabPro facts, the protocol reference and recorded traces | CC-BY-4.0 |
| `sensors/` | Sensor identification and calibration data | CC-BY-4.0 |
| `tools/` | The gate, the generator, the trace format, and the bench tools | MIT |
| `docs/` | Guides for teachers and builders | CC-BY-4.0 |
<!-- folders:end -->

Files outside these folders are MIT.

## Does it hold?

One command, a few seconds:

    python tools/check.py

It prints a line per check and ends with a `VERDICT` line. Read that line and
any `SKIP` lines rather than the exit code. Before a commit, add
`--require-all`, so that a skipped check fails.

`python tools/check.py --control` plants faults for every check, in copies of
the files or in throwaway repositories. It confirms that each fault is caught,
or, for a range with no commits, skipped by name.

The script's docstring lists the checks and what they cannot see.

## Licences

Each folder's licence is the one in the table above, and files outside the
folders are MIT. The table is the one statement of which folder has which
licence.

- The texts and notices are [LICENSE](LICENSE),
  [LICENSE-HARDWARE](LICENSE-HARDWARE) and
  [LICENSE-DOCS-DATA](LICENSE-DOCS-DATA).
- The phrases quoted from Vernier's manual as evidence remain Vernier's.

## Not affiliated with Vernier or Texas Instruments

ProbeTab is an independent project. It is not affiliated with, or endorsed by,
Vernier or Texas Instruments. As the manual's page 1 notes, LabPro belongs to
Vernier Software & Technology as a registered trademark, and CBL 2 to Texas
Instruments as a trademark. The names appear here only to say which hardware
ProbeTab works with.

ProbeTab's code is written from Vernier's published manual and from observing
real hardware. Other LabPro projects are read for understanding, not copied.
