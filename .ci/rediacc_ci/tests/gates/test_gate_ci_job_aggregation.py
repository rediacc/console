r"""Port of `.ci/scripts/test/gates/test-ci-job-aggregation.sh`, retired in W7 P5.

Both-ways test for `rediacc_ci.quality.ci_job_aggregation` (entry point `.ci/scripts/quality/check_ci_job_aggregation.py`), the Python gate that replaced `.ci/scripts/quality/check-ci-job-aggregation.sh` as the registered `check:ci-job-aggregation` step -- the bash file is retired in the same change as this port, once this file reaches the same verdicts on the same fixtures.

The gate's promise: `ci-complete`, the single required status check for branch protection, can see every top-level job in ci.yml. A job outside its `needs:` list, or inside it but with no `RESULT_*` env var, can go red while the required check reports success and the merge button stays enabled.

WHAT IT FOUND. ci.yml declares 24 top-level jobs; `ci-complete` aggregated 18. Five of the six gaps are structural (the aggregator itself, two jobs downstream of it, a job whose cancellation is routine, and build-renet whose failure reaches the verdict only by accident). The sixth, `check-release-state`, was a live hole: it fails, `stage-artifacts` skips because its `if:` requires
that result to be `success` or `skipped`, and the soft tier reads a skip as green, so `CI Complete` passed while a release-state assertion failed on main.

That hole is now CLOSED: check-release-state is in ci-complete's `needs:` and `env:`, and in SOFT_REQUIRED (soft, because it legitimately skips on every PR). `test_real_tree_passes` at the end asserts the repaired state so it cannot regress.

WHY FIXTURES AND NOT THE REAL FILE. Every failure case below plants a synthetic defect. A validator that passes when given nothing is broken by definition, and the only way to know this one can FIRE is to make it fire, one gap shape at a time. Two cases at the end still read the REAL ci.yml, because a parser that only understands its own fixtures is a different kind of blind.

Fixtures are written under `tmp_path` and driven through the gate's `CI_JOB_AGGREGATION_WORKFLOW` / `CI_JOB_AGGREGATION_ASSERT` seams, so no tracked file is ever mutated.
"""

import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_ci_job_aggregation.py")
GATE_MODULE = paths.from_root(".ci", "rediacc_ci", "quality", "ci_job_aggregation.py")
REAL_WORKFLOW = paths.from_root(".github", "workflows", "ci.yml")

# The five jobs the gate exempts. A fixture must declare them, because the gate refuses an exemption that names no job (its liveness check).
EXEMPT_JOBS = [
    "ci-complete",
    "finalize-release-sentinel",
    "pipeline-sentinel",
    "cancel-watchdog",
    "build-renet",
]
# Ordinary jobs. Enough of them, with the exempt five, to clear the gate's 10-job anti-vacuity floor.
PLAIN_JOBS = [
    "initialize",
    "quality",
    "build-cli",
    "build-docker",
    "tests",
    "ops-tests",
    "stage-artifacts",
]


def var_for(job) -> str:
    return "RESULT_%s" % job.upper().replace("-", "_")


def scaffold(
    workflow,
    assert_path,
    *,
    drop_need="",
    drop_result="",
    drop_job="",
    phantom_need="",
    drop_tier="",
    extra_tier="",
    few_jobs=False,
    no_needs=False,
    no_aggregator=False,
):
    """Writes a well-formed pair, then applies exactly the requested defect."""
    plain = ["initialize", "quality"] if few_jobs else list(PLAIN_JOBS)

    all_jobs = []
    for j in EXEMPT_JOBS + plain:
        if j == drop_job:
            continue
        if j == "ci-complete" and no_aggregator:
            continue
        all_jobs.append(j)

    aggregated = [j for j in plain if j not in (drop_job, drop_need)]

    lines = [
        "name: Fixture CI",
        "on:",
        "  push:",
        "    branches: [main]",
        "permissions:",
        "  contents: read",
        "jobs:",
    ]
    for j in all_jobs:
        lines.append("  %s:" % j)
        lines.append("    name: %s" % j)
        lines.append("    runs-on: ubuntu-latest")
        if j == "ci-complete":
            if not no_needs:
                needs_list = list(aggregated)
                if phantom_need:
                    needs_list.append(phantom_need)
                lines.append("    needs: [%s]" % ", ".join(needs_list))
            lines.append("    steps:")
            lines.append("      - run: .ci/scripts/ci/assert-ci-complete.sh")
            lines.append("        env:")
            for k in aggregated:
                if k == drop_result:
                    continue
                lines.append("          %s: ${{ needs.%s.result }}" % (var_for(k), k))
        else:
            lines.append("    steps:")
            lines.append("      - run: echo %s" % j)
    workflow.write_text("\n".join(lines) + "\n", encoding="utf-8")

    hard = []
    soft = []
    for k in aggregated:
        if k == drop_result:
            continue
        var = k.upper().replace("-", "_")
        if var == drop_tier:
            continue
        (hard if k in ("initialize", "build-cli") else soft).append(var)

    lines2 = [
        "#!/bin/bash",
        "set -euo pipefail",
        "HARD_REQUIRED=(%s)" % " ".join(hard),
        "SOFT_REQUIRED=(",
    ]
    lines2.extend("    %s" % var for var in soft)
    if extra_tier:
        lines2.append("    %s" % extra_tier.removeprefix("RESULT_"))
    lines2.append(")")
    assert_path.write_text("\n".join(lines2) + "\n", encoding="utf-8")


