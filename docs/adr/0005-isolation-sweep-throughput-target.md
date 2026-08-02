# ADR 0005: Isolation-sweep throughput target

## Status

Accepted (2026-08-01, issue #268).

## Context

The isolation sweep's targets — `wall_s` ≤ 70s, no module over 60s — were
derived from a local 10-worker sweep and lived only in issue bodies (#263,
#264, #249, #250, #251, #252). No doc owned the target, which is how it
drifted silently for two waves.

### Findings

1. **Worker count defaults to the runner's CPU count.**
   `scripts/run_isolated_tests.py` `main` sets `workers = min(os.cpu_count() or
   1, max(1, len(files)))` when `--workers` is not passed. `ubuntu-latest`
   reports 4 CPUs, so CI runs the sweep at 4 workers — not the 10 the historical
   targets assumed.

2. **The throughput model.** `_report_payload` records `wall_s` (the sweep's
   measured wall-clock time) and each file's `duration_s`. While every worker
   stays fed, `wall_s ≈ Σ files[].duration_s / workers`: total serial test work
   divided by worker count. A single file sets the wall only when its own
   duration exceeds that quotient — the sweep is then pole-bound instead of
   throughput-bound.

3. **Pole-bound evidence.** CI run
   [30724553986](https://github.com/jsbellamy/underline/actions/runs/30724553986)
   at `1320518`: `wall_s` 233.181, longest file `tests/test_final_polish.py`
   233.180, Σ 653.9 over 46 files (quotient 163.5). The single longest file set
   the wall, not the quotient.

4. **Throughput-bound evidence.** CI run
   [30727843714](https://github.com/jsbellamy/underline/actions/runs/30727843714),
   after #267 split `test_final_polish.py` by bundle lifecycle: `wall_s`
   165.761, longest file `tests/test_final_polish_cli.py` 121.944, Σ 662.4 over
   49 files (quotient 165.6). The wall now tracks the quotient, not any single
   file — splitting moved the sweep from pole-bound to throughput-bound.

5. **The historical 70s target is unreachable by partitioning.** At 4 workers,
   reaching `wall_s` ≤ 70s requires Σ ≤ 280s — under half of today's measured
   662.4. No further per-file split can reach it, because splitting itself
   raises Σ (Finding 6).

6. **Splitting a file increases Σ.** Comparing the two runs above for the
   final-polish family alone: 233.180s as one file (run 30724553986) versus
   278.244s as four files (run 30727843714), a +45.1s (+19%) increase in that
   family's own serial work. Each added file repays import, collection, and a
   cold strip-cache read in a fresh process, so splitting is a read-cost tool
   — useful for pole-bound runs, where it flattens one long file into several
   shorter ones the scheduler can spread across workers — not a speed tool once
   the sweep is throughput-bound, where it adds to the very Σ that sets the
   wall.

## Decision

The isolation sweep's budget is expressed as **CI's reported `wall_s`**, read
from the isolation job's uploaded `isolation-report` artifact
(`.github/workflows/ci.yml` job `isolation`, `scripts/run_isolated_tests.py`
`_report_payload`). A local sweep is not the measurement of record: it runs at
a different worker count (typically far more than CI's 4) and roughly half
CI's per-file durations, so its numbers do not transfer.

The lever on that budget is **Σ `duration_s`** — total serial test work across
every isolated file — not any single file's duration. While the sweep is
throughput-bound (Finding 2), reducing one file's duration without reducing
the sum it belongs to does not move `wall_s`.

The per-file ceiling is retired. A per-file number gates nothing while the
longest file is under Σ/workers (Findings 3–4), and the previously stated 70s
target is recorded as unreachable by partitioning: at 4 workers it requires
Σ ≤ 280s against today's measured 662.4 (Finding 5).

The standing budget is **`wall_s` ≤ 180s on CI** — roughly 9% headroom over the
measured 165.761 (Finding 4). A PR whose isolation report exceeds 180s either
reduces Σ or re-argues the budget in a superseding ADR that carries a new CI
report.

## Consequences

### Positive

- The budget is now measured from CI's report of record instead of a stale
  local-sweep number copied between issue bodies.
- The lever (Σ `duration_s`) is named, so a PR that wants to improve the sweep
  knows what to reduce.
- Headroom (9%) is explicit, so a small regression does not require an
  immediate re-derivation.

### Negative

- File splitting, previously treated as a general speed tool, now needs a
  stated reason (import/collection read cost, module cohesion) rather than
  "reduce the isolation number" — a split can make the sweep slower (Finding
  6).
- The budget is CPU-count-sensitive: if `ubuntu-latest`'s CPU count changes,
  the quotient Σ/workers changes and this ADR's 180s figure may need
  re-deriving even with unchanged Σ.

### Limit

This ADR records a measurement regime, not a one-off number. When the budget
is next changed, a superseding ADR carries the new CI report;
`docs/adr/README.md` forbids editing history in place. This slice does not
change `scripts/run_isolated_tests.py` or `.github/workflows/ci.yml` — it
records a target, it does not add a gate.
