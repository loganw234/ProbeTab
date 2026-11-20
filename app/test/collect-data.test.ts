// Held here: the classroom screen's numbers and its file. The practice source's readings are the
// formula its comment names (and the mockup's table); °F is applied once, at the edge, and never
// to stored readings; the CSV's order, header, unit and practice line.
//
// Controls (planted by hand in the code, seen to fail, restored to the file's hash) are recorded in
// the ledger's parcel-collect.md, not here.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { BOM, csvCell, fileName, toCsv } from "../src/collect/csv.ts";
import { PracticeSource, practiceCelsius, readingCount } from "../src/collect/practice.ts";
import { formatTemp, inUnit, toFahrenheit, unitLabel } from "../src/collect/units.ts";
import { PRACTICE_FILE_NOTE } from "../src/collect/words.ts";
import type { Reading } from "../src/collect/types.ts";
import { ManualTimers } from "./collect-fakes.ts";

const PRACTICE_TS = new URL("../src/collect/practice.ts", import.meta.url);
const MOCKUP = new URL("../mockup/index.html", import.meta.url);

test("Fahrenheit is C x 9/5 + 32, at the scale's own fixed points", () => {
  assert.equal(toFahrenheit(0), 32);
  assert.equal(toFahrenheit(100), 212);
  assert.equal(toFahrenheit(-40), -40);
  assert.equal(inUnit(100, "F"), 212);
  assert.equal(inUnit(100, "C"), 100);
  assert.equal(unitLabel("F"), "°F");
  assert.equal(unitLabel("C"), "°C");
});

test("a reading is converted once, then rounded to 0.1", () => {
  assert.equal(formatTemp(75, "C"), "75.0");
  assert.equal(formatTemp(75, "F"), "167.0");
  assert.equal(formatTemp(100, "F"), "212.0");
  // 54.93 C is 130.874 F: converted once from the stored value, not from a rounded 54.9 (130.82 -> 130.8).
  assert.equal(formatTemp(54.93, "F"), "130.9");
  assert.equal(formatTemp(54.93, "C"), "54.9");
});

test("the practice source's formula is the one its comment names", () => {
  const source = readFileSync(PRACTICE_TS, "utf8");
  const f = source.match(/FORMULA: T\(t\) = ([\d.]+) \+ ([\d.]+)\*exp\(-t\/([\d.]+)\) \+ ([\d.]+)\*sin\(t\/([\d.]+)\)/);
  assert.ok(f, "no FORMULA line in practice.ts");
  const [A, B, C, D, E] = f.slice(1).map(Number) as [number, number, number, number, number];
  for (const t of [0, 1, 5, 37, 70, 120, 600, 1800]) {
    assert.equal(practiceCelsius(t), A + B * Math.exp(-t / C) + D * Math.sin(t / E), `at ${t} seconds`);
  }
});

