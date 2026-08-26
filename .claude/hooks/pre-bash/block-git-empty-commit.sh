#!/usr/bin/env bash
# Block empty commits used to re-trigger CI.
#
# THE ONE CASE THIS USED TO GET WRONG. The block is unconditional, and its advice
# is "rerun the run" -- which presupposes a run EXISTS. On 2026-08-26 GitHub
# created no run at all for PR #577: Actions was enabled, the workflow was
# `state=active`, `pull_request: [opened, synchronize]` matched, the branch was
# not a fork, there was no draft filter, and an unrelated scheduled run was
# created 13 seconds after the PR was opened -- so Actions was demonstrably
# alive. `gh api .../commits/<head>/check-runs` returned `total_count: 0`, and no
# `startup_failure` run existed either. There was nothing to rerun, and
# `workflow_dispatch` is guarded to `main` and cannot satisfy PR checks, so the
# only remaining lever was a commit -- which this hook refused.
#
# A guard whose advice is unreachable in the case it fires on stops being a
# guard. So the escape is a CHECK, not a flag: name the head sha you believe has
# no run, and the hook VERIFIES that against GitHub. If a run exists the block
# stands and you are told to rerun it, which is the original advice arriving at
# the moment it is actually true.
#
#   CI_RETRIGGER_NO_RUN_FOR=<head-sha> git commit --allow-empty -m "..."
#
# It cannot be used to dodge the rerun advice: the verification fails whenever
# there is something to rerun. It fails CLOSED on every uncertainty -- no `gh`,
# an API error, a sha that is not HEAD -- because "I could not check" must never
# read as "there is no run".

CMD=$(jq -r '.tool_input.command' 2>/dev/null)

if ! echo "$CMD" | grep -qE 'git commit[^|;&]*--allow-empty'; then
    exit 0
fi

ADVICE="Instead, rerun the run: for failures in tunnel-CONSUMER jobs (Tests+Infra E2E / CLI / E2E Electron, or any job that waited on 'tunnel URL'), use a FULL 'gh run rerun RUN_ID --repo rediacc/console', because the tunnel-url artifact is named per run_attempt and the already-green publisher job (infra-backend) does not rerun on --failed, so a --failed rerun leaves consumers waiting 300s for an artifact that never appears. For all other failures, 'gh run rerun RUN_ID --repo rediacc/console --failed' is cheaper and sufficient. If the run was force-cancelled and the AI classified a transient failure as code-change, first update .ci/prompts/ci-failure-classifier.md so that pattern is recognized as transient, then rerun."

CLAIM="${CI_RETRIGGER_NO_RUN_FOR:-}"
if [ -n "$CLAIM" ]; then
    reason=""
    if ! command -v gh >/dev/null 2>&1; then
        reason="gh is not available, so the no-run claim cannot be verified"
    elif ! head_sha=$(git rev-parse HEAD 2>/dev/null); then
        reason="could not read HEAD, so the claimed sha cannot be checked against it"
    elif [ "${head_sha#"$CLAIM"}" = "$head_sha" ]; then
        reason="CI_RETRIGGER_NO_RUN_FOR='$CLAIM' is not a prefix of HEAD ($head_sha)"
    elif ! count=$(gh api "repos/rediacc/console/commits/$head_sha/check-runs" --jq '.total_count' 2>/dev/null); then
        reason="the check-runs API could not be read; 'I could not check' is not 'there is no run'"
    elif ! echo "$count" | grep -qE '^[0-9]+$'; then
        reason="the check-runs API returned a non-numeric count ('$count')"
    elif [ "$count" -ne 0 ]; then
        reason="$count check-run(s) already exist for $head_sha -- there IS something to rerun"
    fi

    if [ -z "$reason" ]; then
        echo "ℹ️  empty commit ALLOWED: verified 0 check-runs for HEAD ($head_sha), so there is no run to rerun and a commit is the only lever left." >&2
        exit 0
    fi

    echo "❌ BLOCKED: the no-run claim did not verify -- $reason." >&2
    echo "   $ADVICE" >&2
    exit 2
fi

echo "❌ BLOCKED: Do not use empty commits to re-trigger CI. Empty commits kick off a fresh CI run (attempt 1 of 2) that redoes ALL jobs and wastes runner minutes. $ADVICE" >&2
echo "   If GitHub created NO run at all for this head (verify: gh api repos/rediacc/console/commits/\$(git rev-parse HEAD)/check-runs --jq .total_count), there is nothing to rerun; re-run this command with CI_RETRIGGER_NO_RUN_FOR=\$(git rev-parse HEAD), which makes the hook check that claim itself." >&2
exit 2
