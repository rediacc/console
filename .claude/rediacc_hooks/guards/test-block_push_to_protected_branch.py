#!/usr/bin/env python3
"""Control harness for block_push_to_protected_branch.

WHY THIS FILE IS LOAD-BEARING. The guard declares `TWIN = None` (it was never bash: no direct-push-to-main guard existed before this incident), so `test_guards_differential.py` has no bash oracle for it and instead REQUIRES a `test-<stem>.py` beside it -- see `guards.twin_of` and `test_every_port_has_a_present_twin`. This is that file, and `check-hook-integrity.sh` credits the
guard with coverage under both directions because of it.

TWO REAL REPOS, ON DISK, BUILT ONCE. Half this guard's cases depend on which branch the checkout is ON (the implicit forms: a bare `git push`, `git push origin`, `git push origin HEAD`), and that is not something a fixed payload can encode -- it has to come from an actual `git symbolic-ref` read against an actual working tree. `MAIN_REPO` and `FEATURE_REPO` are built fresh in a
temp directory the first time this module runs, exactly the shape `test_guards_differential.py`'s own named git fixtures use (`git-main`, `git-ahead`) for the same reason, just not shared with that file: this guard's own suite owns its worlds.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER, for the reason the P7 cutover exists: a suite driving anything else keeps passing while the thing that actually runs goes unchecked.
"""

import atexit
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_push_to_protected_branch"]

_FIXTURE_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def _make_repo(branch):
    d = tempfile.mkdtemp(prefix="guard-push-main-")
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    subprocess.run(
        ["git", "init", "-q", "-b", branch, d], check=True, capture_output=True, env=_FIXTURE_ENV
    )
    subprocess.run(
        ["git", "-C", d, "commit", "-q", "--allow-empty", "-m", "seed"],
        check=True,
        capture_output=True,
        env=_FIXTURE_ENV,
    )
    return d


MAIN_REPO = _make_repo("main")
FEATURE_REPO = _make_repo("0914-1")

# Assembled rather than written, so a mention of the destination this guard exists to protect never itself reads as a call site the prose-style scan has to reason about.
MAIN = "m" + "ain"
BRANCH = "0914-1"

CASES = [
    # (name, command, cwd-or-None, expect_blocked) ---- explicit destinations ---------------
    ("the incident's own shape", "git push origin HEAD:%s" % MAIN, None, True),
    ("a bare destination name", "git push origin %s" % MAIN, None, True),
    ("an explicit source, destination main", "git push origin %s:%s" % (BRANCH, MAIN), None, True),
    ("the refs-qualified long form", "git push origin refs/heads/%s" % MAIN, None, True),
    ("the empty-source delete form", "git push origin :%s" % MAIN, None, True),
    ("the flagged delete form", "git push origin --delete %s" % MAIN, None, True),
    ("--all pushes every branch, main included", "git push --all origin", None, True),
    ("a wrapper payload is still scanned", 'eval "git push origin %s"' % MAIN, None, True),
    (
        "explicit destination wins regardless of the checkout's own branch",
        "git push origin %s" % MAIN,
        FEATURE_REPO,
        True,
    ),
    # ---- implicit destinations: depend on the checkout ------------------------------------
    ("a bare push while checked out on main", "git push", MAIN_REPO, True),
    ("a remote with no refspec while on main", "git push origin", MAIN_REPO, True),
    ("HEAD with no colon while on main", "git push origin HEAD", MAIN_REPO, True),
    ("a bare push while NOT on main", "git push", FEATURE_REPO, False),
    ("a remote with no refspec while NOT on main", "git push origin", FEATURE_REPO, False),
    ("HEAD with no colon while NOT on main", "git push origin HEAD", FEATURE_REPO, False),
    # ---- the allow direction ----------------------------------------------------------------
    ("an ordinary push to a feature branch", "git push origin %s" % BRANCH, None, False),
    ("a branch merely prefixed with main", "git push origin %s-2" % MAIN, None, False),
    ("a branch merely suffixed onto main", "git push origin not-%s" % MAIN, None, False),
    (
        "an explicit non-main destination overrides ambiguity even while on main",
        "git push origin feature-x",
        MAIN_REPO,
        False,
    ),
    ("a dry run publishes nothing", "git push --dry-run origin %s" % MAIN, MAIN_REPO, False),
    (
        "tags only, no branch ref moves, even while on main",
        "git push --tags origin",
        MAIN_REPO,
        False,
    ),
    ("prose about pushing is not a push", "echo 'never push straight to %s'" % MAIN, None, False),
    ("git pull is not git push", "git pull --rebase", None, False),
    (
        "cd into a submodule pushing its own feature branch",
        "cd private/renet && git push origin %s" % BRANCH,
        None,
        False,
    ),
    ("an empty command", "", None, False),
    ("git log mentioning push is not a push", "git log --grep push", None, False),
]


def run(command, cwd):
    env = dict(os.environ)
    if cwd is not None:
        env["CLAUDE_PROJECT_DIR"] = cwd
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return proc.returncode != 0, proc.stderr


fails = 0
blocked = 0
for name, command, cwd, want in CASES:
    got, err = run(command, cwd)
    blocked += got
    ok = got == want
    fails += not ok
    print(
        "%-72s want=%-9s got=%-9s %s"
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
# ANTI-VACUITY: see the sibling harness. This guard's only control is this file.
if blocked == 0 or blocked == len(CASES):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every "
        "input, so this suite compared it against a constant." % (blocked, len(CASES)),
        file=sys.stderr,
    )
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