def run_gate(workflow, assert_path) -> harness.RunResult:
    return harness.run(
        ["python3", str(GATE)],
        env={
            "CI_JOB_AGGREGATION_WORKFLOW": str(workflow),
            "CI_JOB_AGGREGATION_ASSERT": str(assert_path),
        },
    )


def test_healthy_pair_passes(gate, tmp_path):
    # Baseline. Without this, every failure case below could be passing for the wrong reason (a fixture the parser cannot read fails everything).
    ok_yml, ok_sh = tmp_path / "ok.yml", tmp_path / "ok.sh"
    scaffold(ok_yml, ok_sh)
    result = run_gate(ok_yml, ok_sh)
    gate.assert_eq(result.rc, 0, "a fully wired workflow must pass: %s" % result.combined)
    gate.assert_contains(result.combined, "every non-exempt ci.yml job is aggregated", "and say so")
    gate.log_pass("a fully wired workflow and tier list passes")


def test_job_missing_from_needs_fails(gate, tmp_path):
    # THE PRIMARY DEFECT, planted. This is the shape check-release-state has in the real ci.yml: a declared job the required check never depends on.
    n_yml, n_sh = tmp_path / "n.yml", tmp_path / "n.sh"
    scaffold(n_yml, n_sh, drop_need="ops-tests")
    result = run_gate(n_yml, n_sh)
    gate.assert_eq(result.rc, 1, "a job outside ci-complete's needs must fail the gate")
    gate.assert_contains(result.combined, "NOT in ci-complete's needs", "with the needs diagnostic")
    gate.assert_contains(result.combined, "ops-tests", "naming the job")
    gate.log_pass("a job missing from the aggregator's needs fails and is named")


def test_job_missing_result_env_fails(gate, tmp_path):
    # The second half of the wire. A job can be in needs and still be invisible: assert-ci-complete.sh only reads what the env block passes it.
    r_yml, r_sh = tmp_path / "r.yml", tmp_path / "r.sh"
    scaffold(r_yml, r_sh, drop_result="tests")
    result = run_gate(r_yml, r_sh)
    gate.assert_eq(result.rc, 1, "a job with no RESULT_ env var must fail the gate")
    gate.assert_contains(result.combined, "no RESULT_* env var", "with the env diagnostic")
    gate.assert_contains(result.combined, "RESULT_TESTS", "naming the missing variable")
    gate.log_pass("a job in needs but absent from the env block fails and is named")


def test_phantom_need_fails(gate, tmp_path):
    # The reverse break: a needs entry naming nothing. GitHub rejects the whole workflow at parse time, so catching it locally is strictly cheaper.
    p_yml, p_sh = tmp_path / "p.yml", tmp_path / "p.sh"
    scaffold(p_yml, p_sh, phantom_need="does-not-exist")
    result = run_gate(p_yml, p_sh)
    gate.assert_eq(result.rc, 1, "a needs entry naming no job must fail")
    gate.assert_contains(result.combined, "naming no such job", "with the phantom diagnostic")
    gate.assert_contains(result.combined, "does-not-exist", "naming the phantom")
    gate.log_pass("a needs entry naming no job fails and is named")


def test_untiered_result_var_fails(gate, tmp_path):
    # A var that is passed and then read by nobody. assert-ci-complete.sh does not error on an extra env var, so this is silent by construction.
    u_yml, u_sh = tmp_path / "u.yml", tmp_path / "u.sh"
    scaffold(u_yml, u_sh, drop_tier="OPS_TESTS")
    result = run_gate(u_yml, u_sh)
    gate.assert_eq(result.rc, 1, "a RESULT_ var in no tier must fail")
    gate.assert_contains(
        result.combined, "neither HARD_REQUIRED nor SOFT_REQUIRED", "with the tier diagnostic"
    )
    gate.assert_contains(result.combined, "RESULT_OPS_TESTS", "naming the untiered variable")
    gate.log_pass("a RESULT_ var belonging to no tier fails and is named")


