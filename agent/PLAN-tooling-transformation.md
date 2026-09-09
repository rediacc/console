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
| Gate tests ported / live / deleted | 124 of 149 / 124 / 0 (2026-09-08) | `grep -rh '^BASH_TWIN' .ci/rediacc_ci/tests/gates/*.py \| sort -u \| wc -l` |
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
- **Nothing in the tree checks a step's `env:` at all.** `scripts/gates/check-ci-parity.ts:29` states as a
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
      `73bd8f7ec` had already drained the `.ci` hops onto `_cipath.py`, and the real residue
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
- [ ] **W7P4-Q S batches, 2 writers** The quality-tree cutover -- this is P-A. Six batches of 13.
      **RE-MEASURED 2026-09-08 from the tree and not from a report: LIVE 75 of 77.**
      **COMMITTED 2026-09-08 as `73bd8f7ec` (81 files, 9268 insertions), operator-authorised
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
      **DESIGN 2026-09-08: DO NOT STAFF YET, for two measured reasons.**
      **(a) `PRE-B2` DOES NOT EXIST.** The only `PRE-*` boxes in this plan are PRE-A0 and
      PRE-A1. A writer reads the name as either "blocked" and stops, or "no such box" and
      starts too early. Name the real dependency (probably `B2`) before staffing.
      **(b) The acceptance is false-positive AND false-negative prone.** It says the set of
      `.ci/**/*.sh` paths in the workflows must strictly shrink -- but **31 of 290
      occurrences are on COMMENT lines** and 10 distinct paths appear only in comments, two
      of them naming files that no longer exist. Deleting a stale comment would tick the box
      having flipped nothing; flipping a call site whose path also appears in a nearby
      comment reads as a failed flip. Count only occurrences under a `run:`/`with:` key.
      **The surface is 27% smaller than the box says**, because the uncommitted W7P4-Q
      cutover already removed 57 references: 215/348 at HEAD, 158/290 in the tree, and the
      true `run:` surface is **147 scripts / 258 call sites**. Partition by WORKFLOW FILE,
      not by script -- the workflows are the contended, driver-only resource.
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
      Also unresolved by the deletion: `.ci/rediacc_ci/tests/test_battery.py` is a
      differential whose `TWIN` constant IS `run-all.sh`.
      **PRECONDITION STATUS 2026-09-08, measured not claimed.** `agent/PLAN-extension-shaped-matchers.md`
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
      to fire: `.ci/scripts/test/gates/test-ci-parity.sh` plants a `check_planted_port.py` step (the GATE_SHAPED
      widening above had NO control until then); `.ci/scripts/test/gates/test-gate-paths-exist.sh` scans `*.py`
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
      `.ci/scripts/security/shfmt.sh:71-73` whose margin goes 2.8x to 1.7x,
      `.ci/rediacc_ci/tests/test_battery.py:352`,
      `.ci/rediacc_ci/quality/pool_writer_safety.py:545`).
- [ ] **W7P6 C, 3 writers** The 142 unnamed files (P-C). Port groups above; allowlist the 7-8
      named. Resolve the missing allowlist kind for `bootstrap.sh` before the strict flip.
- [x] **W1P4 C, after PRE-A1** The full `sys.path` sweep. **DONE 2026-09-09, and the box's
      number was wrong in both MAGNITUDE and DIRECTION: 36 files / 39 hops, not "68 and
      rising", and HEAD `73bd8f7ec` carries 45 -- so it FELL.** That commit removed nothing:
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
      committed unformatted in `73bd8f7ec`, UNMASKED `aea2bc733552`, a pre-existing tail
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
- [ ] **B4 S** The `ci-quick` job and **fail-open** scoping. Only 45 of 458 entries declare
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
      generated set contiguous would move **262 of the 264**. `scripts/gen-gates-lock.ts:99`
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
      exactly, because `scripts/gen-gates-lock.ts:99` still makes the array index behaviour.
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
      No entry moves, so the array index -- which `scripts/gen-gates-lock.ts:99` makes
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
- [ ] **C2 C** W2.5 tier 1: `pathsOrigin` required whenever `paths` is present.
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
- [ ] **D4 S** Lifecycle collapse 30 -> 11. The redundancy is mechanical: `require-jq.sh` and
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
- [ ] **W0.0-B S, GENUINELY OPERATOR-BLOCKED** Mint `mc-ci-read`, `mc-rotate`, `dev-shared`. No
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
        **MATCHES** the live token, recomputed the way `scripts/dev/bws-map-refresh.py:83` does
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
- [ ] **W0.1 S, blocked on W0.0-B** Cut over by fingerprint. **Acceptance:** a dispatched workflow
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
      **The honest control:** run it against `19c45c78e` and assert it reds with exactly
      `{.language-policy-allowlist}`. A gate that cannot detect the drift that already happened is
      not the gate.
