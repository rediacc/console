#!/usr/bin/env python3
"""Two-tree harness for block_merge_with_unpushed (box LT12 of agent/plans/PLAN-two-track-merge-dev.md).

WHY A SUITE BESIDE THE GOLDEN. The differential corpus runs this guard in one-tree worlds, where the branch a merge strands is always the root's HEAD. With a landing record (`commit_policy.landing_record`) the open PR's branch lives in a sibling tree, so the merged PR's head comes from `gh pr view` and its unpushed commits are counted in the tree that holds it. Every world here is REAL: a main repository, a linked worktree as the landing tree, and the record file in the common git dir; `gh` is a stub on PATH answering `headRefName` from `FX_HEAD`.

BOTH DIRECTIONS. A merge typed from the main checkout's root judges the landing tree's branch, and one typed from the landing root judges the development branch when the PR's head is the development branch. Each refusal has a twin that differs by which tree holds the unpushed commit, and the no-record world proves the reading before the record existed is unchanged (gh is never consulted there).

THE DEFECTS ARE PROVEN HERE. `TWO_TREE_DEFECT` (the head read from gh dropped) must flip a two-tree case, and the guard's own `DEFECT` (the `main` arm switched off) must flip the on-main control.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, as every guard suite here does.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_merge_with_unpushed"
GUARD = HERE / ("%s.py" % STEM)

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-merge-unpushed-")

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)
RECORD_NAME = "rediacc-landing.json"
LANDING = "1120-1"
DEV = "1121-1"
MAIN = "m" + "ain"
BLOCK_MARK = "are not pushed, and merging deletes the branch"


def git(repo, *args):
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False, env=GIT_ENV
    )
    if proc.returncode != 0:
        raise SystemExit("fixture git %s failed in %s: %s" % (args, repo, proc.stderr))
    return proc.stdout.strip()


def two_trees(unpushed, record=True, main_on=DEV):
    """`(main, landing)`: a main checkout on `main_on` and a linked worktree on LANDING, each branch published as `origin/<b>`; `unpushed` names the branches given one local commit past it."""
    base = pathlib.Path(os.path.realpath(tempfile.mkdtemp(prefix="world-", dir=RUN_TMP)))
    main, landing = base / "main", base / "landing"
    main.mkdir()
    git(main, "init", "-q", "--initial-branch=%s" % MAIN)
    git(main, "commit", "-q", "--allow-empty", "-m", "seed")
    git(main, "update-ref", "refs/remotes/origin/%s" % MAIN, "HEAD")
    for branch in (LANDING, DEV):
        git(main, "branch", branch)
        git(main, "update-ref", "refs/remotes/origin/%s" % branch, branch)
    if main_on != MAIN:
        git(main, "checkout", "-q", main_on)
    git(main, "worktree", "add", "-q", str(landing), LANDING)
    for branch in unpushed:
        holder = landing if branch == LANDING else main
        git(holder, "commit", "-q", "--allow-empty", "-m", "local only on %s" % branch)
    if record:
        common = pathlib.Path(git(main, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        (common / RECORD_NAME).write_text(
            json.dumps({"path": str(landing), "branch": LANDING}), encoding="utf-8"
        )
    return main, landing


GH_STUB = r"""#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]
if a[:2] == ["pr", "view"] and os.environ.get("FX_HEAD"):
    print(os.environ["FX_HEAD"])
    sys.exit(0)
