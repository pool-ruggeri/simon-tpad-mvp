import base64
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_simon
from run_simon import OperatorAbort, Presentation, SessionFiles, load_config, present_trial
from test_tpad_serial import FakeSerial
from tpad_serial import Message, SerialFailure, TPadReader
from trial_logic import Trial


class FakeWindow:
    def __init__(self):
        self.frame = 0
        self.closed = False
        self.size = (1024, 768)

    def flip(self):
        self.frame += 1
        return self.frame / 60

    def close(self):
        self.closed = True


class FakePresentation:
    def __init__(self, config, press_frame=None):
        self.config = config
        self.refresh_hz = 60
        self.window = FakeWindow()
        self.reader = TPadReader(FakeSerial(), lambda record: None, lambda record: None)
        self.phases = []
        self.press_frame = press_frame
        self.sent_press = False

    def timer_sample(self, timeout_ms):
        # Hardware replies are independent of synthetic host flip timestamps.
        if not self.phases:
            return Message(1, b"500\n", "counter", tpad_ms=500)
        return Message(100, b"3000\n", "counter", tpad_ms=3000)

    def pump(self):
        if self.press_frame == self.window.frame and not self.sent_press:
            self.reader.connection.chunks.append(b"A P 1 1200\n")
            self.sent_press = True
        self.reader.poll()
        return []

    def draw(self, phase, trial=None):
        self.phases.append(phase)

    def black_frames(self, count):
        for _ in range(count):
            self.pump()
            self.draw("black")
            self.window.flip()


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(run_simon.ROOT / "config.json")

    def test_real_presenter_timeline_independent_of_early_response(self):
        outcomes = []
        # Skip the real grace wait only in this frame scheduling test.
        for response_frame in (None, 31, 45, 90):
            ui = FakePresentation(self.config, press_frame=response_frame)
            trial = Trial(1, "practice", "blue", "left")
            with patch("run_simon.time.perf_counter", side_effect=[0, 1]):
                present_trial(ui, trial, self.config)
            outcomes.append((ui.phases, trial.stimulus_flip_host_s,
                             trial.offset_flip_host_s, trial.visual_end_host_s))
            self.assertEqual(ui.phases.count("stimulus"), 30)
            self.assertAlmostEqual(trial.offset_flip_host_s - trial.stimulus_flip_host_s, 0.5)
            self.assertAlmostEqual(trial.visual_end_host_s - trial.stimulus_flip_host_s, 1.5)
            self.assertTrue(trial.completed)
        self.assertTrue(all(outcome == outcomes[0] for outcome in outcomes[1:]))

    def test_fixed_timeline_survives_partial_message_then_flags_it(self):
        ui = FakePresentation(self.config)
        ui.reader.connection.chunks.append(b"A P 1 12")
        trial = Trial(1, "practice", "blue", "left")
        with patch("run_simon.time.perf_counter", side_effect=[0, 1]):
            present_trial(ui, trial, self.config)
        self.assertEqual(ui.phases.count("stimulus"), 30)
        self.assertIn("unresolved_serial_fragment", trial.issues)

    def test_four_exports_roundtrip_raw_and_scientific_data(self):
        with tempfile.TemporaryDirectory() as root:
            files = SessionFiles(root, self.config)
            reader = TPadReader(FakeSerial([b"C P 1 1000\r\nA P 1 12", b"00\nA R 1 1300\nC R 1 1500\nnoise\n"]), files.raw, files.event)
            reader.poll()
            reader.poll()
            trial = Trial(1, "practice", "blue", "left", 500, 3000, 0, 100, completed=True)
            files.metadata["status"] = "synthetic_test_only"
            files.checkpoint([trial], reader.events)
            reader.close()
            files.close()
            self.assertEqual({path.name for path in files.directory.iterdir()},
                             {"trials.csv", "events.csv", "serial_raw.jsonl", "session.json"})
            with (files.directory / "trials.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual((rows[0]["rt_ms"], rows[0]["accuracy"]), ("200", "1"))
            with (files.directory / "events.csv").open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 4)
            records = [json.loads(line) for line in (files.directory / "serial_raw.jsonl").read_text(encoding="utf-8").splitlines()]
            wire = b"".join(base64.b64decode(record["raw_base64"]) for record in records if record["kind"] == "rx_chunk")
            self.assertEqual(wire, b"C P 1 1000\r\nA P 1 1200\nA R 1 1300\nC R 1 1500\nnoise\n")
            self.assertTrue(any(record.get("interpretation") == "unknown" for record in records))
            metadata = json.loads((files.directory / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["random_seed"], self.config["random_seed"])
            self.assertEqual(metadata["serial"]["timeout"], 0)

    def test_abort_serial_error_and_display_error_preserve_collected_data(self):
        for error in (OperatorAbort("Escape pressed"), SerialFailure("Disconnected"), RuntimeError("Display failed")):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as root:
                ui = FakePresentation(self.config)
                ui.instructions = lambda text: None
                ui.setup_device = lambda files: None
                def fail_after_collecting(presentation, trial, config):
                    presentation.reader.connection.chunks.append(b"C P 1 1000\nA P 1 1200\nC P 1 12")
                    presentation.reader.poll()
                    trial.lower_ms, trial.lower_sequence = 500, 0
                    raise error
                reader = TPadReader(FakeSerial(), lambda record: None, lambda record: None)
                def open_fake(port, raw_sink, event_sink):
                    reader.raw_sink, reader.event_sink = raw_sink, event_sink
                    return reader
                with patch("run_simon.Presentation", return_value=ui), patch("run_simon.TPadReader.open", side_effect=open_fake), patch("run_simon.present_trial", side_effect=fail_after_collecting):
                    exit_code = run_simon.run(self.config, root)
                directory = next(Path(root).iterdir())
                metadata = json.loads((directory / "session.json").read_text(encoding="utf-8"))
                self.assertEqual(metadata["status"], "aborted" if isinstance(error, OperatorAbort) else "error")
                self.assertEqual(exit_code, 0 if isinstance(error, OperatorAbort) else 1)
                with (directory / "events.csv").open(newline="", encoding="utf-8") as handle:
                    self.assertEqual(len(list(csv.DictReader(handle))), 2)
                with (directory / "trials.csv").open(newline="", encoding="utf-8") as handle:
                    row = next(csv.DictReader(handle))
                self.assertEqual(row["status"], "invalid")
                self.assertEqual(row["rt_ms"], "")
                records = [json.loads(line) for line in (directory / "serial_raw.jsonl").read_text(encoding="utf-8").splitlines()]
                self.assertTrue(any(record.get("interpretation") == "incomplete" for record in records))
                self.assertTrue(ui.window.closed)
                self.assertTrue(reader.connection.closed)

    def test_all_trials_complete_and_session_plan_exported(self):
        with tempfile.TemporaryDirectory() as root:
            ui = FakePresentation(self.config)
            ui.instructions = lambda text: None
            ui.setup_device = lambda files: None
            reader = TPadReader(FakeSerial(), lambda record: None, lambda record: None)
            def open_fake(port, raw_sink, event_sink):
                reader.raw_sink, reader.event_sink = raw_sink, event_sink
                return reader
            def collect(presentation, trial, config):
                base = trial.number * 4000
                trial.lower_ms = base
                trial.lower_sequence = reader.parser.sequence
                button = trial.correct_response
                reader.connection.chunks.append(f"C P 1 {base + 1000}\nA P {button} {base + 1200}\nA R {button} {base + 1300}\nC R 1 {base + 1500}\n".encode())
                reader.poll()
                trial.upper_ms, trial.upper_sequence = base + 3000, reader.parser.sequence + 1
                trial.completed = True
                trial.finalized_host_ns = run_simon.time.perf_counter_ns()
            with patch("run_simon.Presentation", return_value=ui), patch("run_simon.TPadReader.open", side_effect=open_fake), patch("run_simon.present_trial", side_effect=collect):
                self.assertEqual(run_simon.run(self.config, root), 0)
            directory = next(Path(root).iterdir())
            metadata = json.loads((directory / "session.json").read_text(encoding="utf-8"))
            self.assertEqual((metadata["status"], metadata["completed_trials"], metadata["valid_trials"]), ("completed", 20, 20))
            self.assertEqual(len(metadata["trial_plan"]), 20)

    def test_invalid_block_counts_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            config = {**self.config, "practice_trials": 3}
            path = Path(root) / "bad.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)

    def test_firmware_setup_and_timer_query_use_only_approved_commands(self):
        ui = FakePresentation(self.config)
        ui.request = Presentation.request.__get__(ui)
        ui.setup_device = Presentation.setup_device.__get__(ui)
        ui.timer_sample = Presentation.timer_sample.__get__(ui)
        def write(command):
            ui.reader.connection.writes.append(command)
            replies = {b"X": b"MODE 0:\r\n", b"FIRM\n": b"20250809\r\n",
                       b"MOD5\n": b"MODE 5:\r\n", b"T": b"1000\r\n"}
            ui.reader.connection.chunks.append(replies[command])
            return len(command)
        ui.reader.connection.write = write
        with tempfile.TemporaryDirectory() as root:
            files = SessionFiles(root, self.config)
            try:
                ui.setup_device(files)
                sample = ui.timer_sample(100)
                self.assertEqual(sample.tpad_ms, 1000)
                self.assertEqual(files.metadata["firmware_observed"], "20250809")
                self.assertTrue(files.metadata["operating_mode_confirmed"])
            finally:
                files.close()
        self.assertEqual(ui.reader.connection.writes, [b"X", b"FIRM\n", b"MOD5\n", b"T"])

    def test_request_timeout_and_escape_do_not_invent_timer_reply(self):
        ui = FakePresentation(self.config)
        ui.request = Presentation.request.__get__(ui)
        with self.assertRaises(SerialFailure):
            ui.request(b"T", lambda message: message.kind == "counter", 1)
        def abort():
            raise OperatorAbort("Escape pressed")
        ui.pump = abort
        with self.assertRaises(OperatorAbort):
            ui.request(b"T", lambda message: message.kind == "counter", 100)

    def test_firmware_mismatch_stops_before_mode_entry(self):
        ui = FakePresentation(self.config)
        ui.request = Presentation.request.__get__(ui)
        ui.setup_device = Presentation.setup_device.__get__(ui)
        def write(command):
            ui.reader.connection.writes.append(command)
            ui.reader.connection.chunks.append(b"MODE 0:\n" if command == b"X" else b"19990101\n")
            return len(command)
        ui.reader.connection.write = write
        with tempfile.TemporaryDirectory() as root:
            files = SessionFiles(root, self.config)
            try:
                with self.assertRaises(SerialFailure):
                    ui.setup_device(files)
            finally:
                files.close()
        self.assertEqual(ui.reader.connection.writes, [b"X", b"FIRM\n"])


if __name__ == "__main__":
    unittest.main()
