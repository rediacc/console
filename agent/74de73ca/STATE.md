## SESSION 74de73ca 2026-09-03T21:15:19Z

Branch `0903-1`, PR #585, epic `24c98380`. **PUSHED** through `5216e20bb`; renet submodule
through `6c85007` (PR rediacc/renet#110). `ci:quick` 294/294 on the committed tree. The
operator is away, asked for full autonomy, no questions until they run `/ask`, CI reds
first. STATE.md left UNCOMMITTED on purpose: pushing bookkeeping cancels the live cycle.

## The thing that would do real damage

**Do NOT delete the three org secrets** (APP_PRIVATE_KEY, CLOUDFLARE_API_TOKEN,
DOCKERHUB_TOKEN) even though `derive-shadow-pass-list.sh` prints them. It proves each has
an equal Bitwarden twin -- necessary, NOT sufficient. 178 live `secrets.*` reads remain,
and two findings say why this is not a substitution:

1. **It is a REORDERING.** In every shadowed job `app-token` reads the key BEFORE the
   bws-secrets fetch, because app-token is needed to check out the repo and the local
   fetch action needs the repo checked out. Flipping in place hands it an EMPTY key. It
   resolves only where the sparse cone already carries `.github/actions` + `.ci/config`,
   so the fetch can move ahead of it. Proven on one job in `5216e20bb`.
2. **Only 155 of 178 reads are reachable.** The other 23 are passed into REUSABLE
   workflows through `secrets:` blocks, where env context does not exist. The called
   workflow's jobs must fetch from Bitwarden before the caller's block can go. So a
   complete flip still does not free the secrets -- that is a second wave.

## Where CI stands

Cycle for `5216e20bb` watched by bg `biccb7uwp`. **No cycle green yet;** sixteen distinct
reds fixed. That run is the proof of (1): it either mints an app token from the Bitwarden
value or it does not, and the answer generalises to the other 72 job/name pairs. A
CANCELLED run is usually SUPERSEDED -- read JOB conclusions, never the run's.

## Profiling wave 2 -- DONE, all six pieces (`#bc6a0b20` ticked)

`agent/PLAN-resprofile-wave2.md`. Landed: plain `python3` is recorded at last
(`sitecustomize.py` on PYTHONPATH; before it, 3x `python3 -c pass` added zero records);
the devbox builds `bashcov-sup`, which it had never had, so the container recorded no bash
at all; `BASHCOV_SHAPE` from `$0` so `bash.jsonl` is attributable; run-delay PROBED not
sysctl-read; the blocked share reads the tree not the supervisor (0% for 291/291 captures
before, 80/54/10% on real gates now); per-thread states (the leader reads idle for 59/62
ticks on go); and E7, which ABSTAINS on 678 pre-change captures rather than emit findings
it cannot validate. The gate is still unseeded and report-only, deliberately.

## Live facts a fresh session would get wrong

- `ci:quick` runs 294 gates. `check:lint`, `check:ci-format-scope`,
  `gate-test:fetch-depth-safety` and `gate-test:workflow-pr-environment` are slow-lane, so
  a max-lines overrun or a slow-gate tier can only surface in CI.
- The battery asserts it leaves no tracked file modified; a gate test must work on a COPY.
- Solution-page video players are DEFERRED behind a poster on purpose.
- Hook-blocked: a compound command containing `git push`; `git commit --amend`; polling CI
  with sleep+gh (use `ci-trace.py --wait`).
- No IPv6 egress here -- `curl -4` before judging a host unreachable.

## Next action

1. **`[?] #13d281a2` is the only open item.** Its DEFAULT is the work: continue the flip
   file by file, each one moving the bws-secrets fetch ahead of its first consumer before
   flipping that job's reads. 17 files, 72 job/name pairs remain. Delete nothing.
2. If CI is red, read the failing JOB's log and look EARLIER in the job than the step that
   failed -- sixteen for sixteen so far, the error named the wrong subject.
