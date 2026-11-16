#!/usr/bin/env python3
"""Phase 0 with a LabPro: find it, ask its status, read CH1, and record every transfer.

    python tools/bench/labpro_bench.py --out PATH [--form FORM] [--timeout-ms N] [--libusb LIB]
                                       [--descriptors] [--read-ch1 [--discard]
                                       [--every SECONDS [--readings N] [--for SECONDS]]]

By default it finds the one USB device with the LabPro's vendor and product IDs
and sends it Command 7, the status request, and no other command. It never
resets the unit unasked: a unit may still hold an earlier experiment's data. It
reads each reply one packet at a time until the byte that ends a reply, and
writes every bulk transfer to PATH as a trace (protocol/traces/FORMAT.md).

--descriptors reads the device and configuration descriptors, and the device's
strings, into the trace's header. The serial number is masked as
tools/traces.py says: model information only.

--read-ch1 goes on, after Command 7, to read a voltage on CH1. In order:
    the guard: the system state in Command 7's reply is decoded exactly, as
        page 45 gives it. A unit that is initializing or self-testing is read
        again, a few times, a second apart. The reset is sent only to a unit
        that is idle or done with no data unretrieved. --discard allows the
        reset when data is unretrieved, and that data is lost. An armed or
        busy unit is never reset.
    Command 0, the reset; the script listens briefly for anything after it.
    Command 7, which must show idle with no data unretrieved.
    Command 1, channel 1 by auto-ID; the script listens briefly again.
    Command 7, whose error register must be 0.
    Command 9 for channel 1 in mode 0, the present setup: one value.
    Command 7, whose error register must be 0.
    Command 9 in mode 1, once, as an experiment: the stored setup's value.
    Command 7, whose error register must be 0.
--every then reads Command 9 in mode 0 at that interval, of at most
MAX_EVERY seconds, until --readings readings or --for seconds, with Command 7
checked every ERROR_EVERY readings.

pyusb and libusb also make standard USB requests of the device on the
script's behalf: they read its descriptors and which configuration is active,
and when that read fails, the script has pyusb set the first configuration.
These are not LabPro commands, and a trace holds bulk transfers only, so its
note says when the script set the configuration.

Every value about the LabPro comes from protocol/labpro-facts.toml, read
through tools/labpro_facts.py, and each refusal names the fact it rests on.
Whatever the script does not recognise, it refuses by name. It still writes
the transfers it made, because what the LabPro did is the evidence. So it does
when stopped by Ctrl-C, or by an error it does not name, which then goes on
with its traceback. When no transfer was made, there is no trace to write.

FORM is how every command is framed. The manual writes s{7} for a computer
host, and a carriage return after each command on the serial port. Whether USB
wants either is the first thing the bench has to settle:

    s-cr   s{7} and the carriage return (the default)
    s      s{7} alone
    cr     {7} and the carriage return
    bare   {7} alone

LIB is a libusb library to load by its path, for a host where pyusb finds none
by itself. pyusb 1.3.1 already looks in /opt/homebrew/lib on Apple Silicon.

Exit status: 0 when every reply was recognised, 1 when anything was refused or
differed from the manual, or the run was stopped, 2 when the command line is
wrong.
tools/bench/README.md says how to set it up and run it.
"""
import argparse
import datetime
import hashlib
import math
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
    import usb.control
    import usb.core
    import usb.util
except ImportError:  # named when the script runs; see main()
    usb = None

FORMS = ("s-cr", "s", "cr", "bare")
TIMEOUT_MS = 2000      # how long one read waits for a packet; the manual gives no figure
MAX_PACKETS = 64       # a reply that takes more packets than this is refused
QUIET_MS = 300         # how long the script listens for anything after a command, or after a reply
RETRIES = 5            # how often Command 7 is read again while the unit initializes, or is silent
RETRY_SECONDS = 1.0    # how long the script waits before each of those reads
ERROR_EVERY = 10       # in a live reading, Command 7 follows every this many readings
MAX_EVERY = 86400      # the longest interval --every takes, a day; time.sleep refuses some finite numbers
STATES = ("status.state_idle", "status.state_armed", "status.state_busy", "status.state_done",
          "status.state_self_test", "status.state_initializing")
