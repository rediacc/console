# RULES: branch 0807-1 (post-release hygiene)

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints for this branch. Wrong rule -> edit it here, not below it.
Sharpened from `.agent/0804-1/RULES.md` on 2026-08-07 by session d136ac61.
Most of 0804-1's content did NOT copy forward: the two writer teammates, the
briefing, the ops-VM ownership and the licensing do-not-relitigate list all
died with that wave when it shipped as v1.2.16.

## What this branch is

Cleanup that fell out of shipping wave 0804-1, cut AFTER the release so it
could not race the deploy. Three commits, no PR yet, nothing pushed:

- a CI job timeout-headroom gate (`check:ci-timeout-headroom`) plus a
  45-minute ceiling for `Stage Artifacts`, which had none anywhere
- the js-yaml HIGH advisory: 4.x fixed by override, 3.x allowlisted with a
  verified BLOCKER

Based on `origin/main` at 9290c6d45, the released tree. It was rebased there
deliberately: cut from the older 4965ddce4 it recorded a stale
`private/homebrew-tap` pointer and showed permanently dirty.

## Do not re-litigate

- `timeout-minutes: 60` on validate-promote. Measured: that job took 31m54s on
  the run that shipped v1.2.16, past the old 30m ceiling. 60 is HEADROOM, not
  a fix. Promotion is O(channel size) and still trending up; if it passes 60,
  make the copy incremental, do NOT raise the number a second time.
- The js-yaml 3.x allowlist entry (id 1138114). No patched 3.x exists, and
  gray-matter@4.0.3 binds `safeLoad`/`safeDump`, which js-yaml 4 removed. Its
  reachability was checked, not assumed: build-time only, `output: 'static'`.
- astro and sharp advisories are WARNINGS deferred in `.deps-upgrade-blocklist`
  with their own reasons. Not this branch's problem, and not what was red.

## Standing constraints

- Never push `main`, never merge, never force-push, never suppress a gate.
- Never `git checkout/restore/stash/clean`. Repair forward. Shared tree.
- NEVER stage `.claude/settings.local.json`, `private/generative`,
  `private/growth` (non-submodule repos), or a submodule pointer that merely
  drifted. Decide by which commit is NEWER, never by whose work it looks like.
- No attribution trailers in commits; no backticks in `git commit -m`.
  Amending is hook-blocked; make a NEW commit instead.
- Rebase-merge only, all repos; `git branch --merged` lies here. GitHub REFUSES
  rebase-and-merge above 100 commits, so keep waves under it or a merge commit
  becomes the only way in (that is why #551 and #543 both carry one).
- package-lock churn: reconcile with `npx -y npm@10 install
  --package-lock-only --ignore-scripts`. npm 11 rewrites it cosmetically.
- Round-tripping JSON in python: pass `ensure_ascii=False`, or json.dumps
  escapes every non-ASCII character in the whole file. It did, in package.json,
  and it landed in two BLOCKER strings I never meant to touch.
