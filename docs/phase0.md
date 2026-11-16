# Phase 0: first contact with a LabPro

The runbook for the first sessions with a LabPro, on the MacBook. Each step
says what to run, what to watch for, and what to keep.

A reading that looks right is not evidence that it is right. What counts is
the trace each step writes, kept as the last section says.

## Before the LabPro is plugged in

On the MacBook, from the repository's root, at the latest `main`:

1. **Python 3.11 or later.** Check `python3 --version`. macOS's own Python may
   be older; Homebrew's is new enough, from `brew install python`.
2. **libusb,** from Homebrew: `brew install libusb`. pyusb finds it in
   `/opt/homebrew/lib` on Apple Silicon, as
   [tools/bench/README.md](../tools/bench/README.md) says.
3. **The bench script's environment.** On the Mac:

       python3 -m venv .venv
       .venv/bin/python -m pip install --require-hashes --no-deps -r tools/bench/requirements.txt

   pip installs only the pinned pyusb, by its hash. The bench README's own
   commands are the ones the desktop used; these are their Mac form, not yet
   run on a Mac.
4. **Node 22.19 or later,** from `brew install node` if `node --version` gives
   an older one (BELIEVED to be new enough). Then, for typescript, in `app/`,
   run `npm ci --ignore-scripts`.
5. **The gate:** `python3 tools/check.py`. Read its `VERDICT` line and every
   `SKIP` line.
   - **Three checks skip by name in a fresh clone:** reference and facts, because
     the manual is not in it, and privacy, because the list of private strings
     is kept on the desktop alone.
   - **The checks this setup is for are bench, app and types,** and each must
     read PASS.
6. **The bench page's build:** in `app/`, run
   `node node_modules/typescript/bin/tsc -p tsconfig.build.json`.
7. **Chrome.**

## The bench, and safety

- **The LabPro's power.** Page 74 gives a regulated 6 V DC adapter of 600 mA,
  on a 2.1 mm jack with its centre negative, or four AA alkaline cells. Use
  nothing else.
- **There is no power switch** (page 5). To power-cycle the unit, unplug its
  adapter and take out any cells, wait a few seconds, then power it again.
  - **A loss of power clears the data the unit holds** (page 26).
  - So does pressing its Quick Setup button. Leave that button alone while the
    unit holds data you want.
- **The probe's own marked range** is what governs. Stay inside it. Page 74
  gives the LabPro's inputs overvoltage protection to 110 V, powered or not.
