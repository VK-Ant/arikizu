"""Qwen2.5-VL via llama-cpp-python for multimodal action search.

Three operating modes, picked at init time:

1. local-gguf: Qwen2.5-VL-3B GGUF + mmproj loaded via llama-cpp-python.
   The primary mode. Local, quantized, no network.

2. http: an external VLM endpoint (Ollama, vLLM, your own) via
   ARIKIZU_VLM_ENDPOINT. Used when the GGUF is not on disk but the user
   has a VLM server reachable.

3. none: VLM unavailable. The worker still runs; VLM-dependent capabilities
   return a note explaining what's missing. Perception + rule-based action
   recognition keep working.

Default-OFF behavior: the VLM is not loaded at worker start even if the GGUF
is on disk, unless ARIKIZU_VLM_AUTOLOAD=1 or the device has >= 6 GB RAM.
Load it on first VLM-requiring call.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from . import models

logger = logging.getLogger(__name__)

VLM_HTTP_ENDPOINT = os.environ.get("ARIKIZU_VLM_ENDPOINT", "")
VLM_HTTP_MODEL = os.environ.get("ARIKIZU_VLM_HTTP_MODEL", "qwen2.5-vl:3b")
VLM_AUTOLOAD = os.environ.get("ARIKIZU_VLM_AUTOLOAD", "").lower() in ("1", "true", "yes")

try:
    import llama_cpp  # noqa: F401
    LLAMA_CPP_OK = True
    LLAMA_CPP_ERR = ""
except Exception as e:
    LLAMA_CPP_OK = False
    LLAMA_CPP_ERR = str(e)


@dataclass
class VLMResult:
    text: str
    confidence: float
    backend: str
    tokens: int
    ms: float


_LOCAL_VLM = None   # Lazy-init Llama instance
_LOCAL_VLM_ERROR = ""


def backend_available() -> dict[str, Any]:
    """Reportable status for video.backends."""
    gguf_present = models.is_present("qwen2_5_vl_3b_q4")
    mmproj_present = models.is_present("qwen2_5_vl_3b_mmproj")
    mode = "none"
    if LLAMA_CPP_OK and gguf_present and mmproj_present:
        mode = "local-gguf"
    elif VLM_HTTP_ENDPOINT:
        mode = "http"
    return {
        "mode": mode,
        "llama_cpp_installed": LLAMA_CPP_OK,
        "llama_cpp_error": LLAMA_CPP_ERR,
        "gguf_present": gguf_present,
        "mmproj_present": mmproj_present,
        "http_endpoint": VLM_HTTP_ENDPOINT or "(not set)",
        "loaded": _LOCAL_VLM is not None,
        "load_error": _LOCAL_VLM_ERROR,
        "autoload": VLM_AUTOLOAD,
    }


def _ensure_local() -> bool:
    """Lazy-load the local GGUF VLM. Returns True on success."""
    global _LOCAL_VLM, _LOCAL_VLM_ERROR
    if _LOCAL_VLM is not None:
        return True
    if not LLAMA_CPP_OK:
        _LOCAL_VLM_ERROR = f"llama-cpp-python not installed: {LLAMA_CPP_ERR}"
        return False
    if not models.is_present("qwen2_5_vl_3b_q4") or not models.is_present("qwen2_5_vl_3b_mmproj"):
        _LOCAL_VLM_ERROR = "Qwen GGUF or mmproj missing. Download with: scripts/download-vlm.sh"
        return False
    try:
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import Llava15ChatHandler
        gguf = models.path_for("qwen2_5_vl_3b_q4")
        mmproj = models.path_for("qwen2_5_vl_3b_mmproj")
        logger.info("loading Qwen2.5-VL 3B Q4 from %s with mmproj %s", gguf, mmproj)
        chat_handler = Llava15ChatHandler(clip_model_path=str(mmproj), verbose=False)
        _LOCAL_VLM = Llama(
            model_path=str(gguf),
            chat_handler=chat_handler,
            n_ctx=4096,
            n_gpu_layers=int(os.getenv("ARIKIZU_VLM_GPU_LAYERS", "0")),
            logits_all=True,
            verbose=False,
        )
        return True
    except Exception as e:
        _LOCAL_VLM = None
        _LOCAL_VLM_ERROR = f"VLM load failed: {type(e).__name__}: {e}"
        logger.exception("VLM load failed")
        return False


def _bytes_to_data_url(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _structured_action_prompt(action_query: str) -> str:
    """System+user text asking for strict JSON about one action query."""
    return (
        "You look at a single frame and report whether a given action is happening.\n"
        "Respond with ONLY a JSON object matching this schema:\n"
        '{"matches": true|false, "confidence": 0.0..1.0, "evidence": "<one short sentence>", '
        '"actors": ["person", "dog", ...]}\n'
        f'Question: Is the following action happening in this frame: "{action_query}"?'
    )


def _describe_prompt() -> str:
    return (
        "Describe what is happening in this frame. Return ONLY a JSON object:\n"
        '{"actions": ["<action in a few words>", ...], "scene": "<indoor | outdoor + room/place>", '
        '"actors": ["person", "dog", ...], "notable_objects": [...], "confidence": 0.0..1.0}'
    )


def _parse_json_loose(text: str) -> dict:
    """Qwen tends to wrap JSON in prose. Extract the first {...} block."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end < start:
        return {"raw": text}
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return {"raw": text}


