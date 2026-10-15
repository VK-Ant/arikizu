#!/usr/bin/env python3
"""Guard worker demo. AntGuard wrapper.

v0.1: partially live. Regex detects email, phone (incl. +91 formats), and
Aadhaar; redact works. Weekend 10 brings the full AntGuard detector suite.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime  # noqa: E402

SAMPLES = [
    "Email me at venkatkumarr.vk99@gmail.com or call +91 9876543210.",
    "Operator aadhaar 1234 5678 9012 is on site.",
    "Normal line with no PII to report, all good.",
]


def main() -> int:
    require_runtime()
    banner("Guard worker  —  PII scan and redact")

    for s in SAMPLES:
        print(f"\n  text: {s!r}")
        print_result("  guard.scan",   call("guard.scan",   {"text": s}),                                show_body=True)
        print_result("  guard.redact", call("guard.redact", {"text": s, "replacement": "[REDACTED]"}),   show_body=True)

    print()
    print_result("guard.audit", call("guard.audit", {"subject": "demo-run", "payload": {"source": "guard_demo"}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
