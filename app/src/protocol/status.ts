// Commands to the LabPro and their replies: Command 7, the status request, first, as Phase 0
// makes it, and the commands the bench page sends after it. The bench script makes the same
// exchanges (tools/bench/labpro_bench.py). Every value about the LabPro comes from the facts,
// and each refusal names the fact it rests on.

import { cite, count, text } from "./facts.ts";
import { TransportTimeout, type Transport } from "../transport/transport.ts";

/**
 * How a command is framed. The manual writes s{7} for a computer host, and a carriage
 * return after each command on the serial port. Over USB, on 2026-11-25, Command 7 was
 * answered only with both (protocol/REFERENCE.md, question 1).
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

/** Nothing at all came in reply. */
export class NoReply extends StatusRefused {
  constructor(message: string) {
    super(message);
    this.name = "NoReply";
  }
}

/** A recognised reply: each value as the text the LabPro sent. */
export interface Status {
  readonly values: readonly string[];
  readonly softwareId: string;
}

const encoder = new TextEncoder();

/** The bytes of a command and its parameters, framed as form says. */
export function command(number: number, parameters: readonly number[] = [], form: Form = "s-cr"): Uint8Array {
  let message = text("command.open") + [number, ...parameters].map(String).join(text("command.separator"))
    + text("command.close");
  if (form === "s-cr" || form === "s") {
    message = text("command.prefix") + message;
  }
  if (form === "s-cr" || form === "cr") {
    message += text("command.serial_terminator");
  }
  return encoder.encode(message);
}

/** The bytes of Command 7, framed as form says. */
export function statusRequest(form: Form = "s-cr"): Uint8Array {
  return command(count("command.request_system_status"), [], form);
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

/**
 * The bytes of one reply, read until the end of a reply appears: NoReply when nothing came,
 * or StatusRefused. what names the command the reply answers, for the refusal's words.
 */
export async function readReply(transport: Transport, timeoutMs: number = TIMEOUT_MS,
  what = "Command 7"): Promise<Uint8Array> {
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
      if (length === 0) {
        throw new NoReply(`no reply came within ${timeoutMs} ms of ${what}`);
      }
      throw new StatusRefused(`the reply to ${what} stopped after ${length} bytes without its end `
        + `(${cite("reply.terminator")})`);
    }
    pieces.push(piece);
    length += piece.length;
    const reply = joined(pieces);
    if (find(reply, end) >= 0) {
      return reply;
    }
  }
  throw new StatusRefused(`no end of reply in ${MAX_READS} reads, after ${what} (${cite("reply.terminator")})`);
}

/** The values of a reply, before any is checked, or StatusRefused when the reply is not ASCII
 * text, or not one list in braces. */
function listOf(reply: Uint8Array): string[] {
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
  return message.slice(opening.length, message.length - closing.length)
    .split(text("command.separator")).map((value) => value.trim());
}

/** Refuses the first value not written as page 21 gives numbers. */
function checkForm(values: readonly string[]): void {
  const form = text("data.ascii_number_format");
  const pattern = numberForm(form);
  values.forEach((value, index) => {
    if (!pattern.test(value)) {
      throw new StatusRefused(`value ${index + 1} of the reply, ${JSON.stringify(value)}, is not written ${form} `
        + `(${cite("data.ascii_number_format")})`);
    }
  });
}

/** The values of any reply, each as the text the LabPro sent, or StatusRefused. */
export function valuesOf(reply: Uint8Array): string[] {
  const values = listOf(reply);
  checkForm(values);
  return values;
}

/** The values of a Command 7 reply, or StatusRefused naming what does not fit. */
export function parseStatus(reply: Uint8Array): Status {
  const values = listOf(reply);
  const expected = count("status.register_count");
  if (values.length !== expected) {
    throw new StatusRefused(`the reply holds ${values.length} values, not ${expected} (${cite("status.register_count")})`);
  }
  checkForm(values);
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
  const message = statusRequest(options.form ?? "s-cr");
  const taken = await transport.write(message);
  if (taken !== message.length) {
    throw new StatusRefused(`only ${taken} of Command 7's ${message.length} bytes were taken`);
  }
  return parseStatus(await readReply(transport, options.timeoutMs ?? TIMEOUT_MS));
}

/** The system states page 45 gives, by their facts' names. */
export const STATES = ["status.state_idle", "status.state_armed", "status.state_busy", "status.state_done",
  "status.state_self_test", "status.state_initializing"] as const;
export type StateName = (typeof STATES)[number];

/** A system state from Command 7, decoded: the state, and its two flags. */
export interface State {
  readonly name: StateName;
  readonly quickSetup: boolean;
  readonly unretrieved: boolean;
}

/** The system state in Command 7's values, decoded exactly as page 45 gives it, or
 * StatusRefused: a state, plus QuickSetup's flag, plus the flag for data not yet retrieved. */
export function decodeState(values: readonly string[]): State {
  const place = count("status.system_state_position");
  const found = values[place - 1];
  const value = Number(found);
  for (const quick of [0, count("status.quicksetup_flag")]) {
    for (const unretrieved of [0, count("status.unretrieved_data_flag")]) {
      for (const name of STATES) {
        if (found !== undefined && value === count(name) + quick + unretrieved) {
          return Object.freeze({ name, quickSetup: quick !== 0, unretrieved: unretrieved !== 0 });
        }
      }
    }
  }
  throw new StatusRefused(`the system state ${found} is no state page 45 gives, with or without its flags `
    + `(${cite("status.system_state_position")})`);
}
