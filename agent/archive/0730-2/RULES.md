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
- Sweep and push the whole tree every round; `git add -A` is correct here. Check
  `git diff --cached --name-only | grep -cE '\.(mp4|mp3|webm|jpg|png)$'` is 0
  first: `packages/www/public/assets/videos` is 5.0 GB and belongs in R2.
- Never stage the `private/renet` gitlink when it points off main.
- `docs/ci-overhaul/06-progress.md` is the program's running record and must be
  updated in the same turn behaviour changes.

## Not ours

`check:ci-tutorial-caption-sync` is red and belongs to another agent. It fetches
PUBLISHED `words.json` from `media.rediacc.com`, not this tree. A mass failure
right after a publish is a stale CDN cache; Estonian is permanently exempt.