def test_orphan_tier_member_fails(gate, tmp_path):
    # The other direction of the same wire. assert-ci-complete.sh treats an unset var as a failure, so this makes EVERY run red until someone reads the tier list -- loud, but expensive to diagnose in CI rather than here.
    o_yml, o_sh = tmp_path / "o.yml", tmp_path / "o.sh"
    scaffold(o_yml, o_sh, extra_tier="RESULT_GHOST_JOB")
    result = run_gate(o_yml, o_sh)
    gate.assert_eq(result.rc, 1, "a tier member nobody passes must fail")
    gate.assert_contains(result.combined, "never passes", "with the orphan-tier diagnostic")
    gate.assert_contains(result.combined, "RESULT_GHOST_JOB", "naming the orphan")
    gate.log_pass("a tier member with no matching env var fails and is named")


def test_dead_exemption_fails(gate, tmp_path):
    # Liveness. A BLOCKER proves a reason existed; it cannot prove it is still true. Deleting build-renet from the workflow leaves its exemption behind, which is the shape that left 101 electron suppressions in this repo.
    d_yml, d_sh = tmp_path / "d.yml", tmp_path / "d.sh"
    scaffold(d_yml, d_sh, drop_job="build-renet")
    result = run_gate(d_yml, d_sh)
    gate.assert_eq(result.rc, 1, "an exemption for a deleted job must fail")
    gate.assert_contains(
        result.combined, "naming no such job", "with the dead-exemption diagnostic"
    )
    gate.assert_contains(result.combined, "build-renet", "naming the stale entry")
    gate.log_pass("an exemption whose job no longer exists fails and is named")


def test_exempt_job_is_not_required_to_be_aggregated(gate, tmp_path):
    # The exemption must actually do something. In the healthy fixture none of the five exempt jobs is in needs or env, and the gate passes -- so the failure cases above are the exemption being absent, not the check being off.
    e_yml, e_sh = tmp_path / "e.yml", tmp_path / "e.sh"
    scaffold(e_yml, e_sh)
    gate.assert_not_contains(
        e_yml.read_text(encoding="utf-8"),
        "RESULT_BUILD_RENET",
        "the fixture must genuinely leave build-renet unaggregated",
    )
    result = run_gate(e_yml, e_sh)
    gate.assert_eq(result.rc, 0, "an exempt job left unaggregated must still pass")
    gate.log_pass("the exempt set suppresses exactly the jobs it names")


def test_low_effort_blocker_is_rejected(gate, tmp_path):
    # PROVE THE INSTRUMENT. The exempt block claims to be BLOCKER-validated. A copy of the gate with one reason replaced by a banned phrase must fail on the reason, not sail through to the job checks. Without this the validation could be decorative and nothing would say so.
    mutant = tmp_path / "mutant_ci_job_aggregation.py"
    original = GATE_MODULE.read_text(encoding="utf-8")
    mutated = re.sub(
        r"# BLOCKER: this IS the aggregator[^\n]*",
        "# BLOCKER: tbd",
        original,
        count=1,
    )
    gate.assert_contains(mutated, "# BLOCKER: tbd", "the mutation must have applied")
    mutant.write_text(mutated, encoding="utf-8")

    b_yml, b_sh = tmp_path / "b.yml", tmp_path / "b.assert.sh"
    scaffold(b_yml, b_sh)
    result = harness.run(
        ["python3", str(mutant)],
        env={
            "CI_JOB_AGGREGATION_WORKFLOW": str(b_yml),
            "CI_JOB_AGGREGATION_ASSERT": str(b_sh),
            "PYTHONPATH": str(paths.from_root(".ci")),
        },
    )
    gate.assert_eq(result.rc, 1, "a low-effort BLOCKER must fail the gate: %s" % result.combined)
    gate.assert_contains(
        result.combined, "low-effort placeholder", "with the validator's own diagnostic"
    )
    gate.log_pass("a banned-phrase BLOCKER in the exempt set is rejected")


def test_too_few_jobs_is_blind_not_green(gate, tmp_path):
    # Anti-vacuity. A parser that stops understanding the layout returns a tiny job set, and every check over it passes. That must read as blind, never as "all wired".
    f_yml, f_sh = tmp_path / "f.yml", tmp_path / "f.sh"
    scaffold(f_yml, f_sh, few_jobs=True)
    result = run_gate(f_yml, f_sh)
    gate.assert_eq(result.rc, 1, "a below-floor job count must fail")
    gate.assert_contains(result.combined, "this gate is blind", "and say it is blind")
    gate.assert_not_contains(
        result.combined,
        "every non-exempt ci.yml job is aggregated",
        "it must NOT claim everything is wired",
    )
    gate.log_pass("a below-floor job parse reports blindness instead of success")


