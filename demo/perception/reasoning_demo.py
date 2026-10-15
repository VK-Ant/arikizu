#!/usr/bin/env python3
"""Reasoning worker demo. Local LLM via Ollama.

This one is LIVE in v0.1. If it fails, the usual cause is that Ollama is
not running on 127.0.0.1:11434. Start it with:

    ollama serve
    ollama pull qwen2.5:3b-instruct-q4_K_M     # one-time

Then rerun.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime  # noqa: E402


def main() -> int:
    require_runtime()
    banner("Reasoning worker  —  Ollama local LLM")

    print_result(
        "reasoning.answer  (basic q&a)",
        call("reasoning.answer", {
            "question": "What is the capital of Tamil Nadu?",
            "context": "Tamil Nadu is a state in southern India.",
            "max_tokens": 40,
        }),
        show_body=True,
    )

    print_result(
        "reasoning.summarize  (template)",
        call("reasoning.summarize", {
            "text": (
                "Arikizu is an edge-first AI runtime that packages seven libraries "
                "under a Rust supervisor and runs on Jetson devices without requiring "
                "a cloud connection. The dashboard shows pipelines, review queue, and "
                "a live audit log."
            ),
            "template": "In one short sentence:\n{text}",
            "max_tokens": 80,
        }),
        show_body=True,
    )

    print_result(
        "reasoning.complete  (freeform)",
        call("reasoning.complete", {
            "prompt": "A short tagline for Arikizu is:",
            "max_tokens": 20,
        }),
        show_body=True,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
