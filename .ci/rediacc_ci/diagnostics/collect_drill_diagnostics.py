"""Port of `.ci/scripts/test/collect-drill-diagnostics.sh`.

Gathers the logs a failed drill needs but does not print itself: the account server's RustFS compose output (`.account-logs/rustfs.log`, produced by a `... || true` in `account.sh` and therefore invisible anywhere else on a compose failure) and each kept drill work directory's `gateway.log`. See the twin's own header for the 2026-08 incident that made this necessary.

REQUIRES `--keep-work`: without it `drill_teardown` removes the work directory on exit before this ever runs, and no environment variable substitutes for
that (`scripts/drills/lib.sh` sets `DRILL_KEEP_WORK=0` at script level).

ALWAYS EXITS 0. This runs in an `if: always()` diagnostics step attached to an ALREADY-FAILED job; a non-zero exit here would bury the real failure under a complaint about collecting diagnostics for it. An empty collection is reported as a message, never as a failure -- see `main()`.

ORDERING, ARGUED RATHER THAN ASSUMED EQUIVALENT. The twin's first loop is a bash GLOB (`for work in .../rediacc-drill-*/`), and bash sorts glob matches lexicographically regardless of directory order; `sorted()` here reproduces that exactly -- a language guarantee (Python's `sorted()` on strings), not an accident of this filesystem, matching bash's own guarantee the same way.

The twin's final listing is `find "$dest" -type f`, which is UNSORTED readdir order and, taken alone, filesystem-dependent. What makes it reproducible here is not the fixture size, it is that `find` and `os.walk` are both thin wrappers over the SAME kernel primitive (getdents, via readdir/scandir) reading the SAME directory: two different programs reading one unmodified directory
get the SAME enumeration order from the kernel, sorted or not, because neither one imposes an order of its own. Measured directly: a plain `pathlib.glob()` over a hand-built tmpfs directory is NOT alphabetical for more than a couple of entries (confirmed while writing this port, on this filesystem), which is exactly why the FIRST loop does not rely on it and calls `sorted()`
explicitly -- but `find` vs `os.walk` on `$dest` is a different comparison, between two readers of one directory rather than between one reader and an assumption about its order.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil
import sys
import tempfile


def _root() -> pathlib.Path:
    # This file: <root>/.ci/rediacc_ci/diagnostics/collect_drill_diagnostics.py
    return pathlib.Path(__file__).resolve().parents[3]


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments

    root_dir = _root()
    runner_temp = os.environ.get("RUNNER_TEMP")
    base = pathlib.Path(runner_temp) if runner_temp else pathlib.Path(tempfile.mkdtemp())
    dest = base / "drill-diagnostics"
    dest.mkdir(parents=True, exist_ok=True)

    # The account log dir lives in the workspace and survives the drill.
    account_logs = root_dir / ".account-logs"
    if account_logs.is_dir():
        # best-effort, matching the twin's `2>/dev/null || true`
        with contextlib.suppress(OSError):
            shutil.copytree(account_logs, dest / "account-logs", dirs_exist_ok=True)

    tmpdir = pathlib.Path(os.environ.get("TMPDIR") or "/tmp")
    # Bash glob expansion sorts lexicographically; `sorted()` matches it, not a coincidence of iteration order.
    for work in sorted(tmpdir.glob("rediacc-drill-*/")):
        if not work.is_dir():
            continue
        sub = dest / work.name
        sub.mkdir(parents=True, exist_ok=True)
        gateway_log = work / "gateway.log"
        if gateway_log.is_file():
            with contextlib.suppress(OSError):
                shutil.copy2(gateway_log, sub / "gateway.log")

    collected = list(_walk_files(dest))
    count = len(collected)
    print(f"drill diagnostics collected: {count} file(s) under {dest}")
    for path in collected:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        print(f"  {size:>10} bytes  {path}")
    # A VACUOUS collection is REPORTED, not fatal: this runs in an `if: always()` diagnostics step, so exiting non-zero here would replace the real failure the operator came to read with a complaint about its diagnostics. The floor is the message.
    if count == 0:
        print("  (nothing collected -- check that the drills ran with --keep-work)")

    return 0


def _walk_files(dest: pathlib.Path) -> list[pathlib.Path]:
    """Every regular file under `dest`, in `os.walk`'s (unsorted) order.

    Matches `find "$dest" -type f`'s own lack of sorting -- see the module docstring's ORDERING note for what that equivalence claim does and does not cover.
    """
    out: list[pathlib.Path] = []
    for dirpath, _dirnames, filenames in os.walk(dest):
        out.extend(pathlib.Path(dirpath) / name for name in filenames)
    return out


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
