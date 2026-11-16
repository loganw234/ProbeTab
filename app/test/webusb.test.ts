// The WebUSB transport, against a simulated USB device: what a browser's WebUSB would hand it,
// as the lead knows the WebUSB API. Nothing here runs in a browser or touches hardware.

import { test } from "node:test";
import assert from "node:assert/strict";
import { FakeLabPro } from "./fake-labpro.ts";
import { FIXTURES } from "./generated/fixtures.ts";
import { cite, count } from "../src/protocol/facts.ts";
import { requestStatus } from "../src/protocol/status.ts";
import { MemoryTransport } from "../src/transport/memory.ts";
import { TransportClosed, TransportRefused, TransportTimeout } from "../src/transport/transport.ts";
import {
  WebUsbTransport,
  requestLabPro,
  type USBConfigurationLike,
  type USBDeviceLike,
  type USBEndpointLike,
  type USBInTransferResultLike,
  type USBLike,
  type USBOutTransferResultLike,
} from "../src/transport/webusb.ts";

interface Placed extends USBEndpointLike {
  readonly interfaceNumber?: number;
  readonly alternateSetting?: number;
}

interface Options {
  readonly endpoints?: readonly Placed[];
  readonly configured?: boolean;
  readonly unconfiguredAs?: null | undefined;
  readonly outStatus?: "ok" | "stall";
  readonly take?: number;
  readonly releaseFails?: boolean;
  readonly link?: MemoryTransport;
}

function endpoint(direction: "in" | "out", endpointNumber: number, packetSize = count("usb.packet_size"),
  type: USBEndpointLike["type"] = "bulk"): Placed {
  return { endpointNumber, direction, type, packetSize };
}

/** A simulated USB device. With a link, it carries transfers to and from the link's device end. */
class FakeDevice implements USBDeviceLike {
  readonly vendorId = count("usb.vendor_id");
  readonly productId = count("usb.product_id");
  readonly configurations: readonly USBConfigurationLike[];
  readonly calls: string[] = [];
  readonly sent: { endpointNumber: number; data: Uint8Array }[] = [];
  readonly lengths: number[] = [];
  #opened = false;
  #configuration: USBConfigurationLike | null | undefined;
  #waiting: { resolve: (result: USBInTransferResultLike) => void; reject: (error: Error) => void }[] = [];
  #options: Options;

  constructor(options: Options = {}) {
    this.#options = options;
    const endpoints = options.endpoints ?? [endpoint("in", 2), endpoint("out", 1)];
    const numbers = [...new Set(endpoints.map((placed) => placed.interfaceNumber ?? 0))];
    const interfaces = numbers.map((interfaceNumber) => {
      const here = endpoints.filter((placed) => (placed.interfaceNumber ?? 0) === interfaceNumber);
      // The endpoints' own settings come first, so that choosing the first alternate is not the
      // same as choosing alternate setting 0; setting 0 is always there, as in a real device.
      const settings = [...new Set([...here.map((placed) => placed.alternateSetting ?? 0), 0])];
      return {
        interfaceNumber,
        alternates: settings.map((alternateSetting) => ({
          alternateSetting,
          endpoints: here.filter((placed) => (placed.alternateSetting ?? 0) === alternateSetting),
        })),
      };
    });
    this.configurations = [{ configurationValue: 1, interfaces }];
    this.#configuration = options.configured === false
      ? (options.unconfiguredAs === undefined && "unconfiguredAs" in options ? undefined : null)
      : this.configurations[0];
  }

  get opened(): boolean {
    return this.#opened;
  }

  get configuration(): USBConfigurationLike | null | undefined {
    return this.#configuration;
  }

  async open(): Promise<void> {
    this.calls.push("open");
    this.#opened = true;
  }

  async close(): Promise<void> {
    this.calls.push("close");
    this.#opened = false;
    for (const waiter of this.#waiting.splice(0)) {
      waiter.reject(new Error("the device was closed"));
    }
  }

  async selectConfiguration(configurationValue: number): Promise<void> {
    this.calls.push(`selectConfiguration ${configurationValue}`);
    this.#configuration = this.configurations.find((c) => c.configurationValue === configurationValue) ?? null;
  }

  async claimInterface(interfaceNumber: number): Promise<void> {
    this.calls.push(`claimInterface ${interfaceNumber}`);
  }

  async releaseInterface(interfaceNumber: number): Promise<void> {
    this.calls.push(`releaseInterface ${interfaceNumber}`);
    if (this.#options.releaseFails) {
      throw new Error("planted release failure");
    }
  }

  async clearHalt(direction: "in" | "out", endpointNumber: number): Promise<void> {
    this.calls.push(`clearHalt ${direction} ${endpointNumber}`);
  }

