# Project handoff

This is the canonical continuity document for the Simon–TPad MVP. Read it with
AGENTS.md before making changes. Updated 2026-11-18 (Europe/Zurich).

## Current status and repository

The initial MVP, M2 optical calibration patch, and M2B optical timing diagnostic
are implemented. The PO now reports repeated Simon sessions, four-button serial
acquisition, hardware RT checks, ten detected diagnostic pulses and BioSemi TTL
activity visible in ActiView. Saved-BDF event/timing verification, the OpenBCI
branch and full scientific qualification remain outstanding. M2 supplies a visual
patch only; M2B reuses the actual Simon marker and serial acquisition to check
timing after the operator calibrates sensitivity separately in the BBTK app.

- Active existing checkout: `C:\Users\pruggeri\Documents\EXPERIMENTS\GABRIEL_PAOLO`
  on `feature/standalone-tpad-listener`, tracking
  `origin/feature/standalone-tpad-listener`.
- Validated original Simon implementation: `106f32d50590c57e9a752ad1e236ae3ef660ae66`.
  Baseline handoff: `11f9ed1bb8aef954dd0a8119b29c2c6cb01dd9f2`.
  M2 leaves all Simon application modules, configuration, dependencies, and
  original tests unchanged. The M2 commit adds the standalone utility and its
  tests, and updates README/decisions/this handoff; resolve current HEAD below.
- M2 baseline commit: `b05fb53c23c52cce829dd1aca225188d73017601`.
  The current M2 revision replaces its automatic sequence with manual Space
  toggles, following the PO's request. M2B adds `opto_diagnostic.py` and focused
  tests/documentation; Simon source, shared serial/trial modules, configuration,
  dependencies, and original tests remain unchanged. Resolve current HEAD below.
- M2B initial implementation: `75aa94021e79c794a37f83f75f2eb1519a9e9ec2`.
  The PO subsequently simplified its presentation to optical white/black pulses
  only; the current revision supersedes that commit's full Simon timeline.
- Current repository revision: `HEAD`; resolve with the commands below.
- Git author: `paolo ruggeri <paolo@mailtrial.com>`, supplied by the PO and
  configured only in this repository.
- M3 authorizes PRIVATE https://github.com/pool-ruggeri/simon-tpad-mvp and normal
  publication of main with its complete history. Publication progress/evidence
  is recorded in the M3 section below; prior no-remote statements are historical.
- No firmware updates, driver changes, persistent Windows settings changes,
  or global package modifications.

The original PC's sandbox-created checkout has a different Windows owner from
the normal user account. Use a per-command `safe.directory` option for Git if
that checkout reports dubious ownership.

## Existing checkout switch and verification (2026-11-18)

- The existing working directory was clean on `main` at
  `8528349437b5719ab06bf922cdd1953b1153c3f1` before fetching GitHub changes.
  Switched in place to a new local tracking branch at
  `62238cffb84e9d6ff25622cd18b136479cb6f914` (`Add live tPAD button capture tool`).
  HEAD and `origin/feature/standalone-tpad-listener` match, with zero commits
  ahead or behind. No second clone or merge was made; local `main` is unchanged.
- Checked target paths against local files before switching and used
  `git switch --no-overwrite-ignore`. No conflicts were found. After switching
  and testing, all 64,479 protected pre-existing files retained their sizes and
  modification times, including 32,058 files in `.venv`. Content hashes also
  matched for protected files outside environment/cache directories, including
  configuration and experimental output. All pre-existing directories remain.
- Verified `tpad_listener.py` and `capture_tpad.py` are present. Used the existing
  `.venv` Python 3.11.9 without package installation. Ran
  `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`:
  **73 tests passed in 1.848 seconds**, exit code 0. Disabled bytecode writes
  for this process to preserve existing caches. These are automated software
  checks; no physical T-Pad or EEG validation was performed.
- Ignored local evidence: `.cache/branch_switch_20261118T122117019177Z/`
  contains `preservation_before.json`, `preservation_after.json`, and
  `unittest.txt`. Environment/cache files were checked by metadata; these
  manifests are evidence inventories, not backup copies.
