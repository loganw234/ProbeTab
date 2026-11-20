// The spreadsheet file: a CSV, oldest reading first (the table on screen is newest first).
//
// A real run's file starts with the column names. A practice run's file starts with one line
// saying the readings are made up, then the column names. The unit comes from the toggle at the
// moment of saving, applied once to each stored reading.
//
// The text starts with a byte-order mark, so that a spreadsheet reads the degree sign as UTF-8.

import { PRACTICE_FILE_NOTE } from "./words.ts";
import { formatTemp, unitLabel } from "./units.ts";
import type { Reading, Unit } from "./types.ts";

export const BOM = "\uFEFF";
const EOL = "\r\n";

export function csvCell(text: string): string {
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

export interface Savable {
  readonly practice: boolean;
  readonly startedAt: string;
  readonly readings: readonly Reading[];
}

export function toCsv(run: Savable, unit: Unit): string {
  const lines: string[] = [];
  if (run.practice) {
    lines.push(csvCell(PRACTICE_FILE_NOTE));
  }
  lines.push(`Time (s),Temperature (${unitLabel(unit)})`);
  for (const reading of run.readings) {
    lines.push(`${reading.t},${formatTemp(reading.v, unit)}`);
  }
  return BOM + lines.join(EOL) + EOL;
}

/** probetab-practice-run-2026-11-19-2014.csv, from the run's start in the computer's own time. */
export function fileName(run: Savable): string {
  const d = new Date(run.startedAt);
  const two = (n: number): string => String(n).padStart(2, "0");
  const when = Number.isNaN(d.getTime())
    ? "unknown-time"
    : `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}-${two(d.getHours())}${two(d.getMinutes())}`;
  return `probetab-${run.practice ? "practice-" : ""}run-${when}.csv`;
}
