#!/bin/bash
# Account service development functions
# Sourced lazily by run.sh when 'account' command is invoked
#
# Provides: account_dev, account_stop, account_test, account_reset, account_rotation

# Prevent re-sourcing
[[ -n "${ACCOUNT_LIB_LOADED:-}" ]] && return 0
readonly ACCOUNT_LIB_LOADED=1

# Source port utilities
source "$CI_LIB_DIR/find-port.sh"

# =============================================================================
# INTERNAL HELPERS
# =============================================================================

ACCOUNT_DIR="$CONSOLE_ROOT_DIR/private/account"
ACCOUNT_PIDS=()

account_cleanup() {
    local exit_code=$?
    for pid in "${ACCOUNT_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    done
    ACCOUNT_PIDS=()
    rm -f "$ACCOUNT_STATE_FILE"
    exit "$exit_code"
}

# Find 3 consecutive free ports starting from preferred base
account_allocate_ports() {
    local base

    # PINNED inside the devbox. The reverse proxy routes to these ports through
    # STATIC container labels, so an allocator that quietly drifts to the next
    # free triple breaks the -portal and -www routes with a 502 that blames the
    # backend. A container is an isolated network namespace, so there is nothing
    # to collide with; a port that IS busy in there means a leftover process,
    # which must be surfaced rather than routed around.
    if [[ -n "${REDIACC_DEV_PORT_BASE:-}" ]]; then
        base="$REDIACC_DEV_PORT_BASE"
        local offset
        for offset in 0 1 2; do
            if is_port_in_use $((base + offset)); then
                log_error "Port $((base + offset)) is already in use inside this environment"
                log_info "REDIACC_DEV_PORT_BASE pins the ports so the proxy labels stay valid; free it rather than drifting"
                log_info "Leftovers: pkill -f 'astro dev'; pkill -f 'vite --port'; pkill -f dev-gateway.ts"
                exit 1
            fi
        done
        GATEWAY_PORT=$base
        VITE_PORT=$((base + 1))
        ASTRO_PORT=$((base + 2))
        export GATEWAY_PORT VITE_PORT ASTRO_PORT
        return 0
    fi

    base=$(find_preferred_port "$ACCOUNT_DEV_PORT_PREFERRED" \
        "$ACCOUNT_DEV_PORT_PREFERRED" "$ACCOUNT_DEV_PORT_RANGE_END")

    # Verify next 2 ports are also free; if not, scan for 3 consecutive
    if is_port_in_use $((base + 1)) || is_port_in_use $((base + 2)); then
        local found=false
        for candidate in $(seq "$ACCOUNT_DEV_PORT_PREFERRED" "$ACCOUNT_DEV_PORT_RANGE_END"); do
            if ! is_port_in_use "$candidate" &&
                ! is_port_in_use $((candidate + 1)) &&
                ! is_port_in_use $((candidate + 2)); then
                base=$candidate
                found=true
                break
            fi
        done
        if [[ "$found" != "true" ]]; then
            log_error "Cannot find 3 consecutive free ports in range ${ACCOUNT_DEV_PORT_PREFERRED}-${ACCOUNT_DEV_PORT_RANGE_END}"
            exit 1
        fi
    fi

    GATEWAY_PORT=$base
    VITE_PORT=$((base + 1))
    ASTRO_PORT=$((base + 2))
    export GATEWAY_PORT VITE_PORT ASTRO_PORT
}

# Wait for a port to become active (max timeout seconds).
#
# The timeout is a floor, not a verdict: as long as the process is still ALIVE
# it keeps waiting, and only a dead process (or REDIACC_STARTUP_TIMEOUT being
# exceeded with no process to watch) is reported as a failure. A fixed ceiling
# is wrong on slow hardware, and the failure it produces is a lie -- on an arm64
# Crostini box Astro's content sync took 114.8s against a 90s wait, so
# `account dev` aborted and printed "Astro failed to start" about a server that
# was starting normally and came up seconds later.
#
# Pass the watched pid as $4 to get the alive-check; without it the timeout is
# absolute. REDIACC_STARTUP_TIMEOUT overrides the default everywhere.
account_wait_port() {
    local port="$1"
    local name="$2"
    local timeout="${3:-${REDIACC_STARTUP_TIMEOUT:-30}}"
    local watch_pid="${4:-}"
    local elapsed=0
    local announced=false

    while true; do
        if is_port_in_use "$port"; then
            return 0
        fi

        if [[ $elapsed -ge $timeout ]]; then
            # Past the nominal budget. Keep going while the process lives,
            # saying so once so a slow start does not look like a hang.
            if [[ -n "$watch_pid" ]] && kill -0 "$watch_pid" 2>/dev/null; then
                if [[ "$announced" == false ]]; then
                    log_warn "$name is slower than ${timeout}s on this machine; still starting (pid $watch_pid)"
                    log_info "Set REDIACC_STARTUP_TIMEOUT to raise the initial budget"
                    announced=true
                fi
            else
                log_error "$name failed to start on port $port within ${timeout}s"
                [[ -n "$watch_pid" ]] && log_error "its process (pid $watch_pid) is no longer running"
                log_info "Check logs: $ACCOUNT_LOG_DIR/"
                return 1
            fi
        fi

        sleep 1
        elapsed=$((elapsed + 1))
    done
}

# True when a RustFS (S3) endpoint is answering on the port. RustFS returns 403
# on GET / (no anonymous access), so any HTTP status — not just 2xx — means the
# service is up; a closed port yields curl code 000.
#
# Do NOT reintroduce `|| echo 000` here. curl ALREADY prints 000 on a refused
# connection and exits non-zero, so the fallback appended a second one and the
# captured value became "000000" — which is != "000", so this reported ALIVE for
# a dead port. Everything downstream believed it: account_dev logged "Reusing
# RustFS already serving", never started the container, still exported
# CONFIG_R2_*, and the gateway advertised a config store that answered
# ECONNREFUSED on first use.
#
# `|| true` is the repo's established shape for this — .ci/breakpoint/scripts/
# {start-tunnel,hold-breakpoint,reap-breakpoint-orphans}.sh all document the same
# trap. It also keeps the assignment from aborting under `set -e`, which today is
# masked only because both callers invoke this inside an `if`. An empty value
# (curl absent) counts as dead.
account_rustfs_alive() {
    local port="$1"
    local code
    code=$(curl -s -o /dev/null -m 2 -w '%{http_code}' "http://127.0.0.1:${port}/" 2>/dev/null || true)
    [[ -n "$code" && "$code" != "000" ]]
}

