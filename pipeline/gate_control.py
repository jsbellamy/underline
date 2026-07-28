"""Production Gate-control scorer — measurement-only isolation verdicts (#64).

Scores one provider Strip against the Acceptance-profile matrix and emits an
immutable Measurement-run record. Does not mutate Manifest, Promotions, or
Attempt ledgers; persistence is opt-in via :func:`persist_measurement_run`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from typing import Any, Mapping

from PIL import Image, ImageDraw

from pipeline import canonical
from pipeline import strip as S
from pipeline.gate_evidence import (
    EvidenceError,
    load_acceptance_profiles,
    load_manifest,
    load_measurement,
    write_json_immutable,
)
from pipeline.numeric_policy import NUMERIC_POLICY

GATE_CONFIG_DIGEST_LEN = 16  # stored width of gate_config_digest across committed Measurement runs

MEASUREMENT_SCHEMA = "gate-control-measurement/1"

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

GATE_ORDER = (
    "dimension_parity",
    "baseline_row_stable",
    "silhouette_budget",
    "displacement_pass",
    "loop_closure_pass",
    "min_pair_cohort_pass",
    "palette_drift_pass",
)

STRUCTURAL_GATES = frozenset({"dimension_parity", "baseline_row_stable"})

METRIC_OF = {
    "silhouette_budget": ("silhouette_adjacent_max", "silhouette"),
    "loop_closure_pass": (None, "loop"),
    "min_pair_cohort_pass": (None, "min_pair"),
    "palette_drift_pass": ("worst_palette_drift", "palette_drift"),
}

RETRY_INTENT = {
    "STRUCTURAL_RECOVERY_FAILED": "restate the grid/gutter constraint in the prompt",
    "GATE_UNDECIDABLE": "change the motion so alignment is well-posed",
    "TARGET_DEFECT_TOO_WEAK": "amplify the targeted defect",
    "COLLATERAL_GATE_FAILED": "hold the collateral dimension fixed",
}


class SpecificationError(ValueError):
    """The Gate-control specification is invalid. No Measurement run is written."""


def gate_controls_root(repo_root: pathlib.Path | None = None) -> pathlib.Path:
    root = repo_root or REPO_ROOT
    return pathlib.Path(
        os.environ.get("UNDERLINE_GATE_CONTROLS_ROOT", root / "gate-controls")
    )


def corpus_layout() -> S.StripLayout:
    return S.StripLayout(
        frame_w=S.DEFAULT_LAYOUT.frame_w,
        frame_h=S.DEFAULT_LAYOUT.frame_h,
        frame_count=S.DEFAULT_LAYOUT.frame_count,
        gutter=S.DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def applicable_gates(
    motion_class: str,
    *,
    profiles_path: pathlib.Path | None = None,
    repo_root: pathlib.Path | None = None,
) -> dict[str, str]:
    """Class-applicable Gates → why. Inapplicable Gates are omitted."""
    gc = gate_controls_root(repo_root)
    profiles = load_acceptance_profiles(profiles_path or gc / "acceptance-profiles.json")
    profile = profiles.profiles.get(motion_class)
    if profile is None:
        raise SpecificationError(f"unknown motion class {motion_class!r}")

    budget = S.MOTION_CLASSES[motion_class]
    gates: dict[str, str] = {
        "dimension_parity": "structural",
        "palette_drift_pass": "always",
    }
    baseline = profile.get("baseline_row_stable")
    if budget.grounded:
        if baseline is not None and baseline.status != "INAPPLICABLE":
            gates["baseline_row_stable"] = "grounded: true"
    else:
        disp = profile.get("displacement_pass")
        if disp is not None and disp.status != "INAPPLICABLE":
            gates["displacement_pass"] = "grounded: false"

    def _applicable(gate_name: str) -> bool:
        entry = profile.get(gate_name)
        return entry is None or entry.status != "INAPPLICABLE"

    if budget.max_silhouette is not None and _applicable("silhouette_budget"):
        gates["silhouette_budget"] = f"max_silhouette={budget.max_silhouette}"
    if budget.loops and budget.max_loop is not None and _applicable("loop_closure_pass"):
        gates["loop_closure_pass"] = f"max_loop={budget.max_loop}"
    if budget.loops and budget.max_min_pair is not None and _applicable(
        "min_pair_cohort_pass"
    ):
        gates["min_pair_cohort_pass"] = f"max_min_pair={budget.max_min_pair}"

    return {gate: gates[gate] for gate in GATE_ORDER if gate in gates}


def gate_config_hash(
    *,
    repo_root: pathlib.Path | None = None,
    profiles_path: pathlib.Path | None = None,
    manifest_path: pathlib.Path | None = None,
) -> str:
    """Bind Acceptance profiles, ACTIVE Promotion evidence, and numeric policy."""
    root = repo_root or REPO_ROOT
    gc = gate_controls_root(root)
    profiles = load_acceptance_profiles(profiles_path or gc / "acceptance-profiles.json")
    manifest = load_manifest(manifest_path or gc / "manifest.json")

    profile_projection: dict[str, dict[str, Any]] = {}
    for motion_class, gates in sorted(profiles.profiles.items()):
        profile_projection[motion_class] = {
            gate: {
                "status": entry.status,
                "budget": entry.budget,
                "hard_fail": entry.hard_fail,
                "active_promotion": entry.active_promotion,
            }
            for gate, entry in sorted(gates.items())
        }

    active_promotions: list[dict[str, str]] = []
    for promo in sorted(manifest.promotions, key=lambda item: item.id):
        if promo.status != "ACTIVE":
            continue
        measurement_path = root / promo.measurement_path
        measurement = load_measurement(measurement_path)
        active_promotions.append(
            {
                "id": promo.id,
                "specification_id": promo.specification_id,
                "attempt_id": promo.attempt_id,
                "measurement_raw_sha256": measurement.raw_sha256,
            }
        )

    payload = {
        "acceptance_profiles": profile_projection,
        "active_promotions": active_promotions,
        "numeric_policy": NUMERIC_POLICY,
    }
    digest = hashlib.sha256(canonical.packet_bytes(payload)).hexdigest()
    return digest[:GATE_CONFIG_DIGEST_LEN]


def _fraction_evidence(
    coh: Mapping[str, Any], gate: str
) -> tuple[int, int] | None:
    if gate == "silhouette_budget":
        adjacent = coh.get("silhouette_adjacent") or []
        if not adjacent:
            return None
        worst = max(adjacent, key=lambda row: row["frac"])
        return int(worst["changed_cells"]), int(worst["union_opaque"])
    if gate == "loop_closure_pass":
        loop = coh.get("loop_closure")
        if not loop:
            return None
        return int(loop["changed_cells"]), int(loop["union_opaque"])
    return None


def _tri_state_to_isolation(outcome: str) -> str:
    if outcome == "PASS":
        return "pass"
    if outcome in {"REVIEW", "FAIL"}:
        return "fail"
    raise ValueError(f"unknown tri-state outcome {outcome!r}")


def gate_row_from_coherence(
    coh: Mapping[str, Any],
    gate: str,
    applicable_because: str,
) -> dict[str, Any]:
    """Map one applicable Gate from a coherence_split dict to a Measurement row."""
    gate_outcomes = coh.get("gate_outcomes") or {}
    row: dict[str, Any] = {
        "applicable_because": applicable_because,
        "outcome": "undecidable",
        "metric": None,
        "budget": None,
        "reason": None,
    }

    if gate in gate_outcomes:
        record = gate_outcomes[gate]
        tri = record["outcome"]
        row["outcome"] = _tri_state_to_isolation(tri)
        row["acceptance_outcome"] = tri
        row["metric"] = record.get("metric")
        row["budget"] = record.get("budget")
        row["hard_fail"] = record.get("hard_fail")
        evidence = _fraction_evidence(coh, gate)
        if evidence is not None:
            row["numerator"], row["denominator"] = evidence
        return row

    if gate == "dimension_parity":
        value = coh.get("dimension_parity")
        row["outcome"] = "pass" if value else "fail"
        return row

    if gate == "baseline_row_stable":
        if coh.get("baseline_row_inapplicable"):
            row["reason"] = coh.get("baseline_row_reason")
            row["outcome"] = "undecidable"
            return row
        value = coh.get("baseline_row_stable")
        if value is None:
            row["outcome"] = "undecidable"
            return row
        row["outcome"] = "pass" if value else "fail"
        return row

    if gate == "displacement_pass":
        value = coh.get("displacement_pass")
        if value is None:
            row["outcome"] = "undecidable"
            row["reason"] = coh.get("displacement_reason")
            return row
        row["outcome"] = "pass" if value else "fail"
        row["reason"] = coh.get("displacement_reason")
        return row

    # Legacy boolean fallbacks when gate_outcomes omitted the Gate.
    value = coh.get(gate)
    if value is None:
        row["outcome"] = "undecidable"
        return row
    row["outcome"] = "pass" if value else "fail"
    metric_key = METRIC_OF.get(gate, (None, None))[0]
    if metric_key:
        row["metric"] = coh.get(metric_key)
    budget_key = METRIC_OF.get(gate, (None, None))[1]
    if budget_key:
        row["budget"] = (coh.get("budgets") or {}).get(budget_key)
    evidence = _fraction_evidence(coh, gate)
    if evidence is not None:
        row["numerator"], row["denominator"] = evidence
    return row


def classify_isolation(
    gates: Mapping[str, Mapping[str, Any]],
    target_gate: str,
) -> tuple[str, list[str], list[str]]:
    """Return isolation verdict, blockers, and caveats."""
    others_failed = [
        gate
        for gate, row in gates.items()
        if gate != target_gate and row["outcome"] == "fail"
    ]
    target = gates[target_gate]["outcome"]
    caveats = [
        f"{gate} is undecidable — this control does not evidence that dimension"
        for gate, row in gates.items()
        if gate != target_gate and row["outcome"] == "undecidable"
    ]

    blockers: list[str] = []
    if target == "undecidable":
        isolation = "INDETERMINATE"
        blockers.append(f"target gate {target_gate} is undecidable")
    elif target == "fail" and not others_failed:
        isolation = "ISOLATED"
    else:
        isolation = "NOT_ISOLATED"
        if target == "pass":
            blockers.append(f"target gate {target_gate} passes")
        blockers += [f"collateral failure: {gate}" for gate in others_failed]

    return isolation, blockers, caveats


def primary_failure(run: Mapping[str, Any]) -> dict[str, Any] | None:
    """Exactly one. Deterministic: structure, target undecidable, target weak, GATE_ORDER."""
    if run["isolation"] == "ISOLATED":
        return None
    structural = run["structural"]
    if not structural.get("recovered"):
        return {
            "code": "STRUCTURAL_RECOVERY_FAILED",
            "gate": None,
            "rationale": structural.get("reason") or "strip did not recover",
        }

    gates = run["gates"]
    target = run["target_gate"]
    if gates[target]["outcome"] == "undecidable":
        return {
            "code": "GATE_UNDECIDABLE",
            "gate": target,
            "rationale": gates[target].get("reason") or f"{target} returned None",
        }

    if gates[target]["outcome"] == "pass":
        metric = gates[target].get("metric")
        budget = gates[target].get("budget")
        return {
            "code": "TARGET_DEFECT_TOO_WEAK",
            "gate": target,
            "rationale": (
                f"{target} measured {metric} within budget {budget}"
            ),
        }

    collateral = [
        gate
        for gate in GATE_ORDER
        if gate != target and gates.get(gate, {}).get("outcome") == "fail"
    ]
    gate = collateral[0]
    return {
        "code": "COLLATERAL_GATE_FAILED",
        "gate": gate,
        "rationale": (
            f"{gate} measured {gates[gate]['metric']} over budget {gates[gate]['budget']}"
        ),
    }


def retry_action(run: Mapping[str, Any]) -> dict[str, Any] | None:
    pf = run.get("primary_failure")
    if pf is None:
        return None
    gates = run["gates"]
    action: dict[str, Any] = {
        "reason_code": pf["code"],
        "gate": pf["gate"],
        "intent": RETRY_INTENT[pf["code"]],
        "one_prompt_delta": True,
    }
    if not gates:
        return action
    if pf["code"] == "TARGET_DEFECT_TOO_WEAK":
        action["direction"] = "increase"
        action["metric_now"] = gates[pf["gate"]]["metric"]
        action["must_exceed"] = gates[pf["gate"]]["budget"]
    elif pf["code"] == "COLLATERAL_GATE_FAILED":
        action["direction"] = "decrease"
        action["metric_now"] = gates[pf["gate"]]["metric"]
        action["must_fall_below"] = gates[pf["gate"]]["budget"]
    return action


def _abort(
    run: dict[str, Any],
    code: str,
    rationale: str,
    *,
    recovered: bool | None,
) -> dict[str, Any]:
    out = {
        **run,
        "structural": {"recovered": recovered, "reason": rationale},
        "gates": {},
        "isolation": "INDETERMINATE",
        "blockers": [rationale],
        "primary_failure": {
            "code": code,
            "gate": run["target_gate"] if code == "SPEC_INVALID_TARGET" else None,
            "rationale": rationale,
        },
    }
    out["caveats"] = []
    out["retry_action"] = retry_action(out)
    return out


def measure(
    path: pathlib.Path,
    motion_class: str,
    target_gate: str,
    *,
    attempt_id: str | None = None,
    recorded_at: str | None = None,
    scorer_commit: str | None = None,
    repo_root: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Pure measurement: one Measurement run without persistence."""
    root = repo_root or REPO_ROOT
    applicable = applicable_gates(motion_class, repo_root=root)
    config_hash = gate_config_hash(repo_root=root)

    run: dict[str, Any] = {
        "schema": MEASUREMENT_SCHEMA,
        "attempt_id": attempt_id,
        "recorded_at": recorded_at,
        "scorer_commit": scorer_commit,
        "raw": str(path),
        "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scorer_gate_config_sha256": config_hash,
        "motion_class": motion_class,
        "target_gate": target_gate,
        "applicable_gates": list(applicable),
        "numeric_policy": NUMERIC_POLICY,
    }

    if target_gate not in applicable:
        raise SpecificationError(
            f"target gate {target_gate!r} is inapplicable to motion class {motion_class!r}; "
            f"applicable: {', '.join(applicable)}"
        )
    if target_gate in STRUCTURAL_GATES:
        raise SpecificationError(
            f"target gate {target_gate!r} is structural and can never be a target Gate"
        )

    try:
        result = S.ingest_strip_provider(path, corpus_layout(), motion_class=motion_class)
    except (ValueError, OSError) as error:
        return _abort(
            run,
            "STRUCTURAL_RECOVERY_FAILED",
            str(error)[:120],
            recovered=False,
        )

    coh = result.coherence
    if "silhouette_adjacent" not in coh:
        return _abort(
            run,
            "STRUCTURAL_RECOVERY_FAILED",
            coh.get("reason") or "auto-slice failed",
            recovered=False,
        )

    run["structural"] = {
        "recovered": True,
        "pitch_x_score": round(result.recovered["pitch_x"]["score"], 4),
        "pitch_y_score": round(result.recovered["pitch_y"]["score"], 4),
    }

    gates = {
        gate: gate_row_from_coherence(coh, gate, why)
        for gate, why in applicable.items()
    }
    run["gates"] = gates

    isolation, blockers, caveats = classify_isolation(gates, target_gate)
    run["isolation"] = isolation
    run["blockers"] = blockers
    run["caveats"] = caveats
    run["primary_failure"] = primary_failure(run)
    run["retry_action"] = retry_action(run)
    return run


