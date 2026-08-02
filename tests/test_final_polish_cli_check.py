"""Subprocess proof for pipeline.final_polish_cli's `check` subcommand (#96, #101, #264).

`check`, its human and `--json`/`--summary-json` payloads, and `brief` (the
bundle's visual audit profile, which is read-only exactly like `check`). A
test that asserts on `init` argument handling or a `finalize` release belongs
in tests/test_final_polish_cli_init.py or tests/test_final_polish_cli_finalize.py
instead.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline.gate_evidence import sha256_file
from pipeline.strip import (
    IngestResult,
    ingest_strip_provider,
    load_provider_frames,
)
from tests.support import polish_bundle as pb
from tests.support.final_polish_testkit import (
    FRAME_COUNT,
    LANTERN_STRIP,
    PASS_STRIP,
    WALK_STRIP,
    CliResult,
    corpus_layout,
    first_opaque_xy,
    LOGICAL_SIZE,
    run_cli,
    set_opaque_rgb,
    swing_provider_strip,
)
from tests.support.polish_bundle import bundle_store_env


def _idle_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    pb.init_bundle(attempt, bundle)
    return bundle


def _bundle_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.parent.name != "reports":
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _run_check_cli(
    capsys: pytest.CaptureFixture[str],
    bundle: Path,
    ingest_source: Path,
    *,
    json_mode: bool = True,
) -> CliResult:
    args = ["check", str(bundle)]
    if json_mode:
        args.append("--json")
    with patch(
        "pipeline.final_polish.load_provider_frames",
        side_effect=lambda path, layout: load_provider_frames(ingest_source, layout),
    ):
        return run_cli(capsys, args, env=bundle_store_env(bundle))


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class", "motion_ids"),
    [
        ("dwarf-miner", WALK_STRIP, "walk", ["alternating_legs", "stable_torso"]),
        ("lantern", LANTERN_STRIP, "emissive", ["emission_inside_lamp", "no_terrain_halo"]),
    ],
)
def test_brief_json_selects_production_profile_motion_questions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    profile_id: str,
    strip: Path,
    motion_class: str,
    motion_ids: list[str],
) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(strip, motion_class, tmp_path, polish_profile=profile_id)
    pb.init_bundle(attempt, bundle)
    before = _bundle_fingerprint(bundle)

    result = run_cli(capsys, ["brief", str(bundle), "--json"])

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["profile"]["id"] == profile_id
    assert data["motion_class"] == motion_class
    assert [row["id"] for row in data["motion_questions"]] == motion_ids
    assert _bundle_fingerprint(bundle) == before


def test_check_pass_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    result = run_cli(capsys, ["check", str(bundle)], env=bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    assert "Overall  PASS" in result.stdout


def test_check_summary_json_emits_only_dispatch_baseline_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _idle_bundle(tmp_path)

    result = run_cli(capsys, ["check", str(bundle), "--summary-json"], env=bundle_store_env(bundle))

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert set(data) == {
        "outcome",
        "fingerprint",
        "frame_dimensions",
        "identity_lock",
        "gate_outcomes",
        "attestation",
    }
    assert data["outcome"] == "PASS"
    assert len(data["fingerprint"]) == 64
    assert data["frame_dimensions"] == [[16, 24]]
    assert data["identity_lock"] is None
    assert set(data["gate_outcomes"]) == {
        "silhouette_budget",
        "palette_drift_pass",
        "min_pair_cohort_pass",
        "loop_closure_pass",
    }
    assert {gate["outcome"] for gate in data["gate_outcomes"].values()} == {"PASS"}


def test_brief_json_is_read_only_and_selects_walk_questions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(WALK_STRIP, "walk", tmp_path, polish_profile="miner")
    pb.init_bundle(attempt, bundle)
    before = _bundle_fingerprint(bundle)

    result = run_cli(capsys, ["brief", str(bundle), "--json"])

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["profile"]["id"] == "miner"
    assert data["motion_class"] == "walk"
    assert [row["id"] for row in data["motion_questions"]] == [
        "alternating_legs",
        "stable_belt_buckle",
    ]
    assert data["verdicts"] == ["PASS", "EDIT", "UNCERTAIN"]
    assert data["fixed_questions"]
    assert data["editing_rules"]
    assert data["audit_workflow"]
    assert _bundle_fingerprint(bundle) == before


def test_brief_human_output_is_actionable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(WALK_STRIP, "walk", tmp_path, polish_profile="miner")
    pb.init_bundle(attempt, bundle)

    result = run_cli(capsys, ["brief", str(bundle)])

    assert result.returncode == 0, result.stderr
    assert "Profile   miner" in result.stdout
    assert "Verdicts  PASS, EDIT, UNCERTAIN" in result.stdout
    assert "identity_anchors:" in result.stdout
    assert "alternating_legs:" in result.stdout
    assert "Editing rules" in result.stdout
    assert "Audit workflow" in result.stdout


def test_brief_requires_a_profiled_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)

    result = run_cli(capsys, ["brief", str(bundle), "--json"])

    assert result.returncode == 2
    assert "--polish-profile" in result.stderr
    assert not result.stdout


def test_check_json_includes_silhouette_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    result = run_cli(capsys, ["check", str(bundle), "--json"], env=bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["silhouette_artifacts"]["strip"]["relative_path"] == "reports/silhouette-strip.png"
    assert data["silhouette_artifacts"]["gif"]["relative_path"] == "reports/silhouette.gif"
    strip_path = bundle / data["silhouette_artifacts"]["strip"]["relative_path"]
    gif_path = bundle / data["silhouette_artifacts"]["gif"]["relative_path"]
    assert data["silhouette_artifacts"]["strip"]["sha256"] == sha256_file(strip_path)
    assert data["silhouette_artifacts"]["gif"]["sha256"] == sha256_file(gif_path)


def test_check_json_reports_provider_post_edit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    swing_strip = swing_provider_strip(tmp_path)
    attempt = pb.prepare(swing_strip, "swing", tmp_path, polish_profile="dwarf-miner")
    pb.init_bundle(attempt, bundle)

    result = _run_check_cli(capsys, bundle, swing_strip)

    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    post_edit = data["provider_post_edit"]
    assert post_edit is not None
    assert post_edit["magenta_wipe"]["outcome"] == "PASS"
    assert post_edit["outcome"] == "FAIL"
    assert post_edit["reason_code"] == "edit_source_continuity_fail"
    assert post_edit["continuity"]["reason_code"] == "edit_source_continuity_fail"


def test_check_human_report_names_provider_post_edit_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = tmp_path / "bundle"
    swing_strip = swing_provider_strip(tmp_path)
    attempt = pb.prepare(swing_strip, "swing", tmp_path, polish_profile="dwarf-miner")
    pb.init_bundle(attempt, bundle)

    with patch(
        "pipeline.final_polish.load_provider_frames",
        side_effect=lambda path, layout: load_provider_frames(swing_strip, layout),
    ):
        result = run_cli(capsys, ["check", str(bundle)], env=bundle_store_env(bundle))

    assert result.returncode == 1, result.stderr
    assert "Post-edit   FAIL (edit_source_continuity_fail)" in result.stdout


def test_check_human_report_marks_provider_post_edit_not_applicable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _idle_bundle(tmp_path)

    result = run_cli(capsys, ["check", str(bundle)], env=bundle_store_env(bundle))

    assert result.returncode == 0, result.stderr
    assert "Post-edit   (n/a)" in result.stdout


def test_check_json_provider_post_edit_is_null_when_not_evaluated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _idle_bundle(tmp_path)

    result = run_cli(capsys, ["check", str(bundle), "--json"], env=bundle_store_env(bundle))

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "provider_post_edit" in data
    assert data["provider_post_edit"] is None


def test_check_fail_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = first_opaque_xy(polished)
    set_opaque_rgb(polished, x, y, (3, 99, 200))

    result = run_cli(capsys, ["check", str(bundle)], env=bundle_store_env(bundle))
    assert result.returncode == 1
    assert "FAIL" in result.stdout


def test_check_fail_json_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = first_opaque_xy(polished)
    set_opaque_rgb(polished, x, y, (3, 99, 200))

    result = run_cli(capsys, ["check", str(bundle), "--json"], env=bundle_store_env(bundle))
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["outcome"] == "FAIL"
    assert data["structural"]["pass"] is False


def test_check_review_exit_3(tmp_path: Path, capsys) -> None:
    bundle = _idle_bundle(tmp_path)
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
    with patch("pipeline.final_polish_cli.check_bundle") as mock_check:
        from pipeline.final_polish import FinalPolishCheckResult, StructuralCheckResult, VisibleCellDelta

        mock_check.return_value = FinalPolishCheckResult(
            outcome="REVIEW",
            provider_outcome="REVIEW",
            identity_lock=None,
            structural=StructuralCheckResult(pass_=True, outcome="PASS", violations=()),
            delta=VisibleCellDelta(edits=(), per_frame_counts=(0, 0, 0, 0), total_edits=0),
            coherence=review.coherence,
            manifest_sha256="abc",
            provider_sha256="def",
            draft_hashes=("d0", "d1", "d2", "d3"),
            polished_hashes=("p0", "p1", "p2", "p3"),
            fingerprint="fp",
        )
        from pipeline.final_polish_cli import main

        code = main(["check", str(bundle)])
    assert code == 3
    assert "Overall  REVIEW" in capsys.readouterr().out


def test_check_review_json_exit_3(tmp_path: Path, capsys) -> None:
    bundle = _idle_bundle(tmp_path)
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
    with patch("pipeline.final_polish_cli.check_bundle") as mock_check:
        from pipeline.final_polish import FinalPolishCheckResult, StructuralCheckResult, VisibleCellDelta

        mock_check.return_value = FinalPolishCheckResult(
            outcome="REVIEW",
            provider_outcome="REVIEW",
            identity_lock=None,
            structural=StructuralCheckResult(pass_=True, outcome="PASS", violations=()),
            delta=VisibleCellDelta(edits=(), per_frame_counts=(0, 0, 0, 0), total_edits=0),
            coherence=review.coherence,
            manifest_sha256="abc",
            provider_sha256="def",
            draft_hashes=("d0", "d1", "d2", "d3"),
            polished_hashes=("p0", "p1", "p2", "p3"),
            fingerprint="fp",
        )
        from pipeline.final_polish_cli import main

        code = main(["check", str(bundle), "--json"])
    assert code == 3
    data = json.loads(capsys.readouterr().out)
    assert data["outcome"] == "REVIEW"


def test_check_invalid_bundle_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    (bundle / "manifest.json").unlink()
    result = run_cli(capsys, ["check", str(bundle)], env=bundle_store_env(bundle))
    assert result.returncode == 2
    assert result.stderr.strip()
    assert not result.stdout.strip()


def test_v2_walk_check_json_binds_sequential_attempt_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(WALK_STRIP, "walk", tmp_path, polish_profile="dwarf-miner")
    pb.init_bundle(attempt, bundle)
    manifest = json.loads((bundle / "manifest.json").read_text())
    ledger_path = bundle / "provider" / "attempts.json"
    assert manifest["attempt_ledger"]["sha256"] == sha256_file(ledger_path)
    ledger = json.loads(ledger_path.read_text())
    selected = [row for row in ledger["attempts"] if row["selected"]]
    assert len(selected) == 1
    assert selected[0] is ledger["attempts"][-1]
    provenance = json.loads((bundle / "provider" / "source.source.json").read_text())
    assert selected[0]["attempt_id"] == provenance["attempt_id"]
    assert selected[0]["prompt_sha256"] == provenance["prompt_sha256"]
    assert selected[0]["raw_sha256"] == provenance["raw_sha256"]

    result = _run_check_cli(capsys, bundle, WALK_STRIP)
    assert result.returncode == 1, result.stderr
    data = json.loads(result.stdout)
    assert data["identity_lock"] is not None
    assert data["identity_lock"]["motion_class"] == "walk"
    assert data["identity_lock"]["outcome"] == "FAIL"
    identity_lock = data["identity_lock"]
    assert "first_failure" in identity_lock
    assert len(identity_lock["per_frame"]) == 4
    for frame in identity_lock["per_frame"]:
        assert "upper_body" in frame["selected_offsets"]
        assert frame["check_results"]["upper_body"]["comparison"] == "registered-structure"
        assert {
            "occupancy_difference",
            "palette_role_distance",
            "outcome",
        } <= frame["check_results"]["upper_body"].keys()
        assert {"lamp", "eye", "buckle"} <= frame["landmark_results"].keys()
        assert "first_failure" in frame
    assert data["outcome"] == "FAIL"


def test_human_report_includes_required_fields(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    result = run_cli(capsys, ["check", str(bundle)], env=bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    assert "Bundle" in stdout
    assert "Provider" in stdout
    assert "Identity" in stdout
    assert "Motion" in stdout
    assert "Structural" in stdout
    assert "Edits" in stdout
    assert "palette_drift_pass" in stdout
    assert "Overall  PASS" in stdout


def test_json_mode_emits_single_object_with_complete_payload(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    result = run_cli(capsys, ["check", str(bundle), "--json"], env=bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["outcome"] == "PASS"
    assert "structural" in data
    assert "visible_cell_delta" in data
    assert "coherence" in data
    assert "manifest_sha256" in data
    assert "provider_sha256" in data
    assert "draft_hashes" in data
    assert "polished_hashes" in data
    assert "fingerprint" in data
    assert "gate_outcomes" in data


def test_json_invalid_invocation_writes_stderr_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = run_cli(capsys, ["check", str(tmp_path / "missing-bundle")])
    assert result.returncode == 2
    assert result.stderr.strip()
    assert not result.stdout.strip()


def test_check_is_read_only_human_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    before = _bundle_fingerprint(bundle)

    human = run_cli(capsys, ["check", str(bundle)], env=bundle_store_env(bundle))
    assert human.returncode == 0, human.stderr
    assert _bundle_fingerprint(bundle) == before

    json_result = run_cli(capsys, ["check", str(bundle), "--json"], env=bundle_store_env(bundle))
    assert json_result.returncode == 0, json_result.stderr
    assert _bundle_fingerprint(bundle) == before


def test_direct_png_edit_accepted_without_editor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _idle_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = first_opaque_xy(polished)

    draft_union: set[tuple[int, int, int]] = set()
    for index in range(FRAME_COUNT):
        with Image.open(bundle / "draft" / f"frame-{index}.png") as image:
            rgba = image.convert("RGBA")
            pixels = rgba.load()
            assert pixels is not None
            for row_y in range(LOGICAL_SIZE[1]):
                for col_x in range(LOGICAL_SIZE[0]):
                    r, g, b, a = pixels[col_x, row_y]
                    if a == 255:
                        draft_union.add((r, g, b))

    palette_color = next(iter(draft_union))
    set_opaque_rgb(polished, x, y, palette_color)

    result = run_cli(capsys, ["check", str(bundle)], env=bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
