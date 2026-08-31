#!/bin/bash
# Pre-commit quality checks for Claude Code hook
# Exit code 0 = pass (allow commit)
# Exit code 2 = fail (block commit)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🔍 Running pre-commit checks..."

# 0. Check Node.js version (require v22.x)
echo "→ Checking Node.js version..."
if ! command -v node &>/dev/null; then
    echo "❌ Node.js is not installed"
    echo "   Install Node.js v22.x from: https://nodejs.org/"
    exit 2
fi

NODE_VERSION=$(node -v | cut -d'v' -f2)
NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d'.' -f1)

if [ "$NODE_MAJOR" != "22" ]; then
    echo "❌ Node.js version mismatch"
    echo "   Required: v22.x"
    echo "   Current:  v$NODE_VERSION"
    echo "   Install Node.js v22 from: https://nodejs.org/"
    exit 2
fi
echo "✓ Node.js version: v$NODE_VERSION"

# 1. Verify .backend-state is not being committed
STAGED_FILES=$(git diff --cached --name-only 2>/dev/null || true)
if grep -q "\.backend-state" <<<"$STAGED_FILES"; then
    echo "❌ .backend-state file should not be committed"
    echo "   This file is auto-generated and should be in .gitignore"
    echo "   Run: git reset HEAD .backend-state"
    exit 2
fi

# 2. Sync dependencies if package files changed (ensures local matches CI)
if grep -qE "^(package\.json|package-lock\.json|packages/.*/package\.json)$" <<<"$STAGED_FILES"; then
    echo "→ Package files changed, syncing dependencies..."
    if ! npm ci --silent 2>/dev/null; then
        echo "❌ Failed to sync dependencies. Run 'npm ci' manually."
        exit 2
    fi
    echo "✓ Dependencies synced"
fi

# 3. Auto-fix: Run fix:all to automatically fix formatting, lint, and i18n issues
echo "→ Running auto-fixes (format, lint, i18n)..."
if ! npm run fix:all > /dev/null 2>&1; then
    echo "⚠️  Some issues could not be auto-fixed"
    echo "   Run: ./run.sh fix all"
fi

# 2. Check if translation files were modified - MUST regenerate hashes
# The pattern must cover EVERY locale tree fix:i18n regenerates -- www lives
# under i18n/translations/, not i18n/locales/, so a www-only English change used
# to slip past this block entirely.
if grep -qE "i18n/(locales|translations)/.*\.json$" <<<"$STAGED_FILES"; then
    echo "→ Translation files modified, ensuring hashes are up-to-date..."

    # Run i18n hash check
    if ! npm run check:i18n > /dev/null 2>&1; then
        # Hashes are stale - regenerate them
        echo "→ Regenerating translation hashes..."
        npm run fix:i18n > /dev/null 2>&1

        # Stage every manifest fix:i18n regenerates in THIS repo. Staging only a
        # subset left a www or account regeneration unstaged, so the commit
        # landed with a stale committed manifest.
        # Source of truth: LOCALE_CONFIGS in scripts/generate-translation-hashes.ts
        for manifest in \
            packages/cli/src/i18n/locales/.translation-hashes.json \
            packages/www/src/i18n/translations/.translation-hashes.json; do
            if [ -f "$manifest" ]; then
                git add "$manifest"
            else
                echo "⚠️  Expected manifest missing: $manifest"
                echo "   LOCALE_CONFIGS in scripts/generate-translation-hashes.ts is out of sync."
            fi
        done

        # The account manifests live in the private/account submodule and cannot
        # be staged from this repo. Warn so they are not silently left behind.
        for sub_manifest in \
            private/account/web/src/i18n/locales/.translation-hashes.json \
            private/account/src/i18n/locales/.translation-hashes.json; do
            if [ -f "$sub_manifest" ] && ! git -C private/account diff --quiet -- \
                "${sub_manifest#private/account/}"; then
                echo "⚠️  Regenerated $sub_manifest (private/account submodule)"
                echo "   Commit it inside private/account before committing this repo."
            fi
        done

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
    echo ""
    echo "❌ Quality checks failed!"
    echo ""
    echo "   To see detailed errors, run:"
    echo "     ./run.sh quality all      # Run all quality checks"
    echo ""
    echo "   To fix issues automatically:"
    echo "     ./run.sh fix all          # Auto-fix formatting, lint, etc."
    echo ""
    echo "   To run specific checks:"
    echo "     ./run.sh quality lint     # ESLint + Knip"
    echo "     ./run.sh quality format   # Code formatting"
    echo "     ./run.sh quality types    # TypeScript types"
    echo ""
    exit 2
fi
echo "✓ Quality checks passed"

echo ""
echo "✅ All pre-commit checks passed!"
echo "   - Node.js version: v$NODE_VERSION"
echo "   - Dependencies synced"
echo "   - Code auto-fixed"
echo "   - Quality checks passed"
exit 0
