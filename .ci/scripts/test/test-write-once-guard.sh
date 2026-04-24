#!/bin/bash
# Unit tests for the sentinel-aware write_once_guard() in
# .ci/scripts/deploy/upload-to-r2.sh. Mocks aws so the test runs offline.
#
# The guard's three expected behaviours (see
# .ci/scripts/lib/release-state-validator.sh for the invariant):
#   1. `.released` sentinel exists                → exit 1 (seal violated)
#   2. prefix empty + no sentinel                 → return 0 (clean slate)
#   3. prefix non-empty + no sentinel (orphan)    → scrub then return 0

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
GUARD_SCRIPT="$ROOT_DIR/.ci/scripts/deploy/upload-to-r2.sh"
VALIDATOR_LIB="$ROOT_DIR/.ci/scripts/lib/release-state-validator.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_fail() { echo -e "${RED}FAIL:${NC} $*" >&2; exit 1; }
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

test_sealed_prefix_aborts() {
    reset_log
    SENTINEL_EXISTS=true PREFIX_KEYCOUNT=1 run_guard "cli/v0.0.0/" \
        && log_fail "sealed prefix (sentinel present) should abort; guard returned zero"
    grep -q "s3api head-object" "$TEMP/aws.log" \
        || log_fail "guard should have checked head-object for the sentinel"
    grep -q "s3 rm" "$TEMP/aws.log" \
        && log_fail "guard must NOT scrub when the sentinel is present"
    log_pass "sealed prefix aborts (sentinel-aware)"
}

test_empty_prefix_passes() {
    reset_log
    SENTINEL_EXISTS=false PREFIX_KEYCOUNT=0 run_guard "cli/v0.0.0/" \
        || log_fail "empty prefix + no sentinel should pass; guard returned non-zero"
    grep -q "s3 rm" "$TEMP/aws.log" \
        && log_fail "guard must NOT scrub an empty prefix"
    log_pass "empty prefix returns 0 (clean slate)"
}

test_orphan_prefix_scrubs_and_passes() {
    reset_log
    SENTINEL_EXISTS=false PREFIX_KEYCOUNT=1 run_guard "cli/v0.0.0/" \
        || log_fail "orphan prefix should scrub and pass; guard returned non-zero"
    grep -q "s3 rm .*cli/v0.0.0/ --endpoint-url .*--recursive" "$TEMP/aws.log" \
        || log_fail "guard must invoke 'aws s3 rm --recursive' to scrub the orphan"
    log_pass "orphan prefix scrubs and returns 0 (recovery path)"
}

test_dry_run_skips() {
    reset_log
    SENTINEL_EXISTS=true PREFIX_KEYCOUNT=1 DRY_RUN=true run_guard "cli/v0.0.0/" \
        || log_fail "DRY_RUN=true should pass regardless of state"
    grep -q "s3api head-object" "$TEMP/aws.log" \
        && log_fail "DRY_RUN must not call aws at all"
    log_pass "DRY_RUN=true skips all checks"
}

test_sealed_prefix_aborts
test_empty_prefix_passes
test_orphan_prefix_scrubs_and_passes
test_dry_run_skips

echo ""
log_pass "all sentinel-aware write_once_guard cases"
