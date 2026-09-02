#!/bin/bash
# Start a throwaway account server for an E2E leg, and mint the API token that
# leg's suite needs.
#
#   .ci/scripts/test/start-account-for-e2e.sh [--port <n>] [--email <addr>]
#                                             [--plan <code>] [--name <label>]
#
# It prints, and (when running under Actions) appends to $GITHUB_ENV:
#
#   REDIACC_ACCOUNT_SERVER   the base URL the CLI should point at
#   E2E_ACCOUNT_API_TOKEN    a bearer token for a subscribed user
#
# WHY THIS EXISTS. Suite 24 (`packages/e2e-tests/tests/kube/24-cluster-licensing`)
# asserts on the licensing pre-flight that refuses a cluster BEFORE anything is
# provisioned. That needs a subscription with a real machine-slot cap, which no
# VM/E2E leg provides, so the suite sat dark, and its own prerequisite gate
# (`declaredSkip`) made that visible rather than silent. This script is the
# smallest thing that satisfies it.
#
# NOT run-account-e2e.sh. That script starts a server AND runs the account
# portal's own Playwright suite, and it requires the org's ED25519/API/JWT
# secrets. Nothing here signs anything a later run has to verify: the server is
# born with the job and dies with it, so throwaway keys are not a compromise,
# they are the correct choice. Nothing is read from `secrets.*`.
#
# TWO ORDERING RULES, both paid for in the campaign drills (scripts/drills/lib.sh):
#
#   1. THE CLI MUST BE THE TOKEN'S FIRST USER. An API token binds to the client
#      IP on FIRST use, and a request arriving through the CLI's E2E tunnel
#      presents a different client IP than a direct curl. So the token is minted
#      over the SESSION (cookie) API and never touched with curl afterwards.
#      Violating this answers 403, which the CLI reports as "This organization
#      requires a passkey to unlock config storage", which is not what happened, and an
#      hour to see through.
#   2. THE SERVER MUST OUTLIVE THE STEP. `setsid` detaches it from the step's
#      process group so the runner's cleanup of that group does not take it
#      with it. The pid recorded in $PID_FILE is resolved from the LISTENING
#      SOCKET after startup, never from `$!`. See the readiness block below.
#
# FAILS LOUD, NEVER QUIET. Every exit path that did not produce a token is a
# non-zero exit with the server log tail attached. A leg whose account server
# did not come up must go red at THIS step, not turn into a suite that skips.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

PORT="${ACCOUNT_API_PORT:-4900}"
EMAIL="e2e-cluster-licensing@rediacc.io"
PLAN="PROFESSIONAL"
TOKEN_NAME="e2e-cluster-licensing"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            PORT="${2:?--port needs a value}"
            shift 2
            ;;
        --email)
            EMAIL="${2:?--email needs a value}"
            shift 2
            ;;
        --plan)
            PLAN="${2:?--plan needs a value}"
            shift 2
            ;;
        --name)
            TOKEN_NAME="${2:?--name needs a value}"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            exit 2
            ;;
    esac
done

REPO_ROOT="$(get_repo_root)"
ACCOUNT_DIR="$REPO_ROOT/private/account"
BASE="http://127.0.0.1:${PORT}/account/api/v1"
LOG_FILE="${RUNNER_TEMP:-/tmp}/account-for-e2e.log"
PID_FILE="${RUNNER_TEMP:-/tmp}/account-for-e2e.pid"
JAR="${RUNNER_TEMP:-/tmp}/account-for-e2e-cookies.txt"
# Chosen, not scraped. The dev credentials banner rotates its password on every
# start, and /test/ensure-login is idempotent, so choosing beats parsing.
PASSWORD="E2eClusterLicensing123!"

if [[ ! -f "$ACCOUNT_DIR/package.json" ]]; then
    log_error "private/account is not checked out; this leg cannot start an account server."
    log_error "The job must check out with submodules: true."
    exit 1
