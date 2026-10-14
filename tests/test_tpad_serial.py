import base64
import unittest

from tpad_serial import SerialFailure, TPadReader, XiDParser


class FakeSerial:
    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.writes = []
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, size):
        data = self.chunks.pop(0)
        if len(data) > size:
            self.chunks.insert(0, data[size:])
        return data[:size]

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def close(self):
        self.closed = True


class ParserTests(unittest.TestCase):
    def test_documented_messages_and_all_four_buttons(self):
        parser = XiDParser()
        data = b"A P 1 12345\r\nA R 1 12500\nC P 1 13000\rC R 1 13500\n"
        messages = parser.feed(data)
        self.assertEqual([(m.channel, m.edge, m.sensor, m.tpad_ms) for m in messages],
                         [("A", "P", 1, 12345), ("A", "R", 1, 12500),
                          ("C", "P", 1, 13000), ("C", "R", 1, 13500)])
        self.assertTrue(all(m.kind == "event" for m in messages))
        for button in range(1, 5):
            self.assertEqual(parser.feed(f"A P {button} 14000\n".encode())[0].kind, "event")

    def test_every_possible_split_including_crlf(self):
        wire = b"A P 1 12345\r\nC P 1 13000\r\n"
        for split in range(len(wire) + 1):
            with self.subTest(split=split):
                parser = XiDParser()
                messages = parser.feed(wire[:split]) + parser.feed(wire[split:])
                self.assertEqual([m.tpad_ms for m in messages], [12345, 13000])
                self.assertEqual([m.sequence for m in messages], [1, 2])

    def test_bytewise_stream_and_missing_terminator(self):
        parser = XiDParser()
        messages = []
        for value in b"A P 2 1600\n":
            messages.extend(parser.feed(bytes([value])))
        self.assertEqual(len(messages), 1)
        self.assertEqual(parser.feed(b"C P 1 5000"), [])
        fragment = parser.finish()[0]
        self.assertEqual(fragment.kind, "incomplete")
        self.assertIsNone(fragment.tpad_ms)
        self.assertEqual(fragment.raw, b"C P 1 5000")

    def test_malformed_unknown_and_extra_sensor_are_preserved(self):
        parser = XiDParser()
        messages = parser.feed(b"A P 1 invalid\nnoise\n\xff\nA P 5 50\nZ P 1 60\nC P 1 -1\n")
        self.assertEqual([m.kind for m in messages], ["malformed", "unknown", "malformed", "unexpected", "unexpected", "malformed"])
        self.assertEqual(messages[2].raw, b"\xff\n")

    def test_setup_replies_and_timer_counters(self):
        messages = XiDParser().feed(b"MODE 0:\n20250809\nMODE 5:\n12345\n")
        self.assertEqual([m.kind for m in messages], ["mode", "counter", "mode", "counter"])

    def test_overlong_unterminated_data_is_audited(self):
        parser = XiDParser(max_line_bytes=20)
        self.assertEqual(parser.feed(b"x" * 21)[0].kind, "incomplete")
        self.assertFalse(parser.buffer)


class ReaderTests(unittest.TestCase):
    def reader(self, chunks):
        raw, events = [], []
        return TPadReader(FakeSerial(chunks), raw.append, events.append), raw, events

    def test_duplicates_and_held_button_are_not_new_responses(self):
        reader, raw, events = self.reader([b"A P 1 100\nA P 1 100\nA P 1 120\nA R 1 200\n"])
        reader.poll()
        self.assertEqual([event["duplicate"] for event in events], [False, True, False, False])
        self.assertTrue(events[2]["unexpected"])
        self.assertFalse(events[3]["unexpected"])
        self.assertEqual([event["sequence"] for event in events], [1, 2, 3, 4])
        self.assertEqual(base64.b64decode(raw[0]["raw_base64"]), b"A P 1 100\nA P 1 100\nA P 1 120\nA R 1 200\n")

    def test_no_poll_discards_pending_events_and_raw_chunks_reconstruct(self):
        chunks = [b"A P 1 12", b"345\r", b"\nC P 1 13000\n"]
        reader, raw, events = self.reader(chunks)
        for _ in chunks:
            reader.poll()
        received = b"".join(base64.b64decode(record["raw_base64"]) for record in raw if record["kind"] == "rx_chunk")
        self.assertEqual(received, b"".join(chunks))
        self.assertEqual([event["tpad_ms"] for event in events], [12345, 13000])

    def test_disconnection_retains_prior_events(self):
        reader, raw, events = self.reader([b"A P 1 100\n"])
        reader.poll()
        class Disconnected:
            @property
            def in_waiting(self):
                raise OSError("Device disconnected")
        reader.connection = Disconnected()
        with self.assertRaises(SerialFailure):
            reader.poll()
        self.assertTrue(reader.failed)
        self.assertEqual(len(reader.events), 1)
        self.assertEqual(raw[-1]["kind"], "serial_error")

    def test_close_preserves_fragment(self):
        reader, raw, events = self.reader([b"C P 1 12"])
        reader.poll()
        reader.close()
        self.assertEqual(raw[-1]["interpretation"], "incomplete")
        self.assertTrue(reader.connection.closed)

    def test_no_software_ttl_or_timer_reset_command_is_allowed(self):
        reader, raw, events = self.reader([])
        for command in (b"R", b"REST\n", b"RESE\n", b"TTL1\n", b"01", b"SAVS\n", b"AAO1 200\n"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                reader.command(command)
        reader.command(b"T")
        self.assertEqual(reader.connection.writes, [b"T"])


if __name__ == "__main__":
    unittest.main()
