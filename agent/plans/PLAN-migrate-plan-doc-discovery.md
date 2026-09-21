# Plan-document discovery in /migrate and the Stop hook's handoff block

Status: draft
First-Seen: 2026-09-17
Owner: d778be9d
Updated: 2026-09-17
Related: agent/PLAN-plan-file-lifecycle.md, agent/PLAN-tooling-transformation.md

99 open `- [ ]` boxes across 11 committed plans, owned by three idle sessions, are invisible to every "what is left" surface this repo has. This makes the DISCOVERY layer read the plan census it already maintains.

## Why: the failure, measured

Live on this tree, 2026-09-17, branch `0914-1`:

    python3 .claude/hooks/stop/worklist.py --migrate d778be9d --candidates

returns four idle prefixes -- `f4da5c2e`, `74de73ca`, `d1589e0b`, `8f55d4f0` -- every one of them carrying `0 worklist item(s), but a STATE.md Next action below`. Not one plan file is named. Yet `agent/INDEX.md:345` already records:

    | `agent/PLAN-tooling-transformation.md` | ready | 6782 | 13 | 141 | 622006 |

Thirteen open boxes, 141 ticked, `Owner: 8f55d4f0` -- a session the same listing prints as `idle`. The whole tree, computed from the census plus one `plan_owner` read per box-carrying plan:

| Owner | liveness | plans with open boxes | open boxes |
|---|---|---|---|
| `f4da5c2e` | idle | 4 (b2-emit-matrix, ci-vacuity-baseline-registry, stop-hook-overhaul, w9p2-script-relocation) | 48 |
| `8f55d4f0` | idle | 2 (bws-rotation-on-failure, tooling-transformation) | 31 |
| `74de73ca` | idle | 5 (commit-author-identity, env-to-bitwarden-v2, plan-file-lifecycle, plyr-css-on-demand-loading, session-onboarding-marker) | 20 |
| `d778be9d` | live, this session | 3 | 43 |
| unowned | -- | 1 (secret-namespace-migration) | 9 |

96 plans on disk, 15 carrying open boxes, 151 open boxes. **99 of those 151 belong to plans whose declared owner is idle, and no surface in this repo names them.** `check_plan_boxes.py:603` already says the sentence this plan acts on -- "unowned debt is debt nothing chases" -- but its G-A4 only tests for the string `unowned`. A plan owned by a session that stopped three weeks ago
is the same debt wearing a name, and no gate, hook or verb notices.

### Root cause, per mechanism

1. `wl_store.migrate_candidates` (`.claude/hooks/stop/wl_store.py:1973`) builds
its candidate set from exactly two sources: worklist items whose owner is not the requesting session (`wl_store.py:1990`), and the per-session STATE.md `## Next action` fallback added this session (`wl_store.py:2049`, cutoff `WORKLIST_HANDOFF_STALE_HOURS` at `wl_store.py:2072`). It never opens `agent/PLAN-*.md`. There is no code path that could.

2. Every per-stop plan mechanism is OWNERSHIP-SCOPED TO THE CURRENT SESSION, by
design, and therefore structurally cannot do discovery:
   * `wl_checks.plan_drift_rows` (`.claude/hooks/stop/wl_checks.py:1188`) skips
     any plan failing `C.owned_by_me(owner, session_id)` at `wl_checks.py:1228`,
     and further admits only `executing`/`unknown` status (`wl_checks.py:1241`).
     13 of the 15 open plans above are `draft`/`ready`/`partially`, so even
     their own owner would not be nagged. It is a drift nag, not a finder.
   * `wl_planfile.plan_rows` (`.claude/hooks/stop/wl_planfile.py:399`) -- the
     third plan-aware mechanism, the one behind `V_PLAN_DRIFT` at
     `.claude/hooks/stop/worklist_messages.py:859`, "N committed plan file(s)
     under agent/ describe work you have since moved past" -- filters on
     `C.owned_by_me` at `wl_planfile.py:428`. A peer's plan is never shown.
   * `wl_core.owned_by_me` (`.claude/hooks/stop/wl_core.py:206`) returns True
     for `None`, so the ONE unowned plan (secret-namespace-migration, 9 boxes)
     is already visible to everybody. The 99 boxes with a dead owner's name on
     them are visible to nobody. The scoping rule is correct and must stay: a
     peer's live plan is not this session's to rewrite. It is simply not a
     discovery tool.

