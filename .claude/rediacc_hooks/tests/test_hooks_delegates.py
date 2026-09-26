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

import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest
from rediacc_ci import runtmp

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
# DISCOVERED, NOT HAND-MAINTAINED, since 2026-09-22. A hand-maintained list needs a second commit to reach a new script, and the gap is silent: `test-block_push_to_protected_branch.py` was committed, passed its own standalone run, and sat unreached by this module for a full session before anyone noticed. `COUNTED` above stays explicit on purpose -- its counter regex and floor
# are genuine per-module metadata a filename cannot supply -- but TAILED's contract is uniform (no argv, exit 0, non-empty output), which is exactly what a glob can enforce without a human remembering to.
_TAILED_ROOTS = (
    HOOKS / "context",
    HOOKS / "stop",
    HOOKS.parent / "rediacc_hooks" / "guards",
)


def _discover_tailed(roots=_TAILED_ROOTS) -> list[str]:
    """Every `test-*.py` standalone script under the hook trees, minus whatever `COUNTED` already claims with its own argv/counter/floor."""
    counted_names = {pathlib.Path(row[0]).name for row in COUNTED}
    found = []
    for root in roots:
        for path in sorted(root.glob("test-*.py")):
            if path.name in counted_names:
                continue
            found.append(pathlib.Path(os.path.relpath(path, HOOKS)).as_posix())
    return found


TAILED = _discover_tailed()
# Measured 2026-09-22: 16 (9 guards + 6 stop/ + 1 context/), against COUNTED's 4 -- 20 total hyphenated scripts. A floor well below that, re-measured the same way COUNTED's floors are, catches a renamed or emptied root rather than pinning today's exact count.
TAILED_FLOOR = 14

# THE TWO BASH SUB-SUITES ARE GONE, ported to pytest under this same directory: `stop/test-worklist-v5.sh` (26 case files, 944 assertions) and `stop/test-report-inbox.sh` (164 assertions) both drove PYTHON through a shell fixture layer, and the ports keep the same subprocess calls and the same assertions with `wlfix.py` in place of `_harness.sh`.
#
# WHAT REPLACES THEM HERE IS THE SAME CLAIM ABOUT A DIFFERENT ROUTE. `check:ci-pytest` collects them, because `.claude/rediacc_hooks/tests` is a pyproject `testpaths` root. That delegation is invisible when it breaks: a renamed or emptied root looks exactly like a root that ran and passed. So each link is asserted directly, and the control below strips each one.
#
# THE AGGREGATE LINK IS GONE, and its removal is the retirement of `.claude/hooks/test-hooks.sh` rather than a weakening. That link asserted that the bash harness still NAMED this root, which was only ever a proxy for "something outside pytest still watches the delegation". With the harness deleted the proxy has no subject: a string that no file contains cannot be checked, and a
# link kept against a deleted file is the can't-fail shape this module exists to refuse. What it was standing in for -- that the root is collectable and still holds the ported modules -- is asserted directly by the two links that remain, and neither of those was ever mediated by the harness.
PORT_ROOT = "rediacc_hooks/tests"
PORT_FIXTURE = "wlfix.py"
PORT_MODULE_FLOOR = 20

PACKAGE_JSON = HOOKS.parent.parent / "package.json"
PYPROJECT = HOOKS.parent.parent / "pyproject.toml"
FIXTURE = pathlib.Path(__file__).resolve().parent / PORT_FIXTURE


