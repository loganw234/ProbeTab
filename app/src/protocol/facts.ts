// The facts about the LabPro, as the protocol and the transports read them. Each value comes
// from protocol/labpro-facts.toml through its generated copy, and none is retyped here.

import { LABPRO_FACTS, type LabProFact } from "../generated/labpro-facts.ts";

function fact(name: string): LabProFact {
  const found = LABPRO_FACTS[name];
  if (found === undefined) {
    throw new Error(`protocol/labpro-facts.toml has no fact named ${name}`);
  }
  return found;
}

/** The fact's value, which must be text. */
export function text(name: string): string {
  const value = fact(name).value;
  if (typeof value !== "string") {
    throw new TypeError(`the fact ${name} is not text`);
  }
  return value;
}

/** The fact's value, which must be a number. */
export function count(name: string): number {
  const value = fact(name).value;
  if (typeof value !== "number") {
    throw new TypeError(`the fact ${name} is not a number`);
  }
  return value;
}

/** The fact's name and page, for a message that rests on it. */
export function cite(name: string): string {
  return `${name}, page ${fact(name).page}`;
}
