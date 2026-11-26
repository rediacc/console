"""`./run.sh worktree land <id> --run`: execute the picks `land` prints (PLAN-drain-throughput Design D, DT12).

Order: each submodule's picks, then the gitlink commit that bumps it, then the console's picks one at a time. A console conflict confined to `gen-docs` regions takes HEAD's copy, regenerates and continues; any other conflict stops with the paths printed and the pick left in progress. A git step refused because another git process holds the index lock (a background reviewer running git in the same repository) waits and retries a bounded number of times, resuming a pick left in progress with `cherry-pick --continue`; a lock still held is named as a lock, never as a conflict. Afterwards new test files are placed on a shard and the queued TICK rows are applied. One line per step, with its rc.

`execute` is the testable core: it takes the resolved plan and runs git in the directories given.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from typing import NamedTuple

GEN_DOCS = ("npx", "tsx", "scripts/gen/gen-docs.ts", "--write")
SHARD_CHECK = ("npx", "tsx", "scripts/gates/check-shard-manifest-coverage.ts")
SHARD_PLACE_RE = re.compile(r"npm run shard:place -- ([A-Za-z0-9._-]+)")
# A lane `shard:place` refuses (scripts/ci-runner/shard-place.ts PLACE_REFUSED) gets another verb in the gate's line, which only the lead can run: a bucketed lane is rebalanced, quality-code is generated.
UNPLACEABLE_RE = re.compile(
    r"^.*?(?:lightest leg|Add it to a leg): (?!npm run shard:place)(npx tsx .+?)\s*$", re.MULTILINE
)
REBALANCE_LANE_RE = re.compile(r"--rebalance ([A-Za-z0-9._-]+)")
FIXES_REVIEW_RE = re.compile(r"^Fixes-Review:\s*(\S+)\s*$", re.MULTILINE)
BEGIN_MARK = ">>> gen-docs"
END_MARK = "<<< gen-docs"
TRAILER_KEYS = ("PR-TASK:", "Plan-Box:")
TAIL = 300
# #125874ca: git refuses a step when another process holds a `.lock` (index.lock most often); the holder is usually gone within a second.
LOCK_RE = re.compile(r"Unable to create '([^'\n]+\.lock)': File exists")
LOCK_WAITS = (0.5, 1.0, 2.0, 4.0)
SLEEP = time.sleep


def continue_env():
    """The environment of a `cherry-pick --continue`, read at call time so an editor setting changed after import is seen."""
    return {**os.environ, "GIT_EDITOR": "true"}


class LandPlan(NamedTuple):
    """What `--run` executes. `subs` is [(key, live submodule dir, lease shas oldest first)]; `console` the console shas oldest first; `messages` maps a sha to its lease commit message."""

    live: pathlib.Path
    lease_id: str
    subs: list
    console: list
    messages: dict


def git(cwd, *args, env=None):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def confined_to_generated(text: str) -> bool:
    """True when the file has conflict hunks and every hunk lies strictly inside one `gen-docs` block."""
    inside, hunk, saw = False, False, False
    for line in text.splitlines():
        if line.startswith("<<<<<<<"):
            if not inside:
                return False
            hunk, saw = True, True
        elif line.startswith(">>>>>>>"):
            hunk = False
        elif BEGIN_MARK in line or END_MARK in line:
            if hunk:
                return False
            inside = BEGIN_MARK in line
    return saw and not hunk


def _unmerged(live):
    listed = git(live, "diff", "--name-only", "--diff-filter=U").stdout
    return [p for p in listed.splitlines() if p]


def held_lock(cwd, done) -> str:
    """The full path of the lock file a failed git step could not create, or "" when it failed for another reason."""
    if done.returncode == 0:
        return ""
    found = LOCK_RE.search((done.stderr or "") + (done.stdout or ""))
    return str(pathlib.Path(cwd) / found.group(1)) if found else ""


def _picking(cwd) -> bool:
    return git(cwd, "rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD").returncode == 0


def _sequencing(cwd) -> bool:
    rel = git(cwd, "rev-parse", "--git-path", "sequencer").stdout.strip()
    return bool(rel) and (pathlib.Path(cwd) / rel).is_dir()


def retry_lock(cwd, *args, env=None):
    """Run a git step, and while it fails on a held lock wait and run it again, up to `len(LOCK_WAITS)` times. Returns the last result.

    A cherry-pick the lock stopped after it applied (CHERRY_PICK_HEAD set, no conflicted path) resumes with `cherry-pick --continue` rather than starting again. A sequence stopped with no CHERRY_PICK_HEAD is not resumed: `--continue` would skip its current commit, so the lock failure is returned for the caller to name.
    """
    done = git(cwd, *args, env=env)
    for wait in LOCK_WAITS:
        if not held_lock(cwd, done):
            return done
        SLEEP(wait)
        if args[0] == "cherry-pick" and _picking(cwd):
            if _unmerged(cwd):
                return done
            done = git(cwd, "cherry-pick", "--continue", env=continue_env())
        elif args[0] == "cherry-pick" and _sequencing(cwd):
            return done
        else:
            done = git(cwd, *args, env=env)
    return done


def _first_line(text):
    return next((line.strip() for line in (text or "").splitlines() if line.strip()), "")


def _failed_pick_stop(cwd, done, what, prefix=""):
    """The stop line for a pick that failed: the conflicted paths (under `prefix`, a submodule's key), a held lock with its full path, or git's own first line."""
    left = (
        "the cherry-pick is left in progress"
        if _picking(cwd) or _sequencing(cwd)
        else "the pick of %s did not run" % what
    )
    paths = [prefix + p for p in _unmerged(cwd)]
    lock = held_lock(cwd, done)
    if lock and not paths:
        kind = "index lock" if lock.endswith("index.lock") else "git lock"
        return "stop: %s %s is still held by another git process after %d retries; %s" % (
            kind,
            lock,
            len(LOCK_WAITS),
            left,
        )
    if paths:
        return "stop: conflict in %s; the cherry-pick is left in progress" % " ".join(paths)
    return "stop: the pick of %s failed without a conflicted path: %s; %s" % (
        what,
        _first_line(done.stderr or done.stdout) or "rc=%d" % done.returncode,
        left,
    )


def _trailers(messages):
    seen: list[str] = []
    for message in messages:
        for line in message.splitlines():
            if line.startswith(TRAILER_KEYS) and line not in seen:
                seen.append(line)
    return seen


def _gitlink_message(plan, key, landed, picked):
    name = pathlib.PurePath(key).name
    body = [
        "chore(%s): land lease %s commits" % (name, plan.lease_id),
        "",
        "Submodule %s landed %s from lease %s."
        % (key, ", ".join(s[:12] for s in landed), plan.lease_id),
        "",
    ]
    body += _trailers(plan.messages.get(s, "") for s in picked)
    return "\n".join(body) + "\n"


class Runner:
    def __init__(self, emit):
        self.emit = emit
        self.rc = 0
        self.landed: list[tuple[str, str]] = []  # (lease sha, landed sha), in landing order

    def step(self, name, rc, detail=""):
        self.emit("step %s rc=%d%s" % (name, rc, (" " + detail) if detail else ""))
        if rc:
            self.rc = 1
        return rc


def _dirty_index(dirs):
    return [str(d) for d in dirs if git(d, "diff", "--cached", "--quiet").returncode != 0]


def keep_head_hunks(text: str) -> str:
    """Resolve each conflict hunk to its HEAD side and keep every cleanly merged line as it is.

    Only called once `confined_to_generated` holds, so every hunk sits inside a `gen-docs` region that the regenerate step rewrites next. Taking HEAD's whole file instead (`checkout --ours`) would drop the lease commit's clean-merged edits outside the regions. A diff3 base section (`|||||||`) is dropped with the lease side. An unterminated hunk raises ValueError.
    """
    out: list[str] = []
    state = "clean"
    for line in text.splitlines(keepends=True):
        if state == "clean":
            if line.startswith("<<<<<<< "):
                state = "head"
            else:
                out.append(line)
        elif state == "head":
            if line.startswith("||||||| "):
                state = "base"
            elif line.rstrip("\r\n") == "=======":
                state = "lease"
            else:
                out.append(line)
        elif state == "base":
            if line.rstrip("\r\n") == "=======":
                state = "lease"
        elif line.startswith(">>>>>>> "):
            state = "clean"
    if state != "clean":
        raise ValueError("unterminated conflict hunk")
    return "".join(out)


def _read(path):
    """The file's text with its line endings untouched (no universal-newline translation), or None for a missing or non-UTF-8 file."""
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _resolve_generated(plan, run, gen_cmd, sha, emit):
    """Resolve the pick in progress when every conflicted path is a `gen-docs` region.

    None: not applicable (a conflict outside the regions, a modify/delete or binary conflict); nothing was touched. True: resolved and continued. False: a step failed (a take-head rewrite, gen-docs, the add or the continue), possibly before any file was rewritten; the stop line naming the paths has been emitted and the pick is left in progress.
    """
    paths = _unmerged(plan.live)
    if not paths:
        return None
    texts = [_read(plan.live / p) for p in paths]
    if not all(t is not None and confined_to_generated(t) for t in texts):
        return None

    def stop(step):
        emit(
            "stop: %s failed for %s; the cherry-pick is left in progress" % (step, " ".join(paths))
        )
        return False

    for p, text in zip(paths, texts, strict=True):
        try:
            (plan.live / p).write_bytes(keep_head_hunks(text).encode("utf-8"))
            rc = 0
        except (OSError, ValueError):
            rc = 1
        if run.step("take-head %s" % p, rc):
            return stop("take-head")
    done = subprocess.run(
        list(gen_cmd), cwd=str(plan.live), check=False, capture_output=True, text=True
    )
    if run.step(
        "gen-docs", done.returncode, done.stderr.strip()[-TAIL:] if done.returncode else ""
    ):
        return stop("gen-docs")
    if run.step("add generated", retry_lock(plan.live, "add", "--", *paths).returncode):
        return stop("add generated")
    cont = retry_lock(plan.live, "cherry-pick", "--continue", env=continue_env())
    if run.step(
        "continue %s" % sha[:12],
        cont.returncode,
        cont.stderr.strip()[-TAIL:] if cont.returncode else "",
    ):
        return stop("continue")
    return True


def _land_sub(plan, run, key, sub, shas, branch):
    """One submodule's picks and its gitlink commit. True on success."""
    detached = git(sub, "symbolic-ref", "-q", "HEAD").returncode != 0
    if (
        branch
        and detached
        and run.step("switch %s" % key, retry_lock(sub, "switch", "-c", branch).returncode)
    ):
        return False
    before = git(sub, "rev-parse", "HEAD").stdout.strip()
    pick = retry_lock(sub, "cherry-pick", "-x", *shas)
    tail = (pick.stderr or pick.stdout).strip()[-TAIL:] if pick.returncode else ""
    if run.step("pick %s" % key, pick.returncode, tail):
        run.emit(_failed_pick_stop(sub, pick, key, key.rstrip("/") + "/"))
        return False
    landed = git(sub, "rev-list", "--reverse", "%s..HEAD" % before).stdout.split()
    if len(landed) == len(shas):
        run.landed.extend(zip(shas, landed, strict=True))
    else:
        run.step(
            "landed-count %s" % key,
            1,
            "picked %d commit(s) but %d landed; their Fixes-Review trailers are not marked"
            % (len(shas), len(landed)),
        )
    return _land_gitlink(plan, run, key, landed, shas)


def _land_gitlink(plan, run, key, landed, shas):
    """The console commit that bumps submodule `key` to its landed tip. True on success."""
    fd, msg = tempfile.mkstemp(prefix="land-run-", suffix=".msg")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_gitlink_message(plan, key, landed, shas))
        if run.step("add %s" % key, retry_lock(plan.live, "add", "--", key).returncode):
            return False
        done = retry_lock(plan.live, "commit", "-F", msg, "--", key)
        detail = (done.stderr or done.stdout).strip()[-TAIL:] if done.returncode else ""
        return not run.step("gitlink %s" % key, done.returncode, detail)
    finally:
        os.unlink(msg)


