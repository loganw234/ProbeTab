// Degrees Celsius and Fahrenheit, applied once, at the edge where a reading is shown or saved.
// Stored readings are never converted: they stay as the source gave them.

import type { Unit } from "./types.ts";

/** F = C x 9/5 + 32, the definition of the scale. It is not a fact about the LabPro. */
export function toFahrenheit(celsius: number): number {
  return (celsius * 9) / 5 + 32;
}

/** A stored Celsius reading as a number in the unit asked for. */
export function inUnit(celsius: number, unit: Unit): number {
  return unit === "F" ? toFahrenheit(celsius) : celsius;
}

/** A stored Celsius reading as shown: converted once, then rounded to 0.1. */
export function formatTemp(celsius: number, unit: Unit): string {
  return (Math.round(inUnit(celsius, unit) * 10) / 10).toFixed(1);
}

export function unitLabel(unit: Unit): string {
  return unit === "F" ? "°F" : "°C";
}
