"""Port of `.ci/scripts/test/gates/test-releaseversion-cd-retry-assert.sh`.

Both-ways test for the artifact-version assertion's reachability in `.github/workflows/cd-v2.yml`.

WHAT THE ASSERTION IS FOR. assert-artifact-version.sh compares the version baked into the CI artifacts against the version CD is about to publish them under. It is the only thing standing between "these bytes were built as 1.2.16" and a GitHub Release labelled 1.2.17.

WHAT WAS BROKEN. The step carried `retry_mode != 'true'`, excused by a comment
claiming "retry uses the latest tag's version, which the artifacts already match by definition". They do not. Retry takes its VERSION from resolve-version.sh --current, but its ARTIFACTS from resolve-ci-run.sh, which with no ci_run_id supplied picks the LATEST GREEN CI RUN ON MAIN -- not the run that cut that tag. A retry dispatched after any newer CI went green republishes those
newer artifacts under the older tag, which is precisely the mismatch the assertion exists to catch,
with the assertion switched off.

This is a text test rather than a YAML-object test on purpose: the condition is a GitHub expression inside a folded scalar, so its meaning lives in the string either way. The twin keeps awk to stay dependency-free; the port reimplements the same range extraction in Python and `test_the_extractor_matches_the_twins_awk` drives the twin's awk against the same file to prove the two
agree, so the change of implementation is a claim this file has to earn rather than assume.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-releaseversion-cd-retry-assert.sh"

WORKFLOW = paths.from_root(".github", "workflows", "cd-v2.yml")
STEP_NAME = "Assert artifact version matches promotion target"

# The twin's awk program, verbatim, so the equivalence control below drives the real thing rather than a paraphrase of it.
AWK = """
        index($0, "- name: " name) { p = 1; print; next }
        p && /^      - / { exit }
        p { print }
"""


def step_block(path: pathlib.Path, name: str = STEP_NAME) -> str:
    """The step's own YAML block: from its `- name:` line up to (not including) the next step at the same indentation."""
    out = []
    printing = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if ("- name: " + name) in line:
            printing = True
            out.append(line)
            continue
        if printing and line.startswith("      - "):
            break
        if printing:
            out.append(line)
    return "\n".join(out) + ("\n" if out else "")


def test_the_extractor_matches_the_twins_awk(gate):
    """CONTROL FOR THE PORT ITSELF. The twin extracts with awk; this file extracts with a Python loop. A port that changes the extractor and does not compare it against the original has replaced a tested reader with an untested one, and every assertion below would then be about the new reader's idea of the step."""
    awk = harness.run(["awk", "-v", "name=" + STEP_NAME, AWK, str(WORKFLOW)])
    gate.assert_exit_code(0, awk.rc, "the twin's awk still runs")
    gate.assert_eq(step_block(WORKFLOW), awk.out, "the Python extractor agrees with the awk one")
    gate.assert_not_contains(awk.out, "\n\n\n", "and the block is a real block, not empty output")
    gate.log_pass("the ported extractor is byte-identical to the twin's awk on the real workflow")


def test_step_exists(gate):
    gate.log_test("the artifact-version assertion step is present")
    block = step_block(WORKFLOW)
    gate.assert_contains(
        block, "assert_artifact_version", "the step must still run the assertion script"
    )
    gate.log_pass("step found in cd-v2.yml")


def test_retry_mode_no_longer_skips_it(gate):
    gate.log_test("retry mode does NOT skip the assertion")
    block = step_block(WORKFLOW)
    gate.assert_not_contains(block, "retry_mode", "retry must not be excluded from the assertion")
    gate.log_pass("the assertion runs in retry mode")


def test_workers_only_still_skips_it(gate):
    gate.log_test("workers-only still skips the assertion")
    block = step_block(WORKFLOW)
    gate.assert_contains(
        block,
        "workers_only != 'true'",
        "workers-only promotes no artifacts, so it stays excluded",
    )
    # `skip_release` WAS REMOVED FROM cd-v2 (2026-08-26) and asserting it here would now pin a condition that cannot exist. decide-release-mode.sh wrote that output `false` on all three of its paths, so every guard reading it was permanently true -- a condition that cannot be false is a claim, not a guard.
    #
    # Match the CONDITION (`outputs.skip_release`), not the bare word: cd-v2 now carries a comment explaining why the clause was removed, and asserting on the word alone flagged that prose. A gate that cannot survive being written about is too broad.
    gate.assert_not_contains(
        block,
        "outputs.skip_release",
        "the permanently-true skip_release guard is gone; exclusion is upstream, at dispatch",
    )
    gate.log_pass("workers-only remains excluded")


def test_version_env_covers_retry_mode(gate):
    # A step that runs in retry mode but reads only the normal-mode version output would receive an EMPTY VERSION there, which assert-artifact-version.sh rejects outright -- a hard failure on every retry. The env must cover both paths, in the same precedence the job's own next_version output uses.
    gate.log_test("VERSION is wired for both the retry and normal paths")
    block = step_block(WORKFLOW)
    gate.assert_contains(
        block, "steps.version.outputs.next_version", "the retry-mode version output must be read"
    )
    gate.assert_contains(
        block, "steps.init.outputs.next_version", "the normal-mode version output must be read"
    )
    gate.log_pass("VERSION covers retry and normal modes")


def test_planted_old_condition_is_caught(gate, tmp_path):
    # THE CONTROL. Plant the old condition in a copy and prove the checks above go red on it. Without this, "no retry_mode found" could just as easily mean the extractor matched nothing.
    gate.log_test("control: the pre-fix condition is detected")
    # THE PLANT ANCHOR MOVED (2026-08-26). It used to substitute on the
    # `skip_release != 'true' &&` line, which no longer exists -- that guard was
    # permanently true and was removed. The control caught its own plant failing to land rather than passing over an unmutated fixture, which is exactly what it is for. Re-anchored on the condition that IS still there.
    anchor = "        if: steps.skip-check.outputs.workers_only != 'true'"
    replacement = (
        "        if: >-\n"
        "          steps.skip-check.outputs.workers_only != 'true' &&\n"
        "          steps.skip-check.outputs.retry_mode != 'true'"
    )
    body = WORKFLOW.read_text(encoding="utf-8")
    lines = body.splitlines()
    if anchor not in lines:
        gate.log_fail(
            "CONTROL could not plant its defect: the anchor line %r is gone from "
            "cd-v2.yml, so the mutation is a no-op and the checks above would be "
            "passing over an unmutated fixture" % anchor
        )
    planted = tmp_path / "cd-v2.yml"
    planted.write_text(
        "\n".join(replacement if line == anchor else line for line in lines) + "\n",
        encoding="utf-8",
    )

    block = step_block(planted)
    gate.assert_contains(
        block,
        "retry_mode",
        "planted condition must be visible to the extractor (else these checks prove nothing)",
    )
    gate.assert_contains(
        block, "assert_artifact_version", "planted fixture must still be the right step"
    )
    gate.log_pass("the extractor demonstrably sees a retry_mode exclusion when one exists")
