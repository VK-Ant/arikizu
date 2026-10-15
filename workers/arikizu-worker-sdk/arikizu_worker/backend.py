"""Model backend auto-selection.

Workers call `load_model(path)`; the SDK figures out which runtime to use
based on the file extension and what's installed on this host. If nothing
suitable is installed, raises `BackendUnavailable` with a clear hint.

Supported runtimes (installed independently):
    onnxruntime[-gpu]     # .onnx
    tflite-runtime        # .tflite
    openvino              # .xml  (OpenVINO IR)
    tensorrt              # .engine
    coremltools           # .mlpackage, .mlmodel (macOS only)
    torch                 # .pt   (dev/debug path)

The audit log carries which backend was picked for each load, so a
pipeline run can be traced to the exact runtime that produced it.

See docs/MODEL_OPTIMIZATION.md for the device-to-runtime matrix.
"""

from __future__ import annotations

import importlib
import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("arikizu_worker.backend")


class Backend(str, Enum):
    TENSORRT = "tensorrt"
    ONNX_GPU = "onnx_gpu"
    ONNX_CPU = "onnx_cpu"
    OPENVINO = "openvino"
    TFLITE = "tflite"
    COREML = "coreml"
    PYTORCH_GPU = "pytorch_gpu"
    PYTORCH_CPU = "pytorch_cpu"
    HAILO = "hailo"
    SKLEARN = "sklearn"       # joblib-serialized classical models (statistical, no neural weights)


# Global priority if the worker didn't say what it wants.
DEFAULT_PRIORITY = [
    Backend.TENSORRT,
    Backend.ONNX_GPU,
    Backend.PYTORCH_GPU,
    Backend.OPENVINO,
    Backend.HAILO,
    Backend.ONNX_CPU,
    Backend.TFLITE,
    Backend.COREML,
    Backend.PYTORCH_CPU,
]


class BackendUnavailable(RuntimeError):
    """Raised when no runtime for the requested model format is installed."""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _try_import(name: str) -> Any | None:
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def detect_available() -> list[Backend]:
    """Return every backend whose runtime is importable on this host.

    This is called once at worker start; it does NOT hold references.
    """
    out: list[Backend] = []

    # ONNX Runtime (with EP detection)
    ort = _try_import("onnxruntime")
    if ort is not None:
        try:
            providers = ort.get_available_providers()
        except Exception:
            providers = ["CPUExecutionProvider"]
        if "TensorrtExecutionProvider" in providers:
            out.append(Backend.TENSORRT)
        if "CUDAExecutionProvider" in providers or "ROCMExecutionProvider" in providers:
            out.append(Backend.ONNX_GPU)
        out.append(Backend.ONNX_CPU)

    # TFLite (two possible import paths)
    if _try_import("tflite_runtime.interpreter") is not None:
        out.append(Backend.TFLITE)
    elif _try_import("tensorflow") is not None:
        out.append(Backend.TFLITE)

    # OpenVINO
    if _try_import("openvino") is not None:
        out.append(Backend.OPENVINO)

    # CoreML (macOS)
    if _try_import("coremltools") is not None:
        out.append(Backend.COREML)

    # PyTorch
    torch = _try_import("torch")
    if torch is not None:
        try:
            if torch.cuda.is_available():
                out.append(Backend.PYTORCH_GPU)
        except Exception:
            pass
        out.append(Backend.PYTORCH_CPU)

    # Hailo
    if _try_import("hailo_platform") is not None:
        out.append(Backend.HAILO)

    # sklearn / joblib — classical statistical models (timeseries, memory, guard)
    if _try_import("joblib") is not None:
        out.append(Backend.SKLEARN)

    return out


def pick(prefer: list[Backend] | list[str] | None = None) -> Backend | None:
    """Pick a backend to use. `prefer` is an ordered priority list; the
    first one that is actually installed wins. Falls back to the global
    priority if `prefer` is empty or none of its entries are installed.
    """
    available = set(detect_available())
    if not available:
        return None

    prefer_norm: list[Backend] = []
    for b in prefer or []:
        if isinstance(b, Backend):
            prefer_norm.append(b)
        elif isinstance(b, str) and b:
            try:
                prefer_norm.append(Backend(b.strip().lower()))
            except ValueError:
                logger.warning("unknown backend name in prefer list: %r", b)

    for b in prefer_norm:
        if b in available:
            return b
    for b in DEFAULT_PRIORITY:
        if b in available:
            return b
    return next(iter(available))


