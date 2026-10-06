#!/usr/bin/env python3
"""block-unverified-push.sh: both directions, against a real git repo.

HERMETIC BY CONSTRUCTION. Every case runs against a scratch repo with its own CLAUDE_PROJECT_DIR, so this never reads or writes the real .ci/cache/prepush-receipt.json. An earlier draft backed the real one up and restored it, which works right up until the process is killed between the two and leaves the session unable to push for a reason nothing explains.

The refusal arms need a receipt planted at a specific tree sha, which is why they live here rather than in test-hooks.sh: that suite's `check` helper drives a guard against the live tree with no env or cwd control.
"""

import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

# THIS HARNESS SITS BESIDE ITS GUARD, which is what .ci/scripts/quality/check-hook-integrity.sh means by a dedicated test file: `test-<stem>.py` next to `<stem>.py` credits the guard with BOTH directions, and it is the only credit these four have because their block direction needs fixture work `test-hooks.sh`'s one-line `check` helper cannot express.
#
# THE GUARD IS A PYTHON MODULE NOW. W5 P7 ported it from a bash original that PLAN-retire-bash-oracles A3 later deleted, once the differential compared the two byte for byte and froze the result as a golden (tests/goldens/<stem>.jsonl). This harness drives the LIVE guard, which is the dispatcher, for the reason the cutover exists at all: a suite that kept driving the retired file would keep passing while the thing that actually runs went unchecked.
DISPATCH = str(pathlib.Path(__file__).resolve().parents[1] / "dispatch.py")
GUARD_ARGV = [sys.executable, DISPATCH, "block_unverified_push"]

# THE GUARD MODULE ITSELF, for the v2 fixtures and the helper unit tests. `rediacc_hooks.syspath` is loaded BY FILE for the reason its docstring gives (a script outside the package cannot import it by name before `.claude` is on the path).
_SYSPATH = importlib.util.spec_from_file_location(
    "syspath", pathlib.Path(__file__).resolve().parents[1] / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(syspath)
syspath.on_sys_path(syspath.CLAUDE_DIR)
GM = importlib.import_module("rediacc_hooks.guards.block_unverified_push")

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
GM._write_fixture_lock(pathlib.Path(d))
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
        "droppedTouched": [],
        "droppedVerified": {},
    }
    base.update(over)
    base = GM._v2_body(base)
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

# The stricter bar a `"*"` (whole-gate) carry must clear: at least 160 characters.
STAR_REASON = GOOD_REASON + (
    " It emits no finding keys yet, so the whole gate is carried until it does."
)
if not (80 <= len(GOOD_REASON) < 160 <= len(STAR_REASON)):
    raise SystemExit("fixture reasons no longer straddle the 80/160 bars the cases below test")
TRAILERS = "check:ci-pr-task-trailers"
K1 = "P-A2:no-row:agent/plans/PLAN-a.md#0a1b2c3d"
K2 = "P-A2:no-row:agent/plans/_done/PLAN-b.md#4e5f6a7b"


def keyed(*keys, gate=TRAILERS, reason=GOOD_REASON):
    """One v2 entry carrying `keys` (or `"*"`) for `gate`."""
    return {"gate": gate, "findings": keys[0] if keys == ("*",) else list(keys), "reason": reason}


def _rekey():
    """Point the planted receipt at the CURRENT HEAD^{tree}. The guard reads carried-reds.json from HEAD, so carrying is a commit, and a commit moves the tree the receipt must name."""
    CURRENT["tree"] = git("rev-parse", "HEAD^{tree}").stdout.strip()
    if os.path.exists(RECEIPT):
        with open(RECEIPT, encoding="utf-8") as fh:
            body = json.load(fh)
        body["headTree"] = CURRENT["tree"]
        with open(RECEIPT, "w", encoding="utf-8") as fh:
            json.dump(body, fh)


def write_carried(*entries, version=2):
    """The WORKTREE copy only, uncommitted: what another writer's in-flight edit looks like. v2 unless a case plants another version."""
    os.makedirs(os.path.dirname(CARRIED), exist_ok=True)
    doc = {"carried": list(entries)}
    if version is not None:
        doc["version"] = version
    with open(CARRIED, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def carry(*entries, version=2):
    write_carried(*entries, version=version)
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
cases: list[tuple[Any, Any, str]] = []


def run_err(cmd):
    """The guard's stderr, for the cases that assert what a refusal NAMES."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
    return subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=d,
        env=env,
        check=False,
    ).stderr


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

# --- a touched slow gate the lane DROPPED (PLAN-gate-drop-receipt-verify) ------ On 2026-10-03 ci:quick dropped check:ci-plan-record, a gate the diff touched; the receipt said nothing and CI run 37129843955 went red on it.
PLAN_RECORD = "check:ci-plan-record"
DROP = {
    "id": PLAN_RECORD,
    "why": "agent/INDEX.md matches its paths",
    "reason": "it writes the shared tree (tree:repo), which the quick lane does not do",
    "kind": "tree",
    "run": "npx tsx scripts/ci-runner/run.ts --only %s" % PLAN_RECORD,
}


def passed_at(tree, code=0):
    return {
        PLAN_RECORD: {
            "exitCode": code,
            "headTree": tree,
            "finishedAt": "now",
            "judgedRoot": d,
            "stable": True,
        }
    }


put(droppedTouched=[DROP])
cases.append((2, run(PUSH), "DROPPED: an outstanding touched-but-dropped gate refuses"))
_err = run_err(PUSH)
cases.append(
    (
        True,
        PLAN_RECORD in _err and DROP["run"] in _err,
        "DROPPED: the refusal names the gate and its --only command",
    )
)
put(droppedTouched=[DROP], droppedVerified=passed_at(CURRENT["tree"]))
cases.append((0, run(PUSH), "DROPPED CONTROL: a passing --only run at this tree clears it"))
put(droppedTouched=[DROP], droppedVerified=passed_at("0" * 40))
cases.append((2, run(PUSH), "DROPPED: a passing run at ANOTHER tree does not clear it"))
put(droppedTouched=[DROP], droppedVerified=passed_at(CURRENT["tree"], code=1))
cases.append((2, run(PUSH), "DROPPED: a red --only run does not clear it"))
put(
    droppedTouched=[DROP],
    droppedVerified=passed_at(CURRENT["tree"], code=1),
    exitCode=1,
    failed=[PLAN_RECORD],
)
cases.append((2, run(PUSH), "DROPPED: a red re-run listed in failed and NOT carried refuses"))
carry(keyed("*", gate=PLAN_RECORD, reason=STAR_REASON))
put(
    droppedTouched=[DROP],
    droppedVerified=passed_at(CURRENT["tree"], code=1),
    exitCode=1,
    failed=[PLAN_RECORD],
    findings={PLAN_RECORD: None},
)
cases.append(
    (0, run(PUSH), "DROPPED: a red re-run listed in failed and carried is judged by the carry")
)
uncarry()
put(droppedTouched=[DROP], droppedVerified=passed_at(CURRENT["tree"], code=False))
cases.append((2, run(PUSH), "DROPPED: an exitCode of false is not a pass"))
put()
with open(RECEIPT, encoding="utf-8") as _fh:
    _body = json.load(_fh)
del _body["droppedTouched"]
with open(RECEIPT, "w", encoding="utf-8") as _fh:
    json.dump(_body, _fh)
cases.append((2, run(PUSH), "DROPPED: a receipt with NO droppedTouched field fails closed"))
put(droppedTouched=[])
cases.append((0, run(PUSH), "DROPPED CONTROL: an empty droppedTouched allows"))

# --- the allow direction, which decides whether the guard is tolerable ------- A guard whose usual outcome is a false positive is one that gets bypassed.
put()
cases.append((0, run("git status"), "CONTROL: a non-push is out of scope"))
cases.append((0, run("git push --dry-run origin 0827-1"), "CONTROL: a dry run buys no CI round"))
drop()
cases.append(
    (
        2,
        run("git push --dry-run origin x; git push origin 0827-1"),
        "#641e2fce: with no receipt, a dry run beside a real push does not exempt it",
    )
)
cases.append(
    (0, run("git -C . push --dry-run origin 0827-1"), "CONTROL: a dry run behind -C is still one")
)
put()
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


def run_from(cmd, payload_cwd):
    """`run`, with the tool's working directory in the payload the way the harness sends it."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=d)
    return subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": {"command": cmd}, "cwd": payload_cwd}),
        capture_output=True,
        text=True,
        cwd=d,
        env=env,
        check=False,
    ).returncode


