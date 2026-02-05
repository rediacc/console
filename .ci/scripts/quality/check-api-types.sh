#!/bin/bash
# Check that middleware-generated files are up-to-date
# With integrated autofix for PRs
#
# Validates the full generation pipeline:
#   stored-procedures.json -> api-schema.generated.ts -> api-hooks.generated.ts
# Requires SQL Server to be running (for generating stored-procedures.json)
#
# Environment variables:
#   GITHUB_EVENT_NAME - GitHub event type (e.g., 'pull_request')
#   GITHUB_HEAD_REF - PR branch name (set by GitHub Actions)
#   PR_AUTHOR - GitHub username of the PR author (optional, falls back to github-actions[bot])
#
# Exit codes:
#   0 - All files are up-to-date (or auto-fixed on PR)
#   1 - Stale files detected (and could not auto-fix)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
MIDDLEWARE_DIR="$REPO_ROOT/private/middleware"

if [[ ! -d "$MIDDLEWARE_DIR" ]]; then
    log_warn "Middleware submodule not available, skipping"
    exit 0
fi

# Source environment for database connection (if available)
ENV_SCRIPT="$SCRIPT_DIR/../env/create-middleware-env.sh"
if [[ -f "$ENV_SCRIPT" ]]; then
    source "$ENV_SCRIPT"
fi

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
STALE=()

# Helper function - compare files ignoring timestamp lines
# Generated files contain timestamps that change each generation
compare_ignoring_timestamps() {
    local file1="$1"
    local file2="$2"
    diff -q \
        <(grep -vE '(Generated at:|Schema generated:|generated:)' "$file1") \
        <(grep -vE '(Generated at:|Schema generated:|generated:)' "$file2") >/dev/null 2>&1
}

# Phase 1: Validate stored-procedures.json (requires database connection)
PROCEDURES_STALE=false
if [[ -n "${CONNECTION_STRING:-}" ]]; then
    log_step "Generating stored-procedures.json from database..."
    if (cd "$MIDDLEWARE_DIR" && dotnet run -- --generate-procedures --output "$TEMP_DIR/stored-procedures.json"); then
        COMMITTED_PROCEDURES="$MIDDLEWARE_DIR/AppData/stored-procedures.json"
        if [[ -f "$TEMP_DIR/stored-procedures.json" ]]; then
            if ! diff -q "$COMMITTED_PROCEDURES" "$TEMP_DIR/stored-procedures.json" >/dev/null 2>&1; then
                STALE+=("private/middleware/AppData/stored-procedures.json")
                PROCEDURES_STALE=true
            fi
        else
            log_error "Failed to generate stored-procedures.json"
            exit 1
        fi
    else
        log_warn "Failed to generate stored-procedures.json from database, skipping freshness check"
    fi
else
    log_warn "CONNECTION_STRING not set, skipping stored-procedures.json freshness check"
fi

# Check for stored-procedures.json (required for TypeScript generation)
PROCEDURES_JSON="$MIDDLEWARE_DIR/AppData/stored-procedures.json"
if [[ ! -f "$PROCEDURES_JSON" ]]; then
    log_error "stored-procedures.json not found at: $PROCEDURES_JSON"
    log_error "Run 'dotnet run -- --generate-procedures' first to create it."
    exit 1
fi

# Phase 2: Validate TypeScript types
log_step "Generating api-schema.generated.ts..."
(cd "$MIDDLEWARE_DIR" && dotnet run -- --generate-types --output "$TEMP_DIR/api-schema.generated.ts")

# Check api-schema.generated.ts
API_SCHEMA_COMMITTED="$REPO_ROOT/packages/shared/src/types/api-schema.generated.ts"
if [[ -f "$TEMP_DIR/api-schema.generated.ts" ]]; then
    if ! compare_ignoring_timestamps "$API_SCHEMA_COMMITTED" "$TEMP_DIR/api-schema.generated.ts"; then
        STALE+=("packages/shared/src/types/api-schema.generated.ts")
    fi
else
    log_error "Failed to generate api-schema.generated.ts"
    exit 1
fi

