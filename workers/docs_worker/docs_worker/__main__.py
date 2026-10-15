"""Docs worker entry point. Weekend 7 wires DocQWise.

    from docqwise import DocumentExtractor
    extractor = DocumentExtractor(model="layoutlmv3-base")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from arikizu_worker import Worker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )

    worker = Worker("docs")

    @worker.handler("docs.extract")
    def extract(file_path: str = "", schema: dict | None = None) -> dict[str, Any]:
        return {
            "file": file_path,
            "fields": {},
            "schema": schema or {},
            "note": "placeholder; DocQWise not yet wired",
        }

    @worker.handler("docs.table")
    def table(file_path: str = "", page: int = 0) -> dict[str, Any]:
        return {
            "file": file_path,
            "tables": [],
            "page": page,
            "note": "placeholder; DocQWise table extraction not yet wired",
        }

    @worker.handler("docs.search")
    def search(query: str = "", top_k: int = 5) -> dict[str, Any]:
        return {
            "query": query,
            "hits": [],
            "top_k": top_k,
            "note": "placeholder; Vellex retrieval not yet wired",
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
