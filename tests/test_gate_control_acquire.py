"""Production Gate-control acquisition tests (issue #65)."""

from __future__ import annotations

import hashlib
import json
import threading
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest

from pipeline import gate_control as gc
from pipeline import gate_control_acquire as gca
from pipeline import gate_evidence as ge
from pipeline import gate_review as gr
from pipeline import gate_verification as gv

ROOT = Path(__file__).resolve().parents[1]
IDLE_CONTROL = ROOT / "gate-controls/raw/idle--silhouette_budget--001.png"
BINDING_GOOD = ROOT / "prototype/strip-coherence/inbox/07-NEG-palette-drift.png"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _png(tag: bytes = b"raw") -> bytes:
    return b"\x89PNG\r\n\x1a\n" + tag + b"\x00" * 32


def _mock_run_for_png(png: Path, factory: Callable[..., dict]) -> dict:
    return factory(raw_sha256=ge.sha256_file(png))


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (bytes, bytearray)):
        path.write_bytes(payload)
    else:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _seed_gate_controls(tmp_path: Path) -> Path:
    gc_root = tmp_path / "gate-controls"
    gc_root.mkdir(parents=True)
    shutil.copy2(
        ROOT / "gate-controls/acceptance-profiles.json",
        gc_root / "acceptance-profiles.json",
    )
    _write(
        gc_root / "manifest.json",
        {
            "schema": "gate-control-manifest/0",
            "specifications": [],
            "promotions": [],
        },
    )
    (gc_root / "attempts.jsonl").write_text("")
    for name in ("raw", "provenance", "reports", "reviews", "verification"):
        (gc_root / name).mkdir(exist_ok=True)
    return gc_root


def _isolated_run(raw_sha256: str | None = None) -> dict:
    return {
        "schema": gc.MEASUREMENT_SCHEMA,
        "isolation": "ISOLATED",
        "structural": {"recovered": True},
        "gates": {
            "silhouette_budget": {
                "outcome": "fail",
                "acceptance_outcome": "FAIL",
                "metric": 0.3,
                "budget": 0.2239,
                "hard_fail": 0.3,
            },
            "palette_drift_pass": {
                "outcome": "pass",
                "acceptance_outcome": "PASS",
                "metric": 0.1,
                "budget": 0.1974,
            },
        },
        "blockers": [],
        "primary_failure": None,
        "retry_action": None,
        "raw_sha256": raw_sha256 or ("a" * 64),
        "target_gate": "silhouette_budget",
        "motion_class": "idle",
    }


def _not_isolated_run(
    code: str = "TARGET_DEFECT_TOO_WEAK", raw_sha256: str | None = None
) -> dict:
    return {
        "schema": gc.MEASUREMENT_SCHEMA,
        "isolation": "NOT_ISOLATED",
        "structural": {"recovered": True},
        "gates": {
            "silhouette_budget": {
                "outcome": "pass",
                "acceptance_outcome": "PASS",
                "metric": 0.1,
                "budget": 0.2239,
            }
        },
        "blockers": ["target gate silhouette_budget passes"],
        "primary_failure": {
            "code": code,
            "gate": "silhouette_budget",
            "rationale": "too weak",
        },
        "retry_action": {
            "reason_code": code,
            "gate": "silhouette_budget",
            "intent": "amplify the targeted defect",
            "one_prompt_delta": True,
            "direction": "increase",
            "metric_now": 0.1,
            "must_exceed": 0.2239,
        },
        "raw_sha256": raw_sha256 or ("b" * 64),
        "target_gate": "silhouette_budget",
        "motion_class": "idle",
    }


def _structural_fail_run() -> dict:
    return {
        "schema": gc.MEASUREMENT_SCHEMA,
        "isolation": "INDETERMINATE",
        "structural": {"recovered": False, "reason": "pitch-fail"},
        "gates": {},
        "blockers": ["pitch-fail"],
        "primary_failure": {
            "code": "STRUCTURAL_RECOVERY_FAILED",
            "gate": None,
            "rationale": "pitch-fail",
        },
        "retry_action": {
            "reason_code": "STRUCTURAL_RECOVERY_FAILED",
            "gate": None,
            "intent": "restate the grid/gutter constraint in the prompt",
            "one_prompt_delta": True,
        },
        "raw_sha256": "c" * 64,
        "target_gate": "silhouette_budget",
        "motion_class": "idle",
    }


