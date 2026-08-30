#!/bin/bash
# Block until each named VM accepts SSH, then trust its host key.
#
# `ops up` returns once libvirt has started the domains, but the guest is still
# booting. Every later step SSHes in, so waiting here turns a confusing
# mid-suite connection refusal into one clear timeout.
#
# ssh-keyscan runs only AFTER a VM answers, so known_hosts is never populated
# from a half-booted guest.
#
# Usage:
#   .ci/scripts/infra/wait-for-vm-ssh.sh 192.168.111.1 192.168.111.11
#   VM_NET_BASE=192.168.111 .ci/scripts/infra/wait-for-vm-ssh.sh   # .1 and .11
#
# Optional env:
#   VM_NET_BASE   used to build the default host list when no args are given
#   SSH_USER      user to connect as (default: $USER)
#
# 36 attempts, 5s apart -> 180s per VM. Raised from 150s: this repo already has
# a documented incident (docs/ci-overhaul/06-progress.md) where a DIFFERENT
# subsystem's 150s healthcheck budget was insufficient on a downclocked host --
# nested-KVM boot under contention is the same physical phenomenon (CPU
# scheduling pressure slowing a cold start), and 150s is a number already known
# not to be safe for it. No incident is claimed for this exact script; this is
# a preventive alignment to the repo's own evidenced floor, not a repro.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd ssh
require_cmd ssh-keyscan

TARGETS=("$@")
if [[ ${#TARGETS[@]} -eq 0 ]]; then
    : "${VM_NET_BASE:?pass VM addresses as arguments, or set VM_NET_BASE}"
    TARGETS=("${VM_NET_BASE}.1" "${VM_NET_BASE}.11")
fi

SSH_AS="${SSH_USER:-$USER}"
mkdir -p ~/.ssh

for vm in "${TARGETS[@]}"; do
    log_info "Waiting for $vm as $SSH_AS..."
    ready=false
    for i in $(seq 1 36); do
        if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
            "${SSH_AS}@${vm}" echo ready 2>/dev/null; then
            log_info "VM $vm is SSH-ready"
            ssh-keyscan "$vm" >>~/.ssh/known_hosts 2>/dev/null
            ready=true
            break
        fi
        log_info "Waiting for VM $vm SSH... ($i/36)"
        sleep 5
    done
    if [[ "$ready" != "true" ]]; then
        log_error "VM $vm SSH not ready after 180s"
        log_error "load average (1m 5m 15m): $(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || echo unavailable), cores: $(nproc 2>/dev/null || echo unknown)"
        exit 1
    fi
done
