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

# M6 OF PLAN-plan-per-pr-loop, THE MERGED-AND-DELETED TRANSITION (operator ruling 2026-10-02: one live branch, 24/7). `gh` answers per question: `--head <b>` gets the previous PR's state, the day's consumed-heads read gets `HEADS`. The previous branch `0923-1` stays local in every world, because whether its REMOTE branch is gone is the fact under test.
GH_OPEN = stub_dir(
    '#!/bin/sh\ncase "$*" in *--head*) echo OPEN;; *headRefName*) echo 0923-1;; esac\n'
)
GH_MERGED = stub_dir(
    '#!/bin/sh\ncase "$*" in *--head*) echo MERGED;; *headRefName*) echo 0923-1;; esac\n'
)
# Today's first branch already merged and deleted: only `gh` still remembers the name (the 0826-1 double take).
GH_MERGED_TODAY = stub_dir(
    '#!/bin/sh\ncase "$*" in *--head*) echo MERGED;; *headRefName*) echo %s-1;; esac\n' % TODAY
)
# Merged, its remote branch still on origin (the remote-tracking ref is present): not yet deleted.
MAIN_MERGED_PRESENT = make_repo("main", extra=("0923-1",))
git(MAIN_MERGED_PRESENT, "update-ref", "refs/remotes/origin/0923-1", "0923-1")
# Merged, its remote branch deleted and pruned: the local branch alone is no longer live.
MAIN_MERGED_DELETED = make_repo("main", extra=("0923-1",))

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
    # ---- M6: the merged-and-deleted transition ----------------------------------------------
    (
        "M6 previous PR merged, its branch deleted: today's next",
        "git checkout -b %s" % NEXT,
        MAIN_MERGED_DELETED,
        GH_MERGED,
        False,
    ),
    (
        "M6 previous PR still open",
        "git checkout -b %s" % NEXT,
        MAIN_MERGED_DELETED,
        GH_OPEN,
        True,
    ),
    (
        "M6 previous PR merged, its remote branch still present",
        "git checkout -b %s" % NEXT,
        MAIN_MERGED_PRESENT,
        GH_MERGED,
        True,
    ),
    (
        "M6 same day: a merged head's name is consumed",
        "git checkout -b %s-1" % TODAY,
        MAIN_CLEAN,
        GH_MERGED_TODAY,
        True,
    ),
    (
        "M6 same day: MAX+1 over the merged head",
        "git checkout -b %s-2" % TODAY,
        MAIN_CLEAN,
        GH_MERGED_TODAY,
        False,
    ),
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

# ---- the git-level twin (.claude/rediacc_hooks/git/reference-transaction), local facts only ----
# M6 at the git layer: a previous branch whose upstream is still on origin is live, so a new cut is refused; once the remote branch is deleted and pruned (`[gone]`) the cut is allowed. The layer has no `gh`, so it cannot see a merge; the remote branch's deletion is the one signal it reads.
HOOKS = HERE.parent / "git"


def git_level(repo, *args):
    env = {k: v for k, v in GIT_ENV.items() if k != "COMMIT_POLICY_OK"}
    proc = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, check=False, env=env
    )
    return proc.returncode != 0 and "commit-policy:" in proc.stderr, proc.stderr


def merged_world(deleted):
    origin = pathlib.Path(tempfile.mkdtemp(prefix="origin-", dir=RUN_TMP))
    git(origin, "init", "-q", "--bare", "--initial-branch=main")
    repo = make_repo("main", extra=("0923-1",))
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "-u", "origin", "0923-1")
    if deleted:
        git(repo, "push", "-q", "origin", "--delete", "0923-1")
        git(repo, "fetch", "-q", "--prune", "origin")
    git(repo, "config", "core.hooksPath", str(HOOKS))
    return repo


GIT_CASES = [
    ("git-level M6: previous branch still on origin", False, True),
    ("git-level M6: previous branch deleted and pruned", True, False),
]
print()
for name, deleted, want in GIT_CASES:
    got, err = git_level(merged_world(deleted), "switch", "-q", "-c", NEXT)
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
CASES = CASES + GIT_CASES

if blocked == 0 or blocked == len(CASES):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
