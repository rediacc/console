#!/bin/bash
# Check that all docker-compose env var references are defined in ci-env.sh
#
# Prevents silent failures when env vars are added to docker-compose.yml
# but not exported in ci-env.sh (or its .env / GITHUB_ENV blocks). This
# catches the class of bugs where a new variable works on first docker
# compose invocation (same shell) but breaks on subsequent invocations
# (new shell) because the variable isn't persisted.
#
# Usage: check-compose-env.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
CI_ENV="$REPO_ROOT/.ci/scripts/infra/ci-env.sh"
COMPOSE_DIR="$REPO_ROOT/.ci/docker/ci"

log_step "Checking docker-compose env var completeness..."

ERRORS=0

# Helper: check if array contains value
array_contains() {
    local needle="$1"
    shift
    for item in "$@"; do
        [[ "$item" == "$needle" ]] && return 0
    done
    return 1
}

# 1. Extract all ${VAR_NAME} references from compose files (unique var names)
COMPOSE_VARS=()
while IFS= read -r var; do
    [[ -z "$var" ]] && continue
    COMPOSE_VARS+=("$var")
done < <(grep -ohP '\$\{[A-Z0-9_]+' "$COMPOSE_DIR"/docker-compose*.yml 2>/dev/null |
    sed 's/\${//' | sort -u)

if [[ ${#COMPOSE_VARS[@]} -eq 0 ]]; then
    log_error "No env var references found in compose files — check parse logic"
    exit 1
fi

# 2. Extract variables with NON-EMPTY defaults in compose: ${VAR:-some_value}
#    These are safe even if not explicitly defined in ci-env.sh
SAFE_DEFAULT_VARS=()
while IFS= read -r var; do
    [[ -z "$var" ]] && continue
    SAFE_DEFAULT_VARS+=("$var")
done < <(grep -ohP '\$\{[A-Z0-9_]+:-[^}]+\}' "$COMPOSE_DIR"/docker-compose*.yml 2>/dev/null |
    grep -vP ':-\}$' |
    grep -oP '(?<=\$\{)[A-Z0-9_]+' | sort -u)

# 3. Extract variables from the PERSISTED_ENV heredoc block in ci-env.sh
#    Only parse between <<ENVBLOCK and ^ENVBLOCK to avoid matching exports
#    or other assignments outside the persistence block.
PERSISTED_VARS=()
while IFS= read -r var; do
    [[ -z "$var" ]] && continue
    PERSISTED_VARS+=("$var")
done < <(sed -n '/<<ENVBLOCK/,/^ENVBLOCK/p' "$CI_ENV" |
    grep -oP '^[A-Z0-9_]+(?==)' | sort -u)

# 4. Validate: vars WITHOUT safe defaults must be persisted in ci-env.sh
#    Vars with non-empty defaults (e.g., ${ENABLE_HTTPS:-false}) are safe even if
#    not in ci-env.sh — they won't cause failures or container recreation.
log_step "Checking compose vars without safe defaults are persisted in ci-env.sh..."
for var in "${COMPOSE_VARS[@]}"; do
    if array_contains "$var" "${SAFE_DEFAULT_VARS[@]}"; then
        continue
    fi
    if ! array_contains "$var" "${PERSISTED_VARS[@]}"; then
        log_error "docker-compose references \${$var} (no safe default) but ci-env.sh does not persist it"
        echo "  This variable will be empty in workflow steps that don't source ci-env.sh"
        echo "  Fix: Add it to the .env file AND GITHUB_ENV blocks in ci-env.sh"
        ((ERRORS++))
    fi
done

if [[ $ERRORS -gt 0 ]]; then
    echo ""
    log_error "Found $ERRORS compose env var issue(s)"
    echo "See: .ci/scripts/infra/ci-env.sh (.env file + GITHUB_ENV blocks)"
    exit 1
else
    log_info "All compose env vars are properly defined (${#COMPOSE_VARS[@]} vars checked)"
fi
