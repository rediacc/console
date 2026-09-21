# Resource profiling, wave 2: make the layer true, then make it readable
Status: compacted
First-Seen: 2026-09-20
Owner: 74de73ca (2026-09-03)
Full-Text-Blob: a36167a98560c5a625503e65cf881c45eefe6fe7
Record-Sig: 0f1af721

## Why
The claim in docs/ci-overhaul/06-progress.md that 'Every Bash and Python invocation now leaves a record' was false in three independent ways: plain python3 leaves no record (only code importing wl_core is instrumented), the devbox records no bash at all (bashcov-sup is missing), and bash records were write-only with no readers. Additionally, the measured corpus (223 MB, 17,300
files) was 7× larger than claimed (32 MB, 2,363 files) because CI capture folders dominated but were invisible in the ranking.

## Outcome
Approved 2026-09-03 by operator; rides open PR #585 on branch 0903-1 as a single unseeded, report-only gate. Pieces 2–3 landed 2026-09-04: bashcov-sup is now built in devbox-autostart.sh, check_resprofile.py treats zero bash records as UNJUDGEABLE, and bash records gained a repo-relative shape field. The ranking immediately surfaced the single largest entry (sh:-c at 57,718 CPU
seconds). Run-delay signal fixed by probing instead of reading sysctl. Stall discriminator measured at 0 stalls across six largest real captures. Retirement trigger set for 2026-10-03 evaluation: retire if fewer than 2 Resprofile: trailers in 30 days or both top rows unchanged.

## Lessons
- Coverage claims need adversarial verification before trust: the false claim in production docs revealed only by actually running the instrumentation and counting records, not by reading code.
- The corpus was 7× larger than claimed because capture folders (CI automation artifacts) dominate, not the measurement itself — the layer's retention cost was hidden in CI infrastructure, not obvious from the layer's own codepaths.
- Invisible output is ballast: giving bash records a repo-relative shape field (not the full execution string) immediately revealed the single largest entry in the corpus that ranking could not see before.
- Environmental constraints are hard: devbox and host differ in sysctl settings, file permissions, and installed tools (cgroup v2 ro, perf_event_paranoid=2, bashcov-sup missing) — the instrument had to be designed for the constraints, not the ideal.
- Anti-vacuity rules prevent silent failures: treating zero bash records as UNJUDGEABLE (not clean) caught the exact signature of the missing supervisor before the layer could lie through inaction.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: approved
Compacted-By: d778be9d
Compacted-At: 2026-09-20T17:58:59Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: 24c98380, e87fa3ce
Touched: docs/ci-overhaul/06-progress.md
Gates: none
Why-Source: model
Read-History: `git show a36167a98560c5a625503e65cf881c45eefe6fe7` recovers the text; `git log --find-object=a36167a98560c5a625503e65cf881c45eefe6fe7 --all` names the commit

## History
- 2026-09-20T17:58:59Z compacted by d778be9d from `approved` (record-sig 0f1af721)
