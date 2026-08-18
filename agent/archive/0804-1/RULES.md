# RULES: branch 0804-1 (licensing big-bang PR wave)

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints for this branch. Wrong rule → edit it here, not below it.
Sharpened from `.agent/main/RULES.md` on 2026-08-04 by session d136ac61;
the CI-overhaul-specific do-not-relitigate items live on in `.agent/main/`.

## What this branch is

The PR wave landing the ENTIRE licensing campaign tree (fork metering via
datastore-scoped license store, auth-by-blob renewal + soft-claim, 4-part
chain scope, drills harness, i18n gate rebuild, stop-hook fixes, knowledge
agents). Immutable briefing:
`~/.claude/projects/-home-muhammed-monorepo-console/reports/pr-babysit-0804-1-briefing.md`.
Campaign report: `agent/REPORT-licensing-bigbang-2026-08-04.md`.

## Roles (two live writers + a lead share this tree)

- `babysit-0804-1` (Opus teammate) OWNS git state: snapshots, commits, PRs,
  CI rounds. Round log: `~/.claude/.../reports/pr-babysit-0804-1.md`.
- `fix-legs-bf` (Opus teammate) edits its named 16-file datastore-sweep set
  + datastore.ts lastHolder ferry; NEVER touches git. Its paths are
  DO-NOT-STAGE until the lead's explicit absorb message.
- Lead (session d136ac61) rules on escalations via SendMessage; its own
  tree edits are declared to the babysitter before/at commit time.

## Do not re-litigate

- Delegate-by-default /pr-babysit, SendMessage reporting: operator directive
  2026-08-04.
- Datastore-scoped license store, 4-part chain key, IsLicensedOperation
  deletion, commit→Create tier: campaign decisions, drill-proven 39/39
  (full16/full17 logs in the session scratchpad).
- `repo migrate` OUT of a named datastore re-meters BY DESIGN; identity
  travel is a DATASTORE move (`datastore attach --to`). Leg b tests that.
- detach→adopt→attach ordering with adopt FIRST (non-destructive before
  destructive) — renet adopt.go:22-28 states the rule.

## Standing constraints

- Never push `main`, never merge, never force-push, never suppress a gate.
- Never `git checkout/restore/stash/clean`. Repair forward. Shared tree.
- NEVER stage: `private/renet/pkg/infra/docker/{service.go,pull_retry*_test.go}`
  (another session's live work), `.claude/settings.local.json`,
  `private/generative`, `private/growth` (non-submodule repos).
- Media check before commit: staged `.mp4/.mp3/...` count must be 0.
- Ops VMs + dev gateway belong to fix-legs-bf until its final drill rerun.
- No attribution trailers in commits; no backticks in `git commit -m`.
- Rebase-merge only, all repos; `git branch --merged` lies here.
- package-lock churn: reconcile with `npx -y npm@10 install
  --package-lock-only --ignore-scripts` (console AND private/account).
- New CI legs `test-drills` + suite 24 ACCOUNT tier: FIRST exercise this
  push; red there = check wiring first, never disable the leaf.
