# Project handoff

This is the canonical continuity document for the Simon–TPad MVP. Read it with
AGENTS.md before making changes. Updated 2026-10-15 (Europe/Zurich).

## Current status and repository

The initial MVP and M2 standalone optical calibration patch are implemented and
software-verified. Real T-Pad behavioral acceptance and physical/EEG qualification
remain outstanding. M2 supplies a visual patch only; the operator calibrates
sensitivity separately with the official BBTK application.

- Repository: `C:\Users\pruggeri\Documents\EXPERIMENTS\GABRIEL_PAOLO`
- Branch: `main`.
- Validated original Simon implementation: `106f32d50590c57e9a752ad1e236ae3ef660ae66`.
  Baseline handoff: `11f9ed1bb8aef954dd0a8119b29c2c6cb01dd9f2`.
  M2 leaves all Simon application modules, configuration, dependencies, and
  original tests unchanged. The M2 commit adds the standalone utility and its
  tests, and updates README/decisions/this handoff; resolve current HEAD below.
- Current repository revision: `HEAD`; resolve with the commands below.
- Git author: `paolo ruggeri <paolo@mailtrial.com>`, supplied by the PO and
  configured only in this repository.
- No remotes, GitHub repositories, pushes, firmware updates, driver changes,
  Windows settings changes, or global package modifications.

The sandbox-created repository has a different Windows owner from the normal
user account. Use a per-command `safe.directory` option for Git if it reports
dubious ownership; global Git trust configuration was not changed.

## Approved PO decisions

PO-001 through PO-005 remain binding; see DECISIONS.md. All scientific RT uses
T-Pad integers. All event-related TTL is automatic hardware output. Enter Mode 5
once during setup. The PC keyboard controls navigation and Escape; the serial
connection supplies behavioral responses. Future HID redundancy is unimplemented.

## Implemented functionality

- `tpad_serial.py`: XiD parser and timeout-zero, bounded serial polls; partial,
  multi-line, CR/LF/CRLF, malformed, duplicate, held, and unexpected input handling;
  byte-exact raw chunks; all four physical buttons; sensor transitions; error/close
  preservation; command allowlist without TTL writes or explicit timer resets.
- `trial_logic.py`: deterministic balanced trial order; color mapping and
  congruency; hardware timer boundaries; first eligible response; integer RT,
  accuracy, omissions, anticipatory/late/duplicate flags, and conservative validity.
- `run_simon.py`: fixed frame presentation, synchronized white/black lower-left
  marker; ordinary keyboard controls; firmware/mode acknowledgement; read-only
  timer queries on black screens; bounded grace; four session outputs; checkpoint
  and abort/error saving; project-local PsychoPy preferences; GUI smoke command.
- `config.json`: explicit default protocol, serial port, firmware, geometry,
  durations, grace, and seed. `requirements-lock.txt`: verified runtime environment.
- README and manual validation procedure: installation, operation, data fields,
  scientific limits, and separate hardware/EEG qualification.

## Environment and reproducibility

Only one interpreter was found via the Python launcher: 64-bit CPython 3.11.9 at
`C:\Program Files\Python311\python.exe`. Created `.venv` without system-site
packages. Existing user-level PsychoPy 2023.1.3 and pyserial 3.5 were read for
inspection but not altered or imported by the new launcher.

Verified runtime: PsychoPy 2026.2.4, pyserial 3.5, NumPy 2.3.5, pyglet 1.4.11.
All resolved runtime packages are pinned in `requirements-lock.txt`. Packages
were installed only in `.venv`. PsychoPy import uses preferences under
`.cache/roaming/psychopy3`, with user-site loading disabled and no global
site-packages paths. APPDATA is redirected only inside the application process.

## Test evidence

On 2026-10-14:

- `python -m unittest discover -s tests -v`: **36 tests passed**, final run
  0.930 seconds on this PC. Pure parsing/scoring tests and fake-device/display
  integration tests cover the requested cases, all four exports, 20 completed
  synthetic trials, setup acknowledgements, query timeout, firmware mismatch,
  and preservation after Escape/serial/display exceptions.
