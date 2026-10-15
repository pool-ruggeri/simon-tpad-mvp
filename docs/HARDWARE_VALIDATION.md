# Manual hardware validation

Software tests and PsychoPy display smoke checks pass. In the M3 instructions,
the PO reports repeated successful Simon sessions, four-button serial acquisition,
hardware RT checks, a 10/10 optical diagnostic, and BioSemi TTL activity visible
in ActiView. These reports were not independently repeated during publication.
Saved-BDF event/timing validation and the OpenBCI branch remain pending. The
reference firmware is `20250809`, with FTDI latency 1 ms; use the actual local COM
port rather than assuming the reference PC's COM5. See
[INSTALL_ON_NEW_PC.md](INSTALL_ON_NEW_PC.md) for configuration and prerequisites.

## Behavioral acceptance without EEG

1. Connect the T-Pad serial USB lead and Opto 1. Close the BBTK utility, serial
   terminals, and every other COM5 owner. Leave firmware, sensitivity, FTDI
   settings, drivers, and Windows settings unchanged. BioSemi/OpenBCI can remain
   disconnected.
2. Run the tests and windowed task from PowerShell in the project:

   ```powershell
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
   .\.venv\Scripts\python.exe run_simon.py --windowed
   ```

3. Position Opto 1 over the dedicated lower-left square. The square must be
   black during instructions, fixation, response-only time, and black intervals.
   Press Space/Return on the PC keyboard. Confirm setup observes firmware
   `20250809`, receives `MODE 5:`, and leaves the device LED flashing green.
   Setup sends only `X`, `FIRM`, `MOD5`; subsequent black intervals query `T`.
4. Start practice with the PC keyboard. Respond to blue with Button 1 and yellow
   with Button 2, regardless of position. Press very early on at least one trial:
   the colored stimulus and white marker must still persist for their full
   programmed duration. Releases must also appear in `events.csv`.
5. Run all 16 experimental trials. Intentionally omit a response, use the wrong
   valid button once, press Button 3/4 once, press before stimulus once, and press
   well after the 1500 ms window once. Use obvious margins; human action alone
   cannot verify a 1 ms deadline boundary. A held button must not create a new
   response on the next trial without another press.
6. Close the final screen using Space/Return. Locate the printed session directory.
   Confirm exactly four output files, 20 attempted/completed trials, all four
   color/side combinations balanced separately in each block, and mode/firmware
   confirmation in `session.json`. Verify clean trials have one Opto 1 ON/OFF pair
   and plausible ~500 ms optical duration. Investigate every invalid trial.
7. For eligible responses, manually subtract `opto_onset_tpad_ms` from
   `button_press_tpad_ms` and compare to integer `rt_ms`. Wrong Button 1/2 responses
   should have accuracy 0. Valid omissions should have empty response/RT and
   accuracy 0. Buttons 3/4, anticipatory presses, and late presses must remain in
   events/raw data while being excluded from eligible responses.
8. Verify timer samples around trials are integers, increase without resets, and
   arrive in an intelligible stream with the XiD events. The upper sample must
   cover `response_deadline_tpad_ms`. Save the raw logs as evidence for timer
   reply formatting and ordering with this firmware. Timeout/order/backlog flags
   must be resolved before acceptance; never hide them by using host flip times.
9. Repeat in full screen (`.\.venv\Scripts\python.exe run_simon.py`) after moving
   the sensor to the full-screen marker. Confirm no `dropped_visual_frame` flags.
   Software host flips alone do not measure physical luminance onset.

## Missing optics and recovery

Run a separate clearly labelled validation session with Opto 1 covered or removed
from the marker. Stimuli must retain their programmed duration. Trials must be
invalid with missing optical onset/offset and empty RT. Restore the sensor without
changing settings and confirm later trials associate to their own hardware
boundaries rather than inheriting an earlier missing onset.

In separate runs press Escape during a stimulus, and disconnect only the serial
USB cable after collecting at least one trial. The window should close, the port
should be released, and all four files should retain prior data. The interrupted
trial must be incomplete/invalid and contain no invented RT. Escaping may shorten
the active stimulus because it is an emergency abort; behavioral responses never
do. Do not reconnect automatically within the same scientific session.

Raw records include all received bytes and partial lines. Trial summaries are
saved again at shutdown. Confirm `status=aborted` for Escape and `status=error`
with a reason for disconnection. Keep these sessions separate from participant
data. Hardware-generated TTL can still occur in Mode 5 after the application
closes because shutdown does not reconfigure the pad.

## Separate physical and EEG qualification

Use independent measurement to establish the scanout difference between the
lower-left marker and each stimulus position. A common software flip does not
establish identical physical onsets. Check white/black transitions, optical
offsets, and the effects of the device's existing filtering/debounce settings.
Do not apply extra correction to firmware timestamps without measured evidence.

Before connecting EEG, a qualified hardware operator must verify the actual
adapter, pinout, voltage levels, ground, polarity, and acquisition-system input
requirements against both manufacturers' documentation. RJ45 here carries TTL;
it is not an Ethernet connection. Never assume a network cable is a qualified
BioSemi or OpenBCI interface.

Then measure automatic outputs for button presses/releases and optical ON/OFF,
including durations and simultaneous-line behavior, and confirm the same events
in recorded EEG. These outputs represent physical inputs/sensor transitions;
they do not by themselves encode blue/yellow, congruency, or arbitrary trial IDs.
The application must not recreate those physical markers with software TTL
commands. Deriving condition labels requires a separately approved offline
alignment or hardware design.

## Acceptance record

Record operator, date, session IDs, software commit, firmware observed, display
geometry/refresh, raw-log examples, invalid-trial explanations, and measured
timing results. State behavioral acceptance and EEG/electrical qualification as
separate outcomes. Preserve the PO-reported observations above and distinguish
them from documented saved-file/electrical qualification; the latter remains pending.

Reference: [official T-Pad guide](https://www.blackboxtoolkit.com/docs/pdf/TPadv1r1.pdf).
