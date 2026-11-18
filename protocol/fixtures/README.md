# protocol/fixtures/

Hand-written traces: the lead's model of what passes between a host and a
LabPro, written from the manual before any LabPro was connected. There are three:

- `status-request.trace`: Command 7 and its reply, as page 46 shows them;
- `ch1-reading.trace`: CH1 read as the bench script's `--read-ch1` does it.
  - the reset, channel 1 by auto-ID, and Command 9 in both modes;
  - Command 7 between each, its replies page 46's first, and Command 9's
    values from page 48's example.
- `bench-rehearsal.trace`: the bench page's rehearsal, in the order the page
  takes its steps.
  - Connect's Command 7, Read CH1 as `ch1-reading.trace` has it, then a live
    reading of 12 readings, with Command 7 after the 10th;
  - every transfer copied from the two fixtures above, so it models what they
    model.

Tests, and the bench page's rehearsal, use them in place of a device:

- [tools/bench/](../../tools/bench/README.md) replays `status-request.trace`
  through a fake pyusb backend;
- [the app's tests](../../app/README.md) replay them through a simulated
  LabPro. They read them as `app/test/generated/fixtures.ts`, which
  `tools/generate.py` makes from this folder. After changing a fixture, run
  `python tools/generate.py`.
- the bench page's rehearsal replays `bench-rehearsal.trace` through the same
  simulated LabPro, in a browser, from the same generated file.

They are not evidence:

- A fact cannot cite one.
- The gate refuses a file marked as a fixture in `protocol/traces/`.
- Each fixture begins `# probetab-fixture 1`, and its `model` line says what it
  models and which manual pages it follows.

The format is described in [../traces/FORMAT.md](../traces/FORMAT.md).
