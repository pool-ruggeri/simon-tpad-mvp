"""Ten-presentation Opto 1 diagnostic using the unchanged Simon presenter."""

import argparse
import csv
from dataclasses import asdict, fields
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import sys
import time
import uuid

from run_simon import (ROOT, OperatorAbort, Presentation, atomic_json, load_config,
                       package_version, present_trial, software_revision)
from tpad_serial import Event, SerialFailure, TPadReader
from trial_logic import Trial, events_for_trial

EXPECTED_PULSES = 10
INTRO = ("Opto Diagnostic — Position Opto 1 over the Simon Task optical marker. "
         "Press SPACE to start 10 stimulus presentations. Press ESC to quit.")


def describe(values):
    """Population SD; all inputs are differences of integer hardware times."""
    return {"count": len(values), "mean_ms": statistics.mean(values) if values else None,
            "median_ms": statistics.median(values) if values else None,
            "min_ms": min(values) if values else None, "max_ms": max(values) if values else None,
            "sd_ms": statistics.pstdev(values) if values else None}


def pair_optical_events(events, short_ms=10):
    """Pair edges in wire order, recovering only after OFF following repeated ON."""
    optical = [event for event in events if event.channel == "C" and event.sensor == 1]
    pulses, unpaired = [], []
    pending, ambiguous = None, False
    for event in optical:
        if event.duplicate:
            continue
        if event.edge == "P":
            if pending is not None or ambiguous:
                if pending is not None:
                    unpaired.append((pending, "multiple_on_before_off"))
                unpaired.append((event, "multiple_on_before_off"))
                pending, ambiguous = None, True
            else:
                pending = event
        elif ambiguous:
            unpaired.append((event, "off_after_ambiguous_on"))
            ambiguous = False
        elif pending is None:
            unpaired.append((event, "missing_on"))
        elif event.tpad_ms < pending.tpad_ms or pending.unexpected or event.unexpected:
            unpaired.extend(((pending, "inconsistent_edges"), (event, "inconsistent_edges")))
            pending = None
        else:
            duration = event.tpad_ms - pending.tpad_ms
            pulses.append({"on": pending, "off": event, "duration_ms": duration,
                           "kind": "short_activation" if duration <= short_ms else "optical_pulse"})
            pending = None
    if pending is not None:
        unpaired.append((pending, "missing_off"))
    return optical, pulses, unpaired


def event_key(event):
    return event.tpad_ms, event.sequence


