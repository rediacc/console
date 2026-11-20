#!/usr/bin/env python3
"""Control harness for block_pr_freeze_commit (PLAN-two-track-merge-dev F2): the F1 case table, driven through the dispatcher against a scratch repository and a planted babysit phase event.

Both directions: a guard that always refuses passes the refusal rows, one that never refuses passes the admit rows, so each row is asserted. A CONTROL row runs the same feat commit with no phase, so a refusal is the freeze's and not the harness's.
"""

import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile

DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_pr_freeze_commit"]
BRANCH = "1120-1"
OWNER = "d778be9d"


def _now():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _world(tmp, phase=True):
    repo = pathlib.Path(tmp) / "repo"
    subprocess.run(["git", "init", "-q", "-b", BRANCH, str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "base",
        ],
        check=True,
    )
    (repo / ".ci" / "policy").mkdir(parents=True)
    (repo / ".ci" / "policy" / "record-paths.json").write_text(
        json.dumps({"version": 1, "records": [{"glob": "agent/reviews/**", "except": []}]})
    )
    store = pathlib.Path(tmp) / "store"
    store.mkdir()
    if phase:
        ev = {
            "ev": "phase",
            "at": _now(),
            "by": OWNER,
            "o": OWNER,
            "mode": "babysit",
            "branch": BRANCH,
            "pr": 605,
            "why": "test",
            "h": "0",
            "br": BRANCH,
            "ns": 2,
        }
        (store / ("%s.jsonl" % OWNER)).write_text(json.dumps(ev) + "\n")
    return repo, store


def run(repo, store, cmd):
    env = dict(
        os.environ,
        CLAUDE_PROJECT_DIR=str(repo),
        WORKLIST_STORE_DIR=str(store),
        TMPDIR=str(store.parent),
    )
    p = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(repo)}),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        check=False,
    )
    return p.returncode != 0, p.stdout + p.stderr


CASES = [
    # (name, command, expect_blocked)
    ("feat refused", "git commit -m 'feat(ci): a new thing' -- f.txt", True),
    ("chore(pins) refused", "git commit -m 'chore(pins): bump npm' -- f.txt", True),
    ("fix admitted", "git commit -m 'fix(ci): a fix' -- f.txt", False),
    ("test admitted", "git commit -m 'test(ci): a test' -- f.txt", False),
    ("chore(reviews) admitted", "git commit -m 'chore(reviews): records' -- f.txt", False),
    ("chore(plans) admitted", "git commit -m 'chore(plans): tick' -- f.txt", False),
    (
        "record paths only admitted",
        "git commit -m 'feat(ci): records' -- agent/reviews/1120-1/clean.jsonl",
        False,
    ),
    ("not a commit", "git status", False),
    ("prose about a commit is not a commit", "echo 'git commit -m feat(x): y'", False),
]


def main():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        repo, store = _world(tmp)
        for name, cmd, want in CASES:
            got, out = run(repo, store, cmd)
            if got != want:
                fails.append("%s: blocked=%s, want %s\n%s" % (name, got, want, out[-400:]))
            elif want and "worklist.py --phase <me> build" not in out:
                fails.append("%s: the refusal does not name the escape\n%s" % (name, out[-400:]))
        # A -F <file> message is read off disk.
        msgfile = pathlib.Path(tmp) / "msg.txt"
        msgfile.write_text("feat(ci): from a file\n")
        got, out = run(repo, store, "git commit -F %s -- f.txt" % msgfile)
        if not got:
            fails.append("-F file feat: not refused\n%s" % out[-400:])
    with tempfile.TemporaryDirectory() as tmp:
        repo, store = _world(tmp, phase=False)
        got, out = run(repo, store, "git commit -m 'feat(ci): no phase' -- f.txt")
        if got:
            fails.append("CONTROL: with no phase a feat commit must be admitted\n%s" % out[-400:])
    for f in fails:
        print("FAIL", f)
    total = len(CASES) + 2
    if fails:
        print("%d of %d case(s) failed" % (len(fails), total))
        return 1
    print("%d case(s) passed" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
