# Custom agents

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

If instead you want an EXTERNAL agent (Claude Code, Cline, Cursor,
your own) to call Arikizu, use the MCP server at
[`mcp/arikizu_mcp_server.py`](../mcp/arikizu_mcp_server.py). See
[`docs/MCP.md`](MCP.md) for the setup.

The MCP server exposes a safe subset of capabilities as MCP tools. All
calls still route through the Arikizu HTTP router, so policy and audit
apply. External agents cannot bypass governance.
