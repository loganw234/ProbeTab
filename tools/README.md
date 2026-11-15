# tools/

- [check.py](check.py) is the gate: the one command that says whether the
  repository still holds together. Its docstring lists the checks and their
  limits.
- [generate.py](generate.py) makes `app/src/generated/labpro-facts.ts` from
  `protocol/labpro-facts.toml`. Run it after changing the facts; `--check`
  writes nothing.
- [labpro_facts.py](labpro_facts.py) reads the facts file. It is the one place
  that decides which tables are facts, and Python tools read values through it.
- [traces.py](traces.py) defines the trace format: it reads, writes and checks
  traces.

Bench scripts for the LabPro join it from Phase 0. Its licence is the one the
folder table in [README.md](../README.md) gives it.