# A PLAIN PUSH WHOSE TOOL CWD IS A NESTED REPOSITORY (#e83d9ba9), driven with NO receipt so the cwd is the only thing that can let it through; the inverse keeps the same command, from this tree's own root, refused.
_sub = os.path.join(d, "private", "sub")
os.makedirs(_sub, exist_ok=True)
subprocess.run(["git", "init", "-q", _sub], check=True)
cases.append(
    (0, run_from(PUSH, _sub), "CONTROL: a plain push from a submodule cwd is that repo's push")
)
cases.append((2, run_from(PUSH, d), "the same push from this tree's own cwd is still judged"))
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
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]})
cases.append((2, run(PUSH), "a red with NO carried-reds file still refuses"))

carry(keyed(K1))
cases.append((0, run(PUSH), "a red whose every failure is NAMED and justified is allowed"))

put(exitCode=1, failed=[TRAILERS, "check:lint"], findings={TRAILERS: [K1], "check:lint": None})
cases.append((2, run(PUSH), "a SECOND, unnamed red still refuses -- carrying is per-gate"))

# The rot guard: an excuse must not outlive the failure it excuses. The npm side of this repo once carried 101 dead allowlist entries for exactly this reason.
# Two failed gates, one carried and one green-but-carried: the gate-level stale arm, isolated from the unnamed arm.
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]})
carry(keyed(K1), keyed(K1, gate="check:lint"))
cases.append((2, run(PUSH), "a STALE carried entry (its gate now green) refuses"))

# The same rot on a WHOLLY GREEN receipt: nothing failing means every carried entry is stale. Measured 2026-10-02, this arm ran only on a red receipt, so the check:ci-external-links carry rode the green push of afe0503db unremarked.
put(exitCode=0)
carry(keyed(K1))
cases.append(
    (2, run(PUSH), "a GREEN receipt with a carried entry refuses: the excuse outlived its failure")
)
uncarry()
_rekey()
put(exitCode=0)
cases.append((0, run(PUSH), "CONTROL: a GREEN receipt with nothing carried is honoured"))

# A bare excuse is not a justification -- the bar .dead-bash-allowlist applies.
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]})
carry(keyed(K1, reason="known issue"))
cases.append((2, run(PUSH), "a LOW-EFFORT reason does not carry anything"))

# ORDERING: `whole` is checked BEFORE carrying, so carrying cannot become a second way to launder a --only run. That hole is what the whole flag closed.
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]}, whole=False)
carry(keyed(K1))
cases.append((2, run(PUSH), "a NARROWED run is refused even when its red is carried"))

# THE TREE BEING PUSHED DECIDES, not the worktree. The receipt is keyed on HEAD^{tree}, so its excuses must come from the same tree.
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]})
carry(keyed(K1))
write_carried()  # another writer's uncommitted copy DROPS the entry
cases.append(
    (0, run(PUSH), "an uncommitted worktree edit that DROPS an entry does not change the verdict")
)

uncarry()
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]})
write_carried(keyed(K1))  # worktree only
cases.append(
    (2, run(PUSH), "an entry present ONLY in the worktree, absent at HEAD, carries nothing")
)
if os.path.exists(CARRIED):
    os.remove(CARRIED)

# --- finding keys (PLAN-carried-red-finding-keys): a carried gate carries the findings it names ------------------------------------------------ Each planted defect sits beside its clean control.
FULL = {TRAILERS: [K1, K2]}

# 1. NEW FINDING: the gate emitted K2 as well, and only K1 is carried.
put(exitCode=1, failed=[TRAILERS], findings=FULL)
carry(keyed(K1))
cases.append((2, run(PUSH), "1: a NEW finding under a carried gate refuses"))
cases.append((True, K2 in run_err(PUSH), "1: the refusal names the new key"))
carry(keyed(K1, K2))
cases.append((0, run(PUSH), "1/2 CONTROL: every emitted key carried, none stale"))

