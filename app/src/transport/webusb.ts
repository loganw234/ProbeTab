// The WebUSB transport: a stock LabPro on the computer's own USB port, from Chrome or Edge.
// It is written before any LabPro has been connected, and is first exercised at Phase 0.
// Its tests run it against a simulated device, not against a browser.
//
// TypeScript's DOM library does not declare WebUSB, so this file declares the parts it uses,
// under names that end in "Like". They are written from the lead's knowledge of the WebUSB
// API and were not checked against the specification here, so a mistake in them would show
// only in a browser. Where WebUSB declares a value as nullable, the code accepts null and
// undefined alike.

import { cite, count } from "../protocol/facts.ts";
import { TransportClosed, TransportRefused, TransportTimeout, type Transport } from "./transport.ts";

export interface USBEndpointLike {
  readonly endpointNumber: number;
  readonly direction: "in" | "out";
  readonly type: "bulk" | "interrupt" | "isochronous";
  readonly packetSize: number;
}

export interface USBAlternateInterfaceLike {
  readonly alternateSetting: number;
  readonly endpoints: readonly USBEndpointLike[];
}

export interface USBInterfaceLike {
  readonly interfaceNumber: number;
  readonly alternates: readonly USBAlternateInterfaceLike[];
}

export interface USBConfigurationLike {
  readonly configurationValue: number;
  readonly interfaces: readonly USBInterfaceLike[];
}

export interface USBInTransferResultLike {
  readonly data?: DataView | null;
  readonly status: "ok" | "stall" | "babble";
}

export interface USBOutTransferResultLike {
  readonly bytesWritten: number;
  readonly status: "ok" | "stall";
}

export interface USBDeviceLike {
  readonly vendorId: number;
  readonly productId: number;
  readonly opened: boolean;
  readonly configuration?: USBConfigurationLike | null;
  readonly configurations: readonly USBConfigurationLike[];
  open(): Promise<void>;
  close(): Promise<void>;
  selectConfiguration(configurationValue: number): Promise<void>;
  claimInterface(interfaceNumber: number): Promise<void>;
  releaseInterface(interfaceNumber: number): Promise<void>;
  clearHalt(direction: "in" | "out", endpointNumber: number): Promise<void>;
  transferIn(endpointNumber: number, length: number): Promise<USBInTransferResultLike>;
  transferOut(endpointNumber: number, data: Uint8Array): Promise<USBOutTransferResultLike>;
}

export interface USBLike {
  requestDevice(options: {
    readonly filters: readonly { readonly vendorId: number; readonly productId: number }[];
  }): Promise<USBDeviceLike>;
}

/** Asks the browser for a LabPro, by the vendor and product IDs in the facts. The browser shows
 * its own chooser, so this must run from a user's gesture, such as a click. */
export function requestLabPro(usb: USBLike): Promise<USBDeviceLike> {
  return usb.requestDevice({ filters: [{ vendorId: count("usb.vendor_id"), productId: count("usb.product_id") }] });
}

interface Bulk {
  readonly interfaceNumber: number;
  readonly endpoint: USBEndpointLike;
}

/** Rejects with TransportTimeout if promise has not settled within timeoutMs; leaves it running. */
function within<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new TransportTimeout(timeoutMs)), timeoutMs);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

export class WebUsbTransport implements Transport {
  readonly name = "WebUSB";
  #device: USBDeviceLike;
  #claimed: number | null = null;
  #inward: USBEndpointLike | null = null;
  #outward: USBEndpointLike | null = null;
  #pending: Promise<USBInTransferResultLike> | null = null;
  #configuredHere = false;

  constructor(device: USBDeviceLike) {
    this.#device = device;
  }

  /** Whether open() had to select the device's first configuration, because none was active. */
  get configuredHere(): boolean {
    return this.#configuredHere;
  }

  /** Opens the device and claims the interface with the bulk endpoints. If anything is not as
   * the facts describe, it closes the device again before it refuses. */
  async open(): Promise<void> {
    const device = this.#device;
    if (!device.opened) {
      await device.open();
    }
    try {
      await this.#claim(device);
    } catch (error) {
      await this.close().catch(() => undefined);
      throw error;
    }
  }

