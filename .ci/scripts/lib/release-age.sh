#!/bin/bash
# Release-age freshness deferral -- the BASH SHIM. The rule itself lives in
# scripts/lib/release-age.ts and nowhere else.
#
# WHAT THE RULE IS (so a reader here does not have to open the other file to
# know what these functions mean):
#
#   eligibleAt = startOfNextUtcDay(publishedAt + window)   # window default 24h
#   deferred   = now < eligibleAt                          # effective age 24-48h
#
# A freshly-published dependency or advisory fix is not actionable the instant it
# ships: bumping to a version a few hours old churns the tree for nothing. Rather
# than failing a gate the moment a version crosses a flat 24h line -- which makes
# fresh releases trickle in one at a time all day -- a version is deferred until
# the next UTC midnight after it has aged the base window, so everything that
# becomes eligible on a given UTC day surfaces together at the following 00:00.
#
# The base window is read from `.npmrc` `minimum-release-age` (MINUTES). That key
# is this repo's CI-gate knob; it is NOT npm's native install guard (npm's real
# key is `min-release-age`, in DAYS, and npm ignores ours). See .npmrc.
#
# WHY THIS IS A SHIM AND NOT AN IMPLEMENTATION
# --------------------------------------------
# Until 2026-09-06 this file carried its own copy of the rule, joined to the
# TypeScript one only by two "keep the two in sync" comments -- and a comment
# cannot fail. They had in fact already drifted on the missing-.npmrc fallback
# (see release_age_window_seconds below). The TypeScript side won the collapse
# because it has six consumers to this side's two, because it is portable while
# the round-up here needed `date -u -d` (GNU-only, and these gates also run on
# developer macOS), and because this tree is the one scheduled to be ported to
# Python -- making it the source of truth would have meant doing the collapse
# twice.
#
# COST, stated plainly rather than discovered later: a delegated verdict spawns
# `tsx`, about 0.55 s. Both call sites already stand behind a network round trip
# per item (`npm view` in audit.sh, `go list -m -u` in check-go-deps.sh), and
# every answer is memoised per (publish, window) below, so a repeated epoch is
# free. A gate that asked about hundreds of distinct epochs would notice; neither
# of these does.
#
# Consumed by: .ci/scripts/security/audit.sh, .ci/scripts/quality/check-go-deps.sh.

# Guard against double-sourcing.
[[ -n "${__RELEASE_AGE_SH_SOURCED:-}" ]] && return 0
readonly __RELEASE_AGE_SH_SOURCED=1

# BASH 4.2 IS A HARD PRECONDITION OF THIS FILE, AND macOS SHIPS 3.2.57.
#
# `declare -gA __RELEASE_AGE_ELIGIBLE_CACHE=()` below needs `-A` (bash 4.0) and
# `-g` (bash 4.2). This file is reached from `.ci/scripts/security/audit.sh` and
# `.ci/scripts/quality/check-go-deps.sh`, both of which a developer runs locally,
# so 3.2 is not a hypothetical lane.
#
# WHAT BREAKS, DRIVEN ON A REAL bash 3.2.0 ON 2026-09-06. The declaration fails
# with "declare: -g: invalid option" and RETURNS ZERO, so the memo cache is never
# created. Its keys are `"<publish_epoch>:<window>"`, and an indexed array
# evaluates its subscript as ARITHMETIC, in which `:` is not an operator. Every
# read and every write then errors:
#
#   line 4: 1756000000:86400: syntax error in expression (error token is ":86400")
#   line 6: 1756000000:86400: syntax error in expression (error token is ":86400")
#
# on stderr, once per lookup, while bash 5.3.9 stores and returns 1756123456.
# The lookup MISSES every time, which silently defeats the memo the comment at
# __RELEASE_AGE_ELIGIBLE_CACHE argues for at length: `is_release_deferred` then
# spawns tsx (about 0.55 s) per call, behind a per-item network round trip, and
# the only symptom is an expression error naming neither this file nor the cache.
#
# Sibling preconditions, each with its own measured consequence: emit-advisory.sh,
# blocker-validator.sh, release-state-validator.sh.
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 || ("${BASH_VERSINFO[0]:-0}" -eq 4 && "${BASH_VERSINFO[1]:-0}" -lt 2) ]]; then
    echo "release-age.sh needs bash 4.2 or newer; this is bash ${BASH_VERSION:-unknown}." >&2
    echo "  Its eligibility memo is a global associative array (declare -gA). Before 4.2 the" >&2
    echo "  declaration fails silently, every cache key becomes an arithmetic expression, and each" >&2
    echo "  lookup prints 'syntax error in expression' while re-spawning tsx." >&2
    echo "  Fix: brew install bash, put it first on PATH, and re-run; or run the gate in the devbox." >&2
    return 1
