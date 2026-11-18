"""Simulated tPAD records and frames exercise the complete teaching experiment."""

import base64
from collections import Counter
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import csv
from dataclasses import asdict
import io
import json
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import simon_demo_psychopy as demo
from tpad_listener import TPADRecord


class FakeWindow:
    def __init__(self, harness, **kwargs):
        self.harness = harness
        self.size = (1920, 1200) if kwargs["fullscr"] else kwargs["size"]
        self.fullscreen = kwargs["fullscr"]
        self.nDroppedFrames = 0
        self.callbacks, self.drawn, self.frames = [], [], []
        self.closed = False

    def getActualFrameRate(self, **kwargs):
        return self.harness.refresh_hz

    def callOnFlip(self, callback):
        self.callbacks.append(callback)

    def flip(self):
        if self.harness.display_error_frame == len(self.frames):
            raise RuntimeError("Synthetic display error")
        self.harness.now_ns += round(1_000_000_000 / 60)
        if self.harness.delayed_frame == len(self.frames):
            self.harness.now_ns += 50_000_000
            self.nDroppedFrames += 1
        for callback in self.callbacks:
            callback()
        self.callbacks.clear()
        self.harness.on_flip(self.drawn)
        self.frames.append(self.drawn[:])
        self.drawn.clear()
        return 1000 + (self.harness.now_ns - 50_000_000_000) / 1_000_000_000

    def close(self):
        self.closed = True


class FakeStimulus:
    def __init__(self, window, kind, **kwargs):
        self.window, self.kind = window, kind
        self.__dict__.update(kwargs)

    def draw(self):
        self.window.drawn.append((self.kind, getattr(self, "fillColor", None), getattr(self, "pos", None)))


class FakeListener:
    def __init__(self, harness):
        self.harness = harness
        self.closed = False
        self.poll_frames = []
        self.sequence = 0

    def poll(self):
        self.poll_frames.append(len(self.harness.window.frames))
        if self.harness.serial_error_poll == len(self.poll_frames):
            raise OSError("Synthetic serial error")
        records = []
        self.harness.pending.sort(key=lambda item: item[0])
        while self.harness.pending and self.harness.pending[0][0] <= self.harness.now_ns:
            _, channel, edge, sensor, hardware = self.harness.pending.pop(0)
            self.sequence += 1
            is_button = channel == "A"
            records.append(TPADRecord(
                self.sequence, "button" if is_button else "optical",
                f"{channel} {edge} {sensor} {hardware}".encode(),
                self.harness.now_ns - (50_000_000 if channel == "C" and edge == "P" and self.harness.straddled_on else 0),
                self.harness.now_ns, channel, edge, sensor,
                sensor if is_button else None,
                ("press" if edge == "P" else "release") if is_button else ("on" if edge == "P" else "off"),
                hardware))
        return records

    def close(self):
        self.closed = True
        if self.harness.close_error:
            self.harness.close_error = False
            raise OSError("Synthetic close error")
        if self.harness.tail:
            self.sequence += 1
            tail, self.harness.tail = self.harness.tail, b""
            return [TPADRecord(self.sequence, "incomplete", tail, self.harness.now_ns, None)]
        return []


