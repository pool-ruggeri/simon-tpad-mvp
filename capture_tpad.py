"""Show and save live tPAD records for a hardware button check."""

import argparse
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from time import monotonic, sleep

from tpad_listener import TPADListener


OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def show_record(record):
    if record.button is not None:
        description = f"B{record.button} {record.state}"
    else:
        description = f"{record.kind} {record.raw!r}"
    if record.tpad_ms is not None:
        description += f" | tPAD {record.tpad_ms} ms"
    print(f"#{record.sequence} {description}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Show and save live tPAD records.")
    parser.add_argument("--port", required=True, help="tPAD serial port, for example COM3")
    parser.add_argument("--duration", type=float, default=30, help="Capture seconds (default 30)")
    args = parser.parse_args(argv)
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be a positive, finite number of seconds")

    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    capture_path = OUTPUT_DIR / f"tpad_capture_{stamp}.jsonl"
    records = []
    tail = []
    listener = None
    exit_code = 0

    # Open a new file before starting acquisition so existing captures stay intact.
    with capture_path.open("x", encoding="utf-8", newline="\n") as capture:
        try:
            listener = TPADListener(args.port)
            with listener:
                print(
                    f"Capturing {args.port} for {args.duration:g} seconds. "
                    "Press and release B1-B4. Ctrl+C stops early.",
                    flush=True,
                )
                deadline = monotonic() + args.duration
                while monotonic() < deadline:
                    batch = listener.poll()
                    # Keep the full batch if Ctrl+C interrupts printing.
                    records.extend(batch)
                    for record in batch:
                        show_record(record)
                    sleep(0.001)  # Yield briefly between nonblocking polls.
        except KeyboardInterrupt:
            print("\nCapture stopped with Ctrl+C.", flush=True)
            exit_code = 130
        except OSError as error:
            print(f"Capture failed on {args.port}: {error}", file=sys.stderr)
            exit_code = 1
        finally:
            if listener is not None:
                # The context releases the port. Collect any already-read tail.
                tail = listener.close()
                records.extend(tail)
            for record in records:
                row = asdict(record)
                row["raw_base64"] = base64.b64encode(row.pop("raw")).decode("ascii")
                capture.write(json.dumps(row) + "\n")

    for record in tail:
        show_record(record)
    print(f"Saved {len(records)} records to {capture_path}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
