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

## Deferred work

Real device/optical acceptance comes next. Electrical TTL interface qualification
and recorded EEG trigger verification follow separately. HID redundancy,
counterbalanced mappings, larger study designs, and derived EEG condition codes
need new product decisions; none are represented as completed features.
