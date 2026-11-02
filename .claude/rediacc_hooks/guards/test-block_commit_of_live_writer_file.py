#!/usr/bin/env python3
"""Control harness for block_commit_of_live_writer_file (OWN_SUITE: never bash, so no golden).

Every case drives the live guard through the dispatcher against a real repository under a `rediacc_ci.runtmp` run directory, with a planted session under a fixture `CLAUDE_CONFIG_DIR`: a live writer (its transcript ends on a tool call in flight), a finished writer (its turn ended an hour ago), and a finished sub-writer of the live one. The planting is the guard's own `write_session`, so this suite and the differential agree on what a live transcript is.

CONTROLS FIRST, both directions: a live writer's file named, covered by a directory pathspec, staged for a bare commit or swept by `-a` is refused; a finished writer's file, an untouched file, a commit in another repository and an unreadable roster are allowed (the last with a stderr note). Then two MUTATIONS in a copy of the guard: the declared `DEFECT` (the overlap test never matches) and a liveness that calls every writer finished. Each must flip a refusal to allowed, or the refusals never depended on that branch.
"""

import importlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CLAUDE = HERE.parents[1]
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_commit_of_live_writer_file"
GUARD = HERE / ("%s.py" % STEM)


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
guard = importlib.import_module("rediacc_hooks.guards." + STEM)

RUN_TMP = runtmp.run_dir("guard-live-writer-")

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)
SEEDED = (
    "src/live.ts",
    "src/done.ts",
    "src/other.ts",
    "lib/child.py",
    "lib/grand.py",
    "docs/a.md",
    "out/x.txt",
)


def git(repo, *argv):
    subprocess.run(["git", *argv], cwd=str(repo), check=True, capture_output=True, env=GIT_ENV)


def make_repo():
    path = pathlib.Path(tempfile.mkdtemp(prefix="repo-", dir=RUN_TMP)).resolve()
    git(path, "init", "-q", "--initial-branch=main")
    return path


def seed(repo, rels):
    for rel in rels:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("seed\n", encoding="utf-8")


REPO = make_repo()
OUTSIDE = make_repo()
seed(REPO, SEEDED)
seed(OUTSIDE, ("src/live.ts",))
for repo in (REPO, OUTSIDE):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seed")

# A submodule root: a `.git` file makes `subm` a gitlink-shaped directory (#e59c13a0).
(REPO / "subm").mkdir()
git(REPO / "subm", "init", "-q", "--initial-branch=main")
(REPO / "subm/inner.ts").write_text("writer edit\n", encoding="utf-8")
# A submodule one directory down: a directory pathspec over `wrap` contains it without naming it.
(REPO / "wrap/nested").mkdir(parents=True)
git(REPO / "wrap/nested", "init", "-q", "--initial-branch=main")
(REPO / "wrap/nested/inner.ts").write_text("writer edit\n", encoding="utf-8")
(REPO / ".git/info/exclude").write_text("subm/\nwrap/\n", encoding="utf-8")

SESSION = "c0ffee00-live-writer-suite-000000000000"
CONFIG = pathlib.Path(tempfile.mkdtemp(prefix="config-", dir=RUN_TMP))
LIVE, DONE, CHILD = "asuitelivewriter00001", "asuitedonewriter00002", "asuitechildwriter0003"
GRAND = "asuitegrandwriter0004"
guard.write_session(
    CONFIG,
    REPO,
    SESSION,
    [
        (
            LIVE,
            "suite live writer",
            [str(REPO / "src/live.ts"), str(REPO / "out"), str(REPO / "subm/inner.ts")],
            True,
            "",
        ),
        (DONE, "suite finished writer", [str(REPO / "src/done.ts")], False, ""),
        (
            "asuitenestwriter00005",
            "suite nested-submodule writer",
            [str(REPO / "wrap/nested/inner.ts")],
            True,
            "",
        ),
        # Finished, but its parent is live: its edit is part of unfinished work.
        (CHILD, "suite sub-writer", [str(REPO / "lib/child.py")], False, LIVE),
        # Finished under a finished parent, two levels below the live writer.
        (GRAND, "suite grand-writer", [str(REPO / "lib/grand.py")], False, CHILD),
    ],
)
# A session directory with no subagents is an honest empty roster, not an unreadable one.
EMPTY_SESSION = "e0e0e0e0-live-writer-suite-000000000000"
(next(CONFIG.glob("projects/*")) / EMPTY_SESSION).mkdir()


