"""AcceptancePolicy injection seam — lazy defaults and coherence_split policy (#138)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline import strip as S
from pipeline.strip import (
    AcceptancePolicy,
    GatePolicy,
    build_runtime_acceptance_policy,
)

ROOT = Path(__file__).resolve().parents[1]
REPO_PROFILES = ROOT / "gate-controls" / "acceptance-profiles.json"
REPO_MANIFEST = ROOT / "gate-controls" / "manifest.json"


def _gate_controls_copy(tmp_path: Path) -> Path:
    gate_controls = tmp_path / "gate-controls"
    shutil.copytree(ROOT / "gate-controls", gate_controls)
    return gate_controls


def _set_walk_silhouette_budget(gate_controls: Path, budget: float) -> None:
    profiles_path = gate_controls / "acceptance-profiles.json"
    doc = json.loads(profiles_path.read_text())
    doc["profiles"]["walk"]["gates"]["silhouette_budget"]["budget"] = budget
    profiles_path.write_text(json.dumps(doc, indent=2) + "\n")


def test_for_class_returns_fixture_budgets_not_repo_defaults(tmp_path: Path) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    fixture_budget = 0.9999
    _set_walk_silhouette_budget(gate_controls, fixture_budget)
    policy = build_runtime_acceptance_policy(
        profiles_path=gate_controls / "acceptance-profiles.json",
        manifest_path=gate_controls / "manifest.json",
    )
    assert isinstance(policy, AcceptancePolicy)
    walk = policy.for_class("walk")
    assert walk.max_silhouette == fixture_budget
    repo_policy = build_runtime_acceptance_policy(
        profiles_path=REPO_PROFILES,
        manifest_path=REPO_MANIFEST,
    )
    assert repo_policy.for_class("walk").max_silhouette != fixture_budget


def test_for_class_raises_for_unknown_motion_class(tmp_path: Path) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    policy = build_runtime_acceptance_policy(
        profiles_path=gate_controls / "acceptance-profiles.json",
        manifest_path=gate_controls / "manifest.json",
    )
    with pytest.raises(ValueError, match="nonesuch"):
        policy.for_class("nonesuch")


def test_build_runtime_policy_honours_gate_controls_root_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    fixture_budget = 0.8888
    _set_walk_silhouette_budget(gate_controls, fixture_budget)
    monkeypatch.setenv("UNDERLINE_GATE_CONTROLS_ROOT", str(gate_controls))
    policy = build_runtime_acceptance_policy()
    assert policy.for_class("walk").max_silhouette == fixture_budget


def test_import_performs_no_file_read(tmp_path: Path) -> None:
    empty_root = tmp_path / "empty-gate-controls"
    empty_root.mkdir()
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "UNDERLINE_GATE_CONTROLS_ROOT": str(empty_root),
    }
    result = subprocess.run(
        [sys.executable, "-c", "import pipeline.strip"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_lazy_motion_classes_match_repo_runtime_projection() -> None:
    expected = build_runtime_acceptance_policy(
        profiles_path=REPO_PROFILES,
        manifest_path=REPO_MANIFEST,
    )
    for motion_class, budget in expected.motion_classes.items():
        assert S.MOTION_CLASSES[motion_class] == budget
    for motion_class, gates in expected.acceptance_gates.items():
        assert S.ACCEPTANCE_GATES[motion_class] == gates


def _loop_sensitive_frames() -> list[list[list[S.Cell]]]:
    def frame(body: list[S.Cell]) -> list[list[S.Cell]]:
        return [
            [(1, 1, 1), None],
            [(1, 1, 1), None],
            body,
            [(2, 2, 2), (2, 2, 2)],
        ]

    stable = frame([(1, 1, 1), None])
    shifted = frame([(9, 9, 9), (1, 1, 1)])
    return [stable, stable, stable, shifted]


def test_coherence_split_uses_injected_policy_budget(tmp_path: Path) -> None:
    gate_controls = _gate_controls_copy(tmp_path)
    repo_policy = build_runtime_acceptance_policy(
        profiles_path=gate_controls / "acceptance-profiles.json",
        manifest_path=gate_controls / "manifest.json",
    )
    idle_gates = dict(repo_policy.acceptance_gates["idle"])
    loop_policy = idle_gates["loop_closure_pass"]
    tightened = GatePolicy(
        status=loop_policy.status,
        budget=0.2,
        hard_fail=loop_policy.hard_fail,
        active_promotion=loop_policy.active_promotion,
    )
    idle_gates["loop_closure_pass"] = tightened
    injected = AcceptancePolicy(
        motion_classes=repo_policy.motion_classes,
        acceptance_gates={**repo_policy.acceptance_gates, "idle": idle_gates},
    )
    frames = _loop_sensitive_frames()
    default_result = S.coherence_split(frames, motion_class="idle")
    injected_result = S.coherence_split(
        frames, motion_class="idle", policy=injected
    )
    gate_name = "loop_closure_pass"
    assert gate_name in default_result["gate_outcomes"]
    assert gate_name in injected_result["gate_outcomes"]
    assert (
        default_result["gate_outcomes"][gate_name]["outcome"]
        != injected_result["gate_outcomes"][gate_name]["outcome"]
    )
