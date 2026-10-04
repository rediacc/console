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
# THE GUARD IS A PYTHON MODULE NOW. W5 P7 ported it from a bash original that PLAN-retire-bash-oracles A3 later deleted, once the differential compared the two byte for byte and froze the result as a golden (tests/goldens/<stem>.jsonl). This harness drives the LIVE guard, which is the dispatcher, for the reason the cutover exists at all: a suite that kept driving the retired file would keep passing while the thing that actually runs went unchecked.
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
        "droppedTouched": [],
        "droppedVerified": {},
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
cases = []


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
            {
                "headTree": g(where, "rev-parse", "HEAD^{tree}"),
                "whole": True,
                "exitCode": 0,
                "droppedTouched": [],
            }
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
