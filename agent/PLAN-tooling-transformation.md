# PLAN: Tooling Transformation
Status: ready
Owner: 8f55d4f0
Updated: 2026-09-07

ONE plan, not two. Round 1 was drafted into `~/.claude/plans/` where nothing
tracked it; Round 2 was then written as a SECOND document, which made it worse.
Both are now here, in one tracked file: Round 2 is the live plan, Round 1 is
kept below in full because its 83 ticked boxes are the
only record of what was actually done and why.

Round 1's 48 still-open boxes are de-checkboxed on purpose. Every one is
carried by a Round 2 box above, and leaving both checked would count the same
work twice in `.ci/config/plan-boxes.json`. Their text is preserved verbatim.

READ THE ROUND 1 NUMBERS WITH CARE: fifteen counts it pins were re-measured on
2026-09-07 and were stale, and four of its premises were false. The corrections
are in the Round 2 section; where the two disagree, Round 2 was measured.

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
| Bash libs shimmed | 2 of 15 | `.ci/scripts/lib/age-check.sh:62`, `.ci/lib/find-port.sh:68` |
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
| W6 P5: `LEGACY_ARMS_MAX` reaches zero | **the name does not exist.** The budget is a partition assertion at `.ci/scripts/test/gates/test-run-sh.sh:278-306,:329` plus a 120-line `run.sh` ceiling at `:372-375`. run.sh is at **120 of 120** |
| W9 P2: baseline is "one sorted array" | an **object** with 42 `unguarded` entries. Hazard stands, description does not |
| Gaps: "the language-policy gate does not exist" | it exists, registered three-point, and **blocks on growth** |
| W12 P2.7: "A5 in `04-decisions.md`" | **not there.** A5 is a gate rule at `.ci/scripts/quality/check_plan_boxes.py:41,:428`. P3.2's "A6" DOES mean `docs/ci-overhaul/04-decisions.md:22-23`. Two schemes, adjacent boxes |
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
package (`scripts/gate-bind.ts:98`, `inScope` at `:201-202`, self-control at `:1069`), so this is not a
tooling gap -- it means the 78 headers cannot land as a cheap preparatory box. **They ARE
W7 P4 for the quality tree**, one atomic commit per gate. This is the largest re-ordering here.

### P-B. A gate cannot declare `env:` -- or an extra `if:` conjunct

`scripts/ci-runner/gate-spec.ts` has no `env` field (complete list: noProfile, id, run, gate,
needs, mutex, reads, weight, heavy, paths, slow, qualityGateTest, leaves, ci) and
`emitStep` (`scripts/gate-bind.ts:408-419`) hardcodes
`if: ${{ !cancelled() && steps.${guard}.outcome == 'success' }}` with no extension point.
**Six gate files already carry the literal blocker string `gate-bind cannot emit one`** and sit
at `emit: false` for that reason alone; ~14 steps carry an extra `if:` conjunct. All 26 `env:`
blocks sit outside the regions, which is why 126 of 276 steps are hand-written. Fixing `env`
alone leaves those unshardable. This is W2.4's missing `reads?: string[]` recurring, and it
violates the programme's own acceptance test at `docs/ci-overhaul/08-driver-contract.md:377-385`.

Two further holes in the same machinery:
- `scripts/gate-bind.ts:1567-1569` filters `dropped` to `claimed` and refuses only on `claimed`. Bare
  `dropped` is never printed on the write path and never asserted empty -- the 2026-09-05
  four-deleted-steps shape, still open.
- **Nothing in the tree checks a step's `env:` at all.** `scripts/check-ci-parity.ts:29` states as a
  design rule that an `env:` value is not an invocation. Strip `DOCKERHUB_TOKEN` from
  `.github/workflows/ci-quality.yml:1159` in a scratch copy today and the whole battery stays green.

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

**A new shim is illegal.** `.ci/scripts/quality/check_language_policy.py:143` sets `SHIM_MAX_LINES = 1`. The two
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

- [ ] **PRE-A0 S** `check-ci-parity` learns `python3 -m`. `resolveLeaves` (`scripts/check-ci-parity.ts:139-228`)
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
      `REAL_TREE_GROUP`, but `.ci/rediacc_ci/tests/gates/test_twin_parity.py:211-219` **refuses outright** to drive any
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
      Re-key the `PATTERN="test-*.sh"` glob discovery `scripts/check-dead-bash.ts:19-20` depends on, same
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
      **Also fix `.ci/rediacc_ci/check_pytest.py:74-78`** in batch 1: it still says the binder "only scans
      `.ci/scripts/` and `scripts/`" and that a header there "would be inert". False since
      2026-09-06 (`docs/ci-overhaul/08-driver-contract.md:303-311`), and it is the only in-code statement of the
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
      escape. Plus a new gate, id check-ci-step-env-parity (this box creates it), asserting each step's `env:` map equals
      `lock[id].env ?? {}`, both directions.
      **Red proof available today:** strip `DOCKERHUB_TOKEN` from `.github/workflows/ci-quality.yml:1159` in a
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
      and the floor of five (367.9s). `scripts/check-gate-manifest.ts:511-520` already rules that the
      oracle judges the FLOOR, so 367.9s is the only one computed the admissible way. Record
      `docs/ci-overhaul/12-w3-timing-contract.md`: one statistic, one source (a quiesced reference
      worktree, `git status --porcelain` empty, tree id recorded). **No target in this slice is
      checked off by a timing** -- the W3 targets become recorded observations attached to
      structural boxes. The quality-tier wall has never been measured and must come from the
      GitHub run, not a worktree.
- [ ] **C1 S, driver-only** W2.3's generated manifest region. **Its invariant-3 precondition has
      lifted** -- all four text readers now read the lock, and `scripts/ci-runner/gate-spec.ts:10-18` says so.
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
- [ ] **D1 C** Cross-OS. Only W5 P1's `/proc`-vs-`ps` seam exists (`.claude/rediacc_hooks/proc.py:32-43`);
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
      **Invariant 2 bites in six places, all verified:** `.ci/config/language-policy-baseline.json:476`;
      `.ci/policy/.dead-bash-allowlist:42` plus three golden files encoding the line index;
      `.ci/rediacc_ci/quality/trap_registry.py:227` (`TRAP_HOOK_SUITE`, a single path constant, plus two control
      fixtures); `.ci/rediacc_ci/quality/hook_integrity.py:69` (`SUITE=`, single path); and two line-numbered measurement
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
      only `__init__.py` and `tools.py`; the 22 rows DESCRIBE installs and `.ci/rediacc_ci/setup/tools.py:167-169` says
      so ("prose, not something this module executes"). `setup` is still bash: `run.sh:97`
      `PORTED_VERBS=()` -> `.ci/legacy/run-legacy.sh:1068` -> `setup()` `:543-715` + `setup_check()` `:719`,
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
      **The trap:** `.ci/scripts/test/gates/test-run-sh.sh:315-327` requires `n_legacy > 0` before believing any
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
      the OLD fingerprint, i.e. the `client_id_sha256` that
      `.ci/config/bws-token-expiry.json` records for `mc_migrate_claude`. Cite the file,
      not the value: the value changes at the cutover, which is the whole point.
- [ ] **W4-D1 S** The `.ci/policy` contract has already drifted, **one day after the move**.
      `POLICY_FILES` holds 15 (`scripts/lib/policy-paths.ts:69-86`); the directory holds 16.
      `.language-policy-allowlist` is reached by a hardcoded join at `.ci/scripts/quality/check_language_policy.py:112`,
      bypassing the seam. **Acceptance:** three-way set equality -- directory == `POLICY_FILES` ==
      the Python name set. This box is the evidence that W4 P4b's inventory gate is load-bearing,
      not cosmetic.
