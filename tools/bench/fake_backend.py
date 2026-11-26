"""A pyusb backend that stands in for a LabPro by replaying a trace.

The device it shows pyusb is built from protocol/labpro-facts.toml: the vendor
and product IDs, the bulk endpoints in each direction, and their packet size.
What the device says is the trace's, in order:

  - each write must be the trace's next OUT, byte for byte, or Mismatch is
    raised;
  - each read must ask for one packet, the endpoint's packet size, as the
    script is written to; it returns the trace's next IN;
  - a read when the next transfer is not an IN times out, as a read from a
    LabPro waits while it answers NAK (page 23).

It also keeps what a test needs to see: the timeout of every transfer, how
often the device was opened and closed, and every descriptor asked for.

It answers GET_DESCRIPTOR for the device, the configuration and the strings,
with bytes built from its own fields, as USB lays them out. No other control
request is expected, and any other raises Mismatch.

A fixture is the lead's model of a LabPro, so a test that passes against one
says the script agrees with that model, not with a LabPro. A recording from
the bench can be replayed the same way.

One thing it can do beyond replaying, when asked to with command_1_errors: set
the error register. See CHANNEL_ROWS and FakeLabPro.error. That is the fake's own
model of a LabPro, and the real unit's code differs (see CHANNEL_ROWS), so it is
off unless a test asks, and a replay of a recording never has a reply rewritten.

The descriptors' other fields, such as the endpoint addresses and the class
codes, are this file's inventions, chosen so that a script relying on them
would fail. The real unit's are in the header of
protocol/traces/2026-11-25-first-contact.trace, and some match: both class codes
are 0xFF and the IN endpoint is 0x82, as here. So the fake no longer catches a
script that relies on those.
"""
import array
import struct

import usb.backend
import usb.core
import usb.util

IN_ADDRESS = 0x82   # invented, and the real unit's too (2026-11-25-first-contact.trace)
OUT_ADDRESS = 0x01  # invented, and numbered apart from IN_ADDRESS on purpose; the real unit's is 0x02
# The fake's own model: a unit that is told to set up a channel no row of page 31's table holds
# sets its error register (page 45 says it is non-zero after a fault) and keeps it until
# Command 0 clears the error state (page 30). The channels come from the facts, one fact for
# each row of that table, named here. The fake sets code 1. The real unit drew 12 for channel 14
# (protocol/traces/2026-11-25-ch1-volt-opfirst.trace), which the manual's table of error codes
# gives for a channel that does not exist, and read 0 again at the next run, before that run's reset
# (2026-11-25-ch1-0v.trace), for a cause not settled.
CHANNEL_ROWS = ("channel.numbers_all", "channel.numbers_analog", "channel.numbers_sonic",
                "channel.numbers_digital_in", "channel.numbers_digital_out")
ERROR_CODE = 1


def channels(facts, rows=CHANNEL_ROWS):
    """The channel numbers the named facts give. Each value is one number, two joined by a
    comma, or a first and a last joined by " - ", as the facts file's comment on them says."""
    found = set()
    for name in rows:
        for part in str(facts[name]).split(","):
            first, _, last = part.strip().partition(" - ")
            found.update(range(int(first), int(last or first) + 1))
    return frozenset(found)


class Mismatch(AssertionError):
    """The script did something the replayed trace does not hold."""


