#!/bin/bash
# Curated-repo healthcheck smoke test.
#
# Deploys the app-postgres template on the worker VM and asserts that
# its container healthcheck converges to `healthy` within a bounded
# window. The healthcheck (`pg_isready -h localhost`) traverses the
# eBPF connect4 rewrite path (127.0.0.1 → SERVICE_IP4), so a regression
# that breaks the rewrite contract — the class of bug that hid behind
# nextcloud-talk's 3-day silent failure — surfaces here at PR time.
#
# Why this complements the unit-level eBPF tests:
#   - `pkg/ebpf/socket_isolation_e2e_test.go` proves bind/connect rewrites
#     work in isolation against synthetic listeners.
#   - This script proves a real Docker container with a real healthcheck,
#     under the production rdc orchestration path, actually reaches
#     "healthy" state. Catches integration regressions the unit tests
#     can miss (e.g., compose wrapper drops --wait, healthcheck command
#     missing from the image, network namespace setup ordering changes).
#
# Usage:
#   .ci/scripts/private/compose-healthcheck-smoke-test.sh
#
# Inputs (env):
#   VM_NET_BASE  — VM subnet base (default 192.168.111)
#   VM_WORKERS   — Worker IDs (default "11"; first ID is used)
#   SSH_USER     — SSH user (default $USER)
#   SSH_KEY      — SSH key path (default ~/.ssh/id_ed25519)
#   MACHINE_NAME — rdc machine alias (default worker-1)
#   TIMEOUT_SECS — Max seconds to wait for db to reach healthy (default 120)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

VM_NET_BASE="${VM_NET_BASE:-192.168.111}"
read -ra WORKER_IDS <<<"${VM_WORKERS:-11}"
VM_IP="${VM_NET_BASE}.${WORKER_IDS[0]}"
SSH_USER="${SSH_USER:-${USER:-$(whoami)}}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
MACHINE_NAME="${MACHINE_NAME:-worker-1}"
TIMEOUT_SECS="${TIMEOUT_SECS:-120}"

REPO_NAME="healthcheck-smoke"

_ssh() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
        "${SSH_USER}@${VM_IP}" "$@"
}

cleanup() {
    log_step "Cleanup (best-effort)"
    rdc repo down --name "$REPO_NAME" -m "$MACHINE_NAME" 2>/dev/null || true
    rdc repo delete --name "$REPO_NAME" -m "$MACHINE_NAME" --force 2>/dev/null || true
}
trap cleanup EXIT

# -------------------------------------------------------------------------
# Phase 0 — register worker VM with rdc CLI (idempotent)
# -------------------------------------------------------------------------
log_step "Registering worker $VM_IP as machine '$MACHINE_NAME'"
rdc config ssh set --key "$SSH_KEY" >/dev/null
rdc config machine add --name "$MACHINE_NAME" --ip "$VM_IP" --user "$SSH_USER" 2>/dev/null ||
    log_warn "Machine '$MACHINE_NAME' already registered (continuing)"
log_step "Provisioning renet on worker (rdc config machine setup)"
rdc config machine setup --name "$MACHINE_NAME"

# Pre-clean any debris from prior runs so create doesn't conflict
cleanup

# -------------------------------------------------------------------------
# Phase 1 — bring up app-postgres (db has pg_isready healthcheck on localhost)
# -------------------------------------------------------------------------
log_step "Creating repo + applying app-postgres template"
rdc repo create --name "$REPO_NAME" -m "$MACHINE_NAME" --size 2G
rdc repo template apply --name app-postgres -m "$MACHINE_NAME" -r "$REPO_NAME"

log_step "Bringing repo up (db must converge to healthy via pg_isready)"
rdc repo up --name "$REPO_NAME" -m "$MACHINE_NAME"

# -------------------------------------------------------------------------
# Phase 2 — poll db's healthcheck status until healthy or timeout
# -------------------------------------------------------------------------
log_step "Polling db healthcheck (timeout ${TIMEOUT_SECS}s)"

