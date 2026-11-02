"""Cron scheduler for pipeline triggers.

Each scheduled pipeline runs on its own asyncio task. We use croniter to
compute next-fire times. Falls back to a stub if croniter is unavailable
(so the worker still boots and manual triggers work).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Awaitable, Callable

from .loader import Pipeline


logger = logging.getLogger("pipeline_worker.scheduler")

try:
    from croniter import croniter
    _HAVE_CRONITER = True
except ImportError:
    _HAVE_CRONITER = False


class Scheduler:
    """Fires scheduled pipelines by cron expression."""

    def __init__(self, run_fn: Callable[[Pipeline, dict], Awaitable[dict]]):
        self._run = run_fn
        self._tasks: list[asyncio.Task] = []
        self._stopping = False

    def start(self, pipelines: dict[str, Pipeline]) -> int:
        """Spawn one background task per scheduled pipeline. Returns count."""
        count = 0
        for name, p in pipelines.items():
            if p.trigger.type != "schedule" or not p.trigger.cron:
                continue
            if not _HAVE_CRONITER:
                logger.warning(
                    "schedule trigger on %s needs croniter: pip install croniter. Skipping.",
                    name,
                )
                continue
            task = asyncio.create_task(self._loop(p))
            self._tasks.append(task)
            count += 1
        return count

    async def stop(self) -> None:
        self._stopping = True
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    async def _loop(self, pipeline: Pipeline) -> None:
        cron_expr = pipeline.trigger.cron
        try:
            itr = croniter(cron_expr, datetime.now())
        except Exception as e:
            logger.error("invalid cron for %s: %r: %s", pipeline.name, cron_expr, e)
            return

        logger.info("scheduled %s on cron %r", pipeline.name, cron_expr)
        while not self._stopping:
            next_fire = itr.get_next(datetime)
            wait_s = (next_fire - datetime.now()).total_seconds()
            if wait_s > 0:
                try:
                    await asyncio.sleep(wait_s)
                except asyncio.CancelledError:
                    return
            # Fire
            try:
                started = time.perf_counter()
                report = await self._run(pipeline, {"source": "schedule", "fired_at": time.time()})
                logger.info(
                    "pipeline %s fired by schedule: ok=%s stages=%d duration=%dms",
                    pipeline.name, report.get("ok"), len(report.get("stages", {})),
                    int((time.perf_counter() - started) * 1000),
                )
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.exception("pipeline %s run failed: %s", pipeline.name, e)
