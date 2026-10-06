"""How many cores this process may use, and the machine-wide lease that keeps concurrent runs from each assuming every core (agent/plans/PLAN-prepush-full-cpu.md, part 4).

Operator ruling 2026-10-05: no static worker counts in any local or CI lane; every parallel tool sizes itself from the cores actually available at launch.

THE READ SIDE. `granted_cores` is the one answer every parallel tool asks:

1. `CI_RUNNER_CORES`, the cores scripts/ci-runner's scheduler (or this module's `run` and `pytest` verbs) granted it at launch, when set to a positive integer;
2. otherwise the CPUs this process may run on (`os.sched_getaffinity`, which honours a container's or taskset's mask, where `os.cpu_count` would report the whole host).

THE LEASE. A pool of one token per core, shared by every worktree, push clone and session of this user on this machine. A token is the file `<i>.lock` in the lease directory, HELD by `fcntl.flock(LOCK_EX | LOCK_NB)` on an open descriptor. Nothing ever counts files: whether a token is free is asked of the kernel, by trying its lock. A holder that dies by any signal, `kill -9` included, frees its tokens because the kernel drops a flock when the last descriptor on it closes, so a stale lease cannot exist. The sidecar `<i>.json` (pid, command, label, start time) is a label for `status` and nothing more; the sidecar of a free token is stale by definition and is overwritten at the next acquire. Acquisition never blocks inside the kernel (`LOCK_NB`): `--wait` is a poll loop that retries the whole grant, so a waiter never sits on a partial grant another waiter needs. Every scan of the tokens (acquire, `free`, `status`) holds the pool mutex `pool.mutex` for the scan alone, so a probe's momentary hold on a token is never what a concurrent acquirer finds busy.

WHERE THE POOL LIVES, and why it is never `.ci/cache`. `.ci/cache` is per checkout, while the contention is per machine across worktrees and push clones, so a pool there would let two checkouts each take every core. In order:

1. `$REDIACC_CORE_LEASE_DIR`, when set (the tests point it at a temp directory);
2. `$XDG_RUNTIME_DIR/rediacc-cores`, when that directory exists and is this user's;
3. `/run/user/<uid>/rediacc-cores`, when that exists and is this user's: it is what `XDG_RUNTIME_DIR` names on a systemd host, named directly so a process whose environment lost the variable still joins the same pool;
4. `/tmp/rediacc-cores-<uid>`, the literal /tmp and NOT `$TMPDIR`, because runtmp and the test fixtures redirect `TMPDIR` per run, and a pool keyed on it would split into one pool per run, each believing it owns every core.

A lease directory owned by another user is refused (exit 69), never shared: its tokens would be someone else's to forge.

THE POOL SIZE is `$REDIACC_CORE_LEASE_TOKENS` when set to a positive integer (the tests use 4), else `available_cores()`.

RUN REGISTRATION (plan part 4, B11). Counting free tokens tells a run nothing about the other runs: two runs started together both read every token free and the first took them all. So each run also holds a marker, `runs/<pid>-<monotonic_ns>-<hex>.lock` under the lease directory, flock'd for the run's lifetime (`Pool.register`; created O_CREAT|O_EXCL and locked inside the pool mutex, so no counter can see an unlocked new marker and mistake it for a dead one). `Pool.live_runs` probes every marker under the mutex with a fresh open: a lock it can take means the owner is dead, and the marker is unlinked; a held one is live. A run's share of the pool is ceil(total / live_runs); `run` and `pytest` cap their `--max` at it (never below `--min`, never below 1), and the broker reports the count in its `free` reply for the scheduler to do the same. An unusable `runs/` is the same exit 69 as an unusable token directory.

CLI (`python3 .ci/rediacc_ci/core_lease.py <verb> ...`). `--max` takes a positive integer or `all` (the pool size); `--min` defaults to 1 and `--max` to `all`.

  acquire --min M --max N [--wait] [--timeout S] [--label L]
      Takes k tokens, M <= k <= N, as many as are free. Prints `k` and a newline on stdout, flushed, then HOLDS them until its stdin reaches EOF (or it dies), so give it a pipe; `</dev/null` releases at once. Fewer than M free: prints `0`, exit 75 (with `--wait`: polls until M are free, or exit 75 after `--timeout` seconds).
  run --min M --max N [--wait] [--timeout S] [--label L] -- CMD...
      Takes k tokens like `acquire`, then execs CMD with `CI_RUNNER_CORES=k` and `CI_CORE_LEASE_HELD=1` exported and the token descriptors inherited, so the lease lives exactly as long as CMD's process tree holds them. Exit: CMD's own, 75 when short, 127 when CMD cannot be executed.
  pytest --real PYTEST [-- ARGS...]
      The session pytest wrapper's verb (.ci/bootstrap.sh writes the wrapper). With `CI_CORE_LEASE_HELD` set, or for --version/-V/-VV/--help/-h, execs PYTEST untouched. Otherwise reads xdist's `-n` from ARGS and `PYTEST_ADDOPTS` (`-n N` asks for up to N tokens, `-n auto` and `-n logical` for the whole pool, no `-n` or `-n 0` for one), waits for at least one token, rewrites `-n` to the grant k, and execs PYTEST like `run`.
  broker [--label L]
      For a parent process (scripts/ci-runner/lease-client.ts). Registers a run marker at spawn and holds it for its lifetime. JSON lines on stdin, exactly one JSON line answered on stdout per request:
        {"op":"free"}                                   -> {"free":F,"total":T,"held":[ids this broker holds],"runs":R}   (R = live registered runs, this broker's own included, at least 1)
        {"op":"acquire","min":M,"max":N,"label":"g"}    -> {"k":K,"ids":[...]}  (M may be 0: whatever is free, possibly ids []; K is 0 and ids [] when fewer than M were free, and nothing is kept then; "max" may be "all"; "label" is optional)
        {"op":"release","ids":[...]}                    -> {"released":[...],"unknown":[ids this broker did not hold]}
        anything malformed                              -> {"error":"..."}
      Never waits: a short grant is the caller's to hold or retry. Spawn it as `python3 .ci/rediacc_ci/core_lease.py broker` or, with `<root>/.ci` on PYTHONPATH, `python3 -m rediacc_ci.core_lease broker`; both run this CLI. On stdin EOF it releases everything and exits 0; its own death by any signal releases everything too. Tokens are never inherited by anything the parent spawns.
  free
      Prints the number of free tokens, exit 0.
  status [--json]
      The live run count, then one line per held token: its holder, label, age, and `IDLE` when the holder's process tree has used no CPU for 10 minutes (a report, never a kill). Exit 0.
  selftest   (also the no-argument form)
      In-process controls over a temp pool. Exit 0 green, 1 red.

Exit codes for every verb: 0 ok, 2 usage, 69 the lease directory is unusable (the message names the fix), 75 fewer than --min tokens were free (or --wait timed out), 127 the command could not be executed.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import fcntl
import json
import os
import pathlib
import secrets
import shlex
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

ENV = "CI_RUNNER_CORES"
HELD_ENV = "CI_CORE_LEASE_HELD"
DIR_ENV = "REDIACC_CORE_LEASE_DIR"
TOKENS_ENV = "REDIACC_CORE_LEASE_TOKENS"

EXIT_OK = 0
EXIT_RED = 1
EXIT_USAGE = 2
EXIT_UNUSABLE = 69
EXIT_SHORT = 75
EXIT_NOEXEC = 127

# The kernel lock that IS the token. LOCK_NB is load-bearing: a blocking flock on a held token would park an acquirer inside the kernel on ONE token while others sit free (test_core_lease.py plants its removal and the over-grant case must hang to its timeout).
LOCK_FLAGS = fcntl.LOCK_EX | fcntl.LOCK_NB

# The pool mutex: every scan of the tokens (an acquire, a `free` count, a `status`) holds it, so a probe that takes a token's lock for a microsecond can never be what a concurrent acquirer finds busy. Without it a runner polling `free` before each admit pass made a session's `--max 3` over 4 free tokens come back with 2 (test_core_lease.py `test_probes_never_short_a_concurrent_acquire`, and its planted `unguarded-scan`). Held only for the scan, never across a sidecar write or a wait; taken with LOCK_NB and a spin, so a process stopped mid-scan is reported after MUTEX_TIMEOUT_S rather than hanging every caller.
MUTEX_NAME = "pool.mutex"
RUNS_DIR = "runs"
MUTEX_TIMEOUT_S = 10.0
MUTEX_SPIN_S = 0.001

# How long `--wait` sleeps between whole-grant attempts.
WAIT_POLL_SECONDS = 0.2

# A `--wait` grant that came after blocking is topped up until one pause of this length adds nothing. A holder's tokens are freed one descriptor at a time as the kernel tears the process down, so a waiter that wakes mid-teardown sees only some of them (measured 2026-10-06 under load: killing a 3-token holder showed 1 or 2 tokens free to a tight poller in 43 of 100 kills); taking that partial grant would shortchange the waiter for the whole life of its command.
SETTLE_SECONDS = 0.1

# A live holder whose process tree has used no CPU for this long is reported as IDLE by `status`.
IDLE_REPORT_SECONDS = 600

# Info-only pytest flags: they run no tests, so the wrapper never makes them wait for a token. bootstrap.sh's version and plugin probes (`--version`, `-VV`) go through here.
PYTEST_INFO_FLAGS = frozenset({"--version", "-V", "-VV", "--help", "-h"})

# Planted defects for test_core_lease.py, after block_unverified_push.py's DEFECT convention: (text in this file, the defective text). Each must occur exactly once, which the test asserts before planting, so a reworded line cannot silently void its control.
DEFECTS: dict[str, tuple[str, str]] = {
    # A token "held" means a sidecar exists: a holder killed by -9 never removes it, so the pool never refills.
    "sidecar-count": (
        "        try:\n            fcntl.flock(fd, LOCK_FLAGS)\n        except BlockingIOError:\n",
        (
            "        try:\n            if self.sidecar(index).exists():\n"
            "                raise BlockingIOError\n        except BlockingIOError:\n"
        ),
    ),
    # Probes scan without the pool mutex: a `free` count holds a token's lock just as an acquirer tries it.
    "unguarded-scan": (
        "        with self._scan():\n            return sum(",
        "        with contextlib.nullcontext():\n            return sum(",
    ),
    # Run markers are counted as files: a run killed by -9 leaves its marker, so it is counted live forever and the survivors' share stays too small.
    "runs-file-count": (
        "                with contextlib.suppress(OSError):\n                    marker.unlink()\n",
        "                live += 1\n",
    ),
    # A new marker is created and locked outside the pool mutex, with a pause between the two steps: a concurrent count finds the unlocked marker, takes it for a dead run's, unlinks it, and the new run counts 0 for itself.
    "runs-no-mutex": (
        "        with self._scan():\n            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)\n",
        "        with contextlib.nullcontext():\n            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)\n            time.sleep(0.005)\n",
    ),
    # The CLI verbs ignore the share and take whatever is free: first come takes all.
    "runs-no-cap": (
        "    return max(minimum, 1, min(maximum, -(-pool.size // max(1, runs))))\n",
        "    return maximum\n",
    ),
    # A waiter that wakes takes the tokens free at that instant and does not settle: a holder whose tokens are freed one by one leaves it a partial grant.
    "no-settle": (
        "            if got and blocked and len(got) < maximum:\n",
        "            if False:\n",
    ),
    # Acquire without LOCK_NB: the second acquirer blocks in the kernel on the first held token.
    "blocking-flock": (
        "LOCK_FLAGS = fcntl.LOCK_EX | fcntl.LOCK_NB\n",
        "LOCK_FLAGS = fcntl.LOCK_EX\n",
    ),
}


class LeaseError(Exception):
    """The lease directory cannot be used; the message names the fix."""


def available_cores() -> int:
    """The CPUs this process may run on, at least 1."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _positive_int(raw: str | None) -> int | None:
    text = (raw or "").strip()
    if text.isdigit() and int(text) > 0:
        return int(text)
    return None


