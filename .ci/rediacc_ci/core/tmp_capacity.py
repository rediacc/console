"""Refuse to start a pytest run or a ci-runner run when the temp filesystem is nearly out of inodes or space, with ONE line that names the cause.

WHY. /tmp here is a tmpfs capped at 1,048,576 inodes. On 2026-10-09 it filled twice in one session (worklist #edd646a8): `ci:quick` broke at 93% inode use, and a hook pytest run reported "43 failed, 10379 passed, 921 errors" with 1,330 inodes free. None of those errors named inodes, and the session nearly blamed a correct patch. A full temp filesystem fails every test that touches `tmp_path` with an ENOSPC buried in a fixture traceback, so the run reads as a code regression. This module turns that into one early, named refusal before a single test or gate starts.

WHO CALLS IT. The repo-root `conftest.py` (`pytest_configure`, controller only) and `scripts/ci-runner/run.ts` (`tmpCapacityRefusal`, before selection), which runs `python3 -m rediacc_ci.core.tmp_capacity` so the floor and the message have one home.

WHAT IT READS. `os.statvfs` on `tempfile.gettempdir()` and on any explicit basetemp (`--path`, or pytest's `--basetemp`), deduplicated by device. `f_favail` and `f_bavail` (what an unprivileged process can still use), not `f_ffree`/`f_bfree`. A filesystem reporting `f_files == 0` (btrfs allocates inodes dynamically) has no inode ceiling, which is printed as such rather than read as zero free.

UNKNOWN IS A REFUSAL. A path whose statvfs fails is reported as unchecked and the run refuses, because a capacity check that cannot read the capacity has verified nothing.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import tempfile
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

__all__ = [
    "FLOOR_ENV",
    "Floor",
    "Reading",
    "check",
    "consumers",
    "floor_from_env",
    "main",
    "read",
    "shortfalls",
]

# THE FLOOR, and why these numbers.
#
# MIN_FREE_INODES = 100,000. A single hook pytest basetemp was measured at 70,000-90,000 inodes on 2026-10-09 and a finished scratch clone at about 10,000, and the run that broke `ci:quick` did so with roughly 73,000 free (93% of 1,048,576 used). The floor must sit ABOVE that failure point, or the check would have passed the very run it exists for, and it must leave room for
# one whole basetemp to be created after it passes. 100,000 does both, and on this tmpfs it is 9.5% of the inodes, so it fires at about 90.5% use: early enough to name the cause, late enough not to cry wolf at the 50-60% this machine normally runs at.
#
# MIN_FREE_INODE_PCT = 5. The absolute floor is the binding one on this tmpfs; the percentage is for a much larger temp filesystem (a CI runner's root disk with millions of inodes), where 100,000 free would already mean 99%+ use and a sick filesystem.
#
# MIN_FREE_BYTES = 1 GiB. Space was not the incident, but a run that writes junit, caches and clones into a temp dir with less than this fails the same unnamed way. A percentage floor on bytes is deliberately absent: a small CI tmpfs at 80% use with several GiB free is healthy.
MIN_FREE_INODES = 100_000
MIN_FREE_INODE_PCT = 5.0
MIN_FREE_BYTES = 1 << 30

# FOR TESTS ONLY, and it can only RAISE the inode floor. A control must be able to plant "this machine is below the floor" against the real filesystem, which is what the conftest and ci-runner wiring controls do. An override that could LOWER the floor would be a switch for getting past the check, which is the suppression this repo forbids; a value below the
# default is therefore ignored in favour of the default, and a value that is not an integer is a refusal rather than a silent fallback.
FLOOR_ENV = "TMP_CAPACITY_MIN_FREE_INODES"

# The consumer walk runs only on the refusal path, so its cost is paid once by a run that was not going to start anyway. Capped so that a million-inode tree cannot turn a one-line refusal into a minute of silence; a capped walk says so.
WALK_BUDGET_S = 3.0
TOP = 3

FIX = (
    "fix: delete finished scratch clones (`python3 .claude/hooks/stop/worklist.py --prune-scratch <me>` lists the "
    "session scratchpad, `--write` deletes) and finished pytest runs' basetemps, which that verb does not touch: "
    "remove a pytest-<n> directory under <tmp>/pytest-of-<user> that no live process uses; then rerun"
)


@dataclasses.dataclass(frozen=True)
class Reading:
    """One filesystem's capacity, as statvfs reports it for an unprivileged process. `total_inodes == 0` means the filesystem has no inode ceiling."""

    path: str
    total_inodes: int
    free_inodes: int
    total_bytes: int
    free_bytes: int


