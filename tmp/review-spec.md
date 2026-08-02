# Spec review — issue #234

**Diff:** `main...HEAD` (1 commit, 6 files)  
**Spec:** [issue #234](https://github.com/jsbellamy/underline/issues/234) Contract C1–C7 + Manifest

## Findings

### C3-1 — Missing proof: non-allowlisted base (partial)

> "The supplied base Bundle's … attestation state must be `attested` or allowlisted `legacy`." / Proof: "focused tests cover … **non-allowlisted base**"

`_resolve_base_bundle_attestation` rejects unattested bases (`unattested_base_bundle`), but no focused test initializes against an unattested provider base. `test_init_rejects_cell_authored_base` only exercises a cell-authored base.

### C5-1 — Missing proof: Identity Lock FAIL on cell-author (partial)

> Proof: "a **Cell-authored Identity Lock failure remains FAIL**"

`check_bundle` still runs `evaluate_identity_lock` on the shared path, but no cell-author test forces a FAIL identity-lock outcome.

### C5-2 — Missing proof: Motion-class Gates on cell-author (partial)

> Proof: "**unchanged Motion-class Gates run**"

Successful `check_bundle` on cell-author bundles implies gates ran, but no test asserts `coherence` / `gate_outcomes` for cell-author the way provider suites do.

### C6-1 — Thin complete-report assertion (minor)

> "`check_bundle --summary-json` and the **complete report** expose … base Frame digests/mapping, and ledger digest"

`test_check_summary_json_exposes_cell_author_attestation` covers `--summary-json`. `test_finalize_report_exposes_cell_author_bindings` checks only `attestation.state`, `generation_mode`, `base_specification_id`, and provider absence — not digest/mapping fields that `_attestation_report_payload` already emits.

## No scope creep or wrong implementation observed

Provider `initialize_bundle`, `init`, and `animation-strip-provenance/0` remain provider-only. Cell-author lifecycle, schema, CLI mutual exclusion, replay rejection codes, and honest attestation payloads match the Contract. `npm run test:changed` → 932 passed.

## Claim summary

| Claim | Verdict |
|-------|---------|
| C1 | met |
| C2 | met |
| C3 | needs manual |
| C4 | met |
| C5 | needs manual |
| C6 | met |
| C7 | met |
| Manifest | met |
