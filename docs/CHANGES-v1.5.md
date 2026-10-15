# Arikizu v1.5

## v1.5.22 (real inference + zero-config auto-discovery)

Two real fixes so the demo works without yaml editing.

1. **Real YOLOv8 inference in vision worker.** The detect handler
   previously loaded the model but returned empty detections. Now:
   - Decodes browser frame (base64) or reads image from disk
   - Letterboxes to 640x640, normalizes, runs onnxruntime inference
   - Postprocesses with NMS, maps 80 COCO class ids to names
   - Returns real {class, score, bbox} per detected object
   Includes CUDA / CoreML / CPU provider auto-selection. Boxes
   drawn on the webcam are now actual detections, not canned.

2. **Workers auto-discover models in ./models/.** No yaml edit needed:
   - vision_worker picks the first .onnx (prefers yolov8n.onnx)
   - reasoning_worker picks the first .gguf
   - audio_worker already auto-discovers silero_vad.onnx
   Drop any ONNX / GGUF file in models/, restart make run, done.
   Set ARIKIZU_VISION_MODEL / ARIKIZU_REASONING_GGUF to override.

The minimum demo is now 4 commands with zero yaml editing:

```
scripts/bootstrap.sh
scripts/download-default-models.sh --tier minimum
make build
make run
```

Open http://localhost:7000/. Click vision webcam, you see real
YOLOv8 detections. Click reasoning, you get real SmolLM2 answers.
Click documents, you get real SLM-based extraction and Q&A.

## v1.5.21 (no fake boxes, PDF upload, document Q&A)
## v1.5.20 (docs extraction via SLM)
## v1.5.19 (live dashboard + visible backend)
## v1.5.18 .. v1.5 (prior history)
