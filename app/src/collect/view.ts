// What the page shows, worked out as plain data from the run's state. page.ts only copies this
// into the page, so that Node can hold the words, and above all the marks that say practice
// readings are made up, wherever they are shown, live or restored.

import { graphSvg } from "./graph.ts";
import { formatTemp, unitLabel } from "./units.ts";
import {
  CLEAR_NOTE, CONNECT_NOTE, DEFAULT_SETTINGS, MADE_UP_CAPTION, MADE_UP_PILL, NO_STORAGE_LINE, POWER_LEAD, POWER_SENTENCE,
  PRACTICE_BANNER, SAVE_FIRST, duration, localStamp, plural,
} from "./words.ts";
import type { Phase } from "./collector.ts";
import type { KeptRun, Unit } from "./types.ts";

/** What the view needs of the collector. */
export interface Situation {
  readonly phase: Phase;
  readonly run: KeptRun | null;
  readonly restored: boolean;
  readonly unit: Unit;
  readonly storageOk: boolean;
  /** True once a source is connected, and whether it makes up its readings. */
  readonly connected: boolean;
  readonly connectedPractice: boolean;
}

export interface Chip {
  readonly text: string;
  readonly ok: boolean;
}

export interface Row {
  readonly time: string;
  readonly value: string;
  readonly newest: boolean;
}

export interface View {
  readonly practiceBanner: string | null;
  readonly chips: readonly Chip[];
  readonly message: string;
  /** "It takes:" and the facts' power text, before connecting only. */
  readonly powerLead: string | null;
  readonly powerDetail: string | null;
  readonly connectNote: string | null;
  readonly show: {
    readonly connect: boolean;
    readonly practice: boolean;
    readonly settings: boolean;
    readonly start: boolean;
    readonly progress: boolean;
    readonly stop: boolean;
    readonly save: boolean;
    readonly another: boolean;
    readonly clear: boolean;
  };
  readonly progress: { readonly value: number; readonly max: number; readonly label: string };
  readonly big: string;
  readonly bigUnit: string;
  readonly sub: string;
  readonly pill: string | null;
  readonly graph: string;
  readonly graphCaption: string;
  readonly tempHeader: string;
  readonly tableCaption: string;
  readonly rows: readonly Row[];
  readonly emptyRow: boolean;
  readonly unitF: boolean;
  readonly storageLine: string | null;
  readonly clearNote: string | null;
}

function sentence(run: KeptRun, restored: boolean): string {
  const last = run.readings[run.readings.length - 1];
  const count = plural(run.readings.length, "reading", "readings");
  const length = last === undefined ? "no time" : duration(last.t);
  const body = `${count} in ${length}.`;
  if (!restored) {
    return `${run.end === "stopped" ? "Run stopped early" : "Run finished"}: ${body} ${SAVE_FIRST}`;
  }
  const when = localStamp(run.startedAt);
  const lead =
    run.end === "open"
      ? `The last run was stopped when the page closed (started ${when})`
      : `The last run, kept in this browser (started ${when})`;
  return `${lead}: ${body} ${SAVE_FIRST}`;
}

/** `powerText` is the fact power.supply's value, read from the generated facts by the caller. */
export function viewOf(s: Situation, powerText: string): View {
  const run = s.run;
  const shownRun = s.phase === "collecting" || s.phase === "finished" ? run : null;
  const practice = shownRun !== null ? shownRun.practice : s.connected && s.connectedPractice;
  const readings = shownRun === null ? [] : shownRun.readings;
  const last = readings[readings.length - 1];
  const first = readings[0];
  const before = s.phase === "before";
  const label = unitLabel(s.unit);

  const chips: Chip[] = [];
  if (before) {
    chips.push({ text: "LabPro: not connected", ok: false });
  } else if (practice) {
    chips.push({ text: "No LabPro: practice with made-up readings", ok: false });
  }

  let message = "";
  if (before) {
    message = POWER_SENTENCE;
  } else if (s.phase === "ready") {
    message = "Ready. Press Start, and made-up temperature readings will appear.";
  } else if (s.phase === "collecting") {
    message = "Collecting readings. Press Stop to end the run early.";
  } else if (run !== null) {
    message = sentence(run, s.restored);
  }

  const settings = shownRun === null ? DEFAULT_SETTINGS : shownRun.settings;
  const rows: Row[] = readings
    .map((r, i) => ({ time: String(r.t), value: formatTemp(r.v, s.unit), newest: i === readings.length - 1 }))
    .reverse();

  let detail = "No readings yet.";
  if (first !== undefined && last !== undefined) {
    const start = formatTemp(first.v, s.unit);
    const now = formatTemp(last.v, s.unit);
    detail =
      s.phase === "collecting"
        ? `It started at ${start} ${label} and is now ${now} ${label}.`
        : `It started at ${start} ${label} and ended at ${now} ${label}.`;
  }

  let sub = "No reading yet.";
  if (last !== undefined) {
    sub = s.phase === "collecting" ? `Latest reading, ${duration(last.t)} in.` : `Last reading, at ${duration(last.t)}.`;
  }

  return {
    practiceBanner: practice ? PRACTICE_BANNER : null,
    chips,
    message,
    powerLead: before ? POWER_LEAD : null,
    powerDetail: before ? powerText : null,
    connectNote: before ? CONNECT_NOTE : null,
    show: {
      connect: before,
      practice: before,
      settings: s.phase === "ready",
      start: s.phase === "ready",
      progress: s.phase === "collecting",
      stop: s.phase === "collecting",
      save: s.phase === "finished",
      another: s.phase === "finished",
      clear: s.phase === "finished",
    },
    progress: {
      value: last === undefined ? 0 : last.t,
      max: settings.forSeconds,
      label: `${last === undefined ? 0 : last.t} of ${settings.forSeconds} seconds`,
    },
    big: last === undefined ? "– –" : formatTemp(last.v, s.unit),
    bigUnit: last === undefined ? "" : ` ${label}`,
    sub,
    pill: practice ? MADE_UP_PILL : null,
    graph: graphSvg(readings, { unit: s.unit, forSeconds: settings.forSeconds, practice }),
    graphCaption: `${practice ? MADE_UP_CAPTION + " " : ""}${detail}`,
    tempHeader: `Temperature (${label})`,
    tableCaption: `${practice ? MADE_UP_CAPTION + " " : ""}Newest at the top.`,
    rows,
    emptyRow: rows.length === 0,
    unitF: s.unit === "F",
    storageLine: s.storageOk ? null : NO_STORAGE_LINE,
    clearNote: s.phase === "finished" ? CLEAR_NOTE : null,
  };
}