  async #claim(device: USBDeviceLike): Promise<void> {
    if (device.configuration == null) {
      const first = device.configurations[0];
      if (first === undefined) {
        throw new TransportRefused("the device offers no configuration");
      }
      await device.selectConfiguration(first.configurationValue);
      this.#configuredHere = true;
    }
    const configuration = device.configuration;
    if (configuration == null) {
      throw new TransportRefused("no configuration is active, even after selecting the first");
    }
    const found: { in: Bulk[]; out: Bulk[] } = { in: [], out: [] };
    for (const usbInterface of configuration.interfaces) {
      const alternate = usbInterface.alternates.find((setting) => setting.alternateSetting === 0);
      for (const endpoint of alternate?.endpoints ?? []) {
        if (endpoint.type === "bulk") {
          found[endpoint.direction].push({ interfaceNumber: usbInterface.interfaceNumber, endpoint });
        }
      }
    }
    const seen = [...found.in, ...found.out]
      .map((bulk) => `${bulk.endpoint.direction.toUpperCase()} ${bulk.endpoint.endpointNumber} `
        + `on interface ${bulk.interfaceNumber}`)
      .join(", ") || "none";
    for (const [way, name] of [["in", "usb.bulk_in_endpoints"], ["out", "usb.bulk_out_endpoints"]] as const) {
      if (found[way].length !== count(name)) {
        throw new TransportRefused(`the device has ${found[way].length} bulk ${way.toUpperCase()} endpoints, `
          + `not ${count(name)} (${cite(name)}); bulk endpoints seen: ${seen}`);
      }
    }
    const inward = found.in[0];
    const outward = found.out[0];
    if (inward === undefined || outward === undefined) {
      throw new TransportRefused(`the device lacks a bulk endpoint in each direction; bulk endpoints seen: ${seen}`);
    }
    if (inward.interfaceNumber !== outward.interfaceNumber) {
      throw new TransportRefused(`the bulk endpoints sit on different interfaces: ${seen}`);
    }
    for (const bulk of [inward, outward]) {
      if (bulk.endpoint.packetSize !== count("usb.packet_size")) {
        throw new TransportRefused(`endpoint ${bulk.endpoint.endpointNumber} takes packets of `
          + `${bulk.endpoint.packetSize} bytes, not ${count("usb.packet_size")} (${cite("usb.packet_size")})`);
      }
    }
    await device.claimInterface(inward.interfaceNumber);
    this.#claimed = inward.interfaceNumber;
    this.#inward = inward.endpoint;
    this.#outward = outward.endpoint;
  }

  /** Releases the interface and closes the device. The device is closed even when releasing
   * the interface fails, and that failure is then thrown. */
  async close(): Promise<void> {
    const claimed = this.#claimed;
    this.#claimed = null;
    this.#inward = null;
    this.#outward = null;
    this.#pending = null;
    try {
      if (claimed !== null) {
        await this.#device.releaseInterface(claimed);
      }
    } finally {
      if (this.#device.opened) {
        await this.#device.close();
      }
    }
  }

  async write(data: Uint8Array): Promise<number> {
    const outward = this.#outward;
    if (outward === null) {
      throw new TransportClosed(this.name);
    }
    const result = await this.#device.transferOut(outward.endpointNumber, data);
    if (result.status !== "ok") {
      await this.#recover(result.status, "out", outward.endpointNumber);
    }
    return result.bytesWritten;
  }

  async read(timeoutMs: number): Promise<Uint8Array> {
    const inward = this.#inward;
    if (inward === null) {
      throw new TransportClosed(this.name);
    }
    // WebUSB cannot cancel a transfer in. One that times out here stays pending, and the next
    // read waits on it, rather than asking for another packet and losing this one's bytes.
    if (this.#pending === null) {
      const pending = this.#device.transferIn(inward.endpointNumber, inward.packetSize);
      pending.catch(() => undefined); // a transfer still pending at close() rejects; nothing waits on it then
      this.#pending = pending;
    }
    let result: USBInTransferResultLike;
    try {
      result = await within(this.#pending, timeoutMs);
    } catch (error) {
      if (!(error instanceof TransportTimeout)) {
        this.#pending = null;
      }
      throw error;
    }
    this.#pending = null;
    if (result.status !== "ok") {
      await this.#recover(result.status, "in", inward.endpointNumber);
    }
    const view = result.data;
    if (view == null) {
      return new Uint8Array(0);
    }
    return new Uint8Array(view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength));
  }

  /** Refuses a transfer that did not end ok. A stalled endpoint is halted until the halt is
   * cleared, so it is cleared first, for the next transfer's sake. */
  async #recover(status: string, direction: "in" | "out", endpointNumber: number): Promise<never> {
    if (status === "stall") {
      await this.#device.clearHalt(direction, endpointNumber);
      throw new TransportRefused(`the transfer ${direction} stalled; its endpoint's halt was cleared`);
    }
    throw new TransportRefused(`the transfer ${direction} ended with status ${status}`);
  }
}
