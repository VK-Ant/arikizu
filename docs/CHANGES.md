# Arikizu v1.7

## v1.7.3 (fixes for the two things that catch everyone first time)

VK's screenshots on WSL + RTX 5050 confirmed two real failure modes.
Both have one-command fixes, now surfaced loudly in the README and the
diagnostic tooling.

**Problem 1: Video Studio shows "unknown / 0 people / 0 objects".**

MediaPipe not installed. The diagnostic panel already said MISSING,
but the fix command was buried. Now:

- README has a prominent "Two things that catch everyone first time"
  section at the top with copy-paste fixes.
- `scripts/doctor.sh` for each MediaPipe-dependent model row now shows
  the full `uv add` command inline, not just the download step.

**Problem 2: Agent answers "Arikizu is video editing software".**

SmolLM2-360M is a 360-million-parameter model: fine for canned Q&A,
too small to follow a system prompt or emit structured tool calls.
The default install uses it, so first-time Agent Studio users get
hallucinations.

- `scripts/download-reasoning-llm.sh` added: downloads
  Qwen2.5-{0.5b,1.5b,3b,7b}-Instruct Q4_K_M from Qwen's canonical
  Hugging Face repo. Default is 1.5B (~1 GB), the smallest size that
  can reliably do agent chat with tool calling.
