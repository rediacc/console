# PLAN: Ask-flow preemptive settled-check
Status: compacted
Owner: 9d92d9b6
Full-Text-Blob: 2c5a6ce84c56d71b63bf8b2783dd7deafb025214
Record-Sig: 47163916

## Why
The block-settled-questions.sh hook uses regex to detect questions already settled by CLAUDE.md. Two live false positives (2026-08-28, 2026-08-30) slipped through: a how-question and a question referencing a different PR. Root cause: regex cannot distinguish between rules that SETTLE questions (don't ask) from rules that MANDATE asking them (must ask), because both use identical
vocabulary (commit, branch, PR, worktree).

## Outcome
Design fully specified, not implemented. Replaces regex with Haiku 4.5 classifier using existing wl_judge._run_structured infrastructure. Fails open on all paths. Part 1 (matcher) is MVD; Parts 2–3 are dependent. Specified offline and live test suites with nine calibration cases. Cost: prefilter ~5ms, model hit 2–6s at $0.02–0.06 per call, 12s hard cap.

## Lessons
- Semantic rule-set overlaps defeat regex. When two rule columns use identical vocabulary but opposite meanings (settle vs. mandate), phrase shape cannot distinguish them—the distinction belongs to a model.
- Reuse existing transport rather than invert. Three model-call wrappers exist in this repo with matched auth and budget; a fourth copy is a fourth bug.
- Fail-open inverts the ledger contract. Guard a question, not an artifact. Blocking a legitimate ask is invisible in production; passing a settled one spends one round trip.
- Latency at interrupt cost is cheap. The operator is interrupted anyway; 5 seconds then is cheaper than a round trip.
- Measure before iterating. Live hooks expose false positives; testing regex in isolation misses them.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T17:49:44Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: CLAUDE.md, .claude/hooks/stop/wl_judge.py, .claude/hooks/stop/wl_admit.py
Gates: none
Why-Source: model
Read-History: `git show 2c5a6ce84c56d71b63bf8b2783dd7deafb025214` recovers the text; `git log --find-object=2c5a6ce84c56d71b63bf8b2783dd7deafb025214 --all` names the commit

## History
- 2026-09-20T17:49:44Z compacted by d778be9d from `draft` (record-sig 47163916)
