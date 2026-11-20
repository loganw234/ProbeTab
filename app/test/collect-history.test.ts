// Held here: the screen's history. The last run is saved and restored from one versioned key;
// data that is not a run this page wrote is ignored, never trusted and never a failure; storage
// that throws, is full, or is missing leaves the page working; the °F choice has a key of its own.
//
// Not held: two tabs sharing the one key (a stated limit), and the real localStorage (this uses a
// fake; the page's own glue passes window.localStorage, which only a browser tries).
import { test } from "node:test";
import assert from "node:assert/strict";
import { History, RUN_KEY, UNIT_KEY, parseRun } from "../src/collect/history.ts";
import { practiceCelsius } from "../src/collect/practice.ts";
import type { KeptRun, Reading } from "../src/collect/types.ts";
import { FullStorage, MemoryStorage, ThrowingStorage } from "./collect-fakes.ts";

function sampleRun(n = 3): KeptRun {
  const readings: Reading[] = Array.from({ length: n }, (_, k) => ({ t: k * 5, v: practiceCelsius(k * 5) }));
  return {
    version: 1,
    practice: true,
    storedUnit: "C",
    startedAt: "2026-11-19T20:14:00.000Z",
    settings: { everySeconds: 5, forSeconds: 120 },
    end: "open",
    readings,
  };
}

test("the keys are named for this page and carry a version", () => {
  assert.equal(RUN_KEY, "probetab.collect.lastRun.v1");
  assert.match(UNIT_KEY, /^probetab\.collect\.[a-z]+\.v\d+$/);
  assert.notEqual(RUN_KEY, UNIT_KEY);
});

test("a saved run comes back exactly, from the one key", () => {
  const storage = new MemoryStorage();
  const history = new History(() => storage);
  const run = sampleRun(25);
  assert.equal(history.loadRun(), null, "nothing kept yet");
  assert.equal(history.saveRun(run), true);
  assert.deepEqual([...storage.map.keys()], [RUN_KEY]);
  assert.deepEqual(history.loadRun(), run);
});

test("only the last run is kept: a save replaces, and clear removes", () => {
  const storage = new MemoryStorage();
  const history = new History(() => storage);
  history.saveRun(sampleRun(3));
  history.saveRun({ ...sampleRun(5), end: "done" });
  assert.equal(history.loadRun()?.readings.length, 5);
  assert.equal(storage.map.size, 1);
  assert.equal(history.clearRun(), true);
  assert.equal(history.loadRun(), null);
  assert.equal(storage.map.size, 0);
});

test("data of an unknown version or shape is ignored without failing", () => {
  const good = sampleRun();
  const bad: [string, string][] = [
    ["not JSON", "{not json"],
    ["empty text", ""],
    ["null", "null"],
    ["an array", "[]"],
    ["a number", "7"],
    ["a later version", JSON.stringify({ ...good, version: 2 })],
    ["no version", JSON.stringify({ ...good, version: undefined })],
    ["a unit other than the stored Celsius", JSON.stringify({ ...good, storedUnit: "F" })],
    ["no unit", JSON.stringify({ ...good, storedUnit: undefined })],
    ["practice as text", JSON.stringify({ ...good, practice: "yes" })],
    ["no start time", JSON.stringify({ ...good, startedAt: undefined })],
    ["settings missing", JSON.stringify({ ...good, settings: undefined })],
    ["an interval of zero", JSON.stringify({ ...good, settings: { everySeconds: 0, forSeconds: 120 } })],
    ["a length as text", JSON.stringify({ ...good, settings: { everySeconds: 5, forSeconds: "120" } })],
    ["an end it never writes", JSON.stringify({ ...good, end: "exploded" })],
    ["readings not a list", JSON.stringify({ ...good, readings: {} })],
    ["a reading as text", JSON.stringify({ ...good, readings: [{ t: "0", v: 75 }] })],
    ["a reading with no value", JSON.stringify({ ...good, readings: [{ t: 0 }] })],
    ["a reading with a null value", JSON.stringify({ ...good, readings: [{ t: 0, v: null }] })],
    ["a negative time", JSON.stringify({ ...good, readings: [{ t: -1, v: 75 }] })],
    ["a reading that is not an object", JSON.stringify({ ...good, readings: [5] })],
  ];
  for (const [what, text] of bad) {
    assert.equal(parseRun(text), null, what);
    const storage = new MemoryStorage();
    storage.setItem(RUN_KEY, text);
    assert.equal(new History(() => storage).loadRun(), null, `loaded: ${what}`);
  }
  assert.deepEqual(parseRun(JSON.stringify(good)), good, "the same text, undamaged, is read");
});

