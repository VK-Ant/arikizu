---
name: Bug report
about: Something broke; help us reproduce it.
title: '[bug] '
labels: ['bug', 'triage']
---

**What happened**

Short description.

**Expected**

What should have happened instead.

**Steps to reproduce**

1. `make run` with this `arikizu.yaml`:
   ```yaml
   # paste the relevant part
   ```
2. `make smoke` in another terminal
3. See the failing row(s)

**Smoke test output**

```
# paste the PASS/WAIT/FAIL summary
```

**Environment**

- Device: Pi 4 (4 GB) / Pi 5 / Jetson Orin Nano / x86_64 Linux / macOS
- OS: `uname -a`
- Rust: `rustc --version`
- Python: `python3 --version`
- uv: `uv --version`
- Arikizu version/commit: `git describe --always`

**Audit log excerpt (if relevant)**

```
# curl -s 'http://127.0.0.1:7000/api/v1/audit?limit=20' | jq
```

**Status output**

```
# arikizu status --dev --json
```
