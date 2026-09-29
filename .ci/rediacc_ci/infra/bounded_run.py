"""Run one command under a hard time limit, with a periodic host heartbeat, and kill everything it started when the limit fires.

WHY THIS EXISTS. The macos-intel `rdc ops up --basic` step normally takes 2-4 minutes. On 2026-09-28 it ran 50+ minutes twice with the same renet binary that had just passed four times, and neither the step's `timeout-minutes: 15` nor the job's `timeout-minutes: 45` fired, so the runner itself stopped enforcing its limits. The watchdog then cancelled the job, and a cancelled job keeps no log. This wrapper moves the limit inside the job, where it does not depend on the runner's timer, and prints the host's state every `--heartbeat` seconds so the log shows the machine's condition before any freeze.

The macOS runner has no coreutils `timeout`, so the limit is enforced here with the standard library. The command runs in its own session (`start_new_session`), which lets one `killpg` reach every process it forked that stayed in the group. QEMU's `-daemonize` calls `setsid` and leaves that group, so a guest is reaped separately through the pid files the qemu driver writes (`--reap-pidfiles`, a glob expanded at kill time).

EXIT CODES. The command's own code when it finishes in time (128+N when a signal N killed it); 124 when the limit fired, as coreutils `timeout` does; 128+N when this process received signal N (the runner's own cancel sends SIGINT, then SIGTERM). Every kill path reports any process that survived it, so "nothing is left alive" is printed as a checked fact rather than assumed.

A successful run reaps nothing: the VMs `ops up` starts are what the later steps test. The heartbeat and every diagnostic go to stderr, so the command's stdout stays its own.
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import os
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

TIMEOUT_EXIT = 124
TERM_GRACE_S = 10.0
PROBE_TIMEOUT_S = 5.0


def log(msg: str) -> None:
    print(f"bounded_run: {msg}", file=sys.stderr, flush=True)


def probe(argv: Sequence[str]) -> str:
    """One diagnostic command's stdout, or a short reason it gave none. Bounded, so a stuck probe cannot stall the watchdog loop that calls it."""
    try:
        done = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=PROBE_TIMEOUT_S, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"<{argv[0]}: {type(exc).__name__}>"
    return done.stdout.strip()


def memory_line() -> str:
    """Free and used memory in MiB: `vm_stat` pages on macOS, /proc/meminfo on Linux."""
    if sys.platform == "darwin":
        raw = probe(["vm_stat"])
        page = 4096
        fields: dict[str, int] = {}
        for line in raw.splitlines():
            if "page size of" in line:
                page = int(
                    "".join(ch for ch in line.split("page size of")[1] if ch.isdigit()) or page
                )
                continue
            name, _, value = line.partition(":")
            digits = value.strip().rstrip(".")
            if digits.isdigit():
                fields[name.strip()] = int(digits) * page // (1 << 20)
        keys = (
            "Pages free",
            "Pages active",
            "Pages inactive",
            "Pages wired down",
            "Pages occupied by compressor",
            "Swapouts",
        )
        parts = [
            f"{k.removeprefix('Pages ').replace(' ', '_')}={fields[k]}M"
            for k in keys
            if k in fields
        ]
        swap = probe(["sysctl", "-n", "vm.swapusage"])
        return (
            " ".join(parts) + (f" swap[{swap}]" if swap else "")
            if parts
            else f"vm_stat: {raw[:120] or 'no output'}"
        )
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            info = {k: v.split()[0] for k, _, v in (line.partition(":") for line in fh)}
        return " ".join(
            f"{k}={int(info[k]) // 1024}M"
            for k in ("MemTotal", "MemAvailable", "SwapFree")
            if k in info
        )
    except OSError as exc:
        return f"<meminfo: {exc}>"


def top_processes(n: int = 6) -> list[str]:
    """The `n` busiest processes by CPU, from `ps` sorted here: BSD and procps disagree on every sort flag."""
    rows = []
    for line in probe(["ps", "-Ao", "pid=,pcpu=,rss=,etime=,comm="]).splitlines():
        cols = line.split(None, 4)
        if len(cols) == 5:
            try:
                rows.append((float(cols[1]), cols))
            except ValueError:
                continue
    rows.sort(key=lambda r: r[0], reverse=True)
    return [
        f"pid={c[0]} cpu={c[1]}% rss={int(c[2]) // 1024}M etime={c[3]} {c[4][-60:]}"
        for _, c in rows[:n]
    ]