test("a run read back holds only the fields it knows", () => {
  const read = parseRun(JSON.stringify({ ...sampleRun(1), extra: "ignored", readings: [{ t: 0, v: 75, more: 1 }] }));
  assert.deepEqual(Object.keys(read ?? {}).sort(), ["end", "practice", "readings", "settings", "startedAt", "storedUnit", "version"]);
  assert.deepEqual(read?.readings[0], { t: 0, v: 75 });
});

test("storage that throws on every call: no history, no failure", () => {
  const history = new History(() => new ThrowingStorage());
  assert.equal(history.available(), false);
  assert.equal(history.loadRun(), null);
  assert.equal(history.saveRun(sampleRun()), false);
  assert.equal(history.clearRun(), false);
  assert.equal(history.loadUnit(), "C");
  assert.equal(history.saveUnit("F"), false);
});

test("storage that cannot even be opened, or is missing: no history, no failure", () => {
  for (const open of [
    () => {
      throw new Error("SecurityError");
    },
    () => null,
  ]) {
    const history = new History(open);
    assert.equal(history.available(), false);
    assert.equal(history.loadRun(), null);
    assert.equal(history.saveRun(sampleRun()), false);
    assert.equal(history.clearRun(), false);
    assert.equal(history.loadUnit(), "C");
    assert.equal(history.saveUnit("F"), false);
  }
});

test("a full storage reads what it holds and says a save did not happen", () => {
  const storage = new FullStorage();
  storage.map.set(RUN_KEY, JSON.stringify(sampleRun(2)));
  const history = new History(() => storage);
  assert.equal(history.available(), false, "it cannot take a write");
  assert.equal(history.saveRun(sampleRun(9)), false);
  assert.equal(history.loadRun()?.readings.length, 2, "the older run is still there");
  assert.equal(history.saveUnit("F"), false);
});

test("a working storage is available, and the probe leaves nothing behind", () => {
  const storage = new MemoryStorage();
  assert.equal(new History(() => storage).available(), true);
  assert.equal(storage.map.size, 0);
});

test("the °F choice has a key of its own, and anything unreadable means Celsius", () => {
  const storage = new MemoryStorage();
  const history = new History(() => storage);
  assert.equal(history.loadUnit(), "C");
  assert.equal(history.saveUnit("F"), true);
  assert.equal(storage.map.get(UNIT_KEY), "F");
  assert.equal(history.loadUnit(), "F");
  history.saveUnit("C");
  assert.equal(history.loadUnit(), "C");
  storage.map.set(UNIT_KEY, "kelvin");
  assert.equal(history.loadUnit(), "C");
  // Clearing the run leaves the choice alone.
  history.saveUnit("F");
  history.saveRun(sampleRun());
  history.clearRun();
  assert.equal(history.loadUnit(), "F");
});

test("the size of the longest run: 30 minutes at one reading a second", () => {
  const readings = Array.from({ length: 1801 }, (_, k) => ({ t: k, v: practiceCelsius(k) }));
  const run = { ...sampleRun(1), readings };
  const bytes = JSON.stringify(run).length;
  // MEASURED here, not assumed: the plan's "tens of kilobytes". localStorage holds about 5 million
  // characters in a browser (BELIEVED, from the browser's usual quota), so this fits many times over.
  console.log(`# 1801 readings, JSON of ${bytes} characters`);
  assert.ok(bytes < 200_000, `${bytes}`);
});
