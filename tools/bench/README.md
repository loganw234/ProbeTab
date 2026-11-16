# tools/bench/

The bench script for Phase 0 with a LabPro, and its tests.

- [labpro_bench.py](labpro_bench.py) finds the LabPro by its vendor and product
  IDs, and writes every bulk transfer to a trace in
  [the trace format](../../protocol/traces/FORMAT.md).
  - **By default** it sends Command 7 and no other command, and never resets
    the unit.
  - **Asked to,** it also records the device's descriptors, reads a voltage on
    CH1, and takes a live reading.
  - Its docstring says what it does and what it refuses.
- [fake_backend.py](fake_backend.py) is a pyusb backend that stands in for a
  LabPro by replaying a trace: a fixture now, and a recording once there is
  one. It also answers requests for the device's descriptors.
- [test_bench.py](test_bench.py) and [test_ch1.py](test_ch1.py) run the script
  against the fake. The gate's `bench` check runs them.
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
- **Linux:** the distribution's libusb-1.0.
- **Windows:** libusb's DLL, and the WinUSB driver bound to the LabPro. That
  changes the machine's drivers, and the plan leaves it to the owner's hand.
  Without the driver, the script refuses, naming it.

## At the bench

    .venv/bin/python tools/bench/labpro_bench.py --out first-contact.trace --descriptors

That run records the descriptors and Command 7's reply, and changes nothing the
unit holds. pyusb may set the unit's configuration, as the limits below say.
Then, to read CH1:

    .venv/bin/python tools/bench/labpro_bench.py --out ch1.trace --read-ch1

**The steps of `--read-ch1`**, after Command 7:
1. **The guard.** The system state is decoded as page 45 gives it.
   - A unit that is initializing or self-testing is read again, up to five
     times, a second apart.
   - The reset goes only to a unit that is idle or done.
   - A unit holding data not yet retrieved is refused unless `--discard` is
     given, and then that data is lost.
   - An armed or busy unit is never reset, `--discard` or not.
2. **The reset** (Command 0), and a brief listen for anything after it.
3. **Command 7,** which must show idle.
4. **Channel 1 by auto-ID** (Command 1), and a brief listen.
5. **Command 7,** whose error register must be 0.
6. **One reading:** Command 9 in mode 0, the present setup, then Command 7.
7. **The experiment:** Command 9 in mode 1, the stored setup, once, then
   Command 7.

**A live reading.** Add `--every SECONDS` and either `--readings N` or
`--for SECONDS`, for the battery drain: Command 9 in mode 0 at that interval,
with Command 7 checked every tenth reading.
- **The ranges.** `--every` must be from 0 to 86,400 seconds (a day), `--for`
  above 0, and `--readings` 1 or more. Each is checked before anything is
  sent.
- **Ctrl-C** stops the run, and the trace keeps the transfers made so far.

**The options:**
- **`--form`** chooses how every command is framed; the docstring lists the
  four forms. Try `s-cr`, the manual's framing, first. Every later run uses the
  framing that worked.
- **`--timeout-ms`** sets how long each transfer waits.
- **`--libusb`** loads libusb from a path, where pyusb cannot find it.
- **`--descriptors`** records the device and configuration descriptors, and
  the device's strings, in the trace's header. The serial number keeps only its
  first 3 and last 2 characters: model information only, by the owner's ruling
  of 2026-11-16.

**What it reports.** The script prints what it found, each reply's values, and
CH1's readings, then where the trace went and its SHA-256.

**Exit status.** It is 0 when every reply was recognised. It is 1 when
anything was refused or differed from the manual, or when the run was stopped,
by Ctrl-C or by an error the script does not name. Such an error then goes on
with its traceback. In each case the script writes the transfers it made. When
it made none, as when it stops before the first Command 7, there is no trace
to write.

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
  lead's model of a LabPro, built from the facts and the fixtures.
- **Nothing here has run against real hardware or a real backend.** The libusb
  version in a trace's `stack` line is read through ctypes, and that read is
  untested until Phase 0.
- **Standard USB requests are not in the trace.** pyusb and libusb read the
  device's descriptors and its active configuration, and the script has pyusb
  set the first configuration when that read fails. A trace holds bulk
  transfers only. Its note says when the script set the configuration, and its
  header holds the descriptors when `--descriptors` asks for them.
- **The descriptors are as the host's USB stack gives them.** libusb may
  answer from its cache (BELIEVED).
- **What CH1's value means is for the bench to show:** a reading in the
  sensor's units, or a raw voltage. Known voltages from a bench supply show it.
- **The script reads nothing before its first Command 7.** A reply left over
  from an earlier session would be read as this one's. The trace would show
  it.
- **A late reply is not drained.** A reply that comes after a read that drew
  none would be taken by the next read. The trace would show it.
- **The guard reads the state, then resets.** A unit whose state changes
  between the two is not caught.
- **`--for` can run one interval past its time,** because the script waits
  after each reading, the last included.
- **A Ctrl-C while the trace is being written** may leave it partial or empty.
  A Ctrl-C while the descriptors are read is untested.
- **How much a serial shows.** A serial of 6 or 7 characters shows most of
  itself, by the owner's rule of 3 and 2 kept. The manufacturer and product
  strings are recorded whole.
- **A carriage return inside a reply ends it early.** The script then refuses
  the reply as not one list in braces, and what the LabPro had still to send
  is left unread. The trace keeps what was read.
- **One path is untested:** bulk endpoints on different interfaces, which the
  script refuses but no test builds.
- **On a case-insensitive volume, as macOS's usually is,** an `--out` path that
  spells `protocol/fixtures` in other letters may get past the guard against
  writing among the fixtures (BELIEVED, not run).
- **Collection with Command 3 and `g` waits for Phase 1.**

Its licence is the one the folder table in [README.md](../../README.md) gives
it.
