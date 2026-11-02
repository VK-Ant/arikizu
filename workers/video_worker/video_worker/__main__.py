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


# ADE20K 150-class semantic labels. Covers indoor + outdoor scenes.
# Order is the official ADE20K class index 0..149.
_ADE20K_NAMES = [
    "wall", "building", "sky", "floor", "tree", "ceiling", "road",
    "bed", "windowpane", "grass", "cabinet", "sidewalk", "person",
    "earth", "door", "table", "mountain", "plant", "curtain", "chair",
    "car", "water", "painting", "sofa", "shelf", "house", "sea",
    "mirror", "rug", "field", "armchair", "seat", "fence", "desk",
    "rock", "wardrobe", "lamp", "bathtub", "railing", "cushion",
    "base", "box", "column", "signboard", "chest_of_drawers", "counter",
    "sand", "sink", "skyscraper", "fireplace", "refrigerator",
    "grandstand", "path", "stairs", "runway", "case", "pool_table",
    "pillow", "screen_door", "stairway", "river", "bridge", "bookcase",
    "blind", "coffee_table", "toilet", "flower", "book", "hill",
    "bench", "countertop", "stove", "palm_tree", "kitchen_island",
    "computer", "swivel_chair", "boat", "bar", "arcade_machine",
    "hovel", "bus", "towel", "light", "truck", "tower", "chandelier",
    "awning", "streetlight", "booth", "television", "airplane",
    "dirt_track", "clothes", "pole", "land", "bannister", "escalator",
    "ottoman", "bottle", "buffet", "poster", "stage", "van", "ship",
    "fountain", "conveyer_belt", "canopy", "washer", "plaything",
    "swimming_pool", "stool", "barrel", "basket", "waterfall", "tent",
    "bag", "minibike", "cradle", "oven", "ball", "food", "step",
    "tank", "trade_name", "microwave", "pot", "animal", "bicycle",
    "lake", "dishwasher", "screen", "blanket", "sculpture", "hood",
    "sconce", "vase", "traffic_light", "tray", "ashcan", "fan", "pier",
    "crt_screen", "plate", "monitor", "bulletin_board", "shower",
    "radiator", "glass", "clock", "flag",
]


