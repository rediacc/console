#!/bin/bash
# Unit test for the attested skip-plan reconciler,
# .ci/scripts/ci/skip-plan-reconcile.cjs (Wave B edge cases 25-32, section E).
#
# WHAT THIS GUARDS. `ci-complete` sees only caller-level scalars, and for a
# reusable caller that scalar reads `success` when every inner job succeeded
# OR self-skipped. Per-inner-job conclusions are not exposed to sibling jobs
# by any expression, so an inner job silently skipping while its siblings pass
# (the invisible cell) is undetectable at caller level. The reconciler closes
# that hole by checking the attested plan against the Jobs API at leaf level.
# Until it provably hard-fails on a planted mismatch, the scope engine's
# vector must never gate a real job; this file is that proof.
#
# THE PLAN IS THE ALLOWLIST. Run 30307775327 (healthy) had ELEVEN skipped
# inner jobs against zero failures, all legitimate: cached-vs-uncached
# variants, unexpanded matrix legs, one push-gated job. That exact shape is a
# fixture here and must NOT fire; only jobs the plan marked `run` may.
#
# Every failure case is paired with the passing control so nothing passes
# vacuously, and the fixture's shape (the eleven skips actually being there)
# is itself asserted, per the house doctrine: a validator that passes when
# given nothing is broken by definition.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

RECONCILE="$REPO_ROOT/.ci/scripts/ci/skip-plan-reconcile.cjs"
MAP="$REPO_ROOT/.ci/scripts/ci/scope-map.cjs"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

RUN_ID="30307775327"

# Base fixtures. The plan is generated FROM scope-map's job keys so a key
# rename there flows into the fixture (parity between the two tables is
# asserted separately). The jobs payload mirrors run 30307775327: a success
# leaf for every planned key, the eleven structural skips observed live, and
# unplanned extras the reconciler must ignore.
node -e '
const fs = require("fs");
const m = require(process.argv[1]);
const dir = process.argv[2];
const keys = Object.keys(m.JOB_SURFACES);
const plan = {
  run_id: process.argv[3],
  mode: "full",
  jobs: Object.fromEntries(keys.map((k) => [k, { run: true, reason: "full" }])),
};
fs.writeFileSync(dir + "/plan.json", JSON.stringify(plan, null, 2));
const S = (name) => ({ name, conclusion: "success" });
const K = (name) => ({ name, conclusion: "skipped" });
const jobs = [
  S("Initialize"),
  S("Tests + Infra / Unit"),
  S("Tests + Infra / E2E Workers (ubuntu-24.04)"),
  S("Tests + Infra / E2E Workers (fedora-43)"),
  S("Tests + Infra / E2E Ceph"),
  S("Tests + Infra / E2E Ceph Workers"),
  S("Tests + Infra / E2E K8s"),
  S("Tests + Infra / E2E K8s Ceph"),
  S("Tests + Infra / E2E K8s Multinode"),
  S("Tests + Infra / E2E Migrate"),
  S("Tests + Infra / Concurrent Fork Isolation"),
  S("Tests + Infra / Renet"),
  S("Tests + Infra / Account E2E"),
  S("Tests + Infra / Migration Test"),
  S("OPS Tests / OPS Provision (linux-amd64)"),
  S("OPS Tests / OPS Provision (macos-intel)"),
  S("OPS Tests / OPS Check (linux-arm64)"),
  S("Elite Run"),
  S("Tests + Infra / Update Flow / Update flow (Linux x64)"),
  S("Tests + Infra / Linux Packages"),
  S("Validate Install Methods / Linux (x64)"),
  S("Validate Install Methods / Linux (arm64)"),
  S("Validate Install Methods / macOS (ARM64)"),
  S("Validate Install Methods / Windows (x64)"),
  // The healthy eleven, verbatim from run 30307775327.
  K("Build (Renet) / Procwalk (${{ matrix.os }})"),
  K("Build (Renet) / Renet (Full)"),
  K("Build (Docker Fast) / Renet Docker"),
  K("Build (Docker Fast) / CLI Docker"),
  K("Build (Docker Fast) / JSON"),
  K("Build (Docker Fast) / CLI Docker (cached)"),
  K("Build (Docker Fast) / Server Docker (cached)"),
  K("Build (Docker Fast) / Devcontainer (amd64)"),
  K("Build (Docker Fast) / Devcontainer (arm64)"),
  K("Build (Docker Fast) / Devcontainer Manifest"),
  K("Check Release State"),
];
fs.writeFileSync(dir + "/jobs.json", JSON.stringify({ jobs }, null, 2));
' "$MAP" "$WORK" "$RUN_ID"

