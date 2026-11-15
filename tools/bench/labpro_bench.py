#!/usr/bin/env python3
"""First contact with a LabPro: find it, ask its status, record every transfer.

    python tools/bench/labpro_bench.py --out PATH [--form FORM] [--timeout-ms N] [--libusb LIB]

It finds the one USB device with the LabPro's vendor and product IDs. Over its
bulk endpoints it sends Command 7, the status request, and no other command.
It never resets the unit, which may still hold an earlier experiment's data.
It reads the reply one packet at a time until the byte that ends a reply, then
writes every bulk transfer to PATH as a trace (protocol/traces/FORMAT.md).

pyusb and libusb also make standard USB requests of the device on the
script's behalf: they read its descriptors and which configuration is active,
and when that read fails, the script has pyusb set the first configuration.
These are not LabPro commands, and a trace holds bulk transfers only, so its
note says when the script set the configuration.

LIB is a libusb library to load by its path, for a host where pyusb finds none
by itself. pyusb 1.3.1 already looks in /opt/homebrew/lib on Apple Silicon.

Every value about the LabPro comes from protocol/labpro-facts.toml, read
through tools/labpro_facts.py, and each refusal names the fact it rests on.
Whatever the script does not recognise, it refuses by name. It still writes
the transfers it made, because what the LabPro did is the evidence.

FORM is how Command 7 is framed. The manual writes s{7} for a computer host,
and a carriage return after each command on the serial port. Whether USB
wants either is the first thing the bench has to settle:

    s-cr   s{7} and the carriage return (the default)
    s      s{7} alone
    cr     {7} and the carriage return
    bare   {7} alone

Exit status: 0 when the reply was recognised, 1 when anything was refused or
differed from the manual, 2 when the command line is wrong.
tools/bench/README.md says how to set it up and run it.
"""
import argparse
import datetime
import hashlib
import platform
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
import labpro_facts  # noqa: E402
import traces  # noqa: E402

try:
    import usb.backend.libusb1
    import usb.core
    import usb.util
except ImportError:  # named when the script runs; see main()
    usb = None

FORMS = ("s-cr", "s", "cr", "bare")
TIMEOUT_MS = 2000   # how long one read waits for a packet; the manual gives no figure
MAX_PACKETS = 64    # a reply that takes more packets than this is refused


class Refused(Exception):
    """Something the script does not recognise, said in words."""


class Facts:
    """The facts file's facts by name: facts[name] is a value, cite(name) says where it is from."""

    def __init__(self, root=ROOT):
        self.tables = dict(labpro_facts.facts(labpro_facts.load(root)))

    def __getitem__(self, name):
        return self.tables[name]["value"]

    def cite(self, name):
        return f"{name}, page {self.tables[name]['page']}"


def command(facts, number, form):
    """The bytes of a command that takes no parameters, framed as form says."""
    text = facts["command.open"] + str(number) + facts["command.close"]
    if form in ("s-cr", "s"):
        text = facts["command.prefix"] + text
    if form in ("s-cr", "cr"):
        text += facts["command.serial_terminator"]
    return text.encode("ascii")


def number_form(template):
    """A pattern for numbers written as template says, as sm.dddddEsee on page 21:
    s is a sign, m, d and e are digits, and any other character is itself."""
    parts = {"s": "[+-]", "m": "[0-9]", "d": "[0-9]", "e": "[0-9]"}
    return re.compile("".join(parts.get(ch, re.escape(ch)) for ch in template))


