// Held here: what the screen says, as plain data. Above all, that practice readings are marked
// made up wherever they are shown (live, finished, restored, mid-run restored), in marks that do not
// depend on one another, so that a screenshot cropped past one still carries another; that a run
// that is not practice carries none of them; the power sentence and the facts' text beneath it; the
// table newest first; °F applied once to what is shown; the graph's picture and its text alternative.
//
// Not held: that the page's glue copies the view into the page (page.ts, shown only by a browser).
import { test } from "node:test";
import assert from "node:assert/strict";
import { text } from "../src/protocol/facts.ts";
import { describeReadings, graphSvg, niceTicks } from "../src/collect/graph.ts";
import { practiceCelsius } from "../src/collect/practice.ts";
import type { KeptRun, Reading } from "../src/collect/types.ts";
import { viewOf, type Situation } from "../src/collect/view.ts";
import {
  CLEAR_NOTE, CONNECT_NOTE, NO_STORAGE_LINE, POWER_LEAD, POWER_SENTENCE, SAVE_FIRST, duration, localStamp,
} from "../src/collect/words.ts";

const POWER = text("power.supply");

function readings(n: number): Reading[] {
  return Array.from({ length: n }, (_, k) => ({ t: k * 5, v: practiceCelsius(k * 5) }));
}

function runOf(over: Partial<KeptRun> = {}, n = 25): KeptRun {
  return {
    version: 1,
    practice: true,
    storedUnit: "C",
    startedAt: new Date(2026, 10, 19, 20, 14).toISOString(),
    settings: { everySeconds: 5, forSeconds: 120 },
    end: "done",
    readings: readings(n),
    ...over,
  };
}

function situation(over: Partial<Situation> = {}): Situation {
  return {
    phase: "finished",
    run: runOf(),
    restored: false,
    unit: "C",
    storageOk: true,
    connected: true,
    connectedPractice: true,
    ...over,
  };
}

/** Every situation in which practice readings are, or are about to be, shown. */
const PRACTICE_SITUATIONS: [string, Situation][] = [
  ["ready", situation({ phase: "ready", run: null })],
  ["collecting, no reading yet", situation({ phase: "collecting", run: runOf({ end: "open" }, 0) })],
  ["collecting", situation({ phase: "collecting", run: runOf({ end: "open" }, 8) })],
  ["finished", situation()],
  ["finished early", situation({ run: runOf({ end: "stopped" }, 8) })],
  ["restored, finished", situation({ restored: true, connected: false, connectedPractice: false })],
  ["restored, stopped when the page closed", situation({ restored: true, connected: false, connectedPractice: false, run: runOf({ end: "open" }, 8) })],
  ["in degrees F", situation({ unit: "F" })],
];

test("practice readings are marked made up in five marks that stand apart", () => {
  for (const [what, s] of PRACTICE_SITUATIONS) {
    const v = viewOf(s, POWER);
    assert.match(v.practiceBanner ?? "", /made up/, `banner: ${what}`);
    assert.equal(v.pill, "made up", `pill: ${what}`);
    assert.match(v.graphCaption, /Made-up readings: a cup of hot water cooling\. Not a measurement\./, `graph caption: ${what}`);
    assert.match(v.tableCaption, /Made-up readings: a cup of hot water cooling\. Not a measurement\./, `table caption: ${what}`);
    assert.match(v.graph, />made up</, `inside the graph: ${what}`);
    assert.match(v.graph, /aria-label="[^"]*Made-up readings/, `graph's text alternative: ${what}`);
  }
});

test("the screen says hot water, not warm", () => {
  const v = viewOf(situation(), POWER);
  assert.ok(/hot water/.test(v.graphCaption) && !/warm/i.test(v.graphCaption + v.tableCaption + v.message));
});

test("a run that is not practice carries none of the made-up marks", () => {
  const real = situation({ run: runOf({ practice: false }), connectedPractice: false });
  const v = viewOf(real, POWER);
  const everything = [v.practiceBanner, v.pill, v.graph, v.graphCaption, v.tableCaption, v.message, v.sub, ...v.chips.map((c) => c.text)].join("\n");
  assert.ok(!/made[- ]up|practice|not a measurement/i.test(everything), everything);
  assert.equal(v.practiceBanner, null);
  assert.equal(v.pill, null);
});

test("before connecting: the power sentence, then 'It takes:' and the facts' text, and a connect that waits", () => {
  const v = viewOf(situation({ phase: "before", run: null, connected: false, connectedPractice: false }), POWER);
  assert.equal(v.message, POWER_SENTENCE);
  assert.equal(
    POWER_SENTENCE,
    "Give the LabPro power: plug in its power supply, or put batteries in it. Then plug it into this computer with its USB cable.",
  );
  assert.equal(v.powerLead, POWER_LEAD);
  assert.equal(POWER_LEAD, "It takes:");
  assert.equal(v.powerDetail, text("power.supply"), "the fact's text, as the facts give it");
  assert.equal(v.connectNote, CONNECT_NOTE);
  assert.match(CONNECT_NOTE, /comes after its first test on the bench/);
  assert.equal(v.show.connect, true);
  assert.equal(v.show.practice, true);
  assert.equal(v.practiceBanner, null, "no readings, no banner");
  assert.deepEqual(v.chips, [{ text: "LabPro: not connected", ok: false }]);
  assert.equal(v.big, "– –");
  assert.equal(v.emptyRow, true);
});

