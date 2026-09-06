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
# THIS FILE IS A DELEGATING SHIM. The implementation lives in
# .ci/rediacc_ci/core/age.py, which carries the reasoning in full: why a
# truncated history makes this gate answer -1 rather than "fresh" (measured
# 2026-09-03 against github.com/docker/docker in .go-deps-upgrade-blocklist,
# 195 days on a full clone and 2 on a truncated one), and why the graft LIST is
# the test rather than `git rev-parse --is-shallow-repository`.
#
# WHAT STAYS IN BASH, AND WHY. emit_advisory. It is a separate library with its
# own contract -- eight optional associative arrays keyed by advisory id, and
# the `::error::` / `::warning::` Actions form -- and its two callers
# (.ci/scripts/security/audit.sh, .ci/scripts/quality/check-go-deps.sh) populate
# those arrays before calling in. The port splits the DECISION (Python, and
# testable without a runner) from the EMISSION (here, alongside every other
# advisory in this repo). Neither caller changes.

# Guard against double-sourcing.
[[ -n "${__AGE_CHECK_SH_SOURCED:-}" ]] && return 0

# shellcheck source=emit-advisory.sh
# BLOCKER: required for ci_error / ci_warn used by this library's public API
source "$(dirname "${BASH_SOURCE[0]}")/emit-advisory.sh"

# There is deliberately no bash fallback implementation: a fallback is a second
# implementation, and this one decides whether a year-old suppression is
# expired. Failing to load is louder than answering wrongly. REDIACC_CI_ROOT is
# the package's single environment override (.ci/rediacc_ci/paths.py).
__age_check_root="${REDIACC_CI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
if [[ ! -d "$__age_check_root/.ci/rediacc_ci/core" ]]; then
    echo "age-check.sh: cannot find rediacc_ci under '$__age_check_root/.ci' (set REDIACC_CI_ROOT)" >&2
    unset __age_check_root
    return 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "age-check.sh: python3 is required; the age logic lives in rediacc_ci.core.age" >&2
    unset __age_check_root
    return 1
fi
readonly __AGE_CHECK_SH_SOURCED=1
readonly AGE_CHECK_CI_DIR="$__age_check_root/.ci"
unset __age_check_root

readonly AGE_WARN_DAYS="${AGE_WARN_DAYS:-180}"
readonly AGE_FAIL_DAYS="${AGE_FAIL_DAYS:-365}"

# PYTHONPATH rather than `cd`: every caller runs git against ITS OWN cwd (the
# gate's checkout, or a temp fixture that test-age-check.sh cds into), and
# changing directory here would silently measure the wrong repository.
_age_check_py() {
    PYTHONPATH="$AGE_CHECK_CI_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m rediacc_ci.core.age "$@"
}

# _age_grafts_file
#
# Path to a NON-EMPTY graft list, or empty when history is complete.
# Kept as a function because it was one: private by name, but a shim that drops
# a helper is a shim that cannot be swapped back.
_age_grafts_file() {
    _age_check_py grafts-file
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
    _age_check_py days "$1" "$2"
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
    local line rc=0

    # The exit code IS the return value: 1 only for `error`. A warn returns 0,
    # exactly as the bash implementation did, so a caller aggregating returns
    # does not start failing on reminders.
    line="$(_age_check_py verdict "$file" "$entry" \
        "$AGE_WARN_DAYS" "$AGE_FAIL_DAYS" "${CI:-}")" || rc=$?

    local level message remedy
    IFS=$'\t' read -r level message remedy <<<"$line"

    case "$level" in
        error | warn) emit_advisory "$level" "$id" "$name" "$message" "$remedy" ;;
        ok) ;;
        *)
            # A verdict this shim cannot read is not a pass. Anything other than
            # the three known levels means the contract moved underneath it.
            echo "age-check.sh: unreadable verdict '$line' for $file/$entry" >&2
            return 1
            ;;
    esac
    return "$rc"
}
