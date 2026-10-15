# Why Arikizu, Who uses it, Where it helps

<p align="center">
 <img src="assets/logo-400.png" alt="Arikizu" width="140">
</p>

Most AI software ships as a cloud API. That works for most people. But
there is a long tail of users for whom cloud is impossible, expensive,
or against policy. Arikizu is for them.

So: why I built it, who the user is, where it actually helps today.

---

## 1. Why

### 1.1 The gap

Three things are all simultaneously true in late 2026:

- **AI quality is good enough for real work.** the vision model can read a factory
 line. the ASR model transcribes a nurse's handoff note. A small LLM can
 summarize a shift report.
- **Compute is small enough for a Pi.** a compact vision model is 6 MB. a VAD model is
 1.5 MB. A Jetson Orin Nano runs them with power to spare.
- **Nobody has packaged this for a non-engineer to install and run.**
 Every piece exists as a Python package, a Docker image, or a cloud
 service. The gap is the integration.

Three options exist today for the "I want AI on my shop floor" problem:

| Option | Why it does not fit |
| ------------------------------------- | ----------------------------------------------------------------------- |
| Cloud API (OpenAI, Anthropic, Gemini) | Network, cost per call, data leaves the premises, offline is impossible |
| Build it from scratch | Needs an ML engineer for 3 months; most teams don't have one |
| Buy a vertical appliance | $20k+, locked to one vendor, one use-case |

Arikizu is the fourth option: install one binary on a Pi, get vision,
audio, documents, time series, reasoning, memory, guard and eval behind
one API, add your own policies, done.

### 1.2 Why "OS" and not "SDK"

An SDK is a toolbox you still have to assemble. Arikizu is the assembled
runtime: supervisor, routing, lifecycle, policy, audit, dashboard, all
behind one `systemctl start arikizu`. See [`WHY_OS.md`](WHY_OS.md) for
the full argument.

### 1.3 Why single-device

I chose single-device deliberately. Multi-node needs auth, service
discovery, mTLS, and a non-single-user mental model, all of which
contradict "install with one command and forget." The target users are
not running Kubernetes. One Pi per site, each with its own Arikizu, is
the right unit of deployment.

### 1.4 Why edge-first

Edge is not a cost optimization. It is a trust and latency decision:

- **Trust**: medical, legal, defense, religious and personal data
 physically cannot leave the device without consent.
- **Latency**: 50 ms detection cannot wait for a round trip to AWS.
- **Resilience**: a factory line does not stop when the ISP does.
- **Cost at scale**: 100 sites paying $0.001 per API call x 10 million
 calls a month is not cheap, and the model gets slower not faster.

### 1.5 Why responsible-AI as a first-class citizen

Every call is audited. Every pipeline can insert an approval gate.
Every result can be corrected or rejected. PII is scanned and redacted
before it reaches a reasoning worker.

This is not a feature bolted on. The `ant-feedback` crate is a peer of
`ant-supervisor` in the architecture (see
[`ARCHITECTURE.md`](ARCHITECTURE.md) section 1), not a plugin.

Why: the people building these systems a decade from now will be the
ones who get this right first. I would rather set the pattern than wait
for the regulation to force it.

---

## 2. Who

Three concrete user personas. Each one is a real person who exists today
and has a problem Arikizu solves.

### 2.1 The site operator (primary user)

**Example:** Priya, 48, floor supervisor at a textile dyeing unit in
Tiruppur. 20 years on the job, uses WhatsApp and Google Translate daily,
has never written a line of code.

**Her problem today:** She walks the line four times a shift and
visually checks for color drift. If she misses one, 500 meters of
fabric gets scrapped. There is one camera per line but nobody looks at
the footage.

**What she needs from Arikizu:**

- A Pi on her desk, plugged into the camera feed.
- A dashboard she can open on her phone over WiFi (`http://arikizu.local`).
- A card that says "4 color-drift alerts in the last 2 hours."
- A button to approve or reject each alert so the model learns from her.

**What she does NOT need:**

- Python, Rust, pip, Docker, Kubernetes, IAM policies, API keys.
- A monthly subscription.
- To upload the footage anywhere.
- To understand the vision model or ONNX.

Priya is the first and most important user. Everything in the
dashboard is designed for her: 6 cards, big fonts, a greeting that
knows what time it is, status dots that are either green or not.

### 2.2 The integrator (power user)

**Example:** Arjun, 32, works at an industrial automation reseller in
Pune. Installs sensors, PLCs, and vision systems for mid-sized
factories. Comfortable with the Linux command line but not an ML
engineer.

**His problem today:** His customers ask for AI features. He can quote
them a Siemens Industrial Edge box for $8000 or spend 3 weeks writing
Python glue for them. Neither works at the price his customers can pay.

