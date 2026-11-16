// The in-memory transport, on its own.

import { test } from "node:test";
import assert from "node:assert/strict";
import { MemoryTransport } from "../src/transport/memory.ts";
import { TransportClosed, TransportTimeout } from "../src/transport/transport.ts";

async function opened(): Promise<MemoryTransport> {
  const link = new MemoryTransport();
  await link.open();
  return link;
}

test("a write reaches the device's end as one piece, copied", async () => {
  const link = await opened();
  const data = Uint8Array.of(1, 2, 3);
  assert.equal(await link.write(data), 3);
  data[0] = 9;
  assert.deepEqual(await link.device.read(100), Uint8Array.of(1, 2, 3));
});

test("the device's writes reach the host in order, one piece to a read", async () => {
  const link = await opened();
  link.device.write(Uint8Array.of(1));
  link.device.write(Uint8Array.of(2, 3));
  assert.deepEqual(await link.read(100), Uint8Array.of(1));
  assert.deepEqual(await link.read(100), Uint8Array.of(2, 3));
});

test("a read with nothing to read times out", async () => {
  const link = await opened();
  await assert.rejects(link.read(20), TransportTimeout);
});

test("a read that is waiting gets the bytes when they come", async () => {
  const link = await opened();
  const waiting = link.read(500);
  link.device.write(Uint8Array.of(7));
  assert.deepEqual(await waiting, Uint8Array.of(7));
});

test("a read that timed out does not take bytes that come later", async () => {
  const link = await opened();
  await assert.rejects(link.read(20), TransportTimeout);
  link.device.write(Uint8Array.of(5));
  assert.deepEqual(await link.read(100), Uint8Array.of(5));
});

test("a transport that is not open refuses reads and writes", async () => {
  const link = new MemoryTransport();
  await assert.rejects(link.write(Uint8Array.of(1)), TransportClosed);
  await assert.rejects(link.read(20), TransportClosed);
  await link.open();
  await link.close();
  await assert.rejects(link.read(20), TransportClosed);
});
