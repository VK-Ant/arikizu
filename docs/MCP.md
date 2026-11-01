# MCP server: external agents calling Arikizu

Arikizu ships a Model Context Protocol server at
[`mcp/arikizu_mcp_server.py`](../mcp/arikizu_mcp_server.py) that exposes
a safe subset of its capabilities as MCP tools. External agents (Claude
Code, Cline, Cursor, your own agent framework) can connect and call
Arikizu as a standard tool server.

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

## Wire it up to Claude Code

Add to your project's `.mcp.json` (or user-level `~/.claude.json`):

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

Restart Claude Code. The Arikizu tools now appear in the tool list.

## Wire it up to Cline / Cursor

Same JSON block, placed in Cline's settings UI or Cursor's MCP
configuration file.

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

Or just test via Claude Code: run a prompt that would need Arikizu
("find anyone in the kitchen webcam without a hard hat"). Claude Code
picks up `video_live_detect`, calls it, reports.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tool returns `HTTP 503` | Arikizu isn't running. `make run`. |
| Tool returns `HTTP 404` | Capability not registered. Check `capabilities.toml`. |
| "capability not exposed over MCP" | Add it to `MCP_ALLOWED_CAPABILITIES`. |
| External agent cannot see Arikizu tools | Check `.mcp.json` path is absolute, restart agent host. |
| Everything deny-policied | External agents hit the GLOBAL policy, not an agent-specific one. See `workers/agent_worker/agent_worker/policy.py#DEFAULT_POLICY`. |
