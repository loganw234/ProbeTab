// Held here: the run's states and what each button does to the kept run. A kept run is never
// discarded without the question: Start, Collect another run and Clear each ask, every time. Readings
// are stored as the source gave them, whatever the °F toggle says. Storage that throws leaves
// the run working.
//
// Not held: the page's glue (page.ts), which wires these methods to buttons; two tabs.
import { test } from "node:test";
import assert from "node:assert/strict";
import { Collector, validSettings } from "../src/collect/collector.ts";
import { History, RUN_KEY } from "../src/collect/history.ts";
import { PracticeSource, practiceCelsius } from "../src/collect/practice.ts";
import type { Settings } from "../src/collect/types.ts";
import { CLEAR_QUESTION, REPLACE_QUESTION } from "../src/collect/words.ts";
import { ManualTimers, MemoryStorage, ThrowingStorage } from "./collect-fakes.ts";
import type { StorageLike } from "../src/collect/history.ts";

const SETTINGS: Settings = { everySeconds: 5, forSeconds: 120 };

function setup(storage: StorageLike = new MemoryStorage(), answers: boolean[] = []) {
  const timers = new ManualTimers();
  const asked: string[] = [];
  const history = new History(() => storage);
  const make = () =>
    new Collector({
      history,
      confirm: (q) => {
        asked.push(q);
        return answers.shift() ?? false;
      },
      makePractice: () => new PracticeSource(timers),
      now: () => new Date(2026, 10, 19, 20, 14),
    });
  return { storage, timers, asked, history, make, answers };
}

/** A collector that has finished a full practice run. */
function finished(s = setup()) {
  const c = s.make();
  c.connectPractice();
  assert.equal(c.start(SETTINGS), true);
  s.timers.drain();
  assert.equal(c.phase, "finished");
  return { c, s };
}

test("the four states, in order, for a full practice run", () => {
  const s = setup();
  const c = s.make();
  assert.equal(c.phase, "before");
  assert.equal(c.run, null);
  assert.equal(c.connectPractice(), true);
  assert.equal(c.phase, "ready");
  assert.equal(c.source?.practice, true);
  assert.equal(c.start(SETTINGS), true);
  assert.equal(c.phase, "collecting");
  assert.equal(c.run?.readings.length, 1, "the first reading comes at once");
  s.timers.drain();
  assert.equal(c.phase, "finished");
  assert.equal(c.run?.readings.length, 25);
  assert.equal(c.run?.end, "done");
  assert.equal(c.restored, false);
  assert.equal(c.run?.practice, true);
  assert.equal(c.run?.startedAt, new Date(2026, 10, 19, 20, 14).toISOString());
});

test("a button works only in its own state", () => {
  const s = setup();
  const c = s.make();
  assert.equal(c.start(SETTINGS), false, "Start before connecting");
  assert.equal(c.stop(), false);
  assert.equal(c.another(), false);
  assert.equal(c.clear(), false);
  c.connectPractice();
  assert.equal(c.connectPractice(), false, "a second connect");
  assert.equal(c.stop(), false, "Stop before Start");
  c.start(SETTINGS);
  assert.equal(c.start(SETTINGS), false, "Start while collecting");
  assert.equal(c.another(), false, "Collect another run while collecting");
  assert.equal(c.clear(), false, "Clear while collecting");
  assert.deepEqual(s.asked, []);
});

test("settings are the person's choices, from the lists, and nothing else starts a run", () => {
  assert.equal(validSettings(SETTINGS), true);
  assert.equal(validSettings({ everySeconds: 60, forSeconds: 60 }), true);
  assert.equal(validSettings({ everySeconds: 7, forSeconds: 120 }), false);
  assert.equal(validSettings({ everySeconds: 5, forSeconds: 119 }), false);
  assert.equal(validSettings({ everySeconds: 0, forSeconds: 120 }), false);
  const c = setup().make();
  c.connectPractice();
  assert.equal(c.start({ everySeconds: 5, forSeconds: 119 }), false);
  assert.equal(c.phase, "ready");
});

