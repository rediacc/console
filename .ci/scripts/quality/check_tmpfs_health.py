#!/usr/bin/env python3
"""check:ci-tmpfs-health -- fail while there is still headroom to fail safely,
not after the inode table hits zero free.

WHY THIS EXISTS. `/tmp` (and CI runners generally) is a tmpfs with a FIXED
inode count independent of `df -h`'s block/byte view: a tree can show 19G free
of 29G and still be completely exhausted, because `df -i` (inodes) is a
separate budget from `df` (bytes). That exact split caused a real incident
this campaign: pytest's `tmp_path` fixture retained every run's temp tree
(`tmp_path_retention_policy` defaulting to "all"), and `/tmp/pytest-of-*`
alone accumulated ~70k inodes per run with no cleanup policy, until the
filesystem's inode table hit 1,048,574 / 1,048,576 used -- 2 free -- and every
subsequent Bash tool call in the session started failing with ENOSPC, even
though disk space looked completely healthy the whole time. The root cause
(`tmp_path_retention_policy = "failed"` in pyproject.toml) is fixed separately;
this gate is the instrumented tripwire so the NEXT uninstrumented temp-file
habit (a build script, a different test runner, a future fixture) is caught
at 90% used instead of discovered at 100% used via a wall of unrelated
failures.

SCOPE, stated so it is not mistaken for more than it is. This measures
CURRENT inode headroom at gate-run time -- a single point-in-time reading, not
a before/after delta bracketing every CI phase. A delta needs a write on each
side of every job step across every workflow, which is a wiring change to
every job, not a single check script; open the design in a plan if that is
wanted. A single-point threshold gate run in the quality lane already catches
the actual failure mode above, because the exhaustion is monotonic within a
run (nothing frees inodes mid-CI-job) -- by the time any phase's tmp usage is
past 90%, the NEXT phase is the one that would have hit the wall.

---- gate ----
step: Tmpfs health
needs: none
lane: quality-code
selftest: true
---- end gate ----
"""

from __future__ import annotations

import os
import sys
from typing import NamedTuple

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

THRESHOLD = 0.90

# Every path checked. /tmp is where the real incident happened; TMPDIR is
# checked too because some runners point it elsewhere and pytest/tempfile both honour it ahead of the hardcoded /tmp.
CHECK_PATHS = ["/tmp"]
if os.environ.get("TMPDIR") and os.environ["TMPDIR"] not in CHECK_PATHS:
    CHECK_PATHS.append(os.environ["TMPDIR"])


class Vfs(NamedTuple):
    f_files: int
    f_ffree: int


def usage_ratio(vfs: Vfs) -> float:
    """Fraction of inodes USED. 0.0 on a filesystem with no inode accounting
    (f_files == 0, e.g. some overlay/network mounts) -- absence of the metric
    is not evidence of exhaustion."""
    if vfs.f_files == 0:
        return 0.0
    used = vfs.f_files - vfs.f_ffree
    return used / vfs.f_files


def check_path(path: str, threshold: float = THRESHOLD) -> tuple[float, bool]:
    """(ratio, is_red) for one real path. Raises if the path does not exist --
    callers only pass paths they already know are live filesystems."""
    st = os.statvfs(path)
    vfs = Vfs(f_files=st.f_files, f_ffree=st.f_ffree)
    ratio = usage_ratio(vfs)
    return ratio, ratio >= threshold


def controls() -> None:
    """Control-first: the threshold logic is exercised on FAKE vfs tuples, not
    real filesystem state, so the control proves the math rather than the
    ambient health of whatever machine runs this."""
    # A tmpfs one inode away from total exhaustion -- this is the actual shape of the real incident (1,048,574 / 1,048,576 used).
    exhausted = Vfs(f_files=1_048_576, f_ffree=2)
    if usage_ratio(exhausted) < THRESHOLD:
        print(
            "%s✗ CONTROL FAILED%s: a near-total inode exhaustion was not flagged red" % (RED, NC),
            file=sys.stderr,
        )
        sys.exit(2)

    # A healthy filesystem with plenty of headroom must stay green.
    healthy = Vfs(f_files=1_048_576, f_ffree=900_000)
    if usage_ratio(healthy) >= THRESHOLD:
        print(
            "%s✗ CONTROL FAILED%s: a healthy inode count was misreported as exhausted" % (RED, NC),
            file=sys.stderr,
        )
        sys.exit(2)

    # A filesystem with no inode accounting (f_files == 0) must read as
    # healthy, not divide-by-zero and not false-positive.
    no_accounting = Vfs(f_files=0, f_ffree=0)
    if usage_ratio(no_accounting) != 0.0:
        print(
            "%s✗ CONTROL FAILED%s: a filesystem with no inode accounting was not "
            "treated as healthy" % (RED, NC),
            file=sys.stderr,
        )
        sys.exit(2)


def main() -> int:
    controls()
    red = False
    for path in CHECK_PATHS:
        try:
            ratio, is_red = check_path(path)
        except OSError as exc:
            print("%s✗%s %s: %s" % (RED, NC, path, exc), file=sys.stderr)
            red = True
            continue
        marker = "%s✗%s" % (RED, NC) if is_red else "%s✓%s" % (GREEN, NC)
        print(
            "%s %s: %.1f%% of inodes used (threshold %.0f%%)"
            % (marker, path, ratio * 100, THRESHOLD * 100)
        )
        if is_red:
            red = True
    if red:
        print(
            "tmpfs inode headroom below threshold -- see "
            ".ci/scripts/quality/check_tmpfs_health.py for the incident this guards "
            "against.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        controls()
        print("%s✓%s selftest" % (GREEN, NC))
        sys.exit(0)
    sys.exit(main())
