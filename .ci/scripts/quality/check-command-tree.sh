#!/bin/bash
# Check that the exported command tree is up-to-date with the CLI.
#
# packages/cli/scripts/command-tree.json is the shipped snapshot of the live
# Commander tree, and NINE validators trust it as their model of the CLI:
#
#   scripts/lib/positional-cli-detector.ts  (and, through it, the two ESLint rules
#                                            no-positional-cli-syntax{,-source} and
#                                            packages/www/scripts/validate-docs-cli-usage.js)
#   scripts/validate-cli-examples.ts
#   scripts/check-cli-docs.ts
#   scripts/check-design-tree.ts
#   packages/cli/scripts/check-command-planes.ts
#
# Nothing regenerated it, and nothing checked it. A stale tree does not fail loudly:
# it fails OPEN. Every one of those validators would keep passing while describing a
# CLI that no longer exists — a removed command stays "valid" in the docs, a new one
# is never checked at all, and the positional detector reds on correct syntax (which
# is exactly what happened when P4 gave leaves positional refs). contract.json has had
# a freshness gate all along; this is the same gate for its sibling.
#
# Usage:
#   .ci/scripts/quality/check-command-tree.sh
#
# Exit codes:
#   0 - Command tree is up-to-date
#   1 - Stale command tree detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
COMMITTED="$REPO_ROOT/packages/cli/scripts/command-tree.json"

cd "$REPO_ROOT"

# The exporter imports the live CLI, which resolves @rediacc/shared and
# @rediacc/provisioning through their dist builds.
log_step "Building packages the CLI imports..."
npm run build:packages >/dev/null

log_step "Re-exporting the command tree..."
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

npx tsx packages/cli/scripts/export-command-tree.ts --output "$TEMP_DIR/command-tree.json" >/dev/null

if [[ ! -f "$COMMITTED" ]]; then
    log_error "packages/cli/scripts/command-tree.json is missing."
    echo "  Regenerate it with: npm run export:command-tree -w @rediacc/cli"
    exit 1
fi

if ! diff -q "$COMMITTED" "$TEMP_DIR/command-tree.json" >/dev/null 2>&1; then
    log_error "packages/cli/scripts/command-tree.json is STALE."
    echo ""
    echo "  The committed tree no longer matches the live CLI. Every validator that"
    echo "  reads it is now describing a CLI that does not exist, and each of them"
    echo "  fails OPEN — they keep passing while checking nothing."
    echo ""
    echo "  Fix:"
    echo "    npm run export:command-tree -w @rediacc/cli"
    echo "    git add packages/cli/scripts/command-tree.json"
    echo ""
    echo "  Diff (committed vs live):"
    diff "$COMMITTED" "$TEMP_DIR/command-tree.json" | head -40 | sed 's/^/    /'
    exit 1
fi

log_info "packages/cli/scripts/command-tree.json matches the shipped CLI"
