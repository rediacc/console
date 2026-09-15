# PLAN: B2 emit the matrix (within-lane sharding for ci-quality.yml)
Status: draft -- design only, not implemented
Owner: f4da5c2e

## Why

`agent/PLAN-tooling-transformation.md:3684` (box "B2 S, driver-only, long pole") asks to
"emit the matrix" for `.github/workflows/ci-quality.yml`'s quality lanes. The box's own text
went through two design revisions in place (2026-09-08 design note, then a 2026-09-09 refutation
of part of that note, then a 2026-09-14 read-only re-verification wave). This plan re-measures
everything against the tree at commit `22746ac3e` (2026-09-15) rather than trusting the box's
prose, and turns the box's own "Five pieces, in order, all driver-only" (D1-D5) into an
executable task list, plus one gap the box itself never closed: a real completeness check for
its stated acceptance criterion.

Campaign context: `agent/PLAN-tooling-transformation.md:3684` (the box, read in full through
`:3972`, the line before B3 opens), `:6043` (invariant 11's canonical definition), `:3973`
(B3, DONE, the aggregator this box's shards report to), `:3994` (B4, the sibling box that
landed `ci-quick` on 2026-09-14 and changed the lane count this box reasons over).

## 1. What "the matrix" concretely is, and why the box's own opening paragraph is describing
   a design that was abandoned

The box's first paragraph (lines 3684-3688) describes generating a single `include:` list from
`laneCanEmit()`-true lanes -- i.e. one shared job iterating a cross-lane matrix, replacing the
ten named `quality-*` jobs with matrix legs. That is the design clause (b) of the 2026-09-08
design note assumed, and it was **refuted by direct measurement on 2026-09-09** (box text,
`:3718-3737`): inserting a real `strategy: matrix: shard: [1,2]` into `quality-static` and
re-running `laneCapabilities`, `laneCanEmit`, and `regionAfterSetup` showed all three survive
unchanged, because `scripts/gate-bind.ts:308-315` (`laneCanEmit`, re-read here at its current
line numbers) finds a job by its two-space key and scans to the next two-space key; a
`strategy:` block sits at four-space indent and does not disturb that scan.

**The design that survived, and is the one this plan implements, is within-lane sharding.**
Each `quality-*` job keeps its own YAML key (`quality-code:`, `quality-static:`, ...,
unchanged, so `LANE_ORDER` in `scripts/ci-runner/lanes.ts` and branch-protection required-check
names never see a rename); a job that is sharded gets its own
`strategy: { fail-fast: false, matrix: { shard: [1..N] } }` block, and gate-bind ANDs
`matrix.shard == N` onto the `when` of every step it emits into that job's region
(`scripts/gate-bind.ts:616-626`, already built). There is no cross-lane `include:` list, and
the box's own opening paragraph should be read as superseded by its own later text, not as the
current design.

## 2. Current state of the generator: mechanism partially built, deliverable (D1-D5) not started

Re-verified live, 2026-09-15 (spot-checked by the driver directly: `SHARD_COUNTS` confirmed
empty, `rewriteStrategyRegions` confirmed absent, `6b1a1b060` confirmed a real commit, both
named lanes confirmed still without `- id: setup`):

| Piece | Status | Evidence |
|---|---|---|
| `laneCanEmit` (invariant 11 mechanism) | Built, unchanged | `scripts/gate-bind.ts:308-315` |
| `shardAssignment` (leg lookup from `SHARD_COUNTS` via `shardPlan`) | Built, unchanged since 2026-09-09 | `scripts/gate-bind.ts:459-472` |
| Conjunct-writing inside `rewriteRegions` (ANDs `matrix.shard == N` onto a step's `when`) | Built, unchanged | `scripts/gate-bind.ts:564-635`, called from `--write` at `:1791` |
| `SHARD_COUNTS` (the knob) | Present, deliberately empty | `scripts/ci-runner/lanes.ts:393` |
| B3 aggregator, static + runtime halves, `--receipts DIR` consumer | DONE (box B3, `:3973`) | `scripts/gates/check-quality-complete.ts`, registered, `job: 'quality-code'` at `scripts/ci-runner/manifest.ts:4966` |
| `rewriteStrategyRegions` (D3: emit the `strategy:` block itself) | **Does not exist** | `grep -rn rewriteStrategyRegions scripts/` = 0 hits |
| `strategy:` block or `# >>> gate-bind strategy` marker anywhere in the workflow | **Does not exist** | `grep -n "gate-bind strategy\|strategy:" .github/workflows/ci-quality.yml` = 0 hits |
| `step?: string` on `ShardInput` / step-level merge rule (D1) | **Not implemented** | `scripts/ci-runner/lanes.ts:207-218`, no `step` field |
| `SHARD_REPLICATED_MAX` / replicated-share refusal (D2) | **Does not exist** | 0 hits repo-wide |
| Per-step `id:`, receipt-writing step, `quality-shard-N` artifact upload (D4) | **Not implemented** | no `toJSON(steps)` / `quality-shard-` hits in `scripts/gate-bind.ts` or the workflow |
| D5 static clauses (matrix values == `[1..N]`; move `check:ci-quality-complete`'s own `lane:` off a shardable lane) | **Not implemented** | `check-quality-complete.ts`'s own gate header still declares `lane: quality-code` (`scripts/gates/check-quality-complete.ts:59`) |
| Two selftest controls for the conjunct path (shard-assigned lane emits correctly; unsharded lane emits byte-identically) | **Missing**, confirmed by grepping `selftest()` for `shard` -- 0 hits | `scripts/gate-bind.ts:848-1100` |
| Stale comment `scripts/gate-bind.ts:571` ("today only one lane is in `SHARD_COUNTS`") | **Still stale** (SHARD_COUNTS is empty) | unchanged since 2026-09-09 |

`git log` on `scripts/gate-bind.ts` and `scripts/ci-runner/lanes.ts` shows no commit since
`1ae84c3e3` (2026-09-09); the 2026-09-14 wave that re-derived D1-D5 was explicitly read-only
(isolated worktree, primary tree owned by a `pr-babysit` agent). **This is not a stale-box/
already-done situation like W7P4-W or W9-P2. B2 is genuinely unstarted at the deliverable
level**; what exists is scaffolding from an earlier, narrower wave (leg lookup + conjunct
emission + the aggregator), built and proven inert, with the actual "emit the matrix" work
(D1-D5) never begun.

## 3. Invariant 11: still accurate, but its own canonical text is stale on lane count

Canonical definition, `agent/PLAN-tooling-transformation.md:6043`: "A gate-bind region may only
be emitted into a lane that has an `- id: setup` step. Verified: eight of ten lanes have one;
`quality-branch:507` and `quality-submodule-branches:587` do not... Gates needing
`fetch-depth: 0` and the PR head ref stay hand-registered in `quality-branch`."

"Handled by construction" means: `laneCanEmit()` (`scripts/gate-bind.ts:308-315`) is a pure
scan of a job's block for a literal `- id: setup` line, and `--write`'s emission path
(`:1757`) refuses to place a region in a job where that returns false. That mechanism is
unchanged and still correct today.

**What has drifted**: the "eight of ten" count. `ci-quick:` landed 2026-09-14 (commit
`6b1a1b060`, box B4's job half -- landed for real, not left in an isolated worktree as B4's
last note implies; worth flagging to whoever owns B4's status). Recount, 2026-09-15, over
`.github/workflows/ci-quality.yml`'s 11 top-level jobs:

- **9 lanes have `- id: setup`**: `ci-quick`, `quality-static`, `quality-code`,
  `quality-content`, `quality-packages`, `quality-i18n`, `quality-www-build`,
  `quality-security`, `quality-go`.
- **2 lanes do not**: `quality-branch`, `quality-submodule-branches` (still exactly the two
  named in the box; the claim is verified accurate as of 2026-09-15).
- **Of the 9 setup-having lanes, only 6 hold a `# >>> gate-bind` region**: `quality-static`,
  `quality-code`, `quality-content`, `quality-i18n`, `quality-www-build`, `quality-security`.
  `ci-quick`, `quality-packages`, `quality-go` have a setup step but **zero** gate-bind
  region -- entirely hand-written despite passing `laneCanEmit`. This reproduces the box's own
  2026-09-09 clause (a) finding exactly (then: 8 `laneCanEmit`-true / 6 region-holding; now: 9
  / 6, because `ci-quick` is new and is itself setup-having/region-less).

Invariant 11 itself needs no code change. Its prose in the invariants list (`:6043`) is stale
on the lane count and should be corrected to "nine of eleven" (or reworded to not hardcode a
count) whenever this box lands, as a one-line side fix, not part of the D1-D5 critical path.

## 4. Acceptance criterion: no gate exists, and the criterion as literally worded describes
   the abandoned cross-lane design, not the surviving within-lane one

Box text (`:3689-3693`): "matrix-lane set UNION hand-written-quality-job set EQUALS the
top-level job set, with empty intersection... Plus: step-name multiset unchanged per lane...
`dropped` empty; actionlint green; every shard's `runs-on`/`timeout-minutes` equal to its
pre-rewrite lane's."

No such gate exists. `scripts/gates/check-quality-complete.ts` checks shard-count/receipt
wiring only for lanes already present in `SHARD_COUNTS` (`:390-408`); it never asserts anything
about lanes NOT in `SHARD_COUNTS`, and never asserts a completeness partition over the full job
set. `grep`-ing `scripts/gates/*.ts` for anything matrix/lane-set-shaped beyond
`check-quality-complete.ts` finds nothing else relevant.

**The criterion also needs restating**, for two reasons, both confirmed live:

1. It was written against the abandoned cross-lane `include:` design (section 1). Under the
   surviving within-lane design there is no single generated `include:` list to check against
   a "top-level job set" -- each lane keeps its own key regardless of whether it is sharded.
   The equivalent, correctly-scoped check is: **every job that CAN and DOES get a generated
   `strategy:`/conjunct region is disjoint from an explicit hand-written-lane allowlist, and
   their union is the full job set.**
2. The two-set partition (region-bearing vs. the two named no-setup lanes) does not cover the
   tree as measured: `ci-quick`, `quality-packages`, `quality-go` are setup-having,
   region-less, entirely hand-written jobs that fall into neither of the box's two named sets.
   They are hand-written by omission (nobody has registered a manifest gate against them),
   not by declared design the way `quality-branch`/`quality-submodule-branches` are (invariant
   11 forbids a region there outright). A completeness gate that infers "hand-written" from
   "has no region today" would silently grandfather in any future lane that simply never got a
   gate registered -- the wrong shape for a gate whose job is to catch exactly that drift.

**Design for the corrected gate** (new, not previously specified in the box): a static clause,
either inside `check-quality-complete.ts` or a new small gate, asserting:
- `REGION_LANES` = jobs with a `# >>> gate-bind` marker (computed the same way `laneCanEmit`
  scans a job block, generalized to "has a region" per the box's own clause (a) correction, not
  `laneCanEmit()`).
- `DECLARED_HAND_WRITTEN_LANES` = an explicit, named constant (not inferred), starting as
  `['quality-branch', 'quality-submodule-branches']` -- the two invariant-11-mandated lanes --
  with `ci-quick`, `quality-packages`, `quality-go` requiring an explicit decision (either add
  them to this constant with a `why:`, or register manifest gates against them so they earn a
  region; this plan does not decide that, it only makes the gap visible instead of silent).
- Assert `REGION_LANES ∪ DECLARED_HAND_WRITTEN_LANES` equals the workflow's full job set,
  intersection empty, both directions (a lane in both, or in neither, reds by name).
- Assert no lane in `DECLARED_HAND_WRITTEN_LANES` has an `- id: setup` unless it is one of the
  two invariant-11 lanes (i.e. don't let the allowlist quietly absorb a setup-having lane
  without a recorded reason).

## 5. What B2 still owes: the five pieces (D1-D5), re-verified against today's line numbers

All of D1-D5 below are the box's own design (`:3901-3972`), re-verified live and unimplemented.
Order matters: D1 changes the unit of planning that D2-D5 build on.

**D1. Shard over emitted steps, not lock ids.**
- Add `step?: string` to `ShardInput` (`scripts/ci-runner/lanes.ts:207-218`; `GateSpec` already
  carries `ci.step`, confirmed at `scripts/ci-runner/manifest.ts:4967`, so the real lock drives
  it unchanged).
- In `shardPlan`, add a fifth merge rule immediately after the mutex merge and before the
  `needs` merge: group a lane's entries by `ci.step` and union each group, heavy peak counted
  as ONE for a shared-step unit (mirroring `concurrentHeavy`'s existing treatment of a
  mutex-only unit, `scripts/ci-runner/lanes.ts:583-585`).
- Widen the `overloaded` refusal (`scripts/ci-runner/lanes.ts:572-579`) so a shared-step unit
  is not caught by it.
- This directly fixes Finding 1(i)/(iii) from the box: `quality-code`'s 100 lock ids collapsing
  to 99 steps because `check:lint*` (5 ids) share one `Lint` step, and the "8 heavy" refusal
  actually being "2 heavy steps" once counted in the workflow's currency.

**D2. Refuse the id/step gap instead of emitting it.**
- `shardAssignment` returns `{ legs, replicated }`, where `replicated` is the lane's lock
  entries whose step is not one gate-bind emits (Finding 1(ii): 33 of `quality-code`'s 100
  entries have no step inside the region today).
- `--write` prints them by name with their lane share, every run.
- Add `SHARD_REPLICATED_MAX: Record<string, number>` beside `SHARD_COUNTS`
  (`scripts/ci-runner/lanes.ts:393`), as a fraction; refuse when the replicated share exceeds
  it. This is what would have caught the `quality-security` back-out (`:3754-3771`)
  automatically instead of by hand.

**D3. Emit the `strategy:` block; do not hand-write it.**
- New function `rewriteStrategyRegions(workflow, counts)` in `scripts/gate-bind.ts`, called
  from the `--write` path just before the existing `rewriteRegions` call
  (`scripts/gate-bind.ts:1791`).
- New marker pair at the job's four-space indent, between `timeout-minutes:` and `steps:`:
  `# >>> gate-bind strategy (generated; do not edit inside)` /
  `# <<< gate-bind strategy`, holding `strategy: { fail-fast: false, matrix: { shard: [1..N] } }`
  from `SHARD_COUNTS`. `continue-on-error` stays banned.
- Refuse in both directions: a lane in `SHARD_COUNTS` with no strategy region refuses with the
  exact YAML to paste; a strategy region for a lane not in `SHARD_COUNTS` refuses as a drain.
- Leave `name:`, `runs-on`, `timeout-minutes` literal and untouched, so `laneCapabilities`,
  `WATCHDOG_NO_RETRY_PATTERNS` (matches `Quality` by `String.includes`), and CHECK 3
  (`.ci/rediacc_ci/security/workflow_gates.py:631`, `timeout-minutes <= 14` for `ubuntu-slim`)
  read what they read today.
- **Operator ask required before this lands for the first real lane**: if the job's rendered
  check name is a required branch-protection check, confirm the design (`name:` unchanged, so
  the rendered name is unchanged) does not itself require a branch-protection update -- but the
  ask should happen regardless per the box's own instruction, since it is the one consumer
  outside this tree.

**D4. Make the leg's receipt count what ran, not what was planned.**
- `check:ci-quality-complete`'s `--receipts DIR` consumer already exists and expects
  `{ lane, index, of, result, gates, source }` (`scripts/gates/check-quality-complete.ts:96-106`,
  `readReceipts` at `:112`) -- only the *producer* inside the workflow step is missing.
- Give each conjuncted step (post-D1 merge, one per STEP) an `id:` (`gate_` + the gate id with
  `:`/`-` mapped to `_`).
- Emit one final unconjuncted step, `if: always()`, that writes the receipt from
  `toJSON(steps)`, `job.status`, `matrix.shard`, and the leg count, counting a step as run when
  its outcome is not `skipped`.
- The `gates` field must be in lock-id currency (matching `readReceipts`'s expectation), so
  gate-bind also emits a step-id -> lock-id map into that step's `env:`.
- Upload as `quality-shard-${{ matrix.shard }}`; the aggregator job downloads the set and runs
  `check:ci-quality-complete -- --receipts <dir>`.
- This is the fix for Finding 2 (the vacuity): an all-skipped leg reports `gates: 0` against a
  plan that says N, instead of reporting green having run nothing.

**D5. Two static clauses `check:ci-quality-complete` does not have yet.**
- For each lane in `SHARD_COUNTS`, assert the job's `matrix.shard` list equals `[1..N]`
  exactly, both directions.
- Move `check:ci-quality-complete`'s own declared `lane:` off any lane that can be sharded.
  Verified still `lane: quality-code` today (`scripts/gates/check-quality-complete.ts:59`,
  matching `job: 'quality-code'` at `scripts/ci-runner/manifest.ts:4966`) -- if `quality-code`
  is ever the first lane sharded, this gate's own aggregation step would be conjuncted onto one
  leg of the very lane it polices and silently skip on the others. Retarget it to a lane that
  will never be sharded (e.g. `quality-branch`, one of the two invariant-11 hand-written lanes,
  since those can never hold a `strategy:` region by construction) or a dedicated always-run
  step. This is a driver-only registration change (`package.json` + `manifest.ts` +
  the workflow step, one writer, per invariant 13).

**Plus, before any `SHARD_COUNTS` entry is populated (not optional, per the box's own "AND ONE
GAP IN THE CONTROLS" note, `:3965-3972`)**: add the two missing selftest controls to
`scripts/gate-bind.ts`'s `selftest()` -- a lane WITH an assignment emits `matrix.shard == N` on
exactly the steps the plan gives that leg, and a lane WITHOUT one emits byte-identically to
today. Confirmed live: `grep` for `shard` inside the selftest block returns zero hits.

**Plus, a one-line fix in passing**: `scripts/gate-bind.ts:571`'s comment ("today only one lane
is in `SHARD_COUNTS`") should read "no lane is" -- still stale, confirmed live.

## 6. Explicitly out of scope for this box

- **Populating `SHARD_COUNTS` for `quality-code` or any other lane.** The box's own Finding 3
  measured real CI runs (568s/644s wall clock against a 15-minute budget) and found the region
  coverage ceiling is 1.46x at today's step granularity -- "sharding first buys 1.3x and pays 4x
  of runner for it." The prerequisite work (splitting the composite `Lint` step into its five
  declared gates; giving `check:types` and `check:ci-dead-bash` real declarations so they enter
  the region) is a distinct, larger effort not named as one of the box's five D-pieces. D1-D5
  build the mechanism correctly for whichever lane is chosen later; this plan does not choose
  one, matching the box's own back-out precedent (`quality-security`, populated then reverted
  because the ranking inverted once lock-ids were counted as workflow steps).
- **Deciding whether `ci-quick`, `quality-packages`, `quality-go` should ever get a region.**
  Section 4's new completeness gate only requires that decision be made *explicit*, not that it
  be made *here*.
- **`.github/workflows/**` is a MUTEX file per the driver contract** (W8 P1, W3 P3, W7 P4, E2 all
  collide on it). Confirm no concurrent writer holds it before starting D3/D4.
- **Serialization with C2** (`agent/PLAN-tooling-transformation.md:4426`, still `[ ]`, `pathsOrigin`
  required whenever `paths` is present): both boxes touch `scripts/gate-bind.ts`. Confirm C2 is
  not in flight before starting; do not run concurrently.

## Tasks

- [ ] Confirm no concurrent writer holds `.github/workflows/ci-quality.yml`, `scripts/gate-bind.ts`,
      or `scripts/ci-runner/lanes.ts` (driver-only mutex files); confirm C2 is not in flight.
- [ ] D1: add `step?: string` to `ShardInput` (`scripts/ci-runner/lanes.ts:207-218`); add the
      fifth merge rule (group by `ci.step`, union, heavy-peak-as-one) to `shardPlan`; widen the
      `overloaded` refusal exemption for a shared-step unit.
- [ ] D2: `shardAssignment` returns `{ legs, replicated }`; `--write` prints replicated entries
      by name and lane share; add `SHARD_REPLICATED_MAX` beside `SHARD_COUNTS`; refuse when the
      replicated share exceeds the declared ceiling.
- [ ] D3: implement `rewriteStrategyRegions(workflow, counts)` in `scripts/gate-bind.ts`; new
      `# >>> gate-bind strategy` / `# <<< gate-bind strategy` marker pair; call from `--write`
      just before `rewriteRegions` (`scripts/gate-bind.ts:1791`); refuse in both directions;
      leave `name:`/`runs-on:`/`timeout-minutes:` literal. Ask the operator before this lands
      against any real lane, per the box's branch-protection caveat.
- [ ] D4: per-step `id:` (post-D1 merge, one per emitted step); one final `if: always()` receipt
      step writing `toJSON(steps)` + `job.status` + `matrix.shard` + leg count, counting
      non-`skipped` outcomes; step-id -> lock-id map in the receipt step's `env:`; upload as
      `quality-shard-${{ matrix.shard }}`; wire the aggregator job to download and run
      `check:ci-quality-complete -- --receipts <dir>` (the `--receipts` consumer already exists,
      `scripts/gates/check-quality-complete.ts:410-419`, verify the receipt shape matches
      `ShardReceipt` at `:96-106` exactly).
- [ ] D5a: add the static clause asserting, for each `SHARD_COUNTS` lane, the job's
      `matrix.shard` list equals `[1..N]` exactly, both directions.
- [ ] D5b: retarget `check:ci-quality-complete`'s own gate-header `lane:` off `quality-code`
      (currently `scripts/gates/check-quality-complete.ts:59`, matching
      `scripts/ci-runner/manifest.ts:4966`) onto a lane that can never be sharded (e.g.
      `quality-branch`); this is a driver-only `package.json`/`manifest.ts`/workflow-step edit,
      one writer, landed in the same commit per invariant 13.
- [ ] Add the two missing selftest controls to `scripts/gate-bind.ts`'s `selftest()`: a lane
      WITH an assignment emits `matrix.shard == N` on exactly the steps the plan gives that leg;
      a lane WITHOUT one emits byte-identically to today. Required before any `SHARD_COUNTS`
      population, per the box's own gap note.
- [ ] Fix the stale comment at `scripts/gate-bind.ts:571` ("today only one lane is in
      `SHARD_COUNTS`" -> "no lane is").
- [ ] New completeness gate (or new static clause in `check-quality-complete.ts`): define
      `DECLARED_HAND_WRITTEN_LANES` explicitly (starting `['quality-branch',
      'quality-submodule-branches']`); assert `REGION_LANES ∪ DECLARED_HAND_WRITTEN_LANES`
      equals the workflow's full job set with empty intersection, both directions; assert no
      lane in the allowlist has `- id: setup` unless it carries a recorded `why:`. Surfaces
      `ci-quick`, `quality-packages`, `quality-go` as an explicit open decision rather than a
      silent gap.
- [ ] Update invariant 11's prose (`agent/PLAN-tooling-transformation.md:6043`, "eight of ten
      lanes") to match the current 9-of-11 count, or reword to not hardcode a count.
- [ ] Correct B4's status note about `ci-quick` (box `:4029-4033` says it stays `[ ]` "until it
      lands in the primary tree" -- `git log` shows commit `6b1a1b060` on 2026-09-14 landed it
      for real). Flag to whoever owns B4, out of this plan's direct scope but noted since B2's
      lane count depends on it.
- [ ] Re-run `check:ci-gates-lock`, `check:ci-parity`, `check:ci-gate-bind --write` (dry-run
      first), `actionlint`, and the new completeness gate after each piece lands; confirm
      `dropped` stays empty and every shard's `runs-on`/`timeout-minutes` match its pre-rewrite
      lane's, per the box's stated acceptance criteria.

### Critical Files for Implementation

- /home/developer/console/scripts/ci-runner/lanes.ts
- /home/developer/console/scripts/gate-bind.ts
- /home/developer/console/scripts/gates/check-quality-complete.ts
- /home/developer/console/.github/workflows/ci-quality.yml
- /home/developer/console/scripts/ci-runner/manifest.ts
