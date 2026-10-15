#!/usr/bin/env python3
"""Raspberry Pi vision end-to-end: camera -> arikizu -> vision.detect.

Flow:
  1. Pick a camera (picamera2, then /dev/video0 via opencv, then fallback image)
  2. Capture one frame to /tmp/arikizu-vision.jpg
  3. POST to /api/v1/call/vision/detect
  4. Print PASS/WAIT/FAIL

Works even without a camera attached — falls back to demo/fixtures/sample.png.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import BOLD, GREEN, GREY, RED, RESET, YELLOW, banner, call, print_result, require_runtime  # noqa: E402

OUT_PATH = "/tmp/arikizu-vision.jpg"
FALLBACK = str(Path(__file__).resolve().parent.parent / "fixtures" / "sample.png")


def capture_picamera2(path: str) -> bool:
    try:
        from picamera2 import Picamera2
    except ImportError:
        return False
    try:
        cam = Picamera2()
        cam.configure(cam.create_still_configuration(main={"size": (640, 480)}))
        cam.start()
        time.sleep(0.3)
        cam.capture_file(path)
        cam.stop()
        cam.close()
        return True
    except Exception as e:
        print(f"  {YELLOW}picamera2 failed:{RESET} {e}")
        return False


def capture_opencv(path: str) -> bool:
    try:
        import cv2
    except ImportError:
        return False
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        cap.release()
        return False
    # Give the sensor a moment to settle; discard the first few frames.
    for _ in range(3):
        cap.read()
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return False
    try:
        cv2.imwrite(path, frame)
        return True
    except Exception as e:
        print(f"  {YELLOW}opencv write failed:{RESET} {e}")
        return False


def capture_fallback(path: str) -> bool:
    if not os.path.exists(FALLBACK):
        print(f"  {RED}fallback image missing:{RESET} {FALLBACK}")
        print(f"  Run: python3 demo/fixtures/make_fixtures.py")
        return False
    shutil.copy(FALLBACK, path)
    return True


def pick_source(path: str, prefer: str | None) -> str:
    """Try sources in order; return the name of the one that worked."""
    attempts = []
    if prefer:
        attempts.append(prefer)
    for s in ["picamera2", "opencv", "fallback"]:
        if s not in attempts:
            attempts.append(s)

    for source in attempts:
        print(f"  trying {source}...", end=" ", flush=True)
        ok = {
            "picamera2": lambda: capture_picamera2(path),
            "opencv": lambda: capture_opencv(path),
            "fallback": lambda: capture_fallback(path),
        }[source]()
        print(f"{GREEN}captured{RESET}" if ok else f"{YELLOW}skipped{RESET}")
        if ok:
            return source
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", type=float, default=0.5, help="confidence threshold")
    ap.add_argument("--image", help="skip capture, use this image path")
    ap.add_argument("--loop", type=int, default=1, help="capture N frames (1 by default)")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between frames in --loop mode")
    ap.add_argument("--source", choices=["picamera2", "opencv", "fallback"], help="force a capture source")
    args = ap.parse_args()

    require_runtime()
    banner("Raspberry Pi vision e2e")

    results = {"PASS": 0, "WAIT": 0, "FAIL": 0, "SKIP": 0}
    for i in range(args.loop):
        if args.image:
            img_path = args.image
            if not os.path.exists(img_path):
                print(f"  {RED}image not found:{RESET} {img_path}")
                return 2
            print(f"  frame {i+1}/{args.loop}: using {img_path}")
        else:
            print(f"  frame {i+1}/{args.loop}:")
            source = pick_source(OUT_PATH, args.source)
            if not source:
                print(f"  {RED}no capture source worked{RESET}")
                return 2
            img_path = OUT_PATH
            size = os.path.getsize(img_path) if os.path.exists(img_path) else 0
            print(f"  wrote {img_path} ({size} bytes) via {source}")

        res = call("vision.detect", {"image_path": img_path, "confidence": args.conf})
        print_result("vision.detect", res, show_body=True)
        results[res.status] = results.get(res.status, 0) + 1

        if i < args.loop - 1:
            time.sleep(args.interval)

    if args.loop > 1:
        print()
        print(f"  {BOLD}{results['PASS']}{RESET} live  "
              f"{BOLD}{results['WAIT']}{RESET} placeholder  "
              f"{BOLD}{results['FAIL']}{RESET} failing  "
              f"{BOLD}{results['SKIP']}{RESET} skipped")

    # Hint: show how to get real results.
    if results.get("WAIT", 0) > 0 and results.get("PASS", 0) == 0:
        print()
        print(f"  {GREY}WAIT means SightRAG is not yet wired (Weekend 5). The capture + HTTP path works.{RESET}")

    return 0 if results.get("FAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