test("the power sentence names no LabPro value", () => {
  // The sentence is plain words. Every figure and unit of the fact is absent from it.
  for (const piece of POWER.split(/,| or /).map((p) => p.trim()).filter((p) => p !== "")) {
    assert.ok(!POWER_SENTENCE.includes(piece) && !CONNECT_NOTE.includes(piece), piece);
  }
  assert.ok(!/\d/.test(POWER_SENTENCE + POWER_LEAD + CONNECT_NOTE), "no figure at all");
});

test("only the state's own buttons show", () => {
  const shown = (s: Situation) => Object.entries(viewOf(s, POWER).show).filter(([, on]) => on).map(([k]) => k);
  assert.deepEqual(shown(situation({ phase: "before", run: null, connected: false })), ["connect", "practice"]);
  assert.deepEqual(shown(situation({ phase: "ready", run: null })), ["settings", "start"]);
  assert.deepEqual(shown(situation({ phase: "collecting", run: runOf({ end: "open" }, 3) })), ["progress", "stop"]);
  assert.deepEqual(shown(situation()), ["save", "another", "clear"]);
});

test("the table is newest at the top, and the newest row is marked", () => {
  const v = viewOf(situation(), POWER);
  assert.equal(v.rows.length, 25);
  assert.deepEqual(v.rows[0], { time: "120", value: "45.5", newest: true });
  assert.deepEqual(v.rows[24], { time: "0", value: "75.0", newest: false });
  assert.equal(v.rows.filter((r) => r.newest).length, 1);
  assert.match(v.tableCaption, /Newest at the top\.$/);
  assert.equal(v.tempHeader, "Temperature (°C)");
});

test("the toggle shows °F once, from the stored Celsius, and touches nothing stored", () => {
  const run = runOf();
  const frozen = JSON.stringify(run);
  const c = viewOf(situation({ run }), POWER);
  const f = viewOf(situation({ run, unit: "F" }), POWER);
  assert.equal(f.rows[0]?.value, "113.9", "45.5 C is 113.9 F, not 236.x");
  assert.equal(f.rows[24]?.value, "167.0");
  assert.equal(f.big, "113.9");
  assert.equal(f.bigUnit, " °F");
  assert.equal(c.bigUnit, " °C");
  assert.equal(f.tempHeader, "Temperature (°F)");
  assert.match(f.graphCaption, /It started at 167\.0 °F and ended at 113\.9 °F\./);
  assert.match(f.graph, /Temperature \(°F\)/);
  assert.equal(f.unitF, true);
  assert.equal(JSON.stringify(run), frozen, "the stored run is untouched");
});

test("the message for each state", () => {
  const msg = (s: Situation) => viewOf(s, POWER).message;
  assert.equal(msg(situation({ phase: "ready", run: null })), "Ready. Press Start, and made-up temperature readings will appear.");
  assert.equal(msg(situation({ phase: "collecting", run: runOf({ end: "open" }, 3) })), "Collecting readings. Press Stop to end the run early.");
  assert.equal(msg(situation()), `Run finished: 25 readings in 2 minutes. ${SAVE_FIRST}`);
  assert.equal(msg(situation({ run: runOf({ end: "stopped" }, 8) })), `Run stopped early: 8 readings in 35 seconds. ${SAVE_FIRST}`);
  const when = localStamp(runOf().startedAt);
  assert.equal(when, "2026-11-19 20:14");
  assert.equal(
    msg(situation({ restored: true })),
    `The last run, kept in this browser (started ${when}): 25 readings in 2 minutes. ${SAVE_FIRST}`,
  );
  assert.equal(
    msg(situation({ restored: true, run: runOf({ end: "open" }, 8) })),
    `The last run was stopped when the page closed (started ${when}): 8 readings in 35 seconds. ${SAVE_FIRST}`,
  );
  assert.match(SAVE_FIRST, /Save them before you collect another run/);
});

test("a restored run says to save before collecting another, and what stays on a shared computer", () => {
  const v = viewOf(situation({ restored: true }), POWER);
  assert.match(v.message, /Save them before you collect another run\./);
  assert.equal(v.clearNote, CLEAR_NOTE);
  assert.match(CLEAR_NOTE, /shared computer/);
  assert.equal(viewOf(situation({ phase: "ready", run: null }), POWER).clearNote, null);
});

test("the line about storage shows only when storage does not keep runs", () => {
  assert.equal(viewOf(situation(), POWER).storageLine, null);
  assert.equal(viewOf(situation({ storageOk: false }), POWER).storageLine, NO_STORAGE_LINE);
  assert.match(NO_STORAGE_LINE, /not keeping runs/);
});

