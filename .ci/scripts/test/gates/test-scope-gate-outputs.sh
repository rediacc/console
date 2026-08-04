#!/bin/bash
# The scope gate's OUTPUT CONTRACT, driven end to end through the real
# .ci/scripts/ci/scope-shadow.sh.
#
# WHAT THIS GUARDS. Since 2026-07-31 that script no longer observes, it
# DECIDES: ci.yml reads its `run_<key>=false` outputs and skips jobs on them.
# The safety property is entirely in the encoding, and it is one sentence: a
# false line is the ONLY thing that can shrink a run, so every failure path
# must emit zero of them. That property is invisible to code reading, because
# every one of its failure paths is an error path -- an engine that crashed, a
# plan that could not be written, an operator override -- and error paths are
# exactly what unit tests over pure functions never reach. So this drives the
# actual script, with a PATH-shimmed `gh` and a real git repository, and reads
# the bytes it appends to $GITHUB_OUTPUT.
#
# THE FIXTURE IS A WHOLE REPO, and it has to be. scope-engine.cjs resolves its
# repo root from its own __dirname (`path.resolve(__dirname, '../../..')`), so
# pointing the engine somewhere safe means copying .ci/scripts/ci into a
# fixture tree and running the copy: git history, branch shape and merge
# parents then all belong to the test. A symlink would NOT work, because node
# resolves a symlinked module to its real path and __dirname would land back on
# this repository.
#
# EVERY CASE CARRIES ITS CONTROL. An emitter that writes nothing at all passes
# cases (b), (c) and (d) trivially, so case (a) pins the exact set of false
# lines a reduced plan must produce, and cases (b) and (d) re-run the SAME
# fixture with the defect removed and require the lines to come back.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# THE WORKFLOW CONTRACT, spelled out as literals on purpose.
#
# ci.yml's `initialize` job declares one output per name below and reads them
# out of $GITHUB_OUTPUT. An output emitted under a name that is not on this list
# is SILENTLY DROPPED by the outputs block: no error, no warning, and the job it
# was meant to skip simply runs. So a rename on either side is invisible at
# runtime and shows up only as "the scope engine stopped saving any time",
# which nobody notices for weeks.
#
# Deriving this list from scope-map would defeat the point. It is a second,
# independent copy of the spelling, and the test below asserts the two agree.
WORKFLOW_CONTRACT_KEYS=(
    run_unit
    run_e2e_workers
    run_e2e_ceph
    run_e2e_ceph_workers
    run_e2e_k8s
    run_e2e_k8s_ceph
    run_e2e_k8s_multinode
    run_e2e_migrate
    run_fork_isolation
    run_renet
    run_license_enforcement
    run_account_e2e
    run_drills
    run_ops
    run_elite_run
    run_update_flow
    run_package_tests
    run_install_methods
)

FIX="$WORK/repo"
CI_DIR="$FIX/.ci/scripts/ci"
BASELINE_RUN_ID=1111
CURRENT_RUN_ID=999

