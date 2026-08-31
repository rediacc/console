#!/bin/bash
# Run the CSI driver conformance suite (csi-sanity, spec 09 §12) on a scratch
# loop-BTRFS datastore. Full idempotency + error-code conformance for the
# node-local `csi.rediacc.io` driver, zero VMs.
#
# Two upstream specs stay red BY DESIGN — they are RULED deviations (spec 09 §16,
# CSI-DEVIATION-1 max-length name / CSI-DEVIATION-2 snapshot same-name-different-
# source), each already enforced by a dedicated Go unit test. They are skipped
# here so the step is green + loud (48/50). Do NOT remove the skips without
# re-ruling the deviations in spec 09 §16.
#
# Requires: root (run under sudo), `go` on PATH, btrfs-progs + cryptsetup
# (installed here if absent), loop-device support. No env vars.
#
# Local run (from repo root):
#   sudo env "PATH=$PATH" .ci/scripts/private/renet-csi-sanity.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
REPO_ROOT="$(get_repo_root)"

CSI_IMG="${CSI_SANITY_IMG:-/tmp/csi-btrfs.img}"
CSI_MNT="${CSI_SANITY_BASE:-/mnt/csi-sanity}"
# The two ruled-deviation specs (spec 09 §16) that stay red by design.
SKIP_SPECS='should not fail when creating volume with maximum-length name|should fail when requesting to create a snapshot with already existing name and different source volume ID'

if ! command -v mkfs.btrfs >/dev/null || ! command -v cryptsetup >/dev/null; then
    log_step "Installing btrfs-progs + cryptsetup..."
    apt-get update -qq && apt-get install -y -qq btrfs-progs cryptsetup-bin
fi

log_step "Creating scratch loop-BTRFS datastore at $CSI_MNT..."
# Idempotent re-run: a previous run's mount/image must not fail this one
# (bit the first local rerun; GH runners get fresh /tmp and never see it).
umount "$CSI_MNT" 2>/dev/null || true
truncate -s 4G "$CSI_IMG"
mkfs.btrfs -q -f "$CSI_IMG"
mkdir -p "$CSI_MNT"
mount -o loop "$CSI_IMG" "$CSI_MNT"

log_step "Running csi-sanity conformance suite..."
cd "$REPO_ROOT/private/renet"
out="$(REDIACC_CSI_SANITY_BASE="$CSI_MNT" go test -tags root -run TestCSISanity ./pkg/kubecsi/ \
    -v -count=1 -timeout 600s -args -ginkgo.skip="$SKIP_SPECS" 2>&1)" || {
    echo "$out"
    exit 1
}
echo "$out"

# Loud-skip guard: the whole suite skips off-root/off-BTRFS. Require a non-zero
# executed-spec count AND a passing TestCSISanity.
if ! grep -qE 'Ran [1-9][0-9]* of [0-9]+ Specs' <<<"$out"; then
    echo "::error::csi-sanity ran zero specs — root/BTRFS prerequisites not met"
    exit 1
fi
if ! grep -q -- '--- PASS: TestCSISanity' <<<"$out"; then
    echo "::error::csi-sanity did not PASS"
    exit 1
fi
log_info "csi-sanity conformance passed (48/50; 2 ruled deviations skipped per spec 09 §16)"
