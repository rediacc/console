Status: ready Owner: f4da5c2e Date: 2026-09-09

# Finish the big pieces: a completion strategy measured against the tree

## 0. The mechanism, restated from the ledger rather than from feel

`.ci/config/plan-boxes.json` totals **157 open and 230 done** across 89 plan files. Percentage-done climbs because the denominator climbs: ~206 boxes closed this week against ~275 added. A box count is the wrong instrument and this repo already knows it -- all 149 bash gate tests were ONE box, closed at `agent/PLAN-tooling-transformation.md:237`.

**The axis that measures the actual transformation reads 1 of 521.** The committed baseline at HEAD carries 521 paths; the worktree carries 520; the single difference is `.ci/lib/setup.sh`, staged deleted. Every other baselined path still exists.

**And the duplicate-maintenance surface is 62,233 lines.** 141 of 149 bash gate tests (43,510 lines) and 75 of 77 bash quality gates (18,723 lines) have a LIVE, registered, green Python replacement, and every one of the bash files is still on disk. That is 48% of the estate paid for twice, and it is gated behind a single box.

## 1. The big pieces, ranked by value per unit of work

**Rank 1 -- `agent/PLAN-tooling-transformation.md:621`, W7P5-c, the deletion box.** The only box in the programme that removes anything. Finishing it retires 62,233 lines of twice-maintained bash and moves the real axis from 1/521 to roughly 223/521. Its cost is NOT writer-hours: the K=5 shadow ledger licences each deletion and ledgers accrue per CI run, so it is throughput-limited
by the merge rate. That is why it must START first and why adding writers to it does nothing.

**REFUTED BY THE CENSUS OF 2026-09-09. The paragraph above is wrong and is kept so the correction is legible.** Every ledger that exists already passes K=5 with >=2 fingerprints, and did before the census ran: **81 of 82 green**, the one red being the known `w7p2-stagingtag` carve-out. Driven independently by the driver over all 82 pairs. **Zero files wait on accrual.**

**The real constraint is COVERAGE, and coverage is writer work.** Mapping every ledger row's `old.cmd` to a bash path gives **77 quality twins with a ledger and 0 of 149 gate tests**. The gate-test half is 45,099 lines, **73% of the surface**, and has no ledger to accrue FROM -- recording a first row is a writer recording it, not a merge happening. So this box DOES parallelise and
the schedule below is pessimistic about it.

**AND THE COVERAGE GAP CLOSED THE SAME DAY, by ruling rather than by work.** The gate-test half was never unlicensed: `test_twin_parity.py` covers **141 subjects, 231 of 231 rows agreeing**, continuously and re-keyed on both shas. A shadow-gate ledger is not obtainable there at all -- bash halts at the first failure while pytest decorates every one, and the comparator has no rule
to strip it. Driver ruling: that continuous check IS C1 for those twins. **The 73%-of-surface constraint this section reported is therefore gone, and W7P5-c's remaining work is C2 and C3, not evidence-gathering.**

**Licensed today: 23 files / 4,068 lines**, 22 strictly -- `check-lockfile.sh` exits 1 on `private/account/package-lock.json (npm@10 cannot resolve)` and **its bash twin fails identically**, so that is uncommitted submodule state, not a port defect. Batch 1 drains the baseline 515 -> 493. Full report: `agent/f4da5c2e/W7P5c-licence-census.md`.

**Rank 2 -- the kill list (section 2).** Retires 72 of 157 open boxes without doing them, in one sonnet session, and it is calendar-forced: `.ci/config/plan-lifecycle.json` sets `warn_days` 26 and `delete_days` 33, so the first hard `check:ci-plan-housekeeping` red lands **2026-09-26**.

**Rank 3 -- `agent/PLAN-tooling-transformation.md:607`, W7P5-a, deploy + release.** 48 files / 5,440 lines out, and the cleanest big piece available today: `.ci/scripts/deploy` and `.ci/scripts/release` measure **dirty=0** while 773 files are dirty tree-wide. Zero ledgers, zero gate registrations. Fully mechanical.

**Rank 4 -- `agent/PLAN-tooling-transformation.md:613`, W7P5-b, the bash libs.** 14 files / 6,408 lines. `common.sh` has 772 sourcers, the highest fan-in in the tree.