# ---------------------------------------------------------------------------
# Fixture: a repository whose branch shape makes a REDUCED round the correct
# answer, plus the three `gh` responses the baseline walk needs.
#
#   main:  B ------------------- M
#   pr:     \-- C1 --- C2 ------/
#
# The engine walks first-parent from head (C2) fenced at M^1 (B), so C1 is the
# only candidate. C1's run is green and carries an attested FULL plan, which
# makes it a usable baseline, and the NET delta C1..C2 touches docs plus
# packages/www only. Of the 18 job surfaces exactly one (`unit`) consumes www,
# so the correct plan runs `unit` and skips the other seventeen. That asymmetry
# is the point: an emitter that skips everything, or nothing, fails.
# ---------------------------------------------------------------------------
build_fixture() {
    mkdir -p "$FIX/.ci/scripts"
    cp -r "$REPO_ROOT/.ci/scripts/ci" "$CI_DIR"

    git -C "$FIX" init -q -b main
    git -C "$FIX" config user.email "scope-gate-test@example.invalid"
    git -C "$FIX" config user.name "Scope Gate Test"

    mkdir -p "$FIX/docs" "$FIX/packages/www/src"
    printf 'base\n' >"$FIX/docs/a.md"
    git -C "$FIX" add docs
    git -C "$FIX" commit -q -m "base"
    BASE_SHA="$(git -C "$FIX" rev-parse HEAD)"

    git -C "$FIX" checkout -q -b pr
    printf 'c1\n' >>"$FIX/docs/a.md"
    git -C "$FIX" add docs
    git -C "$FIX" commit -q -m "c1"
    C1_SHA="$(git -C "$FIX" rev-parse HEAD)"

    printf 'c2\n' >"$FIX/docs/b.md"
    printf '<p>c2</p>\n' >"$FIX/packages/www/src/index.astro"
    git -C "$FIX" add docs packages
    git -C "$FIX" commit -q -m "c2"
    C2_SHA="$(git -C "$FIX" rev-parse HEAD)"

    git -C "$FIX" checkout -q main
    git -C "$FIX" merge -q --no-ff -m "merge pr" pr
    MERGE_SHA_FIX="$(git -C "$FIX" rev-parse HEAD)"

    # The baseline plan C1's run attested. Built THROUGH the real buildPlan so
    # its 18 keys cannot drift from scope-map's; a hand-written key list here
    # would silently stop being a full plan the day a surface is added, and the
    # test would then pass for the wrong reason.
    node -e '
const { buildPlan } = require(process.argv[1]);
const plan = buildPlan({ modules: new Set(), reasons: [], mode: "full", full_reasons: ["seed"] });
plan.run_id = Number(process.argv[2]);
plan.base_sha = process.argv[3];
plan.head_sha = process.argv[4];
plan.conditions = {};
require("fs").writeFileSync(process.argv[5], JSON.stringify(plan, null, 2));
' "$CI_DIR/scope-map.cjs" "$BASELINE_RUN_ID" "$BASE_SHA" "$C1_SHA" "$WORK/baseline-plan.json"

    # The per-job outcomes attestPlan reconciles that plan against, generated
    # from the reconciler's OWN name table for the same anti-drift reason. Every
    # job succeeded, so the strict reconcile the baseline reader performs passes
    # and C1 becomes usable.
    node -e '
const { EXPECTED_JOB_NAMES } = require(process.argv[1]);
const jobs = Object.values(EXPECTED_JOB_NAMES)
  .flat()
  .map((name) => ({ name, conclusion: "success" }));
require("fs").writeFileSync(
  process.argv[2],
  JSON.stringify({ total_count: jobs.length, jobs }, null, 2),
);
' "$CI_DIR/skip-plan-reconcile.cjs" "$WORK/jobs.json"

    printf '{"workflow_runs":[{"id":%s,"name":"Console CI","head_sha":"%s","status":"completed","conclusion":"success"}]}\n' \
        "$BASELINE_RUN_ID" "$C1_SHA" >"$WORK/runs.json"

    # The gh shim. SCOPE_GH_FAIL=1 turns every call into a failure, which is how
    # case (b) breaks the engine without touching its source.
    mkdir -p "$WORK/bin"
    cat >"$WORK/bin/gh" <<SHIM
#!/bin/bash
set -uo pipefail
if [[ "\${SCOPE_GH_FAIL:-}" == "1" ]]; then
    echo "gh: simulated API failure" >&2
    exit 1
fi
if [[ "\${1:-}" == "run" && "\${2:-}" == "download" ]]; then
    dir=""
    while (( \$# > 0 )); do
        [[ "\$1" == "-D" ]] && dir="\${2:-}"
        shift
    done
    [[ -n "\$dir" ]] || exit 1
    mkdir -p "\$dir"
    cp "$WORK/baseline-plan.json" "\$dir/plan.json"
    exit 0
fi
if [[ "\${1:-}" == "api" ]]; then
    case "\${2:-}" in
        */jobs\?*) cat "$WORK/jobs.json"; exit 0 ;;
        *actions/runs\?head_branch*) cat "$WORK/runs.json"; exit 0 ;;
    esac
fi
echo "gh shim: unhandled invocation: \$*" >&2
exit 1
SHIM
    chmod +x "$WORK/bin/gh"

    # The seventeen keys a correct reduced plan must mark false, derived from the
    # real surface table rather than listed by hand.
    EXPECTED_FALSE="$(node -e '
const { JOB_SURFACES } = require(process.argv[1]);
process.stdout.write(
  Object.keys(JOB_SURFACES)
    .filter((k) => !JOB_SURFACES[k].includes("www"))
    .sort()
    .map((k) => `run_${k}=false`)
    .join("\n"),
);
' "$CI_DIR/scope-map.cjs")"
}

