# protocol/

What this project knows about the LabPro, and how it knows it.

## labpro-facts.toml

[labpro-facts.toml](labpro-facts.toml) is the single source for facts about
the LabPro.

- Code takes its values from it, or from files generated from it, and never
  retypes them.
- A document may restate a value for its reader, beside the page it comes from.
  The facts file wins any disagreement, and no gate compares the two.

Each fact names its source, the source's page, the words on that page that
state it, and a status:

- `manual`: read from the source and not yet seen on a bench;
- `bench`: confirmed on a LabPro, with `trace` naming the recorded trace.

Every `bench` fact so far rests on one session, on 2026-11-25, with one LabPro
and one Windows computer.

`python tools/check.py` does two things with this file:

- It holds every fact to that shape.
- Where the manual is present, it finds each fact's words on the cited page.

It does not check that a fact's value agrees with its words. That is a
reader's check.

## The source

Vernier's LabPro Technical Reference Manual, revision dated 08/02/02.

- The copy cited is pinned by size and SHA-256 in labpro-facts.toml.
- Page numbers are the PDF's own. On every page a fact's `page` field cites,
  they match the manual's printed numbers. The appendices are numbered apart:
  the PDF's page 78 is printed A-1, pages 79 to 83 are B-1 to B-5, and page 84
  is C-1. The facts file's notes and comments, REFERENCE.md and the runbook
  cite some of those pages, always by the PDF's number.
- The manual is not in this repository and is not to be added.

## traces/ and fixtures/

- [traces/](traces/FORMAT.md) holds recordings of real bench sessions, each
  pinned by its SHA-256 in `traces/SHA256SUMS`. A fact becomes `bench` only by
  naming one. The first 16 came from the session of 2026-11-25, on Windows,
  and three more from the session of 2026-11-27, on a MacBook.
- [fixtures/](fixtures/README.md) holds hand-written traces, the lead's model of
  the device, for tests. They are not evidence.
- [traces/FORMAT.md](traces/FORMAT.md) describes the format.
  `tools/traces.py` defines it.

## REFERENCE.md

[REFERENCE.md](REFERENCE.md) describes the commands Phase 0 sends first, in
this project's own words. It also lists:

- where the manual disagrees with itself;
- what only the bench can settle, and what it has settled so far.

## Still to come

The rest of the bench's answers: REFERENCE.md's questions 3, 4 and 6, a
session on a Chromebook, and recordings for the facts still `manual`.

## Licence

This folder's licence is the one the folder table in
[README.md](../README.md) gives it.

The evidence phrases are short quotations from the manual. They remain
Vernier's, and [LICENSE-DOCS-DATA](../LICENSE-DOCS-DATA) excepts them.