  transferIn(endpointNumber: number, length: number): Promise<USBInTransferResultLike> {
    this.calls.push(`transferIn ${endpointNumber}`);
    this.lengths.push(length);
    const link = this.#options.link;
    if (link !== undefined) {
      return link.read(5000).then((data) => ({ status: "ok", data: new DataView(data.buffer, data.byteOffset, data.byteLength) }));
    }
    return new Promise((resolve, reject) => this.#waiting.push({ resolve, reject }));
  }

  async transferOut(endpointNumber: number, data: Uint8Array): Promise<USBOutTransferResultLike> {
    this.calls.push(`transferOut ${endpointNumber}`);
    this.sent.push({ endpointNumber, data: data.slice() });
    if (this.#options.link !== undefined) {
      await this.#options.link.write(data);
    }
    return { bytesWritten: this.#options.take ?? data.length, status: this.#options.outStatus ?? "ok" };
  }

  /** Completes the oldest pending transfer in with result. */
  complete(result: USBInTransferResultLike): void {
    const waiter = this.#waiting.shift();
    assert.ok(waiter !== undefined, "no transfer in is pending");
    waiter.resolve(result);
  }

  /** Completes the oldest pending transfer in with data. */
  deliver(data: Uint8Array): void {
    this.complete({ status: "ok", data: new DataView(data.buffer.slice(0)) });
  }

  /** Fails the oldest pending transfer in. */
  fail(error: Error): void {
    const waiter = this.#waiting.shift();
    assert.ok(waiter !== undefined, "no transfer in is pending");
    waiter.reject(error);
  }
}

async function opened(options: Options = {}): Promise<{ device: FakeDevice; transport: WebUsbTransport }> {
  const device = new FakeDevice(options);
  const transport = new WebUsbTransport(device);
  await transport.open();
  return { device, transport };
}

function refusedNaming(pattern: RegExp) {
  return (error: unknown) => {
    assert.ok(error instanceof TransportRefused, `${String(error)} is not a TransportRefused`);
    assert.match(error.message, pattern);
    return true;
  };
}

function transfersIn(device: FakeDevice): number {
  return device.calls.filter((call) => call.startsWith("transferIn")).length;
}

test("requestLabPro asks the browser for the facts' vendor and product IDs", async () => {
  let asked: unknown;
  const usb: USBLike = {
    requestDevice: async (options) => {
      asked = options;
      return new FakeDevice();
    },
  };
  await requestLabPro(usb);
  assert.deepEqual(asked, { filters: [{ vendorId: count("usb.vendor_id"), productId: count("usb.product_id") }] });
});

test("open claims the interface that holds the bulk endpoints, wherever they are", async () => {
  const { device, transport } = await opened({
    endpoints: [{ ...endpoint("in", 6), interfaceNumber: 2 }, { ...endpoint("out", 3), interfaceNumber: 2 }],
  });
  assert.deepEqual(device.calls, ["open", "claimInterface 2"]);
  assert.equal(transport.configuredHere, false);
  assert.equal(await transport.write(Uint8Array.of(1, 2)), 2);
  assert.equal(device.sent[0]?.endpointNumber, 3);
  const reading = transport.read(100);
  device.deliver(Uint8Array.of(9));
  assert.deepEqual(await reading, Uint8Array.of(9));
  assert.ok(device.calls.includes("transferIn 6"));
});

test("open selects the first configuration when none is active, and says so", async () => {
  const { device, transport } = await opened({ configured: false });
  assert.deepEqual(device.calls.slice(0, 2), ["open", "selectConfiguration 1"]);
  assert.equal(transport.configuredHere, true);
});

test("open treats a configuration reported as undefined as none", async () => {
  const { device, transport } = await opened({ configured: false, unconfiguredAs: undefined });
  assert.deepEqual(device.calls.slice(0, 2), ["open", "selectConfiguration 1"]);
  assert.equal(transport.configuredHere, true);
});

test("open refuses other bulk endpoint counts, naming the fact, and closes the device", async () => {
  const device = new FakeDevice({ endpoints: [endpoint("in", 2), endpoint("in", 3), endpoint("out", 1)] });
  await assert.rejects(new WebUsbTransport(device).open(),
    refusedNaming(new RegExp(`2 bulk IN endpoints, not ${count("usb.bulk_in_endpoints")} \\(${cite("usb.bulk_in_endpoints")}\\)`)));
  assert.equal(device.opened, false, "the device was left open after the refusal");
  await assert.rejects(opened({ endpoints: [endpoint("in", 2)] }),
    refusedNaming(new RegExp(`0 bulk OUT endpoints, not ${count("usb.bulk_out_endpoints")}`)));
});

test("open refuses another packet size, IN or OUT, naming the fact", async () => {
  const half = count("usb.packet_size") / 2;
  const pattern = new RegExp(`packets of ${half} bytes, not ${count("usb.packet_size")} \\(${cite("usb.packet_size")}\\)`);
  await assert.rejects(opened({ endpoints: [endpoint("in", 2, half), endpoint("out", 1)] }), refusedNaming(pattern));
  await assert.rejects(opened({ endpoints: [endpoint("in", 2), endpoint("out", 1, half)] }), refusedNaming(pattern));
});

test("open refuses bulk endpoints on different interfaces", async () => {
  await assert.rejects(opened({ endpoints: [{ ...endpoint("in", 2), interfaceNumber: 0 }, { ...endpoint("out", 1), interfaceNumber: 1 }] }),
    refusedNaming(/sit on different interfaces/));
});

test("open looks only at each interface's alternate setting 0", async () => {
  await assert.rejects(opened({ endpoints: [{ ...endpoint("in", 2), alternateSetting: 1 }, { ...endpoint("out", 1), alternateSetting: 1 }] }),
    refusedNaming(/0 bulk IN endpoints/));
});

test("open counts bulk endpoints only", async () => {
  const { device } = await opened({ endpoints: [endpoint("in", 2), endpoint("out", 1), endpoint("in", 4, 8, "interrupt")] });
  assert.deepEqual(device.calls, ["open", "claimInterface 0"]);
});

test("a read asks for one packet", async () => {
  const { device, transport } = await opened();
  const reading = transport.read(100);
  device.deliver(Uint8Array.of(1));
  await reading;
  assert.deepEqual(device.lengths, [count("usb.packet_size")]);
});

test("a read that times out leaves its transfer pending, and the next read waits on it", async () => {
  const { device, transport } = await opened();
  await assert.rejects(transport.read(20), TransportTimeout);
  device.deliver(Uint8Array.of(4, 5));
  assert.deepEqual(await transport.read(100), Uint8Array.of(4, 5));
  assert.equal(transfersIn(device), 1);
});

test("a transfer in that fails is not waited on again", async () => {
  const { device, transport } = await opened();
  const reading = transport.read(100);
  const planted = new Error("planted transfer failure");
  device.fail(planted);
  await assert.rejects(reading, (error: unknown) => error === planted);
  const next = transport.read(100);
  device.deliver(Uint8Array.of(6));
  assert.deepEqual(await next, Uint8Array.of(6));
  assert.equal(transfersIn(device), 2);
});

test("a read gives only the bytes its data view covers", async () => {
  const { device, transport } = await opened();
  const reading = transport.read(100);
  device.complete({ status: "ok", data: new DataView(Uint8Array.of(9, 9, 1, 2, 3, 9).buffer, 2, 3) });
  assert.deepEqual(await reading, Uint8Array.of(1, 2, 3));
});

test("a transfer in with no data gives no bytes", async () => {
  const { device, transport } = await opened();
  const reading = transport.read(100);
  device.complete({ status: "ok", data: null });
  assert.deepEqual(await reading, new Uint8Array(0));
});

test("a stalled read clears its endpoint's halt, then is refused", async () => {
  const { device, transport } = await opened();
  const reading = transport.read(100);
  device.complete({ status: "stall" });
  await assert.rejects(reading, refusedNaming(/transfer in stalled; its endpoint's halt was cleared/));
  assert.ok(device.calls.includes("clearHalt in 2"));
});

test("a read that ends in babble is refused", async () => {
  const { device, transport } = await opened();
  const reading = transport.read(100);
  device.complete({ status: "babble" });
  await assert.rejects(reading, refusedNaming(/transfer in ended with status babble/));
});

test("a stalled write clears its endpoint's halt, then is refused", async () => {
  const { device, transport } = await opened({ outStatus: "stall" });
  await assert.rejects(transport.write(Uint8Array.of(1)), refusedNaming(/transfer out stalled; its endpoint's halt was cleared/));
  assert.ok(device.calls.includes("clearHalt out 1"));
});

test("a write resolves to the bytes the device took", async () => {
  const { transport } = await opened({ take: 1 });
  assert.equal(await transport.write(Uint8Array.of(1, 2, 3)), 1);
});

test("close releases the interface and closes the device, with a transfer still pending", async () => {
  const { device, transport } = await opened();
  await assert.rejects(transport.read(20), TransportTimeout);
  await transport.close();
  assert.deepEqual(device.calls.slice(-2), ["releaseInterface 0", "close"]);
  await assert.rejects(transport.read(20), TransportClosed);
});

test("close closes the device even when releasing the interface fails", async () => {
  const { device, transport } = await opened({ releaseFails: true });
  await assert.rejects(transport.close(), /planted release failure/);
  assert.equal(device.calls.at(-1), "close");
  assert.equal(device.opened, false);
  await assert.rejects(transport.write(Uint8Array.of(1)), TransportClosed);
});

test("a read or a write before open is refused", async () => {
  const transport = new WebUsbTransport(new FakeDevice());
  await assert.rejects(transport.write(Uint8Array.of(1)), TransportClosed);
  await assert.rejects(transport.read(20), TransportClosed);
});

test("Command 7 over WebUSB, to the simulated LabPro replaying the fixture", async () => {
  const fixture = FIXTURES["status-request.trace"];
  assert.ok(fixture !== undefined);
  const link = new MemoryTransport();
  await link.open();
  const fake = new FakeLabPro(fixture, "status-request.trace", link.device, 200);
  const { transport } = await opened({ link });
  const status = await requestStatus(transport, { timeoutMs: 1000 });
  await fake.finished;
  assert.equal(fake.mismatch, null);
  assert.equal(fake.remaining.length, 0);
  assert.equal(status.values.length, count("status.register_count"));
  await transport.close();
});
