"""Memory worker. Weekend 9 wires adaptive-intelligence.

    from adaptive_intelligence import SessionMemory, RewardModel
    memory = SessionMemory(backend="chroma", path="./models/memory")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from arikizu_worker import Worker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )

    worker = Worker("memory")
    store: dict[str, list[dict[str, Any]]] = {}

    @worker.handler("memory.recall")
    def recall(session_id: str = "", query: str = "", top_k: int = 5) -> dict[str, Any]:
        items = store.get(session_id, [])
        return {
            "session_id": session_id,
            "items": items[-top_k:],
            "note": "in-memory placeholder; adaptive-intelligence not yet wired",
        }

    @worker.handler("memory.update")
    def update(session_id: str = "", item: dict | None = None) -> dict[str, Any]:
        store.setdefault(session_id, []).append(item or {})
        return {"ok": True, "count": len(store[session_id])}

    @worker.handler("memory.reward")
    def reward(query_id: str = "", score: float = 0.0) -> dict[str, Any]:
        return {
            "query_id": query_id,
            "score": score,
            "note": "placeholder; RL reward not yet wired",
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