**Rank 5 -- `agent/PLAN-tooling-transformation.md:738`, W7P6, the 142 unnamed files.**

**Rank 6 -- `agent/PLAN-tooling-transformation.md:768`, W1P6, the strict flip.** One file deletion, terminal. It is the box that lets the operator say the programme is done.

**Deprioritise -- `agent/PLAN-tooling-transformation.md:2660`, W9 P2.** Its own text says ALONE IN ITS WAVE, so it costs a full wave slot and delivers tidiness, not deletion.

## 2. The kill list: close these WITHOUT completing them

**Executed as `git mv` into `agent/archive/plans/`, never as deletions or bulk ticks.** G-A1 at `.ci/scripts/quality/check_plan_boxes.py:435` refuses any open box gone at HEAD, and the age amnesty was removed on 2026-09-09. The archive door exists at `.ci/scripts/quality/check_plan_boxes.py:171`, is accepted by G-A2 at R100, and **has never been used** -- `agent/archive/plans` does
not exist on disk. Archiving drops `open` without raising `done`, so the percentage is not flattered.

| plan | open | retire | reason, verified against the tree |
|---|---|---|---|
| `agent/archive/plans/PLAN-stop-plan-box-enforcement.md` | 6 | 6 | `Status: superseded`. Its `--adopt` box SHIPPED (`.claude/hooks/stop/worklist.py:1177`); its parser box is duplicated at `agent/PLAN-plan-file-lifecycle.md:455`. |
| `agent/archive/plans/PLAN-env-to-bitwarden.md` | 20 | 20 | Subsumed: `agent/PLAN-env-to-bitwarden-v2.md:34` folds v1's list into ONE box, and `.ci/lib/bws-env.sh` already exists. |
| `agent/archive/plans/PLAN-github-secrets-removal.md` | 13 | 11 | The workflow layer is DONE: 4 distinct `secrets.*` names remain, 75 of 83 refs are `BWS_ACCESS_TOKEN`, `SHADOW_NAMES` occurs zero times, and `MIN_REFERENCES` is already 1 at `.ci/scripts/quality/check_secret_reachability.py:81`. |
| `agent/archive/plans/PLAN-secret-names-one-to-one.md` | 9 | 9 | No `Owner:`; superseded by `agent/archive/plans/PLAN-github-secrets-removal.md:580`. |
| `agent/archive/plans/PLAN-migrate-command.md` | 11 | 11 | Shipped: `--migrate` at `.claude/hooks/stop/worklist.py:1058`, `.claude/hooks/stop/wl_store.py:1947`, the skill and case 26 all on disk. |
| `agent/archive/plans/PLAN-handoff-sequence.md` | 7 | 7 | Waits on a superseded plan. |
| `agent/archive/plans/PLAN-worklist-ownership-continuity.md` | 3 | 3 | 11 of 14 done; `--adopt` live and documented in `CLAUDE.md:98`. |
| `agent/PLAN-secret-namespace-migration.md` | 7 | 2 | Two boxes name `mc_migrate_claude`, a row replaced on 2026-09-09. |
| `agent/PLAN-plan-file-lifecycle.md` | 3 | 1 | Its box asks for a wholesale deletion its own gate now REFUSES. |
| `agent/archive/plans/PLAN-branch-aware-workflows.md` | 2 | 2 | Both operator-gated by their own text. |
| **total** | **81** | **72** | **157 open becomes 85** |

Also fix two malformed headers, currently invisible to the census: `agent/PLAN-review-red-stop-hook-check.md:1` and `agent/PLAN-subagent-idle-detection.md`.

**Second bucket, ~14 boxes of LEDGER LAG** -- already built, never ticked. Verify and tick; do not implement. Confirmed on disk against `agent/PLAN-commit-author-identity.md:223`, `agent/PLAN-plyr-css-on-demand-loading.md:128` and `agent/PLAN-session-onboarding-marker.md:172`.

**After both buckets: 157 becomes ~71, of which ~12 are operator- or calendar-gated. The honest executable denominator is about 59.**

## 3. The accretion rule: a box ratchet CI can enforce

