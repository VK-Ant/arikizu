"""Audio worker. Real Silero VAD inference on the shipped sample.

Auto-discovers the VAD model in ./models/. Returns real speech
segments (start/end seconds) for any .wav file passed to audio.vad.
Transcription stays as a note until a real ASR model is wired.
"""

from __future__ import annotations

import asyncio
import logging
import os
import wave
from pathlib import Path
from typing import Any

from arikizu_worker import Worker


def _find_project_root_early() -> Path:
    """Same project-root walk the vision worker uses. The supervisor spawns
    us from workers/audio_worker/, so './models' needs resolving against
    the project root, not our package dir."""
    p = Path.cwd().resolve()
    for parent in [p] + list(p.parents):
        if (parent / "arikizu.yaml.example").exists() or \
           (parent / "capabilities.toml").exists() or \
           (parent / "Cargo.toml").exists():
            return parent
    return p


def _resolve_models_dir(env_value: str) -> str:
    if os.path.isabs(env_value):
        return env_value
    root = _find_project_root_early()
    candidate = root / env_value
    if candidate.exists():
        return str(candidate)
    return str(Path(env_value).resolve())


def _auto_discover_vad(models_dir: str) -> str:
    p = Path(models_dir)
    if not p.exists():
        return ""
    for name in ("silero_vad.onnx", "vad.onnx"):
        if (p / name).exists():
            return str(p / name)
    return ""


MODELS_DIR = _resolve_models_dir(os.environ.get("ARIKIZU_MODELS_DIR", "./models"))
VAD_PATH = os.environ.get("ARIKIZU_AUDIO_VAD_MODEL") or _auto_discover_vad(MODELS_DIR)

_VAD_SESSION = None
_LOAD_ERROR = ""  # last reason VAD failed to load, surfaced via audio.backends


def _try_load_vad(path: str, logger: logging.Logger):
    global _LOAD_ERROR
    _LOAD_ERROR = ""
    if not path:
        _LOAD_ERROR = (
            f"no VAD file found. Looked in MODELS_DIR={MODELS_DIR!r}; "
            "set ARIKIZU_AUDIO_VAD_MODEL or run scripts/download-default-models.sh"
        )
        logger.warning(_LOAD_ERROR)
        return None
    if not os.path.isfile(path):
        _LOAD_ERROR = f"VAD path does not exist: {path!r}"
        logger.warning(_LOAD_ERROR)
        return None
    try:
        import onnxruntime as ort
    except Exception as e:
        _LOAD_ERROR = f"onnxruntime not installed: {e}. Fix: cd workers && uv sync"
        logger.warning(_LOAD_ERROR)
        return None
    try:
        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        logger.info("loaded %s", path)
        return sess
    except Exception as e:
        _LOAD_ERROR = f"onnxruntime failed to load {path!r}: {type(e).__name__}: {e}"
        logger.warning(_LOAD_ERROR)
        return None


def _read_wav(path: str) -> tuple[list[float], int] | None:
    """Return (samples in [-1,1], sample rate) from a wav file. Mono only."""
    # Try several locations for relative paths
    candidates = [Path(path)]
    if not Path(path).is_absolute():
        for base in (Path.cwd(), Path.cwd().parent, Path.cwd() / ".."):
            candidates.append(base / path)
    for p in candidates:
        if not p.exists():
            continue
        try:
            with wave.open(str(p), "rb") as w:
                sr = w.getframerate()
                nch = w.getnchannels()
                sw = w.getsampwidth()
                nframes = w.getnframes()
                raw = w.readframes(nframes)
            if sw == 2:
                import array
                a = array.array("h")
                a.frombytes(raw)
                samples = [x / 32768.0 for x in a]
            elif sw == 1:
                import array
                a = array.array("B")
                a.frombytes(raw)
                samples = [(x - 128) / 128.0 for x in a]
            else:
                return None
            # Downmix to mono
            if nch > 1:
                samples = [sum(samples[i:i+nch]) / nch for i in range(0, len(samples), nch)]
            return samples, sr
        except Exception:
            continue
    return None