def port_delegation_problem(fixture_present: bool, pyproject_source: str, module_count: int):
    """None when the ported suite is genuinely reachable, else the ONE link that broke.

    Returns the reason rather than raising so the control can observe a verdict.
    """
    if PORT_ROOT not in pyproject_source:
        return (
            "FAIL[%s]: the directory is not a pyproject testpaths root, so check:ci-pytest "
            "no longer collects the ported Stop-hook suite and it runs NOWHERE." % PORT_ROOT
        )
    if not fixture_present:
        return (
            "FAIL[%s]: %s is gone, so every ported case has lost its fixture layer and the "
            "modules that import it collect as errors rather than running NOWHERE quietly."
            % (PORT_ROOT, PORT_FIXTURE)
        )
    if module_count < PORT_MODULE_FLOOR:
        return (
            "FAIL[%s]: only %d test_wl_*.py module(s) present against a floor of %d; the port "
            "had 27, so most of the suite runs NOWHERE."
            % (PORT_ROOT, module_count, PORT_MODULE_FLOOR)
        )
    return None


# Fixed-name caches that node and tsx keep under TMPDIR (`node-compile-cache`, `tsx-<uid>`), created by a suite that shells out to a tsx gate. One per user, reused by every later run rather than added to, so in the real /tmp they cannot accumulate; they are exempt by exact shape, never by prefix, and anything else left behind still fails.
_SHARED_TOOL_CACHE = re.compile(r"^(node-compile-cache|tsx-[0-9]+)$")


