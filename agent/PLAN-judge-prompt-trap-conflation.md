# PLAN: the stop-judge conflates a PAST trap example with a CURRENT finding
Status: compacted
Owner: d778be9d
Full-Text-Blob: 7b082ab92d12ab27ec933722ae1b9030c1febdaf
Record-Sig: 8e688a15

## Why
The stop-judge was hallucinating bulk mechanical-transform findings that didn't exist in the working tree—twice naming changes that a `git status` check proved false. Root cause: a worked example from a real 884-file incident was quoted verbatim into the live prompt with no fence separating "hypothetical" from "what to find now", causing the model to paraphrase that example shape
even when it didn't apply. A second gap: claim fields (`scope`, `defect_class`) were never validated against the actual diff before firing.

## Outcome
Landed and verified: file-list grounding via `wl_reggate.fixset_files()` from git; `M.FIXSET_GROUND_TRUTH` injected into prompt; de-fanged magic-number example; anchoring sentences to `wl_proofcheck`/`wl_classsweep`/`JUDGE_PROMPT`; `wl_rules.scope_grounded()` added; annotation wired into `enforce` via optional `fixset_files`. All 399 existing tests pass; new controls verify both
hallucination patterns. `PR-TASK: [unresolved]`, evidence: worklist `[unresolved]`.

## Lessons
- Worked examples in prompts sent to models at eval time become actively dangerous when not visually and semantically fenced from the live question. Copy-pasteable magnitudes are the highest-risk artifact form.
- A safety mechanism filtering findings must be grounded in real, computed data (git diff-tree) BEFORE asking the judge, not after. The prompt is halfway to hallucination without that.
- Reserved-instruction-bypass gaps exist in multiple places. One fix does not automatically fix the class; systematic audit needed.
- When fixing a safety mechanism, append information (annotate) rather than remove findings (suppress). The failure-direction contract is load-bearing.
- The judge pipeline's contract (`[unresolved]`, `[unresolved]`) must survive byte-for-byte. Changing failure direction is a structural violation.

## Boxes
- [x] Add `wl_reggate._diff_tree_files`/`fixset_files`, refactor `gate_only_fixset` to use it
    (record) sig=f06b6846 done=f67f82cca
- [x] Compute and pass `fixset_files` through `wl_checks.py` -> `wl_judge.run_judge`
    (record) sig=48e9411c done=f67f82cca
- [x] Add `M.FIXSET_GROUND_TRUTH`, inject into the judge prompt when `fixset_files is not None`
    (record) sig=2003b963 done=f67f82cca
- [x] De-fang `wl_proofcheck.PROOF_PROMPT`'s magic-number example; add the anchoring sentences to `wl_proofcheck`/`wl_classsweep`/`JUDGE_PROMPT`
    (record) sig=6cf28520 done=f67f82cca
- [x] Add `wl_rules.scope_grounded`; wire the UNVERIFIED annotation into `wl_proofcheck.enforce`/`wl_classsweep.enforce` via a new optional `fixset_files` parameter on `apply_verdict`, defaulting to `None`
    (record) sig=e6959b0e done=f67f82cca
- [x] New hermetic tests: `scope_grounded` unit controls, enforce-with-grounding controls (both hallucination replays), `fixset_files` git-fixture controls
    (record) sig=2218eb43 done=f67f82cca
- [x] Run the full `test-judge-schema.py` suite (399 existing) unmodified, plus new controls, all green
    (record) sig=c6514d3b done=f67f82cca
- [x] Commit, `PR-TASK: e87fa3ce`, evidence into worklist `544eab1e`
    (record) sig=c7120cc7 done=f67f82cca

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:13:08Z
Boxes: 8 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: none
Gates: none
Why-Source: model
Read-History: `git show 7b082ab92d12ab27ec933722ae1b9030c1febdaf` recovers the text; `git log --find-object=7b082ab92d12ab27ec933722ae1b9030c1febdaf --all` names the commit

## History
- 2026-09-20T18:13:08Z compacted by d778be9d from `done` (record-sig 8e688a15)
