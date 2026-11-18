// The bench page's rehearsal, on Node: session.ts's steps, called in the order page.ts calls
// them for Connect and then Read CH1, against the rehearsal's stand-in for WebUSB, which replays
// protocol/fixtures/bench-rehearsal.trace through the simulated LabPro. If those steps and the
// rehearsal's script drift apart, the first test fails, as the rehearsal page would meet a
// LabPro that stops answering. page.ts itself does not run here: its order is retyped below, so
// a change to it shows only in the rehearsal page, which is run by hand, as app/README.md says.

import { test } from "node:test";
import assert from "node:assert/strict";
import { FIXTURES } from "./generated/fixtures.ts";
import { MANUFACTURER, PRODUCT, RehearsalUsb, SCRIPT } from "./rehearsal-device.ts";
import { count } from "../src/protocol/facts.ts";
import { NoReply } from "../src/protocol/status.ts";
import { BenchSession, readCh1 } from "../src/bench/session.ts";
import { RecordingTransport, deviceString, maskSerial } from "../src/bench/record.ts";
import { WebUsbTransport, requestLabPro } from "../src/transport/webusb.ts";

const FIXTURE = FIXTURES[SCRIPT];
if (FIXTURE === undefined) {
  throw new Error(`the generated fixtures have no ${SCRIPT}`);
}
/** The live reading the rehearsal page asks for. */
const READINGS = 12;
/** The simulated LabPro's patience here: long enough for each step, short enough that a test
 * that goes wrong ends soon. */
const PATIENCE_MS = 1000;
const LABPRO = { filters: [{ vendorId: count("usb.vendor_id"), productId: count("usb.product_id") }] };

/** Connect as page.ts does it, but with short listens and waits. */
async function connect() {
  const usb = new RehearsalUsb(FIXTURE, PATIENCE_MS);
  const transport = new WebUsbTransport(await requestLabPro(usb));
  const recording = new RecordingTransport(transport);
  await recording.open();
  recording.start();
  const session = new BenchSession(recording, { quietMs: 20, retryMs: 10, timeoutMs: 200 });
  return { usb, recording, session };
}

test("session.ts's steps, in page.ts's order, follow the rehearsal's script to its end: Connect, then Read CH1 "
  + "with 12 live readings",
  async () => {
    const { usb, recording, session } = await connect();
    await session.status(); // Connect sends Command 7
    const first = await session.status(); // Read CH1 sends Command 7, then reads CH1
    const ch1 = await readCh1(session, first, { live: { every: 0, readings: READINGS } });
    assert.equal(ch1.live.length, READINGS);
    assert.equal(ch1.stopped, false);
    assert.deepEqual(session.findings, []);
    await recording.close();
    const labPro = usb.device?.labPro;
    assert.ok(labPro !== undefined);
    await labPro.finished;
    assert.equal(labPro.mismatch, null);
    assert.deepEqual(labPro.remaining, []);
    assert.deepEqual(recording.transfers.map((transfer) => [transfer.direction, transfer.bytes]),
      FIXTURE.transfers.map((transfer) => [transfer.direction, transfer.bytes]));
  });

test("the device names itself as the rehearsal's, so the page's record says where it came from", async () => {
  const device = await new RehearsalUsb(FIXTURE, PATIENCE_MS).requestDevice(LABPRO);
  assert.equal(deviceString(device.manufacturerName), MANUFACTURER);
  assert.equal(deviceString(device.productName), PRODUCT);
  assert.equal(maskSerial(deviceString(device.serialNumber)), "REH******01");
  await device.labPro.finished; // no command comes, so it stops waiting after its patience
  assert.equal(device.labPro.remaining.length, FIXTURE.transfers.length);
});

test("a request that names other IDs is refused, as WebUSB refuses when no device is chosen", async () => {
  const usb = new RehearsalUsb(FIXTURE, PATIENCE_MS);
  const other = { filters: [{ vendorId: count("usb.vendor_id"), productId: count("usb.product_id") + 1 }] };
  await assert.rejects(usb.requestDevice(other), { name: "NotFoundError" });
  assert.equal(usb.device, null);
});

test("a step outside the script meets a simulated LabPro that stops answering", async () => {
  const { usb, recording, session } = await connect();
  await session.status(); // Connect: in the script
  await session.send(count("command.reset")); // the script holds Command 7 next, not Command 0
  const labPro = usb.device?.labPro;
  assert.ok(labPro !== undefined);
  await labPro.finished;
  assert.equal(labPro.mismatch, `the host sent 73 7b 30 7d 0d, where ${SCRIPT} has OUT 73 7b 37 7d 0d`);
  await assert.rejects(session.status(), NoReply);
  await recording.close();
});

test("the device refuses and cancels transfers as WebUSB does", async () => {
  const device = await new RehearsalUsb(FIXTURE, PATIENCE_MS).requestDevice(LABPRO);
  const endpoints = device.configurations[0]?.interfaces[0]?.alternates[0]?.endpoints ?? [];
  const inward = endpoints.find((endpoint) => endpoint.direction === "in");
  const outward = endpoints.find((endpoint) => endpoint.direction === "out");
  assert.ok(inward !== undefined && outward !== undefined);
  await assert.rejects(device.transferIn(inward.endpointNumber, inward.packetSize), { name: "InvalidStateError" });
  await device.open();
  await assert.rejects(device.transferOut(outward.endpointNumber, new Uint8Array([0x73])), { name: "NotFoundError" });
  await device.claimInterface(0);
  await assert.rejects(device.transferIn(outward.endpointNumber, inward.packetSize), { name: "NotFoundError" });
  const waiting = device.transferIn(inward.endpointNumber, inward.packetSize);
  await device.close();
  await assert.rejects(waiting, { name: "AbortError" });
  await device.labPro.finished;
});