RESETTABLE = ("status.state_idle", "status.state_done")
WAITING = ("status.state_initializing", "status.state_self_test")


class Refused(Exception):
    """Something the script does not recognise, said in words."""


class NoReply(Refused):
    """Nothing at all came in reply."""


class Facts:
    """The facts file's facts by name: facts[name] is a value, cite(name) says where it is from."""

    def __init__(self, root=ROOT):
        self.tables = dict(labpro_facts.facts(labpro_facts.load(root)))

    def __getitem__(self, name):
        return self.tables[name]["value"]

    def cite(self, name):
        return f"{name}, page {self.tables[name]['page']}"


def command(facts, number, form, parameters=()):
    """The bytes of a command and its parameters, framed as form says."""
    text = (facts["command.open"] + facts["command.separator"].join(str(item) for item in (number, *parameters))
            + facts["command.close"])
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


def values_of(reply, facts):
    """The values of a reply, each as the text the LabPro sent, or Refused."""
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
    form = facts["data.ascii_number_format"]
    pattern = number_form(form)
    for place, value in enumerate(values, start=1):
        if not pattern.fullmatch(value):
            raise Refused(f"value {place} of the reply, {value!r}, is not written {form} "
                          f"({facts.cite('data.ascii_number_format')})")
    return values


def registers(reply, facts):
    """The values of a Command 7 reply, or Refused."""
    values = values_of(reply, facts)
    count = facts["status.register_count"]
    if len(values) != count:
        raise Refused(f"the reply holds {len(values)} values, not {count} ({facts.cite('status.register_count')})")
    place, check = facts["status.check_value_position"], facts["status.check_value"]
    if float(values[place - 1]) != check:
        raise Refused(f"value {place} of the reply is {values[place - 1]}, not {check} "
                      f"({facts.cite('status.check_value')}; {facts.cite('status.check_value_position')})")
    return values


def decode_state(values, facts):
    """(the state's fact name, QuickSetup, data unretrieved) for Command 7's system state, or Refused."""
    place = facts["status.system_state_position"]
    value = float(values[place - 1])
    for quick in (0, facts["status.quicksetup_flag"]):
        for unretrieved in (0, facts["status.unretrieved_data_flag"]):
            for name in STATES:
                if value == facts[name] + quick + unretrieved:
                    return name, bool(quick), bool(unretrieved)
    raise Refused(f"the system state {values[place - 1]} is no state page 45 gives, with or without its flags "
                  f"({facts.cite('status.system_state_position')})")


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


def string_of(device, index):
    """A string descriptor's text, with spaces at either end removed: none when there is no string or
    it is blank, and unreadable when it cannot be read or holds a character that is not printable."""
    if not index:
        return "none"
    try:
        text = usb.util.get_string(device, index)
    except (usb.core.USBError, ValueError):
        return "unreadable"
    text = (text or "").strip()
    if not text:
        return "none"
    return text if text.isprintable() else "unreadable"


def read_descriptors(device):
    """The trace header's lines for the device's descriptors and strings, the serial masked, or Refused."""
    lines = {"device": bytes(usb.control.get_descriptor(device, 18, usb.util.DESC_TYPE_DEVICE, 0)).hex(" ")}
    head = bytes(usb.control.get_descriptor(device, 9, usb.util.DESC_TYPE_CONFIG, 0))
    if len(head) < 9:
        raise Refused(f"the configuration descriptor's first read gave {len(head)} bytes, not 9")
    total = head[2] | head[3] << 8
    lines["configuration"] = bytes(usb.control.get_descriptor(device, total, usb.util.DESC_TYPE_CONFIG, 0)).hex(" ")
    for key in ("device", "configuration"):
        problem = traces.descriptor_problem(key, lines[key])
        if problem:
            raise Refused(f"the device's {key} descriptor is not well formed: {problem}")
    lines["manufacturer"] = string_of(device, device.iManufacturer)
    lines["product"] = string_of(device, device.iProduct)
    serial = string_of(device, device.iSerialNumber)
    lines["serial"] = serial if serial in traces.SERIAL_ABSENT else traces.mask_serial(serial)
    return lines


