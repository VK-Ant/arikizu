# Custom Pipelines (YAML)

**This is how you build your own logic in Arikizu without writing Python.**

A pipeline is a YAML file that chains Arikizu capabilities together.
You pick a trigger (what starts it), name the stages (what runs), and
each stage's output can feed the next stage's input. The runtime
handles execution, policy enforcement, and audit logging.

## Why this exists (and why you might not need it)

**If you only call one capability at a time, you don't need pipelines.**
The HTTP API, a Python app, or an agent is enough.

Use pipelines when you want to compose several capability calls into
one unit of work that:
- Runs on a schedule (every 5 minutes, every night at 2am, every hour)
- Chains outputs together without writing a Python wrapper
- Needs a human approval step in the middle
- Should log the full chain to the audit database as one event

If none of those apply, skip the pipeline worker. Everything else in
Arikizu works without it.

## To enable the pipeline worker

1. In `arikizu.yaml`, uncomment the `pipeline` block in the `workers:` list.
2. Rename `_hello.yaml.example` to `hello.yaml` (drop the leading
   underscore AND the `.example` suffix). This is the demo pipeline;
   skip if you want to start from scratch.
3. `make run` (or restart the supervisor).

Files starting with `_` or `.` are deliberately skipped so the demo
sits dormant until you ask for it.

## What works today vs. roadmap

| Feature | Status |
|---------|--------|
| Load `pipelines/*.yaml` (one or many per file via `---`) | **Working** |
| Manual trigger via `POST /api/v1/call/pipeline/run` | **Working** |
| Schedule trigger (cron, 5- or 6-field) | **Working** |
| Sequential stages with `inputs`, `when:`, `on_error:` | **Working** |
| Template substitution: `{{inputs.x}}`, `{{stage.field}}`, filters, expressions | **Working** |
| Meta-capabilities: `pipeline.filter`, `pipeline.delay`, `pipeline.classify` | **Working** |
| Action: `audit` (writes to audit log) | **Working** |
| Action: `webhook` (POST to a URL) | **Working** |
| `pipeline.list` + `pipeline.reload` capabilities | **Working** |
| Event trigger (fire from internal event bus) | Roadmap |
| File-watch trigger (new file in a folder) | Roadmap |
| Webhook trigger (receive a POST) | Roadmap |
| Action: `email`, `sms` | Roadmap (shape returned; call is not wired) |

**Hello-world ships in the box.** `pipelines/hello.yaml` fires both
manually and every 5 minutes. Try it:

    curl -X POST http://127.0.0.1:7000/api/v1/call/pipeline/run \
      -H 'content-type: application/json' \
      -d '{"payload": {"name": "hello", "inputs": {"who": "VK", "language": "ta"}}}'

If YAML can express it, use YAML. When you need branching, loops, or
custom math that YAML can't do cleanly, drop into Python by writing a
worker (see `workers/`).

## When to use a pipeline vs. a worker vs. an agent

| You want to | Use |
|-------------|-----|
| Chain existing capabilities in order | **Pipeline (YAML)** |
| Add a new ML model or custom algorithm | **Worker (Python)** |
| Give an LLM the capabilities as tools and let it pick | **Agent (JSON)** |

Pipelines are deterministic. Agents reason. Workers run everything else.

## Pipeline grammar

```yaml
name: my_pipeline         # required: unique id
description: ...          # optional: what this does

trigger:                  # optional: what fires it. Default: manual
  type: schedule          # schedule | event | manual | webhook
  cron: "*/5 * * * *"     # for schedule
  event: video.detection  # for event
  path: /tmp/incoming     # for file-watch

inputs:                   # optional: variables you can use with {{var}}
  camera: cam_a
  threshold: 0.7

stages:                   # the ordered list of steps
  - name: step1
    capability: vision.detect
    inputs:
      image_path: /tmp/latest.jpg
      confidence: "{{threshold}}"
    when: always          # always | if (expression)
    on_error: continue    # continue | abort | retry

  - name: step2
    capability: reasoning.summarize
    inputs:
      text: "{{step1.detections | length}} items found"

actions:                  # optional: what to do with results
  - type: audit
    message: "{{name}} finished with {{step1.detections | length}} detections"
  - type: webhook
    url: https://example.com/alert
    payload: "{{step2.summary}}"
    when: "{{step1.detections | length}} > 0"
```

### What you can reference

Inside a stage's `inputs` and `when`:
- `{{inputs.foo}}` — pipeline-level inputs
- `{{<stage_name>.<field>}}` — any field from a previous stage's output
- Jinja2-style filters: `| length`, `| default("x")`, `| upper`

### Available capabilities

Every capability declared in `capabilities.toml` is callable from a
pipeline. The common ones:

| Capability | Does |
|------------|------|
| `vision.detect` | YOLOv8 object detection on an image |
| `vision.pose` | MediaPipe pose landmarks |
| `video.live_detect` | Live frame detect + pose + action rule |
| `video.segment_at_point` | Click-to-segment at a (x,y) point |
| `audio.transcribe` | Whisper transcription |
| `audio.vad` | Silero VAD on a wav file |
| `docs.extract` | Text + tables from PDF/DOCX |
| `docs.redact` | PII redaction |
| `reasoning.summarize` | Local LLM summarization |
| `reasoning.answer` | Local LLM Q&A over documents |
| `timeseries.forecast` | WavqWise forecasting |
| `timeseries.anomaly` | Anomaly detection on a signal |
| `guard.scan` | AntGuard safety/privacy scan |
| `memory.update` | Store context for later recall |
| `feedback.approve` | Human approval gate |

Run `curl http://127.0.0.1:7000/api/v1/capabilities` for the live list.

## Triggers

### Schedule
```yaml
trigger:
  type: schedule
  cron: "0 */4 * * *"    # every 4 hours
```

### Event (from another pipeline, worker, or external POST)
```yaml
trigger:
  type: event
  event: video.action_detected    # fires when a worker emits this event
```

### File watch (new file lands in a folder)
```yaml
trigger:
  type: event
  path: /mnt/cameras/incoming/*.jpg
```

### Webhook (POST hits the HTTP router)
```yaml
trigger:
  type: webhook
  path: /hooks/my-pipeline
  secret: "${WEBHOOK_SECRET}"      # env var from arikizu.yaml
```

### Manual (CLI or API)
```bash
curl -X POST http://127.0.0.1:7000/api/v1/pipeline/run \
  -d '{"name": "my_pipeline"}'
```

## Policies apply

Every capability call made from a pipeline goes through the same
policy enforcement as a call from the UI or an agent. If a stage calls
a capability set to `ask`, the pipeline pauses on the approval queue
until a human approves or rejects it. See the `feedback.approve` stage
in `examples/safety-alert.yaml` for an explicit human gate.

## Install your pipeline

Drop the YAML in `pipelines/` or a folder of your choice, then
reference it from your `arikizu.yaml`:

```yaml
pipelines:
  dir: ./pipelines
  autoload: true
```

Or load one explicitly:

```bash
arikizu pipeline load pipelines/examples/safety-alert.yaml
```

Reload without restart: `arikizu pipeline reload`.

## Examples

See [`examples/`](examples/) for working pipelines:

- `safety-alert.yaml` — hard-hat check on factory camera, Slack alert
- `invoice-qa.yaml` — PDF invoice extract + totals check + flag
- `elder-care.yaml` — fall detection on home camera, SMS to family
- `sensor-triage.yaml` — IoT signal anomaly + forecast + escalation
- `retail-count.yaml` — people count + dwell time per hour

Each one is 20-50 lines of YAML. Copy, rename, change the camera path
or signal source, done.
