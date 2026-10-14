# Project handoff

This is the canonical continuity document for the Simon–TPad MVP. Read it with
AGENTS.md before making changes. Updated 2026-10-14 (Europe/Zurich).

## Current status and repository

The initial MVP is implemented and software-verified. Real T-Pad behavioral
acceptance and physical/EEG qualification remain outstanding.

- Repository: `C:\Users\pruggeri\Documents\EXPERIMENTS\GABRIEL_PAOLO`
- Branch: `main`.
- Validated implementation commit: `106f32d50590c57e9a752ad1e236ae3ef660ae66`.
  The subsequent handoff commit updates this document only; the code and tests
  remain at this validated implementation revision.
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
  the project uses pixels and has no calibrated viewing-distance/visual-angle setup.
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
