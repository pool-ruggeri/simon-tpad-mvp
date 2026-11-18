"""Exercise the complete procedural demo with fake frames and tPAD records."""

import base64
from collections import Counter
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import simon_demo_psychopy as demo
from tpad_listener import TPADRecord


def optical_session():
    """Eight independently identified host slots; hardware clock starts elsewhere."""
    trials = demo.make_trials()
    records, timing = [], []
    for index, trial in enumerate(trials):
        host = 80_000_000_000 + index * 2_500_000_000
        hardware = 900_000 + index * 2500
        trial.update(started=True, completed=True, collection_end_ns=host + 2_000_000_000)
        for transition, delta in (("stimulus_onset", 0), ("patch_offset", 200_000_000)):
            timing.append(dict(trial_number=index + 1, transition=transition, flip_monotonic_ns=host + delta))
        for channel, edge, sensor, stamp, delta in (
                ("C", "P", 1, hardware, 10), ("C", "R", 1, hardware + 200, 210),
                ("A", "P", trial["expected_response"], hardware + 300, 310),
                ("A", "R", trial["expected_response"], hardware + 400, 410)):
            is_button = channel == "A"
            records.append(TPADRecord(
                sequence=len(records) + 1, kind="button" if is_button else "optical",
                raw=f"{channel} {edge} {sensor} {stamp}".encode(),
                rx_first_ns=host + delta * 1_000_000, rx_complete_ns=host + delta * 1_000_000,
                channel=channel, edge=edge, sensor=sensor, button=sensor if is_button else None,
                state=("press" if edge == "P" else "release") if is_button else ("on" if edge == "P" else "off"),
                tpad_ms=stamp))
    return trials, records, timing


