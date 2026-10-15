# Simon–TPad MVP

A small Windows PsychoPy Simon task with Black Box Toolkit T-Pad v1 serial
responses. Blue maps to Button 1 / left; yellow maps to Button 2 / right.
There are 4 practice and 16 experimental trials, balanced over color and side.
The seed, trial order, software revision, and acquisition settings are saved.

The local implementation and synthetic tests pass. The display smoke test passes.
Real T-Pad behavior, physical optical timing, and EEG triggers still require the
manual procedure in [docs/HARDWARE_VALIDATION.md](docs/HARDWARE_VALIDATION.md).

## Run on this PC

Open PowerShell in the repository and run:

```powershell
Set-Location 'C:\Users\pruggeri\Documents\EXPERIMENTS\GABRIEL_PAOLO'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run_simon.py --gui-smoke
.\.venv\Scripts\python.exe run_simon.py --windowed
```

The smoke test displays a blue stimulus and marker, then closes automatically;
it does not open a serial port or produce behavioral results. Use the windowed
experiment for initial operator checks and position Opto 1 over its marker.
For subsequent full-screen validation:

```powershell
.\.venv\Scripts\python.exe run_simon.py
```

Close the BBTK utility and other COM5 applications first. Space or Return advances
instructions and starts each block. Escape exits and saves collected data.
During trials use only T-Pad Buttons 1 and 2. Buttons 3 and 4 are recorded but do
not count as Simon responses. The T-Pad keyboard HID interface is not used.

## Standalone optical calibration patch (M2)

```powershell
.\.venv\Scripts\python.exe calibrate_opto.py
```

The utility matches the Simon marker's `rgb` black `(-1, -1, -1)` and white
`(1, 1, 1)`, pyglet backend, and synchronized flips. It reads display size/index
from `config.json` and keeps its window visible when BBTK has keyboard focus.

Only default `testMonitor` profiles were found on this PC; their dimensions are
not accepted as a physical calibration. First use a ruler and Left/Right to make
the displayed reference square **4 cm on both sides**, measuring between border
line centers; Return confirms the scale for this run. Then click below the
instructions to create the black patch, or click again to reposition it. Border
clicks are clamped so the whole patch remains inside the window and away from
instructions. Keep the sensor inside the patch, away from its external outline.

Each **SPACE press toggles black → white → black**, as often as needed. The patch
starts black and holds its selected color until the next press; there is no timer
or automatic sequence. Click again to reposition it at any time. Focus the patch
window for SPACE or ESC; ESC closes. The selected color stays visible while BBTK
has focus. Text and cursor stay outside the sensor area.

If the physical scale is already measured, specify drawing pixels per centimeter:

```powershell
.\.venv\Scripts\python.exe calibrate_opto.py --pixels-per-cm 40
```

**40 is an example, not a measurement of this monitor.** An unambiguous calibrated
PsychoPy profile matching the display can supply geometry; `--monitor NAME`
selects a profile. Ambiguous/default profiles or high-DPI scaling require a ruler
or measured px/cm. Check both physical sides again after moving monitors or
changing scaling/resolution. Scale is not saved globally; pixel rounding limits
size precision.

