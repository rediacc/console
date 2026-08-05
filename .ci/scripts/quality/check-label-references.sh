#!/bin/bash
# Every GitHub label a workflow or .ci script references by name must be
# declared in .github/labels.yml.
#
# WHY. Labels are the repo's kill switches and routing flags, and nothing used
# to connect the code that reads them to the labels that exist: `full-ci` (the
# scope engine's documented kill switch), `autopilot`, `autopilot-blocked` and
# `rollback` were all referenced by merged code for weeks while not existing on
# the repo at all. The worst failure mode is SILENT fail-open:
# promote-stable.yml searched `label:rollback`, and a search for a nonexistent
# label returns zero PRs, so the promotion block simply never fired.
#
# Declaring in labels.yml is the tracked, reviewable half; creating the label
# live is one `gh label create`. This gate enforces the tracked half, in the
# code -> labels.yml direction only (a declared label nothing references is
# inventory, not an error).
#
# HOW LABELS ARE FOUND. A curated pattern set, one per consumption shape that
# exists in the tree. Each pattern is SELF-TESTED against a planted sample
# line before the sweep, so a regex that silently stops matching turns the
# gate red instead of quietly under-reporting (the check-silent-failure gate
# scanned zero files for weeks; that class of death is the one to design out).
# A floor on the total distinct labels found catches a broken sweep the
# self-tests cannot (for example a bad SCAN_DIRS path).
#
# Usage: check-label-references.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

LABELS_FILE="${LABEL_REFS_LABELS_FILE:-.github/labels.yml}"
# Space-separated for the test seam; defaults to the real surfaces.
SCAN_DIRS="${LABEL_REFS_SCAN_DIRS:-.github .ci}"
# The tree carries well over this many distinct referenced labels; finding
# fewer means the sweep itself broke (wrong root, bad glob), not a clean tree.
MIN_DISTINCT="${LABEL_REFS_MIN_DISTINCT:-8}"

[ -f "$LABELS_FILE" ] || {
    log_error "labels file not found: $LABELS_FILE"
    exit 1
}

# ---------------------------------------------------------------------------
# Pattern registry: name | extraction regex (grep -E, capture via sed) |
# planted sample that MUST yield the label 'selftest-label'.
# ---------------------------------------------------------------------------
# Each extractor is a grep -horE pattern piped through a sed capture. They are
# kept as parallel arrays because bash 4 associative arrays lose ordering and
# the self-test error should name the pattern that died.

PATTERN_NAMES=(
    "workflow-contains"
    "gh-api-labels-array"
    "search-filter"
    "js-includes"
    "js-label-const"
    "js-labels-array"
    "jq-arg-label"
    "var-default-yml"
    "var-default-sh"
    "grep-exact-label"
)

# This script and its test carry PLANTED sample lines (the self-test below
# and the test's fixtures): instrument fixtures, not label references. Both
# are excluded by basename, which cannot affect the self-test because its
# sample files are named sample.txt.
GREP_EXCLUDES=(--exclude=check-label-references.sh --exclude=test-label-references.sh)

# extract <name> <file-or-dir...>: prints one label per line.
extract() {
    local name="$1"
    shift
    case "$name" in
        workflow-contains)
            grep -rhoE "${GREP_EXCLUDES[@]}" "labels\.\*\.name, '[A-Za-z0-9._:-]+'" "$@" 2>/dev/null |
                sed -E "s/.*'([^']+)'.*/\1/" || true
            ;;
        gh-api-labels-array)
            grep -rhoE "${GREP_EXCLUDES[@]}" "labels\[\]=[A-Za-z0-9._:-]+" "$@" 2>/dev/null |
                sed -E 's/.*labels\[\]=//' || true
            ;;
        search-filter)
            grep -rhoE "${GREP_EXCLUDES[@]}" "label:[A-Za-z0-9._-]+" "$@" 2>/dev/null |
                sed -E 's/^label://' || true
            ;;
        js-includes)
            grep -rhoE "${GREP_EXCLUDES[@]}" "labels\.includes\('[A-Za-z0-9._:-]+'\)" "$@" 2>/dev/null |
                sed -E "s/.*'([^']+)'.*/\1/" || true
            ;;
        js-label-const)
            grep -rhoE "${GREP_EXCLUDES[@]}" "ISSUE_LABEL = '[A-Za-z0-9._:-]+'" "$@" 2>/dev/null |
                sed -E "s/.*'([^']+)'.*/\1/" || true
            ;;
        js-labels-array)
            # Quoted strings on a line declaring a *_LABELS array literal.
            grep -rhE "${GREP_EXCLUDES[@]}" "_LABELS = \[" "$@" 2>/dev/null |
                grep -oE "'[A-Za-z0-9._:-]+'" |
                sed -E "s/'//g" || true
            ;;
        jq-arg-label)
            # autopilot-gate.sh passes the label under test as `--arg l "..."`.
            grep -rhoE "${GREP_EXCLUDES[@]}" -- "--arg l \"[A-Za-z0-9._:-]+\"" "$@" 2>/dev/null |
                sed -E 's/.*"([^"]+)".*/\1/' || true
            ;;
        var-default-yml)
            grep -rhoE "${GREP_EXCLUDES[@]}" "AUTOPILOT_LABEL \|\| '[A-Za-z0-9._:-]+'" "$@" 2>/dev/null |
                sed -E "s/.*'([^']+)'.*/\1/" || true
            ;;
        var-default-sh)
            grep -rhoE "${GREP_EXCLUDES[@]}" "AUTOPILOT_LABEL:-[A-Za-z0-9._:-]+" "$@" 2>/dev/null |
                sed -E 's/.*AUTOPILOT_LABEL:-//' || true
            ;;
        grep-exact-label)
            # detect-bump-type.sh matches PR labels with `grep -qx "<label>"`;
            # verified the only -qx uses in the surfaces are label matches.
            grep -rhoE "${GREP_EXCLUDES[@]}" 'grep -qx "[A-Za-z0-9._:-]+"' "$@" 2>/dev/null |
                sed -E 's/.*"([^"]+)".*/\1/' || true
            ;;
        *)
            log_error "unknown pattern: $name"
            exit 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Self-test: every extractor must capture 'selftest-label' from its own
