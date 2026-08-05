"""Subprocess proof for pipeline.final_polish_cli's `finalize` subcommand (#96, #101, #264).

`finalize`, the release frames it creates on PASS, and the `npm run
strip:polish` entry-point test that exercises `init`, `check`, and `finalize`
through a real subprocess (`AGENTS.md` § Evidence). A test that asserts on
`init` argument handling or a `check` report belongs in
tests/test_final_polish_cli_init.py or tests/test_final_polish_cli_check.py
instead.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline.final_polish_cli import main
from pipeline.gate_evidence import sha256_file
from pipeline.strip import IngestResult, ingest_strip_provider
from tests.support import polish_bundle as pb
from tests.support.corpus_paths import INBOX
from tests.support.final_polish_testkit import (
    FRAME_COUNT,
    ROOT,
    corpus_layout,
    first_opaque_xy,
    run_cli,
    set_opaque_rgb,
)
from tests.support.polish_bundle import bundle_store_env
from tests.support.polish_review_fixture import write_passing_reviews

PASS_STRIP = INBOX / "01-miner-idle.png"


def _idle_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path, polish_profile="miner")
    pb.init_bundle(attempt, bundle)
    return bundle


def _run_npm(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    import os

    run_env = os.environ.copy()
    if env is not None:
        run_env.update(env)
    return subprocess.run(
        ["npm", "run", "strip:polish", "--", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=run_env,
    )


def test_npm_entrypoint_runs_init_check_finalize(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path, polish_profile="miner")
    args = pb.init_argv(attempt, bundle)
    env = dict(attempt.env)
    init = _run_npm(args, env=env)
    assert init.returncode == 0, init.stderr
    assert bundle.is_dir()

    check = _run_npm(["check", str(bundle)], env=env)
    assert check.returncode == 0, check.stderr

    packet = _run_npm(["review-packet", str(bundle), "--json"], env=env)
    assert packet.returncode == 0, packet.stderr

    answers = {
        row["id"]: ("PASS", "ok")
        for key in ("fixed_questions", "motion_questions")
        for row in json.loads((bundle / "reviews" / "packet.json").read_text())[key]
    }
    from tests.support.polish_review_fixture import write_review

    write_review(
        bundle,
        ordinal=1,
        reviewer_id="cli-reviewer",
        reviewer_session_id="cli-session",
        answers=answers,
    )
    validate = _run_npm(["validate-reviews", str(bundle), "--json"], env=env)
    assert validate.returncode == 0, validate.stderr

    finalize = _run_npm(["finalize", str(bundle)], env=env)
    assert finalize.returncode == 0, finalize.stderr
    assert list((bundle / "release").glob("*.png"))


def test_finalize_pass_exit_0_and_creates_release(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    write_passing_reviews(bundle)
    result = run_cli(capsys, ["finalize", str(bundle)], env=bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    assert "Report" in result.stdout
    assert "Release" in result.stdout
    assert (bundle / "release" / "frame-0.png").is_file()


def test_finalize_pass_json_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    write_passing_reviews(bundle)
    result = run_cli(capsys, ["finalize", str(bundle), "--json"], env=bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["outcome"] == "PASS"
    assert "report_path" in data
    assert "release_frames" in data
    assert len(data["release_frames"]) == FRAME_COUNT


def test_finalize_fail_json_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    x, y = first_opaque_xy(polished)
    set_opaque_rgb(polished, x, y, (250, 1, 2))
    write_passing_reviews(bundle)

    result = run_cli(capsys, ["finalize", str(bundle), "--json"], env=bundle_store_env(bundle))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["outcome"] == "FAIL"
    assert "report_path" in data
    assert "release_frames" not in data


def test_finalize_review_exit_3_records_report(tmp_path: Path, capsys) -> None:
    bundle = _idle_bundle(tmp_path)
    write_passing_reviews(bundle)
    base = ingest_strip_provider(bundle / "provider" / "source.png", corpus_layout(), motion_class="idle")
    review = IngestResult(
        layout=base.layout,
        source=base.source,
        recovered=base.recovered,
        slice_meta=base.slice_meta,
        coherence={**base.coherence, "outcome": "REVIEW", "pass": False},
        pass_=False,
        outcome="REVIEW",
    )
    with patch("pipeline.final_polish.ingest_strip_provider", return_value=review):
        with patch.dict("os.environ", bundle_store_env(bundle) or {}):
            code = main(["finalize", str(bundle)])
    assert code == 3
    captured = capsys.readouterr().out
    assert "Overall  REVIEW" in captured
    assert "Report" in captured
    assert len(list((bundle / "reports").glob("*.json"))) == 1
    assert not (bundle / "release").exists()


def test_finalize_review_json_exit_3(tmp_path: Path, capsys) -> None:
    bundle = _idle_bundle(tmp_path)
    write_passing_reviews(bundle)
    base = ingest_strip_provider(bundle / "provider" / "source.png", corpus_layout(), motion_class="idle")
    review = IngestResult(
        layout=base.layout,
        source=base.source,
        recovered=base.recovered,
        slice_meta=base.slice_meta,
        coherence={**base.coherence, "outcome": "REVIEW", "pass": False},
        pass_=False,
        outcome="REVIEW",
    )
    with patch("pipeline.final_polish.ingest_strip_provider", return_value=review):
        with patch.dict("os.environ", bundle_store_env(bundle) or {}):
            from pipeline.final_polish_cli import main

            code = main(["finalize", str(bundle), "--json"])
    assert code == 3
    data = json.loads(capsys.readouterr().out)
    assert data["outcome"] == "REVIEW"
    assert "report_path" in data
    assert "release_frames" not in data


def test_finalize_fail_exit_1_records_report_without_release(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    x, y = first_opaque_xy(polished)
    set_opaque_rgb(polished, x, y, (250, 1, 2))
    write_passing_reviews(bundle)

    result = run_cli(capsys, ["finalize", str(bundle)], env=bundle_store_env(bundle))
    assert result.returncode == 1
    assert "Report" in result.stdout
    assert "Release" not in result.stdout
    assert not (bundle / "release").exists()
    assert len(list((bundle / "reports").glob("*.json"))) == 1


def test_finalize_revalidates_and_lists_release_only_on_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = first_opaque_xy(polished)
    set_opaque_rgb(polished, x, y, (250, 1, 2))
    write_passing_reviews(bundle)

    fail = run_cli(capsys, ["finalize", str(bundle)], env=bundle_store_env(bundle))
    assert fail.returncode == 1
    report_path = next((bundle / "reports").glob("*.json"))
    report = json.loads(report_path.read_text())
    assert report["outcome"] == "FAIL"
    assert "release_frames" not in report
    assert "Report" in fail.stdout

    draft = bundle / "draft" / "frame-0.png"
    polished.write_bytes(draft.read_bytes())
    import shutil

    shutil.rmtree(bundle / "reviews")
    write_passing_reviews(bundle)

    pass_result = run_cli(capsys, ["finalize", str(bundle)], env=bundle_store_env(bundle))
    assert pass_result.returncode == 0, pass_result.stderr
    assert "Report" in pass_result.stdout
    release_paths = sorted((bundle / "release").glob("*.png"))
    assert len(release_paths) == FRAME_COUNT
    for path in release_paths:
        polished_path = bundle / "polished" / path.name
        assert sha256_file(path) == sha256_file(polished_path)
