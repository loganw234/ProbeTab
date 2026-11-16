# The trace format

A trace records what passed between a host and a LabPro in one bench session,
one USB transfer to a line. Recorded traces are this project's evidence about
the LabPro; [the README](../../README.md) says why. This folder holds them, and
`SHA256SUMS` beside them pins each one's bytes.

[`tools/traces.py`](../../tools/traces.py) is the format's definition: it reads,
writes and checks traces, and `python tools/check.py` holds every trace to it.
This page describes the format. Where the two disagree, the code is right and
this page is a defect.

## An example

```trace
# probetab-trace 1
# date: 2026-11-20T14:03:11-07:00
# os: macOS 15.1
# stack: python 3.12.7, pyusb 1.3.1, libusb 1.0.27
# firmware: unknown
OUT 0 73 7b 37 7d 0d
IN 1532 7b 20 31 2e 30 7d 0d
```

The gate parses this example as a recording, so it cannot drift from the code.
Its bytes are made up for the example; they are not a recording.

## The rules

- UTF-8 text with LF line endings, ending with a newline.
- The first line names the kind and the version: `# probetab-trace 1` for a
  recording, `# probetab-fixture 1` for a hand-written fixture.
- Then the header, one `# key: value` line each, in any order:
  - a recording has `date`, `os`, `stack` and `firmware`, once each;
  - a fixture has `date`, and `model`: what it models and which manual pages it
    follows;
  - either may add one `note`;
  - either may add what the device says of itself, each line at most once:
    - `device` and `configuration`: the device descriptor and the configuration
      descriptor, in the same hex as a transfer's bytes. A `device` line is 18
      bytes, beginning `12 01`. A `configuration` line begins `09 02`, and is as
      long as its own total-length field, in its third and fourth bytes, says.
    - `manufacturer` and `product`: the device's strings, as text.
    - `serial`, masked. Only its first 3 and last 2 characters show, and every
      other character is `*`. A serial of 5 characters or fewer is masked
      whole. It reads `none` when the device has no serial, and `unreadable`
      when it could not be read. The counts are the owner's ruling (2026-11-16):
      model information only. `tools/traces.py` holds them, and a trace already
      written keeps the mask it was written with.
  - any other key is refused. No key holds a hostname, a user name or a path,
    and the gate's privacy check reads the values like any other text.
- Keys are lower-case letters. A value is printable text that begins with a
  non-space character, so it holds no tab, control character or line
  separator.
- `date` reads `YYYY-MM-DDTHH:MM:SS+HH:MM` (or `-HH:MM`), optionally with
  fractional seconds, in ASCII digits, and must be a real date and time.
- `firmware` is the version the LabPro reports, or `unknown` before it has
  reported one.
- Then one line for each transfer:
  - `OUT` (host to LabPro) or `IN` (LabPro to host);
  - the microseconds since the session began, in decimal with no leading zero,
    never decreasing (two transfers may share a time);
  - the bytes as two-digit lower-case hex, one space apart. A transfer may
    carry no bytes.
- A trace holds at least one transfer.
- `tools/traces.py` also writes traces. It refuses to write anything that would
  not read back exactly as given.
- **Two rules the gate cannot check:**
  - that `date` was taken from the clock when the session was recorded;
  - that `firmware` is what the LabPro reported.

## Recordings and fixtures

- **Recordings** live here. Each is listed in `SHA256SUMS` as
  `<sha256>  <name>.trace`.
- **Fixtures** live in [protocol/fixtures/](../fixtures/README.md) and are never
  listed here. They are the lead's model of the device, written by hand, and
  they are not evidence.
- **A fact becomes `bench`** only by naming a recording listed here with its
  hash.
- **Limit.** The gate cannot tell a recording from a fixture copied here with a
  recording's header. Which traces were recorded is kept in the lead's ledger,
  with the session that made each.
