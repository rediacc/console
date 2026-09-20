# PLAN: ci-trace must be able to read a branch that has no open PR
Status: compacted
Owner: 854ac1c6
Full-Text-Blob: fe0fb4ebc96721663e8496ccbc77ce1a9303342a
Record-Sig: c5bdd92b

## Why
ci-trace.py could not read CI for branches with no open PR (like main after a merge), leaving the post-merge verification step with no sanctioned tool to check the release path—other alternatives are blocked by guards. The reader was the only one, and it had no fallback.

## Outcome
Shipped in [unresolved] with ci_branch_query and allow_branch parameter. Test 1 (test-ci-trace-branch.sh) landed and is wired. Test 2 (check-ci-watch-recipe.sh extension to prove the skill's invocation matches the tool's capability) was NOT done—the visibility gap that let this ship in the first place remains. A third gap found in use: cannot watch a run on a deleted branch, deliberately left unfixed because run-id keying reintroduces the stale-attempt bug the reader exists to prevent.

## Lessons
- allow_branch=False as the default preserves byte-for-byte backwards compatibility, which is load-bearing for the Stop hook's PR-currency logic—changing the default silently would corrupt unrelated logic
- no-ref is distinct from no-pr because they need opposite responses from callers—a silent merge would have left a caller unable to distinguish 'branch does not exist' from 'PR not yet opened'
- Run-id keying reintroduces the stale-attempt bug that head-keying was designed to eliminate; a tool that watches runs must key on head, not attempt
- The gate proves the script exists, but not that every invocation named in a skill resolves through a code path that exists—Test 2 would have caught this before ship
- Two different things flowing through one undifferentiated channel repeats a defect already fixed ([unresolved] in run.sh); the source must be named in output so ambiguity cannot hide

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T12:25:15Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .ci/scripts/ci/ci-trace.py, .claude/hooks/stop/wl_ci.py
Gates: none
Why-Source: model
Read-History: `git show fe0fb4ebc96721663e8496ccbc77ce1a9303342a` recovers the text; `git log --find-object=fe0fb4ebc96721663e8496ccbc77ce1a9303342a --all` names the commit

## History
- 2026-09-20T12:25:15Z compacted by d778be9d from `done` (record-sig c5bdd92b)
