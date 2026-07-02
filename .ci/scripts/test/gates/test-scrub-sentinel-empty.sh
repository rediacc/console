#!/bin/bash
# Regression test for scrub-sentinel.sh's empty-prefix hang.
#
# Before commit 27e9a49ab the dry-run plan loop called `aws s3 ls --recursive`
# inside `count="$(... | wc -l)"`. `aws s3 ls` returns exit 1 when the prefix
# is empty, and `set -eo pipefail` made the whole script abort right after
# `count=0` was assigned -- silently, with the operator seeing only the
# "sentinel: absent" line and no exit message.
#
# This test pins the fix: a dry-run against a guaranteed-empty version must
# print the cli plan AND exit 0, regardless of whether the underlying R2 list
# call succeeds.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=lib/test-helpers.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

test_dry_run_completes_with_no_credentials() {
    # No R2 credentials => `aws s3api list-objects-v2` errors, the helper
    # returns 0, and the dry-run plan emits "objects: 0" for the cli product.
    # Critically: the script must reach the "dry-run: pass --execute" final
    # line. If pipefail kills it after the count assignment we'll see no exit
    # message and the test fails.
    local out rc=0
    out="$(R2_ACCESS_KEY_ID="invalid" \
        R2_SECRET_ACCESS_KEY="invalid" \
        R2_ENDPOINT="https://invalid.example.invalid" \
        bash "$REPO_ROOT/scripts/dev/scrub-sentinel.sh" v9.99.99 2>&1)" || rc=$?

    assert_exit_code 0 "$rc" "dry-run must succeed even with bad credentials"
    assert_contains "$out" "s3://rediacc-releases/cli/v9.99.99/" "cli plan line printed"
    assert_contains "$out" "dry-run: pass --execute" "script reached its final exit message"
    log_pass "empty-prefix dry-run completes without hanging"
}

test_dry_run_emits_zero_object_count() {
    # Cosmetic but important: the operator relies on the "objects: N" count
    # to decide whether the scrub is safe. If the helper falls back to a
    # malformed value (e.g. "None"), the count must still normalise to 0.
    local out
    out="$(R2_ACCESS_KEY_ID="invalid" \
        R2_SECRET_ACCESS_KEY="invalid" \
        R2_ENDPOINT="https://invalid.example.invalid" \
        bash "$REPO_ROOT/scripts/dev/scrub-sentinel.sh" v9.99.99 2>&1)"

    # One product (cli), one count line. Must contain "objects: 0".
    local zero_count
    zero_count="$(printf '%s\n' "$out" | grep -c 'objects: 0' || true)"
    assert_eq "1" "$zero_count" "objects: 0 emitted for the cli product"
    log_pass "object count normalises to 0 on empty/unreachable prefix"
}

test_dry_run_completes_with_no_credentials
test_dry_run_emits_zero_object_count

log_pass "all scrub-sentinel empty-prefix cases"
