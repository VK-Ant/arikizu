# Testing the Video Studio

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
