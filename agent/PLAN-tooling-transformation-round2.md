# PLAN: Tooling Transformation, Round 2
Status: ready
Owner: 8f55d4f0
Updated: 2026-09-07

Supersedes the open half of `.claude/plans/let-s-ultrathink-and-make-lazy-pudding.md`
(an UNTRACKED harness plan, which is why this one is tracked: an untracked plan does
not survive a compaction, and W12 exists to stop exactly that).

Status: READY. Supersedes the open half of `let-s-ultrathink-and-make-lazy-pudding.md` and the
wave tables in `docs/ci-overhaul/12-remaining-work.md`. Drafted 2026-09-07 by four parallel
planning agents over a full re-measure, with every load-bearing claim spot-checked against the
tree by the synthesiser. Where the predecessors disagree with this file, this file was measured
today and they were not.

Branch `0906-1`, HEAD `19c45c78e`.

---

## Read this first: three axes, never collapsed

The programme's headline was "quality gates ported: 77 of 77 (100%)". That number is true and
it is not progress. It describes artifacts existing. Every workstream reports three numbers:

- **PORTED** a Python twin exists
- **LIVE** CI actually invokes it
- **DELETED** the bash twin is gone

For the `.ci` quality gates those are **78 / 0 / 0**. Zero references to `rediacc_ci/quality`
exist in `package.json`, `scripts/ci-runner/manifest.ts`, `.github/workflows/ci-quality.yml` or
`scripts/ci-runner/gates.lock.json`. What CI runs is 69 bash gates plus 43 Python gates that
were never part of the port. That is the design (invariant 5 forbids deleting a twin in the
change that ports it), but "100%" as a headline reads as finished, and it is not.

---

## Measured baseline (2026-09-07)

Cite the command, not the number. A box that pins a count is wrong by construction.

| Fact | Value | Command |
|---|---|---|
| Tracked `.sh` under `.ci`/`.claude` | 581 | `git ls-files \| grep -E '^(\.ci\|\.claude)/.*\.sh$' \| wc -l` |
| Bash ruling 7 says must go | **521 files / 129,342 lines** | `bashFiles` in `.ci/config/language-policy-baseline.json` |
| Permanently exempt by name | 64 (media 13, breakpoint 24, tutorials 27) | 3 `tree:` entries in `.ci/policy/.language-policy-allowlist` |
| **Bash files DELETED so far** | **0** | -- |
| Bash LOC with a Python twin | 29,329 (23%) | gates 18,206 + 64 gate tests 10,851 + 2 shimmed libs 272 |
| Bash LOC still untwinned | **100,013 (77%)** | -- |
| Python already written | 174,870 lines | `git ls-files '.ci/**/*.py' '.claude/**/*.py' \| xargs wc -l` |
| Port expansion ratio | 2.56x (gates), 1.43x (gate tests) | 46,523/18,206 and 15,523/10,851 |
| **Python still to write** | **143,000 - 256,000 lines** | 100,013 x the ratio band |
| Gate tests ported / live / deleted | 64 of 149 / 64 / 0 | `grep -rh '^BASH_TWIN' .ci/rediacc_ci/tests/gates/*.py \| sort -u \| wc -l` |
| Workflow-invoked scripts shimmed | 0 of 215 (348 call sites) | `grep -rhoE '\.ci/scripts/[A-Za-z0-9_./-]+\.sh' .github/workflows/` |
| `deploy/` + `release/` ported | 0 of 48 | -- |
| Bash libs shimmed | 2 of 15 | `age-check.sh:62`, `find-port.sh:68` |
| Lock entries | 458 total, 448 `gate: true`, 149 gate tests, 95 slow, 45 with `paths` | `gates.lock.json` |
| Workflow steps region-emitted | 150 of 276; **126 hand-written** | walk the `>>> gate-bind` markers |
| Plan boxes ticked | 81 of 131 | -- |
| Milestones met | **2 of 12** (M2, M4) | -- |

**The honest headline: 0 of 521 bash files deleted, 23% twinned, 2 of 12 milestones.** The 62%
box figure measures drafting, not shipping. By eventual-Python volume the programme is roughly
41-55% through; by deletion it is at zero.

---

## M-1: the wave is unlanded, and it precedes everything

Branch `0906-1` (upstream `origin/tooling-transformation-w0`) is **115 commits ahead of
origin/main and 0 behind**, **1,198 files changed, +174,362 / -25,205**, with **no open PR**
(`gh pr list --state open` returns `[]`). Every measurement above describes a tree nobody has
reviewed or merged. Land it first: the longer it sits, the worse the merge, and every number
here drifts under it.

---

## Corrections to the predecessor plans

Nine pinned counts were stale, four premises false, three prerequisites missing.

| Previous claim | Measured today |
|---|---|
| W1 P4: 67 `sys.path` files | **68**, and it rises with every port |
| W7 P3: 41, then 53 ported; 148 tests | **64 of 149**; remaining **85** |
| W7 P4: 201 scripts / 334 call sites | **215 / 348** -- the surface GREW |
| W5: 374 `check` / 21 `check_out`; M5's 395 | **398 / 24**, so **422** |
| W12 P2.8: 32 compacted, next red 09-25 (2) | **31**; next red **2026-09-26 (3)**; warn band **09-19** |
| Requirement 15: 8 / 8 / 20 json | **9 / 16 / 24** |
| W8: 1,014 env names | **745** under a stated method; 1,014 is not reproducible |
| TRAPS floor 75 | **77 / 77** |
| M11: 46 records | **32** (31 compacted + 1 parked) |
| W6 P5: `LEGACY_ARMS_MAX` reaches zero | **the name does not exist.** The budget is a partition assertion at `test-run-sh.sh:278-306,:329` plus a 120-line `run.sh` ceiling at `:372-375`. run.sh is at **120 of 120** |
| W9 P2: baseline is "one sorted array" | an **object** with 42 `unguarded` entries. Hazard stands, description does not |
| Gaps: "the language-policy gate does not exist" | it exists, registered three-point, and **blocks on growth** |
| W12 P2.7: "A5 in `04-decisions.md`" | **not there.** A5 is a gate rule at `check_plan_boxes.py:41,:428`. P3.2's "A6" DOES mean `04-decisions.md:22-23`. Two schemes, adjacent boxes |
| Gaps: `private/growth` submodule PR | **not a submodule.** `.gitmodules` lists four; `.gitignore:85` ignores it |
| W8 P1: "exactly two agents" | **one writer.** The residue is ~24 entries of one secret name on a single-writer file, and all four directions are already gated |

---

## Three prerequisites no box owned

### P-A. A header on a port is a CUTOVER, not a registration

`derivedId()` (`scripts/lib/gate-header.ts:235-238`) maps `.ci/rediacc_ci/quality/npmrc.py` to
`check:ci-npmrc`, the id its live bash twin already owns (`package.json:121`).
**CORRECTED 2026-09-07 BY MEASUREMENT: the split is 59 colliding / 18 not, NOT "all 77,
zero do not".** Two independent runs of `derivedId()` over `.ci/rediacc_ci/quality/*.py`
agree on it. The overstatement is worth keeping visible because the CONCLUSION survives it
while the obvious go/no-go test does NOT: an agent told "all of them collide" writes no
header, but an agent told "18 are free" needs to know that those 18 are ALSO unwritable, for
three different reasons. Seven have twins under an ABBREVIATED id `derivedId` never produces
(`label_references` -> `check:ci-label-refs`, `no_app_admin_perm` -> `check:ci-app-admin-perm`,
and five more), so they look free to any lock-keyed grep. Nine are invoked straight from a
workflow with no `package.json` key at all, a registration shape gate-bind's verifier does not
model. Two are referenced nowhere.

**AND THE AUTHORITY IS `package.json`, NOT THE LOCK.** `release_state.py` derives
`check:ci-release-state`, which is ABSENT from `gates.lock.json` and PRESENT in
`package.json`. A go/no-go test of "confirm the id is absent from the lock" passes it and
produces a red gate. That test was mine, and it was wrong.

