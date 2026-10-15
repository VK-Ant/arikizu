#!/usr/bin/env python3
"""Generate the demo fixtures with stdlib only.

Creates:
  demo/fixtures/sample.png   8x8 red PNG
  demo/fixtures/sample.wav   1 second sine wave at 440 Hz, 16kHz mono
  demo/fixtures/sample.txt   short plain-text document
  demo/fixtures/series.json  sine-wave with one anomaly, 120 points

Idempotent; skips files that already exist.
"""

from __future__ import annotations

import json
import math
import pathlib
import struct
import sys
import wave
import zlib

HERE = pathlib.Path(__file__).resolve().parent


def make_png() -> None:
    path = HERE / "sample.png"
    if path.exists():
        return
    # 8x8 solid red (255, 0, 0). Hand-rolled minimum PNG.
    width, height = 8, 8
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw, 9)
    png = sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    path.write_bytes(png)
    print(f"wrote {path}")


def make_wav() -> None:
    path = HERE / "sample.wav"
    if path.exists():
        return
    rate = 16000
    duration_s = 1.0
    freq = 440.0
    frames = int(rate * duration_s)
    samples = bytes()
    for i in range(frames):
        value = int(32767 * 0.3 * math.sin(2 * math.pi * freq * i / rate))
        samples += struct.pack("<h", value)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples)
    print(f"wrote {path}")


def make_txt() -> None:
    path = HERE / "sample.txt"
    if path.exists():
        return
    path.write_text(
        "Arikizu Factory Floor Report\n"
        "============================\n\n"
        "Date: 2026-10-12\n"
        "Shift: morning\n"
        "Line: 3\n\n"
        "Defects observed:\n"
        "- Three missing bolts on housing A at 09:14\n"
        "- One hairline crack on housing B at 10:02\n"
        "- Camera 2 lost signal between 10:33 and 10:35\n\n"
        "Operator: VK (vk@example.com, phone +91 9876543210)\n"
        "Approved by: shift_lead\n"
    )
    print(f"wrote {path}")


def make_series() -> None:
    path = HERE / "series.json"
    if path.exists():
        return
    rate = 60
    points = 120
    series = []
    for i in range(points):
        base = 50 + 10 * math.sin(2 * math.pi * i / 30)
        series.append(round(base, 3))
    # Inject one anomaly at index 72.
    series[72] = 500.0
    path.write_text(json.dumps({"series": series, "anomaly_index": 72}, indent=2))
    print(f"wrote {path}")


def main() -> int:
    make_png()
    make_wav()
    make_txt()
    make_series()
    print("fixtures ready in demo/fixtures/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