3. `wl_checks.handoff_note` (`.claude/hooks/stop/wl_checks.py:3079`) -- the Stop
hook's `HANDOFF CANDIDATES` block, which asks the session to carry inherited work into `## Remaining` -- is a second consumer of the SAME `migrate_candidates` call (`wl_checks.py:3094`). So the gap is one function wide and closing it fixes both surfaces at once.

### What was checked and ruled out

`agent/ledgers/census-plan-record.jsonl` (written by `check_plan_record.py:205`) is NOT the plan census this needs: it is a shadow-mode ledger of what candidate COMPACTION rules C9/C10/C11 would have flagged, keyed by record grammar, and it carries no open-box counts.

The census that IS needed already exists and is already fresh: `## Plan census` in `agent/INDEX.md` (`.claude/hooks/stop/wl_planindex.py:98`), one row per plan as `(rel, status, lines, open, ticked, bytes)`, read by `wl_planindex.index_census` (`wl_planindex.py:301`) from ONE file read plus a `stat` per plan, with a loud slow-path fallback through `wl_planindex.census_rows`
(`wl_planindex.py:164`) when it disagrees with disk. Verified live today: `index_census` returns `state=fresh`, 96 rows, 96 stats. The only field it lacks is `Owner:`, which `wl_checks.plan_owner` (`.claude/hooks/stop/wl_checks.py:1115`) reads from the first 10 header lines -- and it is only needed for the 15 plans with `open > 0`.

## The decision

**Make the DISCOVERY layer plan-aware. Leave the two storage mechanisms alone.**

The single-source-of-truth instinct behind this plan is right, but the unit of truth is the QUESTION, not the file:

| question | the one authority | why nothing else may answer it |
|---|---|---|
| which boxes of a design are open? | the `agent/PLAN-*.md` file | it is committed, gated byte-for-byte by `check:ci-plan-boxes` A0/A1, and outlives every session |
| what is a session blocked on right now? | `agent/worklist/<prefix>.jsonl` | per-session, append-only, and what the Stop hook blocks on -- load-bearing, unchanged by this plan |
| what should a resuming session pick up? | the discovery layer (`--candidates`, `handoff_note`) | it owns NO storage; it must read both and duplicate neither |

Today the third row has no implementation for plans. That is the entire defect.

### The road not taken: unify storage

Making the worklist store authoritative -- plan files losing their own `Status:`/`Owner:` lifecycle, or growing an auto-synced worklist item per plan -- is rejected on three measurements:

* **Six consumers already parse the plan header**: `wl_checks.plan_records`
(`wl_checks.py:1154`), `wl_checks.plan_owner` (`wl_checks.py:1115`), `wl_planfile.plan_rows`, `wl_planindex.census_rows`, `wl_planrec.index_rows`, and two CI gates (`check_plan_boxes.py` G-A3/G-A4, `check_plan_record.py` R8). R8 compares `agent/INDEX.md` for BYTE EQUALITY against a re-read of the plans. Moving the lifecycle into a JSONL store means a committed markdown document
whose status lives elsewhere -- `wl_planindex.py`'s own docstring calls that shape out and refuses it ("a sidecar nothing checks would be a cache that can lie"), and `agent/README.md:9-12` names the precedent it cost.
* **An auto-synced item per plan is the duplication risk stated as a feature.**
An item whose text drifts from the plan's own boxes is worse than no item, and the Stop hook BLOCKS on open items -- auto-creating one for `PLAN-stop-hook-overhaul.md` would block a session on 31 boxes it never agreed to take. Worse, the reconciliation it would buy already exists: `wl_planfile.reconcile` (`wl_planfile.py:343`) computes `untracked` / `stale_open` / `reopened` for
any plan IN SCOPE. The correct way to get it is to put the plan in scope, not to mint a shadow item.
* The store is per-session and append-only; a plan outlives many sessions. They
have different lifetimes, so they are different files.