test("the run is saved after every reading, and at its end", () => {
  const s = setup();
  const c = s.make();
  c.connectPractice();
  c.start(SETTINGS);
  const stored = () => s.history.loadRun();
  assert.equal(stored()?.readings.length, 1);
  assert.equal(stored()?.end, "open");
  for (let n = 2; n <= 6; n += 1) {
    s.timers.fire();
    assert.equal(stored()?.readings.length, n, `after reading ${n}`);
    assert.equal(stored()?.end, "open");
  }
  s.timers.drain();
  assert.equal(stored()?.readings.length, 25);
  assert.equal(stored()?.end, "done");
});

test("Stop ends the run early, keeps the readings so far, and nothing more arrives", () => {
  const s = setup();
  const c = s.make();
  c.connectPractice();
  c.start(SETTINGS);
  s.timers.fire();
  s.timers.fire();
  assert.equal(c.stop(), true);
  assert.equal(c.phase, "finished");
  assert.equal(c.run?.end, "stopped");
  assert.equal(c.run?.readings.length, 3);
  assert.equal(s.timers.drain(), 0, "no timer is left");
  assert.equal(c.run?.readings.length, 3);
  assert.equal(s.history.loadRun()?.end, "stopped");
  assert.equal(s.history.loadRun()?.readings.length, 3);
});

test("a tab closed mid-run keeps what it had, and comes back marked open", () => {
  const s = setup();
  const c = s.make();
  c.connectPractice();
  c.start(SETTINGS);
  s.timers.fire();
  s.timers.fire();
  // The tab closes here: nothing more runs. A new page opens on the same storage.
  const reopened = s.make();
  assert.equal(reopened.phase, "finished");
  assert.equal(reopened.restored, true);
  assert.equal(reopened.run?.end, "open");
  assert.equal(reopened.run?.readings.length, 3);
  assert.equal(reopened.run?.practice, true);
  assert.equal(reopened.source, null, "nothing is connected after a restore");
});

test("a finished run comes back the next day, as it was", () => {
  const { s } = finished();
  const next = s.make();
  assert.equal(next.phase, "finished");
  assert.equal(next.restored, true);
  assert.equal(next.run?.end, "done");
  assert.equal(next.run?.readings.length, 25);
});

test("Start with a run kept in the browser asks first, and a no leaves everything as it was", () => {
  const s = setup(new MemoryStorage(), [false]);
  const c = s.make();
  c.connectPractice();
  // Another tab, or an earlier visit, left a run.
  const other = setup(s.storage);
  const old = finished(other).c.run;
  assert.ok(old !== null);
  const kept = s.storage.getItem(RUN_KEY);
  s.asked.length = 0;
  assert.equal(c.start(SETTINGS), false);
  assert.deepEqual(s.asked, [REPLACE_QUESTION]);
  assert.equal(c.phase, "ready");
  assert.equal(c.run, null);
  assert.equal(s.storage.getItem(RUN_KEY), kept, "the kept run is untouched");
  assert.equal(s.timers.waiting.size, 0, "no source started");
});

test("Start with a run kept, answered yes, replaces it", () => {
  const s = setup(new MemoryStorage(), [true]);
  const c = s.make();
  c.connectPractice();
  finished(setup(s.storage));
  s.asked.length = 0;
  assert.equal(c.start({ everySeconds: 10, forSeconds: 60 }), true);
  assert.deepEqual(s.asked, [REPLACE_QUESTION]);
  assert.equal(c.phase, "collecting");
  assert.equal(s.history.loadRun()?.settings.everySeconds, 10, "the new run replaced the old");
  assert.equal(s.history.loadRun()?.readings.length, 1);
});

test("Start with nothing kept does not ask", () => {
  const s = setup();
  const c = s.make();
  c.connectPractice();
  c.start(SETTINGS);
  assert.deepEqual(s.asked, []);
});

