"""Simon–TPad MVP: keyboard navigation, fixed PsychoPy frames, serial responses."""

import argparse
import csv
from dataclasses import fields
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid

from tpad_serial import Event, SerialFailure, TPadReader
from trial_logic import Trial, frame_count, make_trials, score_trial, visual_phase

ROOT = Path(__file__).resolve().parent


class OperatorAbort(Exception):
    pass


def load_config(path):
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    positive = (
        "fixation_ms", "stimulus_ms", "response_window_ms", "black_interval_ms",
        "drain_grace_ms", "setup_timeout_ms", "optical_duration_tolerance_ms",
        "marker_size_px", "stimulus_size_px", "stimulus_eccentricity_px",
    )
    for name in positive:
        if type(config[name]) is not int or config[name] <= 0:
            raise ValueError(f"{name} must be a positive integer.")
    if config["response_window_ms"] < config["stimulus_ms"]:
        raise ValueError("The response window must cover the stimulus duration.")
    for name in ("practice_trials", "experimental_trials"):
        if type(config[name]) is not int or config[name] < 0 or config[name] % 4:
            raise ValueError(f"{name} must be a nonnegative multiple of four.")
    if config["practice_trials"] + config["experimental_trials"] == 0:
        raise ValueError("At least one block must contain trials.")
    if type(config["random_seed"]) is not int:
        raise ValueError("random_seed must be an integer.")
    if type(config["full_screen"]) is not bool:
        raise ValueError("full_screen must be a boolean.")
    if type(config["screen"]) is not int or config["screen"] < 0:
        raise ValueError("screen must be a nonnegative integer.")
    if type(config["marker_margin_px"]) is not int or config["marker_margin_px"] < 0:
        raise ValueError("marker_margin_px must be a nonnegative integer.")
    if not isinstance(config["serial_port"], str) or not config["serial_port"].strip():
        raise ValueError("serial_port must be a nonempty string.")
    if not isinstance(config["expected_firmware"], str) or len(config["expected_firmware"]) != 8 or not config["expected_firmware"].isascii() or not config["expected_firmware"].isdecimal():
        raise ValueError("expected_firmware must be an eight-digit string.")
    if len(config["window_size"]) != 2 or any(type(n) is not int or n <= 0 for n in config["window_size"]):
        raise ValueError("window_size must contain two positive integers.")
    return config


