"""Non-blocking T-Pad XiD acquisition. No software TTL or timer-reset commands."""

from dataclasses import asdict, dataclass
import base64
import re
import time


@dataclass(frozen=True)
class Message:
    sequence: int
    raw: bytes
    kind: str
    channel: str = ""
    edge: str = ""
    sensor: int | None = None
    tpad_ms: int | None = None


@dataclass(frozen=True)
class Event:
    sequence: int
    channel: str
    edge: str
    sensor: int
    tpad_ms: int
    arrival_monotonic_ns: int
    raw_text: str
    duplicate: bool = False
    unexpected: bool = False


class XiDParser:
    """Keep partial lines across reads; accept CR, LF, and CRLF boundaries."""

    def __init__(self, max_line_bytes=4096):
        self.buffer = bytearray()
        self.sequence = 0
        self.max_line_bytes = max_line_bytes

    def _message(self, raw, incomplete=False):
        self.sequence += 1
        kind = "incomplete" if incomplete else "unknown"
        try:
            text = raw.decode("ascii").strip()
        except UnicodeDecodeError:
            return Message(self.sequence, raw, "malformed")
        if incomplete:
            return Message(self.sequence, raw, kind)
        match = re.fullmatch(r"([A-Z])\s+([PR])\s+(\d+)\s+(\d+)", text)
        if match:
            channel, edge, sensor, stamp = match.groups()
            sensor, stamp = int(sensor), int(stamp)
            # The installed pad has four buttons and one Opto. Other documented
            # channels are preserved but cannot supply a Simon response/onset.
            limits = {"A": 4, "C": 2, "M": 1, "T": 1}
            kind = "event" if channel in limits and 1 <= sensor <= limits[channel] else "unexpected"
            return Message(self.sequence, raw, kind, channel, edge, sensor, stamp)
        if text.isascii() and text.isdecimal():
            return Message(self.sequence, raw, "counter", tpad_ms=int(text))
        if re.fullmatch(r"MODE [0-6]:", text):
            return Message(self.sequence, raw, "mode")
        if text.startswith(("A ", "C ", "M ", "T ")):
            kind = "malformed"
        return Message(self.sequence, raw, kind)

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        while self.buffer:
            boundary = next((i for i, b in enumerate(self.buffer) if b in (10, 13)), None)
            if boundary is None:
                if len(self.buffer) > self.max_line_bytes:
                    raw = bytes(self.buffer)
                    self.buffer.clear()
                    messages.append(self._message(raw, incomplete=True))
                break
            raw = bytes(self.buffer[:boundary + 1])
            del self.buffer[:boundary + 1]
            if raw.strip():
                messages.append(self._message(raw))
        return messages

    def finish(self):
        """Audit a trailing fragment; never guess its timestamp before a delimiter."""
        if not self.buffer:
            return []
        raw = bytes(self.buffer)
        self.buffer.clear()
        return [self._message(raw, incomplete=True)]


class SerialFailure(RuntimeError):
    pass


class TPadReader:
    """Own one serial connection; one bounded read per poll, with timeout=0."""

    def __init__(self, connection, raw_sink, event_sink):
        self.connection = connection
        self.raw_sink = raw_sink
        self.event_sink = event_sink
        self.parser = XiDParser()
        self.events = []
        self.messages = []
        self.seen = set()
        self.active = set()
        self.failed = False
        self.issue_sequences = []

    @classmethod
    def open(cls, port, raw_sink, event_sink):
        import serial
        try:
            connection = serial.Serial(
                port=port, baudrate=115200, bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                timeout=0, write_timeout=0.1, xonxoff=False,
                rtscts=False, dsrdtr=False,
            )
        except (serial.SerialException, OSError) as exc:
            raise SerialFailure(f"Cannot open {port}: {exc}. Close the BBTK utility and other port owners.") from exc
        return cls(connection, raw_sink, event_sink)

    def _accept(self, messages, arrival_ns):
        for message in messages:
            self.messages.append(message)
            record = {
                "kind": "message", "sequence": message.sequence,
                "arrival_monotonic_ns": arrival_ns, "interpretation": message.kind,
                "raw_base64": base64.b64encode(message.raw).decode("ascii"),
                "raw_text": message.raw.decode("ascii", errors="backslashreplace"),
            }
            self.raw_sink(record)
            if message.kind in ("malformed", "incomplete", "unknown", "unexpected"):
                self.issue_sequences.append(message.sequence)
            if message.kind not in ("event", "unexpected") or message.sensor is None:
                continue
            identity = (message.channel, message.edge, message.sensor, message.tpad_ms)
            duplicate = identity in self.seen
            self.seen.add(identity)
            input_id = (message.channel, message.sensor)
            unexpected = message.kind == "unexpected"
            if not duplicate:
                if message.edge == "P":
                    unexpected |= input_id in self.active
                    self.active.add(input_id)
                else:
                    unexpected |= input_id not in self.active
                    self.active.discard(input_id)
            event = Event(
                message.sequence, message.channel, message.edge, message.sensor,
                message.tpad_ms, arrival_ns, record["raw_text"], duplicate, unexpected,
            )
            self.events.append(event)
            self.event_sink(asdict(event))

    def poll(self):
        if self.failed:
            raise SerialFailure("Serial acquisition has already failed.")
        try:
            waiting = self.connection.in_waiting
            data = self.connection.read(min(waiting, 4096)) if waiting else b""
        except (OSError, RuntimeError) as exc:
            self.failed = True
            self.raw_sink({"kind": "serial_error", "message": str(exc), "arrival_monotonic_ns": time.perf_counter_ns()})
            raise SerialFailure(f"Serial acquisition failed: {exc}") from exc
        if data:
            arrival_ns = time.perf_counter_ns()
            self.raw_sink({
                "kind": "rx_chunk", "arrival_monotonic_ns": arrival_ns,
                "raw_base64": base64.b64encode(data).decode("ascii"),
            })
            self._accept(self.parser.feed(data), arrival_ns)

    def command(self, command):
        # Explicit allowlist: no TTL writes, setting changes, firmware updates,
        # or R/REST timer resets. Command writes happen only on black screens.
        if command not in (b"X", b"FIRM\n", b"MOD5\n", b"T"):
            raise ValueError("Command is outside the approved MVP allowlist.")
        self.raw_sink({"kind": "tx", "host_monotonic_ns": time.perf_counter_ns(),
                       "raw_base64": base64.b64encode(command).decode("ascii")})
        try:
            if self.connection.write(command) != len(command):
                raise OSError("Incomplete command write")
        except (OSError, RuntimeError) as exc:
            self.failed = True
            raise SerialFailure(f"Serial command failed: {exc}") from exc

    def close(self):
        self._accept(self.parser.finish(), time.perf_counter_ns())
        self.connection.close()