# 2. STALE FINDING: K2 is carried and the gate no longer emits it.
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]})
cases.append((2, run(PUSH), "2: a carried key the gate no longer emits refuses"))
cases.append((True, K2 in run_err(PUSH), "2: the refusal names the stale key"))

# 3. KEYED CARRY OF A GATE THAT EMITS NOTHING: the receipt has null, so the keys cannot be checked.
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: None})
carry(keyed(K1))
cases.append((2, run(PUSH), "3: a keyed carry of a gate with no parsable findings refuses"))
carry(keyed("*", reason=STAR_REASON))
cases.append((0, run(PUSH), "3/4 CONTROL: '*' with a 160-char reason over a null gate is allowed"))

# 4. "*" OVER A GATE THAT DOES EMIT: it must be carried by key.
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]})
cases.append((2, run(PUSH), "4: '*' over a gate that emits keys refuses"))

# 5. "*" BELOW THE STRICTER BAR: an 80-character reason carries a key, not a whole gate.
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: None})
carry(keyed("*", reason=GOOD_REASON))
cases.append((2, run(PUSH), "5: '*' with a reason under 160 characters carries nothing"))
carry(keyed("*", reason=STAR_REASON))
cases.append((0, run(PUSH), "5 CONTROL: the same '*' with 160+ characters is allowed"))

# 6. OLD RECEIPT: no `findings` field at all reads as null for every gate, so a keyed carry fails closed.
put(exitCode=1, failed=[TRAILERS])
carry(keyed(K1))
cases.append((2, run(PUSH), "6: a receipt with no findings field cannot verify a keyed carry"))
put(exitCode=1, failed=[TRAILERS], findings={TRAILERS: [K1]})
cases.append((0, run(PUSH), "6 CONTROL: the field present with the carried keys is allowed"))

# 7. SCHEMA: a v1 entry, an empty findings list, a missing version, and "*" beside keys all refuse rather than being skipped.
carry({"gate": TRAILERS, "reason": GOOD_REASON})
cases.append((2, run(PUSH), "7: a v1 entry (no findings) is a schema error"))
carry(keyed(K1))
cases.append((0, run(PUSH), "7 CONTROL: the same entry in v2 is allowed"))
carry({"gate": TRAILERS, "findings": [], "reason": GOOD_REASON})
cases.append((2, run(PUSH), "7: an empty findings list is a schema error"))
carry(keyed(K1), version=None)
cases.append((2, run(PUSH), "7: a file with no version 2 is a schema error"))
carry(keyed(K1), keyed("*", reason=STAR_REASON))
cases.append((2, run(PUSH), "7: '*' beside keyed entries for one gate is a schema error"))
# Several keyed entries for one gate union their keys.
put(exitCode=1, failed=[TRAILERS], findings=FULL)
carry(keyed(K1), keyed(K2))
cases.append((0, run(PUSH), "7 CONTROL: two keyed entries for one gate union their keys"))

uncarry()

# --- the PUSHED tree, not HEAD's ---------------------------------------------------------- `git push origin <src>:<dst>` sends <src>, so the receipt must have judged <src>'s tree. Measured on #591 (2026-10-03): an unpushed local commit on top of the green PR head refused the fast-forward fallback as "a different tree".
_rekey()
pushed_sha = git("rev-parse", "HEAD").stdout.strip()
put(exitCode=0)  # the receipt judges the commit about to be pushed
with open(os.path.join(d, "local-only.txt"), "w", encoding="utf-8") as fh:
    fh.write("a change the push does not carry\n")
git("add", "--", "local-only.txt")
git(
    "commit", "-q", "-m", "a local commit on top, never pushed"
)  # a different tree, unlike --allow-empty
cases.append(
    (
        0,
        run("git push origin %s:refs/heads/x" % pushed_sha),
        "an explicit <src>:<dst> push is judged by <src>'s tree, not HEAD's",
    )
)
cases.append(
    (
        2,
        run(PUSH),
        "CONTROL: a push of the branch (HEAD's tree) is still refused against that receipt",
    )
)
cases.append(
    (2, run("git push origin HEAD:refs/heads/x"), "CONTROL: HEAD:<dst> is judged by HEAD's tree")
)
_rekey()

# --- a push of exactly origin/main needs no receipt ------------------------------------------ The GitLab mirror push (pr-merge step 6b, operator ruling 2026-10-03) sends the commit GitHub's required CI already judged.
mirror_sha = git("rev-parse", "HEAD").stdout.strip()
git("update-ref", "refs/remotes/origin/main", mirror_sha)
drop()
cases.append(
    (
        0,
        run("git push gitlab %s:refs/heads/main" % mirror_sha),
        "a push of exactly origin/main's commit needs no receipt",
    )
)
other = git("rev-parse", "HEAD~1").stdout.strip()
cases.append(
    (
        2,
        run("git push gitlab %s:refs/heads/main" % other),
        "CONTROL: a push of any other commit still needs one",
    )
)
cases.append((2, run(PUSH), "CONTROL: a branch push with no receipt is still refused"))
git("update-ref", "-d", "refs/remotes/origin/main")
_rekey()

# --- a live branch behind origin/main is refused before the push ---------------------------------- PR #592's first CI run (run 37110619739) went red only on Quality / Branch: main had moved three commits after 1003-1 was cut, and the push clone's origin/main was stale, so nothing local saw it. The guard fetches origin/main itself and refuses an MMDD-N push that does not contain it.
# Fixtures are a bare "origin" and a second clone that advances it, all on local paths: no case here touches the network.
REPO = pathlib.Path(__file__).resolve().parents[3]
LIVE = "1003-1"


def g(where, *a):
    return subprocess.run(
        ["git", "-C", str(where), *a], capture_output=True, text=True, check=True
    ).stdout.strip()