def analyze(events, runs, short_ms=10, nominal_ms=500, clock_uncertain=False):
    optical, pulses, unpaired = pair_optical_events(events, short_ms)
    pulse_rows = [{"pulse_number": index, "on_sequence": pulse["on"].sequence,
                   "off_sequence": pulse["off"].sequence, "on_tpad_ms": pulse["on"].tpad_ms,
                   "off_tpad_ms": pulse["off"].tpad_ms, "duration_ms": pulse["duration_ms"],
                   "kind": pulse["kind"], "nominal_difference_ms": pulse["duration_ms"] - nominal_ms
                   if pulse["kind"] == "optical_pulse" else None,
                   "timing_valid": not clock_uncertain, "run_number": None,
                   "presentation_number": None, "association": "outside_presentations"}
                  for index, pulse in enumerate(pulses, 1)]
    summaries = []
    for run in runs:
        trials = run["trials"]
        first = next((trial for trial in trials if trial.lower_ms is not None), None)
        lower = (first.lower_ms, first.lower_sequence) if first else None
        upper = run.get("end_boundary")
        def in_run(event):
            return lower is not None and event_key(event) > lower and (upper is None or event_key(event) < upper)
        run_events = [event for event in optical if in_run(event)]
        owned = [i for i, pulse in enumerate(pulses) if in_run(pulse["on"]) and in_run(pulse["off"])]
        full = [i for i in owned if pulses[i]["kind"] == "optical_pulse"]
        # An edge paired across the run boundary is still unpaired WITHIN this run.
        orphans = [event for event, reason in unpaired if in_run(event)]
        for pulse in pulses:
            if in_run(pulse["on"]) != in_run(pulse["off"]):
                orphans.append(pulse["on"] if in_run(pulse["on"]) else pulse["off"])
        matched, presentations = {}, []
        for trial in trials:
            assigned = {event.sequence for event in events_for_trial(trial, optical)}
            candidates = [i for i in full if pulses[i]["on"].sequence in assigned
                          and pulses[i]["off"].sequence in assigned]
            orphaned = any(event.sequence in assigned for event in orphans)
            crossed = any((pulses[i]["on"].sequence in assigned) !=
                          (pulses[i]["off"].sequence in assigned) for i in full)
            late = any(trial.finalized_host_ns and event.arrival_monotonic_ns > trial.finalized_host_ns
                       for event in optical if event.sequence in assigned)
            acquisition_issues = [issue for issue in trial.issues if issue != "dropped_visual_frame"]
            if trial.stimulus_flip_host_s is None:
                status = "not_presented"
            elif not trial.completed or trial.upper_ms is None:
                status = "incomplete_presentation"
            elif clock_uncertain or len(candidates) > 1 or orphaned or crossed or late or acquisition_issues:
                status = "ambiguous"
            elif len(candidates) == 1:
                status = "matched"
                matched[trial.number] = candidates[0]
            else:
                status = "missing"
            for i in candidates:
                pulse_rows[i].update(run_number=run["number"], presentation_number=trial.number,
                                     association=status)
            presentations.append({**asdict(trial), "association": status,
                                  "complete_pulse_candidates": len(candidates), "late_after_grace": late})
        for i in owned:
            pulse_rows[i]["run_number"] = run["number"]
            if pulses[i]["kind"] == "short_activation":
                pulse_rows[i]["association"] = "additional_short_activation"
        intervals = [pulses[matched[n + 1]]["on"].tpad_ms - pulses[matched[n]]["on"].tpad_ms
                     for n in sorted(matched) if n + 1 in matched]
        durations = [pulses[i]["duration_ms"] for i in full]
        summaries.append({
            "run_number": run["number"], "status": run["status"],
            "expected_pulses": EXPECTED_PULSES, "scheduled_stimuli": len(trials),
            "presented_stimuli": sum(trial.stimulus_flip_host_s is not None for trial in trials),
            "presentations_with_frame_warnings": sum("dropped_visual_frame" in trial.issues for trial in trials),
            "on_events": sum(event.edge == "P" and not event.duplicate for event in run_events),
            "off_events": sum(event.edge == "R" and not event.duplicate for event in run_events),
            "complete_detected_pulses": len(full), "matched_presentations": len(matched),
            "missing_or_ambiguous_pulses": sum(row["association"] in ("missing", "ambiguous") for row in presentations),
            "incomplete_presentations": sum(row["association"] == "incomplete_presentation" for row in presentations),
            "not_presented": sum(row["association"] == "not_presented" for row in presentations),
            "additional_short_activations": len(owned) - len(full),
            "unpaired_events": len(orphans), "duplicate_events": sum(event.duplicate for event in run_events),
            "unpaired_on_events": sum(event.edge == "P" for event in orphans),
            "unpaired_off_events": sum(event.edge == "R" for event in orphans),
            "unmatched_full_pulses": len(full) - len(matched),
            "duration": describe([] if clock_uncertain else durations),
            "latest_duration_ms": durations[-1] if durations and not clock_uncertain else None,
            "onset_interval": describe([] if clock_uncertain else intervals),
            "end_boundary": upper, "presentations": presentations,
        })
    unique = [event for event in optical if not event.duplicate]
    return {"runs": summaries, "pulses": pulse_rows,
            "optical_state": ("ON" if unique[-1].edge == "P" else "OFF") if unique else "UNKNOWN",
            "unpaired_events": [{"sequence": event.sequence, "edge": event.edge, "tpad_ms": event.tpad_ms, "reason": reason}
                                for event, reason in unpaired]}


