# Arikizu Quickstart

Pi-first. The scaffold's final home is a Raspberry Pi (or Jetson), so test
there directly. If you don't have a Pi handy or want faster iteration on
Mac/Windows, see the Docker-dev section at the bottom.

Order matters. Finish the Pi section before posting anything about
"working on a Pi."

---

## Path A: Raspberry Pi 4 (4 GB+), Pi 5, or Jetson Orin Nano (recommended)

### A.1  Prepare the Pi

Flash Raspberry Pi OS 64-bit Lite with Raspberry Pi Imager.

In the Imager's settings cog (gear icon) BEFORE writing:

- [x] Set hostname: `arikizu-dev`
- [x] Enable SSH; use password or key
- [x] Set user / password
- [x] Configure Wi-Fi (your SSID + password)
- [x] Set locale and timezone (Asia/Kolkata)

Flash, boot, wait 60 s. From your Windows laptop:

```
ssh pi@arikizu-dev.local
```

Jetson Orin Nano: use the stock JetPack 6 image.
Jetson AGX Orin: same.
Jetson Nano (original 2019): don't; NVIDIA EOL'd it. Use a different Pi.

### A.2  Install toolchains on the Pi

```
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git curl pkg-config libssl-dev unzip \
                    python3-picamera2 python3-opencv alsa-utils libportaudio2 \
                    v4l-utils
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l
```

### A.3  Add swap (required on 4 GB Pi for the Rust link step)

```
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && \
sudo mkswap /swapfile && sudo swapon /swapfile
echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
```

Skip this on Pi 5 (8 GB) and Jetson AGX (32 GB+).

On Jetson Orin Nano, instead do:

```
sudo nvpmodel -m 0 && sudo jetson_clocks
sudo fallocate -l 8G /swapfile && sudo chmod 600 /swapfile && \
sudo mkswap /swapfile && sudo swapon /swapfile
```

### A.4  Copy or clone Arikizu

```
# From your Windows laptop (PowerShell or WSL)
scp arikizu-v1.5.zip pi@arikizu-dev.local:~/

# Back on the Pi
cd ~ && unzip arikizu-v1.5.zip && cd arikizu
```

Or clone the public repo once it's up:

```
git clone https://github.com/VK-Ant/arikizu
cd arikizu
```

### A.5  Hardware probe

```
python3 demo/raspberrypi/probe.py
```

Expected on a Pi 4 with a Pi Camera 3 and a USB mic:

```
OK   device         Raspberry Pi 4 Model B Rev 1.5
OK   /dev/video*    /dev/video0
OK   picamera2      importable
OK   alsa card      card 0: USB [USB PnP Sound Device]
```

A `--` (double dash) next to a camera or mic is fine for a first run; the
demos fall back to fixtures.

### A.6  GPU auto-detect + default models

```
scripts/install-runtime.sh                      # detects Pi/Jetson, installs matching runtime
scripts/download-default-models.sh --tier minimum   # yolov8n + silero_vad, ~8 MB
```

On Pi: installs `onnxruntime` CPU. On Jetson: installs `onnxruntime-gpu` from the Jetson AI Lab index.

### A.7  Config (trim for 4 GB Pi)

```
cp arikizu.yaml.example arikizu.yaml
nano arikizu.yaml
```

For Pi 4 (4 GB), keep only these workers (everything else wastes RAM):

```yaml
workers:
  - name: test
    python: uv
    module: test_worker
    args: [run, --package, test-worker, python, -m, test_worker]
    cwd: ./workers
  - name: vision
    python: uv
    module: vision_worker
    args: [run, --package, vision-worker, python, -m, vision_worker]
    cwd: ./workers
    env:
      ARIKIZU_MODELS_DIR: /home/pi/arikizu/models
      ARIKIZU_VISION_MODEL: /home/pi/arikizu/models/yolov8n.onnx
  - name: guard
    python: uv
    module: guard_worker
    args: [run, --package, guard-worker, python, -m, guard_worker]
    cwd: ./workers
  - name: timeseries
    python: uv
    module: timeseries_worker
    args: [run, --package, timeseries-worker, python, -m, timeseries_worker]
    cwd: ./workers
```

Pi 5 (8 GB) or Jetson: keep all workers, but still skip `reasoning` unless a local LLM runtime is running on the Pi (which is slow: see `docs/MODEL_STRATEGY.md`).

### A.8  Build

```
scripts/check_prereqs.sh
scripts/bootstrap.sh
```

Build time by device:

| Device              | First build  |
| ------------------- | ------------ |
| Pi 4 (4 GB)         | 20-30 min    |
| Pi 5 (8 GB)         | 10-15 min    |
| Jetson Orin Nano    | 20-25 min    |
| Jetson AGX Orin     | 8-12 min     |

The link step is where the Pi struggles. Swap (A.3) is what lets it finish.

### A.9  Run and verify

Terminal 1 on the Pi:

```
make run
```

Expected end:

```
INFO addr=127.0.0.1:7000 starting HTTP server
INFO serving demo sandbox at /demo
```

Terminal 2 on the Pi (or a second ssh session):

```
make smoke
```

