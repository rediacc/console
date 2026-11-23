#!/usr/bin/env python3
"""Control harness for block_rebase_over_foreign_dirt: the dirt refusal and the stand-down probe of box R20261123.3 (agent/plans/PLAN-stop-hook-retro-20261123.md).

    python3 .claude/rediacc_hooks/guards/test-block_rebase_over_foreign_dirt.py    rc 0, one line per row

WHAT IT BUILDS. One real main checkout on a development branch, clean, whose `refs/remotes/origin/old` is a base WITHOUT `def operation_in_progress` in `.claude/hooks/stop/wl_git.py` and whose `refs/remotes/origin/main` is a base WITH it, plus a linked tree of the same repository (the landing tree's shape). Each row drives the live guard through the real dispatcher process, so check:ci-guard-mutations' redirect reaches the planted copy.

WHAT EACH PLANT TURNS GREEN INTO RED. The guard's DEFECT (every dirty path exempt) admits the peer-dirt row. MUTANTS `standdown-carried` (every base carries the stand-down) and `standdown-main` (no tree is the main checkout) each admit the main-checkout rows onto the old base. The control rows (a base with the stand-down, `--continue`, `--abort`, the linked tree, an unknown ref) are allowed under every plant, so they prove the rows that fire are judging the base and the tree, not refusing every rebase.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_rebase_over_foreign_dirt"
BRANCH = "0101-1"
WL_GIT_REL = ".claude/hooks/stop/wl_git.py"
STANDDOWN_MARK = "would rebase the main checkout onto"
DIRT_MARK = "would start over uncommitted tracked work"


def _env(project=None):
    env = {
        k: v for k, v in os.environ.items() if not k.startswith("GIT_") and k != "COMMIT_POLICY_OK"
    }
    env.update(
        {
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
    )
    # The project directory of every row is set below; an inherited one would point the guard at the live checkout.
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    # Re-applied after the scrub above: check:ci-guard-mutations hands the planted copy through these.
    for key in ("GUARD_MUTANT_TARGET", "GUARD_MUTANT_SOURCE", "GUARD_MUTANT_LOG"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def git(repo, *args):
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=_env(), check=False
    )
    if proc.returncode != 0:
        raise SystemExit("fixture git %s: rc=%d %s" % (args, proc.returncode, proc.stderr))
    return proc.stdout.strip()


def write(repo, rel, text):
    path = pathlib.Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_all(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def build(base):
    repo = base / "console"
    git(base, "init", "-q", "-b", BRANCH, str(repo))
    write(repo, WL_GIT_REL, "def rebase_state(root):\n    return None\n")
    write(repo, "src/app.ts", "v1\n")
    old = commit_all(repo, "chore: base without the stand-down")
    write(repo, WL_GIT_REL, "def operation_in_progress(root):\n    return ''\n")
    fixed = commit_all(repo, "fix: the stand-down")
    git(repo, "update-ref", "refs/remotes/origin/old", old)
    git(repo, "update-ref", "refs/remotes/origin/main", fixed)
    git(repo, "reset", "-q", "--hard", old)
    write(repo, "src/app.ts", "topic\n")
    commit_all(repo, "feat: topic")
    linked = base / "landing"
    git(repo, "worktree", "add", "-q", "--detach", str(linked))
    if git(repo, "status", "--porcelain") or git(linked, "status", "--porcelain"):
        raise SystemExit("the fixture trees are not clean")
    return repo, linked


def guard(cmd, project):
    proc = subprocess.run(
        [sys.executable, DISPATCH, STEM],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=str(project),
        env=_env(project),
        check=False,
        timeout=120,
    )
    return proc.returncode, proc.stderr


def main():
    # Under the TMPDIR the suite is given, and removed whatever the rows answer: check:ci-guard-mutations refuses a pristine run that leaves an entry there.
    base = pathlib.Path(tempfile.mkdtemp(prefix="guard-rebase-dirt-"))
    try:
        return rows_hold(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def rows_hold(base):
    repo, linked = build(base)
    # (label, command, tree, dirty, want rc, mark the refusal must carry)
    rows = [
        (
            "main checkout onto a base without the stand-down",
            "git rebase origin/old",
            repo,
            False,
            2,
            STANDDOWN_MARK,
        ),
        (
            "--onto a base without the stand-down",
            "git rebase --onto origin/old origin/main",
            repo,
            False,
            2,
            STANDDOWN_MARK,
        ),
        (
            "a wrapper payload onto the old base",
            "sh -c 'git rebase origin/old'",
            repo,
            False,
            2,
            STANDDOWN_MARK,
        ),
        (
            "a peer's modified file, base with the stand-down",
            "git rebase origin/main",
            repo,
            True,
            2,
            DIRT_MARK,
        ),
        ("CONTROL: a base with the stand-down", "git rebase origin/main", repo, False, 0, ""),
        ("CONTROL: --continue starts nothing", "git rebase --continue", repo, False, 0, ""),
        ("CONTROL: --abort starts nothing", "git rebase --abort", repo, False, 0, ""),
        (
            "CONTROL: an unknown ref is git's to refuse",
            "git rebase no-such-ref",
            repo,
            False,
            0,
            "",
        ),
        ("CONTROL: the linked tree is never probed", "git rebase origin/old", linked, False, 0, ""),
    ]
    failures = 0
    for label, cmd, tree, dirty, want, mark in rows:
        if dirty:
            write(tree, "src/app.ts", "peer edit\n")
        rc, err = guard(cmd, tree)
        if dirty:
            write(tree, "src/app.ts", "topic\n")
        ok = rc == want and (not mark or mark in err)
        failures += not ok
        print("%s  %-52s rc=%d want=%d" % ("ok  " if ok else "FAIL", label, rc, want))
        if not ok:
            print("    %s" % "\n    ".join(err.strip().splitlines()[:4]))
    if failures:
        print("%d of %d rows failed" % (failures, len(rows)))
        return 1
    print(
        "all %d rows hold (%d refusals, %d controls)"
        % (len(rows), sum(r[4] == 2 for r in rows), sum(r[4] == 0 for r in rows))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
