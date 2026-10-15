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

    import time
    worker = Worker("memory")
    # Each session holds [{item, added_at, hits, score}]
    store: dict[str, list[dict[str, Any]]] = {}
    rewards: dict[str, float] = {}

    def _score(item: dict, query: str) -> float:
        """Simple relevance: Jaccard over tokens + recency bonus."""
        if not query:
            return 0.0
        q_tokens = set(query.lower().split())
        text = " ".join(str(v) for v in item.get("item", {}).values())
        if not text:
            return 0.0
        t_tokens = set(text.lower().split())
        jac = len(q_tokens & t_tokens) / len(q_tokens | t_tokens) if (q_tokens | t_tokens) else 0.0
        age_s = time.time() - item.get("added_at", 0)
        recency = max(0, 1 - age_s / 3600)  # 0 to 1, decays over an hour
        reward = rewards.get(item.get("id", ""), 0.0)
        return jac * 0.7 + recency * 0.2 + reward * 0.1

    @worker.handler("memory.recall")
    def recall(session_id: str = "", query: str = "", top_k: int = 5) -> dict[str, Any]:
        items = store.get(session_id, [])
        if not query:
            # No query - return most recent
            picked = items[-top_k:][::-1]
            return {
                "session_id": session_id,
                "items": [p["item"] for p in picked],
                "scored": [{"item": p["item"], "score": 1.0, "basis": "recency"} for p in picked],
                "total_in_session": len(items),
                "query": query,
                "backend": "ram-recent",
            }
        # With query - rank by relevance
        scored = [(_score(it, query), it) for it in items]
        scored.sort(key=lambda s: -s[0])
        top = [(sc, it) for sc, it in scored[:top_k] if sc > 0]
        return {
            "session_id": session_id,
            "items": [it["item"] for _, it in top],
            "scored": [{"item": it["item"], "score": round(sc, 3), "basis": "jaccard+recency+reward"}
                       for sc, it in top],
            "total_in_session": len(items),
            "query": query,
            "backend": "ram-ranked",
        }

    @worker.handler("memory.update")
    def update(session_id: str = "", item: dict | None = None) -> dict[str, Any]:
        import uuid
        item = item or {}
        entry = {
            "id": str(uuid.uuid4())[:8],
            "item": item,
            "added_at": time.time(),
        }
        store.setdefault(session_id, []).append(entry)
        return {"ok": True, "id": entry["id"], "count": len(store[session_id]),
                "backend": "ram"}

    @worker.handler("memory.reward")
    def reward(query_id: str = "", score: float = 0.0) -> dict[str, Any]:
        rewards[query_id] = float(score)
        return {
            "query_id": query_id,
            "score": score,
            "stored_rewards": len(rewards),
            "backend": "ram",
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