Expected summary:

```
3 live   8 placeholder   0 failing   N skipped
```

Zero FAIL is the only mandatory line.

### A.10  Dashboard from your Windows laptop

Back on Windows (browser):

```
http://arikizu-dev.local:7000/            operator dashboard (home)
http://arikizu-dev.local:7000/demo/       developer sandbox (one page per capability)
http://arikizu-dev.local:7000/api/v1/status   runtime JSON
```

The operator dashboard is the one your users land on: greeting, 6
capability cards, recent activity, system status. The developer sandbox
is where you test or debug a specific capability by hand.

If `arikizu-dev.local` doesn't resolve on Windows, use the Pi's IP: run
`hostname -I` on the Pi.

### A.11  Walk through the demos

See [`docs/DEMO.md`](docs/DEMO.md) for a click-by-click guide to every
view. Vision live, audio waveform + VAD, document extraction, time-series
forecasting, reasoning chat, memory recall, PII scan, eval scoring.

### A.12  Real vision project (optional, highly recommended)

With the runtime up and a Pi Camera attached, see
[`docs/PI_VISION_TUTORIAL.md`](docs/PI_VISION_TUTORIAL.md) for a 1-hour
end-to-end project: Pi Camera to the vision model to annotated detections to
dashboard to approval gate.

---

## Path B: Local dev on Mac or Linux (if you have one)

If you have a Mac or Linux laptop and want faster iteration:

### Mac (M-series or Intel)

```
xcode-select --install
brew install git pkg-config openssl
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l
cd arikizu && scripts/bootstrap.sh && cp arikizu.yaml.example arikizu.yaml && make run
```

### Linux x86_64

```
sudo apt install -y build-essential git curl pkg-config libssl-dev
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL -l
cd arikizu && scripts/bootstrap.sh && make run
```

Same `make smoke` from there.

---

## Path C: Docker-dev (Windows laptop, no Rust install)

Pi can't realistically run Docker for Arikizu (daemon RAM overhead eats
your budget). But Mac or Windows laptop development IS a good Docker use
case: one command, no Rust install, same build inside.

### C.1  Install Docker Desktop

- Windows: Docker Desktop with WSL2 backend
- macOS: Docker Desktop (native Apple Silicon or Intel)
- Linux: `sudo apt install docker-ce` or distro equivalent

### C.2  Build the dev image and go

```
cd arikizu
scripts/docker-dev.sh make build       # cross-compiles inside the container
scripts/docker-dev.sh make run         # dashboard at http://localhost:7000
```

That's it. The container mounts the current directory, preserves the
Rust `target/` cache in a Docker volume (so rebuilds are fast), and uses
`--net=host` so the dashboard is reachable from your host browser.

### C.3  Why not Docker on the Pi

- Docker daemon idles at ~150 MB RAM. On a 4 GB Pi that's 4% gone for nothing.
- Layered FS churns SD cards; writes 2-3x more bytes than native.
- The flashable image (Weekend 15) ships Arikizu as a systemd service directly, same as Home Assistant OS. Docker would be an extra layer that doesn't help.
- Docker arm64 images are not well-tested for every runtime (TensorRT especially); native install dodges that.

For the Pi, native. For Mac/Windows dev, Docker is fine.

---

## Pass criteria (any path)

Promotable when:

- [x] `scripts/check_prereqs.sh` says "all prerequisites satisfied"
- [x] `scripts/bootstrap.sh` finished without error
- [x] `make run` reaches "HTTP server listening" and logs both
      "serving demo sandbox at /demo" and "serving operator dashboard at /"
- [x] `make smoke` shows 0 FAIL
- [x] Operator dashboard renders at `http://<host>:7000/`
- [x] Developer sandbox renders at `http://<host>:7000/demo/`
- [x] One demo view (any one from [`docs/DEMO.md`](docs/DEMO.md)) returns real data

That's the baseline. Everything else is iteration from there.

## Troubleshooting

| Symptom                                       | Fix                                                                     |
| --------------------------------------------- | ----------------------------------------------------------------------- |
| `scripts/check_prereqs.sh` says uv missing    | Re-run the uv curl line, then `exec $SHELL -l`                           |
| `make run` worker spawn fails                 | `cd workers && uv sync --all-packages`                                   |
| `make smoke` says connection refused          | `make run` not actually running                                          |
| `make smoke` has FAIL on reasoning            | a local LLM runtime not installed: delete the `reasoning` block from `arikizu.yaml`  |
| Pi OOM during cargo build                     | Add 4-8 GB swap (A.3), retry                                             |
| `arikizu-dev.local` doesn't resolve           | Use the Pi IP (`hostname -I` on Pi); check mDNS (`avahi-daemon` running) |
| `vision_pi.py` says "camera index out of range"| No camera attached; fallback kicks in automatically                     |
| Docker build hangs                            | `docker system prune` and retry                                          |
| Jetson onnxruntime-gpu install fails          | JetPack 6 only; JetPack 4/5 need different index URL (not supported)     |

For anything else, open an issue with the full output of
`scripts/check_prereqs.sh` and `arikizu status --dev --json`.
