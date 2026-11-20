# Phase 0 evidence map

Which of the facts in [protocol/labpro-facts.toml](../protocol/labpro-facts.toml)
each step of [phase0.md](phase0.md) can settle, and which none can reach. Facts
are named by key. A key's value is in the facts file, and is not repeated here.

**Two readers.**
- **The owner, before and at the bench:** what each step's trace is for.
- **The lead, after the bench:** which trace to read to move a fact to `bench`.

**A plan, not a result.** Every row below was made by reading code (READ):
`tools/bench/labpro_bench.py`, the bench page's code in `app/src/bench/`, and
the runbook. No LabPro has been connected. Whether a real unit answers as the
code expects is unknown until the bench. The map says what the traces would
hold, not what they do.

## The three words

- **settles:** if the step runs as the runbook writes it, its trace holds the
  bytes or header lines that show the fact true or false. The row names them
  and the code that writes them there. The `usb.` rows settle the true case
  only; see the limit below.
- **bears on:** the trace holds something consistent or inconsistent with the
  fact, but cannot settle it alone. The row says what is missing.
- **not reached:** no step's trace touches it. The row says why.

Rules for placing a row:
- A fact is placed once, under the earliest step that settles it, else the
  earliest that bears on it, else under Not reached. A later step may show it
  too; the row says so.
- Only the trace is evidence. The script's printed report and exit status are
  not.
- **Step 2 runs only when step 1's framing draws no reply.** Every row that
  reads a reply holds only once some framing is answered. Where step 2 supplies
  that reply, read its trace in place of step 1's.
- **Where reading a fact depends on another the bench has not settled,** the
  row names it, and is "bears on".

**One limit on the USB rows.** `bulk_pair` (`labpro_bench.py:206-238`) checks
the endpoints before the descriptors are read. A unit that fails the check
makes no transfer, so the script writes no trace (`labpro_bench.py:623`). So the
`usb.` rows settle the true case only. A false one leaves a refusal on the
screen, which is not evidence.

## What each step's trace is for

1. **Power up, then first contact.** The unit's own description of itself (the
   descriptor lines, from `--descriptors`) and one Command 7 reply, which also
   shows the state the unit arrived in. Most of the
   settled facts are here.
2. **Command 7 in each framing.** Which framing a unit answers, by comparing
   what was sent with whether anything came back. It runs only if step 1 is
   silent.
3. **The guarded reset, then CH1.** Commands 0, 1, 7 and 9, in one run for each
   known voltage. Whether the unit takes them, and what a value is.
4. **The battery drain.** The same Command 9 repeated over an hour. It shows a
   value drifting, and when each reply came. It places no fact: what it shows
   is also in step 3.
5. **The browser page.** Step 3's commands through WebUSB. It places no fact. It
   shows a fact again by a second route, and shows whether the two routes
   agree. Its trace has no descriptor lines, only the device's strings
   (`from_browser.py:146-153`).

## Placed under Step 1: Power up, then first contact

Each row: key, channels, word, then what in the trace shows it and where the code writes it.
`labpro_bench.py` is shortened to `bench.py`.

