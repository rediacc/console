#!/bin/bash
# Unit tests for write_once_guard() in .ci/scripts/deploy/upload-to-r2.sh.
# Mocks aws so the test runs offline and deterministically.
#
# Guards against regression to a dead key-specific sentinel (finding A).
# The guard must:
#   * exit 1 when `aws s3 ls <prefix>` returns non-empty (seal violated)
#   * return 0 when `aws s3 ls <prefix>` returns empty (path vacant)
#   * skip both checks when DRY_RUN=true

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
GUARD_SCRIPT="$ROOT_DIR/.ci/scripts/deploy/upload-to-r2.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_fail() {
    echo -e "${RED}FAIL:${NC} $*" >&2
    exit 1
}
log_pass() { echo -e "${GREEN}PASS:${NC} $*"; }

# Create a tempdir and a fake `aws` on PATH that returns scripted output.
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

cat >"$TEMP/aws" <<'FAKE'
#!/bin/bash
# Fake aws that returns whatever the test set in FAKE_AWS_OUTPUT and
# exits with FAKE_AWS_RC.
if [[ -n "${FAKE_AWS_OUTPUT:-}" ]]; then
    printf '%s\n' "$FAKE_AWS_OUTPUT"
fi
exit "${FAKE_AWS_RC:-0}"
FAKE
chmod +x "$TEMP/aws"
export PATH="$TEMP:$PATH"

# Set the minimum env that upload-to-r2.sh's prelude requires before we
# can source it without triggering the "required variable" exits.
RELEASES_BUCKET=rediacc-releases
R2_ENDPOINT=https://example.invalid
VERSION=0.0.0-test
CHANNEL=pr-0
DRY_RUN=false
export RELEASES_BUCKET R2_ENDPOINT VERSION CHANNEL DRY_RUN

# upload-to-r2.sh runs its main path when sourced; guard against that
# by extracting ONLY the write_once_guard function via sed.
sed -n '/^write_once_guard()/,/^}/p' "$GUARD_SCRIPT" >"$TEMP/guard.sh"

# Helpers it depends on (log_error, log_info). Minimal stubs to stderr.
cat >>"$TEMP/guard-bundle.sh" <<'HELPERS'
log_error() { echo "error: $*" >&2; }
log_info() { echo "info: $*" >&2; }
HELPERS
cat "$TEMP/guard.sh" >>"$TEMP/guard-bundle.sh"

# Run guard in a subshell so that a `exit 1` from the guard doesn't
# terminate the test driver. We check status with "|| true".

test_empty_prefix_passes() {
    FAKE_AWS_OUTPUT="" FAKE_AWS_RC=0 \
        bash -c "set -e; source '$TEMP/guard-bundle.sh'; write_once_guard 'cli/v0.0.0/' 'test'" ||
        log_fail "empty prefix should pass; guard returned non-zero"
    log_pass "empty prefix returns 0"
}

test_nonempty_prefix_aborts() {
    FAKE_AWS_OUTPUT="2026-04-23 12:00:00 1234 cli/v0.0.0/rdc-linux-x64" FAKE_AWS_RC=0 \
        bash -c "set -e; source '$TEMP/guard-bundle.sh'; write_once_guard 'cli/v0.0.0/' 'test'" \
        2>/dev/null &&
        log_fail "non-empty prefix should abort; guard returned zero"
    log_pass "non-empty prefix aborts (exit 1)"
}

test_dry_run_skips() {
    FAKE_AWS_OUTPUT="2026-04-23 12:00:00 1234 cli/v0.0.0/rdc-linux-x64" FAKE_AWS_RC=0 \
        DRY_RUN=true \
        bash -c "set -e; DRY_RUN=true; source '$TEMP/guard-bundle.sh'; write_once_guard 'cli/v0.0.0/' 'test'" ||
        log_fail "DRY_RUN=true should pass regardless of prefix state"
    log_pass "DRY_RUN=true skips the check"
}

test_empty_prefix_passes
test_nonempty_prefix_aborts
test_dry_run_skips

echo ""
log_pass "all write_once_guard cases"