@dataclasses.dataclass(frozen=True)
class Floor:
    min_free_inodes: int = MIN_FREE_INODES
    min_free_inode_pct: float = MIN_FREE_INODE_PCT
    min_free_bytes: int = MIN_FREE_BYTES

    def describe(self) -> str:
        return "%s inodes and %g%% free, %s" % (
            _n(self.min_free_inodes),
            self.min_free_inode_pct,
            _gib(self.min_free_bytes),
        )


def _n(value: int) -> str:
    return f"{value:,}"


def _gib(value: int) -> str:
    return "%.1f GiB" % (value / float(1 << 30))


def floor_from_env(env: Mapping[str, str] | None = None) -> Floor:
    """The floor, with the test-only override applied. Raises ValueError on a value that is not a non-negative integer."""
    # The live read is spelled `os.environ.get` on purpose: check:ci-python-env-registry derives its pairs from that call shape, and a read through a local mapping is invisible to it, which would leave this input undeclared.
    raw = (os.environ.get(FLOOR_ENV) if env is None else env.get(FLOOR_ENV)) or ""
    raw = raw.strip()
    if not raw:
        return Floor()
    try:
        value = int(raw)
    except ValueError:
        raise ValueError("%s=%r is not an integer" % (FLOOR_ENV, raw)) from None
    if value < 0:
        raise ValueError("%s=%r is negative" % (FLOOR_ENV, raw))
    return Floor(min_free_inodes=max(MIN_FREE_INODES, value))


def _existing(path: str) -> str:
    """`path`, or its nearest existing ancestor: a basetemp is usually created after this check runs, and it lands on its parent's filesystem."""
    probe = os.path.abspath(path)
    while not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return probe


def read(path: str) -> Reading:
    """statvfs `path` (or its nearest existing ancestor). Raises OSError when the filesystem cannot be read."""
    target = _existing(path)
    st = os.statvfs(target)
    return Reading(
        path=target,
        total_inodes=int(st.f_files),
        free_inodes=int(st.f_favail),
        total_bytes=int(st.f_blocks) * int(st.f_frsize),
        free_bytes=int(st.f_bavail) * int(st.f_frsize),
    )


def shortfalls(reading: Reading, floor: Floor) -> list[str]:
    """Every floor `reading` is below, as a phrase; empty when the filesystem is healthy."""
    out = []
    if reading.total_inodes > 0:
        pct = 100.0 * reading.free_inodes / reading.total_inodes
        if reading.free_inodes < floor.min_free_inodes:
            out.append("%s inodes free < %s" % (_n(reading.free_inodes), _n(floor.min_free_inodes)))
        elif pct < floor.min_free_inode_pct:
            out.append("%.1f%% inodes free < %g%%" % (pct, floor.min_free_inode_pct))
    if reading.free_bytes < floor.min_free_bytes:
        out.append("%s free < %s" % (_gib(reading.free_bytes), _gib(floor.min_free_bytes)))
    return out


def _shape(reading: Reading) -> str:
    if reading.total_inodes > 0:
        used = reading.total_inodes - reading.free_inodes
        inodes = "%s of %s inodes used (%.1f%%), %s free" % (
            _n(used),
            _n(reading.total_inodes),
            100.0 * used / reading.total_inodes,
            _n(reading.free_inodes),
        )
    else:
        inodes = "no inode ceiling"
    return "%s: %s, %s of %s free" % (
        reading.path,
        inodes,
        _gib(reading.free_bytes),
        _gib(reading.total_bytes),
    )


