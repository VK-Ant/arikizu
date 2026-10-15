# Arikizu v1.5

## v1.5.31 (make it visible when things are broken)

The user's complaint on v1.5.30 was "basically no vision model is loaded,
no detection or segmentation, audio keyword 'I need help' is not
detected". The real problem wasn't the demos: it was that when a model
file is missing or a worker is wedged, nothing on the page said so, so
every failure looked like the same mystery. v1.5.31 makes every failure
mode self-reporting.

**Diagnostics**

- New `scripts/doctor.sh`: one-shot self-check. Prints PASS/FAIL for
  python version (<3.14 for llama-cpp wheels), onnxruntime, numpy,
  pillow, llama-cpp-python, msgpack, each required model file (with
  size check so a half-downloaded file fails loud), the arikizu
  binary, and the supervisor HTTP endpoint. Each FAIL row prints
  the exact fix command.
- `make doctor` now runs the shell script (works even when the build
  or supervisor is broken).

**Visible model banners on demo pages**

- Vision page shows a top banner: green dot "vision model loaded:
  yolov8n.onnx" or red dot "no vision model loaded - fix: run
  scripts/download-default-models.sh".
- Audio page shows the same for the Silero VAD model.
- Demo hub home page shows a Diagnostics section with one row per
  worker: READY (loaded) / MISSING (download command) / OFFLINE
  (supervisor down).

**Real keyword matching on audio demo**

The VAD-heuristic match from v1.5.30 was a lie: it flagged every speech
segment as a hit for every keyword in the list, which is why saying
"I need help" with "help" in the keyword list didn't light up (the
indicator pulsed on every utterance, not just the one that matched).

- Audio demo now uses the browser's built-in Web Speech API for
  phonetic keyword matching. Works offline in Chrome and Edge, no
  download needed. The live transcript shows what the browser heard,
  and keyword hits trigger the KW indicator with the matched word.
- Server `audio.keyword_spot` accepts `transcript=` for real
  substring matching and logs hits to the audit log; the dishonest
  VAD-heuristic fallback is gone.
- New `audio.backends` and `reasoning.backends` capabilities expose
  which model files are loaded, so the diagnostics panel can show it.

## v1.5.30 (demo hub trimmed to 4)

Removed the demos people were skipping:

- Vision search (audit-log search)
- Timeseries (chart + forecast)
- Guard (PII scan + redact)
- Eval (predicted vs expected)
- Memory (session browser)
- JSON sandbox (raw worker testing)
- Runtime JSON link
- Audit log JSON link

Kept the four that are the core story:

1. **Vision** - live webcam object detection
2. **Audio** - live mic VAD + keyword spotting
3. **Documents** - PDF upload + ask question
4. **Reasoning** - local LLM chat

Plus the one-click smoke test at the bottom.

The removed demos still work by direct URL (/demo/eval_view.html etc.)
and remain in the operator dashboard on the home page. They just do
not clutter the developer hub where new users start.

v2 will polish these four, then add the next feature per weekend
instead of showing everything at once.

## v1.5.29 (fixture image path + audio threshold)
## v1.5.28 (segmentation dropdown + Vision Search fix)
## v1.5.27 .. v1.5 (prior history)
