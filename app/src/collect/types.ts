// The shapes the classroom screen shares. None is a fact about the LabPro.

/** The unit a temperature is shown in. Readings are never stored in it: see KeptRun. */
export type Unit = "C" | "F";

/** One reading: the seconds since the run began, and the value exactly as the source gave it,
 * in the source's own unit (degrees Celsius for the practice source). */
export interface Reading {
  readonly t: number;
  readonly v: number;
}

/** The two choices a person makes before a run. They are not facts about the LabPro. */
export interface Settings {
  readonly everySeconds: number;
  readonly forSeconds: number;
}

/** How a kept run ended: "open" when it was last saved mid-run, "done" when it reached its
 * length, "stopped" when Stop was pressed. */
export type End = "open" | "done" | "stopped";

/** The last run, as the browser keeps it. Its readings are as the source gave them, in
 * storedUnit, whatever unit the page shows. */
export interface KeptRun {
  readonly version: 1;
  readonly practice: boolean;
  readonly storedUnit: "C";
  readonly startedAt: string;
  readonly settings: Settings;
  readonly end: End;
  readonly readings: readonly Reading[];
}

/** Where readings come from. A source starts with the choices, gives each reading's time and
 * value, says when it is done, and can be stopped. */
export interface ReadingSource {
  /** True when the readings are made up. */
  readonly practice: boolean;
  start(settings: Settings, onReading: (reading: Reading) => void, onEnd: () => void): void;
  stop(): void;
}
