import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import opto_diagnostic as diagnostic
from opto_diagnostic import DiagnosticFiles, analyze, pair_optical_events
from run_simon import load_config, present_trial
from test_runner import FakePresentation
from test_tpad_serial import FakeSerial
from tpad_serial import Message, SerialFailure, TPadReader
from trial_logic import Trial


def read_events(wire):
    reader = TPadReader(FakeSerial([wire]), lambda record: None, lambda record: None)
    reader.poll()
    return reader.events


def make_run(count=3):
    trials = [Trial(i + 1, "opto_diagnostic", "blue", "left",
                    lower_ms=i * 3000 + 500, upper_ms=i * 3000 + 2900,
                    lower_sequence=0, upper_sequence=100000,
                    stimulus_flip_host_s=999999 + i, offset_flip_host_s=999999.5 + i,
                    completed=True) for i in range(count)]
    return {"number": 1, "status": "completed", "trials": trials,
            "end_boundary": (count * 3000, 100000)}


class OptoDiagnosticTests(unittest.TestCase):
    def test_existing_reader_partial_lines_and_hardware_durations(self):
        reader = TPadReader(FakeSerial([b"C P 1 100", b"0\r\nC R 1 1505\r\n"]), lambda row: None, lambda row: None)
        reader.poll()
        reader.poll()
        optical, pulses, unpaired = pair_optical_events(reader.events)
        self.assertEqual([event.edge for event in optical], ["P", "R"])
        self.assertEqual(pulses[0]["duration_ms"], 505)
        self.assertEqual(unpaired, [])

    def test_short_activations_separate_from_full_pulses_and_duplicates(self):
        events = read_events(b"C P 1 1000\nC P 1 1000\nC R 1 1505\nC P 1 1506\nC R 1 1508\n")
        result = analyze(events, [make_run(1)])
        run = result["runs"][0]
        self.assertEqual((run["on_events"], run["off_events"], run["complete_detected_pulses"]), (2, 2, 1))
        self.assertEqual((run["additional_short_activations"], run["duplicate_events"]), (1, 1))
        self.assertEqual(run["duration"]["mean_ms"], 505)
        self.assertEqual(run["matched_presentations"], 1)
        self.assertEqual([pulse["duration_ms"] for pulse in result["pulses"]], [505, 2])

    def test_missing_on_and_off_are_unpaired_without_invented_pulses(self):
        events = read_events(b"C R 1 1505\nC P 1 4000\n")
        result = analyze(events, [make_run(2)])
        run = result["runs"][0]
        self.assertEqual(run["complete_detected_pulses"], 0)
        self.assertEqual(run["unpaired_events"], 2)
        self.assertEqual(run["missing_or_ambiguous_pulses"], 2)
        self.assertIsNone(run["duration"]["mean_ms"])
        self.assertEqual(result["optical_state"], "ON")

    def test_repeated_on_edges_are_ambiguous_and_later_pulses_recover(self):
        events = read_events(b"C P 1 1000\nC P 1 4000\nC R 1 4505\nC P 1 7000\nC R 1 7505\n")
        result = analyze(events, [make_run(3)])
        run = result["runs"][0]
        self.assertEqual(run["unpaired_events"], 3)
        self.assertEqual([row["association"] for row in run["presentations"]], ["ambiguous", "ambiguous", "matched"])
        self.assertEqual(result["pulses"][0]["presentation_number"], 3)
        self.assertEqual(run["onset_interval"]["count"], 0)

    def test_extra_full_pulses_never_shift_subsequent_matching(self):
        events = read_events(b"C P 1 1000\nC R 1 1505\nC P 1 1800\nC R 1 2306\n"
                             b"C P 1 4000\nC R 1 4503\n")
        result = analyze(events, [make_run(2)])
        run = result["runs"][0]
        self.assertEqual(run["complete_detected_pulses"], 3)
        self.assertEqual(run["matched_presentations"], 1)
        self.assertEqual(run["missing_or_ambiguous_pulses"], 1)
        self.assertEqual([row["association"] for row in run["presentations"]], ["ambiguous", "matched"])

    def test_summary_statistics_use_hardware_only_and_accept_non_500ms_pulses(self):
        events = read_events(b"C P 1 1000\nC R 1 1503\nC P 1 4000\nC R 1 4505\nC P 1 7000\nC R 1 7507\n")
        result = analyze(events, [make_run(3)])
        run = result["runs"][0]
        self.assertEqual(run["matched_presentations"], 3)
        self.assertEqual((run["duration"]["mean_ms"], run["duration"]["median_ms"]), (505, 505))
        self.assertEqual((run["duration"]["min_ms"], run["duration"]["max_ms"]), (503, 507))
        self.assertAlmostEqual(run["duration"]["sd_ms"], math.sqrt(8 / 3))
        self.assertEqual((run["onset_interval"]["mean_ms"], run["onset_interval"]["sd_ms"]), (3000, 0))
        invalid = analyze(events, [make_run(3)], clock_uncertain=True)["runs"][0]
        self.assertIsNone(invalid["duration"]["mean_ms"])

    def test_pulses_crossing_boundaries_or_received_beyond_grace_are_ambiguous(self):
        run = make_run(2)
        result = analyze(read_events(b"C P 1 2800\nC R 1 3600\n"), [run])
        self.assertEqual([row["association"] for row in result["runs"][0]["presentations"]], ["ambiguous", "ambiguous"])
        run = make_run(1)
        run["trials"][0].finalized_host_ns = 1
        result = analyze(read_events(b"C P 1 1000\nC R 1 1505\n"), [run])
        self.assertEqual(result["runs"][0]["presentations"][0]["association"], "ambiguous")

    def test_actual_simon_frame_schedule_is_reused_without_event_driven_offset(self):
        config = load_config(diagnostic.ROOT / "config.json")
        for press in (None, 31):
            ui = FakePresentation(config, press_frame=press)
            trial = Trial(1, "opto_diagnostic", "blue", "left")
            with patch("run_simon.time.perf_counter", side_effect=[0, 1]):
                present_trial(ui, trial, config)
            self.assertEqual(ui.phases[:30], ["fixation"] * 30)
            self.assertEqual(ui.phases[30:60], ["stimulus"] * 30)
            self.assertEqual(ui.phases[60:120], ["response"] * 60)
            self.assertAlmostEqual(trial.offset_flip_host_s - trial.stimulus_flip_host_s, 0.5)

    def test_four_diagnostic_files_preserve_short_events_and_raw_content(self):
        config = load_config(diagnostic.ROOT / "config.json")
        with tempfile.TemporaryDirectory() as root:
            files = DiagnosticFiles(root, config, 10)
            reader = TPadReader(FakeSerial([b"C P 1 1000\nC R 1 1505\nC P 1 1506\nC R 1 1508\nnoise\n"]), files.raw, files.event)
            reader.poll()
            files.runs.append(make_run(1))
            files.checkpoint(reader.events)
            reader.close()
            files.close()
            self.assertEqual({p.name for p in files.directory.iterdir()},
                             {"serial_raw.jsonl", "optical_events.csv", "pulses.csv", "summary.json"})
            with (files.directory / "pulses.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["duration_ms"] for row in rows], ["505", "2"])
            with (files.directory / "optical_events.csv").open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 4)
            summary = json.loads((files.directory / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["runs"][0]["additional_short_activations"], 1)
            self.assertIn("noise", (files.directory / "serial_raw.jsonl").read_text(encoding="utf-8"))

    def test_repeats_keep_one_connection_and_do_not_reset_setup(self):
        config = load_config(diagnostic.ROOT / "config.json")
        instances = []
        class FakeUI(FakePresentation):
            def __init__(self, config, files):
                super().__init__(config)
                self.files, self.waits, self.setups, self.end_ms = files, 0, 0, 0
                instances.append(self)
            def wait_for_start(self):
                self.waits += 1
                if self.waits > 2:
                    raise diagnostic.OperatorAbort()
            def setup_device(self, files):
                self.setups += 1
            def update_panel(self, force=False):
                pass
            def timer_sample(self, timeout_ms):
                return Message(self.reader.parser.sequence + 1, b"", "counter", tpad_ms=self.end_ms)
        def collect(ui, trial, config):
            base = len(ui.files.runs) * 40000 + trial.number * 3000
            trial.lower_ms, trial.lower_sequence = base + 500, ui.reader.parser.sequence
            ui.reader.connection.chunks.append(f"C P 1 {base + 1000}\nC R 1 {base + 1505}\n".encode())
            ui.reader.poll()
            trial.upper_ms, trial.upper_sequence = base + 2900, ui.reader.parser.sequence + 1
            trial.stimulus_flip_host_s, trial.offset_flip_host_s = 1000000, 1000000.5
            trial.completed = True
            ui.end_ms = base + 3000
        with tempfile.TemporaryDirectory() as root:
            with patch.object(diagnostic, "DiagnosticWindow", FakeUI), \
                    patch.object(TPadReader, "open", side_effect=lambda port, raw, event: TPadReader(FakeSerial(), raw, event)) as opened, \
                    patch.object(diagnostic, "present_trial", side_effect=collect):
                self.assertEqual(diagnostic.run(config, root), 0)
            summary = json.loads(next(Path(root).glob("*/summary.json")).read_text(encoding="utf-8"))
            self.assertEqual([run["matched_presentations"] for run in summary["runs"]], [10, 10])
            self.assertEqual(instances[0].setups, 1)
            self.assertEqual(opened.call_count, 1)

    def test_error_preserves_completed_pulse_and_incomplete_raw_fragment(self):
        config = load_config(diagnostic.ROOT / "config.json")
        class FakeUI(FakePresentation):
            def __init__(self, config, files):
                super().__init__(config)
                self.files = files
            def wait_for_start(self):
                pass
            def setup_device(self, files):
                pass
            def update_panel(self, force=False):
                pass
        def collect(ui, trial, config):
            base = trial.number * 3000
            trial.lower_ms, trial.lower_sequence = base + 500, ui.reader.parser.sequence
            wire = f"C P 1 {base + 1000}\n"
            wire += f"C R 1 {base + 1505}\n" if trial.number == 1 else "C R 1 45"
            ui.reader.connection.chunks.append(wire.encode())
            ui.reader.poll()
            trial.stimulus_flip_host_s = 10000
            if trial.number == 2:
                raise SerialFailure("Synthetic disconnection")
            trial.upper_ms, trial.upper_sequence = base + 2900, ui.reader.parser.sequence + 1
            trial.completed = True
        with tempfile.TemporaryDirectory() as root:
            with patch.object(diagnostic, "DiagnosticWindow", FakeUI), \
                    patch.object(TPadReader, "open", side_effect=lambda port, raw, event: TPadReader(FakeSerial(), raw, event)), \
                    patch.object(diagnostic, "present_trial", side_effect=collect):
                self.assertEqual(diagnostic.run(config, root), 1)
            directory = next(Path(root).iterdir())
            summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "error")
            self.assertEqual(summary["runs"][0]["complete_detected_pulses"], 1)
            self.assertTrue(summary["unresolved_serial_fragment"])
            self.assertIn('"interpretation": "incomplete"', (directory / "serial_raw.jsonl").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
