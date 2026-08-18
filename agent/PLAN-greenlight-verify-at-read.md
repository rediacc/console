# PLAN: cross-PR greenlight, verify-at-read (skip test-renet / account E2E on any-PR job-green evidence)
Status: done
Owner: orchestrator (design synthesized from three discovery investigations), branch 0731-2
Updated: 2026-07-31

## Status

DONE 2026-07-31 (commit 03bac5a89). All of D1-D4 landed incl. the
operator-required case 7; two planted-defect proofs recorded in the suite's
case comments; live dry run GREENLIT by run 30628333340 and emitted
run_renet=false with the evidence id. First real in-CI firing will be
observed on a later PR round.

## The ask (operator, verbatim intent)

Today the scope engine skips test-renet / account E2E only when the submodule
pointer did not move against a lineage-local green baseline. Upgrade: if the
CURRENT submodule SHA was ever part of a green run on ANY PR, skip the related
jobs. Renet first, account the same way.

## The one hard design rule

NO STORED MEMO. The repo's own doctrine (.ci/scripts/ci/scope-engine.cjs:177,
"NOBODY WRITES `reconciled`, the READER derives it... SELF-DECLARATION IS
DELETED, NOT BLACKLISTED") says a run that writes its own trust token mints a
claim later readers cannot check, and PR-triggered jobs must never hold the
write powers a durable memo store would need. Therefore: VERIFY-AT-READ. The
greenlight is derived fresh at Initialize time from the GitHub Actions API,
which nobody had to be trusted to write.

## Evidence base (verified during discovery; re-verify anchors before coding)

- Job-level truth: run-level "CI Complete" CANNOT distinguish an executed job
  from a skipped one (.ci/scripts/ci/assert-ci-complete.sh SOFT_REQUIRED
  tiers). The API's per-run JOB conclusions can: a job that ran and succeeded
  reports conclusion=success; a scope-skipped job reports skipped. Greenlight
  evidence is therefore always the JOB conclusion, never the check.
- test-renet input closure (helper transcript a4c6bbddf0dd252f1, anchors
  ct-tests.yml:1404-1506): the renet submodule content PLUS these console-side
  files: .ci/scripts/private/run-renet.sh, renet-ebpf-e2e.sh,
  renet-root-tests.sh, renet-csi-sanity.sh, renet-integration.sh,
  .ci/scripts/lib/common.sh, .ci/scripts/infra/ci-env.sh, and the workflow
  file .github/workflows/ct-tests.yml (whole file: hashing the single job
  block is fragile; whole-file over-invalidation on ct-tests edits is
  accepted conservatism). The implementer MUST derive the analogous account
  E2E closure list from ct-tests.yml the same way (the same transcript's Job B
  section covers it; re-verify against the live workflow).
- Trigger/trust boundary (helper a301a76da42c6623b): no pull_request_target on
  test paths; fork PRs die at Initialize (no APP_PRIVATE_KEY); ct-tests holds
  zero write permissions. The verify-at-read design writes nothing, so no new
  trust surface is created.
- Gitlink at an arbitrary commit is queryable: GET
  repos/{owner}/{repo}/contents/private/renet?ref=<sha> returns the submodule
  object with its sha. This is how a candidate run's renet SHA is derived
  WITHOUT trusting anything the run said about itself.

## Design

### D1. The engine: .ci/scripts/ci/greenlight.cjs

Style copied from scope-engine.cjs / scope-map.cjs: pure functions over
injected data, a thin CLI that gathers the data via `gh api`, offline-testable
in milliseconds. No new dependencies.

Pure core:

```
evaluateGreenlight({ key, wantSubmoduleSha, wantClosureHash, candidates })
  -> { greenlit: boolean, runId?, reason }
```

A candidate is usable ONLY if all hold (mirror evaluateBaselineCandidate's
explicit-refusal style, one named reason per refusal):
1. its JOB for `key` exists with conclusion === 'success' (a missing or
   skipped or failed job refuses: 'job-not-run' / 'job-failed');
2. its gitlink for the submodule at the candidate's head_sha equals
   wantSubmoduleSha ('pointer-differs');
3. its console-side closure hash at head_sha equals wantClosureHash
   ('closure-differs').

A candidate that was itself a REDUCED run is fine: rule 1 requires the job to
have actually run. Intent is not outcome; outcome is what we read.

