"""The sub-suites this harness RUNS, and the floor under each fold.

WHY DELEGATE AT ALL. Every case in hookcases.py is one JSON payload on one guard's stdin. These programs are not that shape: they need a fake task directory, a planted transcript, a real halted rebase. Delegating keeps both readable, and running them
from here is what makes them REACHABLE -- a test nothing invokes is dead code, and
`check_test_file_orphans.py` exists because exactly that happened to test-teammate-idle.py.

THE FLOOR IS THE POINT, NOT THE EXIT CODE. `python3 wl_reggate.py --selftest` also exits 0 -- not because it has a vacuous selftest but because it has NO selftest and no __main__ at all, so running a library module as a script does nothing and succeeds. A wiring that trusted the exit code would have reported that as a passing suite. An unrun suite, a vacuous one, and a module that
ignores its argv are indistinguishable from outside unless you count what came back.

FLOORS SIT BELOW THE MEASURED COUNT, NEVER AT IT. A floor equal to today's count turns every added control into a failure, which teaches people to lower the floor, and a floor someone edits routinely is not a floor. What it has to catch is a selftest that STOPPED RUNNING: zero, or a handful left after a module half-broke.

TWO MODULES CARRIED SELFTESTS THAT NOTHING RAN, found 2026-08-26: wl_git.py and wl_admit.py, 18 controls each, invoked by no suite and no gate. Sharpest detail: test-worklist-v5.sh exempts `--git` from its verb-coverage table and CITES "18 controls in wl_git.py --selftest" as the justification. Coverage was being claimed
from a suite that never executed.
"""

import pathlib
import re
import subprocess

import pytest

from rediacc_hooks.tests import hookcases, hooklabels

HOOKS = hookcases.HOOKS

# A sub-suite may take minutes (test-worklist-v5.sh drives ~940 cases), so the bound is generous; it exists so a hung child is a named failure rather than a job that GitHub eventually cancels with no artefact at all.
SUITE_TIMEOUT_S = 1800

# `^ PASS ` -- the shape the wl_* selftests print.
PASS_2SP = re.compile(r"^  PASS ", re.MULTILINE)
# ` PASS: ` -- test-teammate-idle.py's shape, and the v5 harness's.
PASS_COLON = re.compile(r"^\s*PASS: ", re.MULTILINE)
# Leading-whitespace PASS, the resource modules' shape.
PASS_LOOSE = re.compile(r"^\s*PASS\s", re.MULTILINE)
# ` ok ` -- test-report-inbox.sh's shape. Copying the v5 counter verbatim made it count 0 and still report "ok ... 0 case(s) passed": a green that verified nothing, which is the exact defect the zero-count refusal was added to close.
OK_WORD = re.compile(r"^\s*ok\s", re.MULTILINE)
# A trailing summary line, which two modules print instead of per-case lines.
SUMMARY_N = re.compile(r"^([0-9]+) control\(s\) passed$", re.MULTILINE)


def _count(pattern, text: str) -> int:
    if pattern is SUMMARY_N:
        found = pattern.findall(text)
        return int(found[-1]) if found else 0
    return len(pattern.findall(text))


# (relative path, argv tail, counter, floor, label template, unit)
#
# The FLOOR column is a minimum, re-measured when it drifts far below the real count: wl_git was still floored at 18 when it had 63, so two thirds of its controls could have vanished silently.
COUNTED = [
    ("stop/wl_git.py", ["--selftest"], PASS_2SP, 55, "stop/wl_git.py --selftest", "control"),
    ("stop/wl_admit.py", ["--selftest"], PASS_2SP, 16, "stop/wl_admit.py --selftest", "control"),
    (
        "stop/wl_roundlog.py",
        ["--selftest"],
        PASS_2SP,
        12,
        "stop/wl_roundlog.py --selftest",
        "control",
    ),
    (
        "stop/wl_planfid.py",
        ["--selftest"],
        PASS_2SP,
        50,
        "stop/wl_planfid.py --selftest",
        "control",
    ),
    ("stop/wl_ci.py", ["--selftest"], PASS_2SP, 15, "stop/wl_ci.py --selftest", "control"),
    ("stop/test-teammate-idle.py", [], PASS_COLON, 1, "stop/test-teammate-idle.py", "control"),
    ("stop/test-adhoc-watch.py", [], SUMMARY_N, 1, "stop/test-adhoc-watch.py", "control"),
    (
        "stop/test-plan-status-parse.py",
        [],
        SUMMARY_N,
        1,
        "stop/test-plan-status-parse.py",
        "control",
    ),
    ("stop/test-judge-schema.py", [], SUMMARY_N, 1, "stop/test-judge-schema.py", "control"),
    # The resource recorder runs at the exit of EVERY hook process, so its selftest belongs beside the others; it carries the leak plant (a secret-shaped argv token must never reach a record) and the two silence controls.
    ("stop/wl_resprofile.py", ["--selftest"], PASS_LOOSE, 1, "stop/wl_resprofile.py", "control"),
    # The forkless /proc tree sampler: spawns a known tree and asserts shape, symbolic wchan, and that a planted secret-shaped argv never reaches a sample.
    ("stop/wl_ressample.py", ["--selftest"], PASS_LOOSE, 1, "stop/wl_ressample.py", "control"),
    # The structural deriver: E1/E4/E5/E6 fire-and-silence pairs, the D1 wall-only dilation control, the D2 no-duration-literal self-scan, and the admission floor.
    ("stop/wl_profile.py", ["--selftest"], PASS_LOOSE, 1, "stop/wl_profile.py", "control"),
]