`gate-bind`'s check arm is fail-closed on all of this. The binder already scans the
package (`gate-bind.ts:98`, `inScope` at `:201-202`, self-control at `:1069`), so this is not a
tooling gap -- it means the 78 headers cannot land as a cheap preparatory box. **They ARE
W7 P4 for the quality tree**, one atomic commit per gate. This is the largest re-ordering here.

### P-B. A gate cannot declare `env:` -- or an extra `if:` conjunct

`scripts/ci-runner/gate-spec.ts` has no `env` field (complete list: noProfile, id, run, gate,
needs, mutex, reads, weight, heavy, paths, slow, qualityGateTest, leaves, ci) and
`emitStep` (`gate-bind.ts:408-419`) hardcodes
`if: ${{ !cancelled() && steps.${guard}.outcome == 'success' }}` with no extension point.
**Six gate files already carry the literal blocker string `gate-bind cannot emit one`** and sit
at `emit: false` for that reason alone; ~14 steps carry an extra `if:` conjunct. All 26 `env:`
blocks sit outside the regions, which is why 126 of 276 steps are hand-written. Fixing `env`
alone leaves those unshardable. This is W2.4's missing `reads?: string[]` recurring, and it
violates the programme's own acceptance test at `08-driver-contract.md:377-385`.

Two further holes in the same machinery:
- `gate-bind.ts:1567-1569` filters `dropped` to `claimed` and refuses only on `claimed`. Bare
  `dropped` is never printed on the write path and never asserted empty -- the 2026-09-05
  four-deleted-steps shape, still open.
- **Nothing in the tree checks a step's `env:` at all.** `check-ci-parity.ts:29` states as a
  design rule that an `env:` value is not an invocation. Strip `DOCKERHUB_TOKEN` from
  `ci-quality.yml:1159` in a scratch copy today and the whole battery stays green.

### P-C. 142 of the 521 files are named by no plan box

**VERIFIED INDEPENDENTLY 2026-09-07, and the first attempt to check it was WRONG in the
plan's favour.** Sampling the directories this section lists as examples gives 99, not 142,
which looks like a refutation and is not: the set is the COMPLEMENT, so it also holds
`.ci/scripts/test` (32 files, `run-all.sh` among them) which no example directory names.
Computing it properly -- baseline 521, minus the quality twins, the gate tests, deploy,
release, the bash libs and the `.claude` trees, all of which a box does name -- leaves
**142 exactly**. Recorded because the narrow sample is the check a hurried reader would run,
and it would have produced a confident false correction.

**29,057 lines, 22% of the backlog**, unexamined since the baseline was generated today:
`.ci/scripts/test` non-gate infra 32, `ci` 17, `build` 17, `autopilot` 16, `infra` 11,
`private` 9, `security` 9, `housekeeping` 6, `review` 4, `version` 4, `.ci/docker` 8, `setup` 3,
`env`/`pr`/`signal` 3, `.ci/bootstrap.sh`, `.ci/config/constants.sh`,
`.claude/lib/standing-orders-brief.sh`.

**A new shim is illegal.** `check_language_policy.py:143` sets `SHIM_MAX_LINES = 1`. The two
existing shims are 127 and 145 lines and survive only because both are grandfathered INSIDE the
baseline; any new one is an addition that `write_verdict` (`:441`) refuses even when the total
shrinks. Only **3 files repo-wide** have a one-line effective body. So the allowlist is not an
escape route: **~500 of the 521 must be deleted, not exempted.** Defensible exemptions are the
chicken-and-egg and container-entrypoint classes -- `.ci/bootstrap.sh` (395 lines; it exists
because these hosts have no pip, uv or pytest), the five `.ci/docker` entrypoints, and
`.ci/config/constants.sh`. Roughly 8 files. **The allowlist has no slot for a 395-line
exemption** -- either move `bootstrap.sh` into `.ci/bootstrap/` and use a `tree:` entry, or add
a third kind. Naming it now avoids an unresolvable red at the strict flip.

---

## Four tracks, disjoint by file

- **T-PORT** the `.ci` port. The critical path and the largest body of work.
- **T-SCHED** schedule and platform: the P-B unblocker, W3 P3, W2.3, W2.5, W5 P7, W6 P3/P4/P5.
- **T-ENV** environment, secrets, policy: W0.0/W0.1, W8 P1-P6, W4 P3/P4/P5.
- **T-DOCS** docs, records, layout, gaps: W9 P2, W11 P4/P5/P6, W12, and the unowned gaps.

---

## T-PORT

- [ ] **PRE-A0 S** `check-ci-parity` learns `python3 -m`. `resolveLeaves` (`check-ci-parity.ts:139-228`)
      has no `python3` arm, so `python3 -m rediacc_ci.quality.npmrc` resolves to the bare token
      `python3` and `leaves` can never match. ~40 lines + 4 controls.
      **Acceptance:** every `-m` body resolves to its tracked module path; no entry resolves to
      `python3`. Both directions.
- [ ] **PRE-A1 S** One canonical import line. `pyproject.toml:249` gives tests `pythonpath = [".ci"]`;
      non-test callers have no equivalent, so each entry point carries a `sys.path.insert`. After
      A0 the canonical form is `PYTHONPATH=.ci python3 -m ...` with no hop at all. Converts the 15
      in `.ci/scripts/quality` plus `check_pytest.py`. **Acceptance:** the `sys.path` file set is a
      strict subset of the set at box start, printed by name; no file under
      `.ci/rediacc_ci/quality/` acquires one.
- [ ] **W7P3-a..d C, 2 writers** The 52-53 admissible gate tests, four batches of 13.
      **Batch membership is derived, never chosen:** `ALL(149) - DONE(64) - REAL_TREE - SHADOW`.
      Read the real-tree set FROM `gates.lock.json` (4 `mutex tree:` + 23 `reads tree:` = 27
      entries), and exclude a `test-X.sh` whose subject `check-X.sh` is named by any of the 78
      ledgers. Today: **85 remaining = 53 admissible + 32 needing care** (26 real-tree,
      13 shadow-entangled, 7 both). Match ledger basenames as WHOLE TOKENS -- a substring match
      hits `common.sh` from `d.sh` and excludes 47 instead of 7.
      **Acceptance per module:** ported case SET equals the twin's under the widened word-match
      (not the flat PASS-count floor, which is the failing-open path batch 5 found); a defect
      planted in the REAL subject caught by both sides; subject restored byte-identical by
      sha256; the batch asserts no ported twin is in the real-tree set, read from the lock.
      **Runtime:** `check:ci-pytest` is `slow: true`, `weight: 8`, `-n 8 --dist loadgroup`,
      measured 381.41s against a **294.65s floor set by the guards fixture pinned to one worker**
      -- so the first ~87s of added work is absorbed by spread. Re-tier after every batch, in the
      quiesced reference worktree only (invariant 14).
- [ ] **W7P3-RT S, 1 writer** The 26 real-tree twins. `xdist_groups.group_for()` already returns
      `REAL_TREE_GROUP`, but `test_twin_parity.py:211-219` **refuses outright** to drive any
      ported twin in that set: the isolation machinery exists and the parity driver forbids using
      it. Replace the blanket refusal with a per-module opt-in (`REAL_TREE_TWIN = True`) that also
      requires `REAL_TREE_GROUP`. These 26 include `test-ci-parity.sh`, `test-language-policy.sh`,
      `test-gate-anti-vacuity.sh` and `test-dead-bash.sh` -- the instruments this slice is
      measured by. Port last, never two per batch.
