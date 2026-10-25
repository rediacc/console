#!/usr/bin/env bash
# Run private/elite/scripts/s3-conformance-probe.sh against the object store the elite job just started.
#
# WHY. The probe checks the surface the backup data plane depends on (presigned PUT/GET, create-only PUT with
# If-None-Match: *, HeadObject, DeleteObjects, multipart) and nothing in CI called it, so the pinned RustFS
# image could regress on the load-bearing 412 with every job green (PLAN-backup-program A4d).
#
#   run-elite-s3-probe.sh             live: find the rustfs container, probe it, exit with the probe's status
#   run-elite-s3-probe.sh --selftest  controls: a conformant stub must pass, a stub that ignores If-None-Match
#                                     must FAIL the probe on create-only-conflict
#
# ANTI-VACUITY. A missing container, an empty IP, missing credentials or a missing probe script is a loud failure
# with the cause, never a skipped green. The credentials travel in the environment of the probe process only.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROBE="${ELITE_S3_PROBE_SCRIPT:-$ROOT/private/elite/scripts/s3-conformance-probe.sh}"
STUB="$(dirname "${BASH_SOURCE[0]}")/s3-probe-stub.py"

die() { echo "run-elite-s3-probe: $*" >&2; exit 1; }
[ -f "$PROBE" ] || die "probe script not found at $PROBE (is the private/elite submodule checked out?)"

if [ "${1:-}" = "--selftest" ]; then
    command -v python3 >/dev/null || die "python3 is required for the stub store"
    tmp="$(mktemp -d)"
    pid=""
    trap '[ -n "$pid" ] && kill "$pid" 2>/dev/null; rm -rf "$tmp"' EXIT
    run_stub() { # run_stub <stub flags...>: starts the stub, sets $port and $pid
        python3 -I "$STUB" "$@" >"$tmp/ready" 2>"$tmp/stub.err" &
        pid=$!
        for _ in $(seq 1 50); do grep -q '^READY ' "$tmp/ready" 2>/dev/null && break; sleep 0.1; done
        port="$(awk '/^READY /{print $2}' "$tmp/ready")"
        [ -n "$port" ] || die "stub store did not start: $(cat "$tmp/stub.err")"
    }
    probe_stub() {
        S3_ENDPOINT="http://127.0.0.1:$port" S3_BUCKET=stub S3_ACCESS_KEY_ID=stub S3_SECRET_ACCESS_KEY=stub \
            bash "$PROBE" >"$tmp/probe.out" 2>&1
    }

    run_stub
    probe_stub || { cat "$tmp/probe.out"; die "CONTROL failed: the probe rejected the conformant stub"; }
    grep -q 'create-only-conflict' "$tmp/probe.out" || die "CONTROL failed: the probe never reached the create-only step"
    echo "  PASS  conformant stub passes all probes"
    kill "$pid"; wait "$pid" 2>/dev/null; pid=""

    run_stub --ignore-if-none-match
    if probe_stub; then cat "$tmp/probe.out"; die "the probe PASSED a store that ignores If-None-Match"; fi
    grep -q 'FAIL create-only-conflict' "$tmp/probe.out" || { cat "$tmp/probe.out"; die "the probe failed, but not on create-only-conflict"; }
    echo "  PASS  a non-conformant stub (ignores If-None-Match) is red on create-only-conflict"
    echo "run-elite-s3-probe: selftest ok"
    exit 0
fi

container="${INSTANCE_NAME:-rediacc}-rustfs"
[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null)" = "true" ] \
    || die "container $container is not running; the elite stack did not start its object store"
ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$container" | awk '{print $1}')"
[ -n "$ip" ] || die "container $container has no network address"
access="$(docker exec "$container" printenv RUSTFS_ACCESS_KEY)" || die "cannot read the store's access key from $container"
secret="$(docker exec "$container" printenv RUSTFS_SECRET_KEY)" || die "cannot read the store's secret key from $container"
[ -n "$access" ] && [ -n "$secret" ] || die "the store's credentials are empty in $container"

S3_ENDPOINT="http://$ip:9000" S3_BUCKET="${ELITE_S3_PROBE_BUCKET:-rediacc-backups}" \
    S3_ACCESS_KEY_ID="$access" S3_SECRET_ACCESS_KEY="$secret" bash "$PROBE"
rc=$?
echo "run-elite-s3-probe: probe against $container ($ip) exited $rc"
exit "$rc"
