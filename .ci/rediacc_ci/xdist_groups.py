"""Which xdist group a test module belongs in, DERIVED and never hand-listed.

WHAT A GROUP MEANS, because the name suggests the opposite of what it does. Under `--dist loadgroup`, every item carrying `@pytest.mark.xdist_group(<name>)` is sent to the SAME worker as every other item with that name. Items with no group distribute freely. So a group is not a grouping for convenience: it is a SERIALISATION, and the only reason to ask for one is that two tests
share a resource the scheduler cannot see.

WITHOUT `--dist loadgroup` THE MARKER DOES NOTHING AT ALL. That is what makes it safe to land the derivation before the `-n` that uses it: a serial run collects and passes exactly as it did before, and the markers sit there inert.

--------------------------------------------------------------------------
THE DERIVATION, AND WHY IT YIELDS NOTHING TODAY
--------------------------------------------------------------------------
`.ci/rediacc_ci/tests/gates/test_gate_*.py` modules each declare a `BASH_TWIN`, and `test_twin_parity.py` RUNS that twin against the real tree on every pytest run. A twin that writes or scans the real tree therefore makes `check:ci-pytest` a participant in the battery's isolation contract; two such twins running in two workers at once is the `cp: cannot stat` flake nobody can
reproduce.

Which twins those are is already recorded, and this reads that record rather than becoming a second copy: `scripts/ci-runner/gates.lock.json`, via `battery.classify_from_lock`, under the `mutex` (exclusive) and `reads` (shared) claims. This is where the contract BELONGS.

THERE WAS A SECOND SOURCE AND IT IS GONE, WHICH IS A NARROWING RATHER THAN A LOSS. Until the shell battery runner was retired this also unioned in the `*_FALLBACK` arrays parsed out of `.ci/scripts/test/run-all.sh`, the hand-maintained knowledge that predated the lock declarations. The union was retired ON A MEASUREMENT, not on a hope: with the lock alone and with both
sources the answer was the same 27 names, and the runner-only set was EMPTY -- the arrays had nothing left to contribute because every name in them had landed in the lock. `battery.py`, which replaced that runner, carries no such array on purpose: a hand list beside the lock is the duplicated definition the whole port removes.

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

import os
import pathlib
import random
import socket

from rediacc_ci import battery, paths

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


def real_tree_twins(lock: pathlib.Path) -> set[str]:
    """Gate-test basenames that touch the REAL tree while they run.

    MOVED HERE FROM `test_twin_parity.real_tree_tests`, which now calls this, so the scheduler's idea of what needs isolating and the parity test's idea of what may be driven cannot drift apart. Two copies of this answer would be two answers to one question, and the expensive half of that is that both would look right.

    `lock` is a PARAMETER rather than a module constant so the controls can drive both directions on fixture files. That is the whole reason the signature takes it.

    An unreadable lock contributes NOTHING rather than raising, which is `battery.classify_from_lock`'s documented behaviour and is the caller's decision to interpret: "nothing is declared yet" and "the lock is broken" must not silently become "nothing needs isolating". THAT INTERPRETATION IS NOW THE WHOLE ANSWER, where it used to be one half of a union: a broken lock empties
    this set, so the anti-vacuity refusal on the total -- which lives with the callers, in `test_xdist_groups.py` and at runtime in `test_twin_parity.py` -- is the only thing standing between a damaged lock and a parity run that admits every twin including the ones that rewrite tracked files. That refusal is load-bearing rather than decorative.
    """
    return battery.classify_from_lock(lock, "mutex") | battery.classify_from_lock(lock, "reads")


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
    offset = random.randrange(span)  # noqa: S311 -- spreading probes, not security
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
        import json  # noqa: PLC0415 -- read once per collection, by the conftest only

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
