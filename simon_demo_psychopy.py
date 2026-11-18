"""Eight-trial teaching example: PsychoPy visuals and the standalone tPAD reader.

Read the parameters, trial plan, scoring, saving, then main() in that order.
PsychoPy schedules the screen; only the tPAD clock measures reaction time.
"""

import argparse
import base64
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import uuid

from tpad_listener import TPADListener


# 1. PARAMETERS: these are the few lines a researcher normally changes.
PORT = "COM5"
SEED = 20261118
COLOR_TO_BUTTON = {"red": 1, "blue": 2}  # B1 = physical LEFT; B2 = RIGHT.
# Confirm physical placement before starting; the script cannot detect it.
BUTTON_SIDE = {1: "left", 2: "right"}
FIXATION_MS = 500
STIMULUS_MS = 500
RESPONSE_WINDOW_MS = 1500
ITI_MS = 500
FINAL_COLLECTION_MS = 500
PATCH_ENABLED = True
PATCH_MS = 200
PATCH_SIZE_PX = 150
PATCH_MARGIN_PX = 20
FULL_SCREEN = True
WINDOW_SIZE = (1024, 768)
SCREEN = 0
STIMULUS_X_PX = 220
STIMULUS_RADIUS_PX = 50
# Conservative exclusion thresholds, NOT a measured sensor/transport calibration.
MAX_RECEIVE_DELAY_MS = 100
OPTICAL_DURATION_TOLERANCE_MS = 50
ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "output" / "simon_demo"


def make_trials(seed=SEED):
    """Shuffle two copies of the four conditions with a local, repeatable RNG."""
    conditions = [(color, side) for color in COLOR_TO_BUTTON for side in ("left", "right")] * 2
    random.Random(seed).shuffle(conditions)
    return [dict(trial_number=index, color=color, position=side,
                 congruency="congruent" if side == BUTTON_SIDE[COLOR_TO_BUTTON[color]] else "incongruent",
                 expected_response=COLOR_TO_BUTTON[color], started=False, completed=False,
                 timing_issue=False)
            for index, (color, side) in enumerate(conditions, 1)]


