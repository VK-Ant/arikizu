"""Audio worker entry point.

v0.1 scaffold. Each handler is a placeholder; the IPC path and routing are
proven even before Sonarwise is wired. Weekend 6 fills these in:

    from sonarwise import Transcriber, VAD
    transcriber = Transcriber(model="whisper-small-int8")
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

    worker = Worker("audio")

    @worker.handler("audio.transcribe")
    def transcribe(audio_path: str = "", lang: str = "en") -> dict[str, Any]:
        return {
            "audio": audio_path,
            "text": "",
            "lang": lang,
            "note": "placeholder; Sonarwise not yet wired",
        }

    @worker.handler("audio.vad")
    def vad(audio_path: str = "", threshold: float = 0.5) -> dict[str, Any]:
        return {
            "audio": audio_path,
            "segments": [],
            "threshold": threshold,
            "note": "placeholder; Sonarwise VAD not yet wired",
        }

    @worker.handler("audio.keyword_spot")
    def keyword_spot(audio_path: str = "", keywords: list[str] | None = None) -> dict[str, Any]:
        return {
            "audio": audio_path,
            "spotted": [],
            "keywords": keywords or [],
            "note": "placeholder; Sonarwise KWS not yet wired",
        }

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
