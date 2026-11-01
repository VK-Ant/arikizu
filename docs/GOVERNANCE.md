# Responsible AI by architecture

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
