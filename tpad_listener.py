"""Standalone reader for Black Box Toolkit tPAD Mode 5 serial records."""

from dataclasses import dataclass
import re
import time

import serial


_READ_BYTES = 4096
_MAX_TPAD_MS = 2**53  # The validated MATLAB reader's exact-integer limit.
_CHANNEL_LIMITS = {b"A": 10, b"C": 2, b"M": 1, b"T": 1}
_MODE_REPLY = re.compile(rb"MODE [0-6]:[ \t]*")
_NUMERIC_REPLY = re.compile(rb"[0-9]+[ \t]*")
_EVENT = re.compile(rb"([A-Z])[ \t]+([PR])[ \t]+([0-9]+)[ \t]+([0-9]+)")


@dataclass(frozen=True)
class TPADRecord:
    """One received record, with separate device and PC timing fields."""

    sequence: int
    kind: str
    raw: bytes
    rx_first_ns: int
    rx_complete_ns: int | None
    channel: str = ""
    edge: str = ""
    sensor: int | None = None
    button: int | None = None
    state: str = ""
    tpad_ms: int | None = None
    out_of_order: bool = False


class TPADListener:
    """Open one serial port and confirm Mode 5 before polling."""

    def __init__(self, port: str):
        self._port = port
        self._buffer = bytearray()
        self._overlong = False
        self._first_rx_ns = 0
        self._sequence = 0
        self._highest_tpad_ms = -1
        self._pending: list[TPADRecord] = []
        self._connection = serial.Serial(
            port=port, baudrate=115200, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            timeout=0, write_timeout=0.1, xonxoff=False, rtscts=False, dsrdtr=False,
        )
        try:
            self._set_mode(b"X", "MODE 0:")
            # Give the tPAD at least 25 ms between commands, after confirming Mode 0.
            time.sleep(0.025)
            self._set_mode(b"MOD5\r\n", "MODE 5:")
        except BaseException as error:
            self._release_port(error)
            raise

    def _set_mode(self, command: bytes, acknowledgement: str) -> None:
        if self._connection.write(command) != len(command):
            raise serial.SerialException(f"Incomplete write to {self._port}: {command!r}")

        # Wait only during setup. Keep all replies and early events in receive order.
        sent_ns = time.monotonic_ns()
        deadline = sent_ns + 2_000_000_000
        while time.monotonic_ns() < deadline:
            records = self._read_once()
            self._pending.extend(records)
            # A reply that started before this command cannot acknowledge it.
            if any(
                record.kind == "mode" and record.state == acknowledgement
                and record.rx_first_ns >= sent_ns
                for record in records
            ):
                return
            time.sleep(0.001)
        raise serial.SerialException(
            f"No {acknowledgement} acknowledgement from {self._port} within 2 s."
        )

    def poll(self) -> list[TPADRecord]:
        """Return newly received records after one bounded, nonblocking read."""
        if self._connection is None:
            raise serial.PortNotOpenError()
        try:
            self._pending.extend(self._read_once())
        except OSError as error:
            self._release_port(error)
            raise
        records = self._pending
        self._pending = []
        return records

    def _read_once(self) -> list[TPADRecord]:
        data = self._connection.read(_READ_BYTES)
        if not data:
            return []
        received_ns = time.monotonic_ns()
        records = []
        for byte in data:
            if byte in (10, 13):
                # CR and LF each end a record. The second byte of CRLF is empty.
                if self._buffer:
                    kind = "malformed" if self._overlong else None
                    records.append(self._finish_record(received_ns, kind))
                self._overlong = False
                continue
            if not self._buffer:
                self._first_rx_ns = received_ns
            self._buffer.append(byte)
            if len(self._buffer) == _READ_BYTES:
                # Retain long corrupt lines in pieces. Treat their suffix as
                # part of the same damaged line until the next delimiter.
                records.append(self._finish_record(received_ns, "malformed"))
                self._overlong = True
        return records

    def _finish_record(self, rx_complete_ns: int | None, kind: str | None = None) -> TPADRecord:
        raw = bytes(self._buffer)
        self._buffer.clear()
        self._sequence += 1
        fields = self._parse_payload(raw) if kind is None else {"kind": kind}
        return TPADRecord(
            sequence=self._sequence, raw=raw, rx_first_ns=self._first_rx_ns,
            rx_complete_ns=rx_complete_ns, **fields,
        )

    def _parse_payload(self, raw: bytes) -> dict:
        if _MODE_REPLY.fullmatch(raw):
            return {"kind": "mode", "state": raw.rstrip().decode("ascii")}
        if _NUMERIC_REPLY.fullmatch(raw):
            return {"kind": "reply"}

        match = _EVENT.fullmatch(raw.strip(b" \t"))
        if not match:
            return {"kind": "malformed"}
        channel_bytes, edge_bytes, sensor_digits, stamp_digits = match.groups()
        sensor_digits = sensor_digits.lstrip(b"0") or b"0"
        stamp_digits = stamp_digits.lstrip(b"0") or b"0"
        # Reject oversized fields before converting potentially corrupt numbers.
        if len(sensor_digits) > 2 or len(stamp_digits) > 16:
            return {"kind": "malformed"}
        sensor, stamp = int(sensor_digits), int(stamp_digits)
        if not 1 <= sensor <= _CHANNEL_LIMITS.get(channel_bytes, 0) or stamp > _MAX_TPAD_MS:
            return {"kind": "malformed"}

        channel, edge = channel_bytes.decode("ascii"), edge_bytes.decode("ascii")
        kind, state, button = "other", "", None
        if channel == "A" and sensor <= 4:
            kind, button = "button", sensor
            state = "press" if edge == "P" else "release"
        elif channel in ("C", "M"):
            kind = "optical" if channel == "C" else "microphone"
            state = "on" if edge == "P" else "off"

        # Keep repeats and time regressions in wire order.
        out_of_order = stamp < self._highest_tpad_ms
        self._highest_tpad_ms = max(self._highest_tpad_ms, stamp)
        return {
            "kind": kind, "channel": channel, "edge": edge, "sensor": sensor,
            "button": button, "state": state, "tpad_ms": stamp,
            "out_of_order": out_of_order,
        }

    def close(self) -> list[TPADRecord]:
        """Release the port and return any undelivered records and fragment once."""
        self._release_port()
        if self._buffer:
            self._pending.append(self._finish_record(None, "incomplete"))
        records = self._pending
        self._pending = []
        return records

    def _release_port(self, original_error: BaseException | None = None) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            connection.close()
        except Exception as error:
            if original_error is None:
                raise
            original_error.add_note(f"Could not close the tPAD port: {error}")

    def __enter__(self) -> "TPADListener":
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Keep already-read data available to close() after a with block.
        self._release_port(exc_value)
