"""Corpus runner tri-state reporting against prompts/manifest.json."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from tests.support.corpus_paths import CORPUS_ROOT, ROOT

sys.path.insert(0, str(CORPUS_ROOT))

import corpus  # noqa: E402
from pipeline import strip as S  # noqa: E402
from pipeline.numeric_policy import canonical_metric  # noqa: E402


class _CallResult:
    """Mimics the subprocess.CompletedProcess fields the tests assert on."""

    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_corpus(capsys: pytest.CaptureFixture[str]) -> _CallResult:
    code = corpus.main()
    captured = capsys.readouterr()
    return _CallResult(code, captured.out, captured.err)


def test_evaluate_returns_pass_for_good_idle() -> None:
    path = corpus.find_png("01-miner-idle")
    assert path is not None
    result = corpus.evaluate(path, motion_class="idle")
    assert result["outcome"] == "PASS"
    assert result["pass"] is True
    assert result["review_gates"] == []
    assert result["failed_gates"] == []


def test_evaluate_fail_negative_control() -> None:
    path = corpus.find_png("07-NEG-palette-drift")
    assert path is not None
    result = corpus.evaluate(path, motion_class="idle")
    assert result["outcome"] == "FAIL"
    assert "palette_drift_pass" in result["failed_gates"]


def test_evaluate_review_lists_review_gates_separately() -> None:
    import adversarial

    path = corpus.find_png("01-miner-idle")
    assert path is not None
    layout = S.StripLayout(
        frame_w=16,
        frame_h=24,
        frame_count=4,
        gutter=2,
        pitch_px=24,
        margin_cells=0,
    )
    cells, _ = S.recover_strip_cells(path, layout)
    frames, _ = S.slice_frames_pitch(cells, frame_count=4)
    mutated = adversarial.wrong_pose(frames)
    coh = S.coherence_split(mutated, motion_class="idle")
    assert coh["outcome"] == "REVIEW"
    assert coh["gate_outcomes"]["silhouette_budget"]["outcome"] == "REVIEW"
    assert coh["gate_outcomes"]["silhouette_budget"]["outcome"] != "FAIL"


def test_metric_at_hard_fail_boundary_is_fail_not_review() -> None:
    path = corpus.find_png("07-NEG-palette-drift")
    assert path is not None
    result = corpus.evaluate(path, motion_class="idle")
    policy = S.ACCEPTANCE_GATES["idle"]["palette_drift_pass"]
    assert policy.hard_fail is not None
    layout = S.StripLayout(
        frame_w=16,
        frame_h=24,
        frame_count=4,
        gutter=2,
        pitch_px=24,
        margin_cells=0,
    )
    ingest = S.ingest_strip_provider(path, layout, motion_class="idle")
    drift = ingest.coherence["gate_outcomes"]["palette_drift_pass"]
    assert canonical_metric(ingest.coherence["worst_palette_drift"]) == drift["hard_fail"]
    assert drift["outcome"] == "FAIL"
    assert result["outcome"] == "FAIL"


@pytest.mark.slow
def test_corpus_command_preserves_manifest_agreement(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = _run_corpus(capsys)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "scored 23/23" in result.stdout
    assert "regressions 0" in result.stdout

    npm = subprocess.run(
        ["npm", "run", "-s", "prototype:strip:corpus"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert npm.returncode == 0, npm.stdout + npm.stderr
    assert "scored 23/23" in npm.stdout
    assert "regressions 0" in npm.stdout
