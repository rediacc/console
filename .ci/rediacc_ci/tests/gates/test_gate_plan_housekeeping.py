r"""Port of `.ci/scripts/test/gates/test-plan-housekeeping.sh`, retired in W7 P5.

Drives the REAL `.ci/scripts/quality/check_plan_housekeeping.py` against fixture git repositories with BACKDATED commits.

THIS FILE IS THE ENTIRE JUSTIFICATION FOR LANDING THAT GATE. Measured over all 4001 reachable commits: ZERO plan files fail at 33 days today, and none can -- `agent/` only became a tracked directory on 2026-08-18, so nothing under it is older than 15 days. A gate with no live offenders and no fixture proves exactly nothing; every check mark it prints would be indistinguishable from
a broken scan.

The dates are set with `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE`, the same technique `test_gate_age_check.py` already uses. `PLAN_HK_ROOT` re-points the gate at each fixture, and the last case proves that override is not an escape hatch.

The two cases no other gate in this repo has are the shallow-clone pair: a `git clone --depth 1` of the fixture must REFUSE under CI and must SKIP LOUDLY without it. That is the defect the gate was built around -- `git log` on a shallow clone answers with the graft date and would make the whole check pass vacuously.

NOTE ON THE OTHER TWIN. `.ci/scripts/quality/check-plan-housekeeping.sh` (bash) still exists on disk, but it is NOT this module's subject: it is the differential fixture `.ci/rediacc_ci/tests/test_quality_plan_housekeeping.py` compares the port against, and that comparison is a separate concern from the end-to-end fixture behaviour proven here. This module's `GATE` was already the
Python entry point in the retired bash twin, so this port changes only the harness language, not the subject.
"""

import atexit
import datetime
import pathlib
import shutil
import tempfile

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_plan_housekeeping.py")
CFG = paths.from_root(".ci", "config", "plan-lifecycle.json")

# The filler corpus is IDENTICAL in every case -- 32 plans committed today, there only to clear the gate's 30-plan floor -- so it is built ONCE and copied. Doing it per case cost a git init, 32 writes and a commit thirteen times over. Module-scoped rather than a pytest fixture: several cases nest it inside their OWN tmp_path (`make_repo` copies it under a per-case root), and a
# plain lazy path keeps that copy step identical to the bash original's `cp -r "$TEMPLATE" "$d"`.
_TEMPLATE = None


def _run(*argv, cwd=None, env=None):
    result = harness.run(list(argv), cwd=cwd, env=env)
    if result.rc != 0:
        raise RuntimeError("fixture command failed: %s\n%s" % (argv, result.combined))
    return result


def _template():
    global _TEMPLATE  # noqa: PLW0603
    if _TEMPLATE is not None:
        return _TEMPLATE
    root = pathlib.Path(tempfile.mkdtemp())
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    agent = root / "agent"
    agent.mkdir(parents=True)
    _run("git", "-C", str(root), "init", "-q")
    _run("git", "-C", str(root), "config", "user.email", "t@example.com")
    _run("git", "-C", str(root), "config", "user.name", "t")
    for i in range(1, 33):
        (agent / ("PLAN-filler-%d.md" % i)).write_text(
            "Status: draft\n\n# filler %d\n\n- [ ] a task long enough to parse\n" % i,
            encoding="utf-8",
        )
    _run("git", "-C", str(root), "add", "-A", "--", ".")
    _run("git", "-C", str(root), "-c", "commit.gpgsign=false", "commit", "-qm", "filler")
    _TEMPLATE = root
    return root


def make_repo(directory, days_ago, *names):
    """`make_repo <dir> <days-ago> <name...>`."""
    directory.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_template(), directory)
    for name in names:
        (directory / "agent" / name).write_text(
            "Status: draft\n\n# %s\n\n- [ ] a task long enough to parse\n" % name,
            encoding="utf-8",
        )
    _run("git", "-C", str(directory), "add", "-A", "--", ".")
    when = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%S+0000"
    )
    env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    _run(
        "git",
        "-C",
        str(directory),
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "aged plans",
        env=env,
    )