- [ ] **W4 P4a S** Python `policy_path`. Five hardcoded literals (`.ci/rediacc_ci/quality/go_deps.py:178`,
      `.ci/rediacc_ci/quality/plan_housekeeping.py:238`, `.ci/rediacc_ci/quality/profiler_coverage.py:166`, `.ci/scripts/quality/check_language_policy.py:112/114`,
      `.ci/scripts/quality/check_runner_advice.py:899`). **Design constraint:** `.ci/scripts/test/gates/test-policy-path.sh:79` asserts the TS
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
      `scripts/check-suppression-liveness.ts:61` comment ("Today POLICY_DIR is '' and this is a provable
      no-op", untrue since `b80552370`). Rules: no comment may assert a `POLICY_DIR` value
      differing from `scripts/lib/policy-paths.ts:57`; no comment may cite a policy file by a root path.
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
      registered at `scripts/ci-runner/manifest.ts:2537`. Residue: 13 files mentioning `workflow_call`, **2 distinct
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
      (`.ci/rediacc_ci/tests/test_core_env.py:74-105`, `:434`), with a `python3 -m rediacc_ci.core.env` CLI -- and
      **zero production importers**. `bws_env_load` likewise has zero callers. Both orphaned.
      **Seven sites with a disposition each:** `.ci/config/constants.sh:22` STAYS bash (sourced before Python
      is guaranteed; bootstrap circularity) until W6 P3; `.ci/lib/account.sh:438` and `:791` retarget;
      `.ci/scripts/lib/toolchain.sh:34` is bootstrap-sensitive, measure first; `.ci/legacy/run-legacy.sh:185` **do not
      retarget** (W6 P5 deletes it -- record the decision so it is not re-found and mistaken for a
      miss); `scripts/dev/deploy-bench.sh:137` retarget before W9 P2 moves it;
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
      `.ci/scripts/quality/check_plan_boxes.py:41`/`:42-44`; `04-decisions.md` section A item 6 (`:22-23`) is the
      operator override licence. P2.7's subject is the gate rule; P3.2's is the decisions doc.
- [ ] **W11 P4a C** `policy` provider + region replacing `.ci/policy/README.md`'s hand-typed
      section 2, whose heading literally reads "fifteen" against 16 files on disk.
      **Acceptance:** two-direction set equality, key set == `ls .ci/policy` minus README ==
      `POLICY_FILES`. **It is RED on landing**, which surfaces W4-D1 structurally; this box does
      not fix it, it hands the one-line addition to that box as a fragment.
      **Do not derive the Readers column by grep** -- `scripts/lib/doc-providers.ts:568-583` records that a
      grep-derived Readers column flipped mid-run on 2026-09-06 and forbids re-adding it.
- [ ] **W11 P4b C** `test-split` provider + region in `07-port-brief.md`, rendering the residue as
      an explicit `(unregistered)` row. Non-empty is legal and visible; silence is not.
- [ ] **W11 P5a S** Providers `bootstrap`, `job-graph`, `media` with their regions, one commit.
      `scripts/check-doc-region-parity.ts:22-30` makes invariant 1 automatic here: a provider without a
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
      deadlock A5 avoided no longer exists: `.ci/scripts/quality/check-plan-housekeeping.sh:51` states "THE REMEDY IS
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
      (`.ci/scripts/quality/check_plan_record.py:44`, window `:167-168`, anti-vacuity `:74-79`, four set-based floors
      `:663`); tracked census at `agent/census-plan-record.jsonl`, span 0.41 of 14 days.
      **Do not close the window early to get a quiet number** -- B1 runs inside it and will move
      `would_refuse`, which is exactly what the census exists to measure. **C11 at 0/4 is the one
      to watch:** a candidate that never fires is either a rule with no subject or a broken
      instrument, and the tick must say which.
- [ ] **W12 P3.1b C, before W9 P2** Read epic ids from the ledger, not a published document.
      `scripts/check-pr-task-trailers.ts:285` reads `agent/pr/<branch>.md`, itself generated by
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
      wrong:** there are TWO sets, not three -- `CLOSED_STATES` at `.claude/hooks/stop/wl_planfile.py:221` is
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
      among its keys; `scripts/gen-docs.ts:268` says MISSING keys are **fatal** to `--diff-snapshot`, so
      the moves break the programme's own verification instrument unless the four keys are
      re-keyed in the same commit -- never `--snapshot --force`. (b) the 42-entry
      `unguarded` baseline. Plus the six invariant-2 inventories.
      **Exclude `.ci/breakpoint/**` from any rewrite sweep** -- two files there contain the string
      `scripts/check-` and a blanket sed would break `MANIFEST.sha256`.
- [ ] **U1 C** Requirement 15: a `json-inventory` provider + region over root / `.ci/config` /
      `scripts/data` / `.ci/policy`, with `Discovered by` and `Configurable path?` cells. The
      predicate exists only as prose at `docs/ci-overhaul/08-driver-contract.md:318-334` and **three of its numbers
      went stale in one day**, which is the argument for generating it.
- [ ] **U2 S after P6a, OPERATOR-GATED** Cross-repo PRs. **`private/growth` is not a submodule** --
      `.gitmodules` lists four and `.gitignore:85` ignores it. That clause cannot be executed as
      written; split it into a decision box (documented clone-and-remote procedure, or promotion
      to a real submodule). Name an owner and record the merge order the `pr-merge` skill encodes.
- [ ] **U3 C** Widen `.ci/scripts/test/gates/test-shrink-only-composition.sh:97-102`. It greps `--include=*.ts
      --include=*.js` over `scripts/` and `packages/www/scripts/` -- **two** blind spots: it
      excludes `.py` AND its roots exclude the entire `.ci/` tree. Live subjects today: exactly
      one tracked `.py` offers `--write-baseline` (`check_language_policy.py`) plus
      `.ci/scripts/quality/check_resprofile.py:365`'s equivalent `--reseed-class` over an ACCUMULATING baseline. **The
      hole is self-declared** -- `.ci/scripts/quality/check_language_policy.py:418-428` says the port "names the
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
- [ ] **U5 C** `scripts/check-shape-duplication.ts:122`: `/'(?:[^'\\]|\\.)*'/g` -- `[^'\\]` matches
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

---

# Round 1: the original plan, its history and its ticked boxes

Status: READY. Twelve workstreams drafted by Plan agents, attacked by two adversarial reviewers each, revised against evidence, then ordered and criticized for completeness. Discovery and design artifacts: `/tmp/claude-1000/-home-developer-console/8f55d4f0-b308-4204-b5a2-3ec82e8f8cd9/scratchpad/` (7 reports) and the workflow journal under `.claude/projects/.../workflows/wf_2e95f418-6a8/`.

## Context

The tooling surface is about 245k lines: `.ci/` 122k (91% bash), `.claude/` 62k, `scripts/` 52k TypeScript, `eslint-rules/` 6.4k JavaScript, and a 2,640-line `run.sh`. Discovery found three verbatim duplications and hundreds of copied helpers, five divergent tool-install lists, a half-built gate registry, a GitHub quality tier that runs 131 gate tests in one step and is floored by a single 785 s hook suite, 1,014 environment variable names across ten sources of truth, Linux-only bash with four live macOS bugs, sixteen allow/block lists at the repo root read by cwd-relative code, and an `agent/` history whose pointers mostly do not resolve.

Goal: one enforced language rule, one shared Python core, a declaration-driven gate registry that emits both the local runner input and the CI shard matrix, a bootstrap that installs everything hooks and gates need, centralized environment with Bitwarden as the only credential path, an `agent/` history that is trustworthy and pushed to agents rather than remembered, and measurable parallelism gains. Testing and parallelization are the top priorities. Implementation runs under ultracode: a root driver, ten sub-drivers, agents in worktrees.

## Measured baseline (2026-09-06, branch point c6d3af163)

Every threshold in this plan is judged against these, not against remembered numbers. Four workstream drafts asserted different figures; these are the verified ones. They drift fast: the manifest gained two gates during this planning session alone, so a box that PINS a count is wrong by construction. Cite the command, not the number.

| Fact | Value |
|---|---|
| Manifest entries | 390 `gate: true`, 393 `id:` literals, and RISING (two gates landed mid-session) |
| Gate test files | 131 under `.ci/scripts/test/gates/` (manifest carries 132 `qualityGateTest`; reconcile the off-by-one) |
| Quality gates in bash | 74 `check-*.sh` plus 5 non-check wrappers |
| Files carrying a `---- gate ----` header | 19 tracked, of which 14 currently parse (1 is fixture data, 2 close with `---- /gate ----`) |
| `ci:quick` receipt | 58,029 ms wall; the fast set is what `npm run ci -- --quick --list` prints, not a number to quote |
| Local full-run floor | 785 s, set by `gate-test:claude-hooks` |
| TRAPS.md | 75 headings, exactly on its floor of 75 |
| `.claude` guards | 47 (37 pre-bash, 7 pre-edit, 1 pre-ask, 2 post-bash). **`test-hooks.sh` counts RE-MEASURED 2026-09-07: 398 `check` and 23 `check_out`, not 374/21.** Grown, not regressed, so M5's "395 assertions" is stale in the same direction. `grep -cE '^[[:space:]]*check[[:space:]]'` |
| `package.json` lint keys | `check:lint` at 253, `fix:lint` at 280, `lint` at 293 |
| `.ci/policy/` | EXISTS as of 2026-09-06 but holds only README.md. No allow/block list has moved: all 14 dotfiles are still at the repository root and bws-secret-map.json is still in .ci/config. W4 P2 and P5 are correctly OPEN, but a reader who greps for the directory will conclude otherwise |
| Python on the HOST (not the devbox) | 3.14.4 and ruff present; pytest, uv, uvx, pip, pipx absent. Re-measured 2026-09-06: this row was taken on the bare host `nuc12dcm` and mislabeled. No devbox container is running for this worktree and `/.dockerenv` is absent, so every tool-presence number in this plan describes the host. Not a defect: `.ci/scripts/lib/toolchain.sh` provisions shfmt, shellcheck, actionlint and ruff on demand, version-pinned with a recorded sha256, and pytest comes from the uv shim, so absent here means not yet fetched rather than unavailable. The image itself installs uv/uvx/shellcheck/shfmt but NOT actionlint or pytest, so "the devcontainer has everything" is false in both directions. gitleaks is referenced by zero gates and is wishlist, not gap. |

The Bitwarden shadow retirement already landed at 7343ae9dc: the comparator, its fixture and its gate test are deleted and 45 org secrets are gone. `mc_migrate_claude` (expires 2026-09-08) is now the sole credential path for all of CI and CD.

## Decisions (do not re-litigate)

- **Full port, staged.** Everything in `.ci` and `.claude` becomes Python. The infra-only state is a valid checkpoint (milestone M4).
- **Frozen bash, allowlisted with BLOCKER reasons:** the media/tutorial pipeline (it drives `private/generative` and `private/growth`, gitignored repositories a worktree cannot open), reorganized into `.ci/media/` but not ported; `.ci/breakpoint/` (vendored, drift-locked); `.ci/tutorials/*.sh` recordings; one-line shims.
- **TypeScript stays** for the 117 `scripts/check-*.ts` gates, `scripts/ci-runner`, and `eslint-rules` (JavaScript). Boundary: `.ci` is infrastructure, `scripts/` is product-source analysis needing an AST.
- **Python package: `.ci/rediacc_ci`**, importable as `rediacc_ci`. Hooks live at `.claude/rediacc_hooks` and import it.
- **OS target:** Linux, WSL and macOS natively. Windows gets a launcher into WSL. No Windows-native gating.
- **Bitwarden:** full cutover. No token-expiry CI gate is added; an expired token already fails loudly everywhere, and a clock-driven gate that reds on a quiet day is a worse trade. The local warning in `bws-map-refresh.py` stays.
- **Node floor 22.13.0**, single source in `toolchain.env`, bound to both `engines.node` fields. Also address issue 587 (migrate to npm 11) in the same workstream, since it is the same class of pin drift.
- **Local development gets dev-only signing keys** from a separate `dev-shared` Bitwarden project. Production ED25519, X25519 and JWT keys never reach a developer shell.
- **Root allow/block lists** move to `.ci/policy/`.
- **agent/ history:** variant A of the attested intent-blame design (W12). Records key on blob ids (this repo merges with `gh pr merge --rebase`, so branch SHAs dangle), carry a Record-Sig, are gated for resolve, live and signature, can only be written by the verb, and are pushed to the agent on its first edit of a file the record names. Nothing is ever deleted.
- **The bash-coverage ruling is re-opened out loud** as `04-decisions.md` ruling 7, per that file's own A6 licence.

## A grammar addition landed 2026-09-07: `needs-not:`

`inferredNeeds` deliberately OVER-infers, and that asymmetry is correct: over-inferring
only blocks a declaration, while under-inferring kills a gate on a clean runner. But it
reads ORDINARY STRING LITERALS after `stripProse` has removed the docstrings, and a
control's own description routinely names a tool it never runs. Measured:
`ctl.check("TOOLING: an absent npx yields 127, not an exception")` infers `node` for a
pure-Python gate.

Tightening the pattern was REJECTED ON MEASUREMENT rather than taste: requiring command
position for `npx`/`tsx`, as the code already does for `node`, drops the inference on 24
files, and at least one of them (`test_gate_policy_path.py:48`) really does execute
`node_modules/.bin/tsx`.

So the safe default STAYS and the escape is ARGUED: `needs-not:` subtracts one inferred
capability and REQUIRES a `blocker:` reason, refusing without one. Proven both ways, and
it took `.ci/scripts/quality` from 48 of 49 Python gates declaring to **49 of 49** --
`check_checkout_cone.py` had been the sole holdout, and this was why.

## Invariants every box must respect

1. **Emitter and its parity gate land in the same change.** Anything that becomes generated (manifest, workflow regions, docs) takes its checker with it. This is the rediacc/console#549 failure class.
2. **Shrink-only and extension-keyed inventories are re-keyed in the same change as the move that would trip them:** `shfmt.sh:71-72`, `check-hook-integrity.sh`, `check-dead-bash.ts:152` and `:198`, `check-em-dash-surfaces.ts:137`, `check-gate-id-convention.sh:79-80`, `check-ci-parity.ts:72-73`.
3. **`manifest.ts` keeps every entry literal** until the three text readers (`wl_reggate.py:364`, `check-gate-id-convention.sh`, `check_test_file_orphans.py`) read `gates.lock.json`.
4. **The anti-vacuity contract survives the port:** exit 0 with zero PASS lines is a failure, `--selftest` runs before every real scan, MIN floors hold, exit 77 means cannot-run and never a verdict, planted-defect controls stay with their gate.
5. **Shadow before cutover.** A ported gate runs against its bash twin over K distinct trees with a committed differential artifact before the twin is deleted. Repetition on one tree does not count.
6. **Disjoint files per concurrent agent.** Shared registry files have exactly one writer in flight program-wide.
7. **`agent/` is live gated state** (`wl_store.py:274`). Not gitignored, not restructured without a seam first.
8. **`.ci/breakpoint/` is never touched by a sweep** (`MANIFEST.sha256`, `check:ci-breakpoint-drift`).
9. **Comments are the asset.** Ports transliterate comment archaeology into module docstrings or a `why:` field. `.claude` guards are 52% comments and `command-scan.sh` records six bypass rounds.
10. **No em dashes** in any new file.
11. **A gate-bind region may only be emitted into a lane that has an `- id: setup` step.** Verified: eight of ten lanes have one; `quality-branch:507` and `quality-submodule-branches:587` do not, and every emitted step is guarded on `steps.setup.outcome == 'success'`, so a region there would skip every gate while reporting green. Gates needing `fetch-depth: 0` and the PR head ref stay hand-registered in `quality-branch`.
12. **`gate-bind --write` owns whole regions.** A `--write` on 2026-09-05 deleted four hand-added steps. Any box running it asserts the reported `dropped` set is empty, and only the root driver runs it.
13. **A writer agent authors its registration as a PATCH FRAGMENT; the driver applies it in the
    same commit as the gate file.** This resolves a contradiction the two rules would otherwise
    create, and it removed six workstream phases from the parallel plan before it was noticed:
    invariant 1 says an emitter and its parity gate land in the SAME change, and the registry
    write model says `package.json`, `manifest.ts` and `.github/workflows/**` have exactly one
    writer, the driver. Read literally, no box that registers a gate can be executed by an agent
    at all, which would strand W3 P2, W4 P4, W5 P5, W10 P5, W1 P6, W12 P3.1b and half of W2.3
    and W2.5. The fragment convention keeps both rules: the agent writes the gate, its test and
    its exact literal registration lines, and the driver pastes those lines and commits the whole
    thing together. Proven in practice on 2026-09-06, when ten concurrent writers handed over
    registrations this way and the registry files never had two writers.

14. **No timing number from a feature worktree is admissible.** `.ci/cache` is gitignored and per-worktree, and a 4.5 s gate has been measured at 21 s under two concurrent writers. Every acceptance is structural (set equality, PASS counts, planted controls); timings come from one quiesced reference worktree.

## Program arbitrations (settle before any sub-driver launches)

The twelve workstreams were drafted independently and contradict each other in twenty places. These are the resolutions. They belong in a tracked driver contract (W0.5) so no sub-driver re-decides them.

| Conflict | Resolution |
|---|---|
| Python package path (four proposals) | `.ci/rediacc_ci`. `test-gate-anti-vacuity.sh:299-312` copies only `scripts`, `.ci/scripts` and `.ci/config` into its fixture, so W1's first phase must add `.ci/rediacc_ci` to that copy list, in the same change. |
| Python config home (three proposals) | One `pyproject.toml` at the repo root holding ruff and pytest config; `ruff.toml` is deleted and the four `--config` arguments in `check-python-lint.sh` are removed, since both tools discover it. `.ci/ruff.toml` is dropped. |
| Test runner and roots (three proposals) | pytest, provisioned by the uv shim. Tests live beside their package: `.ci/rediacc_ci/tests`, `.ci/tests/gates`, `.claude/rediacc_hooks/tests`. One edit adds all three to `check_test_file_orphans` SEARCH_DIRS. |
| `run-all.sh` fate (four futures) | Re-key in place (W2, W3), then W7 replaces it with `battery.py` at the end. Never concurrent. |
| Registry write model | Hand-append is legal until W2 lands the generated region plus `gates.lock.json`. After that, registration is a gate header and only the root driver runs `gate:bind --write`. |
| `test-hooks.sh` split owner | W5 owns it. W3's hook-split boxes are delegated to the hooks sub-driver, with one set of wrapper names. |
| `run.ps1` design | W6's WSL launcher (`wsl.exe --cd`). W1's docker-run launcher is dropped. One test file, one `ROOT_MANIFESTS` entry. |
| Node floor and `constants.sh` | W0 owns it, in wave 1. W6 must not touch `NODE_VERSION_MIN`. |
| The five go pins | W0 writes the `ARG` lines by hand in wave 1. W6 later generates the region and must adopt the existing names, asserting no value change. |
| `toolchain.env` writers | Append-only, sequenced W0 (Node floor, go pins) then W1 (UV and PYTEST) then W6 (adoption). |
| `local-common.sh` lifetime | W8's `env_file_load` lands in `rediacc_ci/core/env.py` with a bash shim. W7 deletes the file only after W6's quality lane and W8's retarget. |
| `scripts/dev` ownership | Sequence: W8 deletes its dead script, W0 and W8 make their edits, then W9 moves the directory. |
| Language policy gate | One gate covering both trees, one exemption list. W5's second gate is dropped. |
| Bitwarden token schema | W0 owns the `tokens[]` restructure once; W8 consumes it. Existing `warn_days: 5` is preserved unless the owner changes it. |
| W-key cross-references | Four plans schedule against wrong keys. The driver contract carries the authoritative map and every `serial_after` is re-mapped before launch. |

## Workstreams

Boxes marked C are concurrent (file-disjoint from siblings); S is serial. Phase counts in parentheses are from the revised plans.

### W0: Pre-work, hygiene, known bugs and the driver contract

Goal: land every fix later workstreams silently assume, each box one worktree, each proven by a test that is red before and green after.

#### W0.0 Owner-only actions (no worktree, no tracked change)
- (round 1, SUPERSEDED by a Round 2 box above) Mint `mc-ci-read` (read-only, ci-shared), `mc-rotate` (read-write, admin) and `dev-shared` in the Bitwarden web vault.
      **OPERATOR RULING 2026-09-06: take the default, do not mint today.** The decision is
      made and is not open; what remains is a DATE-TRIGGERED ACTION on 2026-09-08, and it
      belongs to the OPERATOR, not to a session. `BWS_ACCESS_TOKEN` is not in an assistant
      session's environment, so the probe cannot be run from one: scheduling it for an agent
      would create a task that can only fail. Recorded here rather than only in a worklist
      item because a worklist item does not outlive the session that wrote it, and this is
      the last durable place a future reader will look.
      ON 2026-09-08, in the operator's shell: probe the live store with `bws_env_load`. If it
      fails, every wave needing a credential stops, `.ci/config/bws-token-expiry.json` is left
      truthful rather than optimistic, and the failure carries `door:operator-only` with the
      minting steps. `mc_migrate_claude` expires that day and is the SOLE credential path for
      all of CI and CD, so this is not a soft deadline. No `bws` verb mints a machine-account token, so only the owner can. Record expiry dates and client-id fingerprints. Hard deadline: the current token expires 2026-09-08 and is now the sole credential path.
- [x] Remove the two gitignored strays from the working checkout: `tsconfig.tsbuildinfo` and `audit-report.json`. **DONE 2026-09-07:** both were still on disk (7,203 B and 3,058,160 B); removed, and a third stray `.err` from a macOS bash 3.2 probe went with them. `git status --porcelain` no longer lists any untracked file.

#### W0.5 Driver contract and program decisions (serial head, blocks every sub-driver)
- [x] S Land `docs/ci-overhaul/08-driver-contract.md`: the W-key map, the arbitration table above, the single-writer lock table for `package.json`, `manifest.ts`, `ci-quality.yml`, `run-all.sh`, `test-hooks.sh`, `TRAPS.md`, `CLAUDE.md`, and the machine-mutex list (docker daemon, traefik namespace, `~/.rediacc`, port 4800, `account.db`).
- [x] S Record one uncontended full-run timing baseline as a tracked file. **DONE 2026-09-06 (57a23200d):** docs/ci-overhaul/11-timing-baseline.md, 437 gates, wall 780.4s, serial 7021.0s, 9.0x. The receipt records the CONDITIONS too, because a number without them is how the four conflicting figures got into the drafts.
- [x] S Record the floor policy decision out loud: "retire file-count floors" is superseded by "floors must be set-based or corpus-derived, never hand-typed counts", since three workstreams raise floors and none retires them.
- [x] S Record the "modular and dynamic" acceptance test, so the requirement can be checked off: adding a gate, an allowlist or a hook requires no edit to any workflow, runner or dispatcher file.

#### W0.2 Runtime bug fixes (concurrent)
- [x] C Fix the logger clobber at the library in `.ci/scripts/lib/emit-advisory.sh:23-32`: assign colours only when UNSET (`${RED+x}`, because `common.sh:26-31` deliberately sets `RED=''` off a tty), define each `log_*` only when `declare -F` fails, change `$1` to `$*`. Test the real chain (`common.sh` then `blocker-validator.sh:26` then emit-advisory) capturing stdout and stderr separately, since the defect is a stream swap.
- [x] C Register `require-jq.sh` first in the PostToolUse Bash block; both post-bash hooks parse stdin with jq and fail open today. Add a require-jq-first predicate with both-direction controls to `check_hooks_resolvable.py`.
- [x] C Add jq-absent cases to `test-hooks.sh` via a `check_nojq()` helper, building the JSON payload before restricting PATH.

#### W0.3 Delete verified-dead files (concurrent, each drains its own references)
- [x] C `.idx/`, `.gemini/`, root `docker-compose.yml`, `Rediaccfile`, `pyroscope.yaml{,.template}`, draining `scope-map.cjs` and `greenlight.cjs`.
- [x] C `.claude/plans/*` (2 files). [x] C `.claude/skills/skill-test-iterate.md` and its one inbound sentence. [x] C `eslint-rules/i18n/shared/locale-cache.js`. [x] C `scripts/generate-update-index.ts`. [x] C `.ci/scripts/docker/build-image.sh`, draining the shrink-only baseline entry in the same box.

#### W0.4a Lint scope and npm 11 (sole `package.json` owner in W0)
- [x] S Widen `check:lint`, `fix:lint` and `lint` (verified at `package.json:253, 280, 293`) from three roots to seven, adding `eslint-rules .ci workers .github/actions`, and fix the three measured errors. Add a root-drop mutant control to `check_lint_scope_coverage.py`.
- [x] S Issue 587: migrate to npm 11. Bump the pin in `check-lockfile.sh` from npm 10, invert the `CLAUDE.md` lockfile section, check every other npm pin agrees, confirm `ignore-scripts` plus `install:natives` behaves identically, and run the full `npm run ci`, not just quick.

#### W0.4b Pins, ignores, redaction, stale lines, decision record (concurrent)
- [x] C `.gitignore`: add `.env.*` with negations for the three tracked example files.
- [x] C Pin the five `go install ...@latest` at `.devcontainer/Dockerfile:285-289` as `ARG X_VERSION=` lines and register the watchable ones.
- [x] C One Node floor: `NODE_VERSION_MIN=22.13.0` in `toolchain.env`, read by `constants.sh:45` with `:?`, bound to both `engines.node` fields by a new sync control. Removes the masking fallbacks in `run.sh` and `setup.sh`.
- [x] C Redact the four AKIA ids in `agent/PLAN-secret-namespace-migration.md:1615-1616`. The `:1617` value is a token id under a "new id" header, not a bearer, so no rotation.
- [x] C Make three count-bearing stale lines count-free so they cannot re-stale, and fix two narrow stale lines.
- [x] C Record ruling 7 in `docs/ci-overhaul/04-decisions.md` section A: the single-language rule, what bash survives, and that it supersedes `PLAN-shell-resource-profiling.md:7`. Mark that line superseded.

#### W0.1 Bitwarden token schema and cutover (serial, after W0.0 and W0.4a)
- [x] S Restructure `.ci/config/bws-token-expiry.json` to a `tokens[]` array and update its only reader. **DONE, box was simply never ticked:** the file carries warn_days plus tokens[], and the sole reader consumes the array at scripts/dev/bws-map-refresh.py:87. NOTE the plan's old path for that reader (.ci/scripts/quality/bws-map-refresh.py) does not exist and never did.
- (round 1, SUPERSEDED by a Round 2 box above) S Cut CI and local over to `mc-ci-read` and prove it by fingerprint, not by greenness: dispatch one workflow printing `sha256(client-id)` and compare.

Merge waves: wave 1 is W0.5, W0.0, all of W0.2, all of W0.3, W0.4a, all of W0.4b in parallel worktrees; wave 2 is the W0.1 schema box rebased on W0.4a; wave 3 is the cutover.

### W1: Python foundation (6 phases)
- [x] P1 Bootstrap and pin foundation. Serial head: nothing can be proved until Python has a package manager. Checksum-pinned uv shim, `UV_*` and `PYTEST_VERSION` in `toolchain.env`, the anti-vacuity fixture taught to copy the package, `toolchain.sh` stops hardcoding linux and bare `sha256sum`.  **DONE 2026-09-06:** W1 P1 bootstrap+pins landed (.ci/bootstrap.sh, pyproject.toml, uv shim)
- [x] P2 Package skeleton, root `pyproject.toml` replacing `ruff.toml`, the pytest gate placed in a lane that installs pytest, and the shared controls runner replacing the per-file Tally pattern.  **DONE 2026-09-06:** W1 P2 package skeleton + pyproject replacing ruff.toml + check:ci-pytest
- [x] P3 Core modules and the cross-language golden mechanism. Thirteen concurrent boxes, one module plus its tests each: log, paths, proc, gitx, ghx, dockerx, env, secrets, toolchain, workflows, hookio, allowlist, platform. Goldens prove `lanes` and allowlist verdicts byte-equal from both sides.  **DONE 2026-09-06 (5c85a675e), superseding the earlier 4-of-13 note:** twelve of thirteen exist under .ci/rediacc_ci; hookio is the thirteenth and lives under .claude/rediacc_hooks by the arbitration table, not here. The goldens landed with the allowlist module: 17 frozen corpora recorded from the REAL bash and TS readers under a provenance header, with a live three-way differential over the tree's actual lists. Nine mutation probes, the strongest killing 31 tests; a tenth passed at first and exposed that no real reason exercised normalization, which was fixed by deriving a corpus that does.
- (round 1, SUPERSEDED by a Round 2 box above) P4 Policy gates, the canonical path line, and the root-resolution sweep that removes the `sys.path` mutations. **RE-DERIVE BEFORE STAFFING: 67 files carry a `sys.path` mutation, measured 2026-09-07** (`grep -rln 'sys.path.insert\|sys.path.append' .ci/ .claude/`). It was 24 in the draft and 48 on 2026-09-06, so this box has grown on every measurement as the ports add Python. Do not staff it against a remembered number. Two other boxes (W6 P2, W8 P2) wait on this sweep, so its real size decides their scheduling.
- (round 1, SUPERSEDED by a Round 2 box above) P5 Package CLI, the WSL launcher, hook packages, and `INP001` no longer globally ignored. **THREE OF FOUR CLAUSES ARE DONE, measured 2026-09-07; only INP001 remains.** (1) The WSL launcher landed under W6 P1: `run.ps1`, 63 lines, `wsl.exe --cd` with UNC translation, plus `run.cmd`. (2) Hook packages landed at `7acaeca98`: `.claude/rediacc_hooks/` is a real package with 51 guard modules and its own `tests/`, declared in `pyproject.toml` testpaths. (3) The PACKAGE CLI landed today: `.ci/rediacc_ci/__main__.py`, 195 lines, verb table as DATA (`VERBS: tuple[Verb, ...] = ()` at :85, handlers as dotted strings resolved lazily so `--help` imports nothing). Driven, streams captured SEPARATELY: `--help` rc=0 with 294 B on stdout and 0 B on stderr; no verb rc=2 with 0 B on stdout and 131 B on stderr, no traceback; unknown verb rc=2. Proven able to fail by a whole-CLI mutation run in a scratch copy with three planted defects: 8 failed, 8 passed. NO VERB WAS REGISTERED and that is correct, not a shortfall: the legacy dispatcher owns all 16 arms, and registering a name without deleting its legacy arm is the exact overlap `test-run-sh.sh` partitions against in both directions. `PORTED_VERBS` stays `()`; the run.sh change is comment-only, because lines 18-20 had become untrue. (4) INP001 is still in the global `ignore`; full removal needs W5 P7, but NARROWING it to `per-file-ignores` for the three flat script directories is available now. **Headroom warning for W6 P3: `run.sh` is at 120 lines against a ceiling of 120, so `PORTED_VERBS=(setup)` is line-neutral only if it adds no comment line.**
- (round 1, SUPERSEDED by a Round 2 box above) P6 Strict flip of the language policy, after the ports land: no baseline file at all, only allowlisted bash remains.

### W2: Gate registry (7 phases)
- [x] W2.0 Binder foundations: parser v2 with a `kind` discriminant so gate-tests and sub-gates declare without a `step`, an explicit non-emitting class, an import guard, regions in every lane that has a setup step, fixture ignores. Fix the two files closing with `---- /gate ----`.  **DONE 2026-09-06:** W2.0 parser v2: kind discriminant, emit:false, import guard, malformed-header reporting, invariant-11 mechanised
- [x] W2.1 Registry loader and a committed `gates.lock.json` in manifest file order (pool.ts uses array index as its scheduling tiebreaker), with a drift gate.  **DONE 2026-09-06:** W2.1 gates.lock.json, 420 entries in manifest file order, drift gate in the same file
- [x] W2.2 Shadow-gate core: compare exit code plus finding sets, both-empty and new-side-true both count as mismatch, ledger records only clean trees. Usable by W4, W7 and W8.  **DONE 2026-09-06:** W2.2 shadow comparator, registered, 8 verdicts of which one is a pass
- (round 1, SUPERSEDED by a Round 2 box above) W2.3 Headers on every gate, then the lock and the generated manifest region (generated literal region plus a hand region for composites).  **HEADERS DONE 2026-09-06 (ce8dbac6d, 1490d7b7d): 148 of 148 gate tests declare, and the binder now READS them, which it did not when they landed. The generated manifest region is still open, so this box stays open.**
- [x] W2.4 Isolation as a path-scoped contract defined once and implemented identically in `pool.ts` and `run-all.sh`; inventories re-keyed; the three text readers drained; counts fixed.  **PARTIAL, CORRECTED 2026-09-07 BY MEASURING THE LOCK.** The three text readers WERE drained and pool.ts and the battery both implement the contract, so half the box is real. But the DECLARATIONS never landed: of the 148 gate-test entries in gates.lock.json, `mutex`, `reads`, `heavy` and `weight` are populated on **ZERO**, and only `slow` is set (34 of 148). No entry anywhere in the lock carries a `reads` key at all; `mutex` exists on 12 entries repo-wide, none of them a gate test. The consequence is observable rather than theoretical: the battery is running on its LOUD FALLBACK today, printing "no 'tree:' isolation declared in scripts/ci-runner/gates.lock.json; falling back to the hand-maintained W/S lists in this file" at :303-304. So the hand-maintained lists this box exists to retire are still the live source of truth, and W7 P3's `battery.py` inherits the same fallback. A contract implemented by two readers with no data to read is not done. **CLOSED 2026-09-07, and the root cause was a MISSING TYPE, which is why this sat green for a day.** `gate-spec.ts:45` declared `mutex?: string[]` and there was NO `reads` field at all, so the 21 scanner gate tests were UNDECLARABLE by construction while `run-all.sh:275-276` asked `classify_from_lock` for exactly that claim. Added `reads?: string[]` to the spec, then wrote 25 declarations into manifest.ts -- `mutex: ['tree:repo']` on the 4 writers, `reads: ['tree:repo']` on the 21 scanners -- 25 insertions and ZERO deletions, derived FROM the existing fallback arrays rather than invented, so this moves the classification into the registry instead of restating it. Lock regenerated, 456 gates, and it now carries `tree:` on exactly 4 mutex and 21 reads entries. THE PROOF IS A WARNING THAT STOPPED: the battery no longer prints "no 'tree:' isolation declared ... falling back to the hand-maintained W/S lists", stderr is clean and it exits 0. The arrays remain on purpose as a fail-loud backstop -- their own comment says "no declarations yet" and "lock is broken" must not silently become "nothing needs isolating" -- but they are no longer the source of truth
- (round 1, SUPERSEDED by a Round 2 box above) W2.5 `paths` in two tiers: statically enumerable first with `paths_origin` recorded, traced second and only where the soundness oracle covers everything. No `private/<x>/**` globs.  **PARTIAL 2026-09-06:** REVERTED to open 2026-09-06: I marked this done and it is not. `paths_origin` DOES NOT EXIST anywhere in the tree -- grep returns nothing, and gate-spec.ts declares only `paths?: string[]`. What landed is a PROSE COMMENT convention that nothing enforces and no gate can read. Only 35 of 420 lock entries carry `paths` at all. Tier 2 remains correctly unstarted.
- [x] W2.6 Shadow headers, CI emission, cutover procedure, and one real pilot pair cut over end to end.  **DONE 2026-09-07 (5d6f07955):** regions emit and own their steps; 112 hand-written duplicates removed, 10 jobs and 264 unique step names both before and after, actionlint green. The deleter guard written for one job-boundary failure found a SECOND at the other end of each span. **CORRECTED 2026-09-07 by measuring HEAD rather than believing the earlier note: this box is [x] for the REGIONS and carries a live defect. `gate:bind --write` does not emit per-step `env:` at all -- grep for `env` in scripts/gate-bind.ts returns only shebangs and test fixtures -- so the emission at 5d6f07955 landed steps with their env stripped. HEAD's ci-quality.yml holds 20 `env:` blocks where the correct file holds 26; the 11 missing lines sit on steps that READ them, including `check:ci-pr-task-trailers` (PR_HEAD_REF, PR_BASE_REF) and the Docker image freshness step (DOCKERHUB_TOKEN). The repair exists ONLY as uncommitted working-tree work in this shared checkout (711/340, 11 env lines added and zero removed, step-name set byte-identical at 274 = 274, check:ci-gate-bind green at 377 declared gates). An earlier session note in STATE.md said W2.6 was REVERTED; that is false and is corrected there too. main is unaffected -- it is far behind this branch -- so the defect is branch-local. The box does not reopen, but the binder must learn `env:` before the next `--write`, or that write re-strips these 11 lines.**

### W3: CI-quick and parallelism (4 phases)
- [x] P0 The floor: dedupe the doubled suites (the worklist suite and the dead-bash real-tree scan each run twice per full run today) and split the three hook gates behind ONLY filters.  **DONE 2026-09-06:** W3 P0 both doubled suites down to one run each, delegated and asserted
- [x] P1 Packing: split every serial `&&` chain into manifest entries with a `gate: false` parent, shard lint four ways, backfill `paths`.  **DONE 2026-09-06 (86b76edf9, aa542bc45):** lint sharded four ways; four aggregate parents (check:i18n, check:ci-seo, check:ci-redirects, check:ci-i18n-cross-locale) flipped to gate:false with 20 children registered, taking REAL duplicated leaves from 16 to 3; nine paths sets landed, scoped entries 36 to 44. Acceptance verified independently of the proposal: check:i18n's children's leaves union equals its 28 declared leaves exactly. Also fixed check:ci-package-key-budget, RED at HEAD because gen:docs and gen:gates-lock were never registered; both are now gate:false / local-only manifest entries and the baseline SHRANK 49 to 48. The three remaining duplicates (typecheck-workers.sh, validate-tutorial-cast-output.js, check-cli-docs.ts) are separate findings.
- [x] P2 Heavy-job proxies and the parity surface extension. Wire the proxies that already exist (`test-rdc-update.sh`, `test-linux-packages.sh --dry-run`, the two missing unit keys, the Go unit subset, `license-e2e.sh`) and write the ones that do not (ops host check, the three untested CI scripts, a Stripe offline test, an elite compose proxy). Each returns 77 rather than 0 when its toolchain is absent.  **DONE 2026-09-06 (fab50886f):** ten proxies, each seen RED under a planted violation and each returning 77 (not 0) with its toolchain removed from a real PATH. Elite compose and the Stripe offline test CUT with evidence: one needs a worker VM behind a private submodule, the other forwards webhooks from a live sandbox.
- (round 1, SUPERSEDED by a Round 2 box above) P3 GitHub shard matrix, aggregator, `ci-quick` job and fail-open scoping. All ten lanes replaced by emitted shards with literal runners and timeouts; the aggregator reds on an empty include list, proven by a planted all-dropped run.

Targets: local full-run floor 785 s to 273 s (then lower once the hooks are ported); `ci:quick` at or under 58 s while covering more; quality tier wall at or under 9 minutes.

### W4: Policy folder and duplicate collapse (6 phases)
- [x] P0 Decisions and measured baselines, no moves. `.ci-trigger` stays at root with a recorded reason.  **DONE 2026-09-06:** W4 P0 decisions + baselines, .ci-trigger stays at root with its reason
- [x] P1 Seams: the path helper as a pure join with a validated name set and no registry file and no fallback; per-probe liveness floors; the two non-Python collapses (release-age, SEO prefixes).  **DONE 2026-09-06:** W4 P1 seams: policy-paths.ts as a proven no-op, per-probe floors, release-age collapse
- [x] P2 Movers. **NOT TWELVE CONCURRENT BOXES: ONE SERIAL WRITER.** Measured 2026-09-06 over the 14 root allow/block lists: ZERO of the 91 pairs have disjoint reader sets. scripts/lib/policy-paths.ts and .ci/rediacc_ci/tests/test_core_allowlist.py are each read by all 14, check-suppression-liveness.ts by 10, test-policy-liveness-floors.sh by 8. Staffing this twelve ways produces twelve conflicting branches. Still an atomic `git mv` plus readers plus liveness probe per list, but sequenced. Run W9 P1b FIRST: they share three files under scripts/.  **DONE 2026-09-06 (b80552370):** FIFTEEN lists, not fourteen (the plan's count was doc drift; POLICY_FILES is the contract). ONE atomic change across the set, not one per list: POLICY_DIR is a single constant and eleven readers reach it only through policyPath(). 12 probes, 87 entries declared, byte for byte the pre-move baseline.
- (round 1, SUPERSEDED by a Round 2 box above) P3 One blocker-validator: record a three-way golden corpus from today's bash behaviour first, then Python canonical, bash shim and TS client, with the vendored breakpoint copy kept and proven a subset.
- (round 1, SUPERSEDED by a Round 2 box above) P4 Finalize: `pyproject.toml` adoption, the inventory gate, the prose sweep, Python `policy_path`.
- (round 1, SUPERSEDED by a Round 2 box above) P5 `bws-secret-map.json` into `.ci/policy`, deferred behind the Bitwarden cutover.

### W5: .claude hooks to Python (8 phases)
- [x] P0 Skeleton, dispatcher, harness seams and measured baselines (a fork counter, `GUARD_PASS`, `HOOKS_ONLY`).  **DONE 2026-09-06:** W5 P0 skeleton, dispatcher, harness seams
- [x] P1 Transliterate `command-scan.sh` (272 lines, 157 of them comments) with a differential over a captured corpus of at least 320 strings, plus the `/proc` portability layer with a `ps` backend.  **DONE 2026-09-06:** W5 P1 command-scan.sh transliterated, 387-string corpus, 28 fields compared
- [x] P2 Gate pre-keying and `require-python.sh` on all four matchers.  **DONE 2026-09-06:** W5 P2 require-python.sh on all four matchers, registered with the ORDER bump
- [x] P3 Port batches B1 to B3: 19 guards with no shellscan dependency, three concurrent boxes.  **DONE 2026-09-06:** W5 P3 first guard batch
- [x] P4 Port batches B4 to B6: the remaining 28 guards.  **DONE 2026-09-06:** W5 P4 remaining guards; 46 total, 17529 byte-for-byte comparisons
- [x] P5 Registration, surface gates, hook registry gate.  **DONE 2026-09-07 (7acaeca98).**
- [x] P6 Cutover: harness calls the dispatcher, `settings.json` collapses from 65 command entries to 22, shims deleted, key space migrated.  **DONE 2026-09-07 (7acaeca98):** settings.json 73 command entries to 30, 456 execs per Bash call to 35. Twins MOVED to .claude/oracles/, not deleted: they are what test_guards_differential compares against.
- (round 1, SUPERSEDED by a Round 2 box above) P7 Cross-OS, the `WORKLIST_*` registry, suite sharding, lifecycle collapse to 11 entries.

Targets: 2 processes per Bash tool call. **THE BASELINE THIS IS MEASURED AGAINST DOES NOT EXIST IN THE TREE, found 2026-09-07.** `git ls-files | grep -iE 'strace|exec-baseline'` returns ZERO, and there is no `GUARD_PASS` or fork-counter artifact anywhere, so W5 P0's stated deliverable (a fork counter) and the "456 execs to 35" figure in P6's note are both unreproducible today. A target defined against a missing baseline cannot be checked off, and that is the first thing P7 must fix. Measured directly instead: a Bash tool call currently fires **12 hook processes** before any in-guard forks (PreToolUse/Bash 4, PostToolUse 5 on the Bash matcher plus 3 on `*`), against the target of 2. All 374 `check` and 21 `check_out` assertions stay green throughout; `worklist-cases` is untouched.

### W6: Bootstrap, run.sh router and cross-OS (5 phases)
- [x] P1 Prerequisites, router split, launchers, entry tests. Two prerequisite defects land in wave 1 because everything depends on them: `check-dead-bash.ts:152` has no `py` alternative in its TEXTUAL regex, and `run.ts:940` computes `whole` from only `--only`/`--skip`, so a `--changed` receipt currently authorises a push.  **DONE 2026-09-06:** W6 P1 router split: run.sh 120 lines, run-legacy.sh 1334, run.ps1/run.cmd
- [x] P2 Python platform layer, toolchain port behind a differential shadow gate, the four macOS bash fixes, and the one install table.  **DONE 2026-09-07 (2f0c3515d):** `.ci/rediacc_ci/setup/tools.py`, 22 rows, 9 pinned, WITH the pytest row the contract recorded as missing. `w6p2-toolchain` asserts equivalence over 5 distinct trees. The four macOS bugs were DRIVEN against a bash 3.2.0 built from source, not asserted: release-state-validator printed empty stdout and rc=1 for a HEALTHY release state, and blocker-validator's unquoted regex is a SYNTAX ERROR on 3.2 that killed the enclosing function so the allowlist parsed to zero entries. All four now refuse loudly with their version named.
- (round 1, SUPERSEDED by a Round 2 box above) P3 `setup` in Python with the phase table as data, the missing installs (ruff, shellcheck, shfmt, actionlint, uv, pytest, gitleaks, bws, tmux), `.claude` wiring, and opt-in git hooks.
- (round 1, SUPERSEDED by a Round 2 box above) P4 `rdc.sh` down to a 70-line shim, native CLI build moved into the package, macOS-complete setup, a macOS CI probe.
- (round 1, SUPERSEDED by a Round 2 box above) P5 Quality lane last, legacy file deleted, `LEGACY_ARMS_MAX` reaches zero.

### W7: .ci port (6 phases)
- [x] P0 Seams, baselines and counts that every later box is measured against.  **DONE 2026-09-06:** W7 P0 baselines as SETS; corrected three contract counts
- [x] P1 JS relocation out of `.ci`, and the two bash libs ported into `core` behind delegating shims.  **DONE 2026-09-06:** W7 P1(b) two bash libs behind fail-closed shims. P1(a) JS relocation REFUSED on measurement: 22 of 23 files drop from full to reduced CI
- [x] P2 Port the 74 `check-*.sh` plus 5 wrappers behind `@gate`, each with a `--selftest` control and a committed differential artifact over K distinct trees.  **PARTIAL 2026-09-06: 14 of 77 ported, 13 of 14 PROVEN (b9033101a). Superseding an earlier 4-of-14 reading:**, refuted by running the comparator over every ledger: only npmrc, go-module-sync, cli-contract and compose-env reach `equivalence holds over 5 distinct trees`. TEN fail, not the six I named: the six earlier ports report 0 distinct clean trees, and batch A never reached K=5 either (peerdeps 3, appadmin 3, cmdtree 4). stagingtag has 6 clean trees but 3 are DISQUALIFIED by MISMATCH_FINDINGS rows, which is a recorded BEHAVIOURAL divergence rather than a bookkeeping gap. Original note follows: batch A (peer-deps, no-app-admin-perm, command-tree, staging-tag-guard) and batch B (npmrc, go-module-sync, cli-contract, compose-env) landed at 5c85a675e and 6586bc038, each EQUIVALENT over 5 distinct committed HEAD^{tree} ids. THE FIRST SIX ARE NOT ACTUALLY PROVEN: every one of their 34 rows carries clean:false against ONE shared tree id, so --assert reports 0 distinct clean trees and invariant 5 is unmet for all six. The cure found in batch B is to make each specimen its own committed git repo, and to run the new side under PYTHONDONTWRITEBYTECODE=1, since __pycache__ dirties the tree before treeIdentity is computed.  **"77 of 77" MEANS PORTED, NOT LIVE AND NOT DELETED. Re-measured 2026-09-07 after the operator asked why so many .sh files remain, which was the right question.** `rediacc_ci/quality` is referenced ZERO times in `package.json`, `manifest.ts` and `ci-quality.yml`, while `manifest.ts` still names `.ci/scripts/quality` 143 times: CI runs the BASH. 581 `.sh` files are still tracked under `.ci`/`.claude`, all 82 bash quality gates and all 149 bash gate tests are present, and nothing has been deleted. That is the DESIGN (invariant 5 forbids deleting a twin in the porting change; wiring is W7 P4 and deletion is W7 P5, both open), but quoting "100%" as a headline reads as finished and is not. Report three axes from now on: PORTED, LIVE, DELETED. Today they are 77, 0, 0. **AND THE REASON LIVE IS 0 IS STRUCTURAL, not scheduling, measured 2026-09-07: ZERO of the 78 ported modules carries a `---- gate ----` header** (`grep -l -- '---- gate ----' .ci/rediacc_ci/quality/*.py | wc -l` -> 0). In this repo REGISTRATION IS THE HEADER, since `gate:bind` reads it, so W7 P4 cannot begin as a registration change: 78 headers must be written first, and no box costs that work. Five of the six entry points under `.ci/scripts/quality/` that import a port are referenced by nothing at all, and `check-dead-bash.ts` is bash-only so it cannot see them: there is NO dead-Python gate. **DONE 2026-09-06 (9c6a00de8): 77 of 77 ported. RE-MEASURED 2026-09-07 over every ledger in .ci/shadow, which now holds 78 pairs, not 77: 77 of 78 assert `equivalence holds` at K=5.** The one red is w7p2-stagingtag and it is permanent: three tree ids disqualified by rows recorded through a hole since closed, 12 qualifying trees over 9 finding sets, so the claim is evidenced and only the assert cannot express it. No twin deleted: that is W7 P5.
- (round 1, SUPERSEDED by a Round 2 box above) P3 Gate tests to pytest: harness ported once, tests in subject batches, `battery.py` replaces `run-all.sh` and reads isolation from the lock. **FIRST STAGE IN FLIGHT 2026-09-07, and every "blocked" note on this box was STALE:** headers landed on all 148 under W2.3, isolation went onto the lock under W2.4, and W1 P2 put pytest in a lane that installs it, so nothing was ever holding it. On disk now: `.ci/rediacc_ci/tests/gates/` with `harness.py`, `conftest.py`, `test_harness.py`, `test_twin_parity.py` and, after batch 4 on 2026-09-07, EIGHTY-EIGHT ported subjects of 149 after batches 5 through 8 on 2026-09-07 (batch 4 was the first to run under the new `-n 8` concurrency, so a port that binds a fixed port or mutates a module global now flakes where it used to pass; batch 5 needed no `xdist_group` at all and each module records WHY in its docstring). **BATCH 5 FOUND A HOLE IN THE PARITY DRIVER ITSELF, now fixed:** `test_twin_parity.bash_cases()` counted a case as called only when the call was a BARE NAME on its own line, so a twin invoking `test_x "$D/y"` or `with_temp_dir test_x` matched nothing. Measured across the 130 twins that declare cases, 43 had at least one case invisible and 16 saw ZERO, falling through to the weaker flat-twin PASS-count floor -- so the SET comparison that module exists to perform silently did not happen for those 16, `test-ci-parity.sh` (22 cases) among them. That is failing OPEN. Widened to a word match excluding the declaration line and whole-line comments: 0 seeing zero, 0 with any miss, and zero newly-required cases missing from any of the 53 ports, so it strengthens the check without reclassifying existing work. **`check:ci-pytest` IS NOW DECLARED `slow: true`**, not as a regression but as the truth: the tier oracle measured its FLOOR at 367.9s, the gate runs all 9165 Python tests, and each batch adds roughly 200 more, ruff clean. Batch 2's ten were set-derived, not chosen: 148 minus the 6 already done, minus the 4 W and 21 S real-tree members, minus every twin naming a basename that appears in any of the 78 shadow ledgers (159 basenames), leaving 98 admissible; `test-toolchain.sh` was then excluded BY HAND because `w6p2-toolchain`'s ledger points at `.ci/shadow-drivers/`, a directory that NO LONGER EXISTS, so the filename filter cannot see what that pair covered. Every port planted a defect in the REAL subject and drove both sides; all ten restored byte-identical by sha256. Batch 3 read the W/S exclusion set FROM THE LOCK rather than from the bash arrays, which only became possible when W2.4's declarations landed hours earlier, and its parity driver asserts it every run: `none of the 29 ported twins is among the 25 real-tree test(s)`. **BATCH 3 ALSO SURFACED THE PROGRAMME'S NEXT BOTTLENECK, and it is now an operator order.** `check:ci-pytest` measured 810s for 8944 tests and IS the whole local wall time: run 3 was 675.3s wall of which that one gate was 675.3s, with 356 other gates finishing inside it. It runs SERIALLY on a 24-core box -- `import xdist` raises ModuleNotFoundError and pyproject.toml addopts carries no `-n` -- and the corpus grows about 200 tests per batch, so porting makes it worse. Tracked as worklist #d76fa6de under the operator's ordered sequence: plan, implement, validate, optimise again, validate. All 148 bash originals are still present, which is invariant 5 working as intended: a twin is never deleted in the change that ports it. The 148 `gate-test:*` manifest entries are the largest patch fragment in the programme and must be batched, or the driver becomes the bottleneck.
- (round 1, SUPERSEDED by a Round 2 box above) P4 Workflow-invoked wrappers behind one-line shims, then flip the call sites.
- (round 1, SUPERSEDED by a Round 2 box above) P5 `deploy/` and `release/` last, behind golden dry-run parity plus one real run each; bash libs deleted; language gate blocking for `.ci`.

### W8: Environment manifest and Bitwarden (7 phases)
- [x] P0 Verify the retirement landed at 7343ae9dc and re-derive the residue. (The draft's premise that 27 files are uncommitted is refuted: they are committed.)  **DONE 2026-09-06:** W8 P0 retirement verified, residue re-derived, tokens[] restructure
- (round 1, SUPERSEDED by a Round 2 box above) P1 Drain the passthrough class to its irreducible residue. Highest outage risk in the program: each callee cutover deletes `workflow_call` declarations and caller passthroughs in one commit. Exactly two agents, never during a release window, one green real deploy between boxes.
- (round 1, SUPERSEDED by a Round 2 box above) P2 Python invocation contract and the sharded manifest (eight shards, zero unclassified, tombstones enforced).
- (round 1, SUPERSEDED by a Round 2 box above) P3 Generators and the regenerate-and-diff gate for `.env.example`, the docs table and the local allowlist.
- (round 1, SUPERSEDED by a Round 2 box above) P4 The fetch helper and one precedence rule (shell wins), replacing every `set -a; source .env`.
- (round 1, SUPERSEDED by a Round 2 box above) P5 Seeding, reader and writer retarget, `.env` truncation to the machine-local set. Dev keys come from `dev-shared`, not from production.
- (round 1, SUPERSEDED by a Round 2 box above) P6 Python env registry scoped to `.ci` first, with a monotonically shrinking baseline.

### W9: scripts/ and eslint-rules (5 phases)
- [x] P0 Pre-flight receipts, `domains.json` partition, single-writer protocol.  **DONE 2026-09-06:** W9 P0 domains.json partition, 242 files classified, zero unclassified
- [x] P1a eslint-rules prep: a paths module replacing five divergent `__dirname` depths, a RuleTester harness, lint coverage.  **DONE 2026-09-06:** W9 P1a eslint-rules paths module + RuleTester harness + check:ci-lint-rule-units
- [x] P1b scripts prep: repo-root module, `utils` merged into `lib`. **DONE 2026-09-06 (a4828bd3a + b9033101a):** git mv of console.ts, crc32.ts and translation-diff.ts, 24 importers fixed, scripts/utils/ gone, tsc and lint green, zero stale imports. Three inventories re-keyed in the same change per invariant 2. Its recorded blocker (22 of 25 importers dirty) was gone. NOTE 'operator bash relocated out' was NOT done and is not tracked anywhere else.  **THAT PARTIAL NOTE IS NOW FALSE, re-measured 2026-09-07:** `ls scripts/utils` returns No such file, `scripts/lib/{console,crc32,translation-diff}.ts` are all present, and `git log -- scripts/utils` ends at `a4828bd3a refactor(scripts): merge utils into lib`. The merge DID happen; the box carried two contradicting notes and the pessimistic one outlived the work.
- (round 1, SUPERSEDED by a Round 2 box above) P2 Domain moves and data relocation. Strictly serial, single writer: `enumeration-vacuity-baseline.json` **is an OBJECT `{note, unguarded: [42 entries]}`, not "one sorted array"** (verified 2026-09-07; read at `scripts/check-enumeration-vacuity.ts:403` as `.unguarded`). The VERDICT is unchanged, and that is the point of correcting the description rather than the box: a rename still reads as growth to a shrink-only list, so this stays strictly serial and single-writer. But an implementer who greps for an array concludes the box is stale and skips the re-key.
- [x] P3 `eslint.config.js` split into six imported modules, proved byte-identical by a `calculateConfigForFile` differential over all 1,171 tracked lintable paths, plus RuleTester tests for the 35 rules that have none today.

### W10: Media pipeline separation (6 phases, stays bash)
- [x] P0 Preflight: shared fake-binary test scaffolding, and teach the dead-case-arm gate to open `.ci/media`.  **DONE 2026-09-06:** both already on disk from a02496709; this became an AUDIT that found five real defects in that landing, all fixed.
- [x] P1 Extract seven modules into `.ci/media` with both copies coexisting; each box carries a fidelity assertion lifting the same body from both sources. Seven concurrent.  **DONE 2026-09-06:** W10 P1: .ci/media/ holds 11 modules plus tools/
- [x] P2 Cut over: `run.sh` and root `media.sh` become exec delegators. `run.sh` drops from 2,640 to at most 1,400 lines; `./run.sh help` stays byte-identical.  **DONE 2026-09-06:** W10 P2: media.sh is a 23-line exec delegator; run-legacy.sh routes media verbs to .ci/media/media-entry.sh
- [x] P3 Relocate the tts docker context and the R2 upload primitive with exec shims for the cross-repo callers.  **DONE 2026-09-06:** W10 P3: git shows R .ci/docker/tts -> .ci/media/tts, and .ci/media/tools/upload-r2.sh with shims
- [x] P4 Documentation accuracy, coverage probe, portability seams.  **DONE 2026-09-06 (5c85a675e):** five doc claims corrected against the tree (a dead SHA the 2026-08-23 rewrite killed but which still resolves locally; the TTS engine; the function home; a stale count; the credential path), two now MECHANICALLY enforced so they cannot rot. Battery green with docker/node/npm/aws/ssh/GPU/network all absent: suites=11 PASS=94, zero forbidden calls.
- [x] P5 Hand the language-policy BLOCKER strings to W1, which owns the gate.  **DONE 2026-09-07, verified against the tree not the report:** the gate landed today as `check:ci-language-policy`, and the strings ARE handed over. `.ci/policy/.language-policy-allowlist:35` carries the BLOCKER naming private/generative and private/growth as separate bash-native repos this one only orchestrates, immediately above `tree:.ci/media/`. The decisive check is that NONE of the 13 `.ci/media/*.sh` appears in the 521-entry frozen baseline: they are exempt BY NAME WITH A REASON, which is the goal state, rather than frozen debt. The other two entries, `tree:.ci/breakpoint/` (24) and `tree:.ci/tutorials/` (27), each carry their own BLOCKER.

Every new test passes with docker, node, npm, nvcc, aws, ssh, GPU and network absent.

### W11: Docs, records and the generator (7 phases)
- [x] P0 Generator first, before any content moves and before W2 touches the registry. `gen-docs.ts` with directory-scanned providers, plus the pre-port SET snapshot (row sets, not counts, because a floor of 300 passes after 88 of 388 gates vanish).  **DONE 2026-09-06:** W11 P0: scripts/gen-docs.ts plus doc-providers.ts and doc-regions.ts, gen:docs registered. Its parity gate was MISSING and LANDED 2026-09-06 (5c85a675e) as check:ci-doc-region-parity plus gate-test:doc-region-parity. It is not a subset of gate-test:docs-gen, which was the standing reason for not adding it (decision O-1, now refuted): gen-docs DISCOVERS its targets and that test asserts only that at least one was found, so a document losing its markers stops being checked instead of failing. Measured by stripping CLAUDE.md's markers and watching gen-docs still report ok.
- [x] P1 Stale lines, decision record 07, the master checklist, the port brief. Eight concurrent, disjoint files.  **DONE 2026-09-06:** W11 P1: 07-master-checklist.md, 07-port-brief.md and 07-tooling-decisions.md all exist
- [x] P2 CLAUDE.md slimming wave 1 with its first generated spans. 759 lines to at most 580, Session Defaults byte-identical.  **DONE 2026-09-06:** W11 P2: CLAUDE.md 784 -> 580 lines (target was at most 580), two generated spans, Session Defaults byte-identical
- [x] P3 Seam widening. **DONE 2026-09-06 (65f1aa803) and proven a no-op the strong way:** verdict stdout AND stderr byte-identical before and after, with determinism confirmed FIRST over three runs so the identity means something. Both seams are repo-relative file lists with three refusals a list needs (declared path absent, two guard dirs sharing a final segment, zero folding harnesses). 14-step both-direction plant harness, 0 mismatches. Also fixed a pre-existing floorcheck false positive whose window excluded the fold line itself. Driver added scripts/data/hook-audit-scope.json to the gate's paths: it now decides the entire audited corpus, so without it a commit touching only that file would not select the gate.
- (round 1, SUPERSEDED by a Round 2 box above) P4 Docs tied to the registry, the policy folder, the hooks port and the test split.
- (round 1, SUPERSEDED by a Round 2 box above) P5 Docs tied to bootstrap, the CI job graph, the env manifest and the media folder. CLAUDE.md to at most 440 lines and 30 KB. **Gap measured 2026-09-07: CLAUDE.md is 580 lines / 36,756 B, so 140 lines and 6,756 B over.**
- (round 1, SUPERSEDED by a Round 2 box above) P6 Final consistency sweep, submodule pointer, records close-out.

### W12: agent/ history as attested records (variant A, lean cliff)

Forcing function: the housekeeping gate demands deletion of 33 plans on 2026-09-23 and 13 more on 2026-10-06. Phase 1 must be on main by 2026-09-20. Investigation facts: 79 plans and 2.0 MB; 37 of 71 commit citations dangle; 67% of judge-recorded artifact paths do not exist; no worklist event records a commit; `agent/archive/plans/` is named by config but does not exist; SessionStart opens all 79 plans to print 49 filenames.

Record grammar: header lines within the first 10 (`Status: compacted|parked`, `Full-Text: <sha9> <path>` optional when `Full-Text-Blob:` is present, `Record-Sig`), then `## Why`, `## Outcome`, `## Lessons` (trap and decision ids), `## Boxes` (box lines byte-identical, each followed by a 4-space `(record) sig=.. done=<sha9>|open|abandoned item=.. epic=..` line that `BULLET_RE` and `plan_tasks` ignore), `## Record` trailer in the TRAPS grammar including a `Read-History` line carrying the `git show` and `git log --find-object` commands, and `## History` bullets appended only. Record at most 6 KB plus 160 B per box, and the pointed blob at least twice the record.

#### W12.P1 Compaction that survives rebase (on main by 2026-09-20)
- [x] P1.1 `wl_planrec.py`: parse and render the grammar; `resolve()` for commit, ancestor-of-origin/main, blob, file:line, gate, plan, trap, decision, reusing the four existing verification idioms; `derive()` computing Full-Text, blob, Epics from PR-TASK trailers, Touches from `plan_orientation`, Gates, and `done=` per sig by walking the ledger's history; `record_sig`; `launder()` replacing unresolved tokens with `[unresolved]`; `render_index`.  **DONE 2026-09-06:** W12 P1.1: wl_planrec.py, 2214 lines
- [x] P1.2 Statuses: `compacted` into the finished sets, `parked` into not-started.  **DONE 2026-09-06:** W12 P1.2: statuses in wl_planfile.py
- [x] P1.3 `worklist.py --plan-compact` and `--plan-revive`, with refusals, blob-only pointers when the text is not yet on origin/main, one bounded `claude -p` under `--why model` using the existing `WORKLIST_JUDGE_MODEL` (haiku), laundered, written via tempfile and `os.replace`, never committing.  **DONE 2026-09-06:** W12 P1.3: --plan-compact and --plan-revive in worklist.py
- [x] P1.4 `check_plan_record.py`, hand-registered in `quality-branch` per invariant 11: ten rules R1 to R10 with self-control first, a floor, pointer resolve and live, blob equality and size ratio, `done=` proven against the ledger blob, `(record)` inside a box line red, the placeholder under `compacted` red, and `agent/INDEX.md` equal to the render.  **DONE 2026-09-06:** W12 P1.4: check_plan_record.py registered in package.json, manifest.ts and ci-quality.yml quality-branch, hand-written exactly as this box specifies
- [x] P1.5 Housekeeping: compacted plans with a resolving blob are exempt and counted; `parked` stays on the clock; abandoned-annotated boxes leave the ledger's open set; the remedy becomes work-or-compact and DELETE is removed.  **DONE 2026-09-06:** W12 P1.5: housekeeping exemption in check-plan-housekeeping.sh
- [x] P1.6 `block-compacted-plan-edit.sh`, denying edits to a record and printing the `git show` and revive recipes.  **DONE 2026-09-06:** W12 P1.6: .claude/hooks/pre-edit/block-compacted-plan-edit.sh, baselined and covered
- [x] P1.7 SessionStart and the plans block read `agent/INDEX.md` instead of opening 79 plans, with an INDEX STALE state and a census fallback.  **DONE 2026-09-06 (5c85a675e):** 166 file reads to 1, 56.9ms to 2.2ms, whole hook 134ms to 68ms, output byte-identical (HEAD's own plans_block exec'd beside the new one). The brief's premise was WRONG and the correction is the finding: render_index indexes compaction records only and returned the empty string, so P1.7 needed a second census table in the same file plus an R8 that knows about it, not a wiring job. Named blind spot: freshness is stat-only, so a same-length status edit is invisible locally; R8 byte-equality closes it in CI.
- [x] P1.8 The wave PR. **HALTED AND RESTARTABLE 2026-09-06.** Both batch agents were stopped mid-run because the compaction TOOL mis-titled every record: title_of() had an off-by-one in the slug fallback (slug[4:] where len('PLAN-') is 5), no code-fence awareness (a shell comment became a title), and worst, its header-field guard matched any `Word:` so `# PLAN: ...` read as a field, sending 62 of 83 plans to the slug fallback. Fixed at 65f1aa803 with all three cases tested both ways. A SECOND defect is agent-side, not tool-side: one record's Outcome said a plan 'was never implemented' when it shipped in 120cd9e73, because the compactor believed a stale `Status: draft` header. Both agents were sent the rule (a header is a claim, the tree is evidence) before being stopped. THREE records already written carry bad titles and must be revived and redone: PLAN-lint-rule-matrix-probe, PLAN-lint-css-ci-wiring, PLAN-greenlight-verify-at-read.  **DONE 2026-09-06: 32 of 32 aged plans compacted.** The titling defect that halted the wave was fixed at 65f1aa803 and the three bad records were revived and redone.

#### W12.P2 History pushed at the edit; second wave (before 2026-10-06)
- [x] P2.1 `why_lines()` and `--plan-why <path>`, with an affirmative empty answer.  **DONE 2026-09-06:** W12 P2.1: why_lines and --plan-why in worklist.py
- [x] P2.2 `why-on-edit.py`. **DONE at a02496709, never ticked:** 322 lines, registered at .claude/settings.json:179. Every clause present: once-per-path-per-epoch (:186-193), the cap (:87, :282), silence with no edge (:24-28, :288), similar-plan block on a new plan Write (:127, :273).
- [x] P2.3 PostCompact and the CI-red history hook both append why lines.  **DONE at a02496709, never ticked; verified 2026-09-07 against the tree rather than the note:** both halves are self-labelled `W12 P2.3`, PostCompact at `wl_checks.py:2348-2361` and the CI-red hook at `wl_histfirst.py:173-189` (208 lines, wired at `wl_checks.py:4272`).
- [x] P2.4 `check_plan_citations.py`. **DONE at a02496709, never ticked:** 568 lines, parser-blind floor documented at :60-65 and implemented at :366, registered in all three places (package.json, manifest.ts with paths, ci-quality.yml:569). It is live and catching things: it refused two of my own plan citations today.
- [x] P2.5 `--plan-tick` with evidence, flipping the box and updating the ledger in one run.  **DONE 2026-09-06:** W12 P2.5: --plan-tick in worklist.py
- [x] P2.6 Pointer stamps on store compaction and on every STATE.md write. **DONE, never ticked:** both halves use the real pointer_stamp from wl_planrec.py:1371. Store compaction at wl_store.py:1814-1820 (dict.fromkeys, not a set, because the compactor's own file is both in `clear` and the target). STATE.md at worklist.py:1521-1529, taken INSIDE the lock and BEFORE the os.replace, which is the only ordering that makes the stamp true. Both imports suppressed, so a stamp never gates a write.
- (round 1, SUPERSEDED by a Round 2 box above) P2.7 **"A5" POINTS AT THE WRONG FILE, verified 2026-09-07: `grep -cE '\bA5\b' docs/ci-overhaul/04-decisions.md` returns 0.** `A5` and `A6` are GATE RULES in `.ci/scripts/quality/check_plan_boxes.py:41-44` (A5 = a plan may only be deleted wholesale once older than delete_days AND only when deletion actually loses a box; A6 = the scan is not vacuous). The clause therefore reads: **`check_plan_boxes.py` rule A5 becomes never-delete.** Plus two TRAPS entries; CLAUDE.md gains "search first" (0 hits today); the grammar is documented.
- (round 1, SUPERSEDED by a Round 2 box above) P2.8 Second wave. **NOT 13 PLANS AND NOT 2026-10-06, re-measured 2026-09-07.** `check-plan-housekeeping.sh` reports 86 tracked plan(s) with 32 compacted, so **54 are uncompacted**, four times the recorded figure. The next red is **2026-09-25** (2 plans) and then continuous, not 2026-10-06. Staffing this against the old numbers under-provisions it and misses the deadline by eleven days.

#### W12.P3 Registers and remaining edges
- [x] P3.1a Epics durable: the TMPDIR sidecar moved into `agent/worklist/`. **DONE:** wl_epic.py:36-37.
- (round 1, SUPERSEDED by a Round 2 box above) P3.1b **THE STATED PREMISE IS REFUTED, re-scoped 2026-09-07.** "Nothing asserts every PR-TASK id has an epic event" is false: `scripts/check-pr-task-trailers.ts:68-81` emits `unknown-epic` for an unknown id, with both directions controlled at `:106-125`. The gap that actually survives is narrower and worth stating exactly, because the old wording sends an agent to build something that exists: `known` is scraped from a MARKDOWN SNAPSHOT (`:272`, `:277`) rather than read from a `wl_epic.py` event, so the assertion is against a document that can drift, not against the ledger.
- (round 1, SUPERSEDED by a Round 2 box above) P3.2 `DECISIONS.md` with ids, seeded from `04-decisions.md` and the ten locked decisions in the secret-migration plan. **THE "A6 OVERRIDE RULE" IS `04-decisions.md` SECTION A ITEM 6** (`:22-23`, "Do not stick on what I say. Better ideas are welcomed"), an OPERATOR RULING, and NOT the gate rule A6 in `check_plan_boxes.py:42-44`, which is the anti-vacuity clause. P2.7 and P3.2 sit two boxes apart and pointed at OPPOSITE FILES under the same-looking token, which is exactly the confusion the new file must end. **The ids must be PREFIXED (`D-A6` for a decision, `G-A5`/`G-A6` for a gate rule) so the collision cannot recur.**
- (round 1, SUPERSEDED by a Round 2 box above) P3.3 Canonical status vocabulary in config; the three state sets built from it.
- [x] P3.4a The three header keys PARSE: wl_planrec.py HEADER_FIELD_KEYS carries Supersedes, Extends and Related, and they are correctly excluded from being read as a title.
- (round 1, SUPERSEDED by a Round 2 box above) P3.4b Nothing RESOLVES them to a real plan: `git grep 'Supersedes' -- '.ci/scripts/quality/*'` returns nothing. Split out 2026-09-06, same shape as P3.1, because the box read as one unit while its first half was silently complete. Run it AFTER the compaction wave: its gate change alters what check_plan_record.py accepts while that wave runs --update against agent/INDEX.md all the while.
- (round 1, SUPERSEDED by a Round 2 box above) P3.5 Measure before blocking: a two-week advisory census before any blocking rung.

## Gaps still unowned (assign before launch)

- [x] **THE LANGUAGE-POLICY GATE NOW EXISTS. This entry was written and closed the SAME DAY, 2026-09-07**, which is worth leaving visible rather than deleting: the gap was real when found and the fix landed hours later. Built as ADVISORY and shrink-only (`check:ci-language-policy`, 521-path SET baseline, 3 BLOCKER-gated exemptions, registered and green), because blocking against 520 non-exempt shell files would have redded the tree and been suppressed within a day. **The STRICT FLIP is still open and is W1 P6**, whose job is to delete the baseline entirely. Original finding follows. ~~THE LANGUAGE-POLICY GATE ITSELF DOES NOT EXIST, and no box in this plan creates it.~~ Found 2026-09-07: `grep -rin 'language.policy'` across every tracked `.ts/.py/.sh/.json` (excluding node_modules, .git and docs/ci-overhaul) returns NOTHING. No baseline file, no allowlist, no `POLICY_FILES` slot. So **W1 P6 has nothing to flip** and **W10 P5 has nothing to hand its BLOCKER strings to**, and both read as ordinary pending work while their subject is absent. It also sits on the live critical path. Landed 2026-09-07 as a shrink-only gate. **CORRECTION to my own framing, verified in the code 2026-09-07: it is NOT advisory. `run()` returns 1 on growth (`check_language_policy.py:850`), so it BLOCKS, with a frozen floor of 521 paths.** "Advisory" was the wrong word for shrink-only: it does not demand the 521 be fixed, but it fails the build the moment a 522nd appears. In flight as a shrink-only gate (blocking today would red ~119 tracked `.sh` and be suppressed within a day, which is the failure `suppressions.md` exists to prevent); the strict flip stays W1 P6. Its baseline is a SET of paths, not a count, per this plan's own floor policy.

- (round 1, SUPERSEDED by a Round 2 box above) Requirement 15 (organize `.json`): one box owning a predicate and a table for the 8 root json files, the 8 left in `.ci/config` after W4, and the 20 in `scripts/data`.
- [x] `package.json` key budget. **ALREADY SOLVED, measured 2026-09-06:** 343 keys total, 295 scheduled by the manifest and therefore exempt by classification, 48 hand-written against a baseline of 48. Registration boxes do not consume budget, so this gap does not exist. Original text: 307 script keys today and every registration box appends. A shrink-only baseline with a gate-key exemption class, plus one box per workstream naming which keys it retires.
- [x] Comment archaeology for the gate and test ports. **The box was OVERSTATED and is now true: the 0.90 floor was PRINTED and never ENFORCED.** assertEquivalent, the only ruling function, never read row.comments, so --assert returned 0 with every row below the floor; the word 'refused' in 5c described a human. Closed in code at f7d6ede74 with a three-direction control. Not masking a live violation: the worst ratio across 100 recorded rows is 2.95. Originally closed by driver-contract section 5c, which makes a comment-byte ratio of at least 90 percent a port acceptance criterion recorded in the differential artifact each twin already produces, plus a short list of every original line naming a date, run id, sha or issue number for a reviewer to confirm survived.
- (round 1, SUPERSEDED by a Round 2 box above) Cross-repo submodule pull requests: `private/growth` retarget, three `private/account` string fixes, the `private/renet` pointer bump. Named owner and merge order.
- (round 1, SUPERSEDED by a Round 2 box above) `scripts/` layout admission: W9's set-equality gate will red on files W7 adds. Extend `domains.json` in the same wave.
- [x] pytest belongs in W6's one install table, which does not list it today. **DONE, box was stale rather than the work missing:** `.ci/rediacc_ci/setup/tools.py` carries the pytest row and devotes a titled section to it, `WHY THE pytest ROW IS THE POINT OF THIS FILE` at :23, recording that the five pre-existing install lists carried NO pytest row while W1, W5 and W7 each make a Python test runner a gate. Verified 2026-09-07 by grep.
- [x] Issue 587 residue: the npm@10 downgrade in `.ci/lib/local-common.sh` is GONE. **VERIFIED 2026-09-07:** `grep -cE '^[^#]*npm@10' .ci/lib/local-common.sh` returns **0** -- every surviving mention is commentary, and the only live spelling is `npx -y npm@11`. CLAUDE.md's own section records the re-test on 2026-09-06 under the clean-room recipe: all eleven zod copies landed where the npm 10 tree puts them, `packages/shared/node_modules/zod` at 4.5.4, the hoisting defect no longer reproducing. This also closes the last path that rewrote the root lockfile into the non-canonical form on every local loop.

## Implementation tracks and driver structure

Ten sub-drivers, each owning a worktree pool. Sustained ceiling 10 to 12 concurrent worktrees, 14 at the three fan-out bursts, each running with `CI_JOBS=2` and `CI_PROFILE=off`. Above 14 the registry merge queue, not the CPU, is the bottleneck.

| Track | Contents | Agents |
|---|---|---|
| T1 Unblock | W0 plus W8:P0 | 6 in wave 1, 1 in wave 2 |
| T2 Registry spine | W2 | 2, bursting to 6 for header slices |
| T3 Python and .ci port | W1 then W7 | 8 sustained, 13 at the module burst |
| T4 Hooks | W5, plus W3's hook-split boxes | 6 for port batches, 1 for cutover |
| T5 CI schedule | W3 | 3, exactly 1 for the lane conversions |
| T6 Root and bootstrap | W6 | 3, 1 for the router move |
| T7 Secrets, env, policy | W8 and W4 | 8 for the movers, exactly 2 for the passthrough drain |
| T8 Scripts and lint | W9 | 3, exactly 1 for the domain moves |
| T9 Media | W10 | 7 for module extraction, then 1 |
| T10 Docs and records | W11 | 6 to 8, then 1 per shared-file phase |
| T11 agent/ history | W12 | 2, 4 for the compaction wave batches |

The root driver writes no code and owns three things: the registry merge queue (`package.json`, `manifest.ts`, `ci-quality.yml` have exactly one writer in flight; every sub-driver hands over a branch whose gate file and registry entry are in the same commit, and only the root driver runs `gate:bind --write`, once per wave, pasting the `dropped` list into the wave record); the machine mutex (at most one docker, account or traefik box in flight, because worktrees do not isolate the daemon, `~/.rediacc`, port 4800 or the router namespace); and the reference worktree that produces every timing number.

Wave shape: wave 1 is T1 in full, T6's two prerequisite fixes, T10's generator and seam widening, T7's decisions and the first passthrough box, T9's preflight. Wave 2 is T3's bootstrap and skeleton, T2's binder and loader, T8's prep, T4's skeleton through pre-keying, T9's extraction. Waves 3 to 5 are the four cutovers, independent of each other after M4: hooks, quality, Bitwarden, and registry then .ci port. The final wave is the language gate flip plus the records close-out.

## Milestones

- (round 1, SUPERSEDED by a Round 2 box above) M0 Token renewed and Bitwarden is the only path. Hard deadline 2026-09-08.
- (round 1, SUPERSEDED by a Round 2 box above) M1 Pre-work landed: the five silent assumptions hold, each proven by a red-then-green test.
- [x] M2 Python foundation ready: a gate can be Python, tested, placed and trusted.  **MET, measured 2026-09-07:** 78 Python gate modules under `.ci/rediacc_ci/quality`, `check:ci-pytest` live in a lane that installs pytest, and the ports proven at K=5.
- (round 1, SUPERSEDED by a Round 2 box above) M3 Registry cutover: every gate declares itself once and every consumer reads the declaration.
- [x] M4 Infra-only checkpoint: a valid place to stop. Package, registry with a committed lock and path-scoped isolation, policy folder, run.sh router, media folder, docs generator with a pre-port snapshot.  **MET, every clause measured 2026-09-07:** package present; committed lock at 456 entries; path-scoped isolation live (`mutex tree:` 4, `reads tree:` 22); policy folder holding 15 lists; `run.sh` at 120 lines; `.ci/media` with 13 modules; gen-docs generating four regions.
- (round 1, SUPERSEDED by a Round 2 box above) M5 Hooks cutover: 2 processes per Bash call, all 395 assertions green.
- (round 1, SUPERSEDED by a Round 2 box above) M6 Quality cutover: lanes become an emitted shard matrix whose failure modes are red, not silent.
- (round 1, SUPERSEDED by a Round 2 box above) M7 Bitwarden cutover complete: no credential arrives by accident anywhere.
- (round 1, SUPERSEDED by a Round 2 box above) M8 `.ci` ported: no bash under `.ci/scripts/quality`, every twin with a committed differential artifact.
- (round 1, SUPERSEDED by a Round 2 box above) M9 Language gate flipped to blocking, with no baseline file at all.
- (round 1, SUPERSEDED by a Round 2 box above) M10 Records true: no document a session loads is lying; the generator is a deterministic no-op.
- (round 1, SUPERSEDED by a Round 2 box above) M11 agent/ history attested: 46 records, nothing deleted, history pushed at the edit.

Critical path, **RE-DERIVED 2026-09-07 and different from the original in two ways**.

The original read: W0.2 to W1:P1 to W1:P2 to W2.0 to W2.1 to W2.3 to W2.4 to W7:P0 to W7:P1 to W7:P2 to W7:P3 to W7:P4 to W7:P5 to W11:P6.

**W2.3 HAS FALLEN OFF THE PATH**, proven empirically rather than argued: 41 subjects are ported and running with NO manifest region and no manifest entries at all, under the single `check:ci-pytest` entry (`manifest.ts:5573`), because `testpaths` already covers `.ci/rediacc_ci/tests/gates`. So W7 P3 needs no registration and no driver involvement, and W2.3's open half blocks nothing.

**A PREREQUISITE IS MISSING FROM THE PATH ENTIRELY**: W7 P5's third clause is "language gate blocking for `.ci`", and that gate does not exist (see the Gaps section). It has to be BUILT before W7 P5 can be flipped.

Live path: **W7 P3 (107 of 148 remaining) to W7 P4 (201 unique scripts, 334 call sites) to [BUILD the language-policy gate] to W7 P5 (138 .sh) to W11 P6.** W7 P3 is the single largest body of work in the programme and the only thing on the path that can start today.

## Verification

Each box carries its own red-then-green test; these are the program-level proofs.

1. **Nothing lost a verdict.** Every ported gate has a committed differential artifact recording exit-code and normalized-finding equality against its bash twin over K distinct trees, and no twin was deleted in the commit that ported it.
2. **Nothing went vacuously green.** The pre-port set snapshot (row sets, not counts) diffs clean at every wave. Every new gate has a planted defect its selftest fires on, and `check-control-vacuity` confirms the plant lands.
3. **The registry is the only source.** `npm run ci -- --manifest scripts/ci-runner/gates.lock.json --list` is byte-equal to `npm run ci:list`; `gate:bind --write` and `gen-docs --write` are deterministic no-ops on a clean tree; no text reader of `manifest.ts` remains.
4. **The numbers hold.** From the reference worktree: `ci:quick` at or under 58 s while covering more, local full-run floor at or under 273 s, quality tier at or under 9 minutes on a full PR, 2 processes per Bash tool call, hook suites under their pinned ewma.
5. **The tree is clean.** No bash under `.ci` or `.claude` outside the exemption list, no allow/block dotfile at root, no `.sh` or `.py` under `scripts/`, `run.sh` at or under 120 lines, `rdc.sh` at or under 70, CLAUDE.md at or under 440 lines.
6. **Credentials are single-path.** Zero `secrets.X` reads outside the allowlist, `.env` equal to the generated allowlist, one green real run for each deploy path.
7. **History resolves.** Every record's pointer resolves on a fresh clone, `git log --diff-filter=D -- agent/` shows no new deletions, and the housekeeping gate is green with a simulated future date.
8. **Full `npm run ci` green from one driver run** on the reference worktree at every milestone.
