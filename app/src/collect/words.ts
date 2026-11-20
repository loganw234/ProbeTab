// The screen's words, kept in one place so that tests can hold them. None is a LabPro value:
// the power details are read from the facts and passed in, never typed here. The times in the
// settings are the person's choices, not facts.

import type { Settings } from "./types.ts";

/** Seconds, with the words a person reads. */
export const EVERY_CHOICES: readonly number[] = [1, 5, 10, 30, 60];
export const FOR_CHOICES: readonly number[] = [60, 120, 300, 600, 1200, 1800];
export const DEFAULT_SETTINGS: Settings = { everySeconds: 5, forSeconds: 120 };

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** 5 -> "5 seconds", 60 -> "1 minute", 70 -> "1 minute 10 seconds". */
export function duration(seconds: number): string {
  const whole = Math.round(seconds);
  if (whole < 60) {
    return plural(whole, "second", "seconds");
  }
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  const m = plural(minutes, "minute", "minutes");
  return rest === 0 ? m : `${m} ${plural(rest, "second", "seconds")}`;
}

/** A local date and time for the person: 2026-11-19 20:14. */
export function localStamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return "an unknown time";
  }
  const two = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
}

export const POWER_SENTENCE =
  "Give the LabPro power: plug in its power supply, or put batteries in it. Then plug it into this computer with its USB cable.";
export const POWER_LEAD = "It takes:";

export const CONNECT_NOTE =
  "Connecting a LabPro comes after its first test on the bench. Until then, you can practise with made-up readings.";

export const PRACTICE_BANNER = "PRACTICE. Every reading on this page is made up. None was measured.";
export const MADE_UP_PILL = "made up";
export const MADE_UP_CAPTION = "Made-up readings: a cup of hot water cooling. Not a measurement.";

/** The first line of a practice run's file. It holds no comma, so it is one spreadsheet cell. */
export const PRACTICE_FILE_NOTE = "PRACTICE RUN: every reading in this file is made up. None was measured.";

export const SAVE_FIRST = "Save them before you collect another run.";

export const REPLACE_QUESTION =
  "Replace the run kept in this browser? A run you have not saved as a spreadsheet will be lost.";
export const CLEAR_QUESTION =
  "Clear the run kept in this browser? A run you have not saved as a spreadsheet will be lost.";

export const CLEAR_NOTE =
  "The last run stays in this browser until you clear it. On a shared computer, the next person to open this page sees it.";

export const NO_STORAGE_LINE =
  "This browser is not keeping runs (a private window, or no room left), so closing this tab loses the run.";

export const NON_AFFILIATION =
  "ProbeTab is an independent project. It is not affiliated with, or endorsed by, Vernier or Texas Instruments.";
