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
# PRE-EXISTING SKIPS ARE THE SECOND HALF. ci.yml skipped whole columns long
# before the scope engine existed: `full_suite` is false on every push-to-main,
# `pointer_bump_only` cuts the entire expensive pipeline on a submodule-pointer
# PR, `is_bot` cuts the staging chain. Against an unannotated plan a pointer
# bump reports SEVENTEEN failures on a run where nothing went wrong, which is
# why the gate could not be wired. The cases below pin the exemption AND its
# edges: full_suite must never excuse `install_methods` (which really does run
# on push-to-main), is_bot must excuse nothing but it, and the strict module
# default must still refuse such a run as a baseline. Each is a pair: a fixture
# where the new logic must FIRE and a twin where it must stay SILENT.
#
# Every failure case is paired with the passing control so nothing passes
# vacuously, and the fixture's shape (the eleven skips actually being there)
# is itself asserted, per the house doctrine: a validator that passes when
# given nothing is broken by definition.
#
# The five mutants run by hand during authoring, each caught by a DIFFERENT
# assertion: force honorPreexisting true (strict-default case), make
# preexistingSkip return null (pointer-bump case), add install_methods to
# full_suite's keys (the full_suite/install_methods pair), delete the
# claim-mismatch check (the anti-tamper case), and compare conditions as
# strings instead of booleans (the real-boolean case).

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
# asserted separately). The jobs payload is run 30307775327: a success leaf for
# every planned key, the eleven structural skips observed live, and unplanned
# extras the reconciler must ignore.
#
# It is that run PLUS any leg added since, which is a real obligation rather
# than a footnote: because the plan is generated from JOB_SURFACES, adding a
# key there without adding its leaf here makes the healthy fixture fail as
# planned-run-but-missing. That is the gate working (a planned job with no
# observed leaf IS a defect in a real run), so the fix is always to add the
# leaf, never to loosen the check. `License Enforcement` is the first such
# addition.
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
  S("Tests + Infra / License Enforcement"),
  S("Tests + Infra / Account E2E"),
  S("Tests + Infra / Drills"),
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

# annotate <in-plan> <out-plan> <conditions-json> -- run a plan through the REAL
# annotatePlan, the same entry point .ci/scripts/ci/scope-shadow.sh calls. Going
# through the production function rather than hand-writing the annotation is
# what makes these cases test the shipped writer instead of a paraphrase of it.
annotate() {
    node -e '
const fs = require("fs");
const { annotatePlan } = require(process.argv[1]);
const plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
annotatePlan(plan, JSON.parse(process.argv[4]));
fs.writeFileSync(process.argv[3], JSON.stringify(plan, null, 2));
' "$RECONCILE" "$1" "$2" "$3"
}

# reconcile_module <plan> <jobs> <honorPreexisting:true|false> -> "<ok>|<first
# failure>". The CLI always honors, so the strict default is only reachable
# through the module API, which is exactly how scope-engine's attestPlan calls
# it. Without this helper the default could never be tested.
reconcile_module() {
    node -e '
const fs = require("fs");
const r = require(process.argv[1]);
const plan = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const jobs = r.parseJobsPayload(JSON.parse(fs.readFileSync(process.argv[3], "utf8")));
const ctx = { runId: process.argv[5] };
if (process.argv[4] === "true") ctx.honorPreexisting = true;
const res = r.reconcile(plan, jobs, ctx);
process.stdout.write(`${res.ok}|${res.failures[0] || ""}|exempt=${res.exempt.length}`);
' "$RECONCILE" "$1" "$2" "$3" "$RUN_ID"
}

# skipped_count <jobs> -- fixture SHAPE, asserted before any silence is trusted.
skipped_count() {
    node -e '
const d = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
const jobs = Array.isArray(d) ? d : d.jobs;
process.stdout.write(String(jobs.filter((j) => j.conclusion === "skipped").length));
' "$1"
}

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

