#!/bin/bash
# Age-based rot detection for suppression entries.
#
# Every allowlist / blocklist entry carries an implicit re-review cadence:
#   - <= AGE_WARN_DAYS:  silently accepted
#   - >  AGE_WARN_DAYS:  warn (reminder to re-evaluate)
#   - >  AGE_FAIL_DAYS:  fail (the suppression has outlived any reasonable
#                        staleness window; either refresh the BLOCKER with a
#                        new date-stamped comment or take the fix)
#
# Uses git log to determine when a line was added. If the file is untracked
# or git history is unavailable, entry_age_days returns 0 (treat as fresh).

# Guard against double-sourcing.
[[ -n "${__AGE_CHECK_SH_SOURCED:-}" ]] && return 0
readonly __AGE_CHECK_SH_SOURCED=1

# shellcheck source=emit-advisory.sh
# BLOCKER: required for ci_error / ci_warn used by this library's public API
source "$(dirname "${BASH_SOURCE[0]}")/emit-advisory.sh"

readonly AGE_WARN_DAYS="${AGE_WARN_DAYS:-180}"
readonly AGE_FAIL_DAYS="${AGE_FAIL_DAYS:-365}"

# entry_age_days <file> <pattern>
#
# Returns the number of days since the line matching <pattern> was first
# introduced in <file>'s git history. Prints a single integer on stdout.
# Returns 0 (fresh) if git log fails or the line is untracked.
#
# <pattern> is a grep-style regex passed to `git log -S`, which finds the
# commit where the pattern was added. This is more reliable than git blame
# for files where lines have been renumbered.
entry_age_days() {
    local file="$1" pattern="$2"
    # Find the commit that first added the pattern.
    local commit_date
    commit_date=$(git log --diff-filter=A --format=%ct --follow -S "$pattern" -- "$file" 2>/dev/null | tail -1)
    if [[ -z "$commit_date" ]]; then
        echo 0
        return 0
    fi
    local now_epoch=$(($(date +%s)))
    echo $(((now_epoch - commit_date) / 86400))
    return 0
}

# check_entry_age <file> <entry> <id> [<name>]
#
# Emits warn / error via emit_advisory based on entry age.
# Returns 0 if fresh or warn-only; returns 1 if age exceeds AGE_FAIL_DAYS.
# Caller should aggregate returns and fail the script on any non-zero.
#
# <entry>  literal text to search for in file's git history
# <id>     advisory / package identifier for emit_advisory
# <name>   optional display name
check_entry_age() {
    local file="$1"
    local entry="$2"
    local id="$3"
    local name="${4:-$id}"
    local age
    age=$(entry_age_days "$file" "$entry")
    if ((age > AGE_FAIL_DAYS)); then
        emit_advisory error "$id" "$name" \
            "suppression entry is $age days old (>$AGE_FAIL_DAYS) — yearly re-review required" \
            "verify the BLOCKER reason is still valid; either refresh the entry OR take the fix"
        return 1
    elif ((age > AGE_WARN_DAYS)); then
        emit_advisory warn "$id" "$name" \
            "suppression entry is $age days old (>$AGE_WARN_DAYS) — due for re-review"
    fi
    return 0
}
