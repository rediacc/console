#!/bin/bash
# Pre-commit quality checks for Claude Code hook
# Exit code 0 = pass (allow commit)
# Exit code 2 = fail (block commit)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🔍 Running pre-commit checks..."

# 0. Sync dependencies if package files changed (ensures local matches CI)
STAGED_FILES=$(git diff --cached --name-only 2>/dev/null || true)
if echo "$STAGED_FILES" | grep -qE "^(package\.json|package-lock\.json|packages/.*/package\.json)$"; then
    echo "→ Package files changed, syncing dependencies..."
    if ! npm ci --silent 2>/dev/null; then
        echo "❌ Failed to sync dependencies. Run 'npm ci' manually."
        exit 2
    fi
    echo "✓ Dependencies synced"
fi

# 1. Quality checks (version, lint, unused code, format, typecheck, unit tests)
echo "→ Running quality checks..."
if ! npm run quality > /dev/null 2>&1; then
    echo "❌ Quality checks failed. Run 'npm run quality' to see errors."
    exit 2
fi
echo "✓ Quality checks passed"

echo "✅ All pre-commit checks passed!"
exit 0
