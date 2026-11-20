#!/usr/bin/env python3
"""Control harness for block_landing_one_way (PLAN-two-track-merge-dev LT19), driven through the dispatcher against real repositories.

    python3 .claude/rediacc_hooks/guards/test-block_landing_one_way.py                 rc 0
    python3 .claude/rediacc_hooks/guards/test-block_landing_one_way.py --plant-defect  rc 1: every row runs against a copy with the declared DEFECT

The world: a bare origin, its clone as the main checkout on the development branch 1121-1 (two development-only commits, pushed to origin/1121-1), and a linked landing tree on 1120-1 bound by the landing record. Each refused row also runs from the main checkout and with no record, where it must be admitted, so a refusal is the landing tree's and not the harness's.

The landing tree is made with git's linked-tree verb, so block_worktree_add admits this file only once it is committed.
"""

import ast
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
HOOKS = HERE.parent
DISPATCH = str(HOOKS / "dispatch.py")
STEM = "block_landing_one_way"
GUARD = HERE / ("%s.py" % STEM)
REPO_ROOT = HERE.parents[2]
MESSAGE_MARK = "ASKED:2026-11-20T18:46Z"
PLANT = "--plant-defect" in sys.argv[1:]
LANDING_BRANCH = "1120-1"
DEV = "1121-1"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("%s: %s is missing" % (__file__, path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtmp = _load("runtmp", REPO_ROOT / ".ci" / "rediacc_ci" / "runtmp.py")
TMP = pathlib.Path(os.path.realpath(runtmp.run_dir("guard-landing-one-way-")))

GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
GIT_ENV.pop("COMMIT_POLICY_OK", None)
GIT_ENV.update(
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)

failures: list[str] = []


def _git(*argv, cwd):
    proc = subprocess.run(
        ["git", *argv], cwd=str(cwd), check=False, capture_output=True, text=True, env=GIT_ENV
    )
    if proc.returncode != 0:
        raise SystemExit("fixture: git %s failed in %s: %s" % (" ".join(argv), cwd, proc.stderr))
    return proc.stdout.strip()


def _commit(cwd, name):
    (pathlib.Path(cwd) / name).write_text(name + "\n", encoding="utf-8")
    _git("add", name, cwd=cwd)
    _git("commit", "-qm", name, cwd=cwd)
    return _git("rev-parse", "HEAD", cwd=cwd)


REMOTE = TMP / "remote.git"
MAIN = TMP / "main"
LANDING = TMP / "landing"
_git("init", "-q", "--bare", "-b", "main", str(REMOTE), cwd=TMP)
_git("clone", "-q", str(REMOTE), str(MAIN), cwd=TMP)
_git("checkout", "-q", "-B", "main", cwd=MAIN)
_commit(MAIN, "seed.txt")
_git("push", "-q", "origin", "main", cwd=MAIN)
_git("worktree", "add", "-q", "-b", LANDING_BRANCH, str(LANDING), "main", cwd=MAIN)
_git("push", "-q", "-u", "origin", LANDING_BRANCH, cwd=LANDING)
_git("checkout", "-q", "-b", DEV, cwd=MAIN)
DEV_SHA_1 = _commit(MAIN, "dev-1.txt")
DEV_SHA_2 = _commit(MAIN, "dev-2.txt")
_git("push", "-q", "origin", DEV, cwd=MAIN)
# A lease commit off the landing tip, made without moving any branch: what the landing session cherry-picks.
LEASE_SHA = _git(
    "commit-tree", "-p", LANDING_BRANCH, "-m", "lease fix", "%s^{tree}" % LANDING_BRANCH, cwd=MAIN
)

policy = _load("commit_policy_under_test", HOOKS / "commit_policy.py")
if not hasattr(policy, "write_landing_record"):
    raise SystemExit(
        "FAIL: commit_policy has no landing record (PLAN-two-track-merge-dev LT1 not present)"
    )
RECORD = pathlib.Path(policy.write_landing_record(str(MAIN), str(LANDING), LANDING_BRANCH))

# Refused in the landing tree: (name, command).
REFUSED = [
    ("rebase onto development", "git rebase %s" % DEV),
    ("rebase --onto development", "git rebase --onto %s HEAD" % DEV),
    ("merge development", "git merge %s" % DEV),
    ("merge --ff-only origin/development", "git merge --ff-only origin/%s" % DEV),
    ("merge a revision off development", "git merge %s~1" % DEV),
    ("merge a development sha", "git merge %s" % DEV_SHA_1),
    ("cherry-pick development", "git cherry-pick %s" % DEV),
    ("cherry-pick a development sha", "git cherry-pick -x %s" % DEV_SHA_1),
    ("cherry-pick a range", "git cherry-pick %s..%s" % (LANDING_BRANCH, DEV_SHA_2)),
    ("reset to development", "git reset --hard %s" % DEV),
    ("reset to a development sha", "git reset --keep %s" % DEV_SHA_2),
    ("pull development", "git pull origin %s" % DEV),
    ("pull --rebase development", "git pull --rebase origin %s:x" % DEV),
    ("a wrapper", "sh -c 'git merge %s'" % DEV),
    ("global options", "git -c a=b --no-pager merge %s" % DEV),
    ("a chain", "git status && git rebase %s" % DEV),
]

# Admitted in the landing tree.
ALLOWED = [
    ("rebase onto origin/main", "git rebase origin/main"),
    ("rebase continue", "git rebase --continue"),
    ("reset to HEAD", "git reset --hard HEAD"),
    ("reset of paths", "git reset -- seed.txt"),
    ("merge main", "git merge main"),
    ("cherry-pick a lease commit", "git cherry-pick -x %s" % LEASE_SHA),
    ("pull with no source", "git pull"),
    ("pull the landing branch", "git pull origin %s" % LANDING_BRANCH),
    ("push the landing branch", "git push origin %s" % LANDING_BRANCH),
    ("push bare", "git push"),
    ("push the development branch", "git push origin %s" % DEV),
    ("status", "git status"),
    ("prose", "echo git merge %s" % DEV),
    ("a log of development", "git log %s" % DEV),
]


def _payload(command, cwd):
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})


