# guard_worker

Wraps AntGuard. Runtime privacy and security audit: PII detection, redaction, policy check.

v0.1 is **partially live** — the scan and redact handlers use regex-based detectors for email, phone, and Aadhaar. Weekend 10 swaps in the full AntGuard detector suite.

## Capabilities

| Capability       | Payload                                        | Result                                           |
| ---------------- | ---------------------------------------------- | ------------------------------------------------ |
| `guard.scan`     | `{ text: str }`                                | `{ findings: [{kind,span,text?}], severity: str }` |
| `guard.redact`   | `{ text: str, replacement: str }`              | `{ redacted: str, findings: [...] }`             |
| `guard.audit`    | `{ subject: str, payload: object }`            | `{ subject: str, ok: bool }`                     |

## Try the placeholder

```
arikizu call guard.scan '{"text":"Email me at vk@example.com or 9876543210"}'
# -> {"findings":[{"kind":"email", ...}, {"kind":"phone", ...}], "severity":"warn"}

arikizu call guard.redact '{"text":"Email me at vk@example.com","replacement":"[REDACTED]"}'
# -> {"redacted":"Email me at [REDACTED]", "findings":[...]}
```

## Pipeline usage

Add a `guard.scan` or `guard.redact` stage after any `vision.ocr` / `docs.extract` and before any `reasoning.*` or external notification. The returned `findings` ride on the pipeline's carried JSON into the next stage, so the operator sees them in the review queue.

## Wiring (Weekend 10)

```python
from antguard import Scanner, Redactor, PolicyChecker

scanner = Scanner.default()
redactor = Redactor.default()
checker = PolicyChecker.load("./policies")
```