fi

# Repo root = three levels up from .ci/scripts/lib/.
__RELEASE_AGE_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

# Default base window if .npmrc has no minimum-release-age (24h).
#
# THIS IS A CALLER POLICY, NOT PART OF THE RULE, and it is the one place the two
# implementations genuinely disagreed before the collapse: the TypeScript
# getMinReleaseAgeMs() returns 0 (deferral disabled) when the key is absent,
# while this side has always fallen back to 24h. The divergence is preserved
# here, on this side, rather than silently resolved in either direction --
# exactly the way null-handling is already documented as the caller's policy in
# scripts/lib/release-age.ts. Unreachable today in any case: check-npmrc.sh
# gates the key's presence.
readonly RELEASE_AGE_DEFAULT_WINDOW_SECONDS=86400

# The delegate, and the three runners it picks between ONCE per shell process.
#
# All three execute the SAME file, so they cannot answer differently; only the
# loader varies. Measured on 2026-09-06, same query, warm:
#
#   node --experimental-strip-types   0.11 s
#   node_modules/.bin/tsx             0.55 s
#   npx tsx                           0.98 s   (npx re-resolves the binary)
#
# The fast path is tried first and PROVEN before it is adopted: the probe below
# runs a real query and accepts the runner only if it answers with an integer.
# A future Node that renames or drops the flag therefore falls through to tsx
# instead of poisoning every verdict, which matters because the fail-closed
# policy in is_release_deferred turns an unreachable delegate into "deferred",
# and a freshness gate stuck on "deferred" is a gate that has gone quiet.
__RELEASE_AGE_RUNNER=""

__release_age_resolve_runner() {
    [[ -n "$__RELEASE_AGE_RUNNER" ]] && return 0
    local lib="$__RELEASE_AGE_REPO_ROOT/scripts/lib/release-age.ts"
    local probe=""

    if command -v node >/dev/null 2>&1; then
        probe=$(node --experimental-strip-types "$lib" --window-seconds 2>/dev/null) || probe=""
        if [[ "$probe" =~ ^[0-9]+$ ]]; then
            __RELEASE_AGE_RUNNER="node --experimental-strip-types"
            return 0
        fi
    fi
    if [[ -x "$__RELEASE_AGE_REPO_ROOT/node_modules/.bin/tsx" ]]; then
        __RELEASE_AGE_RUNNER="$__RELEASE_AGE_REPO_ROOT/node_modules/.bin/tsx"
        return 0
    fi
    __RELEASE_AGE_RUNNER="npx tsx"
}

__release_age_delegate() {
    __release_age_resolve_runner
    local lib="$__RELEASE_AGE_REPO_ROOT/scripts/lib/release-age.ts"
    # Unquoted on purpose: the runner is a two-word command in two of the three
    # cases, and every word of it is set by this file, never by input.
    # shellcheck disable=SC2086
    (cd "$__RELEASE_AGE_REPO_ROOT" && $__RELEASE_AGE_RUNNER "$lib" "$@")
}

# Memo caches, and the reason they are GLOBALS written by `__..._ensure_*`
# helpers rather than values returned from an echoing function: a caller that
# writes `x=$(f)` runs f in a SUBSHELL, so every cache line f wrote is discarded
# when the subshell exits. Written the obvious way, this file would have spawned
# tsx on every single call and the memo would have been decorative. The public
# echoing wrappers below are kept for callers and tests that want a value; the
# hot path (is_release_deferred) uses the ensure helpers directly and never
# substitutes.
declare -gA __RELEASE_AGE_ELIGIBLE_CACHE=()
__RELEASE_AGE_WINDOW_CACHE=""
__RELEASE_AGE_ELIGIBLE=""

