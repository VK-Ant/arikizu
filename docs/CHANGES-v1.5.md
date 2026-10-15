# Arikizu v1.5

## v1.5.14 (browser webcam + vision backend fix)

Three real changes:

1. **Browser webcam support.** Added a "Use webcam" button to the
   vision view. The browser (Chrome/Edge on Windows, Safari on Mac,
   Firefox on Linux) requests camera permission from the user and
   streams frames straight to the server as base64 JPEG. No WSL
   camera passthrough, no v4l2-loopback, no USB-over-IP setup.
   - Click the button, browser asks "Allow camera?", click Allow.
   - Live frames show in canvas with detection boxes drawn over them.
   - Works on any device that has a browser and a camera.
   - Stop button toggles it back off.

2. **Vision worker was missing onnxruntime.** The reason canned
   detections were showing instead of real ones: `onnxruntime` was
   not in `workers/vision_worker/pyproject.toml`. Added it. Now
   `bootstrap.sh` installs it and the vision model actually loads.

3. **vision.detect now accepts base64 image data.** New
   `image_base64` field alongside `image_path`. The worker decodes
   the frame, picks up its dimensions, and scales the canned demo
   boxes to the real frame size so they land on the right place
   whether the frame is 320x240 or 1920x1080.

## v1.5.13 (demos actually work)
## v1.5.12 (local LLM support)
## v1.5.11 (reasoning fallback)
## v1.5.10 (zero CI, prereqs, device framing)
## v1.5.9 .. v1.5 (prior history)
