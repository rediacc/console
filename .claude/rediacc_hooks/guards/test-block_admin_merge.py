#!/usr/bin/env python3
"""Control harness for block_admin_merge's plan gate (box L2 of agent/plans/PLAN-plan-per-pr-loop.md).

WHY A SUITE BESIDE THE GOLDEN. The differential corpus runs this guard under the harness's default `gh` stub, which answers nothing, so every merge stops at "could not resolve the PR" and the plan gate is never reached (the guard's own PORT NOTE). This file puts a `gh` stub on PATH that answers `gh pr view` with a console PR whose body each case sets, and a fixture checkout whose committed plans the gate
reads at `origin/<head>`.

WHAT A CASE ASSERTS. Only the plan gate's own verdict: `plan` means the refusal is the plan gate's (its message carries PLAN_MARK), `past` means the merge got past the plan gate. A `past` case is still refused further down in this fixture (the per-commit review arm walks commits this fixture does not review), and that refusal is not this suite's subject; the review arm has its own suite in
`tests/test_wl_review_check.py`.

THE --admin BAN THROUGH EXPANSION (review a7b3a36f.2). `ADMIN_CASES` asks a second question of the same world, a green console PR whose plan is ticked: is the refusal the outright ban's (`admin`, its message carries ADMIN_MARK), a refusal further down that only this fixture's unreviewed commits cause (`judged`), or no refusal at all (`allowed`)? Each `admin` row spells `--admin` only through expansion or a command name held in a variable, and each was `judged` or `allowed` before the guard read the walked merge's expanded words and the walk resolved the name: the ban never fired. A control is `judged`, so it proves the walk saw a merge there, not merely that the ban stayed quiet.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, as every guard suite here does.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import _hookpath

from rediacc_hooks.guards import _harness

HERE = pathlib.Path(__file__).resolve()
DISPATCH = str(HERE.parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_admin_merge"]

# The well-known repo slugs, read from .ci/config/well-known.env by the CI reader, loaded by file like runtmp below (check:ci-literal-sources forbids spelling them).
_WK = importlib.util.spec_from_file_location(
    "well_known_for_suite", HERE.parents[3] / ".ci" / "rediacc_ci" / "well_known.py"
)
if _WK is None or _WK.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/well_known.py is missing" % __file__)
well_known = importlib.util.module_from_spec(_WK)
_WK.loader.exec_module(well_known)
GH_REPO, RENET_REPO = well_known.GH_REPO, well_known.RENET_REPO

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-admin-merge-")

PLAN_MARK = "fails the plan gate"
ADMIN_MARK = "'gh pr merge --admin' is banned"
BRANCH = "0914-1"
PLAN_DONE = "agent/plans/PLAN-fx-done.md"
PLAN_OPEN = "agent/plans/PLAN-fx-open.md"
PLAN_DONE2 = "agent/plans/PLAN-fx-done2.md"
QUEUE_REL = "agent/plans/QUEUE.md"
# A queue at the PR head and a different one in the working tree: no QUEUE.md setting admits a second plan, so neither copy changes the plan gate's answer (agent/plans/PLAN-simple-two-tree-loop.md ruling 4).
QUEUE_TEXT = "# Plan queue\n\n## Settings\n\n```stop-hook\neffort: %s\n```\n\n## Promoted\n\n"
PLANS = {
    PLAN_DONE: "# PLAN-fx-done\nStatus: approved\n\n## Boxes\n- [x] A the first box is finished and ticked\n- [x] B the second box is finished and ticked\n",
    PLAN_OPEN: "# PLAN-fx-open\nStatus: approved\n\n## Boxes\n- [x] A the first box is finished and ticked\n- [ ] B the second box is still open on this branch\n",
    PLAN_DONE2: "# PLAN-fx-done2\nStatus: approved\n\n## Boxes\n- [x] A the first box is finished and ticked\n",
    QUEUE_REL: QUEUE_TEXT % "high",
}

_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def _git(repo, *args):
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False, env=_ENV
    )
    if proc.returncode != 0:
        raise SystemExit("fixture git %s failed in %s: %s" % (args, repo, proc.stderr))
    return proc.stdout.strip()


def _make_checkout():
    """A checkout on BRANCH whose plans are committed and published as `origin/<BRANCH>`; the open plan is ticked in the working tree only, which the gate must not count."""
    d = pathlib.Path(tempfile.mkdtemp(prefix="checkout-", dir=RUN_TMP))
    _git(d, "init", "-q", "--initial-branch=%s" % BRANCH)
    for rel, text in PLANS.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text, encoding="utf-8")
    _git(d, "add", "--", *PLANS)
    _git(d, "commit", "-q", "-m", "plans")
    _git(d, "update-ref", "refs/remotes/origin/%s" % BRANCH, "HEAD")
    (d / PLAN_OPEN).write_text(PLANS[PLAN_OPEN].replace("- [ ]", "- [x]"), encoding="utf-8")
    (d / QUEUE_REL).write_text(QUEUE_TEXT % "low", encoding="utf-8")
    return d


CHECKOUT = _make_checkout()

GH_STUB = r"""#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if a[:2] == ["pr", "view"]:
    pr = {
        "number": 7,
        "statusCheckRollup": [{"name": "CI Complete", "conclusion": "SUCCESS"}],
        "headRefName": os.environ["FX_HEAD_REF"],
        "body": os.environ.get("FX_BODY", ""),
    }
    if os.environ.get("FX_HEAD_OID"):
        pr["headRefOid"] = os.environ["FX_HEAD_OID"]
    if os.environ.get("FX_GH") == "nobody":
        del pr["body"]
    print(json.dumps(pr))
    sys.exit(0)
