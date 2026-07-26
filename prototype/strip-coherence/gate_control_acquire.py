#!/usr/bin/env python3
"""Minimal Gate-control acquisition loop for wayfinder #21–#26.

Wraps gate_control.measure with #19 file layout: attempts ledger, provenance,
measurement reports, optional composite, and Promotion pointers. Does not run
full-repo verification — Promotion stays PENDING_VERIFICATION until CI (#30).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

# gate_control lives beside this script; import without package layout.
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))
import importlib.util

_spec = importlib.util.spec_from_file_location("gate_control", _HERE / "gate_control.py")
gc = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(gc)

ROOT = _HERE.parent.parent
GC_ROOT = ROOT / "gate-controls"
SCHEMA = "gate-control-acquisition/0"


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _read_manifest() -> dict:
    path = GC_ROOT / "manifest.json"
    if not path.exists():
        return {"schema": "gate-control-manifest/0", "specifications": [], "promotions": []}
    return json.loads(path.read_text())


def _write_manifest(manifest: dict) -> None:
    path = GC_ROOT / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def _append_attempt(row: dict) -> None:
    path = GC_ROOT / "attempts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _spec_id(motion_class: str, target_gate: str) -> str:
    return f"{motion_class}/{target_gate}"


def _attempt_id(spec: str, ordinal: int) -> str:
    return f"{spec.replace('/', '--')}--{ordinal:03d}"


def _count_attempts(spec_id: str) -> int:
    path = GC_ROOT / "attempts.jsonl"
    if not path.exists():
        return 0
    return sum(
        1 for line in path.read_text().splitlines()
        if json.loads(line).get("specification_id") == spec_id
    )


def record_attempt(
    png: pathlib.Path,
    motion_class: str,
    target_gate: str,
    *,
    prompt_path: pathlib.Path | None = None,
    prompt_delta: str | None = None,
    agent: str = "cursor-agent",
) -> dict:
    """Measure one candidate, write evidence files, append ledger row."""
    spec_id = _spec_id(motion_class, target_gate)
    ordinal = _count_attempts(spec_id) + 1
    attempt_id = _attempt_id(spec_id, ordinal)
    predecessor = _attempt_id(spec_id, ordinal - 1) if ordinal > 1 else None

    prompt_text = prompt_path.read_text() if prompt_path else ""
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()

    raw_dir = GC_ROOT / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_dest = raw_dir / f"{attempt_id}.png"
    shutil.copy2(png, raw_dest)

    provenance = {
        "schema": "gate-control-provenance/0",
        "specification_id": spec_id,
        "attempt_id": attempt_id,
        "generator": "cursor-image-gen",
        "prompt_text": prompt_text,
        "prompt_sha256": prompt_hash,
        "reference_image_sha256": [],
        "generated_at": _now(),
        "acquiring_agent": agent,
        "repository_commit": _git_commit(),
        "raw_path": str(raw_dest.relative_to(ROOT)),
        "raw_sha256": _sha256(raw_dest),
        "media_type": "image/png",
        "dimensions": list(__import__("PIL.Image").Image.open(raw_dest).size),
    }
    prov_path = GC_ROOT / "provenance" / f"{attempt_id}.json"
    prov_path.parent.mkdir(parents=True, exist_ok=True)
    prov_path.write_text(json.dumps(provenance, indent=2) + "\n")

    composite_path = GC_ROOT / "reviews" / attempt_id / "composite.png"
    try:
        run = gc.measure(raw_dest, motion_class, target_gate)
    except gc.SpecificationError as error:
        row = {
            "schema": SCHEMA,
            "attempt_id": attempt_id,
            "specification_id": spec_id,
            "ordinal": ordinal,
            "predecessor_attempt_id": predecessor,
            "recorded_at": _now(),
            "prompt_path": str(prompt_path) if prompt_path else None,
            "prompt_sha256": prompt_hash,
            "prompt_delta": prompt_delta,
            "acquiring_agent": agent,
            "artifact_state": "discarded",
            "isolation": "INDETERMINATE",
            "primary_failure": {"code": "SPEC_INVALID_TARGET", "gate": target_gate,
                                "rationale": str(error)},
            "promotion_blockers": [str(error)],
            "measurement_path": None,
            "provenance_path": str(prov_path.relative_to(ROOT)),
            "composite_path": None,
        }
        _append_attempt(row)
        return row

    report_dir = GC_ROOT / "reports" / attempt_id
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{_now().replace(':', '-')}.json"
    report_path.write_text(json.dumps(run, indent=2) + "\n")

    if run["structural"].get("recovered"):
        gc.build_composite(raw_dest, run, composite_path)

    isolation = run["isolation"]
    pf = run.get("primary_failure")
    blockers = list(run.get("blockers", []))
    if isolation != "ISOLATED":
        blockers.append("not ISOLATED")

    retained = isolation == "ISOLATED" or ordinal <= 3
    if not retained:
        raw_dest.unlink(missing_ok=True)

    row = {
        "schema": SCHEMA,
        "attempt_id": attempt_id,
        "specification_id": spec_id,
        "ordinal": ordinal,
        "predecessor_attempt_id": predecessor,
        "recorded_at": _now(),
        "prompt_path": str(prompt_path) if prompt_path else None,
        "prompt_sha256": prompt_hash,
        "prompt_delta": prompt_delta,
        "acquiring_agent": agent,
        "artifact_state": "retained" if retained else "discarded",
        "isolation": isolation,
        "primary_failure": pf,
        "promotion_blockers": blockers,
        "measurement_path": str(report_path.relative_to(ROOT)),
        "provenance_path": str(prov_path.relative_to(ROOT)),
        "composite_path": (str(composite_path.relative_to(ROOT))
                         if composite_path.exists() else None),
        "raw_sha256": run["raw_sha256"],
    }
    _append_attempt(row)
    return row


def promote_palette_07() -> dict:
    """Register existing inbox 07 as the promoted idle palette-drift control."""
    return promote_isolated(
        "idle",
        "palette_drift_pass",
        _HERE / "inbox" / "07-NEG-palette-drift.png",
        prompt_path=_HERE / "prompts" / "07-NEG-palette-drift.prompt.txt",
        prompt_delta="corpus negative — promoted from inbox",
        agent="corpus-seed",
    )


def promote_isolated(
    motion_class: str,
    target_gate: str,
    png: pathlib.Path,
    *,
    prompt_path: pathlib.Path | None = None,
    prompt_delta: str | None = None,
    agent: str = "cursor-agent",
    note: str = "visual review deferred to #27; full verification deferred to #30",
) -> dict:
    """Record one ISOLATED candidate and register a PENDING_VERIFICATION Promotion."""
    row = record_attempt(
        png,
        motion_class,
        target_gate,
        prompt_path=prompt_path,
        prompt_delta=prompt_delta,
        agent=agent,
    )
    if row["isolation"] != "ISOLATED":
        raise RuntimeError(
            f"{motion_class}/{target_gate} expected ISOLATED, got {row['isolation']}"
        )

    manifest = _read_manifest()
    spec_id = _spec_id(motion_class, target_gate)
    if not any(s["id"] == spec_id for s in manifest["specifications"]):
        manifest["specifications"].append({
            "id": spec_id,
            "motion_class": motion_class,
            "target_gate": target_gate,
        })
    promotion = {
        "id": f"promo--{spec_id.replace('/', '--')}",
        "specification_id": spec_id,
        "attempt_id": row["attempt_id"],
        "measurement_path": row["measurement_path"],
        "status": "PENDING_VERIFICATION",
        "recorded_at": _now(),
        "note": note,
    }
    manifest["promotions"].append(promotion)
    for spec in manifest["specifications"]:
        if spec["id"] == spec_id:
            spec["active_promotion"] = promotion["id"]
    _write_manifest(manifest)
    return promotion


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("png", type=pathlib.Path, nargs="?", help="candidate strip PNG")
    p.add_argument("--motion-class", default="idle")
    p.add_argument("--target-gate", required=False)
    p.add_argument("--prompt", type=pathlib.Path)
    p.add_argument("--prompt-delta", default=None)
    p.add_argument("--promote-07", action="store_true")
    p.add_argument("--promote", action="store_true",
                   help="record attempt and write PENDING_VERIFICATION Promotion")
    args = p.parse_args(argv)

    if args.promote_07:
        promo = promote_palette_07()
        print(json.dumps(promo, indent=2))
        return 0

    if not args.png or not args.target_gate:
        p.error("png and --target-gate required unless --promote-07")

    if args.promote:
        promo = promote_isolated(
            args.motion_class,
            args.target_gate,
            args.png,
            prompt_path=args.prompt,
            prompt_delta=args.prompt_delta,
        )
        print(json.dumps(promo, indent=2))
        return 0

    row = record_attempt(
        args.png,
        args.motion_class,
        args.target_gate,
        prompt_path=args.prompt,
        prompt_delta=args.prompt_delta,
    )
    print(json.dumps(row, indent=2))
    return 0 if row["isolation"] == "ISOLATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
