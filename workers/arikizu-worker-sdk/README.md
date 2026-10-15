# arikizu-worker-sdk

Thin IPC shim. Every worker imports this and gets:

- `Worker("<name>")` — the main class
- `@worker.handler("<domain>.<op>")` decorator — register sync or async handlers
- `worker.run()` — connect to `$ARIKIZU_SOCKET`, send Hello, dispatch Call frames, heartbeat every 1s

## Minimal worker

```python
import asyncio
from arikizu_worker import Worker

worker = Worker("my_worker")

@worker.handler("my.echo")
def echo(message: str = "") -> dict:
    return {"echo": message}

@worker.handler("my.slow")
async def slow(seconds: float = 0.5) -> dict:
    await asyncio.sleep(seconds)
    return {"slept": seconds}

asyncio.run(worker.run())
```

## Framing

Each handler sees the payload the supervisor sent (a Python dict for an object payload, a scalar otherwise). The return value is serialized as the Reply.

A raised exception becomes a `Frame::Error` with `error = "<ExceptionType>: <message>"`; the supervisor forwards it to the HTTP caller as HTTP 500.

The SDK handles:

- Length-prefixed MessagePack framing (big-endian u32)
- Hello handshake with protocol version
- A background heartbeat task that reports memory and queue depth every 1s
- Graceful shutdown on supervisor disconnect

## Events

To publish an event from a handler, hold a reference to the writer side of the stream — v0.1 keeps this simple by not giving a stable API, so for now stick to Reply/Error. Events will land in a cleaner API in Weekend 6 alongside Sonarwise.

## Protocol version

`PROTOCOL_VERSION = 1`. Bump it in both this package and `ant-ipc` when the wire changes.

## Model backend auto-selection

The SDK's `backend` module picks a model runtime from what is installed on
the host: ONNX Runtime (CPU or GPU), TFLite, OpenVINO, TensorRT, CoreML,
or PyTorch. Workers call `load_model(path)` and get back a `ModelHandle`
with a uniform `.infer(inputs)` method.

```python
from arikizu_worker import backend as bk

# Report available runtimes (for the audit log)
print(bk.summarize())
# {'available': ['onnx_cpu', 'tflite', 'pytorch_cpu'],
#  'default_pick': 'onnx_cpu'}

# Load a model, letting the SDK choose the backend
handle = bk.load_model("models/yolov8n.onnx")

# Or specify a preference order (strings or Backend enum values)
handle = bk.load_model(
    "models/yolov8n.onnx",
    prefer=["tensorrt", "onnx_gpu", "onnx_cpu"],
)
print(handle.backend.value, handle.meta)

# Run inference
out = handle.infer({"images": image_tensor_np})
```

Supported file extensions and the runtimes that can load each:

| Extension      | Runtimes it dispatches to                       |
| -------------- | ----------------------------------------------- |
| `.onnx`        | TensorRT, ONNX GPU, ONNX CPU, OpenVINO          |
| `.tflite`      | TFLite                                          |
| `.xml`         | OpenVINO                                        |
| `.engine`      | TensorRT                                        |
| `.pt`, `.pth`  | PyTorch (GPU first, else CPU)                   |
| `.mlpackage`, `.mlmodel` | CoreML (macOS only)                   |

Install only the runtimes you want. If none can load a given file, the
SDK raises `BackendUnavailable` with a hint about which pip package to
install. See [`docs/MODEL_OPTIMIZATION.md`](../../docs/MODEL_OPTIMIZATION.md)
for the device-to-runtime matrix.

## Tests

```
cd workers
uv run pytest arikizu-worker-sdk
```

Covers: framing round-trip (hello + reply + binary payload), oversized-frame sentinel.
