"""Which xdist group a test module belongs in, DERIVED and never hand-listed.

WHAT A GROUP MEANS, because the name suggests the opposite of what it does. Under `--dist loadgroup`, every item carrying `@pytest.mark.xdist_group(<name>)` is sent to the SAME worker as every other item with that name. Items with no group distribute freely. So a group is not a grouping for convenience: it is a SERIALISATION, and the only reason to ask for one is that two tests
share a resource the scheduler cannot see.

WITHOUT `--dist loadgroup` THE MARKER DOES NOTHING AT ALL. That is what makes it safe to land the derivation before the `-n` that uses it: a serial run collects and passes exactly as it did before, and the markers sit there inert.

--------------------------------------------------------------------------
THE DERIVATION, AND WHY IT YIELDS NOTHING TODAY
--------------------------------------------------------------------------
`.ci/rediacc_ci/tests/gates/test_gate_*.py` modules each declare a `BASH_TWIN`, and `test_twin_parity.py` RUNS that twin against the real tree on every pytest run. A twin that writes or scans the real tree therefore makes `check:ci-pytest` a participant in the battery's isolation contract; two such twins running in two workers at once is the `cp: cannot stat` flake nobody can
reproduce.

Which twins those are is already recorded, and this reads that record rather than becoming a second copy: `scripts/ci-runner/gates.lock.json`, via `classify_from_lock` below, under the `mutex` (exclusive) and `reads` (shared) claims. This is where the contract BELONGS. The reader lived in the bash battery runner `battery.py` until that runner was retired with the last `.ci/scripts/test/gates/test-*.sh` (2026-10-09); this module was its only remaining caller, so it moved here.

THERE WAS A SECOND SOURCE AND IT IS GONE, WHICH IS A NARROWING RATHER THAN A LOSS. Until the shell battery runner was retired this also unioned in the `*_FALLBACK` arrays parsed out of `.ci/scripts/test/run-all.sh`, the hand-maintained knowledge that predated the lock declarations. The union was retired ON A MEASUREMENT, not on a hope: with the lock alone and with both
sources the answer was the same 27 names, and the runner-only set was EMPTY -- the arrays had nothing left to contribute because every name in them had landed in the lock. `battery.py`, which replaced that runner, carried no such array on purpose: a hand list beside the lock is the duplicated definition the whole port removes.

MEASURED 2026-09-07 AND STATED SO NOBODY CALLS IT A BUG: 29 of 29 ported modules resolve, and ZERO of them are in `mutex | reads`. **The derivation returns no groups today.** That is the correct answer and not a broken reader, and there is deliberately NO "at least one group must exist" floor here: such a floor would be red on the day it was written and would be suppressed within
the week. The anti-vacuity claim that IS available is one directory up -- `real_tree_twins` must not return an EMPTY SET, because an empty one would make `test_no_ported_twin_is_a_real_tree_writer_or_scanner` admit every twin including the four that rewrite tracked files. `test_xdist_groups.py` asserts that, and `test_twin_parity.py` already refuses on it at runtime.

Note also which direction an empty derivation errs in. It was tempting to read "no groups" as "no parallelism"; the opposite is true. Ungrouped items are the freely distributable ones, so a derivation that returns nothing produces MAXIMUM spread. The failure it could hide is a real-tree twin going undeclared in BOTH sources, which is a defect in the declarations rather than in this
file.

--------------------------------------------------------------------------
ONE GROUP FOR ALL REAL-TREE TWINS, NOT ONE PER CLAIM
--------------------------------------------------------------------------
Splitting `mutex` and `reads` into two group names would look more precise and would be WRONG, because two different groups may run concurrently on two different workers. A reader overlapping a writer is exactly the collision being prevented, so the two claims must share one name. `loadgroup` gives no finer-grained instrument than "same worker", and this uses the whole of it.

--------------------------------------------------------------------------
THE ESCAPE HATCH, AND WHY IT IS FOR GENUINE SHARING ONLY
--------------------------------------------------------------------------
A module may set `XDIST_GROUP = "<name>"` to declare a shared resource no registry knows about. `XDIST_GROUP` takes precedence over the lock join, so a module can name its own resource without having to also be a real-tree twin.

A GROUP IS A SERIAL CHAIN, so it is the last resort, not the first (agent/plans/PLAN-prepush-full-cpu.md, operator ruling 2026-10-05: no static worker counts, wall close to the critical path). Every group pins its members to one worker, and on 2026-10-03 the five largest groups were the floor of check:ci-pytest at any core count. Before declaring one, isolate the resource per worker:

  * THE HOST'S PORT SPACE. `worker_port_range()` below hands each xdist worker a disjoint slice of a range, sized from the worker count at startup, and `free_port_in_range()` draws a free port inside it. The `ports` group (`test_core_ports.py`, `test_testrun_start_account.py`, `test_testrun_account_e2e.py`) was deleted for this: `find_consecutive_free_ports(n, 20000, 30000)` returns the FIRST free run, so two workers asking at once both got 20000, and an ephemeral `bind(0)` released before the server bound it could be drawn twice. Disjoint slices cannot collide.
  * THE REAL TREE. The real-tree group has NO declared member since 2026-10-05: every test that planted into the tracked tree plants into a copy, and `check:ci-pool-writer-safety` reds on a new declaration. The derivation from the lock still applies to a ported twin whose lock entry claims `tree:` (a reader such as `test_gate_runner_advice.py`), which is a group of one.

What remains in a group is a resource that is machine-wide by construction and cannot be sliced from the test side (a driver that pins constant ports or a fixed tmp path in a transcript, a docker daemon); each such module says so where it declares it.
"""

