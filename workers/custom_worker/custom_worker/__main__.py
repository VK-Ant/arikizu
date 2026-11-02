"""The custom worker: load every Python file in ./custom/ and expose
each decorated function as an Arikizu capability.

A user who wants to add their own logic drops a file like
`custom/my_logic.py` with:

    from arikizu_worker import Worker
    worker = Worker.current()         # the single shared worker instance

    @worker.handler("my.calculate")
    def calculate(a: float, b: float) -> dict:
        return {"result": a + b}

Then adds the TOML entry in `capabilities.d/my_logic.toml`:

    [my_calculate]
    name = "my.calculate"
    worker = "custom"
    input = { a = "number", b = "number" }
    output = "object"
    timeout_ms = 5000

Restart the custom worker and the capability is live at
    POST /api/v1/call/my/calculate
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import sys
import time
from pathlib import Path

from arikizu_worker import Worker


# ---------------------------------------------------------------------------
# A module-level singleton so user files can import a shared worker.
# ---------------------------------------------------------------------------

_WORKER: Worker | None = None


def current_worker() -> Worker:
    """Return the shared Worker instance so user modules can register handlers."""
    global _WORKER
    if _WORKER is None:
        raise RuntimeError("custom_worker not initialized yet")
    return _WORKER


# Make this discoverable as `Worker.current()` for convenience.
Worker.current = staticmethod(current_worker)  # type: ignore[attr-defined]


def _find_custom_dir() -> Path:
    """Walk up from CWD to find the arikizu root (holds custom/)."""
    override = os.environ.get("ARIKIZU_CUSTOM_DIR")
    if override:
        return Path(override)
    cwd = Path.cwd().resolve()
    for base in (cwd, *cwd.parents):
        candidate = base / "custom"
        if candidate.is_dir():
            return candidate
    # Fall back: create one in cwd so logs are honest.
    return cwd / "custom"


def _load_user_files(custom_dir: Path) -> list[str]:
    """Import every top-level .py file in custom/ as a module.

    Skips files starting with _ or . (private / draft).
    Returns the list of file names loaded, in alphabetical order.
    """
    if not custom_dir.is_dir():
        logging.warning("custom dir %s does not exist; no user capabilities", custom_dir)
        return []

    loaded: list[str] = []
    sys.path.insert(0, str(custom_dir))     # so files can `import` siblings
    for path in sorted(custom_dir.glob("*.py")):
        if path.name.startswith(("_", ".")):
            continue
        mod_name = f"arikizu_custom_{path.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if not spec or not spec.loader:
            logging.warning("could not build import spec for %s", path)
            continue
        try:
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            loaded.append(path.name)
        except Exception as e:
            logging.exception("failed to load %s: %s", path, e)
            # Don't abort the whole worker over one bad user file.
    return loaded


def _snapshot_dir(custom_dir: Path) -> dict[str, float]:
    """Map {filename: mtime} of top-level .py files for the watch loop."""
    out: dict[str, float] = {}
    if not custom_dir.is_dir():
        return out
    for path in custom_dir.glob("*.py"):
        if path.name.startswith(("_", ".")):
            continue
        try:
            out[path.name] = path.stat().st_mtime
        except OSError:
            continue
    return out


def _reload_user_files(custom_dir: Path) -> int:
    """Clear previous handlers and re-import every file. Returns handler count."""
    assert _WORKER is not None
    _WORKER.handlers.clear()
    # Drop old imported modules so Python re-executes them.
    for key in list(sys.modules):
        if key.startswith("arikizu_custom_"):
            del sys.modules[key]
    loaded = _load_user_files(custom_dir)
    logging.info(
        "custom_worker reloaded: %d file(s), %d capabilit(ies): %s",
        len(loaded), len(_WORKER.handlers), sorted(_WORKER.handlers.keys()),
    )
    return len(_WORKER.handlers)


async def _watch_loop(custom_dir: Path, interval: float = 1.0) -> None:
    """Poll the custom directory and reload when anything changes.

    Polling (not inotify) because it works identically on Linux, Mac, WSL,
    and inside containers, with no extra deps. 1-second cadence is well
    below human edit latency and the import cost is small for user files.
    """
    snapshot = _snapshot_dir(custom_dir)
    while True:
        await asyncio.sleep(interval)
        new_snap = _snapshot_dir(custom_dir)
        if new_snap != snapshot:
            logging.info("custom_worker: change detected in %s, reloading", custom_dir)
            try:
                _reload_user_files(custom_dir)
            except Exception as e:
                logging.exception("custom_worker: reload failed: %s", e)
            snapshot = new_snap


async def _run_with_watch(custom_dir: Path) -> None:
    assert _WORKER is not None
    watcher = asyncio.create_task(_watch_loop(custom_dir))
    try:
        await _WORKER.run()
    finally:
        watcher.cancel()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s - %(message)s",
    )
    global _WORKER
    _WORKER = Worker("custom")

    custom_dir = _find_custom_dir()
    loaded = _load_user_files(custom_dir)

    if not loaded:
        logging.info("custom_worker: no user files in %s. Add a .py file; it loads automatically.", custom_dir)
    else:
        logging.info(
            "custom_worker: loaded %d user file(s) from %s, exposing %d capabilit(ies): %s",
            len(loaded), custom_dir, len(_WORKER.handlers),
            sorted(_WORKER.handlers.keys()),
        )

    # Hot reload is on by default. Disable with ARIKIZU_CUSTOM_NO_WATCH=1.
    if os.environ.get("ARIKIZU_CUSTOM_NO_WATCH"):
        logging.info("custom_worker: hot reload disabled (ARIKIZU_CUSTOM_NO_WATCH)")
        asyncio.run(_WORKER.run())
    else:
        logging.info("custom_worker: hot reload ON — edit %s/*.py and it takes effect in ~1 s", custom_dir)
        asyncio.run(_run_with_watch(custom_dir))


if __name__ == "__main__":
    main()
