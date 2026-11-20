# Phase 0: first contact with a LabPro

The runbook for the first sessions with a LabPro, on the MacBook. Each step
says what to run, what to watch for, and what to keep.

[phase0-evidence.md](phase0-evidence.md) is a map of which facts each step's
trace can settle.

A reading that looks right is not evidence that it is right. What counts is
the trace each step writes, kept as the last section says.

**Every expected outcome about the unit below is BELIEVED,** from the manual
and the code, until a trace shows it. No LabPro has been connected yet.

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
   - **To rehearse the page first,** with no LabPro, also run
     `node node_modules/typescript/bin/tsc -p tsconfig.rehearse.json`, serve the
     page as in section 5, and open `http://127.0.0.1:8000/bench/rehearse.html`.
     [app/README.md](../app/README.md) says what it shows. Its records are not
     evidence.
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
5. **Read the state line.** After the reply's values, the script prints one
   line, such as `state: idle; QuickSetup flag clear; unretrieved-data flag
   clear` (page 45). Write it down. **The data check.** A power-cycle or a Quick
   Setup press loses data the unit holds (page 26), and the script never resets
   an armed or busy unit. So a state line passes the data check only when
   **both** parts hold:
   - **(a)** the state is `idle` or `done`;
   - **(b)** the line says `unretrieved-data flag clear`.

   If either fails, the line fails the check: an `idle` line that says
   `unretrieved-data flag set` fails it. **Step 2 goes on only by this line,
   passing the check,** and step 6 applies the same check to its own first
   trace. A system state the facts do not give is printed as that, and the run
   is not refused for it.

### 2. Command 7 in the other framings

Which framing the unit takes is the first thing to settle. Two cases, by what
step 1 drew.

**A. `s-cr` drew no reply.** Try the others in this order, one at a time, and
stop at the first one that is answered:

    .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-form-s.trace --form s
    .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-form-cr.trace --form cr
    .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-form-bare.trace --form bare

**B. `s-cr` was answered.** That shows the `s` and the carriage return are
accepted, not that each is needed. Run each of the other three once, in the
same commands as above, **only if** step 1's state line passes the data check
(step 1, item 5): the state is `idle` or `done`, **and** the unretrieved-data
flag is `clear`. Otherwise skip case B: the power-cycle it
may need would lose the unit's run or its data.

Each run writes its own trace, even one that drew nothing.

**Between framings:** a framing that drew no reply may have left part of a
command in the unit, so power-cycle the LabPro after it, as the safety section
says. In case B, that includes the last framing, before step 3.
- **Before each power-cycle,** look at the latest state line you have, from
  step 1 or from a framing that was answered. If it fails the data check, so
  that the state is not `idle` or `done`, **or** the unretrieved-data flag is
  `set`, stop. A power-cycle would lose
  that data, so you decide then whether it matters.
- **In case A, while no reply has given a state line,** there is none to look
  at: power-cycle before the next framing, as before.
- **A framing that is answered** needs no power-cycle. Its own state line is
  then the latest.

**Listen as well.** Page 79 says the LabPro beeps when its base code finds an
error in a command from the host. A beep after a framing is evidence about it;
write it down beside the trace's name.

**If no framing is answered in case A,** stop there. Keep the four traces and
your notes, and send them to the lead. The next step is decided from them.

**Every later run** uses the framing that was answered, with `--form`. If more
than one was answered, use `s-cr`, the manual's. In the commands below, put
that framing, such as `s-cr`, where `FRAMING` stands.

### 3. The guarded reset, then CH1

