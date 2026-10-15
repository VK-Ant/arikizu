# ant-models

Model manifests, SHA-256 integrity verification, and backend selection.

## Backends and selection order

The reference backend priority (`default_priority`):

```
TensorRT  >  ONNX GPU  >  CUDA PyTorch  >  OpenVINO  >  ONNX CPU  >  PyTorch CPU  >  llama.cpp
```

`select_backend(available: &[Backend])` picks the highest-priority entry present on this device. The device detection to feed it lives in `ant-devices`.

## Manifest format

Each model carries a manifest (JSON on disk; v0.1 keeps it next to the model file):

```json
{
  "name": "yolov8n-defect",
  "version": "1.3.0",
  "sha256": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
  "size_bytes": 10485760,
  "backend": "onnx_gpu",
  "input_shape": [1, 3, 640, 640],
  "license": "AGPL-3.0"
}
```

## API

```rust
use ant_models::{ModelManifest, verify, select_backend, Backend};

let manifest: ModelManifest = serde_json::from_str(json)?;
verify(&manifest, "./models/yolov8n-defect.onnx")?;    // SHA-256 check

let available = vec![Backend::OnnxGpu, Backend::OnnxCpu];
let chosen = select_backend(&available);
```

A `verify` failure returns `ArikizuError::ModelIntegrityFailure { expected, actual }`. The CLI's `arikizu pull` command (Weekend 9) uses this before writing a model to disk.

## Tests

```
cargo test -p ant-models
```

Covers: SHA-256 of a known file, backend priority selection, serde round-trip of a manifest.
