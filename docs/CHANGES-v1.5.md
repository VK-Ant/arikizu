# Arikizu v1.5

## v1.5.12 (local LLM out of the box)

Reasoning now works defaultly without installing anything else:

1. `scripts/download-default-models.sh --tier standard` adds a 400 MB
   small instruct LLM in GGUF format to `models/`. Standard tier is
   now the recommended default.
2. `workers/reasoning_worker/pyproject.toml` adds `llama-cpp-python` as
   a regular dependency; pre-built wheels exist for Linux x86_64,
   aarch64, and macOS so `scripts/bootstrap.sh` installs it without
   extra work.
3. `arikizu.yaml.example` sets `ARIKIZU_REASONING_GGUF` to point at the
   downloaded file by default. Worker auto-detects it on startup.

Fallback chain is still: local GGUF -> HTTP endpoint -> demo mode.
Nothing crashes if any layer is missing.

For users on minimum tier (no LLM downloaded): reasoning shows the
friendly demo-mode message from v1.5.11.

## v1.5.11 (reasoning worker fallback)
## v1.5.10 (zero CI, clearer prereqs)
## v1.5.9 (ready to publish)
## v1.5.8 (generic model names in prose)
## v1.5.7 (humanized docs)
## v1.5.6 (edge-device setup guide)
## v1.5.5 (beginner Pi guide)
## v1.5.4 (positioning + screenshots)
## v1.5.3 (architecture reference)
## v1.5.2 (brand assets)
## v1.5.1 (docs refresh)
## v1.5 (dashboard release)
