> **BOOTSTRAPPED, NOT YET SHARPENED.** Copied verbatim from `.agent/0730-2/RULES.md`
> on 2026-07-30 by session 84611aab, because the Stop hook needed a `.agent/main/`
> to exist. Most of what follows is CI-overhaul context owned by session b9491d9c
> and scoped to branch 0730-2; I did not rewrite their rules for a branch neither of
> us is on yet. Whoever first does real work on `main` should sharpen this and delete
> this banner. Treat every rule below as "true on 0730-2, unverified on main".

# RULES: branch 0730-2

**SHARPEN THIS FILE. Do not append to it.** These are settled facts and standing
constraints. They change rarely, so they must not be re-typed into `STATE.md` on
every rewrite -- that habit is what made the old handover spend 40% of its budget
restating things that had not changed all day.

Not freshness-gated. A rule cannot go stale by the clock, only by being wrong.
When one turns out to be wrong, EDIT IT HERE rather than adding a correction
below it.

## Do not re-litigate

- The **skip-plan reconciler already exists** (`af53749c2`, wired at
  `ci.yml:1253`) and meets its D-1 bar. Never rebuild it. A session was briefed
  to build it and found it already there.
- The **D5 tag split already exists** (`initialize.sh:159-160` computes separate
  `--closure web` and `--closure rdc` tags), despite `05-execution-guide.md`
  still describing `RDC_TAG="$WEB_TAG"`. The plan is stale here, not the code.
- **Spikes S-1 and S-2 are settled**, evidence in `docs/ci-overhaul/spike-s1-s2.md`.
  `--model claude-sonnet-5` IS honoured, so #539 is cosmetic. `--max-budget-usd`
  DOES bind under OAuth, but as a between-turns post-hoc stop, not a ceiling: a
  $0.01 cap was measured spending $0.234. Say a dollar stop exists; never say a
  hard cap does.
- The **rediacc-autopilot App exists and is validated** (app_id 4409539,
  installation 149445627, no bypass, no administration, no workflows).
- **Wave C landed with every stage flag off** and is NOT gated on Wave B.
  Landing and enabling are different events.

## Operator decisions in force

- **D-1: the scope engine STAYS IN SHADOW** until `pointer_bump_only` is
  observed true. Do not flip the gate live.
- The **retry allowlist OVERRIDES a confident code-change verdict** for
  provisioning legs, `guardForced` excepted. This deliberately re-opens part of
  #537; `MAX_ATTEMPTS` bounds it to one extra attempt.
- **A spent review attempt consumes budget.** A pass that produced nothing is
  charged, under its own prefix so it can never suppress a real review.
- The docker cache-key defect **folds into the D5 tag work**, not a separate fix.
- **Rebase-merge only** across all five repos.

## Standing constraints

- Never push `main`, never merge, never force-push, never suppress a gate.
- Never `git checkout/restore/stash/clean` to undo. Repair forward. The tree is
  shared and other sessions write into it continuously.
- Before staging, check `git diff --cached --name-only | grep -cE
  '\.(mp4|mp3|webm|jpg|png)$'` is 0: `packages/www/public/assets/videos` is 5.0 GB
  and belongs in R2. (This line used to open with "`git add -A` is correct here",
  which contradicted both `block-blanket-git-add.sh` and this file's own rule
  below. A rules file that answers one question twice, differently, is worse than
  one that stays quiet: the reader stops at whichever comes first.)
- Never stage the `private/renet` gitlink when it points off main.
- `docs/ci-overhaul/06-progress.md` is the program's running record and must be
  updated in the same turn behaviour changes.

## Not ours

`check:ci-tutorial-caption-sync` is red and belongs to another agent. It fetches
PUBLISHED `words.json` from `media.rediacc.com`, not this tree. A mass failure
right after a publish is a stale CDN cache; Estonian is permanently exempt.

## The operator's WIP is in this tree ON MAIN. Do not commit it, do not discard it.

Stated by the operator on 2026-08-17 during the `/pr-merge` of `0815-1`:
*"there are my local changes. do not commit or do not discard any of them. WIP"*.
Carried here from `agent/0815-1/RULES.md` on 2026-08-18 because RULES.md is
PER BRANCH: the constraint was written while `0815-1` was checked out, that
branch is now merged and its remote ref deleted, and the dirty files came with
the checkout. A session reading only this file would not have seen it.

At the time of writing that meant four modified tracked files
(`.claude/agents/i18n-guardian.md`, `.claude/commands/handoff.md`,
`.claude/commands/pr-merge.md`, and a session STATE.md) plus untracked
`agent/programs/www-simplification/` (the research corpus moved there from
`docs/www-simplification/` on 2026-08-18, so lifetime matches location), and two new
`.claude/agents/*.md`. The set WILL drift -- re-read `git status`, do not trust
this list.

THE TREE IS PARKED ON `main`, which makes this sharper rather than softer: those
files cannot be committed here at all. The next task starts with a fresh
`MMDD-N` branch BEFORE any tracked file is edited.

- Never `git add -A`, never stage a bare directory. Name every path.
- Never `git checkout`, `restore`, `stash` or `clean` a path you did not create.
  To change branches while keeping such files, back them up, `checkout -f`, then
  restore and verify byte-identity by hash. That is what was done here.
- Re-read `git diff --cached` immediately BEFORE every commit. The index is what
  gets committed, not the paths named on the command line.
