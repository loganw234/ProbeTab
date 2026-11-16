// The bench page's steps: Command 7, the guarded reset, channel 1 and Command 9, through any
// transport, as tools/bench/labpro_bench.py takes them, with the same refusals and the same
// discard. Every value about the LabPro comes from the facts, and each refusal names the fact
// it rests on. The constants are copies of the bench script's own choices, and
// tools/bench/test_browser.py holds each copy to the script's.

import { cite, count } from "../protocol/facts.ts";
import {
  NoReply, StatusRefused, TIMEOUT_MS, command, decodeState, parseStatus, readReply, valuesOf,
  type Form, type State, type StateName,
} from "../protocol/status.ts";
import { TransportTimeout, type Transport } from "../transport/transport.ts";

/** How long the page listens for anything after a command, or after a reply. */
export const QUIET_MS = 300;
/** How often Command 7 is read again while the unit initializes, or is silent. */
export const RETRIES = 5;
/** How long the page waits before each of those reads. */
export const RETRY_MS = 1000;
/** In a live reading, Command 7 follows every this many readings. */
export const ERROR_EVERY = 10;
/** The longest interval between live readings, a day, as the bench script's MAX_EVERY. */
export const MAX_EVERY_SECONDS = 86400;
/** The only states the reset is sent to. */
export const RESETTABLE: readonly StateName[] = ["status.state_idle", "status.state_done"];
/** The states that are read again before anything is decided. */
export const WAITING: readonly StateName[] = ["status.state_initializing", "status.state_self_test"];

/** Waits ms, or less when signal aborts. */
export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve();
      return;
    }
    const done = (): void => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", done);
      resolve();
    };
    const timer = setTimeout(done, ms);
    signal?.addEventListener("abort", done);
  });
}

export interface SessionOptions {
  readonly form?: Form;
  readonly timeoutMs?: number;
  readonly quietMs?: number;
  readonly retryMs?: number;
  readonly say?: (line: string) => void;
}

/** The commands of one session, each sent in the session's framing. What the LabPro does
 * that the manual does not say is kept in findings; what this code does not recognise is
 * refused with StatusRefused. */
export class BenchSession {
  readonly findings: string[] = [];
  readonly say: (line: string) => void;
  readonly #transport: Transport;
  readonly #packets: Transport;
  readonly #form: Form;
  readonly #timeoutMs: number;
  readonly #quietMs: number;
  readonly #retryMs: number;

