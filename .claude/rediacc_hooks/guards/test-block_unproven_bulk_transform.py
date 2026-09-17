#!/usr/bin/env python3
"""block_unproven_bulk_transform: both directions, against a real git repo.

HERMETIC BY CONSTRUCTION, the same shape as `test-block_unverified_push.py`: every case runs against a scratch repo with its own tree, its own staged index and (for the range cases) its own commit history and upstream, so this never touches the real repo's index or history. Commit and push are exercised as the guard actually sees them: the commit case stages real files
against a real HEAD before the commit runs, and the range cases build real commits with a real `@{u}` so `_push_target`/`_range_commits` resolve against genuine git state rather than a mock.

TWIN = None ON THE GUARD ITSELF, so this file is the whole differential, exactly as `test-block_prose_style_commit.py` is for its sibling. `check-hook-integrity.sh` reads this file's existence as crediting both directions.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_unproven_bulk_transform"]

BULK = 20  # must match BULK_FILE_THRESHOLD's default


def run(command, cwd):
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode != 0, proc.stderr


def git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=check)


def scratch_repo():
    d = tempfile.mkdtemp()
    git(d, "init", "-q", "-b", "main")
    git(d, "config", "user.email", "p@example.invalid")
    git(d, "config", "user.name", "p")
    with open(os.path.join(d, "base.txt"), "w", encoding="utf-8") as fh:
        fh.write("x\n")
    git(d, "add", "-A")
    git(d, "commit", "-qm", "base")
    return d


def stage_files(repo, n, prefix="f"):
    for i in range(n):
        with open(os.path.join(repo, "%s%d.py" % (prefix, i)), "w", encoding="utf-8") as fh:
            fh.write("x = %d\n" % i)
    git(repo, "add", "-A")


class Tally:
    """A counter object rather than module globals, matching the sibling harnesses' shape."""

    fails = 0
    blocked = 0


def case(name, command, cwd, want_blocked):
    got, err = run(command, cwd)
    Tally.blocked += got
    ok = got == want_blocked
    Tally.fails += not ok
    print(
        "%-70s want=%-9s got=%-9s %s"
        % (
            name,
            "BLOCKED" if want_blocked else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok and err:
        print("    stderr: %s" % err.strip().splitlines()[-3:])


# ---- COMMIT, direct staged-diff check --------------------------------------

repo = scratch_repo()
case("a small commit under threshold", 'git commit -m "fix: a small thing"', repo, False)

stage_files(repo, BULK)
case(
    "a bulk commit with NO proof in its message is blocked",
    'git commit -m "style: reflow the tree"',
    repo,
    True,
)
case(
    "the same staged files, proof quoted, is allowed",
    'git commit -m "style: reflow the tree\n\nshape-cluster diff: 0 files lost a shape"',
    repo,
    False,
)
case(
    "a bare file count is NOT proof",
    'git commit -m "style: reflow the tree, %d files changed"' % BULK,
    repo,
    True,
)
git(repo, "reset", "-q")  # unstage so the next case starts clean
for name in os.listdir(repo):
    if name.startswith("f") and name.endswith(".py"):
        os.remove(os.path.join(repo, name))

stage_files(repo, BULK - 1, prefix="g")
case("one file under threshold is allowed with no proof", 'git commit -m "fix: several files"', repo, False)
git(repo, "reset", "-q")

case("a plain command is not a target", "ls -la", repo, False)
case("gh pr view is not a write", "gh pr view 1", repo, False)
case(
    "a commit message MENTIONING the phrase, but few files, is fine either way",
    'git commit -m "docs: explain shape_cluster_diff.py"',
    repo,
    False,
)

# ---- PUSH, range check over real commit history ----------------------------

push_repo = scratch_repo()
remote = tempfile.mkdtemp()
git(remote, "init", "-q", "--bare")
git(push_repo, "remote", "add", "origin", remote)
git(push_repo, "push", "-q", "-u", "origin", "main")

stage_files(push_repo, BULK, prefix="p")
git(push_repo, "commit", "-qm", "style: bulk rewrite with no proof")
case(
    "a push carrying an unproven bulk commit is blocked",
    "git push",
    push_repo,
    True,
)

# A second scratch repo for the ALLOWED push, so the first repo's now-diverged
# history (it was blocked, never actually pushed) does not contaminate this case.
push_repo2 = scratch_repo()
remote2 = tempfile.mkdtemp()
git(remote2, "init", "-q", "--bare")
git(push_repo2, "remote", "add", "origin", remote2)
git(push_repo2, "push", "-q", "-u", "origin", "main")
stage_files(push_repo2, BULK, prefix="q")
git(push_repo2, "commit", "-qm", "style: bulk rewrite\n\nast-equality proof: 0 mismatches")
case(
    "a push whose bulk commit already quotes proof is allowed",
    "git push",
    push_repo2,
    False,
)

# A push with no upstream at all: UNRESOLVABLE, so allowed rather than guessed.
detached = scratch_repo()
case("a push with no upstream configured is allowed (unresolvable)", "git push origin main", detached, False)

# ---- GH PR CREATE, range check against the default base --------------------

pr_repo = scratch_repo()
git(pr_repo, "branch", "-m", "main")  # already main; documents the base this case relies on
stage_files(pr_repo, BULK, prefix="r")
git(pr_repo, "commit", "-qm", "style: bulk rewrite with no proof")
case(
    "gh pr create against an unresolvable base is allowed (no origin/main exists)",
    "gh pr create --title x --body y",
    pr_repo,
    False,
)

print()
TOTAL_CASES = 12
if Tally.blocked in (0, TOTAL_CASES):
    print(
        "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every "
        "input, so this suite compared it against a constant." % (Tally.blocked, TOTAL_CASES),
        file=sys.stderr,
    )
    Tally.fails += 1
print(
    "%d case(s), %d blocked, %d allowed"
    % (TOTAL_CASES, Tally.blocked, TOTAL_CASES - Tally.blocked)
)
print("FAILURES: %d" % Tally.fails)
sys.exit(1 if Tally.fails else 0)