def persist_measurement_run(path: pathlib.Path, run: Mapping[str, Any]) -> None:
    """Append one immutable Measurement run; refuse to overwrite."""
    write_json_immutable(path, run)


def git_commit(repo_root: pathlib.Path | None = None) -> str:
    root = repo_root or REPO_ROOT
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


# --- review composite (late visual evidence for Gate Review) -----------------

_COMPOSITE_SCALE = 6
_COMPOSITE_PAD = 8
_COMPOSITE_BAND = 11


def _composite_frames(path: pathlib.Path) -> list[list[list[Any]]] | None:
    return S.load_provider_frames(path, corpus_layout())


def _composite_quantized(frames: list[list[list[Any]]]) -> list[list[list[Any]]]:
    rgbs = S.collect_opaque_rgbs(frames)
    palette, _ = S.build_shared_palette(
        rgbs, max_colors=S.DEFAULT_MAX_PALETTE, merge_dist=S.PROVIDER_MERGE_DIST_RGB
    )
    if not palette:
        return frames
    return [
        [[None if rgb is None else S._nearest_rgb(rgb, palette) for rgb in row] for row in frame]
        for frame in frames
    ]


def _panel_silhouette(
    draw: ImageDraw.ImageDraw,
    frames: list[list[list[Any]]],
    run: Mapping[str, Any],
    dy: int,
    fw: int,
    fh: int,
    cell_w: int,
) -> None:
    half = max(1, _COMPOSITE_SCALE // 2)
    for i in range(len(frames) - 1):
        a, b = frames[i], frames[i + 1]
        x0 = _COMPOSITE_PAD + i * (cell_w + _COMPOSITE_PAD) + cell_w // 2
        for y in range(min(fh, len(a), len(b))):
            for x in range(min(fw, len(a[y]), len(b[y]))):
                oa, ob = a[y][x] is not None, b[y][x] is not None
                if oa != ob:
                    draw.rectangle(
                        [
                            x0 + x * half,
                            dy + y * half,
                            x0 + (x + 1) * half - 1,
                            dy + (y + 1) * half - 1,
                        ],
                        fill=(220, 60, 60),
                    )
                elif oa:
                    draw.point((x0 + x * half, dy + y * half), fill=(60, 60, 70))
        draw.text((x0, dy + fh * half + 2), f"{i}->{i+1}", fill=(150, 150, 160))


def _panel_palette(
    draw: ImageDraw.ImageDraw,
    frames: list[list[list[Any]]],
    run: Mapping[str, Any],
    dy: int,
    fw: int,
    fh: int,
    cell_w: int,
) -> None:
    bar_h = fh * max(1, _COMPOSITE_SCALE // 2)
    hists = [S.palette_histogram(f) for f in _composite_quantized(frames)]
    colours = sorted(
        {c for h in hists for c in h},
        key=lambda c: -sum(h.get(c, 0.0) for h in hists),
    )
    for i, hist in enumerate(hists):
        x0 = _COMPOSITE_PAD + i * (cell_w + _COMPOSITE_PAD)
        y = dy
        for colour in colours:
            share = hist.get(colour, 0.0)
            height = int(round(share * bar_h))
            if height:
                draw.rectangle(
                    [x0, y, x0 + cell_w - 1, y + height - 1],
                    fill=tuple(colour),
                )
                y += height
        draw.text((x0, dy + bar_h + 2), f"f{i} palette", fill=(150, 150, 160))


def _panel_displacement(
    draw: ImageDraw.ImageDraw,
    frames: list[list[list[Any]]],
    run: Mapping[str, Any],
    dy: int,
    fw: int,
    fh: int,
    cell_w: int,
) -> None:
    shifts = S.adjacent_transition_shifts(_composite_quantized(frames))
    for i, entry in enumerate(shifts):
        x0 = _COMPOSITE_PAD + i * (cell_w + _COMPOSITE_PAD)
        dx, dy_shift = entry["dx"], entry["dy"]
        draw.text((x0, dy), f"{entry['from']}->{entry['to']}", fill=(150, 150, 160))
        draw.text((x0, dy + _COMPOSITE_BAND), f"shift ({dx:+d},{dy_shift:+d})", fill=(220, 160, 60))
        cx, cy = x0 + cell_w // 2, dy + _COMPOSITE_BAND * 4
        draw.line([cx, cy, cx + dx * _COMPOSITE_SCALE, cy + dy_shift * _COMPOSITE_SCALE], fill=(220, 160, 60), width=2)
        draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(190, 190, 200))


_PANEL_FOR = {
    "silhouette_budget": _panel_silhouette,
    "loop_closure_pass": _panel_silhouette,
    "min_pair_cohort_pass": _panel_silhouette,
    "palette_drift_pass": _panel_palette,
    "displacement_pass": _panel_displacement,
    "baseline_row_stable": _panel_silhouette,
}


def _composite_band_lines(run: Mapping[str, Any]) -> list[str]:
    lines = [
        f"{run['isolation']}   target={run['target_gate']}   class={run['motion_class']}"
    ]
    for gate, row in run["gates"].items():
        mark = {"pass": "  ok ", "fail": " FAIL", "undecidable": " ?? "}[row["outcome"]]
        star = "*" if gate == run["target_gate"] else " "
        detail = (
            f"{row['metric']:.4f} vs budget {row['budget']}"
            if row["metric"] is not None and row["budget"] is not None
            else (row["reason"] or "")
        )
        lines.append(f"{star}{mark}  {gate:<22} {detail}")
    pf = run.get("primary_failure")
    lines.append(
        f"primary_failure: {pf['code'] if pf else 'none'}"
        + (f" ({pf['gate']})" if pf and pf.get("gate") else "")
    )
    lines += [f"caveat: {c}" for c in run.get("caveats", [])]
    lines.append(f"raw_sha256: {run['raw_sha256']}")
    return lines


def build_composite(
    path: pathlib.Path, run: Mapping[str, Any], out: pathlib.Path
) -> pathlib.Path:
    """Render one late, hash-bound Gate-review composite for a Measurement run."""
    raw_frames = _composite_frames(path)
    if raw_frames is None:
        raise ValueError("cannot composite a strip that did not slice")
    fw, fh = S.DEFAULT_LAYOUT.frame_w, S.DEFAULT_LAYOUT.frame_h
    frames = [
        S.canonicalize_frame(frame, frame_w=fw, frame_h=fh) for frame in raw_frames
    ]
    n = len(frames)
    cell_w, cell_h = fw * _COMPOSITE_SCALE, fh * _COMPOSITE_SCALE
    band_lines = _composite_band_lines(run)
    width = max(
        _COMPOSITE_PAD * 2 + n * cell_w + (n - 1) * _COMPOSITE_PAD,
        _COMPOSITE_PAD * 2 + max(len(line) for line in band_lines) * 6,
    )
    height = (
        _COMPOSITE_PAD * 4
        + cell_h
        + fh * max(1, _COMPOSITE_SCALE // 2)
        + _COMPOSITE_BAND * (len(band_lines) + 2)
    )

    image = Image.new("RGB", (width, height), (24, 24, 28))
    draw = ImageDraw.Draw(image)

    for i, frame in enumerate(frames):
        x0 = _COMPOSITE_PAD + i * (cell_w + _COMPOSITE_PAD)
        for y in range(min(fh, len(frame))):
            for x in range(min(fw, len(frame[y]))):
                rgb = frame[y][x]
                if rgb is not None:
                    draw.rectangle(
                        [
                            x0 + x * _COMPOSITE_SCALE,
                            _COMPOSITE_PAD + y * _COMPOSITE_SCALE,
                            x0 + (x + 1) * _COMPOSITE_SCALE - 1,
                            _COMPOSITE_PAD + (y + 1) * _COMPOSITE_SCALE - 1,
                        ],
                        fill=tuple(rgb),
                    )
        draw.text((x0, _COMPOSITE_PAD + cell_h + 2), f"f{i}", fill=(150, 150, 160))

    dy = _COMPOSITE_PAD * 2 + cell_h + _COMPOSITE_BAND
    panel = _PANEL_FOR.get(str(run["target_gate"]), _panel_silhouette)
    panel(draw, frames, run, dy, fw, fh, cell_w)

    ty = height - _COMPOSITE_BAND * (len(band_lines) + 1)
    verdict_colour = {
        "ISOLATED": (90, 200, 110),
        "NOT_ISOLATED": (230, 170, 60),
        "INDETERMINATE": (200, 80, 80),
    }[str(run["isolation"])]
    for i, line in enumerate(band_lines):
        draw.text(
            (_COMPOSITE_PAD, ty + i * _COMPOSITE_BAND),
            line,
            fill=verdict_colour if i == 0 else (190, 190, 200),
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("png", type=pathlib.Path)
    parser.add_argument("--motion-class", required=True)
    parser.add_argument("--target-gate", required=True, choices=GATE_ORDER)
    parser.add_argument("--attempt-id")
    parser.add_argument("--recorded-at")
    parser.add_argument("--scorer-commit")
    parser.add_argument("--out", type=pathlib.Path, help="append-only Measurement path")
    args = parser.parse_args(argv)

    path = args.png
    if not path.is_file():
        candidate = REPO_ROOT / "prototype" / "strip-coherence" / "inbox" / path.name
        if candidate.is_file():
            path = candidate

    try:
        run = measure(
            path,
            args.motion_class,
            args.target_gate,
            attempt_id=args.attempt_id,
            recorded_at=args.recorded_at or utc_now(),
            scorer_commit=args.scorer_commit or git_commit(),
        )
    except SpecificationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.out is not None:
        persist_measurement_run(args.out, run)

    print(json.dumps(run, indent=2))
    return 0 if run["isolation"] == "ISOLATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
