#!/usr/bin/env python3
"""Drive a KNOWN workload past the sampler and check that the numbers come back.

Port of the retired `.ci/scripts/test/profiler-control.sh` (PLAN-retire-bash-oracles B2), an operator-run control: nothing in CI runs it, because its four phases take about three minutes and need a quiet runner.

    PYTHONPATH=.ci python3 -m rediacc_ci.ci.profiler_control [--interval <sec>] [--keep]

It runs `rediacc_ci.ci.profiler_sampler_linux` by path, the module the bash reached through the `.ci/scripts/ci/profiler/sampler_linux.py` forwarder. The phases, the tolerances and the exit codes are the bash's; the one addition is that `--interval` must be a whole number of seconds, where the bash handed any word to `sleep` and to shell arithmetic.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

SELF = "profiler-control"

SAMPLER = pathlib.Path(__file__).resolve().parent / "profiler_sampler_linux.py"

HELP_TEXT = """\
Drive a KNOWN workload past the sampler and check that the numbers come back.

WHY: every other test in this tree feeds the aggregator synthetic samples, so
nothing else proves that the sampler reads the machine correctly. A sampler
that returns plausible-looking garbage passes every unit test and then moves a
job onto a runner that cannot hold it. This is the control: four phases whose
answers are known before the run starts.

  1. BUSY   30s of exactly one spinning core   expect +1.00 +/- 0.15 cores over idle
  2. IDLE   30s of nothing                     expect mean < 0.25 cores
  3. ALLOC  hold 512 MiB ANONYMOUS             expect a 400-640 MiB step
  4. DISK   write then delete 1 GiB            expect ~1 GiB +/- 15%

BUSY is a DELTA over IDLE rather than an absolute, and at PROC_HOST tier the
three CPU/RAM phases are SKIPPED: without a cgroup the sampler reads the whole
machine. That case exits 2, INCONCLUSIVE, which is neither green nor red. Disk
keeps its verdict at every tier.

Usage:
  PYTHONPATH=.ci python3 -m rediacc_ci.ci.profiler_control [--interval <sec>] [--keep]

Optional env:
  PROFILER_CONTROL_DIR   where the 1 GiB file is written (default the
                         workspace, since that is the filesystem `df` watches)

Exit: 0 every judged phase within tolerance, 1 any phase outside it,
      2 setup error OR inconclusive (PROC_HOST tier).
"""

BUSY_S = 30
IDLE_S = 30
ALLOC_S = 30
# Long enough that a decimated `df` tick lands inside the phase.
DISK_S = 75


def parse_args(argv: list[str]) -> tuple[int, bool] | int:
    """`(interval, keep)`, or an exit code. Every arm consumes at least one argument, so `--interval` as the last word is a loud exit, never a spin."""
    interval, keep = 2, False
    args = list(argv)
    while args:
        word = args[0]
        if word == "--interval":
            if len(args) < 2:
                print("%s: --interval requires a value" % SELF, file=sys.stderr)
                return 2
            if not args[1].isdigit() or int(args[1]) < 1:
                print(
                    "%s: --interval must be a whole number of seconds, got %r" % (SELF, args[1]),
                    file=sys.stderr,
                )
                return 2
            interval = int(args[1])
            args = args[2:]
        elif word == "--keep":
            keep = True
            args = args[1:]
        elif word in ("--help", "-h"):
            sys.stdout.write(HELP_TEXT)
            return 0
        else:
            print("%s: unknown argument: %s" % (SELF, word), file=sys.stderr)
            return 2
    return interval, keep


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def evaluate(
    samples: list[str], marks: list[tuple[str, int, int]], interval: int
) -> tuple[int, list[str]]:
    """The bash's awk program: per-phase statistics over the trimmed window, then the four verdicts. Returns `(exit code, report lines)`."""
    tier = ""
    t: list[int] = []
    cpu: list[float] = []
    mem: list[float] = []
    ws: list[float] = []
    base_mem = 0.0
    base_ws = 0.0
    for line in samples:
        fields = line.rstrip("\n").split("\t")
        if fields[0] == "#META":
            tier = fields[1] if len(fields) > 1 else ""
        elif fields[0] == "S" and len(fields) >= 7:
            t.append(int(float(fields[1] or 0)))
            cpu.append(float(fields[2] or 0))
            mem.append(float(fields[3] or 0))
            ws.append(float(fields[6] or 0))
            if base_mem == 0 or mem[-1] < base_mem:
                base_mem = mem[-1]
            if ws[-1] > 0 and (base_ws == 0 or ws[-1] < base_ws):
                base_ws = ws[-1]
    report: list[str] = []
    if len(t) < 8:
        return 1, ["FAIL setup: only %d samples collected" % len(t)]
    lead = interval * 1000
    stats: dict[str, tuple[int, float, float, float]] = {}
    for name, start, end in marks:
        lo, hi = start + lead, end - lead
        inside = [i for i in range(len(t)) if lo <= t[i] <= hi]
        count = len(inside)
        mean_cpu = (sum(cpu[i] for i in inside) / count) / 1000 if count else 0.0
        max_mem = max((mem[i] for i in inside), default=0.0)
        max_ws = max((ws[i] for i in inside), default=0.0)
        stats[name] = (count, mean_cpu, (max_mem - base_mem) / 1048576, (max_ws - base_ws) / 1024)
    host_tier = tier == "PROC_HOST"
    bad = skipped = 0
    for name, _start, _end in marks:
        count, mean_cpu, mem_mib, ws_mib = stats[name]
        if count == 0:
            report.append("FAIL %s: no samples inside the phase window" % name)
            bad += 1
            continue
        ok = True
        if name == "BUSY":
            delta = mean_cpu - stats["IDLE"][1]
            if host_tier:
                skipped, verdict = skipped + 1, "SKIP"
            else:
                ok = 0.85 <= delta <= 1.15
                verdict = "PASS" if ok else "FAIL"
            report.append(
                "%s BUSY: +%.2f cores over idle (%.2f busy, %.2f idle) across %d samples (expect 1.00 +/- 0.15)"
                % (verdict, delta, mean_cpu, stats["IDLE"][1], count)
            )
        elif name == "IDLE":
            if host_tier:
                skipped, verdict = skipped + 1, "SKIP"
            else:
                ok = mean_cpu < 0.25
                verdict = "PASS" if ok else "FAIL"
            report.append(
                "%s IDLE: mean %.2f cores across %d samples (expect < 0.25)"
                % (verdict, mean_cpu, count)
            )
        elif name == "ALLOC":
            if host_tier:
                skipped, verdict = skipped + 1, "SKIP"
            else:
                ok = 400 <= mem_mib <= 640
                verdict = "PASS" if ok else "FAIL"
            report.append(
                "%s ALLOC: +%.2f MiB above baseline across %d samples (expect 400-640)"
                % (verdict, mem_mib, count)
            )
        elif name == "DISK":
            ok = 870 <= ws_mib <= 1178
            report.append(
                "%s DISK: +%.2f MiB above baseline across %d samples (expect 870-1178)"
                % ("PASS" if ok else "FAIL", ws_mib, count)
            )
        if not ok:
            bad += 1
    report.append("tier: %s, samples: %d" % (tier, len(t)))
    if bad:
        return 1, report
    if skipped:
        report += [
            "CONTROL INCONCLUSIVE: %d phase(s) were skipped because this run is at PROC_HOST tier."
            % skipped,
            "CPU and RAM here describe the whole machine, not the workload. Run this on a runner",
            "with a real cgroup quota (ubuntu-slim, or any container) for a verdict on those three.",
        ]
        return 2, report
    return 0, report


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is not None and proc.poll() is None:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=30)