def granted_cores(environ: Mapping[str, str] | None = None) -> int:
    """The cores granted to this process: the runner's grant when it made one, else every core it may run on."""
    env = os.environ if environ is None else environ
    return _positive_int(env.get(ENV)) or available_cores()


def pool_size(environ: Mapping[str, str] | None = None) -> int:
    """Tokens in the machine-wide pool: $REDIACC_CORE_LEASE_TOKENS, else one per core this process may run on."""
    env = os.environ if environ is None else environ
    return _positive_int(env.get(TOKENS_ENV)) or available_cores()


def _owned_dir(path: str) -> bool:
    try:
        st = os.stat(path)
    except OSError:
        return False
    return os.path.isdir(path) and st.st_uid == os.getuid()


def lease_dir(environ: Mapping[str, str] | None = None) -> pathlib.Path:
    """Where the pool lives; the order and its reasons are in the module docstring."""
    env = os.environ if environ is None else environ
    explicit = (env.get(DIR_ENV) or "").strip()
    if explicit:
        return pathlib.Path(explicit)
    uid = os.getuid()
    for runtime in ((env.get("XDG_RUNTIME_DIR") or "").strip(), "/run/user/%d" % uid):
        if runtime and _owned_dir(runtime):
            return pathlib.Path(runtime) / "rediacc-cores"
    # The literal /tmp on purpose, never $TMPDIR (module docstring, item 4); the owner check in Pool.ensure covers what S108 warns about.
    return pathlib.Path("/tmp") / ("rediacc-cores-%d" % uid)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def pid_namespace() -> str:
    """This process's pid namespace inode, or "0" where /proc does not expose one. A pid recorded in another namespace (the devbox container versus the host, which share a lease directory through a bind mount) names a different process here, so liveness is only judged inside one namespace."""
    try:
        return str(os.stat("/proc/self/ns/pid").st_ino)
    except OSError:
        return "0"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OverflowError, ValueError):
        return False
    return True


