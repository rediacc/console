"""Port of `.ci/scripts/test/gates/test-workflow-pr-environment.sh`, retired in W7 P5.

Both-ways test for the pr-environment rule in `.ci/scripts/quality/check-workflows.sh`.

THE BUG IT GUARDS. A job-level `environment:` makes GitHub create the environment OBJECT and a deployment record. ci.yml's deploy-preview job declared
`pr-${{ github.event.pull_request.number }}`, and CI can never clean the objects
up: deleting one needs Administration:write, which check:ci-app-admin-perm deliberately forbids the CI App from holding, so a leaked token cannot delete `edge` or `stable`. 25 empty `pr-*` shells accumulated on /deployments and had to be removed by hand on 2026-09-03.

THE POSITIVE CONTROL IS THE HISTORICAL DEFECT, VERBATIM: the exact three lines removed from ci.yml, not a synthetic mutation. That text is what created the 25. A rule that cannot reject it would not have caught the thing it exists for.

AND THE SCALAR FORM, which is the case that decides whether this rule is real.
`environment: pr-${{ ... }}` on one line is equally valid GitHub and would sail
past a rule that only looked at a `name:` key. This repo has already shipped a workflow rule that was born VACUOUS (an awk `\\b` that matched nothing while reporting "All workflows are clean"), so the half that is easy to omit is the half asserted first.

NO "the real tree passes" CASE, deliberately, and the twin says why: check:ci-workflows runs this very rule over the real .github/workflows on every pre-push and every CI run, so a copy here asserts nothing new, and it is not free -- the full scan took that battery from ~2s to 21.6s under the lane's contention, which check:ci-gate-manifest correctly refused. The real-tree verdict
belongs to the gate; this file's job is the two directions the gate cannot show by passing.

NO `xdist_group`. Each case gets its own `mktemp -d` fixture directory, and the subject is driven with a per-subprocess environment rather than by mutating this one.
"""

from rediacc_ci.tests.gates import harness, workflow_rule


def test_mapping_form_is_caught(gate):
    gate.log_test("the historical ci.yml block, verbatim, must be refused")
    with harness.temp_dir() as d:
        # The literal block deleted from ci.yml:1234-1236.
        workflow_rule.write_job(
            d / "bad.yml",
            "environment:",
            "  name: pr-${{ github.event.pull_request.number }}",
            "  url: https://pr-${{ github.event.pull_request.number }}.rediacc.workers.dev",
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(1, result.rc, "the historical ci.yml block is refused")
        gate.assert_contains(result.combined, "bad.yml:", "and the finding cites the file and line")
    gate.log_pass("the mapping form -- the defect verbatim -- is caught")


def test_scalar_form_is_caught(gate):
    gate.log_test("the scalar shorthand decides whether this rule is real")
    with harness.temp_dir() as d:
        workflow_rule.write_job(
            d / "bad.yml", "environment: pr-${{ github.event.pull_request.number }}"
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(1, result.rc, "the scalar shorthand is refused too")
    gate.log_pass("the scalar shorthand is caught, so the rule is not a name:-grep")


def test_real_environments_pass(gate):
    gate.log_test("CONTROL: the three forms production actually uses")
    # If the rule rejected these it would block every deploy, which is a worse failure than the one it fixes.
    with harness.temp_dir() as d:
        workflow_rule.write_job(d / "a.yml", "environment:", "  name: edge")
        workflow_rule.write_job(d / "b.yml", "environment:", "  name: ${{ inputs.target }}")
        workflow_rule.write_job(
            d / "c.yml", "environment:", "  name: ${{ inputs.target }}-${{ matrix.id }}"
        )
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(0, result.rc, "edge, inputs.target and the regional form all pass")
    gate.log_pass("CONTROL: the three real production environments are not flagged")


def test_a_pr_prefixed_word_is_not_a_pr_environment(gate):
    gate.log_test("CONTROL: the anchor must be the DASH, not the two letters")
    # `preview` starts with `pr` but is not `pr-`.
    with harness.temp_dir() as d:
        workflow_rule.write_job(d / "a.yml", "environment:", "  name: preview")
        result = workflow_rule.run_check(gate, d, ci=True)
        gate.assert_exit_code(0, result.rc, "a name merely starting with pr is not pr-")
    gate.log_pass("CONTROL: 'preview' is not mistaken for a pr- environment")


def test_the_fixture_directory_is_what_is_judged(gate):
    """CONTROL ON THE HARNESS ITSELF, which no case above supplies.

    Every case here claims a verdict about a fixture tree, and every one of those
    claims rests on `WORKFLOW_INLINE_ONLY=1` actually emptying GITHUB_YAMLS so the
    banned-pattern scans become no-ops and `WORKFLOW_DIR` is the only thing judged. If that switch stopped working, the rule would be reading the REAL `.github/workflows` -- which is clean, and has to stay clean, so the passing cases would keep passing for a reason that has nothing to do with their fixtures.

    Two directories, one violating and one clean, driven through the same incantation in the same process. A verdict that TRACKS the directory is the only evidence that the directory is what was read.
    """
    with harness.temp_dir() as root:
        bad = root / "bad"
        good = root / "good"
        bad.mkdir()
        good.mkdir()
        workflow_rule.write_job(
            bad / "offender.yml",
            "environment:",
            "  name: pr-${{ github.event.pull_request.number }}",
        )
        workflow_rule.write_job(good / "fine.yml", "environment:", "  name: edge")
        bad_result = workflow_rule.run_check(gate, bad, ci=True)
        good_result = workflow_rule.run_check(gate, good, ci=True)
        gate.assert_exit_code(1, bad_result.rc, "the violating fixture directory reds")
        gate.assert_exit_code(0, good_result.rc, "the clean fixture directory passes")
        gate.assert_contains(
            bad_result.combined,
            "offender.yml",
            "the finding names the fixture's own file, so the fixture is what was scanned",
        )
        gate.assert_not_contains(
            good_result.combined,
            "offender.yml",
            "and the clean run never saw the other directory's file",
        )
    gate.log_pass(
        "the verdict tracks WORKFLOW_DIR, so the fixtures above are really what is judged"
    )
