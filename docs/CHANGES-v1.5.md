# Arikizu v1.5

## v1.5.10 (zero CI, clearer prereqs, device-neutral framing)

Three cleanups based on repo visibility:

1. Removed security.yml workflow entirely. All CI gone; cargo-audit was
   failing on scaffolded placeholder code and nothing good comes from
   red X on a repo page at Weekend 3. Kept dependabot.yml (config
   only, no checks fire).

2. README prereqs are now a dedicated section with exact install
   commands for Rust, uv, system packages (per platform), and swap
   (if under 4 GB RAM). Was one line; now the four tools people need
   are each callable in one copy-paste block.

3. New "Where it runs" table in README names all five supported
   device families (Jetson Orin Nano / AGX, Mac Apple Silicon / Intel,
   Linux x86_64, Pi 4/5, Windows via WSL2). Added a one-liner that
   the current demo targets Pi only because that is the hardware I
   have in hand; the binary itself runs on any of them.

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
