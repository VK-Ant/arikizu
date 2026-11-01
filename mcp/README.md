# Arikizu MCP server

Exposes Arikizu capabilities to external agents (Claude Code, Cline,
Cursor, your own agent) through the Model Context Protocol.

## What this gives you

Your agent calls `video_live_detect`, `audio_vad`, `reasoning_answer`,
`guard_scan` and the rest the same way it calls any MCP tool. Under the
hood, each call forwards to the Arikizu HTTP router. Audit logging,
policy enforcement, and the approval queue all apply.

The MCP server is a thin adapter. It does not bypass governance.

## Install

```
pip install mcp httpx
```

## Run

```
export ARIKIZU_HTTP=http://127.0.0.1:7000
python3 mcp/arikizu_mcp_server.py
```

The server speaks MCP over stdio. Hook it up to your agent host.

## Wire up for Claude Code

Add to `.mcp.json` at the root of a project (or your global
`~/.claude.json`):

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

Restart Claude Code. The Arikizu tools appear in the tools list.

## Wire up for Cline / Cursor

Same JSON block in Cline's settings or Cursor's MCP config.

## Which capabilities are exposed

By default, 17 capabilities covering perception, reasoning, documents,
time series, and guard. The full list is in
`arikizu_mcp_server.py#MCP_ALLOWED_CAPABILITIES`. Capabilities not on
this list (`agent.chat`, `memory.update`, `feedback.*`, policy
management) are NOT exposed over MCP because:

- `agent.chat`: you already have an agent; don't nest them.
- `memory.update`: the external agent should not be able to mutate
  Arikizu's long-term memory without passing through a policy decision.
- `feedback.approve` / `feedback.reject`: a hard-deny on the policy
  side; an agent must never approve its own actions.
- Policy editing: platform-level, not agent-level.

To add a capability to the MCP whitelist, edit the
`MCP_ALLOWED_CAPABILITIES` dict and restart the server.

## Governance notes

- Every tool call lands in `arikizu.db` as an audit row with the agent's
  identity, the capability called, the payload, the response, and the
  policy decision.
- An external agent cannot bypass hard-deny capabilities even if its
  user settings say otherwise. The deny is enforced by the HTTP router
  before the capability runs.
- `ask`-policy capabilities (currently `memory.update`, `memory.reward`,
  `feedback.rate`, etc.) will return `"awaiting_approval"` to the
  external agent, which should surface that to its user.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "capability not exposed over MCP" | Edit `MCP_ALLOWED_CAPABILITIES` and restart the server. |
| Tool returns HTTP 503 | Arikizu HTTP server isn't running. Start it with `make run`. |
| Tool returns HTTP 404 | The capability isn't registered. Check `capabilities.toml`. |
| Agent can see the tool but can't call it | Check `ARIKIZU_HTTP` env var points to a reachable Arikizu instance. |
