#!/bin/bash
# Verify the config-migration runner round-trips every committed fixture
# through runMigrations() + RdcConfigSchema.parse() without error, and
# that every version gap in [1..CURRENT_SCHEMA_VERSION-1] has a
# corresponding v<N>-to-v<N+1>.ts migration file.
#
# This catches:
#   - Dropping a migration without bumping CURRENT_SCHEMA_VERSION
#   - Bumping CURRENT_SCHEMA_VERSION without adding the migration file
#   - A fixture under tests/fixtures/config/ that no longer parses
#
# Usage: .ci/scripts/quality/check-config-migrations.sh
#
# Exit codes: 0 = OK, 1 = problem detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
MIGRATIONS_DIR="$REPO_ROOT/packages/cli/src/schema/migrations"
FIXTURES_DIR="$REPO_ROOT/packages/cli/tests/fixtures/config"
RUNNER="$MIGRATIONS_DIR/index.ts"

ERRORS=0

log_step "Checking migration runner exists..."
if [[ ! -f "$RUNNER" ]]; then
    log_error "Migration runner missing: $RUNNER"
    exit 1
fi

# Extract CURRENT_SCHEMA_VERSION from the runner
CURRENT=$(grep -oE 'CURRENT_SCHEMA_VERSION = [0-9]+' "$RUNNER" | grep -oE '[0-9]+$')
if [[ -z "$CURRENT" ]]; then
    log_error "Could not parse CURRENT_SCHEMA_VERSION from $RUNNER"
    exit 1
fi
log_info "CURRENT_SCHEMA_VERSION = $CURRENT"

log_step "Checking migration file coverage..."
for ((v = 1; v < CURRENT; v++)); do
    next=$((v + 1))
    file="$MIGRATIONS_DIR/v${v}-to-v${next}.ts"
    if [[ ! -f "$file" ]]; then
        log_error "Missing migration file: v${v}-to-v${next}.ts"
        log_error "Either add it under $MIGRATIONS_DIR/, or roll back the CURRENT_SCHEMA_VERSION bump."
        ERRORS=$((ERRORS + 1))
    else
        log_info "  ✓ v${v}-to-v${next}.ts present"
    fi
done

log_step "Round-tripping committed fixtures..."
if [[ ! -d "$FIXTURES_DIR" ]]; then
    log_warn "Fixtures dir not found: $FIXTURES_DIR (skipping round-trip)"
else
    fixtures=$(find "$FIXTURES_DIR" -maxdepth 1 -name 'v*-sample.json' | sort)
    if [[ -z "$fixtures" ]]; then
        log_warn "No v*-sample.json fixtures in $FIXTURES_DIR (skipping round-trip)"
    else
        # Use a tsx script to run the actual TypeScript runner — keeps the
        # bash check from re-implementing migration logic.
        tmpscript="$REPO_ROOT/packages/cli/.config-migrations-check.tmp.ts"
        trap 'rm -f "$tmpscript"' EXIT
        cat >"$tmpscript" <<'TSX'
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { runMigrations } from './src/schema/migrations/index.js';
import { RdcConfigSchema } from './src/schema/schemas.js';

const fixturesDir = 'tests/fixtures/config';
const fixtures = readdirSync(fixturesDir).filter((f) => /^v\d+-sample\.json$/.test(f));
let failed = 0;
for (const f of fixtures) {
  const raw = JSON.parse(readFileSync(join(fixturesDir, f), 'utf8'));
  try {
    const migrated = runMigrations(raw);
    const parsed = RdcConfigSchema.safeParse(migrated.config);
    if (!parsed.success) {
      console.error(`FAIL ${f}: ${JSON.stringify(parsed.error.issues)}`);
      failed++;
      continue;
    }
    console.log(`PASS ${f} (from=${migrated.fromVersion}, to=${migrated.toVersion}, migrated=${migrated.migrated})`);
  } catch (err) {
    console.error(`FAIL ${f}: ${(err as Error).message}`);
    failed++;
  }
}
process.exit(failed > 0 ? 1 : 0);
TSX
        if ! result=$(cd "$REPO_ROOT/packages/cli" && npx --no-install tsx "$(basename "$tmpscript")" 2>&1); then
            log_error "Fixture round-trip failed:"
            echo "$result" | while IFS= read -r line; do log_error "  $line"; done
            ERRORS=$((ERRORS + 1))
        else
            echo "$result" | while IFS= read -r line; do log_info "  $line"; done
        fi
    fi
fi

if [[ $ERRORS -gt 0 ]]; then
    log_error ""
    log_error "Config-migrations check failed with $ERRORS error(s)"
    exit 1
fi

log_info "Config-migrations check passed"
exit 0