# __release_age_ensure_window
# Sets __RELEASE_AGE_WINDOW_CACHE. Always succeeds: an unreachable delegate
# falls back to RELEASE_AGE_DEFAULT_WINDOW_SECONDS, which is this side's
# documented missing-config policy.
__release_age_ensure_window() {
    [[ -n "$__RELEASE_AGE_WINDOW_CACHE" ]] && return 0
    local answer=""
    answer=$(__release_age_delegate --window-seconds 2>/dev/null) || answer=""
    if [[ ! "$answer" =~ ^[0-9]+$ ]] || ((answer <= 0)); then
        answer="$RELEASE_AGE_DEFAULT_WINDOW_SECONDS"
    fi
    __RELEASE_AGE_WINDOW_CACHE="$answer"
}

# __release_age_ensure_eligible <publish_epoch> <window_seconds>
# Sets __RELEASE_AGE_ELIGIBLE. Returns 1 when the delegate could not answer.
__release_age_ensure_eligible() {
    local publish_epoch="$1" window="$2"
    local key="$publish_epoch:$window"

    if [[ -n "${__RELEASE_AGE_ELIGIBLE_CACHE[$key]+set}" ]]; then
        __RELEASE_AGE_ELIGIBLE="${__RELEASE_AGE_ELIGIBLE_CACHE[$key]}"
        return 0
    fi

    local answer=""
    answer=$(__release_age_delegate --eligible-epoch "$publish_epoch" "$window" 2>/dev/null) || answer=""
    if [[ ! "$answer" =~ ^-?[0-9]+$ ]]; then
        # THE DELEGATE COULD NOT ANSWER. Say so on stderr rather than inventing a
        # number: a silent fallback here would make every version look eligible
        # (or every one deferred, depending on the sentinel chosen), and a
        # freshness gate that quietly stops deferring is exactly the shape this
        # repo keeps getting caught by. The caller's own fail-closed policy then
        # applies -- see is_release_deferred.
        echo "release-age: could not reach scripts/lib/release-age.ts (tsx missing or failing); treating '$publish_epoch' as DEFERRED" >&2
        __RELEASE_AGE_ELIGIBLE=""
        return 1
    fi
    __RELEASE_AGE_ELIGIBLE_CACHE[$key]="$answer"
    __RELEASE_AGE_ELIGIBLE="$answer"
}

# release_age_window_seconds
# Prints the base freshness window in seconds. Reads `minimum-release-age`
# (minutes) from .npmrc via the shared implementation; falls back to
# RELEASE_AGE_DEFAULT_WINDOW_SECONDS when the key is absent or the delegate
# cannot run.
release_age_window_seconds() {
    __release_age_ensure_window
    echo "$__RELEASE_AGE_WINDOW_CACHE"
}

# release_eligible_epoch <publish_epoch> [window_seconds]
# Prints the epoch (UTC seconds) at which a version published at <publish_epoch>
# becomes eligible: 00:00:00 UTC of the day AFTER (publish + window). Exits
# non-zero, having said why on stderr, when the delegate cannot answer.
release_eligible_epoch() {
    local publish_epoch="$1" window="${2:-}"
    if [[ -z "$window" ]]; then
        __release_age_ensure_window
        window="$__RELEASE_AGE_WINDOW_CACHE"
    fi
    __release_age_ensure_eligible "$publish_epoch" "$window" || return 1
    echo "$__RELEASE_AGE_ELIGIBLE"
}

# is_release_deferred <publish_epoch> [now_epoch] [window_seconds]
# Exit 0 (deferred) when now < eligibleAt; exit 1 (eligible/installable) otherwise.
# An empty/unparseable publish_epoch is treated as DEFERRED (fail-closed): a
# lookup hiccup must never turn into a false "must upgrade" gate failure. The
# same fail-closed rule covers a delegate that cannot run, which
# __release_age_ensure_eligible has already reported loudly on stderr.
is_release_deferred() {
    local publish_epoch="$1"
    local now="${2:-}" window="${3:-}"
    if [[ -z "$publish_epoch" || ! "$publish_epoch" =~ ^[0-9]+$ ]]; then
        return 0
    fi
    [[ -z "$now" ]] && now=$(date -u +%s)
    if [[ -z "$window" ]]; then
        __release_age_ensure_window
        window="$__RELEASE_AGE_WINDOW_CACHE"
    fi
    __release_age_ensure_eligible "$publish_epoch" "$window" || return 0
    ((now < __RELEASE_AGE_ELIGIBLE))
}