def host_facts() -> str:
    """The host's size and hypervisor support, printed once. On macOS `kern.hv_support` 1 means HVF is usable."""
    facts = [f"cpus={os.cpu_count()}"]
    if sys.platform == "darwin":
        mem = probe(["sysctl", "-n", "hw.memsize"])
        if mem.isdigit():
            facts.append(f"mem={int(mem) >> 30}G")
        facts.append(f"hv_support={probe(['sysctl', '-n', 'kern.hv_support']) or '?'}")
        facts.append(f"os={probe(['sw_vers', '-productVersion'])}")
    return " ".join(facts)


def heartbeat(started: float) -> None:
    load = " ".join(f"{x:.2f}" for x in os.getloadavg())
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log(
        f"heartbeat {stamp} elapsed={int(time.monotonic() - started)}s load=[{load}] {memory_line()}"
    )
    for row in top_processes():
        log(f"  top {row}")


def pidfile_pids(pattern: str | None) -> list[int]:
    pids = []
    for path in sorted(glob.glob(pattern)) if pattern else []:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read().strip()
        except OSError:
            continue
        if text.isdigit():
            pids.append(int(text))
    return pids


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def signal_group(pgid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)


def signal_pid(pid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.kill(pid, sig)


def kill_all(child: subprocess.Popen[bytes], reap_pattern: str | None) -> bool:
    """TERM the command's process group and every reaped pid, wait up to TERM_GRACE_S, then KILL what is left. True when nothing survived."""
    pgid = child.pid
    extra = pidfile_pids(reap_pattern)
    log(f"killing process group {pgid}" + (f" and reaped pids {extra}" if extra else ""))
    signal_group(pgid, signal.SIGTERM)
    for pid in extra:
        signal_pid(pid, signal.SIGTERM)
    deadline = time.monotonic() + TERM_GRACE_S
    while time.monotonic() < deadline:
        child.poll()
        if not group_alive(pgid) and not any(alive(p) for p in extra):
            break
        time.sleep(0.2)
    signal_group(pgid, signal.SIGKILL)
    for pid in extra:
        signal_pid(pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.wait(timeout=TERM_GRACE_S)
    time.sleep(0.2)
    # A pid file written after the first read (a guest started during the grace window) is read again here.
    late = [p for p in pidfile_pids(reap_pattern) if p not in extra]
    for pid in late:
        signal_pid(pid, signal.SIGKILL)
    time.sleep(0.2 if late else 0)
    survivors = [p for p in extra + late if alive(p)]
    if group_alive(pgid) or survivors:
        log(f"SURVIVORS after SIGKILL: group {pgid} alive={group_alive(pgid)} pids={survivors}")
        return False
    log("every process the command started is gone")
    return True


def run(
    cmd: Sequence[str],
    limit_s: float,
    beat_s: float,
    reap_pattern: str | None,
    on_beat: Callable[[float], None] = heartbeat,
) -> int:
    log(f"limit={limit_s:g}s heartbeat={beat_s:g}s host: {host_facts()}")
    log(f"running: {' '.join(cmd)}")
    started = time.monotonic()
    child = subprocess.Popen(list(cmd), start_new_session=True)
    received: list[int] = []

    def on_signal(signum: int, _frame: object) -> None:
        received.append(signum)

    previous = {
        s: signal.signal(s, on_signal) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
    }
    try:
        next_beat = started + beat_s
        while True:
            now = time.monotonic()
            wait_s = max(0.0, min(started + limit_s, next_beat) - now)
            try:
                rc = child.wait(timeout=min(wait_s, 1.0))
            except subprocess.TimeoutExpired:
                rc = None
            if rc is not None:
                return rc if rc >= 0 else 128 - rc
            if received:
                sig = received[0]
                log(f"received signal {sig}; stopping the command")
                on_beat(started)
                kill_all(child, reap_pattern)
                return 128 + sig
            now = time.monotonic()
            if now - started >= limit_s:
                log(f"TIMEOUT: still running after {limit_s:g}s: {' '.join(cmd)}")
                on_beat(started)
                kill_all(child, reap_pattern)
                return TIMEOUT_EXIT
            if now >= next_beat:
                on_beat(started)
                next_beat += beat_s
    finally:
        for s, handler in previous.items():
            signal.signal(s, handler)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bounded_run", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--limit", type=float, required=True, help="seconds before the command is killed (exit 124)"
    )
    parser.add_argument(
        "--heartbeat", type=float, default=30.0, help="seconds between host heartbeats on stderr"
    )
    parser.add_argument(
        "--reap-pidfiles",
        default=None,
        help="glob of pid files whose processes are killed with the command",
    )
    parser.add_argument("cmd", nargs=argparse.REMAINDER, help="-- command [args...]")
    args = parser.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd or args.limit <= 0 or args.heartbeat <= 0:
        parser.error("a command after --, and a positive --limit and --heartbeat, are required")
    return run(cmd, args.limit, args.heartbeat, args.reap_pidfiles)


if __name__ == "__main__":
    sys.exit(main())
