"""Port of `.ci/scripts/test/gates/test-installmethods-args.sh`.

`.ci/scripts/test/test-install-methods.sh` must not be able to report success
without having accounted for at least one test. Reproduced live on 2026-08-07:

    test-install-methods.sh --dry-run --method bogus --version 1.2.17
    -> "Results: 0 passed, 0 failed, 0 skipped (total 0)"   EXIT=0

Two causes, both fixed and both pinned here. The argument parser ended with a
bare `*) shift ;;` that swallowed anything it did not recognise, and METHOD was
never validated, so a typo produced a run that matched no test block. And
success was defined as `[[ $FAIL -eq 0 ]]`, which is also true of a run that did
nothing at all.

The rule: every path ends VERIFIED, or in a VISIBLE skip, or in a FAILURE. An
all-skipped run is deliberately still a success -- each skip is printed with its
reason and counted -- but a zero-total run is not, because it says nothing.

Every case drives the REAL script in `--dry-run`, so no Docker and no network.
The zero-total backstop is proven to fire against a MUTATED COPY in a tempdir:
mutating in place under `.ci/` is not an option in a shared tree, and the copy
is why this module writes nowhere outside `tmp_path`.
"""

import pathlib
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-installmethods-args.sh"

TARGET = paths.from_root(".ci", "scripts", "test", "test-install-methods.sh")

# The mutations. WIDEN loosens the parser so a method matching no test block is
# admitted, which is the pre-fix behaviour; DROP_BACKSTOP additionally deletes
# the zero-total refusal, i.e. the code exactly as it stood on 2026-08-07.
WIDEN = ('VALID_METHODS="binary', 'VALID_METHODS="bogus binary')


def target(gate) -> pathlib.Path:
    """The subject, or a LOUD refusal. A missing subject is not a pass."""
    if not TARGET.is_file():
        gate.log_fail("target not found: %s" % TARGET)
    return TARGET


def run_target(script, *args) -> harness.RunResult:
    """Drive the script (or a copy) and merge its streams, as the twin does."""
    return harness.run(["bash", str(script), *args], timeout=120)


def mutate(gate, dest: pathlib.Path, *, drop_backstop: bool = False) -> pathlib.Path:
    """A copy of the subject with the parser widened, in `dest`.

    The copy lives in a tempdir, so SCRIPT_DIR is pinned back at the real
    directory or it cannot find lib/common.sh.
    """
    source = target(gate).read_text(encoding="utf-8")
    if WIDEN[0] not in source:
        gate.log_fail(
            "the subject no longer contains %r, so the mutation would be a no-op and "
            "the backstop control below would prove nothing" % WIDEN[0]
        )
    lines = []
    dropping = False
    for line in source.splitlines():
        if line.startswith("SCRIPT_DIR="):
            lines.append('SCRIPT_DIR="%s"' % target(gate).parent)
            continue
        if drop_backstop:
            if line == "if ((TOTAL == 0)); then":
                dropping = True
                continue
            if dropping:
                if line == "fi":
                    dropping = False
                continue
        lines.append(line.replace(WIDEN[0], WIDEN[1], 1) if WIDEN[0] in line else line)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copymode(target(gate), dest)
    return dest


def test_unknown_method_is_fatal(gate):
    result = run_target(target(gate), "--dry-run", "--method", "bogus", "--version", "1.2.17")
    gate.assert_exit_code(2, result.rc, "an unknown --method must be a hard error")
    gate.assert_contains(
        result.combined, "unknown --method 'bogus'", "the error must name the bad value"
    )
    gate.assert_contains(
        result.combined, "valid --method values:", "the error must list the valid values"
    )
    gate.assert_contains(
        result.combined, "apt", "the valid-value list must actually contain the methods"
    )
    gate.assert_not_contains(result.combined, "total 0", "it must not reach the summary at all")
    gate.log_pass("a typo'd --method stops the run instead of verifying nothing")


def test_unknown_argument_is_fatal(gate):
    result = run_target(target(gate), "--dry-run", "--nope", "--version", "1.2.17")
    gate.assert_exit_code(2, result.rc, "an unrecognised argument must be a hard error")
    gate.assert_contains(
        result.combined, "unknown argument: '--nope'", "the error must name the bad argument"
    )
    gate.log_pass("an unrecognised argument is no longer swallowed")


def test_a_flag_without_a_value_is_fatal(gate):
    for flag in ("--method", "--version", "--platform", "--arch", "--local-artifacts"):
        result = run_target(target(gate), "--dry-run", flag)
        gate.assert_exit_code(2, result.rc, "%s with no value must be a hard error" % flag)
        gate.assert_contains(
            result.combined, "%s requires a value" % flag, "the error must name the flag"
        )
    gate.log_pass("every value-taking flag refuses an empty value")


