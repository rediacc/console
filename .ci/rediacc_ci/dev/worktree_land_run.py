"""`./run.sh worktree land <id> --run`: execute the picks `land` prints (PLAN-drain-throughput Design D, DT12).

Order: each submodule's picks, then the gitlink commit that bumps it, then the console's picks one at a time. A console conflict confined to `gen-docs` regions takes HEAD's copy, regenerates and continues; any other conflict stops with the paths printed and the pick left in progress. Afterwards new test files are placed on a shard and the queued TICK rows are applied. One line per step, with its rc.

`execute` is the testable core: it takes the resolved plan and runs git in the directories given.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import NamedTuple

GEN_DOCS = ("npx", "tsx", "scripts/gen/gen-docs.ts", "--write")
SHARD_CHECK = ("npx", "tsx", "scripts/gates/check-shard-manifest-coverage.ts")
SHARD_PLACE_RE = re.compile(r"npm run shard:place -- ([A-Za-z0-9._-]+)")
BEGIN_MARK = ">>> gen-docs"
END_MARK = "<<< gen-docs"
TRAILER_KEYS = ("PR-TASK:", "Plan-Box:")
TAIL = 300


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

    def step(self, name, rc, detail=""):
        self.emit("step %s rc=%d%s" % (name, rc, (" " + detail) if detail else ""))
        if rc:
            self.rc = 1
        return rc


def _dirty_index(dirs):
    return [str(d) for d in dirs if git(d, "diff", "--cached", "--quiet").returncode != 0]


def keep_head_hunks(text: str) -> str:
    """Resolve each conflict hunk to its HEAD side and keep every cleanly merged line as it is.

    Only called once `confined_to_generated` holds, so every hunk sits inside a `gen-docs` region that the
    regenerate step rewrites next. Taking HEAD's whole file instead (`checkout --ours`) would drop the lease
    commit's clean-merged edits outside the regions. A diff3 base section (`|||||||`) is dropped with the
    lease side. An unterminated hunk raises ValueError.
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


def _resolve_generated(plan, run, gen_cmd, sha):
    """Resolve the pick in progress when every conflicted path is a `gen-docs` region. False leaves it untouched."""
    paths = _unmerged(plan.live)
    if not paths:
        return False
    if not all(confined_to_generated((plan.live / p).read_text(encoding="utf-8")) for p in paths):
        return False
    for p in paths:
        target = plan.live / p
        try:
            target.write_text(keep_head_hunks(target.read_text(encoding="utf-8")), encoding="utf-8")
            rc = 0
        except (OSError, ValueError):
            rc = 1
        if run.step("take-head %s" % p, rc):
            return False
    done = subprocess.run(
        list(gen_cmd), cwd=str(plan.live), check=False, capture_output=True, text=True
    )
    if run.step(
        "gen-docs", done.returncode, done.stderr.strip()[-TAIL:] if done.returncode else ""
    ):
        return False
    if run.step("add generated", git(plan.live, "add", "--", *paths).returncode):
        return False
    env = {**os.environ, "GIT_EDITOR": "true"}
    cont = git(plan.live, "cherry-pick", "--continue", env=env)
    return not run.step(
        "continue %s" % sha[:12],
        cont.returncode,
        cont.stderr.strip()[-TAIL:] if cont.returncode else "",
    )


def _land_sub(plan, run, key, sub, shas, branch):
    """One submodule's picks and its gitlink commit. True on success."""
    detached = git(sub, "symbolic-ref", "-q", "HEAD").returncode != 0
    if (
        branch
        and detached
        and run.step("switch %s" % key, git(sub, "switch", "-c", branch).returncode)
    ):
        return False
    before = git(sub, "rev-parse", "HEAD").stdout.strip()
    pick = git(sub, "cherry-pick", "-x", *shas)
    if run.step(
        "pick %s" % key, pick.returncode, pick.stderr.strip()[-TAIL:] if pick.returncode else ""
    ):
        run.emit("stop: conflict in %s: %s" % (key, " ".join(_unmerged(sub)) or "see git status"))
        return False
    landed = git(sub, "rev-list", "--reverse", "%s..HEAD" % before).stdout.split()
    fd, msg = tempfile.mkstemp(prefix="land-run-", suffix=".msg")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_gitlink_message(plan, key, landed, shas))
        if run.step("add %s" % key, git(plan.live, "add", "--", key).returncode):
            return False
        done = git(plan.live, "commit", "-F", msg, "--", key)
        detail = (done.stderr or done.stdout).strip()[-TAIL:] if done.returncode else ""
        return not run.step("gitlink %s" % key, done.returncode, detail)
    finally:
        os.unlink(msg)


def execute(plan: LandPlan, *, emit=print, gen_cmd=GEN_DOCS) -> int:
    """Run the picks. Returns 0 when every pick landed, 1 on the first stop."""
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
        pick = git(live, "cherry-pick", "-x", sha)
        if pick.returncode == 0:
            run.step("pick %s" % sha[:12], 0)
            continue
        if _resolve_generated(plan, run, gen_cmd, sha):
            continue
        paths = _unmerged(live)
        run.step("pick %s" % sha[:12], 1)
        emit(
            "stop: conflict in %s; the cherry-pick is left in progress"
            % (" ".join(paths) or pick.stderr.strip()[-TAIL:])
        )
        return 1
    return run.rc


def after_picks(live, me, *, emit=print, shard_check=SHARD_CHECK) -> int:
    """Place new tests on a shard when the coverage gate names a lane, then apply the queued ticks for `me`."""
    run = Runner(emit)
    checked = subprocess.run(
        list(shard_check), cwd=str(live), capture_output=True, text=True, check=False
    )
    lanes = list(dict.fromkeys(SHARD_PLACE_RE.findall(checked.stdout + checked.stderr)))
    if not checked.returncode:
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
    if checked.returncode and not lanes:
        run.step("shard-coverage", checked.returncode, "names no lane to place")
    if me:
        script = pathlib.Path(live) / ".claude" / "hooks" / "stop" / "worklist.py"
        done = subprocess.run(
            [sys.executable, str(script), "--apply-ticks", me, "--write"],
            cwd=str(live),
            check=False,
        )
        run.step("apply-ticks", done.returncode)
    return run.rc
