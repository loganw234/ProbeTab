// An in-memory transport: a link with the host's end and the device's end, for tests and
// for a simulated LabPro. Each write arrives at the other end as one piece, as a USB
// transfer does, and is copied, so changing the bytes afterwards changes nothing.

import { TransportClosed, TransportTimeout, type Transport } from "./transport.ts";

/** One direction of the link: pieces waiting to be read, and reads waiting for pieces. */
class Queue {
  #pieces: Uint8Array[] = [];
  #waiting: ((piece: Uint8Array) => void)[] = [];

  push(data: Uint8Array): void {
    const piece = data.slice();
    const waiter = this.#waiting.shift();
    if (waiter === undefined) {
      this.#pieces.push(piece);
    } else {
      waiter(piece);
    }
  }

  take(timeoutMs: number): Promise<Uint8Array> {
    const piece = this.#pieces.shift();
    if (piece !== undefined) {
      return Promise.resolve(piece);
    }
    return new Promise((resolve, reject) => {
      const waiter = (arrived: Uint8Array): void => {
        clearTimeout(timer);
        resolve(arrived);
      };
      const timer = setTimeout(() => {
        const at = this.#waiting.indexOf(waiter);
        if (at >= 0) {
          this.#waiting.splice(at, 1);
        }
        reject(new TransportTimeout(timeoutMs));
      }, timeoutMs);
      this.#waiting.push(waiter);
    });
  }
}

/** The device's end of an in-memory link, where a simulated LabPro reads and writes. */
export interface DeviceEnd {
  /** The next piece the host wrote, or a rejection with TransportTimeout. */
  read(timeoutMs: number): Promise<Uint8Array>;

  /** Bytes for the host to read, as one piece. */
  write(data: Uint8Array): void;
}

/** The host's end of an in-memory link. Its device end is `device`. */
export class MemoryTransport implements Transport {
  readonly name = "memory";
  readonly device: DeviceEnd;
  #toDevice = new Queue();
  #toHost = new Queue();
  #open = false;

  constructor() {
    this.device = {
      read: (timeoutMs: number) => this.#toDevice.take(timeoutMs),
      write: (data: Uint8Array) => this.#toHost.push(data),
    };
  }

  async open(): Promise<void> {
    this.#open = true;
  }

  async close(): Promise<void> {
    this.#open = false;
  }

  async write(data: Uint8Array): Promise<number> {
    if (!this.#open) {
      throw new TransportClosed(this.name);
    }
    this.#toDevice.push(data);
    return data.length;
  }

  async read(timeoutMs: number): Promise<Uint8Array> {
    if (!this.#open) {
      throw new TransportClosed(this.name);
    }
    return this.#toHost.take(timeoutMs);
  }
}
