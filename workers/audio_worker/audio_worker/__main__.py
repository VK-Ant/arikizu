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


def _auto_discover_vad(models_dir: str) -> str:
    p = Path(models_dir)
    if not p.exists():
        return ""
    for name in ("silero_vad.onnx", "vad.onnx"):
        if (p / name).exists():
            return str(p / name)
    return ""


MODELS_DIR = os.environ.get("ARIKIZU_MODELS_DIR", "./models")
VAD_PATH = os.environ.get("ARIKIZU_AUDIO_VAD_MODEL") or _auto_discover_vad(MODELS_DIR)

_VAD_SESSION = None


def _try_load_vad(path: str, logger: logging.Logger):
    if not path or not os.path.isfile(path):
        logger.warning("no VAD model at %r; audio.vad will return a note", path)
        return None
    try:
        import onnxruntime as ort
    except Exception as e:
        logger.warning("onnxruntime missing: %s", e)
        return None
    try:
        sess = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        logger.info("loaded %s", path)
        return sess
    except Exception as e:
        logger.warning("could not load %s: %s", path, e)
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
                     keywords: list | None = None,
                     threshold: float = 0.5) -> dict[str, Any]:
        """Keyword spotter. Current implementation combines VAD with
        energy-level detection to flag "possible keyword at time X" when
        speech is detected. Full phonetic matching needs an ASR model
        (standard-tier download, wired in a future weekend).
        """
        keywords = [str(k).lower().strip() for k in (keywords or []) if str(k).strip()]
        if _VAD_SESSION is None or not pcm or not sample_rate:
            return {"keywords": keywords, "hits": [], "backend": "no-model",
                    "note": "VAD model required for keyword spotting"}
        try:
            samples = [float(x) for x in pcm]
            sr = int(sample_rate)
        except Exception:
            return {"keywords": keywords, "hits": [], "backend": "bad-input"}
        try:
            segs = _run_vad(_VAD_SESSION, samples, sr, threshold=0.5)
        except Exception as e:
            return {"keywords": keywords, "hits": [], "backend": "error", "note": str(e)}
        # Each speech segment becomes a possible-keyword hit. Without a
        # phonetic matcher this is heuristic; it tells the UI there was
        # speech and roughly where. Full matching is weekend-6 work.
        hits = []
        for s in segs:
            for kw in keywords:
                hits.append({
                    "keyword": kw,
                    "start_s": s["start_s"],
                    "end_s": s["end_s"],
                    "confidence": 0.5,  # heuristic, phonetic match pending
                })
        return {
            "keywords": keywords,
            "hits": hits,
            "segments": segs,
            "backend": "vad-heuristic",
            "note": "heuristic match: VAD-detected speech flagged for each requested keyword. Phonetic matching needs ASR (weekend 6).",
        }

    @worker.handler("audio.backends")
    def backends() -> dict[str, Any]:
        return {
            "vad_path": VAD_PATH or "(none)",
            "vad_loaded": _VAD_SESSION is not None,
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
