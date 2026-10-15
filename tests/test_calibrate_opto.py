import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from calibrate_opto import CalibrationWindow, PatchState, patch_position, profile_scale


class OptoCalibrationTests(unittest.TestCase):
    def test_initial_black_and_repeated_manual_toggles(self):
        state = PatchState()
        self.assertEqual(state.phase, "black")
        for expected in ("white", "black", "white", "black"):
            state.toggle()
            self.assertEqual(state.phase, expected)

    def test_space_requires_placement_and_idle_frames_preserve_color(self):
        app = CalibrationWindow.__new__(CalibrationWindow)
        app.window = Mock(size=(1024, 768))
        app.window.winHandle.has_exit = False
        app.event = Mock()
        app.mouse = Mock()
        app.mouse.getPos.return_value = (0, 0)
        app.patch, app.outline, app.title, app.status = Mock(), Mock(), Mock(), Mock()
        app.state, app.position, app.pending_click = PatchState(), None, None
        app.pixels_per_cm, app.side = 40, 160
        app.event.getKeys.return_value = ["space"]
        self.assertTrue(app.step())
        self.assertEqual(app.state.phase, "black")
        app.position = (0, -100)
        self.assertTrue(app.step())
        self.assertEqual(app.state.phase, "white")
        app.event.getKeys.return_value = []
        for _ in range(1200):
            self.assertTrue(app.step())
        self.assertEqual(app.state.phase, "white")
        app.pending_click = (120, -100)
        self.assertTrue(app.step())
        self.assertEqual(app.position, (120, -100))
        self.assertEqual(app.state.phase, "white")
        app.event.getKeys.return_value = ["space"]
        self.assertTrue(app.step())
        self.assertEqual(app.state.phase, "black")
        app.event.getKeys.return_value = ["escape"]
        self.assertFalse(app.step())

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