- `reasoning_worker/_auto_discover_gguf()` now picks the BIGGEST
  text-only instruct GGUF rather than first-alphabetical. If the user
  downloads Qwen 1.5B alongside SmolLM2, Qwen wins automatically on
  restart. Explicitly skips vision-mmproj GGUFs (Qwen2.5-VL mmproj
  won't be mis-selected as a text LLM).
- Agent Studio UI gets a reasoning-model indicator in the header. If
  the current model is tiny (regex: 360m, 135m, smollm2), it shows an
  orange "too small for agent chat" warning with a "how to upgrade"
  link that pops the exact command.
- Agent system prompts now prepend a short grounding paragraph about
  what Arikizu IS and ISN'T. This stops small models from inventing
  "Arikizu is video editing software" when the agent policy doesn't
  cover the user's question.
- `make doctor` gained an agent-reasoning-size check that warns if
  only SmolLM2-360M is downloaded.

Both fixes are visible and copy-pasteable. The honest story about
agent model size (why 360M is not enough, what to use instead) is
documented in the README troubleshooting block.

Verified: 14/14 agent policy + tool-call tests still pass.
Reasoning worker auto-selection picks the biggest instruct GGUF when
multiple are present, correctly skipping mmproj files.

## v1.7.2 (explicit "how to run everything" + smoke-test coverage)

Checkpoint pass: made the full-stack run story explicit in the README
and added the new workers to the smoke test so `make smoke` actually
exercises them.

- **README gets a new "Enable the full stack" section** between the
  5-minute quickstart and the Video Studio section. Four blocks:
  Video Studio install, Agent Studio notes, MCP server install, and
  a single copy-paste block that enables everything at once. Verify
  commands at the bottom.
- **Smoke test ALL array extended** with six new rows:
  `video.actions_known`, `video.device_report`, `video.backends`,
  `agent.policy_default`, `agent.list`, `agent.backends`. These are
  the backend/diagnostic calls that run everywhere regardless of
  which heavy models are loaded.
- No code changes outside the smoke-test list; this is a visibility
  and docs sweep.

## v1.7.1 (examples/ + agent.import + one-click starting points)

Confirmed the download-and-customize story works end-to-end, then
made it concrete with a top-level `examples/` tree so people don't
start from a blank slate.

- `examples/agents/` ships five ready-to-import JSON agents:
  Safety Inspector (factory PPE), Elder Care Companion (home
  monitoring), Document Reviewer (contracts with PII redaction),
  Sensor Triage (time-series anomaly + forecast), Retail Floor
  Watcher (people count, dwell).
- `examples/actions/` has a template (`squatting.py`) plus a README
  showing how to drop a new rule into `video_worker/actions.py`.
- `examples/mcp-configs/` has `.mcp.json` snippets for Claude Code,
  Cline, and Cursor.
- `examples/demo-pages/blank.html` is a minimal page with the shared
  Arikizu header and palette already wired up; copy, rename, fill in.
- `examples/README.md` is the index: what every subdirectory contains,
  the one-liner to import an agent, the one-liner to add an action,
  the one-liner to wire up MCP.

- New capability `agent.import` that loads a JSON agent from either a
  dict (`definition`) or a project-relative file path (`file_path`).
  Added to `capabilities.toml`.
- `demo/web/agent_studio.html` gets an **Import examples** button that
  calls `agent.import` for all five shipped agents in one click.
- `README.md` gets a "Download, customize, use" section just above
  "Make it yours", pointing at `examples/` with a one-line pitch for
  each subdirectory.

- New test `test_example_agents_import_shape` validates every shipped
  agent JSON has `name` + `system_prompt` and a policy that passes
  `policy.validate_policy`. 14/14 tests now pass (was 13).

## v1.7.0 (Agent Studio, MCP server, Responsible AI governance)

Three new pieces land together because they are one story: custom
agents + external agents + the governance ring they all operate inside.

**New: workers/agent_worker/** (~900 lines, 4 modules, 13 passing tests)

- `policy.py` — three-action governance (auto / ask / deny) per
  capability per agent, hard-deny list for platform-level operations,
  default policy covering 35 capabilities, validator that refuses to
  override hard-deny.
- `agents.py` — SQLite-backed agent + conversation + turn storage;
  CRUD surface for the chat loop and the UI.
- `tools.py` — tool-call extraction from LLM output (`<tool_call>` JSON
  blocks), per-call policy dispatch, forwarding to Arikizu HTTP router
  so every call lands in the central audit log.
- `__main__.py` — the chat loop: user turn → reasoning worker →
  extract tool calls → dispatch through policy → feed results back
  for up to 3 LLM iterations → store assistant turn with every tool
  call record.
- 11 new capabilities under `agent.*` registered in capabilities.toml:
  create, update, delete, list, get, policy_default, allowed_caps,
  chat, conversation, conversation_list, backends.

**New: mcp/arikizu_mcp_server.py** (~160 lines)

MCP stdio server that exposes a safe subset of 17 Arikizu capabilities
to external agents (Claude Code, Cline, Cursor, your own framework).
Every call forwards through the Arikizu HTTP router so policy + audit
+ approval queue all apply. The MCP server is a thin adapter, not a
bypass. Install guide in `docs/AGENTS.md`.

**New: demo/web/agent_studio.html** (~380 lines)

Three-pane UI: agent list on the left, chat in the middle, live
policy panel on the right showing the current agent's auto / ask /
deny capability sets. Create / edit modal. Every assistant message
shows attached tool-call records with capability name, policy
decision badge, and the result preview.

**New docs:**

- `docs/AGENTS.md` — custom agent architecture, policy explanation,
  tool-call protocol, Agent Studio walkthrough, pointer to MCP for
  external agents
- `docs/AGENTS.md` — install, wire-up for Claude Code / Cline / Cursor,
  which capabilities are exposed, governance across the boundary,
  troubleshooting
- `docs/AGENTS.md` — the Responsible-AI-by-architecture story:
  four claims, per-entry-point governance table, hard-deny list, how
  the audit log looks as SQL queries, how it compares to cloud-API
  governance

**Updated:**

- `README.md` — new top-nav links for Agents, MCP, Governance; new
  "Custom agents and MCP" section between Video Studio and Make It
  Yours; architecture Mermaid diagram now shows the MCP adapter path,
  the Agent Studio worker beside Video Studio, and the dotted
  "policy enforcement" edge from the agent back to HTTP
- `docs/assets/architecture-glance.svg` — re-rendered (218 KB)
- `demo/web/index.html` — hub card #7 added for Agent Studio;
  diagnostics panel now probes `agent.backends`
- `capabilities.toml` — new `agent.*` section with 11 rows
- `workers/pyproject.toml` — `agent_worker` added to the uv workspace

**Hard-deny list** (platform-level, policy cannot override):
- `feedback.approve`, `feedback.reject` (an agent cannot approve its
  own calls)
- `arikizu.shutdown`, `arikizu.restart` (platform control)
- `arikizu.policy.set` (policy itself cannot be edited by an agent)

Explicitly out of scope for v1.7.0:
- WebSocket-based approval resumption (operator must poll
  `feedback.pending` for now)
- Agent-to-agent delegation (reserved for v1.8)
- Fine-grained per-user auth (local-user trust still assumed)

Verified: 13/13 policy + tool-call unit tests pass. 11/11 action
tests still pass. All eight demo pages' inline JS parses clean.
Mermaid diagram renders to 218 KB SVG. Python modules import cleanly
regardless of whether MediaPipe / llama-cpp / mcp are installed.

---

# Arikizu v1.6

## v1.6.1 (full doc sweep for Video Studio)

v1.6.0 shipped the worker, demo, Mermaid diagram and VIDEO_STUDIO_TEST
guide, but six adjacent docs still read as if the Video Studio did not
exist. Fixed in one pass:

- `docs/ARCHITECTURE.md`: workers table extended to 11 (added `video`
  worker row with its 10 capabilities and the Qwen2.5-VL note); updated
  the "eleven workers" wording in the opening paragraph; replaced the
  stale `assets/architecture.png` reference with the new SVG that was
  already rendered for the main README.
- `docs/SETUP.md`: appended a Video Studio models table listing all
  eight model files (perception + VLM) with sizes, formats, delegate
  recommendations, and the download command.
- `docs/DEMOS.md`: new section 10 "Video Studio: multimodal action
  search" with click-by-click walkthrough including the reference-image
  flow for open-vocabulary actions; "What to show someone else" updated
  to lead with Video Studio instead of basic vision.
- `docs/SETUP.md`: device-capability table extended with a Video Studio
  column showing expected FPS and VLM latency per device, from Pi 4
  (rule-based only) to AGX Orin.
- `workers/README.md`: ASCII tree got the `video_worker` entry plus a
  paragraph on what it covers and the device-aware model picker.
- `docs/assets/architecture-glance.svg`: re-rendered from the current
  Mermaid source to pick up any edits.

## v1.6.0 (Video Studio: multimodal action search on edge)

A new worker, a new demo page, a new category of capability. Ported the
best of VK's local video intelligence POC into Arikizu as a first-class
worker. Three input modes (no prompt, text prompt, reference image) all
route into the same pipeline. Runs edge-first: Pi 4 gets rule-based
action recognition only; Jetson Orin Nano and up get the full stack
including Qwen2.5-VL 3B.

**New: workers/video_worker/** (10 files, ~1600 lines)

- `__main__.py` — worker entry with 11 capabilities registered
- `devices.py` — detects device class, computes model-fit per
  (model, device) pair, picks a recommended preset. The honest
  "will this actually run on my Pi 4" answer, baked in as a lookup.
- `models.py` — model registry, download-on-first-use, project-root
  path resolution (same walk-up pattern as vision/audio workers)
- `actions.py` — 12 rule-based action recognizers (walking, running,
  sitting, standing, waving, kicking, jumping, hands_up, arms_crossed,
  bending, falling, pointing). ~1 ms per frame, no ML inference.
- `perception.py` — MediaPipe LiteRT wrapper (EfficientDet-Lite0 +
  Pose Landmarker + BlazeFace), fails gracefully if MediaPipe missing
- `vlm.py` — Qwen2.5-VL 3B via llama-cpp-python + mmproj; HTTP fallback
  via ARIKIZU_VLM_ENDPOINT; "none" mode keeps everything else running
- `motion.py` — Farneback optical flow helpers
- `history.py` — SQLite history (events + metadata, never frames)

**New capabilities** (12 added to capabilities.toml):

- `video.device_report` — device profile + preset + fit table
- `video.actions_known` — list of recognized actions with definitions
- `video.recognize_pose` — pure pose -> action (no model load)
- `video.live_detect` — one frame -> boxes + pose + action
- `video.live_describe` — one frame + optional prompt -> VLM score
- `video.describe_image` — standalone image description
- `video.search_image` — reference image -> text search phrase
- `video.analyze_frame` — one sampled frame of a longer clip
- `video.record_analysis` — persist analysis summary to SQLite
- `video.history` + `video.history_get` — browse past analyses
- `video.backends` — which models, deps, VLM backends are up

**New: demo/web/video_studio.html** (~550 lines)

Three tabs under the shared Arikizu header:

- Video file: upload clip or drag-drop, text prompt OR reference image,
  overlay toolbar (boxes, pose, mask, blur, labels), timeline with
  action events, HUD showing current-frame action + per-stage latency
- Webcam: live view with same overlays, text prompt for live VLM
  action matching, FPS counter, blur toggle on by default
- History: last 20 analyses

Device banner at the top of every page tells the user up front what
their hardware can and cannot do, before they hit "Run analysis" and
discover an OOM.

**New: scripts/download-video-models.sh**

Device-aware. `scripts/download-video-models.sh` fetches perception
models only (~22 MB). `--with-vlm` adds Qwen2.5-VL 3B GGUF + mmproj
(~2.7 GB). `--vlm-only` skips the perception stack. All URLs point at
canonical Hugging Face mirrors; no manual registry edits needed.

**New: workers/video_worker/tests/test_actions.py** (~130 lines, 11 tests)

Each action rule has a passing test with canned pose landmarks that
match the expected posture. One test asserts the "unknown" floor
behavior (bad input returns unknown, not a confident guess). One
regression test asserts ACTIONS_KNOWN and action_definitions stay in
sync.

**Updated:**

- README.md: new "Video Studio" section with the three-input-mode
  explanation, link to the demo, and the device-aware model note
- README.md: Mermaid architecture diagram now shows the Video Studio
  worker as a highlighted node with its four internal sub-components
  (Perception, Action, Scene, VLM) visible
- docs/AGENTS.md: new section 8 "Customize the Video Studio" with
  recipes for adding an action, swapping the VLM, adding a device
  profile, bringing your own perception backend
- docs/DEMOS.md: seven-step test plan from unit tests
  through hardware benchmark through end-to-end browser walkthrough
- docs/assets/architecture-glance.svg: re-rendered (217 KB)
- scripts/doctor.sh: new rows for the three main MediaPipe/SegFormer
  model files
- demo/web/index.html: 6th card added for Video Studio, diagnostics
  panel probes `video.backends`
- capabilities.toml: 12 new rows under a new `video` section
- workers/pyproject.toml: `video_worker` added to the uv workspace

**Explicitly out of scope** for this version (as requested):

- VideoJev (dropped; needs an NVIDIA GPU with bf16 and a separate server)
- Hard Ollama dependency (dropped; the POC's provider dropdown is replaced
  by auto-detection via video.backends)

Verified: 11/11 action unit tests pass under 100 ms. All six demo pages'
inline JS parses clean. Mermaid diagram renders to 217 KB SVG. Python
modules import cleanly without MediaPipe or llama-cpp installed (fails
soft, reports what's missing).

---

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
anyone would land on. Added `docs/AGENTS.md` as the single
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
