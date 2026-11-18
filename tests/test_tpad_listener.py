"""Exercise the standalone listener with a controlled serial stream and clock."""

from collections import deque
import unittest
from unittest.mock import patch

import serial

import tpad_listener
from tpad_listener import TPADListener


class FakeClock:
    def __init__(self):
        self.now_ns = 0

    def monotonic_ns(self):
        return self.now_ns

    def sleep(self, seconds):
        self.now_ns += round(seconds * 1_000_000_000)


class FakeSerial:
    def __init__(self, clock):
        self.clock = clock
        self.replies = {b"X": [b"MODE 0:\r\n"], b"MOD5\r\n": [b"MODE 5:\r\n"]}
        self.chunks = deque()
        self.writes = []
        self.read_sizes = []
        self.closes = 0

    def write(self, command):
        self.writes.append((command, self.clock.now_ns))
        self.chunks.extend(self.replies[command])
        return len(command)

    def read(self, size):
        self.read_sizes.append(size)
        if not self.chunks:
            return b""
        chunk = self.chunks.popleft()
        if len(chunk) > size:
            self.chunks.appendleft(chunk[size:])
        return chunk[:size]

    def close(self):
        self.closes += 1


class TPADListenerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.device = FakeSerial(self.clock)
        self.open_port = self.enterContext(patch.object(serial, "Serial", return_value=self.device))
        self.enterContext(patch.object(tpad_listener, "time", self.clock))

    def open_ready(self):
        listener = TPADListener("COM_TEST")
        self.addCleanup(listener.close)
        listener.poll()  # Consume setup replies in tests that start with an empty batch.
        return listener

    def test_handshake_config_spacing_and_early_events(self):
        self.device.replies[b"X"] = [b"MODE ", b"0:\t\r\nA P 4 101\r\n"]
        self.device.replies[b"MOD5\r\n"] = [b"MODE 5", b":\r\nC P 1 102\n"]
        with TPADListener("COM_TEST") as listener:
            self.open_port.assert_called_once_with(
                port="COM_TEST", baudrate=115200, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                timeout=0, write_timeout=0.1, xonxoff=False, rtscts=False, dsrdtr=False,
            )
            setup = listener.poll()
            self.assertEqual([record.kind for record in setup], ["mode", "button", "mode", "optical"])
            self.assertEqual([record.state for record in setup], ["MODE 0:", "press", "MODE 5:", "on"])
            self.assertEqual([record.sequence for record in setup], [1, 2, 3, 4])
            self.assertEqual([record.tpad_ms for record in setup], [None, 101, None, 102])
            self.assertEqual(setup[0].raw, b"MODE 0:\t")
            self.assertEqual(listener.poll(), [])
        self.assertEqual([command for command, _ in self.device.writes], [b"X", b"MOD5\r\n"])
        self.assertGreaterEqual(self.device.writes[1][1] - setup[0].rx_complete_ns, 25_000_000)
        self.assertEqual(self.device.closes, 1)

    def test_missing_mode_zero_refuses_other_or_unterminated_replies(self):
        self.device.replies[b"X"] = [b"MODE 1:\r\nMODE 0: extra\r\nMODE 0:"]
        with self.assertRaisesRegex(serial.SerialException, r"MODE 0:.*COM_TEST.*2 s"):
            TPADListener("COM_TEST")
        self.assertEqual(self.device.writes, [(b"X", 0)])
        self.assertEqual(self.clock.now_ns, 2_000_000_000)
        self.assertEqual(self.device.closes, 1)

    def test_missing_mode_five_refuses_replies_that_started_before_mod5(self):
        self.device.replies[b"X"] = [b"MODE 0:\r\nMODE 5:\r\nMODE 5"]
        self.device.replies[b"MOD5\r\n"] = [b":\r\nMODE 4:\r\n"]
        with self.assertRaisesRegex(serial.SerialException, r"MODE 5:.*COM_TEST.*2 s"):
            TPADListener("COM_TEST")
        self.assertEqual(self.device.writes, [(b"X", 0), (b"MOD5\r\n", 25_000_000)])
        self.assertEqual(self.clock.now_ns, 2_025_000_000)
        self.assertEqual(self.device.closes, 1)

    def test_short_write_closes_port(self):
        with patch.object(self.device, "write", return_value=0) as write:
            with self.assertRaisesRegex(serial.SerialException, "Incomplete write"):
                TPADListener("COM_TEST")
        write.assert_called_once_with(b"X")
        self.assertEqual(self.device.closes, 1)
        self.assertEqual(self.device.read_sizes, [])

    def test_initialization_read_error_and_interrupt_close_port(self):
        for error in (serial.SerialException("Read failed"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                closes_before = self.device.closes
                with patch.object(self.device, "read", side_effect=error):
                    with self.assertRaises(type(error)):
                        TPADListener("COM_TEST")
                self.assertEqual(self.device.closes, closes_before + 1)

    def test_all_four_button_presses_and_releases(self):
        listener = self.open_ready()
        lines = [f"A {edge} {button} {100 + button}".encode("ascii")
                 for button in range(1, 5) for edge in ("P", "R")]
        self.device.chunks.append(b"\r\n".join(lines) + b"\r\n")
        records = listener.poll()
        self.assertEqual([record.raw for record in records], lines)
        self.assertEqual([record.kind for record in records], ["button"] * 8)
        self.assertEqual([record.button for record in records], [1, 1, 2, 2, 3, 3, 4, 4])
        self.assertEqual([record.state for record in records], ["press", "release"] * 4)
        self.assertEqual([record.tpad_ms for record in records], [101, 101, 102, 102, 103, 103, 104, 104])

    def test_both_optical_channels_and_voice_key_edges(self):
        listener = self.open_ready()
        self.device.chunks.append(
            b"C P 1 100\nC R 1 120\nC P 2 130\nC R 2 150\nM P 1 170\nM R 1 240\n"
        )
        records = listener.poll()
        actual = [(r.kind, r.channel, r.sensor, r.edge, r.state, r.tpad_ms) for r in records]
        self.assertEqual(actual, [
            ("optical", "C", 1, "P", "on", 100), ("optical", "C", 1, "R", "off", 120),
            ("optical", "C", 2, "P", "on", 130), ("optical", "C", 2, "R", "off", 150),
            ("microphone", "M", 1, "P", "on", 170), ("microphone", "M", 1, "R", "off", 240),
        ])
        self.assertTrue(all(record.button is None for record in records))

    def test_auxiliary_channels_and_numeric_replies_are_retained(self):
        listener = self.open_ready()
        self.device.chunks.append(b"  A\tP 0005 0000 \t\rA P 10 17\nT R 1 18\n0019 \t\n")
        first, external, ttl_input, reply = listener.poll()
        self.assertEqual((first.kind, first.channel, first.sensor, first.tpad_ms), ("other", "A", 5, 0))
        self.assertEqual(first.raw, b"  A\tP 0005 0000 \t")
        self.assertEqual((external.kind, external.sensor, external.tpad_ms), ("other", 10, 17))
        self.assertEqual((ttl_input.kind, ttl_input.channel, ttl_input.edge), ("other", "T", "R"))
        self.assertEqual((reply.kind, reply.raw, reply.tpad_ms), ("reply", b"0019 \t", None))

    def test_every_two_chunk_split_including_crlf(self):
        listener = self.open_ready()
        stream = b"A P 1 12345\r\nC R 2 12345\rM P 1 12345\n"
        for split in range(len(stream) + 1):
            with self.subTest(split=split):
                self.device.chunks.extend((stream[:split], stream[split:]))
                records = listener.poll() + listener.poll()
                self.assertEqual([r.raw for r in records], [b"A P 1 12345", b"C R 2 12345", b"M P 1 12345"])
                self.assertEqual([r.tpad_ms for r in records], [12345, 12345, 12345])
                start = 3 + 3 * split
                self.assertEqual([r.sequence for r in records], list(range(start, start + 3)))

    def test_host_times_follow_first_payload_and_delimiter_reads(self):
        listener = self.open_ready()
        self.clock.sleep(1)
        first_ns = self.clock.now_ns
        for byte in b"C P 2 123":
            self.device.chunks.append(bytes([byte]))
            self.assertEqual(listener.poll(), [])
            self.clock.sleep(0.001)
        self.assertEqual(listener.poll(), [])
        self.clock.sleep(0.125)
        self.device.chunks.append(b"\nA R 1 124\n")
        first, second = listener.poll()
        self.assertEqual((first.tpad_ms, second.tpad_ms), (123, 124))
        self.assertEqual(first.rx_first_ns, first_ns)
        self.assertEqual(first.rx_complete_ns, self.clock.now_ns)
        self.assertEqual(second.rx_first_ns, second.rx_complete_ns)
        self.assertEqual(second.rx_complete_ns, first.rx_complete_ns)

    def test_repetitions_and_time_regressions_stay_in_receive_order(self):
        listener = self.open_ready()
        lines = [b"C P 1 100", b"C R 1 100", b"C P 1 100", b"A P 2 99", b"A P 2 99", b"C R 1 600"]
        self.device.chunks.append(b"\n".join(lines) + b"\n")
        records = listener.poll()
        self.assertEqual([record.raw for record in records], lines)
        self.assertEqual([record.sequence for record in records], list(range(3, 9)))
        self.assertEqual([record.tpad_ms for record in records], [100, 100, 100, 99, 99, 600])
        self.assertEqual([record.out_of_order for record in records], [False, False, False, True, True, False])

    def test_malformed_payloads_keep_original_bytes_and_next_line_recovers(self):
        listener = self.open_ready()
        bad_lines = [
            b"A P 1 unknown", b"C X 1 23", b"A P 1 -1", b"A P 1 1.5", b"\xff",
            b"A P 1 9007199254740993", b"Z P 1 12", b"A P 11 12", b"C P 3 13",
            b"M P 2 14", b"T P 0 15", b"\vA P 1 19", b"MODE 9:",
            b"A P 1 " + b"9" * 1000,
        ]
        valid = b"A P 4 " + b"0" * 1000 + b"9007199254740992"
        self.device.chunks.append(b"\n".join(bad_lines + [valid]) + b"\n")
        records = listener.poll()
        self.assertEqual([record.raw for record in records], bad_lines + [valid])
        for record in records[:-1]:
            self.assertEqual((record.kind, record.tpad_ms, record.sensor), ("malformed", None, None))
        self.assertEqual((records[-1].button, records[-1].tpad_ms), (4, 2**53))

    def test_overlong_lines_preserve_bytes_without_parsing_their_suffix(self):
        listener = self.open_ready()
        corrupt_line = b"x" * 8200 + b"A P 1 48"
        self.device.chunks.append(corrupt_line + b"\nA P 2 49\n")
        records = listener.poll() + listener.poll() + listener.poll()
        self.assertEqual([r.kind for r in records], ["malformed", "malformed", "malformed", "button"])
        self.assertEqual([len(record.raw) for record in records[:2]], [4096, 4096])
        self.assertEqual(b"".join(record.raw for record in records[:-1]), corrupt_line)
        self.assertEqual((records[-1].button, records[-1].tpad_ms), (2, 49))

    def test_poll_takes_one_bounded_read_even_with_a_backlog(self):
        listener = self.open_ready()
        initial_reads = len(self.device.read_sizes)
        self.device.chunks.append(b"A P 1 42\n" * 1000)
        records = listener.poll()
        self.assertEqual(self.device.read_sizes[initial_reads:], [4096])
        self.assertLess(len(records), 1000)
        records += listener.poll() + listener.poll()
        self.assertEqual([record.sequence for record in records], list(range(3, 1003)))
        self.assertEqual(listener.poll(), [])
        self.assertEqual(self.device.read_sizes[initial_reads:], [4096] * 4)

    def test_close_returns_unpolled_setup_and_fragment_without_reading(self):
        self.device.replies[b"MOD5\r\n"] = [b"MODE 5:\r\nA R 1 123"]
        listener = TPADListener("COM_TEST")
        self.addCleanup(listener.close)
        self.device.chunks.append(b"4\n")
        reads_before_close = len(self.device.read_sizes)
        mode_zero, mode_five, tail = listener.close()
        self.assertEqual((mode_zero.state, mode_five.state), ("MODE 0:", "MODE 5:"))
        self.assertEqual((tail.sequence, tail.kind, tail.raw), (3, "incomplete", b"A R 1 123"))
        self.assertIsNone(tail.tpad_ms)
        self.assertIsNone(tail.rx_complete_ns)
        self.assertEqual(self.device.closes, 1)
        self.assertEqual(listener.close(), [])
        with self.assertRaises(serial.PortNotOpenError):
            listener.poll()
        self.assertEqual(self.device.closes, 1)
        self.assertEqual(len(self.device.read_sizes), reads_before_close)

    def test_context_releases_port_and_retains_fragment_on_task_error(self):
        with self.assertRaisesRegex(RuntimeError, "Task failed"):
            with TPADListener("COM_TEST") as listener:
                self.device.chunks.append(b"A P 2 42\nA R 2 ")
                records = listener.poll()
                self.assertEqual(records[-1].tpad_ms, 42)
                raise RuntimeError("Task failed")
        self.assertEqual(self.device.closes, 1)
        self.assertEqual([r.raw for r in listener.close()], [b"A R 2 "])
        self.assertEqual(listener.close(), [])
        self.assertEqual(self.device.closes, 1)

    def test_read_failure_keeps_undelivered_records_available_to_close(self):
        self.device.replies[b"MOD5\r\n"] = [b"MODE 5:\r\nA P 1 9\nA R 1"]
        with TPADListener("COM_TEST") as listener:
            with patch.object(self.device, "read", side_effect=serial.SerialException("Disconnected")) as read:
                with self.assertRaisesRegex(serial.SerialException, "Disconnected"):
                    listener.poll()
                with self.assertRaises(serial.PortNotOpenError):
                    listener.poll()
                read.assert_called_once()
        self.assertEqual(self.device.closes, 1)
        self.assertEqual([r.kind for r in listener.close()], ["mode", "mode", "button", "incomplete"])

    def test_close_failure_does_not_mask_original_task_error(self):
        with patch.object(self.device, "close", side_effect=OSError("Close failed")) as close:
            with self.assertRaisesRegex(ValueError, "Task failed") as caught:
                with TPADListener("COM_TEST") as listener:
                    raise ValueError("Task failed")
            self.assertEqual(listener.close()[0].state, "MODE 0:")
        close.assert_called_once()
        self.assertIn("Close failed", caught.exception.__notes__[0])


if __name__ == "__main__":
    unittest.main()
