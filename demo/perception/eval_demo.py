#!/usr/bin/env python3
"""Eval worker demo. LLMEvalKit wrapper.

v0.1: partially live. Exact-match and Jaccard scoring work; the full
LLMEvalKit metric suite lands Weekend 12.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime  # noqa: E402


def main() -> int:
    require_runtime()
    banner("Eval worker  —  score and compare")

    print_result(
        "eval.score  (identical)",
        call("eval.score", {"predicted": "the cat sat on the mat", "expected": "the cat sat on the mat"}),
        show_body=True,
    )
    print_result(
        "eval.score  (partial)",
        call("eval.score", {"predicted": "the cat sat on the mat", "expected": "a cat sat on a mat"}),
        show_body=True,
    )
    print_result(
        "eval.score  (totally different)",
        call("eval.score", {"predicted": "foo bar baz", "expected": "lorem ipsum dolor"}),
        show_body=True,
    )
    print_result("eval.compare  (equal)", call("eval.compare", {"a": "x", "b": "x"}),  show_body=True)
    print_result("eval.compare  (diff)",  call("eval.compare", {"a": "x", "b": "y"}),  show_body=True)
    print_result("eval.golden_run  (default)", call("eval.golden_run", {"set_name": "default"}), show_body=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
