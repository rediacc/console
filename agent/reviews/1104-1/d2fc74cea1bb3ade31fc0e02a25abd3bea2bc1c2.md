# Review d2fc74ce: fix(drills): backup-window guard adds a run budget, the running-backup signal and a re-check before the delete

Commit: d2fc74cea1bb3ade31fc0e02a25abd3bea2bc1c2
Repo: console
Branch: 1104-1
Parent: e3299bf6ac1ab9e12007335cfb9805bb92419d3f
Patch-Id: bdd983a977d7c90dee00338c9d4173651c2f540f
Reviewed-At: 2026-11-06T12:16:03Z
Model: claude-haiku-5-5
Cost: $0.0089 USD, 1 call(s), 53.1s
Diff: 19422 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Internal CI drill guard fix with no product-facing change.
Dropped: 0
Body-Sig: 1a7897136d4f4277

## Findings

### d2fc74ce.1 [medium] .ci/rediacc_ci/drills/backup_window.py:18
Anchor: in-diff
Claim: The RUN_BUDGET_S comment says a start is refused only when a trigger falls in [now, now + RUN_BUDGET_S + LEAD_S], but window_verdict also refuses for 45 min after any trigger (trig + TAIL_S >= now), so the comment misstates the refused range.
Resolution: fixed 5b9ecc5ec3c9f51a62e2275124fa3491eeb074bf | d778be9d 2026-11-06T21:18:57Z

### d2fc74ce.2 [medium] .ci/rediacc_ci/drills/privdrop_probe.py:123
Anchor: in-diff
Claim: wait_until_clear checks only at elapsed 0..49 min (50 polls, the sleep after the last check is never followed by a check); if the re-check starts at trigger-5 min the window clears at about 50 min, so the loop gives up and prints 'never cleared' while the window is already clear, leaving the fork undeleted.
Resolution: fixed 5b9ecc5ec3c9f51a62e2275124fa3491eeb074bf | d778be9d 2026-11-06T21:18:57Z

### d2fc74ce.3 [low] .ci/rediacc_ci/drills/backup_window.py:39
Anchor: in-diff
Claim: The systemctl filter --state=activating,active,deactivating matches on ActiveState, so a rediacc-backup-*.service oneshot with RemainAfterExit=yes that sits in 'active (exited)' would refuse every run until it is stopped; the listing does not distinguish finished units from running ones.
Resolution: not-a-bug | packages/cli/src/services/backup/backup-schedule-unit-generator.ts:343 the generated backup services are Type=oneshot with no RemainAfterExit, so a finished one reads inactive | d778be9d 2026-11-06T21:18:57Z

### d2fc74ce.4 [low] .ci/rediacc_ci/drills/backup_window.py:111
Anchor: in-diff
Claim: When the read's listing fails, the row LIST-UNITS-FAILED is reported under 'a backup is running', so the refusal message names a running backup that was never observed.
Resolution: fixed 5b9ecc5ec3c9f51a62e2275124fa3491eeb074bf | d778be9d 2026-11-06T21:18:57Z