1. Put the voltage probe on CH1, and its leads on the bench supply.
2. For each of a few known voltages inside the probe's range, spread across it:
   1. Set the supply, and read the voltage with a meter if you have one.
   2. Run, with the supply's setting after `--applied`, and the meter's reading
      after `--meter` if you used one:

          .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-ch1-1v00.trace --read-ch1 --form FRAMING --applied 1.00 --meter 0.998

      Each is a plain number of volts, such as `1.25` or `-0.5`: no unit, no
      exponent, at most 12 characters. For a negative one, write
      `--applied=-0.5`. The script writes both into the trace's note exactly as
      typed, so the voltage is in the trace and not only in its name. They are
      your record, not the LabPro's.
   3. Write the voltages down beside the trace's name, too.
3. **Command 1's order, at one of those voltages.** Page 31 writes Command 1
   with the channel first, but page 40 labels an example with the operation
   first. Two more runs, at the same known voltage, with the 0 to 5 V
   operation, so that the two orders send different bytes:

       .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-ch1-1v00-volt.trace --read-ch1 --form FRAMING --operation voltage --applied 1.00
       .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-ch1-1v00-volt-opfirst.trace --read-ch1 --form FRAMING --operation voltage --order operation-first --applied 1.00

   - **Expect, BELIEVED:** the order the unit takes draws no error, and the
     run reads a value. The other order names, as its channel, the number the
     0 to 5 V operation has, which page 31's list of channels does not hold, so
     it should draw an error. The script then refuses with `the error register
     is ... after Command 1`, and still writes the trace.
   - **The next run's reset clears that error** (page 30), and an error is
     BELIEVED to leave the unit idle. If the next run is refused for the unit's
     state, stop and send the lead the traces.
   - **If both orders draw no error, or both draw one,** the two runs cannot
     tell the orders apart. Their Command 9 values are then all there is to
     compare. Send the lead the traces.
4. **The reset goes only to a unit that is idle or done.** The script refuses a
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

### 6. The Quick Setup check (optional, and last)

Page 26 says pressing the Quick Setup button wipes the unit's stored data and
its setup, and page 45 says the system state's register adds the QuickSetup
flag if the last mode was QuickSetup. This step shows whether a press moves
that register. It is last, and ends with a power-cycle, because what a press
leaves the unit in is unknown until the bench. Skip it if anything above went
wrong.

1. **Before.** Run step 1's command, without `--descriptors`, so that it sends
   Command 7 and nothing else, into a trace of its own:

       .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-qs-before.trace --form FRAMING

   **Go on only if** this trace's own state line passes the data check (step 1,
   item 5): the state is `idle` or `done`, **and** the unretrieved-data flag is
   `clear`; and the reply's error register reads zero
   ([protocol/REFERENCE.md](../protocol/REFERENCE.md) says which value it is).
   **Otherwise stop, and do not press Quick Setup.** If the QuickSetup flag
   already reads set, a press cannot show it appear; go on only if you still
   want to see the register move.
2. **Press Quick Setup once.** Write down the beep. Page 79 gives a
   medium-medium beep if an auto-ID sensor is attached, and a high-high beep if
   none is.
3. **After.** Run the same command into a second trace:

       .venv/bin/python tools/bench/labpro_bench.py --out 2026-11-20-qs-after.trace --form FRAMING

   If it draws no reply, stop there and keep both traces, and still do item 4.
   That is safe: item 1's check passed before the press, and the press itself
   wipes the unit's stored data (page 26).
4. **Power-cycle the LabPro,** to leave it in a known state, as the safety
   section says.

**What the traces would hold, BELIEVED:** in the system-state register
[protocol/REFERENCE.md](../protocol/REFERENCE.md) names, a state's code with no
QuickSetup flag in the first trace, and the same code plus the flag in the
second. Other registers, such as the last run's setup, may change too.

**Not known until the bench:** whether the press alone sets the flag, or only a
run started after it, and what state it leaves the unit in. If the two traces
show the same state register, that is the finding.

## Keeping the evidence

**Send the lead the traces and your notes:**
- what was connected;
- the voltages, the supply's setting and any meter's reading, which are also
  in each CH1 trace's note;
- the state line of each run;
- the framings;
- the beeps, the Quick Setup press's included;
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
