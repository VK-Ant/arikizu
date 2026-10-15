#!/usr/bin/env python3
"""Hello world. First demo to run.

Checks that the runtime is reachable and the test worker is answering.
If this passes, your IPC path is live end-to-end.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime  # noqa: E402


def main() -> int:
    require_runtime()
    banner("Hello Arikizu")

    print_result("test.echo",       call("test.echo", {"message": "hello arikizu"}), show_body=True)
    print_result("test.add 2+40",   call("test.add", {"a": 2, "b": 40}), show_body=True)
    print_result("test.slow 0.3s",  call("test.slow", {"seconds": 0.3}), show_body=True)

    print()
    print("If all three say [PASS] your Rust supervisor is talking to the Python worker.")
    print("Try the per-worker demos next:  python3 demo/perception/vision_demo.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
