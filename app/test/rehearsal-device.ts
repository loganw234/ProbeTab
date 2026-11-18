// The bench page's rehearsal: a stand-in for the browser's WebUSB, whose one device carries the
// page's transfers to and from the tests' simulated LabPro as it replays a fixture. The rehearsal
// page, app/bench/rehearse.html, puts it in place of navigator.usb under the bench page, which
// runs unchanged; test/rehearsal.test.ts runs the page's steps against it on Node.
//
// It is the lead's model of a LabPro, not a LabPro, and nothing a rehearsal shows is evidence. It
// names itself in the strings a device gives, so the page's record says where it came from, and
// tools/bench/from_browser.py will not write such a record into protocol/traces/. Its shape (its
// IDs, its interface and its two bulk endpoints) comes from the facts, as the WebUSB tests'
// device's does, so a rehearsal cannot catch a wrong fact. Where it refuses as WebUSB would, it
// follows the lead's knowledge of WebUSB, not its specification.

import { count } from "../src/protocol/facts.ts";
import { MemoryTransport, type DeviceEnd } from "../src/transport/memory.ts";
import type {
  USBConfigurationLike, USBDeviceLike, USBInTransferResultLike, USBLike, USBOutTransferResultLike,
} from "../src/transport/webusb.ts";
import { FakeLabPro } from "./fake-labpro.ts";
import type { Fixture } from "./generated/fixtures.ts";

/** The fixture a rehearsal replays, from protocol/fixtures/. */
export const SCRIPT = "bench-rehearsal.trace";

/** The strings the device gives. tools/bench/from_browser.py knows a rehearsal's record by
 * MANUFACTURER, and a bench test holds its copy to this one. */
export const MANUFACTURER = "ProbeTab rehearsal";
export const PRODUCT = "Simulated LabPro, not a device";
export const SERIAL = "REHEARSAL01";

/** How long the simulated LabPro waits for the page's next command before it stops replaying:
 * an hour, so that a person can take their time between steps. */
export const PATIENCE_MS = 60 * 60 * 1000;

/** The facts give no endpoint numbers, so these are the WebUSB tests' choice. */
const IN_ENDPOINT = 2;
const OUT_ENDPOINT = 1;
const INTERFACE = 0;
const CONFIGURATION = 1;

/** A transfer in that waits for bytes: as WebUSB's does, it waits with no time limit. */
interface Waiting {
  readonly resolve: (piece: Uint8Array) => void;
  readonly reject: (error: Error) => void;
}

/** The rehearsal's one device: a LabPro's shape, with the simulated LabPro at its far end. */
export class RehearsalDevice implements USBDeviceLike {
  readonly vendorId = count("usb.vendor_id");
  readonly productId = count("usb.product_id");
  readonly manufacturerName = MANUFACTURER;
  readonly productName = PRODUCT;
  readonly serialNumber = SERIAL;
  readonly configurations: readonly USBConfigurationLike[];
  /** The simulated LabPro. It replays the fixture from the device's making, and waits up to its
   * patience for each command the fixture holds. */
  readonly labPro: FakeLabPro;
  readonly #link = new MemoryTransport();
  #replies: Uint8Array[] = [];
  #waiting: Waiting[] = [];
  #opened = false;
  #claimed: number | null = null;
  #configuration: USBConfigurationLike | null;

  constructor(fixture: Fixture, patienceMs: number = PATIENCE_MS) {
    const packetSize = count("usb.packet_size");
    const bulk = (endpointNumber: number, direction: "in" | "out") =>
      Object.freeze({ endpointNumber, direction, type: "bulk" as const, packetSize });
    this.configurations = Object.freeze([Object.freeze({
      configurationValue: CONFIGURATION,
      interfaces: Object.freeze([Object.freeze({
        interfaceNumber: INTERFACE,
        alternates: Object.freeze([Object.freeze({
          alternateSetting: 0,
          endpoints: Object.freeze([bulk(IN_ENDPOINT, "in"), bulk(OUT_ENDPOINT, "out")]),
        })]),
      })]),
    })]);
    this.#configuration = this.configurations[0] ?? null;
    // The page's commands reach the simulated LabPro through the in-memory link; its replies come
    // back through #deliver, so that a transfer in can wait with no time limit, as WebUSB's does.
    const end: DeviceEnd = {
      read: (timeoutMs: number) => this.#link.device.read(timeoutMs),
      write: (data: Uint8Array) => this.#deliver(data),
    };
    this.labPro = new FakeLabPro(fixture, SCRIPT, end, patienceMs);
  }

  get opened(): boolean {
    return this.#opened;
  }

  get configuration(): USBConfigurationLike | null {
    return this.#configuration;
  }

  async open(): Promise<void> {
    this.#opened = true;
    await this.#link.open();
  }