- This handoff update was left local and uncommitted at that checkpoint so HEAD
  stayed at the fetched feature commit. Its content is preserved in the P2
  update below. Resume from this existing directory with the exact commands at
  the end of this document.

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

## P2 minimal PsychoPy Simon demo (2026-11-18)

The PO reports that P1 and `capture_tpad.py` work on COM5, including B1-B4
press/release events, Mode 0/Mode 5 initialization and hardware timestamps.
These remain PO-supplied physical observations, not new P2 measurements.

The PO subsequently requested substantial simplification. The current demo
supersedes the original P2 implementation at
`a0b0e8c60dca7298e55c90f112c066d5c31f31b5`: its 200 ms patch, 20 px margin,
100 ms host receive-delay cutoff and whole-train RT exclusion no longer apply.
The existing uncommitted zero-margin change was preserved. Its original source,
local diff and protected-file hashes are backed up in ignored
`.cache/p2_simplification_20261118T132307874060Z/`.

Current implementation:

- `simon_demo_psychopy.py`: 233 total lines including comments/blank lines.
  Parameters first, two small event/export helpers, one procedural `main()`;
  no classes or scoring framework. Initialization, acquisition and cleanup are
  marked A/B/C. Reuses the unchanged standalone listener directly.
- Eight balanced red/blue x left/right trials; fixed local RNG seed 20261118.
  RED = B1/physical left, BLUE = B2/physical right; confirm physical placement.
  Fixation 500 ms, colored stimulus 500 ms, response window 1500 ms, ITI 500 ms.
  Fullscreen by default; `--windowed` remains for initial checks. Space/Return
  starts; Escape saves and exits. Responses cannot shorten any visual phase.
- Patch: 150 x 150 drawing pixels at EXACT bottom-left with ZERO margin.
  Center = `(-win.size[0]/2 + 75, -win.size[1]/2 + 75)`. White starts on the
  stimulus flip for 100 nominal ms (six frames near 60 Hz); otherwise black.
  Planned/actual transition flips are logged; PsychoPy's dropped-frame count
  is saved. Timing/scanout are nominal until physically measured.
- Polls the nonblocking reader every displayed trial frame, during instructions
  and a final black collection interval. All records are retained in original
  order, including releases, B3/B4, both optics, microphone, mode/diagnostic,
  repeated, extra, malformed and incomplete records. No raw filtering,
  suppression, debounce, deduplication, reordering or timestamp replacement.
- `receipt_trial`/`receipt_phase` are serial RECEIPT context; every raw row
  explicitly says `association=unconfirmed`. Final/cleanup data are unassigned.
  A partial payload that started before stimulus onset cannot establish its
  optical onset association. There is no host receive-delay cutoff.
- Trial accuracy is independent of optical validity. The first B1/B2 press
  received during the nominal stimulus/response-wait window supplies response,
  original hardware time and accuracy (`response_basis=nominal_window_receipt`).
  A completed omission has accuracy 0. Serial lag can affect this receipt-based
  summary; raw logs remain available for separate analysis.
- All received Opto 1 ON/OFF values appear as JSON lists in the trial table;
  a unique pair supplies its observed hardware duration, including unusual
  short pulses. Only an ordered, context-consistent pair without local damaged
  acquisition or time regression can supply observed RT. The selected press
  must follow ON in receive order and be within 0-1500 hardware ms. The sole
  subtraction is `press.tpad_ms - onset.tpad_ms`. It is labeled as an observed
  receipt-context association, not confirmed physical trial identity or full
  scientific qualification. Uncertain/missing/extra optics leave only that
  trial's RT unavailable; accuracy and other trials remain intact.
- Unique ignored `output/simon_demo/<session>/` has `events.jsonl`, `trials.csv`,
  `timing.csv`, `session.json`. Raw payload bytes are exact base64; both PC
  receipt timestamps, original hardware ms and sequence are saved. Eight trial
  rows include unstarted/partial trials. Exports are attempted independently
  after completion, Escape or handled serial/display/setup/close errors.

