"""Port of `.ci/scripts/test/gates/test-workflow-inline.sh`.

Both-ways test for the inline-run rule in
`.ci/scripts/quality/check-workflows.sh`.

The rule keeps CI step LOGIC out of workflow YAML: a `run:` block scalar whose
shell logic exceeds INLINE_MAX_LOGIC (8) non-blank / non-comment lines is a
violation. There is no baseline and no per-file exemption. A gate like this fails
in BOTH directions, so both are asserted:

  * Too quiet: an over-threshold block slips through and the workflow accretes
    un-shared shell logic, or the whole rule goes blind because the workflow
    directory moved.
  * Too loud: it miscounts (comments, blank lines, the step's own YAML keys) and
    reds a file that already complies.

HISTORY, because it is the point of `test_no_baseline_escape_hatch`: the rule
used to be a ratchet over `.ci/quality/workflow-inline-baseline.json`, which
grandfathered 52 legacy blocks. All 52 were extracted and both the file and the
ratchet logic were deleted. If someone reintroduces a baseline the rule stops
holding, so that case pins its ABSENCE rather than trusting the reviewer.

CI IS NOT SET HERE, and that is copied from the twin rather than overlooked.
test-workflow-inline.sh defines its own `run_check` with no `CI` assignment,
unlike the two callers of workflow-rule.sh which hard-code `CI=true`. The shared
helper therefore takes `ci` as an argument and this file passes False, so the
fixtures are judged in the same environment the twin judges them in.

NO `xdist_group`. Each case gets its own `mktemp -d` fixture directory, and the
subject is driven with a per-subprocess environment rather than by mutating this
one.
"""

import pathlib

from rediacc_ci.tests.gates import harness, workflow_rule

BASH_TWIN = ".ci/scripts/test/gates/test-workflow-inline.sh"

# INLINE_MAX_LOGIC, restated so the boundary cases can be read without opening the subject. It is a MIRROR of the rule's constant, not the source of it: the boundary case below drives 8 and 9 through the real script, so a change to the rule reds there rather than silently agreeing with this line.
INLINE_MAX_LOGIC = 8


def write_workflow(path: pathlib.Path, n: int, lines: int = 9) -> None:
    """`n` over-threshold `run:` blocks plus one always-clean thin block.

    The thin block is what proves thin blocks never count: it is present in every
    fixture, including the one whose expected verdict is a pass.
    """
    body = [
        "name: fixture",
        "on: push",
        "jobs:",
        "  job:",
        "    runs-on: ubuntu-latest",
        "    steps:",
    ]
    for i in range(1, n + 1):
        body.append("      - name: Violating %d" % i)
        body.append("        run: |")
        body += ["          echo line%d" % j for j in range(1, lines + 1)]
    body += [
        "      - name: Thin",
        "        run: |",
        "          echo hi",
        "          bash .ci/scripts/quality/x.sh",
    ]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def run_check(gate, directory, **extra):
    return workflow_rule.run_check(gate, directory, ci=False, **extra)


def test_thin_blocks_never_count(gate):
    gate.log_test("a file of only thin run: blocks must pass")
    with harness.temp_dir() as d:
        write_workflow(d / "clean.yml", 0)
        result = run_check(gate, d)
        gate.assert_exit_code(0, result.rc, "a file with only thin run: blocks must pass")
    gate.log_pass("thin (<=%d line) run: blocks never count as violations" % INLINE_MAX_LOGIC)


def test_fails_any_over_threshold_block(gate):
    gate.log_test("the core of the rule after the baseline was deleted")
    # ONE fat block anywhere fails, with no way to declare it acceptable.
    with harness.temp_dir() as d:
        write_workflow(d / "newbie.yml", 1)
        result = run_check(gate, d)
        gate.assert_exit_code(1, result.rc, "any file with inline logic must fail")
        gate.assert_contains(result.combined, "newbie.yml", "names the offending file")
        gate.assert_contains(
            result.combined,
            "1 inline run: block(s) exceed %d" % INLINE_MAX_LOGIC,
            "reports the count and the threshold",
        )
        gate.assert_contains(
            result.combined,
            "extract each over-threshold block to .ci/scripts",
            "prints the teaching remedy",
        )
    gate.log_pass("a single over-threshold block fails, no exceptions")


def test_reports_line_and_step_name(gate):
    gate.log_test("a gate that says WHERE, not just that the file is bad")
    # Without it the author hunts manually through a 600-line workflow.
    with harness.temp_dir() as d:
        write_workflow(d / "located.yml", 1)
        result = run_check(gate, d)
        gate.assert_exit_code(1, result.rc, "over-threshold block must fail")
        gate.assert_contains(result.combined, "located.yml:8", "cites file:line of the run: block")
        gate.assert_contains(result.combined, "step: Violating 1", "names the offending step")
        gate.assert_contains(
            result.combined, "has 9 logic lines", "reports the block's own logic-line count"
        )
    gate.log_pass("reports file:line, step name and logic-line count")


def test_boundary_at_threshold(gate):
    gate.log_test("off-by-one guard on BOTH sides of the threshold")
    with harness.temp_dir() as d:
        write_workflow(d / "at.yml", 1, INLINE_MAX_LOGIC)
        result = run_check(gate, d)
        gate.assert_exit_code(
            0, result.rc, "exactly %d logic lines is at the limit and must pass" % INLINE_MAX_LOGIC
        )
        (d / "at.yml").unlink()
        write_workflow(d / "over.yml", 1, INLINE_MAX_LOGIC + 1)
        result = run_check(gate, d)
        gate.assert_exit_code(
            1,
            result.rc,
            "%d logic lines is over the limit and must fail" % (INLINE_MAX_LOGIC + 1),
        )
    gate.log_pass(
        "boundary is exact: %d passes, %d fails" % (INLINE_MAX_LOGIC, INLINE_MAX_LOGIC + 1)
    )


