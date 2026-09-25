#!/usr/bin/env python3
"""Control harness for block_second_branch (OWN_SUITE: never bash, so no golden).

REAL REPOSITORIES, BUILT ONCE under a `rediacc_ci.runtmp` run directory: a feature checkout on `0923-1`, a `main` checkout with `0923-1` still live beside it, a clean `main` checkout, a console on `0923-1` holding a nested repository at `private/account` (the submodule shape the coordinated-name rule judges), and a repository outside every console (the `/tmp` exemption). `gh` is stubbed on PATH: one stub answers "no PRs" so liveness comes from the local branches, the other fails, which is the refusal arm.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER. The DEFECT control then plants the guard's own declared `DEFECT` in a copy and requires at least one fire case to flip to allowed; a suite whose green did not depend on the live-count test would pass that copy too.
"""

import datetime
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_second_branch"
GUARD = HERE / ("%s.py" % STEM)

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-second-branch-")

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def git(repo, *args):
    subprocess.run(["git", *args], cwd=str(repo), check=True, capture_output=True, env=GIT_ENV)


def make_repo(branch, extra=(), at=None):
    path = pathlib.Path(at) if at else pathlib.Path(tempfile.mkdtemp(prefix="repo-", dir=RUN_TMP))
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "--initial-branch=main")
    git(path, "commit", "-q", "--allow-empty", "-m", "seed")
    for name in extra:
        git(path, "branch", name)
    if branch != "main":
        git(path, "checkout", "-q", "-B", branch)
    return path


def stub_dir(body):
    d = pathlib.Path(tempfile.mkdtemp(prefix="stub-", dir=RUN_TMP))
    (d / "gh").write_text(body, encoding="utf-8")
    (d / "gh").chmod(0o755)
    return str(d)


GH_EMPTY = stub_dir("#!/bin/sh\nexit 0\n")
GH_DOWN = stub_dir("#!/bin/sh\necho 'gh: offline' >&2\nexit 1\n")

TODAY = datetime.datetime.now().strftime("%m%d")  # noqa: DTZ005 -- the guard reads local time too
NEXT = "%s-1" % TODAY

FEATURE = make_repo("0923-1")
# A second local branch someone already cut: pushing it would make it a second REMOTE one.
FEATURE_EXTRA = make_repo("0923-1", extra=(NEXT,))
MAIN_LIVE = make_repo("main", extra=("0923-1",))
MAIN_CLEAN = make_repo("main")
CONSOLE = make_repo("0923-1")
make_repo("main", at=CONSOLE / "private" / "account")
OUTSIDE = make_repo("main")

CASES = [
    # (name, command, root, gh-stub, expect_blocked) ---- fire ------------------------------
    ("checkout -b from a feature branch", "git checkout -b %s" % NEXT, FEATURE, GH_EMPTY, True),
    ("switch -c from a feature branch", "git switch -c %s" % NEXT, FEATURE, GH_EMPTY, True),
    ("branch <new> from a feature branch", "git branch %s" % NEXT, FEATURE, GH_EMPTY, True),
    ("push creating a remote branch", "git push origin HEAD:%s" % NEXT, FEATURE, GH_EMPTY, True),
    (
        "push -u of a second local branch",
        "git push -u origin %s" % NEXT,
        FEATURE_EXTRA,
        GH_EMPTY,
        True,
    ),
    (
        "gh pr create with another head",
        "gh pr create --draft --head %s" % NEXT,
        FEATURE,
        GH_EMPTY,
        True,
    ),
    ("a sh -c wrapper", "sh -c 'git checkout -b %s'" % NEXT, FEATURE, GH_EMPTY, True),
    ("on main beside a live branch", "git checkout -b %s" % NEXT, MAIN_LIVE, GH_EMPTY, True),
    ("on main, not today's next name", "git checkout -b %s-7" % TODAY, MAIN_CLEAN, GH_EMPTY, True),
    ("gh cannot answer", "git checkout -b %s" % NEXT, MAIN_CLEAN, GH_DOWN, True),
    (
        "a submodule branch off the console's name",
        "git -C private/account checkout -b 0925-9",
        CONSOLE,
        GH_EMPTY,
        True,
    ),
    (
        "a git/refs POST",
        "gh api repos/o/r/git/refs -X POST -f ref=refs/heads/%s -f sha=abc" % NEXT,
        FEATURE,
        GH_EMPTY,
        True,
    ),
    # ---- inverse -----------------------------------------------------------------------------
    (
        "on main with no live branch, today's next",
        "git checkout -b %s" % NEXT,
        MAIN_CLEAN,
        GH_EMPTY,
        False,
    ),
    ("a rename keeps the count at one", "git branch -m 0923-1 %s" % NEXT, FEATURE, GH_EMPTY, False),
    ("a delete", "git branch -d x", FEATURE, GH_EMPTY, False),
    ("a read", "git branch --show-current", FEATURE, GH_EMPTY, False),
    ("pushing the one branch", "git push origin 0923-1", FEATURE, GH_EMPTY, False),
    ("pushing HEAD", "git push -u origin HEAD", FEATURE, GH_EMPTY, False),
    (
        "a submodule branch carrying the console's name",
        "git -C private/account checkout -b 0923-1",
        CONSOLE,
        GH_EMPTY,
        False,
    ),
    (
        "a repository outside the checkout",
        "git -C %s checkout -b anything" % OUTSIDE,
        FEATURE,
        GH_EMPTY,
        False,
    ),
    (
        "F1: a grep for the verbs",
        'grep -n -e "checkout -b" -e "git branch [a-z0-9]" x.py',
        FEATURE,
        GH_EMPTY,
        False,
    ),
    (
        "a heredoc body is data",
        "cat > n.md <<'EOF'\ngit checkout -b %s\nEOF" % NEXT,
        FEATURE,
        GH_EMPTY,
        False,
    ),
    ("an existing name creates nothing", "git branch -f 0923-1 HEAD", MAIN_LIVE, GH_EMPTY, False),
    ("an empty command", "", FEATURE, GH_EMPTY, False),
]

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "assert old in src, 'DEFECT no longer applies'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def run(command, root, gh, broken=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), PATH="%s:%s" % (gh, os.environ["PATH"]))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if broken:
        argv = [
            sys.executable,
            "-c",
            BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), DEFECT, str(GUARD)),
        ]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(argv, input=payload, capture_output=True, text=True, check=False, env=env)
    if broken and proc.returncode not in (0, 2):
        raise SystemExit("broken-copy runner crashed: %s" % proc.stderr[-800:])
    return proc.returncode != 0, proc.stderr


def _declared_defect():
    namespace: dict[str, object] = {}
    for line in GUARD.read_text(encoding="utf-8").split("\n"):
        if line.startswith("DEFECT = "):
            exec(line, namespace)  # noqa: S102 -- the guard's own one-line literal
    return namespace["DEFECT"]


DEFECT = _declared_defect()

fails = 0
blocked = 0
for name, command, root, gh, want in CASES:
    got, err = run(command, root, gh)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-56s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:3])

print()
flipped = [
    name
    for name, command, root, gh, want in CASES
    if want and not run(command, root, gh, broken=True)[0]
]
if flipped:
    print(
        "DEFECT control: planted %r; %d fire case(s) flipped to allowed, e.g. %r"
        % (DEFECT[0], len(flipped), flipped[0])
    )
else:
    print("*** FAIL *** DEFECT control: with %r planted, every fire case still refused" % (DEFECT,))
    fails += 1
if blocked == 0 or blocked == len(CASES):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
