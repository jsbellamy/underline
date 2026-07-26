#!/usr/bin/env python3
"""Throwaway TUI for the strip-coherence prototype. PROTOTYPE — delete when answered."""

from __future__ import annotations

import json
import pathlib
import sys
import termios
import tty
from typing import Any

from pipeline.strip import (
    DEFAULT_LAYOUT,
    IngestResult,
    StripLayout,
    ingest_strip,
    ingest_strip_provider,
    write_synthetic_fixture,
)

HERE = pathlib.Path(__file__).resolve().parent
INBOX = HERE / "inbox"
FIXTURES = HERE / "fixtures"
LAYOUT = DEFAULT_LAYOUT

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
GREEN = "\x1b[32m"
RED = "\x1b[31m"
RESET = "\x1b[0m"


def _read_key() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def _status_line(result: IngestResult | None, label: str) -> str:
    if result is None:
        return f"{DIM}Last run:{RESET} {label} — {RED}error{RESET}"
    color = GREEN if result.pass_ else RED
    verdict = "PASS" if result.pass_ else "FAIL"
    return f"{BOLD}Last:{RESET} {label}  {color}{verdict}{RESET}"


def _format_gate_section(coh: dict[str, Any], indent: str = "  ") -> list[str]:
    lines: list[str] = []
    if "reason" in coh:
        lines.append(f"{indent}{RED}reason:{RESET} {coh['reason']}")
        return lines
    for key in (
        "dimension_parity",
        "baseline_row_stable",
        "silhouette_budget",
        "min_pair_cohort_pass",
        "loop_closure_pass",
        "palette_drift_pass",
    ):
        if key not in coh:
            continue
        ok = coh[key]
        if ok is None:
            mark = f"{DIM}n/a{RESET}"
        else:
            mark = f"{GREEN}yes{RESET}" if ok else f"{RED}no{RESET}"
        lines.append(f"{indent}{key}: {mark}")
    if coh.get("baseline_rows"):
        lines.append(f"{indent}{DIM}baseline_rows:{RESET} {coh['baseline_rows']}")
    for row in coh.get("silhouette_adjacent", []):
        lines.append(
            f"{indent}{DIM}silhouette {row['pair']}:{RESET} "
            f"changed={row['changed_cells']}/{row['union_opaque']} "
            f"({row['frac']:.1%})"
        )
    for row in coh.get("palette_drift", []):
        lines.append(f"{indent}{DIM}palette drift {row['pair']}:{RESET} {row['tv']:.1%}")
    loop = coh.get("loop_closure")
    if loop:
        lines.append(
            f"{indent}{DIM}loop {loop['pair']}:{RESET} "
            f"changed={loop['changed_cells']}/{loop['union_opaque']} "
            f"({loop['frac']:.1%}) pass={loop['pass']}"
        )
    return lines


def _format_report(result: IngestResult) -> str:
    lines: list[str] = []
    lines.append(f"{BOLD}Source{RESET}  {result.source}")
    lines.append(
        f"{BOLD}Layout{RESET}  {result.layout.frame_count}×"
        f"{result.layout.frame_w}×{result.layout.frame_h}  "
        f"gutter={result.layout.gutter}  strip_w={result.layout.strip_width()}"
    )
    rec = result.recovered
    lines.append(
        f"{BOLD}Recovered{RESET}  grid {rec['grid']}  "
        f"expected {rec['expected_grid']}  "
        f"pitch x={rec['pitch_x']['score']:.3f} y={rec['pitch_y']['score']:.3f}"
    )
    sl = result.slice_meta
    lines.append(
        f"{BOLD}Slice{RESET}  raster_match={sl.get('raster_match')}  "
        f"shape_match={sl.get('shape_match')}  "
        f"grid={sl.get('grid')} expected_raster={sl.get('expected_raster')}"
    )
    coh = result.coherence
    if "quantized_motion" in coh:
        lines.append(f"{BOLD}Coherence (raw){RESET}")
        lines.extend(_format_gate_section(coh.get("raw", {})))
        q = coh.get("quantize", {})
        lines.append(
            f"  {DIM}quantize:{RESET} palette={q.get('palette_size')} "
            f"unique_in={q.get('input_unique')} merge={q.get('merge_dist')}"
        )
        lines.append(f"{BOLD}Coherence (quantized motion){RESET}")
        lines.extend(_format_gate_section(coh["quantized_motion"]))
    else:
        lines.append(f"{BOLD}Coherence{RESET}")
        lines.extend(_format_gate_section(coh))
    lines.append("")
    lines.append(f"{BOLD}Overall{RESET}  {'PASS' if result.pass_ else 'FAIL'}")
    return "\n".join(lines)


def _run_fixture(scenario: str) -> tuple[IngestResult, str]:
    path = FIXTURES / f"synthetic-{scenario}.png"
    write_synthetic_fixture(path, LAYOUT, scenario)
    result = ingest_strip(path, LAYOUT)
    return result, f"synthetic/{scenario}"


def _run_inbox() -> tuple[IngestResult | None, str]:
    INBOX.mkdir(parents=True, exist_ok=True)
    pngs = sorted(INBOX.glob("*.png"))
    if not pngs:
        return None, "inbox (empty — drop a .png in prototype/strip-coherence/inbox/)"
    path = pngs[-1]
    provider_layout = StripLayout(
        frame_w=LAYOUT.frame_w,
        frame_h=LAYOUT.frame_h,
        frame_count=LAYOUT.frame_count,
        gutter=LAYOUT.gutter,
        pitch_px=24,
        margin_cells=0,
    )
    return ingest_strip_provider(path, provider_layout), f"inbox/{path.name}"


def main() -> None:
    last: IngestResult | None = None
    last_label = "(none)"
    error: str | None = None

    while True:
        print("\033[2J\033[H", end="")
        print(f"{BOLD}underline — strip coherence prototype{RESET}")
        print(f"{DIM}Question: can one provider strip be sliced + coherence-gated?{RESET}\n")
        print(_status_line(last, last_label))
        if error:
            print(f"{RED}Error:{RESET} {error}\n")
        elif last:
            print()
            print(_format_report(last))
        print()
        print(f"{BOLD}Actions{RESET}")
        print(f"  {BOLD}[1]{RESET} {DIM}synthetic PASS (coherent 4-frame idle){RESET}")
        print(f"  {BOLD}[2]{RESET} {DIM}synthetic FAIL — baseline row drifts (frame 2+){RESET}")
        print(f"  {BOLD}[3]{RESET} {DIM}synthetic FAIL — palette set changes (frame 3+){RESET}")
        print(f"  {BOLD}[4]{RESET} {DIM}ingest latest PNG from inbox/{RESET}")
        print(f"  {BOLD}[j]{RESET} {DIM}dump last report as JSON to stdout{RESET}")
        print(f"  {BOLD}[q]{RESET} {DIM}quit{RESET}")

        key = _read_key()
        error = None
        if key in ("q", "Q", "\x03"):
            break
        try:
            if key == "1":
                last, last_label = _run_fixture("pass")
            elif key == "2":
                last, last_label = _run_fixture("baseline_fail")
            elif key == "3":
                last, last_label = _run_fixture("palette_fail")
            elif key == "4":
                last, last_label = _run_inbox()
            elif key in ("j", "J"):
                if last:
                    print(json.dumps(last.as_dict(), indent=2))
                    input("\nPress Enter...")
            else:
                error = f"unknown key: {repr(key)}"
        except ValueError as exc:
            error = str(exc)
            last = None


if __name__ == "__main__":
    main()
