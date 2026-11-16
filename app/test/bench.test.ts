// The bench page's steps and evidence, against the simulated LabPro replaying
// protocol/fixtures/ch1-reading.trace and variants of it, as tools/bench/test_ch1.py runs the
// bench script against the fake backend. A variant that holds fewer commands than the page
// would send ends the replay early, which is how a reset the guard should have refused shows.

import { test } from "node:test";
import assert from "node:assert/strict";
import { FakeLabPro, fromHex, toHex } from "./fake-labpro.ts";
import { FIXTURES, type FixtureTransfer } from "./generated/fixtures.ts";
import { cite, count, text } from "../src/protocol/facts.ts";
import { StatusRefused } from "../src/protocol/status.ts";
import {
  BenchSession, ERROR_EVERY, MAX_EVERY_SECONDS, QUIET_MS, RESETTABLE, RETRIES, RETRY_MS, WAITING, checkLive,
  readCh1, type Ch1, type Live,
} from "../src/bench/session.ts";
import {
  RecordingTransport, describeHost, deviceString, localDate, maskSerial,
} from "../src/bench/record.ts";
import { MemoryTransport } from "../src/transport/memory.ts";

const NAME = "ch1-reading.trace";
const FIXTURE = FIXTURES[NAME];
if (FIXTURE === undefined) {
  throw new Error(`the generated fixtures have no ${NAME}`);
}
const TIMEOUT_MS = 100;

/** An OUT and the INs that answer it. */
type Exchange = readonly FixtureTransfer[];

function exchanges(): Exchange[] {
  const found: FixtureTransfer[][] = [];
  for (const transfer of FIXTURE.transfers) {
    if (transfer.direction === "OUT") {
      found.push([transfer]);
    } else {
      found.at(-1)?.push(transfer);
    }
  }
  return found;
}

function exchange(index: number): Exchange {
  const found = exchanges()[index];
  if (found === undefined) {
    throw new Error(`${NAME} has no exchange ${index}`);
  }
  return found;
}

/** A number as page 21 writes it, sm.dddddEsee, written here without the protocol code's help. */
function written(value: number): string {
  const [mantissa = "", power = "0"] = value.toExponential(5).split("e");
  const exponent = Number(power);
  return `${value < 0 ? "-" : "+"}${mantissa.replace("-", "")}E${exponent < 0 ? "-" : "+"}`
    + String(Math.abs(exponent)).padStart(2, "0");
}

/** The values of a reply's INs, read here without the protocol code's help. */
function valuesIn(ins: readonly FixtureTransfer[]): string[] {
  const all = new TextDecoder().decode(fromHex(ins.map((transfer) => transfer.bytes).join(" ")));
  const message = all.slice(0, all.indexOf(text("reply.terminator"))).trim();
  return message.slice(text("command.open").length, -text("command.close").length)
    .split(text("command.separator")).map((value) => value.trim());
}

/** values as a reply, padded with zeros to whole packets, as IN transfers. */
function packets(values: readonly string[]): FixtureTransfer[] {
  const size = count("usb.packet_size");
  const message = text("command.open") + " " + values.join(text("command.separator") + " ") + text("command.close")
    + text("reply.terminator");
  const data = new TextEncoder().encode(message);
  const padded = new Uint8Array(Math.ceil(data.length / size) * size);
  padded.set(data);
  const transfers: FixtureTransfer[] = [];
  for (let at = 0; at < padded.length; at += size) {
    transfers.push({ direction: "IN", micros: 1000, bytes: toHex(padded.subarray(at, at + size)) });
  }
  return transfers;
}

const COMMAND_7 = exchange(0);
const READING = exchange(5);

/** Command 7 answered with the fixture's values, but for the system state, and the error. */
function status(state: number = count("status.state_idle"), error = 0): Exchange {
  const values = valuesIn(COMMAND_7.slice(1));
  values[count("status.system_state_position") - 1] = written(state);
  values[count("status.error_position") - 1] = written(error);
  return [COMMAND_7[0] as FixtureTransfer, ...packets(values)];
}

/** Command 7 drawing no reply. */
function silent(): Exchange {
  return [COMMAND_7[0] as FixtureTransfer];
}

interface Outcome {
  readonly ch1: Ch1 | null;
  readonly error: unknown;
  readonly fake: FakeLabPro;
  readonly recording: RecordingTransport;
  readonly session: BenchSession;
  readonly said: string[];
}