def software_revision():
    def git(*args):
        result = subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
            cwd=ROOT, capture_output=True, text=True, timeout=5, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    try:
        return {"commit": git("rev-parse", "HEAD"), "branch": git("branch", "--show-current"),
                "working_tree_dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.TimeoutExpired):
        return {"commit": "unknown", "branch": "unknown", "working_tree_dirty": None}


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


class SessionFiles:
    """Four auditable outputs; checkpoints flush only between visual routines."""

    def __init__(self, results_root, config):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.session_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
        self.directory = Path(results_root) / self.session_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.config = config
        self.raw_handle = (self.directory / "serial_raw.jsonl").open("w", encoding="utf-8", newline="\n")
        self.event_handle = (self.directory / "events.csv").open("w", encoding="utf-8", newline="")
        self.event_writer = csv.DictWriter(self.event_handle, fieldnames=["session_id"] + [field.name for field in fields(Event)])
        self.event_writer.writeheader()
        self.metadata = {
            "session_id": self.session_id, "started_utc": datetime.now(timezone.utc).isoformat(),
            "status": "initializing", "parameters": config,
            "serial": {"port": config["serial_port"], "baudrate": 115200, "bytesize": 8,
                       "parity": "N", "stopbits": 1, "timeout": 0, "write_timeout": 0.1,
                       "xonxoff": False, "rtscts": False, "dsrdtr": False},
            "firmware_expected": config["expected_firmware"], "firmware_observed": None,
            "ftdi_latency_ms": 1, "ftdi_latency_source": "PO-reported; not changed or independently measured",
            "operating_mode": 5, "operating_mode_confirmed": False,
            "psychopy_version": package_version("psychopy"), "pyserial_version": package_version("pyserial"),
            "python_version": sys.version, "python_executable": sys.executable,
            "platform": platform.platform(), "random_seed": config["random_seed"],
            "software_revision": software_revision(),
            "response_mapping": {"blue": {"button": 1, "side": "left"}, "yellow": {"button": 2, "side": "right"}},
            "scientific_clock": "T-Pad integer milliseconds; RT = button press minus Opto 1 ON",
            "hardware_validation": "Not inferred from software tests",
            "ttl_source": "Automatic T-Pad hardware outputs; no software TTL commands",
            "boundary_policy": "Read-only T timer replies around each visual trial; no timer reset",
            "deadline_policy": "Optical onset + response_window_ms, inclusive; sequence resolves equal timestamps",
        }
        self.checkpoint([], [])

    def raw(self, record):
        record = {"session_id": self.session_id, **record}
        self.raw_handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    def event(self, record):
        self.event_writer.writerow({"session_id": self.session_id, **record})

    def checkpoint(self, trials, events):
        rows = [score_trial(trial, events, self.config, self.session_id) for trial in trials]
        template = score_trial(Trial(0, "practice", "blue", "left"), [], self.config)
        path = self.directory / "trials.csv"
        temporary = path.with_suffix(".csv.tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(template))
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        for handle in (self.raw_handle, self.event_handle):
            handle.flush()
            os.fsync(handle.fileno())
        self.metadata["attempted_trials"] = len(trials)
        self.metadata["completed_trials"] = sum(trial.completed for trial in trials)
        self.metadata["valid_trials"] = sum(row["valid"] for row in rows)
        self.metadata["event_count"] = len(events)
        atomic_json(self.directory / "session.json", self.metadata)

    def close(self):
        self.raw_handle.close()
        self.event_handle.close()


def load_psychopy():
    # PsychoPy normally creates per-user preferences on import. Keep this run's
    # preferences/cache inside the project and disable its extra package paths.
    # These environment overrides affect this Python process only.
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    if sys.platform == "win32":
        roaming = cache / "roaming"
        roaming.mkdir(exist_ok=True)
        os.environ["APPDATA"] = str(roaming)
    os.environ["MPLCONFIGDIR"] = str(cache / "matplotlib")
    os.environ["PSYCHOPYNOPACKAGES"] = "1"
    import psychopy
    from psychopy import event, visual
    return psychopy, event, visual


class Presentation:
    """Draw frames and poll the ordinary keyboard separately from serial input."""

    def __init__(self, config):
        self.config = config
        self.psychopy, self.keyboard, visual = load_psychopy()
        self.reader = None
        self.window = visual.Window(
            size=config["window_size"], fullscr=config["full_screen"], screen=config["screen"],
            units="pix", color=(-1, -1, -1), colorSpace="rgb", winType="pyglet",
            waitBlanking=True, allowGUI=not config["full_screen"], autoLog=False,
        )
        width, height = self.window.size
        marker_size = config["marker_size_px"]
        margin = config["marker_margin_px"]
        eccentricity = config["stimulus_eccentricity_px"]
        if marker_size + 2 * margin > min(width, height) or eccentricity + config["stimulus_size_px"] / 2 >= width / 2:
            self.window.close()
            raise ValueError("Marker/stimulus geometry does not fit this display.")
        self.marker = visual.Rect(
            self.window, width=marker_size, height=marker_size,
            pos=(-width / 2 + margin + marker_size / 2, -height / 2 + margin + marker_size / 2),
            fillColor="black", lineColor="black", autoLog=False,
        )
        self.stimulus = visual.Circle(self.window, radius=config["stimulus_size_px"] / 2, autoLog=False)
        self.text = visual.TextStim(self.window, text="", color="white", height=26,
                                    wrapWidth=min(width - 120, 900), autoLog=False)
        self.fixation = visual.TextStim(self.window, text="+", color="white", height=36, autoLog=False)
        self.draw("black")
        self.window.flip()
        self.refresh_hz = self.window.getActualFrameRate(nIdentical=20, nMaxFrames=180, nWarmUpFrames=30)
        if self.refresh_hz is None or self.refresh_hz <= 0:
            self.window.close()
            raise RuntimeError("Cannot measure a stable refresh rate. Check the display before collecting data.")

    def pump(self):
        if self.reader is not None:
            self.reader.poll()
        keys = self.keyboard.getKeys(keyList=["escape", "space", "return"])
        if "escape" in keys:
            raise OperatorAbort("Escape pressed")
        return keys

    def draw(self, phase, trial=None):
        self.marker.fillColor = "white" if phase == "stimulus" else "black"
        self.marker.lineColor = self.marker.fillColor
        if phase == "stimulus":
            self.stimulus.fillColor = trial.color
            self.stimulus.lineColor = trial.color
            self.stimulus.pos = ((-1 if trial.side == "left" else 1) * self.config["stimulus_eccentricity_px"], 0)
            self.stimulus.draw()
        elif phase == "fixation":
            self.fixation.draw()
        elif phase == "instructions":
            self.text.draw()
        self.marker.draw()

    def black_frames(self, count):
        for _ in range(count):
            self.pump()
            self.draw("black")
            self.window.flip()

    def instructions(self, text):
        self.keyboard.clearEvents()
        self.text.text = text + "\n\nPress Space or Return to continue. Escape exits safely."
        while True:
            keys = self.pump()
            self.draw("instructions")
            self.window.flip()
            if "space" in keys or "return" in keys:
                return

    def request(self, command, predicate, timeout_ms):
        """Wait only on a black screen, while polling serial and Escape each frame."""
        start_sequence = self.reader.parser.sequence
        self.reader.command(command)
        stop = time.perf_counter() + timeout_ms / 1000
        while time.perf_counter() < stop:
            self.pump()
            for message in self.reader.messages:
                if message.sequence > start_sequence and predicate(message):
                    return message
            self.draw("black")
            self.window.flip()
        raise SerialFailure(f"No valid reply to {command!r} within {timeout_ms} ms.")

    def timer_sample(self, timeout_ms):
        return self.request(b"T", lambda message: message.kind == "counter", timeout_ms)

    def setup_device(self, files):
        # Mode entry resets its timer once, as documented. No explicit R is sent.
        self.request(b"X", lambda message: message.raw.strip() == b"MODE 0:", self.config["setup_timeout_ms"])
        self.black_frames(frame_count(500, self.refresh_hz))
        firmware = self.request(b"FIRM\n", lambda message: message.kind == "counter" and len(message.raw.strip()) == 8,
                                self.config["setup_timeout_ms"])
        observed = firmware.raw.decode("ascii").strip()
        files.metadata["firmware_observed"] = observed
        if observed != self.config["expected_firmware"]:
            raise SerialFailure(f"Firmware {observed} differs from expected {self.config['expected_firmware']}; no settings were changed.")
        self.black_frames(frame_count(500, self.refresh_hz))
        self.request(b"MOD5\n", lambda message: message.raw.strip() == b"MODE 5:", self.config["setup_timeout_ms"])
        files.metadata["operating_mode_confirmed"] = True
        self.black_frames(frame_count(500, self.refresh_hz))


def present_trial(ui, trial, config):
    """One fixed visual timeline, followed by black collection and bounded grace."""
    lower = ui.timer_sample(config["setup_timeout_ms"])
    trial.lower_ms, trial.lower_sequence = lower.tpad_ms, lower.sequence
    first_issue_sequence = lower.sequence
    for _ in range(frame_count(config["fixation_ms"], ui.refresh_hz)):
        ui.pump()
        ui.draw("fixation")
        ui.window.flip()
    if ("C", 1) in ui.reader.active:
        trial.issues.append("optical_active_before_stimulus")
    if any(event.sequence > lower.sequence and event.channel == "C" and event.sensor == 1
           and not event.duplicate for event in ui.reader.events):
        trial.issues.append("optical_transition_during_fixation")
    stimulus_frames = frame_count(config["stimulus_ms"], ui.refresh_hz)
    response_frames = frame_count(config["response_window_ms"], ui.refresh_hz)
    flips = []
    for index in range(response_frames + 1):
        ui.pump()
        phase = visual_phase(index, stimulus_frames, response_frames)
        ui.draw(phase, trial)
        flip = ui.window.flip()
        flips.append(flip)
        if index == 0:
            trial.stimulus_flip_host_s = flip
        if index == stimulus_frames:
            trial.offset_flip_host_s = flip
        if index == response_frames:
            trial.visual_end_host_s = flip
    if any(b - a > 1.5 / ui.refresh_hz for a, b in zip(flips, flips[1:])):
        trial.issues.append("dropped_visual_frame")
    # The exact optical response deadline is scored in hardware milliseconds.
    # This black interval also covers marker scanout delay relative to its flip.
    ui.black_frames(frame_count(config["black_interval_ms"], ui.refresh_hz))
    grace_end = time.perf_counter() + config["drain_grace_ms"] / 1000
    upper = ui.timer_sample(config["drain_grace_ms"])
    trial.upper_ms, trial.upper_sequence = upper.tpad_ms, upper.sequence
    while time.perf_counter() < grace_end:
        ui.black_frames(1)
    ui.reader.poll()
    if ui.reader.parser.buffer:
        trial.issues.append("unresolved_serial_fragment")
    if ui.reader.connection.in_waiting:
        trial.issues.append("undrained_serial_backlog")
    if any(first_issue_sequence < sequence <= ui.reader.parser.sequence for sequence in ui.reader.issue_sequences):
        trial.issues.append("unrecognized_serial_data")
    if ("C", 1) in ui.reader.active:
        trial.issues.append("optical_active_after_stimulus")
    trial.finalized_host_ns = time.perf_counter_ns()
    trial.completed = True


def gui_smoke(config):
    """Visible, automatically closing display smoke test. Does not open COM5."""
    config = {**config, "full_screen": False}
    ui = Presentation(config)
    try:
        trial = Trial(1, "smoke", "blue", "left")
        for index in range(frame_count(2000, ui.refresh_hz)):
            ui.pump()
            ui.draw("stimulus" if index < frame_count(500, ui.refresh_hz) else "black", trial)
            ui.window.flip()
        evidence = {"psychopy_version": ui.psychopy.__version__, "refresh_hz": ui.refresh_hz,
                    "window_size": [int(n) for n in ui.window.size], "serial_opened": False,
                    "hardware_validation": False}
        atomic_json(ROOT / ".cache" / "gui_smoke.json", evidence)
        print(json.dumps(evidence, indent=2))
    finally:
        ui.window.close()


def run(config, results_root):
    files = SessionFiles(results_root, config)
    print(f"Session output: {files.directory}", flush=True)
    ui = None
    reader = None
    attempted = []
    exit_code = 0
    try:
        planned = make_trials(config["practice_trials"], config["experimental_trials"], config["random_seed"])
        files.metadata["trial_plan"] = [{"number": trial.number, "block": trial.block,
                                         "color": trial.color, "side": trial.side} for trial in planned]
        ui = Presentation(config)
        files.metadata["refresh_hz"] = ui.refresh_hz
        files.metadata["actual_window_size"] = [int(n) for n in ui.window.size]
        files.metadata["frame_schedule"] = {
            name: frame_count(config[name], ui.refresh_hz)
            for name in ("fixation_ms", "stimulus_ms", "response_window_ms", "black_interval_ms")
        }
        ui.instructions("Simon Task\n\nRespond to the COLOR, regardless of its position.\nBlue: T-Pad Button 1 (left response).\nYellow: T-Pad Button 2 (right response).\n\nClose the BBTK utility. Place Opto 1 over the lower-left marker.\nKeep Buttons 1 and 2 released until a stimulus appears.")
        reader = TPadReader.open(config["serial_port"], files.raw, files.event)
        ui.reader = reader
        ui.setup_device(files)
        files.metadata["status"] = "running"
        files.checkpoint(attempted, reader.events)
        previous_upper = None
        previous_block = None
        for trial in planned:
            if trial.block != previous_block:
                message = "Practice block: 4 balanced conditions." if trial.block == "practice" else "Experimental block. Respond to color using Buttons 1 and 2."
                ui.instructions(message)
                previous_block = trial.block
            attempted.append(trial)
            present_trial(ui, trial, config)
            if trial.upper_ms <= trial.lower_ms or (previous_upper is not None and trial.lower_ms < previous_upper):
                for collected in attempted:
                    collected.issues.append("session_hardware_clock_discontinuity")
                raise SerialFailure("Hardware timer moved backward between trials; acquisition stopped.")
            previous_upper = trial.upper_ms
            files.checkpoint(attempted, reader.events)
        files.metadata["status"] = "completed"
        ui.instructions("Session complete. Press Space or Return to close.")
    except (OperatorAbort, KeyboardInterrupt) as exc:
        files.metadata["status"] = "aborted"
        files.metadata["stop_reason"] = str(exc) or "Keyboard interrupt"
        if attempted and not attempted[-1].completed:
            attempted[-1].issues.append("operator_abort")
    except Exception as exc:
        exit_code = 1
        files.metadata["status"] = "error"
        files.metadata["stop_reason"] = f"{type(exc).__name__}: {exc}"
        if attempted and not attempted[-1].completed:
            attempted[-1].issues.append("acquisition_or_presentation_error")
        print(files.metadata["stop_reason"], file=sys.stderr)
    finally:
        # Blacken the marker first, then retain any final bytes without resetting
        # the device or clearing its input buffer. Saving does not need the GUI.
        if ui is not None:
            try:
                ui.draw("black")
                ui.window.flip()
            except Exception as exc:
                files.metadata["display_cleanup_error"] = str(exc)
        if reader is not None:
            try:
                if not reader.failed:
                    reader.poll()
            except SerialFailure as exc:
                files.metadata["cleanup_serial_error"] = str(exc)
            finally:
                try:
                    if attempted and reader.parser.buffer:
                        attempted[-1].issues.append("unresolved_serial_fragment")
                    reader.close()
                except Exception as exc:
                    files.metadata["serial_close_error"] = str(exc)
        files.metadata["ended_utc"] = datetime.now(timezone.utc).isoformat()
        try:
            files.checkpoint(attempted, reader.events if reader is not None else [])
        finally:
            files.close()
            if ui is not None:
                ui.window.close()
        print(f"Session {files.metadata['status']}. Saved: {files.directory}", flush=True)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--seed", type=int, help="Override and save the random seed.")
    parser.add_argument("--windowed", action="store_true", help="Use a window for initial operator checks.")
    parser.add_argument("--gui-smoke", action="store_true", help="Automatically close a display check; no serial or trial data.")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.seed is not None:
            config["random_seed"] = args.seed
        if args.windowed:
            config["full_screen"] = False
        if args.gui_smoke:
            gui_smoke(config)
            return 0
        return run(config, args.results_dir)
    except Exception as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
