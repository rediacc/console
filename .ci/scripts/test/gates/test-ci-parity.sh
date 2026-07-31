#!/bin/bash
# Both-directions test for scripts/check-ci-parity.ts.
#
# The gate's promise: the local gate set and the CI quality surface agree, so a
# local run catches CI failures before a push AND nothing runs locally that CI
# never enforces. It replaced two gates that each covered one direction; the
# third relation (locally-run, never CI-run) had no gate at all, which is
# rediacc/console#549.
#
# WHY CASE 3 IS THE IMPORTANT ONE. The analysis this gate came from first
# reported ZERO findings, because it matched whole workflow FILE TEXT for
# `npm run <key>` and a step NAME contained the literal `npm run ci`. That made
# the entire gate set look CI-executed and the reverse direction vacuously
# empty -- a gate built that way reports perfect parity forever. Case 3 pins the
# defect as a regression case, on a fixture whose step name names the very gate
# its run: block does not run.
#
# Fixtures live under CI_PARITY_ROOT with the gate list injected through
# CI_PARITY_MANIFEST, so no tracked file is ever mutated.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/scripts/check-ci-parity.ts"

LAST_OUT=""

run_gate() {
    local root="$1" rc=0
    LAST_OUT="$(cd "$REPO_ROOT" &&
        CI_PARITY_ROOT="$root" CI_PARITY_MANIFEST="$root/manifest.json" \
            npx tsx "$GATE" 2>&1)" || rc=$?
    # A wrong exit code says nothing about WHY. The helpers print only the
    # assertion message, so opt-in echo of the real output is the difference
    # between a five-second diagnosis and rebuilding the fixture by hand.
    if [[ -n "${CI_PARITY_TEST_DEBUG:-}" ]]; then
        printf 'rc=%s\n%s\n' "$rc" "$LAST_OUT" >&2
    fi
    return "$rc"
}

# The script sets a case can give the fixture. They are per-case rather than
# shared because R1 fires on any check:ci-* key the manifest does not carry, so
# a one-size package.json would redden every case for a reason it is not about.
SCRIPTS_ALPHA='"check:ci-alpha": ".ci/scripts/quality/check-alpha.sh"'
SCRIPTS_BETA='"check:ci-beta": "tsx scripts/check-beta.ts"'
SCRIPTS_ALPHA_BETA="$SCRIPTS_ALPHA,
    $SCRIPTS_BETA"
SCRIPTS_AGGREGATOR="$SCRIPTS_ALPHA_BETA,
    \"check:i18n\": \"npm run check:ci-nested\",
    \"check:ci-nested\": \"tsx scripts/check-nested.ts\""

# scaffold <root> <steps> [<scripts-json-body>] -- the parity surface every case
# shares: ci.yml whose `quality` job calls ci-quality.yml, which is where the
# fixture's steps go. Reached by `uses:` iteration exactly as the real surface
# is, so the computed-surface case gets its shape for free.
scaffold() {
    local root="$1" steps="$2" scripts="${3:-$SCRIPTS_ALPHA}"
    mkdir -p "$root/.github/workflows" "$root/.ci/scripts/quality" "$root/scripts"
    # The gate existence-checks every path-shaped leaf, so the fixture's leaves
    # have to be real files or every case would fail for the wrong reason.
    touch "$root/.ci/scripts/quality/check-alpha.sh" \
        "$root/scripts/check-beta.ts" "$root/scripts/check-nested.ts"
    cat >"$root/package.json" <<JSON
{
  "name": "fixture",
  "scripts": {
    $scripts
  }
}
JSON
    # Both entry jobs are present: paritySurface() returns the EMPTY surface
    # when one is missing, which the preflight then refuses on, so a fixture
    # without review-gate would make every case refuse instead of assert.
    cat >"$root/.github/workflows/ci.yml" <<'YAML'
name: ci
on: push
jobs:
  quality:
    uses: ./.github/workflows/ci-quality.yml
  review-gate:
    runs-on: ubuntu-latest
    steps:
      - name: Review threads
        run: echo review
YAML
    cat >"$root/.github/workflows/ci-quality.yml" <<YAML
name: quality
on: workflow_call
jobs:
  lane:
    runs-on: ubuntu-latest
    steps:
$steps
YAML
}

