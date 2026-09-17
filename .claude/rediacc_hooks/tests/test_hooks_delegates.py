"""The sub-suites this harness RUNS, and the floor under each fold.

WHY DELEGATE AT ALL. Every case in hookcases.py is one JSON payload on one guard's
stdin. These programs are not that shape: they need a fake task directory, a planted
transcript, a real halted rebase. Delegating keeps both readable, and running them
from here is what makes them REACHABLE -- a test nothing invokes is dead code, and
`check_test_file_orphans.py` exists because exactly that happened to
test-teammate-idle.py.

THE FLOOR IS THE POINT, NOT THE EXIT CODE. `python3 wl_reggate.py --selftest` also
exits 0 -- not because it has a vacuous selftest but because it has NO selftest and
no __main__ at all, so running a library module as a script does nothing and
succeeds. A wiring that trusted the exit code would have reported that as a passing
suite. An unrun suite, a vacuous one, and a module that ignores its argv are
indistinguishable from outside unless you count what came back.

FLOORS SIT BELOW THE MEASURED COUNT, NEVER AT IT. A floor equal to today's count
turns every added control into a failure, which teaches people to lower the floor,
and a floor someone edits routinely is not a floor. What it has to catch is a
selftest that STOPPED RUNNING: zero, or a handful left after a module half-broke.

TWO MODULES CARRIED SELFTESTS THAT NOTHING RAN, found 2026-08-26: wl_git.py and
wl_admit.py, 18 controls each, invoked by no suite and no gate. Sharpest detail:
test-worklist-v5.sh exempts `--git` from its verb-coverage table and CITES "18
controls in wl_git.py --selftest" as the justification. Coverage was being claimed
from a suite that never executed.
"""

import re
import subprocess

import pytest

from rediacc_hooks.tests import hookcases, hooklabels

HOOKS = hookcases.HOOKS

# A sub-suite may take minutes (test-worklist-v5.sh drives ~940 cases), so the bound
# is generous; it exists so a hung child is a named failure rather than a job that
# GitHub eventually cancels with no artefact at all.
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
    # The resource recorder runs at the exit of EVERY hook process, so its selftest
    # belongs beside the others; it carries the leak plant (a secret-shaped argv token
    # must never reach a record) and the two silence controls.
    ("stop/wl_resprofile.py", ["--selftest"], PASS_LOOSE, 1, "stop/wl_resprofile.py", "control"),
    # The forkless /proc tree sampler: spawns a known tree and asserts shape, symbolic wchan, and that a planted secret-shaped argv never reaches a sample.
    ("stop/wl_ressample.py", ["--selftest"], PASS_LOOSE, 1, "stop/wl_ressample.py", "control"),
    # The structural deriver: E1/E4/E5/E6 fire-and-silence pairs, the D1 wall-only dilation control, the D2 no-duration-literal self-scan, and the admission floor.
    ("stop/wl_profile.py", ["--selftest"], PASS_LOOSE, 1, "stop/wl_profile.py", "control"),
]

# ONE PASS EACH, on exit status, and that is deliberate rather than lazy. These print in several different formats ("73 checks, 0 failures", "✓ ... 15 blocked, 13 allowed", "FAILURES: 0"), so counting their assertions here would couple this file to that many output shapes and go quietly to zero the moment one reworded a line.
# The child owns its assertions; this asserts that the child RAN and SUCCEEDED.
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

# The two bash sub-suites. The stop gate carries its own because its cases need
# fixtures rather than the single-JSON-on-stdin shape every guard case uses; the
# report-inbox suite covers the whole cross-session waiter/nudge mechanism and this aggregate runner did NOT run it until a sub-agent found 125 invisible cases in it. relative | the npm key that also reaches it, or None when the harness is its only route. NOT EXECUTED HERE -- see test_a_delegated_bash_suite_is_reachable.
BASH_SUITES = [
    ("stop/test-worklist-v5.sh", "check:ci-hook-worklist-suite"),
    ("stop/test-report-inbox.sh", None),
]

# The aggregate that really runs both, itself gated by `gate-test:claude-hooks`.
AGGREGATE = HOOKS / "test-hooks.sh"
PACKAGE_JSON = HOOKS.parent.parent / "package.json"


def bash_suite_problem(relative: str, npm_key, aggregate_source: str, pkg_source: str):
    """None when the suite is genuinely reachable, else the ONE link that broke.

    Returns the reason rather than raising so the control can observe a verdict.
    """
    if not (HOOKS / relative).is_file():
        return "FAIL[%s]: the suite file does not exist, so nothing runs it." % relative
    if relative not in aggregate_source:
        return (
            "FAIL[%s]: test-hooks.sh no longer invokes it, so this suite now runs "
            "NOWHERE -- this module stopped running it on the strength of that "
            "invocation." % relative
        )
    if npm_key is not None:
        matching = [ln for ln in pkg_source.splitlines() if '"%s":' % npm_key in ln]
        if not matching:
            return 'FAIL[%s]: package.json has no "%s" script.' % (relative, npm_key)
        if relative.rsplit("/", 1)[-1] not in "\n".join(matching):
            return 'FAIL[%s]: "%s" no longer runs it.' % (relative, npm_key)
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


@pytest.mark.parametrize(("relative", "npm_key"), BASH_SUITES, ids=[row[0] for row in BASH_SUITES])
def test_a_delegated_bash_suite_is_reachable(relative, npm_key):
    """Reachability is asserted, NOT re-established by running the suite again.

    This module's rationale for executing these was reachability -- "a test nothing
    invokes is dead code". `test-hooks.sh` invokes both itself (lines 2698 and 2743),
    and that harness is executed by the registered gate `gate-test:claude-hooks`. So
    running them here re-did work already done: measured 866.78s and 56.16s, against a
    harness that is 931.14s in total and was being billed three times inside one
    1200s-capped job.

    The reachability CLAIM still has to hold, and a broken one is invisible -- a suite
    the aggregate stopped invoking looks exactly like a suite that ran and passed. So
    the claim is asserted directly and nothing is executed.
    """
    problem = bash_suite_problem(
        relative,
        npm_key,
        AGGREGATE.read_text(encoding="utf-8"),
        PACKAGE_JSON.read_text(encoding="utf-8"),
    )
    hooklabels.record(0, "%s: reachable via test-hooks.sh" % relative, ok=problem is None)
    assert problem is None, problem


def test_the_reachability_assertion_fires_when_the_aggregate_drops_a_suite():
    """CONTROL. A reachability claim that cannot fail is not a claim.

    Driven against an aggregate source with the suite's invocation stripped. Operates
    on a STRING, never on the real file, so no tracked file is written (T-12).
    """
    relative, npm_key = BASH_SUITES[0]
    real = AGGREGATE.read_text(encoding="utf-8")
    assert relative in real, "control could not strip what is not there"
    doctored = real.replace(relative, "stop/SOME-OTHER-SUITE.sh")

    problem = bash_suite_problem(
        relative, npm_key, doctored, PACKAGE_JSON.read_text(encoding="utf-8")
    )
    assert problem is not None, (
        "CONTROL FAILED: reachability PASSED against an aggregate that no longer "
        "invokes %s, so it cannot detect the disappearance it exists to detect." % relative
    )
    assert "runs\nNOWHERE" in problem.replace(" ", "\n") or "NOWHERE" in problem, problem