### What "adopting" a plan means

Adoption re-stamps the plan's own `Owner:` line to the adopting session. That is deliberately the whole mechanism, and it is why a synced shadow item is unnecessary: once `Owner:` names a live session, `wl_planfile.plan_rows` already chases it every stop -- the census tier for `draft` (`wl_planfile.py:191` NOT_STARTED_STATES), the full quoting-and-reconciling treatment for `ready`,
which is in neither `FINISHED_STATES` nor `NOT_STARTED_STATES` and so returns True from `in_scope_status` (`wl_planfile.py:394`). `PLAN-tooling-transformation.md` is `ready`: adopting it starts reconciling its 13 open boxes against the adopter's worklist on the next stop, through code that already exists and is already tested.

This also gives the listing something the STATE.md fallback never had: **a natural tick**. A STATE.md `## Next action` is never resolved, which is why it needed an arbitrary 720h clock at `wl_store.py:2072`. A plan candidate clears itself three ways -- its owner becomes live, its status becomes finished, or its last box is ticked. So the plan pass takes NO time cutoff, matching
`plan_drift_rows`'s own lesson at `wl_checks.py:1197`: the trigger is work, never the clock.

### Noise controls, stated as rules

* Only plans with `open > 0` in the census are considered: the 141 ticked boxes
of `PLAN-tooling-transformation.md` can never resurface, because the census `open` column is the filter and it reads 13.
* Status is filtered with `wl_planfile.FINISHED_STATES` ONLY -- never
`in_scope_status`. `draft` is this repo's default header on plans under active execution (measured at `wl_checks.py:1338`: 6 of 8 box-carrying plans, hiding 72 of 88 open boxes; today 13 of 15). Using `in_scope_status` here would hide the majority of the very work this plan exists to surface.
* Plans whose owner is `live` are excluded. Plans whose owner is `unknown` are
INCLUDED with the verdict printed, because listing is not adopting -- the cost of a false positive is one line.
* At most `WORKLIST_MIGRATE_PLANS_SHOW` (default 3) plans printed per candidate,
with a `+N more` tail, matching the existing 3-item cap at `worklist.py:1133`.
* Unowned plans are OUT OF SCOPE: `owned_by_me(None)` is True
(`wl_core.py:217`), so `PLAN-secret-namespace-migration.md`'s 9 boxes are already shown to every session by the per-stop advisory. Adding them here would duplicate a working surface and there is no prefix to migrate from.

## Design

One new function in `wl_store.py`, one new key on the candidate dict, one new CLI mode, and prose. No new storage, no new file, no new census.

    plan_candidates(root, exclude_live_for=session_liveness_fn) ->
        {owner8: [ {rel, status, open, ticked, title} ] }

reading `wl_planindex.index_census(root)` (falling back to `census_rows` exactly as `plans_block` does at `wl_checks.py:1401`), keeping rows with `open > 0` and status not in `wl_planfile.FINISHED_STATES`, then calling `wl_checks.plan_owner` on that short list only. `wl_planindex` imports `wl_store` at its line 92, so the import inside `wl_store` MUST be deferred into the function
body -- the same cycle-avoidance `wl_planindex.census_rows` documents for `wl_checks`.

`migrate_candidates` then gains a third pass, additive in the same style as the second (`wl_store.py:2049-2056`): owners already present are ENRICHED with a `"plans"` key, never duplicated; owners present only because of a plan get a full candidate row with `counts` all zero and `plans` populated. `"plans"` defaults to `[]` on every candidate so both existing renderers stay total.

## Tasks

- [ ] Add `plan_candidates(root)` to `.claude/hooks/stop/wl_store.py`, returning
      `{owner8: [{"rel","status","open","ticked","title"}]}`.
- [ ] Source it from a DEFERRED `import wl_planindex` + `index_census(root)`,
      with the `census_rows` fallback on a non-fresh state.
