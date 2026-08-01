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