- [ ] **W7P3-BAT S** Wire `battery.py` (811 lines, referenced by nothing), retire `run-all.sh`
      (620 lines, live at `package.json:148` and `:337`).
      **Hard precondition:** `run-all.sh` is itself one of the 142 unnamed files AND one of two
      isolation sources for `real_tree_twins()`. Every `*_FALLBACK` member must first appear as a
      `tree:` declaration in the lock. **Acceptance:**
      `real_tree_twins(lock, runner=/dev/null) == real_tree_twins(lock, runner=run-all.sh)` as a
      SET -- that equality IS the retirement licence and is checkable before anything is deleted.
      Re-key the `PATTERN="test-*.sh"` glob discovery `check-dead-bash.ts:19-20` depends on, same
      change (invariant 2).
- [ ] **W7P4-Q S batches, 2 writers** The quality-tree cutover -- this is P-A. Six batches of 13.
      **One convention, decided: all 77 declare directly in the package module, no entry point.**
      An entry point costs one `sys.path.insert` per gate; after A0/A1 the direct form costs zero.
      Per gate, one atomic commit: header into the `.py`, header out of the `.sh`, `package.json`
      body repointed, `manifest.ts` leaves repointed, step re-emitted. **The bash twin stays on
      disk** -- the K=5 ledger licences the cutover, not the deletion.
      **Acceptance:** `check:ci-gate-bind` is the oracle and is already fail-closed. Set-based:
      the id sets declared under `.ci/rediacc_ci/quality/` and `.ci/scripts/quality/` are
      DISJOINT and their union equals the quality ids in the lock -- one assertion catching both
      a missed twin-header removal and a missed port-header addition.
      **Also fix `check_pytest.py:74-78`** in batch 1: it still says the binder "only scans
      `.ci/scripts/` and `scripts/`" and that a header there "would be inert". False since
      2026-09-06 (`08-driver-contract.md:303-311`), and it is the only in-code statement of the
      rule anyone porting a gate will find.
      **Trap:** a NEW file not yet in a git index is invisible to the binder (`ls-files` reads the
      index). Use the throwaway-index technique in `08-driver-contract.md` section 5b, and
      validate the index copy before use.
- [ ] **W7P4-W C, 2 writers, after PRE-B2** Flip 215 distinct scripts / 348 call sites.
      **Creates no new `.sh` files** (see P-C: a new shim is illegal). Call sites flip straight to
      `npm run <id>` or `python3 -m`; the bash is retired in place.
      **Decomposition nobody had:** **61 of the 215 already have a Python port** and can flip as
      soon as P-A lands; **154 have no port at all** and are almost exactly the P-C backlog plus
      deploy/release (deploy 21, release 21, test 18, ci 15, autopilot 14, build 14, infra 9,
      private 9, security 7, housekeeping 6, quality 6, review 4). So this is two boxes: **P4a**
      the 61, **P4b** the 154.
      **Acceptance:** the set of `.ci/**/*.sh` paths in `.github/workflows/**` strictly shrinks,
      printed by name; every removed path has a lock entry whose `leaves` name the replacement
      and whose `ci.step` matches the emitted step. Both directions.
- [ ] **W7P5-a S** `deploy/` 27 + `release/` 21 = **48 files, 5,440 lines**, 46 workflow call
      sites, zero Python, zero ledgers. Golden dry-run parity plus **one real run each**, K=5
      ledger before any deletion. Each specimen its own committed git repo; new side under
      `PYTHONDONTWRITEBYTECODE=1` (`__pycache__` dirties the tree before `treeIdentity`).
      **Acceptance:** every path has either a ledger asserting `equivalence holds` at K=5 or an
      allowlist entry with a BLOCKER. No third state.
- [ ] **W7P5-b S, the true long pole** The 13 real bash libs, **6,840 lines**. `common.sh` has
      **251 sourcers** -- the highest fan-in file in the programme. Order by fan-in ascending:
      `gate-controls` (41), `bws-env` (111), `emit-advisory` (218), `service` (225),
      `blocker-validator` (237), `release-age` (237), `toolchain` (466),
      `release-state-validator` (496), `common` (772, last). `local-common.sh` is deleted only
      after W6's quality lane and W8's retarget, per the arbitration table.
      **Note:** `age-check.sh` and `find-port.sh` can never be promoted to `shim:` -- they must be
      DELETED, retargeting their 17 and 14 callers. A shim is a delay, not an exit.
- [ ] **W7P5-c S** The deletion box, the only one that removes anything.
      **Licence:** ledger at K=5 with >=2 fingerprints AND the Python side LIVE (registered,
      emitted, green in one full CI run) AND no tracked file references the twin's basename.
      **The one permanent carve-out is `w7p2-stagingtag`**: 3 tree ids disqualified by rows
      recorded through a hole since closed, 12 qualifying trees over 9 finding sets.
      `assertEquivalent` disqualifies unconditionally and by design cannot be cleared by
      re-running. Do not re-record; require a human sign-off line in the deletion commit.
      **The drain shape, derived from `write_verdict`'s composition rules:** a port alone changes
      nothing (`covered` identical, no reseed possible); a deletion is a pure subtraction and is
      **the only legal reseed**; any new `.sh` is refused even if the total shrinks; a missing
      baseline is STRICT MODE, not "no debt". So: **delete a batch -> reseed in the same commit ->
      repeat.** **Acceptance:** `baseline_before - baseline_after` equals exactly the files that
      commit deleted, and `baseline_after - baseline_before` is empty. Checkable from the diff.
- [ ] **W7P6 C, 3 writers** The 142 unnamed files (P-C). Port groups above; allowlist the 7-8
      named. Resolve the missing allowlist kind for `bootstrap.sh` before the strict flip.
- [ ] **W1P4 C, after PRE-A1** The full `sys.path` sweep, 68 files and rising. Re-derive at
      staffing time; W6 P2 and W8 P2 both wait on it. **Acceptance:** SET, printed by name,
      strictly shrinking, plus a floor proving the scanned corpus has not collapsed.
- [ ] **W1P6 S, terminal** Delete `.ci/config/language-policy-baseline.json`. `read_baseline`
      returning `None` IS strict mode (`:478`, `:788`) -- the flip is a file deletion and no code
      change. **Acceptance:** the gate exits 0 printing `language policy STRICT: N bash file(s)
      ... all M allowlisted`, N == M.

---

## T-SCHED

- [ ] **A1 S** `GateSpec.env` **and** a `when` conjunct field, at both ends of the pipe
      (`gate-spec.ts`, `gate-header.ts`, `gate-bind.ts`, `gen-gates-lock.ts`, ~120 lines).
      `when` ANDs onto the standard guard, never replaces it -- a field that could replace it
      re-opens invariant 11 through a side door.
      **Acceptance:** set equality over the 26 `(job, step, env-key, env-value)` tuples before and
      after, computed by the same parser on both sides; `if:` multiset byte-identical; three
      representations (header, lock, emitted) agree. Controls: an `env` value referencing a secret
      not in the workflow's `secrets:` block is REFUSED; a `when` conjunct containing `steps.` is
      REFUSED.
- [ ] **A2 S, cheapest high-value box in the programme** The strip guard. `--write` refuses when
      `dropped` is non-empty **for any reason**, with `--allow-drop <step>` as the one typed
      escape. Plus a new gate `check:ci-step-env-parity` asserting each step's `env:` map equals
      `lock[id].env ?? {}`, both directions.
      **Red proof available today:** strip `DOCKERHUB_TOKEN` from `ci-quality.yml:1159` in a
      scratch copy and run the whole battery -- nothing reds. That is the receipt.
- [ ] **A3 S** Retire the six `env`/`if` hold-outs. The 21 setup-ordering hold-outs stay held out
      permanently and correctly; assert their set is unchanged so this box cannot emit one.