sys.stderr.write("gh: stubbed out\n")
sys.exit(1)
"""
STUB_DIR = pathlib.Path(tempfile.mkdtemp(prefix="stub-", dir=RUN_TMP))
(STUB_DIR / "gh").write_text(GH_STUB, encoding="utf-8")
(STUB_DIR / "gh").chmod(0o755)

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id in ('DEFECT', 'TWO_TREE_DEFECT') for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert cut and old in outside, 'the defect no longer applies outside its declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def _declared(name):
    namespace: dict[str, object] = {}
    for line in GUARD.read_text(encoding="utf-8").split("\n"):
        if line.startswith(name + " = "):
            exec(line, namespace)
    return namespace[name]


DEFECT = _declared("DEFECT")
TWO_TREE_DEFECT = _declared("TWO_TREE_DEFECT")


def run(command, root, head="", defect=None):
    """(blocked, stderr) of one merge typed with the session rooted at `root`."""
    env = dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(root), PATH="%s:%s" % (STUB_DIR, os.environ["PATH"]))
    env.pop("FX_HEAD", None)
    if head:
        env["FX_HEAD"] = head
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)}
    )
    if defect:
        code = BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), defect, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(root)
    )
    if proc.returncode not in (0, 2):
        raise SystemExit("runner crashed (rc %d): %s" % (proc.returncode, proc.stderr[-800:]))
    return proc.returncode == 2, proc.stderr


LANDING_AHEAD = two_trees([LANDING])
DEV_AHEAD = two_trees([DEV])
NO_RECORD = two_trees([DEV], record=False)
NO_RECORD_SYNCED = two_trees([LANDING], record=False)
ON_MAIN = two_trees([], record=False, main_on=MAIN)
git(ON_MAIN[0], "commit", "-q", "--allow-empty", "-m", "local only on main")

MERGE = "gh pr merge 7 --rebase --auto"

# (name, root, FX_HEAD, want_blocked, flips under TWO_TREE_DEFECT)
CASES = [
    ("main root: the landing PR's unpushed commit", LANDING_AHEAD[0], LANDING, True, True),
    ("main root: the landing PR synced, the dev tree ahead", DEV_AHEAD[0], LANDING, False, True),
    ("landing root: its own unpushed commit", LANDING_AHEAD[1], LANDING, True, False),
    ("landing root: the dev draft's unpushed commit", DEV_AHEAD[1], DEV, True, True),
    ("landing root: the dev draft synced, landing ahead", LANDING_AHEAD[1], DEV, False, True),
    ("record, gh down: the root's own branch is judged", DEV_AHEAD[0], "", True, False),
    # The reading before the record: the root's HEAD, whatever gh says.
    ("no record: the root's branch ahead, gh names another", NO_RECORD[0], LANDING, True, False),
    ("no record: the root synced, the sibling ahead", NO_RECORD_SYNCED[0], LANDING, False, False),
    ("no record: on main with a local commit", ON_MAIN[0], "", False, False),
]

fails = 0
blocked = 0
for name, root, head, want, _flips in CASES:
    got, err = run(MERGE, root, head)
    blocked += got
    ok = got == want and (not got or BLOCK_MARK in err)
    fails += not ok
    print(
        "%-60s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok:
        print("    stderr: %s" % err.strip().splitlines()[:3])

print()
want_flip = [c for c in CASES if c[4]]
moved = [c[0] for c in want_flip if run(MERGE, c[1], c[2], defect=TWO_TREE_DEFECT)[0] != c[3]]
kept = [
    c[0] for c in CASES if not c[4] and run(MERGE, c[1], c[2], defect=TWO_TREE_DEFECT)[0] != c[3]
]
if len(moved) == len(want_flip) and not kept:
    print("TWO_TREE_DEFECT control: %d two-tree case(s) flipped, none other" % len(moved))
else:
    print(
        "*** FAIL *** TWO_TREE_DEFECT control: %d of %d flipped (%r), %d other(s) moved (%r)"
        % (len(moved), len(want_flip), moved, len(kept), kept)
    )
    fails += 1
if run(MERGE, ON_MAIN[0], "", defect=DEFECT)[0]:
    print("DEFECT control: with %r planted the on-main merge is refused" % (DEFECT,))
else:
    print("*** FAIL *** DEFECT control: with %r planted the on-main merge still passes" % (DEFECT,))
    fails += 1

if blocked in (0, len(CASES)):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
