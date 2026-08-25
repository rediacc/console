---
name: ci-watch
description: How to watch a GitHub Actions run from an agent session without losing the verdict. The wake-up contract, why cancelled is not passed, why completed is not terminal, and the compound-watch bug that swallowed a real failure for 90 minutes. Use whenever arming a background watch on CI, a review marker, or any other terminal state.
user-invocable: false
self-improving: true
---

# ci-watch: arming a watch that actually wakes you

## The contract

**A watch notifies on process EXIT, not on output.** So it must EXIT at the
terminal state and wait for exactly ONE thing. **One wait per background
command**; arm a second watch after the first fires. *Tell:* a non-empty output
file on a still-running watch means it already answered and is now stuck.

## `completed` is not terminal: the watchdog re-runs

A `completed` run returns to `in_progress` when the watchdog auto-retries a
transient failure, bumping `run_attempt`; exiting on the first `completed` hands
you attempt 1's verdict as final. Require the SAME attempt twice.

## The canonical form

```bash
R=<run-id>; REPO=<owner>/<repo>; P=""
while :; do
  S=$(gh api "repos/$REPO/actions/runs/$R" --jq '"\(.status) \(.run_attempt)"') || { sleep 20; continue; }
  case "$S" in
    completed*) [ "$P" = "$S" ] && break; P="$S"; sleep 90 ;;
    *)          P=""; sleep 20 ;;
  esac
done
gh api "repos/$REPO/actions/runs/$R/jobs?per_page=100" --paginate \
  --jq '.jobs[]|select(.conclusion!="success" and .conclusion!="skipped")|"\(.conclusion)\t\(.name)"'
```

`run_in_background: true`. `sleep 20`, because a pre-bash hook blocks anything
longer. An EMPTY final list is the pass; never filter for `=="failure"`.

## Read the JOBS, not the run

`cancelled` is not a pass, and these look identical while meaning opposites:

| shape | meaning |
|---|---|
| cancelled siblings **with** a failed job | watchdog killed the run for that failure |
| cancelled, **zero** failures, newer head | superseded by a push; watch the newer run |
| one job cancelled at its `timeout-minutes` | it hung; classify it (below) |

**Classify before touching anything:** a job that passed on an earlier run of this
branch is transient, already being retried, and "fixing" it edits working code.

## Re-check on every wake

**A watch that never fires is indistinguishable from a run that never
finished.** Re-read the run on any re-invocation and re-arm freely; a
`killed`/`failed` notification is a re-arm trigger, not a no-op. Each push
restarts the pipeline, so batch fixes into one push. **`gh run watch` stays
rejected**; see [incidents.md](incidents.md).
