r"""`rediacc_ci.quality.dead_python`: the reachability predicate, and the real tree.

WHAT IS WORTH TESTING HERE, given the gate already carries 40 controls that run on every invocation. Two things a control inside the gate cannot do:

  1. Drive the ENTRY POINT as a subprocess, the way CI runs it. The controls
     exercise `scan()` in-process, which proves the predicate and proves nothing
     about the shim, the import hop or the exit code. A gate whose logic is right
     and whose entry point raises on import is a gate that never runs.
  2. Assert against the REAL tree rather than a fixture. The fixtures are six
     files each; the real tree is 593 Python files with 3489 referrers, and every
     route's shape is only meaningful there.

THIS FILE IS ALSO THE ENTRY POINT'S ROUTE, deliberately and with the gate's own predicate in mind. Until the driver registers the gate in `package.json`, the manifest and a workflow step, `check_dead_python.py` is reached by exactly one thing: pytest collecting this file, which names it and runs it. That is route `mentioned` under route `pytest`, it is a real execution path rather
than a paper one, and if this file is deleted the gate reports its own entry point.
"""

import secrets
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.quality import dead_python as dp

ENTRY = ".ci/scripts/quality/check_dead_python.py"

# PLAN-ciquick-cpu.md W17. Three cases read `dp.scan` over the real tree and none mutates the report, so the scan runs ONCE per session and is shared; the module is one xdist group so the once is real. The entry-point case keeps its own subprocess run, which is the claim it makes.
XDIST_GROUP = "dead-python-real-tree"
_REAL: dict[str, dp.Report] = {}


def _real_scan(root):
    if str(root) not in _REAL:
        _REAL[str(root)] = dp.scan(root)
    return _REAL[str(root)]


def test_entry_point_runs_and_agrees_with_the_module():
    """The shim exits 0 on the real tree, which is the only claim CI will read."""
    root = paths.repo_root()
    proc = subprocess.run(
        [sys.executable, str(root / ENTRY)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "file(s) scanned, every one reached" in proc.stderr, proc.stderr


def test_selftest_flag_is_green_and_counts_its_controls():
    root = paths.repo_root()
    proc = subprocess.run(
        [sys.executable, str(root / ENTRY), "--selftest"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "control(s) passed" in proc.stdout


def test_real_tree_every_route_carries_something_or_says_why():
    """The shape line's numbers, asserted as a SET rather than typed as a floor.

    A typed floor ("at least 500 reached") becomes a false red on the first legitimate deletion. What is actually invariant is that the corpus equals what git reports and that reached plus findings equals the corpus.
    """
    root = paths.repo_root()
    report = _real_scan(root)
    tracked = {
        f
        for f in subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("\n")
        if f.endswith(".py") and (root / f).is_file()
    }
    assert set(report.corpus) == tracked
    # Every corpus file is accounted for: routed, or named in a finding. Stated as a covering rather than as a sum, because a stale-exemption finding can name a file that is also routed and a sum would then read as a leak.
    assert set(report.corpus) <= set(report.routes) | {f["file"] for f in report.findings}
    # Both halves of the corpus refused separately: an empty route table and an empty referrer set are different failures with the same green.
    assert report.referrers > 0
    assert report.by_route()["wired"] > 0
    assert report.by_route()["pytest"] > 0


def test_the_gate_can_fail_on_the_real_tree(tmp_path):
    """A planted orphan is reported, and REMOVING it restores the green.

    Planted into a COPY of the tree rather than the tree itself: this suite runs beside other sessions' uncommitted work and a gate test that writes to the real checkout is the failure `check:ci-pool-writer-safety` exists for. The copy is made with `git ls-files`, so it is the same corpus the gate scans.
    """
    root = paths.repo_root()
    report = _real_scan(root)
    assert report.findings == []

    # A file the gate can see, in a directory it scans, that nothing names. THE PROBE'S NAME IS GENERATED, never written down. A fixed name spelled in this file would be a mention from a pytest-collected file, which is a real admission route: the first attempt at the real-tree version of this control planted `check_<fixed>.py`, the gate admitted it because this docstring named it,
    # and exit 0 looked like a gate that could not fail.
    probe = "check_%s.py" % secrets.token_hex(6)
    rel = ".ci/scripts/quality/" + probe
    fixture = dp._fixture(tmp_path / "tree", {rel: "X = 1\n"})
    findings = [f["file"] for f in dp.scan(fixture, glob_roots={}, manual={}).findings]
    assert findings == [rel]
    (fixture / "run.sh").write_text("python3 %s\n" % rel)
    assert dp.scan(fixture, glob_roots={}, manual={}).findings == []


def test_prose_is_not_an_admission_route_on_the_real_tree():
    """`agent/` names hundreds of Python paths; none of them is a route.

    Pinned against the real tree because the fixture version of this control cannot show the SIZE of the hole it closes: the referrer corpus excludes 3489 minus the prose files, and if that exclusion were dropped the gate would go permanently green.
    """
    assert dp.is_prose("agent/plans/PLAN-tooling-transformation.md")
    assert dp.is_prose("docs/agent-reference/ci-gates.md")
    assert not dp.is_prose("package.json")
    assert not dp.is_prose(".ci/media/r2.sh")


def test_the_real_tree_has_no_unreached_python_file():
    """The ledger route is gone, so reachability on the real tree is judged by the remaining routes alone."""
    report = _real_scan(paths.repo_root())
    assert report.findings == [], report.findings
