# Architectural decisions

The PO supplied the initial implementation instructions. The following decisions
are approved constraints, not suggestions to reinterpret in future sessions.

| Decision | Implementation |
| --- | --- |
| PO-001: hardware TTL | Physical events use automatic T-Pad output. No command echoes an event into a software trigger. Electrical/EEG qualification remains separate. |
| PO-002: hardware scientific time | Original integer milliseconds are retained. RT subtracts Opto 1 ON from the eligible button press. Host times diagnose rendering and arrival only. |
| PO-003: Mode 5 | Setup enters command mode, reads firmware, and enters Mode 5 once. No explicit timer reset and no repeated mode entry during trials. |
| PO-004: standard keyboard | Space/Return navigate. Escape saves and exits. Serial Button 1/2 presses are the only behavioral response source. |
| PO-005: future HID | No current HID response path. Keep operator navigation separate from the serial reader. Any future HID channel must correlate to serial identity without double counting or substituting timestamps. |

## Small implementation choices

- Use three responsibility-specific modules, two small acquisition data classes,
  one trial data class, and simple reader/output/presentation helpers.
- Use standard-library `unittest`; tests need neither PsychoPy import nor hardware.
- Balance color/side separately in practice and experiment. Shuffle with a local
  seeded RNG. Save both the seed and full trial plan.
- Use timeout-zero reads of at most 4096 bytes per poll. Preserve every RX chunk,
  raw line, and fragment. No serial input reset/flush at trial boundaries.
- Identify exact repeated events by channel, edge, sensor, and hardware timestamp.
  Retain them but do not count them twice. Track held inputs to reject repeated
  presses without intervening release.
- Use read-only hardware timer samples around trials. Timestamp intervals and
  wire sequence preserve trial identity when an optical onset is missing. If
  firmware does not provide reliable timer replies/order, stop and investigate;
  do not fall back to host timestamps or ordinal pairing of optical events.
- Follow the fixed frame timeline with a black interval and bounded grace.
  Recompute summaries from retained events at checkpoints and shutdown.
  Arrivals beyond a previous grace remain auditable but invalidate its result.
- Keep scientific eligibility tied to optical onset even when marker scanout
  delays it relative to a host flip. Do not use receipt time to end the stimulus.
- Require both optical ON and OFF and a plausible duration. No-response trials
  can be valid omissions; missing optics and incomplete acquisition cannot.
- Conservatively invalidate regressions in wire-event timestamps. If firmware
  smoothing corrections explain such regressions, retain raw values and require
  an evidence-based revision rather than automatically correcting/reordering.
- Pin the Windows Python 3.11.9 environment after dependency and GUI checks.
  Do not reuse or alter the existing PsychoPy 2023.1.3 installation.
- Keep session data and virtual environments out of Git. Local commits only,
  using the PO-provided repository-specific identity.

## Primary references reviewed

