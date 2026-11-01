"""MediaPipe perception wrapper: detector, pose, segmenter, face.

Fails gracefully if MediaPipe is not installed. The worker will still start
and all VLM / rule-based features continue to work; only live overlays and
action recognition on video need this.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from . import models

try:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision as mp_vision
    MP_OK = True
    MP_IMPORT_ERR = ""
except Exception as e:
    MP_OK = False
    MP_IMPORT_ERR = str(e)


DET_SCORE = float(os.getenv("DETECTION_THRESHOLD", "0.35"))
PERSON_SCORE = float(os.getenv("PERSON_THRESHOLD", "0.25"))
MP_DELEGATE = os.getenv("MP_DELEGATE", "cpu").lower()


@dataclass
class Detection:
    label: str
    score: float
    bbox: tuple[float, float, float, float]      # normalized x1, y1, x2, y2 (0..1)


@dataclass
class FrameResult:
    """One frame's perception output."""
    detections: list[Detection] = field(default_factory=list)
    pose_landmarks: list[tuple[float, float, float]] = field(default_factory=list)   # 33 (x, y, z) per person-0
    pose_visibility: list[float] = field(default_factory=list)
    person_mask_shape: tuple[int, int] | None = None    # (h, w) if a mask was produced
    faces: list[tuple[float, float, float, float]] = field(default_factory=list)     # normalized x, y, w, h
    ms: dict[str, float] = field(default_factory=dict)
    width: int = 0
    height: int = 0

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "detections": [
                {"label": d.label, "score": round(d.score, 3),
                 "bbox": [round(v, 4) for v in d.bbox]}
                for d in self.detections
            ],
            "pose_landmarks": [[round(x, 4), round(y, 4), round(z, 4)] for x, y, z in self.pose_landmarks],
            "pose_visibility": [round(v, 3) for v in self.pose_visibility],
            "faces": [[round(v, 4) for v in f] for f in self.faces],
            "ms": self.ms,
            "width": self.width, "height": self.height,
        }


class MediaPipePerception:
    """One instance per worker process. Not thread-safe."""

    def __init__(self, detector_key: str = "efficientdet_lite0",
                 pose_key: str = "pose_landmarker_lite",
                 want_face: bool = True):
        if not MP_OK:
            raise RuntimeError(
                f"MediaPipe not installed: {MP_IMPORT_ERR}. "
                "Fix: cd workers && uv add mediapipe --package video-worker"
            )
        delegate = BaseOptions.Delegate.GPU if MP_DELEGATE == "gpu" else BaseOptions.Delegate.CPU
        running = mp_vision.RunningMode.VIDEO

        det_path = models.ensure(detector_key)
        pose_path = models.ensure(pose_key)
        self.detector = mp_vision.ObjectDetector.create_from_options(
            mp_vision.ObjectDetectorOptions(
                base_options=BaseOptions(model_asset_path=str(det_path), delegate=delegate),
                running_mode=running,
                score_threshold=min(DET_SCORE, PERSON_SCORE),
                max_results=16,
            )
        )
        self.pose = mp_vision.PoseLandmarker.create_from_options(
            mp_vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(pose_path), delegate=delegate),
                running_mode=running,
                num_poses=3,
                output_segmentation_masks=True,
            )
        )
        self.face = None
        if want_face:
            try:
                face_path = models.ensure("blaze_face")
                self.face = mp_vision.FaceDetector.create_from_options(
                    mp_vision.FaceDetectorOptions(
                        base_options=BaseOptions(model_asset_path=str(face_path), delegate=delegate),
                        running_mode=running,
                        min_detection_confidence=0.4,
                    )
                )
            except Exception:
                self.face = None   # face is optional; worker still runs without blur
        self._ts = 0

    def process(self, rgb_image: np.ndarray) -> FrameResult:
        """Run detector + pose + face on one RGB uint8 frame (H, W, 3)."""
        h, w = rgb_image.shape[:2]
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_image)
        # Monotonic timestamp in ms, must be strictly increasing in VIDEO mode.
        self._ts += 1
        ts = self._ts

        out = FrameResult(width=w, height=h)
        ms: dict[str, float] = {}

        t = time.perf_counter()
        det_result = self.detector.detect_for_video(mp_img, ts)
        ms["detect"] = round((time.perf_counter() - t) * 1000, 1)
        for d in det_result.detections:
            box = d.bounding_box
            x1 = box.origin_x / w
            y1 = box.origin_y / h
            x2 = (box.origin_x + box.width) / w
            y2 = (box.origin_y + box.height) / h
            cat = d.categories[0]
            out.detections.append(Detection(
                label=cat.category_name or "object",
                score=float(cat.score),
                bbox=(max(0, x1), max(0, y1), min(1, x2), min(1, y2)),
            ))

        t = time.perf_counter()
        pose_result = self.pose.detect_for_video(mp_img, ts)
        ms["pose"] = round((time.perf_counter() - t) * 1000, 1)
        if pose_result.pose_landmarks:
            lms = pose_result.pose_landmarks[0]
            out.pose_landmarks = [(lm.x, lm.y, lm.z) for lm in lms]
            out.pose_visibility = [getattr(lm, "visibility", 1.0) for lm in lms]
        if pose_result.segmentation_masks:
            mask = pose_result.segmentation_masks[0]
            arr = mask.numpy_view()
            out.person_mask_shape = arr.shape[:2]

        if self.face is not None:
            t = time.perf_counter()
            face_result = self.face.detect_for_video(mp_img, ts)
            ms["face"] = round((time.perf_counter() - t) * 1000, 1)
            for det in face_result.detections:
                box = det.bounding_box
                out.faces.append((
                    box.origin_x / w, box.origin_y / h,
                    box.width / w, box.height / h,
                ))

        out.ms = ms
        return out


def available() -> dict[str, Any]:
    """Reportable status for video.backends."""
    return {
        "mediapipe_installed": MP_OK,
        "mediapipe_error": MP_IMPORT_ERR if not MP_OK else "",
        "delegate": MP_DELEGATE,
        "detection_threshold": DET_SCORE,
        "person_threshold": PERSON_SCORE,
    }
