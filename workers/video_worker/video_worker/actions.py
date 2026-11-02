"""Rule-based action recognition from pose landmarks and motion.

Twelve actions, each evaluated as a function of 33 MediaPipe pose landmarks
plus optional motion vectors from optical flow. No training required. Honest
limits apply: these rules cover the common body-language actions; everything
more subtle (typing, cooking, dancing) is left to the VLM.

Each rule returns (confidence_0_to_1, evidence_dict). The dispatcher picks
the highest-confidence action above a threshold, or 'unknown' when no rule
fires.

Landmark indices follow MediaPipe PoseLandmarker:
    0  nose
    11 left_shoulder   12 right_shoulder
    13 left_elbow      14 right_elbow
    15 left_wrist      16 right_wrist
    23 left_hip        24 right_hip
    25 left_knee       26 right_knee
    27 left_ankle      28 right_ankle
"""
from __future__ import annotations

import math
from typing import Any


NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28


# Threshold below which we report 'unknown' rather than guess.
CONFIDENCE_FLOOR = 0.40


def _midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    """Angle at vertex b in degrees (0 = straight line, 180 = reverse)."""
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 * n2 == 0:
        return 180.0
    cos = max(-1.0, min(1.0, dot / (n1 * n2)))
    return math.degrees(math.acos(cos))


class PoseFrame:
    """A single frame of pose landmarks. Coordinates are normalized 0..1 in image space."""

    def __init__(self, landmarks: list[tuple[float, float, float]], visible: list[float] | None = None):
        """landmarks: list of (x, y, z) per MediaPipe. visible: optional per-landmark visibility 0..1."""
        self.lm = landmarks
        self.vis = visible or [1.0] * len(landmarks)

    def xy(self, i: int) -> tuple[float, float]:
        return (self.lm[i][0], self.lm[i][1])

    def ok(self, *idxs: int) -> bool:
        """All requested landmarks are visible (visibility > 0.3)."""
        return all(self.vis[i] > 0.3 for i in idxs)


# ---------------------------------------------------------------------------
# Individual action rules.
# Each returns (confidence, evidence_dict).
# ---------------------------------------------------------------------------

def is_standing(pose: PoseFrame, motion_px_per_s: float = 0.0) -> tuple[float, dict]:
    """Hips above knees above ankles, body upright, little motion."""
    if not pose.ok(L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE):
        return 0.0, {}
    hip_y = (pose.xy(L_HIP)[1] + pose.xy(R_HIP)[1]) / 2
    knee_y = (pose.xy(L_KNEE)[1] + pose.xy(R_KNEE)[1]) / 2
    ankle_y = (pose.xy(L_ANKLE)[1] + pose.xy(R_ANKLE)[1]) / 2
    upright = hip_y < knee_y < ankle_y
    body_h = ankle_y - hip_y
    if not upright or body_h < 0.1:
        return 0.0, {}
    # Low motion is key for standing vs walking.
    motion_score = max(0.0, 1.0 - motion_px_per_s / 50.0)
    return 0.70 * motion_score, {"hip_y": hip_y, "ankle_y": ankle_y, "motion": motion_px_per_s}


def is_sitting(pose: PoseFrame) -> tuple[float, dict]:
    """Hips roughly at knee height; thighs horizontal."""
    if not pose.ok(L_HIP, R_HIP, L_KNEE, R_KNEE):
        return 0.0, {}
    hip = _midpoint(pose.xy(L_HIP), pose.xy(R_HIP))
    knee = _midpoint(pose.xy(L_KNEE), pose.xy(R_KNEE))
    vertical_gap = abs(hip[1] - knee[1])
    if vertical_gap < 0.08:   # hips and knees almost same height
        return 0.75, {"vertical_gap": vertical_gap}
    # Second rule: knee bent sharply (angle < 110 degrees)
    if pose.ok(L_HIP, L_KNEE, L_ANKLE):
        knee_angle = _angle(pose.xy(L_HIP), pose.xy(L_KNEE), pose.xy(L_ANKLE))
        if knee_angle < 110:
            return 0.60, {"knee_angle": knee_angle}
    return 0.0, {}


