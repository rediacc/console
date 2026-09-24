#!/bin/bash
# The BLOCKER convention, for bash gates. A CLIENT of the canonical
# implementation, not a second copy of it.
#
# The BLOCKER convention:
#   Every numeric ID (or package name) in an allowlist / blocklist must be
#   accompanied by a "# BLOCKER: <reason>" comment line that explains
#   substantively WHY the suppression exists. A blank line resets the tracked
#   BLOCKER, so a single BLOCKER comment can cover a grouped list of related
#   IDs until the next blank line.
#
# THIS FILE STOPPED BEING AN IMPLEMENTATION ON 2026-09-09. The grammar, the
# banned-phrase tables, the 30-character floor and all four message bodies now
# live in .ci/rediacc_ci/core/allowlist.py, which is the same module
# scripts/lib/blocker-validator.ts reads. parse_blockered_list and
# validate_blocker_quality below are transports; they decide nothing.
#
# There is deliberately NO bash fallback, for the reason age-check.sh states in
# the same words: a fallback is a second implementation, and the thing being
# decided here is whether a suppression is allowed to exist. Failing to load is
# louder than answering wrongly, and a suppression validator that quietly stops
# validating looks exactly like a tree with no bad suppressions in it.
#
# WHAT DID NOT MOVE, and why each one stayed:
#
#   emit_advisory / ci_error   the ::error:: / ✗ split is a separate library with
#                              its own contract; the port splits the DECISION
#                              (Python) from the EMISSION (here).
#   the two phrase ARRAYS      see the long note above them. They are a MIRROR
#                              that a gate proves equal to the canonical, kept
#                              because a registered gate test reads them out of
#                              this file's TEXT.
#   the nameref API            five gates pass associative arrays in and out, so
#                              the bash 4.3 precondition below is unchanged.

# Guard against double-sourcing.
[[ -n "${__BLOCKER_VALIDATOR_SH_SOURCED:-}" ]] && return 0
readonly __BLOCKER_VALIDATOR_SH_SOURCED=1

# BASH 4.3 IS A HARD PRECONDITION OF THIS FILE, AND macOS SHIPS 3.2.57.
#
# `local -n` (parse_blockered_list:83 and :86, verify_all_blockers:178) is a
# NAMEREF, which arrived in bash 4.3. On bash 3.2 `local -n _allowed_ref="$2"`
# prints "local: -n: invalid option", RETURNS ZERO, and the function then runs on
# with the alias unset. Measured on a real bash 3.2.0 on 2026-09-06:
#
#   $ bash-3.2 -c 'f(){ local -n r="$1"; echo "${r}"; }; x=hi; f x'
#   local: -n: invalid option        (stderr)
#   (blank line on stdout)           exit 0
#
# THE MEASURED CONSEQUENCE IS AN ALLOWLIST OF ZERO ENTRIES. Driving the real file
# on 3.2 with a one-entry allowlist carrying a valid BLOCKER, the whole library
# failed to load and the caller printed `entries=0`, exit 0, while bash 5.3.9
# printed `entries=1` and the reason text. A suppression gate whose allowlist
# parses to nothing checks nothing, and its output is indistinguishable from a
# tree with no suppressions in it.
#
# THE GUARD SITS ABOVE THE `source` LINE BELOW ON PURPOSE. Bash reads a sourced
# file command by command, so a refusal here runs BEFORE anything further down is
# parsed -- verified against this file, which is a SYNTAX error on 3.2 as well as
# a semantic one (see the note at parse_blockered_list's inline-regex branch).
# Without the guard first, 3.2 reports three parser errors naming a line number
# and then "parse_blockered_list: command not found", which names neither bash
# nor the version.
#
# Sibling preconditions, each with its own measured consequence:
# emit-advisory.sh (which this file sources), release-age.sh,
# release-state-validator.sh.
if [[ "${BASH_VERSINFO[0]:-0}" -lt 4 || ("${BASH_VERSINFO[0]:-0}" -eq 4 && "${BASH_VERSINFO[1]:-0}" -lt 3) ]]; then
    echo "blocker-validator.sh needs bash 4.3 or newer; this is bash ${BASH_VERSION:-unknown}." >&2
    echo "  It passes allowlist tables by nameref (local -n), which arrived in 4.3. On 3.2 the" >&2
    echo "  namerefs fail silently and every allowlist parses to ZERO entries, so a suppression" >&2
    echo "  gate verifies nothing and still exits 0." >&2
    echo "  Fix: brew install bash, put it first on PATH, and re-run; or run the gate in the devbox." >&2
    return 1