# manifest <root> <json-array>
manifest() {
    printf '%s\n' "$2" >"$1/manifest.json"
}

STEP_ALPHA='      - name: Alpha
        run: npm run check:ci-alpha'

MANIFEST_ALPHA='[{"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,
  "leaves":[".ci/scripts/quality/check-alpha.sh"],
  "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml","job":"lane","step":"Alpha"}}]'

# ---------------------------------------------------------------------------

test_declared_step_that_really_runs_it_passes() {
    local d="$1"
    scaffold "$d" "$STEP_ALPHA"
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a manifest gate whose declared step really runs it must pass"
    assert_contains "$LAST_OUT" "agree in both directions" "reports the clean verdict"
    log_pass "a manifest gate whose declared CI step really runs it passes"
}

test_chain_only_gate_fails() {
    # The #549 control: a gate the local set runs that no workflow step does.
    local d="$1"
    scaffold "$d" "$STEP_ALPHA" "$SCRIPTS_ALPHA_BETA"
    manifest "$d" '[{"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,
      "leaves":[".ci/scripts/quality/check-alpha.sh"],
      "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml","job":"lane","step":"Alpha"}},
      {"id":"check:ci-beta","run":"npm run check:ci-beta","gate":true,
      "leaves":["scripts/check-beta.ts"],
      "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml","job":"lane","step":"Beta"}}]'

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a gate no workflow step runs must fail"
    assert_contains "$LAST_OUT" "check:ci-beta" "names the chain-only gate"
    assert_contains "$LAST_OUT" "R3" "reports it in the local-only direction"
    log_pass "a gate that runs locally and in no workflow step fails (the #549 control)"
}

test_step_name_is_not_an_invocation() {
    # The live defect from the plan's section 1.4, pinned as a regression case:
    # the step NAME contains `npm run check:ci-beta` while its run: does not.
    local d="$1"
    scaffold "$d" '      - name: npm run check:ci-beta
        run: npm run check:ci-alpha' "$SCRIPTS_BETA"
    manifest "$d" '[{"id":"check:ci-beta","run":"npm run check:ci-beta","gate":true,
      "leaves":["scripts/check-beta.ts"],
      "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml","job":"lane","step":"npm run check:ci-beta"}}]'

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a step whose NAME names the gate must not count as coverage"
    assert_contains "$LAST_OUT" "check:ci-beta" "still reports the uncovered gate"
    assert_contains "$LAST_OUT" "runs something else" "says the pointed-at step runs something else"
    log_pass "a step name containing an npm invocation is not coverage"
}

test_npm_run_ci_in_a_run_block_is_a_tautology() {
    local d="$1"
    scaffold "$d" '      - name: Everything
        run: npm run ci'
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "npm run ci inside the surface must fail"
    assert_contains "$LAST_OUT" "tautology" "reports it as a tautology"
    assert_contains "$LAST_OUT" "vacuous" "explains that it makes every assertion vacuous"
    assert_contains "$LAST_OUT" "check:ci-alpha" "and does NOT treat it as coverage for the alpha gate"
    log_pass "npm run ci in a run: block is an error, never coverage"
}

test_ci_only_gate_fails() {
    local d="$1"
    scaffold "$d" '      - name: Orphan
        run: .ci/scripts/quality/check-orphan.sh
'"$STEP_ALPHA"
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a CI-run shell gate with no manifest entry must fail"
    assert_contains "$LAST_OUT" "check-orphan.sh" "names the CI-only gate"
    assert_contains "$LAST_OUT" "R2" "reports it in the ci-only direction"
    log_pass "a shell gate CI runs with no manifest entry fails"
}

