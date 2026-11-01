"""Unit tests for policy + tool-call extraction. No HTTP, no DB.

These exercise the governance core: given a capability and an agent policy,
is it allowed, does it need approval, or is it denied? And can we parse
the model's <tool_call> blocks correctly?
"""
from __future__ import annotations

from agent_worker import policy
from agent_worker.tools import extract_tool_calls


def test_default_auto():
    d = policy.decide("reasoning.answer")
    assert d.action == "auto"
    assert not d.requires_approval
    assert not d.denied


def test_default_ask():
    d = policy.decide("memory.update")
    assert d.action == "ask"
    assert d.requires_approval
    assert not d.denied


def test_hard_deny_cannot_be_overridden():
    d = policy.decide("feedback.approve", {"feedback.approve": "auto"})
    assert d.action == "deny"
    assert d.denied


def test_unknown_cap_defaults_to_deny():
    d = policy.decide("some.random.capability")
    assert d.action == "deny"
    assert d.denied


def test_per_agent_policy_overrides_default():
    # memory.update is "ask" by default. Agent policy relaxes to "auto".
    d = policy.decide("memory.update", {"memory.update": "auto"})
    assert d.action == "auto"


def test_per_agent_policy_can_tighten():
    # reasoning.answer is "auto" by default. Agent policy tightens to "ask".
    d = policy.decide("reasoning.answer", {"reasoning.answer": "ask"})
    assert d.action == "ask"
    assert d.requires_approval


def test_allowed_capabilities_grouping():
    caps = policy.allowed_capabilities()
    assert "auto" in caps
    assert "ask" in caps
    assert "deny" in caps
    # feedback.approve must appear in deny (hard-deny)
    assert "feedback.approve" in caps["deny"]
    # reasoning.answer must be auto by default
    assert "reasoning.answer" in caps["auto"]


def test_validate_policy_rejects_bad_action():
    problems = policy.validate_policy({"reasoning.answer": "yes"})
    assert any("unknown action" in p for p in problems)


def test_validate_policy_rejects_override_of_hard_deny():
    problems = policy.validate_policy({"feedback.approve": "auto"})
    assert any("deny-list" in p for p in problems)


def test_extract_single_tool_call():
    text = (
        "I'll check the camera for you.\n"
        '<tool_call>{"capability": "video.live_detect", "payload": {"image_base64": "abc"}}</tool_call>\n'
        "Here's what I found."
    )
    prose, calls = extract_tool_calls(text)
    assert "check the camera" in prose
    assert len(calls) == 1
    assert calls[0]["capability"] == "video.live_detect"
    assert calls[0]["payload"] == {"image_base64": "abc"}


def test_extract_multiple_tool_calls():
    text = (
        '<tool_call>{"capability": "a.b"}</tool_call>'
        'middle text'
        '<tool_call>{"capability": "c.d", "payload": {"x": 1}}</tool_call>'
    )
    prose, calls = extract_tool_calls(text)
    assert len(calls) == 2
    assert calls[0]["capability"] == "a.b"
    assert calls[1]["capability"] == "c.d"
    assert calls[1]["payload"] == {"x": 1}


def test_extract_no_tool_calls():
    text = "Just a normal reply with no tool calls."
    prose, calls = extract_tool_calls(text)
    assert prose == text
    assert calls == []


def test_extract_malformed_tool_call_kept_as_prose():
    text = '<tool_call>not valid json</tool_call>'
    prose, calls = extract_tool_calls(text)
    assert calls == []
    assert "malformed tool call" in prose


def test_example_agents_import_shape():
    """Every shipped example agent in examples/agents/ must have the fields
    agent.import requires, and its policy must validate clean."""
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]  # project root
    examples_dir = root / "examples" / "agents"
    if not examples_dir.exists():
        import pytest
        pytest.skip("examples/agents not present (not a full checkout)")
    files = sorted(examples_dir.glob("*.json"))
    assert len(files) >= 5, f"expected >= 5 example agents, found {len(files)}"
    for f in files:
        definition = json.loads(f.read_text())
        assert "name" in definition and definition["name"].strip(), f"{f.name}: missing name"
        assert "system_prompt" in definition and definition["system_prompt"].strip(), \
            f"{f.name}: missing system_prompt"
        policy_entries = definition.get("policy", {})
        problems = policy.validate_policy(policy_entries)
        assert not problems, f"{f.name}: policy problems {problems}"
