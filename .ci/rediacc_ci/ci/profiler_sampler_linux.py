#!/usr/bin/env python3
# Sample this Linux runner's CPU / RAM / disk / network into a TSV log.
#
# WHY: standard runners are free and unlimited on this public repo, so the cost of a mis-sized job is not money or wall clock, it is core-minutes burned for nothing. A job that uses ~1 core on a 4-vCPU ubuntu-latest VM burns roughly 4x the cores it needs. Deciding which jobs fit ubuntu-slim (1 vCPU / 5 GB / 14 GB disk, hard 15-minute cap) needs measurements, not guesses.
#
# CGROUP-FIRST, deliberately. ubuntu-slim runs in an UNPRIVILEGED CONTAINER, not a VM. Inside a container `nproc` and /proc/meminfo report the HOST, so an advisor fed from /proc would read 4 cores / 16 GB on a 1-core / 5 GB runner and be confidently wrong in the one direction that matters. Every sample therefore carries the tier it was resolved at (CGROUP_V2 | CGROUP_V1 |
# PROC_HOST), and the report refuses to advise from PROC_HOST numbers.
#
# NO FORKS IN THE SAMPLE LOOP. Every reading is a `read < file` builtin plus $(( )) arithmetic; timestamps come from $EPOCHREALTIME, and the inter-sample wait is a `read -t` on a fifo rather than /bin/sleep. On 1 vCPU the fork-free loop costs ~1 ms per sample against 15-30 ms for a $(cat)+awk equivalent, and a profiler that perturbs a 1-core runner is measuring itself. Disk is the
# one exception: `df` is an external command, so it is sampled on a decimated cadence (about once a minute) rather than every tick.
#
# Usage: .ci/scripts/ci/profiler/sampler-linux.sh --out <file> [--interval <sec>] .ci/scripts/ci/profiler/sampler-linux.sh --probe
#
# Optional env (flags win): PROFILER_INTERVAL seconds between samples (default 10) PROFILER_OUT TSV output path PROFILER_RUNNER_LABEL runner label, e.g. ubuntu-slim (default $RUNNER_LABEL)
#   PROFILER_MAX_SECONDS   self-terminate after this long (default 21600 = 6h,
#                          GitHub's own job ceiling; stops an orphan running forever)
# PROFILER_DISK_EVERY_S seconds between `df` calls (default 60)
#   PROFILER_CGROUP_ROOT   cgroup mount to read (default /sys/fs/cgroup; test seam)
#
# Run locally: .ci/scripts/ci/profiler/sampler-linux.sh --probe
#   PROFILER_RUNNER_LABEL=self .ci/scripts/ci/profiler/sampler-linux.sh \
"""Port of `.ci/scripts/ci/profiler/sampler-linux.sh` (627 lines).

THE 39 COMMENT LINES ABOVE ARE THE TWIN'S LINES 2-40, CARRIED BYTE FOR BYTE, and they are not decoration. `usage()` in the twin is `sed -n '2,40p' "$0" | sed 's/^# \\?//'` (`sampler-linux.sh:80`), so `--help` prints the script's OWN first 39 comment lines. A port whose `--help` printed a Python docstring would differ from the twin on its most-read output, so this file reproduces
the mechanism rather than the string: `usage()` below slices lines 2-40 of THIS file and strips the same prefix. `test_help_is_byte_identical` compares the two renderings.

That slice ends mid-continuation, with a dangling `\\` on the last line, because line 41 (`--out /tmp/p.tsv --interval 2 &`) is outside the range. Reproduced, not tidied: tidying it would mean the two `--help` outputs no longer match.

LIVE CALLERS OF THE TWIN, none repointed by this port:
  * `.github/actions/profiler/index.js:32,117` -- the composite action's `main`
    spawns `bash <SAMPLER> --out <tsv> --interval <n>` DETACHED and `unref`s it.
    This is the production path; `.github/actions/setup-workspace/action.yml:72`
    invokes the composite.
  * `.github/workflows/profiler-probe.yml:54` and `:72` -- `--probe`.
  * `.ci/scripts/test/profiler-control.sh:50,121`.
  * `.ci/scripts/test/gates/test-profiler-report.sh:34,398,409,421,478,506` and
    its Python port `.ci/rediacc_ci/tests/gates/test_gate_profiler_report.py:59,703`.

FOUR MEASURED DEFECTS, ALL FIXED IN BOTH SIDES IN LOCKSTEP ON 2026-09-10. Each paragraph below is the record of what was wrong, kept because the measurement is the expensive part and because the differential tests that used to pin the bug now pin the fix. Everything AFTER "PORT NOTES" is still reproduced, not repaired.

(1) A DANGLING VALUE FLAG SPUN FOREVER. `sampler-linux.sh` handled `--out` and
`--interval` with `OUT="${2:-}"; shift 2`. When the flag is the LAST argument,
`shift 2` with `$# == 1` returns non-zero and shifts NOTHING; `set -e` is
deliberately off (`:54-57` explains why), so `while (($# > 0))` never terminated. Measured directly:

    /usr/bin/time -f "%e %U %P" timeout 3 bash .ci/scripts/ci/profiler/sampler-linux.sh --out
    -> wall=3.01 user=3.00 cpu=100%

100% of one core, no output on either stream, no exit. On ubuntu-slim that is the whole machine, and the production caller spawns the sampler `detached: true` with `child.unref()`, so nothing would reap it before the job's 6-hour ceiling. `PROFILER_MAX_SECONDS` could not help: it is evaluated inside the sample loop, which the spin never reached.

BLAST RADIUS, COUNTED NOT ESTIMATED, AND THE FIRST COUNT WAS AN UNDERCOUNT. The twin has 14 real invocation sites (docstrings, this file and the ledgers excluded). TWELVE pass a value after `--out`/`--interval`: `.github/actions/profiler/index.js:117`, `.ci/scripts/test/profiler-control.sh:121`, `.ci/scripts/test/gates/test-profiler-report.sh:398,409,421,478,506` and its Python
port `.ci/rediacc_ci/tests/gates/test_gate_profiler_report.py:548,568,592,656,703`. TWO use `--probe` only, `.github/workflows/profiler-probe.yml:54,72`. ZERO were reachable; the defect was one hand-typed invocation away, and it failed SILENTLY, which is what made it worth fixing rather than noting. (A first pass wrote "8 and 2", having missed the five sites in the gate-test port;
re-derived by enumerating every match rather than by recalling the earlier grep.) Every arm of the loop now consumes at least one argument, and a missing value is the exit 2 every other bad argument already got. `test_a_dangling_value_flag_exits_on_both_sides` pins it.

(2) `--interval 08` KILLED THE SAMPLER. `DISK_EVERY=$(((DISK_EVERY_S + INTERVAL -
1) / INTERVAL))` and `$(( ))` reads a leading `0` as OCTAL. `08` is not a valid octal constant, so bash refused the whole expression, left `DISK_EVERY` unassigned, and the next line died on `set -u`:

    sampler-linux.sh: line 584: 08: value too great for base (error token is "08")
    sampler-linux.sh: line 585: DISK_EVERY: unbound variable
    rc=1, one #META line written, zero samples

`08` and `09` were the only two values that did that. `010` was worse in a quieter way: a VALID octal 8, so the decimation divisor became 8 while `read -t 010` waited 10 real seconds and the `#META` record said `010` -- three different numbers for one flag in one run. Verified individually: `$((010))` is 8, `[ 010 -lt 9 ]` is false (so `test` reads it as decimal 10), and a `read -t
010` on a fifo returned after 10.01s.
Fixed with `INTERVAL=$((10#$INTERVAL))` right after the existing digits-only check.

BLAST RADIUS: `.github/actions/profiler/action.yml:25` declares `interval` with default `'10'`, and the three live callers (`profiler-probe.yml:89,108,127`) all pass `'5'`. Zero were affected, and `interval: '08'` is an entirely ordinary thing to write in YAML.

(3) THE SAME OCTAL TRAP IN `PROFILER_DISK_EVERY_S`, one line down, found by sweeping for the sibling rather than fixing the instance. `is_num 08` is true and `[ 08 -ge 1 ]` is true because `test` parses base 10, so the guard on that line passed `08` through to the same `$(( ))` and produced the same two diagnostics and
the same rc=1. Same fix, `DISK_EVERY_S=$((10#$DISK_EVERY_S))`; that knob keeps its
own convention of falling back to 60 without a word, because a wrong `df` cadence costs a sampling rate and not a runner.

(4) A NON-NUMERIC `PROFILER_MAX_SECONDS` DISABLED THE GUARD IT BELONGS TO. The only use was `[ $(((NOW_US - START_US) / 1000000)) -ge "$MAX_SECONDS" ]`, and `test` answers a non-numeric right-hand side with `[: abc: integer expected` and status 2, which `if` reads as FALSE. So the orphan protection the variable exists for was switched off by the same typo that looks like it would
tighten it. Measured: 3 ticks in 4 seconds, three diagnostics, no stop. Now REJECTED LOUDLY at startup with exit 2, the way `--interval` already was, rather than coerced to the 6-hour default: the line between this file's two conventions is what a wrong value costs, and this one costs a sampler running forever on a runner that has moved on. `sampler-linux.sh` carries the same
argument next to the code, including why the check sits BEFORE the `--probe` branch. The `_test_int` helper that modelled the false comparison was deleted with the bug; a model of a branch that cannot be taken is dead code beside a live one.

`$INTERVAL` USED TO BE ECHOED RAW into the `#META` record (`:528`, `:575`), so `--interval 01` recorded `01`. The first version of this port stored `int(raw)` and wrote `1`; the differential caught it, reading the file did not. That divergence is gone in the other direction as of fix (2): the twin REASSIGNS `$INTERVAL` to the base-10 value, so both sides now record the normalised
number and `test_the_meta_record_carries_the_normalised_interval` is what keeps them together.

PORT NOTES -- the rest of the quirks, each driven before it was written down.

`read -r a b < file` IS NOT `open().readline()`. Three separate behaviours had to be reproduced and each one decides a branch:
  * it returns NON-ZERO when the line is not newline-terminated, INCLUDING for
    an empty file, while still assigning what it read. `detect_cpu_ceiling`'s
    condition is `[ -r "$CG/cpu.max" ] && read -r q p <"$CG/cpu.max"`, so a
    `cpu.max` written without a trailing newline sends the whole detector to the
    `elif`, leaving `CPU_MODE` empty. `_read_fields` returns that `ok` flag.
  * the LAST named variable absorbs the remainder of the line, separators and
    all, after leading and trailing IFS whitespace is stripped.
  * `while read -r k v; do ... done < file` therefore DROPS an unterminated final
    line. `_iter_fields` reproduces it.

A FAILED REDIRECTION PRINTS A bash DIAGNOSTIC AND IS NOT AN ERROR.
`read_mem_bytes:314` guards `$CG/memory.current` with `[ "$MEM_MODE" = "V2" ]`
and NOT with `-r`, so a cgroup tree exposing `memory.max` but not `memory.current` makes real bash write `<path>: line 314: <CG>/memory.current: No such file or directory` to stderr on
EVERY TICK (measured: `bash -c 'read -r p < missing'` -> that text, rc=1). This
port does NOT forge a bash diagnostic carrying the twin's own path and line number; it matches the observable decision (fall through to the next branch) and `test_missing_memory_current_is_a_bash_diagnostic_only` pins the twin's divergence as still real rather than silently fixing it.

`$(( ))` TRUNCATES TOWARD ZERO, `//` FLOORS. `_idiv` is C truncation. Every division in the twin is guarded to non-negative operands today, so the two agree on the real tree; the helper exists so a future negative cannot drift silently.

`is_num` IS `case $1 in '' | *[!0-9]*)`, which rejects `-1`, `+1`, ` 1`, `1.0` and the empty string. cgroup v1 spells "unlimited" as `-1` in `cpu.cfs_quota_us`, and that is exactly why the division at `:160` can never see a negative divisor.

`RUNNER_ENV` IS SANITIZED TO `[a-z-]+` OR THE WHOLE VALUE BECOMES `unknown` (`:218-220`), because it is copied verbatim into a TAB-separated record. Note this rejects `Github-Hosted` and `self_hosted` outright rather than cleaning them.

THE FIFO IS A REAL FIFO. `:553` opens a mkfifo read-write so `read -t` on it never delivers and never EOFs -- a pure-builtin sleep. Reproduced with `os.mkfifo` + `O_RDWR` + `select`, not with `time.sleep`, so the
`SLEEP_MODE=sleep` fallback stays a real branch.

A SIGTERM DOES NOT BREAK THE WAIT, AND THE FIRST VERSION OF THIS PORT ASSUMED IT
DID. The assumption was that bash's `read -t` returns the moment a trapped signal arrives, so the port used `signal.set_wakeup_fd` on a self-pipe to make `select` return instantly. Measured instead of believed, at `--interval 5` with a SIGTERM 1.2s in:

    twin  rc=0  latency=3.80s
    port  rc=0  latency=0.043s   (with the self-pipe)

bash defers the trap until the `read -t` finishes its timeout, so the twin dies one FULL INTERVAL after the signal, not immediately. That is not cosmetic: the production stopper (`.github/actions/profiler/index.js:148-166`) SIGTERMs the sampler, waits, and then SIGKILLs it, annotating the panel with "the sampler had to be SIGKILLed; the final sample may be truncated". A port that
died faster would silently change which of those two notes a job's panel carries. The self-pipe is therefore GONE: plain `select` retries with the RECOMPUTED remaining timeout under PEP 475, which is exactly bash's behaviour, and `test_sigterm_latency_matches_the_twin` measures both sides rather than asserting either.

`EPOCHREALTIME` CANNOT BE ABSENT HERE. `:122-125` refuses bash < 5.0. Python has `time.time()` unconditionally, so that refusal is unreachable in the port and is the one branch with no differential coverage. Named rather than pretended.

Exit: 0 sampling finished / probe done, 2 usage or setup error, 3 HOST_LEAK.
"""

