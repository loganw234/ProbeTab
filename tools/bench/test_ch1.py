"""Tests of the bench script's CH1 reading, live reading and descriptors, against the fake backend.

    python -I -B tools/bench/test_ch1.py

tools/check.py runs this as part of its bench check. Each test works in a scratch folder
holding a copy of the facts file. The variants are made from protocol/fixtures/ch1-reading.trace
by changing its own replies; a test whose variant holds fewer commands than the script would send
fails on the fake's Mismatch, which is how a reset the guard should have refused shows up.
"""
import argparse
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
from fake_backend import FakeLabPro  # noqa: E402

REPO = HERE.parent.parent
CH1 = "protocol/fixtures/ch1-reading.trace"
STATUS = "protocol/fixtures/status-request.trace"


class Bench(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="probetab-bench-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        for folder in ("protocol/fixtures", "protocol/traces"):
            (self.root / folder).mkdir(parents=True)
        shutil.copyfile(REPO / labpro_facts.FACTS, self.root / labpro_facts.FACTS)
        self.facts = bench.Facts(self.root)
        self.out = self.root / "ch1.trace"
        for name, value in (("RETRY_SECONDS", 0), ("ERROR_EVERY", bench.ERROR_EVERY)):
            self.addCleanup(setattr, bench, name, getattr(bench, name))
            setattr(bench, name, value)

    def fixture(self, name=CH1):
        return traces.parse((REPO / name).read_bytes().decode("utf-8"))

    def exchanges(self):
        """The CH1 fixture as exchanges: each OUT, with the INs after it."""
        result = []
        for direction, _, data in self.fixture().transfers:
            if direction == "OUT":
                result.append([data, []])
            else:
                result[-1][1].append(data)
        return result

    def fake(self, exchanges, **changes):
        transfers = []
        for out, ins in exchanges:
            transfers.append(("OUT", 0, out))
            transfers += [("IN", 0, data) for data in ins]
        return FakeLabPro(traces.Trace("fixture", {}, transfers), self.facts, "a test's exchanges", **changes)

    def run_bench(self, fake, *arguments):
        printed = io.StringIO()
        status = bench.main(["--out", str(self.out), *arguments], backend=fake, stdout=printed, root=self.root)
        return status, printed.getvalue()

    def written(self):
        return traces.parse(self.out.read_bytes().decode("utf-8"))

    def values_in(self, ins):
        """The values of a reply, read here without the script's help."""
        data = b"".join(ins)
        text = data[:data.index(self.facts["reply.terminator"].encode("ascii"))].decode("ascii").strip()
        inner = text[len(self.facts["command.open"]):-len(self.facts["command.close"])]
        return [value.strip() for value in inner.split(self.facts["command.separator"])]

    def packets(self, values):
        f = self.facts
        text = (f["command.open"] + " " + (f["command.separator"] + " ").join(values) + f["command.close"]
                + f["reply.terminator"])
        data = text.encode("ascii")
        data += bytes(-len(data) % f["usb.packet_size"])
        size = f["usb.packet_size"]
        return [data[i:i + size] for i in range(0, len(data), size)]

    def status_ins(self, state=None, error=None):
        """A reply to Command 7 like the fixture's, with its system state or error register changed."""
        values = self.values_in(self.exchanges()[0][1])
        if state is not None:
            values[self.facts["status.system_state_position"] - 1] = f"{state:+.5E}"
        if error is not None:
            values[self.facts["status.error_position"] - 1] = f"{error:+.5E}"
        return self.packets(values)

    def status_exchange(self, state=None, error=None):
        return [self.exchanges()[0][0], self.status_ins(state, error)]


class ReadCh1(Bench):
    def test_reads_ch1_as_the_fixture_has_it(self):
        fake = FakeLabPro(self.fixture(), self.facts, CH1)
        status, printed = self.run_bench(fake, "--read-ch1")
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [], "the script left part of the fixture unread")
        self.assertEqual([(d, data) for d, _, data in self.written().transfers],
                         [(d, data) for d, _, data in self.fixture().transfers])
        exchanges = self.exchanges()
        for ins in (exchanges[5][1], exchanges[7][1]):
            self.assertIn(self.values_in(ins)[0], printed)

    def test_data_not_yet_retrieved_is_kept_without_discard(self):
        flag = self.facts["status.unretrieved_data_flag"]
        status, printed = self.run_bench(self.fake([self.status_exchange(self.facts["status.state_idle"] + flag)]),
                                         "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn(f"holds data not yet retrieved ({self.facts.cite('status.unretrieved_data_flag')})", printed)
        self.assertEqual([d for d, _, _ in self.written().transfers].count("OUT"), 1)

    def test_discard_resets_a_unit_holding_data(self):
        flag = self.facts["status.unretrieved_data_flag"]
        exchanges = [self.status_exchange(self.facts["status.state_idle"] + flag)] + self.exchanges()[1:]
        status, printed = self.run_bench(self.fake(exchanges), "--read-ch1", "--discard")
        self.assertEqual(status, 0, printed)
        self.assertIn("which --discard loses", printed)

    def test_quicksetup_alone_does_not_stop_the_reset(self):
        state = self.facts["status.state_idle"] + self.facts["status.quicksetup_flag"]
        status, printed = self.run_bench(self.fake([self.status_exchange(state)] + self.exchanges()[1:]), "--read-ch1")
        self.assertEqual(status, 0, printed)

    def test_a_done_unit_is_reset(self):
        state = self.facts["status.state_done"]
        status, printed = self.run_bench(self.fake([self.status_exchange(state)] + self.exchanges()[1:]), "--read-ch1")
        self.assertEqual(status, 0, printed)

    def test_armed_and_busy_are_never_reset(self):
        flag = self.facts["status.unretrieved_data_flag"]
        for name in ("status.state_armed", "status.state_busy"):
            for state in (self.facts[name], self.facts[name] + flag):
                for extra in ([], ["--discard"]):
                    with self.subTest(state=state, extra=extra):
                        self.out = self.root / f"{state}-{len(extra)}.trace"
                        status, printed = self.run_bench(self.fake([self.status_exchange(state)]), "--read-ch1", *extra)
                        self.assertEqual(status, 1)
                        self.assertIn("never an armed or busy one, --discard or not", printed)

    def test_initializing_is_read_again_until_idle(self):
        initializing = self.facts["status.state_initializing"]
        exchanges = ([self.status_exchange(initializing)] * 3 + [self.status_exchange(self.facts["status.state_idle"])]
                     + self.exchanges()[1:])
        fake = self.fake(exchanges)
        status, printed = self.run_bench(fake, "--read-ch1")
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [])

    def test_initializing_that_lasts_is_refused(self):
        initializing = self.facts["status.state_initializing"]
        exchanges = [self.status_exchange(initializing)] * (1 + bench.RETRIES)
        status, printed = self.run_bench(self.fake(exchanges), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn(f"stayed initializing through {bench.RETRIES} more readings", printed)

    def test_a_unit_silent_after_the_reset_is_read_again(self):
        exchanges = self.exchanges()
        silent = [exchanges[0][0], []]
        fake = self.fake(exchanges[:2] + [silent] + exchanges[2:])
        status, printed = self.run_bench(fake, "--read-ch1")
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [])

    def test_a_unit_not_idle_after_the_reset_is_refused(self):
        exchanges = self.exchanges()
        busy = self.status_exchange(self.facts["status.state_busy"])
        status, printed = self.run_bench(self.fake(exchanges[:2] + [busy]), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn("after the reset the unit is not idle: busy", printed)

    def test_a_stray_reply_after_the_reset_is_named_and_kept(self):
        exchanges = self.exchanges()
        exchanges[1][1] = self.packets(["+1.00000E+00"])
        fake = self.fake(exchanges)
        status, printed = self.run_bench(fake, "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn(f"came after Command 0, which page 30 says returns nothing", printed)
        self.assertEqual(fake.remaining(), [])

    def test_an_error_after_channel_setup_stops_it(self):
        exchanges = self.exchanges()
        exchanges[4] = self.status_exchange(error=31)
        status, printed = self.run_bench(self.fake(exchanges[:5]), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn(f"after Command 1 ({self.facts.cite('status.error_position')})", printed)

    def test_an_error_after_mode_1_stops_it(self):
        exchanges = self.exchanges()
        exchanges[8] = self.status_exchange(error=31)
        status, printed = self.run_bench(self.fake(exchanges), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn("after Command 9 in mode 1", printed)

    def test_a_reply_of_two_values_to_command_9_is_refused(self):
        exchanges = self.exchanges()
        value = self.values_in(exchanges[5][1])[0]
        exchanges[5][1] = self.packets([value, value])
        status, printed = self.run_bench(self.fake(exchanges[:6]), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn("Command 9's reply holds 2 values, not one", printed)

    def test_the_live_reading_uses_mode_0(self):
        exchanges = self.exchanges()
        fake = self.fake(exchanges + [exchanges[5]] * 3)
        status, printed = self.run_bench(fake, "--read-ch1", "--every", "0", "--readings", "3")
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [])
        self.assertEqual(printed.count(" s  "), 3)

    def test_the_live_reading_checks_for_errors(self):
        bench.ERROR_EVERY = 2
        exchanges = self.exchanges()
        reading, check = exchanges[5], self.status_exchange()
        fake = self.fake(exchanges + [reading, reading, check, reading])
        status, printed = self.run_bench(fake, "--read-ch1", "--every", "0", "--readings", "3")
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [])

    def silent(self):
        """A Command 7 that draws no reply."""
        return [self.exchanges()[0][0], []]

    def test_an_undecodable_state_is_refused_and_nothing_reset(self):
        status, printed = self.run_bench(self.fake([self.status_exchange(7)]), "--read-ch1", "--discard")
        self.assertEqual(status, 1)
        self.assertIn("is no state page 45 gives", printed)
        self.assertEqual([d for d, _, _ in self.written().transfers].count("OUT"), 1)

    def test_self_test_is_read_again_until_idle(self):
        self_test = self.facts["status.state_self_test"]
        exchanges = ([self.status_exchange(self_test)] * 2 + [self.status_exchange(self.facts["status.state_idle"])]
                     + self.exchanges()[1:])
        fake = self.fake(exchanges)
        status, printed = self.run_bench(fake, "--read-ch1")
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [])

    def test_self_test_that_lasts_is_refused(self):
        exchanges = [self.status_exchange(self.facts["status.state_self_test"])] * (1 + bench.RETRIES)
        status, printed = self.run_bench(self.fake(exchanges), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn(f"stayed self-test through {bench.RETRIES} more readings", printed)

    def test_silence_counts_toward_the_re_reads(self):
        exchanges = [self.status_exchange(self.facts["status.state_initializing"])] + [self.silent()] * bench.RETRIES
        status, printed = self.run_bench(self.fake(exchanges), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn(f"drew no reply on any of {bench.RETRIES} more tries", printed)

    def test_silence_then_idle_before_the_reset_goes_on(self):
        exchanges = ([self.status_exchange(self.facts["status.state_initializing"])] + [self.silent()] * 2
                     + [self.status_exchange(self.facts["status.state_idle"])] + self.exchanges()[1:])
        fake = self.fake(exchanges)
        status, printed = self.run_bench(fake, "--read-ch1")
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [])

    def test_a_unit_holding_data_after_the_reset_is_refused(self):
        state = self.facts["status.state_idle"] + self.facts["status.unretrieved_data_flag"]
        exchanges = self.exchanges()[:2] + [self.status_exchange(state)]
        status, printed = self.run_bench(self.fake(exchanges), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn("after the reset the unit is not idle: idle with data unretrieved", printed)

    def test_a_stray_reply_after_channel_setup_is_named_and_kept(self):
        exchanges = self.exchanges()
        exchanges[3][1] = self.packets(["+1.00000E+00"])
        fake = self.fake(exchanges)
        status, printed = self.run_bench(fake, "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn("came after Command 1, which page 32 says returns nothing", printed)
        self.assertEqual(fake.remaining(), [])

    def test_a_stray_reply_after_command_9_is_named_and_kept(self):
        exchanges = self.exchanges()
        exchanges[5][1] = exchanges[5][1] + self.packets(["+1.00000E+00"])
        fake = self.fake(exchanges)
        status, printed = self.run_bench(fake, "--read-ch1")
        self.assertEqual(status, 1)
        self.assertIn("came after Command 9's reply", printed)
        self.assertEqual(fake.remaining(), [])

    def test_ctrl_c_in_the_live_reading_keeps_the_trace(self):
        exchanges = self.exchanges()
        counting = self.fake(exchanges)
        self.run_bench(counting, "--read-ch1")
        self.out = self.root / "interrupted.trace"
        fake = self.fake(exchanges + [exchanges[5]] * 3, interrupt_at=counting.reads + 1)
        status, printed = self.run_bench(fake, "--read-ch1", "--every", "0", "--readings", "3")
        self.assertEqual(status, 1)
        self.assertIn("stopped by the operator (Ctrl-C)", printed)
        self.assertEqual(len(self.written().transfers), len(self.fixture().transfers) + 1)

    def test_an_unnamed_error_keeps_the_trace_and_goes_on(self):
        exchanges = self.exchanges()
        counting = self.fake(exchanges)
        self.run_bench(counting, "--read-ch1")
        self.out = self.root / "failed.trace"
        planted = RuntimeError("planted error")
        fake = self.fake(exchanges + [exchanges[5]] * 3, interrupt_at=counting.reads + 1, interruption=planted)
        with self.assertRaises(RuntimeError) as raised:
            self.run_bench(fake, "--read-ch1", "--every", "0", "--readings", "3")
        self.assertIs(raised.exception, planted)
        self.assertEqual(len(self.written().transfers), len(self.fixture().transfers) + 1)

    def test_every_is_bounded_and_for_is_not(self):
        self.assertEqual(bench.interval(str(bench.MAX_EVERY)), bench.MAX_EVERY)
        with self.assertRaises(argparse.ArgumentTypeError):
            bench.interval(str(bench.MAX_EVERY + 0.5))
        self.assertEqual(bench.duration(str(10 * bench.MAX_EVERY)), 10 * bench.MAX_EVERY)

    def test_live_options_out_of_range_are_refused_before_anything_is_sent(self):
        for arguments in (["--every", "-1"], ["--every", "nan"], ["--every", "inf"], ["--every", "x"],
                          ["--every", str(bench.MAX_EVERY + 0.5)], ["--every", "1e19"], ["--every", "1e308"],
                          ["--every", "1", "--for", "0"], ["--every", "1", "--readings", "0"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                bench.main(["--out", str(self.out), "--read-ch1", *arguments, *(["--readings", "1"]
                           if "--for" not in arguments and "--readings" not in arguments else [])],
                           backend=self.fake([]), stdout=io.StringIO(), root=self.root)

    def test_the_live_reading_checks_for_errors_every_tenth_reading(self):
        exchanges = self.exchanges()
        reading = exchanges[5]
        fake = self.fake(exchanges + [reading] * bench.ERROR_EVERY + [self.status_exchange(), reading])
        status, printed = self.run_bench(fake, "--read-ch1", "--every", "0", "--readings", str(bench.ERROR_EVERY + 1))
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [])

    def test_the_options_that_need_read_ch1_or_an_end_are_refused(self):
        for arguments in (["--every", "1"], ["--discard"], ["--read-ch1", "--every", "1"], ["--read-ch1", "--readings", "2"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                bench.main(["--out", str(self.out), *arguments], backend=self.fake([]), stdout=io.StringIO(),
                           root=self.root)


class Descriptors(Bench):
    def test_descriptors_go_into_the_header_with_the_serial_masked(self):
        fake = FakeLabPro(self.fixture(STATUS), self.facts, STATUS, manufacturer="A Maker", product="A Product",
                          serial="ABC12345XY")
        status, printed = self.run_bench(fake, "--descriptors")
        self.assertEqual(status, 0, printed)
        header = self.written().header
        self.assertEqual(header["device"], fake.device_bytes().hex(" "))
        self.assertEqual(header["configuration"], fake.configuration_bytes().hex(" "))
        self.assertEqual((header["manufacturer"], header["product"]), ("A Maker", "A Product"))
        self.assertEqual(header["serial"], "ABC*****XY")
        total = len(fake.configuration_bytes())
        self.assertEqual(fake.descriptors_asked[:3], [(1, 0, 18), (2, 0, 9), (2, 0, total)])

    def test_a_device_without_strings_records_none(self):
        fake = FakeLabPro(self.fixture(STATUS), self.facts, STATUS)
        status, printed = self.run_bench(fake, "--descriptors")
        self.assertEqual(status, 0, printed)
        header = self.written().header
        self.assertEqual((header["manufacturer"], header["product"], header["serial"]), ("none", "none", "none"))

    def test_a_short_device_descriptor_is_refused(self):
        fake = FakeLabPro(self.fixture(STATUS), self.facts, STATUS, short_device=True)
        status, printed = self.run_bench(fake, "--descriptors")
        self.assertEqual(status, 1)
        self.assertIn("device descriptor is not well formed", printed)
        self.assertFalse(self.out.exists())

    def test_a_short_configuration_read_is_refused(self):
        fake = FakeLabPro(self.fixture(STATUS), self.facts, STATUS, short_configuration=True)
        status, printed = self.run_bench(fake, "--descriptors")
        self.assertEqual(status, 1)
        self.assertIn("the configuration descriptor's first read gave 8 bytes, not 9", printed)

    def test_a_configuration_whose_total_disagrees_is_refused(self):
        fake = FakeLabPro(self.fixture(STATUS), self.facts, STATUS, bad_total=True)
        status, printed = self.run_bench(fake, "--descriptors")
        self.assertEqual(status, 1)
        self.assertIn("its total length says", printed)

    def test_strings_are_trimmed_and_blank_or_unprintable_ones_named(self):
        fake = FakeLabPro(self.fixture(STATUS), self.facts, STATUS, manufacturer="  A Maker ", product="A\x01B",
                          serial="   ")
        status, printed = self.run_bench(fake, "--descriptors")
        self.assertEqual(status, 0, printed)
        header = self.written().header
        self.assertEqual((header["manufacturer"], header["product"], header["serial"]), ("A Maker", "unreadable", "none"))

    def test_the_serial_keeps_its_first_three_and_last_two_characters(self):
        self.assertEqual(traces.mask_serial("ABC12345XY"), "ABC*****XY")
        self.assertEqual(traces.mask_serial("ABCDEF"), "ABC*EF")
        self.assertEqual(traces.mask_serial("ABCDE"), "*****")

    def test_a_trace_with_its_serial_unmasked_is_refused(self):
        header = {"date": "2026-11-20T10:00:00-07:00", "os": "test", "stack": "test", "firmware": "unknown",
                  "serial": "ABC12345XY"}
        with self.assertRaises(ValueError):
            traces.write("trace", header, [("OUT", 0, b"s")])


class Constants(unittest.TestCase):
    def test_the_counts_the_readme_gives(self):
        """Five re-reads, a second apart, Command 7 every tenth live reading, and --every at most a
        day, as the README says."""
        self.assertEqual((bench.RETRIES, bench.RETRY_SECONDS, bench.ERROR_EVERY, bench.MAX_EVERY), (5, 1.0, 10, 86400))


if __name__ == "__main__":
    unittest.main()
