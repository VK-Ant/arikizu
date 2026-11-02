# Demos and Tutorials

How to use the browser demos (vision, audio, documents, time series, video studio), plus the end-to-end Pi vision tutorial and the video studio test checklist.

- [Part 1 — Demo guide](#part-1--demo-guide)
- [Part 2 — Pi vision tutorial](#part-2--pi-vision-tutorial)
- [Part 3 — Video studio test checklist](#part-3--video-studio-test-checklist)

---

## Part 1 — Demo guide


Every demo is a plain HTML file served by the Rust server. Nothing to
build, no npm, no bundler. Open `http://127.0.0.1:7000/demo/` for the
hub, click into any view, click one button to see data flow end to end.

Prereq: `make run` is running in one terminal. If you have not done this
yet, see [`../README.md`](../README.md) "Try it in 5 minutes" first.

## Two entry points

- `http://127.0.0.1:7000/`: operator dashboard. Greeting, 6 capability
  cards, recent activity, system status. This is what a non-engineer sees.
- `http://127.0.0.1:7000/demo/`: developer sandbox. One card per
  capability, raw payloads. This is what you use to test or debug.

Both talk to the same `/api/v1/*` surface. Nothing is magic.

---

## 1. Reasoning chat

**URL:** `/demo/reasoning_chat.html`

**What it does:** Chat with the local LLM worker. Three modes.

| Mode        | Payload                                 | Returns                     |
| ----------- | --------------------------------------- | --------------------------- |
| `answer`    | `{question, context, max_tokens}`       | `{answer, model, latency_ms}` |
| `summarize` | `{text, template, max_tokens}`          | `{summary, ...}`             |
| `complete`  | `{prompt, max_tokens}`                  | `{completion, ...}`          |

**How to test:**

1. Pick `answer` from the Mode dropdown.
2. Type: `What is the Rust ownership model in one sentence?`
3. Press Enter.
4. Expected: a one-sentence answer, with model name and latency in the
   footer.

**If a local LLM runtime is not running:** the worker returns a graceful fallback and
the footer shows the error. The chat still works; you just see the
fallback text. Install a local LLM runtime and `ollama pull qwen2.5:0.5b` to get real
answers. On a Pi, point `ARIKIZU_OLLAMA_URL` at a LAN gateway (see
[`SETUP.md`](SETUP.md)).

---

## 2. Vision: live view

**URL:** `/demo/vision_live.html`

**What it does:** Polls the vision worker, draws annotated frames on a
canvas with a bounding box per detection, counts FPS.

**How to test:**

1. Click **Start**. The page polls `/api/v1/call/vision/detect` at ~5 FPS.
2. Expected on a laptop with no camera: fixture frame with pre-labeled
   detections (cat / book / cup).
3. Expected on a Pi with a Camera Module attached: live annotated frames
   from `/dev/video0` with a compact vision model detections.
4. The FPS counter stabilizes after ~2 s.

**Model used:** `models/yolov8n.onnx` (ships from `scripts/download-default-models.sh --tier minimum`).

**Backend:** auto-selected per device. See the device chip on the top
right of the operator dashboard; it names the exact runtime.

---

## 3. Vision: audit search

**URL:** `/demo/vision_search.html`

**What it does:** Queries the audit log for past detections. Every
`vision.detect` call writes a row to SQLite; this view reads them back.

**How to test:**

1. Make a few calls on `/demo/vision_live.html` first (so the audit log
   has rows).
2. Open this view, type `cat` in the search box.
3. Expected: a list of past rows where "cat" appeared in the detections,
   each with a timestamp.

**API call:** `GET /api/v1/audit?kind=vision&limit=50`.

---

## 4. Audio

**URL:** `/demo/audio_view.html`

**What it does:** Loads an audio file, draws its waveform with WebAudio,
marks VAD (voice activity detection) segments, shows the transcript.

**How to test:**

1. Pick a `.wav` or `.mp3` from your laptop.
2. Click **Analyze**.
3. Expected: waveform draws, orange bands mark detected speech regions,
   transcript appears below.

**Capabilities used:** `audio.vad` (a VAD model), `audio.transcribe`
(the ASR model if `--tier standard` was downloaded, otherwise returns a
placeholder transcript).

**Pi note:** the ASR model runs in ~5x real time on a Pi 4; expect a
30-second clip to take ~2-3 minutes. On Jetson Orin Nano with GPU it is
near real time.

---

## 5. Documents

**URL:** `/demo/docs_view.html`

**What it does:** Give it a file path and a JSON schema, it extracts
fields that match. Also runs `docs.search` against a corpus.

**How to test (extract):**

1. The file-path field defaults to `demo/fixtures/sample.txt`.
2. The schema field defaults to:
   ```json
   {
     "date": "string",
     "shift": "string",
     "line": "integer",
     "defects": "array"
   }
   ```
3. Click **Extract**.
4. Expected: a `PASS` tag (or `WAIT` with a placeholder note if DocQWise
   is not yet wired), and a list of extracted fields.

**How to test (search):**

1. Type `defect` in the search box, click **Go**.
2. Expected: top 3 hits from the corpus, each a JSON row.

---

## 6. Time series

**URL:** `/demo/timeseries_view.html`

**What it does:** Plots a univariate time series on a canvas line chart,
overlays a forecast, marks anomalies.

**How to test:**

1. Click **Load fixture**. A ~90-point series loads.
2. Click **Forecast**. The next 20 points are predicted and drawn in
   orange.
3. Click **Detect anomalies**. Red dots mark anomalous points.

**Models used:** classical statistical models (ARIMA, anomaly detection)
from the classical ML libraries. The `--tier full` download swaps the
forecasting model for a deep one; anomaly detection stays classical.

---

## 7. Memory

**URL:** `/demo/memory_view.html`

**What it does:** Session memory. Three operations.

| Operation       | What                                                        |
| --------------- | ----------------------------------------------------------- |
| `memory.update` | Append an item to a session (any JSON object)               |
| `memory.recall` | Fetch top-k items for a session, optionally filtered by text |
| `memory.reward` | Mark one past retrieval as good/bad to steer future recalls |

**How to test:**

1. Keep `session_id: demo-session` as-is.
2. Click **memory.update**. Default item `{"q":"first","ts":1}` is appended.
3. Change the item to `{"q":"second","ts":2}` and click again.
4. Click **memory.recall**. Expected: both items listed, most-recent-first.
5. Type `second` in the query box, click again. Expected: only the second item.
6. Enter any `query_id`, set a score, click **memory.reward**.
   Expected: `{"ok":true,"...":"recorded"}`.

**Backing library:** adaptive-intelligence (RAM only in v0.1; resets on
worker restart).

---

## 8. Guard (PII)

**URL:** `/demo/guard_view.html`

**What it does:** Scans text for PII (emails, phone numbers, SSNs,
addresses), shows the hits side by side with a redacted copy.

**How to test:**

1. Paste any text with an email or phone number into the left pane.
2. Click **Scan**.
3. Expected: left pane highlights each hit in orange; right pane shows
   the redacted version.

**Detectors in v0.1:** regex-based (email, phone, SSN, credit card,
IPv4). Full AntGuard integration is Weekend 10.

---

## 9. Eval

**URL:** `/demo/eval_view.html`

**What it does:** Side-by-side predicted vs expected, with score cards.

**How to test (single scoring):**

1. Default inputs: `the cat sat on the mat` vs `a cat sat on a mat`.
2. Click **Score**.
3. Expected: two score cards. `exact: 0%`, `jaccard: 75%`.
4. Change the predicted text to match the expected exactly. Click again.
   Expected: both 100%.

**How to test (golden set):**

1. Keep the default set name `default`.
2. Click **Run**.
3. Expected: a JSON summary with `pass_count`, `fail_count`, and per-case
   scores.

**Golden sets:** YAML files in `golden/`. Add your own; they appear in
the dropdown next time you reload.

---

## 10. Operator dashboard

**URL:** `/`

**What it does:** The home page a non-engineer sees. Pulls live data
from the same API the demos use; nothing hard-coded.

- **Greeting**: time-of-day aware (Good Morning / Afternoon / Evening / Night)
- **Online chip**: green when `/api/v1/status` responds, red if not
- **Device chip**: shows "Raspberry Pi" / "Jetson" / "Mac" / "Linux" based on `GET /api/v1/status.device.platform`
- **Capability cards**: Vision / Documents / Audio / Reasoning / Analytics / More: each links to the specialized view
- **Recent activity**: `GET /api/v1/audit?limit=5`, newest first
- **System status**: AI Services (worker health), Storage (SQLite + models dir), Network (reachable or not)

Nothing to test here directly; it reflects whatever the rest of the
system is doing. If a worker is down, "AI Services" shows a red dot. If
you make a call on any demo page, it appears in Recent Activity within
~1 second.

---

## Common issues

| Symptom                                           | Fix                                                                        |
| ------------------------------------------------- | -------------------------------------------------------------------------- |
| Page loads but nothing happens on click           | `make run` isn't on, or wrong port. Check terminal 1.                      |
| `Score` returns `WAIT: library not wired`         | Expected. The capability is scaffolded; the real library is a future weekend. |
| Vision shows a fixture frame, no camera           | Expected on a laptop. On a Pi, check `python3 demo/raspberrypi/probe.py`.  |
| Reasoning says "cannot reach a local LLM runtime"              | Install a local LLM runtime and `ollama pull qwen2.5:0.5b`, or point `ARIKIZU_OLLAMA_URL` at a LAN gateway. |
| Recent Activity on `/` stays empty                | Make at least one call on any demo page; the audit log fills from there.  |
| `.local` hostname doesn't resolve on Windows      | Use the Pi's IP from `hostname -I`.                                        |
| Dashboard shows red "Network" dot                 | The worker socket is unreachable. Check `make run` output.                 |

---

## 10. Video Studio: multimodal action search

Three input modes, same pipeline. Runs on your device.

- **No prompt**: 12 default rule-based actions (walking, running,
  sitting, standing, waving, kicking, jumping, hands_up, arms_crossed,
  bending, falling, pointing).
- **Text prompt**: type any action phrase. The VLM scores each sampled
  frame against it. Works for actions outside the default 12.
- **Reference image**: upload a screenshot of the action. The VLM
  describes it internally and uses that description to search the clip.
  This is how new, user-defined actions get found without any training.

**Click-by-click walkthrough:**

1. Open [`/demo/video_studio.html`](http://127.0.0.1:7000/demo/video_studio.html).
2. Device banner at the top shows your hardware class and the recommended
   model preset. Pi 4 shows "rule-based only, VLM too slow"; Jetson Orin
   Nano shows "Full stack with VLM via CUDA".
3. Click **Webcam** tab. Click **Start webcam**. Allow camera.
4. Within a second you see detection boxes and the pose skeleton over
   your body. The action label updates every ~200 ms.
5. Raise your hand above your head. Label flips to **hands_up**.
   Cross your arms. Label flips to **arms_crossed**. Walk back and forth
   in front of the camera. Label flips to **walking**.
6. Toggle **privacy blur** on. Face region blurs on the overlay.
7. Type **"a person pointing"** in the webcam prompt. Point at the camera
   with one arm. Within 5 s the VLM match pill lights green.
8. Switch to **Video file** tab. Drop any MP4.
9. Set sampling interval to 1 s. Click **Run analysis**. Timeline bars
   appear per detected action segment. History tab logs the run.
10. For a new action not in the 12: upload a reference image showing it,
    leave the prompt blank, click Run. The worker converts the image to
    a search phrase first (`video.search_image`), then uses that phrase
    for frame-by-frame VLM scoring.

**Expected FPS** per device:

| Device | Live FPS (webcam) | VLM latency |
|---|---|---|
| Raspberry Pi 4 | 2-3 (rule-based only) | VLM disabled |
| Jetson Orin Nano | 8-12 (CPU) / 20-30 (GPU) | ~1.8 s per prompt |
| Mac Apple Silicon | 15-25 | ~0.9 s per prompt |
| Linux x86_64 modern CPU | 10-15 | ~2.5 s per prompt |

Full test plan including unit tests and end-to-end walkthrough:
[`docs/DEMOS.md`](DEMOS.md).

---

## What to show someone else

If you have ~5 minutes to demo Arikizu, go in this order:

1. Open `/` (operator dashboard). Point out the device chip and recent activity.
2. Open `/demo/video_studio.html`. Open webcam. Show the live action
   label changing as you move. This is the single most impressive demo.
3. Click **Documents**. Extract a field.
4. Click **Reasoning**. Ask one question.
5. Open `/demo/` (sandbox). Show that every one of those is a plain HTML
   file hitting the same `/api/v1/call/*` surface: no magic, no cloud.

That's the whole pitch: one binary, one device, every capability behind
one API, human-in-the-loop by default.

---

## Part 2 — Pi vision tutorial


Target: a working object-detection pipeline on a Raspberry Pi 4 or 5 with a
Pi Camera Module 3. By the end of this tutorial, your camera is streaming
frames through Arikizu, the vision model-nano is detecting objects, the dashboard
shows live events, and an approval gate catches alerts for a human to
confirm.

This is the project to post about. Not placeholders, not maybes: a real
camera, real detections, real audit log.

## Hardware (what you need in front of you)

- Raspberry Pi 4 (4 GB+) or Pi 5
- Pi Camera Module 3 (standard, Wide, or NoIR), connected to the Pi's CSI port
- Power supply, SD card, Ethernet or Wi-Fi
- (Optional) PIR motion sensor on GPIO, or a USB webcam if no Pi Camera
- A laptop on the same network

## Pre-flight (five minutes)

Confirm Arikizu's QUICKSTART Path A is done up through section A.6
(`install-runtime.sh` + `download-default-models.sh`). From the Pi:

```
# Confirm the model landed
ls -lh models/yolov8n.onnx     # ~6 MB

# Confirm the runtime got installed
python3 -c "import onnxruntime as ort; print(ort.__version__, ort.get_available_providers())"
# Expected: 1.1x.x ['CPUExecutionProvider']

# Confirm the camera is seen
rpicam-hello --list-cameras
# Expected: Available cameras: 0 : imx708 ...
```

If any of those three lines does not say what's expected, fix that before
continuing. Camera not seen means check the ribbon cable and `sudo raspi-config` → Interface → Camera → Enable.

## Step 1: Install the Python camera stack

```
sudo apt install -y python3-picamera2 python3-opencv python3-numpy
# Pi 5 uses libcamera out of the box; Pi 4 may need:
# sudo apt install -y libcamera-apps
```

Verify:

```
python3 -c "from picamera2 import Picamera2; print('picamera2 ok')"
```

## Step 2: Point vision_worker at a Python backend for one real detection

The vision scaffold has `vision.detect` wired to the ONNX runtime. We'll
upgrade it to actually run the vision model and return real detections. For this
tutorial, we won't bring in SightRAG yet: we'll use plain ONNX + a tiny
numpy preprocess step so the pipeline is end-to-end today.

Create `~/arikizu/workers/vision_worker/vision_worker/yolo.py`:

```python
"""Minimal YOLOv8 postprocessor. Not SightRAG: just enough to prove
the end-to-end path on a Pi before Weekend 5 wires the real library.
"""

from __future__ import annotations

import numpy as np

COCO = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]


def preprocess(image_bgr: np.ndarray, size: int = 640) -> tuple[np.ndarray, float, float]:
    """BGR HxWx3 uint8 → NCHW float32 in [0,1], plus scale factors to map
    detections back to the original image.
    """
    h, w = image_bgr.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(h * scale), int(w * scale)
    import cv2
    resized = cv2.resize(image_bgr, (nw, nh))
    padded = np.zeros((size, size, 3), dtype=np.uint8)
    padded[:nh, :nw] = resized
    # BGR → RGB, HWC → CHW, uint8 → float32
    x = padded[:, :, ::-1].astype(np.float32) / 255.0
    x = np.transpose(x, (2, 0, 1))[None]  # 1x3xHxW
    return x, scale, scale


def postprocess(output: np.ndarray, scale_x: float, scale_y: float,
                conf: float = 0.5, iou: float = 0.45) -> list[dict]:
    """YOLOv8 output is (1, 84, 8400). 4 bbox + 80 class scores per anchor.
    Returns list of {class, score, bbox: [x1,y1,x2,y2]} in ORIGINAL coords.
    """
    import cv2
    pred = output[0].T  # (8400, 84)
    boxes = pred[:, :4]  # cx, cy, w, h
    scores_all = pred[:, 4:]
    class_ids = scores_all.argmax(1)
    scores = scores_all[np.arange(len(scores_all)), class_ids]

    keep = scores > conf
    boxes = boxes[keep]
    scores = scores[keep]
    class_ids = class_ids[keep]

    # cxcywh → xyxy
    xyxy = np.empty_like(boxes)
    xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2

    # NMS (OpenCV)
    indices = cv2.dnn.NMSBoxes(xyxy.tolist(), scores.tolist(), conf, iou)
    detections = []
    for i in np.array(indices).flatten():
        x1, y1, x2, y2 = xyxy[i]
        detections.append({
            "class": COCO[int(class_ids[i])],
            "score": float(scores[i]),
            "bbox": [float(x1 / scale_x), float(y1 / scale_y),
                     float(x2 / scale_x), float(y2 / scale_y)],
        })
    return detections
```

## Step 3: Wire the vision handler to use it

Edit `~/arikizu/workers/vision_worker/vision_worker/__main__.py`.
Find the `detect` handler and replace it with:

```python
@worker.handler("vision.detect")
def detect(image_path: str = "", confidence: float = 0.5) -> dict:
    h = _h()
    if h is None:
        return {"image": image_path, "detections": [], "backend": "none",
                "note": "no model loaded"}
    try:
        import cv2
        from .yolo import preprocess, postprocess
        img = cv2.imread(image_path)
        if img is None:
            return {"image": image_path, "error": f"could not read {image_path}"}
        x, sx, sy = preprocess(img)
        out = h.infer({"images": x})
        # ONNX models expose outputs by name; grab the first one
        first_output_name = next(iter(out))
        preds = out[first_output_name]
        detections = postprocess(preds, sx, sy, conf=confidence)
        return {
            "image": image_path,
            "detections": detections,
            "backend": h.backend.value,
            "model": str(h.path),
        }
    except Exception as e:
        return {"image": image_path, "detections": [], "error": str(e)}
```

Install cv2 in the vision worker:

```
cd ~/arikizu/workers
echo 'opencv-python-headless>=4.9.0' >> vision_worker/pyproject.toml.add
```

Add this to vision_worker/pyproject.toml's `dependencies` block:

```toml
dependencies = [
    "arikizu-worker-sdk",
    "pillow>=10.0.0",
    "numpy>=1.26.0",
    "opencv-python-headless>=4.9.0",
]
```

Resync:

```
cd ~/arikizu/workers
uv sync --package vision-worker
```

## Step 4: Restart Arikizu and verify

```
# Terminal 1 (Pi)
cd ~/arikizu
# Kill the old `make run` (Ctrl+C)
make run
```

In another terminal (Pi or your laptop):

```
# Grab one frame from the Pi Camera
python3 demo/raspberrypi/vision_pi.py
```

Expected output now (not WAIT, actually PASS):

```
Raspberry Pi vision e2e
----------------------------------------
  frame 1/1:
  trying picamera2... captured
  wrote /tmp/arikizu-vision.jpg (xxxxxx bytes) via picamera2
  [PASS] vision.detect        150ms  HTTP 200
           {"detections":[{"class":"person","score":0.84,"bbox":[...]},
                          {"class":"laptop","score":0.72,"bbox":[...]}],
            "backend":"onnx_cpu","model":"/home/pi/arikizu/models/yolov8n.onnx"}
```

Real detections. Real latency. Real backend.

This is the output to screenshot.

## Step 5: Dashboard event stream

Open `http://arikizu-dev.local:7000/events` in your laptop browser. Then
loop the camera for 30 seconds:

```
python3 demo/raspberrypi/vision_pi.py --loop 30 --interval 1
```

The events page shows one event per detection streaming in live. Audit tab
(`/audit`) records them.

## Step 6: Add an approval gate

Edit `~/arikizu/arikizu.yaml`, add a pipeline:

```yaml
pipeline:
  - name: detect_people
    capability: vision.detect
    inputs:
      image_path: /tmp/arikizu-vision.jpg
      confidence: 0.5

  - name: filter_sensitive
    capability: guard.scan

  - name: supervisor_approval
    capability: feedback.approve
    approver_role: shift_lead
```

Then from your laptop:

```
curl -X POST http://arikizu-dev.local:7000/api/v1/pipeline/run \
     -H 'content-type: application/json' -d '{}'
```

The run stops at the approval stage. Open `http://arikizu-dev.local:7000/review`
- one row waiting. Approve. The run resumes and finishes with
`status: succeeded`.

That's a full edge-AI pipeline with human-in-the-loop. On a Pi 4. Running
offline.

## Step 7: Sensor integration (if you want)

The camera is one sensor. Arikizu's `devices:` block in `arikizu.yaml`
accepts others. For a complete factory-QA-style demo, add a PIR motion
sensor on GPIO 23 so detection only fires when something moves:

### Hardware

- HC-SR501 PIR sensor
- GND → Pi GND
- VCC → Pi 5V
- OUT → Pi GPIO 23

### Install the GPIO helper

```
sudo apt install -y python3-gpiozero
```

### Trigger pipeline from the sensor

Write `/home/pi/arikizu/motion_trigger.py`:

```python
#!/usr/bin/env python3
from gpiozero import MotionSensor
import httpx
import time

pir = MotionSensor(23)

while True:
    pir.wait_for_motion()
    print("motion detected; triggering pipeline")
    try:
        r = httpx.post("http://127.0.0.1:7000/api/v1/pipeline/run",
                       json={}, timeout=60)
        print(f"pipeline: {r.status_code}")
    except Exception as e:
        print(f"trigger failed: {e}")
    time.sleep(2)  # debounce
```

Run it as its own systemd unit, or just `python3 motion_trigger.py` in a
tmux. Now the camera + ML pipeline fires only on motion. One Pi, two
sensors (motion + camera), one ML model, one approval queue.

### Other sensors (brief)

| Sensor                    | Pi interface | Python lib        | What to do with it                 |
| ------------------------- | ------------ | ----------------- | ---------------------------------- |
| PIR motion (HC-SR501)     | GPIO digital | gpiozero          | gate pipeline on motion            |
| Ultrasonic distance (HC-SR04) | GPIO digital | gpiozero          | gate on proximity                  |
| Temp/humidity (DHT22)     | GPIO 1-wire  | adafruit_dht      | feed `timeseries.detect_anomaly`   |
| Load cell / strain gauge  | HX711 → GPIO | hx711             | feed `timeseries.forecast`         |
| GPS (NEO-6M)              | UART         | pyserial          | geo-tag detections                 |
| Modbus RTU (industrial)   | USB RS-485   | pymodbus          | bridge PLC data into Arikizu       |
| MQTT broker               | network      | paho-mqtt         | bridge any industrial feed         |

Each one plugs into Arikizu the same way: write a tiny Python script that
reads the sensor and either POSTs to `/api/v1/pipeline/run` (to fire a
pipeline) or POSTs to `/api/v1/call/<worker>/<op>` (to feed data directly
into a worker). Arikizu's pipeline executor handles the rest.

## What this proves

- Pi 4 + Pi Camera 3 + ONNX Runtime CPU + a compact vision model = real detections at ~150-400 ms per frame
- The vision worker's handler takes 20 lines of code to go from placeholder to real
- The audit log + review queue work for a real pipeline, not just a demo
- Adding a GPIO sensor is 5 lines of Python plus one systemd unit

## What SightRAG adds on Weekend 5

- Segmentation (Mobile SAM) alongside detection
- OCR branch (Tesseract + layout)
- Tracking across frames (ByteTrack)
- Per-class confidence calibration
- Richer evidence shape for the review queue

Same handler signatures. Same dashboard. Same audit log. The vision_worker
you have now is forward-compatible with SightRAG; swapping in happens
by importing the SightRAG classes in `__main__.py` instead of the
tutorial's inline `yolo.py`.

## Troubleshooting

| Symptom                                      | Fix                                                       |
| -------------------------------------------- | --------------------------------------------------------- |
| `rpicam-hello` says "no cameras found"       | `sudo raspi-config` → Interface → Camera → Enable, reboot |
| `onnxruntime` not found after step 2          | `scripts/install-runtime.sh` didn't run; run it again      |
| `cv2.imread()` returns None                   | Image path from the capture script didn't match; check `/tmp/arikizu-vision.jpg` exists |
| Detections look wrong (wrong boxes)           | Verify scale factors in `preprocess`; add `cv2.imwrite` of the preprocessed image to debug |
| High latency (>1s per frame)                  | Normal on Pi 4 CPU; use `--loop N` to measure average, or move to Pi 5 or Jetson |
| GPIO: PermissionError                         | `sudo usermod -aG gpio pi` and re-login                   |

## Memory budget on a Pi 4 (4 GB)

After this tutorial, with the four workers from QUICKSTART A.7:

| Component                    | RSS      |
| ---------------------------- | -------- |
| Rust runtime (arikizu)       | ~90 MB   |
| test_worker                  | ~50 MB   |
| vision_worker (ONNX + the vision model)  | ~250 MB  |
| guard_worker                 | ~45 MB   |
| timeseries_worker (classical ML libraries)  | ~110 MB  |
| OS + journaled logs          | ~400 MB  |
| **Total**                    | **~950 MB** |

Leaves ~3 GB for cameras, I/O, and headroom. Pi 4 (4 GB) can run this
24/7 at 1 FPS with no swap pressure.

Pi 5 (8 GB) with everything turned on: ~1.5 GB.

## What to screenshot for your post

- `arikizu status --dev` on the Pi (shows the device detection)
- `make smoke` output on the Pi showing a PASS on vision.detect
- `/events` tab in the browser mid-detection stream
- `/review` tab showing the pending approval
- Pi + camera photo (optional; good for engagement)

That's the project. One Pi, one camera, one evening. End-to-end.

---

## Part 3 — Video studio test checklist


Three layers, each answers a different question.

---

## 1. Unit tests (does the logic work in isolation?)

Fastest. Does not need MediaPipe, VLM or any model file. Exercises the
rule-based action recognizer against canned pose landmarks.

```
cd workers/video_worker
PYTHONPATH=. python3 -m pytest tests/ -v
```

Expected: 11 green in under 100 ms. One test per action rule plus
`test_unknown_floor` and `test_actions_known_registry`.

If any test fails, the rule logic in
`workers/video_worker/video_worker/actions.py` changed and the fixture
needs updating.

---

## 2. Device + model diagnostic (will my hardware actually run this?)

Before you try the UI, confirm the stack is reachable.

```
make doctor
curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/device_report \
  -H 'content-type: application/json' -d '{"payload":{}}'
```

Expected `video.device_report` returns:

- `device.device_class`: one of `pi4 pi5 jetson_nano jetson_orin_nano
  mac_apple_silicon linux_x86 windows_wsl`
- `preset.detector`: usually `efficientdet_lite0`
- `preset.vlm`: `none` on Pi 4, `qwen2_5_vl_3b_q4` on Jetson Orin Nano and up
- `fits[]`: one row per model with `expected_fps` for this device

Then confirm which models are on disk:

```
curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/backends \
  -H 'content-type: application/json' -d '{"payload":{}}' | jq
```

If any critical row shows `present: false`, run:

```
scripts/download-video-models.sh              # perception only (~22 MB)
scripts/download-video-models.sh --with-vlm   # add Qwen VL (~2.7 GB)
```

---

## 3. Rule-based action recognition (does pose -> action work?)

Call the pure-logic endpoint. No MediaPipe needed on the client side; the
browser or any script can send pose landmarks.

```
cat > /tmp/pose_waving.json <<'EOF'
{"payload":{
  "landmarks":[[0.5,0.5,0],[0.5,0.5,0],[0.5,0.5,0],[0.5,0.5,0],[0.5,0.5,0],
               [0.5,0.5,0],[0.5,0.5,0],[0.5,0.5,0],[0.5,0.5,0],[0.5,0.5,0],
               [0.5,0.5,0],
               [0.4,0.4,0],[0.6,0.4,0], [0.4,0.4,0],[0.6,0.4,0],
               [0.4,0.2,0],[0.6,0.2,0],
               [0.4,0.4,0],[0.6,0.4,0],[0.4,0.4,0],[0.6,0.4,0],[0.4,0.4,0],[0.6,0.4,0],
               [0.4,0.6,0],[0.6,0.6,0],[0.4,0.75,0],[0.6,0.75,0],
               [0.4,0.9,0],[0.6,0.9,0], [0.5,0.9,0],[0.5,0.9,0],[0.5,0.9,0],[0.5,0.9,0]],
  "visibility":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]
}}
EOF

curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/recognize_pose \
  -H 'content-type: application/json' -d @/tmp/pose_waving.json | jq
```

Expected: `{"action": "hands_up" | "waving", "confidence": > 0.7}`.

---

## 4. Live frame perception (does MediaPipe actually run?)

Takes a JPEG from your webcam or any image, base64 encodes it, posts to
`video.live_detect`.

```bash
base64 -w0 <(curl -sS https://picsum.photos/640/480) > /tmp/img.b64 2>/dev/null \
  || base64 /path/to/your/image.jpg > /tmp/img.b64
echo '{"payload":{"image_base64":"'$(cat /tmp/img.b64)'"}}' \
  > /tmp/live.json

curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/live_detect \
  -H 'content-type: application/json' -d @/tmp/live.json | jq '.frame.ms, .action'
```

Expected: `.frame.ms` shows `{detect, pose, face}` per-stage latency and
`.action` has an action label (or `unknown` if the image has no person).

If `backend: "no-mediapipe"` comes back, MediaPipe isn't installed. Fix:

```
cd workers && uv add mediapipe --package video-worker
```

---

## 5. VLM scoring (does the open-vocabulary action search work?)

Only works when `video.backends.vlm.mode` is `local-gguf` or `http`.

```bash
curl -sS -X POST http://127.0.0.1:7000/api/v1/call/video/live_describe \
  -H 'content-type: application/json' \
  -d '{"payload":{"image_base64":"'$(cat /tmp/img.b64)'",
                   "prompt":"a person standing in a room"}}' | jq
```

Expected: `{matches: true|false, confidence: 0..1, evidence: "..."}`.

Response time on edge hardware: Jetson Orin Nano ~1.8 s, Mac M2 ~0.9 s,
Pi 4 not supported.

---

## 6. End-to-end browser walkthrough

Open `http://127.0.0.1:7000/demo/video_studio.html`.

1. Device banner at top shows your device class + recommended preset
2. Click **Webcam** tab, click **Start webcam**, allow camera
3. Within 2 seconds you see boxes + pose skeleton on your face/body
4. Mic indicator says "running"; action label updates every ~200 ms
5. Toggle **privacy blur** on; your face area goes dark on the overlay
6. Type a prompt like "a person raising their hand" in the webcam prompt
   field, raise your hand, wait up to 5 s for the VLM pass
7. Expect "VLM match: YES ##%"
8. Click **Video file** tab, drop any short MP4
9. Set interval to 1 s, click Run analysis
10. Timeline fills with action bars after processing finishes
11. Click **History** tab; the clip you just ran appears at the top

If any step fails, the HUD panel on the right shows the latency per stage
and the device banner at the top shows which models are loaded. That is
usually enough to figure out what is missing.

---

## 7. Hardware benchmark

Measure actual per-stage ms on your box, not just the predicted FPS.
This script is called by the UI on page load for the live FPS counter;
you can run it manually to log a baseline.

```
cd /home/vk001/arikizu/workers/video_worker
PYTHONPATH=. python3 -c "
from video_worker.devices import detect, preset_for, all_fits
from video_worker.models import prefetch_for_device
d = detect()
print(f'device: {d.device_class} ({d.arch}, {d.cpu_count} CPU, {d.ram_gb} GB RAM, GPU: {d.gpu_name or \"none\"})')
print(f'preset: {preset_for(d.device_class)}')
print()
print(f'{\"model\":<30} {\"fits\":<6} {\"ms\":<6} {\"fps\":<6} {\"delegate\":<16} reason')
for f in all_fits(d.device_class):
    print(f'{f[\"model_key\"]:<30} {str(f[\"fits\"]):<6} {f[\"expected_ms_per_frame\"]:<6} {f[\"expected_fps\"]:<6} {f[\"delegate\"]:<16} {f[\"reason\"]}')
"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `backend: "no-mediapipe"` | MediaPipe not installed | `cd workers && uv add mediapipe --package video-worker` |
| `vlm.mode: "none"` with GGUF present | llama-cpp-python not installed | `cd workers && uv add llama-cpp-python --package video-worker` |
| `pose_landmarks: []` on every frame | no person visible, or the person is tiny | step closer to the camera; or set `PERSON_THRESHOLD=0.15` |
| VLM returns `raw: "..."` instead of parsed JSON | the model drifted from the schema | reduce `max_tokens`, or use a larger VLM via `ARIKIZU_VLM_ENDPOINT` |
| Timeline shows every frame as `unknown` | confidence floor too high for your lighting / angle | lower `CONFIDENCE_FLOOR` in `video_worker/actions.py` |
| Device banner says "detecting device..." forever | the HTTP router or the supervisor is down | `make run` in another terminal, check `http://127.0.0.1:7000/api/v1/status` |
