# PLAN: REST and GraphQL parity for the gh pr guards
Status: compacted
First-Seen: 2026-09-20
Owner: d778be9d
Full-Text-Blob: e93a81177de1dd3bb8e1c6a7f4a3979a2a846bcb
Record-Sig: 479e711f

## Why
Three pre-bash guards (block_admin_merge, block_nondraft_pr_create, block_premature_ready) were blind to REST or GraphQL API calls that reached the same GitHub mutations as their command-line forms. All three had confirmed bypasses where the gh pr control returned rc=2 but direct API calls returned rc=0 through the chain. The sharpest case: block_admin_merge's --admin ban could be
circumvented via the REST merge endpoint, potentially leaving merged PRs permanently red (incident from 2026-07-22).

## Outcome
Landed as commit b163191d2 across seven files (188 insertions, 0 deletions). All three bypasses now return rc=2 through --chain pre-bash. Sanctioned forms still pass (gh pr merge --rebase --auto, gh pr create --draft, gh pr ready). The PATCH body edit form routes correctly to block_raw_pr_body_edit rather than being caught by the new arms. Full verification suite passed including
non-regression on refresh-pr-body.sh. One deviation from written plan: oracle-drift plant ran against scratch reversion instead of plant-then-edit order, but evidence was equivalent (port rc=2 against twin rc=0) and is recorded here.

## Lessons
- Twinned guards (Python port + bash oracle) must be edited in lockstep; [unresolved] forbids the exit code itself from diverging, not merely the comment ratio
- GraphQL mutation detection requires two-part raw-versus-scan testing: shellscan strips quoted -f query= values, so the mutation name must be found in the raw command, not SCAN
- Dispatch chain stops at first refusal ([unresolved]); an earlier ORDER ban may render later guard code unreachable — verify against --chain pre-bash, not individual guards
- Ban by endpoint and method independently, never by shape, because one endpoint carries both banned and sanctioned calls (pulls/<n> has banned PUT/merge and sanctioned PATCH/body-edit)
- When a deviation from plan order is functionally equivalent, still record it — plans that absorb their own deviations silently stop being evidence of what happened

## Boxes
- [x] Add the REST merge arm to block_admin_merge.py at :170-172, before the gh_pr_at_command_pos early return
    (record) sig=6666e17c done=f67f82cca
- [x] Mirror that arm byte-for-byte into the twin .claude/oracles/pre-bash/block-admin-merge.sh at :28-29
    (record) sig=db5abd71 done=f67f82cca
- [x] Add the REST create arm to block_nondraft_pr_create.py at :70-72 and its twin block-nondraft-pr-create.sh at :21-22
    (record) sig=261d3308 done=f67f82cca
- [x] Add the GraphQL ready arm to block_premature_ready.py at :70-72 and its twin block-premature-ready.sh at :23-24, as the two-part raw-versus-scan test
    (record) sig=22b04c9d done=f67f82cca
- [x] Extend EDGE_CASES in all three ports with the bypass, the reordered-flag bypass, the GET control and the prose control
    (record) sig=88510a21 done=f67f82cca
- [x] Mirror one BLOCK and one ALLOW per guard into .claude/rediacc_hooks/tests/hookcases.py at the :1052 shape
    (record) sig=e896ee97 done=f67f82cca
- [x] Run the four defect plants in a scratch copy and record that each flips the case it is supposed to flip
    (record) sig=07152306 done=f67f82cca
- [x] Run the full verification list and the live chain matrix, including the refresh-pr-body.sh non-regression
    (record) sig=8c4b79c0 done=f67f82cca

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:08:35Z
Boxes: 8 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: .claude/hooks/post-bash/refresh-pr-body.sh
Gates: none
Why-Source: model
Read-History: `git show e93a81177de1dd3bb8e1c6a7f4a3979a2a846bcb` recovers the text; `git log --find-object=e93a81177de1dd3bb8e1c6a7f4a3979a2a846bcb --all` names the commit

## History
- 2026-09-20T18:08:35Z compacted by d778be9d from `done` (record-sig 479e711f)
