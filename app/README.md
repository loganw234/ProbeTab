# app/

The browser app. It will hold:

- one transport interface with four implementations: WebUSB, Web Serial,
  WebSocket and Web Bluetooth;
- the LabPro protocol, written once;
- sensor recognition and calibration;
- the interface.

It is written in the TypeScript that Node's type stripping accepts: erasable
syntax only, so no enums, namespaces or parameter properties, and imports that
name their `.ts` files. The tests run the `.ts` files as they are. The bench
page runs a build of them, which tsc makes (see [The bench page](#the-bench-page)).

## What is here (2026-11-19)

- [src/transport/transport.ts](src/transport/transport.ts): the transport
  interface. A transport opens, closes, writes bytes, and reads the next bytes
  with a timeout. It knows nothing of what the bytes mean.
- [src/transport/memory.ts](src/transport/memory.ts): an in-memory transport,
  for tests and for a simulated LabPro.
- [src/transport/webusb.ts](src/transport/webusb.ts): the WebUSB transport,
  for a stock LabPro on the computer's own USB port.
  - It closes the device again when it refuses one.
  - It clears a stalled endpoint's halt before it refuses the transfer.
  - It first reached a LabPro on 2026-11-25, in Chrome 158 on Windows with
    WinUSB bound ([the recording](../protocol/traces/2026-11-25-browser.trace)).
    On 2026-11-27 it reached one in Chrome 157 on macOS, with no driver
    installed by the owner's account
    ([the recording](../protocol/traces/2026-11-27-mac-browser-live.trace)).
- [src/protocol/status.ts](src/protocol/status.ts): the commands the bench
  script sends, and their replies, through any transport. These are Command 7,
  Command 0, Command 1 and Command 9, and the system state decoded as page 45
  of the manual gives it.
- [src/protocol/facts.ts](src/protocol/facts.ts) reads the facts from
  [src/generated/labpro-facts.ts](src/generated/labpro-facts.ts).
  - `tools/generate.py` makes that file from `protocol/labpro-facts.toml`.
  - Never edit it by hand.
- [src/bench/](src/bench/) is the bench page's code:
  - [session.ts](src/bench/session.ts) takes the bench script's steps, with its
    refusals and its discard: the status, the guarded reset, channel 1,
    Command 9, and the live reading.
  - [record.ts](src/bench/record.ts) keeps every transfer for the record the
    page saves. It also gives the device's strings, the serial number masked,
    and the platform and browser from the browser's own hints.
  - [page.ts](src/bench/page.ts) is the glue to the page: its buttons, its log
    and its Save.
- [bench/index.html](bench/index.html) is the page, and
  [tsconfig.build.json](tsconfig.build.json) is how it is built.
- [index.html](index.html) is the published site's landing page, written for
  teachers and students. It says what ProbeTab will do, and lists the bench page
  and its rehearsal under "For testers".
- [test/](test/) runs it all on Node. It uses
  [a simulated LabPro](test/fake-labpro.ts), which replays a fixture from
  `protocol/fixtures/` through [a generated copy](test/generated/fixtures.ts).
  The simulated LabPro shares no code with `src/protocol/`.
- The rehearsal ([below](#the-rehearsal)) puts that simulated LabPro under the
  bench page in a browser:
  - [bench/rehearse.html](bench/rehearse.html) shows the bench page in a frame;
  - [test/rehearsal-device.ts](test/rehearsal-device.ts) is the stand-in for
    the browser's WebUSB, and
    [test/rehearsal-install.ts](test/rehearsal-install.ts) puts it in place;
  - [tsconfig.rehearse.json](tsconfig.rehearse.json) is how it is built.
- [mockup/index.html](mockup/index.html) is a picture of what the classroom
  app's page may look like, for the owner to react to. It is visual only: the
  buttons do nothing, and every reading is made up from the formula in its
  comment. A switcher in its banner shows four states (before connecting,
  connected, collecting, finished). The site publishes it at `mockup/`, and the
  landing page does not link it. [test/mockup.test.ts](test/mockup.test.ts) holds that it
  loads nothing from another site in the forms the test reads (its header names
  those it misses), that its table is that formula, and that it says it is a
  mockup. It has not been tried with a screen reader or on a
  Chromebook.
- [collect/index.html](collect/index.html) is the classroom screen, first
  piece: the mockup's look made to work, with **practice readings only**. Every
  reading on it is made up, and it says so in several places, in its file and
  in a kept run it restores. No LabPro is connected by it, and nothing in it is
  evidence about one. Its code is in [src/collect/](src/collect/), and it loads
  its built modules from `web/collect/`:
  - [practice.ts](src/collect/practice.ts) is the practice source, from the
    mockup's formula;
  - [collector.ts](src/collect/collector.ts) is the run's four states and what
    each button does to it, with its clock, storage and questions handed in;
  - [history.ts](src/collect/history.ts) keeps the last run, and the °F choice,
    in `localStorage` (below);
  - [csv.ts](src/collect/csv.ts), [units.ts](src/collect/units.ts),
    [graph.ts](src/collect/graph.ts), [view.ts](src/collect/view.ts) and
    [words.ts](src/collect/words.ts) make the spreadsheet file, convert °C to
    °F, draw the graph as an SVG string, work out what the page shows, and hold
    its words;
  - [page.ts](src/collect/page.ts) is the thin glue to the page. Node does not
    test it.
  - **History** is the last run only, saved after every reading under
    `probetab.collect.lastRun.v1`. A run comes back marked "stopped when the
    page closed" if the tab closed mid-run. Start, Collect another run and
    Clear each ask before discarding it, every time. Readings are kept in
    Celsius as the source gave them, whatever the °F toggle says. Storage that
    is missing or full is told to the person in a line; the page works without
    it. Two tabs open at once share the one run and can overwrite each other's
    (a stated limit). Thirty minutes at one reading a second is about 59,000
    characters of JSON (MEASURED, [collect-history.test.ts](test/collect-history.test.ts)).
  - The site publishes it at `collect/`, and the landing page does not link
    it. `python tools/bench/serve.py` serves it at `/collect/` as well.
    Browsers keep `localStorage` per origin, so the published page and
    `serve.py` each keep their own last run, and a move of the site to another
    domain starts without one.
  - Its tests are `test/collect-*.test.ts`, with
    [collect-fakes.ts](test/collect-fakes.ts) (a storage, a failing storage and
    a clock driven by hand). `collect-page.test.ts` imports the mockup test's
    finder of references to other sites, so the mockup's tests run in its
    process too.

## Running the tests

The tests need only Node with type stripping, which Node 22.19 has by default.
From the repository's root:

    node --test app/test/memory.test.ts app/test/status.test.ts app/test/webusb.test.ts app/test/bench.test.ts app/test/rehearsal.test.ts app/test/collect-data.test.ts app/test/collect-history.test.ts app/test/collect-run.test.ts app/test/collect-view.test.ts app/test/collect-page.test.ts

The gate's `app` check runs each `app/test/*.test.ts` alone, in a node process
of its own, and requires node's summary from each. A file that holds no tests,
or exits early, prints none.

The gate's `types` check also needs typescript, which `package.json` pins and
`package-lock.json` locks to its hash. From this folder:

    npm ci --ignore-scripts

That installs the one package into `node_modules/`, which git ignores. The
types check reads `src/` only. The tests would need Node's own types, which are
not installed.

## The bench page

For Phase 0: the bench script's steps from a browser, over WebUSB, with every
transfer kept.

1. **Build it.** From this folder, with typescript installed as above:

       node node_modules/typescript/bin/tsc -p tsconfig.build.json

   That writes the JavaScript into `web/`, which git ignores. The gate's
   `types` check makes the same build in a scratch folder.
2. **Serve it** to this computer alone. From the repository's root:

       python tools/bench/serve.py

3. **Open** `http://127.0.0.1:8000/bench/` in Chrome or Edge.
   - **Connect** asks the browser for the LabPro, then sends Command 7.
   - **Read CH1** sends Command 7 again, then the bench script's steps. It
     resets the unit only when the unit is idle or done. Data not yet retrieved
     is kept unless Discard is ticked.
   - **A live reading** needs its interval and either a number of readings or a
     number of seconds. Stop ends it between readings.
4. **Save the record.** It downloads as JSON, only when you click Save.
   `tools/bench/from_browser.py` writes a trace from it, as
   [tools/bench/README.md](../tools/bench/README.md) says.

One connection per page: reload the page for another, so that a record is never
replaced unsaved.

## The rehearsal

The bench page in a browser with a simulated LabPro in place of a LabPro, for
use before Phase 0. It shows whether the page's buttons, its log and its Save
work end to end. It shows nothing about a LabPro: the simulated LabPro is the
lead's model, and so is everything it answers.

1. **Build it.** From this folder, after the page's build:

       node node_modules/typescript/bin/tsc -p tsconfig.rehearse.json

   That writes its JavaScript into `web/rehearsal/`.
2. **Serve it** as the page is served: `python tools/bench/serve.py`.
3. **Open** `http://127.0.0.1:8000/bench/rehearse.html`.
   - It shows the bench page, unchanged, in a frame, under a banner.
   - Each time the frame loads, it adds one script to it, which puts
     [the stand-in](test/rehearsal-device.ts) where the browser's WebUSB would
     be.
   - The banner says how far the simulated LabPro has got.
4. **Follow its script:** Connect, then Read CH1 with a live reading of 12
   readings, at any interval.
   - The simulated LabPro replays
     [bench-rehearsal.trace](../protocol/fixtures/bench-rehearsal.trace), and
     stops answering at the first command the fixture does not hold. Reload the
     page for a fresh one.
   - A refusal that sends nothing, such as a live reading with no end, leaves
     the script where it was.

Its device calls itself "ProbeTab rehearsal", so a saved record says where it
came from. `tools/bench/from_browser.py` writes such a record only outside
`protocol/traces/`, with a note saying it is a rehearsal and not a recording.

[test/rehearsal.test.ts](test/rehearsal.test.ts) runs `session.ts`'s steps
against the same stand-in on Node, in the order `page.ts` calls them, so the
gate fails when those steps and the script drift apart. It does not run
`page.ts`, whose order it retypes, so a change to that order shows only in the
rehearsal by hand. The gate does not build the rehearsal, or type-check its two
files in `test/`; tsc does both when it builds the rehearsal.

## The published site

[.github/workflows/pages.yml](../.github/workflows/pages.yml) publishes five
things to GitHub Pages, laid out as this folder is:

- `index.html`, the landing page;
- `bench/`, the bench page and its rehearsal;
- `collect/`, the classroom screen, with practice readings only;
- `web/`, the JavaScript tsc builds for `bench/` and `collect/`;
- `mockup/`, the mockup of the classroom app's page, whose buttons do nothing.

It runs on each push to `main`, and by hand. It runs the app's tests and both
builds first, and deploys only when all of them pass, and only from `main`. A
run by hand on another branch builds and tests, and publishes nothing. Nothing
else of the repository is published there.

The site's domain is set in the repository's Pages settings, not by a file
here. Those settings, and the domain's DNS records, are the owner's.

## Limits

- **The tests run on Node, not in a browser.** The WebUSB transport runs
  against a simulated device.
  - The bench page's steps and its record are tested on Node.
  - Its glue to the page, `page.ts`, is not. The rehearsal ran it in a browser
    on 2026-11-18, by hand, against the simulated LabPro (MEASURED). Against a
    LabPro, it first ran on 2026-11-25, in Chrome 158 on Windows
    ([the recording](../protocol/traces/2026-11-25-browser.trace)), and on
    2026-11-27 in Chrome 157 on macOS
    ([the recording](../protocol/traces/2026-11-27-mac-browser-live.trace)).
- **The WebUSB declarations in `webusb.ts`, and the client-hint declarations in
  `record.ts`, are this project's own.** TypeScript's DOM library has neither.
  They are written from the lead's knowledge of the APIs, not checked against
  their specifications here. They worked in Chrome 158 on Windows and Chrome
  157 on macOS, in the recordings of 2026-11-25 and 2026-11-27. A mistake in a
  part those runs did not use would still not be caught.
- **On Windows, a browser may reach a stock LabPro only with the WinUSB driver
  bound to it.** The outline names this as a risk. With WinUSB bound, Chrome 158
  reached the LabPro on 2026-11-25; without it, a browser was not tried. On
  macOS, Chrome 157 reached it on 2026-11-27 with no driver installed, by the
  owner's account.
- **A school-managed Chromebook may block WebUSB.**
- **The page's copies of the bench script's choices** are held to the script's
  by a bench test, `tools/bench/test_browser.py`:
  - the timeouts;
  - the re-reads;
  - the framings;
  - the guard's states;
  - the serial rule.

  They are the scripts' own choices, not facts about the LabPro.
- **A WebUSB read that times out cannot be cancelled.** It stays pending, and
  the next read waits on it.
  - So a reply more than 2 seconds late is taken as the next command's.
  - The bench page's guard could then act on a stale state, as
    [tools/bench/README.md](../tools/bench/README.md) says of the bench script.
  - Whether a LabPro ever answers late is for the bench to show.
- **A write to the LabPro has no timeout.** A write that never ends cannot be
  stopped from the page, since Stop acts only in a live reading. Reloading the
  page then loses the record, unsaved.
- **Two of the page's inputs are read late, or loosely:**
  - Discard is read when the guard runs, after Command 7's reply, not when Read
    CH1 is pressed.
  - A number box holding text reads as empty, so Read CH1 then runs without a
    live reading. The guard still applies.
- **Each transfer's time** is when the page took it from WebUSB, not when it
  reached the computer.
- **No check holds the page's HTML to its code.** The ids `page.ts` looks up,
  and the built script's path, were checked by hand on 2026-11-16. In the
  rehearsal of 2026-11-18, the page started, which it does only when it finds
  every id, and each button was pressed (MEASURED).
- **A live reading's interval is a wait, not a period.** After each reading's
  reply the page listens 0.3 s for anything more, and only then waits the
  interval, as the bench script does (READ, `tools/bench/labpro_bench.py`). In
  the rehearsal, an interval of 0.5 s gave readings about 0.8 s apart, and 0
  gave them about 0.3 s apart (MEASURED, in a browser pane that was hidden,
  where timers may run late).
- **The transfers table is redrawn when a step ends,** so it does not grow
  during a live reading. The log does (MEASURED, in the rehearsal).
- **Save hands the record to the browser,** which may ask before it saves. In
  the rehearsal, the saved file was the page's bytes exactly (MEASURED,
  SHA-256).
- **A trace's `os` line is what the browser's hints say.** On Windows 11,
  Chromium gave "Windows 15.0.0" (MEASURED, 2026-11-16).
- **The simulated LabPro is the lead's model, built from a fixture.** Passing
  tests show the app agrees with that model, not with a LabPro.
- **USB pads a reply's last packet** (page 23 of the manual). The protocol
  code stops at the reply's end and does not look at what follows it. Whether
  the bridge passes that padding on is for the bridge's design to say.
- **Two paths in `webusb.ts` no test reaches:**
  - its second check that a configuration is active;
  - `close()` dropping a read still pending.
- **Edge cases in opening:**
  - `open()` called twice, or on a device the caller had opened, closes the
    device when it refuses.
  - A `clearHalt` that rejects replaces the refusal's message with its own.

Its licence is the one the folder table in [README.md](../README.md) gives it.
