#!/bin/bash
# Integration test for scripts/check-suppression-liveness.ts.
#
# The gate must be provable BOTH ways: it passes on a clean tree AND it fires on
# a planted stale entry. A gate that only ever passes proves nothing — this repo
# has shipped several of those (check_stale_entries in audit.sh skipped the
# common staleness case for its whole life; check-no-app-admin-perm.sh was never
# wired into a job at all).
#
# Every case runs against a FIXTURE root via SUPPRESSION_LIVENESS_ROOT so no
# tracked file is ever mutated — the working tree routinely holds uncommitted
# work from other sessions (CLAUDE.md session default 1).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-suppression-liveness.ts"

# Build a fixture repo that is healthy on every probe, then let each test bend
# exactly one thing. Echoes the fixture path.
make_fixture() {
    local t
    t="$(mktemp -d)"
    mkdir -p "$t/.github/workflows" "$t/.github/actions/app-token" "$t/private/renet"
    cp "$REPO_ROOT/package.json" "$t/package.json"
    cp "$REPO_ROOT/package-lock.json" "$t/package-lock.json"
    cp "$REPO_ROOT/.github/workflows/ci.yml" "$t/.github/workflows/ci.yml"
    cp "$REPO_ROOT/.github/actions/app-token/action.yml" "$t/.github/actions/app-token/action.yml"
    [[ -f "$REPO_ROOT/private/renet/Dockerfile" ]] && cp "$REPO_ROOT/private/renet/Dockerfile" "$t/private/renet/Dockerfile"
    [[ -f "$REPO_ROOT/private/renet/go.mod" ]] && cp "$REPO_ROOT/private/renet/go.mod" "$t/private/renet/go.mod"
    echo "$t"
}

run_gate() {
    local root="$1"
    shift
    # ACTION_REFS_MIN_FILES=2, NOT 0. make_fixture plants exactly two .github
    # files (ci.yml and the app-token action), and collectActionRefs carries a
    # vacuity floor of 10 sized for the real tree -- which threw VACUOUS here on
    # 2026-09-05 and took the whole gate-test battery red. Telling the probe the
    # fixture's TRUE corpus size keeps the floor meaningful (an empty or
    # half-built fixture still refuses) instead of switching the guard off, which
    # is what a 0 would do.
    (cd "$REPO_ROOT" && SUPPRESSION_LIVENESS_ROOT="$root" ACTION_REFS_MIN_FILES=2 \
        npx tsx "$GATE" "$@" 2>&1) || return $?
}

test_passes_on_real_repo() {
    local out rc=0
    out=$(cd "$REPO_ROOT" && npx tsx "$GATE" 2>&1) || rc=$?
    assert_exit_code 0 "$rc" "live tree should have no FAIL-tier stale entries"
    assert_contains "$out" "probes:" "prints a probe summary"
    log_pass "passes clean on the real repository"
}

test_fires_on_dead_deps_entry() {
    local t out rc=0
    t="$(make_fixture)"
    printf '# BLOCKER: planted dead package to prove the deps probe fires in this test\ntotally-not-a-real-package\n' >"$t/.deps-upgrade-blocklist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "a dead deps entry must fail the gate"
    assert_contains "$out" "totally-not-a-real-package" "names the dead entry"
    assert_contains "$out" ".deps-upgrade-blocklist:2" "cites file:line"
    assert_contains "$out" "npm run check:deps" "emits the exact follow-up command"
    log_pass "fires on a dead .deps-upgrade-blocklist entry"
}

test_no_false_positive_on_live_entry() {
    local t out rc=0
    t="$(make_fixture)"
    # eslint is genuinely declared in the root manifest, which is the only one
    # the fixture carries. (zod would NOT work here: it appears in the real
    # package.json only under "overrides", and an override is not a declaration
    # — the deps probe would correctly condemn it.)
    printf '# BLOCKER: live package pinned deliberately, must not be reported as stale\neslint\n' >"$t/.deps-upgrade-blocklist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "a declared package must not be condemned"
    assert_not_contains "$out" "FAIL" "no findings for a live entry"
    log_pass "does not condemn a still-declared package"
}

test_oracle_floor_skips_instead_of_condemning() {
    local t out rc=0
    t="$(make_fixture)"
    # Two deps only: far below the deps probe's floor of 20. The entry must be
    # SKIPPED, never condemned. This is the direct analogue of the total_vulns>0
    # guard in .ci/scripts/security/audit.sh.
    cat >"$t/package.json" <<'EOF'
{"name":"fixture","dependencies":{"a":"1.0.0","b":"1.0.0"}}
EOF
    printf '# BLOCKER: must survive because the oracle is too small to be trusted here\nsomething\n' >"$t/.deps-upgrade-blocklist"
    # A second, LIVE entry on a healthy probe, so the run still checks something.
    # Without it the only entry is the skipped one, the run asserts nothing, and
    # the anti-vacuity rule fails it for a different reason than the one under
    # test here.
    printf '# BLOCKER: pinned deliberately; referenced only from a composite action file\nactions/create-github-app-token\n' >"$t/.actions-upgrade-blocklist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "a suspect oracle must not fail the gate"
    assert_contains "$out" "SKIP" "reports a skip"
    assert_contains "$out" "floor is 20" "explains the floor that was not met"
    assert_not_contains "$out" "FAIL" "must not condemn against a suspect oracle"
    log_pass "oracle floor skips loudly instead of condemning"
}

