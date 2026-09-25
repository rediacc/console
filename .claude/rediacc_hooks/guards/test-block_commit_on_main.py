#!/usr/bin/env python3
"""Control harness for block_commit_on_main (OWN_SUITE: never bash, so no golden).

REAL REPOSITORIES under a `rediacc_ci.runtmp` run directory: a checkout on `main`, a feature checkout on `0923-1`, a console on `0923-1` holding a nested repository on `main` at `private/account` (the `git -C private/account commit` case), and a repository on `main` outside every console (the `/tmp` exemption). Each case drives the live guard through the dispatcher.

THE DEFECT CONTROL plants the guard's own declared `DEFECT` in a copy and requires at least one fire case to flip to allowed. The CONFIG CONTROL holds `.ci/config/commit-policy.json` and `commit_policy.DEFAULTS` to one set of values, the promise `commit_policy`'s docstring makes: a guard that fell back to defaults must not quietly enforce a different policy from the file.
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
STEM = "block_commit_on_main"
GUARD = HERE / ("%s.py" % STEM)
REPO = HERE.parents[2]

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", REPO / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-commit-main-")

_POLICY = importlib.util.spec_from_file_location("commit_policy", HERE.parent / "commit_policy.py")
if _POLICY is None or _POLICY.loader is None:
    raise SystemExit("%s: commit_policy.py is missing" % __file__)
commit_policy = importlib.util.module_from_spec(_POLICY)
_POLICY.loader.exec_module(commit_policy)

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


def make_repo(branch, at=None):
    path = pathlib.Path(at) if at else pathlib.Path(tempfile.mkdtemp(prefix="repo-", dir=RUN_TMP))
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "--initial-branch=main")
    git(path, "commit", "-q", "--allow-empty", "-m", "seed")
    if branch != "main":
        git(path, "checkout", "-q", "-b", branch)
    return path


MAIN = make_repo("main")
FEATURE = make_repo("0923-1")
CONSOLE = make_repo("0923-1")
make_repo("main", at=CONSOLE / "private" / "account")
OUTSIDE = make_repo("main")

EVIDENCE = "\n\nHotfix-Evidence: 18012345678"
HOTFIX = 'git commit -m "fix(ci): x [hotfix]%s" -- a.ts' % EVIDENCE

CASES = [
    # (name, command, root, expect_blocked) ---- fire -----------------------------------------
    ("on main, no [hotfix]", 'git commit -m "feat: x" -- a.ts', MAIN, True),
    (
        "a [hotfix] with 6 files",
        'git commit -m "fix: x [hotfix]%s" -- a b c d e f' % EVIDENCE,
        MAIN,
        True,
    ),
    ("a [hotfix] with no Hotfix-Evidence", 'git commit -m "fix: x [hotfix]" -- a.ts', MAIN, True),
    ("a [hotfix] on a feature branch", HOTFIX, FEATURE, True),
    (
        "a submodule on its own main",
        'git -C private/account commit -m "feat: x" -- a.ts',
        CONSOLE,
        True,
    ),
    ("a heredoc message on main", "git commit -F - -- a <<'EOF'\nfeat: x\nEOF", MAIN, True),
    ("an unreadable message on main", "cat m | git commit -F - -- a", MAIN, True),
    ("a wrapper on main", "sh -c 'git commit -m \"feat: x\" -- a'", MAIN, True),
    # ---- inverse -----------------------------------------------------------------------------
    ("the same commit on a feature branch", 'git commit -m "feat: x" -- a.ts', FEATURE, False),
    ("a valid hotfix", HOTFIX, MAIN, False),
    (
        "a valid hotfix with ASKED evidence",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: ASKED:2026-09-25T10:00Z" -- a',
        MAIN,
        False,
    ),
    (
        "a repository outside the checkout",
        'git -C %s commit -m "feat: x" -- a' % OUTSIDE,
        FEATURE,
        False,
    ),
    ("prose about committing on main", "echo 'git commit on main'", MAIN, False),
    ("git log", "git log -n 3", MAIN, False),
    ("an empty command", "", MAIN, False),
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


def _declared_defect():
    namespace: dict[str, object] = {}
    for line in GUARD.read_text(encoding="utf-8").split("\n"):
        if line.startswith("DEFECT = "):
            exec(line, namespace)  # noqa: S102 -- the guard's own one-line literal
    return namespace["DEFECT"]


DEFECT = _declared_defect()


def run(command, root, broken=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if broken:
        code = BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), DEFECT, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(argv, input=payload, capture_output=True, text=True, check=False, env=env)
    if broken and proc.returncode not in (0, 2):
        raise SystemExit("broken-copy runner crashed: %s" % proc.stderr[-800:])
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, command, root, want in CASES:
    got, err = run(command, root)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-44s want=%-8s got=%-8s %s"
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
flipped = [n for n, c, r, want in CASES if want and not run(c, r, broken=True)[0]]
if flipped:
    print(
        "DEFECT control: planted %r; %d fire case(s) flipped, e.g. %r"
        % (DEFECT[0], len(flipped), flipped[0])
    )
else:
    print("*** FAIL *** DEFECT control: with %r planted, every fire case still refused" % (DEFECT,))
    fails += 1

on_disk = commit_policy.load_config(REPO)
if on_disk != commit_policy.DEFAULTS:
    print("*** FAIL *** .ci/config/commit-policy.json and commit_policy.DEFAULTS disagree:")
    for key in sorted(commit_policy.DEFAULTS):
        if on_disk.get(key) != commit_policy.DEFAULTS[key]:
            print(
                "    %s: file %r, defaults %r"
                % (key, on_disk.get(key), commit_policy.DEFAULTS[key])
            )
    fails += 1
else:
    print(
        "config control: .ci/config/commit-policy.json == commit_policy.DEFAULTS (%d keys)"
        % len(on_disk)
    )
raw = json.loads((REPO / ".ci" / "config" / "commit-policy.json").read_text(encoding="utf-8"))
unread = sorted(k for k in raw if not k.startswith("$") and k not in commit_policy.DEFAULTS)
if unread:
    print("*** FAIL *** config keys nothing reads: %s" % unread)
    fails += 1

if blocked == 0 or blocked == len(CASES):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
