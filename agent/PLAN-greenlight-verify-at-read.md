# -greenlight-verify-at-read
Status: compacted
Owner: orchestrator (design synthesized from three discovery investigations), branch 0731-2
Full-Text: f7a5351a9 agent/PLAN-greenlight-verify-at-read.md
Full-Text-Blob: 797d986ae411011b63c51b254fb17ebc0518d143
Record-Sig: 4fb11232

## Why
The scope engine was re-running account E2E and renet tests every time the submodule pointer changed, even when that exact commit had already passed those tests on a different PR. This wasted CI resources and slowed feedback. The operator wanted to greenlight skips based on any successful cross-PR run of the same submodule commit, not just same-branch baselines.

## Outcome
Landed in commit 03bac5a89 (2026-07-31). All four design components are in place: greenlight.cjs engine (pure, offline-testable), scope-shadow.sh wiring (consults greenlight after scope engine), test-greenlight.sh with planted-defect proofs, and docs updates. Live verification occurred via dry run 30628333340, which correctly emitted run_renet=false with greenlight evidence. The verify-at-read design derives greenlights fresh from GitHub Actions API at each run, with no durable memo layer to corrupt or trust.

## Lessons
- Verify-at-read is the only auditable gate for PR-side CI decisions: any stored memo from PR jobs creates an un-checkable trust token, so API state derived at read time is the only source that later readers can verify.
- Closure hashing (the set of console-side files that affect a job's outcome) is the constraint that makes cross-PR greenlighting safe: job conclusion + gitlink match + closure hash match are three independent gates; any one difference blocks the skip.
- Planted-defect proofs (deliberately invert a validation rule, watch the test fail, revert with md5 evidence) catch intent-vs-outcome gaps that code inspection misses—in this case, skipped jobs reporting 'success' to naive readers.
- Fail-open is the safety contract: the greenlight engine can only grant run_<key>=false; it cannot force a skip or silence a run, so an engine bug causes re-runs (safe) not false skips (unsafe).
- API candidate filtering order is a budget constraint: check job + gitlink first (API-cheap), then fetch closure files only for matches (API-expensive), avoiding wasted calls on mismatches that would never greenlight anyway.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T15:29:35Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: .ci/scripts/ci/scope-engine.cjs
Gates: check:actions
Why-Source: model
Read-History: `git show 797d986ae411011b63c51b254fb17ebc0518d143` recovers the text; `git log --find-object=797d986ae411011b63c51b254fb17ebc0518d143 --all` names the commit

## History
- 2026-09-06T15:29:35Z compacted by 8f55d4f0 from `done` (record-sig 4fb11232)
