#!/bin/bash
# Gather the logs a failed drill needs but does not print.
#
# WHY THIS EXISTS. `drill transfer` can die with:
#
#   ✗ Could not seed a config store: {"error":"Internal server error"}
#   ✗ Config storage needs the RustFS container from ./run.sh account dev (Docker).
#
# and the evidence for that claim is in two places the drill's own stdout never
# reaches, so uploading the tee'd drill log re-uploads the job log and answers
# nothing (observed on wave 0804-1):
#
#   1. .account-logs/rustfs.log — `docker compose up -d config-rustfs` output.
#      account.sh runs it as `... || true`, so a compose failure (image pull,
#      registry rate limit, ghost container) is INVISIBLE anywhere else. If
#      RustFS never answers, account_dev leaves CONFIG_R2_* unset, the dev
#      gateway skips config blob storage entirely (dev-gateway.ts:54), and the
#      seed route answers 500 — which is the symptom, three steps downstream.
#   2. <drill work dir>/gateway.log — the gateway's own stdout, which says
#      whether config blob storage was wired at all.
#
# REQUIRES the drills to have been invoked with `--keep-work`. drill_teardown
# rm -rf's the work dir on EXIT otherwise, and an env var cannot substitute:
# scripts/drills/lib.sh assigns DRILL_KEEP_WORK=0 at script level, overwriting
# anything inherited, so only the flag survives.
#
# Env: RUNNER_TEMP (destination root; defaults to a temp dir for local use)
#      TMPDIR      (where drill work dirs live; defaults to /tmp)
# Run locally:
#   ./run.sh drill transfer --keep-work || .ci/scripts/test/collect-drill-diagnostics.sh
#
# Always exits 0: this runs on an already-failed job and must never convert a
# real drill failure into a confusing collector failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

dest="${RUNNER_TEMP:-$(mktemp -d)}/drill-diagnostics"
mkdir -p "$dest"

# The account log dir lives in the workspace and survives the drill.
if [[ -d "$ROOT_DIR/.account-logs" ]]; then
    cp -r "$ROOT_DIR/.account-logs" "$dest/account-logs" 2>/dev/null || true
fi

for work in "${TMPDIR:-/tmp}"/rediacc-drill-*/; do
    [[ -d "$work" ]] || continue
    sub="$dest/$(basename "$work")"
    mkdir -p "$sub"
    cp "$work/gateway.log" "$sub/gateway.log" 2>/dev/null || true
done

# Print what was collected, so the job log itself says whether the artifact is
# worth downloading. An empty collection is a finding: it means --keep-work was
# dropped, or the drill failed before the gateway wrote anything.
count=$(find "$dest" -type f 2>/dev/null | wc -l)
echo "drill diagnostics collected: $count file(s) under $dest"
find "$dest" -type f -printf '  %10s bytes  %p\n' 2>/dev/null || true
if [[ "$count" -eq 0 ]]; then
    echo "  (nothing collected -- check that the drills ran with --keep-work)"
fi

exit 0
