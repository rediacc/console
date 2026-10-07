#!/usr/bin/env python3
"""Control harness for block_unpushed_submodule_pin (OWN_SUITE: never bash, so no golden).

LOAD-BEARING, NOT OPTIONAL. The guard declares `OWN_SUITE = True`, so `test_guards_differential.py` requires this file beside it, `test_hooks_delegates.py` discovers and runs it, and `check_hook_integrity.py` credits the guard with both directions because it exists.

THE 6a94a96a9 SHAPE, REBUILT ON DISK. A console-shaped superproject on branch `0923-1` whose last commit bumps the `private/renet` gitlink to a renet commit no `refs/remotes/*` branch in the renet clone reaches. That is the push that cost the 2026-09-28 CI round. The same world is then moved one step at a time -- the pin published, the remote ref gone, the submodule deinitialized -- and each step asserts the verdict the guard's header promises for it.

NOTHING HERE PUSHES. Remote-tracking refs are written with `update-ref`, which is exactly what a real `git push` or `git fetch` leaves behind in the clone; a fixture that really pushed would itself be a push the live chain judges.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, the thing that actually runs.
"""

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_unpushed_submodule_pin"]

# `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those): a pid-stamped run directory, removed at exit and swept by the next run when this one was killed first.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-submodule-pin-")

ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)
BRANCH = "0923-1"


def git(cwd, *args):
    # check=True: fixture steps, not assertions. A failed setup must abort loudly rather than leave a world every later case misreads.
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, env=ENV
    ).stdout.strip()


def build():
    """Console on `0923-1`, `private/renet` bumped from a published sha to a local-only one."""
    root = tempfile.mkdtemp(prefix="console-", dir=RUN_TMP)
    git(root, "init", "-q", "--initial-branch=main")
    pathlib.Path(root, "seed.txt").write_text("seed\n", encoding="utf-8")
    git(root, "add", "seed.txt")
    sub = os.path.join(root, "private", "renet")
    os.makedirs(sub)
    git(sub, "init", "-q", "--initial-branch=main")
    git(sub, "commit", "-q", "--allow-empty", "-m", "published")
    old = git(sub, "rev-parse", "HEAD")
    git(sub, "update-ref", "refs/remotes/origin/main", old)
    git(sub, "commit", "-q", "--allow-empty", "-m", "pin target, local only")
    new = git(sub, "rev-parse", "HEAD")
    # Detached, as `git submodule update` leaves a real submodule: the refusal then names the console's branch as the destination.
    git(sub, "checkout", "-q", "--detach", new)
    git(root, "update-index", "--add", "--cacheinfo", "160000,%s,private/renet" % old)
    git(root, "commit", "-q", "-m", "pin published")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "-b", BRANCH)
    git(root, "update-ref", "refs/remotes/origin/%s" % BRANCH, "HEAD")
    git(root, "update-index", "--cacheinfo", "160000,%s,private/renet" % new)
    git(root, "commit", "-q", "-m", "feat(ceph): bump renet")
    return root, sub, old, new


