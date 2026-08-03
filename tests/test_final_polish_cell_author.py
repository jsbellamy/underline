"""Cell-author generation mode lifecycle (issue #234)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from pipeline import asset_acquire as aa
from pipeline.cell_delta import CellDeltaError
from pipeline.cell_raster import read_cells, write_cells
from pipeline.final_polish import (
    BUNDLE_SCHEMA,
    CELL_AUTHOR_GENERATION_MODE,
    CELL_AUTHOR_PROVENANCE_SCHEMA,
    BundleExistsError,
    InitializationRejectedError,
    InvalidBundleError,
    PROVENANCE_SCHEMA,
    check_bundle,
    finalize_bundle,
    initialize_cell_authored_bundle,
)
from pipeline.final_polish_cli import main as final_polish_cli_main
from pipeline.gate_evidence import sha256_file
from tests.support import polish_bundle as pb
from tests.support.final_polish_testkit import (
    FRAME_COUNT,
    LOGICAL_SIZE,
    PASS_STRIP,
    ROOT,
    WALK_STRIP,
    run_cli,
    set_opaque_rgb,
    write_animation_provenance,
)
from tests.support.polish_bundle import acquisition_store_env
from tests.support.polish_review_fixture import write_passing_reviews
from pipeline.final_polish import MOTION_POSE_PLAN_SCHEMA


def _store_env(prepared: pb.PreparedCellAuthor) -> dict[str, str]:
    store_root = prepared.base_bundle.parent / "acquisition-controls"
    return acquisition_store_env(store_root)


def _init_cell(tmp_path: Path, bundle: Path | None = None) -> tuple[pb.PreparedCellAuthor, Path]:
    prepared = pb.prepare_cell_author("idle", tmp_path)
    out = bundle or (tmp_path / "cell-bundle")
    pb.init_cell_bundle(prepared, out)
    return prepared, out


def test_cell_author_provenance_schema_and_field_set(tmp_path: Path) -> None:
    prepared, bundle = _init_cell(tmp_path)
    provenance = json.loads((bundle / "authoring" / "provenance.json").read_text())

    assert provenance["schema"] == CELL_AUTHOR_PROVENANCE_SCHEMA
    assert provenance["generation_mode"] == CELL_AUTHOR_GENERATION_MODE
    assert provenance["specification_id"] == prepared.specification_id
    assert provenance["motion_class"] == "idle"
    assert provenance["base_specification_id"] == json.loads(
        (prepared.base_bundle / "provider" / "source.source.json").read_text()
    )["specification_id"]
    assert provenance["base_frames_sha256"] == json.loads(
        prepared.cell_delta_ledger.read_text()
    )["base_frames_sha256"]
    assert provenance["base_frame_mapping"] == [0, 0, 0, 0]
    assert provenance["pose_plan"]["sha256"] == sha256_file(prepared.pose_plan)
    assert provenance["cell_delta_ledger"]["sha256"] == sha256_file(prepared.cell_delta_ledger)
    assert provenance["authoring_agent"] == "pytest"
    assert provenance["authoring_session_id"] == "pytest-session-001"
    assert isinstance(provenance["repository_commit"], str) and len(provenance["repository_commit"]) == 40

    forbidden = {
        "attempt_id",
        "raw_path",
        "raw_sha256",
        "edit_source_sha256",
        "dimensions",
        "model",
        "generator",
        "prompt_text",
        "prompt_sha256",
    }
    assert forbidden.isdisjoint(provenance.keys())


def test_animation_provenance_rejects_cell_author_generation_mode(tmp_path: Path) -> None:
    provider = PASS_STRIP
    provenance_path = tmp_path / "bad.source.json"
    write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        generation_mode=CELL_AUTHOR_GENERATION_MODE,
    )
    record = json.loads(provenance_path.read_text())
    assert record["schema"] == PROVENANCE_SCHEMA
    store_root = tmp_path / "acquisition-controls"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        with pytest.raises(aa.AssetAcquisitionError) as exc:
            aa.record_asset_attempt(
                provider,
                "test/idle",
                motion_class="idle",
                generation_mode=CELL_AUTHOR_GENERATION_MODE,
                acquiring_agent="pytest",
                prompt_text="nope",
                repo_root=tmp_path,
            )
    assert exc.value.reason_code == "provider_attempt_claims_cell_author"


def test_init_cell_creates_providerless_v2_bundle(tmp_path: Path) -> None:
    prepared, bundle = _init_cell(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text())

    assert manifest["schema"] == BUNDLE_SCHEMA
    assert manifest["generation_mode"] == CELL_AUTHOR_GENERATION_MODE
    assert "provider" not in manifest
    assert "provenance" not in manifest
    assert "attempt_ledger" not in manifest
    assert not (bundle / "provider").exists()

    authoring = manifest["cell_authoring"]
    assert authoring["base_specification_id"] == json.loads(
        prepared.cell_delta_ledger.read_text()
    )["base_specification_id"]
    assert authoring["base_frame_mapping"] == [0, 0, 0, 0]
    assert authoring["pose_plan"]["sha256"] == sha256_file(prepared.pose_plan)
    assert authoring["cell_delta_ledger"]["sha256"] == sha256_file(prepared.cell_delta_ledger)

    for index in range(4):
        draft = bundle / "draft" / f"frame-{index}.png"
        polished = bundle / "polished" / f"frame-{index}.png"
        assert draft.is_file() and polished.is_file()
        assert sha256_file(draft) == sha256_file(polished)


def test_init_rejects_wrong_base_digest(tmp_path: Path) -> None:
    prepared = pb.prepare_cell_author("idle", tmp_path)
    ledger = json.loads(prepared.cell_delta_ledger.read_text())
    ledger["base_frames_sha256"][0] = "0" * 64
    bad_ledger = tmp_path / "bad-ledger.json"
    bad_ledger.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")

    with patch.dict("os.environ", _store_env(prepared)):
        with pytest.raises(InitializationRejectedError) as exc:
            initialize_cell_authored_bundle(
                prepared.authored_frames_dir,
                prepared.motion_class,
                tmp_path / "bundle",
                specification_id=prepared.specification_id,
                base_bundle_root=prepared.base_bundle,
                cell_delta_ledger=bad_ledger,
                pose_plan=prepared.pose_plan,
                polish_profile=prepared.polish_profile,
                identity_reference=prepared.identity_reference,
                authoring_agent=prepared.authoring_agent,
                authoring_session_id=prepared.authoring_session_id,
            )
    assert exc.value.reason_code == "base_frame_hash_mismatch"


def test_init_rejects_unattested_provider_base(tmp_path: Path) -> None:
    prepared = pb.prepare_cell_author("idle", tmp_path)
    shutil.rmtree(prepared.base_bundle.parent / "acquisition-controls")
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("UNDERLINE_ACQUISITION_CONTROLS_ROOT", None)
        with pytest.raises(InitializationRejectedError) as exc:
            initialize_cell_authored_bundle(
                prepared.authored_frames_dir,
                prepared.motion_class,
                tmp_path / "bundle",
                specification_id=prepared.specification_id,
                base_bundle_root=prepared.base_bundle,
                cell_delta_ledger=prepared.cell_delta_ledger,
                pose_plan=prepared.pose_plan,
                polish_profile=prepared.polish_profile,
                identity_reference=prepared.identity_reference,
                authoring_agent=prepared.authoring_agent,
                authoring_session_id=prepared.authoring_session_id,
            )
    assert exc.value.reason_code == "unattested_base_bundle"


def test_init_rejects_cell_authored_base(tmp_path: Path) -> None:
    prepared, first = _init_cell(tmp_path)
    with patch.dict("os.environ", _store_env(prepared)):
        with pytest.raises(InitializationRejectedError) as exc:
            initialize_cell_authored_bundle(
                prepared.authored_frames_dir,
                prepared.motion_class,
                tmp_path / "nested",
                specification_id="test/idle-nested",
                base_bundle_root=first,
                cell_delta_ledger=prepared.cell_delta_ledger,
                pose_plan=prepared.pose_plan,
                polish_profile=prepared.polish_profile,
                identity_reference=prepared.identity_reference,
                authoring_agent=prepared.authoring_agent,
                authoring_session_id="nested-session",
            )
    assert exc.value.reason_code in {"cell_author_base_forbidden", "unattested_base_bundle"}


def test_init_rejects_replay_mismatch(tmp_path: Path) -> None:
    prepared = pb.prepare_cell_author(
        "idle",
        tmp_path,
        mutate_frame=(0, 5, 11, (140, 96, 64)),
    )
    tampered_dir = tmp_path / "tampered-frames"
    tampered_dir.mkdir()
    for index in range(4):
        shutil.copy2(
            prepared.authored_frames_dir / f"frame-{index}.png",
            tampered_dir / f"frame-{index}.png",
        )
    cells = read_cells(tampered_dir / "frame-0.png")
    cells[11][5] = (1, 2, 3)
    write_cells(tampered_dir / "frame-0.png", cells)

    with patch.dict("os.environ", _store_env(prepared)):
        with pytest.raises(InitializationRejectedError) as exc:
            initialize_cell_authored_bundle(
                tampered_dir,
                prepared.motion_class,
                tmp_path / "bundle",
                specification_id=prepared.specification_id,
                base_bundle_root=prepared.base_bundle,
                cell_delta_ledger=prepared.cell_delta_ledger,
                pose_plan=prepared.pose_plan,
                polish_profile=prepared.polish_profile,
                identity_reference=prepared.identity_reference,
                authoring_agent=prepared.authoring_agent,
                authoring_session_id=prepared.authoring_session_id,
            )
    assert exc.value.reason_code == "cell_delta_replay_mismatch"


def test_check_rejects_replay_mismatch(tmp_path: Path) -> None:
    prepared, bundle = _init_cell(tmp_path)
    cells = read_cells(bundle / "draft" / "frame-0.png")
    cells[11][5] = (1, 2, 3)
    write_cells(bundle / "draft" / "frame-0.png", cells)

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "cell_delta_replay_mismatch"


def test_manifest_mode_tamper_raises_generation_mode_changed(tmp_path: Path) -> None:
    _, bundle = _init_cell(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["generation_mode"] = "text-to-image"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "generation_mode_changed"


def test_provider_field_in_cell_bundle_raises_generation_mode_changed(tmp_path: Path) -> None:
    _, bundle = _init_cell(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["provider"] = {
        "original_filename": "fake.png",
        "relative_path": "provider/source.png",
        "sha256": "0" * 64,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "generation_mode_changed"


def test_provider_bundle_with_cell_authoring_rejects(tmp_path: Path) -> None:
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    bundle = tmp_path / "provider-bundle"
    pb.init_bundle(attempt, bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["cell_authoring"] = {"base_specification_id": "test/idle"}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        check_bundle(bundle)
    assert exc.value.reason_code == "generation_mode_changed"


def test_check_summary_json_exposes_cell_author_attestation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared, bundle = _init_cell(tmp_path)
    result = run_cli(capsys, ["check", str(bundle), "--summary-json"])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["attestation"]["state"] == CELL_AUTHOR_GENERATION_MODE
    assert payload["generation_mode"] == CELL_AUTHOR_GENERATION_MODE
    assert payload["base_specification_id"] == json.loads(
        prepared.cell_delta_ledger.read_text()
    )["base_specification_id"]
    assert payload["base_frames_sha256"] == json.loads(
        prepared.cell_delta_ledger.read_text()
    )["base_frames_sha256"]
    assert payload["base_frame_mapping"] == [0, 0, 0, 0]
    assert payload["cell_delta_ledger_sha256"] == sha256_file(prepared.cell_delta_ledger)
    assert "attempt_id" not in payload.get("attestation", {})
    assert "store_path" not in payload.get("attestation", {})


def test_finalize_report_exposes_cell_author_bindings(tmp_path: Path) -> None:
    prepared, bundle = _init_cell(tmp_path)
    write_passing_reviews(bundle)
    report_path = finalize_bundle(bundle)
    report = json.loads(report_path.read_text())
    ledger = json.loads(prepared.cell_delta_ledger.read_text())
    assert report["attestation"]["state"] == CELL_AUTHOR_GENERATION_MODE
    assert report["generation_mode"] == CELL_AUTHOR_GENERATION_MODE
    assert report["base_specification_id"] == ledger["base_specification_id"]
    assert report["attestation"]["base_frames_sha256"] == ledger["base_frames_sha256"]
    assert report["attestation"]["base_frame_mapping"] == ledger["base_frame_mapping"]
    assert report["attestation"]["cell_delta_ledger_sha256"] == sha256_file(
        prepared.cell_delta_ledger
    )
    assert "provider" not in report


def test_cell_author_identity_lock_failure_is_fail(tmp_path: Path) -> None:
    prepared, bundle = _init_cell_from_walk(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    set_opaque_rgb(polished, 8, 10, (250, 1, 2))
    result = check_bundle(bundle)
    assert result.identity_lock is not None
    assert result.identity_lock.outcome == "FAIL"
    assert result.outcome == "FAIL"


def test_cell_author_check_runs_motion_class_gates(tmp_path: Path) -> None:
    _, bundle = _init_cell(tmp_path)
    result = check_bundle(bundle)
    assert "gate_outcomes" in result.coherence
    assert len(result.coherence["gate_outcomes"]) > 0
    assert result.coherence["outcome"] in {"PASS", "REVIEW", "FAIL"}


def _init_cell_from_walk(tmp_path: Path) -> tuple[pb.PreparedCellAuthor, Path]:
    prepared = pb.prepare_cell_author("walk", tmp_path, polish_profile="dwarf-miner")
    bundle = tmp_path / "walk-cell-bundle"
    pb.init_cell_bundle(prepared, bundle)
    return prepared, bundle


REAL_DWARF_IDLE_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "idle"


def _prepare_swing_from_real_idle_bundle(tmp_path: Path) -> pb.PreparedCellAuthor:
    """C4: cell-author a swing Bundle from the real checked-in dwarf idle Bundle.

    The idle Bundle's release Frames are 16x24; swing's canvas is 24x24 at
    canonical_origin (1, 0) — this only succeeds because `initialize_cell_authored_bundle`
    embeds the base onto the target class canvas before validating the ledger (issue #290).
    """
    return pb.prepare_cell_author(
        "swing",
        tmp_path,
        polish_profile="dwarf-miner",
        base_bundle_root=REAL_DWARF_IDLE_BUNDLE,
    )


def _init_cell_from_real_idle_to_swing(tmp_path: Path) -> tuple[pb.PreparedCellAuthor, Path]:
    prepared = _prepare_swing_from_real_idle_bundle(tmp_path)
    bundle = tmp_path / "swing-cell-bundle"
    pb.init_cell_bundle(prepared, bundle)
    return prepared, bundle


def test_cell_author_swing_from_real_idle_bundle_reaches_providerless_bundle(
    tmp_path: Path,
) -> None:
    prepared, bundle = _init_cell_from_real_idle_to_swing(tmp_path)
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA
    assert manifest["generation_mode"] == CELL_AUTHOR_GENERATION_MODE
    assert manifest["motion_class"] == "swing"
    assert manifest["layout"]["frame_w"] == 24
    assert manifest["layout"]["frame_h"] == 24
    assert not (bundle / "provider").exists()

    provenance = json.loads((bundle / "authoring" / "provenance.json").read_text())
    assert provenance["motion_class"] == "swing"
    assert provenance["base_specification_id"] == "first-room/dwarf/idle"


def test_cell_author_swing_authoring_base_bytes_match_ledger_digests(tmp_path: Path) -> None:
    prepared, bundle = _init_cell_from_real_idle_to_swing(tmp_path)
    ledger = json.loads(prepared.cell_delta_ledger.read_text())
    for index, expected_digest in enumerate(ledger["base_frames_sha256"]):
        base_path = bundle / "authoring" / "base" / f"frame-{index}.png"
        assert read_cells(base_path, size=(24, 24)) is not None
        assert sha256_file(base_path) == expected_digest


def test_cell_author_swing_rejects_unembedded_base_hash(tmp_path: Path) -> None:
    prepared = _prepare_swing_from_real_idle_bundle(tmp_path)
    ledger = json.loads(prepared.cell_delta_ledger.read_text())
    ledger["base_frames_sha256"][0] = "f" * 64
    bad_ledger = tmp_path / "bad-ledger.json"
    bad_ledger.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InitializationRejectedError) as exc:
        initialize_cell_authored_bundle(
            prepared.authored_frames_dir,
            "swing",
            tmp_path / "swing-cell-bundle-rejected",
            specification_id=prepared.specification_id,
            base_bundle_root=prepared.base_bundle,
            cell_delta_ledger=bad_ledger,
            pose_plan=prepared.pose_plan,
            polish_profile=prepared.polish_profile,
            identity_reference=prepared.identity_reference,
            authoring_agent=prepared.authoring_agent,
            authoring_session_id=prepared.authoring_session_id,
        )
    assert exc.value.reason_code == "base_frame_hash_mismatch"


def test_init_cell_cli_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared = pb.prepare_cell_author("idle", tmp_path)
    bundle = tmp_path / "cli-bundle"
    result = run_cli(
        capsys,
        pb.init_cell_argv(prepared, bundle),
        env=_store_env(prepared),
    )
    assert result.returncode == 0, result.stderr
    assert bundle.is_dir()


def test_init_cell_cli_rejects_provider_args(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared = pb.prepare_cell_author("idle", tmp_path)
    bundle = tmp_path / "cli-bundle"
    argv = pb.init_cell_argv(prepared, bundle) + [
        "--provenance",
        str(prepared.pose_plan),
    ]
    with pytest.raises(SystemExit) as excinfo:
        with patch.dict("os.environ", _store_env(prepared)):
            final_polish_cli_main(argv)
    assert excinfo.value.code == 2


def test_init_cell_cli_rejection_leaves_no_partial_bundle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared = pb.prepare_cell_author("idle", tmp_path)
    ledger = json.loads(prepared.cell_delta_ledger.read_text())
    ledger["base_frames_sha256"][0] = "f" * 64
    bad_ledger = tmp_path / "bad-ledger.json"
    bad_ledger.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    bundle = tmp_path / "cli-bundle"
    argv = pb.init_cell_argv(prepared, bundle)
    argv[argv.index(str(prepared.cell_delta_ledger))] = str(bad_ledger)
    result = run_cli(capsys, argv, env=_store_env(prepared))
    assert result.returncode == 2, result.stderr
    assert not bundle.exists()


def test_init_cell_cli_rejection_emits_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared = pb.prepare_cell_author("idle", tmp_path)
    bundle = tmp_path / "cli-bundle"
    pb.init_cell_bundle(prepared, bundle)
    result = run_cli(
        capsys,
        pb.init_cell_argv(prepared, bundle, json_mode=True),
        env=_store_env(prepared),
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["reason_code"] == "bundle_exists"


def test_dwarf_walk_provider_init_unchanged(tmp_path: Path) -> None:
    attempt = pb.prepare(pb.WALK_STRIP, "walk", tmp_path, polish_profile="dwarf-miner")
    bundle = tmp_path / "walk-bundle"
    with patch.dict("os.environ", attempt.env):
        pb.init_bundle(attempt, bundle)
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest.get("generation_mode") != CELL_AUTHOR_GENERATION_MODE
    assert "provider" in manifest


def test_pose_plan_schema_bound(tmp_path: Path) -> None:
    _, bundle = _init_cell(tmp_path)
    pose_plan = json.loads((bundle / "authoring" / "pose-plan.json").read_text())
    assert pose_plan["schema"] == MOTION_POSE_PLAN_SCHEMA