# planted sample. A pattern that cannot fire is a pattern that silently
# stopped protecting its consumption shape.
# ---------------------------------------------------------------------------
SELFTEST_DIR="$(mktemp -d)"
trap 'rm -rf "$SELFTEST_DIR"' EXIT

sample_for() {
    case "$1" in
        workflow-contains) echo "if: contains(github.event.pull_request.labels.*.name, 'selftest-label')" ;;
        gh-api-labels-array) echo "gh api -f 'labels[]=selftest-label'" ;;
        search-filter) echo '--search "merged:>=X label:selftest-label"' ;;
        js-includes) echo "if (labels.includes('selftest-label')) {" ;;
        js-label-const) echo "const ISSUE_LABEL = 'selftest-label';" ;;
        js-labels-array) echo "const ISSUE_LABELS = ['selftest-label', OTHER];" ;;
        jq-arg-label) echo 'jq -e --arg l "selftest-label" query' ;;
        var-default-yml) echo "LABEL: \${{ vars.AUTOPILOT_LABEL || 'selftest-label' }}" ;;
        var-default-sh) echo 'LABEL="${AUTOPILOT_LABEL:-selftest-label}"' ;;
        grep-exact-label) echo 'echo "$labels" | grep -qx "selftest-label"' ;;
    esac
}

for name in "${PATTERN_NAMES[@]}"; do
    sample_for "$name" >"$SELFTEST_DIR/sample.txt"
    got="$(extract "$name" "$SELFTEST_DIR/sample.txt")"
    if [ "$got" != "selftest-label" ]; then
        log_error "SELF-TEST FAILED: pattern '$name' extracted '${got:-<nothing>}' from its planted sample; the extractor is broken and the sweep would silently under-report"
        exit 1
    fi
done

# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------
# shellcheck disable=SC2086 # SCAN_DIRS is deliberately word-split
FOUND="$(for name in "${PATTERN_NAMES[@]}"; do extract "$name" $SCAN_DIRS; done | sort -u)"

# 'ubuntu-slim' etc. cannot appear: patterns anchor on label-consuming shapes,
# not on generic strings. Still, drop anything that is obviously a template
# placeholder rather than a literal.
FOUND="$(printf '%s\n' "$FOUND" | grep -v '^\s*$' | grep -vE '[${}]' || true)"

DISTINCT=$(printf '%s\n' "$FOUND" | sed '/^$/d' | wc -l)
if [ "$DISTINCT" -lt "$MIN_DISTINCT" ]; then
    log_error "sweep found only $DISTINCT distinct label reference(s) (floor: $MIN_DISTINCT). The tree carries more than that, so the sweep itself is broken (wrong root or dead glob), not clean."
    exit 1
fi

DECLARED="$(grep -E '^- name:' "$LABELS_FILE" | sed -E 's/^- name:[[:space:]]*//' | sed -E 's/[[:space:]]+$//')"

MISSING=0
while IFS= read -r label; do
    [ -n "$label" ] || continue
    if ! printf '%s\n' "$DECLARED" | grep -qx "$label"; then
        # Name every referencing site so the fix needs no re-discovery.
        # `|| true` because this runs under `set -o pipefail` and grep exits 1
        # on no-match: without it, a label whose site list came up empty would
        # KILL the sweep mid-report instead of naming the finding it just
        # made. Display-only value, so an empty result is legitimate here.
        sites="$( (grep -rln "$label" $SCAN_DIRS 2>/dev/null || true) | head -5 | tr '\n' ' ')"
        log_error "label '$label' is referenced by code but not declared in $LABELS_FILE (sites: $sites)"
        MISSING=$((MISSING + 1))
    fi
done <<<"$FOUND"

if [ "$MISSING" -gt 0 ]; then
    log_error "$MISSING undeclared label reference(s). Declare them in $LABELS_FILE and create them live with 'gh label create' if absent."
    exit 1
fi

log_info "all $DISTINCT code-referenced labels are declared in $LABELS_FILE"