def run(command, session=SESSION, runner=None):
    env = dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(REPO), CLAUDE_CONFIG_DIR=str(CONFIG))
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "session_id": session,
            "cwd": str(REPO),
            "tool_input": {"command": command},
        }
    )
    argv = [sys.executable, "-c", runner] if runner else [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(REPO)
    )
    if proc.returncode not in (0, 2):
        raise SystemExit("guard crashed (rc=%d): %s" % (proc.returncode, proc.stderr[-800:]))
    return proc.returncode == 2, proc.stderr


def prepare(setup):
    if setup == "dirty":
        (REPO / "src/live.ts").write_text("dirty\n", encoding="utf-8")
    elif setup:
        for rel in setup:
            (REPO / rel).write_text("edited\n", encoding="utf-8")
        git(REPO, "add", "--", *setup)


def reset():
    """Back to the seeded state: an empty index and the seed contents rewritten."""
    git(REPO, "reset", "-q")
    seed(REPO, SEEDED)


ROSTER_NOTE = "could not be read"

# (name, command, setup, expect_blocked, stderr needle, session)
CASES = [
    # ---- fire -------------------------------------------------------------------------------
    ("a live writer's file named", "git commit -F m -- src/live.ts", None, True, LIVE, SESSION),
    (
        "the refusal names the file",
        "git commit -F m -- src/live.ts",
        None,
        True,
        "src/live.ts",
        SESSION,
    ),
    ("a directory pathspec covers it", "git commit -F m -- src/", None, True, LIVE, SESSION),
    # ---- a gitlink pathspec commits the submodule pointer, never the submodule's files (#e59c13a0)
    (
        "a submodule root pathspec does not cover its files",
        "git commit -F m -- subm",
        None,
        False,
        "",
        SESSION,
    ),
    (
        "a submodule root with a trailing slash does not cover its files",
        "git commit -F m -- subm/",
        None,
        False,
        "",
        SESSION,
    ),
    (
        "an absolute submodule root does not cover its files",
        "git commit -F m -- %s/subm" % REPO,
        None,
        False,
        "",
        SESSION,
    ),
    # A directory pathspec that CONTAINS a submodule takes the gitlink, not the files inside it (a2e29702.2).
    (
        "a directory containing a submodule does not cover the submodule's files",
        "git commit -F m -- wrap",
        None,
        False,
        "",
        SESSION,
    ),
    (
        "CONTROL: the same file named directly inside the nested submodule",
        "git commit -F m -- wrap/nested/inner.ts",
        None,
        True,
        "asuitenestwriter00005",
        SESSION,
    ),
    # CONTROL: a writer's file named INSIDE the submodule is still that writer's file.
    (
        "a file inside the submodule named directly",
        "git commit -F m -- subm/inner.ts",
        None,
        True,
        LIVE,
        SESSION,
    ),
    ("an absolute pathspec", "git commit -F m -- %s/src/live.ts" % REPO, None, True, LIVE, SESSION),
    (
        "named from a subdirectory",
        "cd src && git commit -F m -- live.ts",
        None,
        True,
        LIVE,
        SESSION,
    ),
    (
        "mixed with a clean path",
        "git commit -F m -- src/other.ts src/live.ts",
        None,
        True,
        LIVE,
        SESSION,
    ),
    ("a bare commit with it staged", "git commit -m x", ("src/live.ts",), True, LIVE, SESSION),
    ("-a sweeps it from the worktree", "git commit -a -m x", "dirty", True, LIVE, SESSION),
    (
        "a finished sub-writer of a live writer",
        "git commit -F m -- lib/child.py",
        None,
        True,
        "lib/child.py",
        SESSION,
    ),
    (
        "a finished grandchild under a live grandparent",
        "git commit -F m -- lib/grand.py",
        None,
        True,
        "lib/grand.py",
        SESSION,
    ),
    (
        "the refusal text names the whole spawn chain",
        "git commit -F m -- lib/grand.py",
        None,
        True,
        "spawn chain (parent, grandparent",
        SESSION,
    ),
    (
        "after an unrelated add in the same line",
        "git add -- docs/a.md && git commit -F m -- src/live.ts",
        None,
        True,
        LIVE,
        SESSION,
    ),
    # ---- inverse ----------------------------------------------------------------------------
    ("a finished writer's file", "git commit -F m -- src/done.ts", None, False, "", SESSION),
    ("a file no writer touched", "git commit -F m -- src/other.ts", None, False, "", SESSION),
    (
        "a bare commit, only clean paths staged",
        "git commit -m x",
        ("src/other.ts",),
        False,
        "",
        SESSION,
    ),
    # A writer that wrote INTO `out/` does not claim every file below it (see the guard's docstring).
    (
        "a file under a dir a writer wrote into",
        "git commit -F m -- out/x.txt",
        None,
        False,
        "",
        SESSION,
    ),
    (
        "a commit in another repository",
        "git -C %s commit -F m -- src/live.ts" % OUTSIDE,
        None,
        False,
        "",
        SESSION,
    ),
    ("not a commit", "git diff -- src/live.ts", None, False, "", SESSION),
    ("prose naming a commit", "echo 'git commit -- src/live.ts'", None, False, "", SESSION),
    (
        "an empty roster passes silently",
        "git commit -F m -- src/live.ts",
        None,
        False,
        "",
        EMPTY_SESSION,
    ),
    (
        "an unreadable roster fails open, loudly",
        "git commit -F m -- src/live.ts",
        None,
        False,
        ROSTER_NOTE,
        "zz-no-such",
    ),
    (
        "no session id fails open, loudly",
        "git commit -F m -- src/live.ts",
        None,
        False,
        ROSTER_NOTE,
        "",
    ),
]

