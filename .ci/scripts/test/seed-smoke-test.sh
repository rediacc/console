#!/bin/bash
# Seed test data into the preview D1 database for license smoke tests.
#
# Creates: user, organization, org membership, subscription, team,
# team membership, and API token with license:activate + license:read scopes.
#
# The API token value is deterministic (derived from PR number) so the
# smoke test script can compute it without secrets.
#
# Usage:
#   PR_NUMBER=123 .ci/scripts/test/seed-smoke-test.sh
#
# Required env:
#   PR_NUMBER                 PR number (for deterministic IDs and token)
#   CLOUDFLARE_API_TOKEN      Wrangler auth
#   CLOUDFLARE_ACCOUNT_ID     Wrangler account
#   ACCOUNT_JWT_SECRET        Used to derive deterministic token hash

set -euo pipefail

: "${PR_NUMBER:?PR_NUMBER is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

DB_NAME="account-db-pr-${PR_NUMBER}"
WORKER_DIR="$ROOT_DIR/workers/www"
NOW="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"

# Deterministic IDs based on PR number
USER_ID="smoke-user-pr-${PR_NUMBER}"
ORG_ID="smoke-org-pr-${PR_NUMBER}"
SUB_ID="smoke-sub-pr-${PR_NUMBER}"
TEAM_ID="smoke-team-pr-${PR_NUMBER}"
TOKEN_ID="smoke-tok-pr-${PR_NUMBER}"
MEMBERSHIP_ID="smoke-mem-pr-${PR_NUMBER}"
TEAM_MEMBERSHIP_ID="smoke-tmem-pr-${PR_NUMBER}"

EMAIL="smoketest-pr${PR_NUMBER}@rediacc.io"
CUSTOMER_ID="cus_smoke_pr_${PR_NUMBER}"

# Generate deterministic token: rdt_smoke_<pr_number>_<jwt_secret_prefix>
# This lets the smoke test script compute the same token from the same inputs.
TOKEN_VALUE="rdt_smoke_${PR_NUMBER}_$(echo -n "${ACCOUNT_JWT_SECRET:-default}" | sha256sum | cut -c1-32)"

# Compute SHA-256 hash of the token (what gets stored in DB)
TOKEN_HASH="$(echo -n "$TOKEN_VALUE" | sha256sum | cut -c1-64)"

# Compute SHA-256 hash of the lowercase email
EMAIL_HASH="$(echo -n "$EMAIL" | tr '[:upper:]' '[:lower:]' | sha256sum | cut -c1-64)"

echo "Seeding smoke test data into $DB_NAME..."
echo "  User: $EMAIL"
echo "  Subscription: $SUB_ID (COMMUNITY)"
echo "  Token hash: ${TOKEN_HASH:0:16}..."

cd "$WORKER_DIR"

# Generate a wrangler config that points to the preview DB
DB_UUID=$(npx wrangler d1 list --json 2>/dev/null | node -e "
  const data = require('fs').readFileSync('/dev/stdin', 'utf8');
  const dbs = JSON.parse(data);
  const db = dbs.find(d => d.name === '${DB_NAME}');
  if (db) console.log(db.uuid);
  else { console.error('Database ${DB_NAME} not found'); process.exit(1); }
")

cat > /tmp/wrangler-seed.toml <<TOML
name = "pr-${PR_NUMBER}"
main = "src/index.ts"
compatibility_date = "2026-01-20"
[[d1_databases]]
binding = "DB"
database_name = "${DB_NAME}"
database_id = "${DB_UUID}"
TOML

# Execute SQL seed (single batch for atomicity)
npx wrangler d1 execute "$DB_NAME" --remote --config /tmp/wrangler-seed.toml --command "
INSERT OR IGNORE INTO users (id, email, email_hash, preferred_language, company_name, role, created_at, updated_at, totp_enabled)
VALUES ('${USER_ID}', '${EMAIL}', '${EMAIL_HASH}', 'en', 'Smoke Test', 'customer', '${NOW}', '${NOW}', 0);

INSERT OR IGNORE INTO organizations (id, name, owner_user_id, customer_id, data_region, created_at, updated_at)
VALUES ('${ORG_ID}', 'Smoke Test Org', '${USER_ID}', '${CUSTOMER_ID}', 'eu', '${NOW}', '${NOW}');

INSERT OR IGNORE INTO org_memberships (id, org_id, user_id, role, joined_at)
VALUES ('${MEMBERSHIP_ID}', '${ORG_ID}', '${USER_ID}', 'owner', '${NOW}');

INSERT OR IGNORE INTO teams (id, org_id, name, slug, is_default, created_at, updated_at)
VALUES ('${TEAM_ID}', '${ORG_ID}', 'Default', 'default', 1, '${NOW}', '${NOW}');

INSERT OR IGNORE INTO team_memberships (id, team_id, user_id, role, joined_at)
VALUES ('${TEAM_MEMBERSHIP_ID}', '${TEAM_ID}', '${USER_ID}', 'member', '${NOW}');

INSERT OR IGNORE INTO subscriptions (id, customer_id, customer_email, type, status, max_activations, plan_code, created_at, updated_at, org_id, repo_license_issuances_usage_adjustment)
VALUES ('${SUB_ID}', '${CUSTOMER_ID}', '${EMAIL}', 'subscription', 'active', 2, 'COMMUNITY', '${NOW}', '${NOW}', '${ORG_ID}', 0);

INSERT OR IGNORE INTO api_tokens (id, name, token_hash, subscription_id, team_id, scopes, created_at, created_by_user_id)
VALUES ('${TOKEN_ID}', 'Smoke Test Token', '${TOKEN_HASH}', '${SUB_ID}', '${TEAM_ID}', '[\"license:activate\",\"license:read\"]', '${NOW}', '${USER_ID}');
"

rm -f /tmp/wrangler-seed.toml

# Output the token value for the smoke test to use
echo "SMOKE_TEST_TOKEN=${TOKEN_VALUE}" >> "$GITHUB_OUTPUT"
echo "Seed complete."
