# The DUPLICATION angle: trigger, verdict, and what the history actually says
Status: compacted
First-Seen: 2026-09-20
Full-Text-Blob: 49d0c8831c5086a49590a8c127d9a4ebd5b15e6e
Record-Sig: 5f819dd0

## Why
The shape-duplication gate was designed to detect repeated patterns in check scripts, but it was unclear whether it would fire so frequently (either over- or under-firing) as to be unusable. The plan aimed to calibrate the gate's thresholds and verify all three pieces (trigger, verdict, and divergence exit) could ship together.

## Outcome
Implemented and shipped. The gate was seeded and calibrated: 14/14 on the first fixture run, with accepted-divergence exit added. Measurement revealed: (1) gate over-fires in authoring months (74 times in Aug 2026 vs. plan's fear of 2x/year), driven by gate-authoring bursts, not under-firing; (2) design needed to accommodate legitimate divergences with BLOCKER-validated reasons,
not just a re-seed hammer; (3) calibration is not stable across samples (17/20 on extended run vs 14/14 initial).

## Lessons
- Shallow clone caused ~3,000× measurement error on commit add-rates—unshallow is non-negotiable for any measurement that touches history.
- Plan's gate-firing threshold was inverted: fear was under-fire (twice/year); actual is burst-fire (74 in one month). Measurement flips the risk and changes whether the design is viable.
- Four load-bearing claims about code were wrong: git ls-tree doesn't glob; counter output coordinates are not line numbers; importing the counter ran the whole gate; the 28-span cleanup opportunity is actually 62 spans where 46 can't use the helper (divergence, not duplication).
- Single-run calibration is not stable; re-running same fixtures on same rubric scored 17/20 not 14/14. Do not record a rubric as calibrated without stating sample size.
- Divergence-detection is real work: the gate fired legitimately on run-dedup code. Accepting specific divergences with reasons is cheaper than re-seeding and erasing the finding.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: implemented
Compacted-By: d778be9d
Compacted-At: 2026-09-20T16:45:45Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: 23ac415a, e87fa3ce
Touched: .ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh
Gates: check:ci-pytest
Why-Source: model
Read-History: `git show 49d0c8831c5086a49590a8c127d9a4ebd5b15e6e` recovers the text; `git log --find-object=49d0c8831c5086a49590a8c127d9a4ebd5b15e6e --all` names the commit

## History
- 2026-09-20T16:45:45Z compacted by d778be9d from `implemented` (record-sig 5f819dd0)
