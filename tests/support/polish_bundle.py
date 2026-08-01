"""Prepared Attempt fixture for Polish Bundle tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

from PIL import Image

from pipeline.final_polish import PROVENANCE_SCHEMA, initialize_bundle
from pipeline.gate_evidence import sha256_bytes, sha256_file
from pipeline.identity_lock import build_identity_seed, magenta_pad_generation_source_png
from pipeline.strip import ingest_strip_provider, layout_for_motion_class, load_provider_frames
from tests.final_polish_harness import acquisition_store_env, record_store_attempt

ROOT = Path(__file__).resolve().parents[2]
INBOX = ROOT / "prototype" / "strip-coherence" / "inbox"
WALK_STRIP = INBOX / "05-miner-walk.png"
SWING_STRIP = INBOX / "06-miner-swing.png"
IDENTITY_PNG = ROOT / "assets" / "first-room" / "dwarf" / "identity.png"
IDENTITY_JSON = ROOT / "assets" / "first-room" / "dwarf" / "identity.json"
CANONICAL_IDENTITY_SHA = "7495a733c11be50fff2d2a16d5842d56d6a79cb7642da7a344bc699290f7c9c6"
_PROMPT_TEXT = "underline test provenance prompt"


@dataclass(frozen=True)
class PreparedAttempt:
    provider: Path
    provenance: Path
    identity_reference: Path | None
    edit_source: Path | None
    ingest_source: Path
    env: Mapping[str, str]


def prepare(
    provider: Path,
    motion_class: str,
    tmp_path: Path,
    *,
    polish_profile: str | None = None,
) -> PreparedAttempt:
    effective_provider = _effective_provider_path(
        provider,
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
    identity_reference: Path | None = None
    edit_source: Path | None = None
    record_kwargs: dict[str, Any] = {
        "motion_class": motion_class,
        "generation_mode": generation_mode,
        "acquiring_agent": "pytest",
        "prompt_text": _PROMPT_TEXT,
        "repo_root": tmp_path,
    }
    if generation_mode == "image-edit":
        padded_seed = _padded_edit_source_seed(tmp_path, motion_class)
        identity_reference = IDENTITY_PNG
        edit_source = padded_seed
        record_kwargs["reference_image_sha256"] = CANONICAL_IDENTITY_SHA
        record_kwargs["edit_source"] = padded_seed
    specification_id = f"test/{motion_class}"
    row, provider_for_init = record_store_attempt(
        store_root,
        effective_provider,
        specification_id,
        motion_class=motion_class,
        generation_mode=generation_mode,
        acquiring_agent="pytest",
        prompt_text=_PROMPT_TEXT,
        repo_root=tmp_path,
        reference_image_sha256=record_kwargs.get("reference_image_sha256"),
        edit_source=record_kwargs.get("edit_source"),
    )
    provenance_path = tmp_path / f"{effective_provider.stem}.source.json"
    provenance_kwargs: dict[str, object] = {
        "motion_class": motion_class,
        "generation_mode": generation_mode,
        "attempt_id": row["attempt_id"],
        "predecessor_attempt_id": row["predecessor_attempt_id"],
        "specification_id": specification_id,
    }
    if generation_mode == "image-edit":
        padded_seed = _padded_edit_source_seed(tmp_path, motion_class)
        provenance_kwargs.update(
            {
                "reference_image_sha256": [CANONICAL_IDENTITY_SHA],
                "edit_source_sha256": sha256_file(padded_seed),
            }
        )
    if polish_profile is not None:
        provenance_kwargs["fixture_polish_profile"] = polish_profile
    _write_animation_provenance(provider_for_init, provenance_path, **provenance_kwargs)
    ingest_source = (
        _dwarf_miner_ingest_source(provider, motion_class)
        if polish_profile == "dwarf-miner" and effective_provider != provider
        else effective_provider
    )
    return PreparedAttempt(
        provider=provider_for_init,
        provenance=provenance_path,
        identity_reference=identity_reference,
        edit_source=edit_source,
        ingest_source=ingest_source,
        env=acquisition_store_env(store_root),
    )


def init_bundle(attempt: PreparedAttempt, bundle: Path) -> None:
    motion_class = _motion_class(attempt)
    polish_profile = _polish_profile(attempt)
    probe_layout = layout_for_motion_class(motion_class, margin_cells=0)
    init_kwargs = {
        "provenance_sidecar": attempt.provenance,
        "polish_profile": polish_profile,
        "identity_reference": attempt.identity_reference,
        "edit_source": attempt.edit_source,
    }
    if attempt.ingest_source != attempt.provider:
        base_ingest = ingest_strip_provider(
            attempt.ingest_source,
            probe_layout,
            motion_class=motion_class,
        )
        base_frames = load_provider_frames(attempt.ingest_source, probe_layout)
        with (
            patch("pipeline.final_polish.ingest_strip_provider", return_value=base_ingest),
            patch(
                "pipeline.final_polish.load_provider_frames",
                return_value=base_frames,
            ),
            patch.dict("os.environ", attempt.env),
        ):
            initialize_bundle(
                attempt.provider,
                motion_class,
                bundle,
                **init_kwargs,
            )
        return
    with patch.dict("os.environ", attempt.env):
        initialize_bundle(
            attempt.provider,
            motion_class,
            bundle,
            **init_kwargs,
        )


def init_argv(
    attempt: PreparedAttempt,
    bundle: Path,
    *,
    json_mode: bool = False,
) -> list[str]:
    motion_class = _motion_class(attempt)
    polish_profile = _polish_profile(attempt)
    args = [
        "init",
        str(attempt.provider),
        "--motion-class",
        motion_class,
        "--out",
        str(bundle),
        "--provenance",
        str(attempt.provenance),
    ]
    if attempt.identity_reference is not None:
        args.extend(["--identity-reference", str(attempt.identity_reference)])
    if attempt.edit_source is not None:
        args.extend(["--edit-source", str(attempt.edit_source)])
    if polish_profile is not None:
        args.extend(["--polish-profile", polish_profile])
    if json_mode:
        args.append("--json")
    return args


def _provenance_record(attempt: PreparedAttempt) -> dict[str, object]:
    return json.loads(attempt.provenance.read_text(encoding="utf-8"))


def _motion_class(attempt: PreparedAttempt) -> str:
    return str(_provenance_record(attempt)["motion_class"])


def _polish_profile(attempt: PreparedAttempt) -> str | None:
    value = _provenance_record(attempt).get("fixture_polish_profile")
    return str(value) if value else None


def _provider_dimensions(provider_path: Path) -> list[int]:
    with Image.open(provider_path) as image:
        return [image.width, image.height]


def _item_geometry(*, motion_class: str) -> dict[str, int]:
    layout = layout_for_motion_class(motion_class, margin_cells=0)
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
    attempt_id: str = "test--001",
    predecessor_attempt_id: str | None = None,
    reference_image_sha256: list[str] | None = None,
    edit_source_sha256: str | None = None,
    prompt_text: str = _PROMPT_TEXT,
    **overrides: object,
) -> None:
    if reference_image_sha256 is None:
        reference_image_sha256 = []
    record: dict[str, object] = {
        "schema": PROVENANCE_SCHEMA,
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
        "item_geometry": _item_geometry(motion_class=motion_class),
    }
    record.update(overrides)
    provenance_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _padded_edit_source_seed(tmp_path: Path, motion_class: str) -> Path:
    out = tmp_path / (
        "swing-edit-source.png" if motion_class == "swing" else "padded-edit-source.png"
    )
    kwargs: dict[str, str] = {}
    if motion_class == "swing":
        kwargs["motion_class"] = "swing"
    build_identity_seed(IDENTITY_JSON, out, **kwargs)
    return out


def _identity_seed_pad_px() -> int:
    doc = json.loads(IDENTITY_JSON.read_text(encoding="utf-8"))
    return int(doc["seed_pad_px"])


def _padded_inbox_provider(
    inbox_strip: Path,
    tmp_path: Path,
    *,
    motion_class: str | None = None,
) -> Path:
    seed_pad_px = _identity_seed_pad_px()
    kwargs: dict[str, str] = {}
    if motion_class is not None:
        kwargs["motion_class"] = motion_class
    out = tmp_path / f"{inbox_strip.stem}-padded-provider.png"
    out.write_bytes(
        magenta_pad_generation_source_png(
            inbox_strip.read_bytes(),
            seed_pad_px,
            **kwargs,
        )
    )
    return out


def _walk_provider_on_edit_canvas(tmp_path: Path) -> Path:
    seed = _padded_edit_source_seed(tmp_path, "walk")
    out = tmp_path / "walk-on-edit-canvas.png"
    pad = _identity_seed_pad_px()
    with Image.open(seed) as canvas:
        base = canvas.copy()
        with Image.open(WALK_STRIP) as walk:
            base.paste(walk.convert("RGBA"), (pad, pad))
        base.save(out)
    return out


def _swing_padded_inbox_provider(tmp_path: Path) -> Path:
    return _padded_inbox_provider(SWING_STRIP, tmp_path, motion_class="swing")


def _swing_provider_on_edit_canvas(tmp_path: Path) -> Path:
    seed = _padded_edit_source_seed(tmp_path, "swing")
    inner = _padded_inbox_provider(SWING_STRIP, tmp_path, motion_class="swing")
    out = tmp_path / "swing-on-edit-canvas.png"
    pad = _identity_seed_pad_px()
    with Image.open(seed) as seed_image:
        canvas = seed_image.copy()
        with Image.open(inner) as inner_image:
            canvas.paste(inner_image.convert("RGBA"), (pad, pad))
        canvas.save(out)
    return out


def _effective_dwarf_miner_provider(
    provider_path: Path,
    tmp_path: Path,
    motion_class: str,
) -> Path:
    if motion_class == "walk" and provider_path == WALK_STRIP:
        return _walk_provider_on_edit_canvas(tmp_path)
    if motion_class == "swing" and provider_path == SWING_STRIP:
        return _swing_padded_inbox_provider(tmp_path)
    if motion_class == "swing" and provider_path.parent == tmp_path:
        stem = provider_path.stem
        if stem in {"swing-24-provider", "swing-on-edit-canvas"}:
            return _swing_provider_on_edit_canvas(tmp_path)
    return provider_path


def _dwarf_miner_ingest_source(
    provider_path: Path,
    motion_class: str,
) -> Path:
    if motion_class == "walk":
        return WALK_STRIP
    if provider_path.stem == "swing-24-provider":
        return provider_path
    return SWING_STRIP


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
