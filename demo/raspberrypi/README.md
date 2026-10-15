# Raspberry Pi end-to-end tests

The point: prove the full path works on real Pi hardware before anything else.

```
camera / mic  →  capture file  →  arikizu HTTP API  →  worker  →  response
```

If any of these scripts return something sensible, the vertical slice is live.
When SightRAG and Sonarwise are wired on Weekend 5/6, the same scripts return
real detections and real transcripts — no change needed.

Target hardware (verified):

- Raspberry Pi 4 Model B (4 GB or 8 GB) running Raspberry Pi OS 64-bit (bookworm)
- Pi Camera Module 3 OR a USB webcam
- USB microphone OR a USB sound card with mic input

Also works on:

- Pi 5 (both camera stacks)
- Pi Zero 2 W (vision is slow; audio fine)
- Jetson Orin Nano (camera via /dev/video*)

## Install

```
# One-time setup on the Pi:
sudo apt install -y python3-picamera2 python3-opencv alsa-utils libportaudio2
python3 -m pip install --user sounddevice
```

Not every library needs to be present. The scripts probe for what's
there and skip the rest with a clear SKIP line.

## Run

In one terminal:

```
cd ~/arikizu && make run
```

In another:

```
cd ~/arikizu
python3 demo/raspberrypi/probe.py          # 1. hardware probe
python3 demo/raspberrypi/vision_pi.py      # 2. camera -> vision.detect
python3 demo/raspberrypi/audio_pi.py       # 3. mic -> audio.transcribe
```

Or run all three in sequence:

```
bash demo/raspberrypi/run_all.sh
```

## What each script does

### probe.py

Prints what's on this Pi:

- Pi model (reads `/proc/device-tree/model`)
- Kernel, CPU, memory
- `/dev/video*` entries (cameras)
- `arecord -l` output (mics)
- Whether picamera2, opencv, sounddevice are importable
- Whether arikizu is reachable

Pure read, zero network. Safe to run anytime.

### vision_pi.py

1. Picks a camera: picamera2 if available, else `/dev/video0` via opencv, else
   falls back to the bundled `demo/fixtures/sample.png`.
2. Grabs one frame, saves to `/tmp/arikizu-vision.jpg`.
3. POSTs to `/api/v1/call/vision/detect` with that path, confidence 0.5.
4. Prints PASS / WAIT / FAIL for the call plus the response.

Flags:

```
python3 demo/raspberrypi/vision_pi.py --conf 0.7      # higher threshold
python3 demo/raspberrypi/vision_pi.py --image /path   # skip camera, use existing
python3 demo/raspberrypi/vision_pi.py --loop 10       # 10 frames with 1s between
```

### audio_pi.py

1. Picks a mic: `sounddevice` default device if importable, else `arecord` on
   the first ALSA capture device, else falls back to `demo/fixtures/sample.wav`.
2. Records 3 seconds to `/tmp/arikizu-audio.wav` at 16 kHz mono.
3. POSTs to `/api/v1/call/audio/transcribe` with that path.
4. Prints PASS / WAIT / FAIL plus any detected text.

Flags:

```
python3 demo/raspberrypi/audio_pi.py --seconds 5         # record longer
python3 demo/raspberrypi/audio_pi.py --wav /path         # skip mic
python3 demo/raspberrypi/audio_pi.py --vad               # also run vision.vad
```

### run_all.sh

Just runs probe, vision_pi, audio_pi in order and prints a summary at the end.
Non-zero exit on any FAIL.

## Reading the output

Same classifier as `demo/smoke_test.py`:

- **PASS** — real result returned. Vision found objects or OCR'd text; audio
  transcribed to text.
- **WAIT** — worker returned the placeholder note. SightRAG or Sonarwise
  is not wired yet; the capture + path + HTTP call all worked.
- **SKIP** — the matching worker isn't running (503). Expected if you've
  trimmed your `arikizu.yaml` to a subset of workers.
- **FAIL** — real bug. Camera failed to open, 500 from the runtime, non-JSON
  response, or timeout.

## Common issues

| Symptom                                   | Fix                                                                   |
| ----------------------------------------- | --------------------------------------------------------------------- |
| `picamera2 not installed`                 | `sudo apt install python3-picamera2`                                  |
| `cv2 not installed`                       | `sudo apt install python3-opencv`                                     |
| `No /dev/video*` found                    | `sudo modprobe bcm2835-v4l2` for the legacy Pi Camera path            |
| `sounddevice: PortAudio library not found`| `sudo apt install libportaudio2`                                      |
| `arecord: no soundcards found`            | Check `arecord -l`; your mic may be USB and needs `plughw:1,0` syntax |
| vision.detect returns WAIT                | Normal in v0.1. Weekend 5 ships the real wiring.                      |
| audio.transcribe returns WAIT             | Normal in v0.1. Weekend 6 ships the real wiring.                      |

## Measuring

The scripts print one-line timing. For sustained measurement, use `--loop N`
on vision_pi.py and watch the dashboard's `/events` tab for the live stream.

Typical v0.1 numbers on a Pi 4 (placeholder handlers; real numbers come after
Weekend 5/6):

- Capture frame (picamera2):     20-40 ms
- HTTP call to vision.detect:    2-5 ms (just the placeholder round trip)
- Total end-to-end:              < 60 ms

Real SightRAG numbers depend on model choice; a YOLO nano on Pi 4 CPU typically
runs 150-400 ms per frame.
