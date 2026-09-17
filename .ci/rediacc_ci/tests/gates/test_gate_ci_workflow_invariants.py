"""Port of `.ci/scripts/test/gates/test-ci-workflow-invariants.sh`.

Both-ways test for `.ci/scripts/security/check-ci-workflow-invariants.sh`.

THE METHOD IS THE POINT: a static check that has never been watched FAILING is
indistinguishable from `true`. So the invariant is proven in both directions -- the
real `ci.yml` passes, and a workflow with the invariant broken must exit 1 with the
pinned diagnostic.

The strongest case here is not a synthetic mutation, it is HISTORY: commit
`6584a8795` is the real `main` whose `validate-install` lacked the channel
condition, and it produced "Version mismatch: expected '1.2.27', got '1.2.26'" on
nightlies 32323997586 and 32208001410. If the gate cannot reject that exact file,
it would not have caught the bug it exists for. That case is SKIPPED rather than
failed when the commit is unreachable (a shallow clone), because a missing object
is not evidence of a working gate -- and the skip is printed, not folded into the
green.

WHERE THE PORT REIMPLEMENTS THE TWIN. Two places, both mechanical:

  * THE SCOPED MUTATION. The twin embeds a `python3` heredoc that walks `ci.yml`
    line by line and cuts exactly one `needs.initialize.outputs.channel != ''`
    from inside the `validate-install` job. The port runs the identical algorithm
    natively. The `cut == 1` assertion is kept because it is what caught a
    tolerant-matcher bug once already: the condition stopped being the LAST clause
    when the skip_release gate was added (2026-08-26), an exact-match matcher
    silently cut nothing, and the assertion is the only reason the test did not
    quietly pass over an unmutated file. Keep both halves: the matcher tolerant,
    the assertion strict.

  * THE VACUITY FIXTURE. The twin builds it with `grep -v "docker_tag:"`. The port
    filters the same lines in Python. Same file, no pipeline.

NO `xdist_group`. Each case writes its fixtures into pytest's own `tmp_path` and
drives the gate as a subprocess with `WORKFLOW_FILE` pointing there. Nothing in
the repository is written, and the one case that reads `git` reads it read-only.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-ci-workflow-invariants.sh"

GATE = paths.from_root(".ci", "scripts", "security", "check-ci-workflow-invariants.sh")
REAL = paths.from_root(".github", "workflows", "ci.yml")

HISTORICAL_COMMIT = "6584a8795"
CONDITION = "needs.initialize.outputs.channel != ''"


def run_gate(gate, workflow: pathlib.Path) -> harness.RunResult:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    return harness.run(
        ["bash", str(GATE)], cwd=paths.repo_root(), env={"WORKFLOW_FILE": str(workflow)}
    )


def verdict(result: harness.RunResult) -> str:
    """ "PASS" or "FAIL", the twin's own two-valued shorthand."""
    return "PASS" if result.rc == 0 else "FAIL"


def drop_condition_from_validate_install(source: str) -> tuple[str, int]:
    """The scoped mutation, and the count of lines it cut.

    SCOPED to the `validate-install` block on purpose. A blanket filter would also
    strip `validate-promote`'s identical condition -- two lines match in `ci.yml` --
    so the mutation would be broader than this test's own framing and could then
    pass for the wrong reason.
    """
    out: list[str] = []
    in_job = False
    cut = 0
    for line in source.split("\n"):
        if line.startswith("  validate-install:"):
            in_job = True
        elif (
            in_job
            and line.startswith("  ")
            and not line.startswith("   ")
            and line.rstrip().endswith(":")
        ):
            in_job = False
        # Tolerate a trailing `&&`: the condition stopped being the last clause when the skip_release gate was added after it (2026-08-26).
        if in_job and line.strip().rstrip("&").strip() == CONDITION:
            cut += 1
            # The preceding line now dangles an `&&`; trim it so the YAML parses.
            if out and out[-1].rstrip().endswith("&&"):
                out[-1] = out[-1].rstrip()[:-2].rstrip()
            continue
        out.append(line)
    return "\n".join(out), cut


def test_real_workflow_passes(gate):
    gate.log_test("the baseline every other case rests on")
    # If this failed, every other case would be meaningless.
    if not REAL.is_file():
        gate.log_fail("%s is missing; there is no baseline to judge" % paths.relative_to_root(REAL))
    gate.assert_eq(verdict(run_gate(gate, REAL)), "PASS", "the real ci.yml satisfies the invariant")
    gate.log_pass("the real ci.yml passes")