def ci_recipe(head):
    """`rediacc_ci.quality.branch.recipe("main", head)`, the text CI prints, read in a child with `.ci` on PYTHONPATH (no sys.path hop in this file)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, sys; from rediacc_ci.quality.branch import recipe;"
                " print(json.dumps(recipe('main', sys.argv[1])))"
            ),
            head,
        ],
        capture_output=True,
        text=True,
        check=True,
        env=dict(os.environ, PYTHONPATH=str(REPO / ".ci")),
    )
    return "\n".join(json.loads(proc.stdout))


bw = pathlib.Path(tempfile.mkdtemp(dir=RUN_TMP))
origin = bw / "origin.git"
work = bw / "work"
mover = bw / "mover"
subprocess.run(
    ["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True
)
subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True, capture_output=True)
g(work, "config", "user.email", "p@example.invalid")
g(work, "config", "user.name", "p")
g(work, "remote", "add", "origin", str(origin))
(work / "base.txt").write_text("base\n", encoding="utf-8")
GM._write_fixture_lock(work)
g(work, "add", "-A")
g(work, "commit", "-qm", "base")
g(work, "push", "-q", "origin", "main")
g(work, "fetch", "-q", "origin")
g(work, "checkout", "-qb", LIVE)
(work / "live.txt").write_text("live\n", encoding="utf-8")
g(work, "add", "--", "live.txt")
g(work, "commit", "-qm", "live work")
# main moves on origin AFTER the branch was cut, through another clone, so work's own origin/main is STALE: only a fetch can see the three commits.
subprocess.run(["git", "clone", "-q", str(origin), str(mover)], check=True, capture_output=True)
g(mover, "config", "user.email", "p@example.invalid")
g(mover, "config", "user.name", "p")
for i in range(3):
    (mover / ("main-%d.txt" % i)).write_text("m\n", encoding="utf-8")
    g(mover, "add", "-A")
    g(mover, "commit", "-qm", "main moves %d" % i)
g(mover, "push", "-q", "origin", "main")


def plant_green(where):
    """A whole, green receipt for `where`'s HEAD^{tree}, so the receipt arm allows and the base check is the only thing left to judge."""
    cache = pathlib.Path(where) / ".ci" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "prepush-receipt.json").write_text(
        json.dumps(
            GM._v2_body(
                {
                    "headTree": g(where, "rev-parse", "HEAD^{tree}"),
                    "whole": True,
                    "exitCode": 0,
                    "failed": [],
                    "droppedTouched": [],
                }
            )
        ),
        encoding="utf-8",
    )


def drive(where, cmd):
    proc = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=str(where),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(where)),
        check=False,
    )
    return proc.returncode, proc.stderr


plant_green(work)
stale = g(work, "rev-parse", "refs/remotes/origin/main")
rc, err = drive(work, "git push origin %s" % LIVE)
cases.append((2, rc, "BEHIND: a live branch three commits behind origin/main is refused"))
cases.append(
    (True, ci_recipe(LIVE) in err, "BEHIND: the refusal prints CI's REBASE LOCALLY recipe verbatim")
)
cases.append(
    (
        True,
        g(work, "rev-parse", "refs/remotes/origin/main") != stale,
        "BEHIND: the guard fetched origin/main itself rather than trusting the stale ref",
    )
)
rc, _err = drive(work, "git push --force-with-lease origin %s" % LIVE)
cases.append((2, rc, "BEHIND: a --force-with-lease republish of the live branch is judged too"))
rc, _err = drive(work, "git push -u origin HEAD")
cases.append((2, rc, "BEHIND: HEAD pushed from the live branch is judged as the live branch"))

# CONTROL: the same branch rebased onto origin/main is allowed.
g(work, "rebase", "-q", "origin/main")
plant_green(work)
rc, err = drive(work, "git push --force-with-lease origin %s" % LIVE)
cases.append((0, rc, "CONTROL: the live branch on top of origin/main is allowed"))
cases.append((False, "REBASE LOCALLY" in err, "CONTROL: and prints no recipe"))

# CONTROL: a branch that is not MMDD-N is not judged, however far behind.
g(work, "checkout", "-qb", "feature", g(work, "rev-list", "--max-parents=0", "HEAD"))
(work / "feature.txt").write_text("f\n", encoding="utf-8")
g(work, "add", "--", "feature.txt")
g(work, "commit", "-qm", "feature")
plant_green(work)
rc, err = drive(work, "git push origin feature")
cases.append((0, rc, "CONTROL: a non-MMDD-N branch push is not judged against origin/main"))

# CANNOT JUDGE: the live branch is behind again, but origin is unreachable, so the fetch fails. Warn, say so, and allow (fail open on a broken environment).
g(work, "checkout", "-q", LIVE)
g(work, "reset", "-q", "--hard", g(work, "rev-list", "--max-parents=0", "HEAD"))
(work / "live.txt").write_text("live again\n", encoding="utf-8")
g(work, "add", "--", "live.txt")
g(work, "commit", "-qm", "live work, cut before main moved")
plant_green(work)
g(work, "update-ref", "refs/remotes/origin/main", g(work, "rev-parse", "HEAD~1"))
g(work, "remote", "set-url", "origin", str(bw / "gone.git"))
rc, err = drive(work, "git push origin %s" % LIVE)
cases.append((0, rc, "CANNOT JUDGE: a failed fetch of origin/main allows"))
cases.append((True, "cannot judge" in err, "CANNOT JUDGE: and the warning says so explicitly"))

shutil.rmtree(bw, ignore_errors=True)

# --- a record-only commit ADVANCES the receipt (PLAN-prepush-full-cpu part 5, PF25/PF26) ------------- `worklist.py --review-commit` commits agent/reviews/<branch>/ after every reviewed commit; nine receipts died that way on 2026-10-05 with no code changed. A receipt for tree T now admits a HEAD whose diff from T is confined to .ci/policy/record-paths.json, PROVIDED the readers of
# the touched records were re-run at each step (`advances`). The guard recomputes every step's diff itself and never trusts the step's `paths`.
GUARD = pathlib.Path(__file__).resolve().parent / "block_unverified_push.py"
R_PLAN = "check:fixture-plan-implementation"
R_ARCH = "check:fixture-session-archival"
R_TREE = "check:fixture-tree-shape"
ADV_POLICY = {
    "version": 1,
    "records": [
        {
            "glob": "agent/reviews/**",
            "except": [],
            "readers": [
                {"id": R_PLAN, "evidence": "fixture:1"},
                {"id": R_ARCH, "evidence": "fixture:2"},
            ],
        },
        {
            "glob": "agent/worklist/*.jsonl",
            "except": ["agent/worklist/epics.jsonl"],
            "readers": [{"id": R_TREE, "evidence": "fixture:3"}],
        },
    ],
}
REVIEW = "agent/reviews/0827-1/clean.jsonl"
WORKLIST = "agent/worklist/abcd1234.jsonl"
BOTH_REVIEW_READERS = {R_PLAN: 0, R_ARCH: 0}


