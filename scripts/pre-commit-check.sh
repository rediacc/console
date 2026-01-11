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

# 1. Version consistency check (fast, should run first)
echo "→ Checking version consistency..."
if ! npm run version:check > /dev/null 2>&1; then
    echo "❌ Version mismatch detected. Run 'npm run version:list' for details."
    exit 2
fi
echo "✓ Version consistency check passed"

# 2. ESLint (with zero warnings policy)
echo "→ Running lint..."
if ! npm run lint -- --max-warnings 0 > /dev/null 2>&1; then
    echo "❌ Lint failed. Run 'npm run lint' to see errors."
    exit 2
fi
echo "✓ Lint passed"

# 3. Unused code check (knip)
echo "→ Checking unused code..."
if ! npm run lint:unused > /dev/null 2>&1; then
    echo "❌ Unused code check failed. Run 'npm run lint:unused' to see errors."
    exit 2
fi
echo "✓ Unused code check passed"

# 4. Format check (Biome)
echo "→ Checking format..."
if ! npm run format:check > /dev/null 2>&1; then
    echo "❌ Format check failed. Run 'npm run format' to fix."
    exit 2
fi
echo "✓ Format passed"

# 5. TypeScript type check
echo "→ Running typecheck..."
if ! npm run typecheck > /dev/null 2>&1; then
    echo "❌ Typecheck failed. Run 'npm run typecheck' to see errors."
    exit 2
fi
echo "✓ Typecheck passed"

# 6. Unit tests (fast, catches runtime errors)
echo "→ Running unit tests..."
if ! npm run test:run > /dev/null 2>&1; then
    echo "❌ Unit tests failed. Run 'npm run test:run' to see errors."
    exit 2
fi
echo "✓ Unit tests passed"

echo "✅ All pre-commit checks passed!"
exit 0