fi

die_with_log() {
    log_error "$1"
    if [[ -f "$LOG_FILE" ]]; then
        log_error "Last 40 lines of $LOG_FILE:"
        tail -40 "$LOG_FILE" >&2 || true
    fi
    exit 1
}

# ---------------------------------------------------------------------------
# Throwaway key material. Generated in-process, never persisted anywhere but
# this server's own environment.
# ---------------------------------------------------------------------------
log_step "Generating throwaway server keys..."
KEYS="$(node -e '
const crypto = require("crypto");
const ed = crypto.generateKeyPairSync("ed25519");
const x = crypto.generateKeyPairSync("x25519");
const der = (k, t) => k.export({ type: t, format: "der" }).toString("base64");
console.log(JSON.stringify({
  edPriv: der(ed.privateKey, "pkcs8"),
  edPub: der(ed.publicKey, "spki"),
  xPriv: der(x.privateKey, "pkcs8"),
  xPub: der(x.publicKey, "spki"),
}));
')"
ACCOUNT_ED25519_PRIVATE_KEY="$(jq -r '.edPriv' <<<"$KEYS")"
ACCOUNT_ED25519_PUBLIC_KEY="$(jq -r '.edPub' <<<"$KEYS")"
ACCOUNT_X25519_PRIVATE_KEY="$(jq -r '.xPriv' <<<"$KEYS")"
ACCOUNT_X25519_PUBLIC_KEY="$(jq -r '.xPub' <<<"$KEYS")"
# envSchema (private/account/src/types/env.ts:18,55) requires >= 32 characters
# for both. Fixed placeholder strings were rejected outright, which is the
# schema doing its job; random 64-hex satisfies it without inventing a secret.
ACCOUNT_SERVER_API_KEY="$(openssl rand -hex 32)"
ACCOUNT_JWT_SECRET="$(openssl rand -hex 32)"

# ---------------------------------------------------------------------------
# The server. ENVIRONMENT is left at the node entry's default; TEST_MODE is the
# only opener for the /test/* seed routes, and deployed Workers never set it.
# ---------------------------------------------------------------------------
log_step "Starting account server on port $PORT..."
# Outside the repo on purpose: private/account only gitignores `account.db*`, so
# a database written into the submodule leaves an untracked file behind.
DB_PATH="${RUNNER_TEMP:-/tmp}/e2e-account-$$.db"
rm -f "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"
(
    cd "$ACCOUNT_DIR"
    setsid env \
        ACCOUNT_ED25519_PRIVATE_KEY="$ACCOUNT_ED25519_PRIVATE_KEY" \
        ACCOUNT_ED25519_PUBLIC_KEY="$ACCOUNT_ED25519_PUBLIC_KEY" \
        ACCOUNT_X25519_PRIVATE_KEY="$ACCOUNT_X25519_PRIVATE_KEY" \
        ACCOUNT_X25519_PUBLIC_KEY="$ACCOUNT_X25519_PUBLIC_KEY" \
        ACCOUNT_SERVER_API_KEY="$ACCOUNT_SERVER_API_KEY" \
        ACCOUNT_JWT_SECRET="$ACCOUNT_JWT_SECRET" \
        ROOT_EMAIL="root@rediacc.invalid" \
        DATABASE_PATH="$DB_PATH" \
        PORT="$PORT" \
        TEST_MODE=true \
        npx tsx src/entry/node.ts >"$LOG_FILE" 2>&1 &
)
log_info "account server starting, log $LOG_FILE"

# THE READINESS TEST IS THE PORT, NOT A PID, and that is not a style choice.
# `npx` FORKS rather than execs, so `$!` here is the npx wrapper and the server
# is its grandchild (measured: launch pid 1155097, tsx 1155113, listener
# 1155124). A `kill -0 $!` liveness check on that pid therefore reports "the
# server exited during startup" for a server that is starting perfectly well:
# a false red that depends on nothing but scheduling. The port is the only
# signal that means what it says, so the loop waits on it for the full budget
# and the log tail explains any timeout.
log_step "Waiting for the account server to answer /health..."
HEALTHY=0
for _ in $(seq 1 60); do
    if curl -sf -m 2 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