def is_walking(pose: PoseFrame, motion_px_per_s: float) -> tuple[float, dict]:
    """Upright + moderate motion + alternating legs."""
    if not pose.ok(L_HIP, R_HIP, L_ANKLE, R_ANKLE):
        return 0.0, {}
    standing_conf, _ = is_standing(pose, 0.0)   # just check upright shape
    if standing_conf < 0.1:
        return 0.0, {}
    if 20 < motion_px_per_s < 150:
        return 0.75, {"motion": motion_px_per_s}
    return 0.0, {}


def is_running(pose: PoseFrame, motion_px_per_s: float) -> tuple[float, dict]:
    """Walking shape + high motion. We rely on the recognizer to pick running
    over walking when motion is high enough."""
    if not pose.ok(L_HIP, R_HIP, L_ANKLE, R_ANKLE):
        return 0.0, {}
    standing_conf, _ = is_standing(pose, 0.0)
    if standing_conf < 0.1:
        return 0.0, {}
    if motion_px_per_s > 150:
        return 0.80, {"motion": motion_px_per_s}
    return 0.0, {}


def is_waving(pose: PoseFrame, wrist_motion: tuple[float, float, float, float] | None = None) -> tuple[float, dict]:
    """At least one wrist above shoulder, with lateral motion in recent frames.

    wrist_motion: (lw_dx, lw_dy, rw_dx, rw_dy) over the last ~0.5s if known.
    """
    if not pose.ok(L_WRIST, L_SHOULDER, R_WRIST, R_SHOULDER):
        return 0.0, {}
    lw_up = pose.xy(L_WRIST)[1] < pose.xy(L_SHOULDER)[1]
    rw_up = pose.xy(R_WRIST)[1] < pose.xy(R_SHOULDER)[1]
    if not (lw_up or rw_up):
        return 0.0, {}
    if wrist_motion is None:
        return 0.55, {"wrist_above_shoulder": True}
    lw_dx, lw_dy, rw_dx, rw_dy = wrist_motion
    lateral = max(abs(lw_dx), abs(rw_dx))
    if lateral > 0.05:
        return 0.80, {"lateral_motion": lateral}
    return 0.55, {"wrist_above_shoulder": True}


def is_kicking(pose: PoseFrame, ankle_motion: tuple[float, float] | None = None) -> tuple[float, dict]:
    """One ankle above the other hip level with upward motion."""
    if not pose.ok(L_ANKLE, R_ANKLE, L_HIP, R_HIP):
        return 0.0, {}
    hip_y = (pose.xy(L_HIP)[1] + pose.xy(R_HIP)[1]) / 2
    la_y = pose.xy(L_ANKLE)[1]
    ra_y = pose.xy(R_ANKLE)[1]
    high_ankle = min(la_y, ra_y)
    if high_ankle < hip_y:   # ankle above hip in image coords (lower y)
        return 0.75, {"high_ankle_y": high_ankle, "hip_y": hip_y}
    return 0.0, {}


def is_jumping(pose: PoseFrame, hip_dy: float | None = None) -> tuple[float, dict]:
    """Both feet above baseline + rapid vertical motion."""
    if hip_dy is None or hip_dy > -0.08:
        return 0.0, {}
    # hip_dy < 0 means moving up in image coords.
    return 0.75, {"hip_dy": hip_dy}


def is_hands_up(pose: PoseFrame) -> tuple[float, dict]:
    """Both wrists above head, roughly stationary (frozen posture)."""
    if not pose.ok(L_WRIST, R_WRIST, NOSE):
        return 0.0, {}
    nose_y = pose.xy(NOSE)[1]
    if pose.xy(L_WRIST)[1] < nose_y and pose.xy(R_WRIST)[1] < nose_y:
        return 0.85, {"both_wrists_above_head": True}
    return 0.0, {}


def is_arms_crossed(pose: PoseFrame) -> tuple[float, dict]:
    """Each wrist is on the opposite side of the body from its shoulder."""
    if not pose.ok(L_WRIST, R_WRIST, L_SHOULDER, R_SHOULDER):
        return 0.0, {}
    lw_x = pose.xy(L_WRIST)[0]
    rw_x = pose.xy(R_WRIST)[0]
    ls_x = pose.xy(L_SHOULDER)[0]
    rs_x = pose.xy(R_SHOULDER)[0]
    # Left wrist crossed to right side (lw_x > rs_x) and vice versa.
    if lw_x > rs_x and rw_x < ls_x:
        return 0.75, {"lw_x": lw_x, "rw_x": rw_x}
    return 0.0, {}


