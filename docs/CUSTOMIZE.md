# Customize Arikizu

How to adapt Arikizu for your own project. Every recipe here is one or
two files changed; nothing requires understanding the whole codebase.

Table of contents:

1. [Swap a model](#1-swap-a-model) — use your own ONNX / GGUF file
2. [Add a capability](#2-add-a-capability) — a new worker handler the HTTP API exposes
3. [Add a new worker](#3-add-a-new-worker) — a whole new worker process
4. [Rebrand the UI](#4-rebrand-the-ui) — logo, name, colors
5. [Add a demo page](#5-add-a-demo-page) — your own HTML tool using the API
6. [Load your own data](#6-load-your-own-data) — sensors, cameras, feeds
7. [Deploy on a device](#7-deploy-on-a-device) — Pi, Jetson, server

Every recipe is standalone. You do not need to do them in order.

---

## 1. Swap a model

**Use case:** replace yolov8n with yolov8s for better detection, use a
larger GGUF for reasoning, drop in your own fine-tuned ONNX.

**Two ways:**

A) Drop the file into `models/` with a filename the worker already
   recognizes. The worker auto-discovers it.

| Worker    | Filenames it looks for                            |
| --------- | ------------------------------------------------- |
| vision    | `yolov8n.onnx`, `yolov8s.onnx`, `yolo*.onnx`     |
| audio     | `silero_vad.onnx`, `vad.onnx`                     |
| reasoning | first `*.gguf` file (any name)                    |

B) Point an env var at your file directly. This wins over
   auto-discovery.

```
export ARIKIZU_VISION_MODEL=/path/to/my-detector.onnx
export ARIKIZU_AUDIO_VAD_MODEL=/path/to/my-vad.onnx
export ARIKIZU_REASONING_GGUF=/path/to/my-llm.gguf
make run
```

**Catch:** the vision worker's inference pipeline expects YOLOv5/v8
output shape (one output tensor like `[1, 84, 8400]`). If your model
has a different shape, override `_run_inference` in
`workers/vision_worker/vision_worker/__main__.py` or write your own
worker (recipe 3).

---

## 2. Add a capability

**Use case:** your project needs a specific thing — grade an answer,
classify a signal, run your library's own API. You want it available
over HTTP so your UI and any script can call it.

Pick the worker that fits (vision, audio, docs, reasoning, timeseries,
guard, eval, memory, test) or add a new one (recipe 3). Then:

### Step 1: register the capability

Edit `capabilities.toml`:

```toml
[your_capability]
name = "your.capability"           # dotted name used in the HTTP path
worker = "vision"                  # which worker handles it
input = { arg1 = "string", arg2 = "number" }
output = "object"
timeout_ms = 30000
priority = 0
```

### Step 2: write the handler

In the worker's `__main__.py`:

```python
@worker.handler("your.capability")
def your_capability(arg1: str = "", arg2: float = 0.0) -> dict[str, Any]:
    # Your work here. Return a dict.
    return {"result": arg1.upper(), "count": int(arg2 * 2)}
```

### Step 3: use it

```
curl -X POST http://127.0.0.1:7000/api/v1/call/your/capability \
  -H 'content-type: application/json' \
  -d '{"payload": {"arg1": "hello", "arg2": 3}}'
```

Every call automatically logs to the audit DB, so your capability
shows up on the operator dashboard with no extra wiring.

---

## 3. Add a new worker

**Use case:** you have your own library (your SightRAG, Sonarwise, a
scikit-learn model, a C extension) and you want it as its own worker
process so it starts and crashes independently.

### Step 1: scaffold

```
cd workers
cp -r test_worker my_worker
```

Edit `workers/my_worker/pyproject.toml`:
- Rename `[project] name = "my-worker"`
- Rename the package dir from `test_worker/` to `my_worker/`
- Add your library's deps

### Step 2: write handlers

In `workers/my_worker/my_worker/__main__.py`:

```python
from arikizu_worker import Worker
import asyncio

def main():
    worker = Worker("my")   # worker name used in capabilities.toml

    @worker.handler("my.predict")
    def predict(input_text: str = "") -> dict:
        # Call YOUR library here
        from your_library import YourModel
        model = YourModel.load()
        return {"prediction": model(input_text)}

    @worker.handler("my.backends")
    def backends() -> dict:
        return {"loaded": True, "model": "yours"}

    asyncio.run(worker.run())

if __name__ == "__main__":
    main()
```

### Step 3: register in `capabilities.toml`

```toml
[my_predict]
name = "my.predict"
worker = "my"
input = { input_text = "string" }
output = "object"
timeout_ms = 30000
```

### Step 4: register in workspace

Add `"my_worker"` to the `members` list in `workers/pyproject.toml`,
then `cd workers && uv sync` to install.

### Step 5: run

```
make run
```

The supervisor sees `worker = "my"` in capabilities.toml and auto-
spawns the worker. Your handlers are reachable at
`/api/v1/call/my/predict`.

---

## 4. Rebrand the UI

**Use case:** customer-facing demo under your own brand.

### Logo and name

Replace `demo/web/logo.png` with your 128×128 PNG. The hub and every
demo page already reference `/demo/logo.png`.

The title appears in two places per page: the browser `<title>` tag
and the header `<strong>` block. Grep for `Arikizu` across
`demo/web/*.html` and `ui/static/index.html`:

```
cd demo/web && grep -l Arikizu *.html
```

### Colors

Every page defines the palette as CSS tokens in the top of its
`<style>` block:

```css
:root {
  --bg: #faf9f4;      /* page background */
  --fg: #1a1a1a;      /* text */
  --card: #ffffff;    /* panels */
  --border: #e8e6df;
  --accent: #c75c2a;  /* buttons, links, highlights */
  --muted: #6b6b6b;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#1a1a14; --fg:#f0f0ec; --card:#23231c;
          --border:#2f2f26; --accent:#e07a4a; --muted:#9b9b96; }
}
```

Change `--accent` and the whole UI follows. The pages share this
palette; swap it once per page or write a script to sync them.

### Operator dashboard

The dashboard lives at `ui/static/index.html`. It's a standalone HTML
file with the same token system. Edit for the same effect.

---

## 5. Add a demo page

**Use case:** a specific tool for your users — a signal classifier UI,
an inspection form, a custom chart.

Copy any demo page as a starting point:

```
cp demo/web/timeseries_view.html demo/web/my_tool.html
```

Keep the shared header snippet so it stays consistent with the rest:

```html
<header class="app-header">
  <a href="/demo/" class="home">
    <img src="/demo/logo.png" alt=""><strong>Arikizu</strong>
  </a>
  <span class="sep">/</span>
  <span class="page">My Tool</span>
</header>
```

Call your capability from JavaScript:

```js
const r = await fetch("/api/v1/call/my/predict", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ payload: { input_text: "hello" } }),
});
const b = await r.json();
```

Add a card for your page on the hub (`demo/web/index.html`), inside
the `<div class="grid" id="views">`:

```html
<a class="card" href="/demo/my_tool.html">
  <h3>My Tool <span class="badge">live</span></h3>
  <p>What your tool does, in one sentence.</p>
  <span class="pill">my.predict</span>
</a>
```

Pages served from `demo/web/` are automatically available under
`/demo/` by the HTTP server. No build step.

---

## 6. Load your own data

### Browser-side upload

The timeseries page shows the pattern: file input, parse in JS, send
the result as the payload. See
`demo/web/timeseries_view.html` for CSV / TSV / JSON / XLSX parsing.

### Server-side file at a known path

Pass `file_path` in the payload. The worker reads it from disk. Use
when the file is already on the device:

```js
fetch("/api/v1/call/vision/detect", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ payload: {
    image_path: "/var/lib/my-app/latest.jpg",
    confidence: 0.3,
  }}),
});
```

### Browser camera / microphone

See `demo/web/vision_live.html` (webcam → base64 JPEG → vision.detect)
and `demo/web/audio_view.html` (mic → PCM array → audio.vad). The
Rust HTTP layer accepts base64 image payloads and PCM number arrays
directly.

### LAN sensor stream

If your sensors push to a MQTT broker, a TCP socket, or a file watcher,
write a small worker (recipe 3) that reads them and calls other
workers. The audit DB will record every call it makes.

---

## 7. Deploy on a device

Per-device walkthroughs are in `docs/SETUP.md`:

- Raspberry Pi 4 / 5 (`setup-rpi.sh` wrapper, cross-build via `scripts/build-aarch64.sh`)
- NVIDIA Jetson (CUDA + TensorRT ONNX provider)
- Mac Apple Silicon (CoreML provider)
- Linux x86_64 server (default)
- Windows via WSL2 (what you are probably on right now)

The runtime binary is one static Rust executable plus the Python
workers. Models in `models/` are read on startup; swap them without
rebuilding.

---

## 8. Customize the Video Studio

The video worker is the most composable of the Arikizu workers because it
plugs several things together. Four common customizations:

**Add a new action to the recognizer.** Open
`workers/video_worker/video_worker/actions.py`. Each action is a function
`is_<name>(pose, ...) -> (confidence, evidence)`. Add yours, register it
in `recognize()`'s `scores` dict and in `ACTIONS_KNOWN`, add a test in
`workers/video_worker/tests/test_actions.py`. Hot-reload by restarting
the worker.

**Swap the VLM.** Qwen2.5-VL 3B is the default. For something smaller:
MiniCPM-V 2.6, Moondream2, SmolVLM. Edit `models.py` REGISTRY to add the
GGUF + mmproj URLs for the new model, then `ARIKIZU_VLM_MODEL=<key>` picks
it. For a hosted VLM: set `ARIKIZU_VLM_ENDPOINT=http://your-server/v1/chat/completions`
and the worker uses that instead of local inference.

**Add a device profile.** `devices.py` has a `_FIT_TABLE` with one row per
model per device class. If your target hardware is not covered, add a new
entry to `_detect_device_class()` and add rows in each model's fit map.
UI reads this on page load and uses it to pick the preset.

**Use your own perception backend.** `MediaPipePerception` is one implementation.
Any class that provides `process(rgb_image) -> FrameResult` works. Set
`PERCEPTION_BACKEND=my_module:MyBackend` (as in the POC we based this on)
and the worker uses yours.

---

## Where things live

```
arikizu/
  Cargo.toml             Rust workspace (9 crates)
  capabilities.toml      Capability registry (recipe 2)
  arikizu.yaml.example   Optional per-worker overrides
  crates/
    ant-supervisor/      Worker lifecycle + IPC
    ant-http/            HTTP server + audit log
    ant-router/          Capability dispatch
    ant-cli/             `arikizu run` entrypoint
    ant-ipc/             MessagePack over Unix socket
    ant-models/          Device detection, model picker
    ant-devices/         Hardware inventory
    ant-feedback/        Event bus
    ant-common/          Shared types
  workers/
    pyproject.toml       uv workspace root
    arikizu-worker-sdk/  Base Worker class (recipe 3)
    vision_worker/       YOLOv8 ONNX, detect + segment
    audio_worker/        Silero VAD + keyword spot
    docs_worker/         PDF / text extraction
    reasoning_worker/    GGUF LLM + builtin KB
    timeseries_worker/   Forecast + anomaly detection
    guard_worker/        PII scan + redact
    eval_worker/         Prediction scoring
    memory_worker/       Session memory
    test_worker/         Minimal echo worker (scaffolding start)
  models/                yolov8n.onnx, silero_vad.onnx ship here
  demo/
    web/                 All demo HTML pages
    fixtures/            Sample images, audio, CSV, text
  ui/
    static/              Operator dashboard
  scripts/
    doctor.sh            Diagnostic (recipe before customization)
    download-default-models.sh
    export_yolo_onnx.py  Local yolov8n export via ultralytics
```

Any file above is yours to change. The project is Apache 2.0.
