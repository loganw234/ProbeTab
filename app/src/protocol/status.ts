// Command 7, the status request, and its reply: the first exchange Phase 0 makes, and the
// one the bench script makes too (tools/bench/labpro_bench.py). Every value about the LabPro
// comes from the facts, and each refusal names the fact it rests on.

import { cite, count, text } from "./facts.ts";
import { TransportTimeout, type Transport } from "../transport/transport.ts";

/**
 * How Command 7 is framed. The manual writes s{7} for a computer host, and a carriage
 * return after each command on the serial port; whether USB wants either is the first thing
 * the bench has to settle.
 */
export const FORMS = ["s-cr", "s", "cr", "bare"] as const;
export type Form = (typeof FORMS)[number];

/** How long one read waits; the manual gives no figure. */
export const TIMEOUT_MS = 2000;

/** A reply that takes more reads than this is refused. */
export const MAX_READS = 64;

/** A reply this code does not recognise, said in words that name the fact it rests on. */
export class StatusRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StatusRefused";
  }
}

/** A recognised reply: each value as the text the LabPro sent. */
export interface Status {
  readonly values: readonly string[];
  readonly softwareId: string;
}

const encoder = new TextEncoder();

/** The bytes of Command 7, framed as form says. */
export function statusRequest(form: Form = "s-cr"): Uint8Array {
  let command = text("command.open") + String(count("command.request_system_status")) + text("command.close");
  if (form === "s-cr" || form === "s") {
    command = text("command.prefix") + command;
  }
  if (form === "s-cr" || form === "cr") {
    command += text("command.serial_terminator");
  }
  return encoder.encode(command);
}

/** A pattern for numbers written as template says, as sm.dddddEsee on page 21: s is a sign,
 * m, d and e are digits, and any other character is itself. */
export function numberForm(template: string): RegExp {
  const parts: Readonly<Record<string, string>> = { s: "[+-]", m: "[0-9]", d: "[0-9]", e: "[0-9]" };
  const pattern = [...template].map((ch) => parts[ch] ?? ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("");
  return new RegExp(`^${pattern}$`);
}

function find(haystack: Uint8Array, needle: Uint8Array): number {
  for (let at = 0; at + needle.length <= haystack.length; at++) {
    if (needle.every((byte, offset) => haystack[at + offset] === byte)) {
      return at;
    }
  }
  return -1;
}

function joined(pieces: readonly Uint8Array[]): Uint8Array {
  const all = new Uint8Array(pieces.reduce((total, piece) => total + piece.length, 0));
  let at = 0;
  for (const piece of pieces) {
    all.set(piece, at);
    at += piece.length;
  }
  return all;
}

function hex(data: Uint8Array): string {
  return [...data].map((byte) => byte.toString(16).padStart(2, "0")).join(" ");
}

/** The bytes of one reply, read until the end of a reply appears, or StatusRefused. */
export async function readReply(transport: Transport, timeoutMs: number = TIMEOUT_MS): Promise<Uint8Array> {
  const end = encoder.encode(text("reply.terminator"));
  const pieces: Uint8Array[] = [];
  let length = 0;
  for (let reads = 0; reads < MAX_READS; reads++) {
    let piece: Uint8Array;
    try {
      piece = await transport.read(timeoutMs);
    } catch (error) {
      if (!(error instanceof TransportTimeout)) {
        throw error;
      }
      throw new StatusRefused(length === 0
        ? `no reply came within ${timeoutMs} ms of Command 7`
        : `the reply stopped after ${length} bytes without its end (${cite("reply.terminator")})`);
    }
    pieces.push(piece);
    length += piece.length;
    const reply = joined(pieces);
    if (find(reply, end) >= 0) {
      return reply;
    }
  }
  throw new StatusRefused(`no end of reply in ${MAX_READS} reads (${cite("reply.terminator")})`);
}

/** The values of a Command 7 reply, or StatusRefused naming what does not fit. */
export function parseStatus(reply: Uint8Array): Status {
  const end = find(reply, encoder.encode(text("reply.terminator")));
  const body = end >= 0 ? reply.subarray(0, end) : reply;
  if (body.some((byte) => byte > 0x7f)) {
    throw new StatusRefused(`the reply holds bytes that are not ASCII text: ${hex(body)}`);
  }
  const message = new TextDecoder().decode(body).trim();
  const opening = text("command.open");
  const closing = text("command.close");
  if (!(message.startsWith(opening) && message.endsWith(closing) && message.length >= opening.length + closing.length)) {
    throw new StatusRefused(`the reply ${JSON.stringify(message)} is not one list in ${opening} and ${closing} `
      + `(${cite("command.separator")})`);
  }
  const values = message.slice(opening.length, message.length - closing.length)
    .split(text("command.separator")).map((value) => value.trim());
  const expected = count("status.register_count");
  if (values.length !== expected) {
    throw new StatusRefused(`the reply holds ${values.length} values, not ${expected} (${cite("status.register_count")})`);
  }
  const form = text("data.ascii_number_format");
  const pattern = numberForm(form);
  values.forEach((value, index) => {
    if (!pattern.test(value)) {
      throw new StatusRefused(`value ${index + 1} of the reply, ${JSON.stringify(value)}, is not written ${form} `
        + `(${cite("data.ascii_number_format")})`);
    }
  });
  const place = count("status.check_value_position");
  const check = count("status.check_value");
  const found = values[place - 1];
  if (found === undefined || Number(found) !== check) {
    throw new StatusRefused(`value ${place} of the reply is ${found}, not ${check} `
      + `(${cite("status.check_value")}; ${cite("status.check_value_position")})`);
  }
  const softwareId = values[count("status.software_id_position") - 1];
  if (softwareId === undefined) {
    throw new StatusRefused(`the reply has no value at the software ID's place (${cite("status.software_id_position")})`);
  }
  return Object.freeze({ values: Object.freeze(values), softwareId });
}

/** Sends Command 7 over the transport and reads its reply: the status, or StatusRefused. */
export async function requestStatus(
  transport: Transport,
  options: { readonly form?: Form; readonly timeoutMs?: number } = {},
): Promise<Status> {
  const command = statusRequest(options.form ?? "s-cr");
  const taken = await transport.write(command);
  if (taken !== command.length) {
    throw new StatusRefused(`only ${taken} of Command 7's ${command.length} bytes were taken`);
  }
  return parseStatus(await readReply(transport, options.timeoutMs ?? TIMEOUT_MS));
}
