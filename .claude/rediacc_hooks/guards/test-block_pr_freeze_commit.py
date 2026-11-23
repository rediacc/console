#!/usr/bin/env python3
"""Control harness for block_pr_freeze_commit (PLAN-two-track-merge-dev F2, keyed on the landing tree's role by PLAN-simple-two-tree-loop B1): the F1 case table, driven through the dispatcher against a main checkout and a linked landing tree bound by a landing record, with a `gh` stub on PATH answering the landing branch's open PRs.

Both directions: a guard that always refuses passes the refusal rows, one that never refuses passes the admit rows, so each row is asserted. CONTROL rows run the same feat commit in the development tree, and in the landing tree with no open PR, so a refusal is the freeze's and not the harness's; an UNKNOWN row (gh fails) must refuse, since an unchecked PR state is never read as "no PR".
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import _hookpath

from rediacc_hooks.guards import _harness
from rediacc_hooks.tests.fixtures.guards.loader import load_table

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_pr_freeze_commit"]


def _commit_policy():
    """commit_policy.py by path (stdlib imports only): the one writer of the landing record."""
    path = pathlib.Path(__file__).resolve().parents[1] / "commit_policy.py"
    spec = importlib.util.spec_from_file_location("harness_commit_policy", path)
    if spec is None or spec.loader is None:
        raise ImportError("%s is missing" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


commit_policy = _commit_policy()

BRANCH = "1120-1"
DEV_BRANCH = "1120-2"
IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
ESCAPE_MARK = "landing --promote"
GH_STUB = (
    '#!/bin/sh\ncat "$(dirname "$0")/../gh-answer.json"\nexit "$(cat "$(dirname "$0")/../gh-rc")"\n'
)


def _world(tmp, answer='[{"number": 605}]', rc=0):
    """(landing, store): `tmp`/main on DEV_BRANCH, `tmp`/landing a linked tree on BRANCH bound by the record, and the gh stub answering `answer` with exit `rc`."""
    tmp = pathlib.Path(os.path.realpath(tmp))
    main = tmp / "main"
    subprocess.run(["git", "init", "-q", "-b", DEV_BRANCH, str(main)], check=True)
    (main / ".ci" / "policy").mkdir(parents=True)
    (main / ".ci" / "policy" / "record-paths.json").write_text(
        json.dumps({"version": 1, "records": [{"glob": "agent/reviews/**", "except": []}]})
    )
    subprocess.run(["git", "-C", str(main), "add", "."], check=True)
    subprocess.run(["git", "-C", str(main), *IDENT, "commit", "-q", "-m", "base"], check=True)
    landing = tmp / "landing"
    worktree_add = ["git", "-C", str(main), "worktree", "add", "-q", "-b", BRANCH]
    subprocess.run([*worktree_add, str(landing)], check=True)
    commit_policy.write_landing_record(str(main), str(landing), BRANCH)
    (tmp / "bin").mkdir()
    (tmp / "bin" / "gh").write_text(GH_STUB)
    (tmp / "bin" / "gh").chmod(0o755)
    set_gh(tmp, answer, rc)
    store = tmp / "store"
    store.mkdir()
    return landing, store


def set_gh(tmp, answer, rc=0):
    (pathlib.Path(tmp) / "gh-answer.json").write_text(answer)
    (pathlib.Path(tmp) / "gh-rc").write_text(str(rc))


def run(repo, store, cmd, cwd=None, extra_env=None):
    env = dict(
        os.environ,
        CLAUDE_PROJECT_DIR=str(repo),
        WORKLIST_STORE_DIR=str(store),
        TMPDIR=str(store.parent),
        PATH="%s%s%s" % (store.parent / "bin", os.pathsep, os.environ["PATH"]),
        **(extra_env or {}),
    )
    p = _harness.run(
        GUARD_ARGV,
        input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd or repo)}
        ),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
    )
    return p.returncode != 0, p.stdout + p.stderr


CASES = load_table("block_pr_freeze_commit", "CASES")


def main():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        repo, store = _world(tmp)
        for name, cmd, want in CASES:
            got, out = run(repo, store, cmd)
            if got != want:
                fails.append("%s: blocked=%s, want %s\n%s" % (name, got, want, out[-400:]))
            elif want and ESCAPE_MARK not in out:
                fails.append("%s: the refusal does not name the escape\n%s" % (name, out[-400:]))
        # A -F <file> message is read off disk.
        msgfile = pathlib.Path(tmp) / "msg.txt"
        msgfile.write_text("feat(ci): from a file\n")
        got, out = run(repo, store, "git commit -F %s -- f.txt" % msgfile)
        if not got:
            fails.append("-F file feat: not refused\n%s" % out[-400:])
        # A relative -F file beside the tool call's cwd (review 84a5679f.4).
        sub = repo / "sub"
        sub.mkdir()
        (sub / "rel-msg.txt").write_text("feat(ci): relative to the cwd\n")
        got, out = run(repo, store, "git commit -F rel-msg.txt -- f.txt", cwd=sub)
        if not got:
            fails.append("-F file relative to the cwd: not refused\n%s" % out[-400:])
        # No pathspec: the staged paths are judged (review 84a5679f.3): a staged record file alone is admitted, a staged code file is refused.
        rec = repo / "agent" / "reviews" / "1120-1" / "clean.jsonl"
        rec.parent.mkdir(parents=True)
        rec.write_text("{}\n")
        subprocess.run(["git", "-C", str(repo), "add", str(rec)], check=True)
        got, out = run(repo, store, "git commit -m 'feat(ci): records only, no pathspec'")
        if got:
            fails.append("no pathspec, staged record file: refused\n%s" % out[-400:])
        (repo / "code.py").write_text("x = 1\n")
        subprocess.run(["git", "-C", str(repo), "add", "code.py"], check=True)
        got, out = run(repo, store, "git commit -m 'feat(ci): code, no pathspec'")
        if not got:
            fails.append("no pathspec, staged code file: not refused\n%s" % out[-400:])
    with tempfile.TemporaryDirectory() as tmp:
        # -a: unstaged tracked changes join the judged paths (review b5f9d11c.2).
        repo, store = _world(tmp)
        ident = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        (repo / "tracked.py").write_text("x = 1\n")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.py"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), *ident, "commit", "-q", "-m", "fix: tracked"], check=True
        )
        (repo / "tracked.py").write_text("x = 2\n")
        rec = repo / "agent" / "reviews" / "1120-1" / "clean.jsonl"
        rec.parent.mkdir(parents=True)
        rec.write_text("{}\n")
        subprocess.run(["git", "-C", str(repo), "add", str(rec)], check=True)
        got, out = run(repo, store, "git commit -m 'feat(ci): records only'")
        if got:
            fails.append(
                "-a absent: the staged record file alone must be admitted\n%s" % out[-400:]
            )
        got, out = run(repo, store, "git commit -a -m 'feat(ci): records and tracked.py'")
        if not got:
            fails.append(
                "-a: the unstaged tracked.py must join the paths and refuse the feat\n%s"
                % out[-400:]
            )
        # Git cannot list the paths (a corrupt index): judged with none, so a feat is refused and a fix admitted (review b5f9d11c.1/.3).
        bad = pathlib.Path(tmp) / "corrupt-index"
        bad.write_bytes(b"not an index")
        got, out = run(
            repo,
            store,
            "git commit -m 'feat(ci): unlistable'",
            extra_env={"GIT_INDEX_FILE": str(bad)},
        )
        if not got:
            fails.append("unlistable paths: a feat must be refused\n%s" % out[-400:])
        got, out = run(
            repo,
            store,
            "git commit -m 'fix(ci): unlistable'",
            extra_env={"GIT_INDEX_FILE": str(bad)},
        )
        if got:
            fails.append("unlistable paths: a fix must be admitted\n%s" % out[-400:])
    with tempfile.TemporaryDirectory() as tmp:
        landing, store = _world(tmp)
        feat = "git commit -m 'feat(ci): a feature' -- f.txt"
        main = landing.parent / "main"
        got, out = run(main, store, feat)
        if got:
            fails.append(
                "CONTROL: the development tree must admit the feat the landing tree refuses\n%s"
                % out[-400:]
            )
        got, out = run(landing, store, feat)
        if not got:
            fails.append("the landing tree with PR 605 open must refuse the feat\n%s" % out[-400:])
        set_gh(store.parent, "[]")
        got, out = run(landing, store, feat)
        if got:
            fails.append(
                "CONTROL: with no open PR the landing tree must admit the feat\n%s" % out[-400:]
            )
        set_gh(store.parent, "", rc=1)
        got, out = run(landing, store, feat)
        if not got or "unknown" not in out:
            fails.append(
                "UNKNOWN: a gh that fails must refuse the feat, naming why\n%s" % out[-400:]
            )
        got, out = run(landing, store, "git commit -m 'fix(ci): a repair' -- f.txt")
        if got:
            fails.append("UNKNOWN: a fix needs no PR read and must be admitted\n%s" % out[-400:])
    for f in fails:
        print("FAIL", f)
    total = len(CASES) + 13
    if fails:
        print("%d of %d case(s) failed" % (len(fails), total))
        return 1
    print("%d case(s) passed" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