Verification using the existing `.venv` Python 3.11.9:

- Full suite: **85 tests passed in 2.516 seconds** (73 original + 12 updated demo tests), covering
  balance/seed/mapping/congruency, 100 ms patch/500 ms stimulus, zero-margin
  fullscreen geometry including simulated 1920 x 1200, phase polling, all raw
  record types/repeats, missing/extra/short/late optics, response accuracy with
  missing optics, omissions, crossed receipt context, timing independence,
  Escape in every phase, setup/serial/display/close errors and independent
  exports. The 150 ms optical-delivery test demonstrates removal of the old
  100 ms receive cutoff.
  Log: `.cache/p2_simplification_20261118T132307874060Z/unittest.txt`.
- Real fullscreen GUI smoke passed with an empty mocked listener and serial-open
  guard. Actual framebuffer in this tool run: **1920 x 1080**, patch center
  **(-885, -465)**, refresh **59.9708602 Hz**. All eight patches had **6 white
  frames**; observed flip durations **98.495-102.129 ms**. Stimulus intervals
  were **498.254-502.157 ms**. **0 dropped frames**, **1,232 polls**.
- Own-backbuffer pixel checks confirmed the complete 150 px square reaches the
  left/bottom edges, white RGB 255 inside and black RGB 0 immediately outside;
  black-state samples were RGB 0. Readback/screenshot saving happens BEFORE
  refresh measurement/acquisition, not during timed pulses. Evidence:
  `.cache/simon_demo_smoke/evidence.json`, `patch_black.png`, `patch_white.png`,
  and the timestamped simulated session. No device or COM5 was opened.
- The tool framebuffer differs from the PO-reported 1920 x 1200 lab display.
  Nothing was reconfigured: placement uses actual `win.size`; a 1920 x 1200
  window yields (-885, -525), verified in simulation. Confirm the intended
  display using real session metadata. A temporary-monitor warning is not
  physical calibration evidence.
- Protected listener/capture/original Simon/serial/scoring modules, configuration,
  dependency pins, existing `.venv` and pre-existing acquisition data are unchanged.
  Preservation checked 32,103 data/environment files; syntax, CLI help and Git
  diff checks passed. Local details are in the same evidence folder's
  `verification.json`.

Physical acceptance and remaining limits:

1. Close BBTK/capture; confirm COM5 and B1-left/B2-right. Launch fullscreen below
   and position Opto 1 inside the zero-margin patch on the actual intended display.
2. Retain real logs and check eight nominal 100 ms pulses, raw integer timestamps,
   receipt context/delivery and marker-to-colored-stimulus scanout alignment.
   Observed RTs require physical review of those association assumptions.
3. Check correct/error/omission responses, B3/B4/releases/microphone raw records
   when available, a missing/extra pulse without losing accuracy/other trials,
   and Escape during fixation/stimulus/wait/ITI followed by restart/port release.
4. Inspect all raw events before more sophisticated offline scoring. No host
   timestamp is substituted for missing optics, and no software TTL, firmware,
   sensitivity, driver or system change was introduced.

Data are buffered for this short task. Forced termination, power/disk failure
or unread driver bytes remain unrecoverable. The unchanged listener does not
expose internal setup records if its constructor itself fails. Physical optical,
voice-key and EEG qualification remain separate from these simulated checks.

