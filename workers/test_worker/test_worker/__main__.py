"""Entry point for the Arikizu test worker.

Run under the supervisor; it sets ARIKIZU_SOCKET and spawns this process.
Standalone invocation (for debugging) requires setting that env var manually.
"""

from __future__ import annotations

import asyncio
import logging

from arikizu_worker import Worker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )

    worker = Worker("test")

    @worker.handler("test.echo")
    def echo(message: str = "") -> dict:
        return {"echo": message}

    @worker.handler("test.add")
    def add(a: int = 0, b: int = 0) -> dict:
        return {"sum": a + b}

    @worker.handler("test.slow")
    async def slow(seconds: float = 0.5) -> dict:
        await asyncio.sleep(seconds)
        return {"slept": seconds}

    asyncio.run(worker.run())


if __name__ == "__main__":
    main()