# mutate <in> <out> <js body over `data`> -- derive a fixture variant
mutate() {
    node -e '
const fs = require("fs");
const data = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
const fn = new Function("data", process.argv[3]);
fn(data);
fs.writeFileSync(process.argv[2], JSON.stringify(data, null, 2));
' "$1" "$2" "$3"
}

# run_reconcile <plan> <jobs> [run-id] -> prints exit code; streams captured
# SEPARATELY (failures must land on stderr, warnings on stdout).
run_reconcile() {
    local rc=0
    node "$RECONCILE" --plan "$1" --jobs "$2" --run-id "${3:-$RUN_ID}" \
        >"$WORK/out.txt" 2>"$WORK/err.txt" || rc=$?
    echo "$rc"
}
out() { cat "$WORK/out.txt"; }
err() { cat "$WORK/err.txt"; }

# ---------------------------------------------------------------------------

test_mandatory_invisible_cell_hard_fails() {
    # Edge case 25, the planted mismatch this whole chunk exists for: plan
    # says `Tests + Infra / Unit` runs, the leaf is skipped, every sibling
    # succeeded (so every caller scalar would read success). Must exit
    # non-zero with planned-run-but-skipped.
    mutate "$WORK/jobs.json" "$WORK/jobs-unit-skipped.json" \
        'data.jobs.find((j) => j.name === "Tests + Infra / Unit").conclusion = "skipped"'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-unit-skipped.json")" "1" \
        "a planned-run leaf that self-skipped must hard-fail"
    assert_contains "$(err)" "planned-run-but-skipped: 'unit' -> 'Tests + Infra / Unit'" \
        "with the key and the leaf named, on stderr"
    # CONTROL: the identical pipeline with the leaf back to success is green.
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json")" "0" \
        "the untouched healthy fixture reconciles clean"
    log_pass "the invisible cell hard-fails: planned-run leaf skipped, siblings green (case 25)"
}

test_healthy_eleven_must_not_fire() {
    # Section E: the plan is the allowlist. First prove the fixture SHAPE
    # (the eleven structural skips are really in there), or the silence below
    # would be a test of nothing.
    local skips
    skips="$(node -e '
const d = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
process.stdout.write(String(d.jobs.filter((j) => j.conclusion === "skipped").length));
' "$WORK/jobs.json")"
    assert_eq "$skips" "11" "the fixture carries the eleven structural skips from run $RUN_ID"

    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json")" "0" \
        "eleven structural skips against a full plan reconcile clean"
    assert_not_contains "$(err)" "planned-run-but-skipped" "no skip is flagged"
    assert_not_contains "$(out)" "::warning::" "and none is even warned about"

    # CONTROL: the reconciler CAN fire on this very fixture, and when it does
    # it blames only the planted key, never the structural skips.
    mutate "$WORK/jobs.json" "$WORK/jobs-ceph-skipped.json" \
        'data.jobs.find((j) => j.name === "Tests + Infra / E2E Ceph").conclusion = "skipped"'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-ceph-skipped.json")" "1" \
        "planting one scope-relevant skip flips the same fixture red"
    assert_contains "$(err)" "planned-run-but-skipped: 'e2e_ceph'" "blaming the planted key"
    assert_not_contains "$(err)" "Build (Docker Fast)" \
        "and never the structural skips: the plan is the allowlist"
    log_pass "the healthy eleven from run $RUN_ID stay silent; only planned jobs can fire (section E)"
}

test_planned_job_missing_hard_fails() {
    # Edge case 27: planned to run, absent from the Jobs API entirely (a
    # rename, a dropped workflow call, a DAG break).
    mutate "$WORK/jobs.json" "$WORK/jobs-no-unit.json" \
        'data.jobs = data.jobs.filter((j) => j.name !== "Tests + Infra / Unit")'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-no-unit.json")" "1" \
        "a planned job absent from the payload must hard-fail"
    assert_contains "$(err)" "planned-job-missing: 'unit'" "as planned-job-missing"
    # CONTROL: presence is what silences it (the healthy fixture passes).
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json")" "0" \
        "with the job present the same plan reconciles clean"
    log_pass "a planned job missing from the Jobs API hard-fails (case 27)"
}

