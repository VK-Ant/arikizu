#!/usr/bin/env python3
"""Approval-gate pipeline demo.

Runs a pipeline that contains `feedback.approve`, waits a few seconds for
the pending action to show up, then approves it. Terminates with the final
run status.

Needs two terminals usually (one for `arikizu run`, one for this), or run
this in the background while watching the dashboard's /review page.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import BASE_URL, banner, require_runtime  # noqa: E402


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        raw = resp.read()
        return json.loads(raw) if raw.strip() else {}


def get(path: str) -> list | dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=15) as resp:
        return json.loads(resp.read())


def run_pipeline(result_box: list) -> None:
    try:
        result_box.append(post("/api/v1/pipeline/run", {}))
    except Exception as e:
        result_box.append({"error": str(e)})


def main() -> int:
    require_runtime()
    banner("Approval-gate pipeline")

    # Start the pipeline run on a background thread; it will stop at the gate.
    result_box: list = []
    t = threading.Thread(target=run_pipeline, args=(result_box,), daemon=True)
    t.start()

    # Poll /feedback/pending until the gate shows up (or 15s pass).
    deadline = time.monotonic() + 15
    pending = []
    while time.monotonic() < deadline:
        pending = get("/api/v1/feedback/pending")
        if pending:
            break
        time.sleep(0.5)

    if not pending:
        print("No pending approval showed up within 15s. Pipeline may have no feedback.approve stage,")
        print("or an earlier stage failed. Check /audit for details.")
        t.join(timeout=5)
        print("final:", result_box[0] if result_box else "<no result>")
        return 1

    action = pending[0]
    print(f"Pending gate found: pipeline={action['pipeline']} stage={action['stage']}")
    print(f"Approving as `demo-operator`...")
    post("/api/v1/feedback/approve", {"action_id": action["action_id"], "approver": "demo-operator"})

    # Wait for the run to finish.
    t.join(timeout=60)
    run = result_box[0] if result_box else {}
    print()
    print(f"final status: {run.get('status', '?')}")
    print(json.dumps(run, indent=2))
    return 0 if run.get("status") in ("succeeded", "Succeeded") else 1


if __name__ == "__main__":
    sys.exit(main())