fi

# shellcheck source=emit-advisory.sh
# BLOCKER: required for ci_error / log_error helpers used by this library
source "$(dirname "${BASH_SOURCE[0]}")/emit-advisory.sh"

# THE CANONICAL IMPLEMENTATION, and the two ways this file refuses to run without
# it. Same shape as .ci/scripts/lib/age-check.sh, for the same measured reason:
# a missing dependency must be a loud failure with the fix in the message, never
# a degraded answer. REDIACC_CI_ROOT is the package's single environment
# override (.ci/rediacc_ci/paths.py) and is honoured here so a planted-defect
# control can point this at a scratch tree.
__blocker_root="${REDIACC_CI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
if [[ ! -d "$__blocker_root/.ci/rediacc_ci/core" ]]; then
    echo "blocker-validator.sh: cannot find rediacc_ci under '$__blocker_root/.ci' (set REDIACC_CI_ROOT)" >&2
    unset __blocker_root
    return 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "blocker-validator.sh: python3 is required; the BLOCKER rule lives in rediacc_ci.core.allowlist" >&2
    unset __blocker_root
    return 1
fi
readonly BLOCKER_VALIDATOR_CI_DIR="$__blocker_root/.ci"
unset __blocker_root

# ASCII 30, RECORD SEPARATOR. `verify-rows` prefixes each failure block with
# RS followed by the block's LINE COUNT, and this file then reads exactly that
# many lines. A counted frame rather than a sentinel line, because a sentinel
# can be forged by a BLOCKER reason and a count cannot.
readonly BLOCKER_VALIDATOR_RS=$'\x1e'

# PYTHONPATH rather than `cd`: every caller passes list paths relative to ITS
# OWN cwd, and changing directory here would resolve them against the wrong tree
# -- which, per the canonical module's own docstring, is indistinguishable from
# an empty allowlist.
_blocker_py() {
    PYTHONPATH="$BLOCKER_VALIDATOR_CI_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m rediacc_ci.core.allowlist "$@"
}

# THESE TWO ARRAYS ARE A MIRROR, NOT THE RULE. Nothing in this file reads them
# any more: validate_blocker_quality asks rediacc_ci.core.allowlist. They survive
# because .ci/rediacc_ci/tests/gates/test_gate_breakpoint_portability.py parses
# LOW_EFFORT_BLOCKER_PATTERNS out of this file's TEXT to prove the vendored
# breakpoint copy is a subset of it, and deleting the array would delete that
# registered assertion rather than satisfy it.
#
# A MIRROR THAT NOTHING COMPARES IS JUST A SECOND OPINION, so it is compared:
# .ci/rediacc_ci/tests/test_blocker_implementations.py asserts set EQUALITY in
# both directions against LOW_EFFORT_PHRASES / LOW_EFFORT_SUBSTRINGS /
# MIN_REASON_LENGTH, which is the direction the goldens structurally cannot see
# (they generate their corpus FROM the Python list, so a phrase present here and
# absent there produces no test case at all). Edit the canonical, then re-run
# that suite; it will name the difference.
readonly LOW_EFFORT_BLOCKER_PATTERNS=(
    # npm-audit ack-tier phrases
    "no fix" "no fix available" "no fix yet" "no upstream fix" "no fix published"
    "no patch" "no patch yet" "no patch available"
    "none" "n/a" "na" "empty" "-"
    # scheduling ack-tier
    "tbd" "wip" "fixme" "todo" "later" "fix later" "will fix" "pending"
    "skip" "skipping" "skipped" "ignore" "ignoring" "ignored"
    "unknown" "unknown reason" "idk" "dunno" "whatever"
    # review-gate-style ack phrases
    "ok" "okay" "ack" "acknowledged" "noted" "done" "fixed" "applied"
    "addressed" "updated" "changed" "understood"
    # explicit escape-hatch attempts
    "escape" "escape hatch" "suppressed" "suppress" "bypass" "override"
    "upstream issue" "transitive" "dev dep" "dev only"
)