# Force-remove ghost RustFS containers by name. A corrupt `docker compose`
# project state can leave containers that block a fresh recreate but survive a
# plain `docker rm` — `rm -f` clears them. Best-effort and never touches the
# live :9100 reuse path (a running RustFS must survive).
account_docker_ghost_clean() {
    command -v docker &>/dev/null || return 0
    docker info &>/dev/null || return 0
    local ids
    ids=$(docker ps -aq --filter "name=account-config-rustfs" --filter "name=rediacc-config-rustfs-dev" 2>/dev/null || true)
    [[ -n "$ids" ]] && echo "$ids" | xargs docker rm -f >/dev/null 2>&1 || true
    return 0
}

# =============================================================================
# ENSURE .ENV
# =============================================================================

account_generate_crypto_keys() {
    # Ed25519
    local keys
    keys=$(node --eval "
        const crypto = require('crypto');
        const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
        const priv = privateKey.export({ type: 'pkcs8', format: 'der' }).toString('base64');
        const pub = publicKey.export({ type: 'spki', format: 'der' }).toString('base64');
        process.stdout.write(priv + '\n' + pub);
    ")
    ED25519_PRIV=$(echo "$keys" | head -1)
    ED25519_PUB=$(echo "$keys" | tail -1)

    # X25519
    local x25519_keys
    x25519_keys=$(node --eval "
        const crypto = require('crypto');
        const { privateKey, publicKey } = crypto.generateKeyPairSync('x25519');
        const priv = privateKey.export({ type: 'pkcs8', format: 'der' }).toString('base64');
        const pub = publicKey.export({ type: 'spki', format: 'der' }).toString('base64');
        process.stdout.write(priv + '\n' + pub);
    ")
    X25519_PRIV=$(echo "$x25519_keys" | head -1)
    X25519_PUB=$(echo "$x25519_keys" | tail -1)

    # Random secrets
    JWT_SEC=$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-64)
    API_K=$(openssl rand -base64 48 | tr -d '/+=' | cut -c1-64)
}

account_generate_fresh_env() {
    log_step "Generating account .env..."
    account_generate_crypto_keys

    cat >"$ACCOUNT_DIR/.env" <<EOF
# Auto-generated by ./run.sh — $(date -u +%Y-%m-%dT%H:%M:%SZ)

# Account server URL (used by rdc CLI for subscription commands)
# Updated automatically by dev-gateway on startup with the actual port
REDIACC_ACCOUNT_SERVER=http://localhost:4800

# SQLite database path
DATABASE_PATH=account.db

# Ed25519 key pair (for subscription/license signing)
ACCOUNT_ED25519_PRIVATE_KEY=${ED25519_PRIV}
ACCOUNT_ED25519_PUBLIC_KEY=${ED25519_PUB}

# X25519 key pair (for E2E encryption)
ACCOUNT_X25519_PRIVATE_KEY=${X25519_PRIV}
ACCOUNT_X25519_PUBLIC_KEY=${X25519_PUB}

# Admin API key
ACCOUNT_SERVER_API_KEY=${API_K}

# JWT secret for session tokens
ACCOUNT_JWT_SECRET=${JWT_SEC}

# Stripe sandbox (uncomment and fill to enable Stripe features)
# STRIPE_SANDBOX_SECRET_KEY=sk_test_...
# STRIPE_SANDBOX_WEBHOOK_SECRET is auto-captured from stripe listen

# Fixed webhook secret for E2E webhook simulation tests. Deliberately NOT named
# STRIPE_WEBHOOK_SECRET: Bitwarden holds a real production secret under that
# name, and one fetch-by-name away this fixture slot would have received it.
STRIPE_E2E_WEBHOOK_SECRET=whsec_e2e_test_webhook_secret_for_simulation_only

# Root email (receives alerts for disputes, refunds, etc.)
# Set via GitHub variable ROOT_EMAIL or environment
ROOT_EMAIL="${ROOT_EMAIL:-}"

# Server port (used by standalone node entry, not the dev gateway)
PORT=3000

# WebAuthn passkey (for config storage setup)
WEBAUTHN_RP_ID=localhost
WEBAUTHN_RP_NAME=Rediacc
WEBAUTHN_ORIGIN=http://localhost:4800
EOF

    log_info "Generated private/account/.env with fresh keys"
}

# Append a key=value to .env if the key doesn't already exist
account_env_add_if_missing() {
    local key="$1" value="$2" comment="${3:-}"
    local env_file="$ACCOUNT_DIR/.env"
    if ! grep -q "^${key}=" "$env_file" 2>/dev/null; then
        [[ -n "$comment" ]] && echo -e "\n# ${comment}" >>"$env_file"
        echo "${key}=${value}" >>"$env_file"
        return 0
    fi
    return 1
}

# Ensure all required keys exist in .env, adding any that are missing
account_ensure_env_keys() {
    local env_file="$ACCOUNT_DIR/.env"
    local added=0

    # Generate keys only if we actually need them
    local need_gen=false
    for key in ACCOUNT_ED25519_PRIVATE_KEY ACCOUNT_ED25519_PUBLIC_KEY ACCOUNT_X25519_PRIVATE_KEY ACCOUNT_X25519_PUBLIC_KEY ACCOUNT_SERVER_API_KEY ACCOUNT_JWT_SECRET; do
        if ! grep -q "^${key}=" "$env_file" 2>/dev/null; then
            need_gen=true
            break
        fi
    done

    if [[ "$need_gen" == "true" ]]; then
        account_generate_crypto_keys

        account_env_add_if_missing "ACCOUNT_ED25519_PRIVATE_KEY" "$ED25519_PRIV" "Ed25519 key pair (for subscription/license signing)" && added=1
        account_env_add_if_missing "ACCOUNT_ED25519_PUBLIC_KEY" "$ED25519_PUB" && added=1
        account_env_add_if_missing "ACCOUNT_X25519_PRIVATE_KEY" "$X25519_PRIV" "X25519 key pair (for E2E encryption)" && added=1
        account_env_add_if_missing "ACCOUNT_X25519_PUBLIC_KEY" "$X25519_PUB" && added=1
        account_env_add_if_missing "ACCOUNT_SERVER_API_KEY" "$API_K" "Admin API key" && added=1
        account_env_add_if_missing "ACCOUNT_JWT_SECRET" "$JWT_SEC" "JWT secret for session tokens" && added=1
    fi

    # Non-crypto defaults (only added if missing, never overridden)
    account_env_add_if_missing "REDIACC_ACCOUNT_SERVER" "http://localhost:4800" "Account server URL" && added=1
    account_env_add_if_missing "DATABASE_PATH" "account.db" "SQLite database path" && added=1
    account_env_add_if_missing "STRIPE_E2E_WEBHOOK_SECRET" "whsec_e2e_test_webhook_secret_for_simulation_only" "E2E webhook-simulation fixture (not a credential)" && added=1
    account_env_add_if_missing "PORT" "3000" "Server port" && added=1
    # Account server's own outbound OTel endpoint (dev-gateway only; CF
    # Workers use native tracing in prod). The CLI/renet client credentials
    # are served at runtime from `OBS_OTLP_CREDENTIALS`, which the
    # rotation tool writes here during `./run.sh rotation rotate otlp-<region>`.
    account_env_add_if_missing "OTEL_ENDPOINT" "https://otlp.rediacc.io" "OTel OTLP endpoint" && added=1
    # WebAuthn passkey (for config storage setup)
    account_env_add_if_missing "WEBAUTHN_RP_ID" "localhost" "WebAuthn Relying Party ID" && added=1
    account_env_add_if_missing "WEBAUTHN_RP_NAME" "Rediacc" "WebAuthn display name" && added=1
    account_env_add_if_missing "WEBAUTHN_ORIGIN" "http://localhost:${GATEWAY_PORT:-4800}" "WebAuthn origin URL" && added=1
    # Note: ROOT_EMAIL, STRIPE_SANDBOX_SECRET_KEY, AWS_SES_* are user-set values
    # — only created in fresh generation, never added/overridden on ensure/reset

    if [[ $added -gt 0 ]]; then
        log_info "Added missing keys to existing .env"
    fi
}

account_ensure_env() {
    if [[ ! -f "$ACCOUNT_DIR/.env" ]]; then
        account_generate_fresh_env
        return 0
    fi

    # Ensure any newly added keys are present
    account_ensure_env_keys
}

# =============================================================================
# STRIPE AUTO-SETUP
# =============================================================================

account_stripe_auto() {
    local stripe_key="${STRIPE_SANDBOX_SECRET_KEY:-}"
    if [[ -z "$stripe_key" ]]; then
        return 0
    fi

    # Check stripe CLI
    if ! command -v stripe &>/dev/null; then
        log_warn "STRIPE_SANDBOX_SECRET_KEY is set but stripe CLI not found"
        log_info "Install from: https://docs.stripe.com/stripe-cli"
        log_info "Continuing without webhook forwarding"
        return 0
    fi

    log_step "Setting up Stripe sandbox..."

    # Kill any orphaned stripe listen forwarding to this worktree's gateway port.
    # This handles cases where a previous session crashed without cleanup.
    local stale_pids
    stale_pids=$(pgrep -f "stripe listen.*--forward-to http://localhost:${GATEWAY_PORT}/" 2>/dev/null || true)
    if [[ -n "$stale_pids" ]]; then
        log_info "Cleaning up stale stripe listen (PIDs: $stale_pids)"
        echo "$stale_pids" | xargs kill 2>/dev/null || true
        sleep 1
    fi

    # Sync products/prices (idempotent)
    log_info "Syncing Stripe products/prices..."
    (cd "$ACCOUNT_DIR" && STRIPE_SECRET_KEY="$stripe_key" npx tsx scripts/stripe-sync.ts 2>&1 | tail -5)

    # Start stripe listen in background
    local stripe_log
    stripe_log=$(mktemp)

    stripe listen \
        --api-key "$stripe_key" \
        --forward-to "http://localhost:${GATEWAY_PORT}/account/api/v1/webhooks/stripe" \
        >"$stripe_log" 2>&1 &
    local stripe_pid=$!
    ACCOUNT_PIDS+=("$stripe_pid")

    # Wait for webhook secret
    local webhook_secret=""
    local elapsed=0
    while [[ $elapsed -lt 30 ]]; do
        webhook_secret=$(grep -oE 'whsec_[^[:space:]]+' "$stripe_log" 2>/dev/null || true)
        if [[ -n "$webhook_secret" ]]; then
            break
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    rm -f "$stripe_log"

    if [[ -z "$webhook_secret" ]]; then
        log_warn "stripe listen did not output webhook secret within 30s"
        log_info "Stripe features may not work — check stripe CLI auth"
        return 0
    fi

    export STRIPE_SANDBOX_WEBHOOK_SECRET="$webhook_secret"
    log_info "Stripe webhook forwarding active (secret: ${webhook_secret:0:12}...)"
}

# =============================================================================
# PUBLIC COMMANDS
# =============================================================================

account_dev() {
    check_node_version

    # Auto-kill previous instance from this worktree
    if [[ -f "$ACCOUNT_STATE_FILE" ]]; then
        local old_gateway old_pids
        old_gateway=$(grep "^gateway_port=" "$ACCOUNT_STATE_FILE" 2>/dev/null | cut -d= -f2)
        old_pids=$(grep "^pids=" "$ACCOUNT_STATE_FILE" 2>/dev/null | cut -d= -f2)
        log_step "Stopping previous account instance (gateway:${old_gateway:-?})..."

        # Kill tracked child PIDs (vite, astro)
        if [[ -n "$old_pids" ]]; then
            for pid in ${old_pids//,/ }; do
                kill "$pid" 2>/dev/null || true
            done
        fi

        # Kill anything on the gateway port and its 2 siblings (gateway, vite, astro)
        if [[ -n "$old_gateway" ]]; then
            for offset in 0 1 2; do
                local port=$((old_gateway + offset))
                local port_pids
                # `|| true`: lsof exits 1 when nothing listens (e.g. a stale
                # state file from a dead session), which would abort under set -e.
                port_pids=$(lsof -ti:"$port" 2>/dev/null || true)
                if [[ -n "$port_pids" ]]; then
                    echo "$port_pids" | xargs kill -9 2>/dev/null || true
                fi
            done
        fi

        sleep 2 # Let OS reclaim ports
        rm -f "$ACCOUNT_STATE_FILE"
        log_info "Previous instance stopped"
    fi

    log_step "Starting account development environment"

    # Allocate dynamic ports
    account_allocate_ports
    log_info "Ports: gateway=$GATEWAY_PORT vite=$VITE_PORT astro=$ASTRO_PORT"

    # Generate .env if needed
    account_ensure_env

    # Load environment
    set -a
    source "$ACCOUNT_DIR/.env"
    set +a

    # Dependencies
    ensure_deps

    # Install account + web deps if needed
    if [[ ! -d "$ACCOUNT_DIR/node_modules" ]] ||
        [[ "$ACCOUNT_DIR/package-lock.json" -nt "$ACCOUNT_DIR/node_modules" ]]; then
        log_step "Installing account dependencies..."
        (cd "$ACCOUNT_DIR" && npm install --prefer-offline --no-audit --no-fund 2>&1 | tail -1)
    fi

    if [[ ! -d "$ACCOUNT_DIR/web/node_modules" ]] ||
        [[ ! -d "$ACCOUNT_DIR/web/node_modules/react-router-dom" ]] ||
        [[ "$ACCOUNT_DIR/web/package-lock.json" -nt "$ACCOUNT_DIR/web/node_modules" ]]; then
        log_step "Installing account web dependencies..."
        (cd "$ACCOUNT_DIR/web" && npm install --prefer-offline --no-audit --no-fund 2>&1 | tail -1)
    fi

    # Ensure shared packages are built (account depends on @rediacc/shared)
    ensure_packages_built

    # Setup cleanup trap
    trap account_cleanup EXIT INT TERM

    # Create log directory
    mkdir -p "$ACCOUNT_LOG_DIR"

    # Start config blob storage (RustFS) if Docker is available. The web console's
    # config store (key slots, proxy, etc.) needs this; without it the portal shows
    # "Config storage not configured on this server".
    if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
        log_step "Starting config blob storage (RustFS)..."
        local rustfs_port=9100
        local rustfs_key="${CONFIG_R2_ACCESS_KEY_ID:-configadmin}"
        local rustfs_secret="${CONFIG_R2_SECRET_ACCESS_KEY:-configadmin}"

        # Reuse a RustFS already serving on the canonical port. This survives a
        # corrupt `docker compose` project state (dangling/ghost containers that
        # block recreate but cannot be `docker rm`'d without a daemon restart):
        # a plain `docker run` of the same image on 9100 is picked up here.
        if account_rustfs_alive "$rustfs_port"; then
            log_info "Reusing RustFS already serving on port ${rustfs_port}"
        else
            # Best-effort clean of stale project containers so a fresh recreate
            # is not blocked by a prior run's leftovers. Only reached when no
            # RustFS is serving on the port, so a live instance is never touched.
            account_docker_ghost_clean
            export CONFIG_RUSTFS_PORT=$rustfs_port
            (cd "$ACCOUNT_DIR" && CONFIG_RUSTFS_PORT=$rustfs_port \
                docker compose up -d config-rustfs config-rustfs-init) \
                >"$ACCOUNT_LOG_DIR/rustfs.log" 2>&1 || true
            account_wait_port "$rustfs_port" "RustFS" 30 || true
        fi

        if account_rustfs_alive "$rustfs_port"; then
            export CONFIG_R2_ENDPOINT="http://127.0.0.1:${rustfs_port}"
            export CONFIG_R2_BUCKET="rediacc-configs"
            export CONFIG_R2_ACCESS_KEY_ID="$rustfs_key"
            export CONFIG_R2_SECRET_ACCESS_KEY="$rustfs_secret"
            # Ensure the bucket exists (compose's init does this too, but the
            # reuse path skips it).
            docker run --rm --network host \
                -e AWS_ACCESS_KEY_ID="$rustfs_key" -e AWS_SECRET_ACCESS_KEY="$rustfs_secret" \
                -e AWS_DEFAULT_REGION=us-east-1 amazon/aws-cli s3api create-bucket \
                --bucket rediacc-configs --endpoint-url "http://127.0.0.1:${rustfs_port}" \
                >/dev/null 2>&1 || true
            log_info "Config blob storage: http://127.0.0.1:${rustfs_port}/rediacc-configs"
        else
            log_warn "RustFS failed to start (config storage disabled). If 'docker compose' is stuck on a ghost container, run: docker run -d --name rediacc-config-rustfs-dev -p 9100:9000 -e RUSTFS_VOLUMES=/data -e RUSTFS_ADDRESS=0.0.0.0:9000 -e RUSTFS_ACCESS_KEY=configadmin -e RUSTFS_SECRET_KEY=configadmin rustfs/rustfs:latest"
        fi
    else
        log_info "Docker not available — config blob storage disabled"
    fi

    # Start Astro dev server (marketing site)
    log_step "Starting Astro dev server on :${ASTRO_PORT}..."
    # Bind address: loopback on a host, 0.0.0.0 inside the devbox. The devbox
    # sets REDIACC_DEV_BIND because the reverse proxy reaches these servers over
    # the container network -- a 127.0.0.1 bind is invisible to it, and the
    # symptom is a 502 from Traefik rather than anything pointing at the bind.
    local dev_bind="${REDIACC_DEV_BIND:-127.0.0.1}"
    (cd "$CONSOLE_ROOT_DIR/packages/www" && npx astro dev --port "$ASTRO_PORT" --host "$dev_bind") \
        >"$ACCOUNT_LOG_DIR/astro.log" 2>&1 &
    local astro_pid=$!
    ACCOUNT_PIDS+=("$astro_pid")

    # Start Vite dev server (account portal SPA)
    log_step "Starting Vite dev server on :${VITE_PORT}..."
    (cd "$ACCOUNT_DIR/web" && npx vite --port "$VITE_PORT" --host "$dev_bind") \
        >"$ACCOUNT_LOG_DIR/vite.log" 2>&1 &
    local vite_pid=$!
    ACCOUNT_PIDS+=("$vite_pid")

    # Wait for both to be ready
    # Cold caches are slow: Astro's first content sync alone can take ~30s.
    account_wait_port "$ASTRO_PORT" "Astro" 90 "$astro_pid" || exit 1
    account_wait_port "$VITE_PORT" "Vite" 60 "$vite_pid" || exit 1

    # Auto-setup Stripe if key is configured
    account_stripe_auto

    # Save state for auto-kill on next ./run.sh account dev
    {
        echo "gateway_port=$GATEWAY_PORT"
        echo "pids=${ACCOUNT_PIDS[*]// /,}"
        echo "worktree=$CONSOLE_ROOT_DIR"
        echo "started=$(date +%s)"
    } >"$ACCOUNT_STATE_FILE"

    # Provision + print dev login credentials once the gateway is healthy
    account_dev_credentials "$GATEWAY_PORT" &

    # Start gateway (foreground — keeps terminal alive). Precompute the WebAuthn
    # origin so its ${GATEWAY_PORT} isn't expanded from the same env-prefix that
    # (re)assigns GATEWAY_PORT (that ordering is a shellcheck SC2097/SC2098 trap).
    local webauthn_origin="http://localhost:${GATEWAY_PORT}"
    log_step "Starting dev gateway on :${GATEWAY_PORT}..."
    (cd "$ACCOUNT_DIR" &&
        GATEWAY_PORT=$GATEWAY_PORT \
            VITE_PORT=$VITE_PORT \
            ASTRO_PORT=$ASTRO_PORT \
            CONFIG_R2_ENDPOINT="${CONFIG_R2_ENDPOINT:-}" \
            CONFIG_R2_BUCKET="${CONFIG_R2_BUCKET:-}" \
            CONFIG_R2_ACCESS_KEY_ID="${CONFIG_R2_ACCESS_KEY_ID:-}" \
            CONFIG_R2_SECRET_ACCESS_KEY="${CONFIG_R2_SECRET_ACCESS_KEY:-}" \
            WEBAUTHN_RP_ID="localhost" \
            WEBAUTHN_ORIGIN="$webauthn_origin" \
            npx tsx src/entry/dev-gateway.ts)
}

# Provision three dev logins (root / customer / partner) with fresh random
# passwords, seed the partner org with demo data, and print a credentials
# block. Runs in the background from account_dev: waits for the gateway
# health endpoint, then drives the dev-only /test routes (unmounted in
# production). Passwords rotate on every start by design.
account_dev_credentials() {
    local gateway_port="$1"
    local base="http://127.0.0.1:${gateway_port}/account/api/v1"

    local i healthy=0
    for i in $(seq 1 60); do
        if curl -sf -m 2 "http://127.0.0.1:${gateway_port}/health" >/dev/null 2>&1; then
            healthy=1
            break
        fi
        sleep 2
    done
    if [[ $healthy -ne 1 ]]; then
        log_warn "Gateway not healthy after 120s; skipped dev login provisioning"
        return 0
    fi

    local root_email="${ROOT_EMAIL:-root@rediacc.dev}"
    local user_email="dev-user@rediacc.io"
    local partner_email="dev-partner@rediacc.io"
    local root_pw user_pw partner_pw
    root_pw=$(openssl rand -hex 8)
    user_pw=$(openssl rand -hex 8)
    partner_pw=$(openssl rand -hex 8)

    local ok=1
    curl -sf -X POST "$base/test/ensure-login" -H 'Content-Type: application/json' \
        -d "{\"email\":\"$root_email\",\"password\":\"$root_pw\"}" >/dev/null 2>&1 || ok=0
    curl -sf -X POST "$base/test/ensure-login" -H 'Content-Type: application/json' \
        -d "{\"email\":\"$user_email\",\"password\":\"$user_pw\"}" >/dev/null 2>&1 || ok=0
    curl -sf -X POST "$base/test/ensure-login" -H 'Content-Type: application/json' \
        -d "{\"email\":\"$partner_email\",\"password\":\"$partner_pw\"}" >/dev/null 2>&1 || ok=0
    # Give the dev user a PROFESSIONAL plan so paid surfaces (the web console,
    # gated on PLAN_METADATA[plan].webConsole) are reachable in dev. Idempotent.
    curl -sf -X POST "$base/test/ensure-subscription" -H 'Content-Type: application/json' \
        -d "{\"email\":\"$user_email\",\"planCode\":\"PROFESSIONAL\"}" >/dev/null 2>&1 || ok=0
    # Partner demo data (idempotent; re-runs append a fresh batch)
    curl -sf -X POST "$base/test/seed-demo-partner" -H 'Content-Type: application/json' \
        -d "{\"email\":\"$partner_email\"}" >/dev/null 2>&1 || ok=0

    if [[ $ok -ne 1 ]]; then
        log_warn "Dev login provisioning failed (see gateway log); logins may be stale"
        return 0
    fi

    # Seed a fully unlockable config store for the dev user so the web console is
    # usable with a known password on a fresh start. This is a CONSTANT password
    # (never rotated): an idempotent re-seed cannot re-wrap the CEK without the
    # prior password, so a fixed one keeps re-runs working. Best-effort and does
    # NOT gate the login banner below — config storage needs RustFS (Docker), so
    # a Docker-less dev box still gets its logins printed.
    local store_pw="DevConsole123!"
    local seed_json seed_existing="" seed_recovery="" seed_totp=""
    seed_json=$(curl -sf -X POST "$base/test/seed-config-store" -H 'Content-Type: application/json' \
        -d "{\"email\":\"$user_email\",\"password\":\"$store_pw\"}" 2>/dev/null || true)
    if [[ -n "$seed_json" ]]; then
        {
            read -r seed_existing
            read -r seed_recovery
            read -r seed_totp
        } < <(node -e 'const d=JSON.parse(require("fs").readFileSync(0,"utf8")||"{}");console.log(d.existing?1:0);console.log(d.recoveryCode||"");console.log(d.totpSecret||"")' <<<"$seed_json" 2>/dev/null || true)
    fi

    # 65 box-drawing dashes for the borders. account_banner_row's %-63s pads by
    # BYTES, so every content string below stays ASCII-only — a multibyte glyph
    # (arrow / em dash) would shift the closing bar left and break the box.
    local rule
    rule=$(printf '─%.0s' $(seq 1 65))

    local recovery_display
    if [[ "$seed_existing" == "1" ]]; then
        recovery_display="issued on first seed (unchanged)"
    else
        recovery_display="${seed_recovery:-<unavailable>}"
    fi

    local lan_ip
    lan_ip=$(hostname -I 2>/dev/null | awk '{print $1}')

    echo ""
    echo "  ┌${rule}┐"
    account_banner_row "Dev logins (fresh passwords each start)"
    echo "  ├${rule}┤"
    account_banner_row "$(printf 'root     %-32s %s' "$root_email" "$root_pw")"
    account_banner_row "$(printf 'user     %-32s %s' "$user_email" "$user_pw")"
    account_banner_row "$(printf 'partner  %-32s %s' "$partner_email" "$partner_pw")"
    echo "  ├${rule}┤"
    account_banner_row "Portal:   http://localhost:${gateway_port}/account/login"
    account_banner_row "Console:  http://localhost:${gateway_port}/account/console"
    if [[ -n "$lan_ip" ]]; then
        account_banner_row "Network:  http://${lan_ip}:${gateway_port}/account/login"
        account_banner_row "          (LAN reachable; no passkeys over LAN)"
    fi
    echo "  ├${rule}┤"
    account_banner_row "Store password:  ${store_pw}"
    account_banner_row "Recovery code:   ${recovery_display}"
    if [[ -n "$seed_totp" ]]; then
        account_banner_row "2FA code:        ./run.sh account totp"
        account_banner_row "2FA secret:      ${seed_totp}"
    else
        account_banner_row "2FA:             config storage disabled (Docker needed)"
    fi
    echo "  ├${rule}┤"
    account_banner_row "root    -> /account/admin    (operator)"
    account_banner_row "partner -> /account/partner  (seeded demo data)"
    account_banner_row "user    -> /account/console  (PROFESSIONAL + config store)"
    echo "  └${rule}┘"
    echo ""
}

# One padded banner row inside the 65-col box drawn by account_dev_credentials /
# account_totp: 2-space indent, a border bar, 2 spaces, then a 63-wide field.
account_banner_row() {
    printf "  │  %-63s│\n" "$1"
}

# Print the current TOTP code for a dev user (default dev-user@rediacc.io). Reads
# the running gateway's port from the state file — the store + TOTP secret are
# seeded by `account dev`, so the gateway must be up. Dev-only route.
account_totp() {
    local email="${1:-dev-user@rediacc.io}"
    if [[ ! -f "$ACCOUNT_STATE_FILE" ]]; then
        log_error "No running dev gateway (state file absent). Start it: ./run.sh account dev"
        exit 1
    fi
    local gateway_port
    gateway_port=$(grep "^gateway_port=" "$ACCOUNT_STATE_FILE" 2>/dev/null | cut -d= -f2)
    if [[ -z "$gateway_port" ]]; then
        log_error "Could not read gateway port from ${ACCOUNT_STATE_FILE}"
        exit 1
    fi

    local url="http://127.0.0.1:${gateway_port}/account/api/v1/test/totp-code"
    local json
    json=$(curl -sf -m 5 -G "$url" --data-urlencode "email=${email}" 2>/dev/null || true)
    if [[ -z "$json" ]]; then
        log_error "No TOTP code for '${email}'. Has ./run.sh account dev seeded a config store?"
        exit 1
    fi

    local code seconds
    {
        read -r code
        read -r seconds
    } < <(node -e 'const d=JSON.parse(require("fs").readFileSync(0,"utf8")||"{}");console.log(d.code||"");console.log(d.secondsRemaining??"")' <<<"$json" 2>/dev/null || true)
    if [[ -z "$code" ]]; then
        log_error "No TOTP code for '${email}'. Has ./run.sh account dev seeded a config store?"
        exit 1
    fi

    log_info "TOTP for ${email}: ${code}  (${seconds}s remaining)"
}

account_stop() {
    log_step "Stopping account services"

    # Kill dev processes tracked in state file
    if [[ -f "$ACCOUNT_STATE_FILE" ]]; then
        local old_gateway old_pids
        old_gateway=$(grep "^gateway_port=" "$ACCOUNT_STATE_FILE" 2>/dev/null | cut -d= -f2)
        old_pids=$(grep "^pids=" "$ACCOUNT_STATE_FILE" 2>/dev/null | cut -d= -f2)
        if [[ -n "$old_pids" ]]; then
            for pid in ${old_pids//,/ }; do
                kill "$pid" 2>/dev/null || true
            done
            sleep 1
            for pid in ${old_pids//,/ }; do
                kill -9 "$pid" 2>/dev/null || true
            done
        fi
        if [[ -n "$old_gateway" ]]; then
            local port_pid
            port_pid=$(lsof -ti:"$old_gateway" 2>/dev/null | head -1)
            [[ -n "$port_pid" ]] && kill -9 "$port_pid" 2>/dev/null || true
        fi
    fi

    # Stop Docker containers
    (cd "$ACCOUNT_DIR" && docker compose down --remove-orphans) 2>/dev/null || true

    local containers=(account-server)
    for container in "${containers[@]}"; do
        if docker ps -a --format "{{.Names}}" 2>/dev/null | grep -q "^${container}$"; then
            docker stop "$container" 2>/dev/null || true
            docker rm "$container" 2>/dev/null || true
        fi
    done

    # RustFS config-store containers (including ghosts a corrupt compose state
    # leaves behind) are force-removed by name.
    account_docker_ghost_clean

    rm -f "$ACCOUNT_STATE_FILE"
    log_info "Account services stopped"
}

account_test() {
    check_node_version

    ensure_packages_built

    log_step "Running account tests"
    (cd "$ACCOUNT_DIR" && npx vitest run "$@")
}

account_test_e2e() {
    check_node_version

    # Load backend .env to extract secrets for E2E tests
    local account_env="$ACCOUNT_DIR/.env"
    if [[ ! -f "$account_env" ]]; then
        log_error "Account .env not found. Run: ./run.sh account reset"
        exit 1
    fi

    set -a
    source "$account_env"
    set +a

    # Check dev gateway is running
    local gateway_port="${GATEWAY_PORT:-}"
    if [[ -z "$gateway_port" ]]; then
        # Try to detect from REDIACC_ACCOUNT_SERVER
        gateway_port=$(echo "${REDIACC_ACCOUNT_SERVER:-}" | grep -oP ':\K[0-9]+' || echo "")
    fi

    if [[ -z "$gateway_port" ]]; then
        log_error "Cannot determine gateway port"
        log_info "Start the dev gateway first: ./run.sh account dev"
        exit 1
    fi

    if ! is_port_in_use "$gateway_port"; then
        log_error "Dev gateway not running on port $gateway_port"
        log_info "Start it first: ./run.sh account dev"
        exit 1
    fi

    # Wire backend secrets → E2E env vars
    export E2E_PORT="$gateway_port"
    export E2E_BASE_URL="http://localhost:${gateway_port}/account/"
    export ROOT_EMAIL="${ROOT_EMAIL:-}"

    # Webhook simulation secret (matches backend's STRIPE_WEBHOOK_SECRET)
    if [[ -n "${STRIPE_E2E_WEBHOOK_SECRET:-}" ]]; then
        export E2E_WEBHOOK_SECRET="$STRIPE_E2E_WEBHOOK_SECRET"
        log_info "Webhook simulation: enabled (STRIPE_E2E_WEBHOOK_SECRET)"
    else
        log_warn "Webhook simulation: disabled (STRIPE_E2E_WEBHOOK_SECRET not set)"
    fi

    # Stripe sandbox key (for real Stripe E2E tests)
    if [[ -n "${STRIPE_SANDBOX_SECRET_KEY:-}" ]]; then
        export STRIPE_SANDBOX_SECRET_KEY
        log_info "Stripe sandbox E2E: enabled"
    else
        log_warn "Stripe sandbox E2E: disabled (STRIPE_SANDBOX_SECRET_KEY not set)"
    fi

    ensure_packages_built

    # Install E2E deps if needed
    local e2e_dir="$ACCOUNT_DIR/e2e"
    if [[ ! -d "$e2e_dir/node_modules" ]] ||
        [[ "$e2e_dir/package-lock.json" -nt "$e2e_dir/node_modules" ]]; then
        log_step "Installing E2E dependencies..."
        (cd "$e2e_dir" && npm install --prefer-offline --no-audit --no-fund 2>&1 | tail -1)
    fi

    log_step "Running account E2E tests (gateway on :${gateway_port})"
    (cd "$e2e_dir" && npx playwright test --project=chromium --reporter=list "$@")
}

account_reset() {
    check_node_version

    log_step "Resetting account development environment"

    local env_file="$ACCOUNT_DIR/.env"

    if [[ -f "$env_file" ]]; then
        # Regenerate crypto keys in-place, preserving user-added values
        log_info "Regenerating crypto keys (preserving user values)..."
        account_generate_crypto_keys

        _sed_i "s|^ACCOUNT_ED25519_PRIVATE_KEY=.*|ACCOUNT_ED25519_PRIVATE_KEY=${ED25519_PRIV}|" "$env_file"
        _sed_i "s|^ACCOUNT_ED25519_PUBLIC_KEY=.*|ACCOUNT_ED25519_PUBLIC_KEY=${ED25519_PUB}|" "$env_file"
        _sed_i "s|^ACCOUNT_X25519_PRIVATE_KEY=.*|ACCOUNT_X25519_PRIVATE_KEY=${X25519_PRIV}|" "$env_file"
        _sed_i "s|^ACCOUNT_X25519_PUBLIC_KEY=.*|ACCOUNT_X25519_PUBLIC_KEY=${X25519_PUB}|" "$env_file"
        _sed_i "s|^ACCOUNT_JWT_SECRET=.*|ACCOUNT_JWT_SECRET=${JWT_SEC}|" "$env_file"
        _sed_i "s|^ACCOUNT_SERVER_API_KEY=.*|ACCOUNT_SERVER_API_KEY=${API_K}|" "$env_file"

        # Ensure any newly added keys exist
        account_ensure_env_keys
    else
        account_generate_fresh_env
    fi

    # Reset database
    local db_path="$ACCOUNT_DIR/account.db"
    for f in "$db_path" "$db_path-shm" "$db_path-wal" "$db_path-journal"; do
        if [[ -f "$f" ]]; then
            log_info "Removing $(basename "$f")"
            rm -f "$f"
        fi
    done

    echo ""
    log_info "Account reset complete!"
    log_info ""
    log_info "Start dev server with: ./run.sh account dev"
}

# Populate a demo partner org end-to-end against the running dev gateway.
# Usage: ./run.sh account seed-demo <email> [--port N]
# The port defaults to the running dev gateway's port (from the state file),
# then falls back to the preferred dev port.
account_seed_demo() {
    local email="" port=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --port)
                port="$2"
                shift 2
                ;;
            --port=*)
                port="${1#*=}"
                shift
                ;;
            -*)
                log_error "Unknown option: $1"
                echo "Usage: ./run.sh account seed-demo <email> [--port N]"
                exit 1
                ;;
            *)
                if [[ -z "$email" ]]; then
                    email="$1"
                else
                    log_error "Unexpected argument: $1"
                    echo "Usage: ./run.sh account seed-demo <email> [--port N]"
                    exit 1
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$email" ]]; then
        log_error "Missing email"
        echo "Usage: ./run.sh account seed-demo <email> [--port N]"
        exit 1
    fi

    # Resolve the gateway port: explicit --port wins, else the running dev
    # gateway's port from the state file, else the preferred default.
    if [[ -z "$port" && -f "$ACCOUNT_STATE_FILE" ]]; then
        port=$(grep "^gateway_port=" "$ACCOUNT_STATE_FILE" 2>/dev/null | cut -d= -f2)
    fi
    port="${port:-$ACCOUNT_DEV_PORT_PREFERRED}"

    local url="http://127.0.0.1:${port}/account/api/v1/test/seed-demo-partner"
    log_step "Seeding demo partner '${email}' via ${url}"

    local body http_code curl_exit json_payload
    json_payload=$(jq -n --arg email "$email" '{email: $email}')
    body=$(curl -sS -m 60 -w $'\n%{http_code}' \
        -H 'Content-Type: application/json' \
        -d "$json_payload" \
        "$url")
    curl_exit=$?
    http_code="${body##*$'\n'}"
    body="${body%$'\n'*}"

    if [[ $curl_exit -ne 0 ]]; then
        log_error "Could not reach the account gateway on port ${port}"
        log_info "Is the dev gateway running? Start it with: ./run.sh account dev"
        exit 1
    fi

    if [[ "$http_code" != "200" ]]; then
        log_error "Seed failed (HTTP ${http_code})"
        echo "$body" | jq . 2>/dev/null || echo "$body"
        log_info "Is the dev gateway running? Start it with: ./run.sh account dev"
        exit 1
    fi

    log_info "Demo partner seeded"
    echo "$body" | jq . 2>/dev/null || echo "$body"
}