done
[[ "$HEALTHY" == "1" ]] || die_with_log "The account server never became healthy on port $PORT within 120s."

# Now that something is listening, record the pid that actually holds the port
# (not the wrapper), so a later step or a local caller can stop the right thing.
SERVER_PID="$(lsof -ti:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [[ -n "$SERVER_PID" ]]; then
    echo "$SERVER_PID" >"$PID_FILE"
    log_info "account server healthy, listener pid $SERVER_PID (recorded in $PID_FILE)"
else
    log_info "account server healthy (no pid resolved; lsof unavailable)"
fi

# ---------------------------------------------------------------------------
# Seed a subscribed user, then mint its token over the cookie session.
# ---------------------------------------------------------------------------
log_step "Seeding a $PLAN subscription for $EMAIL..."
curl -sS -X POST "$BASE/test/ensure-login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" >/dev/null ||
    die_with_log "/test/ensure-login failed (is TEST_MODE on?)"
curl -sS -X POST "$BASE/test/ensure-subscription" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"planCode\":\"$PLAN\"}" >/dev/null ||
    die_with_log "/test/ensure-subscription failed"

rm -f "$JAR"
LOGIN="$(curl -sS -c "$JAR" -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")"
if ! jq -e '.user.id' >/dev/null 2>&1 <<<"$LOGIN"; then
    log_error "Headless login failed: $LOGIN"
    die_with_log "could not open a session for $EMAIL"
fi

SUBSCRIPTION_ID="$(curl -sS -b "$JAR" "$BASE/portal/subscription" | jq -r '.id // empty')"
[[ -n "$SUBSCRIPTION_ID" ]] || die_with_log "no subscription id for $EMAIL after seeding"

MINT="$(curl -sS -b "$JAR" -X POST "$BASE/api-tokens" -H 'Content-Type: application/json' \
    -d "{\"subscriptionId\":\"$SUBSCRIPTION_ID\",\"name\":\"$TOKEN_NAME\",\"scopes\":[\"license:read\",\"license:activate\",\"subscription:read\"]}")"
TOKEN="$(jq -r '.token // empty' <<<"$MINT")"
if [[ -z "$TOKEN" ]]; then
    log_error "API token mint failed: $MINT"
    die_with_log "could not mint an API token"
fi
# From here on nothing but the CLI may present this token (rule 1 in the header).
rm -f "$JAR"

SERVER_URL="http://127.0.0.1:${PORT}"
log_info "subscription $SUBSCRIPTION_ID, token ${TOKEN:0:12}..."

if [[ -n "${GITHUB_ENV:-}" ]]; then
    # Not a `secrets.*` value, so Actions does not mask it on its own. It only
    # opens a localhost server that dies with the job, but an unmasked bearer
    # token in a public repo's logs is a bad habit to model.
    echo "::add-mask::$TOKEN"
    {
        echo "REDIACC_ACCOUNT_SERVER=$SERVER_URL"
        echo "E2E_ACCOUNT_API_TOKEN=$TOKEN"
    } >>"$GITHUB_ENV"
    log_info "exported REDIACC_ACCOUNT_SERVER and E2E_ACCOUNT_API_TOKEN to \$GITHUB_ENV"
fi
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "server-url=$SERVER_URL" >>"$GITHUB_OUTPUT"
fi

# Bare stdout for a local caller: `eval "$(.../start-account-for-e2e.sh | tail -2)"`.
echo "REDIACC_ACCOUNT_SERVER=$SERVER_URL"
echo "E2E_ACCOUNT_API_TOKEN=$TOKEN"
