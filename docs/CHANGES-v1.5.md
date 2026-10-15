# Arikizu v1.5

## v1.5.28 (segmentation dropdown + Vision Search fix)

Two significant fixes based on screenshots and feedback:

1. **Vision Search now actually works.**
   Root cause: the HTTP layer wasn't writing capability calls to the
   audit log. Only /api/v1/stop was. So Vision Search queried for
   past vision.detect rows and found zero.

   Fixed in `crates/ant-http/src/lib.rs`: every capability call is now
   logged with capability name, trimmed payload (base64 image bytes
   stripped and replaced with size markers so the DB stays small),
   and full result. Errors are logged separately with ".error" suffix
   so dashboards can filter them.

   After this fix, click Vision Live for 10 seconds, go to Vision
   Search, type "person" → rows appear.

2. **Detection / segmentation dropdown on Vision Live.**
   New dropdown in the control row: "detection (boxes)" or
   "segmentation (mask overlay)". The segment mode calls a new
   `vision.segment` capability and renders boxes with a 25% colored
   fill to indicate the region, not just outline. For true per-pixel
   masks, point ARIKIZU_VISION_MODEL at yolov8n-seg.onnx; same
   handler loads whichever model file is set.

Also: dashboard polls every 5s now show the audit_rows count
climbing in real time as calls hit any capability.

## v1.5.27 (vision diagnostic + more detectors + ranked memory)
## v1.5.26 (demo gaps + audio keyword spot)
## v1.5.25 .. v1.5 (prior history)