def adv_world(name, carried_doc=None):
    """A repo whose base commit carries the record policy (and optionally carried-reds.json); returns (root, base tree)."""
    root = pathlib.Path(tempfile.mkdtemp(dir=RUN_TMP)) / name
    root.mkdir()
    g(root, "init", "-q", "-b", "0827-1")
    g(root, "config", "user.email", "p@example.invalid")
    g(root, "config", "user.name", "p")
    (root / ".ci" / "policy").mkdir(parents=True)
    (root / ".ci" / "policy" / "record-paths.json").write_text(
        json.dumps(ADV_POLICY), encoding="utf-8"
    )
    (root / "code.txt").write_text("code\n", encoding="utf-8")
    GM._write_fixture_lock(root)
    if carried_doc is not None:
        (root / ".ci" / "config").mkdir(parents=True)
        (root / ".ci" / "config" / "carried-reds.json").write_text(
            json.dumps(carried_doc), encoding="utf-8"
        )
    g(root, "add", "-A")
    g(root, "commit", "-qm", "base")
    return root, g(root, "rev-parse", "HEAD^{tree}")


def adv_commit(root, *rels):
    """Commit a change to each repo-relative path and return the new HEAD^{tree}."""
    for rel in rels:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as fh:
            fh.write("one more line\n")
    g(root, "add", "-A")
    g(root, "commit", "-qm", "change %s" % ", ".join(rels))
    return g(root, "rev-parse", "HEAD^{tree}")


def adv_receipt(root, head_tree, advances, **over):
    body = {
        "headTree": head_tree,
        "whole": True,
        "exitCode": 0,
        "failed": [],
        "findings": {},
        "droppedTouched": [],
        "droppedVerified": {},
    }
    if advances is not None:
        body["advances"] = advances
    body.update(over)
    body = GM._v2_body(body)
    cache = root / ".ci" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "prepush-receipt.json").write_text(json.dumps(body), encoding="utf-8")


def step(frm, to, gates, paths=(REVIEW,), findings=None):
    """One `advances` entry as the runner writes it (PF24); `findings` is the per-reader keys `runAdvance` records beside the exit codes (F11)."""
    body = {
        "from": frm,
        "to": to,
        "paths": list(paths),
        "gates": dict(gates),
        "finishedAt": "2026-10-05T00:00:00Z",
    }
    if findings is not None:
        body["findings"] = findings
    return body


def drive_broken(where, cmd):
    """The guard with its own declared DEFECT planted, in a child, exactly as test-block_second_branch.py drives its copy."""
    namespace: dict[str, object] = {}
    body = []
    for line in GUARD.read_text(encoding="utf-8").split("\n"):
        if line.startswith("DEFECT = "):
            exec(line, namespace)  # noqa: S102 -- the guard's own one-line literal
        else:
            body.append(line)
    # THE DECLARATION ITSELF CONTAINS THE TEXT IT PLANTS, so `old in src` alone stays true after the guarded line is deleted, and the plant then changes nothing but its own declaration. Measured 2026-10-05 with the line replaced by hand: the copy runner's assertion passed.
    old_text = namespace["DEFECT"][0]  # type: ignore[index]
    if old_text not in "\n".join(body):
        # A FAILING RESULT, not an abort: the summary then still names every case the missing line broke.
        print("  the guard's DEFECT %r no longer names a line of code" % old_text)
        return -1, ""
    runner = (
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
    ) % (str(GUARD.parents[2]), str(GUARD), namespace["DEFECT"], str(GUARD))
    proc = subprocess.run(
        [sys.executable, "-c", runner],
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=str(where),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(where)),
        check=False,
    )
    if proc.returncode not in (0, 2):
        raise SystemExit("broken-copy runner crashed: %s" % proc.stderr[-800:])
    return proc.returncode, proc.stderr


ADV_PUSH = "git push origin 0827-1"
# Each world: (label, want, root). The confinement worlds are re-driven against the planted DEFECT below.
ADV_WORLDS = []

# 1. A record-only commit with both of its readers re-run green at HEAD is admitted.
w, t0 = adv_world("records-readers-green")
t1 = adv_commit(w, REVIEW)
adv_receipt(w, t0, [step(t0, t1, BOTH_REVIEW_READERS)])
ADV_WORLDS.append(("ADVANCE: a record-only commit with its readers re-run is admitted", 0, w))

# 2. The same commit with one reader NOT re-run is refused, and the refusal names the reader.
w, t0 = adv_world("records-reader-missing")
t1 = adv_commit(w, REVIEW)
adv_receipt(w, t0, [step(t0, t1, {R_PLAN: 0})])
ADV_WORLDS.append(("ADVANCE: a record-only commit with a reader NOT re-run is refused", 2, w))
cases.append(
    (True, R_ARCH in drive(w, ADV_PUSH)[1], "ADVANCE: the missing-reader refusal names the reader")
)

# 3. Records plus ONE code file, behind an advance whose `paths` claims records only and whose readers are green: the recomputed diff holds code.
w, t0 = adv_world("records-plus-code")
t1 = adv_commit(w, REVIEW, "code.txt")
adv_receipt(w, t0, [step(t0, t1, BOTH_REVIEW_READERS)])
ADV_WORLDS.append(("ADVANCE: records plus one code file is refused", 2, w))
cases.append(
    (
        True,
        "code.txt" in drive(w, ADV_PUSH)[1],
        "ADVANCE: the confinement refusal names the code path the step's `paths` hid",
    )
)

# 4. A code-only commit, behind the same forged advance.
w, t0 = adv_world("code-only")
t1 = adv_commit(w, "code.txt")
adv_receipt(w, t0, [step(t0, t1, BOTH_REVIEW_READERS)])
ADV_WORLDS.append(("ADVANCE: a code-only commit is refused", 2, w))

