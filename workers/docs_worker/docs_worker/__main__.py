"""Docs worker entry point.

Demo mode returns real extraction over the shipped fixture (and over
any plain-text file you pass in) using regex rules. Weekend 7 swaps
this out for DocQWise layout parsing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any

from arikizu_worker import Worker


DATE_PAT = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b")
INT_PAT = re.compile(r"\b(-?\d+)\b")
FLOAT_PAT = re.compile(r"\b(-?\d+\.\d+)\b")
SHIFT_PAT = re.compile(r"\b(morning|afternoon|evening|night|first|second|third|day|swing)\b", re.I)
LINE_PAT = re.compile(r"\bline[:\s]+(\d+)\b", re.I)
DEFECT_PAT = re.compile(r"\b(crack|scratch|dent|burn|leak|chip|misalignment|discoloration)\b", re.I)


def _read_text(path: str) -> str:
 if not path:
 return ""
 p = Path(path)
 if not p.is_absolute():
 p = Path.cwd() / p
 try:
 if p.suffix.lower() in (".txt", ".md", ".log", ""):
 return p.read_text(errors="ignore")[:20000]
 except Exception:
 return ""
 return ""


def _extract_field(text: str, kind: str, name: str) -> Any:
 """Pick a value for one field from the text based on its declared type."""
 kind = (kind or "string").lower()
 name_l = name.lower()

 # Try to find a labelled value first (e.g. "line: 7")
 labelled = re.search(rf"\b{re.escape(name)}\b\s*[:=]\s*([^\n,;]{{1,80}})", text, re.I)
 if labelled:
 v = labelled.group(1).strip()
 if kind == "integer":
 m = INT_PAT.search(v)
 return int(m.group(1)) if m else None
 if kind == "float":
 m = FLOAT_PAT.search(v)
 return float(m.group(1)) if m else None
 if kind == "array":
 return [x.strip() for x in re.split(r"[;,/]", v) if x.strip()]
 return v

 # No label: fall back to common patterns based on the field name
 if "date" in name_l or kind == "date":
 m = DATE_PAT.search(text)
 return m.group(1) if m else None
 if "shift" in name_l:
 m = SHIFT_PAT.search(text)
 return m.group(1).lower() if m else None
 if "line" in name_l:
 m = LINE_PAT.search(text)
 return int(m.group(1)) if m else None
 if "defect" in name_l or (kind == "array" and "defect" in text.lower()):
 return sorted({d.group(1).lower() for d in DEFECT_PAT.finditer(text)}) or None
 if kind == "integer":
 m = INT_PAT.search(text)
 return int(m.group(1)) if m else None
 if kind == "float":
 m = FLOAT_PAT.search(text)
 return float(m.group(1)) if m else None
 return None


def main() -> None:
 logging.basicConfig(
 level=logging.INFO,
 format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
 )

 worker = Worker("docs")

 @worker.handler("docs.extract")
 def extract(file_path: str = "", file_text: str = "",
 schema: dict | None = None) -> dict[str, Any]:
 schema = schema or {}
 # Prefer inline text from a browser upload; fall back to the
 # server-side path for the shipped fixture.
 text = file_text or _read_text(file_path)
 fields: dict[str, Any] = {}
 for name, kind in schema.items():
 fields[name] = _extract_field(text, str(kind), name)
 return {
 "file": file_path,
 "fields": fields,
 "schema": schema,
 "backend": "regex-demo",
 "chars_scanned": len(text),
 "note": None if text else (
 "could not read file; pass a readable .txt/.md path"
 ),
 }

 @worker.handler("docs.table")
 def table(file_path: str = "", page: int = 0) -> dict[str, Any]:
 text = _read_text(file_path)
 rows = []
 for line in text.splitlines():
 if "|" in line or "\t" in line:
 parts = [p.strip() for p in re.split(r"[|\t]", line) if p.strip()]
 if 2 <= len(parts) <= 10:
 rows.append(parts)
 return {
 "file": file_path,
 "tables": [{"rows": rows}] if rows else [],
 "page": page,
 "backend": "regex-demo",
 }

 @worker.handler("docs.search")
 def search(query: str = "", top_k: int = 5) -> dict[str, Any]:
 corpus = Path.cwd() / "demo" / "fixtures"
 hits = []
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
 return {
 "query": query,
 "hits": hits[:top_k],
 "top_k": top_k,
 "backend": "regex-demo",
 }

 asyncio.run(worker.run())


if __name__ == "__main__":
 main()
