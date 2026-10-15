r"""Run explicitly: .\.venv\Scripts\python.exe tests\smoke_calibrate_opto.py.

Opens real windows for about 25 seconds. Injects input into this utility's own
window, checks rendered patch pixels, and transfers focus to a blank test window.
It never launches BBTK or contacts the T-Pad. 40 px/cm is synthetic test geometry.
"""

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibrate_opto import BLACK, WHITE, CalibrationWindow, ROOT


def send_mouse(app, x, y, pressed):
    # Win32 client coordinates have a top-left origin. Messages target our HWND.
    client_x = int((app.window.size[0] / 2 + x) / app.window.getContentScaleFactor())
    client_y = int((app.window.size[1] / 2 - y) / app.window.getContentScaleFactor())
    packed = client_x | (client_y << 16)
    ctypes.windll.user32.PostMessageW(app.window._hw_handle, 0x0200, 0, packed)
    ctypes.windll.user32.PostMessageW(app.window._hw_handle, 0x0201 if pressed else 0x0202, int(pressed), packed)
    assert app.step()


def send_key(app, name):
    from pyglet.window import key
    symbol = getattr(key, name.upper())
    app.window.winHandle.dispatch_event("on_key_press", symbol, 0)
    assert app.step()
    app.window.winHandle.dispatch_event("on_key_release", symbol, 0)


def check_pixels(app, expected):
    # GL_FRONT reads can be empty under the Windows compositor. Capture only our
    # visible client area instead, which also checks the topmost window behavior.
    from PIL import ImageGrab
    origin, rect = wintypes.POINT(0, 0), wintypes.RECT()
    assert ctypes.windll.user32.ClientToScreen(app.window._hw_handle, ctypes.byref(origin))
    assert ctypes.windll.user32.GetClientRect(app.window._hw_handle, ctypes.byref(rect))
    frame = ImageGrab.grab(bbox=(origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom), all_screens=True)
    scale = app.window.getContentScaleFactor()
    x = round(frame.width / 2 + app.position[0] / scale)
    y = round(frame.height / 2 - app.position[1] / scale)
    # Check the center and near all four patch corners, away from the outline.
    for dx, dy in ((0, 0), (-70, -70), (70, -70), (-70, 70), (70, 70)):
        actual = frame.getpixel((x + round(dx / scale), y + round(dy / scale)))[:3]
        if actual != expected:
            frame.save(ROOT / ".cache" / "opto_smoke_actual.png")
        assert actual == expected, (actual, expected, frame.size, (x + dx, y + dy))
    return frame


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    ruler_only = "--ruler-only" in sys.argv
    app = focus_window = None
    # A mistaken serial call would fail the smoke test immediately.
    with patch("serial.Serial", side_effect=AssertionError("Serial is forbidden in the patch utility")):
        try:
            app = CalibrationWindow(config, pixels_per_cm=None if ruler_only else 40)
            assert app.step()
            if ruler_only:
                assert app.pixels_per_cm is None
                initial_side = app.side
                send_key(app, "RIGHT")
                assert app.side == initial_side + 1
                send_key(app, "LEFT")
                assert app.side == initial_side
                send_key(app, "ENTER")
                assert app.pixels_per_cm == initial_side / 4
            send_mouse(app, -180, -80, True)
            first_position = tuple(app.position)
            send_mouse(app, -180, -80, False)
            send_mouse(app, 120, -100, True)
            send_mouse(app, 120, -100, False)
            assert first_position != tuple(app.position)
            assert tuple(app.position) == (120, -100), (app.position, app.window.size, app.window.clientSize, app.window.getContentScaleFactor())
            check_pixels(app, (0, 0, 0)).save(ROOT / ".cache" / "opto_smoke_black.png")
            if ruler_only:
                # Compare numeric endpoints to the actual legacy named-color
                # Rect defaults used by the unchanged Simon optical marker.
                from psychopy import visual
                reference = visual.Rect(app.window, fillColor="black", lineColor="black", autoLog=False)
                assert reference.colorSpace == app.patch.colorSpace == "rgb"
                assert tuple(reference.fillColor) == BLACK
                reference.fillColor = "white"
                assert tuple(reference.fillColor) == WHITE
                print("Ruler setup, reference marker colors, placement and black patch verified. Physical size is unmeasured.")
                return
            send_key(app, "SPACE")
            assert app.sequence.phase == "black"
            # This is an owned blank window, standing in for switching to BBTK.
            # A native STATIC window provides an independent focus target without
            # introducing a second OpenGL context into PsychoPy's render process.
            create_window = ctypes.windll.user32.CreateWindowExW
            create_window.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                      wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                      wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
            create_window.restype = wintypes.HWND
            focus_window = create_window(0, "STATIC", "Calibration focus smoke test",
                                          0x10CF0000, 15, 15, 250, 120, None, None, None, None)
            assert focus_window
            ctypes.windll.user32.SetForegroundWindow(focus_window)
            ctypes.windll.user32.GetForegroundWindow.restype = wintypes.HWND
            was_unfocused = False
            checked_white = False
            while app.sequence.phase != "completed":
                assert app.step()
                was_unfocused |= ctypes.windll.user32.GetForegroundWindow() != app.window._hw_handle
                if app.sequence.phase == "white" and not checked_white:
                    check_pixels(app, (255, 255, 255)).save(ROOT / ".cache" / "opto_smoke_white.png")
                    checked_white = True
            check_pixels(app, (0, 0, 0))
            assert checked_white and was_unfocused
            history = list(app.sequence.history)
            durations = [b["flip_s"] - a["flip_s"] for a, b in zip(history, history[1:])]
            assert all(abs(duration - 10) < 2 / app.refresh_hz for duration in durations), durations
            ctypes.windll.user32.DestroyWindow(focus_window)
            focus_window = None
            send_key(app, "SPACE")
            assert app.sequence.phase == "black"
            from pyglet.window import key
            app.window.winHandle.dispatch_event("on_key_press", key.ESCAPE, 0)
            assert not app.step()
            evidence = {"phase_history": history, "durations_s": durations,
                        "refresh_hz": app.refresh_hz, "placement_and_reposition": True,
                        "unfocused_sequence": True, "repeat_and_escape": True,
                        "black_white_pixels_verified": True, "serial_opened": False,
                        "pixels_per_cm": 40, "physical_scale": "synthetic, not ruler-verified"}
            (ROOT / ".cache" / "opto_smoke.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
        finally:
            if focus_window is not None:
                ctypes.windll.user32.DestroyWindow(focus_window)
            if app is not None:
                app.close()


if __name__ == "__main__":
    main()