class DiagnosticFiles:
    """Dedicated logs for all repeats in one launch; flush only on black screens."""

    def __init__(self, root, config, short_ms):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.session_id = f"{stamp}_{uuid.uuid4().hex[:8]}"
        self.directory = Path(root) / self.session_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.raw_handle = (self.directory / "serial_raw.jsonl").open("w", encoding="utf-8")
        self.event_handle = (self.directory / "optical_events.csv").open("w", encoding="utf-8", newline="")
        self.event_writer = csv.DictWriter(self.event_handle, fieldnames=[field.name for field in fields(Event)])
        self.event_writer.writeheader()
        self.runs, self.short_ms, self.nominal_ms = [], short_ms, config["stimulus_ms"]
        self.start_sequence = 0
        self.metadata = {"session_id": self.session_id, "status": "initializing", "parameters": config,
                         "software_revision": software_revision(), "python_version": sys.version,
                         "psychopy_version": package_version("psychopy"), "pyserial_version": package_version("pyserial"),
                         "firmware_expected": config["expected_firmware"], "firmware_observed": None,
                         "operating_mode_confirmed": False, "short_activation_threshold_ms": short_ms,
                         "serial_settings": {"baudrate": 115200, "bytesize": 8, "parity": "N", "stopbits": 1,
                                             "timeout": 0, "flow_control": False},
                         "clock_uncertain": False, "simulation": False,
                         "statistics_policy": "Duration: all complete non-short physical pairs inside run hardware bounds; "
                         "interval: adjacent scheduled presentations with unique hardware-bound matches; population SD. "
                         "Host flip and receipt times are never subtracted from hardware times.",
                         "hardware_validation": "Requires real T-Pad evidence; no automatic pass/fail claim."}
        self.checkpoint([])

    def raw(self, record):
        self.raw_handle.write(json.dumps({"session_id": self.session_id, **record}) + "\n")

    def event(self, record):
        if record["channel"] == "C":
            self.event_writer.writerow(record)

    def snapshot(self, events):
        return analyze([event for event in events if event.sequence > self.start_sequence], self.runs,
                       self.short_ms, self.nominal_ms, self.metadata["clock_uncertain"])

    def checkpoint(self, events):
        result = self.snapshot(events)
        columns = ("pulse_number", "on_sequence", "off_sequence", "on_tpad_ms", "off_tpad_ms", "duration_ms",
                   "kind", "nominal_difference_ms", "timing_valid", "run_number", "presentation_number", "association")
        path = self.directory / "pulses.csv"
        temporary = path.with_suffix(".csv.tmp")
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(result["pulses"])
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        for handle in (self.raw_handle, self.event_handle):
            handle.flush()
            os.fsync(handle.fileno())
        atomic_json(self.directory / "summary.json", {**self.metadata, **result})
        return result

    def close(self):
        self.raw_handle.close()
        self.event_handle.close()


def number(value):
    return "n/a" if value is None else f"{value:.2f}"


