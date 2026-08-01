# Standards axis — #261 (`116dded`)

## Documented-standard violations

### S1 — Stale PR-body completion matrix (`issue-implementer.md` step 5)

When `test:changed` widens to `whole_suite`, the selector reason must appear **in the completion matrix** (`docs/agents/issue-implementer.md` lines 114–116). The scratch file `tmp/completion-matrix.md` satisfies this (line 15 attributes both `tests/conftest.py` and incidental `package-lock.json`). The PR-body `## Completion matrix` table (`tmp/pr-body.md`) has only C1–C7 rows; the `whole_suite` attribution lives only in `## Verification` prose, not in the matrix the Spec reviewer consumes.

### S2 — Stale evidence citation in completion matrix (`AGENTS.md` Evidence)

Matrix rows for C3 cite `tests/test_support_strip_cache.py::test_mutating_the_returned_value_does_not_affect_the_next_read_of_the_same_key`, but the committed test is `test_mutating_the_returned_value_does_not_affect_the_next_read`. Command-cited evidence must name a resolvable location.

## Companion-artifact checklist (verified)

| Surface | Result |
|---|---|
| `conftest.py` → `test:changed` whole-suite | Scratch matrix documents selector reason (S1 applies to PR-body copy). |
| No `pipeline/` / `prototype/` `strip_cache` imports (C7) | `grep -rn "strip_cache" pipeline/ prototype/` → exit 1, no matches. |
| `tests/support/` convention | `strip_cache.py` and `test_support_strip_cache.py` have module docstrings and `from __future__ import annotations` (matches `polish_bundle.py`). |
| Public function typing in `strip_cache.py` | `store_root`, `key_digest`, `read`, `write` fully annotated. |
| No contract/budget doc updates | Confirmed — test-only perf cache. |
| Issue Proof runtime commands in PR body | Present: focused pytest, cold/warm `--durations=25`, `run_isolated_tests.py`, `test:changed`, `grep` (C7). `npm test` equivalent to cited `pytest -q` per `package.json`. |

**No violations in the committed diff** for Python style (`code-style.md`), Touches manifest, or C7 import boundary.

## Baseline smells (judgement calls)

### B1 — Duplicated Code

`test_a_raising_call_through_the_wrapper_is_never_cached` rebuilds the cache key tuple inline instead of extending `_key()`:

```python
    key = (
        _fake_raising_recover.__qualname__,
        str(target),
        stat.st_mtime_ns,
        stat.st_size,
        "idle",
        (),
    )
```

Same six-tuple shape as `_key()` and `conftest.py::_memoized_strip_read`.

### B2 — Feature Envy

`test_corrupt_entry_is_treated_as_a_miss_and_can_be_overwritten` reaches into `strip_cache._entry_path` to inject corrupt bytes rather than writing through the public `write` API plus an external filesystem operation on the digest filename.

### B3 — Middle Man (suppressed)

`strip_cache.py` is a thin pickle/fs façade; issue #261 Contract explicitly splits disk tier from `conftest` wiring — repo interim form, not speculative generality.
