// The bench page's glue to the browser: its buttons, its log and its record. The steps are
// in session.ts and the evidence in record.ts, which the tests run on Node. This file is not
// tested on Node, and is first run in a browser at Phase 0.

import { count } from "../protocol/facts.ts";
import { FORMS, type Form } from "../protocol/status.ts";
import { WebUsbTransport, requestLabPro, type USBDeviceLike, type USBLike } from "../transport/webusb.ts";
import { BenchSession, checkLive, readCh1, type Live } from "./session.ts";
import {
  RECORD_FORMAT, RecordingTransport, deviceString, hostOf, localDate, maskSerial,
  type BrowserRecord, type UADataLike,
} from "./record.ts";

/** The strings WebUSB gives a device, which webusb.ts's declarations leave out. */
interface NamedDevice extends USBDeviceLike {
  readonly manufacturerName?: string | null;
  readonly productName?: string | null;
  readonly serialNumber?: string | null;
}

const browser = navigator as unknown as { readonly usb?: USBLike; readonly userAgentData?: UADataLike };

function element<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (found === null) {
    throw new Error(`the page has no element #${id}`);
  }
  return found as T;
}

const formChoice = element<HTMLSelectElement>("form");
const buttons = {
  connect: element<HTMLButtonElement>("connect"),
  status: element<HTMLButtonElement>("status"),
  read: element<HTMLButtonElement>("read"),
  stop: element<HTMLButtonElement>("stop"),
  save: element<HTMLButtonElement>("save"),
  disconnect: element<HTMLButtonElement>("disconnect"),
};
const discard = element<HTMLInputElement>("discard");
const every = element<HTMLInputElement>("every");
const readings = element<HTMLInputElement>("readings");
const seconds = element<HTMLInputElement>("seconds");
const log = element<HTMLPreElement>("log");
const table = element<HTMLTableSectionElement>("transfers");

function say(line: string): void {
  log.textContent += line + "\n";
  log.scrollTop = log.scrollHeight;
}

/** What one connection gathers, for the record the page saves. */
interface Connection {
  readonly transport: WebUsbTransport;
  readonly recording: RecordingTransport;
  readonly session: BenchSession;
  readonly date: string;
  readonly os: string;
  readonly stack: string;
  readonly form: Form;
  readonly manufacturer: string;
  readonly product: string;
  readonly serial: string;
  firmware: string;
  closed: boolean;
  readonly refusals: string[];
}

/** The page's one connection: a second needs the page reloaded, so that a record is never
 * replaced unsaved. */
let connection: Connection | null = null;
let busy = false;
let stopper: AbortController | null = null;

function settle(): void {
  const open = connection !== null && !connection.closed;
  buttons.connect.disabled = busy || connection !== null;
  formChoice.disabled = busy || connection !== null;
  buttons.status.disabled = busy || !open;
  buttons.read.disabled = busy || !open;
  buttons.disconnect.disabled = busy || !open;
  buttons.stop.disabled = stopper === null;
  buttons.save.disabled = busy || connection === null || connection.recording.transfers.length === 0;
}

function showTransfers(): void {
  const rows = connection?.recording.transfers ?? [];
  table.replaceChildren(...rows.map((transfer) => {
    const row = document.createElement("tr");
    const text = transfer.bytes === "" ? "" : String.fromCharCode(...transfer.bytes.split(" ").map((byte) => {
      const code = Number.parseInt(byte, 16);
      return code >= 0x20 && code < 0x7f ? code : 0xb7;
    }));
    for (const cell of [transfer.direction, transfer.ms.toFixed(1), transfer.bytes, text]) {
      const data = document.createElement("td");
      data.textContent = cell;
      row.append(data);
    }
    return row;
  }));
}

/** Runs one step at a time: a second click while a step runs does nothing. Whatever a step
 * refuses is said and kept in the record. */
async function step(work: (open: Connection | null) => Promise<void>): Promise<void> {
  if (busy) {
    return;
  }
  busy = true;
  settle();
  try {
    await work(connection);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    say(`refused: ${message}`);
    connection?.refusals.push(message);
  } finally {
    busy = false;
    stopper = null;
    showTransfers();
    settle();
  }
}