class DiagnosticWindow(Presentation):
    """Use the original marker, draw method, setup, and keyboard/serial polling."""

    def __init__(self, config, files):
        self.files, self.waiting, self.last_timer = files, True, None
        self.panel, self.preview, self.next_panel_update = None, None, 0
        self.state_labels, self.current_state = {}, "UNKNOWN"
        self.white_visible = False
        super().__init__(config)
        from psychopy import visual
        width, height = self.window.size
        available = width - config["marker_margin_px"] - config["marker_size_px"] - 48
        if available < 400:
            self.window.close()
            raise ValueError("The diagnostic statistics panel does not fit outside this marker.")
        self.panel = visual.TextStim(self.window, text="", color="white", height=17,
                                     wrapWidth=min(720, available), pos=(width / 2 - 20, height / 2 - 20),
                                     anchorHoriz="right", anchorVert="top", alignText="left", autoLog=False)
        self.preview = visual.Rect(self.window, size=(config["marker_size_px"] + 14,) * 2,
                                   pos=self.marker.pos, fillColor=None, lineColor="white", autoLog=False)
        self.state_labels = {state: visual.TextStim(self.window, text=f"Current Opto 1 state: {state}",
                             color="white", height=17, pos=(width / 2 - 20, -height / 2 + 30),
                             anchorHoriz="right", autoLog=False) for state in ("ON", "OFF", "UNKNOWN")}
        # Prepare all state glyphs before any presentation; switching state later
        # selects an existing label rather than doing text layout during white.
        for label in self.state_labels.values():
            label.draw()
        self.window.flip()
        self.files.metadata.update(refresh_hz=self.refresh_hz, marker_size_px=list(map(float, self.marker.size)),
                                   marker_position_px=list(map(float, self.marker.pos)), marker_color_space=self.marker.colorSpace)
        self.update_panel(force=True)

    def timer_sample(self, timeout_ms):
        sample = super().timer_sample(timeout_ms)
        if self.last_timer is not None and sample.tpad_ms < self.last_timer:
            self.files.metadata["clock_uncertain"] = True
            raise SerialFailure("Hardware timer moved backward; timing statistics are invalid.")
        self.last_timer = sample.tpad_ms
        return sample

    def pump(self):
        keys = super().pump()
        self.update_panel()
        if self.state_labels:
            latest = next((event for event in reversed(self.reader.events if self.reader else [])
                           if event.channel == "C" and event.sensor == 1 and not event.duplicate), None)
            self.current_state = ("ON" if latest.edge == "P" else "OFF") if latest else "UNKNOWN"
        return keys

    def update_panel(self, force=False):
        now = time.perf_counter()
        # Rebuilding the long text while white can miss a display frame. Keep
        # its cached glyphs during white; the small state label still updates.
        if self.panel is None or (not force and (self.white_visible or now < self.next_panel_update)):
            return
        self.next_panel_update = now + 0.25
        result = self.files.snapshot(self.reader.events if self.reader is not None else [])
        lines = [INTRO if self.waiting else "Opto diagnostic running. No button responses required.", ""]
        if result["runs"]:
            run = result["runs"][-1]
            duration, interval = run["duration"], run["onset_interval"]
            if run["status"] == "running":
                # Keep live text compact; the long instructions, path, and final
                # summary are laid out only outside the presentation schedule.
                self.panel.text = "\n".join([
                    "Opto diagnostic — no button response required",
                    f"Scheduled: 10  Presented: {run['presented_stimuli']}",
                    f"ON: {run['on_events']}  OFF: {run['off_events']}  Complete: {run['complete_detected_pulses']}",
                    f"Latest: {number(run['latest_duration_ms'])}  Mean: {number(duration['mean_ms'])} ms",
                    f"Min: {number(duration['min_ms'])}  Max: {number(duration['max_ms'])} ms",
                    f"Short activations: {run['additional_short_activations']} (<= {self.files.short_ms} ms)",
                ])
                return
            lines += [f"Run {run['run_number']}: {run['status']}",
                      f"Scheduled: 10 | Presented: {run['presented_stimuli']} | ON: {run['on_events']} | OFF: {run['off_events']}",
                      f"Complete pulses: {run['complete_detected_pulses']} | Matched presentations: {run['matched_presentations']}",
                      f"Latest: {number(run['latest_duration_ms'])} ms | Mean: {number(duration['mean_ms'])} ms",
                      f"Min / Max: {number(duration['min_ms'])} / {number(duration['max_ms'])} ms",
                      f"Additional short activations: {run['additional_short_activations']} (<= {self.files.short_ms} ms)"]
            if run["status"] != "running":
                lines += [f"Missing / ambiguous: {run['missing_or_ambiguous_pulses']} | Unpaired ON/OFF: {run['unpaired_on_events']}/{run['unpaired_off_events']}",
                          f"Median: {number(duration['median_ms'])} ms | SD: {number(duration['sd_ms'])} ms",
                          f"Onset interval mean / SD: {number(interval['mean_ms'])} / {number(interval['sd_ms'])} ms",
                          f"Not presented: {run['not_presented']} | Incomplete: {run['incomplete_presentations']}",
                          f"Presentations with frame warnings: {run['presentations_with_frame_warnings']}",
                          f"Nominal white duration: {self.files.nominal_ms} ms. No hardware pass/fail inferred."]
        else:
            lines += ["Scheduled per run: 10 | ON: 0 | OFF: 0 | Complete pulses: 0",
                      "Latest / mean / min / max: n/a | Additional short activations: 0"]
        lines += ["", f"Log session: {self.files.session_id} (full directory printed in console)"]
        self.panel.text = "\n".join(lines)

    def draw(self, phase, trial=None):
        super().draw("black" if phase == "instructions" else phase, trial)
        self.white_visible = phase == "stimulus"
        if self.waiting and self.preview is not None:
            self.preview.draw()
        if self.panel is not None:
            self.panel.draw()
        if self.state_labels:
            self.state_labels[self.current_state].draw()

    def wait_for_start(self):
        self.waiting = True
        self.keyboard.clearEvents()
        self.update_panel(force=True)
        while True:
            keys = self.pump()
            self.draw("instructions")
            self.window.flip()
            if "space" in keys:
                self.waiting = False
                return