# run_gate <case-name> [env-args...] -- drive the real script, return its rc.
# Sets OUTFILE / OUTDIR for the caller to inspect.
run_gate() {
    local name="$1"
    shift
    OUTDIR="$WORK/out-$name"
    OUTFILE="$OUTDIR/github-output"
    mkdir -p "$OUTDIR"
    : >"$OUTFILE"
    local rc=0
    (
        cd "$FIX"
        PATH="$WORK/bin:$PATH" \
            SCOPE_SHADOW_OUT="$OUTDIR" \
            OUTPUT_FILE="$OUTFILE" \
            MERGE_SHA="$MERGE_SHA_FIX" \
            HEAD_SHA="$C2_SHA" \
            GITHUB_REPOSITORY="rediacc/console" \
            GITHUB_RUN_ID="$CURRENT_RUN_ID" \
            GITHUB_HEAD_REF="pr" \
            GITHUB_STEP_SUMMARY="$OUTDIR/summary.md" \
            env "$@" bash "$CI_DIR/scope-shadow.sh"
    ) >"$OUTDIR/gate.log" 2>&1 || rc=$?
    return "$rc"
}

# count_false <output-file>
count_false() {
    grep -c '^run_[a-z0-9_]*=false$' "$1" 2>/dev/null || true
}

# ---------------------------------------------------------------------------

test_reduced_plan_emits_exactly_the_out_of_scope_keys() {
    local rc=0
    run_gate reduced || rc=$?
    assert_exit_code 0 "$rc" "the gate must always exit 0"

    # CONTROL, and it runs BEFORE anything reads the lines. An emitter that
    # writes nothing would satisfy every other case in this file, so if a reduced
    # plan produces no false line at all, nothing below is evidence of anything.
    #
    # The ordering is not cosmetic. Collecting the lines first meant
    # `actual="$(grep ... | sort)"` returned 1 under `set -e` and the whole test
    # exited THERE, with an empty log: the planted-defect run failed for the
    # right reason and said nothing about why, which is a dead instrument even
    # though its exit code was right. Measured, on the defect described below.
    local n
    n="$(count_false "$OUTFILE")"
    if [[ "$n" -eq 0 ]]; then
        cat "$OUTDIR/gate.log" >&2
        log_fail "a reduced plan emitted ZERO run_*=false lines -- the emitter is dead, and every other case here would still pass"
    fi

    local actual
    actual="$(grep '^run_[a-z0-9_]*=false$' "$OUTFILE" | sort || true)"
    assert_eq "$actual" "$EXPECTED_FALSE" \
        "a reduced plan must mark exactly the out-of-scope keys false"
    assert_not_contains "$(cat "$OUTFILE")" "run_unit=false" \
        "the one key whose surface the delta touches must NOT be marked false"
    assert_not_contains "$(cat "$OUTFILE")" "=true" \
        "the gate must never write a run_<key>=true line"
    assert_eq "$(grep -c '^scope_mode=' "$OUTFILE")" "1" "exactly one scope_mode line"
    assert_contains "$(cat "$OUTFILE")" "scope_mode=reduced" "and it must say reduced"
    log_pass "a reduced plan emits false for exactly the $n out-of-scope keys, and scope_mode=reduced"
}

test_emitted_names_match_the_workflow_contract() {
    # The emitter can only ever produce `run_<key>` for a key in scope-map's
    # JOB_SURFACES, so comparing that table to the literal list above is the
    # whole contract: same 18 names, same spelling. A key added to scope-map
    # without a matching ci.yml output would be emitted and dropped on the
    # floor; a key renamed in ci.yml without scope-map would be read as empty
    # forever, which reads as "run it" and is safe but silently free of any
    # saving at all.
    local from_map expected
    from_map="$(node -e '
const { JOB_SURFACES } = require(process.argv[1]);
process.stdout.write(Object.keys(JOB_SURFACES).map((k) => `run_${k}`).join("\n"));
' "$CI_DIR/scope-map.cjs")"
    expected="$(printf '%s\n' "${WORKFLOW_CONTRACT_KEYS[@]}")"
    assert_eq "$from_map" "$expected" \
        "the emitter's key set must match ci.yml's 18 declared outputs exactly, in name and spelling"

    # CONTROL: the comparison is over a non-empty set. An empty JOB_SURFACES and
    # an empty literal list would compare equal and assert nothing.
    assert_eq "$(printf '%s\n' "${WORKFLOW_CONTRACT_KEYS[@]}" | grep -c .)" "18" \
        "the contract list must hold all 18 keys, or the comparison above is vacuous"
    log_pass "the 18 emitted output names match ci.yml's declared outputs byte for byte"
}

