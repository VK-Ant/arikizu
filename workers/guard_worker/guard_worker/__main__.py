"""Guard worker. Weekend 10 wires AntGuard.

    from antguard import Scanner, Redactor
    scanner = Scanner.default()
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from arikizu_worker import Worker

# Simple regex patterns for the v0.1 placeholder. AntGuard brings a real
# detector suite in Weekend 10.
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d \-()]{7,}\d")
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")


def _detect(text: str) -> list[dict[str, Any]]:
    findings = []
    for match in EMAIL_RE.finditer(text):
        findings.append({"kind": "email", "span": [match.start(), match.end()], "text": match.group()})
    for match in PHONE_RE.finditer(text):
        findings.append({"kind": "phone", "span": [match.start(), match.end()], "text": match.group()})
    for match in AADHAAR_RE.finditer(text):
        findings.append({"kind": "aadhaar", "span": [match.start(), match.end()]})
    return findings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )

    worker = Worker("guard")

    @worker.handler("guard.scan")
    def scan(text: str = "") -> dict[str, Any]:
        findings = _detect(text)
        return {"findings": findings, "severity": "warn" if findings else "ok"}

    @worker.handler("guard.redact")
    def redact(text: str = "", replacement: str = "[REDACTED]") -> dict[str, Any]:
        findings = _detect(text)
        out = text
        # Replace right-to-left to keep spans valid.
        for finding in sorted(findings, key=lambda f: f["span"][0], reverse=True):
            s, e = finding["span"]
            out = out[:s] + replacement + out[e:]
        return {"redacted": out, "findings": findings}

    @worker.handler("guard.audit")
    def audit(subject: str = "", payload: dict | None = None) -> dict[str, Any]:
        payload = payload or {}
        return {
            "subject": subject,
            "ok": True,
            "note": "placeholder; AntGuard full audit not yet wired",
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
