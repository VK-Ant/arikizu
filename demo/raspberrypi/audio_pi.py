#!/usr/bin/env python3
"""Raspberry Pi audio end-to-end: mic -> arikizu -> audio.transcribe.

Flow:
  1. Pick a mic (sounddevice default, else arecord, else fallback WAV)
  2. Record N seconds to /tmp/arikizu-audio.wav at 16 kHz mono
  3. POST to /api/v1/call/audio/transcribe
  4. Optionally run vision.vad and keyword_spot too
  5. Print PASS/WAIT/FAIL

Works even without a mic — falls back to demo/fixtures/sample.wav.
"""

from __future__ import annotations

import argparse
import math
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import BOLD, GREEN, GREY, RED, RESET, YELLOW, banner, call, print_result, require_runtime  # noqa: E402

OUT_PATH = "/tmp/arikizu-audio.wav"
FALLBACK = str(Path(__file__).resolve().parent.parent / "fixtures" / "sample.wav")
SAMPLE_RATE = 16000


def record_sounddevice(path: str, seconds: float) -> bool:
    try:
        import sounddevice as sd
        import numpy as np
    except (ImportError, OSError) as e:
        print(f"  {YELLOW}sounddevice not usable:{RESET} {e}")
        return False
    try:
        print(f"  recording {seconds}s via sounddevice (speak now)...", flush=True)
        audio = sd.rec(int(SAMPLE_RATE * seconds), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(audio.tobytes())
        return True
    except Exception as e:
        print(f"  {YELLOW}sounddevice capture failed:{RESET} {e}")
        return False


def record_arecord(path: str, seconds: float) -> bool:
    if not shutil.which("arecord"):
        return False
    try:
        print(f"  recording {seconds}s via arecord (speak now)...", flush=True)
        subprocess.run(
            [
                "arecord",
                "-q",
                "-f", "S16_LE",
                "-c", "1",
                "-r", str(SAMPLE_RATE),
                "-d", str(int(seconds)),
                path,
            ],
            check=True,
            timeout=seconds + 5,
        )
        return os.path.getsize(path) > 44
    except subprocess.CalledProcessError as e:
        print(f"  {YELLOW}arecord failed:{RESET} rc={e.returncode}")
        return False
    except Exception as e:
        print(f"  {YELLOW}arecord failed:{RESET} {e}")
        return False


def record_fallback(path: str, seconds: float) -> bool:
    if os.path.exists(FALLBACK):
        shutil.copy(FALLBACK, path)
        print(f"  using fallback fixture: {FALLBACK}")
        return True
    # Last resort: generate a short tone right here.
    frames = int(SAMPLE_RATE * seconds)
    import struct
    data = b"".join(
        struct.pack("<h", int(32767 * 0.3 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE)))
        for i in range(frames)
    )
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(data)
    print(f"  wrote synthetic 440 Hz tone (no fixture, no mic)")
    return True


def pick_source(path: str, seconds: float, prefer: str | None) -> str:
    attempts = []
    if prefer:
        attempts.append(prefer)
    for s in ["sounddevice", "arecord", "fallback"]:
        if s not in attempts:
            attempts.append(s)

    for source in attempts:
        print(f"  trying {source}...")
        ok = {
            "sounddevice": lambda: record_sounddevice(path, seconds),
            "arecord": lambda: record_arecord(path, seconds),
            "fallback": lambda: record_fallback(path, seconds),
        }[source]()
        if ok:
            return source
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=3.0, help="recording length")
    ap.add_argument("--wav", help="skip capture, use this WAV path")
    ap.add_argument("--lang", default="en", help="transcription language code")
    ap.add_argument("--vad", action="store_true", help="also run audio.vad")
    ap.add_argument("--source", choices=["sounddevice", "arecord", "fallback"], help="force a source")
    args = ap.parse_args()

    require_runtime()
    banner(f"Raspberry Pi audio e2e  ({args.seconds}s)")

    if args.wav:
        audio_path = args.wav
        if not os.path.exists(audio_path):
            print(f"  {RED}wav not found:{RESET} {audio_path}")
            return 2
        print(f"  using {audio_path}")
    else:
        source = pick_source(OUT_PATH, args.seconds, args.source)
        if not source:
            print(f"  {RED}no audio source worked{RESET}")
            return 2
        audio_path = OUT_PATH
        size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
        print(f"  wrote {audio_path} ({size} bytes) via {source}")

    res = call("audio.transcribe", {"audio_path": audio_path, "lang": args.lang})
    print_result("audio.transcribe", res, show_body=True)
    pass_count = 1 if res.status == "PASS" else 0
    wait_count = 1 if res.status == "WAIT" else 0

    if args.vad:
        res2 = call("audio.vad", {"audio_path": audio_path, "threshold": 0.5})
        print_result("audio.vad", res2, show_body=True)
        if res2.status == "PASS": pass_count += 1
        elif res2.status == "WAIT": wait_count += 1

    if wait_count and not pass_count:
        print()
        print(f"  {GREY}WAIT means Sonarwise is not yet wired (Weekend 6). The capture + HTTP path works.{RESET}")

    return 0 if res.status != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