def is_bending(pose: PoseFrame) -> tuple[float, dict]:
    """Shoulders much closer to hips in y than normal (bent torso)."""
    if not pose.ok(L_SHOULDER, R_SHOULDER, L_HIP, R_HIP):
        return 0.0, {}
    sh_y = (pose.xy(L_SHOULDER)[1] + pose.xy(R_SHOULDER)[1]) / 2
    hp_y = (pose.xy(L_HIP)[1] + pose.xy(R_HIP)[1]) / 2
    sh_x = (pose.xy(L_SHOULDER)[0] + pose.xy(R_SHOULDER)[0]) / 2
    hp_x = (pose.xy(L_HIP)[0] + pose.xy(R_HIP)[0]) / 2
    # Horizontal distance from shoulders to hips exceeds vertical distance = bent forward
    dx = abs(sh_x - hp_x)
    dy = abs(sh_y - hp_y)
    if dy < 0.05:
        return 0.0, {}
    if dx / dy > 0.6:
        return 0.60, {"dx": dx, "dy": dy}
    return 0.0, {}


def is_falling(pose: PoseFrame, hip_dy: float | None = None) -> tuple[float, dict]:
    """Rapid downward motion + hip below knee (collapsed posture)."""
    if hip_dy is None or hip_dy < 0.15:
        return 0.0, {}
    if not pose.ok(L_HIP, R_HIP, L_KNEE, R_KNEE):
        return 0.0, {}
    hip_y = (pose.xy(L_HIP)[1] + pose.xy(R_HIP)[1]) / 2
    knee_y = (pose.xy(L_KNEE)[1] + pose.xy(R_KNEE)[1]) / 2
    if hip_y > knee_y:   # hips below knees in image coords
        return 0.80, {"hip_dy": hip_dy}
    return 0.0, {}


def is_pointing(pose: PoseFrame) -> tuple[float, dict]:
    """One arm extended (shoulder-elbow-wrist nearly straight), other at rest."""
    if not pose.ok(L_SHOULDER, L_ELBOW, L_WRIST, R_SHOULDER, R_ELBOW, R_WRIST):
        return 0.0, {}
    l_angle = _angle(pose.xy(L_SHOULDER), pose.xy(L_ELBOW), pose.xy(L_WRIST))
    r_angle = _angle(pose.xy(R_SHOULDER), pose.xy(R_ELBOW), pose.xy(R_WRIST))
    # One arm straight (>160), the other bent (<120).
    if l_angle > 160 and r_angle < 120:
        return 0.65, {"left_angle": l_angle, "right_angle": r_angle, "side": "left"}
    if r_angle > 160 and l_angle < 120:
        return 0.65, {"left_angle": l_angle, "right_angle": r_angle, "side": "right"}
    return 0.0, {}


# ---------------------------------------------------------------------------
# Upper-body-only rules: for the common case where the camera only sees
# the torso + head (person sitting at a desk, close-up webcam, etc).
# ---------------------------------------------------------------------------

def is_head_down(pose: PoseFrame) -> tuple[float, dict]:
    """Nose much lower than shoulders (looking down, reading, dozing)."""
    if not pose.ok(NOSE, L_SHOULDER, R_SHOULDER):
        return 0.0, {}
    nose_y = pose.xy(NOSE)[1]
    sh_y = (pose.xy(L_SHOULDER)[1] + pose.xy(R_SHOULDER)[1]) / 2
    # Normally nose is well above shoulders (lower y). If nose has dropped
    # noticeably below the shoulder line, head is down.
    if nose_y > sh_y + 0.03:
        return 0.65, {"nose_y": round(nose_y, 3), "shoulder_y": round(sh_y, 3)}
    return 0.0, {}


