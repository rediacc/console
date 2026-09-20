# PLAN: a resumable rebase executor with an AI in the loop
Status: compacted
Owner: session 9d92d9b6, branch 0826-3
Full-Text-Blob: 0de01ed0e941e9b219977dd009621b603df52b51
Record-Sig: bba3285f

## Why
Operator rejected a design that refused rebase conflict resolution entirely. Manual testing across 10 real conflicts showed the ratio: 1 oracle-decidable (gitlinks), 6 mechanical (registries, JSON, markdown), 2 requiring judgment. Refusing all ten to protect the two was poor automation.

## Outcome
All five sequenced steps landed 2026-08-27: rebase-status (read-only), classifier with 52 controls, resolve-gitlinks --execute, rebase-resolve with JSON registry union, and rebase-continue looping. Fixtures at .ci/scripts/test/lib/git-fixture.sh drive five halt kinds. check:ci-git-tool-safety bans --skip. Three wiring bugs caught only by real-halt fixtures, not code review.

## Lessons
- Mechanical union is dangerous: glued seams ship silently. Token lists where touched + see became touchedsee passed checks. Entry-based operations prevent this; invariant checks (token count, no duplicate ids, no resurrection) are mandatory.
- Git already owns rebase state in .git/rebase-merge/. A second persistence layer drifts from truth. Halt reporters read git's state directly.
- Pure functions plus controls find one class of bugs; fixture tests find another. Three real-halt issues (tuple typing, return signature, routing) never surfaced in code review.
- Every executable verb needs explicit scope and epilogue handling, not inherited from callers. Force-push's epilogue expects a branch name; rebase-continue has none.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: implemented
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:43:23Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: none
Gates: check:ci-git-tool-safety
Why-Source: model
Read-History: `git show 0de01ed0e941e9b219977dd009621b603df52b51` recovers the text; `git log --find-object=0de01ed0e941e9b219977dd009621b603df52b51 --all` names the commit

## History
- 2026-09-20T16:43:23Z compacted by d778be9d from `implemented` (record-sig bba3285f)