test_vacuous_run_fails() {
    local t out rc=0
    t="$(mktemp -d)"
    # No manifests, no lockfile, no .github, no go.mod: every oracle unavailable,
    # yet entries exist. The run proved nothing and must not report success.
    printf '# BLOCKER: entry that cannot be checked because every oracle is missing here\nsomething\n' >"$t/.deps-upgrade-blocklist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "a vacuous run must fail"
    assert_contains "$out" "vacuous" "says the run proved nothing"
    log_pass "vacuous run (all probes skipped, entries present) fails"
}

test_composite_action_counts_as_a_reference() {
    local t out rc=0
    t="$(make_fixture)"
    # create-github-app-token is referenced ONLY from the composite action.
    # Before collectActionRefs() scanned .github/actions, this entry would have
    # been wrongly condemned.
    printf '# BLOCKER: pinned deliberately; referenced only from a composite action file\nactions/create-github-app-token\n' >"$t/.actions-upgrade-blocklist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "composite-action reference must count as live"
    assert_not_contains "$out" "create-github-app-token" "not reported dead"
    log_pass "composite-action references keep an entry alive"
}

test_overrides_warn_never_fail() {
    local t out rc=0
    t="$(make_fixture)"
    python3 - "$t" <<'PY'
import json,sys
p=sys.argv[1]+'/package.json'
d=json.load(open(p))
d.setdefault('overrides',{})['ghost-pkg']='^1.0.0'
d.setdefault('_overridesReasons',{})['ghost-pkg']='BLOCKER: forces a patched transitive that is not currently installed anywhere'
json.dump(d,open(p,'w'),indent=2)
PY
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "a dead override must WARN, never fail"
    assert_contains "$out" "WARN" "reported at warn tier"
    assert_contains "$out" "npm pkg delete" "offers the removal command"
    log_pass "dead override warns and never fails the gate"
}

test_preventive_annotation_silences_override_warning() {
    local t out rc=0
    t="$(make_fixture)"
    python3 - "$t" <<'PY'
import json,sys
p=sys.argv[1]+'/package.json'
d=json.load(open(p))
d.setdefault('overrides',{})['ghost-pkg']='^1.0.0'
d.setdefault('_overridesReasons',{})['ghost-pkg']='BLOCKER: preventive — guards against a vulnerable transitive returning to the tree'
json.dump(d,open(p,'w'),indent=2)
PY
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 0 "$rc" "preventive override stays silent"
    assert_not_contains "$out" "ghost-pkg" "annotated override is not reported"
    log_pass "'BLOCKER: preventive —' opts an override out of the warning"
}

test_findings_are_capped() {
    local t out rc=0
    t="$(make_fixture)"
    {
        echo "# BLOCKER: bulk planted dead entries to prove the per-probe output cap works"
        for i in $(seq 1 25); do echo "not-a-real-package-$i"; done
    } >"$t/.deps-upgrade-blocklist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "bulk dead entries still fail"
    assert_contains "$out" "and 15 more" "rolls up beyond the per-probe cap"
    log_pass "output is capped per probe with a roll-up line"
}

test_fires_on_dead_template_skiplist_entry() {
    local t out rc=0
    t="$(make_fixture)"
    mkdir -p "$t/packages/json/templates"
    cp -r "$REPO_ROOT/packages/json/templates/." "$t/packages/json/templates/" 2>/dev/null || true
    printf 'gone/removed-template\n' >"$t/packages/json/.templates-skiplist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "a skiplist entry for a deleted template must fail"
    assert_contains "$out" "gone/removed-template" "names the dead template"
    log_pass "fires on a .templates-skiplist entry whose template is gone"
}

test_cli_i18n_prefix_matching() {
    local t out rc=0
    t="$(make_fixture)"
    mkdir -p "$t/packages/cli/src/i18n/locales/en"
    cp "$REPO_ROOT/packages/cli/src/i18n/locales/en/cli.json" "$t/packages/cli/src/i18n/locales/en/cli.json"
    # First entry is a live PREFIX (matches many leaves); second matches nothing.
    printf '# BLOCKER: live dynamic-key prefix that still matches leaves in the catalog\ncommands.sync.\n\n# BLOCKER: prefix matching nothing so it can exempt nothing from the orphan scan\nnope.not.a.real.prefix.\n' >"$t/.cli-i18n-orphan-allowlist"
    out=$(run_gate "$t") || rc=$?
    rm -rf "$t"
    assert_exit_code 1 "$rc" "a prefix matching zero leaves must fail"
    assert_contains "$out" "nope.not.a.real.prefix." "names the dead prefix"
    assert_not_contains "$out" "commands.sync." "live prefix must survive prefix-matching"
    log_pass "cli-i18n prefixes are matched as prefixes, not exact keys"
}

log_test "test-suppression-liveness"
test_passes_on_real_repo
test_fires_on_dead_deps_entry
test_no_false_positive_on_live_entry
test_oracle_floor_skips_instead_of_condemning
test_vacuous_run_fails
test_composite_action_counts_as_a_reference
test_overrides_warn_never_fail
test_preventive_annotation_silences_override_warning
test_findings_are_capped
test_fires_on_dead_template_skiplist_entry
test_cli_i18n_prefix_matching
echo ""
log_pass "all tests passed"