function showStatus(values: readonly string[]): void {
  say("Command 7's values, in order (protocol/REFERENCE.md names them):");
  values.forEach((value, index) => say(`  ${String(index + 1).padStart(2)}  ${value}`));
}

buttons.connect.addEventListener("click", () => void step(async () => {
  const usb = browser.usb;
  if (usb === undefined) {
    throw new Error("this browser offers no WebUSB; Chrome and Edge do, on a page served from localhost");
  }
  const device = await requestLabPro(usb) as NamedDevice;
  const transport = new WebUsbTransport(device);
  const recording = new RecordingTransport(transport);
  await recording.open();
  const host = await hostOf(browser.userAgentData);
  const form = formChoice.value as Form;
  const open: Connection = {
    transport, recording, session: new BenchSession(recording, { form, say }),
    date: localDate(new Date()), os: host.os, stack: host.stack, form,
    manufacturer: deviceString(device.manufacturerName), product: deviceString(device.productName),
    serial: maskSerial(deviceString(device.serialNumber)), firmware: "unknown", closed: false, refusals: [],
  };
  connection = open;
  say(`connected: ${open.manufacturer}, ${open.product}, serial ${open.serial}; ${open.stack} on ${open.os}`);
  if (transport.configuredHere) {
    say("no configuration was active, so the page selected the device's first");
  }
  recording.start();
  const values = await open.session.status();
  open.firmware = values[count("status.software_id_position") - 1] ?? "unknown";
  showStatus(values);
}));

buttons.status.addEventListener("click", () => void step(async (open) => {
  if (open !== null && !open.closed) {
    showStatus(await open.session.status());
  }
}));

function number(input: HTMLInputElement): number | undefined {
  return input.value.trim() === "" ? undefined : Number(input.value);
}

buttons.read.addEventListener("click", () => void step(async (open) => {
  if (open === null || open.closed) {
    return;
  }
  const interval = number(every);
  let live: Live | undefined;
  if (interval !== undefined) {
    stopper = new AbortController();
    const wanted = number(readings);
    const limit = number(seconds);
    live = {
      every: interval,
      signal: stopper.signal,
      ...(wanted === undefined ? {} : { readings: wanted }),
      ...(limit === undefined ? {} : { seconds: limit }),
    };
    checkLive(live);
    settle();
  }
  const first = await open.session.status();
  const ch1 = await readCh1(open.session, first, { discard: discard.checked, ...(live === undefined ? {} : { live }) });
  say(`read ${ch1.live.length} live readings${ch1.stopped ? ", then stopped" : ""}`);
  for (const finding of open.session.findings) {
    say(`differs from the manual: ${finding}`);
  }
}));

buttons.stop.addEventListener("click", () => {
  stopper?.abort();
});

buttons.save.addEventListener("click", () => {
  const open = connection;
  if (open === null) {
    return;
  }
  const record: BrowserRecord = {
    format: RECORD_FORMAT, date: open.date, os: open.os, stack: open.stack, firmware: open.firmware,
    form: open.form, manufacturer: open.manufacturer, product: open.product, serial: open.serial,
    refusals: [...open.refusals], findings: [...open.session.findings], transfers: [...open.recording.transfers],
  };
  const blob = new Blob([JSON.stringify(record, null, 2) + "\n"], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `probetab-bench-${open.date.replaceAll(":", "-")}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  say(`saved ${record.transfers.length} transfers as ${link.download}`);
});

buttons.disconnect.addEventListener("click", () => void step(async (open) => {
  if (open !== null && !open.closed) {
    open.closed = true;
    await open.recording.close();
    say("closed the connection; the record stays until the page is reloaded");
  }
}));

for (const form of FORMS) {
  const option = document.createElement("option");
  option.value = form;
  option.textContent = form;
  formChoice.append(option);
}
say(`ready: choose the framing (${FORMS[0]} is the bench script's default), then Connect`);
settle();
