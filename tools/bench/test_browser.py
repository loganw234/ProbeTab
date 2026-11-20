"""Tests of the bench page's Python side: the converter from the page's record to a trace, the
server that serves the page, and the constants the page keeps in step with the bench script and
the trace format.

    python -I -B tools/bench/test_browser.py

tools/check.py runs this as part of its bench check. The records are made here from
protocol/fixtures/ch1-reading.trace, as the page would save them. The server serves a scratch
folder laid out as app/ is.
"""
import http.client
import io
import json
import re
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import from_browser  # noqa: E402
import labpro_bench as bench  # noqa: E402
import serve  # noqa: E402
import traces  # noqa: E402

REPO = HERE.parent.parent
CH1 = "protocol/fixtures/ch1-reading.trace"


def fixture():
    return traces.parse((REPO / CH1).read_bytes().decode("utf-8"))


def record(**changes):
    """A record of the CH1 fixture's transfers, as the page saves one, with changes."""
    made = {
        "format": from_browser.FORMAT, "date": "2026-11-20T10:15:00-07:00", "os": "macOS 15.1.0",
        "stack": "Google Chrome 131.0.6778.86, WebUSB", "firmware": "+6.01120E+00", "form": "s-cr",
        "manufacturer": "A Maker", "product": "A Product", "serial": "ABC*****XY", "refusals": [], "findings": [],
        "transfers": [{"direction": direction, "ms": micros / 1000, "bytes": data.hex(" ")}
                      for direction, micros, data in fixture().transfers],
    }
    made.update(changes)
    return made