test_defined_gate_absent_from_the_manifest_fails() {
    # R1: a check:ci-* key that exists in package.json but is scheduled by
    # nothing is inert -- it looks present, it greps, it passes review, and it
    # examines nothing.
    local d="$1"
    scaffold "$d" "$STEP_ALPHA" "$SCRIPTS_ALPHA_BETA"
    manifest "$d" '[{"id":"check:ci-beta","run":"npm run check:ci-beta","gate":true,
      "leaves":["scripts/check-beta.ts"],
      "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml","job":"lane","step":"Alpha"}}]'

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a defined-but-unlisted check:ci-* key must fail"
    assert_contains "$LAST_OUT" "check:ci-alpha" "names the inert gate"
    assert_contains "$LAST_OUT" "R1" "reports it as the defined-but-never-run break"
    log_pass "a check:ci-* key absent from the manifest fails"
}

test_aggregator_transitivity() {
    # check:ci-nested is not named by any workflow step directly; it is reached
    # through check:i18n. A naive substring test over the aggregator reports it
    # as dead and is simply wrong, so the resolver walks the graph.
    local d="$1"
    scaffold "$d" '      - name: i18n
        run: npm run check:i18n' "$SCRIPTS_AGGREGATOR"
    manifest "$d" '[{"id":"check:ci-nested","run":"npm run check:ci-nested","gate":true,
      "leaves":["scripts/check-nested.ts"],
      "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml","job":"lane","step":"i18n"}},
      {"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,
      "leaves":[".ci/scripts/quality/check-alpha.sh"],
      "ci":{"kind":"local-only","blocker":"needs release credentials no developer machine holds, so no workflow can run it"}},
      {"id":"check:ci-beta","run":"npm run check:ci-beta","gate":true,
      "leaves":["scripts/check-beta.ts"],
      "ci":{"kind":"local-only","blocker":"needs release credentials no developer machine holds, so no workflow can run it"}}]'

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a gate reached only through an aggregator must count as covered"
    log_pass "coverage through an aggregator resolves transitively"
}

test_workspace_scoping() {
    # `npm run test:unit -w @rediacc/cli` resolves in that workspace's manifest,
    # not the root one. Without this the key looks undefined and the existence
    # check false-positives.
    local d="$1"
    scaffold "$d" '      - name: CLI units
        run: npm run test:unit -w @rediacc/cli'
    mkdir -p "$d/packages/cli"
    cat >"$d/packages/cli/package.json" <<'JSON'
{ "name": "@rediacc/cli", "scripts": { "test:unit": "vitest run" } }
JSON
    manifest "$d" '[{"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,
      "leaves":["vitest"],
      "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml","job":"lane","step":"CLI units"}}]'

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "the declared leaves must not silently match the root manifest"
    assert_contains "$LAST_OUT" "vitest" "the workspace script resolved to its real leaf"
    assert_contains "$LAST_OUT" "hygiene" "and the root-key mismatch is a hygiene finding, not a coverage one"
    log_pass "a workspace-scoped invocation resolves in that workspace's manifest"
}

test_manifest_rot_is_reported() {
    local d="$1"
    scaffold "$d" "$STEP_ALPHA"
    manifest "$d" '[{"id":"check:ci-alpha","run":"npm run check:ci-alpha","gate":true,
      "leaves":[".ci/scripts/quality/check-alpha.sh"],
      "ci":{"kind":"step","workflow":".github/workflows/ci-quality.yml","job":"ghost-lane","step":"Alpha"}}]'

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a pointer naming a job that does not exist must fail"
    assert_contains "$LAST_OUT" "ghost-lane" "names the job that is not there"
    log_pass "a stale ci pointer is reported rather than trusted"
}

test_exemption_clears_a_finding() {
    local d="$1"
    scaffold "$d" '      - name: Orphan
        run: .ci/scripts/quality/check-orphan.sh
'"$STEP_ALPHA"
    manifest "$d" "$MANIFEST_ALPHA"
    cat >"$d/.ci-parity-exempt" <<'EOF'
# BLOCKER: reads the pull request body through the GitHub API, so there is nothing for a local checkout to validate before the PR exists
ci-only  .ci/scripts/quality/check-orphan.sh
EOF

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a direction-tagged BLOCKER exemption must clear the finding"
    log_pass "a valid direction-tagged exemption silences a finding"
}

