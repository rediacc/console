# PLAN: Context state file cleanup — opportunistic TTL sweep on save

Status: done 2026-09-22 -- all 4 boxes done. The fix fired for real in production during this session (see T4): 245 of 248 stale files swept, 1.1MB down to 80K, no hook broke, this session's own state survived.
Owner: d778be9d
First-Seen: 2026-09-22
Updated: 2026-09-22

## Why

`.claude/hooks/context/state/` holds 259 files (one `<session>.json` plus one `<session>-onboard.json` per session ever run), 1.1MB total, gitignored (`.claude/hooks/context/state/.gitignore:1`), accumulating without bound.
Unlike `agent/<session>/` (tracked, committed repo bloat, fixed by `PLAN-agent-session-archival.md`), these files are transient and local-only: they are written by context-budget hooks on every PostToolUse and compaction boundary, and read only during that same session's own execution.
Found as a sibling of the agent-session-archival problem during a stop-gate judge's class sweep on 2026-09-22.

**No CI gate needed.** Gitignored and local-only means no repo bloat, no discoverability problem, nothing the CI gate estate needs to enforce. A full archival mechanism (grace period + `--check`/`--status`/`--move` verbs + CI gate, the pattern `PLAN-agent-session-archival.md` used) would be disproportionate to a 1.1MB local cache.

**Age threshold:** `WORKLIST_DEAD_HOURS` (default 24, read via `os.environ.get("WORKLIST_DEAD_HOURS", "24")` at `.claude/hooks/stop/wl_store.py:1470`, `:1919`, `:2323` — there is no single named constant, it is re-read inline at each call site). Reusing this number keeps one liveness horizon instead of inventing a second.

**Safe to delete unconditionally past the threshold.** The only readers of a state file are `.claude/hooks/context/band-notice.py:183`, `epoch-reset.py:23`, `onboard.py:187`, each calling `load_state(session_id)` for the CURRENTLY RUNNING session only — nothing ever reads another session's state file, dead or alive.

**Sweep, not a gate.** `save_state()` (`.claude/hooks/context/ctx_budget.py:317`) already runs on every PostToolUse and compaction boundary. A debounced TTL sweep piggybacked on that hot path costs negligible overhead, needs no new wiring, and runs far more often than any Stop-only gate would.

## Tasks

- [x] T1 Add `cleanup_stale_state_files(grace_hours=24, now=None)` to `ctx_budget.py`: a pure function taking `state_dir()`'s file listing and their mtimes, deleting only `*.json`/`*-onboard.json` older than `grace_hours`, returning `(count_deleted, count_total, deleted_names)`. All exceptions caught and logged, never raised — a cleanup failure must never break `save_state()`.
    (done) 2026-09-22: `.claude/hooks/context/ctx_budget.py:320-343` (`cleanup_stale_state_files`); both suffixes match `.json` since `<session>-onboard.json` already ends in `.json`, so one `endswith` check covers both.
- [x] T2 Call it from `save_state()` (`ctx_budget.py:317`), debounced by a module-level `_last_cleanup_time` (init 0) so it runs at most once per 60 seconds regardless of call volume. Fire-and-forget: a failed cleanup does not fail the save.
    (done) 2026-09-22: `.claude/hooks/context/ctx_budget.py:346-364` (the debounced call inside `save_state()`).
- [x] T3 Add test coverage modelled on the existing pure-function test pattern.
    (done) 2026-09-22, CORRECTED FROM THE ORIGINAL BOX: the design's cited path, `.claude/rediacc_hooks/tests/test_context_state_cleanup.py`, does not match how this repo already tests `ctx_budget.py` -- `.claude/hooks/context/test-context-bands.py` is the existing, already-wired suite for this exact module (`import ctx_budget as B` at its own top), so `test_cleanup_stale_state_files()` was added there instead of inventing a second test file for the same module. `.claude/hooks/context/test-context-bands.py:898-949` (new test function), wired into `main()` at `:959`. 88 checks, 0 failures (`python3 .claude/hooks/context/test-context-bands.py`).
- [x] T4 Live verification (not a new gate).
    (done) 2026-09-22, and more thoroughly than planned: the fix fired FOR REAL in production during this session's own subsequent tool calls, not just in a deliberate test. `.claude/hooks/context/state/errors.log`'s last line records `2026-09-22T21:06:34Z cleanup_stale_state_files Exception: swept 245 of 248 stale state file(s)`. Before: 259 files, 1.1MB (measured earlier in this same session). After: 14 files (12 `*-precompact-facts.md`, this session's own `d778be9d.json`/`d778be9d-onboard.json`/`why-d778be9d.json`), 80K. `save_state()`'s own contract held throughout -- no hook error, no broken tool call. `*-precompact-facts.md` files were correctly left untouched: out of scope, a different artifact with unverified reader semantics, not part of this plan's `*.json` claim.
