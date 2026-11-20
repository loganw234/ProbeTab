"""Tests of the bench script's CH1 reading, live reading and descriptors, against the fake backend.

    python -I -B tools/bench/test_ch1.py

tools/check.py runs this as part of its bench check. Each test works in a scratch folder
holding a copy of the facts file. The variants are made from protocol/fixtures/ch1-reading.trace
by changing its own replies; a test whose variant holds fewer commands than the script would send
fails on the fake's Mismatch, which is how a reset the guard should have refused shows up.
"""
import argparse
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
from fake_backend import IN_ADDRESS, OUT_ADDRESS, FakeLabPro, channels  # noqa: E402

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


class Command1(Bench):
    """--operation and --order: what Command 1 sends, and what the fake's model of a unit makes of it."""

    def command_1(self, *parameters):
        """Command 1 in the s-cr framing, built here from the facts' strings and numbers."""
        f = self.facts
        numbers = (f["command.channel_setup"], *parameters)
        return (f["command.prefix"] + f["command.open"] + f["command.separator"].join(str(n) for n in numbers)
                + f["command.close"] + f["command.serial_terminator"]).encode("ascii")

    def exchanges_with(self, sent):
        """The CH1 fixture's exchanges, with Command 1 replaced by sent."""
        exchanges = self.exchanges()
        self.assertEqual(exchanges[3][0], self.command_1(self.facts["channel.ch1"],
                                                         self.facts["channel.operation_auto_id"]))
        exchanges[3][0] = sent
        return exchanges

    def command_1_sent(self):
        """Command 1, the one OUT of the trace the run wrote whose number is Command 1's."""
        f = self.facts
        start = f["command.prefix"] + f["command.open"] + str(f["command.channel_setup"]) + f["command.separator"]
        outs = [data for direction, _, data in self.written().transfers
                if direction == "OUT" and data.decode("ascii").startswith(start)]
        self.assertEqual(len(outs), 1)
        return outs[0]

    def test_the_voltage_operation_is_sent_by_its_fact(self):
        f = self.facts
        sent = self.command_1(f["channel.ch1"], f["channel.operation_voltage_0_5"])
        self.assertNotEqual(sent, self.command_1(f["channel.ch1"], f["channel.operation_auto_id"]))
        status, printed = self.run_bench(self.fake(self.exchanges_with(sent)), "--read-ch1", "--operation", "voltage")
        self.assertEqual(status, 0, printed)
        self.assertEqual(self.command_1_sent(), sent)

    def test_auto_id_and_channel_first_are_the_defaults(self):
        f = self.facts
        sent = self.command_1(f["channel.ch1"], f["channel.operation_auto_id"])
        for arguments in ([], ["--operation", "auto-id"], ["--order", "channel-first"]):
            with self.subTest(arguments=arguments):
                self.out = self.root / f"default-{len(arguments)}-{'-'.join(arguments)}.trace"
                status, printed = self.run_bench(self.fake(self.exchanges()), "--read-ch1", *arguments)
                self.assertEqual(status, 0, printed)
                self.assertEqual(self.command_1_sent(), sent)

    def test_operation_first_sends_the_parameters_the_other_way_round(self):
        f = self.facts
        first = self.command_1(f["channel.ch1"], f["channel.operation_voltage_0_5"])
        other = self.command_1(f["channel.operation_voltage_0_5"], f["channel.ch1"])
        self.assertNotEqual(first, other)
        for order, sent in (("channel-first", first), ("operation-first", other)):
            with self.subTest(order=order):
                self.out = self.root / f"{order}.trace"
                status, printed = self.run_bench(self.fake(self.exchanges_with(sent)), "--read-ch1",
                                                 "--operation", "voltage", "--order", order)
                self.assertEqual(status, 0, printed)
                self.assertEqual(self.command_1_sent(), sent)

    def test_operation_first_with_equal_values_sends_the_same_bytes(self):
        """The map's Q5 as it stood: auto-ID's value equals the channel's, so the order cannot show."""
        f = self.facts
        self.assertEqual(f["channel.ch1"], f["channel.operation_auto_id"])
        status, printed = self.run_bench(self.fake(self.exchanges()), "--read-ch1", "--order", "operation-first")
        self.assertEqual(status, 0, printed)
        self.assertEqual(self.command_1_sent(), self.command_1(f["channel.ch1"], f["channel.operation_auto_id"]))

    def play(self, fake):
        """The fake's next exchange, driven as a script would: the OUT it holds, then the packets of any
        reply that follows. Returns those packets."""
        sent = fake.transfers[0][2]
        fake.bulk_write(None, OUT_ADDRESS, 0, sent, 100)
        size, packets = self.facts["usb.packet_size"], []
        while fake.transfers and fake.transfers[0][0] == "IN":
            buffer = array.array("B", bytes(size))
            packets.append(bytes(buffer[:fake.bulk_read(None, IN_ADDRESS, 0, buffer, 100)]))
        return packets

    def test_the_fake_models_page_31s_channels(self):
        """The model's own test: Command 1 for a channel page 31 does not list sets the error register, which
        Command 7 then shows until Command 0 clears it."""
        f = self.facts
        place = f["status.error_position"] - 1
        # Every number page 31 gives, typed here on purpose as a second reading of the page, then the
        # numbers just past the ends of its rows, and the 0 to 5 V operation's number, which the
        # order test sends as a channel. The fake reads its channels from the facts, so a wrong row
        # there fails here.
        listed = (0, 1, 2, 3, 4, 11, 12, 21, 22, 31, 32)
        outside = (5, 10, 13, 14, 20, 23, 30, 33)
        for channel, held in [(number, True) for number in listed] + [(number, False) for number in outside]:
            with self.subTest(channel=channel):
                exchanges = self.exchanges()
                fake = self.fake([[self.command_1(channel, f["channel.operation_auto_id"]), []], exchanges[0],
                                  exchanges[1], exchanges[2]], command_1_errors=True)
                self.play(fake)
                shown = float(self.values_in(self.play(fake))[place])
                self.assertEqual(shown != 0, not held, f"channel {channel}: error register {shown}")
                self.play(fake)  # Command 0
                self.assertEqual(float(self.values_in(self.play(fake))[place]), 0, "Command 0 did not clear it")

    def test_the_model_is_off_unless_a_test_asks(self):
        f = self.facts
        exchanges = self.exchanges()
        fake = self.fake([[self.command_1(14, 1), []], exchanges[0]])
        self.play(fake)
        self.assertEqual(float(self.values_in(self.play(fake))[f["status.error_position"] - 1]), 0)

    def test_a_channel_page_31_does_not_list_stops_the_run_and_the_trace_keeps_the_bytes(self):
        f = self.facts
        wrong = self.command_1(f["channel.operation_voltage_0_5"], f["channel.ch1"])
        fake = self.fake(self.exchanges_with(wrong)[:5], command_1_errors=True)
        status, printed = self.run_bench(fake, "--read-ch1", "--operation", "voltage", "--order", "operation-first")
        self.assertEqual(status, 1)
        self.assertIn(f"after Command 1 ({f.cite('status.error_position')})", printed)
        self.assertEqual(self.command_1_sent(), wrong)

    def test_the_order_page_31_gives_draws_no_error_in_the_model(self):
        f = self.facts
        right = self.command_1(f["channel.ch1"], f["channel.operation_voltage_0_5"])
        fake = self.fake(self.exchanges_with(right), command_1_errors=True)
        status, printed = self.run_bench(fake, "--read-ch1", "--operation", "voltage")
        self.assertEqual(status, 0, printed)
        self.assertEqual(fake.remaining(), [])

    def test_the_models_channels_are_read_as_the_facts_file_writes_them(self):
        # Made-up rows, not the facts: one number, two joined by a comma, and a range.
        rows = {"one": "0", "two": "11, 12", "range": "1 - 4"}
        self.assertEqual(channels(rows, rows=tuple(rows)), frozenset({0, 1, 2, 3, 4, 11, 12}))

    def test_the_models_channels_hold_ch1_and_not_the_voltage_operation(self):
        # The order test above rests on both: CH1's number is a channel page 31's table gives,
        # and the 0 to 5 V operation's number, sent where the channel goes, is not.
        held = channels(self.facts)
        self.assertIn(self.facts["channel.ch1"], held)
        self.assertNotIn(self.facts["channel.operation_voltage_0_5"], held)


