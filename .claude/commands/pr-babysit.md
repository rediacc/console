---
description: Start the PR loop for the landing PR, in this session or as a background pr-babysitter teammate (`bg` first). Every rule of the loop is in .claude/agents/pr-babysitter.md.
argument-hint: "[bg] [short summary of the change to seed intent/PR titles]"
# Model-invocable, as every command is (operator ruling 2026-10-09: no command or skill is
# user-only; a hook and check:ci-model-invocable-commands refuse the flag), and the per-PR
# loop's own entry point since the operator ruling of 2026-10-02 (PLAN-plan-per-pr-loop M1):
# the AI starts it without being asked.
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git submodule status:*), Bash(gh pr list:*), Bash(date:*), Bash(./run.sh worktree landing --status)
---

## Current state

- Today (branch base): !`date +%m%d`
- Development tree branch (this checkout): !`git branch --show-current`
- Landing tree branch: !`./run.sh worktree landing --status`
- Live local branches besides `main`: !`git branch --format='%(refname:short)' | grep -vx main | tr '\n' ' '; echo`
- Console tree (excl. settings.local.json): !`git status --short | grep -v '.claude/settings.local.json' | wc -l | tr -d ' '` changed path(s)
- Submodules with changes: !`git status --short private/renet private/account private/elite private/homebrew-tap 2>/dev/null || echo '(none)'`
- Existing date branches (console remote): !`git branch -r | grep "$(date +%m%d)-" || echo '(none yet)'`
- Date names ALREADY CONSUMED (PR heads, merged included): !`gh pr list --state all --limit 100 --json headRefName --jq '.[].headRefName' 2>/dev/null | grep "^$(date +%m%d)-" | sort -u | tr '\n' ' ' || echo '(none yet)'`
- Open PRs on the current branch: !`cb="$(git branch --show-current)"; for r in console renet account; do p=$(gh pr list --repo rediacc/$r --head "$cb" --state open --json number,title --jq '.[] | "  rediacc/'$r' #\(.number) \(.title)"' 2>/dev/null); [ -n "$p" ] && echo "$p"; done; true`

## Mode

- The first whitespace-delimited token of `$ARGUMENTS` exactly `bg` selects delegate mode; anything else, no arguments included, selects inline mode.
- The rest of `$ARGUMENTS` seeds the intent summary.

## Start

The session reads `.claude/agents/pr-babysitter.md` in full and runs it: as the babysitter in inline mode (section *Modes*), or as the lead in delegate mode (section *Delegate mode: the lead's side*).
