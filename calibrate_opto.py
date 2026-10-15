"""Standalone 4 x 4 cm optical patch. No serial connection or device commands."""

import argparse
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
# run_simon.py: Window rgb background -1; Rect defaults to rgb and maps the
# named black/white colors to these endpoints. Keep the same display pipeline.
COLOR_SPACE = "rgb"
BLACK = (-1, -1, -1)
WHITE = (1, 1, 1)
PHASE_SECONDS = 10.0
HEADER_PX = 200
INTRO = "Click to create a 4 × 4 cm calibration patch and position it under the optical sensor."


@dataclass
class Sequence:
    """Start every ten-second interval at its actual presentation flip."""

    phase: str = "ready"
    started_at: float | None = None
    history: list = field(default_factory=list)

    def start(self):
        if self.phase in ("ready", "completed"):
            self.phase, self.started_at = "black", None

    def advance(self, next_flip):
        if self.started_at is not None and next_flip >= self.started_at + PHASE_SECONDS:
            if self.phase == "black":
                self.phase, self.started_at = "white", None
            elif self.phase == "white":
                self.phase, self.started_at = "completed", None

    def flipped(self, timestamp):
        if self.phase != "ready" and self.started_at is None:
            self.started_at = timestamp
            self.history.append({"phase": self.phase, "flip_s": timestamp})
            print(f"{self.phase}: flip {timestamp:.6f} s", flush=True)


def monitor_folders():
    """Read existing profiles before redirecting PsychoPy's process-local cache."""
    folders = [ROOT / ".cache" / "roaming" / "psychopy3" / "monitors"]
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        folders.append(Path(os.environ["APPDATA"]) / "psychopy3" / "monitors")
    folders.append(Path.home() / ".psychopy3" / "monitors")
    return list(dict.fromkeys(folders))


def profile_scale(folders, display_size, name=None):
    """Use geometry only, never a profile's gamma or the default testMonitor."""
    candidates = {}
    for folder in folders:
        for path in sorted(folder.glob("*.json")):
            if name is not None and path.stem != name:
                continue
            if path.stem.lower() == "testmonitor":
                continue
            try:
                calibrations = json.loads(path.read_text(encoding="utf-8"))
                latest = calibrations[max(calibrations)]
                width = float(latest["width"])
                pixels = tuple(latest["sizePix"])
                notes = str(latest.get("notes", "")).lower()
                if (not math.isfinite(width) or width <= 0 or pixels != tuple(display_size)
                        or "not very useful" in notes or "default" in notes):
                    continue
                candidates.setdefault(path.stem, (pixels[0] / width, f"monitor profile {path}"))
            except (OSError, ValueError, TypeError, KeyError):
                continue
    if len(candidates) == 1:
        return next(iter(candidates.values()))
    if name:
        raise ValueError(f"No usable calibrated profile named {name!r} matches this display resolution.")
    return None, "Use a ruler; no unique calibrated monitor profile matches this display."


def patch_position(position, side, window_size):
    """Keep the complete patch and its external outline below the instructions."""
    width, height = window_size
    half, margin = side / 2, 14
    left, right = -width / 2 + half + margin, width / 2 - half - margin
    bottom, top = -height / 2 + half + margin, height / 2 - HEADER_PX - half - margin
    if left > right or bottom > top:
        raise ValueError("A 4 cm patch does not fit below the instructions. Use a larger window in config.json.")
    return (max(left, min(right, position[0])), max(bottom, min(top, position[1])))


def load_psychopy():
    # Match the Simon launcher's isolation without importing its experiment or
    # serial modules. No preferences or monitor profiles outside this repo change.
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    if sys.platform == "win32":
        roaming = cache / "roaming"
        roaming.mkdir(exist_ok=True)
        # Prevent PsychoPy's legacy monitor-folder migration from moving an
        # existing per-user calibration into this project on first import.
        (roaming / "psychopy3" / "monitors").mkdir(parents=True, exist_ok=True)
        os.environ["APPDATA"] = str(roaming)
    os.environ["MPLCONFIGDIR"] = str(cache / "matplotlib")
    os.environ["PSYCHOPYNOPACKAGES"] = "1"
    from psychopy import event, visual
    return event, visual