def run_gate(root, **env) -> harness.RunResult:
    base = {"PLAN_HK_ROOT": str(root), "PLAN_HK_CONFIG": str(CFG)}
    base.update(env)
    return harness.run(["python3", str(GATE)], env=base)


# -- 1. THE PLANT: an over-age plan is reported, and named ------------------


def test_over_age(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 40, "PLAN-ancient.md")
    result = run_gate(d)
    gate.assert_eq(result.rc, 1, "a plan committed 40 days ago must fail")
    gate.assert_contains(result.combined, "PLAN-ancient.md", "names the offending plan")
    gate.assert_contains(result.combined, "unchanged for more than", "says what the finding IS")
    gate.log_pass("an over-age plan is reported by name")


# -- 2. THE PAIR, and the case that makes the INSTRUMENT choice testable ---- A plan first committed 40 days ago but AMENDED 2 days ago must PASS. This is what distinguishes last-commit from added-date; without it the gate could be using either and nobody would know.


def test_amended_recently(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 40, "PLAN-ancient.md")
    with (d / "agent" / "PLAN-ancient.md").open("a", encoding="utf-8") as fh:
        fh.write("- [ ] one more task, added today\n")
    _run("git", "-C", str(d), "add", "-A")
    _run("git", "-C", str(d), "-c", "commit.gpgsign=false", "commit", "-qm", "still being worked")
    result = run_gate(d)
    gate.assert_eq(
        result.rc, 0, "an OLD plan amended today must pass -- last-commit, not added-date"
    )
    gate.log_pass("CONTROL: editing an old plan resets its clock")


# -- 3. CONTROL: a young corpus is silent ------------------------------------


def test_young_is_silent(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 2, "PLAN-fresh.md")
    result = run_gate(d)
    gate.assert_eq(result.rc, 0, "a corpus with nothing over the threshold must pass")
    gate.assert_not_contains(
        result.combined, "unchanged for more than", "and say nothing about ages"
    )
    gate.log_pass("CONTROL: a young corpus is silent, so the plant above means something")


# -- 4. The WARN band names the date, and does NOT fail ----------------------


def test_warn_band(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 28, "PLAN-soon.md")
    result = run_gate(d)
    gate.assert_eq(result.rc, 0, "a plan inside the warn band must WARN, never fail")
    gate.assert_contains(result.combined, "PLAN-soon.md", "names it")
    gate.assert_contains(result.combined, "red on", "and names the exact date it goes red")
    gate.log_pass("the warn band announces the red date a week early")


# -- 5-7. The allowlist, and its three liveness rules ------------------------


def test_allowlist_suppresses(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 40, "PLAN-ancient.md")
    allow = d / ".plan-housekeeping-allowlist"
    allow.write_text(
        "# BLOCKER: this plan is a multi-week migration the operator is still "
        "executing daily\n2099-01-01  agent/PLAN-ancient.md\n",
        encoding="utf-8",
    )
    result = run_gate(d, PLAN_HK_ALLOWLIST=str(allow))
    gate.assert_eq(result.rc, 0, "an unexpired entry with a real BLOCKER suppresses the finding")
    gate.log_pass("the escape hatch works")


def test_allowlist_expires(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 40, "PLAN-ancient.md")
    allow = d / ".plan-housekeeping-allowlist"
    allow.write_text(
        "# BLOCKER: this plan is a multi-week migration the operator is still "
        "executing daily\n2020-01-01  agent/PLAN-ancient.md\n",
        encoding="utf-8",
    )
    result = run_gate(d, PLAN_HK_ALLOWLIST=str(allow))
    gate.assert_eq(result.rc, 1, "an EXPIRED entry stops suppressing, on its own stated date")
    gate.assert_contains(result.combined, "EXPIRED", "and says so")
    gate.log_pass("an exemption cannot outlive the argument for it")