# 5. A record-only commit with NO advance at all keeps today's refusal, word for word (the frozen golden's text).
w, t0 = adv_world("records-no-advance")
t1 = adv_commit(w, REVIEW)
adv_receipt(w, t0, None)
ADV_WORLDS.append(("ADVANCE: a record-only commit with no advance is refused", 2, w))
cases.append(
    (
        True,
        "the gate run judged a different tree (%s), not this one (%s)." % (t0, t1)
        in drive(w, ADV_PUSH)[1],
        "ADVANCE: with no advance the refusal is today's text, unchanged",
    )
)

# 6. Two chained advances (reviews, then a worklist file) are admitted.
w, t0 = adv_world("two-chained")
t1 = adv_commit(w, REVIEW)
t2 = adv_commit(w, WORKLIST)
adv_receipt(
    w, t0, [step(t0, t1, BOTH_REVIEW_READERS), step(t1, t2, {R_TREE: 0}, paths=(WORKLIST,))]
)
ADV_WORLDS.append(("ADVANCE: two chained advances are admitted", 0, w))

# 7. A step whose `from` no verified step reached does not chain.
w, t0 = adv_world("broken-chain")
t1 = adv_commit(w, REVIEW)
t2 = adv_commit(w, WORKLIST)
adv_receipt(
    w, t0, [step(t0, t1, BOTH_REVIEW_READERS), step("1" * 40, t2, {R_TREE: 0}, paths=(WORKLIST,))]
)
ADV_WORLDS.append(("ADVANCE: a step starting off the chain does not reach HEAD", 2, w))

# 8. An excluded record path (agent/worklist/epics.jsonl) is outside the set.
w, t0 = adv_world("excluded-record")
t1 = adv_commit(w, "agent/worklist/epics.jsonl")
adv_receipt(w, t0, [step(t0, t1, {R_TREE: 0}, paths=("agent/worklist/epics.jsonl",))])
ADV_WORLDS.append(("ADVANCE: an excluded path under a record glob is refused", 2, w))

# 9. A reader RED at the step that the receipt's `failed` does not list is refused.
w, t0 = adv_world("reader-red-unlisted")
t1 = adv_commit(w, REVIEW)
adv_receipt(w, t0, [step(t0, t1, {R_PLAN: 1, R_ARCH: 0})])
ADV_WORLDS.append(("ADVANCE: a reader red at the step and not in `failed` is refused", 2, w))

# 10. A reader RED at the step, listed in `failed` and NOT carried, is refused by the carry rule.
w, t0 = adv_world("reader-red-uncarried")
t1 = adv_commit(w, REVIEW)
adv_receipt(
    w,
    t0,
    [step(t0, t1, {R_PLAN: 1, R_ARCH: 0})],
    exitCode=1,
    failed=[R_PLAN],
    findings={R_PLAN: None},
)
ADV_WORLDS.append(("ADVANCE: a reader red at the step and not carried is refused", 2, w))

# 11. The same red, carried by name in carried-reds.json at HEAD, is admitted: the carry rule judges it.
w, t0 = adv_world(
    "reader-red-carried",
    carried_doc={"version": 2, "carried": [keyed("*", gate=R_PLAN, reason=STAR_REASON)]},
)
t1 = adv_commit(w, REVIEW)
adv_receipt(
    w,
    t0,
    [step(t0, t1, {R_PLAN: 1, R_ARCH: 0})],
    exitCode=1,
    failed=[R_PLAN],
    findings={R_PLAN: None},
)
ADV_WORLDS.append(("ADVANCE: a reader red at the step and carried is admitted", 0, w))

# 11b. The same red under a KEYED carry is refused: the advance recorded no finding keys, so a keyed carry cannot vouch for the step.
w, t0 = adv_world(
    "reader-red-keyed-carry",
    carried_doc={"version": 2, "carried": [keyed(K1, gate=R_PLAN)]},
)
t1 = adv_commit(w, REVIEW)
adv_receipt(
    w,
    t0,
    [step(t0, t1, {R_PLAN: 1, R_ARCH: 0})],
    exitCode=1,
    failed=[R_PLAN],
    findings={R_PLAN: [K1]},
)
ADV_WORLDS.append(("ADVANCE: a reader red at the step under a keyed carry is refused", 2, w))

# 11d. F11: the same red under a KEYED carry IS admitted when the step recorded findings that equal the receipt's and the carry names every key.
w, t0 = adv_world(
    "reader-red-keyed-carry-recorded",
    carried_doc={"version": 2, "carried": [keyed(K1, gate=R_PLAN)]},
)
t1 = adv_commit(w, REVIEW)
adv_receipt(
    w,
    t0,
    [step(t0, t1, {R_PLAN: 1, R_ARCH: 0}, findings={R_PLAN: [K1]})],
    exitCode=1,
    failed=[R_PLAN],
    findings={R_PLAN: [K1]},
)
ADV_WORLDS.append(
    ("ADVANCE: a red reader whose recorded findings match a keyed carry is admitted", 0, w)
)

# 11e. The step recorded a key the receipt (and the carry) never had: a NEW finding, refused.
w, t0 = adv_world(
    "reader-red-keyed-carry-extra-key",
    carried_doc={"version": 2, "carried": [keyed(K1, gate=R_PLAN)]},
)
t1 = adv_commit(w, REVIEW)
adv_receipt(
    w,
    t0,
    [step(t0, t1, {R_PLAN: 1, R_ARCH: 0}, findings={R_PLAN: [K1, K2]})],
    exitCode=1,
    failed=[R_PLAN],
    findings={R_PLAN: [K1]},
)
ADV_WORLDS.append(("ADVANCE: a red reader with an uncarried new key is refused", 2, w))

# 11f. The step recorded `null` (nothing parsable) for the red reader: refused under a keyed carry.
w, t0 = adv_world(
    "reader-red-keyed-carry-null",
    carried_doc={"version": 2, "carried": [keyed(K1, gate=R_PLAN)]},
)
t1 = adv_commit(w, REVIEW)
adv_receipt(
    w,
    t0,
    [step(t0, t1, {R_PLAN: 1, R_ARCH: 0}, findings={R_PLAN: None})],
    exitCode=1,
    failed=[R_PLAN],
    findings={R_PLAN: [K1]},
)
ADV_WORLDS.append(("ADVANCE: a red reader that recorded no parsable findings is refused", 2, w))