# The declared DEFECT applied to a copy, the whole guard otherwise unchanged.
BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id == 'DEFECT' for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert cut and old in outside, 'DEFECT no longer applies outside its own declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def _declared_defect():
    for node in ast.parse(GUARD.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "DEFECT" for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise SystemExit("%s declares no DEFECT" % GUARD)


DEFECT_PAIR = _declared_defect()
ENV = dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(LANDING))


def run_guard(command, cwd, defect=None):
    payload = _payload(command, cwd)
    if defect is not None:
        code = BROKEN_RUNNER % (str(HOOKS.parent), str(GUARD), defect, str(GUARD))
        argv = [sys.executable, "-c", code]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(
        argv, input=payload, capture_output=True, text=True, check=False, env=ENV, cwd=str(cwd)
    )
    if proc.returncode not in (0, 2):
        print("*** CRASH *** rc=%d %r\n%s" % (proc.returncode, command, proc.stderr[-800:]))
        failures.append("crash: %s" % command)
    return proc.returncode, proc.stderr


def check(name, want_blocked, command, cwd):
    rc, err = run_guard(command, cwd, defect=DEFECT_PAIR if PLANT else None)
    blocked = rc == 2
    fine = blocked == want_blocked
    if blocked and MESSAGE_MARK not in err:
        fine = False
    if not want_blocked and err:
        fine = False
    print(
        "%-52s want=%-8s got=%-8s %s"
        % (
            name[:52],
            "BLOCKED" if want_blocked else "allowed",
            "BLOCKED" if blocked else "allowed",
            "ok" if fine else "*** FAIL ***",
        )
    )
    if not fine:
        failures.append(name)
        print("    command: %r\n    stderr: %s" % (command, err.strip()[:600]))
    return blocked


