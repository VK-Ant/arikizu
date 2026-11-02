"""Template substitution tests. No worker, no HTTP."""
from __future__ import annotations

from pipeline_worker.template import render, resolve_one


def test_lookup_simple():
    ctx = {"inputs": {"name": "VK"}}
    assert resolve_one("inputs.name", ctx) == "VK"


def test_lookup_nested():
    ctx = {"step1": {"detections": [1, 2, 3]}}
    assert resolve_one("step1.detections", ctx) == [1, 2, 3]


def test_filter_length():
    ctx = {"step1": {"detections": ["a", "b", "c"]}}
    assert resolve_one("step1.detections | length", ctx) == 3


def test_filter_default():
    ctx = {"inputs": {}}
    assert resolve_one('inputs.name | default("friend")', ctx) == "friend"


def test_expression_boolean():
    ctx = {"step1": {"count": 5}}
    assert resolve_one("step1.count > 0", ctx) is True
    assert resolve_one("step1.count > 10", ctx) is False


def test_render_string_mixed():
    ctx = {"name": "pipeline_x", "step1": {"count": 7}}
    out = render("Pipeline {{name}} finished with {{step1.count}} items", ctx)
    assert out == "Pipeline pipeline_x finished with 7 items"


def test_render_single_expr_keeps_type():
    """When the entire string is one {{...}}, result preserves its type."""
    ctx = {"inputs": {"items": [1, 2, 3]}}
    out = render("{{inputs.items}}", ctx)
    assert out == [1, 2, 3]
    assert isinstance(out, list)


def test_render_nested_dict():
    ctx = {"inputs": {"camera": "cam_a"}, "step1": {"count": 2}}
    val = {"device": "{{inputs.camera}}", "has_detections": "{{step1.count > 0}}"}
    out = render(val, ctx)
    assert out["device"] == "cam_a"
    assert out["has_detections"] is True


def test_missing_key_returns_none():
    assert resolve_one("inputs.missing", {"inputs": {}}) is None


def test_eval_cannot_access_builtins():
    """Expressions must not be able to call open() or similar."""
    ctx = {}
    # If the sandbox leaks, this would try to read a file. We expect None
    # because __builtins__ is wiped.
    result = resolve_one("open('/etc/passwd')", ctx)
    assert result is None
