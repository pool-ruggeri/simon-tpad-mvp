"""Check the capture command using mocked listener records."""

import base64
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import capture_tpad
from tpad_listener import TPADListener, TPADRecord


class CaptureTPADTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.output = Path(directory) / "output"
        self.listener = MagicMock(spec=TPADListener)
        self.open_listener = self.enterContext(
            patch.object(capture_tpad, "TPADListener", return_value=self.listener)
        )
        self.enterContext(patch.object(capture_tpad, "OUTPUT_DIR", self.output))
        self.sleep = self.enterContext(patch.object(capture_tpad, "sleep"))
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(redirect_stdout(self.stdout))
        self.enterContext(redirect_stderr(self.stderr))

    def assert_saved(self, expected_records):
        files = list(self.output.glob("tpad_capture_*.jsonl"))
        self.assertEqual(len(files), 1)
        rows = files[0].read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), len(expected_records))
        for row, expected in zip(rows, expected_records):
            record = json.loads(row)
            record["raw"] = base64.b64decode(record.pop("raw_base64"), validate=True)
            self.assertEqual(record, asdict(expected))

    def test_button_capture_prints_live_and_saves_every_record(self):
        batch = [
            TPADRecord(1, "mode", b"MODE 0:\t", 10, 11, state="MODE 0:"),
            TPADRecord(2, "mode", b"MODE 5:", 20, 21, state="MODE 5:"),
        ]
        for button in range(1, 5):
            for edge, state in (("P", "press"), ("R", "release")):
                sequence = len(batch) + 1
                stamp = sequence - 3
                raw = f"A {edge} {button} {stamp}".encode("ascii")
                batch.append(TPADRecord(
                    sequence, "button", raw, 101, 102, channel="A", edge=edge,
                    sensor=button, button=button, state=state, tpad_ms=stamp,
                ))
        malformed = TPADRecord(11, "malformed", b"\x00\xffbad", 202, 203)
        batch.append(malformed)
        tail = TPADRecord(12, "incomplete", b"A P 2 ", 300, None)
        self.listener.poll.return_value = batch
        self.listener.close.return_value = [tail]

        def check_live(_seconds):
            terminal = self.stdout.getvalue()
            for record in batch[2:10]:
                self.assertIn(
                    f"B{record.button} {record.state} | tPAD {record.tpad_ms} ms", terminal
                )
            self.assertIn("MODE 0:", terminal)
            self.assertIn("MODE 5:", terminal)
            self.assertIn(f"malformed {malformed.raw!r}", terminal)

        self.sleep.side_effect = check_live
        with patch.object(capture_tpad, "monotonic", side_effect=[0, 0, 30]):
            self.assertEqual(capture_tpad.main(["--port", "COM3", "--duration", "30"]), 0)
        self.open_listener.assert_called_once_with("COM3")
        self.sleep.assert_called_once()
        self.listener.__exit__.assert_called_once_with(None, None, None)
        self.listener.close.assert_called_once()
        self.assertIn(f"incomplete {tail.raw!r}", self.stdout.getvalue())
        self.assert_saved(batch + [tail])

    def test_ctrl_c_during_output_saves_the_full_batch_and_closes(self):
        batch = [
            TPADRecord(1, "mode", b"MODE 0:", 10, 11, state="MODE 0:"),
            TPADRecord(2, "mode", b"MODE 5:", 20, 21, state="MODE 5:"),
            TPADRecord(3, "malformed", b"\xff", 30, 31),
        ]
        tail = TPADRecord(4, "incomplete", b"A R 1 ", 32, None)
        self.listener.poll.return_value = batch
        self.listener.close.return_value = [tail]
        with patch.object(capture_tpad, "monotonic", side_effect=[0, 0]), \
                patch.object(capture_tpad, "show_record", side_effect=[None, KeyboardInterrupt(), None]):
            self.assertEqual(capture_tpad.main(["--port", "COM3"]), 130)
        self.listener.__exit__.assert_called_once()
        self.assertIs(self.listener.__exit__.call_args.args[0], KeyboardInterrupt)
        self.listener.close.assert_called_once()
        self.assertIn("Capture stopped with Ctrl+C.", self.stdout.getvalue())
        self.assert_saved(batch + [tail])

    def test_serial_error_reports_failure_and_saves_received_records(self):
        mode = TPADRecord(1, "mode", b"MODE 0:", 10, 11, state="MODE 0:")
        self.listener.poll.side_effect = [[mode], OSError("Disconnected")]
        self.listener.close.return_value = []
        with patch.object(capture_tpad, "monotonic", side_effect=[0, 0, 1]):
            self.assertEqual(capture_tpad.main(["--port", "COM3"]), 1)
        self.listener.__exit__.assert_called_once()
        self.listener.close.assert_called_once()
        self.assertIn("Disconnected", self.stderr.getvalue())
        self.assert_saved([mode])


if __name__ == "__main__":
    unittest.main()
