"""Example custom action: squatting.

Hip below knee height + knees bent sharply + feet planted (ankles below
knees). Not quite sitting (sitting has horizontal thighs; squatting has
vertical thighs).

To integrate, add this function to video_worker/actions.py, then:

    scores["squatting"] = is_squatting(pose)
    ACTIONS_KNOWN.append("squatting")
"""
from __future__ import annotations


def is_squatting(pose) -> tuple[float, dict]:
    """pose is a video_worker.actions.PoseFrame instance."""
    from video_worker.actions import (
        L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE, _angle
    )
    if not pose.ok(L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE):
        return 0.0, {}
    hip_y = (pose.xy(L_HIP)[1] + pose.xy(R_HIP)[1]) / 2
    knee_y = (pose.xy(L_KNEE)[1] + pose.xy(R_KNEE)[1]) / 2
    ankle_y = (pose.xy(L_ANKLE)[1] + pose.xy(R_ANKLE)[1]) / 2
    # Hip near knee height (crouched) AND ankles below knees (feet planted).
    if abs(hip_y - knee_y) > 0.15:
        return 0.0, {}
    if ankle_y <= knee_y:
        return 0.0, {}
    # Knee bent sharply.
    left_knee_angle = _angle(pose.xy(L_HIP), pose.xy(L_KNEE), pose.xy(L_ANKLE))
    if left_knee_angle > 110:
        return 0.0, {}
    return 0.75, {"left_knee_angle": left_knee_angle,
                  "hip_knee_gap": abs(hip_y - knee_y)}
