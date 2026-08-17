# RULES: branch 0807-4 (PR #555 — the linear replacement for #553)

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints for this branch. Wrong rule -> edit it here, not below it.
Sharpened from `.agent/0807-2/RULES.md` on 2026-08-08 by session d136ac61.

0807-2's operator mandate carries forward VERBATIM because this branch is the
same work; its writer-ownership table does NOT, because the two writer agents
finished long ago and describing them here would be fiction.

## What this branch is

**The exact content of #553, with linear history.** 17 commits, ZERO merge
commits. Same tree that passed 79 jobs green on #553 at `c60def0d6`, plus a
knip bump.

The operator mandate it carries, unchanged:

> **WE SHOULD ALWAYS HAVE A VERSION! SKIP OR FAIL!**

Every path must end VERIFIED, or in an explicit VISIBLE skip, or in a FAILURE. A
path that cannot determine a version and returns success IS the defect. If a fix
leaves a fourth outcome, it is not done.

## WHY THIS BRANCH EXISTS AT ALL — do not undo this

#553 became unmergeable through no fault of its content, and the chain is worth
knowing before anyone "simplifies" it:

1. `main` moved (#552, #554 landed), so 0807-2 went `DIRTY`.
2. Updating it by REBASE would have required a force-push.
   `block-git-force-push.sh`: *"Rewriting already-pushed history is the user's
   decision, not an agent's."* Categorical. Not negotiable by an agent.
3. So 0807-2 absorbed main via a MERGE commit (a plain fast-forward push).
4. This repo is **rebase-merge only** — verified, not assumed:
   `allow_merge_commit=false allow_squash_merge=false allow_rebase_merge=true`.
   GitHub then refused: `This branch can't be rebased`.
5. The base-flip workaround failed too: 0807-1 had been deleted on merge, so
   there was nothing to flip to.

The rebase performed in step 2's place was PRESERVED as local branch
`rebased-0807-2-keep` and pushed here as 0807-4. That is why this branch is
linear and mergeable while #553 is not.

## Do not re-litigate

- **Both waves' gate registrations must survive.** The 0807-1 wave and this one
  BOTH add manifest entries and workflow steps. Every conflict in
  `scripts/ci-runner/manifest.ts`, `ci-quality.yml` and
  `docs/ci-overhaul/06-progress.md` was resolved by KEEPING BOTH SIDES. Dropping
  either silently unwires gates. 200 manifest gates; six spot-checked by name.
- **Submodule pointers are final**: `account e75e295a9`, `renet 325905214`.
  Each moved only after confirming an EMPTY tree diff against the old branch tip
  (rebase-merge preserves content and changes only SHAs).
- renet **#99 was CLOSED, not merged** — a duplicate of #100 whose `go.mod`/
  `go.sum` blobs are byte-identical to what #100 landed. Do not reopen it.
- `compareVersions` does NOT return 0 for an empty string (`Number('')` is 0).
  The silent-equal case is NON-NUMERIC segments producing NaN. Any fix targets
  NaN, not emptiness.
- The review cap on #553/#555 is spent by STARVED attempts, not posted reports.
  `Review Complete` passes via the DEADLOCK GUARD that #554 put on main. That is
  designed machinery, not a bypass.

## Standing constraints

- **AUTOPILOT is active** (operator asleep, invoked `/pr-merge`). Landing PRs is
  authorised. `--admin` and force-push are NOT, and both are hook-blocked. If
  something cannot merge legitimately, **STOP AND REPORT** rather than force it.
- Never push `main` directly. Never suppress a gate.
- Never `git checkout/restore/stash/clean` to undo a mistake. Repair forward.
- Never `git add -A`. Stage by explicit path. NEVER stage
  `.claude/settings.local.json`, `private/generative`, or `private/growth`.
- A blocked PreToolUse hook aborts the ENTIRE compound command — nothing in it
  ran. Do not assume an earlier step in the same call happened.
- PRs on `rediacc/console` MUST be created `--draft`, then flipped with
  `gh pr ready` once `CI Complete` is green; that flip triggers the review.
- **Answer the top-level review SUMMARY, not just the inline threads.** A summary
  has no thread to resolve, and `review-findings: []` does NOT exempt it. Missing
  this cost three separate rounds and one force-cancelled run in this wave.
- Dependency bumps: NEVER `check:deps --upgrade` (it has bumped a submodule's
  deps and rewritten the lockfile under npm 11). Edit the single pin, then
  `npx -y npm@10 install --package-lock-only --ignore-scripts`.
- shfmt is `-i 4 -ci`. `mapfile` is BANNED. ruff reads the GIT mode, so a
  shebanged `.py` needs `git update-index --chmod=+x`.
- No attribution trailers in commits; no backticks in `git commit -m`; amending
  is hook-blocked — make a NEW commit.