def test_unknown_platform_and_arch_are_fatal(gate):
    result = run_target(
        target(gate),
        "--dry-run",
        "--method",
        "binary",
        "--version",
        "1.2.17",
        "--platform",
        "solaris",
    )
    gate.assert_exit_code(2, result.rc, "an unknown --platform must be a hard error")
    gate.assert_contains(
        result.combined, "unknown --platform 'solaris'", "the error must name the bad platform"
    )

    result = run_target(
        target(gate),
        "--dry-run",
        "--method",
        "binary",
        "--version",
        "1.2.17",
        "--arch",
        "riscv",
    )
    gate.assert_exit_code(2, result.rc, "an unknown --arch must be a hard error")
    gate.assert_contains(
        result.combined, "unknown --arch 'riscv'", "the error must name the bad arch"
    )
    gate.log_pass("a platform or arch that matches no test block stops the run")


def test_a_valid_run_still_works(gate):
    """The other direction: the parser must not have become so strict that a
    legitimate invocation fails. These are the exact flag shapes ci.yml and
    ct-install-methods.yml use."""
    result = run_target(target(gate), "--dry-run", "--method", "apt", "--version", "1.2.17")
    gate.assert_exit_code(0, result.rc, "a valid invocation must still succeed")
    gate.assert_contains(result.combined, "total 3", "the three APT distros must be accounted for")

    result = run_target(
        target(gate),
        "--dry-run",
        "--method",
        "binary",
        "--version",
        "1.2.17",
        "--platform",
        "linux",
        "--arch",
        "arm64",
    )
    gate.assert_exit_code(0, result.rc, "a valid --platform/--arch invocation must still succeed")
    gate.log_pass("the invocations CI actually uses are still accepted")


def test_a_dry_run_is_never_reported_as_a_pass(gate):
    """A dry run installs nothing and compares no version. It used to be counted
    as a PASS, which made "3 passed, 0 failed" indistinguishable in the summary
    from three real verifications."""
    result = run_target(target(gate), "--dry-run", "--method", "apt", "--version", "1.2.17")
    gate.assert_exit_code(0, result.rc, "a dry run is not a failure")
    gate.assert_contains(result.combined, "0 passed", "a dry run must claim zero passes")
    gate.assert_contains(result.combined, "3 skipped", "a dry run must be counted as skips")
    gate.assert_contains(
        result.combined, "dry-run, nothing was verified", "the reason must be visible per test"
    )
    gate.log_pass("a dry run reports skips, not passes")


def test_an_all_skipped_run_is_visible_and_allowed(gate):
    """`--method verify` with no REPO_CHANNEL is a real CI condition (schedule
    and workflow_dispatch stage no artifacts). It must succeed, and it must SAY
    that it verified nothing -- the visible-skip half of the rule."""
    result = harness.run(
        ["bash", str(target(gate)), "--method", "verify", "--version", "1.2.17"],
        env={"REPO_CHANNEL": ""},
        timeout=120,
    )
    gate.assert_exit_code(0, result.rc, "an all-skipped run is a success")
    gate.assert_contains(result.combined, "SKIP: Channel Verify", "the skip must be named")
    gate.assert_contains(result.combined, "no REPO_CHANNEL", "the skip must carry its reason")
    gate.assert_contains(
        result.combined, "1 skipped", "the skip must be counted, so the total is never zero"
    )
    gate.assert_not_contains(
        result.combined, "total 0", "a block that matched must never leave the total at zero"
    )
    gate.log_pass("an all-skipped run succeeds loudly rather than silently")


def test_the_backstop_fires_on_a_zero_total_run(gate, tmp_path):
    """The zero-total backstop, proven against a mutated copy.

    With every method, platform and arch validated, and every block registering
    at least a skip, no invocation of the shipped script can reach a zero total.
    That makes the backstop unreachable by argument alone -- and an unreachable
    guard is exactly the kind that rots into one that cannot fire.
    """
    # Mutation 1: only the parser is loosened. The backstop must catch it.
    with_backstop = mutate(gate, tmp_path / "with-backstop.sh")
    result = run_target(with_backstop, "--dry-run", "--method", "bogus", "--version", "1.2.17")
    gate.assert_exit_code(1, result.rc, "a run that executed zero tests must FAIL")
    gate.assert_contains(
        result.combined, "total 0", "the mutation really did produce a zero-total run"
    )
    gate.assert_contains(
        result.combined, "executed ZERO tests", "the failure must say what went wrong"
    )
    gate.assert_contains(
        result.combined, "Refusing to report success", "the failure must say why it refuses"
    )

    # Mutation 2: the same loosened parser with the backstop removed, i.e. the code exactly as it stood on 2026-08-07. It must report the incident's
    # signature -- "total 0" with EXIT=0. Without this the case above would not
    # prove that the backstop is what makes the difference.
    without = mutate(gate, tmp_path / "without-backstop.sh", drop_backstop=True)
    result = run_target(without, "--dry-run", "--method", "bogus", "--version", "1.2.17")
    gate.assert_exit_code(
        0, result.rc, "the OLD summary must pass a zero-total run, or this test proves nothing"
    )
    gate.assert_contains(
        result.combined, "0 passed, 0 failed, 0 skipped (total 0)", "the reproduced signature"
    )
    gate.log_pass("the zero-total backstop fires, and the old summary really did not")
