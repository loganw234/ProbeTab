// Stand-ins for the classroom screen's tests: a storage, a storage that fails, and a clock driven
// by hand. Not a test file: the gate runs only *.test.ts, each alone.

import type { StorageLike } from "../src/collect/history.ts";
import type { Timers } from "../src/collect/practice.ts";

/** A working localStorage. */
export class MemoryStorage implements StorageLike {
  readonly map = new Map<string, string>();
  getItem(key: string): string | null {
    return this.map.has(key) ? (this.map.get(key) as string) : null;
  }
  setItem(key: string, value: string): void {
    this.map.set(key, value);
  }
  removeItem(key: string): void {
    this.map.delete(key);
  }
}

/** A storage whose every call throws, as one can in a private window or when blocked. */
export class ThrowingStorage implements StorageLike {
  getItem(): string | null {
    throw new Error("storage blocked");
  }
  setItem(): void {
    throw new Error("storage blocked");
  }
  removeItem(): void {
    throw new Error("storage blocked");
  }
}

/** A full storage: it reads, and refuses to write, as a browser does when its quota is used. */
export class FullStorage extends MemoryStorage {
  override setItem(): void {
    throw new Error("QuotaExceededError");
  }
}

/** Timers that run only when the test says so. */
export class ManualTimers implements Timers {
  private next = 1;
  readonly waiting = new Map<number, { run: () => void; milliseconds: number }>();
  setTimeout(run: () => void, milliseconds: number): unknown {
    const id = this.next++;
    this.waiting.set(id, { run, milliseconds });
    return id;
  }
  clearTimeout(handle: unknown): void {
    this.waiting.delete(handle as number);
  }
  /** Run the one waiting timer, and say how long it waited. Null when none waits. */
  fire(): number | null {
    const first = this.waiting.entries().next();
    if (first.done === true) {
      return null;
    }
    const [id, timer] = first.value;
    this.waiting.delete(id);
    timer.run();
    return timer.milliseconds;
  }
  /** Run timers until none waits. */
  drain(): number {
    let count = 0;
    while (this.fire() !== null) {
      count += 1;
    }
    return count;
  }
}