# Find the per-repo Docker socket. Network IDs are integers but their
# allocation is not stable across runs, so glob and pick the youngest
# socket that owns a container named 'db'.
deadline=$(( $(date +%s) + TIMEOUT_SECS ))
status="unknown"
streak=""
while [[ $(date +%s) -lt $deadline ]]; do
    # ssh wrapper because the docker socket is on the worker, not local.
    state=$(_ssh "sudo bash -c '
      for sock in /var/run/rediacc/docker-*.sock; do
        [ -S \"\$sock\" ] || continue
        cid=\$(docker -H unix://\$sock ps -a --filter name=^db\$ --format \"{{.ID}}\" 2>/dev/null | head -1)
        if [ -n \"\$cid\" ]; then
          docker -H unix://\$sock inspect --format \"{{.State.Health.Status}}|{{.State.Health.FailingStreak}}\" \"\$cid\" 2>/dev/null && exit 0
        fi
      done
      echo \"missing|\"
    '" 2>/dev/null || echo "ssh-error|")

    status="${state%%|*}"
    streak="${state#*|}"
    if [[ "$status" == "healthy" ]]; then
        log_info "✓ db reached healthy (streak=$streak)"
        break
    fi
    log_step "  status=$status streak=$streak — waiting..."
    sleep 5
done

if [[ "$status" != "healthy" ]]; then
    log_error "db did not reach healthy within ${TIMEOUT_SECS}s (last status=$status streak=$streak)"
    log_error "Diagnostic dump follows"

    log_step "[diag] db container state + recent logs"
    _ssh "sudo bash -c '
      for sock in /var/run/rediacc/docker-*.sock; do
        [ -S \"\$sock\" ] || continue
        cid=\$(docker -H unix://\$sock ps -a --filter name=^db\$ --format \"{{.ID}}\" 2>/dev/null | head -1)
        if [ -n \"\$cid\" ]; then
          echo \"=== \$sock ===\"
          docker -H unix://\$sock inspect --format \"State={{.State.Status}} Health={{.State.Health.Status}}/{{.State.Health.FailingStreak}}\" \"\$cid\"
          echo \"--- last 5 health log entries ---\"
          docker -H unix://\$sock inspect --format \"{{json .State.Health.Log}}\" \"\$cid\" 2>&1 | head -100
          echo \"--- last 30 container log lines ---\"
          docker -H unix://\$sock logs --tail 30 \"\$cid\" 2>&1
        fi
      done
    '" || true

    log_step "[diag] postgres listening sockets on host"
    _ssh "sudo ss -tlnp 'sport = :5432' 2>&1" || true

    exit 1
fi

# -------------------------------------------------------------------------
# Phase 3 — assert app container also started (proves depends_on chain)
# -------------------------------------------------------------------------
# The 'app' container has depends_on: db.condition: service_healthy.
# If db's healthcheck converged, app should be running. This is a cheap
# extra assertion that catches a different class of regression than the
# db healthcheck alone (compose orchestration ordering, env propagation).
log_step "Confirming app container is running (depends_on db.healthy)"
app_state=$(_ssh "sudo bash -c '
  for sock in /var/run/rediacc/docker-*.sock; do
    [ -S \"\$sock\" ] || continue
    cid=\$(docker -H unix://\$sock ps -a --filter name=^app\$ --format \"{{.ID}}\" 2>/dev/null | head -1)
    if [ -n \"\$cid\" ]; then
      docker -H unix://\$sock inspect --format \"{{.State.Status}}\" \"\$cid\" 2>/dev/null && exit 0
    fi
  done
  echo \"missing\"
'" 2>/dev/null || echo "ssh-error")

if [[ "$app_state" != "running" ]]; then
    log_error "app container state=$app_state (want 'running')"
    exit 1
fi
log_info "✓ app container running"

log_info "PASS: app-postgres compose converged — eBPF rewrites + healthchecks intact"
