// Command 7 and its reply, against the simulated LabPro replaying the fixture, as the bench
// script's tests run it against the fake pyusb backend.

import { test } from "node:test";
import assert from "node:assert/strict";
import { FakeLabPro, fromHex, toHex } from "./fake-labpro.ts";
import { FIXTURES, type FixtureTransfer } from "./generated/fixtures.ts";
import { LABPRO_FACTS } from "../src/generated/labpro-facts.ts";
import { cite, count, text } from "../src/protocol/facts.ts";
import { FORMS, MAX_READS, StatusRefused, requestStatus, statusRequest } from "../src/protocol/status.ts";
import { MemoryTransport } from "../src/transport/memory.ts";
import type { Transport } from "../src/transport/transport.ts";

const NAME = "status-request.trace";
const FIXTURE = FIXTURES[NAME];
if (FIXTURE === undefined) {
  throw new Error(`the generated fixtures have no ${NAME}`);
}
const TIMEOUT_MS = 100;

function commandSent(): string {
  const out = FIXTURE.transfers.find((transfer) => transfer.direction === "OUT");
  if (out === undefined) {
    throw new Error(`${NAME} has no OUT`);
  }
  return out.bytes;
}

function reply(): FixtureTransfer[] {
  return FIXTURE.transfers.filter((transfer) => transfer.direction === "IN");
}

/** The fixture's reply values, read here without the protocol code's help. */
function replyValues(): string[] {
  const data = fromHex(reply().map((transfer) => transfer.bytes).join(" "));
  const all = new TextDecoder().decode(data);
  const message = all.slice(0, all.indexOf(text("reply.terminator"))).trim();
  return message.slice(text("command.open").length, -text("command.close").length)
    .split(text("command.separator")).map((value) => value.trim());
}

/** data padded with zeros to whole packets of size bytes, as IN transfers. */
function packetsOf(data: Uint8Array, size = count("usb.packet_size")): FixtureTransfer[] {
  const padded = new Uint8Array(Math.ceil(data.length / size) * size);
  padded.set(data);
  const transfers: FixtureTransfer[] = [];
  for (let at = 0; at < padded.length; at += size) {
    transfers.push({ direction: "IN", micros: 1000, bytes: toHex(padded.subarray(at, at + size)) });
  }
  return transfers;
}

function packets(values: readonly string[], size?: number): FixtureTransfer[] {
  const separator = text("command.separator") + " ";
  const message = text("command.open") + " " + values.join(separator) + text("command.close") + text("reply.terminator");
  return packetsOf(new TextEncoder().encode(message), size);
}

function withReply(values: readonly string[]): FixtureTransfer[] {
  return [{ direction: "OUT", micros: 0, bytes: commandSent() }, ...packets(values)];
}

async function replaying(transfers: readonly FixtureTransfer[] = FIXTURE.transfers) {
  const link = new MemoryTransport();
  await link.open();
  const fake = new FakeLabPro({ model: "a test's trace", transfers }, transfers === FIXTURE.transfers ? NAME : "a test's trace",
    link.device, 200);
  return { link, fake };
}

async function refusal(transfers: readonly FixtureTransfer[], pattern: RegExp): Promise<FakeLabPro> {
  const { link, fake } = await replaying(transfers);
  await assert.rejects(requestStatus(link, { timeoutMs: TIMEOUT_MS }), (error: unknown) => {
    assert.ok(error instanceof StatusRefused, `${String(error)} is not a StatusRefused`);
    assert.match(error.message, pattern);
    return true;
  });
  await fake.finished;
  return fake;
}

test("replays the fixture: the status, with every transfer used", async () => {
  const { link, fake } = await replaying();
  const status = await requestStatus(link, { timeoutMs: TIMEOUT_MS });
  await fake.finished;
  assert.equal(fake.mismatch, null);
  assert.equal(fake.remaining.length, 0, "the protocol code left part of the fixture unread");
  assert.equal(status.values.length, count("status.register_count"));
  assert.equal(status.softwareId, replyValues()[count("status.software_id_position") - 1]);
});

test("each form sends its bytes", async () => {
  const prefix = text("command.prefix");
  const terminator = text("command.serial_terminator");
  const full = new TextDecoder().decode(fromHex(commandSent()));
  assert.ok(full.startsWith(prefix) && full.endsWith(terminator), full);
  const expected = {
    "s-cr": full,
    "s": full.slice(0, -terminator.length),
    "cr": full.slice(prefix.length),
    "bare": full.slice(prefix.length, -terminator.length),
  };
  assert.deepEqual(Object.keys(expected).sort(), [...FORMS].sort());
  for (const form of FORMS) {
    assert.equal(new TextDecoder().decode(statusRequest(form)), expected[form], form);
    const bytes = toHex(new TextEncoder().encode(expected[form]));
    const { link, fake } = await replaying([{ direction: "OUT", micros: 0, bytes }, ...reply()]);
    await requestStatus(link, { form, timeoutMs: TIMEOUT_MS });
    await fake.finished;
    assert.equal(fake.mismatch, null, form);
  }
});

