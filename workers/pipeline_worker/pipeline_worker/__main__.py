"""Pipeline worker entry point.

Loads YAML pipelines from ./pipelines/*.yaml, exposes:
  pipeline.list       - list loaded pipelines + their trigger types
  pipeline.run        - run a pipeline by name (optionally with inputs)
  pipeline.reload     - re-scan the pipelines directory
  pipeline.filter     - meta-capability for `when:` gating inside a stage
  pipeline.delay      - meta-capability: pause for N seconds inside a stage
  pipeline.classify   - meta-capability: pick a level by evaluating rules

Scheduled triggers fire automatically on the configured cron. Manual
triggers wait for a `pipeline.run` call.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import asdict
from pathlib import Path

from arikizu_worker import Worker

from .executor import META_CAPABILITIES, execute
from .loader import Pipeline, load_dir
from .scheduler import Scheduler


_PIPELINES: dict[str, Pipeline] = {}
_SCHEDULER: Scheduler | None = None


def _find_pipelines_dir() -> Path:
    override = os.environ.get("ARIKIZU_PIPELINES_DIR")
    if override:
        return Path(override)
    cwd = Path.cwd().resolve()
    for base in (cwd, *cwd.parents):
        candidate = base / "pipelines"
        if candidate.is_dir():
            return candidate
    return cwd / "pipelines"


async def _reload(root: Path) -> int:
    """Reload pipelines from disk and restart the scheduler."""
    global _PIPELINES
    new_pipelines = load_dir(root)
    if _SCHEDULER:
        await _SCHEDULER.stop()
    _PIPELINES = new_pipelines
    if _SCHEDULER:
        fired = _SCHEDULER.start(_PIPELINES)
        logging.info("pipeline_worker: reloaded %d pipelines, %d scheduled", len(_PIPELINES), fired)
    return len(_PIPELINES)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    worker = Worker("pipeline")

    pipelines_dir = _find_pipelines_dir()

    @worker.handler("pipeline.list")
    def pipeline_list() -> dict:
        """Return summary of every loaded pipeline."""
        items = []
        for p in _PIPELINES.values():
            items.append({
                "name": p.name,
                "description": p.description,
                "trigger": p.trigger.type,
                "cron": p.trigger.cron,
                "stage_count": len(p.stages),
                "source_file": p.source_file,
            })
        return {"count": len(items), "pipelines": sorted(items, key=lambda x: x["name"])}

    @worker.handler("pipeline.run")
    async def pipeline_run(name: str = "", inputs: dict | None = None) -> dict:
        """Run a loaded pipeline. Caller may pass inputs to override defaults."""
        if not name:
            return {"error": "name required"}
        p = _PIPELINES.get(name)
        if not p:
            return {"error": f"pipeline '{name}' not found. Call pipeline.list to see loaded ones."}
        if inputs:
            # Merge user-supplied inputs on top of the pipeline's defaults.
            merged = dict(p.inputs)
            merged.update(inputs)
            # Shallow-clone the pipeline so we don't mutate the loaded one.
            effective = Pipeline(
                name=p.name, description=p.description, trigger=p.trigger,
                inputs=merged, stages=p.stages, actions=p.actions,
                source_file=p.source_file,
            )
            return await execute(effective, {"source": "manual"})
        return await execute(p, {"source": "manual"})

    @worker.handler("pipeline.reload")
    async def pipeline_reload() -> dict:
        """Re-scan the pipelines directory."""
        n = await _reload(pipelines_dir)
        return {"ok": True, "loaded": n, "dir": str(pipelines_dir)}

    # Meta-capabilities are also exposed as top-level handlers so pipelines
    # from other hosts can call them, and so you can test them from the UI.
    @worker.handler("pipeline.filter")
    async def pipeline_filter(when: bool = True) -> dict:
        return await META_CAPABILITIES["pipeline.filter"]({}, {"when": when})

    @worker.handler("pipeline.delay")
    async def pipeline_delay(seconds: float = 0) -> dict:
        return await META_CAPABILITIES["pipeline.delay"]({}, {"seconds": seconds})

    @worker.handler("pipeline.classify")
    async def pipeline_classify(rules: list | None = None) -> dict:
        return await META_CAPABILITIES["pipeline.classify"]({}, {"rules": rules or []})

    # Load pipelines + start the scheduler before serving.
    async def _bootstrap_and_run() -> None:
        global _SCHEDULER
        _PIPELINES.update(load_dir(pipelines_dir))
        logging.info("pipeline_worker: loaded %d pipeline(s) from %s", len(_PIPELINES), pipelines_dir)

        async def _run_one(p: Pipeline, td: dict) -> dict:
            return await execute(p, td)
        _SCHEDULER = Scheduler(_run_one)
        fired = _SCHEDULER.start(_PIPELINES)
        if fired:
            logging.info("pipeline_worker: scheduled %d cron trigger(s)", fired)
        await worker.run()

    asyncio.run(_bootstrap_and_run())


if __name__ == "__main__":
    main()
