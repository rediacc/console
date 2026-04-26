#!/bin/bash
# Concurrent fork isolation regression test.
#
# Reproduces the renet#60 race condition (and renet#59 prerequisite) on a worker
# VM provisioned by `renet ops up`. Asserts that:
#   1. `rdc repo up parent:child` exits 0 (no EADDRINUSE liveness failure).
#   2. parent's db and child's db each bind to their OWN 127.0.x.x:5432 — never
#      0.0.0.0:5432. The bind-rewrite is the contract per services.md:101.
#   3. The fork's per-network daemon contains no parent-project containers
#      (renet#59 — name conflict that masked the bind race).
#
# Without the fix, step (1) fails: parent's postgres holds 0.0.0.0:5432, and
# child's postgres exits with "could not bind IPv4 address \"0.0.0.0\":
# Address in use". With the fix, two distinct 127.0.x.x:5432 listeners coexist.
#
# Usage:
#   .ci/scripts/private/concurrent-fork-isolation-test.sh
#
# Inputs (env):
#   VM_NET_BASE  — VM subnet base (default 192.168.111)
#   VM_WORKERS   — Worker IDs (default "11"; first ID is used)
#   SSH_USER     — SSH user (default $USER)
#   SSH_KEY      — SSH key path (default ~/.ssh/id_ed25519)
#   MACHINE_NAME — rdc machine alias (default worker-1)

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

PARENT_REPO="bindrace-parent"
FORK_TAG="child"
FORK_REPO="${PARENT_REPO}:${FORK_TAG}"

_ssh() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
        "${SSH_USER}@${VM_IP}" "$@"
}

cleanup() {
    log_step "Cleanup (best-effort)"
    rdc repo down --name "$FORK_REPO" -m "$MACHINE_NAME" 2>/dev/null || true
    rdc repo down --name "$PARENT_REPO" -m "$MACHINE_NAME" 2>/dev/null || true
    rdc repo delete --name "$FORK_REPO" -m "$MACHINE_NAME" --force 2>/dev/null || true
    rdc repo delete --name "$PARENT_REPO" -m "$MACHINE_NAME" --force 2>/dev/null || true
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
# Phase 1 — bring parent up
# -------------------------------------------------------------------------
log_step "Creating parent repo + applying app-postgres template"
rdc repo create --name "$PARENT_REPO" -m "$MACHINE_NAME" --size 2G
rdc repo template apply --name app-postgres -m "$MACHINE_NAME" -r "$PARENT_REPO"
log_step "Bringing parent up (parent's postgres will bind first)"
rdc repo up --name "$PARENT_REPO" -m "$MACHINE_NAME"

# -------------------------------------------------------------------------
# Phase 2 — fork-of-running parent: this is the failure path on main
# -------------------------------------------------------------------------
log_step "Forking parent into '$FORK_TAG' (parent stays running)"
rdc repo fork --parent "$PARENT_REPO" --tag "$FORK_TAG" -m "$MACHINE_NAME"
log_step "Bringing fork up — must succeed (renet#60 regression guard)"
if ! rdc repo up --name "$FORK_REPO" -m "$MACHINE_NAME"; then
    log_error "rdc repo up '$FORK_REPO' failed — renet#60 race regressed"
    log_error "(parent's postgres likely captured 0.0.0.0:5432 unrewritten)"
    exit 1
fi

# -------------------------------------------------------------------------
# Phase 3 — bind isolation assertions
# -------------------------------------------------------------------------
# Both daemons run with network_mode: host, so the worker VM's `lo` is shared
# with every container. `ss -tlnp4 sport = :5432` on the host shows the union
# of all postgres binds across all per-repo daemons. The contract is two
# distinct 127.0.x.x:5432 entries, no 0.0.0.0:5432.
log_step "Reading postgres binds on worker (sport = :5432)"
binds_raw=$(_ssh "ss -Hltnp4 'sport = :5432' 2>/dev/null | awk '{print \$4}'" || true)
binds=()
while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    binds+=("$line")
done < <(printf '%s\n' "$binds_raw")

log_step "Found ${#binds[@]} listener(s):"
for b in "${binds[@]:-}"; do
    log_step "  $b"
done

if [[ ${#binds[@]} -lt 2 ]]; then
    log_error "expected >=2 postgres listeners (parent + fork), got ${#binds[@]}"
    exit 1
fi

for b in "${binds[@]}"; do
    if [[ "$b" == "0.0.0.0:5432" || "$b" == "*:5432" ]]; then
        log_error "found wildcard bind '$b' — bind-rewrite did not fire (renet#60 regressed)"
        exit 1
    fi
    if ! [[ "$b" =~ ^127\.0\.[0-9]+\.[0-9]+:5432$ ]]; then
        log_error "unexpected bind '$b' — expected 127.0.x.x:5432"
        exit 1
    fi
done

# Distinct addresses
unique_ips=()
while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    unique_ips+=("$line")
done < <(printf '%s\n' "${binds[@]}" | sort -u)
if [[ ${#unique_ips[@]} -lt 2 ]]; then
    log_error "all binds collapsed to a single IP (${binds[0]}) — isolation violated"
    exit 1
fi
log_info "✓ ${#unique_ips[@]} distinct loopback binds — isolation holds"

# -------------------------------------------------------------------------
# Phase 4 — renet#59 regression guard: fork's daemon has no parent containers
# -------------------------------------------------------------------------
# Each repo has its own dockerd at /var/run/rediacc/docker-<networkID>.sock.
# Find the fork's socket by scanning containers; assert no compose-project
# label points at the parent's project (basename of parent's mount).
log_step "Asserting fork daemon has no foreign-project containers (renet#59)"
parent_project=$(_ssh "basename /mnt/rediacc/mounts/${PARENT_REPO} 2>/dev/null" || echo "$PARENT_REPO")
fork_project=$(_ssh "basename /mnt/rediacc/mounts/${FORK_REPO} 2>/dev/null" || echo "${FORK_REPO//:/_}")

# For each per-network socket, count fork-project + parent-project containers
# via docker --filter (exact label match, not substring of the Labels column —
# parent name is a prefix of fork name, so substring matching false-positives).
# A socket owning both means renet#59 regressed.
foreign=$(_ssh "
sudo bash -c '
set -e
for sock in /var/run/rediacc/docker-*.sock; do
    [ -S \"\$sock\" ] || continue
    fork_match=\$(docker -H unix://\$sock ps -a --filter \"label=com.docker.compose.project=$fork_project\" -q 2>/dev/null | wc -l)
    parent_match=\$(docker -H unix://\$sock ps -a --filter \"label=com.docker.compose.project=$parent_project\" -q 2>/dev/null | wc -l)
    if [ \"\$fork_match\" -gt 0 ] && [ \"\$parent_match\" -gt 0 ]; then
        echo \"\$parent_match\"
        exit 0
    fi
done
echo 0
'
")

if [[ "${foreign:-0}" -gt 0 ]]; then
    log_error "fork daemon contains $foreign parent-project containers — renet#59 regressed"
    exit 1
fi
log_info "✓ no parent-project containers in fork daemon"

log_info "PASS: parent + fork running, distinct binds, no foreign containers"
