"""Eval worker. Weekend 12 wires LLMEvalKit.

    from llmevalkit import Scorer, GoldenRunner
    scorer = Scorer(metrics=["rouge", "exact", "cosine"])
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from arikizu_worker import Worker

GOLDEN_DIR = Path(os.environ.get("ARIKIZU_GOLDEN_DIR", "./golden"))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )

    worker = Worker("eval")

    @worker.handler("eval.score")
    def score(predicted: str = "", expected: str = "", metrics: list[str] | None = None) -> dict[str, Any]:
        metrics = metrics or ["exact", "jaccard"]
        out = {}
        if "exact" in metrics:
            out["exact"] = 1.0 if predicted.strip() == expected.strip() else 0.0
        if "jaccard" in metrics:
            a = set(predicted.lower().split())
            b = set(expected.lower().split())
            out["jaccard"] = len(a & b) / len(a | b) if (a | b) else 0.0
        return {"scores": out, "note": "placeholder; LLMEvalKit full metric suite not yet wired"}

    @worker.handler("eval.compare")
    def compare(a: str = "", b: str = "") -> dict[str, Any]:
        return {"a_len": len(a), "b_len": len(b), "equal": a == b}

    @worker.handler("eval.golden_run")
    def golden_run(set_name: str = "default") -> dict[str, Any]:
        path = GOLDEN_DIR / f"{set_name}.jsonl"
        if not path.exists():
            return {"set": set_name, "error": "golden set not found", "path": str(path)}
        count = sum(1 for _ in path.open())
        return {"set": set_name, "size": count, "note": "placeholder; eval runner not yet wired"}

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
