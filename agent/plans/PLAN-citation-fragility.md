# PLAN: object-citation fragility in agent/ plans
Status: compacted
First-Seen: 2026-09-20
Full-Text-Blob: f439a5441017c0c19accc9ffebeea00394e3be5e
Record-Sig: a0c54f71

## Why
The agent/ plan corpus (86 files, 343 object citations) contained 33 unreachable tokens that would break on a fresh clone. Eight tokens were already fragile as loose objects from local filter-branch mutations. The gate's error message steered toward blob form universally, which was correct for file-content claims but wrong for commit-identity claims.

## Outcome
Eight fragile commit tokens repointed using subject-match plus git rev-list reachability verification. Tree-resolution kind added to wl_planrec.resolve and check_plan_citations.py ([unresolved]... now resolves correctly). UUID-tail exemption (UUID_TAIL_RE) added to citations() filter. Inline notes added at four dead-on-purpose and cross-repository sites. Changes verified against
check:ci-plan-citations gate.

## Lessons
- Blob form is correct for file-content claims but rewrites commit-identity claims: a blob names file state, not an event. The 62 healthy commit-identity citations stay as-is despite rebase fragility.
- Reachability oracle for fresh-clone survival is git rev-list --objects <target-ref>, not resolve()'s existence check or merge-base --is-ancestor. Local long-lived clones diverge from CI artifacts.
- Already-fragile tokens from filter-branch mutations were silently wrong on execution day, not hypothetical. Repointing them ranked higher than architectural prevention.
- Coincidental hex tokens (UUID tails, fingerprints, report IDs) need systematic gate exemption, not one-off fencing. UUID-tail pattern prevents Stripe/JWT/database-id citations from false flagging.
- Tree objects (alongside blob/commit) appear in rewrite-documenting plans. Adding tree-resolver-kind eliminated a class of false 'dead' findings.

## Boxes
- [x] Repoint the 8 already-fragile commit-identity citations. Done: 6 repointed with diff-content verified identical to the original (not just subject-matched), 2 correctly left as-is with an inline note instead of a false repoint (the first only reachable via a stale non-`origin/main` remote; the second part of an exact historical pointer-value mapping where substituting a same-subject commit would record the wrong value). One of the 8 turned out to be a file-content claim, not a commit-identity one, and was repointed to its tree id instead. The three tokens, quoted outside prose because they are deliberately unresolvable:
    (record) sig=4237ec1e done=c6e9c84c2
- [x] Handle the 9 coincidental hex tokens in class (c). Done via the systemic fix this plan recommended rather than 9 individual fences: `UUID_TAIL_RE` exemption landed in `check_plan_citations.py` (constant + `citations()` filter + 2 new selftest controls), verified against 2 real corpus sites directly. The 3 non-UUID-shaped tokens (fingerprint/report-id labeled) are not currently red and were left untouched.
    (record) sig=6f9c2842 done=c6e9c84c2
- [x] Add a `tree` resolution kind. Done: `wl_planrec.resolve` (+`RESOLVE_KINDS`) and `check_plan_citations.py`'s `unresolved()`, verified live against `444e9c09092a80bbb7defa6eea122e0de28a89eb` (now resolves as `tree`; `blob`/`commit` correctly still refuse it).
    (record) sig=65c3008d done=c6e9c84c2
- [x] Add inline notes at the dead-on-purpose / cross-repo citations. Done for all 4 plus the 2 stale "see git log" pointers below, plus 2 more found while doing this work (`c05edbba`, `f020473e`) that needed the same treatment.
    (record) sig=911d45dd done=c6e9c84c2
- [x] Repoint or note the 2 stale "see git log" pointers in `agent/plans/PLAN-stop-report-queue.md:8`. Done (noted, truncated below the citation threshold).
    (record) sig=c977c684 done=c6e9c84c2
- [x] Leave the 62 healthy commit-identity citations and 53 `Full-Text-Blob:` citations untouched. Done — none were touched.
    (record) sig=46f5fd50 done=c6e9c84c2

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: d778be9d
Compacted-At: 2026-09-20T18:10:29Z
Boxes: 6 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: agent/plans/PLAN-stop-report-queue.md, agent/plans/PLAN-git-history-media-rewrite.md, agent/plans/PLAN-fix-ci-contention-aware-timeouts.md, agent/plans/PLAN-fix-tutorial-player-debug-hook-attachment.md, agent/plans/PLAN-secret-namespace-migration.md, agent/plans/PLAN-www-bundle-determinism.md, agent/plans/PLAN-env-to-bitwarden-v2.md, agent/plans/PLAN-promote-mutation-runner.md, agent/plans/PLAN-subagent-idle-detection.md
Gates: check:ci-plan-citations, check:ci-shape-duplication
Why-Source: model
Read-History: `git show f439a5441017c0c19accc9ffebeea00394e3be5e` recovers the text; `git log --find-object=f439a5441017c0c19accc9ffebeea00394e3be5e --all` names the commit

## History
- 2026-09-20T18:10:29Z compacted by d778be9d from `done` (record-sig a0c54f71)