def registers(reply, facts):
    """The values of a Command 7 reply, each as the text the LabPro sent, or Refused."""
    end = reply.find(facts["reply.terminator"].encode("ascii"))
    body = reply[:end] if end >= 0 else reply
    try:
        text = body.decode("ascii").strip()
    except UnicodeDecodeError:
        raise Refused(f"the reply holds bytes that are not ASCII text: {body.hex(' ')}") from None
    opening, closing = facts["command.open"], facts["command.close"]
    if not (text.startswith(opening) and text.endswith(closing)):
        raise Refused(f"the reply {text!r} is not one list in {opening} and {closing} "
                      f"({facts.cite('command.separator')})")
    values = [value.strip() for value in text[len(opening):-len(closing)].split(facts["command.separator"])]
    count = facts["status.register_count"]
    if len(values) != count:
        raise Refused(f"the reply holds {len(values)} values, not {count} ({facts.cite('status.register_count')})")
    form = facts["data.ascii_number_format"]
    pattern = number_form(form)
    for place, value in enumerate(values, start=1):
        if not pattern.fullmatch(value):
            raise Refused(f"value {place} of the reply, {value!r}, is not written {form} "
                          f"({facts.cite('data.ascii_number_format')})")
    place, check = facts["status.check_value_position"], facts["status.check_value"]
    if float(values[place - 1]) != check:
        raise Refused(f"value {place} of the reply is {values[place - 1]}, not {check} "
                      f"({facts.cite('status.check_value')}; {facts.cite('status.check_value_position')})")
    return values


def find_labpro(facts, backend):
    vendor, product = facts["usb.vendor_id"], facts["usb.product_id"]
    try:
        found = list(usb.core.find(find_all=True, idVendor=vendor, idProduct=product, backend=backend))
    except usb.core.NoBackendError:
        raise Refused("pyusb found no USB backend; install libusb, as tools/bench/README.md says") from None
    if not found:
        raise Refused(f"no LabPro found: no USB device has vendor {vendor:#06x} and product {product:#06x} "
                      f"({facts.cite('usb.vendor_id')}; {facts.cite('usb.product_id')})")
    if len(found) > 1:
        raise Refused(f"{len(found)} devices have the LabPro's vendor and product IDs; connect only one")
    return found[0]


def bulk_pair(device, facts):
    """(interface, IN endpoint, OUT endpoint, whether the script set the configuration),
    as the manual describes them, or Refused."""
    configured_here = False
    try:
        configuration = device.get_active_configuration()
    except usb.core.USBError:
        device.set_configuration()
        configured_here = True
        configuration = device.get_active_configuration()
    found = {"IN": [], "OUT": []}
    for interface in configuration:
        if interface.bAlternateSetting != 0:
            continue
        for endpoint in interface:
            if usb.util.endpoint_type(endpoint.bmAttributes) != usb.util.ENDPOINT_TYPE_BULK:
                continue
            way = "IN" if usb.util.endpoint_direction(endpoint.bEndpointAddress) == usb.util.ENDPOINT_IN else "OUT"
            found[way].append((interface, endpoint))
    seen = ", ".join(f"{way} {endpoint.bEndpointAddress:#04x} on interface {interface.bInterfaceNumber}"
                     for way in found for interface, endpoint in found[way]) or "none"
    for way, fact in (("IN", "usb.bulk_in_endpoints"), ("OUT", "usb.bulk_out_endpoints")):
        if len(found[way]) != facts[fact]:
            raise Refused(f"the device has {len(found[way])} bulk {way} endpoints, not {facts[fact]} "
                          f"({facts.cite(fact)}); bulk endpoints seen: {seen}")
    (interface, inward), (other, outward) = found["IN"][0], found["OUT"][0]
    if interface.bInterfaceNumber != other.bInterfaceNumber:
        raise Refused(f"the bulk endpoints sit on different interfaces: {seen}")
    for endpoint in (inward, outward):
        if endpoint.wMaxPacketSize != facts["usb.packet_size"]:
            raise Refused(f"endpoint {endpoint.bEndpointAddress:#04x} takes packets of {endpoint.wMaxPacketSize} "
                          f"bytes, not {facts['usb.packet_size']} ({facts.cite('usb.packet_size')})")
    return interface, inward, outward, configured_here


