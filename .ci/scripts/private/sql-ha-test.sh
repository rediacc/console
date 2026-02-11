#!/bin/bash
# SQL HA integration test via renet-provisioned VMs
#
# Usage: .ci/scripts/private/sql-ha-test.sh [--scenarios <list>]
#
# Provisions 3 VMs using renet, deploys SQL Server HA (Always On AG) to each,
# runs HA test scenarios, and cleans up. Designed for CI (GitHub Actions with KVM)
# or local bare-metal testing.
#
# Prerequisites:
#   - renet binary installed (renet ops up)
#   - 3 VMs provisioned and SSH-accessible
#   - SSH key at ~/.ssh/id_ed25519
#   - VM_NET_BASE set (e.g., 192.168.112)
#
# Environment:
#   VM_NET_BASE     - Base IP subnet for VMs (required)
#   SQL_HA_NODES    - Comma-separated VM IDs (default: "11 12 13")
#   SSH_USER        - SSH user for VMs (default: current user)
#   SCENARIOS       - Space-separated list of test-ha scenarios (default: "planned kill recovery integrity")

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
SQL_DIR="$REPO_ROOT/private/sql"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VM_NET_BASE="${VM_NET_BASE:?VM_NET_BASE must be set}"
read -ra SQL_HA_VM_IDS <<<"${SQL_HA_NODES:-11 12 13}"
SSH_USER="${SSH_USER:-$USER}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
SCENARIOS="${SCENARIOS:-planned coordinator-kill kill recovery integrity}"

# Node names (match the standard HA naming)
NODE_NAMES=("sql-1" "sql-2" "sql-3")
NODE_IPS=()
for id in "${SQL_HA_VM_IDS[@]}"; do
    NODE_IPS+=("${VM_NET_BASE}.${id}")
done

REMOTE_SQL_DIR="/home/${SSH_USER}/sql"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ssh() {
    local ip="$1"
    shift
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
        "${SSH_USER}@${ip}" "$@"
}

_scp() {
    scp -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 "$@"
}

# ---------------------------------------------------------------------------
# Phase 1: Deploy SQL HA to VMs
# ---------------------------------------------------------------------------

deploy_sql_ha() {
    log_step "Deploying SQL HA to ${#NODE_IPS[@]} VMs..."

    # Generate SA password once (shared across all nodes)
    local sa_password
    sa_password="SqlHA$(openssl rand -hex 12)!"

    for i in "${!NODE_IPS[@]}"; do
        local ip="${NODE_IPS[$i]}"
        local name="${NODE_NAMES[$i]}"

        log_step "  Deploying to ${name} (${ip})..."

        # Install prerequisites (rsync, jq, Docker)
        _ssh "$ip" "{ command -v rsync && command -v jq; } >/dev/null 2>&1 || { sudo apt-get -qq update && sudo apt-get -qq install -y rsync jq >/dev/null; }"
        _ssh "$ip" "command -v docker >/dev/null 2>&1 || {
            curl -fsSL https://get.docker.com | sh
            sudo usermod -aG docker \$USER
        }"

        # Sync sql directory to VM
        rsync -az --delete \
            -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
            --exclude '.git' \
            --exclude 'mssql*/' \
            --exclude 'terraform/' \
            --exclude 'node_modules/' \
            "$SQL_DIR/" "${SSH_USER}@${ip}:${REMOTE_SQL_DIR}/"

        # Generate .env for this node
        local all_ips
        all_ips=$(
            IFS=','
            echo "${NODE_IPS[*]}"
        )
        local all_nodes="${NODE_NAMES[0]}:sync:primary,${NODE_NAMES[1]}:sync,${NODE_NAMES[2]}:async"

        _ssh "$ip" "cat > ${REMOTE_SQL_DIR}/.env" <<EOF
