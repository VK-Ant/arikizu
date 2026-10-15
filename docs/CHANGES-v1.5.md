# Arikizu v1.5

## v1.5.21 (no fake boxes, PDF upload, document Q&A)

Four fixes based on the "nothing works" / "which model" feedback:

1. **No more fake bounding boxes on the webcam.** Removed the canned
   detections that drew 4 boxes over everyone's face. When the vision
   model is not loaded, the API now returns zero detections and a
   note telling you exactly which command downloads the model. The
   webcam frame shows alone, no fake overlays.

2. **New download script URLs.** Replaced with the version from the
   user. Vision model now from HuggingFace Kalray mirror, SmolLM2
   from unsloth GGUF (both work reliably). Script now also prints
   ARIKIZU_REASONING_GGUF in the final "Environment" block so people
   see exactly which env var to set in arikizu.yaml.

3. **PDF upload for Documents demo.** The Documents demo now accepts
   .pdf files. pdf.js is lazy-loaded from CDN on first PDF upload,
   extracts text in the browser, then sends the plain text to the
   server where the SLM extracts fields. .txt / .md / .log / .csv
   still work as before.

4. **Ask-a-question mode for Documents.** New "Ask" input alongside
   schema-based extract. Upload a document, type a question, click
   Ask, SLM returns an answer based on the document contents.
   Example: "what defects were observed?" over a shift report.

Combined with v1.5.20 (SLM-based extraction), Documents demo is
real document AI: upload PDF -> OCR text -> LLM answers either as
JSON fields (schema) or free-form (Q&A).

## v1.5.20 (docs extraction via SLM)
## v1.5.19 (live dashboard + visible backend)
## v1.5.18 (removed Vellex)
## v1.5.17 .. v1.5 (prior history)
