# Arikizu v1.5

## v1.5.33 (surface the real reason models don't load)

User screenshot after v1.5.32: reasoning READY, vision + audio still
MISSING even though the files are on disk and sized correctly
(yolov8n.onnx = 12 MB, silero_vad.onnx = 2.3 MB). My project-root fix
is reaching the files; the ONNX session is failing to load them.

Most likely cause: the Kalray yolov8n.onnx mirror ships specialized
ops that some onnxruntime builds reject. The script already pulled it
once with no checksum so it is sitting on disk and the "already
exists" fast path skips a refresh.

**Fix:**

- Switched vision download primary to `onnx-community/yolov8n` (plain
  CPU-friendly ONNX export); Kalray stays as fallback.
- Added `--force` flag to `scripts/download-default-models.sh` so an
  existing file can be replaced in-place.
- `vision.backends` and `audio.backends` now return `load_error`,
  `models_dir`, and `cwd`, with the exact exception the ONNX loader
  threw. No more guessing.
- Demo-hub diagnostics panel shows that `load_error` inline under the
  MISSING tag, so VK can read the real failure without opening logs.

**On WSL to re-fetch with the new mirror:**

```
scripts/download-default-models.sh --force
pkill -f arikizu; make run
```

If the YOLO file still fails to load, the diagnostic row will now
print exactly which onnxruntime exception threw.

## v1.5.32 (the real "nothing loads" fix)

v1.5.31 added the diagnostics, which proved the user's point: the model
files were on disk, but the workers still reported "no model loaded".
The actual cause: workers are spawned by the Rust supervisor from inside
their package dir (workers/vision_worker/, workers/audio_worker/, etc).
The default `ARIKIZU_MODELS_DIR=./models` therefore resolved to
`workers/vision_worker/models/` which was empty. The model file sits at
`<project_root>/models/yolov8n.onnx`.

**Fix:**

- Each worker now walks up from its CWD looking for a project marker
  (arikizu.yaml.example, capabilities.toml, or Cargo.toml) and resolves
  `./models` against that root instead of its own package dir.
- Done in vision_worker, audio_worker, and reasoning_worker.
- Zero config change needed: existing env vars still win if set
  explicitly, absolute paths still work, and the fallback is the old
  CWD-relative behavior for anyone running outside the project.

**Audio indicator conflict (also user-reported):**

The screenshot showed "Live transcript: help" but the mic indicator
stuck at "mic: silence". Root cause: the 1-second PCM chunker was
posting to the server every second, which returned "no speech" (because
the chunker's audio stream and the Web Speech API's audio stream are
separate pipes), and that result overwrote the recognizer's "KW: help"
with "silence" within one tick.

- PCM chunker now defers to the recognizer when the recognizer is
  running (Chrome and Edge). It only writes the indicator when the
  recognizer is absent (Firefox fallback).
- Indicator is sticky: a KW hit holds for 2.5s so a one-word match
  stays visible instead of being wiped by the next tick.
- Recognizer also sets "heard: ..." for speech that didn't match a
  keyword, so you can see it IS listening even without a hit.

## v1.5.31 (make it visible when things are broken)

The user's complaint on v1.5.30 was "basically no vision model is loaded,
no detection or segmentation, audio keyword 'I need help' is not
detected". The real problem wasn't the demos: it was that when a model
file is missing or a worker is wedged, nothing on the page said so, so
every failure looked like the same mystery. v1.5.31 makes every failure
mode self-reporting.

**Diagnostics**

- New `scripts/doctor.sh`: one-shot self-check. Prints PASS/FAIL for
  python version (<3.14 for llama-cpp wheels), onnxruntime, numpy,
  pillow, llama-cpp-python, msgpack, each required model file (with
  size check so a half-downloaded file fails loud), the arikizu
  binary, and the supervisor HTTP endpoint. Each FAIL row prints
  the exact fix command.
- `make doctor` now runs the shell script (works even when the build
  or supervisor is broken).

**Visible model banners on demo pages**

- Vision page shows a top banner: green dot "vision model loaded:
  yolov8n.onnx" or red dot "no vision model loaded - fix: run
  scripts/download-default-models.sh".
- Audio page shows the same for the Silero VAD model.
- Demo hub home page shows a Diagnostics section with one row per
  worker: READY (loaded) / MISSING (download command) / OFFLINE
  (supervisor down).

**Real keyword matching on audio demo**

The VAD-heuristic match from v1.5.30 was a lie: it flagged every speech
segment as a hit for every keyword in the list, which is why saying
"I need help" with "help" in the keyword list didn't light up (the
indicator pulsed on every utterance, not just the one that matched).

- Audio demo now uses the browser's built-in Web Speech API for
  phonetic keyword matching. Works offline in Chrome and Edge, no
  download needed. The live transcript shows what the browser heard,
  and keyword hits trigger the KW indicator with the matched word.
- Server `audio.keyword_spot` accepts `transcript=` for real
  substring matching and logs hits to the audit log; the dishonest
  VAD-heuristic fallback is gone.
- New `audio.backends` and `reasoning.backends` capabilities expose
  which model files are loaded, so the diagnostics panel can show it.

## v1.5.30 (demo hub trimmed to 4)

Removed the demos people were skipping:

- Vision search (audit-log search)
- Timeseries (chart + forecast)
- Guard (PII scan + redact)
- Eval (predicted vs expected)
- Memory (session browser)
- JSON sandbox (raw worker testing)
- Runtime JSON link
- Audit log JSON link

Kept the four that are the core story:

1. **Vision** - live webcam object detection
2. **Audio** - live mic VAD + keyword spotting
3. **Documents** - PDF upload + ask question
4. **Reasoning** - local LLM chat

Plus the one-click smoke test at the bottom.

The removed demos still work by direct URL (/demo/eval_view.html etc.)
and remain in the operator dashboard on the home page. They just do
not clutter the developer hub where new users start.

v2 will polish these four, then add the next feature per weekend
instead of showing everything at once.

## v1.5.29 (fixture image path + audio threshold)
## v1.5.28 (segmentation dropdown + Vision Search fix)
## v1.5.27 .. v1.5 (prior history)