def read_reply(device, inward, facts, timeout_ms, record, findings, what):
    """The reply's packets joined, up to the one holding the end of the reply, or Refused."""
    size, multiple = facts["usb.packet_size"], facts["usb.in_transfer_multiple"]
    terminator = facts["reply.terminator"].encode("ascii")
    reply = b""
    for _ in range(MAX_PACKETS):
        try:
            packet = bytes(device.read(inward.bEndpointAddress, size, timeout_ms))
        except usb.core.USBTimeoutError:
            if not reply:
                raise NoReply(f"no reply came within {timeout_ms} ms of {what}") from None
            raise Refused(f"the reply to {what} stopped after {len(reply)} bytes without its end "
                          f"({facts.cite('reply.terminator')})") from None
        record("IN", packet)
        if len(packet) % multiple:
            findings.append(f"a packet of {len(packet)} bytes, where transfers to the host come in multiples "
                            f"of {multiple} ({facts.cite('usb.in_transfer_multiple')})")
        reply += packet
        if terminator in reply:
            return reply
    raise Refused(f"no end of reply to {what} in {MAX_PACKETS} packets ({facts.cite('reply.terminator')})")


class Session:
    """The commands of one run, each sent in the run's framing, and every transfer recorded."""

    def __init__(self, device, inward, outward, facts, form, timeout_ms, record, findings, say):
        self.device, self.inward, self.outward = device, inward, outward
        self.facts, self.form, self.timeout_ms = facts, form, timeout_ms
        self.record, self.findings, self.say = record, findings, say

    def send(self, number, *parameters):
        message = command(self.facts, number, self.form, parameters)
        try:
            written = self.device.write(self.outward.bEndpointAddress, message, self.timeout_ms)
        except usb.core.USBTimeoutError:
            raise Refused(f"the LabPro did not take Command {number} within {self.timeout_ms} ms") from None
        self.record("OUT", message[:written])
        if written != len(message):
            self.findings.append(f"only {written} of Command {number}'s {len(message)} bytes were taken")

    def reply(self, what):
        return read_reply(self.device, self.inward, self.facts, self.timeout_ms, self.record, self.findings, what)

    def quiet(self, after, said=None):
        """Listens briefly after a command or a reply, and records and names anything that comes."""
        try:
            packet = bytes(self.device.read(self.inward.bEndpointAddress, self.facts["usb.packet_size"], QUIET_MS))
        except usb.core.USBTimeoutError:
            return
        self.record("IN", packet)
        self.findings.append(f"{len(packet)} bytes came after {after}" + (f", which {said}" if said else ""))

    def status(self):
        self.send(self.facts["command.request_system_status"])
        return registers(self.reply("Command 7"), self.facts)

    def settled(self, values):
        """The decoded state, once it is neither initializing nor self-testing, read again while it is, or
        while Command 7 draws no reply, up to RETRIES times; None if Command 7 drew no reply at the last."""
        state = decode_state(values, self.facts) if values is not None else None
        tries = 0
        while (state is None or state[0] in WAITING) and tries < RETRIES:
            time.sleep(RETRY_SECONDS)
            tries += 1
            try:
                state = decode_state(self.status(), self.facts)
            except NoReply:
                state = None
        return state

    def no_errors(self, after):
        values = self.status()
        place = self.facts["status.error_position"]
        if float(values[place - 1]) != 0:
            raise Refused(f"the error register is {values[place - 1]} after {after} "
                          f"({self.facts.cite('status.error_position')})")

    def channel_value(self, mode):
        facts = self.facts
        self.send(facts["command.request_channel_data"], facts["channel.ch1"], mode)
        values = values_of(self.reply("Command 9"), facts)
        if len(values) != 1:
            raise Refused(f"Command 9's reply holds {len(values)} values, not one "
                          f"({facts.cite('command.request_channel_data')})")
        self.quiet("Command 9's reply")
        return values[0]


def label(name):
    return name.removeprefix("status.state_").replace("_", "-")