test_over_running_warns_only() {
    # Edge case 28: plan says skip, job ran and passed. Over-running is the
    # safe direction (extra evidence), so it must warn and NOT block; blocking
    # it would punish the fail-open `!= 'false'` YAML polarity.
    mutate "$WORK/plan.json" "$WORK/plan-skip-unit.json" \
        'data.jobs.unit = { run: false, reason: "out-of-scope" }'
    assert_eq "$(run_reconcile "$WORK/plan-skip-unit.json" "$WORK/jobs.json")" "0" \
        "a planned-skip job that ran anyway must NOT fail the reconcile"
    assert_contains "$(out)" "::warning::planned-skip-but-ran: 'unit'" \
        "but it is warned about, on stdout, as an Actions annotation"
    assert_not_contains "$(err)" "FAIL" "and nothing lands on stderr"
    # CONTROL: the warning is earned, not constant. When the planned skip
    # actually skipped, silence.
    mutate "$WORK/jobs.json" "$WORK/jobs-unit-skipped2.json" \
        'data.jobs.find((j) => j.name === "Tests + Infra / Unit").conclusion = "skipped"'
    assert_eq "$(run_reconcile "$WORK/plan-skip-unit.json" "$WORK/jobs-unit-skipped2.json")" "0" \
        "a planned skip that skipped is clean"
    assert_not_contains "$(out)" "::warning::" "with no warning"
    log_pass "over-running warns only; honored skips are silent (case 28)"
}

test_missing_plan_hard_fails_polarity_inverted() {
    # Edge case 29, THE POLARITY INVERSION: the engine degrades toward more
    # CI, the reconciler degrades toward red. A missing attestation must
    # never read as green.
    assert_eq "$(run_reconcile "$WORK/does-not-exist.json" "$WORK/jobs.json")" "1" \
        "a missing plan artifact must hard-fail"
    assert_contains "$(err)" "skip-plan-missing" "named as skip-plan-missing"
    assert_contains "$(err)" "degrades to red" "and the message states the polarity"
    # Unparseable is the same as absent: no attestation.
    printf 'not json at all\n' >"$WORK/plan-garbage.json"
    assert_eq "$(run_reconcile "$WORK/plan-garbage.json" "$WORK/jobs.json")" "1" \
        "an unparseable plan is as missing"
    # CONTROL: a readable, valid plan passes, so the failure is about the
    # artifact, not the code path.
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json")" "0" \
        "the real plan still reconciles clean"
    log_pass "a missing or unreadable plan hard-fails: the reconciler degrades to red (case 29)"
}

test_run_id_mismatch_is_tamper() {
    # Edge case 30, anti-tamper: the plan must name THIS run, or a stale or
    # substituted artifact could vouch for skips it never planned.
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json" "999999")" "1" \
        "a plan carrying another run's id must hard-fail"
    assert_contains "$(err)" "plan-run-id-mismatch" "as plan-run-id-mismatch"
    mutate "$WORK/plan.json" "$WORK/plan-no-runid.json" 'delete data.run_id'
    assert_eq "$(run_reconcile "$WORK/plan-no-runid.json" "$WORK/jobs.json")" "1" \
        "a plan without a run_id must hard-fail too"
    # CONTROL: the matching id is what passes (every other test's green runs
    # use it, but assert once explicitly).
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json" "$RUN_ID")" "0" \
        "the matching run id reconciles clean"
    log_pass "a run-id mismatch or absence hard-fails, anti-tamper (case 30)"
}