class Converter(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="probetab-browser-"))
        (self.root / "protocol" / "fixtures").mkdir(parents=True)
        self.out = self.root / "browser.trace"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_converter(self, given, out=None):
        path = self.root / "record.json"
        path.write_bytes(given if isinstance(given, bytes) else json.dumps(given).encode("utf-8"))
        printed = io.StringIO()
        status = from_browser.main([str(path), "--out", str(out or self.out)], stdout=printed, root=self.root)
        return status, printed.getvalue()

    def written(self):
        return traces.parse(self.out.read_bytes().decode("utf-8"))

    def test_writes_the_fixture_s_transfers_as_a_trace(self):
        status, printed = self.run_converter(record())
        self.assertEqual(status, 0, printed)
        trace = self.written()
        self.assertEqual(trace.kind, "trace")
        self.assertEqual(trace.transfers, fixture().transfers)
        self.assertEqual({key: trace.header[key] for key in ("date", "os", "stack", "firmware", "manufacturer", "product",
                                                              "serial")},
                         {"date": "2026-11-20T10:15:00-07:00", "os": "macOS 15.1.0",
                          "stack": "Google Chrome 131.0.6778.86, WebUSB", "firmware": "+6.01120E+00",
                          "manufacturer": "A Maker", "product": "A Product", "serial": "ABC*****XY"})
        self.assertIn("framed as s-cr", trace.header["note"])
        self.assertNotIn(b"\r", self.out.read_bytes())

    def test_times_become_whole_microseconds(self):
        transfers = [{"direction": "OUT", "ms": 0, "bytes": "73"}, {"direction": "IN", "ms": 0.0004, "bytes": ""},
                     {"direction": "IN", "ms": 1.2346, "bytes": "7b 7d"}]
        status, printed = self.run_converter(record(transfers=transfers))
        self.assertEqual(status, 0, printed)
        self.assertEqual([micros for _, micros, _ in self.written().transfers], [0, 0, 1235])

    def test_times_that_decrease_are_refused(self):
        transfers = [{"direction": "OUT", "ms": 0, "bytes": "73"}, {"direction": "IN", "ms": 5, "bytes": "7b"},
                     {"direction": "IN", "ms": 4.9, "bytes": "7d"}]
        status, printed = self.run_converter(record(transfers=transfers))
        self.assertEqual(status, 1)
        self.assertIn("transfer 3's time 4.9 ms comes before the one before it, 5 ms", printed)
        self.assertFalse(self.out.exists())

    def test_the_serial_is_masked_again_by_the_trace_rule(self):
        for number, (given, kept) in enumerate((("ABC12345XY", "ABC*****XY"), ("AB", "**"), ("  ", "none"),
                                                ("unreadable", "unreadable"))):
            with self.subTest(given=given):
                self.out = self.root / f"serial-{number}.trace"
                status, printed = self.run_converter(record(serial=given))
                self.assertEqual(status, 0, printed)
                self.assertEqual(self.written().header["serial"], kept)

    def test_device_strings_follow_the_trace_rule(self):
        status, printed = self.run_converter(record(manufacturer="  A Maker ", product="A" + chr(1) + "B"))
        self.assertEqual(status, 0, printed)
        header = self.written().header
        self.assertEqual((header["manufacturer"], header["product"]), ("A Maker", "unreadable"))

    def test_malformed_records_are_refused_each_for_its_own_reason(self):
        def changed(**changes):
            return json.dumps(record(**changes)).encode("utf-8")

        def transfer_changed(index=0, **changes):
            made = record()
            made["transfers"][index] = {**made["transfers"][index], **changes}
            return json.dumps(made).encode("utf-8")

        without_form = record()
        del without_form["form"]
        last = len(record()["transfers"])
        cases = [
            ("not JSON", b"{", "the record is not JSON"),
            ("not UTF-8", b"\xff", "the record is not UTF-8 text"),
            ("not an object", b"[]", "the record is not a JSON object"),
            # These two say where the message begins: the reader's own refusals pass through unchanged.
            ("NaN", json.dumps(record()).replace('"ms": 0.0', '"ms": NaN', 1).encode("utf-8"),
             "refused: NaN is not a number JSON allows"),
            ("a key twice", json.dumps(record()).replace('"os":', '"os": "x", "os":', 1).encode("utf-8"),
             "refused: the key 'os' appears twice in one object"),
            ("a key missing", json.dumps(without_form).encode("utf-8"), "missing form"),
            ("a key unknown", changed(extra="x"), "unknown extra"),
            ("another format", changed(format="probetab-browser-record 2"), "is not 'probetab-browser-record 1'"),
            ("another form", changed(form="crlf"), "form 'crlf' is none of"),
            ("refusals not a list of text", changed(refusals=[1]), "refusals is not a list of text"),
            ("no transfers", changed(transfers=[]), "transfers is not a list holding at least one transfer"),
            # The last transfer, so that the time's being a boolean is refused before any order is.
            ("a time that is true", transfer_changed(-1, ms=True),
             f"transfer {last}'s time True is not a number of milliseconds"),
            ("a negative time", transfer_changed(ms=-1), "transfer 1's time -1 is not a number of milliseconds"),
            ("a time as text", transfer_changed(ms="0"), "transfer 1's time '0' is not a number of milliseconds"),
            ("another direction", transfer_changed(direction="SIDEWAYS"), "direction 'SIDEWAYS' is neither OUT nor IN"),
            ("bytes in capitals", transfer_changed(bytes="73 7B"), "bytes are not two-digit lower-case hex"),
            ("bytes run together", transfer_changed(bytes="737b"), "bytes are not two-digit lower-case hex"),
            ("a transfer key unknown", transfer_changed(extra=1), "does not hold exactly direction, ms, bytes"),
            ("a date without its offset", changed(date="2026-11-20T10:15:00"), "does not read YYYY-MM-DDTHH:MM:SS+HH:MM"),
            ("a date that is not a date", changed(date="2026-02-30T10:15:00+00:00"), "is not a real date and time"),
            ("an os beginning with a space", changed(os=" macOS"), "the trace format refuses the record's header"),
            ("a stack that is not text", changed(stack=7), "stack is int, not text"),
            ("a time too large for a float", transfer_changed(ms=10 ** 400),
             "transfer 1's time of more than 30 digits is not a number of milliseconds"),
            ("a float time too large for microseconds", transfer_changed(ms=1e306),
             "transfer 1's time 1e+306 ms is too large to write in microseconds"),
            ("JSON nested too deep", b"[" * 100000 + b"]" * 100000, "the record nests deeper than JSON's reader goes"),
            ("a number of 5,000 digits", b'{"format": ' + b"1" * 5000 + b"}", "the record holds a number too long to read"),
        ]
        self.assertIn('"ms": 0.0', json.dumps(record()), "the NaN case needs a first time of 0.0 to replace")
        for name, given, words in cases:
            with self.subTest(name=name):
                status, printed = self.run_converter(given)
                self.assertEqual(status, 1, printed)
                self.assertTrue(printed.startswith("refused: "), printed)
                self.assertIn(words, printed)
                self.assertFalse(self.out.exists())

    def test_never_writes_over_a_file(self):
        self.out.write_bytes(b"kept")
        status, printed = self.run_converter(record())
        self.assertEqual(status, 1)
        self.assertIn("never writes over a file", printed)
        self.assertEqual(self.out.read_bytes(), b"kept")

    def test_a_path_the_system_refuses_is_refused_by_name(self):
        """A stand-in for a path the system refuses, as Windows refuses ::$DATA in a folder's name, which
        other systems take as plain text."""
        with mock.patch.object(from_browser.Path, "exists", side_effect=PermissionError(13, "Permission denied")):
            status, printed = self.run_converter(record())
        self.assertEqual(status, 1)
        self.assertIn("cannot be used: Permission denied", printed)

    def test_a_trace_the_system_will_not_write_is_refused_by_name(self):
        with mock.patch.object(from_browser, "open", create=True, side_effect=OSError(22, "Invalid argument")):
            status, printed = self.run_converter(record())
        self.assertEqual(status, 1)
        self.assertIn("cannot be written: Invalid argument", printed)

    def test_never_writes_among_the_fixtures(self):
        out = self.root / "protocol" / "fixtures" / "browser.trace"
        status, printed = self.run_converter(record(), out=out)
        self.assertEqual(status, 1)
        self.assertIn("protocol/fixtures/ holds fixtures only", printed)
        self.assertFalse(out.exists())

    def test_a_record_from_a_device_is_noted_as_recorded(self):
        status, printed = self.run_converter(record())
        self.assertEqual(status, 0, printed)
        self.assertTrue(self.written().header["note"].startswith("recorded by the bench page in a browser"))

    def test_a_rehearsal_s_record_is_noted_as_a_rehearsal(self):
        status, printed = self.run_converter(record(manufacturer=" " + from_browser.REHEARSAL + " "))
        self.assertEqual(status, 0, printed)
        note = self.written().header["note"]
        self.assertTrue(note.startswith("a rehearsal, not a recording"), note)
        self.assertIn("framed as s-cr", note)

    def test_a_rehearsal_s_record_is_never_written_among_the_recordings(self):
        (self.root / "protocol" / "traces").mkdir()
        out = self.root / "protocol" / "traces" / "browser.trace"
        status, printed = self.run_converter(record(manufacturer=from_browser.REHEARSAL), out=out)
        self.assertEqual(status, 1)
        self.assertIn("protocol/traces/ holds recordings of a LabPro only", printed)
        self.assertFalse(out.exists())
        status, printed = self.run_converter(record(), out=out)
        self.assertEqual(status, 0, printed)


