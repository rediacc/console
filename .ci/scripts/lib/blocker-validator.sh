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
            if [[ -z "$current_blocker" && "$stripped" =~ ${comment_char}[[:space:]]*BLOCKER:[[:space:]]*(.+)$ ]]; then
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
