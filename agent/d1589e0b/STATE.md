## SESSION d1589e0b 2026-09-06T08:05Z

# Branch tooling-transformation-w0 is PUSHED and rebased on main. Four nightly reds fixed ON MAIN.

## Next action
**Nothing is blocked on me.** One `[?]` is open: `#ed6f6ea8` -- merge account
PR #86 and bump console's `private/account` gitlink, which greens main's LAST
nightly red. Its DEFAULT executes in 120 min. A trace of main CI is running in
the background; read its verdict before claiming main is green.

## What this round did

**Four reds on main, from nightly run `34014201256`, three of them mine.**
The nightly failed FOUR Quality shards and each was a separate cause:

| shard | cause | fixed |
|---|---|---|
| Code | `check:lint`: `writeBaselineVerdict` import I orphaned in `scripts/check-secret-scope.ts` | `3defca1c0` on main |
| Security | my `(a2)` arm's exemption liveness sweep ran on FIXTURE trees, so `check-workflow-gates.sh` exited 1 on every fixture -- reddening `test-slim-timeout.sh` and all of `test-workflow-contracts.sh` | `935724166` on main |
| Content | `check:deps`: `eslint-plugin-regexp` 3.2.0->3.3.0, `hono` 4.13.5->4.13.7 | `97be44b94` on main |
| Go | `private/account` `rotation-bitwarden-names.test.ts` pins AWS_SES_*_ASIA as missing; they resolve now | **PR #86, unmerged** -- `[?] #ed6f6ea8` |

Plus one found on the way: `claude-review-reusable.yml` used `uses:
./.github/actions/profiler`, and `./` resolves against the CALLER's tree, so
every rediacc/account and rediacc/renet review run died on it. Guarded with the
same `if: github.repository == 'rediacc/console'` the bws-secrets step twelve
lines below already carried. `5aa8d197a` on main.

## THE LESSON OF THIS ROUND: I shipped an arm with no test, and other gates paid
Arm `(a2)` and its `DECLARED_UNUSED_OK` list shipped with **zero** controls. The
cost did not land on the arm -- it landed on two unrelated gate tests, for a file
their fixtures were never meant to contain. Six paired cases now cover it
(`test-workflow-contracts.sh`, 29/29), and `REAL_WORKFLOW_TREE` is overridable
precisely so the liveness sweep is drivable from a fixture at all.

## THE RELEASE IS HALF-COMPLETING, and it is not mine alone
`Release to Edge` **34019022671** (v1.3.11) shows `failure`, but read the jobs:
Initialize, publish, all three regional account deploys, marketing, smoke test
and all six install validations **succeeded**. Only `Tag & GitHub Release`
failed, on `git push origin v1.3.11`:

    ! [remote rejected] v1.3.11 -> v1.3.11 (refusing to allow a GitHub App to
      create or update workflow `.github/workflows/claude-review-reusable.yml`
      without `workflows` permission)

So edge is DEPLOYED as 1.3.11 with **no git tag and no GitHub Release**; the
newest tag is `v1.3.10`. Not mine alone and not new: run **34003183456** died
identically on v1.3.8, naming `ci-quality.yml`. The trigger is a workflow commit
landing on main while a release is in flight -- mine (`5aa8d197a`) landed during
this one.

It is at least not silent: `promote-stable.yml:68` calls
`.ci/scripts/release/assert-edge-tag-exists.sh`, which refuses to promote a
channel pointer whose version has no tag/Release/sentinel. I first read that
guard as unwired and was wrong -- grep `.github/` directly before saying so.

Tracked as `[?] #567dcb4c`, `door:operator-only`: `.github/actions/app-token`
never requests `workflows` (only contents/pull-requests/actions/packages/
deployments), and the release bot has **never** landed a `.github/workflows`
commit, so there is no evidence the App installation holds that permission --
requesting one it lacks makes the token mint fail and would break every CD run.

## A cancelled run with ZERO jobs is "superseded", not "killed"
`34018240626` on `935724166` reads `cancelled`. `total_count` for its jobs is
**0**: nothing ever started, so no job failed, and a newer commit exists. That
is the superseded shape. The watchdog-kill shape has cancelled siblings AND a
failed job. Both print the same word.

## Two things I got wrong, recorded so they are not repeated
1. **"Blocked by a peer's uncommitted tree" was true of the REBASE and I carried
   it to the PUSH.** A push needs no clean tree. The branch had no upstream at
   all; `git push -u` worked immediately. Ten commits sat unpushed for hours on a
   diagnosis that was never tested.
2. **`check:deps --upgrade` is wider than `check:deps`.** It swept
   `private/account` and took nodemailer 9->10 and typescript 6->7, majors CI
   never demanded. Reverted; the submodule is byte-identical to its committed
   state. Bump only what the gate NAMES.

