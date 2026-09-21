# PLAN: the always-tier, and three checks that could never reach a reader
Status: compacted
First-Seen: 2026-09-20
Owner: unowned (drafted by 9d92d9b6, 2026-08-28)
Full-Text-Blob: 4117fa10f7f154c69832f9a53c7231a9ff2de6b3
Record-Sig: fa47aabb

## Why
The operator was not seeing critical blocking notifications because three checks that must always surface—`no-waiter-asked`, `no-waiter`, and `requests`—were sitting in a rotating tier with ~23 other checks ahead of them. The `no-waiter-asked` check bumped its escalation ladder at compute time unconditionally, advancing rungs every stop whether or not the session saw them. The
file's own comment at lines 2965–2970 named the rule ("someone else pays for the silence") but left all three checks rotatable. Across 57 blocking stops, 4 unread sub-agent reports went unreported.

## Outcome
Landed in commit `12de2e910`. Promoted three checks to always-tier, where compute time and display time coincide so escalation ladders now walk correctly. Added tombstone mechanism to `wl_wait.py` (EXPIRED markers instead of unlinks) to distinguish lapsed from never-armed waiters. Implemented nudge decay instead of counter reset to prevent silence-buying by periodic waiter
re-arming. Added `ALWAYS_FULL_MAX=2` collapse (quote at most 2 invariants in full, rest as single-line summary) to keep the tier legible. Pinned always-key set in `test-always-tier.py` to detect future violations. Graduated `unread-reports` with time-based escalation. Tier expanded from 21 to 27 checks. Test suite: 854/0.

## Lessons
- Grace counters reset by their own failure create perverse incentives: arming a single waiter zeros `nudges_ignored`, allowing 30+ minutes of guaranteed silence after it lapses. Decay instead of reset.
- Rotation sorting via LRU + battery-order meant ~23 checks landed ahead of listening checks, so first sighting hit rung 5 of the escalation ladder instead of rung 1. Tier membership alone fixes this—no reordering needed.
- Checks with unreachable fire conditions don't vanish silently; the code itself must document the block. `no-waiter` required `live_work_crons` which was never true, but the comment lived beside unfixed code.
- The always-tier rule was written into file comments (2965–2970) but had no machine-enforced boundary. Violations went undetected until a human reported the night-long silence. Pin the set in tests.
- Lapsed vs never-armed waiters were structurally indistinguishable, so a session could buy indefinite silence by re-arming periodically. Tombstones (mtime-based EXPIRED markers) age out in 60s and cost nothing.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: landed
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:44:44Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: none
Gates: none
Why-Source: model
Read-History: `git show 4117fa10f7f154c69832f9a53c7231a9ff2de6b3` recovers the text; `git log --find-object=4117fa10f7f154c69832f9a53c7231a9ff2de6b3 --all` names the commit

## History
- 2026-09-20T16:44:44Z compacted by d778be9d from `landed` (record-sig fa47aabb)
