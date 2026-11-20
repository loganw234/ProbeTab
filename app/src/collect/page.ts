// The classroom screen's glue to the browser: it copies the view into the page and passes the
// buttons on to the collector. The logic is in collector.ts and view.ts, which the tests run on
// Node. This file is not tested on Node. On 2026-11-19 it ran once in a headless Edge, driven over
// the DevTools protocol by a throwaway script that is not kept: practice, Start, Stop, Save, the
// °F box, a reload that restored the run, and Clear with a no and a yes (MEASURED). Nothing else
// has run it: no phone, no screen reader, no Chromebook, no second tab.

import { text } from "../protocol/facts.ts";
import { Collector } from "./collector.ts";
import { fileName, toCsv } from "./csv.ts";
import { History } from "./history.ts";
import { PracticeSource } from "./practice.ts";
import { viewOf } from "./view.ts";
import { DEFAULT_SETTINGS, EVERY_CHOICES, FOR_CHOICES, duration } from "./words.ts";
import type { View } from "./view.ts";

function el<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (found === null) {
    throw new Error(`the page has no element #${id}`);
  }
  return found as T;
}

const parts = {
  banner: el("banner"),
  chips: el("chips"),
  message: el("message"),
  powerBlock: el("power-block"),
  powerLead: el("power-lead"),
  powerDetail: el("power-detail"),
  connectNote: el("connect-note"),
  connect: el("btn-connect"),
  practice: el("btn-practice"),
  settings: el("settings"),
  start: el("btn-start"),
  progress: el("progress-wrap"),
  stop: el("btn-stop"),
  save: el("btn-save"),
  another: el("btn-another"),
  clear: el("btn-clear"),
  clearNote: el("clear-note"),
  big: el("big"),
  bigUnit: el("big-unit"),
  sub: el("sub"),
  pill: el("pill"),
  graph: el("graph"),
  graphCaption: el("graph-caption"),
  tableCaption: el("table-caption"),
  tempHeader: el("th-temp"),
  rows: el("rows"),
  storageLine: el("storage-line"),
};
const every = el<HTMLSelectElement>("sel-every");
const length = el<HTMLSelectElement>("sel-for");
const meter = el<HTMLProgressElement>("progress");
const meterLabel = el<HTMLLabelElement>("progress-label");
const unitF = el<HTMLInputElement>("unit-f");

function fill(select: HTMLSelectElement, choices: readonly number[], chosen: number): void {
  for (const seconds of choices) {
    const option = document.createElement("option");
    option.value = String(seconds);
    option.textContent = duration(seconds);
    option.selected = seconds === chosen;
    select.append(option);
  }
}
fill(every, EVERY_CHOICES, DEFAULT_SETTINGS.everySeconds);
fill(length, FOR_CHOICES, DEFAULT_SETTINGS.forSeconds);

const collector = new Collector({
  history: new History(() => window.localStorage),
  confirm: (question) => window.confirm(question),
  makePractice: () => new PracticeSource(),
  now: () => new Date(),
});

function render(view: View): void {
  parts.banner.hidden = view.practiceBanner === null;
  parts.banner.textContent = view.practiceBanner ?? "";
  parts.chips.replaceChildren(
    ...view.chips.map((chip) => {
      const li = document.createElement("li");
      li.textContent = (chip.ok ? "✓ " : "") + chip.text;
      li.className = chip.ok ? "ok" : "";
      return li;
    }),
  );
  parts.message.textContent = view.message;
  parts.powerBlock.hidden = view.powerLead === null;
  parts.powerLead.textContent = view.powerLead ?? "";
  parts.powerDetail.textContent = view.powerDetail ?? "";
  parts.connectNote.hidden = view.connectNote === null;
  parts.connectNote.textContent = view.connectNote ?? "";
  parts.connect.hidden = !view.show.connect;
  parts.practice.hidden = !view.show.practice;
  parts.settings.hidden = !view.show.settings;
  parts.start.hidden = !view.show.start;
  parts.progress.hidden = !view.show.progress;
  parts.stop.hidden = !view.show.stop;
  parts.save.hidden = !view.show.save;
  parts.another.hidden = !view.show.another;
  parts.clear.hidden = !view.show.clear;
  parts.clearNote.hidden = view.clearNote === null;
  parts.clearNote.textContent = view.clearNote ?? "";
  meter.value = view.progress.value;
  meter.max = Math.max(view.progress.max, 1);
  meterLabel.textContent = view.progress.label;
  parts.big.textContent = view.big;
  if (view.bigUnit === "") {
    parts.big.setAttribute("role", "img");
    parts.big.setAttribute("aria-label", "no reading yet");
  } else {
    parts.big.removeAttribute("role");
    parts.big.removeAttribute("aria-label");
  }
  parts.bigUnit.textContent = view.bigUnit;
  parts.sub.textContent = view.sub;
  parts.pill.hidden = view.pill === null;
  parts.pill.textContent = view.pill ?? "";
  parts.graph.innerHTML = view.graph;
  parts.graphCaption.textContent = view.graphCaption;
  parts.tableCaption.textContent = view.tableCaption;
  parts.tempHeader.textContent = view.tempHeader;
  parts.rows.replaceChildren(
    ...(view.emptyRow
      ? [emptyRow()]
      : view.rows.map((row) => {
          const tr = document.createElement("tr");
          if (row.newest) {
            tr.className = "newest";
          }
          for (const value of [row.time, row.value]) {
            const td = document.createElement("td");
            td.textContent = value;
            tr.append(td);
          }
          return tr;
        })),
  );
  unitF.checked = view.unitF;
  parts.storageLine.hidden = view.storageLine === null;
  parts.storageLine.textContent = view.storageLine ?? "";
}

function emptyRow(): HTMLElement {
  const tr = document.createElement("tr");
  tr.className = "empty";
  const td = document.createElement("td");
  td.colSpan = 2;
  td.textContent = "No readings yet.";
  tr.append(td);
  return tr;
}

function refresh(): void {
  render(
    viewOf(
      {
        phase: collector.phase,
        run: collector.run,
        restored: collector.restored,
        unit: collector.unit,
        storageOk: collector.storageOk,
        connected: collector.source !== null,
        connectedPractice: collector.source !== null && collector.source.practice,
      },
      text("power.supply"),
    ),
  );
}

/** After a button hides itself, put the keyboard's place on the next step. */
function focusNext(): void {
  const next = { before: parts.practice, ready: parts.start, collecting: parts.stop, finished: parts.save }[collector.phase];
  next.focus();
}

let shownPhase = collector.phase;
collector.subscribe(() => {
  refresh();
  if (collector.phase !== shownPhase) {
    shownPhase = collector.phase;
    focusNext();
  }
});

parts.practice.addEventListener("click", () => {
  collector.connectPractice();
});
parts.start.addEventListener("click", () => {
  collector.start({ everySeconds: Number(every.value), forSeconds: Number(length.value) });
});
parts.stop.addEventListener("click", () => {
  collector.stop();
});
parts.another.addEventListener("click", () => {
  collector.another();
});
parts.clear.addEventListener("click", () => {
  collector.clear();
});
unitF.addEventListener("change", () => {
  collector.setUnit(unitF.checked ? "F" : "C");
});
parts.save.addEventListener("click", () => {
  const run = collector.run;
  if (run === null) {
    return;
  }
  const blob = new Blob([toCsv(run, collector.unit)], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = fileName(run);
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10000);
});

refresh();
