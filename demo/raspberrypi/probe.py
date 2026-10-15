#!/usr/bin/env python3
"""Raspberry Pi hardware probe.

Reports what's on this device without touching the network. Safe to run
anytime; nothing changes.
"""

from __future__ import annotations

import glob
import os
import platform
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import BOLD, GREEN, GREY, RED, RESET, YELLOW, banner, runtime_up  # noqa: E402


def _read(path: str) -> str:
    try:
        return open(path).read().strip()
    except Exception:
        return ""


def ok(label: str, value: str) -> None:
    print(f"  {GREEN}OK{RESET}   {label:28} {value}")


def miss(label: str, value: str = "") -> None:
    print(f"  {YELLOW}--{RESET}   {label:28} {value}")


def bad(label: str, value: str) -> None:
    print(f"  {RED}XX{RESET}   {label:28} {value}")


def section(name: str) -> None:
    print()
    print(f"{BOLD}{name}{RESET}")
    print(f"{GREY}{'-' * max(len(name), 40)}{RESET}")


def probe_platform() -> None:
    section("platform")
    model = _read("/proc/device-tree/model").replace("\x00", "")
    if model:
        ok("device", model)
    else:
        miss("device", "not a device-tree system")
    ok("kernel", platform.release())
    ok("arch",   platform.machine())
    ok("python", platform.python_version())

    cpus = 0
    try:
        cpus = os.cpu_count() or 0
    except Exception:
        pass
    ok("cpu cores", str(cpus))

    mem_total = 0
    for line in _read("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            mem_total = int(line.split()[1]) // 1024
            break
    if mem_total:
        ok("memory (MB)", str(mem_total))

    # Pi power/throttle (vcgencmd), optional
    if shutil.which("vcgencmd"):
        try:
            throttled = subprocess.check_output(
                ["vcgencmd", "get_throttled"], text=True, timeout=2
            ).strip()
            ok("vcgencmd", throttled)
        except Exception:
            pass


def probe_cameras() -> None:
    section("cameras")
    vids = sorted(glob.glob("/dev/video*"))
    if vids:
        ok("/dev/video*", ", ".join(vids))
    else:
        miss("/dev/video*", "no video devices found")

    try:
        import picamera2  # noqa: F401
        ok("picamera2", "importable")
    except ImportError:
        miss("picamera2", "pip install picamera2 (apt: python3-picamera2)")

    try:
        import cv2
        ok("opencv-python", cv2.__version__)
    except ImportError:
        miss("opencv-python", "apt: python3-opencv  OR  pip install opencv-python")


def probe_audio() -> None:
    section("audio")
    if shutil.which("arecord"):
        try:
            out = subprocess.check_output(["arecord", "-l"], text=True, timeout=2)
            lines = [l for l in out.splitlines() if l.startswith("card ")]
            if lines:
                for line in lines:
                    ok("alsa card", line)
            else:
                miss("arecord -l", "no capture devices")
        except Exception as e:
            bad("arecord -l", str(e))
    else:
        miss("arecord", "apt: alsa-utils")

    try:
        import sounddevice  # noqa: F401
        ok("sounddevice", "importable")
    except (ImportError, OSError) as e:
        miss("sounddevice", f"not importable ({e})")


def probe_runtime() -> None:
    section("arikizu runtime")
    if runtime_up():
        ok("arikizu", "reachable at http://127.0.0.1:7000")
    else:
        bad("arikizu", "not reachable — start with `make run`")


def main() -> int:
    banner("Raspberry Pi probe")
    probe_platform()
    probe_cameras()
    probe_audio()
    probe_runtime()
    print()
    print("Next:")
    print("  python3 demo/raspberrypi/vision_pi.py")
    print("  python3 demo/raspberrypi/audio_pi.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
