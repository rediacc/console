#!/bin/bash
# Check workflow files for banned patterns
#
# Validates that GitHub Actions workflows and actions don't use patterns that
# violate CI design principles:
#   - continue-on-error: Silently ignores step/job failures
#   - script: |          Inline scripts violate multi-CI design (use .ci/scripts/)
#   - fail-fast:         Watchdog handles failure cancellation; GitHub defaults to false
#
# Usage: check-workflows.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

log_step "Checking workflows for banned patterns..."

ERRORS=0

# Collect all workflow and action YAML files
GITHUB_YAMLS=()
while IFS= read -r file; do
    GITHUB_YAMLS+=("$file")
done < <(find .github/workflows .github/actions -name "*.yml" -type f 2>/dev/null)

# Check a banned pattern across all files
# Usage: check_pattern <grep_pattern> <label> <fix_hint>
check_pattern() {
    local pattern="$1"
    local label="$2"
    local fix_hint="$3"

    for file in "${GITHUB_YAMLS[@]}"; do
        matches=$(grep -n "$pattern" "$file" 2>/dev/null || true)
        if [[ -n "$matches" ]]; then
            while IFS= read -r match; do
                [[ -z "$match" ]] && continue
                local_line="${match%%:*}"
                local_content="${match#*:}"
                # Skip comments
                if echo "$local_content" | grep -qE "^\s*#"; then
                    continue
                fi
                log_error "$file:$local_line: ${label} is banned"
                echo "  Line: $local_content"
                echo "  Fix:  $fix_hint"
                echo ""
                ((ERRORS++))
            done <<< "$matches"
        fi
    done
}

# Banned patterns
check_pattern \
    "continue-on-error" \
    "continue-on-error" \
    "Ensure upstream dependencies are correct so steps always succeed"

check_pattern \
    "script:[[:space:]]*|" \
    "inline script: |" \
    "Move script to .ci/scripts/ and use: script: return await require('./.ci/scripts/ci/my-script.cjs')({github, context, core})"

check_pattern \
    "fail-fast" \
    "fail-fast" \
    "Remove fail-fast — the watchdog handles failure cancellation. GitHub defaults to false when omitted"

if [[ $ERRORS -gt 0 ]]; then
    echo ""
    log_error "Found $ERRORS banned pattern(s) in workflows"
    exit 1
else
    log_info "All workflows are clean"
fi
