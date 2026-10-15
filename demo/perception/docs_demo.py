#!/usr/bin/env python3
"""Docs worker demo. DocQWise wrapper.

v0.1: placeholder (WAIT) until Weekend 7.

Usage:
 python3 demo/fixtures/make_fixtures.py
 python3 demo/perception/docs_demo.py
 python3 demo/perception/docs_demo.py /path/to/your/document.pdf
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import banner, call, print_result, require_runtime # noqa: E402


def main() -> int:
 require_runtime()
 doc = sys.argv[1] if len(sys.argv) > 1 else "demo/fixtures/sample.txt"
 if not os.path.exists(doc):
 print(f"doc not found: {doc}")
 return 2

 banner(f"Docs worker — {doc}")

 schema = {"date": "string", "shift": "string", "line": "integer", "defects": "array"}
 print_result("docs.extract (factory-report schema)",
 call("docs.extract", {"file_path": doc, "schema": schema}), show_body=True)
 print_result("docs.table (page 0)",
 call("docs.table", {"file_path": doc, "page": 0}), show_body=True)
 print_result("docs.search 'defect'",
 call("docs.search", {"query": "defect", "top_k": 3}), show_body=True)

 return 0


if __name__ == "__main__":
 sys.exit(main())