def score_trials(trials, records, timing, patch_enabled, session_complete):
    """Qualify the entire optical train before assigning any scientific RT.

    This receive-only example has no hardware timer-query boundaries. Therefore
    it needs ALL eight uniquely matched ON/OFF pairs, with bounded delivery near
    the corresponding flips. It never pairs the nth pulse with the nth trial.
    One missing/extra/late pair invalidates the train instead of shifting trials.
    Delivery limits and the sensor-to-stimulus alignment still need physical
    acceptance. Host nanoseconds below only check delivery, never calculate RT.
    """
    optical = [r for r in records if r.kind == "optical" and r.sensor == 1]
    delay_ns = MAX_RECEIVE_DELAY_MS * 1_000_000
    pairs = {}
    for trial in trials:
        flips = {row["transition"]: row for row in timing
                 if row["trial_number"] == trial["trial_number"] and row["transition"]}
        if "stimulus_onset" not in flips or "patch_offset" not in flips:
            continue
        pair = []
        for edge, transition in (("P", "stimulus_onset"), ("R", "patch_offset")):
            flip_ns = flips[transition]["flip_monotonic_ns"]
            candidates = [r for r in optical if r.edge == edge and r.rx_complete_ns is not None
                          and flip_ns <= r.rx_first_ns <= r.rx_complete_ns <= flip_ns + delay_ns]
            if len(candidates) == 1:
                pair.append(candidates[0])
        if len(pair) == 2:
            on, off = pair
            if (on.sequence < off.sequence and on.tpad_ms is not None and off.tpad_ms is not None
                    and abs(off.tpad_ms - on.tpad_ms - PATCH_MS) <= OPTICAL_DURATION_TOLERANCE_MS):
                pairs[trial["trial_number"]] = (on, off)

    # No deduplication: repeats remain records and make optical identity uncertain.
    matched = {r.sequence for pair in pairs.values() for r in pair}
    train_ok = (len(trials) == 8 and len(pairs) == 8 and len(optical) == 16
                and len(matched) == 16 and matched == {r.sequence for r in optical})
    global_reasons = []
    if not patch_enabled:
        global_reasons.append("patch_disabled")
    if not session_complete:
        global_reasons.append("session_incomplete")
    if not train_ok:
        global_reasons.append("optical_train_missing_ambiguous_or_late")
    if any(r.out_of_order for r in records):
        global_reasons.append("hardware_time_regression")
    if any(r.kind in ("malformed", "incomplete") for r in records):
        global_reasons.append("damaged_or_incomplete_acquisition")

    # Keep held/repeated presses visible and exclude them rather than silently
    # treating a repeated press as a new response. Release all buttons at start.
    held = set()
    repeated = set()
    for record in records:
        if record.kind == "button" and record.button in COLOR_TO_BUTTON.values():
            if record.state == "press":
                if record.button in held:
                    repeated.add(record.sequence)
                held.add(record.button)
            elif record.state == "release":
                held.discard(record.button)

    for trial in trials:
        reasons = list(global_reasons)
        trial.update(actual_response=None, accuracy=None, optical_onset_ms=None,
                     button_ms=None, rt_ms=None, hardware_rt_valid=False, outcome="invalid")
        if not trial["completed"]:
            reasons.append("trial_incomplete")
        if trial["timing_issue"]:
            reasons.append("visual_frame_delay")
        pair = pairs.get(trial["trial_number"])
        if pair:
            onset, _ = pair
            # Select by HARDWARE time across the retained stream, including ITI
            # arrivals. Same-ms presses preceding ON in wire order are anticipatory.
            eligible = [r for r in records if r.kind == "button" and r.state == "press"
                        and r.button in COLOR_TO_BUTTON.values() and r.tpad_ms is not None
                        and r.sequence > onset.sequence
                        and 0 <= r.tpad_ms - onset.tpad_ms <= RESPONSE_WINDOW_MS]
            if any(r.sequence in repeated for r in eligible):
                reasons.append("repeated_or_held_button_press")
            if any(r.rx_complete_ns is None or r.rx_complete_ns > trial.get("collection_end_ns", 0)
                   for r in eligible):
                reasons.append("response_received_after_trial_collection")
            if not reasons:
                trial["optical_onset_ms"] = onset.tpad_ms
                trial["accuracy"] = 0  # A qualified omission is not a correct trial.
                trial["outcome"] = "omission"
                if eligible:
                    response = eligible[0]  # First eligible B1/B2 PRESS in acquisition order.
                    trial.update(actual_response=response.button, button_ms=response.tpad_ms,
                                 rt_ms=response.tpad_ms - onset.tpad_ms, hardware_rt_valid=True,
                                 accuracy=int(response.button == trial["expected_response"]), outcome="response")
        trial["validity"] = "valid" if not reasons else "excluded"
        trial["exclusion_reason"] = ";".join(reasons)


def save_session(directory, metadata, trials, records, timing):
    """Write each output independently so one failed export does not skip others.

    Data are buffered during this short demo to keep disk I/O off timed frames.
    Finally calls this after Escape/errors. Power loss or forced termination is
    outside that guarantee. Raw payloads are exact bytes encoded as base64;
    delimiters and unread driver bytes are not supplied by TPADListener.
    """
    raw_rows = []
    for record in records:
        row = asdict(record)
        row["raw_base64"] = base64.b64encode(row.pop("raw")).decode("ascii")
        raw_rows.append(row)
    errors = []
    for name, rows in (("events.jsonl", raw_rows), ("trials.csv", trials),
                       ("timing.csv", timing), ("session.json", metadata)):
        try:
            with (directory / name).open("w", encoding="utf-8", newline="") as handle:
                if name == "events.jsonl":
                    for row in rows:
                        handle.write(json.dumps(row) + "\n")
                elif name == "session.json":
                    json.dump(rows, handle, indent=2)
                    handle.write("\n")
                elif rows:
                    columns = list(dict.fromkeys(key for row in rows for key in row))
                    writer = csv.DictWriter(handle, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)
        except OSError as error:
            errors.append(f"{name}: {error}")
    if errors:
        raise OSError("; ".join(errors))