- [ ] Filter to `open > 0` and status not in `wl_planfile.FINISHED_STATES`, then
      call `plan_owner` only on the surviving short list, wrapped so an
      unreadable header yields owner `None` (dropped) rather than an exception.
- [ ] Give it a docstring naming the measurement in this plan (99 open boxes, 11
      plans, 3 idle owners, 2026-09-17) and stating why `in_scope_status` is NOT
      the filter and why there is no time cutoff.
- [ ] Add `WORKLIST_MIGRATE_PLANS_SHOW` (default `"3"`) and
      `WORKLIST_MIGRATE_PLAN_MIN_OPEN` (default `"1"`) as module constants in
      `wl_store.py` read via `os.environ.get`.
- [ ] Register both new names in `.ci/policy/worklist-env-registry.json` (kind
      `tuning`, alongside the `WORKLIST_HANDOFF_STALE_HOURS` entry at line 279),
      in `.ci/config/env-manifest.json`, and under the
      `.claude/hooks/stop/wl_store.py` key in `.ci/config/python-env-registry.json`,
      or `check:ci-worklist-env-registry` reds.
- [ ] In `migrate_candidates` (`.claude/hooks/stop/wl_store.py:1973`), seed
      `"plans": []` on both existing candidate-dict constructions so every
      consumer sees the key unconditionally.
- [ ] Add the third pass after the STATE.md fallback loop: call
      `plan_candidates`, enrich any candidate already in `out` whose `prefix`
      matches, and append a new candidate for each remaining owner that is not
      the requesting session, not `live`, and not already covered -- with
      `counts` zeroed, `next_action` filled from `agent_next_action` when one
      exists, and `verdict`/`evidence` from `session_liveness`.