| Fact | Channels | Word | What the trace holds, and the code |
|---|---|---|---|
| `usb.vendor_id` | - | settles | `device` header line, the vendor field (bytes 8-9, low byte first); bench.py:255, header at :530 |
| `usb.product_id` | - | settles | `device` header line, the product field (bytes 10-11, low byte first); bench.py:255 |
| `usb.bulk_in_endpoints` | - | settles | `configuration` header line: the bulk endpoint descriptors with the direction bit set; bench.py:260 |
| `usb.bulk_out_endpoints` | - | settles | same line, the bulk descriptors with the direction bit clear; bench.py:260 |
| `usb.packet_size` | - | settles | same line, each endpoint's maximum packet size; the IN lines' byte counts agree (bench.py:285) |
| `usb.in_transfer_multiple` | - | settles | byte count of every `IN` line of Command 7's reply, the last included; bench.py:285 records each packet, :286 flags a short one |
| `command.request_system_status` | - | settles | an `OUT` line that sends the command's number with no parameters, in the framing used, and the `IN` lines that answer it as a list; bench.py:309, :285 |
| `command.open` | - | bears on | `OUT` starts with it and the reply is a braced list; but no framing leaves it off, so "must" is untested |
| `command.close` | - | bears on | as `command.open`, for the closing character |
| `command.prefix` | - | bears on | the `s-cr` framing is sent (bench.py:126-134); an answer shows it is accepted, not that it is needed. Settled by step 2 only if step 1 is silent (Q1) |
| `command.serial_terminator` | - | bears on | as `command.prefix`, for the carriage return |
| `reply.terminator` | - | settles | the `IN` line holding the end of Command 7's reply: the carriage return, then what follows it in that packet (zeros, or a line feed); bench.py:285, :290 (Q7) |
| `data.ascii_number_format` | - | settles | the reply's text: each value's sign, digits and exponent, as written in the `IN` bytes; checked at bench.py:157-161 after the packets are recorded |
| `status.register_count` | - | settles | the number of comma-separated values in Command 7's reply; bench.py:169-171 |
| `status.check_value` | - | settles | the constant at the place `status.check_value_position` names; bench.py:172-175 |
| `status.check_value_position` | - | settles | the same value, where it stands in the reply; bench.py:172-175 |
| `status.software_id_position` | - | bears on | `firmware` header line is the value at the place this fact names (bench.py:490, :530), in the form of a version; missing: the unit's version from any other source, to tell it is one |
| `status.error_position` | - | bears on | the value at the place this fact names reads zero in a healthy unit; missing: a unit in error, and other places may read zero too |
| `status.system_state_position` | - | bears on | the value at the place this fact names reads like an idle code; missing: a state change at that place, which no step makes (see suggestion 4) |
| `status.state_idle` | - | bears on | an idle unit's reply; depends on `status.system_state_position` being the place read |
| `status.state_armed` | - | bears on | the Command 7 reply holds the system state at the place `status.system_state_position` names, recorded before any step acts (bench.py:489) and decoded there (:179-189); it shows this code only if the unit arrives armed, which no step causes. Depends on `status.system_state_position` |
| `status.state_busy` | - | bears on | the Command 7 reply holds the system state at the place `status.system_state_position` names, recorded before any step acts (bench.py:489) and decoded there (:179-189); it shows this code only if the unit arrives busy, which no step causes. Depends on `status.system_state_position` |
| `status.state_done` | - | bears on | the Command 7 reply holds the system state at the place `status.system_state_position` names, recorded before any step acts (bench.py:489) and decoded there (:179-189); it shows this code only if the unit arrives done, which no step causes. Depends on `status.system_state_position` |
| `status.quicksetup_flag` | - | bears on | the Command 7 reply holds the system state at the place `status.system_state_position` names, recorded before any step acts (bench.py:489) and decoded there (:179-189); it shows this flag only if the unit arrives with the flag set, which no step causes. Depends on `status.system_state_position`, and on the state codes, since the flag's amount is what is left after a state's code |
| `status.unretrieved_data_flag` | - | bears on | the Command 7 reply holds the system state at the place `status.system_state_position` names, recorded before any step acts (bench.py:489) and decoded there (:179-189); it shows this flag only if the unit arrives with the flag set, which no step causes. Depends on `status.system_state_position`, and on the state codes, since the flag's amount is what is left after a state's code |

## Placed under Step 2: Command 7 in each framing

No fact is placed here. If step 1 is silent, these traces settle `command.prefix`
and `command.serial_terminator`, and Q1. A silent trace holds an `OUT` line and
no `IN` line, and that is itself the finding.

## Placed under Step 3: The guarded reset, then CH1

