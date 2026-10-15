#!/usr/bin/env python3
"""Vision worker demo. SightRAG wrapper.

v0.1: handlers return placeholder notes (WAIT). Once SightRAG is wired on
Weekend 5, the same calls return real detections and these turn to PASS.

Usage:
  python3 demo/fixtures/make_fixtures.py          # once, to create sample.png
  python3 demo/perception/vision_demo.py
  python3 demo/perception/vision_demo.py /path/to/your/image.jpg
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime  # noqa: E402


def main() -> int:
    require_runtime()
    img = sys.argv[1] if len(sys.argv) > 1 else "demo/fixtures/sample.png"
    if not os.path.exists(img):
        print(f"image not found: {img}")
        print("run: python3 demo/fixtures/make_fixtures.py")
        return 2

    banner(f"Vision worker  —  {img}")

    print_result("vision.detect  (conf=0.5)", call("vision.detect", {"image_path": img, "confidence": 0.5}), show_body=True)
    print_result("vision.detect  (conf=0.9)", call("vision.detect", {"image_path": img, "confidence": 0.9}))
    print_result("vision.ocr     (en)",       call("vision.ocr",    {"image_path": img, "lang": "en"}), show_body=True)
    print_result("vision.caption",            call("vision.caption",{"image_path": img}), show_body=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
