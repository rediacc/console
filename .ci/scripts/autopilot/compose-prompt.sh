#!/bin/bash
# Compose one autopilot round's prompt from the trusted template plus the
# gate's fixtures, and publish it as a step output.
#
# THE INJECTED BLOCKS ARE THE MODEL'S ONLY STATE CHANNEL. Agent mode inlines
# no PR text at all (03-v2-autonomy.md wall 1), so everything a round needs
# rides here: the decision, the state comment, the failed-job list, and -- for
# a review-response round -- the author-filtered review payload the gate built.
#
# A REVIEW ROUND WITH NO PAYLOAD REFUSES. The gate treats a failed thread
# fetch as a warning so one GraphQL hiccup cannot stop fix rounds; the cost of
# that choice is paid here, where a missing payload would mean answering
# findings the round never read.
#
# Usage:
#   compose-prompt.sh --prompts <dir> --fx <dir> --template <file> \
#     --mode <mode> --out <file>
#
# Writes <file>, and appends a `prompt` entry to $GITHUB_OUTPUT when that
# variable is set (so it is a no-op locally).
#
# THE HEREDOC DELIMITER IS RANDOM PER RUN, and that is a control rather than a
# flourish: the prompt now carries review-thread text that an outsider can
# influence by replying into a trusted thread. A fixed marker appearing in
# that text would close the `prompt` output early and let the remainder of the
# comment declare step outputs of its own.
#
# Exit: 0 composed, 1 a review round with no payload, 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
PROMPTS="${ARG_PROMPTS:-}"
FX="${ARG_FX:-}"
TEMPLATE="${ARG_TEMPLATE:-}"
MODE="${ARG_MODE:-}"
OUT="${ARG_OUT:-}"

[[ -n "$PROMPTS" && -n "$FX" && -n "$TEMPLATE" && -n "$MODE" && -n "$OUT" ]] || {
    log_error "usage: compose-prompt.sh --prompts <dir> --fx <dir> --template <file> --mode <mode> --out <file>"
    exit 2
}
require_dir "$PROMPTS"
require_dir "$FX"
require_file "$PROMPTS/$TEMPLATE"

{
    cat "$PROMPTS/$TEMPLATE"
    printf '\n<autopilot_state>\n'
    cat "$FX/decision.json"
    [[ -f "$FX/state.txt" ]] && cat "$FX/state.txt"
    printf '</autopilot_state>\n'
    printf '\n<failed_jobs>\n'
    [[ -f "$FX/failed-jobs.txt" ]] && cat "$FX/failed-jobs.txt"
    printf '</failed_jobs>\n'
} >"$OUT"

if [[ "$MODE" == "review-response" ]]; then
    if [[ ! -s "$FX/review-payload.json" ]]; then
        log_error "review-response round with no review payload fixture at $FX/review-payload.json; refusing to run a review round blind"
        exit 1
    fi
    {
        printf '\n<review_payload>\n'
        cat "$FX/review-payload.json"
        printf '\n</review_payload>\n'
    } >>"$OUT"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    delim="AUTOPILOT_PROMPT_EOF_$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    {
        printf 'prompt<<%s\n' "$delim"
        cat "$OUT"
        printf '%s\n' "$delim"
    } >>"$GITHUB_OUTPUT"
fi
log_info "composed the $MODE prompt ($(wc -c <"$OUT") bytes) from $TEMPLATE"
