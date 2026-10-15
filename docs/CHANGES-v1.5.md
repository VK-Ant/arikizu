# Arikizu v1.5

## v1.5.9 (ready to publish)

Three changes based on first-publish feedback:

1. Removed three CI workflows that were failing on push:
   - `.github/workflows/build.yml` (Rust + Python + UI matrix build)
   - `.github/workflows/image.yml` (Pi image build)
   - `.github/workflows/release.yml` (cargo-dist release)
   
   These were premature. CI makes sense once the project is stable
   enough that regressions matter. Right now, failing checks on the
   repo page just look bad. Re-add when ready (Weekend 15 planned).
   Kept `security.yml` (CodeQL + dependabot) because those were
   mostly passing and are useful signal.

2. License is now Apache 2.0.
   - Added `LICENSE` file with the full Apache 2.0 text.
   - Updated README License section to point at it.
   - Copyright notice: "Copyright 2026 Venkatkumar Rajan (VK-Ant)".

3. Replaced the detailed Status section with a Roadmap table.
   - The old "Live today" bullets listed basics as achievements, which
     reads odd on a published project.
   - New Roadmap table shows what each future weekend brings; what
     works today is implied by the README being usable.

## v1.5.8 (generic model names in prose)
## v1.5.7 (humanized docs)
## v1.5.6 (edge-device setup guide)
## v1.5.5 (beginner Pi guide)
## v1.5.4 (positioning + screenshots)
## v1.5.3 (architecture reference)
## v1.5.2 (brand assets)
## v1.5.1 (docs refresh)
## v1.5 (dashboard release)