def _fix_hint_for(backend_tag: str, err: str) -> str:
    """Return a specific fix command for a given error class."""
    err_low = err.lower()
    # Catch system-library errors specifically; they look like
    # "no-mediapipe" at import time but are really a missing .so.
    syslib_markers = ("libgl", "libgl.so", "libgles", "libegl", "libglib",
                      "libsm", "libxext", "libxrender", "libgomp",
                      "shared object", "cannot open shared")
    if any(m in err_low for m in syslib_markers):
        return ("MediaPipe needs system libraries not installed on your box. "
                "Run: scripts/install-video-system-deps.sh "
                "then: pkill -9 -f arikizu && make run")
    if backend_tag == "no-mediapipe":
        return "cd workers && uv add mediapipe --package video-worker && cd .. && pkill -9 -f arikizu && make run"
    if backend_tag == "no-models":
        return "scripts/download-video-models.sh"
    if backend_tag == "missing-system-lib":
        return ("scripts/install-video-system-deps.sh  "
                "(installs libgl1 libglib2.0-0 libsm6 libxext6 libxrender1)")
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
        # Stage 1: MediaPipe import.
        # Note: a libGL-missing error LOOKS like an import failure. Detect
        # it specifically and route to the system-dep install, not a
        # pointless 'uv add mediapipe' retry.
        if perception_mod.MP_OK:
            results["mediapipe_import"]["ok"] = True
            results["mediapipe_import"]["detail"] = "import works"
        else:
            err = perception_mod.MP_IMPORT_ERR
            results["mediapipe_import"]["detail"] = err
            results["overall"] = "FAIL"
            err_low = err.lower()
            syslib_markers = ("libgl", "libgl.so", "libgles", "libegl", "libglib",
                              "libsm", "libxext", "libxrender", "libgomp",
                              "shared object", "cannot open shared")
            if any(m in err_low for m in syslib_markers):
                results["fix"] = (
                    "The Python package IS installed but a system library it needs is missing. "
                    "Run: scripts/install-video-system-deps.sh "
                    "then: pkill -9 -f arikizu && make run"
                )
                results["mediapipe_import"]["detail"] = (
                    f"{err}  <-- this is a system library missing, NOT the Python package"
                )
            else:
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
        # Score an action for EACH person detected, not just person 0.
        per_person_actions: list[dict[str, Any]] = []
        for pose_entry in result.poses:
            lms_tuples = [(x, y, z) for x, y, z in pose_entry["landmarks"]]
            pf = actions.PoseFrame(lms_tuples, pose_entry["visibility"])
            per_person_actions.append({
                "person_id": pose_entry["person_id"],
                **actions.recognize(pf, motion_px_per_s=float(motion_px_per_s or 0)),
            })
        # Legacy single-person action (first person).
        action = {"action": "unknown", "confidence": 0.0, "evidence": {}, "scores": {}}
        if result.pose_landmarks:
            pose = actions.PoseFrame(result.pose_landmarks, result.pose_visibility)
            action = actions.recognize(pose, motion_px_per_s=float(motion_px_per_s or 0))
        return {
            "frame": result.to_jsonable(),
            "action": action,                       # legacy: first person's action
            "actions_per_person": per_person_actions,  # NEW: one entry per person
            "n_people": len(per_person_actions),
            "n_faces": len(result.faces),
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

    @worker.handler("video.segment_at_point")
    def segment_at_point(image_base64: str = "", x: float = 0.5, y: float = 0.5,
                         backend: str = "auto") -> dict[str, Any]:
        """Click-to-segment: given a frame and a normalized (x, y) point in
        [0,1], return a binary mask + bounding box for whatever is under
        that point.

        backend:
          "auto"       - try SegFormer semantic segmentation first (way
                         more reliable for complex indoor scenes), fall
                         back to MediaPipe magic_touch if SegFormer is
                         unavailable. Default.
          "segformer"  - force SegFormer semantic segmentation.
          "magic_touch" - force MediaPipe interactive segmenter.

        SegFormer path: runs scene parse, looks up the semantic class at
        the click point, returns just that class's mask. If the user
        clicked on a person, this returns the person region, not the
        whole image.

        Returns {mask_png_base64, bbox, point_x, point_y, class_name,
                 backend, ms}.
        """
        import base64 as _b64
        import io as _io
        import time

        if not image_base64:
            return {"error": "image_base64 required"}

        # -------------------------------------------------------------
        # SegFormer path (default): semantic segmentation gives reliable
        # person/wall/door/etc classes. Click point -> majority class in
        # a 5x5 window -> return just that class's mask.
        # -------------------------------------------------------------
        if backend in ("auto", "segformer", "combined"):
            try:
                import numpy as np
                from PIL import Image
                import onnxruntime as ort

                sf_model = models.ensure("segformer_b0_int8")
                raw = _b64.b64decode(image_base64)
                pil = Image.open(_io.BytesIO(raw)).convert("RGB")
                orig_w, orig_h = pil.size
                img = pil.resize((512, 512), Image.BILINEAR)
                arr = np.asarray(img, dtype=np.float32) / 255.0
                mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
                std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
                arr = ((arr - mean) / std).transpose(2, 0, 1)[None, :, :, :]

                available = set(ort.get_available_providers())
                preference = ["TensorrtExecutionProvider", "CUDAExecutionProvider",
                              "CoreMLExecutionProvider", "OpenVINOExecutionProvider",
                              "CPUExecutionProvider"]
                providers = [p for p in preference if p in available] or ["CPUExecutionProvider"]

                t = time.perf_counter()
                sess = ort.InferenceSession(str(sf_model), providers=providers)
                in_name = sess.get_inputs()[0].name
                logits = sess.run(None, {in_name: arr})[0]
                cls_map = np.argmax(logits[0], axis=0).astype(np.int32)

                cls_pil = Image.fromarray(cls_map.astype(np.uint8), mode="L")
                cls_pil = cls_pil.resize((orig_w, orig_h), Image.NEAREST)
                cls_full = np.asarray(cls_pil)

                # Majority vote in 5x5 window around click.
                px = max(0, min(orig_w - 1, int(round(float(x) * orig_w))))
                py = max(0, min(orig_h - 1, int(round(float(y) * orig_h))))
                y_lo, y_hi = max(0, py - 2), min(orig_h, py + 3)
                x_lo, x_hi = max(0, px - 2), min(orig_w, px + 3)
                neigh = cls_full[y_lo:y_hi, x_lo:x_hi].flatten()
                uniq_n, cnt_n = np.unique(neigh, return_counts=True)
                clicked_class = int(uniq_n[int(np.argmax(cnt_n))])

                mask = (cls_full == clicked_class).astype(np.uint8) * 255
                ys, xs = np.where(mask > 0)
                if len(xs) == 0:
                    return {"error": "no object at that point",
                            "backend": "segformer", "class_name": "unknown"}

                # Try MediaPipe magic_touch to REFINE the edges, if available.
                # magic_touch gives tighter boundaries; SegFormer gives the
                # right class. Combine: keep magic_touch's result only
                # where it falls INSIDE SegFormer's class region, so we get
                # fine edges but still only the clicked object.
                refined = False
                active_backend = "segformer"
                if backend in ("auto", "combined") and perception_mod.MP_OK:
                    try:
                        import mediapipe as mp
                        from mediapipe.tasks.python import BaseOptions, vision as mp_vision
                        from mediapipe.tasks.python.components.containers import keypoint as kp_mod

                        mt_model_path = models.ensure("magic_touch")
                        mt_opts = mp_vision.InteractiveSegmenterOptions(
                            base_options=BaseOptions(model_asset_path=str(mt_model_path),
                                                     delegate=BaseOptions.Delegate.CPU),
                            output_category_mask=True,
                        )
                        rgb_arr = np.asarray(pil)
                        mt_mask = None
                        with mp_vision.InteractiveSegmenter.create_from_options(mt_opts) as segmenter:
                            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_arr)
                            roi = mp_vision.InteractiveSegmenterRegionOfInterest(
                                format=mp_vision.InteractiveSegmenterRegionOfInterest.Format.KEYPOINT,
                                keypoint=kp_mod.NormalizedKeypoint(x=float(x), y=float(y)),
                            )
                            seg_result = segmenter.segment(mp_img, roi)
                        mt_raw = seg_result.category_mask.numpy_view()
                        if mt_raw.ndim == 3:
                            mt_raw = mt_raw.squeeze(
                                axis=-1 if mt_raw.shape[-1] == 1 else 0)
                        # Sample the clicked class in the magic_touch mask too
                        mt_clicked = int(mt_raw[py, px])
                        mt_mask = (mt_raw == mt_clicked).astype(np.uint8) * 255

                        # Guard against magic_touch returning garbage (near-whole
                        # image). If so, skip the refinement.
                        mt_frac = int(mt_mask.sum() // 255) / float(orig_w * orig_h)
                        if 0.0 < mt_frac < 0.80:
                            # Intersect: tighter edges, but ONLY inside the
                            # SegFormer class region. This is the "combined"
                            # mask VK asked for.
                            combined = ((mt_mask > 0) & (mask > 0)).astype(np.uint8) * 255
                            # Only accept if the combined mask retains a
                            # reasonable portion of the semantic mask.
                            semantic_px = int(mask.sum() // 255)
                            combined_px = int(combined.sum() // 255)
                            if semantic_px > 0 and combined_px / float(semantic_px) > 0.25:
                                mask = combined
                                refined = True
                                active_backend = "combined"
                    except Exception:
                        # Refinement is best-effort; keep the SegFormer mask.
                        pass

                # Recompute bbox from the (possibly refined) mask.
                ys, xs = np.where(mask > 0)
                if len(xs) == 0:
                    return {"error": "no object after refinement",
                            "backend": active_backend, "class_name": "unknown"}
                x0_px, y0_px = int(xs.min()), int(ys.min())
                x1_px, y1_px = int(xs.max()), int(ys.max())
                bbox = [x0_px / orig_w, y0_px / orig_h,
                        x1_px / orig_w, y1_px / orig_h]

                # Full-frame mask PNG (for canvas overlay).
                buf_full = _io.BytesIO()
                Image.fromarray(mask, mode="L").save(buf_full, format="PNG")
                mask_b64 = _b64.b64encode(buf_full.getvalue()).decode("ascii")

                # ---- Cropped RGBA PNG: the segmented part ONLY, cut to
                # bbox with transparent background. This is what VK wants
                # to download: a tight PNG that is just the person / wall /
                # door, no extra pixels around it. ----
                pad = 4
                cx0 = max(0, x0_px - pad)
                cy0 = max(0, y0_px - pad)
                cx1 = min(orig_w, x1_px + 1 + pad)
                cy1 = min(orig_h, y1_px + 1 + pad)
                rgb_full = np.asarray(pil)
                crop_rgb = rgb_full[cy0:cy1, cx0:cx1]
                crop_alpha = mask[cy0:cy1, cx0:cx1]
                rgba = np.dstack([crop_rgb, crop_alpha])
                buf_crop = _io.BytesIO()
                Image.fromarray(rgba, mode="RGBA").save(buf_crop, format="PNG", optimize=True)
                crop_b64 = _b64.b64encode(buf_crop.getvalue()).decode("ascii")

                ms = round((time.perf_counter() - t) * 1000, 1)
                pixel_count = int((mask > 0).sum())
                class_name = (_ADE20K_NAMES[clicked_class]
                              if 0 <= clicked_class < len(_ADE20K_NAMES)
                              else f"class_{clicked_class}")
                return {
                    "mask_png_base64": mask_b64,
                    "crop_png_base64": crop_b64,
                    "crop_width": cx1 - cx0,
                    "crop_height": cy1 - cy0,
                    "crop_bbox_px": [cx0, cy0, cx1, cy1],
                    "bbox": bbox,
                    "point_x": float(x), "point_y": float(y),
                    "mask_pixel_count": pixel_count,
                    "mask_fill_fraction": round(pixel_count / float(orig_w * orig_h), 3),
                    "class_name": class_name,
                    "class_id": clicked_class,
                    "backend": active_backend,
                    "refined_by_magic_touch": refined,
                    "provider": sess.get_providers()[0] if sess.get_providers() else "unknown",
                    "ms": ms,
                }
            except Exception as e:
                if backend in ("segformer", "combined"):
                    return {"error": f"segmentation failed: {e}",
                            "backend": "inference-failed"}
                # auto: fall through to magic_touch
                logger_fallback = e

        # -------------------------------------------------------------
        # MediaPipe magic_touch fallback (only when SegFormer unavailable)
        # -------------------------------------------------------------
        try:
            rgb, _raw = _b64_to_rgb_np(image_base64)
        except Exception as e:
            return {"error": f"decode failed: {e}"}
        if not perception_mod.MP_OK:
            return {"error": "MediaPipe not installed", "backend": "no-mediapipe"}

        try:
            import numpy as np
            from PIL import Image
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions, vision as mp_vision
            from mediapipe.tasks.python.components.containers import keypoint as kp_mod

            model_path = models.ensure("magic_touch")
            segmenter_opts = mp_vision.InteractiveSegmenterOptions(
                base_options=BaseOptions(model_asset_path=str(model_path),
                                         delegate=BaseOptions.Delegate.CPU),
                output_category_mask=True,
            )
        except Exception as e:
            return {"error": f"segmenter not available: {e}", "backend": "init-failed"}

        try:
            t = time.perf_counter()
            with mp_vision.InteractiveSegmenter.create_from_options(segmenter_opts) as segmenter:
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                roi = mp_vision.InteractiveSegmenterRegionOfInterest(
                    format=mp_vision.InteractiveSegmenterRegionOfInterest.Format.KEYPOINT,
                    keypoint=kp_mod.NormalizedKeypoint(x=float(x), y=float(y)),
                )
                seg_result = segmenter.segment(mp_img, roi)
            ms = round((time.perf_counter() - t) * 1000, 1)
            cat_mask = seg_result.category_mask.numpy_view()
            # MediaPipe may return a 2D or 3D array. Squeeze down to 2D.
            if cat_mask.ndim == 3:
                cat_mask = cat_mask.squeeze(axis=-1 if cat_mask.shape[-1] == 1 else 0)

            # Figure out which class is the "object" the user clicked on.
            # We used to just sample cat_mask[click_y, click_x], but that
            # fails whenever the click lands on a boundary pixel or on a
            # thin feature the model classified as background. So:
            #   1. Vote across a 5x5 window around the click
            #   2. If the chosen class covers MOST of the frame it is
            #      almost certainly the background. Flip to the next-smaller
            #      class that has at least 1% of the frame.
            mh, mw = cat_mask.shape[:2]
            total_px = mh * mw
            px = max(0, min(mw - 1, int(round(float(x) * mw))))
            py = max(0, min(mh - 1, int(round(float(y) * mh))))

            # 5x5 majority vote around the click
            y_lo, y_hi = max(0, py - 2), min(mh, py + 3)
            x_lo, x_hi = max(0, px - 2), min(mw, px + 3)
            neigh = cat_mask[y_lo:y_hi, x_lo:x_hi].flatten()
            uniq_n, cnt_n = np.unique(neigh, return_counts=True)
            inside_value = int(uniq_n[int(np.argmax(cnt_n))])

            # Frame-wide class counts
            vals, counts = np.unique(cat_mask, return_counts=True)
            class_counts = {int(v): int(c) for v, c in zip(vals, counts)}
            clicked_frac = class_counts.get(inside_value, 0) / float(total_px)

            # If the clicked class fills more than half the frame, almost
            # always it is the background and the object is the SMALLER
            # class on the other side of the boundary.
            if clicked_frac >= 0.50 and len(vals) >= 2:
                others = [(v, c) for v, c in class_counts.items()
                          if v != inside_value and c >= total_px * 0.01]
                if others:
                    others.sort(key=lambda vc: vc[1])  # smallest first
                    inside_value = others[0][0]

            inside = (cat_mask == inside_value).astype(np.uint8) * 255
            # Final guard against runaway masks: if even the chosen class
            # still fills >85 % of the frame, return empty with a clear flag.
            if int(inside.sum() // 255) > total_px * 0.85:
                inside = np.zeros_like(inside)

            # Compute bbox of the mask
            ys, xs = np.where(inside > 0)
            if len(xs) == 0:
                bbox = None
                h, w = inside.shape[:2]
            else:
                h, w = inside.shape[:2]
                bbox = [float(xs.min() / w), float(ys.min() / h),
                        float(xs.max() / w), float(ys.max() / h)]
            # Encode mask as PNG
            buf = _io.BytesIO()
            Image.fromarray(inside, mode="L").save(buf, format="PNG")
            mask_b64 = _b64.b64encode(buf.getvalue()).decode("ascii")
            pixel_count = int((inside > 0).sum())
            # Cropped RGBA PNG for download
            crop_b64 = None
            crop_w_px = 0
            crop_h_px = 0
            crop_box = None
            if bbox is not None and pixel_count > 0:
                pad = 4
                h_full, w_full = inside.shape[:2]
                cx0 = max(0, int(xs.min()) - pad)
                cy0 = max(0, int(ys.min()) - pad)
                cx1 = min(w_full, int(xs.max()) + 1 + pad)
                cy1 = min(h_full, int(ys.max()) + 1 + pad)
                crop_rgb = rgb[cy0:cy1, cx0:cx1]
                crop_alpha = inside[cy0:cy1, cx0:cx1]
                rgba = np.dstack([crop_rgb, crop_alpha])
                buf_crop = _io.BytesIO()
                Image.fromarray(rgba, mode="RGBA").save(buf_crop, format="PNG", optimize=True)
                crop_b64 = _b64.b64encode(buf_crop.getvalue()).decode("ascii")
                crop_w_px = cx1 - cx0
                crop_h_px = cy1 - cy0
                crop_box = [cx0, cy0, cx1, cy1]
            return {
                "mask_png_base64": mask_b64,
                "crop_png_base64": crop_b64,
                "crop_width": crop_w_px,
                "crop_height": crop_h_px,
                "crop_bbox_px": crop_box,
                "bbox": bbox,
                "point_x": float(x), "point_y": float(y),
                "mask_pixel_count": pixel_count,
                "mask_fill_fraction": round(pixel_count / float(mh * mw), 3),
                "clicked_category": int(inside_value),
                "class_name": f"magic_touch_class_{int(inside_value)}",
                "backend": "magic_touch",
                "ms": ms,
            }
        except Exception as e:
            return {"error": f"segmentation failed: {e}", "backend": "inference-failed"}

    @worker.handler("video.scene_parse")
    def scene_parse(image_base64: str = "", top_k: int = 10) -> dict[str, Any]:
        """Semantic scene segmentation with SegFormer-B0 (512x512, ADE20K
        150 classes). Covers both indoor (wall, floor, chair, bed, sofa,
        table, lamp, window, door, ceiling, person, ...) and outdoor
        (sky, road, building, tree, grass, car, sidewalk, mountain, water,
        field, ...) scenes.

        Returns per-class mask summary: {class_name, pixel_count, bbox,
        fill_fraction}. Top-K classes by pixel count are returned.
        """
        import base64 as _b64
        import io as _io
        import time
        if not image_base64:
            return {"error": "image_base64 required"}
        try:
            import numpy as np
            from PIL import Image
            import onnxruntime as ort
        except ImportError as e:
            return {"error": f"onnxruntime or PIL missing: {e}", "backend": "no-onnx",
                    "fix_hint": "pip install onnxruntime pillow"}

        try:
            model_path = models.ensure("segformer_b0_int8")
        except Exception as e:
            return {"error": f"segformer model not available: {e}", "backend": "no-model",
                    "fix_hint": "scripts/download-video-models.sh or ensure segformer_b0_ade20k_512_int8.onnx is in models/"}

        try:
            t = time.perf_counter()
            raw = _b64.b64decode(image_base64)
            pil = Image.open(_io.BytesIO(raw)).convert("RGB")
            orig_w, orig_h = pil.size
            img = pil.resize((512, 512), Image.BILINEAR)
            arr = np.asarray(img, dtype=np.float32) / 255.0
            # ImageNet normalization
            mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
            arr = (arr - mean) / std
            # NCHW
            arr = arr.transpose(2, 0, 1)[None, :, :, :]

            # Pick the best provider that's actually available on this box.
            # Jetson -> TensorRT or CUDA; Mac -> CoreML; Pi/x86 -> CPU.
            available = set(ort.get_available_providers())
            preference = [
                "TensorrtExecutionProvider",
                "CUDAExecutionProvider",
                "CoreMLExecutionProvider",
                "OpenVINOExecutionProvider",
                "CPUExecutionProvider",
            ]
            providers = [p for p in preference if p in available] or ["CPUExecutionProvider"]
            sess = ort.InferenceSession(str(model_path), providers=providers)
            in_name = sess.get_inputs()[0].name
            logits = sess.run(None, {in_name: arr})[0]   # (1, 150, H', W')
            cls_map = np.argmax(logits[0], axis=0).astype(np.int32)   # (H', W')

            # Upsample to input resolution via nearest neighbor
            cls_pil = Image.fromarray(cls_map.astype(np.uint8), mode="L")
            cls_pil = cls_pil.resize((orig_w, orig_h), Image.NEAREST)
            cls_full = np.asarray(cls_pil)

            total_px = orig_w * orig_h
            vals, counts = np.unique(cls_full, return_counts=True)
            pairs = sorted(zip(vals.tolist(), counts.tolist()), key=lambda vc: -vc[1])
            top = pairs[: max(1, int(top_k))]

            classes_out = []
            for v, c in top:
                mask = (cls_full == v)
                ys, xs = np.where(mask)
                if len(xs) == 0:
                    continue
                bbox = [float(xs.min() / orig_w), float(ys.min() / orig_h),
                        float(xs.max() / orig_w), float(ys.max() / orig_h)]
                # Encode this class's mask as a tiny PNG for the UI to overlay
                m8 = (mask.astype(np.uint8)) * 255
                buf = _io.BytesIO()
                Image.fromarray(m8, mode="L").save(buf, format="PNG", optimize=True)
                mask_b64 = _b64.b64encode(buf.getvalue()).decode("ascii")
                classes_out.append({
                    "class_id": int(v),
                    "class_name": _ADE20K_NAMES[v] if 0 <= v < len(_ADE20K_NAMES) else f"class_{v}",
                    "pixel_count": int(c),
                    "fill_fraction": round(c / float(total_px), 3),
                    "bbox": bbox,
                    "mask_png_base64": mask_b64,
                })
            ms = round((time.perf_counter() - t) * 1000, 1)
            # Report the actual provider used (first in the session's list)
            used_provider = sess.get_providers()[0] if sess.get_providers() else "unknown"
            return {
                "classes": classes_out,
                "image_width": orig_w, "image_height": orig_h,
                "model": "segformer_b0_ade20k_512_int8",
                "backend": "onnx",
                "provider": used_provider,
                "ms": ms,
            }
        except Exception as e:
            return {"error": f"scene_parse failed: {e}", "backend": "inference-failed"}

    @worker.handler("video.save_segment")
    def save_segment(name: str = "", image_base64: str = "", mask_png_base64: str = "",
                     bbox: list | None = None, note: str = "") -> dict[str, Any]:
        """Store a segment (frame + mask + bbox) to disk so the user can
        download or re-use it later. Returns the saved path."""
        import base64 as _b64
        import time
        from pathlib import Path
        if not image_base64 or not mask_png_base64:
            return {"error": "image_base64 and mask_png_base64 required"}
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (name or "segment"))[:40]
        ts = int(time.time())
        root = models._find_project_root()
        out_dir = root / "data" / "segments" / f"{ts}-{safe_name}"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            (out_dir / "frame.jpg").write_bytes(_b64.b64decode(image_base64))
            (out_dir / "mask.png").write_bytes(_b64.b64decode(mask_png_base64))
            meta = {
                "name": name, "note": note, "bbox": bbox,
                "saved_at": ts, "frame": "frame.jpg", "mask": "mask.png",
            }
            import json
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
        except Exception as e:
            return {"error": f"save failed: {e}"}
        return {
            "saved_dir": str(out_dir),
            "files": ["frame.jpg", "mask.png", "meta.json"],
            "name": name,
        }

    @worker.handler("video.list_segments")
    def list_segments(limit: int = 50) -> dict[str, Any]:
        """List saved segments (newest first)."""
        from pathlib import Path
        root = models._find_project_root()
        seg_dir = root / "data" / "segments"
        if not seg_dir.exists():
            return {"segments": []}
        entries = sorted(seg_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:int(limit)]
        import json
        out = []
        for d in entries:
            if not d.is_dir():
                continue
            meta_path = d / "meta.json"
            if meta_path.exists():
                try:
                    out.append({"dir": d.name, **json.loads(meta_path.read_text())})
                except Exception:
                    out.append({"dir": d.name})
            else:
                out.append({"dir": d.name})
        return {"segments": out}

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