# ONE PASS EACH, on exit status, and that is deliberate rather than lazy. These print in several different formats ("73 checks, 0 failures", "✓ ... 15 blocked, 13 allowed", "FAILURES: 0"), so counting their assertions here would couple this file to that many output shapes and go quietly to zero the moment one reworded a line. The child owns its assertions; this asserts that the
# child RAN and SUCCEEDED.
#
# Empty output still fails: a suite that prints nothing has not demonstrated it did anything, and exit 0 alone is what a stub returns.
#
# Each of these was committed, each passes, and each ran only when somebody invoked it by hand until 2026-08-23.
TAILED = [
    "context/test-context-bands.py",
    "../rediacc_hooks/guards/test-block_destructive_git_restore.py",
    "../rediacc_hooks/guards/test-block_git_amend.py",
    "../rediacc_hooks/guards/test-block_unverified_push.py",
    "../rediacc_hooks/guards/test-block_host_toolchain_run.py",
    "stop/test-completion-evidence.py",
    "stop/test-always-tier.py",
    "stop/test-planfile.py",
    "stop/test-planindex.py",
    "stop/test-planrec.py",
    "stop/test-reggate-ledger.py",
]

# THE TWO BASH SUB-SUITES ARE GONE, ported to pytest under this same directory: `stop/test-worklist-v5.sh` (26 case files, 944 assertions) and `stop/test-report-inbox.sh` (164 assertions) both drove PYTHON through a shell fixture layer, and the ports keep the same subprocess calls and the same assertions with `wlfix.py` in place of `_harness.sh`.
#
# WHAT REPLACES THEM HERE IS THE SAME CLAIM ABOUT A DIFFERENT ROUTE. The aggregate no longer runs them; `check:ci-pytest` collects them, because `.claude/rediacc_hooks/tests` is a pyproject `testpaths` root. That delegation is invisible when it breaks: a renamed or emptied root looks exactly like a root that ran and passed. So the three links are asserted directly, and the
# control below strips each one.
PORT_ROOT = "rediacc_hooks/tests"
PORT_FIXTURE = "wlfix.py"
PORT_MODULE_FLOOR = 20

# The aggregate that really runs both, itself gated by `gate-test:claude-hooks`.
AGGREGATE = HOOKS / "test-hooks.sh"
PACKAGE_JSON = HOOKS.parent.parent / "package.json"
PYPROJECT = HOOKS.parent.parent / "pyproject.toml"


def port_delegation_problem(aggregate_source: str, pyproject_source: str, module_count: int):
    """None when the ported suite is genuinely reachable, else the ONE link that broke.

    Returns the reason rather than raising so the control can observe a verdict.
    """
    if PORT_ROOT not in pyproject_source:
        return (
            "FAIL[%s]: the directory is not a pyproject testpaths root, so check:ci-pytest "
            "no longer collects the ported Stop-hook suite and it runs NOWHERE." % PORT_ROOT
        )
    if PORT_ROOT not in aggregate_source or PORT_FIXTURE not in aggregate_source:
        return (
            "FAIL[%s]: test-hooks.sh no longer names the ported suite, so the aggregate has "
            "stopped checking that the delegation is live and a broken one runs NOWHERE."
            % PORT_ROOT
        )
    if module_count < PORT_MODULE_FLOOR:
        return (
            "FAIL[%s]: only %d test_wl_*.py module(s) present against a floor of %d; the port "
            "had 27, so most of the suite runs NOWHERE."
            % (PORT_ROOT, module_count, PORT_MODULE_FLOOR)
        )
    return None