def test_allowlist_unnecessary(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 2, "PLAN-fresh.md")
    allow = d / ".plan-housekeeping-allowlist"
    allow.write_text(
        "# BLOCKER: this plan is a multi-week migration the operator is still "
        "executing daily\n2099-01-01  agent/PLAN-fresh.md\n",
        encoding="utf-8",
    )
    result = run_gate(d, PLAN_HK_ALLOWLIST=str(allow))
    gate.assert_eq(
        result.rc, 1, "an entry that suppresses NOTHING is refused -- the converse direction"
    )
    gate.assert_contains(result.combined, "suppresses nothing", "and says which way it is wrong")
    gate.log_pass("an exemption must actually be exempting something")


def test_allowlist_low_effort_blocker(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 40, "PLAN-ancient.md")
    allow = d / ".plan-housekeeping-allowlist"
    allow.write_text("# BLOCKER: needed\n2099-01-01  agent/PLAN-ancient.md\n", encoding="utf-8")
    result = run_gate(d, PLAN_HK_ALLOWLIST=str(allow))
    gate.assert_eq(result.rc, 1, "a one-word BLOCKER buys no silence")
    # NAME THE FINDING. This gate exits 1 for stale plans and dangling allowlist rows as well, so the bare code cannot tell "the BLOCKER was too thin" from "the fixture was wrong".
    gate.assert_contains(
        result.combined,
        "allowlist problem",
        "and the refusal must be an ALLOWLIST problem, not some other red",
    )
    gate.log_pass("the BLOCKER must be substantive, not a word")


def test_allowlist_dangling(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 2, "PLAN-fresh.md")
    allow = d / ".plan-housekeeping-allowlist"
    allow.write_text(
        "# BLOCKER: this plan is a multi-week migration the operator is still "
        "executing daily\n2099-01-01  agent/PLAN-that-never-existed.md\n",
        encoding="utf-8",
    )
    result = run_gate(d, PLAN_HK_ALLOWLIST=str(allow))
    gate.assert_eq(result.rc, 1, "an entry naming no tracked plan is refused")
    gate.assert_contains(result.combined, "not a tracked plan file", "and says the plan is gone")
    gate.log_pass("an exemption cannot outlive the file it names")


# -- 8-9. THE SHALLOW PAIR. The defect this gate exists around. -------------


def test_shallow_refuses_in_ci(gate, tmp_path):
    d = tmp_path / "r"
    s = tmp_path / "shallow"
    make_repo(d, 40, "PLAN-ancient.md")
    _run("git", "clone", "-q", "--depth", "1", "file://%s" % d, str(s))
    result = run_gate(s, CI="true")
    gate.assert_eq(result.rc, 1, "a SHALLOW checkout in CI must refuse, not answer")
    gate.assert_contains(result.combined, "SHALLOW", "and say why")
    gate.assert_not_contains(result.combined, "none over", "and must NOT claim a clean tree")
    gate.log_pass("the graft-date defect is refused in CI rather than answered wrongly")


def test_shallow_skips_locally(gate, tmp_path):
    d = tmp_path / "r"
    s = tmp_path / "shallow"
    make_repo(d, 40, "PLAN-ancient.md")
    _run("git", "clone", "-q", "--depth", "1", "file://%s" % d, str(s))
    result = run_gate(s, CI="")
    gate.assert_eq(result.rc, 0, "a shallow checkout locally is a SKIP, not a failure")
    gate.assert_contains(
        result.combined, "PARTIAL RUN", "and it says the run was partial, not clean"
    )
    gate.log_pass("locally the age verdict is deferred loudly, never silently")


# -- 8b. AN EMPTY .git/shallow IS NOT A SHALLOW CLONE ------------------------ `git rev-parse --is-shallow-repository` answers on the FILE'S EXISTENCE, and `git fetch --unshallow` against a partial clone leaves it behind empty. CI job 100500447167 unshallowed successfully and this gate still refused, in the exact lane its own error message recommends. A graft is what corrupts the
# dates, so an empty graft list must not refuse -- and the over-age plant must still be found through it, or "not shallow" would just be a quieter way of checking nothing.


