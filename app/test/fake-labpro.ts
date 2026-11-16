// A simulated LabPro for tests: it replays a fixture at the device's end of an in-memory link.
// It knows nothing of the LabPro's protocol, and shares no code with src/protocol/, so the
// protocol code is tested against a model written apart from it. The gate follows this
// file's imports to hold it to that. A fixture is the lead's model of a LabPro, not evidence.

import type { DeviceEnd } from "../src/transport/memory.ts";
import type { Fixture, FixtureTransfer } from "./generated/fixtures.ts";

/** Bytes written as a trace writes them, two-digit hex one space apart, as bytes. */
export function fromHex(text: string): Uint8Array {
  return Uint8Array.from(text === "" ? [] : text.split(" ").map((byte) => Number.parseInt(byte, 16)));
}

/** Bytes as a trace writes them. */
export function toHex(data: Uint8Array): string {
  return [...data].map((byte) => byte.toString(16).padStart(2, "0")).join(" ");
}

export class FakeLabPro {
  readonly name: string;
  readonly finished: Promise<void>;
  #remaining: FixtureTransfer[];
  #mismatch: string | null = null;

  /**
   * Replays fixture at device, in order: each IN is written for the host to read, and each
   * OUT must arrive from the host as the fixture holds it, byte for byte. The replay stops at
   * the first mismatch, or when the host sends nothing within waitMs.
   */
  constructor(fixture: Fixture, name: string, device: DeviceEnd, waitMs: number) {
    this.name = name;
    this.#remaining = [...fixture.transfers];
    this.finished = this.#replay(device, waitMs);
  }

  /** What the host sent that the fixture does not hold, or null. */
  get mismatch(): string | null {
    return this.#mismatch;
  }

  /** The transfers not yet replayed. */
  get remaining(): readonly FixtureTransfer[] {
    return this.#remaining;
  }

  async #replay(device: DeviceEnd, waitMs: number): Promise<void> {
    for (let next = this.#remaining[0]; next !== undefined; next = this.#remaining[0]) {
      if (next.direction === "IN") {
        device.write(fromHex(next.bytes));
        this.#remaining.shift();
        continue;
      }
      let sent: Uint8Array;
      try {
        sent = await device.read(waitMs);
      } catch {
        return; // the host sent nothing more
      }
      if (toHex(sent) !== next.bytes) {
        this.#mismatch = `the host sent ${toHex(sent)}, where ${this.name} has OUT ${next.bytes}`;
        return;
      }
      this.#remaining.shift();
    }
  }
}