def _call_local(prompt: str, image_bytes: bytes, max_tokens: int = 200) -> VLMResult:
    """One VLM round-trip against the local Llama instance."""
    import time
    if not _ensure_local():
        return VLMResult(text="", confidence=0.0, backend="none", tokens=0, ms=0.0)
    t = time.perf_counter()
    data_url = _bytes_to_data_url(image_bytes)
    try:
        resp = _LOCAL_VLM.create_chat_completion(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        text = resp["choices"][0]["message"]["content"] or ""
        tokens = int(resp.get("usage", {}).get("total_tokens", 0))
    except Exception as e:
        logger.exception("local VLM call failed")
        return VLMResult(text=f"error: {e}", confidence=0.0, backend="local-gguf", tokens=0, ms=0.0)
    ms = round((time.perf_counter() - t) * 1000, 1)
    return VLMResult(text=text, confidence=1.0, backend="local-gguf", tokens=tokens, ms=ms)


def _call_http(prompt: str, image_bytes: bytes, max_tokens: int = 200) -> VLMResult:
    """OpenAI-shape chat completion against VLM_HTTP_ENDPOINT."""
    import time
    import httpx
    data_url = _bytes_to_data_url(image_bytes)
    body = {
        "model": VLM_HTTP_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": prompt},
            ],
        }],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    t = time.perf_counter()
    try:
        r = httpx.post(VLM_HTTP_ENDPOINT, json=body, timeout=120)
        r.raise_for_status()
        resp = r.json()
        text = resp["choices"][0]["message"]["content"]
        tokens = int(resp.get("usage", {}).get("total_tokens", 0))
    except Exception as e:
        logger.exception("http VLM call failed")
        return VLMResult(text=f"error: {e}", confidence=0.0, backend="http", tokens=0, ms=0.0)
    ms = round((time.perf_counter() - t) * 1000, 1)
    return VLMResult(text=text, confidence=1.0, backend="http", tokens=tokens, ms=ms)


def _dispatch(prompt: str, image_bytes: bytes, max_tokens: int = 200) -> VLMResult:
    """Pick the best available backend for one call."""
    mode = backend_available()["mode"]
    if mode == "local-gguf":
        return _call_local(prompt, image_bytes, max_tokens)
    if mode == "http":
        return _call_http(prompt, image_bytes, max_tokens)
    return VLMResult(text="", confidence=0.0, backend="none", tokens=0, ms=0.0)


def score_action(action_query: str, image_bytes: bytes) -> dict[str, Any]:
    """Multimodal action search for ONE frame.

    Returns {"matches": bool, "confidence": float, "evidence": str,
             "actors": [...], "backend": str, "ms": float, "raw": str}
    """
    prompt = _structured_action_prompt(action_query)
    r = _dispatch(prompt, image_bytes, max_tokens=200)
    parsed = _parse_json_loose(r.text)
    return {
        "matches": bool(parsed.get("matches", False)),
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "evidence": parsed.get("evidence", "")[:200],
        "actors": parsed.get("actors", []) if isinstance(parsed.get("actors"), list) else [],
        "backend": r.backend,
        "ms": r.ms,
        "raw": parsed.get("raw", ""),
    }


def describe_frame(image_bytes: bytes) -> dict[str, Any]:
    """Open-ended per-frame description used when no prompt is given."""
    prompt = _describe_prompt()
    r = _dispatch(prompt, image_bytes, max_tokens=300)
    parsed = _parse_json_loose(r.text)
    return {
        "actions": parsed.get("actions", []) if isinstance(parsed.get("actions"), list) else [],
        "scene": parsed.get("scene", "") or "",
        "actors": parsed.get("actors", []) if isinstance(parsed.get("actors"), list) else [],
        "notable_objects": parsed.get("notable_objects", []) if isinstance(parsed.get("notable_objects"), list) else [],
        "confidence": float(parsed.get("confidence", 0.0) or 0.0),
        "backend": r.backend,
        "ms": r.ms,
        "raw": parsed.get("raw", ""),
    }


def describe_reference_image(image_bytes: bytes) -> dict[str, Any]:
    """Turn a reference-image action into a text description we can later use
    to search a target video. This gives us 'show-me-this-action' from a
    single screenshot without a trained matching model."""
    prompt = (
        "This image shows a specific action. Describe the action in ONE short "
        "sentence that could be used as a search query for a different video. "
        "Focus on the body posture and what the actor is doing. Ignore clothing, "
        "race, gender, age and background. Reply ONLY with JSON:\n"
        '{"action_phrase": "<the search query>", "actors": ["person", ...]}'
    )
    r = _dispatch(prompt, image_bytes, max_tokens=120)
    parsed = _parse_json_loose(r.text)
    return {
        "action_phrase": parsed.get("action_phrase", "") or "",
        "actors": parsed.get("actors", []) if isinstance(parsed.get("actors"), list) else [],
        "backend": r.backend,
        "ms": r.ms,
        "raw": parsed.get("raw", ""),
    }
