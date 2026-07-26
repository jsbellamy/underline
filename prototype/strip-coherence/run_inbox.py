#!/usr/bin/env python3
"""Ingest the latest inbox PNG with provider-tolerant auto gutter slicing."""

from __future__ import annotations

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from strip import DEFAULT_LAYOUT, StripLayout, ingest_strip_provider

INBOX = pathlib.Path(__file__).resolve().parent / "inbox"


def main() -> int:
    pngs = sorted(INBOX.glob("*.png"))
    if not pngs:
        print(f"no PNG in {INBOX}")
        return 1
    path = pngs[-1]
    layout = StripLayout(
        frame_w=DEFAULT_LAYOUT.frame_w,
        frame_h=DEFAULT_LAYOUT.frame_h,
        frame_count=DEFAULT_LAYOUT.frame_count,
        gutter=DEFAULT_LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )
    result = ingest_strip_provider(path, layout)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.pass_ else 2


if __name__ == "__main__":
    raise SystemExit(main())
