## SESSION 74de73ca 2026-09-03T21:38:26Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `cfbdc6cbe`; renet submodule
`6c85007` (PR rediacc/renet#110). `ci:quick` 295/295 on the committed tree. Operator away,
full autonomy, no questions until they run `/ask`, CI reds first. STATE.md is committed
with real changes only -- a bookkeeping-only push cancels the live cycle.

## The thing that would do real damage

**Do NOT delete APP_PRIVATE_KEY / CLOUDFLARE_API_TOKEN / DOCKERHUB_TOKEN** even though
`derive-shadow-pass-list.sh` prints them. It proves an equal Bitwarden twin exists --
necessary, NOT sufficient. 176 live `secrets.*` reads remain (104/44/28). Two findings:

1. **It is a REORDERING.** In most shadowed jobs `app-token` reads the key BEFORE the
   bws-secrets fetch (app-token is needed to check out the repo; the local fetch action
   needs the repo checked out). Flipping in place hands it an EMPTY key. It resolves where
   the sparse cone already carries `.github/actions` + `.ci/config`. But the ordering is a
   per-job property: in `breakpoint.yml` the fetch already precedes app-token. Check,
   never assume.
2. **Only 155 of 178 reads are reachable.** 23 are passed into REUSABLE workflows via
   `secrets:` blocks, where env context does not exist. Those callees must fetch from
   Bitwarden themselves first. A complete flip still does not free the secrets.

Proven flip: `5216e20bb` (backfill-release-sentinel.yml), the first live consumer of a
Bitwarden value anywhere in the tree.

**Do NOT touch `.github/workflows/breakpoint.yml` casually.** It is VENDORED from
`.ci/breakpoint/workflow/breakpoint.yml` with a MANIFEST.sha256; a flip there was refused
by check:ci-breakpoint-drift AND gate-test:breakpoint-secret-exposure, and editing the
template plus `--write` did not satisfy them either. I reverted all three files rather
than force it. Read `.ci/breakpoint/README.md` before retrying; it is 1 of 72 pairs.

## Where CI stands

Watched by bg `bh03rtnqs`, whose head is superseded -- re-arm with
`.ci/scripts/ci/ci-trace.py --wait` (background). **No cycle green yet;** ~16 reds fixed,
and in every one the error named the WRONG SUBJECT. Look EARLIER in the job than the step
that failed. A CANCELLED run is usually SUPERSEDED: read JOB conclusions, never the run's.

## Landed tonight, do not redo

- Profiling wave 2 COMPLETE (all six pieces of `agent/PLAN-resprofile-wave2.md`): plain
  `python3` is recorded at last, the devbox builds `bashcov-sup` (it had none), bash
  records carry a shape, run-delay is probed not sysctl-read, the blocked share reads the
  tree (0% for 291/291 before; 80/54/10% now), per-thread states, and E7 which abstains
  rather than guess. Gate deliberately unseeded/report-only.
- `check:ci-checkout-cone` -- a step may not run a file its job never checked out. 359
  invocation sites, 106 jobs, 0 findings. Its own controls caught two of my bugs.
- `check:ci-battery-clean-tree`, `check:ci-workflow-env-provision`,
  `gate-test:fetch-depth-safety`, `gate-test:workflow-pr-environment` all new tonight.

## Live facts a fresh session would get wrong

- `ci:quick` runs 295 gates; `check:lint` and four others are slow-lane, so a max-lines
  overrun or a mis-tier can only surface in CI.
- Hook-blocked: a compound command containing `git push`; `git commit --amend`; polling CI
  with sleep+gh. Use `ci-trace.py --wait` in the background.
- No IPv6 egress here -- `curl -4` before judging a host unreachable.

## Next action

1. **`[?] #13d281a2` is the only open item.** Its DEFAULT is the work: continue the flip
   file by file, each time checking whether that job's fetch precedes its first consumer
   and moving it if not. 16 files left. Delete nothing.
2. If CI is red, read the failing JOB's log first.