# 11c. A reader that could not run (exit 77) is admitted only when the receipt already lists it as blocked.
w, t0 = adv_world("reader-could-not-run-blocked")
t1 = adv_commit(w, REVIEW)
adv_receipt(w, t0, [step(t0, t1, {R_PLAN: 77, R_ARCH: 0})], blocked=[R_PLAN])
ADV_WORLDS.append(("ADVANCE: a reader that could not run and is blocked is admitted", 0, w))
w, t0 = adv_world("reader-could-not-run-unblocked")
t1 = adv_commit(w, REVIEW)
adv_receipt(w, t0, [step(t0, t1, {R_PLAN: 77, R_ARCH: 0})])
ADV_WORLDS.append(("ADVANCE: a reader that could not run and is not blocked is refused", 2, w))

# 12. A step whose `from` is not a tree hash is refused before git ever sees it (an option-shaped value would be an argument to `git diff`).
w, t0 = adv_world("from-not-a-hash")
t1 = adv_commit(w, REVIEW)
adv_receipt(w, t0, [step(t0, t1, BOTH_REVIEW_READERS), step("--output=x", t1, {})])
ADV_WORLDS.append(("ADVANCE: an option-shaped `from` is never passed to git", 0, w))
cases.append(
    (False, (w / "x").exists(), "ADVANCE: the option-shaped step wrote no file through git diff")
)

# 13. A record-only commit's advance makes a dropped gate's --only run at the receipt tree still count: a non-reader's verdict cannot change across a confined step.
w, t0 = adv_world("dropped-verified-at-receipt-tree")
t1 = adv_commit(w, REVIEW)
adv_receipt(
    w,
    t0,
    [step(t0, t1, BOTH_REVIEW_READERS)],
    droppedTouched=[DROP],
    droppedVerified=passed_at(t0),
)
ADV_WORLDS.append(("ADVANCE: a --only pass at the receipt tree carries along the chain", 0, w))

for label, want, root in ADV_WORLDS:
    cases.append((want, drive(root, ADV_PUSH)[0], label))

# THE CONTROL: the guard's declared DEFECT replaces the confinement check with True. Both code worlds must flip to admitted (the suite's green depends on that line), and the reader worlds must NOT move (the plant is specific to confinement, not a guard that admits everything).
DEFECT_FLIPS = {
    "ADVANCE: records plus one code file is refused",
    "ADVANCE: a code-only commit is refused",
}
DEFECT_HOLDS = {
    "ADVANCE: a record-only commit with a reader NOT re-run is refused",
    "ADVANCE: a record-only commit with no advance is refused",
    "ADVANCE: a step starting off the chain does not reach HEAD",
}
for label, want, root in ADV_WORLDS:
    if label in DEFECT_FLIPS:
        cases.append((0, drive_broken(root, ADV_PUSH)[0], "DEFECT CONTROL flips: " + label))
    elif label in DEFECT_HOLDS:
        cases.append((want, drive_broken(root, ADV_PUSH)[0], "DEFECT CONTROL holds: " + label))
cases.append(
    (
        True,
        len([lab for lab, _, _ in ADV_WORLDS if lab in DEFECT_FLIPS | DEFECT_HOLDS]) == 5,
        "DEFECT CONTROL: every named world exists, so the control cannot shrink to nothing",
    )
)


# F11 DEFECT CONTROL: with `keyed_carry_vouches` forced True, the new-key world is admitted, so its refusal above is that function's equality check at work.
def drive_keyed_off(where, cmd):
    runner = (
        "import sys; sys.path.insert(0, %r)\n"
        "from rediacc_hooks import hookio\n"
        "src = open(%r, encoding='utf-8').read()\n"
        "ns = {'__name__': 'broken', '__file__': %r}\n"
        "exec(compile(src, 'broken', 'exec'), ns)\n"
        "ns['keyed_carry_vouches'] = lambda *a, **k: True\n"
        "ev = hookio.Event(sys.stdin.read())\n"
        "sys.exit(ns['run'](ev))\n"
    ) % (str(GUARD.parents[2]), str(GUARD), str(GUARD))
    proc = subprocess.run(
        [sys.executable, "-c", runner],
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=str(where),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(where)),
        check=False,
    )
    return proc.returncode


for label, _want, root in ADV_WORLDS:
    if label == "ADVANCE: a red reader with an uncarried new key is refused":
        cases.append((0, drive_keyed_off(root, ADV_PUSH), "F11 DEFECT CONTROL flips: " + label))
    elif label == "ADVANCE: a red reader whose recorded findings match a keyed carry is admitted":
        cases.append((0, drive_keyed_off(root, ADV_PUSH), "F11 DEFECT CONTROL holds: " + label))

# --- receipt v2: carried gates, recomputed at the pushed tree (PLAN-fast-loop F3) ---------------
V2_PUSH = "git push origin main"


def v2_world(name, variant, origin_verdict="ok"):
    root = pathlib.Path(tempfile.mkdtemp(dir=RUN_TMP)) / name
    GM._repo_v2_carried(root, variant, origin_verdict)
    return root


def drive_v2_off(where, cmd):
    """The guard with v2_verdict forced to accept, in a child: the planted DEFECT the v2 worlds must notice."""
    runner = (
        "import sys; sys.path.insert(0, %r)\n"
        "from rediacc_hooks import hookio\n"
        "src = open(%r, encoding='utf-8').read()\n"
        "ns = {'__name__': 'broken', '__file__': %r}\n"
        "exec(compile(src, 'broken', 'exec'), ns)\n"
        "ns['v2_verdict'] = lambda *a, **k: ''\n"
        "ev = hookio.Event(sys.stdin.read())\n"
        "sys.exit(ns['run'](ev))\n"
    ) % (str(GUARD.parents[2]), str(GUARD), str(GUARD))
    proc = subprocess.run(
        [sys.executable, "-c", runner],
        input=json.dumps({"tool_input": {"command": cmd}}),
        capture_output=True,
        text=True,
        cwd=str(where),
        env=dict(os.environ, CLAUDE_PROJECT_DIR=str(where)),
        check=False,
    )
    return proc.returncode, proc.stderr


def test_v2_carried_hash_match_allows():
    w = v2_world("v2-ok", "ok")
    cases.append(
        (0, drive(w, V2_PUSH)[0], "V2: a carried gate whose hashes still match is allowed")
    )