/** The page's steps against a replay of variant: Command 7, then readCh1 with options. */
async function run(variant: readonly Exchange[], options: { readonly discard?: boolean; readonly live?: Live } = {},
  say?: (line: string) => void): Promise<Outcome> {
  const link = new MemoryTransport();
  await link.open();
  const fake = new FakeLabPro({ model: "a test's variant", transfers: variant.flat() }, "a test's variant", link.device, 200);
  const recording = new RecordingTransport(link);
  const said: string[] = [];
  const session = new BenchSession(recording, {
    timeoutMs: TIMEOUT_MS, quietMs: 20, retryMs: 0,
    say: (line) => {
      said.push(line);
      say?.(line);
    },
  });
  let ch1: Ch1 | null = null;
  let error: unknown = null;
  try {
    ch1 = await readCh1(session, await session.status(), options);
  } catch (caught) {
    error = caught;
  }
  await fake.finished;
  return { ch1, error, fake, recording, session, said };
}

function outs(outcome: Outcome): number {
  return outcome.recording.transfers.filter((transfer) => transfer.direction === "OUT").length;
}

function refused(outcome: Outcome, pattern: RegExp): void {
  assert.ok(outcome.error instanceof StatusRefused, `expected a refusal, got ${String(outcome.error)}`);
  assert.match(outcome.error.message, pattern);
}

function whole(outcome: Outcome): Ch1 {
  assert.equal(outcome.error, null, String(outcome.error));
  assert.equal(outcome.fake.mismatch, null);
  assert.deepEqual(outcome.fake.remaining, [], "the page left part of the variant unread");
  assert.ok(outcome.ch1 !== null);
  return outcome.ch1;
}

test("reads CH1 as the fixture has it, with every transfer used and kept", async () => {
  const outcome = await run(exchanges());
  const ch1 = whole(outcome);
  assert.equal(ch1.present, valuesIn(exchange(5).slice(1))[0]);
  assert.equal(ch1.stored, valuesIn(exchange(7).slice(1))[0]);
  assert.deepEqual(outcome.session.findings, []);
  assert.deepEqual(outcome.recording.transfers.map((transfer) => [transfer.direction, transfer.bytes]),
    FIXTURE.transfers.map((transfer) => [transfer.direction, transfer.bytes]));
});

test("an armed or busy unit is never reset, discard or not", async () => {
  for (const name of ["status.state_armed", "status.state_busy"]) {
    for (const discard of [false, true]) {
      const outcome = await run([status(count(name))], { discard });
      refused(outcome, /never an armed or busy one, discard or not/);
      assert.equal(outs(outcome), 1, `${name}, discard ${discard}: only Command 7 is sent`);
    }
  }
});

test("an undecodable state is refused, and nothing reset", async () => {
  for (const state of [7, 1.5, 0, 100]) {
    const outcome = await run([status(state)], { discard: true });
    refused(outcome, /is no state page 45 gives/);
    assert.equal(outs(outcome), 1, `state ${state}: only Command 7 is sent`);
  }
});

test("a done unit, and an idle one with QuickSetup's flag, are reset", async () => {
  for (const state of [count("status.state_done"), count("status.state_idle") + count("status.quicksetup_flag")]) {
    whole(await run([status(state), ...exchanges().slice(1)]));
  }
});

test("data not yet retrieved is kept unless discarded", async () => {
  const holding = count("status.state_done") + count("status.unretrieved_data_flag");
  refused(await run([status(holding)]), /holds data not yet retrieved/);
  whole(await run([status(holding), ...exchanges().slice(1)], { discard: true }));
});

test("initializing and self-test are read again until idle", async () => {
  for (const name of WAITING) {
    whole(await run([status(count(name)), status(count(name)), status(), ...exchanges().slice(1)]));
  }
});

test("a state that lasts is refused after the re-reads", async () => {
  const outcome = await run(Array.from({ length: 1 + RETRIES }, () => status(count("status.state_self_test"))));
  refused(outcome, new RegExp(`stayed self-test through ${RETRIES} more readings`));
  assert.equal(outs(outcome), 1 + RETRIES);
});

test("silence counts toward the re-reads", async () => {
  const outcome = await run([status(count("status.state_initializing")), ...Array.from({ length: RETRIES }, silent)]);
  refused(outcome, new RegExp(`drew no reply on any of ${RETRIES} more tries`));
});

