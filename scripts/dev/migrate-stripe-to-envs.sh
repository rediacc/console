#!/bin/bash
# One-shot migration: Stripe secrets from org level to per-environment scopes.
#
# Stripe credentials are NOT managed by the rotation tool (see
# private/account/scripts/rotation/lib/config.ts — no Stripe entry). They're
# rotated manually via the Stripe dashboard. So this one-shot script handles
# the env-scope migration once; future manual rotations push to the same envs
# via `gh secret set --env`.
#
# For SES (US/Asia) and OTLP, env-scope is handled by the rotation tool —
# next `./run.sh rotation rotate ses-us` (etc.) pushes to env scope
# automatically per ROTATION_CONFIG.awsSes[].githubSecretEnvScope and the
# OTLP consumer refs in lib/config.ts. No migration script needed; just
# rotate once after merging the workflow YAML changes.
#
# For TURNSTILE_SECRET_KEY, R2_*, CLOUDFLARE_API_TOKEN, GPG_*, ACCOUNT_*,
# AWS_SES_*_EU, DOCKERHUB_*, STRIPE_SANDBOX_*: stay at org level by design
# (used by CI / preview / operator paths that can't access env-scoped
# secrets without declaring `environment:`).
#
# Usage:
#   1. export STRIPE_SECRET_KEY_EU=sk_live_... \
#             STRIPE_SECRET_KEY_US=sk_live_... \
#             STRIPE_SECRET_KEY_ASIA=sk_live_... \
#             STRIPE_WEBHOOK_SECRET_EU=whsec_... \
#             STRIPE_WEBHOOK_SECRET_US=whsec_... \
#             STRIPE_WEBHOOK_SECRET_ASIA=whsec_...
#   2. ./scripts/dev/migrate-stripe-to-envs.sh
#   3. # Verify by triggering promote-stable.yml workflow_dispatch with force=false:
#      gh workflow run promote-stable.yml --ref main
#   4. ./scripts/dev/migrate-stripe-to-envs.sh --remove-from-org
#
# Exits 0 on success, 1 on missing values or push failure.

set -euo pipefail

REPO="rediacc/console"
ORG="rediacc"
REMOVE_FROM_ORG=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --remove-from-org)
            REMOVE_FROM_ORG=true
            shift
            ;;
        --help | -h)
            sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

# (secret_name, target_env) pairs.
#
# STRIPE_SECRET_KEY_EU lives in 3 envs:
#   - edge: cd-v2.yml publish job (env: edge) runs Stripe sync against prod EU
#   - stable: cd-deploy-worker.yml stable target uses it for the www worker
#   - stable-eu: cd-deploy-account.yml matrix-eu when target=stable
# WEBHOOK lives in 2 (no Stripe sync in publish job for webhook):
#   - stable, stable-eu
declare -a MIGRATIONS=(
    "STRIPE_SECRET_KEY_EU:edge"
    "STRIPE_SECRET_KEY_EU:stable"
    "STRIPE_SECRET_KEY_EU:stable-eu"
    "STRIPE_WEBHOOK_SECRET_EU:stable"
    "STRIPE_WEBHOOK_SECRET_EU:stable-eu"

    "STRIPE_SECRET_KEY_US:stable-us"
    "STRIPE_WEBHOOK_SECRET_US:stable-us"
    "STRIPE_SECRET_KEY_ASIA:stable-asia"
    "STRIPE_WEBHOOK_SECRET_ASIA:stable-asia"
)

declare -a SECRET_NAMES=(
    STRIPE_SECRET_KEY_EU STRIPE_SECRET_KEY_US STRIPE_SECRET_KEY_ASIA
    STRIPE_WEBHOOK_SECRET_EU STRIPE_WEBHOOK_SECRET_US STRIPE_WEBHOOK_SECRET_ASIA
)

if [[ "$REMOVE_FROM_ORG" == "true" ]]; then
    echo "==> Deleting Stripe secrets from org-level (after env-scope verification)..."
    for name in "${SECRET_NAMES[@]}"; do
        echo "  - $name"
        gh secret delete --org "$ORG" "$name" || echo "    (already gone or no permission)"
    done
    echo "Done. Verify with: gh secret list --org $ORG | grep -i stripe"
    exit 0
fi

# Validate all values are exported
missing=()
for name in "${SECRET_NAMES[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        missing+=("$name")
    fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "ERROR: missing exports for these env vars:" >&2
    printf '  - %s\n' "${missing[@]}" >&2
    echo "" >&2
    echo "See header of this script for the export block to copy." >&2
    exit 1
fi

echo "==> Pushing ${#MIGRATIONS[@]} (secret, env) pairs to $REPO..."
for pair in "${MIGRATIONS[@]}"; do
    name="${pair%%:*}"
    env="${pair##*:}"
    value="${!name}"
    printf '  %-30s -> env %s ... ' "$name" "$env"
    if printf '%s' "$value" | gh secret set --env "$env" --repo "$REPO" "$name" --body - 2>/dev/null; then
        echo "ok"
    else
        echo "FAILED"
        exit 1
    fi
done

echo ""
echo "Done. Next steps:"
echo "  1. Trigger promote-stable.yml dry-run:"
echo "     gh workflow run promote-stable.yml --ref main"
echo "  2. Inspect deploy logs to confirm env-scoped values resolved per region."
echo "  3. After verification, remove org-level copies:"
echo "     ./scripts/dev/migrate-stripe-to-envs.sh --remove-from-org"
echo ""
echo "For SES (US/Asia) + OTLP env-scope migration: just trigger the rotation"
echo "tool — it now pushes to env scope automatically."
echo "  ./run.sh rotation rotate ses-us"
echo "  ./run.sh rotation rotate ses-asia"
echo "  ./run.sh rotation rotate otlp-eu"
echo "  ./run.sh rotation rotate otlp-us"
echo "  ./run.sh rotation rotate otlp-asia"
