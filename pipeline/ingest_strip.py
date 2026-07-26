"""CLI: gate a provider strip and export per-frame PNGs on pass."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from pipeline.strip import (
    DEFAULT_LAYOUT,
    IngestResult,
    StripLayout,
    coherence_split_json_gates,
    export_frames,
    format_coherence_split_report,
    ingest_strip_provider,
    load_provider_frames,
)


def _corpus_layout() -> StripLayout:
    return StripLayout(
        frame_w=DEFAULT_LAYOUT.frame_w,
        frame_h=DEFAULT_LAYOUT.frame_h,
        frame_count=DEFAULT_LAYOUT.frame_count,
        gutter=DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )


def _format_report(result: IngestResult) -> str:
    lines: list[str] = []
    lines.append(f"Source  {result.source}")
    lines.append(
        f"Layout  {result.layout.frame_count}×{result.layout.frame_w}×{result.layout.frame_h}  "
        f"gutter={result.layout.gutter}  strip_w={result.layout.strip_width()}"
    )
    rec = result.recovered
    lines.append(
        f"Recovered  grid {rec['grid']}  expected {rec['expected_grid']}  "
        f"pitch x={rec['pitch_x']['score']:.3f} y={rec['pitch_y']['score']:.3f}"
    )
    sl = result.slice_meta
    lines.append(
        f"Slice  raster_match={sl.get('raster_match')}  "
        f"shape_match={sl.get('shape_match')}  "
        f"grid={sl.get('grid')} expected_raster={sl.get('expected_raster')}"
    )
    lines.append("Coherence")
    lines.extend(format_coherence_split_report(result.coherence))
    lines.append("")
    lines.append(f"Overall  {'PASS' if result.pass_ else 'FAIL'}")
    return "\n".join(lines)


def _json_payload(result: IngestResult, exported: list[pathlib.Path] | None = None) -> dict[str, Any]:
    gate_views = coherence_split_json_gates(result.coherence)
    payload: dict[str, Any] = {
        "pass": result.pass_,
        "source": result.source,
        "layout": {
            "frame_w": result.layout.frame_w,
            "frame_h": result.layout.frame_h,
            "frame_count": result.layout.frame_count,
            "gutter": result.layout.gutter,
            "strip_width": result.layout.strip_width(),
        },
        "recovered": result.recovered,
        "slice": result.slice_meta,
        "coherence": result.coherence,
        **gate_views,
    }
    if exported is not None:
        payload["exported_frames"] = [str(path) for path in exported]
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate a provider strip and export frames on pass.")
    parser.add_argument("png", type=pathlib.Path, help="Provider strip PNG")
    parser.add_argument("--motion-class", required=True, help="Motion class for gating")
    parser.add_argument("--out", type=pathlib.Path, help="Output directory for frame PNGs")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")
    args = parser.parse_args(argv)

    layout = _corpus_layout()

    try:
        result = ingest_strip_provider(
            args.png,
            layout,
            motion_class=args.motion_class,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    exported: list[pathlib.Path] | None = None
    if result.pass_ and args.out is not None:
        frames = load_provider_frames(args.png, layout)
        if frames is not None:
            exported = export_frames(
                frames,
                args.out,
                args.png.stem,
                frame_w=layout.frame_w,
                frame_h=layout.frame_h,
            )

    if args.json:
        print(
            json.dumps(
                _json_payload(result, exported),
                separators=(",", ":"),
            )
        )
    else:
        print(_format_report(result))

    return 0 if result.pass_ else 1


if __name__ == "__main__":
    raise SystemExit(main())