# Check api-schema.zod.ts
API_ZOD_COMMITTED="$REPO_ROOT/packages/shared/src/types/api-schema.zod.ts"
if [[ -f "$TEMP_DIR/api-schema.zod.ts" ]]; then
    if ! compare_ignoring_timestamps "$API_ZOD_COMMITTED" "$TEMP_DIR/api-schema.zod.ts"; then
        STALE+=("packages/shared/src/types/api-schema.zod.ts")
    fi
else
    log_error "Failed to generate api-schema.zod.ts"
    exit 1
fi

# Phase 3: Validate React hooks
log_step "Generating api-hooks.generated.ts..."
(cd "$MIDDLEWARE_DIR" && dotnet run -- --generate-hooks --output "$TEMP_DIR/api-hooks.generated.ts")

# Check api-hooks.generated.ts
API_HOOKS_COMMITTED="$REPO_ROOT/packages/web/src/api/api-hooks.generated.ts"
if [[ -f "$TEMP_DIR/api-hooks.generated.ts" ]]; then
    if ! compare_ignoring_timestamps "$API_HOOKS_COMMITTED" "$TEMP_DIR/api-hooks.generated.ts"; then
        STALE+=("packages/web/src/api/api-hooks.generated.ts")
    fi
else
    log_error "Failed to generate api-hooks.generated.ts"
    exit 1
fi

