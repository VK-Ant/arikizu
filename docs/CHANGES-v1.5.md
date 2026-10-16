# Arikizu v1.5

## v1.5.40 (README architecture diagram: Mermaid instead of ASCII)

The "Architecture at a glance" block in the README was ASCII art, which
GitHub renders in a monospace code block and reads badly: boxes drift,
pipes don't align, the four-zone shape is lost. Replaced it with a
Mermaid flowchart that GitHub renders natively.

- Four interaction entry points (UI, CLI) → HTTP → Supervisor → six
  worker boxes (Vision/SightRAG, Audio/Sonarwise, Documents/DocQWise,
  Reasoning/LLM, Timeseries/WavqWise, Guard/AntGuard).
- Feedback Manager shown as a peer of Supervisor + HTTP (bidirectional
  arrows), matching how it actually sits in the system.
- Colored class defs: supervisor + HTTP in accent orange, workers in
  neutral card color, feedback in trust green.
- Verified by rendering the diagram with mermaid-cli: 208 KB SVG,
  parses cleanly, syntax is portable to GitHub's renderer.
- `docs/assets/architecture-glance.svg` saved as a fallback for
  non-GitHub markdown viewers.

## v1.5.39 (customization guide)

Scattered mentions of "how to swap a model" or "how to add a worker"
across ARCHITECTURE.md, MODELS.md, HOW_IT_RUNS.md, but no one page
anyone would land on. Added `docs/CUSTOMIZE.md` as the single
customization reference. Seven recipes, each one or two file edits:

1. Swap a model (drop into models/ or set an env var)
2. Add a capability (one TOML entry + one handler function)
3. Add a new worker (scaffold from test_worker/, four steps)
4. Rebrand the UI (replace logo.png, change --accent token)
5. Add a demo page (copy any page, keep the shared header)
6. Load your own data (upload, server path, camera/mic, LAN stream)
7. Deploy on a device (Pi, Jetson, Mac, Linux, WSL)

Plus a `Where things live` map at the end so a new contributor can
find any file in one glance.

- Linked from the README top-nav alongside Quickstart and
  Architecture.
- "Make it yours" section added to the README between the demo
  walkthrough and default models sections, so a reader who skips the
  top-nav still sees it.

## v1.5.38 (one consistent header across all demo pages)

VK's note: "all should be same background, add Arikizu logo on top,
attractive and clean". Every demo page now shares the same header:
Arikizu logo + name as a link back to the hub, breadcrumb separator,
then the page name (Vision / Audio / Documents / Reasoning /
Timeseries). Hovering the Arikizu name tints it accent orange so the
breadcrumb-back action is obvious.

- Softened the palette: dark background goes from `#15150f` (almost
  black) to `#1a1a14` (warm charcoal), card from `#1f1f18` to
  `#23231c`, border a shade warmer. Light-mode background a hair
  warmer too. Same tokens on all six pages; no page is darker or
  colder than another.
- Header has a smaller logo (32px) and tighter padding so it doesn't
  dominate on short pages.
- Vision page's frames/fps/status moved to the right side of the
  header via `margin-left: auto`, so the status row doesn't push the
  main area down.
- Reasoning page's "Local LLM via GGUF…" blurb condensed into a
  single small line beside the title.

## v1.5.37 (timeseries: upload your own sensor data)

The timeseries demo was always-generated sine wave + injected spikes.
Fine as a smoke test, pointless as a real demo. Added file upload so
anyone can drop their own sensor log on the page and run forecast /
anomaly against it.

- File upload accepts .csv, .tsv, .txt, .json, .xls, .xlsx.
- CSV / TSV: splits on comma / tab / semicolon, picks the first column
  where >=80% of rows parse as finite numbers (so header rows and
  timestamp columns are skipped automatically).
- JSON: accepts a flat array of numbers, {series: [...]}, {data: [...]},
  or an array of objects (first numeric field wins).
- XLSX: SheetJS 0.18.5 is lazy-loaded from cdnjs only when the user
  picks an Excel file.
- `demo/fixtures/sensor_readings.csv` added — 96 rows of synthetic
  temperature / pressure / vibration data with two injected anomaly
  spikes at index 41 and 71, so there's always something to try the
  upload with.
- Timeseries card is back on the demo hub (5 cards instead of 4), now
  that it accepts real data rather than only showing a sine.

## v1.5.36 (audio page: drop the pointless file-based VAD)

The shipped sample.wav is a 1-second sine tone, so "Run VAD on file"
always reported 0 segments and audio.transcribe always reported
(empty). Both PASS but neither showed anything useful. Removed.

Audio page is now one flow: click "Use microphone", speak a keyword,
indicator flips to KW: &lt;word&gt;. Live transcript shows what was
heard. Waveform draws from the mic input while it's on.

## v1.5.35 (models ship in the zip)

VK's point was correct: a demo should not make the user hunt down model
files from flaky HF mirrors. The vision and audio models are small
(12 MB and 2.3 MB respectively), so they now ship pre-installed in
`models/` with the release.

**What's bundled:**

- `models/yolov8n.onnx` (12 MB, AGPL-3.0, exported from ultralytics
  v8.4.178, loads cleanly in plain onnxruntime)
- `models/silero_vad.onnx` (2.3 MB, MIT, extracted from `silero-vad`
  PyPI v6.2.3)
- `models/NOTICE.md` explaining each model's source and license

**Still downloaded on demand:**

- SmolLM2 360M GGUF (258 MB — too big for a zip). Reasoning worker has
  a built-in KB fallback so the demo runs without it.

**On WSL:** unzip, `make build`, `make run`. The vision and audio
demos work immediately. Diagnostics panel is READY on both without any
download step.

## v1.5.34 (the actual bug: vision was loading Silero VAD)

The traceback from the WSL run cracked it open:

```
Required inputs (['state', 'sr']) are missing from input feed (['input']).
File ".../vision_worker/__main__.py", line 336, in detect
```

`state` and `sr` are Silero VAD inputs. The vision worker was loading
`silero_vad.onnx` and trying to run YOLO inference on it.

**Root cause chain:**

1. `--force` deleted the Kalray yolov8n.onnx on disk.
2. The replacement URL (`onnx-community/yolov8n`) returned 401 — that
   repo path does not exist on HF the way I guessed.
3. The Kalray fallback was also attempted but may have failed too.
4. yolov8n.onnx was then absent from models/.
5. `_auto_discover_model` had a last-resort `glob("*.onnx")` that
   returned the first ONNX file alphabetically: `silero_vad.onnx`.
6. onnxruntime loaded that file. On the first vision.detect call it
   demanded `state` and `sr` (VAD inputs) that the YOLO code never
   provides.

**Fixes:**

- `_auto_discover_model` is now strict. It accepts only YOLO
  filenames (`yolov8*.onnx`, `yolov5*.onnx`, `yolo.onnx`) and files
  that start with `yolo`. If no YOLO file is present, it returns
  empty and the banner says so plainly. It will never again load a
  VAD file as a vision model.
- Download script now tries three HF mirrors in sequence and prints
  the exact fallback command when all three fail.
- `scripts/export_yolo_onnx.py` added: uses the `ultralytics` PyPI
  package to export a guaranteed-working ONNX locally. This is the
  bulletproof path when HF mirrors are flaky:
  ```
  pip install ultralytics
  python3 scripts/export_yolo_onnx.py
  ```
- Vision page banner now shows the actual `load_error` text instead
  of a generic "run the download script" message, so a wrong-model
  bug (if one ever recurs) is immediately visible.

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
