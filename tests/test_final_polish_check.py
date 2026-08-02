"""Behavioral proof for pipeline.final_polish checking (issues #95 and #101).

`check_bundle`: the structural and coherence gates, the attempt-ledger and
attestation rules, silhouette artifacts, and the report payloads a check emits.
A test that initializes a bundle only to assert on `check_bundle`'s report
belongs here rather than in tests/test_final_polish_init.py.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

import adversarial
from pipeline import strip as S
from pipeline.final_polish import (
    ATTEMPT_LEDGER_SCHEMA,
    BUNDLE_SCHEMA_LEGACY_1,
    InvalidBundleError,
    check_bundle as polish_check_bundle,
    initialize_bundle,
)
from pipeline.asset_pack import FIRST_ROOM_ANIMATION_POLICY
from pipeline.gate_evidence import (
    sha256_bytes,
    sha256_file,
)
from pipeline.final_polish_cli import main as final_polish_cli_main
from tests.final_polish_harness import (
    acquisition_store_env,
    record_store_attempt,
)
from tests.support import polish_bundle as pb

from tests.support.final_polish_fixtures import (
    FRAME_COUNT,
    LANTERN_STRIP,
    LOGICAL_SIZE,
    PASS_STRIP,
    ROOT,
    SWING_BUNDLE,
    WALK_STRIP,
    _IDLE_STORE_ATTEMPT_KWARGS,
    _bundle_tree,
    _check_bundle,
    _finalize_bundle,
    _init_bundle,
    _load_frame_rgba,
    _set_opaque_rgb,
    _swing_provider_strip,
    _write_animation_provenance,
)


DWARF_IDLE_BUNDLE = ROOT / "assets" / "first-room" / "dwarf" / "idle"


def _init_bundle_polish(
    strip: Path,
    motion_class: str,
    bundle: Path,
    tmp_path: Path,
    *,
    polish_profile: str | None = None,
) -> None:
    """Idle/blob_idle/emissive/lantern bundle construction via the polish_bundle seam.

    The one swing call site in this module still builds through the interim
    `tests.support.final_polish_fixtures._init_bundle` (issue #249).
    """
    attempt = pb.prepare(strip, motion_class, tmp_path, polish_profile=polish_profile)
    pb.init_bundle(attempt, bundle)


def _init_passing_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path)
    return bundle


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


def _set_alpha(path: Path, x: int, y: int, alpha: int) -> None:
    image = _load_frame_rgba(path)
    pixels = image.load()
    assert pixels is not None
    r, g, b, _ = pixels[x, y]
    pixels[x, y] = (r, g, b, alpha)
    image.save(path)


@pytest.mark.parametrize("profile_id", ["dwarf-miner", "lantern"])
def test_tampered_production_profile_is_an_invalid_bundle(
    tmp_path: Path,
    profile_id: str,
) -> None:
    strip = PASS_STRIP if profile_id == "dwarf-miner" else LANTERN_STRIP
    motion_class = "idle" if profile_id == "dwarf-miner" else "emissive"
    bundle = tmp_path / "bundle"
    _init_bundle_polish(strip, motion_class, bundle, tmp_path, polish_profile=profile_id)
    profile = json.loads((bundle / "profile.json").read_text())
    profile["description"] = "tampered"
    (bundle / "profile.json").write_text(json.dumps(profile) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "profile_hash_mismatch"


def test_tampered_embedded_profile_is_an_invalid_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")
    profile = json.loads((bundle / "profile.json").read_text())
    profile["description"] = "tampered"
    (bundle / "profile.json").write_text(json.dumps(profile) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "profile_hash_mismatch"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("missing", "missing_profile"),
        ("malformed", "invalid_profile"),
        ("schema", "profile_identity_mismatch"),
        ("id", "profile_identity_mismatch"),
        ("content", "invalid_profile"),
    ],
)
def test_invalid_embedded_profiles_fail_closed(
    tmp_path: Path,
    mutation: str,
    reason_code: str,
) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="miner")
    profile_path = bundle / "profile.json"
    manifest_path = bundle / "manifest.json"

    if mutation == "missing":
        profile_path.unlink()
    elif mutation == "malformed":
        profile_path.write_text("{not-json")
    else:
        profile = json.loads(profile_path.read_text())
        if mutation == "content":
            profile.pop("fixed_questions")
        else:
            profile[mutation] = "wrong"
        profile_path.write_text(json.dumps(profile) + "\n")

    if mutation != "missing":
        manifest = json.loads(manifest_path.read_text())
        manifest["polish_profile"]["sha256"] = sha256_file(profile_path)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == reason_code


def test_existing_v1_bundle_remains_check_compatible(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema"] = "final-polish-bundle/1"
    manifest.pop("polish_profile")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    assert _check_bundle(bundle).outcome == "PASS"


def test_v0_bundle_is_rejected(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema"] = "final-polish-bundle/0"
    manifest.pop("polish_profile", None)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "invalid_manifest"


def test_schema_v2_swing_check_rejects_legacy_provenance_geometry(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle(
        _swing_provider_strip(tmp_path),
        "swing",
        bundle,
        tmp_path,
        polish_profile="dwarf-miner",
    )
    provenance_path = bundle / "provider" / "source.source.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["item_geometry"]["frame_w"] = 16
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["provenance"]["sha256"] = sha256_file(provenance_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "invalid_provenance"


def test_schema_v1_swing_check_accepts_legacy_provenance_geometry(tmp_path: Path) -> None:
    bundle = tmp_path / "swing-v1"
    shutil.copytree(SWING_BUNDLE, bundle)
    provenance_path = bundle / "provider" / "source.source.json"
    provenance = json.loads(provenance_path.read_text())
    assert provenance["item_geometry"]["frame_w"] == 16
    result = _check_bundle(bundle)
    assert result.outcome == "PASS"
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA_LEGACY_1


def test_provider_tamper_raises_invalid_bundle(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provider = bundle / "provider" / "source.png"
    provider.write_bytes(provider.read_bytes() + b"\x00")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "provenance_hash_mismatch"


def test_draft_tamper_raises_invalid_bundle(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    draft = bundle / "draft" / "frame-0.png"
    _set_opaque_rgb(draft, 0, 0, (1, 2, 3))

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "draft_hash_mismatch"


@pytest.mark.parametrize(
    ("mutator", "reason_code"),
    [
        ("missing", "missing_frame"),
        ("extra", "extra_frame"),
        ("misordered", "misordered_frames"),
        ("unreadable", "unreadable_frame"),
        ("wrong_mode", "wrong_mode"),
        ("wrong_size", "wrong_size"),
        ("non_binary_alpha", "non_binary_alpha"),
    ],
)
def test_invalid_polished_frames_raise_stable_reason_codes(
    tmp_path: Path, mutator: str, reason_code: str
) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished = bundle / "polished"

    if mutator == "missing":
        (polished / "frame-3.png").unlink()
    elif mutator == "extra":
        shutil.copy(polished / "frame-0.png", polished / "frame-99.png")
    elif mutator == "misordered":
        (polished / "frame-0.png").rename(polished / "frame-9.png")
    elif mutator == "unreadable":
        (polished / "frame-1.png").write_bytes(b"not-a-png")
    elif mutator == "wrong_mode":
        with Image.open(polished / "frame-1.png") as image:
            image.convert("RGB").save(polished / "frame-1.png")
    elif mutator == "wrong_size":
        Image.new("RGBA", (15, 24), (0, 0, 0, 0)).save(polished / "frame-2.png")
    elif mutator == "non_binary_alpha":
        _set_alpha(polished / "frame-0.png", 1, 1, 128)

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == reason_code
    assert not list((bundle / "reports").glob("*.json"))


def test_alpha_mask_edit_fails_structurally(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_alpha(polished, x, y, 0)

    result = _check_bundle(bundle)
    assert result.structural.pass_ is False
    assert result.structural.outcome == "FAIL"
    assert any(v.code == "alpha_mismatch" for v in result.structural.violations)


def test_new_opaque_color_fails_structurally(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished = bundle / "polished" / "frame-1.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, (3, 99, 200))

    result = _check_bundle(bundle)
    assert result.structural.pass_ is False
    assert any(v.code == "palette_violation" for v in result.structural.violations)


def test_master_palette_color_outside_draft_union_passes_structural_layer(
    tmp_path: Path,
) -> None:
    from pipeline.palette_quantize import load_master_palette

    bundle = _init_passing_bundle(tmp_path)
    palette = load_master_palette(ROOT / "assets" / "palettes" / "first-room.json")
    master_only = palette.role_colors["cyan-crystal"][0]
    polished = bundle / "polished" / "frame-0.png"
    x, y = _first_opaque_xy(polished)
    _set_opaque_rgb(polished, x, y, master_only)

    result = _check_bundle(bundle)
    assert result.structural.pass_ is True


def test_reused_draft_palette_color_passes_structural_layer(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    draft_union: set[tuple[int, int, int]] = set()
    for index in range(FRAME_COUNT):
        with Image.open(bundle / "draft" / f"frame-{index}.png") as image:
            rgba = image.convert("RGBA")
            pixels = rgba.load()
            assert pixels is not None
            for y in range(LOGICAL_SIZE[1]):
                for x in range(LOGICAL_SIZE[0]):
                    r, g, b, a = pixels[x, y]
                    if a == 255:
                        draft_union.add((r, g, b))

    polished = bundle / "polished" / "frame-0.png"
    with Image.open(polished) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        for y in range(LOGICAL_SIZE[1]):
            for x in range(LOGICAL_SIZE[0]):
                _, _, _, a = pixels[x, y]
                if a == 0:
                    palette_color = next(iter(draft_union))
                    pixels[x, y] = (*palette_color, 255)
                    break
            else:
                continue
            break
        image.save(polished)

    result = _check_bundle(bundle)
    assert result.structural.pass_ is True


def test_visible_cell_delta_order_and_counts(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    polished0 = bundle / "polished" / "frame-0.png"
    polished2 = bundle / "polished" / "frame-2.png"
    x0, y0 = _first_opaque_xy(polished0)
    x2, y2 = _first_opaque_xy(polished2)
    _set_opaque_rgb(polished0, x0, y0, (11, 22, 33))
    _set_opaque_rgb(polished2, x2, y2, (44, 55, 66))

    # transparent RGB-only change must not appear in delta
    with Image.open(polished0) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        for y in range(LOGICAL_SIZE[1]):
            for x in range(LOGICAL_SIZE[0]):
                _, _, _, a = pixels[x, y]
                if a == 0:
                    pixels[x, y] = (99, 88, 77, 0)
                    break
            else:
                continue
            break
        image.save(polished0)

    result = _check_bundle(bundle)
    edits = result.delta.edits
    assert [(e.frame_index, e.x, e.y) for e in edits] == [(0, x0, y0), (2, x2, y2)]
    assert result.delta.per_frame_counts == (1, 0, 1, 0)
    assert result.delta.total_edits == 2


def test_zero_edit_real_bundle_passes_coherence(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = _check_bundle(bundle)
    assert result.delta.total_edits == 0
    assert result.coherence["outcome"] == "PASS"
    assert result.outcome == "PASS"


def test_synthetic_recolour_reaches_coherence_split(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    frames = adversarial.real_frames("idle")
    mutated = adversarial.recolour(frames)
    polished_dir = bundle / "polished"
    for index in range(FRAME_COUNT):
        S.export_frames([mutated[index]], polished_dir, "swap", frame_w=16, frame_h=24)
        (polished_dir / "swap-f0.png").replace(polished_dir / f"frame-{index}.png")

    result = _check_bundle(bundle)
    assert result.coherence["outcome"] == "FAIL"
    assert result.coherence["gate_outcomes"]["palette_drift_pass"]["outcome"] == "FAIL"
    assert result.outcome == "FAIL"


def test_check_is_read_only(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    before = _bundle_tree(bundle)
    _check_bundle(bundle)
    assert _bundle_tree(bundle) == before


def test_existing_v1_idle_bundle_remains_check_compatible(tmp_path: Path) -> None:
    bundle = tmp_path / "dwarf-idle"
    shutil.copytree(DWARF_IDLE_BUNDLE, bundle)
    result = _check_bundle(bundle)
    assert result.outcome == "PASS"
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert manifest["schema"] == BUNDLE_SCHEMA_LEGACY_1


def _write_attempt_ledger(bundle: Path, attempts: list[dict[str, object]]) -> None:
    ledger_path = bundle / "provider" / "attempts.json"
    ledger_path.write_text(
        json.dumps({"schema": ATTEMPT_LEDGER_SCHEMA, "attempts": attempts}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["attempt_ledger"]["sha256"] = sha256_file(ledger_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def test_valid_sequential_attempt_ledger_passes_check(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="rejected", rejection_reason="palette_drift")
    accepted, provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS)
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=accepted["attempt_id"],
        predecessor_attempt_id=accepted["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
    assert _check_bundle(bundle).outcome == "PASS"
    ledger = json.loads((bundle / "provider" / "attempts.json").read_text())
    assert len(ledger["attempts"]) == 2


def test_rejected_attempt_ledger_with_identity_lock_near_miss_detail_passes(
    tmp_path: Path,
) -> None:
    store_root = tmp_path / "acquisition-controls"
    rejected, rejected_provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="rejected", rejection_reason="identity_lock")
    accepted, provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS)
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=accepted["attempt_id"],
        predecessor_attempt_id=accepted["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
    provenance = json.loads(provenance_path.read_text())
    _write_attempt_ledger(
        bundle,
        [
            {
                "attempt_id": rejected["attempt_id"],
                "predecessor_attempt_id": None,
                "outcome": "rejected",
                "rejection_reason": "identity_lock",
                "rejection_detail": {
                    "schema": "identity-lock-near-miss/0",
                    "primary_reason_code": "identity_lock_near_miss",
                    "frame_index": 2,
                    "kind": "check",
                    "id": "upper_body",
                    "occupancy_difference": 0.22,
                    "max_occupancy_difference": 0.20,
                    "occupancy_margin": -0.02,
                },
                "prompt_sha256": provenance["prompt_sha256"],
                "raw_sha256": rejected["raw_sha256"],
                "selected": False,
            },
            {
                "attempt_id": accepted["attempt_id"],
                "predecessor_attempt_id": rejected["attempt_id"],
                "outcome": "accepted",
                "rejection_reason": None,
                "prompt_sha256": provenance["prompt_sha256"],
                "raw_sha256": provenance["raw_sha256"],
                "selected": True,
            },
        ],
    )
    assert _check_bundle(bundle).outcome == "PASS"


@pytest.mark.parametrize(
    ("rejection_detail", "reason_code"),
    [
        ({"schema": "identity-lock-near-miss/0"}, "invalid_attempt_ledger"),
        ({"primary_reason_code": "identity_lock"}, "invalid_attempt_ledger"),
        ("not-an-object", "invalid_attempt_ledger"),
    ],
)
def test_malformed_rejection_detail_fails_closed(
    tmp_path: Path,
    rejection_detail: object,
    reason_code: str,
) -> None:
    store_root = tmp_path / "acquisition-controls"
    rejected, rejected_provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="rejected", rejection_reason="identity_lock")
    accepted, provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS)
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=accepted["attempt_id"],
        predecessor_attempt_id=accepted["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
    provenance = json.loads(provenance_path.read_text())
    _write_attempt_ledger(
        bundle,
        [
            {
                "attempt_id": rejected["attempt_id"],
                "predecessor_attempt_id": None,
                "outcome": "rejected",
                "rejection_reason": "identity_lock",
                "rejection_detail": rejection_detail,
                "prompt_sha256": provenance["prompt_sha256"],
                "raw_sha256": rejected["raw_sha256"],
                "selected": False,
            },
            {
                "attempt_id": accepted["attempt_id"],
                "predecessor_attempt_id": rejected["attempt_id"],
                "outcome": "accepted",
                "rejection_reason": None,
                "prompt_sha256": provenance["prompt_sha256"],
                "raw_sha256": provenance["raw_sha256"],
                "selected": True,
            },
        ],
    )

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == reason_code


def test_accepted_row_with_rejection_detail_fails_closed(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provenance = json.loads((bundle / "provider" / "source.source.json").read_text())
    _write_attempt_ledger(
        bundle,
        [
            {
                **{
                    "attempt_id": provenance["attempt_id"],
                    "predecessor_attempt_id": None,
                    "outcome": "accepted",
                    "rejection_reason": None,
                    "prompt_sha256": provenance["prompt_sha256"],
                    "raw_sha256": provenance["raw_sha256"],
                    "selected": True,
                },
                "rejection_detail": {
                    "schema": "identity-lock-near-miss/0",
                    "primary_reason_code": "identity_lock",
                },
            }
        ],
    )

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "invalid_attempt_ledger"


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        ("duplicate_id", "attempt_ledger_not_attested"),
        ("two_selected", "attempt_ledger_not_attested"),
        ("selected_not_final", "attempt_ledger_not_attested"),
        ("missing_predecessor", "attempt_ledger_not_attested"),
        ("cyclic", "attempt_ledger_not_attested"),
        ("prompt_mismatch", "attempt_ledger_not_attested"),
    ],
)
def test_invalid_attempt_ledger_fails_closed(
    tmp_path: Path,
    mutation: str,
    reason_code: str,
) -> None:
    bundle = _init_passing_bundle(tmp_path)
    provenance = json.loads((bundle / "provider" / "source.source.json").read_text())
    base_row = {
        "attempt_id": provenance["attempt_id"],
        "predecessor_attempt_id": None,
        "outcome": "accepted",
        "rejection_reason": None,
        "prompt_sha256": provenance["prompt_sha256"],
        "raw_sha256": provenance["raw_sha256"],
        "selected": True,
    }
    attempts: list[dict[str, object]] = [dict(base_row)]

    if mutation == "duplicate_id":
        attempts = [dict(base_row), dict(base_row)]
        attempts[1]["selected"] = False
        attempts[1]["outcome"] = "rejected"
        attempts[1]["rejection_reason"] = "palette_drift"
    elif mutation == "two_selected":
        attempts = [
            {
                **base_row,
                "attempt_id": "test--001",
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
                "selected": True,
            },
            {
                **base_row,
                "attempt_id": "test--002",
                "predecessor_attempt_id": "test--001",
                "selected": True,
            },
        ]
    elif mutation == "selected_not_final":
        attempts = [
            {
                **base_row,
                "attempt_id": "test--001",
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
                "selected": False,
            },
            {
                **base_row,
                "attempt_id": "test--002",
                "predecessor_attempt_id": "test--001",
                "selected": False,
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
            },
        ]
    elif mutation == "missing_predecessor":
        attempts = [dict(base_row)]
        attempts[0]["predecessor_attempt_id"] = "missing--001"
    elif mutation == "cyclic":
        attempts = [
            {
                **base_row,
                "attempt_id": "test--001",
                "predecessor_attempt_id": "test--002",
                "outcome": "rejected",
                "rejection_reason": "palette_drift",
                "selected": False,
            },
            {
                **base_row,
                "attempt_id": "test--002",
                "predecessor_attempt_id": "test--001",
                "selected": True,
            },
        ]
    elif mutation == "prompt_mismatch":
        attempts = [dict(base_row)]
        attempts[0]["prompt_sha256"] = "b" * 64

    _write_attempt_ledger(bundle, attempts)

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == reason_code


def test_provenance_binding_rejects_path_escape(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["provenance"] = {
        "relative_path": "../outside.json",
        "sha256": sha256_file(outside),
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "provenance_path_escape"


def test_polish_profile_binding_rejects_path_escape(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    _init_bundle_polish(PASS_STRIP, "idle", bundle, tmp_path, polish_profile="dwarf-miner")
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    manifest = json.loads((bundle / "manifest.json").read_text())
    manifest["polish_profile"] = {
        **manifest["polish_profile"],
        "relative_path": "../outside.json",
        "sha256": sha256_file(outside),
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "profile_path_escape"


def _distinct_rgba_states(path: Path) -> set[tuple[int, int, int, int]]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        pixels = rgba.load()
        assert pixels is not None
        width, height = rgba.size
        return {pixels[x, y] for y in range(height) for x in range(width)}


def _silhouette_artifacts_payload(result) -> dict[str, object]:
    assert result.silhouette_artifacts is not None
    return {
        "strip": {
            "relative_path": result.silhouette_artifacts.strip_relative_path,
            "sha256": result.silhouette_artifacts.strip_sha256,
        },
        "gif": {
            "relative_path": result.silhouette_artifacts.gif_relative_path,
            "sha256": result.silhouette_artifacts.gif_sha256,
        },
    }


def test_check_emits_two_colour_silhouette_strip_and_gif_for_dwarf_idle(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "dwarf-idle"
    shutil.copytree(DWARF_IDLE_BUNDLE, bundle)
    layout = json.loads((bundle / "manifest.json").read_text())["layout"]
    expected_strip_size = (
        layout["frame_count"] * layout["frame_w"]
        + (layout["frame_count"] - 1) * layout["gutter"],
        layout["frame_h"],
    )
    reports = bundle / "reports"
    existing_report_hashes = {
        path.name: sha256_file(path) for path in reports.glob("*.json")
    }

    result = _check_bundle(bundle)

    strip_path = bundle / "reports" / "silhouette-strip.png"
    gif_path = bundle / "reports" / "silhouette.gif"
    assert strip_path.is_file()
    assert gif_path.is_file()
    with Image.open(strip_path) as strip:
        assert strip.size == expected_strip_size
    with Image.open(gif_path) as gif:
        assert gif.size == (layout["frame_w"], layout["frame_h"])
        assert getattr(gif, "n_frames", 1) == FRAME_COUNT
    assert _distinct_rgba_states(strip_path) == {(0, 0, 0, 0), (0, 0, 0, 255)}
    assert len(_distinct_rgba_states(gif_path)) == 2
    for name, digest in existing_report_hashes.items():
        assert sha256_file(reports / name) == digest
    payload = _silhouette_artifacts_payload(result)
    assert payload["strip"]["relative_path"] == "reports/silhouette-strip.png"
    assert payload["gif"]["relative_path"] == "reports/silhouette.gif"
    assert payload["strip"]["sha256"] == sha256_file(strip_path)
    assert payload["gif"]["sha256"] == sha256_file(gif_path)
    policy = FIRST_ROOM_ANIMATION_POLICY["dwarf-idle"]
    with Image.open(gif_path) as gif:
        frame_durations = []
        for index in range(gif.n_frames):
            gif.seek(index)
            frame_durations.append(gif.info["duration"])
    assert frame_durations == policy["durations_ms"]


def test_check_silhouette_artifacts_are_deterministic(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    first = _check_bundle(bundle)
    first_strip = (bundle / "reports" / "silhouette-strip.png").read_bytes()
    first_gif = (bundle / "reports" / "silhouette.gif").read_bytes()
    second = _check_bundle(bundle)
    assert sha256_bytes(first_strip) == second.silhouette_artifacts.strip_sha256
    assert sha256_bytes(first_gif) == second.silhouette_artifacts.gif_sha256
    assert first_strip == (bundle / "reports" / "silhouette-strip.png").read_bytes()
    assert first_gif == (bundle / "reports" / "silhouette.gif").read_bytes()


def test_check_silhouette_report_paths_and_hashes_match_disk(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    result = _check_bundle(bundle)
    payload = _silhouette_artifacts_payload(result)
    strip_path = bundle / str(payload["strip"]["relative_path"])
    gif_path = bundle / str(payload["gif"]["relative_path"])
    assert payload["strip"]["sha256"] == sha256_file(strip_path)
    assert payload["gif"]["sha256"] == sha256_file(gif_path)


def test_check_silhouette_emission_does_not_change_gate_outcomes(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    baseline = _check_bundle(bundle)
    follow_up = _check_bundle(bundle)
    assert follow_up.outcome == baseline.outcome
    assert follow_up.coherence["gate_outcomes"] == baseline.coherence["gate_outcomes"]


def test_check_rejects_hand_edited_attempt_ledger(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="rejected", rejection_reason="palette_drift")
    accepted, provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS)
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=accepted["attempt_id"],
        predecessor_attempt_id=accepted["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
    ledger = json.loads((bundle / "provider" / "attempts.json").read_text())
    del ledger["attempts"][0]
    _write_attempt_ledger(bundle, ledger["attempts"])
    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "attempt_ledger_not_attested"


def test_check_rejects_predecessor_rewrite_not_in_store(tmp_path: Path) -> None:
    store_root = tmp_path / "acquisition-controls"
    record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS, outcome="rejected", rejection_reason="palette_drift")
    accepted, provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS)
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=accepted["attempt_id"],
        predecessor_attempt_id=accepted["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
    ledger = json.loads((bundle / "provider" / "attempts.json").read_text())
    ledger["attempts"][-1]["predecessor_attempt_id"] = "dwarf-swing--002"
    _write_attempt_ledger(bundle, ledger["attempts"])
    with pytest.raises(InvalidBundleError) as exc:
        _check_bundle(bundle)
    assert exc.value.reason_code == "attempt_ledger_not_attested"


def test_legacy_allowlist_drops_when_provider_digest_changes(tmp_path: Path) -> None:
    bundle = _init_passing_bundle(tmp_path)
    store_root = tmp_path / "acquisition-controls"
    provider_path = bundle / "provider" / "source.png"
    shutil.copy2(WALK_STRIP, provider_path)
    new_sha = sha256_file(provider_path)
    provenance_path = bundle / "provider" / "source.source.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["raw_sha256"] = new_sha
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    ledger_path = bundle / "provider" / "attempts.json"
    ledger = json.loads(ledger_path.read_text())
    for row in ledger["attempts"]:
        if row.get("selected"):
            row["raw_sha256"] = new_sha
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["provider"]["sha256"] = new_sha
    manifest["provenance"]["sha256"] = sha256_file(provenance_path)
    manifest["attempt_ledger"]["sha256"] = sha256_file(ledger_path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(store_root)

    with patch.dict("os.environ", acquisition_store_env(store_root)):
        with pytest.raises(InvalidBundleError) as exc:
            _check_bundle(bundle)
    assert exc.value.reason_code == "attempt_not_registered"


def test_legacy_allowlist_grandfathers_checked_in_bundles(tmp_path: Path) -> None:
    allowlist = json.loads(
        (ROOT / "acquisition-controls" / "legacy-bundles.json").read_text()
    )
    specification_ids = {entry["specification_id"] for entry in allowlist["bundles"]}
    assert "first-room/dwarf/swing" not in specification_ids

    idle_bundle = tmp_path / "idle"
    shutil.copytree(DWARF_IDLE_BUNDLE, idle_bundle)
    idle_result = polish_check_bundle(idle_bundle)
    assert idle_result.attestation is not None
    assert idle_result.attestation.state == "legacy"

    bundle = _init_passing_bundle(tmp_path)
    shutil.rmtree(tmp_path / "acquisition-controls")
    with patch.dict("os.environ", acquisition_store_env(tmp_path / "acquisition-controls")):
        with pytest.raises(InvalidBundleError) as exc:
            _check_bundle(bundle)
    assert exc.value.reason_code == "attempt_not_registered"


def test_attestation_report_payloads(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store_root = tmp_path / "acquisition-controls"
    row, provider = record_store_attempt(store_root, PASS_STRIP, "test/idle", repo_root=tmp_path, **_IDLE_STORE_ATTEMPT_KWARGS)
    provenance_path = tmp_path / "provenance.json"
    _write_animation_provenance(
        provider,
        provenance_path,
        motion_class="idle",
        attempt_id=row["attempt_id"],
        predecessor_attempt_id=row["predecessor_attempt_id"],
    )
    bundle = tmp_path / "bundle"
    with patch.dict("os.environ", acquisition_store_env(store_root)):
        initialize_bundle(provider, "idle", bundle, provenance_sidecar=provenance_path)
        result = _check_bundle(bundle)
    assert result.attestation is not None
    assert result.attestation.state == "attested"
    assert result.attestation.attempt_id == row["attempt_id"]

    report_path = _finalize_bundle(bundle)
    report = json.loads(report_path.read_text())
    assert report["attestation"]["state"] == "attested"
    assert report["attestation"]["attempt_id"] == row["attempt_id"]
    assert report["attestation"]["store_path"] == "attempts.jsonl"

    with patch.dict("os.environ", acquisition_store_env(store_root)):
        code = final_polish_cli_main(["check", str(bundle), "--summary-json"])
    assert code == 0
    attested_summary = json.loads(capsys.readouterr().out)
    assert attested_summary["attestation"]["state"] == "attested"

    idle_bundle = tmp_path / "legacy-idle"
    shutil.copytree(DWARF_IDLE_BUNDLE, idle_bundle)
    legacy_result = polish_check_bundle(idle_bundle)
    assert legacy_result.attestation is not None
    assert legacy_result.attestation.state == "legacy"

    with patch.dict("os.environ", {}, clear=False):
        code = final_polish_cli_main(["check", str(idle_bundle), "--summary-json"])
    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["attestation"]["state"] == "legacy"
