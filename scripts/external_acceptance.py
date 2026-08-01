"""External-acceptance CI helper (issue #232).

Every acceptance verdict on a pull request used to be produced by the
pipeline code *on that same branch*, so a branch that changes `pipeline/`
changed its own evaluator and nothing noticed. This script gives the
`external-acceptance` CI job (`.github/workflows/ci.yml`) three pieces of
logic, each importable and unit-tested on its own:

- `discover_bundles` walks a candidate `assets/` tree for Polish Bundle
  directories (C4) -- no hardcoded list.
- `compare_verdict` decides whether main's verdict for a bundle agrees with
  the candidate branch's own pipeline's verdict for the same bundle (C2).
- `exit_code_for_divergences` applies the `evaluator-change` label policy: a
  divergence fails the job unless the PR declares it (C3).

`main()` wires these to two already-installed pipeline checkouts (an
`evaluator/` tree pinned to `main`, and the `candidate/` tree under test) by
shelling out to `pipeline.final_polish_cli check --summary-json` once per
tree per bundle, so the two verdicts are always computed by two different
copies of the judging code. This script performs no network calls and no
writes outside the job artifact it is told to produce.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass

from pipeline.final_polish import BUNDLE_SCHEMAS


def discover_bundles(assets_root: pathlib.Path) -> list[pathlib.Path]:
    """Walk `assets_root` for directories whose `manifest.json` declares a
    Polish Bundle schema (C4). Depth-unbounded and driven entirely by the
    manifest's own `schema` field, so a new bundle is covered the moment its
    directory exists -- nothing to enumerate by hand.
    """
    if not assets_root.is_dir():
        return []
    bundles: list[pathlib.Path] = []
    for manifest_path in sorted(assets_root.rglob("manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(manifest, dict) and manifest.get("schema") in BUNDLE_SCHEMAS:
            bundles.append(manifest_path.parent)
    return bundles


@dataclass(frozen=True)
class Divergence:
    """A bundle where main's verdict and the candidate's own verdict disagree.

    A divergence means one of two things: the branch changed the evaluator,
    or the branch's assets depend on an evaluator change. Either way it is a
    review question (C2), never a silent pass.
    """

    bundle: str
    main_outcome: str
    candidate_outcome: str
    main_fingerprint: str
    candidate_fingerprint: str

    def message(self) -> str:
        return (
            f"{self.bundle}: main's verdict is {self.main_outcome!r} "
            f"(fingerprint {self.main_fingerprint}) but the candidate branch's "
            f"own pipeline reports {self.candidate_outcome!r} "
            f"(fingerprint {self.candidate_fingerprint}) for the same bundle. "
            "Either the branch changed the evaluator, or its assets depend on "
            "an evaluator change -- this is a review question, not a silent pass."
        )


def compare_verdict(
    bundle: str, main_verdict: dict[str, object], candidate_verdict: dict[str, object]
) -> Divergence | None:
    """Compare main's `check --summary-json` payload for `bundle` against the
    candidate branch's own payload for the same bundle (C2). `None` means the
    outcomes agree; otherwise the returned `Divergence` names both `outcome`
    values and both fingerprints.
    """
    main_outcome = str(main_verdict["outcome"])
    candidate_outcome = str(candidate_verdict["outcome"])
    if main_outcome == candidate_outcome:
        return None
    return Divergence(
        bundle=bundle,
        main_outcome=main_outcome,
        candidate_outcome=candidate_outcome,
        main_fingerprint=str(main_verdict.get("fingerprint", "")),
        candidate_fingerprint=str(candidate_verdict.get("fingerprint", "")),
    )


def exit_code_for_divergences(
    divergences: list[Divergence], *, evaluator_change: bool
) -> tuple[int, list[str]]:
    """Apply the `evaluator-change` label policy (C3). With no divergences the
    job always passes. With divergences: the label present downgrades every
    divergence to a `::notice::` annotation and the job still passes; absent
    the label, the job fails and each divergence's message is returned as a
    failure line.
    """
    if not divergences:
        return 0, []
    if evaluator_change:
        return 0, [f"::notice::{d.message()}" for d in divergences]
    return 1, [d.message() for d in divergences]


def _run_check(pipeline_root: pathlib.Path, bundle: pathlib.Path) -> dict[str, object]:
    """Invoke `pipeline_root`'s own copy of the final-polish CLI against
    `bundle` and return its `--summary-json` payload. Called once per tree
    per bundle so the two verdicts are always produced by two different
    copies of `pipeline/final_polish.py`.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pipeline_root)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipeline.final_polish_cli",
            "check",
            str(bundle.resolve()),
            "--summary-json",
        ],
        cwd=str(pipeline_root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if not result.stdout.strip():
        raise RuntimeError(
            f"check --summary-json produced no output for {bundle} "
            f"under {pipeline_root}: {result.stderr}"
        )
    return json.loads(result.stdout)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate-assets",
        type=pathlib.Path,
        required=True,
        help="candidate/assets directory to discover Polish Bundles under",
    )
    parser.add_argument(
        "--evaluator-root",
        type=pathlib.Path,
        required=True,
        help="checkout of main whose pipeline computes the evaluator verdict",
    )
    parser.add_argument(
        "--candidate-root",
        type=pathlib.Path,
        required=True,
        help="checkout of the PR branch whose pipeline computes the candidate verdict",
    )
    parser.add_argument(
        "--evaluator-change",
        action="store_true",
        help="the PR carries the evaluator-change label",
    )
    parser.add_argument("--report", type=pathlib.Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    bundles = discover_bundles(args.candidate_assets)
    verdicts = []
    divergences: list[Divergence] = []
    for bundle in bundles:
        bundle_name = bundle.relative_to(args.candidate_assets).as_posix()
        main_verdict = _run_check(args.evaluator_root, bundle)
        candidate_verdict = _run_check(args.candidate_root, bundle)
        verdicts.append(
            {"bundle": bundle_name, "main": main_verdict, "candidate": candidate_verdict}
        )
        divergence = compare_verdict(bundle_name, main_verdict, candidate_verdict)
        if divergence is not None:
            divergences.append(divergence)

    exit_code, messages = exit_code_for_divergences(
        divergences, evaluator_change=args.evaluator_change
    )
    for message in messages:
        print(message)

    payload = {
        "schema": "external-acceptance-report/0",
        "outcome": "PASS" if exit_code == 0 else "FAIL",
        "evaluator_change": args.evaluator_change,
        "bundles": [v["bundle"] for v in verdicts],
        "verdicts": verdicts,
        "divergences": [dataclasses.asdict(d) for d in divergences],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"external_acceptance_report={json.dumps(payload, separators=(',', ':'))}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
