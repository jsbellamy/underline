#!/usr/bin/env python3
"""DEPRECATED compatibility shim — use ``pipeline.gate_control_acquire`` via ``npm run gate-control:acquire``.

Forwards acquisition, promotion, and verification helpers to the production
module. Existing callers may keep invoking this module path; new code should use
the canonical production command.
"""

from __future__ import annotations

import pathlib
import sys

from pipeline import gate_control_acquire as prod

record_attempt = prod.record_attempt
promote_isolated = prod.promote_isolated
write_pending_promotion = prod.write_pending_promotion
complete_promotion_verification = prod.complete_promotion_verification
invalidate_stale_active_promotion = prod.invalidate_stale_active_promotion
AcquisitionError = prod.AcquisitionError
specification_id = prod.specification_id
promotion_id_for_spec = prod.promotion_id_for_spec
gates_requiring_review = prod.gates_requiring_review
review_required = prod.review_required
decide_artifact_retention = prod.decide_artifact_retention
consecutive_primary_reason_streak = prod.consecutive_primary_reason_streak
acquisition_escalation_required = prod.acquisition_escalation_required
allocate_attempt_identity = prod.allocate_attempt_identity
main = prod.main


def promote_palette_07() -> dict:
    """Register existing inbox 07 as the promoted idle palette-drift control."""
    here = pathlib.Path(__file__).resolve().parent
    return promote_isolated(
        here / "inbox" / "07-NEG-palette-drift.png",
        "idle",
        "palette_drift_pass",
        prompt_path=here / "prompts" / "07-NEG-palette-drift.prompt.txt",
        prompt_delta="corpus negative — promoted from inbox",
        agent="corpus-seed",
        budget_binding_good=here / "inbox" / "07-NEG-palette-drift.png",
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
