"""Executor tests using the meta-capabilities and a monkey-patched HTTP call.

Keeps the test offline — no live Arikizu HTTP router needed.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from pipeline_worker import executor
from pipeline_worker.executor import _should_run, execute
from pipeline_worker.loader import Action, Pipeline, Stage, Trigger


def test_should_run_literals():
    assert _should_run("always", {}) is True
    assert _should_run("", {}) is True
    assert _should_run("never", {}) is False
    assert _should_run("false", {}) is False


def test_should_run_resolves_expression():
    assert _should_run("inputs.n > 0", {"inputs": {"n": 5}}) is True
    assert _should_run("inputs.n > 10", {"inputs": {"n": 5}}) is False


def test_meta_filter():
    p = Pipeline(name="t", stages=[
        Stage(name="s1", capability="pipeline.filter", inputs={"when": True}),
    ])
    r = asyncio.run(execute(p))
    assert r["ok"] is True
    assert r["stages"]["s1"]["passed"] is True


def test_meta_delay():
    p = Pipeline(name="t", stages=[
        Stage(name="s1", capability="pipeline.delay", inputs={"seconds": 0.01}),
    ])
    r = asyncio.run(execute(p))
    assert r["ok"] is True
    assert r["stages"]["s1"]["done"] is True


def test_meta_classify_default_rule():
    p = Pipeline(name="t", stages=[
        Stage(name="s1", capability="pipeline.classify",
              inputs={"rules": [
                  {"level": "critical", "when": False},
                  {"level": "warn", "when": False},
                  {"level": "ok", "when": "default"},
              ]}),
    ])
    r = asyncio.run(execute(p))
    assert r["stages"]["s1"]["level"] == "ok"


def test_stage_output_feeds_next_stage(monkeypatch):
    """Stage 1's output should be visible to stage 2 via templating."""
    async def fake_call(cap, payload, timeout_s=30.0):
        if cap == "fake.produce":
            return {"value": 42}
        if cap == "fake.consume":
            # If payload came through resolver, "n" should be 42, not the literal {{...}} string.
            return {"got": payload.get("n")}
        return {"error": "unknown cap"}
    monkeypatch.setattr(executor, "_call_capability", fake_call)

    p = Pipeline(name="chain", stages=[
        Stage(name="s1", capability="fake.produce"),
        Stage(name="s2", capability="fake.consume", inputs={"n": "{{s1.value}}"}),
    ])
    r = asyncio.run(execute(p))
    assert r["stages"]["s1"]["value"] == 42
    assert r["stages"]["s2"]["got"] == 42


def test_when_skips_stage():
    p = Pipeline(name="t", inputs={"skip_me": True}, stages=[
        Stage(name="s1", capability="pipeline.filter",
              inputs={"when": True}, when="{{inputs.skip_me == False}}"),
    ])
    r = asyncio.run(execute(p))
    assert r["stages"]["s1"].get("skipped") is True


def test_stage_error_aborts_by_default(monkeypatch):
    async def fake_call(cap, payload, timeout_s=30.0):
        return {"error": "boom"}
    monkeypatch.setattr(executor, "_call_capability", fake_call)

    p = Pipeline(name="t", stages=[
        Stage(name="s1", capability="bad.cap"),
        Stage(name="s2", capability="pipeline.filter", inputs={"when": True}),
    ])
    r = asyncio.run(execute(p))
    assert r["ok"] is False
    # s2 should NOT have run.
    assert "s2" not in r["stages"]


def test_on_error_continue(monkeypatch):
    async def fake_call(cap, payload, timeout_s=30.0):
        return {"error": "boom"}
    monkeypatch.setattr(executor, "_call_capability", fake_call)

    p = Pipeline(name="t", stages=[
        Stage(name="s1", capability="bad.cap", on_error="continue"),
        Stage(name="s2", capability="pipeline.filter", inputs={"when": True}),
    ])
    r = asyncio.run(execute(p))
    # Did run s2 despite s1 failing.
    assert "s2" in r["stages"]
    assert r["stages"]["s2"]["passed"] is True
