"""Docs worker.

Document extraction uses the small language model served by the
reasoning worker, not a regex. docs_worker builds a prompt from the
file text and the schema, posts it to the local /api/v1/call/reasoning/
answer endpoint, and parses the LLM's JSON reply.

Falls back to a lightweight regex only if the LLM path returns nothing
(no model loaded, HTTP server unreachable).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

from arikizu_worker import Worker


HTTP_BASE = os.environ.get("ARIKIZU_HTTP_BASE", "http://127.0.0.1:7000")


def _read_text(path: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        if p.suffix.lower() in (".txt", ".md", ".log", ".json", ".csv", ""):
            return p.read_text(errors="ignore")[:20000]
    except Exception:
        return ""
    return ""


# ---------------------------------------------------------------------------
# SLM-based extraction
# ---------------------------------------------------------------------------

def _build_prompt(text: str, schema: dict) -> str:
    schema_desc = "\n".join(f"  - {name} ({kind})" for name, kind in schema.items())
    return (
        "You read a document and extract fields into JSON.\n"
        "Return ONLY a valid JSON object with these keys and no commentary.\n"
        "If a field is not found, set it to null.\n"
        "For 'array' fields, return a JSON array of strings.\n"
        "For 'integer' fields, return a number without quotes.\n\n"
        f"Fields to extract:\n{schema_desc}\n\n"
        "Document:\n"
        f"{text[:4000]}\n\n"
        "JSON:\n"
    )


_JSON_PAT = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.S)


async def _extract_with_slm(text: str, schema: dict) -> tuple[dict | None, str]:
    """Returns (fields, backend) or (None, reason)."""
    prompt = _build_prompt(text, schema)
    payload = {"payload": {"question": prompt, "context": "", "max_tokens": 400}}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{HTTP_BASE}/api/v1/call/reasoning/answer", json=payload)
            r.raise_for_status()
            body = r.json()
    except Exception as e:
        return None, f"HTTP call to reasoning failed: {e}"

    backend = (body.get("backend") or "").lower()
    answer = body.get("answer") or ""
    if backend == "builtin":
        return None, "reasoning worker is in built-in mode (no LLM loaded)"
    # Try to pull a JSON object out of the answer
    m = _JSON_PAT.search(answer)
    if not m:
        return None, f"LLM reply had no parseable JSON (backend={backend})"
    try:
        obj = json.loads(m.group(0))
    except Exception as e:
        return None, f"JSON parse failed (backend={backend}): {e}"
    if not isinstance(obj, dict):
        return None, f"LLM returned non-object (backend={backend})"
    # Filter to just the requested keys
    out: dict[str, Any] = {}
    for k in schema.keys():
        out[k] = obj.get(k)
    return out, f"slm:{backend}"


# ---------------------------------------------------------------------------
# Regex fallback (used only if the SLM path returns nothing)
# ---------------------------------------------------------------------------

DATE_PAT = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b")
INT_PAT = re.compile(r"\b(-?\d+)\b")
SHIFT_PAT = re.compile(r"\b(morning|afternoon|evening|night|first|second|third|day|swing)\b", re.I)
LINE_PAT = re.compile(r"\bline[:\s]+(\d+)\b", re.I)
DEFECT_PAT = re.compile(r"\b(crack|scratch|dent|burn|leak|chip|misalignment|discoloration)\b", re.I)


def _regex_field(text: str, kind: str, name: str) -> Any:
    name_l = name.lower()
    m = re.search(rf"\b{re.escape(name)}\b\s*[:=]\s*([^\n,;]{{1,80}})", text, re.I)
    if m:
        v = m.group(1).strip()
        if kind == "integer":
            mi = INT_PAT.search(v)
            return int(mi.group(1)) if mi else None
        if kind == "array":
            return [x.strip() for x in re.split(r"[;,/]", v) if x.strip()]
        return v
    if "date" in name_l:
        md = DATE_PAT.search(text)
        return md.group(1) if md else None
    if "shift" in name_l:
        ms = SHIFT_PAT.search(text)
        return ms.group(1).lower() if ms else None
    if "line" in name_l:
        ml = LINE_PAT.search(text)
        return int(ml.group(1)) if ml else None
    if "defect" in name_l or kind == "array":
        return sorted({d.group(1).lower() for d in DEFECT_PAT.finditer(text)}) or None
    return None


def _extract_with_regex(text: str, schema: dict) -> dict:
    return {name: _regex_field(text, str(kind), name) for name, kind in schema.items()}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("docs")

    worker = Worker("docs")

    @worker.handler("docs.extract")
    async def extract(file_path: str = "", file_text: str = "",
                      schema: dict | None = None) -> dict[str, Any]:
        schema = schema or {}
        text = file_text or _read_text(file_path)
        if not text:
            return {
                "file": file_path,
                "fields": {},
                "schema": schema,
                "backend": "none",
                "note": "could not read file; pass a .txt/.md path or upload text",
            }

        fields, backend = await _extract_with_slm(text, schema)
        if fields is None:
            logger.info("SLM extraction unavailable: %s; using regex fallback", backend)
            fields = _extract_with_regex(text, schema)
            backend = "regex-fallback"
            note = "Install the local SLM (download SmolLM2 and set ARIKIZU_REASONING_GGUF) for real LLM extraction."
        else:
            note = None
        return {
            "file": file_path,
            "fields": fields,
            "schema": schema,
            "backend": backend,
            "chars_scanned": len(text),
            "note": note,
        }

    @worker.handler("docs.table")
    def table(file_path: str = "", page: int = 0) -> dict[str, Any]:
        text = _read_text(file_path)
        rows: list[list[str]] = []
        for line in text.splitlines():
            if "|" in line or "\t" in line:
                parts = [p.strip() for p in re.split(r"[|\t]", line) if p.strip()]
                if 2 <= len(parts) <= 10:
                    rows.append(parts)
        return {
            "file": file_path,
            "tables": [{"rows": rows}] if rows else [],
            "page": page,
            "backend": "text-split",
        }

    @worker.handler("docs.search")
    def search(query: str = "", top_k: int = 5) -> dict[str, Any]:
        corpus = Path.cwd() / "demo" / "fixtures"
        hits: list[dict[str, Any]] = []
        if not query.strip():
            return {"query": query, "hits": [], "top_k": top_k, "note": "empty query"}
        if corpus.exists():
            q = query.lower()
            for f in corpus.glob("*.txt"):
                try:
                    text = f.read_text(errors="ignore")
                except Exception:
                    continue
                for i, line in enumerate(text.splitlines(), start=1):
                    if q in line.lower():
                        hits.append({
                            "file": str(f.relative_to(Path.cwd())),
                            "line": i,
                            "text": line.strip()[:200],
                            "score": line.lower().count(q),
                        })
        hits.sort(key=lambda h: -h["score"])
        return {"query": query, "hits": hits[:top_k], "top_k": top_k, "backend": "text-search"}

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
