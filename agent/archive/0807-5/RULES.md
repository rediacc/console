# RULES: branch 0807-5 (PR pending — the edge smoke-test retry + its PR gate)

**SHARPEN THIS FILE. Do not append to it.** Settled facts and standing
constraints for this branch. Wrong rule -> edit it here, not below it.
Sharpened from `.agent/0807-4/RULES.md` on 2026-08-08 by session d136ac61.

**Almost nothing carried forward, deliberately.** 0807-4 was the 3400-line
version-hole wave with an exhausted review cap, a superseded predecessor, and a
merge-commit problem. This branch is FOUR FILES cut fresh off `main` AFTER that
wave landed. Copying 0807-4's rules here would describe constraints that no
longer apply — its "do not revive #553", its cap-exhaustion note, its
keep-both-waves conflict rule are all history now. What DID carry: the standing
constraints at the bottom, which are the session's, not the branch's.

## What this branch is

One commit fixing a real release-path defect, plus the gate that catches its
class on a PR:

- `.ci/scripts/deploy/verify-edge-endpoints.sh` — the four load-bearing
  assertions now run through a new `fetch_retry`.
- `.ci/scripts/test/gates/test-edge-verify-retries.sh` — new, control-first.
- `package.json` + `scripts/ci-runner/manifest.ts` — wiring.

## The incident it fixes, and the reasoning error worth not repeating

Release run **31234422166** deployed edge successfully, then failed
`edge.rediacc.com footer does not render v1.2.19` — while edge was ALREADY
serving v1.2.19 (verified live afterwards). One `curl` against an
eventually-consistent CDN, moments after deploy, no retry. The script had TWELVE
such reads and zero retries.

The cascade is the expensive part: the failure skipped `Tag & GitHub Release`, so
a good release shipped with **no v1.2.19 git tag and no GitHub Release**.

**THE REASONING ERROR.** I first concluded this was main-only and therefore
un-catchable on a PR, because `verify-edge-endpoints.sh` runs only from
`cd-v2.yml` (dispatch-only, main-only). The premise is true; the conclusion was
wrong. The defect was never "edge served the wrong version" — edge was correct.
It was "the assertion samples once", which is a property of a SHELL SCRIPT and can
be driven against a fake predicate on any PR with no deploy at all. The operator
caught this by asking "can't we catch the error on PR time?".

Generalise it: before calling something un-testable on a PR, separate the
ENVIRONMENT you cannot reproduce from the LOGIC you can.

## Do not re-litigate

- **Not `curl --retry`.** That retries transport errors. These failures are
  200-OK-but-STALE, which `--retry` cannot see. The predicate must re-fetch AND
  re-match; that is why `fetch_retry` takes a predicate rather than a URL.
- **The "never agrees is still REJECTED" case is load-bearing.** Without it the
  cheap way to make this gate green forever is a retry that accepts anything
  eventually — worse than no check.
- The release for `1ebd8aff4` is INCOMPLETE, not broken: edge is deployed and
  serving correctly, but v1.2.19 was never tagged and no GitHub Release exists.
  **Re-cutting a release is the OPERATOR's call** (`/pr-merge` step 5 says so
  explicitly); do not dispatch one.

## Standing constraints

- **AUTOPILOT is active** (operator asleep, invoked `/pr-merge`). Landing PRs is
  authorised. `--admin` and force-push are NOT, and both are hook-blocked. If
  something cannot merge legitimately, **STOP AND REPORT**.
- Never push `main` directly. The ONE exception is /pr-merge step 5: a main-only
  failure in the release path of a merge this command performed. Even then, keep
  it surgical and say so loudly.
- Never `git checkout/restore/stash/clean` to undo a mistake. Repair forward.
- Never `git add -A`. Stage by explicit path. NEVER stage
  `.claude/settings.local.json`, `private/generative`, or `private/growth`.
  NOTE: `git stash list` shows two stashes belonging to OTHER sessions
  (`security-hardening-console-resolved`, `blocker-gate-extensions-wip`) —
  leave them completely alone.
- A blocked PreToolUse hook aborts the ENTIRE compound command — nothing in it
  ran. Do not assume an earlier step in the same call happened.
- PRs on `rediacc/console` MUST be created `--draft`, then flipped with
  `gh pr ready` once `CI Complete` is green; that flip triggers the review.
- **Answer the top-level review SUMMARY, not just the inline threads.** A summary
  has no thread to resolve and `review-findings: []` does NOT exempt it. Missing
  this cost three rounds and one force-cancelled run in this wave.
- Dependency bumps: NEVER `check:deps --upgrade`. Edit the single pin, then
  `npx -y npm@10 install --package-lock-only --ignore-scripts`.
- Verify gate reachability by RUNNING it through the runner
  (`npx tsx scripts/ci-runner/run.ts --only <key>`), never by reading
  `gate: true` off the manifest.
- shfmt is `-i 4 -ci`. `mapfile` is BANNED. ruff reads the GIT mode, so a
  shebanged `.py` needs `git update-index --chmod=+x`.
- No attribution trailers in commits; no backticks in `git commit -m`; amending
  is hook-blocked — make a NEW commit.
