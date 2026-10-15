# Pi vision project: camera to dashboard in one hour

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
