# PLAN: stop-hook cadence, an intent channel, and the noise cuts that come first
Status: compacted
Full-Text: f7a5351a9 agent/PLAN-stop-hook-cadence.md
Full-Text-Blob: af70feee31f7c4646bb5fe3783be6bbfc4814871
Record-Sig: 73f26660

## Why
The Stop hook forced continuations often enough that sessions spent turns satisfying checks rather than shipping. Section 1 cut the measured noise (roster, world signature, brief staleness, the verdict's reason), section 3 changed WHEN the hook blocks, section 4 added an `--intent` channel, and section 2, batching the rotating tier, was always the speculative remainder.

## Outcome
PARTIALLY SHIPPED, and the missing part is the part the plan itself booked as never ordered. Measured 2026-09-06: the roster cap at `.claude/hooks/stop/wl_liveness.py:725` with its truncation and counted summary; the ownership-scoped world signature with its bucketed peer count; the brief work gate, landed narrower than designed so only the STALE verdict is downgraded and `missing`
still fires unconditionally; the verdict that prints WHY rather than an age; the cadence pause cap with its off-switch and the session-scoped block counter it needed; and `--intent` at `.claude/hooks/stop/worklist.py:1867` with its sidecar and the `intent-expired` violation pinned in the always-tier test. All of that in 120cd9e73. Section 2 is genuinely absent. THE FILE CARRIES TWO
GENERATIONS OF STATUS TEXT: below the true top line sits a later-dated paragraph asserting that `--intent` "does not exist yet and no code may reference it", which is now FALSE. A reader going top to bottom reads the true line first and the false one second.

## Lessons
- A plan that corrects its own stale status by APPENDING leaves both versions in
the file. Appending is honest about history and dishonest about state, which is why a record has exactly one Outcome.
- Section 4's own history is the sharper warning: an earlier revision claimed it
shipped when `grep -c` found zero references. The correction was written into the file, and then reality moved past the correction too.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:08:54Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: none
Gates: none
Why-Source: author
Read-History: `git show af70feee31f7c4646bb5fe3783be6bbfc4814871` recovers the text; `git log --find-object=af70feee31f7c4646bb5fe3783be6bbfc4814871 --all` names the commit

## History
- 2026-09-06T17:08:54Z compacted by 8f55d4f0 from `done` (record-sig 73f26660)