- `python -m pip check`: no broken requirements.
- `python -m compileall -q run_simon.py tpad_serial.py trial_logic.py tests`: passed.
- `python run_simon.py --help`: passed without opening hardware.
- `python run_simon.py --gui-smoke`: passed with actual PsychoPy import/window,
  blue stimulus/white marker drawing, black offset, and automatic close.
  Measured refresh 59.978467729887036 Hz, window 1024 x 768. The only observed
  GUI warnings concerned a temporary monitor specification; no calibration is
  claimed. Smoke evidence is in ignored `.cache/gui_smoke.json`.
- Read-only serial enumeration listed COM1, COM3, COM5. COM5 was not opened
  for these checks. Synthetic tests do not validate the attached pad or TTL.
- `git diff --cached --check`: passed after removing trailing blank lines found
  by the first staged-file check.

## M2 implementation and verification (2026-10-15)

`calibrate_opto.py` is an independent windowed PsychoPy utility. It reads only
display size/index from config.json and does not import the Simon runner or
serial acquisition code. There are no device commands or serial connections.
No packages were installed or dependency pins changed for M2.

The marker inspection established `rgb` color space, black `(-1, -1, -1)`,
white `(1, 1, 1)`, pyglet backend, synchronized flips, and default gamma handling.
M2 uses those explicit numeric endpoints and settings. A live comparison to the
original named-color Rect defaults confirmed the same values/color space.

The initial instruction asks the operator to click to create the 4 x 4 cm patch.
Without reliable scaling, the utility first presents a ruler-reference square:
Left/Right adjusts its size, Return confirms both sides as physically 4 cm.
Alternatively use measured `--pixels-per-cm` or matching calibrated profile
geometry (`--monitor NAME` for explicit selection). The two inspected profiles,
project-local and per-user `testMonitor.json`, both identify themselves as default
and are rejected as physical calibration evidence. Scale is not saved globally.
The ruler UI was tested with synthetic confirmation, not a physical measurement.

Clicks place/reposition a black patch below a reserved instruction area. Click
coordinates are captured at the event, avoiding pointer motion before processing.
The full patch is clamped within the window; its outline is outside it. Mouse
cursor and instruction text never cover the patch while it is being presented.
Space starts black for 10 s, white for 10 s, then black with the completion
message; Space repeats. Placement is locked while running. Escape and close
cleanup release the window without touching the T-Pad. A Windows topmost window
remains visible when another application has focus; no focus-dependent pause,
blocking sleep, global keyboard hook, or persistent Windows change is used.

M2 verification:

- Full suite: **41 tests passed** (36 original + 5 M2), final run 0.991 s.
  M2 tests cover actual-flip phase anchoring, deadlines, repeat behavior, safe
  geometry, rejection of default/mismatched profiles, and explicit profile choice.
- The GUI smoke opened real windows, injected click/key events into its own
  utility, verified placement and repositioning, checked black/white/black RGB
  pixels in desktop captures, kept another owned window in the foreground during
  the sequence, and verified repeat/ESC. `serial.Serial` was guarded to fail if
  called; it was not called. BBTK itself was not launched by these tests.
- Measured black duration: **10.0019473 s**; white duration: **10.0155785 s**;
  measured refresh **59.9069824 Hz**. These are software flip intervals, not
  photodiode measurements. The ten-second target is limited by display refresh
  granularity, Windows composition, and missed frames. No physical exactness or
  sensor calibration success is inferred.
- An additional ruler GUI smoke verified Left/Right, Return, subsequent click
  placement, black rendering, and the original Simon marker color equivalence.
- Compile checks and `calibrate_opto.py --help` passed. Git diff confirmed that
  `run_simon.py`, `tpad_serial.py`, `trial_logic.py`, `config.json`, requirements,
  and existing tests were unchanged.
- OpenGL front-buffer captures were empty in the sandbox. Successful visual
  verification used the interactive desktop and captured only the utility's
  client area. Evidence: ignored `.cache/opto_smoke.json`,
  `.cache/opto_smoke_white.png`, `.cache/opto_smoke_black.png`. The smoke uses
  synthetic 40 px/cm, not a measurement of this monitor. A default monitor warning
  appeared; no calibrated physical display dimensions are claimed.