test_naming_trap_uses_explicit_table() {
    # Edge case 31, verified in the tree: ci.yml's `update-flow-test` is a
    # CALLER display-named `Tests + Infra / Update Flow` whose real leaf is
    # `Tests + Infra / Update Flow / Update flow (Linux x64)`, while
    # `package-tests` is a PLAIN job named `Tests + Infra / Linux Packages`,
    # NOT inside ct-tests.yml. The name shape lies in both directions, so the
    # mapping must be an explicit table.
    local names
    names="$(node -e '
const r = require(process.argv[1]);
process.stdout.write(JSON.stringify({
  update_flow: r.EXPECTED_JOB_NAMES.update_flow,
  package_tests: r.EXPECTED_JOB_NAMES.package_tests,
}));
' "$RECONCILE")"
    assert_contains "$names" "Tests + Infra / Update Flow / Update flow" \
        "update_flow maps to the caller LEAF, three name segments deep"
    assert_contains "$names" "Tests + Infra / Linux Packages" \
        "package_tests maps to the top-level plain job"

    # Behavioural: the two `Tests + Infra / ...` names bucket separately.
    mutate "$WORK/jobs.json" "$WORK/jobs-updflow-skipped.json" \
        'data.jobs.find((j) => j.name === "Tests + Infra / Update Flow / Update flow (Linux x64)").conclusion = "skipped"'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-updflow-skipped.json")" "1" \
        "a skipped update-flow leaf fires"
    assert_contains "$(err)" "'update_flow'" "against the update_flow key"
    # CONTROL: the sibling-named plain job fires its OWN key, so keys are not
    # inferred from the shared display prefix.
    mutate "$WORK/jobs.json" "$WORK/jobs-pkg-skipped.json" \
        'data.jobs.find((j) => j.name === "Tests + Infra / Linux Packages").conclusion = "skipped"'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-pkg-skipped.json")" "1" \
        "a skipped Linux Packages job fires"
    assert_contains "$(err)" "'package_tests'" "against package_tests"
    assert_not_contains "$(err)" "'update_flow'" "and never update_flow"
    log_pass "structure comes from the explicit table, not the name shape (case 31)"
}

test_matrix_match_by_prefix_never_sloppy() {
    # Edge case 32: matrix legs match by expected-name + ` (`. That must
    # cover the unexpanded-template form a skipped matrix reports (seen live:
    # `Procwalk (${{ matrix.os }})`), and must NOT let `E2E Ceph` swallow
    # `E2E Ceph Workers`.
    mutate "$WORK/jobs.json" "$WORK/jobs-template-skip.json" \
        'data.jobs.push({ name: "Tests + Infra / E2E Workers (${{ matrix.os-image }})", conclusion: "skipped" })'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-template-skip.json")" "1" \
        "an unexpanded skipped matrix leg still matches its key"
    assert_contains "$(err)" "planned-run-but-skipped: 'e2e_workers'" \
        "as e2e_workers, template form and all"

    # Precision: remove the plain `E2E Ceph` job. `E2E Ceph Workers` is still
    # present and green; if the matcher were bare startsWith it would satisfy
    # e2e_ceph and this would pass instead of failing.
    mutate "$WORK/jobs.json" "$WORK/jobs-no-ceph.json" \
        'data.jobs = data.jobs.filter((j) => j.name !== "Tests + Infra / E2E Ceph")'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-no-ceph.json")" "1" \
        "E2E Ceph Workers must not satisfy the e2e_ceph key"
    assert_contains "$(err)" "planned-job-missing: 'e2e_ceph'" "which reports missing"
    assert_not_contains "$(err)" "planned-job-missing: 'e2e_ceph_workers'" \
        "while e2e_ceph_workers still matches its own job"
    # CONTROL: with both present (base fixture) neither fires.
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json")" "0" \
        "both ceph keys reconcile clean when both jobs exist"
    log_pass "matrix legs match by prefix + ' (', never bare startsWith (case 32)"
}

test_unknown_plan_key_fails_closed() {
    # A plan key the table cannot map cannot be verified: red, not shrug
    # (same polarity as case 29).
    mutate "$WORK/plan.json" "$WORK/plan-bogus-key.json" \
        'data.jobs.totally_new_job = { run: true, reason: "modules:x" }'
    assert_eq "$(run_reconcile "$WORK/plan-bogus-key.json" "$WORK/jobs.json")" "1" \
        "an unmappable plan key must hard-fail"
    assert_contains "$(err)" "unknown-plan-key: 'totally_new_job'" "named as unknown-plan-key"
    # CONTROL: every real key maps (the healthy fixture passes).
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json")" "0" \
        "the real key set reconciles clean"
    log_pass "an unknown plan key fails closed (the reconciler cannot verify it)"
}