test("the fake names bytes the fixture does not hold", async () => {
  const { link, fake } = await replaying();
  await assert.rejects(requestStatus(link, { form: "bare", timeoutMs: TIMEOUT_MS }), StatusRefused);
  await fake.finished;
  assert.match(fake.mismatch ?? "", new RegExp(`where ${NAME} has OUT ${commandSent()}`));
});

test("no reply is refused", async () => {
  await refusal([{ direction: "OUT", micros: 0, bytes: commandSent() }],
    new RegExp(`no reply came within ${TIMEOUT_MS} ms of Command 7`));
});

test("a reply without its end is refused", async () => {
  const first = reply()[0];
  assert.ok(first !== undefined);
  await refusal([{ direction: "OUT", micros: 0, bytes: commandSent() }, first],
    new RegExp(`stopped after ${fromHex(first.bytes).length} bytes without its end`));
});

test("a reply of one value too few is refused", async () => {
  const values = replyValues().slice(0, -1);
  await refusal(withReply(values), new RegExp(`holds ${values.length} values, not ${count("status.register_count")}`));
});

test("a wrong check value is refused", async () => {
  const values = replyValues();
  values[count("status.check_value_position") - 1] = "+8.88700E+03";
  await refusal(withReply(values), new RegExp(cite("status.check_value")));
});

test("a value written another way is refused", async () => {
  const values = replyValues();
  values[1] = "0.0";
  await refusal(withReply(values), new RegExp(`value 2 of the reply, "0.0", is not written ${text("data.ascii_number_format")}`));
});

test("a value with anything around it is refused", async () => {
  const values = replyValues();
  values[1] = `${values[1]}x`;
  await refusal(withReply(values), new RegExp(`value 2 of the reply, "${values[1].replace(/[+.]/g, "\\$&")}", is not written`));
});

test("spaces around the reply are allowed", async () => {
  const separator = text("command.separator") + " ";
  const message = " " + text("command.open") + " " + replyValues().join(separator) + text("command.close") + " "
    + text("reply.terminator");
  const { link, fake } = await replaying([{ direction: "OUT", micros: 0, bytes: commandSent() },
    ...packetsOf(new TextEncoder().encode(message))]);
  const status = await requestStatus(link, { timeoutMs: TIMEOUT_MS });
  await fake.finished;
  assert.equal(status.values.length, count("status.register_count"));
});

test("cite names the fact and its page", () => {
  assert.equal(cite("usb.vendor_id"), `usb.vendor_id, page ${LABPRO_FACTS["usb.vendor_id"]?.page}`);
});

test("a reply outside braces is refused", async () => {
  const message = replyValues().join(text("command.separator") + " ") + text("reply.terminator");
  const quoted = (literal: string) => literal.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  await refusal([{ direction: "OUT", micros: 0, bytes: commandSent() }, ...packetsOf(new TextEncoder().encode(message))],
    new RegExp(`is not one list in ${quoted(text("command.open"))} and ${quoted(text("command.close"))}`));
});

test("a reply that is not ASCII is refused", async () => {
  const data = Uint8Array.of(0xff, ...new TextEncoder().encode(text("reply.terminator")));
  await refusal([{ direction: "OUT", micros: 0, bytes: commandSent() }, ...packetsOf(data)], /not ASCII text: ff/);
});

test("a reply with no end in its reads is refused", async () => {
  const filler: FixtureTransfer[] = Array.from({ length: MAX_READS + 1 },
    () => ({ direction: "IN", micros: 1000, bytes: toHex(new Uint8Array(count("usb.packet_size"))) }));
  const fake = await refusal([{ direction: "OUT", micros: 0, bytes: commandSent() }, ...filler],
    new RegExp(`no end of reply in ${MAX_READS} reads`));
  assert.equal(fake.remaining.length, 0, "the fake queues every IN once the OUT has arrived");
});

test("a short write is refused", async () => {
  const short: Transport = {
    name: "short",
    open: async () => undefined,
    close: async () => undefined,
    write: async (data: Uint8Array) => data.length - 2,
    read: async () => new Uint8Array(0),
  };
  const sent = statusRequest();
  await assert.rejects(requestStatus(short), new RegExp(`only ${sent.length - 2} of Command 7's ${sent.length} bytes were taken`));
});

test("a transport's own error passes through, unrenamed", async () => {
  const planted = new Error("planted error");
  const failing: Transport = {
    name: "failing",
    open: async () => undefined,
    close: async () => undefined,
    write: async (data: Uint8Array) => data.length,
    read: async () => {
      throw planted;
    },
  };
  await assert.rejects(requestStatus(failing), (error: unknown) => error === planted);
});
