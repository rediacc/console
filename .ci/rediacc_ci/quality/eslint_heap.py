#!/usr/bin/env python3
"""Run eslint with a heap and a worker count the machine can actually give it.

Ported from `scripts/eslint-heap.sh` (PLAN-retire-bash-oracles B5, W10). Usage (stdlib only, so no PYTHONPATH):

    python3 .ci/rediacc_ci/quality/eslint_heap.py <requested-mb> <eslint args...>

---- gate ----
id: check:lint
run: npm run check:lint:cli && npm run check:lint:web && npm run check:lint:tooling && npm run check:lint:account
step: Lint
needs: node
---- end gate ----

THE HEADER STAYS ON THE PARENT, and the parent does not name this file. `check:lint` used to be ONE eslint process over every root: 166.5s measured on 2026-09-06, a single indivisible unit that pinned one scheduler slot for the whole of it while other workers idled. It is now four scripts (`check:lint:cli`, `check:lint:web`, `check:lint:tooling`, `check:lint:account`), each invoking THIS runner over a disjoint slice of the roots, with `check:lint` as their aggregate. Measured the same day: the four run concurrently in 87.5s wall, about 1.9x. A header block declares exactly one gate, so it declares the one the workflow has a step for; the four shards are registered in the manifest against that same `Lint` step. `run:` must stay byte equal to the `check:lint` key in package.json.

WHAT HOLDS THE SHARDS HONEST is `.ci/scripts/quality/check_lint_scope_coverage.py`, which follows the `npm run` links out of `check:lint` and unions the eslint roots it finds. It names this file by `ESLINT_RUNNER`, and reads the first two tokens after it as the runner and the heap, so the roots stay positional.

WHY THE HEAP IS CLAMPED. `check:lint` hard-coded `--max-old-space-size=8192`. On CI that is right and this keeps it. On a 6.6 GB workstation with no swap it is a guaranteed kill: node grows past what the kernel can back, the OOM killer takes it, and eslint dies with exit 137 after roughly three minutes. Measured 2026-08-26, two things made that worse than a plain failure: it looks like it might work (it burns three minutes first and reports a signal that is easy to misread, and a wrapper pipeline around it exits 0 unless PIPESTATUS is checked), and while it climbs it starves everything else on the box (the Stop hook's judge timed out at 240s in that window and was reported as broken; it answers in 6.5s when memory is free).

THE CEILING IS UNCHANGED. The heap is never raised above the request, so CI keeps what it always got. It only clamps DOWNWARD on a host that cannot honour the request.

KEYED ON MemAvailable, NOT MemTotal. The first version used 65% of TOTAL, which on a 6654MB box with ~2900MB resident is 4325MB, still more than the kernel could hand out, so it clamped, announced that it had protected the run, and was OOM-killed anyway. A clamp that still dies is worse than no clamp. MemAvailable is the kernel's own estimate of what a new allocation can get WITHOUT swapping; MemFree excludes reclaimable page cache and would clamp far harder than needed.

WORKERS. eslint 9.39 lints on one thread unless given `--concurrency`, so a run granted many cores used about 1.4 of them. No static count (operator ruling 2026-10-05): the width is the runner's grant, `CI_RUNNER_CORES`, and with no grant eslint keeps its own default. Measured 2026-10-05 on packages/cli (24 cores, a loaded box): no flag 106s / 4.4GB peak RSS; 2 workers 84s / 7.4GB; 4 workers 56s / 12GB; 8 workers 187s / 21GB and then an OOM kill (137) on the retry. Each worker costs about 3GB, so the grant alone is not a safe width: it is capped by what MemAvailable can back after the reserve. `ESLINT_WORKER_MB` tunes that estimate. A caller that passes its own `--concurrency` keeps it.

EXIT STATUS IS ESLINT'S. The child inherits stdin, stdout and stderr and its status is returned unchanged; a child killed by a signal is reported the way a shell reports it (128 plus the signal), so an OOM kill still reads 137 and is never swallowed.

PORT NOTES (Rule T, each a deliberate delta from the bash with a test in `test_quality_eslint_heap.py`):

  * NODE_OPTIONS is EXTENDED, not replaced. The bash ran `env NODE_OPTIONS=--max-old-space-size=N npx eslint`, which discarded whatever the caller had already put in NODE_OPTIONS (a `--require` hook, a source-map flag). The heap flag is now appended, so a caller's options survive and the heap flag still wins as the last occurrence.
  * A non-numeric `ESLINT_HEAP_RESERVE_MB` or `ESLINT_WORKER_MB` is a named refusal with exit 2. Bash arithmetic read a word as a variable name (empty, so zero), which silently turned a typo into a zero reserve and an unclamped heap.
  * A non-numeric requested heap is the same refusal; bash passed the word through to node.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

DEFAULT_RESERVE_MB = 1200
DEFAULT_WORKER_MB = 3000
HEAP_FLOOR_MB = 1024
MEMINFO = pathlib.Path("/proc/meminfo")
EXIT_MISSING_HEAP = 1
EXIT_USAGE = 2
EXIT_NOT_FOUND = 127
SIGNAL_BASE = 128


class UsageError(Exception):
    """The invocation or its environment is not one this runner can act on."""

    def __init__(self, message: str, code: int = EXIT_USAGE) -> None:
        super().__init__(message)
        self.code = code


def available_mb(meminfo: pathlib.Path = MEMINFO) -> int | None:
    """MemAvailable in MB, or None when the host does not say."""
    try:
        text = meminfo.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            fields = line.split()
            if len(fields) >= 2 and fields[1].isdigit():
                return int(fields[1]) // 1024
            return None
    return None


def _int_env(env: dict[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    if not raw.isdigit():
        raise UsageError(
            "eslint-heap: %s must be a whole number of megabytes, got %r" % (name, raw)
        )
    return int(raw)


def plan_heap(requested_mb: int, avail_mb: int | None, reserve_mb: int) -> tuple[int, str | None]:
    """The heap to use and the notice to print when it was clamped. Never above the request."""
    if avail_mb is None or avail_mb <= 0:
        return requested_mb, None
    cap = avail_mb - reserve_mb
    if cap >= requested_mb:
        return requested_mb, None
    cap = max(cap, HEAP_FLOOR_MB)
    note = (
        "eslint-heap: %dMB available; clamping the requested %dMB heap to %dMB (reserving %dMB) "
        "so eslint is not OOM-killed. CI is unaffected -- the request is never raised."
        % (avail_mb, requested_mb, cap, reserve_mb)
    )
    return cap, note


def plan_workers(
    args: list[str],
    env: dict[str, str],
    avail_mb: int | None,
    reserve_mb: int,
) -> tuple[list[str], str | None]:
    """The `--concurrency` argument to add (possibly none) and the notice to print."""
    if any(a.startswith("--concurrency") for a in args):
        return [], None
    grant_raw = env.get("CI_RUNNER_CORES", "")
    if not grant_raw.isdigit() or int(grant_raw) <= 1:
        return [], None
    grant = int(grant_raw)
    workers = grant
    note = None
    if avail_mb is not None and avail_mb > 0:
        worker_mb = _int_env(env, "ESLINT_WORKER_MB", DEFAULT_WORKER_MB)
        if worker_mb == 0:
            raise UsageError("eslint-heap: ESLINT_WORKER_MB must be above zero")
        # Truncation toward zero, as the shell's integer division does: a negative budget is zero workers, not minus one.
        budget = avail_mb - reserve_mb
        mem_workers = -(-budget // worker_mb) if budget < 0 else budget // worker_mb
        if mem_workers < workers:
            note = (
                "eslint-heap: %dMB available; capping eslint workers from the granted %d to %d "
                "(about %dMB each)." % (avail_mb, grant, max(mem_workers, 1), worker_mb)
            )
            workers = mem_workers
    if workers > 1:
        return ["--concurrency=%d" % workers], note
    return [], note


def node_options(existing: str | None, heap_mb: int) -> str:
    """The caller's NODE_OPTIONS with the heap flag appended, so the heap flag is the last word."""
    flag = "--max-old-space-size=%d" % heap_mb
    return "%s %s" % (existing.strip(), flag) if existing and existing.strip() else flag