import fcntl
import json
import os
import pathlib
import secrets
import socket
import time

from rediacc_ci import core_lease, paths

# The source, as path PARTS rather than a joined string, so a component is greppable on its own and the separator is the platform's.
LOCK_SUBDIR = ("scripts", "ci-runner", "gates.lock.json")

# The one name every real-tree twin shares. A single string constant, because two spellings of it would silently create two groups that can run concurrently -- which is the failure the section above argues against.
REAL_TREE_GROUP = "real-tree"

# The module attribute a test file sets to name a resource no registry knows.
GROUP_ATTR = "XDIST_GROUP"

# The attribute that makes a module a ported gate test with a bash twin.
TWIN_ATTR = "BASH_TWIN"


def lock_path(root: pathlib.Path | None = None) -> pathlib.Path:
    """`<root>/scripts/ci-runner/gates.lock.json`."""
    return paths.from_root(*LOCK_SUBDIR, root=root)


def classify_from_lock(lock: pathlib.Path, claim: str) -> set[str]:
    """Basenames of the implementing file (`leaves[0]`) of every lock entry declaring a `tree:` resource under `claim` (`mutex` for exclusive, `reads` for shared).

    Returns an EMPTY SET when the lock is unreadable or declares nothing, and the caller decides what that means -- "no declarations yet" and "the lock is broken" must not silently become the same thing as "nothing needs isolating".

    THE IDENTITY IS `leaves[0]`, NEVER `run`. This used to match a `run` naming a `.ci/scripts/test/gates/*.sh` file first, back when every isolation-declaring entry was one of those bash files and `run` WAS the path. That directory holds no test since 2026-10-09, so the `run` branch could only ever match nothing, and it was removed with the battery rather than kept as a path that cannot fire. An entry with no `leaves` names no file and contributes nothing.
    """
    try:
        with lock.open(encoding="utf-8") as handle:
            entries = json.load(handle)
    except (OSError, ValueError):
        return set()
    if not isinstance(entries, list):
        return set()
    found = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        claimed = entry.get(claim)
        if not isinstance(claimed, list):
            continue
        if not any(isinstance(r, str) and r.startswith("tree:") for r in claimed):
            continue
        leaves = entry.get("leaves")
        if isinstance(leaves, list) and leaves and isinstance(leaves[0], str):
            found.add(os.path.basename(leaves[0]))
    return found


