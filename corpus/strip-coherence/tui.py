#!/usr/bin/env python3
"""Interactive TUI for the strip coherence evidence suite."""

from __future__ import annotations

import json
import pathlib
import sys
import termios
import tty

from pipeline.strip import (
    DEFAULT_LAYOUT,
    IngestResult,
    StripLayout,
    format_ingest_report,
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


def _format_report(result: IngestResult) -> str:
    base = format_ingest_report(result)
    lines = base.split("\n")
    # Re-wrap section headers with TUI bold tokens.
    out: list[str] = []
    for line in lines:
        if line.startswith("Source  "):
            out.append(f"{BOLD}Source{RESET}  {line[7:]}")
        elif line.startswith("Layout  "):
            out.append(f"{BOLD}Layout{RESET}  {line[8:]}")
        elif line.startswith("Recovered  "):
            out.append(f"{BOLD}Recovered{RESET}  {line[11:]}")
        elif line.startswith("Slice  "):
            out.append(f"{BOLD}Slice{RESET}  {line[7:]}")
        elif line == "Coherence":
            out.append(f"{BOLD}Coherence{RESET}")
        elif line.startswith("Overall  "):
            out.append(f"{BOLD}Overall{RESET}  {line[9:]}")
        elif line.startswith("  "):
            out.extend(_format_gate_section_line(line))
        else:
            out.append(line)
    return "\n".join(out)


def _format_gate_section_line(line: str) -> list[str]:
    """Colorize a single coherence line from format_ingest_report."""
    text = line.strip()
    if text.endswith(": pass"):
        key = text[:-6]
        return [f"  {key}: {GREEN}yes{RESET}"]
    if text.endswith(": FAIL"):
        key = text[:-6]
        return [f"  {key}: {RED}no{RESET}"]
    if ": inapplicable" in text:
        return [f"  {DIM}{text}{RESET}"]
    if text.startswith("silhouette "):
        return [f"  {DIM}{text}{RESET}"]
    if text.startswith("palette drift "):
        return [f"  {DIM}{text}{RESET}"]
    if text.startswith("loop "):
        return [f"  {DIM}{text}{RESET}"]
    return [line]


def _run_fixture(scenario: str) -> tuple[IngestResult, str]:
    path = FIXTURES / f"synthetic-{scenario}.png"
    write_synthetic_fixture(path, LAYOUT, scenario)
    result = ingest_strip(path, LAYOUT)
    return result, f"synthetic/{scenario}"


def _ingest_latest_inbox() -> tuple[IngestResult | None, str]:
    INBOX.mkdir(parents=True, exist_ok=True)
    pngs = sorted(INBOX.glob("*.png"))
    if not pngs:
        return None, "inbox (empty — drop a .png in corpus/strip-coherence/inbox/)"
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
                last, last_label = _ingest_latest_inbox()
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