class Harness:
    def __init__(self):
        self.now_ns = 50_000_000_000
        self.pending = []
        self.white = False
        self.trial = 0
        self.press_delay_ms = 300
        self.missing_on, self.missing_off, self.extra_on = set(), set(), set()
        self.delivery_delay_ms = 0
        self.optical_duration_ms = 100
        self.straddled_on = self.wrong_response = False
        self.escape_frame = self.serial_error_poll = self.display_error_frame = self.delayed_frame = None
        self.close_error = False
        self.handshake_error = False
        self.tail = b""
        self.refresh_hz = 60
        self.listener = FakeListener(self)

    def window_factory(self, **kwargs):
        self.window = FakeWindow(self, **kwargs)
        return self.window

    def on_flip(self, drawn):
        white = any(kind == "patch" and color == "white" for kind, color, _ in drawn)
        if white and not self.white:
            self.trial += 1
            self.onset_ms = 900_000 + self.trial * 2500
            if self.trial not in self.missing_on:
                due = self.now_ns + self.delivery_delay_ms * 1_000_000
                self.pending.append((due, "C", "P", 1, self.onset_ms))
                if self.trial in self.extra_on:
                    self.pending.append((due, "C", "P", 1, self.onset_ms))
            colors = [color for kind, color, _ in drawn if kind == "stimulus"]
            button = demo.BUTTONS[colors[0]]
            if self.wrong_response:
                button = 3 - button
            if self.press_delay_ms is not None:
                due = self.now_ns + self.press_delay_ms * 1_000_000
                self.pending.extend(((due, "A", "P", button, self.onset_ms + self.press_delay_ms),
                                     (due + 10_000_000, "A", "R", button, self.onset_ms + self.press_delay_ms + 10)))
        if self.white and not white and self.trial not in self.missing_off:
            self.pending.append((self.now_ns + self.delivery_delay_ms * 1_000_000, "C", "R", 1, self.onset_ms + self.optical_duration_ms))
        self.white = white

    def keys(self, keyList):
        if self.escape_frame is not None and len(self.window.frames) >= self.escape_frame:
            return ["escape"]
        return ["space"] if "space" in keyList else []

    def run(self, directory, args=None):
        psychopy = ModuleType("psychopy")
        psychopy.visual = SimpleNamespace(
            Window=self.window_factory,
            Circle=lambda win, **kw: FakeStimulus(win, "stimulus", **kw),
            Rect=lambda win, **kw: FakeStimulus(win, "patch", **kw),
            TextStim=lambda win, **kw: FakeStimulus(win, "text", **kw))
        psychopy.event = SimpleNamespace(getKeys=self.keys)
        with ExitStack() as stack:
            stack.enter_context(patch.dict("sys.modules", {"psychopy": psychopy}))
            stack.enter_context(patch.dict("os.environ"))
            stack.enter_context(patch.object(demo, "ROOT", Path(directory)))
            stack.enter_context(patch.object(demo, "OUTPUT_ROOT", Path(directory) / "output"))
            self.open_listener = stack.enter_context(patch.object(
                demo, "TPADListener", return_value=self.listener,
                side_effect=OSError("Setup failed") if self.handshake_error else None))
            stack.enter_context(patch.object(demo.time, "monotonic_ns", side_effect=lambda: self.now_ns))
            stack.enter_context(patch.object(demo.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="test-commit\n")))
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(redirect_stderr(io.StringIO()))
            result = demo.main(["--port", "COM_TEST", *(args or [])])
        session = max((Path(directory) / "output").iterdir())
        with (session / "trials.csv").open(encoding="utf-8", newline="") as handle:
            trials = list(csv.DictReader(handle))
        with (session / "timing.csv").open(encoding="utf-8", newline="") as handle:
            timing = list(csv.DictReader(handle))
        records = [json.loads(row) for row in (session / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        metadata = json.loads((session / "session.json").read_text(encoding="utf-8"))
        return result, trials, timing, records, metadata


class SimonDemoTests(unittest.TestCase):
    def run_demo(self, harness=None, args=None):
        harness = harness or Harness()
        with tempfile.TemporaryDirectory() as directory:
            result = harness.run(directory, args)
        return harness, result

    def test_eight_balanced_reproducible_trials_mapping_and_congruency(self):
        _, (_, first, _, _, _) = self.run_demo()
        _, (_, second, _, _, _) = self.run_demo()
        self.assertEqual(first, second)
        self.assertEqual(Counter((t["color"], t["position"]) for t in first),
                         {("red", "left"): 2, ("red", "right"): 2, ("blue", "left"): 2, ("blue", "right"): 2})
        for trial in first:
            self.assertEqual(int(trial["expected_button"]), demo.BUTTONS[trial["color"]])
            self.assertEqual(trial["congruency"], "congruent" if (trial["color"], trial["position"]) in
                             (("red", "left"), ("blue", "right")) else "incongruent")
        with patch.object(demo, "SEED", demo.SEED + 1):
            _, (_, different, _, _, _) = self.run_demo()
        self.assertNotEqual([t["color"] for t in first], [t["color"] for t in different])

    def test_fullscreen_zero_margin_patch_is_100_ms_and_stimulus_is_500_ms(self):
        harness, (result, _, timing, _, session) = self.run_demo()
        self.assertEqual(result, 0)
        self.assertTrue(harness.window.fullscreen)
        self.assertEqual(session["window_size_px"], [1920, 1200])
        self.assertEqual(session["patch_position_px"], [-885, -525])
        for number in range(1, 9):
            transitions = {r["transition"]: r for r in timing if r["trial_number"] == str(number)}
            onset = float(transitions["stimulus_onset"]["flip_psychopy_s"])
            self.assertAlmostEqual(float(transitions["patch_offset"]["flip_psychopy_s"]) - onset, 0.1, places=6)
            self.assertAlmostEqual(float(transitions["stimulus_offset"]["flip_psychopy_s"]) - onset, 0.5, places=6)
            self.assertEqual(int(transitions["patch_offset"]["frame"]) - int(transitions["stimulus_onset"]["frame"]), 6)
        self.assertEqual(sum(any(k == "patch" and c == "white" for k, c, _ in frame) for frame in harness.window.frames), 48)
        _, (_, _, _, _, windowed) = self.run_demo(args=["--windowed"])
        self.assertEqual(windowed["patch_position_px"], [-437, -309])

    def test_complete_exports_and_continuous_polling(self):
        harness, (result, trials, _, events, session) = self.run_demo()
        self.assertEqual(result, 0)
        self.assertEqual(session["status"], "completed")
        self.assertEqual(session["git_commit"], "test-commit")
        self.assertTrue(all(t["rt_ms"] == "300" and t["accuracy"] == "1" for t in trials))
        self.assertTrue(all(t["response_basis"] == "nominal_window_receipt" for t in trials))
        self.assertEqual([e["sequence"] for e in events], list(range(1, 33)))
        self.assertTrue(all(e["association"] == "unconfirmed" for e in events))
        self.assertTrue(set(range(2, len(harness.window.frames) + 1)) <= set(harness.listener.poll_frames))
        self.assertTrue(harness.window.closed and harness.listener.closed)
        harness.open_listener.assert_called_once_with("COM_TEST")

    def test_missing_or_extra_optics_affect_only_that_trial_not_accuracy(self):
        for problem in ("missing_on", "missing_off", "extra_on"):
            with self.subTest(problem=problem):
                harness = Harness()
                getattr(harness, problem).add(1)
                _, (_, trials, _, _, _) = self.run_demo(harness)
                self.assertEqual(trials[0]["rt_ms"], "")
                self.assertTrue(all(t["accuracy"] == "1" for t in trials))
                self.assertTrue(all(t["rt_ms"] == "300" for t in trials[1:]))
                self.assertIn("uncertain", trials[0]["quality"])

    def test_no_100_ms_receive_delay_cutoff_and_no_short_pulse_filter(self):
        harness = Harness()
        harness.delivery_delay_ms = 150
        _, (_, trials, _, _, _) = self.run_demo(harness)
        self.assertTrue(all(t["rt_ms"] == "300" for t in trials))
        harness = Harness()
        harness.optical_duration_ms = 2
        _, (_, trials, _, events, _) = self.run_demo(harness)
        self.assertTrue(all(t["pulse_duration_ms"] == "2" for t in trials))
        self.assertEqual(sum(e["kind"] == "optical" for e in events), 16)

    def test_crossing_onset_or_late_receipt_is_uncertain_without_forced_rt(self):
        for problem in ("straddled_on", "late"):
            with self.subTest(problem=problem):
                harness = Harness()
                if problem == "straddled_on":
                    harness.straddled_on = True
                else:
                    harness.delivery_delay_ms = 700
                _, (_, trials, _, events, _) = self.run_demo(harness)
                self.assertTrue(all(t["rt_ms"] == "" and t["accuracy"] == "1" for t in trials))
                self.assertEqual(sum(e["kind"] == "optical" for e in events), 16)

    def test_errors_and_omissions_are_independent_of_missing_optics(self):
        harness = Harness()
        harness.wrong_response = True
        harness.missing_on = set(range(1, 9))
        _, (_, trials, _, _, _) = self.run_demo(harness)
        self.assertTrue(all(t["accuracy"] == "0" and t["response_ms"] and not t["rt_ms"] for t in trials))
        harness = Harness()
        harness.press_delay_ms = None
        _, (_, trials, _, _, _) = self.run_demo(harness)
        self.assertTrue(all(t["accuracy"] == "0" and t["response_ms"] == "" for t in trials))

    def test_early_responses_never_change_visual_timeline(self):
        timelines = []
        for delay in (None, 1, 300, 1400):
            harness = Harness()
            harness.press_delay_ms = delay
            _, (result, _, timing, _, _) = self.run_demo(harness)
            self.assertEqual(result, 0)
            timelines.append(timing)
        self.assertTrue(all(timeline == timelines[0] for timeline in timelines))

    def test_every_record_is_preserved_in_original_order_with_receipt_context(self):
        records = []
        for channel, sensor in (("A", 1), ("A", 2), ("A", 3), ("A", 4), ("C", 1), ("M", 1)):
            for edge in ("P", "R"):
                kind = {"A": "button", "C": "optical", "M": "microphone"}[channel]
                records.append(TPADRecord(len(records) + 1, kind, f"{channel} {edge} {sensor} 123".encode(),
                                          100, 200, channel, edge, sensor, sensor if channel == "A" else None,
                                          "press" if edge == "P" else "release", 123))
        records += [records[0], TPADRecord(99, "mode", b"MODE 5:", 1, 2),
                    TPADRecord(100, "malformed", b"\x00\xffbad", 3, 4), TPADRecord(101, "incomplete", b"A P", 5, None)]
        events = []
        demo.keep_events(records, events, 2, "fixation")
        for record, event in zip(records, events):
            restored = dict(event)
            restored["raw"] = base64.b64decode(restored.pop("raw_base64"))
            for key in ("receipt_trial", "receipt_phase", "association"):
                restored.pop(key)
            self.assertEqual(restored, asdict(record))
        self.assertEqual(events[0]["receipt_phase"], "fixation")
        self.assertEqual(len(events), len(records))

    def test_escape_errors_and_cleanup_preserve_partial_data(self):
        for problem in ("instructions", "fixation", "stimulus", "response_wait", "iti", "final", "serial", "display", "close"):
            with self.subTest(problem=problem):
                harness = Harness()
                harness.tail = b"A R 1 "
                escape = dict(instructions=0, fixation=15, stimulus=34, response_wait=85, iti=140, final=1210)
                if problem in escape:
                    harness.escape_frame = escape[problem]
                elif problem == "serial":
                    harness.serial_error_poll = 70
                elif problem == "display":
                    harness.display_error_frame = 70
                else:
                    harness.close_error = True
                _, (result, trials, _, events, session) = self.run_demo(harness)
                self.assertEqual(result, 130 if problem in escape else 1)
                self.assertEqual(session["status"], "interrupted" if problem in escape else "error")
                self.assertEqual(len(trials), 8)
                self.assertTrue(harness.window.closed and harness.listener.closed)
                self.assertEqual(base64.b64decode(events[-1]["raw_base64"]), b"A R 1 ")
                self.assertIsNone(events[-1]["receipt_trial"])
                self.assertEqual(events[-1]["receipt_phase"], "cleanup")

    def test_startup_failures_still_save_all_eight_rows(self):
        for problem in ("refresh", "handshake"):
            with self.subTest(problem=problem):
                harness = Harness()
                harness.refresh_hz = None if problem == "refresh" else 60
                harness.handshake_error = problem == "handshake"
                _, (result, trials, _, _, session) = self.run_demo(harness)
                self.assertEqual(result, 1)
                self.assertEqual(session["status"], "error")
                self.assertEqual(len(trials), 8)
                self.assertTrue(harness.window.closed)

    def test_failed_export_does_not_skip_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "trials.csv").mkdir()
            with self.assertRaises(OSError):
                demo.save_files(output, [{"raw_base64": "AA=="}], [], [], {"status": "test"})
            self.assertTrue((output / "events.jsonl").is_file())
            self.assertTrue((output / "timing.csv").is_file())
            self.assertEqual(json.loads((output / "session.json").read_text())["status"], "test")


if __name__ == "__main__":
    unittest.main()