def run(config, output_root, short_ms=10):
    files = DiagnosticFiles(output_root, config, short_ms)
    print(f"Diagnostic output: {files.directory}", flush=True)
    ui = reader = active_run = None
    exit_code = 0
    try:
        ui = DiagnosticWindow(config, files)
        while True:
            ui.wait_for_start()
            if reader is None:
                reader = TPadReader.open(config["serial_port"], files.raw, files.event)
                ui.reader = reader
                ui.setup_device(files)
                files.start_sequence = reader.parser.sequence
                files.metadata["analysis_start_sequence"] = files.start_sequence
            active_run = {"number": len(files.runs) + 1, "status": "running",
                          "trials": [Trial(i, "opto_diagnostic", "blue", "left") for i in range(1, 11)]}
            files.runs.append(active_run)
            files.metadata["status"] = "running"
            for trial in active_run["trials"]:
                present_trial(ui, trial, config)
                if trial.upper_ms <= trial.lower_ms:
                    files.metadata["clock_uncertain"] = True
                    raise SerialFailure("Hardware timer did not advance across the presentation.")
                files.checkpoint(reader.events)
            end = ui.timer_sample(config["setup_timeout_ms"])
            active_run["end_boundary"] = (end.tpad_ms, end.sequence)
            active_run["status"] = "completed"
            files.checkpoint(reader.events)
            ui.update_panel(force=True)
            active_run = None
    except (OperatorAbort, KeyboardInterrupt):
        files.metadata["status"] = "closed"
        if active_run is not None:
            active_run["status"] = "aborted"
    except Exception as exc:
        exit_code = 1
        files.metadata.update(status="error", stop_reason=f"{type(exc).__name__}: {exc}")
        if active_run is not None:
            active_run["status"] = "error"
        print(files.metadata["stop_reason"], file=sys.stderr)
    finally:
        if ui is not None:
            try:
                ui.waiting = False
                ui.draw("black")
                ui.window.flip()
            except Exception as exc:
                files.metadata["display_cleanup_error"] = str(exc)
        if reader is not None:
            try:
                if not reader.failed:
                    reader.poll()
            except SerialFailure as exc:
                files.metadata["serial_cleanup_error"] = str(exc)
            finally:
                try:
                    if reader.parser.buffer:
                        files.metadata["unresolved_serial_fragment"] = True
                    reader.close()
                except Exception as exc:
                    files.metadata["serial_close_error"] = str(exc)
        try:
            files.checkpoint(reader.events if reader is not None else [])
        finally:
            files.close()
            if ui is not None:
                ui.window.close()
        print(f"Diagnostic saved: {files.directory}", flush=True)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--port", help="Override the serial port (default from config.json: COM5).")
    parser.add_argument("--windowed", action="store_true", help="Initial GUI checks; full screen matches Simon by default.")
    parser.add_argument("--short-pulse-ms", type=int, default=10, help="Separate additional activations at or below this hardware duration.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output" / "opto_diagnostics")
    args = parser.parse_args()
    config = load_config(args.config)
    if config["stimulus_ms"] != 500:
        parser.error("This milestone requires the Simon configuration's nominal 500 ms stimulus duration.")
    if not 0 < args.short_pulse_ms < config["stimulus_ms"]:
        parser.error("short-pulse-ms must be between 1 and stimulus_ms - 1.")
    if args.port:
        config["serial_port"] = args.port
    if args.windowed:
        config["full_screen"] = False
    return run(config, args.output_dir, args.short_pulse_ms)


if __name__ == "__main__":
    raise SystemExit(main())
