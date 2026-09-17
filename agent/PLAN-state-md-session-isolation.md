# PLAN: STATE.md session isolation
Status: compacted
Owner: 99ccf057
Full-Text: f7a5351a9 agent/PLAN-state-md-session-isolation.md
Full-Text-Blob: bb261677a201d15fcc277f98ee32d489d091d269
Record-Sig: 2ffbba40

## Why
STATE.md was keyed per BRANCH while sessions are per SESSION, and this repo routinely runs several sessions in one shared checkout. On 2026-08-09 three were live at once and one, obeying the Stop hook's staleness nag, destroyed a peer's entire state document: a live canary campaign, attempt 6 in flight, a watch id, five flag flips, an operator-owned design question. It was
recovered only because the writer read the single-slot backup before writing again; one write later and recovery would have been impossible. The staleness gate DROVE the collision, nagging every session on the branch on a 15-minute clock to rewrite the one shared file.

## Outcome
SHIPPED, as ONE commit exactly as the plan demanded, b93097be1. Measured 2026-09-06: the section parser and renderer, the mine/dead/briefing predicates, the reap archive path and the future-skew constant are all in the store module; the new message constants are consumed by the PostCompact peers note and the class-2 peer note in the checks module; and the pre-edit guard now denies
ALL tool writes to STATE.md, leaving `worklist.py` the only writer. ONE HEADER CORRECTION AND ONE LATER DEVIATION. The header says "IMPLEMENTED, uncommitted" and it was committed the same day. And the document is no longer branch-keyed at all: f7a5351a9 re-keyed it to `agent/<session-prefix>/STATE.md`, which is the alternative this plan's section 3.10 explicitly REJECTED. The
sectioning, merge, reap and peer machinery survived on top of that change.

## Lessons
- A staleness gate over a shared file manufactures the collision it then
reports. Ownership had to move before the cadence could be trusted.
- A rejected alternative can win later. This record says so rather than leaving
the plan's rejection standing as the last word on the layout.

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
Read-History: `git show bb261677a201d15fcc277f98ee32d489d091d269` recovers the text; `git log --find-object=bb261677a201d15fcc277f98ee32d489d091d269 --all` names the commit

## History
- 2026-09-06T17:08:54Z compacted by 8f55d4f0 from `done` (record-sig 2ffbba40)