def test_empty_shallow_file_is_not_shallow(gate, tmp_path):
    d = tmp_path / "r"
    make_repo(d, 40, "PLAN-ancient.md")
    git_path = harness.run(["git", "-C", str(d), "rev-parse", "--git-path", "shallow"]).out.strip()
    (d / git_path).write_text("", encoding="utf-8")
    is_shallow = harness.run(
        ["git", "-C", str(d), "rev-parse", "--is-shallow-repository"]
    ).out.strip()
    if is_shallow != "true":
        gate.log_fail(
            "fixture did not reproduce the condition: git does not call this repo shallow"
        )
    result = run_gate(d, CI="true")
    gate.assert_eq(
        result.rc, 1, "the AGE finding must still be reported through an empty .git/shallow"
    )
    gate.assert_contains(result.combined, "PLAN-ancient.md", "naming the over-age plan")
    gate.assert_not_contains(result.combined, "SHALLOW", "and NOT refusing as shallow")
    gate.log_pass("an empty graft list is a complete history, whatever rev-parse says")


# -- 8c. A SHALLOW CLONE WHOSE PLANS ARE ALL PRESENT MUST STILL ANSWER ------ The case CI actually hit. Job 100507628220 measured 90 commits reachable and 1 graft and REFUSED -- in the lane its own error message recommends -- while every plan's history was entirely present (`agent/` has only been tracked since 2026-08-18, so nothing in the corpus is older than the boundary). A
# graft only corrupts this gate when a PLAN's last commit is the boundary, so that is what is asked. The plant must still be found through it, or "not on the boundary" would just be a quieter way of checking nothing.


def test_shallow_but_plans_present(gate, tmp_path):
    d = tmp_path / "r"
    c = tmp_path / "deep"
    make_repo(d, 40, "PLAN-ancient.md")
    # One more commit that touches EVERY plan, so no plan's last commit is the boundary once the clone grafts at the commit below it. Backdated too, or the over-age plant would be reset by this very commit.
    when = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=40)).strftime(
        "%Y-%m-%dT%H:%M:%S+0000"
    )
    for f in sorted((d / "agent").glob("PLAN-*.md")):
        with f.open("a", encoding="utf-8") as fh:
            fh.write("- [ ] one more\n")
    _run("git", "-C", str(d), "add", "-A", "--", ".")
    _run(
        "git",
        "-C",
        str(d),
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "touch every plan",
        env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when},
    )
    _run("git", "clone", "-q", "--depth", "2", "file://%s" % d, str(c))

    git_path = harness.run(["git", "-C", str(c), "rev-parse", "--git-path", "shallow"]).out.strip()
    shallow_file = c / git_path
    if not (shallow_file.is_file() and shallow_file.stat().st_size > 0):
        gate.log_fail("fixture did not reproduce the condition: the clone carries no graft")
    result = run_gate(c, CI="true")
    gate.assert_eq(
        result.rc, 1, "the AGE finding must still be reported through a graft no plan sits on"
    )
    gate.assert_contains(result.combined, "PLAN-ancient.md", "naming the over-age plan")
    gate.assert_not_contains(result.combined, "SHALLOW", "and NOT refusing as shallow")
    gate.log_pass("a graft below every plan is not a reason to refuse")


# -- 10. The override is not an escape hatch ---------------------------------


def test_empty_tree_is_not_a_pass(gate, tmp_path):
    d = tmp_path / "empty"
    d.mkdir(parents=True)
    _run("git", "-C", str(d), "init", "-q")
    result = run_gate(d)
    gate.assert_eq(result.rc, 1, "an empty tree must fail, or PLAN_HK_ROOT is an escape hatch")
    gate.assert_contains(result.combined, "VACUOUS INPUT", "and say the corpus was lost")
    gate.log_pass("the fixture override cannot be used to pass vacuously")