test_low_effort_blocker_is_rejected() {
    # The exemption list is a hole in the promise; the reason has to be real.
    local d="$1"
    scaffold "$d" '      - name: Orphan
        run: .ci/scripts/quality/check-orphan.sh
'"$STEP_ALPHA"
    manifest "$d" "$MANIFEST_ALPHA"
    cat >"$d/.ci-parity-exempt" <<'EOF'
# BLOCKER: tbd
ci-only  .ci/scripts/quality/check-orphan.sh
EOF

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a low-effort BLOCKER must be rejected by the shared validator"
    assert_contains "$LAST_OUT" "BLOCKER validation failed" "names the validator failure"
    log_pass "a low-effort BLOCKER reason is rejected"
}

test_missing_direction_tag_is_rejected() {
    # The tag is load-bearing: the liveness oracle differs per direction, so an
    # untagged entry cannot be checked for staleness at all.
    local d="$1"
    scaffold "$d" '      - name: Orphan
        run: .ci/scripts/quality/check-orphan.sh
'"$STEP_ALPHA"
    manifest "$d" "$MANIFEST_ALPHA"
    cat >"$d/.ci-parity-exempt" <<'EOF'
# BLOCKER: reads the pull request body through the GitHub API, so there is nothing for a local checkout to validate before the PR exists
.ci/scripts/quality/check-orphan.sh
EOF

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "an exemption with no direction must be rejected"
    assert_contains "$LAST_OUT" "ci-only" "tells the author which directions exist"
    log_pass "an exemption without a direction tag is rejected"
}

test_path_in_a_yaml_comment_is_not_an_invocation() {
    # Too-loud guard: ci-build-renet.yml carries "# Keep the version in sync with
    # .ci/scripts/quality/lint.sh". Prose is not a step.
    local d="$1"
    scaffold "$d" '      # see .ci/scripts/quality/check-orphan.sh for the rules
'"$STEP_ALPHA"
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "a script path inside a YAML comment must not count as an invocation"
    log_pass "a path mentioned in a comment is not treated as a gate invocation"
}

test_non_gate_scripts_are_not_swept_in() {
    # Build, deploy and release helpers are steps, not gates, and have no
    # business in a local gate set.
    local d="$1"
    scaffold "$d" '      - name: Upload
        run: .ci/scripts/deploy/upload-repos-to-r2.sh
      - name: Pack
        run: .ci/scripts/build/pack-cli-npm.sh
'"$STEP_ALPHA"
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 0 "$rc" "deploy/build helpers must not be treated as gates"
    log_pass "only quality/security check-*.sh and test/test-*.sh count as gates"
}

test_test_dir_gates_are_swept_in() {
    # The widened rule, and the reason it was widened: test-write-once-guard.sh
    # and test-install-script.sh ran in Quality/Static and nowhere else, and the
    # old quality|security-only pattern could not see either (plan finding F3).
    local d="$1"
    scaffold "$d" '      - name: Write-once guard
        run: .ci/scripts/test/test-write-once-guard.sh
'"$STEP_ALPHA"
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a .ci/scripts/test/test-*.sh gate CI runs must be swept in"
    assert_contains "$LAST_OUT" "test-write-once-guard.sh" "names the test-dir gate"
    log_pass "a .ci/scripts/test/test-*.sh gate counts as gate-shaped (F3)"
}

test_empty_manifest_refuses() {
    local d="$1"
    scaffold "$d" "$STEP_ALPHA"
    manifest "$d" '[]'

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "an empty manifest means nothing asserted, which must fail"
    assert_contains "$LAST_OUT" "Refusing to run" "refuses rather than reporting a clean run"
    log_pass "an empty manifest refuses to run (anti-vacuity)"
}

test_empty_workflow_tree_refuses() {
    local d="$1"
    mkdir -p "$d/.github/workflows"
    cat >"$d/package.json" <<'JSON'
{ "name": "fixture", "scripts": { "check:ci-alpha": "echo alpha" } }
JSON
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "an empty workflow tree means nothing asserted, which must fail"
    assert_contains "$LAST_OUT" "Refusing to run" "refuses rather than reporting a clean run"
    log_pass "an empty workflow tree refuses to run (anti-vacuity)"
}

