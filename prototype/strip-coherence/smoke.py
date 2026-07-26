#!/usr/bin/env python3
"""Non-interactive smoke check for the strip prototype. PROTOTYPE — delete when answered."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from strip import DEFAULT_LAYOUT, ingest_strip, write_synthetic_fixture

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
EXPECT = {
    "pass": True,
    "baseline_fail": False,
    "palette_fail": False,
}


def main() -> int:
    layout = DEFAULT_LAYOUT
    failed = False
    for scenario, want_pass in EXPECT.items():
        path = FIXTURES / f"synthetic-{scenario}.png"
        write_synthetic_fixture(path, layout, scenario)
        result = ingest_strip(path, layout)
        ok = result.pass_ == want_pass
        mark = "ok" if ok else "MISMATCH"
        print(f"{mark}  {scenario}: got {'PASS' if result.pass_ else 'FAIL'}, want {'PASS' if want_pass else 'FAIL'}")
        if not ok:
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
