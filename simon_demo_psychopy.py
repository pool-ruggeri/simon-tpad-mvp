"""A small Simon teaching task: PsychoPy schedules frames; tPAD timestamps measure RT."""

import argparse
import base64
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

from tpad_listener import TPADListener

# PARAMETERS: B1 must be physically LEFT and B2 RIGHT; confirm before starting.
PORT = "COM5"
SEED = 20261118
BUTTONS = {"red": 1, "blue": 2}
DURATIONS_MS = dict(fixation=500, stimulus=500, response=1500, iti=500, patch=100, final_collection=500)
PATCH_SIZE_PX = 150  # ZERO margin: its two outer edges touch the screen corner.
FULLSCREEN = True
WINDOW_SIZE = (1024, 768)  # Used for initial windowed checks; fullscreen uses the actual display.
ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "output" / "simon_demo"


def keep_events(batch, events, trial_number, phase):
    """Save every record unchanged, adding receipt context (not physical trial identity)."""
    for event in batch:
        row = asdict(event)
        row["raw_base64"] = base64.b64encode(row.pop("raw")).decode("ascii")
        row.update(receipt_trial=trial_number, receipt_phase=phase, association="unconfirmed")
        events.append(row)  # No sorting, deduplication, debounce or discarded records.


def save_files(directory, events, trials, timing, session):
    """Attempt all four files even if one fails; the directory is unique to this run."""
    errors = []
    for name, rows in (("events.jsonl", events), ("trials.csv", trials),
                       ("timing.csv", timing), ("session.json", session)):
        try:
            with (directory / name).open("w", encoding="utf-8", newline="") as handle:
                if name == "events.jsonl":
                    for row in rows:
                        handle.write(json.dumps(row) + "\n")
                elif name == "session.json":
                    json.dump(rows, handle, indent=2)
                else:
                    columns = list(dict.fromkeys(key for row in rows for key in row)) or ["trial_number"]
                    writer = csv.DictWriter(handle, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(rows)
        except OSError as error:
            errors.append(f"{name}: {error}")
    if errors:
        raise OSError("; ".join(errors))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=PORT)
    parser.add_argument("--windowed", action="store_true", help="Initial display checks; default is fullscreen")
    args = parser.parse_args(argv)
    directory = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    conditions = [(color, position) for color in BUTTONS for position in ("left", "right")] * 2
    random.Random(SEED).shuffle(conditions)
    trials = [dict(trial_number=i, color=color, position=position, expected_button=BUTTONS[color],
                   congruency="congruent" if (color, position) in (("red", "left"), ("blue", "right")) else "incongruent",
                   completed=False) for i, (color, position) in enumerate(conditions, 1)]
    events, timing = [], []
    session = dict(started_utc=datetime.now(timezone.utc).isoformat(), status="initializing", errors=[],
                   port=args.port, seed=SEED, parameters=DURATIONS_MS.copy(), buttons=BUTTONS,
                   patch_size_px=PATCH_SIZE_PX, patch_margin_px=0, fullscreen=FULLSCREEN and not args.windowed)
    win = tpad = None
    exit_code = 0
    print(f"Session output: {directory}", flush=True)
    try:
        revision = subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
                                  cwd=ROOT, capture_output=True, text=True, timeout=5)
        session["git_commit"] = revision.stdout.strip() if revision.returncode == 0 else "unknown"
        # Keep this process's PsychoPy preferences in the project, as in the original runner.
        (ROOT / ".cache" / "roaming").mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.environ["APPDATA"] = str(ROOT / ".cache" / "roaming")
        os.environ["PSYCHOPYNOPACKAGES"] = "1"
        os.environ["MPLCONFIGDIR"] = str(ROOT / ".cache" / "matplotlib")
        from psychopy import event, visual

        win = visual.Window(size=WINDOW_SIZE, fullscr=session["fullscreen"], units="pix", color="black",
                            winType="pyglet", waitBlanking=True, autoLog=False)
        width, height = map(int, win.size)
        patch_position = (-width / 2 + PATCH_SIZE_PX / 2, -height / 2 + PATCH_SIZE_PX / 2)
        session.update(window_size_px=[width, height], patch_position_px=patch_position)
        patch = visual.Rect(win, width=PATCH_SIZE_PX, height=PATCH_SIZE_PX, pos=patch_position,
                            fillColor="black", lineColor=None, autoLog=False)
        stimulus = visual.Circle(win, radius=50, lineColor=None, autoLog=False)
        fixation = visual.TextStim(win, text="+", color="white", height=32, autoLog=False)
        instructions = visual.TextStim(win, text="Respond to COLOR, ignore POSITION.\nRED = B1 (left); BLUE = B2 (right).\n"
                                      "Release all buttons. Space/Return starts; Escape saves and exits.",
                                      color="white", height=24, wrapWidth=width - 160, autoLog=False)
        refresh_hz = win.getActualFrameRate(nIdentical=20, nMaxFrames=180, nWarmUpFrames=30)
        if refresh_hz is None or not refresh_hz > 0:
            raise RuntimeError("Cannot measure a stable refresh rate.")
        frames = {name: max(1, round(ms * refresh_hz / 1000)) for name, ms in DURATIONS_MS.items()}
        session.update(refresh_hz=float(refresh_hz), frame_counts=frames)
        # A. TPAD INITIALIZATION: once; the listener provides the Mode 0/Mode 5 handshake.
        tpad = TPADListener(args.port)
        while True:
            keep_events(tpad.poll(), events, None, "instructions")
            keys = event.getKeys(keyList=["space", "return", "escape"])
            if "escape" in keys:
                raise KeyboardInterrupt("Escape")
            instructions.draw()
            patch.draw()
            win.flip()
            if "space" in keys or "return" in keys:
                break

        win.recordFrameIntervals = True  # PsychoPy records missed frames without changing the schedule.
        win.nDroppedFrames = 0
        for trial in trials:
            stimulus.fillColor = trial["color"]
            stimulus.pos = (-220 if trial["position"] == "left" else 220, 0)
            transitions = {0: "fixation_onset", frames["fixation"]: "stimulus_onset",
                           frames["fixation"] + frames["patch"]: "patch_offset",
                           frames["fixation"] + frames["stimulus"]: "stimulus_offset",
                           frames["fixation"] + frames["response"]: "response_deadline"}
            for frame in range(frames["fixation"] + frames["response"] + frames["iti"]):
                if "escape" in event.getKeys(keyList=["escape"]):
                    raise KeyboardInterrupt("Escape")
                elapsed = frame - frames["fixation"]
                if elapsed < 0:
                    phase = "fixation"
                    fixation.draw()
                elif elapsed < frames["stimulus"]:
                    phase = "stimulus"
                    stimulus.draw()
                elif elapsed < frames["response"]:
                    phase = "response_wait"
                else:
                    phase = "iti"
                patch.fillColor = "white" if 0 <= elapsed < frames["patch"] else "black"
                patch.draw()  # Circle and white patch first appear together on this flip.
                flip_s = win.flip()
                pc_ns = time.monotonic_ns()  # PC diagnostic only; never subtract from tPAD milliseconds.
                if frame == 0:
                    trial_start = flip_s
                if frame == frames["fixation"]:
                    trial["onset_pc_ns"] = pc_ns
                if frame in transitions:
                    timing.append(dict(trial_number=trial["trial_number"], phase=phase, frame=frame,
                                       transition=transitions[frame], flip_psychopy_s=flip_s,
                                       planned_psychopy_s=trial_start + frame / refresh_hz, pc_after_flip_ns=pc_ns))
                # B. EVENT ACQUISITION: nonblocking poll during EVERY phase, once per frame.
                # Each event.tpad_ms is the original hardware time. Keep the WHOLE batch.
                new_events = tpad.poll()
                keep_events(new_events, events, trial["trial_number"], phase)
            trial["completed"] = True  # Responses never skip a frame or end a trial early.
        for frame in range(frames["final_collection"] + 1):
            if "escape" in event.getKeys(keyList=["escape"]):
                raise KeyboardInterrupt("Escape")
            win.flip()  # Final black collection; late records stay unassigned, not forced into trial 8.
            keep_events(tpad.poll(), events, None, "final_collection")
        session["status"] = "completed"
    except KeyboardInterrupt as error:
        session["status"], exit_code = "interrupted", 130
        session["errors"].append(str(error) or "Ctrl+C")
    except Exception as error:
        session["status"], exit_code = "error", 1
        session["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        # C. TPAD CLEANUP: release the port and keep undelivered records/partial payloads.
        if tpad is not None:
            for attempt in range(2):  # Retry only to recover the tail if port close itself raises.
                try:
                    remaining_events = tpad.close()
                    keep_events(remaining_events, events, None, "cleanup")
                    break
                except Exception as error:
                    session["errors"].append(f"tPAD close: {error}")
                    session["status"], exit_code = "error", 1
        if win is not None:
            try:
                session["dropped_frames"] = int(win.nDroppedFrames)
                win.close()
            except Exception as error:
                session["errors"].append(f"Window close: {error}")
                session["status"], exit_code = "error", 1
        # Simple summaries use RECEIPT context, which cannot prove physical trial identity.
        # Accuracy uses the first B1/B2 press received in the nominal response window, even without optics.
        for trial in trials:
            received = [e for e in events if e["receipt_trial"] == trial["trial_number"]]
            presses = [e for e in received if e["kind"] == "button" and e["state"] == "press"
                       and e["button"] in (1, 2) and e["receipt_phase"] in ("stimulus", "response_wait")]
            response = presses[0] if presses else None
            optical = [e for e in received if e["kind"] == "optical" and e["sensor"] == 1]
            ons = [e for e in optical if e["edge"] == "P"]
            offs = [e for e in optical if e["edge"] == "R"]
            trial.update(response_button=response["button"] if response else None,
                         response_basis="nominal_window_receipt",
                         response_ms=response["tpad_ms"] if response else None,
                         accuracy=int(response["button"] == trial["expected_button"]) if response else (0 if trial["completed"] else None),
                         optical_on_ms=json.dumps([e["tpad_ms"] for e in ons]),
                         optical_off_ms=json.dumps([e["tpad_ms"] for e in offs]), pulse_duration_ms=None, rt_ms=None,
                         quality="missing/extra optical edges; association uncertain")
            if len(ons) == len(offs) == 1:
                on, off = ons[0], offs[0]
                trial["pulse_duration_ms"] = off["tpad_ms"] - on["tpad_ms"]
                associated = (on["receipt_phase"] == "stimulus" and off["receipt_phase"] in ("stimulus", "response_wait")
                              and on["rx_first_ns"] >= trial.get("onset_pc_ns", 0) and on["sequence"] < off["sequence"]
                              and on["tpad_ms"] <= off["tpad_ms"]
                              and not any(e["out_of_order"] or e["kind"] in ("malformed", "incomplete") for e in received))
                trial["quality"] = "receipt-context pair; physical association unconfirmed" if associated else "optical association uncertain"
                if associated and response and on["sequence"] < response["sequence"]:
                    rt_ms = response["tpad_ms"] - on["tpad_ms"]  # ONLY the same hardware clock.
                    if 0 <= rt_ms <= DURATIONS_MS["response"]:
                        trial["rt_ms"] = rt_ms  # Observed RT; not a full scientific qualification.
                    else:
                        trial["quality"] += "; response outside hardware window"
            if not trial["completed"]:
                trial["quality"] += "; partial/unstarted trial"
        session.update(ended_utc=datetime.now(timezone.utc).isoformat(), received_records=len(events))
        save_files(directory, events, trials, timing, session)  # Buffered during frames; saved after ESC/errors too.
    print(f"Session {session['status']}; data saved to {directory}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