def real_tree_twins(lock: pathlib.Path) -> set[str]:
    """Gate-test basenames that touch the REAL tree while they run.

    MOVED HERE FROM `test_twin_parity.real_tree_tests`, which now calls this, so the scheduler's idea of what needs isolating and the parity test's idea of what may be driven cannot drift apart. Two copies of this answer would be two answers to one question, and the expensive half of that is that both would look right.

    `lock` is a PARAMETER rather than a module constant so the controls can drive both directions on fixture files. That is the whole reason the signature takes it.

    An unreadable lock contributes NOTHING rather than raising, which is `classify_from_lock`'s documented behaviour and is the caller's decision to interpret: "nothing is declared yet" and "the lock is broken" must not silently become "nothing needs isolating". THAT INTERPRETATION IS NOW THE WHOLE ANSWER, where it used to be one half of a union: a broken lock empties
    this set, so the anti-vacuity refusal on the total -- which lives with the callers, in `test_xdist_groups.py` and at runtime in `test_twin_parity.py` -- is the only thing standing between a damaged lock and a parity run that admits every twin including the ones that rewrite tracked files. That refusal is load-bearing rather than decorative.
    """
    return classify_from_lock(lock, "mutex") | classify_from_lock(lock, "reads")


def group_for(module: object, unsafe: set[str] | None = None) -> str | None:
    """The xdist group `module`'s tests belong in, or None to distribute freely.

    Takes the imported MODULE and not its path, because both inputs it reads are declarations in the module's own namespace: a name in a file is a guess, an attribute on the module is a statement.

    `unsafe` defaults to the real derivation, and the conftest passes it in explicitly so the lock is read once per session rather than once per item across roughly nine thousand of them.
    """
    explicit = getattr(module, GROUP_ATTR, None)
    if isinstance(explicit, str) and explicit:
        return explicit
    twin = getattr(module, TWIN_ATTR, None)
    if isinstance(twin, str) and twin:
        known = real_tree_twins(lock_path()) if unsafe is None else unsafe
        if os.path.basename(twin) in known:
            return REAL_TREE_GROUP
    return None


# --------------------------------------------------------------------------- Per-worker port slices ---------------------------------------------------------------------------

#: The range the slices are cut from: below Linux's default ephemeral range (32768-60999), so no `bind(0)` anywhere in the suite can be handed a port inside a slice.
PORT_RANGE = (20000, 30000)

#: The environment xdist sets in each worker: its id (`gw<N>`) and the total worker count.
WORKER_ENV = "PYTEST_XDIST_WORKER"
WORKER_COUNT_ENV = "PYTEST_XDIST_WORKER_COUNT"


def worker_port_range(
    low: int = PORT_RANGE[0], high: int = PORT_RANGE[1], environ: dict[str, str] | None = None
) -> tuple[int, int]:
    """This worker's own inclusive slice of `[low, high]`, disjoint from every other worker's.

    Sized from the worker count xdist reports at startup, never from a constant, so 4 workers get 2,500 ports each and 23 get 434. A serial run (no xdist variables, or malformed ones) gets the whole range, which is exactly what it had before slicing existed.
    """
    env = os.environ if environ is None else environ
    worker = env.get(WORKER_ENV, "")
    count = env.get(WORKER_COUNT_ENV, "")
    if not (worker.startswith("gw") and worker[2:].isdigit() and count.isdigit()):
        return low, high
    index, total = int(worker[2:]), int(count)
    if total <= 0 or index >= total:
        return low, high
    width = (high - low + 1) // total
    start = low + index * width
    end = high if index == total - 1 else start + width - 1
    return start, end


