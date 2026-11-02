<!-- Thanks for the PR. Please fill in the sections below. -->

## What this changes

One or two sentences.

## Why

Issue number, or short rationale.

## Testing

- [ ] `cargo fmt --all -- --check` passes
- [ ] `cargo clippy --workspace --all-targets -- -D warnings` passes
- [ ] `cargo test --workspace` passes
- [ ] `uv run pytest -q` in `workers/` passes (if touched)
- [ ] `make smoke` reports 0 FAIL

## Security

- [ ] No new third-party crate / pip package added, OR the validation
      checklist in `SECURITY.md` was followed
- [ ] No secret, API key, or credential added
- [ ] No change to systemd sandbox or policy allowlist that widens
      permissions

## Docs

- [ ] README / docs updated if behavior visible to users changed
- [ ] Capability added to `capabilities.toml` if a new worker handler
- [ ] Added entry to `docs/ARCHITECTURE.md` if a new module

## Breaking change?

- [ ] No
- [ ] Yes — details in the body

<!-- Commits should follow the convention in CONTRIBUTING.md: present-tense
     imperative, trailer for the co-author line. -->
