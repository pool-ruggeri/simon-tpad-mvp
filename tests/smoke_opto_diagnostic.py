r"""Run .\.venv\Scripts\python.exe tests\smoke_opto_diagnostic.py.

Real display and ten marker-only white/black pulses, with explicitly synthetic
505 ms serial pulses and one additional 2 ms activation. Never opens a device.
"""

import json
from pathlib import Path
import sys
import time
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import opto_diagnostic as diagnostic
from test_tpad_serial import FakeSerial
from tpad_serial import TPadReader
from trial_logic import frame_count


class SyntheticPad(FakeSerial):
    def __init__(self):
        super().__init__()
        self.clock = time.perf_counter()
        self.onset_ms = None
        self.pulses = 0

    def milliseconds(self):
        return int((time.perf_counter() - self.clock) * 1000)

    def write(self, data):
        self.writes.append(data)
        if data == b"MOD5\n":
            self.clock = time.perf_counter()
        replies = {b"X": b"MODE 0:\r\n", b"FIRM\n": b"20250809\r\n",
                   b"MOD5\n": b"MODE 5:\r\n", b"T": f"{self.milliseconds()}\r\n".encode()}
        self.chunks.append(replies[data])
        return len(data)

    def optical(self, edge):
        if edge == "P":
            self.onset_ms = self.milliseconds()
            wire = f"C P 1 {self.onset_ms}\r\n"
        else:
            self.pulses += 1
            wire = f"C R 1 {self.onset_ms + 505}\r\n"
            if self.pulses == 3:
                wire += f"C P 1 {self.onset_ms + 506}\r\nC R 1 {self.onset_ms + 508}\r\n"
        self.chunks.append(wire.encode())


def main():
    device = SyntheticPad()
    windows = []
    output_root = diagnostic.ROOT / ".cache" / "opto_diagnostic_smoke"

    class SmokeWindow(diagnostic.DiagnosticWindow):
        def __init__(self, config, files):
            self.previous_white = False
            self.white_frames = []
            self.wait_calls = 0
            files.metadata.update(simulation=True, hardware_validation="Synthetic GUI smoke; no physical T-Pad test")
            super().__init__(config, files)
            self.stimulus.draw = Mock(side_effect=AssertionError("Colored stimuli must not be drawn"))
            self.fixation.draw = Mock(side_effect=AssertionError("Fixation must not be drawn"))
            windows.append(self)

        def draw(self, phase, trial=None):
            super().draw(phase, trial)
            white = phase == "white"
            if white and not self.previous_white:
                self.white_frames.append(0)
                self.window.callOnFlip(device.optical, "P")
            elif self.previous_white and not white:
                self.window.callOnFlip(device.optical, "R")
            if white:
                self.white_frames[-1] += 1
            self.previous_white = white

        def wait_for_start(self):
            from pyglet.window import key
            self.wait_calls += 1
            if self.wait_calls == 2:
                # Capture only our rendered backbuffer. Other applications may
                # legitimately cover the window on a shared laboratory desktop.
                self.waiting = True
                self.update_panel(force=True)
                self.draw("instructions")
                self.window.getMovieFrame(buffer="back")
                self.window.movieFrames.pop().save(output_root / "summary_screen.png")
                self.window.flip()
            symbol = key.SPACE if self.wait_calls == 1 else key.ESCAPE
            self.window.callOnFlip(self.window.winHandle.dispatch_event, "on_key_press", symbol, 0)
            super().wait_for_start()

    config = diagnostic.load_config(diagnostic.ROOT / "config.json")
    config["full_screen"] = False
    with patch("serial.Serial", side_effect=AssertionError("Smoke must not open hardware")), \
            patch.object(diagnostic, "DiagnosticWindow", SmokeWindow), \
            patch.object(TPadReader, "open", side_effect=lambda port, raw, event: TPadReader(device, raw, event)):
        assert diagnostic.run(config, output_root) == 0
    directory = max((path for path in output_root.iterdir() if path.is_dir()), key=lambda path: path.name)
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    run = summary["runs"][0]
    assert summary["simulation"] is True
    assert run["status"] == "completed"
    assert run["presented_stimuli"] == run["complete_detected_pulses"] == run["matched_presentations"] == 10, run
    assert run["additional_short_activations"] == 1
    assert run["duration"]["mean_ms"] == 505
    assert windows[0].white_frames == [frame_count(500, windows[0].refresh_hz)] * 10
    windows[0].stimulus.draw.assert_not_called()
    windows[0].fixation.draw.assert_not_called()
    assert device.writes.count(b"MOD5\n") == 1
    assert all(command in (b"X", b"FIRM\n", b"MOD5\n", b"T") for command in device.writes)
    durations = [row["offset_flip_host_s"] - row["stimulus_flip_host_s"] for row in run["presentations"]]
    # This checks for major scheduling errors, not a guarantee against OS/GPU
    # frame misses. All observed frame warnings remain in the evidence below.
    assert all(abs(duration - 0.5) < 2 / windows[0].refresh_hz for duration in durations), durations
    evidence = {"session_directory": str(directory), "simulation": True,
                "presented": run["presented_stimuli"], "matched": run["matched_presentations"],
                "short_activations": run["additional_short_activations"], "white_frames": windows[0].white_frames,
                "display_white_durations_s": durations,
                "presentation_issues": [row["issues"] for row in run["presentations"]],
                "refresh_hz": windows[0].refresh_hz, "marker_size_px": summary["marker_size_px"],
                "marker_position_px": summary["marker_position_px"], "serial_device_opened": False}
    (output_root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
