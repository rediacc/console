# PLAN: stop-report output queue (one section per stop, priority + FIFO)
Status: compacted
Owner: queue-plan agent, branch 0731-2
Full-Text-Blob: 2d78c88a313dec8db7e5aaddf14a127f0119409e
Record-Sig: 8e0d1154

## Why
The allow report emitted all sections at once, overwhelming the operator with simultaneous notifications. The judge approval line was unnecessarily verbose on every stop. A deeper defect existed: the block path exits before emitting three one-shot entries (ladder pings, archived items, escalated requests), silently losing them on block stops.

## Outcome
Implemented in full and verified 2026-08-05. A per-session state doc now holds queued sections with priority-class (0/1/2) and FIFO ordering. Entries enqueue at COMPUTE time when budgets are spent, ensuring survival through block stops and crashes. Judge line changed to bare stamp, full reason shown only on context change or signature change. Test cases 173–177 added to validate
queue behavior, priority ordering, and one-shot survival.

## Lessons
- One-shot entries must be enqueued at COMPUTE time (when the producer spends its budget), not at emit time, to survive block stops. The three silently-lost entries (ladder pings, archived items, escalated requests) proved this the hard way.
- Sticky one-shot entries don't track shown[] because their producer cannot re-fire by construction; showing twice is cosmetic but loss is the failure this prevents.
- Volatile entries detect content changes by signature and re-enqueue at priority, with FIFO as tiebreak — both dimensions are load-bearing and neither can be skipped.
- Block path and queue must remain separate systems: blocks state true-now evidence, queued entries are aged and may describe violations already fixed, so merging them makes blocks unreliable.
- Test one-shot survival through competing class-0 entries explicitly (case 176 leg 2) — a naive drop bug is invisible to headline tests and requires this scenario to catch it.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:12:41Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: none
Gates: none
Why-Source: model
Read-History: `git show 2d78c88a313dec8db7e5aaddf14a127f0119409e` recovers the text; `git log --find-object=2d78c88a313dec8db7e5aaddf14a127f0119409e --all` names the commit

## History
- 2026-09-20T18:12:41Z compacted by d778be9d from `done` (record-sig 8e0d1154)
