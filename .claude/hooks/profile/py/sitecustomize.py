"""Arm the resource exit-recorder for EVERY python3 under this repo.

WHY THIS FILE EXISTS. `wl_core.py` arms `wl_resprofile.install()`, so coverage was
"processes that import wl_core", not "every python3" -- and the progress doc claimed
the latter. Measured 2026-09-03: three `python3 -c pass` calls added ZERO records to
exit.jsonl. `sitecustomize` is imported by `site` at interpreter startup, before any
user code, which is the only seam that reaches a plain `python3` without rewriting
the command (a PreToolUse hook cannot mutate tool_input.command).

WHY IT IS SEPARATE FROM wl_resprofile, and why it imports so little. Importing that
module costs +33 ms at interpreter start because it pulls in json, pathlib and
tempfile. That is fine for a hook process, which imports them anyway; it is not fine
on EVERY python3, where it roughly doubles startup. So this file carries its own
minimal recorder: os, sys, time, resource, atexit, and `%`-formatted JSON. The
record is byte-compatible with wl_resprofile's `v:1` shape, deliberately, so one
reader serves both.

WE SHADOW THE DISTRO sitecustomize, so we re-export it. `/usr/lib/python3.14/
sitecustomize.py` installs apport's exception hook; PYTHONPATH precedes stdlib on
sys.path, so ours wins and apport would silently vanish. Its five lines are
reproduced verbatim at the end.

CONTRACTS, and they are not optional because this runs on every interpreter:
never print, never raise, never change the exit status, and write nothing when the
cwd is outside the repo. `WORKLIST_PROFILE=off` disables it. A root that resolves to
`/` is REFUSED -- that is how a module copied to a fixture path once made every cwd
on the machine in scope, and the stray `~/.claude/resprofile/<day>/` folder it left
is still there.

ONE RECORD PER PROCESS. `_WL_SITEPROFILE` marks the interpreter as armed; wl_core's
own `install()` is idempotent by `atexit` but would double-count, so it checks the
same marker.
"""

import atexit
import os
import resource
import sys
import time

_T0 = time.monotonic()
_ARMED = "_WL_SITEPROFILE"


def _root():
    """<repo>/.claude/hooks/profile/py/sitecustomize.py -> <repo>, or None."""
    try:
        p = os.path.realpath(__file__)
        for _ in range(5):
            p = os.path.dirname(p)
        return p if p and p != "/" else None
    except BaseException:  # noqa: BLE001 -- silence is this file's contract
        return None


def _in_scope(root):
    try:
        c = os.path.realpath(os.getcwd())
    except BaseException:  # noqa: BLE001 -- silence is this file's contract
        return False
    return c == root or c.startswith(root + os.sep)


def _shape(root):
    """`py:<repo-relative argv[0]>[#<verb>]`; argv beyond argv[1] is never read."""
    argv = sys.argv or [""]
    s = argv[0] or ""
    try:
        r = os.path.realpath(s)
        rel = r[len(root) + 1 :] if r.startswith(root + os.sep) else "<external>"
    except BaseException:  # noqa: BLE001 -- silence is this file's contract
        rel = "<external>"
    if not s or s in ("-c", "-"):
        rel = "<inline>"
    verb = ""
    a1 = argv[1] if len(argv) > 1 else ""
    if a1.startswith("--") and len(a1) <= 24 and a1[2:].replace("-", "").isalnum():
        verb = "#" + a1[2:]
    return "py:%s%s" % (rel, verb)


def _proc_int(path, keys):
    out = {}
    try:
        with open(path) as fh:
            for line in fh:
                k, _, v = line.partition(":")
                if k in keys:
                    out[k] = int(v.split()[0])
    except BaseException:  # noqa: BLE001 -- silence is this file's contract
        pass
    return out


def _run_delay_ns():
    """schedstat field 2. PROBED, not read from kernel.sched_schedstats.

    That sysctl is 0 on this kernel and the counter is live anyway: measured
    2026-09-03, two burners pinned to one core read run_delay=752ms while a third
    alone on its own core read 0. wl_resprofile reported this signal dead from the
    sysctl, which is the mirror image of trusting a flag over a measurement.
    """
    try:
        with open("/proc/self/schedstat") as fh:
            f = fh.read().split()
        return int(f[1]) if len(f) >= 3 else None
    except BaseException:  # noqa: BLE001 -- silence is this file's contract
        return None


def _esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _on_exit(root, day_dir):
    try:
        # THE RICHER RECORDER WINS. A hook process imports wl_core, which arms
        # wl_resprofile with PSI, cgroup scope and availability flags this file
        # deliberately does not pay for. It stamps the marker "super" when it does,
        # and the check happens HERE, at exit, so atexit ordering cannot decide it.
        if os.environ.get(_ARMED) == "super":
            return
        rs = resource.getrusage(resource.RUSAGE_SELF)
        rc = resource.getrusage(resource.RUSAGE_CHILDREN)
        io = _proc_int("/proc/self/io", ("rchar", "wchar", "read_bytes", "write_bytes"))
        hwm = _proc_int("/proc/self/status", ("VmHWM",)).get("VmHWM")
        rd = _run_delay_ns()
        tmp = os.environ.get("TMPDIR", "")
        rec = (
            '{"v":1,"t":%d,"shape":"%s","wall_ms":%d,"cpu_ms":%d,"child_cpu_ms":%d,'
            '"rss_kb":%d,"child_rss_kb_max":%d,"io":{%s},"run_delay_ns":%s,'
            '"src":"site","fixture":%s}\n'
        ) % (
            int(time.time() * 1000),
            _esc(_shape(root)),
            int((time.monotonic() - _T0) * 1000),
            int((rs.ru_utime + rs.ru_stime) * 1000),
            int((rc.ru_utime + rc.ru_stime) * 1000),
            hwm if hwm is not None else rs.ru_maxrss,
            rc.ru_maxrss,
            ",".join('"%s":%d' % (k, v) for k, v in sorted(io.items())),
            "null" if rd is None else str(rd),
            "true" if (tmp.startswith("/tmp") and "hookfix" in tmp) else "false",
        )
        fd = os.open(
            os.path.join(day_dir, "exit.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
        )
        try:
            os.write(fd, rec.encode())
        finally:
            os.close(fd)
    except BaseException:  # noqa: BLE001 -- silence is this file's contract
        pass


def _install():
    try:
        if os.environ.get("WORKLIST_PROFILE") == "off":
            return
        if os.environ.get(_ARMED):
            return
        root = _root()
        if root is None or not _in_scope(root):
            return
        slug = root.lstrip("/").replace("/", "-")
        day = time.strftime("%Y-%m-%d")
        d = os.path.join(os.path.expanduser("~"), ".claude", "resprofile", slug, day)
        os.makedirs(d, exist_ok=True)
        os.environ[_ARMED] = "1"
        atexit.register(_on_exit, root, d)
    except BaseException:  # noqa: BLE001 -- silence is this file's contract
        pass


_install()

# The distro sitecustomize we shadow, verbatim: install the apport exception
# handler if available.
try:
    import apport_python_hook
except ImportError:
    pass
else:
    apport_python_hook.install()