# ---------------------------------------------------------------------------
# Model handle
# ---------------------------------------------------------------------------


class ModelHandle:
    """Opaque wrapper around a loaded model.

    Workers can either call `handle.infer(inputs)` for the convenience
    path, or reach `handle.impl` for the raw session/interpreter when
    they want runtime-specific features.
    """

    def __init__(self, backend: Backend, impl: Any, path: Path, meta: dict[str, Any] | None = None):
        self.backend = backend
        self.impl = impl
        self.path = path
        self.meta = meta or {}

    def __repr__(self) -> str:
        return f"<ModelHandle backend={self.backend} path={self.path.name}>"

    def infer(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Run inference. `inputs` keys must match the model's input names."""
        if self.backend in (Backend.ONNX_CPU, Backend.ONNX_GPU, Backend.TENSORRT):
            outputs = self.impl.run(None, inputs)
            # Return as {name: value} to keep the interface uniform.
            output_names = [o.name for o in self.impl.get_outputs()]
            return dict(zip(output_names, outputs))

        if self.backend == Backend.TFLITE:
            interp = self.impl
            input_details = interp.get_input_details()
            output_details = interp.get_output_details()
            # TFLite inputs are positional; align by name order.
            for i, det in enumerate(input_details):
                name = det.get("name", f"input_{i}")
                if name in inputs:
                    interp.set_tensor(det["index"], inputs[name])
                elif i == 0 and len(inputs) == 1:
                    # Common case: single input, caller didn't bother to name it.
                    interp.set_tensor(det["index"], next(iter(inputs.values())))
            interp.invoke()
            return {
                det.get("name", f"output_{i}"): interp.get_tensor(det["index"])
                for i, det in enumerate(output_details)
            }

        if self.backend == Backend.OPENVINO:
            # OpenVINO 2024+: compiled model is callable.
            # inputs can be a dict keyed by name or a positional tuple.
            result = self.impl(inputs)
            # Each key is an OpenVINO output tensor; stringify for the caller.
            return {str(k): v for k, v in result.items()}

        if self.backend in (Backend.PYTORCH_CPU, Backend.PYTORCH_GPU):
            import torch
            model = self.impl
            with torch.no_grad():
                # Convert dict values to tensors on the right device.
                device = "cuda" if self.backend == Backend.PYTORCH_GPU else "cpu"
                tensors = {k: torch.as_tensor(v).to(device) for k, v in inputs.items()}
                out = model(**tensors) if hasattr(model, "forward") else model(*tensors.values())
            # Normalize output to a dict.
            if isinstance(out, dict):
                return {k: v.cpu().numpy() for k, v in out.items()}
            if isinstance(out, (list, tuple)):
                return {f"output_{i}": v.cpu().numpy() for i, v in enumerate(out)}
            return {"output": out.cpu().numpy()}

        if self.backend == Backend.COREML:
            # CoreML expects a dict keyed by input feature name.
            return dict(self.impl.predict(inputs))

        if self.backend == Backend.SKLEARN:
            # Classical estimators: pick the right method based on what the
            # object exposes. Caller passes {"X": array}; result is a dict so
            # the handler can read .predict, .predict_proba, .score_samples.
            obj = self.impl
            # Note: cannot use `or` here — numpy arrays raise on bool coercion.
            if "X" in inputs:
                X = inputs["X"]
            else:
                X = next(iter(inputs.values()))
            out: dict[str, Any] = {}
            for name in ("predict", "score_samples", "decision_function"):
                m = getattr(obj, name, None)
                if callable(m):
                    try:
                        out[name] = m(X)
                    except Exception as e:  # keep other methods working
                        out[f"{name}_error"] = str(e)
            # Dict-shaped bundle (e.g. a serialized Thompson sampler state).
            if not out and isinstance(obj, dict):
                out["state"] = obj
            return out

        raise BackendUnavailable(f"infer() not implemented for backend {self.backend}")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


_FORMAT_BACKENDS = {
    ".onnx":      [Backend.TENSORRT, Backend.ONNX_GPU, Backend.ONNX_CPU, Backend.OPENVINO],
    ".tflite":    [Backend.TFLITE],
    ".xml":       [Backend.OPENVINO],              # OpenVINO IR
    ".engine":    [Backend.TENSORRT],
    ".pt":        [Backend.PYTORCH_GPU, Backend.PYTORCH_CPU],
    ".pth":       [Backend.PYTORCH_GPU, Backend.PYTORCH_CPU],
    ".mlpackage": [Backend.COREML],
    ".mlmodel":   [Backend.COREML],
    ".joblib":    [Backend.SKLEARN],               # sklearn / numpy bundles
    ".pkl":       [Backend.SKLEARN],               # pickle (riskier; same loader)
}


def load_model(
    path: str | Path,
    prefer: list[Backend] | list[str] | None = None,
) -> ModelHandle:
    """Load a model and return a `ModelHandle`.

    The file extension decides which backends are legal; the first one
    from `prefer` (then from the global priority) that's installed wins.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"model not found: {path}")

    ext = path.suffix.lower()
    legal = _FORMAT_BACKENDS.get(ext)
    if legal is None:
        raise BackendUnavailable(f"unknown model format: {ext}. Supported: {sorted(_FORMAT_BACKENDS.keys())}")

    # Narrow the user's prefer list to backends that can load this format.
    narrowed: list[Backend] = []
    for b in (prefer or []):
        if isinstance(b, str):
            try:
                b = Backend(b.strip().lower())
            except ValueError:
                continue
        if b in legal:
            narrowed.append(b)
    # Fall back to the legal list order if nothing from prefer survived.
    if not narrowed:
        narrowed = legal

    chosen = pick(narrowed)
    if chosen is None:
        raise BackendUnavailable(
            f"no installed runtime can load {ext} files. "
            f"For {ext}, install one of: {', '.join(b.value for b in legal)}. "
            f"See docs/MODEL_OPTIMIZATION.md for install commands."
        )

    logger.info("loading %s via %s", path, chosen.value)

    if chosen in (Backend.ONNX_CPU, Backend.ONNX_GPU, Backend.TENSORRT):
        import onnxruntime as ort
        providers = {
            Backend.TENSORRT: ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"],
            Backend.ONNX_GPU: ["CUDAExecutionProvider", "CPUExecutionProvider"],
            Backend.ONNX_CPU: ["CPUExecutionProvider"],
        }[chosen]
        sess = ort.InferenceSession(str(path), providers=providers)
        return ModelHandle(chosen, sess, path, {"providers": sess.get_providers()})

    if chosen == Backend.TFLITE:
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            from tensorflow.lite import Interpreter  # type: ignore[attr-defined]
        interp = Interpreter(model_path=str(path))
        interp.allocate_tensors()
        return ModelHandle(chosen, interp, path)

    if chosen == Backend.OPENVINO:
        import openvino as ov
        core = ov.Core()
        model = core.read_model(str(path)) if ext == ".xml" else core.read_model(str(path))
        compiled = core.compile_model(model, "AUTO")
        return ModelHandle(chosen, compiled, path)

    if chosen in (Backend.PYTORCH_CPU, Backend.PYTORCH_GPU):
        import torch
        device = "cuda" if chosen == Backend.PYTORCH_GPU else "cpu"
        model = torch.load(str(path), map_location=device)
        if hasattr(model, "eval"):
            model.eval()
        return ModelHandle(chosen, model, path)

    if chosen == Backend.COREML:
        import coremltools as ct
        model = ct.models.MLModel(str(path))
        return ModelHandle(chosen, model, path)

    if chosen == Backend.SKLEARN:
        import joblib
        obj = joblib.load(str(path))
        return ModelHandle(chosen, obj, path, {"type": type(obj).__name__})

    # Fallthrough; shouldn't happen because `pick` already filtered.
    raise BackendUnavailable(f"no loader implemented for {chosen}")


# ---------------------------------------------------------------------------
# Convenience: let a worker summarize what it will use (for the audit log)
# ---------------------------------------------------------------------------


def summarize() -> dict[str, Any]:
    """Return a dict a worker can emit as a startup event."""
    avail = detect_available()
    return {
        "available": [b.value for b in avail],
        "default_pick": pick().value if avail else None,
    }


__all__ = [
    "Backend",
    "BackendUnavailable",
    "ModelHandle",
    "detect_available",
    "pick",
    "load_model",
    "summarize",
]
