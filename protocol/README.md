# protocol/

What this project knows about the LabPro, and how it knows it.

## labpro-facts.toml

[labpro-facts.toml](labpro-facts.toml) is the single source for facts about
the LabPro. Code and documents take their values from it, or from files
generated from it; they do not restate them.

Each fact names its source, the source's page, the words on that page that
state it, and a status:

- `manual`: read from the source and not yet seen on a bench;
- `bench`: confirmed on a LabPro, with `trace` naming the recorded trace.

`python tools/check.py` does two things with this file:

- It holds every fact to that shape.
- Where the manual is present, it finds each fact's words on the cited page.

It does not check that a fact's value agrees with its words. That is a
reader's check.

## The source

Vernier's LabPro Technical Reference Manual, revision dated 08/02/02.

- The copy cited is pinned by size and SHA-256 in labpro-facts.toml.
- Page numbers are the PDF's own. On every page cited so far they match the
  manual's printed numbers.
- The manual is not in this repository and is not to be added.

## Still to come

- The protocol reference, written in this project's own words from the manual
  and the bench.
- The recorded traces that test it.

## Licence

This folder's licence is the one the folder table in
[README.md](../README.md) gives it.

The evidence phrases are short quotations from the manual. They remain
Vernier's, and [LICENSE-DOCS-DATA](../LICENSE-DOCS-DATA) excepts them.
