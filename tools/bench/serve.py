#!/usr/bin/env python3
"""Serve the bench page to this computer alone.

    python tools/bench/serve.py [--port N]

It serves three folders of app/ and nothing else: bench/, the bench page and its
rehearsal (rehearse.html), collect/, the classroom screen, and web/,
the JavaScript that tsc builds from app/src/ (app/README.md says how to build
it). It binds to 127.0.0.1, so no other computer can reach it. Open
http://127.0.0.1:N/bench/ (or /collect/) in Chrome or Edge: WebUSB needs a secure origin, and
Chromium counts 127.0.0.1 as one (BELIEVED, from Chromium's behaviour; Phase 0
shows it).

Each file's type comes from its extension, by this script's own table, never
the system's: Windows' registry can make .js plain text (BELIEVED), and a
browser will not run a module served as text. A path outside the three folders,
a folder without an index.html, or an extension not in the table is answered
404. Ctrl-C stops it.

The port is 8000 unless --port says otherwise; 0 takes any free port.
"""
import argparse
import http.server
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ADDRESS = "127.0.0.1"
SERVED = ("bench", "collect", "web")
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".map": "application/json",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the three folders under its directory, each file by TYPES."""

    quiet = False  # the tests set it, so that their output holds only their results

    def log_message(self, format, *args):
        if not self.quiet:
            super().log_message(format, *args)

    def send_head(self):
        app = Path(self.directory).resolve()
        try:
            full = Path(self.translate_path(self.path)).resolve()
        except OSError:
            full = None
        if full is None or not any(full.is_relative_to(app / folder) for folder in SERVED):
            self.send_error(404, "not served")
            return None
        if full.is_dir():
            if not (full / "index.html").is_file():
                self.send_error(404, "not served")
                return None
        elif full.suffix not in TYPES:
            self.send_error(404, "not served")
            return None
        return super().send_head()

    def guess_type(self, path):
        return TYPES.get(Path(path).suffix, "application/octet-stream")


def make_server(app, port, address=ADDRESS):
    """A server for app's three folders on address and port, not yet serving. Only the tests
    name an address, and they name 127.0.0.1."""
    return http.server.ThreadingHTTPServer((address, port), partial(Handler, directory=str(app)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Serve the bench page to this computer alone.")
    parser.add_argument("--port", type=int, default=8000, help="the port, 8000 unless given; 0 takes any free one")
    args = parser.parse_args(argv)
    app = ROOT / "app"
    try:
        server = make_server(app, args.port)
    except OSError as exc:
        print(f"refused: cannot serve on {ADDRESS}:{args.port}: {exc.strerror or exc}")
        return 1
    host, port = server.server_address[:2]
    if not (app / "web" / "bench" / "page.js").is_file():
        print("app/web/ holds no build of the page yet; app/README.md says how to build it")
    print(f"serving app/bench/, app/collect/ and app/web/ to this computer alone: open http://{host}:{port}/bench/ "
          f"or /collect/ in Chrome or Edge; Ctrl-C stops it")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