class Server(unittest.TestCase):
    def setUp(self):
        self.app = Path(tempfile.mkdtemp(prefix="probetab-serve-"))
        # Beside the three served folders lie files with types the server does serve, so that only the
        # check of the folders can refuse them.
        for name, data in (("bench/index.html", b"<!doctype html>"), ("collect/index.html", b"<!doctype html>"),
                           ("collect/data.json", b"secret"), ("web/bench/page.js", b"export {};"),
                           ("web/bench/page.ts", b"export {};"), ("web/bench/data.json", b"secret"), ("web/sub/note.js", b""),
                           ("package.json", b"{}"), ("secret.js", b"secret"), ("src/bench/page.js", b"secret"),
                           ("node_modules/typescript/lib/tsc.js", b"secret"), ("secret/index.html", b"secret")):
            (self.app / name).parent.mkdir(parents=True, exist_ok=True)
            (self.app / name).write_bytes(data)
        serve.Handler.quiet = True
        # Named here, so that a fault planted in serve.ADDRESS never opens a port to the network.
        self.server = serve.make_server(self.app, 0, address="127.0.0.1")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        shutil.rmtree(self.app, ignore_errors=True)

    def get(self, path):
        host, port = self.server.server_address[:2]
        connection = http.client.HTTPConnection(host, port, timeout=5)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            return response.status, response.getheader("Content-Type"), response.read()
        finally:
            connection.close()

    def test_it_binds_to_this_computer_alone(self):
        """serve.py's own main(), with a stand-in server that records where it would bind and stops at
        once, so that no port is opened by this test."""
        asked = []

        class StandIn:
            def __init__(self, address, handler):
                asked.append(address)
                self.server_address = address

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                pass

        with mock.patch.object(serve.http.server, "ThreadingHTTPServer", StandIn), \
                mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(serve.main(["--port", "8000"]), 0)
        self.assertEqual(asked, [("127.0.0.1", 8000)])
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_the_page_and_its_modules_are_served_with_their_types(self):
        for path, kind in (("/bench/", "text/html; charset=utf-8"), ("/bench/index.html", "text/html; charset=utf-8"),
                           ("/collect/", "text/html; charset=utf-8"), ("/collect/index.html", "text/html; charset=utf-8"),
                           ("/web/bench/page.js", "text/javascript; charset=utf-8")):
            with self.subTest(path=path):
                status, content_type, _ = self.get(path)
                self.assertEqual((status, content_type), (200, kind))

    def test_anything_else_is_refused(self):
        for path in ("/package.json", "/secret.js", "/src/bench/page.js", "/node_modules/typescript/lib/tsc.js",
                     "/secret/", "/bench/../secret.js", "/bench/%2e%2e/secret.js", "/collect/../secret.js", "/collect/data.json",
                     "/web/..%2fsecret.js",
                     "/web/bench/page.ts", "/web/bench/data.json", "/web/", "/web/sub/", "/", "/missing.js"):
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"secret", body)