class Descriptor:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class FakeLabPro(usb.backend.IBackend):
    """Replays trace (a traces.Trace) as a LabPro would, named name in what it says.

    The keyword arguments change the device away from the facts, for tests of
    the script's refusals.
    """

    fake = True

    def __init__(self, trace, facts, name, *, devices=1, bulk_in=None, bulk_out=None, packet_size=None,
                 in_address=IN_ADDRESS, out_address=OUT_ADDRESS, configured=True, kernel_driver=False,
                 take=None, write_timeout=False, read_error=None, unsupported=None,
                 manufacturer=None, product=None, serial=None, short_device=False, short_configuration=False,
                 bad_total=False, interrupt_at=None, interruption=KeyboardInterrupt, command_1_errors=False):
        self.command_1_errors = command_1_errors  # model the error register, as the comment on CHANNEL_ROWS says
        self.error = 0                      # the error register the model holds
        self.short_configuration = short_configuration  # the configuration's first, 9-byte read gives 8
        self.bad_total = bad_total          # the configuration's total length says one byte more than it holds
        self.interrupt_at = interrupt_at    # the read, counted from 1, at which interruption is raised:
        self.interruption = interruption    # Ctrl-C by default, or an error the script does not name
        self.reads = 0
        # The device's strings, by the index its device descriptor gives each; 0 means none.
        self.strings = {}
        for index, text in enumerate((manufacturer, product, serial), start=1):
            if text is not None:
                self.strings[index] = text
        self.short_device = short_device    # the device descriptor comes back a byte short
        self.descriptors_asked = []         # (type, index, length) for every GET_DESCRIPTOR
        self.transfers = list(trace.transfers)
        self.facts = facts
        self.channels = channels(facts) if command_1_errors else None  # read only for the model
        self.name = name
        self.devices = list(range(devices))
        size = facts["usb.packet_size"] if packet_size is None else packet_size
        ins = facts["usb.bulk_in_endpoints"] if bulk_in is None else bulk_in
        outs = facts["usb.bulk_out_endpoints"] if bulk_out is None else bulk_out
        self.endpoints = ([self.endpoint(in_address + i, size) for i in range(ins)]
                          + [self.endpoint(out_address + i, size) for i in range(outs)])
        self.configuration = 1 if configured else 0
        self.kernel_driver = kernel_driver
        self.take = take                    # how many bytes a write is taken, when not all
        self.write_timeout = write_timeout  # every write times out
        self.read_error = read_error        # an exception every read raises
        self.unsupported = unsupported      # the backend method that raises NotImplementedError
        self.opened = 0
        self.closed = 0
        self.timeouts = []                  # (direction, timeout) for every transfer asked for

    @staticmethod
    def endpoint(address, size):
        return Descriptor(bLength=7, bDescriptorType=usb.util.DESC_TYPE_ENDPOINT, bEndpointAddress=address,
                          bmAttributes=usb.util.ENDPOINT_TYPE_BULK, wMaxPacketSize=size, bInterval=0,
                          bRefresh=0, bSynchAddress=0, extra_descriptors=[])

    def describe(self):
        return f"fake backend replaying {self.name}"

    def remaining(self):
        """The transfers not yet replayed."""
        return list(self.transfers)

    # pyusb's backend interface, as much of it as the script reaches.

    def enumerate_devices(self):
        return iter(self.devices)

    def get_device_descriptor(self, dev):
        return Descriptor(bLength=18, bDescriptorType=usb.util.DESC_TYPE_DEVICE, bcdUSB=0x0110,
                          bDeviceClass=0xFF, bDeviceSubClass=0, bDeviceProtocol=0, bMaxPacketSize0=8,
                          idVendor=self.facts["usb.vendor_id"], idProduct=self.facts["usb.product_id"],
                          bcdDevice=0x0100, iManufacturer=1 if 1 in self.strings else 0,
                          iProduct=2 if 2 in self.strings else 0, iSerialNumber=3 if 3 in self.strings else 0,
                          bNumConfigurations=1,
                          address=5 + dev, bus=1, port_number=1 + dev, port_numbers=(1 + dev,),
                          speed=usb.util.SPEED_FULL)

    def get_configuration_descriptor(self, dev, config):
        if config != 0:
            raise IndexError(config)
        return Descriptor(bLength=9, bDescriptorType=usb.util.DESC_TYPE_CONFIG,
                          wTotalLength=9 + 9 + 7 * len(self.endpoints), bNumInterfaces=1, bConfigurationValue=1,
                          iConfiguration=0, bmAttributes=0x80, bMaxPower=50, extra_descriptors=[])

    def get_interface_descriptor(self, dev, intf, alt, config):
        if (intf, alt, config) != (0, 0, 0):
            raise IndexError((intf, alt, config))
        return Descriptor(bLength=9, bDescriptorType=usb.util.DESC_TYPE_INTERFACE, bInterfaceNumber=0,
                          bAlternateSetting=0, bNumEndpoints=len(self.endpoints), bInterfaceClass=0xFF,
                          bInterfaceSubClass=0, bInterfaceProtocol=0, iInterface=0, extra_descriptors=[])

    def get_endpoint_descriptor(self, dev, ep, intf, alt, config):
        if (intf, alt, config) != (0, 0, 0) or not 0 <= ep < len(self.endpoints):
            raise IndexError((ep, intf, alt, config))
        return self.endpoints[ep]

    def unsupported_here(self, method):
        if self.unsupported == method:
            raise NotImplementedError("Operation not supported or unimplemented on this platform")

    def open_device(self, dev):
        self.unsupported_here("open_device")
        self.opened += 1
        return dev

    def close_device(self, dev_handle):
        self.closed += 1

    def set_configuration(self, dev_handle, config_value):
        self.configuration = config_value

    def get_configuration(self, dev_handle):
        return self.configuration

    def claim_interface(self, dev_handle, intf):
        self.unsupported_here("claim_interface")

    def release_interface(self, dev_handle, intf):
        pass

    def is_kernel_driver_active(self, dev_handle, intf):
        return self.kernel_driver

    def device_bytes(self):
        d = self.get_device_descriptor(0)
        data = struct.pack("<BBHBBBBHHHBBBB", d.bLength, d.bDescriptorType, d.bcdUSB, d.bDeviceClass,
                           d.bDeviceSubClass, d.bDeviceProtocol, d.bMaxPacketSize0, d.idVendor, d.idProduct,
                           d.bcdDevice, d.iManufacturer, d.iProduct, d.iSerialNumber, d.bNumConfigurations)
        return data[:-1] if self.short_device else data

    def configuration_bytes(self):
        c = self.get_configuration_descriptor(0, 0)
        i = self.get_interface_descriptor(0, 0, 0, 0)
        data = struct.pack("<BBHBBBBB", c.bLength, c.bDescriptorType, c.wTotalLength + self.bad_total, c.bNumInterfaces,
                           c.bConfigurationValue, c.iConfiguration, c.bmAttributes, c.bMaxPower)
        data += struct.pack("<BBBBBBBBB", i.bLength, i.bDescriptorType, i.bInterfaceNumber, i.bAlternateSetting,
                            i.bNumEndpoints, i.bInterfaceClass, i.bInterfaceSubClass, i.bInterfaceProtocol,
                            i.iInterface)
        for e in self.endpoints:
            data += struct.pack("<BBBBHB", e.bLength, e.bDescriptorType, e.bEndpointAddress, e.bmAttributes,
                                e.wMaxPacketSize, e.bInterval)
        return data

    def string_bytes(self, index):
        if index == 0:
            return bytes([4, usb.util.DESC_TYPE_STRING, 0x09, 0x04])  # one language: US English
        if index not in self.strings:
            raise usb.core.USBError(f"the fake has no string {index}")
        text = self.strings[index].encode("utf-16-le")
        return bytes([2 + len(text), usb.util.DESC_TYPE_STRING]) + text

    def ctrl_transfer(self, dev_handle, bmRequestType, bRequest, wValue, wIndex, data, timeout):
        if bmRequestType != 0x80 or bRequest != 0x06:
            raise Mismatch(f"the script made control request {bmRequestType:#04x} {bRequest:#04x}, "
                           f"which is not GET_DESCRIPTOR")
        kind, index = wValue >> 8, wValue & 0xFF
        self.descriptors_asked.append((kind, index, len(data)))
        if kind == usb.util.DESC_TYPE_DEVICE:
            blob = self.device_bytes()
        elif kind == usb.util.DESC_TYPE_CONFIG:
            blob = self.configuration_bytes()
            if self.short_configuration and len(data) == 9:
                blob = blob[:8]
        elif kind == usb.util.DESC_TYPE_STRING:
            blob = self.string_bytes(index)
        else:
            raise usb.core.USBError(f"the fake has no descriptor of type {kind}")
        count = min(len(blob), len(data))
        data[:count] = array.array("B", blob[:count])
        return count

    def packet_size(self, ep):
        return next(endpoint.wMaxPacketSize for endpoint in self.endpoints if endpoint.bEndpointAddress == ep)

    def bulk_write(self, dev_handle, ep, intf, data, timeout):
        sent = bytes(data)
        self.timeouts.append(("OUT", timeout))
        if usb.util.endpoint_direction(ep) != usb.util.ENDPOINT_OUT:
            raise Mismatch(f"the script wrote {sent.hex(' ')} to {ep:#04x}, an IN endpoint")
        if self.write_timeout:
            raise usb.core.USBTimeoutError(f"timed out after {timeout} ms: the fake takes no write")
        if not self.transfers or self.transfers[0][0] != "OUT":
            after = "nothing more" if not self.transfers else f"an IN of {len(self.transfers[0][2])} bytes"
            raise Mismatch(f"the script sent {sent.hex(' ')}, where {self.name} has {after} next")
        want = self.transfers[0][2]
        if sent != want:
            raise Mismatch(f"the script sent {sent.hex(' ')}, where {self.name} has OUT {want.hex(' ')}")
        self.transfers.pop(0)
        if self.command_1_errors:
            self.model_error(sent)
        return len(sent) if self.take is None else min(self.take, len(sent))

    def model_error(self, sent):
        """Keeps the error register of the model on CHANNEL_ROWS, and puts it into the reply to Command 7
        that the trace holds next, in place of the register the trace holds there."""
        facts = self.facts
        text = sent.decode("ascii", "replace")
        start, end = text.find(facts["command.open"]), text.rfind(facts["command.close"])
        if start < 0 or end < start:
            return
        try:
            numbers = [int(part) for part in text[start + 1:end].split(facts["command.separator"])]
        except ValueError:
            return
        if numbers[0] == facts["command.reset"]:
            self.error = 0
        elif numbers[0] == facts["command.channel_setup"] and len(numbers) > 1 and numbers[1] not in self.channels:
            self.error = ERROR_CODE
        elif numbers[0] == facts["command.request_system_status"] and self.error:
            self.place_error()

    def place_error(self):
        """Rewrites the register at status.error_position in the replay's next reply, keeping every
        packet's length."""
        facts = self.facts
        count, terminator = 0, facts["reply.terminator"].encode("ascii")
        joined = b""
        while count < len(self.transfers) and self.transfers[count][0] == "IN":
            joined += self.transfers[count][2]
            count += 1
            if terminator in joined:
                break
        if terminator not in joined:
            return
        separator = facts["command.separator"].encode("ascii")
        at = joined.index(facts["command.open"].encode("ascii")) + 1
        for _ in range(facts["status.error_position"] - 1):
            at = joined.index(separator, at) + 1
        stop = min(place for place in (joined.find(separator, at), joined.find(facts["command.close"].encode("ascii"), at))
                   if place >= 0)
        spaces = len(joined[at:stop]) - len(joined[at:stop].lstrip())
        kept = joined[at + spaces:stop]
        new = f"{self.error:+.5E}".encode("ascii")
        if len(new) != len(kept):
            raise Mismatch(f"the fake cannot put {new!r} where {self.name} has {kept!r}")
        joined = joined[:at + spaces] + new + joined[stop:]
        place = 0
        for index in range(count):
            direction, when, old = self.transfers[index]
            self.transfers[index] = (direction, when, joined[place:place + len(old)])
            place += len(old)

    def bulk_read(self, dev_handle, ep, intf, buff, timeout):
        self.timeouts.append(("IN", timeout))
        self.reads += 1
        if self.reads == self.interrupt_at:
            raise self.interruption
        if usb.util.endpoint_direction(ep) != usb.util.ENDPOINT_IN:
            raise Mismatch(f"the script read from {ep:#04x}, an OUT endpoint")
        if len(buff) != self.packet_size(ep):
            raise Mismatch(f"the script asked for {len(buff)} bytes, where a packet from {ep:#04x} "
                           f"is {self.packet_size(ep)}")
        if self.read_error is not None:
            raise self.read_error
        if not self.transfers or self.transfers[0][0] != "IN":
            raise usb.core.USBTimeoutError(f"timed out after {timeout} ms: {self.name} has no IN next")
        data = self.transfers[0][2]
        if len(data) > len(buff):
            raise Mismatch(f"{self.name}'s next IN holds {len(data)} bytes, more than the {len(buff)} "
                           f"the script asked for")
        self.transfers.pop(0)
        buff[:len(data)] = array.array("B", data)
        return len(data)