# EVERY SUITE RUNS WITH ITS OWN EMPTY TMPDIR, AND LEAVING ANYTHING IN IT IS A FAILURE. /tmp here is a tmpfs capped at 1,048,576 inodes, and on 2026-09-24 the cap was hit: every Bash and Write call on the machine failed with ENOSPC for hours, and the cleanup removed 2,576 leaked `tmp*` directories, mostly git fixture repos made at module scope by these standalone suites and never deleted. pytest's own `tmp_path_retention_policy` cannot see them, because they are not pytest tests. Python's `tempfile` honours `TMPDIR`, so pointing it at a fresh directory per suite catches any `mkdtemp`/`TemporaryDirectory` leak in the class, and the directory is removed afterwards whatever the verdict.
def _run(relative: str, tail: list[str]) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run one suite under a private TMPDIR; return its result and the entries it left behind."""
    path = HOOKS / relative
    argv = ["bash", str(path)] if path.suffix == ".sh" else ["python3", str(path), *tail]
    # Under one pid-stamped run dir, because the `finally` below does not run when pytest itself is killed on its timeout; the next run's sweep reclaims it then.
    scratch = tempfile.mkdtemp(prefix="suite-", dir=runtmp.shared("hook-suite-tmpdir-"))
    try:
        env = dict(os.environ, TMPDIR=scratch)
        done = subprocess.run(
            argv,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=SUITE_TIMEOUT_S,
            check=False,
            env=env,
        )
        leftovers = sorted(n for n in os.listdir(scratch) if not _SHARED_TOOL_CACHE.match(n))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return done, leftovers


def _assert_no_leak(name: str, leftovers: list[str]) -> None:
    assert not leftovers, (
        "%s left %d entr(y/ies) in its private TMPDIR after exiting: %s. A standalone suite "
        "must delete every temp directory it creates (try/finally or atexit + rmtree); leaked "
        "fixture repos are what filled the /tmp inode cap on 2026-09-24."
        % (name, len(leftovers), ", ".join(leftovers[:20]))
    )


def _folded(relative: str, tail: list[str], counter, floor: int, name: str, unit: str) -> None:
    path = HOOKS / relative
    assert path.is_file(), "%s missing" % relative
    done, leftovers = _run(relative, tail)
    text = (done.stdout + done.stderr).decode("utf-8", "replace")
    assert done.returncode == 0, "%s exited %d:\n%s" % (name, done.returncode, text[-2000:])
    found = _count(counter, text)
    ok = found >= floor and found > 0 and not leftovers
    hooklabels.record(0, "%s: %d %s(s) passed" % (name, found, unit), ok=ok)
    assert found > 0, (
        "%s exited 0 but reported NO %ss. A selftest that prints nothing and exits 0 "
        "is a vacuous green." % (name, unit)
    )
    assert found >= floor, "%s: %d %s(s), expected >= %d" % (name, found, unit, floor)
    _assert_no_leak(name, leftovers)


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
    done, leftovers = _run(relative, [])
    text = (done.stdout + done.stderr).decode("utf-8", "replace")
    ok = done.returncode == 0 and text.strip() != "" and not leftovers
    last = text.rstrip("\n").split("\n")[-1] if text.strip() else ""
    hooklabels.record(0, "%s: %s" % (relative, last[:90]), ok=ok)
    assert done.returncode == 0, "%s exited %d:\n%s" % (relative, done.returncode, text[-2000:])
    assert text.strip() != "", "%s printed nothing, which is what a stub returns" % relative
    _assert_no_leak(relative, leftovers)


def test_tailed_discovery_meets_its_floor():
    """The glob replacing a hand-maintained list is a claim, not a formality: a renamed root or a broken glob would silently shrink `TAILED` to whatever it still finds, and a parametrized suite over a short list just runs fewer tests rather than failing loudly."""
    assert len(TAILED) >= TAILED_FLOOR, (
        "only %d test-*.py script(s) discovered under the hook trees, expected >= %d; "
        "a root may have been renamed, or the glob broken" % (len(TAILED), TAILED_FLOOR)
    )


def test_tailed_discovery_control_an_emptied_root_finds_nothing():
    """CONTROL, on an explicit empty root tuple rather than a renamed real directory (T-12): proves the floor check above would have caught a broken discovery root instead of passing vacuously over zero scripts."""
    broken = _discover_tailed(roots=())
    assert broken == [], "control setup: an empty roots tuple found %r" % (broken,)
    assert len(broken) < TAILED_FLOOR, (
        "CONTROL FAILED: an emptied root's result still met the floor, so the floor check "
        "cannot detect the disappearance it exists to detect"
    )


def ported_module_count() -> int:
    return len(list(pathlib.Path(__file__).resolve().parent.glob("test_wl_*.py")))


def test_the_ported_stop_hook_suite_is_reachable():
    """Reachability is asserted, NOT re-established by running the suite again.

    This module's rationale for executing the two retired bash suites was reachability, since a test nothing invokes is dead code. Running them here re-did work already done: measured 866.78s and 56.16s, against a harness that is 931.14s in total and was being billed three times inside one 1200s-capped job. The ports inherit the rationale and the restraint: check:ci-pytest
    collects them, and re-running them from here would reintroduce exactly that doubling.

    The reachability CLAIM still has to hold, and a broken one is invisible: a root the collector stopped seeing looks exactly like a root that ran and passed. So the claim is asserted directly and nothing is executed.
    """
    problem = port_delegation_problem(
        FIXTURE.is_file(),
        PYPROJECT.read_text(encoding="utf-8"),
        ported_module_count(),
    )
    hooklabels.record(0, "%s: reachable via check:ci-pytest" % PORT_ROOT, ok=problem is None)
    assert problem is None, problem


def test_the_reachability_assertion_fires_on_each_broken_link():
    """CONTROL. A reachability claim that cannot fail is not a claim.

    Each of the three links is stripped in turn, on STRINGS and a COUNT, never on the real files, so no tracked file is written (T-12). All three are driven rather than one, because a predicate can be right about the link its author tested and blind to the other two.
    """
    pyproject = PYPROJECT.read_text(encoding="utf-8")
    assert PORT_ROOT in pyproject, "control could not strip what is not there"
    assert FIXTURE.is_file(), "control could not strip a fixture that is already absent"

    for label, args in (
        ("testpaths", (True, pyproject.replace(PORT_ROOT, "SOME/OTHER/ROOT"), 27)),
        ("fixture", (False, pyproject, 27)),
        ("floor", (True, pyproject, 0)),
    ):
        problem = port_delegation_problem(*args)
        assert problem is not None, (
            "CONTROL FAILED: reachability PASSED with the %s link broken, so it cannot detect "
            "the disappearance it exists to detect." % label
        )
        assert "NOWHERE" in problem, problem
