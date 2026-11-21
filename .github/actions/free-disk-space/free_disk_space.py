#!/usr/bin/env python3
"""Frees runner disk in the background (`start`) and joins that cleanup later (`wait`).

Usage (from action.yml): python3 "$FREE_DISK_SPACE" start|wait
Environment: THRESHOLD_GB (`start` only), RUNNER_TEMP.

It sits beside the action because callers run it before, or without, a full checkout. Standard library only.

`start` measures free space on `/` and only launches the deletion (the preinstalled .NET, Android SDK, GHC, PowerShell and Swift, then `docker system prune -af`) when it is below THRESHOLD_GB, writing the pid of the detached cleanup to `$RUNNER_TEMP/free-disk-space.pid`. It always logs the measurement and its decision. `wait` joins that pid; it no-ops when no pidfile exists, which is exactly the case when `start` decided free space was already sufficient.
Measured problem, job 108658401190: these runners already have about 83 GB free on `/` before any cleanup, yet an unconditional cleanup cost 221-309s on some legs for no benefit.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import time

CLEANUP = (
    "sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc "
    "/usr/local/share/powershell /usr/share/swift 2>/dev/null || true; "
    "docker system prune -af 2>/dev/null || true"
)


def pidfile() -> pathlib.Path:
    return pathlib.Path(os.environ["RUNNER_TEMP"]) / "free-disk-space.pid"


def df() -> None:
    subprocess.run(["df", "-h", "/"], check=False)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start(threshold_gb: int) -> None:
    print("=== Disk usage before cleanup ===", flush=True)
    df()
    avail_gb = shutil.disk_usage("/").free // 2**30
    print("Free space on /: %dGB (threshold: %dGB)" % (avail_gb, threshold_gb), flush=True)
    if avail_gb >= threshold_gb:
        print("At or above threshold; skipping cleanup")
        return
    print("Below threshold; starting background cleanup", flush=True)
    # A new session, so the cleanup outlives this step the way the old `( ... ) &` did.
    proc = subprocess.Popen(
        ["bash", "-c", CLEANUP],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pidfile().write_text("%d\n" % proc.pid, encoding="utf-8")


def wait() -> None:
    path = pidfile()
    if path.is_file():
        pid = int(path.read_text(encoding="utf-8").strip())
        while pid_alive(pid):
            time.sleep(1)
        path.unlink(missing_ok=True)
    else:
        print(
            "No cleanup was started (free space was already above threshold); nothing to wait for"
        )
    print("=== Disk usage after cleanup ===")
    df()


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("start", "wait"):
        print("::error::free-disk-space: usage: free_disk_space.py start|wait")
        return 2
    if argv[0] == "start":
        raw = os.environ.get("THRESHOLD_GB", "")
        if not raw.isdigit():
            print("::error::free-disk-space: threshold_gb must be a whole number, got '%s'" % raw)
            return 2
        start(int(raw))
    else:
        wait()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
