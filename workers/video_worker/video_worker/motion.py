"""Optical-flow motion analysis.

Dense Farneback flow between consecutive frames gives us a per-clip motion
level, dominant direction, and an active-segments timeline. Cheap on CPU
and runs on any machine OpenCV runs on.
"""
from __future__ import annotations

import numpy as np


def flow_vector(prev_gray: np.ndarray, next_gray: np.ndarray) -> tuple[float, float]:
    """Return (mean_dx, mean_dy) per pixel between two consecutive gray frames."""
    import cv2
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, next_gray, None,
        pyr_scale=0.5, levels=3, winsize=15, iterations=3,
        poly_n=5, poly_sigma=1.2, flags=0,
    )
    return float(flow[..., 0].mean()), float(flow[..., 1].mean())


def flow_magnitude(prev_gray: np.ndarray, next_gray: np.ndarray) -> float:
    """Average flow magnitude between two frames."""
    import cv2
    flow = cv2.calcOpticalFlowFarneback(
        prev_gray, next_gray, None,
        pyr_scale=0.5, levels=3, winsize=15, iterations=3,
        poly_n=5, poly_sigma=1.2, flags=0,
    )
    mag = np.hypot(flow[..., 0], flow[..., 1])
    return float(mag.mean())


def classify_level(px_per_frame: float, fps: float = 24.0) -> str:
    """Human-readable motion level given a per-frame magnitude."""
    per_sec = px_per_frame * fps
    if per_sec < 10:
        return "still"
    if per_sec < 60:
        return "low"
    if per_sec < 200:
        return "moderate"
    return "high"