def _proc_cpu_table() -> dict[int, tuple[int, int]] | None:
    """pid -> (ppid, utime+stime ticks) for every process, or None where /proc has no stat files."""
    table: dict[int, tuple[int, int]] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return None
    for name in entries:
        if not name.isdigit():
            continue
        try:
            raw = pathlib.Path("/proc", name, "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # comm may hold spaces and parentheses, so split after its LAST ')'.
        fields = raw[raw.rfind(")") + 2 :].split()
        try:
            table[int(name)] = (int(fields[1]), int(fields[11]) + int(fields[12]))
        except (IndexError, ValueError):
            continue
    return table or None


def tree_cpu_ticks(pid: int) -> int | None:
    """CPU ticks used by `pid` and every live descendant, or None where that cannot be read."""
    table = _proc_cpu_table()
    if table is None or pid not in table:
        return None
    children: dict[int, list[int]] = {}
    for child, (ppid, _ticks) in table.items():
        children.setdefault(ppid, []).append(child)
    total, stack, seen = 0, [pid], set()
    while stack:
        cur = stack.pop()
        if cur in seen or cur not in table:
            continue
        seen.add(cur)
        total += table[cur][1]
        stack.extend(children.get(cur, ()))
    return total


@dataclass(frozen=True)
class Run:
    """One registered run: its marker file and the descriptor whose flock says the run is alive."""

    path: pathlib.Path
    fd: int

    def close(self) -> None:
        """Release the marker's lock; the file is left for the next `live_runs` to sweep."""
        with contextlib.suppress(OSError):
            os.close(self.fd)


@dataclass(frozen=True)
class Token:
    """One held token: its index and the descriptor whose flock holds it."""

    index: int
    fd: int


def _write_json_atomic(path: pathlib.Path, data: Mapping[str, object]) -> None:
    tmp = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    try:
        tmp.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink()


class Pool:
    """The token pool under one directory. Held means flock'd by someone; nothing here counts files."""

    def __init__(self, directory: pathlib.Path, size: int) -> None:
        if size < 1:
            raise ValueError("a pool needs at least one token, got %d" % size)
        self.directory = directory
        self.size = size

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Pool:
        """The machine-wide pool this environment names."""
        pool = cls(lease_dir(environ), pool_size(environ))
        pool.ensure()
        return pool

    def ensure(self) -> None:
        """Create the directory (0700) and refuse one this user does not own."""
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            st = self.directory.stat()
        except OSError as exc:
            msg = (
                "cannot create the core lease directory %s (%s); set %s to a directory this user owns"
                % (
                    self.directory,
                    exc,
                    DIR_ENV,
                )
            )
            raise LeaseError(msg) from exc
        if st.st_uid != os.getuid():
            msg = (
                "the core lease directory %s is owned by uid %d, not this user (%d); set %s to a directory this user owns"
                % (
                    self.directory,
                    st.st_uid,
                    os.getuid(),
                    DIR_ENV,
                )
            )
            raise LeaseError(msg)
        self._ensure_runs()

    @property
    def runs_dir(self) -> pathlib.Path:
        """Where the run markers live."""
        return self.directory / RUNS_DIR

    def _ensure_runs(self) -> None:
        try:
            self.runs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            usable = self.runs_dir.is_dir() and os.access(self.runs_dir, os.W_OK | os.X_OK)
        except OSError as exc:
            msg = (
                "cannot create the run marker directory %s (%s); set %s to a directory this user owns"
                % (
                    self.runs_dir,
                    exc,
                    DIR_ENV,
                )
            )
            raise LeaseError(msg) from exc
        if not usable:
            msg = (
                "the run marker directory %s is not a usable directory; remove it or set %s to a directory this user owns"
                % (
                    self.runs_dir,
                    DIR_ENV,
                )
            )
            raise LeaseError(msg)

    def lock_path(self, index: int) -> pathlib.Path:
        """The file whose flock is token `index`."""
        return self.directory / ("%d.lock" % index)

    def sidecar(self, index: int) -> pathlib.Path:
        """The label of token `index`: who took it last. Stale whenever the token is free."""
        return self.directory / ("%d.json" % index)

    @contextlib.contextmanager
    def _scan(self) -> Iterator[None]:
        """Hold the pool mutex for one scan of the tokens. Never nest: a second open of the mutex in this process conflicts with the first (flock is per open file description)."""
        fd = os.open(self.directory / MUTEX_NAME, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            deadline = time.monotonic() + MUTEX_TIMEOUT_S
            while True:
                try:
                    fcntl.flock(fd, LOCK_FLAGS)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        msg = (
                            "the pool mutex %s has been held for %ds; a process stopped mid-scan holds it (find it with `fuser %s`)"
                            % (
                                self.directory / MUTEX_NAME,
                                MUTEX_TIMEOUT_S,
                                self.directory / MUTEX_NAME,
                            )
                        )
                        raise LeaseError(msg) from None
                    time.sleep(MUTEX_SPIN_S)
            yield
        finally:
            os.close(fd)

    def register(self, label: str = "") -> Run:
        """Register this run: a new marker, created and flock'd inside the pool mutex, held until the handle closes or the process dies."""
        self._ensure_runs()
        name = "%d-%d-%s.lock" % (os.getpid(), time.monotonic_ns(), secrets.token_hex(4))
        path = self.runs_dir / name
        with self._scan():
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
            try:
                fcntl.flock(fd, LOCK_FLAGS)
            except BaseException:
                os.close(fd)
                raise
        with contextlib.suppress(OSError):
            os.write(fd, (json.dumps({"pid": os.getpid(), "label": label}) + "\n").encode())
        return Run(path, fd)

    def live_runs(self) -> int:
        """Registered runs alive right now. Under the pool mutex each marker is probed with a fresh open (flock is per open file description, so a marker this process holds reads as held): a lock that can be taken means its owner is dead, and the marker is unlinked."""
        self._ensure_runs()
        live = 0
        with self._scan():
            for marker in sorted(self.runs_dir.glob("*.lock")):
                try:
                    fd = os.open(marker, os.O_RDWR | os.O_CLOEXEC)
                except OSError:
                    continue
                try:
                    fcntl.flock(fd, LOCK_FLAGS)
                except BlockingIOError:
                    live += 1
                    continue
                finally:
                    os.close(fd)
                with contextlib.suppress(OSError):
                    marker.unlink()
        return live

    def _claim(self, index: int) -> int | None:
        """Token `index`'s locked descriptor, or None when someone holds it. Never blocks. Callers hold `_scan()`."""
        fd = os.open(self.lock_path(index), os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(fd, LOCK_FLAGS)
        except BlockingIOError:
            os.close(fd)
            return None
        except BaseException:
            os.close(fd)
            raise
        return fd

    def try_acquire(self, minimum: int, maximum: int, label: str = "") -> list[Token]:
        """Up to `maximum` free tokens, or none at all when fewer than `minimum` are free."""
        held: list[Token] = []
        with self._scan():
            for index in range(self.size):
                if len(held) >= maximum:
                    break
                fd = self._claim(index)
                if fd is not None:
                    held.append(Token(index, fd))
            if len(held) < minimum:
                self.release(held)
                return []
        for token in held:
            self._label(token.index, label)
        return held

    def acquire(
        self,
        minimum: int,
        maximum: int,
        *,
        wait: bool = False,
        timeout: float | None = None,
        label: str = "",
        on_wait: Callable[[], None] | None = None,
    ) -> list[Token]:
        """`try_acquire`, and with `wait` retried whole until it succeeds or `timeout` seconds pass."""
        deadline = None if timeout is None else time.monotonic() + timeout
        told = False
        blocked = False
        while True:
            got = self.try_acquire(minimum, maximum, label)
            if got and blocked and len(got) < maximum:
                got = self._settle(got, maximum, label)
            if got or not wait:
                return got
            if deadline is not None and time.monotonic() >= deadline:
                return []
            # Settling keys on having BLOCKED, not on having announced it: a caller with no on_wait blocks just the same.
            blocked = True
            if not told and on_wait is not None:
                on_wait()
                told = True
            time.sleep(WAIT_POLL_SECONDS)

    def _settle(self, held: list[Token], maximum: int, label: str) -> list[Token]:
        """`held`, plus whatever else frees up while the grant settles: a pause, then a top-up, until a pause adds nothing or `maximum` is reached."""
        while len(held) < maximum:
            time.sleep(SETTLE_SECONDS)
            more = self.try_acquire(0, maximum - len(held), label)
            if not more:
                break
            held = [*held, *more]
        return held

    @staticmethod
    def release(tokens: Sequence[Token]) -> None:
        """Close the descriptors; the kernel frees each flock with its last descriptor."""
        for token in tokens:
            with contextlib.suppress(OSError):
                os.close(token.fd)

    def _is_free(self, index: int) -> bool:
        """Ask the kernel, by trying the lock and letting go at once. Callers hold `_scan()`."""
        fd = self._claim(index)
        if fd is None:
            return False
        os.close(fd)
        return True

    def free_count(self) -> int:
        """Tokens free right now, asked of the kernel under the pool mutex."""
        with self._scan():
            return sum(1 for index in range(self.size) if self._is_free(index))

    def held_indices(self) -> list[int]:
        """The tokens someone holds right now, asked of the kernel under the pool mutex."""
        with self._scan():
            return [index for index in range(self.size) if not self._is_free(index)]

    def _label(self, index: int, label: str) -> None:
        # No CPU reading here: one costs a scan of every /proc entry, and an acquire labels every token it takes. `status` sets the CPU mark the first time it sees a holder.
        pid = os.getpid()
        _write_json_atomic(
            self.sidecar(index),
            {
                "pid": pid,
                "ppid": os.getppid(),
                "pidns": pid_namespace(),
                "label": label,
                "cmd": " ".join(shlex.quote(a) for a in sys.argv),
                "start": _now_iso(),
                "start_epoch": time.time(),
            },
        )

    def read_label(self, index: int) -> dict[str, object]:
        """Token `index`'s sidecar, or {} when it is missing or unreadable."""
        try:
            data = json.loads(self.sidecar(index).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def status(self) -> dict[str, object]:
        """Every held token with its label and liveness. Refreshes each live holder's CPU mark in its sidecar so IDLE means "no CPU since the mark", the mark moving whenever CPU was used."""
        now = time.time()
        held: list[dict[str, object]] = []
        for index in self.held_indices():
            label = self.read_label(index)
            pid_raw = label.get("pid")
            pid = pid_raw if isinstance(pid_raw, int) else None
            row: dict[str, object] = {"index": index, **label}
            foreign = label.get("pidns", pid_namespace()) != pid_namespace()
            row["foreign_pidns"] = foreign
            row["holder_alive"] = None if foreign else pid is not None and _alive(pid)
            ticks = tree_cpu_ticks(pid) if pid is not None and row["holder_alive"] else None
            row["idle_seconds"] = None
            if ticks is not None:
                seen_at = label.get("cpu_seen_at")
                if label.get("cpu_ticks") != ticks or not isinstance(seen_at, (int, float)):
                    _write_json_atomic(
                        self.sidecar(index), {**label, "cpu_ticks": ticks, "cpu_seen_at": now}
                    )
                    row["idle_seconds"] = 0.0
                else:
                    row["idle_seconds"] = round(now - seen_at, 1)
            idle = row["idle_seconds"]
            row["idle"] = isinstance(idle, float) and idle >= IDLE_REPORT_SECONDS
            held.append(row)
        return {
            "dir": str(self.directory),
            "total": self.size,
            "free": self.size - len(held),
            "runs": self.live_runs(),
            "held": held,
        }


# --------------------------------------------------------------------------- pytest -n


def _n_options(args: Sequence[str]) -> Iterator[tuple[int, int, str]]:
    """(start, stop, value) of every xdist `-n` in `args`, in the spellings argparse accepts: `-n V`, `-nV`, `-n=V`, `--numprocesses V`, `--numprocesses=V`. Stops at `--`."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return
        if arg in {"-n", "--numprocesses"}:
            if i + 1 < len(args):
                yield i, i + 2, args[i + 1]
            i += 2
            continue
        if arg.startswith("--numprocesses="):
            yield i, i + 1, arg.split("=", 1)[1]
        elif arg.startswith("-n") and not arg.startswith("--") and len(arg) > 2:
            yield i, i + 1, arg[2:].removeprefix("=")
        i += 1


def requested_workers(args: Sequence[str], total: int) -> int | None:
    """Tokens an xdist request asks for at most: N for `-n N`, `total` for auto/logical, None for a serial run (no `-n`, or `-n 0`). The last `-n` wins, as in argparse."""
    found = list(_n_options(args))
    if not found:
        return None
    value = found[-1][2].strip()
    if value in {"auto", "logical"}:
        return total
    if value.isdigit():
        return int(value) or None
    return None


def rewrite_workers(args: Sequence[str], grant: int) -> list[str]:
    """`args` with every `-n` replaced by `-n <grant>`."""
    out: list[str] = []
    pos = 0
    for start, stop, _value in _n_options(args):
        out.extend(args[pos:start])
        out.extend(["-n", str(grant)])
        pos = stop
    out.extend(args[pos:])
    return out


# --------------------------------------------------------------------------- CLI


def _max_arg(raw: str) -> int | str:
    if raw == "all":
        return raw
    value = _positive_int(raw)
    if value is None:
        msg = "expected a positive integer or 'all', got %r" % raw
        raise argparse.ArgumentTypeError(msg)
    return value


def _bounds(pool: Pool, minimum: int, maximum: int | str, floor: int = 1) -> tuple[int, int]:
    top = pool.size if maximum == "all" else min(int(maximum), pool.size)
    if minimum < floor:
        msg = "--min must be at least %d, got %d" % (floor, minimum)
        raise ValueError(msg)
    if minimum > pool.size:
        msg = "--min %d exceeds the pool of %d token(s) in %s" % (
            minimum,
            pool.size,
            pool.directory,
        )
        raise ValueError(msg)
    if top < minimum:
        msg = "--max %s is below --min %d" % (maximum, minimum)
        raise ValueError(msg)
    return minimum, top


def _share_cap(pool: Pool, minimum: int, maximum: int, runs: int) -> int:
    """`maximum` capped at this run's share of the pool, ceil(total / runs), and never below `minimum` or 1."""
    return max(minimum, 1, min(maximum, -(-pool.size // max(1, runs))))


def _err(message: str) -> None:
    print("core_lease: %s" % message, file=sys.stderr, flush=True)


def _waiting_notice(pool: Pool, minimum: int) -> Callable[[], None]:
    def notice() -> None:
        _err(
            "fewer than %d of %d core token(s) are free; waiting (who holds them: python3 %s status)"
            % (minimum, pool.size, pathlib.Path(__file__).resolve())
        )

    return notice


def _exec_holding(
    tokens: Sequence[Token],
    cmd: Sequence[str],
    extra_env: Mapping[str, str],
    run: Run | None = None,
) -> int:
    env = dict(os.environ)
    env.update(extra_env)
    env[ENV] = str(len(tokens))
    env[HELD_ENV] = "1"
    for token in tokens:
        os.set_inheritable(token.fd, True)
    if run is not None:
        # The marker's lock lives as long as the command's process tree, like the tokens.
        os.set_inheritable(run.fd, True)
    try:
        os.execvpe(cmd[0], list(cmd), env)  # noqa: S606 -- the whole point of `run`: become the command, keeping the lock descriptors
    except OSError as exc:
        _err("cannot execute %s: %s" % (cmd[0], exc))
        Pool.release(tokens)
        if run is not None:
            run.close()
        return EXIT_NOEXEC
    return EXIT_NOEXEC  # pragma: no cover -- execvpe returns only by raising


def _cmd_acquire(pool: Pool, ns: argparse.Namespace) -> int:
    minimum, maximum = _bounds(pool, ns.min, ns.max)
    tokens = pool.acquire(
        minimum,
        maximum,
        wait=ns.wait,
        timeout=ns.timeout,
        label=ns.label,
        on_wait=_waiting_notice(pool, minimum),
    )
    print(len(tokens), flush=True)
    if not tokens:
        return EXIT_SHORT
    try:
        while sys.stdin.buffer.read(65536):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        pool.release(tokens)
    return EXIT_OK


def _cmd_run(pool: Pool, ns: argparse.Namespace) -> int:
    cmd = list(ns.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        _err("run needs a command after --")
        return EXIT_USAGE
    minimum, maximum = _bounds(pool, ns.min, ns.max)
    label = ns.label or " ".join(cmd)
    marker = pool.register(label)
    maximum = _share_cap(pool, minimum, maximum, pool.live_runs())
    tokens = pool.acquire(
        minimum,
        maximum,
        wait=ns.wait,
        timeout=ns.timeout,
        label=label,
        on_wait=_waiting_notice(pool, minimum),
    )
    if not tokens:
        marker.close()
        _err("fewer than %d core token(s) free in %s" % (minimum, pool.directory))
        return EXIT_SHORT
    return _exec_holding(tokens, cmd, {}, marker)


def _cmd_pytest(ns: argparse.Namespace) -> int:
    real = ns.real
    args = list(ns.args)
    if args and args[0] == "--":
        args = args[1:]
    if not (os.path.isfile(real) and os.access(real, os.X_OK)):
        _err(
            "the real pytest %s is missing or not executable; run `bash .ci/bootstrap.sh` to reinstall it"
            % real
        )
        return EXIT_NOEXEC
    if os.environ.get(HELD_ENV) or PYTEST_INFO_FLAGS.intersection(args):
        try:
            os.execv(real, [real, *args])  # noqa: S606 -- a pass-through wrapper
        except OSError as exc:
            _err("cannot execute %s: %s" % (real, exc))
            return EXIT_NOEXEC
    pool = Pool.from_env()
    addopts = shlex.split(os.environ.get("PYTEST_ADDOPTS", ""))
    want = requested_workers([*addopts, *args], pool.size)
    marker = pool.register("pytest " + " ".join(args))
    tokens = pool.acquire(
        1,
        _share_cap(pool, 1, min(want or 1, pool.size), pool.live_runs()),
        wait=True,
        label="pytest " + " ".join(args),
        on_wait=_waiting_notice(pool, 1),
    )
    extra: dict[str, str] = {}
    if want is not None:
        args = rewrite_workers(args, len(tokens))
        if list(_n_options(addopts)):
            extra["PYTEST_ADDOPTS"] = shlex.join(rewrite_workers(addopts, len(tokens)))
    return _exec_holding(tokens, [real, *args], extra, marker)


def _cmd_broker(pool: Pool, ns: argparse.Namespace) -> int:
    held: dict[int, Token] = {}
    marker = pool.register(ns.label or "broker")

    def answer(req: object) -> dict[str, object]:
        if not isinstance(req, dict):
            return {"error": "a request is a JSON object"}
        op = req.get("op")
        if op == "free":
            return {
                "free": pool.free_count(),
                "total": pool.size,
                "held": sorted(held),
                "runs": max(1, pool.live_runs()),
            }
        if op == "acquire":
            minimum, maximum = req.get("min", 1), req.get("max", "all")
            if (
                isinstance(minimum, bool)
                or not isinstance(minimum, int)
                or not (
                    maximum == "all" or (isinstance(maximum, int) and not isinstance(maximum, bool))
                )
            ):
                return {"error": "acquire needs integer min and integer-or-'all' max"}
            try:
                # min 0 is the runner's "whatever is free, possibly nothing"; the CLI verbs keep a floor of 1.
                lo, hi = _bounds(pool, minimum, maximum, floor=0)
            except ValueError as exc:
                return {"error": str(exc)}
            label = req.get("label")
            got = pool.try_acquire(lo, hi, label if isinstance(label, str) else ns.label)
            held.update((t.index, t) for t in got)
            return {"k": len(got), "ids": [t.index for t in got]}
        if op == "release":
            ids = req.get("ids")
            if not isinstance(ids, list):
                return {"error": "release needs a list of ids"}
            released, unknown = [], []
            for tid in ids:
                token = held.pop(tid, None) if isinstance(tid, int) else None
                if token is None:
                    unknown.append(tid)
                else:
                    pool.release([token])
                    released.append(tid)
            return {"released": released, "unknown": unknown}
        return {"error": "unknown op %r" % (op,)}

    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                reply = answer(json.loads(line))
            except LeaseError as exc:
                reply = {"error": str(exc)}
            except ValueError as exc:
                reply = {"error": "not JSON: %s" % exc}
            try:
                sys.stdout.write(json.dumps(reply, sort_keys=True) + "\n")
                sys.stdout.flush()
            except BrokenPipeError:
                break
    except KeyboardInterrupt:
        pass
    finally:
        pool.release(list(held.values()))
        marker.close()
    return EXIT_OK


def _cmd_status(pool: Pool, ns: argparse.Namespace) -> int:
    report = pool.status()
    if ns.json:
        print(json.dumps(report, sort_keys=True))
        return EXIT_OK
    held = report["held"]
    assert isinstance(held, list)  # noqa: S101 -- narrowing for the type checker
    print(
        "core lease %s: %s of %s token(s) free, %s live run(s)"
        % (report["dir"], report["free"], report["total"], report["runs"])
    )
    for row in held:
        who = "pid %s" % row.get("pid", "?")
        if row.get("foreign_pidns"):
            who += " (in another pid namespace, host or container; liveness unknown from here)"
        elif not row.get("holder_alive"):
            who += " (gone; a process that inherited its descriptor still holds it)"
        flag = "  IDLE %ss" % row["idle_seconds"] if row.get("idle") else ""
        print(
            "  token %s  %s  since %s  %s%s"
            % (row["index"], who, row.get("start", "?"), row.get("label", ""), flag)
        )
    return EXIT_OK


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core_lease.py", description="The machine-wide core lease."
    )
    sub = parser.add_subparsers(dest="verb")

    def grant_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--min", type=int, default=1)
        p.add_argument("--max", type=_max_arg, default="all")
        p.add_argument("--wait", action="store_true")
        p.add_argument("--timeout", type=float, default=None)
        p.add_argument("--label", default="")

    grant_args(sub.add_parser("acquire"))
    run = sub.add_parser("run")
    grant_args(run)
    run.add_argument("cmd", nargs=argparse.REMAINDER)
    pyt = sub.add_parser("pytest")
    pyt.add_argument("--real", required=True)
    pyt.add_argument("args", nargs=argparse.REMAINDER)
    broker = sub.add_parser("broker")
    broker.add_argument("--label", default="")
    sub.add_parser("free")
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    sub.add_parser("selftest")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """The CLI; exit codes in the module docstring."""
    parser = _parser()
    try:
        ns = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    if ns.verb in {None, "selftest"}:
        return selftest()
    try:
        if ns.verb == "pytest":
            return _cmd_pytest(ns)
        pool = Pool.from_env()
        handlers: dict[str, Callable[[Pool, argparse.Namespace], int]] = {
            "acquire": _cmd_acquire,
            "run": _cmd_run,
            "broker": _cmd_broker,
            "status": _cmd_status,
        }
        if ns.verb == "free":
            print(pool.free_count())
            return EXIT_OK
        return handlers[ns.verb](pool, ns)
    except LeaseError as exc:
        _err(str(exc))
        return EXIT_UNUSABLE
    except ValueError as exc:
        _err(str(exc))
        return EXIT_USAGE


# --------------------------------------------------------------------------- selftest


def selftest() -> int:
    """Controls first, both directions: a grant is honoured and a bad one falls back to the real count; the pool grants what is free and no more, frees on release, and refuses a short grant whole."""
    real = available_cores()
    checks: list[tuple[str, bool]] = [
        ("a positive grant is honoured", granted_cores({ENV: "5"}) == 5),
        ("no grant reads the real core count", granted_cores({}) == real),
        ("a zero grant is not a grant", granted_cores({ENV: "0"}) == real),
        ("a malformed grant is not a grant", granted_cores({ENV: "eight"}) == real),
        ("the real count is at least one core", real >= 1),
        ("an explicit lease dir wins", lease_dir({DIR_ENV: "/x/y"}) == pathlib.Path("/x/y")),
        ("-n 6 asks for 6", requested_workers(["-q", "-n", "6"], 24) == 6),
        ("-n auto asks for the pool", requested_workers(["-nauto"], 24) == 24),
        (
            "--numprocesses=logical asks for the pool",
            requested_workers(["--numprocesses=logical"], 9) == 9,
        ),
        ("no -n is serial", requested_workers(["-q", "x.py"], 24) is None),
        ("-n 0 is serial", requested_workers(["-n", "0"], 24) is None),
        (
            "an -n after -- is a test argument, not ours",
            requested_workers(["--", "-n", "4"], 24) is None,
        ),
        (
            "-n is rewritten to the grant",
            rewrite_workers(["-q", "-n=8", "t.py"], 3) == ["-q", "-n", "3", "t.py"],
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="core-lease-selftest-") as tmp:
        pool = Pool(pathlib.Path(tmp) / "pool", 4)
        pool.ensure()
        first = pool.try_acquire(1, 3)
        second = pool.try_acquire(1, 3)
        checks.append(("first grant of max 3 over 4 is 3", len(first) == 3))
        checks.append(("second grant gets the 1 left", len(second) == 1))
        checks.append(("an empty pool refuses min 1 whole", pool.try_acquire(1, 2) == []))
        checks.append(
            ("held tokens leave sidecars, and sidecars do not free them", pool.free_count() == 0)
        )
        pool.release(first)
        checks.append(("release frees exactly what it held", pool.free_count() == 3))
        checks.append(
            ("a short grant takes nothing", pool.try_acquire(4, 4) == [] and pool.free_count() == 3)
        )
        pool.release(second)
        checks.append(("everything released, everything free", pool.free_count() == 4))
    for label, ok in checks:
        print("  %s  %s" % ("PASS" if ok else "FAIL", label))
    bad = [label for label, ok in checks if not ok]
    print("core_lease selftest: %d check(s), %d failed" % (len(checks), len(bad)))
    return EXIT_RED if bad else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