def test_comments_and_blanks_are_not_logic(gate):
    gate.log_test("TOO-LOUD direction: authors must not be punished for explaining themselves")
    # A well-commented 6-line block must not be counted as a 20-line one.
    with harness.temp_dir() as d:
        body = [
            "name: fixture",
            "on: push",
            "jobs:",
            "  job:",
            "    runs-on: ubuntu-latest",
            "    steps:",
            "      - name: Commented",
            "        run: |",
        ]
        for i in range(1, 7):
            body += ["          # explanation %d" % i, "", "          echo line%d" % i]
        (d / "commented.yml").write_text("\n".join(body) + "\n", encoding="utf-8")
        result = run_check(gate, d)
        gate.assert_exit_code(
            0, result.rc, "comments and blank lines must not count toward the limit"
        )
    gate.log_pass("only non-blank, non-comment lines count as logic")


def test_counts_blocks_within_a_file(gate):
    gate.log_test("the rule counts BLOCKS inside a file, not mere file presence")
    with harness.temp_dir() as d:
        write_workflow(d / "multi.yml", 3)
        result = run_check(gate, d)
        gate.assert_exit_code(1, result.rc, "3 over-threshold blocks must fail")
        gate.assert_contains(
            result.combined, "3 inline run: block(s)", "reports the actual block count"
        )
        gate.assert_contains(
            result.combined, "step: Violating 3", "reports the LAST block, not just the first"
        )
    gate.log_pass("counts each over-threshold block within a file (reports 3, not 1)")


def test_reports_every_offending_file(gate):
    gate.log_test("stopping at the first bad file turns one fix round into three")
    with harness.temp_dir() as d:
        write_workflow(d / "alpha.yml", 1)
        write_workflow(d / "beta.yml", 2)
        result = run_check(gate, d)
        gate.assert_exit_code(1, result.rc, "multiple offending files must fail")
        gate.assert_contains(result.combined, "alpha.yml", "names the first offending file")
        gate.assert_contains(result.combined, "beta.yml", "names the second offending file")
    gate.log_pass("reports every offending file in one pass")


def test_no_baseline_escape_hatch(gate):
    gate.log_test("regression guard on the DELETED grandfather clause")
    # A baseline file sitting in the tree, naming the offending workflow with a matching count, must NOT excuse it. If this ever passes at exit 0, the ratchet has come back.
    with harness.temp_dir() as d:
        write_workflow(d / "legacy.yml", 2)
        (d / "baseline.json").write_text('{"legacy.yml":2}\n', encoding="utf-8")
        (d / "workflow-inline-baseline.json").write_text('{"legacy.yml":2}\n', encoding="utf-8")
        result = run_check(
            gate, d, extra_env={"WORKFLOW_INLINE_BASELINE": str(d / "baseline.json")}
        )
        gate.assert_exit_code(1, result.rc, "a baseline file must not grandfather anything")
        gate.assert_contains(
            result.combined,
            "legacy.yml",
            "still names the file the baseline tried to excuse",
        )
    gate.log_pass("no baseline escape hatch: a stray baseline file changes nothing")


def test_empty_tree_is_not_a_pass(gate):
    gate.log_test("ANTI-VACUITY: a workflow dir with no workflows is not clean")
    # If the workflow directory moves or empties, the rule is asserting nothing and must say so instead of reporting clean. `assert_vacuous_tree_fails` is
    # the harness's port of the bash helper of the same name; it takes a runner
    # returning a RunResult, where the bash original left the output in $LAST_OUT.
    with harness.temp_dir() as d:
        gate.assert_vacuous_tree_fails(
            lambda path: run_check(gate, path),
            d,
            "this check is blind",
            "a workflow dir with no workflows must fail, not pass vacuously",
        )


def test_the_fixture_directory_is_what_is_judged(gate):
    """CONTROL ON THE HARNESS ITSELF, which no case above supplies.

    Every case here claims a verdict about a fixture tree, and every one of those
    claims rests on `WORKFLOW_INLINE_ONLY=1` actually emptying GITHUB_YAMLS so the
    banned-pattern scans become no-ops and `WORKFLOW_DIR` is the only thing
    judged. `test_empty_tree_is_not_a_pass` proves the rule REFUSES a directory
    with nothing in it, which is a different claim: it says the scan noticed the
    absence, not that a PRESENT file was the one read.

    Two directories, one violating and one clean, driven through the same
    incantation in the same process. A verdict that TRACKS the directory is the
    only evidence that the directory is what was read.
    """
    with harness.temp_dir() as root:
        bad = root / "bad"
        good = root / "good"
        bad.mkdir()
        good.mkdir()
        write_workflow(bad / "offender.yml", 1)
        write_workflow(good / "fine.yml", 0)
        bad_result = run_check(gate, bad)
        good_result = run_check(gate, good)
        gate.assert_exit_code(1, bad_result.rc, "the violating fixture directory reds")
        gate.assert_exit_code(0, good_result.rc, "the clean fixture directory passes")
        gate.assert_contains(
            bad_result.combined,
            str(bad),
            "the finding cites the FIXTURE path, so the real .github tree is not what was scanned",
        )
    gate.log_pass(
        "the verdict tracks WORKFLOW_DIR, so the fixtures above are really what is judged"
    )
