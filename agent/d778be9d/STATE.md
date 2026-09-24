## SESSION d778be9d 2026-09-24T06:49:41Z

Branch 0923-1, PR #590. MAIN IS BROKEN (all GitHub Actions vars deleted on operator order; main's workflows still read vars.*) -- pr-babysitter a149262d8b6a1601f is landing PR #590 (item #f2dd1732; briefings reports/pr-babysit-0923-1-briefing.md + -v2.md). Operator runs /pr-merge.

## In flight
- OBS/rdc writer ae404e341fcdf699b (#f962bb8e): move /tmp/rediacc_20260426124447.json into ~/.config/rediacc/, fix ./rdc.sh, list repos, settle OBS_OTLP_CREDENTIALS JSON vs base64 (possible live prod telemetry defect) read-only.

## Uncommitted, NOT yet verified (resume here)
- .claude/rediacc_hooks/guards/block_nonstandard_branch_name.py: added a foreign-repo exemption (target_root outside this checkout -> ALLOW; submodules keep the rule). NEEDS cases in .claude/rediacc_hooks/tests/hookcases.py (git -C /home/developer/rovaip branch chore/x <sha> allowed; git -C private/account branch chore/x still blocked; plain git branch chore/x blocked) and a planted-defect proof, then tell the babysitter to absorb it.

## Operator rulings this stretch
- rovaip: another project. Local rovaip branches may be deleted (they were); NEVER touch rovaip remote branches.
- Drop gitlab e2e-test-separate-v2 (not yet done: delete it on the gitlab remote with `git push gitlab --delete e2e-test-separate-v2`, log its tip cc1870147 to .ci/cache/deleted-branches-all.txt first).
- Admin creds in ci-shared (done, gates green); dev keys _DEV in ci-shared; dev SES aliases EU (recorded in agent/plans/PLAN-account-env-to-bws.md).

## Next action
1. Finish the branch-name guard cases above and verify.
2. Delete gitlab e2e-test-separate-v2 per the ruling.
3. When a writer slot frees (babysitter + OBS hold both): run the stale-.sh plan update (#8ea2de80, survey done: 10 plans, 66 refs, all UPDATE), then the queue: stop-hook-overhaul 1.3, check:deps, harness output, report scaffold, shape counter, minimum-release-age, decided-not-done plan state, PLAN-account-env-to-bws boxes.
