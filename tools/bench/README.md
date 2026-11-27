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
  LabPro by replaying a trace: a fixture, or a recording from
  [protocol/traces/](../../protocol/traces/FORMAT.md). The tests replay
  fixtures. It also answers requests for the device's descriptors.
  - **When a test asks,** it also models one fault: Command 1 for a channel
    that page 31's list does not hold sets the error register, and the fake
    keeps it until Command 0. It reads that list from the facts'
    `channel.numbers_*` rows. That is the fake's own model. The real unit, on
    2026-11-25, drew error 12 for such a channel, where the fake sets 1
    ([ch1-volt-opfirst](../../protocol/traces/2026-11-25-ch1-volt-opfirst.trace)),
    and read 0 again at the next run, before that run's reset
    ([ch1-0v](../../protocol/traces/2026-11-25-ch1-0v.trace)), for a cause not
    settled. The model is off unless a test asks, so a replayed recording is
    never rewritten.
- [test_bench.py](test_bench.py) and [test_ch1.py](test_ch1.py) run the script
  against the fake. The gate's `bench` check runs them.
- **The browser bench page's Python side:**
  - [serve.py](serve.py) serves the page to this computer alone.
  - [from_browser.py](from_browser.py) writes a trace from the record the page
    saves.
  - [test_browser.py](test_browser.py) tests both. It also holds the page's
    copies of the script's constants to the script's own.
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
  `--libusb`. On 2026-11-19, by the owner's reports, the bench script on the
  owner's MacBook found libusb by itself, with no `--libusb`: before the LabPro
  had arrived, it refused "no LabPro found". An earlier try there refused for
  want of a USB backend, for a cause not reported.
- **Linux:** the distribution's libusb-1.0.
- **Windows:** libusb's DLL, and the WinUSB driver bound to the LabPro. That
  changes the machine's drivers, and the plan leaves it to the owner's hand.
  With no driver at all, libusb does not list the LabPro, and the script
  refuses "no LabPro found" (seen on 2026-11-25). With another driver bound,
  the refusal names WinUSB (BELIEVED, untried).

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
4. **Channel 1** (Command 1), by auto-ID with the channel first unless
   `--operation` and `--order` say otherwise, and a brief listen.
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
- **`--operation auto-id|voltage`** chooses Command 1's operation, from the
  facts file: `auto-id` (the default) or `voltage`, the 0 to 5 V operation.
- **`--order channel-first|operation-first`** chooses the order of Command 1's
  two parameters. Channel first is the default, as page 31 writes it. With
  auto-ID the two orders send the same bytes, since the facts give the channel
  and auto-ID the same number; so the order shows only with `--operation
  voltage`. On 2026-11-25 the unit took the channel first
  ([protocol/REFERENCE.md](../../protocol/REFERENCE.md), question 5).
- **`--applied VOLTS` and `--meter VOLTS`** record the voltage set on the supply,
  and a meter's reading if there is one, in the trace's `note`, after the text
  the script writes there, exactly as typed. Each is an optional minus sign,
  digits, and optionally a point and more digits, at most 12 characters: `1.25`
  and `-0.5` pass, and `1e3`, `.5` and `1,5` do not. They are the operator's
  record, not the LabPro's. For a negative number, write it with an equals sign,
  as `--applied=-0.5`.
- **The four options above go only with `--read-ch1`,** and are refused
  without it. A number that does not fit is refused before any device is opened.
- **The state line.** After its first Command 7, every run prints one line,
  such as `state: idle; QuickSetup flag clear; unretrieved-data flag clear`
  (page 45). The runbook's steps 2 and 6 go on only by it. Without `--read-ch1`,
  a system state no fact gives is printed as such and the run goes on; with it,
  the guard refuses that state as before.

**What it reports.** The script prints what it found, each reply's values, and
CH1's readings, then where the trace went and its SHA-256.

