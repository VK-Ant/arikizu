# How Arikizu actually runs

Short answer: Arikizu is not a Linux replacement. It runs on top of Raspberry
Pi OS (which is Debian + the Linux kernel), started by systemd at boot. The
`.img.xz` ships Raspberry Pi OS Lite with Arikizu pre-installed and
auto-enabled, so the user sees only Arikizu but Linux is doing the real work
underneath.

Same pattern as Home Assistant OS, OctoPrint, RetroPie, DietPi, RaspAP: they
are all called "OS" or "Pi distros," they all package Linux plus a stack of
software, and users flash and boot them without touching Linux directly.

## The stack

```
+------------------------------------------------------------------+
|  USER                                                             |
|  http://arikizu.local                                             |
|  dashboard, pipelines, review queue, audit log, demo sandbox      |
+------------------------------------------------------------------+
|                                                                   |
|  ARIKIZU (one Rust binary + Python workers)                       |
|  --------------------------------------------                     |
|  arikizu run                                                      |
|    ant-cli -> ant-supervisor -> ant-ipc -> Python workers         |
|    ant-http  (HTTP + WebSocket on :7000)                          |
|    ant-feedback (SQLite audit at /var/lib/arikizu/arikizu.db)     |
|    ant-router, ant-models, ant-devices, ant-feedback::audit       |
|                                                                   |
+------------------------------------------------------------------+
|                                                                   |
|  SYSTEMD                                                          |
|  --------                                                         |
|  arikizu.service     (unit from packaging/systemd/)               |
|  avahi-daemon        (so the Pi announces arikizu.local)          |
|  ssh, chrony, cron   (default Raspberry Pi OS services)           |
|                                                                   |
+------------------------------------------------------------------+
|                                                                   |
|  RASPBERRY PI OS (Debian bookworm 64-bit)                         |
|  -------------------------------------------                      |
|  Linux kernel + apt + python3 + libasound2 + picamera2 + opencv  |
|  Networking (wpa_supplicant, dhcpcd, dnsmasq)                     |
|  Device drivers (camera, mic, GPU, I2C, SPI)                      |
|                                                                   |
+------------------------------------------------------------------+
|                                                                   |
|  HARDWARE                                                         |
|  Raspberry Pi 4 / 5 / Zero 2 W / Jetson Orin Nano                 |
|  + Pi Camera / USB webcam, USB mic                                |
|                                                                   |
+------------------------------------------------------------------+
```

Arikizu lives in two of these rows (ARIKIZU + the systemd unit that
starts it). Everything above is Arikizu's UI; everything below is Linux.

## What boots up, in order

```
1.  Pi powers on
2.  Bootloader loads the Linux kernel from the SD card
3.  Linux boots: mounts rootfs, brings up devices, hands over to systemd
4.  systemd starts default services: ssh, chrony, wpa_supplicant, avahi
5.  systemd starts arikizu-firstboot.service (once, on first boot only)
       - creates the arikizu user and /var/lib/arikizu
       - pip installs worker wheels from /opt/arikizu/wheels (offline)
       - copies default config to /etc/arikizu/
       - disables itself so it never runs again
6.  systemd starts arikizu.service
       - exec /usr/bin/arikizu run --config /etc/arikizu/arikizu.yaml
       - Arikizu spawns Python workers over Unix sockets
       - HTTP listens on 127.0.0.1:7000 (and :: via avahi -> arikizu.local)
7.  LED blinks a few times, Pi is ready
8.  User opens http://arikizu.local in a browser on the same LAN
```

Steps 1-4 are Raspberry Pi OS doing exactly what it always does. Steps
5-7 are Arikizu-specific. The user sees only step 8.

Time from power-on to ready: 60-90 s on first boot (step 5 adds setup
time), 20-30 s on every reboot after.

## What the user does, what Linux does

| User sees                                | Linux is doing                                           |
| ---------------------------------------- | -------------------------------------------------------- |
| Opens `http://arikizu.local`             | avahi-daemon resolves mDNS to the Pi's LAN IP            |
| Dashboard loads                          | arikizu.service is serving on :7000; nginx is NOT needed |
| Clicks "Run smoke test" in `/demo`       | ant-http dispatches to ant-router → ant-supervisor → Python worker over Unix socket |
| Approves a pipeline stage                | ant-feedback writes to /var/lib/arikizu/arikizu.db       |
| Watches live events in `/events`         | ant-supervisor's tokio broadcast bus → axum WebSocket    |
| Shuts the Pi down                        | systemd gracefully stops arikizu.service, syncs the DB, powers off |

The user is never asked to open a terminal. The user is never shown Linux.
That is what the "OS" word is reserved for: the thing you flash, boot,
and use.

## Controlling Arikizu from the command line (sysadmin only)

For a sysadmin SSH'ing in, Arikizu is just another systemd service:

```
# Status
sudo systemctl status arikizu

# Restart (after editing /etc/arikizu/arikizu.yaml)
sudo systemctl restart arikizu

# Follow logs
sudo journalctl -u arikizu -f

# Stop entirely
sudo systemctl stop arikizu

# Disable auto-start
sudo systemctl disable arikizu
```

Config lives at:

- `/etc/arikizu/arikizu.yaml`         : pipeline config
- `/etc/arikizu/capabilities.toml`    : capability registry
- `/etc/arikizu/policies/*.yaml`      : security policies

State lives at:

- `/var/lib/arikizu/arikizu.db`       : SQLite audit log
- `/var/lib/arikizu/golden/`          : annotated examples
- `/var/lib/arikizu/models/`          : downloaded model files
- `/run/arikizu/*.sock`               : per-worker Unix sockets

Nothing of Arikizu's state lives outside those two trees. Reinstalling
the `.deb` keeps everything; reflashing the image keeps nothing (the
image is factory-fresh by design).

## Why we still call the bundle "Arikizu OS"

Three reasons the name is right even though Linux is underneath:

**1. It's what the user flashes.** The thing on the SD card is "Arikizu
Pi image." The user does not install Linux and then install Arikizu;
they flash one `.img.xz` and that is the install.

**2. It's what the user boots into.** Boot ends at the Arikizu dashboard,
not at a Linux login prompt. mDNS announces as `arikizu.local`. The
hostname is `arikizu`. The default service is `arikizu.service`.
Every surface the user touches is Arikizu.

**3. It matches the industry precedent.** Android is "Android OS" and runs
on a Linux kernel. Home Assistant OS runs on a Linux kernel. ChromeOS
runs on a Linux kernel. "OS" is reserved for the top-level bundle the
user interacts with, not the kernel underneath.

If someone pushes back with "but it's really just Linux + a daemon,"
that is a true observation. Every one of the OSes above is "really just
Linux + a daemon." That is how the whole industry ships edge-device
operating systems.

## Short way to tell the story

> Arikizu doesn't replace Linux. It runs on top of Raspberry Pi OS as a
> systemd service. The `.img.xz` ships both of them pre-wired, so when you
> flash and boot a Pi, you boot into Arikizu. Linux is doing the real
> work; Arikizu is doing the real user experience.

That's the whole answer to "how does it run?"
