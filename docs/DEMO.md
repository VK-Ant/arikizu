# Demo walkthrough

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
[`MODELS.md`](MODELS.md)).

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

## What to show someone else

If you have ~5 minutes to demo Arikizu, go in this order:

1. Open `/` (operator dashboard). Point out the device chip and recent activity.
2. Click **Vision**. Show live annotated frames (or fixture).
3. Back to `/`, click **Documents**. Extract a field.
4. Back to `/`, click **Reasoning**. Ask one question.
5. Open `/demo/` (sandbox). Show that every one of those is a plain HTML
   file hitting the same `/api/v1/call/*` surface: no magic, no cloud.

That's the whole pitch: one binary, one device, every capability behind
one API, human-in-the-loop by default.