  constructor(transport: Transport, options: SessionOptions = {}) {
    this.#transport = transport;
    // The transport that replies are read through, and only replies: each packet of a reply is
    // held to the multiple that transfers to the host come in, as the bench script holds it.
    this.#packets = {
      name: transport.name,
      open: () => transport.open(),
      close: () => transport.close(),
      write: (data: Uint8Array) => transport.write(data),
      read: async (timeoutMs: number) => {
        const packet = await transport.read(timeoutMs);
        const multiple = count("usb.in_transfer_multiple");
        if (packet.length % multiple) {
          this.findings.push(`a packet of ${packet.length} bytes, where transfers to the host come in multiples `
            + `of ${multiple} (${cite("usb.in_transfer_multiple")})`);
        }
        return packet;
      },
    };
    this.#form = options.form ?? "s-cr";
    this.#timeoutMs = options.timeoutMs ?? TIMEOUT_MS;
    this.#quietMs = options.quietMs ?? QUIET_MS;
    this.#retryMs = options.retryMs ?? RETRY_MS;
    this.say = options.say ?? (() => undefined);
  }

  async send(number: number, ...parameters: number[]): Promise<void> {
    const message = command(number, parameters, this.#form);
    const taken = await this.#transport.write(message);
    if (taken !== message.length) {
      this.findings.push(`only ${taken} of Command ${number}'s ${message.length} bytes were taken`);
    }
  }

  reply(what: string): Promise<Uint8Array> {
    return readReply(this.#packets, this.#timeoutMs, what);
  }

  /** Listens briefly after a command or a reply, and names anything that comes. */
  async quiet(after: string, said?: string): Promise<void> {
    let piece: Uint8Array;
    try {
      piece = await this.#transport.read(this.#quietMs);
    } catch (error) {
      if (error instanceof TransportTimeout) {
        return;
      }
      throw error;
    }
    this.findings.push(`${piece.length} bytes came after ${after}` + (said === undefined ? "" : `, which ${said}`));
  }

  /** Command 7's values, or NoReply, or StatusRefused. */
  async status(): Promise<readonly string[]> {
    await this.send(count("command.request_system_status"));
    return parseStatus(await this.reply("Command 7")).values;
  }

  /** The decoded state once it is neither initializing nor self-testing, read again while it is,
   * or while Command 7 draws no reply, up to RETRIES times; null if Command 7 drew no reply at
   * the last. */
  async settled(values: readonly string[] | null): Promise<State | null> {
    let state = values === null ? null : decodeState(values);
    let tries = 0;
    while ((state === null || WAITING.includes(state.name)) && tries < RETRIES) {
      await sleep(this.#retryMs);
      tries += 1;
      try {
        state = decodeState(await this.status());
      } catch (error) {
        if (!(error instanceof NoReply)) {
          throw error;
        }
        state = null;
      }
    }
    return state;
  }

  async noErrors(after: string): Promise<void> {
    const values = await this.status();
    const place = count("status.error_position");
    const found = values[place - 1];
    if (found === undefined || Number(found) !== 0) {
      throw new StatusRefused(`the error register is ${found} after ${after} (${cite("status.error_position")})`);
    }
  }

  /** Command 9's one value for channel 1 in mode, then a brief listen. */
  async channelValue(mode: number): Promise<string> {
    await this.send(count("command.request_channel_data"), count("channel.ch1"), mode);
    const values = valuesOf(await this.reply("Command 9"));
    const value = values[0];
    if (values.length !== 1 || value === undefined) {
      throw new StatusRefused(`Command 9's reply holds ${values.length} values, not one `
        + `(${cite("command.request_channel_data")})`);
    }
    await this.quiet("Command 9's reply");
    return value;
  }
}

function label(name: StateName): string {
  return name.replace("status.state_", "").replaceAll("_", "-");
}

/** The live reading's ends: a reading every `every` seconds, until `readings` readings or
 * `seconds` seconds, or until signal aborts. */
export interface Live {
  readonly every: number;
  readonly readings?: number;
  readonly seconds?: number;
  readonly signal?: AbortSignal;
  readonly clock?: () => number;
}

/** Refuses a live reading that would not end, or whose numbers are out of range, before
 * anything is sent. */
export function checkLive(live: Live): void {
  if (!(Number.isFinite(live.every) && live.every >= 0 && live.every <= MAX_EVERY_SECONDS)) {
    throw new StatusRefused(`the interval ${live.every} is not a number of seconds from 0 to ${MAX_EVERY_SECONDS}`);
  }
  if (live.readings === undefined && live.seconds === undefined) {
    throw new StatusRefused("a live reading needs a number of readings or a number of seconds, so that it ends");
  }
  if (live.readings !== undefined && !(Number.isInteger(live.readings) && live.readings >= 1)) {
    throw new StatusRefused(`${live.readings} is not a whole number of readings, 1 or more`);
  }
  if (live.seconds !== undefined && !(Number.isFinite(live.seconds) && live.seconds > 0)) {
    throw new StatusRefused(`${live.seconds} is not a number of seconds above 0`);
  }
}

/** What reading CH1 gave: Command 9's value in mode 0 and in mode 1, and the live readings. */
export interface Ch1 {
  readonly present: string;
  readonly stored: string;
  readonly live: readonly { readonly ms: number; readonly value: string }[];
  readonly stopped: boolean;
}

/**
 * Reads CH1 after Command 7's values `first`, in the bench script's steps: the guard, the
 * reset, a brief listen, Command 7 showing idle, channel 1 by auto-ID, a brief listen,
 * Command 7, Command 9 in mode 0, Command 7, Command 9 in mode 1 once, Command 7, then the
 * live reading if one is asked for. Refused at any step it does not recognise.
 */
export async function readCh1(session: BenchSession, first: readonly string[],
  options: { readonly discard?: boolean; readonly live?: Live } = {}): Promise<Ch1> {
  if (options.live !== undefined) {
    checkLive(options.live);
  }
  const state = await session.settled(first);
  if (state === null) {
    throw new StatusRefused(`Command 7 drew no reply on any of ${RETRIES} more tries`);
  }
  if (WAITING.includes(state.name)) {
    throw new StatusRefused(`the unit stayed ${label(state.name)} through ${RETRIES} more readings of Command 7 `
      + `(${cite(state.name)})`);
  }
  if (!RESETTABLE.includes(state.name)) {
    throw new StatusRefused(`the unit is ${label(state.name)} (${cite(state.name)}); the page resets only an idle or `
      + `done unit, never an armed or busy one, discard or not`);
  }
  if (state.unretrieved && !options.discard) {
    throw new StatusRefused(`the unit holds data not yet retrieved (${cite("status.unretrieved_data_flag")}); `
      + `discard resets it anyway, and that data is lost`);
  }
  session.say(`the unit is ${label(state.name)}${state.unretrieved ? ", with data not yet retrieved, which discard loses" : ""}; `
    + `resetting it`);
  await session.send(count("command.reset"));
  await session.quiet("Command 0", `page 30 says returns nothing (${cite("command.reset_reply")})`);
  const after = await session.settled(null);
  if (after === null || after.name !== "status.state_idle" || after.unretrieved) {
    const seen = after === null ? "no reply" : label(after.name) + (after.unretrieved ? " with data unretrieved" : "");
    throw new StatusRefused(`after the reset the unit is not idle: ${seen} (${cite("status.state_idle")})`);
  }
  await session.send(count("command.channel_setup"), count("channel.ch1"), count("channel.operation_auto_id"));
  await session.quiet("Command 1", `page 32 says returns nothing (${cite("command.channel_setup_reply")})`);
  await session.noErrors("Command 1");
  const present = await session.channelValue(count("channel_data.mode_retest"));
  await session.noErrors("Command 9");
  const stored = await session.channelValue(count("channel_data.mode_stored"));
  await session.noErrors("Command 9 in mode 1");
  session.say(`CH1: ${present} by Command 9 in mode 0, the present setup; ${stored} in mode 1, the stored setup`);
  const live: { ms: number; value: string }[] = [];
  const plan = options.live;
  if (plan === undefined) {
    return Object.freeze({ present, stored, live, stopped: false });
  }
  const clock = plan.clock ?? (() => performance.now());
  const began = clock();
  let stopped = false;
  while ((plan.readings === undefined || live.length < plan.readings)
    && (plan.seconds === undefined || clock() - began < plan.seconds * 1000)) {
    if (plan.signal?.aborted) {
      stopped = true;
      break;
    }
    const value = await session.channelValue(count("channel_data.mode_retest"));
    const ms = clock() - began;
    live.push({ ms, value });
    session.say(`${(ms / 1000).toFixed(1).padStart(9)} s  ${value}`);
    if (live.length % ERROR_EVERY === 0) {
      await session.noErrors("the live reading");
    }
    await sleep(plan.every * 1000, plan.signal);
  }
  if (stopped) {
    session.say("stopped by the operator; the transfers made so far are kept");
  }
  return Object.freeze({ present, stored, live, stopped });
}
