// The transport layer: one interface, with one implementation for each way of reaching a
// LabPro. The project outline names four: WebUSB, Web Serial, WebSocket and Web Bluetooth.
// Each carries the same bytes to and from the LabPro. A transport knows nothing of what the
// bytes mean; the protocol layer, in src/protocol/, never knows which transport is in use.

/** A connection to a LabPro that moves bytes. */
export interface Transport {
  /** What carries the bytes, as the app names it to its user. */
  readonly name: string;

  /** Opens the connection, or rejects with TransportRefused, saying what is not as expected. */
  open(): Promise<void>;

  /** Closes the connection. Closing one that is not open does nothing. */
  close(): Promise<void>;

  /** Sends bytes to the LabPro, and resolves to how many of them it took. */
  write(data: Uint8Array): Promise<number>;

  /**
   * Resolves to the next bytes from the LabPro: one USB transfer, or the next piece of a
   * stream. Rejects with TransportTimeout when none come within timeoutMs.
   */
  read(timeoutMs: number): Promise<Uint8Array>;
}

/** Nothing came within the time allowed. */
export class TransportTimeout extends Error {
  constructor(timeoutMs: number) {
    super(`nothing came within ${timeoutMs} ms`);
    this.name = "TransportTimeout";
  }
}

/** The device is not as the facts describe it, said in words that name the fact. */
export class TransportRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TransportRefused";
  }
}

/** A read or a write on a transport that is not open. */
export class TransportClosed extends Error {
  constructor(name: string) {
    super(`the ${name} transport is not open`);
    this.name = "TransportClosed";
  }
}
