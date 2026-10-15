# Arikizu demos

Everything in this folder is for testing and poking. Nothing here is part
of the shipped runtime.

Order to follow after your first `make run`:

1. **Prove IPC is live** — `python3 demo/perception/hello.py` (three PASS lines).
2. **"Is everything working?"** — `python3 demo/smoke_test.py` (one line per capability).
3. **Visual sandbox** — open `http://127.0.0.1:7000/demo` in a browser.
4. **Pi hardware tests** — `python3 demo/raspberrypi/probe.py` and friends.

## Zero-dep web sandbox at /demo

Arikizu serves `demo/web/index.html` at `http://127.0.0.1:7000/demo` whenever
that file exists in the directory it was launched from. No build step,
no streamlit, no npm — just HTML + fetch. Each worker is a tab; each
capability is a card with a JSON payload editor and a Call button. Results
show PASS / WAIT / FAIL and a timing badge.

The home tab has a one-click smoke test grid.

## CLI demos

Zero third-party deps — all use urllib.

| Script                                 | What it does                                      |
| -------------------------------------- | ------------------------------------------------- |
| `smoke_test.py`                        | Fires every capability once; prints the grid      |
| `perception/hello.py`                  | `test.echo`, `test.add`, `test.slow`              |
| `perception/vision_demo.py`            | `vision.detect`, `.ocr`, `.caption`               |
| `perception/audio_demo.py`             | `audio.transcribe`, `.vad`, `.keyword_spot`       |
| `perception/docs_demo.py`              | `docs.extract`, `.table`, `.search`               |
| `perception/reasoning_demo.py`         | `reasoning.answer`, `.summarize`, `.complete`     |
| `perception/timeseries_demo.py`        | `timeseries.forecast`, `.detect_anomaly`          |
| `perception/memory_demo.py`            | `memory.update`, `.recall`, `.reward`             |
| `perception/guard_demo.py`             | `guard.scan`, `.redact`, `.audit`                 |
| `perception/eval_demo.py`              | `eval.score`, `.compare`, `.golden_run`           |
| `pipelines/two_stage.py`               | Runs the configured pipeline                      |
| `pipelines/approval_gate.py`           | Runs + approves the pending gate in-script        |

## Raspberry Pi end-to-end tests

Separate folder because the hardware matters:

| Script                                     | What it does                                                   |
| ------------------------------------------ | -------------------------------------------------------------- |
| `raspberrypi/probe.py`                     | Pi model, memory, cameras, mics, library importability         |
| `raspberrypi/vision_pi.py`                 | Camera -> frame on disk -> `vision.detect`                     |
| `raspberrypi/audio_pi.py`                  | Mic -> WAV on disk -> `audio.transcribe`                       |
| `raspberrypi/run_all.sh`                   | All three in sequence                                          |

See `raspberrypi/README.md` for the install matrix (picamera2, opencv,
sounddevice, alsa-utils) and the full flag reference.

Both Pi scripts fall back gracefully when no camera or mic is attached —
they use the fixtures and still exercise the HTTP path.

## Fixtures (stdlib-generated)

`demo/fixtures/make_fixtures.py` writes:

- `sample.png` — 8x8 red PNG for vision calls
- `sample.wav` — 1 second 440 Hz sine for audio calls
- `sample.txt` — a short factory-report text for docs calls
- `series.json` — 120-point sine with one anomaly for timeseries

No numpy/PIL dependency.

## Statuses

Every demo and the web sandbox classifies results the same way:

| Status | Meaning                                               | Normal when                        |
| ------ | ----------------------------------------------------- | ---------------------------------- |
| PASS   | real result (worker and library both live)            | always                             |
| WAIT   | placeholder note returned                             | library not yet wired              |
| SKIP   | 503 "worker not running" or 404                       | you've turned off that worker      |
| FAIL   | HTTP error, non-JSON, timeout, or `error` field       | never — investigate every FAIL     |

A healthy session has 0 FAIL. Everything else is choice.

## Make targets

```
make smoke          # python3 demo/smoke_test.py
make demo-hello     # python3 demo/perception/hello.py
make demo-fixtures  # python3 demo/fixtures/make_fixtures.py
make demo-pi        # bash demo/raspberrypi/run_all.sh
make demo-web       # just prints the URL to open
```