MSSQL_SA_PASSWORD=${sa_password}
ACCEPT_EULA=Y
HA_NODES=${all_nodes}
HA_MODE=remote
HA_THIS_NODE=${name}
HA_IPS=${all_ips}
HA_SSH_USER=${SSH_USER}
HA_SSH_KEY=${HOME}/.ssh/id_ed25519
HA_PROJECT_DIR=${REMOTE_SQL_DIR}
HA_MEMORY_LIMIT_MB=2048
EOF

        # Create secrets directory with SA password (required before ha up)
        _ssh "$ip" "mkdir -p ${REMOTE_SQL_DIR}/secrets && echo -n '${sa_password}' > ${REMOTE_SQL_DIR}/secrets/sa_password.txt"
    done

    log_step "Distributing SSH keys for inter-node access..."
    for i in "${!NODE_IPS[@]}"; do
        local ip="${NODE_IPS[$i]}"
        # Copy SSH key to each node for inter-node communication
        _scp "$SSH_KEY" "${SSH_USER}@${ip}:${HOME}/.ssh/id_ed25519"
        _scp "${SSH_KEY}.pub" "${SSH_USER}@${ip}:${HOME}/.ssh/id_ed25519.pub"
        _ssh "$ip" "chmod 600 ${HOME}/.ssh/id_ed25519"

        # Add all node IPs to known_hosts
        for peer_ip in "${NODE_IPS[@]}"; do
            _ssh "$ip" "ssh-keyscan -H ${peer_ip} >> ${HOME}/.ssh/known_hosts 2>/dev/null || true"
        done
    done
}

# ---------------------------------------------------------------------------
# Phase 2: Start HA cluster
# ---------------------------------------------------------------------------

start_ha_cluster() {
    log_step "Starting HA cluster..."

    # Start SQL on each node
    for i in "${!NODE_IPS[@]}"; do
        local ip="${NODE_IPS[$i]}"
        local name="${NODE_NAMES[$i]}"
        log_step "  Starting SQL on ${name}..."
        _ssh "$ip" "cd ${REMOTE_SQL_DIR} && ./run.sh ha up"
    done

    # Wait for all SQL instances to be healthy
    log_step "Waiting for SQL instances to become healthy..."
    for i in "${!NODE_IPS[@]}"; do
        local ip="${NODE_IPS[$i]}"
        local name="${NODE_NAMES[$i]}"
        local attempts=0
        while [[ $attempts -lt 24 ]]; do
            if _ssh "$ip" "docker exec sqlserver-ha-${name} /opt/mssql-tools18/bin/sqlcmd \
                -S localhost -U sa -P \"\$(cat ${REMOTE_SQL_DIR}/secrets/sa_password.txt 2>/dev/null || grep MSSQL_SA_PASSWORD ${REMOTE_SQL_DIR}/.env | cut -d= -f2)\" \
                -Q 'SELECT 1' -C" >/dev/null 2>&1; then
                log_step "  ${name}: healthy"
                break
            fi
            sleep 10
            attempts=$((attempts + 1))
        done
        if [[ $attempts -ge 24 ]]; then
            log_error "  ${name}: failed to become healthy after 240s"
            return 1
        fi
    done

    # Harden (from primary node, SSHes to all)
    log_step "Hardening cluster..."
    _ssh "${NODE_IPS[0]}" "cd ${REMOTE_SQL_DIR} && ./run.sh ha harden"

    # Initialize AG (from primary node)
    # AG cert files are created by mssql (UID 10001) with mode 640.
    # A background chmod loop on the primary ensures the SSH user can SCP them to secondaries.
    log_step "Initializing Availability Group..."
    _ssh "${NODE_IPS[0]}" "while true; do sudo chmod -R a+r ${REMOTE_SQL_DIR}/ha-shared/ 2>/dev/null; sleep 0.5; done" &
    local chmod_pid=$!
    _ssh "${NODE_IPS[0]}" "cd ${REMOTE_SQL_DIR} && ./run.sh ha init"
    kill $chmod_pid 2>/dev/null || true
    wait $chmod_pid 2>/dev/null || true

    # Create test database
    log_step "Creating test database..."
    _ssh "${NODE_IPS[0]}" "cd ${REMOTE_SQL_DIR} && ./run.sh ha add-db testdb"

    # Wait for AG synchronization
    log_step "Waiting for AG synchronization..."
    local sync_attempts=0
    while [[ $sync_attempts -lt 12 ]]; do
        local synced
        synced=$(_ssh "${NODE_IPS[0]}" "docker exec sqlserver-ha-${NODE_NAMES[0]} /opt/mssql-tools18/bin/sqlcmd \
            -S localhost -U sqladmin -P \"\$(cat ${REMOTE_SQL_DIR}/secrets/admin_password.txt)\" \
            -Q 'SET NOCOUNT ON; SELECT COUNT(*) FROM sys.dm_hadr_availability_replica_states WHERE synchronization_health_desc = '\''HEALTHY'\''' \
            -C -h -1 -W" 2>/dev/null | tr -d '[:space:]')
        if [[ "$synced" -ge "${#NODE_IPS[@]}" ]] 2>/dev/null; then
            log_step "AG fully synchronized (${synced} healthy replicas)"
            break
        fi
        sleep 10
        sync_attempts=$((sync_attempts + 1))
    done

    if [[ $sync_attempts -ge 12 ]]; then
        log_warn "AG not fully synced after 120s, proceeding anyway"
    fi
}

