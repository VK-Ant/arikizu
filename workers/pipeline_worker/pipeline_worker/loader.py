"""Load pipeline YAML files from pipelines/*.yaml.

Each file can contain one or more pipelines separated by `---`. Each
pipeline is validated into a Pipeline dataclass.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger("pipeline_worker.loader")


@dataclass
class Stage:
    name: str
    capability: str
    inputs: dict[str, Any] = field(default_factory=dict)
    when: str = "always"
    on_error: str = "abort"       # abort | continue | retry


@dataclass
class Action:
    type: str                      # audit | webhook | sms | email
    when: str = "always"
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trigger:
    type: str                      # manual | schedule | event | webhook | file-watch
    cron: str | None = None
    event: str | None = None
    path: str | None = None
    hook_path: str | None = None
    secret: str | None = None


@dataclass
class Pipeline:
    name: str
    description: str = ""
    trigger: Trigger = field(default_factory=lambda: Trigger(type="manual"))
    inputs: dict[str, Any] = field(default_factory=dict)
    stages: list[Stage] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    source_file: str = ""


def _parse_stage(raw: dict) -> Stage:
    if "name" not in raw or "capability" not in raw:
        raise ValueError(f"stage missing name or capability: {raw}")
    return Stage(
        name=raw["name"],
        capability=raw["capability"],
        inputs=raw.get("inputs") or {},
        when=str(raw.get("when", "always")),
        on_error=str(raw.get("on_error", "abort")),
    )


def _parse_action(raw: dict) -> Action:
    if "type" not in raw:
        raise ValueError(f"action missing type: {raw}")
    cfg = {k: v for k, v in raw.items() if k not in ("type", "when")}
    return Action(type=raw["type"], when=str(raw.get("when", "always")), config=cfg)


def _parse_trigger(raw: dict | None) -> Trigger:
    if raw is None:
        return Trigger(type="manual")
    t = raw.get("type", "manual")
    return Trigger(
        type=t,
        cron=raw.get("cron"),
        event=raw.get("event"),
        path=raw.get("path"),
        hook_path=raw.get("path") if t == "webhook" else None,
        secret=raw.get("secret"),
    )


def _parse_pipeline(doc: dict, source_file: str) -> Pipeline:
    if "name" not in doc:
        raise ValueError(f"pipeline missing name in {source_file}")
    return Pipeline(
        name=doc["name"],
        description=doc.get("description", ""),
        trigger=_parse_trigger(doc.get("trigger")),
        inputs=doc.get("inputs") or {},
        stages=[_parse_stage(s) for s in (doc.get("stages") or [])],
        actions=[_parse_action(a) for a in (doc.get("actions") or [])],
        source_file=source_file,
    )


def load_file(path: Path) -> list[Pipeline]:
    """Load every pipeline (one per --- document) from one YAML file."""
    text = path.read_text()
    pipelines: list[Pipeline] = []
    for i, doc in enumerate(yaml.safe_load_all(text)):
        if doc is None:
            continue
        if not isinstance(doc, dict):
            logger.warning("skipping non-dict document in %s (index %d)", path, i)
            continue
        try:
            pipelines.append(_parse_pipeline(doc, str(path.name)))
        except Exception as e:
            logger.exception("invalid pipeline in %s index %d: %s", path, i, e)
    return pipelines


def load_dir(root: Path, include_examples: bool = False) -> dict[str, Pipeline]:
    """Load every *.yaml in a directory. Returns {name: Pipeline}.

    By default the examples subfolder is skipped — pipelines live at the
    top level of `pipelines/`, examples are reference material. Pass
    include_examples=True for tests.
    """
    out: dict[str, Pipeline] = {}
    if not root.is_dir():
        return out
    glob_root = sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml"))
    if include_examples:
        glob_root += sorted((root / "examples").glob("*.yaml"))
    for path in glob_root:
        if path.name.startswith(("_", ".")):
            continue
        for p in load_file(path):
            if p.name in out:
                logger.warning("duplicate pipeline name %r in %s (first wins)", p.name, path.name)
                continue
            out[p.name] = p
    return out
