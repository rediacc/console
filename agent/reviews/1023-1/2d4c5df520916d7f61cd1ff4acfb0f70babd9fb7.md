# Review 2d4c5df5: feat(hooks,ci): turbo-next skips blocked plans, --defer checks NOT-BEFORE, a --promote verb, per-spawn Owns, and two gates

Commit: 2d4c5df520916d7f61cd1ff4acfb0f70babd9fb7
Repo: console
Branch: 1023-1
Parent: 65bfe8b4512aca3772c470c1b62d3220f320e7c5
Patch-Id: 3951dce5ca24268c8122f33de1a8cfd62c0ef061
Reviewed-At: 2026-10-23T13:24:19Z
Model: claude-haiku-5-5
Cost: $0.0125 USD, 1 call(s), 41.6s
Diff: 146072 bytes, 25 files, truncated: yes
Unreviewed: .claude/hooks/stop/wl_prscope.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/worklist_messages.py, .claude/rediacc_hooks/plan_gate.py, .claude/rediacc_hooks/tests/test_plan_gate.py, .claude/rediacc_hooks/tests/test_wl_guide_and_deferrals.py, .claude/rediacc_hooks/tests/test_wl_identity.py, .claude/rediacc_hooks/tests/test_wl_planconc_narrow.py, .claude/rediacc_hooks/tests/test_wl_promote.py, .claude/rediacc_hooks/tests/test_wl_prscope.py, .github/workflows/ci-quality.yml, CLAUDE.md, docs/ci-overhaul/07-port-brief.md, package.json, scripts/ci-runner/gates.lock.json, scripts/ci-runner/manifest.ts, scripts/data/doc-registry.md
Verdict: findings
Attempt: 1
Labels: bump=minor kind=bug,feature,ci why=New --promote verb, check:ci-commit-citations and check:ci-proxy-cost-guard gates, plus a planning-hook fix for prerequisites and --defer validation: a new capability with bug fixes.
Dropped: 0
Body-Sig: 067625bff1994cf3

## Findings

### 2d4c5df5.1 [medium] .claude/hooks/stop/wl_planconc.py:645
Anchor: in-diff
Claim: In live_plans, a lease held by this session (`mine` true) adds a holder but appends no entry to `declared`, so `all(o for o in owns)` ignores that holder; when the writer rows for the plan all declared a subset Owns, LivePlans.owns narrows the plan to that subset even though a live holder with no declared Owns still runs on the whole plan. The `if not mine:` guard should cover every new holder, not only peer leases, and no test in the diff exercises a live_plans lease holder (test narrow l1/l2 set LIVE_T.owns by hand).
Resolution: fixed eb053fda0841286135bc41b3c0bccc446e93dd9f | d778be9d 2026-10-24T20:30:24Z