# =============================================================================
# ROTATION (secret rotation lifecycle for AWS IAM, CF tokens, CF Turnstile)
# =============================================================================
# Thin bash wrapper around the TypeScript rotation CLI in
# private/account/scripts/rotation/. All actual logic — manifest read/write,
# platform calls, state transitions — lives in TS so it's type-checked,
# testable, and stays inside the private submodule (the public console repo
# does not contain rotation orchestration).
#
# Invoked from run.sh as: ./run.sh rotation <subcommand> [args]
#
# See /home/muhammed/.claude/plans/steady-munching-seal.md for the full design.
account_rotation() {
    check_node_version
    cd "$ACCOUNT_DIR" || exit 1
    npx tsx scripts/rotation/index.ts "$@"
}

# =============================================================================
# ACCOUNT DEV DATABASE BROWSER
# =============================================================================

# Browse the dev database in the browser.
#
# The dev database is NOT wrangler/D1, despite wrangler.toml declaring one:
# `account dev` runs src/entry/dev-gateway.ts, which opens better-sqlite3 on
# DATABASE_PATH (default account.db) with cwd=private/account. So the file that
# actually holds dev data is private/account/account.db.
#
# DEFAULT IS A SELF-HOSTED UI, and that is a deliberate reversal. Drizzle Studio
# was the first choice, but its local process serves only an API -- the UI is
# hosted at local.drizzle.studio, and a real browser proved that Chrome's Local
# Network Access restriction blocks that public page from reaching a local
# server. Drizzle's own page says so: "Recent Chrome/Chromium updates may block
# local network access by default. This prevents Drizzle Studio from accessing
# Drizzle Kit on local host." No proxy change can fix that; it needs a per-site
# browser permission. sqlite_web serves its UI from the SAME origin as the data,
# so there is no third-party page and nothing to grant.
#
# `--studio` keeps the Drizzle Studio behaviour for anyone who wants its
# schema-aware view and is willing to grant that permission.
account_db() {
    check_node_version

    local use_studio=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --studio)
                use_studio=true
                shift
                ;;
            *)
                log_error "Unknown option for account db: $1"
                return 2
                ;;
        esac
    done

    local db_path="${DATABASE_PATH:-$ACCOUNT_DIR/account.db}"
    if [[ ! -f "$db_path" ]]; then
        log_error "No dev database at $db_path"
        log_info "Start the stack once so it gets created and migrated: ./run.sh account dev"
        return 1
    fi

    # shellcheck source=/dev/null
    source "$CONSOLE_ROOT_DIR/.ci/lib/find-port.sh"

    # Prefer this worktree's devbox slot so the URL is stable and two worktrees
    # can browse at once. Then STEP ASIDE if it is taken: when the browser runs
    # on the host while the devbox is up, docker-proxy already holds that port.
    local preferred=4983
    if [[ -f "$DEVBOX_STATE_FILE" ]]; then
        # ONE PARSER FOR .devbox-state, not two. This used to hand-roll
        # `sed -n 's/^base_port=//p'` -- a byte-for-byte reimplementation of
        # devbox_state_get (.ci/lib/devbox.sh) -- which was tolerable only while
        # the format never changed. It changed: a `slug=` key was added, and a
        # format with two independent readers is one edit away from them
        # disagreeing.
        #
        # devbox.sh sources only find-port.sh, which this file already sources,
        # so pulling it in adds no constants.sh readonly hazard. Guarded so a
        # second source is a no-op, because check-account-probes.sh sources this
        # file standalone under `set +eu` and that path is documented as fragile.
        if ! declare -F devbox_state_get >/dev/null 2>&1; then
            # shellcheck source=./devbox.sh
            # BLOCKER: devbox_state_get is the single reader for .devbox-state
            source "$CONSOLE_ROOT_DIR/.ci/lib/devbox.sh" 2>/dev/null || true
        fi
        local base=""
        if declare -F devbox_state_get >/dev/null 2>&1; then
            base="$(devbox_state_get base_port || true)"
        fi
        [[ -n "$base" ]] && preferred=$((base + ${DEVBOX_OFFSET_STUDIO:-3}))
    fi
    local port
    port="$(find_preferred_port "$preferred" "$((preferred + 1))" "$((preferred + 40))")" || {
        log_error "No free port near $preferred for the database browser"
        return 1
    }

    log_warn "Note: ./run.sh account reset DELETES this database."

    if [[ "$use_studio" == true ]]; then
        if [[ ! -d "$ACCOUNT_DIR/node_modules" ]]; then
            log_step "Installing account dependencies (drizzle-kit)..."
            (cd "$ACCOUNT_DIR" && npm install --prefer-offline --no-audit --no-fund 2>&1 | tail -1)
        fi
        log_step "Drizzle Studio (API only) on $db_path"
        log_info "UI: https://local.drizzle.studio/?port=${port}&host=<the host you reach this on>"
        log_warn "Chrome blocks that hosted page from reaching a local server unless you enable"
        log_warn "\"Local network access\" for local.drizzle.studio in Site information."
        cd "$ACCOUNT_DIR" || return 1
        DATABASE_PATH="$db_path" npx drizzle-kit studio --port "$port" --host 0.0.0.0
        return $?
    fi

    local sqlite_web="${HOME}/.local/bin/sqlite_web"
    if [[ ! -x "$sqlite_web" ]]; then
        if command -v sqlite_web &>/dev/null; then
            sqlite_web="$(command -v sqlite_web)"
        elif command -v uv &>/dev/null; then
            log_step "Installing sqlite-web (one-time)"
            uv tool install sqlite-web >/dev/null 2>&1 || {
                log_error "Could not install sqlite-web; retry with: ./run.sh account db --studio"
                return 1
            }
        else
            log_error "sqlite-web is not installed and uv is unavailable"
            log_info "Use ./run.sh account db --studio instead"
            return 1
        fi
    fi

    log_step "Database browser on $db_path"
    log_info "Port: $port"
    echo ""
    exec "$sqlite_web" --host 0.0.0.0 --port "$port" --no-browser "$db_path"
}
