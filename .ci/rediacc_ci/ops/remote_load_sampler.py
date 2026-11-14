"""Load and iowait sampler for one machine, wrapped around one command, with a peak report and stated exit codes.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.remote_load_sampler --machine hostinger --config eu-bench \\
        -- ./rdc.sh backup download mail@hostinger --to /tmp/rdc-bdl --config eu-bench

WHY IT EXISTS (PLAN-backup-local-image.md L2 step 3). The plan asks for load and iowait "before, during and after" a download on a production machine. The script PLAN-snapshot-read-io-cap.md L1 names, /tmp/scr/readcap.sh, was never committed, and read_cap_seed.py is tied to `backup snapshot`. This module samples around any command and reuses read_cap_seed's sample command, parser and figures, so both tools read the machine the same way: `rdc --config <name> term connect <machine> -c` over /proc, a delta between two samples per figure.

PHASES. `baseline` is --baseline-s of samples before the command starts. `during` is one sample per --interval-s until the command exits. `after` is --after-s of samples once it has exited. Without a command, `during` lasts --duration-s. Each sample is an SSH round trip, so the real spacing can exceed the interval.

RULES. Peak 1-minute load during the run is held to the baseline mean plus --max-load-delta (default 3.5, the operator ruling of 2026-10-29 in PLAN-snapshot-read-io-cap.md L1). Peak iowait during the run is held to --max-iowait (default 15). A flag set to a negative number turns its rule off. The `after` peaks are reported and never judged.

EXIT. The wrapped command's own rc when it is non-zero (128+N for a signal). Otherwise 3 for a sampling failure (no baseline sample, no sample during the run, or any sample that could not be read), 4 when a threshold was exceeded, 2 on bad arguments, and 0 otherwise. Every figure is printed before the exit code is chosen.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol, TextIO

from rediacc_ci.ops import read_cap_seed as rcs

INTERVAL_S = 10.0
BASELINE_S = 60.0
AFTER_S = 60.0
MAX_LOAD_DELTA = 3.5
MAX_IOWAIT = 15.0

EXIT_USAGE = 2
EXIT_SAMPLING = 3
EXIT_THRESHOLD = 4


class Process(Protocol):
    def wait(self, timeout: float | None = None) -> int: ...


Spawner = Callable[[Sequence[str]], Process]


def real_spawner(argv: Sequence[str]) -> Process:
    # stdin is /dev/null on purpose (an open handle that always reads EOF): the wrapped command runs unattended, so a prompt on stdin (a confirmation, a passphrase) gets EOF instead of hanging the sampler.
    return subprocess.Popen(list(argv), stdin=subprocess.DEVNULL)


@dataclass
class Deps:
    runner: rcs.Runner = rcs.real_runner
    spawner: Spawner = real_spawner
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


@dataclass
class Phase:
    name: str
    loads: list[float] = field(default_factory=list)
    iowaits: list[float] = field(default_factory=list)
    busys: list[float] = field(default_factory=list)
    failed: int = 0

    @property
    def samples(self) -> int:
        return len(self.loads)

    def peak_load(self) -> float | None:
        return max(self.loads) if self.loads else None

    def peak_iowait(self) -> float | None:
        return max(self.iowaits) if self.iowaits else None

    def peak_busy(self) -> float | None:
        return max(self.busys) if self.busys else None

    def mean_load(self) -> float | None:
        return sum(self.loads) / len(self.loads) if self.loads else None


class Sampler:
    def __init__(self, deps: Deps, rdc: str, config: str, machine: str, out: TextIO) -> None:
        self.deps, self.rdc, self.config, self.machine, self.out = deps, rdc, config, machine, out
        self.prev: rcs.Sample | None = None

    def take(self, phase: Phase) -> None:
        rc, stdout, stderr = self.deps.runner(
            rcs.sample_argv(self.rdc, self.config, self.machine), rcs.SAMPLE_TIMEOUT_S
        )
        sample = rcs.parse_sample(stdout) if rc == 0 else None
        if sample is None:
            phase.failed += 1
            tail = " | ".join(stderr.strip().splitlines()[-2:])
            print(
                "sample failed (%s): rc=%d %s" % (phase.name, rc, tail), file=self.out, flush=True
            )
            return
        previous, self.prev = self.prev, sample
        figure = rcs.interval_figures(previous, sample) if previous else None
        # The first sample has no predecessor, so it carries load only.
        phase.loads.append(sample.load)
        detail = ""
        if figure is not None:
            phase.iowaits.append(figure.iowait)
            phase.busys.append(figure.busy)
            detail = " iowait=%.0f busy=%.0f" % (figure.iowait, figure.busy)
        print("%s load=%.2f%s" % (phase.name, sample.load, detail), file=self.out, flush=True)

    def span(self, phase: Phase, seconds: float, interval: float) -> None:
        began = self.deps.clock()
        tick = 0
        while True:
            self.take(phase)
            tick += 1
            due = began + tick * interval
            if due - began > seconds:
                return
            self.deps.sleep(max(0.0, due - self.deps.clock()))


def _fmt(value: float | None, spec: str = "%.2f") -> str:
    return "none" if value is None else spec % value


def evaluate(
    baseline: Phase,
    during: Phase,
    after: Phase,
    command_rc: int | None,
    max_delta: float,
    max_iowait: float,
) -> tuple[int, list[str]]:
    """(exit code, the reasons it was chosen)."""
    reasons: list[str] = []
    if command_rc:
        return (128 - command_rc if command_rc < 0 else command_rc), ["command rc=%d" % command_rc]
    reasons.extend(
        "%s: %d sample(s) unreadable" % (phase.name, phase.failed)
        for phase in (baseline, during, after)
        if phase.failed
    )
    if not baseline.samples:
        reasons.append("no baseline sample")
    if not during.samples:
        reasons.append("no sample during the run")
    if reasons:
        return EXIT_SAMPLING, reasons
    base = baseline.mean_load()
    peak = during.peak_load()
    if max_delta >= 0 and base is not None and peak is not None and peak > base + max_delta:
        reasons.append("peak load %.2f exceeds baseline %.2f + %.2f" % (peak, base, max_delta))
    wa = during.peak_iowait()
    if max_iowait >= 0 and wa is not None and wa > max_iowait:
        reasons.append("peak iowait %.0f exceeds %.0f" % (wa, max_iowait))
    return (EXIT_THRESHOLD if reasons else 0), reasons


def report(
    baseline: Phase,
    during: Phase,
    after: Phase,
    seconds: float,
    command_rc: int | None,
    code: int,
    reasons: list[str],
) -> str:
    return " ".join(
        [
            "baseload=%s" % _fmt(baseline.mean_load()),
            "peakload=%s" % _fmt(during.peak_load()),
            "peakwa=%s" % _fmt(during.peak_iowait(), "%.0f"),
            "peakbusy=%s" % _fmt(during.peak_busy(), "%.0f"),
            "afterpeakload=%s" % _fmt(after.peak_load()),
            "afterpeakwa=%s" % _fmt(after.peak_iowait(), "%.0f"),
            "samples=%d/%d/%d" % (baseline.samples, during.samples, after.samples),
            "seconds=%.0f" % seconds,
            "cmdrc=%s" % ("none" if command_rc is None else command_rc),
            "rc=%d" % code,
            "reasons=%s" % ("; ".join(reasons).replace(" ", "_") or "none"),
        ]
    )


@dataclass(frozen=True)
class Plan:
    rdc: str
    config: str
    machine: str
    command: Sequence[str]
    baseline_s: float
    interval_s: float
    after_s: float
    duration_s: float
    max_delta: float
    max_iowait: float


def run(deps: Deps, plan: Plan, out: TextIO) -> int:
    sampler = Sampler(deps, plan.rdc, plan.config, plan.machine, out)
    baseline, during, after = Phase("baseline"), Phase("during"), Phase("after")
    sampler.span(baseline, plan.baseline_s, plan.interval_s)
    began = deps.clock()
    command_rc: int | None = None
    if plan.command:
        proc = deps.spawner(plan.command)
        while command_rc is None:
            sampler.take(during)
            try:
                command_rc = proc.wait(timeout=plan.interval_s)
            except subprocess.TimeoutExpired:
                continue
    else:
        sampler.span(during, plan.duration_s, plan.interval_s)
    seconds = deps.clock() - began
    if plan.after_s > 0:  # --after-s 0 asks for no after phase: no sample, so no failed one either
        sampler.span(after, plan.after_s, plan.interval_s)
    code, reasons = evaluate(baseline, during, after, command_rc, plan.max_delta, plan.max_iowait)
    print(report(baseline, during, after, seconds, command_rc, code, reasons), file=out, flush=True)
    return code


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="remote_load_sampler", description=(__doc__ or "").splitlines()[0]
    )
    p.add_argument("--machine", required=True)
    p.add_argument("--config", required=True, help="no default: a bare rdc targets production")
    p.add_argument("--rdc", default="./rdc.sh")
    p.add_argument("--baseline-s", type=float, default=BASELINE_S)
    p.add_argument("--interval-s", type=float, default=INTERVAL_S)
    p.add_argument("--after-s", type=float, default=AFTER_S)
    p.add_argument(
        "--duration-s", type=float, default=0.0, help="sampling time when no command is given"
    )
    p.add_argument("--max-load-delta", type=float, default=MAX_LOAD_DELTA)
    p.add_argument("--max-iowait", type=float, default=MAX_IOWAIT)
    p.add_argument("command", nargs=argparse.REMAINDER, help="after `--`: the command to wrap")
    return p


def main(
    argv: Sequence[str] | None = None, deps: Deps | None = None, out: TextIO | None = None
) -> int:
    out = out or sys.stdout
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else 0
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not rcs.NAME.fullmatch(args.machine) or not rcs.NAME.fullmatch(args.config):
        print("bad --machine or --config", file=out)
        return EXIT_USAGE
    if (
        args.interval_s <= 0
        or args.baseline_s < 0
        or args.after_s < 0
        or (not command and args.duration_s <= 0)
    ):
        print(
            "need a positive --interval-s, non-negative phases, and a command or --duration-s",
            file=out,
        )
        return EXIT_USAGE
    plan = Plan(
        args.rdc,
        args.config,
        args.machine,
        command,
        args.baseline_s,
        args.interval_s,
        args.after_s,
        args.duration_s,
        args.max_load_delta,
        args.max_iowait,
    )
    return run(deps or Deps(), plan, out)


if __name__ == "__main__":
    sys.exit(main())