**What he needs from Arikizu:**

- A `.deb` or flashable image that installs on a Pi or Jetson in 20
 minutes.
- A `capabilities.toml` he can edit to add their custom detector.
- A `policies/*.yaml` to add their safety rules.
- A pipeline YAML that chains vision + guard + reasoning + approval.
- The dashboard, for his customer's operator to use.
- A SQLite audit log he can hand to the customer's compliance person.

**What he does NOT need:**

- To learn a new framework.
- A cloud bill to pass to his customer.
- Vendor lock-in.

Arjun is why Arikizu is open-source and self-hosted. He adds value by
knowing his customer; Arikizu is the runtime he resells.

### 2.3 The AI engineer (contributor / extender)

**Example:** You and me. Reads code, writes workers, cares about the
architecture.

**Our problem today:** Every edge-AI side project rebuilds the same
plumbing. IPC, supervisor, config loader, audit log, dashboard. By the
time the plumbing works, the interesting part is a weekend away.

**What we need from Arikizu:**

- A Python worker SDK that handles the boring parts (IPC, framing,
 backend selection, graceful shutdown) in one import.
- A capability registry that is just TOML.
- An HTTP surface we don't have to write.
- A dashboard we can extend by dropping an HTML file in `demo/web/`.
- A test harness that proves the whole chain in `make smoke`.

The 10 workers today are examples. Writing an 11th worker takes about
30 lines of Python.

---

## 3. Where it helps

Twelve concrete deployments, grouped by vertical. Each one is a real
pattern I have seen or can defend from first principles.

### 3.1 Manufacturing (floor supervision)

**Pattern:** camera on a line + vision worker + guard worker + approval
gate for scrap decisions.

- **Textile dyeing:** color drift detection, reject-or-continue approval.
- **Pharma packaging:** blister-pack fill-level check, batch tracking.
- **Electronics assembly:** PCB defect detection with the operator
 confirming each flag.

Why Arikizu: no vendor cloud sees the production data. Audit log
satisfies ISO 9001.

### 3.2 Healthcare (nurse station, clinic)

**Pattern:** audio worker + docs worker + reasoning + memory + strict
guard policy.

- **Nurse handoff notes:** record, transcribe, summarize, redact PHI,
 save to the patient record. Audit who heard what.
- **Rural clinic triage:** patient speaks symptoms in Tamil; local
 the ASR model transcribes; small LLM asks three follow-up questions;
 doctor sees the structured intake form.
- **Mental-health intake:** audio stays on-device, only the structured
 summary leaves (and only if the patient approves it).

Why Arikizu: HIPAA / Indian DPDP compliance by construction. The data
cannot leak because it never left.

### 3.3 Ship engineering (maritime)

**Pattern:** docs worker + reasoning + memory, no network.

- **Engine room manuals:** 2000-page OEM PDFs, extract the right
 procedure for the fault code the engineer just typed.
- **Watch log summarization:** 12-hour watch notes to a 1-paragraph
 handoff.
- **Compliance:** every answer the AI gives is in the audit log, with
 the source paragraph.

Why Arikizu: a ship at sea has no reliable internet. Everything must
work offline.

### 3.4 Heritage conservation

**Pattern:** vision + docs + memory.

- **Temple scanning:** vision worker detects iconography; memory recalls
 past scans of the same deity across temples; docs worker extracts
 from epigraphy transcripts.
- **Museum cataloguing:** camera on a cart, moves through the stacks,
 Arikizu classifies and matches each object against the catalogue.

Why Arikizu: cultural data stays in the country / institution. No
training labels leak to a US cloud.

### 3.5 Agriculture (greenhouse, farm)

**Pattern:** vision + timeseries + guard + alerts.

- **Greenhouse pest detection:** camera + vision worker; alerts when a
 pest class exceeds threshold.
- **Soil moisture time series:** forecast watering need; anomaly
 detection on sensor drift.

Why Arikizu: the farm has no reliable network. The Pi runs standalone
and syncs when WiFi is in range.

### 3.6 Defense / border / compliance-heavy

**Pattern:** every worker, strict policies, air-gapped.

- Any site where "no outbound network" is a hard rule.
- Classified or sensitive data processing.

Why Arikizu: `ProtectSystem=strict`, no outbound calls by default, every
model is SHA-256 verified, every action is in the audit log.

---

## 4. Where it does NOT help

I want to be honest about the non-fit list, because overclaiming kills
trust.