from __future__ import annotations

import contextlib
import errno
import os
import pathlib
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import typing

SELF = pathlib.Path(__file__).resolve()

# ubuntu-slim is 1 vCPU / 5 GB. Anything materially above that on a slim runner means the cgroup read failed open and we are looking at the host.
SLIM_MEM_CEILING = 6 * 1024 * 1024 * 1024
SLIM_CPU_CEILING_MILLI = 1500


# --------------------------------------------------------------------------- The bash builtins this script is built out of ---------------------------------------------------------------------------


def is_num(value: str | None) -> bool:
    """`is_num()` (`sampler-linux.sh:138-143`): non-empty and all ASCII digits.

    Rejects `-1`, `+1`, `1.0`, ` 1` and ``. cgroup v1's "unlimited" is `-1`, so this is the guard that keeps a negative out of every division below.
    """
    if not value:
        return False
    return all("0" <= ch <= "9" for ch in value)


def _idiv(a: int, b: int) -> int:
    """`$(( a / b ))`: C truncation toward zero, not Python's floor."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


class BashArithError(Exception):
    """`$(( ))` refused the expression, e.g. `08` under octal rules.

    bash writes `<script>: line N: 08: value too great for base (error token is "08")`, leaves the target variable UNASSIGNED, and the next expansion of it then dies on `set -u`. Carrying the exception is how the port reproduces that sequence without forging bash's own path and line number.
    """


def _arith(token: str) -> int:
    """A bash NUMERIC CONSTANT, which is not `int()`.

    `$(( ))` reads a leading `0` as OCTAL, `0x` as hex and `base#digits` as that base. `int()` reads everything as decimal, and the difference is not academic here: `--interval 010` makes the twin compute the disk-decimation divisor as 8 while `read -t 010` waits 10 seconds, and `--interval 08` makes it refuse the expression outright. See the module docstring for the measurement
    and the blast radius.
    """
    text = token.strip()
    negative = text.startswith("-")
    if text[:1] in ("+", "-"):
        text = text[1:]
    if not text:
        raise BashArithError(token)
    try:
        if text.lower().startswith("0x"):
            # The WHOLE string, prefix included: `int("0x1f", 16)` is 31. `int(text, 0)` would also accept `0b`/`0o`, which bash does not.
            value = int(text, 16)
        elif "#" in text:
            base, _sep, digits = text.partition("#")
            value = int(digits, int(base))
        elif text.startswith("0") and text != "0":
            value = int(text, 8)
        else:
            value = int(text, 10)
    except ValueError as exc:
        raise BashArithError(token) from exc
    return -value if negative else value


def _split_fields(line: str, count: int) -> list[str]:
    """`read -r a b c` field splitting: the LAST name absorbs the remainder.

    Leading and trailing IFS whitespace is stripped from the line first, then it is split on runs of IFS whitespace at most `count - 1` times.
    """
    parts = line.strip(" \t").split(None, count - 1) if count > 1 else [line.strip(" \t")]
    while len(parts) < count:
        parts.append("")
    return parts


def _read_fields(path: str, count: int) -> tuple[bool, list[str]]:
    """`read -r v1..vN < path`.

    Returns `(ok, fields)`. `ok` is `read`'s exit status: FALSE when the first line is not newline-terminated (an empty file included), even though the fields are still assigned from whatever was read.

    Raises OSError when the redirection itself fails, which is the caller's cue to reproduce bash's "condition is false" rather than to crash.
    """
    with open(path, "rb") as fh:
        raw = fh.readline()
    text = raw.decode("utf-8", errors="surrogateescape")
    ok = text.endswith("\n")
    return ok, _split_fields(text.rstrip("\n"), count)


def _iter_fields(path: str, count: int) -> typing.Iterator[list[str]]:
    """`while read -r v1..vN; do ... done < path`.

    Drops an unterminated final line, exactly as `read` returning non-zero at EOF drops it in the twin.
    """
    with open(path, "rb") as fh:
        for raw in fh:
            text = raw.decode("utf-8", errors="surrogateescape")
            if not text.endswith("\n"):
                return
            yield _split_fields(text[:-1], count)


def usage() -> None:
    """`usage()` (`:79-81`): `sed -n '2,40p' "$0" | sed 's/^# \\?//'`.

    Slices THIS file, not the twin. The 39 lines are carried verbatim at the top precisely so the two renderings are the same bytes.
    """
    lines = SELF.read_text(encoding="utf-8").split("\n")
    for line in lines[1:40]:
        print(re.sub(r"^# ?", "", line))


# --------------------------------------------------------------------------- The sampler ---------------------------------------------------------------------------


class Sampler:
    """One run of the script. Every bash global is an attribute here."""

    def __init__(self, environ: dict[str, str] | None = None) -> None:
        env = os.environ if environ is None else environ
        self.env = env
        # `${VAR:-default}`: exported-but-empty is UNSET.
        self.interval_raw = env.get("PROFILER_INTERVAL") or "10"
        self.out = env.get("PROFILER_OUT") or ""
        self.runner_label = env.get("PROFILER_RUNNER_LABEL") or env.get("RUNNER_LABEL") or "unknown"
        self.max_seconds_raw = env.get("PROFILER_MAX_SECONDS") or "21600"
        # Both of these are re-derived in `parse_args`, which is the only place that has seen argv and is therefore the only place that can validate.
        self.interval = 0
        self.max_seconds = 0
        self.cg = env.get("PROFILER_CGROUP_ROOT") or "/sys/fs/cgroup"
        self.ws_dir = env.get("GITHUB_WORKSPACE") or os.getcwd()
        self.tmp_dir = env.get("RUNNER_TEMP") or "/tmp"
        self.mode = "sample"

        self.cpu_ceil_milli = 0
        self.mem_ceil_bytes = 0
        self.cpu_src = ""  # CGROUP_V2 | CGROUP_V1 | PROC_HOST
        self.mem_src = ""
        self.cpu_mode = ""  # how to read usage each tick
        self.mem_mode = ""
        self.tier = ""
        self.container_hint = "UNKNOWN"
        self.runner_env = ""
        self.host_leak_msg = ""

        self.cpu_usec = 0
        self.mem_bytes = 0
        self.net_rx = 0
        self.net_tx = 0
        self.df_tmp = ""
        self.disk_ws_kb = 0
        self.disk_tmp_kb = 0
        self.df_used = 0
        self.now_us = 0
        self.running = True

    # -- argument parsing (`:83-125`) ---------------------------------------

    def parse_args(self, argv: list[str]) -> int | None:
        """Returns an exit code, or None to carry on.

        EVERY BRANCH CONSUMES AT LEAST ONE ARGUMENT, which is the loop's variant and the fix of 2026-09-10. Both sides used to reproduce a non-terminating `while (($# > 0))`: `shift 2` with one argument left returns non-zero and shifts nothing, `set -e` is off in the twin by design, so `--out` as the final argument burned 100% of a core with no output and no exit. See the module
        docstring for the measurement.
        """
        args = list(argv)
        while len(args) > 0:
            head = args[0]
            if head == "--out":
                if len(args) < 2:
                    print("sampler-linux.sh: --out requires a value", file=sys.stderr, flush=True)
                    return 2
                self.out = args[1]
                del args[:2]
            elif head == "--interval":
                if len(args) < 2:
                    print(
                        "sampler-linux.sh: --interval requires a value", file=sys.stderr, flush=True
                    )
                    return 2
                self.interval_raw = args[1]
                del args[:2]
            elif head == "--probe":
                self.mode = "probe"
                del args[:1]
            elif head in ("--help", "-h"):
                usage()
                return 0
            else:
                print("sampler-linux.sh: unknown argument: %s" % head, file=sys.stderr, flush=True)
                return 2

        raw = self.interval_raw
        if not is_num(raw):
            print(
                "sampler-linux.sh: --interval must be a whole number of seconds, got '%s'" % raw,
                file=sys.stderr,
                flush=True,
            )
            return 2
        # `INTERVAL=$((10#$INTERVAL))`, the fix of 2026-09-10. `08` and `09` pass
        # `is_num` and are INVALID OCTAL to every `$(( ))` below, and `010` was three different numbers in one run (8 to the arithmetic, 10 to `read -t`, `010` in the #META record). The twin now REASSIGNS `$INTERVAL`, so the raw string stops existing there and `interval_raw` has to follow it: #META
        # records the normalised value on both sides now, and the `>= 1` message
        # below reports `0` for an input of `00`, which is what it is.
        self.interval = int(raw, 10)
        self.interval_raw = str(self.interval)
        if self.interval < 1:
            print(
                "sampler-linux.sh: --interval must be >= 1, got '%s'" % self.interval_raw,
                file=sys.stderr,
                flush=True,
            )
            return 2

        # PROFILER_MAX_SECONDS IS THE SELF-TERMINATION GUARD and until 2026-09-10 it had no validation at all. Its only use is `[ <elapsed> -ge "$MAX_SECONDS" ]`, and `test` answers a non-numeric right-hand side with `[: abc: integer expected` and status 2, which `if` reads as FALSE -- so the orphan guard was switched OFF by the same typo that looks like it would tighten it.
        # Rejected
        # loudly rather than coerced, and validated before the `--probe` branch;
        # `sampler-linux.sh` carries the full argument for both choices.
        raw = self.max_seconds_raw
        if not is_num(raw):
            print(
                "sampler-linux.sh: PROFILER_MAX_SECONDS must be a whole number of seconds, "
                "got '%s'" % raw,
                file=sys.stderr,
                flush=True,
            )
            return 2
        self.max_seconds = int(raw, 10)
        self.max_seconds_raw = str(self.max_seconds)

        # `:122-125` refuses bash < 5.0 for want of $EPOCHREALTIME. Unreachable here: Python always has a clock. Named in the docstring.
        return None

    # -- ceiling resolution (`:145-197`) -------------------------------------

    def detect_cpu_ceiling(self) -> None:
        cpu_max = os.path.join(self.cg, "cpu.max")
        v1_quota = os.path.join(self.cg, "cpu", "cpu.cfs_quota_us")
        v1_period = os.path.join(self.cg, "cpu", "cpu.cfs_period_us")

        if os.access(cpu_max, os.R_OK):
            try:
                ok, (q, p) = _read_fields(cpu_max, 2)
            except OSError:
                ok, q, p = False, "", ""
            if ok:
                self.cpu_mode = "V2"
                if is_num(q) and is_num(p) and int(p) > 0:
                    self.cpu_ceil_milli = _idiv(int(q) * 1000, int(p))
                    self.cpu_src = "CGROUP_V2"
                    return
                # "max <period>": the cgroup exists but imposes no quota, so the real ceiling is the host's core count. That is a HOST reading.
        elif os.access(v1_quota, os.R_OK):
            try:
                ok, (q,) = _read_fields(v1_quota, 1)
            except OSError:
                ok, q = False, ""
            if ok:
                self.cpu_mode = "V1"
                try:
                    ok2, (p,) = _read_fields(v1_period, 1)
                except OSError:
                    # bash prints its own redirection diagnostic here; see the module docstring for why this port does not forge one.
                    ok2, p = False, ""
                if ok2 and is_num(q) and is_num(p) and int(p) > 0:
                    self.cpu_ceil_milli = _idiv(int(q) * 1000, int(p))
                    self.cpu_src = "CGROUP_V1"
                    return

        n = self._nproc()
        if not is_num(n):
            n = "0"
        count = int(n)
        if count <= 0:
            count = 1
        self.cpu_ceil_milli = count * 1000
        self.cpu_src = "PROC_HOST"

    @staticmethod
    def _nproc() -> str:
        """`n="$(nproc 2>/dev/null || echo 0)"`.

        Command substitution strips trailing newlines, and a missing binary yields the literal `0`.
        """
        try:
            proc = subprocess.run(
                ["nproc"], capture_output=True, text=True, check=False, timeout=30
            )
        except (OSError, subprocess.SubprocessError):
            return "0"
        if proc.returncode != 0:
            return "0"
        return proc.stdout.rstrip("\n")

    def detect_mem_ceiling(self) -> None:
        mem_max = os.path.join(self.cg, "memory.max")
        v1_limit = os.path.join(self.cg, "memory", "memory.limit_in_bytes")

        if os.access(mem_max, os.R_OK):
            try:
                ok, (v,) = _read_fields(mem_max, 1)
            except OSError:
                ok, v = False, ""
            if ok:
                self.mem_mode = "V2"
                if is_num(v) and int(v) > 0:
                    self.mem_ceil_bytes = int(v)
                    self.mem_src = "CGROUP_V2"
                    return
        elif os.access(v1_limit, os.R_OK):
            try:
                ok, (v,) = _read_fields(v1_limit, 1)
            except OSError:
                ok, v = False, ""
            if ok:
                self.mem_mode = "V1"
                # cgroup v1 spells "unlimited" as a number near 2^63, not a word.
                if is_num(v) and 0 < int(v) < 4611686018427387904:
                    self.mem_ceil_bytes = int(v)
                    self.mem_src = "CGROUP_V1"
                    return

        try:
            for k, v, _rest in _iter_fields("/proc/meminfo", 3):
                if k == "MemTotal:":
                    if is_num(v):
                        self.mem_ceil_bytes = int(v) * 1024
                    break
        except OSError:
            pass
        self.mem_src = "PROC_HOST"

    def detect_container(self) -> None:
        """`detect_container()` (`:223-247`).

        Note the middle branch's `else: return 0`: an UNREADABLE `/proc/1/comm` stops the fingerprint at UNKNOWN and never consults `/proc/1/cgroup`.
        """
        if os.path.exists("/.dockerenv"):
            self.container_hint = "CONTAINER"
            return
        comm_ok = False
        v = ""
        if os.access("/proc/1/comm", os.R_OK):
            try:
                comm_ok, (v,) = _read_fields("/proc/1/comm", 1)
            except OSError:
                comm_ok = False
        if comm_ok:
            if v not in ("systemd", "init"):
                self.container_hint = "CONTAINER"
                return
        else:
            return
        if os.access("/proc/1/cgroup", os.R_OK):
            try:
                cg_ok, (v,) = _read_fields("/proc/1/cgroup", 1)
            except OSError:
                cg_ok = False
            if cg_ok:
                if v in ("0::/", "0::/init.scope"):
                    self.container_hint = "HOST"
                else:
                    self.container_hint = "CONTAINER"

    def resolve(self) -> None:
        """`:217-262`: RUNNER_ENV sanitisation, the three detectors, the tier."""
        runner_env = self.env.get("RUNNER_ENVIRONMENT", "")
        # `case $RUNNER_ENV in '' | *[!a-z-]*) RUNNER_ENV=unknown`. Whole-value
        # rejection, not cleaning: `Github-Hosted` becomes `unknown`.
        if not runner_env or not all(("a" <= c <= "z") or c == "-" for c in runner_env):
            runner_env = "unknown"
        self.runner_env = runner_env

        self.detect_cpu_ceiling()
        self.detect_mem_ceiling()
        self.detect_container()

        # The tier is the WORSE of the two sources.
        if self.cpu_src == "PROC_HOST" or self.mem_src == "PROC_HOST":
            self.tier = "PROC_HOST"
        elif self.cpu_src == "CGROUP_V1" or self.mem_src == "CGROUP_V1":
            self.tier = "CGROUP_V1"
        else:
            self.tier = "CGROUP_V2"

    # -- HOST_LEAK (`:270-280`) ---------------------------------------------

    def check_host_leak(self) -> bool:
        """True when clean. Sets `host_leak_msg` only when it is not."""
        if "slim" not in self.runner_label:
            return True
        if (
            self.mem_ceil_bytes <= SLIM_MEM_CEILING
            and self.cpu_ceil_milli <= SLIM_CPU_CEILING_MILLI
        ):
            return True
        self.host_leak_msg = (
            "HOST_LEAK on runner label '%s': detected memory ceiling %s bytes "
            "(limit %s) and CPU quota %s millicores (limit %s) via tier %s. A slim "
            "runner is 1 vCPU / 5 GB; these are host numbers, so every conclusion "
            "drawn from them would be wrong."
            % (
                self.runner_label,
                self.mem_ceil_bytes,
                SLIM_MEM_CEILING,
                self.cpu_ceil_milli,
                SLIM_CPU_CEILING_MILLI,
                self.tier,
            )
        )
        return False

    # -- per-sample readings (`:286-419`) ------------------------------------

    def read_cpu_usec(self) -> bool:
        if self.cpu_mode == "V2":
            try:
                for k, v in _iter_fields(os.path.join(self.cg, "cpu.stat"), 2):
                    if k == "usage_usec":
                        self.cpu_usec = int(v) if is_num(v) else self._bash_int(v)
                        return True
            except OSError:
                pass
        elif self.cpu_mode == "V1":
            usage = os.path.join(self.cg, "cpuacct", "cpuacct.usage")
            if os.access(usage, os.R_OK):
                try:
                    ok, (ns,) = _read_fields(usage, 1)
                except OSError:
                    ok, ns = False, ""
                if ok and is_num(ns):
                    self.cpu_usec = _idiv(int(ns), 1000)
                    return True
        # /proc/stat is in USER_HZ jiffies; 100 Hz is the value every Ubuntu runner kernel ships, and this branch only feeds a PROC_HOST report.
        try:
            ok, fields = _read_fields("/proc/stat", 10)
        except OSError:
            return False
        if not ok:
            return False
        _cpu, u, n, s, _idle, _iowait, irq, sirq, steal, _rest = fields
        self.cpu_usec = (
            self._bash_int(u)
            + self._bash_int(n)
            + self._bash_int(s)
            + self._bash_int(irq)
            + self._bash_int(sirq)
            + self._bash_int(steal)
        ) * 10000
        return True

    @staticmethod
    def _bash_int(token: str) -> int:
        """`$(( x ))` on an arbitrary word: empty is 0, non-numeric is a bash error.

        The twin never reaches the error case on a real /proc, and neither side has a defined answer for it, so the port takes the benign reading.
        """
        try:
            return int(token)
        except ValueError:
            return 0

    def read_mem_bytes(self) -> bool:
        if self.mem_mode == "V2":
            cur_ok, cur = self._try_read_one(os.path.join(self.cg, "memory.current"))
            if cur_ok and is_num(cur):
                inactive = "0"
                try:
                    for k, v, _rest in _iter_fields(os.path.join(self.cg, "memory.stat"), 3):
                        if k == "inactive_file":
                            inactive = v
                            break
                except OSError:
                    pass
                if not is_num(inactive):
                    inactive = "0"
                c, i = int(cur), int(inactive)
                self.mem_bytes = c - i if c > i else c
                return True
        if self.mem_mode == "V1":
            cur_ok, cur = self._try_read_one(
                os.path.join(self.cg, "memory", "memory.usage_in_bytes")
            )
            if cur_ok and is_num(cur):
                inactive = "0"
                try:
                    for k, v, _rest in _iter_fields(
                        os.path.join(self.cg, "memory", "memory.stat"), 3
                    ):
                        if k == "total_inactive_file":
                            inactive = v
                            break
                except OSError:
                    pass
                if not is_num(inactive):
                    inactive = "0"
                c, i = int(cur), int(inactive)
                self.mem_bytes = c - i if c > i else c
                return True

        total = "0"
        avail = "0"
        try:
            for k, v, _rest in _iter_fields("/proc/meminfo", 3):
                if k == "MemTotal:":
                    total = v
                elif k == "MemAvailable:":
                    avail = v
                    break
        except OSError:
            return False
        if not (is_num(total) and is_num(avail)):
            return False
        self.mem_bytes = (int(total) - int(avail)) * 1024
        return True

    @staticmethod
    def _try_read_one(path: str) -> tuple[bool, str]:
        """One `read -r v < path` whose redirection may fail.

        ONE open, not two: the twin reads the file once per tick, and a second open could see a different value on a live /sys or /proc file.
        """
        try:
            ok, fields = _read_fields(path, 1)
        except OSError:
            # bash writes its own diagnostic naming the twin's path and line; see the module docstring. The DECISION -- condition false -- matches.
            return False, ""
        return ok, fields[0]

    def read_net_bytes(self) -> bool:
        self.net_rx = 0
        self.net_tx = 0
        try:
            for (line,) in _iter_fields("/proc/net/dev", 1):
                if ":" not in line:
                    continue
                name, _sep, rest = line.partition(":")
                # The kernel prints "%6s:%8llu", so once rx_bytes exceeds 8 digits the colon is glued to the number and a naive field split reads "eth0:1234" as the interface name.
                name = name.replace(" ", "")
                if name in ("", "lo", "Inter", "face"):
                    continue
                parts = rest.split()
                if len(parts) >= 9 and is_num(parts[0]) and is_num(parts[8]):
                    self.net_rx += int(parts[0])
                    self.net_tx += int(parts[8])
        except OSError:
            pass
        return True

    def df_used_kb(self, target: str) -> None:
        self.df_used = 0
        if not self.df_tmp:
            return
        try:
            proc = subprocess.run(
                ["df", "-P", "-k", target],
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            return
        try:
            with open(self.df_tmp, "w", encoding="utf-8") as fh:
                fh.write(proc.stdout)
        except OSError:
            return
        if proc.returncode != 0:
            return
        try:
            rows = list(_iter_fields(self.df_tmp, 4))
        except OSError:
            return
        if len(rows) < 2:
            return
        used = rows[1][2]
        if is_num(used):
            self.df_used = int(used)

    def read_disk_kb(self) -> None:
        self.df_used_kb(self.ws_dir)
        self.disk_ws_kb = self.df_used
        self.df_used_kb(self.tmp_dir)
        self.disk_tmp_kb = self.df_used

    def now(self) -> None:
        """`now_us()` (`:409-419`), out of `$EPOCHREALTIME`.

        `LC_ALL=C` is exported at `:63` so the radix character is a dot; the port
        never renders through a locale at all.
        """
        self.now_us = int(time.time() * 1000000)

    # -- --probe (`:425-513`) ------------------------------------------------

    def probe_file(self, path: str) -> str:
        if os.access(path, os.R_OK):
            try:
                ok, (v,) = _read_fields(path, 1)
            except OSError:
                return "(unreadable)"
            if ok:
                return v
        return "(unreadable)"

    @staticmethod
    def _command_v(name: str) -> str:
        found = shutil.which(name)
        return found or "(missing)"

    def run_probe(self, emit: typing.Callable[[str], None]) -> None:
        mt = self.probe_file("/proc/meminfo")

        emit("## Runner probe: %s" % self.runner_label)
        emit("")
        emit("**Runner label:** %s" % self.runner_label)
        emit(
            "**Resolved tier:** %s (cpu via %s, memory via %s)"
            % (self.tier, self.cpu_src, self.mem_src)
        )
        if os.path.isdir(self.cg) and os.access(self.cg, os.R_OK):
            emit("**Cgroup mount:** %s readable" % self.cg)
        else:
            emit("**Cgroup mount:** %s NOT readable" % self.cg)
        if os.path.exists(os.path.join(self.cg, "cgroup.controllers")):
            emit("**Cgroup version:** v2 (cgroup.controllers present)")
        elif os.path.isdir(os.path.join(self.cg, "cpu")) or os.path.isdir(
            os.path.join(self.cg, "memory")
        ):
            emit("**Cgroup version:** v1 (per-controller directories)")
        else:
            emit("**Cgroup version:** none visible")
        emit("**cpu.max:** %s" % self.probe_file(os.path.join(self.cg, "cpu.max")))
        emit(
            "**cpu.cfs_quota_us:** %s"
            % self.probe_file(os.path.join(self.cg, "cpu", "cpu.cfs_quota_us"))
        )
        emit("**memory.max:** %s" % self.probe_file(os.path.join(self.cg, "memory.max")))
        emit(
            "**memory.limit_in_bytes:** %s"
            % self.probe_file(os.path.join(self.cg, "memory", "memory.limit_in_bytes"))
        )
        emit("**memory.current:** %s" % self.probe_file(os.path.join(self.cg, "memory.current")))
        nproc = self._nproc_or_missing()
        emit("**nproc:** %s" % nproc)
        emit("**/proc/meminfo MemTotal:** %s" % mt)
        emit("**Detected CPU ceiling:** %s millicores" % self.cpu_ceil_milli)
        emit("**Detected RAM ceiling:** %s bytes" % self.mem_ceil_bytes)
        emit(
            "**RUNNER_ENVIRONMENT:** %s (recorded as: %s)"
            % (self.env.get("RUNNER_ENVIRONMENT") or "(unset)", self.runner_env)
        )
        emit("**/.dockerenv:** %s" % ("present" if os.path.exists("/.dockerenv") else "absent"))
        emit("**/proc/1/cgroup:** %s" % self.probe_file("/proc/1/cgroup"))
        emit("**/proc/1/comm:** %s" % self.probe_file("/proc/1/comm"))
        emit("**awk:** %s" % self._command_v("awk"))
        emit("**node:** %s" % self._command_v("node"))
        emit("**df:** %s" % self._command_v("df"))
        emit("**bash:** %s" % (self.env.get("BASH_VERSION") or "unknown"))

        handle, self.df_tmp = self._mktemp()
        if handle is not None:
            os.close(handle)
        self.read_disk_kb()
        emit("**df workspace used:** %s KiB (%s)" % (self.disk_ws_kb, self.ws_dir))
        emit("**df runner temp used:** %s KiB (%s)" % (self.disk_tmp_kb, self.tmp_dir))

        # 100 iterations of the real per-tick work, disk excluded.
        self.now()
        t0 = self.now_us
        for _ in range(100):
            self.read_cpu_usec()
            self.read_mem_bytes()
            self.read_net_bytes()
        self.now()
        t1 = self.now_us
        emit(
            "**Per-sample cost:** %s us over 100 iterations (cpu+mem+net, no disk)"
            % _idiv(t1 - t0, 100)
        )

        if self.check_host_leak():
            emit("**Host leak check:** clean")
        else:
            emit("**Host leak check:** WOULD FAIL - %s" % self.host_leak_msg)
        if self.df_tmp:
            with contextlib.suppress(OSError):
                os.unlink(self.df_tmp)

    def _nproc_or_missing(self) -> str:
        """`$(nproc 2>/dev/null || echo '(missing)')`, distinct from `_nproc`."""
        try:
            proc = subprocess.run(
                ["nproc"], capture_output=True, text=True, check=False, timeout=30
            )
        except (OSError, subprocess.SubprocessError):
            return "(missing)"
        if proc.returncode != 0:
            return "(missing)"
        return proc.stdout.rstrip("\n")

    @staticmethod
    def _mktemp() -> tuple[int | None, str]:
        try:
            fd, path = tempfile.mkstemp()
        except OSError:
            return None, ""
        return fd, path

    # -- sampling (`:519-627`) ----------------------------------------------

    def run(self, argv: list[str]) -> int:
        rc = self.parse_args(argv)
        if rc is not None:
            return rc

        self.resolve()

        if self.mode == "probe":
            summary = self.env.get("GITHUB_STEP_SUMMARY") or ""
            if summary:
                # `run_probe | tee -a "$GITHUB_STEP_SUMMARY"`.
                sink = open(summary, "a", encoding="utf-8")  # noqa: SIM115
                try:

                    def emit(line: str) -> None:
                        print(line, flush=True)
                        sink.write(line + "\n")
                        sink.flush()

                    self.run_probe(emit)
                finally:
                    sink.close()
            else:
                self.run_probe(lambda line: print(line, flush=True))
            return 0

        if not self.out:
            print(
                "sampler-linux.sh: --out <file> (or PROFILER_OUT) is required",
                file=sys.stderr,
                flush=True,
            )
            return 2

        self.host_leak_msg = ""
        if not self.check_host_leak():
            # `: >"$OUT" || true` then `printf ... >>"$OUT"`. Both may fail with a bash diagnostic; the exit code is 3 either way.
            try:
                with open(self.out, "w", encoding="utf-8"):
                    pass
            except OSError:
                pass
            try:
                with open(self.out, "a", encoding="utf-8") as fh:
                    fh.write(
                        "#META\tHOST_LEAK\t%s\t%s\t%s\t0\t%s\t%s\t%s\t%s\t%s\n"
                        % (
                            self.cpu_ceil_milli,
                            self.mem_ceil_bytes,
                            # THE RAW STRING, not the parsed int. The twin never converts `$INTERVAL`, so `--interval 01` records `01`. Caught by the differential, not by reading.
                            self.interval_raw,
                            self.runner_label,
                            self.cpu_src,
                            self.mem_src,
                            self.container_hint,
                            self.runner_env,
                        )
                    )
            except OSError:
                pass
            print("sampler-linux.sh: %s" % self.host_leak_msg, file=sys.stderr, flush=True)
            return 3

        try:
            work_dir = tempfile.mkdtemp()
        except OSError:
            print("sampler-linux.sh: cannot create work dir", file=sys.stderr, flush=True)
            return 2

        try:
            return self._sample_loop(work_dir)
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)  # `trap cleanup EXIT`

    def _sample_loop(self, work_dir: str) -> int:
        self.df_tmp = os.path.join(work_dir, "df")
        fifo_path = os.path.join(work_dir, "tick")

        self.running = True

        def stop(_signum: int, _frame: object) -> None:
            self.running = False

        previous = {}
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(OSError, ValueError):  # non-main thread
                previous[sig] = signal.signal(sig, stop)

        # NO WAKEUP FD, DELIBERATELY. bash defers a trap until `read -t` has run out its timeout, so the twin keeps waiting after a SIGTERM and dies at the end of the interval. PEP 475 makes plain `select` do the same thing: the handler runs, then the call is retried with the remaining timeout. Measured, both sides; see the module docstring.

        # Fork-free wait: a fifo held open read-write never delivers and never EOFs, so a timed read on it is a pure sleep.
        sleep_mode = "fifo"
        fifo_fd = -1
        try:
            os.mkfifo(fifo_path)
            fifo_fd = os.open(fifo_path, os.O_RDWR | os.O_NONBLOCK)
        except OSError:
            sleep_mode = "sleep"
            if fifo_fd >= 0:
                os.close(fifo_fd)
                fifo_fd = -1

        def tick_wait() -> None:
            watch = [fifo_fd] if sleep_mode == "fifo" else []
            try:
                select.select(watch, [], [], self.interval)
            except OSError as exc:
                if exc.errno != errno.EINTR:  # pragma: no cover - defensive
                    raise

        try:
            self.now()
            start_us = self.now_us
            try:
                with open(self.out, "w", encoding="utf-8"):
                    pass
            except OSError:
                print("sampler-linux.sh: cannot write %s" % self.out, file=sys.stderr, flush=True)
                return 2

            out_fh = open(self.out, "a", encoding="utf-8")  # noqa: SIM115 - the twin's `exec 8>>`
            try:
                out_fh.write(
                    "#META\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n"
                    % (
                        self.tier,
                        self.cpu_ceil_milli,
                        self.mem_ceil_bytes,
                        self.interval_raw,  # the raw string; see the HOST_LEAK record
                        _idiv(start_us, 1000),
                        self.runner_label,
                        self.cpu_src,
                        self.mem_src,
                        self.container_hint,
                        self.runner_env,
                    )
                )
                out_fh.flush()

                # Disk about once a minute, and always on the first tick so the table is never blank for short jobs.
                disk_every_s_raw = self.env.get("PROFILER_DISK_EVERY_S") or "60"
                if is_num(disk_every_s_raw) and int(disk_every_s_raw, 10) >= 1:
                    # `DISK_EVERY_S=$((10#$DISK_EVERY_S))`. THE SAME OCTAL TRAP AS
                    # --interval, one line down, found on 2026-09-10 by sweeping for the sibling rather than fixing the instance: `is_num 08` is true and `[ 08 -ge 1 ]` is true because `test` parses base 10, so `08` reached `$(( ))` intact and killed the sampler the same way. This knob keeps its silent fallback -- a wrong `df` cadence costs a sampling rate, not a runner -- and only
                    # gains the base.
                    disk_every_s = int(disk_every_s_raw, 10)
                else:
                    disk_every_s = 60
                # `$(( ))`, NOT `int()`, still models the twin, but `$INTERVAL` is normalised in `parse_args` now and `$DISK_EVERY_S` just above, so neither can hand `$(( ))` an expression it refuses. The octal death (`08: value too great for base`, then `DISK_EVERY: unbound variable`
                # from `set -u`, one #META line written and zero samples) is fixed on
                # both sides; `_arith` stays as the model of the operator.
                interval_arith = _arith(self.interval_raw)
                disk_every = _idiv(disk_every_s + interval_arith - 1, interval_arith)
                disk_every = max(disk_every, 1)

                if not self.read_cpu_usec():
                    self.cpu_usec = 0
                prev_cpu_usec = self.cpu_usec
                prev_us = start_us
                tick = 0

                # `[ ... -ge "$MAX_SECONDS" ]`, and the right-hand side can no longer be refused: `parse_args` rejects a non-numeric PROFILER_MAX_SECONDS at startup as of 2026-09-10. Before that, `test` printed `[: abc: integer expected` and evaluated FALSE every tick, so the orphan guard was OFF -- measured, 3 ticks in 4 seconds with three diagnostics and no stop. The `_test_int`
                # helper that modelled the refusal went with the bug: a model of a branch that cannot be taken is dead code beside a live one.
                max_seconds = self.max_seconds

                while self.running:
                    tick_wait()
                    if not self.running:
                        break
                    self.now()
                    if not self.read_cpu_usec():
                        self.cpu_usec = prev_cpu_usec
                    if not self.read_mem_bytes():
                        self.mem_bytes = 0
                    self.read_net_bytes()

                    wall_us = self.now_us - prev_us
                    cpu_delta = self.cpu_usec - prev_cpu_usec
                    if wall_us > 0 and cpu_delta >= 0:
                        cpu_milli = _idiv(cpu_delta * 1000, wall_us)
                    else:
                        cpu_milli = 0

                    if tick % disk_every == 0:
                        self.read_disk_kb()

                    out_fh.write(
                        "S\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n"
                        % (
                            _idiv(self.now_us, 1000),
                            cpu_milli,
                            self.mem_bytes,
                            self.net_rx,
                            self.net_tx,
                            self.disk_ws_kb,
                            self.disk_tmp_kb,
                        )
                    )
                    out_fh.flush()

                    prev_cpu_usec = self.cpu_usec
                    prev_us = self.now_us
                    tick += 1

                    if _idiv(self.now_us - start_us, 1000000) >= max_seconds:
                        print(
                            "sampler-linux.sh: reached PROFILER_MAX_SECONDS=%s, stopping"
                            % self.max_seconds_raw,
                            file=sys.stderr,
                            flush=True,
                        )
                        break
            finally:
                out_fh.close()  # `exec 8>&-`
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            if fifo_fd >= 0:
                os.close(fifo_fd)
        return 0


def main(argv: list[str]) -> int:
    # --- carried verbatim from sampler-linux.sh, lines 60-63 ------------------- EPOCHREALTIME renders its fraction with the LOCALE's radix character; under a
    # comma locale "1690000000,123456" would break the ${x%.*} split below and every
    # timestamp with it.
    # (the twin's next line is `export LC_ALL=C`; this is it.)
    os.environ["LC_ALL"] = "C"
    return Sampler().run(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