test("the practice source gives the mockup's table, to 0.1", () => {
  const html = readFileSync(MOCKUP, "utf8");
  const rows = [...html.matchAll(/<tr class="[^"]*"><td>(\d+)<\/td><td>([\d.]+)<\/td><\/tr>/g)];
  assert.equal(rows.length, 25);
  for (const [, t, v] of rows) {
    assert.equal(formatTemp(practiceCelsius(Number(t)), "C"), v, `at ${t} seconds`);
  }
});

test("a run's readings: one at 0 and one at each whole interval up to the length", () => {
  assert.equal(readingCount({ everySeconds: 5, forSeconds: 120 }), 25);
  assert.equal(readingCount({ everySeconds: 1, forSeconds: 60 }), 61);
  assert.equal(readingCount({ everySeconds: 60, forSeconds: 60 }), 2);
  assert.equal(readingCount({ everySeconds: 30, forSeconds: 1800 }), 61);
});

function run(source: PracticeSource, timers: ManualTimers, every: number, length: number) {
  const got: Reading[] = [];
  let ended = 0;
  source.start({ everySeconds: every, forSeconds: length }, (r) => got.push(r), () => (ended += 1));
  return { got, ended: () => ended, timers };
}

test("the practice source gives a reading now, then one each interval, and says when it is done", () => {
  const timers = new ManualTimers();
  const r = run(new PracticeSource(timers), timers, 5, 120);
  assert.equal(r.got.length, 1, "the first reading comes at once");
  assert.equal(r.got[0]?.t, 0);
  const waits: number[] = [];
  for (let w = timers.fire(); w !== null; w = timers.fire()) {
    waits.push(w);
  }
  assert.equal(r.got.length, 25);
  assert.deepEqual(waits, Array(24).fill(5000), "each wait is the interval");
  assert.deepEqual(r.got.map((x) => x.t), Array.from({ length: 25 }, (_, k) => k * 5));
  for (const x of r.got) {
    assert.equal(x.v, practiceCelsius(x.t), "the value is the source's own, in Celsius, unrounded");
  }
  assert.equal(r.ended(), 1);
  assert.equal(timers.waiting.size, 0);
});

test("a stopped practice source gives no more readings and no end", () => {
  const timers = new ManualTimers();
  const source = new PracticeSource(timers);
  const r = run(source, timers, 5, 120);
  timers.fire();
  timers.fire();
  assert.equal(r.got.length, 3);
  source.stop();
  assert.equal(timers.waiting.size, 0, "its timer is cleared");
  assert.equal(timers.drain(), 0);
  assert.equal(r.got.length, 3);
  assert.equal(r.ended(), 0);
});

test("starting a practice source again leaves the first one's timer dead", () => {
  const timers = new ManualTimers();
  const source = new PracticeSource(timers);
  const first = run(source, timers, 5, 60);
  const second = run(source, timers, 10, 60);
  timers.drain();
  assert.equal(first.got.length, 1, "only the reading it gave at once");
  assert.equal(second.got.length, 7);
});

const SAMPLE: Reading[] = [
  { t: 0, v: 75 },
  { t: 5, v: 73.46 },
  { t: 10, v: 100 },
];
const RUN = { practice: true, startedAt: new Date(2026, 10, 19, 20, 14).toISOString(), readings: SAMPLE };

function lines(csv: string): string[] {
  assert.ok(csv.startsWith(BOM), "starts with a byte-order mark");
  assert.ok(csv.endsWith("\r\n"), "ends with a line end");
  return csv.slice(BOM.length, -2).split("\r\n");
}

test("a practice run's file: the made-up line first, then the column names, then oldest first", () => {
  assert.deepEqual(lines(toCsv(RUN, "C")), [
    PRACTICE_FILE_NOTE,
    "Time (s),Temperature (°C)",
    "0,75.0",
    "5,73.5",
    "10,100.0",
  ]);
  assert.match(PRACTICE_FILE_NOTE, /made up/);
  assert.ok(!PRACTICE_FILE_NOTE.includes(","), "the note is one cell");
});

test("a real run's file starts with the column names, and says nothing of practice", () => {
  const csv = toCsv({ ...RUN, practice: false }, "C");
  assert.equal(lines(csv)[0], "Time (s),Temperature (°C)");
  assert.ok(!/made up|practice/i.test(csv));
});

test("the file in °F converts each stored reading once, and changes nothing stored", () => {
  const before = JSON.stringify(SAMPLE);
  assert.deepEqual(lines(toCsv(RUN, "F")), [
    PRACTICE_FILE_NOTE,
    "Time (s),Temperature (°F)",
    "0,167.0",
    "5,164.2",
    "10,212.0",
  ]);
  assert.equal(JSON.stringify(SAMPLE), before);
  // Saving twice, in either unit, gives the same text each time: no state carries over.
  assert.equal(toCsv(RUN, "F"), toCsv(RUN, "F"));
  assert.deepEqual(lines(toCsv(RUN, "C")).slice(2), ["0,75.0", "5,73.5", "10,100.0"]);
});

test("a cell with a comma or a quote is quoted, and a plain one is not", () => {
  // Not reachable with today's note, held so that a note with a comma could not split into two cells.
  assert.equal(csvCell("plain"), "plain");
  assert.equal(csvCell("a,b"), '"a,b"');
  assert.equal(csvCell('say "hi"'), '"say ""hi"""');
});

test("the file's name says practice for a practice run, and the start in the computer's own time", () => {
  assert.equal(fileName(RUN), "probetab-practice-run-2026-11-19-2014.csv");
  assert.equal(fileName({ ...RUN, practice: false }), "probetab-run-2026-11-19-2014.csv");
  assert.equal(fileName({ ...RUN, startedAt: "not a time" }), "probetab-practice-run-unknown-time.csv");
});
