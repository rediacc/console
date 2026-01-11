#!/bin/bash
# Pre-commit quality checks for Claude Code hook
# Exit code 0 = pass (allow commit)
# Exit code 2 = fail (block commit)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🔍 Running pre-commit checks..."

# 1. ESLint (with zero warnings policy)
echo "→ Running lint..."
if ! npm run lint -- --max-warnings 0 > /dev/null 2>&1; then
    echo "❌ Lint failed. Run 'npm run lint' to see errors."
    exit 2
fi
echo "✓ Lint passed"

# 2. Unused code check (knip)
echo "→ Checking unused code..."
if ! npm run lint:unused > /dev/null 2>&1; then
    echo "❌ Unused code check failed. Run 'npm run lint:unused' to see errors."
    exit 2
fi
echo "✓ Unused code check passed"

# 3. Format check (Biome)
echo "→ Checking format..."
if ! npm run format:check > /dev/null 2>&1; then
    echo "❌ Format check failed. Run 'npm run format' to fix."
    exit 2
fi
echo "✓ Format passed"

# 4. TypeScript type check
echo "→ Running typecheck..."
if ! npm run typecheck > /dev/null 2>&1; then
    echo "❌ Typecheck failed. Run 'npm run typecheck' to see errors."
    exit 2
fi
echo "✓ Typecheck passed"

echo "✅ All pre-commit checks passed!"
exit 0
