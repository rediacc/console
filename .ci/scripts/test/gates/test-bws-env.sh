#!/bin/bash
# Both-ways test for .ci/lib/bws-env.sh, the shared Bitwarden fetcher local
# scripts use instead of reading private/account/.env.
#
# WHY THIS CLASS NEEDS A TEST. Every failure mode of a credential fetcher is
# quiet by nature: an empty value exports cleanly, a missing token looks like a
# network blip, and a silent fallback to a local file makes a broken fetch work
# on the author's machine and nowhere else. So the cases that matter here are
# mostly REFUSALS, and each is planted rather than described.
#
# `bws` is faked on PATH. The real binary is never invoked and no live store is
# touched -- the fake is the point, not a limitation: it lets the empty-value and
# missing-name cases be tested at all, which a live store cannot do on demand.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

HELPER="$REPO_ROOT/.ci/lib/bws-env.sh"

# fixture <dir> <listing-json> -- a fake bws plus a map naming two secrets
fixture() {
    local d="$1" listing="$2"
    mkdir -p "$d/bin" "$d/.ci/config"
    printf '%s' "$listing" >"$d/listing.json"
    cat >"$d/bin/bws" <<FAKE
#!/bin/bash
# the real bws wraps --output json in ANSI unless --color no is passed; a fake
# that ignores the flag would let a regression in the caller go unnoticed.
for a in "\$@"; do [ "\$a" = "--color" ] && seen=1; done
[ -n "\${seen:-}" ] || { echo "fake bws: caller did not pass --color" >&2; exit 3; }
cat "$d/listing.json"
FAKE
    chmod +x "$d/bin/bws"
    cat >"$d/.ci/config/bws-secret-map.json" <<'MAP'
{ "project": "p", "secrets": { "ALPHA_TOKEN": { "id": "1" }, "BETA_TOKEN": { "id": "2" } } }
MAP
}

run_load() {
    local d="$1"
    shift
    (
        set +e
        export BWS_ENV_ROOT="$d" BWS_BIN="$d/bin/bws" PATH="$d/bin:$PATH"
        # shellcheck disable=SC1090
        source "$HELPER"
        bws_env_load "$@" 2>&1
        echo "rc=$?"
    )
}

BOTH='[{"key":"ALPHA_TOKEN","value":"a-val"},{"key":"BETA_TOKEN","value":"b-val"}]'

test_loads_both() {
    local d="$1"
    fixture "$d" "$BOTH"
    local out
    out="$(BWS_ACCESS_TOKEN=t run_load "$d")"
    assert_contains "$out" "exported 2 secret(s)" "a complete store exports every mapped name"
    assert_contains "$out" "rc=0" "and succeeds"
    assert_not_contains "$out" "a-val" "NEVER prints a value"
    log_pass "loads every mapped name, and prints no value"
}

test_named_subset() {
    local d="$1"
    fixture "$d" "$BOTH"
    local out
    out="$(BWS_ACCESS_TOKEN=t run_load "$d" ALPHA_TOKEN)"
    assert_contains "$out" "exported 1 secret(s)" "an explicit list fetches only those"
    log_pass "an explicit name list is honoured"
}

test_empty_value_is_absent() {
    # The whole point: sm-action exports "" without complaint and zod strips an
    # unknown key, so a blank ships a broken feature that still returns 200.
    local d="$1"
    fixture "$d" '[{"key":"ALPHA_TOKEN","value":""},{"key":"BETA_TOKEN","value":"b"}]'
    local out
    out="$(BWS_ACCESS_TOKEN=t run_load "$d")"
    assert_contains "$out" "ALPHA_TOKEN" "the empty name is reported"
    assert_contains "$out" "rc=1" "an empty value FAILS rather than exporting a blank"
    log_pass "an empty stored value is treated as absent, and fails"
}

test_missing_name_fails() {
    local d="$1"
    fixture "$d" '[{"key":"ALPHA_TOKEN","value":"a"}]'
    local out
    out="$(BWS_ACCESS_TOKEN=t run_load "$d")"
    assert_contains "$out" "BETA_TOKEN" "the missing name is named"
    assert_contains "$out" "rc=1" "a mapped name the store lacks fails"
    log_pass "a mapped name absent from the store fails, naming it"
}

test_no_token_refuses() {
    local d="$1"
    fixture "$d" "$BOTH"
    local out
    out="$(run_load "$d")"
    assert_contains "$out" "BWS_ACCESS_TOKEN is not set" "says which credential is missing"
    assert_contains "$out" "cannot come from Bitwarden" "and why it cannot be fetched"
    assert_contains "$out" "rc=1" "refuses"
    log_pass "a missing bootstrap token refuses with the reason"
}

test_bws_failure_is_not_silent() {
    local d="$1"
    fixture "$d" "$BOTH"
    printf '#!/bin/bash\nexit 1\n' >"$d/bin/bws"
    chmod +x "$d/bin/bws"
    local out
    out="$(BWS_ACCESS_TOKEN=t run_load "$d")"
    assert_contains "$out" "secret list failed" "a failing bws is reported"
    assert_contains "$out" "expired" "and points at the likeliest cause"
    assert_contains "$out" "rc=1" "refuses"
    log_pass "a failing bws call is named, not swallowed"
}

test_never_falls_back_to_env() {
    # A silent fallback is how a fetch that stopped working keeps passing locally.
    local d="$1"
    fixture "$d" '[{"key":"BETA_TOKEN","value":"b"}]'
    mkdir -p "$d/private/account"
    echo 'ALPHA_TOKEN=from-dot-env' >"$d/private/account/.env"
    local out
    out="$(BWS_ACCESS_TOKEN=t run_load "$d")"
    assert_contains "$out" "rc=1" "an absent name still fails even when .env has it"
    assert_not_contains "$out" "from-dot-env" "and the local copy is never read"
    log_pass "no silent fallback to .env"
}

log_test "test-bws-env"
with_temp_dir test_loads_both
with_temp_dir test_named_subset
with_temp_dir test_empty_value_is_absent
with_temp_dir test_missing_name_fails
with_temp_dir test_no_token_refuses
with_temp_dir test_bws_failure_is_not_silent
with_temp_dir test_never_falls_back_to_env
echo ""
log_pass "all tests passed"
