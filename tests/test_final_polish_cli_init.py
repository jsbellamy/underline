"""Subprocess proof for pipeline.final_polish_cli's `init` subcommand (#96, #101, #264).

`init`: argument rejection, partial-bundle cases, the `seed` and `acquire`
pre-init preparation subcommands, and the general parser/profile-doc checks
that are not specific to `check` or `finalize`. A test that asserts on a
`check` or `finalize` report belongs in tests/test_final_polish_cli_check.py
or tests/test_final_polish_cli_finalize.py instead.
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from pipeline.final_polish_cli import main
from pipeline.gate_evidence import sha256_file
from pipeline.strip import (
    IngestResult,
    ingest_strip_provider,
)
from tests.support import polish_bundle as pb
from tests.support.final_polish_fixtures import (
    CANONICAL_IDENTITY_SHA,
    IDENTITY_JSON,
    IDENTITY_PNG,
    INBOX,
    LANTERN_STRIP,
    PASS_STRIP,
    ROOT,
    _corpus_layout,
    _run_cli,
    _write_cli_animation_provenance,
)

FAIL_STRIP = INBOX / "08-NEG-identity-drift.png"
IDLE_SEED_STRIP = ROOT / "assets" / "first-room" / "dwarf" / "idle" / "provider" / "source.png"
GENERATION_SOURCE_SHA256 = "655b8ff6a560d0e36ac008872d37239e33e25e51d70e77f4201ac2d1ca043ad3"
PADDED_SEED_DIMENSIONS = [1664, 1152]


def test_init_creates_bundle_via_module_entrypoint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    args = pb.init_argv(attempt, bundle)
    result = _run_cli(capsys, args, env=dict(attempt.env))
    assert result.returncode == 0, result.stderr
    assert (bundle / "manifest.json").is_file()
    assert (bundle / "polished" / "frame-0.png").is_file()


def test_init_fail_strip_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(FAIL_STRIP, "idle", tmp_path)
    args = pb.init_argv(attempt, bundle)
    result = _run_cli(capsys, args, env=dict(attempt.env))
    assert result.returncode == 1
    assert not bundle.exists()
    assert "FAIL" in result.stdout
    assert "palette_drift_pass" in result.stdout or "silhouette" in result.stdout


def test_init_fail_strip_json_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(FAIL_STRIP, "idle", tmp_path)
    args = pb.init_argv(attempt, bundle, json_mode=True)
    result = _run_cli(capsys, args, env=dict(attempt.env))
    assert result.returncode == 1
    assert not bundle.exists()
    data = json.loads(result.stdout)
    assert data["outcome"] == "FAIL"
    assert data["pass"] is False
    assert "coherence" in data
    assert "gate_outcomes" in data


def test_init_pass_json_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    args = pb.init_argv(attempt, bundle, json_mode=True)
    result = _run_cli(capsys, args, env=dict(attempt.env))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["outcome"] == "PASS"
    assert "fingerprint" in data
    assert "structural" in data


def test_init_with_profile_binds_profile_in_json_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path, polish_profile="miner")
    args = pb.init_argv(attempt, bundle, json_mode=True)
    result = _run_cli(capsys, args, env=dict(attempt.env))
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
    attempt = pb.prepare(strip, motion_class, tmp_path, polish_profile=profile_id)
    args = pb.init_argv(attempt, bundle, json_mode=True)
    result = _run_cli(capsys, args, env=dict(attempt.env))
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["polish_profile"] == {
        "id": profile_id,
        "sha256": sha256_file(bundle / "profile.json"),
    }


def test_init_unknown_profile_exit_2_without_partial_bundle(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path, polish_profile="missing")
    args = pb.init_argv(attempt, bundle)
    result = _run_cli(capsys, args, env=dict(attempt.env))
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
        attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
        args = pb.init_argv(attempt, bundle, json_mode=True)

        with patch.dict("os.environ", dict(attempt.env)):

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
        attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
        args = pb.init_argv(attempt, bundle)

        with patch.dict("os.environ", dict(attempt.env)):

            code = main(args)
    assert code == 3
    assert not bundle.exists()
    assert "REVIEW" in capsys.readouterr().out


def test_init_invalid_provider_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    missing = tmp_path / "missing.png"
    provenance_path = tmp_path / "missing.source.json"
    _write_cli_animation_provenance(PASS_STRIP, provenance_path, motion_class="idle")
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
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    args = pb.init_argv(attempt, bundle)
    motion_class_index = args.index("--motion-class")
    args[motion_class_index + 1] = "nonsense"
    result = _run_cli(capsys, args, env=dict(attempt.env))
    assert result.returncode == 2
    assert "unknown motion_class" in result.stderr


def test_init_existing_bundle_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    attempt = pb.prepare(PASS_STRIP, "idle", tmp_path)
    args = pb.init_argv(attempt, bundle)
    result = _run_cli(capsys, args, env=dict(attempt.env))
    assert result.returncode == 2
    assert "already exists" in result.stderr


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
