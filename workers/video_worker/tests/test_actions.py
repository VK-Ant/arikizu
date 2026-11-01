"""Unit tests for rule-based action recognition.

Each test feeds a canned pose landmark set that corresponds to one action
and asserts the recognizer returns that label. No MediaPipe needed; this
isolates the action-rule logic from the perception stack.
"""
from __future__ import annotations

from video_worker.actions import PoseFrame, recognize


def _landmarks_zero() -> list[tuple[float, float, float]]:
    """33 landmarks all at (0.5, 0.5, 0) with low visibility, as a baseline."""
    return [(0.5, 0.5, 0.0) for _ in range(33)]


def test_hands_up():
    lm = _landmarks_zero()
    lm[0] = (0.5, 0.4, 0.0)      # nose at y=0.4
    lm[15] = (0.4, 0.2, 0.0)     # left wrist above nose
    lm[16] = (0.6, 0.2, 0.0)     # right wrist above nose
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis))
    assert r["action"] == "hands_up"
    assert r["confidence"] >= 0.7


def test_sitting_by_knee_angle():
    lm = _landmarks_zero()
    # Hips roughly same height as knees -> sitting
    lm[23] = (0.4, 0.5, 0.0)   # left hip
    lm[24] = (0.6, 0.5, 0.0)   # right hip
    lm[25] = (0.4, 0.54, 0.0)  # left knee just below hips
    lm[26] = (0.6, 0.54, 0.0)  # right knee
    lm[27] = (0.4, 0.9, 0.0)   # left ankle far below
    lm[28] = (0.6, 0.9, 0.0)
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis))
    assert r["action"] == "sitting"


def test_standing_still():
    lm = _landmarks_zero()
    # Upright: hips above knees above ankles
    lm[23] = (0.4, 0.4, 0.0)
    lm[24] = (0.6, 0.4, 0.0)
    lm[25] = (0.4, 0.6, 0.0)
    lm[26] = (0.6, 0.6, 0.0)
    lm[27] = (0.4, 0.9, 0.0)
    lm[28] = (0.6, 0.9, 0.0)
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis), motion_px_per_s=5.0)
    assert r["action"] == "standing"


def test_walking_moderate_motion():
    lm = _landmarks_zero()
    lm[23] = (0.4, 0.4, 0.0); lm[24] = (0.6, 0.4, 0.0)
    lm[25] = (0.4, 0.6, 0.0); lm[26] = (0.6, 0.6, 0.0)
    lm[27] = (0.4, 0.9, 0.0); lm[28] = (0.6, 0.9, 0.0)
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis), motion_px_per_s=60.0)
    assert r["action"] == "walking"


def test_running_high_motion():
    lm = _landmarks_zero()
    lm[23] = (0.4, 0.4, 0.0); lm[24] = (0.6, 0.4, 0.0)
    lm[25] = (0.4, 0.6, 0.0); lm[26] = (0.6, 0.6, 0.0)
    lm[27] = (0.4, 0.9, 0.0); lm[28] = (0.6, 0.9, 0.0)
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis), motion_px_per_s=250.0)
    assert r["action"] == "running"


def test_kicking():
    lm = _landmarks_zero()
    # Hips at y=0.5, knees well below at y=0.75 (not sitting),
    # left ankle at y=0.3 (above hips in image coords -> kicking)
    lm[0] = (0.5, 0.3, 0.0)                               # nose above the raised ankle
    lm[23] = (0.4, 0.5, 0.0); lm[24] = (0.6, 0.5, 0.0)
    lm[25] = (0.4, 0.75, 0.0); lm[26] = (0.6, 0.75, 0.0)
    lm[27] = (0.4, 0.3, 0.0); lm[28] = (0.6, 0.9, 0.0)
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis))
    assert r["action"] == "kicking"


def test_falling_requires_hip_dy():
    lm = _landmarks_zero()
    lm[23] = (0.4, 0.8, 0.0); lm[24] = (0.6, 0.8, 0.0)
    lm[25] = (0.4, 0.5, 0.0); lm[26] = (0.6, 0.5, 0.0)
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis), hip_dy=0.25)
    assert r["action"] == "falling"


def test_arms_crossed():
    lm = _landmarks_zero()
    # Standing shape (not sitting), nose above wrists
    lm[0] = (0.5, 0.2, 0.0)
    lm[11] = (0.4, 0.3, 0.0)   # left shoulder
    lm[12] = (0.6, 0.3, 0.0)   # right shoulder
    lm[15] = (0.7, 0.5, 0.0)   # left wrist crossed to right side
    lm[16] = (0.3, 0.5, 0.0)   # right wrist crossed to left side
    lm[23] = (0.4, 0.6, 0.0); lm[24] = (0.6, 0.6, 0.0)
    lm[25] = (0.4, 0.75, 0.0); lm[26] = (0.6, 0.75, 0.0)
    lm[27] = (0.4, 0.9, 0.0); lm[28] = (0.6, 0.9, 0.0)
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis))
    assert r["action"] == "arms_crossed"


def test_pointing_right():
    lm = _landmarks_zero()
    # Nose high so wrists at y=0.4 are NOT above it (defeats hands_up).
    # Right arm fully extended horizontally (shoulder-elbow-wrist in a line
    # at same y), left arm bent at the elbow.
    lm[0] = (0.5, 0.2, 0.0)
    lm[11] = (0.4, 0.4, 0.0); lm[12] = (0.6, 0.4, 0.0)   # shoulders
    lm[13] = (0.35, 0.5, 0.0)                             # left elbow (bent)
    lm[14] = (0.75, 0.4, 0.0)                             # right elbow (same y as shoulder)
    lm[15] = (0.4, 0.55, 0.0)                             # left wrist (bent back toward shoulder)
    lm[16] = (0.9, 0.4, 0.0)                              # right wrist (straight line w/ shoulder+elbow)
    # Add a standing base so sitting doesn't fire
    lm[23] = (0.4, 0.6, 0.0); lm[24] = (0.6, 0.6, 0.0)
    lm[25] = (0.4, 0.75, 0.0); lm[26] = (0.6, 0.75, 0.0)
    lm[27] = (0.4, 0.9, 0.0); lm[28] = (0.6, 0.9, 0.0)
    vis = [1.0] * 33
    r = recognize(PoseFrame(lm, vis))
    assert r["action"] == "pointing"


def test_unknown_floor():
    """Very visible but garbage input should be reported as unknown, not forced."""
    lm = [(0.0, 0.0, 0.0)] * 33
    vis = [0.1] * 33   # low visibility
    r = recognize(PoseFrame(lm, vis))
    assert r["action"] == "unknown"


def test_actions_known_registry():
    from video_worker.actions import ACTIONS_KNOWN, action_definitions
    defs = {d["name"] for d in action_definitions()}
    assert set(ACTIONS_KNOWN) == defs
    assert len(ACTIONS_KNOWN) == 12
