# Why "OS"

Arikizu is called an operating system because it does the job of one: for
the AI stack on an edge device, not for the CPU. This doc lays out what
that means and what it doesn't.

> **Quick note.** Arikizu does not replace the Linux kernel. It runs on top
> of Raspberry Pi OS as a systemd service, same shape as Home Assistant OS
> or OctoPrint. For the stack diagram and the boot sequence, see
> [`HOW_IT_RUNS.md`](HOW_IT_RUNS.md).

## What an OS does, and what Arikizu does

A classical OS is defined by five jobs. Arikizu does all five, scoped to
the layer above Linux:

| Classical OS job                       | What Arikizu does                                                           |
| -------------------------------------- | --------------------------------------------------------------------------- |
| Process management (init, systemd)     | `ant-supervisor` spawns and monitors every worker; restarts on failure      |
| IPC (pipes, sockets, dbus)             | `ant-ipc` runs length-prefixed MessagePack over Unix sockets, protocol v1   |
| System call dispatch                   | `ant-router` maps capability names (`vision.detect`) to a worker handler    |
| Device management (/dev, udev)         | `ant-devices` enumerates CPUs, GPUs, Jetson, cameras, mics                  |
| Security policy (SELinux, AppArmor)    | `ant-supervisor::policy` + `policies/*.yaml` allowlist hosts and capabilities |
| Logging (syslog, journald)             | `ant-feedback::audit` writes an append-only SQLite audit log                |
| Shell + user API                       | `arikizu` CLI + REST + WebSocket + the dashboard at `/`                     |
| Scheduler                              | `ant-supervisor::pipeline` walks stages with timeouts and approval gates    |
| Boot                                   | `arikizu run` reads `arikizu.yaml`, spawns workers, listens                 |

The Rust runtime is the kernel. The Python workers are the userspace. The
capability names are the syscall table. `arikizu.yaml` is `/etc`. The
dashboard is `top` + `journalctl` with buttons.

## What makes it feel like an OS to a user

- One binary installs with one command: `curl ... | sh` → `arikizu`.
- One config file at the root: `arikizu.yaml`.
- One default surface: open `http://127.0.0.1:7000` and everything is there.
- Workers are **drivers**: adding a new sensor or model means adding a
  Python package under `workers/` and a line in `capabilities.toml`.
  No framework changes.
- Everything runs on one device. No cluster, no cloud, no account.

## What it is not

- **Not a kernel.** Runs on Linux. The kernel owns scheduling, memory, drivers.
- **Not a distribution.** No package manager yet (Weekend 15 ships `arikizu pull`).
- **Not a container runtime.** Workers are plain OS processes, not Docker.
- **Not an orchestrator across machines.** One device, one install. Multi-node
  is explicitly out of scope: multi-site deployments run one Arikizu per site.

## Why the "OS" name is the right one

Three reasons:

**1. It sets the right expectation about ownership.**
A framework is something you import. A library is something you call. An OS
is something you install, boot, and don't think about. Arikizu is the third
kind. When a factory supervisor turns on their Jetson, they do not want to
know whether SightRAG or Sonarwise is handling a given frame: they want the
whole machine to work. "OS" names that scope.

**2. It matches the precedent.**
Home Assistant calls their software "HAOS". Mycroft called theirs an "AI OS".
Everything from Chromium OS to CoreOS to Android bundles Linux underneath but
is named for the layer on top. Arikizu is the same shape: a Rust supervisor
plus Python workers plus a web shell, all built to be installed as a unit on
a Jetson or Pi and left to run.

**3. It differentiates from the alternatives.**
"Framework" would put Arikizu next to LangChain. "Platform" would put it next
to SageMaker. "OS" puts it next to the thing it actually competes with: the
pile of shell scripts and systemd units that an edge-AI engineer writes by
hand to glue together OpenCV + the ASR model + a local LLM runtime + a dashboard. Arikizu is
that pile, done once, correctly.

## What this means for the project

- Install story is: one binary, one config, one URL.
- Upgrade story is: replace the binary, keep the config, the audit DB migrates.
- "Hello world" is `arikizu init my-app && cd my-app && arikizu run`.
- The reference target is Jetson Orin Nano 8 GB. Raspberry Pi 4/5 and
  x86_64 Linux are first-class dev targets. Everything else is best-effort.
- The README's one-liner reflects that: *edge-first, offline-first,
  responsible-AI operating system for a single device*.

## What this means for how you talk about it

Short pitch:

> Arikizu is an edge-first AI operating system. One Rust supervisor, a set of
> Python workers wrapping vision/audio/docs/reasoning/time-series libraries,
> and a browser dashboard: installed as one binary on a Jetson or Pi, with
> human-in-the-loop and an audit log built in. No cloud, no account.

Longer pitch (an engineer in your network):

> Think a local LLM runtime, but for the full stack: vision + audio + documents + reasoning
> + feedback, all behind one capability API. The runtime is Rust so it stays
> under 100 MB of RAM; the workers are Python so you can swap models without
> rebuilding. Pipelines have approval gates, so a nurse or shift lead stays in
> the loop. Everything on-device. Everything auditable.

One line (a product person):

> One edge device, one install, every modality, auditable. Human in the loop.
