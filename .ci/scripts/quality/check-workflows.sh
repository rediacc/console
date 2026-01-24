#!/bin/bash
# Check workflow files for banned patterns
#
# Validates that GitHub Actions workflows don't use patterns that hide failures:
#   - continue-on-error: Silently ignores step/job failures
#
# These patterns can mask real CI problems that should be fixed properly.
#
# Usage: check-workflows.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

log_step "Checking workflows for banned patterns..."

ERRORS=0

# Check for continue-on-error in all workflow files
while IFS= read -r file; do
    matches=$(grep -n "continue-on-error" "$file" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
        while IFS= read -r match; do
            [[ -z "$match" ]] && continue
            local_line="${match%%:*}"
            local_content="${match#*:}"
            # Skip comments
            if echo "$local_content" | grep -qE "^\s*#"; then
                continue
            fi
            log_error "$file:$local_line: continue-on-error is banned"
            echo "  Line: $local_content"
            echo "  Fix:  Ensure upstream dependencies are correct so steps always succeed"
            echo ""
            ((ERRORS++))
        done <<< "$matches"
    fi
done < <(find .github/workflows -name "*.yml" -type f 2>/dev/null)

if [[ $ERRORS -gt 0 ]]; then
    echo ""
    log_error "Found $ERRORS banned pattern(s) in workflows"
    log_info "continue-on-error hides failures — fix job dependencies instead"
    exit 1
else
    log_info "All workflows are clean"
fi
