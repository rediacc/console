#!/bin/bash
# Check that subscription schema is up-to-date between TypeScript and Go
#
# Usage:
#   .ci/scripts/quality/check-subscription-schema.sh
#
# Exit codes:
#   0 - Schema is up-to-date
#   1 - Stale schema detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
SCHEMA_FILE="$REPO_ROOT/packages/shared/src/subscription/schema.generated.json"
RENET_DIR="$REPO_ROOT/private/renet"

cd "$REPO_ROOT"

# Phase 1: Generate fresh schema and check for changes
log_step "Generating fresh subscription schema..."
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

# GENERATE OUT OF TREE. This used to regenerate $SCHEMA_FILE in place and then
# `biome format --write` it, which made this gate a WRITER of a tracked file
# while the ~8.7x-parallel pool read the same tree -- the hazard class in
# scripts/ci-runner/manifest.ts:346-365, observed live with this exact file
# stamped mid-battery. The check only ever needed something to DIFF against, so
# it writes to $TEMP_DIR and the tracked file is never touched.
SUBSCRIPTION_SCHEMA_OUT="$TEMP_DIR/schema.fresh.json" \
    npx tsx packages/shared/scripts/generate-subscription-schema.ts >/dev/null

# Format through STDIN rather than --write, so biome still resolves this repo's
# config for the file's real path without that path being written.
if ! npx biome format --stdin-file-path="packages/shared/src/subscription/schema.generated.json" \
    <"$TEMP_DIR/schema.fresh.json" >"$TEMP_DIR/schema.formatted.json" 2>/dev/null; then
    # Formatting is cosmetic here; an unformatted comparison is still a valid
    # staleness check, and failing the gate on a formatter hiccup would be worse.
    cp "$TEMP_DIR/schema.fresh.json" "$TEMP_DIR/schema.formatted.json"
fi

if [[ -f "$SCHEMA_FILE" ]] && diff -q "$SCHEMA_FILE" "$TEMP_DIR/schema.formatted.json" >/dev/null 2>&1; then
    log_info "Subscription schema is up-to-date"
else
    log_warn "Subscription schema is STALE: regenerate with 'npx tsx packages/shared/scripts/generate-subscription-schema.ts'"
fi

# Phase 2: Run Go tests to validate schema consistency
require_submodule "$RENET_DIR" "Renet submodule (Go schema validation)" || exit 0

log_step "Running Go schema validation tests..."
cd "$RENET_DIR"

if ! go test ./pkg/subscription/... -run 'TestGoTypesMatchTypeScriptSchema|TestGoConstantsMatchTypeScriptSchema|TestSchemaVersion|TestPlanResourcesConsistency|TestPlanFeaturesConsistency' -v; then
    log_error "Go types do not match TypeScript schema!"
    log_error ""
    log_error "This means the subscription types are out of sync between TypeScript and Go."
    log_error "To fix:"
    log_error "  1. Update Go types in private/renet/pkg/subscription/types.go to match TypeScript"
    log_error "  2. Run: npx tsx packages/shared/scripts/generate-subscription-schema.ts"
    log_error "  3. Run: cd private/renet && go test ./pkg/subscription/... -run TestGoTypesMatchTypeScriptSchema -v"
    exit 1
fi

log_info "Go types match TypeScript schema"

# Phase 3: Check if schema file needs to be committed
cd "$REPO_ROOT"
if ! git diff --quiet "$SCHEMA_FILE" 2>/dev/null; then
    log_error "Schema file has uncommitted changes"
    log_error ""
    log_error "This step ALREADY regenerated it for you (phase 1). There is nothing"
    log_error "left to run: review the diff and commit it."
    log_error "  git diff $SCHEMA_FILE"
    log_error ""
    log_error "This compares against git HEAD, so it stays red in a working tree that"
    log_error "has legitimately-regenerated output but is not committed yet."
    exit 1
fi

exit 0
