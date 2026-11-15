# protocol/fixtures/

Hand-written traces: the lead's model of what passes between a host and a
LabPro, written from the manual before any LabPro was connected. The bench
script's tests use them in place of a device:
[tools/bench/](../../tools/bench/README.md) replays `status-request.trace`
through a fake pyusb backend.

They are not evidence:

- A fact cannot cite one.
- The gate refuses a file marked as a fixture in `protocol/traces/`.
- Each fixture begins `# probetab-fixture 1`, and its `model` line says what it
  models and which manual pages it follows.

The format is described in [../traces/FORMAT.md](../traces/FORMAT.md).