test_quiet_wire_values_do_not_trip_the_kill_switch() {
    # THE EXACT STRINGS ci.yml PRODUCES ON AN ORDINARY PR. `vars.FULL_CI` is the
    # EMPTY STRING when the repository variable is unset, and the label check
    # `contains(...)` renders the literal 'false', never an empty value. Both
    # must read as "not forced". Comparing against 'true' rather than testing
    # for non-emptiness is what makes that work, and this case exists so nobody
    # can later relax it to `[[ -n "$FORCE_FULL_CI" ]]` and make every PR full
    # while the engine looks perfectly healthy.
    local rc=0
    run_gate quietwire FORCE_FULL_CI= FULL_CI_LABEL=false || rc=$?
    assert_exit_code 0 "$rc" "the gate must always exit 0"
    assert_contains "$(cat "$OUTFILE")" "scope_mode=reduced" \
        "an empty FORCE_FULL_CI and a literal 'false' label must NOT force full"
    local n
    n="$(count_false "$OUTFILE")"
    if [[ "$n" -eq 0 ]]; then
        cat "$OUTDIR/gate.log" >&2
        log_fail "the quiet wire values suppressed every false line -- the kill switch is firing on an ordinary PR"
    fi
    assert_eq "$n" "17" "and the reduction must be the same one an unset environment produces"
    log_pass "the empty-string and literal-'false' wire values leave the kill switch disarmed"
}

test_the_deciding_plan_is_the_baseline_plan() {
    # The reduction above can only come from --resolve-baseline: the merge-base
    # classify over B..C2 also touches docs/a.md, and would classify identically
    # here, so the two are told apart by WHICH artifact plan.json was built from.
    # plan.json carries the baseline walk's own fields; a plan.json written from
    # scope-classify.json cannot have them.
    local rc=0
    run_gate deciding || rc=$?
    assert_exit_code 0 "$rc" "the gate must always exit 0"

    local baseline_sha
    baseline_sha="$(node -e '
const p = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
process.stdout.write(String(p.baseline && p.baseline.sha));
' "$OUTDIR/plan.json")"
    assert_eq "$baseline_sha" "$C1_SHA" \
        "plan.json must be the BASELINE plan (it carries the resolved baseline sha), not the merge-base classify"
    assert_eq "$(node -e '
const p = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
process.stdout.write(String(p.run_id));
' "$OUTDIR/plan.json")" "$CURRENT_RUN_ID" \
        "and it must name THIS run, or the reconciler refuses it as substituted evidence"
    log_pass "the plan that gates jobs is the plan the reconciler will audit"
}

test_engine_failure_emits_no_false_line() {
    local rc=0
    run_gate enginefail SCOPE_GH_FAIL=1 || rc=$?
    assert_exit_code 0 "$rc" "an engine failure must still exit 0"
    assert_eq "$(count_false "$OUTFILE")" "0" \
        "an engine that cannot reach the API must not skip a single job"
    assert_contains "$(cat "$OUTFILE")" "scope_mode=full" \
        "and must say so as full, so the reconcile step stays tolerant"

    # CONTROL: the same fixture, same command, working shim. If this did not
    # produce false lines, the assertion above would be measuring the fixture
    # rather than the failure.
    local rc2=0
    run_gate enginefail-control || rc2=$?
    assert_exit_code 0 "$rc2" "the control run must exit 0"
    local n
    n="$(count_false "$OUTFILE")"
    if [[ "$n" -eq 0 ]]; then
        cat "$OUTDIR/gate.log" >&2
        log_fail "CONTROL FAILED: the same fixture with a working gh shim also emitted zero false lines, so the failure case proves nothing"
    fi
    log_pass "an engine failure emits zero false lines (control: the same fixture emits $n)"
}

