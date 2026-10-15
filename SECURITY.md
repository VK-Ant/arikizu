# Security

Arikizu runs on devices that may sit in a factory, a hospital, or a ship
engine room. The threat model below is what we defend against today, what
we don't yet, and how dependencies get validated before they ship.

Honest first: v0.1 covers the obvious supply-chain and runtime-isolation
practices. It does **not yet** cover signed releases, mTLS between
dashboards, or hardware-rooted model attestation. Those land Weekend 15+.

## Threat model

What a reasonable attacker might try, and how we respond today.

| Threat                                      | Current mitigation                                          | Status |
| ------------------------------------------- | ----------------------------------------------------------- | ------ |
| Supply-chain: malicious crate/pypi package  | Version-pinned manifests, `cargo audit`, `pip-audit` in CI  | live   |
| Supply-chain: typosquatted dep              | `cargo deny` with name allowlist (Weekend 15)                | gap    |
| Backdoored model file                       | SHA-256 verify every download; `.pkl` loader warned         | partial|
| Pickle RCE (joblib loads unsafely)          | Only `.joblib` from a trusted source; audit log records load| partial|
| Arbitrary code via `arikizu.yaml`           | YAML is parsed with `serde_yaml`; no `!!python/object` tags | live   |
| Supervisor privilege escalation             | systemd sandbox: NoNewPrivileges, ProtectSystem=strict       | live   |
| Worker reaches the internet                 | `policies/no-outbound.yaml` enforces allow-hosts             | advisory |
| Dashboard without auth                      | Bound to `127.0.0.1` by default; LAN exposure needs reverse proxy | partial |
| Audit log tampering                         | SQLite append-only (no UPDATE/DELETE path); PRAGMA WAL        | partial |
| Worker crash takes down runtime             | Supervisor restarts; state keyed by pending_calls dashmap    | partial |
| Secret in config file                       | `.gitignore` for `.env` + ENV substitution in yaml           | gap    |
| IPC frame flood                             | 100 MB frame cap in `ant-ipc`                                | live   |
| Approval replay / forgery                   | PendingAction uuids, oneshot resolution                      | live   |
| Model inference OOM                         | Workers isolated as processes; one crash does not take out others | live   |
| Human approver impersonation                | Approver string trusted today; signed tokens Weekend 16     | gap    |

Legend: **live** = enforced in code, **advisory** = policy-level, **partial** = partial coverage, **gap** = known shortfall, roadmapped.

## Supply-chain validation (every dependency)

What we require before adding a new crate or pypi package:

### Rust crates

- [ ] Pinned exact version in `Cargo.toml` (no `*`, no `^`)
- [ ] Comes from crates.io (no git url except in workspace deps)
- [ ] `cargo audit` passes on this version
- [ ] License is compatible (Apache-2.0, MIT, BSD; AGPL rejected except for models)
- [ ] At least one of: >10k downloads, trusted author (dtolnay, tokio-rs, etc), code read by VK
- [ ] Not deprecated or superseded by a canonical alternative

### Python packages

- [ ] Pinned exact version in `pyproject.toml` (no `>=` alone)
- [ ] Comes from pypi.org (no `git+https://` except for workspace deps)
- [ ] `pip-audit` passes
- [ ] License is compatible
- [ ] Published by a known maintainer; check `pypi.org/project/<name>/` for ownership
- [ ] No typosquat risk (name differs from a popular package by one char)

### Models

- [ ] SHA-256 pinned in `scripts/download-default-models.sh`
- [ ] License is compatible with your deployment (yolov8 is AGPL-3.0: not fine for closed commercial without an Ultralytics license)
- [ ] Hosted on a trusted mirror (HuggingFace, GitHub Releases, Ultralytics assets)
- [ ] No executable code (ONNX / TFLite / joblib only; `.pt` warned; `.pkl` discouraged)

### Current validated dependency list

Rust (crates.io, pinned in Cargo.toml):
`tokio`, `axum`, `tower-http`, `serde`, `rmp-serde`, `thiserror`, `anyhow`,
`tracing`, `clap`, `rusqlite`, `reqwest`, `futures-util`, `chrono`, `uuid`,
`dashmap`, `sha2`, `toml`, `serde_yaml`. All read, all common, all audited.

Python (pypi, pinned in pyproject.toml of each worker):
`msgpack`, `pydantic`, `httpx`, `numpy`, `scikit-learn`, `joblib`,
`soundfile`, `Pillow`. All read, all common.

Models (SHA-256 pinned):
`yolov8n.onnx` (Ultralytics assets v8.3.0),
`silero_vad.onnx` (snakers4 v5.1).
Others fetched by tier.

## Runtime hardening

### systemd sandbox

`packaging/systemd/arikizu.service` applies these on every start:

