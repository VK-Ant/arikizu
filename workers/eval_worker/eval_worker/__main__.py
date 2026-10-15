"""Eval worker. Weekend 12 wires LLMEvalKit.

    from llmevalkit import Scorer, GoldenRunner
    scorer = Scorer(metrics=["rouge", "exact", "cosine"])
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from arikizu_worker import Worker


def _find_golden_dir() -> Path:
    env = os.environ.get("ARIKIZU_GOLDEN_DIR")
    if env and Path(env).exists():
        return Path(env)
    for base in (Path.cwd(), Path.cwd().parent, Path("./golden")):
        p = base / "golden" if base.name != "golden" else base
        if p.exists():
            return p
    return Path("./golden")


GOLDEN_DIR = _find_golden_dir()


def _exact(a: str, b: str) -> float:
    return 1.0 if a.strip() == b.strip() else 0.0


def _jaccard(a: str, b: str) -> float:
    sa, sb = set(a.lower().split()), set(b.lower().split())
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )

    worker = Worker("eval")

    @worker.handler("eval.score")
    def score(predicted: str = "", expected: str = "",
              metrics: list[str] | None = None) -> dict[str, Any]:
        metrics = metrics or ["exact", "jaccard"]
        out: dict[str, float] = {}
        if "exact" in metrics:
            out["exact"] = _exact(predicted, expected)
        if "jaccard" in metrics:
            out["jaccard"] = _jaccard(predicted, expected)
        return {"scores": out, "backend": "builtin"}

    @worker.handler("eval.compare")
    def compare(a: str = "", b: str = "") -> dict[str, Any]:
        return {"a_len": len(a), "b_len": len(b), "equal": a == b}

    @worker.handler("eval.golden_run")
    def golden_run(set_name: str = "default",
                   pass_threshold: float = 0.8) -> dict[str, Any]:
        path = GOLDEN_DIR / f"{set_name}.jsonl"
        if not path.exists():
            return {
                "set": set_name,
                "error": "golden set not found",
                "path": str(path),
                "hint": "create golden/<name>.jsonl with lines like "
                        '{"predicted":"...","expected":"..."}',
            }
        rows = []
        for line in path.open():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            pred, exp = row.get("predicted", ""), row.get("expected", "")
            scores = {"exact": _exact(pred, exp), "jaccard": _jaccard(pred, exp)}
            # "pass" if either exact match or jaccard above threshold
            passed = scores["exact"] == 1.0 or scores["jaccard"] >= pass_threshold
            rows.append({
                "query_id": row.get("query_id", f"row{len(rows)+1}"),
                "scores": scores,
                "passed": passed,
            })
        total = len(rows)
        passes = sum(1 for r in rows if r["passed"])
        return {
            "set": set_name,
            "size": total,
            "passed": passes,
            "failed": total - passes,
            "pass_rate": round(passes / total, 3) if total else 0.0,
            "mean_jaccard": round(
                sum(r["scores"]["jaccard"] for r in rows) / total, 3
            ) if total else 0.0,
            "rows": rows,
            "backend": "builtin",
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