| Fact | Channels | Word | What the trace holds, and the code |
|---|---|---|---|
| `command.reset` | - | bears on | an `OUT` line for it (bench.py:384), then Command 7 reading idle; a unit already idle reads idle either way. Missing: a unit whose state a reset changes. Depends on `status.system_state_position` |
| `command.reset_reply` | - | settles | no `IN` line between that `OUT` and the next `OUT`: the script listens 300 ms and records anything that comes (bench.py:385, :316-323). Silence is shown only within that listen; a later reply would land after the next command |
| `command.channel_setup` | - | bears on | an `OUT` line (bench.py:390), then Command 7 with a zero error register (:392). Missing: any visible effect of the setup |
| `command.channel_setup_reply` | - | settles | no `IN` line after that `OUT` before the next `OUT`; bench.py:391, :316-323. Silence is shown only within that listen; a later reply would land after the next command |
| `command.request_channel_data` | - | bears on | each one `OUT` line and a reply of one value (bench.py:393, :352-358). What the value is, is Q4 |
| `command.separator` | - | bears on | commands with parameters are sent, and answered; no run changes the character, so only "accepted" is shown |
| `collection.sample_time_default` | - | bears on | the Command 7 reply after the reset holds the last run's sample time. Missing: a fact giving that value's place in the reply, which the facts file lacks, and that a reset leaves it at the default. Step 1's reply holds the same value before the reset, but cannot tell a default from one an earlier run set |
| `channel.ch1` | - | bears on | Commands 1 and 9 name channel 1 and draw a value; missing: the voltage applied at the port labelled CH1, which is in the owner's notes and the file's name, not in the trace |
| `channel.operation_auto_id` | - | bears on | the operation is sent and the next status shows no error (bench.py:390-392); missing: any sign that the unit identified a sensor |
| `channel_data.mode_retest` | - | bears on | an `OUT` line for Command 9 in the retest mode, and one value (bench.py:393); step 4 and step 5 repeat it. Missing: a sensor changed between the two modes |
| `channel_data.mode_stored` | - | bears on | Command 9 in the stored mode (bench.py:395), one value; read back to back, the two differ only if the input changes between them |

## Placed under Step 4: The battery drain

No fact is placed here. Its repeated Command 9 lines show `channel_data.mode_retest`
again, with a time on each line.

## Placed under Step 5: The browser page

No fact is placed here. Its trace shows steps 1 and 3 again, through WebUSB
(`session.ts:214-279`, `record.ts:61-71`). It has no descriptor lines, so it
shows no `usb.` descriptor fact.

## Not reached

| Fact | Channels | Word | Why no trace touches it |
|---|---|---|---|
| `ports.analog` | - | not reached | the count of sockets, seen by eye; no trace records it |
| `ports.digital` | - | not reached | seen by eye; no step uses a digital port |
| `adc.bits` | - | not reached | no step reads the converter's raw word; Command 9's value is text, and what it means is Q4 |
| `buffer.points` | - | not reached | no collection is run |
| `realtime.usb_max_rate` | - | not reached | no real-time collection is run (Q6) |
| `realtime.serial_max_rate` | `1` | not reached | the serial port; no step uses it |
| `realtime.serial_max_rate` | `2 - 4` | not reached | the serial port |
| `realtime.serial_max_rate` | `4 - 6` | not reached | the serial port |
| `non_realtime.max_rate` | `1` | not reached | non-real-time collection is not run |
| `non_realtime.max_rate` | `2` | not reached | non-real-time collection is not run |
| `non_realtime.max_rate` | `3 - 4` | not reached | non-real-time collection is not run |
| `non_realtime.max_rate` | `5` | not reached | non-real-time collection is not run |
| `non_realtime.max_rate` | `6` | not reached | non-real-time collection is not run |
| `power.supply` | - | not reached | heard and seen at power-up, not recorded; a limit no step tests |
| `power.jack` | - | not reached | a fit by eye; no trace |
| `sensor_supply.volts` | - | not reached | needs a meter on the sensor socket; no step uses one |
| `sensor_supply.max_current` | - | not reached | a limit no step comes near |
| `command.data_collection_setup` | - | not reached | no step sends Command 3 |
| `command.conversion_equation_setup` | - | not reached | no step sends Command 4 |
| `data.get_request` | - | not reached | no step collects data, so `data.get_request` is never sent |
| `data.binary_mode_command` | - | not reached | no step sends it (Q3) |
| `data.binary_packing_max` | - | not reached | binary mode is not run |
| `data.binary_sample_bits` | - | not reached | binary mode is not run |
| `data.byte_order` | - | not reached | binary mode is not run |
| `data.realtime_time_counter_bits` | - | not reached | no real-time collection is run |
| `data.checksum` | - | not reached | it concerns binary records, which are not collected |
| `status.state_self_test` | - | not reached | every Command 7 reply holds the system state, at the place `status.system_state_position` names; but the self-test runs at power-up, before the cable is connected, so a reply could show its code only by chance |
| `status.state_initializing` | - | not reached | every Command 7 reply holds the system state, at the place `status.system_state_position` names; but the steps wait for the beeps, so a reply could show its code only by chance at start-up |
| `collection.max_points` | - | not reached | no step sends Command 3 |
| `collection.realtime_points` | - | not reached | no step sends Command 3 |
| `collection.sample_time_min` | - | not reached | no step sends Command 3 |
| `collection.sample_time_max` | - | not reached | no step sends Command 3 |
| `channel.operation_voltage_0_5` | - | not reached | the script sends the auto-ID operation only (bench.py:390) |

