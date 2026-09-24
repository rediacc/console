#!/usr/bin/env python3
"""block-unverified-push.sh: both directions, against a real git repo.

HERMETIC BY CONSTRUCTION. Every case runs against a scratch repo with its own CLAUDE_PROJECT_DIR, so this never reads or writes the real .ci/cache/prepush-receipt.json. An earlier draft backed the real one up and restored it, which works right up until the process is killed between the two and leaves the session unable to push for a reason nothing explains.

The refusal arms need a receipt planted at a specific tree sha, which is why they live here rather than in test-hooks.sh: that suite's `check` helper drives a guard against the live tree with no env or cwd control.
"""

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

# THIS HARNESS SITS BESIDE ITS GUARD, which is what .ci/scripts/quality/check-hook-integrity.sh means by a dedicated test file: `test-<stem>.py` next to `<stem>.py` credits the guard with BOTH directions, and it is the only credit these four have because their block direction needs fixture work `test-hooks.sh`'s one-line `check` helper cannot express.
#
# THE GUARD IS A PYTHON MODULE NOW. W5 P7 ported it and moved the bash original to .claude/oracles/, where the differential still compares the two byte for byte. This harness drives the LIVE guard, which is the dispatcher, for the reason the cutover exists at all: a suite that kept driving the retired file would keep passing while the thing that actually runs went unchecked.
DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_unverified_push"]

# `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those): a pid-stamped run directory, removed at exit and swept by the next run when this one was killed before `atexit` could fire, which is how /tmp hit its inode cap on 2026-09-24.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("unverified-push-test-")
# Inside RUN_TMP: the rmtree at the bottom runs only when the suite reaches it.
d = tempfile.mkdtemp(dir=RUN_TMP)


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
# The tree the planted receipt names. A dict rather than a rebound global: carrying is a commit, so it moves.
CURRENT = {"tree": TREE}

RECEIPT = os.path.join(d, ".ci", "cache", "prepush-receipt.json")