CLI mode (`node greenlight.cjs --key renet` from Initialize):
- compute wantSubmoduleSha from the checked-out gitlink (git ls-tree HEAD);
- compute wantClosureHash by hashing the closure file list FROM THE LOCAL
  CHECKOUT (the PR's own content: if the PR edits run-renet.sh, its hash
  differs from every candidate and nothing greenlights, which is correct);
- list candidates: gh api runs for workflow ci.yml, any branch, most recent
  N=40, completed only; for each, one jobs call filtered to the job name, and
  ONLY for gitlink-matching candidates the closure fetch (8 contents calls) --
  filter order matters for API budget: job+gitlink first, closure last;
- hard time budget (default 60s) and candidate cap; on ANY error, timeout, or
  no match: exit with greenlit=false. FAIL-OPEN IS THE CONTRACT, exactly like
  scope-shadow.sh:9-19: the engine may only ever cause a SKIP to become a RUN
  never the reverse... i.e. the engine only ever grants run_<key>=false, and
  absence of a greenlight changes nothing.

### D2. Wiring: inside the existing scope step, after the scope engine

In .ci/scripts/ci/scope-shadow.sh, after plan.json is written and only when
the engine decided run_renet is NOT already false: consult greenlight.cjs;
on greenlit, emit run_renet=false AND rewrite that key's plan.json entry with
reason "greenlight:<candidate-run-id>" so the reconciler sees a PLANNED skip
and the audit trail names the evidence run. Same for account_e2e. The
existing kill switches need no new wiring: FULL_CI / the label short-circuit
scope-shadow before any of this runs, and the step is pull_request-only, so
the nightly stays full by construction.

### D3. Anti-vacuity and tests

.ci/scripts/test/gates/test-greenlight.sh, fixture-driven against the PURE
core (injected candidates, no network), FIRE + CONTROL per property:
1. full match greenlights (FIRE) and names the run id;
2. matching gitlink + FAILED job refuses 'job-failed';
3. matching gitlink + SKIPPED job refuses 'job-not-run' (the intent-vs-outcome
   case, the one that would otherwise chain reduced runs);
4. matching job + differing closure hash refuses 'closure-differs';
5. empty candidate list refuses; a thrown/errored fetch path yields
   greenlit=false (fail-open proof, planted);
6. the CLI's emit only ever writes `run_<key>=false`, never `=true` (grep the
   emitted lines under a fixture greenlight);
7. (operator-required, added 2026-07-31) a candidate with a SUCCESSFUL job and
   a MATCHING closure hash but a DIFFERENT gitlink SHA refuses
   'pointer-differs': the skip applies only on the exact same submodule hash;
   any submodule change runs the related tests.
PLANTED-DEFECT proof, mandatory: invert rule 1 (accept skipped jobs), observe
case 3 fail while case 1 passes, revert with md5 evidence.

The new gate test lands in .ci/scripts/test/gates/, so the parity manifest's
qualityGateTest set-equality (scripts/ci-runner/manifest.ts, assertion 7 of
check-ci-parity) FORCES a manifest entry; add it. check-ci-parity and
test-ci-parity.sh must stay green.

### D4. Docs, same change

- docs/ci-overhaul/06-progress.md: a short greenlight section (what, why
  verify-at-read, the closure key).
- A paragraph on cross-branch Actions-cache/API trust (the discovery found
  ZERO docs on cache trust anywhere): where it belongs is the new section;
  state that greenlight trusts only reader-derived API facts.

## Constraints

Fail-open everywhere; no new deps; shellcheck + shfmt -i 4 -ci on any .sh;
eslint+knip clean on any TS (none expected; greenlight.cjs is CJS like its
siblings); no staging, no git add, no commits (shared index); the tree carries
other sessions' work, repair forward; no em dashes in authored text. If an
anchor cited here does not hold against the live code, stop that piece and
report the contradiction instead of improvising.

## Acceptance

- test-greenlight.sh green with the planted-defect evidence recorded in case
  comments; check-ci-parity + test-ci-parity.sh + test-scope-engine.sh green;
  npm run ci (the parallel runner) green except the documented environmental
  check:actions.
- A dry CLI run on this checkout (`node .ci/scripts/ci/greenlight.cjs --key
  renet --debug`) prints its candidate table and a truthful verdict against
  real API data. Both verdict directions need not be observable live (a
  greenlight requires a matching candidate to exist); the fixture suite covers
  both.
- The live observation (first real greenlight firing in CI) happens on a later
  PR and is NOT part of this change's acceptance.