BBTK must own COM5 for sensitivity calibration. The operator coordinates the
independently controlled patch with BBTK's external-patch workflow (guide section
5), acknowledging the correct black/white prompts. There is no calibration
handshake and the sequence is not synchronized to BBTK's own automatic patch.
After calibration, disconnect/close BBTK before starting a Simon session.

M2 resume commands, in the existing repository:

```powershell
.\.venv\Scripts\python.exe calibrate_opto.py
.\.venv\Scripts\python.exe calibrate_opto.py --pixels-per-cm 40
.\.venv\Scripts\python.exe tests\smoke_calibrate_opto.py
.\.venv\Scripts\python.exe tests\smoke_calibrate_opto.py --ruler-only
```

The value 40 is an example/synthetic test scale. Measure the actual patch with a
ruler on its target display, including both axes, and repeat the scale check after
moving monitors or changing resolution/DPI scaling. Pixel rounding limits size
precision. Next: the PO verifies physical size and runs BBTK calibration, then
continues the existing real T-Pad validation procedure. Hardware/EEG status below
remains unchanged.

## Hardware status and known limitations

The PO reports T-Pad v1, COM5 at 115200/8N1/no flow control, firmware `20250809`,
FTDI latency 1 ms, four buttons, Opto 1, working serial, and faulty HID. The app
verifies firmware/mode during an operator-started session. None of these hardware
claims was independently remeasured in the implementation run.

No known unresolved software test failures. Remaining qualification/limits:

- Real firmware timer-query delimiters, reply ordering, serial delay/backlog,
  button identities, and optical P/R polarity require direct raw-log evidence.
  The guide contains an inconsistent example; follow PO-approved P=ON/R=OFF.
- Responses never control stimulus offset. The visual response phase is fixed
  from its flip; scientific response eligibility is exactly 1500 hardware ms
  from marker ON. Black collection covers scanout differences. Marker/stimulus
  physical onset differences must be independently measured.
- Missing/ambiguous optics, unresolved acquisition, dropped visual frames, and
  backwards/order-uncertain hardware time invalidate RT. Late data remains raw
  and event-visible but data arriving beyond grace invalidates its trial.
- The current reader tracks held buttons; release outside a trial stays in
  events.csv but need not appear in that trial's release column.
- Frame resolution limits visual duration. A measured refresh rate is mandatory;
  the Simon task uses pixels and has no calibrated viewing-distance/visual-angle setup.
- Raw/event writes are buffered during rendering. Handled abort/errors preserve
  received data with a writable disk; abrupt power loss or forced termination
  can lose data since the last checkpoint. Disk writes are synchronous between
  trials; there is no background acquisition service.
- EEG electrical adapters, polarity, grounding, voltage compatibility, pulse
  widths, simultaneous TTL lines, and recorded EEG are unqualified. Hardware
  markers do not encode arbitrary Simon conditions or trial IDs.
- No HID redundancy or HID/serial synchronization is implemented. Do not infer
  physiological or full hardware acceptance from software test success.

## Next milestone

The PO executes docs/HARDWARE_VALIDATION.md without EEG first. Preserve real
session IDs/raw logs, confirm all clean trials and the timer-boundary assumptions,
and record timing/abort evidence here. After behavioral acceptance, qualify the
physical marker scanout relation and EEG electrical/recorded TTL chain separately.

## Exact commands to resume

```powershell
Set-Location 'C:\Users\pruggeri\Documents\EXPERIMENTS\GABRIEL_PAOLO'
git -c safe.directory=C:/Users/pruggeri/Documents/EXPERIMENTS/GABRIEL_PAOLO status --short --branch
git -c safe.directory=C:/Users/pruggeri/Documents/EXPERIMENTS/GABRIEL_PAOLO log -1 --format='%H %s'
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run_simon.py --gui-smoke
.\.venv\Scripts\python.exe run_simon.py --windowed
```

For the full-screen behavioral session, move the sensor to the full-screen marker:

```powershell
.\.venv\Scripts\python.exe run_simon.py
```

If `.venv` is absent on another PC, use the exact recreation commands in README.md.
Never install into global Python or an existing PsychoPy environment.
