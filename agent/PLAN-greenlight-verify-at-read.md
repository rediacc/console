# PLAN: cross-PR greenlight, verify-at-read (skip test-renet / account E2E on any-PR job-green evidence)
Status: compacted
Owner: orchestrator (design synthesized from three discovery investigations), branch 0731-2
Full-Text: f7a5351a9 agent/PLAN-greenlight-verify-at-read.md
Full-Text-Blob: 797d986ae411011b63c51b254fb17ebc0518d143
Record-Sig: 4fb11232

## Why
The scope engine skipped test-renet and the account E2E only when the submodule
pointer had not moved against a lineage-local green baseline, so a submodule sha
that some OTHER PR had already proven green still paid for a full re-run. The ask
was to widen the evidence to any PR. The hard constraint was that no run may write
its own trust token: PR-triggered jobs hold no write powers, and a self-declared
memo is a claim later readers cannot check. Hence verify-at-read, deriving the
greenlight fresh from the GitHub Actions API at Initialize time.

## Outcome
SHIPPED, measured against the tree on 2026-09-06 rather than taken from the header.
`.ci/scripts/ci/greenlight.cjs` exists (50,978 bytes) and `git log --diff-filter=A`
names its adding commit as e64c79032, "feat(ci): cross-PR greenlight: skip
test-renet/account-E2E on verify-at-read job-green evidence", an ancestor of
origin/main. The pure core `evaluateGreenlight({ key, wantGitlinks, wantClosureHash,
candidates })` is at `.ci/scripts/ci/greenlight.cjs:766` with named refusal reasons, which is D1 as
designed. It is wired at both ends: `.github/workflows/ci-quality.yml:1199` runs
`npm run check:ci-greenlight-closures`, and `.ci/scripts/ci/scope-engine.cjs:169`
consumes the `greenlight:<run-id>` skip reason that scope-shadow.sh's
apply_greenlight writes.

ONE CORRECTION TO THE PLAN'S OWN TEXT. Its `## Status` section claimed "DONE
2026-07-31 (commit 03bac5a8)". GIVEN AT 8 CHARACTERS ON PURPOSE, and do not "restore"
the ninth: `check:ci-plan-citations` judges any 9-or-more hex token as a git object it
must resolve, and the whole point of this sentence is that this one CANNOT be resolved.
At 8 it is a name for a thing that is gone, which is what it is. That sha still exists
as an object in this clone but
is reachable from no branch and is NOT an ancestor of origin/main: it is the
pre-rewrite id of the same commit, invalidated by the 2026-08-23 media history
rewrite that changed every sha in this repository. The live pointer is e64c79032.
The plan's signature shape changed too, from `wantSubmoduleSha` in the design to
`wantGitlinks` in the code, so the engine covers more than one submodule.

## Lessons
- A commit sha written into a plan is a perishable pointer here. This plan's own
  headline sha died in the media history rewrite while the work it named was and
  is fully landed, which is precisely why a record points at a content-addressed
  blob and treats the commit as a convenience.
- A design's parameter names are not the shipped ones. `wantSubmoduleSha` became
  `wantGitlinks`; reading the plan alone would have left the record describing an
  interface that does not exist.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:01:29Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/scripts/ci/scope-engine.cjs
Gates: check:actions
Why-Source: auto
Read-History: `git show 797d986ae411011b63c51b254fb17ebc0518d143` recovers the text; `git log --find-object=797d986ae411011b63c51b254fb17ebc0518d143 --all` names the commit

## History
- 2026-09-06T17:01:29Z compacted by 8f55d4f0 from `done` (record-sig 4fb11232)