def put(**over):
    base = {
        "headTree": CURRENT["tree"],
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


CARRIED = os.path.join(d, ".ci", "config", "carried-reds.json")

# A reason long enough to clear the substance bar the guard applies (>= 80
# chars), so these cases test the CARRYING logic rather than accidentally testing the length check. The low-effort case below uses a short one on purpose.
GOOD_REASON = (
    "BLOCKER: the repair is a rebase reword and block-git-amend.sh has no override, "
    "so it belongs to the operator rather than this session."
)


def _rekey():
    """Point the planted receipt at the CURRENT HEAD^{tree}. The guard reads carried-reds.json from HEAD, so carrying is a commit, and a commit moves the tree the receipt must name."""
    CURRENT["tree"] = git("rev-parse", "HEAD^{tree}").stdout.strip()
    if os.path.exists(RECEIPT):
        with open(RECEIPT, encoding="utf-8") as fh:
            body = json.load(fh)
        body["headTree"] = CURRENT["tree"]
        with open(RECEIPT, "w", encoding="utf-8") as fh:
            json.dump(body, fh)


def write_carried(*entries):
    """The WORKTREE copy only, uncommitted: what another writer's in-flight edit looks like."""
    os.makedirs(os.path.dirname(CARRIED), exist_ok=True)
    with open(CARRIED, "w", encoding="utf-8") as fh:
        json.dump({"carried": list(entries)}, fh)


def carry(*entries):
    write_carried(*entries)
    git("add", "--", CARRIED)
    git("commit", "-q", "--allow-empty", "-m", "carry")
    _rekey()


def uncarry():
    if git("ls-files", "--", CARRIED).stdout.strip():
        git("rm", "-q", "-f", "--", CARRIED)
        git("commit", "-qm", "uncarry")
        _rekey()
    elif os.path.exists(CARRIED):
        os.remove(CARRIED)


def drop():
    if os.path.exists(RECEIPT):
        os.remove(RECEIPT)


def run(cmd):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
    return subprocess.run(
        GUARD_ARGV,
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

# A `--quick --only <one-gate>` run produces a receipt otherwise identical to one from all 254 gates. Without this the guard would honour a push proven by a single gate -- a hole the runner closes by recording `whole`.
put(whole=False)
cases.append((2, run(PUSH), "a NARROWED run (--only/--skip) cannot authorise a push"))

put(exitCode=1, failed=["check:format", "check:ci-parity"])
cases.append((2, run(PUSH), "a RED receipt refuses, and names the failures"))

# --- the allow direction, which decides whether the guard is tolerable ------- A guard whose usual outcome is a false positive is one that gets bypassed.
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
# DELETE-ONLY PUSHES, driven with NO receipt so the exemption is the only thing that can let them through; under the green receipt above every push is allowed and these would prove nothing.
cases.append(
    (0, run("git push origin --delete 0914-1"), "CONTROL: a --delete push publishes no tree")
)
cases.append((0, run("git push origin -d 0914-1 tooling-w0"), "CONTROL: the -d spelling, two refs"))
cases.append((0, run("git push origin :0914-1"), "CONTROL: a colon refspec is a delete too"))
cases.append(
    (
        2,
        run("git push origin --delete 0914-1 && git push origin 0827-1"),
        "a delete chained with a real push is still a push",
    )
)
cases.append(
    (2, run("git push origin :old 0827-1"), "one publishing refspec beside a delete publishes")
)
cases.append(
    (
        2,
        run("git push --tags origin --delete old"),
        "--tags publishes whatever else the segment says",
    )
)

# --- carried reds: a RED receipt may authorise a push only when NAMED --------- All-or-nothing is the shape that gets a guard bypassed, so a red may be carried -- but only with every failure named, no stale entry, and a substantive reason.
uncarry()
put(exitCode=1, failed=["check:ci-pr-task-trailers"])
cases.append((2, run(PUSH), "a red with NO carried-reds file still refuses"))

carry({"gate": "check:ci-pr-task-trailers", "reason": GOOD_REASON})
cases.append((0, run(PUSH), "a red whose every failure is NAMED and justified is allowed"))

put(exitCode=1, failed=["check:ci-pr-task-trailers", "check:lint"])
cases.append((2, run(PUSH), "a SECOND, unnamed red still refuses -- carrying is per-gate"))

# The rot guard: an excuse must not outlive the failure it excuses. The npm side of this repo once carried 101 dead allowlist entries for exactly this reason.
put(exitCode=1, failed=["check:lint"])
carry({"gate": "check:ci-pr-task-trailers", "reason": GOOD_REASON})
cases.append((2, run(PUSH), "a STALE carried entry (its gate now green) refuses"))

# A bare excuse is not a justification -- the bar .dead-bash-allowlist applies.
put(exitCode=1, failed=["check:ci-pr-task-trailers"])
carry({"gate": "check:ci-pr-task-trailers", "reason": "known issue"})
cases.append((2, run(PUSH), "a LOW-EFFORT reason does not carry anything"))

# ORDERING: `whole` is checked BEFORE carrying, so carrying cannot become a second way to launder a --only run. That hole is what the whole flag closed.
put(exitCode=1, failed=["check:ci-pr-task-trailers"], whole=False)
carry({"gate": "check:ci-pr-task-trailers", "reason": GOOD_REASON})
cases.append((2, run(PUSH), "a NARROWED run is refused even when its red is carried"))

# THE TREE BEING PUSHED DECIDES, not the worktree. The receipt is keyed on HEAD^{tree}, so its excuses must come from the same tree.
put(exitCode=1, failed=["check:ci-pr-task-trailers"])
carry({"gate": "check:ci-pr-task-trailers", "reason": GOOD_REASON})
write_carried()  # another writer's uncommitted copy DROPS the entry
cases.append(
    (0, run(PUSH), "an uncommitted worktree edit that DROPS an entry does not change the verdict")
)

uncarry()
put(exitCode=1, failed=["check:ci-pr-task-trailers"])
write_carried({"gate": "check:ci-pr-task-trailers", "reason": GOOD_REASON})  # worktree only
cases.append(
    (2, run(PUSH), "an entry present ONLY in the worktree, absent at HEAD, carries nothing")
)
if os.path.exists(CARRIED):
    os.remove(CARRIED)

uncarry()

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