def _run(relative: str, tail: list[str]) -> subprocess.CompletedProcess:
    path = HOOKS / relative
    argv = ["bash", str(path)] if path.suffix == ".sh" else ["python3", str(path), *tail]
    return subprocess.run(
        argv,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=SUITE_TIMEOUT_S,
        check=False,
    )


def _folded(relative: str, tail: list[str], counter, floor: int, name: str, unit: str) -> None:
    path = HOOKS / relative
    assert path.is_file(), "%s missing" % relative
    done = _run(relative, tail)
    text = (done.stdout + done.stderr).decode("utf-8", "replace")
    assert done.returncode == 0, "%s exited %d:\n%s" % (name, done.returncode, text[-2000:])
    found = _count(counter, text)
    ok = found >= floor and found > 0
    hooklabels.record(0, "%s: %d %s(s) passed" % (name, found, unit), ok=ok)
    assert found > 0, (
        "%s exited 0 but reported NO %ss. A selftest that prints nothing and exits 0 "
        "is a vacuous green." % (name, unit)
    )
    assert found >= floor, "%s: %d %s(s), expected >= %d" % (name, found, unit, floor)


@pytest.mark.xdist_group("hooks-delegates")
@pytest.mark.parametrize(
    ("relative", "tail", "counter", "floor", "name", "unit"),
    COUNTED,
    ids=[row[4] for row in COUNTED],
)
def test_a_counted_selftest_is_folded_with_a_floor(relative, tail, counter, floor, name, unit):
    _folded(relative, tail, counter, floor, name, unit)


@pytest.mark.xdist_group("hooks-delegates")
@pytest.mark.parametrize("relative", TAILED)
def test_an_orphan_control_suite_runs_and_says_something(relative):
    path = HOOKS / relative
    assert path.is_file(), "%s missing" % relative
    done = _run(relative, [])
    text = (done.stdout + done.stderr).decode("utf-8", "replace")
    ok = done.returncode == 0 and text.strip() != ""
    last = text.rstrip("\n").split("\n")[-1] if text.strip() else ""
    hooklabels.record(0, "%s: %s" % (relative, last[:90]), ok=ok)
    assert done.returncode == 0, "%s exited %d:\n%s" % (relative, done.returncode, text[-2000:])
    assert text.strip() != "", "%s printed nothing, which is what a stub returns" % relative


def ported_module_count() -> int:
    return len(list(pathlib.Path(__file__).resolve().parent.glob("test_wl_*.py")))


def test_the_ported_stop_hook_suite_is_reachable():
    """Reachability is asserted, NOT re-established by running the suite again.

    This module's rationale for executing the two retired bash suites was reachability, since a test nothing invokes is dead code. Running them here re-did work already done: measured 866.78s and 56.16s, against a harness that is 931.14s in total and was being billed three times inside one 1200s-capped job. The ports inherit the rationale and the restraint: check:ci-pytest
    collects them, and re-running them from here would reintroduce exactly that doubling.

    The reachability CLAIM still has to hold, and a broken one is invisible: a root the collector stopped seeing looks exactly like a root that ran and passed. So the claim is asserted directly and nothing is executed.
    """
    problem = port_delegation_problem(
        AGGREGATE.read_text(encoding="utf-8"),
        PYPROJECT.read_text(encoding="utf-8"),
        ported_module_count(),
    )
    hooklabels.record(0, "%s: reachable via check:ci-pytest" % PORT_ROOT, ok=problem is None)
    assert problem is None, problem


def test_the_reachability_assertion_fires_on_each_broken_link():
    """CONTROL. A reachability claim that cannot fail is not a claim.

    Each of the three links is stripped in turn, on STRINGS and a COUNT, never on the real files, so no tracked file is written (T-12). All three are driven rather than one, because a predicate can be right about the link its author tested and blind to the other two.
    """
    aggregate = AGGREGATE.read_text(encoding="utf-8")
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    assert PORT_ROOT in aggregate, "control could not strip what is not there"
    assert PORT_ROOT in pyproject, "control could not strip what is not there"

    for label, args in (
        ("testpaths", (aggregate, pyproject.replace(PORT_ROOT, "SOME/OTHER/ROOT"), 27)),
        ("aggregate", (aggregate.replace(PORT_ROOT, "SOME/OTHER/ROOT"), pyproject, 27)),
        ("floor", (aggregate, pyproject, 0)),
    ):
        problem = port_delegation_problem(*args)
        assert problem is not None, (
            "CONTROL FAILED: reachability PASSED with the %s link broken, so it cannot detect "
            "the disappearance it exists to detect." % label
        )
        assert "NOWHERE" in problem, problem
