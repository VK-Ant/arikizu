#!/usr/bin/env python3
"""Memory worker demo. adaptive-intelligence wrapper.

v0.1: partially live (in-process dict). Weekend 9 wires adaptive-intelligence
proper. The write-then-read round-trip already works.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime  # noqa: E402


def main() -> int:
    require_runtime()
    banner("Memory worker  —  write then recall")

    session = "demo-session-1"

    print_result(
        "memory.update  'first'",
        call("memory.update", {"session_id": session, "item": {"q": "first", "ts": 1}}),
    )
    print_result(
        "memory.update  'second'",
        call("memory.update", {"session_id": session, "item": {"q": "second", "ts": 2}}),
    )
    print_result(
        "memory.update  'third'",
        call("memory.update", {"session_id": session, "item": {"q": "third", "ts": 3}}),
    )
    print_result(
        "memory.recall  top_k=2",
        call("memory.recall", {"session_id": session, "query": "", "top_k": 2}),
        show_body=True,
    )
    print_result(
        "memory.reward  score=0.9",
        call("memory.reward", {"query_id": "demo-q", "score": 0.9}),
    )

    print()
    print("A successful round-trip means the in-process memory worker is up.")
    print("Note: this worker's state is in-RAM and resets when the runtime restarts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