## The seven questions

From [protocol/REFERENCE.md](../protocol/REFERENCE.md), "What Phase 0 has to settle".

| Question | Word | Step | What the traces hold, and what is missing |
|---|---|---|---|
| Q1 | bears on | 1, 2 | step 1 sends `s-cr` only. An answer shows it works, not that each part is needed. If step 1 is silent, step 2's traces settle it |
| Q2 | bears on | 1 | the bytes and how they sit in packets are settled (`IN` lines, bench.py:285). The unit's software ID rests on `status.software_id_position`, which is bears on |
| Q3 | not reached | - | no step sends the binary-mode command or collects data |
| Q4 | bears on | 3 | the value's text is in each `IN` line. The voltage applied is not in the trace, only in the owner's notes and the file's name |
| Q5 | not reached | - | step 3 sends `channel.ch1` with `channel.operation_auto_id`, whose values in the facts file are equal, so the bytes are the same in either order |
| Q6 | not reached | - | no step collects in real time. Step 4's Command 9 is one request for each reply, not the real-time path |
| Q7 | settles | 1, 3 | the bytes after the carriage return in the reply's last packet. If the carriage return ends a packet, step 1 does not read on; step 3's replies do (bench.py:357) |

## Suggestions, for the owner's call

Each is a small addition to a step. None is made here.

1. **Q5 and `channel.operation_voltage_0_5`:** in step 3, also send `channel.ch1` with the operation `channel.operation_voltage_0_5` names, which needs a small option in the script, so that the two orders send different bytes.
2. **Q1, `command.prefix`, `command.serial_terminator`:** after step 1 is answered, run each other framing once, but only while step 1's Command 7 shows no data not yet retrieved, since a power-cycle after a silent framing clears held data.
3. **Q4, `channel.ch1`:** write the applied voltage into each CH1 trace as its note, so the evidence does not rest on a file name; it needs a small option in the script.
4. **`status.system_state_position`, `status.quicksetup_flag`, `status.state_idle`:** after step 1's Command 7 shows no data held, press Quick Setup once and run step 1's Command 7 alone, and the place that moves by the flag's amount is the state's.

## The limits

- **No gate holds this map to the facts file.** A fact added or renamed later is
  missing from the map until someone updates it. The scratch script that checked
  it is not committed.
- **The map is read from code, not measured.** A row that says "settles" says
  what the code would write, if the unit answers as the manual says.
- **A trace holds bulk transfers and a few header lines.** The owner's notes,
  the beeps and the lights are not in it.

Its licence is the one the folder table in [README.md](../README.md) gives it.
