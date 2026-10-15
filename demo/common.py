"""Shared helpers for every demo.

Zero third-party deps. Uses urllib so a fresh clone can run the smoke test
without a pip install.
"""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

BASE_URL = "http://127.0.0.1:7000"
CALL_TIMEOUT_S = 60

# ANSI colors. Fallback cleanly on dumb terminals.
if sys.stdout.isatty():
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    GREY = "\033[90m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
else:
    GREEN = YELLOW = RED = GREY = BOLD = RESET = ""


@dataclass
class CallResult:
    status: str  # PASS | WAIT | FAIL | SKIP
    message: str
    body: Any = None
    elapsed_ms: float = 0.0


def _post_json(url: str, payload: dict) -> tuple[int, bytes]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=CALL_TIMEOUT_S) as resp:
        return resp.getcode(), resp.read()


def _get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=CALL_TIMEOUT_S) as resp:
        return resp.getcode(), resp.read()


def runtime_up() -> bool:
    """Return True if arikizu is running on BASE_URL."""
    try:
        code, _ = _get(f"{BASE_URL}/health")
        return code == 200
    except (urllib.error.URLError, socket.timeout, ConnectionError):
        return False


def call(capability: str, payload: dict | None = None) -> CallResult:
    """Invoke a capability over the HTTP API. Classifies the result."""
    if "." not in capability:
        return CallResult("FAIL", f"invalid capability `{capability}`")

    domain, op = capability.split(".", 1)
    url = f"{BASE_URL}/api/v1/call/{domain}/{op}"
    start = time.monotonic()
    try:
        code, raw = _post_json(url, {"payload": payload or {}})
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        # "worker not running" is a config choice, not a bug. SKIP it.
        if e.code == 503 and "not running" in detail:
            return CallResult("SKIP", f"{detail}")
        # 404 means the capability isn't in capabilities.toml at all.
        if e.code == 404:
            return CallResult("SKIP", "capability not registered")
        return CallResult("FAIL", f"HTTP {e.code}: {detail}")
    except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
        return CallResult("FAIL", f"connection error: {e}")

    elapsed = (time.monotonic() - start) * 1000
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return CallResult("FAIL", f"non-JSON response: {raw[:200]!r}", elapsed_ms=elapsed)

    # Classify: placeholder note means WAIT, error field means FAIL, otherwise PASS.
    if isinstance(body, dict):
        if "error" in body and body["error"]:
            return CallResult("FAIL", str(body["error"])[:200], body=body, elapsed_ms=elapsed)
        if "note" in body and "placeholder" in str(body.get("note", "")).lower():
            return CallResult("WAIT", str(body["note"])[:200], body=body, elapsed_ms=elapsed)
    return CallResult("PASS", f"HTTP {code}", body=body, elapsed_ms=elapsed)


def status_glyph(status: str) -> str:
    return {
        "PASS": f"{GREEN}[PASS]{RESET}",
        "WAIT": f"{YELLOW}[WAIT]{RESET}",
        "FAIL": f"{RED}[FAIL]{RESET}",
        "SKIP": f"{GREY}[SKIP]{RESET}",
    }.get(status, f"[{status}]")


def print_result(label: str, result: CallResult, show_body: bool = False) -> None:
    tag = status_glyph(result.status)
    timing = f"{result.elapsed_ms:5.0f}ms" if result.elapsed_ms else "       "
    print(f"  {tag} {label:30} {GREY}{timing}{RESET}  {result.message}")
    if show_body and result.body is not None:
        print(f"           {GREY}{json.dumps(result.body)[:300]}{RESET}")


def banner(title: str) -> None:
    print()
    print(f"{BOLD}{title}{RESET}")
    print(f"{GREY}{'-' * max(len(title), 40)}{RESET}")


def require_runtime() -> None:
    """Print a friendly message and exit if the runtime is not reachable."""
    if runtime_up():
        return
    print(f"{RED}arikizu is not running on {BASE_URL}.{RESET}")
    print()
    print("Start it in another terminal:")
    print()
    print("  cd ~/arikizu && make run")
    print()
    print("Then rerun this demo.")
    sys.exit(1)


def status_summary() -> dict:
    """Fetch /api/v1/status and return the parsed JSON."""
    code, raw = _get(f"{BASE_URL}/api/v1/status")
    return json.loads(raw) if code == 200 else {}