def read_ch1(session, first, discard, every, readings, seconds, say):
    """Reads CH1, as the docstring gives the steps, after the status first. Refused at any step it
    does not recognise."""
    facts = session.facts
    state = session.settled(first)
    if state is None:
        raise Refused(f"Command 7 drew no reply on any of {RETRIES} more tries")
    name, quick, unretrieved = state
    if name in WAITING:
        raise Refused(f"the unit stayed {label(name)} through {RETRIES} more readings of Command 7 "
                      f"({facts.cite(name)})")
    if name not in RESETTABLE:
        raise Refused(f"the unit is {label(name)} ({facts.cite(name)}); the script resets only an idle or done "
                      f"unit, never an armed or busy one, --discard or not")
    if unretrieved and not discard:
        raise Refused(f"the unit holds data not yet retrieved ({facts.cite('status.unretrieved_data_flag')}); "
                      f"--discard resets it anyway, and that data is lost")
    say(f"the unit is {label(name)}{', with data not yet retrieved, which --discard loses' if unretrieved else ''}; "
        f"resetting it")
    session.send(facts["command.reset"])
    session.quiet("Command 0", f"page 30 says returns nothing ({facts.cite('command.reset_reply')})")
    state = session.settled(None)
    if state is None or state[0] != "status.state_idle" or state[2]:
        seen = "no reply" if state is None else label(state[0]) + (" with data unretrieved" if state[2] else "")
        raise Refused(f"after the reset the unit is not idle: {seen} ({facts.cite('status.state_idle')})")
    session.send(facts["command.channel_setup"], facts["channel.ch1"], facts["channel.operation_auto_id"])
    session.quiet("Command 1", f"page 32 says returns nothing ({facts.cite('command.channel_setup_reply')})")
    session.no_errors("Command 1")
    present = session.channel_value(facts["channel_data.mode_retest"])
    session.no_errors("Command 9")
    stored = session.channel_value(facts["channel_data.mode_stored"])
    session.no_errors("Command 9 in mode 1")
    say(f"CH1: {present} by Command 9 in mode 0, the present setup; {stored} in mode 1, the stored setup")
    if every is None:
        return
    began, count = time.monotonic(), 0
    while (readings is None or count < readings) and (seconds is None or time.monotonic() - began < seconds):
        value = session.channel_value(facts["channel_data.mode_retest"])
        count += 1
        say(f"{time.monotonic() - began:9.1f} s  {value}")
        if count % ERROR_EVERY == 0:
            session.no_errors("the live reading")
        time.sleep(every)


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


class Run:
    """What one run gathers: its transfers, what it read, and what it refused or found."""

    def __init__(self):
        self.transfers, self.findings = [], []
        self.firmware, self.stack, self.refusal = "unknown", None, None
        self.configured_here, self.descriptors = False, {}