def test_v2_planted_input_change_refuses():
    w = v2_world("v2-stale", "stale-input")
    rc, err = drive(w, V2_PUSH)
    cases.append((2, rc, "V2: an input changed after the carry is refused"))
    cases.append(
        (
            True,
            "check:fx" in err and "filesHash" in err,
            "V2: and the refusal names the gate and filesHash",
        )
    )
    # THE DEFECT CONTROL: with v2_verdict forced to accept, the same world is admitted, so the refusal above is that function's work.
    cases.append(
        (
            0,
            drive_v2_off(w, V2_PUSH)[0],
            "V2 DEFECT CONTROL: v2_verdict forced to accept admits the stale input",
        )
    )
    ok = v2_world("v2-ok-control", "ok")
    cases.append(
        (
            0,
            drive_v2_off(ok, V2_PUSH)[0],
            "V2 DEFECT CONTROL holds: the matching world stays allowed",
        )
    )


def test_v2_carried_red_never_green():
    dropped = v2_world("v2-red-dropped", "red-dropped", "fail")
    rc, err = drive(dropped, V2_PUSH)
    cases.append((2, rc, "V2: a carried fail missing from `failed` is refused"))
    cases.append(
        (True, "failed" in err and "check:fx" in err, "V2: and the refusal names the mismatch")
    )
    flipped = v2_world("v2-red-flipped", "verdict-flipped", "fail")
    rc, err = drive(flipped, V2_PUSH)
    cases.append((2, rc, "V2: a carried verdict flipped to ok against its origin is refused"))
    cases.append((True, "verdict" in err or "failed" in err, "V2: and the refusal names a field"))
    honest = v2_world("v2-red-honest", "ok", "fail")
    cases.append(
        (2, drive(honest, V2_PUSH)[0], "V2: a carried red stays red (no carried-reds entry)")
    )
    gone = v2_world("v2-no-origin", "no-origin")
    rc, err = drive(gone, V2_PUSH)
    cases.append((2, rc, "V2: a carry with no archived origin receipt is refused"))
    cases.append(
        (
            0,
            drive_v2_off(dropped, V2_PUSH)[0],
            "V2 DEFECT CONTROL: the dropped red passes with v2_verdict off",
        )
    )


def test_v1_receipt_refused():
    w = pathlib.Path(tempfile.mkdtemp(dir=RUN_TMP)) / "v1"
    GM.FIXTURES["push-v1-receipt"](w)
    rc, err = drive(w, V2_PUSH)
    cases.append((2, rc, "V2: a receipt without schema 2 is refused"))
    cases.append(
        (
            True,
            "npm run ci:quick" in err and "schema" in err,
            "V2: and names the command that writes a v2 receipt",
        )
    )


def test_v2_helpers():
    cases.append((True, GM.v2_match_glob("src/**", "src/a/b.ts"), "GLOB: ** crosses /"))
    cases.append((False, GM.v2_match_glob("src/*", "src/a/b.ts"), "GLOB: * does not cross /"))
    cases.append((True, GM.v2_match_glob("src/*", "src/a.ts"), "GLOB: * matches within a segment"))
    cases.append((True, GM.v2_match_glob("a?", "a?"), "GLOB: ? is literal"))
    cases.append((False, GM.v2_match_glob("a?", "ab"), "GLOB: ? is not a wildcard"))
    cases.append((False, GM.v2_match_glob("**/*.ts", "x.ts"), "GLOB: **/ needs a slash"))
    cases.append(
        (
            True,
            GM.v2_match_glob("a.b", "a.b") and not GM.v2_match_glob("a.b", "axb"),
            "GLOB: . is literal",
        )
    )
    entries = [
        ("100644", "blob", "b" * 40, "src/z.ts"),
        ("160000", "commit", "c" * 40, "private/x"),
        ("100644", "blob", "a" * 40, "src/a.ts"),
        ("100644", "blob", "d" * 40, "other.txt"),
    ]
    lines = GM.v2_input_lines(entries, ["src/**", "private/x"], [])
    want = [
        "100644 %s\tsrc/a.ts" % ("a" * 40),
        "100644 %s\tsrc/z.ts" % ("b" * 40),
        "160000 %s\tprivate/x" % ("c" * 40),
    ]
    cases.append(
        (
            sorted(want, key=lambda x: x.split("\t")[1]),
            lines,
            "FILES: lines are `<mode> <oid>\\t<path>`, sorted by path, gitlink by name",
        )
    )
    manual = hashlib.sha256(("files\n" + "".join(x + "\n" for x in lines)).encode()).hexdigest()
    cases.append(
        (
            manual,
            GM.v2_files_hash(lines),
            "FILES: filesHash is sha256('files\\n' + lines each ending in newline)",
        )
    )
    cases.append(
        (
            GM.v2_files_hash(lines),
            GM.v2_files_hash(list(reversed(lines))),
            "FILES: the hash does not depend on input order",
        )
    )
    cases.append(
        (
            '{"a":[1,"é"],"b":{"c":true,"d":null}}',
            GM.v2_canon({"b": {"d": None, "c": True}, "a": [1, "é"]}),
            "CANON: sorted keys, no spaces, UTF-8",
        )
    )
    cases.append(
        (
            hashlib.sha256(b"def\n{}\n{}").hexdigest(),
            GM.v2_def_hash({}, {}),
            "DEF: defHash = sha('def\\n' + canon(entry) + '\\n' + canon(scripts))",
        )
    )


test_v2_carried_hash_match_allows()
test_v2_planted_input_change_refuses()
test_v2_carried_red_never_green()
test_v1_receipt_refused()
test_v2_helpers()

shutil.rmtree(d, ignore_errors=True)

bad = 0
for want, got, label in cases:
    if want != got:
        bad += 1
        print(f"  FAIL [{want}] {label} (got {got})")
print(
    f"FAILURES: {bad}  ({len(cases)} case(s), {sum(1 for w, _, _ in cases if w == 2)} block / "
    f"{sum(1 for w, _, _ in cases if w == 0)} allow / "
    f"{sum(1 for w, _, _ in cases if w is True)} message)"
)
sys.exit(1 if bad else 0)
