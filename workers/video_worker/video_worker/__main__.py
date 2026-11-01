"""Arikizu video intelligence worker. Entry point.

Capabilities exposed:

- video.device_report:  device profile + recommended model preset + fit table
- video.actions_known:  list of rule-based action rules the recognizer knows
- video.live_detect:    one frame (base64) -> detections + pose + action label
- video.live_describe:  one frame + optional text prompt -> VLM score
- video.describe_image: one frame -> open-ended VLM description
- video.search_image:   reference image -> search query phrase for a video
- video.recognize_pose: pose landmarks + motion vector -> action label (pure, no model)
- video.history:        recent analyses from SQLite
- video.history_get:    one analysis detail
- video.backends:       which Python deps, which model files, which backends are up
- video.analyze:        full video pipeline (upload path on the HTTP side)
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
from typing import Any

from arikizu_worker import Worker

from . import actions, devices, history, models, perception as perception_mod, vlm


def _b64_to_rgb_np(image_base64: str):
    """Decode a base64 JPEG/PNG into an RGB uint8 numpy array."""
    import numpy as np
    from PIL import Image
    data = base64.b64decode(image_base64)
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return np.array(img), data


def _fix_hint_for(backend_tag: str, err: str) -> str:
    """Return a specific fix command for a given error class."""
    if backend_tag == "no-mediapipe":
        return "cd workers && uv add mediapipe --package video-worker && cd .. && pkill -9 -f arikizu && make run"
    if backend_tag == "no-models":
        return "scripts/download-video-models.sh"
    if backend_tag == "missing-system-lib":
        return "sudo apt install -y libgl1 libglib2.0-0 ; then: pkill -9 -f arikizu && make run"
    return "check video_worker logs; call /api/v1/call/video/backends for diagnostic"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("video")

    # Device detection runs once at startup. The worker tells the UI
    # which preset to show.
    profile = devices.detect()
    preset = devices.preset_for(profile.device_class)
    logger.info(
        "video worker starting on %s (%s, %.1f GB RAM); preset = %s",
        profile.device_class, profile.arch, profile.ram_gb, preset,
    )

    # Perception is lazy-init: we only load MediaPipe on first use so a
    # worker that is never asked for live detection does not pay for it.
    _perception: perception_mod.MediaPipePerception | None = None

    def _get_perception():
        nonlocal _perception
        if _perception is not None:
            return _perception
        _perception = perception_mod.MediaPipePerception(
            detector_key=preset["detector"],
            pose_key=preset["pose"],
            want_face=True,
        )
        return _perception

    worker = Worker("video")

    # -----------------------------------------------------------------------
    # Device + diagnostics
    # -----------------------------------------------------------------------

    @worker.handler("video.device_report")
    def device_report() -> dict[str, Any]:
        """Device profile + recommended preset + per-model fit table."""
        return devices.report()

    @worker.handler("video.selftest")
    def selftest() -> dict[str, Any]:
        """Actually run the perception stack against a 640x480 synthetic
        image and report per-stage pass/fail with the exact error.
        Call this when the diagnostic says READY but detections don't show."""
        import numpy as np
        results: dict[str, Any] = {
            "mediapipe_import": {"ok": False, "detail": ""},
            "models_present": {"ok": False, "detail": "", "missing": []},
            "perception_init": {"ok": False, "detail": ""},
            "inference_runs": {"ok": False, "detail": "", "ms": None},
        }
        # Stage 1: MediaPipe import
        if perception_mod.MP_OK:
            results["mediapipe_import"]["ok"] = True
            results["mediapipe_import"]["detail"] = "import works"
        else:
            results["mediapipe_import"]["detail"] = perception_mod.MP_IMPORT_ERR
            results["overall"] = "FAIL"
            results["fix"] = "cd workers && uv add mediapipe --package video-worker ; pkill -9 -f arikizu && make run"
            return results
        # Stage 2: model files present
        required_keys = [preset["detector"], preset["pose"], "blaze_face"]
        missing = [k for k in required_keys if not models.is_present(k)]
        if not missing:
            results["models_present"]["ok"] = True
            results["models_present"]["detail"] = "all required model files present"
        else:
            results["models_present"]["detail"] = f"missing: {', '.join(missing)}"
            results["models_present"]["missing"] = missing
            results["overall"] = "FAIL"
            results["fix"] = "scripts/download-video-models.sh"
            return results
        # Stage 3: perception init
        try:
            per = _get_perception()
            results["perception_init"]["ok"] = True
            results["perception_init"]["detail"] = f"delegate={perception_mod.MP_DELEGATE}"
        except Exception as e:
            results["perception_init"]["detail"] = str(e)
            results["overall"] = "FAIL"
            results["fix"] = _fix_hint_for("init-failed", str(e))
            return results
        # Stage 4: run inference on a synthetic 640x480 image
        try:
            import time
            fake_rgb = np.full((480, 640, 3), 128, dtype=np.uint8)
            # Draw a dark rectangle so the detector has SOMETHING to look at
            fake_rgb[150:350, 220:420] = 60
            t = time.perf_counter()
            frame_result = per.process(fake_rgb)
            ms = round((time.perf_counter() - t) * 1000, 1)
            results["inference_runs"]["ok"] = True
            results["inference_runs"]["detail"] = (
                f"inference completed in {ms} ms; "
                f"detections={len(frame_result.detections)}, "
                f"pose_landmarks={len(frame_result.pose_landmarks)}, "
                f"faces={len(frame_result.faces)}"
            )
            results["inference_runs"]["ms"] = ms
            results["overall"] = "PASS"
        except Exception as e:
            results["inference_runs"]["detail"] = f"inference failed: {e}"
            results["overall"] = "FAIL"
            results["fix"] = _fix_hint_for("inference-failed", str(e))
        return results

    @worker.handler("video.backends")
    def backends() -> dict[str, Any]:
        """Which Python deps, which model files, which VLM backends are up.
        The demo hub Diagnostics panel calls this on page load."""
        return {
            "device": devices.detect().__dict__,
            "preset": preset,
            "models": models.status(),
            "perception": perception_mod.available(),
            "perception_initialized": _perception is not None,
            "vlm": vlm.backend_available(),
        }

    # -----------------------------------------------------------------------
    # Action recognition
    # -----------------------------------------------------------------------

    @worker.handler("video.actions_known")
    def actions_known() -> dict[str, Any]:
        """Which rule-based actions this worker can label."""
        return {
            "count": len(actions.ACTIONS_KNOWN),
            "names": actions.ACTIONS_KNOWN,
            "definitions": actions.action_definitions(),
            "confidence_floor": actions.CONFIDENCE_FLOOR,
        }

    @worker.handler("video.recognize_pose")
    def recognize_pose(landmarks: list | None = None,
                       visibility: list | None = None,
                       motion_px_per_s: float = 0.0,
                       wrist_motion: list | None = None,
                       ankle_motion: list | None = None,
                       hip_dy: float = 0.0) -> dict[str, Any]:
        """Pure action recognition from pose landmarks only. No model loaded.
        The browser can call this with landmarks produced by MediaPipe JS or
        by video.live_detect, and get an action label back in under 1 ms.
        """
        if not landmarks or len(landmarks) < 33:
            return {"action": "unknown", "confidence": 0.0, "evidence": {},
                    "note": "need 33 landmarks"}
        tuples = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)
                  for p in landmarks]
        pose = actions.PoseFrame(tuples, visibility)
        wm = tuple(wrist_motion) if wrist_motion and len(wrist_motion) == 4 else None
        am = tuple(ankle_motion) if ankle_motion and len(ankle_motion) == 2 else None
        return actions.recognize(
            pose, motion_px_per_s=float(motion_px_per_s or 0),
            wrist_motion=wm, ankle_motion=am, hip_dy=float(hip_dy or 0),
        )

    # -----------------------------------------------------------------------
    # Live detection: one frame in, perception + action out
    # -----------------------------------------------------------------------

    @worker.handler("video.live_detect")
    def live_detect(image_base64: str = "", motion_px_per_s: float = 0.0) -> dict[str, Any]:
        """One frame -> detections + pose + action label. The webcam view
        calls this at the device's recommended FPS (device_report tells it)."""
        if not image_base64:
            return {"error": "image_base64 required"}
        try:
            rgb, _ = _b64_to_rgb_np(image_base64)
        except Exception as e:
            return {"error": f"could not decode image: {e}"}
        try:
            per = _get_perception()
        except Exception as e:
            # Figure out which specific failure this is. Giving the user
            # "no-mediapipe" when the real problem is a missing model file
            # or a system-lib issue sends them chasing the wrong fix.
            backend_tag = "init-failed"
            err_str = str(e)
            if "mediapipe" in err_str.lower() and ("not installed" in err_str.lower()
                                                   or "no module" in err_str.lower()):
                backend_tag = "no-mediapipe"
            elif "download" in err_str.lower() or "could not" in err_str.lower():
                backend_tag = "no-models"
            elif "libgl" in err_str.lower() or "shared" in err_str.lower():
                backend_tag = "missing-system-lib"
            return {
                "frame": per_result_to_dict_empty(rgb.shape[1], rgb.shape[0]),
                "action": {"action": "unknown", "confidence": 0.0, "evidence": {}},
                "note": err_str,
                "backend": backend_tag,
                "fix_hint": _fix_hint_for(backend_tag, err_str),
            }
        try:
            result = per.process(rgb)
        except Exception as e:
            return {
                "frame": per_result_to_dict_empty(rgb.shape[1], rgb.shape[0]),
                "action": {"action": "unknown", "confidence": 0.0, "evidence": {}},
                "note": f"inference failed: {e}",
                "backend": "inference-failed",
                "fix_hint": "Check video_worker logs. Common cause: GPU delegate requested on a system without GPU support; set MP_DELEGATE=cpu and restart.",
            }
        # Pose -> action
        action = {"action": "unknown", "confidence": 0.0, "evidence": {}, "scores": {}}
        if result.pose_landmarks:
            pose = actions.PoseFrame(result.pose_landmarks, result.pose_visibility)
            action = actions.recognize(pose, motion_px_per_s=float(motion_px_per_s or 0))
        return {
            "frame": result.to_jsonable(),
            "action": action,
            "backend": "mediapipe",
        }

    def per_result_to_dict_empty(w: int, h: int) -> dict:
        return {
            "detections": [], "pose_landmarks": [], "pose_visibility": [],
            "faces": [], "ms": {}, "width": w, "height": h,
        }

    # -----------------------------------------------------------------------
    # VLM: multimodal action search
    # -----------------------------------------------------------------------

    @worker.handler("video.live_describe")
    def live_describe(image_base64: str = "", prompt: str = "") -> dict[str, Any]:
        """One frame + optional prompt -> VLM output.

        If prompt is empty, returns an open-ended description.
        If prompt is non-empty, scores the frame for that specific action.
        """
        if not image_base64:
            return {"error": "image_base64 required"}
        try:
            data = base64.b64decode(image_base64)
        except Exception as e:
            return {"error": f"base64 decode failed: {e}"}
        if prompt:
            return vlm.score_action(prompt, data)
        return vlm.describe_frame(data)

    @worker.handler("video.describe_image")
    def describe_image(image_base64: str = "") -> dict[str, Any]:
        """Standalone image description (no video context)."""
        if not image_base64:
            return {"error": "image_base64 required"}
        try:
            data = base64.b64decode(image_base64)
        except Exception as e:
            return {"error": f"base64 decode failed: {e}"}
        return vlm.describe_frame(data)

    @worker.handler("video.search_image")
    def search_image(image_base64: str = "") -> dict[str, Any]:
        """Reference-image action search: turn an action image into a text
        search query that video.analyze can use."""
        if not image_base64:
            return {"error": "image_base64 required"}
        try:
            data = base64.b64decode(image_base64)
        except Exception as e:
            return {"error": f"base64 decode failed: {e}"}
        return vlm.describe_reference_image(data)

    # -----------------------------------------------------------------------
    # History
    # -----------------------------------------------------------------------

    @worker.handler("video.history")
    def history_list(limit: int = 20) -> dict[str, Any]:
        return {"rows": history.recent(limit=max(1, min(100, int(limit))))}

    @worker.handler("video.history_get")
    def history_get(event_id: int = 0) -> dict[str, Any]:
        row = history.get(int(event_id))
        if row is None:
            return {"error": f"no analysis with id={event_id}"}
        return row

    # -----------------------------------------------------------------------
    # Full video analysis (upload path).
    # Signature: image_base64 of ONE sample frame, prompt, duration_s hint,
    # frames_per_s hint, device_preset override. The caller (browser) is the
    # one that samples the video frames and sends them one-by-one on this
    # endpoint, so the worker never has to decode large video blobs itself.
    # -----------------------------------------------------------------------

    @worker.handler("video.analyze_frame")
    def analyze_frame(image_base64: str = "", prompt: str = "",
                      time_s: float = 0.0, motion_px_per_s: float = 0.0) -> dict[str, Any]:
        """Analyze one sampled frame of a longer video. Returns everything
        we found for that frame. The browser aggregates across frames and
        posts the summary to video.record_analysis when done."""
        if not image_base64:
            return {"error": "image_base64 required"}
        try:
            rgb, raw = _b64_to_rgb_np(image_base64)
        except Exception as e:
            return {"error": f"decode failed: {e}"}
        out = {"time_s": float(time_s), "backend": "mediapipe"}
        try:
            per = _get_perception()
            r = per.process(rgb)
            out["frame"] = r.to_jsonable()
            if r.pose_landmarks:
                pose = actions.PoseFrame(r.pose_landmarks, r.pose_visibility)
                out["action_rule"] = actions.recognize(pose, motion_px_per_s=motion_px_per_s)
            else:
                out["action_rule"] = {"action": "unknown", "confidence": 0.0, "evidence": {}}
        except Exception as e:
            out["backend"] = "no-mediapipe"
            out["note"] = str(e)
            out["frame"] = per_result_to_dict_empty(rgb.shape[1], rgb.shape[0])
            out["action_rule"] = {"action": "unknown", "confidence": 0.0, "evidence": {}}
        # Optional VLM pass per frame when a prompt is set
        if prompt and vlm.backend_available()["mode"] != "none":
            out["action_vlm"] = vlm.score_action(prompt, raw)
        return out

    @worker.handler("video.record_analysis")
    def record_analysis(video_name: str = "clip",
                        prompt: str = "",
                        backend: str = "mediapipe",
                        total_frames: int = 0,
                        analyzed_frames: int = 0,
                        duration_s: float = 0.0,
                        events: list | None = None,
                        subjects: list | None = None,
                        scene: dict | None = None,
                        motion_analysis: dict | None = None) -> dict[str, Any]:
        """Browser calls this after a video analysis is complete to persist
        the summary. SQLite stores metadata only; no frame images are kept."""
        row_id = history.record(
            video_name=video_name, prompt=prompt, backend=backend,
            total_frames=int(total_frames), analyzed_frames=int(analyzed_frames),
            duration_s=float(duration_s),
            events=events or [], subjects=subjects or [],
            scene=scene, motion_analysis=motion_analysis,
        )
        return {"id": row_id, "stored": True}

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