def _review_band_run() -> dict:
    return {
        "schema": gc.MEASUREMENT_SCHEMA,
        "isolation": "NOT_ISOLATED",
        "structural": {"recovered": True},
        "gates": {
            "silhouette_budget": {
                "outcome": "fail",
                "acceptance_outcome": "REVIEW",
                "metric": 0.25,
                "budget": 0.2239,
                "hard_fail": 0.3,
            }
        },
        "blockers": ["target gate silhouette_budget passes"],
        "primary_failure": {
            "code": "TARGET_DEFECT_TOO_WEAK",
            "gate": "silhouette_budget",
            "rationale": "weak",
        },
        "retry_action": {
            "reason_code": "TARGET_DEFECT_TOO_WEAK",
            "gate": "silhouette_budget",
            "intent": "amplify the targeted defect",
            "one_prompt_delta": True,
        },
        "raw_sha256": "d" * 64,
        "target_gate": "silhouette_budget",
        "motion_class": "idle",
    }


def test_gates_requiring_review_detects_review_band_metric() -> None:
    gates = gca.gates_requiring_review(_review_band_run())
    assert gates == ["silhouette_budget"]
    assert gca.review_required(_isolated_run()) is False
    assert gca.review_required(_review_band_run()) is True
    assert gca.review_required(_isolated_run(), promotion_verification=True) is True


def test_retention_matrix_keeps_isolated_and_discards_redundant_rejects() -> None:
    assert gca.decide_artifact_retention(_isolated_run(), ordinal=99) == "retained"
    assert (
        gca.decide_artifact_retention(_not_isolated_run(), ordinal=1) == "retained"
    )
    assert (
        gca.decide_artifact_retention(_not_isolated_run(), ordinal=4) == "discarded"
    )
    assert (
        gca.decide_artifact_retention(
            _not_isolated_run(), ordinal=99, unseparated_evidence=True
        )
        == "retained"
    )


def test_escalation_fires_on_third_consecutive_matching_reason() -> None:
    spec_id = "idle/silhouette_budget"
    attempts = []
    for ordinal in range(1, 4):
        attempts.append(
            ge.Attempt(
                schema=gca.ATTEMPT_SCHEMA,
                attempt_id=f"idle--silhouette_budget--{ordinal:03d}",
                specification_id=spec_id,
                ordinal=ordinal,
                artifact_state="discarded",
                isolation="NOT_ISOLATED",
                measurement_path=None,
                provenance_path=None,
                composite_path=None,
                raw_sha256=None,
                recorded_at="2026-07-27T00:00:00+00:00",
                raw={
                    "primary_failure": {
                        "code": "TARGET_DEFECT_TOO_WEAK",
                        "gate": "silhouette_budget",
                        "rationale": "weak",
                    }
                },
            )
        )
    streak = gca.consecutive_primary_reason_streak(
        attempts, spec_id, "TARGET_DEFECT_TOO_WEAK"
    )
    assert streak == 3
    assert gca.acquisition_escalation_required(streak)

    attempts.append(
        ge.Attempt(
            schema=gca.ATTEMPT_SCHEMA,
            attempt_id="idle--silhouette_budget--collateral",
            specification_id=spec_id,
            ordinal=99,
            artifact_state="discarded",
            isolation="NOT_ISOLATED",
            measurement_path=None,
            provenance_path=None,
            composite_path=None,
            raw_sha256=None,
            recorded_at="2026-07-27T00:00:00+00:00",
            raw={
                "primary_failure": {
                    "code": "COLLATERAL_GATE_FAILED",
                    "gate": "palette_drift_pass",
                    "rationale": "collateral",
                }
            },
        )
    )
    attempts.append(
        ge.Attempt(
            schema=gca.ATTEMPT_SCHEMA,
            attempt_id="idle--silhouette_budget--004",
            specification_id=spec_id,
            ordinal=4,
            artifact_state="discarded",
            isolation="NOT_ISOLATED",
            measurement_path=None,
            provenance_path=None,
            composite_path=None,
            raw_sha256=None,
            recorded_at="2026-07-27T00:00:00+00:00",
            raw={
                "primary_failure": {
                    "code": "TARGET_DEFECT_TOO_WEAK",
                    "gate": "silhouette_budget",
                    "rationale": "weak",
                }
            },
        )
    )
    attempts.append(
        ge.Attempt(
            schema=gca.ATTEMPT_SCHEMA,
            attempt_id="idle--silhouette_budget--005",
            specification_id=spec_id,
            ordinal=5,
            artifact_state="discarded",
            isolation="NOT_ISOLATED",
            measurement_path=None,
            provenance_path=None,
            composite_path=None,
            raw_sha256=None,
            recorded_at="2026-07-27T00:00:00+00:00",
            raw={
                "primary_failure": {
                    "code": "TARGET_DEFECT_TOO_WEAK",
                    "gate": "silhouette_budget",
                    "rationale": "weak",
                }
            },
        )
    )
    reset = gca.consecutive_primary_reason_streak(
        attempts, spec_id, "TARGET_DEFECT_TOO_WEAK"
    )
    assert reset == 2


