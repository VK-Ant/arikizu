# Pre-built artifact drop zone

CI drops these before `pi-gen` runs:

```
arikizu                       # aarch64 release binary from cargo cross
wheels/*.whl                  # aarch64-manylinux Python wheels for every worker
arikizu.yaml.default          # copied from repo root / arikizu.yaml.example
capabilities.toml.default     # copied from repo root
no-outbound.yaml              # copied from policies/
arikizu.service               # copied from packaging/systemd/
arikizu-firstboot.sh          # already in this folder
arikizu-firstboot.service     # already in this folder
```

The copy-from-repo step lives in `.github/workflows/image.yml`.

Nothing in this folder is checked in except the firstboot scripts; the rest
are build artifacts.
