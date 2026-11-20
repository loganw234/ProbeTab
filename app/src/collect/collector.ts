// The run, and what the buttons do to it. Plain logic with its dependencies handed in, so that
// Node tests it without a browser. page.ts only wires it to the page.
//
// The four states are the mockup's: before connecting, ready, collecting, finished.
// A kept run is never discarded without the question, every time, from Start, Collect another
// run and Clear alike. Nothing tracks whether a file was saved: the page cannot tell.

import { History } from "./history.ts";
import { CLEAR_QUESTION, EVERY_CHOICES, FOR_CHOICES, REPLACE_QUESTION } from "./words.ts";
import type { End, KeptRun, Reading, ReadingSource, Settings, Unit } from "./types.ts";

export type Phase = "before" | "ready" | "collecting" | "finished";

export interface CollectorDeps {
  readonly history: History;
  /** Asks the person a yes-or-no question. True is yes. */
  readonly confirm: (question: string) => boolean;
  readonly makePractice: () => ReadingSource;
  readonly now: () => Date;
}

export function validSettings(settings: Settings): boolean {
  return (
    EVERY_CHOICES.includes(settings.everySeconds) &&
    FOR_CHOICES.includes(settings.forSeconds) &&
    settings.everySeconds <= settings.forSeconds
  );
}

export class Collector {
  phase: Phase = "before";
  /** The run on show, while collecting or finished. */
  run: KeptRun | null = null;
  /** True while the run on show came from the browser's storage, not from this page's own run. */
  restored = false;
  unit: Unit;
  /** False once the browser would not keep a run, until a save works again. */
  storageOk: boolean;
  /** The source the page is connected to, once it is. */
  source: ReadingSource | null = null;

  private readonly deps: CollectorDeps;
  private readonly listeners: (() => void)[] = [];

  constructor(deps: CollectorDeps) {
    this.deps = deps;
    this.unit = deps.history.loadUnit();
    this.storageOk = deps.history.available();
    const kept = deps.history.loadRun();
    if (kept !== null) {
      this.run = kept;
      this.restored = true;
      this.phase = "finished";
    }
  }

  subscribe(listener: () => void): void {
    this.listeners.push(listener);
  }

  private changed(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }

  private persist(): void {
    if (this.run !== null) {
      this.storageOk = this.deps.history.saveRun(this.run);
    }
  }

  /** Before connecting: take the practice source. */
  connectPractice(): boolean {
    if (this.phase !== "before") {
      return false;
    }
    this.source = this.deps.makePractice();
    this.phase = "ready";
    this.changed();
    return true;
  }

  /** Ready: begin a run. Asks first when the browser holds a kept run. False when nothing began. */
  start(settings: Settings): boolean {
    const source = this.source;
    if (this.phase !== "ready" || source === null || !validSettings(settings)) {
      return false;
    }
    if (this.deps.history.loadRun() !== null && !this.deps.confirm(REPLACE_QUESTION)) {
      return false;
    }
    this.run = {
      version: 1,
      practice: source.practice,
      storedUnit: "C",
      startedAt: this.deps.now().toISOString(),
      settings: { everySeconds: settings.everySeconds, forSeconds: settings.forSeconds },
      end: "open",
      readings: [],
    };
    this.restored = false;
    this.phase = "collecting";
    this.persist();
    this.changed();
    // The source may give its first reading before start() returns, so everything is set first.
    source.start(
      this.run.settings,
      (reading) => this.onReading(source, reading),
      () => this.finish(source, "done"),
    );
    return true;
  }

  private onReading(source: ReadingSource, reading: Reading): void {
    if (this.phase !== "collecting" || this.source !== source || this.run === null) {
      return;
    }
    this.run = { ...this.run, readings: [...this.run.readings, reading] };
    this.persist();
    this.changed();
  }

  private finish(source: ReadingSource, end: End): void {
    if (this.phase !== "collecting" || this.source !== source || this.run === null) {
      return;
    }
    this.run = { ...this.run, end };
    this.phase = "finished";
    this.persist();
    this.changed();
  }

  /** Collecting: end the run early. The readings so far are kept. */
  stop(): boolean {
    const source = this.source;
    if (this.phase !== "collecting" || source === null) {
      return false;
    }
    source.stop();
    this.finish(source, "stopped");
    return true;
  }

  /** Finished: clear the kept run, after asking, and go back to the step before it. */
  private discard(question: string): boolean {
    if (this.phase !== "finished" || !this.deps.confirm(question)) {
      return false;
    }
    this.deps.history.clearRun();
    this.run = null;
    this.restored = false;
    this.phase = this.source === null ? "before" : "ready";
    this.changed();
    return true;
  }

  /** Finished: begin again, after asking. */
  another(): boolean {
    return this.discard(REPLACE_QUESTION);
  }

  /** Finished: remove the kept run, after asking. */
  clear(): boolean {
    return this.discard(CLEAR_QUESTION);
  }

  /** The °F toggle. It changes what is shown and saved, never what is stored. */
  setUnit(unit: Unit): void {
    this.unit = unit;
    this.deps.history.saveUnit(unit);
    this.changed();
  }
}