test_flat_job_never_blames_a_lookalike_caller() {
    # Edge case 33: caller-derivation must not fire for a FLAT job whose
    # display name merely shares a prefix with a reusable caller.
    #
    # `package-tests` is a plain top-level job named "Tests + Infra / Linux
    # Packages" (ci.yml:572-573, needs: [initialize, quality]). The `tests`
    # reusable caller's own display name is exactly "Tests + Infra"
    # (ci.yml:673-674). Splitting the expected name on ' / ' regardless would
    # derive 'Tests + Infra' and then blame that unrelated job, converting a
    # real case-27 rename or DAG break into a bogus case-25 caller-skip.
    #
    # This also exercises the `matched.length === 0` branch with a skipped
    # lookalike present, which nothing did before: the other cases only ever
    # mutate an existing job's conclusion.
    mutate "$WORK/jobs.json" "$WORK/jobs-flat-trap.json" \
        'data.jobs = data.jobs.filter((j) => j.name !== "Tests + Infra / Linux Packages");
         data.jobs.push({ name: "Tests + Infra", conclusion: "skipped" })'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-flat-trap.json")" "1" \
        "a flat job missing from the payload still hard-fails"
    assert_contains "$(err)" "planned-job-missing: 'package_tests'" \
        "reported as the rename/DAG break it actually is"
    assert_not_contains "$(err)" "planned-run-but-skipped: 'package_tests'" \
        "never misattributed to the lookalike 'Tests + Infra' caller"

    # CONTROL, and without it this test would pass just as well if caller
    # derivation were deleted outright. A GENUINE reusable leaf must still
    # produce the caller-skip diagnosis under the same shape of mutation.
    mutate "$WORK/jobs.json" "$WORK/jobs-ops-caller-skipped.json" \
        'data.jobs = data.jobs.filter((j) => !j.name.startsWith("OPS Tests / "));
         data.jobs.push({ name: "OPS Tests", conclusion: "skipped" })'
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-ops-caller-skipped.json")" "1" \
        "a genuinely skipped reusable caller still hard-fails"
    assert_contains "$(err)" "planned-run-but-skipped: 'ops' -> reusable caller 'OPS Tests'" \
        "and is still diagnosed as a caller skip, not a missing job"
    assert_not_contains "$(err)" "planned-job-missing: 'ops'" \
        "so the caller-derivation path is alive, not merely disabled"

    # CONTROL: the untouched fixture stays clean.
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs.json")" "0" \
        "the healthy fixture reconciles clean throughout"
    log_pass "flat lookalikes never borrow a caller's skip (case 33)"
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

test_pointer_bump_exempts_every_key() {
    # THE case this whole extension exists for. On a pointer-bump PR
    # `build-renet` skips (ci.yml:493) and the entire expensive pipeline goes
    # with it, so all eighteen planned keys skip while nothing is wrong. The
    # plan predicted `run: true` for every one of them, so an unannotated plan
    # reports eighteen failures on a perfectly healthy run.
    mutate "$WORK/jobs.json" "$WORK/jobs-pointer-bump.json" \
        'data.jobs.forEach((j) => { j.conclusion = "skipped"; })'
    # SHAPE first: the silence below is only meaningful if the skips are real.
    local total skips
    total="$(node -e 'const d=JSON.parse(require("fs").readFileSync(process.argv[1],"utf8"));process.stdout.write(String(d.jobs.length))' "$WORK/jobs-pointer-bump.json")"
    skips="$(skipped_count "$WORK/jobs-pointer-bump.json")"
    assert_eq "$skips" "$total" "the pointer-bump fixture skips every job it carries"

    # FIRE: the plan as it was written before this change (no conditions).
    assert_eq "$(run_reconcile "$WORK/plan.json" "$WORK/jobs-pointer-bump.json")" "1" \
        "an unannotated plan reds a pointer-bump run: the false-fire this fixes"
    assert_contains "$(err)" "planned-run-but-skipped: 'unit'" "blaming scope for a non-scope skip"
    assert_contains "$(err)" "planned-run-but-skipped: 'install_methods'" \
        "including install_methods, which pointer_bump_only really does cut"

    # SILENT: the same jobs against a plan that records the condition.
    annotate "$WORK/plan.json" "$WORK/plan-pointer-bump.json" \
        '{"pointer_bump_only":true,"full_suite":true,"is_bot":false}'
    assert_eq "$(run_reconcile "$WORK/plan-pointer-bump.json" "$WORK/jobs-pointer-bump.json")" "0" \
        "recording pointer_bump_only makes the identical run reconcile clean"
    assert_not_contains "$(err)" "planned-run-but-skipped" "with no failure at all"
    assert_contains "$(out)" "pre-existing skips (not scope decisions, not verified by this run)" \
        "and the excused keys are printed, so a vacuous pass is visible"
    assert_contains "$(out)" "unit (pointer_bump_only)" "naming the key and the condition"
    assert_contains "$(out)" "0 of 18 planned keys verified" \
        "and the headline counts VERIFIED keys, not planned ones: this pass proves nothing"
    log_pass "pointer_bump_only exempts all 18 keys; the same run reds without the annotation"
}

test_full_suite_exempts_seventeen_but_never_install_methods() {
    # The condition sets are NOT interchangeable, and this is the pair that
    # proves it. `validate-install` (ci.yml:1081-1083) hangs off
    # `stage-artifacts`, which carries no full_suite clause (ci.yml:658), so the
    # install matrix genuinely DOES run on push-to-main. Exempting it under
    # full_suite would excuse a real skip for ever.
    annotate "$WORK/plan.json" "$WORK/plan-push.json" \
        '{"pointer_bump_only":false,"full_suite":false,"is_bot":false}'

    # SILENT: the push-to-main shape. Everything full_suite gates skipped, the
    # install matrix still green.
    mutate "$WORK/jobs.json" "$WORK/jobs-push.json" \
        'data.jobs.forEach((j) => {
           if (!j.name.startsWith("Validate Install Methods")) j.conclusion = "skipped";
         })'
    assert_eq "$(skipped_count "$WORK/jobs-push.json")" "33" \
        "the push fixture skips all 33 non-install jobs and leaves the four install legs"
    assert_eq "$(run_reconcile "$WORK/plan-push.json" "$WORK/jobs-push.json")" "0" \
        "a push-to-main shape reconciles clean once full_suite is recorded"
    assert_contains "$(out)" "unit (full_suite)" "excusing unit under full_suite"
    assert_not_contains "$(out)" "install_methods (full_suite)" \
        "and never excusing install_methods, which full_suite does not gate"

    # FIRE, the paired twin: the ONE key full_suite must not cover goes missing
    # and the same annotated plan must still red.
    mutate "$WORK/jobs-push.json" "$WORK/jobs-push-install-skipped.json" \
        'data.jobs.filter((j) => j.name.startsWith("Validate Install Methods"))
           .forEach((j) => { j.conclusion = "skipped"; })'
    assert_eq "$(run_reconcile "$WORK/plan-push.json" "$WORK/jobs-push-install-skipped.json")" "1" \
        "a skipped install matrix on push-to-main is a REAL finding and must fire"
    assert_contains "$(err)" "planned-run-but-skipped: 'install_methods'" "naming install_methods"
    assert_not_contains "$(err)" "planned-run-but-skipped: 'unit'" \
        "while the seventeen full_suite really gates stay excused"

    # And pointer_bump_only DOES cover it, on the identical payload. Two
    # conditions, two different key sets, same jobs: the table discriminates
    # rather than handing out one blanket exemption.
    annotate "$WORK/plan.json" "$WORK/plan-pb2.json" \
        '{"pointer_bump_only":true,"full_suite":true,"is_bot":false}'
    assert_eq "$(run_reconcile "$WORK/plan-pb2.json" "$WORK/jobs-push-install-skipped.json")" "0" \
        "the same skipped install matrix is excused under pointer_bump_only"
    log_pass "full_suite exempts 17 keys and never install_methods; pointer_bump_only exempts all 18"
}