def is_leaning_back(pose: PoseFrame) -> tuple[float, dict]:
    """Shoulders behind hips in horizontal distance (torso tilted back)."""
    if not pose.ok(L_SHOULDER, R_SHOULDER, L_HIP, R_HIP):
        return 0.0, {}
    sh_x = (pose.xy(L_SHOULDER)[0] + pose.xy(R_SHOULDER)[0]) / 2
    hp_x = (pose.xy(L_HIP)[0] + pose.xy(R_HIP)[0]) / 2
    sh_y = (pose.xy(L_SHOULDER)[1] + pose.xy(R_SHOULDER)[1]) / 2
    hp_y = (pose.xy(L_HIP)[1] + pose.xy(R_HIP)[1]) / 2
    # Negligible vertical difference: not leaning
    dy = hp_y - sh_y
    if dy < 0.05:
        return 0.0, {}
    dx = abs(sh_x - hp_x)
    # Noticeable horizontal offset AND still upright-ish
    if dx / dy > 0.35 and dx / dy < 0.9:
        return 0.60, {"dx": round(dx, 3), "dy": round(dy, 3)}
    return 0.0, {}


def is_typing(pose: PoseFrame) -> tuple[float, dict]:
    """Both wrists near each other at waist height, elbows bent sharply.
    A classic 'hands on keyboard' posture."""
    if not pose.ok(L_WRIST, R_WRIST, L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW):
        return 0.0, {}
    lw = pose.xy(L_WRIST); rw = pose.xy(R_WRIST)
    sh_y = (pose.xy(L_SHOULDER)[1] + pose.xy(R_SHOULDER)[1]) / 2
    # Wrists below shoulders (not up in the air)
    if lw[1] < sh_y + 0.08 or rw[1] < sh_y + 0.08:
        return 0.0, {}
    # Wrists close horizontally (keyboard width, not arms-wide).
    # Shoulder-width is a natural upper bound.
    wrist_gap = abs(lw[0] - rw[0])
    shoulder_gap = abs(pose.xy(L_SHOULDER)[0] - pose.xy(R_SHOULDER)[0]) or 0.001
    if wrist_gap > shoulder_gap * 0.9:
        return 0.0, {}
    # Elbows bent
    l_angle = _angle(pose.xy(L_SHOULDER), pose.xy(L_ELBOW), lw)
    r_angle = _angle(pose.xy(R_SHOULDER), pose.xy(R_ELBOW), rw)
    if l_angle < 150 and r_angle < 150:
        return 0.70, {"wrist_gap": round(wrist_gap, 3),
                      "l_elbow": round(l_angle, 1), "r_elbow": round(r_angle, 1)}
    return 0.0, {}


def is_resting(pose: PoseFrame) -> tuple[float, dict]:
    """Shoulders horizontal, arms hanging / resting below shoulders, no gesture."""
    if not pose.ok(L_SHOULDER, R_SHOULDER, L_WRIST, R_WRIST, NOSE):
        return 0.0, {}
    sh_y = (pose.xy(L_SHOULDER)[1] + pose.xy(R_SHOULDER)[1]) / 2
    nose_y = pose.xy(NOSE)[1]
    # Head upright
    if nose_y > sh_y - 0.05:
        return 0.0, {}
    # Both wrists below shoulders
    if pose.xy(L_WRIST)[1] < sh_y or pose.xy(R_WRIST)[1] < sh_y:
        return 0.0, {}
    # Base-posture class with LOW confidence so specific gestures win when
    # they fire. Returns a signal when upper body is visible and still.
    return 0.45, {}


# ---------------------------------------------------------------------------
# Dispatcher: run every rule, pick the strongest.
# ---------------------------------------------------------------------------

ACTIONS_KNOWN = [
    # Full-body
    "standing", "sitting", "walking", "running", "waving", "kicking",
    "jumping", "hands_up", "arms_crossed", "bending", "falling", "pointing",
    # Upper-body-only (desk / webcam close-up)
    "head_down", "leaning_back", "typing", "resting",
]


