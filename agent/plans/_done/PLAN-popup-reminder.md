# PLAN: probabilistic "out of the blue" Stop-hook reminder

Status: done -- both boxes closed 2026-09-23; a peer folded the wl_checks.py call-site change into commit 004b5dba1.
First-Seen: 2026-09-23
Owner: d778be9d
Updated: 2026-09-23

## What the operator asked for

A general Stop-hook mechanism, for every session in this repo (not just this one): roughly 20% of the time, the hook should surface a reminder even on a stop that would otherwise be silent. The other ~80% of stops behave exactly as today.

## Design (Plan agent af59a00a996d9eb3b, verified against the tree before landing)

- **Content**: reuse `wl_hints.py`'s existing rotating-hint corpus (`docs/agent-reference/HINTS.md`) rather than inventing a new pool. `wl_hints.hint_pick()`/`render()` already do exactly the right thing; they are just gated on other output already existing.
- **The gate itself**: a new, independent boolean roll (`wl_popup.should_pop(rng=None)`), matching the `rng` determinism seam `outq_drain()` and `hint_pick()` already use in `wl_checks.py`, so it is provably 1.0/0.0 for a fixed seed rather than a flaky rate-over-many-runs test.
- **Not routed through `outq_add`/`outq_drain`**: that queue is fixed at `OUTQ_PER_STOP = 3` and competes with real advisories; `wl_hints` deliberately bypasses it already ("never queued and never the reason a stop produces output").
- **Landing site**: `wl_checks.py`'s existing hint-render gate, `if parts:` (the sole place deciding whether the rotating hint can fire), becomes `if parts or wl_popup.should_pop():`. That is the entire required edit to the contested file.

## Why a separate module

`.claude/hooks/stop/wl_checks.py` and its siblings (`wl_hints.py`, `worklist.py`, `worklist_messages.py`, and the `test-*.py` family) are under active, uncommitted rewrite by a concurrent session for the whole span of this session (confirmed repeatedly via git's own STALE INDEX warnings).

`wl_popup.py` and `test-popup.py` are both brand-new files, so adding them carries zero collision risk. The one edit to `wl_checks.py` itself is a single line, additive (an `or`, not a replacement of existing logic), and is the smallest possible surface against that file.

## Delivered

- [x] `.claude/hooks/stop/wl_popup.py` -- `should_pop(rng=None)`, `POP_PROBABILITY = 0.2`.
    (ticked) 4/4 pytest (test-popup.py), both directions proven under fixed seeds (1 fires, 0 does not), plus a default-rng-matches-explicit-rng control and a pinned-probability control.
- [x] The one-line `wl_checks.py` call-site change (`if parts:` -> `if parts or wl_popup.should_pop():`), landed the same way every other genuinely-additive touch to this contested file has this session: named explicitly, minimal, and flagged rather than buried.
    (ticked) 2026-09-23T10:13:46Z by d778be9d: Peer folded the exact 2-line change into commit 004b5dba1, confirmed via .claude/hooks/stop/wl_checks.py:32; investigation recorded in commit 53f0e7365.
