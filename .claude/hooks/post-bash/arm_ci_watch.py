#!/usr/bin/env python3
"""PostToolUse: after a push of the live branch, arm ONE background CI watcher for the pushed head (agent/plans/PLAN-ci-verdict.md, box G).

WHY. The operator disabled the Stop hook on 2026-10-02, and with it went the only thing that told a session its CI had finished. So the push itself now starts the watch: `.ci/scripts/ci/ci-trace.py --wait --until-final` runs detached, and on its final verdict the tracer writes the branch-keyed cache beside the worklist (`wl_civerdict.write_cache`) and appends the verdict to the session's CI worklist item. A later turn, a SessionStart or another session reads it from disk with no network call.

ONE WATCHER PER HEAD. `<worklist>.ciwatch-<sha1(branch)[:8]>` records the head, pid, session and item of the watcher armed last. A second push of the same head (a retry, a no-op push, a submodule push from the same turn) finds that watcher alive and arms nothing. A new head arms a new watcher; the old one keeps running until its own head's verdict, which is still a true statement about that head.

ONLY A PUSH THAT MOVED THE LIVE BRANCH. The command must mention `git push` (the same test cancel_old_ci.py uses), and afterwards `origin/<branch>` must equal `HEAD`: git updates the remote-tracking ref only on a successful push, so a failed push, a push of a submodule, or a push of some other ref leaves them apart and nothing is armed. `main` and a detached HEAD are never watched.

THE ITEM. The session's CI item is reused while it is open (its id is in the state file and a fresh `--lease` on it succeeds); otherwise `worklist.py --add` makes one, tagged with the session prefix. The lease names `worker:<pid>`: the watcher is a detached process, not a harness background task, so the roster reports it as unverifiable rather than dead, which is the documented reading of such a worker. Leases are capped at `wl_core.MAX_LEASE_MIN`.

Advisory: always exits 0, prints one line when it armed or reused a watcher, and never blocks the tool call that already ran.
"""

import contextlib
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time

HOOKS = pathlib.Path(__file__).resolve().parents[1]


def _load_syspath():
    """The canonical `.claude` hop, rediacc_hooks/syspath.py, loaded BY PATH: this hook runs as a script, so `rediacc_hooks` is not importable by name until the hop has run."""
    hop_file = HOOKS.parent / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop_file)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_SYSPATH = _load_syspath()
_SYSPATH.on_sys_path(_SYSPATH.CLAUDE_DIR)
_SYSPATH.on_sys_path(_SYSPATH.STOP_DIR)

import wl_core as C  # noqa: E402
from rediacc_hooks import hookio  # noqa: E402

TRACE = pathlib.Path(".ci") / "scripts" / "ci" / "ci-trace.py"
WORKLIST = HOOKS / "stop" / "worklist.py"
WATCH_TIMEOUT = "3h"
LEASE_MIN = 180  # the worklist clamps it to wl_core.MAX_LEASE_MIN
ADDED_RE = re.compile(r"added #([0-9a-f]+)")

ARMED = "CI watch armed for %s @ %s: ci-trace --wait --until-final (pid %s), verdict lands on worklist #%s and the branch cache."
REUSED = "CI watch already running for %s @ %s (pid %s, worklist #%s); none armed."


def state_path(worklist, branch):
    tag = hashlib.sha1((branch or "").encode("utf-8")).hexdigest()[:8]
    return pathlib.Path("%s.ciwatch-%s" % (worklist, tag))


def read_state(path):
    try:
        doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def write_state(path, doc):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    os.replace(tmp, path)


def watcher_alive(pid):
    """True when `pid` is a live process whose command line is a ci-trace watch. A recycled pid running something else is not our watcher."""
    try:
        pid = int(pid)
        os.kill(pid, 0)
    except (TypeError, ValueError, ProcessLookupError, PermissionError, OSError):
        return False
    try:
        cmdline = pathlib.Path("/proc/%d/cmdline" % pid).read_bytes()
    except OSError:
        return True  # no /proc: the signal probe is the best evidence there is
    return b"ci-trace" in cmdline


