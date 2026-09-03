## SESSION 74de73ca 2026-09-03T02:26:32Z

## Operator away; autonomous work authorized. Do NOT ask.

Park a real operator decision as [?] with a DEFAULT and keep working.

## Where the work is

Branch `0903-1` in console and all three submodules. PRs: console **#585** (draft),
account **#85**, renet **#110**, elite **#16**. Epic 24c98380; `PR-TASK: 24c98380` on
every commit. Heads: console `00215294e`, account `6e35d26`, renet `870205b`,
elite `f253283`. **`npm run ci:quick` is 291/291**, `.ci/config/carried-reds.json` is
EMPTY, everything is pushed. Tree clean apart from `packages/www/package.json` (a peer's
sitemap bump -- theirs, leave it).

Watching: cron 7d947ca1 at :09/:54, and a wl_wait mail waiter (bwpc336ef). The waiter
fires ONCE -- relaunch it in the same turn you act on it, as a harness background task,
never with a shell `&`. The PR-checks monitor has expired; re-arm if you want events.

## THE ONE THING THAT NEEDS THE OPERATOR -- and it is the only open item

Run 33691632299, "Tests + Infra / Account E2E", compare step: six names matched but
**ACCOUNT_SERVER_API_KEY and STRIPE_SANDBOX_WEBHOOK_SECRET came back MISMATCH** --
GitHub and Bitwarden hold different VALUES. A THIRD followed in run 33704079162 (the
watchdog): **ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN**. Worth checking before re-seeding: GitHub
calls that one `CLAUDE_CODE_OAUTH_TOKEN` while the shadow name carries the `ANTHROPIC_`
prefix, so a rotation applied to one name would never have reached the other. Deleting the org secrets would destroy the
live value of both, and no session can reconcile them: GitHub secrets are write-only.
Parked as [?] #fbd35dba, DEFAULT "delete no org secret". Nothing is deleted until those
two are re-seeded in ci-shared and every compare step says match.

## Landed 2026-09-03 02:00-03:30Z (this block is newest; read it first)

Four commits on `0903-1`, all `PR-TASK: 24c98380`, all pushed, ci:quick 291/291.

**`7a7ccd1d6` check:ci-syncpack-sources.** The gate for the submodule-outside-the-pins
fix below. Every tracked package.json that declares dependencies must be matched by a
`source` glob or excluded in `.ci/config/syncpack-source-exclusions.json` with a BLOCKER
reason (8 are, on purpose). Proven by removing private/account from `source`: exit 1,
naming it. **Its message describes a check_b fix it does not contain** -- see the trap
below; the code landed in `9b9746955`.

**`9b9746955` the shadow was switching off the guards it ran in front of.** The compare
step sat near the top of all 62 jobs and exits 1 on mismatch, so a finding stopped that
job's work. In the watchdog it aborted the job before the monitor ever ran: run
33704079162 said "failure" having monitored NOTHING. Fixed three ways -- an
expected-mismatch ledger (`.ci/config/shadow-expected-mismatches.json`, 3 entries, each
with its run and `door:operator-only`) that lets 9 blocked jobs proceed while still
REPORTING; the watchdog's shadow moved last with `always()`; and two gates so it cannot
rot (`gate-test:shadow-compare` drives the REAL body extracted from ci.yml through all
six paths, `check_bws_map` assertion 12 ties ledger and workflows both directions).
**Verified in a live run**: 33705949777 shows `Monitor jobs and cancel on failure`
success, then `shadow ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN MISMATCH (EXPECTED)`. An
UNEXCUSED mismatch still fails; an EMPTY stays fatal; an excused name that starts
MATCHING fails until its entry goes.

**`1ea9e23bc` a gate that judged a tree it could not see.** check:ci-syncpack-sources had
landed in `quality-branch`, which checks out NO submodules -- so private/account
vanished and its two correct exclusions read as DEAD entries. It now refuses with CANNOT
VERIFY when a directory its config names is absent, and its step moved to `quality-code`
(submodules: true), beside Lockfile. Also `CHECK 6` in check-workflow-gates.sh so nothing
can be re-added ahead of the watchdog's monitor, and the submodule pointer for the
lockfile fix.

**`00215294e` five traps + the i18next bump.** TRAPS.md 57 -> 62 entries (floor bumped in
the same commit, as its ratchet demands). i18next ^26.4.0 -> ^26.4.1 in packages/cli with
the syncpack pin moved in lockstep -- the pin's reason is ONE shared line, not one frozen
version.

**account `d86909d` + `6e35d26`.** npm 11 had pruned vitest's nested `@esbuild/*` from
that lockfile; CI pins npm 10, which requires it, and four jobs died at
setup-workspace. Regenerated with npm@10. Then the three minors check:deps demanded --
and NOT the typescript ^6.0.3 -> ^7.0.2 major `--upgrade` also took, which would have
made account the only one of eight manifests off the monorepo's compiler line.

## Three habits this block cost, before you repeat them

1. **Stage in its own tool call.** A pre-bash hook rejects the WHOLE command, so a
   `git add` written beside a blocked `git commit` never runs; the retry then commits the
   old index under the new message. It happened twice. `git show HEAD --stat` before
   believing any message.
2. **`npm ci --dry-run` locally proves nothing** -- it runs npm 11 here and CI pins 10.
   `npx -y npm@10 ci --dry-run` is the check, and `npx -y npm@10 install
   --package-lock-only --ignore-scripts` is the fix.
3. **`check:actions` needs a token locally.** Without one it hits the anonymous rate
   limit and refuses (correctly) rather than passing vacuously. Run ci:quick with
   `GH_TOKEN="$(gh auth token)" GITHUB_TOKEN="$(gh auth token)"` or it reds for nothing.

## Landed since the last state write

**private/account is now inside syncpack's pins** (console `b6c28bd1b`, account
`be1bbc1`). syncpack's default source is package.json's `workspaces`, so a SUBMODULE was
outside every versionGroup -- the OTel lockstep included. Proven fixed by planting a
drift in account's @opentelemetry/core: it now reports `2x` where before it reported
nothing. Three divergences surfaced and each was resolved on its merits:

- `@rediacc/**` cannot be `*` in a non-workspace (no graph for it to resolve through), so
  it gets an explicit exception placed BEFORE the wildcard rule -- syncpack takes the
  first matching group.
- `@types/node` ^25.5.1 -> ^22.20.0. A CORRECTNESS fix: account declares
  `engines: node >=22.0.0` and was typing against Node 25 APIs absent at runtime.
- `typescript` ^7.0.2 -> ^6.0.3, a whole major apart from every other manifest.

Both version moves were verified before keeping: tsc clean on both of account's tsconfig
projects, integration suite 1550/1550 across 92 files.

## Next action

Nothing is queued. The worklist has exactly one open item and it is the [?] above, which
only the operator can answer. So: re-arm a PR-checks monitor and read CI.

    gh run list --branch 0903-1 --limit 1
    gh api repos/rediacc/console/actions/jobs/<id> \
      --jq '.steps[]|select(.conclusion=="failure")|.name'

Name failing STEPS, not jobs -- the run-level view reports cancelled siblings as
failures, and the watchdog cancels the run when one job fails. A failure in a file this
branch touched is yours; before calling one pre-existing, show that none of its findings
are in files the branch touched.
