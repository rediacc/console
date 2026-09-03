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
# Uses git log to determine when a line was added.
#
# WHY THIS REFUSES RATHER THAN GUESSING, measured 2026-09-03. `git log
# --diff-filter=A` on a TRUNCATED history attributes every line present at the
# graft boundary to the boundary commit, so an old suppression reports as new.
# The same real entry, github.com/docker/docker in .go-deps-upgrade-blocklist:
#
#     full clone       195 days  (added 2026-02-20)
#     truncated clone    2 days  (added 2026-09-01)
#
# AGE_WARN_DAYS is 180, so on the truncated clone that entry silently stops
# warning, and at AGE_FAIL_DAYS=365 it could never fail. A liveness gate whose
# whole job is expiring stale suppressions then expires nothing and says so in
# green. Sibling of the same defect in check-plan-housekeeping.sh, found by
# sweeping for it after that one landed.
#
# So entry_age_days prints -1 for CANNOT-VERIFY, and check_entry_age turns that
# into a refusal in CI and a warning locally -- never into "fresh".

# Guard against double-sourcing.
[[ -n "${__AGE_CHECK_SH_SOURCED:-}" ]] && return 0
readonly __AGE_CHECK_SH_SOURCED=1

# shellcheck source=emit-advisory.sh
# BLOCKER: required for ci_error / ci_warn used by this library's public API
source "$(dirname "${BASH_SOURCE[0]}")/emit-advisory.sh"

readonly AGE_WARN_DAYS="${AGE_WARN_DAYS:-180}"
readonly AGE_FAIL_DAYS="${AGE_FAIL_DAYS:-365}"

# _age_grafts_file
#
# Path to a NON-EMPTY graft list, or empty when history is complete.
# `git rev-parse --is-shallow-repository` is deliberately not the test: it
# answers on the EXISTENCE of .git/shallow, and `git fetch --unshallow` against
# a partial clone leaves that file behind empty. What corrupts an age is a
# GRAFT, so the graft list is what gets asked. (Same reasoning, same words, as
# check-plan-housekeeping.sh -- and if one of them is ever wrong, both are.)
_age_grafts_file() {
    local f
    f="$(git rev-parse --git-path shallow 2>/dev/null)" || return 0
    [[ -n "$f" && -s "$f" ]] && echo "$f"
    return 0
}

# entry_age_days <file> <pattern>
#
# Days since the line matching <pattern> was first introduced in <file>'s git
# history. Prints a single integer on stdout, or -1 for CANNOT VERIFY.
#
# -1 is printed when the answer would be fiction: the pattern resolves to no
# commit at all, or it resolves to a graft boundary, which reports the
# boundary's date rather than the line's. Callers must not treat -1 as an age.
#
# <pattern> is a grep-style regex passed to `git log -S`, which finds the
# commit where the pattern was added. This is more reliable than git blame
# for files where lines have been renumbered.
entry_age_days() {
    local file="$1" pattern="$2"
    # Find the commit that first added the pattern. %H alongside %ct so the
    # commit can be tested against the graft list.
    local line commit_sha commit_date grafts
    line=$(git log --diff-filter=A --format='%H %ct' --follow -S "$pattern" -- "$file" 2>/dev/null | tail -1)
    commit_sha="${line%% *}"
    commit_date="${line##* }"
    if [[ -z "$line" || -z "$commit_date" ]]; then
        # No commit found. On a complete history that means the line is
        # untracked and genuinely new; on a truncated one it means the
        # introducing commit was cut away, which is not the same thing.
        grafts="$(_age_grafts_file)"
        if [[ -n "$grafts" ]]; then
            echo -1
        else
            echo 0
        fi
        return 0
    fi
    grafts="$(_age_grafts_file)"
    if [[ -n "$grafts" ]] && grep -qxF "$commit_sha" "$grafts" 2>/dev/null; then
        echo -1
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
    if ((age < 0)); then
        # CANNOT VERIFY. In CI that is a refusal: this gate's entire purpose is
        # expiring stale suppressions, and a truncated history makes every one
        # of them look new. Locally it is a warning, because a developer's
        # shallow clone is normal and should not block their run.
        if [[ "${CI:-}" == "true" ]]; then
            emit_advisory error "$id" "$name" \
                "CANNOT VERIFY age: this checkout's history is truncated, so every suppression would report as new" \
                "run this gate in a job whose actions/checkout carries fetch-depth: 0 and filter: blob:none"
            return 1
        fi
        emit_advisory warn "$id" "$name" \
            "age DEFERRED: this checkout's history is truncated (git fetch --unshallow --filter=blob:none to answer it here)"
        return 0
    fi
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
