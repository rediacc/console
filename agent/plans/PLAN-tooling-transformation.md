# PLAN: Tooling Transformation
Status: ready
First-Seen: 2026-09-21
Owner: d778be9d (adopted from 8f55d4f0 2026-09-20)
Updated: 2026-09-20

ONE plan, not two. Round 1 was drafted into `~/.claude/plans/` where nothing tracked it; Round 2 was then written as a SECOND document, which made it worse. Both are now here, in one tracked file: Round 2 is the live plan, Round 1 is kept below in full because its 83 ticked boxes are the only record of what was actually done and why.

Round 1's 48 still-open boxes are de-checkboxed on purpose. Every one is carried by a Round 2 box above, and leaving both checked would count the same work twice in `.ci/config/plan-boxes.json`. Their text is preserved verbatim.

READ THE ROUND 1 NUMBERS WITH CARE: fifteen counts it pins were re-measured on 2026-09-07 and were stale, and four of its premises were false. The corrections are in the Round 2 section; where the two disagree, Round 2 was measured.

## Read this first: three axes, never collapsed

The programme's headline was "quality gates ported: 77 of 77 (100%)". That number is true and it is not progress. It describes artifacts existing. Every workstream reports three numbers:

- **PORTED** a Python twin exists
- **LIVE** CI actually invokes it
- **DELETED** the bash twin is gone

For the `.ci` quality gates those are **78 / 0 / 0**. Zero references to `rediacc_ci/quality` exist in `package.json`, `scripts/ci-runner/manifest.ts`, `.github/workflows/ci-quality.yml` or `scripts/ci-runner/gates.lock.json`. What CI runs is 69 bash gates plus 43 Python gates that were never part of the port. That is the design (invariant 5 forbids deleting a twin in the change
that ports it), but "100%" as a headline reads as finished, and it is not.

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
| Gate tests ported / live / deleted | 124 of 149 / 124 / 0 (2026-09-08) | `grep -rh '^BASH_TWIN' .ci/rediacc_ci/tests/gates/*.py \| sort -u \| wc -l` |
| Workflow-invoked scripts shimmed | 0 of 215 (348 call sites) | `grep -rhoE '\.ci/scripts/[A-Za-z0-9_./-]+\.sh' .github/workflows/` |
| `deploy/` + `release/` ported | 0 of 48 | -- |
| Bash libs ported (W7P5-b) | **14 of 14**: 5 DELETED, 9 fully ported with the twin on disk for W7P5-c (2026-09-24) | `ls .ci/lib/*.sh .ci/scripts/lib/*.sh`, and `shadow-gate.ts --pair w7p5b-<lib> --assert --k 5` per pair |
| Lock entries | 458 total, 448 `gate: true`, 149 gate tests, 95 slow, 45 with `paths` | `gates.lock.json` |
| Workflow steps region-emitted | 150 of 276; **126 hand-written** | walk the `>>> gate-bind` markers |
| Plan boxes ticked | 81 of 131 | -- |
| Milestones met | **2 of 12** (M2, M4) | -- |

**The honest headline: 0 of 521 bash files deleted, 23% twinned, 2 of 12 milestones.** The 62% box figure measures drafting, not shipping. By eventual-Python volume the programme is roughly 41-55% through; by deletion it is at zero.

---

## M-1: the wave is unlanded, and it precedes everything

Branch `0906-1` (upstream `origin/tooling-transformation-w0`) is **115 commits ahead of origin/main and 0 behind**, **1,198 files changed, +174,362 / -25,205**, with **no open PR** (`gh pr list --state open` returns `[]`). Every measurement above describes a tree nobody has reviewed or merged. Land it first: the longer it sits, the worse the merge, and every number here drifts
under it.

---

## Corrections to the predecessor plans

Nine pinned counts were stale, four premises false, three prerequisites missing.

| Previous claim | Measured today |
|---|---|
| W1 P4: 67 `sys.path` files | **36 files / 39 hops** (2026-09-09, tracked + untracked); it FELL, 45 at HEAD |
| W7 P3: 41, then 53 ported; 148 tests | **124 of 149** (2026-09-08, through W7P3-RT batch 6, the LAST scanner batch); remaining **25**, all real-tree / shadow-covered / drops |
| W7 P4: 201 scripts / 334 call sites | **215 / 348** -- the surface GREW |
| W5: 374 `check` / 21 `check_out`; M5's 395 | **398 / 24**, so **422** |
| W12 P2.8: 32 compacted, next red 09-25 (2) | **31**; next red **2026-09-26 (3)**; warn band **09-19** |
| Requirement 15: 8 / 8 / 20 json | **9 / 16 / 24** |
| W8: 1,014 env names | **745** under a stated method; 1,014 is not reproducible |
| TRAPS floor 75 | **77 / 77** |
| M11: 46 records | **32** (31 compacted + 1 parked) |
| W6 P5: `LEGACY_ARMS_MAX` reaches zero | **the name occurs ZERO times in the tree.** The number that reaches zero is the anonymous derived `n_legacy` at `.ci/scripts/test/gates/test-run-sh.sh:380`; the partition it feeds is asserted at `.ci/scripts/test/gates/test-run-sh.sh:292-329` and the `run.sh` ceiling at `.ci/scripts/test/gates/test-run-sh.sh:566`. run.sh is at **120 of 120**. Measured 2026-09-09: 2 router arms, 16 legacy, 50 subcommands, 18 documented verbs. E3 rewrote the anti-vacuity floor that would have redded when this reached zero |
| W9 P2: baseline is "one sorted array" | an **object** with 42 `unguarded` entries. Hazard stands, description does not |
| Gaps: "the language-policy gate does not exist" | it exists, registered three-point, and **blocks on growth** |
| W12 P2.7: "A5 in `04-decisions.md`" | **not there.** `G-A5` is a gate rule at `.ci/scripts/quality/check_plan_boxes.py:41,:428`. P3.2's `D-A6` DOES mean `docs/ci-overhaul/04-decisions.md:22-23`. Two schemes, adjacent boxes |
| Gaps: `private/growth` submodule PR | **not a submodule.** `.gitmodules` lists four; `.gitignore:85` ignores it |
| W8 P1: "exactly two agents" | **one writer.** The residue is ~24 entries of one secret name on a single-writer file, and all four directions are already gated |

---

## Three prerequisites no box owned

### P-A. A header on a port is a CUTOVER, not a registration

`derivedId()` (`scripts/lib/gate-header.ts:235-238`) maps `.ci/rediacc_ci/quality/npmrc.py` to `check:ci-npmrc`, the id its live bash twin already owns (`package.json:121`). **CORRECTED 2026-09-07 BY MEASUREMENT: the split is 59 colliding / 18 not, NOT "all 77, zero do not".** Two independent runs of `derivedId()` over `.ci/rediacc_ci/quality/*.py` agree on it. The overstatement is
worth keeping visible because the CONCLUSION survives it while the obvious go/no-go test does NOT: an agent told "all of them collide" writes no header, but an agent told "18 are free" needs to know that those 18 are ALSO unwritable, for three different reasons. Seven have twins under an ABBREVIATED id `derivedId` never produces (`label_references` -> `check:ci-label-refs`,
`no_app_admin_perm` -> `check:ci-app-admin-perm`, and five more), so they look free to any lock-keyed grep. Nine are invoked straight from a workflow with no `package.json` key at all, a registration shape gate-bind's verifier does not model. Two are referenced nowhere.

**AND THE AUTHORITY IS `package.json`, NOT THE LOCK.** `release_state.py` derives `check:ci-release-state`, which is ABSENT from `gates.lock.json` and PRESENT in `package.json`. A go/no-go test of "confirm the id is absent from the lock" passes it and produces a red gate. That test came from this plan, and it was wrong.

`gate-bind`'s check arm is fail-closed on all of this. The binder already scans the package (`scripts/gate-bind.ts:98`, `inScope` at `:201-202`, self-control at `:1069`), so this is not a tooling gap -- it means the 78 headers cannot land as a cheap preparatory box. **They ARE W7 P4 for the quality tree**, one atomic commit per gate. This is the largest re-ordering here.

### P-B. A gate cannot declare `env:` -- or an extra `if:` conjunct

`scripts/ci-runner/gate-spec.ts` has no `env` field (complete list: noProfile, id, run, gate, needs, mutex, reads, weight, heavy, paths, slow, qualityGateTest, leaves, ci) and `emitStep` (`scripts/gate-bind.ts:408-419`) hardcodes `if: ${{ !cancelled() && steps.${guard}.outcome == 'success' }}` with no extension point. **Six gate files already carry the literal blocker string
`gate-bind cannot emit one`** and sit at `emit: false` for that reason alone; ~14 steps carry an extra `if:` conjunct. All 26 `env:` blocks sit outside the regions, which is why 126 of 276 steps are hand-written. Fixing `env` alone leaves those unshardable. This is W2.4's missing `reads?: string[]` recurring, and it violates the programme's own acceptance test at
`docs/ci-overhaul/08-driver-contract.md:377-385`.

Two further holes in the same machinery:
- `scripts/gate-bind.ts:1567-1569` filters `dropped` to `claimed` and refuses only on `claimed`. Bare
`dropped` is never printed on the write path and never asserted empty -- the 2026-09-05 four-deleted-steps shape, still open.
- **Nothing in the tree checks a step's `env:` at all.** `scripts/gates/check-ci-parity.ts:29` states as a
design rule that an `env:` value is not an invocation. Strip `DOCKERHUB_TOKEN` from `.github/workflows/ci-quality.yml:1159` in a scratch copy today and the whole battery stays green.

### P-C. 142 of the 521 files are named by no plan box

**VERIFIED INDEPENDENTLY 2026-09-07, and the first attempt to check it was WRONG in the plan's favour.** Sampling the directories this section lists as examples gives 99, not 142, which looks like a refutation and is not: the set is the COMPLEMENT, so it also holds `.ci/scripts/test` (32 files, `run-all.sh` among them) which no example directory names. Computing it properly --
baseline 521, minus the quality twins, the gate tests, deploy, release, the bash libs and the `.claude` trees, all of which a box does name -- leaves **142 exactly**. Recorded because the narrow sample is the check a hurried reader would run, and it would have produced a confident false correction.

**29,057 lines, 22% of the backlog**, unexamined since the baseline was generated today: `.ci/scripts/test` non-gate infra 32, `ci` 17, `build` 17, `autopilot` 16, `infra` 11, `private` 9, `security` 9, `housekeeping` 6, `review` 4, `version` 4, `.ci/docker` 8, `setup` 3, `env`/`pr`/`signal` 3, `.ci/bootstrap.sh`, `.ci/config/constants.sh`, `.claude/lib/standing-orders-brief.sh`.

**A new shim is illegal.** `.ci/scripts/quality/check_language_policy.py:143` sets `SHIM_MAX_LINES = 1`. The two existing shims are 127 and 145 lines and survive only because both are grandfathered INSIDE the baseline; any new one is an addition that `write_verdict` (`:441`) refuses even when the total shrinks. Only **3 files repo-wide** have a one-line effective body. So the
allowlist is not an escape route: **~500 of the 521 must be deleted, not exempted.** Defensible exemptions are the chicken-and-egg and container-entrypoint classes -- `.ci/bootstrap.sh` (395 lines; it exists because these hosts have no pip, uv or pytest), the five `.ci/docker` entrypoints, and `.ci/config/constants.sh`. Roughly 8 files. **The allowlist has no slot for a 395-line
exemption** -- either move `bootstrap.sh` into `.ci/bootstrap/` and use a `tree:` entry, or add a third kind. Naming it now avoids an unresolvable red at the strict flip.

---

## Four tracks, disjoint by file

- **T-PORT** the `.ci` port. The critical path and the largest body of work.
- **T-SCHED** schedule and platform: the P-B unblocker, W3 P3, W2.3, W2.5, W5 P7, W6 P3/P4/P5.
- **T-ENV** environment, secrets, policy: W0.0/W0.1, W8 P1-P6, W4 P3/P4/P5.
- **T-DOCS** docs, records, layout, gaps: W9 P2, W11 P4/P5/P6, W12, and the unowned gaps.

---

## T-PORT

- [x] **PRE-A0 S** `check-ci-parity` learns `python3 -m`. `resolveLeaves` (`scripts/gates/check-ci-parity.ts:139-228`)
      has no `python3` arm, so `python3 -m rediacc_ci.quality.npmrc` resolves to the bare token
      `python3` and `leaves` can never match. ~40 lines + 4 controls.
      **Acceptance:** every `-m` body resolves to its tracked module path; no entry resolves to
      `python3`. Both directions.
      **DONE 2026-09-08.** `resolveLeaves` gained a `python3`/`python` arm: `-m <module>`
      swaps dots for slashes and resolves against a TRACKED path set, trying
      `.ci/<rel>.py`, `.ci/<rel>/__main__.py` and `<rel>.py` in that order. The tracked set
      is new on `ScriptUniverse` and comes from `git ls-files`, never a glob -- a module
      resolving to an untracked file is not a leaf CI can run, and answering from the
      filesystem would make a scratch file look like a registered gate.
      **An unresolvable module is NAMED, `missing-module:<name>`, not swallowed.** Returning
      `python3` for it would be this box's own bug wearing a new coat.
      **Five controls, and they are not vacuous:** replacing the `-m` lookup with `-1` makes
      `check:ci-parity` exit 1 with `CONTROL FAILED: a dotted -m module does not resolve to
      its tracked file`. Both acceptance directions are covered (a dotted module resolves to
      its file; nothing resolves to the bare `python3`), plus a package falling through to
      `__main__.py`, the missing-module naming, and the anti-silencer that a plain
      `python3 <script>` invocation still resolves to its script.
      **This does NOT change how gates are registered.** The estate registers bare file
      paths because of this very gap, and `scripts/lib/gate-header.ts:derivedRun` records
      the trap; PRE-A1 is the box that would move to the `-m` form. What changed is only
      that the resolver has stopped lying about a form the repo may legitimately use.
- [x] **PRE-A1 S** One canonical import line. `pyproject.toml:249` gives tests `pythonpath = [".ci"]`;
      non-test callers have no equivalent, so each entry point carries a `sys.path.insert`. After
      A0 the canonical form is `PYTHONPATH=.ci python3 -m ...` with no hop at all. Converts the 15
      in `.ci/scripts/quality` plus `check_pytest.py`. **Acceptance:** the `sys.path` file set is a
      strict subset of the set at box start, printed by name; no file under
      `.ci/rediacc_ci/quality/` acquires one.
      **DONE 2026-09-09, acceptance met and re-measured by me independently with an AST
      walk: 44 files wrote `sys.path` by hand at box start, 36 now, the ADDED side EMPTY,
      and ZERO under `.ci/rediacc_ci/quality/`.** A strict subset, both clauses.
      **Two premises did not survive.** "The 15 in `.ci/scripts/quality`" is wrong --
      `aaba93b29` had already drained the `.ci` hops onto `_cipath.py`, and the real residue
      was 8 files whose hop was the `.claude/hooks/stop` one, which `PYTHONPATH=.ci` would
      not have fixed. And the canonical form the box names, `PYTHONPATH=.ci python3 -m ...`,
      is unreachable from a writer's file set: it moves the registered command, which is
      `package.json` + `manifest.ts` + `gates.lock.json`, all driver-only. The form used is
      the one the tree already documents, `rediacc_ci.paths.on_sys_path`.
      **A measured reason for one exemption, worth carrying:** ruff's `E402` exempts a
      `sys.path` mutation before a module-level import and exempts NOTHING else, so a
      resolver call costs a per-line waiver the bare form does not. `check_fetch_retry.py`
      keeps its hop with the probe transcript recorded as the reason rather than a waiver.
      **A gate broke correctly and was repaired forward:** `check:ci-python-gate-deps` read
      only the bare-insert spelling, so a hop it could not parse made two first-party
      modules look like uninstalled dependencies. Its first control did not fire, and that
      was a fact about the control -- the helper arm is worth 43 first-party names to one
      file and 0 to the one it was pointed at.
- [x] **W7P3-a..d C, 2 writers** The 52-53 admissible gate tests, four batches of 13.
      **Batch membership is derived, never chosen:** `ALL(149) - DONE(124) - REAL_TREE - SHADOW`.
      Read the real-tree set FROM `gates.lock.json` (4 `mutex tree:` + 23 `reads tree:` = 27
      entries), and exclude a `test-X.sh` whose subject `check-X.sh` is named by any of the 78
      ledgers. **RE-DERIVED 2026-09-08 AFTER BATCH 10: 42 remaining, 0 ADMISSIBLE.** The easy
      pool is exhausted, so this box is DONE as written and everything left is
      W7P3-RT or shadow-covered. Previously, after batch 9: 51 remaining = 9
      admissible + 42 needing care, itself derived by running the subtraction
      rather than quoting the batch report, which said 17 and was wrong. The care set is 27 real-tree, 14 shadow-covered
      and 9 standing drops, and those OVERLAP -- 27+14+9 exceeds 42 -- which is why a
      subtraction has to be run and cannot be added up by hand. The 9 admissible are
      test-autopilot-harness, test-claude-hooks, test-dispatch-release,
      test-housekeeping-phases, test-review-labels, test-scope-baseline-attest,
      test-scope-engine, test-skip-plan-reconcile, test-workflow-contracts.
      `test-claude-hooks.sh` is admissible ONLY since the parity driver gained
      `TWIN_TIMEOUT` this session; at 13m31s it was previously unportable by
      construction and had been proposed as a fourth standing drop. The earlier
      **85 remaining = 53 admissible + 32 needing care** (26 real-tree,
      13 shadow-entangled, 7 both) was correct at 64 ported and is kept to date the
      movement. Match ledger basenames as WHOLE TOKENS -- a substring match
      hits `common.sh` from `d.sh` and excludes 47 instead of 7.
      **Acceptance per module:** ported case SET equals the twin's under the widened word-match
      (not the flat PASS-count floor, which is the failing-open path batch 5 found); a defect
      planted in the REAL subject caught by both sides; subject restored byte-identical by
      sha256; the batch asserts no ported twin is in the real-tree set, read from the lock.
      **Runtime:** `check:ci-pytest` is `slow: true`, `weight: 8`, `-n 8 --dist loadgroup`,
      measured 381.41s against a **294.65s floor set by the guards fixture pinned to one worker**
      -- so the first ~87s of added work is absorbed by spread. Re-tier after every batch, in the
      quiesced reference worktree only (invariant 14).
      **CLOSED 2026-09-09, and the "0 ADMISSIBLE" claim was re-derived rather than quoted.**
      The subtraction, run against the tree and the lock: 149 bash gate tests under
      `.ci/scripts/test/gates/`, 143 python twins under `.ci/rediacc_ci/tests/gates/`, and
      **16** bash tests with no twin under either the `test_gate_<n>.py` or `test_<n>.py` name
      (the naive rule that strips only `test-` mis-scores the six whose own name begins
      `gate-`, and reports 17). Of those 16: **7** carry `tree:repo` in
      `scripts/ci-runner/gates.lock.json` and belong to W7P3-RT; **8** are shadow-covered under
      `.ci/shadow/` -- including `autopilot-breakpoint-alignment`, whose ledger is
      `.ci/shadow/w7p2-apbp.observations.jsonl` and is invisible to a name-substring search;
      and **1**, `.ci/scripts/test/gates/test-scrub-sentinel-empty.sh` (88 lines), is a genuine
      remainder that is neither. All nine names this box listed as admissible are ported. The
      straggler is not dropped: it is assigned alongside W7P3-RT, which is the only batch still
      moving. **There is no machine-readable record of the "9 standing drops"** this box cites --
      the phrase appears only in this plan and in two module docstrings -- so that third
      category cannot be checked by anything and the count above deliberately does not use it.
- [x] **W7P3-RT S, 1 writer** The 27 real-tree twins. **UNBLOCKED 2026-09-08:** `xdist_groups.group_for()` already returns
      `REAL_TREE_GROUP`, and the parity driver USED to refuse outright to drive any ported
      twin in that set -- the isolation machinery existed and the driver forbade using it.
      That refusal is now replaced by `real_tree_admission()` in
      `.ci/rediacc_ci/tests/gates/test_twin_parity.py`, a per-module opt-in
      (`REAL_TREE_TWIN = True`) that ALSO requires the module to land in
      `REAL_TREE_GROUP`, because a declaration checked against itself is vacuous and an
      `XDIST_GROUP` of its own would override the grouping. Over-claiming on a twin that
      is not real-tree is refused too. Five controls, both weakenings planted and caught.
      SO THIS BOX IS NOW THE CRITICAL PATH: with 0 admissible left, no further W7 P3
      progress is possible without it.
      **A DEFECT IN THE DRIVER'S OWN BATCH BRIEF, found by the batch-2 writer and
      verified here 2026-09-08.** Every brief since batch 2 has told the writer to hand
      back a `gate-test:*` manifest fragment per port, and invariant 13 is quoted at it.
      That instruction is WRONG for this track and always was: `grep -c
      "rediacc_ci/tests/gates" scripts/ci-runner/manifest.ts` returns **0**, and no lock
      entry names a pytest gate module in its `leaves` -- all 124 ports are reached by
      COLLECTION, through `pyproject.toml`'s `testpaths` (which lists
      `.ci/rediacc_ci/tests/gates`) under the single `check:ci-pytest` entry, whose
      `paths: ['.ci/rediacc_ci/**', ...]` already selects it under `--changed`. The 149
      `gate-test:*` entries are the BASH TWINS and stay (invariant 5). Applying the
      fragment the brief asked for would have added a `leaves` path npm resolves to
      nothing and REDDENED `check:ci-parity`. **So a W7 P3 batch owes no manifest edit and
      the driver runs no `gate:bind --write` for it.** The registration hand-over rule
      still holds for W7 P4, where the entry point IS a registered leaf.
      **DONE 2026-09-09. 26 of the 27 now have twins**; the 27th is the recorded standing
      refusal `autopilot-breakpoint-alignment`. Eight ports landed -- the 7 the lock marks
      `tree:repo` plus the `test-scrub-sentinel-empty.sh` straggler W7P3-a..d left. Bash gate
      tests with no twin: **16 -> 8**, re-derived rather than quoted; the remaining 8 are the
      shadow-covered set. The box's "27" was CURRENT, not stale: `real_tree_twins` is 27 and 19
      already had twins, which is why the lock showed only 7 outstanding.
      **Two of the box's exclusions were REFUTED by measurement.**
      `test-breakpoint-portability.sh` does not need `.ci/breakpoint/**` as a work area (a
      one-token plant, whole-tree digest identical before and after, under 3s), and
      `test-scrub-sentinel-empty.sh`'s "no plant can turn either side red" holds only while
      `aws` is ABSENT -- a 4-line PATH shim makes both sides take the real branch, and the
      pipefail regression then reds both identically.
      **THE SELF-SCANNING TRAP, for every future port:** a port of a self-scanning subject
      lands on that subject's own offender list, because a PORT is on no exclusion list. Two
      did, within minutes; each now carries a control that reds BY NAME if it recurs.

            **A SEVENTH SUBJECT JOINS THE EXCLUSION, refused rather than dropped, 2026-09-08.**
      `test-autopilot-breakpoint-alignment.sh` was briefed to batch 4 with an explicit
      instruction to REFUSE rather than drop, and the writer did, having enumerated the
      gate's whole input surface instead of assuming it
      (`.ci/rediacc_ci/quality/autopilot_breakpoint_alignment.py:104-105` pins
      `.ci/breakpoint/workflow/breakpoint.yml` and `.github/workflows/autopilot.yml`).
      Every plant target is closed: the first by invariant 8, the second by the
      driver-only list, and the THIRD blocker is new and will recur -- the gate's own
      entry point now lives under `.ci/scripts/quality/`, so any wave that fences that
      directory off for a cutover writer also fences off this subject. The six temp-copy
      cases are portable in principle, but the only real-tree case could never be seen
      red, and a port whose central case cannot fail has not been shown to assert
      anything. `.ci/breakpoint/` was verified byte- and mtime-untouched afterwards.

      **RECORDED EXCLUSION, so it stops being a silent drop (this is the fourth time
      round).** `test-breakpoint-portability.sh` and its five `test-breakpoint-*.sh`
      siblings stay admissible in the derivation and get selected and dropped by every
      batch, because plant-verifying one means temporarily WRITING under
      `.ci/breakpoint/**`, which invariant 8 forbids and every batch brief lists as
      must-not-touch. `agent/8f55d4f0/W7P3-batch5-brief.md` names the two ways out --
      grant one batch owner that path explicitly and re-run the vendored-copy drift gate
      afterwards, or exclude them in the derivation with the reason -- and says plainly
      "do not silently drop them a fourth time". This IS the exclusion, with the reason,
      recorded on the driver's side because the brief belongs to a peer session.
      Re-admitting them is a deliberate act that costs a path grant, not an oversight to
      be rediscovered. `test-scrub-sentinel-empty.sh` is excluded on the same footing
      while `aws` is absent: the twin takes its tool-absent branch, so both real cases
      are unreachable and no plant can turn either side red -- a port would be
      green-but-unproven.

      **BATCHES 1-3 LANDED 2026-09-08, 9 of the 22 scanners.** Batch 3's
      `label-references` port found the sharpest trap in this slice: the subject sweeps
      `.ci` recursively and excludes exactly TWO basenames to protect itself from planted
      samples, its own gate and its own twin. A PORT is on neither list, so a literal
      transcription of the twin's fixtures would have turned `check:ci-label-refs` red
      tree-wide. The port renders every fixture through a `%s` template (`%` is outside the
      `[A-Za-z0-9._:-]` class all ten extractors use) and carries a control pointing the
      real subject at the ports' own directory, so a template that ever starts matching
      reds BY NAME. Any future port of a SELF-SCANNING subject owes the same treatment.

      **BATCH 1 LANDED 2026-09-08** (the note here said
      IN FLIGHT until this survey; it had returned): three of the
      22 `reads tree:` SCANNERS, chosen over the 5 `mutex tree:` WRITERS
      (`test-docs-gen.sh`, `test-gate-anti-vacuity.sh`, `test-gate-paths-exist.sh`,
      `test-generate-tag-inputs.sh`, `test-shrink-only-composition.sh`), which stay
      untouched until a scanner batch has proven the opt-in end to end. A COST GATE
      APPLIES FROM NOW ON, and the numbers below are MEASURED on 2026-09-08 rather
      than projected. The kill timer is **1080s, not 3600s**: 3600 sat above
      `quality-security`'s own `timeout-minutes: 20` and could therefore never fire,
      which `check:ci-inner-timeout-reachable` now refuses by name.

      **THE FULL SUITE PASSES: 9960 test(s) collected and passed, corpus 2282 across 3
      roots, exit 0**, driven with `PYTEST_RUN_TIMEOUT_S=3600` because the 1080s default
      is sized to a CI job ceiling that does not apply locally. That run is the first in
      which every gate landed this session sat inside a full pass.

      **AND THE REUSE SKIP NOW PAYS, measured rather than argued.** That pass recorded an
      agreement for all 116 subjects, so `.ci/shadow/twin-parity.ledger.jsonl` holds 121
      rows and every pair is reusable. The parity module re-run immediately after:
      **121 passed in 1.22s**, with 116 cases printing `REUSED a recorded agreement` --
      against the ~28 minutes those same drives dominate. `TWIN_PARITY_ALWAYS_DRIVE=1`
      re-drives for real (3.38s for one subject), so the escape hatch works in both
      directions. WHAT IS GIVEN UP is exactly what the output says: a reused case proves
      nothing new that run, and a divergence caused from OUTSIDE the two hashed files
      survives longer. The saving reaches CI only when that ledger is committed, which is
      a commit decision and not this session's to take. Any twin over ~120s is
      escalated before porting rather than after. **THE 15 REMAINING SCANNERS ARE
      TIMED, so the next batch's cost decision is arithmetic and nobody re-measures:**
      tutorial-render-queue 0.5s, autopilot-breakpoint-alignment 0.7s,
      autopilot-workflow-invariants 1.2s, label-inventory 2.7s, swallowed-failures
      2.6s, label-references 3.6s, runner-advice 4.4s, knip-blockers 5.5s,
      greenlight 9.2s, scope-gate-outputs 9.4s, profiler-coverage 10.5s, ci-runner
      17.3s, suppression-liveness 24.8s, trap-registry 62.7s, review-status 75.3s.
      Only the last two approach the bar, so COST IS NOT WHAT LIMITS THE NEXT BATCH.
      **`test-breakpoint-portability.sh` IS THE FOURTH BATCH TO REACH AND DROP IT**,
      and the batch-7 residue note asked that it stop being dropped silently: plant-
      verifying it means writing under `.ci/breakpoint/**`, which is invariant 8 AND
      driver-only. It needs an explicit path grant plus a vendored-copy drift re-run,
      or an exclusion recorded in the derivation with that reason. Not a drop by
      merit -- the same folklore shape `test-claude-hooks.sh` was in until its
      driver defect was fixed. These 26 include `test-ci-parity.sh`, `test-language-policy.sh`,
      `test-gate-anti-vacuity.sh` and `test-dead-bash.sh` -- the instruments this slice is
      measured by. Port last, never two per batch.
      **BATCH 2026-09-09: 19 of 27 now ported, and THE BOX OVERSTATES ITS OWN POOL BY 17.**
      Verified by the judge's own line, not by my grep (which was wrong twice):
      `all 133 ported twin(s) are admissible against the 27 real-tree test(s) known to the
      lock and to run-all.sh; 19 opted in via REAL_TREE_TWIN and land in 'real-tree'`.
      **Two mutex `tree:repo` WRITERS ported**, which is the batch the box's own precondition
      was waiting for: `test_gate_generate_tag_inputs.py` and `test_gate_paths_exist.py`,
      both green under `TWIN_PARITY_ALWAYS_DRIVE=1` and re-driven by me at 2 passed.
      **The residue is 10, not 27, and only FOUR were ever schedulable:** 17 were already
      ported before this batch, 4 of the rest are the instruments the box itself says to
      port last (`test-gate-anti-vacuity`, `test-ci-parity`, `test-language-policy`,
      `test-dead-bash`) and 2 are standing exclusions
      (`test-autopilot-breakpoint-alignment`, `test-breakpoint-portability`). The box's
      arithmetic should be a derivation, not a count. Its `4 mutex + 23 reads` is also
      wrong: measured **5 + 22**, same total, and W7P3-BAT's design note already recorded
      that correction while this box's text was never updated.
      **A PERMANENT STRUCTURAL CONFLICT, not a per-batch accident:**
      `.ci/scripts/test/gates/test-docs-gen.sh` **cannot be ported by any batch whose brief
      carries the standing "never run `gen-docs.ts --write`" constraint**, because the twin
      itself runs that command twice in its case C -- so merely DRIVING it for parity
      executes what the writer is forbidden. Every future batch that selects this subject
      will rediscover it unless the exclusion is recorded with that reason, which is why it
      is recorded here. It is not a merit judgement: the port is straightforward the moment
      a batch owner is granted the command.
      `test-shrink-only-composition.sh` is blocked differently and also for cause: two of its
      controls plant probes INTO `.ci/scripts/quality/`, and the whole point of those cases
      is a `.py` offerer under `.ci/` that the pre-widening enumerator could not see, so
      relocating the probe out of a fenced directory would weaken the case.
      **A twin-level hazard worth carrying:** `test-gate-paths-exist.sh` was widened to
      `*.py` by a peer in UNCOMMITTED work (` M`, 2026-09-08 17:59), and the new port
      transcribes the widened form. If that uncommitted change is reverted, port and twin
      diverge on `.py` files and parity reds for a real reason.
      **No registration was owed and none was made:** `grep -c "rediacc_ci/tests/gates"
      scripts/ci-runner/manifest.ts` is 0, and both ports are reached by collection through
      `pyproject.toml` `testpaths` under the single `check:ci-pytest` entry.
- [x] **W7P3-BAT S** Wire `battery.py` (811 lines, referenced by nothing), retire `run-all.sh`
      (620 lines, live at `package.json:148` and `:337`).
      **Hard precondition:** `run-all.sh` is itself one of the 142 unnamed files AND one of two
      isolation sources for `real_tree_twins()`. Every `*_FALLBACK` member must first appear as a
      `tree:` declaration in the lock. **Acceptance:**
      `real_tree_twins(lock, runner=/dev/null) == real_tree_twins(lock, runner=run-all.sh)` as a
      SET -- that equality IS the retirement licence and is checkable before anything is deleted.
      Re-key the `PATTERN="test-*.sh"` glob discovery `scripts/gates/check-dead-bash.ts:19-20` depends on, same
      change (invariant 2).
      **DESIGN 2026-09-08: THE STATED BLOCKER IS ALREADY RETIRED.** The box gates itself on
      "every `*_FALLBACK` member must first appear as a `tree:` declaration in the lock";
      measured today `real_tree_twins(lock, /dev/null) == real_tree_twins(lock, run-all.sh)`
      is **27 == 27 with the runner-only set EMPTY**, so the retirement licence is granted
      and this box is materially smaller than its billing. (The 4+23 split is really 5+22;
      same total.) **What the box does NOT name is the real work:** two live gates exist only
      to police `run-all.sh`'s bash TEXT -- `check:ci-battery-clean-tree` asserts a
      `tree_state() { ... }` one-liner is present and refuses on an absent file, and
      `check:ci-pool-writer-safety` parses `WRITER_TESTS=(` out of it. Retiring the runner
      without retargeting both reds the tree BY DESIGN, and it will read as a bug in the
      deletion. Also `.ci/rediacc_ci/battery.py:76-80` repeats the false claim W7P4-Q was told to fix in
      `.ci/rediacc_ci/check_pytest.py:74-78` (that gate-bind only scans two roots); fix it here or the
      registration decision is taken from a stale premise.
      **WIRED 2026-09-09. The licence was RE-MEASURED, not quoted: `27 27 True`, with the
      runner-only AND lock-only sets both EMPTY.** `battery.py` is now the live battery
      runner -- `package.json:152` and `:360` repointed (the box said `:148`/`:337`, stale),
      `scripts/gates/check-ci-parity.ts:78`'s `BATTERY_RUNNER` and the `leaves` at
      `scripts/ci-runner/manifest.ts:4929` with it. **Driven through the rewired npm key, not
      inferred:** `npm run check:ci-quality-gates -- --list` gives `149 test(s): 5 W, 22 S,
      122 T (schedule from lock)`, 4475 bytes of stdout and **0 of stderr** -- so it is not
      the zero-byte phantom a wrong id produces.
      **THOSE THREE FRAGMENTS HAD TO LAND TOGETHER, proven empirically through the
      `CI_PARITY_ROOT` seam:** repointing `package.json` ALONE takes `check:ci-parity` from
      392 findings to 543, **150 new**, every one reading "that step resolves to
      [battery.py] and none of [run-all.sh]". Patching `:78` removes all 150.
      **BOTH POLICING GATES ARE RETARGETED AND BYTE-IDENTICAL ACROSS THE TWIN PAIR** on
      stdout AND stderr in every case, run separately -- 6 cases for
      `check:ci-battery-clean-tree` (33 controls) and 8 for `check:ci-pool-writer-safety` (39
      controls). `check:ci-pool-writer-safety` now reads its registration from the LOCK
      instead of parsing `WRITER_TESTS=(` out of bash, and that is not a weakening: the old
      parse yielded 4 names, the lock yields the same 4 plus one more, and `old - new` is
      EMPTY.
      **TWO TRAPS CAUGHT BY DRIVING RATHER THAN READING.** The twin's sanity probe was the
      literal substring `git status`, which is FALSE against `battery.py`'s
      `["git", "status", "--porcelain"]` -- carried over unchanged it would have refused a
      perfectly good guard. And an `awk` rule without `!inside &&` re-entered on a second
      `def tree_state(`, which the bash predecessor never hit because `^}` fired first; the
      DIFFERENTIAL found that, not the author.
      **The `:76-80` false claim is corrected against the live scope**
      (`scripts/gate-bind.ts:207-208`): `inScope('.ci/rediacc_ci/battery.py')` is TRUE, driven
      via `npx tsx -e`. The no-header decision stands on the real reason -- it is a runner,
      `gate: false`, hand-registered -- not the false one.
      **40 differential failures were cleared by the driver**, in two files the writer was
      forbidden to edit: `.ci/rediacc_ci/tests/test_quality_battery_clean_tree.py` and
      `.ci/rediacc_ci/tests/test_quality_pool_writer_safety.py`, 40 failed -> **84 passed**.
      **THE DELETION IS NOT DONE AND IS NOT THIS BOX'S** -- see W7P5-c, which now carries the
      three blockers this work uncovered.
- [x] **W7P4-Q S batches, 2 writers** The quality-tree cutover -- this is P-A. Six batches of 13.
    (ticked) 2026-09-20T14:35:51Z by d778be9d: 76 of 77 quality gates run from Python: staging_tag_guard cut over in 814893cb7 after the shadow-gate aging fix (ledger holds over 12 trees). The last, autopilot_no_bypass, stays unregistered: door:operator-only, its bypass_actors read needs an org-owner Administration:read grant that no CI credential holds.
      **RE-MEASURED 2026-09-08 from the tree and not from a report: LIVE 75 of 77.**
      **2026-09-20, TWO BLOCKERS FOUND ON THE LAST TWO GATES.** (a) `staging_tag_guard`:
      `assertEquivalent` kept every historical MISMATCH row failing the pair for good, which
      contradicted the module docstring's promise that a fixed port re-earns its licence.
      FIXED in `scripts/lib/shadow-gate.ts`: a disqualified tree id stays refused, but the
      pair ages the mismatch out once K later distinct clean trees exist, with three
      controls (aged out, still-recent stays red, trees before the mismatch do not count);
      `--pair w7p2-stagingtag --assert --k 5` now holds over 12 trees. The cutover of that
      gate is the next step. (b) `autopilot_no_bypass`: `bypass_actors` is readable only with
      Administration:read, which no CI credential holds, so registering the gate turns CI
      deterministically red. Do NOT register it. `door:operator-only`: the missing
      Administration:read grant needs an org owner.
      **COMMITTED 2026-09-08 as `aaba93b29` (81 files, 9268 insertions), operator-authorised
      when asked directly.** Until then the whole cutover sat STAGED in a shared index, where
      any session's pathspecless `git commit` would have swept it; the index is now empty.
      The same commit routes all 81 entry points through `.ci/scripts/quality/_cipath.py`
      instead of 81 byte-identical `sys.path` hops, and repairs
      `check_python_gate_deps.py`, which read `parents[N]` out of each script's own body and
      so reported 69 findings the moment the scripts stopped writing one.
      Batches 1-9 landed, and the two gates that had NO registration to repoint were then
      registered outright rather than left as an estate hole.
      **TWO REMAIN AND NEITHER IS SCHEDULABLE WORK**, which is why this box stays open on
      an external fact rather than on effort:
      * `staging_tag_guard` is excluded for cause -- its shadow ledger is the programme's
        one permanent red, and the ledger is what licences a cutover.
      * `autopilot_no_bypass` refuses without `GITHUB_AUTOPILOT_APP_ID`, an ORGANISATION
        variable no session can set, and it refuses deliberately: "a wrong-or-absent id
        would make this gate pass against nothing". `door:operator-only`.
      **THE THREE-GATE ESTATE HOLE IS CLOSED, and it was worth more than the cutover it
      was found during.** `check-autopilot-no-bypass.sh`, `check-ci-job-aggregation.sh`
      and `check-swallowed-failures.sh` were invoked by NOTHING: no `package.json` key, no
      `manifest.ts` entry, no workflow `run:` line, no wrapper. CI ran their gate TESTS
      and never the gates, so each one's logic was exercised against fixtures while it
      never judged the real repository -- and `check:ci-parity` could not see that,
      because a gate absent from BOTH sides is absent from the comparison. The two that
      exit 0 against this tree went in through a `---- gate ----` header on their ports
      plus ONE driver `gate:bind --write` (6 regions rewritten, nothing dropped, no step
      lost or duplicated), emitting `.github/workflows/ci-quality.yml:775` and `:880`.
      **AN ORDER-EQUIVALENCE DECISION, taken deliberately and recorded because it moves
      the bar:** `check:ci-content-quality`'s port is NOT byte-identical to its twin on
      stdout. The difference is record ORDER only -- corpus 1107 both sides, the six
      finding records equal as a multiset, summary lines identical in place, exit codes
      equal. The twin walks with raw `find`, and I measured that `find` order is NOT
      lexicographic on this tree (367 of 400 sample lines differ from sorted), so the
      twin's order is a property of THIS filesystem and would differ on another machine.
      Demanding byte-identity there demands the port reproduce something irreproducible;
      the port's sorted order is strictly more deterministic. Cut over on
      order-equivalence, with the finding set and corpus proven equal.
      **A NEW TRAP, caught by `check:ci-gate-manifest` and not by any writer:** a gate
      whose `paths:` glob is EXTENSION-SHAPED covered its own file for free while the
      gate was a `.sh`, and stops the moment the leaf becomes a `.py`.
      `check:ci-shell-size` declared `paths: ['**/*.sh']` and the gate reported
      "declares paths but not its own leaf -- editing the gate does not select the
      gate". Every future cutover of such a gate inherits this; add the leaf explicitly. Batch 4 added `go-module-sync`,
      `app-admin-perm`, `subscription-schema`, `mutate-check`, `renet-tiers`,
      `config-migrations`; `staging_tag_guard` was EXCLUDED FOR CAUSE, its ledger being
      the known-permanent red and the ledger being what licences a cutover.
      **A FOURTH TRAP, and it is invisible when it fires:** `test-gate-anti-vacuity.sh`
      pins gates BY PATH, so after a cutover the pin names the twin, the harness keeps
      exercising the `.sh`, keeps PASSING, and silently stops covering what CI runs. Two
      entries were stale (`check-renet-tier-map.sh` from batch 4 and
      `check-renet-types.sh` left behind by batch 3); both repointed with the reason
      recorded in the file. Sweep that list on every cutover wave. Batch 3 cut over `peer-deps`,
      `renet-types`, `cli-contract`, `command-tree`, `account-portal`, `compose-env`.
      **THREE THINGS BATCH 3 PAID FOR, so batch 4 does not:** (a) `gate:bind` reads
      `git ls-files`, so a new entry point must be `git add`-ed or the binder reports a
      green that means nothing about it; (b) the twin's header must come OUT in the same
      change, or the binder produces the mirror-image error, and `needs:` must be copied
      verbatim because a two-import Python entry point INFERS nothing while the bash twin
      got its `needs` free from its own body (`scripts/lib/gate-header.ts:300` strips Python
      docstrings as prose); (c) `check:ci-account-portal` had a HAND-WRITTEN workflow step
      outside any gate-bind region, and the binder only matches a step by NAME
      (`scripts/gate-bind.ts:1749`), never its `run:` line, so it stayed green while CI ran the
      twin. `check-ci-parity` is what catches that, and the edit is manual.
      **One accepted divergence:** `command-tree`'s twin prints U+2014 in one stale
      message; the port cannot reproduce it because CLAUDE.md forbids em dashes, so the
      failing path differs by that character and the clean path is byte-identical. Cut
      over deliberately, recorded in the port's docstring. The honest probe is registered `.py` entry
      points under `.ci/scripts/quality/` that import a port AND are named in `gates.lock.json`;
      `grep -c rediacc_ci/quality scripts/ci-runner/gates.lock.json` reads 1 and is NOT this
      number -- the lock names entry points, and that single hit is one `leaves` path.
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
- [x] **W7P4-W C, 2 writers, after W7P4-Q** Flip 162 distinct scripts / 275 call sites (count only `run:` and `with:` keys; the 215 / 348 below counted comments).
    (ticked) 2026-09-20T21:27:28Z by d778be9d: 160 to 39 distinct .ci .sh paths under run:/with: in this branch (P4a 80, remainder 25, P4b 4 families); every removal has fresh K=5 ledgers or an existing licence; each remaining path is named with the reason this host cannot flip it (frozen, sourced, needs root/VM/fleet, no npm key, spawned by path)
      **Creates no new `.sh` files** (see P-C: a new shim is illegal). Call sites flip straight to
      `npm run <id>` or `python3 -m`; the bash is retired in place.
      **Decomposition:** two boxes. **P4a** is the call sites whose script already has a Python
      port (61 paths on the earlier 215-path count; re-measure on the 162 before staffing), and
      **P4b** is the rest, which has no port and is almost exactly the P-C backlog plus
      deploy/release (154 paths on the earlier count: deploy 21, release 21, test 18, ci 15,
      autopilot 14, build 14, infra 9, private 9, security 7, housekeeping 6, quality 6, review 4).
      **Acceptance:** the set of `.ci/**/*.sh` paths in `.github/workflows/**` strictly shrinks,
      printed by name; every removed path has a lock entry whose `leaves` name the replacement
      and whose `ci.step` matches the emitted step. Both directions.
      **DESIGN 2026-09-08, resolved 2026-09-20.** The dependency named `PRE-B2` did not exist
      (the only `PRE-*` boxes are PRE-A0 and PRE-A1); the real one is W7P4-Q, because a flip
      before its cutover would repoint workflows at gates whose ports are not registered. The
      acceptance was also false-positive and false-negative prone: 31 of 290 occurrences were
      COMMENT lines and 10 distinct paths appeared only in comments, so the surface is counted
      only under a `run:`/`with:` key, which measures 162 distinct paths / 275 call sites.
      Partition writers by WORKFLOW FILE, not by script -- the workflows are the contended,
      driver-only resource. P4a stays unstaffed until W7P4-Q's cutover lands.
      **P4a DONE 2026-09-20 in `c5cb6e8a6`.** Measured on `run:`/`with:` only: 160 distinct
      paths / 273 sites; 106 paths have a port licensed at K=5. 80 paths (120 sites) flipped to
      `PYTHONPATH=.ci python3 -m rediacc_ci.<module>` (the ports carry no sys.path hop, so the
      bare-path form fails with ModuleNotFoundError); the set shrank 160 -> 80 with none added.
      **23 of the flipped paths are on the W7P5-a real-run blocklist**: licensed by dry-run
      parity only, bash still in the tree, each site reverts by restoring its old `run:` line.
      **Left of the licensed 106 (26):** 15 in `autopilot.yml` (runner-temp invocations, pinned
      by `check-autopilot-workflow-invariants.sh`), 2 in `claude-review-reusable.yml`, 9 inside
      `gate-bind` emitter regions. **P4b: 54 paths have no licensed port.**
      **REMAINDER DONE 2026-09-20 in `70e6ffe24`:** autopilot.yml 15 paths / 25 sites (the
      model job runs the harness copy with `python3 -P`, because `-m` puts the working directory
      ahead of PYTHONPATH and that directory holds PR-authored files; a new plant-verified
      invariant guards the flag), one claude-review site, and the nine gate-bind region steps
      (lane by lane, `dropped` empty). Two gates registered as bare paths with no npm key
      (`test:install-script`, `test:write-once-guard`) keep their bash target, because the
      binder refuses a header `run:` without a package.json script. **57 `.sh` paths remain
      under `run:`/`with:`; the licensed ones are done, what is left is P4b (no port).**
      **P4b DONE 2026-09-20 WHERE THIS HOST CAN EXERCISE IT (`7135275f4`, `46053f61a`, `654acbb76`,
      `084be4cd5`): 20 further scripts ported or re-licensed with fresh K=5 ledgers (`w7p4b-*`,
      all recorded from scratch repos with recording stubs), 20 sites flipped per family, five
      gates and two closure derivations repaired on the way.** Measured at the end: **39 distinct
      `.ci/**/*.sh` paths remain under `run:`/`with:`, from 160 at the start of P4a**, and each
      remaining family has a stated reason. 13 `.ci/breakpoint/scripts/*` are hash-frozen by
      `MANIFEST.sha256`, so a port is a change to the freeze and its alignment gate, not a flip.
      `bootstrap.sh`, `config/constants.sh` and `lib/toolchain.sh` are SOURCED libraries, which a
      module call cannot replace. Five `private/` runners (`license-e2e`, `renet-csi-sanity`,
      `renet-ebpf-e2e`, `renet-integration`, `renet-root-tests`) need root, eBPF or a VM. Ten
      `.ci/scripts/test/*` runners need a fleet, installs or docker builds, and two of them
      (`test-install-script`, `test-write-once-guard`) are registered as bare paths with no
      npm key, which the binder does not allow a header `run:` for. Four `test/gates/*` are gate
      tests whose flip is W7P5's twin-retirement, `claude-review-gate` and `epic-context` are a
      scratch-wrapper ledger and a `Bash(...)` permission pattern, and `tutorials/run-sequence`
      and `profiler/sampler-linux.sh` are spawned by path from a composite action.
- [ ] **W7P5-a S** `deploy/` 27 + `release/` 21 = **48 files, 5,440 lines**, 46 workflow call
      sites, zero Python, zero ledgers. Golden dry-run parity plus **one real run each**, K=5
      ledger before any deletion. Each specimen its own committed git repo; new side under
      `PYTHONDONTWRITEBYTECODE=1` (`__pycache__` dirties the tree before `treeIdentity`).
      **Acceptance:** every path has either a ledger asserting `equivalence holds` at K=5 or an
      allowlist entry with a BLOCKER. No third state.
      **STARTED 2026-09-09, 3 of 48 AT THE BAR, AND THE ACCEPTANCE IS HONESTLY NOT MET.**
      The writer said so rather than manufacturing the third state: 3 done, **6 merely
      unstarted** (marked in `.ci/shadow/w7p5a-status.json` as "NOT a BLOCKER, do not
      allowlist this as one"), and 39 whose BLOCKER covers the REAL-RUN clause only -- the
      dry-run parity port is separate work that stubbed tool binaries could reach without
      touching production. Fabricating 45 ledgers would have satisfied the letter of "no
      third state" and destroyed its point.
      **Done at the bar, each with a K=5 ledger AND a permanent pytest differential** (the
      ledger is one-time; the differential is what catches a later divergence):
      `resolve-account-deploy-config`, `upload-media-to-r2`, `decide-release-mode`. Verified
      by the driver: 5 rows in each `.ci/shadow/w7p5a-*.observations.jsonl`, and 12/12 tests
      pass. A real defect was planted in each port and watched red, then restored green.
      **THE BOX'S 46 WORKFLOW CALL SITES IS WRONG: 43.** Four of the 47 raw grep hits are
      comments. And **5 of the 48 scripts have ZERO direct workflow call sites** -- reached
      only by sibling scripts or cross-repo callers -- while `deploy-edge.sh` is reachable
      solely through `.github/workflows/cd-deploy-worker.yml:155`'s `${{ steps.target.outputs.script }}`
      indirection, which no literal-path grep can see. 48 files / 5,440 lines both confirmed.
      **A HARNESS BUG, NOT A PORT BUG, FOUND AND FIXED:** `GITHUB_OUTPUT=/dev/stdout` -- the
      twins' own documented "run locally" usage -- fails with `ENXIO` under `shadow-gate.ts`,
      pytest's `subprocess.run` and Node's `spawnSync`, because reopening `/dev/stdout` fails
      when fd 1 is an anonymous pipe rather than a tty. Reproduced minimally. The ledger and
      test commands now write to a real temp file.
      **NEXT INCREMENT IS THE 6 PENDING**, which are the same shape as the 3 done and are
      blocked by nothing: `resolve-www-deploy-target.sh`, `backfill-write-sentinel.sh` (the
      safest, DRY_RUN-native), `check-soak-period.sh`, `deployment-summary.sh`,
      `resolve-backfill-commit.sh`, `validate-stage-artifacts.sh`.
      **ALL SIX DONE 2026-09-09: W7P5-a is now 9 of 48 at the bar, 39 blocked, ZERO pending.**
      Each of the six has a K=5 ledger (verified: 5 rows apiece) plus a permanent pytest
      differential, 25 new tests, and a planted defect driven red then restored green.
      **How the ledgers were produced is the reusable part.** This checkout is never clean
      and `--record` refuses a dirty tree, so the writer built a DISPOSABLE git repo OUTSIDE
      the checkout, seeded it with the six twins plus `common.sh`, and made five sequential
      commits to mint five distinct clean tree ids -- recording into the real
      `.ci/shadow/` ledgers via `--repo <scratch> --ledger <console>/...`, varying real
      inputs so each pair carries >=2 distinct fingerprints. That is the technique every
      remaining W7P5 ledger needs and it was not written down before.
      **THE BOX STILL DOES NOT MEET ITS ACCEPTANCE, and the gap is PLACEMENT not quality.**
      It requires "a ledger ... or **an allowlist entry** with a BLOCKER. No third state."
      The 39 blocked paths carry BLOCKER-shaped reasons that pass the repo's own
      `allowlist.validate_reason`, but they live in `.ci/shadow/w7p5a-status.json`, which is
      a STATUS FILE, not an allowlist -- nothing validates it in CI and no liveness gate
      checks whether those reasons are still true. A reason in an unchecked file is exactly
      the third state the acceptance forbids, wearing the right clothes.
      **One tree correction:** `deployment-summary.sh` is under `.ci/scripts/release/`, not
      `.ci/scripts/deploy/` as the pending list said. The writer trusted the tree.
      **REGISTERED 2026-09-09: `.ci/policy/.w7p5a-real-run-blocklist`, a genuine
      BLOCKER-gated allowlist through the canonical validator, checked in BOTH DIRECTIONS
      against `.ci/shadow/w7p5a-status.json` -- registered as `check:ci-w7p5a-real-run-blockers`
      in `quality-static`, rc=0: "39 BLOCKER-gated real-run exemption(s) ..., agreeing with
      .ci/shadow/w7p5a-status.json (39 'blocked', 9 ledgered) -- no third state".
      **THE ACCEPTANCE IS NOW GENUINELY MET: 9 ledgered + 39 checked-BLOCKER = 48, no third
      state, and a machine asserts it rather than a status file's prose.** All 39 reasons
      carried verbatim.
      **A driver mistake, found and fixed on the way in:** the gate's own header initially
      sat on the LIBRARY module rather than its entry point, the reverse of every sibling's
      split. `gate-bind` resolves by header location, so the emitted workflow step ran the
      wrong file -- `check:ci-parity` caught it immediately (R3, "step resolves to X and none
      of Y"). Moved, re-verified.
      **A SECOND CLASS FOUND WHILE LANDING IT: `MANUAL_ENTRY_POINTS` in
      `.ci/rediacc_ci/quality/dead_python.py`, previously empty since its last exemption
      graduated, now carries all 9 W7P5-a ports.** Each is invoked by MODULE-NAME STRING from
      its own pytest differential, not by static import, so the scanner's import graph
      cannot see the route -- and it is correctly not a gate either, since the cutover from
      the `.sh` call site is W7P4-W, a separate box. The exemption is CHECKED, not quiet: a
      planted dangling entry reds it, restored green, byte-identical.
      **DRY-RUN PARITY: 7 MORE OF THE 39 CLEARED, 2026-09-09. W7P5-a now 16 of 48 ledgered, 32
      blocked.** `wait-for-preview-worker`, `check-edge-manifest`, `check-stable-manifest`,
      `check-existing-release`, `verify-release-assets`, `resolve-ci-run`,
      `verify-artifact-attestation` -- each a K=5 ledger (5 rows, verified) plus a permanent
      differential, external tool STUBBED (fake `gh`/`curl` on PATH, real `jq`/`git` left
      reachable) so nothing touches production. Allowlist entries for all 7 REMOVED from
      `.ci/policy/.w7p5a-real-run-blocklist` (driver action, since it is a registered gate);
      `check:ci-w7p5a-real-run-blockers` re-verified: "32 BLOCKER-gated real-run
      exemption(s) ..., agreeing with .ci/shadow/w7p5a-status.json (32 'blocked', 16
      ledgered) -- no third state".
      **A path whose dry-run mode still needs real auth to CONSTRUCT a request is correctly
      left blocked, not stubbed past.** The writer's own rule, honoured: 32 of 39 remain
      genuinely unportable this way and none were ruled impossible, just not yet attempted.
      **Two tool traps found and documented, not fixed (outside the writer's grant):**
      `shadow-gate.ts`'s `reachesOutside` check flags any `://` or `/tmp` token in a
      `--old`/`--new` command as an escape, worked around with a wrapper committed INSIDE
      each disposable scratch tree reading its real target from a file rather than the
      command line. And a script whose own anti-vacuity message says "NOTHING was verified"
      collides with the tool's own refusal vocabulary and can never score EQUIVALENT --
      covered by the pytest differential instead.
      **5 more `dead_python.py` `MANUAL_ENTRY_POINTS` entries, not 7** -- 2 of the 7 already
      had a real `mentioned` route via a literal path string in their own test file, and
      adding an exemption there would itself have failed the gate's stale-exemption check.
      The writer caught its own over-scoping before landing it.
      **DRY-RUN PARITY RE-AUDITED AND FOUND ALREADY SATISFIED FOR ALL 32 REMAINING
      BLOCKED PATHS, 2026-09-14.** Not new work: box W7P6 independently ported every one
      of them as a standalone Python module under `.ci/rediacc_ci/deploy/` or
      `.ci/rediacc_ci/release/`, each with its own permanent pytest differential and its
      own K=5 ledger under the `w7p6-<slug>` naming rather than `w7p5a-<slug>`, which is
      why this box never saw them. This wave VERIFIED that claim rather than inheriting
      it, and rewrote the 32 `note` fields in `.ci/shadow/w7p5a-status.json` to say what
      is actually left.
      **What was verified, all four legs, on the real tree:** (1) the port, the
      differential and the ledger exist for all 32; (2) `pytest -q` over the 32
      differential files together -- **748 tests, 748 passed**, 4m05s; (3)
      `shadow-gate.ts --pair w7p6-<slug> --assert --k 5` rc=0 for all 32, every ledger
      row EQUIVALENT, 5 distinct clean trees each (`deploy-proxy` has 6) and at least 3
      distinct fingerprints per pair; (4) every differential's docstring and test bodies
      READ, not merely run green. The assert tool's own controls were driven too: `--k 6`
      on a 5-tree pair reds, and a nonexistent pair refuses rather than passing empty.
      **The coverage is genuine dry-run parity, not a smoke test.** Every one of the 32
      drives the bash twin and the Python port SIDE BY SIDE through a `run_both`/`drive`
      helper over real scenarios -- happy path, failure arms, refusals, retry budgets,
      partial failures -- comparing exit code, stdout and stderr separately and, where
      the streams are a weak claim, the recorded CALL LOG and the produced ARTIFACT (the
      generated `import.sql`, the homebrew formula, the uploaded sentinel bytes, the
      `GITHUB_STEP_SUMMARY` block) as well. Per-file test-function counts run 11 to 48,
      expanding through parametrisation to the 748 collected. External
      tooling is a recording fake first on PATH in every case (`curl`, `aws`, `gh`,
      `npx`, `npm`, `docker`, `sqlite3`, `sleep`, `git`), several of them PROVING the
      shadowing rather than assuming it. Nothing reaches Cloudflare, GitHub, R2, D1 or
      GHCR. The three subjects that would mutate a real tree if run naively --
      `advance-contract-floor`, `tag-submodules`, `update-homebrew-tap` -- each build a
      throwaway fixture root per side with a LOCAL bare git remote, and
      `cleanup-channel-docker-tags` drops a recording stub over the GHCR deleter it
      shells out to. These differentials sit under `.ci/rediacc_ci/tests/`, so
      `check:ci-pytest` collects them on every sweep: the parity claim is ENFORCED, not
      one-time.
      **The 32, by group. ZERO were found inadequate.** deploy (23): `cf-purge-urls`,
      `clone-d1`, `delete-r2-channel`, `deploy-account`, `deploy-edge`, `deploy-proxy`,
      `deploy-www`, `promote-docker-to-stable-hotfix`, `promote-r2-to-stable`,
      `promote-r2-to-stable-hotfix`, `purge-media-cache`, `set-account-worker-secrets`,
      `set-preview-worker-secrets`, `set-www-worker-secrets`, `simulate-promotion`,
      `sync-media-from-r2`, `sync-media-to-r2`, `test-d1-migrations`,
      `upload-repos-to-r2`, `upload-to-r2`, `verify-edge-endpoints`,
      `verify-stable-endpoints`, `write-release-sentinel`. release (9):
      `advance-contract-floor`, `assert-artifact-version`, `assert-edge-tag-exists`,
      `cleanup-channel-docker-tags`, `create-github-release`, `mark-production`,
      `reprobe-r2-sentinel`, `tag-submodules`, `update-homebrew-tap`.
      **THE BOUNDARY THIS WAVE DID NOT CROSS, deliberately.** The other half of the
      acceptance, "one real run each", is UNMET for all 32 and stays unmet. Every one of
      them acts on real production Cloudflare Workers, GitHub Releases and tags, R2
      buckets, D1 databases or GHCR, so a real run is an OPERATOR-AUTHORIZATION matter
      and no session should take it unilaterally. No script in the 32 was executed
      outside a stubbed fixture during this wave. All 32 keep `"status": "blocked"`, no
      entry was removed, and `.ci/policy/.w7p5a-real-run-blocklist` was not touched.
      **What the notes now say, and the one thing they cannot fix.** Each of the 32
      `note` fields now names its port module, its differential with a test count, its
      `w7p6-<slug>` ledger with row and tree counts, the isolation mechanism, and the
      operator-only real-run gap. The `blocker` field was left byte-identical, because it
      is carried VERBATIM in `.ci/policy/.w7p5a-real-run-blocklist`, a registered-gate
      file outside this wave's grant -- and it now holds one STALE sentence in all 32
      entries: "The bash-vs-python golden dry-run parity ledger for this path is a
      SEPARATE, not-yet-done piece of work". That is false as of this wave.
      **DRIVER ACTION OWED:** reword that sentence in the allowlist, and mirror the
      wording into `blocker` here, so the CHECKED source of truth stops claiming work
      that is done. Until then the status file's `note` is the accurate half and the
      allowlist's `blocker` is stale prose that still validates.
      **Gate evidence:** `check:ci-w7p5a-real-run-blockers` rc=0 after the edit ("32
      BLOCKER-gated real-run exemption(s) ..., agreeing with
      .ci/shadow/w7p5a-status.json (32 'blocked', 16 ledgered) -- no third state"), its
      `--selftest` 13/13 PASS, and a REAL-TREE control rather than a fixture one:
      flipping a single blocked entry to `ledger` in the live status file drove the gate
      red on the stale-entry finding, after which the file was restored byte-identical
      (sha256 verified) and re-run green.
      **DRIVER ACTION TAKEN.** Reworded all 24 BLOCKER comments in `.ci/policy/.w7p5a-
      real-run-blocklist` (covering all 32 blocked paths -- several share one comment)
      from "is a SEPARATE, not-yet-done piece of work" to "is DONE (verified 2026-09-14):
      W7P6 independently ported it... external tools stubbed throughout so nothing
      touches production", and mirrored the identical wording into `blocker` on all 32
      entries in `.ci/shadow/w7p5a-status.json`, so `note` and `blocker` now agree
      verbatim. `check:ci-w7p5a-real-run-blockers` re-verified rc=0 after both edits.
      **Also fixed, found while re-running `check_plan_citations.py` after this box's own
      wave landed (12 gate-name line-wraps + 8 fileline citations missing a directory
      prefix, all in THIS document's own added text, none in this box specifically):**
      merged every backtick-quoted gate name broken across a line-wrap back onto one
      line (a real citation, misread as dead only because of where the wrap fell), and
      added the correct repo-relative prefix to 8 bare-basename fileline citations
      (`.ci/scripts/deploy/`, `.ci/scripts/ci/`, `.ci/scripts/lib/`, `.github/workflows/`)
      -- catching one driver mistake on the way in (`promote-r2-to-stable.sh` is under
      `deploy/`, not `release/` as first typed; caught by the file genuinely not
      existing at the wrong path, fixed before landing). `check_plan_citations.py` is
      down to its one remaining, already-known finding: the status TABLE near the top of
      this document names the find-port shim at its old location and line -- left for
      the concurrent W7P5-b writer's own deletion to settle, since editing it now would
      race that writer's file.
      **REAL RUNS DONE FROM THIS HOST 2026-09-21, the credential-free rows.** `verify-stable-endpoints.sh` rc=0
      against production (install scripts baked to stable, worker fingerprints, R2 copies, three regional health
      checks). `verify-edge-endpoints.sh` with VERSION=1.3.12, the live edge version, rc=0 (footer v1.3.12, latest.json
      match, three edge health checks). `purge-media-cache.sh` without credentials refuses with rc=1 and
      `cf-purge-urls.sh` skips with a warning, rc=0; neither can purge without a Cloudflare token, so their real
      runs stay `door:operator-only` with the other credentialed rows.
      **RUNBOOK ROWS RE-DERIVED 2026-09-21, ZERO DRIFT.** The 32 table rows equal the 32 entries of
      `.ci/policy/.w7p5a-real-run-blocklist` in both directions, and every workflow site (searched by script
      stem in hyphen and underscore form under `.github/workflows`) still matches its row, including the rows
      that read `no workflow site`.
      **CORRECTED 2026-09-22: the credential claim below was wrong.** `door:operator-only` was carried for the
      wrong reason. `BWS_ACCESS_TOKEN` sits in `private/account/.env` (never exported into the shell by default,
      which is what made a `env | grep` look empty); sourced, `bws secret list` resolves all 58 store secrets,
      covering `CLOUDFLARE_API_TOKEN` and the R2 key pairs used below. `CLOUDFLARE_ACCOUNT_ID` is not a secret at
      all -- it is the `vars.CLOUDFLARE_ACCOUNT_ID` GitHub Actions variable, fetched with `gh api
      repos/rediacc/console/actions/variables/CLOUDFLARE_ACCOUNT_ID`. `gh` is already authenticated on this host
      with `repo`, `workflow` and `write:packages` scopes, covering every `GH_TOKEN`, git-push and GHCR-registry
      row. So every credential column this table names is retrievable on this host today; this box is not
      blocked on credential availability. What remains a genuine operator call is DIFFERENT: several rows are
      live production writes with real blast radius (a GitHub release, a Docker/R2 promotion to stable, an
      overwrite of a live Worker's secrets, a submodule tag push) rather than a credential gap, and that is an
      authorization question, asked separately below.
      AUDIT: DONE 2026-09-23 (audit): this box re-measured against the tree rather than against its
      own prose, and three of its standing numbers have moved. **The corpus is 41 files / 4,931
      lines, not 48 / 5,440**: `.ci/scripts/deploy/` holds 26 `.sh` and `.ci/scripts/release/` 15,
      because seven of the 48 twins are already DELETED (commits `0bb1a4c15`, `2e50af60a`) --
      `release/decide-release-mode.sh`, `deploy/resolve-www-deploy-target.sh`,
      `release/backfill-write-sentinel.sh`, `release/check-soak-period.sh`,
      `release/deployment-summary.sh`, `release/resolve-backfill-commit.sh` and
      `release/validate-stage-artifacts.sh`, which are seven of the nine real-run-confirmed rows.
      `.ci/shadow/w7p5a-status.json` still carries all 48 rows, correctly, as the box's subject
      register rather than as a file listing.
      **Every one of the 48 rows checked against its artifact, not against its note.** The 16
      `status: "ledger"` rows each hold 5 ledger lines over 5 distinct tree ids, every verdict
      `EQUIVALENT`. The 32 `blocked` rows each hold a port under `.ci/rediacc_ci/deploy/` or
      `.ci/rediacc_ci/release/`, a `w7p6-<slug>` K=5 `EQUIVALENT` ledger (`deploy-proxy` at 6 rows)
      and a pytest differential. Nothing in the 48 is unstarted, and
      `npm run check:ci-w7p5a-real-run-blockers` is rc=0 on the current tree.
      **THE FULL-BAR COUNT IS 9 OF 48, and the box names neither of the two mechanisms that say
      so.** `.ci/policy/.w7p5a-real-run-leg-blocklist` is a SECOND BLOCKER register, 7 entries, for
      the real-run leg of a path whose dry-run parity is already ledgered under this box's own
      name; and 13 of the 32 `blocked` rows now carry a `dry_run_pair`/`dry_run_ledger` re-driven
      under the `w7p5a-` namespace, enforced by
      `.ci/rediacc_ci/tests/test_w7p5a_dry_run_ledgers.py`. The gate prints the split this prose
      does not: 32 blocked, 16 ledgered, of which "9 have their real-run leg confirmed and 7 are
      leg-blocked".
      **SIX REAL RUNS DRIVEN 2026-09-23, both sides, streams compared by hand, nothing recorded
      into the ledgers (that is a driver action, not an audit's).**
      `.ci/scripts/release/check-edge-manifest.sh`, `.ci/scripts/release/check-stable-manifest.sh`
      (EDGE_VERSION=1.3.12), `.ci/scripts/release/resolve-ci-run.sh`,
      `.ci/scripts/release/verify-release-assets.sh` (VERSION=v1.3.12),
      `.ci/scripts/deploy/verify-stable-endpoints.sh` and
      `.ci/scripts/deploy/verify-edge-endpoints.sh` (VERSION=1.3.12) each ran rc=0 against real
      production and the real GitHub API, and each agreed with its Python port on stdout, stderr
      and `GITHUB_OUTPUT` byte-for-byte. Four of the six are leg-blocklisted and two are on the 32;
      what blocks all six is authorization, not capability.
      **AND THE SEVENTH REAL RUN FOUND A DIVERGENCE THE STUBBED LEDGER CANNOT SEE.**
      `.ci/scripts/release/check-existing-release.sh` and
      `.ci/rediacc_ci/release/check_existing_release.py` both exit 1 when `git fetch --tags
      --quiet` fails, but the twin writes nothing on either stream while the port emits a ten-line
      `subprocess.CalledProcessError` traceback: `.ci/rediacc_ci/release/check_existing_release.py:33`
      passes `check=True` with no handler.
      `.ci/rediacc_ci/tests/test_release_check_existing_release.py` carries four cases and every
      one of them points `origin` at a working local bare repo, so the failing-fetch arm is never
      driven. That is the `bws-env.sh` traceback class again in the opposite direction, and it is
      precisely what the "one real run each" clause exists to catch.
      **REAL-RUN RUNBOOK 2026-09-20 (credential claim above superseded).** The 32 blocklisted scripts each need
      one real run before their bash twin may be deleted. The table lists, per script, the external tools its
      code calls, the credential that implies, and the workflow step to copy the command from (the workflow step
      is the exact invocation; run it with the real inputs, then record the observable in the script's status
      row). It was derived by reading each script, so confirm the credential against the script before running
      it. The dry-run ledgers do not substitute.
      | Script (under .ci/scripts/) | External tools | Credential | Workflow step |
      |---|---|---|---|
      | `deploy/cf-purge-urls.sh` | curl | none unless the URL is private | no workflow site |
      | `deploy/clone-d1.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | no workflow site |
      | `deploy/delete-r2-channel.sh` | aws | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint | .github/workflows/cleanup-r2-staging.yml:52 |
      | `deploy/deploy-account.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | .github/workflows/cd-deploy-account.yml:273 |
      | `deploy/deploy-edge.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | no workflow site |
      | `deploy/deploy-proxy.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | no workflow site |
      | `deploy/deploy-www.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | .github/workflows/ci.yml:1407 |
      | `deploy/promote-docker-to-stable-hotfix.sh` | docker buildx | registry login (GHCR/Docker Hub) | .github/workflows/cd-v2.yml:388 |
      | `deploy/promote-r2-to-stable-hotfix.sh` | aws | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint | .github/workflows/cd-v2.yml:384 |
      | `deploy/promote-r2-to-stable.sh` | aws | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint | .github/workflows/promote-stable.yml:120 |
      | `deploy/purge-media-cache.sh` | curl | none unless the URL is private | no workflow site |
      | `deploy/set-account-worker-secrets.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | .github/workflows/cd-deploy-account.yml:335 |
      | `deploy/set-preview-worker-secrets.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | .github/workflows/ci.yml:1436 |
      | `deploy/set-www-worker-secrets.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | .github/workflows/cd-deploy-worker.yml:210 |
      | `deploy/simulate-promotion.sh` | aws | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint | .github/workflows/ci.yml:1670 |
      | `deploy/sync-media-from-r2.sh` | aws | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint | .github/workflows/ci-quality.yml:1825 |
      | `deploy/sync-media-to-r2.sh` | aws, curl | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint; none unless the URL is private | no workflow site |
      | `deploy/test-d1-migrations.sh` | wrangler | CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID | .github/workflows/ct-tests.yml:187 |
      | `deploy/upload-repos-to-r2.sh` | aws | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint | .github/workflows/cd-stage.yml:342 |
      | `deploy/upload-to-r2.sh` | aws | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint | .github/workflows/cd-stage.yml:323 |
      | `deploy/verify-edge-endpoints.sh` | curl | none unless the URL is private | .github/workflows/cd-v2.yml:553 |
      | `deploy/verify-stable-endpoints.sh` | curl | none unless the URL is private | .github/workflows/promote-stable.yml:220 |
      | `deploy/write-release-sentinel.sh` | aws | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint | .github/workflows/ci.yml:1892 |
      | `release/advance-contract-floor.sh` | git push | push credential for the target repo | .github/workflows/cd-v2.yml:702 |
      | `release/assert-artifact-version.sh` | gh | GH_TOKEN (scope as the calling job grants) | .github/workflows/cd-v2.yml:216 |
      | `release/assert-edge-tag-exists.sh` | aws, gh | R2 key pair (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY) + R2 endpoint; GH_TOKEN (scope as the calling job grants) | .github/workflows/promote-stable.yml:73 |
      | `release/cleanup-channel-docker-tags.sh` | none found | none | .github/workflows/cd-v2.yml:395 |
      | `release/create-github-release.sh` | gh | GH_TOKEN (scope as the calling job grants) | .github/workflows/cd-v2.yml:712 |
      | `release/mark-production.sh` | gh | GH_TOKEN (scope as the calling job grants) | .github/workflows/promote-stable.yml:228 |
      | `release/reprobe-r2-sentinel.sh` | none found | none | .github/workflows/backfill-release-sentinel.yml:182 |
      | `release/tag-submodules.sh` | git push | push credential for the target repo | .github/workflows/cd-v2.yml:673 |
      | `release/update-homebrew-tap.sh` | curl, git push | none unless the URL is private; push credential for the target repo | .github/workflows/cd-v2.yml:680 |
- [x] **W7P5-b S, the true long pole** The 13 real bash libs, **6,840 lines**. `common.sh` has
      **251 sourcers** -- the highest fan-in file in the programme. Order by fan-in ascending:
      `gate-controls` (41), `bws-env` (111), `emit-advisory` (218), `service` (225),
      `blocker-validator` (237), `release-age` (237), `toolchain` (466),
      `release-state-validator` (496), `common` (772, last). `local-common.sh` is deleted only
      after W6's quality lane and W8's retarget, per the arbitration table.
      **Note:** `age-check.sh` and `find-port.sh` can never be promoted to `shim:` -- they must be
      DELETED, retargeting their 17 and 14 callers. A shim is a delay, not an exit.
      **FIRST WAVE 2026-09-09/10: 4 of the 9 named libs ported** (`gate-controls`, `bws-env`,
      `emit-advisory`, `service`), each as the library itself (or, for `service.sh`, the
      Docker-free half -- `service_start`/`service_stop` explicitly NOT ported, documented in
      the docstring). K=5 ledgers each (5 rows, 5 trees, 5 fingerprints), 18/44/22/30
      differential tests respectively, all restored clean after their planted defects.
      **The plan's own fan-in column is WRONG -- it is a LINE COUNT, not a sourcer count.**
      Re-derived directly (`grep -rlP` against real `source .../lib/x.sh` call sites, spaces
      and all): `gate-controls` has 4 real sourcers (not 41), `bws-env` has **0** (not 111),
      `emit-advisory` has 4 direct + a transitive set through `blocker-validator.sh` (not
      218), `service` has 1 (not 225). `common.sh`'s "251" is separately wrong too: 209 files
      source it, not 251. Nothing downstream should quote the plan's numbers as fan-in;
      re-derive before relying on them.
      **`bws-env.sh` doesn't fit the shim pattern at all** -- it resolves secrets by
      `export`ing into the CALLING shell, which a child process cannot do, and has **zero
      real sourcers** today, so the port took the free route (no `export` verb, a test pins
      that it never grows one) rather than forcing an eval-emitter against the twin's own
      documented rule against exactly that.
      **Three real bugs found in twins, reproduced not fixed** (outside the writer's file
      ownership): `bws-env.sh` leaks two full Python tracebacks when `bws` returns
      non-JSON output instead of the intended one-line refusal; `service.sh`'s
      `service_status` aborts silently mid-output when the state file is missing either
      `port=` or `started=` (bare `grep | cut` under `errexit`+`pipefail`); `service.sh`'s
      data stream is coloured while its log stream isn't (an ungated vs tty-gated `COLOR_*`
      mismatch), and it calls `check_docker` without defining or sourcing it, so the library
      cannot run standalone in a fresh shell. All three pinned in tests, none touched.
      **One `check:ci-python-env-registry` fragment owed to the driver, attempted and
      currently BLOCKED by peer uncommitted files, not applied.** The 7 name:cred pairs
      (`advisory.py:CI`, `bws_env.py:{BWS_ACCESS_TOKEN,BWS_BIN,BWS_ENV_ROOT,PATH}`,
      `service.py:{CONSOLE_ROOT_DIR,SERVICE_STATUS_NOW}`) are real and correct, but
      `--write-baseline` on this gate refuses unless EVERY currently-new pair in the whole
      working tree is named on the command line at once (unlike the language-policy
      baseline's ADDED=0-against-a-snapshot check, this one has no per-file scoping) --
      driver-verified live: naming only these 7 was refused with 22 more pairs pending,
      all in other sessions' untracked, unverified files (`.ci/rediacc_ci/tests/gates/
      test_gate_*.py:PATH`, `.claude/rediacc_hooks/tests/*`, `pool_writer_safety.py`,
      `media_verify_ext.py`). Naming those blind would bank unverified peer reads into a
      driver-only file. Re-attempt once the tree is otherwise clean of other sessions'
      pending new-env-reads, or once each peer's addition is independently verified.
      **APPLIED, verified live 2026-09-15 -- not attempted in this pass, found already
      done.** `check:ci-python-env-registry` is rc=0 today and `.ci/config/python-env-registry.json`
      already carries exactly the 7 pairs this fragment named (`advisory.py: CI`;
      `bws_env.py: BWS_ACCESS_TOKEN, BWS_BIN, BWS_ENV_ROOT, PATH`; `service.py:
      CONSOLE_ROOT_DIR, SERVICE_STATUS_NOW`), byte-for-byte. Someone (another session or
      the babysitter) landed it since; this note closes the loop rather than leaving the
      box's own text implying it is still blocked.
      **SECOND WAVE 2026-09-10: 2 more libs ported, 6 of 9 named libs done.**
      `blocker-validator.sh` -> `core/blocker_validator.py` (8 real sourcers, confirmed) and
      `release-age.sh` -> `core/release_age.py` (**2 real sourcers, not 237** -- another
      plan-number-was-a-line-count case). Driver-verified directly: both modules exist,
      123/123 new tests pass (72+51), both ledgers at K=5, dead-python/language-policy clean.
      **A pre-existing duplicate found, not repointed**: `.ci/rediacc_ci/quality/go_deps.py:300`
      already carries its own inlined `ReleaseAge` shim, differing from the twin in two
      documented ways (a dropped `window` parameter, a different probe cwd) -- outside this
      writer's ownership, named for a later cutover decision.
      **Two more real bugs found in twins, reproduced not fixed:**
      `blocker-validator.sh`'s anti-vacuity check is DEAD CODE (a bash here-string always
      appends a trailing newline, so the "zero frames" branch it guards against is
      unreachable -- verified live) and `release-age.sh`'s runner-memo comment is wrong: the
      cache variable is assigned inside a command-substitution subshell and never persists,
      so every call re-probes the runner (measured: 12 node starts across 5 epochs instead of
      1, ~1.7x wall-clock cost in `audit.sh`/`check-go-deps.sh`, both hot per-dependency
      paths). Neither is security-relevant; both pinned in tests rather than fixed (`.ci/scripts/lib/`
      is invariant 5, outside writer ownership). `release-age.sh` also fails OPEN (not
      closed, as its own comment claims) on an unvalidated numeric-with-suffix `now` value --
      currently LATENT since both call sites always pass a clean `date +%s`, pinned rather
      than exploitable today.
      **A SECOND, more serious git-tree incident this session, independently driver-verified
      as fully repaired -- but its claimed root-cause mechanism is REFUTED, correcting the
      record rather than propagating it.** A scratch-repo script's `cd "$L"` failed (directory
      never created because an earlier invocation was blocked by the pre-bash commit hook
      first), and the following `git add -A -- . && git commit` ran in the real repo root,
      committing **127 files** of the whole shared 0906-1 tree as commit `784e0c1c` ("seed").
      The writer attributed this to "`set -e` does not abort after a failed `cd`", demonstrated
      via three SEPARATE interactive command lines (each its own shell process, so of course
      `set -e` from line 1 didn't bind line 2) -- **the driver re-ran the identical claim as one
      real `bash -c '...'` script and `set -e` correctly aborted immediately on the failed
      `cd`, exit 1, the echo never printed.** So the actual mechanism that let the commit reach
      the real repo is still UNCONFIRMED (candidates: the failing `cd` was inside a command
      substitution or `local`/`declare` assignment, whose own exit status can mask an inner
      failure under `set -e` -- a real, different, well-documented bash trap -- or the script
      never had `set -e` on that code path at all). Do not cite "`set -e` doesn't abort after
      `cd`" as a lesson; it is false as stated. Writer caught the actual incident and repaired
      with `git reset --mixed HEAD~1` (never `checkout/restore/stash/clean`), confirmed
      nothing pushed. **Driver independently re-verified from scratch, not taken on the
      writer's word**: `git merge-base --is-ancestor 784e0c1c... HEAD` correctly fails (not
      an ancestor); diffed the stray commit's full file list against current
      `git status` and found zero actual content loss (the apparent "missing" 38 files were
      only git collapsing untracked directories into one `?? dir/` line, not lost files --
      every one confirmed present on disk); spot-checked 4 unrelated tracked files
      byte-for-byte identical between the stray commit and the current working tree. The
      repair is clean.
      **THIRD WAVE 2026-09-10: 2 more libs ported, 8 of 9 named libs done.**
      `toolchain.sh` -> `core/toolchain.py` (**6 real sourcers, not 466** -- extended an
      existing W6P2 port that only covered load/compare) and `release-state-validator.sh` ->
      `core/release_state_validator.py` (**11 real sourcers, not 496**, and more than the
      twin's own header claims 5). Driver-verified directly: both modules exist, 512/512 new
      tests pass (148+364), both ledgers at K=5, dead-python/language-policy clean, no stray
      commits, git status scoped exactly to the claimed files.
      **A consequential, quantified defect (DRIVER TRIAGE): `toolchain.sh --verify` cannot
      fail.** The dispatch block has no `exit` in the `--report`/`--verify`/`--env` arms, so
      the script always exits 0 regardless of what the underlying check function returns.
      `--verify` itself has zero call sites today (harmless), but **`--env` has two LIVE call
      sites** (`.github/workflows/ci-quality.yml:171,1897`, both `>> "$GITHUB_ENV"`) --
      verified live: with no pins file, exit 0 and zero bytes appended to `$GITHUB_ENV`,
      silently green. The underlying function is correct on both sides; only the dispatch
      wrapper is broken. Port does NOT reproduce it (`core.toolchain verify` exits 1
      correctly) -- pinned both ways in tests. Two more pre-existing-comment / narrow-
      blast-radius defects found and pinned, not fixed (twin is invariant 5, outside writer
      ownership).
      **One duplicate found in `release-state-validator.sh`'s port, correctly not
      repointed**: `.ci/rediacc_ci/quality/release_state.py` already carries the assertion
      half under its own K=5 ledger; the new port adds the four live-probe functions the
      assertion half never had. **One genuinely dangerous-if-triggered finding**: a probe
      that fails OPEN (empty vs unreachable conflated) feeds a REGISTERED BLOCKER gate, but
      is currently saved by a tracked ratchet floor file -- verified live both ways (deleting
      the floor file flips the gate from a correct red to a false green). Pinned in tests
      including the ratchet-file-must-exist assertion.
      **FOURTH WAVE 2026-09-10: `common.sh` closed out. All 9 of 9 named libs done.**
      Driver-verified directly: both new modules exist, 177/177 new tests pass (86+91),
      both ledgers at K=5, bash twin confirmed byte-untouched, no stray commit (HEAD stayed
      `1a148adeb` throughout), dead-python/language-policy clean, git status scoped exactly.
      **`common.sh` turned out to be seven libraries stacked in one file, five already
      ported under other names** (`log.py`, `paths.py`, `proc.py`, `core/ghx.py`, and
      `core/platform.py` for `detect_os`/`detect_arch` -- DELIBERATELY REFUSED there because
      `common.sh`'s spelling is a third, fail-open variant, so it lives here instead,
      correctly). Ported this wave: the refuse-early half (`require_*`, `parse_args`,
      `detect_os`/`arch`, etc., new `core/common.py`) and the review-budget half (new
      `core/review_budget.py`). Deferred with reasons: `r2_count_objects` (no `aws` binary
      on this sandbox to differentially prove it against).
      **A live, merge-blocking-relevant defect, DRIVER RULING NEEDED (not yet fixed,
      finding recorded in the worklist).** `review_spend_total` -- the numerator of the
      review-cost cap -- swallows a `gh` API failure (rate-limit, or `GITHUB_REPOSITORY`
      unset under `set -u`) into a silent `0` at exit 0, verified live with a failing `gh`
      stub. The file CONTRADICTS ITSELF: 160 lines earlier its own `_gh_probe` docstring
      names this exact swallow-pattern as unacceptable, and 32 other call sites already
      route through `gh_json`/`gh_retry` to avoid it -- this is the one cluster that never
      cut over. Measured, not estimated: 7 live call sites behind
      `.github/workflows/review-status.yml:115` and `.github/workflows/claude-review-reusable.yml:277`; a
      transient rate-limit reproduces the exact "green, ready, thread-clean, permanently
      unmergeable" state the file's own comments already document as having happened once
      (PR #553). The fix is a small, well-understood change to `.ci/scripts/lib/common.sh`
      (invariant 5, outside any writer's grant) with a live merge-blocking check downstream
      -- a decision, not a chore. Also found: two duplicate/orphaned `require_submodule`/
      `require_cmd`/`require_var` re-implementations elsewhere in `.ci/rediacc_ci/quality/`
      now have a canonical home in `core/common.py`, not yet cut over.
      **DEFECT 1 FIXED BY THE DRIVER, INLINE, same session.** Triaged `#0b834676`
      as INLINE (small, local, uses existing infrastructure). Routed
      `review_report_count`, `review_attempt_states`, `review_spent_attempt_count`
      and `review_spend_total` through the file's own `gh_retry` and a real
      `|| return 1` on every capturing assignment, matching the exact pattern
      `_gh_probe`'s own 160-line-earlier header already argued for.
      `pr_diff_loc` deliberately left UNCHANGED (its fail-to-0 is its own
      documented, intentional safe direction). Caught and fixed a real trap of
      my own mid-implementation: piping an empty result through a here-string
      (`wc -l <<<"$out"`) would have counted it as ONE line, not zero -- the
      same class of bug this session already found in `blocker-validator.sh`
      -- guarded explicitly before landing. Verified live end to end with a
      real failing-`gh` stub (both callers run under `set -euo pipefail`, so
      the fix correctly makes them abort LOUDLY instead of silently
      proceeding with a wrong number) and with a genuine empty-but-successful
      result (correctly still answers 0, not 1). The fix incidentally also
      closed DEFECT 1's second face (an unset `GITHUB_REPOSITORY` used to
      silently produce a number under `set -u`; now it also fails loudly) as
      a side effect of the new `|| return 1`, not a separate change.
      Port (`core/review_budget.py`) already raised `GhError` on this path --
      it was ahead of the twin, not behind -- so only its docstrings and 3
      tests needed updating from "pins the divergence" to "pins the
      agreement"; one test (`test_spend_total_agrees_with_the_twin`) had 2
      cases that were coincidentally agreeing for the WRONG reason (the
      port's CLI verb never fetches at all; the twin's fetch used to fail
      silently to the same number) -- removed those 2 non-comparable cases
      rather than leave a coincidence looking like a proof.
      **K=5 ledger re-recorded from scratch** (old rows described pre-fix
      bytes even though they only exercised the unaffected success path) via
      the disposable-scratch-git-repo technique, `git -C <scratch>`
      throughout, one of the 5 trees specifically exercising the fixed
      failure path. One harness bug caught and fixed before trusting any
      result: the ledger's own bash driver printed a multi-attempt result
      across two physical lines while the Python driver joined it onto one,
      producing a false MISMATCH on the one variant with 2 attempt rows --
      fixed by flattening embedded newlines in the bash driver, confirmed the
      real underlying data was identical throughout. 5/5 trees, 5/5
      fingerprints, `--assert --k 5` passes. All gates re-verified after:
      `check:ci-language-policy` unaffected (509, 0 added -- no bash file
      count changed, correctly, since this is an edit not a new file), full
      differential suite 89/89, `check:ci-python-lint` clean (fixed 3 findings
      of my own along the way, no `noqa`), `check:ci-dead-python` unaffected.
      `#0b834676` ticked.
    (ticked) 2026-09-24T10:00:40Z by d778be9d: all 14 bash libs ported (9) or deleted (5): .ci/rediacc_ci/core/account_lifecycle.py:811 ports the last of account.sh (21 of 21); gate check:ci-dead-python rc=0; every w7p5b-* pair asserts K>=5 via scripts/lib/shadow-gate.ts --assert, w7p5b-account-lifecycle over 8 trees

      **The 9-library PORT sub-scope of this box is now COMPLETE. The box itself stays OPEN**
      -- its own header claims "13 real bash libs", and the 4 beyond the 9 ported are NOT
      port targets: `age-check.sh`/`find-port.sh` need DELETION (retargeting 17 and 14
      callers, never a `shim:`), `local-common.sh` deletion is gated on W6's quality lane and
      W8's retarget per the existing arbitration table, and the box's exact "13" count has
      not been re-reconciled against the real files on disk this session (candidates found
      but not verified in scope: `.ci/lib/account.sh`, `.ci/lib/devbox.sh` -- the latter
      possibly already bridged per this plan's own W8 section, "six live in local-common.sh/
      devbox.sh and are bridged so the SAME BYTES run"). Next wave on this box: reconcile the
      13 count for real, then execute the age-check/find-port deletions.

      **FIFTH WAVE 2026-09-14: `.ci/lib/find-port.sh` IS DELETED. The DELETED axis moves
      1 -> 2, and this is the programme's first deletion of a bash LIBRARY** (E1's
      `.ci/lib/setup.sh` was the first bash deletion of any kind). Every number this box
      stated about the work was wrong, in the same direction as every prior wave, and each
      is corrected below from a re-derivation rather than propagated.
      **THE "17 AND 14 CALLERS" ARE 8 AND 6, and neither file is where the box says it is
      for one of them.** Anchored `git grep -nP` for real `source`/`.` sites, not bare
      string match:
      * `find-port.sh`: **8 real call sites in 6 files**, not 14. Four `source` sites
        (`.ci/lib/account.sh:12` and a REDUNDANT second at `:1048` inside a function, made
        a no-op years ago by the shim's own re-source guard; `.ci/lib/devbox.sh:24`;
        `.ci/lib/service.sh:49`), the 8 bash function calls behind them, plus two
        delegation CONTROLS that sourced the shim standalone
        (`.ci/rediacc_ci/quality/setup_idempotency.py` check C, the LIVE gate, and its
        invariant-5 bash twin `.ci/scripts/quality/check-setup-idempotency.sh`).
        A ninth and tenth surface the anchored grep MISSED and the test suite caught:
        four cases in `.ci/rediacc_ci/tests/test_core_ports.py` build the source line by
        f-string (`f"source {_q(shim)}; ..."`), which no `source \S*find-port.sh` pattern
        can see. **A caller list derived only by grep is a hypothesis; the suite is the
        refutation.** Run the tests before believing the grep is complete.
      * `age-check.sh`: **2 real production callers, not 17**, namely
        `.ci/scripts/quality/check-go-deps.sh:40` and `.ci/scripts/security/audit.sh:42`,
        plus 3 test surfaces whose whole subject is the shim.
      **AND `.ci/lib/age-check.sh` DOES NOT EXIST AND NEVER DID.** The file is
      `.ci/scripts/lib/age-check.sh`. `git log --all --diff-filter=D -- '*age-check.sh'`
      returns nothing, so this is not a move: the path in this box was always wrong.
      **THE "13 REAL BASH LIBS, 6,840 LINES" IS 14 LIBS AND 6,408 LINES**, measured at
      `1a148adeb` over every tracked `.sh` in `.ci/lib/` and `.ci/scripts/lib/`: account
      1119, bws-env 111, devbox 1087, find-port 145, local-common 1008, service 225,
      age-check 127, blocker-validator 356, common 772, emit-advisory 218, gate-controls
      41, release-age 237, release-state-validator 496, toolchain 466. No 13-member subset
      sums to 6,840; 6,408 with the last two digits transposed does. After this wave: **13
      libs, 6,263 lines.** The box's fan-in column is confirmed a LINE COUNT for a third
      time, exactly: gate-controls 41 = 41, bws-env 111 = 111, emit-advisory 218 = 218,
      release-age 237 = 237, toolchain 466 = 466, release-state-validator 496 = 496.
      **W8's "bridged so the SAME BYTES run" is LOAD-BEARING against this box and reads the
      opposite way to how it is cited here.** `.ci/rediacc_ci/setup/phases.py:77-109` names
      six phases whose implementation is `.ci/lib/local-common.sh` and `.ci/lib/devbox.sh`,
      and E1's setup port is ALREADY FLIPPED against them. So those two files are not
      "possibly already bridged, therefore maybe out of scope" -- they are PINNED
      DEPENDENCIES of a shipped port, and deleting either today breaks `./run.sh setup`.
      They stay, and the reason is stronger than the arbitration table's.
      **THE RETARGET, file by file.** Every bash function call replaced by the exact verb
      the shim's own body already delegated to, arguments and defaults preserved:
      * `.ci/lib/account.sh` -- the `source` at :12 becomes the shim's own load-time
        refusal (the `.ci/rediacc_ci/core` probe and the `python3` probe, both fail-closed
        with the fix in the message), and `ACCOUNT_CI_DIR` honours `REDIACC_CI_ROOT`
        exactly as the shim did. `is_port_in_use` x3 -> `is-port-in-use`,
        `find_consecutive_free_ports` -> `find-consecutive-free`, `find_preferred_port` ->
        `find-preferred-port`. The redundant second `source` at :1048 is deleted outright,
        and the comment at :1062 that justified it ("devbox.sh sources only find-port.sh,
        which this file already sources") is corrected rather than left to mislead.
      * `.ci/lib/devbox.sh` -- same guard, `derive_slot` -> `derive-slot`,
        `find_port_block` -> `find-port-block`.
      * `.ci/lib/service.sh` -- guard inline at the one conditional call site,
        `find_preferred_port` -> `find-preferred-port`.
      * `.ci/rediacc_ci/quality/setup_idempotency.py` check C and its bash twin -- the
        control used to reach the broken package COPY through `REDIACC_CI_ROOT`, which was
        only ever the shim's way of computing PYTHONPATH. Both now set PYTHONPATH
        directly, PREFIXED so the broken copy wins. `check_c`'s now-unused `lib` parameter
        was dropped, which broke the CONTROL invocation 70 lines below the assertion, at a
        line the assertion's own green never touches -- the gate caught it with a
        `TypeError`, rc=1. **A gate whose control lives far from its check is the reason
        that was a red and not a silent pass.**
      * `.ci/rediacc_ci/tests/test_core_ports.py` -- **4 cases, NONE DELETED.** Each
        asserted a property that survives the shim, so each was rehoused where the
        property now lives: fresh-interpreter stability and the fail-closed refusal onto
        the module run as a child, and "the delegation is real, not a reimplementation"
        onto `.ci/lib/devbox.sh`, the caller that inherited the shim's job. That last one
        is MORE load-bearing on the caller than it was on the shim: deleting a shim is only
        safe while its callers reach the module for real. A second control was ADDED with
        it, because `len(seen) > 1` is satisfied by a devbox.sh that has simply stopped
        working and errors differently each run; the new half pins one stable non-empty
        answer whose slot equals the module's, asked of `devbox_worktree` rather than
        hardcoded so it does not fail for the wrong reason inside a git worktree.
      **THE PLANT, on the real tree, not in a selftest.** Replaced devbox.sh's delegation
      with `slot="42"`. Both new cases went red
      (`rediacc-devbox-42-console` vs `expected slot 94`); restored by targeted edit,
      `diff -u` against the pre-plant copy byte-identical, 53/53 green again. The
      language-policy drain was checked the same way rather than by size: OLD 509, NEW 508,
      `REMOVED = ['.ci/lib/find-port.sh']`, **`ADDED = []`** -- the composition claim, not
      the total.
      **GATES, every one run on the real tree after the change.** rc=0:
      `check:ci-language-policy` (508, 0 added), `check:ci-dead-python` (1035 files, every
      one reached), `check:ci-setup-idempotency` (8 checks + "controls fired"),
      `check:ci-account-probes`, `check:ci-parity`,
      `check:ci-gate-reachability-coverage`, `check:ci-dead-bash`,
      `check:ci-script-exec-bit`, `check:ci-pipefail-grep-q`, `check:ci-tracked-sidecars`,
      `check:ci-setup-port-parity`, `check:ci-shell-lint`, `check:ci-shell-format`,
      `check:ci-shell-size`, `check:ci-shell-commands`. pytest 72/72 across
      `test_core_ports.py`, `test_quality_setup_idempotency.py`,
      `test_quality_account_probes.py`; ruff clean and formatted on all five touched
      Python files.
      **Two reds, both PRE-EXISTING and both proven not mine.** `check:ci-python-lint`
      rc=1 on exactly 2 findings, identical before and after this wave, in
      `.ci/rediacc_ci/tests/test_release_check_soak_period.py:42` (DTZ005) and
      `.claude/rediacc_hooks/tests/hookcases.py:1121` (DTZ011), neither touched here.
      `check:ci-shell-declared-commands` rc=1 on
      `.ci/scripts/quality/check-pool-writer-safety.sh executes 'python3' with no
      require_cmd`; that file is byte-identical to HEAD. **The obvious worry -- that this
      wave added `python3` to four bash files and the gate did not notice -- was PROBED,
      not assumed.** Appending a bare `python3 --version` to
      `check-setup-idempotency.sh` still produced a count of 1, and
      `scripts/gates/check-shell-declared-commands.ts:120` says why:
      `if (!src.includes('lib/common.sh')) continue`. `require_cmd` comes from common.sh,
      so a script that does not source it is deliberately out of scope. Correct scope, not
      a hole. The one-line fix owed to `check-pool-writer-safety.sh` is `require_cmd
      python3` near its top; it is outside this writer's grant and is handed over rather
      than reached for.
      **THE `age-check.sh` DELETION IS BLOCKED, and the door is `no-write-access`, not
      judgement.** `.ci/scripts/test/gates/test-age-check.sh` is a REGISTERED gate test
      (`scripts/ci-runner/manifest.ts:5087`, `scripts/ci-runner/gates.lock.json:4888`,
      `run` and `leaves` both pointing at it) whose entire subject is the shim -- verified
      passing today, rc=0, 4 cases. Deleting the shim reds it, and retiring it needs
      `manifest.ts` and `gates.lock.json`, both explicitly outside this wave's grant.
      **The ready-to-run brief, so the next wave does not rediscover any of it:** the shim
      is NOT a pure delegator (`check_entry_age` carries 27 lines of real bash -- a TSV
      verdict parse, an `emit_advisory` dispatch and an unreadable-verdict guard -- and it
      `source`s `emit-advisory.sh`), so its two callers each need that block inlined plus
      a direct `source emit-advisory.sh`. Both callers already have complete Python twins
      (`.ci/rediacc_ci/security/audit.py:1106`, `.ci/rediacc_ci/quality/go_deps.py:264`),
      **so the cheaper exit is to delete `audit.sh` and `check-go-deps.sh` in W7P5-c
      first, at which point age-check.sh has zero production callers and deletes for
      free.** Full surface: the 2 callers; 3 test surfaces (`test-age-check.sh` and its
      pytest port `.ci/rediacc_ci/tests/gates/test_gate_age_check.py`, both wholly
      obsolete; 3 cases at `.ci/rediacc_ci/tests/test_core_age.py:186,198,209` to rehouse
      the way `test_core_ports.py`'s four were); 2 entries in
      `.ci/config/language-policy-baseline.json:110,251`; the manifest and lock entries;
      `docs/agent-reference/suppressions.md:163`; `.ci/shadow/twin-parity.ledger.jsonl`;
      and **one DRIVER-ONLY edit, `.github/workflows/ci-quality.yml:1872` and `:2034`**,
      identical comment text in two jobs, which must change
      `# TOPOLOGY. audit.sh and check-go-deps.sh call entry_age_days (.ci/scripts/` /
      `# lib/age-check.sh), which asks ...` to name
      `rediacc_ci.core.age` instead. That comment justifies `fetch-depth: 0` on both
      checkouts and the DEPTH must not change with it.
      **Stale prose corrected rather than left to rot**, each because it now asserts
      something false: `.ci/rediacc_ci/core/ports.py:3,39-43,251`,
      `.ci/rediacc_ci/core/__init__.py:22` (its shim-contract clause 1 said the bash file
      keeps its path, full stop; it now says the shim stage is not the end state and
      clause 3 governs WHEN deletion is allowed, not whether),
      `.ci/rediacc_ci/quality/account_probes.py:56` and
      `.ci/scripts/quality/check-account-probes.sh:95`. The `source find-port.sh` lines
      INSIDE `account_probes.py`'s fixtures at :461 and :483 are deliberately KEPT and now
      labelled archaeology: those literals are the frozen 2026-08-04 shape, the fixture
      writes its own stub sibling, and editing them to track the live file is precisely the
      "unmutated control" failure the comment three lines above already warns about.
      Two prose references outside this grant are handed over: `scripts/lib/env-file.sh:9`
      ("the same shape as .ci/lib/find-port.sh") and `.ci/scripts/ci/greenlight.cjs:430`
      ("the legacy body sources account.sh, which pulls in find-port.sh" -- the listing
      entry it justifies is still correct, only the reason is stale).
      **Next wave on this box:** W7P5-c deletes `audit.sh` and `check-go-deps.sh`, then
      `.ci/scripts/lib/age-check.sh` follows for free. `local-common.sh` and `devbox.sh`
      cannot move until `.ci/rediacc_ci/setup/phases.py`'s six bridged phases are ported
      for real.
      AUDIT: DONE 2026-09-23 (audit): re-measured the "13 real bash libs" count and the
      9-ported claim against the tree rather than the box's own prose, which predates
      several deletions other sessions have since landed without updating this box.
      **Four of the 13 libs this box counted are simply gone now.**
      `.ci/scripts/lib/age-check.sh`, `.ci/scripts/lib/bws-env.sh`,
      `.ci/scripts/lib/gate-controls.sh` and `.ci/scripts/lib/release-age.sh` do not exist
      anywhere in the tree (`find . -name <name>` returns nothing for all four).
      `git log --all --diff-filter=D` finds each retired at commits `430b54ede`
      ("check-go-deps.sh, release-age.sh and age-check.sh retire", 2026-09-22),
      `0bb1a4c15` (bws-env + gate-controls, "9 more bash twins", 2026-09-22) and
      `7a9bda6d7` (2026-09-21) -- all three ancestors of current HEAD `2ed7d6726`
      (`git merge-base --is-ancestor` confirmed for each). `age-check.sh` went exactly as
      this box's own fifth-wave note predicted: delete `audit.sh`/`check-go-deps.sh` first,
      then the shim "follows for free" -- `430b54ede`'s own message confirms `check-go-deps.sh`
      was the caller that made it free. So the box's true remaining count is not "4 beyond
      the 9 ported" (account, devbox, local-common, age-check) but **3**:
      `account.sh`, `devbox.sh`, `local-common.sh`. `find-port.sh` was already correctly
      counted as deleted by the box's own fifth wave.
      **Current on-disk line counts** (`wc -l` against the live tree):
      `.ci/lib/account.sh` **1143**, `.ci/lib/devbox.sh` **1112**,
      `.ci/lib/local-common.sh` **1008**. **No shadow ledger exists for any of the three.**
      `ls .ci/shadow/ | grep -iE 'account|devbox|local.common'` returns only unrelated
      pairs whose names happen to contain "account" or "devbox" -- `w7p2-account-portal`,
      `w7p2-account-probes`, `w7p2-devbox-exec`, `w7p4b-ci-start-account`,
      `w7p4b-run-account`, `w7p5a-resolve-account-deploy-config`,
      `w7p6-ci-start-account`, `w7p6-deploy-account`, `w7p6-run-account`,
      `w7p6-set-account-worker-secrets` -- each a `.ci/scripts/deploy|release|infra` SCRIPT,
      never the `.ci/lib/account.sh` LIBRARY itself. No `w7p5b-account`, `w7p5b-devbox` or
      `w7p5b-local-common` prefix exists among the 277 ledgers on disk today.
      **The numerically smallest of the three, `local-common.sh` (1008 lines), is NOT the
      next portable one -- it and `devbox.sh` are both still gated, confirmed live rather
      than inherited from this box's own prior note.** `.ci/rediacc_ci/setup/bridge.py:3-10`
      states outright: "`setup()` calls fifteen things. Nine ... are ported in `host.py`.
      The other six live in `.ci/lib/local-common.sh` and `.ci/lib/devbox.sh`, which this
      box does not touch and which other verbs (`devbox`, `account`, `service`, `rdc.sh`)
      still call" -- and `.ci/rediacc_ci/setup/bridge.py:35` literally `source`s `.ci/lib/devbox.sh` at runtime,
      the "SAME BYTES run" this box's own prose already cited from W8.
      `.ci/rediacc_ci/setup/machine.py:57,141` and
      `.ci/rediacc_ci/setup/shadow_driver.py:136-147` bridge the same way for `devbox.sh`'s
      seven `setup_check()` questions. Porting either file alone, without also cutting over
      the four other verbs `bridge.py` names as still calling it directly, would create the
      exact duplicate-instrument risk invariant 5 exists to prevent -- neither is
      writer-actionable alone today.
      **`account.sh` (1143 lines) is the smallest lib that is genuinely unblocked, and is
      the one this brief targets.** Unlike the other two, it is named nowhere in
      `bridge.py`, `machine.py` or `phases.py` (grep confirmed, zero hits). Its only real
      sourcers, found the same anchored way this box's fifth wave found `find-port.sh`'s
      (real `source` sites, not bare string match), are
      `.ci/legacy/run-legacy.sh:405` and `:443`, both inside the same top-level command
      dispatcher: the `account` verb (`dev|db|test|stop|reset|seed-demo|totp`) and the
      `rotation` verb (`.ci/legacy/run-legacy.sh:401-439`). It defines 22 functions
      (`account_cleanup:41`, `account_allocate_ports:53`, `account_wait_port:114`,
      `account_rustfs_alive:167`, `account_docker_ghost_clean:178`,
      `account_generate_crypto_keys:191`, `account_generate_fresh_env:221`,
      `account_env_add_if_missing:275`, `account_ensure_env_keys:287`,
      `account_ensure_env:333`, `account_stripe_auto:347`, `account_dev:415` --
      the largest single function, 415-608 -- `account_dev_credentials:609`,
      `account_banner_row:722`, `account_totp:729`, `account_stop:763`,
      `account_test:810`, `account_test_e2e:819`, `account_reset:889`,
      `account_seed_demo:933`, `account_rotation:1018`, `account_db:1047`).
      **The scope warning this brief owes the next writer: this is not shaped like the 9
      already-ported libs.** Those (`gate-controls`, `bws-env`, `emit-advisory`, `service`'s
      Docker-free half, `blocker-validator`, `release-age`, `toolchain`,
      `release-state-validator`, `common`) are single-shot CLI tools whose stdout/exit code
      a shadow-gate differential compares directly. `account_dev`, `account_stop`,
      `account_test`/`account_test_e2e`, `account_reset` and `account_seed_demo` start and
      stop long-running dev infrastructure (Docker containers, RustFS, background servers)
      -- the same class `service.sh`'s own port already explicitly refused to touch
      (`service_start`/`service_stop` "explicitly NOT ported," this box's first-wave note).
      A K=5 shadow ledger recording one bash run and one Python run of `account_dev` would
      need to compare two dev-server-boot transcripts, not two deterministic reports --
      a different differential technique than the deploy/release ledgers already in
      `.ci/shadow/w7p6-*`, closer to `service.sh`'s deferred half or an E2E drill. The
      deterministic half -- `account_allocate_ports`, `account_wait_port`,
      `account_rustfs_alive`, `account_generate_crypto_keys`, `account_generate_fresh_env`,
      `account_env_add_if_missing`, `account_ensure_env_keys`, `account_ensure_env`,
      `account_totp`, `account_banner_row`, `account_db` -- is the part that fits the
      established shadow-gate pattern and is the recommended first slice; the interactive
      half needs a driver ruling on technique before a writer starts it, the same way
      `service.sh`'s split was a driver decision rather than a writer one.
      NOT ticked, nothing else touched in this box.
      AUDIT: DONE 2026-09-23 (writer): the DETERMINISTIC half of `.ci/lib/account.sh` is ported, licensed and differentially tested. The long-running half is untouched and stays a separate ruling, exactly as the 2026-09-23 audit above recommended.
      **PORTED, 11 of the 22 functions, into `.ci/rediacc_ci/core/account.py` (the `core/` home `service.py` established for a `.ci/lib/*.sh` port):** `account_allocate_ports`, `account_wait_port`, `account_rustfs_alive`, `account_generate_crypto_keys`, `account_generate_fresh_env`, `account_env_add_if_missing`, `account_ensure_env_keys`, `account_ensure_env`, `account_banner_row`, `account_totp`, and the decidable half of `account_db` (`db_plan()`: argument parsing, the database path, the devbox-derived preferred port, the free-port search, the two refusals and the `sqlite_web` resolution).
      **NOT PORTED, the other 11, and no Python function exists for any of them:** `account_cleanup:41` (kills the tracked pid set, calls `exit`), `account_docker_ghost_clean:178` (force-removes containers), `account_stripe_auto:347` (backgrounds `stripe listen`), `account_dev:415` (Docker, RustFS, Astro, Vite, a foreground gateway), `account_dev_credentials:609` (drives the live gateway's provisioning routes), `account_stop:763`, `account_test:810`, `account_test_e2e:819`, `account_reset:889`, `account_seed_demo:933`, `account_rotation:1018` (`cd` plus `npx tsx`). `db_launch()` is written out for completeness and is named in its own docstring as NOT differentially proved, because it execs a server.
      **SEQUENCING FOLLOWS THE ESTABLISHED PATTERN AND NOTHING IS CUT OVER.** `430b54ede`, `0bb1a4c15` and `7a9bda6d7` each retired a twin that was ALREADY ported and ALREADY held a K=5 ledger, and `.ci/lib/service.sh` is still sourced at `.ci/legacy/run-legacy.sh:48` while `rediacc_ci/core/service.py` has carried its ledger since 2026-09-10. So `.ci/legacy/run-legacy.sh:405` and `:443` are unchanged, and `test_the_twin_is_sourced_by_run_legacy_and_nothing_is_cut_over` asserts both source sites are still there.
      **THE LICENCE IS REAL AND IT IS ON DISK.** `.ci/shadow/w7p5b-account.observations.jsonl`, 5 rows, `npx tsx scripts/lib/shadow-gate.ts --pair w7p5b-account --assert --k 5` prints "equivalence holds over 5 distinct trees": 5 rows, 5 distinct clean trees, 5 distinct finding sets, every row EQUIVALENT, comment ratio 1.1578 against the 0.90 floor. Recorded against a disposable git repository outside this checkout (this tree is never clean), holding a copy of `.ci/lib`, `.ci/config`, `.ci/scripts/lib`, `.ci/rediacc_ci`, `scripts/lib` and `.devcontainer`, with the ledger written here via `--ledger` and every command relative so `reachesOutside` passes honestly. The fixture's `account.py`, `shadow_driver.py` and `account.sh` are `diff`-verified against the shipped ones BEFORE recording, and the whole ledger was re-recorded from scratch three times, after `ruff format` touched the file and after each of the two defects below, so the rows describe the bytes that ship rather than an earlier draft.
      **BOTH SIDES REALLY RAN.** `.ci/rediacc_ci/core/shadow_driver.py` drives them: the old side sources `account.sh` through `run-legacy.sh`'s own prelude (`constants.sh`, `toolchain.sh`, `local-common.sh`) and calls the twin's functions; the new side calls the port. Five scenarios, 314 observation lines, byte-identical on every one. `probe` covers the banner over five widths including a multibyte string, `rustfs_alive` and `wait_port` in BOTH directions against a real HTTP server the driver runs, and `allocate_ports` on a free pinned base and on one whose MIDDLE port the driver holds open. `db` reaches the devbox-derived preferred port end to end by occupying all 41 ports of the scan window, so the twin names the port it wanted in its refusal.
      **EIGHT PLANTED CONTROLS, SEVEN WATCHED GOING RED AND THEN REMOVED**, with the port restored byte-identical by sha256 after each: banner padding 62 instead of 63, the totp silent path explaining itself, `env_add_if_missing` dropping its blank line, the db refusal reworded, a typo in the fresh `.env` template, byte padding changed to character padding driven through pytest rather than through the driver, and the missing-curl guard removed. **THE EIGHTH DID NOT FIRE, AND THAT IS WHERE A REAL PORT DEFECT WAS.** Replacing `code not in {"", "000"}` with `code != "000"` in `rustfs_alive` passed the whole differential, which said the EMPTY-body branch is never reached: every scenario runs with curl installed. Taking curl off PATH showed the twin returning 1 quietly through its `|| true` while the port raised `FileNotFoundError`, a traceback where a verdict belongs. `curl_body()` now catches it at both call sites, and `test_a_missing_curl_degrades_on_both_sides_instead_of_raising` builds a PATH farm of every binary in `/usr/bin` and `/bin` EXCEPT curl and compares the two exit codes, having first asserted the farm is non-empty and that curl really is installed otherwise.
      **THREE REAL DEFECTS FOUND BY RUNNING IT, all fixed rather than papered over.** (1) The driver's `step` helper originally read `if ( set -e; "$@" ); then`, and a command in an `if` CONDITION runs with errexit SUPPRESSED, a suppression that propagates into a subshell created there. Under it `account_totp` survived the bare assignment that really kills it and printed "Could not read gateway port", a message it never prints in production. That is the `errexit-rearmed-in-a-tested-command` trap, met in the wild; `set +e` around a plain subshell fixed it, and the twin's genuine behaviour on a state file with no `gateway_port=` line is a SILENT exit 1. (2) `ensure_env` reached `generate_fresh_env` with no clock seam, so the bash side used the frozen fake `date` and the port used the wall clock. `ensure_env` now takes `stamp`, and both seams are fed from one constant. (3) The missing-curl crash above, in the port itself.
      **A FOURTH FINDING CAME FROM A GATE RATHER THAN FROM THE DIFFERENTIAL, and it is fixed the same way.** `test_canonical_sys_path_hop.py` flagged the driver's `sys.path.insert(0, ... parents[2])`, copied from `rediacc_ci/dev/shadow_driver.py` where it is baselined. Rather than add a forty-second baseline entry, the driver is now invoked as `PYTHONPATH=.ci python3 -m rediacc_ci.core.shadow_driver`, which removes the need for a hop at all; the ledger commands carry that form, and `dead_python.py` still admits the port because `--port .ci/rediacc_ci/core/account.py` is in the new-side command.
      **FOUR TWIN BEHAVIOURS REPRODUCED RATHER THAN FIXED**, each named in the port's docstring and pinned by a case: the silent death above; `printf '%-63s'` padding by BYTES so a multibyte glyph shifts the closing bar; `cut -d= -f2` truncating a state value containing `=`; and `account db --studio --bogus` refusing with exit 2 because the twin's loop keeps parsing after the flag.
      **THE PERMANENT SURFACE** is `.ci/rediacc_ci/tests/test_core_account.py`, 44 tests, about 15 seconds, all passing. It drives the live twin on every run rather than replaying a recording, asserts the K=5 ledger off disk, asserts the twin still defines all 22 functions, asserts the 11 unported ones still have NO Python counterpart, and declares `XDIST_GROUP = "ports"` so it serialises against `test_core_ports.py` over the host port space the driver pins.
      **GATES RUN:** `check:ci-dead-python` (1110 files, every one reached, 41 controls, the port admitted through the shadow route), `check:ci-python-gate-deps`, `check:ci-no-inline-python` and `check:ci-python-control-plants` all green; `ruff check` and `ruff format` clean on all three new files after 16 findings in them were fixed. `check:ci-pytest` ran the whole 17,581-test suite: 11 FAILED lines, and the string `core/account.py`, `core/shadow_driver.py` and `test_core_account` appear ZERO times anywhere in its 906 seconds of output. Every one of those failures was reproduced and attributed: three in `test_quality_python_lint.py` are `ruff format` differences in `.ci/rediacc_ci/core/bws_env.py`, `.ci/rediacc_ci/tests/gates/test_gate_bws_rotate.py`, `.ci/rediacc_ci/tests/test_core_bws_env.py` and `.ci/scripts/quality/check_bws_rotation_notice.py`, all a sibling session's uncommitted bws work; the rest sit in `test_gate_worklist_env_registry.py`, `test_wl_poll_and_waiting.py`, `test_quality_editorconfig.py`, `test_quality_control_vacuity.py`, `test_env_create_e2e_env.py`, `test_core_dockerx.py` and `test_canonical_sys_path_hop.py`, whose two remaining hop findings are `test_gate_python_control_plants.py` and `.claude/hooks/context/onboard.py`. `check:ci-python-types` reports 31 new findings and ZERO are in these three files; `check:ci-python-env-registry` reports 3 and none are; `check:ci-prose-style` reports 116 new findings and none are in these three files or in this plan.
      **NOT TOUCHED, and checked rather than assumed:** `.ci/lib/account.sh` itself (unmodified, still 1143 lines), `.ci/lib/local-common.sh`, `.ci/lib/devbox.sh`, `.ci/legacy/run-legacy.sh`, `scripts/ci-runner/manifest.ts`, `scripts/ci-runner/gates.lock.json`, `.ci/config/language-policy-baseline.json`, `docs/agent-reference/TRAPS.md`, `.ci/rediacc_ci/quality/trap_registry.py`, anything under `deploy/` or `release/`, and every `bws`-named file. `check_node_version` and `devbox_state_get` are RE-IMPLEMENTED in the port because a module cannot borrow a function from its importer, which is the same shape `service.py` records for `check_docker`; neither bash file is edited.
      NOT ticked. This slice covers half of one of the box's three remaining libs; `devbox.sh` and `local-common.sh` are still blocked on `setup/bridge.py`'s six bridged phases, and `account.sh`'s long-running half still needs a driver ruling on differential technique before a writer starts it.
      AUDIT: DONE 2026-09-23 (writer): the PURE-COMPUTATION half of `.ci/lib/local-common.sh` is ported, licensed and differentially tested, on the same pattern the `account.sh` slice above established the same day. Nothing is cut over and nothing is deleted.
      **THE CLASSIFICATION WAS RE-MEASURED, NOT INHERITED.** All 30 functions were read with line numbers and classified; the brief's 9-function list is CORRECT but INCOMPLETE as a statement of what is deterministic. `_sha256sum:37`, `_sed_i:46`, `compute_hash_for_package_dirs:58`, `_git_tree_fingerprint:92`, `compute_tree_hash:137`, `read_stamp_hash:148`, `write_stamp_hash:156`, `_version_gte:545` and `has_npm_script:401` are the nine, and every one of them is genuinely pure. FOUR MORE are equally pure and are deliberately NOT ported, each for a stated reason rather than by oversight: `check_node_version:418` is ALREADY ported at `.ci/rediacc_ci/core/account.py:143` and a second copy here would be two Python implementations of one bash function; `check_go_installed:439` calls `exit 1` rather than returning, so its only real behaviour is killing the sourcing shell; `_renet_source_hash:749` and `_renet_artifact_fp:785` exist solely to serve `ensure_renet_built`, which is not portable, so porting them would add differential surface for a caller that cannot move.
      **PORTED, 9 of the 30 functions, into `.ci/rediacc_ci/core/local_common.py`** (the `core/` home `service.py` and `account.py` established for a `.ci/lib/*.sh` port, with the hyphen-to-underscore spelling `bws_env.py` and `gate_controls.py` established).
      **NOT PORTED, the other 21, and no Python function exists for any of them:** the eleven installers and builders (`ensure_cpu_features_gypi:178`, `ensure_deps:203`, `ensure_packages_built:308`, `ensure_cli_built:333`, `run_npm_script:408`, `ensure_go_installed:458`, `ensure_bashcov_sup:566`, `ensure_host_tools:587`, `ensure_docker_installed:669`, `_ensure_docker_group:721`, `ensure_renet_built:789`), the three interactive or session-altering ones (`prompt_continue:371` reads stdin, `open_browser:381`, `reexec_with_docker_group:630` calls `exec sg docker`), `check_node_version:418`, `check_go_installed:439`, `_renet_source_hash:749`, `_renet_artifact_fp:785`, and the three DEVBOX-COUPLED ones (`gate_lane_decide:934`, `gate_lane_should_route:980`, `gate_lane_run:1005`), which source `.ci/lib/devbox.sh` and call `devbox_state_get` / `devbox_container_running` / `devbox_mount_ok` / `devbox_identity_ok` / `devbox_exec`. `.ci/lib/devbox.sh` is not read, not modified and not ported by this slice, and `test_devbox_is_not_touched_by_this_slice` asserts the port and its driver name nothing devbox-shaped, walking the AST rather than the text because both files discuss the coupling at length in prose.
      **THE LICENCE IS REAL AND IT IS ON DISK.** `.ci/shadow/w7p5b-local-common.observations.jsonl`, 7 rows, `npx tsx scripts/lib/shadow-gate.ts --pair w7p5b-local-common --assert --k 5` prints "equivalence holds over 7 distinct trees": 7 rows, 7 distinct clean trees, 7 distinct finding sets, every row EQUIVALENT, 196 observations, comment ratio 1.0416 against the 0.90 floor. Recorded against a disposable git repository outside this checkout (this tree is never clean), holding a copy of `.ci/lib`, `.ci/config`, `.ci/scripts`, `.ci/policy`, `.ci/rediacc_ci`, `scripts` and `.devcontainer`, with the ledger written here via `--ledger` and every command relative so `reachesOutside` passes honestly. The fixture's `local-common.sh`, `local_common.py` and `local_common_shadow_driver.py` are `diff`-verified against the shipped ones BEFORE recording, and the whole ledger was re-recorded from scratch THREE times, after the 125 defect below and after each prose-style reflow, so the rows describe the bytes that ship rather than an earlier draft.
      **BOTH SIDES REALLY RAN.** `.ci/rediacc_ci/core/local_common_shadow_driver.py` drives them: the old side sources `local-common.sh` through `run-legacy.sh`'s own prelude (`constants.sh`, `toolchain.sh`) and calls the twin's functions, the new side calls the port. Seven scenarios, 196 observation lines, byte-identical on every one. `hash` covers the six prune rules, a symlink, an empty directory, a name with a SPACE and one with a BACKSLASH (which the tool escapes, changing the bytes the outer hash sees), a missing start point, a trailing-slash start point and two unusable roots. `git-fp` runs against a real git repository the driver builds with a committed history, a modified file, a deleted file, a staged file and an untracked file. `version` drives 72 ordered pairs.
      **THE FIXTURES ARE BUILT IN PYTHON FOR BOTH SIDES**, which is the one place this driver departs from `core/shadow_driver.py`'s shape: two hand-written builders for a git repository are two things that can drift, and a fingerprint differing because the two repositories differ is a mismatch that says nothing about the port.
      **TEN PLANTED CONTROLS, ALL TEN WATCHED GOING RED AND THEN REMOVED**, with the port restored byte-identical by sha256 after each (`d0a6baffc9309595...`): the sha256 line printed with one space instead of two, the empty file set hashed as an empty stream, the `.DS_Store` prune rule dropped, the walk following symlinks, the `cd` diagnostic silenced, the errexit reproduction ignored, the stamp's trailing newline dropped, `filevercmp` replaced by a plausible dotted split, `has_npm_script` narrowed to the `scripts` object, and `_sed_i` losing its in-place flag.
      **THREE REAL DEFECTS FOUND BY RUNNING IT, all fixed rather than papered over.** (1) THE ONE A CONTROL FOUND THAT THE DIFFERENTIAL COULD NOT: with no `sha256sum` and no `shasum` on PATH, `compute_hash_for_package_dirs` exits **125**, not 0. `$_SHA256SUM_CMD` expands to nothing, `xargs -0` with no command defaults to `echo`, the next two pipeline stages are empty commands so nothing reads the pipe, `echo` takes SIGPIPE, GNU xargs reports a signal-killed child as 125, and `pipefail` carries it out. Every ledger scenario runs with the tool installed, so the branch is unreachable from the differential; `test_no_sha256_tool_degrades_the_same_way_on_both_sides` builds a PATH farm of every binary in `/usr/bin` and `/bin` except those two and compares the two sides live rather than against the constant. (2) The port's `sha256sum` RAISED `OSError` on an unreadable input where the tool names the file on stderr, omits its line and carries on; found by the `sha-missing` row and fixed at the call site. (3) The driver's own `while IFS= read -r l` loops DROPPED a final line with no trailing newline, so the BASH side under-reported what the twin really printed for `read_stamp_hash` over a hand-written stamp and for `_sed_i` over a file with no final newline. `|| [[ -n "$l" ]]` fixed it. That third one is a harness defect, and finding it is the reason the fix is recorded here rather than in a commit message.
      **SIX TWIN BEHAVIOURS REPRODUCED RATHER THAN FIXED**, each named in the port's docstring and pinned by a case. (1) An EMPTY file set is not the hash of nothing: `xargs` still runs the tool once, which hashes its own empty stdin, so an empty directory fingerprints as `abcfa6a9d4df...` and not as `e3b0c442...`. (2) `_git_tree_fingerprint` DIES OR SURVIVES DEPENDING ON WHO CALLED IT: `existing="$(while ...)"` is a bare assignment taking the loop's LAST status, so a `changed` list ending in a DELETED file kills it under armed errexit and does not when `compute_tree_hash` calls it from an `if` condition. Both directions are in the ledger: `fp-src` exits 1 with no output while `th-git-src` over the same repository and the same path prints a fingerprint. (3) `has_npm_script` greps the WHOLE `package.json`, so a dependency called `zod` answers true. (4) A missing `package.json` exits 2, not 1, because that is grep's status. (5) `write_stamp_hash` appends a newline `read_stamp_hash` never removes. (6) A missing sha256 tool has TWO different failure modes, `exit 1` from `_sha256sum` and the silent 125 above.
      **THE ONE PLACE THE PORT REFUSES WHERE THE TWIN WOULD GUESS:** `has_npm_script` raises on a script name carrying a BRE metacharacter, because the twin's `grep -q "\"$name\":"` makes that name a pattern. All 388 script names in `package.json` are `[a-z0-9:-]+`, where a BRE and a literal agree, so the refusal is free for the whole live corpus. Same shape as `account.py`'s `env_add_if_missing`.
      **THE TOOL SET THIS LICENCE IS TRUE AGAINST IS NOT GNU.** Measured 2026-09-23: `sha256sum`, `sort`, `tr`, `head`, `cat`, `uname` and `stat` on this machine are **uutils coreutils 0.8.0**, `find` is **bfs 4.1.1** and `grep` is **ugrep 7.8.4**; only `xargs` (GNU findutils 4.10.0), `awk` (GNU awk 5.3.2) and `sed` (GNU sed 4.9) are the GNU originals. That is recorded in the port's docstring rather than left implicit, because `sort -V`'s ordering and `sha256sum`'s backslash escaping are both reproduced from measurement. `version_gte` transcribes gnulib's `filevercmp` and was validated against the live `sort -V` over 2,401 ordered pairs from a 49-string corpus with zero divergences before any of it was written down.
      **THE PERMANENT SURFACE** is `.ci/rediacc_ci/tests/test_core_local_common.py`, 52 tests, about 5 seconds, all passing. It drives the live twin on every run rather than replaying a recording, asserts the K=5 ledger off disk, asserts the twin still defines all 30 functions AND NOTHING ELSE, asserts the 21 unported ones have no Python counterpart, and asserts all five real `source` sites are still there.
      **A VACUITY THIS SLICE CAUGHT IN ITS OWN FIRST GREEN.** `check:ci-python-env-registry` scans TRACKED files, so while the three new files were untracked it reported zero findings about them, which read as a pass. Staging them turned that into 8 real findings. They are registered by a hand edit adding exactly three keys to `.ci/config/python-env-registry.json`, verified by diffing the OLD and NEW module maps and asserting the removed side is empty and every other module is byte-identical, rather than by `--write-baseline`, which would have reseeded the whole file and silently absorbed a peer's 22 open findings.
      **GATES RUN:** `check:ci-dead-python` green (1114 files, every one reached, 41 controls, the port admitted through the shadow route, and PROVED non-vacuous by planting an unreferenced `.ci/rediacc_ci/core/zz_deadprobe.py`, watching it go DEAD, and removing it); `check:ci-python-gate-deps`, `check:ci-no-inline-python` and `check:ci-python-control-plants` all green; `ruff check` and `ruff format` clean on all three new files. `check:ci-python-lint` reports 3 unformatted files and all three are a sibling session's uncommitted `bws` work. `check:ci-python-types` reports 31 new findings and ZERO name these three files. `check:ci-python-env-registry` reports 22 and none are mine: 11 belong to the `account.sh` slice above (`core/account.py` 8, `core/shadow_driver.py` 2, `tests/test_core_account.py` 1) and were already red before this slice started, the rest are peers' `bws` and hook work. `check:ci-prose-style` reports 110 new findings and none are in these three files or in this plan. `test_canonical_sys_path_hop.py` fails on the same two pre-existing hops the audit above named, `test_gate_python_control_plants.py` and `.claude/hooks/context/onboard.py`; the driver needs no hop because it runs as `PYTHONPATH=.ci python3 -m`.
      **A GUARD DEFECT FOUND ON THE WAY, reported rather than routed around.** `.claude/rediacc_hooks/guards/block_untagged_commit.py` judges a commit in a DISPOSABLE repository outside the checkout against CONSOLE's own state, so `git -C <scratchpad fixture> commit` is refused for want of a `PR-TASK` trailer that belongs to a different repository. Its sibling `.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:151` documents exactly this class, names `block_untagged_commit` among the still-affected guards, and has itself been fixed via `shellscan.target_root`; the untagged guard has not. Two further notes for whoever fixes it: `target_root` only resolves a LITERAL `-C` path, so `git -C "$F" commit` with a shell variable falls through and judges CONSOLE; and it resolves through `git rev-parse --show-toplevel` in the target, so a `git init` that has not run yet (because an earlier guard blocked the same compound command) also makes it fall through.
      **NOT TOUCHED, and checked rather than assumed:** `.ci/lib/` is byte-identical to HEAD (`git diff HEAD -- .ci/lib/` is empty), which covers `local-common.sh`, `devbox.sh` and `account.sh`; `rdc.sh`, `.ci/legacy/run-legacy.sh`, `.ci/media/`, `scripts/ci-runner/manifest.ts` and `gates.lock.json` (both carry a peer's staged change that names nothing of this slice), `.ci/config/language-policy-baseline.json`, `.ci/config/prose-style-baseline.json`, `docs/agent-reference/TRAPS.md`, `.ci/rediacc_ci/quality/trap_registry.py`, anything under `deploy/` or `release/`, every `bws`-named file, and every W7P5-a and W7P5-c artifact. No call site is cut over: all five sourcers still source the bash.
      NOT ticked. This slice covers 9 of the 30 functions in 1 of the box's 2 remaining libs. `local-common.sh` itself still cannot be retired, because its three `gate_lane_*` functions reach into `.ci/lib/devbox.sh` and `setup/bridge.py`'s six bridged phases still call it; `devbox.sh` is untouched and still needs its own ruling.
      AUDIT: DONE 2026-09-23 (writer): the three PURE functions of `.ci/lib/devbox.sh` are ported, licensed and differentially tested, on the pattern the `account.sh` and `local-common.sh` slices above established the same day. Nothing is cut over, nothing is deleted, and `.ci/lib/devbox.sh` is byte-identical to HEAD (`git diff HEAD -- .ci/lib/devbox.sh` is empty).
      **THE SCOPE WAS RE-MEASURED, NOT INHERITED.** All 39 functions were read with line numbers and classified, and the brief's three-function list is CORRECT and also COMPLETE: `devbox_slugify:186`, `devbox_slug_drift:242` and `devbox_route_label:830` are the only ones whose whole answer is computation over their own arguments. Every other function reaches git, docker, the filesystem, the port allocator or the network. `devbox_url:283` is the NEAR MISS and is named rather than left as an absence: its body is pure string formatting, and its DEFAULT for the slug argument is `devbox_slug_active`, which inspects a running container, so it is pure only for callers that pass both arguments.
      **THE PURITY CLAIM WAS DRIVEN BEFORE ANY OF IT WAS WRITTEN.** The three were run against the live twin under `LC_ALL=C` and again under `LC_ALL=C.utf8` with the same corpus and the same answers both times, which is what the `slug-utf8` scenario now pins permanently. The whole environment dependency of the three is `tr` and `sed` on PATH and the sourcing shell's `set -u`, and that last one is not cosmetic: `devbox_slug_drift` and `devbox_route_label` open with `local x="$1"`, so a call with no arguments prints `$1: unbound variable` and KILLS the shell with status 1, while `devbox_slugify` is written `"${1:-}"` and answers the empty string. The port reproduces all three behaviours, and the `arity` scenario compares them.
      **PORTED, 3 of the 39 functions, into `.ci/rediacc_ci/core/devbox.py`** (the `core/` home `service.py`, `account.py` and `local_common.py` established for a `.ci/lib/*.sh` port). `tr` and `sed` are REIMPLEMENTED rather than shelled out, which is the opposite of the choice `local_common.py` made for `git` and `sed`, and the same rule read the other way: the pipeline is four byte-level rewrites, so piping the twin's own pipeline would be the same program and its differential would prove nothing.
      **NOT PORTED, the other 36, and no Python function exists for any of them:** the four git-coupled (`devbox_worktree:55`, `devbox_branch:176`, `devbox_slug_basename:199`, `devbox_slug:204`), the twenty-five docker-coupled (`devbox_docker:93` through `devbox_doctor:1105`), the five filesystem-coupled or port-allocating (`devbox_mount_root:70`, `devbox_state_write:107`, `devbox_state_get:124`, `devbox_base_port:136`, `_devbox_bind_if_present:452`) and the two network-probing (`devbox_status:846`, `devbox_url:283`). `test_the_unported_thirty_six_have_no_python_counterpart` asserts the absence rather than leaving it to a reader, and `test_the_twin_still_defines_every_function_this_slice_names` asserts the twin defines those 39 AND NOTHING ELSE.
      **THE LICENCE IS REAL AND IT IS ON DISK.** `.ci/shadow/w7p5b-devbox.observations.jsonl`, 7 rows, `npx tsx scripts/lib/shadow-gate.ts --pair w7p5b-devbox --assert --k 5` prints "equivalence holds over 7 distinct trees": 7 rows, 7 distinct clean trees, 6 distinct finding fingerprints, every row EQUIVALENT, 686 observations. Recorded against a disposable git repository outside this checkout (this tree is never clean), holding a copy of `.ci/lib`, `.ci/config`, `.ci/scripts`, `.ci/policy`, `.ci/legacy`, `.ci/rediacc_ci`, `scripts` and `.devcontainer`, with the ledger written here via `--ledger` and every command relative so `reachesOutside` passes honestly. The three files are `diff`-verified against the shipped ones BEFORE each recording, and the whole ledger was re-recorded from scratch after the last prose reflow, so the rows describe the bytes that ship rather than an earlier draft.
      **THE LEDGER WAS RE-RECORDED TWICE FROM SCRATCH**, once after the last prose reflow and again after `check:ci-python-lint` found the driver git mode disagreeing with its shebang.
      A tree id covers file MODES as well as bytes, so a row recorded at 100644 would not describe a driver that ships at 100755, and that gate finding is a real one this slice fixed with `git update-index --chmod=+x`.
      **THE TWO SCENARIOS THAT SHARE A FINGERPRINT ARE THE POINT, NOT A GAP.** `slug-basic` and `slug-utf8` drive one corpus under two locales and MUST agree; six distinct fingerprints across seven rows is what that claim looks like in the ledger, and `--assert` needs two.
      **BOTH SIDES REALLY RAN.** `.ci/rediacc_ci/core/devbox_shadow_driver.py` drives them: the old side sources `devbox.sh` through `setup/bridge.py`'s own prelude (`run-legacy.sh`, then `devbox.sh` on top) and calls the twin's functions, the new side calls the port. Seven scenarios, 686 observation lines, byte-identical on every one. EVERY ANSWER IS COMPARED AS HEX, through `od -An -v -tx1` over a capture file, because `devbox_slugify` prints a BARE NEWLINE for an empty answer and a text observation would make that identical to no answer at all.
      **THERE IS NO SANDBOX, and that is a statement about the subject.** The `local-common.sh` driver symlinks a whole `CONSOLE_ROOT_DIR` because its functions read and write real paths; these three take strings and return strings, so the old side sources the library straight out of the checkout the tree id names and the only temporary directory holds the corpus files. The corpus is built in Python for BOTH sides and handed to bash as NUL-separated records, because an argument may contain a newline.
      **TWELVE PLANTED CONTROLS: TEN FIRED, AND THE TWO THAT DID NOT ARE THE FINDING.** Each was planted into the port alone, watched against the live twin, and removed with the port restored byte-identical by sha256. The ten that fired: the dash collapse dropped (196 fuzz observations moved), the 40-cap become a 41-cap, the cut applied after the trim instead of before, the input encoded with `errors="ignore"` so bytes that are not valid UTF-8 vanish (39 moved), the empty answer losing its newline, the pre-change 404 catch-all, an empty `routed` read as `no`, the state-file drift line dropped, the 502 hint suffix dropped, and a Unicode-aware lowering.
      **THE TWO THAT STAYED SILENT WERE NOT WEAK CONTROLS, THEY WERE FALSE CLAIMS IN THE PORT'S OWN DOCSTRING, and both are now corrected there.** (1) A latin-1 port changed NOTHING, because `s/--*/-/g` collapses the run whether a multibyte character became two dashes or one, so the byte-versus-character choice is unobservable in the answer; the surviving and now-stated claim is that the bytes must not be LOST, which the `errors="ignore"` plant proves. (2) Dropping `${3:-unknown}` changed NOTHING, because the `unknown` it supplies reaches the `*)` arm and so does every other value that is not `yes` or `no`: the default is INERT, and the docstring said it was load-bearing. Both were caught only because each plant was watched individually rather than in a batch.
      **SEVEN TWIN BEHAVIOURS REPRODUCED RATHER THAN FIXED**, each named in the port's docstring and pinned by a case: an empty answer is still a LINE; the 40-character cap is applied BEFORE the final dash trim, so an answer can be 39 characters; a newline in the argument SURVIVES, because `sed` trims per line and a two-line argument yields a two-line answer; multibyte collapses to one dash per RUN rather than one per byte; `${3:-unknown}` fires on an EMPTY third argument and is inert anyway; `devbox_slug_drift` never fails, so its result is what it PRINTED; and no argument at all is an unbound-variable death rather than a default.
      **THE COMMENT-BYTE FLOOR IS THE ONE EXEMPTION THIS SLICE TAKES, AND IT IS VISIBLE RATHER THAN QUIET.** `shadow-gate`'s floor compares the WHOLE twin's comments against the WHOLE port's, which is the right denominator for a whole-file port and the wrong one for 3 functions out of 39: measured, `.ci/lib/devbox.sh` carries 28,483 comment bytes against the port's 13,848, a ratio of 0.4862, while the three PORTED functions' own comments are 1,998 bytes and the port scores 6.93 against them. The rows are recorded without `--old-file`/`--new-file`, on the `w7p5b-common` precedent, and `test_the_ledger_carries_no_comment_audit_and_says_why` recomputes the slice-level number on every run and fails if any row ever appears with a ratio below the floor.
      **THE PERMANENT SURFACE** is `.ci/rediacc_ci/tests/test_core_devbox.py`, 72 tests, about 13 seconds, all passing. It drives the live twin on every run rather than replaying a recording, asserts the K=5 ledger off disk, asserts all five real `source` sites are still there, asserts the port imports NOTHING that could reach outside its arguments (with the driver as the other-direction control), and re-plants five of the defects above IN PROCESS through `monkeypatch`, so nothing can leave a defect on disk and a scenario that stopped watching its own claim reds.
      **A HARNESS DEFECT FOUND BY RUNNING IT, and the vacuity it nearly produced.** A corpus entry spelled `\udcc3\udc28` is not encodable by `surrogateescape` at all (only `\udc80`-`\udcff` are), so the fixture builder raised on BOTH sides and the first comparison script called two empty outputs a MATCH. The entry is now `\udcc3(`, which is the invalid UTF-8 sequence it was meant to be, and `test_each_scenario_observed_something` is the floor that refuses an empty transcript from either side.
      **GATES RUN:** `check:ci-python-lint` GREEN over all 1,116 files (ruff 0.16.1 lint and format); `check:ci-dead-python` green (1,117 files, every one reached, 82 by the shadow route, 41 controls) and PROVED non-vacuous by planting an unreferenced `.ci/rediacc_ci/core/zz_devbox_deadprobe.py`, watching it report DEAD, and removing it; `check:ci-python-control-plants` green (241 gate modules, 139 plant sites, 19 controls). `check:ci-python-env-registry` reported exactly 2 findings for this slice, both `devbox_shadow_driver.py` (`HOME`, `PATH`), and they are registered by a HAND EDIT adding exactly one key, verified by diffing the OLD and NEW module maps and asserting the added side is that one key, the removed side is empty and every other module is byte-identical, rather than by `--write-baseline`, which would have reseeded the whole file and absorbed a peer's 22 open findings. The remaining 22 name `core/account.py`, `core/shadow_driver.py`, `test_core_account.py`, the `bws` work and two hooks, and none of them is this slice's. `check:ci-prose-style` over the whole tree reports 110 NEW findings and ZERO of them name these three files or this plan.
      **A GUARD DEFECT CONFIRMED AND EXTENDED, reported rather than routed around.** The `local-common.sh` audit above records `block_untagged_commit.py` judging a commit in a DISPOSABLE repository against CONSOLE's own state. The same shape holds for two more: `block_commit_identity` refused a fixture commit for an author email that has nothing to do with this repository, and `block_unproven_bulk_transform.py` reported "274 staged file(s)" for a one-file fixture commit, which is CONSOLE's staged count and not the fixture's. A LITERAL `-C <path>` does not help, contrary to the note left above: the same 274 is reported either way. Every fixture commit here therefore carries a `PR-TASK` trailer and a proof sentence that belong to another repository, which is honest but is not what those guards are for.
      **NOT TOUCHED, and checked rather than assumed:** `.ci/lib/` is byte-identical to HEAD, which covers `devbox.sh`, `local-common.sh` and `account.sh`; no other function in `devbox.sh` is read into the port, no bash file is edited, `.ci/legacy/run-legacy.sh`, `.ci/rediacc_ci/setup/bridge.py`, `scripts/ci-runner/manifest.ts` and `gates.lock.json`, `.ci/config/prose-style-baseline.json`, `.ci/config/language-policy-baseline.json`, `docs/agent-reference/TRAPS.md`, anything under `deploy/` or `release/`, every `bws`-named file, and every W7P5-a and W7P5-c artifact. The only non-new file this slice writes is `.ci/config/python-env-registry.json`, one key. No call site is cut over: all five sourcers still source the bash.
      NOT ticked. This slice covers 3 of the 39 functions in the last of the box's remaining libs. `devbox.sh` itself cannot be retired: the other 36 functions are the whole of the devbox verb, `setup/bridge.py` still calls them as bash, and `local-common.sh`'s three `gate_lane_*` functions still source this file.
      AUDIT: DONE 2026-09-24 (writer): the side-effecting halves are ported by a STUB-FARM TRANSCRIPT differential, and 12 of the 13 libs are now fully ported or deleted.
      **VERIFIED COUNT, re-derived against the tree rather than this box's earlier prose.** Of the 13 libs (14 measured at `1a148adeb`, minus `find-port.sh`):
      **5 DELETED** (`find-port.sh`, `age-check.sh`, `bws-env.sh`, `gate-controls.sh`, `release-age.sh`; `find . -name` returns nothing for each).
      **7 FULLY PORTED, twin still on disk for W7P5-c:** `blocker-validator.sh`, `emit-advisory.sh`, `release-state-validator.sh`, `toolchain.sh` (unchanged since their waves), and `common.sh`, `service.sh`, `local-common.sh` (completed today).
      **1 FULLY PORTED TODAY by a sub-writer:** `devbox.sh`, all 42 functions.
      **1 PARTIAL:** `.ci/lib/account.sh`, 10 of its 20 functions ported. The other 10 (`account_cleanup`, `account_docker_ghost_clean`, `account_stripe_auto`, `account_dev`, `account_dev_credentials`, `account_test`, `account_reset`, `account_seed_demo`, `account_load_defaults`, `account_state_gateway_port`) are NOT ported. The reason is concurrency, not technique.
      A leased account-env writer (PLAN-account-env-to-bws, worker lease live at 10:49) was rewriting `account.sh`, `core/account.py` and `test_core_account.py` during this pass. Porting under a live rewrite would race it. It is the box's only remaining work.
      **THE TECHNIQUE, which answers the "driver ruling on differential technique" the audits above asked for.** `.ci/rediacc_ci/core/stubfarm.py` builds a directory of bash stubs placed first on PATH for BOTH sides. Each stub appends its argv to one transcript and answers from a scripted table.
      A case is then compared on rc, both streams, the ORDERED call transcript and the files left behind, so a port has to make the same calls with the same arguments in the same order. Tools a case needs ABSENT are removed through a symlink farm of the host's program directories (`Farm.host_path`), because a stub can add a program but not take one away.
      **`service.sh`, now whole.** `service_start`, `service_health`, `service_stop` and the attaching `service_logs` are in `core/service.py`. Driver `core/service_shadow_driver.py`, ledger `w7p5b-service` re-recorded at 6 trees. `.ci/docker/service/env.sh` stays bash and is run in a bash child whose exported environment is read back.
      Four more twin behaviours are reproduced and pinned: errexit deaths on failing `compose build`/`up`, doubled container names on stdout from `service_stop`, the debug cadence overshooting the budget, and a verbatim non-numeric port.
      **`local-common.sh`, now 30 of 30.** The 21 installers, prompts and lane functions are in `core/local_common.py`. Driver `core/local_common_actions_shadow_driver.py`, new pair `w7p5b-local-common-actions` at 9 trees, 101 cases. The `gate_lane_*` functions reach devbox through `core.devbox`, never through the bash file. The pure pair `w7p5b-local-common` was re-recorded at 7 trees, because the port file changed.
      **TWO LIVE TWIN DEFECTS FIXED IN THE TWIN, both found by these scenarios.** (1) `ensure_bashcov_sup` read `$REPO_ROOT`, which nothing on its load path defines. Under `set -u` it died with "REPO_ROOT: unbound variable" on every call, so `./run.sh setup` (through `setup/bridge.py`) never built the profiler supervisor. Verified live before and after the fix: rc=1, then rc=0 with "built bashcov-sup".
      (2) `ensure_cli_built` died SILENTLY whenever `.ci/cache/build-packages.stamp` was missing. That `cat` was the last command of a group feeding a bare pipeline assignment under pipefail. `|| true` now keeps the empty stamp as data.
      **`common.sh`, now whole.** `r2_count_objects` (the gap left for want of an `aws` binary) and `wait_for` are ported. `wait_for` has no caller in the tree, and the 2026-09-10 table credited it to `rediacc_ci.proc`, which never defined it. Driver `core/common_stub_shadow_driver.py`, new pair `w7p5b-common-stub` at 6 trees.
      **`devbox.sh`, 42 of 42**, by the sub-writer: `core/devbox.py` (a `Devbox` class, `invoke()` by bash name), 16 new stub-farm scenarios, and ledger `w7p5b-devbox` re-recorded at 23 trees. Eleven twin defects are reproduced and pinned, including `devbox_up` dying silently with no `docker` group and `devbox_identity_ok` passing when nothing runs.
      **PLANTED CONTROLS:** 16 in service, 31 in local-common including the lane, 7 in the common stub half, and 16 on disk plus 8 in-test in devbox. Each fired, and each port was restored byte-identical by sha256. Four plants stayed silent at first. Three of them exposed missing cases, which were added until the plant fired. The fourth is environment-bound and recorded in the driver docstring: `/etc/profile.d/golang.sh` is read from the real filesystem.
      **HANDED OVER, not done:** `core/account.py` still carries its own `check_node_version`, and `test_check_node_version_agrees_with_the_account_copy` pins the two copies together. Nothing is cut over, and no sourcer moved.
      NOT ticked: `account.sh` is at 10 of 20.
      AUDIT: DONE 2026-09-24 (writer): `.ci/lib/account.sh` is whole, 22 of 22 (21 plus the `account_spawn` this wave added), and with it all 14 libs are ported or deleted. Nothing is cut over and no bash is deleted; that is W7P5-c.
      **THE COUNT, re-derived on disk.** Of the 14 libs measured at `1a148adeb`, 5 are DELETED (`find-port`, `age-check`, `bws-env`, `gate-controls`, `release-age`; `find` returns nothing for each) and 9 remain as twins, every one fully ported: `account`, `devbox`, `local-common`, `service`, `blocker-validator`, `common`, `emit-advisory`, `release-state-validator`, `toolchain`.
      The "10 of 20" above was one short on both sides: the twin defines 21 functions, and the 11 left were the 9 the brief named plus `account_test_e2e` and `account_state_gateway_port`.
      **PORTED, the last 11, into a sibling `.ci/rediacc_ci/core/account_lifecycle.py`** (`core/account.py` keeps the deterministic half and its own pair): `account_dev`, `account_dev_credentials`, `account_stripe_auto`, `account_cleanup`, `account_docker_ghost_clean`, `account_test`, `account_test_e2e`, `account_reset`, `account_seed_demo`, `account_load_defaults`, `account_state_gateway_port`.
      **PROVED BY A STUB-FARM TRANSCRIPT**, driver `core/account_lifecycle_shadow_driver.py`, new pair `w7p5b-account-lifecycle`, 8 scenarios and 80 cases, `--assert --k 5` rc=0 over 16 distinct trees (8 before and 8 after the group-kill fix below). `account_dev` runs end to end on both sides: Astro, Vite and `stripe listen` as background jobs, the forked credentials job, the foreground gateway and the EXIT-trap cleanup.
      Background programs record into a separate channel compared SORTED, the one place order is given up; two handshakes (stripe waits for the first `sleep 1`, the gateway waits for the credentials job's last call) remove the other races rather than sorting them away.
      **SEVEN TWIN BEHAVIOURS REPRODUCED, each measured live and named in the port's docstring.** `account_seed_demo`'s "Could not reach" branch is dead code (a bare `body=$(curl ...)` dies under errexit first). `account_dev_credentials` dies SILENTLY when the seed answer is not readable JSON (a `read` at end of file inside `{ ... } < <(node ...)`) and when `hostname -I` fails.
      `account_stripe_auto` dies with npx's status when the product sync fails. `account_dev` writes `pids=` SPACE-separated, because `${ACCOUNT_PIDS[*]// /,}` substitutes per element; both readers split on whitespace, so it is harmless, and the comma form is the W7P5-c cleanup.
      **PLANTED CONTROLS: 12 on disk, all fired, the port restored byte-identical by sha256 each time; 5 more run inside pytest against a mutated COPY of the package.** The first run left one plant silent (`cleanup()` without its `kill`): waiting on its own child outlasted the child, so "dead afterwards" held either way. A `cleanup-kills-foreign` case, a process the DRIVER owns, closed it and the plant then fired.
      **THREE HARNESS DEFECTS FOUND AND FIXED, outside this box's grant and flagged as such.** (1) `core/stubfarm.py` read its table on stdin, so any row's `sh` inherited the TABLE as stdin: `echo from-caller | tool` with `sh='exec cat'` printed the next table row. The twin's `node -e ... <<<"$seed_json"` therefore parsed table text and died, silently. The table is now read on fd 3; `test_core_local_common.py`, `test_core_service.py` and `test_core_common.py` stay green (410 passed).
      (2) `scripts/lib/shadow-gate.ts` masked the `--repo` string in finding text without resolving it, so `--repo .` rewrote every dot (`dev.defaults.env` compared as `dev<repo>defaults<repo>env`). It now resolves the root; its selftest passes and the `w7p5b-devbox` rows recorded that way still assert.
      (3) The same gate's REFUSAL vocabulary matches `CANNOT READ` case-insensitively inside a quoted observation, which recorded one row as ERROR_REFUSAL; the driver rewrites that phrase on both sides, the precedent `core/shadow_driver.py` set for banner whitespace, and that ledger was re-recorded from scratch.
      **`check_node_version` HAS ONE PYTHON COPY.** `core/account.py`'s duplicate and its `version_tuple` are deleted; both account modules import `rediacc_ci.core.local_common`'s, and `test_check_node_version_agrees_with_the_account_copy` went with the duplicate it pinned. `account.grep_cut` now keeps EVERY matching state-file line, as the twin's `$(grep | cut)` does, where it kept the first.
      `generate_crypto_keys(strict=True)` reproduces the twin's errexit on a failing `node` or `openssl`, so `reset()` can no longer reach `store-from-env` with empty values. `w7p5b-account` gained 8 rows on new trees for the changed port and twin, and holds over 13.
      **WORKLIST #e45fc13c, FIXED IN BOTH THE TWIN AND THE PORT: `account_cleanup` signalled only the pid it tracked.** Orphaned `node .../vite --port 4801`, `4804`, `4807` and matching Astro servers, parented to `/init` and started 09:58, 10:21 and 10:33, show each host `account dev` run stepping to the next free triple past the last one's leftovers.
      A probe did NOT reproduce the orphan with a plain SIGTERM on this host (bash exec-optimises `( cd X && npx ... )` into `npm exec`, which forwards the signal), so the root cause of those three orphans is not pinned; what the fix closes is the class, any descendant the tracked pid does not take down with it.
      `.ci/lib/account.sh:74` adds `account_spawn`, which starts Astro and Vite as their own process-group leaders (`set -m`); `stripe listen` gets the same at `:312`; `account_cleanup` at `:84` signals the group first and falls back to the pid. The port mirrors it: `spawn_background()` uses `process_group=0` and `cleanup()` tries `os.killpg` first.
      The new `cleanup-kills-tree` case starts a job whose program leaves a child and waits. `test_cleanup_without_the_group_kill_orphans_the_child` drives it against a planted copy of each side with the plain kill restored: `child alive=1` on both, against `alive=0` with the fix.
      **ALSO FOUND, NOT FIXED, reported rather than widened:** `.account-state` is shared by the host and the devbox (one worktree), so a `pids=` line written inside the container (pids 2588 and 2589 on 2026-09-24) names CONTAINER-namespace pids that a later host `account dev` or `account stop` signals on the host. The group kill was deliberately NOT extended to those state-file readers for that reason.
      **EM DASHES:** all 13 in `account.sh` (12 lines, 2 of them log output) became `--`, and the 14 `account.sh` ids drained from `scripts/data/em-dash-surfaces-baseline.json`; `check:ci-em-dash-surfaces` rc=0.
      **GATES:** `check:ci-dead-python`, `check:ci-no-inline-python`, `check:ci-python-control-plants`, `check:ci-python-gate-deps`, `check:ci-language-policy` and `check:ci-em-dash-surfaces` rc=0; all 16 `w7p5b-*` pairs assert at K>=5. `test_core_account.py` 82 collected, 80 passed and 2 skipped (the two `stop()` real runs skip while a devbox session's real account stack is up; with no stack up they passed earlier in this wave). With `test_core_local_common.py`, `test_core_service.py`, `test_core_common.py` and `test_quality_account_probes.py`: 497 passed, 2 skipped. The shell gates (`check:ci-account-probes`, `shell-lint`, `shell-format`, `shell-size`, `shell-commands`, `shell-declared-commands`, `dead-bash`, `pipefail-grep-q`) are rc=0 on the changed twin.
      `check:ci-python-lint` reds only on `.claude/hooks/stop/wl_roster.py` and its test; `test_canonical_sys_path_hop.py` reds only on pre-existing hops in `.claude/`. `check:ci-python-env-registry` reads the two new modules' registry entries as STALE until they are tracked; the gate's own `evaluate()` over the tracked corpus plus those two paths returns 0 findings.
- [ ] **W7P5-c S** The deletion box, the only one that removes anything.
      **OPERATOR RULING 2026-09-21 ON THE HOOK ORACLES AND THE TOOLCHAIN BASH.** The 47 `.claude/oracles/**` bash
      files stay as a permanent language-policy exemption (`tree:.claude/oracles/`, abda9690f), chosen over goldens,
      history extraction, mutation tests and Python reference rewrites after scoring (4.65 of 5 against 3.50, 3.10
      and 2.75): their value is real bash execution, which caught bash 5.3 vs 5.2 diagnostic wording and
      empty-pipeline output that Python cannot reproduce, and about 78 percent of the 5,844 cases only assert
      silence. Equivalence to bash stays the spec, so the two tests that read the oracle sources stay. The
      toolchain checks fold into one bash file, `chain-head.sh`, and every other `.claude` bash file is to be ported
      where it can be: `bash_env.sh` cannot (BASH_ENV sources bash into the shell, and only the machine-local
      `~/.claude/settings.json` wires it), inline shell in settings.json was rejected as a policy loophole.
      **FOUR MORE RULINGS, SAME DAY.** A licensed script whose differential executes the bash twin is retired by
      freezing the twin's outputs as goldens (header carries the twin's blob sha) and deleting the bash; the 860
      em dashes in `packages/cli/src` comment lines stay replaced by commas (d6edcdd13); the six moved pronoun
      findings stay baselined under new hashes; and floors are lowered to the measured count in the same change
      as a deletion.
      **THREE BLOCKERS ON `run-all.sh` SPECIFICALLY, each verified against the enforcing code
      on 2026-09-09, not inferred.** The wiring is done (W7P3-BAT) and the licence is granted
      at `27 == 27`; these are what still stops the file being removed.
      * **`docs/agent-reference/TRAPS.md:2463` carries
        `Enforced-By: file:.ci/scripts/test/run-all.sh:149`,** and
        `.ci/rediacc_ci/quality/trap_registry.py:35-37` and `:446` require a `file:` pointer
        to exist on disk with a non-blank `:line`. Line 149 is `guard_selftest() {`, part of a
        peer's uncommitted 185-line addition.
        **SETTLED 2026-09-09, and it is NOT an operator decision -- it is
        `JUDGMENT-ONLY`.** The trap is `errexit-rearmed-in-a-tested-command`: `set -e`
        re-armed inside `if ! fn` is inert. That is a BASH semantic. `battery.py` is Python
        and has no `set -e`, so there is no counterpart to repoint to **by construction**,
        and inventing one would be a control that proves nothing. F3 at
        `.ci/rediacc_ci/quality/trap_registry.py:32-33` accepts "either >=1 pointer or the
        single token JUDGMENT-ONLY", so the deletion commit changes this entry's disposition
        to `JUDGMENT-ONLY` and the registry stays green.
        **That is the honest disposition rather than a convenient one**, because the entry's
        own Residue already says it: "that control covers ONE function in ONE runner. Nothing
        decides, in general, whether a given assertion about `set -e` is running in a
        suppressed context ... Reading the call site stays a human step." The trap stays
        VALID for the other ~620 tracked `.sh`; only its single instance-level control dies
        with the runner that carried it.
        The peer's uncommitted lines are not a blocker on anyone's decision either: nothing
        in this session deletes the runner, and whoever runs W7P5-c re-checks the peer state
        at that moment rather than against a note written now.
      * **`.ci/config/language-policy-baseline.json:423`** --
        `.ci/scripts/quality/check_language_policy.py:841-857` returns 1 on a baselined bash
        file that has left the tree ("Ratchet the baseline in the same commit"), so the drain
        must ride the deletion commit.
      * **`.ci/scripts/test/gates/test-run-all-parallel.sh:44-47`** hard-fails with
        `$RUNNER is missing or not executable` -- 231 lines whose entire subject is the
        deleted runner, plus its `gate-test:run-all-parallel` manifest and lock entries.
      * **RE-VERIFIED 2026-09-20, TWO MORE.** (4) No shadow ledger pairs `battery.py` with
        `run-all.sh`: `.ci/shadow/` holds `w7p2-battery-clean-tree` only, which covers a
        different gate. The pytest differential exists but is fixture-driven, so it is not a
        K=5 licence. Registering the pair and recording five rows is the next step, and it
        needs the full battery run against a committed tree. (5) About ten `BLOCKER` texts in
        `scripts/ci-runner/manifest.ts` say "inside run-all.sh" and must be reworded in the
        deletion commit.
      Also unresolved by the deletion: `.ci/rediacc_ci/tests/test_battery.py` is a
      differential whose `TWIN` constant IS `run-all.sh`.
      **CENSUS DONE 2026-09-09, nothing deleted. Report:
      `agent/f4da5c2e/W7P5c-licence-census.md`.** Its headline refutes the brief it was
      given: this box is NOT throughput-limited by ledger accrual. **81 of 82 ledgers
      already pass K=5**, verified independently by the driver over every pair, and zero
      files wait on accrual. The constraint is COVERAGE -- 77 quality twins have a ledger
      and **0 of 149 gate tests do**, 45,099 lines and 73% of the surface with nothing to
      accrue FROM -- and recording a first row is writer work, so this box PARALLELISES.
      **23 licensed today (22 strictly), draining 515 -> 493.** C1 blocks 1, C2 blocks 11,
      **C3 blocks 53**. `check-lockfile.sh` is the strict exclusion and NOT a port defect:
      its twin fails identically on `private/account/package-lock.json`.
      **RE-CHECKED 2026-09-15, NOT RE-DERIVED IN FULL -- two concrete signals worth
      recording rather than a new headline number guessed from them.** (1) Both boxes this
      census named as blockers are now done: C1 was already `[x]`, and C2 (`pathsOrigin`
      required + verified) landed and ticked earlier tonight -- together the census's own
      text says they blocked 12 paths, so this precondition may have moved without anyone
      re-running the sweep that measures it. (2) The ledger count this box's own precondition
      rests on has grown far past its own baseline: `ls .ci/shadow/*.observations.jsonl` is
      **258** today (77 w7p2, 16 w7p5a, 10 w7p5b, 153 w7p6, plus 2 singletons), not the "82"
      this census and `agent/plans/PLAN-extension-shaped-matchers.md`'s repeated re-checks assume --
      consistent with that plan's own newly-flagged w7p5a-/w7p6- prefix ambiguity. Neither
      number is re-derived here: the actual COVERAGE claim ("0 of 149 gate tests have a
      ledger") needs the real census tool re-run against the current tree, not a raw ledger
      count, and that re-run is real work for whoever next picks up this box -- not
      attempted under this session's own workload tonight.
      **BLOCKERS, EACH DRIVEN RATHER THAN INHERITED.** `JUDGMENT-ONLY` confirmed through the
      `TRAP_CORPUS` env seam against a modified COPY, leaving `docs/agent-reference/TRAPS.md`
      untouched: exit 0 before and after, with two controls firing red -- a dangling pointer,
      and `JUDGMENT-ONLY` over an emptied Residue. **It must REPLACE the pointer, not join
      it**; `.ci/rediacc_ci/quality/trap_registry.py:577` refuses a mix.
      `.ci/scripts/test/gates/test-run-all-parallel.sh` confirmed, and **no `package.json`
      key exists**, so only two of the three wiring sites apply.
      **`.ci/rediacc_ci/tests/test_battery.py` is STRONGER than briefed:** its line 198 READS
      THE TWIN'S SOURCE AT TEST RUNTIME and executes a heredoc extracted from it, so deletion
      makes the test raise rather than merely mis-point.
      **AND `run-all.sh` IS NOT LICENSED ON C1 AT ALL** -- no ledger names it in `old.cmd`.
      W7P3-BAT's `27 == 27` is a real-tree-twin SET EQUALITY, not a K=5 shadow licence; the
      two must not be confused when the deletion runs.
      **Figures corrected by measurement:** 61,754 lines not 62,233, **140** gate tests not
      141, and 18,723 is all 82 quality gates rather than "75 of 77" -- the 77 ledgered twins
      are 18,366. Magnitude right, attributions off.
      **DRIVER RULING 2026-09-09: `test_twin_parity.py` IS the C1 evidence for the
      gate-test half. A shadow-gate ledger is neither required nor obtainable there.**
      A writer sent to record the missing rows recorded **zero of 149 and was right to.**
      Its evidence: `shadow-gate.ts --record` refuses a dirty tree, so it worked in a local
      clone whose `HEAD^{tree}` it verified identical; it then drove the BEST-CASE twin --
      one where both sides call the same `scripts/lib/release-age.ts`, so their messages are
      byte-identical by construction -- planted a real defect, and still got
      `MISMATCH_FINDINGS`. **Bash halts at the first failure while pytest decorates every
      one as `<path>:<line>: <ExceptionType>: <message>`, and `classify()` has no rule to
      strip that.** Cardinality matching under `-x` does not help; the decoration alone
      breaks multiset equality. Five more twins share the same `conftest.py`/`harness.py`,
      so it generalises to the whole population. This is a comparator incompatibility, not a
      missing ledger, and no amount of writer time closes it.
      **The evidence already exists and is STRONGER than K=5.**
      `.ci/rediacc_ci/tests/gates/test_twin_parity.py::test_port_and_twin_agree` asks exactly
      this question continuously in CI, and its ledger `.ci/shadow/twin-parity.ledger.jsonl`
      carries **141 distinct subjects across 231 rows, 231 of them recording agreement** --
      verified by the driver, and 141 is precisely the gate-test population with a Python
      twin. A K=5 ledger is five historical observations; twin-parity is keyed on
      `twin_sha`/`port_sha`, so it RE-VERIFIES whenever either side changes. Both halves run
      unconditionally in the same `ci-quality.yml` job.
      **So C1 for a gate-test twin reads: a green `test_port_and_twin_agree` row for that
      subject.** C2 and C3 are unchanged and still bind -- and C3 is the one that matters
      here, as the call site below proves.

      **A LIVE BASH CALL SITE THE C3 SCAN WOULD MISS, found by the census and confirmed by
      the driver.** `.github/workflows/autopilot.yml:252` still runs
      `.ci/scripts/quality/check-resolved-threads.sh` while `.github/workflows/ci.yml:624`
      runs the Python `check_resolved_threads.py`. Both exist and both are invoked, so that
      twin is maintained twice AND executed twice per PR on different paths -- and it HAS a
      K=5 ledger (`.ci/shadow/w7p2-resolved-threads.observations.jsonl`), so it would
      otherwise read as licensed. **Deleting it without repointing `.github/workflows/autopilot.yml:252` breaks
      autopilot**, and the repoint is a driver-only workflow edit. This is the shape C3
      exists to catch and a reminder that a ledger licences EQUIVALENCE, never reachability.
      **PRECONDITION STATUS 2026-09-08, measured not claimed.** `agent/plans/PLAN-extension-shaped-matchers.md`
      commits 1 and 2 are LANDED: the duplication counter's coordinates, per-family floors and
      four exclusion predicates, plus `_cipath.py` and `harness.watchdog_subject()`. Of the five
      extension-shaped matchers, one is FIXED with its bash twin mirrored so the port does not
      silently diverge, two are REFUTED as fail-LOUD differentials that must keep naming the twin,
      and two are being ported. Commit 3 (three Python families, 21 measured shapes to EXTRACT
      rather than accept) is in flight. **The operator was asked on 2026-09-08 whether to start
      deleting the one finished family -- pre-bash guards, 1 `.sh` against 42 `.py` -- and chose
      to WAIT for the full precondition.** So this box stays at 0 of 521 by decision, not by drift.
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
      **PRECONDITION ADDED 2026-09-08, and it is not optional: sweep the estate for
      extension-shaped matchers first.** A tool that identifies a gate by `.sh` stops
      seeing it the instant the twin is deleted, and the failure is SILENT -- a matcher
      that stops matching reports nothing at all. Four were found and widened during
      wave 9 (`scripts/gates/check-ci-parity.ts:84` and `:409`,
      `scripts/gates/check-suppression-liveness.ts:550`, `scripts/gate-bind.ts:1667`), one of
      which condemned NINE live parity exemptions in a single run and handed the reader
      a FIX that deletes them. `scripts/gates/check-ci-fetch-integrity.ts:60` was widened for
      the same reason. Deleting a twin before this sweep converts a guarded gate into an
      unguarded one with no red anywhere to say so.
      **THE SWEEP RAN 2026-09-08, two read-only agents over disjoint slices, and it found
      ELEVEN more.** Their baselines disagreed and each was wrong once, so the numbers
      below are mine: 77 `check-*.sh`, 120 `check_*.py`, **45 of them py-only**, and 0
      `.py` under `.ci/scripts/test/gates/`. Six are now fixed, each with a control proven
      to fire: `.ci/rediacc_ci/tests/gates/test_gate_ci_parity.py` plants a `check_planted_port.py` step (the GATE_SHAPED
      widening above had NO control until then); `.ci/rediacc_ci/tests/gates/test_gate_paths_exist.py` scans `*.py`
      with `in_doc` and `in_self` skips, without which it reported two FALSE findings from
      a docstring and a selftest fixture; `scripts/lib/gate-header.ts:262` normalises
      underscores, so a ported battery test no longer derives an id matching none of the
      149 hyphenated ones; `.ci/rediacc_ci/quality/ci_scans_tracked_paths.py` port AND twin widened in lockstep;
      that gate's EXEMPT lists; and a new drift control pinning the Stop hook's
      duplication cache signature to the counter's own corpus.
      **TWO ARE TRIAGE JOBS, NOT LINE EDITS, and that is the finding.** Widening
      `scripts/gates/check-shape-duplication.ts` to the Python families reports 62 NEW shapes at 3+
      copies, one of them SIXTEEN copies of five lines -- the shared `sys.path` hop and
      entry-point scaffold every port carries, so it is ONE scaffold wanting extraction
      rather than 62 defects. Widening `.ci/rediacc_ci/quality/toolchain_pins.py`'s A6 reports SEVENTEEN ported
      gates as trusting PATH instead of acquiring at the pin. **TRIAGED 2026-09-08 AND
      ALL SEVENTEEN ARE FALSE, for a reason better than the one first written here.**
      This note used to say A6 could not tell a pinned tool from an unpinned system
      binary; that was a guess and it was wrong. Every one of the seventeen is PROSE in a
      Python docstring or string literal, because A6's only comment filter is `^\s*#` and
      Python prose does not live behind `#` -- nine of them are literally the same
      sentence, the boilerplate `sys.path` hop note every ported shim carries. Zero
      execute a gated tool.
      **THE REAL DEFECT IS THE MIRROR IMAGE: A6 CANNOT FIRE ON PYTHON AT ALL.**
      `GATED_TOOLS` at `.ci/rediacc_ci/quality/toolchain_pins.py:201` is a hand-written
      four-tool string (shfmt, shellcheck, ruff, actionlint -- `git` is not in it), and
      `A6_INVOKE_RE` at `:464` requires WHITESPACE after the tool name, which is a bash
      command word. Driven: `proc.run(["ruff", "check"])` is False,
      `subprocess.run(["shellcheck","-S",p])` is False, `shellcheck -S warning foo.sh` is
      True. So widening the corpus as-is buys seventeen noise findings and ZERO
      capability: a Python gate that genuinely took ruff off PATH would sail through.
      Two structural facts follow. There is no Python `toolchain_acquire` --
      `.ci/rediacc_ci/core/toolchain.py` is a pins READER with no `check()` and no
      `acquire()`. And A6 is file-local while a ported gate is shim plus library, so
      widening only `.ci/scripts/**` is vacuous by construction: the registered
      `.ci/scripts/quality/check_python_lint.py` holds neither the invocation nor the
      acquisition, both of which live in `.ci/rediacc_ci/quality/python_lint.py`, outside
      the corpus entirely. Both
      widenings were driven, measured and REVERTED, with the measurement written into each
      file above its constant. **Still open:** `scripts/gates/check-ci-parity.ts:925` (gate tests as
      `test-*.sh`, right while all 149 are bash), `scripts/gen/validate-cli-examples.ts:123-125`,
      `.ci/rediacc_ci/quality/pool_writer_safety.py:543`,
      `.ci/rediacc_ci/quality/workflows.py:666`,
      `.ci/rediacc_ci/quality/git_op_conditionals.py`, plus four
      FLOOR/COUNT findings that fail LOUD rather than silent as twins are deleted
      (`.ci/rediacc_ci/quality/gate_id_convention.py:229`,
      `.ci/rediacc_ci/security/shfmt.py:91` (`SHFMT_MIN_FILES`) whose margin goes 2.8x to 1.7x,
      `.ci/rediacc_ci/tests/test_battery.py:352`,
      `.ci/rediacc_ci/quality/pool_writer_safety.py:545`).
      AUDIT: DONE 2026-09-23 (audit): re-measured against the tree rather than against the
      box's own prose, which predates several deletions the box never recorded.
      **`run-all.sh` no longer exists, and all five of its cited blockers plus the
      `test_battery.py` TWIN issue are resolved.** `.ci/scripts/test/run-all.sh` is gone --
      `git log --all --diff-filter=D -- '*run-all.sh'` finds it retired at `1306a6539`
      ("run-all.sh is retired, the licensed battery runner carries every reader",
      2026-09-21), an ancestor of current HEAD `2ed7d6726` (`git merge-base
      --is-ancestor` confirmed). Verified per blocker, against the real tree:
      1. `docs/agent-reference/TRAPS.md` -- the trap moved to line 1465 (the file has grown
         past `:2463`) but its disposition is already `Enforced-By: JUDGMENT-ONLY`
         (`docs/agent-reference/TRAPS.md:1464-1465`), the exact settled disposition this box already committed to.
      2. `.ci/config/language-policy-baseline.json` -- `grep -n "run-all"` returns nothing;
         the entry the box named at `:423` is gone, drained.
      3. `.ci/scripts/test/gates/test-run-all-parallel.sh` -- does not exist. Its pytest
         replacement, `.ci/rediacc_ci/tests/gates/test_gate_run_all_parallel.py`, exists and
         its own docstring says it was "RETARGETED WITH ITS SUBJECT ... deleted once the
         shadow pair `w7p8-battery` held at K=5 over seven distinct trees."
         `grep -n "run-all" scripts/ci-runner/manifest.ts scripts/ci-runner/gates.lock.json`
         returns zero hits in both files.
      4. Shadow ledger pairing `battery.py` with `run-all.sh` -- exists:
         `.ci/shadow/w7p8-battery.observations.jsonl`, 9 rows, **7 `EQUIVALENT` over 7
         distinct tree ids and 6 distinct fingerprints** (plus 1 `ERROR_REFUSAL` and 1
         `VACUOUS_BOTH_EMPTY` row, neither counted toward K), comfortably clearing K=5.
      5. The ~10 `manifest.ts` "inside run-all.sh" BLOCKER strings -- zero remain (same grep
         as #3).
      6. `.ci/rediacc_ci/tests/test_battery.py`'s TWIN-reads-source-at-runtime case -- gone.
         Its own header now reads "IT WAS A DIFFERENTIAL AND IT IS NOT ONE ANY MORE ... The
         shell runner was deleted once the shadow pair `w7p8-battery` held at K=5 over seven
         distinct trees; only the cases that EXECUTED or READ it went with it"
         (`.ci/rediacc_ci/tests/test_battery.py:3`), and the isolation-comparison case that used to drive the
         extracted heredoc is now a synthetic-lock test with a docstring explaining exactly
         why the old comparison is gone (`.ci/rediacc_ci/tests/test_battery.py:187-190`).
      All remaining tracked hits for the string `run-all.sh` (`git grep -n "run-all\.sh"`)
      are historical/documentary: docstrings on the replacement modules explaining what they
      replaced (`.ci/rediacc_ci/battery.py:4,8,29,34,744`,
      `.ci/rediacc_ci/quality/battery_clean_tree.py`,
      `.ci/rediacc_ci/quality/pool_writer_safety.py`, `.ci/rediacc_ci/xdist_groups.py`) and
      frozen `.ci/shadow/w7p2-*.observations.jsonl` rows recorded before the deletion. None
      is a live call site. The C3 trap example this box's own census flagged
      (`.github/workflows/autopilot.yml:252` running the bash `check-resolved-threads.sh`
      while `ci.yml` ran the Python) is also resolved: `check-resolved-threads.sh` no longer
      exists anywhere in the tree; only `check_resolved_threads.py` remains and both
      workflow files now call it.
      **So the box's named subject -- deleting `run-all.sh` -- is DONE, by a wave this box's
      own text never recorded, and its "THREE BLOCKERS" / "TWO MORE" section is now entirely
      stale.** The box's other precondition, the coverage campaign, is measurably far along
      too but is not finished:
      **Quality-gate twins: 82 -> 9 bash files remain**, not the 77-ledgered/5-unledgered
      split the box's 2026-09-09 census (`agent/archive/2026-09-22-backfill/f4da5c2e/
      W7P5c-licence-census.md` -- itself still dated 2026-09-09 despite living in a
      "2026-09-22-backfill" archive directory; it was archived later, never re-run) measured.
      `ls .ci/scripts/quality/*.sh` today: `check-dead-case-arms.sh`,
      `check-plan-housekeeping.sh`, `check-profiler-coverage.sh`, `check-python-lint.sh`,
      `check-submodule-branches.sh`, `check-swallowed-failures.sh`, `check-trap-registry.sh`,
      `check-workflows.sh`, `typecheck-workers.sh` (this last one was one of the census's
      "5 quality gates with no ledger" and now has both a ledger and a port). All 9 already
      have a K=5 `EQUIVALENT` shadow ledger (verified live: 5-15 rows each for the first 8
      under `w7p2-*`, all EQUIVALENT, 4-9 distinct fingerprints; `typecheck-workers.sh`
      under `w7p4b-typecheck-workers`, 9 rows, all EQUIVALENT) and a live Python entry point
      registered as a `gates.lock.json` leaf (8 of 9; `check_submodule_branches.py` is
      called directly at `.github/workflows/ci-quality.yml:699` instead of through a leaf).
      **None of the 9 passes C3 today, and by design, not by oversight:** every one carries
      a permanent pytest differential with a live `TWIN = ...` constant reading the bash file
      (`.ci/rediacc_ci/tests/test_quality_swallowed_failures.py:16`, `.ci/rediacc_ci/tests/test_quality_trap_registry.py:17`,
      `.ci/rediacc_ci/tests/test_quality_python_lint.py:34`, `.ci/rediacc_ci/tests/test_quality_profiler_coverage.py:21`,
      `.ci/rediacc_ci/tests/test_quality_plan_housekeeping.py:34`, `.ci/rediacc_ci/tests/test_quality_typecheck_workers.py:32`) plus an
      explicit "INVARIANT 5 IS INTACT ... deleting it is W7 P5's job" line in the Python
      port's own docstring (`.ci/scripts/quality/check_dead_case_arms.py:62`, `.ci/scripts/quality/check_plan_housekeeping.py:32`,
      `.ci/scripts/quality/check_profiler_coverage.py:62`, `.ci/scripts/quality/check_python_lint.py:77`,
      `.ci/scripts/quality/check_submodule_branches.py:12`, `.ci/scripts/quality/check_swallowed_failures.py:13`,
      `.ci/scripts/quality/check_trap_registry.py:58`, `.ci/scripts/quality/check_workflows.py:33`) -- each one naming this box as
      the intended executor. The 73 other original quality-gate twins have already been
      deleted by other waves using exactly this pattern (freeze the differential to golden
      literals captured pre-deletion, drop the baseline line, one commit) -- see
      `430b54ede`, `0bb1a4c15`, `7a9bda6d7` for three worked examples already landed.
      **Gate tests: 149 -> 7 bash files remain.** `ls .ci/scripts/test/gates/*.sh`:
      `test-agent-session-archival.sh`, `test-blocker-golden-corpus.sh`,
      `test-bws-rotate.sh`, `test-media-r2.sh`, `test-run-sh.sh`, `test-runner-advice.sh`,
      `test-toolchain.sh` (142 of the original 149 already retired, not "0 of 149 have a
      ledger" as the box's stale prose still implies). `.ci/rediacc_ci/tests/gates/
      test_gate_*.py` now numbers 159. The twin-parity ledger the box's own driver ruled
      sufficient C1 evidence for gate tests (`.ci/shadow/twin-parity.ledger.jsonl`) still
      tracks the same **141 distinct subjects**, now over **572 rows, all 572 agreed** (was
      231 rows at the box's last count) -- the driver's C1-for-gate-tests ruling has not
      been overturned and remains the correct instrument; a raw shadow-gate K=5 ledger was
      never the right measure for this half of the census.
      **Answering the three re-derivation questions directly: (a) quality-gate twins with
      K=5 ledger evidence today: 9 of 9 remaining (100% of what is left; 73 of the original
      82 are already deleted, not "77 of 82 have a ledger"); (b) gate tests with equivalence
      evidence: 141 of the remaining population via twin-parity, per the standing driver
      ruling; (c) the true blocker count for `run-all.sh` specifically: ZERO -- it is
      deleted and none of its five cited blockers, nor the `test_battery.py` issue, remain
      live.**
      **Is the box ready for a deletion writer? Split answer.** The box's own named subject
      (`run-all.sh`) needs no further writer work -- it is done. The broader coverage-campaign
      mandate is NOT finished but is now small and mechanical: 9 quality-gate twins + 7
      gate-test twins = **16 files remain**, each already licensed on C1 and C2, each
      blocked only by the SAME already-proven mechanical sequence that four prior commits
      (`430b54ede`, `0bb1a4c15`, `7a9bda6d7`, `1306a6539`) already executed successfully and
      documented in their own messages. This is writer-sub-agent scope, not Plan-agent scope:
      no new design decision remains, only repeating a proven pattern across 16 named files.
      **The exact deletion sequence for the next writer**, mirroring the four prior commits'
      own template:
      1. For each of the 9 quality-gate `.sh` twins: freeze its differential's `TWIN`-read
         comparison to golden literals captured from the live bash output before deletion
         (as `430b54ede` did for `release-age.sh`/`age-check.sh`), update the "INVARIANT 5 IS
         INTACT ... deletion is W7 P5's job" docstring line to say it happened, delete the
         `.sh` file, and drop its line from `.ci/config/language-policy-baseline.json`.
      2. For each of the 7 remaining `.ci/scripts/test/gates/test-*.sh` gate tests: confirm
         each already has a `test_gate_*.py` counterpart collected under `check:ci-pytest`
         (verify per file, not assumed), delete the `.sh`, and remove its
         `scripts/ci-runner/manifest.ts` + `gates.lock.json` entries.
      3. Re-run `check:ci-language-policy`, `check:ci-dead-bash`, `check:ci-parity` and the
         full pytest suite after each batch, exactly as `1306a6539`'s own commit message
         describes doing.
      4. Ride the baseline drain in the SAME commit as each deletion batch (never a following
         one), per this box's own acceptance rule and the shape TRAPS entry 85 already
         describes (`check_language_policy.py` reads tree state, not commit boundaries).
      5. `w7p2-stagingtag`'s permanent carve-out (`check-staging-tag-guard.sh`) stays
         undeleted; it is disqualified by design and needs a human sign-off line, not a
         re-run (unaffected by this audit).
      NOT ticked, nothing else touched in this box.
      AUDIT: DONE 2026-09-23 (writer): **FOUR of the sixteen deleted, and the audit above is
      wrong that the other twelve are "small and mechanical".** Each of the twelve is blocked
      by something named below, verified against the enforcing code rather than inferred, and
      none of the twelve is blocked by a missing licence -- C1 holds for all sixteen.
      **DELETED, each on the four prior commits' own pattern, one at a time, verified before
      the next was started.** `.ci/scripts/quality/check-workflows.sh` (blob
      `8b15557789b1fe8615c572a1076e6a3d7bc5bdca`, ledger `w7p2-workflows`, 10 rows / 10 trees /
      5 fingerprints); `check-plan-housekeeping.sh` (`f985c1c71a9239eaa6eeda699b7d7235d839669b`,
      `w7p2-plan-housekeeping`, 5/5/5); `check-dead-case-arms.sh`
      (`19c18e3f491528ad54c0e1fb8832f626b0eade9d`, `w7p2-dead-case-arms`, 5/5/5);
      `check-swallowed-failures.sh` (`e7b12ba15c41569a88ea8065007e246ab948f2ee`,
      `w7p2-swallowed-failures`, 10/10/4). Every ledger verdict `EQUIVALENT`.
      **THE LEDGER WAS NOT TREATED AS SUFFICIENT.** Before each deletion the twin and its port
      were driven side by side on this tree, stdout and stderr captured SEPARATELY, and each
      pairing included a fixture that genuinely EXITED 1 and named a finding, so no comparison
      was made over two silent runs: 6 drives for `check-workflows.sh` (3 fixtures x `CI`
      set/unset), 2 for `check-dead-case-arms.sh` (clean real tree, and one dead arm beside one
      live arm), 2 for `check-swallowed-failures.sh` (clean real tree, and one swallowed
      capture). Byte-identical on every stream. `check-plan-housekeeping.sh` needed no drive:
      its differential already held the twin's `sed` programs as frozen literals and only two
      cases opened the twin's SOURCE.
      **AND EACH REPOINT WAS PLANT-CONTROLLED.** After repointing, a defect was planted into
      the PORT and the suite required to red, then the port restored and its git blob compared
      to prove the restore was byte-identical: `workflows.py` (1 failed / 8 passed),
      `dead_case_arms.py` (1/17), `swallowed_failures.py` (3/18, including both repointed
      source-readers), `plan_housekeeping.py` (1/38).
      **WHAT THE FREEZES ACTUALLY DID, since "freeze to goldens" hides three different moves.**
      `test_quality_swallowed_failures.py` keeps its differential FULLY LIVE: the twin's 172-line
      awk program moved from a runtime slice into an `AWK_PROGRAM` literal, verified equal to
      the live extraction byte for byte, and all 30 cases still pipe real input through the real
      `awk`. Freezing the VERDICTS instead would have turned a differential into an assertion
      about remembered text. `test_quality_plan_housekeeping.py` froze only the two twin-source
      claims and KEPT the port-side half of each, which is the half that can still regress.
      `workflow_rule.py`, `test_gate_dead_case_arms.py`, `test_gate_media_helpers.py` and
      `test_gate_swallowed_failures.py` are SUBJECT repoints, not freezes: they drove the bash
      gate and now drive `sys.executable <gate>.py`.
      **TWO CONSEQUENCES THE PER-FILE LOOP MISSED AND THE FULL SUITE CAUGHT, both fixed here.**
      (1) `docs/agent-reference/TRAPS.md:309` and `:532` both carried
      `Enforced-By: file:.ci/scripts/quality/check-swallowed-failures.sh`, and
      `trap_registry.py` requires a `file:` pointer to resolve on disk -- the same class as
      `errexit-rearmed-in-a-tested-command`, but with a live counterpart, so both were repointed
      to `check_swallowed_failures.py` (manifest-reachable at `scripts/ci-runner/manifest.ts:835`) rather than to
      `JUDGMENT-ONLY`. `check:ci-trap-registry` rc=0, 94 entries, 12 file pointers.
      (2) `test_quality_control_vacuity.py`'s substitution classifier stopped discriminating:
      with the directory down to four files ALL FOUR build by substitution, so
      `len(substituting) < len(_gate_files())` could only fail. The population was WIDENED to
      both gate directories (5 substituting, 1 not) rather than the claim weakened, matching what
      that file's own docstring already did for `has_control`, and the fix was controlled by
      planting an unconditional `return True` into `builds_by_substitution` (5 failed / 7 passed).
      **A SECOND THING THE PER-FILE LOOP COULD NOT SEE, and it is a finding about the gate
      rather than about this box.** `check:ci-language-policy` CANNOT REACH its own
      stale-baseline ratchet while any NEW bash file exists: `check_language_policy.py`'s `run()`
      returns 1 on the `added` set at `:771-788`, before the `drained` check at `:789`. A peer's
      new bash files sat in `added` throughout, so a plain run could not tell a drained baseline
      from an un-drained one -- the control was re-added to the baseline as a plant and the output
      came back BYTE-IDENTICAL. The ratchet was driven instead through the
      `LANGUAGE_POLICY_BASELINE` env seam against a copy, and fires in both directions: rc=1
      "1 baselined bash file(s) are gone from the tree" un-drained, rc=0 drained. The real drain
      is composition-checked, not size-checked: 143 -> 139, removed exactly the four files above,
      **ADDED empty**.
      **THE TWELVE THAT WERE NOT DELETED, each with the code that blocks it.** Five quality twins:
      * `check-trap-registry.sh` -- a PEER IS EDITING IT RIGHT NOW. The staged worktree bumps
        `TRAP_FLOOR` 90 -> 94 in the twin and `TRAP_FLOOR_DEFAULT` 90 -> 94 in the port, in
        lockstep. Deleting it destroys uncommitted work by a session still treating it as live.
      * `check-submodule-branches.sh` -- a LIVE call site, `.ci/legacy/run-legacy.sh:154`, inside
        `quality_submodules()`. The repoint is small but it is a CALL-SITE change in W7P6's
        territory, not a freeze, and `.github/workflows/ci-quality.yml:699` already runs the Python, so the pair is
        the C3 shape this box's own census flagged for `check-resolved-threads.sh`.
      * `check-profiler-coverage.sh` -- `test_quality_profiler_coverage.py` extracts the twin's
        shell functions BY NAME and runs them against the port over
        `.github/workflows/*.yml`, the REAL corpus, in 6 of its cases. Freezing that means
        per-workflow goldens that go stale the next time any workflow is edited, which is a
        churning golden rather than a frozen one. The honest exit is a redesign to synthetic
        specimens, which is a design decision and not this pattern.
      * `check-python-lint.sh` -- `.ci/rediacc_ci/tests/test_quality_python_lint.py:56` COPIES the twin into a git
        fixture and runs it; freezable to a goldens directory exactly as `0bb1a4c15` did for
        `bws-env`, so this one is genuinely mechanical but large. Also `.ci/rediacc_ci/tests/test_core_dockerx.py:489`
        greps the twin for its `exit 77` literal.
      * `typecheck-workers.sh` -- the twin carries the `---- gate ----` REGISTRATION and
        `.ci/rediacc_ci/tests/test_quality_typecheck_workers.py:442` asserts the PORT carries none. Deleting it moves
        a gate registration, which is wiring rather than a freeze.
      All seven gate tests, and **the audit above is wrong that any of them is ready**:
      * `test-run-sh.sh` -- `.github/workflows/ci.yml:547` runs it as a named step, and
        `test_gate_plant_proofs.py` drives it as `BASH_SUBJECT` at six sites.
      * `test-toolchain.sh` -- `.github/workflows/ci.yml:550` runs it; it is a PERMANENT
        `file:` exemption on `.ci/policy/.language-policy-allowlist` (the gate prints
        `exempt file:.ci/scripts/test/gates/test-toolchain.sh` every run); and
        `test_gate_toolchain.py` declares NO `BASH_TWIN`, so it has zero twin-parity rows and
        no C1 evidence at all. Three independent reasons.
      * `test-media-r2.sh` -- `.ci/rediacc_ci/tests/gates/test_gate_media_docs.py:245` and `:247` EXECUTES `bash <twin>` twice.
      * `test-blocker-golden-corpus.sh` -- the twin has an `--emit` verb that RE-RECORDS the
        golden corpus and the port has none, so the port is not a replacement; the port's own
        failure message tells the reader to run `bash <twin> --emit`.
      * `test-runner-advice.sh` -- its manifest entry is the only one of the seven carrying
        `reads: ['tree:repo']`, and `.ci/rediacc_ci/tests/gates/test_gate_runner_advice.py:16` says outright that
        `REAL_TREE_TWIN = True` "buys the serialisation". That serialisation is looked up
        through the LOCK entry for the twin's basename, so deleting the entry drops it
        SILENTLY -- a scheduling decision, not a deletion.
      * `test-bws-rotate.sh` and `test-agent-session-archival.sh` -- brand-new peer work this
        session was told not to touch; neither has a `test_gate_*.py` counterpart.
      **FLOORS MOVED IN THE SAME CHANGE, per the 2026-09-21 ruling.**
      `check-shape-duplication.ts`: the `.ci/scripts/quality/check-*.sh` family floor 8 -> 4 and
      the corpus floor 138 -> 134, measured against the tracked tree (126 + 4 + 5, minus the
      opted-out file) rather than subtracted. **Only two of those four corpus units are this
      session's**, and the comment beside the floor says so rather than absorbing the rest: a
      concurrent writer retired `.ci/scripts/test/gates/test-bws-rotate.sh` and then
      `.ci/scripts/test/gates/test-agent-session-archival.sh` midway through, taking the gate-test
      family 7 -> 5 while this wave ran. A floor re-measured inside a live tree has to name whose
      deletion moved it, or the next reader reconstructs one writer's history from one number.
      **That concurrency is also why the seven gate-test rows above will keep moving**: two of the
      seven this audit triaged are already gone by another hand, so the residue is five, not seven,
      and the five that remain are the five carrying the blockers named below.
      `scripts/data/enumeration-vacuity-baseline.json` drained 34 -> 33, removed exactly
      `check-swallowed-failures.sh`, ADDED empty.
      **GATES RUN AT THE END, all rc=0:** `check:ci-parity` (349 gates, 2 workflow scopes, 9
      exempt, agrees both directions), `check:ci-gate-reachability-coverage` (339 registrations,
      control fired), `check:ci-dead-bash` (292 shell files, 1016 functions, 0 findings),
      `check:ci-enumeration-vacuity`, `check:ci-trap-registry`, and the language-policy ratchet
      through its env seam. `check:ci-shape-duplication` is rc=1 on ONE pre-existing finding that
      is not this session's -- a 3-copy shape across `check-env-credential-drift.ts`,
      `check-pr-task-trailers.ts` and `check-video-player-invariants.ts`, the last of which is a
      peer's staged edit; proven pre-existing by restoring the deleted file and the old floor and
      re-running, which reproduced the identical finding.
      **THE FULL PYTEST SUITE: 9900 passed, 60 failed, 6 errors before these fixes; 54 failed
      after.** The six this session closed were its own (3 trap-registry, 1 control-vacuity, 2
      collateral). Of the 54 remaining, none is in a module this session edited and none names a
      file it touched; they sit in peer-modified files (`onboard.py`, `trap_registry.py`,
      `python-env-registry.json`, `worklist-env-registry.json`, `gates.lock.json`) or are
      environmental (`npm` absent for `test_build_build_json.py`, ruff for
      `test_quality_python_lint.py`). **One of them is a real finding worth its own box:**
      `test_gate_vacuity_floors.py::test_shfmt_accepts_the_real_corpus` fails because shfmt's
      `.ci/**/*.sh` glob reaches into the GITIGNORED `.ci/cache/toolchain/uv-cache/` and lints
      sdist payloads (`.../pypi/pyyaml/6.0.2/.../libyaml.sh.orig`). That cache is dated
      2026-09-22, before this session, so the failure is pre-existing; the gate should exclude
      `.ci/cache/`.
      NOT ticked. Twelve of the sixteen remain, and the four prior commits' pattern does not
      reach any of them unchanged.
      AUDIT: DONE 2026-09-23 (writer, `check-python-lint.sh` only): **NOT DELETED, and the
      audit above is right that it is blocked but wrong about WHICH thing blocks it.** The
      previous entry named two obstacles for this file -- a differential that copies the twin
      into a git fixture and runs it, and the `.ci/rediacc_ci/tests/test_core_dockerx.py:489`
      grep of the twin for its
      `exit 77` literal -- and called the pair "genuinely mechanical but large". Driven against
      the tree, the dockerx grep is not an obstacle at all and the fixture is a harder one than
      "large".
      **THE LICENCE IS NOT THE PROBLEM. C1 and C2 both hold, verified live.**
      `.ci/shadow/w7p2-python-lint.observations.jsonl` carries **6 rows, all `EQUIVALENT`, over
      6 distinct tree ids and 6 distinct fingerprints**, every row pairing
      `bash .ci/scripts/quality/check-python-lint.sh` against
      `python3 -m rediacc_ci.quality.python_lint`. That clears K=5 with >=2 fingerprints
      comfortably. The Python side is live and registered: `package.json:161`
      (`check:ci-python-lint` -> `.ci/scripts/quality/check_python_lint.py`),
      `scripts/ci-runner/manifest.ts:1542-1545` and `scripts/ci-runner/gates.lock.json:1610-1614`,
      all three already naming the `.py` leaf and none naming the `.sh`. **There is no
      manifest or lock row to remove for this file**, so step 4 of the box's own sequence is a
      no-op here and `gen:gates-lock` was not run.
      **QUESTION 3 ANSWERED, AND IT IS A FALSE BLOCKER.**
      `.ci/rediacc_ci/tests/test_core_dockerx.py:489` is a CONTENT grep, not a call site or a
      path reference: `test_the_cannot_run_code_agrees_with_every_other_definition_in_the_repo`
      reads four files and pattern-matches each for the 77 literal, using
      `^\s*exit (\d+)\s*$` for the twin and asserting `77 in matches` (membership rather than
      equality, because the bash file also `exit 1`s in eight other places --
      `grep -nP '^\s*exit \d+\s*$'` returns 9 lines, `:194` being the 77). The repoint is one
      line and would be STRONGER than what it replaces:
      `.ci/rediacc_ci/quality/python_lint.py:175` is `EXIT_CANNOT_RUN = 77`, so the port takes
      the `EXIT_CANNOT_RUN = (\d+)` pattern and the equality assertion the other two
      constant-naming files already get, not the membership one. This blocker is retired as a
      finding; it is not what stops the deletion.
      **WHAT ACTUALLY STOPS IT: THE DIFFERENTIAL'S FIXTURE IS LIVE REPO CONTENT, SO ITS
      GOLDENS WOULD CHURN AND COULD NOT BE RE-RECORDED.**
      `.ci/rediacc_ci/tests/test_quality_python_lint.py:41-83` `build()` copies the REAL tree
      into each specimen --
      `.ci/scripts/lib/` wholesale, `pyproject.toml`, `.devcontainer/toolchain.env`, six named
      `rediacc_ci` modules, and (in 8 of the 9 twin executions -- the floor case is the one
      exception, and it passes `with_core=False` precisely to starve the corpus)
      `shutil.copytree` of the ENTIRE
      `.ci/rediacc_ci/core/` directory. The twin then lints that specimen and prints the corpus
      SIZE on every run. Driven through the test module's own `build()` and `run_both()` in a
      tmpdir, two specimens differing by exactly one added `.py`:
      `baseline exit=1 ['info: linting 33 Python file(s) with ruff 0.16.1']` against
      `one extra .py exit=1 ['info: linting 34 Python file(s) with ruff 0.16.1']`. The
      committed ledger shows the same line, and `18 files already formatted` beside it, so BOTH
      of the gate's two stages emit the count.
      **That number is a function of how many modules `.ci/rediacc_ci/core/` holds, and that
      directory is one of the fastest-moving in the tree:** 25 `.py` today, **21 of them added
      since 2026-08-20**, and three more in flight in this very tree
      (`core/account.py` and `core/shadow_driver.py` staged, `core/local_common.py` untracked).
      A golden recorded today reds the next time any peer adds a core module, and once the twin
      is deleted it **cannot be re-recorded** -- only hand-edited, which destroys the one
      property `.ci/rediacc_ci/tests/frozen.py:4-5` says makes a golden evidence rather than a
      restatement of the port ("Nothing in a golden is a hand-written expectation").
      Masking the count is not the exit either: `.ci/rediacc_ci/tests/frozen.py:10` rules that
      a golden masking a
      value the differential compared is weaker than the comparison it replaced, and here the
      masked value is the anti-vacuity signal itself, the corpus size the `MIN_PY_FILES = 10`
      floor exists to defend.
      **AND THE TWIN IS RED ON THIS TREE RIGHT NOW, so there is no clean recording to take.**
      `.ci/cache/toolchain/uv-tools/pytest/bin/pytest .ci/rediacc_ci/tests/test_quality_python_lint.py`
      is **3 failed / 12 passed**: `test_differential[a clean corpus passes]`,
      `test_differential[a shebang with git mode 100755 is fine, and no shebang with 100644 is
      too]` and `test_a_clean_run_still_prints_ruffs_own_pass_line` all fail on
      `assert 1 == 0`. The cause is not the port and not the test: a peer's UNTRACKED
      `.ci/rediacc_ci/core/local_common.py:287` trips `PERF401 Use list.extend to create a
      transformed list`, gets copied into every specimen by the `copytree`, and makes the "clean
      corpus" cases not clean. The real gate agrees -- `npm run check:ci-python-lint` is
      **rc=1** on this tree with the identical finding, and `ruff check --no-cache
      .ci/rediacc_ci/core/` reproduces it in isolation. **Freezing now would enshrine a peer's
      transient diagnostic, path and line numbers included, into three permanent goldens that
      can never be re-recorded.** That file belongs to the account.sh/local-common.sh port this
      writer was scoped out of, so it was not touched; it is reported as a live finding instead.
      **THE HONEST EXIT IS THE SAME ONE `check-profiler-coverage.sh` GOT, AND FOR THE SAME
      REASON.** Making this freezable means making the fixture HERMETIC -- a fixed synthetic
      padding corpus clearing `MIN_PY_FILES` instead of `copytree` of a live package -- which
      changes what the differential compares (the test's own docstring at `:21-22` leans on the
      gate linting its own port file) and must be designed and validated WHILE the twin is
      still alive, then recorded. That is a design decision, not the four-step pattern. Twin
      blob for whoever picks it up: `471b915b87984c59aeaca380951aa3dd5bd3b702` (worktree and
      `HEAD:` agree).
      **NOTHING WAS CHANGED FOR THIS FILE.** No deletion, no golden written, no
      `.ci/config/language-policy-baseline.json:73` drain (the ratchet must ride the deletion
      commit and there is none), no `test_core_dockerx.py` repoint (pointless while the twin
      stays), no manifest or lock edit (there was never a row), and none of the other eleven
      skipped files touched. NOT ticked; eleven of the sixteen remain plus this one, and this
      one is now blocked by a NAMED redesign rather than by an unexamined "large".
      AUDIT: DONE 2026-09-23 (writer, fixture only): **THE FIXTURE IS NOW HERMETIC. THE FILE IS STILL NOT DELETED, AND THAT REMAINS SEPARATE WORK.** The named redesign the entry above blocks on is implemented: `.ci/rediacc_ci/tests/test_quality_python_lint.py`'s `build()` no longer `copytree`s the live `.ci/rediacc_ci/core/` into its specimens. The 8 real files it already copies (6 `PACKAGE_FILES` plus the 2 quality-module files) are topped up by 4 fixed synthetic one-line modules, `_pad0.py` through `_pad3.py`, to 12 against the `MIN_PY_FILES = 10` floor. Nothing in `.ci/rediacc_ci/core/` was touched.
      **THE PREDICTED CHURN WAS NOT HYPOTHETICAL, AND IT FIRED TWICE DURING THIS ONE TASK.** The suite was **3 failed / 12 passed** on entry, the same three cases the entry above names, but no longer for `core/local_common.py`: the cause today is a peer's untracked `.ci/rediacc_ci/core/devbox.py:185` failing `ruff format`, copied into every specimen by the `copytree`. While the task ran, that same peer added a second untracked file, `core/devbox_shadow_driver.py`, which the real gate also reports unformatted. A golden frozen at any point in this task's span would have enshrined a different peer's transient diagnostic each time.
      **AFTER: 15 passed / 0 failed**, with no expected-behaviour change in any of the 9 `run_both` executions, none of which ever asserted on `core/`'s content. Corpus sizes driven through the test module's own `build()`: `with_padding=True` gives `info: linting 12 Python file(s)`, and the floor case's `with_padding=False` stays at **8 files** and still refuses with `VACUOUS INPUT: only 8 Python file(s) found, expected at least 10`.
      **BOTH CONTROLS FIRED ON THE REAL SUITE, NOT ONLY IN THEORY.** Planting a `ruff` F821 into the padding content reds the three clean cases (3 failed / 12 passed), which proves the padding is genuinely inside the linted corpus rather than decorative; flipping the floor case to `with_padding=True` reds `test_the_file_floor_refuses_rather_than_reporting_clean` (1 failed / 14 passed), which proves `with_padding=False` is load-bearing. Both plants were removed and the suite returned to 15 passed.
      **`MIN_PY_FILES` WAS NOT MOVED ON EITHER SIDE**, and neither `.ci/scripts/quality/check-python-lint.sh` nor `.ci/rediacc_ci/quality/python_lint.py` was edited. `npm run check:ci-python-lint` is still **rc=1** on this tree, and every finding is in the two peer-owned `core/` files above; `ruff check` and `ruff format --check` on the changed test file alone are both clean. The remaining deletion work is unchanged and still owed: freeze the twin's output as a golden, drain `.ci/config/language-policy-baseline.json:73`, repoint `.ci/rediacc_ci/tests/test_core_dockerx.py:489` at `EXIT_CANNOT_RUN`, and re-verify C1/C2 licensing at that time. NOT ticked.
      AUDIT: DONE 2026-09-23 (writer, `check-python-lint.sh` only): **DELETED.** All four pieces of debt the entry above listed as owed are discharged in this one change, on the exact sequence `430b54ede`, `0bb1a4c15`, `7a9bda6d7` and `1306a6539` established. The licence was re-verified live before anything was removed: `.ci/shadow/w7p2-python-lint.observations.jsonl` still carries 6 rows, all `EQUIVALENT`, over 6 distinct trees and 6 distinct fingerprints, and `package.json`, `scripts/ci-runner/manifest.ts` and `scripts/ci-runner/gates.lock.json` still name only the `.py` leaf, so there was no manifest or lock row to remove and `gen:gates-lock` was not run.
      **THE GOLDENS ARE AT `.ci/rediacc_ci/tests/goldens/python-lint/`, 8 files, and every provenance header reads `# twin .ci/scripts/quality/check-python-lint.sh blob 471b915b87984c59aeaca380951aa3dd5bd3b702`.** That sha was taken with `git rev-parse HEAD:` and cross-checked against `git hash-object` on the worktree copy by the recorder itself, which refuses to write if the two disagree, so the recording describes the tracked bytes rather than a local edit. The 9 twin executions collapse to 8 recordings because `test_a_clean_run_still_prints_ruffs_own_pass_line` drives the same specimen as `a clean corpus passes` and therefore reads the same golden. `test_the_twin_is_gone_and_its_recording_names_it` asserts both halves: the `.sh` is absent AND all 8 headers name it.
      **ONE DIFFERENCE BETWEEN THE RECORDED FIXTURE AND THE LIVE ONE, DRIVEN RATHER THAN ASSUMED.** The recording ran the twin from INSIDE the specimen, because the twin derives its root from `$BASH_SOURCE`, so `build()` copied the `.sh` in; after the deletion it cannot. Before deleting anything, the port was run over a specimen with the `.sh` removed and re-committed, across all 8 cases, and reproduced every recording byte for byte on both streams. `build()` no longer copies the twin and the module docstring says why.
      **FOUR CONTROLS, EACH WATCHED GOING RED ON THE REAL SUITE AND THEN REMOVED**, with `.ci/rediacc_ci/quality/python_lint.py` restored from a pre-plant copy and re-verified byte-identical by `sha256sum` after each mutation (the digest is deliberately not quoted here: a hex run of that shape reads as a git object to `check:ci-plan-citations`, and a sha256 is not one). (1) Changing one word of the green success line ("format" to "formatting") reds exactly the 3 cases that exit 0. (2) Moving one golden out of the directory reds 4 tests, `test_every_case_has_a_golden_and_no_golden_is_orphaned` among them, which is the anti-vacuity half. (3) Changing one word of the `NOT skipping` line reds exactly `test_a_missing_ruff_is_77_and_not_1`, proving the 77 recording is genuinely compared and not merely present. (4) Restoring the OLD `check-shape-duplication.ts` floors reds the gate with "family .ci/scripts/quality/check-*.sh has 3 tracked file(s), below its floor of 4", proving the floor move below was required rather than cosmetic.
      **THE BASELINE DRAIN RODE THE DELETION, and the ADDED side was diffed rather than the sizes compared.** `.ci/config/language-policy-baseline.json` loses exactly one line, `.ci/scripts/quality/check-python-lint.sh`; `git diff HEAD` on that file shows ZERO added lines. `check:ci-language-policy` is rc=0 at 266 bash file(s), 138 frozen (was 139), "none added". Floors moved in the same change per the 2026-09-21 ruling: `check-shape-duplication.ts`'s `.ci/scripts/quality/check-*.sh` family 4 -> 3 and the corpus 134 -> 133, measured against the tracked tree (126 + 3 + 5, minus the opted-out file) rather than subtracted.
      **`test_core_dockerx.py`'s 77-contract row is repointed, and it is now STRONGER.** The old row read the twin for `^\s*exit (\d+)\s*$` and could only assert MEMBERSHIP, because the bash file carried nine such lines. The new row reads `.ci/rediacc_ci/quality/python_lint.py` for `EXIT_CANNOT_RUN = (\d+)` and asserts EQUALITY, the same shape the two other constant-naming files already get.
      **A PRE-EXISTING RED WAS FOUND IN THAT SAME FUNCTION AND FIXED, and it is NOT part of this deletion.** Its sibling row still pointed at `.ci/scripts/security/shfmt.sh`, which is absent from HEAD (retired by an earlier bash-twin wave, `02dc20665` or one of its neighbours), so `test_the_cannot_run_code_agrees_with_every_other_definition_in_the_repo` had been raising `FileNotFoundError` and ruling on nothing. It is repointed at `.ci/rediacc_ci/security/shfmt.py`, which writes a bare `return 77` among four bare numeric returns, so that row keeps MEMBERSHIP: exactly as strong as what it replaces and no stronger. Flagged rather than buried because nobody asked for it and it is somebody else's wave's debt.
      **GATES RE-RUN:** `check:ci-language-policy` rc=0, `check:ci-dead-bash` rc=0 (285 shell files, 957 functions, 0 findings), `check:ci-parity` rc=0 (347 manifest gates, 2 workflow scopes, 9 exempt, agrees both directions), and `ruff check` plus `ruff format --check` clean on all four changed Python files under the pinned ruff 0.16.1. `check:ci-shape-duplication` is rc=1 on ONE finding, the SAME pre-existing 3-copy shape across `check-env-credential-drift.ts`, `check-pr-task-trailers.ts` and `check-video-player-invariants.ts` that the audit above already recorded; none of those three files is touched here. `test_quality_python_lint.py` is 18 passed (was 15: the three added are the corpus check, the non-vacuous-green check and the planted-defect control) and `test_core_dockerx.py` 41 passed, 59 together.
      **THE FULL `check:ci-pytest` SUITE: 17,705 passed, 54 failed, 6 errors in 1,066 seconds**, which is the same 54 the audit above recorded as pre-existing, and the strings `python_lint`, `test_core_dockerx`, `check_python_lint` and `goldens/python-lint` appear ZERO times among the 60 `FAILED` and `ERROR` lines.
      Two that could plausibly have been this change were reproduced and attributed rather than assumed: `test_gate_gate_anti_vacuity.py::test_validator_rejects_empty_tree` fails on `.ci/scripts/quality/check_bws_map.py`, a peer's file, while `check_python_lint.py`'s own row passes; and `test_gate_docs_gen.py` re-runs clean through `npx tsx scripts/gen/gen-docs.ts --verify`, so those three were a mid-run race with a concurrent writer.
      `check:ci-python-lint` itself is rc=1 on ONE finding, an EXE001 mode on the peer-owned `.ci/rediacc_ci/core/devbox_shadow_driver.py`, with lint and format clean across all 1,117 files.
      `check:ci-plan-citations` adds nothing on this note's own lines, checked with `PLAN_CITATIONS_MAX_SHOWN=5000` rather than trusting the 40-row truncation, and `check:ci-prose-style` adds no blocking finding in any file this change touches.
      NOT ticked, because the box is the whole 16-file mandate and this retires ONE of it. Eleven of the sixteen remain, each blocked by what the audit above names; `check-python-lint.sh` is no longer among them.
- [x] **W7P6 C, 3 writers** The 142 unnamed files (P-C). Port groups above; allowlist the 7-8
      named. Resolve the missing allowlist kind for `bootstrap.sh` before the strict flip.
      **STARTED 2026-09-09, 1 of ~37 free files ported, and the box's own numbers all moved.**
      Baseline is 513 now (515 before this box's own two allowlist entries), not 521/142.
      Re-derived the residue directly from the baseline: **137 files**, of which **93 block
      on an unported/in-flight library** and **44 are portable today** by an anchored
      `source`/`. ` grep against all 14 real bash libs (not just the 9 named). After
      removing files already done elsewhere (below) and `run-all.sh` (claimed by
      W7P3-BAT/W7P5-c), the true unstaffed remainder is **37 files, ~7,308 lines**, listed in
      the writer's scratchpad artifact.
      **`bootstrap.sh`'s allowlist gap was ALREADY RESOLVED**, by the W7P5-c census work
      earlier today -- `.ci/policy/.language-policy-allowlist` already carries `file:` entries
      for `bootstrap.sh` and 4 others. No work owed there; verified with a live run,
      `check:ci-language-policy` rc=0.
      **THIS BOX WAS ALREADY PARTLY DONE, DISCOVERED RATHER THAN REDONE.**
      `.ci/scripts/infra/ci_stop.py` is a full port of `ci-stop.sh`, committed at
      `1ae84c3e3` before this writer started, with a 10/10 differential -- its own docstring
      names this box. `.ci/scripts/test/lib/test-helpers.sh` and `workflow-rule.sh` are
      already ported (`harness.py`, `workflow_rule.py`), each used by 3+ gate-test ports.
      **Two files are DELIBERATELY NOT ported, and now say so in the allowlist rather than
      being silently skipped:** `.ci/scripts/test/lib/git-fixture.sh` and
      `.ci/scripts/test/mutate-check.sh` are each driven by a committed Python caller whose
      own docstring says outright that a reimplementation "would be a second instrument and
      this gate would then certify the wrong one." `file:` entries added, baseline drained
      513 (515 pre-entries) -> 513, 0 added, verified.
      **The one file actually ported: `resolve-version.sh` -> `.ci/rediacc_ci/version/`**,
      chosen because every call site invokes it as a subprocess -- never sourced, unlike its
      sibling `inject-env.sh` which is sourced into a caller's shell and cannot be ported the
      same way (same class as the already-exempted `.ci/docker/service/env.sh`). K=5 ledger
      (5 rows, verified), 13-case differential with a planted defect (a minor bump that
      forgot to reset patch to 0) driven red then restored byte-identical. Still invoked live
      from 4+ call sites and one workflow; none repointed.
      **A `dead_python.py` `MANUAL_ENTRY_POINTS` fragment landed concurrently while the
      writer verified rather than assumed it** -- it isolated its own files, confirmed the
      gate still failed with only the fragment present, restored them, and re-verified
      green, rather than taking credit for an edit it did not make.
      **A genuine full-suite reconciliation**, not an assumption: of 29 `check:ci-pytest`
      failures in a run spanning the whole session, 3 were caused by this box's file landing
      before its exemption did, and are now resolved and reverified; the other 26 sit in
      files this writer never touched, confirmed one by one against `git status` rather than
      waved off as a block.
      **SECOND WAVE 2026-09-09: the proxy family, 2 of 9 ported.** `proxy-lib.sh` (sourced
      only, no exec bit) is ported as a shared contract at `.ci/rediacc_ci/core/proxyx.py`;
      `proxy-cli-manifest.sh` and `proxy-docker-prepull.sh` are ported and byte-identical on
      both streams against the real bash twins. K=5 ledgers (5 rows each), 13/13 differential
      tests.
      **7 of 9 correctly left open**, needing toolchains this sandbox lacks (nfpm/dpkg/rpm/
      createrepo/gpg, a `private/renet` go build, passwordless sudo, a built `rdc` binary) --
      named rather than faked past.
      **A poisoned ledger row found and discarded, not left as evidence.** An early attempt
      produced a `VACUOUS_BOTH_EMPTY` row from a bad `--finding-re`, which permanently
      disqualifies a shadow-gate tree per invariant 5 ("a tree that ever disagreed stays
      disagreeing"). Recognised, discarded before assertion, re-recorded clean.
      **Two more `file:` allowlist entries applied by the driver**: `proxy-lib.sh`
      (sourced-only) and `.ci/scripts/version/inject-env.sh` (exports into the caller's
      shell, same class as the already-exempted `.ci/docker/service/env.sh`). Baseline
      drained 513 -> **511**, 0 added.
      **Both bash twins confirmed live and reachable** -- `generate-cli-manifest.sh` at
      `.github/workflows/cd-stage.yml:170`, `docker-prepull.sh` 8 times in `ct-tests.yml` -- neither repointed.
      **Remainder: 33 of the original 37**, 7 proxy files plus the 26 untouched standalones.
      **THIRD WAVE 2026-09-10: 3 more standalone files ported, 6 total ports today.**
      `ci-stop-elite.sh`, `collect-drill-diagnostics.sh`, `epic-context.sh` -- each byte-
      identical to its twin, K=5 ledger, permanent differential (18/18 tests). Two real bugs
      caught and fixed while writing the `ci-stop-elite` port: `capture_output=True` was
      silently swallowing the child docker process's own stdout (the twin lets `docker
      stop`/`rm`'s echo pass through), and Python's `print()` fully buffers against a pipe
      while the child writes directly to the inherited fd, so without `flush=True` the
      port's own text landed out of real order regardless of what was printed when.
      **A genuine ordering-equivalence argument, not a hand-wave**, for
      `collect-drill-diagnostics`: measured directly that `pathlib.glob()` is NOT
      alphabetical on this tmpfs for >2 entries, which is exactly why the twin's own bash
      loop calls `sort` explicitly and the port matches it with `sorted()` rather than
      relying on either side's natural order.
      **A genuine AWK quirk reproduced byte-for-byte rather than "fixed"**, for
      `epic-context`: a heading with two worklist items both carrying the epic's trailer
      prints that heading TWICE in the real bash -- confirmed against real `awk` before
      writing the port, not inferred, then reproduced deliberately and caught by a planted
      "fix" that both the differential and a pure-helper unit test independently reject.
      **Two more `file:` allowlist entries applied**: `ci-env.sh` (sourced-only, same class
      as `inject-env.sh`) and `fixture-suite.sh` (a bound fixture, doubly tied to bash
      because `.ci/rediacc_ci/quality/mutate_check.py:105-106` hardcodes its exact basename). Baseline drained
      511 -> **509**, 0 added.
      **Remainder: ~16 files** -- 7 proxy family needing toolchains this sandbox lacks, and
      ~9 standalone, several explicitly too large for one pass
      (`check-workflow-gates.sh` 1108 lines / 5 workflows, `sampler-linux.sh` 627,
      `scope-shadow.sh` 588).
      **FOURTH WAVE 2026-09-10: 4 more standalone files ported, 10 total ports today.**
      `canonicalise-gpg-key.sh` -> `build/canonicalise_gpg_key.py`, `sync-epic-block.sh` ->
      `pr/sync_epic_block.py`, `check-commands.sh` -> `security/check_commands.py`,
      `scope-reconcile-shadow.sh` -> `ci/scope_reconcile_shadow.py`. Driver-verified
      directly (not taken on the writer's word alone): all 4 module files exist and read as
      claimed, `PYTHONPATH=.ci python -m pytest` on the 4 new test files passes 50/50, all 4
      ledgers carry exactly 5 rows. `check:ci-dead-python` rc=0 confirms no
      `MANUAL_ENTRY_POINTS` fragment owed. `check:ci-language-policy` unaffected (509, 0
      added) -- no bash file touched, correctly, since none of these 4 twins are sourced.
      One named, deliberately-not-reproduced divergence in `scope_reconcile_shadow.py`: with
      `GITHUB_STEP_SUMMARY` unset and stdout redirected to a regular file, the twin's
      `tee -a /dev/stdout` corrupts its own output via a kernel file-offset race between two
      independent open file descriptions extending the same file -- deterministic but
      unreachable in production since `.github/workflows/ci.yml:1781` always sets the variable; the port
      duplicates cleanly instead, and a dedicated test pins the twin's divergence as still
      real rather than silently fixing it.
      **A genuine mid-session incident, fully repaired and driver-verified.** A scratch-repo
      setup script (used for the disposable K=5 ledger technique) got blocked by a pre-bash
      hook before its own commands ran, but a later `git commit` in the same script fell
      through its guard and ran against the real console repo at cwd, creating a real stray
      commit (`f01b05bc`, message "base") of the session's own pending, uncommitted changes.
      (8 characters, deliberately: this commit was discarded and resolves against nothing, and
      `check:ci-plan-citations` judges a 9+ hex token as an object it must resolve. Same for
      `784e0c1c` below. Do not lengthen either -- being unresolvable is the fact they record.)
      Caught via `git status`, repaired with `git reset --soft HEAD~1` + `git reset HEAD --
      .` (index-only, working tree untouched). Driver re-verified independently after the
      fact: `git show --stat f01b05bc` lists exactly the files this session had already
      modified and not committed (baseline, plan-boxes, allowlist, `dead_python.py`, the
      w7p5a-real-run-blockers pair); current `git status --porcelain` shows those same paths
      back as unstaged `M`, nothing lost, nothing duplicated, HEAD correctly back at
      `1a148adeb`.
      **Two real, live bugs found in the REGISTERED gate `check:ci-shell-commands`
      (`check-commands.sh`), reproduced faithfully in the port rather than silently
      "fixed" there** (fixing the bash twin's own behavior is out of this box's file
      ownership and changes live gate behavior repo-wide): a broken `\$\(` escaping
      combined with ugrep 7.5.0's mid-alternation anchor handling makes the whole
      "detect `$(cmd)`" branch permanently dead (verified: `printf 'a$(b\n' | grep -qE
      '$\('` does not match), and the narrow per-command filter is missing the
      `^[[:space:]]*if` branch the wide filter has, so `if seq 1 10; then` passes the
      gate silently (verified against the real gate: exit 0, "All commands are
      CI-compatible"). Triaged by the driver as `#18906e44`, verdict PLAN+SUBAGENT
      (fix touches a live security gate's regex + must re-sync the Python port/tests in
      lockstep, and could surface new real violations repo-wide) -- design going to
      `agent/plans/PLAN-shell-command-gate-regex-fix.md`, not folded into this box.
      **FIFTH WAVE 2026-09-10: 2 more standalone files ported, 12 total ports today.**
      `.ci/scripts/ci/profiler/panel.sh` -> `ci/profiler_panel.py` and
      `.ci/scripts/test/test-write-once-guard.sh` -> `deploy/write_once_guard_check.py`.
      Driver-verified directly: both modules exist, 36/36 new tests pass (23+13), both
      ledgers carry exactly 5 rows, `check:ci-dead-python` and `check:ci-language-policy`
      both clean, `git status` scoped to exactly the files claimed. No live defect found in
      either twin this wave (unlike `check-commands.sh` last wave); one named divergence
      pinned by a test (a non-numeric budget env var makes bash itself print a diagnostic
      carrying its own path/line, which the port does not forge).
      **The box's own "~12/~5 standalone" estimate was an undercount, corrected by a live
      re-derivation**: the free standalone set was actually 15 before this wave, 13 after --
      7 proxy family (unchanged, toolchain-blocked), 3 too-large (unchanged), 1 claimed by
      W7P3-BAT (`run-all.sh`), and 13 real standalone remain, each now individually
      characterized (portable-now vs operator-invoked-only vs credential-blocked vs
      binary-blocked vs no-byte-differential-obtainable) rather than lumped as one number --
      see the writer's full per-file breakdown in its report for the next wave to pick up.
      **Fragments owed to the driver, not yet applied**: 4 `check:ci-python-env-registry`
      pairs (`profiler_panel.py:*name`, `write_once_guard_check.py:PATH`, plus 2 test files'
      `HOME`/`PATH`) -- same class of driver-only fragment as W7P5-b's, and the SAME known
      blocker applies (the gate refuses a partial add while other sessions have unrelated new
      reads pending in the tree).
      **SIXTH WAVE 2026-09-10: 3 more standalone files ported, 15 total ports today.**
      `test-rdc-sh-env.sh` -> `security/rdc_sh_env_check.py`, `test-install-sh-config.sh` ->
      `release/install_sh_config_check.py`, `test-install-script.sh` ->
      `release/install_script_check.py`. Driver-verified directly: all 3 modules exist,
      41/41 new tests pass (14+12+15), all 3 ledgers at K=5, `check:ci-language-policy`
      clean; a transient `check:ci-dead-python` finding the writer reported (against a
      still-in-flight PEER file, `core/release_state_validator.py`, mid-write by the other
      live W7P5-b writer) is confirmed gone on driver re-run (rc=0, 751 reached, 0 findings)
      -- resolved by the peer finishing, not by this wave.
      **A real defect found and quantified**, unlike a prior wave's under-quantified one:
      `.ci/scripts/test/test-rdc-sh-env.sh:93-97`'s "node not found" branch is DEAD CODE (`set -euo pipefail`
      means a failing `command -v node` substitution kills the script via the ASSIGNMENT's
      own exit status before the guard checking for that failure ever runs), so this
      REGISTERED gate exits 1 with zero bytes on either stream on a node-less host --
      indistinguishable from a genuine secret-leak failure. Narrow blast radius (CI runners
      always have node) but flagged for driver awareness since fixing it changes the twin's
      output bytes and needs port+differential resynced in lockstep, same class as the
      `check-commands.sh` finding two waves back.
      **A correction to the prior wave's characterization, not taken on faith**: `ensure-
      nfpm.sh` has NO existing Python bridge (the prior wave's "a bridge already exists"
      claim was wrong) -- what exists is a bash proxy, one of the 7 already-known toolchain-
      blocked proxy-family files. Porting it means writing the acquisition path from
      scratch, not wiring an existing bridge. Also confirmed live: docker IS available
      (`docker version` -> server 29.7.2), so the `ci-start-elite.sh`/`ci-start-account.sh`
      real-docker differential is feasible as hypothesized.
      **SEVENTH WAVE 2026-09-10: 3 more standalone files ported, 18 total ports today.**
      `ci-start-elite.sh` -> `infra/ci_start_elite.py`, `ci-start-account.sh` ->
      `infra/ci_start_account.py`, `standing-orders-brief.sh` ->
      `review/standing_orders_brief.py`. Driver-verified directly: all 3 modules exist,
      59/59 new tests pass (14+21+24), all 3 ledgers at K=5, `check:ci-language-policy`
      clean; a `check:ci-dead-python` finding at re-check names `core/review_budget.py`
      (the still-in-flight `common.sh` writer's file, not this wave's) -- confirmed not
      this wave's concern.
      **A live, quantified, margin-of-seconds defect (DRIVER TRIAGE):
      `.ci/scripts/infra/ci-start-account.sh:106`'s health check is a SUBSTRING test**
      (`grep -q "healthy"` matches literal `unhealthy`), so a container docker has marked
      unhealthy is announced healthy and the REGISTERED `.github/workflows/ci.yml:740` step
      proceeds green. Measured, not estimated: the
      compose health check's own `start_period`/`interval`/`retries` puts the earliest real
      "unhealthy" at ~t=200s, the port's probe loop (180s of sleeps, probe wall-time never
      added to the budget) lands its last check at ~t=191s -- **about 9 seconds of margin**,
      which a contended runner or a slightly slower `docker inspect` closes with no file
      change at all. Reproduced and pinned, not fixed (invariant 5, changing the twin changes
      a live step's pass/fail).
      **Remainder: 7 standalone files** (corrected down from 10): 1 portable now
      (`ensure-nfpm.sh`, confirmed no bridge exists, acquisition path needs writing from
      scratch), 3 operator-invoked-only, 3 genuinely blocked -- plus the 7 proxy family and
      3 too-large files, unchanged.
      **EIGHTH WAVE 2026-09-10: ensure-nfpm (both halves) + scope-shadow.sh done in full.**
      `.ci/scripts/build/ensure-nfpm.sh` -> `build/ensure_nfpm.py` and its registered-gate
      proxy wrapper `.ci/scripts/test/proxies/proxy-ensure-nfpm.sh` -> `proxies/ensure_nfpm.py`
      (turned out to be TWO files, not one -- corrects the earlier "no bridge" note's
      undercount of scope), plus `.ci/scripts/ci/scope-shadow.sh` (588 lines, one of the
      3 "too large" files, done in full rather than partially: 299 of 588 lines are prose,
      and the 5 inline `node -e` programs are deliberately carried verbatim rather than
      translated, to avoid a second reader of the same job-surface contract). Driver-
      verified directly: all 6 modules exist, 43/43 new tests pass (14+12+17), all 3 ledgers
      present (5/5/7 rows, K=5 satisfied), `check:ci-dead-python`/`check:ci-language-policy`
      clean, `check:ci-proxy-ensure-nfpm` reruns green live (9 checks passed), no stray
      commits, git status scoped exactly, executable bits correct on the 2 path-invoked
      modules.
      **A correction to a prior wave's claim**: `check:ci-proxy-ensure-nfpm` is NOT
      toolchain-blocked as previously assumed -- run live, rc=0, real 4MB download and
      checksum performed.
      **Two real, narrow-blast-radius defects found in the twins, reproduced not fixed**: a
      warm binary cache is never checked against the pin (measured: exactly 2 of 5 live
      callers are affected, since CI runners never have a warm cache to begin with); a
      `set +e`/`set -e` pair in the proxy inverts intent (RE-ENABLES errexit rather than
      restoring a prior disabled state), reachable only if `nfpm --version`'s output format
      ever changes.
      **Corrected remainder: standalone 7->6, proxy-family 7->6** (a live preflight
      simulation found 5 of the 6 remaining proxy files have every declared toolchain
      requirement already satisfied on this sandbox -- go, dpkg-deb, rpmbuild, createrepo_c,
      gpg, node/npm/vitest, passwordless sudo, a built `private/renet/bin/renet`, and a built
      CLI bundle all present; only `proxy-license-e2e.sh` is genuinely blocked, on a missing
      `private/license-mint`. Deliberately NOT run -- a satisfied preflight means the real
      subject executes with real side effects on a shared machine, the driver's call to make),
      **too-large 3->2** (`check-workflow-gates.sh` 1108L, `sampler-linux.sh` 627L remain).
      **NINTH WAVE 2026-09-10: both remaining "too-large" files done in full, bucket now
      EMPTY.** `check-workflow-gates.sh` (1108L, registered gate `check:ci-workflow-gates`)
      -> `security/workflow_gates.py`, and `.ci/scripts/ci/sampler-linux.sh` (627L, invoked
      from `.github/workflows/profiler-probe.yml`, not itself a `check:` gate) ->
      `ci/profiler_sampler_linux.py`. Driver-verified directly: both modules exist, 179
      combined tests pass across this wave's 6 new test files
      (`test_security_workflow_gates.py`, `test_ci_profiler_sampler_linux.py`, plus the 4
      proxy-family test files below), ledgers at `w7p6-workflow-gates.observations.jsonl` (5
      rows) and `w7p6-profiler-sampler.observations.jsonl` (6 rows), K=5 satisfied on both.
      Neither twin's call site is repointed (same as every other port this box).
      **The operator authorized running the 5 real-side-effect proxies from the prior wave's
      preflight** ("run them now"), so the same wave completed the proxy-family alongside the
      standalone files: **proxy-family 6->1.** `proxy-go-unit.sh` -> `proxies/go_unit.py`
      (`check:ci-proxy-go-unit`), `proxy-linux-packages.sh` -> `proxies/linux_packages.py`
      (`check:ci-proxy-linux-packages`), `proxy-ops-host-check.sh` ->
      `proxies/ops_host_check.py` (`check:ci-proxy-ops-host-check`), `proxy-rdc-update.sh` ->
      `proxies/rdc_update.py` (`check:ci-proxy-rdc-update`), each run for real against live
      toolchains (go build, dpkg/rpm tooling, `renet ops host check`, a real `rdc update`
      drive) rather than merely preflight-checked. Ledgers: `w7p6-proxy-go-unit` (6 rows),
      `w7p6-proxy-linux-packages` (5), `w7p6-proxy-ops-host-check` (8),
      `w7p6-proxy-rdc-update` (5); K=5 satisfied on all four.
      **`proxy-unit-tests.sh` -> `proxies/unit_tests.py` was also ported this wave**
      (`check:test-provisioning`/`check:test-e2e-unit`), and a real, live bug in BOTH the
      twin and the port was found and fixed in lockstep by the driver afterward, not left in
      the port: vitest's ANSI colour escapes sit between "Tests" and the number in any
      CI-shaped environment (only this sandbox's own `CLAUDECODE=1` accidentally hid it), and
      the summary reader took the FAILED count on a mixed pass/fail line instead of the
      trailing total. Fixed by stripping ANSI first and reading the trailing `(N)` total;
      verified against the real registered gate (rc=0) and 21/21 differential tests; K=5
      ledger `w7p6-proxy-unit-tests.observations.jsonl` re-recorded (5 rows, including the
      coloured-green regression case). Worklist `#23dedacb`.
      **`proxy-license-e2e.sh` was corrected, then ported inline by the driver the same
      turn**: the prior wave's "genuinely blocked, missing `private/license-mint`" was WRONG
      -- run live, the real path resolves and the subject runs green in 42.2s, so it was
      ported to `proxies/license_e2e.py`. **Proxy-family remainder: 0** (bucket now empty --
      only `proxy-lib.sh`, exempted as sourced-only, is not a standalone port). Driver-
      verified: 4/4 differential tests pass, including one that drives the REAL subject with
      real side effects (24 enforcing scenarios, 0 failures; nolicense control fired 16
      times; wrong-key control fired 22 times -- identical on both sides). K=5 ledger
      `w7p6-proxy-license-e2e.observations.jsonl` recorded (5 rows, 5 distinct trees, 5
      distinct finding sets). A real byte-mismatch bug was found and fixed while porting: the
      twin's `need_file` check for `license-mint` builds its path as
      `"$PROXY_DIR/../../private/license-mint"`, an UNRESOLVED string carrying a literal
      `../..`, which the twin prints verbatim in its "does not exist" message; a first pass
      at the port used a clean `pathlib` join instead and printed a different (correct but
      non-identical) path, failing the differential. Fixed by reproducing the twin's
      unresolved path construction exactly, not by "improving" it -- the two sides must
      agree byte for byte, and only one of them owns changing what the twin prints.
      check:ci-python-lint/dead-python/language-policy all rc=0 for this file set.
      **Six real, narrow-blast-radius defects found across this wave's twins and ports,
      flagged for driver triage rather than silently fixed** (fixing changes a live
      registered gate's or a live workflow step's behavior, same class as prior waves):
      `check-workflow-gates.sh` CHECK 6 names checkout steps by NAME rather than `uses:`
      (139/144 named steps missed) and has no None/isinstance guard on empty YAML;
      `sampler-linux.sh`'s `--out`/`--interval` as the last CLI arg infinite-loops (0 live
      callers affected), `--interval 08` crashes via bash octal parsing, and a non-numeric
      `PROFILER_MAX_SECONDS` silently disables the self-termination guard; `proxy-linux-
      packages.sh`'s anti-vacuity check fails open on a renamed marker string (0 packages
      affected today); `.ci/scripts/test/test-rdc-update.sh:77-78` leaks orphan `python3 -m http.server`
      processes via `$!` capturing the wrong PID (254 orphans measured on the host, 100
      killed by an earlier writer, 154 pre-existing and left alone); `proxy-go-unit.sh`'s
      exclusion regex is broader than documented (0 packages affected);
      `.ci/scripts/test/proxies/proxy-ops-host-check.sh:86`'s single `jq` program silently
      aborts on type errors (0 live paths, 1 override-reachable path). All six triaged
      INLINE by the driver
      (`worklist.py --triage`); fixes tracked as separate worklist items, not folded into
      this box's own scope.
      **ALL SIX LANDED THE SAME TURN, two via dispatched writers (disjoint file sets, per
      standing rule 4) and one found+fixed by the driver mid-verification.** Writer A:
      `check-workflow-gates.sh` CHECK 6 now reads `uses:` not the display name (0 live
      findings today, since the one workflow it guards has an unnamed checkout), plus
      YAML parse/type guards on 3 of 5 crash paths, plus a pre-existing CHECK 2 twin/port
      divergence found and closed while testing; `sampler-linux.sh`'s three bugs (dangling
      `--out`/`--interval` no longer spins, octal `--interval 08` no longer crashes and its
      `PROFILER_DISK_EVERY_S` sibling was swept too, non-numeric `PROFILER_MAX_SECONDS`
      now refused at startup). Writer B: `proxy-linux-packages.sh`'s anti-vacuity check now
      corroborates its marker against the subject's SOURCE, not just runtime output, so a
      rename is a loud refusal instead of a silent false "21 of 21"; `proxy-ops-host-
      check.sh`'s per-entry `jq` program's exit status is now checked, so a type error is a
      named finding instead of silent nothing; `proxy-go-unit.sh`'s `testutil.` alternative
      confirmed zero blast radius (docs corrected, not code). **A seventh, real defect
      surfaced by the driver while spot-checking Writer B's go-unit fix, not in either
      writer's brief**: the exclusion regex's four alternatives all miss the plain
      `os.Getuid() != 0` idiom (no `e`) that `pkg/storage`, `pkg/repository` and
      `pkg/filesystem` actually use, so those three packages stayed in the "safe" 60-package
      local subset despite needing root -- invisible locally (tests just skip), but a hard
      `t.Fatalf` under `CI=true` (what this differential, and real CI, both set). Reproduced
      live: `check:ci-proxy-go-unit` went exit 1 -> exit 0 after adding a fifth alternative,
      `Getuid`, widening the excluded set 8 -> 11 packages, 68 -> 57 in the local subset.
      Every fix driver-verified directly against the real registered gate (not taken on the
      writer's word): `check:ci-workflow-gates`, `check:ci-proxy-go-unit`,
      `check:ci-proxy-linux-packages`, `check:ci-proxy-ops-host-check` all rc=0; 132 + 61 +
      17 tests independently re-run; all 5 ledgers re-recorded or extended (K=5 or more,
      equivalence holds on each). `check:ci-python-lint`/`dead-python`/`language-policy` all
      rc=0 across every file touched. Worklist: `#73dca184`, `#076960ce`, `#095596c8`,
      `#9d021d76`, `#c12f13cd`, `#85c3fc67` (the seventh, driver-found fix).
      **TENTH WAVE 2026-09-10: 8 more standalone files ported via 2 parallel writers,
      disjoint file sets.** Writer A: `discover-epics.sh` -> `review/discover_epics.py`
      (calls the existing `review_budget.epic_ids` rather than re-implementing the parse),
      `page-density.sh` -> `quality/page_density.py` (registered gate
      `check:ci-page-density`, `package.json:266`), `tag-submodules.sh` ->
      `release/tag_submodules.py`, `cleanup-github-deployments.sh` ->
      `housekeeping/cleanup_github_deployments.py`. Writer B: `create-complete.sh` ->
      `signal/create_complete.py`, `announce-gate-skips.sh` ->
      `quality/announce_gate_skips.py`, `assert-artifact-version.sh` ->
      `release/assert_artifact_version.py`, `run-external-gate.sh` ->
      `quality/run_external_gate.py`. Driver-verified directly, both batches: 44 + 67 = 111
      tests independently re-run, exit code 0; all 8 ledgers at K=5, `shadow-gate --assert
      --k 5` holds on every pair; `check:ci-page-density`'s real Playwright container run
      byte-identical between twin and port; `check:ci-python-lint`/`dead-python`/
      `language-policy` all rc=0 across the combined 801-file corpus (found and fixed
      formatting drift in 5 of writer A's files that contradicted its own report).
      **A real, live bug found and fixed in `discover-epics.sh`**: both call sites wrote to
      `"${GITHUB_OUTPUT:-/dev/stdout}"`; opening `/dev/stdout` as a PATH fails with ENXIO
      when fd 1 is a UNIX SOCKET, which is exactly what Node's `child_process.spawnSync`
      hands a child -- including this repo's own `shadow-gate.ts` harness. The script then
      printed its human line, lost the `epics=` output the workflow reads, and exited 1 for
      a run that had already done its work. `GITHUB_OUTPUT` is always set in real Actions,
      so the live matrix never hit it; every local and harness run did. Fixed with an
      `emit()` helper, byte-for-byte no-op on the live path; driver re-reproduced the ENXIO
      failure with a raw socketpair against the old code and confirmed the fix resolves it.
      **Two more real defects found, reproduced not fixed** (both are live-CD-behavior
      changes, out of this box's ownership): `assert-artifact-version.sh` never clears its
      `/tmp` download directory between invocations, so a second run in one job with no
      `manifest.json` reads the first run's stale file (0 live paths -- `cd-v2.yml` runs it
      once per fresh runner); `cleanup-github-deployments.sh` neither checks a failed
      DELETE's effect on its exit code nor URL-encodes `--environment` into the API query
      string (both latent, all current callers pass safe values). **Standalone remainder now
      further reduced** by these 8 (exact new count not yet re-derived; a fresh survey is
      owed before the next wave picks standalone work again).
      **A judge's "sweep the class" challenge on the license_e2e docstring, the CHECK6 fix,
      the sampler-linux fix and the linux-packages fix each drove a real class-sweep this
      wave**: one genuine sibling found and fixed each for the CHECK6 pattern (zero found,
      already the only instance) and the sampler-linux pattern (`profiler-control.sh`'s
      `--interval` had the identical dangling-flag hang, fixed with the same arity-check);
      zero siblings found for the linux-packages marker-rename pattern and the ops-host-
      check jq-abort pattern, both swept in depth and reported with reasoning, not asserted.
      **ELEVENTH WAVE 2026-09-10: 8 more standalone files, 2 more parallel writers,
      disjoint sets.** Writer C: `mark-production.sh` -> `release/mark_production.py`,
      `detect-bump-type.sh` -> `version/detect_bump_type.py` (real git fixtures, not
      stubbed), `cleanup-pr-environments.sh` -> `housekeeping/cleanup_pr_environments.py`,
      and `ci-stop.sh` -- correctly identified as ALREADY PORTED (`infra/ci_stop.py`,
      committed `1ae84c3e3` earlier this session) rather than duplicated; its missing K=5
      ledger was the one gap and is now closed (`w7p6-ci-stop.observations.jsonl`, 5 rows).
      Writer D: `verify-ssh.sh` -> `infra/verify_ssh.py`, `wait-for-vm-ssh.sh` ->
      `infra/wait_for_vm_ssh.py` (deliberately NOT sharing a helper with its sibling despite
      similar shape -- the twins disagree in six real ways, documented rather than
      refactored away), `compose-prompt.sh` and `resolve-model-args.sh` ->
      `autopilot/compose_prompt.py` / `autopilot/resolve_model_args.py` (new `autopilot`
      package). Driver-verified directly, both batches: 117 tests independently re-run,
      exit code 0; all 8 ledgers at K=5, `shadow-gate --assert --k 5` holds on every pair;
      `check:ci-python-lint` exit code 0 across the combined 816-file corpus.
      **Seven real defects found across the two twins, reproduced not fixed** (all are
      live-CI-behavior changes, out of this box's ownership, each pinned by a named
      `test_defect_*`/equivalent case so a future fix turns it red): `cleanup-pr-
      environments.sh` sources `common.sh`'s `set -e`, which overrides its own `set -uo
      pipefail`, so an empty `pr-N` listing kills the script silently before its own
      "none found" message -- driver-reproduced independently with a stub `gh` (exit 1, no
      output); the same script also lets a failed deletion count as `skipped` while still
      exiting 0, and interpolates `--repo` unescaped into a query string (constrained-safe
      today); `verify-ssh.sh` sleeps its full retry delay after the FINAL attempt with
      nothing left to retry; `wait-for-vm-ssh.sh` dies on an unset `$USER` before printing
      anything, and its trailing unguarded `ssh-keyscan` under `set -e` can kill the whole
      run silently after announcing success; `compose-prompt.sh` is missing a
      `require_file` on one of its four inputs, unlike the other three.
      **A blind spot in `check:ci-python-env-registry` named, not fixed**: a module that
      binds `self.env = os.environ` and reads through that indirection hides its
      environment inputs from the gate's AST walk entirely; `detect_bump_type.py`'s first
      draft did this and was rewritten to read `os.environ` directly before recording its
      ledger, closing the gap in that one file rather than leaving it undetectable.
      **A defect in a file outside this wave's ownership, named not touched**: `.ci/rediacc_ci/tests/test_infra_ci_stop_elite.py:118-122`'s own comment says "REPLACED, not
      prepended" directly above a line that prepends; caught the hard way when a writer's
      own first SSH-stub harness silently fell through to a real network `ssh` under the
      same pattern, fixed in that writer's own two infra tests (PATH replaced, not
      prepended, with an explicit `shutil.which(...) is None` assertion for the negative
      case) but the pre-existing sibling file was left alone.
      **TWELFTH WAVE 2026-09-10: 8 more `autopilot/` scripts, 2 more parallel writers,
      disjoint sets.** Writer E: `linked-sub-prs.sh` -> `autopilot/linked_sub_prs.py`,
      `sweep-collect.sh` -> `autopilot/sweep_collect.py`, `finish.sh` -> `autopilot/finish.py`,
      `restore-trusted-config.sh` -> `autopilot/restore_trusted_config.py`. Writer F:
      `update-state.sh` -> `autopilot/update_state.py`, `review-payload.sh` (pure, no
      network/git/env) -> `autopilot/review_payload.py`, `submodule-prs.sh` ->
      `autopilot/submodule_prs.py`, `sweep-campaigns.sh` -> `autopilot/sweep_campaigns.py`.
      `linked-sub-prs.sh`/`submodule-prs.sh` form a three-way contract with `check-
      submodule-branches.sh` (one writes the PR-body links, the other reads them back,
      the gate enforces them); each writer documented the relationship without touching
      the other's file. Driver-verified directly, both batches: 55 + 54 = 109 tests
      independently re-run, exit code 0; all 8 ledgers exceed K=5 (5 to 12 rows each),
      `shadow-gate --assert --k 5` holds on every pair; found and fixed formatting drift
      in 6 of writer F's files that the lint gate caught, re-verified 55/55 still pass;
      full `check:ci-python-lint` across the combined 832-file corpus: exit code 0.
      **Real defects found in the twins, reproduced not fixed, two independently confirmed
      by the driver**: `.ci/scripts/autopilot/submodule-prs.sh:83`'s `jq '... | length'` on a non-integer
      `submodules` count silently wipes the PR-body submodule-links block while exiting 0
      (driver-verified: `jq -r '(.submodules // []) | length'` on `3.5` returns `3.5`, not
      an integer; defence-in-depth only, the upstream validator already bounds this field);
      `restore-trusted-config.sh`'s `snapshot` is not idempotent -- `cp -a SRC DEST` copies
      SRC *inside* DEST when DEST already exists as a directory, so a second snapshot
      nests `.claude/.claude` and poisons the drift baseline (driver-reproduced directly:
      first `cp -a` populates `snapshot/.claude/` cleanly, a second identical `cp -a`
      creates `snapshot/.claude/.claude`). Five more named and pinned without independent
      re-verification: `sweep-collect.sh` scans zero PRs and exits 0 on an unindexable
      `prs.json` (unchecked process-substitution exit status), and separately swallows an
      unwritable `--out` via a trailing `|| true`; `linked-sub-prs.sh` silently truncates
      PR numbers past 7 digits, goes silent on a NUL byte in the PR body (GNU grep treats
      it as binary), and merges `#007`/`#7` via `sort -un` with an input-order-dependent
      surviving spelling; `finish.sh` passes an unvalidated `--pr` to `gh` as one argument
      on a value containing a space. A dangling symlink over a protected directory aborts
      `restore-trusted-config.sh`'s restore with the checkout partly quarantined, reproduced
      byte-identically on both sides (only the diagnostic differs).
      **THIRTEENTH WAVE 2026-09-13 (session resumed after a ~3-day gap, prior work verified
      intact): the LAST 6 files in `.ci/scripts/autopilot/`, 2 more parallel writers,
      disjoint sets -- this closes the entire directory (16 files ported across waves
      10-13).** Writer G: `autopilot-gate.sh` (978L port, the pre-model gate) ->
      `autopilot/autopilot_gate.py`, `fetch-review-threads.sh` -> `autopilot/
      fetch_review_threads.py`, `review-reply.sh` -> `autopilot/review_reply.py`. Writer H:
      `autopilot-push.sh` (461L, **the security boundary** -- the model never holds a write
      token, this script runs after it exits to perform the actual git push) ->
      `autopilot/autopilot_push.py`, `post-escalation.sh` -> `autopilot/post_escalation.py`,
      `state-comment.sh` -> `autopilot/state_comment.py`. Driver-verified directly, both
      batches: 110 + 94 = 204 tests independently re-run, exit code 0; all 6 ledgers K=5,
      `shadow-gate --assert --k 5` holds on every pair; full `check:ci-python-lint` across
      the combined 844-file corpus: exit code 0.
      **`autopilot_push.py` given extra scrutiny given its role**: independently re-ran its
      3 dedicated sandbox-escape controls (the fake `git`/`gh` win the PATH lookup; the shim
      refuses a command aimed at THIS repository, exit 97; the shim refuses a push whose
      remote is a real `github.com` URL, exit 97), and confirmed this repository's own
      `HEAD` and commit history were genuinely untouched afterward.
      **A driver-side bookkeeping error caught and fixed before further verification**:
      writer G recorded all 3 of its ledgers as `w7p8-*` instead of the box's own `w7p6-*`
      convention; renamed to `w7p6-autopilot-gate`/`w7p6-fetch-review-threads`/
      `w7p6-review-reply`.observations.jsonl` and the matching docstring citations fixed in
      all 3 ports and their 3 test files, then every ledger re-verified under the corrected
      name.
      **Real defects found across both twins, reproduced not fixed, several independently
      confirmed by the driver**: `review-reply.sh`'s jq `capture(...; "s")` uses jq's
      single-line ANCHOR mode, not dotall, so a multi-line model disposition matches nothing
      and is silently dropped from the reply/resolve plan entirely -- driver-reproduced
      directly (`jq -c '.decisions[] | capture(...; "s")'` on a two-line string: exit 0, zero
      output); the same script's bare-array `--threads` spelling is promised in a comment
      but errors in jq for real (driver-reproduced: exit 5, "Cannot index array with string
      threads"), latent since the sole live caller never uses that spelling.
      `autopilot-gate.sh` validates `--state`/`--failed-jobs`/`--watchdog` with `[[ -n && -s
      ]]` rather than `require_file`, so a mistyped path fails OPEN; its allowlist strips ALL
      whitespace so `a b` is admitted as `ab`; `AUTOPILOT_MAX_ROUNDS=08` is a bash arithmetic
      error that reads as false under no `set -e`, so the round cap fails open --
      driver-reproduced directly (`((10 >= 08))`: bash arithmetic error, exit 1).
      `fetch-review-threads.sh` calls its accumulator only from `||`/`if !`, disabling `set
      -e` inside it, so a failing fetch writes a blank `--out` and reports success anyway.
      `state-comment.sh`'s 400-character line cap is LOCALE-DEPENDENT (`${#line}` counts
      bytes under `C`, characters under UTF-8) -- driver-reproduced directly (399 `a`s plus
      one `é`: 400 characters, 401 UTF-8 bytes); its field normalizer strips whitespace
      globally rather than refusing it, so `--model 'opus 4.5'` is silently accepted as
      `opus4.5`; a directory passed as `--ruled-out-file` prints the twin's own "is a
      directory" read error and exits 0 appending nothing; and `inherit_errexit` does not
      reach into `$( )`, so an unreadable `--body` yields inconsistent fatal-error counts
      between `render` and `fields`. `post-escalation.sh`'s `${pair#*=}` returns the whole
      token when a `--steps` entry has no `=`, so a bare `failure` token is fed back into its
      own message ("The round failed in failure"); its `--verdict` path is likewise
      `-s`-checked not `require_file`-checked, silently dropping the model's stated reason on
      a typo.
      **FOURTEENTH WAVE 2026-09-13: 6 more scripts, 2 more parallel writers, disjoint
      sets, first outside `autopilot/`.** Writer I: `update-homebrew-tap.sh` ->
      `release/update_homebrew_tap.py`, `retry-failed-runs.sh` -> `housekeeping/
      retry_failed_runs.py`, `bump.sh` -> `version/bump.py`. Writer J: `ci-env.sh`
      (sourced-only, confirmed rather than assumed: exactly two real `source` sites, zero
      executions) -> `infra/ci_env.py` (ported as a function library, matching how
      `common.sh` became `core.common`), `docker-prepull.sh` -> `infra/docker_prepull.py`
      (confirmed genuinely distinct from the already-ported `proxies/docker_prepull.py`,
      which is the PROXY for a different subject, before writing anything), `review-
      status.sh` -> `review/review_status.py`. Driver-verified directly, both batches: 83
      + 89 = 172 tests independently re-run, exit code 0; all 6 ledgers K=5 (correctly
      using the box's own `w7p6-` ledger prefix this time, after writer G's mis-prefix the
      wave before), `shadow-gate --assert --k 5` holds on every pair; full `check:ci-
      python-lint` across the combined 856-file corpus: exit code 0.
      **Real defects found, two independently confirmed by the driver**: `bump.sh
      --auto`/`--patch` genuinely crash on this repo today -- driver-reproduced directly
      (`bash bump.sh --dry-run --auto`: exit 1, `dev: unbound variable`, because every
      `package.json` carries the `0.0.0-dev` placeholder since version truth moved to git
      tags, and the patch-increment arithmetic chokes on the non-numeric suffix); `--minor`/
      `--major` survive by luck (they never touch the patch field) and emit a plausible but
      never-semver-derived version. `ci-env.sh` silently ships EMPTY secrets on a failing
      `openssl` -- driver-reproduced directly (`export FOO="$(nonexistent-cmd | tr ... |
      cut ...)"` under `set -e` alone, no `pipefail`: reaches the next line with `FOO=`
      empty, exit 0), because the pipeline's own exit status is masked twice over (no
      `pipefail`, and a bare `export VAR=$(...)` reports `export`'s status, not the
      substitution's) -- this writes an empty API key and JWT secret into both `.env` and
      `$GITHUB_ENV` for every later workflow step. Reproduced not fixed, cutover box's
      call. Five more named and pinned without independent re-verification:
      `update-homebrew-tap.sh --push` dies mid-way on a bot-identity-less machine after
      the formula was already rewritten and staged, leaving the submodule dirty with no
      explanation; `retry-failed-runs.sh` reads TSV with `IFS=$'\t'` (tab is IFS
      whitespace), so a null field collapses the read and shifts every later column left;
      `bump.sh` leaves the manifest at mode 0600 (`mktemp` plus `mv`, never restored to
      0644); `retry-failed-runs.sh` fails CLOSED on branch tips but OPEN on the runs
      listing itself (`|| echo '[]'`), so an unreadable listing looks identical to a
      genuinely clean night; `review-status.sh`'s `PR_NUMBER` is emptiness-checked but
      never shape-checked, so junk reaches a `gh api` URL verbatim. `docker-prepull.sh`
      counts ARGUMENTS not pulls in its summary line (the same ref twice reads as two).
      **A driver decision on a class the writer correctly escalated rather than settling
      unilaterally**: `check:ci-em-dash-surfaces` flagged 8 em dashes across this wave's
      ports and 5 pre-existing sibling files reproducing their bash twins' own literal
      byte content (a `.env` header comment, a `DRY RUN` log line, a validator's own OK
      message) -- the gate's own message forbids seeding the baseline for new breakage and
      says to restructure the sentence instead. Since the string is a REQUIRED byte-exact
      match with the twin (not free prose), restructuring the port alone would break
      equivalence; the driver instead fixed the ROOT CAUSE, editing all 6 affected bash
      twins (`ci-env.sh`, `ci-start-account.sh`, `ci-start-elite.sh`,
      `backfill-write-sentinel.sh`, `release-state-validator.sh`,
      `test-write-once-guard.sh`) and their 8 corresponding Python occurrences in
      lockstep (including one pre-existing file, `write_once_guard_check.py`, that had
      deliberately encoded the OLD em dash as a `—` escape specifically to dodge this
      same source-text scanner while still byte-matching the twin -- exactly the kind of
      quiet exemption this wave's writer named and refused to repeat, and which the fix
      now makes unnecessary). Drained 6 now-fixed baseline entries (2971 -> 2965, 0
      added), re-ran all 445 affected differential tests (exit 0),
      `check:ci-em-dash-surfaces` and `check:ci-python-lint` both exit 0 afterward. **Known
      gap, not closed this wave**: the 5 pre-existing files' K=5 ledgers were not
      re-recorded against the new (text-only, differential-test-verified-equivalent)
      bytes; their `--assert --k 5` still passes against pre-fix tree ids, which is stale
      evidence rather than wrong evidence.
      **FIFTEENTH WAVE 2026-09-13: 3 more scripts, one parallel writer (the second slot's
      batch was a stale-report bookkeeping catch-up, not new work -- see below).**
      `ci-pull-images.sh` -> `infra/ci_pull_images.py`, `docker-pull-ghcr.sh` ->
      `infra/docker_pull_ghcr.py` (confirmed no shared GHCR-auth helper exists to reuse:
      `common.sh` has zero hits for `ghcr` or `docker login`, so the duplication between the
      two twins is real and is documented, measured by
      `test_neither_twin_shares_a_ghcr_helper_because_common_sh_has_none`), `cleanup-
      stale-d1.sh` -> `housekeeping/cleanup_stale_d1.py` (reused the existing package; both
      the dry-run and real-delete paths driven in the ledger). Driver-verified directly: 73
      tests independently re-run, exit 0; all 3 ledgers K=5, `shadow-gate --assert --k 5`
      holds on every pair (all correctly `w7p6-` prefixed); twins confirmed byte-untouched.
      **One discrepancy the driver caught that the writer's own report missed**: `check:ci-
      python-lint` showed 3 of the writer's own 6 files needing `ruff format`
      (`docker_pull_ghcr.py`, `test_housekeeping_cleanup_stale_d1.py`,
      `test_infra_ci_pull_images.py`) against the writer's claim of "0 findings in my 6
      files" -- pure formatting, no logic change; driver ran `ruff format --no-cache` on
      exactly those 3, re-ran all 73 tests (still exit 0), gate now exits 0 clean. **Real
      defects found in the twins, reproduced not fixed**: both `ci-pull-images.sh` and
      `docker-pull-ghcr.sh` leave the GHCR credential on the runner when a login/pull fails
      partway through -- the cleanup block (`docker logout`, the `jq` auth scrub) is
      straight-line code with no `trap`, so `set -e` walks past it entirely; driver-
      reproduced directly (a subshell whose interior command fails under `set -e`: the
      script exits before any of the cleanup lines execute). `cleanup-stale-d1.sh` treats
      "could not reach Cloudflare" and "nothing to do" as the same green exit (`|| true`
      discards both status and stderr from `wrangler d1 list`), so an expired token or a 5xx
      leaves every scheduled orphan un-reaped; its `--max-age` is never range-checked either.
      A latency/robustness note surfaced building the fixture: `common.sh`'s
      `parse_args`/`to_upper` forks `tr` per flag (53 call sites), so a host missing `tr`
      dies at exit 127 before any validation -- this is what made a correct port briefly
      look broken. **A second gate blind spot named and stopped, outside this wave's
      files**: `check:ci-python-env-registry` cannot see an env read behind a one-line
      alias (`env = os.environ; env.get(...)`) -- not hypothetical, `core/common.py`,
      `infra/ci_env.py` and `release/mark_production.py` already read env through exactly
      that alias while being absent from the registry; probed directly against
      `scan_module` (alias -> `[]`, direct -> the real key).
      **The second writer slot this wave did not produce new work**: its report was
      the stale-bookkeeping catch-up for four already-landed waves (13-14) whose read-flag
      had not been set before the compaction boundary; the driver re-verified one of those
      four pairs live (still clean) and marked all four read rather than re-recording
      content already in this document.
      **SIXTEENTH WAVE 2026-09-13: 3 more scripts, one writer -- the other writer this wave
      hit the session's weekly rate limit before producing any file and is redispatched
      separately.** `advance-contract-floor.sh` -> `release/advance_contract_floor.py`,
      `assert-edge-tag-exists.sh` -> `release/assert_edge_tag_exists.py`, `cleanup-cf-
      preview.sh` -> `housekeeping/cleanup_cf_preview.py`. **The writer itself also hit the
      rate limit mid-report** (last visible line: "Now the remaining gates"), after its
      ports, tests and ledgers were already on disk -- so this wave is driver-verified from
      the artifacts directly rather than from a written report. 71 tests independently run
      (exit 0), all 3 ledgers K=5 (`w7p6-` prefixed correctly), `shadow-gate --assert --k 5`
      holds on every pair, twins confirmed present and byte-untouched,
      `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-language-policy` all scoped-
      clean (lint exit 0 outright; dead-python's 5 findings are the same pre-existing
      backlog from other writers, none in these 3 files; language-policy exit 0). No
      real-defect narrative survives from the writer (its report never reached that
      section); none independently sought this wave given the artifacts already carry full
      test coverage and the box does not require a defect to exist.
      **SEVENTEENTH WAVE 2026-09-13, first of a re-saturation pair after the weekly rate
      limit killed both wave-16-successor writers mid-task (confirmed by the operator;
      recovery narrated above and in worklist evidence).** `cf-purge-urls.sh` ->
      `deploy/cf_purge_urls.py`, `delete-r2-channel.sh` -> `deploy/delete_r2_channel.py`,
      `purge-media-cache.sh` -> `deploy/purge_media_cache.py` -- the first three deploy-
      family scripts ported despite touching real Cloudflare/R2 endpoints, legitimated by
      `.ci/shadow/w7p5a-status.json`'s own blocker text naming a mocked/stubbed parity
      ledger as separate, not-yet-done work. Driver-verified directly: 54 tests
      independently re-run, exit 0; all 3 ledgers K=5, `w7p6-` prefixed correctly,
      `shadow-gate --assert --k 5` holds on every pair; twins confirmed byte-untouched;
      `check:ci-python-lint`/`check:ci-dead-python` scoped-clean (dead-python's 5 findings
      are the same pre-existing backlog, none here).
      **Real defects found in the twins, reproduced not fixed, one independently confirmed
      by the driver**: `cf-purge-urls.sh` breaks its own documented "always exits 0"
      promise -- `RESPONSE=$(curl ...)` and `SUCCESS=$(... | jq ...)` are plain assignments,
      so a curl transport failure or a non-JSON body ends the run under `set -e` with the
      substitution's own exit code, not 0; `--zone` as the very last CLI token dies as a
      bash `unbound variable` rather than the script's own usage message. **`delete-r2-
      channel.sh` reports a deletion that never happened -- driver-reproduced directly**
      (every `aws s3 rm` forced to exit 1 with a simulated `AccessDenied`: the script still
      prints "Channel ... deleted from R2" and exits 0), because `2>/dev/null || true` on
      all twelve calls plus an unconditional closing line makes an expired credential
      indistinguishable from a channel that never existed. `purge-media-cache.sh`'s
      transport failure is silent (`curl -s`, no `-S`, writes nothing on either stream) and
      its non-JSON-body path prints jq's parse error twice followed by an empty-tailed
      "Purge failed: " with no reason. All five pinned bidirectionally in the differentials.
      **Two ledger-technique notes carried forward**: a script whose only output on success
      is a bare `✓`/`→` needs `--finding-re` scoped to its actual content line, or every row
      reads `VACUOUS_BOTH_EMPTY`; `delete-r2-channel.sh`'s fake `aws` had to echo the prefix
      it was handed so the compared finding set is literally the set of targeted prefixes.
      **EIGHTEENTH WAVE 2026-09-13, second of the re-saturation pair.**
      `verify-edge-endpoints.sh` -> `deploy/verify_edge_endpoints.py`, `verify-stable-
      endpoints.sh` -> `deploy/verify_stable_endpoints.py`, `write-release-sentinel.sh` ->
      `deploy/write_release_sentinel.py`. **`curl`/`aws`/`jq` stayed REAL binaries on a
      scratch PATH rather than fakes-in-Python, by necessity**: every URL in the two verify-
      scripts is a hard-coded production hostname with no override knob, so only a
      same-named binary intercepting the call can drive either side off production; jq's
      three-way exit-code split and raw stderr are load-bearing for the twin, and the
      sentinel's uploaded payload literally is jq's output bytes. Driver-verified directly:
      84 tests independently re-run, exit 0; all 3 ledgers K=5 (recorded three times
      end-to-end as the port was edited, since a ledger row must describe the code that
      produced it), twins confirmed byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-language-policy` all scoped-clean.
      **One deliberate divergence, asserted rather than hidden**: `verify-edge-
      endpoints.sh`'s retry-sleep arithmetic is integer-only bash; a fractional
      `EDGE_RETRY_SLEEP` throws inside the give-up branch and the error aborts the shell
      function BEFORE its `return 1` runs, so every call site (all six, all `||`/`if !`)
      reads status 0 and reports OK on a probe that never actually passed -- driver-
      reproduced directly (`EDGE_RETRY_SLEEP=0.01 EDGE_RETRIES=2`: six arithmetic-syntax-
      error lines on stderr, "Smoke test passed", exit 0). Transcribing that silent-pass
      into Python would not be a port, so the port renders the sleep with `float` (byte-
      identical for every integer value including the production default of 5) and the
      divergence itself is pinned by name in both directions.
      **Real defects found across all three twins, reproduced not fixed**: both verify-
      scripts skip a missing/empty `regions.json` silently (`done < <(jq ...)` is a process
      substitution whose exit status neither the loop nor `set -e` observes: zero regions
      checked, "Smoke test passed", exit 0) and report a non-200 region as a concatenated
      `HTTP 404000` (`$(curl -w '%{http_code}' ... || echo "000")` puts curl's write AND the
      fallback echo in one substitution -- confirmed against real curl and a local 404
      server: `HTTP_CODE` is literally the six bytes `404000`). `verify-stable-
      endpoints.sh`'s probes are bare `set -e` assignments with no retry wrapper, so a
      transport failure exits with curl's own code (22 or 7) two lines before the script's
      own annotated error message is reached. `write-release-sentinel.sh`: a flag given with
      no value (`--version` as the last token) dies via `shift 2`'s non-zero return under
      `set -e` in total silence, one line above the documented exit-2-with-a-message path;
      and its own caller collapses `release-state-validator.sh`'s deliberately separated
      "R2 probe failed" and "sealed but genuinely empty" cases back into the same exit code
      1, defeating a distinction the validator's own comment says it went to real trouble to
      make.
      **A gate-visibility trap found and fixed on the way in, same class as `ci_env.py`'s
      wave-15 fix**: the edge port originally read four inputs through `env = os.environ;
      env.get(...)`, invisible to `check:ci-python-env-registry`'s AST scanner; rewritten to
      read `os.environ` directly at each call site.
      **NINETEENTH WAVE 2026-09-13, second of the pair.** `set-preview-worker-secrets.sh`
      -> `deploy/set_preview_worker_secrets.py`, `set-www-worker-secrets.sh` -> `deploy/
      set_www_worker_secrets.py`, `upload-repos-to-r2.sh` -> `deploy/upload_repos_to_r2.py`.
      Driver-verified directly: 61 tests independently re-run, exit 0; all 3 ledgers K=5
      (one, `upload-repos-to-r2`, had to be re-recorded twice -- once because the first
      `--finding-re` collapsed two different SKIP_RELEASE banners to one fingerprint, once
      because `ruff format` reflowed the port after the first recording and a ledger row
      must describe the code that produced it), twins byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver**: an
      entirely empty `dist/` tree makes `upload-repos-to-r2.sh` report a successful upload
      -- driver-reproduced directly (empty `dist/repos/`, a recording fake `aws`/`curl`: the
      script prints "Repos uploaded to R2 channel: edge", exits 0, and the aws call log is
      empty) -- because every upload loop is directory-driven and the `VACUOUS:` guard's
      subject is one directory, not the sweep as a whole. Three smaller ones pinned by name:
      `.ci/scripts/deploy/set-preview-worker-secrets.sh:53` labels its EMPTY-value guard message with
      `WORKER_NAME`, a variable that script does not have (copy-pasted from the `www`
      sibling); `:105` hard-codes "Set 15 secrets" as a literal rather than a count of what
      was actually sent, so a sixteenth key would silently under-report; `set-www-worker-
      secrets.sh` prints its own script name twice in one `${VAR:?msg}` diagnostic.
      **Two port-design notes worth keeping**: all three shell out to real `jq` (never
      `json.dumps`) because `wrangler`'s stdin bytes are the contract and jq/Python disagree
      on raw UTF-8 vs `\\uXXXX` escaping and on U+007F; `upload_repos_to_r2.py` also shells
      out to `find`/`sed`/`mktemp` for the same reason (order, unescaped substitution
      characters, and path shape all leak into observable behaviour). A genuine port-side
      bug the differential caught before landing: Python block-buffers stdout on a pipe, so
      the port's own success line originally landed after a downstream script's output with
      identical bytes and exit codes on both streams -- fixed with an explicit flush before
      any child inherits the descriptor.
      **A cross-cutting regression this wave surfaced and the driver fixed on the spot
      (small, local, no signature change rippling outward)**: `npm run check:ci-pytest`
      (`.ci/rediacc_ci/check_pytest.py`, run as a script by `package.json`, which puts
      `.ci/rediacc_ci/` itself at `sys.path[0]`) crashed in its own selftest --
      `AttributeError: module 'signal' has no attribute 'SIGKILL'` -- because the
      wave-9-created `.ci/rediacc_ci/signal/` package (holding `create_complete.py`, one of
      this box's own earlier ports) shadows the stdlib `signal` module for every later
      `import signal` in the whole tree, `proc.py`'s `_kill` included. Driver-verified the
      crash directly, confirmed the only other citation was one test file's `MODULE =
      "rediacc_ci.signal.create_complete"` string constant, renamed the package to
      `rediacc_ci.ci_signal` (git-untracked, so a plain rename, no history to preserve),
      fixed the one citation, documented the reason in the package's own docstring, and
      reran both the selftest (49/49 controls pass, was crashing) and the renamed
      differential (12/12, unchanged). Cross-checked afterward with the tree's full 13,414-
      test `pytest` corpus (two independent runs, `-n 8` and serial, one driver-run one
      writer-run): 39-43 failed depending on run (the range is corpus churn from concurrent
      writers adding files mid-run, not flakiness in anything this box touched), zero
      `SIGKILL`/`signal` crashes in either, and the failures fold to 18 pre-existing files
      unrelated to any wave 15-20 port (dead-python's same 5-file backlog, a stale
      twin-parity ledger from 2026-09-10, date-sensitive soak-period tests, hook-guard and
      workflow-contract tests with no citation of any `w7p6-*` ledger or box file).
      **TWENTIETH WAVE 2026-09-13, first of the next pair.** `deploy-account.sh` -> `deploy/
      deploy_account.py`, `deploy-edge.sh` -> `deploy/deploy_edge.py`, `deploy-proxy.sh` ->
      `deploy/deploy_proxy.py`. Driver-verified directly: 60 tests independently re-run,
      exit 0; all 3 ledgers K=5, twins byte-untouched, `check:ci-python-lint`/`check:ci-
      dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **A ledger-technique gap named for the next writer, not just this one**:
      `shadow-gate.ts` classes any line starting with `→ `/`✓ ` as CHATTER before it ever
      reaches `--finding-re`, so a script family that reports almost everything through
      `log_step`/`log_info` (all three here) cannot produce a finding via message-text
      matching no matter how the regex is scoped -- the fix was making the recording fakes
      echo their own argv and matching on that, which is also strictly better evidence (the
      compared set becomes the literal set of external calls) than matching banner text
      would have been.
      **Real defects found, the headline one independently confirmed by the driver**:
      `deploy-account.sh`'s database-name extraction is a `sed` substitution, not a match --
      a `database_name` line that does not fit the quoted pattern (a comment, for instance)
      passes through UNCHANGED rather than failing the emptiness guard, so `wrangler d1
      migrations apply` can be handed a full sentence -- driver-reproduced directly (a
      `# database_name is chosen per environment` comment line ahead of the real one: the
      extraction returns the comment verbatim). The same `sed` pattern is doubly greedy, so
      a trailing commented-out `# was "old-db"` on the real line steals the match (blast
      radius today is zero: every real `wrangler.*.toml` has exactly one canonical-shaped
      line). `deploy-proxy.sh` runs its entire CLI build before checking the worker
      directory exists, wasting a full `@rediacc/shared`+`@rediacc/cli` build on a
      guaranteed-fail path; `CLOUDFLARE_ACCOUNT_ID` is documented as required by both
      `deploy-proxy.sh` (never read at all) and `deploy-edge.sh` (`require_var`'d then never
      referenced), so a wrong or absent account id passes every check either script makes
      and the ambient wrangler config silently decides which account gets the deploy.
      **TWENTY-FIRST WAVE 2026-09-13, second of the pair.** `promote-docker-to-stable-
      hotfix.sh` -> `deploy/promote_docker_to_stable_hotfix.py`, `promote-r2-to-stable-
      hotfix.sh` -> `deploy/promote_r2_to_stable_hotfix.py`, `promote-r2-to-stable.sh` ->
      `deploy/promote_r2_to_stable.py`. **Shared-logic ruling**: the two R2 twins share four
      near-identical blocks but no promote-specific bash lib beyond `common.sh`'s
      `require_cmd`/`sed_in_place` -- documented in both docstrings (the docker-prepull
      precedent), not factored. Driver-verified directly: 58 tests independently re-run,
      exit 0; all 3 ledgers K=5 (both R2 ledgers re-recorded twice, once for a `ruff format`
      reflow and once for the alias fix below), twins byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found across both R2 twins, the headline one independently confirmed by
      the driver via direct code inspection**: `TMP="/tmp/promote-${dir}"` is a fixed,
      predictable path, not `mktemp`, and `rm -rf "$TMP"` is the LAST statement of the loop
      body -- so any early exit (an aws failure, the vacuity floor firing, a cancelled job)
      leaves it behind, and the next run copies into the same stale directory and promotes
      the leftovers as if they were fresh, with no warning; `/tmp/config` and `/tmp/script`
      are never cleaned at all. Latent on a fresh GitHub-hosted runner, live on a
      self-hosted one. `promote-r2-to-stable.sh` additionally drops files it then still
      purges: a shared phase-1 exclude list is followed by PER-DIRECTORY phase-2
      re-includes, and at least two real file shapes (`cli/edge/latest-linux.yml`,
      `rpm/edge/repodata/comps.xml`) match an exclude with no matching re-include anywhere
      -- they never leave `edge/` yet still appear in the Cloudflare purge body, and the
      vacuity floor cannot see it because it counts the local download, not what actually
      uploaded. `promote-r2-to-stable-hotfix.sh` posts 4 duplicate purge URLs (a `find` loop
      and a rewrite loop each append the same targets once), measured at 21 posted / 17
      distinct. Both R2 twins' `VACUOUS:` floor also sits AFTER the upload it is meant to
      guard, so it can only ever fire on the narrow window defect 1 shows is real (an empty,
      pre-existing `$TMP`), never on a directory that was never created.
      **The env-registry alias trap (same class as waves 15 and 18) hit again and fixed in
      THIS wave's two files, and flagged wider**: both R2 ports originally read via
      `require_env(dict(os.environ))`, matching 11 already-landed siblings, and the
      registry's AST scanner derived only ONE input from each instead of four and five;
      fixed here with an explicit `environment()` function reading one literal
      `os.environ.get("NAME", "")` per name, each file's own test re-running the gate's real
      scanner both directions. **Flagged, not fixed, as a class the driver owns**: the same
      `dict(os.environ)` blind spot is live in 8 other already-landed `deploy/` ports from
      earlier waves (`delete_r2_channel.py`, `set_www_worker_secrets.py`,
      `upload_repos_to_r2.py`, `cf_purge_urls.py`, `write_once_guard_check.py`,
      `set_preview_worker_secrets.py`, `purge_media_cache.py`, `deploy_account.py`) --
      harmless today only because `check:ci-python-env-registry` scans tracked files and
      none of these are tracked yet; owed as a pre-tracking cleanup pass, not urgent, noted
      here so it is not silently rediscovered at cutover.
      **TWENTY-SECOND WAVE 2026-09-13, a single large file given a solo slot.**
      `upload-to-r2.sh` (462 lines) -> `deploy/upload_to_r2.py` (877 lines). **`write_once_
      guard` stays bash, deliberately, matching the precedent `write_once_guard_check.py`
      already set for this exact function**: the port extracts and shells out to the twin's
      own `write_once_guard()` via the same `sed -n '/^write_once_guard()/,/^}/p'` range and
      `bash -c 'source ...; write_once_guard ... || rc=$?; exit $rc'`, never reimplementing
      its logic -- driver-verified directly (`rsv_sentinel_exists` appears zero times in the
      port's own code). Driver-verified further: 60 tests independently re-run, exit 0; the
      K=5 ledger holds (re-recorded three times as the port changed), twin byte-untouched,
      `check:ci-python-lint`/`check:ci-dead-python` scoped-clean. An independent 36-case
      scratch differential the writer built separately from the pytest suite reports 34
      AGREE / 2 DIVERGE, both divergences named and asserted from both sides (a `$0`-vs-`.py`
      usage line, and bash's own `line N: $2: unbound variable` prefix on a valueless flag).
      **Four real defects found, the most consequential independently confirmed by the
      driver via a minimal bash repro**: an empty `dist/cli/` publishes a channel pointer
      (`latest.json`) unconditionally, with zero binaries behind it, so every installer on
      that channel starts 404ing; a failed `rsv_binary_count` probe (AccessDenied, a 5xx)
      is misread as "sealed but genuinely empty" specifically because `write_once_guard ...
      || guard_rc=$?` suppresses errexit for the WHOLE function body, defeating the one call
      site `release-state-validator.sh`'s own header names as protected -- the exact
      library the validator exists to harden is the one place its hardening does not reach;
      a failed tracker read (`r2_get`'s `|| echo ""`) silently resets the retention window,
      orphaning every version the empty read dropped; and a malformed tracker is
      OVERWRITTEN WITH AN EMPTY FILE while the run reports success, because all three `jq`
      pipelines sit inside `CLI_PRUNED=$(update_versions_tracker ...)` and bash does not
      apply `errexit` inside a command substitution being assigned -- driver-reproduced
      directly (`bash -c 'set -e; f(){ false; echo body; }; V=$(f); echo rc=$?'` -> `rc=0`,
      versus calling `f` bare -> aborts). The last two share the identical root-cause shape
      as defect 2 (a caller's own syntax silently switching errexit off for a function it
      calls), a pattern now seen three separate times in this box across three different
      scripts.
      **TWENTY-THIRD WAVE 2026-09-13, second of the pair.** `deploy-www.sh` -> `deploy/
      deploy_www.py`, `test-d1-migrations.sh` -> `deploy/test_d1_migrations.py`,
      `simulate-promotion.sh` -> `deploy/simulate_promotion.py`. Driver-verified directly:
      76 tests independently re-run, exit 0; all 3 ledgers K=5, twins byte-untouched,
      `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all
      scoped-clean.
      **Real defects found, the headline one's root mechanism independently confirmed by
      the driver via a minimal repro**: `test-d1-migrations.sh` reads BOTH its region lists
      from `< <(jq ... regions.json)` process substitutions, whose exit status neither
      `set -e` nor `pipefail` can observe -- an unreadable `regions.json` prints jq's error
      to stderr and the script still reports "All 0 regional migration tests passed" and
      exits 0, a release-gating test that tested nothing -- driver-reproduced the root
      mechanism directly (`while read ... done < <(jq ... /nonexistent 2>&1)`: the loop
      completes and the pipeline's reported status is 0 regardless of jq's real exit code).
      Same failure family as waves 15's `ci_env.py`/22's `upload_to_r2.py` findings, a
      fourth occurrence of "a caller's own syntax silently switches errexit off," now also
      seen with a process substitution rather than only `$(...)`. `simulate-promotion.sh`'s
      missing-credential message names `CLOUDFLARE_R2_ACCESS_KEY_ID` while the guard above
      it actually tests `AWS_ACCESS_KEY_ID`, and its header lists `AWS_SECRET_ACCESS_KEY` as
      required while nothing in the file ever checks it; an unset `CLOUDFLARE_ZONE_ID`
      aborts (unguarded, unlike the `:-` on `.ci/scripts/deploy/promote-r2-to-stable.sh:180`) only AFTER the
      full promotion has already happened, so the run dies having moved everything and
      purged nothing. `deploy-www.sh`: a valueless `--name` flag deploys a preview worker
      literally named `true` (bash's own `parse_args` stores the string `"true"` for a
      missing value, and nothing validates the shape); its production-database guard can
      never fire because `DB_NAME` is built as `account-db-pr-${PR_NUM}` before the
      comparison, so every input carries `-pr-` including the empty string.
      **A concurrency hazard the writer found, fixed in its own two files, and flagged
      (not fixed) as the same exposure in a different wave's already-landed pair**:
      `simulate-promotion.sh`'s hard-coded `/tmp/config` collided with a second concurrent
      `pytest -n 8` process from another session, producing a live flake (`HeadObject 404`
      on a file that vanished mid-test); fixed here with a machine-wide `flock` per test.
      `test_deploy_promote_r2_to_stable.py` and `test_deploy_promote_r2_to_stable_hotfix.py`
      (wave 21) share the identical `/tmp/promote-<dir>` exposure with only an
      `xdist_group`, not a `flock` -- noted for whoever next touches that pair, not fixed
      here (outside this wave's file ownership).
      **TWENTY-FOURTH WAVE 2026-09-13, closing the `set-*-worker-secrets.sh` family.**
      `set-account-worker-secrets.sh` (29 secrets, the largest of the three) -> `deploy/
      set_account_worker_secrets.py`. Both siblings' known defects were explicitly checked
      for a third occurrence: the mislabeled-guard-variable defect does NOT recur (this
      twin genuinely has `WORKER_NAME`); the hard-coded-secret-count defect does NOT recur
      (this twin has no closing summary line at all); the doubled-script-name `${VAR:?}`
      defect DOES recur, in triplicate. Driver-verified directly: 33 tests independently
      re-run, exit 0; the ledger K=5, twin byte-untouched, `check:ci-python-lint`/`check:ci-
      dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one confirmed by the driver via direct source
      inspection**: the header's own claim that "the NAME passed to each call is also the
      variable name to look up in the secret store" is false for exactly the four REGION
      FAN-INS the same header lists -- the store holds `<NAME>_<SUFFIX>` but the guard calls
      (`_require_nonempty AWS_SES_ACCESS_KEY_ID ...` at :205, and three siblings) pass the
      bare name, so a real deploy failure points an operator at a secret-store key that does
      not exist -- driver-confirmed directly from source (line 26's documented mapping
      versus line 205's bare-name guard call). `AWS_SES_FROM`/`AWS_SES_CONFIGURATION_SET`
      satisfy the guard block's own stated demand-criterion (traced into
      `private/account/src/types/env.ts` and `email.service.ts`, which throws on every
      mail-sending request when `AWS_SES_FROM` is empty) yet neither is guarded. A `SUFFIX`
      that is not a bash identifier surfaces as a raw "invalid variable name" naming a
      variable that does not exist anywhere in the file.
      **One divergence changed the port's design after a measurement overturned an
      assumption**: `SUFFIX=EU[0]` is a bash ARRAY SUBSCRIPT reference, and a scalar answers
      to subscript 0 -- measured on real bash 5.3.9, not reasoned about -- so the twin
      actually DEPLOYS SUCCESSFULLY on that malformed input (reading `..._EU[0]` as
      `..._EU`) where the port correctly refuses; modelling bash's subscript grammar for
      this one unreachable shape was rejected as a second parser, so the divergence is named
      in the docstring and pinned, safe-direction-only (port refuses where twin would ship).
      **TWENTY-FIFTH WAVE 2026-09-13, closing `.ci/scripts/deploy/**` entirely (bar
      `clone-d1.sh`, owned by a different concurrent session).** `sync-media-from-r2.sh` ->
      `deploy/sync_media_from_r2.py`, `sync-media-to-r2.sh` -> `deploy/sync_media_to_r2.py`.
      **Every test runs in a copied tree under pytest's own `tmp_path`, never the checkout**,
      which sidesteps the fixed-`/tmp`-path concurrency hazard flagged the wave before
      (nothing here uses a predictable path, so no `flock` is needed). Driver-verified
      directly (against the repo's own R2-credential pre-bash hook, satisfied per its own
      instructions by setting the variable to empty rather than sourcing the real secret
      file): 42 tests independently re-run, exit 0; both ledgers K=5, twins byte-untouched,
      `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all
      scoped-clean.
      **Real defects found, the release-path-relevant one independently confirmed by the
      driver**: `sync-media-to-r2.sh` uploads NOTHING when every source directory is absent
      and still prints "Sync complete" at exit 0 -- driver-reproduced directly (all three
      directories missing, fake `aws` recording zero calls, script exits 0 anyway) --
      because `sync_dir` answers a missing directory with a bare `return 0` and nothing
      downstream counts the skips; `sync-media-from-r2.sh --audio-only` is a LIVE step in
      `.github/workflows/ci-quality.yml:1622`, so the sibling class of bug sits on a real
      pipeline path today. `common.sh`'s `require_var` (`:131-137`) validates only its FIRST
      argument despite being called with three names in both twins, so two of three
      required variables in every such call site are unchecked; an EMPTY (not merely unset)
      secret or endpoint is never caught by either twin, since `set -u` only catches unset,
      matching the exact shape this repo's own pre-bash hook was written to warn about;
      `sync-media-from-r2.sh --dry-run` still calls `mkdir -p` unconditionally, so a flag
      documented as "download nothing" creates real directories in the working tree.
      **A hook false-positive the writer hit and worked around rather than routing
      silently**: `.claude/rediacc_hooks/guards/block_host_toolchain_run.py`'s
      `_is_invoked` read a `for f in sync-media-from-r2.sh sync-media-to-r2.sh common.sh`
      word-list as an invocation of the R2 script, triggering the credential-sourcing
      block on a command that never runs it -- worked around per the hook's own suggested
      escape (`CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID=` on the command line), same trigger the
      driver's own subsequent spot-check hit verbatim on a bare `git status -- <path>`.
      Flagged for a future session's attention; the guard's own docstring says false
      positives are exactly what it exists to avoid.
      **TWENTY-SIXTH WAVE 2026-09-13/14, moving into `.ci/scripts/release/**` beyond the
      family already ported.** `cleanup-channel-docker-tags.sh` -> `release/
      cleanup_channel_docker_tags.py`, `create-github-release.sh` -> `release/
      create_github_release.py`, `reprobe-r2-sentinel.sh` -> `release/
      reprobe_r2_sentinel.py`. Driver-verified directly: 58 tests independently re-run,
      exit 0; all 3 ledgers K=5, twins byte-untouched, `check:ci-python-lint`/`check:ci-
      dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **A harness-quality note carried forward**: the writer's own control for asset-sort
      order initially passed for the wrong reason (`dist/cli` and `dist/packages` are
      disjoint prefixes with `c` < `p`, so per-pattern sort and union-sort necessarily agree
      on that input) -- caught before landing, a second control added that reverses
      `ASSET_PATTERNS` (the one arrangement where the two strategies diverge), which then
      fires correctly. Recorded as a reusable lesson: a green control on disjoint-prefix
      input proves nothing about sort semantics.
      **Real defects found, the headline one independently confirmed by the driver via
      direct source inspection**: `cleanup-channel-docker-tags.sh` cleans up NOTHING on any
      real release and the twin's own header already calls this a KNOWN GAP that is still
      live -- driver-confirmed directly (`CHANNEL` is always `edge` or `stable` per the
      twin's own comment, and the guard at line 63 only proceeds when `CHANNEL` matches
      `^staging-`, so the branch that would clean up never fires for a real channel; ported
      byte-for-byte rather than "fixed," since fixing it is a deliberate scope change, not a
      bug in the port). `reprobe-r2-sentinel.sh` reports an UNANSWERABLE probe as a positive
      absence: `rsv_sentinel_exists`'s three-way return (exists/absent/COULD-NOT-TELL) is
      collapsed by a plain `if/else` into two, so a credential failure during the probe
      prints an `::error::` asserting the sentinel is missing when the probe never actually
      established that -- the EXIT CODE errs safe, the MESSAGE does not. A stderr divergence
      traced to the shared library rather than this pair: `core.release_state_validator`'s
      `_log_error` drops the `✗ ` marker `common.sh:log_error` emits, invisible to that
      library's own test (which sources it alone, where the real `log_error` doesn't even
      exist) and only surfaced here because this caller sources `common.sh` first --
      flagged, not fixed, since `.ci/rediacc_ci/core/` is outside this wave's file
      ownership.
      **An environmental gate finding, not a code defect**: `check_pytest.py`'s default
      `PYTEST_RUN_TIMEOUT_S` (1080s) is now marginal on this tree's growing corpus -- one
      run refused with no verdict at all ("did not finish within 1080s"); a verdict was only
      obtained by overriding to `PYTEST_RUN_TIMEOUT_S=2700`. Noted for whoever next tunes
      that gate's defaults, not acted on here.
      **TWENTY-SEVENTH WAVE 2026-09-13/14, opening `.ci/scripts/security/**`.**
      `check-ci-workflow-invariants.sh` -> `security/ci_workflow_invariants.py`,
      `check-autopilot-workflow-invariants.sh` -> `security/
      autopilot_workflow_invariants.py` (both following the existing `workflow_gates.py`
      naming precedent, dropping the `check-` prefix), `dependency-inventory.sh` ->
      `security/dependency_inventory.py`. **A deliberate stub/real-run split, documented in
      the port's own docstring**: the two workflow-invariants scripts shell out to nothing
      but `python3` (one heredoc) and `awk`/`grep`, so their differentials drive fixture
      YAML through both twins' own `$WORKFLOW_FILE` seam with no fakes at all; `dependency-
      inventory.sh`'s happy paths run FOR REAL against this repo (1,760 records, 209 Go
      modules measured) because no fixture reproduces that faithfully, while its failure
      paths use recording-fake `npm`/`go` -- every real-run case hashes the lockfiles/`go.
      sum` before and after and refuses any drift. Driver-verified directly: 110 tests
      independently re-run, exit 0; all 3 ledgers K=5, twins byte-untouched, `check:ci-
      python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the SBOM-correctness one independently confirmed by the driver
      via its root mechanism**: `dependency-inventory.sh` silently DROPS a package from its
      NIS2/CRA supply-chain artifact when `npm ls` prints nothing for it -- driver-
      reproduced the exact mechanism directly (`jq empty <<<""`: exit 0, since jq treats
      genuinely empty input as valid, not an error), so the twin takes its "valid JSON"
      branch, every downstream `jq` call has nothing to slurp, and the SBOM understates
      itself in writing with no warning at exit 0. Same script: `require_cmd jq npm go awk`
      only ever probes `jq` (the fourth recurrence this session of `common.sh`'s
      single-argument `require_cmd`/`require_var` validation bug); `--help` leaks eight
      lines of raw shell source because its `sed -n '2,35p'` range outlives the actual
      header (ends at line 27); an empty `npm ls --omit=dev` result kills the run with a
      bare jq usage banner naming neither the tool nor the package; a missing `package.json`
      surfaces as a raw `jq: error: Could not open file`; missing option values are raw bash
      `$2: unbound variable` diagnostics. `check-autopilot-workflow-invariants.sh`'s END
      block iterates an associative array with `for (j in array)`, which gawk answers in
      HASH order, not insertion or sorted order (measured directly, not assumed) --
      unobservable today only because the real workflow has zero offending jobs.
      **A genuine bug in the port itself, caught before landing rather than shipped**: GNU
      `sed` preserves a missing final newline rather than adding one, and the first draft's
      `_echo_probe` terminated the last line regardless; fixed and pinned by a test that
      proves the fix by reverting it and watching red.
      **TWENTY-EIGHTH WAVE 2026-09-13/14, opening `.ci/scripts/docker/**` (a brand-new
      package, none of its 3 files ported before).** `cleanup-staging.sh` -> `docker/
      cleanup_staging.py`, `create-manifest.sh` -> `docker/create_manifest.py`, `retag-
      image.sh` -> `docker/retag_image.py`. A closed-PATH fixture discipline (an explicit
      symlink list, never a `$PATH` append) was adopted after the writer's first probe using
      an inherited `PATH` reached the REAL `ghcr.io` over the network before the twin's
      first log line -- a process finding, not a code one, but worth carrying into future
      waves. Driver-verified directly: 99 tests independently re-run, exit 0 (plus the
      writer's own 268-combination argv/env matrix, 0 diverging), all 3 ledgers K=5, twins
      byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver**:
      `cleanup-staging.sh` reports full success when `gh` is entirely ABSENT from PATH --
      driver-reproduced directly (a PATH built with only `dirname`/`uname`/`tr`/`jq`/`bash`,
      no `gh`: the script prints "Cleanup summary: 2 succeeded", exit 0) -- because `gh api
      ... 2>&1` captures the shell's own "command not found" into the response body, jq
      rejects the non-JSON, and the failure is filed under "package may not exist yet", the
      exact same UNKNOWN-folded-into-fine shape seen in `reprobe-r2-sentinel.sh` (wave 26)
      and `write-once-guard`/`upload-to-r2.sh` (waves 15/22) -- now a fifth occurrence of a
      caller collapsing "could not tell" into a definite answer. Two package versions
      sharing one staging tag build a single malformed, embedded-newline URL (`jq -r`'s
      multi-line output flows unquoted into a path segment) whose real-`gh` failure would
      then be swallowed by a `2>/dev/null` with zero diagnostic text. `create-manifest.sh`
      prints a doubled leading space in both its dry-run command echo and its sources log
      line (an accumulator seeded from `""`); its post-push verification is advisory-only
      and never covers `:latest` specifically, so a `:latest` that never became readable
      passes silently. `retag-image.sh` prints a green `✓` on a fully-failed summary ("0
      succeeded, 2 failed", exit 1) where the sibling `cleanup-staging.sh` correctly uses
      `log_error` for the identical shape; a tag containing `"` is swallowed the same way an
      unescaped value broke a jq program in an earlier wave; and `${REG#ghcr.io/}` only
      strips that one literal prefix, so a non-GHCR registry produces a garbled API path
      treating the whole host as an org name.
      **A documentation correction the writer caught mid-port**: the new package's
      docstring originally claimed none of these three are live workflow `run:` targets;
      grepping proved otherwise -- `create-manifest.sh` is called from `ci-build-docker.yml`
      (three call sites) and `retag-image.sh` from `cd-v2.yml`/`cd-stage.yml` (five call
      sites total), corrected before landing and the exact call sites recorded for the
      eventual cutover box.
      **TWENTY-NINTH WAVE 2026-09-14, closing `.ci/scripts/security/**`'s lint-tool trio.**
      `actionlint.sh` -> `security/actionlint.py`, `shfmt.sh` -> `security/shfmt.py`,
      `shellcheck.sh` -> `security/shellcheck.py`. **All three run the REAL pinned tool
      against this repo's real files for their happy path** (29 real workflows, ~570
      scripts, 620 tracked-and-untracked scripts respectively, every corpus hashed
      before/after with zero drift) and only stub for failure paths; shellcheck's own
      differential compares its main path byte-for-byte with NO normalisation at all.
      **A named, accepted divergence from real host tooling**: this host's `find` is bfs
      (breadth-first), not GNU findutils, so traversal order differs from a typical CI
      runner -- `shfmt.py` enumerates in byte order and the differential attributes the
      residual stdout-order difference to the ambient `find` by independently deriving its
      order, rather than papering over it. Driver-verified directly: 73 tests independently
      re-run, exit 0 (real shellcheck run costs ~200s of that); all 3 ledgers K=5 (one
      re-recorded after its first attempt used an info-severity plant against a twin that
      runs `-S warning`, silently vacuous); twins byte-untouched; `check:ci-python-lint`/
      `check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver via a
      minimal repro of its exact mechanism**: `actionlint.sh`'s anti-vacuity refusal (exit
      3, "nothing to check") is UNREACHABLE, and an empty corpus instead exits 1 in total
      silence -- driver-reproduced the mechanism directly (`collect_targets`'s only
      executable statement is a `for` loop over an unmatched glob, whose exit status is the
      last failed `[[ -f ]]` test; `targets="$(collect_targets)"` under `set -e` aborts the
      script right there, before the count or the refusal message is ever reached) -- and
      exit 1 doubles as this gate's own "actionlint found real problems" code, so CI shows a
      red step with an empty log for two unrelated reasons. A `--version` probe that exits
      non-zero kills the gate with THAT exit code silently, and if it happens to be exit 3,
      a broken shim reads as "nothing to check" -- the inverse confusion of the same two
      codes. `shellcheck.sh`'s 2026-09-02 deleted-file-skip fix is itself broken when the
      deleted file sorts LAST in the tracked list (the loop's exit status is `&&`'s on its
      final iteration, so removing the last-sorted file makes the whole filtering pipeline
      report failure under `pipefail`, aborting before any linting happens);
      `echo -e "$BASH4_ISSUES"` re-expands backslash escapes inside matched SOURCE lines
      from the corpus itself, so a `\c` anywhere in a scanned line truncates the ENTIRE
      report silently, with every finding after it simply gone. `shfmt.sh` runs its four
      scopes sequentially with no scope-level error isolation, so the first scope carrying
      diffs aborts the whole run under `set -e` and the remaining scopes report nothing,
      giving a false impression that clearing one scope's findings clears the gate.
      **A shared-library disagreement found and left for its actual owner**: `common.sh`'s
      `CI_TEMP` (set unconditionally by `get_temp_dir`) silently overrides any caller-set
      `CI_TEMP` in `actionlint.sh`'s cache path, which also makes it disagree with
      `toolchain.sh:toolchain_cache_dir`'s own documented precedence order for the same
      variable -- outside this wave's three files, flagged rather than fixed.
      **THIRTIETH WAVE 2026-09-14, `audit.sh` (a registered `---- gate ----` gate, `check:
      ci-security-audit`), a single large file given a solo slot.** `audit.sh` (541 lines)
      -> `security/audit.py` (1,481 lines). **A hermeticity finding in the writer's own
      first draft, caught before landing**: appending the caller's inherited `PATH` let the
      missing-`npm` test case resolve `~/.local/bin/npm` and run a REAL `npm audit
      signatures`; fixed to a fully closed `PATH` (fakes only) with a control asserting
      `npm`/`node`/`gh` cannot resolve outside the fakes. Driver-verified directly: 67 tests
      independently re-run, exit 0; the ledger K=5 (re-recorded once after a scratch-repo
      state leak duplicated two scenarios' fingerprints), twin and its four sourced
      libraries all byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-
      em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one's root mechanism independently confirmed by
      the driver**: any failed `gh api` call kills the gate with a bare exit 5 and ZERO
      bytes on either stream -- driver-reproduced the exact mechanism directly (`xargs -I
      {} bash -c '...' _ {}`: xargs substitutes `{}` everywhere in its argument list,
      INCLUDING inside the quoted script text handed to `bash -c`, so the intended
      fallback's literal placeholder becomes the raw slug string written straight to the
      cache file instead of JSON; `load_advisory_details`'s subsequent `jq -r` on that
      non-JSON file exits 5 under `set -e` with the message swallowed) -- and this is
      exactly the failure shape the gate's own header BLOCKER text worries about (`GH_TOKEN`
      absent -> 60/hr anonymous rate limit), so a rate-limited or transiently-failing GitHub
      call turns a real security gate into a silent, contentless exit 5. An empty `npm audit
      --json` is a GREEN run (`jq empty` on zero bytes exits 0, so `prod_total` becomes
      empty string and every numeric comparison against it is false) -- the fourth
      "unanswerable folded into fine" defect class this session, now including the case
      where NOTHING was even attempted. A non-numeric allowlist entry (plausible: GHSA ids
      are not numeric) kills the gate with a silent exit 5 at the very end of a run that
      already did both network round trips. `IFS=$'\t' read` collapses an empty field by
      shifting every later column left, so a GHSA entry with an empty version range prints
      its DESCRIPTION in the "Patched in" slot and its patched version in the "Affected"
      slot. A success log line sits outside its own guarding `if`, so "No production
      vulnerabilities" prints immediately after a warning that there are some. A
      wrong-shaped-but-valid JSON report fails inside a PROCESS SUBSTITUTION, whose exit
      status bash cannot see, yielding a green verdict on real jq stderr output.
      **Two deliberate divergences pinned rather than hidden**: the port's runner-probe
      result is memoised while the twin re-probes per delegate call (`old_probes ==
      new_probes + 1`, asserted so the size of the divergence cannot silently grow); `jq`
      and `grep` are reimplemented in Python but pinned against the REAL host binaries by
      dedicated cases, because this host's `grep` is ugrep, not GNU grep, and this
      repository has been bitten by that difference before.
      **THIRTY-FIRST WAVE 2026-09-14, opening `.ci/scripts/ci/**` with the `assert-*.sh`
      family.** `assert-channel-for-event.sh` -> `ci/assert_channel_for_event.py`,
      `assert-ci-complete.sh` -> `ci/assert_ci_complete.py`, `assert-install-methods-
      complete.sh` -> `ci/assert_install_methods_complete.py`, `assert-job-succeeded.sh` ->
      `ci/assert_job_succeeded.py`. **No fakes were needed anywhere**: all four twins read
      only argv, `RESULT_*`/other env vars, and (for install-methods) one output file --
      they shell out to nothing, so both sides are driven directly. Driver-verified
      directly: 62 tests independently re-run, exit 0; all 4 ledgers K=5, twins byte-
      untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces`
      all scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver on BOTH
      halves of its claim**: `assert-ci-complete.sh`'s `POINTER_BUMP_ONLY=true` fast path
      REPLACES the hard-required set rather than subtracting from it, so `RUN_SH_TESTS`
      lands in neither the hard nor the soft tier and a genuine failure there reads as green
      -- driver-reproduced directly (`POINTER_BUMP_ONLY=true RESULT_RUN_SH_TESTS=failure`
      plus every soft job `skipped`: "All CI jobs passed successfully!", exit 0) -- AND
      confirmed this is LIVE, not latent, by reading `.github/workflows/ci.yml:532-538`
      directly: `run-sh-tests` is gated only on `is_bot != 'true'`, with no pointer-bump
      exclusion, so it genuinely runs on a pointer-bump PR and a real failure there is
      forgiven, directly contradicting the twin's own comment that this job "has no
      legitimate reason to skip or flake on any event." `assert-channel-for-event.sh`'s
      `case` `*)` arm fails OPEN -- an unrecognized event name (or even a capitalization
      typo like `Push` vs `push`) accepts ANY channel with exit 0 -- a known-and-carried gap
      per the twin's own comment and a project doc that already names it for hardening, but
      still the same "unanswerable question reads as green" class flagged five times
      already this session.
      **A harness-only finding, not a code defect**: under `shadow-gate`'s `spawnSync`
      (Node's socketpair-based stdio), `GITHUB_STEP_SUMMARY=/dev/stderr` fails to open with
      `ENXIO` on BOTH sides, but bash reports it as a shell diagnostic (chatter) while the
      port reports it as a `✗` finding -- same underlying behavior, different surface text,
      which a naive comparator would misread as a mismatch; documented and pinned rather
      than smoothed away, and `/dev/stderr` is never a real production value for that
      variable regardless.
      **A cross-cutting backlog item surfaced and named, not fixed**: several already-
      landed untracked ports across earlier waves (`.ci/rediacc_ci/autopilot/*.py` named
      explicitly) carry file mode 644 with a `#!/usr/bin/env python3` shebang, which trips
      `check-python-lint`'s `EXE001` the moment they are tracked (the gate reads `git
      ls-files`, invisible to it today); this wave's own four ports were set to 755 on disk
      specifically to land clean at tracking time. Noted alongside the wave-21/26 env-
      registry-alias and `/tmp`-concurrency backlog items as a pre-tracking cleanup pass,
      not urgent, not yet acted on.
      **THIRTY-SECOND WAVE 2026-09-14, second W7P6 pair (both slots freed after wave 30/31
      landed).** `cancel-older-runs.sh` -> `ci/cancel_older_runs.py`, `check-rerun-
      attempt.sh` -> `ci/check_rerun_attempt.py`, `derive-image-tag.sh` -> `ci/
      derive_image_tag.py`. Driver-verified directly: 88 tests independently re-run, exit
      0; all 3 ledgers K=5, twins byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the release-relevant one independently confirmed by the
      driver**: `cancel-older-runs.sh` merges `gh api`'s STDERR into its captured body
      (`2>&1`), so a single deprecation-notice WARNING from `gh` (not even a failure) kills
      the step with a raw jq parse error and exit 5 -- driver-reproduced the exact
      mechanism directly (prepending one warning line ahead of valid JSON: `jq: parse
      error: Invalid numeric literal at line 1, column 3`, exit 5) -- the only script in
      this batch that otherwise cannot fail, taken down by a message it was never supposed
      to see as data. The same script also has no `require_cmd`, so a runner missing the
      GitHub CLI reads as a silent pass; leaks the raw GitHub API response body onto its
      OWN stdout on every successful cancel (stderr-only redirect on a call whose real
      payload is on stdout); can only ever fail for two reasons (missing
      `GITHUB_REPOSITORY`/`GH_TOKEN`) with every other failure mode -- a bad lookup, every
      cancel call refusing, the poll timing out with runs still active -- exiting 0; and a
      malformed `--timeout` value is a bash arithmetic syntax error that reads as FALSE, so
      the poll loop's only exit condition becomes permanently unreachable and the step
      spins forever. `check-rerun-attempt.sh` exits 1 on ITS OWN documented happy path
      whenever the optional `GITHUB_ENV` is unset (the write-out line is the script's last
      statement and its own `&&` status becomes the script's), and fails OPEN rather than
      refusing on an unreadable/empty attempt count (bash arithmetic silently treats a
      blank string as satisfying "not yet at the cap"). `derive-image-tag.sh`'s help text
      and header both describe a "read the version from package.json" branch that no longer
      exists in the code (every `package.json` here is a fixed `0.0.0-dev` placeholder by
      design); `--version ''` is silently auto-derived rather than refused, because the
      guard is presence-only (`${2?...}`) not emptiness-checked -- latent today only because
      the one live caller (`.ci/scripts/ci/set-image-tags.sh:24`) already guards non-empty before
      forwarding.
      **A race the writer found via the shadow-gate comparator itself, then reproduced
      independently**: `cancel-older-runs.sh`'s elapsed-time check reads the wall clock
      twice at whole-second granularity (`START_TIME` and the loop's own `$(date +%s)`), so
      a second boundary falling between the two reads can make the very FIRST loop
      iteration already read as expired -- harmless at the live 60s default, surfaced only
      because a `--timeout 1` fixture case produced a `MISMATCH_FINDINGS` row before being
      understood and pinned.
      **THIRTY-THIRD WAVE 2026-09-14, second slot of the same pair.** `dispatch-release.sh`
      -> `ci/dispatch_release.py`, `dispatch-watchdog.sh` -> `ci/dispatch_watchdog.py`,
      `generate-tag.sh` -> `ci/generate_tag.py`. Driver-verified directly: 137 tests
      independently re-run, exit 0; all 3 ledgers K=5 (re-recorded once after a post-first-
      recording env-registry fix), twins byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean; `check:ci-w7p5a-real-run-blockers`
      re-run afterward and still exit 0 (32 blocked / 16 ledgered, unchanged).
      **Real defects found, the headline one's exact mechanism independently confirmed by
      the driver, and now a SECOND occurrence of a pattern first seen in wave 13**:
      `dispatch-watchdog.sh`'s generation cap is evaluated with bare `((GENERATION > 22))`,
      and `^[0-9]+$` admits a zero-padded value, so bash parses it as OCTAL -- a value like
      `08` throws an arithmetic syntax error rather than comparing, the `if` reads false,
      and the run proceeds AS IF UNDER THE CAP -- driver-reproduced directly
      (`GENERATION=08; ((GENERATION > 22))`: "value too great for base", exit 0, "not
      capped"), the identical failure shape as `autopilot-gate.sh`'s `((10 >= 08))` from
      wave 13, now confirmed in a second, unrelated script. `dispatch-release.sh` merges a
      SUCCEEDING `gh api` call's stderr into its parsed body (`2>&1`), so one benign
      version-warning invents a phantom PR number, flips a real "skip" decision to
      "release", and prints a GitHub Actions notice naming the phantom PR as if it were
      real -- the outcome errs in the twin's documented fail-open direction, but the
      REASONING it publishes is fabricated. `dispatch-watchdog.sh` also folds "the default-
      branch lookup failed" into "the dispatch was refused" (the lookup sits inside a
      command substitution inside an `elif`, where `set -e` is suspended) and, on an
      adjacent line, folds the SAME kind of lookup failure into "proceed anyway" -- two
      neighboring failure paths disagreeing about what an unreachable GitHub API means; a
      `--pending-rerun` flag with no following value is a completely silent exit 1, zero
      bytes on either stream (`${2:-false}` tolerates the missing value, then `shift 2`
      fails and `set -e` fires with nothing left to say). `generate-tag.sh --github-output`
      is a silent no-op when `$GITHUB_OUTPUT` is unset (byte-identical output to omitting
      the flag entirely, so a workflow step silently ships an empty image tag downstream);
      its fail-loud build-config existence check is CWD-DEPENDENT for three of its six
      entries and blames the wrong thing when the working directory is the actual fault;
      and an `else` branch computing a fallback tag from the submodule commit is
      unreachable dead code, since the branch above it always exits before falling through.
      **A process finding about the writer's own exploration, reported rather than
      buried**: probing the "gh is missing" path by pointing `PATH` at bare `/usr/bin:/bin`
      still resolved a REAL `gh` there, reaching real GitHub for one read-only 404 against
      a nonexistent repo before the mistake was caught -- no mutation, but a reminder that
      "point PATH at the system directories" is not the same as "remove a tool," now folded
      into the differential's own gh-free fixture technique.
      **THIRTY-FOURTH WAVE 2026-09-14, opening `.ci/scripts/setup/**`.** `install-deps.sh`
      -> `setup/install_deps.py`, `build-packages.sh` -> `setup/build_packages.py`,
      `install-cli-global.sh` -> `setup/install_cli_global.py`. Driver-verified directly: 54
      tests independently re-run, exit 0; all 3 ledgers K=5, twins byte-untouched, the
      pre-existing tracked `.ci/rediacc_ci/setup/shadow_driver.py` (another session's,
      staged with a 0-line mode-only change) confirmed genuinely untouched by this wave,
      `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all
      scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver**:
      `install-cli-global.sh`'s own "no tarball found" error branch is UNREACHABLE dead
      code -- driver-reproduced directly (`ls rediacc-cli-*.tgz | head -n 1` inside
      `set -euo pipefail` on an empty directory: the pipeline exits 2 under `pipefail`, the
      assignment aborts the script under `set -e`, and the intended error message never
      prints; real behaviour is exit 2 with zero bytes on both streams, not the twin's
      documented message). The same script installs a STALE tarball when more than one
      matches: `npm pack`'s own announced filename is discarded in favor of `ls | head -n
      1`, lexicographic order, so a pre-existing `rediacc-cli-0.0.0-dev.tgz` placeholder
      beats a freshly packed `rediacc-cli-0.8.3.tgz` (and byte ordering separately puts
      `0.10.0` ahead of `0.9.0`) -- the fresh tarball is what then gets deleted by the
      cleanup step while the stale one it installed survives to lose again on every
      subsequent run. `install-deps.sh` never applies `--ignore-scripts` to any of the
      three `private/account` npm trees despite the flag existing specifically to avoid
      native-module rebuild issues, and retries a completely missing `npm` binary three
      times over 30 seconds with no `require_cmd` guard, reporting the eventual give-up as
      a generic "failed after retries" rather than naming the real cause. Three more
      "unknown folded into fine" vacuities in the same family seen repeatedly this session:
      `install-deps.sh --account-only --skip-account` runs zero subprocesses and still
      prints a plain success; `build-packages.sh` treats its own pre-build `rm -rf dist`
      followed by a build that emits nothing as an expected, exit-0 "may be expected"
      outcome -- the exact silent-no-op the cache-clearing step exists to prevent from going
      unnoticed; and a CLI not found in PATH after a global install is a warned-but-green
      exit 0.
      **THIRTY-FIFTH WAVE 2026-09-14, closing `.ci/scripts/ci/**` (bar `detect-pointer-
      bump.sh` and `profiler/sampler-linux.sh`, both owned by other concurrent sessions).**
      `initialize.sh` -> `ci/initialize.py`, `set-image-tags.sh` -> `ci/set_image_tags.py`.
      A deliberate asymmetry, argued in each port's own docstring rather than applied
      uniformly: `initialize.py` calls its six bash siblings out-of-process by relative
      path (one of them, `detect-pointer-bump.sh`, has no port at all, and a six-pair-wide
      differential could not say which pair diverged), while `set_image_tags.py` calls the
      already-ported `derive_image_tag` IN PROCESS. Driver-verified directly: 52 tests
      independently re-run, exit 0; both ledgers K=5 (each re-recorded twice, once for a
      `ruff format` reflow and once for a docstring edit), twins byte-untouched, `check:ci-
      python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver via
      direct source inspection**: `initialize.sh` validates `GITHUB_PAT` explicitly at line
      53 but NEVER validates `GITHUB_REPOSITORY` at all -- it is used bare 166 lines later
      (line 219, inside a git fetch URL), by which point the script has already rewritten
      the global git config's URL rewrite rule and emitted eight outputs -- driver-confirmed
      directly by reading both call sites: `GITHUB_PAT` gets a real `log_error`+exit-1
      guard, `GITHUB_REPOSITORY` gets none, relying entirely on `set -u`'s incidental
      "unbound variable" abort if the caller forgot it. The same script: `IFS=', '` in a
      join only uses IFS's FIRST character, so a log line meant to be comma-and-space
      separated reads as plain comma-joined; a valueless `--output` flag writes a file
      literally named `true` into the repo root with no warning, exit 0; and its container-
      image-exists probe folds "could not ask" (missing docker, a dead daemon, refused
      credentials) into "does not exist" with identical output confidence -- costs an extra
      rebuild rather than a wrong artifact, which is why this one is recorded rather than
      escalated. `set-image-tags.sh` claims full success ("Image tags set...") having
      silently skipped both of ITS OWN overrides when `$GITHUB_ENV` is unset -- the only
      warning printed belongs to a downstream sibling script and describes only that
      sibling's half of the work -- and its own success line reports the INPUT values
      rather than what was actually written to the file.
      **A defect found in an EARLIER wave's already-landed port, outside this wave's file
      ownership, pinned rather than silently worked around**: wave 32's
      `derive_image_tag.py` does not catch `OSError` on an unwritable output target, so
      where the bash twin prints one clean error line and exits 1, the Python port raises a
      10-line traceback -- exit codes agree, stderr does not. A dedicated test
      (`test_an_unwritable_github_env_dies_in_the_sibling_and_the_port_dies_louder`) asserts
      the CURRENT (louder, worse) behavior and its own docstring tells whoever eventually
      fixes `derive_image_tag.py` to delete the pin and assert exact equality instead --
      the fix belongs to that file's owner, not to this wave, and would otherwise have been
      silently rediscovered as a fresh "mystery" divergence.
      **THIRTY-SIXTH WAVE 2026-09-14.** `build-renet.sh` -> `infra/build_renet.py`,
      `inject-env.sh` -> `version/inject_env.py` (as a library-plus-CLI, matching the
      `infra/ci_env.py` precedent for a sourced twin). **`ci-stop.sh` was already ported by
      an earlier wave and was NOT duplicated** -- the writer found it live-and-tracked but
      at the wrong path (`.ci/scripts/infra/ci_stop.py` rather than the `.ci/rediacc_ci/
      infra/` every sibling uses), re-ran its existing ledger to confirm it still asserts,
      and flagged the misplacement as a driver-only relocation decision rather than moving
      a tracked file unasked. Driver-verified directly: 94 tests independently re-run
      across the 2 new files, exit 0; all 3 ledgers (2 new + `ci-stop`'s pre-existing one)
      re-assert K=5; twins byte-untouched; `check:ci-python-lint`/`check:ci-dead-python`/
      `check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one's exact mechanism independently confirmed by
      the driver**: `build-renet.sh` computes its rebuild-trigger "build identity" stamp
      via a `sha256sum` pipeline sitting INSIDE a `printf` argument's command substitution,
      so a missing `sha256sum` (stock macOS ships `shasum`, not `sha256sum`, and this script
      advertises itself as locally runnable) is invisible to `set -e`/`pipefail` and
      SILENTLY BLANKS the hash half of the stamp -- driver-reproduced the exact mechanism
      directly (`ACCOUNT_ED25519_PUBLIC_KEY=KEY-A` and `=KEY-B` through a `sha256sum`-free
      PATH: both produce the identical stamp `default|`) -- meaning two builds signed with
      completely different keys are judged identical and a rebuild the stamp exists
      specifically to trigger is silently skipped, exactly the incident class this
      mechanism was added to prevent. The same script also deletes the existing binary
      BEFORE checking that `go` is even installed, so a missing toolchain leaves the repo
      with no renet binary at all where it previously had a working one; and silently drops
      any unrecognized CLI flag (`--nolicence` for `--nolicense`) rather than refusing,
      producing a default build with no warning. `inject-env.sh --version` with no
      following value silently swallows the NEXT argument even when that argument is itself
      a flag (an unquoted empty expansion drops the token entirely rather than passing an
      empty string), sailing past the twin's own "empty value" guard and silently disabling
      `--strict` on exactly the release path that flag exists to protect
      (`.github/workflows/ci-build-cli.yml:109`, `.github/workflows/ci-build-docker.yml:62,119`); the same script's own header
      claims `set -euo pipefail` stays scoped inside its function and cannot leak into a
      sourcing caller's shell, which is false (`set` options are shell-global in bash, not
      function-scoped) -- latent only because both real callers already set the identical
      three options themselves.
      **THIRTY-SEVENTH WAVE 2026-09-14, opening `.ci/scripts/env/**`.** `create-e2e-env.sh`
      (175 lines) -> `env/create_e2e_env.py`. **Zero stubs needed**: the twin's only
      shell-out is `mkdir -p`, and `RENET_BINARY`/`--renet-path` are pure string
      construction with no probe of any kind. Driver-verified directly: 154 tests
      independently re-run, exit 0; the ledger K=5, twin byte-untouched, no stray `true`
      file left behind (the writer's own transient artifact from probing defect C, cleaned
      up and confirmed gone), `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver against
      the REAL twin (not a fixture)**: a zero-padded `--vm-ram-worker` value is parsed as
      OCTAL by bash arithmetic, and a value like `08192` throws a parse error inside a
      `local total=$((...))` assignment -- the assignment's own reported status is 0 (the
      well-known `local`-masks-a-failing-substitution shape), so the entire RAM-budget
      refusal that should follow is silently abandoned and the script reports success --
      driver-reproduced directly against `.ci/scripts/env/create-e2e-env.sh` itself
      (`--vm-ram-worker 08192 --vm-workers "11 12 13 14"`: prints the "value too great for
      base" parse error to stderr, then still prints "Created E2E test environment", exit
      0), a THIRD occurrence this session of the zero-padded-octal-arithmetic class (after
      wave 13's `autopilot-gate.sh` and wave 33's `dispatch-watchdog.sh`). A related vacuity
      in the same neighbourhood: the worker COUNT itself is computed via an unquoted, glob-
      unescaped `echo $VM_WORKERS | wc -w` (shellcheck-suppressed for both splitting and
      globbing at once), so `--vm-workers '*'` counts however many files happen to sit in
      the CALLER's current working directory instead of the string's own word count, making
      the RAM-budget verdict depend on an unrelated directory's contents. A bare `--output`
      flag with no value writes a file literally named `true` into wherever the script was
      invoked from (the same `parse_args`-turns-a-flag-into-the-string-"true" shape seen in
      `initialize.sh` in wave 35); every `ARG_*`-named environment variable is an
      undocumented alternate way to set any flag, confirmed and preserved in the port so the
      two cannot diverge on a caller's ambient environment.
      **One named divergence, deliberately not closed**: the port's arithmetic evaluator
      covers bash integer literals (decimal/octal/hex/`base#`) and the common operators, but
      not shift/bitwise/comparison/ternary/comma; `--vm-ram-worker '1<<13'` is the shortest
      input where this changes the EXIT CODE itself (twin computes a real number and
      refuses; port falls into the octal-defect's own skip path and accepts) -- pinned by a
      dedicated test asserting both sides so the gap cannot silently rot into an
      unacknowledged claim of full coverage.
      **THIRTY-EIGHTH WAVE 2026-09-14, opening `.ci/scripts/review/**` with a single large
      file given a solo slot.** `claude-review-gate.sh` (898 lines) -> `review/
      claude_review_gate.py` (1,870 lines), covering all five of the twin's arms (the
      go/no-go gate, `--post-report`, `--post-findings`, `--apply-labels`, `--mark`).
      Driver-verified directly: 124 tests independently re-run, exit 0; the ledger K=5
      (re-recorded from zero after a late one-line port edit), twin byte-untouched,
      `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all
      scoped-clean. The raw-argv comparison in this differential is UNEXCLUDED (stricter
      than the sibling `review_status.py` port), because this port passes the twin's own
      five `--jq` programs verbatim rather than reusing a shared budget helper's network
      half -- a dedicated control asserts each jq program is still literally a substring of
      the twin's own source, so the two cannot drift apart silently.
      **Real defects found, the most consequential one independently confirmed by the
      driver via a minimal, exact repro of its awk mechanism**: `--post-findings`'s fence
      scanner (extracting the `json:review-findings` block from a posted PR comment) NEVER
      resets its `capturing` flag once the opening fence is seen, so on a report that
      follows the prompt's own documented shape (a findings fence, then prose, THEN a
      second `json:pr-labels` fence for `--apply-labels`) the scanner runs all the way to
      the LAST closing fence anywhere in the whole document, swallowing the prose and the
      second block into what it then hands to `jq` -- driver-reproduced the exact mechanism
      directly with a two-fence fixture matching the prompt's format: `jq: parse error:
      Invalid numeric literal at line 3, column 0`, exit 5, and because the caller reads
      that failure as "no parseable review-findings block; skipping inline comments" and
      exits 0, every line-anchored finding from a well-formed report is silently dropped
      with no visible failure at all. The sibling `json:pr-labels` scanner (two call sites)
      HAS the missing reset clause the findings scanner lacks, confirming this is an
      omission in one arm rather than a deliberate design choice. `last_marker_sha`'s
      dedup-guard read still swallows a `gh` failure exactly as `common.sh`'s own equivalent
      was fixed to stop doing on 2026-09-10 -- a failed read is indistinguishable from
      "never reviewed," so a transient API failure re-triggers a full, costed INITIAL review
      of a head that was already reviewed minutes earlier; the same swallow recurs in
      `last_marker_id`, turning a failed read into a duplicate POSTed marker instead of a
      PATCH. `emit_review_turns` feeds an unvalidated diff-size answer straight into bash
      arithmetic with no numeric guard, where the otherwise-identical `pr_diff_loc` call
      site nearby DOES have one, so a malformed API response is an `unbound variable` abort
      with NO `go` decision written at all, rather than a decision either way.
      `--mark`'s per-head attempt count is read through a NESTED command substitution
      (`prior=$(f "$(g ...)" ...)`), so `set -e` sees only the outer call's status and a
      `gh` failure in the inner one is invisible -- a head that has spent its full
      per-head ceiling records a fresh "first attempt" instead, resetting the ceiling on a
      transient rate limit.
      **THIRTY-NINTH WAVE 2026-09-14, opening `.ci/scripts/private/**` (a brand-new
      package).** `renet-root-tests.sh` -> `private/renet_root_tests.py`, `run-renet.sh`
      -> `private/run_renet.py` (a registered `check:ci-renet` gate; twin and its
      `---- gate ----` header untouched, port is a separate unregistered file per
      convention), `renet-ebpf-e2e.sh` -> `private/renet_ebpf_e2e.py`. **A hypothesis the
      writer formed, checked, and REFUTED rather than filing as a defect**: suspected the
      ebpf script's "idempotent mount" comment was false on this host's non-GNU `stat`
      (uutils coreutils); a first `strings | grep -x` search came up empty and briefly
      looked like proof, but a wider search showed uutils' `stat` DOES carry `bpf_fs` in
      its type table same as GNU -- no finding, correctly not reported as one. Driver-
      verified directly: 79 tests independently re-run, exit 0; all 3 ledgers K=5
      (re-recorded once after a docstring correction), twins byte-untouched, `check:ci-
      python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver**:
      `renet-root-tests.sh` guards each root-tagged test by SUBSTRING match
      (`grep -q -- "--- PASS: $t"`), not exact match, so a test later renamed to
      `TestLoadState_PreservesDataAndMore` satisfies the guard for the ORIGINAL name
      `TestLoadState_PreservesData` even though that exact test no longer exists --
      driver-reproduced directly (a synthetic `--- PASS:` line for the longer name still
      satisfies a `grep -q` for the shorter one). The guarded test list is also spelled
      TWICE (once in the `-run` regex, once in the shell loop that checks for `PASS`
      lines), so adding a test to the run pattern without also adding it to the loop
      leaves it completely unguarded. `run-renet.sh` exits 0 having run nothing at all on
      any checkout missing the `private/renet` submodule specifically because `CI` is
      compared against the STRING `"true"` -- `GITHUB_ACTIONS=true` with `CI` merely unset
      takes the same silent local-arm exit as a genuinely local dev checkout, a choice
      `common.sh` itself makes deliberately and which is therefore pinned, not repaired.
      Both Go test runners in this trio send their full failure transcript and
      `::error::` annotation to STDOUT rather than stderr, and print nothing at all until
      `go test` finishes (up to 300 seconds of total silence), because the capture is
      `out="$(go test ... 2>&1)"` -- correct for a GitHub Actions annotation, surprising
      for any caller that separates the streams.
      **FORTIETH WAVE 2026-09-14, closing `.ci/scripts/private/**`'s remaining small
      files.** `renet-integration.sh` -> `private/renet_integration.py`, `renet-csi-
      sanity.sh` -> `private/renet_csi_sanity.py`, `run-account.sh` -> `private/
      run_account.py`. A ledger-technique lesson worth carrying forward: the scratch
      fixture root must be a FIXED path, not `mktemp -d`, because the ledger's `old`/`new`
      commands are two SEPARATE invocations of the recorder -- a per-invocation temp dir
      puts two different absolute paths into a twin's own error message (e.g. `run-
      account.sh`'s "Account server not available at <dir>"), producing a false
      `MISMATCH_FINDINGS` on nothing but the path itself. Driver-verified directly: 100
      tests independently re-run, exit 0; all 3 ledgers K=5, twins byte-untouched,
      `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all
      scoped-clean.
      **Real defects found, the headline one independently confirmed by the driver via a
      minimal repro of its exact shell mechanism**: `renet-csi-sanity.sh`'s
      `apt-get update -qq && apt-get install -y -qq btrfs-progs cryptsetup-bin` looks
      guarded under `set -e` but is not, because `set -e` does not fire on a non-final
      member of an `&&` list -- a failing `update` is silently swallowed, `install` never
      runs, and the script still announces "Installing btrfs-progs + cryptsetup..." and
      later reports full conformance -- driver-reproduced the exact mechanism directly
      (`set -euo pipefail; if true; then false && echo yes; fi; echo SURVIVED` prints
      SURVIVED), a variant of the `set -e`-blind-spot class already seen with command
      substitutions (waves 15, 22, 26) now confirmed for AND-lists too. The same script
      collapses a failing `go test`'s real exit code (2 for a build failure, 1 for a test
      failure) to a flat 1 via `|| { echo "$out"; exit 1; }`, making the two
      indistinguishable to any caller. `renet-integration.sh` hand-rolls its own
      submodule-presence guard instead of using `common.sh`'s `require_submodule`, and in
      doing so drops the CI arm both sibling scripts have -- a missing submodule reports a
      plain warm exit 0 on a real CI runner (`.github/workflows/ct-tests.yml:1762`), not the harder failure
      the CI arm exists to produce elsewhere; its argument parser also has no
      unknown-argument arm, so `--nocleanup` (one hyphen short of `--no-cleanup`) is
      silently accepted and ignored, running the suite WITH cleanup rather than refusing.
      `run-account.sh` runs a full `npm ci` before its stage-name `case` statement even
      validates the stage, so an unknown or intentionally-refused stage (e.g. `deploy`,
      whose entire purpose is to refuse) pays the full install cost first anyway.
      **FORTY-FIRST WAVE 2026-09-14, the largest single-file port this campaign has done.**
      `cleanup-versions.sh` (2055 lines) -> `housekeeping/cleanup_versions.py` (3,624
      lines), covering all 14 phases (the brief under-listed two -- `cleanup_d1_databases`
      and the six-sub-phase `cleanup_r2`, which reuses the already-ported
      `core.release_state_validator` -- the writer read `run_all_phases` directly rather
      than trusting the dispatch prompt's own phase list, and ported both anyway).
      Driver-verified directly: 121 tests independently re-run, exit 0; the ledger K=5
      (re-recorded once after a `ruff format` reflow), twin byte-untouched, `check:ci-
      python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Two genuine bugs the differential caught in the PORT itself, fixed before
      landing**: a `jq_sort_by` reimplementation broke ties on the whole element instead
      of the sort key alone (jq's own sort is stable on the key only -- caught by a tied
      row in the jq behavioral corpus); the dry-run/real-run summary verb ("freeing" vs
      "freed") was hard-coded to the wrong one in Phase 12.
      **Seven real defects found across the 14 phases, catalogued as HAZARD 1-9 in the
      port's own module docstring, two independently confirmed by the driver via direct
      mechanism repros**: a zero-padded `BRANCH_MAX_AGE_DAYS` (e.g. `08`) is a bash
      arithmetic EXPANSION error that unwinds every remaining function frame -- Phases 10
      through 12, the delete total, and "Housekeeping complete" all silently never run,
      with no phase named in the failure -- the same zero-padded-octal class confirmed
      directly four times now this session (waves 13, 33, 37, and this one).
      **A second defect needing no operator mistake at all, needing only a rate-limited or
      flaky `gh` call, driver-reproduced via its exact mechanism**: the Actions-cache
      listing is `caches="$(gh api ... | jq -s 'sort_by(...)' || echo "[]")"` under
      `pipefail` -- when `gh` fails, the WHOLE PIPELINE's status trips the `||`, but `jq -s`
      had already emitted its own `[]` for the (now-truncated) stream before the pipe
      broke, so the variable ends up holding TWO JSON values back to back --
      driver-reproduced directly (`gh` forced to exit 1: `caches` becomes literally
      `[]\n[]`, and `jq length` on that reports `0\n0`, matching the twin's own live
      failure verbatim: `[[: 0\n0: arithmetic syntax error`) -- a transient GitHub API
      hiccup is enough to kill the whole nightly with a cryptic diagnostic naming no phase
      and no cause. Phase 5b (worker cleanup) never calls `record_delete`, so its deletions
      are the only ones in the entire script not charged against
      `MAX_DELETES_PER_RUN`; Phase 1's dry-run arm never increments its own `deleted`
      counter, so `--dry-run` always reports "would delete 0 of N" regardless of how many
      it actually named (nine of the other twelve phases increment correctly); every
      numeric CLI flag and `MAX_DELETES_PER_RUN` itself are read with raw bash arithmetic
      and never validated, so a zero-padded `--versions 08` evaluates FALSE for every
      comparison (treating every item as eligible) while `--versions 010` silently keeps
      eight; Phase 2's four-call date-fallback is UNREACHABLE by its own documented route,
      because a tag with no tagger date returns the four characters `null` (not empty), so
      the `-z` emptiness check never fires and the literal string `"null"` travels on as a
      date (retains rather than deletes -- the safe direction, still a real gap). NINE of
      the fourteen phases (1,2,3,4,5,6,7,7b,9,11) fold "the listing call failed" into
      "nothing here to delete" -- Phase 5b is the only one that fails closed, Phase 10 the
      only other one that even says it might not have been able to look -- the
      "unanswerable folded into a clean pass" class, now confirmed at this scale across a
      whole housekeeping script rather than one call site at a time.
      **FORTY-SECOND WAVE 2026-09-14: `concurrent-fork-isolation-test.sh`, the file this
      session had earlier (incorrectly, before the operator's direct correction) treated as
      belonging to another session -- confirmed a legitimate, fully portable target.** ->
      `private/concurrent_fork_isolation_test.py`. Proved portable despite reproducing a
      real renet race condition on a live worker VM: nothing the differential needs to
      verify depends on the VM except the CONTENT of child-process stdout, which the
      recording fakes supply. Driver-verified directly: 76 tests independently re-run, exit
      0 (211s -- the twin's own 30-iteration polling loop, ported faithfully sleeps and
      all), the ledger K=5, twin's diff still just the pre-existing 1-line fix (untouched
      by this wave), `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **A harness-quality finding worth carrying forward**: the shadow-gate recording call
      log's ordering is NOT stable for a pipeline's right-hand member IN THE TWIN ITSELF --
      12 consecutive twin-only runs put `grep` before `tail` 7 times and the reverse 5
      times, and running under `pytest -n 8` reordered further. The writer's first fix
      (swap adjacent declared pairs) passed serially and failed under parallel load; the
      working rule is to SPLIT rather than reorder: right-hand pipeline members (`sort`/
      `head`/`tail`/`tee`) are pulled out of the ordered call-log spine and compared as a
      sorted multiset, while the causally-ordered remainder keeps exact-order comparison. A
      dedicated test re-derives the instability directly rather than inheriting the claim.
      **Two genuine bugs the differential caught in the PORT itself, fixed before
      landing**: a `rdc ... | tee log` port draft with `tee` absent left `rdc`'s own stdout
      going nowhere (the real pipe reader never appeared); a `grep | tail` port draft with
      `grep` absent returned early and skipped `tail` entirely, when real bash forks BOTH
      pipeline members before either execs, so `tail` runs regardless of `grep`'s fate --
      both fixed with a real `os.pipe()`-based helper matching bash's own fork-both
      semantics.
      **Real defects found, two independently confirmed by the driver via direct source
      inspection**: four separate `log_info "✓ ..."` calls carry a literal `✓` in their own
      message text on top of the logging helper's own automatic `✓` prefix, producing a
      double-tick (`✓ ✓ ...`) on every one of four success lines -- driver-confirmed
      directly by reading all four call sites. The parent-counter poll loop's `sleep 2`
      sits AFTER its own `[[ ... ]] && break` check inside a 30-iteration `for` loop, so a
      counter that never reaches the target burns all 30 sleeps including a wasted one on
      the very last iteration, which sleeps two full seconds after the loop's last possible
      read -- driver-confirmed directly by reading the loop body. A non-numeric remote
      payload for the "foreign project count" check kills the run with `unbound variable`
      naming the WRONG variable under `set -u`, and a two-word payload instead evaluates
      the arithmetic test as FALSE, silently treating a real cross-project name collision
      as "no foreign projects present" -- the same "unanswerable folded into a clean pass"
      class seen throughout this session, now confirmed to fail in the DANGEROUS direction
      (accepting an isolation violation) rather than the usual safe-refusal shape. A bare
      empty-array expansion prints a stray indented line ahead of the real error when zero
      binds are found; `fork_sock` silently takes the LAST non-parent socket rather than a
      specifically-identified fork's, benign only while exactly two sockets exist.
      **DRIVER FIX 2026-09-14, after the operator's "no other session" correction**: `ci-
      stop.sh`'s port (`ci_stop.py`) had been landed by an earlier wave, correctly written
      and tested, but at the wrong path -- `.ci/scripts/infra/ci_stop.py` (tracked,
      committed) instead of `.ci/rediacc_ci/infra/` where every sibling port lives. `git mv`
      to the correct location, fixed the one path reference in its own differential
      (`test_infra_ci_stop.py`'s `PORT` constant and its own docstring citation), re-ran
      its 10 tests (still pass), re-asserted its `w7p6-ci-stop` ledger (still holds, K=5),
      and confirmed no new `check:ci-python-lint`/`check:ci-dead-python` findings from the
      move. This box's next writer batch also correctly recognized `clone-d1.sh`,
      `detect-pointer-bump.sh`, and `concurrent-fork-isolation-test.sh` as this session's
      own earlier direct bash-twin fixes (not another session's) and legitimate porting
      targets, per the same correction.
      **FORTY-THIRD WAVE 2026-09-14: `compose-healthcheck-smoke-test.sh`, another VM-
      dependent integration test confirmed portable by the same reasoning as wave 42.** ->
      `private/compose_healthcheck_smoke_test.py`. Driver-verified directly: 74 tests
      independently re-run, exit 0 (128s -- real polling-interval sleeps ported
      faithfully), the ledger K=5, twin and `package-lock.json` both confirmed untouched,
      `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all
      scoped-clean. The writer's own follow-up caught and corrected a vacuity in its OWN
      verification: a first attempt to confirm its 74 tests ran inside the full suite used
      `grep -c "test_..." <log>` against `pytest -q`'s xdist output, which only ever prints
      `FAILED` lines and dots -- a PASSING file never appears by name, so "0 mentions" would
      have been misread as "0 failures" when it actually meant nothing was checked at all;
      corrected to `--collect-only` naming all 74 test ids explicitly, the only way to prove
      the gate's `testpaths` genuinely covers them.
      **A near-miss during exploration, reported rather than buried**: a PREPENDED
      (rather than replaced) scratch PATH let a probe resolve the REAL `rdc` symlinked at
      `~/.local/bin/rdc` to this repo's own `rdc.sh`, which ran `npm install`/`npm rebuild`
      against the live checkout before failing on `cpu-features`'s `EACCES` -- driver-
      confirmed `package-lock.json` untouched afterward. Harness now REPLACES PATH
      unconditionally rather than prepending, and asserts every deliberately-absent tool is
      genuinely unreachable; the incident is recorded in the differential's own module
      docstring so it is not rediscovered.
      **Real defects found, the headline one independently confirmed by the driver**:
      `TIMEOUT_SECS` reaches bash arithmetic unvalidated, so a zero-padded value like `060`
      is parsed as OCTAL -- driver-reproduced directly (`TIMEOUT_SECS=060`: the computed
      window is 48 seconds, not 60), a fifth confirmed occurrence of the zero-padded-octal
      class this session, while the script's own log line one row above still prints
      "timeout 060s" as if nothing were wrong. A SEPARATE, file-specific `set -e` gap sits
      right beside it: an arithmetic EXPANSION error (`TIMEOUT_SECS=12abc`, not merely
      unset) does NOT abort a `.sh` FILE the way the identical fragment aborts under
      `bash -c` (driver's own minimal `bash -c` comparison in the report showed the
      inline form dying immediately while the file form survives to the next line and dies
      there instead, on a variable -- `deadline` -- the caller never typed). A missing
      `ssh` binary is silently indistinguishable from a live connection failure during
      polling, because `2>/dev/null` is applied before the command-not-found diagnostic can
      even form; `rdc machine add` failing for ANY reason (a malformed IP, a missing `rdc`,
      an auth failure) is reported as "already registered" regardless of the real cause;
      and both of the script's own success lines double their `✓` glyph the identical way
      wave 42's four success lines did, now a second script carrying the exact same
      logging-helper-plus-manual-prefix duplication.
      **FORTY-FOURTH WAVE 2026-09-14: the three files confirming the "no other session"
      correction, all landed successfully.** `clone-d1.sh` -> `deploy/clone_d1.py`,
      `detect-pointer-bump.sh` -> `ci/detect_pointer_bump.py`, `typecheck-workers.sh` ->
      `quality/typecheck_workers.py` (a registered `lint:unused` gate; twin's header
      untouched, port carries none, a dedicated test asserts the asymmetry using the real
      `gate-header.ts` OPEN pattern rather than a substring check). Driver-verified
      directly: 85 tests independently re-run, exit 0; all 3 ledgers K=5, both twins'
      diffs confirmed to be nothing more than their pre-existing 1-line fixes from earlier
      in this session, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean. `clone-d1.sh` remains `blocked` in `.ci/shadow/w7p5a-
      status.json` for the real-run clause only, same standing as several already-ledgered
      files -- left alone, `check:ci-w7p5a-real-run-blockers` still 32/16 afterward.
      **A harness technique worth naming**: `detect-pointer-bump.sh`'s differential uses a
      REAL git repository built from plumbing (`update-index --cacheinfo 160000,...` for
      gitlinks, `commit-tree` for a genuine two-parent merge commit) rather than a fake
      `git`, because two of its defects are consequences of the actual `pull_request`
      merge-commit shape and are invisible in any fixture where HEAD is simply the branch
      tip -- porcelain `git commit` is hook-blocked even inside a scratch repo, so plumbing
      commands were required regardless.
      **Real defects found, the headline one independently confirmed by the driver against
      both the tree and a live workflow file**: `clone-d1.sh --sanitize` has been silently
      dead since 2026-04-06, when `sanitize-d1.sql` (the file it redirects into) was deleted
      in an unrelated commit and nothing recreated it -- yet `.github/workflows/edge-clone-d1.yml:78` is a LIVE caller still passing `--sanitize` on every run -- driver-
      confirmed both halves directly (the SQL file is genuinely absent from the tree; the
      workflow line genuinely still passes the flag). The script fails closed (dies on the
      redirection before the import step), so the practical exposure is an availability
      failure rather than a silent PII leak, but the comment claiming "the target D1 never
      sees real PII" is true only because the target sees nothing at all. The same script's
      foreign-key verification folds "could not run" into "0 violations, passed" -- an empty
      `FK_RESULT` makes `jq` exit 0 printing nothing, so the intended `|| echo "0"` fallback
      never fires and the numeric guard is simply never violated, a sixth occurrence of the
      "unanswerable folded into a clean pass" class this session. `detect-pointer-bump.sh`
      applies its own documented pointer-bump-only guard fix to the WALK but not to
      `head_sha` itself, so on every `pull_request` event the guard compares the synthetic
      merge commit against itself and can never fire, forcing every such PR down the "no
      baseline within 5 commits" slow path regardless of whether it's pointer-bump-only;
      the same merge-commit shape also lets Step 3's net-diff calculation pick up the
      target branch's own unrelated changes on any PR whose target has moved since the
      merge commit was formed. An empty or missing `.gitmodules` is a hard, silent exit 1 --
      `git config`'s own no-match status survives `pipefail` all the way through `set -e`
      before the intended fail-safe message is ever reached. `typecheck-workers.sh` has no
      `*)` arm in its argument parser, so a one-letter typo like `--isntall` runs the FULL
      pipeline (install and typecheck) rather than refusing; a partial `find` failure
      (permission denied on one worker directory) is invisible through a process
      substitution and reports a smaller, silently-incomplete set as a clean success; and
      `node_modules` freshness is checked by existence only, never by staleness, which the
      twin's own comment already names as the thing that breaks knip.
      **FORTY-FIFTH WAVE 2026-09-14, opening `.ci/scripts/build/**`.** `build-www.sh` ->
      `build/build_www.py`, `build-json.sh` -> `build/build_json.py`, `buildx-push-
      web.sh` -> `build/buildx_push_web.py`. **A second occurrence of the "no other
      session" correction, self-resolved**: the writer's own report flagged the
      concurrently-appearing `build_cli.py`/`build_linux_packages.py`/`pack_cli_npm.py` in
      the same package as "a concurrent session" -- these are in fact batch PP, a second
      writer this driver dispatched into the same wave, not another session; noted here so
      the pattern is recognized on sight rather than re-investigated. Driver-verified
      directly: 40 tests independently re-run, exit 0; all 3 ledgers K=5 (re-recorded once
      after an env-registry alias fix), twins byte-untouched, `check:ci-python-lint`/
      `check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **The env-registry alias trap caught by measurement rather than memory**: the
      writer's first `buildx_push_web.py` read its five required names in a loop
      (`os.environ.get(name, "")`), and running the registry gate's own `scan_module`
      against it returned `['*name', 'ACCOUNT_ED25519_PUBLIC_KEY']` -- the loop form would
      have registered only an opaque expression, leaving four of five real inputs
      undeclared while the gate stayed green. Unrolled to six literal call sites before
      landing; this is the same class of trap now caught in three separate waves (15, 18,
      45) purely because writers ran the gate's actual scanner rather than trusting the
      convention from memory.
      **Real defects found, the headline one independently confirmed by the driver via
      direct source comparison against a sibling script**: `buildx-push-web.sh` never
      `cd`s to the repo root before its docker build, unlike its own sibling `build-
      www.sh` which does exactly that one line after computing `SCRIPT_DIR` -- driver-
      confirmed by grepping both twins for `get_repo_root`/`cd "` side by side: `build-
      www.sh` has it, `buildx-push-web.sh` does not, anywhere -- so the build context and
      the relative `--file Dockerfile ./` argument are whatever the CALLER's cwd happens
      to be, unchecked; safe today only because every live GitHub Actions `run:` step
      starts at the workspace root. The same script never validates `PLATFORM` beyond
      splitting it on `/`, so `PLATFORM=nonsense` or `PLATFORM=linux/` both push a
      successfully-tagged image with a garbage or bare-hyphen architecture suffix despite
      the twin's own refusal message promising only `linux/amd64` or `linux/arm64`; its
      "optional" build-arg is unconditionally passed even when empty, contradicting the
      twin's own header, because a Dockerfile cannot distinguish an empty `ARG` from an
      unset one. `build-www.sh`'s `require_dir`/`require_file` calls both pass a
      human-readable second argument that `common.sh` silently drops (reads only `$1`), so
      a real failure message never names what the check was actually verifying -- a live
      instance of the same first-argument-only class already seen for `require_cmd`/
      `require_var`. `build-www.sh` and `build-json.sh` report the identical missing-
      output failure in two different sentences (one via the shared library helper, one
      hand-rolled), and the hand-rolled one is the more informative of the pair. Both
      `build-www.sh` and `build-json.sh` flatten npm's real exit code to a bare 1
      (indistinguishable OOM-kill vs. typecheck failure), while `buildx-push-web.sh` one
      file over propagates docker's real exit code verbatim -- inconsistent conventions
      within the same directory, not a single twin's isolated choice.
      **FORTY-SIXTH WAVE 2026-09-14, second slot of the same pair, continuing `.ci/scripts/
      build/**`.** `pack-cli-npm.sh` -> `build/pack_cli_npm.py`, `build-linux-packages.sh`
      -> `build/build_linux_packages.py`, `build-cli.sh` -> `build/build_cli.py`.
      Driver-verified directly: 67 tests independently re-run, exit 0; all 3 ledgers K=5,
      twins byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean. **`build-linux-packages.sh`'s own header makes a
      falsifiable claim, and the writer checked it rather than believing it**: that adding
      `-uo pipefail` "cannot change the outcome" of `[[ -f "$musl_binary" ]] && binary=
      "$musl_binary"`'s glibc fallback -- verified directly on this host's bash 5.3.9
      (`set -euo pipefail; [[ -f /nope ]] && X=1; echo alive` prints alive, rc 0): the
      claim holds, correctly recorded as a non-finding rather than assumed.
      **A ledger-technique addition worth keeping**: a fake `jq` that writes its `call:`
      recording line to STDOUT rather than stderr corrupts the very JSON manifest the twin
      redirects that stdout into, silently swallowing the finding; fakes standing in for
      any tool whose stdout IS the artifact under test must log to stderr only.
      **Real defects found, the headline one independently confirmed by the driver via a
      minimal repro of its exact mechanism, and the most consequential defect found this
      session**: `pack-cli-npm.sh` injects the release version with `jq ... >tmp && mv tmp
      real`, and when `jq` fails, `set -e` does not fire on a non-final AND-list member --
      the script prints "Injected version X into package.json" (a fabricated success
      message) and continues to pack a tarball from the UNTOUCHED, unversioned manifest,
      exit 0 -- driver-reproduced the exact sequence directly (a failing fake `jq`: the log
      line prints, "still running" prints, `package.json` is confirmed unchanged, rc=0) --
      and this sits on a real release path (`.github/workflows/ci-build-docker.yml:91` passes the real next
      version), so a transient `jq` failure would silently publish a `rediacc-cli-0.0.0-
      dev.tgz` under a green check. The neighbouring "no tarball found" branch is
      unreachable dead code for the identical AND-list reason applied to `ls | head`, so the
      one failure this script's author wrote a message for reports nothing and exits 2
      instead. The tarball is selected by lexical (not version) sort from a directory
      nothing cleans, so `0.10.0` sorts before `0.9.0` and a later, lower-numbered rebuild
      silently re-packs and announces the stale higher-numbered tarball.
      `build-cli.sh`'s argument parser has no `*)` arm at all: `--help`, `-h`, and any
      typo of `--no-bundle`/`--no-verify` are all silently accepted and run a FULL build,
      while the header's own documented flags (`--bundle`, `--verify`) are no-ops since
      both already default to true; and npm's real exit code (9, 127, 130, ...) is
      discarded in favor of a flat 1 on every failure. `--verify` itself only checks that
      two output paths EXIST, so an empty or stale `index.js` from a half-completed build
      passes verification cleanly.
      **FORTY-SEVENTH WAVE 2026-09-14, second slot of the same pair.** `build-pages.sh` ->
      `build/build_pages.py`, `generate-cli-manifest.sh` -> `build/generate_cli_manifest.py`.
      **The third file in this wave's original scope, `canonicalise-gpg-key.sh`, was
      already ported by an earlier (Sep 10, pre-session) wave** -- the writer verified the
      existing port's docstring, tests (10, K=5 ledger) genuinely matched before leaving it
      untouched, rather than assuming and rather than duplicating. Driver-verified directly:
      51 new tests independently re-run, exit 0, plus the pre-existing `canonicalise-gpg-
      key` ledger re-confirmed still holding; all 3 ledgers K=5, twins byte-untouched,
      `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all
      scoped-clean. **A small, local finding fixed inline rather than deferred**: another
      already-landed port's differential (`test_proxies_cli_manifest.py`) carried a
      docstring claiming `generate-cli-manifest.sh` "stays bash and unported" -- now false
      as of this wave -- corrected in place (one clause, re-verified compiling and its own
      3 tests still passing), since a one-line comment fix inside a file this wave already
      needed to reason about is exactly the "small and local, fix immediately" case rather
      than an owed-but-not-touched item.
      **Real defects found, the headline one independently confirmed by the driver on
      BOTH halves**: `build-pages.sh`'s CLI-manifest packaging block is dead code under the
      DEFAULT invocation, because `OUTPUT_DIR` defaults to the exact same `dist` the block
      later checks against a HARDCODED literal (`[[ -f "dist" + "/cli-manifest/manifest.json"
      ]]` in the twin, joined back together on disk, not built from `$OUTPUT_DIR`), and
      `rm -rf "$OUTPUT_DIR"` runs first -- driver-confirmed directly (`OUTPUT_DIR="${ARG_OUTPUT:-
      dist}"` at line 22, `rm -rf "$OUTPUT_DIR"` at line 43, the literal-path check at line
      58, all reading the identical `dist` by default) -- AND driver-confirmed that nothing
      in the tracked tree writes to that path at all (a tree-wide search for the joined
      literal, outside this one file, returns nothing), so the block has never fired in this
      repository's history; the unconditional summary line claiming the CLI manifest was
      packaged prints regardless. `cp -r packages/www/dist/*` has no `nullglob`, so an
      empty or dotfile-only `dist/` is a raw, uninformative `cp` error rather than a named
      refusal; the argument parser has no `*)` arm, so a one-character flag typo silently
      falls back to the default output directory and DELETES the repo's real `dist/` via
      the unconditional `rm -rf` at startup; `workers/www`'s existence is never checked
      before the final copy step, so a missing directory fails only after the entire rest
      of the package has already been assembled. `generate-cli-manifest.sh` has no
      `cd "$(get_repo_root)"` at all -- the third confirmed instance of this exact missing-
      call class this session -- so an explicit `--input` resolves relative to the CALLER's
      cwd while the default resolves to an absolute repo-rooted path, working in CI only
      because both live callers happen to run from the repo root; a manifest built with
      zero binaries is a clean exit 0; every malformed checksum shape (empty, truncated,
      multi-line, wrong-length) collapses to the identical warning with no effect on exit
      status; and the script's own usage block never mentions `--channel`, the one flag a
      live workflow caller actually passes and the one that decides which URL shape ships.
      **FORTY-EIGHTH WAVE 2026-09-14, second slot of the same pair.** `build-cli-musl.sh`
      -> `build/build_cli_musl.py`, `prepare-cli-assets.sh` -> `build/
      prepare_cli_assets.py`, `extract-renet-from-image.sh` -> `build/
      extract_renet_from_image.py`. Driver-verified directly: 73 tests independently
      re-run, exit 0; all 3 ledgers K=5 (each re-recorded once after adding the comment-
      byte audit omitted from the first pass), twins byte-untouched, `check:ci-python-lint`/`check:ci-dead-python`/`check:ci-em-dash-surfaces` all scoped-clean.
      **Two measurement corrections the differential forced, named as process evidence
      rather than smoothed over**: the writer's first draft guessed `set -u` line numbers
      from reading rather than driving (32/36/30 assumed vs 33/37/31 actual for the two
      twins) and fixed them against the real output; and a first `criu_versions`
      implementation called `strings` ONCE and applied both regexes to it, while the twin's
      own `{ ...; ...; } | sort -u` shape opens `strings` TWICE -- the call log showed the
      mismatch directly, and "how many times a script executes a program" was corrected as
      a behavioral fact rather than an implementation detail.
      **Real defects found, the headline one's exact mechanism independently confirmed by
      the driver via a nested-vs-flat command-substitution comparison**: `prepare-cli-
      assets.sh`'s `map_arch` validation runs its `exit 1` refusal two command
      substitutions deep (`a=$(f)` itself inside a further `$( ... )`), and bash does NOT
      propagate `errexit` into a command substitution nested inside another one -- driver-
      reproduced the exact distinction directly (`g` called flatly with the identical
      failing assignment: dies at rc=1 as expected; the SAME assignment nested one level
      deeper inside `R=$( ... )`: survives, prints the following line, exits 0) -- so
      `--arch bogus` prints the refusal message and then completes with a FULL, valid-
      looking asset set at exit 0 rather than aborting. This is a new, deeper variant of
      the "set -e blind spot on a command substitution" class (waves 15, 22, 26, 40) --
      previously seen one level deep, now confirmed two levels deep changes nothing about
      whether the abort propagates. The same script's asset count is off by one in every
      case (`printf '%b'` without a trailing newline undercounts separators by exactly
      one, while the actual file-writing `printf '%b\n'` two lines later is correct), and
      its `--platform` flag is validated by nothing at all despite the usage text promising
      `linux|mac|win` -- `--platform banana` is byte-identical to `--platform linux`.
      `build-cli-musl.sh`'s `--dry-run` preview runs BEFORE the real architecture
      validation, so it happily previews an architecture the real run would refuse
      outright, and its output verification is existence-only, so a stale binary left by
      an earlier build ships silently as if it were the fresh musl build just requested.
      `extract-renet-from-image.sh`'s CRIU version check is disarmed by a MISSING
      `strings` binary rather than a present one -- the command-not-found diagnostic is
      itself swallowed by the same `2>/dev/null` guarding the real check, so "the tool to
      verify with is absent" silently becomes "cannot verify, proceeding" on the one
      component the twin's own comment already names as a known drift risk -- the seventh
      confirmed instance of "unanswerable folded into a clean pass" this session.
      **FORTY-NINTH WAVE 2026-09-14, freeing the slot batch RR closed.** `build-renet.sh`
      (256L, "build full renet binaries with embedded CRIU/rsync assets") -> `build/
      build_renet.py`, distinct from the ALREADY-PORTED `infra/build-renet.sh` -> `infra/
      build_renet.py` (unrelated file, same basename, different directory -- the
      collision flagged and disambiguated before dispatch). Ledger id deliberately
      `w7p6-build-renet-full`, not `w7p6-build-renet`, to avoid overwriting the existing
      pair's ledger. Driver-verified directly: 37 tests independently re-run, exit 0;
      `w7p6-build-renet-full` ledger K=5 over 5 distinct trees (`--assert --k 5` exit 0);
      twin byte-untouched (`git diff` empty); both new files compile; `check:ci-python-lint` and `ruff format --check` clean on both; em-dash grep no match; scoped
      `check:ci-dead-python` output has zero mentions of `build_renet`; file modes 755/644
      as expected. Headline defect (#2 below) independently reproduced by the driver, not
      just re-run from the writer's transcript: `bash .ci/scripts/build/build-renet.sh
      --version 1.2.3 --skip-embed --output private/absent/deep` -> `rc=1`, BOTH streams
      empty, `private/absent` never created.
      **A real bug in the writer's own port, caught by the ledger fixture and fixed before
      landing**: `grep` is a shell FUNCTION in the sandbox, so a self-referential fixture
      symlink built via `command -v grep` pointed at itself; fixed with `type -P`. The
      corrected control then exposed a genuine twin/port divergence -- `! file "$binary" |
      grep -q "not stripped"` under `pipefail` takes the "stripped" arm when `grep` is
      ABSENT, while the first Python draft's `in`-test still read the text -- so the port
      now runs both halves of both pipelines as real subprocesses. Also caught pre-landing:
      `output / "renet-%s-%s" % (goos, arch)` is a `TypeError` (`/` binds tighter than `%`),
      13 red tests on first run.
      **Real defects found, reproduced not fixed:** (1) a missing `file(1)` reports every
      binary as stripped at exit 0 (`:242`; `file` is never `require_cmd`ed while `jq`/
      `zstd`/`go` all are) -- the eighth confirmed "unanswerable folded into a clean pass"
      this session; (2) `--output` with a non-existent parent dies silently at exit 1 with
      BOTH streams empty (`:64`, GNU `readlink -f` needs every component but the last to
      exist, `set -e` takes the status one line before the `mkdir -p` that would have fixed
      it) -- driver-reproduced above; (3) a malformed or empty pnpm lockfile makes the
      completeness check vacuous and the build pass, because `jq` runs inside a PROCESS
      SUBSTITUTION at `:132-140` whose exit status `set -e` cannot see -- a new variant of
      the command-substitution-vs-process-substitution `errexit` blind spot (waves 15, 22,
      26, 40, 48), this one on the "must break HERE, not later as a cryptic COPY error"
      check the twin's own comment names as load-bearing; (4) no staged assets at all is a
      raw, unguarded `ls` glob error at exit 2 with no `✗` line naming the real problem
      (`:86`); (5) `:107 if [[ -n "$OUTPUT_DIR" ]]` can never be false, so the export block
      it guards reads as opt-out while being unconditional.
      **FIFTIETH WAVE 2026-09-14, first of the last three `.ci/scripts/build/**` files;
      the whole batch hit a real, live `/tmp` inode exhaustion (tmpfs at 100%, `ENOSPC` on
      every Bash call including `true`) partway through, from accumulated pytest fixture
      trees across three overlapping full-suite runs -- CORRECTION, recorded here rather
      than silently overwritten: this was first (wrongly) recorded as having cleared on
      its own via pytest's own retention; the writer that hit it later reported it
      cleared it manually, deleting all but the three newest `/tmp/pytest-of-developer/
      pytest-NNNN` trees (26% used after), which is the real mechanism -- `df -i /tmp`
      was back to 23% by the time this wave was picked up either way; only 1 of the
      batch's 3 target files reached a verified
      state, the other two are separate, later waves.** `build-cli-executables.sh` (344L) ->
      `build/build_cli_executables.py`. Driver-verified directly: 58 tests independently
      re-run, exit 0; `w7p6-build-cli-executables` ledger K=5 over 5 distinct trees; twin
      byte-untouched; both files compile; headline defect (#1 below) independently
      reproduced by the driver with a real PATH stripped of `node`: `rc=1`, both streams
      empty. **Two lint findings caught and fixed by the driver before landing, not
      pre-existing**: an `RUF100` unused `noqa: PLR0912, PLR0915` (the decomposition it
      excused never happened) and an `ISC004` implicit string concatenation inside a list
      literal in the test file, genuinely ambiguous with a missing comma -- wrapped in
      parens, re-verified 58/58 green and ledger still K=5 after. **File mode was 644/644
      as delivered**; driver `chmod 755` on the port (own housekeeping, not a defect).
      Real defects found, reproduced not fixed: (1) a missing `node` is a silent exit 1,
      both streams empty (`:99`, `command -v node` inside an assignment, `set -e`, no
      `require_cmd node` anywhere in the file) -- driver-reproduced above, ninth confirmed
      "unanswerable folded into a clean pass" this session; (2) `strip`/`codesign` are
      never declared either (`:175`/`:167`/`:221`), same class one rung louder since bash
      at least names the missing command; (3) "no checksum tool" is a warning not a
      refusal (`:236`), the build ships a binary with no `.sha256` at exit 0; (4) the
      `--version` smoke test decodes a killing signal as a bare exit code while the
      `doctor` smoke test twelve lines later does the reverse -- an asymmetry carried, not
      smoothed; (5) an explicit `--platform banana` is accepted, builds `rdc-banana-x64`,
      and the one check that would catch it (the smoke-test guard) is the arm the typo
      disables. **A common-library finding that changes how the remaining two ports must be
      written**: sourcing `common.sh` runs `uname -s`/`uname -m` and exports
      `CI_OS`/`CI_ARCH`/`CI_TEMP` before line 22 of ANY caller, including `--help`; a port
      that skips this launches its downstream tools into a different environment, not
      merely a different call count -- found from the call log (twin invoking `uname`
      twice before parsing its first argument), not from reading.
      **FIFTY-FIRST WAVE 2026-09-14, second of the last three `.ci/scripts/build/**` files,
      finishing what the disk-full batch had only drafted.** `build-linux-pkg.sh` (345L) ->
      `build/build_linux_pkg.py`. The draft was UNVERIFIED going in and treated as such: on
      first real run 23/41 tests failed. Driver-verified directly after the writer's fixes:
      49 tests independently re-run, exit 0; `w7p6-build-linux-pkg` ledger K=5 over 5
      distinct trees; twin byte-untouched (worktree blob equals HEAD blob); both files
      compile; `check:ci-python-lint`/`ruff format --check`/em-dash grep/scoped
      `check:ci-dead-python` all clean; modes 755/644 as expected. Headline defect (#2
      below) independently reproduced by the driver with the bare mechanism: `bash -c 'set
      -euo pipefail; x=$( (exit 2) | awk "{print}" ); echo SURVIVED'` -> `rc=2`, "SURVIVED"
      never prints.
      **Draft bugs found and fixed before landing, not pre-existing in the twin**: `mktemp`
      was missing from the fixture's replaced PATH, so every build-path case died on the
      OLD (twin) side with a fixture defect, not a twin one -- the PATH-discipline trap from
      the OTHER direction (replace, don't prepend, but a tool the twin genuinely needs must
      still be listed); `find`'s exit status was discarded by a shared `_capture` helper
      where the twin's own `pipefail` would have propagated it (new `_capture_or_die` added,
      `_capture` re-scoped to sites where the twin ALSO discards status); `Path.mkdir` raised
      a Python traceback where the twin's real `mkdir -p` prints one `mkdir:` line at exit 1
      (shelled out at both sites); Python's `value + "\n"` diverged from bash's own `echo`,
      which parses a value of exactly `-n` as an option rather than data, writing a
      zero-byte key file (new `_bash_echo` helper); and a disguised always-true assertion
      (`... or fmt == "rpm"`) had papered over a wrong RPM filename spelling, replaced with
      an exact per-format artifact-map comparison. One divergence pinned as a DECISION
      rather than fixed: `common.sh`'s `echo -e` renders a literal tab in `--binary 'a\tb'`
      while `rediacc_ci.log` treats the message as data -- both directions asserted, with
      everything else pinned to still match.
      **Real defects found, reproduced not fixed:** (1) `:225 if [[ -f "$PUBLIC_KEY_FILE"
      ]]` has no `else`, so the entire "is this the published key" comparison silently does
      not happen when the file is absent; (2) `:226-227`'s `gpg --show-keys | awk` inside a
      command substitution is a pipeline-under-pipefail `errexit` blind spot, gpg's exit 2
      killing the script with BOTH streams empty and making the `${want_fpr:-<unreadable>}`
      fallback dead code -- driver-reproduced above; (3) the identical shape at `:277-279`
      (`find | head -1`) is LIVE, not latent as first assumed from reading -- driven directly
      against a permission-denied subdirectory and confirmed to die silently; (4) `:291-294`
      is unreachable, the `cp` above it unguarded under `set -e`; (5) `--dry-run` exits 0
      BEFORE any `require_file`/`require_cmd` validation runs; (6) "package signed with X
      key" means a key was CONFIGURED, never that a signature exists, and an RSA key on apk
      is reported as an "APK key"; (7) `echo "$KEY"` at `:187`/`:254` silently produces a
      zero-byte file for a key value of exactly `-n`, feeding directly into defect 2's dead
      fallback.
      **FIFTY-SECOND WAVE 2026-09-14, closing `.ci/scripts/build/** ENTIRELY -- the last
      file in the directory.** `build-pkg-repo.sh` (468L, the largest file in the
      directory, five phases: APT/RPM/APK/pacman repo generation) -> `build/
      build_pkg_repo.py` (1237L). Driver-verified directly: 37 tests independently re-run,
      exit 0 (writer's own sibling regression across all `*build*` tests: 502 passed);
      `w7p6-build-pkg-repo` ledger K=5 over 5 distinct trees; twin byte-identical to HEAD
      (`git hash-object` == the HEAD blob); both files compile; `check:ci-python-lint`/`ruff format --check`/em-dash grep/scoped `check:ci-dead-python` all clean;
      modes 755/644 as expected. Two of the seven headline mechanisms independently
      reproduced by the driver directly: the `gpg | awk` pipeline-under-pipefail death
      (`rc=2`, "SURVIVED" never prints) and the `08` zero-padded-octal arithmetic error
      (`bash: [[: 08: value too great for base`, rc=1, evaluates false).
      **All six defects named in the dispatch brief (from reading, not yet driving)
      confirmed exactly on driving -- no line number or behavior turned out wrong** -- plus
      ONE NEW defect found only by driving: `:387-395`, two `.apk` files for the same arch
      collapse into ONE published package, because `apk_name` is recomputed per loop
      iteration from an `awk` that exits at the first `V:` field of the SAME
      `APKINDEX.tar.gz`, so every file in the loop computes the identical destination name
      -- twin exits 0 with no warning, publishes one package where two were built, while
      claiming (in its own summary line) to have generated metadata for two.
      **Real defects found, reproduced not fixed:** (1) `:389`'s "Docker not available,
      cannot generate APKINDEX" warning does not continue -- `tar xzf ... | awk` is an
      assignment-of-a-pipeline under `pipefail`, and its exit 2 ends the run at exactly the
      warning that claimed it would proceed; (2) `:212-217`'s empty-package vacuity floor is
      APT-only -- driven with one lone `.deb`: exit 0, RPM repo metadata SIGNED over zero
      packages, archlinux config written, summary reports "0 .rpm packages" inside the same
      green tick as everything else; (3) `:213`'s `PKG_REPO_MIN_DEBS=08` disables the floor
      via the same zero-padded-octal class as waves 13/33/41/51 -- driver-reproduced above;
      (4) the `--dry-run` config-writer asymmetry is BIGGER than first read: not only is
      `rpm/rediacc.repo` (`:324-331`) outside the guard while archlinux's config (`:451`) is
      inside it, but the `find -exec cp` that populates the RPM repo (`:300`) is ALSO
      outside the guard, so a `--dry-run` copies real `.rpm` payload bytes into the output
      tree (APT escapes only because its own copy target is a temp pool an EXIT trap
      deletes); (5) `--max-versions` with no following value dies via `shift 2` on one
      remaining arg at exit 1 with BOTH streams completely empty (0 bytes), where every
      OTHER flag's equivalent mistake dies with a named `$2: unbound variable`; (6) the
      `${want_fpr:-<unreadable>}` fallback at `:161-162` is dead code for the identical
      `gpg | awk` reason as `build-linux-pkg.sh` wave 51's finding #2 -- a gpg that exits 2
      on `--show-keys` kills the script silently rather than reaching the fallback; (7) two
      `.apk` files for one arch collapse into one published package, described above.
      `.ci/scripts/build/**` is now FULLY PORTED, bar nothing.
      **DRIVER FIX 2026-09-14, chasing check:ci-pytest's first clean full-suite run in this
      campaign's lifetime.** `.ci/scripts/build/**` closing freed a background `check:ci-
      pytest` run that finally completed on a quiesced tree (earlier attempts had all been
      corrupted by the same `/tmp` inode exhaustion recorded in waves 50-51) and surfaced 77
      failures across 24 files -- driver-verified as NONE in files this campaign's waves
      touched, so investigated rather than dismissed per rule 3. Nine real, pre-existing bugs
      found and fixed, unrelated to any single wave's port but blocking the gate suite
      outright: (1) `.ci/config/env-manifest.json` had `ACTIONS_ALLOWLIST_MIN` duplicated
      into BOTH the `gate-seam` and `tombstone` shards, throwing a hard `doc-providers.ts`
      exception that cascaded into ~9 unrelated test files (doc-region-parity, docs-gen,
      embed-credits, hook-cross-os, gate-lanes, layout-overflow, workflow-contracts,
      twin-parity) -- removed the erroneous tombstone entry (dated to the same 2026-09-09
      "safety commit" as several other findings below), leaving the file matching HEAD for
      that key; (2) the same manifest had 4 UNCLASSIFIED names (`GATE_PATHS_SCAN_FLOOR`,
      `GEN_MANIFEST_DEBUG`, `HOOK_LABEL_DIR`, `POOL_SAFETY_LOCK`) and 2 invalid entries from
      that same commit -- `ZZ_GATE_PLANT_NEVER_READ` (test-plant cruft that leaked into the
      real file, deleted, never a genuine read), and the `DEBUG` collision's `authority`
      pointing at `local-executor.ts`, which git history shows NEVER mentioned bare `DEBUG`,
      repointed at `docs/environment-variables.md:107` per the entry's own "why" text -- plus
      a stale `POOL_SAFETY_RUNNER`->`POOL_SAFETY_LOCK` rename (the code comment says the
      retarget happened 2026-09-09) and an invalid `tombstone_proof_sites` entry for
      `packages/cli/src/cli.ts`/`REDIACC_YES` (a live flag, never tombstoned, wrongly
      suppressed); `.ci/rediacc_ci/quality/python_env_registry.json`-style registry also
      needed 23 named `--allow-new` entries plus 1 drain (`POOL_SAFETY_RUNNER`), and
      `.ci/policy/worklist-env-registry.json` needed one new `WORKLIST_FOCUS` flag entry --
      `npx tsx scripts/gen-docs.ts --write` then resynced `scripts/data/doc-registry.md`'s
      generated env-manifest region; (3) `scripts/gates/check-embed-credits.ts` imported
      `../generate-embed-credits.js` (one level up), but that file had moved to
      `scripts/gen/generate-embed-credits.ts` in an earlier reorganization that updated the
      gate's OWN error-message text (`scripts/gen/...`) but missed its import statement --
      this broke the REAL gate outright (`ERR_MODULE_NOT_FOUND`), not just its test, fixed
      with a one-line import-path correction; (4) `scripts/ci-runner/lanes.ts`'s
      `quality-branch` lane grew from 4 to 5 gates at some point after both `test-gate-
      lanes.sh` (the bash twin) and its Python port hardcoded "5 shards over quality-
      branch's 4 gates must refuse" / "Ask for at most 4" -- both updated to 6-shards-over-5
      to keep testing genuine over-provisioning rather than a request the lane can now
      actually satisfy; (5) `mark-production.py`'s differential (`test_gate_mark_production
      .py`) was missing 2 real cases the bash twin gained 2026-09-10
      (`test_object_type_lookup_failure_is_a_refusal`, `test_annotated_tag_deref_failure_is_
      a_refusal`) -- ported both, extending the port's `make_gh` fake with the `object.sha`/
      `object.type` branches the twin's own fake already had; (6) `.claude/rediacc_hooks/
      tests/test_hooks_procs.py` hardcoded the GNU coreutil `timeout` as a literal subprocess
      argv0, an undeclared platform-sensitive operation per `hook_cross_os.py` -- given a
      real `REDIACC_TIMEOUT_BIN` env-override seam (Homebrew's `coreutils` package installs
      `gtimeout` on a bare macOS/BSD userland) rather than a bare Scope exemption, which
      correctly made the AST-visible finding disappear entirely (the code is now genuinely
      portable, not just declared exempt); (7) `.ci/scripts/security/check-workflow-gates.sh`
      -- `DECLARED_UNUSED_OK` was drained to empty 2026-09-08 ("W8 P1b's declared endgame"
      per its own comment) as a real, permanent migration, but 5 tests in both the bash twin
      (`test-workflow-contracts.sh`) and its Python port kept asserting against the ONE
      historical entry that used to live there -- added a genuine `WORKFLOW_GATES_EXTRA_
      EXEMPTIONS` test-only env seam (never set in production, verified the real gate still
      reports "0 declared-unused exemption(s)" unprompted) to both the checker script and
      BOTH test suites, restoring coverage of a mechanism that must still work the next time
      a secret migrates off direct passing; (8) two REAL calendar-date test fixtures had
      rotted: `test_release_check_soak_period.py`'s `EDGE_DATE` fixtures were pinned to
      absolute 2026-07/09 dates that the bash twin's `date +%s`-at-runtime arithmetic
      silently outgrew day by day, and `hookcases.py`'s "today's MMDD allowed" case hardcoded
      `0909` from whenever it was written -- both rewritten to compute the fixture relative
      to `datetime.now()` at test-run time, matching the twin's own runtime-relative
      arithmetic instead of racing it; (9) `rediacc_ci.quality.release_state.assert_bijection`
      emitted a real em-dash where its bash twin (`.ci/scripts/lib/release-state-validator.sh:361`) emits
      literal `--`, a byte-level port/twin divergence caught by the differential --
      corrected to `--`, then `npx tsx scripts/gates/check-em-dash-surfaces.ts --write-
      baseline` drained the one baselined finding the fix retired (the file's OTHER two real
      em-dashes at `:587`/`:594` genuinely match the twin and stay); (10)
      `rediacc_ci.release.validate_stage_artifacts` was the only file in the whole `release/`
      package with a hand-written `sys.path.insert(0, os.path.join(..., "..", "..", ".."))`
      -- every sibling relies on the differential's own `PYTHONPATH=.ci`, and this port's own
      docstring already says repo-root comes from `paths.repo_root()`, "not a manual `../../
      ..` climb" -- deleted the dead hop, matching every sibling. Two more registry
      findings the same run surfaced: `verify_release_assets.py` had a stale `MANUAL_ENTRY_
      POINTS` exemption in `dead_python.py` that a real "mentioned" route had since made
      false (removed), while `ci_signal/create_complete.py`, `quality/announce_gate_skips
      .py`, `quality/run_external_gate.py` and `release/assert_artifact_version.py` -- named
      as "not mine" in essentially every wave's gate output this whole campaign -- were
      simply MISSING the same by-name exemption their sibling module-string-invoked ports
      already carry; added all 4. One more, purely cosmetic, self-inflicted: `test_blocker_implementations.py`'s own docstring illustrated
      quote-boundary matching using 5 REAL entries from the phrase table it scans for,
      pushing the file's own self-detected count to exactly `TABLE_THRESHOLD` (10) and
      tripping its own anti-duplication check -- reworded to illustrative non-table words
      (`"cat"`/`"category"`, `"an"`), dropping the count to 5. Also applied `shfmt -w` across
      `.ci/**`, `.claude/**`, `./run.sh`, `scripts/dev/**` and `scripts/docker/**`, fixing
      genuine pre-existing `for ((i=1; ...))`-style spacing drift (`.ci/lib/account.sh` and
      ~14 tutorial/test scripts) that was failing `test_gate_vacuity_floors.py`'s real-corpus
      control. Every fix here was verified against the REAL gate script or REAL twin
      directly, not only its test port, and the `.ci/scripts/build/**` twins themselves were
      confirmed byte-untouched throughout.
      **FIFTY-THIRD WAVE 2026-09-14, THE LAST FILE IN THE ENTIRE "142 UNNAMED FILES" BUCKET.**
      `browser-smoke.sh` (57L) -> `quality/browser_smoke.py`. Driver-verified directly: 21
      tests independently re-run, exit 0; `w7p6-browser-smoke` ledger K=5 over 5 distinct
      trees; twin byte-untouched; both files compile; `check:ci-python-lint`/`ruff format
      --check`/em-dash grep/scoped `check:ci-dead-python` all clean; modes 755/644 as
      expected. Headline defect independently reproduced by the driver with a real PATH
      holding only `dirname`/fake `node`/fake `docker`, `id` genuinely absent: two `line 50:
      id: command not found` lines, `-u :` with both ids empty, `exit=0`. The writer also
      drove BOTH sides against the real gate in a real Chromium container (twice: the
      `REDIACC_SMOKE_NO_DOCKER=1` escape hatch AND the full docker-pull path), byte-identical
      stdout and stderr both times -- the strongest confirmation any single wave has produced
      this session, going beyond the differential into the genuine external tool.
      **Real defects found, reproduced not fixed:** (1) `:51`'s `-u "$(id -u):$(id -g)"` is a
      failed command substitution inside an argument list that `set -euo pipefail` cannot
      abort on, silently handing docker `-u :` at exit 0 -- driver-reproduced above, the
      TENTH confirmed "unanswerable folded into a clean pass" this session, and the reason
      the port shells out to real `id` rather than `os.getuid()` (which cannot fail, and so
      would be a strictly different, unfalsifiable program on this exact path); (2) `:4`'s
      `# needs: node` under-declares its own real dependencies (also `docker`, `id`),
      documentation-only in consequence since `python-yaml` is the only capability with an
      acquire recipe. Two sibling divergences from `page-density.sh` (mount path, `-e
      CI=true`) pinned as behavior with dedicated tests, not defects.
      **A control that did not fire on first attempt, and the control was wrong**: removing
      only the port's own import left the dead-python gate quiet, because `dead_python
      .mentioned_paths` also credits a route to any file whose BASENAME appears as text
      anywhere reached -- and the differential's own `PORT` constant contains the literal
      string `"browser_smoke.py"`. Fixed by removing both the import and the literal
      together; the test file was restored byte-identical afterward (`diff` clean).
      `.ci/scripts/quality/**`, and with it every named file in the W7P6 "142 unnamed files"
      survey, is now FULLY PORTED. `python-env-registry` will owe `--write-baseline --allow-
      new .ci/rediacc_ci/quality/browser_smoke.py:REDIACC_SMOKE_NO_DOCKER` at commit time
      (the gate scans tracked files only, so it is silent on this and every other untracked
      port in this cohort until then -- registering now would read the entry as newly STALE).
      **DRIVER FIX 2026-09-14, a gap the driver's own earlier fix left behind.** A fresh full
      `check:ci-pytest` run after wave 53 showed 11 failures, not zero. Investigated per rule
      3 rather than assumed environmental: 6 of the 11 (2 each in `test_quality_env_manifest
      .py`, `test_gate_python_env_registry.py`, `test_gate_worklist_env_registry.py`) traced
      to `REDIACC_TIMEOUT_BIN` -- the env-override seam this driver added to `test_hooks_procs
      .py` earlier today (item 6 of the DRIVER FIX above) -- never having been registered in
      `python-env-registry.json` or `env-manifest.json`, the same class of gap fixed for 23
      OTHER names earlier in this session, just missed for this one because it was added
      AFTER that sweep. Registered in both (harness shard, alongside `HOOK_LABEL_DIR` from
      the same test-file family), `gen-docs.ts --write` re-synced the doc region, all 32
      tests across the three files re-verified green. The remaining 5 (2x `test_deploy_
      simulate_promotion.py`, 1x `test_deploy_promote_r2_to_stable_hotfix.py`, 1x
      `test_housekeeping_cleanup_versions.py`, 1x `test_gate_hook_cross_os.py`) all passed
      cleanly re-run in isolation (50, 121 and 5 tests respectively) -- xdist contention
      under the full 15919-test parallel run, not a correctness defect; `test_gate_hook_cross
      _os.py`'s own module docstring already documents this exact flake class for a sibling
      case. A further full-suite run was kicked off to confirm zero failures end to end.
      **That further run confirmed the class, not a fix: 8 failed, DIFFERENT specific test
      IDs within the SAME five files** (`test_deploy_simulate_promotion.py`, `test_deploy_
      promote_r2_to_stable_hotfix.py`, `test_gate_hook_cross_os.py`, `test_gate_worklist_env_
      registry.py`, `test_housekeeping_cleanup_versions.py`) -- driver re-ran all five
      together in isolation a second time: 183 passed, 0 failed. Two consecutive full runs
      naming a different specific test each time inside a fixed small file set, both clean
      in isolation, is resource contention under 15919-test parallelism, not a correctness
      defect this campaign introduced or needs to chase further -- `test_gate_hook_cross_os
      .py` already carried this exact class as documented, known behavior for a sibling case
      before this session touched it. W7P6's own scope (porting, not this suite's
      parallel-execution ceiling) is satisfied: every file this box named is ported,
      differentially tested, K=5-ledgered, and passes on its own merits.
      **BOX CLOSED 2026-09-14, waves 1-53.** All 37 originally-unstaffed free files (plus
      every file discovered mid-box in `deploy/`, `release/`, `docker/`, `security/`, `ci/`,
      `setup/`, `env/`, `review/`, `private/` and `build/`) are ported, bar the explicit
      non-targets already named above (`git-fixture.sh`, `mutate-check.sh`, sourced-only
      libs) and two profiler files (`sampler-linux.sh`, `panel.sh`) confirmed out of scope
      earlier in the box. `browser-smoke.sh` (wave 53) was the last file in the whole "142
      unnamed files" survey. Cutover (registering the Python side as the live gate, deleting
      the bash twin) is explicitly NOT this box's job -- see W7P4-Q/W7P4-W/W7P5-a/b/c/W1P6's
      own sequence below, unstarted and untouched by this box on purpose.
- [x] **W1P4 C, after PRE-A1** The full `sys.path` sweep. **DONE 2026-09-09, and the box's
      number was wrong in both MAGNITUDE and DIRECTION: 36 files / 39 hops, not "68 and
      rising", and HEAD `aaba93b29` carries 45 -- so it FELL.** That commit removed nothing:
      81 files changed, 9268 insertions, **0 deletions**, all new shims already on `_cipath`.
      The deliverable is `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py`, which already
      existed and **governed 2 of the 39 hops** -- a control scoped to exactly the ground its
      own workstream had already cleared. Widened to the whole tree; it rides
      `check:ci-pytest`, so there is no wiring patch. The set is printed BY NAME and keyed on
      `sha1(ast.unparse(call))[:12]`, so an entry survives a MOVE and deliberately re-keys on
      a REWRITE; shrink-only in BOTH directions.
      **The old floor was `assert len(files) > 50`, a typed constant -- the finish-line trap
      itself.** The floor is now the known-positive set: every exempt-or-baselined path must
      still be FOUND carrying a hop.
      **THE FIRST PLANT DID NOT FIRE AND THE CONTROL WAS AT FAULT.** The corpus was
      `gitx.ls_files("*.py")` without `untracked=True`, and a new file is untracked by
      definition, so the plant sat in the one file the scan could not see. `gitx.ls_files`'s
      own docstring records the identical defect in `.ci/scripts/quality/check-python-lint.sh:88`. Fixing it moved
      the corpus 567 -> 655 and surfaced **3 hops added AFTER PRE-A1**, invisible to any
      committed enumeration: `.ci/rediacc_ci/tests/test_wl_proc.py:43`,
      `.ci/rediacc_ci/tests/test_worklist_state_stdin.py:42` and
      `.claude/hooks/stop/wl_proc.py:35` -- two of them a hand-rolled re-implementation of
      `on_sys_path` in a file that already imports `paths`. They are a concurrent writer's
      uncommitted work, so they are baselined as FRESH and printed every run rather than
      folded into 33 lines of old debt.
      **NOTHING FURTHER IS REDUCIBLE, measured not assumed:** six hops are in files that are
      a module AND a script, and `import _cipath` raises `ModuleNotFoundError` when such a
      file is imported by package name -- driven on a throwaway package, where
      `python3 pkg/sub/dualuse.py` loads and `from pkg.sub import dualuse` dies.
- [ ] **W1P6 S, terminal** Delete `.ci/config/language-policy-baseline.json`. `read_baseline`
      returning `None` IS strict mode (`:478`, `:788`) -- the flip is a file deletion and no code
      change. **Acceptance:** the gate exits 0 printing `language policy STRICT: N bash file(s)
      ... all M allowlisted`, N == M.
      **MEASURED 2026-09-20:** `check_language_policy.py` reads 583 bash files under `.ci` and `.claude`, 508
      frozen in the baseline (shrink-only, none added) and 75 exempt by name across 14 allowlist entries. The
      box cannot move until those 508 are ported or allowlisted, and deleting the baseline before then reds the
      gate, so it stays terminal and blocked by the port chain (W7P4-Q, W7P5-a/b/c). A new tracked `.sh` also
      counts against it: a session added one this week and the gate refused it, so new bash cases belong in an
      existing file.

---

## T-SCHED

- [x] **A1 S** `GateSpec.env` **and** a `when` conjunct field, at both ends of the pipe
      (`gate-spec.ts`, `gate-header.ts`, `gate-bind.ts`, `gen-gates-lock.ts`, ~120 lines).
      `when` ANDs onto the standard guard, never replaces it -- a field that could replace it
      re-opens invariant 11 through a side door.
      **Acceptance:** set equality over the 26 `(job, step, env-key, env-value)` tuples before and
      after, computed by the same parser on both sides; `if:` multiset byte-identical; three
      representations (header, lock, emitted) agree. Controls: an `env` value referencing a secret
      not in the workflow's `secrets:` block is REFUSED; a `when` conjunct containing `steps.` is
      REFUSED.
      **DONE 2026-09-08. Acceptance met, and TWO of this box's own premises were wrong.**
      *(a)* Two of the four files it names do not exist: there is no `scripts/lib/gate-spec.ts`
      (it is `scripts/ci-runner/gate-spec.ts`) and no `scripts/ci-runner/gen-gates-lock.ts`
      (it is `scripts/gen-gates-lock.ts`). *(b)* The tuple count is **24**, not 26, measured
      by the acceptance parser over every registered gate step.
      **The pipe is three files, not four**, because `gen-gates-lock.ts:render` serialises the
      whole `GateSpec` — adding the fields to the type carries them into the lock with no code
      change there, which is why they went in the type rather than in a second serialiser.
      **Grammar:** `env-<KEY>: <value>`, one key per line. NOT a comma list: the values are
      GitHub expressions like `${{ github.event.pull_request.number }}`, and splitting a
      comma list correctly would mean knowing when a comma sits inside `${{ }}`.
      `ENV_FIELD` is a separate uppercase-only regex, so the existing lowercase `FIELD`
      grammar is untouched and a lowercase `env-foo:` is simply not an env line.
      **`when` is parenthesised when emitted**, and that is not cosmetic: `a && b || c`
      parses as `(a && b) || c`, so an unparenthesised `when` containing `||` would bind
      looser than the guard and run the step on a FAILED setup — the exact invariant-11
      side door the box warns about. `steps.` inside a `when` is refused outright.
      **Acceptance, by the same parser on both sides:** 705 `(job, step, env-key, env-value)`
      tuples identical before and after, `if:` multiset identical (66 distinct lines, 385
      occurrences). The plumbing is deliberately INERT on landing — no gate declares `env`
      yet — which is exactly why those two sets had to be byte-identical.
      **Controls:** 7 on the header (env parsed; `when` parsed; `steps.` refused; empty env
      value refused, because an empty value SETS the variable to `""` rather than leaving it
      unset; empty `when` refused; a lowercase key is not an env line; no env stays absent)
      and 5 on the emitter (env sorted and placed between guard and run; no env emits no
      `env:` key at all; `when` ANDed with the guard surviving verbatim; a `||` `when`
      parenthesised; and no `when` leaves the guard byte-identical to pre-A1).
      `check:ci-gate-bind`, `check:ci-parity`, `check:ci-gate-manifest`, `check:ci-gates-lock`
      all rc=0; gate-bind selftest 0 failures.
      **A REAL-TREE PLANT CAUGHT THIS BOX HALF-DONE AFTER ALL TWELVE CONTROLS PASSED,**
      and the correction is the most useful thing in this entry. `emitStep` handled `env`
      and `when` correctly and `Bound` declared both fields -- but NOTHING COPIED THEM
      ACROSS from the parsed header, so a gate declaring `env-PROBE_TOKEN` bound to a step
      with no env and `gate-bind --dry-run` reported `already matches`. Every control
      passed because every control called `emitStep` directly, which is precisely what
      `.claude/agents/gate-author.md` warns about: "not in the selftest alone, which only
      proves your helper functions work, but ON THE REAL TREE, in the real invocation".
      Fixed by carrying `h.env`/`h.when` into `Bound`, then PROVEN on the real tree:
      planting both on `check_agent_browser_exit.py` and running the real binder emits
      `if: ${{ !cancelled() && steps.setup.outcome == 'success' && (github.event_name ==
      'pull_request') }}` with `env: PROBE_TOKEN: ${{ github.token }}` beneath it. Plant
      removed, tree restored byte-identical, binder back to `already matches`, and the
      acceptance sets re-measured identical to the pre-A1 snapshot.
      `check:ci-gate-reachability-coverage` rc=0 as well -- the second meta-gate that
      specialist names, which the first pass had not run.
- [x] **A2 S, cheapest high-value box in the programme** The strip guard. `--write` refuses when
      `dropped` is non-empty **for any reason**, with `--allow-drop <step>` as the one typed
      escape. Plus a new gate, id check-ci-step-env-parity (this box creates it), asserting each step's `env:` map equals
      `lock[id].env ?? {}`, both directions.
      **Red proof available today:** strip `DOCKERHUB_TOKEN` from `.github/workflows/ci-quality.yml:1159` in a
      scratch copy and run the whole battery -- nothing reds. That is the receipt.
      **HALF LANDED 2026-09-08: the strip guard is IN and proven; the env-parity gate is not.**
      `scripts/gate-bind.ts` now refuses `--write` on ANY drop the rewrite cannot re-emit,
      not merely one the manifest still names, with `--allow-drop <step>` as the single
      typed escape. The predicate was EXTRACTED as `classifyDrops()` so a control can drive
      it -- a refusal living inline in `main` is one nobody has ever watched fire. Six
      controls, and they are not vacuous: mutating `classifyDrops` to return an empty list
      fails THREE of them. Selftest 0 failures, `check:ci-gate-bind` rc=0.
      **The env half is MEASURED and deferred to a writer.** 17 registered steps carry
      `env:` in `ci-quality.yml` and ZERO lock entries carry one, so the parity assertion
      reds 17 times today. The line the box cites has drifted -- `:1159` is now the
      `# <<< gate-bind` marker -- but the receipt holds: `DOCKERHUB_TOKEN` on
      `check:ci-docker-image-freshness` is one of the 17. The env content is a closed set of
      GitHub context expressions (`GITHUB_TOKEN`, `EXTERNAL_QUALITY_MODE`, `PR_NUMBER`,
      `GITHUB_BASE_REF`, `GH_TOKEN`, `PR_HEAD_REF`, `DOCKERHUB_TOKEN`, six others), so the
      cure is mechanical: `ci.env` beside `ci.step` in the lock, which is already the
      workflow-derived block, then the both-directions gate. **0 env blocks sit inside a
      gate-bind region today**, which is why nothing has been stripped yet and why the
      guard above is the urgent half.
      **THE ENV HALF LANDED 2026-09-08 TOO, so this box is now COMPLETE.**
      `scripts/gates/check-ci-step-env-parity.ts` is registered and rc=0: 251 registered steps
      (251 resolved) across 2 workflows, 28 `env:` blocks parsed, 17 registered steps
      carrying env, 24 env keys declared in the lock. It landed RED with those same 24 as
      `workflow-only` findings and I DRAINED them rather than baselining: 17 manifest
      entries gained an `env` field, `gen:gates-lock` carried them into the lock, and the
      gate went green. No `accepted` entry was added for any of the 24.
      **A GAP IN A1 THAT THIS GATE EXPOSED.** `bind()` carries `h.env` into `Bound` and
      `emitStep` writes it, so header -> workflow is closed -- but `Registered`
      (`scripts/gate-bind.ts:580`) holds only `file, step, job, run, why`, and
      `gen-gates-lock.ts` projects the MANIFEST, not the headers. So the lock could never
      learn env from a header, and `check:ci-docker-image-freshness` was emitted WITH
      `DOCKERHUB_TOKEN` and recorded in the lock WITHOUT it, silently. The chain now closes
      by COMPOSITION: `check:ci-gate-bind` pins header -> workflow for emitted steps, this
      gate pins workflow -> lock. The residue is gates with `emit: false` or in a setup-less
      lane, where a header `env-` line is verified against nothing -- for those the manifest
      `env` is the only gated source and a header `env-` line should NOT be added.
      **Two duplication shapes were my own fallout and both are resolved.** Adding a 640-line
      gate to the `scripts/check-*.ts` family produced a new shape, three copies of the
      wrapped-report tail; I collapsed my file's three `console.error` calls into one, which
      changes delivery and not the message. Its fingerprint is recorded in the comment at
      `scripts/gates/check-ci-step-env-parity.ts:447` rather than here, because the shape is FIXED
      and a retired fingerprint resolves against nothing -- `check:ci-plan-citations` judges
      any 9+ hex token as a git object and was right to refuse it. Running the house formatter (biome, NOT prettier
      -- `check:format` is `biome format .`) over `scripts/gates/check-control-in-string.ts`, which I had
      committed unformatted in `aaba93b29`, UNMASKED `aea2bc733552`, a pre-existing tail
      shared by three unrelated gates; accepted with a BLOCKER naming the divergence, because
      the gate itself says collapsing three specific claims into one generic line makes a red
      harder to read.
- [x] **A3 S** Retire the six `env`/`if` hold-outs. The 21 setup-ordering hold-outs stay held out
      permanently and correctly; assert their set is unchanged so this box cannot emit one.
      **DONE 2026-09-08, and the honest answer is ONE retired, FIVE reclassified.** The six
      are exactly `check-actions.ts`, `check-dkim-notify.ts`, `check-docker-image-freshness.ts`,
      `check-external-links.ts`, `check-pr-epic-block.ts`, `check-pr-task-trailers.ts` -- the
      count is right. But only ONE of them was held out by env alone.
      **RETIRED:** `check-docker-image-freshness.ts`. Its own blocker said "keep the
      hand-written step until the binder learns `env:`, then delete this line and the
      hand-written copy in the same change", which is precisely what A1 enabled. Header now
      declares `env-DOCKERHUB_TOKEN: ${{ env.BWS_DOCKERHUB_TOKEN }}`; `gate-bind --write`
      emitted it; the emitted copy came out BYTE-IDENTICAL to the hand-written one, which is
      the proof the emission is faithful; the duplicate was deleted. Acceptance re-measured
      after: 705 env tuples and the 66/385 `if:` multiset both UNCHANGED, so a retirement
      moved a step from hand-written to emitted and changed no CI behaviour at all.
      **THE OTHER FIVE HAD A DIFFERENT REAL BLOCKER, and their BLOCKER line said otherwise.**
      Three (`check-actions`, `check-dkim-notify`, `check-external-links`) run through the
      `.ci/scripts/quality/run-external-gate.sh` WRAPPER, which the derived run does not
      produce. Two (`check-pr-epic-block`, `check-pr-task-trailers`) have NO `if:` at all --
      they run unconditionally -- so emitting them would ADD the standard guard and change
      WHEN the gate runs. Four of the five also carry PROSE comments inside their `env:`
      block, which the `env-<KEY>:` grammar cannot hold. All five blockers were CORRECTED
      rather than deleted: a BLOCKER whose stated reason has quietly expired is the exact
      shape `check:ci-suppression-liveness` exists to refuse, and leaving "gate-bind cannot
      emit an env block" in place after A1 would have held these out forever on a dead
      reason. Retiring them is a behaviour change and needs its own box.
      **The 21 setup-ordering hold-outs:** the classifier finds NINE, not 21. Recorded as
      drift rather than chased; they stay held out either way, and the box's own assertion
      is that their set is unchanged, which it is.
      `check:ci-gate-bind`, `check:ci-parity`, `check:ci-gate-manifest`,
      `check:ci-suppression-liveness` and `check:ci-knip-blockers` all rc=0.
- [x] **B1 S** `shardPlan(lock, laneCaps, shards)` in `scripts/ci-runner/lanes.ts`, pure, writes
      nothing. `lanes.ts` already derives `{job, runsOn, timeoutMinutes, submodules, node, tools}`
      per lane -- the matrix's literal runners and timeouts come from there; nothing new parses
      YAML. Rules: a `mutex` group never splits; `heavy` at most one per shard; balance on
      `weight`, tiebreak on `slow`. **Acceptance:** union equals the lane's gate set, shards
      pairwise disjoint, none empty; **more shards than gates must REFUSE**, not emit an empty
      shard that reports green having run nothing.
      **DONE 2026-09-09.** `shardPlan` at `scripts/ci-runner/lanes.ts:408`, 22 controls in the
      registered twin and 22 matched in its port; 394 plans verified over the REAL lock at
      every shard count from 1 to entries+2, plus 63 refusals. Lock is **465/455/95/46**, not
      the box's 458/448/95/45.
      **THE BOX NAMES THREE RULES AND THE TREE HAS A FOURTH:** twelve `quality-www-build`
      entries declare `needs: [build:www]`, a step in that same lane, so within-lane `needs`
      is a co-location constraint. Honouring only mutex/heavy/weight would put a gate in a
      runner that never built what it validates. That is why www-build's 16 entries are 4
      units. Cross-lane needs are not co-location: `build:packages` is `local-only`.
      **A REFUSAL THE WRITER LANDED WAS WRONG AND I CORRECTED IT RATHER THAN ACCEPTING IT.**
      It refused `quality-go` at EVERY shard count because the `account-vitest` mutex group
      holds two heavy gates. But `scripts/ci-runner/gate-spec.ts:44` defines mutex as "no two
      gates sharing a group overlap" and `heavy` bounds CONCURRENT heap, so two heavies that
      can never run together peak at ONE. Refusing was refusing arithmetic, and it made a
      real lane unshardable for no reason. Heavy is now counted as concurrent; a unit merged
      by within-lane `needs` is the opposite case, both really resident, and still refuses.
      **MY OWN FIX HAD A BUG AND MY OWN ANTI-SILENCER CAUGHT IT:** I recorded
      `merge.find(e.id)` at union time, but union-find roots MOVE as later unions land, so
      the needs-merged unit slipped past the refusal. Roots are now resolved once, after
      every union. The control then failed a SECOND time for a different reason -- a
      synthetic lane name is refused before the heavy rule is ever reached -- which is the
      control being right twice. Twin 37 PASS, port 37 passed, both agreeing.
- [x] **B2 S, driver-only, long pole** Emit the matrix. **Invariant 11 is handled by construction:**
    (ticked) 2026-09-20T15:45:13Z by d778be9d: emitted for quality-code x4 (0e92e992d); local gates green, first CI run pending the operator's push
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
      **DESIGN 2026-09-08: the invariant-11 MECHANISM is real and I verified every clause --
      `laneCanEmit` at `scripts/gate-bind.ts:302-309`, the two setup-less lanes, the "7 steps
      total" -- but THE CONCLUSION DOES NOT HOLD AS STATED, in three ways.**
      **(a)** `laneCanEmit()` is true for EIGHT lanes and only SIX hold a region;
      `quality-packages` (14 entries) and `quality-go` (16) are setup-ful and entirely
      hand-written. Generate the include list from "has a region", not from `laneCanEmit()`.
      **(b) A real `strategy.matrix` DESTROYS THE JOB KEY, and three tools resolve on it:**
      `scripts/ci-runner/lanes.ts:25-36` LANE_ORDER refuses a lane whose job is missing, `laneCanEmit(wf,
      'quality-static')` would return false and make gate-bind refuse every region -- so
      invariant 11 fires against every sharded lane, which is precisely what the box says is
      handled by construction. The intended shape must be sharding WITHIN a lane, keeping the
      YAML key; say so explicitly, because "emit the matrix" reads as the other thing.
      **(c)** Under within-lane sharding every gate runs N times unless each step carries a
      shard conjunct. A1 landed `when`, but it is HEADER-declared, so this needs gate-bind to
      write a DRIVER-COMPUTED `when` -- a `gate-bind.ts` change, not "by construction".
      **B2 therefore joins the `gate-spec.ts`/`gate-header.ts`/`gate-bind.ts` serial chain
      (A1 -> A2 -> C2) and cannot run concurrently with C2.** Add it to the collision map.
      Lock numbers are 465/455/95/46, not 458/448/95/45.
      **STARTED 2026-09-09. THE DESIGN NOTE'S CLAUSE (b) IS REFUTED BY MEASUREMENT, and it
      is the clause the whole shape of this box rested on.**
      (b) says "a real `strategy.matrix` DESTROYS THE JOB KEY, and three tools resolve on
      it", naming `LANE_ORDER`, `laneCanEmit` and gate-bind's regions, and concludes the
      matrix must therefore be sharding WITHIN a lane rather than a real matrix. **All
      three survive.** Inserting a real `strategy: fail-fast: false / matrix: shard: [1, 2]`
      into `quality-static` and re-running the actual functions:
      `laneCapabilities` still returns all TEN lanes including `quality-static`;
      `laneCanEmit(wf, 'quality-static')` is `true` before and after; `regionAfterSetup` is
      `true` before and after. The reason is structural: `scripts/gate-bind.ts:302-308`
      finds a job by a TWO-space key and scans to the next two-space key, and a `strategy:`
      block sits at four, so the scan window is unchanged and `- id: setup` is still inside
      it. `LANE_ORDER`'s refusal at `scripts/ci-runner/lanes.ts:178` keys off
      `caps.has(job)`, which is still true.
      **What that changes:** a real matrix is available, and the box's conclusion that B2
      "joins the serial chain and cannot run concurrently with C2" rests on a false premise.
      **It is still probably serial with C2, but for clause (c)'s reason and not (b)'s** --
      (c) is correct that every gate would run N times unless each step carries a shard
      conjunct, and that needs gate-bind to write a DRIVER-COMPUTED `when`, which is a
      `scripts/gate-bind.ts` change and does collide with C2.
      **Clause (a) is confirmed exactly:** `laneCanEmit` is true for EIGHT lanes
      (`grep -cE '^\s+- id: setup'` = 8) and only SIX hold a region
      (`grep -c '# >>> gate-bind'` = 6), so the include list must be generated from "has a
      region", never from `laneCanEmit()`.
      **Real plans computed against the live lock, so feasibility is measured not assumed**
      (477 entries, not the 465 this box records -- the lock moved three times today):
      `quality-security` 166 entries / 162 units, x4 gives 37/43/43/43 gates at weight
      44/43/43/43 and zero heavy; `quality-static` 53 entries / 53 units, x2 gives 27/26 on
      `ubuntu-slim` at timeout 12, inside the `<= 14` CHECK 3 cap; `quality-code` 99 entries
      / 98 units needs x8 because it holds 8 heavy gates, and **x3 REFUSES with exactly the
      right message** -- "8 heavy gate(s) but only 3 shard(s) ... Ask for at least 8".
      Refusal 5 is live and correct.
      **A correction to my own probe rather than to the code:** my first pass read
      `plan.shards` and printed "0 shard(s)" for two lanes, which reads exactly like the
      empty-shard failure this box exists to prevent. The real path is `plan.lanes[].shards`
      (`scripts/ci-runner/lanes.ts:253-255`). B1's work is sound; the probe was wrong.
      **STEP 1 DONE, THEN DELIBERATELY BACKED OUT, because it would have made CI SLOWER.**
      `SHARD_COUNTS` was populated with `quality-security: 4` on the strength of that lane
      holding 166 of the lock's 477 entries -- the largest by a wide margin -- and the
      matrix and aggregator were emitted. `check:ci-quality-complete` went rc=1 with exactly
      one finding, `aggregator job absent`, then rc=0 once the job landed: **the
      both-directions pin is live and I saw both halves of it fire.**
      **Then the conjuncts landed and there were only FOURTEEN.** LOCK ENTRIES ARE NOT
      WORKFLOW STEPS, and the ranking inverts completely. Measured on the real workflow:
      `quality-code` **98** steps, `quality-static` 60, `quality-content` 42, `quality-go`
      22, and **`quality-security` NINETEEN** -- fifth, not first. 149 of its 166 entries
      are the gate-test battery, which is ONE hand-written step, and gate-bind can only
      conjunct the 13 inside its emitted region. Six steps would have carried no conjunct,
      four of them real work including `Quality-gate unit tests`, **so the most expensive
      step in the lane would have run on all four legs**. A matrix that multiplies the
      dominant step is slower than no matrix.
      Backed out: `SHARD_COUNTS` is empty again, the matrix and the aggregator are gone,
      `gate-bind --write` re-run to zero conjuncts, and
      `check:ci-quality-complete`/`gate-bind`/`parity`/`gates-lock` are all rc=0.
      **THE MECHANISM IS BUILT AND STAYS**, inert until a lane is named:
      `shardAssignment` in `scripts/gate-bind.ts` computes each gate's leg from
      `SHARD_COUNTS` through the same `shardPlan` the aggregator re-runs, and
      `rewriteRegions` ANDs `matrix.shard == N` onto any header `when`, parenthesising the
      header half so a `||` cannot bind loose. A driver-computed conjunct is the only
      correct kind: a hand-written `matrix.shard == 3` goes stale the moment any OTHER gate
      is added to the lane, and stale in the silent direction -- the gate stops running on
      a leg that still reports green.
      **What B2 still owes: the `quality-code` decision.** It is the real target (98 steps,
      99 entries, so nearly every entry is its own step) and it holds 8 `heavy` gates, so
      `shardPlan` refuses anything under x8.
      **THAT MEASUREMENT IS NOW TAKEN, 2026-09-09, and it inverts the trade this box
      assumes.** From `.ci/cache/gate-durations.json`, floor-of-recent per gate as
      `scripts/gates/check-gate-manifest.ts:527` requires: `quality-code` sums to **1724 s of
      serial gate work** across 91 of its 99 entries (8 carry no recorded duration).
      The lane does not run that serially -- `scripts/ci-runner/run.ts:941` sets
      `jobs = os.availableParallelism() - 2`, so on a standard 4-vCPU `ubuntu-latest` the
      in-job pool is **two slots wide**. 1724 / 2 = **862 s = 14.4 min against a
      `timeout-minutes: 15` budget, which is 96% OF THE CAP.**
      **So the constraint is not "eight setups are wasteful". It is that the lane sits one
      bad week from timing out and the in-job pool CANNOT widen**, being bounded by the
      runner's cores -- and `ubuntu-slim`, the cheaper runner, is smaller still. Adding
      runners is the only lever left, which is what a matrix is.
      At x8 each shard carries ~215 s of serial work, ~108 s at two slots, plus one setup.
      The trade, stated so it can be argued with: **wall clock 14.4 min -> under 3 min, at
      roughly 8 x (1.8 min + setup) runner-minutes against today's 1 x 14.4.**
      **The setup step's own cost is the remaining unknown and it is the whole question**,
      because it is paid eight times. It must come from a real CI run: `git status
      --porcelain` is 350+ lines in this checkout and B5 already ruled that nothing timed
      here is admissible.
      **Why `quality-security` differed, which is the transferable part:** 19 steps whose
      dominant cost is ONE hand-written battery step cannot be divided by a step-level
      split, while `quality-code`'s 98 steps divide almost perfectly. Shardability is a
      property of how the cost is DISTRIBUTED, not of how many lock entries a lane holds.
      **Remaining for B2:** populate `SHARD_COUNTS` (empty today at
      `scripts/ci-runner/lanes.ts:370`, deliberately, because `check:ci-quality-complete`
      pins the workflow to it in both directions), emit the matrix, teach gate-bind the
      driver-computed `when`, and add the aggregator job. `LaneShards` at `:241` is
      currently unexported with a comment naming B2 as the change that may export it.
      **WAVE 2026-09-14, READ-ONLY (isolated worktree; the primary tree is owned by a
      pr-babysit agent, so nothing here was implemented). CLAUSE (c) IS CORRECT AS A
      REQUIREMENT AND IS ALREADY DISCHARGED IN CODE. The `Remaining for B2` line above is
      now the stale part.** The driver-computed `when` this box asks for EXISTS:
      `shardAssignment` at scripts/gate-bind.ts:459 plans the lane through the same
      `shardPlan` (scripts/ci-runner/lanes.ts:431) that `check:ci-quality-complete` re-runs,
      the `--write` path builds the per-lane map at scripts/gate-bind.ts:1787, and
      scripts/gate-bind.ts:624 ANDs `matrix.shard == N` onto any header `when` with the
      header half parenthesised. Nothing in A1, A2 or C1 supersedes or duplicates it.
      A1's field is still header-only at scripts/lib/gate-header.ts:103 and
      scripts/ci-runner/gate-spec.ts:84, and ZERO lock entries declare a `when` today, so the
      conjunct's "header `when` present" branch has never had a real input.
      What B2 still owes is therefore NOT "teach gate-bind the driver-computed `when`". It is
      the five pieces below, three of which this box has never named.
      **NUMBERS RE-DERIVED AGAINST TODAY'S TREE, and two of the four moved again.** The lock
      is **483 / 473 / 95 / 46** (entries / `gate: true` / slow / paths-declaring) in the
      working tree and 481/471/95/46 at the branch tip, against the 465/455/95/46 recorded
      above and the 477 recorded below. Slow and paths are the two that held. Per-lane lock
      entries: `quality-security` 166, `quality-code` **100** (was 99), `quality-static` 58,
      `quality-content` 42, `quality-i18n` 40, `quality-www-build` 16, `quality-go` 16,
      `quality-packages` 14, `quality-branch` 5, `build-renet` 1, plus 13 `test` and 12
      `local-only`. Workflow steps per lane: `quality-code` **99** (was 98), `quality-static`
      **65** (was 60), `quality-content` 42, `quality-go` 22, `quality-security` 19,
      `quality-packages` 18, `quality-i18n` 15, `quality-www-build` 13. The step ranking's
      SHAPE is unchanged, so the conclusion drawn from it survives; the figures do not.
      **FINDING 1, AND IT BLOCKS ANY POPULATION OF `SHARD_COUNTS`: THE PLAN IS OVER LOCK IDS,
      THE WORKFLOW RUNS STEPS, AND THE TWO ARE NOT THE SAME SET.** `shardPlan` shards every
      lock entry whose `ci.job` is the lane (scripts/ci-runner/lanes.ts:485 builds its units
      from exactly that set), while `rewriteRegions` can only attach a conjunct to a step it
      emits inside the region. Measured on the real tree, three distinct ways that diverges:
      (i) **Many ids share ONE step.** `quality-code` has 100 entries and 99 steps because
      `check:lint`, `check:lint:cli`, `check:lint:web`, `check:lint:tooling` and
      `check:lint:account` all carry `ci.step: Lint` (.github/workflows/ci-quality.yml:896,
      one `run:` of four npm scripts chained with `&&`). `quality-content` has the same shape
      on `Dead CSS` (3 ids), `quality-security` on `Quality-gate unit tests` (149 ids). A step
      can hold ONE `if:`, so a plan that puts `check:lint` on leg 1 and `check:lint:cli` on
      leg 3 is unrealisable: four of the five silently ride leg 1, and
      scripts/gate-bind.ts:624 cannot notice, because it looks the leg up by the emitting
      gate's id alone.
      (ii) **33 of `quality-code`'s 100 entries have no step inside the region** (the region
      is .github/workflows/ci-quality.yml:791 to :989). They get a leg from the plan and no
      conjunct in the file, so they run on EVERY leg while the plan believes they ran once.
      (iii) **The heavy refusal is computed in the wrong currency.** `quality-code`'s "8 heavy
      gates, so nothing under x8" is 8 heavy IDS: `check:lint` five times (all ONE step),
      `lint:unused`, `check:types` and `check:ci-account-layer-isolation`. That is FOUR heavy
      steps, and two of the four (`check:types`, `check:ci-account-layer-isolation`) sit
      outside the region and are not shardable at all. Counted as the workflow runs them, the
      conjunctable heavy count is **2**, so the minimum viable shard count for `quality-code`
      is 2, not 8. The x8 floor this box has been reasoning against is an artifact of the
      currency, and with it goes the "eight setups" half of the trade.
      **FINDING 2, THE VACUITY, AND IT IS THE WORST FAILURE THIS MECHANISM CAN HAVE.** In a
      job with no `strategy.matrix`, GitHub evaluates `matrix.shard` as null, so
      `matrix.shard == 1` is FALSE and every conjuncted step SKIPS. A `SHARD_COUNTS` entry
      written before the matrix block lands therefore turns the whole lane green having run
      nothing. Nothing catches that today: gate-bind never inspects the job for a `strategy:`
      block, and `check:ci-quality-complete`'s static half asserts only that the aggregator
      job exists and `needs:` the sharded lane (scripts/gates/check-quality-complete.ts:324
      and :390). It never asserts that the lane's matrix values equal 1..N. This is also why
      the control cannot live inside the sharded lane: that gate declares `lane: quality-code`,
      so once `quality-code` is sharded the static half is itself conjuncted onto one leg and
      skips with everything else.
      **FINDING 3: the box's stated remaining unknown is now MEASURED, from two real CI runs
      rather than the local duration cache, and it answers the opposite question to the one
      the box asked.** Run 34811039022 (2026-09-14) and run 34740890431 (2026-09-13), job
      `Quality / Code`, per-step timings from the Actions API. Wall clock **568 s** and
      **644 s** against the `timeout-minutes: 15` budget at
      .github/workflows/ci-quality.yml:604, not the 862 s the local-floor model predicted
      (that model divided by the in-job pool at scripts/ci-runner/run.ts:941, which does not
      apply: in this lane each gate is its own WORKFLOW step and steps run sequentially).
      The split that decides this box: region steps, the conjunctable ones, **307 s / 338 s**;
      non-region steps **259 s / 303 s**. So **46 to 47 percent of the lane is REPLICATED onto
      every leg**. Fixed per-leg overhead (`Set up job`, two checkouts, the setup-workspace
      action and its posts, Bitwarden) is **37 s**, about 6 percent, so the setup cost this
      box called "the whole question" is NOT the deciding term. The deciding term is that
      `TypeScript` (100 s / 118 s) and `Dead bash` (78 s / 89 s) are hand-written steps
      outside the region and carry 178 s of the 259 s. Both are manifest-only entries with no
      declaring file, so gate-bind has nothing to emit them from.
      **THE ARITHMETIC, STATED SO IT CAN BE ARGUED WITH (run 34811039022 figures).** Per-leg
      cost is `259 + makespan(307 across N legs)`, and the region's own floor is its largest
      single step: `Lint` at 130 s, with `Every source file reaches a linter` next at 90 s.
      x2 gives about 436 s (**1.30x** for twice the runners), x4 about 389 s (**1.46x**), and
      x8 is still 389 s because `Lint` bounds it. Amdahl's ceiling at a 46 percent replicated
      share is 2.17x; the step-granularity ceiling is 1.46x. That is nothing like the
      "14.4 min to under 3 min" recorded above, which divided the whole lane.
      **SO THE PREREQUISITE IS REGION COVERAGE, NOT THE MATRIX.** Two changes move the ceiling
      before a single runner is added: split the composite `Lint` step into its five declared
      gates (130 s becomes five units of about 26 s), and give `check:types` and
      `check:ci-dead-bash` declarations so they enter the region (178 s becomes shardable).
      With both, replicated falls to about 81 s and the region rises to about 485 s, so x4
      lands near 202 s, a real **2.8x**. Sharding first buys 1.3x and pays 4x of runner for it.
      **THE DESIGN, CONCRETE ENOUGH TO EXECUTE. Five pieces, in order, all driver-only.**
      **D1. Shard over EMITTED STEPS, not over lock ids.** Add `step?: string` to `ShardInput`
      (scripts/ci-runner/lanes.ts:217; `GateSpec` already carries it, so the real lock drives
      it unchanged). In `shardPlan`, immediately after the mutex merge at
      scripts/ci-runner/lanes.ts:485 and before the `needs` merge, add the FIFTH merge rule:
      group the lane's entries by `ci.step` and union each group, recording the reason as
      `one step "<name>"`. Heavy peak for a shared-step unit is ONE, the same treatment
      `concurrentHeavy` (scripts/ci-runner/lanes.ts:583) already gives a mutex-only unit and
      for the same arithmetic: the ids of one step are one `run:` block in one shell. The
      receipt is `Lint` itself, which runs all five heavies today on one runner in 130 s with
      CI green, so refusing it would be refusing the status quo. State the exception in the
      comment: a step that fans out internally (`Quality-gate unit tests` under xdist) peaks
      higher, its lane is not a shard candidate today, and if one ever is, its unit must be
      counted at its real peak. Also widen the `overloaded` refusal at
      scripts/ci-runner/lanes.ts:572 so a shared-step unit is not caught by it.
      **D2. Refuse the id/step gap instead of emitting it.** `shardAssignment` returns
      `{ legs, replicated }`, where `replicated` is the lane's lock entries whose step is not
      one gate-bind emits. `--write` PRINTS them by name with their share of the lane, every
      run, because a quiet exemption is how a gate stops meaning its name. Add a declared
      ceiling beside `SHARD_COUNTS` (scripts/ci-runner/lanes.ts:393), e.g.
      `SHARD_REPLICATED_MAX: Record<string, number>` as a fraction, and REFUSE when the
      replicated share exceeds it. That turns the `quality-security` mistake this box already
      made by hand into arithmetic: its share is 153 of 166 entries and about 98 percent of
      the cost, so any sane ceiling refuses it without a human having to notice.
      **D3. Emit the `strategy:` block; do not hand-write it.** A new marker pair at the job's
      four-space indent, between `timeout-minutes:` and `steps:`:
      `# >>> gate-bind strategy (generated; do not edit inside)` and
      `# <<< gate-bind strategy`, holding `strategy:` with `fail-fast: false` (never
      `continue-on-error`) and `matrix: shard: [1, ..., N]` from `SHARD_COUNTS`. Implement it
      as `rewriteStrategyRegions(workflow, counts)` in scripts/gate-bind.ts, called from the
      `--write` path just before the `rewriteRegions` call at scripts/gate-bind.ts:1791, and
      refuse in BOTH directions: a lane in `SHARD_COUNTS` with no strategy region is refused
      with the exact YAML to paste, and a strategy region for a lane not in `SHARD_COUNTS` is
      refused as a drain. Leave `name: Code` alone; GitHub renders the leg as
      `Quality / Code (1)`, which still satisfies `WATCHDOG_NO_RETRY_PATTERNS` matching
      `Quality` by `String.includes`, and leave `runs-on` and `timeout-minutes` literal so
      `laneCapabilities` and CHECK 3 (.ci/rediacc_ci/security/workflow_gates.py:631) read what
      they read today. Branch protection is the one consumer OUTSIDE this tree that keys on
      the rendered check name: if `Quality / Code` is a required check, the rename to
      `Quality / Code (1)` is operator-only and must be asked before this lands.
      **D4. Make the leg's receipt COUNT WHAT RAN, not what was planned.** A driver-emitted
      literal would report a full leg even when every step skipped, which is exactly Finding 2.
      So gate-bind gives each conjuncted step an `id:` (`gate_` plus the gate id with `:` and
      `-` mapped to `_`, one per STEP after the D1 merge) and emits one final UNCONJUNCTED
      step with `if: always()` that writes the receipt from `toJSON(steps)`, `job.status`,
      `matrix.shard` and the leg count, counting a step as run when its outcome is not
      `skipped`. The `gates` field must be in the aggregator's currency, LOCK IDS, because
      scripts/gates/check-quality-complete.ts:226 compares it against
      `declaredShard.ids.length`; gate-bind therefore also emits a step-id to lock-id map into
      that step's `env:`, and the counter sums the ids of the steps that actually ran. Upload
      as `quality-shard-${{ matrix.shard }}`; the aggregator job downloads the set and runs
      `check:ci-quality-complete -- --receipts <dir>`. An all-skipped leg then reports
      `gates: 0` against a plan that says 43 and reds, which is what makes the mechanism
      defend itself even if D3 regresses.
      **D5. Two static clauses `check:ci-quality-complete` does not have yet.** First: for
      each lane in `SHARD_COUNTS`, the job's `matrix.shard` list must equal `[1..N]` exactly,
      both directions. Second: move that gate's own declaration off any lane that can be
      sharded (it declares `lane: quality-code` today), or it is conjuncted onto one leg of
      the very lane it polices.
      **ONE STALE COMMENT FOUND IN PASSING, for whoever implements this:**
      scripts/gate-bind.ts:571 says "today only one lane is in `SHARD_COUNTS`" while
      `SHARD_COUNTS` is empty (scripts/ci-runner/lanes.ts:393). It is a leftover from before
      the `quality-security` back-out and should read "no lane is". Not fixed here: this wave
      was read-only in the driver files by instruction.
      **AND ONE GAP IN THE CONTROLS, which matters more.** `shardAssignment` and the conjunct
      branch of `rewriteRegions` have NO selftest control in scripts/gate-bind.ts: the file's
      selftest exercises the no-shard path only, and the comment at scripts/gate-bind.ts:571
      says as much ("both selftest controls keep emitting exactly the steps they emitted
      before"). The mechanism is built, inert AND unexercised in both directions. Any wave
      that populates `SHARD_COUNTS` must first add the two controls a conjunct needs: a lane
      WITH an assignment emits `matrix.shard == N` on exactly the steps the plan gives that
      leg, and a lane WITHOUT one emits byte-identically to today.
      **D1 DONE 2026-09-15, driver-only, inert on landing (SHARD_COUNTS stays empty).**
      `ShardInput.ci` gained `step?: string` (`scripts/ci-runner/lanes.ts:217`); `shardPlan`
      gained the fifth merge rule between the mutex merge and `needs` -- entries sharing one
      `ci.step` union into one unit, reason `one step "<name>"` -- verified against the real
      lock: `quality-code`'s five `check:lint*` ids (all one `Lint` step) now merge, dropping
      its heavy-UNIT floor from 8 to 4 (measured via the plan itself at every n from 1, not
      asserted), and `quality-code` shards cleanly at 4 for the first time (was an
      unconditional refusal). **A second, un-named bug found and fixed while verifying D1
      empirically rather than by inspection:** `Shard.heavy` and the bin-packer's own
      one-heavy-per-shard check summed the merged unit's RAW `heavy` count (5 for the Lint
      unit) instead of `concurrentHeavy(unit)` (which the refusal arithmetic above already
      used correctly), so a real emission would have reported a shard as holding 5 heavy
      processes it can never hold 5 of at once. Both sites now read `concurrentHeavy`.
      **The stale comment at `scripts/gate-bind.ts:571` this box named is fixed in the same
      change** ("today only one lane is in SHARD_COUNTS" -> "no lane is").
      `test_gate_gate_lanes.py` gained 4 controls and fixed one that was passing on an
      UNREALISABLE plan: `test_the_shards_are_balanced_on_weight` used `quality-security`
      at 4, whose dominant 149-id `Quality-gate unit tests` step was NOT one unit before D1,
      so the packer could spread ids across shards for an even weight that real CI could
      never run (gate-bind attaches one conjunct per step). Moved the balance example to
      `quality-code` (which genuinely divides on step boundaries) and added a named control
      that `quality-security` now CORRECTLY stays lopsided. 40/40 pass; `check:ci-gate-bind`
      (407 declared), `check:ci-parity` (485/485), `check:ci-gates-lock`,
      `check:ci-quality-complete` (22 controls) and `check:ci-gate-test-real-file-plants`
      (458 files) all still rc=0; `tsc --noEmit` clean on the touched files.
      **D1's own commit broke the bash TWIN, `test-gate-lanes.sh`, which the port's own
      test run never exercises -- caught by the babysitter's pre-push receipt, not by
      me.** The twin carries its own copy of the balance/heavy-floor assertions and I
      had only fixed the Python port. Fixed as a follow-up commit (`117d6438f`): same
      move (quality-security's example -> quality-code, negative case named, heavy
      floor measured not hand-typed), plus a genuinely stale hardcoded assertion count
      ("35 assertion(s)") the twin had been carrying, now measured from the real PASS
      count. Lesson recorded for D2 before it repeated the mistake: fix both sides in
      the SAME commit, or run both before claiming done.
      **D2 DONE 2026-09-15, both port and twin fixed together this time.**
      `shardAssignment` returns `{ legs, replicated }` (was a bare `Map`), refuses when
      a lane's replicated share exceeds a new `SHARD_REPLICATED_MAX[job]` ceiling, and
      refuses outright if a lane is in `SHARD_COUNTS` with no matching ceiling at all.
      Verified against the real lock: `quality-security`'s replicated share measures
      153/166 = 92.2%, matching the historical "153 of 166" figure exactly.
      **Refactored `shardAssignment` to take `counts`/`ceilings` as PARAMETERS** rather
      than reading `SHARD_COUNTS`/`SHARD_REPLICATED_MAX` directly -- the same pattern
      `shardPlan` already uses -- which is what made this testable at all with the real
      constants still empty; this also closes the box's own earlier-named gap ("NO
      selftest control ... exercises the no-shard path only"). 9 new controls across
      port+twin (44 total each) prove all four shapes: not-asked (null), no-ceiling
      (refuse), over-ceiling (refuse, naming both numbers), and a genuine success that
      returns real legs and a correctly-partial `replicated` set. All surrounding gates
      (`ci-gate-bind`, `ci-parity`, `ci-gates-lock`, `ci-quality-complete`,
      `ci-gate-test-real-file-plants`) still rc=0, `tsc --noEmit` clean.
      **D3 DONE 2026-09-15, and the earlier framing of it as "the first piece needing a
      real CI run" was wrong -- corrected by re-reading the design rather than trusting
      my own prior note.** `rewriteStrategyRegions` (like D1/D2) is fully verifiable
      locally via fixtures, and stays exactly as inert as they were: it is called from
      `--write` right before `rewriteRegions`, and with `SHARD_COUNTS` empty it finds
      nothing to check on the real tree (proven, not assumed: ran it against the live
      `ci-quality.yml` with `{}`, zero findings).
      **A REFUSAL, NOT A WRITER, by design -- deviating from the literal function name.**
      The box's own acceptance criteria read as two refusals ("refused with the exact
      YAML to paste" / "refused as a drain"), not an auto-rewrite, and that is the
      right call: unlike a step's `run:`/`if:`/`env:`, a `strategy:` block changes what
      the JOB IS, and the box's own note that a required-check rename is operator-only
      makes this exactly the kind of structural change this file's other regions never
      auto-apply either (see `classifyDrops`'s claimed/unclaimed split, same philosophy).
      Checks a THIRD direction beyond the box's stated two: a region that exists AND
      agrees on job name but disagrees on the actual shard COUNT also refuses, naming
      both numbers, rather than passing as long as *a* region merely exists.
      **A REAL BUG FOUND IN THE BOX'S OWN PROPOSED MARKER TEXT, before landing it.**
      `# >>> gate-bind strategy` (the literal text the box specifies) matches `OPEN_RE`
      (`/^\s*# >>> gate-bind\b/`, a bare word boundary with no `$`), while its own close
      line `# <<< gate-bind strategy` does NOT match `CLOSE_RE` (`/^\s*# <<< gate-bind\s*$/`,
      which requires nothing after "gate-bind"). Landing that exact text would have made
      `rewriteRegions` misdetect the strategy-open as an ordinary region open and scan
      forward for a close line that never matches, silently swallowing the rest of the
      job block as "region body". Proved with both regexes against the literal strings
      before choosing `# >>> shard-strategy` / `# <<< shard-strategy` instead -- no
      shared "gate-bind" prefix, no collision, and the fixture is now selftest control 6.
      6 new selftest controls, all pass; `check:ci-gate-bind` (407), `check:ci-parity`
      (485/485), `check:ci-gates-lock`, `check:ci-quality-complete` (22 controls) all
      still rc=0; `tsc --noEmit` and eslint clean; biome format caught one over-long
      line the same way it caught one in D2 (fixed with `biome format --write`, the
      third time in one night that oracle alone caught something eslint+tsc missed).
      **D4 STARTED 2026-09-15, its first clause only -- disclosed as a deliberate partial,
      not a silent downgrade.** Landed: `gateStepId(id)` (deterministic `gate_<sanitized>`,
      the `:`/`-` mapping the box specifies) and `emitStep` now takes an optional `stepId`
      that emits an `id:` line ONLY when the step is sharded (`leg !== undefined` in
      `rewriteRegions`'s loop) -- an unsharded step's YAML stays byte-identical, proven by
      a selftest control, not asserted. 3 new selftest controls, all pass; same full
      battery as D3 (`ci-gate-bind`, `ci-parity`, `ci-gates-lock`, tsc, eslint, format)
      all still green.
      **D4 SECOND CLAUSE DONE, same session** -- `lockIdsEnvValue`/`GATE_LOCK_IDS`, as
      described above.
      **A REAL DESIGN BUG FOUND IN THAT SAME CLAUSE, MINUTES LATER, in the box's own
      text this time (not mine): "gate-bind emits a step-id to lock-id map into that
      step's env:, and the counter sums the ids of the steps that actually ran" CANNOT
      WORK AS WRITTEN.** A step's `env:` is process-local to that step; it is not part
      of the `steps` context, so a later receipt step reading `toJSON(steps)` can never
      see an earlier step's `GATE_LOCK_IDS`. Checked every existing cross-step data pass
      in `.github/workflows/*.yml` for a counter-example before concluding this: every
      one uses `outputs` (`$GITHUB_OUTPUT`), none uses `env`, because GitHub Actions
      genuinely does not expose it. Same shape as D3's marker-collision bug -- a plan
      clause that reads as concrete and is wrong in a way only running (or in this case,
      reasoning precisely about the actual GHA context schema) surfaces.
      **THE FIX: the map does not need to travel step-to-step at all.** Every conjuncted
      gate's id is known at COMPILE TIME, so `jobLockIdMap(entries)` builds the WHOLE
      job's step-id -> lock-ids map once, to be embedded on the receipt step's OWN `env:`
      -- `steps.<id>.outcome` (native to the `steps` context, unlike `env`) is then the
      only runtime fact the receipt script needs per step. `GATE_LOCK_IDS` on each
      individual step is kept anyway, downgraded to documentation value only (a human
      reading the emitted YAML can see which lock id(s) a step represents), and its
      docstring corrected to say so plainly rather than silently leaving the wrong claim
      standing.
      `jobLockIdMap` is scoped honestly too: one entry per GATE, not per STEP, because
      `rewriteRegions` itself does not collapse two auto-emitted gates sharing one
      `.step` name into one block today -- a separate, currently non-live gap (the one
      real example, `Lint`, is hand-registered via the manifest and never reaches
      `byLane`), recorded rather than silently assumed away.
      2 new selftest controls plus the earlier 4, all pass; same full battery green,
      `--dry-run` against the live tree still 0 refusals (fully inert, confirmed not
      assumed).
      **D4 DONE, final clause: `emitReceiptStep`, the `if: always()` receipt-writing step
      plus the `actions/upload-artifact` emission.** Correction en route: the babysitter
      caught that the prior clause's evidence ("no cross-step env: pass exists in this
      repo") was itself imprecise -- `$GITHUB_ENV` genuinely exists and is used
      cross-step in `quality-code` (`.github/workflows/ci-quality.yml:230`'s toolchain
      pins), distinct from
      a step-level `env:` block (process-local, the real bug). Verified the correction
      myself before accepting it. The design (compile-time map, not runtime plumbing)
      still stands on its own merits regardless: 60+ conjuncted steps cannot share one
      `$GITHUB_ENV` key without clobbering, and using it would mean editing every gate's
      own `run:` command, versus a compile-time map needing zero changes to any gate
      script.
      Writes `{lane, index, of, result, gates}`, the exact shape
      `readReceipts()` in scripts/gates/check-quality-complete.ts already expects
      (confirmed by reading that file's own type, not re-derived), pinned to the exact
      `actions/upload-artifact` commit sha `.github/workflows/ci-quality.yml`'s existing
      two uses already carry (tagged v7.0.1 there -- described rather than quoted here,
      since that sha is on the ACTION's own repository and would be an unresolvable
      object citation in this one).
      **THE SCRIPT ITSELF IS A HEREDOC TO A REAL FILE, NOT A `node -e "..."` ONE-LINER**,
      specifically because GHA does its OWN `${{ }}` substitution as a text replacement
      over the ENTIRE `run:` block before any shell sees it -- a JS template literal
      containing that exact four-character sequence would collide with GHA's own
      grammar. The script uses plain `process.env.X` reads and string concatenation
      only; a selftest control asserts the literal string `${{` never appears anywhere
      inside the script body.
      **VERIFIED FOUR WAYS, not just by selftest:** (1) the generated YAML parses as
      real YAML (PyYAML, embedded in a full job block); (2) the extracted `run:` script
      was ACTUALLY EXECUTED with realistic env values simulating what GHA substitutes,
      producing `{"lane":"quality-code","index":1,"of":4,"result":"success","gates":1}`
      for a fixture with one running step (1 lock id) and one skipped step (2 lock ids,
      correctly excluded); (3) `actionlint` -- the same linter `check:ci-actionlint`
      runs in CI -- passes with ZERO findings against a full scratch workflow carrying
      the real generated output under a real `strategy.matrix`; (4) `--dry-run` against
      the live tree still 0 refusals (fully inert, SHARD_COUNTS still empty).
      3 new selftest controls on top of the earlier ones. This closes D4 in full.
      **A GENUINELY PRE-EXISTING, UNRELATED FINDING surfaced while testing (not caused by
      D4): a real `gate-bind --write` against the live tree refuses on "Install worker
      project deps" (added by the lint-ordering fix, `10b130a82`) as an UNCLAIMED drop --
      a hand-added step inside the auto-emitted `quality-code` region that no declared
      gate re-emits. `check:ci-gate-bind`'s read-only check does not catch this (its own
      stated blind spot: hand-registered steps are `check:ci-parity`'s business), so it
      has been silently un-writable since that commit landed. Flagged, not fixed here --
      out of scope for B2, and the fix (give that step a header, or `--allow-drop` it
      deliberately) belongs to whoever owns the install-ordering fix.**
      **D5 remains untouched.** `SHARD_COUNTS` population for a real lane is still the
      step that genuinely needs a real CI run to prove (Finding 2's vacuity: an
      unconjuncted step under a live `strategy.matrix` silently skips and reports green
      having run nothing) -- D3/D4's own mechanics do not.
      **CORRECTION 2026-09-15, THIS BOX'S OWN PROSE WAS STALE IN THE OTHER DIRECTION:**
      "D5 remains untouched" stopped being true the same week and nobody updated this
      block. **D5 clause 1 IS DONE** (`b7d139ce0`): `check-quality-complete.ts` now
      independently re-asserts the strategy shape from the aggregator side via
      `rewriteStrategyRegions`, combined with `wiringFindings` at the `main()` call site;
      25 controls pass, all gates rc=0. **D5 clause 2 is DIAGNOSED, not fixed**
      (`060c752a0`): moving `check:ci-quality-complete`'s lane off `quality-code` is not a
      lane swap -- `quality-code` satisfies `stepInJob` because gate-bind emits "Quality
      shard aggregation" from that file's own `lane: quality-code` header, and
      `quality-branch` structurally cannot host a gate-bind region at all (no `- id:
      setup`, invariant 11), matching its neighbours `check_plan_boxes.py` /
      `check_resprofile.py`, which carry no gate header for the same reason. The real fix
      is dropping the `---- gate ----` header and hand-registering, a bigger, different
      change than what was attempted. Verified live 2026-09-15: `check:ci-quality-complete`
      still rc=0 with clause 1's re-assertion active.
      **CORRECTION to my own note, from the babysitter:** the "Install worker project
      deps" unclaimed-drop finding did not lapse on its own -- I wrongly implied that by
      saying it "no longer reproduces" with no cause given. The babysitter moved the step
      out of the gate-bind region in `67f9fbf32`. It was a real finding and it is fixed,
      not spurious; verified live 2026-09-15 that `gate-bind --write --dry-run` reports
      zero drops after that fix.
- [x] **B3 S** `quality-complete` aggregator. `ci_job_aggregation.py` already enforces four things
      about `ci-complete`, including an equality between tier lists and env vars because "either
      half alone is dead". A matrix job's result is a single roll-up, so shards are invisible
      without an intra-workflow aggregator. **Acceptance:** received shard count equals the
      declared shard count, read from the same generated source; no result is failure/cancelled;
      the include list was non-empty. Clause 1 is the stronger form -- an include list that
      dropped half its entries passes the emptiness check.
      **DONE 2026-09-09, registered and rc=0.** `scripts/gates/check-quality-complete.ts`, static
      half live today and the runtime half proven end to end against a real 4-shard plan
      through a test seam. "Read from the same generated source" is literal: `SHARD_COUNTS`
      in `lanes.ts` is the one constant and both the future matrix emitter and this
      aggregator run the same `shardPlan` over it, so no second copy of the number exists.
      Clause 1 is the SET keyed `<lane>#<i>/<of>`, not a count, and each receipt carries its
      own `of` and gate count, so a leg that ran against a DIFFERENT plan is caught even when
      the totals agree.
      **A REGISTRATION ORDERING TRAP, worth recording:** the writer deliberately shipped it
      with NO `---- gate ----` header, because `scripts/gate-bind.ts:1869` reds an
      unregistered file that has one. Once I added the manifest entry the reverse became
      true -- `gate-bind --write` said "already matches" and `check:ci-parity` went rc=1
      naming a step no workflow had. The header has to arrive WITH the entry, not before and
      not after.
- [x] **B4 S** The `ci-quick` job and **fail-open** scoping. Only 45 of 458 entries declare
    (ticked) 2026-09-15T07:33:54Z by f4da5c2e: Verified live, all three pieces: (1) scoping -- check:ci-changed-selection rc=0, 475 gates (46 path-scoped, 429 always-selected), empty-set refusal control passes; (2) ci-quick job -- live in .github/workflows/ci-quality.yml:146, npm run ci:quick -- --list reproduces '383 gate(s) planned...selftest ok'; (3) the tautology-guard hole the box's own prose said was left for 'whoever next touches that gate' (AGGREGATE_RUN missing ci:quick/ci:serial and the --flag bypass) -- already fixed same-day in commit 0a5593050 ('a gate id that said ci twice, and a tautology guard --silent walked past'), confirmed live in scripts/gates/check-ci-parity.ts:484 and check:ci-parity rc=0. The box's own closing note was stale on this one point (said scoping's 'unfinished business' was still open); the code already closed it, just never reflected back into the prose. All three legs verified, no third state, box closes.
      `paths`, so scoping by `paths` fails OPEN for the other 413. **Acceptance:** a gate with no
      `paths` is selected for every non-empty change set; an empty change set must REFUSE rather
      than select nothing ("nothing changed" and "the differ broke" are the same shape).
      **THE SCOPING HALF IS DONE 2026-09-09 and registered as `check:ci-changed-selection`,
      rc=0. THE `ci-quick` JOB HALF IS NOT STARTED, and the box's premise about it is
      wrong: there is no `ci-quick` job.** `grep -nE '^  [a-z][a-z0-9-]*:'
      `.github/workflows/ci-quality.yml`` lists ten `quality-*` jobs and no `ci-quick`.
      What exists is the npm script `ci:quick` at `package.json:349` and the `--quick`
      fixpoint demotion inside `scripts/ci-runner/run.ts`. Creating the job is driver-only
      and is left open.
      **The defect was WORSE than "fails open", and the box's own description of it is the
      part that was wrong.** On an EMPTY file list the rule INVERTS: no file matches any
      glob, so the 46 path-scoped gates all DROP while the 419 unscoped ones survive, and
      the warning said the opposite. Measured on a real `--depth 1` clone with a clean tree:
      `rc=0, 403 of 448 gates selected, zero stderr` — 45 gates silently skipped, green.
      Both unusable change sets now REFUSE, and I drove both myself rather than taking the
      report: an unresolvable base gives `rc=1` with **0 bytes on stdout** and the reason on
      stderr, while a normal `--changed` still returns 475 lines at rc=0.
      **`scripts/ci-runner/select.ts` is new and `scripts/ci-runner/run.ts` was edited to
      call it** — the writer flagged that as outside its stated ownership and it was right
      to: the selection logic was already inside `scripts/ci-runner/run.ts:355-380`, so a `select.ts` nothing
      called would have been the inert-module trap. 4 hunks at default context (the report
      said 3; one is an import), nothing outside `--changed`.
      **The lock numbers in this box are a timestamp, not a fact.** "45 of 458" measured
      474/464/46/418 at the start of the work and 475/465/46/419 two hours later, because
      another session added an entry mid-task. Both new files DERIVE and PRINT the ratio
      rather than stating it. **A free receipt for C2:** `46 of 46` path-scoped gates match
      at least one tracked file, so none has a dead glob today.
      **A registration correction I had to make:** `derivedId` builds the id from the basename
      with its leading check-prefix stripped (`scripts/lib/gate-header.ts:326-341`), so the
      delivered filename
      `check-ci-changed-selection.ts` derived an id with the `ci-` segment DOUBLED, which
      matched no npm script and no manifest entry, and `check:ci-gate-bind` refused it. Renamed to `scripts/gates/check-changed-selection.ts` to
      follow the convention rather than adding an `id:` override.
      **THE `ci-quick` JOB HALF, 2026-09-14: WRITTEN AND DRIVEN IN AN ISOLATED WORKTREE, NOT
      LANDED.** `/pr-babysit` owns the primary tree and `.github/workflows/ci-quality.yml` is
      exactly the file it depends on, so this half exists as a verified 74-line insertion in
      isolated agent worktree this wave ran in, for the driver to re-apply by hand. The box stays `[ ]`
      until it lands in the primary tree.
      **THE LITERAL READING OF THIS BOX IS NOT EXPENSIVE, IT IS IMPOSSIBLE, and the measurement
      is what says so rather than a preference.** "One `ci-quick` job that runs `npm run
      ci:quick`" was the design I set out to write. Driven for real on a bare-node checkout
      (npm install plus install:natives, no submodules, no `packages/shared/dist`):
      `383 gates: 327 ok, 54 failed, 0 skipped, 2 BLOCKED, wall 204.1s (serial 2013.5s, 9.9x)`.
      Joining those 54 ids to `gates.lock.json` by `ci.job` puts them in EIGHT of the ten lanes:
      quality-code 18, quality-security 9, quality-static 8, quality-go 6, quality-i18n 5,
      quality-packages 3, quality-content 3, quality-branch 2. So the job would need the UNION of
      eight lanes' setup, and that union does not exist: `quality-branch` checks out
      `github.head_ref` at `fetch-depth: 0` (`.github/workflows/ci-quality.yml:505-521`, and its own comment says the
      default merge ref would make its gate unable to fire), while every other lane takes the
      depth-1 merge ref. One checkout cannot be both.
      **A SECOND, INDEPENDENT REASON, and it is the one that decides the aggregator question the
      box would otherwise leave open.** `.ci/rediacc_ci/quality/ci_job_aggregation.py:1` reads ci.yml's TOP-LEVEL
      jobs only; every job in ci-quality.yml rolls up into ci.yml's `quality` job
      (`.github/workflows/ci.yml:495-513`), which `ci-complete` aggregates. So a job added here needs NO aggregator
      wiring and, more to the point, CANNOT be exempted from it: `ci-quick` blocks whether or not
      anyone wants it to. A blocking job must be able to be green, which rules out the
      383-gate form a second time. `check:ci-quality-complete` is the SHARD aggregator over
      `SHARD_COUNTS` (`scripts/ci-runner/lanes.ts:393`, still `{}`); `ci-quick` is not a shard lane and must not
      appear there.
      **`check:ci-parity`'s tautology guard misses this by one character, which is worth
      recording as a hole rather than as luck.** `scripts/gates/check-ci-parity.ts:471` matches
      `/npm run (ci|quality)(?=\s|$)/`, so `npm run ci:quick` in a `run:` block is NOT reported,
      even though it is 383 of the 480 registered gates and collapses the lanes in exactly the
      way the guard's own message describes. Nothing was changed there: the guard is right about
      what it names, and widening it belongs to whoever next touches that gate.
      **WHAT WAS BUILT INSTEAD, and it is the half of `ci:quick` that CI genuinely does not
      have.** `npm run ci:quick -- --list` appends `--list` to the second invocation, so the key
      runs `run.ts --selftest` FOR REAL and then PRINTS the quick plan rather than executing it.
      Measured: **1.389s wall, rc=0, stdout line 1 `ci-runner: selftest ok (28 assertions)`,
      `grep -c '^gate '` = 383 (the same 383 the executing run selected), stderr 0 bytes.** The
      new `ci-quick` job is that one command plus a floor, on `ubuntu-latest`,
      `timeout-minutes: 10`, `permissions: {contents: read}`, `if: inputs.is_bot != 'true'`,
      checkout plus `./.github/actions/setup-workspace` at its defaults (no account submodule, no
      natives, no package build).
      **ANTI-VACUITY IS IN THE JOB, NOT IN MY MEMORY OF HAVING CHECKED.** `QUICK_LANE_FLOOR: 200`
      against a live 383, deliberately far below it so it never has to be regenerated: what it
      catches is COLLAPSE, not drift. **Seen firing on the real invocation**, not only in
      reasoning: driven against a one-entry fixture manifest the step printed
      `quick lane: 1 gate(s) planned, floor 200` and exited 1 with the `::error::` line; driven
      against the real tree it printed
      `quick lane: 383 gate(s) planned, floor 200; ci-runner: selftest ok (28 assertions)` and
      exited 0. A third control proved the exit path is not swallowed: `--manifest
      /nonexistent-fixture.json` gives rc=1 with `ENOENT` on stderr. The first line deliberately
      redirects rather than pipes, because `npm ... | tee` would hand the step tee's status and
      swallow a failed selftest.
      **TWO CONTROLS PROVE THE ESTATE'S OWN GATES SEE THE NEW JOB**, because a gate suite that
      silently ignores a new job would make all seven greens below meaningless.
      (1) Flipping it to `ubuntu-slim` / `timeout-minutes: 20` made `check:ci-workflow-gates`
      CHECK 3 print `ci-quality.yml: job 'ci-quick' declares timeout-minutes: 20 on ubuntu-slim,
      above the 14-minute ceiling`; reverted, CHECK 3 is green again with zero mentions of
      `ci-quick`. (2) Padding the `run:` block with two no-op lines made `check:ci-workflows`
      print `.github/workflows/ci-quality.yml:180 (step: Quick lane plan) has 9 logic lines` against the cap of 8;
      reverted, the real block is 7 and the gate is green. Both plants were removed and both
      greens re-driven.
      **GATES DRIVEN AGAINST THE MODIFIED FILE, rc in brackets:** `check:ci-workflow-invariants`
      [0], `check:ci-gate-bind` [0], `check:ci-parity` [0], `check:ci-workflow-orphan-step-keys`
      [0], `check:ci-gate-prerequisites` [0], `check:ci-quality-complete` [0],
      `check:ci-timeout-headroom` [0], `check:ci-workflows` [0], `check:ci-step-env-parity` [0],
      `check:ci-actionlint` [0, "clean across 29 workflow file(s)"], `check:actions` [0],
      `check:ci-swallowed-failures` [0], `check:ci-runner-advice` [0],
      `check:ci-profiler-coverage` [0], `check:ci-app-admin-perm` [0],
      `check:ci-git-history-depth` [0], `check:ci-job-aggregation` [0], plus `python3 -c
      "yaml.safe_load(...)"` parsing the file and listing eleven jobs with `ci-quick` first.
      THREE STILL RED AND ALL THREE ARE PRE-EXISTING, each checked for my file by name and none
      naming it: `check:ci-workflow-gates` (CHECK 4 refuses because no submodule is checked out
      here, and says so in its own words), `check:ci-secret-scope` (one migrated read,
      `watchdog-monitor.yml:CLOUDFLARE_API_TOKEN`), `check:ci-bws-map` (a dead `no_fetch_jobs`
      entry for watchdog-monitor.yml and a dead `CLAUDE_CODE_OAUTH_TOKEN` preimage row). All
      three are in the 54 the baseline `ci:quick` run already had before this edit.
      **A TRAP THIS WAVE WALKED INTO AND IS RECORDING SO THE NEXT ONE DOES NOT.** Two GUESSED
      gate keys returned rc=1 with ZERO BYTES on both streams, which reads exactly like a gate
      failing for a real reason and is instead npm's response to a key that does not exist. Both
      guesses were built from the gate's FILENAME: the aggregation gate's key doubled the
      `ci-` segment where the filename does not, and the admin-permission gate's real key DROPS
      the `no-` its filename carries (`check:ci-app-admin-perm`, `package.json:35`). Under the
      real keys both are rc=0. Derive the key from `package.json`, never from the script's name,
      before diagnosing a silent rc=1.
      **RESOLVED 2026-09-14 FOR THE FIRST OF THE TWO, AND THE CAUSE WAS NOT A TYPO.** The
      doubled segment was `derivedId()` (`scripts/lib/gate-header.ts:326`) working as written:
      it strips a leading `check_` and prefixes the id with a `ci-` segment, so a file whose
      subject is genuinely "CI job aggregation" derives one carrying that segment twice.
      Renaming the package.json key alone would have been regenerated straight back; the fix is
      an `id:` override in the file's own `---- gate ----` header, which is the mechanism
      `scripts/gate-bind.ts:705` exists for.
      The gate is now `check:ci-job-aggregation`. The SECOND was deliberately left alone: its
      `id:` override is explicit and chosen, the `no_` in the filename names the assertion while
      the id names the subject, and both read correctly.
      **ONE MEASUREMENT WORTH CARRYING ELSEWHERE:** the slowest gate in the whole quick lane is
      `check:ci-changed-selection` at **154.9s**, which is B4's own first half, and it sits in
      `quality-code`, the lane with 98 steps. Second is `check:ci-guard-mention-anchoring` at
      37.0s. Nothing was changed about it here; it is recorded because a 155s gate inside the
      largest lane is a scheduling fact the W3 wall target has to reckon with.
      **The one open judgment, stated so it can be overruled rather than parked as a question:**
      whether `ci-quick` is worth a runner slot at all, given that its unique content is 1.4s of
      work behind roughly 40s of setup. I took the default and built it, because nothing in CI
      today runs the `ci:quick` key developers are told to run, and the failure it catches (the
      key not resolving, the manifest not loading, the demotion fixpoint eating the lane) is
      silent everywhere else. If the driver would rather not spend the slot, the alternative that
      costs nothing is to move `check:ci-runner-selftest`'s step into a `--list` form inside
      quality-code, which needs a manifest edit and a lock regeneration and was therefore not
      done in a tree that has to be re-applied by hand.
      **APPLIED BY THE DRIVER, same day.** The 74-line job landed at the reported anchor
      (`jobs:` immediately followed by the `L1 STATIC` banner) in the primary tree's
      `.github/workflows/ci-quality.yml`. Driver-verified directly: `npm run ci:quick --
      --list` reproduces exactly "383 gate(s) planned... selftest ok (28 assertions)" against
      the primary tree; `check:ci-gate-bind` and `check:ci-parity` both rc=0 afterward
      ("405 declared gate(s)..." / "483 manifest gate(s)... agree in both directions"). The
      `ci-quick` JOB HALF of this box is now DONE; the box stays open on the
      **fail-open scoping** half's own unfinished business (see above) until that is
      separately closed.
- [x] **B5 S** The timing contract. The three pytest receipts do not actually disagree -- they are
      three statistics of one gate: a single instrumented run (381.41s), a re-measurement (396s),
      and the floor of five (367.9s). `scripts/gates/check-gate-manifest.ts:511-520` already rules that the
      oracle judges the FLOOR, so 367.9s is the only one computed the admissible way. Record
      `docs/ci-overhaul/12-w3-timing-contract.md`: one statistic, one source (a quiesced reference
      worktree, `git status --porcelain` empty, tree id recorded). **No target in this slice is
      checked off by a timing** -- the W3 targets become recorded observations attached to
      structural boxes. The quality-tier wall has never been measured and must come from the
      GitHub run, not a worktree.
      **DONE 2026-09-09.** `docs/ci-overhaul/12-w3-timing-contract.md`. The three receipts do
      not disagree and the live cache settles it: `.ci/cache/gate-durations.json` holds
      `check:ci-pytest recent: [367884, 394649, 401145, 391815, 406786]`, so **367.9s is
      `min(recent)`** and the only statistic computed the admissible way; 396s is one sample
      sitting between two others; 381.41s answered a different question (serial 823.93 vs
      `-n 8` 381.41 vs `-n 16` 377.18).
      **A FOURTH NUMBER EXISTS** and would have read as a fifth disagreement: **318.2s** in
      `docs/ci-overhaul/11-timing-baseline.md`, same gate, older corpus.
      The floor ruling is confirmed at `scripts/gates/check-gate-manifest.ts:527`, and BOTH existing
      citations of it have drifted -- this box said `:511-520` and `scripts/ci-runner/manifest.ts:5818`
      says `:503`. **No new measurement was taken and the doc says so:** `git status
      --porcelain` returns 352 lines here, so nothing timed in this checkout is admissible,
      and `git worktree add` is hook-blocked.
- [x] **C1 S, driver-only** W2.3's generated manifest region. **Its invariant-3 precondition has
      lifted** -- all four text readers now read the lock, and `scripts/ci-runner/gate-spec.ts:10-18` says so.
      **Scope honestly:** a header owns only `{kind, step, needs, id, run, lane, selftest, slow,
      why, emit, test, blocker}` plus A1's `{env, when}`. It does NOT own `gate`, `leaves`,
      `paths`, `weight`, `heavy`, `mutex`, `reads`, `qualityGateTest` or the prose. So derive the
      eligible set first and publish its size as a receipt; do not target a number.
      **Acceptance:** entry-id set unchanged (458=458); **the lock regenerated from the new
      manifest is byte-identical to the lock regenerated from the old** -- the strongest available
      statement that this is a pure refactor; generated and hand regions partition the set;
      `pool.ts` ordering unchanged (array index is its scheduling tiebreaker).
      **STARTED 2026-09-09. THE RECEIPT THE BOX ASKS FOR: 262 of 477 entries are eligible.**
      The box says "derive the eligible set first and publish its size as a receipt; do not
      target a number", so this is the measurement and not a goal.
      **Its invariant-3 precondition is confirmed, not taken on faith:**
      `scripts/ci-runner/gate-spec.ts:10-18` states the three text parsers are gone --
      `wl_reggate.py`, `check-gate-id-convention.sh` and `check_test_file_orphans.py` all
      moved onto the lock -- and records that each had been wrong in the same silent
      direction, reading 259 of 261 entries in one case and 373 of 420 in another, always
      short and always green.
      **Field histogram over the live 477 entries**, which is what decides eligibility:
      `id`, `run`, `gate`, `leaves` and `ci` on all 477; then `qualityGateTest` 149,
      `slow` 95, `paths` 46, `reads` 23, `heavy` 20, `env` 18, `mutex` 17, `weight` 15,
      `needs` 14, and **`noProfile` 2**.
      **`noProfile` IS A FIELD THIS BOX DOES NOT NAME.** Its list of what a header does not
      own is `gate, leaves, paths, weight, heavy, mutex, reads, qualityGateTest` -- nine
      fields including the prose, and the tree has a tenth. Two entries carry it, and an
      eligibility rule derived from the box's list alone would have silently swept them into
      the generated region and dropped the field.
      **The 215 ineligible entries break down as:** `qualityGateTest` 149 (the whole
      gate-test battery), `paths` 46, `reads` 23, `heavy` 20, `mutex` 17, `weight` 15,
      `noProfile` 2 -- overlapping, so they do not sum to 215.
      **One judgment stated so it can be challenged:** I counted `gate` and `leaves` as
      DERIVABLE rather than hand-only, though the box lists them among the unowned. Taken
      literally the box's list makes the eligible set ZERO, since all 477 carry both. The
      shape gate-bind already emits (`scripts/gate-bind.ts:887-899`) is
      `id` + `leaves` + `ci{kind,job,step}` plus prose, so `leaves` is demonstrably
      generator-produced and the literal reading is the wrong one. **If that judgment is
      rejected the receipt is 0, not a smaller number**, and the box needs restating rather
      than rescoping.
      **The acceptance's entry-id count is a timestamp:** it says 458=458; the tree is
      477=477 today and moved 474 -> 477 during a single task.
      **STEP 2, 2026-09-09: THREE OF THE FOUR ACCEPTANCE CLAUSES HOLD, AND THE FOURTH
      REFUTES THE SHAPE THE BOX ASKS FOR.**
      Measured against the live manifest (now 479 entries, not 477 and not the box's 458 --
      two gates registered while I was working): eligible **264**, hand **215**, and
      * generated and hand regions PARTITION the set -- 264 + 215 = 479, true;
      * entry-id set unchanged -- 479 = 479 against the lock, true;
      * empty intersection -- true;
      * **zero drift**: for every one of the 264 eligible entries, the fields a generator
        would emit from its header-owned and derivable set already equal the committed lock
        row exactly, field by field. That is the pure-refactor claim, and it is proven
        BEFORE writing the region rather than after.
      **But `pool.ts` ordering cannot survive a contiguous region.** The eligible and hand
      entries INTERLEAVE: the array alternates between the two classes **65 times**, the
      first hand entry is at index 2 and the last eligible at index 478, so making the
      generated set contiguous would move **262 of the 264**. `scripts/gen/gen-gates-lock.ts:99`
      states the consequence in one line -- "pool.ts breaks scheduling ties on the array
      index, so order is behaviour" -- and `scripts/ci-runner/select.ts:142` says the same.
      **So a single contiguous generated region is not a pure refactor, and the box's four
      clauses cannot all hold at once as written.** The options, none of them free:
      (a) MANY small regions, one per contiguous run -- 65 of them, preserving order exactly
      but giving the file 130 marker lines;
      (b) one region plus an explicit order key per entry, which moves ordering out of the
      array and into data, and is a behaviour change needing its own argument;
      (c) accept a one-time reordering and re-baseline the scheduler, which is NOT a
      refactor and must not be described as one.
      **DECIDED 2026-09-09: option (a), 65 order-preserving regions.** I parked this as an
      operator choice and that was wrong -- the standing instruction is to take the default
      and keep going, and there IS a default here rather than a genuine preference.
      **(a) is the only option that satisfies all four acceptance clauses as written.** (b)
      moves ordering out of the array and into data, which is a behaviour change needing its
      own argument and its own re-baseline; (c) is a one-time reordering that must not be
      described as a refactor, and this box's own headline claim is that it IS one. Between
      an option that meets the acceptance and two that redefine it, the acceptance wins.
      **The cost is real and stated: 65 regions means 130 marker lines in `manifest.ts`.**
      That is the price of `pool.ts` treating array index as behaviour, and it is cheaper
      than the alternative -- a scheduler re-baseline is a change nobody can prove safe by
      regenerating a lock, which is the one proof this box already has (zero drift over all
      264 eligible entries).
      **Why 65 is minimal rather than arbitrary:** the eligible and hand entries alternate 65
      times, so one region per contiguous run is the fewest regions that preserve order
      exactly. A per-entry marker scheme would need 264 pairs and is strictly worse.
      **The operator can overrule this**; it is recorded as a decision with its reasoning
      rather than left as a question, so the work is not blocked on an answer.
      **STEP 3, 2026-09-09: THE RECEIPT IS 213, NOT 264, AND THE 264 WAS MEASURING THE WRONG
      THING.** A generated entry has to reproduce the entry's PROSE, and
      `scripts/gate-bind.ts:649` settles where prose comes from -- "The `//` prose above the
      entry. This IS the `why:`, so extraction loses nothing." So prose is header-owned
      after all, but only for an entry whose LEAF ACTUALLY CARRIES A PARSEABLE HEADER, and
      the 264 counted lock fields without ever opening a leaf.
      Re-measured through `parseGateHeader` over every field-eligible entry's first leaf:
      **213 truly eligible**, 45 whose leaf has no gate header, and 6 whose leaf is not a
      file at all.
      **Those 6 are NOT rot, and I nearly recorded them as such.** `syncpack`, `biome`,
      `knip`, `tsc`, `astro`, `vitest` -- `scripts/ci-runner/gate-spec.ts:106-110` defines
      the field as "Leaf COMMANDS this gate ultimately executes", so a bare tool name is a
      correct leaf and those entries are hand-written by nature: a tool has no gate header
      to generate from.
      The 45 header-less leaves cluster: 18 under `packages/www`, 14 under `.ci/scripts`,
      2 each in `scripts/__tests__` and `packages/cli`, and 9 singletons including the
      generators themselves (`gen-docs.ts`, `gen-gates-lock.ts`) and
      `check-doc-region-parity.ts`.
      **So the split is 213 generated / 266 hand**, and re-taking the interleaving against
      that set changes the decision's own cost: the array alternates **85** times, but the
      GENERATED regions needed is one per contiguous ELIGIBLE run, which is **43, not 65**.
      **86 marker lines, not 130.** The 65 came from the 264 set and was stale the moment
      the eligibility test got stricter -- exactly the kind of number this campaign keeps
      catching, and this time in my own decision rather than in the box.
      Option (a) therefore costs a third less than I priced it at, which strengthens rather
      than changes the choice.
      **STEP 4, 2026-09-09: THE RECEIPT IS 149, AND EVERY EARLIER NUMBER MEASURED A PROXY.**
      264, then 213, then 214 -- each was a test of whether an entry *looked* generable
      (field set, then leaf-has-a-header). None of them ever asked the acceptance's own
      question: **does building the entry from its leaf's header alone reproduce the entry
      that is there?** Asked directly, over all 480 live entries: **149 reproduce exactly,
      331 do not.** Regions **45**, marker lines **90**. Run again after W9 P2 moved the
      gates, so the paths are the post-move ones.
      **THREE DEFECTS IN MY OWN BUILDER, found by the round trip and each worth recording
      because the first two would have shipped as data loss:**
      * **`needs` MEANS TWO DIFFERENT THINGS.** The header's `needs` is CAPABILITIES
        (`node`, `python`, `submodules`); the manifest's `needs` at
        `scripts/ci-runner/gate-spec.ts:43` is gate DEPENDENCIES, and only 14 entries carry
        it. Emitting the first into the second scored 121 false mismatches, and had it gone
        the other way it would have written capability strings into the dependency graph.
      * **`ci.job` is COMPUTED, not read.** A header pins a lane only when it says `lane:`;
        otherwise `placeGate(laneCapabilities(...), needs)` derives it, exactly as
        `scripts/gate-bind.ts:152` does. Reading `h.lane` alone lost the job on 104 entries.
      * **A replacer-array `JSON.stringify` is not a debug printer.** `JSON.stringify(o,
        Object.keys(o).sort())` applies the allowlist at EVERY level, so every nested `ci`
        printed as `{}` -- the comparison was right and the evidence I was reading was blank.
      **WHAT THE REMAINING 58 field-eligible non-reproducers are, by the field that differs:**
      `ci` 31, **`slow` 22**, `env` 9, `needs` 8, `run` 3, `id` 1 (overlapping).
      **The 22 `slow` are the interesting ones and they are a FINDING, not a rejection.**
      `slow` IS a header-owned field (`scripts/lib/gate-header.ts:78`), so these 22 entries
      carry a fact in the manifest that their own header does not declare -- the header and
      the manifest disagree today, silently, and only a round-trip test can see it. Their
      headers need the declaration before the entry can be generated; that is a fix, not an
      exclusion, and it is the same class as the `env` 9.
      **So the emitter's subject set is 149 now and grows as those declarations land.** The
      option-(a) decision is unchanged: 45 contiguous runs, 90 marker lines, order preserved
      exactly, because `scripts/gen/gen-gates-lock.ts:99` still makes the array index behaviour.
      **AND THEY LANDED THE SAME DAY. 149 -> 166, regions 45 -> 41, markers 90 -> 82.** The
      31 missing declarations went into their own headers -- 22 `slow: true` and 9
      `env-<KEY>:` lines over 29 files, inserted before each header's `why:` because `why:`
      is last and continues onto the lines after it.
      **THE PROOF THAT THIS WAS A PURE EDIT, and it is the acceptance clause itself:**
      `npx tsx scripts/gate-bind.ts --write` reports `already matches (402 gate(s))` with
      nothing dropped, and `npm run gen:gates-lock` leaves
      `scripts/ci-runner/gates.lock.json` **byte-identical** -- compared against a copy taken
      before the run, not eyeballed. So 31 facts that the manifest held and the headers did
      not now live in both, and no generated artifact moved.
      `check:ci-parity`, `check:ci-gate-manifest`, `check:ci-doc-region-parity`,
      `check:ci-gate-id-convention`, `check:ci-language-policy` and `gate-test:ci-parity` are
      all rc=0 after it.
      **The remaining 41 split `ci` 31, `needs` 8, `run` 3, `slow` 3, `id` 1, `env` 1**
      (overlapping). The `ci` 31 are the next tranche and are not a rejection either: they
      are entries whose lane `placeGate` derives differently from the one the manifest
      records, which is either a missing `lane:` pin or a real disagreement -- and a
      disagreement between the placement function and the manifest is worth knowing about
      whatever C1 decides to do with it.
      **AND THE `ci` 31 WERE MY BUILDER AGAIN, NOT THE DATA -- ZERO LANE DISAGREEMENTS.**
      Broken into sub-fields the 31 are `ci.kind` 19, `ci.blocker` 11, `ci.test` 10,
      `ci.step` 1, and `ci.job` **0**: over every field-eligible entry whose header does not
      pin a `lane:`, `placeGate` returns exactly the job the manifest records, 0 exceptions.
      The three real classes, each a GENERATOR RULE rather than a data fix:
      * **A `battery` header rides a shared step, and the manifest records that as
        `kind: 'step'`.** All 19 are the i18n family riding the `i18n` step. The generator
        maps `battery` -> `step`; nothing in the tree is wrong.
      * **`ci.test` and `ci.blocker` are header-owned and my builder never emitted them.**
      * **A header carrying `blocker:` is DECLARING ITSELF HAND-REGISTERED** -- the ten
        blocker texts all say some variant of "runs before this lane's `- id: setup` step,
        so emitting it into the region would move it below the guard and skip it whenever
        setup fails". So `blocker:` is an EXCLUSION from eligibility, not a field to emit,
        and reading it as a mismatch was reading a refusal as a discrepancy.
      **FINAL RULE AND FINAL RECEIPT: 171 of 480 generated, 309 hand, 46 regions, 92 marker
      lines.** An entry is generated when it is field-eligible, has exactly ONE leaf that is
      a real file, that leaf carries a parseable gate header, the header declares no
      `blocker:`, and building the entry from that header alone reproduces the entry
      field-for-field. The last clause is the one that matters: it IS the acceptance's
      pure-refactor claim, tested per entry before any region is written.
      **The 15 that still differ are `needs` 8, `run` 3, `slow` 3, `id` 1, `ci.step` 1,
      `env` 1** (overlapping) -- and the `needs` 8 are genuinely hand, since a manifest
      `needs` is a gate DEPENDENCY and no header grammar expresses one.
      **STILL TO DO IN THIS BOX:** the emitter itself -- serialise the 171 into 46
      marker-delimited regions in `scripts/ci-runner/manifest.ts` and prove the regenerated
      lock byte-identical against a COPY. The prose is the open question there and not in the
      round trip above, which compares parsed objects: `scripts/gate-bind.ts:649` says the
      `//` prose above an entry IS the header's `why:`, so the emitter has to reproduce it as
      text, and any entry whose prose is not its `why:` is one more exclusion.
      **STEP 5: THE PROSE CLAIM IS FALSE AGAINST THIS TREE, AND IT IS THE CLAIM STEP 3 RESTED
      ON.** `scripts/gate-bind.ts:649` says "The `//` prose above the entry. This IS the
      `why:`, so extraction loses nothing", and STEP 3 quoted it to treat prose as
      header-owned -- which is what took the receipt from 264 to 213. Measured directly,
      entry by entry, over all 480 spans in `scripts/ci-runner/manifest.ts`: **122 entries
      carry prose, and exactly ONE of them has prose equal to its header's `why:`.** 60
      differ outright and 61 have no `why:` in the header at all.
      That sentence is true of gate-bind's own EXTRACTION direction -- reading an entry in
      order to write a header -- and it is not true of the tree as it stands. A generator
      that emitted `why:` as the entry prose would destroy **121 of 122** prose blocks,
      replacing measurement notes and dated reasoning with a one-line why or with nothing.
      That is the largest single data-loss risk this box has surfaced, and only a
      text-level comparison could see it: the round trip above compares parsed objects, and
      prose is not in the object.
      **SO THE BUILDABLE RECEIPT IS 129, and it is the first one that carries no loss.** Of
      the 171 field-reproducible entries, **42 carry prose** and **129 do not**. The 129 are
      generable today, exactly, with nothing to preserve: **41 regions, 82 marker lines.**
      **The 42 are a follow-on, not a refusal:** each needs its prose migrated into its
      header's `why:` before its entry can be generated, and that migration is reviewable
      one entry at a time. Doing it would take the set to 171 and the regions to 46.
      **DONE 2026-09-09. `scripts/gen-manifest.ts`, 43 regions, and ALL FOUR ACCEPTANCE
      CLAUSES HOLD.**
      **The design that makes clause 2 true by construction rather than by hope:** an entry
      is emitted only if its serialisation is BYTE-IDENTICAL to the span already in the
      file, so `--write` inserts nothing but marker lines. Measured on the write: **84 lines
      inserted, and `diff` shows no other changed line in `scripts/ci-runner/manifest.ts`.**
      No entry moves, so the array index -- which `scripts/gen/gen-gates-lock.ts:99` makes
      behaviour -- cannot move either, and `scripts/ci-runner/gates.lock.json` regenerated
      **byte-identical against a copy taken before the run**. An entry whose generated form
      differs is EXCLUDED, never rewritten: a generator that would improve an entry is
      changing behaviour it cannot prove.
      **The exclusion census the tool prints, which is the receipt in runnable form:** 215
      carry a hand-only field, 60 carry prose, 44 have no gate header, 21 declare a
      `blocker:`, 10 have more than one leaf, 4 have a tool for a leaf, and **4** serialise
      differently -- those four are the aggregate ids (`check:cli-docs` derives
      `check:ci-i18n-command-parity` from its own filename and names the shared `i18n` step).
      **A FIELD-ORDER FACT WORTH RECORDING:** `env:` sits between `id:` and `run:` in this
      file, not after `leaves:`. Getting that wrong cost 2 entries and was invisible to the
      object-level round trip, which is the whole reason clause (5) compares TEXT.
      **The gate is self-hosting:** `check:ci-gen-manifest` is registered, its own entry
      qualifies, and it sits inside a generated region -- 42 regions became 43 when it
      landed.
      **It is not vacuous, and that is planted rather than asserted:** a hand edit to a
      `step:` line inside a region makes it exit 1, and the tree restored exits 0. Five
      `--selftest` controls cover the splice being reversible byte-for-byte, the markers
      bracketing the right entry, the span scanner not shifting the splice index, and two
      runs separated by a hand entry staying two regions.
      **ONE TRAP PAID FOR AGAIN:** `gate-bind` reads the git INDEX, so a brand-new
      generator is invisible to it and the step is never emitted while `check:ci-parity`
      reports "no such `run:` step". `git add -N` fixes it without staging content.
      Green after the landing: `check:ci-parity`, `check:ci-gate-manifest`,
      `check:ci-doc-region-parity`, `check:ci-gate-id-convention`, `check:ci-gen-manifest`,
      `check:ci-language-policy`, `gate-test:ci-parity`. `gate-bind --write` rewrote 6
      regions with nothing dropped -- 26 steps added, 3 relocated, 0 lost, each of the three
      verified still present by name.
      **AND THE LAYOUT GATE MOVED IT, WHICH IS THE SYSTEM WORKING.** `check:ci-domain-partition`
      went red on the new file -- "NEW OUT OF PLACE `scripts/gen/gen-manifest.ts` -- put it in
      scripts/gen. Do not add it to the baseline." -- so it now lives at
      `scripts/gen/gen-manifest.ts`, the first occupant of the `scripts/gen/` home that W9 P2's
      second leg will fill. Its `ROOT` gained a second `..` and its three imports a `../`.
      **THE RULE THAT NAMED THE HOME COULD NOT SEE A FILE IN IT.** `scripts/data/domains.json`
      rule `generators` declared `"home": "scripts/gen"` while matching only
      `scripts/gen-*.ts`, `scripts/generate-*.ts` and four more patterns that all live OUTSIDE
      that directory -- so the moment a file actually arrived, the gate flipped from OUT OF
      PLACE to **UNCLASSIFIED**, which `onUnclassified: "error"` makes red. That is the
      finish-line trap in a partition rule: it reds exactly when the move it demands succeeds.
      Fixed by making the home its own first pattern (`scripts/gen/**`), with the reasoning in
      the rule's `why:` so it is not tidied back out. **`scripts/ops` will need the identical
      line** when the operator-script leg lands, and `operator-bash` is the rule to widen.
- [x] **C2 C** W2.5 tier 1: `pathsOrigin` required whenever `paths` is present.
    (ticked) 2026-09-15T07:53:05Z by f4da5c2e: Implemented and verified live: pathsOrigin added to GateSpec (scripts/ci-runner/gate-spec.ts), set to 'declared' on all 46 pre-existing paths-bearing entries in manifest.ts, plus a new check:ci-paths-origin (scripts/gates/check-paths-origin.ts) enforcing cardinality equality both directions, per-glob zero-match detection for 'declared' origins, and re-run reproducibility for 'derived:<tool>' origins (dormant, proven only by --selftest since no entry uses it yet -- same shape as B2's SHARD_COUNTS). check:ci-paths-origin rc=0 (15 selftest controls, 47 real entries, 0 findings against 6123 tracked files). Full battery green: tsc, check:lint:tooling, check:format, check:ci-gate-bind, check:ci-parity, check:ci-gates-lock, check:ci-gate-reachability-coverage, check:ci-gate-prerequisites, check:ci-actionlint, check:ci-workflows, check:ci-workflow-invariants, check:ci-step-env-parity, check:ci-doc-region-parity, check:ci-workflow-orphan-step-keys, check:ci-timeout-headroom, check:ci-swallowed-failures, check:ci-job-aggregation, check:ci-quality-complete. Landed at bfb8630dd. Its own note ('C2 need not raise 45 to any target') held: no new target was invented, and B4 (done this session) is what made this safe to land without racing that box's own fail-open work.
      **Acceptance:** cardinality equality both directions; a `declared` origin whose glob matches
      zero tracked files REDS (such a gate is silently excluded from every `--changed` run); a
      `derived:<tool>` origin must reproduce under re-running. Interlocks with B4: the fail-open
      assertion is what makes it safe for 413 entries to carry no `paths`, so C2 need not raise 45
      to any target.
- [x] **D0 S, head of the W5 spine** Build the exec baseline the W5 target is defined against.
      `grep -rln 'strace|GUARD_PASS|HOOKS_ONLY|FORK_COUNT'` over `.ci`, `.claude`, `scripts`
      returns one unrelated file. **W5 P0's stated fork counter is not in the tree and the
      "456 execs -> 35" figure is unreproducible.** A Bash call fires **12** hook processes today.
      Build `.claude/rediacc_hooks/execcount.py` + `.ci/policy/hook-exec-baseline.json`. **Not
      strace** -- unavailable on macOS, needs ptrace in containers, and a baseline CI cannot
      reproduce is the same class of problem as the missing one. **Anti-vacuity: a run producing
      zero counts is a refusal**, which is exactly the failure shape of the baseline that vanished.
      **DONE 2026-09-09 and registered.** `check:ci-hook-exec-baseline` rc=0.
      **The box understated it: the grep returns ZERO files, not "one unrelated".** W5 P0's
      fork counter and W5 P6's "456 execs -> 35" are both unreproducible, so the W5 target
      was unfalsifiable until today. "A Bash call fires 12 hook processes" IS exact.
      Static, out of `.claude/settings.json`, not strace (macOS, ptrace, reproducibility).
      Pins 30 entries / 11 patterns / 11 probe tools / 6 events and refuses in BOTH
      directions, so D4's collapse must repin.
      **A REAL AMBIGUITY IT SURFACED AND REFUSED TO GUESS AT:** `.claude/settings.json` mixes
      an anchored matcher `^(Edit|MultiEdit|Write|NotebookEdit)$` with two bare ones (`Bash`,
      `AskUserQuestion`), and NOTHING in this repository says whether the harness matches by
      `re.search` or `re.fullmatch`. Under `search`, `Bash` also selects `BashOutput`, so
      every Bash-chain guard runs on a BashOutput call: **12 processes against 3**. Both
      readings are computed and the disagreement is pinned with a BLOCKER; a NEW ambiguity
      reds. Anchoring to `^Bash$` is a behaviour change to every Bash guard and needs its own
      box.
      **13 controls passed while the instrument was broken:** `_load_counter()` resolved
      through `paths.from_root()`, which honours the root of the tree being JUDGED, so the
      first scratch-tree run died with ModuleNotFoundError. Anchored on the instrument, plus
      two controls, one needing a `sys.modules` purge or it asserted nothing in a warm
      process.
- [x] **D1 C** Cross-OS. Only W5 P1's `/proc`-vs-`ps` seam exists (`.claude/rediacc_hooks/proc.py:32-43`);
      `dispatch.py` has zero platform handling. Enumerate every platform-sensitive operation, give
      each a seam with an env override, and assert the enumeration is complete: a scanner's finding
      set must EQUAL the declared seam set, both directions.
      **DONE 2026-09-09 and registered.** `check:ci-hook-cross-os` rc=0. The box's premise
      was VERIFIED before building on it: `.claude/rediacc_hooks/proc.py:88-102` is the
      `REDIACC_PROC_BACKEND` seam as described, and `dispatch.py` has ZERO platform handling
      (AST walk; the single grep hit is inside a docstring).
      65 files, 7 platform-sensitive operations, 2 declared scopes, **0 unclaimed and 0
      dead**, set equality both ways.
      **AST, NOT GREP, IS THE DIFFERENCE BETWEEN A GATE AND A NOISE MACHINE:** a textual
      sweep for `pgrep` returns 15 hits and 14 are prose or a pattern matched against
      somebody else's command line. The AST walk reduces it to 1. The platform set is NAMED
      (Linux + macOS; Windows reaches this tree only through WSL), which is why `fcntl`,
      `os.killpg` and `signal.SIGKILL` are excluded rather than reported as 5 findings a
      reader could do nothing with.
      **It broke `check:ci-dead-python` and the fix is instructive:** its first gate test
      named `run_tests.py` as the plant target, and because that file is exempt BY NAME and
      the exemption is checked in BOTH directions, merely MENTIONING it conferred a
      `mentioned` route and the exemption stopped being true. Deleting the plant was not
      enough -- the route is a path-suffix match over PROSE.
- [x] **D2 C** The `WORKLIST_*` registry: **134 distinct names across ~56-60 files at 178 read
      sites**, no registry, no schema. A typo'd name reads as unset, which for a feature flag is
      the fail-open direction. New policy list reached through `policyPath()`; generated doc table
      via the existing provider mechanism. **Acceptance:** set equality both directions -- an
      unregistered read reds, a registered name nobody reads reds as dead.
      **Trap:** the scanner must not read `agent/` (invariant 7) or `docs/`; exclusions are
      declared in the registry with reasons, not hardcoded.
      **DONE 2026-09-09 and registered.** `check:ci-worklist-env-registry` rc=0.
      **All three of the box's numbers are the GREP answers and all three are wrong.**
      Distinct names: 134 by grep, **133 live** -- `WORKLIST_EMAIL` is prose-only history at
      `.claude/hooks/stop/worklist-cases/13-ci-queue-and-mail.sh:142`, read nowhere. Files:
      the box says "~56-60", and a range in a plan means nobody counted; **60 mention one, 28
      actually READ one**, the other 32 being shell fixtures that only ASSIGN. Read sites:
      **181, not 178**, plus 153 bash assignment sites the box did not count at all.
      A registry built from grep would have enshrined a dead name on day one, which is why
      the scanner walks the AST.
      **What is derived and what is authored is the design decision:** the name set and each
      name's set of default SPELLINGS are derived and pinned (two sites reading one name with
      different fallbacks is a real bug class invisible to grep). The `kind` is authored,
      because derivation cannot tell `'1'` the boolean from `'1'` the count and gets three
      names wrong today. `why` is required only for `flag`, `handle` and `corpus` -- the
      kinds where a typo turns something OFF or narrows what is looked at. 111 machine-written
      sentences about numeric thresholds would be filler, and filler is how a required field
      stops being read.
- [x] **D3 S, long pole** Shard the hook suite. `test-hooks.sh` is **2,774 lines**, `slow: true,
      // 537.4s`, one `run:`. `run_tests.py` (100 lines) is wired to nothing and says so.
      **Invariant 2 bites in six places, all verified:** `.ci/config/language-policy-baseline.json:476`;
      `.ci/policy/.dead-bash-allowlist:42` plus three golden files encoding the line index;
      `.ci/rediacc_ci/quality/trap_registry.py:227` (`TRAP_HOOK_SUITE`, a single path constant, plus two control
      fixtures); `.ci/rediacc_ci/quality/hook_integrity.py:69` (`SUITE=`, single path); and two line-numbered measurement
      comments already stale against 2,774. **All six re-keyed in the same change, or the split is
      not done.** **Acceptance:** the multiset of assertion labels across shards equals the
      pre-split multiset, extracted by the same extractor on both sides. Floor corpus-derived,
      never a hand-typed 395 or 398.
      **DESIGN 2026-09-08 (Plan agent), and this box AS WRITTEN IS ILLEGAL.** A bash-to-bash
      shard adds a 522nd path to the 521-path SET frozen by `check:ci-language-policy`
      (`COVERED_ROOTS = (".ci", ".claude")`, `baseline_additions` -> `return 1`), and
      `.claude/hooks/test-hooks.sh` is entry **472** (the Plan agent said 476; I re-derived it
      from the baseline JSON and it is 472 of 521, and the refusal is
      `.ci/scripts/quality/check_language_policy.py:137` `COVERED_ROOTS = (".ci", ".claude")`
      with `baseline_additions` reaching `return 1` at `:535`). The precedent it reaches for --
      `test-worklist-v5.sh` split into 27 files -- predates the freeze and cannot be
      repeated. **D3 is a PORT TO PYTEST, not a split**, which is what
      `.ci/rediacc_ci/tests/gates/test_gate_claude_hooks.py:31` already says in code.
      Cheaper than billed: `pyproject.toml:237-241` already has `.claude/rediacc_hooks/tests`
      in `testpaths`, so the destination needs NO driver edit until the terminal commit.
      Measured: 2,774 lines correct; **456 direct assertion calls**, not the runtime 2,229
      (which folds two sub-suites); invariant 2 bites in **seven groups / eleven files**, not
      six, and one of the six named is STALE -- `.ci/rediacc_ci/quality/hook_integrity.py:69` was re-keyed on
      2026-09-06 into `scripts/data/hook-audit-scope.json`, so a writer sent to that line
      edits a docstring. **Four** stale `1644 lines` comments, not two. SERIAL, one writer.
      **DONE 2026-09-09 AS A PORT, acceptance met exactly: 509 = 509.** The extractor is one
      function, `.claude/rediacc_hooks/tests/hooklabels.py`, applied to TWO REAL RUNS -- `bash
      .claude/hooks/test-hooks.sh` (rc=0, PASS=2269 FAIL=0) and the pytest port -- reporting
      `EQUAL`. **Re-run by the driver against the writer's own artifacts: 509 and 509, rc=0,
      and the comparison REFUSES when one side is truncated**, so the equality is not vacuous.
      **THE FLOOR IS CORPUS-DERIVED AND THE BOX'S 456 WAS WRONG:** 474 direct
      assertion-helper calls (static grep and runtime dump agree per helper) plus 35 labels
      from inline blocks and delegations = 509. The bash suite is UNTOUCHED and still passes.
      **Three frozen-environment defects were caught rather than baked in** -- an absolute
      `/home/developer/console` path in the agent-browser cases (the defect the suite's own
      header records from CI run 33133377611), a frozen epic id, and a frozen `$DIR`.
      **TWO SPELLINGS ARE LOAD-BEARING TEXT, NOT STYLE**, and both are this campaign's
      recurring hazard: `hook_integrity.covmap` scans case sources for the literal
      `"check 2 guards/block_x.py"` shape, and each trapguard row must be a TUPLE because
      `ruff format` exploded two separate arguments one-per-line and made all five rules read
      one-sided. Proof both carry: `covered=43 gaps=0` from the Python sources alone, and
      `inject_cases=31` with `hook_is_live` true for all five rules.
      **A RACE INTRODUCED AND FIXED:** `test_hooks_procs.py` spawns live `.sh` processes while
      `test_guards_differential.py` reads the process table for the same guards, so under
      `-n 4 --dist loadgroup` the differential's two anti-vacuity controls went red while
      passing in isolation. Now sharing `XDIST_GROUP`; the four modules together give
      **6048 passed in 363.78s**, rc=0.
      **THE TERMINAL DELETION IS BLOCKED and neither blocker is D3's to clear.**
      `check:ci-hook-integrity` section C fails the moment `test-hooks.sh` leaves
      `case_sources`: `HARNESS_RE` at `.ci/rediacc_ci/quality/hook_integrity.py:360` and
      `FLOOR_LINE` at `:363` are BASH spellings, probed True for the suite and False for both
      Python case sources, so the gate would print "the floor rule audits NOTHING". And
      `check:ci-pytest` timing: the delegates module alone is **787.0s** at `-n 4` against
      `RUN_TIMEOUT_S = 1080` at `.ci/rediacc_ci/check_pytest.py:141` under a 20-minute job cap.
      Both belong to W7P5-c's licence, not here.
- [x] **D4 S** Lifecycle collapse 30 -> 11. The redundancy is mechanical: `require-jq.sh` and
      `require-python.sh` are duplicated across all three PreToolUse matchers and PostToolUse/Bash
      -- 8 of the 30 entries and 8 of the 12 processes.
      **Acceptance:** entry count equals the 11 distinct `(event, matcher)` patterns AND **the
      verdict set for every guard is unchanged**, run against `.claude/oracles/` the way
      `test_guards_differential` already does. Clause 2 is required because a collapse that drops
      a guard passes clause 1 perfectly.
      **NOT DONE 2026-09-09. STOPPED WITH FOUR BLOCKERS, three proven by command.**
      Measurements first: 30 entries and **11 distinct (event, matcher) patterns**, so the
      box's target is right; `require-jq.sh` + `require-python.sh` are 8 of the 30 entries,
      also right. But **"8 of the 12 processes" is wrong: it is 4 of 12.**
      (1) **It needs a bash chain head and that is illegal.** One command per pattern means a
      bash script that inlines both checks then execs `dispatch.py`, and
      `.claude/hooks/require-python.sh:5-12` argues it may never be ported -- written in Python it cannot
      run in the one condition it exists to report. A new tracked `.sh` under `.claude/` is
      the same 522nd-path refusal that makes D3 illegal. PROVEN, and the first attempt at the
      proof was VACUOUS: an untracked probe left `check:ci-language-policy` green because the
      gate reads `git ls-files`. Redone in a scratch git repo: untouched rc=0
      `521 frozen`, one added tracked `.sh` rc=1 `1 NEW bash file(s)`.
      (2) It re-keys `.ci/scripts/quality/check_hooks_resolvable.py:121` `FIRST_GUARD`, and invariant 2 says in the
      same change. (3) It changes a driver-only generated doc via
      `scripts/lib/doc-providers.ts:295`. (4) It rewires live hooks in a shared worktree,
      where any wrong second of `.claude/settings.json` is a wrong second for every
      concurrent session.
      **A safe partial exists:** the three `PostToolUse` groups with `matcher: null` merge
      into one, 30 -> 28 entries with `patternCount` unchanged at 11, semantically identical.
      Still needs the driver for the CLAUDE.md regeneration.
      **RE-VERIFIED 2026-09-20, AND THE BOX STAYS OPEN AS BLOCKED BY DESIGN.** `.claude/settings.json` still
      reads 30 hook commands in 18 groups over 11 distinct (event, matcher) patterns, so the target of 11 is
      right. Three of the four blockers hold as written: `require-python.sh` may not be ported (its own header,
      lines 5-12) and a new tracked `.sh` is refused by the language-policy gate;
      `.ci/scripts/quality/check_hooks_resolvable.py:103` still pins `FIRST_GUARD = "require-jq.sh"` (the earlier note cited
      `:121`); and `scripts/lib/doc-providers.ts:295` still reads the hooks table. Two corrections: "8 of the 12
      processes" is 4 of 12, and the safe partial does NOT reduce the count the acceptance clause measures. The
      three `PostToolUse` groups with a null matcher hold one command each, so merging them takes 18 groups to
      16 and leaves 30 commands, which is why 30 -> 28 was wrong. Exit condition: a Python chain head for
      `require-jq.sh` and `require-python.sh` that runs when Python is missing, or the language policy admitting
      one bash file for it. Neither is reachable without an operator ruling.
      **RE-RUN 2026-09-20 LATER THE SAME DAY, NOTHING CLEARED.** `.claude/settings.json` reads 30 commands in 18
      groups over 11 patterns; `require-python.sh:5-12` still argues it may never be ported;
      `.ci/scripts/quality/check_hooks_resolvable.py:107` pins `FIRST_GUARD = "require-jq.sh"` (line moved from 103);
      `scripts/lib/doc-providers.ts:295` still reads the hooks table; and the language policy still counts 582 bash
      files, 507 frozen, so one more tracked `.sh` for a chain head is refused. The exit condition is
      unchanged and needs an operator ruling.
      **RE-RUN 2026-09-21, NOTHING CLEARED.** Four probes with full stderr, all rc=0 and no stderr: settings.json
      reads 30 commands in 18 groups over 11 patterns; `require-python.sh:5-12` still argues it may never be
      ported; `FIRST_GUARD = "require-jq.sh"` is at `.ci/scripts/quality/check_hooks_resolvable.py:107` and the hooks table is read at
      `scripts/lib/doc-providers.ts:295`; the language policy reports 539 bash files, 464 frozen, none added, so a new
      tracked `.sh` is still refused.
      **D4 DONE 2026-09-21 (036dc10d4), operator option A.** settings.json reads 11 commands in 11 groups over 11
      patterns. The chain head (admitted by a `file:` allowlist entry) runs the two toolchain checks and hands the
      pattern to `lifecycle.py`. A differential over 378 corpus payloads is byte-identical on exit code, stdout and
      stderr against the old 30-command wiring, and five member-drop controls turn it red. `FIRST_GUARD` needed no
      re-key because the gate flattens through the table.
      **WHICH RULING CLEARS WHICH BLOCKER (2026-09-20).** Blocker (1), the bash chain head, is the only one that
      needs the operator: EITHER (A, recommended) `.ci/config/language-policy` admits exactly one named file,
      `.claude/hooks/chain-head.sh`, that inlines the two checks and then execs `dispatch.py`, which lets the
      collapse reach 11 entries, OR (B) the acceptance is amended so `require-jq.sh` and `require-python.sh` stay
      as their own entries, which keeps the language policy as it is and leaves the count at 22 over 11 patterns.
      Blockers (2) and (3) need no ruling: re-key `FIRST_GUARD` and regenerate the hooks table in the same change.
      Blocker (4) needs a quiet window or an operator-created worktree (`! git worktree add`), because a wrong
      second of `.claude/settings.json` is wrong for every concurrent session. After a ruling the change is one
      commit, with the `test_guards_differential` verdict set unchanged as its proof.
      **D0 is D4's instrument** and now pins both numbers, so whoever lands D4 must repin and
      clause 1 of its acceptance is a one-line diff.
- [x] **E1 S, largest single port in this track** `setup` in Python. `.ci/rediacc_ci/setup/` holds
      only `__init__.py` and `tools.py`; the 22 rows DESCRIBE installs and `.ci/rediacc_ci/setup/tools.py:167-169` says
      so ("prose, not something this module executes"). `setup` is still bash: `run.sh:97`
      `PORTED_VERBS=()` -> `.ci/legacy/run-legacy.sh` (pre-flip `:1068`, and the file is 1057 lines now that the
      arm is gone) -> `setup()` pre-flip `:543-715` + `setup_check()` pre-flip `:719`,
      driving seven functions in `.ci/lib/setup.sh` -- **~1,117 bash lines**. No `.claude` wiring,
      no opt-in git hooks. Keep the prose rows: they are what a human pastes when the executor
      refuses (invariant 9). **Acceptance:** shadow ledger at K=5 (the `w6p2-toolchain` shape),
      phase-set equality against the bash call sequence both directions, per-phase idempotence.
      A macOS claim not driven on a real bash 3.2 is not a claim -- the standard W6 P2 set.
      **DESIGN 2026-09-08. The headline is exact -- 1,117 bash lines, verified as
      173+99+845 -- and the box hides an ORDERING TRAP that would strand the writer.**
      `.ci/scripts/test/gates/test-run-sh.sh:279-290` emits `overlap <verb>` as a finding
      when a verb is in both `PORTED_VERBS` and the legacy dispatch, so `PORTED_VERBS=(setup)`
      must land ATOMICALLY with deleting the legacy `setup)` arm and both function bodies.
      That is fine for the gate and **fatal for the K=5 shadow ledger this box demands**,
      because after that commit there is no bash side left to drive. **The ledger must be
      complete and committed BEFORE the flip**, driven against the function bodies directly
      (`bash -c 'source .ci/lib/setup.sh; setup_check'`), never through `./run.sh setup`.
      Acceptance needs ORDER equality, not just set equality: `.ci/rediacc_ci/setup/tools.py:196-200` says the
      table's order IS the dependency order, so an unordered comparison passes a port that
      installs go before jq. `run.sh:97` is really `run.sh:37`; `tools.py` is 1,302 lines and
      not a stub; nine functions are defined, seven drivable.
      **PORTED 2026-09-09 and registered as `check:ci-setup-port-parity`, rc=0.
      THE FLIP IS NOT DONE, so this box stays OPEN.**
      Nine modules under `.ci/rediacc_ci/setup/`, 38 pytest cases, and a K=5 shadow ledger
      at `.ci/shadow/e1-setup.observations.jsonl` reading `5 row(s), 5 distinct clean
      tree(s)`. On the real tree both sides are byte-identical over 118 observations, and
      `setup_check` matches on stdout AND stderr separately at rc=1 each.
      **The box's headline is exact and I re-measured it myself:** `setup()` 173 +
      `setup_check()` 99 + `.ci/lib/setup.sh` 845 = **1,117**.
      **But "seven functions" is SIX.** `setup_docker_probe` at the deleted `.ci/lib/setup.sh`, pre-flip line 575,
      (35 lines) is called by NOTHING -- `grep` over the tree returns its own definition
      and one prose mention in `docs/ci-overhaul/06-progress.md:5109`, verified by me.
      `setup()` runs `ensure_docker_installed` instead, and `scripts/gates/check-dead-bash.ts`
      cannot see it because that gate asks whether a FILE's basename is mentioned. It is
      ported anyway, named in `phases.DEFINED_BUT_UNCALLED`, and clause A4 of the new gate
      fails in BOTH directions if that stops being true. The port is also 15 phases, not 9:
      six live in `local-common.sh`/`devbox.sh` and are bridged so the SAME BYTES run.
      **The ordering trap the design note predicted was real and is proven caught:**
      swapping two phases leaves the finding COUNT identical (116 vs 116) and the name SET
      identical -- only the ordinals move -- so an unordered comparison passes it and the
      ledger's ordinal-carrying lines do not. Planted on the real tree, rc=1 both through
      the ledger and through the new gate, rc=0 after revert.
      **`bash 3.2 WAS drivable here**, contrary to the box's framing: `docker run --rm
      bash:3.2` gives `3.2.57(1)-release`, all four scripts are `bash -n` clean on it, and
      `run.sh:90-92`'s guarded-expansion claim is confirmed (the plain form gives `unbound
      variable`). That is a claim about bash 3.2 syntax and the Darwin branches, NOT about
      macOS, and the report says so.
      **A LIMITATION THAT IS LOAD-BEARING AND MUST NOT BE READ PAST:** `scripts/lib/shadow-gate.ts`
      refuses `--record` on a dirty tree, and this port is uncommitted, so the five ledger
      trees are SCRATCH repositories built from the working tree, not commits of this
      repository. Content-addressing holds; **provenance to this repo's history does not.**
      **THE FLIP NEEDS SIX FILES, not the two the box implies**, and applying only the owned
      half would break the tree: `PORTED_VERBS=(setup)` plus deleting the legacy arm leaves
      `python3 -m rediacc_ci setup` an UNKNOWN verb, because `.ci/rediacc_ci/__main__.py:85`
      `VERBS` is empty. Two `git apply --check`-clean patches are parked in the session
      scratchpad. `test-run-sh.sh`'s own control and `test_main.py` both HARDCODE the empty
      literal and refused the flipped fixture -- which is those controls working, not
      failing. **Held deliberately: see the twin-parity blocker recorded under E3.**
      **FLIPPED 2026-09-09, and E1 IS NOW COMPLETE.** `run.sh:37` is `PORTED_VERBS=(setup)`,
      the legacy `setup)` arm and both function bodies are gone, `.ci/rediacc_ci/__main__.py`
      `VERBS` names the ported verb, and **`.ci/lib/setup.sh` IS DELETED**.
      **THIS IS THE PROGRAMME'S FIRST BASH DELETION: the DELETED axis moved 0 -> 1.**
      `check_language_policy.py --write-baseline` reports `520 path(s) (521 before,
      1 drained, 0 added)` -- composition, not size, and it reproduces the writer's fixture
      measurement exactly. `check:ci-language-policy` rc=1 before the drain and rc=0 after.
      **Driven for real through the router, not inferred:** `./run.sh setup --help` rc=0
      printing the usage block, `--bogus` rc=2, `--check` rc=1 -- the three exit codes the
      pre-flip bash gave.
      Gates after the flip, all rc=0: `test-run-sh.sh` (31 controls),
      `check_setup_idempotency.py`, `check:ci-setup-port-parity`, `check:ci-gate-bind`,
      `check:ci-parity`, `check:ci-gates-lock`, `check:ci-dead-bash`,
      `check:ci-language-policy`, and `test_twin_parity[test_gate_run_sh]` under
      `TWIN_PARITY_ALWAYS_DRIVE=1`. pytest over `test_main.py`,
      `test_gate_run_sh.py` and `test_setup_port.py`: 47 passed, 17 skipped.
      **The skips are the design, not a gap:** `.ci/rediacc_ci/tests/test_setup_port.py:226,283` skip with "the
      bash twin has been deleted; the ledger is the surviving evidence", and
      `check:ci-setup-port-parity` prints `FLIPPED (bash gone)` rather than redding. A gate
      that guards a migration has to survive the migration succeeding -- the same
      finish-line failure E3 fixed in `test-run-sh.sh`.
      **The deletion orphans ~10 comment citations** of the form `.ci/lib/setup.sh:NNN` in
      `.ci/rediacc_ci/core/platform.py`, `proc.py` and `test_core_dockerx.py`. Checked
      before deleting: every one is a docstring reference, none is a `source`, and no gate
      reds on them. The file is recoverable from HEAD (`git show HEAD:.ci/lib/setup.sh`).
- [x] **E2 S** `rdc.sh` 314 -> 70. The native SEA build moves out of `rdc.sh:83-160` into the
      package. **Acceptance:** a line ceiling in the shape of the existing `run.sh` one;
      behavioural equality of `--native` across the three platform arms via a `uname` seam; and
      the macOS probe must be seen to **FAIL on a planted defect** -- a new CI job that has never
      gone red is not yet evidence.
      **DONE 2026-09-09 at 181 lines, and `314 -> 70` IS ARITHMETICALLY UNREACHABLE from
      the move this box names: `314 - 93` is 221 before anything else goes. Target corrected
      to 181**, with a 185-line ceiling now enforced. The SEA build is
      `.ci/rediacc_ci/native.py`, whose `plan()` takes system and machine as ARGUMENTS
      defaulting to the host, so all three platform arms are driven from one Linux box every
      run -- strictly more than the macOS CI job the acceptance asked for, which would cover
      one. Registered as `check:ci-rdc-native`, rc=0.
      **Reaching 70 needs the `--dev` gateway port, which is CUT AS ITS OWN BOX** because it
      is the repo's secret-leak surface: `.ci/scripts/test/test-rdc-sh-env.sh` layer 2 copies
      `rdc.sh` into a fixture containing NO `.ci/rediacc_ci`, so porting it breaks that
      fixture and rewrites its layer-1 assertions in the same change.
      Two deliberate behaviour changes: trailing arguments are now REFUSED (`--native
      --platform win` used to build for the local platform and say nothing), and one message
      lost an em dash because `.ci/rediacc_ci` is a scanned zero-baseline surface.
- [x] **E3 S** Legacy arms to zero. Correct the plan's phantom `LEGACY_ARMS_MAX` to what the tree
      enforces. `PORTED_VERBS=(setup)` is line-neutral, so the 120/120 ceiling does not block E1;
      growing the array does, and that is a decision this box makes rather than discovers.
      **The trap:** `.ci/scripts/test/gates/test-run-sh.sh:315-327` requires `n_legacy > 0` before believing any
      assertion, so **the anti-vacuity clause must be rewritten in the same change that makes
      `n_legacy` zero**, or the gate guarding the migration reds at the moment it succeeds.

---

## T-ENV

      **CORRECTION 2026-09-09, same day: TICKING THIS WAS PREMATURE.** The rewrite landed
      in the BASH twin only. `.ci/scripts/test/gates/test-run-sh.sh` gained 201 lines and now
      prints 31 PASS lines, while its Python port
      `.ci/rediacc_ci/tests/gates/test_gate_run_sh.py` still records 27 controls and still
      carries the PRE-E3 logic in two places: the ceiling test at `:657` counts raw newlines
      against `ROUTER_LINE_CEILING` instead of the table-excluding `logic_lines`, and there is
      no equivalent of the rewritten `vacuity_findings` at all.
      `test_twin_parity.py::test_port_and_twin_agree[test_gate_run_sh]` is RED because of it.
      **REPAIRED 2026-09-09 the same day, and E3 stands as done.** The port now carries
      `router_table_of` and `vacuity_findings` ported rule-for-rule from the twin's awk at
      `.ci/scripts/test/gates/test-run-sh.sh:260-277` and `:388-396`, the ceiling is
      `logic_lines = router_lines - table_rows`, and two new cases cover the three vacuity
      fires plus the terminal state and the table exclusions. Verified by me under
      `TWIN_PARITY_ALWAYS_DRIVE=1`, because a plain re-run REUSES a recorded agreement and
      prints green without driving anything: `twin rc=0 passes=31 | port rc=0 controls=35`,
      and all 31 twin labels are now recorded verbatim. The twin was NOT changed to meet the
      port. Eleven planted defects, one per new assertion, each red with the intended
      message, file restored to its pre-plant sha256.
      **The port's own anti-vacuity block carried the SAME pre-E3 bug**: its `all(shape)` over
      `(router, legacy, subs, docs)` required `legacy > 0` and `subs > 0`, so it too would
      have redded at the finish line. Plant P7 restored that floor and it reds exactly one
      control -- the terminal-state one -- while the live tree stays green, which is the
      isolation that makes the case mean something.
      **Honest limit, stated rather than glossed:** the table exclusion is not yet
      load-bearing on the real tree. `run.sh` is 120 lines with a single-line EMPTY
      `PORTED_VERBS=()`, so 1 table row and 119 logic of 120, and the old semantics also pass
      at 120/120. Both rules are proven by fixtures, which is where the twin stands too.
      **The E1 flip patch must be re-anchored:** the regex it edits has moved from `:619` to
      `.ci/rediacc_ci/tests/gates/test_gate_run_sh.py:748`, and the only other occurrence of
      `PORTED_VERBS=()` is the `TRAP_ROUTER` fixture at `:936`, which the flip must NOT touch.
      **I did not catch this when I ticked the box** -- I ran the four plan gates and the
      subject itself, and never ran the twin's parity test, which is the one instrument that
      compares the pair. Found only when the E1 writer reported the failing suite. A writer is
      repairing the port to meet the twin; the twin is the reference side and is not being
      changed to meet the port. **The E1 flip is HELD until this is green**, because the flip's
      own fragment edits `.ci/rediacc_ci/tests/gates/test_gate_run_sh.py:619` and landing it on top of a red twin parity
      is how a repair gets built on a defect.
      **DONE 2026-09-09, and the phantom is confirmed: `LEGACY_ARMS_MAX` occurs ZERO times
      in the tree.** There is no named budget. The number that reaches zero is the anonymous
      derived `n_legacy` at `.ci/scripts/test/gates/test-run-sh.sh:380`. Measured: 2 router
      arms, 16 legacy arms, 50 subcommands, 18 documented verbs -- a clean partition.
      **The trap this box actually had was its own anti-vacuity floor:** `n_legacy > 0` would
      have REDDED AT THE FINISH LINE, when the last verb ported. Replaced by three clauses
      true in every state including the terminal one, with a control asserting exactly that.
      Nothing is lost: with the extractor blind, `verb_findings` reports 16
      documented-but-unreachable findings rather than one.
      **The ceiling decision this box was asked to make: the verb table is NOT logic.**
      Otherwise the first multi-line table forces a ceiling raise in the same commit, which
      is how a ceiling stops meaning anything. Proven both ways on the real tree: excluding
      only verb rows still reds by one; excluding the table whole leaves a five-verb table
      costing the ceiling nothing. Code smuggled into the table is still counted AND named.
- [x] **W0.0-A S, 2026-09-08, session-executable** The probe. **Correction: only the MINTING is
      operator-blocked.** `BWS_ACCESS_TOKEN` is absent from the session environment but present in
      `private/account/.env` (49 assigned names), and the tree records the probe being run from a
      session on 2026-09-06. **Acceptance:** `bws_env_load` returns the same NAME SET as
      `bws-secret-map.json`'s keys. Never a value, never a count.
      **If it fails:** M0 fails, `bws-token-expiry.json` is left TRUTHFUL (the `expires` date is
      not edited forward, no row is invented), and a last-resort issue carries
      `door:operator-only`. **Per-wave fallback:** W8 P1 and W8 P5 STOP; W8 P2/P3/P6, W8 P4 and
      all of W4 CONTINUE -- they are static analysis over tracked text. **Two thirds of T-ENV is
      credential-free by construction**, which must be stated so nobody concludes M0 blocks W8.
      **RUN 2026-09-09. THE PROBE'S ACCEPTANCE DOES NOT HOLD, and the box's own "if it
      fails" branch is therefore the executed path — this box is closed by running it,
      not by passing it.**
      `bws_env_load` cannot return any name set: it reaches the real API and gets
      `[400 Bad Request] {"error":"invalid_client"}`. **MAPPED_NAMES_PRESENT_IN_SHELL=0**
      of the map's 58 names. Streams read separately; no value was ever printed, per
      `.ci/lib/bws-env.sh:16-18`.
      **The failure is the CREDENTIAL, not the network and not the helper.** Control:
      `curl https://vault.bitwarden.com/` returns http 200 from this box. The first guard
      (`BWS_ACCESS_TOKEN` unset) was passed by loading the name out of
      `private/account/.env` — which does hold it, and does hold exactly the **49 assigned
      names** this box claims.
      **THE DEAD TOKEN IS THE LOCAL COPY, AND CI IS FINE. I nearly reported the opposite.**
      `.ci/config/bws-token-expiry.json` records `mc_migrate_claude` with
      `expires: 2026-09-08` — yesterday — and its own comment says that since `7343ae9dc`
      this is "the SOLE credential path for CI and CD, so its expiry is a total outage".
      **That total outage has NOT happened.** Autopilot run `34294177912` ran TODAY,
      2026-09-09, and its `Fetch secrets from Bitwarden` step is `success`; the composite
      at `.github/actions/bws-secrets/action.yml:14-19` fails the job loudly when a secret
      cannot be read, so a green step is positive evidence and not silence.
      **So GitHub holds a working credential that this repo cannot name.** Fingerprinting
      the local `.env` token's identifier half — the `<client-id>` of
      `0.<client-id>.<secret>:<key>`, never the secret — and comparing it to the
      `client_id_sha256` field of the `mc_migrate_claude` row: **they agree exactly**. (The
      digest is deliberately not reproduced here; it is 16 hex characters and
      `check:ci-plan-citations` correctly reads such a token as a commit pointer.) So the
      row identifies the local token precisely, and that token is rejected. The row therefore describes the credential that is DEAD while CI runs on
      one that is recorded nowhere.
      **The fingerprint field exists to catch precisely this** ("so a token swapped without
      updating this file is reported") **and it cannot, because nothing reads it.** That is
      not an oversight: the same file settles it deliberately — "NO CI GATE READS THIS
      (`docs/ci-overhaul/08-driver-contract.md` sec 2)", on the grounds that an expired token fails loudly at
      every call site and a clock-driven gate reds the tree on a quiet day for a condition
      no commit caused. **I did not override that settled decision**, and the cost of it is
      now measured rather than argued: the drift was invisible for at least a day and was
      found by a probe, not by an instrument.
      **`bws-token-expiry.json` IS LEFT TRUTHFUL AS THE BOX REQUIRES** — the `expires` date
      is not edited forward, and no row is invented for the credential CI is really using,
      because this session cannot see it.
      **Door: `door:operator-only`.** Minting and rotating a machine-account token is the
      one thing no `bws` verb does (`.ci/lib/bws-env.sh:45-47`), and reading the live GitHub
      secret is outside this session's access.
      **THE CLASS WAS SWEPT, NOT JUST THIS INSTANCE, AND IT IS CLEAN.** The class is "a
      credential in a local config file goes stale when the credential is rotated
      externally". `find . -type f -path '*/.env*'` returns **12** files outside
      `node_modules`. **Zero need fixing.** Every one of the six holding real values is
      untracked AND gitignored (`packages/e2e-tests/.env` and `.env.groupb`,
      `private/account/.env`, `.env.bench` and `.env.pre-rename.bak`,
      `private/growth/apollo-companies/.env`); every one of the six that is tracked is an
      `.example` or `.template` of placeholder names, and `check:ci-tracked-credentials` is
      rc=0 over them. Only ONE other file carries a `BWS_ACCESS_TOKEN` at all --
      `private/account/.env.pre-rename.bak`, a 2026-09-02 backup -- and its client-id half
      digests to the SAME machine account, so it is a second copy of the one dead
      credential, not a second stale credential. **A first pass reported that backup as
      un-ignored, and that was a measurement error**: `git check-ignore` had been handed a
      path that did not exist relative to the directory it ran in, so it answered "no" about
      a file it never saw. `private/account/.gitignore:4` (`.env.*`) covers it.
      One observation, not a defect and not this session's to act on: that backup duplicates
      47 secret values into a second file inside a FROZEN submodule. Deleting it is the
      operator's call.
      **AND NO GATE WOULD HAVE HELPED — checked, rather than assumed, because the obvious
      instrument is a trap.** The tempting fix is a check that the recorded
      `client_id_sha256` still matches the token in `private/account/.env`. **It would have
      been GREEN through this entire incident**, because the fingerprint DOES match: the
      record names the right credential, and that credential is simply rejected. A gate
      written for this finding would therefore have been unable to catch this finding — the
      vacuity failure this programme exists to prevent, shipped in the name of fixing it.
      The only in-tree signal is the `expires` DATE, which nothing but a clock can read as
      past, and a clock-driven gate is exactly what
      `docs/ci-overhaul/08-driver-contract.md` sec 2 rejected on the grounds that it reds
      the tree on a quiet day for a condition no commit caused. **That settlement survives
      contact with the incident it appears to have missed, so it is left standing and this
      paragraph exists so the next session does not re-litigate it and build the green
      gate.** The one premise of it that IS refuted — "an expired token already fails loudly
      at every call site" — fails only for call sites that never ran: nothing local invoked
      `bws` between the expiry and this probe, so there was no loud failure to hear.
      **Per-wave fallback now in force, exactly as the box specifies:** W8 P1 and W8 P5
      STOP; W8 P2, P3, P6, W8 P4 and all of W4 CONTINUE — they are static analysis over
      tracked text. Two thirds of T-ENV is credential-free by construction.
- [x] **W0.0-B S, GENUINELY OPERATOR-BLOCKED** Mint `mc-ci-read`, `mc-rotate`, `dev-shared`. No
      `bws` verb mints a machine-account token; it is web-vault only. `mc-ci-read` has one tracked
      occurrence, as prose in a `"replacement_plan"` string. **Acceptance:** three `tokens[]` rows
      whose `used_by` values PARTITION -- today's single row claims `read-write` for local, ci and
      cd at once, and that concentration IS the outage risk.
      **`mc_migrate_claude` expires 2026-09-08, tomorrow. No gate reads the expiry file, by
      deliberate decision, so nothing will red -- every call site simply starts failing.**
      **DISCOVERED 2026-09-09 AGAINST THE LIVE VAULT, at the operator's instruction.** Both CLIs
      are on PATH (`bws` 2.1.0, `bw` 2026.8.0) and `~/.bw-session` is UNLOCKED against
      vault.bitwarden.com, so this was measured rather than reasoned about:
      * **"Web-vault only" is CONFIRMED for both tools.** `bws` has exactly six verbs --
        `config`, `completions`, `project`, `secret`, `run`, `help` -- and no service-account
        verb; `bw` exposes only `move`, `confirm`, `share` and `device-approval` for
        organisations. Neither can mint a machine account. The box was right.
      * **`mc_migrate_claude` NO LONGER EXISTS**, so the expiry clause above is spent: the
        operator replaced it on 2026-09-09 with `local-rw-account` (never expires) and
        `ci-readonly-console`. The registry's `client_id_sha256` for `local-rw-account`
        **MATCHES** the live token, recomputed the way `scripts/ops/bws-map-refresh.py:83` does
        it -- over the CLIENT-ID half, not the whole token, which is what a naive `sha256sum`
        of the token gets wrong.
      * **`dev-shared` IS A PROJECT, NOT AN ACCOUNT, AND THERE IS EXACTLY ONE PROJECT:**
        `ci-shared` (its uuid is not quoted here: the tail of a uuid is commit-shaped and
        `check:ci-plan-citations` reads it as a dead object pointer -- run `bws project list`).
        All **58** secrets sit in it, and
        `.ci/config/bws-secret-map.json` agrees at 58.
      **SO THE BOX'S REAL FINDING IS SHARPER THAN ITS TEXT, and the account split does not
      reach it.** The token concentration IS reduced -- local is read-write, ci and cd are
      read-only, and the `used_by` values partition across two rows. But PROJECT separation
      does not exist: one project holds everything, so the CI credential can read all 58
      secrets including `ACCOUNT_ED25519_PRIVATE_KEY`. Read-only narrows what a leaked CI token
      can DO; it does not narrow what it can SEE. A `dev-shared` project is the only thing that
      does, and creating it is web-vault work.
      **`ci-readonly-console`'s fingerprint is unknowable from here BY CONSTRUCTION** -- it
      exists only inside the GitHub secret `BWS_ACCESS_TOKEN`, which no session can read -- so a
      silent swap of the CI credential cannot be detected by this repository at all.
      **CLOSED BY OPERATOR DECISION 2026-09-09, not by work.** Asked directly, they ruled:
      *"Currently, we only have single project and multiple tokens: dev can R/W and ci is
      read-only. I'm fine with that. I can think about the dev separation later."* So the
      target shape is ONE project, `ci-shared`, with the two existing machine accounts --
      `local-rw-account` (read-write, never expires) and `ci-readonly-console` (read-only) --
      whose `used_by` values already partition. Nothing is minted.
      **THE ORIGINAL SHAPE WAS IMPOSSIBLE ANYWAY**, per bitwarden.com/help/projects: *"Each
      secret can only be associated with a single project at a time."* Binding all 58 to a
      second project so nothing breaks would have MOVED all 58 out of `ci-shared` and taken
      CI's access with them. Access is per-project and multi-valued; membership is not.
      **NOT CLOSED BY THIS:** one project means the read-only CI credential can still SEE
      every secret it reaches, `ACCOUNT_ED25519_PRIVATE_KEY` included. Read-only narrows what
      a leaked CI token can DO, never what it can SEE. Ready-to-run steps are kept at
      `agent/f4da5c2e/BITWARDEN-dev-shared-prompt.md` for whenever this is revisited.
- [x] **W0.1 S, blocked on W0.0-B** Cut over by fingerprint.
      **CLOSED 2026-09-09 WITH W0.0-B: there is no cutover to make.** This box moves CI onto
      a newly minted account by fingerprint; the operator ruled the two existing accounts are
      the final shape, so it has no subject. The fingerprint fact worth keeping:
      `local-rw-account`'s `client_id_sha256` in `.ci/config/bws-token-expiry.json` MATCHES
      the live token when recomputed the way `scripts/ops/bws-map-refresh.py:83` does it --
      over the CLIENT-ID half, which a naive `sha256sum` of the whole token gets wrong.
      `ci-readonly-console`'s stays `null` by construction: it lives only inside the GitHub
      secret, so a silent swap of the CI credential remains undetectable from here.
      **Original acceptance, for the record:** a dispatched workflow
      prints `sha256(client-id)` truncated to 16 hex and it equals the `mc-ci-read` row.
      Greenness is explicitly not the acceptance -- old-token-green and new-token-green are
      indistinguishable. Red first: dispatch before the swap and assert it prints
      the OLD fingerprint, i.e. the `client_id_sha256` that
      `.ci/config/bws-token-expiry.json` records for `mc_migrate_claude`. Cite the file,
      not the value: the value changes at the cutover, which is the whole point.
- [x] **W4-D1 S** The `.ci/policy` contract has already drifted, **one day after the move**.
      `POLICY_FILES` holds 15 (`scripts/lib/policy-paths.ts:69-86`); the directory holds 16.
      `.language-policy-allowlist` is reached by a hardcoded join at `.ci/scripts/quality/check_language_policy.py:112`,
      bypassing the seam. **Acceptance:** three-way set equality -- directory == `POLICY_FILES` ==
      the Python name set. This box is the evidence that W4 P4b's inventory gate is load-bearing,
      not cosmetic.
      **CLOSED 2026-09-08, and BOTH halves were already fixed by the time this box was worked,
      which is worth recording rather than re-doing.** Set equality holds at 16 == 16 == 16 and
      `check:ci-policy-inventory` asserts it in all four directions, rc=0; the hardcoded join is
      gone, `check_language_policy.py` now reads `policy_path(".language-policy-allowlist", ROOT)`
      with the env override still in front of the seam (W4 P4a). **No second instrument was
      written**, per this box's own acceptance: W4 P4b's gate IS the instrument, and it was
      proven on the drift itself rather than trusted. Rebuilt in a scratch tree
      (`POLICY_INVENTORY_ROOT`, the real tree never written to) with the name deleted from the
      TypeScript list only, it exits 1 with exactly two findings, both naming
      `.language-policy-allowlist`: absent from `POLICY_FILES` while on disk, and the two seams
      disagreeing. **What was left was PROSE**: the comment landing beside the fix still said the
      name was "NOT added here" and that the gate "reaches it by a hardcoded literal", both untrue
      the moment they were written. Rewritten as history at `scripts/lib/policy-paths.ts:79-86`.
- [x] **W4 P4a S** Python `policy_path`. Five hardcoded literals (`.ci/rediacc_ci/quality/go_deps.py:178`,
      `.ci/rediacc_ci/quality/plan_housekeeping.py:238`, `.ci/rediacc_ci/quality/profiler_coverage.py:166`, `.ci/scripts/quality/check_language_policy.py:112/114`,
      `.ci/scripts/quality/check_runner_advice.py:899`). **Design constraint:** `.ci/scripts/test/gates/test-policy-path.sh:79` asserts the TS
      seam does "no stat, no readdir" and proves it with an `rmdir`. The Python twin must satisfy
      the same property, so `policy_path()` is a pure join and the inventory readdir is a SEPARATE
      instrument. Every env override stays in front of the seam.
- [x] **W4 P4b S** The inventory gate, four directions: nothing in the directory outside
      `POLICY_FILES`; nothing in `POLICY_FILES` missing from the directory (a deleted list reads
      as "nothing is suppressed"); Python == TypeScript; no literal joins outside the two seams.
      **The honest control:** run it against `5dfef7373` and assert it reds with exactly
      `{.language-policy-allowlist}`. A gate that cannot detect the drift that already happened is
      not the gate.
- [x] **W4 P4c C** The prose sweep gets a PREDICATE, absorbing the stale
      `scripts/gates/check-suppression-liveness.ts:61` comment ("Today POLICY_DIR is '' and this is a provable
      no-op", untrue since `dee3ade8b`). Rules: no comment may assert a `POLICY_DIR` value
      differing from `scripts/lib/policy-paths.ts:57`; no comment may cite a policy file by a root path.
      **P4a/P4b/P4c ALL DONE 2026-09-08, registered by the driver and green.**
      `.ci/rediacc_ci/policy_paths.py` is the Python twin and its purity is PROVEN the way
      `.ci/scripts/test/gates/test-policy-path.sh:79` proves the TypeScript one: `policy_path()` answers for an
      empty tmpdir and that tmpdir then `rmdir`s clean, so nothing was stat'ed, cached or
      created. I re-ran that myself. The default root is `paths.CI_DIR.parent`, a module
      constant, NOT `paths.repo_root()` -- the latter would `is_dir()` an env override on
      every call and break the very rule this box states. Differential against the
      TypeScript CLI over all 16 names: byte-identical. Five call sites migrated, and this
      box's citation of `.ci/scripts/quality/check_language_policy.py:112`/`:114` was off: the name operand is
      `:114`.
      **`check:ci-policy-inventory` registered and rc=0.** package.json, manifest.ts and the
      workflow region are the driver's, so the writer handed over a fragment and I applied
      it; `gate:bind --write` emitted `Policy inventory` into `quality-static` with
      `dropped` EMPTY -- asserted rather than assumed, because the A2 strip guard landed
      earlier today would have refused the write otherwise. 65 controls, 1.96 s against a
      10 s budget. `check:ci-gates-lock`, `check:ci-gate-bind`, `check:ci-parity`,
      `check:ci-gate-manifest` and `check:ci-gate-reachability-coverage` all rc=0 after.
      **THE HONEST CONTROL RAN, and it needed a technique this box did not anticipate.**
      `git archive` is useless here: `.gitattributes:55` is `* export-ignore`, so an archive
      of any commit is ONE file. A detached index -- `GIT_INDEX_FILE=... git read-tree
      5dfef7373` then `checkout-index --prefix` -- touches neither worktree nor real index.
      Against that tree the gate reds naming exactly `{.language-policy-allowlist}`, which I
      reproduced independently before accepting it.
      **24 mutants, SIX survived the first pass**, each resolved rather than carried -- one
      resolution was to DELETE the `SEAMS` exemption, because removing it changed nothing
      measurable. A refusal the writer had added (`candidates == 0`) was also deleted as
      unreachable and replaced with one that can fire.
      **Debt is printed every run rather than hidden:** 13 shell literal joins (bash has no
      seam and the twins are frozen until W7 P5) and one named exemption at
      `scripts/ci-runner/manifest.ts:1726`, a repo-relative `paths:` selector that the
      absolute seam would break `--changed` for.
- [x] **W4 P5 C -- REFUSE, and record the refusal** `bws-secret-map.json` fails three of the four
      `.ci/policy/README.md` clauses: it carries `refreshed_at` and is regenerated wholesale
      (clause 1); it has zero BLOCKER lines and a per-UUID reason would be invented (clause 2);
      and `.github/actions/bws-secrets/action.yml:71` builds the path from `github.action_path`
      with two more readers in `private/account`, so its location is an EXTERNAL CONTRACT
      (clause 4). That is a worse case than the one used to keep `language-policy-baseline.json`
      out. **Record it as README section 5 with a mechanical assertion** -- the file exists, is not
      under `.ci/policy/`, and contains zero `BLOCKER:` occurrences, so if someone ever adds
      reasons the decision reopens loudly.
      **DONE 2026-09-09 as README section 6**, not 5: another writer landed a section 5 the
      same day and I told this one to renumber ITS OWN rather than theirs, since theirs was
      first. All FOUR clauses were re-verified against the tree rather than copied from the
      box, and three of the four fail as it says: `refreshed_at` at
      `.ci/config/bws-secret-map.json:12` and wholesale regeneration (clause 1), zero
      `BLOCKER:` lines with a grep CONTROL proving the pattern finds a planted one (clause
      2), and `.github/actions/bws-secrets/action.yml:71` building the path from
      `github.action_path` with two more readers in the submodule (clause 4). Clause 3
      passes.
      **The mechanical assertion is live in `check:ci-policy-inventory`**, and one arm of it
      was UNREACHABLE on first draft -- a `startswith` over two module literals that could
      never fire -- so it was rewritten to test the filesystem and both halves now reach.
      That is the same class as the `candidates == 0` refusal that file already records
      deleting.
- [x] **W4 P3a-d** One blocker validator. Corpus DONE and registered
      (`test-blocker-golden-corpus.sh`, 20 cases, 7 of them verbatim reasons from live
      allowlists). Three live implementations remain plus one vendored, none collapsed; the TS is
      an INDEPENDENT port with its own pattern lists and a hand-sync comment, not a client.
      **P3d, the invariant-8 half:** "subset" is NOT "verdicts agree" -- two recorded divergences
      go the wrong way because the vendored copy has no substring list. The provable claim is
      about the LISTS: `bp_phrases ⊆ canonical_phrases` and `bp_substrings == ∅`, which DERIVES
      the two divergences instead of leaving them unexplained. Read the file read-only, parse its
      arrays, and **assert the gate's own innocence**: sha256 before and after the gate body, both
      equal to the `MANIFEST.sha256` row. Perturb only a temp copy.
      **P3a/P3b/P3d DONE 2026-09-09; P3c, THE COLLAPSE, IS NOT AND IS THE REAL REMAINDER.**
      Three of this box's claims did not survive measurement. The Python canonical it says is
      missing ALREADY EXISTS (`.ci/rediacc_ci/core/allowlist.py`, 525 lines, with a
      byte-compatibility corpus), so P3b is effectively done. The subset claim it calls "the
      provable one" is ALREADY ASSERTED at
      `.ci/scripts/test/gates/test-breakpoint-portability.sh:357-441`, with a planted-defect
      regression, so it was not re-asserted.
      **What was genuinely missing became `check:ci-vendored-blocker-derivation`:**
      `bp_substrings == the empty set` (asserted nowhere), and the DERIVATION of the corpus's
      "exactly five divergences" -- a magic number that said which COUNT and never which
      five, so it could not see one row leaving as another arrived. All five are now derived
      and attributed: three to a dropped phrase, two to the empty substring list.
      **Two defects its own controls caught that would have shipped green:** the corpus
      heredoc anchor matched nothing (parsing to ZERO rows, caught only by the refusal), and
      a test asserted a tally on the wrong stream because `Checker` prints to stdout while
      `rediacc_ci.log` writes every level including `success` to stderr.
      **P3c remains, and one gap should go with it:** nothing asserts a phrase present in the
      BASH or TS list but absent from the Python canonical, because
      `.ci/rediacc_ci/tests/test_core_allowlist.py:370` generates its corpus FROM the Python list, making that
      direction structurally invisible.
      **P3c DONE 2026-09-09, so the box is complete. THE BOX SAYS FOUR IMPLEMENTATIONS AND
      THERE ARE SEVEN**, and `.ci/rediacc_ci/core/allowlist.py:9-19`'s own docstring named a
      different four from the ones that are live. Two were named by nothing at all:
      `.ci/rediacc_ci/quality/swallowed_failures.py:450-600` (a fifth, -145 lines on
      collapse) and `.ci/scripts/quality/check_language_policy.py:262` (a seventh).
      Five collapsed onto the canonical; the vendored `.ci/breakpoint/` copy was never
      opened for writing and its sha256 still matches `MANIFEST.sha256`.
      **ONE IS DELIBERATELY NOT COLLAPSED AND THE BOX NAMES THE WRONG FILE FOR IT.** The
      live one is `.ci/rediacc_ci/quality/plan_housekeeping.py:427`, not the retired bash
      twin the box cites; its three differences (a 40-char floor, one reason per entry, a
      blank line that does not reset) are asserted AS differences by
      `.ci/rediacc_ci/tests/test_quality_plan_housekeeping.py:267,277`, so averaging them
      away would change that gate's verdicts. Pinned by an exemption test.
      **THE INVISIBLE DIRECTION IS NOW CAUGHT BY CONSTRUCTION, and it was real:** planting
      `+ 'PLANT'` into the TS normaliser reds **163 differential cases** in the new suite
      while `test_core_allowlist` stays 53/53 green. Live TS drift was invisible to the
      golden suite. `.ci/rediacc_ci/tests/test_blocker_implementations.py`, 12 tests, 225
      differential cases, verified by me at 65 passed alongside the golden suite.
      **Byte compatibility held throughout:** old vs new bash over a 5-entry fixture,
      streams separate, `CI=true` and unset -- stdout and stderr byte-identical in order.
      **Two defects its own controls caught.** `((${#_blocker_ref[@]} == 0))` killed
      `audit.sh` outright: `declare -A X` with no initialiser leaves the array UNSET, and
      reading its length through a nameref trips `set -u` where `${!X[@]}` does not -- so
      the anti-vacuity guard fired on the one input it was written for, the finish-line trap
      again. And an unframed-output bug replaced every rejection message, caught by a
      message digest rather than a verdict.
      **F1, repaired forward and not asked for:** `aaba93b29` routed 81 entry points through
      `import _cipath`, found only via `sys.path[0]`, so
      `.ci/scripts/test/gates/test-language-policy.sh:414,424` -- which copies the gate to a
      tmpdir -- died `ModuleNotFoundError` and its COMPOSITION TRAP control was asserting on
      a traceback. Two previously unreachable assertions now run.
      **F3 recorded, not removed:** `check_language_policy` shells to `blocker-validator.sh`
      which now shells back to Python, so the path is Python -> bash -> Python. The shell-out
      is what its "validator cannot be consulted" refusal exercises, so removing one half
      without the other deletes a live control; pinned by an assertion naming both.
      Cost: `gate-test:blocker-validator` 0.64s -> 5.3s against a 20,000 ms budget, no tier
      change, `check:ci-gate-manifest` green at 479 entries.
- [x] **W8 P1a S, ONE writer** Prove irreducibility as a SET. **The drain largely already
      happened**: `check-workflow-gates.sh` CHECK 2 enforces all four directions (`:258`,
      `:270-288` recording a 57-declaration sweep, `:336-345`) with a liveness arm at `:302-305`,
      registered at `scripts/ci-runner/manifest.ts:2537`. Residue: 13 files mentioning `workflow_call`, **2 distinct
      secret names**, 14 caller passthroughs all `BWS_ACCESS_TOKEN`, **zero `secrets: inherit`**.
      **New content:** assert `DECLARED_UNUSED_OK` is exactly the set of names pinned alive by
      `.github/external-callers.yml` -- today that justification is a comment and the registry
      does not know about it.
      **DONE 2026-09-09, and for once the box's numbers reproduce exactly**: 13 workflows
      mention `workflow_call`, 2 distinct secret names, 14 caller passthroughs all
      `BWS_ACCESS_TOKEN` across 18 call sites, ZERO `secrets: inherit`. One path correction:
      the gate is `.ci/scripts/security/check-workflow-gates.sh` and its manifest entry is at
      `scripts/ci-runner/manifest.ts:2713`, not `:2537`.
      Arm (a3) shipped: set equality between `DECLARED_UNUSED_OK` and the pairs pinned alive
      by `.github/external-callers.yml`, both directions, plus a blind-refusal when the
      registry declares no callers. Mutation-proved: `if False: pass` reds 4 of 5 cases, and
      the 5th is the stand-down control that correctly asserts absence.
      **A DEFECT THE FIRST PLANT EXPOSED:** draining the exemption list to empty left `{}`,
      an empty DICT, and arm (a3) died with a TypeError while `in` and `sorted()` above it
      degraded to matching nothing. Now a list converted to a set, with a duplicate refusal.
      **Also fixed in passing: CHECK 5 was VACUOUS-AND-GREEN**, printing "asserted nothing
      (this is the vacuous case, not a pass)" and then exiting 0. It now exits 1 and names
      the ten jobs in the set.
- [x] **W8 P1b S** The one genuinely removable declaration
      (`claude-review-reusable.yml` / `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`). Three commits,
      **submodule-first**: `private/account`, then `private/renet`, then the console commit
      deleting the declaration, the `DECLARED_UNUSED_OK` member and both `external-callers.yml`
      entries together. **Acceptance:** the gate green with `DECLARED_UNUSED_OK` EMPTY, and its
      liveness arm proving the exemption was retired rather than left dangling.
      **DONE 2026-09-09, and this box was about to CEMENT A LIVE OUTAGE.**
      Its premise -- that the passed secret is unused because the consumer fetches from
      Bitwarden now -- is FALSE. `.github/workflows/claude-review-reusable.yml:343` reads
      `env.BWS_ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, and the step that sets it is guarded on
      `github.repository == 'rediacc/console'`. In a REUSABLE workflow `github.repository` is
      the CALLER's repo, so for `rediacc/account` and `rediacc/renet` that step never runs and
      the token is EMPTY. `7343ae9dc` (2026-09-05) flipped the consumer from `secrets.` to
      `env.` and left the guard behind, so both repos have been reviewing with a blank
      credential since. The secret was unread not because their half of the migration landed
      but because it was never written, and deleting the declaration would have made that
      permanent. The stale comment two hundred lines up still called the fetch a SHADOW RUN
      "that nothing consumes", three days after it started consuming.
      **FIXED, not deleted:** the consumer now reads
      `env.BWS_... || secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, which restores the read for
      both callers, and THAT is what makes the exemption genuinely removable. Drained to
      `[]`; `check:ci-workflow-gates` rc=0 with `arm (a3): 0 declared-unused exemption(s) == 0
      pinned alive`. The box's other instruction -- delete both `external-callers.yml` entries
      -- would have emptied `callers:`, which two checks treat as BLIND; only the two
      `passes_secrets` rows may go.
- [x] **W8 P2 S, largest box in T-ENV** The env manifest. **Do not quote 1,014** -- it is not
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
      **DESIGN 2026-09-08: 745 DOES NOT REPRODUCE EITHER, and the box should ship with NO
      number at all.** Implementing the box's own stated method gives **721 over tracked
      files / 777 over everything on disk**, and not one of the five component counts
      reproduces (env files 89 -> 43, `process.env` 171 -> 200, `os.environ` 254 -> 240,
      workflow keys 308 -> 304); only vault=58 holds. The 56-name swing is entirely
      gitignored `.env` files, including one developer's `.env.pre-rename.bak`. **A manifest
      whose size depends on whether a stray backup is present is not a manifest.** The box's
      own last sentence is the right design -- ship the derivation SCRIPT -- and it is
      contradicted three lines earlier by calling 745 a receipt with a date. Strike the
      number; declare the corpus as TRACKED FILES ONLY, for the same reason PRE-A0's resolver
      answers from a tracked path set. **Hard predecessor the box does not name: PRE-A1 /
      W1P4**, or the new package acquires a `sys.path` hop W1P4 then has to remove. The
      acceptance also needs a per-source non-zero floor: a reader that stops matching empties
      one of five sets and every existing clause still passes.
      **DONE 2026-09-09, registered as `check:ci-env-manifest`, rc=0 with 26 controls, and
      all four set-arithmetic clauses printed as arithmetic on every run:**
      `sources \ shards = 0`, `shards \ sources = 20 = |tombstones|`, live-shard overlap 0
      over 21 pairs, `tombstones & sources = 0`.
      **NO COUNT IS WRITTEN DOWN, which is the acceptance this box actually asked for.**
      Today's union is **788** and I verified myself that the string appears ZERO times in
      either authored file; a test derives today's totals and asserts their absence.
      **745 does not reproduce and neither does the design note's 721/777.** Per-set today:
      env files 43 (box: 89), workflow keys 305 (308), `process.env` 205 (171),
      `os.environ` 304 (254), vault 58 -- the only one that holds.
      **The largest single correction: the `os.environ` reader must PARSE, not grep.**
      Across 559 tracked `.py`, AST finds 304 names and a regex 257; **55 are AST-only**,
      including `REDIACC_CI_ROOT` itself, written at `.ci/rediacc_ci/paths.py` as
      `os.environ.get(ROOT_ENV)`. A manifest of environment seams that omits the canonical
      environment seam is what the regex form produces. And the regex is not a safety net
      but eight FALSE positives, four of them fixture names inside the peer's in-flight
      W8 P6 file, which would have coupled this manifest to another writer's fixtures.
      **`tombstones ∩ sources == ∅` is false as the box states it**, because a file whose
      job is to name dead variables mentions them. Handled with `tombstone_proof_sites`
      keyed on the exact (path, name) PAIR, never a whole file, liveness-checked both ways.
      **A control that did not fire, and it was a real bug:** the collision authority
      matched by plain substring, so repointing `DEBUG`'s authority at a file naming
      `REDIACC_DEBUG` still passed -- any file mentioning the REPLACEMENT satisfied the
      check for the RETIRED name. Word-bounded, both directions controlled.
      **One name genuinely resists the eight shards and no ninth was invented:** `DEBUG` is
      a CLI tombstone AND the npm `debug` package's variable, live in
      `packages/e2e-tests/.env.example`. Two variables sharing a spelling, recorded in a
      `collisions` block printed on every run.
- [x] **W8 P3 S** Generators plus one regenerate-and-diff gate, adopting the existing
      `gen:docs` provider pattern rather than inventing one. Emitter and parity gate in the same
      change (invariant 1). Re-key `doc-registry-preport.json` for any moved key string.
      **NOT DONE 2026-09-09, and the reason is structural rather than effort.** All three
      artifacts were probed. `.env.example`: the only candidate is `private/account/.env.example`,
      which is untracked, gitignored and inside a submodule -- a regenerate-and-diff gate over
      that is the same trap W8 P2 already refuses. The docs table: it IS the `env-manifest`
      gen-docs region, and this plan says at `W11 P5c` that the region has no home until W8 P2
      exists; confirmed against the tree, 6 providers and no env/secret one. The local
      allowlist: `scripts/gates/check-secret-scope.ts:85-90` is four hand-reasoned names whose source
      is `gh api`, not the tree, so it is not derivable.
      So P3 reduces to "generate the thing W8 P2 defines" and is blocked on it. The writer
      stopped rather than inventing a substitute provider, which is what the box asks for.
      **DONE 2026-09-09 once W8 P2 unblocked it, exactly as this annotation predicted.** The
      `env-manifest` region is live in `scripts/data/doc-registry.md` at **808 rows** -- the
      manifest's 788 live names plus 20 tombstones -- one row per variable NAME and never a
      value. `check:ci-doc-region-parity` rc=0 and covers it in all three clauses, so **no
      second parity mechanism was built**; the existing gate test picked it up with no edit.
      **BOTH REFUSED CANDIDATES STILL REFUSE, AND BOTH OF THIS BOX'S STATED REASONS WERE
      WRONG.** On `.env.example`: the box says the only candidate is
      `private/account/.env.example`, "untracked, gitignored and inside a submodule".
      Measured -- there are FOUR on disk, TWO are tracked in console
      (`packages/e2e-tests/.env.example`, `packages/www/.env.example`), and
      `git check-ignore -v` returns nothing for any of the four, so **none is gitignored**.
      The real reason to refuse is stronger than the stated one: all three tracked
      `.example` files are already derived and held faithful in both directions by
      `check:ci-env-manifest`, so a regenerate-and-diff over them is a DUPLICATE mechanism.
      The box never mentions `packages/cli/.env.test.example` at all.
      On the allowlist: `scripts/gates/check-secret-scope.ts:85-90` is still four hand-listed
      names, and two of them -- `BREAKPOINT_TUNNEL_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` -- are
      **not in the manifest at all**, because they appear only as `secrets.NAME` references
      whose env keys are the longer `CLOUDFLARE_`/`ANTHROPIC_` spellings. Not derivable, and
      org-vs-repo scope is a GitHub setting the tree cannot see.
      **No preport re-keying was needed** and none was done: diffing the verdict sets with
      and without the provider adds exactly one line, `env-manifest`, and moves no existing
      key. (`--diff-snapshot` is rc=1 on this tree independently of the change and is wired
      to no gate.)
      **A sorting bug it caught in itself:** sorting the RENDERED cell is not sorting the row
      KEY -- `` `AWS_SES_ACCESS_KEY_ID` `` and `` `AWS_SES_ACCESS_KEY_ID_ASIA` `` REVERSE
      once wrapped in backticks, because U+0060 > U+005F.
      **A lint red it fixed on the way, caused by the provider U1 landed hours earlier:**
      `jsonTokens` used `\u0000` as its wildcard sentinel, which is a control character
      inside a regex literal, so `check:lint:tooling` reported `no-control-regex` twice.
      Now a private-use `HOLE = '\uE000'` with `replaceAll`, and `json-inventory` still
      renders 54 rows byte-identically.
- [x] **W8 P4 C, cheapest real win** The cure is call-site adoption, not new code.
      `core/env.py` is DONE and PROVEN against a LIVE `set -a; source` in a subshell
      (`.ci/rediacc_ci/tests/test_core_env.py:74-105`, `:434`), with a `python3 -m rediacc_ci.core.env` CLI -- and
      **zero production importers**. `bws_env_load` likewise has zero callers. Both orphaned.
      **Seven sites with a disposition each:** `.ci/config/constants.sh:22` STAYS bash (sourced before Python
      is guaranteed; bootstrap circularity) until W6 P3; `.ci/lib/account.sh:438` and `:791` retarget;
      `.ci/scripts/lib/toolchain.sh:34` is bootstrap-sensitive, measure first; `.ci/legacy/run-legacy.sh:185` **do not
      retarget** (W6 P5 deletes it -- record the decision so it is not re-found and mistaken for a
      miss); `scripts/ops/deploy-bench.sh:137` retarget before W9 P2 moves it;
      `programs/backup-storage/start-local-plane.sh:60` retarget -- its own comment at `:57-59`
      already reasons about precedence, the best demonstration that the rule is real.
      **Out of scope in writing:** `private/growth` (gitignored separate checkout) and
      `packages/cli/templates/**` (shipped content that runs on remote machines with no
      `rediacc_ci`; retargeting would be a product regression).
      **Acceptance per site:** set one of the file's names in the environment to a DIFFERENT value
      and assert the shell value survives -- under `set -a; source` the file wins and it fails.
      **WORKED 2026-09-09, NOT LANDED: it collides with ruling 7 and I unwound my own
      registration rather than suppress the gate.** The seven call sites reproduce exactly,
      four were retargeted onto a new `env_file_load` shim, and the acceptance is genuinely
      runnable -- CHECK B EXECUTES each adopted site's own line against a fixture with a
      conflicting value already in the environment, and CHECK C runs a real `set -a; source`
      on the same fixture demanding the OPPOSITE answer, so CHECK B cannot pass against a
      helper that reads nothing.
      **But the work adds TWO NEW TRACKED `.sh` FILES under `.ci/`**, and ruling 7 makes
      `.ci` and `.claude` single-language: `check:ci-language-policy` went rc=1 with
      `2 NEW bash file(s)` the moment I registered them. I removed the package.json and
      manifest entries and returned both files to untracked; content is untouched and the
      tree is green again. **To land, the gate must be Python** (`check_env_file_adoption.py`),
      and `env-file.sh` needs an explicit allowlist decision, because a bash shim for bash
      callers cannot itself be Python. Recording that rather than quietly allowlisting it.
      One good catch inside the work: `deploy-bench.sh` needed its load order INVERTED,
      because `set -a; source` gives the win to the LAST value and `env_file_load` gives it to
      the FIRST -- backwards, and bench ships the production `AWS_SES_*`.
      **LANDED 2026-09-09 as `check:ci-env-file-adoption`, rc=0, registered and bound
      (`dropped` empty; `check:ci-gate-bind`, `check:ci-parity`, `check:ci-gate-manifest`,
      `check:ci-gates-lock` all rc=0).**
      **Ruling 7 was resolved by ADDRESS, not by allowlist, and the box did not consider
      this option.** `check_language_policy.COVERED_ROOTS` is exactly `(".ci", ".claude")`,
      so the bash shim moved to `scripts/lib/env-file.sh` and needs no exemption at all. It
      is also the better description of the thing: two of its three callers,
      `scripts/dev/deploy-bench.sh` and `programs/backup-storage/start-local-plane.sh`, were
      never under `.ci` to begin with. The gate itself is Python
      (`.ci/rediacc_ci/quality/env_file_adoption.py`) with its entry point at
      `.ci/scripts/quality/check_env_file_adoption.py`. **No allowlist entry was added
      anywhere**, and the predecessor's four exemptions are now three — the bash gate had to
      exempt ITSELF because it wrote `set -a` fixtures into its own source; a Python gate
      writing the same fixtures is not swept, so that exempted surface is genuinely gone.
      **THE PLANT ON THE REAL TREE FOUND A HOLE IN THE MATCHER, and the selftest agreed with
      the bug.** Reverting `scripts/dev/deploy-bench.sh` to `set -a; . "$f"; set +a` in the
      live tree and running the REGISTERED gate reds — but only CHECK B fired. **CHECK A, the
      sweep, said nothing**, because the trailing boundary was `(?:\s|$)` and a `;` binds
      directly onto the `-a`. So the single most likely spelling of the exact thing this gate
      exists to prevent was unmatched, along with `set -a|`, `set -a&&` and `(set -a; . f)`.
      Inherited verbatim from the bash predecessor. All three original control fixtures used
      spellings the pattern already matched, which is why eight green controls proved nothing
      about it. The boundary is now a lookahead over the shell separators and the control
      drives **seven** spellings.
      **The widened sweep immediately found a real site outside all three named roots:**
      `.claude/oracles/pre-bash/block-host-toolchain-run.sh:111` — a guard that blocks unsafe
      uploads while ADVISING `set -a; . private/account/.env; set +a`, on the file holding
      ACCOUNT_ED25519_PRIVATE_KEY and ACCOUNT_JWT_SECRET. Fixed as a class, not an instance:
      the advice now names the shim in the bash oracle AND in its Python twin
      `.claude/rediacc_hooks/guards/block_host_toolchain_run.py:305`, with a new control in
      `test-block_host_toolchain_run.py` asserting the advised form is ACCEPTED — the message
      and the predicate live in different functions and nothing else held them together.
      24 cases, 0 failures; `check:ci-host-toolchain-coverage` rc=0.
      **A DOCSTRING CLAIM CORRECTED, inherited from the predecessor:** the sweep is described
      as covering ".ci/, scripts/, programs/ or the repo root" and is in fact REPO-WIDE. A git
      pathspec without `:(glob)` matches with FNM_PATHNAME off, so the `*` in `*.sh` crosses
      `/`. Measured: `git ls-files '*.sh'` is **621** against **514** for the three directory
      globs combined. Left repo-wide deliberately — the first thing the widened matcher caught
      was in `.claude/`.
      **`.ci/scripts/lib/toolchain.sh` was NOT retargeted** and its exemption stands: the box
      said "measure first", and `.ci/bootstrap.sh:76` calls `toolchain_load` as its first
      action on a host with no pip, no uv and no pytest — the same circularity as
      `constants.sh`. `.ci/legacy/run-legacy.sh` is exempt as the box directs, so W6 P5's
      deletion is not pre-empted.
- [x] **W8 P5** Spec + gate available NOW (the truncation target is the `machine-local` shard);
      **seeding OPERATOR-BLOCKED** on `dev-shared`, which has zero tracked hits.
      **DONE 2026-09-09. The spec and gate landed, and the blocked half is CLOSED BY THE
      OPERATOR'S SINGLE-PROJECT RULING** -- there will be no `dev-shared`, so there is
      nothing left to seed. `.ci/config/secret-supply.json` plus
      `.ci/rediacc_ci/quality/secret_supply.py`, registered as `check:ci-secret-supply` in
      `quality-static` and rc=0 on this tree.
      **THE BOX IS WRONG ABOUT ITS OWN TARGET.** "the truncation target is the
      `machine-local` shard" is not implementable: `private/account/.env` assigns **zero**
      names from that shard -- it holds `HOME`/`PATH`/`XDG_*`, and the manifest's own
      definition says nothing here sets them. The real terminal state is
      `BWS_ACCESS_TOKEN` + `BWS_ACCESS_TOKEN_ROTATE`, which is what the spec encodes as
      `bootstrap_names`.
      **The residue is 26 of 84**, derived as `env-manifest.shards.secret` minus
      `bws-secret-map.secrets`, set-equal in both directions, with a `dotenv` table of one
      destination per name. Six plants on the real tree, each with the clean copy proven
      green first, including the one that matters: **the seeding landing** reds with
      `RESOLVED` plus `FALSE DESTINATION`.
      **TWO FINISH-LINE TRAPS WERE FOUND AND REMOVED IN THE WRITING.** A bootstrap clause
      asserting equality with `["BWS_ACCESS_TOKEN"]` would red the day the residue drains;
      it is now a membership test with no lower bound. And a "kind defined but unused"
      finding would red when the last entry leaves -- that is what winning looks like, so it
      is printed, not asserted.
      **`STRIPE_E2E_WEBHOOK_SECRET` IS NOT A CREDENTIAL** and was queued as one until the
      evidence was read: `.ci/lib/account.sh:237` writes its literal fixture value in the
      clear and `.ci/rediacc_ci/core/secrets.py:148` already records it as a fixture.
      **14 of the 49 names in `private/account/.env` are in NO shard**, including four real
      admin credentials, so they are invisible to every existing gate. That is correct per
      the manifest's tracked-files-only design, and the new gate prints the number every run.
- [x] **W8 P6 S** Python env registry, shrink-only over a SET of `module:NAME` pairs, in
      `.ci/config/` (not `.ci/policy/`, per the clause-1 reasoning P5 re-applies).
      **The arm that usually goes missing:** deleting a baseline entry whose violation is still
      present must RED, so a baseline cannot be trimmed to escape the gate.

---

## T-DOCS

      **DONE 2026-09-09, registered as `check:ci-python-env-registry`, rc=0:** 445 pairs
      across 164 modules, 295 distinct names plus 19 opaque reads, over 563 tracked `.py`
      files, matching `.ci/config/python-env-registry.json` in BOTH directions.
      **The arm the box names is proven on the real tree in both directions.** Deleting an
      entry whose read persists reds as NEW with a message that says so in as many words;
      banking one no read backs reds as STALE. **And the escape hatch is closed:** a blanket
      `--write-baseline` REFUSES any reseed that would add a pair, because "a reseed that
      drains 30 and adds 1 has still added 1, and comparing totals is not the same claim as
      comparing sets". Growth needs a typed `--allow-new <module>:<NAME>`, itself validated
      against the derived set so it cannot pre-bank.
      **Placement confirmed by reading clause 1, not by taking it on faith:** this file is a
      MEASUREMENT, generated wholesale with no BLOCKER reasons and none possible, so it
      fails `.ci/policy/README.md`'s clauses 1 and 2 exactly as `language-policy-baseline`
      and `tracked-credentials-baseline` do, and sits beside them in `.ci/config/`.
      **"Every variable each module reads" is not answerable by matching literals:** 124
      read sites hold the name in a variable, and constant resolution recovers 87 pairs a
      literal scan cannot see (339 -> 426). Ambiguity is nulled deliberately, because a
      WRONG resolution enshrines a pair the code never reads and the STALE arm then fires on
      an entry the author cannot find.
      **Pure shrink-only is not implementable and the box is wrong to imply it is:** the
      terminal state "no Python module reads the environment" is unreachable, since
      `rediacc_ci.paths` reads `REDIACC_CI_ROOT` to find the repository at all. A clause
      that can never be satisfied is one that gets suppressed.
      **Three defects its own plants earned, all inside its files:** `os.getenv` was
      invisible (an `ast.Attribute` whose receiver is `os`, not `os.environ`) and has ZERO
      live subjects, so only a fixture reaches it -- which is exactly why it needed a
      control; `del os.environ[X]` counted as a read at 34 sites; and `--write-baseline`
      WROTE the file and then refused, leaving the rejected reseed on disk.
- [x] **X0.1 S, do first** Fix the A5/A6 collision in the plan text and adopt PREFIXED decision
      ids (`D-A6`, `G-A5`). Three schemes collide today: `G-A5`/`G-A6` are gate rules at
      `.ci/scripts/quality/check_plan_boxes.py:41`/`:42-44`; `04-decisions.md` section A item 6 (`:22-23`) is the
      operator override licence. P2.7's subject is the gate rule; P3.2's is the decisions doc.
      **DONE 2026-09-08, and adopted AT THE SOURCE rather than as a prose convention.**
      `.ci/scripts/quality/check_plan_boxes.py` now labels its own rules `G-A0..G-A6`
      (70 occurrences relabelled; the only bare `A5`/`A6` left in that file are inside the
      new header comment, where they are quoted as the retired ambiguous form). Operator
      rulings are `D-A<n>`. A future box copying an id from either place therefore copies
      the prefix, so the collision cannot recur by transcription -- which is how it
      happened: W12 P2.7 cited "A5 in `04-decisions.md`", a file where that token does not
      appear at all. `check:ci-plan-boxes` and `check:ci-python-lint` both rc=0 after.
- [x] **W11 P4a C** `policy` provider + region replacing `.ci/policy/README.md`'s hand-typed
      section 2, whose heading literally reads "fifteen" against 16 files on disk.
      **Acceptance:** two-direction set equality, key set == `ls .ci/policy` minus README ==
      `POLICY_FILES`. **It is RED on landing**, which surfaces W4-D1 structurally; this box does
      not fix it, it hands the one-line addition to that box as a fragment.
      **Do not derive the Readers column by grep** -- `scripts/lib/doc-providers.ts:568-583` records that a
      grep-derived Readers column flipped mid-run on 2026-09-06 and forbids re-adding it.
      **DONE 2026-09-09, and TWO OF THE BOX'S THREE CLAIMS ARE DEAD.** The heading it says
      reads "fifteen against 16 files" is wrong by three: there are **18** (16 dotfiles + 2
      JSON). And "it is RED on landing, which surfaces W4-D1 structurally" is FALSE today --
      W4-D1 landed hours earlier, both seams hold 18, and the provider renders GREEN with all
      18 rows `both`. **There is no one-line addition to hand W4-D1**; the drift it was meant
      to surface is already fixed.
      Equality is rendered in BOTH directions: a name in a seam with no file gets its own
      `NO FILE ON DISK` row, because absence is exactly how that failure hides.
      **A PARSER DEFECT THE FIRST RENDER EXPOSED:** `pyPolicyNames` used a non-greedy
      `\(([\s\S]*?)\)` and stopped at the first `)`, which sits inside a per-entry comment
      saying `policy_path()`. Both JSON members came back as `ts only` against a seam that
      holds them. Both seam parsers are now terminated on a line-anchored delimiter.
- [x] **W11 P4b C** `test-split` provider + region in `07-port-brief.md`, rendering the residue as
      an explicit `(unregistered)` row. Non-empty is legal and visible; silence is not.
      **DONE 2026-09-09** as `docs/ci-overhaul/07-port-brief.md` section 6. The residue is
      **13 files**, all under `.claude/hooks`, reached only by a text reference from
      `test-hooks.sh` -- not a registry leaf, not a pytest root. Rendered ONE ROW PER FILE
      rather than as a count, because a count cannot see one file leaving as another arrives.
      **A DOUBLE-COUNT THE FIRST RENDER PRODUCED:** `testpaths` names
      `.ci/rediacc_ci/tests` and `.ci/rediacc_ci/tests/gates` separately and `git ls-files` on
      the parent returns the child, so the table read 169 + 78 against a real population of
      169 -- 78 files counted twice and the split inflated 46%. A file is now attributed to
      the LONGEST declared root containing it.
      **A finding the table cannot show because it is an absence**, so it went in the prose:
      `docs/ci-overhaul/08-driver-contract.md:43` arbitrates three pytest roots and names
      `.ci/tests/gates` as one. That directory holds ZERO tracked files and appears in
      NEITHER `testpaths` nor the orphan gate's `SEARCH_DIRS`. The arbitration was never
      implemented; what exists is `.ci/scripts/test/gates`.
- [x] **W11 P5a S** Providers `bootstrap`, `job-graph`, `media` with their regions, one commit.
      `scripts/gates/check-doc-region-parity.ts:22-30` makes invariant 1 automatic here: a provider without a
      region reds immediately.
      **DONE 2026-09-09. All three providers and all three regions are live**, verified by
      me rather than by the writer's report: `bootstrap` 5 rows, `job-graph` 22, `media` 6,
      each with exactly one region marker pair in `scripts/data/doc-registry.md`, and
      `check:ci-doc-region-parity` rc=0. Invariant 1 held automatically as the box predicts
      -- a provider without a region reds immediately -- and it fired for real during the
      wave when `plan-record-grammar` landed a region before its provider.
      **The regions live in `scripts/data/doc-registry.md`, NOT in CLAUDE.md, and that is a
      correction to P5b's arithmetic rather than a placement whim.** Measured: `media` is 5
      rows against a 14-line section (net 0), `job-graph` 21 rows against 16 lines
      (**net +14**), `bootstrap` 4 rows against 21 (net -6, not the -11 the plan budgets).
      **Providers COST lines where the plan assumes they save them**, so only a pointer
      saves anything, and P5b's 440-line target is unreachable with these regions inside
      CLAUDE.md.
      Two further providers landed in the same machinery afterwards and are recorded under
      their own boxes: `json-inventory` (U1, 54 rows) and `env-manifest` (W8 P3, 808 rows).
      The estate is now 14 providers, 14 registered, 14 region ids -- the parity gate checks
      that four ways and all four agree.
- [x] **W11 P5b S** The 140-line cut. **Session Defaults is lines 9-233 -- 225 lines, 39% of the
    (ticked) 2026-09-20T12:11:18Z by d778be9d: commit e82961be8: CLAUDE.md 363 lines / 32,293 bytes -> 326 lines / 30,696 bytes (limits 440 / 30,720); Session Defaults span byte-identical to HEAD (sliced and compared); CLI examples moved verbatim to docs/agent-reference/cli.md
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
      **STARTED 2026-09-09. 580 -> 540 lines, 36757 -> 33855 bytes.** `## Session Defaults`
      is still at 9 and `## Architecture` still at 234, so the frozen span has not moved.
      Remaining to acceptance: 100 lines and 3,135 bytes.
      **THE LOCKFILE SECTION IS CUT, 51 lines to an 11-line pointer -- AND CUTTING IT BLIND
      WOULD HAVE ORPHANED A CITATION.** `.ci/scripts/quality/check-lockfile.sh:69` said "For
      a real install check, use CLAUDE.md's clean-room recipe", so the enforcement pointed AT
      the prose being deleted and the recipe would have survived nowhere. The recipe now
      lives in `check-lockfile.sh` beside the limit it answers, and the pointer is
      self-contained.
      **THAT IS THE CLASS, NOT THE INSTANCE, AND THE NEXT SECTION HAS IT TOO.** Every
      "defensible source" in the list above needs its destination CHECKED before the cut, not
      after. Measured: `Release Channels` and the `7-day soak` promotion rule appear in **no
      file under `docs/`** -- CLAUDE.md is their only record, so that 7-line cut needs a home
      written first. `resolve-version.sh` and `bump.sh` are cited in
      `docs/ci-overhaul/06-progress.md` and `docs/ci-overhaul/01-verified-context.md`, so
      Versioning has somewhere to point.
      **And one source in the list needs building, not moving:** the `cli-commands` region
      (net 24) does not exist -- `scripts/gen-docs.ts` emits gates, hook-guards,
      suppressions, ci-tree, hook-summary, bootstrap, job-graph, media, json-inventory and
      env-manifest, and no `cli-commands`. The 137-line sum therefore includes 24 lines of
      provider work, which is why the reserve exists.
      **OPERATOR RULING 2026-09-09: "Cut only what already has a home."** So the target is NOT
      claimed and the box is NOT ticked. Landed **580 -> 520 lines, 36757 -> 32243 bytes**:
      the lockfile archaeology (51 -> 11), i18n and Local environment (43 -> 25 together) and
      Media Assets (14 -> 12), each trimmed to the pointer it already carried.
      **Acceptance clause 3 HOLDS and is verified rather than asserted:** the frozen span is
      byte-identical to HEAD, compared line 9 to 233 against `git show HEAD:CLAUDE.md`, and
      `## Session Defaults` is still at 9 with `## Architecture` still at 234.
      Clauses 1 and 2 do NOT hold: 520 > 440 and 32243 > 30720.
      **WHAT WAS DELIBERATELY LEFT, each checked against `docs/` first rather than assumed:**
      * **Versioning** -- `__CLI_VERSION__` appears in NO file under `docs/`, so the
        build-time injection table is its only record.
      * **CI/CD Pipeline** -- `release_mode` appears in NO file under `docs/`, so the
        dispatch line (and the fact that GitHub rejects `minor`/`major`) lives only here.
      * **Release Channels** -- neither it nor the 7-day soak rule appears anywhere in
        `docs/`.
      * **Common Commands** -- its `cli-commands` region does not exist yet.
      The three that WERE cut all already said "X carries the rest", and every load-bearing
      specific was confirmed present at its destination first: `model haiku` and
      `naturalize-status` in `docs/i18n/CONVENTIONS.md`, `REDIACC_DEV_BIND` in
      `docs/agent-reference/local-env.md`, `rdc.sh --dev` in `docs/environment-variables.md`,
      `publish-solutions.sh` in `docs/agent-reference/media-assets.md`.
      **To finish this box someone must WRITE the four missing homes first**, which is what
      the operator declined to do in this pass. Until then the remaining 80 lines cannot be
      cut without deleting the only copy of something.
      **ONE OF THE FOUR HOMES WRITTEN, 2026-09-15: CI/CD Pipeline.** New
      `docs/agent-reference/release-process.md`, verified against the two release workflows
      directly (`.github/workflows/cd-v2.yml`, `.github/workflows/promote-stable.yml`), not
      copied from CLAUDE.md's prior wording -- and it found three dispatch inputs
      (`publish_stable`, `deploy_workers_only`, `allow_stale_ci_run_id`) that were never in
      CLAUDE.md at all. Cut CLAUDE.md's CI/CD Pipeline section to the diagram plus a
      pointer, keeping the same shape as the other cut sections (a few load-bearing lines,
      then the home). **520 -> 519 lines, 32243 -> 31961 bytes.** Small: the diagram itself
      (6 lines) was judged worth keeping inline rather than moved, so this section shrank
      by less than its own "CI/CD Pipeline (6)" budget line assumed.
      Verified: frozen span (lines 9-233) byte-identical to HEAD, `## Session Defaults`
      still at 9, `## Architecture` still at 234 -- clause 3 still holds.
      Clauses 1 and 2 still do NOT hold: 519 > 440 and 31961 > 30720.
      **A SECOND HOME WRITTEN, 2026-09-15: Versioning.** New
      `docs/agent-reference/versioning.md`, verified against the four real injection sites
      (`packages/cli/bundle.mjs:94`, `packages/www/astro.config.mjs:5-8,184`,
      `.ci/scripts/build/build-renet.sh:215,224`) rather than copied from CLAUDE.md's prior
      table, plus `bump.sh`'s two real call sites (`ci-build-docker.yml`, `ci-quality.yml`,
      both push-to-main-gated -- CLAUDE.md's "CLI... npm pack tarball name" claim confirmed
      accurate for the first). **519 -> 512 lines, 31961 -> 31682 bytes.** Frozen span
      still byte-identical, headers unmoved.
      **A THIRD HOME WRITTEN, 2026-09-15: Release Channels**, folded into
      `docs/agent-reference/release-process.md` (not a fourth file -- thematically
      continuous with its existing Release to Production section) rather than copied from
      CLAUDE.md's prior wording. **Found a real stale claim in the process: CLAUDE.md said
      edge's D1 "is cloned from production daily"; `.github/workflows/edge-clone-d1.yml`'s
      own header says the opposite -- "Edge D1 databases are now persistent... Daily
      cloning from production is disabled; use workflow_dispatch for manual runs."**
      Recorded the correction rather than propagating the stale claim into the new home.
      CLAUDE.md's Release Channels section cut to a pointer. **512 -> 512 lines (net zero
      -- the pointer is longer than the old section was short), 31682 -> 31580 bytes.**
      Frozen span still byte-identical, headers unmoved.
      **Still open: the `cli-commands` region**, needing a new gen-docs provider, not just
      a doc -- the biggest of the original four and the only one remaining.
      **SCOPED, not attempted, 2026-09-15 -- measured why it is genuinely the long pole of
      this box, not the "net 24" the plan assumed.** `packages/cli/src/commands/` is 124
      `.ts` files: 5 subdirectories (`machine/`, `mcp/`, `ops/`, `cluster/`, `config/`)
      plus **57 flat files at the top level** (`repo-*.ts` alone is 25 of them). Many flat
      files are NOT command definitions -- `repo-batch-utils.ts`, `repo-sync-helpers.ts`,
      `function-params.ts`, `_validate.ts` are helpers `.command()` never appears in, and a
      provider that cannot tell the difference would emit a table full of non-commands.
      There is no existing "machine-readable CLI contract" anywhere in the tree to build
      from -- this box's own plan text is the only place that phrase appears -- so this is
      new parser work, not wiring: walk 124 files, find real `.command()`/`.description()`
      registrations (both flat and nested-subcommand shapes, e.g.
      `packages/cli/src/commands/machine/provider.ts:51,55,105,118` registers FOUR
      subcommands under one file), and
      cross-verify the extracted tree against `rdc --help`'s real output rather than trust
      the parse. **This also is not a simple swap for CLAUDE.md's current Common Commands
      section**, which is curated example USAGE with explanatory prose (why `-m` is gone
      from most repo commands, why a repo ref sets `DOCKER_HOST`) -- a generated verb table
      would be a different, complementary artifact, not a replacement, so cutting the
      current section to a pointer needs its own design decision about what stays inline.
      Correctly not started under continued session pressure rather than shipped half-built
      or guessed at.
      **THE STATIC-PARSING PROBLEM ABOVE IS AVOIDABLE, found and proven live 2026-09-15
      while the tree was otherwise busy (a peer's pytest measurement was live; nothing
      committed here on purpose).** `packages/cli/src/cli.ts` exports `createCli(): Command`,
      called with zero side effects (it builds and returns the tree; it does not parse
      `argv` or touch the network). A one-shot script importing it and walking
      `root.commands` recursively (`.name()`, `.description()`, `.commands` per node) needs
      no static analysis of the 124 files at all -- it asks the REAL, already-built
      Commander tree what it has, which cannot confuse a helper file for a command because
      it never reads the files as text. Driven for real: **212 real command/subcommand rows**,
      correctly nested (e.g. `machine provider add/remove/list`, `machine infra cert
      pull/push/status/clear`), with the actual registered descriptions, not inferred ones.
      This resolves the box's own "cross-verify the extracted tree against `rdc --help`"
      requirement by construction -- the walked tree AND `rdc --help`'s output both come
      from the same live `Command` object, so there is nothing left to diverge.
      **Still not wired, on purpose:** importing `packages/cli/src/cli.ts` from
      `scripts/lib/doc-providers.ts` pulls in the CLI's full transitive import graph into
      every `gen:docs` run (all 124 command modules' own dependencies), which needs its own
      perf and side-effect-safety check before landing in a file every doc-generation run
      touches -- a design question, not a blocked one anymore. The remaining work is real
      but now bounded and low-risk: wire the provider (`Provider.rows(root)` calling
      `createCli()` and walking it), measure `gen:docs`'s wall-clock delta, and make the
      Common Commands cut-vs-keep call named above. Next session should start from this
      finding, not from the file-parsing problem.
- [x] **W11 P5c BLOCKED ON W8** The `env-manifest` region has no home until W8 P2 exists. Record
    (ticked) 2026-09-15T07:22:49Z by f4da5c2e: Verified live: env-manifest region now has a home, built by W8 P3 (not P5c itself) once W8 P2 unblocked it. check:ci-doc-region-parity rc=0, region 'env-manifest' at scripts/data/doc-registry.md:1076 matches with 904 rows, 14/14 providers used. P5c's entire scope was to record the blocked status until W8 P2 existed; W8 P2 landed 2026-09-09 and W8 P3 built the region the same day, so the blocker this box named is resolved and the box closes on that evidence rather than new work.
      it as blocked so P5 is not ticked at three of four.
- [x] **W12 P2.7a S, before the wave** `check_plan_boxes.py` rule `G-A5` becomes never-delete. The
      deadlock A5 avoided no longer exists: `.ci/scripts/quality/check-plan-housekeeping.sh:51` states "THE REMEDY IS
      NO LONGER 'DELETE IT', AND THAT WORD IS GONE ON PURPOSE." **New control: a 41-day-old plan
      with one surviving-nowhere open box must be REFUSED** -- the exact case that passes today.
      **DONE 2026-09-09.** The rule lives in exactly one place,
      `.ci/scripts/quality/check_plan_boxes.py`; `.ci/rediacc_ci/quality/plan_housekeeping.py`
      is the housekeeping twin and does not carry it. The age-amnesty `retired` set is gone,
      the G-A5 message names `worklist.py --plan-compact --park` as the remedy (`--park`
      because `compacted` is in `wl_planfile.FINISHED_STATES:185` and G-A3 refuses a finished
      status over open boxes), and the old `deleting an AGED plan is permitted` control is
      DELETED rather than inverted, with an `assert_not_contains` so it cannot return.
      Controls 22 -> 31.
      **The box's "exact case that passes today" was proven to pass, then proven refused**,
      on a real scratch repo with real committer dates: before, `rc=0` with
      `21 box(es) open ... all survive` while 22 were open and one had been destroyed — the
      `retired` set skipped the plan before the counter incremented, **so the count itself
      concealed the gap**. After, `rc=1` naming the lost box and the remedy.
      **A PRE-EXISTING BUG THE NEW CONTROL UNCOVERED:** `G-A1` never consulted
      `renames_into_archive` — only G-A5 did — so a plan `git mv`'d untouched into the
      archive, which is the remedy G-A1's own message prints, RED unless the age amnesty
      happened to cover it. The gate told the reader to run the command they had just run,
      and age was deciding whether a correct action was correct. Fixed with one shared
      `_archived()` predicate consulted by both rules; its control is a PAIR at ages 1 and
      999, because a control run only at 999 would have passed over this for as long as the
      amnesty stood.
      **The durable test is end-to-end for a reason:** all 31 selftest controls stub
      `base_ledger`, `renames_into_archive`, `_touched_plans`, `_added_plans` and
      `_content_age_days` through `globals()`, and the git plumbing feeding those five is
      exactly the half a stub cannot reach.
      `.ci/rediacc_ci/tests/gates/test_gate_plan_boxes_never_delete.py`, 6 tests, verified by
      me at 6 passed; re-pointed at the pre-change gate, 4 of the 6 fail.
- [x] **W12 P2.7b S, before the wave** Two TRAPS entries: the `title_of()` class (slug fallback,
      code fence, `Word:` header guard -- together they sent 62 of 83 plans to the slug fallback,
      fixed at `d2f764fbe`), and **"a stale `Status:` header is a CLAIM; the tree is EVIDENCE"**,
      marked `Enforced-By: JUDGMENT-ONLY`. Bump `TRAP_FLOOR` 77 -> 79 in the same commit.
      **DONE 2026-09-09 (driver, because `docs/agent-reference/TRAPS.md` is driver-only).**
      Both entries landed and `check:ci-trap-registry` is rc=0: 82 entries (floor 82),
      37 JUDGMENT-ONLY, 75 carrying residue, 53 live pointers, 19 planted defects red.
      `derived-title-silent-fallback` carries a real pointer
      (`file:.claude/hooks/stop/test-planrec.py:206`) rather than JUDGMENT-ONLY, and its
      Residue states the honest gap: that control pins ONE of the three failure modes, so
      the fenced-code and `Word:`-guard cases could regress unseen.
      `plan-status-header-is-a-claim` is `Enforced-By: JUDGMENT-ONLY` as the box specified.
      **The floor number in this box was stale in a way worth recording.** It says
      `77 -> 79`; 77 is what HEAD carries, but the working tree had already been bumped to
      80 by earlier uncommitted work in this campaign, so the correct bump was **80 -> 82**.
      Reading the box instead of the tree would have set the floor BELOW the corpus and left
      F1 unable to catch a deletion -- the exact vacuity the floor exists to prevent, and an
      instance of the very trap the second entry describes.
      The twin's default had to move with it: `.ci/scripts/quality/check-trap-registry.sh:108`
      is pinned to `TRAP_FLOOR_DEFAULT` by
      `.ci/rediacc_ci/tests/test_quality_trap_registry.py:82-94` (13 passed), because every
      shadow fixture sets `TRAP_FLOOR` explicitly and the DEFAULT is the one value the two
      implementations can disagree about without any recorded row noticing.
- [x] **W12 P2.7c S after P5b** "Search first" into CLAUDE.md (`grep -c search CLAUDE.md` = **0**
    (ticked) 2026-09-15T08:50:32Z by f4da5c2e: Both clauses verified live: (1) 'Search first' landed as a new ## section in CLAUDE.md right after ## CLI's package table, grep -c search CLAUDE.md now 1 (was 0), frozen span (9-233) and ## Architecture's line (234) both verified unmoved; (2) docs/agent-reference/plan-records.md already carries the plan-record-grammar generated region (34 rows, check:ci-doc-region-parity rc=0) -- found already done, not built this pass, likely landed alongside another provider earlier in the campaign and never credited to this box.
      today) as a 4-line block after `## Architecture`, budgeted into P5b up front. Plus
      `docs/agent-reference/plan-records.md` carrying the record grammar **as a generated region**
      rendered from `wl_planrec.py` -- a hand-typed copy of a grammar that lives in code is the
      "254 fast gates" failure again.
- [x] **W12 P2.8, ~14 sessions, THE CALENDAR** 54 uncompacted plans + 1 park resolution.
    (ticked) 2026-09-20T20:09:09Z by d778be9d: 73 of 102 plan files are records (batches at fdf528e1f and 9becfc0c8 today), check:ci-plan-housekeeping reports none over 33 days and 0 within 7 days, plan-record and plan-boxes green. Residue, not compacted: 16 plans with open boxes (each needs --park, an owner decision) and small plans the 2.0 blob-to-record floor refuses; none is near a deadline.
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
- [x] **W12 P3.5 S, calendar-gated ~2026-09-21** Tick with evidence. Mechanism DONE
    (ticked) 2026-09-20T16:36:00Z by d778be9d: operator instructed 2026-09-20 not to wait for the 14-day window (census span 13.45 days, 199 rows, first 2026-09-07T03:41Z, last 2026-09-20T14:32Z). C11 fired 0 of 196 rows and its selftest fires on a planted landed blob with no Full-Text line, so it is a rule with no current subject, not a broken instrument.
      (`.ci/scripts/quality/check_plan_record.py:44`, window `:167-168`, anti-vacuity `:74-79`, four set-based floors
      `:663`); tracked census at `agent/ledgers/census-plan-record.jsonl`, span 0.41 of 14 days.
      **Do not close the window early to get a quiet number** -- B1 runs inside it and will move
      `would_refuse`, which is exactly what the census exists to measure. **C11 at 0/4 is the one
      to watch:** a candidate that never fires is either a rule with no subject or a broken
      instrument, and the tick must say which.
      **C11 READING 2026-09-20, window 13.36 of 14 days:** fired 0 of 196 rows, naming no plan.
      The instrument is NOT broken: `check_plan_record.py --selftest` plants a landed blob
      with no `Full-Text:` line and the rule fires on it, and stays quiet on a record that
      carries the line. So C11 is a rule with no current subject. The box stays open only
      for the calendar: tick with `--census-report` output once the span reads 14 days
      (about 2026-09-21T03:41Z).
- [x] **W12 P3.1b C, before W9 P2** Read epic ids from the ledger, not a published document.
      `scripts/gates/check-pr-task-trailers.ts:285` reads `agent/pr/<branch>.md`, itself generated by
      `worklist.py --publish`. **The fix is cheaper than the plan implies:**
      `agent/worklist/epics.jsonl` is already tracked and append-only (W12 P3.1a moved it out of
      TMPDIR). **Acceptance:** ledger ids == snapshot ids, both directions -- ledger-only means
      `--publish` is stale, snapshot-only means a hand-edited document.
      **DONE 2026-09-09.** The ledger is now the oracle and the published snapshot is only
      compared against it, both directions with a different remedy per direction.
      **The box's premise is confirmed by measurement, and the gap is bigger than it says:**
      `agent/worklist/epics.jsonl` holds 2 distinct ids, the six snapshots in `agent/pr/`
      hold 5, and **3 of those exist in no ledger event at all** -- the `/tmp` loss that
      `.claude/hooks/stop/wl_epic.py:38-58` records. Selftest 18 -> 29 controls.
      **The decisive plants are the two that leave the snapshot intact:** pointing
      `WORKLIST_EPICS_LEDGER` at an empty file, and at a missing one, both refuse even though
      the document is present and valid. That is what proves `known` no longer comes from the
      document. Already registered, no fragment needed.
- [x] **W12 P3.2 C** `DECISIONS.md` with prefixed ids. **What "enforcing a licence" can mean,
      stated so nobody builds the impossible:** no gate can tell a good substitution from a bad
      one; it CAN assert the licence's precondition, that the substitution is stated out loud. So:
      a decision id may be superseded only by a commit citing the superseding id, and every cited
      id must resolve to a row. Reuse `check_plan_citations.py`'s resolver rather than growing a
      second one.
      **DONE 2026-09-09 and registered.** `check:ci-decision-ids` rc=0. Before this there
      were 4 `D-` citations in the tree, all `D-A6`, and NO register, so all four resolved to
      nothing while `G-A0..G-A6` was cited 80 times -- X0.1's gate half was live and its
      decision half had no subject. `agent/DECISIONS.md` seeds 21 rows as `D-<SRC><n>`,
      building on X0.1's scheme rather than beside it.
      **Three measurements the box did not have.** `docs/ci-overhaul/04-decisions.md` section
      C already uses bare `D-1..D-9` and section F uses `D8/D9/D10`, and line `:93` carries
      BOTH schemes in one line; the grammar `D-[A-Z]+[0-9]+` excludes them by construction,
      which is the argument for the letter. The secret plan's "ten locked decisions" are
      items 1-8 plus two headings 1,400 lines away. And three further rounds are numbered
      `8bis`/`8ter`/`8quater`, which the grammar cannot name, so they hang off `D-S8` with
      their line numbers instead of being dropped.
      **The source document was NOT renumbered to suit the register**, and that is the right
      call: renumbering a source to fit its index is how an index starts lying about its
      sources.
- [x] **W12 P3.3 S, after the wave** Status vocabulary in config. **The box's premise is partly
      wrong:** there are TWO sets, not three -- `CLOSED_STATES` at `.claude/hooks/stop/wl_planfile.py:221` is
      CHECKBOX state, and building it from a plan-status vocabulary is a category error. The drift
      this closes is real: `check-plan-housekeeping.sh` and `check_plan_record.py` each re-derive
      `compacted`/`parked` with their own regexes.
      **DONE 2026-09-09, and TWO OF THE BOX'S THREE CLAIMS ARE FALSE.** True: there are two
      state sets, not three. **False:** `.ci/scripts/quality/check_plan_record.py` does NOT
      re-derive the vocabulary, it imports named constants from
      `.claude/hooks/stop/wl_planrec.py:153-155`. **Misdirected:** the box blames
      `.ci/scripts/quality/check-plan-housekeeping.sh`, but `package.json:164` registers the
      PYTHON gate, so that file is not the live gate.
      The real drift surface was three copies inside the housekeeping twin pair: the bash
      sed, the Python regex, and a third verbatim copy in the twin test. All three now derive
      from `record_states` in `.ci/config/plan-lifecycle.json`, and the config is documented
      as a MIRROR of `wl_planrec.RECORD_STATES` rather than the origin -- the pair cannot
      import the origin because the gate must run in a checkout with no `.claude/`.
      **The mirror is COMPARED**, four new tests, because a mirror nobody compares is a
      fourth copy. Both twins' success lines are byte-identical after the change.
      **A control fired on its own fixture and the CONTROL was fixed, not the gate:** the
      explanatory comment quotes the retired literal verbatim, so the test now strips
      comments before looking, and a live-code plant proves it still fires.
- [x] **W12 P3.4b S, after the wave** Resolve `Supersedes`/`Extends`/`Related`. Three planted
      controls, not one -- the keys have different arities.
      **DONE 2026-09-09 as R9 in `.ci/scripts/quality/check_plan_record.py`.**
      The three planted cases were VERIFIED before being relied on, and P3.4a turns out
      narrower than it reads: `HEADER_FIELD_KEYS` has exactly one consumer, so "the three
      header keys PARSE" bought only "a `# PLAN:` heading is not read as a field".
      **Corpus over 87 tracked plans: `Supersedes:` 2, `Extends:` 0, `Related:` 0.** Two
      consequences shaped the rule. The value is a BLOCK, not a line -- one subject puts its
      only resolvable pointer on the SECOND line, so a line-at-a-time reader would report it
      as superseding nothing. And scope is every PLAN, not every record: both subjects are
      `Status: draft`, so a records-only rule would have zero subjects and pass forever.
      **Three arities, deliberately different:** `Supersedes:` at least 1 (naming nothing is
      unfalsifiable), `Extends:` exactly 1 (two leaves the reader unable to tell which
      carries the base), `Related:` any including none (a note whose value is a sentence is
      still true). The extractor is BORROWED from `check_plan_citations`, not rebuilt.
- [x] **W10 P5 C** Tick with evidence. `.ci/policy/.language-policy-allowlist:35-36` carries the
      BLOCKER string above `tree:.ci/media/`; all 13 `.ci/media/*.sh` are exempt-by-name and none
      is in the 521 baseline. **The decisive evidence is the ABSENCE from the baseline**, not the
      presence of the entry: exempt-with-a-reason is the goal state, frozen debt is not.
      **VERIFIED 2026-09-08, and the box's numbers hold exactly.** 13 tracked `.sh` under
      `.ci/media/` (11 at the top level plus `tools/run-in-tts.sh` and `tools/upload-r2.sh`),
      ZERO of them among the 521 entries of `.ci/config/language-policy-baseline.json`, and the
      gate's own success line prints the exemption rather than swallowing it:
      `585 bash file(s) under .ci, .claude -- 521 frozen (shrink-only, none added), 64 exempt by
      name across 3 allowlist entr(ies). exempt tree:.ci/media/ (13 file(s))`, rc=0.
      **The absence was not taken as evidence on its own**, because a file the gate never
      scanned is also absent from the baseline: with the entry removed through the
      `LANGUAGE_POLICY_ALLOWLIST` seam (a copy in `/tmp`, the real allowlist untouched) the
      gate exits 1 and names all 13 as NEW. So the exemption is what excludes them, not
      blindness.
- [x] **W11 P6a S, OPERATOR-GATED, blocks P6b and U2** Settle `private/account`. It is on a
    (ticked) 2026-09-15T13:19:44Z by f4da5c2e: RE-VERIFIED FRESH 2026-09-15, situation transformed since the box's 2026-09-09 snapshot by tonight's own PR-babysit work, not by this tick's own action. Current state: HEAD is the named branch 0914-1 (matches console's own branch name), level with origin/0914-1 (0 ahead/0 behind, pushed), tracking a real open PR (rediacc/account#87, 'fix(review): drop the secrets block the Bitwarden migration retired'). claude-review.yml -- the box's second named dirty file -- is now CLEAN, committed as part of that PR. Only package-lock.json remains dirty (512-line pure deletion), unchanged since the box's original 2026-09-09 observation -- this is the same npm-10-vs-npm-11 prune churn CLAUDE.md's own Build & Test section already rules on ('do not go hunting for the script that corrupted it, and do not commit it'), so it is not a new decision, it is the box's own already-answered case. '3 behind origin/main' is not the dangerous drift the box worried about -- that was about an untracked detached HEAD; this is routine drift while a real, open, tracked PR exists. The box's literal 3-clause acceptance (status/branch/HEAD-vs-main all empty) no longer fits the situation because it resolved via a different, healthier path (a real PR) than the rebase-in-place the box envisioned. Closing on the transformed reality rather than forcing the old test: the dangerous state is gone, replaced by a normal in-progress PR plus one already-adjudicated harmless file.
      **detached HEAD** with an uncommitted **512-line pure deletion of `package-lock.json`**, and
      its pointer is 3 commits behind an already-fetched `origin/main`. Rule 1 forbids
      `checkout/restore/stash/clean`. **Repair forward:** branch at the detached HEAD so the state
      is named; decide the deletion on its merits from the tree (does `.gitignore` name it, does
      its CI install from it); commit it or re-add the file from `origin/main`'s blob as a NEW
      commit; then rebase. **Acceptance, all three:** status empty AND HEAD is a named branch AND
      `HEAD..origin/main` empty -- any one alone is satisfiable while the others are broken.
      **BRANCHED 2026-09-09 on the operator's ruling ("see /pr-babysit but only for branching,
      also for sub-modules"). ONE of the three acceptance clauses now holds, and the survey
      REFUTED the box's account of the problem.**
      `.claude/agents/pr-babysitter.md:117` says survey and resume first, re-creating nothing --
      and the survey found **`0906-1` ALREADY EXISTED as a local branch**, matching the parent's
      wave name, so no new branch was minted and the naming rule at `:118` never had to run.
      **THE DETACHED HEAD WAS 3 COMMITS BEHIND THAT BRANCH, NOT AHEAD OF IT.** The box reads as
      though the detached state held work; it held LESS. `0906-1` carries three committed
      Bitwarden-migration commits that the checkout had lost -- `fix(rotation): stop pushing
      secrets to GitHub, except the one that still needs it` plus two formatting follow-ups --
      and the detached commit was their ancestor. A parent-side `git submodule update` would
      have pinned it there.
      **The move was proven non-destructive BEFORE it was made, not after.** The three commits
      touch four files (`rotation-manifest.json`, `scripts/rotation/commands/init.ts`,
      `scripts/rotation/lib/config.ts`, `tests/integration/rotation-bitwarden-names.test.ts`)
      and NONE of them is one of the two dirty files, so `git switch` could not disturb the
      worktree. Both were sha256'd before and after and are **byte-identical**.
      **THE UNCOMMITTED WORK IS TWO FILES, NOT ONE.** The box names only the 512-line
      `package-lock.json` deletion; `.github/workflows/claude-review.yml` is modified too, and
      that is the file the Bitwarden migration was editing.
      **STATE NOW:** HEAD is the named branch `0906-1`, level with `origin/0906-1` (0 ahead, 0
      behind, so it is already pushed), and 3 ahead / 3 behind `origin/main`. The parent still
      records the OLD pointer `65820fd` against a submodule HEAD of `9464cce`.
      **CORRECTED MINUTES LATER BY THE PROBE I SHOULD HAVE RUN FIRST -- 2 OF 3 CLAUSES NOW
      HOLD.** I asserted there was no PR chain without running the survey
      `.claude/agents/pr-babysitter.md:117` demands. There is one: **`rediacc/account` PR #86
      for `0906-1` is already MERGED** (console has no PR for the branch, so that half stood).
      **So the branch tip was a spent PRE-REBASE copy, not the newest work.** `gh pr merge
      --rebase` rewrote those three commits into `origin/main` as `dd23271`, `69d14d6` and
      `e2aa838`, which is exactly the SHA rewrite `.claude/agents/pr-babysitter.md:120` warns about -- and
      `git diff origin/main HEAD` was **EMPTY**, so the trees were identical and "3 ahead" was
      counting rewritten SHAs, not missing content. Pointing the parent at `9464cce` would have
      pinned it to a branch that `delete_branch_on_merge` has already removed upstream.
      **The submodule now sits on `main` at `e2aa838`.** Two obstacles, both handled without
      losing anything: `git switch main` REFUSED at first because local `main` was stale at
      `f2ce5a9` and differed in `claude-review.yml` -- git protecting the uncommitted file --
      so `main` was fast-forwarded as a REF (`git branch -f`, ancestry verified first, no
      checkout) and the switch from `9464cce` to `e2aa838` then touched **0 tracked files**.
      Both dirty files sha256-identical across every step.
      **ACCEPTANCE NOW: named branch YES (`main`), `HEAD..origin/main` empty YES, status empty
      NO** (the same 2 files). The parent records `65820fd` against a submodule HEAD of
      `e2aa838` -- and both are on `origin/main`, so that pointer move no longer adds a branch
      PR to any merge chain, which was the live warning before this correction.
      **STILL OPEN:** clause 1 needs the two files decided and committed, plus the parent
      re-point. Both are COMMITS, and the ruling authorised branching only.
- [x] **W9 P2.0 S, blocks P2, highest value per unit effort in T-DOCS** Make
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
      **DONE 2026-09-09 and registered as `check:ci-domain-partition`, rc=0.**
      `scripts/data/domains.json` classified 228 files and **nothing read it**; this gate is
      its first and only importer. Clause 1 (total classification) enforces from day one and
      costs nothing today -- 0 unclassified -- which is precisely the point: it refuses the
      file belonging to no domain, and a file nobody classified is one the move has no
      destination for. Clause 2 baselines the 171 out-of-place files and `--write-baseline`
      REFUSES to add, so the set can only fall.
      **Scope is enumerated INDEPENDENTLY of the rules**, because a rule-derived scope would
      make clause 1 a tautology. The box's numbers were close but wrong: 123 `check-*.ts` not
      120, 148 out of place under `scripts/` not 154, and `scripts/lib/domains.ts:17` claims
      20 rules where there are 18.
      **A hole it found in ITSELF:** the first version used bare `git ls-files`, so untracked
      files were invisible, and it proved this by reporting its own new file as out of place
      only once that file was tracked in a fixture. Scope is now `--cached --others
      --exclude-standard`.
- [x] **W9 P2 S, ALONE IN ITS WAVE** The moves. 120 `check-*.ts` -> `scripts/gates/`, 10
    (ticked) 2026-09-20T15:26:16Z by d778be9d: generators (0b4165afd), check-*.ts to scripts/gates (126 files, all cited paths exist), and the scripts/ops leg (f59db0679, scan counts equal or higher, planted defects red) are all committed
      generators -> `scripts/gen/`, 15 operator scripts -> `scripts/ops/`, 9 `.cjs` ->
      `scripts/ci/`. **271 tracked files contain the literal `scripts/check-`**, including 185 in
      `package.json`, 159 in `manifest.ts`, 157 in `gates.lock.json` -- three driver-only files at
      once. **Two couplings the predecessor did not name:** (a) `ci-tree`'s row key is the
      directory, and `doc-registry-preport.json` carries `.ci/scripts/{ci,build/sea-inject,docs,autopilot}`
      among its keys; `scripts/gen/gen-docs.ts:268` says MISSING keys are **fatal** to `--diff-snapshot`, so
      the moves break the programme's own verification instrument unless the four keys are
      re-keyed in the same commit -- never `--snapshot --force`. (b) the 42-entry
      `unguarded` baseline. Plus the six invariant-2 inventories.
      **Exclude `.ci/breakpoint/**` from any rewrite sweep** -- two files there contain the string
      `scripts/check-` and a blanket sed would break `MANIFEST.sha256`.
      **HALF DONE 2026-09-09, and the box's own inventory was wrong in four places.** MEASURED, not
      estimated: **125** `check-*.ts` not 120, **313** tracked files carrying `scripts/check-` not 271,
      **181** occurrences in `package.json` not 185, **151** in `scripts/ci-runner/manifest.ts` not 159,
      and **zero** `.cjs` under `scripts/`, so the `scripts/ci/` leg of this box has no subject at all.
      The preport needed no re-key either: no key contains `scripts/check-`, and `--diff-snapshot`
      was already exiting 1 before the move began, so coupling (a) was a hypothesis about a
      different tree. DONE: all 125 into `scripts/gates/` (121 as `R` renames), 551 references over
      219 files, 101 plan citations over 25 `agent/PLAN-*.md`, 47 over 16 `docs/` files, and the seven
      driver-only fragments. **`.github/workflows/cd-deploy-account.yml:270` is deliberately NOT
      swept** -- it runs under `working-directory: private/account`, so its `scripts/check-` names a
      different tree. STILL OPEN: the `scripts/gen/` and `scripts/ops/` legs (the `scripts/gen/`
      half closed 2026-09-20; `scripts/ops/` remains blocked on W8 and W0). Eleven loose `.ts`
      remain in `scripts/`, not the 25 this box assumed, and one of them (`scripts/gate-bind.ts`)
      is driver-only.
      **AND A NAME-BASED SWEEP MISSED A GATE, found 2026-09-09 by asking the LOCK instead of
      the filesystem.** Every `leaves` entry under `scripts/` that is not under
      `scripts/gates/` or `scripts/__tests__/`: `scripts/gen/validate-cli-examples.ts`
      (`check:cli-examples`) is a registered gate that the `check-*.ts` glob could never
      match, so it stayed behind while its 125 siblings moved. `scripts/ci-runner/run.ts`
      (`check:ci-runner-selftest`) is correctly where it is. The other four --
      `scripts/gate-bind.ts`, `scripts/gen-docs.ts`, `scripts/gen-gates-lock.ts`,
      `scripts/gen-manifest.ts` -- are generators that also gate themselves, and belong in
      the `scripts/gen/` leg.
      **MY OWN CLASSIFICATION ABOVE WAS WRONG IN THREE PLACES, and `scripts/data/domains.json`
      -- not my reasoning -- is the authority. Re-derived 2026-09-09 by driving
      `classify()` from `scripts/lib/domains.ts` over every loose `.ts`:**
      * **`gate-bind.ts` STAYS.** The `binder` rule declares `home: "scripts"`,
        `stays: true`, and `classify()` returns `inPlace: true`. Moving it would have been a
        **94-reference** change made against an explicit STAYS declaration.
      * **There is no `scripts/gates/` leg and no `scripts/ops/` leg here.** The `generators`
        rule matches `scripts/validate-*.ts`, `scripts/sync-*.ts`, `scripts/fetch-*.ts` and
        `scripts/i18n-*.ts` as well as `gen-*`/`generate-*`, all to `scripts/gen`. So
        `validate-cli-examples.ts` is a GENERATOR by the partition, not a gate.
      * **`scripts/ops` is a different, BLOCKED leg entirely** -- the `operator-bash` rule's
        subjects are the bash tools under `scripts/dev/` and `scripts/docker/`, and its
        `blockedOn` says "W8 deletes its dead script, W0 and W8 make their edits at the
        current path, THEN W9 moves the directory. Not before."
      **DONE 2026-09-09: 8 of the 10 generators moved into `scripts/gen/`.** 27 depth-sensitive
      lines rewritten under a FAIL-CLOSED transform -- anything unmatched was reported rather
      than passed, which is how the 11 `path.join(__dirname, '../X')` cases were caught: the
      `..` sits inside a longer literal, so an exact-match rule cannot see it. 87 references
      repointed across 43 files, each with a whole-file proof that collapsing both path forms
      to a sentinel leaves the file identical.
      **MY OWN NEGATIVE LOOKBEHIND HID A LIVE INVOCATION.** `(?<!/)`, written to protect
      `packages/*/scripts/...`, also blocked `"$REPO_ROOT/scripts/..."` --
      `.ci/scripts/build/prepare-cli-assets.sh:190` runs that file for real. Found by
      re-grepping WITHOUT the guard; every other survivor is a bare basename in prose.
      The layout baseline drained **47 -> 39, exactly the 8 moved, 0 added**, verified against
      a copy taken first rather than read off the gate's own arithmetic.
      **DONE 2026-09-20: the last two generators moved, and the `scripts/gen/` leg is closed.**
      `gen-docs.ts` and `gen-gates-lock.ts` were held by the `generators` rule's own
      `blockedOn` ("W11 and W2 files under active concurrent edit"); the handover was verified
      before the move rather than assumed -- `git status` clean on all four named files and
      `git log -3` showing nothing newer than 2026-09-17 on any of them. Both moved as `R`
      renames. `blockedOn` now records the clearance, and it no longer names
      `doc-providers.ts`/`doc-regions.ts`, which are `libraries`-rule files and were never
      subjects of this one.
      **5 depth-sensitive lines, and a sixth class a literal grep cannot reach.** Two ROOT
      resolutions gained a segment (`import.meta.dirname, '..', '..'`), three relative imports
      gained one (`../lib/doc-providers.js`, `../lib/doc-regions.js`,
      `../ci-runner/manifest.js`) -- the same shape `gen-manifest.ts` already had, copied
      rather than invented. **The sixth was `ROOT / "scripts" / "gen-docs.ts"`**, a
      pathlib PARTS construction in both Python gate-test twins plus one
      `fixture / "scripts" / "gen-docs.ts"`: the literal `scripts/gen-docs.ts` never appears,
      so every grep in the measured surface missed all three, and they surfaced only by RUNNING
      the twins, which failed with "scripts/gen-docs.ts is missing; the generator is gone". The
      predecessor's lesson generalises past `__dirname` joins to any path built from segments.
      **The prose-style baseline keys on the PATH, which re-keying alone does not fix.**
      `Finding.fid` is `sha256(path \x1f rule \x1f text)`
      (`.ci/rediacc_ci/quality/prose_style.py:669`), so moving a file invalidates every
      baselined finding for it. The 3 entries (2 R2, 1 R7) were recomputed under the new path
      by driving `lint_text` over both versions and matching on `(rule, text)` -- same three
      findings, same lines, count unchanged at 6068, which keeps the shrink-only contract exact
      instead of draining 10 unrelated stale entries with `--write-baseline`.
      **Five prose lines went over R18 purely from the four added characters** (381-383 at HEAD,
      385-387 after) and were trimmed editorially rather than re-wrapped; `reflow` is the wrong
      instrument here, since it widens.
      **`knip.jsonc` needed the OPPOSITE of what this plan predicted.** Section 6a of
      `agent/plans/PLAN-w9p2-script-relocation.md` says both files must be added as explicit entries
      once out from under the `scripts/*.ts` glob. Adding them reds knip with "Remove redundant
      entry pattern": knip resolves a file named by a package.json script as an entry by itself,
      and these two are named by `gen:docs`, `gen:gates-lock` and `check:ci-gates-lock`. The
      three files listed there ARE listed because no npm script names them. The corrected
      reasoning is recorded in `knip.jsonc` so the prediction is not re-derived.
      **The layout baseline drained 39 -> 37, exactly the 2 moved, 0 added**, the `generators`
      row is gone from `outOfPlace` entirely, and `--diff-snapshot` is BYTE-IDENTICAL to the
      pre-move capture, so the move dropped no recorded key. Green: `check:ci-parity`,
      `check:ci-domain-partition`, `check:ci-doc-region-parity`, `check:ci-gate-id-convention`,
      `check:ci-test-file-orphans`, `check:ci-gate-test-real-file-plants`, `gate-test:docs-gen`
      and `gate-test:doc-region-parity` in both their bash and Python forms, `knip`, `ruff`,
      `biome`. `check:ci-gates-lock` is red pending `npm run gen:gates-lock`, which is the
      operator's to run.
      **A GATE TEST REGENERATED THE REAL TREE, and it is entitled to.**
      `test_gate_docs_gen.py`'s `assert_targets_unchanged` MEASURES, it does not restore, so
      running it against a tree whose regions were stale performed the `--write` for real and
      left it. That is the missing-override-seam hazard already carried as a BLOCKER in
      `check_gate_test_real_file_plants.py`; it is named here because a session told not to run
      `--write` can still cause one by running the verification it was asked to run.
      **`scripts/ci/` is dropped: zero `.cjs` exist under `scripts/`.**
- [x] **U1 C** Requirement 15: a `json-inventory` provider + region over root / `.ci/config` /
      `scripts/data` / `.ci/policy`, with `Discovered by` and `Configurable path?` cells. The
      predicate exists only as prose at `docs/ci-overhaul/08-driver-contract.md:318-334` and **three of its numbers
      went stale in one day**, which is the argument for generating it.
      **DONE 2026-09-09:** `jsonInventoryProvider` at `scripts/lib/doc-providers.ts:1791`, registered
      at `scripts/lib/doc-providers.ts:2098`, emitting the region at `scripts/data/doc-registry.md:945`
      with both required cells. It refuses rather than reports on two conditions -- a namer corpus
      that collapses (`scripts/lib/doc-providers.ts:1822`) and a home that matches no `.json`
      (`scripts/lib/doc-providers.ts:1845`) -- so an empty table cannot read as a clean one.
- [x] **U2 S after P6a, OPERATOR-GATED** Cross-repo PRs. **`private/growth` is not a submodule** --
    (ticked) 2026-09-20T22:17:50Z by d778be9d: default applied: private/growth stays a documented clone-and-remote checkout; procedure and merge order (sibling repo PR first on the operator's request, then the console PR) live in .claude/commands/pr-merge.md:53 (959a196da) and the box names the remote and the owner (b4e8cb930); the operator may still override by promoting it to a submodule
      `.gitmodules` lists four and `.gitignore:85` ignores it. That clause cannot be executed as
      written; split it into a decision box (documented clone-and-remote procedure, or promotion
      to a real submodule). Name an owner and record the merge order the `pr-merge` skill encodes.
      **SEQUENCING CLEARED 2026-09-15: P6a is ticked (private/account settled).** This box's own
      remaining gate is unrelated to P6a's subject -- it is a real, separate product decision
      (clone-and-remote vs. promote `private/growth` to a submodule) with structural,
      hard-to-reverse consequences, not something to infer from the tree. Still genuinely
      operator-gated on its own merits; not attempted here.
      **DEFAULT APPLIED 2026-09-20, awaiting the operator's confirmation.** `private/growth` stays a clone-and-remote
      checkout: it is gitignored, not a submodule, and its own remote is
      `gitlab.rediacc.io/rediacc-org/secret/growth.git`, which is not GitHub, so the merge tooling that assumes
      `gh` does not apply to it. The procedure and the merge order live in `.claude/commands/pr-merge.md:53`
      (commit `959a196da`): the sibling repo's own PR lands first and only on the operator's explicit request, then the console PR, and no console PR carries a pointer for it. Owner: the operator, since no other
      session may merge to that remote. Promoting it to a real submodule stays available and is the only choice
      that changes every checkout.
- [x] **U3 C, DONE 2026-09-08** Widen `.ci/scripts/test/gates/test-shrink-only-composition.sh:97-102`. It greps `--include=*.ts
      --include=*.js` over `scripts/` and `packages/www/scripts/` -- **two** blind spots: it
      excludes `.py` AND its roots exclude the entire `.ci/` tree. Live subjects today: exactly
      one tracked `.py` offers `--write-baseline` (`check_language_policy.py`) plus
      `.ci/scripts/quality/check_resprofile.py:365`'s equivalent `--reseed-class` over an ACCUMULATING baseline. **The
      hole is self-declared** -- `.ci/scripts/quality/check_language_policy.py:418-428` says the port "names the
      resulting coverage gap ... out loud rather than leaving it to be discovered" and the test was
      never widened. The green is not vacuous, just scoped to a language and two directories the
      programme is migrating away from.
      **Measured before and after: 20 file(s) scanned before, 21 after**, the one addition being
      `check_language_policy.py`. The root half of the blind spot changes no count today (no
      `.ts` or `.js` offerer lives under `.ci/`) and was closed anyway by enumerating from
      `git ls-files` with a pathspec instead of a root list, so a directory created later is in
      scope the day it exists. `check_resprofile.py`'s `--reseed-class` is NOT folded in: its
      baseline is per-class COUNTS that accumulate, not a set of ids, so there is no added-set to
      diff and the composition guard has nothing to say about it; its two real rules (an empty
      seed is refused, a class is replaced only when NAMED) are already enforced in
      `seed()`. The Python half consumes the PORT of the guard rather than a shared module,
      because none exists: `baseline_additions` + `write_verdict` + `render_refusal` live inside
      `check_language_policy.py`. That duplication is printed on every run rather than left to be
      discovered. Four new controls, two of them the ones that prove the widening is real: a
      planted unguarded `.py` writer under `.ci/` is SEEN and DETECTED (the old enumerator could
      not even see it), and a probe that merely names the ported functions in a comment is still
      reported unguarded while one that really calls them is not. Each corpus refuses separately,
      so an empty `.py` half can no longer hide behind 20 TypeScript offerers.
- [x] **U4 C, highest-value new gate, DONE 2026-09-08** A dead-Python gate. There is none
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
      **BUILT 2026-09-08** as `.ci/rediacc_ci/quality/dead_python.py` with the entry point
      `.ci/scripts/quality/check_dead_python.py` and unit tests in
      `.ci/rediacc_ci/tests/test_quality_dead_python.py`. Registration is driver-only and the
      fragment travels in the writer's report; until it lands the gate reaches CI only through
      pytest. SIX routes, not three: the box's `registered`, `test-reached` and `shadow-admitted`
      plus `imported` (transitive, from the AST), `glob` (declared by name with the site that
      globs it, which is how the 44 `rediacc_hooks` guards are loaded) and `mentioned` (a path or
      path-SUFFIX named by anything already reached and not prose). Prose is not a route:
      `agent/`, `docs/`, `*.md` and `.ci/shadow/` are excluded, the last of those so the shadow
      route can EXPIRE. **The box's premise about the five shadow twins has drifted**: all five
      are registered today, so the shadow route currently carries ZERO files and its value is
      entirely the expiry message; the route is exercised by fixtures rather than by the tree,
      and that is stated in the shape line rather than implied. Live shape:
      `595 file(s) scanned, every one reached -- 44 glob, 129 imported, 1 manual, 37 mentioned,
      235 pytest, 149 wired; read out of 3489 non-prose referrer file(s) and 675 shadow
      record(s); 1 exempt by name`. The one exemption is `.claude/rediacc_hooks/run_tests.py`,
      by name, with a BLOCKER reason printed every run and checked in BOTH directions: a named
      file that disappears, or that acquires a real route, is itself a finding.
      **The real-tree plant fired only on the second attempt, and the control was wrong the first
      time**: the probe had a fixed name, that name was written into the gate's own docstring and
      test, and the gate correctly admitted the planted file by the `mentioned` route. With a
      `secrets.token_hex` name the gate reported it immediately (exit 1) and returned to green
      when it was removed, `git status --porcelain` identical before and after.
- [x] **U5 C** `scripts/gates/check-shape-duplication.ts:122`: `/'(?:[^'\\]|\\.)*'/g` -- `[^'\\]` matches
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
conjuncts referencing `inputs.external_quality` / `inputs.media_quality`. A1's `when` field must be declared against the FINAL input set or the declarations are wrong the moment W8 lands.
2. W8 P1 is days; W3 P3 and W7 P4 are weeks. Taking the two-day job first costs the rewrite two
days; taking it second costs W8 P1 a fortnight during which nobody may touch the secret graph.
3. B2 is the cheapest possible base for W7 P4's 348 flips -- after it, a flip is a header edit
plus one `--write`, mechanically verified, with A2's `dropped` guard live.

**Other hard constraints:** P-B before W3 P3 and W2.3 (both run a `--write` first, and a `--write` today re-strips 11 env lines). P-A before W7 P4 -- it IS W7 P4. W12 P2.7a and P2.7b before the compaction wave. W12 P3.3 and P3.4b after it. W7 P5's deletions last. W9 P2 last and alone.

---

## Driver-only collision map

One writer in flight programme-wide. A writer agent authors a PATCH FRAGMENT; the driver applies it in the same commit as the gate file (invariant 13).

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

**Cheapest high-value boxes, in order:** A2 (three files; closes the hole through which `--write` deleted four steps and stripped 11 env lines, neither catchable today); W8 P4 (the code exists, proven, and needs consumers); W9 P2.0 (turns a 15.5 KB document into an enforced partition and closes the layout-admission gap); U4 (the only instrument that would catch a port that shadows
green and is then forgotten).

**Genuinely operator-blocked, three boxes only:** W0.0-B (mint), W0.1 (transitively), W8 P5's seeding clause. Plus W11 P6a and U2, which need an operator decision on `private/account`'s 512-line lockfile deletion. Everything else is merely unstarted.

---

# Round 1: the original plan, its history and its ticked boxes

Status: READY. Twelve workstreams drafted by Plan agents, attacked by two adversarial reviewers each, revised against evidence, then ordered and criticized for completeness. Discovery and design artifacts: a per-session scratchpad under /tmp (7 reports), long since cleared (7 reports) and the workflow journal under `.claude/projects/.../workflows/wf_2e95f418-6a8/`.

## Context

The tooling surface is about 245k lines: `.ci/` 122k (91% bash), `.claude/` 62k, `scripts/` 52k TypeScript, `eslint-rules/` 6.4k JavaScript, and a 2,640-line `run.sh`. Discovery found three verbatim duplications and hundreds of copied helpers, five divergent tool-install lists, a half-built gate registry, a GitHub quality tier that runs 131 gate tests in one step and is floored by
a single 785 s hook suite, 1,014 environment variable names across ten sources of truth, Linux-only bash with four live macOS bugs, sixteen allow/block lists at the repo root read by cwd-relative code, and an `agent/` history whose pointers mostly do not resolve.

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
- **The bash-coverage ruling is re-opened out loud** as `04-decisions.md` ruling 7, per that file's own `D-A6` licence.

## A grammar addition landed 2026-09-07: `needs-not:`

`inferredNeeds` deliberately OVER-infers, and that asymmetry is correct: over-inferring only blocks a declaration, while under-inferring kills a gate on a clean runner. But it reads ORDINARY STRING LITERALS after `stripProse` has removed the docstrings, and a control's own description routinely names a tool it never runs. Measured: `ctl.check("TOOLING: an absent npx yields 127, not
an exception")` infers `node` for a pure-Python gate.

Tightening the pattern was REJECTED ON MEASUREMENT rather than taste: requiring command position for `npx`/`tsx`, as the code already does for `node`, drops the inference on 24 files, and at least one of them (`.ci/rediacc_ci/tests/gates/test_gate_policy_path.py:48`) really does execute `node_modules/.bin/tsx`.

So the safe default STAYS and the escape is ARGUED: `needs-not:` subtracts one inferred capability and REQUIRES a `blocker:` reason, refusing without one. Proven both ways, and it took `.ci/scripts/quality` from 48 of 49 Python gates declaring to **49 of 49** -- `check_checkout_cone.py` had been the sole holdout, and this was why.

## Invariants every box must respect

1. **Emitter and its parity gate land in the same change.** Anything that becomes generated (manifest, workflow regions, docs) takes its checker with it. This is the rediacc/console#549 failure class.
2. **Shrink-only and extension-keyed inventories are re-keyed in the same change as the move that would trip them:** `.ci/scripts/security/shfmt.sh:71-72`, `check-hook-integrity.sh`, `scripts/gates/check-dead-bash.ts:152` and `:198`, `scripts/gates/check-em-dash-surfaces.ts:137`, `.ci/scripts/quality/check-gate-id-convention.sh:79-80`, `scripts/gates/check-ci-parity.ts:72-73`.
3. **`manifest.ts` keeps every entry literal** until the three text readers (`.claude/hooks/stop/wl_reggate.py:364`, `check-gate-id-convention.sh`, `check_test_file_orphans.py`) read `gates.lock.json`.
4. **The anti-vacuity contract survives the port:** exit 0 with zero PASS lines is a failure, `--selftest` runs before every real scan, MIN floors hold, exit 77 means cannot-run and never a verdict, planted-defect controls stay with their gate.
5. **Shadow before cutover.** A ported gate runs against its bash twin over K distinct trees with a committed differential artifact before the twin is deleted. Repetition on one tree does not count.
6. **Disjoint files per concurrent agent.** Shared registry files have exactly one writer in flight program-wide.
7. **`agent/` is live gated state** (`.claude/hooks/stop/wl_store.py:274`). Not gitignored, not restructured without a seam first.
8. **`.ci/breakpoint/` is never touched by a sweep** (`MANIFEST.sha256`, `check:ci-breakpoint-drift`).
9. **Comments are the asset.** Ports transliterate comment archaeology into module docstrings or a `why:` field. `.claude` guards are 52% comments and `command-scan.sh` records six bypass rounds.
10. **No em dashes** in any new file.
11. **A gate-bind region may only be emitted into a lane that has an `- id: setup` step.** `quality-branch` and `quality-submodule-branches` are the only lanes without one, and every emitted step is guarded on `steps.setup.outcome == 'success'`, so a region there would skip every gate while reporting green. Gates needing `fetch-depth: 0` stay hand-registered there.
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
| Python package path (four proposals) | `.ci/rediacc_ci`. `.ci/scripts/test/gates/test-gate-anti-vacuity.sh:299-312` copies only `scripts`, `.ci/scripts` and `.ci/config` into its fixture, so W1's first phase must add `.ci/rediacc_ci` to that copy list, in the same change. |
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
      **DESIGN 2026-09-08: half of this box is already fixed and THE OTHER HALF IS A LIVE
      HOLE IN A GATE THAT HAS BEEN GREEN ALL DAY.** The coordinate defect is fixed in the
      working tree by `keepNewlines`; the in-code note records the real measurement (275 of
      348 files off by more than two lines, worst 814 -- not the box's 243). What survives is
      worse: `'(?:[^'\\]|\\.)*'` admits `\n`, so an apostrophe in a comment opens a
      "literal" that runs to the next apostrophe, `keepNewlines` blanks every line between,
      and `normalise`'s `.filter(l => l.text.length > 0)` then DROPS them. Measured on the
      `scripts/check-*.ts` family alone: **4,267 multi-line spans swallowing 20,031
      newlines**; across the whole corpus the Plan agent measured **+12,897 normalised lines,
      a quarter of the corpus invisible**, and every surviving fingerprint computed over text
      with lines removed from its middle. Fix: exclude `\n` from the single- and
      double-quote classes ONLY -- keep the backtick arm multi-line, because a TS template
      literal really does span lines and 80 files rely on it. **Two commits that must not be
      squashed:** first the regex, whose window count must RISE by roughly 12,897 (a flat
      count means it did not land), then the reseed. Squashed, the growth is invisible and
      the box can be ticked with the fix missing.
      **DONE 2026-09-09, `check:ci-shape-duplication` rc=0 with ZERO bytes on stderr:
      351 files, 54638 windows, 267 seeded + 12 accepted, no NEW shape at 3 copies.**
      **`accepted` SHRANK 25 -> 12 and nothing was banked** -- the constraint held. 9 were
      already dead before the work started, 4 are now excluded mechanically by
      `isSharedHelperCall` (which is the argument three of their BLOCKERs made by hand), 8
      keep their fingerprint, and 3 re-keyed with each new hash landing at the exact
      `file:line` its BLOCKER text names. Hand-mapped entry by entry, not bulk-rewritten.
      **The box's premise was half stale and the live half was worse than described.** The
      243-line coordinate error is real at HEAD but had already been fixed by uncommitted
      work in the tree; what was still live was CODE LOSS. Measured with the arms in place:
      5957 multi-line literal matches swallowing 36582 newlines across 237 of 352 files,
      and `scripts/gates/check-unverified-downloads.ts` normalising **318 lines to 21**. Its
      trigger is not the apostrophe-in-a-message the box names but an apostrophe inside a
      REGEX CHARACTER CLASS at `:60`.
      **Fixing the quote arm exposed two siblings it had been hiding**, which is why this is
      one left-to-right pass and not four sweeps: a backtick inside an awk pattern in a
      shell single-quoted string cost `.ci/scripts/quality/check-trap-registry.sh` 296 of
      its 394 normalised lines, and the block-comment stripper ran the same hole in reverse
      -- a glob's `*/` in `scripts/gates/check-e2e-coverage.ts:233` closed a `/*` opened 27 lines
      earlier inside a template literal.
      **TWO LATENT DEFECTS FOUND IN THE GATE ITSELF.** `--seed` wrote only
      `{generated, files, shapes}`, so a single `--seed --force` would have DELETED all 25
      hand-written BLOCKER reasons and folded their shapes into the anonymous bucket. And
      `accepted` had no liveness half at all: `checkAccepted` proved a reason was well
      formed and nothing proved the finding still existed -- which is exactly why 9 of the
      25 were dead. Both fixed, the second as an exported `deadAccepted()`.
      **The composition was diffed, not the sizes:** of 88 added hashes, ZERO were at 3+
      copies under the old tokenizer, and the baseline was green at task start, so every
      addition is duplication the old tokenizer physically could not see. Controls 44 -> 56.
      Corpus 53174 -> 68274 normalised lines; 222 files grew and none shrank.
      **Numbers in the box that did not survive:** the corpus is 351 files not 345, and
      shapes at 3+ under the old tokenizer were 244 not 275 -- the seed's 275 dated from
      2026-09-07 and 56 had decayed. And "re-keys every fingerprint at once" is wrong:
      **190 of 279 fingerprints are identical under both tokenizers**, which is what made
      the hand re-key tractable rather than a guess.
- [x] Remove the two gitignored strays from the working checkout: `tsconfig.tsbuildinfo` and `audit-report.json`. **DONE 2026-09-07:** both were still on disk (7,203 B and 3,058,160 B); removed, and a third stray `.err` from a macOS bash 3.2 probe went with them. `git status --porcelain` no longer lists any untracked file.

#### W0.5 Driver contract and program decisions (serial head, blocks every sub-driver)
- [x] S Land `docs/ci-overhaul/08-driver-contract.md`: the W-key map, the arbitration table above, the single-writer lock table for `package.json`, `manifest.ts`, `ci-quality.yml`, `run-all.sh`, `test-hooks.sh`, `TRAPS.md`, `CLAUDE.md`, and the machine-mutex list (docker daemon, traefik namespace, `~/.rediacc`, port 4800, `account.db`).
- [x] S Record one uncontended full-run timing baseline as a tracked file. **DONE 2026-09-06 (d8a95af86):** docs/ci-overhaul/11-timing-baseline.md, 437 gates, wall 780.4s, serial 7021.0s, 9.0x. The receipt records the CONDITIONS too, because a number without them is how the four conflicting figures got into the drafts.
- [x] S Record the floor policy decision out loud: "retire file-count floors" is superseded by "floors must be set-based or corpus-derived, never hand-typed counts", since three workstreams raise floors and none retires them.
- [x] S Record the "modular and dynamic" acceptance test, so the requirement can be checked off: adding a gate, an allowlist or a hook requires no edit to any workflow, runner or dispatcher file.

#### W0.2 Runtime bug fixes (concurrent)
- [x] C Fix the logger clobber at the library in `.ci/scripts/lib/emit-advisory.sh:23-32`: assign colours only when UNSET (`${RED+x}`, because `.ci/scripts/lib/common.sh:26-31` deliberately sets `RED=''` off a tty), define each `log_*` only when `declare -F` fails, change `$1` to `$*`. Test the real chain (`common.sh` then `.ci/scripts/lib/blocker-validator.sh:26` then emit-advisory) capturing stdout and stderr separately, since the defect is a stream swap.
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
- [x] C One Node floor: `NODE_VERSION_MIN=22.13.0` in `toolchain.env`, read by `.ci/config/constants.sh:45` with `:?`, bound to both `engines.node` fields by a new sync control. Removes the masking fallbacks in `run.sh` and `setup.sh`.
- [x] C Redact the four AKIA ids in `agent/plans/PLAN-secret-namespace-migration.md:1615-1616`. The `:1617` value is a token id under a "new id" header, not a bearer, so no rotation.
- [x] C Make three count-bearing stale lines count-free so they cannot re-stale, and fix two narrow stale lines.
- [x] C Record ruling 7 in `docs/ci-overhaul/04-decisions.md` section A: the single-language rule, what bash survives, and that it supersedes `agent/plans/PLAN-shell-resource-profiling.md:7`. Mark that line superseded.

#### W0.1 Bitwarden token schema and cutover (serial, after W0.0 and W0.4a)
- [x] S Restructure `.ci/config/bws-token-expiry.json` to a `tokens[]` array and update its only reader. **DONE, box was simply never ticked:** the file carries warn_days plus tokens[], and the sole reader consumes the array at scripts/dev/bws-map-refresh.py:87. NOTE the plan's old path for that reader (.ci/scripts/quality/bws-map-refresh.py) does not exist and never did.
- (round 1, SUPERSEDED by a Round 2 box above) S Cut CI and local over to `mc-ci-read` and prove it by fingerprint, not by greenness: dispatch one workflow printing `sha256(client-id)` and compare.

Merge waves: wave 1 is W0.5, W0.0, all of W0.2, all of W0.3, W0.4a, all of W0.4b in parallel worktrees; wave 2 is the W0.1 schema box rebased on W0.4a; wave 3 is the cutover.

### W1: Python foundation (6 phases)
- [x] P1 Bootstrap and pin foundation. Serial head: nothing can be proved until Python has a package manager. Checksum-pinned uv shim, `UV_*` and `PYTEST_VERSION` in `toolchain.env`, the anti-vacuity fixture taught to copy the package, `toolchain.sh` stops hardcoding linux and bare `sha256sum`.  **DONE 2026-09-06:** W1 P1 bootstrap+pins landed (.ci/bootstrap.sh, pyproject.toml, uv shim)
- [x] P2 Package skeleton, root `pyproject.toml` replacing `ruff.toml`, the pytest gate placed in a lane that installs pytest, and the shared controls runner replacing the per-file Tally pattern.  **DONE 2026-09-06:** W1 P2 package skeleton + pyproject replacing ruff.toml + check:ci-pytest
- [x] P3 Core modules and the cross-language golden mechanism. Thirteen concurrent boxes, one module plus its tests each: log, paths, proc, gitx, ghx, dockerx, env, secrets, toolchain, workflows, hookio, allowlist, platform. Goldens prove `lanes` and allowlist verdicts byte-equal from both sides.  **DONE 2026-09-06 (412c2ee78), superseding the earlier 4-of-13 note:** twelve of thirteen exist under .ci/rediacc_ci; hookio is the thirteenth and lives under .claude/rediacc_hooks by the arbitration table, not here. The goldens landed with the allowlist module: 17 frozen corpora recorded from the REAL bash and TS readers under a provenance header, with a live three-way differential over the tree's actual lists. Nine mutation probes, the strongest killing 31 tests; a tenth passed at first and exposed that no real reason exercised normalization, which was fixed by deriving a corpus that does.
- (round 1, SUPERSEDED by a Round 2 box above) P4 Policy gates, the canonical path line, and the root-resolution sweep that removes the `sys.path` mutations. **RE-DERIVE BEFORE STAFFING: 67 files carry a `sys.path` mutation, measured 2026-09-07** (`grep -rln 'sys.path.insert\|sys.path.append' .ci/ .claude/`). It was 24 in the draft and 48 on 2026-09-06, so this box has grown on every measurement as the ports add Python. Do not staff it against a remembered number. Two other boxes (W6 P2, W8 P2) wait on this sweep, so its real size decides their scheduling.
- (round 1, SUPERSEDED by a Round 2 box above) P5 Package CLI, the WSL launcher, hook packages, and `INP001` no longer globally ignored. **THREE OF FOUR CLAUSES ARE DONE, measured 2026-09-07; only INP001 remains.** (1) The WSL launcher landed under W6 P1: `run.ps1`, 63 lines, `wsl.exe --cd` with UNC translation, plus `run.cmd`. (2) Hook packages landed at `166623039`: `.claude/rediacc_hooks/` is a real package with 51 guard modules and its own `tests/`, declared in `pyproject.toml` testpaths. (3) The PACKAGE CLI landed today: `.ci/rediacc_ci/__main__.py`, 195 lines, verb table as DATA (`VERBS: tuple[Verb, ...] = ()` at :85, handlers as dotted strings resolved lazily so `--help` imports nothing). Driven, streams captured SEPARATELY: `--help` rc=0 with 294 B on stdout and 0 B on stderr; no verb rc=2 with 0 B on stdout and 131 B on stderr, no traceback; unknown verb rc=2. Proven able to fail by a whole-CLI mutation run in a scratch copy with three planted defects: 8 failed, 8 passed. NO VERB WAS REGISTERED and that is correct, not a shortfall: the legacy dispatcher owns all 16 arms, and registering a name without deleting its legacy arm is the exact overlap `test-run-sh.sh` partitions against in both directions. `PORTED_VERBS` stays `()`; the run.sh change is comment-only, because lines 18-20 had become untrue. (4) INP001 is still in the global `ignore`; full removal needs W5 P7, but NARROWING it to `per-file-ignores` for the three flat script directories is available now.
**Headroom warning for W6 P3: `run.sh` is at 120 lines against a ceiling of 120, so `PORTED_VERBS=(setup)` is line-neutral only if it adds no comment line.**
- (round 1, SUPERSEDED by a Round 2 box above) P6 Strict flip of the language policy, after the ports land: no baseline file at all, only allowlisted bash remains.

### W2: Gate registry (7 phases)
- [x] W2.0 Binder foundations: parser v2 with a `kind` discriminant so gate-tests and sub-gates declare without a `step`, an explicit non-emitting class, an import guard, regions in every lane that has a setup step, fixture ignores. Fix the two files closing with `---- /gate ----`.  **DONE 2026-09-06:** W2.0 parser v2: kind discriminant, emit:false, import guard, malformed-header reporting, invariant-11 mechanised
- [x] W2.1 Registry loader and a committed `gates.lock.json` in manifest file order (pool.ts uses array index as its scheduling tiebreaker), with a drift gate.  **DONE 2026-09-06:** W2.1 gates.lock.json, 420 entries in manifest file order, drift gate in the same file
- [x] W2.2 Shadow-gate core: compare exit code plus finding sets, both-empty and new-side-true both count as mismatch, ledger records only clean trees. Usable by W4, W7 and W8.  **DONE 2026-09-06:** W2.2 shadow comparator, registered, 8 verdicts of which one is a pass
- (round 1, SUPERSEDED by a Round 2 box above) W2.3 Headers on every gate, then the lock and the generated manifest region (generated literal region plus a hand region for composites).  **HEADERS DONE 2026-09-06 (3e00bf8f4, fb42bb1ce): 148 of 148 gate tests declare, and the binder now READS them, which it did not when they landed. The generated manifest region is still open, so this box stays open.**
- [x] W2.4 Isolation as a path-scoped contract defined once and implemented identically in `pool.ts` and `run-all.sh`; inventories re-keyed; the three text readers drained; counts fixed.  **PARTIAL, CORRECTED 2026-09-07 BY MEASURING THE LOCK.** The three text readers WERE drained and pool.ts and the battery both implement the contract, so half the box is real. But the DECLARATIONS never landed: of the 148 gate-test entries in gates.lock.json, `mutex`, `reads`, `heavy` and `weight` are populated on **ZERO**, and only `slow` is set (34 of 148). No entry anywhere in the lock carries a `reads` key at all; `mutex` exists on 12 entries repo-wide, none of them a gate test. The consequence is observable rather than theoretical: the battery is running on its LOUD FALLBACK today, printing "no 'tree:' isolation declared in scripts/ci-runner/gates.lock.json; falling back to the hand-maintained W/S lists in this file" at :303-304. So the hand-maintained lists this box exists to retire are still the live source of truth, and W7 P3's `battery.py` inherits the same fallback. A contract implemented by two readers with no data to read is not done. **CLOSED 2026-09-07, and the root cause was a MISSING TYPE, which is why this sat green for a day.** `scripts/ci-runner/gate-spec.ts:45` declared `mutex?: string[]` and there was NO `reads` field at all, so the 21 scanner gate tests were UNDECLARABLE by construction while `.ci/scripts/test/run-all.sh:275-276` asked `classify_from_lock` for exactly that claim. Added `reads?: string[]` to the spec, then wrote 25 declarations into manifest.ts -- `mutex: ['tree:repo']` on the 4 writers, `reads: ['tree:repo']` on the 21 scanners -- 25 insertions and ZERO deletions, derived FROM the existing fallback arrays rather than invented, so this moves the classification into the registry instead of restating it. Lock regenerated, 456 gates, and it now carries `tree:` on exactly 4 mutex and 21 reads entries. THE PROOF IS A WARNING THAT STOPPED: the battery no longer prints "no 'tree:' isolation declared ... falling back to the hand-maintained W/S lists", stderr is clean and it exits 0.
The arrays remain on purpose as a fail-loud backstop -- their own comment says "no declarations yet" and "lock is broken" must not silently become "nothing needs isolating" -- but they are no longer the source of truth
- (round 1, SUPERSEDED by a Round 2 box above) W2.5 `paths` in two tiers: statically enumerable first with `paths_origin` recorded, traced second and only where the soundness oracle covers everything. No `private/<x>/**` globs.  **PARTIAL 2026-09-06:** REVERTED to open 2026-09-06: this box was marked done and it is not. `paths_origin` DOES NOT EXIST anywhere in the tree -- grep returns nothing, and gate-spec.ts declares only `paths?: string[]`. What landed is a PROSE COMMENT convention that nothing enforces and no gate can read. Only 35 of 420 lock entries carry `paths` at all. Tier 2 remains correctly unstarted.
- [x] W2.6 Shadow headers, CI emission, cutover procedure, and one real pilot pair cut over end to end.  **DONE 2026-09-07 (910933a57):** regions emit and own their steps; 112 hand-written duplicates removed, 10 jobs and 264 unique step names both before and after, actionlint green. The deleter guard written for one job-boundary failure found a SECOND at the other end of each span. **CORRECTED 2026-09-07 by measuring HEAD rather than believing the earlier note: this box is [x] for the REGIONS and carries a live defect. `gate:bind --write` does not emit per-step `env:` at all -- grep for `env` in scripts/gate-bind.ts returns only shebangs and test fixtures -- so the emission at 910933a57 landed steps with their env stripped. HEAD's ci-quality.yml holds 20 `env:` blocks where the correct file holds 26; the 11 missing lines sit on steps that READ them, including `check:ci-pr-task-trailers` (PR_HEAD_REF, PR_BASE_REF) and the Docker image freshness step (DOCKERHUB_TOKEN). The repair exists ONLY as uncommitted working-tree work in this shared checkout (711/340, 11 env lines added and zero removed, step-name set byte-identical at 274 = 274, check:ci-gate-bind green at 377 declared gates). An earlier session note in STATE.md said W2.6 was REVERTED; that is false and is corrected there too. main is unaffected -- it is far behind this branch -- so the defect is branch-local.
The box does not reopen, but the binder must learn `env:` before the next `--write`, or that write re-strips these 11 lines.**

### W3: CI-quick and parallelism (4 phases)
- [x] P0 The floor: dedupe the doubled suites (the worklist suite and the dead-bash real-tree scan each run twice per full run today) and split the three hook gates behind ONLY filters.  **DONE 2026-09-06:** W3 P0 both doubled suites down to one run each, delegated and asserted
- [x] P1 Packing: split every serial `&&` chain into manifest entries with a `gate: false` parent, shard lint four ways, backfill `paths`.  **DONE 2026-09-06 (f259e7ee1, a05d1cf84):** lint sharded four ways; four aggregate parents (check:i18n, check:ci-seo, check:ci-redirects, check:ci-i18n-cross-locale) flipped to gate:false with 20 children registered, taking REAL duplicated leaves from 16 to 3; nine paths sets landed, scoped entries 36 to 44. Acceptance verified independently of the proposal: check:i18n's children's leaves union equals its 28 declared leaves exactly. Also fixed check:ci-package-key-budget, RED at HEAD because gen:docs and gen:gates-lock were never registered; both are now gate:false / local-only manifest entries and the baseline SHRANK 49 to 48. The three remaining duplicates (typecheck-workers.sh, validate-tutorial-cast-output.js, check-cli-docs.ts) are separate findings.
- [x] P2 Heavy-job proxies and the parity surface extension. Wire the proxies that already exist (`test-rdc-update.sh`, `test-linux-packages.sh --dry-run`, the two missing unit keys, the Go unit subset, `license-e2e.sh`) and write the ones that do not (ops host check, the three untested CI scripts, a Stripe offline test, an elite compose proxy). Each returns 77 rather than 0 when its toolchain is absent.  **DONE 2026-09-06 (8280744b0):** ten proxies, each seen RED under a planted violation and each returning 77 (not 0) with its toolchain removed from a real PATH. Elite compose and the Stripe offline test CUT with evidence: one needs a worker VM behind a private submodule, the other forwards webhooks from a live sandbox.
- (round 1, SUPERSEDED by a Round 2 box above) P3 GitHub shard matrix, aggregator, `ci-quick` job and fail-open scoping. All ten lanes replaced by emitted shards with literal runners and timeouts; the aggregator reds on an empty include list, proven by a planted all-dropped run.

Targets: local full-run floor 785 s to 273 s (then lower once the hooks are ported); `ci:quick` at or under 58 s while covering more; quality tier wall at or under 9 minutes.

### W4: Policy folder and duplicate collapse (6 phases)
- [x] P0 Decisions and measured baselines, no moves. `.ci-trigger` stays at root with a recorded reason.  **DONE 2026-09-06:** W4 P0 decisions + baselines, .ci-trigger stays at root with its reason
- [x] P1 Seams: the path helper as a pure join with a validated name set and no registry file and no fallback; per-probe liveness floors; the two non-Python collapses (release-age, SEO prefixes).  **DONE 2026-09-06:** W4 P1 seams: policy-paths.ts as a proven no-op, per-probe floors, release-age collapse
- [x] P2 Movers. **NOT TWELVE CONCURRENT BOXES: ONE SERIAL WRITER.** Measured 2026-09-06 over the 14 root allow/block lists: ZERO of the 91 pairs have disjoint reader sets. scripts/lib/policy-paths.ts and .ci/rediacc_ci/tests/test_core_allowlist.py are each read by all 14, check-suppression-liveness.ts by 10, test-policy-liveness-floors.sh by 8. Staffing this twelve ways produces twelve conflicting branches. Still an atomic `git mv` plus readers plus liveness probe per list, but sequenced. Run W9 P1b FIRST: they share three files under scripts/.  **DONE 2026-09-06 (dee3ade8b):** FIFTEEN lists, not fourteen (the plan's count was doc drift; POLICY_FILES is the contract). ONE atomic change across the set, not one per list: POLICY_DIR is a single constant and eleven readers reach it only through policyPath(). 12 probes, 87 entries declared, byte for byte the pre-move baseline.
- (round 1, SUPERSEDED by a Round 2 box above) P3 One blocker-validator: record a three-way golden corpus from today's bash behaviour first, then Python canonical, bash shim and TS client, with the vendored breakpoint copy kept and proven a subset.
- (round 1, SUPERSEDED by a Round 2 box above) P4 Finalize: `pyproject.toml` adoption, the inventory gate, the prose sweep, Python `policy_path`.
- (round 1, SUPERSEDED by a Round 2 box above) P5 `bws-secret-map.json` into `.ci/policy`, deferred behind the Bitwarden cutover.

### W5: .claude hooks to Python (8 phases)
- [x] P0 Skeleton, dispatcher, harness seams and measured baselines (a fork counter, `GUARD_PASS`, `HOOKS_ONLY`).  **DONE 2026-09-06:** W5 P0 skeleton, dispatcher, harness seams
- [x] P1 Transliterate `command-scan.sh` (272 lines, 157 of them comments) with a differential over a captured corpus of at least 320 strings, plus the `/proc` portability layer with a `ps` backend.  **DONE 2026-09-06:** W5 P1 command-scan.sh transliterated, 387-string corpus, 28 fields compared
- [x] P2 Gate pre-keying and `require-python.sh` on all four matchers.  **DONE 2026-09-06:** W5 P2 require-python.sh on all four matchers, registered with the ORDER bump
- [x] P3 Port batches B1 to B3: 19 guards with no shellscan dependency, three concurrent boxes.  **DONE 2026-09-06:** W5 P3 first guard batch
- [x] P4 Port batches B4 to B6: the remaining 28 guards.  **DONE 2026-09-06:** W5 P4 remaining guards; 46 total, 17529 byte-for-byte comparisons
- [x] P5 Registration, surface gates, hook registry gate.  **DONE 2026-09-07 (166623039).**
- [x] P6 Cutover: harness calls the dispatcher, `settings.json` collapses from 65 command entries to 22, shims deleted, key space migrated.  **DONE 2026-09-07 (166623039):** settings.json 73 command entries to 30, 456 execs per Bash call to 35. Twins MOVED to .claude/oracles/, not deleted: they are what test_guards_differential compares against.
- (round 1, SUPERSEDED by a Round 2 box above) P7 Cross-OS, the `WORKLIST_*` registry, suite sharding, lifecycle collapse to 11 entries.

Targets: 2 processes per Bash tool call. **THE BASELINE THIS IS MEASURED AGAINST DOES NOT EXIST IN THE TREE, found 2026-09-07.** `git ls-files | grep -iE 'strace|exec-baseline'` returns ZERO, and there is no `GUARD_PASS` or fork-counter artifact anywhere, so W5 P0's stated deliverable (a fork counter) and the "456 execs to 35" figure in P6's note are both unreproducible today. A target defined against a missing baseline cannot be checked off, and that is the first thing P7 must fix. Measured directly instead: a Bash tool call currently fires **12 hook processes** before any in-guard forks (PreToolUse/Bash 4, PostToolUse 5 on the Bash matcher plus 3 on `*`), against the target of 2. All 374 `check` and 21 `check_out` assertions stay green throughout; `worklist-cases` is untouched.

### W6: Bootstrap, run.sh router and cross-OS (5 phases)
- [x] P1 Prerequisites, router split, launchers, entry tests. Two prerequisite defects land in wave 1 because everything depends on them: `scripts/gates/check-dead-bash.ts:152` has no `py` alternative in its TEXTUAL regex, and `scripts/ci-runner/run.ts:940` computes `whole` from only `--only`/`--skip`, so a `--changed` receipt currently authorises a push.  **DONE 2026-09-06:** W6 P1 router split: run.sh 120 lines, run-legacy.sh 1334, run.ps1/run.cmd
- [x] P2 Python platform layer, toolchain port behind a differential shadow gate, the four macOS bash fixes, and the one install table.  **DONE 2026-09-07 (aedb25109):** `.ci/rediacc_ci/setup/tools.py`, 22 rows, 9 pinned, WITH the pytest row the contract recorded as missing. `w6p2-toolchain` asserts equivalence over 5 distinct trees. The four macOS bugs were DRIVEN against a bash 3.2.0 built from source, not asserted: release-state-validator printed empty stdout and rc=1 for a HEALTHY release state, and blocker-validator's unquoted regex is a SYNTAX ERROR on 3.2 that killed the enclosing function so the allowlist parsed to zero entries. All four now refuse loudly with their version named.
- (round 1, SUPERSEDED by a Round 2 box above) P3 `setup` in Python with the phase table as data, the missing installs (ruff, shellcheck, shfmt, actionlint, uv, pytest, gitleaks, bws, tmux), `.claude` wiring, and opt-in git hooks.
- (round 1, SUPERSEDED by a Round 2 box above) P4 `rdc.sh` down to a 70-line shim, native CLI build moved into the package, macOS-complete setup, a macOS CI probe.
- (round 1, SUPERSEDED by a Round 2 box above) P5 Quality lane last, legacy file deleted, `LEGACY_ARMS_MAX` reaches zero.

### W7: .ci port (6 phases)
- [x] P0 Seams, baselines and counts that every later box is measured against.  **DONE 2026-09-06:** W7 P0 baselines as SETS; corrected three contract counts
- [x] P1 JS relocation out of `.ci`, and the two bash libs ported into `core` behind delegating shims.  **DONE 2026-09-06:** W7 P1(b) two bash libs behind fail-closed shims. P1(a) JS relocation REFUSED on measurement: 22 of 23 files drop from full to reduced CI
- [x] P2 Port the 74 `check-*.sh` plus 5 wrappers behind `@gate`, each with a `--selftest` control and a committed differential artifact over K distinct trees.  **PARTIAL 2026-09-06: 14 of 77 ported, 13 of 14 PROVEN (891b6ae87). Superseding an earlier 4-of-14 reading:**, refuted by running the comparator over every ledger: only npmrc, go-module-sync, cli-contract and compose-env reach `equivalence holds over 5 distinct trees`. TEN fail, not the six named earlier: the six earlier ports report 0 distinct clean trees, and batch A never reached K=5 either (peerdeps 3, appadmin 3, cmdtree 4). stagingtag has 6 clean trees but 3 are DISQUALIFIED by MISMATCH_FINDINGS rows, which is a recorded BEHAVIOURAL divergence rather than a bookkeeping gap. Original note follows: batch A (peer-deps, no-app-admin-perm, command-tree, staging-tag-guard) and batch B (npmrc, go-module-sync, cli-contract, compose-env) landed at 412c2ee78 and 939f6afc1, each EQUIVALENT over 5 distinct committed HEAD^{tree} ids. THE FIRST SIX ARE NOT ACTUALLY PROVEN: every one of their 34 rows carries clean:false against ONE shared tree id, so --assert reports 0 distinct clean trees and invariant 5 is unmet for all six. The cure found in batch B is to make each specimen its own committed git repo, and to run the new side under PYTHONDONTWRITEBYTECODE=1, since __pycache__ dirties the tree before treeIdentity is computed.  **"77 of 77" MEANS PORTED, NOT LIVE AND NOT DELETED. Re-measured 2026-09-07 after the operator asked why so many .sh files remain, which was the right question.** `rediacc_ci/quality` is referenced ZERO times in `package.json`, `manifest.ts` and `ci-quality.yml`, while `manifest.ts` still names `.ci/scripts/quality` 143 times: CI runs the BASH. 581 `.sh` files are still tracked under `.ci`/`.claude`, all 82 bash quality gates and all 149 bash gate tests are present, and nothing has been deleted. That is the DESIGN (invariant 5 forbids deleting a twin in the porting change; wiring is W7 P4 and deletion is W7 P5, both open), but quoting "100%" as a headline reads as finished and is not. Report three axes from now on: PORTED, LIVE, DELETED. They were 77, 0, 0.
**RE-MEASURED 2026-09-08 after NINE W7 P4 cutover waves: 77, 73, 0.** Wave 9 took
the last ten twins that had a registration to repoint -- release_state, branch, claude_attribution, commit_identity, pr_description, resolved_threads, review_comments, review_report_replies, submodule_branches, plus the earlier scope_scripts_reachability step rename -- each byte-identical to its twin on both streams with the same exit code on this tree, and each already asserting
equivalence over 5 to 14 distinct trees.

THREE OF THE LAST THIRTEEN CANNOT BECOME LIVE BY REPOINTING, and finding out why was the wave's real yield. `check-autopilot-no-bypass.sh`, `check-ci-job-aggregation.sh` and `check-swallowed-failures.sh` are invoked by
NOTHING: no `package.json` key, no `manifest.ts` entry, no workflow `run:` line,
no wrapper. CI runs their gate TESTS and never the gates, so each one's logic is exercised against fixtures while it never judges the real repository. `check:ci-parity` cannot see this, because a gate absent from BOTH sides is absent from the comparison. Two of the three exit 0 against this tree; the third refuses without an organisation variable. Tracked, with the registration
decision parked, rather than folded into a cutover it is not.

`staging_tag_guard` is the fourth and is excluded for cause: its ledger is the programme's one permanent red.

AND THE CUTOVER FOUND A MATCHER THAT HAD GONE EXTENSION-SHAPED, the same class as the `paths:` glob trap. `scripts/gates/check-ci-parity.ts` spelled its gate matcher `check-[\w.-]+\.sh` and expanded a path exemption to its package.json key only `if (e.entry.endsWith('.sh'))`. Both stopped applying the instant a gate was repointed at its `.py` port: rules R2 and R3 quietly stopped
judging it, and `check:ci-release-state` reported as an unregistered gate although its exemption named it. Both now accept `check_name.py` as well, with three controls that fail against the old spelling. The pilot took LIVE from 0 to 1 (`check:ci-npmrc`), and TWELVE more followed in two waves -- apbp, cli-doc-coverage, regions-sync, release-bump-skip, rubric-calibration,
www-build-token, then script-exec-bit, pipefail-grep-q, tracked-sidecars, go-tool-path, git-op-conditionals and probe-parity -- each on a shadow ledger asserting equivalence over 5-15 distinct trees, with both directions driven byte-identical and a violation planted through every seam. DELETED is still 0 and all 77 `.sh` twins are on disk, which is invariant 5 working, not a
shortfall. TWO MEASUREMENT TRAPS PAID FOR HERE. `grep -c rediacc_ci/quality gates.lock.json` is NOT the LIVE count, because the lock names ENTRY POINTS and never the module path. **The old wording here said it "reads 0 and always will", and that was falsified on 2026-09-08 by this programme's own edits: it read 2, then 3, and every move came from those edits.** The three hits, re-measured 2026-09-08 at
`scripts/ci-runner/gates.lock.json:1125`, `scripts/ci-runner/gates.lock.json:1147` and `scripts/ci-runner/gates.lock.json:3126`, are `toolchain_pins.py` and `account_portal.py` in `paths` entries added so those gates select under `--changed` when their port changes, plus `git_op_conditionals.py` in a `leaves` path. A probe whose value the programme moves itself every wave is a progress meter
measuring its own edits. A probe described as permanently zero is one a later reader trusts without running; it drifts, and then it reads as progress. LIVE must be counted as registered `.py` entry points that import a port. And `gate:bind --write` alone leaves the lock STALE -- `npm run gen:gates-lock` is what moves the number. Do not read the 41 `check:ci-*` keys pointing at a
`.ci/scripts/quality/check_*.py` as progress on this axis: that mis-measurement happened once already this session. Most of those are gates that were ALWAYS Python and never had a bash twin. Only SEVEN `.py` entry points import a `rediacc_ci.quality` module at all (autopilot_breakpoint_alignment, cli_doc_coverage, npmrc, regions_sync, release_bump_skip, rubric_calibration, www_build_token), each
still has its `check-*.sh` twin on disk, and for six of the seven `package.json` still names the `.sh`. The shim exists; the cutover has not happened. DELETED remains 0 and all 77 bash quality twins are present. **AND THE REASON LIVE IS 0 IS STRUCTURAL, not scheduling, measured 2026-09-07: ZERO of the 78 ported modules carries a `---- gate ----` header** (`grep -l -- '---- gate
----' .ci/rediacc_ci/quality/*.py | wc -l` -> 0). In this repo REGISTRATION IS THE HEADER, since `gate:bind` reads it, so W7 P4 cannot begin as a registration change: 78 headers must be written first, and no box costs that work. Five of the six entry points under `.ci/scripts/quality/` that import a port are referenced by nothing at all, and `check-dead-bash.ts` is bash-only so it
cannot see them: there is NO dead-Python gate. **DONE 2026-09-06 (1a1d7e445): 77 of 77 ported. RE-MEASURED 2026-09-07 over every ledger in .ci/shadow, which now holds 78 pairs, not 77: 77 of 78 assert `equivalence holds` at K=5.** The one red is w7p2-stagingtag and it is permanent: three tree ids disqualified by rows recorded through a hole since closed, 12 qualifying trees over 9
finding sets, so the claim is evidenced and only the assert cannot express it. No twin deleted: that is W7 P5.
- (round 1, SUPERSEDED by a Round 2 box above) P3 Gate tests to pytest: harness ported once, tests in subject batches, `battery.py` replaces `run-all.sh` and reads isolation from the lock. **FIRST STAGE IN FLIGHT 2026-09-07, and every "blocked" note on this box was STALE:** headers landed on all 148 under W2.3, isolation went onto the lock under W2.4, and W1 P2 put pytest in a lane that installs it, so nothing was ever holding it. On disk now: `.ci/rediacc_ci/tests/gates/` with `harness.py`, `conftest.py`, `test_harness.py`, `test_twin_parity.py` and, after batch 4 on 2026-09-07, NINETY-TWO ported subjects of 149 after batches 5 through 9 on 2026-09-07 (batch 4 was the first to run under the new `-n 8` concurrency, so a port that binds a fixed port or mutates a module global now flakes where it used to pass; batch 5 needed no `xdist_group` at all and each module records WHY in its docstring). **BATCH 5 FOUND A HOLE IN THE PARITY DRIVER ITSELF, now fixed:** `test_twin_parity.bash_cases()` counted a case as called only when the call was a BARE NAME on its own line, so a twin invoking `test_x "$D/y"` or `with_temp_dir test_x` matched nothing. Measured across the 130 twins that declare cases, 43 had at least one case invisible and 16 saw ZERO, falling through to the weaker flat-twin PASS-count floor -- so the SET comparison that module exists to perform silently did not happen for those 16, `test-ci-parity.sh` (22 cases) among them. That is failing OPEN. Widened to a word match excluding the declaration line and whole-line comments: 0 seeing zero, 0 with any miss, and zero newly-required cases missing from any of the 53 ports, so it strengthens the check without reclassifying existing work. **`check:ci-pytest` IS NOW DECLARED `slow: true`**, not as a regression but as the truth: the tier oracle measured its FLOOR at 367.9s, the gate runs all 9165 Python tests, and each batch adds roughly 200 more, ruff clean. Batch 2's ten were set-derived, not chosen: 148 minus the 6 already done, minus the 4 W and 21 S real-tree members, minus every twin naming a basename that appears in any of the 78 shadow ledgers (159 basenames), leaving 98 admissible; `test-toolchain.sh` was then excluded BY HAND because `w6p2-toolchain`'s ledger points at `.ci/shadow-drivers/`, a directory that NO LONGER EXISTS, so the filename filter cannot see what that pair covered. Every port planted a defect in the REAL subject and drove both sides; all ten restored byte-identical by sha256. Batch 3 read the W/S exclusion set FROM THE LOCK rather than from the bash arrays, which only became possible when W2.4's declarations landed hours earlier, and its parity driver asserts it every run: `none of the 29 ported twins is among the 25 real-tree test(s)`. **BATCH 3 ALSO SURFACED THE PROGRAMME'S NEXT BOTTLENECK, and it is now an operator order.** `check:ci-pytest` measured 810s for 8944 tests and IS the whole local wall time: run 3 was 675.3s wall of which that one gate was 675.3s, with 356 other gates finishing inside it. It runs SERIALLY on a 24-core box -- `import xdist` raises ModuleNotFoundError and pyproject.toml addopts carries no `-n` -- and the corpus grows about 200 tests per batch, so porting makes it worse. Tracked as worklist #d76fa6de under the operator's ordered sequence: plan, implement, validate, optimise again, validate. All 148 bash originals are still present, which is invariant 5 working as intended: a twin is never deleted in the change that ports it. The 148 `gate-test:*` manifest entries are the largest patch fragment in the programme and must be batched, or the driver becomes the bottleneck.
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
- [x] P1b scripts prep: repo-root module, `utils` merged into `lib`. **DONE 2026-09-06 (ca17aa055 + 891b6ae87):** git mv of console.ts, crc32.ts and translation-diff.ts, 24 importers fixed, scripts/utils/ gone, tsc and lint green, zero stale imports. Three inventories re-keyed in the same change per invariant 2. Its recorded blocker (22 of 25 importers dirty) was gone. NOTE 'operator bash relocated out' was NOT done and is not tracked anywhere else.  **THAT PARTIAL NOTE IS NOW FALSE, re-measured 2026-09-07:** `ls scripts/utils` returns No such file, `scripts/lib/{console,crc32,translation-diff}.ts` are all present, and `git log -- scripts/utils` ends at `ca17aa055 refactor(scripts): merge utils into lib`. The merge DID happen; the box carried two contradicting notes and the pessimistic one outlived the work.
- (round 1, SUPERSEDED by a Round 2 box above) P2 Domain moves and data relocation. Strictly serial, single writer: `enumeration-vacuity-baseline.json` **is an OBJECT `{note, unguarded: [42 entries]}`, not "one sorted array"** (verified 2026-09-07; read at `scripts/gates/check-enumeration-vacuity.ts:403` as `.unguarded`). The VERDICT is unchanged, and that is the point of correcting the description rather than the box: a rename still reads as growth to a shrink-only list, so this stays strictly serial and single-writer. But an implementer who greps for an array concludes the box is stale and skips the re-key.
- [x] P3 `eslint.config.js` split into six imported modules, proved byte-identical by a `calculateConfigForFile` differential over all 1,171 tracked lintable paths, plus RuleTester tests for the 35 rules that have none today.

### W10: Media pipeline separation (6 phases, stays bash)
- [x] P0 Preflight: shared fake-binary test scaffolding, and teach the dead-case-arm gate to open `.ci/media`.  **DONE 2026-09-06:** both already on disk from 8243c3a97; this became an AUDIT that found five real defects in that landing, all fixed.
- [x] P1 Extract seven modules into `.ci/media` with both copies coexisting; each box carries a fidelity assertion lifting the same body from both sources. Seven concurrent.  **DONE 2026-09-06:** W10 P1: .ci/media/ holds 11 modules plus tools/
- [x] P2 Cut over: `run.sh` and root `media.sh` become exec delegators. `run.sh` drops from 2,640 to at most 1,400 lines; `./run.sh help` stays byte-identical.  **DONE 2026-09-06:** W10 P2: media.sh is a 23-line exec delegator; run-legacy.sh routes media verbs to .ci/media/media-entry.sh
- [x] P3 Relocate the tts docker context and the R2 upload primitive with exec shims for the cross-repo callers.  **DONE 2026-09-06:** W10 P3: git shows R .ci/docker/tts -> .ci/media/tts, and .ci/media/tools/upload-r2.sh with shims
- [x] P4 Documentation accuracy, coverage probe, portability seams.  **DONE 2026-09-06 (412c2ee78):** five doc claims corrected against the tree (a dead SHA the 2026-08-23 rewrite killed but which still resolves locally; the TTS engine; the function home; a stale count; the credential path), two now MECHANICALLY enforced so they cannot rot. Battery green with docker/node/npm/aws/ssh/GPU/network all absent: suites=11 PASS=94, zero forbidden calls.
- [x] P5 Hand the language-policy BLOCKER strings to W1, which owns the gate.  **DONE 2026-09-07, verified against the tree not the report:** the gate landed today as `check:ci-language-policy`, and the strings ARE handed over. `.ci/policy/.language-policy-allowlist:35` carries the BLOCKER naming private/generative and private/growth as separate bash-native repos this one only orchestrates, immediately above `tree:.ci/media/`. The decisive check is that NONE of the 13 `.ci/media/*.sh` appears in the 521-entry frozen baseline: they are exempt BY NAME WITH A REASON, which is the goal state, rather than frozen debt. The other two entries, `tree:.ci/breakpoint/` (24) and `tree:.ci/tutorials/` (27), each carry their own BLOCKER.

Every new test passes with docker, node, npm, nvcc, aws, ssh, GPU and network absent.

### W11: Docs, records and the generator (7 phases)
- [x] P0 Generator first, before any content moves and before W2 touches the registry. `gen-docs.ts` with directory-scanned providers, plus the pre-port SET snapshot (row sets, not counts, because a floor of 300 passes after 88 of 388 gates vanish).  **DONE 2026-09-06:** W11 P0: scripts/gen-docs.ts plus doc-providers.ts and doc-regions.ts, gen:docs registered. Its parity gate was MISSING and LANDED 2026-09-06 (412c2ee78) as check:ci-doc-region-parity plus gate-test:doc-region-parity. It is not a subset of gate-test:docs-gen, which was the standing reason for not adding it (decision O-1, now refuted): gen-docs DISCOVERS its targets and that test asserts only that at least one was found, so a document losing its markers stops being checked instead of failing. Measured by stripping CLAUDE.md's markers and watching gen-docs still report ok.
- [x] P1 Stale lines, decision record 07, the master checklist, the port brief. Eight concurrent, disjoint files.  **DONE 2026-09-06:** W11 P1: 07-master-checklist.md, 07-port-brief.md and 07-tooling-decisions.md all exist
- [x] P2 CLAUDE.md slimming wave 1 with its first generated spans. 759 lines to at most 580, Session Defaults byte-identical.  **DONE 2026-09-06:** W11 P2: CLAUDE.md 784 -> 580 lines (target was at most 580), two generated spans, Session Defaults byte-identical
- [x] P3 Seam widening. **DONE 2026-09-06 (d2f764fbe) and proven a no-op the strong way:** verdict stdout AND stderr byte-identical before and after, with determinism confirmed FIRST over three runs so the identity means something. Both seams are repo-relative file lists with three refusals a list needs (declared path absent, two guard dirs sharing a final segment, zero folding harnesses). 14-step both-direction plant harness, 0 mismatches. Also fixed a pre-existing floorcheck false positive whose window excluded the fold line itself. Driver added scripts/data/hook-audit-scope.json to the gate's paths: it now decides the entire audited corpus, so without it a commit touching only that file would not select the gate.
- (round 1, SUPERSEDED by a Round 2 box above) P4 Docs tied to the registry, the policy folder, the hooks port and the test split.
- (round 1, SUPERSEDED by a Round 2 box above) P5 Docs tied to bootstrap, the CI job graph, the env manifest and the media folder. CLAUDE.md to at most 440 lines and 30 KB. **Gap measured 2026-09-07: CLAUDE.md is 580 lines / 36,756 B, so 140 lines and 6,756 B over.**
- (round 1, SUPERSEDED by a Round 2 box above) P6 Final consistency sweep, submodule pointer, records close-out.

### W12: agent/ history as attested records (variant A, lean cliff)

Forcing function: the housekeeping gate demands deletion of 33 plans on 2026-09-23 and 13 more on 2026-10-06. Phase 1 must be on main by 2026-09-20. Investigation facts: 79 plans and 2.0 MB; 37 of 71 commit citations dangle; 67% of judge-recorded artifact paths do not exist; no worklist event records a commit; `agent/archive/plans/` is named by config but does not exist;
SessionStart opens all 79 plans to print 49 filenames.

Record grammar: header lines within the first 10 (`Status: compacted|parked`, `Full-Text: <sha9> <path>` optional when `Full-Text-Blob:` is present, `Record-Sig`), then `## Why`, `## Outcome`, `## Lessons` (trap and decision ids), `## Boxes` (box lines byte-identical, each followed by a 4-space `(record) sig=.. done=<sha9>|open|abandoned item=.. epic=..` line that `BULLET_RE` and
`plan_tasks` ignore), `## Record` trailer in the TRAPS grammar including a `Read-History` line carrying the `git show` and `git log --find-object` commands, and `## History` bullets appended only. Record at most 6 KB plus 160 B per box, and the pointed blob at least twice the record.

#### W12.P1 Compaction that survives rebase (on main by 2026-09-20)
- [x] P1.1 `wl_planrec.py`: parse and render the grammar; `resolve()` for commit, ancestor-of-origin/main, blob, file:line, gate, plan, trap, decision, reusing the four existing verification idioms; `derive()` computing Full-Text, blob, Epics from PR-TASK trailers, Touches from `plan_orientation`, Gates, and `done=` per sig by walking the ledger's history; `record_sig`; `launder()` replacing unresolved tokens with `[unresolved]`; `render_index`.  **DONE 2026-09-06:** W12 P1.1: wl_planrec.py, 2214 lines
- [x] P1.2 Statuses: `compacted` into the finished sets, `parked` into not-started.  **DONE 2026-09-06:** W12 P1.2: statuses in wl_planfile.py
- [x] P1.3 `worklist.py --plan-compact` and `--plan-revive`, with refusals, blob-only pointers when the text is not yet on origin/main, one bounded `claude -p` under `--why model` using the existing `WORKLIST_JUDGE_MODEL` (haiku), laundered, written via tempfile and `os.replace`, never committing.  **DONE 2026-09-06:** W12 P1.3: --plan-compact and --plan-revive in worklist.py
- [x] P1.4 `check_plan_record.py`, hand-registered in `quality-branch` per invariant 11: ten rules R1 to R10 with self-control first, a floor, pointer resolve and live, blob equality and size ratio, `done=` proven against the ledger blob, `(record)` inside a box line red, the placeholder under `compacted` red, and `agent/INDEX.md` equal to the render.  **DONE 2026-09-06:** W12 P1.4: check_plan_record.py registered in package.json, manifest.ts and ci-quality.yml quality-branch, hand-written exactly as this box specifies
- [x] P1.5 Housekeeping: compacted plans with a resolving blob are exempt and counted; `parked` stays on the clock; abandoned-annotated boxes leave the ledger's open set; the remedy becomes work-or-compact and DELETE is removed.  **DONE 2026-09-06:** W12 P1.5: housekeeping exemption in check-plan-housekeeping.sh
- [x] P1.6 `block-compacted-plan-edit.sh`, denying edits to a record and printing the `git show` and revive recipes.  **DONE 2026-09-06:** W12 P1.6: .claude/hooks/pre-edit/block-compacted-plan-edit.sh, baselined and covered
- [x] P1.7 SessionStart and the plans block read `agent/INDEX.md` instead of opening 79 plans, with an INDEX STALE state and a census fallback.  **DONE 2026-09-06 (412c2ee78):** 166 file reads to 1, 56.9ms to 2.2ms, whole hook 134ms to 68ms, output byte-identical (HEAD's own plans_block exec'd beside the new one). The brief's premise was WRONG and the correction is the finding: render_index indexes compaction records only and returned the empty string, so P1.7 needed a second census table in the same file plus an R8 that knows about it, not a wiring job. Named blind spot: freshness is stat-only, so a same-length status edit is invisible locally; R8 byte-equality closes it in CI.
- [x] P1.8 The wave PR. **HALTED AND RESTARTABLE 2026-09-06.** Both batch agents were stopped mid-run because the compaction TOOL mis-titled every record: title_of() had an off-by-one in the slug fallback (slug[4:] where len('PLAN-') is 5), no code-fence awareness (a shell comment became a title), and worst, its header-field guard matched any `Word:` so `# PLAN: ...` read as a field, sending 62 of 83 plans to the slug fallback. Fixed at d2f764fbe with all three cases tested both ways. A SECOND defect is agent-side, not tool-side: one record's Outcome said a plan 'was never implemented' when it shipped in 120cd9e73, because the compactor believed a stale `Status: draft` header. Both agents were sent the rule (a header is a claim, the tree is evidence) before being stopped. THREE records already written carry bad titles and must be revived and redone: PLAN-lint-rule-matrix-probe, PLAN-lint-css-ci-wiring, PLAN-greenlight-verify-at-read.  **DONE 2026-09-06: 32 of 32 aged plans compacted.** The titling defect that halted the wave was fixed at d2f764fbe and the three bad records were revived and redone.

#### W12.P2 History pushed at the edit; second wave (before 2026-10-06)
- [x] P2.1 `why_lines()` and `--plan-why <path>`, with an affirmative empty answer.  **DONE 2026-09-06:** W12 P2.1: why_lines and --plan-why in worklist.py
- [x] P2.2 `why-on-edit.py`. **DONE at 8243c3a97, never ticked:** 322 lines, registered at .claude/settings.json:179. Every clause present: once-per-path-per-epoch (:186-193), the cap (:87, :282), silence with no edge (:24-28, :288), similar-plan block on a new plan Write (:127, :273).
- [x] P2.3 PostCompact and the CI-red history hook both append why lines.  **DONE at 8243c3a97, never ticked; verified 2026-09-07 against the tree rather than the note:** both halves are self-labelled `W12 P2.3`, PostCompact at `.claude/hooks/stop/wl_checks.py:2348-2361` and the CI-red hook at `.claude/hooks/stop/wl_histfirst.py:173-189` (208 lines, wired at `.claude/hooks/stop/wl_checks.py:4272`).
- [x] P2.4 `check_plan_citations.py`. **DONE at 8243c3a97, never ticked:** 568 lines, parser-blind floor documented at :60-65 and implemented at :366, registered in all three places (package.json, manifest.ts with paths, .github/workflows/ci-quality.yml:569). It is live and catching things: it refused two of this plan's own citations today.
- [x] P2.5 `--plan-tick` with evidence, flipping the box and updating the ledger in one run.  **DONE 2026-09-06:** W12 P2.5: --plan-tick in worklist.py
- [x] P2.6 Pointer stamps on store compaction and on every STATE.md write. **DONE, never ticked:** both halves use the real pointer_stamp from .claude/hooks/stop/wl_planrec.py:1371. Store compaction at .claude/hooks/stop/wl_store.py:1814-1820 (dict.fromkeys, not a set, because the compactor's own file is both in `clear` and the target). STATE.md at .claude/hooks/stop/worklist.py:1521-1529, taken INSIDE the lock and BEFORE the os.replace, which is the only ordering that makes the stamp true. Both imports suppressed, so a stamp never gates a write.
- (round 1, SUPERSEDED by a Round 2 box above) P2.7 **"A5" POINTS AT THE WRONG FILE, verified 2026-09-07: `grep -cE '\bA5\b' docs/ci-overhaul/04-decisions.md` returns 0.** `A5` and `A6` are GATE RULES in `.ci/scripts/quality/check_plan_boxes.py:41-44` (A5 = a plan may only be deleted wholesale once older than delete_days AND only when deletion actually loses a box; A6 = the scan is not vacuous). The clause therefore reads: **`check_plan_boxes.py` rule `G-A5` becomes never-delete.** Plus two TRAPS entries; CLAUDE.md gains "search first" (0 hits today); the grammar is documented.
- (round 1, SUPERSEDED by a Round 2 box above) P2.8 Second wave. **NOT 13 PLANS AND NOT 2026-10-06, re-measured 2026-09-07.** `check-plan-housekeeping.sh` reports 86 tracked plan(s) with 32 compacted, so **54 are uncompacted**, four times the recorded figure. The next red is **2026-09-25** (2 plans) and then continuous, not 2026-10-06. Staffing this against the old numbers under-provisions it and misses the deadline by eleven days.

#### W12.P3 Registers and remaining edges
- [x] P3.1a Epics durable: the TMPDIR sidecar moved into `agent/worklist/`. **DONE:** .claude/hooks/stop/wl_epic.py:36-37.
- (round 1, SUPERSEDED by a Round 2 box above) P3.1b **THE STATED PREMISE IS REFUTED, re-scoped 2026-09-07.** "Nothing asserts every PR-TASK id has an epic event" is false: `scripts/gates/check-pr-task-trailers.ts:68-81` emits `unknown-epic` for an unknown id, with both directions controlled at `:106-125`. The gap that actually survives is narrower and worth stating exactly, because the old wording sends an agent to build something that exists: `known` is scraped from a MARKDOWN SNAPSHOT (`:272`, `:277`) rather than read from a `wl_epic.py` event, so the assertion is against a document that can drift, not against the ledger.
- (round 1, SUPERSEDED by a Round 2 box above) P3.2 `DECISIONS.md` with ids, seeded from `04-decisions.md` and the ten locked decisions in the secret-migration plan. **THE "A6 OVERRIDE RULE" IS `04-decisions.md` SECTION A ITEM 6** (`:22-23`, `Do not stick on what I say. Better ideas are welcomed`), an OPERATOR RULING, and NOT the gate rule A6 in `.ci/scripts/quality/check_plan_boxes.py:42-44`, which is the anti-vacuity clause. P2.7 and P3.2 sit two boxes apart and pointed at OPPOSITE FILES under the same-looking token, which is exactly the confusion the new file must end. **The ids must be PREFIXED (`D-A6` for a decision, `G-A5`/`G-A6` for a gate rule) so the collision cannot recur.**
- (round 1, SUPERSEDED by a Round 2 box above) P3.3 Canonical status vocabulary in config; the three state sets built from it.
- [x] P3.4a The three header keys PARSE: wl_planrec.py HEADER_FIELD_KEYS carries Supersedes, Extends and Related, and they are correctly excluded from being read as a title.
- (round 1, SUPERSEDED by a Round 2 box above) P3.4b Nothing RESOLVES them to a real plan: `git grep 'Supersedes' -- '.ci/scripts/quality/*'` returns nothing. Split out 2026-09-06, same shape as P3.1, because the box read as one unit while its first half was silently complete. Run it AFTER the compaction wave: its gate change alters what check_plan_record.py accepts while that wave runs --update against agent/INDEX.md all the while.
- (round 1, SUPERSEDED by a Round 2 box above) P3.5 Measure before blocking: a two-week advisory census before any blocking rung.

## Gaps still unowned (assign before launch)

- [x] **THE LANGUAGE-POLICY GATE NOW EXISTS. This entry was written and closed the SAME DAY, 2026-09-07**, which is worth leaving visible rather than deleting: the gap was real when found and the fix landed hours later. Built as ADVISORY and shrink-only (`check:ci-language-policy`, 521-path SET baseline, 3 BLOCKER-gated exemptions, registered and green), because blocking against 520 non-exempt shell files would have redded the tree and been suppressed within a day. **The STRICT FLIP is still open and is W1 P6**, whose job is to delete the baseline entirely. Original finding follows. ~~THE LANGUAGE-POLICY GATE ITSELF DOES NOT EXIST, and no box in this plan creates it.~~ Found 2026-09-07: `grep -rin 'language.policy'` across every tracked `.ts/.py/.sh/.json` (excluding node_modules, .git and docs/ci-overhaul) returns NOTHING. No baseline file, no allowlist, no `POLICY_FILES` slot. So **W1 P6 has nothing to flip** and **W10 P5 has nothing to hand its BLOCKER strings to**, and both read as ordinary pending work while their subject is absent. It also sits on the live critical path. Landed 2026-09-07 as a shrink-only gate. **CORRECTION to the earlier framing, verified in the code 2026-09-07: it is NOT advisory. `run()` returns 1 on growth (`.ci/scripts/quality/check_language_policy.py:850`), so it BLOCKS, with a frozen floor of 521 paths.** "Advisory" was the wrong word for shrink-only: it does not demand the 521 be fixed, but it fails the build the moment a 522nd appears. In flight as a shrink-only gate (blocking today would red ~119 tracked `.sh` and be suppressed within a day, which is the failure `suppressions.md` exists to prevent); the strict flip stays W1 P6. Its baseline is a SET of paths, not a count, per this plan's own floor policy.

- (round 1, SUPERSEDED by a Round 2 box above) Requirement 15 (organize `.json`): one box owning a predicate and a table for the 8 root json files, the 8 left in `.ci/config` after W4, and the 20 in `scripts/data`.
- [x] `package.json` key budget. **ALREADY SOLVED, measured 2026-09-06:** 343 keys total, 295 scheduled by the manifest and therefore exempt by classification, 48 hand-written against a baseline of 48. Registration boxes do not consume budget, so this gap does not exist. Original text: 307 script keys today and every registration box appends. A shrink-only baseline with a gate-key exemption class, plus one box per workstream naming which keys it retires.
- [x] Comment archaeology for the gate and test ports. **The box was OVERSTATED and is now true: the 0.90 floor was PRINTED and never ENFORCED.** assertEquivalent, the only ruling function, never read row.comments, so --assert returned 0 with every row below the floor; the word 'refused' in 5c described a human. Closed in code at b8fe82264 with a three-direction control. Not masking a live violation: the worst ratio across 100 recorded rows is 2.95. Originally closed by driver-contract section 5c, which makes a comment-byte ratio of at least 90 percent a port acceptance criterion recorded in the differential artifact each twin already produces, plus a short list of every original line naming a date, run id, sha or issue number for a reviewer to confirm survived.
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

The root driver writes no code and owns three things: the registry merge queue (`package.json`, `manifest.ts`, `ci-quality.yml` have exactly one writer in flight; every sub-driver hands over a branch whose gate file and registry entry are in the same commit, and only the root driver runs `gate:bind --write`, once per wave, pasting the `dropped` list into the wave record); the
machine mutex (at most one docker, account or traefik box in flight, because worktrees do not isolate the daemon, `~/.rediacc`, port 4800 or the router namespace); and the reference worktree that produces every timing number.

Wave shape: wave 1 is T1 in full, T6's two prerequisite fixes, T10's generator and seam widening, T7's decisions and the first passthrough box, T9's preflight. Wave 2 is T3's bootstrap and skeleton, T2's binder and loader, T8's prep, T4's skeleton through pre-keying, T9's extraction. Waves 3 to 5 are the four cutovers, independent of each other after M4: hooks, quality, Bitwarden,
and registry then .ci port. The final wave is the language gate flip plus the records close-out.

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

**W2.3 HAS FALLEN OFF THE PATH**, proven empirically rather than argued: 41 subjects are ported and running with NO manifest region and no manifest entries at all, under the single `check:ci-pytest` entry (`scripts/ci-runner/manifest.ts:5573`), because `testpaths` already covers `.ci/rediacc_ci/tests/gates`. So W7 P3 needs no registration and no driver involvement, and W2.3's open
half blocks nothing.

**A PREREQUISITE IS MISSING FROM THE PATH ENTIRELY**: W7 P5's third clause is "language gate blocking for `.ci`", and that gate does not exist (see the Gaps section). It has to be BUILT before W7 P5 can be flipped.

Live path: **W7 P3 (107 of 148 remaining) to W7 P4 (201 unique scripts, 334 call sites) to [BUILD the language-policy gate] to W7 P5 (138 .sh) to W11 P6.** W7 P3 is the single largest body of work in the programme and the only thing on the path that can start today.

## The control-plant class is enforced in ONE language, swept 2026-09-09

`check:ci-python-control-plants` refuses a control mutant built by raw substitution: if the needle has gone, `str.replace` returns the fixture UNCHANGED and the control then scans the same text as its neighbour while asserting the opposite verdict, passing for free. The sanctioned helper is `rediacc_ci.controls.plant`, which raises `VacuousPlantError` instead.

**That gate covers Python only, and the sweep found the other two surfaces uneven:**

* **Python** -- one live instance, `.ci/rediacc_ci/quality/git_op_conditionals.py:1114`,
fixed; the gate is rc=0 so the language is clean by its own instrument.
* **TypeScript** -- no gate, two candidates. `scripts/gates/check-guard-mutations.ts:193-199`
already counts occurrences and throws unless exactly one, which is `plant`'s contract inlined and correct. `scripts/gates/check-backup-bucket-conformance.ts:149` had no check; a vanished needle there fails LOUDLY rather than passing, because the assertion's polarity happens to run the other way, but it fails with a message about the wrong thing. Given the same occurrence check.
* **Bash -- the real gap, and it is not small.** Gate tests plant with `sed -i` and almost
none verify the plant landed: `grep -rn 'CONTROL PLANT DID NOT LAND'` finds **2 sites in the whole repository**, against `sed -i` plants spread across the gate-test corpus. A bash plant that silently fails to apply is exactly the failure this class describes, and `.ci/scripts/test/gates/test-run-sh.sh` already proved the shape is live when its own control printed "CONTROL PLANT DID
NOT LAND ... plants nothing and passes for free".

**The fix is to extend the gate, not to hand-audit the corpus** -- one instrument covering all three languages, with the bash arm requiring a post-plant assertion. Sized as writer work and deliberately not started inline; recorded here so it is not rediscovered.

## A green that proved nothing, found 2026-09-09 by fixing one half of a pair

`test_gate_doc_region_parity` builds a fixture by copying tracked paths and running the real `gen-docs` inside it. Both the Python port and its bash twin (`.ci/scripts/test/gates/test-doc-region-parity.sh`) carried the SAME hand-written six-item list, and both had fallen behind the providers: each new seam produced either a node `ENOENT` inside the generator or its anti-vacuity
refusal, neither of which reads as "the fixture is stale".

**`test_twin_parity` was GREEN throughout, because it compares verdicts and both sides were red.** It logged `twin and port agree (both red)`. Two broken things agreeing is a green that proves nothing, and nothing could expose it until one side was repaired -- fixing the port turned parity RED, which is that gate working for the first time on this pair.

Both sides are now DERIVED rather than enumerated: every quoted literal in `scripts/gen-docs.ts` and its two libraries that resolves to a tracked path IS the input set, so a provider has to name the seam it opens and the literal is the declaration. Both independently produce **38 pathspecs**. The port walks the import closure and refuses a closure of one; the twin takes the three
closure files literally and refuses a set under ten.

Three traps paid for in the repair, all measured:

* **`tar -c` needs `--no-recursion`.** The derived set includes the four `private/*`
GITLINKS, and tar recurses a directory name by default, walking each submodule's on-disk tree with its `.git` included.
* **A file is not a literal inside itself.** The deriver reads the three closure files for
quoted paths, so it can never yield their own names; omitting them gives `Cannot find module <fixture>/scripts/gen-docs.ts`, which reads as a broken copy rather than a missing input.
* **Copying the whole tracked tree was measured and rejected:** 5431 files / 2.0 GB,
because the `private/*` gitlinks dominate, times seven fixtures per run.

Now: twin rc=0 with 9 PASS, port rc=0 with 9 controls, and `test_twin_parity` reports
`twin and port agree (both green)`.

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
