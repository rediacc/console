#!/bin/bash
# Build the review payload the model is allowed to see, from the raw review
# threads the gate fetched. PURE: one JSON file in, one JSON object out, no
# network, no git, no env. That purity is the point -- this script decides
# WHOSE TEXT REACHES THE MODEL, which is the mitigation for 03-v2-autonomy.md
# section 6's residual 1, and a security decision that cannot be exercised
# offline is a security decision nobody has tested.
#
# THE FILTER IS ON THE ROOT COMMENT'S AUTHOR, and only the root's. A review
# thread is STARTED by whoever raised the finding; anyone with a GitHub
# account can REPLY into a thread on a public repo. So:
#   - a thread whose ROOT author does not match is dropped whole. An outsider
#     cannot get text in front of the model by opening a thread.
#   - a matching thread keeps ALL its comments, replies included. Replies are
#     carried deliberately, as DATA: an unresolved finding often gets its real
#     detail in a follow-up, and the prompt already states that every quoted
#     snippet is data about the code rather than an instruction. What an
#     attacker can achieve by replying is putting untrusted prose inside a
#     trusted thread -- which is exactly what the prompt's data framing and
#     the harness's no-write-token invariant are there to absorb.
# Resolved and outdated threads are dropped: neither is outstanding work, and
# both are pure round cost.
#
# Usage:
#   review-payload.sh --threads <file> [--author-filter <substring>]
#                     [--max-bytes <n>] [--out <file>]
#
# <file> is fetch-review-threads.sh's output: a JSON array of
# {id, isResolved, isOutdated, path, line, comments:{nodes:[{databaseId, body,
# author:{login}}]}}.
#
# Output (stdout, or --out):
#   {"threads":[{id, path, line, comments:[{author, body, id}]}],
#    "kept":N, "dropped":N, "bytes":N}
# `dropped` counts threads shed by the byte cap ONLY, and it is reported
# rather than swallowed: a round that silently saw half the findings would
# "address every finding" and leave the rest to be rediscovered.
#
# Exit: 0 built, 2 usage/parse error. A payload with zero threads is a valid
# payload, not an error.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
THREADS="${ARG_THREADS:-}"
# `${x-default}`, NOT `${x:-default}`: an explicitly EMPTY --author-filter is a
# wiring bug, and `:-` would quietly substitute the safe default and make the
# guard below unreachable -- a check that cannot fire.
AUTHOR_FILTER="${ARG_AUTHOR_FILTER-github-actions}"
MAX_BYTES="${ARG_MAX_BYTES:-49152}"
OUT="${ARG_OUT:-}"

[[ -n "$THREADS" ]] || {
    log_error "usage: review-payload.sh --threads <file> [--author-filter <substring>] [--max-bytes <n>] [--out <file>]"
    exit 2
}
require_file "$THREADS"
[[ "$MAX_BYTES" =~ ^[0-9]{1,8}$ ]] || {
    log_error "--max-bytes must be a number, got '$MAX_BYTES'"
    exit 2
}
[[ -n "$AUTHOR_FILTER" ]] || {
    log_error "--author-filter must not be empty: an empty filter would match every author, which is the opposite of filtering"
    exit 2
}
jq -e 'type == "array"' "$THREADS" >/dev/null 2>&1 || {
    log_error "threads fixture is not a JSON array: $THREADS"
    exit 2
}

# The byte cap sheds OLDEST-FIRST. GitHub returns review threads in creation
# order, so the newest findings are the ones a round can still act on; an
# older thread that has survived several rounds unaddressed is the better
# thing to lose, and it is reported as lost rather than dropped in silence.
payload="$(jq -c --arg af "$AUTHOR_FILTER" --argjson max "$MAX_BYTES" '
    [ .[]
      | select((.isResolved // false) == false and (.isOutdated // false) == false)
      | select((((.comments.nodes // [])[0].author.login) // "") | contains($af))
      | {
          id: .id,
          path: (.path // ""),
          line: (.line // null),
          comments: [ (.comments.nodes // [])[]
                      | {author: ((.author.login) // "unknown"),
                         body: ((.body) // ""),
                         id: (.databaseId // null)} ]
        }
    ]
    | . as $kept
    | reduce range(0; ($kept | length)) as $i ({threads: $kept, dropped: 0};
        if ((.threads | tojson | length) <= $max) then .
        else {threads: (.threads[1:]), dropped: (.dropped + 1)} end)
    | {threads: .threads,
       kept: (.threads | length),
       dropped: .dropped,
       bytes: (.threads | tojson | length)}
' "$THREADS")"

if [[ -n "$OUT" ]]; then
    printf '%s\n' "$payload" >"$OUT"
else
    printf '%s\n' "$payload"
fi

dropped="$(jq -r '.dropped' <<<"$payload")"
if [[ "$dropped" != "0" ]]; then
    log_warn "review payload capped at ${MAX_BYTES} bytes: $dropped oldest thread(s) dropped, $(jq -r '.kept' <<<"$payload") kept"
else
    log_info "review payload: $(jq -r '.kept' <<<"$payload") thread(s), $(jq -r '.bytes' <<<"$payload") bytes, rooted by an author matching '$AUTHOR_FILTER'"
fi
