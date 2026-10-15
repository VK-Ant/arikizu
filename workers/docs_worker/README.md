# docs_worker

Wraps DocQWise (extraction, tables, retrieval). Weekend 7 fills in; v0.1 ships placeholders.

## Capabilities

| Capability | Payload | Result |
| -------------- | ---------------------------------------------- | --------------------------- |
| `docs.extract` | `{ file_path: str, schema: object }` | `{ fields: {...} }` |
| `docs.table` | `{ file_path: str, page: int }` | `{ tables: [...] }` |
| `docs.search` | `{ query: str, top_k: int }` | `{ hits: [...] }` |

## Wiring (Weekend 7)

```python
from docqwise import DocumentExtractor

extractor = DocumentExtractor.load("layoutlmv3-base-fp16")

@worker.handler("docs.extract")
def extract(file_path: str = "", schema: dict | None = None) -> dict:
 return {"file": file_path, "fields": extractor(file_path, schema or {})}
```

## Supported inputs

The extractor accepts the file formats SightRAG passes through: PDF (text + scanned), DOCX, HTML, plain text, Markdown. For images-of-documents the request can go to `vision.ocr` first and then to `docs.extract` with the OCR'd text as `file_path` using a `text:` prefix. The pipeline executor handles the hand-off through the carried JSON.
