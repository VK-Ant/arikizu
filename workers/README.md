# Arikizu Python workers

Every worker is a tiny package. It imports the SDK, registers handlers, and calls `worker.run()`. The supervisor spawns the process, hands it a Unix socket in `$ARIKIZU_SOCKET`, and the worker starts answering `test.*` / `vision.*` / etc. calls.

```
workers/
├── pyproject.toml                 uv workspace, lists every member
├── arikizu-worker-sdk/            the shared IPC shim; every worker imports this
├── test_worker/                   reference worker; test.echo, test.add, test.slow
├── vision_worker/                 SightRAG; vision.detect, vision.ocr, vision.caption
├── audio_worker/                  Sonarwise; audio.transcribe, audio.vad, audio.keyword_spot
├── docs_worker/                   DocQWise/Vellex; docs.extract, docs.table, docs.search
├── reasoning_worker/              Ollama HTTP; reasoning.answer, summarize, complete
├── timeseries_worker/             WavqWise; timeseries.forecast, detect_anomaly
├── memory_worker/                 adaptive-intelligence; memory.recall, update, reward
├── guard_worker/                  AntGuard; guard.scan, redact, audit
└── eval_worker/                   LLMEvalKit; eval.score, compare, golden_run
```

## Setup

```
cd workers
uv sync          # creates .venv/, resolves every member together
```

## Running one worker standalone (debugging)

```
cd workers
# Terminal 1: a dummy socket
ARIKIZU_SOCKET=/tmp/debug.sock python -c "
import asyncio, os
from arikizu_worker import Worker
w = Worker('test')
@w.handler('test.echo')
def echo(**kw): return kw
asyncio.run(w.run())
"
# Terminal 2: connect with socat and send a Hello
```

In practice, let the Rust supervisor spawn the worker and tail the logs with `RUST_LOG=debug`.

## Scaffold a new worker

1. Copy `test_worker/` to `<name>_worker/`
2. In its `pyproject.toml`, change `name = "<name>-worker"` and the entry-point script
3. Rewrite `__main__.py`: `Worker("<name>")` and the `@worker.handler("<name>.op")` functions
4. Add the module path to `workers/pyproject.toml` under `[tool.uv.workspace] members`
5. Register the capabilities in `/capabilities.toml`
6. `uv sync` and `arikizu run`

## Wiring one of VK's seven libraries

The v0.1 scaffolds return placeholder dicts so the IPC path and routing can be tested end-to-end. Replace the handler bodies with the real library calls when ready.

Example for vision:

```python
# vision_worker/vision_worker/__main__.py
from sightrag import Detector, OCRReader, Captioner

detector = Detector.load("yolov8n-defect.onnx")

@worker.handler("vision.detect")
def detect(image_path: str = "", confidence: float = 0.5) -> dict:
    detections = detector(image_path, conf=confidence)
    return {"image": image_path, "detections": [d.to_dict() for d in detections]}
```

The frame format and heartbeat loop stay in the SDK; the worker just supplies the handlers.
