# PLAN: bump-none must withhold the R2 channel pointer, not just the tag
Status: compacted
Owner: 854ac1c6
Full-Text-Blob: b9f4b3fbe9b685d698dbb4cba7919e82c20ecae1
Record-Sig: c26118fe

## Why
bump-none release mode claimed to skip the entire release, but the R2 upload step was not actually skipping channel pointer writes. This was a recurring live bug (3 occurrences in PR #573, #574, #576) that broke the immutable-URL promise and created supply chain risk: successive skipped releases served different bytes from the same versioned URL, and untagged pointers remained live
for housekeeping to delete under an active channel reference.

## Outcome
COMPLETE as of 2026-08-26T14:0xZ. Remediation landed: cut real v1.3.1 tag and sealed it via backfill sentinel (section 4). Implementation landed end-to-end: upload-to-r2.sh and upload-repos-to-r2.sh now guard against writing on --skip-release; signal flows from initialize.sh through ci.yml and cd-stage.yml to both upload scripts; assert-edge-tag-exists.sh precondition wired into
promote-stable.yml before any R2 write; validate-install and validate-promote skip on skipped releases; rsv_assert_channel_pointer_tagged added to check-release-state.sh to detect the class of defect (channel pointer naming untagged version). All four test suites (T1-T4) green with planted defects verified to fire.

## Lessons
- The remediation's ci_run_id must be re-read from live R2 manifest immediately before dispatch, not taken from the plan—each bump-none merge moves the edge pointer, and tagging at the wrong commit reintroduces the exact tag-vs-artifact drift the fix exists to prevent.
- A guard that no workflow invokes is vacuous (T1 and T4 named this as their blind spot). T2, the gate test proving workflow threading, must not be deferred—it is load-bearing for the whole wiring.
- Guards belong in two places: the uploader (T1, prevents writing) and the pre-promotion validator (T4, prevents consuming untagged bytes). Relying on only the upload guard leaves promote-stable vulnerable to the same defect from other causes.
- Step ordering in promote-stable matters: the precondition must run before any promotion write, not after. A step order that 'looks right' is silently reordered by an editor and catches nothing.
- bump-none is now a documented operator-facing feature ([unresolved], CLAUDE.md Release Channels) and is relied upon for controlled release skipping. Document the semantics faithfully in help text and gate descriptions so future sessions understand why the wiring exists.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:44:20Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: package.json, .github/labels.yml
Gates: check:ci-parity, check:ci-release-state
Why-Source: model
Read-History: `git show b9f4b3fbe9b685d698dbb4cba7919e82c20ecae1` recovers the text; `git log --find-object=b9f4b3fbe9b685d698dbb4cba7919e82c20ecae1 --all` names the commit

## History
- 2026-09-20T16:44:20Z compacted by d778be9d from `done` (record-sig c26118fe)
