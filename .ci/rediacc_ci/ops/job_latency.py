"""Wall-time latency of one rdc command over N runs, and the delta between two result files.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.job_latency --rdc ./rdc.sh --config eu-bench \
        --runs 20 --out before.json -- repo list -m hostinger
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.job_latency --compare before.json after.json

WHY IT EXISTS (agent/plans/PLAN-detached-jobs.md, J23). The budget is p50 plus 500 ms and p95 plus 1 s per short command; L3a measures the baseline and L3b the result with this script.

RUN. Each run is `<rdc> --config <name> [--debug] <rdc args>`, timed with a monotonic clock around the child process. Output: `runs=N p50_ms=X p95_ms=X max_ms=X`, with percentiles by nearest rank. With `--debug` the runs pass `--debug` to rdc, and every `rediacc.job.start_latency_ms` value a run prints (as `name=12.5`, `name: 12.5` or `"name":12.5`, on stdout or stderr) is collected; the line `start_latency_ms samples=N p50_ms=X p95_ms=X max_ms=X` follows. `--out <file>` writes the same numbers and every sample as JSON.

COMPARE. `--compare before.json after.json` prints `metric before after delta` for p50, p95 and max wall time (and the start latency when both files carry it), the delta being after minus before.

EXIT. 0 printed; 2 when any run exits non-zero (its rc and the tail of its stderr are named; no result is written or printed), on a missing, unreadable or incomplete result file, an unwritable `--out`, or on bad arguments (nothing is printed when the write fails). A result file is never written for a failed run.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

ATTRIBUTE = "rediacc.job.start_latency_ms"
_START = re.compile(re.escape(ATTRIBUTE) + r"""["']?\s*[=:]\s*["']?(-?\d+(?:\.\d+)?)""")
KEYS = ("p50", "p95", "max")

# (argv) -> (returncode, stdout, stderr)
Runner = Callable[[Sequence[str]], "tuple[int, str, str]"]


class LatencyError(Exception):
    pass


def real_runner(argv: Sequence[str]) -> tuple[int, str, str]:
    proc = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile; ValueError on an empty list."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[rank - 1]


def summarize(values: Sequence[float]) -> dict[str, float]:
    return {
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values),
    }


def measure(
    rdc: str,
    config: str,
    rdc_args: Sequence[str],
    runs: int,
    *,
    debug: bool = False,
    runner: Runner = real_runner,
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    argv = [rdc, "--config", config, *(["--debug"] if debug else []), *rdc_args]
    wall_ms: list[float] = []
    starts: list[float] = []
    for index in range(1, runs + 1):
        began = clock()
        rc, stdout, stderr = runner(argv)
        wall_ms.append((clock() - began) * 1000.0)
        if rc != 0:
            tail = " | ".join(stderr.strip().splitlines()[-3:])
            raise LatencyError("run %d of %d exited %d: %s" % (index, runs, rc, tail))
        if debug:
            starts.extend(float(m) for m in _START.findall(stdout + "\n" + stderr))
    result: dict = {
        "command": argv,
        "runs": runs,
        "wall_ms": wall_ms,
        "wall": summarize(wall_ms),
    }
    if starts:
        result["start_latency_ms"] = starts
        result["start_latency"] = summarize(starts)
    return result


def format_result(result: dict) -> list[str]:
    wall = result["wall"]
    lines = [
        "runs=%d p50_ms=%.1f p95_ms=%.1f max_ms=%.1f"
        % (result["runs"], wall["p50"], wall["p95"], wall["max"])
    ]
    if "start_latency" in result:
        s = result["start_latency"]
        lines.append(
            "start_latency_ms samples=%d p50_ms=%.1f p95_ms=%.1f max_ms=%.1f"
            % (len(result["start_latency_ms"]), s["p50"], s["p95"], s["max"])
        )
    return lines


def _load(path: str) -> dict:
    try:
        data = json.loads(Path(path).read_text())
        sections = ["wall"] + (["start_latency"] if "start_latency" in data else [])
        for section in sections:
            for key in KEYS:
                float(data[section][key])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise LatencyError("cannot read result file %s: %s" % (path, exc)) from None
    return data


def compare(before_path: str, after_path: str) -> list[str]:
    before, after = _load(before_path), _load(after_path)
    lines: list[str] = []
    pairs = [("wall", before["wall"], after["wall"])]
    if "start_latency" in before and "start_latency" in after:
        pairs.append(("start_latency", before["start_latency"], after["start_latency"]))
    for label, old, new in pairs:
        lines.extend(
            "%s.%s before_ms=%.1f after_ms=%.1f delta_ms=%+.1f"
            % (label, key, old[key], new[key], new[key] - old[key])
            for key in KEYS
        )
    return lines


def main(
    argv: list[str] | None = None,
    *,
    runner: Runner = real_runner,
    clock: Callable[[], float] = time.monotonic,
    out=None,
) -> int:
    out = out or sys.stdout
    parser = argparse.ArgumentParser(prog="job_latency", description=__doc__.split("\n")[0])
    parser.add_argument("--rdc")
    parser.add_argument("--config")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--out")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    parser.add_argument("rdc_args", nargs="*")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    try:
        if args.compare:
            for line in compare(*args.compare):
                print(line, file=out)
            return 0
        if not args.rdc or not args.config or not args.rdc_args or args.runs < 1:
            print(
                "job_latency: need --rdc, --config, --runs >= 1 and the rdc args after `--`",
                file=sys.stderr,
            )
            return 2
        result = measure(
            args.rdc,
            args.config,
            args.rdc_args,
            args.runs,
            debug=args.debug,
            runner=runner,
            clock=clock,
        )
    except LatencyError as exc:
        print("job_latency: %s" % exc, file=sys.stderr)
        return 2
    if args.out:
        try:
            Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        except OSError as exc:
            print("job_latency: cannot write %s: %s" % (args.out, exc), file=sys.stderr)
            return 2
    for line in format_result(result):
        print(line, file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