if a[:2] == ["api", "graphql"]:
    print("0")
    sys.exit(0)
print("[]")
"""
STUB_DIR = pathlib.Path(tempfile.mkdtemp(prefix="stub-", dir=RUN_TMP))
(STUB_DIR / "gh").write_text(GH_STUB, encoding="utf-8")
(STUB_DIR / "gh").chmod(0o755)

MERGE = "gh pr merge 7 --repo %s --rebase --auto" % GH_REPO

CASES = [
    # (name, command, FX_BODY or None for an unreadable body, expected verdict)
    ("open boxes and no Operational-Reason", MERGE, "Plan: %s" % PLAN_OPEN, "plan"),
    # PLAN-simple-two-tree-loop B8: `Operational-Reason:` admits no open box any more; it keeps only the fast-forward fallback role.
    (
        "open boxes with an Operational-Reason are still refused",
        MERGE,
        "Plan: %s\nOperational-Reason: the last box is a live run after merge" % PLAN_OPEN,
        "plan",
    ),
    (
        "every box ticked with an Operational-Reason",
        MERGE,
        "Plan: %s\nOperational-Reason: GitHub cannot rebase this PR" % PLAN_DONE,
        "past",
    ),
    ("every box ticked", MERGE, "Prose first.\n\n**Plan:** `%s`" % PLAN_DONE, "past"),
    ("no Plan line and no Operational-Reason", MERGE, "Prose only.", "plan"),
    ("an empty body", MERGE, "", "plan"),
    ("the body cannot be read", MERGE, None, "plan"),
    (
        "two plans and no Operational-Reason",
        MERGE,
        "Plan: %s\nPlan: %s" % (PLAN_DONE, PLAN_OPEN),
        "plan",
    ),
    (
        "two plans with an Operational-Reason, one with an open box",
        MERGE,
        "Plan: %s, %s\nOperational-Reason: #591 finishes as-is" % (PLAN_DONE, PLAN_OPEN),
        "plan",
    ),
    (
        "two ticked plans are refused: a plan rides one PR",
        MERGE,
        "Plan: %s, %s" % (PLAN_DONE, PLAN_DONE2),
        "plan",
    ),
    (
        "two plans, one open at the head, are refused",
        MERGE,
        "Plan: %s, %s" % (PLAN_DONE2, PLAN_OPEN),
        "plan",
    ),
    ("a Plan line naming no plan path", MERGE, "Plan: the one about merges", "plan"),
    ("a plan that does not exist", MERGE, "Plan: agent/plans/PLAN-fx-missing.md", "plan"),
    (
        "an immediate merge is judged too",
        "gh pr merge 7 --repo %s --rebase" % GH_REPO,
        "Plan: %s" % PLAN_OPEN,
        "plan",
    ),
    # A submodule PR names no plan; the gate is the console PR's.
    (
        "a submodule PR is not plan-gated",
        "gh pr merge 7 --repo %s --rebase --auto" % RENET_REPO,
        "",
        "past",
    ),
]


_TICKED = "Plan: %s" % PLAN_DONE

ADMIN_CASES = [
    # (name, command, expected verdict); every row runs against the ticked, green PR above.
    ("eval of a split flag", 'X=-; eval "gh pr merge 7 --repo %s $X-admin"' % GH_REPO, "admin"),
    ("a flag spelled by expansion", "A=--adm; gh pr merge 7 --repo %s ${A}in" % GH_REPO, "admin"),
    ("a bash -c payload", 'X=-; bash -c "gh pr merge 7 --repo %s $X-admin"' % GH_REPO, "admin"),
    ("the verb held in a variable", "X=pr; gh $X merge 7 --repo %s --admin" % GH_REPO, "admin"),
    ("a vanished command name", "N=; $N gh pr merge 7 --repo %s --admin" % GH_REPO, "admin"),
    ("a command name that splits", 'N="gh pr"; $N merge 7 --repo %s --admin' % GH_REPO, "admin"),
    ("the eval form the golden records", 'X=--admin; eval "gh pr merge 7 $X"', "admin"),
    # CONTROLS: the same spellings with a flag that is not --admin are judged as merges and get past the ban.
    (
        "eval of a split ordinary flag",
        'X=-; eval "gh pr merge 7 --repo %s $X-auto"' % GH_REPO,
        "judged",
    ),
    ("a vanished name, no --admin", "N=; $N gh pr merge 7 --repo %s --auto" % GH_REPO, "judged"),
    ("a split name, no --admin", 'N="gh pr"; $N merge 7 --repo %s --auto' % GH_REPO, "judged"),
    (
        "the verb held in a variable, no --admin",
        "X=pr; gh $X merge 7 --repo %s --auto" % GH_REPO,
        "judged",
    ),
]


def run(command, body, root=CHECKOUT, head=BRANCH, oid="", argv=None):
    env = dict(
        os.environ,
        PATH="%s:%s" % (STUB_DIR, os.environ["PATH"]),
        CLAUDE_PROJECT_DIR=str(root),
        FX_HEAD_REF=head,
        # The reviewer's sidecars (TMPDIR/claude-worklist) land in the suite's own run directory, which runtmp removes.
        TMPDIR=tempfile.mkdtemp(prefix="tmp-", dir=RUN_TMP),
    )
    env.pop("FX_HEAD_OID", None)
    if oid:
        env["FX_HEAD_OID"] = oid
    if body is None:
        env["FX_GH"] = "nobody"
    else:
        env["FX_BODY"] = body
    proc = _harness.run(
        argv or GUARD_ARGV,
        input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)}
        ),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stderr


fails = 0
verdicts = set()
for name, command, body, want in CASES:
    rc, err = run(command, body)
    got = "plan" if (rc != 0 and PLAN_MARK in err) else "past"
    verdicts.add(got)
    ok = got == want
    fails += not ok
    print("%-60s want=%-5s got=%-5s %s" % (name, want, got, "ok" if ok else "*** FAIL ***"))
    if not ok:
        print("    rc=%d stderr: %s" % (rc, err.strip().splitlines()[:3]))

admin_verdicts = set()
for name, command, want in ADMIN_CASES:
    rc, err = run(command, _TICKED)
    got = "admin" if (rc != 0 and ADMIN_MARK in err) else ("judged" if rc != 0 else "allowed")
    admin_verdicts.add(got)
    ok = got == want
    fails += not ok
    print("%-60s want=%-6s got=%-7s %s" % (name, want, got, "ok" if ok else "*** FAIL ***"))
    if not ok:
        print("    rc=%d stderr: %s" % (rc, err.strip().splitlines()[:3]))

# ---- two trees (box LT12 of agent/plans/PLAN-two-track-merge-dev.md) ----------------------
# A main checkout on DEV and a linked worktree on LANDING, each branch one reviewed commit past `origin/main` with its review committed in its OWN tree, and the landing record in the common git dir. With the record the review precondition reads the tree that holds the PR's head; a guard reading the session root finds no record of the other tree's commits and refuses. The no-record world keeps the root's reading.
LANDING, DEV = "1120-1", "1121-1"
REVIEWS_MARK = "fails the per-commit review precondition"
REASON_BODY = "Operational-Reason: a two-tree fixture names no plan"
_SYSPATH_SPEC = importlib.util.spec_from_file_location(
    "_admin_merge_syspath", HERE.parents[1] / "syspath.py"
)
if _SYSPATH_SPEC is None or _SYSPATH_SPEC.loader is None:
    raise SystemExit("%s: syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH_SPEC)
_SYSPATH_SPEC.loader.exec_module(_syspath)
_syspath.on_sys_path(_syspath.STOP_DIR)
rv = importlib.import_module("wl_review")


def _reviewed_commit(tree, branch, name):
    """One commit on `branch` in `tree`, its review written in the reviewer's own format and committed beside it, and `origin/<branch>` at the result."""
    (tree / name).write_text("a = 1\n", encoding="utf-8")
    _git(tree, "add", "--", name)
    _git(tree, "commit", "-q", "-m", "fix(x): %s" % name)
    sha = _git(tree, "rev-parse", "HEAD")
    review = rv.Review(
        sha=sha,
        subject="fix(x): %s" % name,
        branch=branch,
        reviewed_at="2026-11-20T00:00:00Z",
        model="m",
    )
    target = rv.review_path(tree, branch, sha)
    rv.write_atomic(target, rv.render(review))
    _git(tree, "add", "--", str(target.relative_to(tree)))
    _git(tree, "commit", "-q", "-m", "chore(reviews): record")
    _git(tree, "update-ref", "refs/remotes/origin/%s" % branch, "HEAD")
    return _git(tree, "rev-parse", "HEAD")


