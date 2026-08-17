#!/bin/bash
# BLOCKER validation for .breakpoint-drift-accept. VENDORED SUBSET of
# .ci/scripts/lib/blocker-validator.sh.
#
# Vendored rather than sourced for the reason in breakpoint-common.sh, plus one
# specific to this file: the canonical validator sources emit-advisory.sh, a
# transitive dependency breakpoint must not take.
#
# The banned-phrase array below MUST stay a SUBSET of the canonical one.
# test-breakpoint-portability.sh asserts exactly that (and skips the assertion
# when the canonical file is absent, i.e. downstream), so the copy cannot rot in
# the one repo that is able to notice.
#
# Why validate at all: docs/agent-reference/suppressions.md calls BLOCKER "the single
# escape mechanism". An unvalidated accept-list fills up with "# ok" inside a
# month, and then the drift gate is decorative.
#
# FILE FORMAT (.breakpoint-drift-accept):
#   # BLOCKER: <>=30 chars saying what is different about THIS repo and why
#   #          upstream cannot carry the change>
#   scripts/some-file.sh
#
# One BLOCKER comment immediately above each accepted path. Blank lines and
# other comments are ignored.

# shellcheck disable=SC2034  # arrays are consumed by the functions below

readonly BREAKPOINT_BLOCKER_MIN_LENGTH=30

# Subset of LOW_EFFORT_BLOCKER_PATTERNS in .ci/scripts/lib/blocker-validator.sh.
# Trimmed to the phrases that plausibly appear in a drift context; the npm-audit
# specific ones ("no upstream fix", "dev dep") are dropped as inapplicable.
readonly BREAKPOINT_LOW_EFFORT_BLOCKERS=(
    "none" "n/a" "na" "empty" "-"
    "tbd" "wip" "fixme" "todo" "later" "fix later" "will fix" "pending"
    "skip" "skipping" "skipped" "ignore" "ignoring" "ignored"
    "unknown" "unknown reason" "idk" "dunno" "whatever"
    "ok" "okay" "ack" "acknowledged" "noted" "done" "fixed" "applied"
    "addressed" "updated" "changed" "understood"
    "escape" "escape hatch" "suppressed" "suppress" "bypass" "override"
)

# bp_validate_blocker <path> <reason>
# Returns 0 if the reason is acceptable, 1 otherwise (printing why, and how to
# fix it, in the shape .ci/scripts/lib/blocker-validator.sh uses).
bp_validate_blocker() {
    local path="$1" reason="$2"
    local normalized pattern

    normalized=$(echo "$reason" |
        tr '[:upper:]' '[:lower:]' |
        sed 's/^[[:space:]]*//;s/[[:space:]]*$//' |
        sed 's/[.!?,;:]*$//')

    for pattern in "${BREAKPOINT_LOW_EFFORT_BLOCKERS[@]}"; do
        if [[ "$normalized" == "$pattern" ]]; then
            log_error "drift-accept: BLOCKER for '$path' is a low-effort placeholder (\"$reason\")"
            echo "  Rejected because: \"$normalized\" matches the banned-phrase list; it adds nothing beyond 'we accepted it'." >&2
            echo "  Action: say what is different about THIS repo and why the canonical copy cannot carry the change." >&2
            echo "  Example: 'renet self-hosted runners have no azure apt mirror, so the desktop install must" >&2
            echo "            retry against ports.ubuntu.com; console's hosted runners resolve azure fine'" >&2
            return 1
        fi
    done

    if ((${#normalized} < BREAKPOINT_BLOCKER_MIN_LENGTH)); then
        log_error "drift-accept: BLOCKER for '$path' is too short (${#normalized} chars, minimum $BREAKPOINT_BLOCKER_MIN_LENGTH)"
        echo "  Current: \"$reason\"" >&2
        echo "  Action: name the repo-specific constraint AND why it cannot be upstreamed." >&2
        return 1
    fi

    return 0
}

# bp_parse_drift_accept <file>
#
# Emits one `<path>\t<reason>` line per accepted entry on stdout. A path with no
# BLOCKER comment directly above it emits an empty reason, which
# bp_validate_blocker then rejects -- so "forgot the comment" fails loudly
# instead of silently accepting.
bp_parse_drift_accept() {
    local file="$1"
    [[ -f "$file" ]] || return 0

    local line reason=""
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            '#'*BLOCKER:*)
                reason="${line#*BLOCKER:}"
                reason="${reason#"${reason%%[![:space:]]*}"}"
                ;;
            '#'*)
                # A non-BLOCKER comment between the reason and the path would
                # otherwise silently orphan the reason; treat it as continuation
                # only when we already have one, else ignore.
                ;;
            '') ;;
            *)
                printf '%s\t%s\n' "$line" "$reason"
                reason=""
                ;;
        esac
    done <"$file"
}
