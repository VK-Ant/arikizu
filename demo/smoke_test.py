#!/usr/bin/env python3
"""The "is everything working?" check.

Hits every capability the runtime should serve, classifies each as
PASS / WAIT / FAIL, prints a one-line summary at the end.

Legend:
  PASS   capability returned a real result
  WAIT   capability returned the placeholder note (library not yet wired)
  FAIL   capability returned an error, timed out, or 500'd
  SKIP   capability was intentionally not tested (needs external data)

Zero third-party deps; runs with plain python3.

Usage:
  python3 demo/smoke_test.py
"""

from __future__ import annotations

import sys

# Allow running as `python demo/smoke_test.py` from repo root.
sys.path.insert(0, __import__("os").path.dirname(__file__))

from common import (
    BOLD,
    GREY,
    RESET,
    banner,
    call,
    print_result,
    require_runtime,
    status_summary,
)

# ---------------------------------------------------------------------------
# Capability menu. One line per call.
# ---------------------------------------------------------------------------
CALLS = [
    # (label,                 capability,            payload)
    ("hello: echo",           "test.echo",           {"message": "hello"}),
    ("hello: add 2+40",       "test.add",            {"a": 2, "b": 40}),
    ("hello: slow 0.2s",      "test.slow",           {"seconds": 0.2}),

    ("vision: detect",        "vision.detect",       {"image_path": "demo/fixtures/sample.png", "confidence": 0.5}),
    ("vision: ocr",           "vision.ocr",          {"image_path": "demo/fixtures/sample.png", "lang": "en"}),
    ("vision: caption",       "vision.caption",      {"image_path": "demo/fixtures/sample.png"}),

    ("audio: transcribe",     "audio.transcribe",    {"audio_path": "demo/fixtures/sample.wav", "lang": "en"}),
    ("audio: vad",            "audio.vad",           {"audio_path": "demo/fixtures/sample.wav", "threshold": 0.5}),
    ("audio: keyword_spot",   "audio.keyword_spot",  {"audio_path": "demo/fixtures/sample.wav", "keywords": ["hello"]}),

    ("docs: extract",         "docs.extract",        {"file_path": "demo/fixtures/sample.txt", "schema": {}}),
    ("docs: table",           "docs.table",          {"file_path": "demo/fixtures/sample.txt", "page": 0}),
    ("docs: search",          "docs.search",         {"query": "arikizu", "top_k": 3}),

    ("reasoning: summarize",  "reasoning.summarize", {"text": "Arikizu is edge-first AI runtime.", "max_tokens": 80}),
    ("reasoning: answer",     "reasoning.answer",    {"question": "What is 2+2?", "context": "basic arithmetic.", "max_tokens": 40}),

    ("timeseries: forecast",  "timeseries.forecast", {"series": [1.0, 1.1, 1.2, 1.3, 1.4], "horizon": 5}),
    ("timeseries: anomaly",   "timeseries.detect_anomaly", {"series": [1.0, 1.1, 1.2, 10.0, 1.3], "threshold": 3.0}),

    ("memory: update",        "memory.update",       {"session_id": "demo-1", "item": {"q": "first"}}),
    ("memory: recall",        "memory.recall",       {"session_id": "demo-1", "query": "first", "top_k": 3}),
    ("memory: reward",        "memory.reward",       {"query_id": "demo-q", "score": 0.9}),

    ("guard: scan",           "guard.scan",          {"text": "Email vk@example.com or +91 9876543210"}),
    ("guard: redact",         "guard.redact",        {"text": "Email vk@example.com", "replacement": "[X]"}),
    ("guard: audit",          "guard.audit",         {"subject": "demo", "payload": {"n": 1}}),

    ("eval: score exact",     "eval.score",          {"predicted": "the cat sat", "expected": "the cat sat", "metrics": ["exact", "jaccard"]}),
    ("eval: score miss",      "eval.score",          {"predicted": "the cat sat", "expected": "the dog ran", "metrics": ["exact", "jaccard"]}),
    ("eval: compare",         "eval.compare",        {"a": "foo", "b": "foo"}),
]


def main() -> int:
    require_runtime()

    info = status_summary()
    banner(f"Arikizu smoke test  —  pipeline: {info.get('pipeline', '?')}  v{info.get('version', '?')}")
    workers = {w["name"]: w["state"] for w in info.get("workers", [])}
    if workers:
        print(f"  {GREY}workers:{RESET} " + ", ".join(f"{n}={s}" for n, s in workers.items()))
    else:
        print(f"  {GREY}no workers reported running{RESET}")

    counts = {"PASS": 0, "WAIT": 0, "FAIL": 0, "SKIP": 0}
    for label, cap, payload in CALLS:
        res = call(cap, payload)
        print_result(label, res)
        counts[res.status] = counts.get(res.status, 0) + 1

    banner("Summary")
    total = sum(counts.values())
    print(f"  {BOLD}{counts['PASS']}{RESET} live   "
          f"{BOLD}{counts['WAIT']}{RESET} placeholder   "
          f"{BOLD}{counts['FAIL']}{RESET} failing   "
          f"{BOLD}{counts['SKIP']}{RESET} skipped   "
          f"(of {total})")
    if counts["FAIL"] == 0:
        print()
        print(f"  Everything that should respond is responding.")
        print(f"  WAIT rows become PASS once the matching library is wired in; see docs/MODULES.md.")
        return 0
    print()
    print(f"  Some capabilities failed; see the lines marked [FAIL] above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
