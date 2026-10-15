import json
from pathlib import Path
import tempfile
import unittest

from calibrate_opto import Sequence, patch_position, profile_scale


class OptoCalibrationTests(unittest.TestCase):
    def test_ten_second_phases_are_anchored_to_their_actual_flips(self):
        sequence = Sequence()
        sequence.start()
        sequence.advance(1234)
        self.assertEqual(sequence.phase, "black")
        sequence.flipped(1234.5)
        sequence.advance(1244.49999)
        self.assertEqual(sequence.phase, "black")
        sequence.advance(1244.5)
        self.assertEqual(sequence.phase, "white")
        # A delayed white flip must still receive its own full ten seconds.
        sequence.flipped(1244.52)
        sequence.advance(1254.51999)
        self.assertEqual(sequence.phase, "white")
        sequence.advance(1254.52)
        self.assertEqual(sequence.phase, "completed")
        sequence.flipped(1254.53)
        self.assertEqual([entry["phase"] for entry in sequence.history], ["black", "white", "completed"])

    def test_space_during_sequence_does_not_restart_it_and_repeat_starts_black(self):
        sequence = Sequence()
        sequence.start()
        sequence.flipped(5)
        sequence.start()
        self.assertEqual(sequence.started_at, 5)
        sequence.advance(15)
        sequence.flipped(15)
        sequence.advance(25)
        sequence.flipped(25)
        sequence.start()
        self.assertEqual((sequence.phase, sequence.started_at), ("black", None))

    def test_patch_is_kept_whole_and_outside_instruction_area(self):
        self.assertEqual(patch_position((0, -50), 160, (1024, 768)), (0, -50))
        x, y = patch_position((10000, 10000), 160, (1024, 768))
        self.assertLessEqual(x + 80 + 14, 512)
        self.assertLessEqual(y + 80 + 14, 384 - 200)
        with self.assertRaises(ValueError):
            patch_position((0, 0), 800, (1024, 768))

    def test_default_monitor_is_rejected_and_calibrated_geometry_requires_resolution_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            data = {"2026_10_15": {"width": 50, "sizePix": [1920, 1080], "notes": "Measured lab display"}}
            (folder / "testMonitor.json").write_text(json.dumps(data), encoding="utf-8")
            self.assertIsNone(profile_scale([folder], (1920, 1080))[0])
            (folder / "LabDisplay.json").write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(profile_scale([folder], (1920, 1080))[0], 38.4)
            self.assertIsNone(profile_scale([folder], (1280, 720))[0])
            with self.assertRaises(ValueError):
                profile_scale([folder], (1280, 720), "LabDisplay")

    def test_multiple_profiles_require_explicit_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name, width in (("DisplayA", 50), ("DisplayB", 60)):
                data = {"2026_10_15": {"width": width, "sizePix": [1920, 1080]}}
                (folder / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
            self.assertIsNone(profile_scale([folder], (1920, 1080))[0])
            self.assertEqual(profile_scale([folder], (1920, 1080), "DisplayB")[0], 32)


if __name__ == "__main__":
    unittest.main()