def _bindable(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def free_port_in_range(
    environ: dict[str, str] | None = None, low: int = PORT_RANGE[0], high: int = PORT_RANGE[1]
) -> int:
    """A port that is free right now, inside this worker's slice.

    A RANDOM START inside the slice rather than the first free port, so two pytest SESSIONS on one machine (whose `gw0` workers share a slice) do not walk the same sequence; within one session the slices are disjoint, which is the collision that used to need the `ports` group.
    """
    start, end = worker_port_range(low, high, environ)
    span = end - start + 1
    offset = secrets.randbelow(span)
    for step in range(span):
        port = start + (offset + step) % span
        if _bindable(port):
            return port
    msg = "no free port in this worker's slice %d-%d" % (start, end)
    raise OSError(msg)


# --------------------------------------------------------------------------- Longest first ---------------------------------------------------------------------------

#: Per-file measured durations (ms) for the pytest lane, refreshed from CI by `budget_report.py --refresh`.
LANE_DURATIONS_SUBDIR = (".ci", "config", "lane-durations.json")
UNIT_PREFIX = "pytest:"
LANE_ID = "quality-pytest"


def unit_durations(path: pathlib.Path | None = None) -> tuple[dict[str, float], float]:
    """`({repo-relative test file: measured ms}, default ms for a file with no entry)`, or `({}, 0.0)` when the file cannot be read.

    THE TRACKED FILE, NOT THE LOCAL JUNIT, and that is a correctness choice. Every xdist worker collects on its own and the controller refuses a run whose workers collected different orders; a junit another session rewrites mid-collection would hand two workers two orders. A tracked file read at collection is the same bytes for every worker.
    """
    source = path if path is not None else paths.from_root(*LANE_DURATIONS_SUBDIR)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, 0.0
    units = data.get("units") if isinstance(data, dict) else None
    units = units if isinstance(units, dict) else {}
    durations = {
        key[len(UNIT_PREFIX) :]: float(value)
        for key, value in units.items()
        if key.startswith(UNIT_PREFIX) and isinstance(value, (int, float))
    }
    defaults = data.get("defaultUnitMs") if isinstance(data, dict) else None
    default = defaults.get(LANE_ID, 0.0) if isinstance(defaults, dict) else 0.0
    return durations, float(default) if isinstance(default, (int, float)) else 0.0


def order_longest_first(files: list[str], durations: dict[str, float], default: float) -> list[int]:
    """The indices of `files` (one per collected item, repo-relative) sorted by their file's measured duration, longest first.

    STABLE, so items keep their collection order inside a file and between equal files: a module whose cases rely on running in file order still does. `loadgroup` hands pending scopes out in collection order, so this is longest-processing-time-first scheduling, which keeps the longest files from being started last and finishing alone.
    """
    return sorted(range(len(files)), key=lambda i: -durations.get(files[i], default))


# --------------------------------------------------------------------------
# A GROUP IS MACHINE-WIDE, SO ITS SERIALISATION IS TOO (2026-10-05)
# --------------------------------------------------------------------------
# What remains in a group is a resource machine-wide by construction (the docstring above): a driver pinning constant ports, a fixed tmp path. `--dist loadgroup` serialises a group inside ONE pytest run only. Once the core lease split the machine fairly between concurrent runs (agent/plans/PLAN-prepush-full-cpu.md B11), two runs at 12 workers each both ran `account-shadow-fixed-ports` at once and nine of its cases failed on "port 45210 is taken ... [Errno 98] Address already in use". So every group also takes a flock named for it, beside the core lease, from its first item to its last in a worker: one process holds at most one group lock at a time, so two runs cannot deadlock on two groups taken in opposite orders, and process death releases the lock.

#: How long an item waits for ONE holder to leave its group before failing with that holder named. The largest group measured 217.3 s in one run (env-manifest, 2026-10-05); a holder that keeps it past this is hung, not busy. The bound is per holder: a queue of several runs taking the group in turn is busy, not hung, and on 2026-10-13 a waiter behind three writers' suites was failed as if one of them had hung.
GROUP_LOCK_WAIT_S = 900.0
GROUP_LOCK_POLL_S = 0.2


def group_lock_dir() -> pathlib.Path:
    """`groups/` beside the core lease's tokens, so a devbox and its host share one set (the lease directory is bound into the devbox)."""
    return core_lease.lease_dir() / "groups"


# --------------------------------------------------------------------------
# THE GROUP HAS TO REACH THE NODE ID, AND SINCE PYTEST 9.2 XDIST NO LONGER PUTS IT THERE
# --------------------------------------------------------------------------
# `--dist loadgroup` schedules on the node id's `@<group>` suffix, read in the controller, which only ever sees the id strings a worker sends. xdist 3.8.0 (xdist/remote.py:254) writes that suffix with `item._nodeid = ...`. pytest 9.2.0 replaced `_nodeid` with a structured `_id`, so the assignment now lands on an attribute nothing reads, and raises nothing.
#
# MEASURED 2026-11-01 on one test module, eight items, four of them in one group, `-n 3 --dist loadgroup`: pytest 9.1.1 ran the group on gw0 alone under `test_g[0]@g`; pytest 9.2.0 (4ecbce4dd, 2026-10-31) ran it on gw0, gw1 and gw2 under `test_g[0]`. No test failed, because MachineGroupLock still serialised the group: every worker handed one group item sat in time.sleep on that one flock. ci:quick run 40 read 19 of 20 workers in hrtimer_nanosleep with hooks-guards.lock open while the machine showed under 3 busy cores, and run 39 spent 735 s like that.
#
# THE ASSIGNMENT IS RE-CHECKED BECAUSE THE FAILURE IT REPAIRS WAS SILENT. A later pytest that moves the id again must fail the run naming the cause, not bring the tail back green.
#
# THE STAMP LIVES ONLY FOR THE MOMENT THE IDS ARE SENT. The controller matches a finished item by its index, so nothing later needs the suffix, and every report carries the id it was given: pytest 9.2's junit parses a report's id back into its parts, which would print a parametrised test as `t[x]@g]`, and that name would become the finding key on a red. Taking it off again gives a test the same name under xdist as in a serial run.


def stamp_group_ids(items: list, group_of) -> list[tuple[object, object]]:
    """Give every grouped item the `@<group>` node id `--dist loadgroup` schedules on, returning `(item, its id before)` for `unstamp_group_ids`. `group_of(item)` is the caller's reader, the same one that takes the machine-wide lock, so the schedule and the lock cannot disagree."""
    stamped: list[tuple[object, object]] = []
    for item in items:
        group = group_of(item)
        if group is None:
            continue
        before = item._id
        wanted = "%s@%s" % (item.nodeid, group)
        item._id = type(before).parse(wanted)
        if item.nodeid != wanted:
            raise RuntimeError(
                "xdist group %r did not reach the node id of %s: `--dist loadgroup` would spread the group over every worker and each would wait on its machine-wide lock. "
                "Read how this pytest stores a node id and fix xdist_groups.stamp_group_ids."
                % (group, item.nodeid)
            )
        stamped.append((item, before))
    return stamped


def unstamp_group_ids(stamped: list[tuple[object, object]]) -> None:
    """Put back the ids `stamp_group_ids` replaced."""
    for item, before in stamped:
        item._id = before


class MachineGroupLock:
    """The one group lock a pytest process holds, if any. `enter(group)` waits for it machine-wide; `release()` lets it go."""

    def __init__(self, root: pathlib.Path | None = None, wait_s: float = GROUP_LOCK_WAIT_S) -> None:
        self._root = root
        self._wait_s = wait_s
        self.held: str | None = None
        self._fd: int | None = None

    def enter(self, group: str) -> None:
        if self.held == group:
            return
        self.release()
        root = self._root if self._root is not None else group_lock_dir()
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / ("%s.lock" % "".join(c if c.isalnum() or c in "-_" else "_" for c in group))
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        deadline = time.monotonic() + self._wait_s
        seen = ""
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                holder = os.pread(fd, 200, 0).decode("utf-8", "replace").strip()
                if holder != seen:
                    # Another run has the group now: the one waited on left, so the clock starts again for this one.
                    seen, deadline = holder, time.monotonic() + self._wait_s
                if time.monotonic() >= deadline:
                    os.close(fd)
                    raise TimeoutError(
                        "xdist group %r is held machine-wide by another run (%s) for over %g s; "
                        "a group lock outliving that is a hung run"
                        % (group, holder or "holder unknown", self._wait_s)
                    ) from None
                time.sleep(GROUP_LOCK_POLL_S)
        os.ftruncate(fd, 0)
        os.pwrite(fd, ("pid %d\n" % os.getpid()).encode(), 0)
        self.held, self._fd = group, fd

    def release(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
        self.held, self._fd = None, None
