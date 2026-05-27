#!/bin/bash
# Unit tests for the sentinel-aware write_once_guard() in
# .ci/scripts/deploy/upload-to-r2.sh. Mocks aws so the test runs offline.
#
# The guard's behaviours (see .ci/scripts/lib/release-state-validator.sh):
#   1. sentinel exists + binaries present  → return 10 (SKIP: idempotent rerun)
#   2. sentinel exists + NO binaries       → exit 1 (FAIL: sealed-but-empty)
#   3. no sentinel (clean OR orphan bytes) → return 0 (PROCEED, overwrite in place)
# The guard NEVER runs `aws s3 rm` — orphan cleanup is the nightly housekeeping
# job's responsibility, so a retried/cancelled release can't lose its binaries.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
GUARD_SCRIPT="$ROOT_DIR/.ci/scripts/deploy/upload-to-r2.sh"
VALIDATOR_LIB="$ROOT_DIR/.ci/scripts/lib/release-state-validator.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_fail() {
    echo -e "${RED}FAIL:${NC} $*" >&2
    exit 1
}
log_pass() { echo -e "${GREEN}PASS:${NC} $*"; }

TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

# Fake aws: dispatches on the first two args so each subcommand can be scripted
# independently. Also records every invocation into $TEMP/aws.log so tests can
# assert whether `aws s3 rm --recursive` was called by the orphan-scrub path.
cat >"$TEMP/aws" <<FAKE
#!/bin/bash
printf '%s\n' "\$*" >>"$TEMP/aws.log"
case "\$1 \$2" in
    "s3api head-object")
        # Sentinel existence check. Controlled by SENTINEL_EXISTS.
        if [[ "\${SENTINEL_EXISTS:-false}" == "true" ]]; then
            exit 0
        fi
        exit 254  # typical NoSuchKey exit from awscli
        ;;
    "s3api list-objects-v2")
        # Prefix non-empty check (rsv_prefix_nonempty) uses --query KeyCount.
        printf '%s\n' "\${PREFIX_KEYCOUNT:-0}"
        exit 0
        ;;
    "s3 rm")
        # Scrub call. Always succeeds.
        exit 0
        ;;
    *)
        exit 0
        ;;
esac
FAKE
chmod +x "$TEMP/aws"
export PATH="$TEMP:$PATH"

# Environment upload-to-r2.sh requires before we can source it.
export RELEASES_BUCKET=rediacc-releases
export R2_ENDPOINT=https://example.invalid
export VERSION=0.0.0-test
export CHANNEL=pr-0
export DRY_RUN=false

# Extract just the guard function + define stubs for log_* + pull in the
# validator library (which provides rsv_sentinel_exists / rsv_prefix_nonempty).
sed -n '/^write_once_guard()/,/^}/p' "$GUARD_SCRIPT" >"$TEMP/guard.sh"
cat >"$TEMP/bundle.sh" <<STUBS
log_error() { echo "error: \$*" >&2; }
log_warn()  { echo "warn: \$*" >&2; }
log_info()  { echo "info: \$*" >&2; }
SCRIPT_DIR="$ROOT_DIR/.ci/scripts/deploy"
RELEASES_BUCKET="$RELEASES_BUCKET"
R2_ENDPOINT="$R2_ENDPOINT"
DRY_RUN=\${DRY_RUN:-false}
STUBS
cat "$VALIDATOR_LIB" >>"$TEMP/bundle.sh"
cat "$TEMP/guard.sh" >>"$TEMP/bundle.sh"

reset_log() { : >"$TEMP/aws.log"; }

run_guard() {
    bash -c "source '$TEMP/bundle.sh'; write_once_guard '$1' 'test'" 2>/dev/null
}

# PREFIX_KEYCOUNT drives BOTH the mock's list-objects-v2 responses; the guard
# only calls rsv_binary_count when the sentinel exists, so it doubles as the
# "binary count" for the sealed cases below.

test_sealed_with_binaries_skips() {
    reset_log
    local rc=0
    SENTINEL_EXISTS=true PREFIX_KEYCOUNT=16 run_guard "cli/v0.0.0/" || rc=$?
    [[ "$rc" == "10" ]] ||
        log_fail "sealed + binaries present should SKIP (rc=10, idempotent rerun); got rc=$rc"
    grep -q "s3 rm" "$TEMP/aws.log" &&
        log_fail "guard must NEVER scrub"
    log_pass "sealed + binaries → idempotent SKIP (rc=10)"
}

test_sealed_but_empty_fails() {
    reset_log
    local rc=0
    SENTINEL_EXISTS=true PREFIX_KEYCOUNT=0 run_guard "cli/v0.0.0/" || rc=$?
    [[ "$rc" == "1" ]] ||
        log_fail "sealed + NO binaries (sealed-but-empty) should FAIL loud (rc=1); got rc=$rc"
    grep -q "s3 rm" "$TEMP/aws.log" &&
        log_fail "guard must NEVER scrub"
    log_pass "sealed + no binaries → FAIL loud (rc=1)"
}

test_no_sentinel_proceeds_without_scrub() {
    # Clean prefix: PROCEED, no scrub.
    reset_log
    SENTINEL_EXISTS=false PREFIX_KEYCOUNT=0 run_guard "cli/v0.0.0/" ||
        log_fail "clean prefix (no sentinel) should PROCEED (rc=0)"
    grep -q "s3 rm" "$TEMP/aws.log" &&
        log_fail "guard must NEVER scrub a clean prefix"

    # Orphan prefix (bytes, no sentinel): PROCEED and OVERWRITE in place — must
    # NOT scrub (the old behaviour that deleted retried releases' binaries).
    reset_log
    SENTINEL_EXISTS=false PREFIX_KEYCOUNT=9 run_guard "cli/v0.0.0/" ||
        log_fail "orphan prefix should PROCEED (rc=0), overwriting in place"
    grep -q "s3 rm" "$TEMP/aws.log" &&
        log_fail "guard must NEVER scrub an orphan — that is the nightly housekeeping job's responsibility"
    log_pass "no sentinel → PROCEED (rc=0), never scrubs"
}

test_dry_run_skips() {
    reset_log
    SENTINEL_EXISTS=true PREFIX_KEYCOUNT=1 DRY_RUN=true run_guard "cli/v0.0.0/" ||
        log_fail "DRY_RUN=true should pass regardless of state"
    grep -q "s3api head-object" "$TEMP/aws.log" &&
        log_fail "DRY_RUN must not call aws at all"
    log_pass "DRY_RUN=true skips all checks"
}

test_sealed_with_binaries_skips
test_sealed_but_empty_fails
test_no_sentinel_proceeds_without_scrub
test_dry_run_skips

echo ""
log_pass "all sentinel-aware write_once_guard cases"
