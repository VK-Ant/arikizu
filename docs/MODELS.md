# Models

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
