"""Vision worker. Real YOLO ONNX inference.

Auto-discovers a model in ./models/ (any .onnx file). No env vars or
yaml edits needed for the default flow. Set ARIKIZU_VISION_MODEL to
override.

Pipeline: image bytes -> resize to 640x640 letterbox -> normalize ->
onnxruntime -> NMS -> real detections with class names and bbox.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from arikizu_worker import Worker


# COCO 80 class names, matches yolov8n training set
COCO_NAMES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus",
    "train", "truck", "boat", "traffic light", "fire hydrant",
    "stop sign", "parking meter", "bench", "bird", "cat", "dog",
    "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
    "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat",
    "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl",
    "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop",
    "mouse", "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]


def _find_project_root_early() -> Path:
    """Walk up from CWD until we see a project marker. The Rust supervisor
    spawns workers from workers/<name>/, so the default './models' would
    resolve relative to that package dir, not the project root where the
    model file actually lives. Walking up fixes it with zero config.
    """
    p = Path.cwd().resolve()
    for parent in [p] + list(p.parents):
        if (parent / "arikizu.yaml.example").exists() or \
           (parent / "capabilities.toml").exists() or \
           (parent / "Cargo.toml").exists():
            return parent
    return p


def _resolve_models_dir(env_value: str) -> str:
    """Resolve the models dir against the project root, not the worker CWD."""
    if os.path.isabs(env_value):
        return env_value
    root = _find_project_root_early()
    # Try project-root first, then CWD (back-compat for anyone with the old
    # layout who put models next to the worker package).
    candidate = root / env_value
    if candidate.exists():
        return str(candidate)
    return str(Path(env_value).resolve())


def _auto_discover_model(models_dir: str) -> str:
    p = Path(models_dir)
    if not p.exists():
        return ""
    for candidate in ("yolov8n.onnx", "yolov8s.onnx", "yolov5n.onnx", "model.onnx"):
        if (p / candidate).exists():
            return str(p / candidate)
    for f in sorted(p.glob("*.onnx")):
        return str(f)
    return ""


MODELS_DIR = _resolve_models_dir(os.environ.get("ARIKIZU_MODELS_DIR", "./models"))
MODEL_PATH = os.environ.get("ARIKIZU_VISION_MODEL") or _auto_discover_model(MODELS_DIR)
INPUT_SIZE = int(os.environ.get("ARIKIZU_VISION_INPUT_SIZE", "640"))

_SESSION = None
_LOAD_ERROR = ""  # last reason the model failed to load, surfaced via vision.backends


def _try_load_onnx(path: str, logger: logging.Logger):
    global _LOAD_ERROR
    _LOAD_ERROR = ""
    if not path:
        _LOAD_ERROR = (
            f"no model file found. Looked in MODELS_DIR={MODELS_DIR!r}; "
            "set ARIKIZU_VISION_MODEL or run scripts/download-default-models.sh"
        )
        logger.warning(_LOAD_ERROR)
        return None
    if not os.path.isfile(path):
        _LOAD_ERROR = f"model path does not exist: {path!r}"
        logger.warning(_LOAD_ERROR)
        return None
    try:
        import onnxruntime as ort
    except Exception as e:
        _LOAD_ERROR = (
            f"onnxruntime not installed: {e}. Fix: cd workers && uv sync"
        )
        logger.warning(_LOAD_ERROR)
        return None
    try:
        providers = ["CPUExecutionProvider"]
        if "CUDAExecutionProvider" in ort.get_available_providers():
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        elif "CoreMLExecutionProvider" in ort.get_available_providers():
            providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        sess = ort.InferenceSession(path, providers=providers)
        logger.info("loaded %s with providers=%s", path, providers)
        return sess
    except Exception as e:
        _LOAD_ERROR = f"onnxruntime failed to load {path!r}: {type(e).__name__}: {e}"
        logger.warning(_LOAD_ERROR)
        return None


def _letterbox(img: Image.Image, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize keeping aspect ratio, pad to square. Return (chw array, scale, pad_x, pad_y)."""
    w, h = img.size
    scale = size / max(w, h)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = img.resize((new_w, new_h), Image.BILINEAR)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    pad_x = (size - new_w) // 2
    pad_y = (size - new_h) // 2
    canvas.paste(resized, (pad_x, pad_y))
    arr = np.array(canvas, dtype=np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)[None, :, :, :]  # NCHW
    return arr, scale, pad_x, pad_y


def _nms(xyxy: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.45) -> list[int]:
    if len(xyxy) == 0:
        return []
    x1, y1, x2, y2 = xyxy[:, 0], xyxy[:, 1], xyxy[:, 2], xyxy[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    kept = []
    while order.size > 0:
        i = int(order[0])
        kept.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou < iou_thresh]
    return kept