- [ ] Extend `_migrate_cli`'s `--candidates` renderer
      (`.claude/hooks/stop/worklist.py:1097-1140`) so `item_desc` reports plans
      when `total == 0` ("0 worklist item(s), but N committed plan(s) with M
      open box(es)"), and print up to `WORKLIST_MIGRATE_PLANS_SHOW` lines of the
      form `PLAN agent/PLAN-x.md  [status]  N open / M ticked` plus a `+K more
      plan(s)` tail.
- [ ] Add a `--plan <path> [<path>...]` mode to `_migrate_cli`: for each path,
      refuse a status in `FINISHED_STATES`, refuse zero open boxes, no-op with a
      message when the owner already resolves to the requesting session,
      otherwise rewrite the `Owner:` line.
- [ ] The rewrite writes `Owner: <adopter8> (adopted from <prev8> <YYYY-MM-DD>)`
      WITHIN the first `PLAN_HEADER_LINES` (10) lines -- session-shaped token
      FIRST so `PLAN_OWNER_ID_RE` picks the adopter, and never inserting a line
      that would push the header past line 10.
- [ ] In the same mode, set an existing `Updated:` line in the header to today's
      date and leave it absent when absent; touch NO box line, so
      `check:ci-plan-boxes` A0 task signatures and A1 never-deleted stay
      byte-identical.
- [ ] Have `--plan` print `npm run check:ci-plan-record -- --update` after any
      successful rewrite, because the edit changes the plan's byte size and
      `index_census` uses size as its freshness signal (`wl_planindex.py`
      module docstring) -- a stale census would otherwise put a loud banner on
      the next SessionStart.
- [ ] Make `--migrate <me> <prefix>` PRINT that prefix's open plans and the
      exact `--plan` command rather than adopting them: a store migration must
      not silently rewrite committed documents, matching the skill's own rule
      that a predecessor's STATE.md is left alone as a peer's document.
- [ ] Extend `CLI_MIGRATE_USAGE` (`.claude/hooks/stop/worklist_messages.py:773`)
      with the `--plan` form, and keep the usage text the only place the
      grammar is written.
- [ ] Teach `handoff_note` (`.claude/hooks/stop/wl_checks.py:3079`) to print a
      `PLAN <rel> [status] N open` line per candidate plan under the existing
      item lines, capped by the same constant, so a session's `## Remaining`
      guidance can name the plans; keep the block advisory and never blocking.
- [ ] Update `.claude/skills/migrate/SKILL.md`: state that a candidate can be
      named by a committed plan with open boxes and a non-live owner; fix the
      stale `WORKLIST_DEAD_HOURS` claim at line 27, which the code has read as
      `WORKLIST_HANDOFF_STALE_HOURS` (720h) since this session's fix.
- [ ] In the same skill update, extend the AskUserQuestion label rule so `<n>
      open` covers plan boxes, and document `--plan` in the "What it does and
      does not touch" table as the only thing that writes a peer's plan, and
      only when named.
- [ ] Add cases to `.claude/hooks/stop/worklist-cases/26-migrate.sh` (its `mig`
      helper at the top and the `check` form at line 272 are the models): a
      plan with open boxes owned by an aged peer appears in `--candidates`; the
      same plan with `Status: done` does not; the same plan with zero open
      boxes does not.
- [ ] Also in that suite: a plan owned by a LIVE session does not appear; an
      owner already listed for worklist items is ENRICHED rather than
      duplicated (assert the prefix appears once).
- [ ] Add the CONTROL case the suite's convention demands: a peer with 0 items,
      no STATE.md `## Next action`, and one `Status: ready` plan with open
      boxes must still be a candidate -- this is the exact live shape
      (`8f55d4f0`, `PLAN-tooling-transformation.md`) that produced nothing
      before this change.
- [ ] Add `--plan` adoption cases: the `Owner:` line is rewritten and the
      header stays within 10 lines; every `- [ ]` and `- [x]` line is
      byte-identical before and after; a second run reports the plan already
      belongs to the requesting session and changes nothing; a `Status: done`
      plan is refused.
- [ ] Regenerate `agent/INDEX.md` with `npm run check:ci-plan-record -- --update`
      after this plan file lands, since a new `agent/PLAN-*.md` changes the
      census path set and R8 compares for equality.

## Verification

Run, in order, and record the output of the first two in the commit message:

1. `python3 .claude/hooks/stop/worklist.py --migrate d778be9d --candidates`
-- must now name `agent/PLAN-tooling-transformation.md [ready] 13 open` under `8f55d4f0` and `agent/PLAN-stop-hook-overhaul.md [ready] 31 open` under `f4da5c2e`. Before the change, neither string appears anywhere in the output.
2. `python3 .claude/hooks/stop/worklist.py --migrate d778be9d --candidates --json`
-- every candidate object carries a `plans` array (possibly empty); the union of `plans[].rel` over all candidates must be exactly the 11 idle-owned plans tabulated in the Why section, and must NOT contain any plan owned by `d778be9d` or `PLAN-secret-namespace-migration.md`.
3. `npm run check:ci-hook-worklist-suite` -- the whole v5 control suite, which
sources the new `26-migrate.sh` cases. Every new case must be present in the PASS count, not merely absent from FAIL.
4. `python3 .claude/hooks/stop/test-planindex.py` -- proves the census contract
this change now depends on is untouched.
5. `npm run check:ci-plan-record` -- R8 byte-equality of `agent/INDEX.md`, after
the `-- --update` regeneration. Red here means the census was not regenerated.
6. `npm run check:ci-plan-boxes` -- A0 signatures and A1 never-deleted over the
plans `--plan` rewrote, plus G-A4 over this newly added plan (it carries open boxes and resolves `Owner: d778be9d`, so it passes by construction).
7. `npm run check:ci-worklist-env-registry` -- proves the two new `WORKLIST_*`
names are registered rather than silently unset.
8. `npm run check:ci-plan-citations` and `npm run check:ci-prose-style` -- this
plan adds a file under `agent/`; every `file:line` above was resolved against the live tree on 2026-09-17 and every `check:` key exists in `package.json`.

The negative control that makes the rest mean something: `git stash` the `wl_store.py` change and re-run step 1. It must return the four bare prefixes with no `PLAN` line at all. A verification that passes both before and after has proved nothing. </content>