def test_aggregator_without_needs_is_blind_not_green(gate, tmp_path):
    # The degenerate case the primary check cannot distinguish on its own: with zero needs entries, "every job is missing" is true but the useful verdict is that the aggregator aggregates nothing.
    nn_yml, nn_sh = tmp_path / "nn.yml", tmp_path / "nn.sh"
    scaffold(nn_yml, nn_sh, no_needs=True)
    result = run_gate(nn_yml, nn_sh)
    gate.assert_eq(result.rc, 1, "an aggregator with no needs must fail")
    gate.assert_contains(result.combined, "aggregates nothing", "with the empty-needs diagnostic")
    gate.log_pass("an aggregator with an empty needs list reports that it aggregates nothing")


def test_missing_aggregator_is_named(gate, tmp_path):
    # A rename of the required status check must break here, loudly, rather than matching an empty block and asserting over nothing.
    na_yml, na_sh = tmp_path / "na.yml", tmp_path / "na.sh"
    scaffold(na_yml, na_sh, no_aggregator=True)
    result = run_gate(na_yml, na_sh)
    gate.assert_eq(result.rc, 1, "a missing aggregator job must fail")
    gate.assert_contains(result.combined, "No job named 'ci-complete'", "naming what is gone")
    gate.log_pass("a missing aggregator job is reported by name")


def test_missing_input_file_is_named(gate, tmp_path):
    # An absent input used to be the classic silent pass: no file, no findings, green. Both inputs are guarded.
    ok_sh = tmp_path / "ok.sh"
    ok_sh.write_text("#!/bin/bash\n", encoding="utf-8")
    result = run_gate(tmp_path / "nope.yml", ok_sh)
    gate.assert_eq(result.rc, 1, "a missing workflow must fail")
    gate.assert_contains(result.combined, "input not found", "with the missing-input diagnostic")
    gate.log_pass("a missing input fails instead of asserting over nothing")


def test_parser_understands_the_real_workflow(gate):
    # A parser that only reads its own fixtures is a second kind of blind. This runs against the REAL ci.yml and pins that the job set it extracts is the real one -- 24 jobs at the time of writing, floored at 20 so an ordinary job addition or removal does not fail this test for no reason.
    text = REAL_WORKFLOW.read_text(encoding="utf-8")
    in_jobs = False
    count = 0
    for line in text.split("\n"):
        if re.match(r"^jobs:[ \t]*$", line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^[^ \t#]", line):
            in_jobs = False
        if in_jobs and re.match(r"^  [A-Za-z0-9_-]+:[ \t]*$", line):
            count += 1
    if count < 20:
        gate.log_fail(
            "the real ci.yml parsed to only %d job(s); the gate's parser is blind to the live layout"
            % count
        )
    # And the exempt names must all be live jobs in it, or the gate's own liveness check would be the thing reporting.
    for j in EXEMPT_JOBS:
        occurrences = len(re.findall(r"(?m)^  %s:" % re.escape(j), text))
        gate.assert_eq(
            occurrences, 1, "exempt job '%s' must exist exactly once in the real ci.yml" % j
        )
    gate.log_pass(
        "the parser reads the real ci.yml (%d jobs) and every exempt name is a live job in it"
        % count
    )


def test_real_tree_passes(gate):
    # This case replaces one that asserted the gate still REPORTED the check-release-state gap. That gap was the finding this gate was built
    # for, and it was real: check-release-state was a declared job that
    # ci-complete did not aggregate, and because stage-artifacts requires its result to be `success` OR `skipped`, a FAILURE made stage-artifacts skip, which the soft tier reads as green. `CI Complete` could therefore pass while a release-state assertion failed on main.
    #
    # It is now wired in (ci.yml's ci-complete `needs:` and `env:`, plus SOFT_REQUIRED in assert-ci-complete.sh), so the durable assertion is the inverse: the real tree must PASS, and must keep passing. A future job added to ci.yml without being aggregated fails here as well as in CI.
    result = harness.run(["python3", str(GATE)])
    if result.rc != 0:
        gate.log_fail(
            "the real ci.yml no longer satisfies the aggregation invariant: %s" % result.combined
        )
    gate.assert_contains(
        result.combined,
        "every non-exempt ci.yml job is aggregated",
        "the gate must affirm the real tree, not merely stay silent",
    )
    gate.log_pass("the real ci.yml satisfies the aggregation invariant")