- **The bench supply:**
  - Set its voltage, and a low current limit such as 20 mA, before you connect
    it. A voltage probe draws almost nothing (BELIEVED).
  - Connect the probe's red lead to the supply's positive terminal, and its
    black lead to the negative (BELIEVED, from the leads' colours).
- **Earthing.** Check how the supply's output is earthed before you connect it.
  A loop through the supply's earth and the Mac's charger is possible
  (BELIEVED). Running the Mac on its battery for the session avoids that loop
  (BELIEVED).
- **The drain's resistor** must be rated for the power it carries. That power
  is the battery's voltage squared, over the resistance. For example, 1.5 V
  across 10 ohms is 0.225 W, so use a resistor rated 0.5 W or more
  (COMPUTED).

## The session, in order

Name each trace for its step and its date, such as
`2026-11-20-first-contact.trace`. The script never writes over a file.

### 1. Power up, then first contact

1. **Power the LabPro, and listen** (page 79).
   - **A normal start** is six beeps in three pairs, high-high, medium-medium,
     then low-to-high, as the red, yellow and green lights come on in turn.
   - **Two high-high beeps alone** mean its base code is missing.
   - **Three high-high beeps** mean the power-up self-test failed.

   Write down what you hear and see.
2. **Connect its USB cable to the Mac.** A Mac with USB-C ports alone needs a
   USB-C-to-A adapter for it.
3. **Record its descriptors and its status:**

       .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-first-contact.trace --descriptors

   - This sends Command 7 alone, framed the manual's way (`s-cr`), and changes
     nothing the unit holds.
   - pyusb may set the unit's USB configuration, as the bench README says.
4. **Exit status 0** means the reply was recognised. Note every line that begins
   `differs from the manual` or `refused`.

### 2. Command 7 in each framing, until one is answered

If `s-cr` draws no reply, try the others in this order, one at a time:

    .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-form-s.trace --form s
    .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-form-cr.trace --form cr
    .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-form-bare.trace --form bare

Each run writes its own trace, even one that drew nothing.

**Between framings:** a framing that drew no reply may have left part of a
command in the unit.
- **While no framing has yet drawn a reply,** power-cycle the LabPro before
  the next framing, as the safety section says.
- **Once a Command 7 has shown data not yet retrieved,** stop. A power-cycle
  would lose that data, so you decide then whether it matters.

**Listen as well.** Page 79 says the LabPro beeps when its base code finds an
error in a command from the host. A beep after a framing is evidence about it;
write it down beside the trace's name.

**If no framing is answered,** stop there. Keep the four traces and your
notes, and send them to the lead. The next step is decided from them.

**Every later run** uses the framing that was answered, with `--form`. In the
commands below, put that framing, such as `s-cr`, where `FRAMING` stands.

### 3. The guarded reset, then CH1

1. Put the voltage probe on CH1, and its leads on the bench supply.
2. For each of a few known voltages inside the probe's range, spread across it:
   1. Set the supply, and read the voltage with a meter if you have one.
   2. Run:

          .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-ch1-1v00.trace --read-ch1 --form FRAMING

   3. Write the voltages down beside the trace's name.
3. **The reset goes only to a unit that is idle or done.** The script refuses a
   unit holding data not yet retrieved. `--discard` resets it anyway, and that
   data is lost: nothing here can retrieve it yet.

What CH1's value means, a reading in the sensor's units or a raw voltage, is
[protocol/REFERENCE.md](../protocol/REFERENCE.md)'s question 4. These traces
answer it.

### 4. The battery drain

Put the battery and its resistor across the probe, then take a live reading:

    caffeinate -i .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-drain.trace --read-ch1 --form FRAMING --every 10 --for 3600

- Choose the interval and the length to suit the battery.
- `caffeinate -i` keeps the Mac from sleeping while the run lasts (BELIEVED).
  Keep its lid open.
- Ctrl-C stops the run early, and the trace keeps the transfers made so far.

### 5. The browser page

1. Serve it: `python3 tools/bench/serve.py`.
2. Open `http://127.0.0.1:8000/bench/` in Chrome.
3. Choose the framing, then press Connect, and pick the LabPro.
4. Press Read CH1, with or without a live reading.
5. Press Save the record. It downloads as JSON.
6. Write the trace from it. The download's name ends with the session's date
   and time, which stand where `DATE` is. If Chrome adds a number to a
   repeated name, such as ` (1)`, use the name it gave:

       python3 tools/bench/from_browser.py ~/Downloads/probetab-bench-DATE.json --out 2026-11-20-browser.trace

[app/README.md](../app/README.md) says what each button does.

**Use the page when no bench script run is under way.** A run ends when the
script exits, so a finished run holds nothing.

## Keeping the evidence

**Send the lead the traces and your notes:**
- what was connected;
- the voltages;
- the framings;
- the beeps;
- every line the script began `differs from the manual` or `refused`.

The lead then keeps each trace that is to be evidence:
1. It goes into `protocol/traces/`.
2. Its line goes into `protocol/traces/SHA256SUMS`, as `<sha256>  <name>.trace`.
3. The session goes into the lead's ledger.

Then [protocol/REFERENCE.md](../protocol/REFERENCE.md)'s questions for Phase 0
are answered from the traces, each answer naming the trace that showed it.
[protocol/traces/FORMAT.md](../protocol/traces/FORMAT.md) says what a trace
holds.

The page's JSON records stay on the Mac. The traces made from them are the
evidence.

## If the LabPro stops answering

Page 79 gives a manual reset: keep Start/Stop pressed for five seconds. It
works on firmware 6.022 or newer.
- **Page 79 does not say what this reset clears.** Treat it as clearing the
  data buffer, as a reset command does (page 26).
- **Command 7's first register is the software ID,** written `X.MMmms`, which a
  trace records as its `firmware`. How page 79's "6.022" reads against that
  form is for the bench to show.

## A Chromebook, later

There is no Chromebook for Phase 0. When one is acquired:
- the page would be served from its Linux container, and ChromeOS would forward
  the port to `localhost` (BELIEVED);
- a school-managed Chromebook may block WebUSB.

Both are checked then.

## Windows

The Mac is Phase 0's host.
- **On Windows, the bench script needs the WinUSB driver bound to the
  LabPro,** as [tools/bench/README.md](../tools/bench/README.md) says.
- **A browser may need it too,** as [app/README.md](../app/README.md) says.
  That is measured when Windows is.
- **Binding the driver changes the machine's drivers.** It is the owner's to
  make, apart from this runbook.

Its licence is the one the folder table in [README.md](../README.md) gives it.