test("Collect another run asks every time, and a no keeps the run, on screen and in the browser", () => {
  const { c, s } = finished(setup(new MemoryStorage(), [false, false, true]));
  const kept = s.storage.getItem(RUN_KEY);
  assert.equal(c.another(), false);
  assert.equal(c.another(), false);
  assert.deepEqual(s.asked, [REPLACE_QUESTION, REPLACE_QUESTION]);
  assert.equal(c.phase, "finished");
  assert.equal(c.run?.readings.length, 25);
  assert.equal(s.storage.getItem(RUN_KEY), kept);
  assert.equal(c.another(), true, "a yes");
  assert.equal(s.asked.length, 3, "asked again, though it had been asked before");
  assert.equal(c.phase, "ready");
  assert.equal(c.run, null);
  assert.equal(s.storage.getItem(RUN_KEY), null);
});

test("Clear asks every time, and a no keeps the run, on screen and in the browser", () => {
  const { c, s } = finished(setup(new MemoryStorage(), [false, true]));
  const kept = s.storage.getItem(RUN_KEY);
  assert.equal(c.clear(), false);
  assert.deepEqual(s.asked, [CLEAR_QUESTION]);
  assert.equal(c.phase, "finished");
  assert.equal(s.storage.getItem(RUN_KEY), kept);
  assert.equal(c.clear(), true);
  assert.equal(s.asked.length, 2);
  assert.equal(c.run, null);
  assert.equal(s.storage.getItem(RUN_KEY), null);
  assert.equal(c.phase, "ready", "still connected to the practice source");
});

test("Clear on a restored run asks, and afterwards a reopened page finds nothing", () => {
  const { s } = finished();
  s.answers.push(true);
  const c = s.make();
  assert.equal(c.restored, true);
  assert.equal(c.clear(), true);
  assert.deepEqual(s.asked, [CLEAR_QUESTION]);
  assert.equal(c.phase, "before", "a restored page has no source to go back to");
  assert.equal(s.make().run, null);
});

test("every question says an unsaved run will be lost", () => {
  for (const q of [REPLACE_QUESTION, CLEAR_QUESTION]) {
    assert.match(q, /not saved as a spreadsheet will be lost/);
  }
});

test("the °F toggle changes nothing stored: readings stay as the source gave them", () => {
  const s = setup();
  const c = s.make();
  assert.equal(c.unit, "C");
  c.setUnit("F");
  assert.equal(s.history.loadUnit(), "F");
  c.connectPractice();
  c.start(SETTINGS);
  s.timers.drain();
  const stored = s.history.loadRun();
  assert.ok(stored !== null);
  for (const r of stored.readings) {
    assert.equal(r.v, practiceCelsius(r.t), `at ${r.t} seconds`);
  }
  c.setUnit("C");
  c.setUnit("F");
  assert.deepEqual(s.history.loadRun()?.readings, stored.readings, "toggling again changes nothing");
  assert.equal(s.make().unit, "F", "the choice comes back with the page");
  assert.equal(s.make().run?.readings[3]?.v, practiceCelsius(15), "and so does the run, in Celsius");
});

test("storage that throws: the run still runs, and the page can say it is not kept", () => {
  const s = setup(new ThrowingStorage());
  const c = s.make();
  assert.equal(c.storageOk, false, "known before any run");
  assert.equal(c.phase, "before");
  c.connectPractice();
  assert.equal(c.start(SETTINGS), true);
  s.timers.drain();
  assert.equal(c.phase, "finished");
  assert.equal(c.run?.readings.length, 25);
  assert.equal(c.storageOk, false);
  c.setUnit("F");
  assert.equal(c.unit, "F");
  s.answers.push(true);
  assert.equal(c.another(), true);
  assert.equal(c.phase, "ready");
});

test("a working storage says it is keeping runs", () => {
  const c = setup().make();
  assert.equal(c.storageOk, true);
});

test("listeners hear every change", () => {
  const s = setup();
  const c = s.make();
  let heard = 0;
  c.subscribe(() => (heard += 1));
  c.connectPractice();
  c.start(SETTINGS);
  s.timers.drain();
  assert.ok(heard >= 27, `${heard}`);
});
