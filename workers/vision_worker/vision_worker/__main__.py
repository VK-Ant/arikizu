"""Vision worker entry point.

Shows the full "pick a backend, load a model, run inference" pattern.
Falls back to placeholder output when no model file is configured, so
the IPC + routing path is testable before SightRAG is wired in Weekend 5.

Env vars (all optional):
    ARIKIZU_VISION_MODEL        path to .onnx / .tflite / .xml / .engine / .pt
    ARIKIZU_BACKEND_PREFER      comma-separated priority list, e.g. "tensorrt,onnx_gpu,onnx_cpu"
    ARIKIZU_VISION_LABELS       path to a text file with one class label per line

Weekend 5 wires SightRAG in place of the raw inference calls, keeping the
same handler signatures.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from arikizu_worker import Worker
from arikizu_worker import backend as bk


def _default_model_path(models_dir: str) -> str:
    """Fall back to the first .onnx file in the models dir, or empty string."""
    p = Path(models_dir)
    if not p.exists():
        return ""
    for candidate in ("yolov8n.onnx", "yolov5n.onnx", "model.onnx"):
        if (p / candidate).exists():
            return str(p / candidate)
    # Last resort: any .onnx we find
    for f in sorted(p.glob("*.onnx")):
        return str(f)
    return ""


MODELS_DIR = os.environ.get("ARIKIZU_MODELS_DIR", "./models")
MODEL_PATH = os.environ.get("ARIKIZU_VISION_MODEL") or _default_model_path(MODELS_DIR)
PREFER = [s for s in os.environ.get("ARIKIZU_BACKEND_PREFER", "").split(",") if s]
LABELS_PATH = os.environ.get("ARIKIZU_VISION_LABELS", "")


def _load_labels() -> list[str]:
    if LABELS_PATH and Path(LABELS_PATH).exists():
        return [line.strip() for line in Path(LABELS_PATH).read_text().splitlines() if line.strip()]
    return []


def _try_load(path: str, prefer: list[str], logger: logging.Logger):
    """Load a model, return a ModelHandle or None (with logged reason)."""
    if not path:
        logger.info("no model path; using placeholder handlers")
        return None
    try:
        h = bk.load_model(path, prefer=prefer or None)
        logger.info("loaded %s via %s (%s)", path, h.backend.value, h.meta)
        return h
    except FileNotFoundError:
        logger.warning("model path %s does not exist; using placeholder", path)
    except bk.BackendUnavailable as e:
        logger.warning("could not load %s: %s; using placeholder", path, e)
    except Exception as e:  # keep worker alive on any backend-specific error
        logger.warning("backend load error for %s: %s; using placeholder", path, e)
    return None


# mutable handle so switch_model can rotate it
_HANDLE: dict[str, Any] = {"handle": None, "path": ""}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("vision")

    # Report what runtimes are present on this host, for the audit log.
    summary = bk.summarize()
    logger.info("backend scan: %s", summary)

    _HANDLE["handle"] = _try_load(MODEL_PATH, PREFER, logger)
    _HANDLE["path"] = MODEL_PATH if _HANDLE["handle"] else ""

    labels = _load_labels()
    worker = Worker("vision")

    def _h():
        return _HANDLE["handle"]

    @worker.handler("vision.detect")
    def detect(image_path: str = "", image_base64: str = "",
               confidence: float = 0.5) -> dict[str, Any]:
        h = _h()
        # When the browser sends a webcam frame, image_base64 is set.
        # We decode its dimensions so canned boxes scale to the real
        # frame, otherwise the UI draws boxes off-screen.
        src_w, src_h = 640, 480
        if image_base64:
            try:
                import base64, io
                from PIL import Image
                im = Image.open(io.BytesIO(base64.b64decode(image_base64)))
                src_w, src_h = im.size
            except Exception:
                pass

        if h is None:
            # Demo mode: canned detections, scaled to the actual frame.
            def scale(b):
                return [
                    int(b[0] * src_w / 640),
                    int(b[1] * src_h / 480),
                    int(b[2] * src_w / 640),
                    int(b[3] * src_h / 480),
                ]
            return {
                "image": image_path or ("(webcam frame)" if image_base64 else "/demo/fixtures/scene.jpg"),
                "width": src_w,
                "height": src_h,
                "backend": "demo-webcam" if image_base64 else "demo-fixture",
                "note": "demo mode; no vision model loaded. Boxes are canned.",
                "detections": [
                    {"class": "box", "score": 0.94, "bbox": scale([90, 310, 190, 420])},
                    {"class": "box", "score": 0.91, "bbox": scale([240, 320, 350, 430])},
                    {"class": "box", "score": 0.88, "bbox": scale([400, 315, 510, 425])},
                    {"class": "person", "score": 0.82, "bbox": scale([255, 165, 345, 310])},
                ],
            }
        # Model is loaded. Weekend 5 wires in SightRAG preprocessing.
        return {
            "image": image_path or "(webcam frame)",
            "detections": [],
            "backend": h.backend.value,
            "model_path": str(h.path),
            "confidence_threshold": confidence,
            "note": "model loaded; SightRAG preprocessing not yet wired",
        }

    @worker.handler("vision.ocr")
    def ocr(image_path: str = "", lang: str = "en") -> dict[str, Any]:
        h = _h()
        if h is None:
            return {"image": image_path, "text": "", "lang": lang, "note": "placeholder; SightRAG OCR not yet wired"}
        return {
            "image": image_path, "text": "", "lang": lang,
            "backend": h.backend.value, "note": "model loaded; OCR pipeline not yet wired",
        }

    @worker.handler("vision.caption")
    def caption(image_path: str = "") -> dict[str, Any]:
        h = _h()
        if h is None:
            return {"image": image_path, "caption": "", "note": "placeholder; captioning not yet wired"}
        return {
            "image": image_path, "caption": "",
            "backend": h.backend.value, "note": "model loaded; captioning pipeline not yet wired",
        }

    @worker.handler("vision.backends")
    def backends() -> dict[str, Any]:
        """Report what runtimes are available on this host."""
        h = _h()
        # Also report what models are on disk, so the dashboard can list them.
        models_dir = Path(MODELS_DIR)
        on_disk = [str(p) for p in sorted(models_dir.glob("*.onnx"))] if models_dir.exists() else []
        return {
            **bk.summarize(),
            "model_path": _HANDLE["path"] or None,
            "model_loaded": h is not None,
            "picked_backend": h.backend.value if h else None,
            "available_models": on_disk,
            "models_dir": str(models_dir),
            "labels_loaded": len(labels),
            "env_prefer": PREFER,
        }

    @worker.handler("vision.switch_model")
    def switch_model(model_path: str = "", prefer: list[str] | None = None) -> dict[str, Any]:
        """Hot-swap the loaded vision model. UI exposes this on /models."""
        new_prefer = prefer if prefer is not None else PREFER
        h_new = _try_load(model_path, new_prefer, logger)
        if h_new is None:
            return {
                "ok": False,
                "model_path": model_path,
                "error": "load failed; worker kept previous model",
                "current_model": _HANDLE["path"] or None,
            }
        _HANDLE["handle"] = h_new
        _HANDLE["path"] = model_path
        return {
            "ok": True,
            "model_path": model_path,
            "backend": h_new.backend.value,
            "providers": h_new.meta.get("providers", []),
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