[T-Pad v1 User Guide](https://www.blackboxtoolkit.com/docs/pdf/TPadv1r1.pdf),
revision RC1 dated 2025-09-11: sections 11.9, 12.2, 13, 14, 17, and 19 were
reviewed before implementation. Section 17 documents the `T` timer query and
command separation; setup waits on black screens between commands. Sections
11.9/12.2 establish Mode 5 event semantics. The guide's section 13 contains an
inconsistent optical ON example using `R` while its explanation describes `P`;
this implementation uses the PO's approved `P=ON`, `R=OFF` semantics and requires
physical confirmation. Section 14's example has blocking/reset details that are
not adopted because the approved architecture requires uninterrupted rendering.

[PsychoPy installation documentation](https://psychopy.org/download.html)
documents Python 3.11 support beginning with PsychoPy 2026.2.0 and library-only
installation. Installed version 2026.2.4 passed the local display smoke test.

## M2: standalone optical calibration patch (PO request, 2026-10-15)

- Add `calibrate_opto.py` as a standalone visual utility. It does not import the
  Simon runner, open serial, set a device mode, reset a timer, send TTL, adjust
  sensitivity, or launch the experiment. The operator uses the separate BBTK app
  for sensitivity calibration; that application must have exclusive serial access.
- Explicitly use the Simon marker's `rgb` endpoints: black `(-1, -1, -1)` and
  white `(1, 1, 1)`. Preserve pyglet, pixel coordinates, black window background,
  synchronized flips, and default color/gamma pipeline. Read the existing
  configured display index/window size; force windowed presentation only here.
- Use calibrated monitor width/resolution for geometry when an unambiguous,
  non-default profile matches the display. Do not trust the existing default
  `testMonitor` data. Otherwise require ruler confirmation or measured px/cm.
  Profiles are read only, and gamma is not taken from them. Scale is local to the
  run; moving monitors or changing resolution/scaling requires rechecking it.
- Anchor each ten-second phase to its actual flip and schedule transitions on
  subsequent refreshes, without sleeps or focus-based pauses. These are host
  display-control times, never scientific Simon RT or hardware measurements.
  Finite refresh timing and compositor latency prevent a physical exactness claim.
- Keep text, outline, and cursor outside the sensor's patch area. Prevent patch
  placement from overlapping the instruction panel; lock placement while running.
  Windows topmost z-order keeps the window visible while BBTK has keyboard focus,
  without persistent system settings or global keyboard hooks.
- The utility supplies a fixed sequence, not a BBTK calibration handshake. Follow
  the independent-patch workflow in section 5 of the
  [official guide](https://www.blackboxtoolkit.com/docs/pdf/TPadv1r1.pdf), coordinating
  prompts manually. Successful sensitivity calibration requires operator/device
  evidence; the completion message confirms the visual sequence only.

## M2B: optical timing diagnostic (PO request, 2026-10-15)

- After the PO's clarification on 2026-10-15, this is a marker-only transition
  diagnostic: ten cycles of 500 ms white and 500 ms black. No colored stimulus,
  fixation, or response window is drawn or scheduled. This supersedes the initial
  reuse of the full Simon timeline in commit `75aa940`.
- Reuse `Presentation` for marker geometry/display setup and serial/keyboard
  acquisition, plus `events_for_trial` for hardware boundaries. The diagnostic's
  simple `present_pulse` loop draws only white/black and uses a small timing-only
  `PulsePresentation` record. The Simon task, calibration utility, shared serial
  reader, configuration, and dependencies remain unchanged. The optical marker
  retains Simon's dimensions/position/colors, rather than M2's 4 cm geometry.
- Poll throughout the black interval, query its hardware boundary, and checkpoint
  on black. Query/saving overhead may extend black but never controls white offset.
  Add a final black grace interval to collect late messages after pulse ten.
- Enter Mode 5 once after the first Space; keep the connection and clock across
  repetitions. Keep only the existing command allowlist. Read-only hardware timer
  boundaries associate pulses without ordinal event matching or clock mixing.
- Pair original integer Opto 1 edges in wire order. Repeated ON before OFF makes
  the group unpaired/ambiguous until an OFF restores synchronization. Preserve
  duplicates without counting them twice. A pair of any nonnegative hardware
  duration is complete; lengths <= a configurable 10 ms default are classified
  as additional short activations and excluded from full-pulse timing averages.
- Report detected physical pairs separately from uniquely matched presentations.
  Multiple full pairs, orphan/crossed edges, late data, or unresolved acquisition
  prevent a confident scheduled match. A missing presentation never shifts
  subsequent identity. No duration tolerance is used to invent a match or onset.
- Duration statistics cover complete non-short pairs inside run bounds; onset
  intervals cover adjacent uniquely matched scheduled indices only. Use population
  SD. Timer regression invalidates timing statistics. Host times are rendering/
  arrival diagnostics only. No automatic hardware pass/fail is claimed.
- Cache the large panel during white; use compact numeric layout on black and a
  separate small live state label. The initial smoke exposed text-layout frame
  misses; the revised display avoids that white-duration interference. Preserve
  all frame warnings rather than concealing them in detection results.
- Keep four dedicated files under ignored `output/opto_diagnostics/`. Retain all
  repeats in one launch's files, with per-run summaries. Keep raw bytes and all
  optical events, including events outside scheduled windows, unpaired edges,
  and short activations. Checkpoint only on black screens and again on shutdown.

## Deferred work

Real device/optical acceptance comes next. Electrical TTL interface qualification
and recorded EEG trigger verification follow separately. HID redundancy,
counterbalanced mappings, larger study designs, and derived EEG condition codes
need new product decisions; none are represented as completed features.
