#!/bin/bash
# Announce, loudly, which gates a CI-control label has removed from this run.
#
# WHY THIS EXISTS. The repo's label opt-outs are expressed as a step-level
# `if:` (job-level was tried for external_quality and reverted, ci-quality.yml
# "No label opt-out at JOB level any more"). That is the right shape, but it
# has one hole: a skipped step leaves the job `success` and prints NOTHING, so
# a run whose media gates were all removed looks exactly like a run where they
# all passed. `no-media-quality` is a temporary hold on gates that are being
# actively repaired, and a temporary hold nobody can see in the log is how a
# hold becomes permanent.
#
# So the announcer runs UNCONDITIONALLY -- it is not itself behind the mode
# `if:` -- and it does two jobs the step `if:` cannot:
#
#   skip  emit a ::warning:: and a step summary naming every gate that did not
#         run, plus the instruction to remove the label. Exit 0.
#   hard  print one line naming how many gates ARE enforced, which is the
#         proof that this announcer ran at all (a silent instrument and a
#         missing instrument look identical).
#   unset treat as hard. A wiring break must never read as "gates removed".
#   other REFUSE (exit 2). The step `if:` treats any unrecognised value as
#         "run", which is fail-closed but completely silent; this is the only
#         place a typo'd mode string is ever reported.
#
# Zero gate names is a refusal too: an announcer with nothing to announce is
# a miswired announcer, not a clean run.
#
# Usage: GATE_SKIP_MODE=hard|skip announce-gate-skips.sh <label> <gate...>

set -euo pipefail

MODE="${GATE_SKIP_MODE:-hard}"

if [ "$#" -lt 2 ]; then
    echo "usage: GATE_SKIP_MODE=hard|skip $0 <label> <gate...>" >&2
    exit 2
fi

LABEL="$1"
shift

case "$MODE" in
    hard | skip) ;;
    *)
        echo "announce-gate-skips: unknown GATE_SKIP_MODE '$MODE' (expected hard|skip)" >&2
        exit 2
        ;;
esac

if [ "$MODE" = "hard" ]; then
    echo "gate-skips: none. $# gate(s) enforced in this job (label '$LABEL' not applied): $*"
    exit 0
fi

echo "::warning::label '$LABEL' removed $# gate(s) from this job: $*"
echo "gate-skips: $# gate(s) NOT run in this job because the PR carries '$LABEL': $*"
echo "gate-skips: this is a temporary hold. Remove the label to restore them."

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
        echo "### Gates skipped by \`$LABEL\` ($# in this job)"
        echo ""
        for gate in "$@"; do
            echo "- \`$gate\` -- did NOT run"
        done
        echo ""
        echo "These gates are held, not exempt. Remove the \`$LABEL\` label as"
        echo "soon as the work it is waiting on lands, and let the run go red"
        echo "if the underlying defect is still there."
        echo "See docs/agent-reference/ci-gates.md."
    } >>"$GITHUB_STEP_SUMMARY"
fi

exit 0
