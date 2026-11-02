# Agents, MCP, Governance, and Customization

Everything about Arikizu as an agentic platform: building custom agents, exposing capabilities over MCP to any external AI agent, the Responsible AI governance model, and how to customize the stack for your own org or hardware.

- [Part 1 — Custom agents](#part-1--custom-agents)
- [Part 2 — MCP server](#part-2--mcp-server)
- [Part 3 — Governance and Responsible AI](#part-3--governance-and-responsible-ai)
- [Part 4 — Customization guide](#part-4--customization-guide)

---

## Part 1 — Custom agents


Agents in Arikizu are chatbots you define that can call the system's own
capabilities as tools. You give an agent three things: a name, a system
prompt, and a policy. The policy decides which capabilities the agent
may call directly, which require human approval, and which are refused.

Every tool call lands in the audit log. Nothing can bypass that.

---

## What an agent is

Four fields:

```
id              auto-generated, stable
name            "Safety Inspector"
description     "Scans factory floor cameras for missing PPE"
system_prompt   "You are a factory floor safety inspector..."
policy          {capability: "auto" | "ask" | "deny"}
```

Agents are persistent (SQLite). Conversations with an agent are stored
turn by turn, including every tool call the agent made.

---

## Example: safety inspector

```
POST /api/v1/call/agent/create
{
  "payload": {
    "name": "Safety Inspector",
    "description": "Factory floor PPE compliance",
    "system_prompt": "You are a safety inspector. When the user asks about an area, call video.live_detect on the latest frame from that area's camera and tell them whether anyone is missing a hard hat. Reply in one or two sentences.",
    "policy": {
      "video.live_detect": "auto",
      "video.analyze_frame": "auto",
      "reasoning.answer": "auto",
      "memory.update": "ask"
    }
  }
}
```

Then chat with it:

```
POST /api/v1/call/agent/chat
{
  "payload": {
    "agent_id": "agent_abc123...",
    "message": "Is anyone on line 3 missing a hard hat?"
  }
}
```

The reasoning model sees the system prompt, the user message, and the
list of allowed capabilities. If it decides to call
`video.live_detect`, it emits a tool_call block. The agent worker
dispatches that through the policy module, forwards the call to the
Arikizu HTTP router, and feeds the result back for the model to
summarize.

---

## Policy: auto, ask, deny

Three actions per capability per agent:

- **auto**: the call runs immediately, logged to audit.
- **ask**: the call is queued for human approval. The chat turn
  returns `awaiting_approval` and the operator sees an approval card.
- **deny**: the call is refused before it reaches the worker. Logged
  as a policy denial.

If a capability is not listed in the agent's policy, the default comes
from `DEFAULT_POLICY` in `workers/agent_worker/agent_worker/policy.py`.
If it's not in that either, it defaults to **deny**. Adding a new
worker never silently grants agents access to it.

### Hard-deny list

Some capabilities are hard-denied for every agent regardless of policy:

```python
HARD_DENY = {
    "feedback.approve",     # agent cannot approve its own actions
    "feedback.reject",
    "arikizu.shutdown",
    "arikizu.restart",
    "arikizu.policy.set",
}
```

An agent policy that tries to override these is validated as invalid.

### Default policy highlights

| Pattern | Default | Why |
|---|---|---|
| `vision.*`, `video.live_*`, `audio.*`, `docs.*`, `timeseries.*` (reads) | **auto** | Read-only, no external side effects |
| `reasoning.*` | **auto** | Pure LLM calls, no side effects |
| `memory.update`, `memory.reward`, `video.record_analysis` | **ask** | Mutates state the operator may want to see first |
| `feedback.approve`, `feedback.reject` | **deny** (hard) | An agent cannot approve its own calls |
| `arikizu.*` (platform control) | **deny** (hard) | Not for agents |

Any capability can be tightened per agent (`"reasoning.answer": "ask"`
makes the agent always wait for a human). Capabilities on the hard-deny
list cannot be relaxed.

---

## Tool call protocol

The agent's system prompt is appended with the list of allowed
capabilities and this instruction:

> To call a tool, emit a block exactly like:
> `<tool_call>{"capability": "worker.operation", "payload": {...}}</tool_call>`

The agent worker extracts every tool_call block, dispatches each
through policy, and feeds results back as `TOOL <capability> OK/DENIED/
AWAITING_APPROVAL: <result>` for the next LLM turn. Up to 3 iterations
per user message (configurable via `max_iterations`), so an agent can
chain calls: detect → check memory → answer.

---

## Governance in practice

- Every chat turn creates an audit row per tool call with:
  `(agent_id, capability, payload, decision, result, timestamp)`
- An `ask` decision produces an approval card the operator sees in the
  dashboard; the agent's next chat turn can read the resolution via
  `feedback.pending` and resume.
- A `deny` decision is logged with the reason. The agent's response to
  the user says the tool was denied; the agent cannot retry it under
  a different name because policy keys use the exact capability name.

---

## Agent Studio

The browser demo at `/demo/agent_studio.html` is the full management UI:

- Left: list of agents, create/edit/delete
- Center: chat with the selected agent, with tool call records
  attached to each assistant message showing capability + policy
  decision + result
- Right: live policy panel showing which capabilities are auto, ask,
  deny for the selected agent

---

## MCP server for external agents

If instead you want an EXTERNAL AI agent to call Arikizu, use the MCP
server at
[`mcp/arikizu_mcp_server.py`](../mcp/arikizu_mcp_server.py). See
[`docs/AGENTS.md`](AGENTS.md) for the setup.

The MCP server exposes a safe subset of capabilities as MCP tools. All
calls still route through the Arikizu HTTP router, so policy and audit
apply. External agents cannot bypass governance.

---

## Part 2 — MCP server


Arikizu ships a Model Context Protocol server at
[`mcp/arikizu_mcp_server.py`](../mcp/arikizu_mcp_server.py) that exposes
a safe subset of its capabilities as MCP tools. Any MCP-compatible
external agent can connect and call Arikizu as a standard tool server.
Ready-to-use config snippets for popular clients are in
[`examples/mcp-configs/`](../examples/mcp-configs/).

## Why

- The Agent Studio inside Arikizu is for custom agents that LIVE in
  Arikizu.
- The MCP server is for agents that live ELSEWHERE and want to use
  Arikizu's local-first perception, documents, reasoning, time series,
  and guard capabilities as tools in their own workflow.

Both paths go through the same governance layer (audit log + policy +
approval queue).

---

## Install the Python side

```
pip install mcp httpx
```

The MCP server is a thin stdio adapter. It does not need a separate
daemon; the agent host runs it on demand.

---

## Wire it up to an external agent

Add the following block to the MCP config file of your AI agent client
(each client's own docs will tell you where that file lives, typically
`.mcp.json` at a project root or a per-user settings file):

```json
{
  "mcpServers": {
    "arikizu": {
      "command": "python3",
      "args": ["/absolute/path/to/arikizu/mcp/arikizu_mcp_server.py"],
      "env": {"ARIKIZU_HTTP": "http://127.0.0.1:7000"}
    }
  }
}
```

Restart the client. The Arikizu tools now appear in its tool list.

Ready-to-use config files for popular clients are in
[`examples/mcp-configs/`](../examples/mcp-configs/).

## Wire it up to any MCP-aware agent

The server speaks standard MCP over stdio. Any agent framework that can
spawn an MCP child process and talk the protocol will work.

---

## Which capabilities are exposed

The whitelist is in `mcp/arikizu_mcp_server.py#MCP_ALLOWED_CAPABILITIES`.
Currently 17 capabilities covering:

- Perception: `video_live_detect`, `video_analyze_frame`,
  `video_live_describe`, `video_describe_image`, `video_search_image`,
  `video_recognize_pose`, `video_actions_known`, `video_device_report`,
  `vision_detect`
- Audio: `audio_vad`, `audio_keyword_spot`
- Documents: `docs_extract`
- Time series: `timeseries_forecast`, `timeseries_detect_anomaly`
- Reasoning: `reasoning_answer`, `reasoning_summarize`
- Guard: `guard_scan`, `guard_redact`

Capabilities not on this list are refused by the MCP server even if the
external agent asks for them. These include `agent.chat` (don't nest
agents), `memory.update` (long-term state should go through a policy
decision), `feedback.approve` (hard-denied platform-wide), and anything
under `arikizu.*` (platform control).

To add a capability to the MCP whitelist, edit `MCP_ALLOWED_CAPABILITIES`
and restart the MCP child process (the agent host usually does this
automatically on config reload).

---

## Governance across the boundary

The MCP server does not re-implement governance. Every call forwarded
from an external agent lands on the HTTP router, which:

1. Applies the global policy (hard-deny list)
2. Writes the audit row
3. Routes to the owning worker
4. Returns the response or the policy decision

If a capability is `ask`-policy for an agent that uses the MCP interface,
the external agent receives a response indicating "awaiting human
approval". The external agent should surface this to its user. The
operator approves the call via the Arikizu operator dashboard, and the
external agent can poll `feedback.pending` to resume.

---

## Testing the MCP server manually

```
# One terminal: run Arikizu
make run

# Another terminal: run the MCP server by hand
export ARIKIZU_HTTP=http://127.0.0.1:7000
python3 mcp/arikizu_mcp_server.py

# The server waits on stdin. Type an MCP JSON-RPC request:
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

The server replies with the tool list over stdout.

Or just test from the external agent client you wired up: run a prompt
that would need Arikizu ("find anyone in the kitchen webcam without a
hard hat"). The client picks up `video_live_detect`, calls it, reports.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tool returns `HTTP 503` | Arikizu isn't running. `make run`. |
| Tool returns `HTTP 404` | Capability not registered. Check `capabilities.toml`. |
| "capability not exposed over MCP" | Add it to `MCP_ALLOWED_CAPABILITIES`. |
| External agent cannot see Arikizu tools | Check `.mcp.json` path is absolute, restart agent host. |
| Everything deny-policied | External agents hit the GLOBAL policy, not an agent-specific one. See `workers/agent_worker/agent_worker/policy.py#DEFAULT_POLICY`. |

---

## Part 3 — Governance and Responsible AI


Arikizu's answer to Responsible AI is not a governance layer bolted on
after the fact. It is the shape of the system.

Four claims make it work:

1. **Local-first.** The data your capabilities see never leaves the
   device. There is no cloud API round-trip to govern, so the
   governance surface is small and local.
2. **Every call auditable.** Every capability call, from every source
   (browser, agent, MCP, CLI) lands in the same SQLite audit log with
   agent identity, payload, policy decision, result, and timestamp.
3. **Every risky call gated.** The policy module decides per capability
   whether an agent runs it, waits for approval, or is refused.
   Approval requests surface in the operator dashboard.
4. **Every call reversible or correctable.** The feedback worker gives
   the operator a one-click path to rate, correct, or reject any call
   after the fact, with the correction routed back to the owning worker.

The audit log + policy + feedback form a loop. Governance is a ring
around the whole runtime, not a layer per worker.

---

## How governance applies to each entry point

| Entry point | Governed by |
|---|---|
| Browser | Per-user policy (future); for now the UI is trusted but every call is still audited |
| CLI | Same as the browser; local-user trust |
| Internal custom agent | **Per-agent policy** (auto / ask / deny per capability), plus audit |
| External MCP agent | **Global policy** (default `DEFAULT_POLICY`), plus audit |
| Scheduled task | Same as the agent that owns the task |

An internal agent's policy is defined when the agent is created and can
be edited any time. An external MCP agent uses the global default; the
MCP whitelist (`MCP_ALLOWED_CAPABILITIES`) is a second gate on top.

---

## Hard-deny: things no policy can enable

Some capabilities are refused for every agent regardless of what the
per-agent policy says:

- `feedback.approve`, `feedback.reject` — an agent must never approve
  its own actions. A human has to.
- `arikizu.shutdown`, `arikizu.restart` — platform control, not for
  agents.
- `arikizu.policy.set` — policy itself cannot be edited by an agent.

These are listed in one place:
`workers/agent_worker/agent_worker/policy.py#HARD_DENY`. Policy
validation refuses any agent definition that tries to override them.

---

## Per-agent policy: auto, ask, deny

Three decisions per capability, per agent:

- **auto**: run immediately, log to audit.
- **ask**: queue for human approval. The agent's chat turn returns
  `awaiting_approval` and the operator sees an approval card.
- **deny**: refuse before dispatch. Logged as a policy denial.

The dispatcher in `agent_worker/tools.py` applies these decisions
BEFORE forwarding to the HTTP router. A capability denied by policy
never runs; its payload is logged but no worker ever sees it.

---

## The audit log

One SQLite table, one row per call. Schema:

```
events(id, created_at, kind, source, worker, capability, agent_id,
       payload_json, response_json, decision, ms, bytes_in, bytes_out)
```

Writable from any worker via the shared audit sink. Readable from:

- `/api/v1/audit?limit=N` for the operator dashboard
- `GET /api/v1/call/video/history` for per-worker views
- `GET /api/v1/call/agent/conversation/<id>` for per-agent history

An audit row is never deleted by the application. If an operator wants
to purge data, they run a SQLite DELETE directly, and that act is
itself logged by the surrounding systemd/journal, not by Arikizu.

---

## Approval queue (ask-policy)

When an agent emits a tool call for an `ask`-policy capability, the
dispatcher creates an approval request. The operator sees it in the
dashboard:

```
Agent "Safety Inspector" wants to call video.record_analysis
  payload: {"video_name": "line3-camera", "events": [...]}
  [approve]  [reject]  [edit payload and approve]
```

Approve: the call runs, result flows back to the agent, agent resumes.
Reject: the call is refused, agent's next LLM turn sees "DENIED by
operator" and can respond to the user accordingly.
Edit: operator modifies the payload before approval.

The agent's loop pauses while waiting. A production deployment can
subscribe to approval events via WebSocket and surface them anywhere
(Slack, PagerDuty, email).

---

## Feedback: correction after the fact

Even for `auto`-policy calls that already ran, the operator can:

- `feedback.rate` — thumbs up or down on a specific call
- `feedback.correct` — attach the correct answer; routes into the
  golden set for future eval runs
- `feedback.annotate` — add a note the next agent run can read

Ratings and corrections feed into:

- The golden set at `golden/` for `eval.golden_run`
- The `memory` worker as weighted facts the next conversation can recall

---

## Running an audit

A compliance review is a SQL query:

```sql
-- All agent-triggered video calls last month
SELECT created_at, agent_id, capability, decision, ms
FROM events
WHERE kind = 'agent_tool_call'
  AND capability LIKE 'video.%'
  AND created_at > unixepoch('now', '-30 days')
ORDER BY created_at DESC;

-- Policy denials by capability
SELECT capability, COUNT(*) AS n
FROM events
WHERE decision = 'deny'
  AND created_at > unixepoch('now', '-7 days')
GROUP BY capability ORDER BY n DESC;

-- Who approved what
SELECT a.created_at, a.capability, a.agent_id,
       e.payload_json AS approval_payload
FROM events a
LEFT JOIN events e ON e.kind = 'approval' AND e.payload_json LIKE '%' || a.id || '%'
WHERE a.decision = 'ask' AND a.created_at > unixepoch('now', '-30 days');
```

The point: a regulator or a customer's security review runs ordinary
SQL on one file. There is no "query the audit vendor's API" story.

---

## Comparison to the cloud-API shape

Cloud API-based AI has governance after the fact:

- You send data to a provider; the provider audits in their logs.
- You configure policies in their UI; the provider enforces in their
  infra.
- You trust the provider's attestations about who saw what.

Arikizu moves these to the device:

- Data never leaves; no cross-trust-boundary audit needed.
- Policy is a Python file on your disk; you can diff it.
- Enforcement is one function call in one process you control.
- Audit is a SQLite file on your disk; you can grep it.

That is the Responsible-AI-by-architecture claim: the single most
powerful governance control is not sending the data to a cloud at all.
Everything else is a thin, local, auditable loop on top of that.

---

## Part 4 — Customization guide


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
