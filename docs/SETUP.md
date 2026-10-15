# Edge Device Setup Guide

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

| Device               | Vision | Audio    | Reasoning   | Overall             |
| -------------------- | ------ | -------- | ----------- | ------------------- |
| Pi 4 (4 GB)          | 2-3 FPS CPU | VAD realtime, the ASR model 5x slow | LAN gateway only | Entry level; proves it all works |
| Pi 5 (8 GB)          | 5-7 FPS CPU | VAD realtime, the ASR model 2x slow | Small LLM OK  | Comfortable for one line / room |
| Jetson Orin Nano     | 25-40 FPS GPU | the ASR model near realtime | Local 3B LLM | Multi-camera lane / clinic |
| Jetson AGX Orin      | 60+ FPS GPU | Instant | Local 7B LLM | Factory floor / vehicle |
| Mac M-series         | 15-30 FPS CoreML | Instant | Local 7B LLM | Dev + demo + personal use |
| Mac Intel            | 5-10 FPS CPU | Fine | LAN gateway | Dev + demo only |
| Linux x86 + NVIDIA   | 50+ FPS GPU | Instant | Local 13B+ LLM | Workstation / small server |
| Linux x86 no GPU     | 5-15 FPS CPU | Fine | LAN gateway | Dev + demo + light prod |
| WSL on Windows       | 5-15 FPS CPU | Fine (needs ALSA passthrough) | LAN gateway | Dev only |

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
2. [`PI_VISION_TUTORIAL.md`](PI_VISION_TUTORIAL.md): Pi Camera +
   the vision model + approval gate. 1 hour.
3. [`BRING_YOUR_OWN_MODEL.md`](BRING_YOUR_OWN_MODEL.md): swap in your
   trained ONNX / TFLite / TensorRT model. (coming in v1.5.6)
4. [`ARCHITECTURE.md`](ARCHITECTURE.md): understand what's under the hood.
5. [`WHY_AND_WHO.md`](WHY_AND_WHO.md): real-world deployment patterns.

This is the whole setup guide for every edge device Arikizu runs on.
Pick yours, follow the tagged subsections, and you have a working AI
runtime in anywhere from 15 min (laptop) to 2 hours (Pi 4).
