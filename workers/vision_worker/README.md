# vision_worker

Wraps SightRAG. v0.1 scaffold ships placeholder handlers; Weekend 5 fills them in.

## Capabilities

| Capability        | Payload                                        | Result                                |
| ----------------- | ---------------------------------------------- | ------------------------------------- |
| `vision.detect`   | `{ image_path: str, confidence: float }`       | `{ detections: [...] }`               |
| `vision.ocr`      | `{ image_path: str, lang: str }`               | `{ text: str, lang: str }`            |
| `vision.caption`  | `{ image_path: str }`                          | `{ caption: str }`                    |

## Wiring SightRAG (Weekend 5)

```python
# vision_worker/__main__.py
from sightrag import Detector, OCRReader, Captioner

detector = Detector.load("yolov8n-defect.onnx", backend="onnx_gpu")
ocr      = OCRReader.default()
captioner = Captioner.load("blip-2-xl-q4")

@worker.handler("vision.detect")
def detect(image_path: str = "", confidence: float = 0.5) -> dict:
    detections = detector(image_path, conf=confidence)
    return {"image": image_path, "detections": [d.to_dict() for d in detections]}
```

Keep the handler signature stable; the capability spec in `capabilities.toml` is what the runtime trusts.

## Model placement

- Place model files under `./models/vision/` (gitignored by default)
- Each file carries a sidecar `.json` manifest; see `ant-models/README.md` for the format
- `arikizu pull vision` (Weekend 15) downloads and verifies

## Try the placeholder

```
arikizu call vision.detect '{"image_path":"/tmp/sample.jpg","confidence":0.5}'
# -> {"image":"/tmp/sample.jpg","detections":[],"note":"placeholder; SightRAG not yet wired"}
```