- [x] **W4 P4c C** The prose sweep gets a PREDICATE, absorbing the stale
      `scripts/gates/check-suppression-liveness.ts:61` comment ("Today POLICY_DIR is '' and this is a provable
      no-op", untrue since `b80552370`). Rules: no comment may assert a `POLICY_DIR` value
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
      19c45c78e` then `checkout-index --prefix` -- touches neither worktree nor real index.
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
      **F1, repaired forward and not asked for:** `73bd8f7ec` routed 81 entry points through
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
      miss); `scripts/dev/deploy-bench.sh:137` retarget before W9 P2 moves it;
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
- [ ] **W8 P5** Spec + gate available NOW (the truncation target is the `machine-local` shard);
      **seeding OPERATOR-BLOCKED** on `dev-shared`, which has zero tracked hits.
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
- [ ] **W11 P5c BLOCKED ON W8** The `env-manifest` region has no home until W8 P2 exists. Record
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
      fixed at `65f1aa803`), and **"a stale `Status:` header is a CLAIM; the tree is EVIDENCE"**,
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
- [ ] **W11 P6a S, OPERATOR-GATED, blocks P6b and U2** Settle `private/account`. It is on a
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
      different tree. STILL OPEN: the `scripts/gen/` and `scripts/ops/` legs. Eleven loose `.ts`
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
      **STILL OPEN: `gen-docs.ts` and `gen-gates-lock.ts`**, which the `generators` rule
      itself blocks -- "scripts/gen-docs.ts, scripts/gen-gates-lock.ts,
      scripts/lib/doc-providers.ts and scripts/lib/doc-regions.ts are W11 and W2 files under
      active concurrent edit; they move only once those workstreams have handed over."
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
- [ ] **U2 S after P6a, OPERATOR-GATED** Cross-repo PRs. **`private/growth` is not a submodule** --
      `.gitmodules` lists four and `.gitignore:85` ignores it. That clause cannot be executed as
      written; split it into a decision box (documented clone-and-remote procedure, or promotion
      to a real submodule). Name an owner and record the merge order the `pr-merge` skill encodes.
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

Status: READY. Twelve workstreams drafted by Plan agents, attacked by two adversarial reviewers each, revised against evidence, then ordered and criticized for completeness. Discovery and design artifacts: a per-session scratchpad under /tmp (7 reports), long since cleared (7 reports) and the workflow journal under `.claude/projects/.../workflows/wf_2e95f418-6a8/`.

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
- **The bash-coverage ruling is re-opened out loud** as `04-decisions.md` ruling 7, per that file's own `D-A6` licence.

## A grammar addition landed 2026-09-07: `needs-not:`

`inferredNeeds` deliberately OVER-infers, and that asymmetry is correct: over-inferring
only blocks a declaration, while under-inferring kills a gate on a clean runner. But it
reads ORDINARY STRING LITERALS after `stripProse` has removed the docstrings, and a
control's own description routinely names a tool it never runs. Measured:
`ctl.check("TOOLING: an absent npx yields 127, not an exception")` infers `node` for a
pure-Python gate.

Tightening the pattern was REJECTED ON MEASUREMENT rather than taste: requiring command
position for `npx`/`tsx`, as the code already does for `node`, drops the inference on 24
files, and at least one of them (`.ci/rediacc_ci/tests/gates/test_gate_policy_path.py:48`) really does execute
`node_modules/.bin/tsx`.

So the safe default STAYS and the escape is ARGUED: `needs-not:` subtracts one inferred
capability and REQUIRES a `blocker:` reason, refusing without one. Proven both ways, and
it took `.ci/scripts/quality` from 48 of 49 Python gates declaring to **49 of 49** --
`check_checkout_cone.py` had been the sole holdout, and this was why.

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
- [x] S Record one uncontended full-run timing baseline as a tracked file. **DONE 2026-09-06 (57a23200d):** docs/ci-overhaul/11-timing-baseline.md, 437 gates, wall 780.4s, serial 7021.0s, 9.0x. The receipt records the CONDITIONS too, because a number without them is how the four conflicting figures got into the drafts.
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
- [x] C Redact the four AKIA ids in `agent/PLAN-secret-namespace-migration.md:1615-1616`. The `:1617` value is a token id under a "new id" header, not a bearer, so no rotation.
- [x] C Make three count-bearing stale lines count-free so they cannot re-stale, and fix two narrow stale lines.
- [x] C Record ruling 7 in `docs/ci-overhaul/04-decisions.md` section A: the single-language rule, what bash survives, and that it supersedes `agent/PLAN-shell-resource-profiling.md:7`. Mark that line superseded.

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
- [x] W2.4 Isolation as a path-scoped contract defined once and implemented identically in `pool.ts` and `run-all.sh`; inventories re-keyed; the three text readers drained; counts fixed.  **PARTIAL, CORRECTED 2026-09-07 BY MEASURING THE LOCK.** The three text readers WERE drained and pool.ts and the battery both implement the contract, so half the box is real. But the DECLARATIONS never landed: of the 148 gate-test entries in gates.lock.json, `mutex`, `reads`, `heavy` and `weight` are populated on **ZERO**, and only `slow` is set (34 of 148). No entry anywhere in the lock carries a `reads` key at all; `mutex` exists on 12 entries repo-wide, none of them a gate test. The consequence is observable rather than theoretical: the battery is running on its LOUD FALLBACK today, printing "no 'tree:' isolation declared in scripts/ci-runner/gates.lock.json; falling back to the hand-maintained W/S lists in this file" at :303-304. So the hand-maintained lists this box exists to retire are still the live source of truth, and W7 P3's `battery.py` inherits the same fallback. A contract implemented by two readers with no data to read is not done. **CLOSED 2026-09-07, and the root cause was a MISSING TYPE, which is why this sat green for a day.** `scripts/ci-runner/gate-spec.ts:45` declared `mutex?: string[]` and there was NO `reads` field at all, so the 21 scanner gate tests were UNDECLARABLE by construction while `.ci/scripts/test/run-all.sh:275-276` asked `classify_from_lock` for exactly that claim. Added `reads?: string[]` to the spec, then wrote 25 declarations into manifest.ts -- `mutex: ['tree:repo']` on the 4 writers, `reads: ['tree:repo']` on the 21 scanners -- 25 insertions and ZERO deletions, derived FROM the existing fallback arrays rather than invented, so this moves the classification into the registry instead of restating it. Lock regenerated, 456 gates, and it now carries `tree:` on exactly 4 mutex and 21 reads entries. THE PROOF IS A WARNING THAT STOPPED: the battery no longer prints "no 'tree:' isolation declared ... falling back to the hand-maintained W/S lists", stderr is clean and it exits 0. The arrays remain on purpose as a fail-loud backstop -- their own comment says "no declarations yet" and "lock is broken" must not silently become "nothing needs isolating" -- but they are no longer the source of truth
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
- [x] P1 Prerequisites, router split, launchers, entry tests. Two prerequisite defects land in wave 1 because everything depends on them: `scripts/gates/check-dead-bash.ts:152` has no `py` alternative in its TEXTUAL regex, and `scripts/ci-runner/run.ts:940` computes `whole` from only `--only`/`--skip`, so a `--changed` receipt currently authorises a push.  **DONE 2026-09-06:** W6 P1 router split: run.sh 120 lines, run-legacy.sh 1334, run.ps1/run.cmd
- [x] P2 Python platform layer, toolchain port behind a differential shadow gate, the four macOS bash fixes, and the one install table.  **DONE 2026-09-07 (2f0c3515d):** `.ci/rediacc_ci/setup/tools.py`, 22 rows, 9 pinned, WITH the pytest row the contract recorded as missing. `w6p2-toolchain` asserts equivalence over 5 distinct trees. The four macOS bugs were DRIVEN against a bash 3.2.0 built from source, not asserted: release-state-validator printed empty stdout and rc=1 for a HEALTHY release state, and blocker-validator's unquoted regex is a SYNTAX ERROR on 3.2 that killed the enclosing function so the allowlist parsed to zero entries. All four now refuse loudly with their version named.
- (round 1, SUPERSEDED by a Round 2 box above) P3 `setup` in Python with the phase table as data, the missing installs (ruff, shellcheck, shfmt, actionlint, uv, pytest, gitleaks, bws, tmux), `.claude` wiring, and opt-in git hooks.
- (round 1, SUPERSEDED by a Round 2 box above) P4 `rdc.sh` down to a 70-line shim, native CLI build moved into the package, macOS-complete setup, a macOS CI probe.
- (round 1, SUPERSEDED by a Round 2 box above) P5 Quality lane last, legacy file deleted, `LEGACY_ARMS_MAX` reaches zero.

### W7: .ci port (6 phases)
- [x] P0 Seams, baselines and counts that every later box is measured against.  **DONE 2026-09-06:** W7 P0 baselines as SETS; corrected three contract counts
- [x] P1 JS relocation out of `.ci`, and the two bash libs ported into `core` behind delegating shims.  **DONE 2026-09-06:** W7 P1(b) two bash libs behind fail-closed shims. P1(a) JS relocation REFUSED on measurement: 22 of 23 files drop from full to reduced CI
- [x] P2 Port the 74 `check-*.sh` plus 5 wrappers behind `@gate`, each with a `--selftest` control and a committed differential artifact over K distinct trees.  **PARTIAL 2026-09-06: 14 of 77 ported, 13 of 14 PROVEN (b9033101a). Superseding an earlier 4-of-14 reading:**, refuted by running the comparator over every ledger: only npmrc, go-module-sync, cli-contract and compose-env reach `equivalence holds over 5 distinct trees`. TEN fail, not the six I named: the six earlier ports report 0 distinct clean trees, and batch A never reached K=5 either (peerdeps 3, appadmin 3, cmdtree 4). stagingtag has 6 clean trees but 3 are DISQUALIFIED by MISMATCH_FINDINGS rows, which is a recorded BEHAVIOURAL divergence rather than a bookkeeping gap. Original note follows: batch A (peer-deps, no-app-admin-perm, command-tree, staging-tag-guard) and batch B (npmrc, go-module-sync, cli-contract, compose-env) landed at 5c85a675e and 6586bc038, each EQUIVALENT over 5 distinct committed HEAD^{tree} ids. THE FIRST SIX ARE NOT ACTUALLY PROVEN: every one of their 34 rows carries clean:false against ONE shared tree id, so --assert reports 0 distinct clean trees and invariant 5 is unmet for all six. The cure found in batch B is to make each specimen its own committed git repo, and to run the new side under PYTHONDONTWRITEBYTECODE=1, since __pycache__ dirties the tree before treeIdentity is computed.  **"77 of 77" MEANS PORTED, NOT LIVE AND NOT DELETED. Re-measured 2026-09-07 after the operator asked why so many .sh files remain, which was the right question.** `rediacc_ci/quality` is referenced ZERO times in `package.json`, `manifest.ts` and `ci-quality.yml`, while `manifest.ts` still names `.ci/scripts/quality` 143 times: CI runs the BASH. 581 `.sh` files are still tracked under `.ci`/`.claude`, all 82 bash quality gates and all 149 bash gate tests are present, and nothing has been deleted. That is the DESIGN (invariant 5 forbids deleting a twin in the porting change; wiring is W7 P4 and deletion is W7 P5, both open), but quoting "100%" as a headline reads as finished and is not. Report three axes from now on: PORTED, LIVE, DELETED. They were 77, 0, 0. **RE-MEASURED 2026-09-08 after NINE W7 P4 cutover waves: 77, 73, 0.** Wave 9 took
the last ten twins that had a registration to repoint -- release_state, branch,
claude_attribution, commit_identity, pr_description, resolved_threads,
review_comments, review_report_replies, submodule_branches, plus the earlier
scope_scripts_reachability step rename -- each byte-identical to its twin on both
streams with the same exit code on this tree, and each already asserting
equivalence over 5 to 14 distinct trees.

THREE OF THE LAST THIRTEEN CANNOT BECOME LIVE BY REPOINTING, and finding out why
was the wave's real yield. `check-autopilot-no-bypass.sh`,
`check-ci-job-aggregation.sh` and `check-swallowed-failures.sh` are invoked by
NOTHING: no `package.json` key, no `manifest.ts` entry, no workflow `run:` line,
no wrapper. CI runs their gate TESTS and never the gates, so each one's logic is
exercised against fixtures while it never judges the real repository.
`check:ci-parity` cannot see this, because a gate absent from BOTH sides is
absent from the comparison. Two of the three exit 0 against this tree; the third
refuses without an organisation variable. Tracked, with the registration decision
parked, rather than folded into a cutover it is not.

`staging_tag_guard` is the fourth and is excluded for cause: its ledger is the
programme's one permanent red.

AND THE CUTOVER FOUND A MATCHER THAT HAD GONE EXTENSION-SHAPED, the same class as
the `paths:` glob trap. `scripts/gates/check-ci-parity.ts` spelled its gate matcher
`check-[\w.-]+\.sh` and expanded a path exemption to its package.json key only
`if (e.entry.endsWith('.sh'))`. Both stopped applying the instant a gate was
repointed at its `.py` port: rules R2 and R3 quietly stopped judging it, and
`check:ci-release-state` reported as an unregistered gate although its exemption
named it. Both now accept `check_name.py` as well, with three controls that fail
against the old spelling. The pilot took LIVE from 0 to 1 (`check:ci-npmrc`), and TWELVE more followed in two waves -- apbp, cli-doc-coverage, regions-sync, release-bump-skip, rubric-calibration, www-build-token, then script-exec-bit, pipefail-grep-q, tracked-sidecars, go-tool-path, git-op-conditionals and probe-parity -- each on a shadow ledger asserting equivalence over 5-15 distinct trees, with both directions driven byte-identical and a violation planted through every seam. DELETED is still 0 and all 77 `.sh` twins are on disk, which is invariant 5 working, not a shortfall. TWO MEASUREMENT TRAPS PAID FOR HERE. `grep -c rediacc_ci/quality gates.lock.json` is NOT the LIVE count, because the lock names ENTRY POINTS and never the module path. **The old wording here said it "reads 0 and always will", and that was falsified on 2026-09-08 by my own edits: it read 2, then 3, and every move was mine.** The three hits, re-measured 2026-09-08 at `scripts/ci-runner/gates.lock.json:1125`, `scripts/ci-runner/gates.lock.json:1147` and `scripts/ci-runner/gates.lock.json:3126`, are `toolchain_pins.py` and `account_portal.py` in `paths` entries I added so those gates select under `--changed` when their port changes, plus `git_op_conditionals.py` in a `leaves` path. A probe whose value I move myself every wave is a progress meter measuring my own edits. A probe described as permanently zero is one a later reader trusts without running; it drifts, and then it reads as progress. LIVE must be counted as registered `.py` entry points that import a port. And `gate:bind --write` alone leaves the lock STALE -- `npm run gen:gates-lock` is what moves the number. Do not read the 41 `check:ci-*` keys pointing at a `.ci/scripts/quality/check_*.py` as progress on this axis: I mis-measured that way once this session. Most of those are gates that were ALWAYS Python and never had a bash twin. Only SEVEN `.py` entry points import a `rediacc_ci.quality` module at all (autopilot_breakpoint_alignment, cli_doc_coverage, npmrc, regions_sync, release_bump_skip, rubric_calibration, www_build_token), each still has its `check-*.sh` twin on disk, and for six of the seven `package.json` still names the `.sh`. The shim exists; the cutover has not happened. DELETED remains 0 and all 77 bash quality twins are present. **AND THE REASON LIVE IS 0 IS STRUCTURAL, not scheduling, measured 2026-09-07: ZERO of the 78 ported modules carries a `---- gate ----` header** (`grep -l -- '---- gate ----' .ci/rediacc_ci/quality/*.py | wc -l` -> 0). In this repo REGISTRATION IS THE HEADER, since `gate:bind` reads it, so W7 P4 cannot begin as a registration change: 78 headers must be written first, and no box costs that work. Five of the six entry points under `.ci/scripts/quality/` that import a port are referenced by nothing at all, and `check-dead-bash.ts` is bash-only so it cannot see them: there is NO dead-Python gate. **DONE 2026-09-06 (9c6a00de8): 77 of 77 ported. RE-MEASURED 2026-09-07 over every ledger in .ci/shadow, which now holds 78 pairs, not 77: 77 of 78 assert `equivalence holds` at K=5.** The one red is w7p2-stagingtag and it is permanent: three tree ids disqualified by rows recorded through a hole since closed, 12 qualifying trees over 9 finding sets, so the claim is evidenced and only the assert cannot express it. No twin deleted: that is W7 P5.
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
- [x] P1b scripts prep: repo-root module, `utils` merged into `lib`. **DONE 2026-09-06 (a4828bd3a + b9033101a):** git mv of console.ts, crc32.ts and translation-diff.ts, 24 importers fixed, scripts/utils/ gone, tsc and lint green, zero stale imports. Three inventories re-keyed in the same change per invariant 2. Its recorded blocker (22 of 25 importers dirty) was gone. NOTE 'operator bash relocated out' was NOT done and is not tracked anywhere else.  **THAT PARTIAL NOTE IS NOW FALSE, re-measured 2026-09-07:** `ls scripts/utils` returns No such file, `scripts/lib/{console,crc32,translation-diff}.ts` are all present, and `git log -- scripts/utils` ends at `a4828bd3a refactor(scripts): merge utils into lib`. The merge DID happen; the box carried two contradicting notes and the pessimistic one outlived the work.
- (round 1, SUPERSEDED by a Round 2 box above) P2 Domain moves and data relocation. Strictly serial, single writer: `enumeration-vacuity-baseline.json` **is an OBJECT `{note, unguarded: [42 entries]}`, not "one sorted array"** (verified 2026-09-07; read at `scripts/gates/check-enumeration-vacuity.ts:403` as `.unguarded`). The VERDICT is unchanged, and that is the point of correcting the description rather than the box: a rename still reads as growth to a shrink-only list, so this stays strictly serial and single-writer. But an implementer who greps for an array concludes the box is stale and skips the re-key.
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
- [x] P2.3 PostCompact and the CI-red history hook both append why lines.  **DONE at a02496709, never ticked; verified 2026-09-07 against the tree rather than the note:** both halves are self-labelled `W12 P2.3`, PostCompact at `.claude/hooks/stop/wl_checks.py:2348-2361` and the CI-red hook at `.claude/hooks/stop/wl_histfirst.py:173-189` (208 lines, wired at `.claude/hooks/stop/wl_checks.py:4272`).
- [x] P2.4 `check_plan_citations.py`. **DONE at a02496709, never ticked:** 568 lines, parser-blind floor documented at :60-65 and implemented at :366, registered in all three places (package.json, manifest.ts with paths, .github/workflows/ci-quality.yml:569). It is live and catching things: it refused two of my own plan citations today.
- [x] P2.5 `--plan-tick` with evidence, flipping the box and updating the ledger in one run.  **DONE 2026-09-06:** W12 P2.5: --plan-tick in worklist.py
- [x] P2.6 Pointer stamps on store compaction and on every STATE.md write. **DONE, never ticked:** both halves use the real pointer_stamp from .claude/hooks/stop/wl_planrec.py:1371. Store compaction at .claude/hooks/stop/wl_store.py:1814-1820 (dict.fromkeys, not a set, because the compactor's own file is both in `clear` and the target). STATE.md at .claude/hooks/stop/worklist.py:1521-1529, taken INSIDE the lock and BEFORE the os.replace, which is the only ordering that makes the stamp true. Both imports suppressed, so a stamp never gates a write.
- (round 1, SUPERSEDED by a Round 2 box above) P2.7 **"A5" POINTS AT THE WRONG FILE, verified 2026-09-07: `grep -cE '\bA5\b' docs/ci-overhaul/04-decisions.md` returns 0.** `A5` and `A6` are GATE RULES in `.ci/scripts/quality/check_plan_boxes.py:41-44` (A5 = a plan may only be deleted wholesale once older than delete_days AND only when deletion actually loses a box; A6 = the scan is not vacuous). The clause therefore reads: **`check_plan_boxes.py` rule `G-A5` becomes never-delete.** Plus two TRAPS entries; CLAUDE.md gains "search first" (0 hits today); the grammar is documented.
- (round 1, SUPERSEDED by a Round 2 box above) P2.8 Second wave. **NOT 13 PLANS AND NOT 2026-10-06, re-measured 2026-09-07.** `check-plan-housekeeping.sh` reports 86 tracked plan(s) with 32 compacted, so **54 are uncompacted**, four times the recorded figure. The next red is **2026-09-25** (2 plans) and then continuous, not 2026-10-06. Staffing this against the old numbers under-provisions it and misses the deadline by eleven days.

#### W12.P3 Registers and remaining edges
- [x] P3.1a Epics durable: the TMPDIR sidecar moved into `agent/worklist/`. **DONE:** .claude/hooks/stop/wl_epic.py:36-37.
- (round 1, SUPERSEDED by a Round 2 box above) P3.1b **THE STATED PREMISE IS REFUTED, re-scoped 2026-09-07.** "Nothing asserts every PR-TASK id has an epic event" is false: `scripts/gates/check-pr-task-trailers.ts:68-81` emits `unknown-epic` for an unknown id, with both directions controlled at `:106-125`. The gap that actually survives is narrower and worth stating exactly, because the old wording sends an agent to build something that exists: `known` is scraped from a MARKDOWN SNAPSHOT (`:272`, `:277`) rather than read from a `wl_epic.py` event, so the assertion is against a document that can drift, not against the ledger.
- (round 1, SUPERSEDED by a Round 2 box above) P3.2 `DECISIONS.md` with ids, seeded from `04-decisions.md` and the ten locked decisions in the secret-migration plan. **THE "A6 OVERRIDE RULE" IS `04-decisions.md` SECTION A ITEM 6** (`:22-23`, "Do not stick on what I say. Better ideas are welcomed"), an OPERATOR RULING, and NOT the gate rule A6 in `.ci/scripts/quality/check_plan_boxes.py:42-44`, which is the anti-vacuity clause. P2.7 and P3.2 sit two boxes apart and pointed at OPPOSITE FILES under the same-looking token, which is exactly the confusion the new file must end. **The ids must be PREFIXED (`D-A6` for a decision, `G-A5`/`G-A6` for a gate rule) so the collision cannot recur.**
- (round 1, SUPERSEDED by a Round 2 box above) P3.3 Canonical status vocabulary in config; the three state sets built from it.
- [x] P3.4a The three header keys PARSE: wl_planrec.py HEADER_FIELD_KEYS carries Supersedes, Extends and Related, and they are correctly excluded from being read as a title.
- (round 1, SUPERSEDED by a Round 2 box above) P3.4b Nothing RESOLVES them to a real plan: `git grep 'Supersedes' -- '.ci/scripts/quality/*'` returns nothing. Split out 2026-09-06, same shape as P3.1, because the box read as one unit while its first half was silently complete. Run it AFTER the compaction wave: its gate change alters what check_plan_record.py accepts while that wave runs --update against agent/INDEX.md all the while.
- (round 1, SUPERSEDED by a Round 2 box above) P3.5 Measure before blocking: a two-week advisory census before any blocking rung.

## Gaps still unowned (assign before launch)

- [x] **THE LANGUAGE-POLICY GATE NOW EXISTS. This entry was written and closed the SAME DAY, 2026-09-07**, which is worth leaving visible rather than deleting: the gap was real when found and the fix landed hours later. Built as ADVISORY and shrink-only (`check:ci-language-policy`, 521-path SET baseline, 3 BLOCKER-gated exemptions, registered and green), because blocking against 520 non-exempt shell files would have redded the tree and been suppressed within a day. **The STRICT FLIP is still open and is W1 P6**, whose job is to delete the baseline entirely. Original finding follows. ~~THE LANGUAGE-POLICY GATE ITSELF DOES NOT EXIST, and no box in this plan creates it.~~ Found 2026-09-07: `grep -rin 'language.policy'` across every tracked `.ts/.py/.sh/.json` (excluding node_modules, .git and docs/ci-overhaul) returns NOTHING. No baseline file, no allowlist, no `POLICY_FILES` slot. So **W1 P6 has nothing to flip** and **W10 P5 has nothing to hand its BLOCKER strings to**, and both read as ordinary pending work while their subject is absent. It also sits on the live critical path. Landed 2026-09-07 as a shrink-only gate. **CORRECTION to my own framing, verified in the code 2026-09-07: it is NOT advisory. `run()` returns 1 on growth (`.ci/scripts/quality/check_language_policy.py:850`), so it BLOCKS, with a frozen floor of 521 paths.** "Advisory" was the wrong word for shrink-only: it does not demand the 521 be fixed, but it fails the build the moment a 522nd appears. In flight as a shrink-only gate (blocking today would red ~119 tracked `.sh` and be suppressed within a day, which is the failure `suppressions.md` exists to prevent); the strict flip stays W1 P6. Its baseline is a SET of paths, not a count, per this plan's own floor policy.

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

**W2.3 HAS FALLEN OFF THE PATH**, proven empirically rather than argued: 41 subjects are ported and running with NO manifest region and no manifest entries at all, under the single `check:ci-pytest` entry (`scripts/ci-runner/manifest.ts:5573`), because `testpaths` already covers `.ci/rediacc_ci/tests/gates`. So W7 P3 needs no registration and no driver involvement, and W2.3's open half blocks nothing.

**A PREREQUISITE IS MISSING FROM THE PATH ENTIRELY**: W7 P5's third clause is "language gate blocking for `.ci`", and that gate does not exist (see the Gaps section). It has to be BUILT before W7 P5 can be flipped.

Live path: **W7 P3 (107 of 148 remaining) to W7 P4 (201 unique scripts, 334 call sites) to [BUILD the language-policy gate] to W7 P5 (138 .sh) to W11 P6.** W7 P3 is the single largest body of work in the programme and the only thing on the path that can start today.

## The control-plant class is enforced in ONE language, swept 2026-09-09

`check:ci-python-control-plants` refuses a control mutant built by raw substitution: if the
needle has gone, `str.replace` returns the fixture UNCHANGED and the control then scans the
same text as its neighbour while asserting the opposite verdict, passing for free. The
sanctioned helper is `rediacc_ci.controls.plant`, which raises `VacuousPlantError` instead.

**That gate covers Python only, and the sweep found the other two surfaces uneven:**

* **Python** -- one live instance, `.ci/rediacc_ci/quality/git_op_conditionals.py:1114`,
  fixed; the gate is rc=0 so the language is clean by its own instrument.
* **TypeScript** -- no gate, two candidates. `scripts/gates/check-guard-mutations.ts:193-199`
  already counts occurrences and throws unless exactly one, which is `plant`'s contract
  inlined and correct. `scripts/gates/check-backup-bucket-conformance.ts:149` had no check; a
  vanished needle there fails LOUDLY rather than passing, because the assertion's polarity
  happens to run the other way, but it fails with a message about the wrong thing. Given
  the same occurrence check.
* **Bash -- the real gap, and it is not small.** Gate tests plant with `sed -i` and almost
  none verify the plant landed: `grep -rn 'CONTROL PLANT DID NOT LAND'` finds **2 sites in
  the whole repository**, against `sed -i` plants spread across the gate-test corpus. A
  bash plant that silently fails to apply is exactly the failure this class describes, and
  `.ci/scripts/test/gates/test-run-sh.sh` already proved the shape is live when its own
  control printed "CONTROL PLANT DID NOT LAND ... plants nothing and passes for free".

**The fix is to extend the gate, not to hand-audit the corpus** -- one instrument covering
all three languages, with the bash arm requiring a post-plant assertion. Sized as writer
work and deliberately not started inline; recorded here so it is not rediscovered.

## A green that proved nothing, found 2026-09-09 by fixing one half of a pair

`test_gate_doc_region_parity` builds a fixture by copying tracked paths and running the
real `gen-docs` inside it. Both the Python port and its bash twin
(`.ci/scripts/test/gates/test-doc-region-parity.sh`) carried the SAME hand-written
six-item list, and both had fallen behind the providers: each new seam produced either a
node `ENOENT` inside the generator or its anti-vacuity refusal, neither of which reads as
"the fixture is stale".

**`test_twin_parity` was GREEN throughout, because it compares verdicts and both sides
were red.** It logged `twin and port agree (both red)`. Two broken things agreeing is a
green that proves nothing, and nothing could expose it until one side was repaired --
fixing the port turned parity RED, which is that gate working for the first time on this
pair.

Both sides are now DERIVED rather than enumerated: every quoted literal in
`scripts/gen-docs.ts` and its two libraries that resolves to a tracked path IS the input
set, so a provider has to name the seam it opens and the literal is the declaration. Both
independently produce **38 pathspecs**. The port walks the import closure and refuses a
closure of one; the twin takes the three closure files literally and refuses a set under
ten.

Three traps paid for in the repair, all measured:

* **`tar -c` needs `--no-recursion`.** The derived set includes the four `private/*`
  GITLINKS, and tar recurses a directory name by default, walking each submodule's on-disk
  tree with its `.git` included.
* **A file is not a literal inside itself.** The deriver reads the three closure files for
  quoted paths, so it can never yield their own names; omitting them gives
  `Cannot find module <fixture>/scripts/gen-docs.ts`, which reads as a broken copy rather
  than a missing input.
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