## Local-only red, not a repo red
`check:actions` and `check:deps` both call the GitHub API and rate-limit
anonymously on this machine. Run the lane as
`GITHUB_TOKEN="$(gh auth token)" npm run ci:quick` or you will chase a red that
does not exist in CI.

## READ FIRST: the branch, and what was wrong about this section
`git branch --show-current` = **tooling-transformation-w0**. It appeared
mid-session; 74de73ca confirms it is not theirs. It is now **pushed and rebased
onto main** (`git merge-base --is-ancestor origin/main HEAD` = yes), and local
tracks `origin/tooling-transformation-w0` exactly.

This section used to say the branch was "local only" and that pushes were being
refused. **Both were wrong**, and 74de73ca said so before I proved it: my
`c6d3af163` was on origin/main the whole time. Verify what is on the remote
rather than inferring it from a push you think failed.

Republishing after the rebase went through the mediated verb, not a raw force
push: `.claude/hooks/stop/worklist.py --git force-push <branch> --execute`.
`warn-remote-drift.sh` cannot tell a self-rebase from a peer push, so it blocks
either way; before using the verb I proved by `git patch-id` that every
remote-only commit had a local twin except `7a770d098`, which was deliberately
skipped because its one-line change is on main as `3defca1c0`.

74de73ca's `scripts/gate-bind.ts` fix (`check:ci-gate-bind` ENOENT: it
enumerated via `git ls-files` then read the WORKTREE) is committed and carried
as `b66befbe9`. Their peer answer `#18064e7b` is acked.

## What shipped
**v1.3.8 and v1.3.9 released, signed.** Org-scope reads **147 -> 1**.
`ci:quick` **313/313**.

Gates added: `check:ci-tracked-credentials` (53 controls, bound to
`wl_store.py::_SECRET_SHAPES` so the detector cannot drift narrower than the
redactor) · `check:ci-release-key-canonical` (12) ·
`check:ci-release-signing-coverage` · `check:ci-staging-tag-guard` · a 4th arm on
check-workflow-gates CHECK 2 (a callee DECLARING a secret nothing reads; 57 had
accumulated). Shared tally at `.ci/scripts/lib/gate-controls.sh`.

## DO NOT "just sign archlinux" — it breaks users
`pacman.conf(5)` SigLevel **Optional**, what Arch ships as `LocalFileSigLevel`, is
"An invalid signature is a fatal error, **as is a signature from a key not in the
keyring**." A `.sig` from a key no user holds turns a working `pacman -U` into a
HARD FAILURE; the keyring rollout lands FIRST. nfpm cannot sign archlinux at all
(`field signature not found in type nfpm.ArchLinux`; upstream #628 open, PR #1065
unmerged). Reason recorded in `.ci/config/nfpm.yaml` where the fix is attempted.

**apk is PREPARED**: conditional on `NFPM_APK_KEY_FILE`, `key_name` PINNED to
`releases@rediacc.com` (APKv2 matches the pubkey by FILENAME), both paths gated in
`test-linux-packages.sh` (21/21). Only the RSA key is missing — operator-only,
`door:operator-only`, deliberately not minted by an agent on a shared worktree.

## Findings worth carrying
1. **`""` READS AS "NOT WANTED"** — an empty credential made the build SKIP signing
   and exit 0, green while shipping UNSIGNED packages.
2. **The GPG key is TWO Bitwarden items**; part 1 lacks a trailing newline, so
   joining WELDS two base64 lines. The build repairs it in flight and now SAYS so
   (exit 10) instead of papering over it forever.
3. **Comments count as reads**: `secrets.AWS_SES_*_EU` in prose registered a
   secret named `AWS_SES_`.
4. **Two release jobs**: `Tag & Release` is NOT the tagging step; `Tag & GitHub
   Release` is. Trace a dispatched release BY RUN ID.
5. **Channel-tag cleanup can never succeed** — `cleanup-staging.sh` guards to
   `staging-*` by design and CHANNEL is `edge`/`stable`. It blamed a token scope
   for a design guard. Now gated by `check:ci-staging-tag-guard`.

## Local tooling
`bw`+`bws` on PATH; `~/.bw-session` unlocks the vault; `BWS_ACCESS_TOKEN` NOT in
env. `nfpm` via `.ci/scripts/build/ensure-nfpm.sh`; `createrepo_c`+`rpm` installed.
**No shfmt binary**: format via `npm run check:ci-shell-format`, strip ANSI,
`patch -p0`. **Strip ANSI before counting tsc errors.**

## Operator-only
1. **`BWS_ACCESS_TOKEN` EXPIRES 2026-09-08.** Gates the apk key AND fixing the
   welded GPG value at source.
2. **Account PR #86** unmerged; console gitlink stays at `65820fd74`.
