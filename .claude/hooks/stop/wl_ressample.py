"""wl_ressample: sample a process TREE from /proc at a cadence, forklessly.

WHY A SAMPLER AND NOT JUST THE EXIT RECORDER. wl_resprofile writes one record when
a process EXITS -- totals, cheap, every process. But the findings that matter are
about SHAPE OVER TIME: were the children sequential or overlapping (E1/E4), what
state was each in (R-fraction, the only load-invariant saturation measure), did
zombies accumulate under a live parent (E6), which paths were held write-open
(E4). None of that exists at exit. It has to be observed while the tree is alive,
from the outside, rooted at a pid the caller owns -- for CI gates that root is the
child `scripts/ci-runner/exec.ts:65` spawns.

THE DISCIPLINE, copied from .ci/scripts/ci/profiler/sampler-linux.sh and
report.awk because they already paid for it:
  * NO FORKS in the loop. Every reading is an open()+read() of a /proc file; a
    sampler that perturbs the box is measuring itself.
  * META FIELDS ARE APPEND-ONLY; a new field goes on the end so an archived
    capture keeps parsing.
  * ANTI-VACUITY IS THE POINT. The run record carries `expected_n` beside
    `samples_n`; a consumer that sees fewer than 0.8x the expected count treats the
    capture as UNJUDGEABLE, never as "the tree used nothing". A run shorter than
    one interval is "<interval, unsampled", never 0.
  * `wchan` is read verbatim (symbolic on both host and devbox, verified). The
    partition into DEFERRING {do_wait, anon_pipe_read, pipe_read} and TERMINAL is the
    CONSUMER's job (wl_profile), not this module's: a sampler that classifies is a
    sampler that lies consistently.

WHAT IS RECORDED PER PROCESS PER TICK, and what is not. pid, ppid, comm, state,
wchan, utime/stime/cutime/cstime (clock ticks), minflt/majflt, VmHWM/VmRSS (kB),
voluntary/nonvoluntary ctxt switches, and the WRITABLE fd targets that resolve to a
path under the repo root. NEVER argv, never cmdline, never environ, never any fd
target outside the repo root (a socket or a /tmp path can carry a name that is a
secret). `comm` is 15 bytes of the executable's basename -- a public string.

SAFETY. Runs beside the thing it measures, so a bug here must cost samples, never
the run: every per-pid read is individually guarded (a pid that exits between the
directory listing and the read is normal, not an error), the loop never raises,
and the output file is opened once with O_APPEND.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from pathlib import Path

DEFAULT_INTERVAL_MS = 2000
MAX_DEPTH = 12
MAX_NODES = 512
CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def repo_root() -> Path | None:
    try:
        return Path(__file__).resolve().parents[3]
    except (IndexError, OSError):
        return None


def _children(pid: int) -> list[int]:
    """Children via /proc/<pid>/task/<tid>/children -- present here, one read per thread."""
    out: list[int] = []
    task = "/proc/%d/task" % pid
    try:
        tids = os.listdir(task)
    except OSError:
        return out
    for tid in tids:
        for tok in _read("%s/%s/children" % (task, tid)).split():
            with contextlib.suppress(ValueError):
                out.append(int(tok))
    return out


def _stat_fields(pid: int) -> list[str] | None:
    raw = _read("/proc/%d/stat" % pid)
    if not raw:
        return None
    # comm may contain spaces and parens; it is delimited by the LAST ')'.
    rp = raw.rfind(")")
    if rp < 0:
        return None
    comm = raw[raw.find("(") + 1 : rp]
    rest = raw[rp + 2 :].split()
    return [raw.split(" ", 1)[0], comm, *rest]


def _writable_repo_fds(pid: int, root: Path | None) -> list[str]:
    """Targets of fds opened for writing that resolve under the repo root. Nothing else."""
    if root is None:
        return []
    out: list[str] = []
    fddir = "/proc/%d/fd" % pid
    try:
        names = os.listdir(fddir)
    except OSError:
        return out
    for n in names:
        info = _read("/proc/%d/fdinfo/%s" % (pid, n))
        flags = None
        for line in info.splitlines():
            if line.startswith("flags:"):
                with contextlib.suppress(ValueError):
                    flags = int(line.split()[1], 8)
                break
        if flags is None or (flags & 0o3) == 0:  # O_RDONLY -> not a writer
            continue
        try:
            target = os.readlink("%s/%s" % (fddir, n))
        except OSError:
            continue
        if not target.startswith("/"):
            continue
        try:
            rel = Path(target).relative_to(root)
        except ValueError:
            continue
        out.append(str(rel))
    return out


def sample_pid(pid: int, root: Path | None) -> dict | None:
    st = _stat_fields(pid)
    if st is None or len(st) < 24:
        return None
    rec = {
        "pid": pid,
        "ppid": int(st[3]),
        "comm": st[1][:15],
        "state": st[2],
        "wchan": _read("/proc/%d/wchan" % pid).strip() or None,
        "minflt": int(st[9]),
        "majflt": int(st[11]),
        "utime": int(st[13]),
        "stime": int(st[14]),
        "cutime": int(st[15]),
        "cstime": int(st[16]),
    }
    for line in _read("/proc/%d/status" % pid).splitlines():
        k, _, v = line.partition(":")
        if k in ("VmHWM", "VmRSS", "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches"):
            with contextlib.suppress(IndexError, ValueError):
                rec[
                    {
                        "VmHWM": "hwm_kb",
                        "VmRSS": "rss_kb",
                        "voluntary_ctxt_switches": "vctxt",
                        "nonvoluntary_ctxt_switches": "nvctxt",
                    }[k]
                ] = int(v.split()[0])
    rec["wfd"] = _writable_repo_fds(pid, root)
    return rec


def sample_tree(root_pid: int, root: Path | None = None) -> list[dict]:
    """One tick: every live process under root_pid, bounded in depth and count."""
    root = repo_root() if root is None else root
    out: list[dict] = []
    stack = [(root_pid, 0)]
    seen: set[int] = set()
    while stack and len(out) < MAX_NODES:
        pid, depth = stack.pop()
        if pid in seen or depth > MAX_DEPTH:
            continue
        seen.add(pid)
        rec = sample_pid(pid, root)
        if rec is None:
            continue
        rec["depth"] = depth
        out.append(rec)
        stack.extend((c, depth + 1) for c in _children(pid))
    return out


def _psi(name: str) -> int | None:
    for line in _read("/proc/pressure/%s" % name).splitlines():
        if line.startswith("some "):
            for tok in line.split():
                if tok.startswith("total="):
                    with contextlib.suppress(ValueError):
                        return int(tok[6:])
    return None


def _scope() -> str:
    return "container" if _read("/proc/self/cgroup").strip() == "0::/" else "machine"


def watch(
    root_pid: int,
    out_path: Path,
    interval_ms: int = DEFAULT_INTERVAL_MS,
    run_id: str = "",
    max_s: float = 21600.0,
    t0_ms: int | None = None,
) -> dict:
    """Sample until root_pid is gone (or max_s). Returns the run record it wrote last."""
    root = repo_root()
    t0 = time.monotonic()
    psi0 = {n: _psi(n) for n in ("cpu", "io")}
    fd = os.open(str(out_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    n = 0
    try:
        while time.monotonic() - t0 < max_s:
            try:
                os.kill(root_pid, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                pass
            procs = sample_tree(root_pid, root)
            # A root in state Z is a finished process nobody reaped; the tree is over.
            if procs and procs[0]["state"] == "Z" and len(procs) == 1:
                break
            n += 1
            line = (
                json.dumps(
                    {
                        "v": 1,
                        "k": "S",
                        "run": run_id,
                        "t_ms": int((time.monotonic() - t0) * 1000),
                        "p": procs,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
            with contextlib.suppress(OSError):
                os.write(fd, line.encode("utf-8"))
            time.sleep(interval_ms / 1000.0)
        wall = time.monotonic() - t0
        run = {
            "v": 1,
            "k": "RUN",
            "run": run_id,
            "root_pid": root_pid,
            "interval_ms": interval_ms,
            "samples_n": n,
            "expected_n": int(wall * 1000 // interval_ms),
            "wall_ms": int(wall * 1000),
            "clk_tck": CLK_TCK,
            "scope": _scope(),
            "psi_us": {
                k: ((_psi(k) - v) if (v is not None and _psi(k) is not None) else None)
                for k, v in psi0.items()
            },
            "unsampled": wall * 1000 < interval_ms,
            "t0_ms": t0_ms,
        }
        with contextlib.suppress(OSError):
            os.write(fd, (json.dumps(run, separators=(",", ":")) + "\n").encode("utf-8"))
        return run
    finally:
        os.close(fd)


# A fixture that spawns bash must NOT be re-exec'd under the profiler's own
# supervisor (BASH_ENV is live on this machine): the tree would gain a
# bashcov-sup layer and every depth assertion shifts by one. Caught by the hook
# battery the first time it ran with profiling on -- the profiler measuring its
# own test. The BASH_ENV file honours WORKLIST_PROFILE=off.
_FIXTURE_ENV = {**os.environ, "WORKLIST_PROFILE": "off"}


def selftest() -> int:
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    bad = 0

    def check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal bad
        print(
            "  %s  %s%s"
            % (
                "PASS" if ok else "FAIL",
                name,
                ("\n        " + detail) if (detail and not ok) else "",
            )
        )
        if not ok:
            bad += 1

    d = Path(tempfile.mkdtemp(prefix="ressample-"))
    out = d / "run.jsonl"
    planted = "sk_test_PLANTEDSECRETLOOKALIKE000000000"
    # A known tree: a bash parent that backgrounds two sleepers and waits. One sleeper
    # is wrapped in `bash -c '...' <token>` so the token lands in that child's argv as
    # $0. The inner bash carries TWO commands on purpose: with one simple command
    # bash execs it and the wrapper never exists (angle 1's exec finding, met here).
    # The first draft put the token after `sleep 1.2`, which is an invalid
    # interval, so that child died instantly and "both children found" could only
    # ever see one -- and the fix then failed to land twice because it pattern-matched
    # code that ruff format had reshaped. This function is replaced whole for that reason.
    child = subprocess.Popen(
        ["bash", "-c", "sleep 1.2 & bash -c 'sleep 1.2; :' %s & wait" % planted],
        env=_FIXTURE_ENV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.3)
        run = watch(child.pid, out, interval_ms=200, run_id="selftest")
        lines = [json.loads(ln) for ln in out.read_text().splitlines() if ln.strip()]
        samples = [ln for ln in lines if ln.get("k") == "S"]
        runs = [ln for ln in lines if ln.get("k") == "RUN"]
        check("a RUN record is written last", len(runs) == 1 and lines[-1]["k"] == "RUN")
        check("samples were taken", len(samples) >= 3, "n=%d" % len(samples))
        check(
            "RUN carries expected_n beside samples_n (anti-vacuity)",
            "expected_n" in run and "samples_n" in run and run["samples_n"] == len(samples),
        )
        first = samples[0]["p"]
        check(
            "the root is sampled with depth 0",
            bool(first) and first[0]["pid"] == child.pid and first[0]["depth"] == 0,
        )
        kids = [p for p in first if p["ppid"] == child.pid]
        check(
            "both backgrounded children are found",
            len(kids) == 2,
            "kids=%s" % [(k["comm"], k["state"]) for k in kids],
        )
        sleepers = [p for p in first if p["comm"] == "sleep"]
        check(
            "both sleepers are reached, one of them a level deeper",
            len(sleepers) == 2 and {p["depth"] for p in sleepers} == {1, 2},
            str([(p["comm"], p["depth"]) for p in sleepers]),
        )
        check(
            "sleepers are SLEEPING on hrtimer_nanosleep (symbolic wchan)",
            all(k["state"] == "S" and k["wchan"] == "hrtimer_nanosleep" for k in sleepers),
            str([(k["state"], k["wchan"]) for k in sleepers]),
        )
        inner = [p for p in kids if p["comm"] == "bash"]
        check(
            "the wrapping bash child is itself DEFERRING in do_wait",
            len(inner) == 1 and inner[0]["wchan"] == "do_wait",
            str([(p["comm"], p["wchan"]) for p in inner]),
        )
        check(
            "the parent is DEFERRING in do_wait (healthy, not a verdict)",
            first[0]["wchan"] == "do_wait",
            str(first[0]["wchan"]),
        )
        blob = out.read_text()
        check("PLANT: a secret-shaped argv never reaches a sample", planted not in blob)
        check(
            "comm is the 15-byte basename only",
            all(len(p["comm"]) <= 15 for s in samples for p in s["p"]),
        )
        child.wait(timeout=5)
        check("a dead root samples to an empty tree, not an error", sample_tree(child.pid) == [])
        quick = subprocess.Popen(["true"], env=_FIXTURE_ENV, stdin=subprocess.DEVNULL)
        quick.wait()
        r2 = watch(quick.pid, d / "quick.jsonl", interval_ms=5000, run_id="quick")
        check(
            "a run shorter than one interval is marked unsampled, not measured as 0",
            r2["unsampled"] is True and r2["samples_n"] == 0,
        )
    finally:
        with contextlib.suppress(Exception):
            child.kill()
        shutil.rmtree(d, ignore_errors=True)
    return bad


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        n = selftest()
        print("%s ressample selftest: %d failure(s)" % ("✓" if n == 0 else "✗", n))
        return 1 if n else 0
    if "--watch" in argv:
        i = argv.index("--watch")
        pid = int(argv[i + 1])
        out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else None
        if out is None:
            print("--watch needs --out <file>", file=sys.stderr)
            return 2
        ms = (
            int(argv[argv.index("--interval-ms") + 1])
            if "--interval-ms" in argv
            else DEFAULT_INTERVAL_MS
        )
        rid = argv[argv.index("--run") + 1] if "--run" in argv else ""
        t0 = int(argv[argv.index("--t0") + 1]) if "--t0" in argv else None
        run = watch(pid, out, interval_ms=ms, run_id=rid, t0_ms=t0)
        print(
            json.dumps(
                {
                    "samples_n": run["samples_n"],
                    "expected_n": run["expected_n"],
                    "unsampled": run["unsampled"],
                }
            )
        )
        return 0
    print(
        "usage: wl_ressample.py --selftest | --watch <pid> --out <file> [--interval-ms N] [--run <id>]",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