def execute(plan: LandPlan, *, emit=print, gen_cmd=GEN_DOCS, me="") -> int:
    """Run the picks. Returns 0 when every pick landed, 1 on the first stop. With `me`, the review findings the landed commits name (`Fixes-Review:` trailers) are marked fixed once every pick has landed."""
    run = Runner(emit)
    live = plan.live
    dirty = _dirty_index([live, *(d for _k, d, _s in plan.subs)])
    if dirty:
        emit("refused: staged changes in %s" % ", ".join(dirty))
        return 1
    branch = git(live, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    for key, sub, shas in plan.subs:
        if not _land_sub(plan, run, key, sub, shas, branch):
            return 1
    for sha in plan.console:
        pick = retry_lock(live, "cherry-pick", "-x", sha)
        if pick.returncode == 0:
            run.step("pick %s" % sha[:12], 0)
            run.landed.append((sha, git(live, "rev-parse", "HEAD").stdout.strip()))
            continue
        resolved = (
            None if held_lock(live, pick) else _resolve_generated(plan, run, gen_cmd, sha, emit)
        )
        if resolved:
            run.landed.append((sha, git(live, "rev-parse", "HEAD").stdout.strip()))
            continue
        if resolved is False:
            return 1
        run.step("pick %s" % sha[:12], 1)
        emit(_failed_pick_stop(live, pick, sha[:12]))
        return 1
    if me:
        _mark_reviews(plan, run, me)
    return run.rc


def _mark_reviews(plan, run, me):
    """`worklist.py --review-mark <me> <id> fixed <landed sha>` for each `Fixes-Review:` trailer of a landed commit, one step line each."""
    script = pathlib.Path(plan.live) / ".claude" / "hooks" / "stop" / "worklist.py"
    for lease_sha, landed in run.landed:
        for finding in dict.fromkeys(FIXES_REVIEW_RE.findall(plan.messages.get(lease_sha, ""))):
            done = subprocess.run(
                [sys.executable, str(script), "--review-mark", me, finding, "fixed", landed],
                cwd=str(plan.live),
                capture_output=True,
                text=True,
                check=False,
            )
            tail = (done.stderr or done.stdout).strip()[-TAIL:] if done.returncode else ""
            run.step("review-mark %s %s" % (finding, landed[:12]), done.returncode, tail)


def _coverage(live, shard_check):
    done = subprocess.run(
        list(shard_check), cwd=str(live), capture_output=True, text=True, check=False
    )
    return done.returncode, done.stdout + done.stderr


def after_picks(live, me, *, emit=print, shard_check=SHARD_CHECK) -> int:
    """Place new tests on a shard when the coverage gate names a lane, then apply the queued ticks for `me`.

    A lane the gate sends to another verb (a bucketed lane's `check-lane-budget.ts --rebalance`, quality-code's `gate-bind`) is a stop for the lead: it is named with the gate's own line. After a placement the gate runs again, so a red gate is never reported green because `shard:place` itself succeeded.
    """
    run = Runner(emit)
    code, text = _coverage(live, shard_check)
    lanes = list(dict.fromkeys(SHARD_PLACE_RE.findall(text)))
    refused = [m.group(0).strip() for m in UNPLACEABLE_RE.finditer(text)]
    if not code:
        emit("step shard-coverage rc=0")
    for lane in lanes:
        done = subprocess.run(
            ["npm", "run", "shard:place", "--", lane],
            cwd=str(live),
            capture_output=True,
            text=True,
            check=False,
        )
        run.step("shard:place %s" % lane, done.returncode)
    for line in dict.fromkeys(refused):
        found = REBALANCE_LANE_RE.search(line)
        lane = found.group(1) if found else "(see the gate line)"
        run.step("shard-coverage", code or 1, "lane %s is not placed by --run" % lane)
        emit("stop: coverage gate line for the lead: %s" % line)
    if code and lanes:
        again, _text = _coverage(live, shard_check)
        run.step("shard-coverage recheck", again, "still red after placing" if again else "")
    elif code and not refused:
        run.step("shard-coverage", code, "names no lane to place")
    if me:
        script = pathlib.Path(live) / ".claude" / "hooks" / "stop" / "worklist.py"
        applied = subprocess.run(
            [sys.executable, str(script), "--apply-ticks", me, "--write"],
            cwd=str(live),
            check=False,
        )
        run.step("apply-ticks", applied.returncode)
    return run.rc
