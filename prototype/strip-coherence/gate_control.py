#!/usr/bin/env python3
"""COMPATIBILITY — score one candidate Gate control via pipeline.gate_control.

Forwards measurement, isolation, primary-failure, retry, and composite rendering
to the production scorer.

    PYTHONPATH=. python3 prototype/strip-coherence/gate_control.py \
        inbox/22-NEG-airborne-identity.png --motion-class airborne \
        --target-gate min_pair_cohort_pass --composite out/22.png
"""

from __future__ import annotations

import argparse
import json
import pathlib

from pipeline import gate_control as prod

HERE = pathlib.Path(__file__).resolve().parent
INBOX = HERE / "inbox"

GATE_ORDER = prod.GATE_ORDER
SpecificationError = prod.SpecificationError
applicable_gates = prod.applicable_gates
gate_config_hash = prod.gate_config_hash
measure = prod.measure
primary_failure = prod.primary_failure
retry_action = prod.retry_action
corpus_layout = prod.corpus_layout
build_composite = prod.build_composite

# --- review composite (prototype forwards to production) ---------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("png", type=pathlib.Path)
    parser.add_argument("--motion-class", required=True)
    parser.add_argument("--target-gate", required=True, choices=GATE_ORDER)
    parser.add_argument("--composite", type=pathlib.Path)
    parser.add_argument("--recorded-at")
    parser.add_argument("--scorer-commit")
    args = parser.parse_args(argv)

    path = args.png if args.png.exists() else INBOX / args.png.name
    try:
        run = measure(
            path,
            args.motion_class,
            args.target_gate,
            recorded_at=args.recorded_at or prod.utc_now(),
            scorer_commit=args.scorer_commit or prod.git_commit(),
        )
    except SpecificationError as exc:
        print(str(exc), file=__import__("sys").stderr)
        return 2
    if args.composite and run["structural"].get("recovered"):
        build_composite(path, run, args.composite)
    print(json.dumps(run, indent=2))
    return 0 if run["isolation"] == "ISOLATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
