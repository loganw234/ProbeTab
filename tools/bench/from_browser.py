#!/usr/bin/env python3
"""Write a trace from a record the bench page saved.

    python tools/bench/from_browser.py RECORD.json --out PATH

The bench page (app/bench/) saves every transfer it made as JSON, when its user
asks. This writes them to PATH as a trace (protocol/traces/FORMAT.md), with
tools/traces.py, so the trace format keeps one writer:
  - each transfer's milliseconds, counted from the page's first Command 7,
    become whole microseconds; a record whose times decrease is refused;
  - the device's strings are recorded by tools/traces.py's rule, and the serial
    number is masked by it again, whatever the page did;
  - the page's refusals and findings are not part of a trace, so they are read
    and checked, but not written;
  - a record from the page's rehearsal (app/bench/rehearse.html), whose device
    calls itself "ProbeTab rehearsal", is written with a note saying it is a
    rehearsal and not a recording, and never into protocol/traces/.

It refuses a record that is not exactly what the page writes, naming what is
wrong. It never writes over a file, never writes among the fixtures, and writes
bytes, so the trace has LF line endings on every system.

Exit status: 0 when the trace was written, 1 when the record or PATH was
refused, 2 when the command line is wrong.
"""
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
import traces  # noqa: E402

FORMAT = "probetab-browser-record 1"   # as app/src/bench/record.ts's RECORD_FORMAT; a bench test holds the two
FORMS = ("s-cr", "s", "cr", "bare")    # as tools/bench/labpro_bench.py's FORMS; a bench test holds the two
REHEARSAL = "ProbeTab rehearsal"       # as app/test/rehearsal-device.ts's MANUFACTURER; a bench test holds the two
KEYS = ("format", "date", "os", "stack", "firmware", "form", "manufacturer", "product", "serial",
        "refusals", "findings", "transfers")
TRANSFER_KEYS = ("direction", "ms", "bytes")
HEX = re.compile(r"(?:[0-9a-f]{2}(?: [0-9a-f]{2})*)?")


class Refused(ValueError):
    """A record, or a place to write, that this converter will not take, named."""


def unique_keys(pairs):
    found = {}
    for key, value in pairs:
        if key in found:
            raise Refused(f"the key {key!r} appears twice in one object")
        found[key] = value
    return found


def no_constant(name):
    raise Refused(f"{name} is not a number JSON allows")


