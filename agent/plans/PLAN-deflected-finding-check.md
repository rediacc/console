# PLAN: a mechanical Stop-hook check for deflected findings

Status: executing
Owner: d778be9d
Updated: 2026-09-23

## Finding

The operator flagged a real instance this session: "Confirmed pre-existing and unrelated (untouched file, no uncommitted changes, environment-dependent identity-cache check)." CLAUDE.md rule 2 requires a finding to be fixed, tracked, or door-named in the session that finds it -- not just labeled and left.
The operator wants a fast, mechanical (regex, not judge-call) Stop-hook check for this class, since it must run cheaply on every stop.

## What already exists

`wl_admit.py` already scans the assistant's whole-turn text (since the last genuine operator turn, via `_is_operator_turn`) for evasive/admission phrasing, with its own regex family, settled-signature cache, and REAL/SYNTHETIC test corpus.
`DEFERRED_FINDING_RE`/`deferred_findings()` in `wl_checks.py:602-632` is a closer, simpler precedent: a hand-written regex firing on "found/reported/flagged ... not fixed" language, `last_msg`-scoped, `always=False` (HYGIENE tier), with message template `V_DEFERRED_FINDING`.

Neither covers the "dismissed responsibility without saying not-fixed" family (pre-existing/unrelated/environmental/out of scope), and `DEFERRED_FINDING_RE`'s `last_msg`-only scope is the wrong window for this class: the real incident's corroboration (worklist --add/--triage calls) landed in later tool calls in the SAME turn, not adjacent prose, ~30 seconds after the flagged sentence.

## Design

### Module: new sibling `wl_deflect.py`, beside `wl_admit.py`

Own regex family, own corroboration logic, own settled-signature state -- matching why `wl_admit.py` earned its own module instead of living in `wl_checks.py`.

### Phrase family (grounded in CLAUDE.md:118 and this session's own transcript)

Two shapes, not a bare word list (a bare list badly over-fires: "pre-existing docstrings/content/bumps" are all harmless adjectival uses measured in this session):
- **Verdict shape**: `(that's|this is|confirmed[,:]?) ... (pre-existing|unrelated|environmental|not caused by|not my <noun>)`
- **Finding-noun-adjacent shape**: a finding/bug/defect/failure/regression noun within ~60 chars of the attribution word, either order.

Exclude when the match is immediately followed by a harmless noun (docstrings/content/comments/bumps/"tests pass"), and exclude entirely when `baseline|ratchet(ed)?|floor|grandfathered` appears in the same clause (that debt is already tracked by the repo's own baseline mechanism).

### Corroboration window: the whole turn since the last operator message

Reuse (or generalize into `wl_core.py`) `wl_admit.py`'s `turn_text`/`turn_tools` walker, extended to also capture Bash `command` argument strings (not just tool names), since the corroborating signal lives there: a `worklist.py --add/--triage/--defer/--tick` call, a `#<hex-id>` citation, or a `door:operator-only|operator-deferred|no-write-access` token anywhere in the turn.
If found, the check stays quiet even though the phrase matched -- exactly matching this session's own correctly-handled real instance.

### Message template

New `V_DEFLECTED_FINDING` in `worklist_messages.py`, sibling to `V_DEFERRED_FINDING`: names the matched phrase and line, quotes CLAUDE.md's own rule 2 verification language, and states plainly what would have kept it quiet (a worklist verb call, an id citation, or a door token in the same turn) -- naming the missing evidence, not a banned word.

### Fail-safe and cost

- `always=False` (HYGIENE tier, rotates like its siblings, not shown every stop).
- A settled-signature cache (mirroring `wl_admit.load_settled`/`turn_sig`): the first occurrence of a normalized dismissal without corroboration blocks once; if the identical dismissal recurs in a later turn (this session repeated near-identical language ~6 times about one already-confirmed condition), later occurrences are suppressed -- one free forced disposition per distinct finding per session, not a nag on every stop.
- A detector crash must never crash a stop (`try/except Exception` around the call site, matching every sibling detector).

## Boxes

- [ ] Add `wl_deflect.py`: the phrase regex (verdict-shape + finding-noun-adjacent shape), the harmless-noun exclusion, the baseline/ratchet exemption, and the settled-signature cache (clone `wl_admit.py`'s `load_settled`/`save_settled`/`turn_sig`/`_norm` shape).
- [ ] Extend the turn walker to capture Bash command strings, not just tool names -- either generalize into `wl_core.py` (preferred, since two detectors now need it) or a small local duplicate in `wl_deflect.py` with a comment flagging the duplication for a future fold-in.
- [ ] Add `V_DEFLECTED_FINDING` to `worklist_messages.py`.
- [ ] Wire `wl_deflect` into `wl_checks.py` beside the `DEFERRED_FINDING_RE` call site (`wl_checks.py:4030-4051`), `always=False`.
- [ ] Test coverage: phrase-family MUST_HIT/MUST_MISS pairs (verdict shape, finding-noun shape, harmless-noun exclusion, baseline exemption) using this session's own real quoted lines as fixtures.
      Corroboration-window pairs using a synthetic transcript fixture (same tempdir shape as `wl_admit._selftest`): should-not-block (phrase + later worklist --add in the same turn, matching the real 84031->84053 sequence), should-block (phrase, no corroboration anywhere in the turn), turn-boundary reset control (phrase in one turn, genuine operator message, new turn -- must not leak forward), and a documented false-negative control (an unrelated worklist --add present in the turn, which the whole-turn window cannot distinguish from real corroboration -- assert it currently does NOT block, as a known, accepted tradeoff, not a silent gap).
- [ ] Run the new test file and the full `wl_admit`/`wl_checks` suite; confirm no regression.

## Critical files

- `.claude/hooks/stop/wl_admit.py` (pattern to clone)
- `.claude/hooks/stop/wl_deflect.py` (new)
- `.claude/hooks/stop/wl_checks.py` (wiring)
- `.claude/hooks/stop/worklist_messages.py` (message template)
- `.claude/hooks/stop/wl_core.py` (possible walker generalization)
- `.claude/hooks/stop/test-completion-evidence.py` (sibling test-fixture pattern to clone for the new test file)

Design produced by a dispatched Plan agent (2026-09-23), grounded in this session's own real transcript (the flagged instance and its correct-handling corroboration were both located and quoted) rather than a hypothetical phrase list.
