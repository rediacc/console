#!/bin/bash
# Check that the generated CLI contract is up-to-date with the CLI.
#
# The contract (packages/shared/src/cli-contract/data) is derived from the live
# Commander tree, COMMAND_METADATA and the i18n catalogues. It drives the web
# console, the `rdc --proxy` thin client and the executor, so a stale contract
# means those consumers disagree with the CLI they are driving.
#
# Usage:
#   .ci/scripts/quality/check-cli-contract.sh
#
# Exit codes:
#   0 - Contract is up-to-date
#   1 - Stale contract detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
OUTPUT_DIR="$REPO_ROOT/packages/shared/src/cli-contract/data"

cd "$REPO_ROOT"

# The generator imports the live CLI, which resolves @rediacc/shared and
# @rediacc/provisioning through their dist builds.
log_step "Building packages the CLI imports..."
npm run build:packages >/dev/null

log_step "Regenerating the CLI contract..."
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

npx tsx packages/cli/scripts/generate-cli-contract.ts --output "$TEMP_DIR" >/dev/null

# The version is injected at build time, so ignore it when diffing (both the TS
# constant and the JSON field). Mirrors check-renet-types.sh.
compare_ignoring_version() {
    local file1="$1"
    local file2="$2"
    diff -q \
        <(grep -v -e '_VERSION = ' -e '"version":' "$file1") \
        <(grep -v -e '_VERSION = ' -e '"version":' "$file2") \
        >/dev/null 2>&1
}

STALE=()

for file in contract.generated.ts contract.json; do
    if [[ ! -f "$OUTPUT_DIR/$file" ]]; then
        STALE+=("$file (missing)")
    elif ! compare_ignoring_version "$OUTPUT_DIR/$file" "$TEMP_DIR/$file"; then
        STALE+=("$file")
    fi
done

for generated in "$TEMP_DIR"/i18n/*.json; do
    lang="$(basename "$generated")"
    committed="$OUTPUT_DIR/i18n/$lang"
    if [[ ! -f "$committed" ]]; then
        STALE+=("i18n/$lang (missing)")
    elif ! diff -q "$committed" "$generated" >/dev/null 2>&1; then
        STALE+=("i18n/$lang")
    fi
done

# A locale bundle left behind after its locale was removed.
for committed in "$OUTPUT_DIR"/i18n/*.json; do
    lang="$(basename "$committed")"
    if [[ ! -f "$TEMP_DIR/i18n/$lang" ]]; then
        STALE+=("i18n/$lang (orphaned — no such locale)")
    fi
done

if [[ ${#STALE[@]} -eq 0 ]]; then
    log_info "CLI contract is up-to-date"
    exit 0
fi

log_error "Stale CLI contract: ${STALE[*]}"
log_error "The CLI changed but the generated contract did not. Run:"
log_error "  npm run generate:cli-contract -w @rediacc/cli"
log_error "then commit packages/shared/src/cli-contract/data."
exit 1
