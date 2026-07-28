"""Subprocess proof for pipeline.final_polish_cli (issues #96 and #101)."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline.final_polish import initialize_bundle
from pipeline.final_polish_cli import main
from pipeline.gate_evidence import sha256_bytes, sha256_file
from pipeline.strip import DEFAULT_LAYOUT, IngestResult, StripLayout, ingest_strip_provider

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "prototype" / "strip-coherence" / "inbox"
PASS_STRIP = INBOX / "01-miner-idle.png"
FAIL_STRIP = INBOX / "08-NEG-identity-drift.png"
WALK_STRIP = INBOX / "05-miner-walk.png"
LANTERN_STRIP = INBOX / "14-lantern-flicker.png"
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
IDLE_SEED_STRIP = ROOT / "assets" / "first-room" / "dwarf" / "idle" / "provider" / "source.png"
CANONICAL_IDENTITY_SHA = "db68353f559053abc4d77e8916d1db8a242f4f50eb4a1ef0d4b1f65c4bf650c9"
LOGICAL_SIZE = (DEFAULT_LAYOUT.frame_w, DEFAULT_LAYOUT.frame_h)
FRAME_COUNT = DEFAULT_LAYOUT.frame_count


def _corpus_layout() -> StripLayout:
    return StripLayout(
        frame_w=DEFAULT_LAYOUT.frame_w,
        frame_h=DEFAULT_LAYOUT.frame_h,
        frame_count=DEFAULT_LAYOUT.frame_count,
        gutter=DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _run_module(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, "-m", "pipeline.final_polish_cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def _run_npm(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["npm", "run", "strip:polish", "--", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _provider_dimensions(provider_path: Path) -> list[int]:
    with Image.open(provider_path) as image:
        return [image.width, image.height]


def _write_animation_provenance(
    provider_path: Path,
    provenance_path: Path,
    *,
    motion_class: str,
    generation_mode: str = "text-to-image",
    reference_image_sha256: list[str] | None = None,
    edit_source_sha256: str | None = None,
) -> None:
    if reference_image_sha256 is None:
        reference_image_sha256 = []
    prompt_text = "underline cli test provenance prompt"
    provenance_path.write_text(
        json.dumps(
            {
                "schema": "animation-strip-provenance/0",
                "specification_id": f"test/{motion_class}",
                "attempt_id": "cli-test--001",
                "predecessor_attempt_id": None,
                "generator": "cursor-image-gen",
                "model": "cursor-image-gen",
                "prompt_text": prompt_text,
                "prompt_sha256": sha256_bytes(prompt_text.encode("utf-8")),
                "generation_mode": generation_mode,
                "reference_image_sha256": reference_image_sha256,
                "edit_source_sha256": edit_source_sha256,
                "generated_at": "2026-07-27T22:00:00+00:00",
                "acquiring_agent": "pytest",
                "repository_commit": "0000000000000000000000000000000000000000",
                "raw_path": str(provider_path),
                "raw_sha256": sha256_file(provider_path),
                "media_type": "image/png",
                "dimensions": _provider_dimensions(provider_path),
                "motion_class": motion_class,
                "master_palette_id": "first-room",
                "item_geometry": {
                    "frame_w": DEFAULT_LAYOUT.frame_w,
                    "frame_h": DEFAULT_LAYOUT.frame_h,
                    "frame_count": DEFAULT_LAYOUT.frame_count,
                    "gutter": DEFAULT_LAYOUT.gutter,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _provenance_args(
    tmp_path: Path,
    provider_path: Path,
    motion_class: str,
    *,
    polish_profile: str | None = None,
) -> list[str]:
    provenance_path = tmp_path / f"{provider_path.stem}.source.json"
    kwargs: dict[str, object] = {"motion_class": motion_class}
    identity_args: list[str] = []
    if polish_profile == "dwarf-miner" and motion_class in {"walk", "swing"}:
        kwargs.update(
            {
                "generation_mode": "image-edit",
                "reference_image_sha256": [CANONICAL_IDENTITY_SHA],
                "edit_source_sha256": sha256_file(IDLE_SEED_STRIP),
            }
        )
        identity_args = [
            "--identity-reference",
            str(IDENTITY_PNG),
            "--edit-source",
            str(IDLE_SEED_STRIP),
        ]
    _write_animation_provenance(provider_path, provenance_path, **kwargs)
    return ["--provenance", str(provenance_path), *identity_args]


def _init_cli_args(
    tmp_path: Path,
    provider_path: Path,
    motion_class: str,
    bundle: Path,
    *,
    polish_profile: str | None = None,
    json_mode: bool = False,
) -> list[str]:
    args = [
        "init",
        str(provider_path),
        "--motion-class",
        motion_class,
        "--out",
        str(bundle),
        *_provenance_args(
            tmp_path,
            provider_path,
            motion_class,
            polish_profile=polish_profile,
        ),
    ]
    if polish_profile is not None:
        args.extend(["--polish-profile", polish_profile])
    if json_mode:
        args.append("--json")
    return args


def _library_init_bundle(
    provider_path: Path,
    motion_class: str,
    bundle: Path,
    tmp_path: Path,
    *,
    polish_profile: str | None = None,
) -> None:
    provenance_args = _provenance_args(
        tmp_path,
        provider_path,
        motion_class,
        polish_profile=polish_profile,
    )
    provenance_path = Path(provenance_args[1])
    identity = Path(provenance_args[3]) if len(provenance_args) > 3 else None
    edit = Path(provenance_args[5]) if len(provenance_args) > 5 else None
    initialize_bundle(
        provider_path,
        motion_class,
        bundle,
        provenance_sidecar=provenance_path,
        polish_profile=polish_profile,
        identity_reference=identity,
        edit_source=edit,
    )


def _init_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    provenance_path = tmp_path / "pass.source.json"
    _write_animation_provenance(PASS_STRIP, provenance_path, motion_class="idle")
    initialize_bundle(
        PASS_STRIP,
        "idle",
        bundle,
        provenance_sidecar=provenance_path,
    )
    return bundle


def _bundle_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _first_opaque_xy(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        for y in range(LOGICAL_SIZE[1]):
            for x in range(LOGICAL_SIZE[0]):
                if pixels[x, y][3] == 255:
                    return x, y
    raise AssertionError(f"no opaque cell in {path}")


def _set_opaque_rgb(path: Path, x: int, y: int, rgb: tuple[int, int, int]) -> None:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        pixels[x, y] = (*rgb, 255)
        rgba.save(path)


def test_npm_entrypoint_runs_init_check_finalize(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    init = _run_npm(_init_cli_args(tmp_path, PASS_STRIP, "idle", bundle))
    assert init.returncode == 0, init.stderr
    assert bundle.is_dir()

    check = _run_npm(["check", str(bundle)])
    assert check.returncode == 0, check.stderr

    finalize = _run_npm(["finalize", str(bundle)])
    assert finalize.returncode == 0, finalize.stderr
    assert list((bundle / "release").glob("*.png"))


def test_init_creates_bundle_via_module_entrypoint(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    result = _run_module(_init_cli_args(tmp_path, PASS_STRIP, "idle", bundle))
    assert result.returncode == 0, result.stderr
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "polished" / "frame-0.png").is_file()


def test_init_fail_strip_exit_1(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    result = _run_module(_init_cli_args(tmp_path, FAIL_STRIP, "idle", bundle))
    assert result.returncode == 1
    assert not bundle.exists()
    assert "FAIL" in result.stdout
    assert "palette_drift_pass" in result.stdout or "silhouette" in result.stdout


def test_init_fail_strip_json_exit_1(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    result = _run_module(_init_cli_args(tmp_path, FAIL_STRIP, "idle", bundle, json_mode=True))
    assert result.returncode == 1
    assert not bundle.exists()
    data = json.loads(result.stdout)
    assert data["outcome"] == "FAIL"
    assert data["pass"] is False
    assert "coherence" in data
    assert "gate_outcomes" in data


def test_init_pass_json_exit_0(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    result = _run_module(_init_cli_args(tmp_path, PASS_STRIP, "idle", bundle, json_mode=True))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["outcome"] == "PASS"
    assert "fingerprint" in data
    assert "structural" in data


def test_init_with_profile_binds_profile_in_json_result(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    result = _run_module(
        _init_cli_args(
            tmp_path,
            PASS_STRIP,
            "idle",
            bundle,
            polish_profile="miner",
            json_mode=True,
        )
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["polish_profile"] == {
        "id": "miner",
        "sha256": sha256_file(bundle / "profile.json"),
    }


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class"),
    [
        ("dwarf-miner", PASS_STRIP, "idle"),
        ("lantern", LANTERN_STRIP, "emissive"),
    ],
)
def test_init_with_production_profile_binds_profile_in_json_result(
    tmp_path: Path,
    profile_id: str,
    strip: Path,
    motion_class: str,
) -> None:
    bundle = tmp_path / "bundle"
    result = _run_module(
        _init_cli_args(
            tmp_path,
            strip,
            motion_class,
            bundle,
            polish_profile=profile_id,
            json_mode=True,
        )
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["polish_profile"] == {
        "id": profile_id,
        "sha256": sha256_file(bundle / "profile.json"),
    }


@pytest.mark.parametrize(
    ("profile_id", "strip", "motion_class", "motion_ids"),
    [
        ("dwarf-miner", WALK_STRIP, "walk", ["alternating_legs", "stable_torso"]),
        ("lantern", LANTERN_STRIP, "emissive", ["emission_inside_lamp", "no_terrain_halo"]),
    ],
)
def test_brief_json_selects_production_profile_motion_questions(
    tmp_path: Path,
    profile_id: str,
    strip: Path,
    motion_class: str,
    motion_ids: list[str],
) -> None:
    bundle = tmp_path / "bundle"
    provenance_path = _provenance_args(tmp_path, strip, motion_class, polish_profile=profile_id)
    provenance = Path(provenance_path[1])
    identity = Path(provenance_path[3]) if len(provenance_path) > 3 else None
    edit = Path(provenance_path[5]) if len(provenance_path) > 5 else None
    initialize_bundle(
        strip,
        motion_class,
        bundle,
        provenance_sidecar=provenance,
        polish_profile=profile_id,
        identity_reference=identity,
        edit_source=edit,
    )
    before = _bundle_fingerprint(bundle)

    result = _run_module(["brief", str(bundle), "--json"])

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["profile"]["id"] == profile_id
    assert data["motion_class"] == motion_class
    assert [row["id"] for row in data["motion_questions"]] == motion_ids
    assert _bundle_fingerprint(bundle) == before


def test_init_unknown_profile_exit_2_without_partial_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    result = _run_module(
        _init_cli_args(
            tmp_path,
            PASS_STRIP,
            "idle",
            bundle,
            polish_profile="missing",
        )
    )
    assert result.returncode == 2
    assert "unknown Polish profile" in result.stderr
    assert not bundle.exists()


def test_init_review_strip_json_exit_3(tmp_path: Path, capsys) -> None:
    bundle = tmp_path / "bundle"
    base = ingest_strip_provider(PASS_STRIP, _corpus_layout(), motion_class="idle")
    review = IngestResult(
        layout=base.layout,
        source=base.source,
        recovered=base.recovered,
        slice_meta=base.slice_meta,
        coherence={**base.coherence, "outcome": "REVIEW", "pass": False},
        pass_=False,
        outcome="REVIEW",
    )
    with (
        patch("pipeline.final_polish.ingest_strip_provider", return_value=review),
        patch("pipeline.final_polish_cli.ingest_strip_provider", return_value=review),
    ):
        code = main(_init_cli_args(tmp_path, PASS_STRIP, "idle", bundle, json_mode=True))
    assert code == 3
    data = json.loads(capsys.readouterr().out)
    assert data["outcome"] == "REVIEW"
    assert data["pass"] is False


def test_init_review_strip_exit_3(tmp_path: Path, capsys) -> None:
    bundle = tmp_path / "bundle"
    base = ingest_strip_provider(PASS_STRIP, _corpus_layout(), motion_class="idle")
    review = IngestResult(
        layout=base.layout,
        source=base.source,
        recovered=base.recovered,
        slice_meta=base.slice_meta,
        coherence={**base.coherence, "outcome": "REVIEW", "pass": False},
        pass_=False,
        outcome="REVIEW",
    )
    with (
        patch("pipeline.final_polish.ingest_strip_provider", return_value=review),
        patch("pipeline.final_polish_cli.ingest_strip_provider", return_value=review),
    ):
        code = main(_init_cli_args(tmp_path, PASS_STRIP, "idle", bundle))
    assert code == 3
    assert not bundle.exists()
    assert "REVIEW" in capsys.readouterr().out


def test_init_invalid_provider_exit_2(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    missing = tmp_path / "missing.png"
    provenance_path = tmp_path / "missing.source.json"
    _write_animation_provenance(PASS_STRIP, provenance_path, motion_class="idle")
    result = _run_module(
        [
            "init",
            str(missing),
            "--motion-class",
            "idle",
            "--out",
            str(bundle),
            "--provenance",
            str(provenance_path),
        ]
    )
    assert result.returncode == 2
    assert result.stderr.strip()
    assert not result.stdout.strip()


def test_init_unknown_motion_class_exit_2(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    result = _run_module(_init_cli_args(tmp_path, PASS_STRIP, "nonsense", bundle))
    assert result.returncode == 2
    assert "unknown motion_class" in result.stderr


def test_init_existing_bundle_exit_2(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    result = _run_module(_init_cli_args(tmp_path, PASS_STRIP, "idle", bundle))
    assert result.returncode == 2
    assert "already exists" in result.stderr


def test_check_pass_exit_0(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_module(["check", str(bundle)])
    assert result.returncode == 0, result.stderr
    assert "Overall  PASS" in result.stdout


def test_brief_json_is_read_only_and_selects_walk_questions(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _library_init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="miner")
    before = _bundle_fingerprint(bundle)

    result = _run_module(["brief", str(bundle), "--json"])

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


def test_brief_human_output_is_actionable(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _library_init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="miner")

    result = _run_module(["brief", str(bundle)])

    assert result.returncode == 0, result.stderr
    assert "Profile   miner" in result.stdout
    assert "Verdicts  PASS, EDIT, UNCERTAIN" in result.stdout
    assert "identity_anchors:" in result.stdout
    assert "alternating_legs:" in result.stdout
    assert "Editing rules" in result.stdout
    assert "Audit workflow" in result.stdout


def test_brief_requires_a_profiled_bundle(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)

    result = _run_module(["brief", str(bundle), "--json"])

    assert result.returncode == 2
    assert "--polish-profile" in result.stderr
    assert not result.stdout


def test_check_fail_exit_1(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (3, 99, 200))

    result = _run_module(["check", str(bundle)])
    assert result.returncode == 1
    assert "FAIL" in result.stdout


def test_check_fail_json_exit_1(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (3, 99, 200))

    result = _run_module(["check", str(bundle), "--json"])
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["outcome"] == "FAIL"
    assert data["structural"]["pass"] is False


def test_check_review_exit_3(tmp_path: Path, capsys) -> None:
    bundle = _init_bundle(tmp_path)
    base = ingest_strip_provider(bundle / "provider" / "source.png", _corpus_layout(), motion_class="idle")
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
        code = main(["check", str(bundle)])
    assert code == 3
    assert "Overall  REVIEW" in capsys.readouterr().out


def test_check_review_json_exit_3(tmp_path: Path, capsys) -> None:
    bundle = _init_bundle(tmp_path)
    base = ingest_strip_provider(bundle / "provider" / "source.png", _corpus_layout(), motion_class="idle")
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
        code = main(["check", str(bundle), "--json"])
    assert code == 3
    data = json.loads(capsys.readouterr().out)
    assert data["outcome"] == "REVIEW"


def test_check_invalid_bundle_exit_2(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    (bundle / "manifest.json").unlink()
    result = _run_module(["check", str(bundle)])
    assert result.returncode == 2
    assert result.stderr.strip()
    assert not result.stdout.strip()


def test_finalize_pass_exit_0_and_creates_release(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_module(["finalize", str(bundle)])
    assert result.returncode == 0, result.stderr
    assert "Report" in result.stdout
    assert "Release" in result.stdout
    assert (bundle / "release" / "frame-0.png").is_file()


def test_finalize_pass_json_exit_0(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_module(["finalize", str(bundle), "--json"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["outcome"] == "PASS"
    assert "report_path" in data
    assert "release_frames" in data
    assert len(data["release_frames"]) == FRAME_COUNT


def test_finalize_fail_json_exit_1(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (250, 1, 2))

    result = _run_module(["finalize", str(bundle), "--json"])
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["outcome"] == "FAIL"
    assert "report_path" in data
    assert "release_frames" not in data


def test_finalize_review_exit_3_records_report(tmp_path: Path, capsys) -> None:
    bundle = _init_bundle(tmp_path)
    base = ingest_strip_provider(bundle / "provider" / "source.png", _corpus_layout(), motion_class="idle")
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
        code = main(["finalize", str(bundle)])
    assert code == 3
    captured = capsys.readouterr().out
    assert "Overall  REVIEW" in captured
    assert "Report" in captured
    assert len(list((bundle / "reports").glob("*.json"))) == 1
    assert not (bundle / "release").exists()


def test_finalize_review_json_exit_3(tmp_path: Path, capsys) -> None:
    bundle = _init_bundle(tmp_path)
    base = ingest_strip_provider(bundle / "provider" / "source.png", _corpus_layout(), motion_class="idle")
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
        code = main(["finalize", str(bundle), "--json"])
    assert code == 3
    data = json.loads(capsys.readouterr().out)
    assert data["outcome"] == "REVIEW"
    assert "report_path" in data
    assert "release_frames" not in data


def test_finalize_fail_exit_1_records_report_without_release(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (250, 1, 2))

    result = _run_module(["finalize", str(bundle)])
    assert result.returncode == 1
    assert "Report" in result.stdout
    assert "Release" not in result.stdout
    assert not (bundle / "release").exists()
    assert len(list((bundle / "reports").glob("*.json"))) == 1


def test_no_override_flags_in_parser() -> None:
    from pipeline import final_polish_cli as cli

    parser = argparse.ArgumentParser()
    cli._configure_parser(parser)
    flags = {
        action.dest
        for action in parser._actions
        if action.dest not in {"help", "json", "command"}
    }
    assert "force" not in flags
    assert "yes" not in flags
    assert "override" not in flags


def test_seed_cli_emits_json_and_is_byte_identical_on_rerun(tmp_path: Path) -> None:
    out_a = tmp_path / "seed-a.png"
    out_b = tmp_path / "seed-b.png"
    result = _run_module(
        ["seed", "--identity", str(IDENTITY_PNG), "--out", str(out_a), "--json"]
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["dimensions"] == [1120, 384]
    assert data["sha256"] == sha256_file(out_a)
    rerun = _run_module(
        ["seed", "--identity", str(IDENTITY_PNG), "--out", str(out_b), "--json"]
    )
    assert rerun.returncode == 0
    assert out_a.read_bytes() == out_b.read_bytes()


def test_dwarf_miner_profile_and_prompt_require_image_edit_workflow() -> None:
    profile = json.loads((ROOT / "polish-profiles" / "dwarf-miner.json").read_text())
    workflow = profile["audit_workflow"]
    assert any("Identity Lock" in step for step in workflow)
    assert any("image-edit" in step.lower() for step in workflow)
    assert any("sequential" in step.lower() or "Attempt" in step for step in workflow)
    prompt = (ROOT / "prompts" / "production" / "animation-strip.md").read_text()
    assert "image-edit" in prompt.lower()
    assert "identity seed" in prompt.lower() or "strip:polish seed" in prompt
    assert "text-to-image" in prompt.lower()


def test_human_report_includes_required_fields(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_module(["check", str(bundle)])
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    assert "Bundle" in stdout
    assert "Provider" in stdout
    assert "Motion" in stdout
    assert "Structural" in stdout
    assert "Edits" in stdout
    assert "palette_drift_pass" in stdout
    assert "Overall  PASS" in stdout
    assert "Motion" in stdout
    assert "Structural" in stdout
    assert "Edits" in stdout
    assert "palette_drift_pass" in stdout
    assert "Overall  PASS" in stdout


def test_json_mode_emits_single_object_with_complete_payload(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_module(["check", str(bundle), "--json"])
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


def test_json_invalid_invocation_writes_stderr_only(tmp_path: Path) -> None:
    result = _run_module(["check", str(tmp_path / "missing-bundle")])
    assert result.returncode == 2
    assert result.stderr.strip()
    assert not result.stdout.strip()


def test_check_is_read_only_human_and_json(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    before = _bundle_fingerprint(bundle)

    human = _run_module(["check", str(bundle)])
    assert human.returncode == 0, human.stderr
    assert _bundle_fingerprint(bundle) == before

    json_result = _run_module(["check", str(bundle), "--json"])
    assert json_result.returncode == 0, json_result.stderr
    assert _bundle_fingerprint(bundle) == before


def test_finalize_revalidates_and_lists_release_only_on_pass(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (250, 1, 2))

    fail = _run_module(["finalize", str(bundle)])
    assert fail.returncode == 1
    report_path = next((bundle / "reports").glob("*.json"))
    report = json.loads(report_path.read_text())
    assert report["outcome"] == "FAIL"
    assert "release_frames" not in report
    assert "Report" in fail.stdout

    draft = bundle / "draft" / "frame-0.png"
    polished.write_bytes(draft.read_bytes())

    pass_result = _run_module(["finalize", str(bundle)])
    assert pass_result.returncode == 0, pass_result.stderr
    assert "Report" in pass_result.stdout
    release_paths = sorted((bundle / "release").glob("*.png"))
    assert len(release_paths) == FRAME_COUNT
    for path in release_paths:
        polished_path = bundle / "polished" / path.name
        assert sha256_file(path) == sha256_file(polished_path)


def test_direct_png_edit_accepted_without_editor(tmp_path: Path) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)

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
    _set_opaque_rgb(polished, x, y, palette_color)

    result = _run_module(["check", str(bundle)])
    assert result.returncode == 0, result.stderr


def test_cli_has_no_aseprite_dependency() -> None:
    from pipeline import final_polish_cli as cli

    source = inspect.getsource(cli)
    assert "aseprite" not in source.lower()
    assert "Aseprite" not in source
