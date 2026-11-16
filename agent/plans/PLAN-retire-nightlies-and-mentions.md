# PLAN: retire the daily drift and backup schedules, make stable promotion manual-only, and end @mentions and auto-opened issues
Status: proposed -- operator rulings 1-5, ASKED:2026-11-16T09:19Z, quoted verbatim under Rulings; awaiting approval of the packaging below
Owner: d778be9d
Updated: 2026-11-16
Priority: P2 -- every removed schedule costs runner minutes and mail each day, and every auto-opened issue duplicates a worklist item; nothing breaks while it waits
Depends-On: no-dep -- every box edits landed code; box R3 of agent/plans/PLAN-health-checks-local.md (retire ops-nightly-status.yml with its mentions moved) is superseded here by box P1, not waited on
Concurrency: parallel -- writers S1, N1, N3, B1, G1 and G2 own disjoint files and run side by side; N2 runs after N1 lands; lead boxes R1, D1 and P1 run after every writer lands. PLAN-health-checks-local.md also owns .ci/config/ops-health.json and .ci/config/ci-alerts.json, so N1 starts only when no writer of that plan is live
Owns: agent/plans/PLAN-retire-nightlies-and-mentions.md, .github/workflows/ci-drift.yml, .github/workflows/cd-release-stable.yml, .github/workflows/ci.yml (header comment only), .github/workflows/ct-backup-nightly.yml, .github/workflows/ct-tests.yml (comment only), .github/workflows/ops-nightly-status.yml, .github/workflows/ops-housekeeping.yml (budget-check job only), .github/workflows/ops-d1-size-report.yml, .github/workflows/ci-quality.yml (comment only), .github/labels.yml, .ci/rediacc_ci/release/{check_soak_period,nightly_tested_edge,drift_job}.py, .ci/rediacc_ci/ops/d1_size_report.py, .ci/rediacc_ci/quality/{label_inventory,scope_scripts_reachability}.py, .ci/rediacc_ci/ci/github_status.py, .ci/rediacc_ci/tests/{test_release_check_soak_period,test_release_nightly_drift_waiver,test_release_nightly_tested_edge,test_release_drift_job,test_release_drift_job_budget,test_d1_size_report,test_quality_label_inventory,test_ci_publish_verdict}.py, .ci/rediacc_ci/tests/gates/{test_gate_nightly_status_report,test_gate_label_inventory}.py, .ci/rediacc_ci/tests/goldens/label-inventory/**, .ci/rediacc_ci/tests/goldens/twins/quality.check-profiler-coverage.jsonl, .ci/scripts/ci/{report-nightly-status,greenlight,scope-map}.cjs, scripts/ci/report-budget-check.cjs, .ci/config/{ci-alerts,ops-health,lane-durations,prose-style-baseline}.json, .ci/config/shards/quality-pytest.json, .ci/policy/.profiler-coverage-allowlist, .ci/policy/README.md, scripts/data/{domain-layout-baseline,domains}.json, scripts/data/doc-registry.md, .claude/hooks/stop/wl_schedred.py, .claude/rediacc_hooks/tests/test_wl_schedred.py, .claude/rediacc_hooks/guards/{block_issue_create,test-block_issue_create}.py (new), .claude/rediacc_hooks/guards/{block_unasked_release,test-block_unasked_release}.py, docs/agent-reference/{release-process,ci-gates}.md, CLAUDE.md (release and issue lines only), agent/plans/{PLAN-backup-program,PLAN-first-release-checks,PLAN-health-checks-local}.md (correction lines only)
Live-Proof: none -- every Owns glob is CI, hook or doc tooling and hits no surface of .ci/config/proof-tiers.json (box L4 proves the ops-health Worker config), per "Deploy tooling and proof tooling are not surfaces." in docs/agent-reference/plan-records.md

## Rulings (operator, ASKED:2026-11-16T09:19Z, verbatim)
1. Stable promotion is manual only: remove the `CI - Drift` daily (`.github/workflows/ci-drift.yml`, cron 15 2) and the 06:00 cron of `.github/workflows/cd-release-stable.yml`, including the Drift `workflow_run` trigger; stable promotes only by dispatch or `release:local` after the 7-day soak (or with RELEASE_ASKED). Keep the weekly Console CI schedule (`ci.yml` cron 0 1 * * 0) as the soak-waiver evidence.
2. Remove `ct-backup-nightly.yml` (daily backup suites 26/27); PR and weekly coverage when backup paths change stays.
3. Keep the probes, housekeeping (cleanup, retry), pins-soaked and the OBS mirror schedules.
4. Notifications: no @mentions and no auto-opened issues. Empty `.ci/config/ci-alerts.json` mention and `.ci/config/ops-health.json` github_mentions; delete `.github/workflows/ops-nightly-status.yml`, the issue/comment code of `.ci/scripts/ci/report-nightly-status.cjs` and `scripts/ci/report-budget-check.cjs` (the budget-check job then reports to the job log only), the `nightly-red` label (`.github/labels.yml`, `label_inventory.py`), the d1-size-report alert issue (`--alert-issue`), and their tests. Keep the ops-health Worker email.
5. New Claude hook guard: block `gh issue create` (and API equivalents such as `gh api .../issues -X POST`) from agent Bash; the refusal tells the agent to ask the operator, because the planning system (agent/plans, worklist) replaces issues.

## Context (checked 2026-11-16 on 1104-1)

### C1. The schedules today
Twelve workflows carry a `schedule:` key. The three this plan removes:
- `CI - Drift`, cron `15 2 * * *` (.github/workflows/ci-drift.yml:27). It runs `rediacc_ci.release.drift_job` (.github/workflows/ci-drift.yml:142) and posts the verdict to the ops-health ingest as source `drift` (.github/workflows/ci-drift.yml:168).
- `CD - Release to Stable`, cron `0 6 * * *` (.github/workflows/cd-release-stable.yml:4-5), plus a `workflow_run` trigger on `CI - Drift` (.github/workflows/cd-release-stable.yml:23-26) filtered by the job `if:` (.github/workflows/cd-release-stable.yml:52-56).
- `CT Backup Nightly`, cron `30 3 * * *` (.github/workflows/ct-backup-nightly.yml:15-16), which calls ct-tests.yml with `backup_changed: 'true'` (.github/workflows/ct-backup-nightly.yml:9-12).

Kept by ruling 3 or untouched by any ruling: ci.yml weekly (.github/workflows/ci.yml:24), ops-housekeeping.yml (.github/workflows/ops-housekeeping.yml:27), ops-pins-soaked.yml, ci-obs-mirror.yml, ops-telemetry-probe.yml, ct-backup-perf.yml (weekly, `30 2 * * 6`), ci-vm-bake.yml (monthly), ops-cf-usage-report.yml (weekly) and ops-d1-size-report.yml (daily, `41 5 * * *`, kept as a schedule; only its alert issue goes).

### C2. How the soak waiver is wired
- The weekly evidence step runs only on the drift trigger: `if: ... && github.event_name == 'workflow_run'` (.github/workflows/cd-release-stable.yml:134-139). A dispatch therefore never reads the weekly run today, so ruling 1's "keep the weekly run as the soak-waiver evidence" needs that step moved onto `workflow_dispatch`.
- `check_soak_period.main` enables the waiver only for `PROMOTE_TRIGGER == "workflow_run"` and refuses a drift run that did not conclude success or failure (.ci/rediacc_ci/release/check_soak_period.py:280-298, the refusal at :180-186). The docstring states both rules (.ci/rediacc_ci/release/check_soak_period.py:5-7).
- `nightly_tested_edge.drift_run_qualifies` (.ci/rediacc_ci/release/nightly_tested_edge.py:235-251) exists only for the drift trigger. `weekly_evidence`, `WEEKLY_MAX_AGE_DAYS = 8` and `drift_steps()` (.ci/rediacc_ci/release/nightly_tested_edge.py:68-84, :237-241) are what the weekly waiver itself needs, and they stay. Its docstring still says a red run opens the nightly-red issue (.ci/rediacc_ci/release/nightly_tested_edge.py:9).
- `drift_job` imports `DRIFT_GATE_IDS` and the split step names from nightly_tested_edge (.ci/rediacc_ci/release/drift_job.py:26-33). Nothing outside ci-drift.yml and its two tests runs it (`git grep drift_job` outside .ci/rediacc_ci/release and the tests finds only lane-durations and shard rows). `ops_health_post` stays, because ci.yml's `report-schedule` job posts `ci-weekly` through it (.github/workflows/ci.yml:2455).
- `UPSTREAM_GATES` (.ci/rediacc_ci/security/ci_workflow_invariants.py:1023-1034) and its schedule assertion (`upstream-gate-schedule-skipped`, :1143) judge ci.yml's weekly run and the PR lanes, not ci-drift.yml. No invariant names ci-drift.yml, so neither changes. The only schedule assertion on a kept workflow is the pins-soaked one (:1604-1617), untouched. `workflow_gates.py` names no affected workflow (its one "nightly" hit, .ci/rediacc_ci/security/workflow_gates.py:368, is a comment).
- Tests that drive the drift trigger: test_release_check_soak_period.py (`DRIFT_CONCLUSION` at .ci/rediacc_ci/tests/test_release_check_soak_period.py:174, :396, :414, :700-726), test_release_nightly_drift_waiver.py (.ci/rediacc_ci/tests/test_release_nightly_drift_waiver.py:467-468) and test_release_nightly_tested_edge.py (`drift_run_qualifies` at .ci/rediacc_ci/tests/test_release_nightly_tested_edge.py:38-50).

### C3. `release:local --channel stable` is refused today
`rediacc_ci.release.local` refuses `--channel stable` and names cd-release-stable.yml (.ci/rediacc_ci/release/local.py:7, :65-66). An invariant holds that refusal (.ci/rediacc_ci/security/ci_workflow_invariants.py:724-725), and so does guard rule 3 of `block_unasked_release` (.claude/rediacc_hooks/guards/block_unasked_release.py:7). The stable gate itself exists in `local_gates` (.ci/rediacc_ci/release/local_gates.py:14, :522-535). Ruling 1 names `release:local` as a promotion path; this plan does not lift the 2026-10-27 refusal on that reading alone (question Q1).

### C4. A stable dispatch is not guarded
CLAUDE.md says a stable deploy always needs RELEASE_ASKED (CLAUDE.md:268), yet `block_unasked_release` has no `gh workflow run` arm (`grep -n '"workflow"' .claude/rediacc_hooks/guards/block_unasked_release.py` prints nothing). Today the schedule promotes without anyone asking; once promotion is dispatch-only, an agent `gh workflow run` of the stable workflow is the whole path, so box G2 adds the ask.

### C5. Mentions and issues
- `report-nightly-status.cjs` owns the rolling issue: label `nightly-red` (.ci/scripts/ci/report-nightly-status.cjs:25), mentions read from ci-alerts.json (:39-72), create, comment and close (:106, :114, :318, :325). Its only caller is ops-nightly-status.yml (.github/workflows/ops-nightly-status.yml:68-76). It also carries the weekly run's budget section (`budgetSectionFor`, .ci/scripts/ci/report-nightly-status.cjs:130), which goes with it (question Q4).
- `report-budget-check.cjs` imports the label, title and mention helpers from it (scripts/ci/report-budget-check.cjs:12-18) and creates or comments on the same issue (:89, :113). Its caller is the housekeeping `budget-check` job, which holds `issues: write` for it (.github/workflows/ops-housekeeping.yml:270, :310-316). The job's own red stays (`exit 1`, .github/workflows/ops-housekeeping.yml:318-320).
- ci-alerts.json lists one handle (.ci/config/ci-alerts.json:9). ops-health.json lists one under `github_mentions` (.ci/config/ops-health.json:50), which no code reads: the Worker's config type has no such key (workers/ops-health/src/config.ts:6-18) and `git grep github_mentions` finds only the config file.
- The label: declared in .github/labels.yml:63-65 under a comment naming its creator (:54), and forgiven absence by `CREATE_ON_DEMAND` (.ci/rediacc_ci/quality/label_inventory.py:207), whose reason sits in the docstring (:29-36, :49-54). The gate compares both directions against the live repo, so the live label must be deleted when the declaration goes (box L3).
- d1-size: `--alert-issue` (.ci/rediacc_ci/ops/d1_size_report.py:500-519) runs `sync_alert_issue` (:433) through `_real_gh`, with `_ONCE` naming `issue create` and `issue comment` (:474). The workflow step runs it on rc 3 under `issues: write` (.github/workflows/ops-d1-size-report.yml:28, :62-68). Its tests are .ci/rediacc_ci/tests/test_d1_size_report.py:310-485.
- Other issue writers checked and kept: ci.yml `pr-labels` holds `issues: write` to create labels (.github/workflows/ci.yml:2186-2189), ops-claude-review.yml upserts a PR marker comment (.github/workflows/ops-claude-review.yml:100), and label-guide-comment.cjs comments on PRs (.ci/scripts/ci/label-guide-comment.cjs:185). None opens an issue or @mentions anyone.

### C6. The agent-side watchers
- `wl_schedred` discovers scheduled workflows from the tree (.claude/hooks/stop/wl_schedred.py:6), so the removed ones drop out of the watch by themselves. Its `_BLOCKS` row for `ci-drift` (.claude/hooks/stop/wl_schedred.py:57) and its docstring's nightly-red sentence (:3) go stale. The pin test lists `cd-release-stable`, `ci-drift` and `ct-backup-nightly` (.claude/rediacc_hooks/tests/test_wl_schedred.py:210, :219, :221) and must lose all three.
- `wl_ci.py` has no drift, schedule-stem or nightly-red reference (`grep -n -i "schedule\|drift\|nightly" .claude/hooks/stop/wl_ci.py` hits only .claude/hooks/stop/wl_ci.py:359 and :1061, both unrelated prose). No change.
- test_ci_trace_scheduled.py replaces wl_schedred with a recording fake and names no removed stem (.ci/rediacc_ci/tests/test_ci_trace_scheduled.py:3, :242). No change.
- test_gate_nightly_retry_filters.py drives housekeeping's retry sweep (.ci/rediacc_ci/tests/gates/test_gate_nightly_retry_filters.py:1-15), which ruling 3 keeps. No change.

### C7. Registries and baselines that name removed files
- lane-durations: .ci/config/lane-durations.json:519 (nightly status test), :1177 and :1204 (drift tests).
- pytest shards: .ci/config/shards/quality-pytest.json:26, :332 and :885.
- ops-health ingest age `drift: 36` (.ci/config/ops-health.json:30). A stale ingest entry is ignored, never red (`ingestFresh`, workers/ops-health/src/state.ts:192-200), so dropping the key changes no verdict. The Worker bundles the file (workers/ops-health/src/config.ts:1) and deploy_ops_health hashes it into the code sha (.ci/rediacc_ci/ops/deploy_ops_health.py:69), hence box L4.
- profiler allowlist rows for the deleted job: .ci/policy/.profiler-coverage-allowlist:111-112 and .ci/policy/README.md:357.
- prose baseline row: .ci/config/prose-style-baseline.json:865. Domain rows: scripts/data/domain-layout-baseline.json:13 and scripts/data/domains.json:196.
- twins golden corpus records the deleted workflow text: .ci/rediacc_ci/tests/goldens/twins/quality.check-profiler-coverage.jsonl:8 and :39.
- doc-registry rows regenerated by gen-docs: scripts/data/doc-registry.md:1208 (ct-backup-nightly.yml) and :1277 (ci-alerts.json). gate-costs.json has no row for any removed file.
- Comments naming removed files: .github/workflows/ci.yml:9-15, .github/workflows/ct-tests.yml:110-114, .github/workflows/ci-quality.yml:2452-2453, .ci/scripts/ci/greenlight.cjs:186, .ci/scripts/ci/scope-map.cjs:163, .ci/rediacc_ci/quality/scope_scripts_reachability.py:181, .ci/rediacc_ci/ci/github_status.py:15, and test_ci_publish_verdict.py reads the deleted cjs (.ci/rediacc_ci/tests/test_ci_publish_verdict.py:367-371).
- Docs: the stable section (docs/agent-reference/release-process.md:87-95), the nightly report section (docs/agent-reference/ci-gates.md:413-416) and the label exemption sentence (docs/agent-reference/ci-gates.md:437). CLAUDE.md's release paragraph (CLAUDE.md:268) and its issue doors (CLAUDE.md:48-50, :101, :103).

### C8. The guard pattern
- A guard is a module under .claude/rediacc_hooks/guards/ found by dispatch.py's glob (scripts/data/doc-registry.md:582-615 list every one as "via dispatch.py (glob)"). It declares `CHAIN`, `ORDER`, a `DEFECT` pair the differential plants, `EDGE_CASES`, and `run(ev)` returning `hookio.ALLOW` or `hookio.DENY`. Examples: .claude/rediacc_hooks/guards/block_ci_skip_token.py:12-36 and .claude/rediacc_hooks/guards/block_second_open_pr.py:28-31.
- ORDER values of one chain form a contiguous run with no gap or duplicate (.claude/rediacc_hooks/tests/test_dispatch.py:70-71). The highest pre-bash ORDER today is 70 (.claude/rediacc_hooks/guards/block_shape_lessons.py:19).
- `OWN_SUITE = True` swaps the golden for a dedicated `test-<stem>.py` beside the guard (.claude/rediacc_hooks/tests/test_guards_differential.py:768-770).
- Reusable parsers: `shellscan.gh_args` (.claude/rediacc_hooks/shellscan.py:6144), already used to recognise `gh issue create` by block_commit_meta (.claude/rediacc_hooks/guards/block_commit_meta.py:474-479), and `api_method`, which applies gh's rule that a body flag means POST (.claude/hooks/lib/sanctioned.py:423-433).
- `issues/<n>/comments` is the PR-comment endpoint wl_prreview answers reviews through (.claude/hooks/stop/wl_prreview.py:317, :595, :937), so the guard must admit it: only creating an issue is refused.

### C9. Plans that lean on the removed pieces
| Plan, box | What it leans on | Re-route (box P1 writes the correction line) |
|---|---|---|
| agent/plans/PLAN-health-checks-local.md:531 R3 | retire ops-nightly-status.yml but move the mentions to `github_mentions` | superseded by N1 under ruling 4 (no mentions); R3 closes citing this plan's N1 commit |
| agent/plans/PLAN-backup-program.md:366 J6 | suite 26 "at least nightly" | "weekly (ci.yml full suite) and on backup-path changes"; the Local-route line at :367 stands; Accept unchanged |
| agent/plans/PLAN-first-release-checks.md:74 L5 | "promote-stable (soak or nightly waiver)" | promote-stable by dispatch after the soak or with the weekly waiver; the soak tag at :76 stands |
| agent/plans/PLAN-first-release-checks.md:98-99 L5 | phase 1 "rides the merged release through promote-stable" | the promotion no longer starts by itself: phase 1 is a dispatch with RELEASE_ASKED (G2) |
| agent/plans/PLAN-first-release-checks.md:69 L2 | `release:local --channel stable` | refused today (C3); waits on Q1 |
| PLAN-nightly-green.md box N0 (untracked) | "the first `CI - Drift` run" | the Drift half drops; the weekly-run half stays |
| PLAN-nightly-green.md box F2 (untracked) | `drift_job` CLOCK_GATE_IDS and a forecast pass | drift_job is deleted (S1), so F2 retires; the clock gates still run on every PR and on the weekly run. Question Q3 asks whether the forecast pass moves to housekeeping |

PLAN-nightly-green.md is untracked and owned by session e0f36861, so P1 hands its two corrections to that owner instead of editing the file.

Plans that say "nightly" about something this plan keeps, checked and left alone: agent/plans/PLAN-proxy-cd-six-targets.md:306 N1 and agent/plans/PLAN-cloudflare-proxy.md:81 B4 (the weekly ci.yml run), agent/plans/PLAN-ciquick-reds-1023-1.md:41 R4 and agent/plans/PLAN-ci-quick-cpu-scheduling.md:75 P3 (housekeeping captures), agent/plans/PLAN-backup-program.md:400 K10 (ct-backup-perf.yml, weekly). The machine-side nightly units are renet and account crons, not GitHub schedules: agent/plans/PLAN-hostinger-to-bench.md:75-76, agent/plans/PLAN-product-domain-rename.md:199, agent/plans/PLAN-first-release-checks.md:143 and agent/plans/PLAN-d1-scaling.md:177.

## Design

### D1. Stable promotion: dispatch only, with the weekly waiver and a dry run
- cd-release-stable.yml keeps one trigger, `workflow_dispatch`, with inputs `force` (unchanged) and a new `dry_run` (boolean, default false). The schedule, the `workflow_run` block, the job `if:` and their comments go (.github/workflows/cd-release-stable.yml:4-5, :12-26, :47-56).
- The "Find the weekly fleet run" step runs on every dispatch that is not `force` (its condition becomes `inputs.force != true`). `check_soak_period` reads `PROMOTE_TRIGGER == "workflow_dispatch"` and not FORCE as "use the weekly evidence". `DRIFT_CONCLUSION`, `trigger_refusal` and `drift_run_qualifies` are deleted, so a dispatch can be decided by force, the weekly waiver or the soak, in that order.
- `dry_run: true` stops the job after "Check soak period": every later step carries `inputs.dry_run != true`, and the step summary prints the selection. No R2, Docker or tag write runs. The verify jobs downstream already key on `promoted`, which a dry run never sets.
- Deleted: ci-drift.yml, drift_job.py and its two tests. `ops_health_post` stays for `ci-weekly`.
- The `drift` ingest age leaves ops-health.json (owned by N1, since N1 holds that file).
- `local_gates.py` calls `select` without the drift arguments already (.ci/rediacc_ci/release/local_gates.py:522-529), so it is not edited.

### D2. Notifications
- Deleted: ops-nightly-status.yml, report-nightly-status.cjs, report-budget-check.cjs and test_gate_nightly_status_report.py.
- The housekeeping budget-check job keeps its check step and its fail step. The github-script report step is replaced by a step that prints `/tmp/budget-check.txt` to the log and appends it to `$GITHUB_STEP_SUMMARY`. `issues: write` leaves the job, and the comment block above it (.github/workflows/ops-housekeeping.yml:259-264) is rewritten to say the job reports to its log.
- ci-alerts.json keeps its file with `"mention": []` and a `$comment` naming ruling 4. ops-health.json gets `"github_mentions": []` with its comment line rewritten the same way. Both keep the shape the ruling asked for; Q2 asks whether two configs nobody reads should go instead.
- `nightly-red` leaves labels.yml and `CREATE_ON_DEMAND`, together with its docstring reason and the tests and goldens that seed it. `bug` and `automated` stay declared; the comment above them stops naming the deleted creator.
- d1_size_report loses `--alert-issue`, `sync_alert_issue`, `_find_alert_issues`, `alert_marker`, `_real_gh`, `GhError` and `_ONCE`, plus their tests. The workflow loses the alert step and `issues: write`. The report step exits non-zero on rc 3, so an alert reds the scheduled run, which wl_schedred already surfaces to a session.

### D3. The issue guard
- `block_issue_create.py`: `CHAIN = "pre-bash"`, `ORDER` the next free pre-bash value at landing (71 today), `OWN_SUITE = True`.
- It refuses, in any repository and under `sh -c`, env prefixes or `cd`:
  - `gh issue create`, parsed through `shellscan.gh_args`;
  - `gh api` to an endpoint ending `repos/<owner>/<repo>/issues` whose method is POST by `api_method`, whether `-X POST`, `--method POST` or a body flag gave it;
  - `gh api graphql` whose query carries a `createIssue` mutation;
  - `curl` with a POST or data flag to an `api.github.com/repos/<owner>/<repo>/issues` URL.
- It admits `gh issue list|view`, every GET, and `issues/<n>/comments` (C8), plus prose that merely names the command.
- The refusal names the ruling: issues are retired, agent/plans and the worklist replace them, track the finding with `worklist.py --add` or a plan, and ask the operator if a GitHub issue is still wanted. It names no escape variable.
- `DEFECT` empties the create-verb test, so the differential proves a planted bypass is caught.

### D4. Asking for a stable dispatch
`block_unasked_release` gains an arm: `gh workflow run` naming the stable workflow (its display name or `cd-release-stable.yml`) is an "ask" run (a proven `RELEASE_ASKED=ASKED:<minute>Z`). With `-f dry_run=true` it is free. That puts the dispatch path under CLAUDE.md's existing rule (C4).

## Boxes

- [ ] S1 [writer] Stable promotion is dispatch-only per D1, and the drift workflow and job are deleted.
  - Owns: .github/workflows/cd-release-stable.yml, .github/workflows/ci-drift.yml (delete), .github/workflows/ci.yml (lines 9-15 comment only), .ci/rediacc_ci/release/check_soak_period.py, .ci/rediacc_ci/release/nightly_tested_edge.py, .ci/rediacc_ci/release/drift_job.py (delete), .ci/rediacc_ci/tests/test_release_check_soak_period.py, .ci/rediacc_ci/tests/test_release_nightly_drift_waiver.py, .ci/rediacc_ci/tests/test_release_nightly_tested_edge.py, .ci/rediacc_ci/tests/test_release_drift_job.py (delete), .ci/rediacc_ci/tests/test_release_drift_job_budget.py (delete)
  - CONTROL: a dispatch with no force and a weekly run that contains the edge commit selects through the weekly waiver; the same dispatch with `NIGHTLY_CONCLUSION=none` falls back to the soak; `dry_run` leaves every write step skipped (a workflow-text test asserts each step after "Check soak period" carries the `dry_run` condition).
  - Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_release_check_soak_period.py .ci/rediacc_ci/tests/test_release_nightly_drift_waiver.py .ci/rediacc_ci/tests/test_release_nightly_tested_edge.py .ci/rediacc_ci/tests/test_security_ci_workflow_invariants.py .ci/rediacc_ci/tests/test_workflow_cd_deploy_account_proxy.py .ci/rediacc_ci/tests/gates/test_gate_gh_retry_shell.py` rc 0, `npm run check:ci-workflows` rc 0, and `git grep -n "CI - Drift\|drift_job\|DRIFT_CONCLUSION" -- .github .ci/rediacc_ci` prints nothing.
- [ ] N1 [writer] Notifications per D2: the status workflow, both reporters and their tests are deleted, the budget-check job reports to its log, the mention lists are emptied, the `drift` ingest age goes, and the label goes from the declaration and the inventory.
  - Owns: .github/workflows/ops-nightly-status.yml (delete), .ci/scripts/ci/report-nightly-status.cjs (delete), scripts/ci/report-budget-check.cjs (delete), .ci/rediacc_ci/tests/gates/test_gate_nightly_status_report.py (delete), .github/workflows/ops-housekeeping.yml (budget-check job only), .ci/config/ci-alerts.json, .ci/config/ops-health.json, .github/labels.yml, .ci/rediacc_ci/quality/label_inventory.py, .ci/rediacc_ci/tests/gates/test_gate_label_inventory.py, .ci/rediacc_ci/tests/test_quality_label_inventory.py, .ci/rediacc_ci/tests/goldens/label-inventory/**, .ci/rediacc_ci/tests/test_ci_publish_verdict.py
  - CONTROL: test_gate_label_inventory keeps a create-on-demand case for `ci` (still in CREATE_ON_DEMAND), so the exemption path stays exercised.
  - Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/gates/test_gate_label_inventory.py .ci/rediacc_ci/tests/test_quality_label_inventory.py .ci/rediacc_ci/tests/test_ci_publish_verdict.py .ci/rediacc_ci/tests/test_ops_health.py` rc 0, `npm run check:ci-workflows` rc 0, `cd workers/ops-health && npx vitest run` rc 0, and `git grep -n "nightly-red\|report-nightly-status\|report-budget-check\|issues: write" -- .github/workflows/ops-housekeeping.yml .github/labels.yml .ci/rediacc_ci/quality` prints nothing.
- [ ] N2 [writer] After N1 lands: the registries, baselines and comments that still name N1's deleted files (C7).
  - Owns: .ci/policy/.profiler-coverage-allowlist, .ci/policy/README.md, .ci/config/prose-style-baseline.json, scripts/data/domain-layout-baseline.json, scripts/data/domains.json, .ci/rediacc_ci/tests/goldens/twins/quality.check-profiler-coverage.jsonl, .ci/rediacc_ci/ci/github_status.py, .ci/scripts/ci/scope-map.cjs, .ci/rediacc_ci/quality/scope_scripts_reachability.py, .github/workflows/ci-quality.yml (lines 2452-2453 comment only)
  - Accept: `npm run check:ci-profiler-coverage && npm run check:ci-prose-style && npm run check:ci-workflows` rc 0, the twins test that reads the golden (found by `git grep -l quality.check-profiler-coverage -- .ci/rediacc_ci/tests`) rc 0, and `git grep -n "ops-nightly-status\|report-nightly-status\|report-budget-check" -- .ci scripts .github` prints nothing outside docs/ci-overhaul.
- [ ] N3 [writer] The d1-size alert issue goes per D2; an alert reds the scheduled run instead.
  - Owns: .ci/rediacc_ci/ops/d1_size_report.py, .ci/rediacc_ci/tests/test_d1_size_report.py, .github/workflows/ops-d1-size-report.yml
  - CONTROL: a report with an alerting region still exits 3, and the workflow step's shell turns that 3 into a failed step (a workflow-text test).
  - Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_d1_size_report.py` rc 0, `npm run check:ci-workflows` rc 0, `git grep -n "alert-issue\|alert_issue\|issues: write" -- .ci/rediacc_ci/ops/d1_size_report.py .github/workflows/ops-d1-size-report.yml` prints nothing.
- [ ] B1 [writer] The daily backup suite workflow is deleted (ruling 2), and the schedule watcher drops its stale rows.
  - Owns: .github/workflows/ct-backup-nightly.yml (delete), .github/workflows/ct-tests.yml (lines 110-114 comment only), .ci/scripts/ci/greenlight.cjs (line 186 comment only), .claude/hooks/stop/wl_schedred.py, .claude/rediacc_hooks/tests/test_wl_schedred.py
  - wl_schedred: the `ci-drift` row of `_BLOCKS` and the nightly-red sentence go. A scheduled run on main whose workflow file has no `schedule:` in the tree is reported as an `undeclared` row, so box L2 can read the absence through the sanctioned verb.
  - CONTROL: a fixture page carrying a scheduled run of a workflow with no schedule in the fixture tree yields one `undeclared` row; the pin test lists exactly the nine kept stems.
  - Accept: `.ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_schedred.py .ci/rediacc_ci/tests/test_ci_trace_scheduled.py` rc 0, `npm run check:ci-workflows` rc 0, `git grep -n "ct-backup-nightly" -- .github .ci .claude` prints nothing.
- [ ] G1 [writer] The issue guard per D3, with its own suite.
  - Owns: .claude/rediacc_hooks/guards/block_issue_create.py (new), .claude/rediacc_hooks/guards/test-block_issue_create.py (new)
  - CONTROL, both directions: each refused shape in D3 is denied, including a submodule `--repo` and an `sh -c` wrap; `gh api repos/o/r/issues/12/comments -f body=x`, `gh issue list`, `gh api repos/o/r/issues` (a GET) and `echo 'gh issue create'` are admitted.
  - Accept: `python3 .claude/rediacc_hooks/guards/test-block_issue_create.py` rc 0 and `.ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_guards_differential.py .claude/rediacc_hooks/tests/test_dispatch.py` rc 0.
- [ ] G2 [writer] A stable dispatch needs a proven ask per D4.
  - Owns: .claude/rediacc_hooks/guards/block_unasked_release.py, .claude/rediacc_hooks/guards/test-block_unasked_release.py
  - CONTROL: `gh workflow run cd-release-stable.yml` and the same with `-f force=true`, or with the workflow's display name, are refused without RELEASE_ASKED; `-f dry_run=true` is admitted; `gh workflow run ci.yml` is untouched.
  - Accept: `python3 .claude/rediacc_hooks/guards/test-block_unasked_release.py` rc 0 and `.ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_guards_differential.py` rc 0.
- [ ] R1 [lead] After S1 and N1 land: drop the lane-durations and shard rows of the five deleted test files (C7), by hand, no regenerate script.
  - Owns: .ci/config/lane-durations.json, .ci/config/shards/quality-pytest.json
  - Accept: `npm run ci -- --narrow` rc 0 on the landed tree and `git grep -n "test_release_drift_job\|test_gate_nightly_status_report" -- .ci/config` prints nothing.
- [ ] D1 [lead] After every writer lands: the docs and CLAUDE.md, then the doc-registry regeneration.
  - Owns: docs/agent-reference/release-process.md, docs/agent-reference/ci-gates.md, CLAUDE.md, scripts/data/doc-registry.md
  - docs/agent-reference/release-process.md:87-95 says dispatch only, with `dry_run`, force and the weekly waiver. docs/agent-reference/ci-gates.md:413-416 says a red weekly run reaches sessions through wl_schedred and the ops-health mail, with no issue, and :437 loses the label exemption. CLAUDE.md:268 loses the Drift waiver clause and names the dispatch path; CLAUDE.md:48-50, :101 and :103 change per Q5.
  - Accept: `npx tsx scripts/gen/gen-docs.ts --write` then `npx tsx scripts/gen/gen-docs.ts` rc 0, `npm run check:ci-doc-region-parity && npm run check:ci-prose-style` rc 0.
- [ ] P1 [lead] The plan corrections of C9: a `(corrected 2026-11-16, ruling ASKED:2026-11-16T09:19Z)` line under PLAN-backup-program J6, PLAN-first-release-checks L5 (both) and PLAN-health-checks-local R3, and the two PLAN-nightly-green corrections handed to its owner through a worklist item.
  - Owns: agent/plans/PLAN-backup-program.md, agent/plans/PLAN-first-release-checks.md, agent/plans/PLAN-health-checks-local.md (correction lines only)
  - Accept: `npm run check:ci-plan-boxes && npm run check:ci-plan-citations && npm run check:ci-plan-live-proof` rc 0.
- [ ] L1 [live] Promote dry run from the pushed branch, with no RELEASE_ASKED (G2 admits a dry run): `gh workflow run cd-release-stable.yml --ref <branch> -f dry_run=true`, then read the run. GitHub-only: CD -- the promotion exists only as cd-release-stable.yml, and `release:local --channel stable` is refused in this tree (C3)
  - Accept: the run's "Check soak period" step prints a selection with `path=` and `ready=`, every later promote step is skipped, and its id and conclusion are in the tick evidence.
- [ ] L2 [live] No removed schedule fires: at least 25 hours after the merge to main, the sanctioned schedule read shows no scheduled run of ci-drift.yml, ct-backup-nightly.yml or cd-release-stable.yml created after the merge, and the kept ones still run. GitHub-only: CI parity -- only GitHub's scheduler on main can show that a schedule stopped firing
  - Accept: `.ci/scripts/ci/ci-trace.py --scheduled --json` lists no `undeclared` row for the three stems (B1), and its rows for ops-housekeeping and ops-pins-soaked carry runs newer than the merge.
- [ ] L3 [live] After N1 lands on main: `gh label delete nightly-red --repo <console repo> --yes`, and every open issue carrying it closed with one comment naming its plan (Q6).
  - Accept: `npm run check:ci-label-inventory` rc 0 against the live repo.
- [ ] L4 [live] Redeploy the ops-health Worker with N1's config (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_ops_health ... --write`, the arguments as PLAN-health-checks-local W4 recorded them).
  - Accept: the deploy rc 0, `npm run check:ci-ops-health` rc 0, and `/v1/status` reports the code sha of the landed tree.
- [ ] L5 [live] Stable also promotes locally (operator ruling 2026-11-16: "also allow release:local for stable"): `RELEASE_ASKED=ASKED:<minute>Z npm run release:local -- --channel stable --dry-run` from the landed tree reads every step, with no daily schedule involved; docs/agent-reference/release-process.md names the local stable path beside the manual workflow.
  - Accept: the dry run rc 0 with its step list in the tick evidence, and `rg -n 'release:local -- --channel stable' docs/agent-reference/release-process.md` finds the documented path.

## Writer split and order
- Wave 1, in parallel: S1, N1, N3, B1, G1, G2 (six groups; at most four at once under `writer_cap`, so G1 and G2 start as the first two slots free).
- Wave 2: N2 after N1 lands; R1 after S1 and N1 land.
- Lead, after every writer lands: D1, then P1.
- Live: L1 once S1 and G2 are pushed; L3 and L4 after N1 is on main; L2 a day after the merge.

## Open questions (each with its default)
- Q1. Does ruling 1's "or `release:local`" lift the 2026-10-27 refusal of `release:local --channel stable` (C3)? DEFAULT: no; promotion is by dispatch only in this plan, and lifting the refusal (local.py, the invariant at .ci/rediacc_ci/security/ci_workflow_invariants.py:724-725, block_unasked_release rule 3) becomes its own plan if the operator confirms.
- Q2. ci-alerts.json and ops-health.json `github_mentions` have no reader once N1 lands. Empty them (the ruling's word) or delete the file and the key? DEFAULT: empty, as ruled.
- Q3. PLAN-nightly-green F2's forecast pass loses its host with drift_job. DEFAULT: F2 retires; the forecast pass is not moved.
- Q4. The weekly run's budget section in report-nightly-status.cjs goes with the file. DEFAULT: accept the loss; the housekeeping budget-check job still checks the same freshness registry daily and reds its run.
- Q5. CLAUDE.md rule 2 calls issues the last resort with three doors (CLAUDE.md:48-50), which G1 now refuses. DEFAULT: reword "last-resort issue" to "last-resort item" (a `[?]` worklist item or an operator ask carrying the same evidence and brief), keeping the three `door:` tick values.
- Q6. Close the open `nightly-red` issues when the label goes? DEFAULT: yes, each with one comment naming the plan that replaced it.
- Q7. The owner of PLAN-nightly-green (session e0f36861) applies its two corrections. DEFAULT: P1 adds them as a worklist item tagged to that session.
