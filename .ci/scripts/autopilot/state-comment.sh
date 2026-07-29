#!/bin/bash
# The autopilot state comment: one comment per PR, authored by the autopilot
# app, PATCH-updated in place, in PLAIN VISIBLE TEXT (03-v2-autonomy.md
# section 3 - HTML comments are stripped from prompts, and agent mode inlines
# no thread text at all, so this comment is the ONLY state channel).
#
# TRUST RULE: console is public and anyone can post a lookalike. A comment is
# the state comment only when its author equals the autopilot bot AND its
# body starts with the exact header. Everything else is untrusted data.
#
# Subcommands (select and render are pure and offline-testable; posting is a
# plain `gh api` PATCH/POST the workflow performs with the post-model token):
#   select --comments <file> --bot <login>
#       <file>: JSON array of {id, author, body}. Prints
#       {"found":true,"id":N,"body":...} for the newest trusted match, or
#       {"found":false} when none exists.
#   render --body <file> --state <s> --round <r/cap> --head <sha> \
#          --last-run <id/attempt handled> [--ledger <line>] \
#          [--ruled-out <line>] [--decision <line>]
#       Rebuilds the full body: header, state line, then the three sections
#       carried over from --body (absent/empty file = fresh comment) plus the
#       appended lines. Every appended line is hard-capped at 400 chars.
#       Above 55 KB, ledger rounds older than the last 8 compact to a
#       one-line pointer (full detail persists in that round's workflow
#       logs, reachable by run id).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

HEADER='### Autopilot state (machine-maintained, do not edit)'
LINE_CAP=400
COMPACT_BYTES=$((55 * 1024))
KEEP_FULL_ROUNDS=8

cmd="${1:-}"
shift || true
parse_args "$@"

cap_line() { # truncate one line to LINE_CAP characters
    local line="$1"
    if ((${#line} > LINE_CAP)); then
        printf '%s\n' "${line:0:LINE_CAP}"
    else
        printf '%s\n' "$line"
    fi
}

case "$cmd" in
    select)
        COMMENTS="${ARG_COMMENTS:-}"
        BOT="${ARG_BOT:-}"
        [[ -n "$COMMENTS" && -n "$BOT" ]] || {
            log_error "usage: state-comment.sh select --comments <file> --bot <login>"
            exit 2
        }
        require_file "$COMMENTS"
        # Strict author equality plus exact header prefix; newest (highest id)
        # wins if the bot somehow posted twice.
        jq -c --arg bot "$BOT" --arg header "$HEADER" '
            [ .[]
              | select((.author == $bot) and (.body | startswith($header))) ]
            | sort_by(.id)
            | if length == 0 then {found: false}
              else {found: true, id: .[-1].id, body: .[-1].body} end
        ' "$COMMENTS"
        ;;
    render)
        BODY="${ARG_BODY:-}"
        STATE="${ARG_STATE:-}"
        ROUND="${ARG_ROUND:-}"
        HEAD_SHA="${ARG_HEAD:-}"
        LAST_RUN="${ARG_LAST_RUN:-}"
        [[ -n "$STATE" && -n "$ROUND" && -n "$HEAD_SHA" && -n "$LAST_RUN" ]] || {
            log_error "usage: state-comment.sh render --body <file> --state <s> --round <r/cap> --head <sha> --last-run <id/attempt handled> [--ledger <line>] [--ruled-out <line>] [--decision <line>]"
            exit 2
        }

        work="$(mktemp -d)"
        trap 'rm -rf "$work"' EXIT
        : >"$work/ledger"
        : >"$work/ruled"
        : >"$work/decisions"

        # Carry over the three sections from the previous body. Parsing is a
        # simple section walk; anything outside the known sections is dropped,
        # which keeps a tampered-with body from smuggling text forward.
        if [[ -n "$BODY" && -s "$BODY" ]]; then
            awk -v ledger="$work/ledger" -v ruled="$work/ruled" -v dec="$work/decisions" '
                /^#### Round ledger$/ { section = "ledger"; next }
                /^#### Ruled out$/ { section = "ruled"; next }
                /^#### DECISIONS/ { section = "dec"; next }
                /^####/ { section = ""; next }
                /^###/ { section = ""; next }
                section == "ledger" && /^r[0-9]+ \| run / { print > ledger }
                section == "ruled" && /^- / { print > ruled }
                section == "dec" && /^- / { print > dec }
            ' "$BODY"
        fi

        [[ -n "${ARG_LEDGER:-}" ]] && cap_line "$ARG_LEDGER" >>"$work/ledger"
        [[ -n "${ARG_RULED_OUT:-}" ]] && cap_line "- $ARG_RULED_OUT" >>"$work/ruled"
        [[ -n "${ARG_DECISION:-}" ]] && cap_line "- $ARG_DECISION" >>"$work/decisions"

        render_body() { # render_body <ledger-file>
            printf '%s\n' "$HEADER"
            printf 'state: %s | round: %s | head: %s | last_run: %s\n' \
                "$STATE" "$ROUND" "$HEAD_SHA" "$LAST_RUN"
            printf '\n#### Round ledger\n'
            cat "$1"
            printf '\n#### Ruled out\n'
            cat "$work/ruled"
            printf '\n#### DECISIONS (post-hoc review)\n'
            cat "$work/decisions"
        }

        render_body "$work/ledger" >"$work/body"
        if (($(wc -c <"$work/body") > COMPACT_BYTES)); then
            # Compact everything but the newest KEEP_FULL_ROUNDS ledger lines
            # to a one-line pointer; the run id keeps the full detail
            # reachable in that round's workflow logs.
            total="$(grep -c . "$work/ledger" || true)"
            cut_at=$((total - KEEP_FULL_ROUNDS))
            awk -v cut="$cut_at" '
                NR <= cut {
                    if (match($0, /^r[0-9]+ \| run [^ |]+/)) {
                        print substr($0, RSTART, RLENGTH) " | compacted (full detail in run logs)"
                    } else {
                        print
                    }
                    next
                }
                { print }
            ' "$work/ledger" >"$work/ledger.compact"
            render_body "$work/ledger.compact" >"$work/body"
        fi
        cat "$work/body"
        ;;
    *)
        log_error "unknown subcommand '${cmd}' (select|render)"
        exit 2
        ;;
esac
