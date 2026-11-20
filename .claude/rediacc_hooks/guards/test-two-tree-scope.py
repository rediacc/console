#!/usr/bin/env python3
"""Two-tree scope suite for the guards that place a command and then ask whether it is this checkout's (box LT11's report, agent/plans/PLAN-two-track-merge-dev.md).

Each guard below used to test `is_inside(repo, root)` after `run_repo`, `scoped_repo` or `branch_creations`, so with a landing record a command typed in the sibling bound tree (the landing tree from the main checkout) was skipped as a scratch repository's, or judged as the session root's own. They now test `commit_policy.is_ours` over `commit_policy.bound_trees`.

REAL REPOSITORIES under a `rediacc_ci.runtmp` run directory: a main checkout on the development branch, a linked landing tree on the landing branch, and the landing record in the common git dir; and the same pair with no record. Per guard, one command typed in the landing tree from the main-checkout root must reach the guard's verdict (a refusal, or for the lease push an admission), the guard's declared `TWO_TREE_DEFECT` (the bound trees cut to the session root) must flip it, and the same command in the no-record world must keep the answer it had before the record existed. The no-record answers are the goldens' world, which is why no golden moves.
"""

import importlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import typing

HERE = pathlib.Path(__file__).resolve().parent
CLAUDE = HERE.parents[1]
DISPATCH = str(HERE.parent / "dispatch.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("%s: %s is missing" % (__file__, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtmp = _load("runtmp", CLAUDE.parent / ".ci" / "rediacc_ci" / "runtmp.py")
syspath = _load("rediacc_hooks_syspath", CLAUDE / "rediacc_hooks" / "syspath.py")
syspath.on_sys_path(str(CLAUDE))
hookio = importlib.import_module("rediacc_hooks.hookio")
BP = importlib.import_module("rediacc_hooks.guards._backup_push")
LIVE_WRITER = importlib.import_module("rediacc_hooks.guards.block_commit_of_live_writer_file")

RUN_TMP = runtmp.run_dir("guard-two-tree-scope-")
GIT_ENV = {
    k: v
    for k, v in os.environ.items()
    if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")
}
GIT_ENV.update(
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)
LANDING, DEV = "1120-1", "1121-1"
PLAN = "agent/plans/PLAN-a.md"
BOX = "T16 Retarget writers:"
PLAN_TEXT = (
    "# PLAN: a\n\nStatus: in-progress\nOwner: cafe0000\nDepends-On: no-dep -- a fixture\n\n"
    "## Tasks\n\n- [ ] %s\n- [ ] T17 Delete the env files\n" % BOX
)

# A `gh` that answers nothing: `live_branches(gh=True)` then keeps every local branch live.
GH_DIR = pathlib.Path(tempfile.mkdtemp(prefix="gh-", dir=RUN_TMP))
(GH_DIR / "gh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
(GH_DIR / "gh").chmod(0o755)
CONFIG = pathlib.Path(tempfile.mkdtemp(prefix="config-", dir=RUN_TMP))
SESSION = "c0ffee44-two-tree-scope-000000000000"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, env=GIT_ENV)


def world(record):
    """`(main, landing)`: the main checkout on DEV, the landing tree on LANDING, the record when `record`; the landing tree carries a modified tracked file and a plan with a box deleted, and a live writer of SESSION edits that file."""
    base = pathlib.Path(os.path.realpath(tempfile.mkdtemp(prefix="world-", dir=RUN_TMP)))
    main, landing = base / "main", base / "landing"
    main.mkdir()
    git(main, "init", "-q", "--initial-branch=main")
    git(main, "config", "maintenance.auto", "false")
    git(main, "config", "gc.auto", "0")
    for rel, text in (("src/a.ts", "seed\n"), ("docs/y.md", "seed\n"), (PLAN, PLAN_TEXT)):
        (main / rel).parent.mkdir(parents=True, exist_ok=True)
        (main / rel).write_text(text, encoding="utf-8")
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "seed")
    git(main, "branch", LANDING)
    git(main, "checkout", "-q", "-b", DEV)
    git(main, "worktree", "add", "-q", str(landing), LANDING)
    BP.plant(main)
    BP.plant(landing)
    if record:
        (main / ".git" / "rediacc-landing.json").write_text(
            json.dumps({"path": str(landing), "branch": LANDING}), encoding="utf-8"
        )
    (landing / "src/a.ts").write_text("a landing edit\n", encoding="utf-8")
    (landing / PLAN).write_text(PLAN_TEXT.replace("- [ ] %s\n" % BOX, ""), encoding="utf-8")
    LIVE_WRITER.write_session(
        CONFIG,
        main,
        SESSION,
        [("atwotreelivewriter0001", "landing writer", [str(landing / "src/a.ts")], True, "")],
    )
    return main, landing


TT = world(record=True)
NR = world(record=False)

RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "import ast\n"
    "decl = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id == 'TWO_TREE_DEFECT' for t in n.targets)]\n"
    "assert decl, 'the guard declares no TWO_TREE_DEFECT'\n"
    "old, new = ast.literal_eval(decl[0].value)\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in decl))\n"
    "assert old in outside, 'TWO_TREE_DEFECT no longer applies outside its own declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def run(stem, command, pair, planted=False):
    """(blocked, stderr) of `command` typed in the landing tree of `pair` from its main-checkout root, through the dispatcher or through a copy of the guard with its TWO_TREE_DEFECT planted."""
    main, _landing = pair
    env = dict(
        GIT_ENV,
        CLAUDE_PROJECT_DIR=str(main),
        CLAUDE_CONFIG_DIR=str(CONFIG),
        PATH="%s:%s" % (GH_DIR, os.environ["PATH"]),
        TMPDIR=tempfile.mkdtemp(prefix="tmp-", dir=RUN_TMP),
    )
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(main),
            "session_id": SESSION,
        }
    )
    guard = str(HERE / ("%s.py" % stem))
    argv = (
        [sys.executable, "-c", RUNNER % (str(CLAUDE), guard, guard)]
        if planted
        else [sys.executable, DISPATCH, stem]
    )
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(main)
    )
    if proc.returncode not in (0, 2):
        raise SystemExit(
            "%s runner crashed (rc %d): %s" % (stem, proc.returncode, proc.stderr[-800:])
        )
    return proc.returncode == 2, proc.stderr


def _l(pair):
    return str(pair[1])


# (guard stem, command builder over the pair, want blocked with the record, want blocked with none)
CASES: list[tuple[str, typing.Callable[[tuple], str], bool, bool]] = [
    (
        "block_ci_skip_token",
        lambda p: "git -C %s commit -m 'chore: x [skip ci]' -- src/a.ts" % _l(p),
        True,
        False,
    ),
    (
        "block_no_review_ineligible",
        lambda p: "git -C %s commit -m 'feat: x [no-review]' -- src/a.ts" % _l(p),
        True,
        False,
    ),
    ("block_nonstandard_branch_name", lambda p: "git -C %s branch feature-x" % _l(p), True, False),
    ("block_second_branch", lambda p: "git -C %s branch feature-x" % _l(p), True, False),
    (
        "block_commit_of_live_writer_file",
        lambda p: "git -C %s commit -F m -- src/a.ts" % _l(p),
        True,
        False,
    ),
    (
        "block_plan_box_rewrite",
        lambda p: "git -C %s commit -F m -- %s" % (_l(p), PLAN),
        True,
        False,
    ),
    # The landing branch is the one checked out in the landing tree: deleting it is refused there. With no record the push is judged as the root's own, whose branch is the development one.
    (
        "block_git_force_push",
        lambda p: "git -C %s push origin --delete %s" % (_l(p), LANDING),
        True,
        False,
    ),
    # The admitted lease form in the landing tree, to its own live branch: admitted only once the landing tree is this checkout and its own console.
    (
        "block_git_force_push",
        lambda p: "git -C %s push --force-with-lease origin %s" % (_l(p), LANDING),
        False,
        True,
    ),
    ("block_rebase_over_foreign_dirt", lambda p: "git -C %s rebase main" % _l(p), True, False),
    ("block_blanket_git_add", lambda p: "git -C %s add -A" % _l(p), True, False),
    ("block_destructive_git_restore", lambda p: "git -C %s reset --hard" % _l(p), True, False),
    ("block_destructive_git_restore", lambda p: "git -C %s stash" % _l(p), True, False),
]

fails = 0
for stem, build, want, want_none in CASES:
    got, err = run(stem, build(TT), TT)
    planted, _ = run(stem, build(TT), TT, planted=True)
    none, _ = run(stem, build(NR), NR)
    ok = got == want and planted != want and none == want_none
    fails += not ok
    print(
        "%-34s %-58s record=%-8s planted=%-8s none=%-8s %s"
        % (
            stem,
            build(TT).replace(_l(TT), "<landing>")[:58],
            "BLOCKED" if got else "allowed",
            "BLOCKED" if planted else "allowed",
            "BLOCKED" if none else "allowed",
            "ok" if ok else "*** FAIL *** want record=%s none=%s" % (want, want_none),
        )
    )
    if got != want:
        print("    stderr: %s" % err.strip().splitlines()[:3])

# _backup_push is a predicate, not a guard: `admitted` must hold for a backup push typed in the landing tree, fail with its TWO_TREE_DEFECT planted, and fail with no record.
BACKUP = "git -C %s push gitlab HEAD:refs/backup/%s/live"


def admitted(pair, planted=False):
    main, landing = pair
    ev = hookio.Event(
        json.dumps({"tool_name": "Bash", "tool_input": {"command": BACKUP % (landing, LANDING)}}),
        cwd=str(main),
        env=dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(main)),
    )
    if not planted:
        return BP.admitted(ev, BACKUP % (landing, LANDING))
    src = pathlib.Path(str(BP.__file__)).read_text(encoding="utf-8")
    old, new = BP.TWO_TREE_DEFECT
    if src.count(old) < 2:
        raise SystemExit("_backup_push's TWO_TREE_DEFECT no longer applies outside its declaration")
    ns: dict[str, typing.Any] = {"__name__": "broken_backup_push", "__file__": BP.__file__}
    exec(compile(src.replace(old, new), str(BP.__file__), "exec"), ns)
    return ns["admitted"](ev, BACKUP % (landing, LANDING))


got, planted, none = admitted(TT), admitted(TT, planted=True), admitted(NR)
ok = got and not planted and not none
fails += not ok
print(
    "%-34s %-58s record=%-8s planted=%-8s none=%-8s %s"
    % (
        "_backup_push.admitted",
        (BACKUP % ("<landing>", LANDING))[:58],
        got,
        planted,
        none,
        "ok" if ok else "*** FAIL *** want True, False, False",
    )
)

print("%d case(s); FAILURES: %d" % (len(CASES) + 1, fails))
sys.exit(1 if fails else 0)