# Substring-matched (not exact-match) phrases that signal can-kicking a routine,
# installable bump for convenience rather than a genuine technical hold. The
# upgrade blocklist is only for bumps that genuinely cannot be taken now
# (breaking major, pin conflict, native rebuild, known regression). check-deps
# already auto-defers versions too fresh under the .ci/config/release-age.json
# window, so "routine bump deferred to a dedicated dependency-bump
# PR" / "not needed by this change" is deferral-for-convenience, so take the bump.
# Legitimate major-migration holds read differently (e.g. "dedicated lint-tooling
# PR", "dedicated PR that exercises the email flows") and are NOT matched here.
readonly LOW_EFFORT_BLOCKER_SUBSTRINGS=(
    "deferred to a dedicated dependency-bump pr"
    "not needed by this change"
    "not needed in this change"
    "not needed for this change"
    "to keep this merge focused"
    "to keep this change focused"
    "to keep this pr focused"
)

readonly BLOCKER_MIN_LENGTH=30

# parse_blockered_list <file> <allowed_var> <blocker_var> [<comment_char>]
#
# Populates, for every entry line in <file>:
#   allowed_ref[$entry] = 1
#   blocker_ref[$entry] = <BLOCKER reason>  (empty if no BLOCKER in the group)
#
# Blank lines reset the tracked BLOCKER so the next group starts fresh. Lines
# starting with `# BLOCKER: <reason>` or `// BLOCKER: <reason>` (depending on
# comment_char) capture the reason. Other comments preserve it.
#
# comment_char defaults to '#'; pass '//' for JSON-sidecar-style files.
#
# THE GRAMMAR IS rediacc_ci.core.allowlist.parse_text, and the projection is
# `pairs`: deduplicated entry -> reason, last write wins, which is exactly what
# an associative array can hold and therefore exactly what this function used to
# compute. That equivalence is proved over a frozen corpus of every real list in
# the tree by .ci/rediacc_ci/tests/test_core_allowlist.py, which compares BYTES.
#
# A MISSING FILE STILL RETURNS 0 WITH EMPTY TABLES. That is this function's
# historical contract and five gates rely on it; the canonical calls it
# `missing_ok=True` and refuses to make it the default, so the permissiveness is
# spelled out here, at the call site, where a reviewer sees it.
parse_blockered_list() {
    local file="$1"
    # BLOCKER: nameref-to-assoc-array pattern; shellcheck SC2178 mis-reads the alias as a string assignment
    # shellcheck disable=SC2178
    local -n _allowed_ref="$2"
    # BLOCKER: same nameref-to-assoc-array pattern as _allowed_ref above
    # shellcheck disable=SC2178
    local -n _blocker_ref="$3"
    local comment_char="${4:-#}"
    local rows rc=0 key value

    [[ ! -f "$file" ]] && return 0

    rows="$(_blocker_py pairs "$file" "$comment_char")" || rc=$?
    if ((rc != 0)); then
        ci_error "blocker-validator: rediacc_ci.core.allowlist could not parse $file (exit $rc)"
        echo "  This is a broken reader, not an empty allowlist. Refusing to report zero entries." >&2
        return 1
    fi

    # IFS=TAB and a two-variable read: the key is the first WHITESPACE-separated
    # token of the entry line and therefore cannot contain a TAB, so everything
    # after the first one is the reason, tabs and all.
    while IFS=$'\t' read -r key value; do
        [[ -z "$key" ]] && continue
        _allowed_ref["$key"]=1
        _blocker_ref["$key"]="$value"
    done <<<"$rows"
    return 0
}

# _blocker_emit_message <one message, newline separated>
#
# The stream split, which is the only part of the message contract that stayed in
# bash: the FIRST line through ci_error, which is what turns it into a GitHub
# annotation under CI, the rest as plain echo.
_blocker_emit_message() {
    local first=1 line
    while IFS= read -r line; do
        if ((first)); then
            ci_error "$line"
            first=0
        else
            echo "$line"
        fi
    done <<<"$1"
}

# _blocker_emit <canonical stdout>
#
# Replays a counted RS-framed failure stream from `verify-rows`. THE FRAME IS A
# COUNT, not a sentinel line: a sentinel can be forged by a BLOCKER reason, which
# is text somebody writes, and a forged frame would let one rejection hide inside
# another rejection's message.
_blocker_emit() {
    local stream="$1"
    local line count index frames=0
    while IFS= read -r line; do
        if [[ "$line" != "$BLOCKER_VALIDATOR_RS"* ]]; then
            ci_error "blocker-validator: unframed output from rediacc_ci.core.allowlist: $line"
            return 1
        fi
        count="${line#"$BLOCKER_VALIDATOR_RS"}"
        frames=$((frames + 1))
        index=0
        while ((index < count)); do
            IFS= read -r line || break
            if ((index == 0)); then
                ci_error "$line"
            else
                echo "$line"
            fi
            index=$((index + 1))
        done
    done <<<"$stream"
    if ((frames == 0)); then
        ci_error "blocker-validator: the canonical validator reported a failure but emitted no message"
        return 1
    fi
    return 0
}

