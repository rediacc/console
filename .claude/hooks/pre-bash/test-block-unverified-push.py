#!/usr/bin/env python3
"""block-unverified-push.sh: both directions, against a real git repo.

HERMETIC BY CONSTRUCTION. Every case runs against a scratch repo with its own
CLAUDE_PROJECT_DIR, so this never reads or writes the real
.ci/cache/prepush-receipt.json. An earlier draft backed the real one up and
restored it, which works right up until the process is killed between the two
and leaves the session unable to push for a reason nothing explains.

The refusal arms need a receipt planted at a specific tree sha, which is why
they live here rather than in test-hooks.sh: that suite's `check` helper drives
a guard against the live tree with no env or cwd control.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "block-unverified-push.sh")

d = tempfile.mkdtemp()


def git(*a, **kw):
    # check=True: these are fixtures, not assertions. Nothing here inspects a
    # return code, so a failed setup step must abort loudly rather than leave
    # an empty TREE that fails every later case for the wrong reason.
    return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True, check=True, **kw)


git("init", "-q", "-b", "0827-1")
git("config", "user.email", "p@example.invalid")
git("config", "user.name", "p")
with open(os.path.join(d, "f.txt"), "w", encoding="utf-8") as fh:
    fh.write("x\n")
git("add", "-A")
git("commit", "-qm", "base")
TREE = git("rev-parse", "HEAD^{tree}").stdout.strip()

RECEIPT = os.path.join(d, ".ci", "cache", "prepush-receipt.json")


def put(**over):
    base = {
        "headTree": TREE,
        "head": "x",
        "branch": "0827-1",
        "dirtyDigest": "",
        "selection": "--quick",
        "whole": True,
        "exitCode": 0,
        "failed": [],
        "wallMs": 1,
        "finishedAt": "now",
    }
    base.update(over)
    os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    with open(RECEIPT, "w", encoding="utf-8") as fh:
        json.dump(base, fh)


def drop():
    if os.path.exists(RECEIPT):
        os.remove(RECEIPT)


def run(cmd):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
    return subprocess.run(
        ["bash", GUARD],
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=d,
        env=env,
        check=False,
    ).returncode


PUSH = "git push origin 0827-1"
cases = []

# --- the guard's whole purpose -----------------------------------------------
drop()
cases.append((2, run(PUSH), "no receipt at all: nothing has judged this tree"))

put()
cases.append((0, run(PUSH), "a WHOLE, GREEN, tree-matching receipt is honoured"))

put(headTree="0" * 40)
cases.append((2, run(PUSH), "a receipt for a DIFFERENT tree is not a receipt"))

# A `--quick --only <one-gate>` run produces a receipt otherwise identical to
# one from all 254 gates. Without this the guard would honour a push proven by
# a single gate -- a hole the runner closes by recording `whole`.
put(whole=False)
cases.append((2, run(PUSH), "a NARROWED run (--only/--skip) cannot authorise a push"))

put(exitCode=1, failed=["check:format", "check:ci-parity"])
cases.append((2, run(PUSH), "a RED receipt refuses, and names the failures"))

# --- the allow direction, which decides whether the guard is tolerable -------
# A guard whose usual outcome is a false positive is one that gets bypassed.
put()
cases.append((0, run("git status"), "CONTROL: a non-push is out of scope"))
cases.append((0, run("git push --dry-run origin 0827-1"), "CONTROL: a dry run buys no CI round"))
cases.append((0, run("echo 'remember to git push once green'"), "CONTROL: prose is not a push"))
cases.append(
    (
        0,
        run("cd private/account && git push origin x"),
        "CONTROL: a submodule push advances no console branch",
    )
)

drop()
cases.append((0, run("git status"), "CONTROL: no receipt is still fine for a non-push"))

shutil.rmtree(d, ignore_errors=True)

bad = 0
for want, got, label in cases:
    if want != got:
        bad += 1
        print(f"  FAIL [{want}] {label} (got {got})")
print(
    f"FAILURES: {bad}  ({len(cases)} case(s), {sum(1 for w, _, _ in cases if w == 2)} block / "
    f"{sum(1 for w, _, _ in cases if w == 0)} allow)"
)
sys.exit(1 if bad else 0)