test_is_bot_exempts_exactly_one_key() {
    # is_bot (ci.yml:105) reaches only install_methods, via stage-artifacts
    # (ci.yml:658). It needs no entry for the other seventeen because it can only
    # be true on a `push`, where full_suite already covers them. A narrow
    # exemption must stay narrow, so plant a skip OUTSIDE it.
    annotate "$WORK/plan.json" "$WORK/plan-bot.json" \
        '{"pointer_bump_only":false,"full_suite":true,"is_bot":true}'

    # SILENT half: only the install matrix skipped.
    mutate "$WORK/jobs.json" "$WORK/jobs-bot.json" \
        'data.jobs.filter((j) => j.name.startsWith("Validate Install Methods"))
           .forEach((j) => { j.conclusion = "skipped"; })'
    assert_eq "$(run_reconcile "$WORK/plan-bot.json" "$WORK/jobs-bot.json")" "0" \
        "is_bot excuses the install matrix"
    assert_contains "$(out)" "install_methods (is_bot)" "naming is_bot as the reason"

    # FIRE half: one more key skips, and is_bot must not stretch to cover it.
    mutate "$WORK/jobs-bot.json" "$WORK/jobs-bot-plus-unit.json" \
        'data.jobs.find((j) => j.name === "Tests + Infra / Unit").conclusion = "skipped"'
    assert_eq "$(run_reconcile "$WORK/plan-bot.json" "$WORK/jobs-bot-plus-unit.json")" "1" \
        "a skipped unit leg is still a hard failure under is_bot"
    assert_contains "$(err)" "planned-run-but-skipped: 'unit'" "naming unit"
    assert_not_contains "$(err)" "'install_methods'" "while install_methods stays excused"
    log_pass "is_bot exempts install_methods alone; every other key still fires"
}

