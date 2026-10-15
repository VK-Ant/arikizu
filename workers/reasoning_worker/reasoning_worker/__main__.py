"""Reasoning worker entry point.

Talks to any Ollama-compatible endpoint over HTTP. By pointing at the
right URL you cover three strategies without changing code:

  1. Device-only: ARIKIZU_OLLAMA_ENDPOINT=http://127.0.0.1:11434  (local Ollama)
  2. LAN gateway: ARIKIZU_OLLAMA_ENDPOINT=http://192.168.1.50:11434
  3. Cloud API:   ARIKIZU_OLLAMA_ENDPOINT=https://api.groq.com/openai
                  ARIKIZU_API_KEY=<your key>

Model name comes from ARIKIZU_REASONING_MODEL. Full discussion of what
runs where lives in docs/MODEL_STRATEGY.md.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from arikizu_worker import Worker

OLLAMA_ENDPOINT = os.environ.get("ARIKIZU_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
MODEL = os.environ.get("ARIKIZU_REASONING_MODEL", "qwen2.5:3b-instruct-q4_K_M")
API_KEY = os.environ.get("ARIKIZU_API_KEY", "")

# OpenAI-compatible endpoints use /v1/chat/completions; Ollama's native API
# uses /api/generate. Pick based on the URL shape.
USE_OPENAI_SHAPE = (
    "openai" in OLLAMA_ENDPOINT.lower()
    or "/v1" in OLLAMA_ENDPOINT
    or "groq" in OLLAMA_ENDPOINT.lower()
    or "deepinfra" in OLLAMA_ENDPOINT.lower()
    or "together" in OLLAMA_ENDPOINT.lower()
    or "anthropic" in OLLAMA_ENDPOINT.lower()
)


async def _generate(prompt: str, max_tokens: int = 256) -> str:
    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    if USE_OPENAI_SHAPE:
        base = OLLAMA_ENDPOINT.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        url = f"{base}/chat/completions"
        body = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
        return data["choices"][0]["message"]["content"]

    # Ollama native shape
    url = f"{OLLAMA_ENDPOINT}/api/generate"
    body = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data.get("response", "")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )

    logger = logging.getLogger("reasoning")
    logger.info("endpoint=%s shape=%s model=%s", OLLAMA_ENDPOINT,
                "openai" if USE_OPENAI_SHAPE else "ollama", MODEL)

    worker = Worker("reasoning")

    @worker.handler("reasoning.answer")
    async def answer(question: str = "", context: str = "", max_tokens: int = 256) -> dict[str, Any]:
        prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
        try:
            text = await _generate(prompt, max_tokens=max_tokens)
            return {"answer": text.strip(), "model": MODEL, "endpoint": OLLAMA_ENDPOINT}
        except Exception as e:
            return {"answer": "", "error": str(e), "model": MODEL, "endpoint": OLLAMA_ENDPOINT}

    @worker.handler("reasoning.summarize")
    async def summarize(text: str = "", template: str = "", max_tokens: int = 200) -> dict[str, Any]:
        prompt = template or f"Summarize the following in 3 bullet points:\n\n{text}\n\nSummary:"
        if "{text}" in prompt:
            prompt = prompt.format(text=text)
        try:
            out = await _generate(prompt, max_tokens=max_tokens)
            return {"summary": out.strip(), "model": MODEL, "endpoint": OLLAMA_ENDPOINT}
        except Exception as e:
            return {"summary": "", "error": str(e), "model": MODEL, "endpoint": OLLAMA_ENDPOINT}

    @worker.handler("reasoning.complete")
    async def complete(prompt: str = "", max_tokens: int = 256) -> dict[str, Any]:
        try:
            out = await _generate(prompt, max_tokens=max_tokens)
            return {"completion": out, "model": MODEL, "endpoint": OLLAMA_ENDPOINT}
        except Exception as e:
            return {"completion": "", "error": str(e), "model": MODEL, "endpoint": OLLAMA_ENDPOINT}

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
