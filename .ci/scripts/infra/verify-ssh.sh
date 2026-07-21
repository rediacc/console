#!/bin/bash
# Poll one or more hosts until SSH answers, or fail after N attempts.
#
# `ops up` returns when libvirt has started the domain; sshd comes up later.
# Every later step SSHes in, so waiting here turns a confusing mid-suite
# connection refusal into one clear timeout with an attempt count.
#
# Host-key checking is disabled and known_hosts is /dev/null on purpose: these
# are ephemeral CI VMs whose keys are regenerated on every provision, so
# pinning them would fail on the second run.
#
# Usage:
#   SSH_KEY=~/.ssh/id_rsa .ci/scripts/infra/verify-ssh.sh 192.168.111.1
#   SSH_KEY=... ATTEMPTS=20 .ci/scripts/infra/verify-ssh.sh localhost:2201 localhost:2202
#
# A target may be "host" or "host:port" (or "localhost:PORT" as ops emits).
#
# Required env:
#   SSH_KEY    private key path
# Optional env:
#   ATTEMPTS   default 15
#   SSH_USER   default $(whoami)
#   CHOWN_PATH when set, `sudo chown -R` it first (ops writes the key as root)
#
# Succeeds as soon as ANY target answers -- the callers only need one reachable
# entry point into the cluster.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd ssh
: "${SSH_KEY:?SSH_KEY is required}"
[[ $# -ge 1 ]] || {
    log_error "Usage: $0 <host[:port]> ..."
    exit 1
}

ATTEMPTS="${ATTEMPTS:-15}"
USER_NAME="${SSH_USER:-$(whoami)}"

if [[ -n "${CHOWN_PATH:-}" ]]; then
    sudo chown -R "$(whoami)" "$CHOWN_PATH"
fi

for i in $(seq 1 "$ATTEMPTS"); do
    for target in "$@"; do
        host="$target"
        port=22
        if [[ "$target" == *:* ]]; then
            host="${target%%:*}"
            port="${target##*:}"
        fi
        if ssh -i "$SSH_KEY" -p "$port" \
            -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
            -o ConnectTimeout=5 \
            "${USER_NAME}@${host}" "echo 'SSH OK'"; then
            log_info "SSH connection successful via ${target} on attempt $i"
            exit 0
        fi
        log_info "Attempt $i on ${target} failed"
    done
    log_info "Attempt $i failed for all targets, retrying in 5s..."
    sleep 5
done

log_error "SSH connection failed for all targets after ${ATTEMPTS} attempts"
exit 1
