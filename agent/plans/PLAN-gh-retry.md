# PLAN: GitHub reads survive one 5xx: every CI, release and gate read goes through core/gh_retry

Status: approved -- 2026-10-06: #5d8cfea6 asked where it ships; #597 merged before an answer, so its default runs: the next branch (1006-3), first in QUEUE.md Promoted. Found on PR #597 (run 37507913738: one HTTP 502 failed CI Complete).
Owner: d778be9d
First-Seen: 2026-10-06
Depends-On: no-dep -- builds on core/gh_retry (f09fca116) and the scope_reconcile_shadow fix (f86f2e5ed)
Priority: P1 -- three release-path reads are silently wrong on a single 5xx (wrong build, wrong bump, wrong skip)
Concurrency: parallel -- one module per box; writers own disjoint files
Owns: .ci/rediacc_ci/release/resolve_ci_run.py, .ci/rediacc_ci/version/detect_bump_type.py, .ci/rediacc_ci/ci/dispatch_release.py, .ci/rediacc_ci/release/assert_artifact_version.py, .ci/rediacc_ci/release/assert_edge_tag_exists.py, .ci/rediacc_ci/ci/dispatch_watchdog.py, .ci/rediacc_ci/ci/check_rerun_attempt.py, .ci/rediacc_ci/quality/pr_description.py, .ci/rediacc_ci/quality/label_inventory.py, .ci/rediacc_ci/security/audit.py, .ci/rediacc_ci/docker/cleanup_staging.py, .ci/rediacc_ci/ci/detect_pointer_bump.py, .ci/rediacc_ci/ci/cancel_older_runs.py, .ci/rediacc_ci/ci/ci_diagnose.py, .ci/scripts/ci/ci-trace.py, .ci/rediacc_ci/core/gh_retry.py, .ci/rediacc_ci/tests/**
Worklist: #5d8cfea6

## Why

`core/gh_retry` is the repo's policy for GitHub reads: retry only a transient fault (5xx, connection, timeout), 3 attempts, 5 s then 15 s; a 4xx fails at once. A read-only audit on 2026-10-06 found 20 modules calling `gh` through `subprocess` without it (search: `grep -rln '"gh",\s*$\|\["gh", "api"\|\["gh", "run"' .ci/rediacc_ci`, tests excluded: 26 modules, 20 without gh_retry or ghx), plus ci-trace's `_run_snapshot`. A single 5xx today:
- silently releases the wrong thing: resolve_ci_run (skips a staged run, falls back to GITHUB_SHA), detect_bump_type (a major/minor label read as patch), dispatch_release (releases a skip-labelled PR, withholds a stable label);
- blocks a release or promotion with a misleading message: assert_artifact_version ("artifact not found"), assert_edge_tag_exists;
- fails a CI job or gate: dispatch_watchdog reads, check_rerun_attempt, pr_description, label_inventory, security/audit;
- costs or leaks: cleanup_staging list read, detect_pointer_bump (full CI instead of the fast path), cancel_older_runs first read;
- degrades agent tooling: ci_diagnose.GhFetcher, ci-trace `_run_snapshot`.

Not retried, by design: create_github_release (a retry after a lost response fails "already exists"), the `gh workflow run` dispatches (a duplicate run), the cancel and rerun POSTs.

## Tasks

- [x] G0 gh_retry.gh gains the knobs the call sites need: `timeout` (default ghx's 30 s; an artifact download needs more), `cwd` (for `{owner}/{repo}` placeholders), and an `attempts`/delay bound the Stop hook's 20 s budget can use. Unit tests for each.
    (ticked) 2026-10-06T22:15:05Z by d778be9d: commit:463c2d053 gh_retry.gh passes repo and timeout through to ghx.gh; 16 tests pass
- [x] G1 release/resolve_ci_run.py: every read through gh_retry; a read that still fails after retries refuses loudly instead of falling back (no GITHUB_SHA fallback, no skipped staged run). Gate test updated to the new seam.
    (ticked) 2026-10-06T22:15:07Z by d778be9d: commit:f9be54788 every read through gh_retry; a retried-out fault refuses, no GITHUB_SHA fallback; 132 tests
- [x] G2 version/detect_bump_type.py: per-commit label reads through gh_retry; an unreadable commit after retries fails the release decision instead of being skipped. Gate test updated.
    (ticked) 2026-10-06T22:15:08Z by d778be9d: commit:f9be54788 per-commit label reads through gh_retry; a retried-out 5xx fails the bump decision; 132 tests
- [x] G3 ci/dispatch_release.py: the PR lookup through gh_retry; an unreadable PR after retries refuses instead of releasing on an empty label set. The dispatch itself stays one-shot.
    (ticked) 2026-10-06T22:15:09Z by d778be9d: commit:f9be54788 PR lookup through gh_retry; a retried-out 5xx refuses; dispatch stays one-shot; 132 tests
- [x] G4 release/assert_artifact_version.py and release/assert_edge_tag_exists.py: reads through gh_retry; the artifact message tells a 5xx apart from a missing artifact.
    (ticked) 2026-10-06T22:15:11Z by d778be9d: commit:c5b8c3d95 download through gh_retry with a 300 s timeout, outage told apart from a missing artifact; edge-tag probes through gh_retry; 315 tests
- [x] G5 ci/dispatch_watchdog.py reads and ci/check_rerun_attempt.py through gh_retry; the `gh workflow run` stays one-shot.
    (ticked) 2026-10-06T22:15:12Z by d778be9d: commit:c5b8c3d95 watchdog reads and run_attempt read through gh_retry, dispatch one-shot, group closed on failure; 315 tests
- [x] G6 quality/pr_description.py, quality/label_inventory.py, security/audit.py reads through gh_retry.
    (ticked) 2026-10-06T22:15:13Z by d778be9d: commit:81078dffc three gates' reads through gh_retry, failures name gh's stderr; 294 tests
- [x] G7 docker/cleanup_staging.py list read, ci/detect_pointer_bump.py, ci/cancel_older_runs.py first read through gh_retry.
    (ticked) 2026-10-06T22:15:15Z by d778be9d: commit:81078dffc three cost-only reads through gh_retry (+4b93aef4f review guard); 294 tests
- [x] G8 ci_diagnose.GhFetcher and ci-trace `_run_snapshot` retry transient faults within a bound that fits the Stop hook's timeout.
    (ticked) 2026-10-06T22:15:16Z by d778be9d: commit:fd52f68e5 GhFetcher and _run_snapshot retry transient faults, Stop hook bounded to 2 attempts and a 2 s pause; 198 tests
- [x] G9 A regression gate: a check that every non-test `gh` subprocess read under .ci/rediacc_ci goes through gh_retry or ghx, with the write sites above listed by name and reason; planted control first.
    (ticked) 2026-10-06T22:15:17Z by d778be9d: commit:b26c8d3e1 check:ci-gh-retry-reads: AST scan, 0 new one-shot reads, 86 baselined shrink-only, planted defect proven; wiring gates rc 0
- [x] G10 housekeeping/cleanup_versions.py (lines 1955, 2071, 2184, 2428) and .ci/rediacc_ci/housekeeping/cleanup_pr_environments.py:169: an unreadable PR state skips the delete instead of reading as "not open"; reads through gh_retry. Found by the G9 gate: one 5xx can delete a still-open PR's environment, D1 database, Turnstile widget or R2 prefix. P1, first.
    (ticked) 2026-10-06T22:15:19Z by d778be9d: commit:3720c3637 unreadable PR state keeps the resource at every site incl. Phase 9; 187 tests
- [ ] G11 scope_reconcile_shadow.download_plan and ops/derive_shadow_pass_list reads through gh_retry (the first still retries once with no pause; the second can print a `gh secret delete` for a secret that never matched).
- [ ] G12 Drain gh-retry-reads-baseline.json module by module: the release path first (mark_production, verify_release_assets, check_existing_release, list_edge_releases, nightly_tested_edge.fetch_run_jobs), then the review path (claude_review_gate, review_status, pr_labels, review_table), then the quality checks (commit_identity, claude_attribution, submodule_branches) and the rest; `--write-baseline` after each drained module.