def _git(root, *args):
    return hookio.git_out(list(args), cwd=root).strip()


def worklist_cli(root, sid, *argv):
    """(rc, stdout) of one worklist verb, run AS this session so `<me>` checks pass."""
    env = dict(os.environ, WORKLIST_SESSION_ID=sid)
    try:
        done = subprocess.run(
            [sys.executable, str(WORKLIST), *argv],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(root),
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout


def spawn_watch(root, sid, branch, item, log_path):
    """Start the detached tracer; returns its pid."""
    argv = [
        sys.executable,
        str(pathlib.Path(root) / TRACE),
        "--wait",
        "--until-final",
        "--timeout",
        WATCH_TIMEOUT,
        "--ref",
        branch,
        "--worklist-item",
        item,
        "--session",
        sid[:8],
    ]
    with open(log_path, "ab") as log:
        # Fixed argv, no shell.
        proc = subprocess.Popen(
            argv,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=dict(os.environ, WORKLIST_SESSION_ID=sid),
        )
    return proc.pid


def arm(root, sid, cli=worklist_cli, spawn=spawn_watch, alive=watcher_alive):
    """Arm (or reuse) the watcher for the pushed head. Returns the line to print, or ""."""
    branch = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    if not branch or branch == "main" or not sid:
        return ""
    head = _git(root, "rev-parse", "HEAD")
    if not head or _git(root, "rev-parse", "origin/%s" % branch) != head:
        return ""
    me = sid[:8]
    worklist = C.worklist_for(root)
    sp = state_path(worklist, branch)
    st = read_state(sp)
    if st.get("head") == head and alive(st.get("pid")):
        return REUSED % (branch, head[:8], st.get("pid"), st.get("item") or "?")
    items = st.get("items") if isinstance(st.get("items"), dict) else {}
    item = items.get(me) or ""
    log_path = pathlib.Path("%s.ciwatch-%s.log" % (worklist, me))
    if item:
        pid = spawn(root, sid, branch, item, log_path)
        rc, _out = cli(root, sid, "--lease", me, item, "+%d" % LEASE_MIN, "worker:%s" % pid)
        if rc != 0:
            # Ticked or gone: a new item below, and a watcher pointed at it.
            item = ""
            _kill(pid)
    if not item:
        rc, out = cli(
            root,
            sid,
            "--add",
            me,
            "(%s) CI verdict for %s: the push hook's background ci-trace watch writes the final verdict here; "
            "tick it once the verdict is read and acted on" % (me, branch),
        )
        m = ADDED_RE.search(out or "")
        if rc != 0 or not m:
            return ""
        item = m.group(1)
        pid = spawn(root, sid, branch, item, log_path)
        cli(root, sid, "--lease", me, item, "+%d" % LEASE_MIN, "worker:%s" % pid)
    items[me] = item
    write_state(
        sp,
        {
            "branch": branch,
            "head": head,
            "pid": pid,
            "item": item,
            "session": me,
            "at": time.time(),
            "items": items,
        },
    )
    return ARMED % (branch, head[:8], pid, item)


def _kill(pid):
    with contextlib.suppress(OSError, ValueError, TypeError):
        os.killpg(int(pid), 15)


def main():
    payload = sys.stdin.read()
    ev = hookio.Event(payload)
    if not hookio.grep_q_line(
        "git push", hookio.normalize_git_push(ev.raw("tool_input", "command"))
    ):
        return 0
    try:
        line = arm(ev.project_dir, ev.field("session_id"))
    except Exception as exc:  # noqa: BLE001 -- advisory: a broken arm says so and lets the tool call stand
        line = "CI watch NOT armed (hook error %s: %s)" % (type(exc).__name__, str(exc)[:160])
    if line:
        sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
