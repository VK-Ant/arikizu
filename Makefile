# Arikizu OS development makefile.
#
# Phony targets only. The real build is `cargo build` + `uv sync` + `pnpm build`;
# this file wires them together into one-liner commands.

.PHONY: help setup build build-release test test-rust test-python test-integration \
        run run-release ui ui-dev lint lint-rust lint-python format clean bundle \
        prereqs doctor smoke demo-hello demo-fixtures demo-web demo-pi

SHELL := /bin/bash

# ---------------------------------------------------------------------------
# help (default)
# ---------------------------------------------------------------------------
help:
	@echo "Arikizu OS development commands"
	@echo
	@echo "  make setup           install workspace deps (cargo + uv + pnpm)"
	@echo "  make build           cargo build --workspace (debug)"
	@echo "  make build-release   cargo build --workspace --release"
	@echo "  make test            run every test tier"
	@echo "  make test-rust       cargo test --workspace"
	@echo "  make test-python     uv run pytest in workers/"
	@echo "  make test-integration  Rust supervisor + live Python worker tests"
	@echo "  make run             arikizu run (debug build)"
	@echo "  make run-release     arikizu run (release build)"
	@echo "  make ui              build the SvelteKit dashboard"
	@echo "  make ui-dev          vite dev server for the dashboard"
	@echo "  make lint            cargo clippy + ruff check"
	@echo "  make format          cargo fmt + ruff format"
	@echo "  make clean           cargo clean + ui dist clean + uv cache clean (local only)"
	@echo "  make bundle          cargo-dist build release artifacts"
	@echo "  make prereqs         scripts/check_prereqs.sh"
	@echo "  make doctor          runtime self-check (devices, workers, policies)"
	@echo "  make smoke           run demo/smoke_test.py (is everything working?)"
	@echo "  make demo-hello      run the hello-world demo"
	@echo "  make demo-fixtures   regenerate demo fixtures"
	@echo "  make demo-web        print the URL for the zero-dep web sandbox"
	@echo "  make demo-pi         run all raspberrypi/ e2e checks"

# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------
setup: prereqs
	@echo ">>> syncing rust workspace"
	cargo fetch
	@echo ">>> syncing python workspace"
	cd workers && uv sync
	@echo ">>> syncing ui workspace"
	cd ui && pnpm install
	@echo "setup complete; try: make build"

prereqs:
	@scripts/check_prereqs.sh

# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
build:
	cargo build --workspace

build-release:
	cargo build --workspace --release

# ---------------------------------------------------------------------------
# test
# ---------------------------------------------------------------------------
test: test-rust test-python test-integration

test-rust:
	cargo test --workspace --all-features

test-python:
	cd workers && uv run pytest -q

test-integration:
	cargo test --workspace --test integration -- --test-threads=1

# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
run:
	cargo run --bin arikizu -- run

run-release: build-release
	./target/release/arikizu run

# ---------------------------------------------------------------------------
# ui
# ---------------------------------------------------------------------------
ui:
	cd ui && pnpm run build

ui-dev:
	cd ui && pnpm run dev

# ---------------------------------------------------------------------------
# lint / format
# ---------------------------------------------------------------------------
lint: lint-rust lint-python

lint-rust:
	cargo clippy --workspace --all-targets -- -D warnings

lint-python:
	cd workers && uv run ruff check .

format:
	cargo fmt --all
	cd workers && uv run ruff format .

# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------
clean:
	cargo clean
	rm -rf ui/.svelte-kit ui/build
	cd workers && uv cache clean

# ---------------------------------------------------------------------------
# bundle (release artifacts; Weekend 15)
# ---------------------------------------------------------------------------
bundle:
	@command -v cargo-dist >/dev/null 2>&1 || { \
	  echo "cargo-dist not installed; run: cargo install cargo-dist"; exit 1; }
	cargo dist build

# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------
# Shell-level self-check: python version, pip packages, model files, build
# artifact, and HTTP supervisor. Works even if the build or supervisor is
# broken, which is when you most need it.
doctor:
	@bash scripts/doctor.sh

# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------
smoke: demo-fixtures
	@python3 demo/smoke_test.py

demo-hello:
	@python3 demo/perception/hello.py

demo-fixtures:
	@python3 demo/fixtures/make_fixtures.py

demo-web:
	@echo "Operator dashboard: http://127.0.0.1:7000/"
	@echo "Developer sandbox:  http://127.0.0.1:7000/demo/"
	@echo "Walkthrough:        docs/DEMO.md"
	@echo "Served by arikizu-http when ui/static/index.html and demo/web/index.html exist in cwd."

demo-pi: demo-fixtures
	@bash demo/raspberrypi/run_all.sh

# ---------------------------------------------------------------------------
# Docker dev (Mac / Windows cross-OS)
# ---------------------------------------------------------------------------
docker-build:
	docker build -f Dockerfile.dev -t arikizu-dev .

docker-shell:
	@bash scripts/docker-dev.sh

docker-run:
	@bash scripts/docker-dev.sh make run

docker-smoke:
	@bash scripts/docker-dev.sh make smoke
