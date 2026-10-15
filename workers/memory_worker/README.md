# memory_worker

Wraps adaptive-intelligence. Session memory and RL reward for the orchestrator. Weekend 9 wires the real backend; v0.1 has a simple in-process dict so pipelines can prove end-to-end flow.

## Capabilities

| Capability         | Payload                                                | Result                             |
| ------------------ | ------------------------------------------------------ | ---------------------------------- |
| `memory.recall`    | `{ session_id: str, query: str, top_k: int }`          | `{ items: [...] }`                 |
| `memory.update`    | `{ session_id: str, item: object }`                    | `{ ok: bool, count: int }`         |
| `memory.reward`    | `{ query_id: str, score: float }`                      | `{ query_id: str, score: float }`  |

## Why a separate worker

The orchestration logic that decides what to remember and how to score it is a different library (adaptive-intelligence) than the ones that produce the data to remember. Pulling it into its own worker keeps the ownership clear and lets the memory process be restarted without taking down vision or docs.

## Wiring (Weekend 9)

```python
from adaptive_intelligence import SessionMemory, RewardModel

memory = SessionMemory(backend="chroma", path="./models/memory")
reward = RewardModel.default()

@worker.handler("memory.recall")
def recall(session_id: str = "", query: str = "", top_k: int = 5) -> dict:
    return {"items": memory.recall(session_id, query, top_k=top_k)}
```

## Interaction with feedback.rate

The HTTP route `POST /api/v1/feedback/rate` records a feedback event but does **not** auto-forward to the memory worker. A pipeline stage that wants rate-to-reward wiring posts to `memory.reward` explicitly. Keeps the moving parts visible.
