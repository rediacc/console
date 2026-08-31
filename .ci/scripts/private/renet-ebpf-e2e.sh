#!/bin/bash
# Run the eBPF socket-isolation behavioral regression tests (ebpf_e2e tag).
#
# These load the production BPF objects, attach them to a fresh test cgroup, and
# assert bind/connect rewrite + cross-/26 isolation (the 3-day nextcloud
# dual-stack regression guard). Tagged `ebpf_e2e` so `go vet` only COMPILES them;
# here they EXECUTE.
#
# Requires: root (run under sudo), cgroup2, `go` on PATH, and bpffs at
# /sys/fs/bpf (mounted here if absent). No env vars.
#
# Local run (from repo root):
#   sudo env "PATH=$PATH" .ci/scripts/private/renet-ebpf-e2e.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
cd "$(get_repo_root)/private/renet"

# eBPF pinning requires bpffs mounted at /sys/fs/bpf; mount it idempotently.
if [[ "$(stat -f -c %T /sys/fs/bpf 2>/dev/null)" != "bpf_fs" ]]; then
    log_step "Mounting bpffs at /sys/fs/bpf..."
    mount -t bpf bpffs /sys/fs/bpf
fi

log_step "Running eBPF socket-isolation tests (ebpf_e2e)..."
out="$(go test -tags ebpf_e2e -run TestEBPF_ ./pkg/ebpf/ -v -count=1 -timeout 300s 2>&1)" || {
    echo "$out"
    exit 1
}
echo "$out"

# Loud-skip guard: these tests SKIP without root/bpffs/cgroup2. An all-skips run
# is green-but-useless — fail unless at least one actually PASSed.
if ! grep -q -- '--- PASS: TestEBPF_' <<<"$out"; then
    echo "::error::ebpf_e2e executed zero tests (all skipped) — root/bpffs/cgroup2 prerequisites not met on this runner"
    exit 1
fi
log_info "eBPF socket-isolation tests passed"