```
NoNewPrivileges=true          # worker cannot gain root
ProtectSystem=strict          # root FS is read-only
ProtectHome=true              # /home is invisible
PrivateTmp=true               # /tmp isolated per unit
ReadWritePaths=/var/lib/arikizu /run/arikizu
LimitNOFILE=65536
TasksMax=512
```

The arikizu user has no login shell, no sudo, no password. systemd kills
the whole cgroup on stop; no leftover Python workers.

### Policy enforcement

`policies/no-outbound.yaml` (reference policy) lists which hosts the
runtime may reach. The supervisor's `policy::Policy::check_host()` denies
anything else at the HTTP egress layer. Enforcement is `block` by
default, `warn` for development.

### Network defaults

- HTTP server binds to `127.0.0.1:7000` only.
- To expose on the LAN, admin edits `runtime.http_api` in `arikizu.yaml`.
  There is no auto-detect fallback.
- WebSocket at `/api/v1/events` carries the same binding.
- No CORS by default. If dashboard access from another host is needed,
  put nginx (or Caddy) in front with HTTPS + Basic Auth.

### IPC

- Unix sockets under `/run/arikizu/<worker>.sock`, mode `0600`, owner
  `arikizu`.
- Frames are length-prefixed MessagePack, capped at 100 MB.
- A worker that misbehaves is terminated by the supervisor on timeout
  (per-capability `timeout_ms` in `capabilities.toml`).

## Model trust

### SHA-256 verification

Every default model is fetched with `curl -fL` and checked against a
pinned SHA-256 in `scripts/download-default-models.sh`. A mismatch
deletes the file and refuses to continue.

### `.joblib` and `.pkl`: read before loading

Joblib and pickle both deserialize arbitrary Python objects. Loading a
file written by an untrusted party is code execution.

Rules:

- Only load `.joblib` / `.pkl` from models **you generated** or that come
  from a known-trusted source (HuggingFace model you reviewed, a classical ML libraries
  bundle your CI built).
- Never accept a model file over HTTP upload from the dashboard. The
  switch_model endpoint takes a path on disk; whoever can write to that
  disk is already trusted.
- Prefer ONNX for anything you don't fully control. ONNX is a graph
  description, not executable code.

The SDK logs the model load path to the audit DB so you can trace which
file produced which pipeline run.

### Model provenance in the audit log

Every `load_model()` call writes a row to the audit log:

```json
{
  "kind": "model.loaded",
  "actor": "vision",
  "subject": "/var/lib/arikizu/models/yolov8n.onnx",
  "payload": {"backend": "onnx_cpu", "sha256": "...", "providers": [...]}
}
```

If regulators ever ask "which model handled this detection on 12 Oct
at 9:14 AM," the audit log answers.

## CVE scanning

Add to CI (see `.github/workflows/security.yml`):

```
cargo install cargo-audit
cargo audit --deny warnings

pip install pip-audit
pip-audit --strict
```

Both run on every push and every week via scheduled workflow. A new
CVE in a dependency breaks the build until it's patched or a documented
exception is in `security-exceptions.toml`.

## Dependabot

`.github/dependabot.yml` watches:

- `/` for Rust crate updates (weekly)
- `/workers/*` for Python package updates (weekly)
- `/.github/workflows/` for GitHub Actions version updates (monthly)

PRs land with the new version; CI runs the full matrix; if green, merge.

## Reporting a vulnerability

**Do not open a public GitHub issue** for a vulnerability.

Email `venkatkumarr.vk99@gmail.com` with:

- Component affected
- Reproduction steps
- Impact assessment
- Suggested fix (optional)

Response time target: acknowledgement within 72 hours, triage within 7
days, patch within 30 days for critical, 90 days for high.

Private disclosure through GitHub Security Advisories is also accepted.

## What's not covered yet (be explicit)

| Gap                                          | Workaround today                                | Plan                                   |
| -------------------------------------------- | ----------------------------------------------- | -------------------------------------- |
| Signed release binaries                      | SHA256SUMS file in Releases                     | sigstore cosign (Weekend 15)           |
| Signed Pi image                              | SHA256 in release                               | Signed image (Weekend 16)              |
| HTTPS by default                             | nginx reverse proxy                             | caddy baked into image (Weekend 15)    |
| Dashboard auth                               | bind to 127.0.0.1 + ssh tunnel                  | OIDC-compatible login (Weekend 16)     |
| Approval signing                             | approver name string                            | signed tokens (Weekend 16)             |
| SBOM                                         | manual                                          | cyclonedx generation in CI (W15)       |
| Fine-grained worker isolation (namespaces)   | process boundary                                | optional nspawn container (W18)        |
| Hardware-rooted model attestation            | SHA-256 only                                    | TPM / SE-based (Weekend 20+)           |

Honest framing: Arikizu's current security story is **"regular Linux
service with sensible systemd sandbox + append-only audit."** That is
appropriate for Weekend 3; it is not appropriate for a hospital
production deployment without the Weekend 15+ work.