  /** Closes the device, and cancels any transfer in still waiting, as WebUSB does. */
  async close(): Promise<void> {
    this.#opened = false;
    this.#claimed = null;
    await this.#link.close();
    for (const waiting of this.#waiting.splice(0)) {
      waiting.reject(new DOMException("The transfer was cancelled.", "AbortError"));
    }
  }

  async selectConfiguration(configurationValue: number): Promise<void> {
    this.#mustBeOpen();
    const found = this.configurations.find((configuration) => configuration.configurationValue === configurationValue);
    if (found === undefined) {
      throw new DOMException("The configuration value provided is not supported by the device.", "NotFoundError");
    }
    this.#configuration = found;
  }

  async claimInterface(interfaceNumber: number): Promise<void> {
    this.#mustBeOpen();
    if (!this.#configuration?.interfaces.some((usbInterface) => usbInterface.interfaceNumber === interfaceNumber)) {
      throw new DOMException("The interface number provided is not supported by the device in its current "
        + "configuration.", "NotFoundError");
    }
    this.#claimed = interfaceNumber;
  }

  async releaseInterface(interfaceNumber: number): Promise<void> {
    this.#mustBeOpen();
    if (this.#claimed === interfaceNumber) {
      this.#claimed = null;
    }
  }

  async clearHalt(direction: "in" | "out", endpointNumber: number): Promise<void> {
    this.#endpoint(direction, endpointNumber);
  }

  /** The next piece the simulated LabPro wrote, whole: the fixtures' pieces are each one packet,
   * so length is not consulted. It waits as long as it takes, until the device is closed. */
  transferIn(endpointNumber: number, length: number): Promise<USBInTransferResultLike> {
    void length;
    try {
      this.#endpoint("in", endpointNumber);
    } catch (error) {
      return Promise.reject(error);
    }
    const result = (piece: Uint8Array): USBInTransferResultLike =>
      ({ status: "ok", data: new DataView(piece.buffer, piece.byteOffset, piece.byteLength) });
    const ready = this.#replies.shift();
    if (ready !== undefined) {
      return Promise.resolve(result(ready));
    }
    return new Promise((resolve, reject) => {
      this.#waiting.push({ resolve: (piece) => resolve(result(piece)), reject });
    });
  }

  async transferOut(endpointNumber: number, data: Uint8Array): Promise<USBOutTransferResultLike> {
    this.#endpoint("out", endpointNumber);
    await this.#link.write(data);
    return { bytesWritten: data.length, status: "ok" };
  }

  /** A piece the simulated LabPro wrote: to the oldest transfer in that waits, or kept for the
   * next one. */
  #deliver(data: Uint8Array): void {
    const piece = data.slice();
    const waiting = this.#waiting.shift();
    if (waiting === undefined) {
      this.#replies.push(piece);
    } else {
      waiting.resolve(piece);
    }
  }

  #mustBeOpen(): void {
    if (!this.#opened) {
      throw new DOMException("The device must be opened first.", "InvalidStateError");
    }
  }

  /** Refuses, as WebUSB does, a transfer on a device not open, on an interface not claimed, or
   * on an endpoint the interface does not have. */
  #endpoint(direction: "in" | "out", endpointNumber: number): void {
    this.#mustBeOpen();
    if (this.#claimed !== INTERFACE || endpointNumber !== (direction === "in" ? IN_ENDPOINT : OUT_ENDPOINT)) {
      throw new DOMException("The specified endpoint is not part of a claimed and selected alternate interface.",
        "NotFoundError");
    }
  }
}

/** The stand-in for navigator.usb. Its one device answers a request whose filters name the
 * LabPro's IDs from the facts; any other request is refused, as WebUSB refuses when no device is
 * chosen. The device is made at the first request, so its simulated LabPro's patience starts
 * then. */
export class RehearsalUsb implements USBLike {
  readonly #fixture: Fixture;
  readonly #patienceMs: number;
  #device: RehearsalDevice | null = null;

  constructor(fixture: Fixture, patienceMs: number = PATIENCE_MS) {
    this.#fixture = fixture;
    this.#patienceMs = patienceMs;
  }

  /** The device, once a request has made it. */
  get device(): RehearsalDevice | null {
    return this.#device;
  }

  async requestDevice(options: {
    readonly filters: readonly { readonly vendorId: number; readonly productId: number }[];
  }): Promise<RehearsalDevice> {
    const named = options.filters.some((filter) =>
      filter.vendorId === count("usb.vendor_id") && filter.productId === count("usb.product_id"));
    if (!named) {
      throw new DOMException("No device selected.", "NotFoundError");
    }
    this.#device ??= new RehearsalDevice(this.#fixture, this.#patienceMs);
    return this.#device;
  }
}
