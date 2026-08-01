# Code review — PR #266 / issue #261

Fixed point: `main` (`git diff main...HEAD`, commit `116dded`).

## Standards

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

## Spec

# Spec review — issue #261

## Findings

**D1 — Doc contradicts C4 (Delta tension resolved in code, not in docs)**  
Issue Delta: *"disk store under the pytest temp root"*. Contract **C4**: *"UNDERLINE_STRIP_CACHE_DIR when set, else a directory under the system temp dir keyed by the repo path"*. `store_root()` implements C4 (`tempfile.gettempdir()` + repo digest). Module docstring in `tests/support/strip_cache.py` still claims *"store under the pytest temp root"* — stale relative to both C4 and the implementation. Not a contract miss; documentation drift only.

**P1 — C5 proof uses threads, not processes**  
Proof mapping: *"two processes writing the same key concurrently both succeed"*. `test_concurrent_writers_of_the_same_key_both_succeed_and_agree` spawns eight `threading.Thread` writers in one process. The `mkstemp` + `os.replace` path is exercised under contention, but true xdist-style cross-process writers are not directly tested.

## Missing / partial

None for contract behavior. C4 runtime *"git status clean after npm test"* and full-suite warm/cold timings live in PR body evidence, not in the diff — acceptable if parent verified commands.

## Scope creep

None. Diff touches only `tests/conftest.py`, `tests/support/strip_cache.py`, `tests/test_support_strip_cache.py` as specified.

## Wrong implementation

None. Tier order (C1), key tuple with `st_mtime_ns`/`st_size` (C2), protocol 5 + wrapper `deepcopy` (C3), out-of-repo root (C4), atomic write + corrupt-as-miss (C5), raise-before-write (C6), test-only imports (C7) all match the Contract.

## Reviewed completion matrix

| Claim | Verdict | Evidence |
|---|---|---|
| C1 | met | `_memoized_strip_read` checks `_STRIP_READ_CACHE` first, then `strip_cache.read`, then `fn`+`write` (`tests/conftest.py` L49–59). `test_second_read_through_the_wrapper_hits_disk_without_recomputing`: dict cleared, callee count stays 1. |
| C2 | met | Key tuple unchanged in wrapper (L41–47); `key_digest` hashes `repr(key)` (`strip_cache.py` L39–47). `test_key_digest_changes_when_mtime_changes`; wrapper test third call after `os.utime` recomputes (`calls["count"] == 2`). |
| C3 | met | `PICKLE_PROTOCOL = 5`; `pickle.dumps(..., protocol=5)` (`strip_cache.py` L20, L80). Wrapper returns `copy.deepcopy(...)` (conftest L60). `test_mutating_the_returned_value_does_not_affect_the_next_read`. |
| C4 | met | `store_root`: env override or `gettempdir()/underline-strip-cache-{sha256(repo)[:16]}` (`strip_cache.py` L24–36). `test_store_root_honors_env_override`, `test_store_root_default_is_outside_repo_and_stable`, `test_store_root_default_differs_per_repo_path`. Implements C4 over Delta's pytest-temp wording (see D1). |
| C5 | needs manual | Atomic write (`mkstemp` + `os.replace`, L78–84) and corrupt-as-miss (`read` L61–67, `test_corrupt_entry_is_treated_as_a_miss_and_can_be_overwritten`) evidenced. Concurrent proof is thread-only (P1); no two-process/xdist writer test in diff. |
| C6 | met | `write` only after successful `fn(...)` (conftest L54–58). `test_a_raising_call_through_the_wrapper_is_never_cached`: two raises, `calls["count"] == 2`, no dict entry, no `.pkl`. Stat `OSError` bypasses cache (L36–40). |
| C7 | met | `grep -rn "strip_cache" pipeline/ prototype/` → no matches. Import sites: `tests/conftest.py`, `tests/test_support_strip_cache.py` only. `13 passed` in `tests/test_support_strip_cache.py`. |
