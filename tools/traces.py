"""Read, write and check ProbeTab traces.

This module is the trace format's definition. protocol/traces/FORMAT.md
describes it, and tools/check.py holds every trace and fixture to it.

    python tools/traces.py FILE...   check each file and say what it holds
"""
import datetime
import re
import sys
from dataclasses import dataclass

KINDS = {"# probetab-trace 1": "trace", "# probetab-fixture 1": "fixture"}
HEADER_KEYS = {
    "trace": {"required": ("date", "os", "stack", "firmware"), "optional": ("note",)},
    "fixture": {"required": ("date", "model"), "optional": ("note",)},
}
HEADER = re.compile(r"# ([a-z]+): (\S.*)")
TRANSFER = re.compile(r"(OUT|IN) (0|[1-9][0-9]*)((?: [^ ]+)*)")
BYTE = re.compile(r"[0-9a-f]{2}")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?[+-][0-9]{2}:[0-9]{2}")


class TraceError(ValueError):
    """A file that does not hold to the format, with the line where it stops holding."""

    def __init__(self, line, message):
        super().__init__(f"line {line}: {message}")
        self.line = line


@dataclass
class Trace:
    kind: str           # "trace" for a recording, "fixture" for a hand-written model
    header: dict
    transfers: list     # (direction, microseconds, bytes)


def parse(text):
    """The trace in text, or TraceError naming the first line that breaks the format."""
    if "\r" in text:
        raise TraceError(text[:text.index("\r")].count("\n") + 1,
                         "a carriage return; traces use LF line endings")
    if not text.endswith("\n"):
        raise TraceError(text.count("\n") + 1, "the file does not end with a newline")
    lines = text[:-1].split("\n")
    kind = KINDS.get(lines[0])
    if kind is None:
        raise TraceError(1, f"the first line must be one of {', '.join(sorted(KINDS))}")
    keys = HEADER_KEYS[kind]
    allowed = keys["required"] + keys["optional"]
    header, where = {}, {}
    index = 1
    while index < len(lines) and lines[index].startswith("#"):
        match = HEADER.fullmatch(lines[index])
        if not match:
            raise TraceError(index + 1, "a header line reads '# key: value'")
        key, value = match.groups()
        if not value.isprintable():
            raise TraceError(index + 1, f"the value of {key!r} holds a character that is not printable text")
        if key not in allowed:
            raise TraceError(index + 1, f"unknown header key {key!r}; a {kind} allows {', '.join(allowed)}")
        if key in header:
            raise TraceError(index + 1, f"header key {key!r} appears twice")
        header[key], where[key] = value, index + 1
        index += 1
    missing = [key for key in keys["required"] if key not in header]
    if missing:
        raise TraceError(index + 1, f"the header lacks {', '.join(missing)}")
    if not DATE.fullmatch(header["date"]):
        raise TraceError(where["date"], f"date {header['date']!r} does not read YYYY-MM-DDTHH:MM:SS+HH:MM")
    try:
        datetime.datetime.fromisoformat(header["date"])
    except ValueError:
        raise TraceError(where["date"], f"date {header['date']!r} is not a real date and time") from None
    transfers, last = [], 0
    for index in range(index, len(lines)):
        match = TRANSFER.fullmatch(lines[index])
        if not match:
            raise TraceError(index + 1, "a transfer line reads 'OUT' or 'IN', the microseconds, then the bytes")
        direction, micros, rest = match.group(1), int(match.group(2)), match.group(3).split()
        bad = [token for token in rest if not BYTE.fullmatch(token)]
        if bad:
            raise TraceError(index + 1, f"{bad[0]!r} is not a byte; a byte is two lower-case hex digits")
        if micros < last:
            raise TraceError(index + 1, f"time {micros} comes before the previous line's {last}")
        last = micros
        transfers.append((direction, micros, bytes(int(token, 16) for token in rest)))
    if not transfers:
        raise TraceError(len(lines) + 1, f"a {kind} holds at least one transfer")
    return Trace(kind, header, transfers)


def write(kind, header, transfers):
    """The text of a trace.

    Refuses a header value that is not text, and any text that would not read
    back exactly as given, so parse(write(...)) returns what was written. A
    header value holding a line break is one thing that would not.
    """
    magic = {value: key for key, value in KINDS.items()}[kind]
    keys = HEADER_KEYS[kind]
    allowed = keys["required"] + keys["optional"]
    unknown = sorted(set(header) - set(allowed))
    if unknown:
        raise ValueError(f"refused: header keys {', '.join(unknown)} are not in a {kind}")
    for key, value in header.items():
        if not isinstance(value, str):
            raise ValueError(f"refused: header {key!r} is of type {type(value).__name__}; header values are text")
    lines = [magic] + [f"# {key}: {header[key]}" for key in allowed if key in header]
    for direction, micros, data in transfers:
        lines.append(" ".join([direction, str(micros)] + [f"{byte:02x}" for byte in data]))
    text = "\n".join(lines) + "\n"
    trace = parse(text)
    given = [(direction, micros, bytes(data)) for direction, micros, data in transfers]
    if trace.kind != kind or trace.header != dict(header) or trace.transfers != given:
        raise ValueError("refused: the text would not read back as given; "
                         "a header value holding a line break is one way")
    return text


def main(paths):
    failed = False
    for path in paths:
        try:
            with open(path, "rb") as handle:
                trace = parse(handle.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, TraceError) as exc:
            print(f"{path}: {exc}")
            failed = True
            continue
        count = len(trace.transfers)
        outs = sum(1 for direction, _, _ in trace.transfers if direction == "OUT")
        print(f"{path}: a {trace.kind}, {count} transfer{'' if count == 1 else 's'} "
              f"({outs} OUT, {count - outs} IN)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if sys.argv[1:] else __doc__)