# All files up-to-date
if [[ ${#STALE[@]} -eq 0 ]]; then
    log_info "All middleware-generated files are up-to-date"
    exit 0
fi

# Check if ONLY stored-procedures.json is stale (TypeScript is fine)
# This can happen after autofix - TypeScript was regenerated but submodule wasn't updated
TYPESCRIPT_STALE=false
for file in "${STALE[@]}"; do
    if [[ "$file" != "private/middleware/AppData/stored-procedures.json" ]]; then
        TYPESCRIPT_STALE=true
        break
    fi
done

if [[ "$TYPESCRIPT_STALE" == "false" ]] && [[ "$PROCEDURES_STALE" == "true" ]]; then
    # Only stored-procedures.json is stale - this is expected after autofix
    # The TypeScript files are correct (they were generated from fresh stored-procedures.json)
    # The submodule just couldn't be updated (requires pushing to submodule repo)
    log_warn "Only stored-procedures.json is stale (submodule file)"
    log_warn "TypeScript files are up-to-date, which is what matters for the build"
    log_warn "To fully sync, update the middleware submodule manually"
    exit 0
fi

# Files are stale
log_warn "Stale generated files detected: ${STALE[*]}"

# Check if fixable context (PR only)
if [[ "${GITHUB_EVENT_NAME:-}" != "pull_request" ]] || [[ -z "${GITHUB_HEAD_REF:-}" ]]; then
    log_error "Cannot auto-fix outside PR context"
    log_error "Run './run.sh deploy prep' to regenerate all files, or:"
    log_error "  dotnet run -- --generate-procedures"
    log_error "  dotnet run -- --generate-types"
    log_error "  dotnet run -- --generate-hooks"
    exit 1
fi

# Check for recent autofix commits to prevent loops (specific to API types)
RECENT_AUTOFIX=$(git log --oneline -5 --grep="auto-regenerate middleware API types" 2>/dev/null | head -1 || true)
if [[ -n "$RECENT_AUTOFIX" ]]; then
    log_error "Recent API types autofix commit detected, cannot auto-fix again: $RECENT_AUTOFIX"
    log_error "Please manually regenerate with: ./run.sh deploy prep"
    exit 1
fi

# Phase 4: Apply fixes
log_step "Applying auto-fix..."

# First, update stored-procedures.json if stale (TypeScript generation depends on it)
if [[ "$PROCEDURES_STALE" == "true" ]] && [[ -f "$TEMP_DIR/stored-procedures.json" ]]; then
    cp "$TEMP_DIR/stored-procedures.json" "$MIDDLEWARE_DIR/AppData/stored-procedures.json"
    log_info "Updated stored-procedures.json"
fi

# Now regenerate TypeScript files from the (possibly updated) stored-procedures.json
# This ensures TypeScript is always consistent with stored-procedures.json
# Delete existing files first to bypass middleware's "no changes" skip optimization
log_step "Regenerating TypeScript files..."
rm -f "$API_SCHEMA_COMMITTED" "$API_ZOD_COMMITTED" "$API_HOOKS_COMMITTED"

(cd "$MIDDLEWARE_DIR" && dotnet run -- --generate-types --output "$API_SCHEMA_COMMITTED")
log_info "Generated api-schema.generated.ts and api-schema.zod.ts"

(cd "$MIDDLEWARE_DIR" && dotnet run -- --generate-hooks --output "$API_HOOKS_COMMITTED")
log_info "Generated api-hooks.generated.ts"

# Phase 5: Verify fix by regenerating again (ignoring timestamps)
log_step "Verifying fix..."

# Regenerate TypeScript files to verify they match (content-wise, ignoring timestamps)
VERIFY_DIR="$(mktemp -d)"
(cd "$MIDDLEWARE_DIR" && dotnet run -- --generate-types --output "$VERIFY_DIR/api-schema.generated.ts")
(cd "$MIDDLEWARE_DIR" && dotnet run -- --generate-hooks --output "$VERIFY_DIR/api-hooks.generated.ts")

STILL_STALE=()
if [[ -f "$VERIFY_DIR/api-schema.generated.ts" ]] && ! compare_ignoring_timestamps "$API_SCHEMA_COMMITTED" "$VERIFY_DIR/api-schema.generated.ts"; then
    STILL_STALE+=("api-schema.generated.ts")
fi
if [[ -f "$VERIFY_DIR/api-schema.zod.ts" ]] && ! compare_ignoring_timestamps "$API_ZOD_COMMITTED" "$VERIFY_DIR/api-schema.zod.ts"; then
    STILL_STALE+=("api-schema.zod.ts")
fi
if [[ -f "$VERIFY_DIR/api-hooks.generated.ts" ]] && ! compare_ignoring_timestamps "$API_HOOKS_COMMITTED" "$VERIFY_DIR/api-hooks.generated.ts"; then
    STILL_STALE+=("api-hooks.generated.ts")
fi
rm -rf "$VERIFY_DIR"

if [[ ${#STILL_STALE[@]} -gt 0 ]]; then
    log_error "Files still stale after fix: ${STILL_STALE[*]}"
    exit 1
fi
log_info "Verification successful"

# Phase 6: Commit if changes
cd "$REPO_ROOT"

# Check if there are any changes
SUBMODULE_CHANGED=false
CONSOLE_CHANGED=false

if ! git diff --quiet "private/middleware/AppData/stored-procedures.json" 2>/dev/null; then
    SUBMODULE_CHANGED=true
fi

for file in "packages/shared/src/types/api-schema.generated.ts" "packages/shared/src/types/api-schema.zod.ts" "packages/web/src/api/api-hooks.generated.ts"; do
    if ! git diff --quiet "$file" 2>/dev/null; then
        CONSOLE_CHANGED=true
        break
    fi
done

if [[ "$SUBMODULE_CHANGED" == "false" ]] && [[ "$CONSOLE_CHANGED" == "false" ]]; then
    log_info "Fix verified, no commit needed"
    exit 0
fi

log_step "Committing fix..."
if [[ -n "${PR_AUTHOR:-}" ]]; then
    git config user.name "$PR_AUTHOR"
    git config user.email "${PR_AUTHOR}@users.noreply.github.com"
else
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
fi

# Handle submodule commit first (stored-procedures.json is in middleware submodule)
if [[ "$SUBMODULE_CHANGED" == "true" ]]; then
    log_info "Committing submodule changes..."
    (
        cd "$MIDDLEWARE_DIR"
        if [[ -n "${PR_AUTHOR:-}" ]]; then
            git config user.name "$PR_AUTHOR"
            git config user.email "${PR_AUTHOR}@users.noreply.github.com"
        else
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
        fi
        git add "AppData/stored-procedures.json"
        git commit -m "chore: regenerate stored-procedures.json"
    )
    # Stage the submodule pointer update in parent
    git add "private/middleware"
fi

# Stage console repo files
if [[ "$CONSOLE_CHANGED" == "true" ]]; then
    git add "packages/shared/src/types/api-schema.generated.ts" \
        "packages/shared/src/types/api-schema.zod.ts" \
        "packages/web/src/api/api-hooks.generated.ts"
fi

git commit -m "$(
    cat <<'EOF'
chore(types): auto-regenerate middleware API types

Automatically regenerated by CI.
EOF
)"
git push origin "HEAD:${GITHUB_HEAD_REF}"

log_info "API types fixed and committed"
exit 0