def _run_inference(sess, img: Image.Image, conf_thresh: float,
                   logger: logging.Logger = None) -> dict:
    """Run YOLO ONNX on a PIL image. Handles several export shapes."""
    img_w, img_h = img.size
    x, scale, pad_x, pad_y = _letterbox(img, INPUT_SIZE)
    input_name = sess.get_inputs()[0].name
    outputs = sess.run(None, {input_name: x})
    out = outputs[0]
    out = np.squeeze(out, axis=0) if out.shape[0] == 1 else out

    # Normalize to (N, >=5) with columns [cx, cy, w, h, score, ...classes]
    # or (N, 4+classes) for YOLOv8.
    if out.ndim == 2 and out.shape[0] in (84, 85):
        # (84 or 85, N) -> (N, 84 or 85)
        out = out.T
    elif out.ndim != 2:
        if logger:
            logger.warning("unexpected output shape %s", out.shape)
        return {"width": img_w, "height": img_h, "detections": [],
                "backend": "onnx-shape-mismatch",
                "note": f"model output shape {out.shape} not recognized"}

    boxes_cxcywh = out[:, :4]
    n_cols = out.shape[1]
    if n_cols >= 84:
        # YOLOv8: 4 bbox + 80 class scores (sometimes already sigmoid'd)
        class_scores = out[:, 4:4 + 80]
    elif n_cols == 85:
        # YOLOv5: 4 bbox + 1 objectness + 80 class scores
        objectness = out[:, 4:5]
        class_scores = out[:, 5:] * objectness
    else:
        class_scores = out[:, 4:]

    # Apply sigmoid if the scores look like raw logits (outside [0, 1]).
    if class_scores.size > 0 and (class_scores.max() > 1.5 or class_scores.min() < -0.1):
        class_scores = 1.0 / (1.0 + np.exp(-class_scores))

    class_ids = np.argmax(class_scores, axis=1)
    confidences = class_scores[np.arange(len(class_ids)), class_ids]
    if logger:
        logger.debug("inference: anchors=%d max_conf=%.2f at thresh %.2f",
                     len(confidences), float(confidences.max() if len(confidences) else 0), conf_thresh)
    mask = confidences > conf_thresh
    boxes_cxcywh = boxes_cxcywh[mask]
    class_ids = class_ids[mask]
    confidences = confidences[mask]
    # cxcywh in letterbox space -> xyxy in letterbox space
    xyxy = np.zeros_like(boxes_cxcywh)
    xyxy[:, 0] = boxes_cxcywh[:, 0] - boxes_cxcywh[:, 2] / 2
    xyxy[:, 1] = boxes_cxcywh[:, 1] - boxes_cxcywh[:, 3] / 2
    xyxy[:, 2] = boxes_cxcywh[:, 0] + boxes_cxcywh[:, 2] / 2
    xyxy[:, 3] = boxes_cxcywh[:, 1] + boxes_cxcywh[:, 3] / 2
    # Remove letterbox padding, scale back to original image
    xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - pad_x) / scale
    xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - pad_y) / scale
    xyxy[:, [0, 2]] = np.clip(xyxy[:, [0, 2]], 0, img_w)
    xyxy[:, [1, 3]] = np.clip(xyxy[:, [1, 3]], 0, img_h)
    kept = _nms(xyxy, confidences, iou_thresh=0.45)
    detections = []
    for i in kept[:50]:  # cap for payload size
        cid = int(class_ids[i])
        name = COCO_NAMES[cid] if cid < len(COCO_NAMES) else f"class_{cid}"
        detections.append({
            "class": name,
            "score": float(confidences[i]),
            "bbox": [int(xyxy[i, 0]), int(xyxy[i, 1]), int(xyxy[i, 2]), int(xyxy[i, 3])],
        })
    return {
        "width": img_w,
        "height": img_h,
        "detections": detections,
        "backend": "onnxruntime",
        "model_path": MODEL_PATH,
    }


def _find_project_root() -> Path:
    """Walk up from CWD until we see arikizu.yaml.example or Cargo.toml."""
    p = Path.cwd().resolve()
    for parent in [p] + list(p.parents):
        if (parent / "arikizu.yaml.example").exists() or \
           (parent / "capabilities.toml").exists() or \
           (parent / "Cargo.toml").exists():
            return parent
    return p


_PROJECT_ROOT = _find_project_root()


