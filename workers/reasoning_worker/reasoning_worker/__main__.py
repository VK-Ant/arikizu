"""Reasoning worker entry point.

Backend auto-selection, in order:

  1. Local GGUF model via llama-cpp-python when
     ARIKIZU_REASONING_GGUF points to a readable file.
  2. HTTP endpoint (local LLM runtime, LAN gateway, or OpenAI-compatible
     cloud API) when the socket at ARIKIZU_OLLAMA_ENDPOINT answers.
  3. Demo-mode fallback: the chat UI still works and returns a short
     canned message explaining how to enable real reasoning.

The dashboard never sees a connection error; worst case it sees the
demo response, which is friendlier than a stack trace.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from arikizu_worker import Worker

OLLAMA_ENDPOINT = os.environ.get("ARIKIZU_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
MODEL = os.environ.get("ARIKIZU_REASONING_MODEL", "qwen2.5:0.5b")
API_KEY = os.environ.get("ARIKIZU_API_KEY", "")
GGUF_PATH = os.environ.get("ARIKIZU_REASONING_GGUF", "")

# OpenAI-compatible endpoints use /v1/chat/completions; the local runtime's
# native API uses /api/generate. Pick based on the URL shape.
USE_OPENAI_SHAPE = (
    "openai" in OLLAMA_ENDPOINT.lower()
    or "/v1" in OLLAMA_ENDPOINT
    or "groq" in OLLAMA_ENDPOINT.lower()
    or "deepinfra" in OLLAMA_ENDPOINT.lower()
    or "together" in OLLAMA_ENDPOINT.lower()
)

# Lazy local-model handle; populated on first successful load.
_LLAMA = {"obj": None, "tried": False}


def _demo_response(question: str) -> str:
    q = (question or "").strip() or "(empty question)"
    return (
        f"Demo mode. The reasoning worker is up but has no model loaded, "
        f"so it can only echo back a canned message instead of a real "
        f"answer.\n\n"
        f"Your question was: {q!r}\n\n"
        f"To enable real answers, pick one:\n"
        f"  - Install a local LLM runtime inside your shell:\n"
        f"      curl -fsSL https://ollama.com/install.sh | sh\n"
        f"      ollama serve &\n"
        f"      ollama pull qwen2.5:0.5b\n"
        f"  - Or point ARIKIZU_OLLAMA_ENDPOINT at a LAN or cloud endpoint.\n"
        f"  - Or set ARIKIZU_REASONING_GGUF to a local GGUF model file.\n\n"
        f"The dashboard, audit log, vision, audio, documents, time series, "
        f"memory, guard and eval all work without any LLM. Reasoning is "
        f"the only capability that needs one."
    )


def _try_load_local() -> Any:
    """Return a loaded llama_cpp.Llama handle, or None.

    Only runs once; subsequent calls return the cached result.
    """
    if _LLAMA["tried"]:
        return _LLAMA["obj"]
    _LLAMA["tried"] = True

    if not GGUF_PATH or not os.path.isfile(GGUF_PATH):
        return None
    try:
        from llama_cpp import Llama  # type: ignore
    except Exception:
        return None
    try:
        _LLAMA["obj"] = Llama(
            model_path=GGUF_PATH,
            n_ctx=2048,
            n_threads=max(2, (os.cpu_count() or 4) - 1),
            verbose=False,
        )
    except Exception:
        _LLAMA["obj"] = None
    return _LLAMA["obj"]


def _generate_local(prompt: str, max_tokens: int) -> str | None:
    """Try the local GGUF model. Return text, or None if unavailable."""
    llm = _try_load_local()
    if llm is None:
        return None
    try:
        out = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=0.4,
            stop=["</s>", "<|im_end|>", "User:"],
        )
        return out["choices"][0]["text"].strip()
    except Exception:
        return None


async def _generate_http(prompt: str, max_tokens: int) -> str | None:
    """Try the HTTP endpoint. Return text, or None on any failure."""
    headers: dict[str, str] = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    try:
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
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(url, json=body, headers=headers)
                r.raise_for_status()
                data = r.json()
            return data["choices"][0]["message"]["content"]

        url = f"{OLLAMA_ENDPOINT}/api/generate"
        body = {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
        return data.get("response", "") or None
    except Exception:
        return None


async def _generate(prompt: str, question: str, max_tokens: int) -> tuple[str, str]:
    """Try local, then HTTP, then demo mode. Returns (text, backend)."""
    text = _generate_local(prompt, max_tokens)
    if text:
        return text, "local-gguf"

    text = await _generate_http(prompt, max_tokens)
    if text:
        return text, "http"

    return _demo_response(question), "demo"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("reasoning")

    local_available = GGUF_PATH and os.path.isfile(GGUF_PATH)
    logger.info(
        "reasoning backends: local_gguf=%s http=%s model=%s",
        "yes" if local_available else "no",
        OLLAMA_ENDPOINT,
        MODEL,
    )

    worker = Worker("reasoning")

    @worker.handler("reasoning.answer")
    async def answer(question: str = "", context: str = "", max_tokens: int = 256) -> dict[str, Any]:
        prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
        text, backend = await _generate(prompt, question, max_tokens)
        return {"answer": text.strip(), "model": MODEL, "backend": backend}

    @worker.handler("reasoning.summarize")
    async def summarize(text_in: str = "", template: str = "", max_tokens: int = 200) -> dict[str, Any]:
        prompt = template or f"Summarize the following in 3 bullet points:\n\n{text_in}\n\nSummary:"
        if "{text}" in prompt:
            prompt = prompt.format(text=text_in)
        text, backend = await _generate(prompt, text_in[:80], max_tokens)
        return {"summary": text.strip(), "model": MODEL, "backend": backend}

    @worker.handler("reasoning.complete")
    async def complete(prompt: str = "", max_tokens: int = 256) -> dict[str, Any]:
        text, backend = await _generate(prompt, prompt[:80], max_tokens)
        return {"completion": text, "model": MODEL, "backend": backend}

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
