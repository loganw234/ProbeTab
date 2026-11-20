// Held here: the classroom screen's page (app/collect/index.html) and its code load nothing from
// another site, in the forms the net of mockup.test.ts reads (its header names those it misses; a
// URL built by script is checked here only by searching the code for the calls that would send
// anything out); the page's script is its own built module and nothing else; every id the glue looks
// up is in the page; no LabPro value from the facts is typed in the page or its code; the page says
// what it must say.
//
// Not held: that the built page runs (page.ts says what has run it, and when).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { text } from "../src/protocol/facts.ts";
import { farReferences } from "./mockup.test.ts";

const PAGE = new URL("../collect/index.html", import.meta.url);
const CODE = new URL("../src/collect/", import.meta.url);
const html = readFileSync(PAGE, "utf8");
const sources = readdirSync(CODE)
  .filter((n) => n.endsWith(".ts"))
  .map((n) => [n, readFileSync(new URL(n, CODE), "utf8")] as const);

test("the page loads nothing from another site", () => {
  assert.deepEqual(farReferences(html), []);
  assert.ok(!/https?:\/\/|\/\/[a-z0-9.-]+\.[a-z]{2,}/i.test(html.replace(/<!--[\s\S]*?-->/g, "")), "an address in the page");
});

test("its one script is its own built module, by a relative path, and nothing else runs", () => {
  const scripts = [...html.matchAll(/<script\b[^>]*>/gi)].map((m) => m[0]);
  assert.deepEqual(scripts, ['<script type="module" src="../web/collect/page.js">']);
  assert.ok(!/<script\b[^>]*>\s*\S/i.test(html.replace(/<script\b[^>]*src=[^>]*><\/script>/gi, "")), "an inline script");
  assert.ok(!/<(?:iframe|object|embed|link|base|img|video|audio|source)\b/i.test(html), "a tag that loads something");
  assert.ok(!/\son[a-z]+\s*=/i.test(html), "an event-handler attribute");
  assert.ok(!/@import|@font-face|font-family:\s*["']?[A-Z][a-z]+[^;]*\.(?:woff|ttf)/i.test(html), "a font or an import");
});

test("the code sends nothing out and loads nothing", () => {
  const out = /\bfetch\s*\(|XMLHttpRequest|sendBeacon|WebSocket|EventSource|importScripts|\bimport\s*\(|https?:\/\/|\.src\s*=|new Image\b|cookie/;
  for (const [name, src] of sources) {
    const code = src.replace(/\/\/[^\n]*/g, "").replace(/\/\*[\s\S]*?\*\//g, "");
    assert.ok(!out.test(code), `${name}: ${out.exec(code)?.[0]}`);
  }
});

test("every id the glue looks up is in the page, and no id is there twice", () => {
  const page = sources.find(([n]) => n === "page.ts")?.[1] ?? "";
  const wanted = [...page.matchAll(/\bel(?:<[^>]+>)?\("([a-z-]+)"\)/g)].map((m) => m[1] as string);
  assert.ok(wanted.length >= 25, `${wanted.length} ids found in page.ts`);
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1] as string);
  for (const id of wanted) {
    assert.ok(ids.includes(id), `#${id} is not in the page`);
  }
  assert.equal(new Set(ids).size, ids.length, "an id is used twice");
});

test("no LabPro value from the facts is typed in the page or its code", () => {
  const power = text("power.supply");
  const pieces = power.split(/,| or /).map((p) => p.trim()).filter((p) => p !== "");
  assert.ok(pieces.length >= 2, "the fact's text has pieces to look for");
  const files: [string, string][] = [["index.html", html], ...sources];
  for (const [name, src] of files) {
    for (const piece of [power, ...pieces]) {
      assert.ok(!src.includes(piece), `${name} types "${piece}"`);
    }
  }
  // The page reads the fact through the facts module, by its name.
  const page = sources.find(([n]) => n === "page.ts")?.[1] ?? "";
  assert.match(page, /import \{ text \} from "\.\.\/protocol\/facts\.ts";/);
  assert.match(page, /text\("power\.supply"\)/);
});

test("the page says what it must say", () => {
  assert.match(html, /<html lang="en">/);
  assert.match(html, /<button type="button" class="btn big" id="btn-connect" disabled>Connect the LabPro<\/button>/);
  assert.match(html, /id="btn-practice">Practise with made-up readings</);
  assert.match(html, /not affiliated with, or endorsed by, Vernier or Texas Instruments/);
  assert.match(html, /role="status" aria-live="polite"/);
  assert.match(html, /<caption id="table-caption">/);
  assert.match(html, /<th scope="col">Time \(seconds\)<\/th>/);
  assert.match(html, /<input type="checkbox" id="unit-f">Show °F/);
  assert.match(html, /Collect another run/);
  assert.match(html, /Save as spreadsheet/);
  assert.match(html, /nothing leaves this computer/);
  assert.match(html, /not been tried with a screen reader or on a Chromebook/);
  assert.match(html, /<meta name="viewport" content="width=device-width, initial-scale=1">/);
});

test("the page has no readings or temperatures of its own: they all come from the script", () => {
  const body = html.replace(/<!--[\s\S]*?-->/g, "").replace(/<style>[\s\S]*?<\/style>/, "");
  assert.ok(!/\b\d{2}\.\d\b/.test(body), "a reading typed into the page");
});