def test_the_historical_defect_is_rejected(gate, tmp_path: pathlib.Path):
    gate.log_test("THE CASE THAT MATTERS: the pre-fix main that broke the nightlies")
    show = harness.run(
        ["git", "show", "%s:.github/workflows/ci.yml" % HISTORICAL_COMMIT],
        cwd=paths.repo_root(),
    )
    if show.rc != 0:
        # NOT A PASS AND NOT A SILENT SKIP: a missing object is not evidence of a working gate, so it is named on the way past.
        gate.log_info("SKIP: commit %s is not reachable in this checkout" % HISTORICAL_COMMIT)
        gate.log_pass(
            "SKIP the historical case: %s is unreachable here, so no verdict either way"
            % HISTORICAL_COMMIT
        )
        return
    old = tmp_path / "ci-historical.yml"
    old.write_text(show.out, encoding="utf-8")
    result = run_gate(gate, old)
    gate.assert_eq(
        verdict(result), "FAIL", "the pre-fix ci.yml (%s) must be rejected" % HISTORICAL_COMMIT
    )
    gate.assert_contains(result.combined, "channel-as-docker-tag", "the right invariant fires")
    gate.assert_contains(result.combined, "validate-install", "the offending job is named")
    gate.log_pass(
        "the gate rejects the real workflow that broke nightlies 32323997586 and 32208001410"
    )


def test_dropping_the_condition_is_caught(gate, tmp_path: pathlib.Path):
    gate.log_test("a synthetic mutation of the CURRENT file, so the proof cannot rot")
    mutated, cut = drop_condition_from_validate_install(REAL.read_text(encoding="utf-8"))
    # If the shape drifts so far that the mutation stops landing, this fails LOUDLY instead of the test quietly checking nothing.
    gate.assert_eq(cut, 1, "expected to cut exactly 1 line inside validate-install")
    mut = tmp_path / "ci-mutated.yml"
    mut.write_text(mutated, encoding="utf-8")
    gate.assert_eq(
        mutated.count(CONDITION),
        1,
        "exactly one occurrence removed, the other job's gate left intact",
    )
    result = run_gate(gate, mut)
    gate.assert_eq(verdict(result), "FAIL", "removing the channel condition must be caught")
    gate.assert_contains(result.combined, "channel-as-docker-tag", "the right invariant fires")
    gate.log_pass("dropping the channel condition is caught")


def test_vacuity_guard_when_nothing_is_checked(gate, tmp_path: pathlib.Path):
    gate.log_test("a gate whose subject disappeared must not print a green nobody earned")
    novac = tmp_path / "ci-no-docker-tag.yml"
    novac.write_text(
        "\n".join(
            line
            for line in REAL.read_text(encoding="utf-8").split("\n")
            if "docker_tag:" not in line
        ),
        encoding="utf-8",
    )
    result = run_gate(gate, novac)
    gate.assert_eq(
        verdict(result),
        "FAIL",
        "a workflow with no channel-derived docker_tag must not pass silently",
    )
    gate.assert_contains(result.combined, "no-candidates", "the vacuity guard is what fires")
    gate.log_pass("the vacuity guard refuses to pass when the gate verified nothing")


def test_missing_workflow_is_not_green(gate, tmp_path: pathlib.Path):
    gate.log_test("a missing file is not a clean file")
    result = run_gate(gate, tmp_path / "absent.yml")
    gate.assert_eq(verdict(result), "FAIL", "a missing workflow must not read as green")
    gate.assert_contains(result.combined, "workflow-missing", "the missing-file guard fires")
    gate.log_pass("a missing workflow file fails rather than passing vacuously")


def test_a_correctly_gated_job_is_not_flagged(gate, tmp_path: pathlib.Path):
    gate.log_test("THE OTHER DIRECTION: the gate must not simply always fail")
    ok = tmp_path / "ci-ok.yml"
    ok.write_text(
        "name: fixture\n"
        "on: push\n"
        "jobs:\n"
        "  validate-install:\n"
        "    if: >-\n"
        "      always() &&\n"
        "      needs.initialize.outputs.channel != ''\n"
        "    uses: ./.github/workflows/ct-install-methods.yml\n"
        "    with:\n"
        "      docker_tag: ${{ needs.initialize.outputs.channel }}\n",
        encoding="utf-8",
    )
    gate.assert_eq(verdict(run_gate(gate, ok)), "PASS", "a correctly gated job must pass")
    gate.log_pass("a correctly gated job is not flagged")
