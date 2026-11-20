// The graph: an inline SVG built as a string, no library, in the mockup's look (its classes
// are styled by the page). It plots the readings in the unit asked for, each converted once.
// It carries its own text alternative, and, for practice readings, the words "made up" inside
// the picture itself, so that a screenshot cropped to the graph still says so.

import { MADE_UP_PILL } from "./words.ts";
import { formatTemp, inUnit, unitLabel } from "./units.ts";
import type { Reading, Unit } from "./types.ts";

const LEFT = 56;
const RIGHT = 584;
const TOP = 14;
const BOTTOM = 196;

function esc(text: string): string {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function num(x: number): string {
  return String(Math.round(x * 10) / 10);
}

/** Round-number tick values covering lo to hi, with about four steps. */
export function niceTicks(lo: number, hi: number): number[] {
  const span = Math.max(hi - lo, 1);
  const raw = span / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? 10 * power;
  const first = Math.floor(lo / step + 1e-9);
  const last = Math.ceil(hi / step - 1e-9);
  const ticks: number[] = [];
  for (let i = first; i <= last; i += 1) {
    ticks.push(Math.round(i * step * 1000) / 1000);
  }
  return ticks;
}

function tickLabel(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** The words that stand in for the picture: the first, latest, lowest and highest readings. */
export function describeReadings(readings: readonly Reading[], unit: Unit, practice: boolean): string {
  const label = unitLabel(unit);
  const lead = `Graph of temperature against time.${practice ? " Made-up readings." : ""}`;
  const first = readings[0];
  const last = readings[readings.length - 1];
  if (first === undefined || last === undefined) {
    return `${lead} Empty: no readings yet.`;
  }
  const at = (r: Reading): string => `${formatTemp(r.v, unit)} ${label} at ${r.t} seconds`;
  let low = first;
  let high = first;
  for (const r of readings) {
    low = r.v < low.v ? r : low;
    high = r.v > high.v ? r : high;
  }
  return `${lead} First reading ${at(first)}. Latest ${at(last)}. Lowest ${at(low)}. Highest ${at(high)}.`;
}

export interface GraphOptions {
  readonly unit: Unit;
  readonly forSeconds: number;
  readonly practice: boolean;
}

export function graphSvg(readings: readonly Reading[], options: GraphOptions): string {
  const { unit, forSeconds, practice } = options;
  const shown = readings.map((r) => ({ t: r.t, y: inUnit(r.v, unit) }));
  // With no readings the axis shows 20 to 80 degrees Celsius, whatever the unit: a picture's
  // empty frame, not a fact about any sensor.
  const lo = shown.length === 0 ? inUnit(20, unit) : Math.min(...shown.map((p) => p.y));
  const hi = shown.length === 0 ? inUnit(80, unit) : Math.max(...shown.map((p) => p.y));
  const pad = shown.length === 0 ? 0 : Math.max((hi - lo) * 0.05, 0.5);
  const yTicks = niceTicks(lo - pad, hi + pad);
  const yMin = yTicks[0] ?? lo;
  const yMax = yTicks[yTicks.length - 1] ?? hi;
  const xMax = Math.max(forSeconds, ...shown.map((p) => p.t), 1);
  const x = (t: number): number => LEFT + (t / xMax) * (RIGHT - LEFT);
  const y = (v: number): number => BOTTOM - ((v - yMin) / (yMax - yMin)) * (BOTTOM - TOP);

  const parts: string[] = [];
  for (const tick of yTicks) {
    parts.push(`<line class="grid" x1="${LEFT}" y1="${num(y(tick))}" x2="${RIGHT}" y2="${num(y(tick))}"/>`);
    parts.push(`<text x="${LEFT - 8}" y="${num(y(tick) + 6)}" text-anchor="end">${tickLabel(tick)}</text>`);
  }
  for (let i = 0; i <= 4; i += 1) {
    const t = (xMax * i) / 4;
    parts.push(`<text x="${num(x(t))}" y="218" text-anchor="middle">${tickLabel(Math.round(t * 10) / 10)}</text>`);
  }
  parts.push(`<line class="axis" x1="${LEFT}" y1="${TOP}" x2="${LEFT}" y2="${BOTTOM}"/>`);
  parts.push(`<line class="axis" x1="${LEFT}" y1="${BOTTOM}" x2="${RIGHT}" y2="${BOTTOM}"/>`);
  parts.push(`<text x="320" y="242" text-anchor="middle">Time (seconds)</text>`);
  parts.push(`<text transform="translate(12 105) rotate(-90)" text-anchor="middle">Temperature (${unitLabel(unit)})</text>`);
  if (shown.length === 0) {
    parts.push(`<text class="hint" x="320" y="111" text-anchor="middle">The graph fills in when you press Start.</text>`);
  } else {
    const points = shown.map((p) => `${num(x(p.t))},${num(y(p.y))}`);
    if (points.length > 1) {
      parts.push(`<polyline class="line" points="${points.join(" ")}"/>`);
    }
    const end = shown[shown.length - 1];
    if (end !== undefined) {
      parts.push(`<circle class="dot" cx="${num(x(end.t))}" cy="${num(y(end.y))}" r="6"/>`);
    }
  }
  if (practice) {
    parts.push(`<text class="mark" x="${RIGHT - 8}" y="${TOP + 24}" text-anchor="end">${esc(MADE_UP_PILL)}</text>`);
  }
  const words = esc(describeReadings(readings, unit, practice));
  return (
    `<svg viewBox="0 0 600 244" role="img" aria-label="${words}"><title>${words}</title>` +
    parts.join("") +
    `</svg>`
  );
}