def load(data):
    """The record in data, the bytes of a JSON file, or Refused."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("the record is not UTF-8 text") from None
    try:
        return json.loads(text, object_pairs_hook=unique_keys, parse_constant=no_constant)
    except Refused:  # unique_keys's and no_constant's own, which are ValueErrors too
        raise
    except json.JSONDecodeError as exc:
        raise Refused(f"the record is not JSON: {exc}") from None
    except RecursionError:
        raise Refused("the record nests deeper than JSON's reader goes") from None
    except ValueError as exc:  # Python's limit on the digits of an integer it reads
        raise Refused(f"the record holds a number too long to read: {exc}") from None


def text_of(record, key):
    value = record[key]
    if not isinstance(value, str):
        raise Refused(f"{key} is {type(value).__name__}, not text")
    return value


def convert(record):
    """(header, transfers) for a trace, from a record as the page writes it, or Refused."""
    if not isinstance(record, dict):
        raise Refused("the record is not a JSON object")
    missing = [key for key in KEYS if key not in record]
    unknown = sorted(set(record) - set(KEYS))
    if missing or unknown:
        raise Refused("the record's keys are not the page's: "
                      + "; ".join(part for part in (missing and f"missing {', '.join(missing)}",
                                                    unknown and f"unknown {', '.join(unknown)}") if part))
    if record["format"] != FORMAT:
        raise Refused(f"format {record['format']!r} is not {FORMAT!r}")
    form = text_of(record, "form")
    if form not in FORMS:
        raise Refused(f"form {form!r} is none of {', '.join(FORMS)}")
    for key in ("refusals", "findings"):
        if not isinstance(record[key], list) or not all(isinstance(item, str) for item in record[key]):
            raise Refused(f"{key} is not a list of text")
    items = record["transfers"]
    if not isinstance(items, list) or not items:
        raise Refused("transfers is not a list holding at least one transfer")
    transfers, last = [], 0
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict) or set(item) != set(TRANSFER_KEYS):
            raise Refused(f"transfer {number} does not hold exactly {', '.join(TRANSFER_KEYS)}")
        direction, ms, data = item["direction"], item["ms"], item["bytes"]
        if direction not in ("OUT", "IN"):
            raise Refused(f"transfer {number}'s direction {direction!r} is neither OUT nor IN")
        try:
            usable = not isinstance(ms, bool) and isinstance(ms, (int, float)) and math.isfinite(ms) and ms >= 0
        except OverflowError:  # an integer too large for a float
            usable = False
        if not usable:
            shown = f"{ms!r}" if not isinstance(ms, int) or abs(ms) < 10 ** 30 else "of more than 30 digits"
            raise Refused(f"transfer {number}'s time {shown} is not a number of milliseconds, 0 or more")
        if ms < last:
            raise Refused(f"transfer {number}'s time {ms} ms comes before the one before it, {last} ms")
        last = ms
        if not isinstance(data, str) or not HEX.fullmatch(data):
            raise Refused(f"transfer {number}'s bytes are not two-digit lower-case hex, one space apart")
        try:
            micros = round(ms * 1000)
        except OverflowError:  # a float time too large to be written in whole microseconds
            raise Refused(f"transfer {number}'s time {ms!r} ms is too large to write in microseconds") from None
        transfers.append((direction, micros, bytes.fromhex(data)))
    serial = traces.device_string(text_of(record, "serial"))
    if serial not in traces.SERIAL_ABSENT:
        serial = traces.mask_serial(serial)
    manufacturer = traces.device_string(text_of(record, "manufacturer"))
    if manufacturer == REHEARSAL:
        note = (f"a rehearsal, not a recording: the bench page against the simulated LabPro of "
                f"app/bench/rehearse.html, written by tools/bench/from_browser.py; commands framed as {form}")
    else:
        note = (f"recorded by the bench page in a browser, and written by tools/bench/from_browser.py; "
                f"commands framed as {form}")
    # The trace format's own writer holds the date, and every header value, to its rules.
    header = {
        "date": text_of(record, "date"), "os": text_of(record, "os"), "stack": text_of(record, "stack"),
        "firmware": text_of(record, "firmware"),
        "note": note,
        "manufacturer": manufacturer,
        "product": traces.device_string(text_of(record, "product")),
        "serial": serial,
    }
    return header, transfers


def check_out(path, root):
    """Where the trace goes, or Refused: never over a file, and never among the fixtures."""
    try:
        out = Path(path).resolve()
        if out.exists():
            raise Refused(f"{path} exists, and this converter never writes over a file")
        if not out.parent.is_dir():
            raise Refused(f"{path}: its folder does not exist")
        fixtures = (Path(root) / "protocol" / "fixtures").resolve()
    except OSError as exc:
        raise Refused(f"{path} cannot be used: {exc.strerror or exc}") from None
    if out.is_relative_to(fixtures):
        raise Refused("what this converter writes is a recording, and protocol/fixtures/ holds fixtures only")
    return out


def check_rehearsal(header, out, root):
    """Refused when a record from the page's rehearsal would be written among the recordings."""
    if header["manufacturer"] != REHEARSAL:
        return
    try:
        recordings = (Path(root) / "protocol" / "traces").resolve()
    except OSError as exc:
        raise Refused(f"protocol/traces/ cannot be found: {exc.strerror or exc}") from None
    if out.is_relative_to(recordings):
        raise Refused("this record is from the bench page's rehearsal, against a simulated LabPro, and "
                      "protocol/traces/ holds recordings of a LabPro only")


def main(argv=None, stdout=None, root=ROOT):
    stdout = stdout or sys.stdout

    def say(line):
        print(line, file=stdout)

    parser = argparse.ArgumentParser(description="Write a trace from a record the bench page saved.")
    parser.add_argument("record", help="the JSON file the bench page saved")
    parser.add_argument("--out", required=True, help="where to write the trace; never over a file")
    args = parser.parse_args(argv)
    try:
        out = check_out(args.out, root)
        try:
            data = Path(args.record).read_bytes()
        except OSError as exc:
            raise Refused(f"the record cannot be read: {exc.strerror or exc}") from None
        header, transfers = convert(load(data))
        check_rehearsal(header, out, root)
        try:
            text = traces.write("trace", header, transfers)
        except ValueError as exc:
            raise Refused(f"the trace format refuses the record's header: {exc}") from None
    except Refused as why:
        say(f"refused: {why}")
        return 1
    written = text.encode("utf-8")
    try:
        with open(out, "xb") as handle:
            handle.write(written)
    except OSError as exc:
        say(f"refused: {args.out} cannot be written: {exc.strerror or exc}")
        return 1
    say(f"wrote {len(transfers)} transfers to {args.out}")
    say(f"its SHA-256 is {hashlib.sha256(written).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
