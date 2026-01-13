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

# 1. Auto-fix: Run fix:all to automatically fix formatting, lint, and i18n issues
echo "→ Running auto-fixes (format, lint, i18n)..."
npm run fix:all > /dev/null 2>&1 || true

# 2. Check if translation files were modified - MUST regenerate hashes
if echo "$STAGED_FILES" | grep -qE "i18n/locales/.*\.json$"; then
    echo "→ Translation files modified, ensuring hashes are up-to-date..."

    # Run i18n hash check
    if ! npm run check:i18n > /dev/null 2>&1; then
        # Hashes are stale - regenerate them
        echo "→ Regenerating translation hashes..."
        npm run fix:i18n > /dev/null 2>&1

        # Stage the updated hash files
        git add packages/web/src/i18n/locales/.translation-hashes.json 2>/dev/null || true
        git add packages/cli/src/i18n/locales/.translation-hashes.json 2>/dev/null || true

        echo "✓ Translation hashes regenerated and staged"
    else
        echo "✓ Translation hashes are up-to-date"
    fi
fi

# 3. Stage any files that were auto-fixed
MODIFIED_FILES=$(git diff --name-only 2>/dev/null || true)
if [ -n "$MODIFIED_FILES" ]; then
    echo "→ Staging auto-fixed files..."
    echo "$MODIFIED_FILES" | xargs git add 2>/dev/null || true
    echo "✓ Auto-fixed files staged"
fi

# 4. Quality checks (version, lint, unused code, format, i18n, typecheck, unit tests)
echo "→ Running quality checks..."
if ! npm run quality > /dev/null 2>&1; then
    echo "❌ Quality checks failed. Run 'npm run quality' to see errors."
    exit 2
fi
echo "✓ Quality checks passed"

echo "✅ All pre-commit checks passed!"
exit 0