test_name_table_parity_with_scope_map() {
    # EXPECTED_JOB_NAMES and scope-map's JOB_SURFACES must cover the same
    # keys; the module throws at load on drift. Prove the validator fires in
    # BOTH directions, then that the real tables pass.
    local verdicts
    verdicts="$(node -e '
const r = require(process.argv[1]);
const m = require(process.argv[2]);
const out = [];
const missing = { ...r.EXPECTED_JOB_NAMES };
delete missing.unit;
try { r.validateNameTable(missing, m.JOB_SURFACES); out.push("missing:no-throw"); }
catch (e) { out.push("missing:" + e.message); }
try { r.validateNameTable({ ...r.EXPECTED_JOB_NAMES, extra_key: ["X"] }, m.JOB_SURFACES); out.push("orphan:no-throw"); }
catch (e) { out.push("orphan:" + e.message); }
try { r.validateNameTable(r.EXPECTED_JOB_NAMES, m.JOB_SURFACES); out.push("real:ok"); }
catch (e) { out.push("real:" + e.message); }
process.stdout.write(out.join("\n"));
' "$RECONCILE" "$MAP")"
    assert_contains "$verdicts" "missing:EXPECTED_JOB_NAMES lacks plan key 'unit'" \
        "a surface key without a name entry throws"
    assert_contains "$verdicts" "orphan:EXPECTED_JOB_NAMES has orphan key 'extra_key'" \
        "a name entry without a surface key throws"
    assert_contains "$verdicts" "real:ok" "and the real tables pass both directions"
    log_pass "the name table and scope-map's surfaces cannot drift apart silently"
}

test_jobs_payload_forms_and_absence() {
    # `gh api .../jobs` returns { jobs: [...] }; a bare array must work too,
    # and unusable payloads must hard-fail (reconciler polarity again).
    node -e '
const fs = require("fs");
const d = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
fs.writeFileSync(process.argv[2], JSON.stringify(d.jobs));
' "$WORK/jobs.json" "$WORK/jobs-bare.json"
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-bare.json")" "0" \
        "a bare-array jobs payload reconciles identically"
    printf 'not json\n' >"$WORK/jobs-garbage.json"
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-garbage.json")" "1" \
        "an unparseable jobs payload must hard-fail"
    assert_contains "$(err)" "jobs-payload-missing" "as jobs-payload-missing"
    printf '{"total_count": 0}\n' >"$WORK/jobs-shapeless.json"
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-shapeless.json")" "1" \
        "a payload without a jobs array must hard-fail"
    log_pass "both payload forms parse; unusable evidence hard-fails"
}

test_warnings_never_mask_failures() {
    # A run can over-run one key and under-run another; the warning must not
    # eat the failure, and the streams must stay separate (FAIL on stderr,
    # ::warning:: on stdout).
    mutate "$WORK/plan.json" "$WORK/plan-mixed.json" \
        'data.jobs.unit = { run: false, reason: "out-of-scope" }'
    mutate "$WORK/jobs.json" "$WORK/jobs-mixed.json" \
        'data.jobs.find((j) => j.name === "Tests + Infra / E2E Ceph").conclusion = "skipped"'
    assert_eq "$(run_reconcile "$WORK/plan-mixed.json" "$WORK/jobs-mixed.json")" "1" \
        "a failure alongside a warning still exits non-zero"
    assert_contains "$(err)" "planned-run-but-skipped: 'e2e_ceph'" "the failure is on stderr"
    assert_contains "$(out)" "::warning::planned-skip-but-ran: 'unit'" "the warning is on stdout"
    log_pass "warnings never mask failures, and the streams stay separate"
}

test_usage_errors_are_loud() {
    # Forgetting a flag is a wiring bug and must be non-zero, not a default.
    local rc=0
    node "$RECONCILE" --plan "$WORK/plan.json" --jobs "$WORK/jobs.json" \
        >/dev/null 2>"$WORK/err.txt" || rc=$?
    assert_eq "$rc" "2" "a missing --run-id is a usage error, exit 2"
    assert_contains "$(err)" "--run-id" "naming the missing flag"
    log_pass "missing wiring flags exit non-zero"
}

log_test "test-skip-plan-reconcile"
test_mandatory_invisible_cell_hard_fails
test_healthy_eleven_must_not_fire
test_planned_job_missing_hard_fails
test_over_running_warns_only
test_missing_plan_hard_fails_polarity_inverted
test_run_id_mismatch_is_tamper
test_naming_trap_uses_explicit_table
test_matrix_match_by_prefix_never_sloppy
test_unknown_plan_key_fails_closed
test_name_table_parity_with_scope_map
test_jobs_payload_forms_and_absence
test_warnings_never_mask_failures
test_usage_errors_are_loud
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
