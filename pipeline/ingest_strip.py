"""CLI: gate a provider strip and export per-frame PNGs on pass."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from pipeline.strip import (
    DEFAULT_LAYOUT,
    MIN_GRID_SCORE,
    StripLayout,
    coherence_split,
    export_frames,
    recover_strip_cells,
    slice_frames_pitch,
)


def _provider_layout(layout: StripLayout) -> StripLayout:
    return StripLayout(
        frame_w=layout.frame_w,
        frame_h=layout.frame_h,
        frame_count=layout.frame_count,
        gutter=layout.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _gate_status(
    coherence: dict[str, Any],
    gate_key: str,
    *,
    inapplicable_key: str | None = None,
    reason_key: str | None = None,
    budget_key: str | None = None,
) -> dict[str, Any]:
    value = coherence.get(gate_key)
    budgets = coherence.get("budgets", {})
    if inapplicable_key and coherence.get(inapplicable_key):
        return {
            "status": "inapplicable",
            "value": value,
            "reason": coherence.get(reason_key),
        }
    if value is None and budget_key and budgets.get(budget_key) is None:
        return {
            "status": "inapplicable",
            "value": None,
            "reason": f"{budget_key} budget is None for this motion class",
        }
    if value is None:
        return {"status": "inapplicable", "value": None, "reason": None}
    return {"status": "pass" if value else "fail", "value": value}


def _format_gate_line(label: str, status: dict[str, Any]) -> str:
    state = status["status"]
    if state == "inapplicable":
        reason = status.get("reason")
        detail = f"inapplicable — {reason}" if reason else "inapplicable"
        return f"  {label}: {detail}"
    verdict = "pass" if state == "pass" else "FAIL"
    return f"  {label}: {verdict}"


def _format_report(
    source: str,
    layout: StripLayout,
    recovered: dict[str, Any],
    slice_meta: dict[str, Any],
    coherence: dict[str, Any],
    pass_: bool,
) -> str:
    lines: list[str] = []
    lines.append(f"Source  {source}")
    lines.append(
        f"Layout  {layout.frame_count}×{layout.frame_w}×{layout.frame_h}  "
        f"gutter={layout.gutter}  strip_w={layout.strip_width()}"
    )
    lines.append(
        f"Recovered  grid {recovered['grid']}  expected {recovered['expected_grid']}  "
        f"pitch x={recovered['pitch_x']['score']:.3f} y={recovered['pitch_y']['score']:.3f}"
    )
    lines.append(
        f"Slice  raster_match={slice_meta.get('raster_match')}  "
        f"shape_match={slice_meta.get('shape_match')}  "
        f"grid={slice_meta.get('grid')} expected_raster={slice_meta.get('expected_raster')}"
    )
    lines.append("Coherence")
    if "reason" in coherence and "silhouette_adjacent" not in coherence:
        lines.append(f"  reason: {coherence['reason']}")
    else:
        silhouette = _gate_status(
            coherence,
            "silhouette_budget",
            budget_key="silhouette",
        )
        lines.append(_format_gate_line("max_silhouette", silhouette))
        lines.append(
            _format_gate_line(
                "displacement_pass",
                _gate_status(
                    coherence,
                    "displacement_pass",
                    inapplicable_key="displacement_inapplicable",
                    reason_key="displacement_reason",
                ),
            )
        )
        for key in (
            "dimension_parity",
            "baseline_row_stable",
            "min_pair_cohort_pass",
            "loop_closure_pass",
            "palette_drift_pass",
        ):
            if key not in coherence:
                continue
            gate_value = coherence[key]
            if gate_value is None:
                lines.append(f"  {key}: inapplicable")
            else:
                lines.append(f"  {key}: {'pass' if gate_value else 'FAIL'}")
        for row in coherence.get("silhouette_adjacent", []):
            lines.append(
                f"  silhouette {row['pair']}: "
                f"changed={row['changed_cells']}/{row['union_opaque']} "
                f"({row['frac']:.1%})"
            )
        for row in coherence.get("palette_drift", []):
            lines.append(f"  palette drift {row['pair']}: {row['tv']:.1%}")
        loop = coherence.get("loop_closure")
        if loop:
            loop_pass = loop.get("pass")
            pass_label = loop_pass if loop_pass is not None else "n/a"
            lines.append(
                f"  loop {loop['pair']}: "
                f"changed={loop['changed_cells']}/{loop['union_opaque']} "
                f"({loop['frac']:.1%}) pass={pass_label}"
            )
    lines.append("")
    lines.append(f"Overall  {'PASS' if pass_ else 'FAIL'}")
    return "\n".join(lines)


def _json_payload(
    source: str,
    layout: StripLayout,
    recovered: dict[str, Any],
    slice_meta: dict[str, Any],
    coherence: dict[str, Any],
    pass_: bool,
    exported: list[pathlib.Path] | None = None,
) -> dict[str, Any]:
    silhouette = _gate_status(coherence, "silhouette_budget", budget_key="silhouette")
    displacement = _gate_status(
        coherence,
        "displacement_pass",
        inapplicable_key="displacement_inapplicable",
        reason_key="displacement_reason",
    )
    payload: dict[str, Any] = {
        "pass": pass_,
        "source": source,
        "layout": {
            "frame_w": layout.frame_w,
            "frame_h": layout.frame_h,
            "frame_count": layout.frame_count,
            "gutter": layout.gutter,
            "strip_width": layout.strip_width(),
        },
        "recovered": recovered,
        "slice": slice_meta,
        "coherence": coherence,
        "max_silhouette": silhouette,
        "displacement_pass": displacement,
    }
    if exported is not None:
        payload["exported_frames"] = [str(p) for p in exported]
    return payload


def ingest(
    raw_path: pathlib.Path,
    layout: StripLayout,
    *,
    motion_class: str,
) -> tuple[
    list[list[list[tuple[int, int, int] | None]]] | None,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    bool,
]:
    probe = _provider_layout(layout)
    cells, recovered = recover_strip_cells(raw_path, probe)
    frames, slice_meta = slice_frames_pitch(cells, frame_count=layout.frame_count)
    if frames is None:
        coherence = {
            "pass": False,
            "reason": slice_meta.get("reason", "auto-slice failed"),
            "slice": slice_meta,
        }
    else:
        coherence = coherence_split(frames, motion_class=motion_class)

    pitch_ok = (
        recovered["pitch_x"]["score"] >= MIN_GRID_SCORE
        or recovered["pitch_y"]["score"] >= MIN_GRID_SCORE
    )
    pass_ = pitch_ok and coherence.get("pass", False)
    return frames, recovered, slice_meta, coherence, pass_


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate a provider strip and export frames on pass.")
    parser.add_argument("png", type=pathlib.Path, help="Provider strip PNG")
    parser.add_argument("--motion-class", required=True, help="Motion class for gating")
    parser.add_argument("--out", type=pathlib.Path, help="Output directory for frame PNGs")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")
    args = parser.parse_args(argv)

    layout = _provider_layout(DEFAULT_LAYOUT)
    source = str(args.png.resolve())

    try:
        frames, recovered, slice_meta, coherence, pass_ = ingest(
            args.png,
            layout,
            motion_class=args.motion_class,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    exported: list[pathlib.Path] | None = None
    if pass_ and args.out is not None:
        if frames is not None:
            stem = args.png.stem
            exported = export_frames(frames, args.out, stem)

    if args.json:
        print(
            json.dumps(
                _json_payload(
                    source,
                    layout,
                    recovered,
                    slice_meta,
                    coherence,
                    pass_,
                    exported,
                ),
                separators=(",", ":"),
            )
        )
    else:
        print(
            _format_report(source, layout, recovered, slice_meta, coherence, pass_)
        )

    return 0 if pass_ else 1


if __name__ == "__main__":
    raise SystemExit(main())
