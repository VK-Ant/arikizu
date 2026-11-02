# Setup, Deployment, and Models

Everything you need to install Arikizu, deploy it onto target hardware, and understand which models it uses.

- [Part 1 — Setup](#part-1--setup)
- [Part 2 — Distribution](#part-2--distribution)
- [Part 3 — Models](#part-3--models)

---

## Part 1 — Setup


<p align="center">
  <img src="assets/logo-400.png" alt="Arikizu" width="140">
</p>

Arikizu runs on five device families. Pick yours and follow the steps.
Everything below assumes zero Linux knowledge; every command says what
to type, what you should see, and what to do if it fails.

| Device                                 | Code name used below | Time to running dashboard |
| -------------------------------------- | -------------------- | ------------------------- |
| Raspberry Pi 4 (4 GB) or Pi 5          | `pi`                 | ~2 hours                  |
| Nvidia Jetson Orin Nano / AGX Orin     | `jetson`             | ~90 min                   |
| Mac (Apple Silicon M1-M4 or Intel)     | `mac`                | ~15 min                   |
| Linux x86_64 (laptop, desktop, server) | `linux`              | ~15 min                   |
| Windows via WSL2                       | `wsl`                | ~20 min                   |

> Native Windows is not supported. Rust and Unix sockets need a
> real Linux kernel. Use WSL2 (Windows Subsystem for Linux) instead,
> which gives you a real Linux running inside Windows.

Each section below either applies to all devices (shared) or to one
specific device family. Device tags at the start of each subsection
tell you which.

---

## Section 1: Prepare your device

### 1A: [pi] If you have a blank SD card (new Pi, or want to start fresh)

Full flash walkthrough with Raspberry Pi Imager. 20 minutes.

1. Download Raspberry Pi Imager from `raspberrypi.com/software`.
2. Insert the SD card into your computer.
3. In Imager: Choose Device = Pi 4 or Pi 5, Choose OS = **Raspberry Pi
   OS Lite (64-bit)**, Choose Storage = your SD card.
4. Click "Edit Settings" and set:
   - Hostname: `arikizu-dev`
   - Username / password you will remember
   - WiFi SSID and password
   - Timezone: `Asia/Kolkata`
   - Services tab: enable SSH, password authentication
5. Click Save, Yes, Yes. Wait ~10 min for the write + verify.
6. Insert the SD card into the Pi, plug in power, wait 3 min.

### 1B: [pi] If your Pi already has Raspberry Pi OS installed

Skip the flash. Just confirm your OS is the right version:

```
uname -m
```

- `aarch64` -> you are good, go to Section 2.
- `armv7l` -> you have 32-bit Pi OS, which does not work for Arikizu
  (no ONNX wheels). Follow 1A instead.

Then:

```
cat /etc/os-release | grep PRETTY
```

Should say `Debian GNU/Linux 12 (bookworm)`. If older (Buster,
Bullseye), re-flash to Bookworm using 1A.

### 1C: [jetson] Set up JetPack

Jetson devices run NVIDIA's JetPack OS (Ubuntu + Nvidia drivers +
CUDA).

**For Jetson Orin Nano Developer Kit or AGX Orin:**

1. Download the Jetson JetPack 6 image from `developer.nvidia.com/embedded/jetpack`.
2. Flash with the SDK Manager (Nvidia's tool) or Balena Etcher if you
   want command-line only.
3. Boot the Jetson, complete first-run setup (Ubuntu desktop appears).
4. Open a terminal on the Jetson or SSH in.
5. Max out performance (important, Jetson defaults are power-saving):
   ```
   sudo nvpmodel -m 0
   sudo jetson_clocks
   ```
6. Confirm you are on 64-bit with GPU:
   ```
   uname -m         # aarch64
   nvidia-smi       # should show your GPU
   ```

**Jetson Nano (original, 2019):** not supported. Nvidia EOL'd it; use
a different device.

### 1D: [mac] You just need macOS

No flashing needed. macOS already has what we need. Open the Terminal
app (Cmd+Space, type "terminal", Enter).

Confirm:

```
uname -m
```

- `arm64` -> Apple Silicon (M1-M4). Good.
- `x86_64` -> Intel Mac. Also good, slower.

### 1E: [linux] You just need a 64-bit Linux

Open a terminal (Ctrl+Alt+T on most distros). Confirm:

```
uname -m
cat /etc/os-release | grep PRETTY
```

Should be `x86_64` or `aarch64`. Tested on Ubuntu 22.04, Debian 12,
Fedora 40. Other distros work; package names may differ.

### 1F: [wsl] Install WSL2 on Windows (one time)

Open PowerShell as administrator:

```
wsl --install
```

Press Enter. Windows installs WSL2 and Ubuntu. Reboot.

After reboot, Ubuntu's first-run asks for a username and password.
Pick anything you will remember.

From now on, open "Ubuntu" from your Start menu to get a Linux shell
running inside Windows. Everything below runs there.

---

## Section 2: Connect to your device

### 2A: [pi, jetson] SSH from your main computer

Open a terminal on your main computer:

- Windows: Start -> type `powershell` -> Enter
- Mac: Cmd+Space -> `terminal` -> Enter
- Linux: Ctrl+Alt+T

Type:

```
ssh pi@arikizu-dev.local
```

(For Jetson, use the username and hostname you set during JetPack
setup, e.g. `ssh user@jetson-nano.local`.)

First-time only, type `yes` to accept the fingerprint. Then enter the
password you set. Nothing shows as you type the password; that is
normal.

If `.local` does not resolve, find the IP from your router admin
page and use the IP instead: `ssh pi@192.168.1.45`.

### 2B: [mac, linux, wsl] You already have a terminal

No SSH needed. You are running the terminal directly on the device.
Skip to Section 3.

---

## Section 3: Install everything the device needs

Device-specific commands. Pick the subsection for your device.

### 3A: [pi, jetson] Debian / Ubuntu based

```
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git curl pkg-config libssl-dev unzip \
                    python3-pip python3-venv \
                    python3-picamera2 python3-opencv alsa-utils libportaudio2 \
                    v4l-utils
```

For Jetson, also add CUDA toolkit stuff that JetPack usually already
installed. Verify:

```
nvcc --version
```

Should say `release 12.X` or similar.

### 3B: [mac] Homebrew

Install Homebrew if you don't have it:

```
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Then:

```
xcode-select --install
brew install git pkg-config openssl portaudio
```

### 3C: [linux] Debian / Ubuntu / Fedora

**Debian or Ubuntu:**

```
sudo apt update
sudo apt install -y build-essential git curl pkg-config libssl-dev \
                    python3-pip python3-venv libportaudio2
```

**Fedora:**

```
sudo dnf install -y gcc gcc-c++ git curl openssl-devel pkgconfig \
                    python3-pip python3-virtualenv portaudio-devel
```

### 3D: [wsl] Same as linux Debian/Ubuntu

Inside your Ubuntu shell, use the Debian / Ubuntu commands from 3C.

### 3E: [all] Install Rust

```
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Press Enter when it asks for a choice (standard installation is
correct).

Then:

```
source "$HOME/.cargo/env"
```

### 3F: [all] Install uv

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3G: [all] Reload shell

```
exec $SHELL -l
```

### 3H: [pi only] Add 4 GB swap (critical for the build)

Pi 4 (4 GB RAM) cannot link the Rust binary without more memory.
Add 4 GB of swap:

```
swapon --show
```

If the SIZE column shows less than 4G:

```
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo "/swapfile none swap sw 0 0" | sudo tee -a /etc/fstab
```

Skip this entire step on Pi 5 (8 GB), Jetson, Mac, Linux x86 with
8+ GB RAM.

### 3I: [all] Verify

```
rustc --version        # expect 1.80+
uv --version           # expect 0.4+
python3 --version      # expect 3.11+
free -h                # or 'top -l 1 | head' on Mac
```

If any of these fail, fix that one before continuing. See
Troubleshooting at the bottom.

---

## Section 4: Clone and build Arikizu

Same on every device from here on.

### 4.1 Clone

```
git clone https://github.com/VK-Ant/arikizu
cd arikizu
```

### 4.2 Prereq check

```
scripts/check_prereqs.sh
```

Expected last line: `all prerequisites satisfied`.

### 4.3 Install Python workers

```
scripts/bootstrap.sh
```

Takes 10-15 min on Pi, 5 min on Jetson/Mac/Linux. uv downloads every
Python package each worker needs.

### 4.4 Build the Rust binary

```
make build
```

Build time by device:

| Device                 | First build  |
| ---------------------- | ------------ |
| Pi 4 (4 GB)            | 20-30 min    |
| Pi 5 (8 GB)            | 10-15 min    |
| Jetson Orin Nano       | 15-20 min    |
| Jetson AGX Orin        | 6-10 min     |
| Mac M1-M4              | 3-5 min      |
| Mac Intel              | 8-12 min     |
| Linux x86 modern CPU   | 3-8 min      |

Later rebuilds are seconds because of cargo's cache.

### 4.5 Config and models

```
cp arikizu.yaml.example arikizu.yaml
scripts/download-default-models.sh --tier minimum
```

### 4.6 Device-specific tuning

**[pi] 4 GB Pi: trim workers to save RAM.**

```
nano arikizu.yaml
```

Delete or comment out `reasoning` and `eval` workers. Keep: test,
vision, audio, docs, timeseries, memory, guard.

Also set vision input size to 320 for 3x speed:

```yaml
  - name: vision
    env:
      ARIKIZU_VISION_INPUT_SIZE: "320"
```

**[jetson] Enable GPU backend.**

```
scripts/install-runtime.sh
```

Detects the Jetson, installs `onnxruntime-gpu` from the Jetson AI Lab
index. Vision inference goes from CPU (slow) to GPU (fast).

**[mac] Enable CoreML backend.**

```yaml
  - name: vision
    env:
      ARIKIZU_BACKEND_PREFER: "coreml,onnx_cpu"
```

Apple Silicon with CoreML runs a compact vision model at ~30 FPS.

**[linux with NVIDIA GPU] Enable CUDA.**

```
pip install --upgrade onnxruntime-gpu --break-system-packages
```

Then:

```yaml
  - name: vision
    env:
      ARIKIZU_BACKEND_PREFER: "onnx_gpu,onnx_cpu"
```

**[linux without GPU, wsl, mac Intel] Nothing extra.** CPU is the
default backend; no changes needed.

---

## Section 5: Run and verify

Same on every device.

### 5.1 Launch

```
make run
```

Three log lines near the end:

```
INFO ant_router: loaded capability registry count=29
INFO ant_http: serving demo sandbox at /demo
INFO ant_http: serving operator dashboard at /
INFO ant_http: HTTP server listening addr=127.0.0.1:7000
```

Leave this terminal alone; Ctrl+C stops Arikizu.

### 5.2 Open the dashboard

In your browser (on any device on the same network):

- **If running on your own laptop (mac, linux, wsl):**
  `http://127.0.0.1:7000/`
- **If running on a remote device (pi, jetson, linux server):**
  `http://arikizu-dev.local:7000/` or the device's IP

You see the Arikizu dashboard. The top-right chip auto-detects your
device and shows "Raspberry Pi", "Jetson", "Mac", or "Linux".

### 5.3 Smoke test (second terminal)

For Pi / Jetson / remote Linux, open a second SSH session. For
Mac / Linux / WSL, open a new terminal tab. Then:

```
cd arikizu
make smoke
```

Expected: `0 failing`.

### 5.4 Walk through the demos

Click any capability card on the dashboard. The matching view opens.
Click Start / Analyze / Score. Results appear.

See [`DEMO.md`](DEMO.md) for a click-by-click walkthrough of every
view.

---

## Section 6: Turn off, turn on, verify

### 6.1 Stop Arikizu

In the terminal running `make run`, press **Ctrl+C**.

### 6.2 [pi, jetson] Shut the device down properly

```
sudo shutdown now
```

Wait 30 seconds. LEDs stop. Then unplug power.

Never pull the plug on a running Pi or Jetson; the SD card / eMMC
can corrupt.

### 6.3 [mac, linux, wsl] Nothing special

Close the terminal or shut down your computer normally. Arikizu is
just a process; nothing extra to protect.

### 6.4 Turn on and verify

Plug in power (pi/jetson), wait 2 min, SSH back in. Or just open a
new terminal (mac/linux/wsl).

```
cd arikizu
make run
```

You should see the same three startup lines. Open the dashboard.
Everything still works.

### 6.5 Auto-start on boot (optional, pi/jetson/linux)

Make Arikizu start automatically every time the device powers on:

```
sudo cp packaging/systemd/arikizu.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now arikizu
```

Check status:

```
sudo systemctl status arikizu
```

Should say `Active: active (running)`.

Mac has launchd instead of systemd; see
[`packaging/launchd/README.md`](../packaging/launchd/README.md) when
that is written.

---

## Section 7: What each device is good at

Not all devices are equal. Set expectations correctly.

| Device               | Vision | Audio    | Reasoning   | Video Studio | Overall             |
| -------------------- | ------ | -------- | ----------- | ------------ | ------------------- |
| Pi 4 (4 GB)          | 2-3 FPS CPU | VAD realtime, the ASR model 5x slow | LAN gateway only | 2-3 FPS, rule-based actions only (no VLM) | Entry level; proves it all works |
| Pi 5 (8 GB)          | 5-7 FPS CPU | VAD realtime, the ASR model 2x slow | Small LLM OK  | 7-9 FPS, rule-based only | Comfortable for one line / room |
| Jetson Orin Nano     | 25-40 FPS GPU | the ASR model near realtime | Local 3B LLM | 20-30 FPS live + Qwen VL at ~1.8s/prompt | Multi-camera lane / clinic |
| Jetson AGX Orin      | 60+ FPS GPU | Instant | Local 7B LLM | 60+ FPS + Qwen VL at ~0.6s/prompt | Factory floor / vehicle |
| Mac M-series         | 15-30 FPS CoreML | Instant | Local 7B LLM | 15-25 FPS + Qwen VL at ~0.9s | Dev + demo + personal use |
| Mac Intel            | 5-10 FPS CPU | Fine | LAN gateway | 5-10 FPS, rule-based only | Dev + demo only |
| Linux x86 + NVIDIA   | 50+ FPS GPU | Instant | Local 13B+ LLM | 30+ FPS + Qwen VL at ~0.4s | Workstation / small server |
| Linux x86 no GPU     | 5-15 FPS CPU | Fine | LAN gateway | 10-15 FPS + Qwen VL at ~2.5s | Dev + demo + light prod |
| WSL on Windows       | 5-15 FPS CPU | Fine (needs ALSA passthrough) | LAN gateway | 10-15 FPS + Qwen VL at ~3.5s | Dev only |

The dashboard and API are identical on all of them. Picking a
beefier device just gives you more throughput; the code never
changes.

---

## About pip install (common question)

**You do not run `pip install arikizu`.** Arikizu is not a Python
package. It is a Rust binary plus Python workers plus a web dashboard,
packaged as one runtime.

The Python packages the workers need are installed by
`scripts/bootstrap.sh` in step 4.3. uv does this automatically.

If you want to add a Python package to one worker (for example, add
`torch` to the vision worker), use uv:

```
cd workers
uv add torch --package vision-worker
```

Then restart Arikizu.

---

## Common problems and simple fixes

| Problem                                              | Fix                                                                 |
| ---------------------------------------------------- | ------------------------------------------------------------------- |
| `command not found: cargo` or `uv`                   | Shell didn't pick up installs. Type `exec $SHELL -l`.               |
| `Could not resolve hostname arikizu-dev.local`       | Network doesn't support .local. Find IP from router, use IP directly.|
| `make build` fails near the end on Pi 4              | Out of memory. Confirm 4 GB swap: `swapon --show`. See 3H.          |
| `make run` worker spawn fails                        | Python packages missing. `cd workers && uv sync --all-packages`.    |
| Vision view shows a fixture, not real camera         | Attach camera + reboot. On Pi: `python3 demo/raspberrypi/probe.py`. |
| Dashboard loads but shows "0 workers"                | Rust up but workers failed. Check `make run` output for Python error. |
| `No space left on device`                            | SD/disk full. `cargo clean` frees 3+ GB.                            |
| Pi reboots randomly                                  | Weak power. Use official 15W Pi adapter, not phone chargers.         |
| Build takes >45 min on Pi                            | Slow SD. `sudo hdparm -t /dev/mmcblk0`; replace if under 20 MB/s.   |
| Mac: `clang: error: linker command failed`           | Xcode CLT missing. `xcode-select --install`.                        |
| Linux: `error: cannot find -lssl`                    | Install `libssl-dev` (Debian) or `openssl-devel` (Fedora).          |
| WSL: `curl: Failed to connect`                       | Network. Restart WSL from PowerShell: `wsl --shutdown`, reopen.     |
| Jetson: `onnxruntime-gpu` fails to install           | JetPack 6 only. JetPack 4/5 need different index URL (not supported). |

---

## When to ask for help

If you get stuck:

1. Copy the exact command you ran.
2. Copy the exact error message you saw.
3. Share both.

Guessing wastes time. The exact text usually points to the fix in
seconds.

---

## What's next

Once your dashboard is up:

1. [`DEMO.md`](DEMO.md): click through every capability. 15 min.
2. [`DEMOS.md`](DEMOS.md): Pi Camera +
   the vision model + approval gate. 1 hour.
3. [`BRING_YOUR_OWN_MODEL.md`](BRING_YOUR_OWN_MODEL.md): swap in your
   trained ONNX / TFLite / TensorRT model. (coming in v1.5.6)
4. [`ARCHITECTURE.md`](ARCHITECTURE.md): understand what's under the hood.
5. [`WHY.md`](WHY.md): real-world deployment patterns.

This is the whole setup guide for every edge device Arikizu runs on.
Pick yours, follow the tagged subsections, and you have a working AI
runtime in anywhere from 15 min (laptop) to 2 hours (Pi 4).

---

## Part 2 — Distribution


Both of VK's concerns, written down so no one forgets.

**Problem 1.** A Raspberry Pi Zero 2 W or Pi 4 (1 GB) cannot realistically
compile Rust. First build of a 9-crate workspace with LTO needs 2-3 GB RAM
during link; on a 1 GB device it swaps to death and takes hours, if it
finishes at all. "Build from source on the Pi" is a developer flow, not an
operating-system flow.

**Problem 2.** The moment Arikizu is shipped as a `.exe`, `.dmg`, or even a
plain Linux binary that lands in `/usr/local/bin/arikizu`, people call it an
SDK or a utility. It stops looking like an OS. OSes are flashed to disks or
pre-installed on devices.

Fix: three distribution tiers. Each has a different audience, a different
format, and a different claim.

```
Tier 1  dev binary          developer on laptop         "it's an SDK"       ← acceptable here
Tier 2  system package      sysadmin on existing Pi     "it's a daemon"     ← acceptable here
Tier 3  flashable image     end user on new device      "it's an OS"        ← this is the OS
```

Only Tier 3 earns the OS claim. The others exist to support it.

---

## Tier 1: dev binary (laptop, your dev box)

**Audience.** You and anyone else building on Arikizu. Also a reviewer who
wants to poke at it for an hour.

**Format.** One statically linked binary per OS/arch, published to GitHub
Releases:

| Asset                                   | Target               |
| --------------------------------------- | -------------------- |
| `arikizu-v0.1.0-x86_64-linux.tar.gz`    | laptop Linux         |
| `arikizu-v0.1.0-aarch64-linux.tar.gz`   | laptop ARM Linux     |
| `arikizu-v0.1.0-aarch64-macos.tar.gz`   | Apple Silicon        |
| `arikizu-v0.1.0-x86_64-macos.tar.gz`    | Intel Mac            |
| `SHA256SUMS`                            | verify every asset   |

Installer:

```
curl -fsSL https://arikizu.sh/install.sh | sh
```

Lands at `~/.arikizu/bin/arikizu`. No root required. Workers still ship
as source, so uv on the box still has to download msgpack and friends,
but there is no Rust toolchain to install.

**What this is called.** "The arikizu CLI." Or "the dev binary." Not
"Arikizu OS." The README and the docs say so.

**What this is NOT for.** A nurse on a hospital tablet. A ship engineer
on a boat. The CTO reviewing your demo on a Jetson. These people get
Tier 3.

## Tier 2: system package (existing Pi / server / Jetson)

**Audience.** A sysadmin who already runs Raspberry Pi OS or Debian and
wants Arikizu running as a service alongside everything else.

**Format.** A `.deb` package built once in CI, hosted on an APT repository:

```
echo "deb https://apt.arikizu.sh stable main" | sudo tee /etc/apt/sources.list.d/arikizu.list
curl -fsSL https://apt.arikizu.sh/arikizu.gpg | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/arikizu.gpg
sudo apt update
sudo apt install arikizu
```

The `.deb` contains:

- `/usr/bin/arikizu`               : the cross-compiled aarch64 binary
- `/usr/lib/arikizu/workers/*.whl` : pre-built wheels for every worker (aarch64 Python 3.11)
- `/etc/arikizu/arikizu.yaml`      : default config
- `/etc/arikizu/capabilities.toml` : default capability registry
- `/etc/arikizu/policies/`         : reference policies
- `/lib/systemd/system/arikizu.service`: the systemd unit
- `/var/lib/arikizu/`              : state dir (audit DB lives here)

Enable:

```
sudo systemctl enable --now arikizu
```

Workers are shipped as wheels, not source: zero compile step on install.
On aarch64 Python 3.11, msgpack/pydantic/httpx all have published wheels;
SightRAG/Sonarwise/etc wheels are published alongside Arikizu's.

**What this is called.** "The arikizu system package." Or "arikizu-server."
Not quite "the OS" either, but close.

## Tier 3: flashable image (the OS)

**Audience.** Everyone else. A factory supervisor opening a new Jetson.
A hospital IT person spinning up a Pi for triage. Your mother turning on
a device you handed her.

**Format.** A `.img.xz` built from Raspberry Pi OS Lite, with Arikizu
pre-installed, pre-enabled, and set up to boot straight into "ready":

```
arikizu-pi-v0.1.0.img.xz           ~400 MB compressed, 2.5 GB flashed
arikizu-pi-v0.1.0.img.xz.sig       signature
```

Flashing (Raspberry Pi Imager, Balena Etcher, dd: anything):

```
sudo rpi-imager --cli arikizu-pi-v0.1.0.img.xz /dev/sda
```

First boot (headless, 60-90 s to Arikizu-ready):

1. Pi expands rootfs on first boot
2. systemd starts the `arikizu` service
3. Arikizu reads `/etc/arikizu/arikizu.yaml`, spawns workers
4. mDNS announces `arikizu.local`
5. User opens `http://arikizu.local` in a browser

That's the install. There is no Rust to compile, no uv to invoke, no apt
to update. The user never sees a terminal unless they want to.

**What this is called.** "Arikizu Pi." Or "Arikizu OS flashed to a Pi."
This is the OS claim.

**Why this is the real deliverable.**

- Users recognize it as an OS, because it is flashed to a disk and boots
- Memory objection disappears: nothing is built on the device, ever
- One build in CI, one image, same bytes on every Pi
- Air-gapped shops love it: no network needed on install
- Updates ship as a new `.img.xz`, or OTA via the Model Manager (Weekend 15+)

---

## Build pipeline

Each tier has one source of truth: the CI run.

```
                              GitHub Actions (CI, x86_64 runners)
                              ───────────────────────────────────
                                            │
                   ┌────────────────┬───────┴────────┬──────────────────┐
                   ▼                ▼                ▼                  ▼
             Tier 1 binary    Tier 2 .deb      Tier 2 wheels      Tier 3 .img.xz
             .github/         .github/         .github/           .github/
             release.yml      debian.yml       wheels.yml         image.yml
                   │                │                │                  │
                   └────────────────┴────────────────┴──────────────────┘
                                            │
                                            ▼
                                   GitHub Releases page
                                   APT repo (apt.arikizu.sh)
                                   Image mirror (dl.arikizu.sh)
```

The pieces:

| Piece                           | Where                              | Status in v0.1  |
| ------------------------------- | ---------------------------------- | --------------- |
| Rust cross-compile aarch64      | `.github/workflows/release.yml`    | **scaffolded**  |
| Python wheel build              | `.github/workflows/wheels.yml`     | planned (W15)   |
| `.deb` build                    | `.github/workflows/debian.yml` + `packaging/debian/` | **scaffolded** |
| systemd unit                    | `packaging/systemd/arikizu.service` | **scaffolded** |
| `.img.xz` build (pi-gen)        | `.github/workflows/image.yml` + `packaging/pi-gen/` | **scaffolded** |
| APT repo signing + hosting      | out of tree                        | planned (W15)   |
| OTA image updates               | `ant-models` + manifest signing    | planned (W15)   |

Scaffolded = the file exists and documents the plan; CI runs the parts
that work today. Planned = Weekend 15 writes the real thing.

## What NOT to do

- **Don't ship a `.exe`.** No Windows target. Windows is a dev host (via WSL)
  only. "Arikizu for Windows" would make it look like a tray app.
- **Don't publish to PyPI or crates.io.** Those positions it as a library.
  Workers inside Arikizu are published, Arikizu itself is not.
- **Don't ship a Docker image as the primary surface.** Docker is for CI and
  for sysadmins who prefer it, not for the OS claim. If published, label it
  as "for development" only.
- **Don't ask the Pi to compile anything.** No pip, no cargo, no npm on first
  boot. Everything that runs on the Pi was built off-device.
- **Don't require the internet after install.** The image carries the model
  bundles for the default pipeline. Model updates come later via the
  Model Manager, which the user opts into.

## Reading the whole thing in one line

> Tier 1 is how you build it. Tier 2 is how you install it. Tier 3 is how
> you ship it. The project is an OS because of Tier 3.

---

## Part 3 — Models


Everything about picking, downloading, and running models on Arikizu.
Four topics in one doc: strategy (which LLM where), optimization (which
runtime), catalog (per worker), defaults (what works out of the box).

## 1. Strategy: do you even need an LLM?

Most Arikizu pipelines don't. Vision, OCR, VAD, extraction, embedding,
anomaly detection, PII scanning: none of these need an LLM. Only
"narrate in plain English" and "answer a free-form question" do.

Decision tree:

```
Need freeform generation?
├── No → leave reasoning worker out. Done.
└── Yes
 │
 ├── Pi Zero / Pi 3 / Pi 4 (1 GB) → LAN gateway (big machine on LAN)
 │
 ├── Pi 4 / Pi 5 (4 GB)
 │ ├── OK with 1-3 tok/s? → qwen2.5:1.5b on device
 │ └── Need faster/better? → LAN gateway
 │
 ├── Pi 5 (8 GB)
 │ ├── OK with 3-5 tok/s on 3B? → qwen2.5:3b on device
 │ └── Need 7B? → LAN gateway
 │
 └── Jetson Orin Nano / AGX → qwen2.5:7b on device (GPU, fast)
```

### Device-to-LLM matrix (realistic numbers)

| Device | Model | RAM | Tok/s |
| ------------------- | ----------------------------- | ------- | ---------- |
| Pi 4 (4 GB) | qwen2.5:0.5b-q4_K_M | 400 MB | 5-8 |
| Pi 4 (4 GB) | qwen2.5:1.5b-q4_K_M | 1 GB | 2-4 |
| Pi 5 (8 GB) | qwen2.5:3b-q4_K_M | 2 GB | 3-5 |
| Pi 5 (8 GB) | qwen2.5:7b-q4_K_M | 4.5 GB | 1-2 (slow) |
| Jetson Orin Nano | qwen2.5:7b-q4_K_M | 4.5 GB | 15-25 |
| Mac mini M2 | qwen2.5:7b-q4_K_M | 4.5 GB | 40-80 |

Q4_K_M is the sweet spot. Below Q4 the model gets stupid; above Q6 you
pay memory for ~nothing.

### LAN gateway pattern (what you'll usually use)

On a beefy LAN machine (your Mac, a mini-PC, your dev laptop):

```
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b-instruct-q4_K_M
OLLAMA_HOST=0.0.0.0:11434 ollama serve # bind to all interfaces
```

On the Pi, in `arikizu.yaml`:

```yaml
workers:
 - name: reasoning
 args: [run, --package, reasoning-worker, python, -m, reasoning_worker]
 cwd: ./workers
 env:
 ARIKIZU_OLLAMA_ENDPOINT: http://192.168.1.50:11434
 ARIKIZU_REASONING_MODEL: qwen2.5:7b-instruct-q4_K_M
```

Still "edge" by any reasonable definition. Nothing leaves your LAN.

### Cloud fallback (OpenAI-compatible APIs)

The reasoning worker auto-detects URL shape. One env change:

```yaml
env:
 ARIKIZU_OLLAMA_ENDPOINT: https://api.groq.com/openai
 ARIKIZU_REASONING_MODEL: llama-3.1-70b-versatile
 ARIKIZU_API_KEY: your_key
```

Breaks offline-first. Flag the stage in the audit log so it's auditable.

---

## 2. Runtime optimization: which inference engine

Workers call `arikizu_worker.backend.load_model(path)`. The SDK picks the
fastest runtime that's installed. Install only what you need.

### The five runtimes

| Runtime | Best on | Reads | Install |
| --------------- | ----------------------------------- | --------------------- | --------------------------------------- |
| ONNX Runtime | everywhere; universal fallback | `.onnx` | `pip install onnxruntime` (or -gpu) |
| TFLite | Pi, Coral TPU, Android | `.tflite` | `pip install tflite-runtime` |
| OpenVINO | Intel CPU/iGPU, now ARM too | `.xml`, `.onnx` | `pip install openvino` |
| TensorRT | Jetson, NVIDIA GPUs; fastest | `.engine` | comes with JetPack |
| CoreML | Apple Silicon | `.mlpackage` | `pip install coremltools` + macOS |

### Device → runtime matrix

| Device | First choice | Why |
| ----------------------------- | ----------------- | ----------------------------------- |
| Pi 4 / Pi 5 | ONNX Runtime CPU | ARM CPU; universal |
| Pi 5 + Hailo-8 | Hailo runtime | 13 TOPS for vision/audio |
| Jetson Orin / AGX | TensorRT | 40 TOPS GPU; 2x faster than ONNX GPU|
| Mac Silicon | CoreML | NPU + GPU |
| Intel CPU server | OpenVINO | +20-40% on Intel CPU |
| NVIDIA GPU server | TensorRT | Same reason as Jetson |

Install ONNX Runtime first: it runs anywhere. Layer on OpenVINO /
TensorRT / TFLite only when the hardware warrants it.

### Quantization (free speedup)

| Precision | Pi inference | Jetson | Accuracy hit |
| --------- | --------------- | ---------- | ---------------- |
| FP32 | baseline | baseline | 0% |
| FP16 | n/a on Pi CPU | 2x faster | <0.5% |
| **INT8** | **2-4x faster** | 3-6x | 1-3% recoverable |
| INT4 | 4-6x faster | 4-8x | 3-10% |

INT8 is the sweet spot for Pi. Calibrate on 50-200 production images.

### Benchmark expectations (the vision model-nano, 640x640)

| Device | Runtime | Per frame |
| ----------------------------- | ----------------- | --------- |
| Pi 4 (4 GB) | ONNX RT CPU | 300-500 ms|
| Pi 4 + INT8 | ONNX RT CPU | 150-250 ms|
| Pi 5 | ONNX RT CPU | 150-250 ms|
| Pi 5 + Hailo-8 | Hailo | 10-20 ms |
| Jetson Orin Nano | ONNX RT GPU | 25-40 ms |
| Jetson Orin Nano | TensorRT INT8 | 5-12 ms |

Target 200 ms (5 FPS) for watchable preview; 1 FPS is fine for QA.

### SDK auto-selection

```python
from arikizu_worker.backend import load_model, Backend

# Pick whatever is fastest among installed
handle = load_model("models/yolov8n.onnx")

# Priority order
handle = load_model("models/yolov8n.onnx",
 prefer=[Backend.TENSORRT, Backend.ONNX_GPU, Backend.ONNX_CPU])

outputs = handle.infer({"images": numpy_array})
print(handle.backend) # Backend.ONNX_CPU
```

Supported formats and which backends load each:

| Ext | Dispatches to |
| -------------- | ---------------------------------------------- |
| `.onnx` | TensorRT, ONNX GPU, ONNX CPU, OpenVINO |
| `.tflite` | TFLite |
| `.xml` | OpenVINO |
| `.engine` | TensorRT |
| `.pt`, `.pth` | PyTorch GPU/CPU |
| `.mlpackage` | CoreML |
| `.joblib`, `.pkl` | classical ML libraries (classical statistical, not neural) |

---

## 3. Catalog: what each worker needs

Not everything is a neural network, and not everything that is a neural
network is an LLM.

### Model classes

| Class | Example | Runtime | Size |
| ------------------------- | --------------------------- | -------------- | ------------- |
| Vision CNN / transformer | the vision model, LayoutLM, SAM | ONNX / TRT | 5-500 MB |
| Speech | the ASR model, a VAD model | ONNX / TFLite | 2-150 MB |
| Sentence embedding | all-a text embedding model, bge | ONNX | 20-400 MB |
| Named-entity | spaCy, Presidio | native | 15-60 MB |
| **Classical statistical** | **IsoForest, ARIMA** | **classical ML libraries** | 50 KB-50 MB |
| LLM GGUF | Qwen, Llama, Phi | llama.cpp | 400 MB-7 GB |
| Bandit / RL | Thompson sampler | joblib | 10 KB-10 MB |

### Per worker

#### vision (SightRAG)

| Capability | Default (minimum tier) | Runtime | Upgrade |
| ----------------- | ---------------------------- | -------- | -------------------------------- |
| `vision.detect` | `yolov8n.onnx` (6 MB) | ONNX | yolov8s/m/l, RT-DETR, custom |
| `vision.ocr` | tesseract-eng | tesseract| PaddleOCR, EasyOCR |
| `vision.caption` | placeholder |: | BLIP-2, Florence-2 |
| `vision.segment` | `mobile_sam.onnx` (42 MB) | ONNX | SAM 2, FastSAM |
| `vision.track` | ByteTrack (no model) | numpy | DeepSORT, StrongSORT |

Tesseract: `sudo apt install tesseract-ocr tesseract-ocr-eng`.

#### audio (Sonarwise)

| Capability | Default | Size | Upgrade |
| ---------------------- | ----------------------------- | ------ | ------------------------------------- |
| `audio.vad` | `silero_vad.onnx` | 1.8 MB | WebRTC VAD |
| `audio.transcribe` | `whisper-tiny.en.onnx` | 75 MB | whisper-small / base / large |
| `audio.keyword_spot` | `efficientkws.tflite` | 1 MB | custom-trained KWS |

#### docs (DocQWise)

| Capability | Default | Size |
| ---------------- | ------------------------------- | ------ |
| `docs.extract` | `layoutlmv3-base.onnx` | 500 MB |
| `docs.table` | `table-transformer.onnx` | 110 MB |
| `docs.search` | `all-MiniLM-L6-v2.onnx` | 90 MB |

#### reasoning

Points at a local LLM runtime/OpenAI-compatible endpoint. Not a file on disk.
See strategy section 1.

#### timeseries (WavqWise)

**Statistical, not deep.** No ONNX, no CUDA.

| Capability | Default | Format |
| ---------------------------- | ----------------------------- | --------- |
| `timeseries.forecast` | ARIMA + exponential smoothing | numpy |
| `timeseries.detect_anomaly` | anomaly detection (classical ML libraries) | `.joblib` |

Upgrade path: N-HiTS, N-BEATS, Chronos, TimesFM (all neural, Weekend 8).

#### memory (adaptive-intelligence)

| Capability | Default | Size |
| ------------------ | ----------------------------- | ------ |
| `memory.recall` | `all-MiniLM-L6-v2.onnx` | 90 MB |
| `memory.reward` | Thompson bandit (joblib) | 20 KB |

Shared embedder with docs and eval.

#### guard (AntGuard)

| Capability | Default | Size |
| -------------- | ----------------------------- | ----- |
| `guard.scan` | regex + `en_core_web_sm` | 15 MB |
| `guard.redact` | span-replace from scan |: |

For better PII: `pip install presidio-analyzer presidio-anonymizer`.

#### eval (LLMEvalKit)

| Capability | Default |
| ------------------- | ----------------------------- |
| `eval.score` | exact match + Jaccard |
| `eval.compare` | string diff |
| `eval.golden_run` | runs capability under test |

For BERTScore: point `ARIKIZU_EVAL_EMBEDDER` at the shared embedder.

#### test

No models. Pure IPC proof.

---

## 4. Defaults: what works out of the box

### Three tiers

```
scripts/download-default-models.sh --tier minimum # ~8 MB, any Pi
scripts/download-default-models.sh --tier standard # ~215 MB, Pi 4 (4 GB)
scripts/download-default-models.sh --tier full # ~2 GB, Pi 5 (8 GB), Jetson
```

### What each tier gets you

**minimum** (default: works on any Pi):

| File | Worker | Size |
| -------------------------- | ------------- | ------ |
| `yolov8n.onnx` | vision | 6 MB |
| `silero_vad.onnx` | audio | 2 MB |
| `anomaly_iforest.joblib` | timeseries | 50 KB |
| `reward_bandit.joblib` | memory | 20 KB |

**standard** (+ shared embedder, the ASR model, MobileSAM):

| File | Worker | Size |
| -------------------------- | ------------------- | ------ |
| ... (minimum) | ... | |
| `whisper-tiny.en.onnx` | audio | 75 MB |
| `all-MiniLM-L6-v2.onnx` | docs, memory, eval | 90 MB |
| `mobile_sam.onnx` | vision | 42 MB |

**full** (+ document understanding, bigger speech, bigger vision):

| File | Worker | Size |
| -------------------------- | ------- | ------ |
| ... (everything above) | ... | |
| `table-transformer.onnx` | docs | 110 MB |
| `whisper-small.en.onnx` | audio | 480 MB |
| `yolov8s.onnx` | vision | 60 MB |

### GPU auto-detect

`scripts/install-runtime.sh` probes the device and installs the right
runtime:

| What it looks at | What it installs |
| --------------------------------------- | ----------------------------------------- |
| `/etc/nv_tegra_release` | `onnxruntime-gpu` from Jetson AI Lab index|
| `nvidia-smi` | `onnxruntime-gpu` |
| `/dev/hailo*` | `hailo-platform` |
| macOS + Apple Silicon | `coremltools` |
| Intel CPU + Linux | `openvino` + `onnxruntime` |
| Everything else | `onnxruntime` (CPU only) |

### Backend selection priority (SDK default)

```
TensorRT > ONNX GPU > PyTorch GPU > OpenVINO > Hailo
 > ONNX CPU > TFLite > CoreML > PyTorch CPU
```

Override per worker:

```yaml
env:
 ARIKIZU_BACKEND_PREFER: tensorrt,onnx_gpu,onnx_cpu
```

### Model path precedence

1. `ARIKIZU_VISION_MODEL=/path` env wins outright
2. First of `yolov8n.onnx`, `yolov5n.onnx`, `model.onnx` under `ARIKIZU_MODELS_DIR`
3. Any `.onnx` in that dir
4. None → placeholder handler

### Memory budget rough

| Tier | Peak RSS (all workers loaded) | Device |
| -------- | ----------------------------- | -------------------------- |
| minimum | ~75 MB | Pi Zero 2W, Pi 4 (1 GB) |
| standard | ~770 MB | Pi 4 (4 GB) |
| full | ~2.2 GB | Pi 5 (8 GB), Jetson |

Add ~150 MB for Rust runtime + ~50 MB per Python worker.

### Hot-swap from dashboard

Open `/models`. For each worker that reports a `.backends` capability:

- Shows picked runtime + available runtimes + current model path
- Dropdown lists every `.onnx` under the models dir
- Pick a different file → worker reloads it, no restart
- Failed load keeps the previous model, logs the error

Also via API:

```
GET /api/v1/runtime
POST /api/v1/call/vision/switch_model payload: {"model_path": "/path/to/new.onnx"}
```

Every switch goes to the audit log.

---

## Format conversion matrix (reference)

Convert on a build machine, not on the Pi.

| From | To `.onnx` | To `.tflite` | To OpenVINO `.xml` |
| ---------- | ---------------------------------------- | ---------------------------------------- | ------------------------------ |
| PyTorch | `torch.onnx.export(model, dummy, "x.onnx")` | PyTorch → ONNX → `onnx2tf` | PyTorch → ONNX → `mo` |
| TensorFlow | `tf2onnx.convert.from_keras(...)` | `TFLiteConverter.from_keras_model(...)` | TF → ONNX → `mo` |
| ONNX | (already there) | `onnx2tf -i x.onnx` | `mo --input_model x.onnx` |
| the vision model | `yolo export model=yolov8n.pt format=onnx` | `format=tflite` | `format=openvino` |

Keep source + converted + sidecar `.json` manifest with SHA-256 in `models/`.

---

## Video Studio models (new in v1.6.0)

The Video Studio worker uses six model families, all quantized and
downloaded on first use into `models/`.

| Key | File | Size | Format | Device fit |
|---|---|---|---|---|
| `efficientdet_lite0` | `efficientdet_lite0.tflite` | 4.5 MB | float16 (LiteRT) | all |
| `pose_landmarker_lite` | `pose_landmarker_lite.task` | 5.8 MB | float16 (LiteRT) | all |
| `blaze_face` | `blaze_face_short_range.tflite` | 0.2 MB | float16 (LiteRT) | all |
| `selfie_segmenter` | `selfie_segmenter.tflite` | 0.5 MB | float16 (LiteRT) | all |
| `magic_touch` | `magic_touch.tflite` | 6.0 MB | float32 (LiteRT) | all |
| `segformer_b0_int8` | `segformer_b0_ade20k_512_int8.onnx` | 4.4 MB | int8 (ONNX) | all; CUDA EP on Jetson, CoreML on Mac |
| `qwen2_5_vl_3b_q4` | `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` | ~2.0 GB | int4 (GGUF) | Jetson Orin Nano and up |
| `qwen2_5_vl_3b_mmproj` | `Qwen2.5-VL-3B-Instruct-mmproj-f16.gguf` | ~700 MB | f16 (GGUF) | pair with the Q4 GGUF |

Downloaded by `scripts/download-video-models.sh` (perception only, ~22 MB)
or `scripts/download-video-models.sh --with-vlm` (add VLM, ~2.7 GB total).

The video worker picks which models to actually load based on the detected
device class. See `workers/video_worker/video_worker/devices.py` for the
full (model, device) fit table including expected ms per frame and the
delegate (`cpu-xnnpack`, `cuda`, `coreml`).