def run(root, command, cwd=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    if cwd is not None:
        payload["cwd"] = cwd
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode, proc.stderr


cases: list[tuple[bool, int, int, str, str]] = []


def check(want, root, command, label, cwd=None, expect_in=()):
    rc, err = run(root, command, cwd)
    ok = rc == want and all(s in err for s in expect_in)
    cases.append((ok, want, rc, label, err))


PUSH = "git push origin %s" % BRANCH

# --- the incident: a gitlink to a sha no remote-tracking branch reaches ------
root, sub, old, new = build()
check(
    2,
    root,
    PUSH,
    "the 6a94a96a9 shape: pinned sha absent from every refs/remotes/* branch",
    expect_in=(
        "private/renet -> %s" % new,
        "git -C private/renet push origin %s:refs/heads/%s" % (new, BRANCH),
        "git -C private/renet fetch origin",
    ),
)
check(2, root, "git push", "a bare push publishes the same tip")
check(2, root, "git push origin HEAD:%s" % BRANCH, "an explicit HEAD:<branch> refspec")
check(2, root, "git push -u origin %s" % BRANCH, "-u does not change what is published")
check(2, root, "sh -c 'git push origin %s'" % BRANCH, "a wrapper payload is walked")
check(2, root, "git -C %s push origin %s" % (root, BRANCH), "-C naming the console itself")
check(2, root, PUSH, "the payload cwd inside the console is still the console", cwd=root)

# --- out of scope: nothing here publishes a console tip ----------------------
check(0, root, "git push --dry-run origin %s" % BRANCH, "a dry run")
check(0, root, "git push -n origin %s" % BRANCH, "a dry run, short flag")
check(0, root, "git push origin --delete %s" % BRANCH, "a delete")
check(0, root, "git push --tags origin", "tags only")
# git's own parse of the push (#9de9a8e9), each measured on git 2.53.0: the last of a flag and its negation wins, a unique prefix is the option, a bundle carries it, and `--tags` beside a refspec still pushes the branch.
check(2, root, "git push -n --no-dry-run origin %s" % BRANCH, "a dry run undone by --no-dry-run")
check(2, root, "git push -d --no-delete origin %s" % BRANCH, "a delete undone by --no-delete")
check(2, root, "git push --tags origin %s" % BRANCH, "--tags beside a refspec pushes it")
check(2, root, "git push --push-o ci.skip origin %s" % BRANCH, "a prefixed value flag")
check(0, root, "git push -fn origin %s" % BRANCH, "a dry run in a bundle")
check(0, root, "git push --dry origin %s" % BRANCH, "a dry run by unique prefix")
check(0, root, "echo 'git push origin %s once renet is up'" % BRANCH, "prose about pushing")
check(0, root, "git log --grep push", "git log mentioning push")
check(0, root, "git -C private/renet push origin %s" % BRANCH, "a push inside the submodule, -C")
check(0, root, "cd private/renet && git push origin %s" % BRANCH, "a push inside the submodule, cd")
check(0, root, PUSH, "the payload cwd inside the submodule makes it the submodule's push", cwd=sub)
check(0, root, "cd %s && git push" % RUN_TMP, "a push in another tree")

# --- the fix: the pin becomes reachable from a remote-tracking branch --------
git(sub, "update-ref", "refs/remotes/origin/%s" % BRANCH, new)
check(0, root, PUSH, "passes once the pinned sha IS a remote-tracking branch tip")
git(sub, "update-ref", "-d", "refs/remotes/origin/%s" % BRANCH)
git(sub, "commit", "-q", "--allow-empty", "-m", "later work")
git(sub, "update-ref", "refs/remotes/origin/%s" % BRANCH, "HEAD")
check(0, root, PUSH, "passes when the pinned sha is an ANCESTOR of a remote branch")
git(sub, "update-ref", "-d", "refs/remotes/origin/%s" % BRANCH)
check(2, root, PUSH, "control: removing that remote ref brings the refusal back")

# --- unchanged pins are not re-litigated -------------------------------------
git(root, "update-ref", "refs/remotes/origin/%s" % BRANCH, "HEAD")
pathlib.Path(root, "later.txt").write_text("x\n", encoding="utf-8")
git(root, "add", "later.txt")
git(root, "commit", "-q", "-m", "an ordinary commit")
check(0, root, PUSH, "a push whose pins the remote ref already records")
git(root, "update-ref", "refs/remotes/origin/%s" % BRANCH, "HEAD~2")
check(2, root, PUSH, "control: the same push with the bump still unpublished")

# --- fail open: questions this machine cannot answer -------------------------
git(root, "update-ref", "-d", "refs/remotes/origin/%s" % BRANCH)
check(2, root, PUSH, "a first push of the branch is judged against origin/main")
git(root, "update-ref", "-d", "refs/remotes/origin/main")
check(0, root, PUSH, "no remote-tracking ref at all: fail open")
git(root, "update-ref", "refs/remotes/origin/main", "HEAD~2")
git(root, "checkout", "-q", "--detach")
check(0, root, "git push", "a detached HEAD on a bare push: fail open")
check(2, root, "git push origin HEAD:%s" % BRANCH, "a detached HEAD with an explicit refspec")
git(root, "checkout", "-q", BRANCH)
check(0, root, "git push origin no-such-branch", "a source that does not resolve: fail open")
shutil.move(os.path.join(sub, ".git"), os.path.join(RUN_TMP, "renet-gitdir"))
check(0, root, PUSH, "an uninitialized submodule directory: fail open")
shutil.move(os.path.join(RUN_TMP, "renet-gitdir"), os.path.join(sub, ".git"))
check(2, root, PUSH, "control: the reinitialized submodule refuses again")
git(root, "update-index", "--cacheinfo", "160000,%s,private/renet" % ("1" * 40))
git(root, "commit", "-q", "-m", "pin an object this clone never had")
check(0, root, PUSH, "a pinned object absent from the clone: fail open")

shutil.rmtree(root, ignore_errors=True)

fails = 0
blocked = 0
for ok, want, rc, label, err in cases:
    blocked += rc == 2
    fails += not ok
    print("%-78s want=%d got=%d %s" % (label, want, rc, "ok" if ok else "*** FAIL ***"))
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[:6])

print()
# ANTI-VACUITY: a suite whose every case got one answer compared the guard against a constant.
if blocked in (0, len(cases)):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every input."
        % (blocked, len(cases)),
        file=sys.stderr,
    )
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(cases), blocked, len(cases) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
