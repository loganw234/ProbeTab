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

It also keeps what a test needs to see: the timeout of every transfer, and how
often the device was opened and closed.

A fixture is the lead's model of a LabPro, so a test that passes against one
says the script agrees with that model, not with a LabPro. A recording from
the bench can be replayed the same way.

The descriptors' other fields, such as the endpoint addresses and the class
codes, are this file's inventions, chosen so that a script relying on them
would fail. Nothing here says what a LabPro reports for them.
"""
import array

import usb.backend
import usb.core
import usb.util

IN_ADDRESS = 0x82   # invented: a LabPro's addresses are for the bench to show
OUT_ADDRESS = 0x01  # invented, and numbered apart from IN_ADDRESS on purpose


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
                 take=None, write_timeout=False, read_error=None, unsupported=None):
        self.transfers = list(trace.transfers)
        self.facts = facts
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
                          bcdDevice=0x0100, iManufacturer=0, iProduct=0, iSerialNumber=0, bNumConfigurations=1,
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
        return len(sent) if self.take is None else min(self.take, len(sent))

    def bulk_read(self, dev_handle, ep, intf, buff, timeout):
        self.timeouts.append(("IN", timeout))
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