print("== refused in the landing tree (%d rows)" % len(REFUSED))
for row_name, row_command in REFUSED:
    check(row_name, True, row_command, LANDING)
check(
    "-C into the landing tree from the main checkout",
    True,
    "git -C %s merge %s" % (LANDING, DEV),
    MAIN,
)
check("cd into the landing tree", True, "cd %s && git rebase %s" % (LANDING, DEV), MAIN)

print("== admitted in the landing tree (%d rows)" % len(ALLOWED))
for row_name, row_command in ALLOWED:
    check(row_name, False, row_command, LANDING)

print("== the refused commands from the main checkout")
for row_name, row_command in REFUSED:
    check("main: %s" % row_name, False, row_command, MAIN)

print("== a push after the landing branch took development commits")
_git("merge", "-q", "--ff-only", DEV, cwd=LANDING)
PUSH_REFUSED = [
    ("push the landing branch", "git push origin %s" % LANDING_BRANCH),
    ("push bare", "git push"),
    ("push HEAD", "git push origin HEAD"),
    ("push to main", "git push origin %s:main" % LANDING_BRANCH),
    ("push -u", "git push -u origin %s" % LANDING_BRANCH),
    ("push development onto the landing branch", "git push origin %s:%s" % (DEV, LANDING_BRANCH)),
    (
        "push refs/heads development onto the landing branch",
        "git push origin refs/heads/%s:%s" % (DEV, LANDING_BRANCH),
    ),
    ("push development onto main", "git push origin %s:main" % DEV),
]
for row_name, row_command in PUSH_REFUSED:
    check("taken: %s" % row_name, True, row_command, LANDING)
check("taken: push the development branch", False, "git push origin %s" % DEV, LANDING)
_git("reset", "-q", "--hard", "origin/%s" % LANDING_BRANCH, cwd=LANDING)

print("== the stacked flow: a landing commit the development branch rebased onto before the push")
_commit(LANDING, "fix-1.txt")
_git("rebase", "-q", LANDING_BRANCH, cwd=MAIN)
check("stacked: push the landing fix", False, "git push origin %s" % LANDING_BRANCH, LANDING)
check("stacked: push bare", False, "git push", LANDING)
check("stacked: rebase onto development still refused", True, "git rebase %s" % DEV, LANDING)

if PLANT:
    print("\n%d rows failed with the DEFECT planted" % len(failures))
    sys.exit(1 if failures else 0)

print("== the chain carries it")
listing = subprocess.run(
    [sys.executable, DISPATCH, "--list"], capture_output=True, text=True, check=False, env=ENV
)
listed = [line for line in listing.stdout.splitlines() if STEM in line]
if not (listed and listed[0].split()[0] == "pre-bash"):
    failures.append("not on the pre-bash chain")
    print("*** FAIL *** %s is not listed on pre-bash: %r" % (STEM, listed))
else:
    print("listed: %s" % " ".join(listed[0].split()))

print("== the DEFECT control")
kept = [n for n, c in REFUSED if run_guard(c, LANDING, defect=DEFECT_PAIR)[0] != 0]
if kept:
    failures.append("defect control")
    print("*** FAIL *** with %r planted these still refuse: %r" % (DEFECT_PAIR, kept[:5]))
else:
    print("planted %r: all %d refusals flipped" % (DEFECT_PAIR[0], len(REFUSED)))
planted = subprocess.run(
    [sys.executable, __file__, "--plant-defect"], capture_output=True, text=True, check=False
)
if planted.returncode != 1:
    failures.append("the planted suite stayed green")
    print("*** FAIL *** the suite with the DEFECT planted exited %d" % planted.returncode)
else:
    print("the whole suite with the DEFECT planted: rc=1")

print("== no record: every refused command is admitted")
RECORD.unlink()
for row_name, row_command in REFUSED:
    check("no record: %s" % row_name, False, row_command, LANDING)

print("\n%d failure(s)" % len(failures))
sys.exit(1 if failures else 0)