test("after the reset the unit must be idle, with nothing unretrieved", async () => {
  const outcome = await run([...exchanges().slice(0, 2),
    status(count("status.state_idle") + count("status.unretrieved_data_flag"))]);
  refused(outcome, /after the reset the unit is not idle: idle with data unretrieved/);
});

test("an error after channel setup is refused", async () => {
  const variant = exchanges();
  variant[4] = status(count("status.state_idle"), 1);
  refused(await run(variant), /the error register is \+1\.00000E\+00 after Command 1 \(status\.error_position, page /);
});

test("anything after Commands 0 and 1, or after Command 9's reply, is named and kept", async () => {
  const stray = packets([written(1)]);
  const variant = exchanges();
  variant[1] = [...exchange(1), ...stray];
  variant[3] = [...exchange(3), ...stray];
  variant[5] = [...exchange(5), ...stray];
  const outcome = await run(variant);
  whole(outcome);
  assert.deepEqual(outcome.session.findings, [
    `64 bytes came after Command 0, which page 30 says returns nothing (command.reset_reply, page 30)`,
    `64 bytes came after Command 1, which page 32 says returns nothing (command.channel_setup_reply, page 32)`,
    "64 bytes came after Command 9's reply",
  ]);
  assert.equal(outcome.recording.transfers.length, FIXTURE.transfers.length + 3);
});

test("a reply's packet of another size than the manual's multiple is named, and a stray one only as a stray", async () => {
  const multiple = count("usb.in_transfer_multiple");
  const [out, ...ins] = exchange(0);
  const reply = fromHex(ins.map((transfer) => transfer.bytes).join(" "));
  const first = reply.subarray(0, multiple - 16);
  const rest = new Uint8Array(Math.ceil((reply.length - first.length) / multiple) * multiple);
  rest.set(reply.subarray(first.length));
  const stray = new Uint8Array(multiple - 16);
  const variant = exchanges();
  variant[0] = [out as FixtureTransfer, { direction: "IN", micros: 1000, bytes: toHex(first) },
    { direction: "IN", micros: 2000, bytes: toHex(rest) }];
  variant[1] = [...exchange(1), { direction: "IN", micros: 3000, bytes: toHex(stray) }];
  const outcome = await run(variant);
  whole(outcome);
  assert.deepEqual(outcome.session.findings, [
    `a packet of ${multiple - 16} bytes, where transfers to the host come in multiples of ${multiple} `
      + `(${cite("usb.in_transfer_multiple")})`,
    `${multiple - 16} bytes came after Command 0, which page 30 says returns nothing (${cite("command.reset_reply")})`,
  ]);
});

test("Command 9's value written another way is refused", async () => {
  const variant = exchanges();
  variant[5] = [READING[0] as FixtureTransfer, ...packets(["+x.94383E+00"])];
  refused(await run(variant), new RegExp(`value 1 of the reply, "\\+x\\.94383E\\+00", is not written `
    + `${text("data.ascii_number_format")}`));
});

test("Command 9's reply of two values is refused", async () => {
  const variant = exchanges();
  variant[5] = [READING[0] as FixtureTransfer, ...packets([written(1), written(2)])];
  refused(await run(variant), /Command 9's reply holds 2 values, not one/);
});

test("the live reading checks for errors every tenth reading", async () => {
  const outcome = await run([...exchanges(), ...Array.from({ length: ERROR_EVERY }, () => READING), status(), READING],
    { live: { every: 0, readings: ERROR_EVERY + 1 } });
  assert.equal(whole(outcome).live.length, ERROR_EVERY + 1);
});

test("a stopped live reading ends, and keeps what it read", async () => {
  const stopper = new AbortController();
  let readings = 0;
  const outcome = await run([...exchanges(), READING, READING], { live: { every: 0, readings: 5, signal: stopper.signal } },
    (line) => {
      if (/ s {2}/.test(line) && ++readings === 2) {
        stopper.abort();
      }
    });
  const ch1 = whole(outcome);
  assert.equal(ch1.stopped, true);
  assert.equal(ch1.live.length, 2);
  assert.ok(outcome.said.includes("stopped by the operator; the transfers made so far are kept"));
});

test("live options that would not end, or are out of range, are refused before the reset", async () => {
  const bad: Live[] = [
    { every: -1, readings: 1 }, { every: Number.NaN, readings: 1 }, { every: MAX_EVERY_SECONDS + 1, readings: 1 },
    { every: 1 }, { every: 1, readings: 0 }, { every: 1, readings: 1.5 }, { every: 1, seconds: 0 },
    { every: 1, seconds: Number.POSITIVE_INFINITY },
  ];
  for (const live of bad) {
    assert.throws(() => checkLive(live), StatusRefused, JSON.stringify(live));
    const outcome = await run(exchanges(), { live });
    refused(outcome, /./);
    assert.equal(outs(outcome), 1, `${JSON.stringify(live)}: only the first Command 7 is sent`);
  }
  checkLive({ every: MAX_EVERY_SECONDS, seconds: 10 * MAX_EVERY_SECONDS });
});

test("the counts are the bench script's", () => {
  assert.deepEqual([RETRIES, RETRY_MS, ERROR_EVERY, QUIET_MS, MAX_EVERY_SECONDS], [5, 1000, 10, 300, 86400]);
  assert.deepEqual([...RESETTABLE], ["status.state_idle", "status.state_done"]);
  assert.deepEqual([...WAITING], ["status.state_initializing", "status.state_self_test"]);
});

test("the recording keeps what each write took and each read gave, with its time", async () => {
  let now = 1000;
  const writes: Uint8Array[] = [];
  const inner = {
    name: "planted",
    open: async () => undefined,
    close: async () => undefined,
    write: async (data: Uint8Array) => {
      writes.push(data);
      return data.length - 1;
    },
    read: async () => Uint8Array.of(0x7b, 0x7d),
  };
  const recording = new RecordingTransport(inner, () => now);
  now = 1500;
  recording.start();
  now = 1502.5;
  assert.equal(await recording.write(Uint8Array.of(1, 2, 3)), 2);
  now = 1510;
  await recording.read(10);
  assert.deepEqual(recording.transfers, [
    { direction: "OUT", ms: 2.5, bytes: "01 02" },
    { direction: "IN", ms: 10, bytes: "7b 7d" },
  ]);
});

test("a read that times out is not kept", async () => {
  const link = new MemoryTransport();
  await link.open();
  const recording = new RecordingTransport(link);
  await assert.rejects(recording.read(5));
  assert.deepEqual(recording.transfers, []);
});

test("the serial keeps its first three and last two characters", () => {
  assert.equal(maskSerial("ABC12345XY"), "ABC*****XY");
  assert.equal(maskSerial("ABCDEF"), "ABC*EF");
  assert.equal(maskSerial("ABCDE"), "*****");
  assert.equal(maskSerial("none"), "none");
  assert.equal(maskSerial("unreadable"), "unreadable");
});

test("device strings are trimmed, and blank or unprintable ones named", () => {
  assert.equal(deviceString("  A Maker "), "A Maker");
  assert.equal(deviceString("   "), "none");
  assert.equal(deviceString(null), "none");
  assert.equal(deviceString(undefined), "none");
  assert.equal(deviceString("A\u0001B"), "unreadable");
  assert.equal(deviceString("A\u00a0B"), "unreadable");
});

test("the date is local time with its offset, to the second", () => {
  const when = new Date(Date.UTC(2026, 10, 20, 18, 4, 5, 678));
  const date = localDate(when);
  assert.match(date, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$/);
  assert.equal(new Date(date).getTime(), Date.UTC(2026, 10, 20, 18, 4, 5));
});

test("the host is the platform and the browser, from the browser's hints", () => {
  assert.deepEqual(describeHost({
    platform: "macOS", platformVersion: "15.1.0",
    fullVersionList: [{ brand: "Not_A Brand", version: "8.0.0.0" }, { brand: "Chromium", version: "131.0.6778.86" },
      { brand: "Google Chrome", version: "131.0.6778.86" }],
  }), { os: "macOS 15.1.0", stack: "Google Chrome 131.0.6778.86, WebUSB" });
  assert.deepEqual(describeHost({ platform: "Linux", fullVersionList: [{ brand: "Chromium", version: "130.0.1" }] }),
    { os: "Linux", stack: "Chromium 130.0.1, WebUSB" });
  assert.deepEqual(describeHost(null), { os: "unknown", stack: "a browser that gave no version, WebUSB" });
});