def plan(
    argv: list[str], env: dict[str, str], avail_mb: int | None
) -> tuple[list[str], dict[str, str], list[str]]:
    """Everything the run needs: (command, child environment, notices for stderr)."""
    if not argv or argv[0] == "":
        raise UsageError("eslint-heap: requested heap in MB is required", EXIT_MISSING_HEAP)
    if not argv[0].isdigit():
        raise UsageError(
            "eslint-heap: requested heap must be a whole number of MB, got %r" % argv[0]
        )
    requested = int(argv[0])
    eslint_args = argv[1:]
    reserve = _int_env(env, "ESLINT_HEAP_RESERVE_MB", DEFAULT_RESERVE_MB)
    heap, heap_note = plan_heap(requested, avail_mb, reserve)
    conc, conc_note = plan_workers(eslint_args, env, avail_mb, reserve)
    child = dict(env)
    child["NODE_OPTIONS"] = node_options(env.get("NODE_OPTIONS"), heap)
    notes = [n for n in (heap_note, conc_note) if n]
    return ["npx", "eslint", *conc, *eslint_args], child, notes


def exit_status(returncode: int) -> int:
    """A shell's view of a child status: a signal death is 128 plus the signal."""
    return SIGNAL_BASE - returncode if returncode < 0 else returncode


def main(argv: list[str]) -> int:
    try:
        cmd, child, notes = plan(argv, dict(os.environ), available_mb())
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    for note in notes:
        print(note, file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        proc = subprocess.run(cmd, env=child, check=False)
    except OSError as exc:
        print("eslint-heap: cannot run %s: %s" % (cmd[0], exc.strerror), file=sys.stderr)
        return EXIT_NOT_FOUND
    return exit_status(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