test_parity_surface_is_computed_not_named() {
    # A lane workflow reachable only through `uses:` is in the surface without
    # being named anywhere in the gate. A hand-listed surface could be silently
    # retired by renaming a file; a computed closure cannot.
    local d="$1"
    scaffold "$d" "$STEP_ALPHA"
    cat >>"$d/.github/workflows/ci-quality.yml" <<'YAML'
  extra:
    uses: ./.github/workflows/ci-brand-new-lane.yml
YAML
    cat >"$d/.github/workflows/ci-brand-new-lane.yml" <<'YAML'
name: brand new lane
on: workflow_call
jobs:
  lane:
    runs-on: ubuntu-latest
    steps:
      - name: Orphan in a lane nothing names
        run: .ci/scripts/quality/check-brand-new.sh
YAML
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a gate in a transitively reachable lane must be in scope"
    assert_contains "$LAST_OUT" "check-brand-new.sh" "names the gate from the new lane"
    assert_contains "$LAST_OUT" "ci-brand-new-lane.yml" "and the lane is in the computed surface"
    log_pass "the parity surface is computed by uses: iteration, not by naming files"
}

test_battery_equality_is_enforced() {
    # Without this, flattening run-all.sh recreates #549 once per test: a new
    # test would run in CI via the battery and never locally.
    local d="$1"
    scaffold "$d" '      - name: Quality-gate unit tests
        run: .ci/scripts/test/run-all.sh
'"$STEP_ALPHA"
    mkdir -p "$d/.ci/scripts/test/gates"
    touch "$d/.ci/scripts/test/gates/test-only-on-disk.sh"
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a battery test on disk with no manifest entry must fail"
    assert_contains "$LAST_OUT" "test-only-on-disk.sh" "names the unscheduled battery test"
    assert_contains "$LAST_OUT" "battery" "reports it as a battery-equality break"
    log_pass "a battery test on disk with no qualityGateTest entry fails"
}

test_missing_entry_job_collapses_the_surface() {
    # Renaming ci.yml's `quality` job must not silently shrink the surface to
    # nothing while still reporting a clean run. That is the vacuity failure the
    # whole gate exists to prevent, so it refuses instead.
    local d="$1"
    scaffold "$d" "$STEP_ALPHA"
    sed -i 's/^  quality:$/  quality-renamed:/' "$d/.github/workflows/ci.yml"
    manifest "$d" "$MANIFEST_ALPHA"

    local rc=0
    run_gate "$d" || rc=$?
    assert_exit_code 1 "$rc" "a missing entry job must refuse, not report a clean run"
    assert_contains "$LAST_OUT" "Refusing to run" "refuses rather than passing over an empty surface"
    assert_contains "$LAST_OUT" "parity surface is empty" "says which input went missing"
    log_pass "renaming ci.yml's quality job collapses the surface and refuses"
}

log_test "test-ci-parity"
with_temp_dir test_declared_step_that_really_runs_it_passes
with_temp_dir test_chain_only_gate_fails
with_temp_dir test_step_name_is_not_an_invocation
with_temp_dir test_npm_run_ci_in_a_run_block_is_a_tautology
with_temp_dir test_ci_only_gate_fails
with_temp_dir test_defined_gate_absent_from_the_manifest_fails
with_temp_dir test_aggregator_transitivity
with_temp_dir test_workspace_scoping
with_temp_dir test_manifest_rot_is_reported
with_temp_dir test_exemption_clears_a_finding
with_temp_dir test_low_effort_blocker_is_rejected
with_temp_dir test_missing_direction_tag_is_rejected
with_temp_dir test_path_in_a_yaml_comment_is_not_an_invocation
with_temp_dir test_non_gate_scripts_are_not_swept_in
with_temp_dir test_test_dir_gates_are_swept_in
with_temp_dir test_empty_manifest_refuses
with_temp_dir test_empty_workflow_tree_refuses
with_temp_dir test_missing_entry_job_collapses_the_surface
with_temp_dir test_parity_surface_is_computed_not_named
with_temp_dir test_battery_equality_is_enforced
echo ""
log_pass "all tests passed"
