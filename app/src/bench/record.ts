// The bench page's evidence: every transfer as the page saw it, kept for a trace. The page
// saves it as JSON only when its user asks, and tools/bench/from_browser.py writes the trace
// from that JSON with tools/traces.py, so the trace format keeps one writer and one rule for
// the serial number. Nothing here names the computer or its user.

import type { Form } from "../protocol/status.ts";
import type { Transport } from "../transport/transport.ts";

/** The record's format, as tools/bench/from_browser.py reads it. */
export const RECORD_FORMAT = "probetab-browser-record 1";

/** The serial number keeps this many characters at its start and at its end, as
 * tools/traces.py's SERIAL_KEPT; a bench test holds this copy to that one. */
export const SERIAL_KEPT = [3, 2] as const;
export const MASK = "*";

/** What the serial number reads when there is none, or it cannot be read. */
export const SERIAL_ABSENT: readonly string[] = ["none", "unreadable"];

export interface RecordedTransfer {
  readonly direction: "OUT" | "IN";
  readonly ms: number;
  readonly bytes: string;
}

/** Bytes as a trace writes them: two-digit hex, one space apart. */
export function toHex(data: Uint8Array): string {
  return [...data].map((byte) => byte.toString(16).padStart(2, "0")).join(" ");
}

/** A transport that keeps every transfer made through it: each write's bytes as far as they
 * were taken, and each read's bytes, with the milliseconds since start(). A read that times
 * out moves no bytes, and is not kept. */
export class RecordingTransport implements Transport {
  readonly name: string;
  readonly transfers: RecordedTransfer[] = [];
  readonly #inner: Transport;
  readonly #clock: () => number;
  #start: number;

  constructor(inner: Transport, clock: () => number = () => performance.now()) {
    this.name = inner.name;
    this.#inner = inner;
    this.#clock = clock;
    this.#start = clock();
  }

  /** Counts the milliseconds from now, as the bench script counts them from its first Command 7. */
  start(): void {
    this.#start = this.#clock();
  }

  open(): Promise<void> {
    return this.#inner.open();
  }

  close(): Promise<void> {
    return this.#inner.close();
  }

  async write(data: Uint8Array): Promise<number> {
    const taken = await this.#inner.write(data);
    this.#keep("OUT", data.subarray(0, Math.max(0, taken)));
    return taken;
  }

  async read(timeoutMs: number): Promise<Uint8Array> {
    const data = await this.#inner.read(timeoutMs);
    this.#keep("IN", data);
    return data;
  }

  #keep(direction: "OUT" | "IN", data: Uint8Array): void {
    this.transfers.push(Object.freeze({ direction, ms: Math.max(0, this.#clock() - this.#start), bytes: toHex(data) }));
  }
}

/** Whether every character is printable as Python's str.isprintable has it: none is in
 * Unicode's Other or Separator categories, but the space. */
function printable(text: string): boolean {
  return [...text].every((ch) => ch === " " || !/[\p{C}\p{Z}]/u.test(ch));
}

/** A device's string as the bench script records it: trimmed; none when absent or blank;
 * unreadable when it holds a character that is not printable. The converter applies the
 * script's own rule again, so the trace keeps that rule whatever this one did. */
export function deviceString(value: string | null | undefined): string {
  const trimmed = (value ?? "").trim();
  if (trimmed === "") {
    return "none";
  }
  return printable(trimmed) ? trimmed : "unreadable";
}

/** serial with every character masked but the first and last SERIAL_KEPT, or wholly masked
 * when it is no longer than those two together. none and unreadable are kept. */
export function maskSerial(serial: string): string {
  if (SERIAL_ABSENT.includes(serial)) {
    return serial;
  }
  const [head, tail] = SERIAL_KEPT;
  const characters = [...serial];
  if (characters.length <= head + tail) {
    return MASK.repeat(characters.length);
  }
  return characters.slice(0, head).join("") + MASK.repeat(characters.length - head - tail)
    + characters.slice(characters.length - tail).join("");
}

/** A date and time as the trace format writes them: local time, with its offset from UTC. */
export function localDate(when: Date): string {
  const pad = (value: number, width = 2): string => String(value).padStart(width, "0");
  const offset = -when.getTimezoneOffset();
  const size = Math.abs(offset);
  return `${pad(when.getFullYear(), 4)}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`
    + `T${pad(when.getHours())}:${pad(when.getMinutes())}:${pad(when.getSeconds())}`
    + `${offset < 0 ? "-" : "+"}${pad(Math.floor(size / 60))}:${pad(size % 60)}`;
}

/** The parts of User-Agent Client Hints the page reads. TypeScript's DOM library declares
 * none of them, so they are declared here, from the lead's knowledge of the API, not checked
 * against its specification here. */
export interface HintsLike {
  readonly platform?: string;
  readonly platformVersion?: string;
  readonly fullVersionList?: readonly { readonly brand: string; readonly version: string }[];
}

export interface UADataLike {
  getHighEntropyValues(hints: readonly string[]): Promise<HintsLike>;
}

/** The trace's os and stack, from the browser's own hints: the platform and its version,
 * and the browser and its version. Neither names the computer or its user. The user-agent
 * string is not read, because its version can be frozen. */
export function describeHost(hints: HintsLike | null): { readonly os: string; readonly stack: string } {
  const platform = hints?.platform?.trim() ?? "";
  const version = hints?.platformVersion?.trim() ?? "";
  const os = platform === "" ? "unknown" : version === "" ? platform : `${platform} ${version}`;
  // Browsers list made-up brands, such as "Not_A Brand", so that no one relies on the order.
  const brands = (hints?.fullVersionList ?? []).filter((entry) => !/not.?a.?brand/i.test(entry.brand));
  const named = brands.find((entry) => entry.brand !== "Chromium") ?? brands[0];
  const browser = named === undefined ? "a browser that gave no version" : `${named.brand} ${named.version}`;
  return Object.freeze({ os, stack: `${browser}, WebUSB` });
}

/** describeHost of what the browser gives, or of nothing when it gives nothing. */
export async function hostOf(data: UADataLike | undefined): Promise<{ readonly os: string; readonly stack: string }> {
  if (data === undefined) {
    return describeHost(null);
  }
  try {
    return describeHost(await data.getHighEntropyValues(["platformVersion", "fullVersionList"]));
  } catch {
    return describeHost(null);
  }
}

/** What the page saves, for tools/bench/from_browser.py. */
export interface BrowserRecord {
  readonly format: typeof RECORD_FORMAT;
  readonly date: string;
  readonly os: string;
  readonly stack: string;
  readonly firmware: string;
  readonly form: Form;
  readonly manufacturer: string;
  readonly product: string;
  readonly serial: string;
  readonly refusals: readonly string[];
  readonly findings: readonly string[];
  readonly transfers: readonly RecordedTransfer[];
}
