# app/

The browser app. It will hold:

- one transport interface with four implementations: WebUSB, Web Serial,
  WebSocket and Web Bluetooth;
- the LabPro protocol, written once;
- sensor recognition and calibration;
- the interface.

It is written in the TypeScript that Node's type stripping accepts: erasable
syntax only, so no enums, namespaces or parameter properties, and imports that
name their `.ts` files. There is no build step yet.

## What is here (2026-11-15)

- [src/transport/transport.ts](src/transport/transport.ts): the transport
  interface. A transport opens, closes, writes bytes, and reads the next bytes
  with a timeout. It knows nothing of what the bytes mean.
- [src/transport/memory.ts](src/transport/memory.ts): an in-memory transport,
  for tests and for a simulated LabPro.
- [src/transport/webusb.ts](src/transport/webusb.ts): the WebUSB transport,
  for a stock LabPro on the computer's own USB port.
  - It closes the device again when it refuses one.
  - It clears a stalled endpoint's halt before it refuses the transfer.
  - It is first exercised on real hardware at Phase 0.
- [src/protocol/status.ts](src/protocol/status.ts): Command 7 and its reply, as
  the bench script sends and reads them, through any transport.
- [src/protocol/facts.ts](src/protocol/facts.ts) reads the facts from
  [src/generated/labpro-facts.ts](src/generated/labpro-facts.ts).
  - `tools/generate.py` makes that file from `protocol/labpro-facts.toml`.
  - Never edit it by hand.
- [test/](test/) runs it all on Node. It uses
  [a simulated LabPro](test/fake-labpro.ts), which replays a fixture from
  `protocol/fixtures/` through [a generated copy](test/generated/fixtures.ts).
  The simulated LabPro shares no code with `src/protocol/`.

## Running the tests

The tests need only Node with type stripping, which Node 22.19 has by default.
From the repository's root:

    node --test app/test/memory.test.ts app/test/status.test.ts app/test/webusb.test.ts

The gate's `app` check runs each `app/test/*.test.ts` alone, in a node process
of its own, and requires node's summary from each. A file that holds no tests,
or exits early, prints none.

The gate's `types` check also needs typescript, which `package.json` pins and
`package-lock.json` locks to its hash. From this folder:

    npm ci --ignore-scripts

That installs the one package into `node_modules/`, which git ignores. The
types check reads `src/` only. The tests would need Node's own types, which are
not installed.

## Limits

- **The tests run on Node, not in a browser.** The WebUSB transport runs
  against a simulated device. Both are written from the lead's knowledge of
  the WebUSB API, not checked against its specification here.
- **The WebUSB declarations in `webusb.ts` are this project's own.**
  TypeScript's DOM library has none. A mistake in them would not be caught
  before Phase 0.
- **On Windows, a browser may reach a stock LabPro only with the WinUSB driver
  bound to it.** The outline names this as a risk, and Phase 0 measures it.
- **Some constants are kept in step with the bench script by hand.**
  `TIMEOUT_MS`, `MAX_READS` and the four framings of Command 7 match
  `tools/bench/labpro_bench.py`'s, and no gate compares them. They are the
  scripts' own choices, not facts about the LabPro.
- **A WebUSB read that times out cannot be cancelled.** It stays pending, and
  the next read waits on it. Whether a LabPro ever answers late is for the
  bench to show.
- **The simulated LabPro is the lead's model, built from a fixture.** Passing
  tests show the app agrees with that model, not with a LabPro.
- **USB pads a reply's last packet** (page 23 of the manual). The protocol
  code stops at the reply's end and does not look at what follows it. Whether
  the bridge passes that padding on is for the bridge's design to say.

Its licence is the one the folder table in [README.md](../README.md) gives it.
