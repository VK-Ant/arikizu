"""Policy enforcement for agent capability calls.

Three decision outcomes per (agent_id, capability) pair:

  auto     The call goes through immediately, logged to audit.
  ask      The call is queued for human approval. The agent waits until
           an operator approves or rejects it via /api/v1/feedback/approve.
  deny     The call is refused before it reaches the worker. Logged to
           audit as a policy denial.

The policy table is stored per agent and editable at runtime via
agent.set_policy. Default policy for any capability not listed is "deny",
so adding a new worker never silently gives agents access to it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyDecision:
    """Result of consulting the policy for one capability call."""
    action: str                    # "auto" | "ask" | "deny"
    reason: str                    # one short line explaining the decision
    requires_approval: bool
    denied: bool


# -----------------------------------------------------------------------
# Sensible defaults for the capabilities we ship.
#
# Rule of thumb used here:
#   auto - read-only, no side effects outside the agent's own context
#   ask  - produces output a human will see, or touches external files
#   deny - mutates state the operator did not explicitly agree to
# -----------------------------------------------------------------------
DEFAULT_POLICY: dict[str, str] = {
    # Reasoning: always safe to let an agent think
    "reasoning.answer": "auto",
    "reasoning.summarize": "auto",
    "reasoning.complete": "auto",
    "reasoning.backends": "auto",

    # Vision: read-only, auto
    "vision.detect": "auto",
    "vision.segment": "auto",
    "vision.backends": "auto",

    # Video: perception auto, VLM scoring auto (local), analysis auto
    "video.live_detect": "auto",
    "video.analyze_frame": "auto",
    "video.live_describe": "auto",
    "video.describe_image": "auto",
    "video.search_image": "auto",
    "video.recognize_pose": "auto",
    "video.actions_known": "auto",
    "video.device_report": "auto",
    "video.backends": "auto",
    "video.history": "auto",
    "video.record_analysis": "ask",       # writes to history, operator should see

    # Audio: perception auto
    "audio.vad": "auto",
    "audio.transcribe": "auto",
    "audio.keyword_spot": "auto",
    "audio.backends": "auto",

    # Documents: extraction auto, upload is ask (external file)
    "docs.extract": "auto",
    "docs.search": "auto",

    # Timeseries: auto
    "timeseries.forecast": "auto",
    "timeseries.detect_anomaly": "auto",

    # Memory: read auto, write ask (shapes future agent behavior)
    "memory.recall": "auto",
    "memory.update": "ask",
    "memory.reward": "ask",

    # Guard: scan/redact auto, policy editing deny
    "guard.scan": "auto",
    "guard.redact": "auto",

    # Eval: auto
    "eval.score": "auto",
    "eval.compare": "auto",

    # Test: auto
    "test.echo": "auto",
    "test.add": "auto",

    # Feedback: ask (the agent should not quietly approve its own actions)
    "feedback.approve": "deny",
    "feedback.reject": "deny",
    "feedback.rate": "ask",
    "feedback.correct": "ask",
}


# High-risk capabilities that are ALWAYS denied for any agent, no matter
# what the per-agent policy says. These are listed here so the deny is
# visible, auditable, and in one place.
HARD_DENY: set[str] = {
    "feedback.approve",     # an agent cannot auto-approve its own call
    "feedback.reject",      # same for reject
    "arikizu.shutdown",     # future: supervisor control
    "arikizu.restart",
    "arikizu.policy.set",   # policy itself cannot be edited by an agent
}


def decide(capability: str, per_agent_policy: dict[str, str] | None = None) -> PolicyDecision:
    """Consult the policy for one capability call."""
    if capability in HARD_DENY:
        return PolicyDecision(
            action="deny", reason=f"{capability} is hard-denied by platform policy",
            requires_approval=False, denied=True,
        )
    per_agent_policy = per_agent_policy or {}
    choice = (per_agent_policy.get(capability)
              or DEFAULT_POLICY.get(capability)
              or "deny")
    if choice == "auto":
        return PolicyDecision("auto", "allowed by policy", False, False)
    if choice == "ask":
        return PolicyDecision("ask", "requires human approval", True, False)
    return PolicyDecision("deny",
                          f"{capability} not in agent's allowed capabilities "
                          "(default is deny; add it to the agent's policy to enable)",
                          False, True)


def allowed_capabilities(per_agent_policy: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Return the full policy effective for an agent, grouped by action."""
    merged: dict[str, str] = dict(DEFAULT_POLICY)
    if per_agent_policy:
        merged.update(per_agent_policy)
    out: dict[str, list[str]] = {"auto": [], "ask": [], "deny": []}
    for cap, choice in sorted(merged.items()):
        if cap in HARD_DENY:
            out["deny"].append(cap)
            continue
        out.setdefault(choice, out["deny"]).append(cap)
    return out


def validate_policy(per_agent_policy: dict[str, str]) -> list[str]:
    """Return a list of problems in the proposed policy, empty if clean."""
    problems: list[str] = []
    for cap, choice in per_agent_policy.items():
        if choice not in ("auto", "ask", "deny"):
            problems.append(f"capability {cap!r}: unknown action {choice!r} (must be auto/ask/deny)")
        if cap in HARD_DENY and choice != "deny":
            problems.append(
                f"capability {cap!r}: cannot override platform deny-list; "
                f"this capability is always refused"
            )
    return problems