**Exit status.** It is 0 when every reply was recognised. It is 1 when
anything was refused or differed from the manual, or when the run was stopped,
by Ctrl-C or by an error the script does not name. Such an error then goes on
with its traceback. In each case the script writes the transfers it made. When
it made none, as when it stops before the first Command 7, there is no trace
to write.

## From the browser

The bench page takes the same steps in Chrome or Edge, over WebUSB.
[app/README.md](../../app/README.md) says how to build it and use it.

- **`serve.py`** serves `app/bench/`, `app/collect/` and `app/web/`, and
  nothing else.
  - It binds to 127.0.0.1, so no other computer can reach it.
  - `--port` chooses the port, 8000 by default.
  - Each file's type comes from the script's own table, so `.js` is served as
    JavaScript whatever the system's registry says.
- **`from_browser.py`** writes a trace from the page's saved record:

      python tools/bench/from_browser.py RECORD.json --out browser.trace

  - It uses `tools/traces.py`, so the trace format keeps one writer.
  - Each time in milliseconds becomes whole microseconds. A record whose times
    decrease is refused.
  - It records the device's strings by the trace format's rule, and masks the
    serial number again, whatever the page did.
  - It refuses a record that is not exactly what the page writes, and names what
    is wrong.
  - It never writes over a file, or among the fixtures.
  - The page's refusals and findings are checked, but are not part of a trace,
    so they are not written.
  - A record from the page's rehearsal, whose device calls itself "ProbeTab
    rehearsal", gets a note saying it is a rehearsal and not a recording, and
    is never written into `protocol/traces/`.
  - Both refusals compare resolved paths, in the same way.
    - On Windows, a path into `protocol/traces/` spelled in another case
      resolved to that folder, and was refused (MEASURED by a verifier,
      2026-11-18).
    - On a Mac, whose disks ignore case by default, a path spelled in another
      case is BELIEVED to get past either refusal. That is not tested.
- **A browser trace has no `device` or `configuration` line.** The page records
  the strings WebUSB gives it, not the raw descriptors. The bench script records
  both, when given `--descriptors`.
- **The `os`, `stack` and `firmware` lines are the record's text,** held only to
  the trace format's rules. A record the page did not make could carry anything
  printable there. The gate's privacy check covers a trace once it is in the
  repository.

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
- **It has run against real hardware in one session:** a LabPro, on Windows 11
  through libusb 1.0.30, on 2026-11-25. The libusb version in a trace's `stack` line
  is read through ctypes; it gave 1.0.30 there, and is untried on other hosts.
- **Standard USB requests are not in the trace.** pyusb and libusb read the
  device's descriptors and its active configuration, and the script has pyusb
  set the first configuration when that read fails. A trace holds bulk
  transfers only. Its note says when the script set the configuration, and its
  header holds the descriptors when `--descriptors` asks for them.
- **The descriptors are as the host's USB stack gives them.** libusb may
  answer from its cache (BELIEVED).
- **What CH1's value means is not settled:** a reading in the sensor's units,
  or a raw voltage. On 2026-11-25, CH1 read near the nominal voltages of the
  cells the owner put on it, with a probe the owner believes reads volts. A
  sensor that reads in other units, and a
  metered source, are still needed
  ([protocol/REFERENCE.md](../../protocol/REFERENCE.md), question 4).
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
- **The page's server rests on two beliefs:**
  - Chromium counts `127.0.0.1` as a secure origin, which WebUSB needs. It was
    seen once: on 2026-11-25, Chrome 158 on Windows used WebUSB from the page
    served there, by the lead's record of `serve.py`'s log;
  - Windows' registry can make `.js` plain text, which is why the script keeps
    its own table. That one is unchecked.
- **The converter's refusals of a path the system will not use** are tested
  with stand-ins, not with real paths. One example is `::$DATA` in a folder's
  name, which Windows refuses and other systems take as plain text.

Its licence is the one the folder table in [README.md](../../README.md) gives
it.