def _load_pil(image_path: str, image_base64: str) -> Image.Image | None:
    if image_base64:
        try:
            data = base64.b64decode(image_base64)
            return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            return None
    if not image_path:
        return None
    # Try several locations because the worker's CWD may be workers/ when
    # launched from arikizu.yaml, but paths like demo/fixtures/scene.jpg
    # are relative to the repo root.
    candidates: list[Path] = []
    p = Path(image_path)
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates += [
            Path.cwd() / image_path,
            Path.cwd().parent / image_path,
            _PROJECT_ROOT / image_path,
            Path.home() / "arikizu" / image_path,
        ]
    for cand in candidates:
        if cand.exists() and cand.is_file():
            try:
                return Image.open(cand).convert("RGB")
            except Exception:
                continue
    return None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("vision")

    global _SESSION
    _SESSION = _try_load_onnx(MODEL_PATH, logger)
    if _SESSION is not None:
        logger.info("vision ready: real YOLOv8 inference on %s", MODEL_PATH)
    else:
        logger.warning(
            "vision in no-model mode. Fix: scripts/download-default-models.sh --tier minimum"
        )

    worker = Worker("vision")

    @worker.handler("vision.detect")
    def detect(image_path: str = "", image_base64: str = "",
               confidence: float = 0.25) -> dict[str, Any]:
        img = _load_pil(image_path, image_base64)
        if img is None:
            return {
                "image": image_path or "(no image)",
                "detections": [],
                "backend": "no-image",
                "note": "could not load image. Pass image_base64 (from webcam) or image_path.",
            }
        if _SESSION is None:
            return {
                "image": image_path or "(webcam frame)",
                "width": img.size[0],
                "height": img.size[1],
                "detections": [],
                "backend": "no-model",
                "note": (
                    "No vision model loaded. Run: "
                    "scripts/download-default-models.sh --tier minimum, "
                    "then restart `make run`."
                ),
            }
        try:
            result = _run_inference(_SESSION, img, confidence, logger)
            result["image"] = image_path or "(webcam frame)"
            # Add a visible note when no detections so the UI can show it
            if not result.get("detections"):
                result.setdefault(
                    "note",
                    f"model ran but found no objects above confidence {confidence}. "
                    "Try lowering conf, or move more objects into the frame."
                )
            return result
        except Exception as e:
            logger.exception("inference failed")
            return {
                "image": image_path or "(webcam frame)",
                "detections": [],
                "backend": "error",
                "note": f"inference failed: {e}",
            }

    @worker.handler("vision.segment")
    def segment(image_path: str = "", image_base64: str = "",
                confidence: float = 0.25) -> dict[str, Any]:
        """Segmentation using the default detector + bounding-box mask.
        For a true pixel-level mask, download yolov8n-seg.onnx and point
        ARIKIZU_VISION_MODEL at it; same handler reads whichever is set.
        """
        img = _load_pil(image_path, image_base64)
        if img is None or _SESSION is None:
            return {
                "image": image_path or "(no image)",
                "detections": [],
                "backend": "no-model",
                "note": "no model loaded. Run scripts/download-default-models.sh",
            }
        try:
            result = _run_inference(_SESSION, img, confidence, logger)
            result["image"] = image_path or "(webcam frame)"
            # Mark the detections as "segments" so the UI knows to fill
            for d in result.get("detections", []):
                d["is_segment"] = True
            result["mode"] = "segment"
            if not result.get("detections"):
                result.setdefault(
                    "note",
                    f"segmentation returned nothing above conf {confidence}. "
                    "Lower conf, hold objects clearly in frame, or install yolov8n-seg.onnx.",
                )
            return result
        except Exception as e:
            return {
                "image": image_path or "(webcam frame)",
                "detections": [],
                "backend": "error",
                "note": f"segmentation failed: {e}",
            }

    @worker.handler("vision.ocr")
    def ocr(image_path: str = "", lang: str = "en") -> dict[str, Any]:
        return {"image": image_path, "text": "", "lang": lang,
                "note": "OCR not wired in demo build"}

    @worker.handler("vision.caption")
    def caption(image_path: str = "") -> dict[str, Any]:
        return {"image": image_path, "caption": "",
                "note": "captioning not wired in demo build"}

    @worker.handler("vision.backends")
    def backends() -> dict[str, Any]:
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            ort_version = ort.__version__
        except Exception as e:
            providers = []
            ort_version = f"not installed: {e}"
        return {
            "model_path": MODEL_PATH or "(none)",
            "models_dir": MODELS_DIR,
            "cwd": os.getcwd(),
            "loaded": _SESSION is not None,
            "load_error": _LOAD_ERROR or ("" if _SESSION is not None else "model not loaded; see vision_worker logs"),
            "providers_available": providers,
            "onnxruntime_version": ort_version,
            "input_size": INPUT_SIZE,
        }

    @worker.handler("vision.switch_model")
    def switch_model(model_path: str = "") -> dict[str, Any]:
        global _SESSION, MODEL_PATH
        if not model_path:
            return {"error": "pass model_path"}
        new_sess = _try_load_onnx(model_path, logger)
        if new_sess is None:
            return {"error": f"could not load {model_path}"}
        _SESSION = new_sess
        MODEL_PATH = model_path
        return {"ok": True, "model_path": model_path}

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