test("the reading, its sub line, and the progress", () => {
  const v = viewOf(situation({ phase: "collecting", run: runOf({ end: "open" }, 15) }), POWER);
  assert.equal(v.big, "54.9");
  assert.equal(v.sub, "Latest reading, 1 minute 10 seconds in.");
  assert.deepEqual(v.progress, { value: 70, max: 120, label: "70 of 120 seconds" });
  assert.equal(viewOf(situation(), POWER).sub, "Last reading, at 2 minutes.");
  assert.equal(viewOf(situation({ phase: "ready", run: null }), POWER).sub, "No reading yet.");
});

test("durations and stamps", () => {
  assert.equal(duration(1), "1 second");
  assert.equal(duration(5), "5 seconds");
  assert.equal(duration(60), "1 minute");
  assert.equal(duration(70), "1 minute 10 seconds");
  assert.equal(duration(1800), "30 minutes");
  assert.equal(localStamp("nonsense"), "an unknown time");
});

test("the graph: one polyline point per reading, a dot on the latest, and no address in it", () => {
  const svg = graphSvg(readings(15), { unit: "C", forSeconds: 120, practice: true });
  const points = svg.match(/<polyline class="line" points="([^"]*)"/)?.[1]?.split(" ") ?? [];
  assert.equal(points.length, 15);
  assert.equal((svg.match(/class="dot"/g) ?? []).length, 1);
  assert.ok(!/https?:|\/\/|url\(/.test(svg));
  assert.match(svg, /^<svg viewBox="0 0 600 244" role="img" aria-label="/);
  assert.match(svg, /<title>Graph of temperature against time\./);
  // The line falls: each point's y grows (drawn lower) as the water cools.
  const ys = points.map((p) => Number(p.split(",")[1]));
  for (let i = 1; i < ys.length; i += 1) {
    assert.ok((ys[i] ?? 0) > (ys[i - 1] ?? 0));
  }
});

test("the graph with one reading is a dot, and with none is the empty frame and its hint", () => {
  const one = graphSvg(readings(1), { unit: "C", forSeconds: 120, practice: true });
  assert.ok(!one.includes("<polyline") && one.includes('class="dot"'));
  const none = graphSvg([], { unit: "C", forSeconds: 120, practice: true });
  assert.ok(!none.includes("<polyline") && !none.includes('class="dot"'));
  assert.match(none, /The graph fills in when you press Start\./);
  assert.match(none, /Empty: no readings yet\./);
  const labels = (svg: string) => [...svg.matchAll(/text-anchor="end">([\d.]+)</g)].map((m) => m[1]);
  assert.deepEqual(labels(none), ["20", "40", "60", "80"], "the empty frame is 20 to 80, as the mockup's is");
  assert.match(none, />made up</, "even an empty graph of practice carries the mark");
});

test("the text alternative gives the first, latest, lowest and highest readings", () => {
  assert.equal(
    describeReadings(readings(15), "C", true),
    "Graph of temperature against time. Made-up readings. First reading 75.0 °C at 0 seconds. Latest 54.9 °C at 70 seconds. Lowest 54.9 °C at 70 seconds. Highest 75.0 °C at 0 seconds.",
  );
  const rising: Reading[] = [{ t: 0, v: 20 }, { t: 5, v: 30 }, { t: 10, v: 25 }];
  assert.equal(
    describeReadings(rising, "F", false),
    "Graph of temperature against time. First reading 68.0 °F at 0 seconds. Latest 77.0 °F at 10 seconds. Lowest 68.0 °F at 0 seconds. Highest 86.0 °F at 5 seconds.",
  );
});

test("round ticks cover the readings", () => {
  assert.deepEqual(niceTicks(20, 80), [20, 40, 60, 80]);
  assert.deepEqual(niceTicks(45, 76), [40, 50, 60, 70, 80]);
  const flat = niceTicks(22.1, 22.3);
  assert.ok((flat[0] ?? 99) <= 22.1 && (flat[flat.length - 1] ?? 0) >= 22.3 && flat.length >= 2);
});

test("the graph in °F is drawn from the stored Celsius once: its axis is the converted range", () => {
  const labels = (svg: string) => [...svg.matchAll(/text-anchor="end">([\d.]+)</g)].map((m) => Number(m[1]));
  const c = labels(graphSvg(readings(25), { unit: "C", forSeconds: 120, practice: true }));
  const f = labels(graphSvg(readings(25), { unit: "F", forSeconds: 120, practice: true }));
  // 45.5 to 75.0 C is 113.9 to 167.0 F. A second conversion would put the axis at 200 to 330.
  assert.ok(Math.min(...c) <= 45.5 && Math.max(...c) >= 75, `${c}`);
  assert.ok(Math.min(...f) <= 113.9 && Math.max(...f) >= 167 && Math.max(...f) < 190, `${f}`);
  assert.match(graphSvg(readings(25), { unit: "F", forSeconds: 120, practice: true }), /Temperature \(°F\)/);
});
