# Models shipped with Arikizu

These model files are included so the demos work out of the box with no
download step. Arikizu itself is Apache 2.0 licensed; the models keep
their own upstream licenses.

## yolov8n.onnx

- Model: YOLOv8n (nano) object detector, 80-class COCO
- Source: Exported from `ultralytics` v8.4.178 (yolov8n.pt weights)
- License: **AGPL-3.0** (upstream Ultralytics license)
- Weights SHA256: see yolov8n.onnx.json (if present)

Note: AGPL-3.0 applies to the model weights only, not to the rest of
the Arikizu codebase. If you redistribute Arikizu with these weights,
you must comply with AGPL-3.0 terms for the model. If you want a
non-AGPL object detector, swap in a MIT/Apache-licensed model (e.g.
NanoDet, YOLOX, MobileNet-SSD) and remove this file.

To swap models at runtime without rebuilding:
```
export ARIKIZU_VISION_MODEL=/path/to/your/model.onnx
```

## silero_vad.onnx

- Model: Silero Voice Activity Detection
- Source: `silero-vad` PyPI package v6.2.3, file `silero_vad/data/silero_vad.onnx`
- License: **MIT** (upstream Silero Team license)
- Compatible with Arikizu's Apache 2.0 license.

## Models NOT bundled

- `smollm2-360m-instruct-q4_k_m.gguf` (258 MB) is downloaded on demand via
  `scripts/download-default-models.sh`. The reasoning worker falls back to
  a built-in knowledge base when the GGUF is absent, so the demo still runs.

## Refreshing or upgrading models

```
scripts/download-default-models.sh --force
```

Or export yolov8n.onnx yourself:
```
pip install ultralytics
python3 scripts/export_yolo_onnx.py
```