# validate_blocker_quality <id> <reason> <file>
#
# Returns 0 if acceptable, 1 if low-effort (prints an AI-navigable error).
# The rule and the words are rediacc_ci.core.allowlist.validate_reason's.
validate_blocker_quality() {
    local id="$1" reason="$2" file="$3"
    local out rc=0
    out="$(_blocker_py reason "$id" "$reason" "$file")" || rc=$?
    case "$rc" in
        0) return 0 ;;
        1) ;;
        *)
            # EXIT 2 IS A USAGE ERROR, NOT A VERDICT, and folding it into "reject"
            # would turn a broken call into a finding about somebody's allowlist.
            ci_error "blocker-validator: rediacc_ci.core.allowlist reason exited $rc for entry $id"
            echo "  $out" >&2
            return 1
            ;;
    esac
    # UNFRAMED, and deliberately so. The `reason` verb answers about ONE reason
    # and prints the message raw; only the batch verb frames, because only the
    # batch verb has more than one message to delimit. Feeding this to
    # `_blocker_emit` was the first cut's bug and it did not fail quietly: the
    # gate printed "unframed output from rediacc_ci.core.allowlist" in place of
    # every rejection it was asked to explain, and
    # test_core_allowlist::test_bash_reason_validator_agrees_with_python_on_every_case
    # caught it on the digest of the message rather than on the verdict.
    _blocker_emit_message "$out"
    return 1
}

# verify_all_blockers <file> <blocker_var>
#
# Iterates every entry and validates its BLOCKER. Prints errors and returns
# non-zero if any entry lacks a BLOCKER OR its BLOCKER is low-effort.
#
# ONE python start for the whole table, not one per entry. The first cut of this
# delegation spawned an interpreter inside the loop; measured on
# .ci/policy/.profiler-coverage-allowlist (71 entries) that is 71 starts, and the
# batch form below took the same call from 3.4s to 0.06s.
#
# THE ITERATION ORDER IS STILL THE ASSOCIATIVE ARRAY'S, so the output order does
# not move: the rows are handed over in `"${!_blocker_ref[@]}"` order and come
# back in the same one.
verify_all_blockers() {
    local file="$1"
    # BLOCKER: nameref-to-assoc-array; shellcheck SC2178 misclassifies the alias
    # shellcheck disable=SC2178
    local -n _blocker_ref="$2"
    local id rows="" out rc=0

    # `${!_blocker_ref[@]}` AND NOT `${#_blocker_ref[@]}`, which is not a style
    # preference. `declare -A X` with NO initialiser leaves the array genuinely
    # unset until something is assigned, and reading its LENGTH through a nameref
    # then trips `set -u`. Measured on bash 5.3.9, 2026-09-09:
    #
    #   $ bash -c 'set -eu; declare -A E; f(){ local -n r="$1"; echo ${#r[@]}; }; f E'
    #   bash: line 1: r: unbound variable          exit 1
    #   $ ... for k in "${!r[@]}"; do ...          n=0, exit 0
    #
    # The first cut of this function opened with a `((${#_blocker_ref[@]} == 0))`
    # early return as an anti-vacuity guard and killed
    # .ci/scripts/security/audit.sh on the spot: `declare -A ALLOWED_DEV
    # BLOCKER_DEV` at audit.sh:52 has no initialiser and `.audit-allowlist` is
    # empty, so the guard fired on the one input it was written for. Emptiness is
    # decided from `rows` below instead, after the safe expansion.
    for id in "${!_blocker_ref[@]}"; do
        rows+="$id"$'\t'"${_blocker_ref[$id]}"$'\n'
    done
    [[ -z "$rows" ]] && return 0

    out="$(printf '%s' "$rows" | _blocker_py verify-rows "$file")" || rc=$?
    case "$rc" in
        0) return 0 ;;
        1) ;;
        *)
            ci_error "blocker-validator: rediacc_ci.core.allowlist verify-rows exited $rc for $file"
            echo "  $out" >&2
            return 1
            ;;
    esac
    _blocker_emit "$out"
    return 1
}
