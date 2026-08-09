#!/bin/bash
# Assemble the round's claude_args from validated inputs.
#
# ONE PLACE, because two hardcoded copies of an argument list drift: the review
# pipeline paid for exactly that with a log line claiming a model the run had
# not used. The gate has already constrained --model to its allowlist, so
# nothing arbitrary reaches the flag from here.
#
# EFFORT has two sources and they answer different questions:
#   --effort      the DISPATCH input: one human, one hard failure, this round
#                 only. It is deliberately not recorded in the campaign.
#   --effort-var  the AUTOPILOT_EFFORT repo VARIABLE: the standing setting for
#                 AUTONOMOUS rounds, which have no dispatcher to ask. Without
#                 it every unattended round ran at the model's own default and
#                 the operator's only lever was to dispatch each round by hand.
# The dispatch input wins when present, because a human aiming at one round
# knows something the standing setting does not. An unrecognised variable is
# IGNORED LOUDLY (::notice) rather than passed through: `--effort banana` would
# fail the round after paying for the runner, and a silent drop would leave the
# operator believing a setting was in force that never was.
#
# Usage:
#   resolve-model-args.sh --model <id> --mode <fix|review-response> \
#     [--effort <dispatch>] [--effort-var <variable>]
#
# Prints the argument list (one flag per line) on stdout, and appends an `args`
# entry to $GITHUB_OUTPUT when that variable is set.
#
# Exit: 0 resolved, 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
MODEL="${ARG_MODEL:-}"
MODE="${ARG_MODE:-}"
# `${x-}` rather than `${x:-}` throughout: an explicitly empty value is a real
# case here (an unset repo variable arrives as an empty string), and it must
# read as "absent" rather than be replaced by something else.
EFFORT="${ARG_EFFORT-}"
EFFORT_VAR="${ARG_EFFORT_VAR-}"

[[ -n "$MODEL" && -n "$MODE" ]] || {
    log_error "usage: resolve-model-args.sh --model <id> --mode <mode> [--effort <dispatch>] [--effort-var <variable>]"
    exit 2
}

# The only efforts the CLI accepts. 'default' is the dispatch input's way of
# saying "do not pass the flag at all", so it is not a member.
EFFORT_ALLOWED="low,medium,high,xhigh,max"

in_csv() { # <value> <csv>
    local value="$1" csv="$2" item
    local -a __items=()
    IFS=',' read -ra __items <<<"$csv"
    for item in "${__items[@]}"; do
        [[ -n "$item" && "$item" == "$value" ]] && return 0
    done
    return 1
}

turns=60
[[ "$MODE" == "fix" ]] && turns=80

resolved_effort=""
source_of=""
if [[ -n "$EFFORT" && "$EFFORT" != "default" ]]; then
    if in_csv "$EFFORT" "$EFFORT_ALLOWED"; then
        resolved_effort="$EFFORT"
        source_of="the dispatch input"
    else
        echo "::notice::autopilot: dispatch effort '$EFFORT' is not one of $EFFORT_ALLOWED; ignoring it"
    fi
fi
if [[ -z "$resolved_effort" && -n "$EFFORT_VAR" && "$EFFORT_VAR" != "default" ]]; then
    if in_csv "$EFFORT_VAR" "$EFFORT_ALLOWED"; then
        resolved_effort="$EFFORT_VAR"
        source_of="the AUTOPILOT_EFFORT variable"
    else
        echo "::notice::autopilot: AUTOPILOT_EFFORT is '$EFFORT_VAR', which is not one of $EFFORT_ALLOWED; ignoring it and running at the model's default effort"
    fi
fi

args="--model $MODEL"$'\n'"--max-turns $turns"$'\n'"--disallowed-tools Task,Agent"
if [[ -n "$resolved_effort" ]]; then
    args="$args"$'\n'"--effort $resolved_effort"
fi

printf '%s\n' "$args"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    {
        echo 'args<<AUTOPILOT_ARGS_EOF'
        printf '%s\n' "$args"
        echo 'AUTOPILOT_ARGS_EOF'
    } >>"$GITHUB_OUTPUT"
fi
if [[ -n "$resolved_effort" ]]; then
    log_info "round args: model $MODEL, $turns turns, effort $resolved_effort (from $source_of)"
else
    log_info "round args: model $MODEL, $turns turns, the model's default effort"
fi