- [ ] **B1 S** `shardPlan(lock, laneCaps, shards)` in `scripts/ci-runner/lanes.ts`, pure, writes
      nothing. `lanes.ts` already derives `{job, runsOn, timeoutMinutes, submodules, node, tools}`
      per lane -- the matrix's literal runners and timeouts come from there; nothing new parses
      YAML. Rules: a `mutex` group never splits; `heavy` at most one per shard; balance on
      `weight`, tiebreak on `slow`. **Acceptance:** union equals the lane's gate set, shards
      pairwise disjoint, none empty; **more shards than gates must REFUSE**, not emit an empty
      shard that reports green having run nothing.
- [ ] **B2 S, driver-only, long pole** Emit the matrix. **Invariant 11 is handled by construction:**
      the `include` list is generated only from lanes where `laneCanEmit()` is true, which is the
      same predicate that already refuses a region in a setup-less lane. `quality-branch:389` and
      `quality-submodule-branches:493` (7 steps total) stay hand-written -- verified: those are
      exactly the two lanes with no `- id: setup`.
      **Acceptance:** matrix-lane set UNION hand-written-quality-job set EQUALS the top-level job
      set, with empty intersection -- a lane that lost its setup step falls out of one and into
      the other and the partition still holds. Plus: step-name multiset unchanged per lane (the
      W2.6 instrument, 264=264 then 274=274); `dropped` empty; actionlint green; every shard's
      `runs-on`/`timeout-minutes` equal to its pre-rewrite lane's.
      **Four constraints, all verified:** job names are load-bearing (`WATCHDOG_NO_RETRY_PATTERNS`
      matches `Quality,Review Gate` with `String.includes`, so every shard keeps the `Quality / `
      prefix); `ubuntu-slim` has a hard 15-minute cap and CHECK 3 requires `timeout-minutes <= 14`;
      `continue-on-error` is banned, `fail-fast: false` is the correct and different thing; setup
      class is the lane axis, so sharding within a lane multiplies setup cost and sharding across
      classes would be wrong outright.
- [ ] **B3 S** `quality-complete` aggregator. `ci_job_aggregation.py` already enforces four things
      about `ci-complete`, including an equality between tier lists and env vars because "either
      half alone is dead". A matrix job's result is a single roll-up, so shards are invisible
      without an intra-workflow aggregator. **Acceptance:** received shard count equals the
      declared shard count, read from the same generated source; no result is failure/cancelled;
      the include list was non-empty. Clause 1 is the stronger form -- an include list that
      dropped half its entries passes the emptiness check.
- [ ] **B4 S** The `ci-quick` job and **fail-open** scoping. Only 45 of 458 entries declare
      `paths`, so scoping by `paths` fails OPEN for the other 413. **Acceptance:** a gate with no
      `paths` is selected for every non-empty change set; an empty change set must REFUSE rather
      than select nothing ("nothing changed" and "the differ broke" are the same shape).
- [ ] **B5 S** The timing contract. The three pytest receipts do not actually disagree -- they are
      three statistics of one gate: a single instrumented run (381.41s), a re-measurement (396s),
      and the floor of five (367.9s). `check-gate-manifest.ts:511-520` already rules that the
      oracle judges the FLOOR, so 367.9s is the only one computed the admissible way. Record
      `docs/ci-overhaul/12-w3-timing-contract.md`: one statistic, one source (a quiesced reference
      worktree, `git status --porcelain` empty, tree id recorded). **No target in this slice is
      checked off by a timing** -- the W3 targets become recorded observations attached to
      structural boxes. The quality-tier wall has never been measured and must come from the
      GitHub run, not a worktree.
- [ ] **C1 S, driver-only** W2.3's generated manifest region. **Its invariant-3 precondition has
      lifted** -- all four text readers now read the lock, and `gate-spec.ts:10-18` says so.
      **Scope honestly:** a header owns only `{kind, step, needs, id, run, lane, selftest, slow,
      why, emit, test, blocker}` plus A1's `{env, when}`. It does NOT own `gate`, `leaves`,
      `paths`, `weight`, `heavy`, `mutex`, `reads`, `qualityGateTest` or the prose. So derive the
      eligible set first and publish its size as a receipt; do not target a number.
      **Acceptance:** entry-id set unchanged (458=458); **the lock regenerated from the new
      manifest is byte-identical to the lock regenerated from the old** -- the strongest available
      statement that this is a pure refactor; generated and hand regions partition the set;
      `pool.ts` ordering unchanged (array index is its scheduling tiebreaker).
- [ ] **C2 C** W2.5 tier 1: `pathsOrigin` required whenever `paths` is present.
      **Acceptance:** cardinality equality both directions; a `declared` origin whose glob matches
      zero tracked files REDS (such a gate is silently excluded from every `--changed` run); a
      `derived:<tool>` origin must reproduce under re-running. Interlocks with B4: the fail-open
      assertion is what makes it safe for 413 entries to carry no `paths`, so C2 need not raise 45
      to any target.
- [ ] **D0 S, head of the W5 spine** Build the exec baseline the W5 target is defined against.
      `grep -rln 'strace|GUARD_PASS|HOOKS_ONLY|FORK_COUNT'` over `.ci`, `.claude`, `scripts`
      returns one unrelated file. **W5 P0's stated fork counter is not in the tree and the
      "456 execs -> 35" figure is unreproducible.** A Bash call fires **12** hook processes today.
      Build `.claude/rediacc_hooks/execcount.py` + `.ci/policy/hook-exec-baseline.json`. **Not
      strace** -- unavailable on macOS, needs ptrace in containers, and a baseline CI cannot
      reproduce is the same class of problem as the missing one. **Anti-vacuity: a run producing
      zero counts is a refusal**, which is exactly the failure shape of the baseline that vanished.
- [ ] **D1 C** Cross-OS. Only W5 P1's `/proc`-vs-`ps` seam exists (`proc.py:32-43`);
      `dispatch.py` has zero platform handling. Enumerate every platform-sensitive operation, give
      each a seam with an env override, and assert the enumeration is complete: a scanner's finding
      set must EQUAL the declared seam set, both directions.
- [ ] **D2 C** The `WORKLIST_*` registry: **134 distinct names across ~56-60 files at 178 read
      sites**, no registry, no schema. A typo'd name reads as unset, which for a feature flag is
      the fail-open direction. New policy list reached through `policyPath()`; generated doc table
      via the existing provider mechanism. **Acceptance:** set equality both directions -- an
      unregistered read reds, a registered name nobody reads reds as dead.
      **Trap:** the scanner must not read `agent/` (invariant 7) or `docs/`; exclusions are
      declared in the registry with reasons, not hardcoded.
- [ ] **D3 S, long pole** Shard the hook suite. `test-hooks.sh` is **2,774 lines**, `slow: true,
      // 537.4s`, one `run:`. `run_tests.py` (100 lines) is wired to nothing and says so.
      **Invariant 2 bites in six places, all verified:** `language-policy-baseline.json:476`;
      `.ci/policy/.dead-bash-allowlist:42` plus three golden files encoding the line index;
      `trap_registry.py:227` (`TRAP_HOOK_SUITE`, a single path constant, plus two control
      fixtures); `hook_integrity.py:69` (`SUITE=`, single path); and two line-numbered measurement
      comments already stale against 2,774. **All six re-keyed in the same change, or the split is
      not done.** **Acceptance:** the multiset of assertion labels across shards equals the
      pre-split multiset, extracted by the same extractor on both sides. Floor corpus-derived,
      never a hand-typed 395 or 398.
- [ ] **D4 S** Lifecycle collapse 30 -> 11. The redundancy is mechanical: `require-jq.sh` and
      `require-python.sh` are duplicated across all three PreToolUse matchers and PostToolUse/Bash
      -- 8 of the 30 entries and 8 of the 12 processes.
      **Acceptance:** entry count equals the 11 distinct `(event, matcher)` patterns AND **the
      verdict set for every guard is unchanged**, run against `.claude/oracles/` the way
      `test_guards_differential` already does. Clause 2 is required because a collapse that drops
      a guard passes clause 1 perfectly.