To use BBTK, stop the Simon Task and other COM5 owners, then connect to COM5 in
the official BBTK Configuration & Test application. **The serial port must be
available to BBTK.** This patch utility never opens it or sends device commands.
For an independently controlled patch, follow the external-patch sensitivity
procedure in [section 5 of the T-Pad guide](https://www.blackboxtoolkit.com/docs/pdf/TPadv1r1.pdf):
use BBTK's “Adj. To Another Device” workflow and acknowledge prompts during the
matching patch colors. Focus the patch window and press SPACE when a color change
is needed, then return to BBTK. There is no handshake or confirmation of sensor
calibration from this utility.
BBTK's same-PC automatic routine controls its own patch. All sensitivity changes
are made by the operator in BBTK. Close/disconnect BBTK before a Simon session.

Manual transitions use the draw/flip loop, with no sleeps. Refresh/compositor
timing limits physical precision. No serial connection,
tPAD mode/timer/TTL changes, or Simon launch occur in this utility.

For an automatically closing GUI smoke check (synthetic size, no sensor calibration):

```powershell
.\.venv\Scripts\python.exe tests\smoke_calibrate_opto.py
```

## Opto timing diagnostic (M2B)

After calibration, close the calibration patch and disconnect/close BBTK so COM5
is free. Run:

```powershell
.\.venv\Scripts\python.exe opto_diagnostic.py
```

Place Opto 1 inside the outlined preview of the marker. Space starts ten cycles
of **500 ms white, then 500 ms black**, then shows results with the marker black.
Space repeats; Escape saves and exits. Only the optical square changes color:
there are no colored stimuli, fixation crosses, response windows, or required
button responses. The default marker is the same 80 px lower-left square used
by Simon, rather than M2's 4 cm patch. Display settings come from `config.json`.
Timer queries and saving can extend black intervals; they never end a white pulse.
An extra black drain interval after the last pulse collects delayed serial data.

```powershell
.\.venv\Scripts\python.exe opto_diagnostic.py --port COM5 --windowed
.\.venv\Scripts\python.exe opto_diagnostic.py --short-pulse-ms 10
```

The existing serial reader uses timeout-zero acquisition, verifies firmware,
and enters Mode 5 once. Repeats keep the same connection and clock. Only setup
and read-only timer-query commands are sent; there are no software TTL commands
or T-Pad HID input. Live statistics and the current ON/OFF state stay outside the
marker. The long panel is cached while white; numeric layout is compact and
refreshed at most four times per second during black, with a separate live state
label. No event controls the visual schedule.

Outputs go to `output/opto_diagnostics/<unique_session_id>/`: `serial_raw.jsonl`,
`optical_events.csv`, `pulses.csv`, and `summary.json`. Repeats have separate run
numbers in the same launch's files. Raw bytes, duplicate edges, unpaired events,
and extra activations remain auditable. Summaries are checkpointed between
presentations and saved again on Escape/error; disk/power failures remain outside
that guarantee. Scientific durations and intervals use hardware milliseconds only.

Pulses at or below the saved short threshold (default **10 ms**, including the
reported 1–2 ms activations) are counted separately. Full optical pairs need not
be exactly 500 ms: 503–506 ms pairs are complete, with the difference from nominal
recorded. Durations summarize all complete non-short pairs inside each run's
hardware boundaries. Onset intervals use only adjacent scheduled presentations
with unique complete matches, skipping gaps/ambiguity. Standard deviations use
the population definition. Multiple candidate pulses, orphan edges, crossed
boundaries, or arrival beyond grace prevent a confident scheduled match; no nth
event pairing or host/hardware clock subtraction is used. A completed pair is
not a hardware acceptance result. Review presentation warnings and raw data.

For a real PsychoPy display smoke with **synthetic serial events**, no device:

```powershell
.\.venv\Scripts\python.exe tests\smoke_opto_diagnostic.py
```

Next perform a real device run and retain the output folder. Verify ten unique
full pulses, investigate missing/ambiguous/unpaired/short events and frame
warnings, and confirm sensor positioning/scanout timing before Simon acceptance.
Actual T-Pad detection and electrical/recorded EEG TTL remain separately unverified.

## Recreate the isolated environment

Verified interpreter: 64-bit CPython 3.11.9. PsychoPy 2026.2.4 supports Python
3.11 according to the [official installation documentation](https://psychopy.org/download.html).
The existing user-installed PsychoPy 2023.1.3 was inspected but left unchanged.

On a fresh copy of the project:

```powershell
py -0p
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-cache-dir -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Activation is unnecessary. Always invoke the explicit `.venv` interpreter.
`requirements.txt` pins the two direct dependencies, PsychoPy 2026.2.4 and
pyserial 3.5. `requirements-lock.txt` pins all installed runtime dependencies
from the verified Windows environment. Other platforms need separate installation
qualification. PsychoPy brings its own dependencies; this application adds only
pyserial and uses the standard library for testing and output.

PsychoPy preferences and caches go under `.cache` in this project. The launcher
redirects APPDATA for its own process before PsychoPy import and disables
PsychoPy's extra package search paths. Windows settings and the existing
PsychoPy preferences/installations are not modified.

## Configuration

Edit `config.json`, or keep machine-specific overrides in ignored
`local_config.json` and pass `--config local_config.json`. Block sizes must be
multiples of four. Default settings are COM5, firmware `20250809`, seed `20261014`,
500 ms fixation, 500 ms stimulus, and a 1500 ms optical response window.

```powershell
.\.venv\Scripts\python.exe run_simon.py --seed 12345
.\.venv\Scripts\python.exe run_simon.py --config local_config.json
.\.venv\Scripts\python.exe run_simon.py --help
```

Marker geometry, display index, window size, black interval, and drain grace are
explicit configuration values. The marker is an 80 px square, 20 px from the
lower-left edges by default. Scientific runs use full screen and a stable,
measured refresh rate. A stable refresh rate that cannot be measured stops
startup; no nominal 60 Hz value is silently substituted.

## Timing and event association

The task draws the colored stimulus and white optical marker on the same flip.
After the programmed frame count, it draws the marker black and removes the
stimulus. A response never changes either duration or advances the visual trial.
Durations are rounded to the nearest whole display frame. Host flip timestamps
are diagnostics only; they never enter scientific RT.

The visual trial ends at its fixed nominal response-window frame count from the
stimulus flip. Physical scanout can place the lower-left marker onset later than
that flip, so the scientific response window is evaluated separately as
`Opto 1 ON hardware time + 1500 ms`, including the deadline millisecond. The
following black interval retains eligible responses in that short difference.
The marker and stimulus can occupy different scanlines; their physical luminance
onsets are not assumed simultaneous. RT is relative to the marker, pending
measurement of the marker-to-stimulus scanout difference.

Only the first eligible Button 1 or 2 press after optical onset counts. Earlier
presses are anticipatory; later ones are late. Exact timestamp ties use wire
message sequence: a press before ON in the same millisecond is anticipatory.
Missing/ambiguous optical transitions, inconsistent durations, clock/order
uncertainty, dropped visual frames, and incomplete acquisition invalidate RT.
A valid omission has accuracy 0 and an empty RT.

Read-only `T` timer queries bracket each trial in hardware time. The lower query
precedes fixation. The upper query follows the fixed visual timeline and 500 ms
black interval; a further bounded 500 ms grace drains pending messages. Queries
occur on black screens and do not reset the timer or generate event triggers.
Messages are never flushed at trial boundaries. Every checkpoint re-scores all
attempted trials from the retained event stream; late arrivals remain attached
to their hardware interval. Events arriving beyond that trial's grace invalidate
its result. Missing ON does not shift the next trial's association.

If a boundary reply times out, acquisition stops and the attempted trial is
incomplete. A backwards hardware boundary stops acquisition and invalidates the
session's attempted scientific results. An inconsistent wire-event timestamp
order is retained and conservatively invalidated. Timer-query reply formatting
and ordering need qualification with the stated firmware.

## Outputs

Each actual session creates a new, unique `results/<session_id>/` directory with
exactly four completed output files:

| File | Contents |
| --- | --- |
| `trials.csv` | Trial identity, condition, congruency, response/accuracy, original integer hardware onset/offset/press/release, RT, validity, flags, hardware boundaries, and diagnostic flips. |
| `events.csv` | Every interpreted event in wire order, including releases, sensor transitions, duplicates, unexpected inputs, and arrival diagnostics. |
| `serial_raw.jsonl` | Byte-exact RX chunks in Base64, original message contents, TX commands, fragments, malformed data, and serial errors. Concatenating RX chunks reconstructs the incoming byte stream. |
| `session.json` | Parameters and trial plan, seed, expected/observed firmware, serial settings, confirmed mode, dependency/Python versions, source commit/dirty state, measured display rate, and lifecycle status. |

Empty CSV cells mean unavailable data. Filter behavioral analyses to `valid=True`
and distinguish responses from omissions using `status`. Read `flags` as well:
duplicate, anticipatory, late, unexpected, and non-task-button events may be
informative even when a trial has an eligible response.

Raw and event writes are buffered during visual presentation. Trial boundaries
flush acquisition and atomically replace the trial summary and metadata.
Escape/errors run cleanup and save again, retaining partial lines as raw records.
No implementation can guarantee unflushed data survive abrupt power loss,
process termination, or a failed disk; the tested guarantee concerns handled
Escape and exceptions with a writable output directory.

## Project files and continuity

`tpad_serial.py` owns acquisition/parsing; `trial_logic.py` owns generation and
scientific scoring; `run_simon.py` owns presentation, navigation, and output.
Tests use fake serial input and displays and do not qualify hardware.

Read [docs/PROJECT_HANDOFF.md](docs/PROJECT_HANDOFF.md) before resuming work and
preserve [docs/DECISIONS.md](docs/DECISIONS.md). EEG electrical qualification is
a later milestone; no BioSemi or OpenBCI connection is needed for first software
acceptance. Future HID redundancy is documented but unimplemented. No remote
repository has been created.
