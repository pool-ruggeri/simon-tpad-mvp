# Install and run on another Windows PC

Repository: [pool-ruggeri/simon-tpad-mvp](https://github.com/pool-ruggeri/simon-tpad-mvp)
(private). Use branch `main` and record the exact commit for every laboratory run.

This guide transfers the existing MVP. It does not qualify a new computer,
display, electrical interface, or EEG recording chain for scientific use.

## 1. Obtain the project and prerequisites

Use Windows 10 or Windows 11 **x64**, Windows PowerShell 5.1 or later, and an
ordinary user account with a writable project folder. The reference PC runs
Windows 10 build 19045; Windows 11 and a second physical PC have not been tested.
Other operating systems, ARM64, and 32-bit Python are outside this deployment.

Install these prerequisites through your laboratory's approved process if absent:

- [Git for Windows](https://git-scm.com/download/win), including Git Credential Manager.
- [CPython 3.11.9](https://www.python.org/downloads/release/python-3119/), using the
  **Windows installer (64-bit)** and Python launcher. A per-user installation is
  sufficient. This exact patch version reproduces the reference environment;
  setup rejects other Python versions rather than changing them.
- A working graphics driver/OpenGL desktop for PsychoPy. Compiled Python wheels
  may need the [Microsoft Visual C++ x64 runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).
  If a DLL/import check fails, ask laboratory IT to supply the missing system
  runtime. Setup does not install drivers, runtimes, compilers, or firmware.
- For hardware acquisition, the T-Pad's [FTDI VCP driver](https://ftdichip.com/drivers/vcp-drivers/)
  and official BBTK Configuration & Test application. Obtain these separately
  from their vendors; they are not Python packages or distributed in this repo.

The private repository owner must grant your GitHub account access. Sign into
that account in your browser. Clone using HTTPS; Git Credential Manager can
open the browser for authentication. Follow [GitHub's authentication guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)
if prompted. Do not put a password/token in the URL, a script, or this repository.
Alternatively, if GitHub CLI is already installed, `gh auth login --web` can
authenticate before cloning. A private repository may appear as 404 when the
account is wrong or has no access.

In PowerShell, choose a writable parent folder, then:

```powershell
git clone --branch main https://github.com/pool-ruggeri/simon-tpad-mvp.git
Set-Location .\simon-tpad-mvp
git branch --show-current
git rev-parse HEAD
git status --short --branch
```

Expect `main` and a clean worktree. Compare the full revision to the laboratory's
approved deployment revision. Do not update the code during data collection.

## 2. Create the isolated Python environment

From the cloned folder:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_windows.ps1
```

This uses a process-local execution policy; it does not change persistent policy
or request administrator rights. If institutional policy blocks execution, use
the approved IT procedure or the manual commands below.

Setup checks CPython **3.11.9 x64**, creates `.venv`, installs the pinned packaging
tools and complete runtime lock, checks every pinned version, runs `pip check`,
imports all applications and PsychoPy's visual backend, checks their CLI help,
and runs hardware-free unit tests. It opens no window or serial port. Network
access to the package index and enough disk space for PsychoPy's dependencies
are required. The import check uses only project-local PsychoPy caches.

If Python is not registered with the launcher, give its actual path:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_windows.ps1 -PythonExe 'C:\path\to\Python311\python.exe'
```

An existing `.venv` is preserved. To check it without installing anything:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup_windows.ps1 -VerifyOnly
```

Never copy `.venv` between computers or clones. Each clone needs its own freshly
created environment. Activation is unnecessary; use the explicit interpreter.

Manual fallback, only in this clone, with no existing `.venv`:

```powershell
py -0p
py -3.11-64 -c "import sys, struct; assert sys.version_info[:3] == (3, 11, 9) and struct.calcsize('P') == 8; print(sys.version)"
py -3.11-64 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-bootstrap.txt
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import calibrate_opto; calibrate_opto.load_psychopy(); import run_simon, opto_diagnostic, serial; print('Application and PsychoPy imports passed')"
.\.venv\Scripts\python.exe run_simon.py --help
.\.venv\Scripts\python.exe calibrate_opto.py --help
.\.venv\Scripts\python.exe opto_diagnostic.py --help
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Stop at any failed command. For an interrupted setup that left `.venv`, inspect
the original error, then retry the two pip commands and `-VerifyOnly` above;
do not install into global Python. Do not unpin packages to hide a resolver error.
`requirements.txt` lists the two direct dependencies; the full installation uses
`requirements-lock.txt`. `requirements-bootstrap.txt` pins the reference pip,
setuptools, and wheel separately. Package versions are pinned, not file hashes;
this is not a cryptographically locked or bundled offline distribution.

## 3. Connect the T-Pad and select the actual COM port

Connect the T-Pad's **Serial USB** lead. Keyboard HID is unnecessary for this MVP.
In Windows Device Manager, inspect **Ports (COM & LPT)**; identify the T-Pad's
USB Serial Port by unplugging/replugging its serial lead while all applications
are closed. You can also list ports without opening them:

```powershell
.\.venv\Scripts\python.exe -m serial.tools.list_ports -v
```

COM5 is the reference PC's example, not a portable assumption. The existing
`--config` option accepts a complete JSON configuration. Create the local copy:

```powershell
Copy-Item .\config.json .\local_config.json
notepad .\local_config.json
```

Change only `"serial_port": "COM5"` to the identified port, for example
`"serial_port": "COM7"`. Save as UTF-8 without BOM. Keep the other fields; this
file is a complete configuration, not a partial override. It is ignored by Git.
Do not overwrite an existing local configuration when repeating these steps.
Both serial applications accept `--config local_config.json`. The diagnostic
also has `--port COM7` for a one-launch override. No application code change is
needed to select another port.

For this T-Pad protocol, the reference driver latency is **1 ms**. Before timing
work, have the authorized hardware operator check Device Manager → USB Serial
Port → Properties → Port Settings → Advanced → Latency Timer (msec), and set
1 ms where that FTDI driver supports it. Check latency in the BBTK app as well.
This is a manual system prerequisite; no project script changes it. The
[T-Pad guide, section 17](https://www.blackboxtoolkit.com/docs/pdf/TPadv1r1.pdf)
specifies the latency and **115200 baud, 8 data bits, no parity, 1 stop bit**.
The application uses those serial settings with no flow control and nonblocking
reads; the Device Manager COM name must match the chosen configuration.

The expected firmware is **20250809**. The applications query `FIRM`, check its
reply, and enter **Mode 5 once** at operator-started setup. Expect a flashing
green mode indicator. They use XiD hardware timestamps and read-only `T` queries;
there is no trial-time clock reset or software TTL path. If firmware differs,
stop and investigate; do not flash firmware or change the expected value simply
to suppress the check.

Only one program may own the serial port. BBTK needs it for sensitivity
calibration; Simon and the diagnostic need it for acquisition. Disconnect/close
BBTK, terminals, and other serial programs before starting either Python
acquisition application. Run only one acquisition application at a time.

## 4. Calibrate Opto 1 on the target monitor

```powershell
.\.venv\Scripts\python.exe calibrate_opto.py
```

This helper never opens serial or changes the T-Pad. If there is no unambiguous,
reliable monitor profile, use a physical ruler and Left/Right to make **both
sides 4 cm**, measuring between opposite outline centers; Return confirms the
scale. Click below the instructions to place the initially black patch, and click
again to reposition it. SPACE toggles black/white and holds the selected color;
there is no timer. Focus this window for SPACE or ESC. The window remains visible
when BBTK has focus, and the sensor must stay inside the patch, clear of its outline.

If physical scaling was actually measured, use `--pixels-per-cm VALUE`; an example
number is not a calibration. `--monitor NAME` selects a matching existing profile
for geometry only. Recheck both dimensions on every new monitor or change in
resolution/DPI scaling. Recheck sensitivity after brightness/contrast changes.
Keep the patch window on the display whose size you measured.

With the serial port free, connect in BBTK's official application and use its
external-patch sensitivity workflow, **Adj. To Another Device**, described in
[section 5 of the T-Pad guide](https://www.blackboxtoolkit.com/docs/pdf/TPadv1r1.pdf).
Follow its command-mode and black/white prompts. Switch focus to the patch and
press SPACE when the requested color changes, then return to BBTK to acknowledge
the prompt. Save sensitivity through BBTK if appropriate. There is no handshake
or calibration-success report from this helper. Close the patch and disconnect/
close BBTK before the diagnostic.

## 5. Verify optical timing

Use the actual COM port through the local configuration:

```powershell
.\.venv\Scripts\python.exe opto_diagnostic.py --config .\local_config.json --windowed
```

Or use the diagnostic's existing one-launch port override:

```powershell
.\.venv\Scripts\python.exe opto_diagnostic.py --port COM7 --windowed
```

Place Opto 1 on the outlined lower-left preview, then SPACE starts **ten white
pulses of nominally 500 ms**, separated by black intervals of at least nominally
500 ms. Only the marker changes color. Queries/checkpoints may extend black;
responses never change the visual schedule. SPACE repeats; ESC saves and exits.
Move the sensor and repeat with full-screen settings before a full-screen task.
The diagnostic/task marker is an **80 px** square by default, not the 4 cm
calibration patch. Retain the same display conditions used for calibration.

Inspect the on-screen summary and
`output/opto_diagnostics/<session_id>/{serial_raw.jsonl,optical_events.csv,pulses.csv,summary.json}`.
Compare expected ten presentations with detected full pairs and uniquely matched
presentations. Review missing/ambiguous matches, unpaired ON/OFF edges, unmatched
full pulses, extra short activations, and frame/acquisition warnings. Raw events
are retained. Activations of **10 hardware ms or less** are counted separately
by default (`--short-pulse-ms` changes that recorded threshold). A full pair is
not automatically a scientific acceptance result. Timing statistics use device
milliseconds; host flip times do not substitute for optical measurements.

## 6. Run the Simon Task

First check display startup without hardware:

```powershell
.\.venv\Scripts\python.exe run_simon.py --gui-smoke
```

For an operator check, then a full-screen session:

```powershell
.\.venv\Scripts\python.exe run_simon.py --config .\local_config.json --windowed
.\.venv\Scripts\python.exe run_simon.py --config .\local_config.json
```

Run these one at a time. Position Opto 1 completely inside the lower-left marker,
moving it when switching window/full-screen geometry. PC SPACE/Return advances
instructions and starts blocks. Respond to **blue with T-Pad Button 1 (left)**
and **yellow with Button 2 (right)** regardless of stimulus side. The default
protocol has **4 practice and 16 experimental trials**, balanced by color/side.
All four physical buttons are logged; Buttons 3/4 do not count as task responses.
PC keys are navigation/abort controls, not scientific response inputs.

ESC aborts safely and preserves acquired data; errors also trigger saving. Normal
completion exits through the final instruction screen. Each run prints a unique
`results/<session_id>/` folder containing:

| File | Purpose |
| --- | --- |
| `trials.csv` | Conditions, responses/accuracy, hardware RT, validity and flags. |
| `events.csv` | Parsed physical events, including all buttons, releases and extra edges. |
| `serial_raw.jsonl` | Original byte chunks, messages, commands, fragments and errors. |
| `session.json` | Configuration, firmware/mode, seed/plan, software revision and lifecycle. |

Use valid trials for RT analysis and retain every raw file. A handled abort is
covered; sudden power/disk failure or forced termination can lose buffered data.
Store participant/session/EEG data only in approved data storage, never in Git.
Generated results/output, recordings and archives are ignored by this repository.

**Optical-artifact policy status:** the PO approved selecting the first complete,
correctly timed pulse while retaining later short activations as artifacts.
That policy is **not implemented in Simon scoring** at this revision. Simon
selects the first eligible ON but requires a single ON/OFF pair and invalidates
extra optical edges, with empty RT. The diagnostic separately counts short
activations and can match a single full pair; it does not change Simon scoring
or select the first of multiple full candidates. No scientific scoring change
was made for publication. Investigate flagged trials rather than claiming that
the approved artifact-selection policy is active.

## 7. Verify the physical TTL/EEG chain separately

Mode 5's tPAD outputs mark physical events directly; the PC does not generate or
echo TTL triggers. The PO reports repeated successful Simon sessions, four-button
serial acquisition, hardware RT checks, a **10/10** optical diagnostic, and TTL
activity visible in BioSemi ActiView. Those are laboratory reports, not a
fresh measurement during installation. **Saved BioSemi BDF event/timing validation
is pending.** Visual activity alone does not verify saved event counts, labels,
polarity, onset/offset timing, or alignment with the acquisition sample clock.

Before recording, follow [HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md). Have a
qualified operator check actual pinout, grounds, voltage levels, pulse widths,
polarity and simultaneous lines, then verify events in saved recordings against
retained device logs. Hardware lines do not encode arbitrary Simon trial IDs or
conditions. Marker/stimulus scanout differences also need physical measurement.

**The OpenBCI branch is unvalidated and must not be used before electrical
verification.** Identify the exact board/input and its limits. For Cyton trigger
inputs, the [official guide](https://docs.openbci.com/Cyton/CytonExternal/)
warns against signal amplitudes above **3.3 V**; the
[T-Pad product specifications](https://www.blackboxtoolkit.com/tpad.html) describe
5 V TTL outputs. Do not infer compatibility from connectors or cable labels.
Measure the actual split cable's level-conversion and isolation behavior, including
its output levels under load, polarity, ground paths, leakage/backfeed between
branches, and electrical isolation. A passive split is not a level shifter or
isolator. Require a documented compatible interface and saved-event tests before
use; no project script establishes those properties or changes the hardware.

## 8. Convenience scripts

These wrappers invoke this clone's `.venv` and forward the normal application
arguments; they work when called by full path from another directory:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\launch_calibration.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\launch_diagnostic.ps1 --port COM7 --windowed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\launch_simon.ps1 --config .\local_config.json
```

Relative argument paths such as `local_config.json` are relative to your current
PowerShell folder. Use an absolute path when invoking a wrapper from elsewhere.

## 9. Troubleshooting

| Problem | Action |
| --- | --- |
| GitHub 404/authentication failure | Confirm private-repo access and the correct GitHub account in Credential Manager; never embed a token in a clone URL. |
| Python unavailable/wrong version | Install the exact x64 prerequisite through the approved process, or pass its path with `-PythonExe`; setup will not replace it. |
| Missing packages/install failure | Retain the first pip error, check proxy/index access and available pinned versions, then use the manual pip commands and `-VerifyOnly`. A partial `.venv` is preserved. |
| PsychoPy/DLL/launch failure | Use this clone's `.venv`, inspect `-VerifyOnly` output, check the x64 runtime and graphics prerequisites with IT, and run `--gui-smoke` locally rather than assuming an RDP/headless desktop works. |
| COM port not found | Check the Serial USB lead, power and Device Manager/list_ports; update the local config or diagnostic `--port`. COM numbers can change between USB sockets/PCs. |
| COM port occupied/access denied | Disconnect/close BBTK, terminals and other acquisition applications; only one process can own it. |
| FTDI port/latency option missing | Have IT verify the vendor VCP driver and correct device identity; do not replace unrelated drivers or silently change global settings. |
| Firmware/mode check fails | Retain raw/startup logs, compare observed firmware to 20250809, and investigate with the lab lead. Do not flash or bypass the check. |
| Missing/extra optical events | Check sensor placement, display used for sensitivity calibration, brightness/contrast, white/black preview and raw ON/OFF data. Repeat the diagnostic; preserve artifacts and invalid trials. |
| Patch is not 4 cm | Remeasure both sides on the target monitor; account for DPI/resolution/profile mismatch. Default testMonitor geometry and example px/cm are not measurements. |
| SPACE does not switch the patch | Focus the calibration window; switching to BBTK leaves its color unchanged. Calibration must be confirmed and a patch placed first. |
| TTL visible but no verified saved event | Inspect the saved BioSemi BDF with an approved offline tool; qualify counts, labels and timing. ActiView visibility is not saved-file validation. |
| OpenBCI trigger uncertainty | Keep that branch unused until its voltage limits, actual adapter isolation/level conversion and saved events are verified. |

See [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) for exact software/portability evidence,
remaining limitations and resume commands. A passing setup is software evidence
on the tested computer, not full scientific or EEG qualification.