def phase0(facts, args, backend, say, run):
    """Command 7, and whatever else args asks for, gathered into run, which main writes out
    whatever ends the run."""
    start = time.monotonic_ns()

    def record(direction, data):
        run.transfers.append((direction, (time.monotonic_ns() - start) // 1000, bytes(data)))

    device = None
    try:
        device = find_labpro(facts, backend)
        run.stack = stack_of(device.backend)
        say(f"found the LabPro on bus {device.bus}, address {device.address}")
        interface, inward, outward, run.configured_here = bulk_pair(device, facts)
        if run.configured_here:
            say("pyusb could not read the active configuration, so the script set the device's first")
        say(f"bulk IN {inward.bEndpointAddress:#04x} and OUT {outward.bEndpointAddress:#04x} "
            f"on interface {interface.bInterfaceNumber}, {inward.wMaxPacketSize}-byte packets")
        if args.descriptors:
            run.descriptors = read_descriptors(device)
            say("descriptors: " + "; ".join(f"{key} {value if len(value) < 40 else f'{len(value.split())} bytes'}"
                                            for key, value in run.descriptors.items()))
        try:
            if device.is_kernel_driver_active(interface.bInterfaceNumber):
                raise Refused(f"a kernel driver holds interface {interface.bInterfaceNumber}; "
                              f"this script does not detach it")
        except NotImplementedError:
            pass
        usb.util.claim_interface(device, interface)
        session = Session(device, inward, outward, facts, args.form, args.timeout_ms, record, run.findings, say)
        start = time.monotonic_ns()
        values = session.status()
        run.firmware = values[facts["status.software_id_position"] - 1]
        say("the reply's values, in order (protocol/REFERENCE.md names them):")
        for place, value in enumerate(values, start=1):
            say(f"  {place:>2}  {value}")
        if args.read_ch1:
            read_ch1(session, values, args.discard, args.every, args.readings, getattr(args, "for"), say)
    except Refused as why:
        run.refusal = str(why)
    except usb.core.USBError as exc:
        run.refusal = f"pyusb reported a USB error: {exc}"
    except NotImplementedError as exc:
        run.refusal = (f"the USB backend cannot do that on this host ({exc}); on Windows, the LabPro needs "
                       f"the WinUSB driver, as tools/bench/README.md says")
    except KeyboardInterrupt:
        run.refusal = "stopped by the operator (Ctrl-C); the transfers made so far are kept"
    finally:
        if device is not None:
            usb.util.dispose_resources(device)


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


def write_trace(out, began, run, form):
    note = f"Command 7 framed as {form}"
    if run.configured_here:
        note += "; pyusb could not read the active configuration, so the script set the device's first before it"
    header = {"date": began.isoformat(timespec="seconds"), "os": os_name(), "stack": run.stack,
              "firmware": run.firmware, "note": note, **run.descriptors}
    data = traces.write("trace", header, run.transfers).encode("utf-8")
    with open(out, "xb") as handle:
        handle.write(data)
    return hashlib.sha256(data).hexdigest()


def seconds(text):
    """A finite number of seconds, 0 or more."""
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not a finite number of seconds, 0 or more")
    return value


def interval(text):
    """--every's seconds: from 0 to MAX_EVERY."""
    value = seconds(text)
    if value > MAX_EVERY:
        raise argparse.ArgumentTypeError(f"{text!r} is more than {MAX_EVERY} seconds, the longest interval "
                                         f"--every takes")
    return value


def duration(text):
    """--for's seconds: a finite number above 0."""
    value = seconds(text)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of seconds above 0")
    return value


def reading_count(text):
    """--readings: a whole number, 1 or more."""
    try:
        value = int(text)
    except ValueError:
        value = 0
    if value < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of readings, 1 or more")
    return value


def main(argv=None, backend=None, stdout=None, root=ROOT):
    """Run Phase 0's steps; backend and root are for tests, which pass the fake and a scratch folder."""
    stdout = stdout or sys.stdout

    def say(line):
        print(line, file=stdout)

    parser = argparse.ArgumentParser(description="Phase 0 with a LabPro: Command 7, CH1, recorded.")
    parser.add_argument("--out", required=True, help="where the trace goes; never an existing file")
    parser.add_argument("--form", choices=FORMS, default="s-cr", help="how every command is framed (default s-cr)")
    parser.add_argument("--timeout-ms", type=int, default=TIMEOUT_MS, help="how long one transfer waits")
    parser.add_argument("--libusb", metavar="LIB", help="load libusb from this path, where pyusb cannot find it")
    parser.add_argument("--descriptors", action="store_true", help="record the device's descriptors and strings")
    parser.add_argument("--read-ch1", action="store_true", help="go on to reset, set up and read CH1")
    parser.add_argument("--discard", action="store_true", help="reset even when data is not yet retrieved")
    parser.add_argument("--every", type=interval, metavar="SECONDS", help="then read CH1 at this interval")
    parser.add_argument("--readings", type=reading_count, metavar="N", help="with --every, stop after N readings")
    parser.add_argument("--for", type=duration, metavar="SECONDS", help="with --every, stop after this long")
    args = parser.parse_args(argv)
    if (args.discard or args.every is not None) and not args.read_ch1:
        parser.error("--discard and --every go with --read-ch1")
    if args.every is not None and args.readings is None and getattr(args, "for") is None:
        parser.error("--every needs --readings or --for, so that it ends")
    if (args.readings is not None or getattr(args, "for") is not None) and args.every is None:
        parser.error("--readings and --for go with --every")
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
    run = Run()
    try:
        phase0(facts, args, backend, say, run)
    finally:
        # Whatever ends the run, the transfers made so far are written. An error the script does not
        # name then goes on, with its traceback.
        if run.transfers:
            digest = write_trace(out, began, run, args.form)
            say(f"wrote {len(run.transfers)} transfers to {args.out}")
            say(f"its SHA-256 is {digest}")
        else:
            say("no transfer was made, so no trace was written")
    for finding in run.findings:
        say(f"differs from the manual: {finding}")
    if run.refusal:
        say(f"refused: {run.refusal}")
    return 1 if run.refusal or run.findings else 0


if __name__ == "__main__":
    sys.exit(main())
