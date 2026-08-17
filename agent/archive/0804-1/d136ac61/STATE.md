# STATE — TWO LIVE SESSIONS SHARE THIS BRANCH. Both blocks are current.
# MERGE, never rewrite: a plain rewrite destroyed B's block twice. Cap is 4000
# PER `## SESSION` block, so there is room to merge honestly.
#
# NOTE ON B'S BLOCK BELOW, added by A without editing its content: it is
# stamped 11:50Z, now ~8.5h old, and the head it names is long superseded.
# Read it for B's intent, never for its facts; re-derive head from git.

## SESSION B (d136ac61) — 2026-08-07 04:35Z — WAVE 0804-1 MERGED; release retrying

**ALL THREE PRs MERGED, IRREVERSIBLE, DO NOT REDO:** renet #98 -> e8dd8318a,
account #74 -> 1da0377c2, console #551 -> 9012b2251 (03:09:50Z). #551 was NOT
rebased: GitHub caps rebase-and-merge at 100 commits and it had 120, so it
landed as a MERGE COMMIT via allow_merge_commit, following PR 543's precedent.
The restore ran unconditionally; settings VERIFIED back at merge=false
squash=false rebase=true.

**FIRST RELEASE ATTEMPT FAILED; I PUSHED A FIX TO MAIN.** Run 31143504009
ended CANCELLED at 04:27Z: `Validate Promotion` hit `timeout-minutes: 30` at
30m13s, and assert-ci-complete.sh forgives `skipped` but NOT `cancelled`, so
`CI Complete` and `Pipeline Sentinel` failed and finalize never dispatched
cd-v2.yml. NO Release run was ever created. Cleanup ran, no orphaned R2 bytes.

NOT transient. That job's `main` durations, oldest first: 21m57s, 27m20s,
CANCELLED 31m03s (2026-07-28), 28m35s, 24m09s, 24m56s, 24m01s, CANCELLED
30m51s — years-long creep against its own ceiling. A PR cannot catch it: PR
runs promote the tiny pr-551 channel in 7m19s, `main` promotes the full `edge`
channel, which grows every release. That is the main-only test, so the fix
went DIRECTLY ON MAIN per the pr-merge rule: commit afe143d9a, one file,
timeout 30 -> 60 with the measurements in a comment. Main is afe143d9a, clean.

**IN FLIGHT: Console CI 31147690890 on afe143d9a**, watch b6ah0qi7e. Green =>
finalize dispatches Release (cd-v2.yml): tag -> GitHub Release -> R2 -> DEPLOY
EDGE; watch that separately. 60 only buys headroom: promotion is O(channel
size) and re-copies the whole channel; if it creeps past 60, make the copy
incremental rather than raising the number again.

**TWO RUNS SHARE A HEAD; SELECT BY EVENT, never by workflow name.** event=push
is the release path; event=schedule is the nightly.

**AFTER Release is green, RE-SYNC — not optional.** CD pushes 2 commits back
to main every time (homebrew-tap pointer, contract-floor bump): `git fetch
origin --prune`, `git merge --ff-only origin/main`, `git submodule update
--init --recursive`. The resulting `M private/homebrew-tap` is BEHIND, not
ahead. Then CronDelete bb1e9e5d and inbox poll 1c2c47fd, and hand back.

**IF A MAIN-ONLY STEP FAILS, CLASSIFY FIRST:** did that job run and PASS on PR
run 31136715318? Yes => transient, the watchdog retries, do not fix working
code. Never ran there (finalize-release-sentinel, pipeline-sentinel,
check-release-state, build-devcontainer-manifest, all of cd-v2.yml, Docker)
=> main-only, and only then a surgical direct-to-main commit.

**FINDING #c970a391, deferred, NOT this wave.** Nightly on main failed 10
straight nights. The nightly on the merged head (31145452611) narrowed it:
`Quality / Go` now PASSES; only `Quality / Security` remains — npm audit,
astro x4 XSS plus sharp HIGH GHSA-f88m-g3jw-g9cj (libvips CVEs, fixed in sharp
>=0.35.0). That run also failed `Tests + Infra / E2E K8s Ceph`, unexamined,
not in the push path. Root defect: Quality is SKIPPED on push-to-main, so the
nightly is the only place these touch main and a red nightly notifies nobody.
Fix on a fresh MMDD-N branch AFTER the release.

**TRAPS:** `gh pr list --json commits` silently caps at 100 (use `gh api
.../pulls/N --jq .commits`); the jobs API defaults to per_page=30 (use 100);
a CANCELLED job is not a passing job.

## Next action
Read watch b6ah0qi7e (Console CI 31147690890). If green, find and watch the
Release run: `gh run list --workflow "Release" --limit 3`, event
workflow_dispatch, head afe143d9a. Then re-sync, CronDelete both crons, report.