class Numbers(Bench):
    """--applied and --meter, and the options that go only with --read-ch1."""

    BAD = ("1e3", "1E3", "1,5", "abc", "-", ".5", "5.", "+1", "--1", "-.5", "1.2.3", "", " 1", "1 ", "1\n", "1_0",
           "0x1", "nan", "inf", "١", "1" * 13, "-" + "1" * 12, "0." + "1" * 11)
    GOOD = ("0", "1", "-1", "1.25", "-0.5", "00.10", "1" * 12, "-" + "1" * 11, "0." + "1" * 10)

    def test_the_rule_takes_only_a_plain_number_of_twelve_characters_at_most(self):
        for text in self.GOOD:
            with self.subTest(good=text):
                self.assertEqual(bench.volts(text), text)
        for text in self.BAD:
            with self.subTest(bad=text), self.assertRaises(argparse.ArgumentTypeError):
                bench.volts(text)

    def test_a_number_that_does_not_fit_is_refused_before_any_device_is_opened(self):
        for option in ("--applied", "--meter"):
            for text in self.BAD:
                with self.subTest(option=option, text=text), self.assertRaises(SystemExit) as stopped:
                    fake = self.fake([])
                    try:
                        bench.main(["--out", str(self.out), "--read-ch1", f"{option}={text}"], backend=fake,
                                   stdout=io.StringIO(), root=self.root)
                    finally:
                        self.assertEqual(fake.opened, 0)
                        self.assertFalse(self.out.exists())
                self.assertEqual(stopped.exception.code, 2)

    def test_the_options_for_read_ch1_are_refused_without_it(self):
        for arguments in (["--operation", "voltage"], ["--operation", "auto-id"], ["--order", "operation-first"],
                          ["--order", "channel-first"], ["--applied", "1.25"], ["--meter", "1.25"],
                          ["--applied", "1.25", "--meter", "1.24"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as stopped:
                fake = self.fake([])
                try:
                    bench.main(["--out", str(self.out), *arguments], backend=fake, stdout=io.StringIO(), root=self.root)
                finally:
                    self.assertEqual(fake.opened, 0)
            self.assertEqual(stopped.exception.code, 2)

    def test_the_applied_voltage_and_the_meter_go_into_the_note_as_typed(self):
        note = "Command 7 framed as s-cr"
        for arguments, expected in ((["--applied", "1.25"], note + "; applied 1.25 V"),
                                    (["--meter", "-0.50"], note + "; meter -0.50 V"),
                                    (["--applied", "1.25", "--meter", "00.10"], note + "; applied 1.25 V; meter 00.10 V"),
                                    ([], note)):
            with self.subTest(arguments=arguments):
                self.out = self.root / f"note-{len(arguments)}-{'-'.join(arguments)}.trace"
                status, printed = self.run_bench(self.fake(self.exchanges()), "--read-ch1", *arguments)
                self.assertEqual(status, 0, printed)
                self.assertEqual(self.written().header["note"], expected)

    def test_the_numbers_follow_the_text_the_script_wrote_before(self):
        status, printed = self.run_bench(self.fake(self.exchanges(), configured=False), "--read-ch1",
                                         "--applied", "2.5", "--meter", "2.49")
        self.assertEqual(status, 0, printed)
        note = self.written().header["note"]
        self.assertTrue(note.startswith("Command 7 framed as s-cr; pyusb could not read"), note)
        self.assertTrue(note.endswith("before it; applied 2.5 V; meter 2.49 V"), note)

    def test_the_numbers_are_kept_when_the_run_is_refused(self):
        flag = self.facts["status.unretrieved_data_flag"]
        fake = self.fake([self.status_exchange(self.facts["status.state_idle"] + flag)])
        status, printed = self.run_bench(fake, "--read-ch1", "--applied", "1.25")
        self.assertEqual(status, 1)
        self.assertEqual(self.written().header["note"], "Command 7 framed as s-cr; applied 1.25 V")


class StateLine(Bench):
    """The line every run prints after its first Command 7."""

    LABELS = {"status.state_idle": "idle", "status.state_armed": "armed", "status.state_busy": "busy",
              "status.state_done": "done", "status.state_self_test": "self-test",
              "status.state_initializing": "initializing"}

    def test_every_state_and_flag_is_named_without_read_ch1(self):
        f = self.facts
        for name, label in self.LABELS.items():
            for quick in (False, True):
                for unretrieved in (False, True):
                    state = f[name] + quick * f["status.quicksetup_flag"] + unretrieved * f["status.unretrieved_data_flag"]
                    expected = (f"state: {label}; QuickSetup flag {'set' if quick else 'clear'}; "
                                f"unretrieved-data flag {'set' if unretrieved else 'clear'}")
                    with self.subTest(state=state):
                        self.out = self.root / f"state-{state:g}.trace"
                        status, printed = self.run_bench(self.fake([self.status_exchange(state)]))
                        self.assertEqual(status, 0, printed)
                        self.assertEqual([line for line in printed.splitlines() if line.startswith("state: ")],
                                         [expected])

    def test_a_state_no_fact_gives_is_printed_as_such_and_the_run_goes_on(self):
        status, printed = self.run_bench(self.fake([self.status_exchange(7)]))
        self.assertEqual(status, 0, printed)
        self.assertIn("is no state page 45 gives", printed)
        self.assertIn("the run goes on", printed)
        self.assertNotIn("refused", printed)
        self.assertEqual(len(self.written().transfers), 5)

    def test_with_read_ch1_the_guard_still_refuses_it_once(self):
        status, printed = self.run_bench(self.fake([self.status_exchange(7)]), "--read-ch1")
        self.assertEqual(status, 1)
        self.assertEqual(printed.count("is no state page 45 gives"), 1)
        self.assertNotIn("the run goes on", printed)

    def test_the_line_comes_after_the_values_and_before_the_reset(self):
        status, printed = self.run_bench(FakeLabPro(self.fixture(), self.facts, CH1), "--read-ch1")
        self.assertEqual(status, 0, printed)
        lines = printed.splitlines()
        line = next(place for place, text in enumerate(lines) if text.startswith("state: "))
        self.assertEqual(lines[line], "state: idle; QuickSetup flag clear; unretrieved-data flag clear")
        self.assertLess(max(place for place, text in enumerate(lines) if text.startswith("  ")), line)
        self.assertLess(line, next(place for place, text in enumerate(lines) if "resetting it" in text))

    def test_a_run_whose_command_7_draws_no_reply_prints_no_state(self):
        status, printed = self.run_bench(self.fake([[self.exchanges()[0][0], []]]))
        self.assertEqual(status, 1)
        self.assertNotIn("state: ", printed)


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
