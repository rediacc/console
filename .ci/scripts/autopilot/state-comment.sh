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
#          [--ruled-out <line>] [--decision <line>] \
#          [--campaign open|closed|none] [--model <id>] [--rounds-max <n>]
#       Rebuilds the full body: header, state line, then the three sections
#       carried over from --body (absent/empty file = fresh comment) plus the
#       appended lines. Every appended line is hard-capped at 400 chars.
#       Above 55 KB, ledger rounds older than the last 8 compact to a
#       one-line pointer (full detail persists in that round's workflow
#       logs, reachable by run id).
#   fields --body <file>
#       Prints {"campaign":...,"model":...,"rounds_max":N} read back from the
#       metadata line. autopilot-gate.sh calls THIS rather than re-parsing the
#       line itself, so the format has exactly one reader and one writer.
#
# THE CAMPAIGN FIELDS (campaign / model / rounds_max) are the dispatch-armed
# loop's memory. A `gh workflow run Autopilot -f pr_number=N` is the arming
# act; this comment is where that decision persists, so the workflow_run
# rounds that follow can continue the campaign with the model and round cap
# the operator chose. They ride the metadata line rather than a new section
# because the carry-over parser below deliberately DROPS every line it does
# not recognise (anti-tamper), and the metadata line is re-rendered from
# validated values on every round rather than copied forward verbatim.
#
# EVERY carried-over value is re-validated on read AND on write
# (normalize_field): campaign is one of three literals, model matches a tight
# identifier shape, rounds_max is a small integer. Anything else collapses to
# its sentinel (none/none/0). The state comment is bot-authored and
# author-checked by `select`, so this is defence in depth rather than the
# primary control -- but these values flow into a model selection and a round
# cap, and a surprise value must fail closed rather than propagate.
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

# normalize_field <campaign|model|rounds_max> <value> - collapse anything
# unrecognised to the field's sentinel. Applied to values read back from a
# previous body AND to values passed in as arguments, so there is no path by
# which an unvalidated string reaches the rendered line.
normalize_field() {
    local name="$1" value="${2:-}"
    value="${value//[[:space:]]/}"
    case "$name" in
        campaign) [[ "$value" == "open" || "$value" == "closed" ]] || value="none" ;;
        model) [[ "$value" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || value="none" ;;
        rounds_max) [[ "$value" =~ ^[0-9]{1,4}$ ]] || value="0" ;;
        *)
            log_error "normalize_field: unknown field '$name'"
            exit 2
            ;;
    esac
    printf '%s' "$value"
}

# state_field <body-file> <field> - read one campaign field from the FIRST
# metadata line of a rendered body. Only the first `state: ` line counts: a
# body carrying a second one (appended by anything other than this script) can
# never win, which is the same first-match discipline `select` applies to
# comments.
state_field() {
    local file="${1:-}" name="$2" raw=""
    if [[ -n "$file" && -s "$file" ]]; then
        raw="$(awk -v f="$name" '
            /^state: / {
                n = split($0, parts, / \| /)
                for (i = 1; i <= n; i++) {
                    if (index(parts[i], f ": ") == 1) { print substr(parts[i], length(f) + 3) }
                }
                exit
            }
        ' "$file")"
    fi
    normalize_field "$name" "$raw"
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
            log_error "usage: state-comment.sh render --body <file> --state <s> --round <r/cap> --head <sha> --last-run <id/attempt handled> [--ledger <line>] [--ruled-out <line>] [--decision <line>] [--campaign <c>] [--model <id>] [--rounds-max <n>]"
            exit 2
        }

        # Campaign fields: an explicit argument wins, otherwise the value
        # carried in the previous body survives. That is what makes a round
        # that has nothing to say about the campaign (a label-armed round,
        # say) preserve it instead of silently closing it.
        CAMPAIGN="$(normalize_field campaign "${ARG_CAMPAIGN:-$(state_field "$BODY" campaign)}")"
        MODEL="$(normalize_field model "${ARG_MODEL:-$(state_field "$BODY" model)}")"
        ROUNDS_MAX="$(normalize_field rounds_max "${ARG_ROUNDS_MAX:-$(state_field "$BODY" rounds_max)}")"

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
            # Not cap_line'd, and it does not need to be: every field here is
            # either a workflow-controlled short value or normalized above, so
            # this line cannot grow with the ledger the way an appended line can.
            printf 'state: %s | round: %s | head: %s | last_run: %s | campaign: %s | model: %s | rounds_max: %s\n' \
                "$STATE" "$ROUND" "$HEAD_SHA" "$LAST_RUN" "$CAMPAIGN" "$MODEL" "$ROUNDS_MAX"
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
    fields)
        BODY="${ARG_BODY:-}"
        [[ -n "$BODY" ]] || {
            log_error "usage: state-comment.sh fields --body <file>"
            exit 2
        }
        # An ABSENT body is not an error: no state comment yet is the normal
        # first round, and it must read as "no campaign" rather than as a
        # wiring failure. A body that exists but carries no metadata line
        # reads the same way, because every field falls back to its sentinel.
        jq -cn \
            --arg campaign "$(state_field "$BODY" campaign)" \
            --arg model "$(state_field "$BODY" model)" \
            --argjson rounds_max "$(state_field "$BODY" rounds_max)" \
            '{campaign: $campaign, model: $model, rounds_max: $rounds_max}'
        ;;
    *)
        log_error "unknown subcommand '${cmd}' (select|render|fields)"
        exit 2
        ;;
esac
