"""Capability dispatcher used by the agent chat loop.

An agent "tool call" is a (capability, payload) pair that the agent is
asking Arikizu to execute. We route each call through the policy module,
then forward to the Arikizu HTTP router (same surface the browser uses).

Keeping dispatch at the HTTP level (not direct IPC) means every tool call
goes through the Arikizu audit log and policy enforcement already in
ant-http, with no cross-worker shortcuts.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from . import policy
from .agents import ARIKIZU_HTTP

logger = logging.getLogger(__name__)


# Tool-call JSON format the reasoning model is asked to produce.
#
# The model is told to answer in prose, and when it needs Arikizu's help,
# emit a block like:
#
#   <tool_call>{"capability": "video.live_detect", "payload": {...}}</tool_call>
#
# Multiple tool calls can appear in one assistant turn. We extract them,
# dispatch each through policy, and feed the results back for the next turn.

TOOL_CALL_OPEN = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"


def extract_tool_calls(assistant_text: str) -> tuple[str, list[dict]]:
    """Split an assistant message into (prose, [tool_call, ...])."""
    tool_calls: list[dict] = []
    prose_parts: list[str] = []
    cursor = 0
    while True:
        start = assistant_text.find(TOOL_CALL_OPEN, cursor)
        if start < 0:
            prose_parts.append(assistant_text[cursor:])
            break
        prose_parts.append(assistant_text[cursor:start])
        end = assistant_text.find(TOOL_CALL_CLOSE, start + len(TOOL_CALL_OPEN))
        if end < 0:
            # Malformed: keep the rest as prose, give up on tool calls
            prose_parts.append(assistant_text[start:])
            break
        raw = assistant_text[start + len(TOOL_CALL_OPEN):end].strip()
        try:
            call = json.loads(raw)
            if isinstance(call, dict) and "capability" in call:
                tool_calls.append({
                    "capability": call["capability"],
                    "payload": call.get("payload", {}),
                })
        except json.JSONDecodeError:
            # Keep the raw text as prose so the user can see what happened
            prose_parts.append(f"[malformed tool call: {raw}]")
        cursor = end + len(TOOL_CALL_CLOSE)
    return "".join(prose_parts).strip(), tool_calls


def dispatch_one(capability: str, payload: dict,
                 agent_policy: dict[str, str] | None = None,
                 timeout_s: float = 60.0) -> dict[str, Any]:
    """Run one tool call through policy and (if allowed) through the HTTP API.

    Returns a dict with:
      - decision: "auto" | "ask" | "deny"
      - decision_reason: str
      - result: the capability's response (only if decision == "auto")
      - error: str (only on failure)
    """
    decision = policy.decide(capability, agent_policy)
    out: dict[str, Any] = {
        "capability": capability,
        "payload": payload,
        "decision": decision.action,
        "decision_reason": decision.reason,
    }
    if decision.denied:
        return out
    if decision.requires_approval:
        # The chat loop will surface this as "awaiting approval". A real
        # production flow would open an approval card; here we return the
        # decision and let the UI do the approval round-trip.
        out["awaiting_approval"] = True
        return out
    # Auto-approved: forward to the Arikizu HTTP router.
    url = f"{ARIKIZU_HTTP}/api/v1/call/{capability.replace('.', '/')}"
    try:
        r = httpx.post(url, json={"payload": payload}, timeout=timeout_s)
        if r.status_code >= 400:
            out["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
        else:
            try:
                out["result"] = r.json()
            except Exception:
                out["result"] = {"raw": r.text[:1000]}
    except httpx.RequestError as e:
        out["error"] = f"request failed: {e}"
    return out


def dispatch_all(tool_calls: list[dict],
                 agent_policy: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Dispatch every tool call in order, returning per-call results."""
    return [dispatch_one(c["capability"], c.get("payload", {}), agent_policy)
            for c in tool_calls]


def format_tool_results(results: list[dict]) -> str:
    """Format tool-call results for the next LLM turn."""
    lines: list[str] = []
    for r in results:
        cap = r["capability"]
        if r["decision"] == "deny":
            lines.append(f"TOOL {cap} DENIED: {r['decision_reason']}")
        elif r["decision"] == "ask":
            lines.append(f"TOOL {cap} AWAITING HUMAN APPROVAL: {r['decision_reason']}")
        elif "error" in r:
            lines.append(f"TOOL {cap} ERROR: {r['error']}")
        else:
            result_str = json.dumps(r.get("result", {}))[:800]
            lines.append(f"TOOL {cap} OK: {result_str}")
    return "\n".join(lines) if lines else "(no tool calls executed)"
