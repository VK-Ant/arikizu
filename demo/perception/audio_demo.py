#!/usr/bin/env python3
"""Audio worker demo. Sonarwise wrapper.

v0.1: placeholder (WAIT) until Weekend 6 wires Sonarwise.

Usage:
  python3 demo/fixtures/make_fixtures.py
  python3 demo/perception/audio_demo.py
  python3 demo/perception/audio_demo.py /path/to/your/audio.wav
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime  # noqa: E402


def main() -> int:
    require_runtime()
    audio = sys.argv[1] if len(sys.argv) > 1 else "demo/fixtures/sample.wav"
    if not os.path.exists(audio):
        print(f"audio not found: {audio}")
        print("run: python3 demo/fixtures/make_fixtures.py")
        return 2

    banner(f"Audio worker  —  {audio}")

    print_result("audio.transcribe   (en)",        call("audio.transcribe", {"audio_path": audio, "lang": "en"}), show_body=True)
    print_result("audio.vad          (0.5)",       call("audio.vad", {"audio_path": audio, "threshold": 0.5}), show_body=True)
    print_result("audio.keyword_spot (hello,arikizu)", call("audio.keyword_spot", {"audio_path": audio, "keywords": ["hello", "arikizu"]}), show_body=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
