# tools/bench/

The bench script for Phase 0's first contact with a LabPro, and its tests.

- [labpro_bench.py](labpro_bench.py) finds the LabPro by its vendor and product
  IDs, sends it Command 7 and no other command, and writes every bulk transfer
  to a trace in [the trace format](../../protocol/traces/FORMAT.md). It never
  resets the unit. Its docstring says what it does and what it refuses.
- [fake_backend.py](fake_backend.py) is a pyusb backend that stands in for a
  LabPro by replaying a trace: a fixture now, and a recording once there is
  one.
- [test_bench.py](test_bench.py) runs the script against the fake. The gate's
  `bench` check runs it.
- [requirements.txt](requirements.txt) pins pyusb by version and hash.

Every value about the LabPro comes from `protocol/labpro-facts.toml`, and each
refusal names the fact it rests on.

## Setting up

The script needs Python 3.11 or later, and pyusb. pyusb goes in an environment
of its own, `.venv/` at the repository's root, which git ignores. The lead made
it on Windows on 2026-11-15, from the repository's root, like this:

    python -m venv --without-pip .venv
    python -m pip --python <.venv's Python, as an absolute path> install --require-hashes --no-deps -r tools/bench/requirements.txt

- **Where the environment's Python is:** `.venv/Scripts/python.exe` on Windows,
  and `.venv/bin/python` elsewhere.
- **The path must be absolute.** A relative path failed on Windows: pip could
  not find the file.
- **Only the pinned bytes install.** pip refuses any other file under that name,
  because the hash is pinned.

The tests need nothing more.

Talking to a LabPro also needs libusb, the library pyusb reaches USB through:

- **macOS:** Homebrew's `libusb`. On Apple Silicon, Homebrew puts it in
  `/opt/homebrew/lib`, and pyusb 1.3.1 looks there by itself (its
  `libloader.py`). Where pyusb finds no libusb, pass the library's path with
  `--libusb`. None of this has been run on a Mac.
- **Linux:** the distribution's libusb-1.0;
- **Windows:** libusb's DLL, and the WinUSB driver bound to the LabPro. That
  changes the machine's drivers, and the plan leaves it to the owner's hand.
  Without the driver, the script refuses, naming it.

## At the bench

    .venv/bin/python tools/bench/labpro_bench.py --out first-contact.trace

- **`--form`** chooses how Command 7 is framed; the docstring lists the four
  forms. Try `s-cr`, the manual's framing, first. If no reply comes, try the
  others, one run and one trace each.
- **`--timeout-ms`** sets how long each transfer waits.
- **`--libusb`** loads libusb from a path, where pyusb cannot find it.

**What it reports.** The script prints what it found and the reply's values,
then where the trace went and its SHA-256.

**Exit status.** It is 0 when the reply was recognised, and 1 when anything was
refused or differed from the manual. Either way, the script writes the
transfers it made.

## Keeping a trace as evidence

The script writes wherever `--out` says, with three exceptions:
- never over an existing file;
- never into `protocol/fixtures/`;
- never into `protocol/traces/` when the device is the fake.

A recording becomes evidence in three deliberate steps:

1. copy it into `protocol/traces/`;
2. add its line to `protocol/traces/SHA256SUMS`, as `<sha256>  <name>.trace`;
3. record the session that made it in the lead's ledger.

The gate then holds it to the format and to its hash.

## Limits

- **The tests show agreement with the fake, not with a LabPro.** The fake is the
  lead's model of a LabPro, built from the facts and a fixture.
- **Nothing here has run against real hardware or a real backend.** The libusb
  version in a trace's `stack` line is read through ctypes, and that read is
  untested until Phase 0.
- **Standard USB requests are not in the trace.** pyusb and libusb read the
  device's descriptors and its active configuration, and the script has pyusb
  set the first configuration when that read fails. A trace holds bulk
  transfers only, so its note says when the script set the configuration.
- **The script reads nothing before it sends Command 7.** A reply left over from
  an earlier session would be read as this one's. The trace would show it.
- **A carriage return inside a reply ends it early.** The script then refuses
  the reply as not one list in braces, and what the LabPro had still to send is
  left unread. The trace keeps what was read.
- **One path is untested:** bulk endpoints on different interfaces, which the
  script refuses but no test builds.
- **One command is sent.** The others, and binary mode, wait until Phase 0 has
  settled how USB frames a command.

Its licence is the one the folder table in [README.md](../../README.md) gives
it.
