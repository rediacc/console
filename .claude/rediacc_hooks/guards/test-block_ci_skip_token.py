#!/usr/bin/env python3
"""Control harness for block_ci_skip_token (OWN_SUITE: never bash, so no golden).

Every GitHub skip form, the rejected `[no-ci]`, the `skip-checks: true` trailer (typed and through `--trailer`), and the two message shapes that are not `-m` (a `-F` file on disk and a `-F -` heredoc) must be refused; a mention in prose, `git log --grep` and a commit in a repository outside this checkout must not. Each case drives the live guard through the dispatcher against a real repository under a `rediacc_ci.runtmp` run directory.

THE DEFECT CONTROL plants the guard's declared `DEFECT` (the token finder emptied) in a copy and requires at least one fire case to flip to allowed.
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
STEM = "block_ci_skip_token"
GUARD = HERE / ("%s.py" % STEM)

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-ci-skip-")

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def make_repo(branch):
    path = pathlib.Path(tempfile.mkdtemp(prefix="repo-", dir=RUN_TMP))
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["commit", "-q", "--allow-empty", "-m", "seed"],
        ["checkout", "-q", "-B", branch],
    ):
        subprocess.run(["git", *argv], cwd=str(path), check=True, capture_output=True, env=GIT_ENV)
    return path


REPO = make_repo("0923-1")
OUTSIDE = make_repo("0923-1")
(REPO / "msg.txt").write_text("chore: bump [skip ci]\n", encoding="utf-8")

CASES = [
    # (name, command, expect_blocked) ---- fire ----------------------------------------------
    ("[skip ci]", 'git commit -m "chore: x [skip ci]" -- a', True),
    ("[ci skip]", 'git commit -m "chore: x [ci skip]" -- a', True),
    ("[no ci]", 'git commit -m "chore: x [no ci]" -- a', True),
    ("[skip actions]", 'git commit -m "chore: x [skip actions]" -- a', True),
    ("[actions skip]", 'git commit -m "chore: x [actions skip]" -- a', True),
    ("the rejected [no-ci]", 'git commit -m "chore: x [no-ci]" -- a', True),
    ("upper case", 'git commit -m "chore: x [SKIP CI]" -- a', True),
    ("the skip-checks trailer", 'git commit -m "chore: x\n\nskip-checks: true" -- a', True),
    ("a --trailer value", 'git commit -m "chore: x" --trailer "skip-checks: true" -- a', True),
    ("a -F file on disk", "git commit -F msg.txt -- a", True),
    ("a -F - heredoc", "git commit -F - -- a <<'EOF'\nchore: x [skip ci]\nEOF", True),
    ("a cat-heredoc -m", "git commit -m \"$(cat <<'EOF'\nchore: x [skip ci]\nEOF\n)\" -- a", True),
    # ---- inverse -----------------------------------------------------------------------------
    ("a clean commit", 'git commit -m "chore: x" -- a', False),
    ("echo naming the token", "echo '[skip ci]'", False),
    ("git log --grep", "git log --grep '[skip ci]'", False),
    (
        "a repository outside the checkout",
        'git -C %s commit -m "x [skip ci]" -- a' % OUTSIDE,
        False,
    ),
    ("a heredoc to a file is not a message", "cat > n.md <<'EOF'\n[skip ci]\nEOF", False),
    ("an empty command", "", False),
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
    source = GUARD.read_text(encoding="utf-8")
    start = source.index("DEFECT = ")
    end = source.index(")\n", start) + 1
    exec(source[start:end], namespace)  # noqa: S102 -- the guard's own literal
    return namespace["DEFECT"]


DEFECT = _declared_defect()


def run(command, broken=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(REPO))
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    if broken:
        code = BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), DEFECT, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=env, cwd=str(REPO)
    )
    if broken and proc.returncode not in (0, 2):
        raise SystemExit("broken-copy runner crashed: %s" % proc.stderr[-800:])
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, command, want in CASES:
    got, err = run(command)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-40s want=%-8s got=%-8s %s"
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
flipped = [n for n, c, want in CASES if want and not run(c, broken=True)[0]]
if flipped:
    print(
        "DEFECT control: planted %r; %d fire case(s) flipped, e.g. %r"
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
