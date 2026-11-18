r"""Run .\.venv\Scripts\python.exe tests\smoke_simon_demo_psychopy.py.

Real PsychoPy window, eight trials, empty mocked listener. No hardware is opened.
This checks visual scheduling, not sensor timing or scientific RT qualification.
"""

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
    # Configure local preferences before the smoke's own PsychoPy import.
    (ROOT / ".cache" / "roaming").mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.environ["APPDATA"] = str(ROOT / ".cache" / "roaming")
    os.environ["MPLCONFIGDIR"] = str(ROOT / ".cache" / "matplotlib")
    os.environ["PSYCHOPYNOPACKAGES"] = "1"
    from psychopy import event

    get_keys = event.getKeys
    started = False

    def start_once(keyList):
        nonlocal started
        keys = get_keys(keyList=keyList)  # Real Escape remains available.
        if not started and "space" in keyList:
            started = True
            keys.append("space")
        return keys

    listener = MagicMock(spec=demo.TPADListener)
    listener.poll.return_value = []
    listener.close.return_value = []
    output = ROOT / ".cache" / "simon_demo_smoke"
    with patch("serial.Serial", side_effect=AssertionError("Smoke must not open hardware")), \
            patch.object(demo, "TPADListener", return_value=listener), \
            patch.object(demo, "OUTPUT_ROOT", output), patch.object(event, "getKeys", side_effect=start_once):
        assert demo.main(["--windowed", "--port", "SIMULATED_NO_DEVICE"]) == 0
    directory = max((path for path in output.iterdir() if path.is_dir()), key=lambda path: path.name)
    metadata = json.loads((directory / "session.json").read_text(encoding="utf-8"))
    metadata.update(simulation=True, hardware_validation="Empty mocked listener; no physical tPAD test")
    (directory / "session.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    with (directory / "timing.csv").open(encoding="utf-8", newline="") as handle:
        timing = list(csv.DictReader(handle))
    durations, patch_durations = [], []
    for number in range(1, 9):
        transitions = {row["transition"]: float(row["flip_psychopy_s"]) for row in timing
                       if row["trial_number"] == str(number) and row["transition"]}
        durations.append(transitions["stimulus_offset"] - transitions["stimulus_onset"])
        patch_durations.append(transitions["patch_offset"] - transitions["stimulus_onset"])
    listener.close.assert_called_once()
    # Frame counts are the portable assertion. Retain observed misses, which
    # can occur on this workstation, rather than calling them hardware success.
    for number in range(1, 9):
        rows = [row for row in timing if row["trial_number"] == str(number)]
        assert sum(row["stimulus_visible"] == "True" for row in rows) == metadata["frame_counts"]["stimulus"]
        assert sum(row["patch_white"] == "True" for row in rows) == metadata["frame_counts"]["patch"]
    evidence = dict(simulation=True, serial_device_opened=False, session_directory=str(directory),
                    refresh_hz=metadata["refresh_hz"], stimulus_flip_durations_s=durations,
                    patch_flip_durations_s=patch_durations, poll_calls=listener.poll.call_count,
                    delayed_frames=sum(row["frame_delayed"] == "True" for row in timing))
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