def two_trees(record=True):
    """`(main, landing, tips)`: the main checkout on DEV, the landing worktree on LANDING, and each branch's pushed tip."""
    base = pathlib.Path(os.path.realpath(tempfile.mkdtemp(prefix="world-", dir=RUN_TMP)))
    main, landing = base / "main", base / "landing"
    main.mkdir()
    _git(main, "init", "-q", "--initial-branch=main")
    _git(main, "commit", "-q", "--allow-empty", "-m", "seed")
    _git(main, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(main, "branch", LANDING)
    _git(main, "checkout", "-q", "-b", DEV)
    _git(main, "worktree", "add", "-q", str(landing), LANDING)
    tips = {DEV: _reviewed_commit(main, DEV, "dev.py")}
    tips[LANDING] = _reviewed_commit(landing, LANDING, "landing.py")
    if record:
        common = pathlib.Path(_git(main, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        (common / "rediacc-landing.json").write_text(
            json.dumps({"path": str(landing), "branch": LANDING}), encoding="utf-8"
        )
    return main, landing, tips


TT_MAIN, TT_LANDING, TT_TIPS = two_trees()
NR_MAIN, NR_LANDING, NR_TIPS = two_trees(record=False)
TT_MERGE = "gh pr merge 7 --repo %s --rebase --auto" % GH_REPO

TWO_TREE_CASES = [
    # (name, root, head, tips, want refused by the review arm, flips under TWO_TREE_DEFECT)
    ("main root merges the landing PR", TT_MAIN, LANDING, TT_TIPS, False, True),
    ("landing root merges the landing PR", TT_LANDING, LANDING, TT_TIPS, False, False),
    ("landing root merges the dev draft", TT_LANDING, DEV, TT_TIPS, False, True),
    ("main root merges the dev draft", TT_MAIN, DEV, TT_TIPS, False, False),
    ("no record: main root merges the sibling's PR", NR_MAIN, LANDING, NR_TIPS, True, False),
]

GUARD_FILE = str(HERE.parent / "block_admin_merge.py")
_ns: dict[str, object] = {}
for _line in pathlib.Path(GUARD_FILE).read_text(encoding="utf-8").split("\n"):
    if _line.startswith("TWO_TREE_DEFECT = "):
        exec(_line, _ns)
TWO_TREE_DEFECT = _ns["TWO_TREE_DEFECT"]
BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "assert src.count(old) == 2, 'the defect no longer applies'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)
BROKEN_ARGV = [
    sys.executable,
    "-c",
    BROKEN_RUNNER % (str(HERE.parents[2]), GUARD_FILE, TWO_TREE_DEFECT, GUARD_FILE),
]

two_tree_verdicts = set()
for tt_name, tt_root, tt_head, tt_tips, tt_want, _flips in TWO_TREE_CASES:
    rc, err = run(TT_MERGE, REASON_BODY, root=tt_root, head=tt_head, oid=tt_tips[tt_head])
    tt_got = rc != 0 and REVIEWS_MARK in err
    two_tree_verdicts.add(tt_got)
    tt_ok = tt_got == tt_want and (tt_got or rc == 0)
    fails += not tt_ok
    print(
        "%-60s want=%-7s got=%-7s %s"
        % (
            "two trees: " + tt_name,
            "refused" if tt_want else "passes",
            "refused" if tt_got else ("passes" if rc == 0 else "other"),
            "ok" if tt_ok else "*** FAIL ***",
        )
    )
    if not tt_ok:
        print("    rc=%d stderr: %s" % (rc, err.strip().splitlines()[:3]))
flipping = [c for c in TWO_TREE_CASES if c[5]]
moved = []
for tt_name, tt_root, tt_head, tt_tips, tt_want, _flips in flipping:
    rc, err = run(
        TT_MERGE, REASON_BODY, root=tt_root, head=tt_head, oid=tt_tips[tt_head], argv=BROKEN_ARGV
    )
    if rc not in (0, 2):
        raise SystemExit("broken-copy runner crashed (rc %d): %s" % (rc, err[-800:]))
    if (rc != 0 and REVIEWS_MARK in err) != tt_want:
        moved.append(tt_name)
if flipping and len(moved) == len(flipping):
    print("TWO_TREE_DEFECT control: %d case(s) flipped to the review refusal" % len(moved))
else:
    print(
        "*** FAIL *** TWO_TREE_DEFECT control: %d of %d case(s) flipped"
        % (len(moved), len(flipping))
    )
    fails += 1

print()
# ANTI-VACUITY: a gate that answered one way on every input compared against a constant.
for label, seen in (
    ("plan-gate", verdicts),
    ("admin-ban", admin_verdicts),
    ("two-tree", two_tree_verdicts),
):
    if len(seen) < 2:
        print(
            "*** FAIL *** every %s case got %s: the suite compared the guard against a constant"
            % (label, seen)
        )
        fails += 1
print("%d case(s)" % (len(CASES) + len(ADMIN_CASES) + len(TWO_TREE_CASES)))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
