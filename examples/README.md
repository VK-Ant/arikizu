# Examples

Everything in this directory is a ready-to-use starting point. Clone it,
rename it, change the content, ship it. All MIT-friendly: the examples
themselves are Apache 2.0 like the rest of the project.

## What is here

```
examples/
├── agents/               Agent definitions you can import with one call
├── actions/              Custom action rules you can drop into video_worker
└── mcp-configs/          .mcp.json snippets for MCP-compatible agent clients
```

A blank HTML template for new demo pages lives at
[`../demo/web/_template.html`](../demo/web/_template.html).

---

## agents/

Five ready-to-import JSON agents covering real domains:

| File | Agent | Domain |
|---|---|---|
| `safety-inspector.json` | Safety Inspector | Factory floor PPE compliance |
| `elder-care-companion.json` | Elder Care Companion | Home monitoring for falls, inactivity |
| `document-reviewer.json` | Document Reviewer | Contract / invoice QA with PII redaction |
| `sensor-triage.json` | Sensor Triage | Time-series anomaly + forecast + escalation |
| `retail-floor.json` | Retail Floor Watcher | People count, dwell, queue detection |

**Import one into your running Arikizu:**

```bash
curl -X POST http://127.0.0.1:7000/api/v1/call/agent/import \
  -H 'content-type: application/json' \
  -d '{"payload": {"file_path": "examples/agents/safety-inspector.json"}}'
```

Or click **Import examples** in Agent Studio UI (`/demo/agent_studio.html`)
to load all five at once.

**Make your own.** Copy any of these JSON files, edit the `name`,
`system_prompt`, and `policy`, then import your copy. Each policy
entry is `auto` / `ask` / `deny` per capability.

---

## actions/

Custom action rules for Video Studio. These extend the 12 built-in
actions (walking, running, sitting, standing, waving, kicking, jumping,
hands_up, arms_crossed, bending, falling, pointing).

See `actions/README.md` for how to drop a new rule into
`workers/video_worker/video_worker/actions.py`. Each example is a
single Python function + a one-line test.

---

## mcp-configs/

Config snippets for popular MCP-compatible agent clients. One file per
client, each one a ready-to-paste `mcpServers` block. All assume
`ARIKIZU_HTTP=http://127.0.0.1:7000`; edit the path to point at your
Arikizu checkout.

If your client isn't listed, the shape is the standard MCP server
block, so you can adapt any of these.

---

## demo page template

A minimal HTML page with the shared Arikizu header and a blank body
you can fill in lives at
[`../demo/web/_template.html`](../demo/web/_template.html). Use it as
a starting point for a new demo page:

```
cp demo/web/_template.html demo/web/my_demo.html
# edit, open http://127.0.0.1:7000/demo/my_demo.html
```

---

## Customize deeper

The full customization guide is at [`../docs/AGENTS.md`](../docs/AGENTS.md).
Seven recipes with concrete code:

1. Swap a model
2. Add a capability
3. Add a new worker
4. Rebrand the UI
5. Add a demo page
6. Load your own data
7. Deploy on a device
8. Customize the Video Studio

Plus the agent + MCP + governance docs:

- [`../docs/AGENTS.md`](../docs/AGENTS.md): build custom agents
- [`../docs/AGENTS.md`](../docs/AGENTS.md): expose Arikizu to external agents
- [`../docs/AGENTS.md`](../docs/AGENTS.md): the Responsible AI story

---

## License

Apache 2.0. These examples are code you can read, fork, and ship with
your own product. Attribution appreciated but not required for the
examples themselves (the model files in `models/` keep their own
upstream licenses; see `models/NOTICE.md`).
