r"""Real fullscreen GUI smoke; mocked listener, no serial device. Escape remains available."""

import csv
import json
import os
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import simon_demo_psychopy as demo


def main():
    (ROOT / ".cache" / "roaming").mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.environ["APPDATA"] = str(ROOT / ".cache" / "roaming")
    os.environ["MPLCONFIGDIR"] = str(ROOT / ".cache" / "matplotlib")
    os.environ["PSYCHOPYNOPACKAGES"] = "1"
    from psychopy import event, visual

    get_keys, real_rect = event.getKeys, visual.Rect
    started = False
    output = ROOT / ".cache" / "simon_demo_smoke"
    output.mkdir(parents=True, exist_ok=True)
    captured, white_frames = {}, []
    previous_white = False

    def start_once(keyList):
        nonlocal started
        keys = get_keys(keyList=keyList)
        if not started and "space" in keyList:
            started = True
            keys.append("space")
        return keys

    def capture_patch(win, **kwargs):
        rect = real_rect(win, **kwargs)
        original_draw = rect.draw
        # Inspect only our backbuffer BEFORE refresh measurement and acquisition.
        # Readback/image saving must never add work inside a timed white pulse.
        for label in ("black", "white"):
            win.clearBuffer()
            rect.fillColor = label
            original_draw()
            win.getMovieFrame(buffer="back")
            image = win.movieFrames.pop()
            image.save(output / f"patch_{label}.png")
            width, height = image.size
            inside = [(0, height - 1), (149, height - 1), (0, height - 150), (149, height - 150), (75, height - 75)]
            outside = [(150, height - 1), (0, height - 151)]
            captured[label] = dict(size=list(image.size), inside=[list(image.getpixel(p))[:3] for p in inside],
                                   outside=[list(image.getpixel(p))[:3] for p in outside])
            assert all(all(value >= 240 if label == "white" else value <= 10 for value in rgb)
                       for rgb in captured[label]["inside"]), captured[label]
            assert all(all(value <= 10 for value in rgb) for rgb in captured[label]["outside"]), captured[label]
        rect.fillColor = "black"
        win.clearBuffer()

        def draw():
            nonlocal previous_white
            original_draw()
            white = all(channel > 0.9 for channel in rect.fillColor)
            if white and not previous_white:
                white_frames.append(0)
            if white:
                white_frames[-1] += 1
            previous_white = white
        rect.draw = draw
        return rect

    listener = MagicMock(spec=demo.TPADListener)
    listener.poll.return_value = listener.close.return_value = []
    with patch("serial.Serial", side_effect=AssertionError("Smoke must not open hardware")), \
            patch.object(demo, "TPADListener", return_value=listener), \
            patch.object(demo, "OUTPUT_ROOT", output), patch.object(event, "getKeys", side_effect=start_once), \
            patch.object(visual, "Rect", side_effect=capture_patch):
        assert demo.main(["--port", "SIMULATED_NO_DEVICE"]) == 0  # Default fullscreen.
    directory = max((p for p in output.iterdir() if p.is_dir()), key=lambda p: p.name)
    session = json.loads((directory / "session.json").read_text(encoding="utf-8"))
    session.update(simulation=True, hardware_validation="Mocked listener; no physical tPAD test")
    (directory / "session.json").write_text(json.dumps(session, indent=2), encoding="utf-8")
    with (directory / "timing.csv").open(encoding="utf-8", newline="") as handle:
        timing = list(csv.DictReader(handle))
    pulse_durations, stimulus_durations = [], []
    for number in range(1, 9):
        transitions = {r["transition"]: r for r in timing if r["trial_number"] == str(number)}
        onset = float(transitions["stimulus_onset"]["flip_psychopy_s"])
        pulse_durations.append(1000 * (float(transitions["patch_offset"]["flip_psychopy_s"]) - onset))
        stimulus_durations.append(1000 * (float(transitions["stimulus_offset"]["flip_psychopy_s"]) - onset))
        assert int(transitions["patch_offset"]["frame"]) - int(transitions["stimulus_onset"]["frame"]) == session["frame_counts"]["patch"]
    width, height = session["window_size_px"]
    assert session["fullscreen"] and session["patch_position_px"] == [-width / 2 + 75, -height / 2 + 75]
    assert white_frames == [session["frame_counts"]["patch"]] * 8
    listener.close.assert_called_once()
    evidence = dict(simulation=True, serial_device_opened=False, session_directory=str(directory),
                    fullscreen=session["fullscreen"], window_size_px=[width, height], patch_position_px=session["patch_position_px"],
                    refresh_hz=session["refresh_hz"], white_frames=white_frames, patch_flip_durations_ms=pulse_durations,
                    stimulus_flip_durations_ms=stimulus_durations, pixel_checks=captured, dropped_frames=session["dropped_frames"],
                    poll_calls=listener.poll.call_count)
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