- [ ] **E1 S, largest single port in this track** `setup` in Python. `.ci/rediacc_ci/setup/` holds
      only `__init__.py` and `tools.py`; the 22 rows DESCRIBE installs and `tools.py:167-169` says
      so ("prose, not something this module executes"). `setup` is still bash: `run.sh:97`
      `PORTED_VERBS=()` -> `run-legacy.sh:1068` -> `setup()` `:543-715` + `setup_check()` `:719`,
      driving seven functions in `.ci/lib/setup.sh` -- **~1,117 bash lines**. No `.claude` wiring,
      no opt-in git hooks. Keep the prose rows: they are what a human pastes when the executor
      refuses (invariant 9). **Acceptance:** shadow ledger at K=5 (the `w6p2-toolchain` shape),
      phase-set equality against the bash call sequence both directions, per-phase idempotence.
      A macOS claim not driven on a real bash 3.2 is not a claim -- the standard W6 P2 set.
- [ ] **E2 S** `rdc.sh` 314 -> 70. The native SEA build moves out of `rdc.sh:83-160` into the
      package. **Acceptance:** a line ceiling in the shape of the existing `run.sh` one;
      behavioural equality of `--native` across the three platform arms via a `uname` seam; and
      the macOS probe must be seen to **FAIL on a planted defect** -- a new CI job that has never
      gone red is not yet evidence.
- [ ] **E3 S** Legacy arms to zero. Correct the plan's phantom `LEGACY_ARMS_MAX` to what the tree
      enforces. `PORTED_VERBS=(setup)` is line-neutral, so the 120/120 ceiling does not block E1;
      growing the array does, and that is a decision this box makes rather than discovers.
      **The trap:** `test-run-sh.sh:315-327` requires `n_legacy > 0` before believing any
      assertion, so **the anti-vacuity clause must be rewritten in the same change that makes
      `n_legacy` zero**, or the gate guarding the migration reds at the moment it succeeds.

---

## T-ENV

- [ ] **W0.0-A S, 2026-09-08, session-executable** The probe. **Correction: only the MINTING is
      operator-blocked.** `BWS_ACCESS_TOKEN` is absent from the session environment but present in
      `private/account/.env` (49 assigned names), and the tree records the probe being run from a
      session on 2026-09-06. **Acceptance:** `bws_env_load` returns the same NAME SET as
      `bws-secret-map.json`'s keys. Never a value, never a count.
      **If it fails:** M0 fails, `bws-token-expiry.json` is left TRUTHFUL (the `expires` date is
      not edited forward, no row is invented), and a last-resort issue carries
      `door:operator-only`. **Per-wave fallback:** W8 P1 and W8 P5 STOP; W8 P2/P3/P6, W8 P4 and
      all of W4 CONTINUE -- they are static analysis over tracked text. **Two thirds of T-ENV is
      credential-free by construction**, which must be stated so nobody concludes M0 blocks W8.
- [ ] **W0.0-B S, GENUINELY OPERATOR-BLOCKED** Mint `mc-ci-read`, `mc-rotate`, `dev-shared`. No
      `bws` verb mints a machine-account token; it is web-vault only. `mc-ci-read` has one tracked
      occurrence, as prose in a `"replacement_plan"` string. **Acceptance:** three `tokens[]` rows
      whose `used_by` values PARTITION -- today's single row claims `read-write` for local, ci and
      cd at once, and that concentration IS the outage risk.
      **`mc_migrate_claude` expires 2026-09-08, tomorrow. No gate reads the expiry file, by
      deliberate decision, so nothing will red -- every call site simply starts failing.**
- [ ] **W0.1 S, blocked on W0.0-B** Cut over by fingerprint. **Acceptance:** a dispatched workflow
      prints `sha256(client-id)` truncated to 16 hex and it equals the `mc-ci-read` row.
      Greenness is explicitly not the acceptance -- old-token-green and new-token-green are
      indistinguishable. Red first: dispatch before the swap and assert it prints
      `00991b3077ee8f57`.
- [ ] **W4-D1 S** The `.ci/policy` contract has already drifted, **one day after the move**.
      `POLICY_FILES` holds 15 (`policy-paths.ts:69-86`); the directory holds 16.
      `.language-policy-allowlist` is reached by a hardcoded join at `check_language_policy.py:112`,
      bypassing the seam. **Acceptance:** three-way set equality -- directory == `POLICY_FILES` ==
      the Python name set. This box is the evidence that W4 P4b's inventory gate is load-bearing,
      not cosmetic.
- [ ] **W4 P4a S** Python `policy_path`. Five hardcoded literals (`go_deps.py:178`,
      `plan_housekeeping.py:238`, `profiler_coverage.py:166`, `check_language_policy.py:112/114`,
      `check_runner_advice.py:899`). **Design constraint:** `test-policy-path.sh:79` asserts the TS
      seam does "no stat, no readdir" and proves it with an `rmdir`. The Python twin must satisfy
      the same property, so `policy_path()` is a pure join and the inventory readdir is a SEPARATE
      instrument. Every env override stays in front of the seam.
- [ ] **W4 P4b S** The inventory gate, four directions: nothing in the directory outside
      `POLICY_FILES`; nothing in `POLICY_FILES` missing from the directory (a deleted list reads
      as "nothing is suppressed"); Python == TypeScript; no literal joins outside the two seams.
      **The honest control:** run it against `19c45c78e` and assert it reds with exactly
      `{.language-policy-allowlist}`. A gate that cannot detect the drift that already happened is
      not the gate.