| Not a fit | Use instead |
| ------------------------------------------------------------ | ----------------------------------------- |
| High-throughput cloud workload (1000 req/s) | Managed inference (Bedrock, Vertex, etc.) |
| Training large models | A real GPU cluster |
| Multi-tenant SaaS | Not what Arikizu is for |
| Real-time video >30 FPS at full resolution on a Pi | A dedicated video analytics appliance |
| Models that need >8 GB VRAM | Workstation or server GPU |
| A team of 10 engineers who already have their own ML platform | They don't need Arikizu |

See [`SPEC.md`](SPEC.md) for the full non-fit list and the five-point
qualification checklist.

---

## 5. Comparison with the obvious alternatives

| Dimension | Cloud API (OpenAI/Anthropic/GCP) | Siemens Industrial Edge | Nvidia Jetson+Metropolis | **Arikizu** |
| ---------------- | -------------------------------- | ----------------------- | ------------------------ | ----------------------------- |
| Offline | No | Partial | Yes | **Yes (default)** |
| Install time | Minutes (an API key) | Days | Days | **~30 min on a Pi** |
| Data residency | Vendor's region | Local | Local | **On the device** |
| Cost at 1 device | $0 + per-call fee | $8-20k | $500-$2k + licenses | **$75 Pi + $0** |
| Custom worker | API wrapper | Vendor SDK | Vendor SDK | **~30 lines of Python** |
| Audit log | Vendor-provided (opt-in) | Varies | Varies | **SQLite, every call, local** |
| Human-in-the-loop | Not standard | Varies | Not standard | **Approval gate per stage** |
| License | Proprietary | Proprietary | Proprietary | **Will be OSS (W20)** |

Arikizu is the only option in that table that is simultaneously
offline, cheap, extendable, auditable, and open.

---

## 6. The current state (October 2026)

Honest about what works right now, so you can decide if it fits.

**Fully working today (v1.5):**

- Rust supervisor spawns and manages Python workers over Unix sockets.
- Operator dashboard at `/`, developer sandbox at `/demo/`.
- Vision: real a compact vision model ONNX detection (6 MB model, runs on Pi 4).
- Audio: real a VAD model; real the ASR model ASR when weights are downloaded.
- Reasoning: real local LLM via a local LLM runtime (or a LAN gateway from the Pi).
- Timeseries: real classical ML libraries anomaly detection + forecast.
- Memory: real in-RAM session memory with top-k recall.
- Guard: real regex-based PII scan and redaction.
- Eval: real exact + Jaccard scoring, golden-set runner.
- Audit log: real SQLite, every call recorded.
- HTTP + WebSocket API: real, 14 routes, documented.
- CLI: real, every endpoint reachable from the shell.

**Scaffolded, placeholder behind the API (will light up on the listed weekend):**

| Worker | What's a stub today | When it lights up |
| ------------- | ------------------------------------------------------ | ----------------- |
| vision (segment, track) | detect is real; segment and track return placeholder | Weekend 5 (SightRAG) |
| audio (speaker ID) | VAD and transcribe real; speaker ID is placeholder | Weekend 6 (Sonarwise) |
| docs | DocQWise wrap when installed; otherwise placeholder | Weekend 7 (DocQWise) |
| timeseries (long-range) | short forecasts real; long-range placeholder | Weekend 8 (WavqWise full) |
| memory | works in RAM; persistence placeholder | Weekend 9 (adaptive-intelligence) |
| guard | regex detectors real; ML-based detectors placeholder | Weekend 10 (AntGuard full) |
| eval | exact / jaccard real; LLM-judge placeholder | Weekend 12 (LLMEvalKit full) |

**Not yet (deliberate):**

- Not external document AIs. Not Google Document AI. Not a cloud document AI. The
 docs worker is backed by my own DocQWise library.
- Not multi-tenant.
- Not multi-node.
- Not training.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) section 12 for the full
non-features list, and the top of each worker's module docstring for
its own real-vs-placeholder status.

---

## 7. The decision for a prospective user

Should you try Arikizu? Short answer in three bullets.

- **Yes if:** you have one or more devices doing one specific job, want
 AI help on that job, cannot or do not want to send data to a cloud,
 and are willing to run a Pi or Jetson.
- **Maybe if:** you have a cloud-first stack and want on-prem as a
 compliance option. Arikizu works but your team may prefer the
 familiar cloud API.
- **No if:** your workload is pure cloud scale, you need multi-tenant,
 or you need training.

For "yes" and "maybe" people: 5-minute laptop quickstart is in the
[README](../README.md). Full Pi walkthrough is in
[QUICKSTART.md](../QUICKSTART.md). What each capability does with
screenshots: [DEMO.md](DEMO.md).

---

## 8. The one-sentence version

**Arikizu is the open, auditable, single-device AI runtime for people
who cannot or will not send their data to the cloud.**

That is it. Everything else in the project exists to make that
sentence operationally true.