**A change may not raise the tree-wide open-box total.** Add G-A6 to `.ci/scripts/quality/check_plan_boxes.py`: `open_at_head - open_at_base <= budget`, budget 0.

It cannot be talked around because both inputs are already unforgeable: the base total comes from `base_ledger()` at `.ci/scripts/quality/check_plan_boxes.py:332`, which reads git rather than the worktree, and G-A0 already refuses a head ledger that disagrees with the tree.

Three legal ways to pay for a new box: close one in the same change; archive a plan; or a `Plan-Box-Budget: +N <reason>` trailer whose reason must resolve under `check:ci-plan-citations`, so it cannot become a rubber stamp.

**The hook half:** a session may add an open box only if the worklist log already carries a `--triage` verdict of PLAN+SUBAGENT for that finding. The default verdict is INLINE, which is what `CLAUDE.md` already demands.

## 4. Parallel execution schedule

**The 2-writer cap is not the binding constraint.** Seven contended singletons -- `package.json`, `scripts/ci-runner/manifest.ts`, `scripts/ci-runner/gates.lock.json`, `.ci/config/language-policy-baseline.json`, `.github/workflows/ci-quality.yml`, `docs/agent-reference/TRAPS.md`, `.ci/config/plan-boxes.json` -- mean two waves that both touch one are not disjoint. **Exactly one
writer per wave holds the REGISTRAR role and owns all seven**; the partner hands its registration entries over as a patch.

The second binding constraint is `common.sh`'s 772 sourcers. Past wave 3 the work does not parallelise, and a schedule claiming otherwise is lying.

- **Wave 1, sonnet + sonnet.** 1A registrar: the kill list, owning the 10 plans,
`agent/archive/plans/**` and `.ci/config/plan-boxes.json`. 1B: W7P5-a deploy + release, both trees dirty=0 today, needing none of the seven singletons.
- **Wave 2, opus + sonnet.** 2A registrar: W7P5-c's gate-test half. 2B: W7P5-b's four
lowest-fan-in libs only -- `gate-controls` 41, `bws-env` 111, `emit-advisory` 218, `service` 225.
- **Wave 3, opus + sonnet**, blocked until the live writers land. 3A: W7P5-c's quality
half. 3B: W7P6's first tranche, the groups with no fan-in into 3A.
- **Wave 4, ONE opus, no partner.** `common.sh`'s endgame and W7P4-W, re-measured at
147 scripts / 258 real `run:` sites, not the box's 215/348.
- **Wave 5, ONE sonnet.** W1P6, then W9 P2 if still wanted.

## 5. The honest completion estimate

**15 to 19 working days from a clean start, so roughly 2026-10-01 to 2026-10-06** for "the baseline is deleted and `check:ci-language-policy` is strict".

**This number is void without section 3.** 275 boxes were added in the last seven days; a 19-day plan absorbs another ~590 at that rate and never closes.

**Calendar-gated, unmovable by parallelism:** the plan-housekeeping cliff first reds **2026-09-26** (3 plans), 17 by 09-30, 87 by 10-10, so wave 1A must beat it; `agent/PLAN-tooling-transformation.md:2486` at ~2026-09-21; `agent/PLAN-tooling-transformation.md:2473`, 54 uncompacted plans; and the K=5 shadow ledgers, which accrue per CI run and cannot be outrun by adding writers.

**Operator-gated: 12 boxes gating ~20 downstream.** `agent/PLAN-tooling-transformation.md:1826` (mint the machine accounts) blocking `:1861`; `agent/PLAN-tooling-transformation.md:2581` (settle `private/account`) blocking `:2734`; the `autopilot_no_bypass` organisation variable; the `w7p2-stagingtag` human sign-off; `agent/archive/plans/PLAN-github-secrets-removal.md:551` and
`:578`; `agent/archive/plans/PLAN-branch-aware-workflows.md:149` and `:154`; `agent/PLAN-bws-rotation-on-failure.md:99`; and two deferrals in `agent/PLAN-secret-namespace-migration.md`. **Ask for all of them in one round trip.**

## 6. What "done" means, so the finish line stops moving

The programme is done when `.ci/config/language-policy-baseline.json` does not exist and `check:ci-language-policy` prints STRICT. That is one observable fact, not a percentage, and no new finding can move it.