- [ ] **W4 P4c C** The prose sweep gets a PREDICATE, absorbing the stale
      `check-suppression-liveness.ts:61` comment ("Today POLICY_DIR is '' and this is a provable
      no-op", untrue since `b80552370`). Rules: no comment may assert a `POLICY_DIR` value
      differing from `policy-paths.ts:57`; no comment may cite a policy file by a root path.
- [ ] **W4 P5 C -- REFUSE, and record the refusal** `bws-secret-map.json` fails three of the four
      `.ci/policy/README.md` clauses: it carries `refreshed_at` and is regenerated wholesale
      (clause 1); it has zero BLOCKER lines and a per-UUID reason would be invented (clause 2);
      and `.github/actions/bws-secrets/action.yml:71` builds the path from `github.action_path`
      with two more readers in `private/account`, so its location is an EXTERNAL CONTRACT
      (clause 4). That is a worse case than the one used to keep `language-policy-baseline.json`
      out. **Record it as README section 5 with a mechanical assertion** -- the file exists, is not
      under `.ci/policy/`, and contains zero `BLOCKER:` occurrences, so if someone ever adds
      reasons the decision reopens loudly.
- [ ] **W4 P3a-d** One blocker validator. Corpus DONE and registered
      (`test-blocker-golden-corpus.sh`, 20 cases, 7 of them verbatim reasons from live
      allowlists). Three live implementations remain plus one vendored, none collapsed; the TS is
      an INDEPENDENT port with its own pattern lists and a hand-sync comment, not a client.
      **P3d, the invariant-8 half:** "subset" is NOT "verdicts agree" -- two recorded divergences
      go the wrong way because the vendored copy has no substring list. The provable claim is
      about the LISTS: `bp_phrases ⊆ canonical_phrases` and `bp_substrings == ∅`, which DERIVES
      the two divergences instead of leaving them unexplained. Read the file read-only, parse its
      arrays, and **assert the gate's own innocence**: sha256 before and after the gate body, both
      equal to the `MANIFEST.sha256` row. Perturb only a temp copy.
- [ ] **W8 P1a S, ONE writer** Prove irreducibility as a SET. **The drain largely already
      happened**: `check-workflow-gates.sh` CHECK 2 enforces all four directions (`:258`,
      `:270-288` recording a 57-declaration sweep, `:336-345`) with a liveness arm at `:302-305`,
      registered at `manifest.ts:2537`. Residue: 13 files mentioning `workflow_call`, **2 distinct
      secret names**, 14 caller passthroughs all `BWS_ACCESS_TOKEN`, **zero `secrets: inherit`**.
      **New content:** assert `DECLARED_UNUSED_OK` is exactly the set of names pinned alive by
      `.github/external-callers.yml` -- today that justification is a comment and the registry
      does not know about it.
- [ ] **W8 P1b S** The one genuinely removable declaration
      (`claude-review-reusable.yml` / `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`). Three commits,
      **submodule-first**: `private/account`, then `private/renet`, then the console commit
      deleting the declaration, the `DECLARED_UNUSED_OK` member and both `external-callers.yml`
      entries together. **Acceptance:** the gate green with `DECLARED_UNUSED_OK` EMPTY, and its
      liveness arm proving the exemption was retired rather than left dangling.
- [ ] **W8 P2 S, largest box in T-ENV** The env manifest. **Do not quote 1,014** -- it is not
      reproducible and would set an acceptance nobody can re-derive. Method: union of five defined
      sets = **745** (env files 89, workflow/action `KEY:` 308, `process.env` 171, `os.environ`
      254, vault 58). Bash `${VAR}` is EXCLUDED in writing: it pushes the union to 3,075 and is
      dominated by loop variables. **745 is a receipt with a date, not the acceptance.**
      **Eight shards keyed on who supplies the value and who may read it:** `secret`, `ci-runner`,
      `gate-seam` (the fixture-pointing seams most often mistaken for configuration),
      `toolchain`, `machine-local` (the target of P5's truncation), `product-runtime`, `harness`,
      `tombstone`. Making tombstones the eighth shard means "tombstones enforced" falls out of the
      same set arithmetic as "zero unclassified".
      **Acceptance:** `sources \ shards == ∅`; `shards \ sources == tombstones`; the seven live
      shards pairwise disjoint; `tombstones ∩ sources == ∅`. Ship the derivation SCRIPT so the
      number is re-derived, never typed.
- [ ] **W8 P3 S** Generators plus one regenerate-and-diff gate, adopting the existing
      `gen:docs` provider pattern rather than inventing one. Emitter and parity gate in the same
      change (invariant 1). Re-key `doc-registry-preport.json` for any moved key string.
- [ ] **W8 P4 C, cheapest real win** The cure is call-site adoption, not new code.
      `core/env.py` is DONE and PROVEN against a LIVE `set -a; source` in a subshell
      (`test_core_env.py:74-105`, `:434`), with a `python3 -m rediacc_ci.core.env` CLI -- and
      **zero production importers**. `bws_env_load` likewise has zero callers. Both orphaned.
      **Seven sites with a disposition each:** `constants.sh:22` STAYS bash (sourced before Python
      is guaranteed; bootstrap circularity) until W6 P3; `account.sh:438` and `:791` retarget;
      `toolchain.sh:34` is bootstrap-sensitive, measure first; `run-legacy.sh:185` **do not
      retarget** (W6 P5 deletes it -- record the decision so it is not re-found and mistaken for a
      miss); `deploy-bench.sh:137` retarget before W9 P2 moves it;
      `programs/backup-storage/start-local-plane.sh:60` retarget -- its own comment at `:57-59`
      already reasons about precedence, the best demonstration that the rule is real.
      **Out of scope in writing:** `private/growth` (gitignored separate checkout) and
      `packages/cli/templates/**` (shipped content that runs on remote machines with no
      `rediacc_ci`; retargeting would be a product regression).
      **Acceptance per site:** set one of the file's names in the environment to a DIFFERENT value
      and assert the shell value survives -- under `set -a; source` the file wins and it fails.
- [ ] **W8 P5** Spec + gate available NOW (the truncation target is the `machine-local` shard);
      **seeding OPERATOR-BLOCKED** on `dev-shared`, which has zero tracked hits.
- [ ] **W8 P6 S** Python env registry, shrink-only over a SET of `module:NAME` pairs, in
      `.ci/config/` (not `.ci/policy/`, per the clause-1 reasoning P5 re-applies).
      **The arm that usually goes missing:** deleting a baseline entry whose violation is still
      present must RED, so a baseline cannot be trimmed to escape the gate.

---

## T-DOCS

- [ ] **X0.1 S, do first** Fix the A5/A6 collision in the plan text and adopt PREFIXED decision
      ids (`D-A6`, `G-A5`). Three schemes collide today: `A5`/`A6` are gate rules at
      `check_plan_boxes.py:41`/`:42-44`; `04-decisions.md` section A item 6 (`:22-23`) is the
      operator override licence. P2.7's subject is the gate rule; P3.2's is the decisions doc.
- [ ] **W11 P4a C** `policy` provider + region replacing `.ci/policy/README.md`'s hand-typed
      section 2, whose heading literally reads "fifteen" against 16 files on disk.
      **Acceptance:** two-direction set equality, key set == `ls .ci/policy` minus README ==
      `POLICY_FILES`. **It is RED on landing**, which surfaces W4-D1 structurally; this box does
      not fix it, it hands the one-line addition to that box as a fragment.
      **Do not derive the Readers column by grep** -- `doc-providers.ts:568-583` records that a
      grep-derived Readers column flipped mid-run on 2026-09-06 and forbids re-adding it.
- [ ] **W11 P4b C** `test-split` provider + region in `07-port-brief.md`, rendering the residue as
      an explicit `(unregistered)` row. Non-empty is legal and visible; silence is not.
- [ ] **W11 P5a S** Providers `bootstrap`, `job-graph`, `media` with their regions, one commit.
      `check-doc-region-parity.ts:22-30` makes invariant 1 automatic here: a provider without a
      region reds immediately.
- [ ] **W11 P5b S** The 140-line cut. **Session Defaults is lines 9-233 -- 225 lines, 39% of the
      file, frozen byte-identical** (verified: `## Session Defaults` at 9, `## Architecture` at
      234). The two generated spans are 43 more lines. **So the entire cut comes from a
      hand-written budget of 312 lines: a 45% cut of everything not frozen and not generated.**
      Defensible sources, measured: the npm-lockfile section (**52 lines**, closed archaeology --
      its durable half is a TRAP and its enforcement is in `check-lockfile.sh`); Common Commands
      -> a `cli-commands` region from the machine-readable CLI contract (net 24); Versioning (14);
      Release Channels (7); Media Assets -> the `media` region (6); CI/CD Pipeline -> the
      `job-graph` region (6); Local environment -> the `bootstrap` region (11); i18n -> a pointer
      (17). Sum **137**, with Terminology (9) as the reserve.
      **Acceptance:** `wc -l <= 440` AND `wc -c <= 30720` AND `git diff` over lines 9-233 is
      EMPTY -- the last is an assertion in the box, not a claim in its report.
- [ ] **W11 P5c BLOCKED ON W8** The `env-manifest` region has no home until W8 P2 exists. Record
      it as blocked so P5 is not ticked at three of four.
- [ ] **W12 P2.7a S, before the wave** `check_plan_boxes.py` rule A5 becomes never-delete. The
      deadlock A5 avoided no longer exists: `check-plan-housekeeping.sh:51` states "THE REMEDY IS
      NO LONGER 'DELETE IT', AND THAT WORD IS GONE ON PURPOSE." **New control: a 41-day-old plan
      with one surviving-nowhere open box must be REFUSED** -- the exact case that passes today.
- [ ] **W12 P2.7b S, before the wave** Two TRAPS entries: the `title_of()` class (slug fallback,
      code fence, `Word:` header guard -- together they sent 62 of 83 plans to the slug fallback,
      fixed at `65f1aa803`), and **"a stale `Status:` header is a CLAIM; the tree is EVIDENCE"**,
      marked `Enforced-By: JUDGMENT-ONLY`. Bump `TRAP_FLOOR` 77 -> 79 in the same commit.
- [ ] **W12 P2.7c S after P5b** "Search first" into CLAUDE.md (`grep -c search CLAUDE.md` = **0**
      today) as a 4-line block after `## Architecture`, budgeted into P5b up front. Plus
      `docs/agent-reference/plan-records.md` carrying the record grammar **as a generated region**
      rendered from `wl_planrec.py` -- a hand-typed copy of a grammar that lives in code is the
      "254 fast gates" failure again.
- [ ] **W12 P2.8, ~14 sessions, THE CALENDAR** 54 uncompacted plans + 1 park resolution.
      Four batches staged against the real dates, not evenly: **B1 starts 2026-09-14** (the 17
      reddening 09-26..09-30, five days of slack); **B2 2026-09-21** (13, sharing a boundary with
      the P3.5 window close); **B3 2026-09-26** (the 11-plan 10-06 spike, alone); **B4 2026-10-01**
      (14 + the parked plan). Staffing 3 / 3 / **4** / 2 -- the ceiling is 4 because `--plan-compact`
      runs one bounded `claude -p` and above that the judge is the queue.
      **The touching hazard:** age is LAST-COMMIT age, so compaction resets a plan's clock by 33
      days and the deadline is self-relieving. The trap is the inverse -- any other edit also
      resets it and pushes a plan out of the batch it was assigned to. **A batch agent
      re-derives its own date list at batch start, never inherits one.**
      **Two carried-forward failure modes in every batch brief:** the tool-side `title_of()` fix
      exists, do not re-implement it; and every `## Outcome` is derived from
      `git log --find-object` / `git log -- <path>`, **never from a `Status:` header.**
- [ ] **W12 P3.5 S, calendar-gated ~2026-09-21** Tick with evidence. Mechanism DONE
      (`check_plan_record.py:44`, window `:167-168`, anti-vacuity `:74-79`, four set-based floors
      `:663`); tracked census at `agent/census-plan-record.jsonl`, span 0.41 of 14 days.
      **Do not close the window early to get a quiet number** -- B1 runs inside it and will move
      `would_refuse`, which is exactly what the census exists to measure. **C11 at 0/4 is the one
      to watch:** a candidate that never fires is either a rule with no subject or a broken
      instrument, and the tick must say which.
- [ ] **W12 P3.1b C, before W9 P2** Read epic ids from the ledger, not a published document.
      `check-pr-task-trailers.ts:285` reads `agent/pr/<branch>.md`, itself generated by
      `worklist.py --publish`. **The fix is cheaper than the plan implies:**
      `agent/worklist/epics.jsonl` is already tracked and append-only (W12 P3.1a moved it out of
      TMPDIR). **Acceptance:** ledger ids == snapshot ids, both directions -- ledger-only means
      `--publish` is stale, snapshot-only means a hand-edited document.
- [ ] **W12 P3.2 C** `DECISIONS.md` with prefixed ids. **What "enforcing a licence" can mean,
      stated so nobody builds the impossible:** no gate can tell a good substitution from a bad
      one; it CAN assert the licence's precondition, that the substitution is stated out loud. So:
      a decision id may be superseded only by a commit citing the superseding id, and every cited
      id must resolve to a row. Reuse `check_plan_citations.py`'s resolver rather than growing a
      second one.
- [ ] **W12 P3.3 S, after the wave** Status vocabulary in config. **The box's premise is partly
      wrong:** there are TWO sets, not three -- `CLOSED_STATES` at `wl_planfile.py:221` is
      CHECKBOX state, and building it from a plan-status vocabulary is a category error. The drift
      this closes is real: `check-plan-housekeeping.sh` and `check_plan_record.py` each re-derive
      `compacted`/`parked` with their own regexes.
- [ ] **W12 P3.4b S, after the wave** Resolve `Supersedes`/`Extends`/`Related`. Three planted
      controls, not one -- the keys have different arities.
- [ ] **W10 P5 C** Tick with evidence. `.ci/policy/.language-policy-allowlist:35-36` carries the
      BLOCKER string above `tree:.ci/media/`; all 13 `.ci/media/*.sh` are exempt-by-name and none
      is in the 521 baseline. **The decisive evidence is the ABSENCE from the baseline**, not the
      presence of the entry: exempt-with-a-reason is the goal state, frozen debt is not.
- [ ] **W11 P6a S, OPERATOR-GATED, blocks P6b and U2** Settle `private/account`. It is on a
      **detached HEAD** with an uncommitted **512-line pure deletion of `package-lock.json`**, and
      its pointer is 3 commits behind an already-fetched `origin/main`. Rule 1 forbids
      `checkout/restore/stash/clean`. **Repair forward:** branch at the detached HEAD so the state
      is named; decide the deletion on its merits from the tree (does `.gitignore` name it, does
      its CI install from it); commit it or re-add the file from `origin/main`'s blob as a NEW
      commit; then rebase. **Acceptance, all three:** status empty AND HEAD is a named branch AND
      `HEAD..origin/main` empty -- any one alone is satisfiable while the others are broken.
- [ ] **W9 P2.0 S, blocks P2, highest value per unit effort in T-DOCS** Make
      `scripts/lib/domains.ts` load-bearing. It is 133 lines with **zero importers**; its own
      header says a JSON file nobody executes "is a document, not a partition", which is what it
      is. **The Gaps entry's risk is INVERTED:** there is no set-equality gate reading
      `domains.json` at all, so nothing can red; and 6 of the 9 move rules are already
      `incoming-*` rules mapping `.ci/scripts/**` into `scripts/**`. The classification is done;
      **enforcement is what is missing.**
      **Landing order is the whole trick:** land with clause 1 (total classification) ENFORCING
      and clause 2 (in-place) ADVISORY, printing the out-of-place set. P2 executes the moves.
      Clause 2 flips to blocking in the same commit as the last move. A gate that blocks on 154
      files on day one is suppressed within a day.
- [ ] **W9 P2 S, ALONE IN ITS WAVE** The moves. 120 `check-*.ts` -> `scripts/gates/`, 10
      generators -> `scripts/gen/`, 15 operator scripts -> `scripts/ops/`, 9 `.cjs` ->
      `scripts/ci/`. **271 tracked files contain the literal `scripts/check-`**, including 185 in
      `package.json`, 159 in `manifest.ts`, 157 in `gates.lock.json` -- three driver-only files at
      once. **Two couplings the predecessor did not name:** (a) `ci-tree`'s row key is the
      directory, and `doc-registry-preport.json` carries `.ci/scripts/{ci,build/sea-inject,docs,autopilot}`
      among its keys; `gen-docs.ts:268` says MISSING keys are **fatal** to `--diff-snapshot`, so
      the moves break the programme's own verification instrument unless the four keys are
      re-keyed in the same commit -- never `--snapshot --force`. (b) the 42-entry
      `unguarded` baseline. Plus the six invariant-2 inventories.
      **Exclude `.ci/breakpoint/**` from any rewrite sweep** -- two files there contain the string
      `scripts/check-` and a blanket sed would break `MANIFEST.sha256`.
- [ ] **U1 C** Requirement 15: a `json-inventory` provider + region over root / `.ci/config` /
      `scripts/data` / `.ci/policy`, with `Discovered by` and `Configurable path?` cells. The
      predicate exists only as prose at `08-driver-contract.md:318-334` and **three of its numbers
      went stale in one day**, which is the argument for generating it.
- [ ] **U2 S after P6a, OPERATOR-GATED** Cross-repo PRs. **`private/growth` is not a submodule** --
      `.gitmodules` lists four and `.gitignore:85` ignores it. That clause cannot be executed as
      written; split it into a decision box (documented clone-and-remote procedure, or promotion
      to a real submodule). Name an owner and record the merge order the `pr-merge` skill encodes.
- [ ] **U3 C** Widen `test-shrink-only-composition.sh:97-102`. It greps `--include=*.ts
      --include=*.js` over `scripts/` and `packages/www/scripts/` -- **two** blind spots: it
      excludes `.py` AND its roots exclude the entire `.ci/` tree. Live subjects today: exactly
      one tracked `.py` offers `--write-baseline` (`check_language_policy.py`) plus
      `check_resprofile.py:365`'s equivalent `--reseed-class` over an ACCUMULATING baseline. **The
      hole is self-declared** -- `check_language_policy.py:418-428` says the port "names the
      resulting coverage gap ... out loud rather than leaving it to be discovered" and the test was
      never widened. The green is not vacuous, just scoped to a language and two directories the
      programme is migrating away from.
- [ ] **U4 C, highest-value new gate** A dead-Python gate. There is none
      (`ls scripts/check-dead-*.ts` yields bash, css, service-methods, translation-keys) and
      `check-dead-bash.ts` is bash-only by construction.
      **The design finding, which corrects an earlier reading:** the five "orphaned" entry points
      under `.ci/scripts/quality/` are **NOT dead**. All five are named as the new side of a
      committed shadow ledger (`w7p2-apbp`, `w7p2-clidoc`, `w7p2-rubric`, `w7p2-www-build-token`,
      `w7p2-rbs`) and all five bash twins are still the registered gate. They are **pre-cutover
      W7 shadow twins.** A naive "referenced by nothing is dead" gate would red five legitimate
      ports and be suppressed on its first run.
      **Three admission routes:** registered; test-reached (pytest discovery under `testpaths`,
      which is how 78 modules survive with no manifest entry); shadow-admitted (named as the new
      side of a ledger whose verdict is EQUIVALENT **and whose bash twin still exists**). The
      third route **expires when the twin is deleted**, at which point route 1 must have taken
      over -- and that expiry is the gate's whole value: it turns "a port that shadowed green and
      was then forgotten" from invisible into a named row. An `agent/`-only mention is NOT an
      admission route.
      **Language:** Python under `.ci/rediacc_ci/quality/`, per ruling 7 -- a
      `scripts/check-dead-python.ts` would be renamed twice by W9 P2 and W7.
- [ ] **U5 C** `check-shape-duplication.ts:122`: `/'(?:[^'\\]|\\.)*'/g` -- `[^'\\]` matches
      newlines, so an apostrophe inside a double-quoted message eats every line to the next quote.
      Reports coordinates off by up to 243 lines and silently drops code from its own corpus.
      Corpus is 345 files / 275 shapes; a fix re-keys every fingerprint at once, so it is its own
      piece of work.

---

## Ordering

```
M-1  land the 115-commit wave
  |
W8 P1a -> W8 P1b -> [release window, one green deploy]     (frees .github/workflows/**)
  |
A1 -> A2 -> A3            (env + when + the strip guard)
  |
B1 -> B2 -> B3 -> B4 -> B5   (the shard matrix owns ci-quality.yml)
  |
W7P4-Q (77 cutovers) -> W7P4-W (348 sites) -> W7P5-a/b/c -> W1P6

running continuously alongside, no driver, no registration:
  PRE-A0 -> PRE-A1 -> W7P3-a..d -> W7P3-RT -> W7P3-BAT      and      W7P6, W1P4
running in parallel, file-disjoint:  D0->D1/D2->D3->D4   E1->E2->E3   T-DOCS
W9 P2.0 -> W9 P2  LAST, alone in its wave
```

**Why `.github/workflows/**` goes W8 P1 -> W3 P3 -> W7 P4, in that order:**
1. W8 P1's drain deletes `workflow_call` inputs, and ~14 emitted-class steps carry `if:`
   conjuncts referencing `inputs.external_quality` / `inputs.media_quality`. A1's `when` field
   must be declared against the FINAL input set or the declarations are wrong the moment W8 lands.
2. W8 P1 is days; W3 P3 and W7 P4 are weeks. Taking the two-day job first costs the rewrite two
   days; taking it second costs W8 P1 a fortnight during which nobody may touch the secret graph.
3. B2 is the cheapest possible base for W7 P4's 348 flips -- after it, a flip is a header edit
   plus one `--write`, mechanically verified, with A2's `dropped` guard live.

**Other hard constraints:** P-B before W3 P3 and W2.3 (both run a `--write` first, and a `--write`
today re-strips 11 env lines). P-A before W7 P4 -- it IS W7 P4. W12 P2.7a and P2.7b before the
compaction wave. W12 P3.3 and P3.4b after it. W7 P5's deletions last. W9 P2 last and alone.

---

## Driver-only collision map

One writer in flight programme-wide. A writer agent authors a PATCH FRAGMENT; the driver applies
it in the same commit as the gate file (invariant 13).

| File | Claimants | Rule |
|---|---|---|
| `package.json`, `manifest.ts`, `gates.lock.json` | all four tracks | fragments only; batch per wave, or the driver is the bottleneck |
| `.github/workflows/**` | W8 P1, W3 P3 (B2/B3/B4), W7 P4, E2 | **MUTEX**, in the order above |
| `CLAUDE.md`, `TRAPS.md`, `doc-registry.md`, `doc-providers.ts` | **T-DOCS only** | `doc-providers.ts` is the internal bottleneck: six boxes, strictly serial P4a->P4b->P5a->P5b->U1->P2.7c |
| `scripts/**` renames | W9 P2 | last, alone; 271 files, ~500 registry literals |
| `.ci/breakpoint/**` | **nobody, ever** | invariant 8; W4 P3d reads and hashes it, zero writes; exclude from every sweep |
| `agent/worklist/**` | verbs only | invariant 7; P3.1b reads `epics.jsonl`, never writes it |
| `scripts/lib/policy-paths.ts` | W4-D1 then W4 P4a | zero of the 91 reader pairs are disjoint |
| `gate-spec.ts`/`gate-header.ts`/`gate-bind.ts` | A1, then A2, then C2 | serial handoff, never two writers |

---

## Calendar

| Date | What |
|---|---|
| **2026-09-08** | `mc_migrate_claude` expires. Sole credential path for local, CI and CD. **No gate reads the expiry file, so nothing reds** -- every call site simply starts failing. Minting is operator-only; the probe is not |
| 2026-09-14 | W12 P2.8 batch B1 must start |
| 2026-09-19 | plan-housekeeping warn band opens |
| ~2026-09-21 | W12 P3.5's census window closes |
| **2026-09-26** | first housekeeping RED, 3 plans; then continuous, spiking to 11 on 10-06, 55 by 10-10 |

---

## Effort

| Track | Sessions | Long poles |
|---|---|---|
| T-PORT | ~45-55 | W7 P3's 85 twins (44,032 lines); W7P6's 142 unexamined files (29,057 lines); `common.sh`'s 251 sourcers -- genuinely serial, cannot be widened by adding writers |
| T-SCHED | ~20-22 | E1 `setup` (~1,117 bash lines, K=5 ledger, macOS driven on real bash 3.2); B2 the matrix; D3 the suite split (six inventories re-keyed in one change) |
| T-ENV | ~24 | W8 P2 the manifest (745 names, one owner each) |
| T-DOCS | ~35 | W12 P2.8 (~14, calendar-driven); W9 P2 + P2.0 (4.5, but whole-wave exclusivity) |
| **Total** | **~125-135 agent-sessions** | |

**Cheapest high-value boxes, in order:** A2 (three files; closes the hole through which `--write`
deleted four steps and stripped 11 env lines, neither catchable today); W8 P4 (the code exists,
proven, and needs consumers); W9 P2.0 (turns a 15.5 KB document into an enforced partition and
closes the layout-admission gap); U4 (the only instrument that would catch a port that shadows
green and is then forgotten).

**Genuinely operator-blocked, three boxes only:** W0.0-B (mint), W0.1 (transitively), W8 P5's
seeding clause. Plus W11 P6a and U2, which need an operator decision on `private/account`'s
512-line lockfile deletion. Everything else is merely unstarted.