def test_record_attempt_writes_ordered_evidence(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(
            gc, "measure", return_value=_mock_run_for_png(png, _isolated_run)
        ) as measure:
            with patch.object(gc, "git_commit", return_value="deadbeef"):
                row = gca.record_attempt(
                    png,
                    "idle",
                    "silhouette_budget",
                    repo_root=tmp_path,
                    prompt_text="prompt",
                    clock=lambda: "2026-07-27T12:00:00+00:00",
                )
    measure.assert_called_once()
    gc_root = tmp_path / "gate-controls"
    assert (gc_root / "provenance" / f"{row['attempt_id']}.json").is_file()
    assert row["measurement_path"] is not None
    assert (tmp_path / row["measurement_path"]).is_file()
    last_line = (gc_root / "attempts.jsonl").read_text().strip().splitlines()[-1]
    assert json.loads(last_line)["attempt_id"] == row["attempt_id"]
    assert row["artifact_state"] == "retained"
    assert row["retry_action"] is None


def test_structural_failure_creates_no_review_composite(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(gc, "measure", return_value=_structural_fail_run()):
            row = gca.record_attempt(
                png,
                "idle",
                "silhouette_budget",
                repo_root=tmp_path,
                prompt_text="prompt",
                clock=lambda: "2026-07-27T12:00:00+00:00",
            )
    assert row["composite_path"] is None
    composite = (
        tmp_path
        / "gate-controls"
        / "reviews"
        / row["attempt_id"]
        / "composite.png"
    )
    assert not composite.is_file()


def test_review_band_creates_exactly_one_late_composite(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(gc, "measure", return_value=_review_band_run()):
            row = gca.record_attempt(
                png,
                "idle",
                "silhouette_budget",
                repo_root=tmp_path,
                prompt_text="prompt",
                clock=lambda: "2026-07-27T12:00:00+00:00",
            )
    assert row["review_required"] is True
    assert row["composite_path"] is not None
    composite = tmp_path / row["composite_path"]
    assert composite.is_file()
    review_dir = composite.parent
    assert list(review_dir.glob("composite*.png")) == [composite]


def test_corrupt_provenance_hash_blocks_later_ledger_append(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(
            gc, "measure", return_value=_mock_run_for_png(png, _isolated_run)
        ):
            with patch.object(
                ge,
                "write_provenance_record",
                side_effect=ge.EvidenceError("hash mismatch"),
            ):
                with pytest.raises(ge.EvidenceError, match="hash mismatch"):
                    gca.record_attempt(
                        png,
                        "idle",
                        "silhouette_budget",
                        repo_root=tmp_path,
                        prompt_text="prompt",
                    )
    ledger = (tmp_path / "gate-controls" / "attempts.jsonl").read_text()
    assert ledger.strip() == ""


def test_append_attempt_record_refuses_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "attempts.jsonl"
    row = {
        "schema": gca.ATTEMPT_SCHEMA,
        "attempt_id": "idle--silhouette_budget--001",
        "specification_id": "idle/silhouette_budget",
        "ordinal": 1,
        "artifact_state": "retained",
        "isolation": "ISOLATED",
        "recorded_at": "2026-07-27T00:00:00+00:00",
    }
    ge.append_attempt_record(path, row)
    with pytest.raises(ge.EvidenceError, match="duplicate attempt_id"):
        ge.append_attempt_record(path, row)


def _alloc_worker(gc_root: str, out_path: str) -> None:
    identity = gca.allocate_attempt_identity(Path(gc_root), "idle/silhouette_budget")
    Path(out_path).write_text(
        json.dumps(
            {
                "ordinal": identity.ordinal,
                "attempt_id": identity.attempt_id,
            }
        )
    )


def test_concurrent_allocators_receive_unique_ordinals(tmp_path: Path) -> None:
    gc_root = tmp_path / "gate-controls"
    gc_root.mkdir()
    (gc_root / "attempts.jsonl").write_text("")
    outs = [tmp_path / f"out-{index}.json" for index in range(4)]
    threads = [
        threading.Thread(
            target=_alloc_worker,
            args=(str(gc_root), str(out)),
        )
        for out in outs
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ordinals = sorted(json.loads(out.read_text())["ordinal"] for out in outs)
    attempt_ids = [json.loads(out.read_text())["attempt_id"] for out in outs]
    assert ordinals == [1, 2, 3, 4]
    assert len(set(attempt_ids)) == 4


def test_escalation_emitted_after_three_matching_failures(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(
            gc, "measure", return_value=_mock_run_for_png(png, _not_isolated_run)
        ):
            for _ in range(2):
                gca.record_attempt(
                    png,
                    "idle",
                    "silhouette_budget",
                    repo_root=tmp_path,
                    prompt_text="prompt",
                    clock=lambda: "2026-07-27T12:00:00+00:00",
                )
            third = gca.record_attempt(
                png,
                "idle",
                "silhouette_budget",
                repo_root=tmp_path,
                prompt_text="prompt",
                clock=lambda: "2026-07-27T12:00:00+00:00",
            )
    assert third["escalation"] is not None
    assert third["escalation"]["consecutive_attempts"] == 3


def _write_minimal_review_graph(
    tmp_path: Path,
    *,
    attempt_id: str,
    measurement_path: str,
    provenance_path: str,
    raw_rel: str,
    raw_sha: str,
) -> None:
    gc_root = tmp_path / "gate-controls"
    review_dir = gc_root / "reviews" / attempt_id
    review_dir.mkdir(parents=True, exist_ok=True)
    packet = gr.build_review_packet(
        root=tmp_path,
        attempt_id=attempt_id,
        gate="silhouette_budget",
        budget_binding_good=BINDING_GOOD,
        packet_kind="CANDIDATE_REVIEW",
    )
    gr.write_packet_manifest(review_dir / "packet.json", packet)
  # mechanical APPROVE audits for promotion prerequisites
    for index, review_id in enumerate(("review--01", "review--02"), start=1):
        record = gr.make_audit_record(
            packet=packet,
            review_id=review_id,
            verdict="APPROVE",
            frames=[0, 1],
            observed_feature="fixture",
            rationale="fixture",
            reviewer_identity=f"reviewer-{index}",
            model_identity="fixture-model",
            model_version="1",
            timestamp="2026-07-27T12:00:00+00:00",
        )
        gr.write_audit_record(review_dir / f"review--0{index}.json", record)
    gv.ensure_blinded_second_review_input(review_dir)


def test_write_pending_promotion_requires_approved_reviews(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(
            gc, "measure", return_value=_mock_run_for_png(png, _isolated_run)
        ):
            row = gca.record_attempt(
                png,
                "idle",
                "silhouette_budget",
                repo_root=tmp_path,
                prompt_text="prompt",
                promotion_verification=True,
                clock=lambda: "2026-07-27T12:00:00+00:00",
            )
    with pytest.raises(gca.AcquisitionError, match="missing review packet"):
        gca.write_pending_promotion(
            tmp_path,
            motion_class="idle",
            target_gate="silhouette_budget",
            attempt_id=row["attempt_id"],
        )
    _write_minimal_review_graph(
        tmp_path,
        attempt_id=row["attempt_id"],
        measurement_path=row["measurement_path"],
        provenance_path=row["provenance_path"],
        raw_rel=f"gate-controls/raw/{row['attempt_id']}.png",
        raw_sha=row["raw_sha256"],
    )
    promo = gca.write_pending_promotion(
        tmp_path,
        motion_class="idle",
        target_gate="silhouette_budget",
        attempt_id=row["attempt_id"],
    )
    assert promo["status"] == gv.PENDING_STATUS


def test_discarded_attempt_cannot_back_pending_promotion(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(
            gc, "measure", return_value=_mock_run_for_png(png, _not_isolated_run)
        ):
            row = gca.record_attempt(
                png,
                "idle",
                "silhouette_budget",
                repo_root=tmp_path,
                prompt_text="prompt",
                clock=lambda: "2026-07-27T12:00:00+00:00",
            )
    ledger_path = tmp_path / "gate-controls" / "attempts.jsonl"
    attempt = json.loads(ledger_path.read_text().strip())
    attempt["artifact_state"] = "discarded"
    ledger_path.write_text(json.dumps(attempt, sort_keys=True) + "\n")
    _write_minimal_review_graph(
        tmp_path,
        attempt_id=row["attempt_id"],
        measurement_path=row["measurement_path"],
        provenance_path=row["provenance_path"],
        raw_rel=f"gate-controls/raw/{row['attempt_id']}.png",
        raw_sha=row["raw_sha256"],
    )
    with pytest.raises(gca.AcquisitionError, match="discarded"):
        gca.write_pending_promotion(
            tmp_path,
            motion_class="idle",
            target_gate="silhouette_budget",
            attempt_id=row["attempt_id"],
        )


def test_invalidate_stale_active_promotion(tmp_path: Path) -> None:
    gc_root = _seed_gate_controls(tmp_path)
    attempt_id = "idle--silhouette_budget--001"
    spec_id = "idle/silhouette_budget"
    promo_id = "promo--idle--silhouette_budget"
    raw = _png(b"promoted")
    raw_sha = _sha(raw)
    measurement_rel = f"gate-controls/reports/{attempt_id}/m1.json"
    provenance_rel = f"gate-controls/provenance/{attempt_id}.json"
    raw_rel = f"gate-controls/raw/{attempt_id}.png"
    measurement = {
        "schema": gc.MEASUREMENT_SCHEMA,
        "raw_sha256": raw_sha,
        "motion_class": "idle",
        "target_gate": "silhouette_budget",
        "applicable_gates": ["silhouette_budget"],
        "structural": {"recovered": True},
        "gates": {"silhouette_budget": {"outcome": "fail", "metric": 0.3, "budget": 0.2239}},
        "isolation": "NOT_ISOLATED",
        "blockers": ["target gate silhouette_budget passes"],
        "caveats": [],
        "primary_failure": None,
    }
    provenance = {
        "schema": "gate-control-provenance/0",
        "specification_id": spec_id,
        "attempt_id": attempt_id,
        "generator": "cursor-image-gen",
        "prompt_text": "prompt",
        "prompt_sha256": _sha(b"prompt"),
        "reference_image_sha256": [],
        "generated_at": "2026-07-27T00:00:00+00:00",
        "acquiring_agent": "test",
        "repository_commit": "deadbeef",
        "raw_path": raw_rel,
        "raw_sha256": raw_sha,
        "media_type": "image/png",
        "dimensions": [16, 24],
    }
    attempt = {
        "schema": gca.ATTEMPT_SCHEMA,
        "attempt_id": attempt_id,
        "specification_id": spec_id,
        "ordinal": 1,
        "artifact_state": "retained",
        "isolation": "ISOLATED",
        "recorded_at": "2026-07-27T00:00:00+00:00",
        "measurement_path": measurement_rel,
        "provenance_path": provenance_rel,
        "raw_sha256": raw_sha,
        "promotion_blockers": [],
        "primary_failure": None,
    }
    manifest = {
        "schema": "gate-control-manifest/0",
        "specifications": [
            {
                "id": spec_id,
                "motion_class": "idle",
                "target_gate": "silhouette_budget",
                "active_promotion": promo_id,
            }
        ],
        "promotions": [
            {
                "id": promo_id,
                "specification_id": spec_id,
                "attempt_id": attempt_id,
                "measurement_path": measurement_rel,
                "status": gv.ACTIVE_STATUS,
                "recorded_at": "2026-07-27T00:00:00+00:00",
            }
        ],
    }
    _write(tmp_path / raw_rel, raw)
    _write(tmp_path / measurement_rel, measurement)
    _write(tmp_path / provenance_rel, provenance)
    _write(gc_root / "manifest.json", manifest)
    ge.append_attempt_record(gc_root / "attempts.jsonl", attempt)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(gc_root)}):
        changed = gca.invalidate_stale_active_promotion(tmp_path, promo_id)
    assert changed is True
    updated = ge.load_manifest(gc_root / "manifest.json")
    promo = next(p for p in updated.promotions if p.id == promo_id)
    assert promo.status == gv.INVALIDATED_STATUS


def test_prototype_forwarder_delegates_to_production() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "prototype_gate_control_acquire",
        ROOT / "prototype/strip-coherence/gate_control_acquire.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.record_attempt is gca.record_attempt
    assert module.promote_isolated is gca.promote_isolated


def test_isolated_non_review_attempt_has_no_composite(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(
            gc, "measure", return_value=_mock_run_for_png(png, _isolated_run)
        ):
            with patch.object(gc, "git_commit", return_value="deadbeef"):
                row = gca.record_attempt(
                    png,
                    "idle",
                    "silhouette_budget",
                    repo_root=tmp_path,
                    prompt_text="prompt",
                    clock=lambda: "2026-07-27T12:00:00+00:00",
                )
    assert row["composite_path"] is None


def test_discarded_attempt_unlinks_raw_png(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        for ordinal in range(1, 4):
            with patch.object(
                gc, "measure", return_value=_mock_run_for_png(png, _not_isolated_run)
            ):
                with patch.object(gc, "git_commit", return_value="deadbeef"):
                    row = gca.record_attempt(
                        png,
                        "idle",
                        "silhouette_budget",
                        repo_root=tmp_path,
                        prompt_text="prompt",
                        clock=lambda: f"2026-07-27T12:00:0{ordinal}+00:00",
                    )
        with patch.object(
            gc, "measure", return_value=_mock_run_for_png(png, _not_isolated_run)
        ):
            with patch.object(gc, "git_commit", return_value="deadbeef"):
                row = gca.record_attempt(
                    png,
                    "idle",
                    "silhouette_budget",
                    repo_root=tmp_path,
                    prompt_text="prompt",
                    clock=lambda: "2026-07-27T12:00:10+00:00",
                )
    assert row["artifact_state"] == "discarded"
    raw_path = tmp_path / "gate-controls" / "raw" / f"{row['attempt_id']}.png"
    assert not raw_path.is_file()


def test_npm_script_invokes_production_module() -> None:
    env = {**dict(__import__("os").environ), "PYTHONPATH": str(ROOT)}
    result = subprocess.run(
        ["npm", "run", "-s", "gate-control:acquire", "--", "record", "--help"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--motion-class" in result.stdout
    assert "--target-gate" in result.stdout


def test_measurement_persist_is_append_only_on_rescore(tmp_path: Path) -> None:
    _seed_gate_controls(tmp_path)
    png = tmp_path / "candidate.png"
    shutil.copy2(IDLE_CONTROL, png)
    with patch.dict("os.environ", {"UNDERLINE_GATE_CONTROLS_ROOT": str(tmp_path / "gate-controls")}):
        with patch.object(
            gc, "measure", return_value=_mock_run_for_png(png, _isolated_run)
        ):
            row = gca.record_attempt(
                png,
                "idle",
                "silhouette_budget",
                repo_root=tmp_path,
                prompt_text="prompt",
                clock=lambda: "2026-07-27T12:00:00+00:00",
            )
        first = Path(tmp_path / row["measurement_path"]).read_bytes()
        second_path = Path(tmp_path / row["measurement_path"]).parent / "2026-07-27T13-00-00+00-00.json"
        gc.persist_measurement_run(second_path, {**_isolated_run(), "isolation": "NOT_ISOLATED"})
        assert Path(tmp_path / row["measurement_path"]).read_bytes() == first
        assert second_path.is_file()