class FakeWindow:
    def __init__(self, harness, **kwargs):
        self.harness = harness
        self.size = kwargs["size"]
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
                self.harness.now_ns, self.harness.now_ns, channel, edge, sensor,
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
        white = any(kind == "patch" and color == (1, 1, 1) for kind, color, _ in drawn)
        if white and not self.white:
            self.trial += 1
            self.onset_ms = 900_000 + self.trial * 2500
            self.pending.append((self.now_ns, "C", "P", 1, self.onset_ms))
            colors = [color for kind, color, _ in drawn if kind == "stimulus"]
            button = demo.COLOR_TO_BUTTON[colors[0]]
            if self.press_delay_ms is not None:
                due = self.now_ns + self.press_delay_ms * 1_000_000
                self.pending.extend(((due, "A", "P", button, self.onset_ms + self.press_delay_ms),
                                     (due + 10_000_000, "A", "R", button, self.onset_ms + self.press_delay_ms + 10)))
        if self.white and not white:
            self.pending.append((self.now_ns, "C", "R", 1, self.onset_ms + 200))
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
            result = demo.main(["--windowed", "--port", "COM_TEST", *(args or [])])
        session = max((Path(directory) / "output").iterdir())
        with (session / "trials.csv").open(encoding="utf-8", newline="") as handle:
            trials = list(csv.DictReader(handle))
        with (session / "timing.csv").open(encoding="utf-8", newline="") as handle:
            timing = list(csv.DictReader(handle))
        records = [json.loads(row) for row in (session / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        metadata = json.loads((session / "session.json").read_text(encoding="utf-8"))
        return result, trials, timing, records, metadata


class SimonDemoTests(unittest.TestCase):
    def test_plan_balance_seed_mapping_and_congruency(self):
        plan = demo.make_trials()
        self.assertEqual(plan, demo.make_trials())
        self.assertNotEqual(plan, demo.make_trials(demo.SEED + 1))
        self.assertEqual(Counter((t["color"], t["position"]) for t in plan),
                         {("red", "left"): 2, ("red", "right"): 2, ("blue", "left"): 2, ("blue", "right"): 2})
        for trial in plan:
            self.assertEqual(trial["expected_response"], 1 if trial["color"] == "red" else 2)
            self.assertEqual(trial["congruency"] == "congruent",
                             (trial["color"], trial["position"]) in (("red", "left"), ("blue", "right")))

    def test_hardware_rt_correct_errors_and_omissions(self):
        trials, records, timing = optical_session()
        records = [r for r in records if not (r.kind == "button" and 900_000 <= r.tpad_ms < 902_500)]
        records[4] = TPADRecord(**{**records[4].__dict__, "button": 3 - records[4].button})
        records[5] = TPADRecord(**{**records[5].__dict__, "button": records[4].button})
        demo.score_trials(trials, records, timing, True, True)
        self.assertEqual((trials[0]["outcome"], trials[0]["accuracy"], trials[0]["rt_ms"]), ("omission", 0, None))
        self.assertEqual(trials[1]["accuracy"], 0)
        self.assertTrue(all(t["rt_ms"] == 300 and t["accuracy"] == 1 for t in trials[2:]))

    def test_missing_repeated_crossed_short_and_late_optics_invalidate_train(self):
        for problem in ("missing_on", "missing_off", "duplicate", "crossed", "short", "late", "unassigned"):
            with self.subTest(problem=problem):
                trials, records, timing = optical_session()
                if problem.startswith("missing"):
                    records.pop(0 if problem == "missing_on" else 1)
                elif problem == "duplicate":
                    records.insert(1, records[0])
                elif problem == "crossed":
                    records[0], records[1] = records[1], records[0]
                    records[0] = TPADRecord(**{**records[0].__dict__, "out_of_order": True})
                elif problem == "short":
                    records[1] = TPADRecord(**{**records[1].__dict__, "tpad_ms": records[0].tpad_ms + 2})
                elif problem == "late":
                    records[0] = TPADRecord(**{**records[0].__dict__, "rx_complete_ns": records[0].rx_complete_ns + 150_000_000})
                else:
                    records.append(TPADRecord(999, "optical", b"C P 1 1", 1, 2, "C", "P", 1, state="on", tpad_ms=1))
                demo.score_trials(trials, records, timing, True, True)
                self.assertTrue(all(t["validity"] == "excluded" and t["rt_ms"] is None for t in trials))

    def test_first_press_hardware_deadline_and_unrelated_buttons(self):
        trials, records, timing = optical_session()
        on = records[0]
        extra = [TPADRecord(0, "button", b"A P 1 900000", on.rx_first_ns, on.rx_complete_ns,
                            "A", "P", 1, 1, "press", on.tpad_ms),
                 TPADRecord(0, "button", b"A R 1 900000", on.rx_first_ns, on.rx_complete_ns,
                            "A", "R", 1, 1, "release", on.tpad_ms)]
        records[:0] = extra  # Same-ms press BEFORE optical ON does not count.
        records.insert(3, TPADRecord(2, "button", b"A P 3 900100", on.rx_first_ns, on.rx_complete_ns,
                                    "A", "P", 3, 3, "press", on.tpad_ms + 100))
        demo.score_trials(trials, records, timing, True, True)
        self.assertEqual(trials[0]["rt_ms"], 300)
        for offset, expected in ((1500, 1500), (1501, None)):
            trials, records, timing = optical_session()
            for index in (2, 3):
                records[index] = TPADRecord(**{**records[index].__dict__, "tpad_ms": 900_000 + offset})
            demo.score_trials(trials, records, timing, True, True)
            self.assertEqual(trials[0]["rt_ms"], expected)

    def test_repeated_press_regression_and_fragment_are_explicit_exclusions(self):
        for problem in ("repeat", "regression", "fragment", "malformed", "late_response"):
            with self.subTest(problem=problem):
                trials, records, timing = optical_session()
                if problem == "repeat":
                    records.insert(3, records[2])
                elif problem == "regression":
                    records[2] = TPADRecord(**{**records[2].__dict__, "out_of_order": True})
                elif problem in ("fragment", "malformed"):
                    records.append(TPADRecord(999, "incomplete" if problem == "fragment" else "malformed", b"\xff", 1, None))
                else:
                    records[2] = TPADRecord(**{**records[2].__dict__, "rx_complete_ns": trials[0]["collection_end_ns"] + 1})
                demo.score_trials(trials, records, timing, True, True)
                self.assertEqual(trials[0]["validity"], "excluded")
                self.assertTrue(trials[0]["exclusion_reason"])

    def test_complete_demo_exports_every_record_and_polls_each_frame(self):
        harness = Harness()
        with tempfile.TemporaryDirectory() as directory:
            result, trials, timing, records, metadata = harness.run(directory)
        self.assertEqual(result, 0)
        self.assertEqual(metadata["status"], "completed")
        self.assertEqual(metadata["git_commit"], "test-commit")
        self.assertEqual(len(trials), 8)
        self.assertTrue(all(t["rt_ms"] == "300" and t["accuracy"] == "1" for t in trials))
        self.assertEqual([r["sequence"] for r in records], list(range(1, 33)))
        self.assertEqual(base64.b64decode(records[0]["raw_base64"]), b"C P 1 902500")
        self.assertEqual({r["phase"] for r in timing}, {"fixation", "stimulus", "response_wait", "iti", "final_collection"})
        # Poll before and after EVERY displayed trial/final-collection frame.
        self.assertTrue(set(range(1, len(harness.window.frames) + 1)) <= set(harness.listener.poll_frames))
        harness.open_listener.assert_called_once_with("COM_TEST")
        self.assertTrue(harness.listener.closed and harness.window.closed)

    def test_responses_do_not_change_stimulus_patch_or_phase_durations(self):
        timelines = []
        for press_delay in (None, 1, 300, 1400):
            harness = Harness()
            harness.press_delay_ms = press_delay
            with tempfile.TemporaryDirectory() as directory:
                result, trials, timing, _, _ = harness.run(directory)
            self.assertEqual(result, 0)
            timelines.append([(r["phase"], r["patch_white"], r["flip_psychopy_s"]) for r in timing])
            for number in range(1, 9):
                rows = [r for r in timing if r["trial_number"] == str(number)]
                self.assertEqual(sum(r["stimulus_visible"] == "True" for r in rows), 30)
                self.assertEqual(sum(r["patch_white"] == "True" for r in rows), 12)
                flips = {r["transition"]: float(r["flip_psychopy_s"]) for r in rows if r["transition"]}
                self.assertAlmostEqual(flips["stimulus_offset"] - flips["stimulus_onset"], 0.5, places=6)
                self.assertAlmostEqual(flips["patch_offset"] - flips["stimulus_onset"], 0.2, places=6)
        self.assertTrue(all(timeline == timelines[0] for timeline in timelines[1:]))

    def test_escape_serial_display_and_close_errors_preserve_partial_data(self):
        for problem in ("escape", "serial", "display", "close"):
            with self.subTest(problem=problem):
                harness = Harness()
                harness.tail = b"A R 1 "
                if problem == "escape":
                    harness.escape_frame = 70
                elif problem == "serial":
                    harness.serial_error_poll = 140
                elif problem == "display":
                    harness.display_error_frame = 70
                else:
                    harness.close_error = True
                with tempfile.TemporaryDirectory() as directory:
                    result, trials, _, records, metadata = harness.run(directory)
                self.assertEqual(result, 130 if problem == "escape" else 1)
                self.assertEqual(metadata["status"], "interrupted" if problem == "escape" else "error")
                self.assertEqual(base64.b64decode(records[-1]["raw_base64"]), b"A R 1 ")
                self.assertEqual(records[-1]["kind"], "incomplete")
                self.assertTrue(harness.listener.closed and harness.window.closed)
                self.assertTrue(all(t["rt_ms"] == "" for t in trials))

    def test_disabled_patch_has_no_qualified_hardware_rt(self):
        harness = Harness()
        with tempfile.TemporaryDirectory() as directory:
            result, trials, timing, _, _ = harness.run(directory, ["--no-patch"])
        self.assertEqual(result, 0)
        self.assertTrue(all(t["rt_ms"] == "" and "patch_disabled" in t["exclusion_reason"] for t in trials))
        self.assertTrue(all(row["patch_white"] == "False" for row in timing))

    def test_missed_frame_excludes_rt_without_hiding_timing(self):
        harness = Harness()
        harness.delayed_frame = 80
        with tempfile.TemporaryDirectory() as directory:
            result, trials, timing, _, _ = harness.run(directory)
        self.assertEqual(result, 0)
        self.assertIn("visual_frame_delay", trials[0]["exclusion_reason"])
        self.assertTrue(any(row["frame_delayed"] == "True" for row in timing))
        self.assertTrue(all(trial["rt_ms"] == "300" for trial in trials[1:]))

    def test_export_retains_nonresponses_and_damaged_payloads(self):
        trials, records, timing = optical_session()
        for button in (3, 4):
            for edge, state in (("P", "press"), ("R", "release")):
                records.append(TPADRecord(len(records) + 1, "button", f"A {edge} {button} 999999".encode(),
                                          123, 456, "A", edge, button, button, state, 999999))
        records.append(TPADRecord(999, "malformed", b"\x00\xffbad", 789, 790))
        with tempfile.TemporaryDirectory() as directory:
            demo.save_session(Path(directory), {"status": "test"}, trials, records, timing)
            saved = [json.loads(line) for line in (Path(directory) / "events.jsonl").read_text().splitlines()]
        self.assertEqual([base64.b64decode(row["raw_base64"]) for row in saved], [r.raw for r in records])
        self.assertEqual([row["sequence"] for row in saved], [r.sequence for r in records])
        self.assertEqual(saved[-1]["rx_first_ns"], 789)

    def test_startup_failure_and_no_refresh_save_session(self):
        for failure in ("refresh", "handshake"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                harness = Harness()
                harness.refresh_hz = None if failure == "refresh" else 60
                harness.handshake_error = failure == "handshake"
                result, _, _, _, metadata = harness.run(directory)
                self.assertEqual(result, 1)
                self.assertEqual(metadata["status"], "error")
                self.assertTrue(harness.window.closed)


if __name__ == "__main__":
    unittest.main()