```powershell
.\.venv\Scripts\python.exe simon_demo_psychopy.py --port COM5
.\.venv\Scripts\python.exe simon_demo_psychopy.py --port COM5 --windowed
.\.venv\Scripts\python.exe tests\smoke_simon_demo_psychopy.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Work stays on `feature/standalone-tpad-listener`; resolve the published source
revision with `git log -1` and compare to `git ls-remote origin
refs/heads/feature/standalone-tpad-listener`. No merge into `main`.

## P1 standalone listener on the new Windows PC (2026-11-18)

- Cloned the private project on Windows 10 Education x64 (build 19042) with
  Git 2.54.0. The worktree was clean and `main` matched `origin/main` at
  `8528349437b5719ab06bf922cdd1953b1153c3f1` before creating the feature branch.
- Extracted signed CPython 3.11.9 x64 into the project cache. Passed its local
  path to `setup_windows.ps1 -PythonExe`. Keep `.cache\cpython-3.11.9\tools`
  while using this `.venv`, which uses that base interpreter. All application
  packages are isolated in `.venv`, including PsychoPy 2026.2.4 and pyserial 3.5.
  [Official Python NuGet package](https://www.nuget.org/packages/python/3.11.9)
- Windows setup passed `pip check`, pinned-version checks, application and
  PsychoPy visual imports, CLI startup and all **52 baseline tests**. PsychoPy
  created a temporary monitor specification during import. The full suite after
  implementation passed **70 tests**. The 18 added tests use a mocked port and
  clock and cover setup, timeouts, fragmentation, all supported physical event
  types, damaged input, repeats, receive order and cleanup. The README capture
  example also passed with a mocked port and an isolated copy containing only
  the listener and pyserial.
- The Simon, optical patch and optical diagnostic display smoke checks passed.
  The diagnostic matched 10 of 10 injected pulses and retained one short
  activation. Details are in ignored `.cache/gui_smoke.json`,
  `.cache/opto_smoke.json` and `.cache/opto_diagnostic_smoke/evidence.json`.
- Read the PO-accepted MATLAB listener, integration guide, tests, X/Y demo and
  handoff at `3f848cb67341aa384a6797f629d66130aef4808c`. The Python module
  follows its mode handshake, accepted timestamp range, event framing and raw
  record behavior. It labels M1 as `microphone` with P/R mapped to active/inactive,
  using the vendor's Mode 5 channel table in section 18.5.
  [MATLAB reference guide](https://github.com/pool-ruggeri/PND_BIOSEMI_BIOPAC_ELINK/blob/3f848cb67341aa384a6797f629d66130aef4808c/TPAD_INTEGRATION_GUIDE.md)
  · [Black Box Toolkit tPAD guide](https://www.blackboxtoolkit.com/docs/pdf/TPadv1r1.pdf#page=129)
- `tpad_listener.py` is standalone and requires pyserial and the standard
  library. Setup sends only the two mode commands. Each `poll()` returns the
  next batch of exact payloads without delimiters. The connection closes
  without draining unread device/driver bytes. Poll frequently and keep
  physical event timing on the device clock within one uninterrupted
  acquisition. PC receipt times describe delivery.
  [Python API and capture example](../README.md#standalone-tpad-listener-p1)
- `capture_tpad.py` uses the same listener for a live button check and saves
  every returned record, including the tail on Ctrl+C, in ignored
  `output/tpad_capture_*.jsonl`. The `raw_base64` field preserves the original
  payload bytes. All **73 tests** passed, including three new mocked tests
  for live display, interruption and serial errors. A capture with the real
  listener and mocked serial also preserved both acknowledgements, all eight
  button edges, a malformed record and the incomplete tail.

### Physical button validation to run on this PC

1. Connect the tPAD's Serial USB lead and identify the actual COM port in
   Device Manager. Close BBTK and any acquisition application that owns it.
2. Run `.\.venv\Scripts\python.exe capture_tpad.py --port COM3 --duration 30`
   from the checkout with the actual port in place of COM3. Confirm the terminal
   shows `MODE 0:` followed by `MODE 5:`.
3. Press and release B1, B2, B3 and B4 in order, then repeat. Check that the
   terminal shows both edges for each button and the original hardware time
   in milliseconds.
4. Check the raw event fields, original integer milliseconds and local sequence
   in `output/tpad_capture_*.jsonl` against the observed actions. Repeat with
   Ctrl+C during collection, check the saved partial capture, and start a
   fresh run to verify port release. Record the device and firmware, COM port,
   source commit and observations alongside the captures in ignored `output/`.

The PO subsequently reports physical B1–B4 validation on COM5, including
press/release events, Mode 0/Mode 5 initialization and hardware timestamps.
Optical, voice-key and TTL/EEG qualification remain pending. The Windows pyserial backend clears queued
driver input when opening the port, so begin button presses after setup.

## M3: publication and Windows deployment (2026-10-15)

- Published repository: **PRIVATE**
  [pool-ruggeri/simon-tpad-mvp](https://github.com/pool-ruggeri/simon-tpad-mvp).
  The PO selected `pool-ruggeri`; the unrelated `hippolytefournier` PC credentials
  must not determine repository ownership. The official portable GitHub CLI was
  authenticated as `pool-ruggeri`, with credentials in the Windows keyring and
  no global Git credential-helper change. A repository-local helper uses that
  CLI/keyring so the PC's unrelated account is not used for this origin.
- Created `origin`, pushed main and its full history normally, and verified
  PRIVATE visibility and default branch `main`. The first published source
  revision was `cded7d8bb56280f98c47025f89b1e3663dfc0c6d`; Git's remote reference
  and GitHub's commits API both matched it. The remote tree matched all 27 local
  tracked files, with no generated data/archives/environments/vendor binaries.
  The final documentation revision remains `main/HEAD`; compare it using the
  commands below. No history was rewritten or force-pushed.
- Branch: `main`. Starting HEAD: `53b648516eb3d8202b59f2180a9b245ba177439f`.
  The publication revision is the final `HEAD`; resolve with `git rev-parse HEAD`
  and compare to `git ls-remote origin refs/heads/main`. History is preserved.
- Reviewed all 21 tracked files and all six commits/41 historical blobs at the
  starting revision. No data, vendor binaries, excluded paths or credential
  pattern matches were found. This was source/inventory review and a pattern-based
  scan, not a guarantee that every possible secret format can be detected.
  Evidence: ignored `.cache/publication_audit.json`. `.gitignore` now excludes all
  output/results, data/recordings, EEG formats, archives, virtual environments,
  caches, private keys and editor/machine settings. No local data was deleted.
- Repeated the history scan immediately before publication: eight commits,
  54 historical blobs, 27 tracked files; no excluded paths, binary blobs or
  credential-pattern matches. Publication evidence is recorded in ignored
  `.cache/m3_publication_evidence.json` and checked again after the final push.
- Added `setup_windows.ps1`, `requirements-bootstrap.txt`, and three `launch_*.ps1`
  wrappers. Setup requires CPython 3.11.9 x64, creates only a new clone-local
  `.venv`, installs the unchanged runtime lock plus pinned packaging tools, and
  verifies all versions, dependencies, application/PsychoPy visual imports, CLI
  startup and hardware-free unit tests. Existing environments are preserved;
  `-VerifyOnly` never installs packages. No hardware is opened by setup.
- Added [INSTALL_ON_NEW_PC.md](INSTALL_ON_NEW_PC.md) with the complete private
  clone/setup/COM-port/calibration/diagnostic/task/TTL/troubleshooting procedure.
  COM portability already works through complete local `--config` JSON; the
  diagnostic also has `--port`. Scientific application code is unchanged.
- Reference environment verified: Windows 10 build 19045 x64, CPython 3.11.9 x64,
  PsychoPy 2026.2.4, pyserial 3.5. Windows 10/11 x64 are the deployment targets;
  Windows 11 and a second physical PC have not been validated. Setup does not
  install prerequisites, alter drivers/firmware, or modify global Python.
- Initial `-VerifyOnly` passed pinned versions, `pip check`, all application and
  PsychoPy visual imports, all three CLI help commands, and **52 tests** (3.631 s).
  All three PowerShell launch wrappers also passed `--help`.
- Fresh installation passed from local preparation commit `0cceec3` in the clean
  clone `.cache/portability-check/repo`, using the documented default setup command
  and a newly created `.venv`. Package-index installation (including normal pip
  cache reuse), `pip check`, every pinned version, all application/PsychoPy visual
  imports, CLI startup and **52 tests** (1.687 s) passed. Its 101 installed package
  versions including packaging tools exactly match the original environment.
  The original environment's before/after package sets are unchanged.
- The fresh clone's `run_simon.py --gui-smoke` passed with a real 1024 x 768 window,
  59.9937 Hz measured refresh and no serial open. The expected default-monitor
  warning appeared. No physical display calibration, tPAD or EEG was tested.
  Evidence: ignored `.cache/m3_portability_evidence.json` and the clone's
  `.cache/gui_smoke.json`. This is a same-PC clean installation, not validation
  of a second physical PC, Windows 11, or a package-cache-free/offline installation.
- Both acquisition CLI paths were checked with a temporary complete configuration
  selecting COM17 and a mocked run function; the diagnostic's `--port COM18`
  correctly overrides that setting. No serial connection was opened. The existing
  `.venv` preservation error and nine representative ignore patterns were checked.

M3 laboratory status comes from the PO's supplied milestone instructions, not a
new hardware measurement or review of saved raw/BDF files during this work:

- Simon has run successfully over multiple sessions; all four serial buttons and
  hardware timestamp RT calculations were checked; the optical diagnostic passed
  10/10 pulses. Brief extra optical activations were observed in some sessions.
- BioSemi TTL activity was seen in ActiView. Saved-BDF event counts/labels/timing
  are still pending. OpenBCI is unvalidated and requires electrical verification
  of its exact input limits and actual split-cable isolation/level conversion
  before use, followed by saved-event validation.
- **Approved artifact-policy gap:** Simon's `score_trial` picks the first eligible
  ON but requires a single ON/OFF pair; extra edges invalidate RT. The diagnostic
  separately classifies short activations and matches a unique full pair, without
  choosing the first of multiple full candidates. The PO's first-complete,
  correctly-timed pulse policy is not fully implemented. No scoring feature was
  added as part of M3.

## Environment and reproducibility

On the original reference PC the Python launcher found 64-bit CPython 3.11.9 at
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
The patch starts black; each Space press toggles black/white, indefinitely, with
no timer or automatic transitions. Click to reposition in either color. Focus
this window for Space or Escape. The selected color remains visible while the
operator uses BBTK. Escape and close
cleanup release the window without touching the T-Pad. A Windows topmost window
remains visible when another application has focus; no focus-dependent pause,
blocking sleep, global keyboard hook, or persistent Windows change is used.

Original M2 verification at `b05fb53` (automatic sequence now superseded):

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
5), acknowledging the correct black/white prompts. Refocus the patch window and
press Space for each required change, then return to BBTK. There is no calibration
handshake or automatic sequence, and the utility cannot confirm sensor calibration.
After calibration, disconnect/close BBTK before starting a Simon session.

Manual-control revision verification (2026-10-15):

- Replaced the automatic sequence with a small black/white state. Space toggles
  only after patch placement; idle frames retain the color. Removed the timed
  sequence's refresh-rate measurement and completion message. Initial black,
  ruler/profile scaling, safe placement, explicit RGB values, and serial isolation
  are retained; repositioning is available in either color.
- Full suite: **52 tests passed**, 1.667 s. Updated M2 tests cover initial black,
  repeated toggles, no transition before placement, persistent idle color,
  repositioning while white, and Escape; existing geometry/profile tests pass.
- The real PsychoPy GUI smoke passed black/white/black/white toggles, placement,
  repositioning while white, and Escape. Black held for 11.0101 s and white for
  11.0081 s without Space while another owned window took focus. These are test
  waiting intervals, not automatic phase durations or physical measurements.
  A serial-open guard was never called. No BBTK application or device was opened.
- The ruler-only GUI smoke also passed Left/Right sizing, Return confirmation,
  subsequent click placement, black rendering, and Simon marker color equivalence.
- The first desktop pixel capture was affected by another open window. The
  updated smoke captures only its own rendered backbuffer before the actual flip,
  checking black/white RGB pixels at the center and near all four patch corners.
  Evidence: ignored `.cache/opto_smoke.json`, `.cache/opto_smoke_black.png`, and
  `.cache/opto_smoke_white.png`. The existing default-monitor warning remains.
- Physical dimensions remain unmeasured in these tests (synthetic 40 px/cm).
  Simon and diagnostic scripts, serial/trial modules, configuration, packages,
  and dependency pins are unchanged.

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

## M2B implementation and verification (2026-10-15)

`opto_diagnostic.py` reuses `Presentation` for display/marker setup and acquisition,
plus `events_for_trial` and `TPadReader`. The exact Simon marker is used:
default 80 x 80 drawing pixels, lower-left 20 px margin, named black/white in
`rgb`; in a 1024 x 768 window its center is (-452, -324). Window/display settings
come from config.json, with full screen by default. Following the PO clarification,
only the square alternates: 500 ms white then 500 ms black, repeated ten times.
No colored circle, fixation, or response window is drawn or scheduled. The
diagnostic uses a short `present_pulse` frame loop and timing-only
`PulsePresentation` records. The 4 cm M2 patch is not substituted. Hardware queries
and saving occur on black and may extend it; white duration remains frame-based
and independent of serial events. A final black grace collects delayed events.

The operator sees the requested instruction and an outline around the black
marker, presses Space for ten presentations, reviews the results, and presses
Space to repeat or Escape to save/exit. The outline is preview-only. Text stays
horizontally outside the marker. ON/OFF state uses prepared labels without layout
work while white; the compact numeric panel is updated on black at most 4 Hz.
All raw data is retained, with no new serial protocol, explicit timer reset, HID
channel, or software TTL. Mode 5 setup is entered once per launch; repeats retain
the connection and clock. A backwards timer invalidates timing statistics.

Four dedicated files are saved under ignored `output/opto_diagnostics/<id>/`:
`serial_raw.jsonl`, `optical_events.csv`, `pulses.csv`, and `summary.json`. Repeats
are separate numbered runs in that launch's files. Raw messages/chunks cover
all input; optical CSV includes both optical channels and duplicate flags. Analysis
uses Opto 1 only, ignoring pre-setup events for scientific results while retaining
them in the logs. Checkpoints happen on black screens and on error/Escape cleanup.

Physical edge pairs are separate from matched scheduled presentations. Full
pairs need not be exactly 500 ms. A configurable <=10 ms default threshold
separates the reported 1–2 ms activations. Repeated ON before OFF remains
ambiguous until an OFF restores synchronization. Unique full pairs must fit one
presentation's hardware boundaries without orphan/crossed edges, acquisition
issues, or data beyond its grace; missing/extra events never shift later identity.
Durations summarize all complete non-short physical pairs inside each run's
hardware bounds, even when scheduled identity is ambiguous. Onset intervals use
only adjacent uniquely matched scheduled indices. All measured statistics use
hardware milliseconds, with population SD; flip/arrival times never enter those
differences. Raw per-pulse differences remain visible but invalid if clock timing
becomes uncertain. No automatic hardware pass/fail is inferred.

Initial M2B evidence at `75aa940` (the full presentation loop is now superseded):

- Full suite: **52 tests passed** (41 existing + 11 diagnostic tests), including
  existing optical parsing, partial messages, hardware duration calculations,
  missing/extra/short/duplicate events, conservative matching, statistics,
  reused fixed presentation phases, four output files, repeats with one setup/
  connection, and preservation of completed pulses/fragments on serial error.
  Final run: 1.527 s. Compilation and `opto_diagnostic.py --help` also passed.
- The real PsychoPy GUI smoke uses ten unchanged Simon timelines with explicitly
  simulated serial data and guards against any real serial open. Synthetic full
  pulses are deliberately 505 ms, with one additional 2 ms activation. It reports
  10 complete/matched presentations, one short activation, and 30 white frames
  per presentation at approximately 60 Hz. Simulated 505 ms is test input, not a
  hardware measurement or a comparison between host and device clocks.
- Early display runs exposed expensive text-layout work adding a white frame.
  The long panel is now cached during white and all three small state labels are
  prepared before presentation. Display frame warnings remain recorded and
  visible in the final panel; test-workstation rendering jitter is not hidden.
  Final measured white flip intervals were 497.4168–501.2010 ms at 60.1234 Hz;
  five presentations carried a frame warning somewhere in their fixed visual
  timeline. Every white presentation had 30 drawn frames. These are host display
  diagnostics and do not establish physical optical durations.
- Smoke data/evidence and the rendered results image are under ignored
  `.cache/opto_diagnostic_smoke/`. The image is read from this utility's own
  backbuffer so it cannot capture other applications covering the shared desktop.
  A default monitor warning is expected. No new dependencies were installed.
- Actual T-Pad detection, timer-reply ordering/latency, optical scanout/thresholds,
  and physiological TTL remain unverified. The smoke does not connect to the
  T-Pad and cannot establish sensor or EEG acceptance.

PO clarification verification:

- Full suite: 52 tests passed, including the replacement test asserting only
  white/black phases, 500 ms white duration, and independence from button events.
- The GUI smoke now fails if the original colored stimulus or fixation is drawn.
  It retains the explicit synthetic serial guard and ten-pulse analysis checks.
  The updated smoke passed: ten marker-only pulses, 30 white frames each at
  59.9809 Hz, white flip intervals 499.8541–502.2521 ms, and no white-phase frame
  warnings. Ten full synthetic pulses and one additional 2 ms activation were
  correctly reported. This remains simulated serial evidence, not hardware validation.
- Compilation and CLI checks passed. The latest evidence is in ignored
  `.cache/opto_diagnostic_smoke/evidence.json` and its timestamped session folder.
- Simon and M2 calibration source, shared serial/trial code, configuration,
  environment, and dependency pins remain unchanged. The launch command is the same.

Resume M2B in the repository:

```powershell
.\.venv\Scripts\python.exe opto_diagnostic.py
.\.venv\Scripts\python.exe opto_diagnostic.py --port COM5 --windowed
.\.venv\Scripts\python.exe tests\smoke_opto_diagnostic.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Close the M2 calibration window and disconnect/close BBTK first: the diagnostic
needs exclusive ownership of the configured port. It does not adjust sensitivity.
The PO now reports 10/10 real pulses. On a new PC, repeat M2B, retain its output,
and investigate
short activations, missing/ambiguous/unpaired events, nominal duration deviations,
and all frame warnings. Full-screen physical/EEG qualification remains separate.

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

