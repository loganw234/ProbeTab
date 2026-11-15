# Working on ProbeTab

Short, and only what is non-obvious. The README says what ProbeTab is; this
says what will bite.

## Start here: one command answers "does it still hold?"

    python tools/check.py                    # seconds; one line per check, then VERDICT
    python tools/check.py --control          # each check shown to fail on a planted fault
    python tools/check.py --require-all      # a SKIP becomes a failure
    python tools/check.py --history RANGE    # also scans RANGE's commits: headers, messages, added lines

Read the `VERDICT` line and every `SKIP` line; the exit code is the weakest
signal. The script's docstring says what each check holds and what it cannot
see. There is no cache, so every run does everything.

Before a commit, run it with `--require-all`. Its `staged` check fails if a
staged copy differs from the working copy the other checks read.

## The authority

The LabPro on the bench, through recorded traces. Vernier's manual is a source,
not the authority.

- A fact about the LabPro goes into `protocol/labpro-facts.toml` first, with
  its page and the words that state it, status `manual`.
- It becomes `bench` only with a recorded trace.
- Code and documents take values from that file and never retype them.
- After changing it, run `python tools/generate.py`. The app's copy is
  generated, and the gate fails until it matches.
- Recordings of real sessions go in `protocol/traces/`, listed in its
  `SHA256SUMS`. Hand-written traces go in `protocol/fixtures/`, and are never
  evidence.

## Never commit

- **Vernier's manual, or any copy, extract or long quotation of it.** It is
  not ours to publish. The owner keeps it in the repository folder, where
  `.gitignore` covers it. The gate refuses any PDF, and the manual's exact
  bytes under any name. It cannot see a pasted passage, so that part is yours.
- **Personal data:** home-directory paths, email addresses, hostnames and LAN
  addresses.
  - The gate scans files. Before a push, run it with `--history` over the
    commits being pushed.
  - Write paths outside the repository as `<repos>/...`.

## Traps on this desktop

Each has already cost time in the owner's other projects.

1. **A bare `bash` started from Python is WSL, not Git Bash.** Windows searches
   System32 first. Start programs by full path, or resolve them with
   `shutil.which` and print what was found.
2. **Python text-mode writes produce CRLF.** `.gitattributes` keeps bytes exact
   (`* -text`), so a CRLF would reach a commit silently; the gate's `eol` check
   refuses it. Write bytes, or pass `newline="\n"`.
3. **Backslashes typed into `printf` or a heredoc in this harness arrive
   altered.** Write files that contain backslashes with an editor tool, and use
   forward slashes in commands.
4. **The desktop is shared with its owner, who uses it at the same time.** Put
   no deliberate load on it; long runs are the lead's to schedule.

## The discipline that matters most here

A reading that looks right is not evidence that it is right. Every protocol
claim names the trace that showed it, or says it comes from the manual and is
unverified.