# ---------------------------------------------------------------------------
# Phase 2b: Deploy coordinator service
# ---------------------------------------------------------------------------

# Coordinator API key (generated once, shared across all nodes)
COORD_API_KEY=""

deploy_coordinator() {
    log_step "Deploying HA Coordinator on ${NODE_NAMES[2]}..."

    # Generate API key (min 32 chars required by coordinator)
    COORD_API_KEY="CoordCI$(openssl rand -hex 16)"

    local coord_ip="${NODE_IPS[2]}"
    local coord_url="http://${coord_ip}:3000"

    # Build CLUSTER_NODES in coordinator format: "name:mode:ip,..."
    local cluster_nodes="${NODE_NAMES[0]}:sync:${NODE_IPS[0]},${NODE_NAMES[1]}:sync:${NODE_IPS[1]},${NODE_NAMES[2]}:async:${NODE_IPS[2]}"

    # Export environment for coordinator docker-compose on sql-3
    _ssh "$coord_ip" "cat > ${REMOTE_SQL_DIR}/coordinator/.env" <<EOF
CLUSTER_NODES=${cluster_nodes}
API_KEY=${COORD_API_KEY}
HA_DOMAIN=sql.ci.local
CLUSTER_ID=ci-test
INITIAL_PRIMARY=${NODE_NAMES[0]}
PORT=3000
RUSTFS_ACCESS_KEY=rustfsadmin
RUSTFS_SECRET_KEY=rustfsadmin
LEASE_TTL_MS=120000
MIN_STABLE_DURATION_MS=15000
HEARTBEAT_TIMEOUT_MS=10000
EOF

    # Create CI override for rustfs:
    #  - user "0": rustfs runs as non-root but can't write to fresh Docker named volumes
    #  - healthcheck: rustfs returns 403 on /minio/health/live, use TCP check instead
    _ssh "$coord_ip" "cat > ${REMOTE_SQL_DIR}/coordinator/docker-compose.override.yml" <<'OVERRIDE'
services:
  rustfs:
    user: "0"
    healthcheck:
      test: ["CMD", "sh", "-c", "nc -z 127.0.0.1 9000"]
      interval: 5s
      timeout: 3s
      retries: 10
      start_period: 10s
OVERRIDE

    # Start coordinator via docker-compose (builds image, starts rustfs + coordinator)
    # Retry up to 3 times to handle transient Docker Hub network errors
    log_step "  Building and starting coordinator containers..."
    local build_ok=false
    for attempt in 1 2 3; do
        if _ssh "$coord_ip" "cd ${REMOTE_SQL_DIR}/coordinator && docker compose up --build -d" 2>&1; then
            build_ok=true
            break
        fi
        log_step "  Build attempt ${attempt} failed, retrying in 10s..."
        sleep 10
    done
    if ! $build_ok; then
        log_error "  Coordinator build failed after 3 attempts"
        return 1
    fi

    # Wait for coordinator to become healthy
    log_step "  Waiting for coordinator to become healthy..."
    local attempts=0
    while [[ $attempts -lt 30 ]]; do
        if _ssh "$coord_ip" "curl -sf -H 'X-API-Key: ${COORD_API_KEY}' http://localhost:3000/api/v1/state" >/dev/null 2>&1; then
            log_step "  Coordinator is healthy"
            break
        fi
        sleep 5
        attempts=$((attempts + 1))
    done
    if [[ $attempts -ge 30 ]]; then
        log_error "  Coordinator failed to become healthy after 150s"
        _ssh "$coord_ip" "cd ${REMOTE_SQL_DIR}/coordinator && docker compose logs" 2>/dev/null || true
        return 1
    fi

    # Append coordinator settings to each VM's .env
    log_step "  Configuring watchdog on all nodes..."
    for ip in "${NODE_IPS[@]}"; do
        _ssh "$ip" "cat >> ${REMOTE_SQL_DIR}/.env" <<EOF
COORDINATOR_URL=${coord_url}
COORDINATOR_API_KEY=${COORD_API_KEY}
COORDINATOR_FALLBACK=refuse
WATCHDOG_STARTUP_GRACE=15
EOF
    done

    log_step "Coordinator deployed at ${coord_url}"
}