def read_reply(device, inward, facts, timeout_ms, record, findings):
    """The reply's packets joined, up to the one holding the end of the reply, or Refused."""
    size, multiple = facts["usb.packet_size"], facts["usb.in_transfer_multiple"]
    terminator = facts["reply.terminator"].encode("ascii")
    reply = b""
    for _ in range(MAX_PACKETS):
        try:
            packet = bytes(device.read(inward.bEndpointAddress, size, timeout_ms))
        except usb.core.USBTimeoutError:
            if not reply:
                raise Refused(f"no reply came within {timeout_ms} ms of Command 7") from None
            raise Refused(f"the reply stopped after {len(reply)} bytes without its end "
                          f"({facts.cite('reply.terminator')})") from None
        record("IN", packet)
        if len(packet) % multiple:
            findings.append(f"a packet of {len(packet)} bytes, where transfers to the host come in multiples "
                            f"of {multiple} ({facts.cite('usb.in_transfer_multiple')})")
        reply += packet
        if terminator in reply:
            return reply
    raise Refused(f"no end of reply in {MAX_PACKETS} packets ({facts.cite('reply.terminator')})")


def libusb_of(backend):
    """The backend's name, with libusb's version where it can be read."""
    module = type(backend).__module__
    if not module.endswith("libusb1"):
        return module.rsplit(".", 1)[-1]
    try:
        import ctypes

        class Version(ctypes.Structure):
            _fields_ = [("major", ctypes.c_uint16), ("minor", ctypes.c_uint16), ("micro", ctypes.c_uint16),
                        ("nano", ctypes.c_uint16), ("rc", ctypes.c_char_p), ("describe", ctypes.c_char_p)]

        get_version = backend.lib.libusb_get_version
        get_version.restype = ctypes.POINTER(Version)
        get_version.argtypes = []
        version = get_version().contents
        return f"libusb {version.major}.{version.minor}.{version.micro}"
    except Exception as exc:  # the version is a courtesy; when it cannot be read, the trace says so
        return f"libusb, version not read ({type(exc).__name__})"


def stack_of(backend):
    describe = getattr(backend, "describe", None)
    end = describe() if callable(describe) else libusb_of(backend)
    return f"python {platform.python_version()}, pyusb {usb.__version__}, {end}"


def os_name():
    """The operating system and its version, and nothing that names the machine or its user."""
    system = platform.system()
    if system == "Darwin":
        return f"macOS {platform.mac_ver()[0]}"
    if system == "Windows":
        return f"Windows {platform.release()} ({platform.version()})"
    if system == "Linux":
        return f"Linux {platform.release()}"
    return platform.platform(terse=True)