fails = 0
fired = 0
for name, command, setup, want, needle, session in CASES:
    prepare(setup)
    try:
        got, err = run(command, session=session)
    finally:
        reset()
    fired += got
    # An allowed case with no needle must also be SILENT: a stray note there is a fail-open in disguise.
    ok = got == want and needle in err and (want or needle or err == "")
    fails += not ok
    print(
        "%-42s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL *** stderr=%r" % err[-300:],
        )
    )

# A suite with no refusal at all has not shown the guard can speak.
fails += fired == 0
print("%-42s %s" % ("cases refused: %d" % fired, "ok" if fired else "*** FAIL ***"))

# ---- mutations: each must turn a refusal into an allow -----------------------------------------
RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id == 'DEFECT' for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert old in outside, 'mutation no longer applies outside the DEFECT declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)

MUTATIONS = [
    ("DEFECT: the overlap never matches", guard.DEFECT),
    (
        "every writer reads as finished",
        (
            'if roster.proven_finished(jsonl, now, meta.get("name", ""), cwd, session_id):',
            "if True:",
        ),
    ),
]
for label, (old, new) in MUTATIONS:
    code = RUNNER % (str(CLAUDE), str(GUARD), (old, new), str(GUARD))
    good, _ = run("git commit -F m -- src/live.ts")
    bad, err = run("git commit -F m -- src/live.ts", runner=code)
    red = good and not bad
    fails += not red
    verdict = "ok (the refusal flipped to allowed)" if red else "*** FAIL *** %r" % err[-300:]
    print("%-42s %s" % ("mutation: " + label, verdict))

print()
print("%d case(s), %d mutation(s); FAILURES: %d" % (len(CASES), len(MUTATIONS), fails))
sys.exit(1 if fails else 0)
