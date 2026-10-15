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

# Rule set wired to AntGuard semantics (full ML-based detectors land
# weekend 10). Each pattern tagged with a severity so the UI can
# triage without re-running.
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("email",     re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "warn"),
    ("phone",     re.compile(r"\+?\d[\d \-()]{7,}\d"), "warn"),
    ("aadhaar",   re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"), "high"),
    ("ssn",       re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "high"),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "high"),
    ("ipv4",      re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "info"),
    ("url",       re.compile(r"https?://\S+"), "info"),
    ("api_key",   re.compile(r"\b(?:sk|pk|AKIA)[A-Za-z0-9_\-]{16,}\b"), "high"),
    ("pan_india", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "high"),
    ("iban",      re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"), "warn"),
]


def _detect(text: str) -> list[dict[str, Any]]:
    findings = []
    for kind, pat, sev in _PATTERNS:
        for match in pat.finditer(text):
            findings.append({
                "kind": kind,
                "severity": sev,
                "span": [match.start(), match.end()],
                "text": match.group(),
            })
    return findings


def _summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-kind count for the UI."""
    counts: dict[str, int] = {}
    worst = "ok"
    rank = {"ok": 0, "info": 1, "warn": 2, "high": 3}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
        if rank.get(f.get("severity", "info"), 1) > rank.get(worst, 0):
            worst = f.get("severity", "info")
    return {"counts": counts, "worst_severity": worst}


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )

    worker = Worker("guard")

    @worker.handler("guard.scan")
    def scan(text: str = "") -> dict[str, Any]:
        findings = _detect(text)
        s = _summary(findings)
        return {
            "findings": findings,
            "summary": s["counts"],
            "severity": s["worst_severity"],
            "detector_count": len(_PATTERNS),
            "chars_scanned": len(text),
        }

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