def first_contact(facts, form, backend, timeout_ms, say):
    """Command 7 and its reply: (transfers, firmware, stack, refusal, findings, configured_here)."""
    transfers, findings = [], []
    firmware, stack, refusal, configured_here = "unknown", None, None, False
    start = time.monotonic_ns()

    def record(direction, data):
        transfers.append((direction, (time.monotonic_ns() - start) // 1000, bytes(data)))

    device = None
    try:
        device = find_labpro(facts, backend)
        stack = stack_of(device.backend)
        say(f"found the LabPro on bus {device.bus}, address {device.address}")
        interface, inward, outward, configured_here = bulk_pair(device, facts)
        if configured_here:
            say("pyusb could not read the active configuration, so the script set the device's first")
        say(f"bulk IN {inward.bEndpointAddress:#04x} and OUT {outward.bEndpointAddress:#04x} "
            f"on interface {interface.bInterfaceNumber}, {inward.wMaxPacketSize}-byte packets")
        try:
            if device.is_kernel_driver_active(interface.bInterfaceNumber):
                raise Refused(f"a kernel driver holds interface {interface.bInterfaceNumber}; "
                              f"this script does not detach it")
        except NotImplementedError:
            pass
        usb.util.claim_interface(device, interface)
        message = command(facts, facts["command.request_system_status"], form)
        start = time.monotonic_ns()
        try:
            written = device.write(outward.bEndpointAddress, message, timeout_ms)
        except usb.core.USBTimeoutError:
            raise Refused(f"the LabPro did not take Command 7 within {timeout_ms} ms") from None
        record("OUT", message[:written])
        if written != len(message):
            findings.append(f"only {written} of Command 7's {len(message)} bytes were taken")
        values = registers(read_reply(device, inward, facts, timeout_ms, record, findings), facts)
        firmware = values[facts["status.software_id_position"] - 1]
        say("the reply's values, in order (protocol/REFERENCE.md names them):")
        for place, value in enumerate(values, start=1):
            say(f"  {place:>2}  {value}")
    except Refused as why:
        refusal = str(why)
    except usb.core.USBError as exc:
        refusal = f"pyusb reported a USB error: {exc}"
    except NotImplementedError as exc:
        refusal = (f"the USB backend cannot do that on this host ({exc}); on Windows, the LabPro needs "
                   f"the WinUSB driver, as tools/bench/README.md says")
    finally:
        if device is not None:
            usb.util.dispose_resources(device)
    return transfers, firmware, stack, refusal, findings, configured_here


def check_out(path, root, backend):
    """Where the trace goes, or Refused: never over a file, never among the fixtures, and
    never among the recordings when the device is the fake."""
    out = Path(path).resolve()
    if out.exists():
        raise Refused(f"{path} exists, and this script never writes over a file")
    if not out.parent.is_dir():
        raise Refused(f"{path}: its folder does not exist")
    if out.is_relative_to((root / "protocol" / "fixtures").resolve()):
        raise Refused("what this script writes is a recording, and protocol/fixtures/ holds fixtures only")
    if out.is_relative_to((root / "protocol" / "traces").resolve()) and getattr(backend, "fake", False):
        raise Refused("a trace made against the fake backend is not a recording, "
                      "so it does not go in protocol/traces/")
    return out


def write_trace(out, began, transfers, firmware, stack, form, configured_here):
    note = f"Command 7 framed as {form}"
    if configured_here:
        note += "; pyusb could not read the active configuration, so the script set the device's first before it"
    header = {"date": began.isoformat(timespec="seconds"), "os": os_name(), "stack": stack,
              "firmware": firmware, "note": note}
    data = traces.write("trace", header, transfers).encode("utf-8")
    with open(out, "xb") as handle:
        handle.write(data)
    return hashlib.sha256(data).hexdigest()


def main(argv=None, backend=None, stdout=None, root=ROOT):
    """Run first contact; backend and root are for tests, which pass the fake and a scratch folder."""
    stdout = stdout or sys.stdout

    def say(line):
        print(line, file=stdout)

    parser = argparse.ArgumentParser(description="First contact with a LabPro: Command 7, recorded.")
    parser.add_argument("--out", required=True, help="where the trace goes; never an existing file")
    parser.add_argument("--form", choices=FORMS, default="s-cr", help="how Command 7 is framed (default s-cr)")
    parser.add_argument("--timeout-ms", type=int, default=TIMEOUT_MS, help="how long one transfer waits")
    parser.add_argument("--libusb", metavar="LIB", help="load libusb from this path, where pyusb cannot find it")
    args = parser.parse_args(argv)
    if usb is None:
        say("refused: pyusb is not installed here; tools/bench/README.md says how to install it")
        return 1
    facts = Facts(root)
    began = datetime.datetime.now().astimezone()
    try:
        out = check_out(args.out, root, backend)
    except Refused as why:
        say(f"refused: {why}")
        return 1
    if args.libusb and backend is None:
        backend = usb.backend.libusb1.get_backend(find_library=lambda name: args.libusb)
        if backend is None:
            say(f"refused: libusb could not be loaded from {args.libusb}")
            return 1
    transfers, firmware, stack, refusal, findings, configured_here = first_contact(
        facts, args.form, backend, args.timeout_ms, say)
    if transfers:
        digest = write_trace(out, began, transfers, firmware, stack, args.form, configured_here)
        say(f"wrote {len(transfers)} transfers to {args.out}")
        say(f"its SHA-256 is {digest}")
    else:
        say("no transfer was made, so no trace was written")
    for finding in findings:
        say(f"differs from the manual: {finding}")
    if refusal:
        say(f"refused: {refusal}")
    return 1 if refusal or findings else 0


if __name__ == "__main__":
    sys.exit(main())
