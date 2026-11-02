"""Execute a Pipeline: run each stage, pass outputs forward, fire actions.

Capability calls go through the Arikizu HTTP router (same path the UI
and MCP server use), so policy enforcement and audit logging apply to
every stage.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import asdict
from typing import Any

import httpx

from .loader import Action, Pipeline, Stage
from .template import render, resolve_one


logger = logging.getLogger("pipeline_worker.executor")

ARIKIZU_HTTP = os.environ.get("ARIKIZU_HTTP", "http://127.0.0.1:7000")


# ---------------------------------------------------------------------------
# Meta-capabilities handled directly by the executor (no router round-trip).
# ---------------------------------------------------------------------------

async def _meta_filter(ctx: dict, inputs: dict) -> dict:
    """A no-op stage whose only purpose is to gate downstream stages
    via `when:`. Returns {passed: bool} echoing the condition result."""
    cond = inputs.get("when")
    passed = bool(cond) if cond is not None else True
    return {"passed": passed}


async def _meta_delay(ctx: dict, inputs: dict) -> dict:
    secs = float(inputs.get("seconds", 0))
    secs = max(0.0, min(secs, 3600.0))       # clamp to 1 hour
    await asyncio.sleep(secs)
    return {"done": True, "slept_seconds": secs}


async def _meta_classify(ctx: dict, inputs: dict) -> dict:
    """Walk a `rules` list; the first rule whose `when` is truthy wins.

    Rules:
      - level: critical
        when: True
      - level: warn
        when: True
    (The `when` expressions were already resolved by the template layer.)
    """
    rules = inputs.get("rules") or []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        cond = rule.get("when")
        if cond == "default" or bool(cond):
            level = rule.get("level") or rule.get("label") or "match"
            return {"level": level, "matched_rule": rule}
    return {"level": "none", "matched_rule": None}


META_CAPABILITIES = {
    "pipeline.filter": _meta_filter,
    "pipeline.delay": _meta_delay,
    "pipeline.classify": _meta_classify,
}


# ---------------------------------------------------------------------------
# HTTP call to an ordinary capability
# ---------------------------------------------------------------------------

async def _call_capability(cap: str, payload: dict, timeout_s: float = 30.0) -> dict:
    """POST to /api/v1/call/<cap>/<rest>. Returns the parsed JSON response.

    On HTTP error, returns {"error": "...", "status": N} rather than raising,
    so the pipeline executor can decide whether to abort or continue.
    """
    url = f"{ARIKIZU_HTTP}/api/v1/call/{cap.replace('.', '/')}"
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(url, json={"payload": payload})
        if not r.is_success:
            return {"error": f"HTTP {r.status_code}", "status": r.status_code,
                    "body": r.text[:500]}
        return r.json()
    except httpx.HTTPError as e:
        return {"error": f"http error: {e}", "status": 0}


# ---------------------------------------------------------------------------
# Core: evaluate when:, run stages, fire actions
# ---------------------------------------------------------------------------

def _should_run(when: str, ctx: dict) -> bool:
    """Resolve a `when:` expression and return True/False.

    `always` and the empty string mean run. Anything else is passed
    through the template resolver and coerced to bool.
    """
    w = (when or "").strip()
    if w in ("", "always", "true", "True"):
        return True
    if w in ("never", "false", "False"):
        return False
    resolved = resolve_one(w, ctx)
    if isinstance(resolved, str):
        return resolved.strip().lower() in ("true", "yes", "1", "always")
    return bool(resolved)


async def _run_action(action: Action, ctx: dict) -> dict:
    """Execute one post-stages action. Supported today: audit, webhook."""
    resolved = render(action.config, ctx)
    if action.type == "audit":
        msg = resolved.get("message") or resolved.get("text") or "pipeline event"
        # Audit by calling feedback.annotate, which lands in the audit log.
        return await _call_capability("feedback.annotate", {
            "kind": "pipeline.action",
            "message": str(msg),
            "subject": ctx.get("name", "pipeline"),
        })
    if action.type == "webhook":
        url = resolved.get("url")
        if not url:
            return {"error": "webhook action missing url", "skipped": True}
        method = (resolved.get("method") or "POST").upper()
        payload = resolved.get("payload")
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.request(method, url, json=payload)
            return {"status": r.status_code, "ok": r.is_success}
        except httpx.HTTPError as e:
            return {"error": f"webhook failed: {e}"}
    # sms / email: not wired yet. Audit the intent so the user sees it tried.
    return {"error": f"action type '{action.type}' not implemented yet",
            "skipped": True, "resolved": resolved}


async def execute(pipeline: Pipeline, trigger_data: dict | None = None) -> dict:
    """Run every stage in order; return a report of what happened.

    Returns:
      {
        "name": "...",
        "ok": True / False,
        "stages": {<stage_name>: {...output or {error:...}}},
        "actions": [{"type": "audit", ...}, ...],
        "duration_ms": N,
      }
    """
    t0 = time.perf_counter()
    ctx: dict[str, Any] = {
        "name": pipeline.name,
        "inputs": dict(pipeline.inputs),
        "trigger": dict(trigger_data or {}),
    }
    stage_results: dict[str, Any] = {}
    ok = True

    for stage in pipeline.stages:
        try:
            if not _should_run(stage.when, ctx):
                stage_results[stage.name] = {"skipped": True, "reason": "when=false"}
                continue
            rendered_inputs = render(stage.inputs or {}, ctx)
            if stage.capability in META_CAPABILITIES:
                res = await META_CAPABILITIES[stage.capability](ctx, rendered_inputs)
            else:
                res = await _call_capability(stage.capability, rendered_inputs)
            stage_results[stage.name] = res
            ctx[stage.name] = res
            if isinstance(res, dict) and res.get("error"):
                if stage.on_error == "continue":
                    continue
                ok = False
                break
        except Exception as e:
            logger.exception("stage %s failed: %s", stage.name, e)
            stage_results[stage.name] = {"error": str(e)}
            if stage.on_error == "continue":
                continue
            ok = False
            break

    # Actions (post-run)
    action_results: list[dict] = []
    for action in pipeline.actions:
        if not _should_run(action.when, ctx):
            action_results.append({"type": action.type, "skipped": True})
            continue
        r = await _run_action(action, ctx)
        action_results.append({"type": action.type, **r})

    return {
        "name": pipeline.name,
        "ok": ok,
        "stages": stage_results,
        "actions": action_results,
        "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
