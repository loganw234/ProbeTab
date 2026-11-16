# tools/

- [check.py](check.py) is the gate: the one command that says whether the
  repository still holds together. Its docstring lists the checks and their
  limits.
- [generate.py](generate.py) makes the app's copies of the protocol folder's
  sources: `app/src/generated/labpro-facts.ts` from
  `protocol/labpro-facts.toml`, and `app/test/generated/fixtures.ts` from
  `protocol/fixtures/`. Run it after changing the facts or a fixture; `--check`
  writes nothing.
- [labpro_facts.py](labpro_facts.py) reads the facts file. It is the one place
  that decides which tables are facts, and Python tools read values through it.
- [traces.py](traces.py) defines the trace format: it reads, writes and checks
  traces.
- [bench/](bench/README.md) holds the bench script for Phase 0's first contact
  with a LabPro, the fake LabPro its tests run against, and how to set both up.

Its licence is the one the folder table in [README.md](../README.md) gives it.
