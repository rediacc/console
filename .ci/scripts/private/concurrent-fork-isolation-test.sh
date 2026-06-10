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
#   4. `repo fork --checkpoint` of the RUNNING parent restores process state
#      in the fork while the parent keeps running (console#440 regression
#      guard: cow_sync parent-mount flush + eBPF alias-subnet remap).
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
CP_FORK_TAG="cpchild"
CP_FORK_REPO="${PARENT_REPO}:${CP_FORK_TAG}"

_ssh() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
        "${SSH_USER}@${VM_IP}" "$@"
}

# Temp artifacts removed by the cleanup trap even on premature exit.
COUNTER_DIR=""
cp_up_log=""

cleanup() {
    log_step "Cleanup (best-effort)"
    [[ -n "$COUNTER_DIR" ]] && rm -rf "$COUNTER_DIR"
    [[ -n "$cp_up_log" ]] && rm -f "$cp_up_log"
    rdc repo down --name "$CP_FORK_REPO" -m "$MACHINE_NAME" 2>/dev/null || true
    rdc repo down --name "$FORK_REPO" -m "$MACHINE_NAME" 2>/dev/null || true
    rdc repo down --name "$PARENT_REPO" -m "$MACHINE_NAME" 2>/dev/null || true
    rdc repo delete --name "$CP_FORK_REPO" -m "$MACHINE_NAME" --force 2>/dev/null || true
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

# Counter sidecar for the console#440 checkpoint phase: a checkpoint-labeled
# process whose monotonic in-memory counter proves CRIU restore vs fresh
# start. Lives in a Z-prefixed subdir so it comes up after the template app.
log_step "Uploading checkpoint counter sidecar (Zcounter/)"
COUNTER_DIR=$(mktemp -d)
cat >"$COUNTER_DIR/docker-compose.yml" <<'COMPOSE'
services:
  counter:
    image: alpine:3.20
    network_mode: host
    labels:
      - "rediacc.checkpoint=true"
    command: sh -c 'i=0; while true; do i=$((i+1)); echo "count=$i"; sleep 1; done'
COMPOSE
cat >"$COUNTER_DIR/Rediaccfile" <<'REDIACCFILE'
up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
REDIACCFILE
rdc repo sync upload -m "$MACHINE_NAME" -r "$PARENT_REPO" --local "$COUNTER_DIR" --remote Zcounter
rm -rf "$COUNTER_DIR"
COUNTER_DIR=""

log_step "Bringing parent up (parent's postgres will bind first)"
rdc repo up --name "$PARENT_REPO" -m "$MACHINE_NAME"

# -------------------------------------------------------------------------
# Phase 2 — fork-of-running parent: this is the failure path on main
# -------------------------------------------------------------------------
log_step "Forking parent into '$FORK_TAG' (parent stays running)"
rdc repo fork --parent "$PARENT_REPO" --tag "$FORK_TAG" -m "$MACHINE_NAME"
log_step "Bringing fork up — must succeed (renet#60 regression guard)"
if ! rdc repo up --name "$FORK_REPO" -m "$MACHINE_NAME"; then
    log_error "rdc repo up '$FORK_REPO' failed"
    log_error "Diagnostic dump follows — db logs + cgroup state + listening sockets"

    log_step "[diag] cgroup hierarchy under /sys/fs/cgroup/rediacc.slice"
    _ssh "sudo find /sys/fs/cgroup/rediacc.slice -maxdepth 4 -type d | head -50" || true

    log_step "[diag] postgres binds on host (any source port :5432)"
    _ssh "sudo ss -tlnp4 'sport = :5432' 2>&1" || true

    log_step "[diag] cgroup_configs BPF map contents (pinned at /sys/fs/bpf/rediacc/cgroup_configs)"
    _ssh "sudo bpftool map dump pinned /sys/fs/bpf/rediacc/cgroup_configs 2>&1 | head -60" || true

    log_step "[diag] BPF programs attached to rediacc.slice"
    _ssh "sudo bpftool cgroup tree /sys/fs/cgroup/rediacc.slice 2>&1 | head -30" || true

    log_step "[diag] db container logs (parent + fork sockets)"
    _ssh "sudo bash -c '
      for sock in /var/run/rediacc/docker-*.sock; do
        echo \"=== \$sock ===\"
        docker -H unix://\$sock ps -a --format \"{{.ID}} {{.Names}} {{.Status}}\" 2>/dev/null || true
        cid=\$(docker -H unix://\$sock ps -a --filter name=db --format \"{{.ID}}\" 2>/dev/null | head -1)
        if [ -n \"\$cid\" ]; then
          echo \"--- inspect cgroup ---\"
          docker -H unix://\$sock inspect --format \"{{.HostConfig.CgroupParent}}\" \"\$cid\" 2>&1 || true
          echo \"--- logs ---\"
          docker -H unix://\$sock logs --tail 50 \"\$cid\" 2>&1 || true
        fi
      done
    '" || true

    log_error "(see diagnostic dump above)"
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
# Phase 4 — renet#59 regression guard: no per-network daemon hosts >1 project
# -------------------------------------------------------------------------
# Each repo has its own dockerd at /var/run/rediacc/docker-<networkID>.sock.
# A correctly-isolated fork has its daemon owning exactly one
# com.docker.compose.project. Without #59, the fork's daemon inherits the
# parent's containers and ends up with two distinct project labels. We don't
# try to reconstruct the project name (docker compose normalises mount-path
# basenames into project names, stripping :, etc.) — instead, we count
# distinct project labels per socket: >1 = leak.
log_step "Asserting no per-network daemon hosts more than one compose-project (renet#59)"
foreign=$(_ssh "
sudo bash -c '
set -e
for sock in /var/run/rediacc/docker-*.sock; do
    [ -S \"\$sock\" ] || continue
    projects=\$(docker -H unix://\$sock ps -a --format \"{{index .Labels \\\"com.docker.compose.project\\\"}}\" 2>/dev/null | sort -u | grep -v \"^\$\" || true)
    project_count=\$(echo \"\$projects\" | grep -c . || true)
    if [ \"\$project_count\" -gt 1 ]; then
        echo \"\$sock owns \$project_count projects: \$projects\" >&2
        echo \"\$project_count\"
        exit 0
    fi
done
echo 0
'
")

if [[ "${foreign:-0}" -gt 1 ]]; then
    log_error "a per-network daemon hosts $foreign compose projects — renet#59 regressed"
    exit 1
fi
log_info "✓ each per-network daemon hosts at most one compose project"

# -------------------------------------------------------------------------
# Phase 5 — console#440 regression guard: live fork with CRIU checkpoint
# -------------------------------------------------------------------------
# Fork the RUNNING parent with --checkpoint, bring the fork up, and assert the
# counter process resumed from the dump instead of starting fresh. Guards both
# halves of the #440 fix: the cow_sync parent-mount flush (without it the
# checkpoint data never reaches the fork and restore is silently skipped) and
# the eBPF alias-subnet remap (without it CRIU's restore fails on the parent's
# dump-time addresses).

# counter_sockets prints every per-network docker socket that runs a counter
# container. Before the checkpoint fork exists, that is exactly the parent's.
counter_sockets() {
    _ssh "sudo bash -c '
      for sock in /var/run/rediacc/docker-*.sock; do
        [ -S \"\$sock\" ] || continue
        if docker -H unix://\$sock ps --filter name=counter --format \"{{.Names}}\" 2>/dev/null | grep -q counter; then
          echo \"\$sock\"
        fi
      done
    '"
}

# counter_value <socket> prints the counter container's last logged count.
counter_value() {
    _ssh "sudo bash -c '
      name=\$(docker -H unix://$1 ps --filter name=counter --format \"{{.Names}}\" 2>/dev/null | head -1)
      [ -n \"\$name\" ] || exit 0
      docker -H unix://$1 logs --tail 5 \"\$name\" 2>/dev/null | grep -o \"count=[0-9]*\" | tail -1 | cut -d= -f2
    '"
}

log_step "Locating parent's counter container"
parent_sock=$(counter_sockets | head -1)
if [[ -z "$parent_sock" ]]; then
    log_error "parent has no running counter container — sidecar upload or up failed"
    exit 1
fi

log_step "Waiting for parent counter to reach 15 (restore-vs-fresh margin)"
parent_count=0
for _ in $(seq 1 30); do
    parent_count=$(counter_value "$parent_sock")
    [[ "${parent_count:-0}" -ge 15 ]] && break
    sleep 2
done
if [[ "${parent_count:-0}" -lt 15 ]]; then
    log_error "parent counter stuck at '${parent_count:-0}' — counter container unhealthy"
    exit 1
fi
log_info "parent counter at $parent_count before checkpoint"

log_step "Forking running parent with --checkpoint into '$CP_FORK_TAG'"
rdc repo fork --parent "$PARENT_REPO" --tag "$CP_FORK_TAG" -m "$MACHINE_NAME" --checkpoint

log_step "Bringing checkpoint fork up — restore must fire (console#440)"
cp_up_log=$(mktemp)
if ! rdc repo up --name "$CP_FORK_REPO" -m "$MACHINE_NAME" --debug 2>&1 | tee "$cp_up_log"; then
    log_error "rdc repo up '$CP_FORK_REPO' failed"
    exit 1
fi

if ! grep -q "restored from checkpoint" "$cp_up_log"; then
    log_error "fork up succeeded but no checkpoint restore happened (console#440 regressed:"
    log_error "either the dump never reached the fork — cow_sync — or restore failed and fell back to fresh)"
    grep -iE "checkpoint|restor" "$cp_up_log" | tail -20 || true
    exit 1
fi
rm -f "$cp_up_log"
cp_up_log=""

# The restored counter must continue from >= the pre-checkpoint value. A
# fresh container would have restarted at ~1 and cannot reach the parent's
# pre-fork count within seconds of `up` returning.
log_step "Reading fork's counter (restored process)"
fork_sock=""
for sock in $(counter_sockets); do
    [[ "$sock" != "$parent_sock" ]] && fork_sock="$sock"
done
if [[ -z "$fork_sock" ]]; then
    log_error "no counter container in the fork's daemon"
    exit 1
fi
fork_count=$(counter_value "$fork_sock")
if [[ "${fork_count:-0}" -lt "$parent_count" ]]; then
    log_error "fork counter ${fork_count:-0} < pre-checkpoint $parent_count — process state NOT restored"
    exit 1
fi
log_info "✓ fork counter continued at $fork_count (>= $parent_count) — CRIU state preserved"

log_step "Asserting parent kept running through fork + restore"
parent_after=$(counter_value "$parent_sock")
sleep 3
parent_after2=$(counter_value "$parent_sock")
if [[ "${parent_after2:-0}" -le "${parent_after:-0}" ]]; then
    log_error "parent counter stalled ($parent_after -> $parent_after2) — parent disturbed by fork restore"
    exit 1
fi
log_info "✓ parent counter still advancing ($parent_after -> $parent_after2)"

log_info "PASS: parent + fork running, distinct binds, no foreign containers, checkpoint fork restored"