test_operator_override_forces_full_without_running_the_engine() {
    local switch
    for switch in FORCE_FULL_CI FULL_CI_LABEL; do
        local rc=0
        run_gate "override-$switch" "$switch=true" || rc=$?
        assert_exit_code 0 "$rc" "$switch must still exit 0"
        assert_eq "$(count_false "$OUTFILE")" "0" \
            "$switch must not skip a single job"
        assert_contains "$(cat "$OUTFILE")" "scope_mode=full" "$switch must report full"

        # The override must be legible in the artifact, not just in the outputs:
        # a later run reads this plan as a baseline candidate and an operator
        # reads it to find out why a round was full.
        local reasons
        reasons="$(node -e '
const p = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
process.stdout.write(JSON.stringify(p.full_reasons) + "|" + p.mode);
' "$OUTDIR/plan.json")"
        assert_contains "$reasons" "operator-forced-full" \
            "$switch must name itself in the plan's full_reasons"
        assert_contains "$reasons" "|full" "$switch must produce a full plan"

        # THE ENGINE MUST NOT HAVE RUN. This is the half that makes the kill
        # switch worth having: an operator forcing a full round must not depend
        # on the engine being healthy enough to answer, and must not wait on a
        # baseline walk. No scope-baseline.json means neither happened.
        if [[ -e "$OUTDIR/scope-baseline.json" ]]; then
            log_fail "$switch ran the baseline walk anyway -- the kill switch is downstream of the thing it exists to bypass"
        fi
    done
    log_pass "both kill switches force full, name themselves in the plan, and skip the engine"
}

test_plan_write_failure_emits_nothing_and_still_exits_zero() {
    OUTDIR="$WORK/out-planfail"
    mkdir -p "$OUTDIR/plan.json" # a DIRECTORY where the writer expects a file
    local rc=0
    run_gate planfail || rc=$?
    assert_exit_code 0 "$rc" "an unwritable plan must not fail the job"
    assert_eq "$(wc -l <"$OUTFILE")" "0" \
        "an unwritable plan must emit NO output at all, not even scope_mode"
    assert_contains "$(cat "$OUTDIR/gate.log")" "plan writer FAILED" \
        "and must say so loudly rather than looking like a clean full round"

    # CONTROL: the same case name without the planted directory emits lines.
    rm -rf "$OUTDIR"
    local rc2=0
    run_gate planfail || rc2=$?
    assert_exit_code 0 "$rc2" "the control run must exit 0"
    local n
    n="$(count_false "$OUTFILE")"
    if [[ "$n" -eq 0 ]]; then
        cat "$OUTDIR/gate.log" >&2
        log_fail "CONTROL FAILED: the same run without the planted directory also emitted nothing"
    fi
    log_pass "a plan-write failure emits nothing and exits 0 (control: the same run emits $n)"
}

test_unset_output_file_decides_nothing() {
    # The old shadow behaviour, kept reachable: a local run has no $GITHUB_OUTPUT
    # and must neither crash nor invent one. It must still write the plan, which
    # is what makes `SCOPE_SHADOW_OUT=... scope-shadow.sh` a usable way to see
    # what a change WOULD scope to.
    local rc=0
    run_gate nooutput -u OUTPUT_FILE || rc=$?
    assert_exit_code 0 "$rc" "a run with no OUTPUT_FILE must exit 0"
    assert_eq "$(wc -l <"$OUTFILE")" "0" "and must write nothing anywhere"
    [[ -s "$OUTDIR/plan.json" ]] ||
        log_fail "a run with no OUTPUT_FILE must still write the plan, or the local diagnostic path is gone"
    log_pass "an unset OUTPUT_FILE decides nothing but still writes the plan"
}

log_test "test-scope-gate-outputs"
build_fixture
test_emitted_names_match_the_workflow_contract
test_reduced_plan_emits_exactly_the_out_of_scope_keys
test_quiet_wire_values_do_not_trip_the_kill_switch
test_the_deciding_plan_is_the_baseline_plan
test_engine_failure_emits_no_false_line
test_operator_override_forces_full_without_running_the_engine
test_plan_write_failure_emits_nothing_and_still_exits_zero
test_unset_output_file_decides_nothing
echo ""
log_pass "all tests passed"
