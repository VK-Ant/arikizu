#!/usr/bin/env python3
"""Two-stage pipeline demo. No human gate.

Runs the pipeline configured in arikizu.yaml via the HTTP API and prints
the result object. If the pipeline has an approval gate, use
approval_gate.py instead.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import BASE_URL, banner, require_runtime  # noqa: E402


def main() -> int:
    require_runtime()
    banner("Running pipeline via /api/v1/pipeline/run")

    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/pipeline/run",
        data=b"{}",
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')}")
        return 1

    print(json.dumps(body, indent=2))

    status = body.get("status", "?")
    stages = body.get("stage_results", [])
    oks = sum(1 for s in stages if s.get("result") is not None)
    print()
    print(f"status: {status}   stages passed: {oks} / {len(stages)}")
    return 0 if status in ("succeeded", "Succeeded") else 1


if __name__ == "__main__":
    sys.exit(main())
