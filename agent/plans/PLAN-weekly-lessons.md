# PLAN: Weekly lessons -- hint proposals become fixes on a 7-day cadence, enforced by the Stop hook

Status: approved
Depends-On: no-dep -- no box waits on another plan
Priority: P1 -- 217 hint proposals, 0 resolved, about 45 new each week, and the lesson-curator has never produced output
Concurrency: parallel -- W1-W3 edit wl_hints.py and the curator, W4-W6 edit wl_checks.py, effort.json and worklist_messages.py, W7 edits QUEUE.md tooling
Owns: .claude/hooks/stop/wl_hints.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/worklist_messages.py, .claude/hooks/stop/ctx_budget.py, .claude/config/effort.json, .claude/agents/lesson-curator.md, .claude/rediacc_hooks/tests/test_wl_hints*.py, .claude/rediacc_hooks/tests/test_wl_lessons_weekly*.py, agent/plans/PLAN-weekly-lessons.md
First-Seen: 2026-11-22
Owner: ace763dd
Updated: 2026-11-22

## Ask

Operator, 2026-11-22: "hint-proposals.jsonl stacks but do we solve improve the system? maybe we should have a weekly plan to address the issues? The plan should be enforced by stop hook and should be added to queue.md?", then, after the read-only investigation below: "yes let's make a plan about it".

## Context (measured 2026-11-22, read-only investigation)

1. `agent/ledgers/hint-proposals.jsonl` holds 217 rows, 2026-09-24 to 2026-11-22: per ISO week W39 5, W40 2, W41 31, W42 10, W43 20, W44 16, W45 39, W46 49, W47 45. The oldest is 58 days old, the median 14.
2. None is resolved: `agent/ledgers/hint-resolutions.jsonl` does not exist, so `worklist.py --hint-resolve` (`worklist.py:841`) has never run, and no `docs/agent-reference/HINTS.md` entry cites a `Proposal:` id.
3. 125 of the 217 rows carry no `id` field, so the resolve verb cannot name them.
4. The lesson-curator (`.claude/agents/lesson-curator.md`) writes to `agent/<me8>/lessons/e<epoch>/`; no such directory exists and git holds no commit under `agent/*/lessons/`, so it has never run or never landed output.
5. The only stop-report line, `hint-proposals` (`wl_checks.py:7115`, text `N_HINT_PROPOSALS_PENDING` at `worklist_messages.py:1438`), is `advise: high` in `.claude/config/effort.json:488`, so at the `smart` level it never shows. Its own comment records that 125 proposals waited with none promoted.
6. The 101 distinct `source` keys fragment recurrences. The largest families: the stop-gate judge (`judge` 32, plus `stop-judge` 6 and `stop-gate-judge` 3), `unlanded-lease` 14, `review-mark` 10, `review-findings` 8, `wake-timer` 5, `unread-reports` 5. Repeated pairs sit weeks apart (wake-timer 2026-10-08 and 10-19; review-findings 10-11 and 11-10; ci-red-unwatched 10-19 and 11-04; unlanded-lease 11-06, 11-12 and again 11-22): the same lesson returns because nothing fixed it.
7. What works: the stop-hook retro turns a brief into a `PLAN-stop-hook-retro-<date>.md` with boxes and a QUEUE.md entry, and the four older retros closed every box. Its trigger is a context band with a 7-day rearm (`ctx_budget.py:481` `RETRO_REARM_DAYS`, `:569-585`), not the calendar, and it only advises.
8. `## Settings` in QUEUE.md accepts `effort` only (`wl_planqueue.py:110` `SETTINGS_KEYS`), so the cadence must not become a new setting. The single-owner claim pattern exists in `wl_schedred.py`.

## Design

D1. One weekly lessons plan, `agent/plans/PLAN-lessons-<YYYYMMDD>.md`, is the unit of work. It has one box per cluster of 3 or more pending proposals sharing a normalized source family, and each box is a code change (a guard, gate, check or tool fix) that makes the lesson unnecessary. A lesson that a check already enforces, or that is wrong, closes as resolved with that pointer instead of a box.

D2. The curator produces the plan. The lesson-curator is the existing read-only agent; its brief is extended to emit the plan file (in the retro plan format) and the cluster table. The lead saves it verbatim, as with the retro.

D3. Resolution is the closing act. Every proposal the plan covers is resolved with `worklist.py --hint-resolve` naming the plan box or the commit, so the pending count falls as boxes land. A proposal with no id gets one first (W1), so nothing is unresolvable.

