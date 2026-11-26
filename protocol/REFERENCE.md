# The LabPro protocol, as far as Phase 0 needs it

**Source.** Vernier's LabPro Technical Reference Manual, revision 08/02/02. This
page was written from it before any LabPro had been connected, and it stays the
manual's account. The first bench session, on 2026-11-25, answered some of the
questions the manual leaves. Those answers are in the last section and under
"Channel and operation swapped", each linking the recordings in
[traces/](traces/FORMAT.md) that show it. Which facts a recording shows is in
the facts file's statuses.

**Pages.** Each section cites the manual's pages. The values Phase 0's code
uses are also facts in [labpro-facts.toml](labpro-facts.toml), where the gate
finds each one's wording on its page. Where this page and the facts file
disagree, trust the facts file: this page has a defect.

**Own words.** This page restates the manual in this project's own words. Where
the manual is present, the gate fails a file that shares eight or more words in
a row with it, and [the gate's docstring](../tools/check.py) lists what that
check cannot catch. A close paraphrase is a verifier's call, not the gate's. The
lists below keep the manual's order, so that they can be held against its pages.

## First contact: look before resetting

Pages 6, 7 and 30.

- **Command 7 first.** The manual's advice is to find a LabPro by asking for its
  status with Command 7 alone. A unit may still hold data from an earlier
  experiment, and a reset would destroy it.
- **What reset clears.** Command 0 resets the LabPro. It clears what is held in
  RAM: collected data, error state, channel setup and collection setup. Its
  flash memory is untouched, and it sends no reply.
- **When to reset.** The manual suggests a reset as the usual way to begin
  configuring channels. It should only be sent once the user is done with
  whatever the unit held.
- **Seeing unsent data.** Command 7's reply shows whether a unit holds data
  nobody has collected (register 14, below).

## Talking to a LabPro

- **The form of a command.** A command is its number inside curly braces,
  followed by its parameters, with commas between them (page 29). Written for a
  computer host, it carries a leading `s`: `s{7}` (page 22) and `s{1,2,14,0}`
  (page 32) are the manual's own examples.
- **The end of a command.** On the serial port, a carriage return ends every
  command (page 22).
  - The manual says USB works much like the serial port, in ASCII, but never
    shows a USB exchange byte for byte.
  - Whether USB wants the `s` and the carriage return was the first thing the
    bench had to answer. Question 1, in the last section, gives the answer.
- **What comes back.** The LabPro answers commands in ASCII text, and sends
  collected data as ASCII or binary, whichever the host chose (pages 21 and 22).
  - In ASCII, a number has the form `sm.dddddEsee`: a sign, a digit, five
    decimals, then an exponent with its sign (page 21).
  - A reply holding several values puts them in braces, separated by commas, as
    Command 7's example on page 46 shows.
- **Waking from sleep.** On batteries, a unit in its low-power state misses the
  first byte sent over the serial port. The manual suggests sending `s` and a
  carriage return first to wake it (page 22). Whether USB has the same habit is
  unknown.

## USB, as the manual describes it

Pages 22 to 24.

- **The device.** It identifies as vendor `0x08F7`, product `0x0001`, with one
  bulk endpoint in each direction and 64-byte packets.
- **Packet boundaries.** Everything the LabPro sends arrives in whole 64-byte
  packets, so the last packet of a reply can carry bytes past its end. A reader
  stops at the carriage return of an ASCII reply. For binary data it stops
  after the byte count that the samples it asked for imply.
- **Blocking reads.** A read waits until the LabPro has something to send,
  because the device answers with a NAK (Not Acknowledge) until then. A host
  that must stay responsive reads on a thread of its own.
- **No checksum.** USB carries no checksum byte; the serial port's checksum
  does not apply.
- **Real-time binary rate.**
  - In real-time binary mode, each sample's record is padded with zeros to
    sixteen bytes (page 23), and page 24 says the bytes sent back are always
    sixteen.
  - By default each sample travels in a packet of its own, which the manual
    reckons at about one sample a millisecond.
  - A fourth parameter on the binary-mode command packs up to four samples per
    packet (`{4,0,-1,X}` with X from 1 to 4).
  - When the host is slow to collect packets, samples go missing in runs.

## Command 7: the system status

Pages 45 and 46. The reply holds seventeen registers, in this order:

1. the software ID, written `X.MMmms`: product code, major and minor number,
   step;
2. an error code, non-zero after a fault, which calls for a reset once the
   cause is fixed;
3. battery state: 0 good, 1 low while sampling, 2 low all the time;
4. a constant, 8888. The manual's use for it is conditional: if the host set
   that place in its list to zero before asking, finding 8888 there shows the
   status arrived correctly.
5. to 9. the last run's sample time, trigger condition, trigger channel,
   post-processing and filter, as the host commanded them;
10. the last run's sample count, or the count actually taken if the run was
    stopped early;
11. how time was recorded in the last run: 0 not at all, 1 absolute, 2
    relative;
12. the temperature used to correct a sonic sensor in the last run;
13. whether sound is on (1) or off (0);
14. the system state: idle (1), armed (2), busy (3), done (4), self-test (5) or
    starting up (99). Add 16 if the last run used QuickSetup, and 32 if its
    data has not been collected yet;
15. and 16. the first and last data points ready to send, unless Command 5 has
    narrowed them;
17. the system ID set with Command 6.

**For this project:**
- **Register 1** is what a trace's `firmware` line records.
- **The 32 in register 14** is how a host can see unsent data before choosing to
  reset.
- **Page 46's example** shows a reply as seventeen numbers in braces, beginning
  `{ +6.01120E+00, ...`.

## Command 1: channel setup

Pages 31 and 32. The syntax is
`{1, channel[, operation[, post-processing, delta, equation]]}`.

- **Channels:**
  - 0 means all of them;
  - 1 to 4 are the analog ports;
  - 11 and 12 the DIG/SONIC ports;
  - 21 and 22 the digital inputs;
  - 31 and 32 the digital outputs.
- **Operations for an analog channel:**
  - 0 turns it off;
  - 1 identifies the sensor (falling back to 0 to 5 V when none answers);
  - 2 reads plus or minus 10 V;
  - 3 reads current;
  - 4 reads resistance;
  - 5, 6 and 7 measure period, frequency and transition count, on channel 1
    only;
  - 10 and 11 read TI temperature probes in Celsius and Fahrenheit;
  - 12 reads the TI light sensor;
  - 14 reads 0 to 5 V.
- **Post-processing** can add a first derivative (1) or first and second
  derivatives (2), but only for non-real-time runs, as real-time data is not
  stored.
- **Delta** is for Vernier's own debugging and is always 0.
- **Equation** set to 1 applies the conversion chosen with Command 4.
- **Reply:** none. `s{1,0}` clears every channel, and `s{1,2,14,0}` sets channel
  2 to 0 to 5 V.

## Command 3: data collection setup

Pages 35 and 36. The syntax is
`{3, sample time[, points, trigger type, trigger channel, threshold, pre-store, external clock, time recording, filter[, fast mode]]}`.

- **Sample time** runs from 0.00002 to 16,000 seconds, with 0.5 by default.
  - A value of -1 repeats the previous run.
  - The smallest value, 20 microseconds, is fast mode's fastest (page 36).
    Outside fast mode, each kind of probe has a longer minimum, tabled on page
    35.
- **Points** per channel run from 1 to 12,287, and -1 selects real-time
  collection. See the section on disagreements.
- **Trigger type:**
  - 0 starts at once;
  - 1 waits for the start button (the default);
  - 2 to 5 wait for combinations of rising and falling edges;
  - 6 takes a single sample.

  Several pairings are refused; the table on page 35 lists them.
- **Trigger channel** is 0 for none, 1 for a hardware trigger on channel 1, 2 to
  4 for a software trigger on those channels, and 11 or 12 for the DIG/SONIC
  ports.
- **The threshold** is a number in the trigger channel's own range.
- **Pre-store** is the percentage of points to keep from before the trigger.
- **External clock** is for Vernier's own debugging and is always 0.
- **Time recording:** 0 records no time; 1 times each point from the start of
  collection; 2 times it from the point before it.
- **Filters:**
  - 1 to 4: Savitzky-Golay smoothing over 5, 9, 17 or 29 points;
  - 5 and 6: median pruning over 3 or 5 points;
  - 7 to 9: real-time tracking filters of three strengths;
  - 0: none.
- **Fast mode** (1) samples one analog channel only, between 5,000 and 50,000
  samples a second.
- **Reply:** none. `s{3,0.5,-1}` starts a real-time run at two samples a
  second.

## Command 4: conversion equations, and binary mode

Pages 21, 39 and 40.

- **The usual job.** Command 4 tells a channel how to turn its raw reading into
  units: polynomials, powers, logarithms, exponentials, Steinhart-Hart, and an
  ambient-temperature setting for the sonic channels.
- **Binary mode.** Sent as `{4,0,-1}` (channel 0, equation type -1), it makes
  the LabPro send binary samples instead of ASCII, and only for active analog
  and motion channels. The samples are the raw converter output: calibration
  equations and derivatives are not applied.
- **The binary sample format:**
  - Each sample is a 16-bit word, most significant byte first, with no line
    ending after it.
  - On a LabPro its top twelve bits hold the reading and its bottom four are
    zero. On a CBL 2, ten bits hold the reading and six are zero.
- **A real-time record.** It holds one word for each active channel, lowest
  channel first, then a 32-bit time counter. On the serial port only, it ends
  with a checksum byte: all the record's bytes combined by exclusive-or, then
  inverted.
- **Non-real-time data.** Each `g` returns every point of one channel. The next
  `g` moves on to the next channel (pages 21 and 22).
- **The manual's whole binary run.** Example 2 on page 40 sends a reset, a
  channel setup, `{4,0,-1}`, a setup for 500 samples at 50,000 a second, and `g`.
  Its channel setup line contradicts Command 1's syntax; see the section on
  disagreements.

## Command 9: one reading before a run

Page 48. `{9, channel, mode}`, for channels 1 to 4, 11 or 12, returns one value.
The manual describes it as a check that the setup is right before sampling
starts.

- **Mode 0** tests the channel's sensor identification again.
- **Mode 1** uses the identification stored from the last run, so a sensor can
  be unplugged afterwards.

Its example shows replies such as `{ +1.94383E+00 }`.

## Getting data

Pages 7, 21 and 22.

- **Real time.** Each sample is sent as it is taken. Over USB the LabPro sends a
  sample when the host asks for it, and samples the host does not ask for in
  time are lost. Over the serial port it streams without being asked.
- **Non-real time.** Samples are stored in the LabPro, which sends them only
  after the host's `g`. A `g` sent before collection has finished is answered
  once the last sample is taken.

## Where the manual disagrees with itself

Each is a question for the bench, not something to code around.

- **The point limit.**
  - Command 3 accepts 1 to 12,287 points (page 35).
  - Pages 12, 27, 51, 59 and 81 write 12,000.
  - Pages 24, 74, 82 and 83 write 12k.
- **The checksum example** on page 21 (lead's working, 2026-11-15):
  - The text names 93H as the checksum of its sample record.
  - The bit pattern printed beneath it ends in 1101 0111, which is D7H.
  - Applying the stated rule to that pattern's six data bytes gives D7H as well.
  - This touches only the serial port.
- **The serial real-time limits on page 23** name four channels in two rows. The
  facts file's note on `realtime.serial_max_rate` works the page's own
  arithmetic through.
- **Binary or hexadecimal.**
  - Page 21 heads its section Hex Data, then calls the mode binary.
  - Pages 22 and 23 say binary.
  - Pages 39 and 40 say hexadecimal.
- **One run, two commands, and a reply that disagrees with the prose.**
  - Page 36 writes Command 3 for a 10-second, 61-point run with a 9-point filter
    as ten numbers. Page 46 writes it as nine.
  - Page 46's own status reply then shows that run with filter 0 and time
    recording 2, which fits the shorter command. Its prose says the filter was
    applied.
- **Channel and operation swapped.**
  - Page 40 labels `s{1,14,1}` as setting channel 1 to 0 to 5 V, with the
    operation first. Page 47 shows the same command without a label.
  - Command 1's syntax (page 31) and the examples on pages 22, 43, 50 and 52
    to 55 put the channel first, as `s{1,1,14}`; pages 43, 50 and 52 add
    trailing zeros.
  - **The bench's answer: channel first.** On 2026-11-25 the unit took
    `s{1,1,14}` with error 0 ([ch1-volt](traces/2026-11-25-ch1-volt.trace)),
    and `s{1,14,1}` drew error 12
    ([ch1-volt-opfirst](traces/2026-11-25-ch1-volt-opfirst.trace)). The
    manual's table of error codes gives 12 for a channel that does not exist
    (the PDF's page 80, printed B-2).
- **A copied column.** In Example 2 on page 40, the calculator column repeats
  Example 1's commands beside a different sequence.
- **Sixteen bits or sixteen bytes.** Page 23 says a real-time sample comes back
  as 16 bits, then that it is padded with zeros to 16 bytes, and page 24 says
  16 bytes. This page reads the bits as one channel's reading and the bytes as
  the padded record; the bench decides.

## What Phase 0 has to settle

The first bench session, on 2026-11-25, answered four of these. Each answer
rests on that one session, with one unit and one host: Windows 11 with libusb
1.0.30, and Chrome 158 for the browser's recording, whose header gives the
version Chrome reports for that computer, `Windows 15.0.0`. Every command in it
was framed with the `s` and a carriage return, except in question 1's tests.

1. Whether a USB command needs the leading `s`, the closing carriage return, or
   both.
   - **Both, for Command 7.** `s{7}` and a carriage return drew the reply
     ([first-contact](traces/2026-11-25-first-contact.trace)). `s{7}` alone
     ([form-s](traces/2026-11-25-form-s.trace)), `{7}` and a carriage return
     ([form-cr](traces/2026-11-25-form-cr.trace)), and `{7}` alone
     ([form-bare](traces/2026-11-25-form-bare.trace)) each drew nothing within
     the bench script's 2000 ms.
2. The bytes Command 7 returns over USB, including how its reply sits in 64-byte
   packets, and the unit's software ID.
   - **Seventeen values in braces, then a carriage return and a line feed:**
     `{  +6.06270E+00, +0.00000E+00, … +0.00000E+00 }`. They came in four 64-byte
     packets, the last padded with zero bytes after the line feed
     ([first-contact](traces/2026-11-25-first-contact.trace)). Place 1, the
     software ID by page 45's row order, held `+6.06270E+00` in all 41 replies
     to Command 7.
     The device descriptor's bcdDevice, 0x061B, fits its 06 and 27 (INFERRED).
3. Whether binary-mode samples arrive as raw bytes or as hexadecimal text.
   - **Not reached.** No command of the session asked for binary mode.
4. What Command 9's value is. Page 48 calls it the sensor's current value; the
   bench settles whether that is a reading in the sensor's units or a raw
   voltage, with known voltages from a bench supply.
   - **Not settled.** The owner's probe, which the owner believes is a voltage
     probe, was on the port the owner names as CH1, and Command 1 set it up
     with operation 1. What the probe was put on, and when its contact held or
     slipped, are the owner's account; the recordings hold only the readings.
     CH1 read:
     - about -0.02 with the probe's clips together, at 0 V
       ([ch1-0v](traces/2026-11-25-ch1-0v.trace));
     - +1.585 to +1.595 while the contact held on an AA cell. In the same
       recording, readings near 0, and one of +1.238, came when it slipped
       ([ch1-aa-2](traces/2026-11-25-ch1-aa-2.trace));
     - +9.297 to +9.316 on a 9 V battery
       ([ch1-9v](traces/2026-11-25-ch1-9v.trace)).

     Those are near the cells' nominal voltages, but neither cell was metered.
     A sensor that reads in other units, and a metered source, are still
     needed.
5. Which order of channel and operation Command 1 takes.
   - **Channel first.** `s{1,1,14}` drew error 0
     ([ch1-volt](traces/2026-11-25-ch1-volt.trace)), and `s{1,14,1}` drew error
     12 ([ch1-volt-opfirst](traces/2026-11-25-ch1-volt-opfirst.trace)), which
     the manual's table of error codes gives for a channel that does not exist
     (the PDF's page 80, printed B-2).
6. How fast real-time samples arrive over USB on the hosts that matter.
   - **Not reached.** No real-time run was started.
7. How a reply ends: whether a line feed follows its carriage return.
   - **Yes.** Every reply of the session, 71 of 71, ended with `}`, a carriage
     return and a line feed
     ([first-contact](traces/2026-11-25-first-contact.trace) and the rest).

Licence: the folder table in [the README](../README.md) gives this file's
licence.
