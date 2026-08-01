"""Subprocess proof for pipeline.final_polish_cli (issues #96 and #101)."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline.final_polish import initialize_bundle
from pipeline.final_polish_cli import main
from pipeline.gate_evidence import sha256_bytes, sha256_file
from pipeline.identity_lock import build_identity_seed
from pipeline.strip import (
    DEFAULT_LAYOUT,
    IngestResult,
    StripLayout,
    ingest_strip_provider,
    layout_for_motion_class,
    load_provider_frames,
)

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "prototype" / "strip-coherence" / "inbox"
PASS_STRIP = INBOX / "01-miner-idle.png"
FAIL_STRIP = INBOX / "08-NEG-identity-drift.png"
WALK_STRIP = INBOX / "05-miner-walk.png"
SWING_STRIP = INBOX / "06-miner-swing.png"
LANTERN_STRIP = INBOX / "14-lantern-flicker.png"
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
IDENTITY_JSON = ROOT / "assets" / "first-room" / "dwarf" / "identity.json"
IDLE_SEED_STRIP = ROOT / "assets" / "first-room" / "dwarf" / "idle" / "provider" / "source.png"
from tests.test_final_polish import (
    _dwarf_miner_ingest_source,
    _effective_dwarf_miner_provider,
    _padded_inbox_provider,
    _swing_provider_on_edit_canvas,
    _swing_provider_strip,
    _walk_provider_on_edit_canvas,
)

CANONICAL_IDENTITY_SHA = "7495a733c11be50fff2d2a16d5842d56d6a79cb7642da7a344bc699290f7c9c6"
GENERATION_SOURCE_SHA256 = "655b8ff6a560d0e36ac008872d37239e33e25e51d70e77f4201ac2d1ca043ad3"
PADDED_SEED_DIMENSIONS = [1664, 1152]


def _padded_edit_source_seed(tmp_path: Path, motion_class: str = "walk") -> Path:
    out = tmp_path / (
        "swing-edit-source.png" if motion_class == "swing" else "padded-edit-source.png"
    )
    kwargs: dict[str, str] = {}
    if motion_class == "swing":
        kwargs["motion_class"] = "swing"
    build_identity_seed(IDENTITY_JSON, out, **kwargs)
    return out
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


@dataclass
class _CliResult:
    returncode: int
    stdout: str
    stderr: str


def _run_cli(
    capsys: pytest.CaptureFixture[str],
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> _CliResult:
    if env is None:
        returncode = main(args)
    else:
        with patch.dict("os.environ", env):
            returncode = main(args)
    captured = capsys.readouterr()
    return _CliResult(returncode=returncode, stdout=captured.out, stderr=captured.err)


def _run_check_cli(
    capsys: pytest.CaptureFixture[str],
    bundle: Path,
    ingest_source: Path,
    *,
    json_mode: bool = True,
) -> _CliResult:
    args = ["check", str(bundle)]
    if json_mode:
        args.append("--json")
    with patch(
        "pipeline.final_polish.load_provider_frames",
        side_effect=lambda path, layout: load_provider_frames(ingest_source, layout),
    ):
        return _run_cli(capsys, args, env=_bundle_store_env(bundle))


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


def _acquisition_store_env(store_root: Path) -> dict[str, str]:
    return {"UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root)}


def _bundle_store_env(bundle: Path) -> dict[str, str] | None:
    store_root = bundle.parent / "acquisition-controls"
    if (store_root / "attempts.jsonl").is_file():
        return _acquisition_store_env(store_root)
    return None


def _register_store_attempt_for_init(
    tmp_path: Path,
    provider_path: Path,
    motion_class: str,
    *,
    polish_profile: str | None = None,
) -> tuple[Path, Path, list[str], dict[str, str]]:
    from pipeline import asset_acquire as aa

    effective_provider = _effective_provider_path(
        provider_path,
        tmp_path,
        motion_class,
        polish_profile=polish_profile,
    )
    store_root = tmp_path / "acquisition-controls"
    generation_mode = (
        "image-edit"
        if polish_profile == "dwarf-miner" and motion_class in {"walk", "swing"}
        else "text-to-image"
    )
    record_kwargs: dict[str, object] = {
        "motion_class": motion_class,
        "generation_mode": generation_mode,
        "acquiring_agent": "pytest",
        "prompt_text": "underline cli test provenance prompt",
        "repo_root": tmp_path,
    }
    identity_args: list[str] = []
    if generation_mode == "image-edit":
        padded_seed = _padded_edit_source_seed(tmp_path, motion_class)
        record_kwargs["reference_image_sha256"] = CANONICAL_IDENTITY_SHA
        record_kwargs["edit_source"] = padded_seed
        identity_args = [
            "--identity-reference",
            str(IDENTITY_PNG),
            "--edit-source",
            str(padded_seed),
        ]
    env = _acquisition_store_env(store_root)
    with patch.dict("os.environ", env):
        row = aa.record_asset_attempt(
            effective_provider,
            f"test/{motion_class}",
            **record_kwargs,
        )
    provenance_path = tmp_path / f"{effective_provider.stem}.source.json"
    provenance_kwargs: dict[str, object] = {
        "motion_class": motion_class,
        "generation_mode": generation_mode,
        "attempt_id": row["attempt_id"],
        "predecessor_attempt_id": row["predecessor_attempt_id"],
        "specification_id": f"test/{motion_class}",
    }
    if generation_mode == "image-edit":
        padded_seed = _padded_edit_source_seed(tmp_path, motion_class)
        provenance_kwargs.update(
            {
                "reference_image_sha256": [CANONICAL_IDENTITY_SHA],
                "edit_source_sha256": sha256_file(padded_seed),
            }
        )
    provider_for_init = store_root / row["raw_path"]
    _write_animation_provenance(provider_for_init, provenance_path, **provenance_kwargs)
    return provider_for_init, provenance_path, identity_args, env



def _provider_dimensions(provider_path: Path) -> list[int]:
    with Image.open(provider_path) as image:
        return [image.width, image.height]


def _item_geometry_for(motion_class: str) -> dict[str, int]:
    try:
        layout = layout_for_motion_class(motion_class, margin_cells=0)
    except ValueError:
        layout = _corpus_layout()
    return {
        "frame_w": layout.frame_w,
        "frame_h": layout.frame_h,
        "frame_count": layout.frame_count,
        "gutter": layout.gutter,
    }


def _write_animation_provenance(
    provider_path: Path,
    provenance_path: Path,
    *,
    motion_class: str,
    generation_mode: str = "text-to-image",
    attempt_id: str = "cli-test--001",
    predecessor_attempt_id: str | None = None,
    reference_image_sha256: list[str] | None = None,
    edit_source_sha256: str | None = None,
    **overrides: object,
) -> None:
    if reference_image_sha256 is None:
        reference_image_sha256 = []
    prompt_text = "underline cli test provenance prompt"
    record: dict[str, object] = {
        "schema": "animation-strip-provenance/0",
        "specification_id": f"test/{motion_class}",
        "attempt_id": attempt_id,
        "predecessor_attempt_id": predecessor_attempt_id,
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
        "item_geometry": _item_geometry_for(motion_class),
    }
    record.update(overrides)
    provenance_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _effective_provider_path(
    provider_path: Path,
    tmp_path: Path,
    motion_class: str,
    *,
    polish_profile: str | None = None,
) -> Path:
    if polish_profile == "dwarf-miner":
        return _effective_dwarf_miner_provider(provider_path, tmp_path, motion_class)
    return provider_path


def _provenance_args(
    tmp_path: Path,
    provider_path: Path,
    motion_class: str,
    *,
    polish_profile: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    _, provenance_path, identity_args, env = _register_store_attempt_for_init(
        tmp_path,
        provider_path,
        motion_class,
        polish_profile=polish_profile,
    )
    return ["--provenance", str(provenance_path), *identity_args], env



def _init_cli_args(
    tmp_path: Path,
    provider_path: Path,
    motion_class: str,
    bundle: Path,
    *,
    polish_profile: str | None = None,
    json_mode: bool = False,
) -> tuple[list[str], dict[str, str]]:
    provider_for_init, provenance_path, identity_args, env = _register_store_attempt_for_init(
        tmp_path,
        provider_path,
        motion_class,
        polish_profile=polish_profile,
    )
    args = [
        "init",
        str(provider_for_init),
        "--motion-class",
        motion_class,
        "--out",
        str(bundle),
        "--provenance",
        str(provenance_path),
        *identity_args,
    ]
    if polish_profile is not None:
        args.extend(["--polish-profile", polish_profile])
    if json_mode:
        args.append("--json")
    return args, env



def _library_init_bundle(
    provider_path: Path,
    motion_class: str,
    bundle: Path,
    tmp_path: Path,
    *,
    polish_profile: str | None = None,
) -> None:
    provider_for_init, provenance_path, identity_args, env = _register_store_attempt_for_init(
        tmp_path,
        provider_path,
        motion_class,
        polish_profile=polish_profile,
    )
    identity = Path(identity_args[1]) if len(identity_args) > 1 else None
    edit = Path(identity_args[3]) if len(identity_args) > 3 else None
    effective_provider = _effective_provider_path(
        provider_path,
        tmp_path,
        motion_class,
        polish_profile=polish_profile,
    )
    ingest_source = (
        _dwarf_miner_ingest_source(provider_path, motion_class)
        if polish_profile == "dwarf-miner" and effective_provider != provider_path
        else effective_provider
    )
    probe_layout = layout_for_motion_class(motion_class, margin_cells=0)
    init_kwargs = {
        "provenance_sidecar": provenance_path,
        "polish_profile": polish_profile,
        "identity_reference": identity,
        "edit_source": edit,
    }
    if ingest_source != effective_provider:
        base_ingest = ingest_strip_provider(ingest_source, probe_layout, motion_class=motion_class)
        base_frames = load_provider_frames(ingest_source, probe_layout)
        with (
            patch(
                "pipeline.final_polish.ingest_strip_provider",
                return_value=base_ingest,
            ),
            patch(
                "pipeline.final_polish.load_provider_frames",
                return_value=base_frames,
            ),
            patch.dict("os.environ", env),
        ):
            initialize_bundle(
                provider_for_init,
                motion_class,
                bundle,
                **init_kwargs,
            )
        return
    with patch.dict("os.environ", env):
        initialize_bundle(
            provider_for_init,
            motion_class,
            bundle,
            **init_kwargs,
        )


def _init_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    _library_init_bundle(PASS_STRIP, "idle", bundle, tmp_path)
    return bundle



def _bundle_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.parent.name != "reports":
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
    args, env = _init_cli_args(tmp_path, PASS_STRIP, "idle", bundle)
    init = _run_npm(args, env=env)
    assert init.returncode == 0, init.stderr
    assert bundle.is_dir()

    check = _run_npm(["check", str(bundle)], env=env)
    assert check.returncode == 0, check.stderr

    finalize = _run_npm(["finalize", str(bundle)], env=env)
    assert finalize.returncode == 0, finalize.stderr
    assert list((bundle / "release").glob("*.png"))


def test_init_creates_bundle_via_module_entrypoint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    args, env = _init_cli_args(tmp_path, PASS_STRIP, "idle", bundle)
    result = _run_cli(capsys, args, env=env)
    assert result.returncode == 0, result.stderr
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "polished" / "frame-0.png").is_file()


def test_init_fail_strip_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    args, env = _init_cli_args(tmp_path, FAIL_STRIP, "idle", bundle)
    result = _run_cli(capsys, args, env=env)
    assert result.returncode == 1
    assert not bundle.exists()
    assert "FAIL" in result.stdout
    assert "palette_drift_pass" in result.stdout or "silhouette" in result.stdout


def test_init_fail_strip_json_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    args, env = _init_cli_args(tmp_path, FAIL_STRIP, "idle", bundle, json_mode=True)
    result = _run_cli(capsys, args, env=env)
    assert result.returncode == 1
    assert not bundle.exists()
    data = json.loads(result.stdout)
    assert data["outcome"] == "FAIL"
    assert data["pass"] is False
    assert "coherence" in data
    assert "gate_outcomes" in data


def test_init_pass_json_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    args, env = _init_cli_args(tmp_path, PASS_STRIP, "idle", bundle, json_mode=True)
    result = _run_cli(capsys, args, env=env)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["outcome"] == "PASS"
    assert "fingerprint" in data
    assert "structural" in data


def test_init_with_profile_binds_profile_in_json_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    args, env = _init_cli_args(
        tmp_path,
        PASS_STRIP,
        "idle",
        bundle,
        polish_profile="miner",
        json_mode=True,
    )
    result = _run_cli(capsys, args, env=env)
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
    capsys: pytest.CaptureFixture[str],
    profile_id: str,
    strip: Path,
    motion_class: str,
) -> None:
    bundle = tmp_path / "bundle"
    args, env = _init_cli_args(
        tmp_path,
        strip,
        motion_class,
        bundle,
        polish_profile=profile_id,
        json_mode=True,
    )
    result = _run_cli(capsys, args, env=env)
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
    capsys: pytest.CaptureFixture[str],
    profile_id: str,
    strip: Path,
    motion_class: str,
    motion_ids: list[str],
) -> None:
    bundle = tmp_path / "bundle"
    _library_init_bundle(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)
    before = _bundle_fingerprint(bundle)

    result = _run_cli(capsys, ["brief", str(bundle), "--json"])

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["profile"]["id"] == profile_id
    assert data["motion_class"] == motion_class
    assert [row["id"] for row in data["motion_questions"]] == motion_ids
    assert _bundle_fingerprint(bundle) == before


def test_init_unknown_profile_exit_2_without_partial_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    args, env = _init_cli_args(
        tmp_path,
        PASS_STRIP,
        "idle",
        bundle,
        polish_profile="missing",
    )
    result = _run_cli(capsys, args, env=env)
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
        args, env = _init_cli_args(tmp_path, PASS_STRIP, "idle", bundle, json_mode=True)

        with patch.dict("os.environ", env):

            code = main(args)
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
        args, env = _init_cli_args(tmp_path, PASS_STRIP, "idle", bundle)

        with patch.dict("os.environ", env):

            code = main(args)
    assert code == 3
    assert not bundle.exists()
    assert "REVIEW" in capsys.readouterr().out


def test_init_invalid_provider_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    missing = tmp_path / "missing.png"
    provenance_path = tmp_path / "missing.source.json"
    _write_animation_provenance(PASS_STRIP, provenance_path, motion_class="idle")
    result = _run_cli(capsys,
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


def test_init_unknown_motion_class_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    args, env = _init_cli_args(tmp_path, PASS_STRIP, "nonsense", bundle)
    result = _run_cli(capsys, args, env=env)
    assert result.returncode == 2
    assert "unknown motion_class" in result.stderr


def test_init_existing_bundle_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    args, env = _init_cli_args(tmp_path, PASS_STRIP, "idle", bundle)
    result = _run_cli(capsys, args, env=env)
    assert result.returncode == 2
    assert "already exists" in result.stderr


def test_check_pass_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_cli(capsys, ["check", str(bundle)], env=_bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    assert "Overall  PASS" in result.stdout


def test_check_summary_json_emits_only_dispatch_baseline_fields(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _init_bundle(tmp_path)

    result = _run_cli(capsys, ["check", str(bundle), "--summary-json"], env=_bundle_store_env(bundle))

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
    _library_init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="miner")
    before = _bundle_fingerprint(bundle)

    result = _run_cli(capsys, ["brief", str(bundle), "--json"])

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
    _library_init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="miner")

    result = _run_cli(capsys, ["brief", str(bundle)])

    assert result.returncode == 0, result.stderr
    assert "Profile   miner" in result.stdout
    assert "Verdicts  PASS, EDIT, UNCERTAIN" in result.stdout
    assert "identity_anchors:" in result.stdout
    assert "alternating_legs:" in result.stdout
    assert "Editing rules" in result.stdout
    assert "Audit workflow" in result.stdout


def test_brief_requires_a_profiled_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)

    result = _run_cli(capsys, ["brief", str(bundle), "--json"])

    assert result.returncode == 2
    assert "--polish-profile" in result.stderr
    assert not result.stdout


def test_check_json_includes_silhouette_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_cli(capsys, ["check", str(bundle), "--json"], env=_bundle_store_env(bundle))
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
    swing_strip = _swing_provider_strip(tmp_path)
    _library_init_bundle(swing_strip, "swing", bundle, tmp_path, polish_profile="dwarf-miner")

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
    swing_strip = _swing_provider_strip(tmp_path)
    _library_init_bundle(swing_strip, "swing", bundle, tmp_path, polish_profile="dwarf-miner")

    with patch(
        "pipeline.final_polish.load_provider_frames",
        side_effect=lambda path, layout: load_provider_frames(swing_strip, layout),
    ):
        result = _run_cli(capsys, ["check", str(bundle)], env=_bundle_store_env(bundle))

    assert result.returncode == 1, result.stderr
    assert "Post-edit   FAIL (edit_source_continuity_fail)" in result.stdout


def test_check_human_report_marks_provider_post_edit_not_applicable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _init_bundle(tmp_path)

    result = _run_cli(capsys, ["check", str(bundle)], env=_bundle_store_env(bundle))

    assert result.returncode == 0, result.stderr
    assert "Post-edit   (n/a)" in result.stdout


def test_check_json_provider_post_edit_is_null_when_not_evaluated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle = _init_bundle(tmp_path)

    result = _run_cli(capsys, ["check", str(bundle), "--json"], env=_bundle_store_env(bundle))

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "provider_post_edit" in data
    assert data["provider_post_edit"] is None


def test_check_fail_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (3, 99, 200))

    result = _run_cli(capsys, ["check", str(bundle)], env=_bundle_store_env(bundle))
    assert result.returncode == 1
    assert "FAIL" in result.stdout


def test_check_fail_json_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (3, 99, 200))

    result = _run_cli(capsys, ["check", str(bundle), "--json"], env=_bundle_store_env(bundle))
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


def test_check_invalid_bundle_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    (bundle / "manifest.json").unlink()
    result = _run_cli(capsys, ["check", str(bundle)], env=_bundle_store_env(bundle))
    assert result.returncode == 2
    assert result.stderr.strip()
    assert not result.stdout.strip()


def test_finalize_pass_exit_0_and_creates_release(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_cli(capsys, ["finalize", str(bundle)], env=_bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    assert "Report" in result.stdout
    assert "Release" in result.stdout
    assert (bundle / "release" / "frame-0.png").is_file()


def test_finalize_pass_json_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    result = _run_cli(capsys, ["finalize", str(bundle), "--json"], env=_bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["outcome"] == "PASS"
    assert "report_path" in data
    assert "release_frames" in data
    assert len(data["release_frames"]) == FRAME_COUNT


def test_finalize_fail_json_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (250, 1, 2))

    result = _run_cli(capsys, ["finalize", str(bundle), "--json"], env=_bundle_store_env(bundle))
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
        with patch.dict("os.environ", _bundle_store_env(bundle) or {}):
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
        with patch.dict("os.environ", _bundle_store_env(bundle) or {}):
            code = main(["finalize", str(bundle), "--json"])
    assert code == 3
    data = json.loads(capsys.readouterr().out)
    assert data["outcome"] == "REVIEW"
    assert "report_path" in data
    assert "release_frames" not in data


def test_finalize_fail_exit_1_records_report_without_release(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (250, 1, 2))

    result = _run_cli(capsys, ["finalize", str(bundle)], env=_bundle_store_env(bundle))
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


def test_seed_cli_swing_motion_class_writes_24_cell_canvas(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_path = tmp_path / "swing-seed.png"
    result = _run_cli(
        capsys,
        [
            "seed",
            "--identity-declaration",
            str(IDENTITY_JSON),
            "--motion-class",
            "swing",
            "--out",
            str(out_path),
            "--json",
        ],
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["motion_class"] == "swing"
    assert data["dimensions"] == [2432, 1152]
    assert data["sha256"] == sha256_file(out_path)
    with Image.open(out_path) as image:
        assert image.size == (2432, 1152)


def test_seed_cli_without_motion_class_reproduces_current_digest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline_path = tmp_path / "baseline-seed.png"
    baseline = _run_cli(
        capsys,
        [
            "seed",
            "--identity-declaration",
            str(IDENTITY_JSON),
            "--out",
            str(baseline_path),
            "--json",
        ],
    )
    assert baseline.returncode == 0, baseline.stderr
    baseline_digest = json.loads(baseline.stdout)["sha256"]
    checked_in = tmp_path / "checked-in-seed.png"
    result = _run_cli(
        capsys,
        [
            "seed",
            "--identity-declaration",
            str(IDENTITY_JSON),
            "--out",
            str(checked_in),
            "--json",
        ],
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["sha256"] == baseline_digest
    assert json.loads(result.stdout)["dimensions"] == PADDED_SEED_DIMENSIONS
    assert sha256_file(checked_in) == baseline_digest


def test_seed_cli_emits_json_and_is_deterministic_on_rerun(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_a = tmp_path / "seed-a.png"
    out_b = tmp_path / "seed-b.png"
    result = _run_cli(capsys,
        [
            "seed",
            "--identity-declaration",
            str(IDENTITY_JSON),
            "--out",
            str(out_a),
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["dimensions"] == PADDED_SEED_DIMENSIONS
    assert data["seed_pad_px"] == 64
    assert data["sha256"] == sha256_file(out_a)
    assert data["generation_source_sha256"] == GENERATION_SOURCE_SHA256
    assert data["sha256"] != data["generation_source_sha256"]
    assert data["identity_anchor_sha256"] == CANONICAL_IDENTITY_SHA
    assert out_a.read_bytes() != IDLE_SEED_STRIP.read_bytes()
    rerun = _run_cli(capsys,
        [
            "seed",
            "--identity-declaration",
            str(IDENTITY_JSON),
            "--out",
            str(out_b),
            "--json",
        ]
    )
    assert rerun.returncode == 0
    assert json.loads(rerun.stdout)["sha256"] == sha256_file(out_b)
    with (
        Image.open(IDLE_SEED_STRIP) as source_image,
        Image.open(out_a) as seed_a_image,
        Image.open(out_b) as seed_b_image,
    ):
        source = source_image.convert("RGBA")
        seed_a = seed_a_image.convert("RGBA")
        seed_b = seed_b_image.convert("RGBA")
        expected = Image.new("RGBA", tuple(PADDED_SEED_DIMENSIONS), (255, 0, 255, 255))
        expected.paste(source, (64, 64))
        assert seed_a.tobytes() == expected.tobytes()
        assert seed_b.tobytes() == expected.tobytes()


def test_seed_cli_rejects_release_identity_as_generation_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = _run_cli(capsys,
        [
            "seed",
            "--identity-declaration",
            str(IDENTITY_PNG),
            "--out",
            str(tmp_path / "seed.png"),
            "--json",
        ]
    )
    assert result.returncode == 2
    assert "identity declaration" in result.stderr


def test_dwarf_miner_profile_and_prompt_require_image_edit_workflow() -> None:
    profile = json.loads((ROOT / "polish-profiles" / "dwarf-miner.json").read_text())
    workflow = " ".join(profile["audit_workflow"]).lower()
    assert "strip:polish seed" in workflow
    assert "idle/provider/source.png" in workflow
    assert "identity.png" in workflow
    assert "16x24" in workflow
    assert "does not read or upscale identity.png" in workflow
    assert "edit_source_sha256" in workflow
    assert "seed_pad_px" in workflow
    assert "padded seed digest" in workflow
    assert "655b8ff6a560d0e36ac008872d37239e33e25e51d70e77f4201ac2d1ca043ad3" not in workflow
    assert "edit_source_not_generation_source" in workflow
    assert "idle provider strip" in workflow
    assert "upscaled or tiled" in workflow
    assert "after provider recovery" in workflow
    assert "text-to-image" in workflow
    assert "sequential" in workflow
    assert "predecessor" in workflow
    assert "quota" in workflow
    assert "identity lock" in workflow
    assert "unmodified provider" in workflow
    assert "painting or stamping identity lock" in workflow
    assert "hard flat identity lock stamps" in workflow
    assert "provider_magenta_wipe" in workflow
    assert "provider_post_edit" in workflow
    assert "edit_source_continuity_fail" in workflow
    prompt = (ROOT / "prompts" / "production" / "animation-strip.md").read_text()
    prompt_lower = prompt.lower()
    assert "image-edit" in prompt_lower
    assert "idle/provider/source.png" in prompt_lower
    assert "identity.png" in prompt_lower
    assert "post-ingest identity anchor" in prompt_lower
    assert "is not the seed command" in prompt_lower
    assert "construct a four-copy strip from `identity.png`" in prompt_lower
    assert "edit_source_sha256" in prompt
    assert "seed_pad_px" in prompt_lower
    assert "padded seed digest" in prompt_lower
    assert "655b8ff6a560d0e36ac008872d37239e33e25e51d70e77f4201ac2d1ca043ad3" not in prompt
    assert "edit_source_not_generation_source" in prompt
    assert "the image being edited" in prompt_lower
    assert "idle provider strip" in prompt_lower
    assert "after provider recovery" in prompt_lower
    assert "text-to-image" in prompt_lower
    assert "explicitly forbidden substitutes" in prompt_lower
    assert "tiling `identity.png`" in prompt_lower
    assert "painting/stamping identity lock" in prompt_lower
    assert "unmodified" in prompt_lower and "provider transport raster" in prompt_lower
    assert "provider_magenta_wipe" in prompt
    assert "edit_source_continuity_fail" in prompt
    contract = (ROOT / "docs" / "strip-acquisition-contract.md").read_text()
    assert "edit_source_not_generation_source" in contract
    assert "seed_pad_px" in contract
    assert "padded seed digest" in contract
    assert "paint/stamp Identity Lock" in contract or "paint/stamp identity lock" in contract.lower()
    assert "provider_magenta_wipe" in contract
    assert "edit_source_continuity_fail" in contract
    art = (ROOT / "docs" / "first-room-art-direction.md").read_text().lower()
    assert "idle provider" in art
    assert "seed_pad_px" in art
    assert "padded seed digest" in art
    assert "does not prove the edit came from idle" in art.replace("\n", " ")
    assert "do not paint identity lock cells" in art.replace("\n", " ")

def test_dwarf_miner_profile_and_prompt_require_clipping_margin_guidance() -> None:
    profile = json.loads((ROOT / "polish-profiles" / "dwarf-miner.json").read_text())
    workflow = " ".join(profile["audit_workflow"]).lower()
    assert "safe empty magenta inset" in workflow
    assert "canvas edge" in workflow
    assert "provider_clipping" in workflow

    prompt = (ROOT / "prompts" / "production" / "animation-strip.md").read_text()
    prompt_lower = prompt.lower()
    assert "16×24" in prompt
    assert "gutter" in prompt_lower and "2" in prompt
    assert "safe" in prompt_lower and "empty magenta inset" in prompt_lower
    assert "canvas edge" in prompt_lower
    assert "provider_clipping" in prompt_lower
    assert "logical strip" in prompt_lower or "logical strip /" in prompt_lower
    assert "gutter=2" in prompt_lower or "gutter = 2" in prompt_lower
    assert "pickaxe" in prompt_lower
    assert "regenerate" in prompt_lower

    contract = (ROOT / "docs" / "strip-acquisition-contract.md").read_text().lower()
    assert "safe empty magenta inset" in contract
    assert "provider_clipping" in contract

    art = (ROOT / "docs" / "first-room-art-direction.md").read_text().lower()
    assert "provider_clipping" in art or "safe empty magenta inset" in art

def test_v2_walk_check_json_binds_sequential_attempt_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    _library_init_bundle(WALK_STRIP, "walk", bundle, tmp_path, polish_profile="dwarf-miner")
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
    bundle = _init_bundle(tmp_path)
    result = _run_cli(capsys, ["check", str(bundle)], env=_bundle_store_env(bundle))
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
    bundle = _init_bundle(tmp_path)
    result = _run_cli(capsys, ["check", str(bundle), "--json"], env=_bundle_store_env(bundle))
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
    result = _run_cli(capsys, ["check", str(tmp_path / "missing-bundle")])
    assert result.returncode == 2
    assert result.stderr.strip()
    assert not result.stdout.strip()


def test_check_is_read_only_human_and_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    before = _bundle_fingerprint(bundle)

    human = _run_cli(capsys, ["check", str(bundle)], env=_bundle_store_env(bundle))
    assert human.returncode == 0, human.stderr
    assert _bundle_fingerprint(bundle) == before

    json_result = _run_cli(capsys, ["check", str(bundle), "--json"], env=_bundle_store_env(bundle))
    assert json_result.returncode == 0, json_result.stderr
    assert _bundle_fingerprint(bundle) == before


def test_finalize_revalidates_and_lists_release_only_on_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = _init_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (250, 1, 2))

    fail = _run_cli(capsys, ["finalize", str(bundle)], env=_bundle_store_env(bundle))
    assert fail.returncode == 1
    report_path = next((bundle / "reports").glob("*.json"))
    report = json.loads(report_path.read_text())
    assert report["outcome"] == "FAIL"
    assert "release_frames" not in report
    assert "Report" in fail.stdout

    draft = bundle / "draft" / "frame-0.png"
    polished.write_bytes(draft.read_bytes())

    pass_result = _run_cli(capsys, ["finalize", str(bundle)], env=_bundle_store_env(bundle))
    assert pass_result.returncode == 0, pass_result.stderr
    assert "Report" in pass_result.stdout
    release_paths = sorted((bundle / "release").glob("*.png"))
    assert len(release_paths) == FRAME_COUNT
    for path in release_paths:
        polished_path = bundle / "polished" / path.name
        assert sha256_file(path) == sha256_file(polished_path)


def test_direct_png_edit_accepted_without_editor(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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

    result = _run_cli(capsys, ["check", str(bundle)], env=_bundle_store_env(bundle))
    assert result.returncode == 0, result.stderr


def test_cli_has_no_aseprite_dependency() -> None:
    from pipeline import final_polish_cli as cli

    source = inspect.getsource(cli)
    assert "aseprite" not in source.lower()
    assert "Aseprite" not in source


# --- C7: `strip:polish acquire` CLI surface ----------------------------------


def _acquire_candidate(tmp_path: Path, tag: int = 0) -> Path:
    path = tmp_path / "candidate.png"
    Image.new("RGBA", (24, 32), (tag % 256, 10, 20, 255)).save(path)
    return path


def _acquire_prompt(tmp_path: Path) -> Path:
    path = tmp_path / "prompt.txt"
    path.write_text("swing the pick")
    return path


def test_acquire_json_payload_has_the_contract_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_root = tmp_path / "acquisition-controls"
    candidate = _acquire_candidate(tmp_path)
    prompt = _acquire_prompt(tmp_path)
    with patch.dict("os.environ", {"UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root)}):
        result = _run_cli(
            capsys,
            [
                "acquire",
                str(candidate),
                "--specification-id",
                "first-room/dwarf/swing",
                "--motion-class",
                "swing",
                "--generation-mode",
                "image-edit",
                "--prompt-file",
                str(prompt),
                "--json",
            ],
        )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert set(payload) == {
        "attempt_id",
        "ordinal",
        "predecessor_attempt_id",
        "outcome",
        "raw_path",
        "raw_sha256",
        "dimensions",
        "provenance_path",
    }
    assert payload["attempt_id"] == "first-room--dwarf--swing--001"
    assert payload["outcome"] == "accepted"
    assert (store_root / payload["raw_path"]).is_file()
    assert (store_root / payload["provenance_path"]).is_file()


def test_acquire_reject_records_rejected_outcome_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_root = tmp_path / "acquisition-controls"
    candidate = _acquire_candidate(tmp_path)
    prompt = _acquire_prompt(tmp_path)
    with patch.dict("os.environ", {"UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root)}):
        result = _run_cli(
            capsys,
            [
                "acquire",
                str(candidate),
                "--specification-id",
                "first-room/dwarf/swing",
                "--motion-class",
                "swing",
                "--generation-mode",
                "image-edit",
                "--prompt-file",
                str(prompt),
                "--reject",
                "silhouette failed",
                "--json",
            ],
        )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "rejected"


def test_acquire_exits_two_on_asset_acquisition_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_root = tmp_path / "acquisition-controls"
    candidate = _acquire_candidate(tmp_path)
    prompt = _acquire_prompt(tmp_path)
    with patch.dict("os.environ", {"UNDERLINE_ACQUISITION_CONTROLS_ROOT": str(store_root)}):
        result = _run_cli(
            capsys,
            [
                "acquire",
                str(candidate),
                "--specification-id",
                "first-room/dwarf/swing",
                "--motion-class",
                "swing",
                "--generation-mode",
                "unknown-mode",
                "--prompt-file",
                str(prompt),
                "--json",
            ],
        )
    assert result.returncode == 2
    assert result.stderr.strip() != ""


def test_acquire_attempt_id_is_not_a_recognized_flag(tmp_path: Path) -> None:
    candidate = _acquire_candidate(tmp_path)
    prompt = _acquire_prompt(tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "acquire",
                str(candidate),
                "--specification-id",
                "first-room/dwarf/swing",
                "--motion-class",
                "swing",
                "--generation-mode",
                "image-edit",
                "--prompt-file",
                str(prompt),
                "--attempt-id",
                "not-allowed",
            ]
        )
    assert excinfo.value.code == 2
