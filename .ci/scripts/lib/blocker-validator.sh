#!/bin/bash
# Shared BLOCKER validator used by every suppression-gated quality check.
#
# The BLOCKER convention:
#   Every numeric ID (or package name) in an allowlist / blocklist must be
#   accompanied by a "# BLOCKER: <reason>" comment line that explains
#   substantively WHY the suppression exists. A blank line resets the tracked
#   BLOCKER, so a single BLOCKER comment can cover a grouped list of related
#   IDs until the next blank line.
#
# Quality rules (enforced by validate_blocker_quality):
#   - Normalized (lowercased, trimmed, trailing punctuation stripped) length >= 30
#   - Must not match any phrase in LOW_EFFORT_BLOCKER_PATTERNS
#
# The patterns below cover npm-audit-ack-tier ("no fix", "none"), scheduling-
# ack-tier ("tbd", "todo", "later"), review-gate-style acks ("ok", "ack", see
# .ci/scripts/quality/check-review-comments.sh:17-47 for the sibling list),
# and explicit escape-hatch attempts.

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
# already auto-defers versions too fresh to install under .npmrc
# minimum-release-age, so "routine bump deferred to a dedicated dependency-bump
# PR" / "not needed by this change" is deferral-for-convenience — take the bump.
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
# Walks a file line-by-line, tracking the current contiguous comment block.
# For each bare numeric line OR package-name line (no whitespace, doesn't
# start with comment_char), it populates:
#   allowed_ref[$entry] = 1
#   blocker_ref[$entry] = <BLOCKER reason>  (empty if no BLOCKER in block)
#
# Blank lines reset the tracked BLOCKER so the next group starts fresh. Lines
# starting with `# BLOCKER: <reason>` or `// BLOCKER: <reason>` (depending on
# comment_char) capture the reason. Other comments are preserved in the block.
#
# comment_char defaults to '#'; pass '//' for JSON-sidecar-style files.
parse_blockered_list() {
    local file="$1"
    # BLOCKER: nameref-to-assoc-array pattern — shellcheck SC2178 mis-reads the alias as a string assignment
    # shellcheck disable=SC2178
    local -n _allowed_ref="$2"
    # BLOCKER: same nameref-to-assoc-array pattern as _allowed_ref above
    # shellcheck disable=SC2178
    local -n _blocker_ref="$3"
    local comment_char="${4:-#}"
    local current_blocker=""
    local line stripped

    [[ ! -f "$file" ]] && return 0

    # Build a regex that matches a BLOCKER line for the given comment char.
    # Examples: "#\s*BLOCKER:" or "//\s*BLOCKER:"
    local blocker_re="^${comment_char}[[:space:]]*BLOCKER:[[:space:]]*(.+)$"
    local comment_re="^${comment_char}"
    # The SAME pattern unanchored, for the inline `package # BLOCKER: ...` form
    # below. Held in a variable rather than written as a literal inside `[[ =~ ]]`
    # for the reason the two lines above already are: bash 3.2 cannot PARSE an
    # unquoted `(` inside a conditional regex at all. Measured on bash 3.2.0:
    #   syntax error in conditional expression: unexpected token `('
    # and the error kills the enclosing function definition, so the whole library
    # loads with no functions in it. The version guard at the top of this file
    # refuses before that happens, and this removes the second reason to.
    local inline_blocker_re="${comment_char}[[:space:]]*BLOCKER:[[:space:]]*(.+)$"

    while IFS= read -r line || [[ -n "$line" ]]; do
        # Strip surrounding whitespace
        stripped="${line#"${line%%[![:space:]]*}"}"
        stripped="${stripped%"${stripped##*[![:space:]]}"}"

        if [[ -z "$stripped" ]]; then
            current_blocker=""
        elif [[ "$stripped" =~ $blocker_re ]]; then
            current_blocker="${BASH_REMATCH[1]}"
        elif [[ "$stripped" =~ $comment_re ]]; then
            : # plain comment — preserve current_blocker
        else
            # entry line — take first whitespace-separated token as the key
            local entry="${stripped%%[[:space:]]*}"
            # strip trailing comment if present (for package # reason inline form)
            entry="${entry%%"$comment_char"*}"
            [[ -z "$entry" ]] && continue
            _allowed_ref["$entry"]=1
            _blocker_ref["$entry"]="$current_blocker"
            # For inline form like "package-name # reason", also capture
            # inline reason as blocker if no block-level one was seen.
            if [[ -z "$current_blocker" && "$stripped" =~ $inline_blocker_re ]]; then
                _blocker_ref["$entry"]="${BASH_REMATCH[1]}"
            fi
        fi
    done <"$file"
    return 0
}

# validate_blocker_quality <id> <reason> <file>
#
# Returns 0 if acceptable, 1 if low-effort (prints AI-navigable error).
validate_blocker_quality() {
    local id="$1" reason="$2" file="$3"
    local normalized
    normalized=$(echo "$reason" |
        tr '[:upper:]' '[:lower:]' |
        sed 's/^[[:space:]]*//;s/[[:space:]]*$//' |
        sed 's/[.!?,;:]*$//')

    local pattern
    for pattern in "${LOW_EFFORT_BLOCKER_PATTERNS[@]}"; do
        if [[ "$normalized" == "$pattern" ]]; then
            ci_error "Allowlist $file: BLOCKER for entry $id is a low-effort placeholder (\"$reason\")"
            echo "  Rejected because: \"$normalized\" matches the banned-phrase list — this adds no information beyond 'we suppressed it'"
            echo "  Action: write a specific reason. Good BLOCKERs cite the upstream pin, the package chain, OR why runtime isn't affected."
            echo "  Example: 'electron-builder 26.x pins plist > xmldom 0.8.x; build-time only, requires major electron migration'"
            return 1
        fi
    done

    for pattern in "${LOW_EFFORT_BLOCKER_SUBSTRINGS[@]}"; do
        if [[ "$normalized" == *"$pattern"* ]]; then
            ci_error "Allowlist $file: BLOCKER for entry $id defers a routine bump instead of justifying a hold (\"$reason\")"
            echo "  Rejected because: it contains \"$pattern\" — the upgrade blocklist is for bumps that genuinely cannot be taken now (breaking major, pin conflict, native rebuild, known regression), not for deferring a routine installable bump."
            echo "  Note: check-deps already auto-defers freshly-published versions (until the next UTC day after they age the minimum-release-age window), so there is no need to blocklist a fresh release."
            echo "  Action: TAKE the bump ('npm run check:deps -- --upgrade'), OR cite the concrete technical blocker (which package pins what, what breaks)."
            return 1
        fi
    done

    if ((${#normalized} < BLOCKER_MIN_LENGTH)); then
        ci_error "Allowlist $file: BLOCKER for entry $id is too short (${#normalized} chars, minimum $BLOCKER_MIN_LENGTH)"
        echo "  Current: \"$reason\""
        echo "  Action: a BLOCKER must explain WHO pins what, WHY the fix cannot be taken now, and ideally WHEN to revisit."
        echo "  Example: 'axios 1.15.0 pins follow-redirects <1.16.0; not runtime-exposed in CLI auth path; revisit when axios bumps'"
        return 1
    fi

    return 0
}

# verify_all_blockers <file> <blocker_var>
#
# Iterates every entry and validates its BLOCKER. Prints errors and returns
# non-zero if any entry lacks a BLOCKER OR its BLOCKER is low-effort.
verify_all_blockers() {
    local file="$1"
    # BLOCKER: nameref-to-assoc-array — shellcheck SC2178 misclassifies the alias
    # shellcheck disable=SC2178
    local -n _blocker_ref="$2"
    local id missing=0
    for id in "${!_blocker_ref[@]}"; do
        if [[ -z "${_blocker_ref[$id]}" ]]; then
            ci_error "Allowlist $file: entry $id is missing a '# BLOCKER: <reason>' comment above it"
            echo "  Action: add a line like '# BLOCKER: <who pins what / why we cannot take the fix>' immediately above $id in $file"
            missing=1
        elif ! validate_blocker_quality "$id" "${_blocker_ref[$id]}" "$file"; then
            missing=1
        fi
    done
    return $missing
}