def consumers(
    root: str,
    budget_s: float = WALK_BUDGET_S,
    top: int = TOP,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """The biggest inode consumers under `root`, found cheaply, as one phrase.

    The top `top` entries directly under `root` by inode count, and for the largest one the place its inodes CONCENTRATE: the walk descends through any child holding at least half of its parent, so `/tmp/claude-1000` resolves to the session scratchpad that actually holds the clones, whose own top children are listed. Symlinks are counted, never followed. The walk stops at
    `budget_s` and says "(partial)" when it did.
    """
    deadline = clock() + budget_s
    state = {"partial": False}
    counts: dict[str, int] = {}
    children: dict[str, list[str]] = {}

    def walk(path: str) -> int:
        total = 1
        kids: list[str] = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if clock() > deadline:
                        state["partial"] = True
                        break
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        is_dir = False
                    if is_dir:
                        sub = walk(entry.path)
                        kids.append(entry.path)
                        counts[entry.path] = sub
                        total += sub
                    else:
                        total += 1
        except (OSError, RecursionError):
            pass
        children[path] = kids
        return total

    counts[root] = walk(root)
    ranked = sorted(children.get(root, []), key=lambda p: counts[p], reverse=True)[:top]
    if not ranked:
        return "biggest: nothing readable under %s" % root
    focus = ranked[0]
    while True:
        kids = sorted(children.get(focus, []), key=lambda p: counts[p], reverse=True)
        if kids and counts[kids[0]] * 2 >= counts[focus]:
            focus = kids[0]
            continue
        break
    inner = sorted(children.get(focus, []), key=lambda p: counts[p], reverse=True)[:top]
    parts = []
    for i, path in enumerate(ranked):
        if i == 0:
            label = focus if focus != path else path
            detail = ", ".join("%s %s" % (os.path.basename(k), _n(counts[k])) for k in inner)
            parts.append("%s %s%s" % (label, _n(counts[focus]), " [%s]" % detail if detail else ""))
        else:
            parts.append("%s %s" % (path, _n(counts[path])))
    return "biggest%s: %s" % (
        " (partial, walk capped at %gs)" % budget_s if state["partial"] else "",
        "; ".join(parts),
    )


def _devices(paths: Iterable[str]) -> list[str]:
    seen: set[int] = set()
    out = []
    for path in paths:
        target = _existing(path)
        try:
            dev = os.stat(target).st_dev
        except OSError:
            out.append(path)
            continue
        if dev not in seen:
            seen.add(dev)
            out.append(path)
    return out


def check(
    paths: Iterable[str] | None = None,
    floor: Floor | None = None,
    reader: Callable[[str], Reading] = read,
    walker: Callable[[str], str] = consumers,
) -> tuple[bool, str]:
    """(ok, one line). `paths` defaults to `tempfile.gettempdir()`; `reader` and `walker` are the seams a test injects a fake reading through."""
    candidates = [tempfile.gettempdir()] if paths is None else list(paths)
    if not candidates:
        return False, "tmp-capacity: REFUSING to start: no temp path was given to check"
    if floor is None:
        try:
            floor = floor_from_env()
        except ValueError as exc:
            return False, "tmp-capacity: REFUSING to start: %s" % exc
    shapes = []
    for path in _devices(candidates):
        try:
            reading = reader(path)
        except OSError as exc:
            return False, (
                "tmp-capacity: REFUSING to start: %s is UNCHECKED, statvfs failed (%s); a capacity check that cannot read the capacity has verified nothing"
                % (path, exc)
            )
        short = shortfalls(reading, floor)
        if short:
            return (
                False,
                "tmp-capacity: REFUSING to start: %s; below the floor (%s; floor %s). %s. %s"
                % (
                    _shape(reading),
                    ", ".join(short),
                    floor.describe(),
                    walker(reading.path),
                    FIX,
                ),
            )
        shapes.append(_shape(reading))
    return True, "tmp-capacity: ok, %s (floor %s)" % ("; ".join(shapes), floor.describe())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tmp_capacity",
        description="Refuse when the temp filesystem is below its inode or space floor.",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="a temp path to check (repeatable); default: tempfile.gettempdir()",
    )
    args = parser.parse_args(argv)
    ok, line = check(args.path or None)
    print(line, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