# ---------------------------------------------------------------------------
# Phase 3: Run HA test scenarios
# ---------------------------------------------------------------------------

run_ha_tests() {
    log_step "Running HA test scenarios: ${SCENARIOS}"

    # The test-ha.sh script expects TF_* variables and TF_DEPLOY_KEY.
    # We set them from our renet VM info and source the script.
    export HA_NODES="${NODE_NAMES[0]}:sync:primary,${NODE_NAMES[1]}:sync,${NODE_NAMES[2]}:async"
    export HA_MODE=remote
    export HA_IPS
    HA_IPS=$(
        IFS=','
        echo "${NODE_IPS[*]}"
    )
    export HA_SSH_USER="${SSH_USER}"
    export HA_SSH_KEY="${SSH_KEY}"
    export HA_PROJECT_DIR="${REMOTE_SQL_DIR}"

    # Populate TF_* variables that test-ha.sh expects
    export TF_NODE_NAMES=("${NODE_NAMES[@]}")
    export TF_IPS=("${NODE_IPS[@]}")
    export TF_DEPLOY_KEY="${SSH_KEY}"
    export TF_NODE_COUNT=${#NODE_NAMES[@]}

    # Source the sql .env for MSSQL_SA_PASSWORD (needed by test helpers)
    # The admin password is on disk after hardening
    export SCRIPT_DIR="$SQL_DIR"

    cd "$SQL_DIR"

    # Copy admin password from primary (generated during harden)
    log_step "Fetching admin password from primary..."
    mkdir -p "$SQL_DIR/secrets"
    _scp "${SSH_USER}@${NODE_IPS[0]}:${REMOTE_SQL_DIR}/secrets/admin_password.txt" "$SQL_DIR/secrets/admin_password.txt"

    # Set defaults for optional vars expected by ha.sh/test-ha.sh
    export HA_DOMAINS="${HA_DOMAINS:-}"
    export HA_THIS_NODE="${HA_THIS_NODE:-${NODE_NAMES[0]}}"
    export ACCEPT_EULA="${ACCEPT_EULA:-Y}"
    export MSSQL_SA_PASSWORD="${MSSQL_SA_PASSWORD:-unused}"

    # Export coordinator settings for test-ha.sh coordinator scenarios
    if [ -n "$COORD_API_KEY" ]; then
        export COORDINATOR_URL="http://${NODE_IPS[2]}:3000"
        export COORDINATOR_API_KEY="$COORD_API_KEY"
    fi

    # Source the test-ha script functions
    source "$SQL_DIR/commands/terraform.sh" 2>/dev/null || true
    source "$SQL_DIR/commands/ha.sh" 2>/dev/null || true
    source "$SQL_DIR/commands/test-ha.sh"

    # Re-export TF_DEPLOY_KEY (terraform.sh overwrites it with terraform path)
    export TF_DEPLOY_KEY="${SSH_KEY}"

    # Override _tf_parse_nodes since we already have the data
    _tf_parse_nodes() {
        TF_NODE_NAMES=("${NODE_NAMES[@]}")
        TF_NODE_COUNT=${#NODE_NAMES[@]}
        TF_PRIMARY="${NODE_NAMES[0]}"
    }

    # Override _tf_get_ips since we already have the data
    _tf_get_ips() {
        TF_IPS=("${NODE_IPS[@]}")
    }

    # Override _tha_ssh: test-ha.sh defaults to root@, we use SSH_USER@
    _tha_ssh() {
        local node="$1"
        shift
        local ip
        ip=$(_tha_node_ip "$node") || return 1
        ssh -i "$TF_DEPLOY_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            "${SSH_USER}@${ip}" "$@"
    }

    # Override _tha_remote_run: use correct remote sql directory
    _tha_remote_run() {
        local node="$1"
        shift
        _tha_ssh "$node" "cd ${REMOTE_SQL_DIR} && ./run.sh $*"
    }

    # Override _tha_sql: use correct user and pass admin_pass via SSH
    _tha_sql() {
        local node="$1"
        local sql="$2"
        local extra="${3:-}"
        local admin_pass
        admin_pass=$(cat "$SCRIPT_DIR/secrets/admin_password.txt" 2>/dev/null)
        local ip
        ip=$(_tha_node_ip "$node") || return 1
        echo "$sql" | ssh -i "$TF_DEPLOY_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            "${SSH_USER}@${ip}" "docker exec -i sqlserver-ha-${node} /opt/mssql-tools18/bin/sqlcmd \
            -U sqladmin -P '${admin_pass}' -C ${extra}"
    }

    # Override _tha_scenario_coordinator_down: fix hardcoded /root/sqlserver path
    _tha_scenario_coordinator_down() {
        echo "=== Scenario: coordinator-down — no autonomous failover when coordinator is down ==="
        echo ""

        local primary
        primary=$(_tha_find_primary)
        _tha_info "Current primary: ${primary}"

        # Start watchdogs with a bogus coordinator URL (simulates coordinator being down)
        local bogus_url="http://10.255.255.1:9999"
        for node in "${TF_NODE_NAMES[@]}"; do
            _tha_ssh "$node" "cd ${REMOTE_SQL_DIR} && \
                COORDINATOR_URL='${bogus_url}' \
                COORDINATOR_API_KEY='dummy-key-32-chars-for-validation!!' \
                COORDINATOR_FALLBACK=refuse \
                ./run.sh ha watchdog start" >/dev/null 2>&1
        done
        _tha_info "Watchdogs started with unreachable coordinator (fallback=refuse)"

        sleep 10

        _tha_info "Stopping SQL container on ${primary}..."
        _tha_ssh "$primary" "docker stop sqlserver-ha-${primary}" >/dev/null 2>&1

        _tha_info "Waiting 60s — failover should NOT happen..."
        sleep 60

        local candidates=0
        for node in "${TF_NODE_NAMES[@]}"; do
            [ "$node" = "$primary" ] && continue
            local role
            role=$(_tha_sql "$node" "SET NOCOUNT ON; SELECT role_desc FROM sys.dm_hadr_availability_replica_states WHERE is_local = 1" "-h -1 -W -t 5" 2>/dev/null | tr -d '[:space:]')
            if [ "$role" = "PRIMARY" ]; then
                candidates=$((candidates + 1))
            fi
        done
        _tha_assert "No node promoted to PRIMARY (coordinator-down + refuse)" test "$candidates" -eq 0

        _tha_ssh "$primary" "docker start sqlserver-ha-${primary}" >/dev/null 2>&1
        sleep 30

        for node in "${TF_NODE_NAMES[@]}"; do
            _tha_remote_run "$node" "ha watchdog stop" >/dev/null 2>&1
        done
    }

    # Override preflight to skip Terraform state check
    _tha_preflight() {
        _tf_parse_nodes
        _tf_get_ips

        # Verify SSH access to all nodes
        for node in "${TF_NODE_NAMES[@]}"; do
            local ip
            ip=$(_tha_node_ip "$node") || return 1
            if _tha_ssh "$node" "echo ok" >/dev/null 2>&1; then
                _tha_info "${node}: SSH OK"
            else
                echo -e "\e[31mError: Cannot SSH to ${node} (${ip})\e[0m"
                return 1
            fi
        done

        # Build test image locally
        echo "Building test client image..."
        docker build -q -t sqlserver-client-test "$SQL_DIR/client-test" || return 1
        echo ""
    }

    # Sync coordinator state with actual cluster primary.
    # After scenarios that bypass the coordinator (e.g., ha failover), the coordinator's
    # internal primary can diverge from reality. Reset coordinator with fresh state.
    _sync_coordinator_state() {
        [ -z "$COORD_API_KEY" ] && return 0
        local actual_primary
        actual_primary=$(_tha_find_primary 2>/dev/null) || return 0
        local coord_primary
        coord_primary=$(_tha_coordinator_primary 2>/dev/null)
        if [ "$coord_primary" != "$actual_primary" ]; then
            log_step "  Coordinator primary mismatch (coord=${coord_primary:-?} actual=${actual_primary}), resetting..."
            local coord_ip="${NODE_IPS[2]}"
            # Update INITIAL_PRIMARY in .env and restart coordinator with fresh state
            _ssh "$coord_ip" "cd ${REMOTE_SQL_DIR}/coordinator && \
                sed -i 's/^INITIAL_PRIMARY=.*/INITIAL_PRIMARY=${actual_primary}/' .env && \
                docker compose down -v && docker compose up -d" 2>&1 || true
            # Wait for coordinator to become healthy
            local wait=0
            while [ $wait -lt 60 ]; do
                if _ssh "$coord_ip" "curl -sf -H 'X-API-Key: ${COORD_API_KEY}' http://localhost:3000/api/v1/state" >/dev/null 2>&1; then
                    break
                fi
                sleep 5
                wait=$((wait + 5))
            done
            log_step "  Coordinator restarted with primary=${actual_primary}"
        fi
    }

    # Run each scenario
    local rc=0
    for scenario in $SCENARIOS; do
        log_step "Running scenario: ${scenario}"
        _tha_pass=0
        _tha_fail=0
        _tha_skip=0

        _tha_preflight || {
            rc=1
            continue
        }
        _tha_ensure_healthy_cluster
        _sync_coordinator_state

        local fn="_tha_scenario_${scenario//-/_}"
        if declare -f "$fn" >/dev/null 2>&1; then
            "$fn" || true
            echo ""
            _tha_summary || rc=1
        else
            log_error "Unknown scenario: ${scenario}"
            rc=1
        fi
        echo ""
    done

    return $rc
}

# ---------------------------------------------------------------------------
# Phase 4: Cleanup
# ---------------------------------------------------------------------------

cleanup_ha() {
    log_step "Cleaning up HA cluster..."

    for i in "${!NODE_IPS[@]}"; do
        local ip="${NODE_IPS[$i]}"
        local name="${NODE_NAMES[$i]}"
        log_step "  Cleaning up ${name}..."
        # Kill watchdog processes, then kill+rm all containers, then delete data.
        # Each step uses timeout to avoid hanging (docker kill can be slow on SQL containers).
        _ssh "$ip" "pgrep -u ${SSH_USER} -f _wd_main_loop | xargs -r kill" 2>/dev/null || true
        timeout 30 ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            "${SSH_USER}@${ip}" "docker kill \$(docker ps -q) 2>/dev/null; true" 2>/dev/null || true
        timeout 30 ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
            "${SSH_USER}@${ip}" "docker rm -f \$(docker ps -aq) 2>/dev/null; docker network prune -f 2>/dev/null; docker volume prune -f 2>/dev/null; true" 2>/dev/null || true
        _ssh "$ip" "sudo rm -rf ${REMOTE_SQL_DIR}" 2>/dev/null || true
    done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    # Parse args
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --scenarios)
                SCENARIOS="$2"
                shift 2
                ;;
            --deploy-only)
                deploy_sql_ha
                start_ha_cluster
                deploy_coordinator
                exit 0
                ;;
            --test-only)
                run_ha_tests
                exit $?
                ;;
            --cleanup-only)
                cleanup_ha
                exit 0
                ;;
            *)
                log_error "Unknown arg: $1"
                exit 1
                ;;
        esac
    done

    # Full flow: cleanup stale state → deploy → test → cleanup
    local test_rc=0

    # Ensure cleanup runs on any exit (including errors/signals)
    trap 'cleanup_ha || true' EXIT

    # Pre-cleanup: remove stale containers/data from previous failed runs
    cleanup_ha || true

    deploy_sql_ha
    start_ha_cluster
    deploy_coordinator
    run_ha_tests || test_rc=$?

    exit $test_rc
}

main "$@"