def ts_text(name):
    return (REPO / name).read_bytes().decode("utf-8")


def ts_number(text, name):
    found = re.search(r"export const " + name + r"(?::[^=]+)? = (\d+);", text)
    if found is None:
        raise AssertionError(f"no number constant {name} found")
    return int(found.group(1))


def ts_list(text, name):
    found = re.search(r"export const " + name + r"(?::[^=]+)? = \[([^\]]*)\]", text)
    if found is None:
        raise AssertionError(f"no list constant {name} found")
    return [item.strip().strip('"') for item in found.group(1).replace("\n", " ").split(",") if item.strip()]


class Constants(unittest.TestCase):
    """The page's copies of the bench script's choices and the trace format's rules, held to theirs."""

    def test_the_page_waits_and_reads_as_the_bench_script_does(self):
        text = ts_text("app/src/bench/session.ts")
        self.assertEqual(
            [ts_number(text, name) for name in ("QUIET_MS", "RETRIES", "RETRY_MS", "ERROR_EVERY", "MAX_EVERY_SECONDS")],
            [bench.QUIET_MS, bench.RETRIES, bench.RETRY_SECONDS * 1000, bench.ERROR_EVERY, bench.MAX_EVERY])
        self.assertEqual(ts_list(text, "RESETTABLE"), list(bench.RESETTABLE))
        self.assertEqual(ts_list(text, "WAITING"), list(bench.WAITING))

    def test_the_protocol_code_frames_and_reads_as_the_bench_script_does(self):
        text = ts_text("app/src/protocol/status.ts")
        self.assertEqual([ts_number(text, "TIMEOUT_MS"), ts_number(text, "MAX_READS")],
                         [bench.TIMEOUT_MS, bench.MAX_PACKETS])
        self.assertEqual(ts_list(text, "FORMS"), list(bench.FORMS))
        self.assertEqual(from_browser.FORMS, bench.FORMS)

    def test_the_page_masks_the_serial_by_the_trace_rule(self):
        text = ts_text("app/src/bench/record.ts")
        self.assertEqual([int(item) for item in ts_list(text, "SERIAL_KEPT")], list(traces.SERIAL_KEPT))
        self.assertEqual(ts_list(text, "SERIAL_ABSENT"), list(traces.SERIAL_ABSENT))
        self.assertIn(f'export const MASK = "{traces.MASK}";', text)
        self.assertIn(f'export const RECORD_FORMAT = "{from_browser.FORMAT}";', text)

    def test_the_converter_knows_the_rehearsal_s_device_by_its_name(self):
        text = ts_text("app/test/rehearsal-device.ts")
        self.assertIn(f'export const MANUFACTURER = "{from_browser.REHEARSAL}";', text)


if __name__ == "__main__":
    unittest.main()
