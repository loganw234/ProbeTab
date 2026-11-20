// The last run, kept in the browser's localStorage so that a closed tab, or tomorrow, brings it
// back. Only the last run is kept. Every read and write is inside a try, because storage can be
// missing (a private window), full, or blocked, and the page must work without it.
//
// Stored data of an unknown version or shape is ignored, never trusted and never a failure.
// Readings are stored as the source gave them: the °F choice is kept apart, under its own key.
//
// Two tabs share the one key. Each saves after every reading, so a run in one can overwrite the
// run the other kept. That is a stated limit, not handled here.

import type { End, KeptRun, Reading, Unit } from "./types.ts";

export const RUN_KEY = "probetab.collect.lastRun.v1";
export const UNIT_KEY = "probetab.collect.unit.v1";
const PROBE_KEY = "probetab.collect.probe";

/** The part of localStorage this page uses. */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const ENDS: readonly string[] = ["open", "done", "stopped"];

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function positive(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x) && x > 0;
}

/** The kept run in this text, or null when the text is not one, in any way. */
export function parseRun(text: string): KeptRun | null {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return null;
  }
  if (!isRecord(data) || data["version"] !== 1 || data["storedUnit"] !== "C") {
    return null;
  }
  const { practice, startedAt, settings, end, readings } = data;
  if (typeof practice !== "boolean" || typeof startedAt !== "string" || !isRecord(settings)) {
    return null;
  }
  const everySeconds = settings["everySeconds"];
  const forSeconds = settings["forSeconds"];
  if (!positive(everySeconds) || !positive(forSeconds)) {
    return null;
  }
  if (typeof end !== "string" || !ENDS.includes(end) || !Array.isArray(readings)) {
    return null;
  }
  const kept: Reading[] = [];
  for (const item of readings as unknown[]) {
    if (!isRecord(item)) {
      return null;
    }
    const t = item["t"];
    const v = item["v"];
    if (typeof t !== "number" || !Number.isFinite(t) || t < 0 || typeof v !== "number" || !Number.isFinite(v)) {
      return null;
    }
    kept.push({ t, v });
  }
  return {
    version: 1,
    practice,
    storedUnit: "C",
    startedAt,
    settings: { everySeconds, forSeconds },
    end: end as End,
    readings: kept,
  };
}

export class History {
  private readonly open: () => StorageLike | null;

  /** open gives the storage, or null, or throws: all three mean "no history". */
  constructor(open: () => StorageLike | null) {
    this.open = open;
  }

  /** True when a value can be written and removed. It writes one probe key and removes it. */
  available(): boolean {
    try {
      const storage = this.open();
      if (storage === null) {
        return false;
      }
      storage.setItem(PROBE_KEY, "1");
      storage.removeItem(PROBE_KEY);
      return true;
    } catch {
      return false;
    }
  }

  /** The kept run, or null when there is none, or what is there is not a run this page wrote. */
  loadRun(): KeptRun | null {
    try {
      const storage = this.open();
      const text = storage === null ? null : storage.getItem(RUN_KEY);
      return text === null ? null : parseRun(text);
    } catch {
      return null;
    }
  }

  /** True when the run was written. False means it was not kept. */
  saveRun(run: KeptRun): boolean {
    try {
      const storage = this.open();
      if (storage === null) {
        return false;
      }
      storage.setItem(RUN_KEY, JSON.stringify(run));
      return true;
    } catch {
      return false;
    }
  }

  clearRun(): boolean {
    try {
      const storage = this.open();
      if (storage === null) {
        return false;
      }
      storage.removeItem(RUN_KEY);
      return true;
    } catch {
      return false;
    }
  }

  /** The °F choice. Celsius is the default, and what anything unreadable means. */
  loadUnit(): Unit {
    try {
      const storage = this.open();
      return storage !== null && storage.getItem(UNIT_KEY) === "F" ? "F" : "C";
    } catch {
      return "C";
    }
  }

  saveUnit(unit: Unit): boolean {
    try {
      const storage = this.open();
      if (storage === null) {
        return false;
      }
      storage.setItem(UNIT_KEY, unit);
      return true;
    } catch {
      return false;
    }
  }
}