def main(argv=None):
    # 2. SESSION SETUP: arguments override just port, display mode, seed and patch.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--windowed", action="store_true")
    parser.add_argument("--no-patch", action="store_true")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)
    patch_enabled = PATCH_ENABLED and not args.no_patch
    directory = OUTPUT_ROOT / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ_") + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)  # Never reuse an existing session.
    trials = make_trials(args.seed)
    records, timing = [], []
    metadata = dict(started_utc=datetime.now(timezone.utc).isoformat(), status="initializing",
                    port=args.port, seed=args.seed, git_commit="unknown", errors=[],
                    parameters={name: value for name, value in globals().items()
                                if name.isupper() and isinstance(value, (str, int, float, bool, tuple, dict))})
    metadata["parameters"].update(PORT=args.port, SEED=args.seed, PATCH_ENABLED=patch_enabled,
                                 FULL_SCREEN=FULL_SCREEN and not args.windowed)
    metadata["hardware_rt_policy"] = "Complete unique eight-pulse train; delivery/optical limits require physical acceptance."
    win = listener = None
    exit_code = 0
    print(f"Session output: {directory}", flush=True)
    try:
        revision = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
                                  cwd=ROOT, capture_output=True, text=True, timeout=5, check=False)
        if revision.returncode == 0:
            metadata["git_commit"] = revision.stdout.strip()
        # Keep PsychoPy preferences local to this process/project, as in run_simon.
        cache = ROOT / ".cache"
        (cache / "roaming").mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.environ["APPDATA"] = str(cache / "roaming")
        os.environ["MPLCONFIGDIR"] = str(cache / "matplotlib")
        os.environ["PSYCHOPYNOPACKAGES"] = "1"
        from psychopy import event, visual  # Delayed import keeps --help hardware/GUI-free.

        win = visual.Window(size=WINDOW_SIZE, fullscr=FULL_SCREEN and not args.windowed,
                            screen=SCREEN, units="pix", color=(-1, -1, -1), colorSpace="rgb",
                            winType="pyglet", waitBlanking=True, allowGUI=args.windowed, autoLog=False)
        width, height = map(int, win.size)  # PsychoPy may return NumPy integers.
        patch_position = (-width / 2 + PATCH_MARGIN_PX + PATCH_SIZE_PX / 2,
                          -height / 2 + PATCH_MARGIN_PX + PATCH_SIZE_PX / 2)
        if (PATCH_SIZE_PX + 2 * PATCH_MARGIN_PX >= min(width, height)
                or STIMULUS_X_PX + STIMULUS_RADIUS_PX >= width / 2
                or patch_position[1] + PATCH_SIZE_PX / 2 >= -STIMULUS_RADIUS_PX - 50):
            raise ValueError("Patch and stimulus must fit the display with separate areas.")
        metadata["display"] = dict(size=[width, height], patch_position=patch_position)
        stimulus = visual.Circle(win, radius=STIMULUS_RADIUS_PX, lineColor=None, autoLog=False)
        fixation = visual.TextStim(win, text="+", height=32, color="white", autoLog=False)
        patch = visual.Rect(win, width=PATCH_SIZE_PX, height=PATCH_SIZE_PX, pos=patch_position,
                            colorSpace="rgb", fillColor=(-1, -1, -1), lineColor=None, autoLog=False)
        instructions = visual.TextStim(win, height=24, pos=(0, 80), wrapWidth=width - 160,
                                      text="Respond to COLOR, ignore POSITION.\nRED: B1 (left)   BLUE: B2 (right)\n"
                                           "Confirm button placement and release all buttons.\n"
                                           "Position Opto 1 over the lower-left 150 px patch.\n"
                                           "Space/Return starts eight trials. Escape saves and exits.",
                                      color="white", autoLog=False)
        refresh_hz = win.getActualFrameRate(nIdentical=20, nMaxFrames=180, nWarmUpFrames=30)
        if refresh_hz is None or not math.isfinite(refresh_hz) or refresh_hz <= 0:
            raise RuntimeError("No stable measured refresh rate; check the display before collecting data.")
        refresh_hz = float(refresh_hz)
        metadata["refresh_hz"] = refresh_hz
        # Durations are rounded to WHOLE FRAMES, never ended by a response.
        frame_counts = {name: max(1, round(value * refresh_hz / 1000)) for name, value in
                        (("fixation", FIXATION_MS), ("stimulus", STIMULUS_MS),
                         ("response", RESPONSE_WINDOW_MS), ("patch", PATCH_MS),
                         ("iti", ITI_MS), ("final_collection", FINAL_COLLECTION_MS))}
        metadata["frame_counts"] = frame_counts
        fixation_frames, response_frames = frame_counts["fixation"], frame_counts["response"]
        trial_frames = fixation_frames + response_frames + frame_counts["iti"]

        # TPAD INTEGRATION 1/3 — INITIALIZATION, exactly once before trials.
        # The existing listener owns the Mode 0/Mode 5 handshake. No commands,
        # timer resets or software TTL writes are added by this experiment.
        listener = TPADListener(args.port)
        while True:
            records.extend(listener.poll())  # Also preserve setup/early records.
            keys = event.getKeys(keyList=["escape", "space", "return"])
            if "escape" in keys:
                raise KeyboardInterrupt("Escape pressed during instructions")
            instructions.draw()
            if patch_enabled:
                patch.draw()
            win.flip()
            if "space" in keys or "return" in keys:
                break

        metadata["status"] = "running"
        first_flip = previous_flip = None
        global_frame = 0
        # 3. EXPERIMENT: a fixed frame timeline, independent of all responses.
        for trial in trials:
            stimulus.fillColor = trial["color"]
            stimulus.pos = (-STIMULUS_X_PX if trial["position"] == "left" else STIMULUS_X_PX, 0)
            for frame in range(trial_frames):
                # TPAD INTEGRATION 2/3 — POLLING DURING EVERY TRIAL PHASE.
                # A full batch is retained before doing anything else. No raw
                # event is debounced, suppressed, reordered, or used to end a phase.
                records.extend(listener.poll())
                if "escape" in event.getKeys(keyList=["escape"]):
                    raise KeyboardInterrupt("Escape pressed during trials")
                since_onset = frame - fixation_frames
                visible = 0 <= since_onset < frame_counts["stimulus"]
                white = patch_enabled and 0 <= since_onset < frame_counts["patch"]
                if frame < fixation_frames:
                    phase = "fixation"
                    fixation.draw()
                elif visible:
                    phase = "stimulus"
                    stimulus.draw()
                elif since_onset < response_frames:
                    phase = "response_wait"
                else:
                    phase = "iti"
                if patch_enabled:
                    patch.fillColor = (1, 1, 1) if white else (-1, -1, -1)
                    patch.draw()
                transition = {0: "fixation_onset", fixation_frames: "stimulus_onset",
                              fixation_frames + frame_counts["stimulus"]: "stimulus_offset",
                              fixation_frames + response_frames: "response_deadline"}.get(frame, "")
                if patch_enabled and since_onset == frame_counts["patch"]:
                    transition = "patch_offset"
                row = dict(trial_number=trial["trial_number"], frame=frame, phase=phase,
                           transition=transition, stimulus_visible=visible, patch_white=white)
                # Capture a PC monotonic stamp ON the flip, on the same host
                # clock used by listener receipt diagnostics. Hardware RT never
                # subtracts either this stamp or the PsychoPy flip timestamp.
                win.callOnFlip(lambda stamp=row: stamp.update(flip_monotonic_ns=time.monotonic_ns()))
                row["flip_psychopy_s"] = win.flip()
                if first_flip is None:
                    first_flip = row["flip_psychopy_s"]
                row["planned_psychopy_s"] = first_flip + global_frame / refresh_hz
                row["deviation_ms"] = 1000 * (row["flip_psychopy_s"] - row["planned_psychopy_s"])
                row["interval_ms"] = None if previous_flip is None else 1000 * (row["flip_psychopy_s"] - previous_flip)
                row["frame_delayed"] = row["interval_ms"] is not None and row["interval_ms"] > 1500 / refresh_hz
                trial["timing_issue"] |= row["frame_delayed"]
                if frame == 0:
                    trial["started"] = True
                    if trial["trial_number"] > 1:
                        previous = trials[trial["trial_number"] - 2]
                        previous["collection_end_ns"] = row["flip_monotonic_ns"]
                        previous["timing_issue"] |= row["frame_delayed"]
                timing.append(row)
                previous_flip = row["flip_psychopy_s"]
                global_frame += 1
                records.extend(listener.poll())  # Collect promptly after the flip, too.
            trial["completed"] = True

        # The last ITI ends on this first black flip. Keep polling through a
        # fixed final grace, so the last trial does not lose late-delivered data.
        for frame in range(frame_counts["final_collection"] + 1):
            records.extend(listener.poll())
            if "escape" in event.getKeys(keyList=["escape"]):
                raise KeyboardInterrupt("Escape pressed during final collection")
            row = dict(trial_number=8, frame=trial_frames + frame, phase="final_collection",
                       transition="iti_end" if frame == 0 else "", stimulus_visible=False, patch_white=False)
            if patch_enabled:
                patch.fillColor = (-1, -1, -1)
                patch.draw()
            win.callOnFlip(lambda stamp=row: stamp.update(flip_monotonic_ns=time.monotonic_ns()))
            row["flip_psychopy_s"] = win.flip()
            row["planned_psychopy_s"] = first_flip + global_frame / refresh_hz
            row["deviation_ms"] = 1000 * (row["flip_psychopy_s"] - row["planned_psychopy_s"])
            row["interval_ms"] = 1000 * (row["flip_psychopy_s"] - previous_flip)
            row["frame_delayed"] = row["interval_ms"] > 1500 / refresh_hz
            if frame == 0:
                trials[-1]["timing_issue"] |= row["frame_delayed"]
            timing.append(row)
            previous_flip = row["flip_psychopy_s"]
            global_frame += 1
            records.extend(listener.poll())
        trials[-1]["collection_end_ns"] = row["flip_monotonic_ns"]
        metadata["status"] = "completed"
    except KeyboardInterrupt as error:
        metadata.update(status="interrupted")
        metadata["errors"].append(str(error) or "Ctrl+C")
        exit_code = 130
    except Exception as error:
        metadata.update(status="error")
        metadata["errors"].append(f"{type(error).__name__}: {error}")
        exit_code = 1
    finally:
        # TPAD INTEGRATION 3/3 — CLEANUP, even on Escape or a serial/display error.
        # close() releases the port and returns undelivered records/fragments.
        # A second call can recover its tail if the first port close itself fails.
        if listener is not None:
            for attempt in range(2):
                try:
                    records.extend(listener.close())
                    break
                except Exception as error:
                    metadata["errors"].append(f"tPAD cleanup: {error}")
                    metadata["status"], exit_code = "error", 1
        if win is not None:
            try:
                win.close()  # Releases the display; do not call core.quit() before saving.
            except Exception as error:
                metadata["errors"].append(f"Window cleanup: {error}")
                metadata["status"], exit_code = "error", 1
        score_trials(trials, records, timing, patch_enabled, metadata["status"] == "completed")
        metadata.update(ended_utc=datetime.now(timezone.utc).isoformat(), received_records=len(records),
                        completed_trials=sum(t["completed"] for t in trials))
        save_session(directory, metadata, trials, records, timing)
    print(f"Session {metadata['status']}; saved {len(records)} records to {directory}", flush=True)
    for error in metadata["errors"]:
        print(error, file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
