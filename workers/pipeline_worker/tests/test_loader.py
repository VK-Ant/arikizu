"""Loader tests: parse the real example pipelines + inline fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline_worker.loader import load_dir, load_file


def test_loads_ships_examples():
    """Every example YAML that ships with the repo should parse."""
    root = Path(__file__).resolve().parents[3] / "pipelines" / "examples"
    if not root.is_dir():
        pytest.skip("ships-examples not present in this checkout")
    pipelines: dict = {}
    for p in root.glob("*.yaml"):
        for pipe in load_file(p):
            pipelines[pipe.name] = pipe
    # At least one example loaded, and all have at least one stage.
    assert pipelines, "expected to load the shipped examples"
    for p in pipelines.values():
        assert p.stages, f"{p.name} has no stages"


def test_load_minimal(tmp_path: Path):
    (tmp_path / "min.yaml").write_text(
        "name: m1\n"
        "stages:\n"
        "  - name: step1\n"
        "    capability: test.echo\n"
        "    inputs: {message: hi}\n"
    )
    out = load_dir(tmp_path)
    assert "m1" in out
    assert out["m1"].stages[0].capability == "test.echo"


def test_multi_pipeline_yaml(tmp_path: Path):
    (tmp_path / "multi.yaml").write_text(
        "name: p1\n"
        "stages: []\n"
        "---\n"
        "name: p2\n"
        "stages: []\n"
    )
    out = load_dir(tmp_path)
    assert set(out.keys()) == {"p1", "p2"}


def test_underscore_file_skipped(tmp_path: Path):
    (tmp_path / "_draft.yaml").write_text(
        "name: draft_pipeline\n"
        "stages: []\n"
    )
    (tmp_path / "real.yaml").write_text(
        "name: real_pipeline\n"
        "stages: []\n"
    )
    out = load_dir(tmp_path)
    assert "real_pipeline" in out
    assert "draft_pipeline" not in out


def test_trigger_defaults_to_manual(tmp_path: Path):
    (tmp_path / "a.yaml").write_text("name: n1\nstages: []\n")
    out = load_dir(tmp_path)
    assert out["n1"].trigger.type == "manual"


def test_schedule_trigger_parsed(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(
        "name: cron1\n"
        "trigger: {type: schedule, cron: '0 * * * *'}\n"
        "stages: []\n"
    )
    out = load_dir(tmp_path)
    assert out["cron1"].trigger.type == "schedule"
    assert out["cron1"].trigger.cron == "0 * * * *"
