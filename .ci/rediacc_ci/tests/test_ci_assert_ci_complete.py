"""`rediacc_ci.ci.assert_ci_complete` against its bash twin.

The twin reads ONLY `RESULT_*` env vars plus `POINTER_BUMP_ONLY`, so both sides are driven directly under `diff.env_for(...)`, which REPLACES the environment rather than extending it. That replacement is what makes the `<unset>` cases meaningful: a `RESULT_TESTS` leaking in from the developer's shell would turn the most important assertions in this file green for the wrong reason.

Every case compares stdout, stderr and the exit code byte-for-byte. Nothing is normalised, because this script never prints its own name.

The K=5 ledger is `.ci/shadow/w7p6-assert-ci-complete.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-ci-complete --assert --k 5`).
"""

from __future__ import annotations

from rediacc_ci.ci import assert_ci_complete as port
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/ci/assert-ci-complete.sh"
MODULE = "rediacc_ci.ci.assert_ci_complete"


def all_green() -> dict[str, str]:
    """Every job at `success`. The base every case below perturbs."""
    env = {"RESULT_%s" % job: "success" for job in port.HARD_REQUIRED}
    env.update({"RESULT_%s" % job: "success" for job in port.SOFT_REQUIRED})
    return env


def run_both(
    env_extra: dict[str, str], *, tty: str | None = None
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    old_env = diff.env_for(**env_extra)
    new_env = diff.env_for(**env_extra, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=old_env, tty=tty, timeout=30)
    new = diff.bash_streams("python3 -m %s" % MODULE, env=new_env, tty=tty, timeout=30)
    return old, new


def assert_identical(env_extra: dict[str, str], *, expect_exit: int) -> tuple[int, str, str]:
    old, new = run_both(env_extra)
    assert old[0] == expect_exit, "twin exit changed: %r" % (old,)
    assert new[0] == old[0]
    assert new[1] == old[1]
    assert new[2] == old[2]
    return old


def test_all_success_passes() -> None:
    old = assert_identical(all_green(), expect_exit=0)
    assert old[2] == "✓ All CI jobs passed successfully!\n"
    assert old[1] == ""


def test_the_tier_arrays_still_match_the_twins() -> None:
    """The two arrays are a COPY, so drift is a real risk. Re-read the twin.

    Parsed out of the bash rather than hard-coded a second time here: a test that restated the lists would agree with the port and with itself while both drifted from the file CI actually runs.
    """
    with open("%s/%s" % (diff.repo(), TWIN), encoding="utf-8") as fh:
        text = fh.read()
    hard_line = next(ln for ln in text.splitlines() if ln.startswith("HARD_REQUIRED=("))
    twin_hard = tuple(hard_line.split("(", 1)[1].rstrip(")").split())
    soft_block = text.split("SOFT_REQUIRED=(", 1)[1].split(")", 1)[0]
    twin_soft = tuple(
        word
        for line in soft_block.splitlines()
        for word in line.split()
        if not line.lstrip().startswith("#")
    )
    assert twin_hard == port.HARD_REQUIRED
    assert twin_soft == port.SOFT_REQUIRED


def test_every_unset_variable_is_a_failure_not_a_pass() -> None:
    """An empty environment must NOT read as green. Anti-vacuity, in the twin."""
    old = assert_identical({}, expect_exit=1)
    assert "✗ INITIALIZE: <unset> (hard-required, must be 'success')\n" in old[2]
    assert "✗ QUALITY: <unset> (soft-required, must be 'success' or 'skipped')\n" in old[2]
    assert old[2].endswith(
        "✗ One or more CI jobs did not reach an acceptable conclusion (see above)\n"
    )
    # 5 hard + 16 soft + the trailing summary line.
    assert len(old[2].splitlines()) == len(port.HARD_REQUIRED) + len(port.SOFT_REQUIRED) + 1


def test_an_empty_string_counts_as_unset_on_both_sides() -> None:
    """`${!var:-<unset>}` uses `:-`, so `RESULT_TESTS=` is `<unset>`, not ''."""
    env = all_green()
    env["RESULT_TESTS"] = ""
    old = assert_identical(env, expect_exit=1)
    assert "✗ TESTS: <unset> (soft-required" in old[2]


def test_soft_required_forgives_skipped() -> None:
    env = all_green()
    for job in port.SOFT_REQUIRED:
        env["RESULT_%s" % job] = "skipped"
    assert_identical(env, expect_exit=0)


def test_soft_required_still_blocks_on_failure() -> None:
    env = all_green()
    env["RESULT_BREAKPOINT_LIFECYCLE"] = "failure"
    old = assert_identical(env, expect_exit=1)
    assert (
        "✗ BREAKPOINT_LIFECYCLE: failure (soft-required, must be 'success' or 'skipped')\n"
        in old[2]
    )


def test_hard_required_refuses_skipped() -> None:
    env = all_green()
    env["RESULT_BUILD_CLI"] = "skipped"
    old = assert_identical(env, expect_exit=1)
    assert "✗ BUILD_CLI: skipped (hard-required, must be 'success')\n" in old[2]


def test_hard_findings_are_printed_before_soft_findings() -> None:
    """Order is part of the output, so it is compared rather than assumed."""
    env = all_green()
    env["RESULT_RUN_SH_TESTS"] = "cancelled"
    env["RESULT_QUALITY"] = "cancelled"
    old = assert_identical(env, expect_exit=1)
    lines = old[2].splitlines()
    assert lines[0].startswith("✗ RUN_SH_TESTS:")
    assert lines[1].startswith("✗ QUALITY:")


def test_pointer_bump_forgives_the_three_build_skips() -> None:
    env = all_green()
    env["POINTER_BUMP_ONLY"] = "true"
    for job in port.POINTER_BUMP_EXTRA_SOFT:
        env["RESULT_%s" % job] = "skipped"
    assert_identical(env, expect_exit=0)


def test_pointer_bump_still_blocks_a_build_failure() -> None:
    env = all_green()
    env["POINTER_BUMP_ONLY"] = "true"
    env["RESULT_BUILD_DOCKER"] = "failure"
    old = assert_identical(env, expect_exit=1)
    assert "✗ BUILD_DOCKER: failure (soft-required" in old[2]


def test_pointer_bump_drops_run_sh_tests_from_both_tiers() -> None:
    """A REAL HOLE IN THE TWIN, pinned rather than repaired.

    `POINTER_BUMP_ONLY=true` replaces the hard tier with `(INITIALIZE)` and
    appends only the three build jobs to soft, so `RUN_SH_TESTS` is judged by nothing at all. `ci.yml:532-538` gates `run-sh-tests` on `is_bot` only, so the job really runs on a pointer-bump PR and a genuine failure of the hermetic entry-point suite reads as green.

    Both sides must agree, including on the defect, or the port is not a port. Fixing the twin is a cutover-box decision and is reported, not done here.
    """
    for verdict in ("failure", "cancelled", "skipped", ""):
        env = all_green()
        env["POINTER_BUMP_ONLY"] = "true"
        env["RESULT_RUN_SH_TESTS"] = verdict
        old = assert_identical(env, expect_exit=0)
        assert old[2] == "✓ All CI jobs passed successfully!\n"
        assert "RUN_SH_TESTS" not in old[2]

    # And RUN_SH_TESTS unset entirely -- a renamed job -- is equally invisible.
    env = all_green()
    env["POINTER_BUMP_ONLY"] = "true"
    del env["RESULT_RUN_SH_TESTS"]
    assert_identical(env, expect_exit=0)


def test_pointer_bump_is_the_exact_string_true() -> None:
    """`== "true"`, so `TRUE`/`1`/`yes` leave the full hard tier in force."""
    for value in ("TRUE", "1", "yes", "true ", ""):
        env = all_green()
        env["POINTER_BUMP_ONLY"] = value
        env["RESULT_BUILD_DOCKER"] = "skipped"
        old = assert_identical(env, expect_exit=1)
        assert "✗ BUILD_DOCKER: skipped (hard-required, must be 'success')\n" in old[2]


def test_arguments_are_ignored_by_both() -> None:
    old_env = diff.env_for(**all_green())
    new_env = diff.env_for(**all_green(), PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s --help extra" % TWIN, env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m %s --help extra" % MODULE, env=new_env, timeout=30)
    assert old == new
    assert old[0] == 0


def test_colour_on_a_terminal_is_byte_identical() -> None:
    old, new = run_both({}, tty="stderr")
    assert old[0] == new[0] == 1
    assert diff.escape_bytes(old[2]) > 0, "the twin printed no colour on a tty"
    assert new[2] == old[2]