test_exemption_needs_a_real_boolean() {
    # Missing information must never WIDEN an exemption, so the condition test
    # is a strict boolean compare. A plan whose conditions came through as
    # strings (a shell variable passed unparsed) gets nothing.
    mutate "$WORK/plan.json" "$WORK/plan-stringy.json" \
        'data.conditions = { pointer_bump_only: "true", full_suite: "false", is_bot: "false" }'
    assert_eq "$(run_reconcile "$WORK/plan-stringy.json" "$WORK/jobs-pointer-bump.json")" "1" \
        "string 'true' is not true: no exemption, and the run reds"
    assert_contains "$(err)" "planned-run-but-skipped: 'unit'" "exactly as if nothing were recorded"

    # And an omitted condition is likewise inactive, which is what the writer
    # produces when the environment variable is unset.
    annotate "$WORK/plan.json" "$WORK/plan-omitted.json" '{}'
    assert_eq "$(run_reconcile "$WORK/plan-omitted.json" "$WORK/jobs-pointer-bump.json")" "1" \
        "an omitted condition grants nothing either"

    # CONTROL: the real booleans, same fixture, silent. Without this the two
    # assertions above would pass just as well if exemptions were dead code.
    assert_eq "$(run_reconcile "$WORK/plan-pointer-bump.json" "$WORK/jobs-pointer-bump.json")" "0" \
        "and real booleans on the identical payload reconcile clean"
    log_pass "only a real boolean activates a condition; strings and omissions grant nothing"
}

test_annotation_must_agree_with_the_conditions() {
    # Anti-tamper. The exemption is DERIVED from plan.conditions; the per-job
    # field is only ever cross-checked. A hand-edited artifact claiming an
    # exemption its own conditions do not support must not buy a free pass on
    # the one check that can see an invisible cell.
    mutate "$WORK/plan.json" "$WORK/plan-forged.json" \
        'data.conditions = { pointer_bump_only: false, full_suite: true, is_bot: false };
         data.jobs.unit.preexisting_skip = "pointer_bump_only"'
    assert_eq "$(run_reconcile "$WORK/plan-forged.json" "$WORK/jobs-unit-skipped.json")" "1" \
        "a forged per-job exemption must hard-fail"
    assert_contains "$(err)" "preexisting-claim-mismatch: 'unit' claims 'pointer_bump_only'" \
        "named as a claim mismatch, not silently ignored"

    # Drift in the other direction: conditions say the key is exempt, the
    # annotation is missing. That is a stale writer, and it must be as loud.
    mutate "$WORK/plan-pointer-bump.json" "$WORK/plan-dropped-annot.json" \
        'delete data.jobs.unit.preexisting_skip'
    assert_eq "$(run_reconcile "$WORK/plan-dropped-annot.json" "$WORK/jobs-pointer-bump.json")" "1" \
        "a dropped annotation the conditions imply must hard-fail too"
    assert_contains "$(err)" "the plan's conditions yield 'pointer_bump_only'" \
        "stating what the conditions actually imply"

    # A condition name that does not exist cannot be smuggled in either.
    mutate "$WORK/plan.json" "$WORK/plan-invented.json" \
        'data.conditions = {}; data.jobs.e2e_ceph.preexisting_skip = "the_weather"'
    assert_eq "$(run_reconcile "$WORK/plan-invented.json" "$WORK/jobs-ceph-skipped.json")" "1" \
        "an invented condition name must hard-fail"
    assert_contains "$(err)" "preexisting-claim-mismatch: 'e2e_ceph' claims 'the_weather'" \
        "naming the invention"

    # CONTROL: a plan annotated by the real writer agrees with itself.
    assert_eq "$(run_reconcile "$WORK/plan-pointer-bump.json" "$WORK/jobs-pointer-bump.json")" "0" \
        "an annotatePlan-written plan reconciles clean"
    log_pass "the per-job annotation is cross-checked against the conditions, both directions"
}