def keep_visible(window):
    """Keep this Windows utility above BBTK without taking keyboard focus."""
    if sys.platform != "win32":
        raise RuntimeError("This utility's focus/visibility behavior is supported on Windows only.")
    import ctypes
    from ctypes import wintypes
    set_position = ctypes.windll.user32.SetWindowPos
    set_position.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                             ctypes.c_int, ctypes.c_int, wintypes.UINT]
    set_position.restype = wintypes.BOOL
    # HWND_TOPMOST; SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE. This affects this
    # window's lifetime only, not persistent Windows or device settings.
    if not set_position(window._hw_handle, -1, 0, 0, 0, 0, 0x0013):
        raise RuntimeError("Cannot keep the calibration window visible above other applications.")


class CalibrationWindow:
    """One window, one patch, one draw/flip loop; no pause on focus loss."""

    def __init__(self, config, pixels_per_cm=None, monitor=None):
        folders = monitor_folders()
        self.event, visual = load_psychopy()
        self.window = visual.Window(
            size=config["window_size"], screen=config["screen"], fullscr=False,
            units="pix", color=BLACK, colorSpace=COLOR_SPACE, winType="pyglet",
            waitBlanking=True, allowGUI=True, autoLog=False,
        )
        try:
            self.window.winHandle.set_caption("Optical calibration patch")
            keep_visible(self.window)
            if pixels_per_cm is not None:
                if not math.isfinite(pixels_per_cm) or pixels_per_cm <= 0:
                    raise ValueError("pixels-per-cm must be a finite positive number measured on this display.")
                self.scale_source = "operator-specified pixels per cm"
            elif self.window.getContentScaleFactor() == 1:
                screen = self.window.winHandle.screen
                pixels_per_cm, self.scale_source = profile_scale(folders, (screen.width, screen.height), monitor)
            else:
                if monitor:
                    raise ValueError("Verify high-DPI scaling with a ruler or --pixels-per-cm rather than a profile.")
                self.scale_source = "Use a ruler to account for this display's DPI scaling."
            self.pixels_per_cm = pixels_per_cm
            self.side = round(4 * pixels_per_cm) if pixels_per_cm else 160
            if self.side < 1:
                raise ValueError("The supplied scale makes 4 cm smaller than one drawing pixel.")
            patch_position((0, 0), self.side, self.window.size)
            self.position = None
            self.sequence = Sequence()
            self.mouse = self.event.Mouse(win=self.window, visible=True)
            self.pending_click = None
            self.window.winHandle.push_handlers(on_mouse_press=self.on_click)
            self.patch = visual.Rect(self.window, width=self.side, height=self.side,
                                     fillColor=BLACK, lineColor=BLACK, colorSpace=COLOR_SPACE, autoLog=False)
            self.outline = visual.Rect(self.window, width=self.side + 12, height=self.side + 12,
                                       fillColor=None, lineColor=WHITE, colorSpace=COLOR_SPACE, autoLog=False)
            width, height = self.window.size
            self.title = visual.TextStim(self.window, text=INTRO, color=WHITE, colorSpace=COLOR_SPACE,
                                         height=20, wrapWidth=width - 48, pos=(0, height / 2 - 40), autoLog=False)
            self.status = visual.TextStim(self.window, text="", color=WHITE, colorSpace=COLOR_SPACE,
                                          height=18, wrapWidth=width - 48, pos=(0, height / 2 - 125), autoLog=False)
            self.window.flip()
            refresh = self.window.getActualFrameRate(nIdentical=20, nMaxFrames=180, nWarmUpFrames=30)
            if refresh is None or refresh <= 0:
                raise RuntimeError("Cannot measure a stable refresh rate for timed calibration.")
            self.refresh_hz = refresh
            self.event.clearEvents()
            print(self.scale_source, flush=True)
        except BaseException:
            self.window.close()
            raise

    def on_click(self, x, y, button, modifiers):
        if button == 1:
            # Use the position AT the click, even if the pointer subsequently
            # moves before the next draw/flip loop processes the event.
            scale = self.window.getContentScaleFactor()
            self.pending_click = (x * scale - self.window.size[0] / 2,
                                  y * scale - self.window.size[1] / 2)

    def step(self):
        keys = self.event.getKeys(keyList=["escape", "space", "return", "left", "right"])
        if "escape" in keys or self.window.winHandle.has_exit:
            return False
        clicked, self.pending_click = self.pending_click, None
        running = self.sequence.phase in ("black", "white")
        if self.pixels_per_cm is None:
            # This outline has no claimed physical size until confirmed with a
            # real ruler. Measure BOTH sides; Enter accepts four physical cm.
            proposed = max(4, self.side + keys.count("right") - keys.count("left"))
            try:
                patch_position((0, 0), proposed, self.window.size)
                self.side = proposed
            except ValueError:
                pass
            if "return" in keys:
                self.pixels_per_cm = self.side / 4
                self.scale_source = f"ruler-confirmed {self.pixels_per_cm:g} pixels per cm"
                print(self.scale_source, flush=True)
        elif clicked is not None and not running:
            self.position = patch_position(clicked, self.side, self.window.size)
        if "space" in keys and self.position is not None:
            self.sequence.start()
        self.sequence.advance(self.window.getFutureFlipTime())
        over_patch = (self.position is not None and
                      all(abs(a - b) <= self.side / 2 + 6 for a, b in zip(self.mouse.getPos(), self.position)))
        self.mouse.setVisible(self.sequence.phase not in ("black", "white") and not over_patch)
        self.patch.size = (self.side, self.side)
        self.outline.size = (self.side + 12, self.side + 12)
        if self.pixels_per_cm is None:
            self.status.text = ("Physical size is not calibrated. Measure between opposite border-line centers.\n"
                                "Use Left/Right to make BOTH sides exactly 4 cm with a ruler.\n"
                                "Press Return to confirm; then click to place the patch. Escape closes.")
            self.outline.size = (self.side, self.side)
            self.outline.pos = patch_position((0, -HEADER_PX / 2), self.side, self.window.size)
            self.outline.draw()
        else:
            if self.sequence.phase == "completed":
                message = "Calibration sequence completed.\nSpace repeats; click to reposition. Escape closes."
            elif self.sequence.phase in ("black", "white"):
                message = "Calibration running: 10 s black, then 10 s white, then black.\nSwitch to BBTK as needed; the sequence continues. Escape closes when this window has focus."
            else:
                message = "Click below these instructions to place or reposition the black patch.\nSpace starts: 10 s black, then 10 s white, then black. Escape closes."
            self.status.text = f"{message}\nScale: {self.pixels_per_cm:g} px/cm. Keep this window on the calibrated display."
            if self.position is not None:
                self.patch.pos = self.outline.pos = self.position
                color = WHITE if self.sequence.phase == "white" else BLACK
                self.patch.fillColor = self.patch.lineColor = color
                self.outline.draw()
                self.patch.draw()
        self.title.draw()
        self.status.draw()
        self.sequence.flipped(self.window.flip())
        return True

    def close(self):
        try:
            self.window.clearBuffer()
            self.window.flip()
        finally:
            self.window.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixels-per-cm", type=float, help="Measured PsychoPy drawing pixels per physical cm on this display.")
    parser.add_argument("--monitor", help="Name of an existing calibrated PsychoPy monitor profile (geometry only).")
    args = parser.parse_args()
    if args.monitor and args.pixels_per_cm is not None:
        parser.error("Choose either a monitor profile or pixels-per-cm.")
    app = None
    try:
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        app = CalibrationWindow(config, args.pixels_per_cm, args.monitor)
        while app.step():
            pass
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"Calibration utility failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
