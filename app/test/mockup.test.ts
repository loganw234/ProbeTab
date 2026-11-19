// Held here: the classroom app's mockup (app/mockup/index.html) loads nothing from another site.
// Also held: its table's numbers are the formula its comment names, and it says on its face it is a mockup.
//
// The net: a reference is an attribute value (src, href, srcset, action, poster, formaction) or a CSS
// url(...) or @import that begins with a scheme ("https:", "data:", "javascript:" ...) or with "//".
//
// What the net cannot see: a URL built by script (the page holds no script, which a test below checks);
// an address in an attribute outside the list (object data=, meta refresh content=, body background=);
// a URL in a CSS string outside url() and @import, such as image-set("https://..."); a scheme written
// with character references, such as &#104;ttps:; a relative path that the server maps to another
// site; text a reader follows by hand, such as a printed address; CSS written with escapes (a backslash
// inside the url) or split across lines inside a quoted string. verifier-mockup planted the body
// background, image-set and character-reference forms on 2026-11-19, and each got past the net.
// It reads text, not the browser's own parse, so it can mistake an attribute written inside a comment
// for a real one: it errs towards finding too much.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const PAGE = new URL("../mockup/index.html", import.meta.url);

const FAR = /^\s*(?:[a-z][a-z0-9+.-]*:|\/\/)/i;

export function farReferences(html: string): string[] {
  const found: string[] = [];
  // Attributes, quoted or not. A name must start after whitespace, a quote or a colon (xlink:href).
  const attr = /(?:^|[\s"':])(src|href|srcset|action|formaction|poster)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))/gi;
  for (const m of html.matchAll(attr)) {
    const name = m[1].toLowerCase();
    const value = m[2] ?? m[3] ?? m[4] ?? "";
    const parts = name === "srcset" ? value.split(",").map((p) => p.trim().split(/\s+/)[0]) : [value];
    for (const p of parts) if (FAR.test(p)) found.push(`${name}=${p}`);
  }
  // CSS url(...), quoted or not.
  for (const m of html.matchAll(/url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s]*))\s*\)/gi)) {
    const v = m[1] ?? m[2] ?? m[3] ?? "";
    if (FAR.test(v)) found.push(`url(${v})`);
  }
  // CSS @import, with a string or with url(...) (the latter is also caught above).
  for (const m of html.matchAll(/@import\s+(?:url\(\s*)?(?:"([^"]*)"|'([^']*)')/gi)) {
    const v = m[1] ?? m[2] ?? "";
    if (FAR.test(v)) found.push(`@import ${v}`);
  }
  return found;
}

test("the finder: each planted form is found", () => {
  const planted: [string, string][] = [
    ['<link rel="stylesheet" href="https://fonts.example/x.css">', "href=https://fonts.example/x.css"],
    ["<script src='http://cdn.example/a.js'></script>", "src=http://cdn.example/a.js"],
    ["<img src=//cdn.example/a.png>", "src=//cdn.example/a.png"],
    ['<img srcset="a.png 1x, https://cdn.example/b.png 2x">', "srcset=https://cdn.example/b.png"],
    ['<form action="https://collect.example/post">', "action=https://collect.example/post"],
    ['<video poster="//cdn.example/p.jpg">', "poster=//cdn.example/p.jpg"],
    ["<style>body { background: url(https://cdn.example/b.png) }</style>", "url(https://cdn.example/b.png)"],
    ["<style>body { background: url( 'https://cdn.example/b.png' ) }</style>", "url(https://cdn.example/b.png)"],
    ['<style>@import "https://fonts.example/y.css";</style>', "@import https://fonts.example/y.css"],
    ["<style>@import url(//fonts.example/z.css);</style>", "url(//fonts.example/z.css)"],
    ['<svg><use xlink:href="https://cdn.example/s.svg#a"/></svg>', "href=https://cdn.example/s.svg#a"],
    ['<a HREF="javascript:alert(1)">x</a>', "href=javascript:alert(1)"],
  ];
  for (const [snippet, expected] of planted) {
    assert.ok(farReferences(snippet).includes(expected), `not found in ${snippet}: got ${JSON.stringify(farReferences(snippet))}`);
  }
});

test("the finder: a clean snippet gives nothing", () => {
  const clean = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><line x1="1"/></svg>
    <a href="#top">top</a><a href="other.html">x</a><img src="pics/a.png" srcset="a.png 1x, b.png 2x">
    <style>body { background: url(pics/b.png); } @import "local.css";</style>
    <form action="save">`;
  assert.deepEqual(farReferences(clean), []);
});

const html = readFileSync(PAGE, "utf8");

test("the mockup loads nothing from another site", () => {
  assert.deepEqual(farReferences(html), []);
});

test("the mockup holds no script and no frame, object or embed", () => {
  assert.ok(!/<script\b/i.test(html), "a script tag");
  assert.ok(!/<(?:iframe|object|embed|link|base)\b/i.test(html), "a frame, object, embed, link or base tag");
  assert.ok(!/\son[a-z]+\s*=/i.test(html), "an event-handler attribute");
});

test("the table's numbers are the formula the page's comment names", () => {
  const f = html.match(/FORMULA: T\(t\) = ([\d.]+) \+ ([\d.]+)\*exp\(-t\/([\d.]+)\) \+ ([\d.]+)\*sin\(t\/([\d.]+)\)/);
  assert.ok(f, "no FORMULA line in the page's comment");
  const [A, B, C, D, E] = f.slice(1).map(Number);
  const T = (t: number) => (Math.round((A + B * Math.exp(-t / C) + D * Math.sin(t / E)) * 10) / 10).toFixed(1);
  const rows = [...html.matchAll(/<tr class="[^"]*"><td>(\d+)<\/td><td>([\d.]+)<\/td><\/tr>/g)];
  assert.equal(rows.length, 25, "rows in the table");
  for (const [, t, v] of rows) assert.equal(v, T(Number(t)), `at ${t} seconds`);
  // The big readings and the graph's captions repeat two of those values.
  assert.ok(html.includes(`>${T(70)}</span>`) && html.includes(`>${T(120)}</span>`), "big readings");
});

test("the mockup says on its face that it is one, and carries the non-affiliation line", () => {
  assert.match(html, /<strong>MOCKUP\.<\/strong> The buttons do nothing yet, and every reading is made up\./);
  assert.match(html, /Made-up readings: a cup of warm water cooling\. Not a measurement\./);
  assert.match(html, /not affiliated with, or endorsed by, Vernier or Texas Instruments/);
  assert.ok(html.includes("<caption>"), "a table caption");
  assert.ok(html.includes('role="status"'), "a polite live region");
});