Complete the P2 physical acceptance checks above before interpreting demo RTs.
P1 button validation is PO-reported complete. For the original Simon task on each new PC, repeat
docs/HARDWARE_VALIDATION.md and retain actual session IDs/raw logs
and display/timing/abort evidence. Preserve the PO's reported laboratory successes;
next qualify saved BioSemi BDF events/timing, physical marker scanout and the
OpenBCI cable/input interface before use. Implement the optical artifact-selection
policy only under a separately authorized scientific change.

## Exact commands to resume

```powershell
Set-Location 'C:\Users\pruggeri\Documents\EXPERIMENTS\GABRIEL_PAOLO'
git status --short --branch
git log -1 --format='%H %s'
git remote -v
git ls-remote origin refs/heads/feature/standalone-tpad-listener
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_windows.ps1 -VerifyOnly
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe simon_demo_psychopy.py --port COM5 --windowed
.\.venv\Scripts\python.exe run_simon.py --gui-smoke
.\.venv\Scripts\python.exe run_simon.py --windowed
```

For the full-screen behavioral session, move the sensor to the full-screen marker:

```powershell
.\.venv\Scripts\python.exe run_simon.py
```

For a new PC, follow docs/INSTALL_ON_NEW_PC.md and run setup_windows.ps1. For
an existing environment use setup_windows.ps1 -VerifyOnly. Confirm private
origin/main with `git remote -v` and `git ls-remote origin refs/heads/main`.
Never install into global Python or an existing PsychoPy environment.
