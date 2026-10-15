# Arikizu Pi image build (pi-gen stage)

This folder is a drop-in stage for the Raspberry Pi Foundation's `pi-gen`
image builder. Clone `pi-gen`, copy this folder in as `stage-arikizu`,
list it in `STAGE_LIST`, and run `./build.sh`. Out comes
`arikizu-pi-<version>.img.xz`.

Target base: Raspberry Pi OS Lite 64-bit, bookworm or newer.

## One-command build (recommended path)

```
cd ~/work
git clone https://github.com/RPi-Distro/pi-gen
cd pi-gen
cp -r /path/to/arikizu/packaging/pi-gen/stage-arikizu .
cat >config <<EOF
IMG_NAME=arikizu-pi
RELEASE=bookworm
TARGET_HOSTNAME=arikizu
DISABLE_FIRST_BOOT_USER_RENAME=1
STAGE_LIST="stage0 stage1 stage2 stage-arikizu"
EOF
sudo ./build.sh
```

Output: `deploy/image_<date>-arikizu-pi.zip` (unzip to get `.img`,
then `xz` to compress for release).

Full build time: 30-60 min on a decent x86_64 server (uses QEMU for the
aarch64 chroot steps).

## What this stage does

See `stage-arikizu/00-run.sh` (and its siblings). High level:

1. Install Arikizu's runtime dependencies into the image's apt chroot
   (python3.11, libasound2, python3-picamera2, python3-opencv, ...).
2. Drop the cross-compiled `arikizu` binary into `/usr/bin/`.
3. Drop pre-built Python wheels for every worker into
   `/opt/arikizu/wheels/`.
4. Install the default config and policies to `/etc/arikizu/`.
5. Install the systemd unit from `packaging/systemd/`.
6. Create the `arikizu` user and `/var/lib/arikizu` state dir.
7. Set the mDNS hostname to `arikizu.local`.
8. Enable the service so it boots on first run.

The binary and the wheels are built upstream (CI, aarch64 cross-compile)
and dropped into `files/` before pi-gen runs.

## What the user sees

1. Flash the image with Raspberry Pi Imager (or Balena Etcher, or `dd`).
2. Boot the Pi; wait 60-90 s on first boot (rootfs expansion, systemd start).
3. Open `http://arikizu.local` on any device on the same LAN.
4. The dashboard loads; the smoke test grid shows the live/placeholder/skip
   state for every capability.

That is the OS install, start to finish.

## Status in v0.1

Scaffolded. The stage files below contain real `pi-gen` syntax and are
runnable once Weekend 15 produces the cross-compiled binary and worker
wheels. Fill in the `files/arikizu` and `files/wheels/*.whl` on the CI
side.
