| Claim | Verdict | Evidence |
|---|---|---|
| C1 | met | `_memoized_strip_read` checks `_STRIP_READ_CACHE` first, then `strip_cache.read`, then `fn`+`write` (`tests/conftest.py` L49–59). `test_second_read_through_the_wrapper_hits_disk_without_recomputing`: dict cleared, callee count stays 1. |
| C2 | met | Key tuple unchanged in wrapper (L41–47); `key_digest` hashes `repr(key)` (`strip_cache.py` L39–47). `test_key_digest_changes_when_mtime_changes`; wrapper test third call after `os.utime` recomputes (`calls["count"] == 2`). |
| C3 | met | `PICKLE_PROTOCOL = 5`; `pickle.dumps(..., protocol=5)` (`strip_cache.py` L20, L80). Wrapper returns `copy.deepcopy(...)` (conftest L60). `test_mutating_the_returned_value_does_not_affect_the_next_read`. |
| C4 | met | `store_root`: env override or `gettempdir()/underline-strip-cache-{sha256(repo)[:16]}` (`strip_cache.py` L24–36). `test_store_root_honors_env_override`, `test_store_root_default_is_outside_repo_and_stable`, `test_store_root_default_differs_per_repo_path`. Implements C4 over Delta's pytest-temp wording (see D1). |
| C5 | needs manual | Atomic write (`mkstemp` + `os.replace`, L78–84) and corrupt-as-miss (`read` L61–67, `test_corrupt_entry_is_treated_as_a_miss_and_can_be_overwritten`) evidenced. Concurrent proof is thread-only (P1); no two-process/xdist writer test in diff. |
| C6 | met | `write` only after successful `fn(...)` (conftest L54–58). `test_a_raising_call_through_the_wrapper_is_never_cached`: two raises, `calls["count"] == 2`, no dict entry, no `.pkl`. Stat `OSError` bypasses cache (L36–40). |
| C7 | met | `grep -rn "strip_cache" pipeline/ prototype/` → no matches. Import sites: `tests/conftest.py`, `tests/test_support_strip_cache.py` only. `13 passed` in `tests/test_support_strip_cache.py`. |
