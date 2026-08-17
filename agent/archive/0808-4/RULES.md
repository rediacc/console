# RULES: branch 0808-4 (0808-3 cherry-picked onto post-release main; #558→#559) (Stop-hook task visibility + run-all parallelization)

**SHARPEN THIS FILE. Do not append to it.** Sharpened from `.agent/0808-2/RULES.md`
on 2026-08-08 by session d136ac61. 0808-2's branch-specific content (the gate-id
convention narrative) is MERGED (#557 + the big-bang riders) and did not carry.

## What this branch is

Two disjoint local workstreams, committed but NOT pushed until the operator says:
1. **Stop-hook task visibility** (session-owned files, `.claude/hooks/stop/`):
   `_resolve_tasks_dir` transcript-content join (the task store moved to
   `session-<team-id>` while Stop events carry the conversation id; an EMPTY
   primary dir is "no evidence", not an answer — a July relic dir shadowed the
   real store), `actionable_tasks()`, and the `V_BG_REPORT_TASKS` check-in that
   names unblocked pending tasks during background waits. Harness: case 163
   premise moved to in_progress; NEW case pair 163y (fire + blocked-control).
2. **run-all.sh in-step parallelization** (Opus agent `impl-runall-parallel`
   owns `.ci/scripts/test/run-all.sh`, `test-run-all-parallel.sh`, manifest row):
   W/S/T schedule — the 5 battery flakes were real-tree WRITERS (gate-paths-exist,
   gate-anti-vacuity write into `.ci/scripts` and `scripts/`) racing ~15 real-tree
   scanners, NOT concurrency pressure. 18min serial → ~5.5min target.

## Do not re-litigate

- The transcript join REFUSES on ambiguity (0 or 2+ candidate dirs → None):
  "missing dir = no evidence" is also the no-manufactured-blocks safety, and a
  guessed dir would supervise another session's queue.
- An unblocked pending task during a wait is a CLAIM that nothing stops you —
  the check-in names it; the honest silencer is TaskUpdate addBlockedBy.
- W/S/T: bias closure-too-wide; a wrong parallel schedule must show as RED
  (missing .rc = failure, never a skip).

## Context (merged, do not redo)

console main carries: #552 #554 #555 #556 #557 (big-bang: gate-id convention,
auto-labels + dead detect-bump-type rewrite, 18-key greenlight, renet pointer
to e48cc4ae6 = #101 overlayfs + #102 baseline). v1.2.20 released. E2E-skip
proven live (all 18 keys, 39 jobs skipped). renet+account now hold repo-level
CLAUDE_CODE_OAUTH_TOKEN (first green submodule reviews since ~0730).

## Standing constraints (unchanged from 0808-2, still load-bearing)

- Landing PRs needs the operator; commit local, PUSH ONLY WHEN ASKED (explicit
  for this branch: "You can commit but later push it").
- Never git checkout/restore/stash/clean to undo; repair forward. Never
  `git add -A`; never stage `.claude/settings.local.json`, `private/generative`,
  `private/growth`.
- Answer review REPORTS and summaries, not just threads — now hook-enforced on
  BOTH console (Review Gate) and submodules (block-admin-merge).
- Review budget: a zero-output attempt SPENDS a pass (bot-actor refusals
  included — recorded defect); "push to earn another pass" is WRONG about the
  accounting; at cap the deadlock guard passes loudly.
- A GitHub update-branch rebase poisons the workflow_run actor chain (bot
  actor → review refuses); the workflow_dispatch path is the escape.
- per_page=100; job counts not run status; reviews by --workflow never
  --branch; no em dashes; shfmt -i 4 -ci; mapfile banned; amend hook-blocked.
