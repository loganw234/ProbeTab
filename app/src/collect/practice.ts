// The practice source: made-up temperature readings, for use before a LabPro is connected.
//
// FORMULA: T(t) = 22 + 53*exp(-t/150) + 0.3*sin(t/4), t in seconds, shown to 0.1
// It is the formula of app/mockup/index.html, a cup of hot water cooling in a room. Every
// reading is COMPUTED from it, in degrees Celsius. It is not a measurement of anything.
//
// A reading's time is k times the interval, not the clock's: the clock only paces the readings.

import type { Reading, ReadingSource, Settings } from "./types.ts";

/** The made-up temperature at t seconds, in degrees Celsius, unrounded. */
export function practiceCelsius(t: number): number {
  return 22 + 53 * Math.exp(-t / 150) + 0.3 * Math.sin(t / 4);
}

/** What the source needs of a clock, so that a test can drive it by hand. */
export interface Timers {
  setTimeout(run: () => void, milliseconds: number): unknown;
  clearTimeout(handle: unknown): void;
}

export const browserTimers: Timers = {
  setTimeout: (run, milliseconds) => globalThis.setTimeout(run, milliseconds),
  clearTimeout: (handle) => globalThis.clearTimeout(handle as number),
};

/** How many readings a run of this length at this interval gives: one at 0, and one at each
 * whole interval up to the length. */
export function readingCount(settings: Settings): number {
  return Math.floor(settings.forSeconds / settings.everySeconds) + 1;
}

export class PracticeSource implements ReadingSource {
  readonly practice = true;
  private readonly timers: Timers;
  private handle: unknown = null;
  private generation = 0;

  constructor(timers: Timers = browserTimers) {
    this.timers = timers;
  }

  start(settings: Settings, onReading: (reading: Reading) => void, onEnd: () => void): void {
    this.stop();
    const mine = ++this.generation;
    const total = readingCount(settings);
    let k = 0;
    const tick = (): void => {
      if (mine !== this.generation) {
        return;
      }
      const t = k * settings.everySeconds;
      onReading({ t, v: practiceCelsius(t) });
      k += 1;
      if (k >= total) {
        this.handle = null;
        onEnd();
        return;
      }
      this.handle = this.timers.setTimeout(tick, settings.everySeconds * 1000);
    };
    tick();
  }

  stop(): void {
    this.generation += 1;
    if (this.handle !== null) {
      this.timers.clearTimeout(this.handle);
      this.handle = null;
    }
  }
}