def _run_vad(session, samples: list[float], sr: int,
             threshold: float = 0.5) -> list[dict[str, float]]:
    """Run Silero VAD across the audio and return speech segments."""
    import numpy as np

    # Silero expects 16kHz. Linear resample if needed.
    if sr != 16000:
        ratio = 16000 / sr
        new_len = int(len(samples) * ratio)
        xs = np.linspace(0, len(samples) - 1, new_len)
        indices = xs.astype(int)
        samples = [samples[i] for i in indices]
        sr = 16000

    window = 512  # Silero v5 window size at 16kHz
    audio = np.array(samples, dtype=np.float32)
    state = np.zeros((2, 1, 128), dtype=np.float32)
    sr_arr = np.array(sr, dtype=np.int64)
    probs = []
    for i in range(0, len(audio) - window + 1, window):
        chunk = audio[i:i + window].reshape(1, -1)
        try:
            out = session.run(None, {"input": chunk, "state": state, "sr": sr_arr})
            prob = float(out[0].flatten()[0])
            state = out[1]
        except Exception:
            # Older Silero signature
            try:
                h = np.zeros((2, 1, 64), dtype=np.float32)
                c = np.zeros((2, 1, 64), dtype=np.float32)
                out = session.run(None, {"input": chunk, "h": h, "c": c, "sr": sr_arr})
                prob = float(out[0].flatten()[0])
            except Exception:
                prob = 0.0
        probs.append(prob)

    # Convert per-window probs into segments
    segments: list[dict[str, float]] = []
    in_seg = False
    start_i = 0
    for i, p in enumerate(probs):
        if p >= threshold and not in_seg:
            in_seg = True
            start_i = i
        elif p < threshold and in_seg:
            in_seg = False
            segments.append({
                "start_s": round(start_i * window / sr, 3),
                "end_s": round(i * window / sr, 3),
            })
    if in_seg:
        segments.append({
            "start_s": round(start_i * window / sr, 3),
            "end_s": round(len(probs) * window / sr, 3),
        })
    return segments


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    logger = logging.getLogger("audio")

    global _VAD_SESSION
    _VAD_SESSION = _try_load_vad(VAD_PATH, logger)
    if _VAD_SESSION:
        logger.info("audio ready: real Silero VAD on %s", VAD_PATH)
    else:
        logger.warning(
            "audio in no-model mode. Fix: scripts/download-default-models.sh --tier minimum"
        )

    worker = Worker("audio")

    def _read_pcm_json(payload: dict) -> tuple[list[float], int] | None:
        """Browser mic sends raw PCM samples as a list of floats."""
        if "pcm" in payload and "sample_rate" in payload:
            try:
                samples = [float(x) for x in payload["pcm"]]
                return samples, int(payload["sample_rate"])
            except Exception:
                return None
        return None

    @worker.handler("audio.vad")
    def vad(audio_path: str = "", pcm: list | None = None,
            sample_rate: int = 0, threshold: float = 0.5) -> dict[str, Any]:
        if _VAD_SESSION is None:
            return {
                "audio": audio_path,
                "segments": [],
                "backend": "no-model",
                "note": "VAD model not loaded. Run scripts/download-default-models.sh then restart.",
            }
        # Branch 1: live browser mic chunk sent as PCM list
        if pcm and sample_rate:
            try:
                samples = [float(x) for x in pcm]
                sr = int(sample_rate)
            except Exception:
                return {"audio": "(mic chunk)", "segments": [], "backend": "no-pcm"}
        else:
            data = _read_wav(audio_path)
            if data is None:
                return {
                    "audio": audio_path,
                    "segments": [],
                    "backend": "no-file",
                    "note": f"could not read {audio_path} (must be .wav)",
                }
            samples, sr = data
        try:
            segs = _run_vad(_VAD_SESSION, samples, sr, threshold)
            # Compute an overall "any speech" probability for live display
            has_speech = any(s["end_s"] - s["start_s"] > 0 for s in segs)
            return {
                "audio": audio_path or "(mic chunk)",
                "segments": segs,
                "sample_rate": sr,
                "duration_s": round(len(samples) / sr, 3),
                "speech_detected": has_speech,
                "backend": "silero-onnx",
            }
        except Exception as e:
            return {
                "audio": audio_path,
                "segments": [],
                "backend": "error",
                "note": f"VAD failed: {e}",
            }

    @worker.handler("audio.transcribe")
    def transcribe(audio_path: str = "", lang: str = "en") -> dict[str, Any]:
        return {
            "audio": audio_path,
            "text": "",
            "lang": lang,
            "backend": "no-model",
            "note": "ASR requires standard-tier download. Not yet wired as a full pipeline.",
        }

    @worker.handler("audio.keyword_spot")
    def keyword_spot(pcm: list | None = None, sample_rate: int = 0,
                     keywords: list | None = None, transcript: str = "",
                     threshold: float = 0.5) -> dict[str, Any]:
        """Keyword spotter. Two modes:

        1. transcript= passed in: do a real substring match against it.
           This is what the browser demo uses (it transcribes with
           Web Speech API and sends the text here for logging).
        2. pcm= passed in with no transcript: fall back to VAD-only
           (speech-detected signal), since without ASR we can't tell
           "help" from "hello". Full on-device phonetic matching lands
           when the Whisper encoder is wired as a full ASR pipeline.
        """
        keywords = [str(k).lower().strip() for k in (keywords or []) if str(k).strip()]
        # Mode 1: real transcript-based match
        text = str(transcript or "").lower()
        if text:
            hits = []
            for kw in keywords:
                if kw and kw in text:
                    hits.append({"keyword": kw, "transcript": text[:200], "confidence": 0.95})
            return {
                "keywords": keywords,
                "transcript": text[:500],
                "hits": hits,
                "backend": "transcript-match",
            }
        # Mode 2: pcm chunk, no transcript. Return VAD signal only.
        if _VAD_SESSION is None or not pcm or not sample_rate:
            return {"keywords": keywords, "hits": [], "backend": "no-model",
                    "note": "pass transcript= from browser ASR, or install the VAD model"}
        try:
            samples = [float(x) for x in pcm]
            sr = int(sample_rate)
        except Exception:
            return {"keywords": keywords, "hits": [], "backend": "bad-input"}
        try:
            segs = _run_vad(_VAD_SESSION, samples, sr,
                            threshold=max(0.2, float(threshold) if threshold else 0.3))
        except Exception as e:
            return {"keywords": keywords, "hits": [], "backend": "error", "note": str(e)}
        return {
            "keywords": keywords,
            "hits": [],
            "segments": segs,
            "speech_detected": bool(segs),
            "backend": "vad-only",
            "note": "speech detected but no transcript to match keywords against. Browser demo should pass transcript=.",
        }

    @worker.handler("audio.backends")
    def backends() -> dict[str, Any]:
        try:
            import onnxruntime as ort
            ort_version = ort.__version__
        except Exception as e:
            ort_version = f"not installed: {e}"
        return {
            "vad_path": VAD_PATH or "(none)",
            "models_dir": MODELS_DIR,
            "cwd": os.getcwd(),
            "vad_loaded": _VAD_SESSION is not None,
            "load_error": _LOAD_ERROR or ("" if _VAD_SESSION is not None else "VAD not loaded; see audio_worker logs"),
            "onnxruntime_version": ort_version,
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