def main(argv: list[str]) -> int:
    parsed = parse_args(argv)
    if isinstance(parsed, int):
        return parsed
    interval, keep = parsed
    if not SAMPLER.is_file():
        print("%s: sampler not found at %s" % (SELF, SAMPLER), file=sys.stderr)
        return 2
    work = pathlib.Path(tempfile.mkdtemp())
    data_dir = pathlib.Path(
        os.environ.get("PROFILER_CONTROL_DIR") or os.environ.get("GITHUB_WORKSPACE") or work
    )
    tsv = work / "samples.tsv"
    blob = data_dir / (".profiler-control-blob.%d" % os.getpid())
    marks: list[tuple[str, int, int]] = []
    sampler = busy = None
    try:
        print("%s: sampling every %ds into %s" % (SELF, interval, tsv), flush=True)
        env = dict(os.environ, PROFILER_DISK_EVERY_S="10", PROFILER_RUNNER_LABEL="control")
        sampler = subprocess.Popen(
            [sys.executable, str(SAMPLER), "--out", str(tsv), "--interval", str(interval)], env=env
        )
        time.sleep(interval * 2)

        print("%s: phase 1 BUSY (%ds)" % (SELF, BUSY_S), flush=True)
        start = now_ms()
        busy = subprocess.Popen([sys.executable, "-c", "while True:\n    pass\n"])
        time.sleep(BUSY_S)
        _stop(busy)
        busy = None
        marks.append(("BUSY", start, now_ms()))

        print("%s: phase 2 IDLE (%ds)" % (SELF, IDLE_S), flush=True)
        start = now_ms()
        time.sleep(IDLE_S)
        marks.append(("IDLE", start, now_ms()))

        print("%s: phase 3 ALLOC 512 MiB anonymous (%ds)" % (SELF, ALLOC_S), flush=True)
        start = now_ms()
        # 512 one-MiB bytearrays: anonymous heap, which is what moves memory.current the way an OOM does (page cache would not).
        hold = [bytearray(b"x" * 1048576) for _ in range(512)]
        time.sleep(ALLOC_S)
        marks.append(("ALLOC", start, now_ms()))
        del hold

        print("%s: phase 4 DISK 1 GiB (%ds)" % (SELF, DISK_S), flush=True)
        start = now_ms()
        try:
            with open(blob, "wb") as fh:
                chunk = b"\0" * 1048576
                fh.writelines(chunk for _ in range(1024))
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            print("%s: writing %s failed: %s" % (SELF, blob, exc), file=sys.stderr)
            return 2
        time.sleep(DISK_S)
        marks.append(("DISK", start, now_ms()))
        blob.unlink(missing_ok=True)

        _stop(sampler)
        sampler = None
        samples = tsv.read_text(encoding="utf-8").splitlines() if tsv.is_file() else []
        rc, report = evaluate(samples, marks, interval)
        for line in report:
            print(line)
        return rc
    finally:
        _stop(busy)
        _stop(sampler)
        blob.unlink(missing_ok=True)
        if keep:
            print("kept: %s" % work)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