test_strict_mode_is_the_module_default() {
    # The two consumers want opposite things. The GATE must not red a
    # pointer-bump run; the BASELINE READER (scope-engine's attestPlan, which
    # calls reconcile() over a plan downloaded from an earlier run) must not
    # accept that run as proof, because it validated nothing. Same plan, same
    # jobs, opposite verdict, decided by the flag alone.
    local strict lenient
    strict="$(reconcile_module "$WORK/plan-pointer-bump.json" "$WORK/jobs-pointer-bump.json" "false")"
    lenient="$(reconcile_module "$WORK/plan-pointer-bump.json" "$WORK/jobs-pointer-bump.json" "true")"
    assert_contains "$strict" "false|planned-run-but-skipped" \
        "the module default refuses a pointer-bump run as a baseline"
    assert_contains "$strict" "pre-existing condition pointer_bump_only was active" \
        "and says WHY, since attestPlan only ever surfaces the first failure string"
    assert_contains "$strict" "this run is not proof that it ran" "in those words"
    assert_contains "$lenient" "true|" "while the gate, which opts in, passes the same input"
    assert_contains "$lenient" "exempt=18" "having excused all eighteen keys"

    # CONTROL: the flag is not a blanket mute. On the healthy fixture, where no
    # condition is active, both modes agree and both pass.
    local strict_healthy lenient_healthy
    strict_healthy="$(reconcile_module "$WORK/plan.json" "$WORK/jobs.json" "false")"
    lenient_healthy="$(reconcile_module "$WORK/plan.json" "$WORK/jobs.json" "true")"
    assert_contains "$strict_healthy" "true||exempt=0" "no conditions, strict mode passes"
    assert_contains "$lenient_healthy" "true||exempt=0" "and lenient mode passes identically"
    log_pass "honorPreexisting defaults to false, so a baseline reader still refuses an unproven run"
}

test_exempt_key_that_ran_warns_only() {
    # An exemption handed out where the job ran anyway means the condition
    # table over-claims. Worth saying, never worth blocking: there is no
    # failure to mask when a planned-run job actually ran.
    assert_eq "$(run_reconcile "$WORK/plan-pointer-bump.json" "$WORK/jobs.json")" "0" \
        "a fully-exempt plan against a fully-green run must not fail"
    assert_contains "$(out)" "::warning::preexisting-exempt-but-ran: 'unit'" \
        "but the over-broad exemption is warned about, on stdout"
    assert_contains "$(out)" "the condition table may be over-broad" "with the diagnosis"
    assert_not_contains "$(err)" "FAIL" "and nothing lands on stderr"

    # CONTROL: the warning is earned. When the exempt keys really skipped,
    # silence.
    assert_eq "$(run_reconcile "$WORK/plan-pointer-bump.json" "$WORK/jobs-pointer-bump.json")" "0" \
        "the same plan against the skipped run is clean"
    assert_not_contains "$(out)" "::warning::" "with no warning at all"
    log_pass "an exemption that was not needed warns; one that was is silent"
}

