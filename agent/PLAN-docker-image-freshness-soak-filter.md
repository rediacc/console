# PLAN: docker image freshness must soak on release age, not rebuild age
Status: compacted
Owner: 854ac1c6
Full-Text-Blob: 8a20e7d7e8d59b4a066a2472883dc5be5aadaa0f
Record-Sig: b1139704

## Why
The Docker image freshness gate used the wrong timestamp to enforce the 1440-minute soak window on stale pins. It checked `tag_last_pushed` from Docker Hub, which for Official Images is a rebuild timestamp, not a release date. Python, for example, rebuilds every supported minor on a schedule, stamping 3.10-3.15 within one minute. This caused the gate to oscillate: on rebuild waves it read "no longer stale" (wrong), and 24 hours later "newly stale past the soak" (wrong). Three spurious drains were demanded in one session.

## Outcome
Landed in commit [unresolved] on branch 0825-1. The fix changes the soak logic: instead of filtering all newer candidates unconditionally, it sorts them newest-first, drops only the single newest if inside the window, and treats whatever remains as staleness evidence. This correctly distinguishes a rebuild wave (stale, via the next-newest tag) from a brand-new release (not stale, soak still running). The two spurious drains that had been committed (dependency changes to node and golang versions) were reverted, and `scripts/data/docker-image-freshness-baseline.json` restored to match main. The gate now passes with no drains.

## Lessons
- Docker Official Images rebuild on a schedule, not on release — `tag_last_pushed` is a rebuild timestamp and cannot distinguish years-old Python 3.10 from a brand-new 3.14.
- A shrink-only baseline will oscillate when detection logic is wrong — oscillation itself is a symptom of the root cause, not a reason to commit the drains.
- Soak windows must apply to the newest candidate only; applying them to all candidates defeats their purpose of protecting new releases.
- Six test cases, including three that fail pre-fix, can be embedded in the gate's own `--selftest` battery to prevent regression.
- A pin's own push date does not bear on staleness — staleness is about whether a newer version exists, soaked or not.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T12:25:50Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: scripts/gates/check-docker-image-freshness.ts
Gates: check:ci-docker-image-freshness
Why-Source: model
Read-History: `git show 8a20e7d7e8d59b4a066a2472883dc5be5aadaa0f` recovers the text; `git log --find-object=8a20e7d7e8d59b4a066a2472883dc5be5aadaa0f --all` names the commit

## History
- 2026-09-20T12:25:50Z compacted by d778be9d from `done` (record-sig b1139704)
