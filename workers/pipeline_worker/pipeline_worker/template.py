"""{{var}} substitution for YAML pipeline fields.

Supports:
  {{inputs.foo}}             pipeline-level inputs
  {{stage_name.field}}       any field from a previous stage's output
  {{stage_name.field.sub}}   nested lookup via dots
  {{var | length}}           built-in filters: length, upper, lower, default("x"), json
  {{inputs.n > 5}}            boolean/arithmetic expressions
                             (expression goes through Python's eval with a safe ctx)

Not supported (deliberately): control flow, imports, attribute access to
builtins, arbitrary Python. Expressions are evaluated with eval() but with
__builtins__ wiped and only the context dict available. This is NOT a
sandbox against hostile input; it is a pragmatic DSL for the pipeline
author's own data.
"""
from __future__ import annotations

import json as _json
import re
from typing import Any

_PAT = re.compile(r"\{\{\s*(.+?)\s*\}\}")


def _lookup(path: str, ctx: dict) -> Any:
    """Dotted path lookup into the context, e.g. 'inputs.foo' or 'step1.detections'."""
    cur: Any = ctx
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, (list, tuple)) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            cur = getattr(cur, part, None)
    return cur


def _apply_filter(value: Any, filt: str) -> Any:
    """Apply a single filter like 'length' or 'default("x")' to a value."""
    filt = filt.strip()
    if filt == "length":
        try:
            return len(value) if value is not None else 0
        except TypeError:
            return 0
    if filt == "upper":
        return str(value).upper() if value is not None else ""
    if filt == "lower":
        return str(value).lower() if value is not None else ""
    if filt == "json":
        try:
            return _json.dumps(value)
        except Exception:
            return str(value)
    if filt.startswith("default(") and filt.endswith(")"):
        # default("x") or default('x')
        inner = filt[len("default("):-1].strip()
        if (inner.startswith('"') and inner.endswith('"')) or \
           (inner.startswith("'") and inner.endswith("'")):
            inner = inner[1:-1]
        return value if (value is not None and value != "") else inner
    # Unknown filter: pass through.
    return value


_DOTTED_PAT = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_0-9]+)+)\b")


def _substitute_paths(expr: str, ctx: dict) -> str:
    """Replace every `foo.bar.baz` in `expr` with the repr() of its
    looked-up value. Bare top-level names (no dot) stay as-is so eval can
    see them as locals."""
    def _repl(m: re.Match) -> str:
        path = m.group(1)
        val = _lookup(path, ctx)
        return repr(val)
    return _DOTTED_PAT.sub(_repl, expr)


def resolve_one(expr: str, ctx: dict) -> Any:
    """Resolve a single {{...}} expression.

    If the expression is a plain path (letters/digits/dots), do a direct
    lookup. Otherwise treat it as a Python expression: dotted paths are
    pre-substituted with their values, then eval runs in a restricted
    namespace. Filters (`| length`, `| default("x")`) chain on the result.
    """
    parts = [p.strip() for p in expr.split("|")]
    head = parts[0]
    filters = parts[1:]
    if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_0-9]+)*", head):
        value = _lookup(head, ctx)
    else:
        try:
            # Substitute dotted paths with their looked-up repr, then eval.
            prepared = _substitute_paths(head, ctx)
            safe_locals = {k: v for k, v in ctx.items() if not k.startswith("_")}
            safe_locals.setdefault("True", True)
            safe_locals.setdefault("False", False)
            safe_locals.setdefault("None", None)
            value = eval(prepared, {"__builtins__": {}}, safe_locals)   # noqa: S307
        except Exception:
            return None
    for f in filters:
        value = _apply_filter(value, f)
    return value


def render(value: Any, ctx: dict) -> Any:
    """Recursively substitute {{...}} in a nested structure.

    Strings are substituted. If a string is exactly '{{expr}}' with nothing
    else, the raw result (dict/list/number/bool) is returned, not stringified.
    Lists and dicts are walked. Everything else passes through.
    """
    if isinstance(value, str):
        return _render_string(value, ctx)
    if isinstance(value, list):
        return [render(x, ctx) for x in value]
    if isinstance(value, dict):
        return {k: render(v, ctx) for k, v in value.items()}
    return value


def _render_string(s: str, ctx: dict) -> Any:
    """Render a single string. If the whole string is one expression, keep its type."""
    m = _PAT.fullmatch(s.strip())
    if m:
        return resolve_one(m.group(1), ctx)
    def _sub(m: re.Match) -> str:
        v = resolve_one(m.group(1), ctx)
        return "" if v is None else str(v)
    return _PAT.sub(_sub, s)
