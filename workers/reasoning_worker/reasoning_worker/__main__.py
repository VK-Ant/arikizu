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

def _auto_discover_gguf() -> str:
    """Pick the first .gguf file in ./models/ so no yaml edit is needed."""
    for d in (os.environ.get("ARIKIZU_MODELS_DIR", "./models"), "./models", "../models"):
        if not os.path.isdir(d):
            continue
        files = sorted(f for f in os.listdir(d) if f.endswith(".gguf"))
        if files:
            return os.path.join(d, files[0])
    return ""


OLLAMA_ENDPOINT = os.environ.get("ARIKIZU_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
MODEL = os.environ.get("ARIKIZU_REASONING_MODEL", "smollm2-360m")
API_KEY = os.environ.get("ARIKIZU_API_KEY", "")
GGUF_PATH = os.environ.get("ARIKIZU_REASONING_GGUF", "") or _auto_discover_gguf()

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


# Built-in micro knowledge base. Keeps the demo useful when no real LLM
# is wired. The matches are keyword-based, not semantic; they are good
# enough to show the chat UI works and answer "what is Arikizu"-type
# questions.
_KB: list[tuple[list[str], str]] = [
    (
        ["what", "arikizu"],
        "Arikizu is an edge-first, offline-first operating system for a single "
        "device. One Rust supervisor runs ten Python workers behind one capability "
        "API: vision, audio, documents, reasoning, time series, memory, PII guard, "
        "eval, and more. Everything runs locally; no cloud account required."
    ),
    (
        ["how", "install"],
        "On Linux or WSL: `scripts/check_prereqs.sh && scripts/bootstrap.sh && "
        "make build && make run`. Open http://localhost:7000/ in your browser. "
        "Full walkthrough is in docs/SETUP.md."
    ),
    (
        ["prerequisite", "prereq", "requirement"],
        "Four things: Rust (via rustup), uv (Python package manager), git, and make. "
        "On low-RAM devices like Pi 4, add 4 GB swap. The script "
        "`scripts/check_prereqs.sh` tells you what is missing."
    ),
    (
        ["vision", "detect", "camera"],
        "The vision worker handles object detection, segmentation, and tracking. "
        "The default model is a compact ONNX detector. Click the Vision card on "
        "the dashboard, then Start (fixture) or Use webcam. The webcam button uses "
        "the browser's camera, so no OS-level camera passthrough is needed."
    ),
    (
        ["audio", "speech", "transcribe", "voice"],
        "The audio worker handles voice activity detection and speech-to-text. "
        "Upload a short .wav file in the Audio demo and click Analyze. VAD segments "
        "and transcript appear below the waveform."
    ),
    (
        ["document", "extract", "docs"],
        "The docs worker extracts fields from text or markdown files using a "
        "schema you provide. Open the Documents demo, pass the sample.txt file "
        "and the default schema, click Extract. It returns date, shift, line, "
        "and defects pulled from the text."
    ),
    (
        ["memory", "recall", "remember"],
        "The memory worker is session-scoped: update, recall, and reward. It uses "
        "top-k retrieval with a reward signal that nudges future results. Try the "
        "Memory demo on the sandbox."
    ),
    (
        ["guard", "pii", "redact", "privacy"],
        "The guard worker scans text for PII (emails, phone numbers, SSNs, etc.) "
        "and returns a redacted version alongside the hits. Paste any sensitive "
        "sample on the Guard demo page."
    ),
    (
        ["model", "swap", "custom"],
        "Any ONNX, TFLite, OpenVINO, TensorRT, or CoreML model works. Point the "
        "worker's ARIKIZU_VISION_MODEL (or equivalent) env var at your file. "
        "The backend is auto-selected per device."
    ),
    (
        ["pi", "raspberry", "jetson", "edge"],
        "Arikizu runs on Jetson Orin Nano / AGX, Raspberry Pi 4/5, Mac (Apple "
        "Silicon or Intel), Linux x86_64, and WSL2 on Windows. Same binary, same "
        "code; backend auto-detects the device. See docs/SETUP.md for the "
        "device-by-device walkthrough."
    ),
    (
        ["license", "open source", "oss"],
        "Arikizu is licensed Apache 2.0. The source lives at "
        "github.com/VK-Ant/arikizu. The brand mark and logo belong to the project."
    ),
    (
        ["hello", "hi", "hey"],
        "Hello. I am the Arikizu reasoning worker in built-in mode. Ask me about "
        "what Arikizu is, how to install it, or any specific capability. For "
        "general knowledge questions, point ARIKIZU_REASONING_GGUF at a local "
        "GGUF model file or install a local LLM runtime for real LLM answers."
    ),
]


def _kb_answer(question: str) -> str | None:
    """Pick a KB entry if its keywords all appear in the question."""
    q = (question or "").lower()
    best: tuple[int, str] | None = None
    for words, answer in _KB:
        if all(w in q for w in words):
            score = sum(len(w) for w in words)
            if best is None or score > best[0]:
                best = (score, answer)
    return best[1] if best else None


def _builtin_response(question: str) -> str:
    """Return the KB answer when any keywords match; else a short explainer."""
    hit = _kb_answer(question)
    if hit:
        return hit
    q = (question or "").strip() or "(empty question)"
    return (
        f"I am the Arikizu reasoning worker in built-in mode. For your question "
        f"({q!r}) I have no canned answer. For real LLM responses, point "
        f"ARIKIZU_REASONING_GGUF at a local GGUF file (any size), set "
        f"ARIKIZU_OLLAMA_ENDPOINT to a running LLM runtime, or try asking a "
        f"question about Arikizu itself: what it is, how to install it, how a "
        f"specific worker works."
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

    return _builtin_response(question), "builtin"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("reasoning")

    gguf_exists = GGUF_PATH and os.path.isfile(GGUF_PATH)
    try:
        import llama_cpp  # noqa: F401
        llama_cpp_installed = True
    except Exception:
        llama_cpp_installed = False
    logger.info(
        "reasoning backends: gguf_path=%r gguf_exists=%s llama_cpp_installed=%s "
        "http_endpoint=%s model=%s",
        GGUF_PATH or "(unset)", gguf_exists, llama_cpp_installed,
        OLLAMA_ENDPOINT, MODEL,
    )
    if gguf_exists and llama_cpp_installed:
        logger.info("reasoning: will use local-gguf backend on first call")
    elif gguf_exists and not llama_cpp_installed:
        logger.warning(
            "reasoning: GGUF file found but llama-cpp-python not installed. "
            "Install with: cd workers && uv add llama-cpp-python --package reasoning-worker"
        )
    elif not gguf_exists and GGUF_PATH:
        logger.warning(
            "reasoning: ARIKIZU_REASONING_GGUF=%s does not exist. "
            "Download with: scripts/download-default-models.sh --tier minimum",
            GGUF_PATH,
        )
    else:
        logger.info(
            "reasoning: no local GGUF configured; will try HTTP then fall to builtin KB"
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
