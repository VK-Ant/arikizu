#!/usr/bin/env python3
"""Export a yolov8n.onnx file using the ultralytics PyPI package.

This is a fallback for when every HTTP mirror in download-default-models.sh
fails (HF 401s, GitHub rate limits, etc). Downloads the yolov8n.pt weights
through the ultralytics package (which has its own CDN) and exports to ONNX
with CPU-friendly settings, so the result loads in plain onnxruntime without
custom ops.

Usage:
    python3 -m pip install ultralytics
    python3 scripts/export_yolo_onnx.py                   # writes to ./models/
    python3 scripts/export_yolo_onnx.py /path/to/models   # writes elsewhere
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    models_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "./models")
    models_dir.mkdir(parents=True, exist_ok=True)
    out = models_dir / "yolov8n.onnx"

    try:
        from ultralytics import YOLO
    except ImportError:
        print("error: ultralytics not installed. Run:", file=sys.stderr)
        print("  python3 -m pip install ultralytics", file=sys.stderr)
        return 1

    print(f"loading yolov8n (will auto-download the pt weights if missing)...")
    model = YOLO("yolov8n.pt")

    print(f"exporting to ONNX (opset=12, dynamic=False, simplify=False)...")
    # opset 12 is widely supported; dynamic=False gives static shapes which
    # some lightweight runtimes prefer; simplify=False avoids onnxsim as a
    # hard dependency.
    exported = model.export(format="onnx", opset=12, dynamic=False, simplify=False)
    exported_path = Path(exported)

    if exported_path.resolve() != out.resolve():
        shutil.copy(exported_path, out)
        print(f"copied {exported_path} -> {out}")
    else:
        print(f"wrote {out}")

    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"\nOK  {out} ({size_mb:.1f} MB)")
    print(f"\nSet in your shell (optional; auto-discovered otherwise):")
    print(f"  export ARIKIZU_VISION_MODEL={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