test_exemptions_never_mask_a_failure() {
    # The house invariant, restated for the new path: warnings never mask
    # failures, and neither do exemptions. Mix all three in one run.
    mutate "$WORK/plan-push.json" "$WORK/plan-push-mixed.json" \
        'data.jobs.package_tests = { run: false, reason: "out-of-scope",
                                     preexisting_skip: data.jobs.package_tests.preexisting_skip }'
    mutate "$WORK/jobs-push.json" "$WORK/jobs-push-mixed.json" \
        'data.jobs.find((j) => j.name === "Tests + Infra / Linux Packages").conclusion = "success";
         data.jobs.filter((j) => j.name.startsWith("Validate Install Methods"))
           .forEach((j) => { j.conclusion = "skipped"; })'
    assert_eq "$(run_reconcile "$WORK/plan-push-mixed.json" "$WORK/jobs-push-mixed.json")" "1" \
        "an exemption alongside a warning still exits non-zero on a real failure"
    assert_contains "$(err)" "planned-run-but-skipped: 'install_methods'" "the failure is on stderr"
    assert_contains "$(out)" "::warning::planned-skip-but-ran: 'package_tests'" \
        "the warning is on stdout"
    assert_contains "$(out)" "unit (full_suite)" "and the exempt list is still printed on failure"
    log_pass "exemptions and warnings both fail to mask a real failure"
}

test_condition_table_cannot_rot_silently() {
    # Same discipline as the name-table parity check: an entry naming a key
    # that no longer exists is an exemption that can never apply, and a
    # condition missing from CONDITION_ORDER would be evaluated by nothing.
    # Both are silent, both are rot. Prove the validator fires in every
    # direction, then that the real tables pass.
    local verdicts
    verdicts="$(node -e '
const r = require(process.argv[1]);
const out = [];
const T = () => JSON.parse(JSON.stringify(r.PREEXISTING_CONDITIONS));
const run = (label, conds, order) => {
  try { r.validateConditionTable(conds, order, r.EXPECTED_JOB_NAMES); out.push(label + ":no-throw"); }
  catch (e) { out.push(label + ":" + e.message); }
};
const badKey = T(); badKey.full_suite.keys.push("no_such_job");
run("badkey", badKey, r.CONDITION_ORDER);
run("unordered", T(), r.CONDITION_ORDER.filter((c) => c !== "is_bot"));
const orphan = T(); delete orphan.is_bot;
run("orphan", orphan, r.CONDITION_ORDER);
const bad = T(); bad.is_bot.activeWhen = "true";
run("nonbool", bad, r.CONDITION_ORDER);
run("real", r.PREEXISTING_CONDITIONS, r.CONDITION_ORDER);
process.stdout.write(out.join("\n"));
' "$RECONCILE")"
    assert_contains "$verdicts" "badkey:PREEXISTING_CONDITIONS.full_suite names unknown plan key 'no_such_job'" \
        "a condition naming a dead plan key throws"
    assert_contains "$verdicts" "unordered:CONDITION_ORDER omits 'is_bot'" \
        "a condition absent from the evaluation order throws"
    assert_contains "$verdicts" "orphan:CONDITION_ORDER has orphan condition 'is_bot'" \
        "an order entry with no condition behind it throws"
    assert_contains "$verdicts" "nonbool:PREEXISTING_CONDITIONS.is_bot has a non-boolean activeWhen" \
        "a non-boolean activeWhen throws, since the compare is strict"
    assert_contains "$verdicts" "real:no-throw" "and the real tables pass"

    # Behavioural counterpart to the table: the key sets are the ones the
    # workflow evidence supports, asserted by size so a silent widening shows.
    local sizes
    sizes="$(node -e '
const r = require(process.argv[1]);
const n = (c) => r.PREEXISTING_CONDITIONS[c].keys.length;
process.stdout.write(`pb=${n("pointer_bump_only")} fs=${n("full_suite")} bot=${n("is_bot")}`);
' "$RECONCILE")"
    assert_eq "$sizes" "pb=18 fs=17 bot=1" \
        "pointer_bump_only cuts all 18, full_suite 17 (not install_methods), is_bot 1"
    log_pass "the condition table cannot rot or widen silently"
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
test_flat_job_never_blames_a_lookalike_caller
test_unknown_plan_key_fails_closed
test_name_table_parity_with_scope_map
test_jobs_payload_forms_and_absence
test_warnings_never_mask_failures
test_pointer_bump_exempts_every_key
test_full_suite_exempts_seventeen_but_never_install_methods
test_is_bot_exempts_exactly_one_key
test_exemption_needs_a_real_boolean
test_annotation_must_agree_with_the_conditions
test_strict_mode_is_the_module_default
test_exempt_key_that_ran_warns_only
test_exemptions_never_mask_a_failure
test_condition_table_cannot_rot_silently
test_usage_errors_are_loud
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