D4. The Stop hook enforces the cadence, not the content. A `lessons-weekly` check blocks at `smart` when (a) pending proposals exist and the newest `PLAN-lessons-*.md` is more than 7 days old or absent, or (b) the newest plan is more than 7 days old and still has open boxes. Only one session holds the block at a time (the `wl_schedred.py` claim pattern), and the block names the exact next command (dispatch the curator, or work the oldest open box).

D5. The plan rides the queue the normal way: it joins `## Promoted` in the commit that adds it, so `loop-next` and the progress block see it. No new `## Settings` key.

D6. Source keys are normalized into families (judge, stop-judge and stop-gate-judge are one family), so a recurrence is counted as one cluster rather than split across spellings.

## Risks

- A weekly block that fires while a PR merge is in progress adds pressure at the wrong time: the check honors the `babysit` and `merge` phases, which park it.
- The curator may still fail to produce output (Context 4): W3 proves one real run before W4 can block on it.
- Over-clustering hides distinct lessons: the cluster table in each plan lists every proposal id it absorbs, so a reviewer can split one.

## Tasks

- [x] W1 [writer] Backfill ids: `wl_hints.proposal_id` (`.claude/hooks/stop/wl_hints.py:176`) gains a deterministic id for a row without one (a hash of `at`, `by` and `text`), and `pending_proposals` and `--hint-resolve` accept it, so all 217 rows are resolvable. No rewrite of the ledger file. Test: .claude/rediacc_hooks/tests/test_wl_hints.py.
    (ticked) 2026-11-22T15:48:08Z by ace763dd: present: .claude/hooks/stop/wl_hints.py:176 proposal_id derives an id for id-less rows; .claude/rediacc_hooks/tests/test_wl_hints.py passes
- [ ] W2 [writer] Normalize source families: a table in `wl_hints.py` maps source keys to families (D6), used by the cluster count. Test: .claude/rediacc_hooks/tests/test_wl_hints.py.
- [ ] W3 [writer] The curator emits the weekly plan: `.claude/agents/lesson-curator.md` and its brief (`worklist_messages.py:1442`) produce `PLAN-lessons-<date>.md` in this plan's box format, with a cluster table naming every absorbed proposal id. Prove one real run against the current 217 rows and save its output. Test: .claude/rediacc_hooks/tests/test_wl_lessons_weekly.py.
- [ ] W4 [writer] The `lessons-weekly` Stop hook check (D4) in `.claude/hooks/stop/wl_checks.py`, with its message in `worklist_messages.py`, registered `block: smart` in `.claude/config/effort.json`, single owner through a claim file, parked by the babysit and merge phases. Fixtures: pending proposals and no plan blocks; a plan newer than 7 days stands down; an 8-day-old plan with open boxes blocks; a babysit phase parks it; a second session sees no block while the first holds the claim. Test: .claude/rediacc_hooks/tests/test_wl_lessons_weekly.py.
- [ ] W5 [writer] Retire the invisible advisory: the `hint-proposals` outq line (`wl_checks.py:7115`) is folded into the new check, and its `effort.json` entry is removed, so one check owns the subject. Test: .claude/rediacc_hooks/tests/test_wl_lessons_weekly.py.
- [ ] W6 [writer] Resolution as the closing act: ticking a box of a `PLAN-lessons-*.md` (`worklist.py --plan-tick`) resolves every proposal id its cluster table lists, through the same path as `--hint-resolve`. Test: .claude/rediacc_hooks/tests/test_wl_hints.py.
- [ ] W7 [writer] Queue entry: the curator's saved plan joins `## Promoted` in QUEUE.md in the same commit, through the existing plan-record tooling (no new settings key), and `check:ci-plan-record` accepts it. Test: .claude/rediacc_hooks/tests/test_wl_lessons_weekly.py.
- [ ] W8 [lead] First weekly run: dispatch the curator on the live ledger, save `PLAN-lessons-<date>.md`, add it to Promoted, and record the before and after counts: pending proposals (217 now), resolved (0 now), and the largest families (judge 41, unlanded-lease 14). Accept: the plan file committed and the counts recorded here.

### Critical Files for Implementation
- .claude/hooks/stop/wl_hints.py
- .claude/hooks/stop/wl_checks.py
- .claude/hooks/stop/worklist_messages.py
- .claude/config/effort.json
- .claude/agents/lesson-curator.md