def recognize(pose: PoseFrame,
              motion_px_per_s: float = 0.0,
              wrist_motion: tuple[float, float, float, float] | None = None,
              ankle_motion: tuple[float, float] | None = None,
              hip_dy: float | None = None) -> dict[str, Any]:
    """Run every rule and return the top action above the confidence floor.

    Returns {"action": str, "confidence": float, "evidence": dict,
             "scores": {action_name: confidence}}
    """
    scores: dict[str, tuple[float, dict]] = {
        "standing": is_standing(pose, motion_px_per_s),
        "sitting": is_sitting(pose),
        "walking": is_walking(pose, motion_px_per_s),
        "running": is_running(pose, motion_px_per_s),
        "waving": is_waving(pose, wrist_motion),
        "kicking": is_kicking(pose, ankle_motion),
        "jumping": is_jumping(pose, hip_dy),
        "hands_up": is_hands_up(pose),
        "arms_crossed": is_arms_crossed(pose),
        "bending": is_bending(pose),
        "falling": is_falling(pose, hip_dy),
        "pointing": is_pointing(pose),
        # Upper-body-only rules
        "head_down": is_head_down(pose),
        "leaning_back": is_leaning_back(pose),
        "typing": is_typing(pose),
        "resting": is_resting(pose),
    }
    # Running overrides walking at high motion. Falling overrides sitting
    # if both fire. Hands_up overrides waving (frozen trumps motion).
    if scores["running"][0] >= scores["walking"][0] - 0.05:
        scores["walking"] = (0.0, {})
    if scores["falling"][0] > 0.5:
        scores["sitting"] = (0.0, {})
    if scores["hands_up"][0] > 0.7:
        scores["waving"] = (0.0, {})
    # Gestures override base posture: if we can see someone pointing or
    # waving, that is a more useful label than "standing" or "resting".
    gesture_conf = max(scores["pointing"][0], scores["waving"][0],
                       scores["hands_up"][0], scores["arms_crossed"][0],
                       scores["kicking"][0])
    if gesture_conf >= CONFIDENCE_FLOOR:
        scores["standing"] = (0.0, {})
        scores["resting"] = (0.0, {})
    # Typing beats arms_crossed when the hands are clearly on a keyboard
    # (close together, elbows bent). This matches the common webcam/desk case.
    if scores["typing"][0] > 0.65 and scores["arms_crossed"][0] < 0.80:
        scores["arms_crossed"] = (0.0, {})
    # arms_crossed needs STRONGER evidence than before, because a bad
    # pose read with wrists at mid-body can fire it accidentally.
    if scores["arms_crossed"][0] > 0 and scores["arms_crossed"][0] < 0.72:
        scores["arms_crossed"] = (0.0, {})

    best = max(scores.items(), key=lambda kv: kv[1][0])
    name, (conf, evidence) = best
    if conf < CONFIDENCE_FLOOR:
        return {
            "action": "unknown",
            "confidence": 0.0,
            "evidence": {},
            "scores": {k: round(v[0], 2) for k, v in scores.items()},
        }
    return {
        "action": name,
        "confidence": round(conf, 2),
        "evidence": evidence,
        "scores": {k: round(v[0], 2) for k, v in scores.items()},
    }


def action_definitions() -> list[dict[str, str]]:
    """Human-readable list of what each action means. Used by the UI
    'what can this detect?' panel and by video.actions_known capability."""
    return [
        {"name": "standing", "definition": "Upright posture, little motion. Hips above knees above ankles."},
        {"name": "sitting", "definition": "Hips at knee height, or knee bent sharply."},
        {"name": "walking", "definition": "Upright + moderate forward motion (20-150 px/s)."},
        {"name": "running", "definition": "Upright + high forward motion (>150 px/s)."},
        {"name": "waving", "definition": "One or both wrists above shoulders with lateral motion."},
        {"name": "kicking", "definition": "One ankle raised above hip height."},
        {"name": "jumping", "definition": "Rapid upward motion of the hip (vertical rise)."},
        {"name": "hands_up", "definition": "Both wrists above the head, stationary."},
        {"name": "arms_crossed", "definition": "Each wrist on the opposite side of the body from its shoulder."},
        {"name": "bending", "definition": "Torso bent forward: horizontal shoulder-hip offset exceeds vertical."},
        {"name": "falling", "definition": "Rapid downward motion with hip below knee (collapsed)."},
        {"name": "pointing", "definition": "One arm extended straight, the other at rest."},
        {"name": "head_down", "definition": "Nose dropped below shoulder line (looking down, reading, dozing)."},
        {"name": "leaning_back", "definition": "Shoulders behind hips horizontally (reclined posture)."},
        {"name": "typing", "definition": "Both wrists close together at waist height with bent elbows (keyboard posture)."},
        {"name": "resting", "definition": "Upper body visible, arms down, head upright, no gesture."},
    ]
