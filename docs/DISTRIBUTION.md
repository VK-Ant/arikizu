# Distribution

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
