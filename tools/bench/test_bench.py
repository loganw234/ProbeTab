"""Tests of the bench script against the fake backend, which replays fixtures.

    python -I -B tools/bench/test_bench.py

tools/check.py runs this as its bench check, with a Python that has pyusb.
Each test works in a scratch folder holding a copy of the facts file, so no
trace the script writes, rightly or wrongly, lands in the repository.
"""
import array
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import labpro_bench as bench  # noqa: E402
import labpro_facts  # noqa: E402
import traces  # noqa: E402
import usb.backend.libusb1  # noqa: E402
import usb.core  # noqa: E402
from fake_backend import IN_ADDRESS, FakeLabPro, Mismatch  # noqa: E402

REPO = HERE.parent.parent
FIXTURE = "protocol/fixtures/status-request.trace"


class FirstContact(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="probetab-bench-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        for folder in ("protocol/fixtures", "protocol/traces"):
            (self.root / folder).mkdir(parents=True)
        shutil.copyfile(REPO / labpro_facts.FACTS, self.root / labpro_facts.FACTS)
        self.facts = bench.Facts(self.root)
        self.fixture = traces.parse((REPO / FIXTURE).read_bytes().decode("utf-8"))
        self.out = self.root / "first-contact.trace"

    # Helpers

    def fake(self, transfers=None, **changes):
        if transfers is None:
            return FakeLabPro(self.fixture, self.facts, FIXTURE, **changes)
        return FakeLabPro(traces.Trace("fixture", {}, transfers), self.facts, "a test's trace", **changes)

    def run_bench(self, fake, *arguments, out=None):
        printed = io.StringIO()
        status = bench.main(["--out", str(out or self.out), *arguments], backend=fake, stdout=printed,
                            root=self.root)
        return status, printed.getvalue()

    def written(self):
        return traces.parse(self.out.read_bytes().decode("utf-8"))

    def command_sent(self):
        """The fixture's command: Command 7 as the manual frames it."""
        return [data for direction, _, data in self.fixture.transfers if direction == "OUT"][0]

    def reply(self):
        """The fixture's reply, as its IN transfers."""
        return [transfer for transfer in self.fixture.transfers if transfer[0] == "IN"]

    def reply_values(self):
        """The fixture's reply values, read here without the script's help."""
        data = b"".join(data for _, _, data in self.reply())
        text = data[:data.index(self.facts["reply.terminator"].encode("ascii"))].decode("ascii").strip()
        inner = text[len(self.facts["command.open"]):-len(self.facts["command.close"])]
        return [value.strip() for value in inner.split(self.facts["command.separator"])]

    def packets_of(self, data, size=None):
        """data padded with zeros to whole packets of size bytes, as IN transfers."""
        size = size or self.facts["usb.packet_size"]
        data += bytes(-len(data) % size)
        return [("IN", 1000, data[i:i + size]) for i in range(0, len(data), size)]

    def packets(self, values, size=None):
        """A reply holding values, in packets as packets_of makes them."""
        f = self.facts
        separator = f["command.separator"] + " "
        text = f["command.open"] + " " + separator.join(values) + f["command.close"] + f["reply.terminator"]
        return self.packets_of(text.encode("ascii"), size)

    def with_reply(self, values, size=None):
        return [("OUT", 0, self.command_sent())] + self.packets(values, size)

    # The script against the fixture

    def test_replays_the_fixture_and_records_every_transfer(self):
        fake = self.fake()
        status, printed = self.run_bench(fake)
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [], "the script left part of the fixture unread")
        trace = self.written()
        self.assertEqual(trace.kind, "trace")
        self.assertEqual([(direction, data) for direction, _, data in trace.transfers],
                         [(direction, data) for direction, _, data in self.fixture.transfers])
        software_id = self.reply_values()[self.facts["status.software_id_position"] - 1]
        self.assertEqual(trace.header["firmware"], software_id)
        self.assertIn(f"fake backend replaying {FIXTURE}", trace.header["stack"])
        self.assertEqual(trace.header["note"], "Command 7 framed as s-cr")

    def test_each_form_sends_its_bytes(self):
        prefix = self.facts["command.prefix"].encode("ascii")
        terminator = self.facts["command.serial_terminator"].encode("ascii")
        full = self.command_sent()
        self.assertTrue(full.startswith(prefix) and full.endswith(terminator), full)
        expected = {"s-cr": full, "s": full[:-len(terminator)], "cr": full[len(prefix):],
                    "bare": full[len(prefix):-len(terminator)]}
        self.assertEqual(set(expected), set(bench.FORMS))
        for form, sent in expected.items():
            with self.subTest(form=form):
                fake = self.fake([("OUT", 0, sent)] + self.reply())
                status, printed = self.run_bench(fake, "--form", form, out=self.root / f"{form}.trace")
                self.assertEqual(status, 0, printed)
                self.assertEqual(fake.remaining(), [])

    def test_the_fake_refuses_bytes_the_fixture_does_not_hold(self):
        with self.assertRaises(Mismatch):
            self.run_bench(self.fake(), "--form", "bare")

    def test_the_fake_refuses_a_read_of_more_than_one_packet(self):
        fake = self.fake()
        two_packets = array.array("B", bytes(2 * self.facts["usb.packet_size"]))
        with self.assertRaises(Mismatch):
            fake.bulk_read(None, IN_ADDRESS, 0, two_packets, 100)

    def test_passes_its_timeout_to_every_transfer(self):
        fake = self.fake()
        status, printed = self.run_bench(fake, "--timeout-ms", "1234")
        self.assertEqual(status, 0, printed)
        self.assertEqual(len(fake.timeouts), len(self.fixture.transfers))
        self.assertEqual({timeout for _, timeout in fake.timeouts}, {1234})

    def test_releases_the_device(self):
        fake = self.fake()
        status, printed = self.run_bench(fake)
        self.assertEqual(status, 0, printed)
        self.assertGreater(fake.opened, 0)
        self.assertEqual(fake.closed, fake.opened, "the device was left open")

    def test_finds_its_endpoints_at_any_address(self):
        status, printed = self.run_bench(self.fake(in_address=0x86, out_address=0x05))
        self.assertEqual(status, 0, printed)
        self.assertIn("bulk IN 0x86 and OUT 0x05", printed)

    # Devices that are not as the manual describes

    def test_refuses_when_no_labpro_is_found(self):
        status, printed = self.run_bench(self.fake(devices=0))
        self.assertEqual(status, 1)
        self.assertIn("no LabPro found", printed)
        self.assertIn(self.facts.cite("usb.vendor_id"), printed)
        self.assertFalse(self.out.exists())

    def test_refuses_two_labpros(self):
        status, printed = self.run_bench(self.fake(devices=2))
        self.assertEqual(status, 1)
        self.assertIn("2 devices have the LabPro's vendor and product IDs", printed)
        self.assertFalse(self.out.exists())

    def test_refuses_other_bulk_endpoints(self):
        more = self.facts["usb.bulk_in_endpoints"] + 1
        status, printed = self.run_bench(self.fake(bulk_in=more))
        self.assertEqual(status, 1)
        self.assertIn(f"{more} bulk IN endpoints, not {self.facts['usb.bulk_in_endpoints']} "
                      f"({self.facts.cite('usb.bulk_in_endpoints')})", printed)

    def test_refuses_other_bulk_out_endpoints(self):
        more = self.facts["usb.bulk_out_endpoints"] + 1
        status, printed = self.run_bench(self.fake(bulk_out=more))
        self.assertEqual(status, 1)
        self.assertIn(f"{more} bulk OUT endpoints, not {self.facts['usb.bulk_out_endpoints']} "
                      f"({self.facts.cite('usb.bulk_out_endpoints')})", printed)

    def test_refuses_another_packet_size(self):
        half = self.facts["usb.packet_size"] // 2
        status, printed = self.run_bench(self.fake(packet_size=half))
        self.assertEqual(status, 1)
        self.assertIn(f"packets of {half} bytes, not {self.facts['usb.packet_size']} "
                      f"({self.facts.cite('usb.packet_size')})", printed)

    def test_sets_the_configuration_of_an_unconfigured_device_and_says_so(self):
        status, printed = self.run_bench(self.fake(configured=False))
        self.assertEqual(status, 0, printed)
        self.assertIn("the script set the device's first", printed)
        self.assertIn("the script set the device's first", self.written().header["note"])

    def test_refuses_an_interface_a_kernel_driver_holds(self):
        status, printed = self.run_bench(self.fake(kernel_driver=True))
        self.assertEqual(status, 1)
        self.assertIn("a kernel driver holds interface 0", printed)
        self.assertFalse(self.out.exists())

    def test_an_operation_the_host_cannot_do_is_refused_by_name(self):
        status, printed = self.run_bench(self.fake(unsupported="open_device"))
        self.assertEqual(status, 1)
        self.assertIn("the USB backend cannot do that on this host", printed)
        self.assertFalse(self.out.exists())

    def test_a_write_that_times_out_is_refused(self):
        status, printed = self.run_bench(self.fake(write_timeout=True))
        self.assertEqual(status, 1)
        self.assertIn("the LabPro did not take Command 7 within", printed)
        self.assertFalse(self.out.exists())

    def test_a_short_write_is_named_and_recorded_as_taken(self):
        sent = self.command_sent()
        status, printed = self.run_bench(self.fake(take=len(sent) - 2))
        self.assertEqual(status, 1)
        self.assertIn(f"only {len(sent) - 2} of Command 7's {len(sent)} bytes were taken", printed)
        self.assertEqual(self.written().transfers[0][2], sent[:-2])

    def test_a_usb_error_is_refused_by_name_and_the_command_kept(self):
        status, printed = self.run_bench(self.fake(read_error=usb.core.USBError("planted error")))
        self.assertEqual(status, 1)
        self.assertIn("pyusb reported a USB error", printed)
        self.assertIn("planted error", printed)
        self.assertEqual([direction for direction, _, _ in self.written().transfers], ["OUT"])

    def test_refuses_libusb_it_cannot_load(self):
        self.assertIsNone(usb.backend.libusb1._lib_object, "libusb is already loaded in this process")
        missing = self.root / "no-such-libusb"
        status, printed = self.run_bench(None, "--libusb", str(missing))
        self.assertEqual(status, 1)
        self.assertIn(f"libusb could not be loaded from {missing}", printed)
        self.assertFalse(self.out.exists())

    # Replies that are not as the manual describes

    def test_no_reply_is_refused_and_the_command_still_recorded(self):
        status, printed = self.run_bench(self.fake([("OUT", 0, self.command_sent())]))
        self.assertEqual(status, 1)
        self.assertIn("no reply came within", printed)
        trace = self.written()
        self.assertEqual([direction for direction, _, _ in trace.transfers], ["OUT"])
        self.assertEqual(trace.header["firmware"], "unknown")

    def test_a_reply_without_its_end_is_refused(self):
        first = self.reply()[0]
        status, printed = self.run_bench(self.fake([("OUT", 0, self.command_sent()), first]))
        self.assertEqual(status, 1)
        self.assertIn(f"the reply stopped after {len(first[2])} bytes without its end", printed)
        self.assertEqual(len(self.written().transfers), 2)

    def test_a_reply_of_sixteen_values_is_refused(self):
        values = self.reply_values()[:-1]
        status, printed = self.run_bench(self.fake(self.with_reply(values)))
        self.assertEqual(status, 1)
        self.assertIn(f"holds {len(values)} values, not {self.facts['status.register_count']}", printed)
        self.assertEqual(self.written().header["firmware"], "unknown")

    def test_a_wrong_check_value_is_refused(self):
        values = self.reply_values()
        values[self.facts["status.check_value_position"] - 1] = "+8.88700E+03"
        status, printed = self.run_bench(self.fake(self.with_reply(values)))
        self.assertEqual(status, 1)
        self.assertIn(self.facts.cite("status.check_value"), printed)

    def test_a_value_written_another_way_is_refused(self):
        values = self.reply_values()
        values[1] = "0.0"
        status, printed = self.run_bench(self.fake(self.with_reply(values)))
        self.assertEqual(status, 1)
        self.assertIn(f"value 2 of the reply, '0.0', is not written {self.facts['data.ascii_number_format']}",
                      printed)

    def test_a_reply_outside_braces_is_refused(self):
        f = self.facts
        text = (f["command.separator"] + " ").join(self.reply_values()) + f["reply.terminator"]
        status, printed = self.run_bench(self.fake([("OUT", 0, self.command_sent())]
                                                   + self.packets_of(text.encode("ascii"))))
        self.assertEqual(status, 1)
        self.assertIn(f"is not one list in {f['command.open']} and {f['command.close']}", printed)

    def test_a_reply_that_is_not_ascii_is_refused(self):
        data = b"\xff" + self.facts["reply.terminator"].encode("ascii")
        status, printed = self.run_bench(self.fake([("OUT", 0, self.command_sent())] + self.packets_of(data)))
        self.assertEqual(status, 1)
        self.assertIn("the reply holds bytes that are not ASCII text: ff", printed)

    def test_a_reply_with_no_end_in_its_packets_is_refused(self):
        filler = [("IN", 1000, bytes(self.facts["usb.packet_size"]))] * (bench.MAX_PACKETS + 1)
        fake = self.fake([("OUT", 0, self.command_sent())] + filler)
        status, printed = self.run_bench(fake)
        self.assertEqual(status, 1)
        self.assertIn(f"no end of reply in {bench.MAX_PACKETS} packets", printed)
        self.assertEqual(len(fake.remaining()), 1)

    def test_a_short_packet_is_named_and_the_reply_still_read(self):
        status, printed = self.run_bench(self.fake(self.with_reply(self.reply_values(), size=48)))
        self.assertEqual(status, 1)
        self.assertIn("a packet of 48 bytes", printed)
        self.assertNotEqual(self.written().header["firmware"], "unknown")

    # Where the trace goes

    def test_never_writes_over_a_file(self):
        self.out.write_bytes(b"kept\n")
        fake = self.fake()
        status, printed = self.run_bench(fake)
        self.assertEqual(status, 1)
        self.assertIn("never writes over a file", printed)
        self.assertEqual(self.out.read_bytes(), b"kept\n")
        self.assertEqual(fake.opened, 0, "the device was opened before the refusal")

    def test_never_writes_among_the_fixtures(self):
        out = self.root / "protocol" / "fixtures" / "first-contact.trace"
        status, printed = self.run_bench(self.fake(), out=out)
        self.assertEqual(status, 1)
        self.assertIn("holds fixtures only", printed)
        self.assertFalse(out.exists())

    def test_a_trace_from_the_fake_never_goes_among_the_recordings(self):
        out = self.root / "protocol" / "traces" / "first-contact.trace"
        status, printed = self.run_bench(self.fake(), out=out)
        self.assertEqual(status, 1)
        self.assertIn("is not a recording", printed)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
