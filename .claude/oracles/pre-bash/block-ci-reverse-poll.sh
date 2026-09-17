#!/usr/bin/env bash
# Block reverse CI polling: gh run view ... --jq then sleep.
#
# The guidance POINTS AT the ci-watch skill rather than embedding a copy of the
# loop. It used to embed one, and on 2026-08-25 that copy was found to be one of
# nine divergent versions across the repo, several of them handing out a form
# that exits on the first `status == completed` -- which is not terminal,
# because the watchdog re-runs a transient failure and bumps run_attempt.
#
#
# NOT ROUTED THROUGH lib/command-scan.sh, and that is a decision rather than an
# oversight. On 2026-08-27 nine sibling guards moved to the shared scanner to
# stop them matching prose. This one did not: the scanner drops heredoc bodies,
# and the operator ruled on 2026-08-25 -- four scored options -- that this guard
# keeps its prose false positive. It fails LOUDLY (a blocked command that names
# its workaround) while every narrowing fails SILENTLY, and a heredoc is exactly
# where a real one would hide. test-hooks.sh pins that ruling with a case
# asserting exit 2, and that case is what caught the attempt.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'gh[[:space:]]+run[[:space:]]+view[[:space:]]+[0-9]+[^|;&]*--jq[^|;&]*&&[[:space:]]*sleep'; then
    echo '❌ BLOCKED: Reverse polling pattern (gh run view followed by sleep). Polling chews through context. Run .ci/scripts/ci/ci-trace.py --wait with run_in_background:true -- it keys on the PR head, so a watchdog re-run and a superseded run are both handled structurally. Do NOT use gh run watch -- it has dropped silently on terminal runs (observed 4/4).' >&2
    exit 2
fi
exit 0
