"""One flock per named shared resource: the VM fleet, and each bench region.

THE RESOURCES (PLAN-push-decoupling.md D1.5, D1.6). The KVM fleet (`fleet`) is reset by the e2e-local setup, driven by vm:check and the drills, and rebuilt by `./rdc.sh ops up|down`; a bench region (`bench-<region>`) is deployed, reset and proved by four runners. Before this module only vm:check took a lock, so two of the others could interleave on one resource.

THE PATH. Every resource's file sits in the directory `rediacc_ci.drills.vm_check.lock_path` picks: `$XDG_RUNTIME_DIR`, then `/run/user/<uid>`, each only when it is this user's directory, else a per-user name in /tmp. `fleet` keeps vm:check's own file name, `rediacc-vm-check.lock` (`rediacc-vm-check-<uid>.lock` in /tmp), so vm:check, this module and `wl_checks.vm_check_running` meet on one file.

THE PAYLOAD is JSON `{pid, session, purpose, since}`: vm:check writes the same keys minus `purpose`, so a holder written by either reads in both.

THE WAIT is bounded. A second holder polls until `wait_s` runs out, printing the holder once to stderr, then raises `ResourceBusyError` naming the resource, the file and the holder.

A NESTED HOLDER. A process whose ANCESTOR holds the resource (a drill vm:check runs, `./rdc.sh ops up` under the wrapper), or a second lock object in the process that holds it, is already inside the hold: it takes nothing, waits for nothing and releases nothing (`ResourceLock.nested`). Without that rule the child would wait on its own parent until the wait ran out. A nested object protects nothing of its own, so the object that holds the resource must outlive it (release the nested one first).

THE WRAPPER, for callers that are not Python:

    python3 -m rediacc_ci.core.resource_lock run --resource fleet [--wait S] [--purpose P] -- <argv>

holds the lock for the child's life and exits with the child's code (128+N when signal N killed it). The lock fd is close-on-exec, so a daemon the child leaves behind never inherits it.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import math
import os
import pathlib
import re
import signal
import stat
import subprocess
import sys
import time
from typing import TYPE_CHECKING

if sys.platform != "win32":
    import fcntl

if TYPE_CHECKING:  # annotation-only import
    from collections.abc import Callable, Iterator, Mapping, Sequence

DEFAULT_WAIT_S = 600.0
POLL_S = 0.2
# Exit code of the wrapper when the wait ran out: 75 is EX_TEMPFAIL, the resource is busy, try again later.
EXIT_BUSY = 75
# The file stem of a resource whose name predates this module.
LEGACY_STEMS = {"fleet": "rediacc-vm-check"}
RESOURCE_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


class ResourceBusyError(RuntimeError):
    """The resource stayed held by another process for the whole wait."""

    def __init__(self, resource: str, path: pathlib.Path, holder: str, waited: float) -> None:
        super().__init__(
            "resource %s is busy: %s holds %s after %ds" % (resource, holder, path, int(waited))
        )
        self.resource = resource
        self.path = path
        self.holder = holder
        self.waited = waited


class LockFileRefusedError(ResourceBusyError):
    """The lock file is not safe to use (a symlink, or not this user's private file); a ResourceBusyError so every caller refuses the run with a message rather than a traceback."""

    def __init__(self, resource: str, path: pathlib.Path, reason: str) -> None:
        RuntimeError.__init__(
            self, "resource %s: refusing lock file %s: %s" % (resource, path, reason)
        )
        self.resource = resource
        self.path = path
        self.holder = "unknown"
        self.waited = 0.0


class WaitSettingError(ResourceBusyError):
    """A wait setting (`BENCH_LOCK_WAIT_S`, `RESOURCE_LOCK_WAIT_S`) that is not a finite, non-negative number of seconds; a ResourceBusyError so every caller refuses the run with a message rather than a traceback."""

    def __init__(self, name: str, raw: str) -> None:
        RuntimeError.__init__(
            self, "%s=%r is not a finite, non-negative number of seconds" % (name, raw)
        )
        self.resource = name
        self.path = pathlib.Path("-")
        self.holder = "unknown"
        self.waited = 0.0


def bench_resource(region: str) -> str:
    """The resource of one bench region: `bench-eu`, `bench-us`, ... A blank region is a ValueError, never the one shared `bench-` lock."""
    name = (region or "").strip().lower()
    if not name:
        raise ValueError("a bench region is required; a blank one would take one shared lock")
    return "bench-%s" % name


def _check_name(resource: str) -> str:
    if not RESOURCE_RE.match(resource or ""):
        raise ValueError("resource name %r is not lower-case letters, digits and dashes" % resource)
    return resource


def lock_path(resource: str, environ: Mapping[str, str] | None = None) -> pathlib.Path:
    """The lock file of `resource`, in the directory vm:check's `lock_path` picks; `fleet` is vm:check's own file."""
    stem = LEGACY_STEMS.get(_check_name(resource), "rediacc-%s" % resource)
    env = os.environ if environ is None else environ
    uid = os.getuid()
    for runtime in ((env.get("XDG_RUNTIME_DIR") or "").strip(), "/run/user/%d" % uid):
        with contextlib.suppress(OSError):
            if runtime and os.path.isdir(runtime) and os.stat(runtime).st_uid == uid:
                return pathlib.Path(runtime) / ("%s.lock" % stem)
    return pathlib.Path("/tmp") / ("%s-%d.lock" % (stem, uid))


def open_lock_file(resource: str, path: pathlib.Path) -> int:
    """Open `path` read-write, creating it 0600, without following a symlink; refuse (LockFileRefusedError) a file this user does not own or one a group or others can write. The /tmp fallback name is predictable, so another local user could plant a link there."""
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise LockFileRefusedError(
            resource, path, "%s (a symlink is never followed)" % (exc.strerror or exc)
        ) from exc
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        os.close(fd)
        raise LockFileRefusedError(
            resource,
            path,
            "it must be a regular file owned by uid %d and not group or world writable"
            % os.getuid(),
        )
    return fd


def _iso(epoch: float) -> str:
    return datetime.datetime.fromtimestamp(epoch, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def describe_payload(raw: bytes) -> str:
    """`pid <p>, purpose <x>, session <s>, since <t>` from a lock payload; `holder unknown` when it does not parse."""
    try:
        data = json.loads(raw.decode(errors="replace"))
    except ValueError:
        return "holder unknown"
    if not isinstance(data, dict):
        return "holder unknown"
    return "pid %s, purpose %s, session %s, since %s" % (
        data.get("pid"),
        data.get("purpose") or "-",
        data.get("session") or "-",
        data.get("since"),
    )


def payload_pid(raw: bytes) -> int:
    """The `pid` of a lock payload; 0 when it does not parse."""
    try:
        data = json.loads(raw.decode(errors="replace"))
        pid = int(data.get("pid") or 0) if isinstance(data, dict) else 0
    except (ValueError, TypeError):
        return 0
    return max(pid, 0)


def parent_pid(pid: int) -> int:
    """The parent of `pid` from /proc (Linux) or `ps` (macOS); 0 when unknown."""
    with contextlib.suppress(OSError, ValueError, IndexError):
        stat = pathlib.Path("/proc/%d/stat" % pid).read_text()
        # The command name in field 2 is parenthesised and may hold spaces; the ppid is the second field after it.
        return int(stat.rsplit(")", 1)[1].split()[1])
    with contextlib.suppress(OSError, ValueError, subprocess.SubprocessError):
        out = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
        return int(out.strip() or 0)
    return 0


def ancestors(pid: int | None = None) -> list[int]:
    """The parent chain of `pid` (default this process), nearest first, ending before pid 1."""
    chain: list[int] = []
    current = os.getpid() if pid is None else pid
    for _ in range(64):
        current = parent_pid(current)
        if current <= 1 or current in chain:
            break
        chain.append(current)
    return chain


EXIT_NOT_HELD = 3


def held_by_ancestor(resource: str, environ: Mapping[str, str] | None = None) -> bool:
    """True when `resource` is held right now by this process or one of its ancestors: the lock file cannot be taken and its payload names a PID in the parent chain. A free lock or one held by an unrelated process is False; a lock file that cannot be opened (a symlink, wrong permissions) raises OSError, which the CLI turns into exit 2 so rdc.sh refuses. rdc.sh asks this before wrapping `ops up|down` in the fleet lock, so a re-run under the holder (with any shim between them) enters the hold instead of wrapping again, and no environment variable can claim a hold that does not exist."""
    path = lock_path(resource, environ)
    if not path.exists():
        return False
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return False  # removed between the exists() test and the open: nothing is held
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return payload_pid(os.pread(fd, 4096, 0)) in (os.getpid(), *ancestors())
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def default_session(environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return (env.get("CLAUDE_CODE_SESSION_ID") or "-")[:8]


class ResourceLock:
    """An exclusive flock on one named resource; `acquire` waits at most `wait_s`."""

    def __init__(
        self,
        resource: str,
        *,
        environ: Mapping[str, str] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        say: Callable[[str], None] | None = None,
    ) -> None:
        self.resource = _check_name(resource)
        self.path = lock_path(resource, environ)
        self.environ = os.environ if environ is None else environ
        self.fd: int | None = None
        # True when an ancestor process holds the resource, so this object holds nothing of its own.
        self.nested = False
        self._clock = clock
        self._sleep = sleep
        self._say = (
            say if say is not None else (lambda line: print(line, file=sys.stderr, flush=True))
        )

    def holder(self) -> str:
        """The current payload, read without taking the lock."""
        # O_NONBLOCK: a FIFO planted at the predictable /tmp name would otherwise block this open until a writer appears.
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        except OSError:
            return "holder unknown"
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return "holder unknown"
            return describe_payload(os.pread(fd, 4096, 0))
        except OSError:
            return "holder unknown"
        finally:
            os.close(fd)

    def acquire(
        self,
        purpose: str,
        wait_s: float = DEFAULT_WAIT_S,
        session: str | None = None,
        *,
        nest: bool = True,
    ) -> float:
        """Seconds waited. Raises ResourceBusyError naming the holder when the wait runs out. With `nest` (the default) a resource this process or an ancestor process holds is entered at once, as `nested`; the holding object must outlive a nested one."""
        if self.fd is not None or self.nested:
            raise RuntimeError("resource %s is already held by this lock object" % self.resource)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = open_lock_file(self.resource, self.path)
        started = self._clock()
        announced = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                waited = self._clock() - started
                raw = os.pread(fd, 4096, 0)
                if nest and payload_pid(raw) in (os.getpid(), *ancestors()):
                    os.close(fd)
                    self.nested = True
                    return waited
                holder = describe_payload(raw)
                if waited >= wait_s:
                    os.close(fd)
                    raise ResourceBusyError(self.resource, self.path, holder, waited) from None
                if not announced:
                    self._say(
                        "resource_lock: waiting up to %ds for %s (%s), held by %s"
                        % (int(wait_s), self.resource, self.path, holder)
                    )
                    announced = True
                self._sleep(min(POLL_S, max(0.0, wait_s - waited)))
        self.fd = fd
        os.ftruncate(fd, 0)
        payload = {
            "pid": os.getpid(),
            "session": session if session is not None else default_session(self.environ),
            "purpose": purpose,
            "since": _iso(time.time()),
        }
        os.pwrite(fd, json.dumps(payload).encode(), 0)
        return self._clock() - started

    def release(self) -> None:
        self.nested = False
        if self.fd is None:
            return
        with contextlib.suppress(OSError):
            os.ftruncate(self.fd, 0)
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)
        self.fd = None


@contextlib.contextmanager
def held(
    resource: str,
    *,
    purpose: str,
    wait_s: float = DEFAULT_WAIT_S,
    session: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Iterator[ResourceLock]:
    """Hold `resource` for the body of the `with`; ResourceBusyError when the wait runs out."""
    lock = ResourceLock(resource, environ=environ)
    lock.acquire(purpose, wait_s, session)
    try:
        yield lock
    finally:
        lock.release()


def wait_setting(name: str, raw: str | None) -> float:
    """Seconds from the value `raw` of the environment variable `name`; DEFAULT_WAIT_S when it is unset or blank, WaitSettingError when it is not a finite, non-negative number. Each caller reads its own variable with a literal key, so the python env registry sees the read."""
    raw = (raw or "").strip()
    if not raw:
        return DEFAULT_WAIT_S
    try:
        value = float(raw)
    except ValueError:
        raise WaitSettingError(name, raw) from None
    if not math.isfinite(value) or value < 0:
        raise WaitSettingError(name, raw)
    return value


@contextlib.contextmanager
def bench_held(regions: str | Sequence[str], purpose: str) -> Iterator[list[ResourceLock]]:
    """Hold `bench-<region>` for each region (PLAN-push-decoupling.md D1.6), taken in sorted order so two multi-region holders cannot deadlock. `BENCH_LOCK_WAIT_S` bounds each wait; ResourceBusyError names the holder."""
    names = sorted(
        {bench_resource(r) for r in ([regions] if isinstance(regions, str) else regions)}
    )
    wait_s = wait_setting("BENCH_LOCK_WAIT_S", os.environ.get("BENCH_LOCK_WAIT_S"))
    with contextlib.ExitStack() as stack:
        yield [stack.enter_context(held(name, purpose=purpose, wait_s=wait_s)) for name in names]


def run(resource: str, argv: Sequence[str], *, purpose: str, wait_s: float = DEFAULT_WAIT_S) -> int:
    """Run `argv` under `resource`; the child's exit code, 128+N for a child killed by signal N, EXIT_BUSY when the wait ran out."""
    try:
        lock = ResourceLock(resource)
        lock.acquire(purpose, wait_s)
    except ResourceBusyError as exc:
        print("resource_lock: %s" % exc, file=sys.stderr, flush=True)
        return EXIT_BUSY
    try:
        child = subprocess.Popen(list(argv))
        forwarded = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        previous = {}

        def forward(signum: int, _frame: object) -> None:
            with contextlib.suppress(ProcessLookupError):
                child.send_signal(signum)

        for signum in forwarded:
            previous[signum] = signal.signal(signum, forward)
        try:
            rc = child.wait()
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
        return 128 - rc if rc < 0 else rc
    finally:
        lock.release()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="PYTHONPATH=.ci python3 -m rediacc_ci.core.resource_lock")
    sub = parser.add_subparsers(dest="verb", required=True)
    run_p = sub.add_parser("run", help="run a command while holding a named resource")
    run_p.add_argument("--resource", required=True)
    run_p.add_argument(
        "--wait",
        type=float,
        default=None,
        help="seconds to wait (default %ds, or $RESOURCE_LOCK_WAIT_S)" % DEFAULT_WAIT_S,
    )
    run_p.add_argument("--purpose", default="")
    run_p.add_argument("cmd", nargs=argparse.REMAINDER)
    path_p = sub.add_parser("path", help="print a resource's lock file")
    path_p.add_argument("--resource", required=True)
    holder_p = sub.add_parser("holder", help="print a resource's current holder")
    holder_p.add_argument("--resource", required=True)
    anc_p = sub.add_parser(
        "held-by-ancestor",
        help="exit 0 when this process or an ancestor holds the resource, 3 when not, 2 when the lock cannot be read (a crash exits 1)",
    )
    anc_p.add_argument("--resource", required=True)
    args = parser.parse_args(argv)
    try:
        _check_name(args.resource)
    except ValueError as exc:
        parser.error(str(exc))
    if args.verb == "path":
        print(lock_path(args.resource))
        return 0
    if args.verb == "holder":
        print(ResourceLock(args.resource).holder())
        return 0
    if args.verb == "held-by-ancestor":
        # "Not held" is 3, a code no crash (1) or usage error (2) produces: rdc.sh wraps only on 3 and refuses on anything but 0 or 3, so a failure can neither run ops unlocked nor send it round the re-wrap loop.
        try:
            return 0 if held_by_ancestor(args.resource) else EXIT_NOT_HELD
        except OSError as exc:
            print("resource_lock: held-by-ancestor cannot read the lock: %s" % exc, file=sys.stderr)
            return 2
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        parser.error("run needs a command after --")
    wait_s = args.wait
    if wait_s is None:
        try:
            wait_s = wait_setting("RESOURCE_LOCK_WAIT_S", os.environ.get("RESOURCE_LOCK_WAIT_S"))
        except WaitSettingError as exc:
            parser.error(str(exc))
    return run(args.resource, cmd, purpose=args.purpose or " ".join(cmd)[:120], wait_s=wait_s)


if __name__ == "__main__":
    sys.exit(main())
