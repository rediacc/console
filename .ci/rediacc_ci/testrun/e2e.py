"""Port of `.ci/scripts/test/run-e2e.sh`: drive `npx playwright test` in `packages/e2e-tests`, optionally one leg of a shard manifest, optionally under the zero-skip gate.

THE COMMAND LINES ARE THE TWIN'S. Both modes (a plain run, and a shard leg collapsed into ONE playwright invocation so `globalSetup`'s full VM reset is paid once) build the same argv in the same order; `build_plain_command` and `build_shard_command` are pure so a differential compares them against what the bash twin hands a fake `npx`.

Deliberate differences from the twin (Rule T), each with a test that fails on the bash behaviour:

  1. UNKNOWN ARGUMENTS WERE IGNORED. `--fail-on-skp` ran the suite with the zero-skip gate OFF and exited 0. An unknown flag, a stray positional and a value flag with no value are refused with exit 2.
  2. A VALUE FLAG SWALLOWED THE NEXT FLAG'S VALUE. After `--workers --headed` the twin kept waiting for a value and took the next bare word as the worker count. A token starting with `--` never counts as a value here.
  3. SHARD MODE DROPPED OPTIONS SILENTLY. `--config`, `--filter`, `--grep-invert`, `--test`, `--headed`, `--debug` and `--ui` were parsed and then not used when `--shard-manifest` was given, so a leg ran a different selection than the one asked for. They are refused together with `--shard-manifest`, and `--also` is refused without it.
  4. THE LOG FILE LEAKED. The twin tee'd the whole run into a bare `mktemp` file and removed it on the success paths only, so every early `exit 1` (a bad manifest, an unknown bucket) left one in /tmp. The run is scanned line by line as it streams and no file exists.
"""

import dataclasses
import os
import re
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.core import common
from rediacc_ci.testrun import shard

E2E_TESTS_DIR = "packages/e2e-tests"

# The three describe groups `13-postgres-fork-isolation` splits into, keyed as the shard manifest's `#<bucket>` suffix. Kept verbatim from the twin.
SHARD_GREP_BUCKETS = {
    "part1": "PostgreSQL Data Persistence @bridge @integration|Repository Fork Data Inheritance @bridge @integration",
    "part2": "Multiple Fork Independence @bridge @integration|Fork Data Integrity @bridge @integration",
    "part3": "Large Data Volume Fork @bridge @integration|Service Restart Persistence @bridge @integration",
}

USAGE = (
    "usage: run-e2e.sh [--workers N] [--config FILE] [--filter|--grep PATTERN] [--grep-invert PATTERN] [--test FILE]... "
    "[--headed] [--debug] [--ui] [--fail-on-skip] [--shard-manifest PATH --shard I/N [--also A,B]]"
)

VALUE_FLAGS = {
    "--workers": "workers",
    "--config": "config",
    "--filter": "filter",
    "--grep": "filter",
    "--grep-invert": "grep_invert",
    "--test": "test",
    "--shard-manifest": "shard_manifest",
    "--shard": "shard",
    "--also": "also",
}
BOOL_FLAGS = {
    "--headed": "headed",
    "--debug": "debug",
    "--ui": "ui",
    "--fail-on-skip": "fail_on_skip",
}
SHARD_INCOMPATIBLE = ("config", "filter", "grep_invert", "test", "headed", "debug", "ui")
SHARD_INCOMPATIBLE_FLAGS = (
    "--config",
    "--filter/--grep",
    "--grep-invert",
    "--test",
    "--headed",
    "--debug",
    "--ui",
)

JS_ESCAPE = re.compile(r"[.*+?^${}()|\[\]\\]")


class UsageError(Exception):
    """Bad command line. Exit 2."""


class PairError(UsageError):
    """`--shard-manifest` and `--shard` given alone. The twin's one exit-1 argument refusal, kept as it was: message only, no usage text."""


class UnitIdError(shard.ShardError):
    """A manifest id this runner cannot map to a playwright selection. Logged with the error glyph, as the twin did."""


@dataclasses.dataclass
class Options:
    workers: str = ""
    config: str = ""
    filter: str = ""
    grep_invert: str = ""
    test: list[str] = dataclasses.field(default_factory=list)
    headed: bool = False
    debug: bool = False
    ui: bool = False
    fail_on_skip: bool = False
    shard_manifest: str = ""
    shard: str = ""
    also: str = ""
    given: set[str] = dataclasses.field(default_factory=set)


def parse(argv: list[str]) -> Options:
    opts = Options()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in BOOL_FLAGS:
            setattr(opts, BOOL_FLAGS[arg], True)
            opts.given.add(BOOL_FLAGS[arg])
            i += 1
        elif arg in VALUE_FLAGS:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise UsageError(f"{arg} needs a value")
            key = VALUE_FLAGS[arg]
            if key == "test":
                opts.test.append(argv[i + 1])
            else:
                setattr(opts, key, argv[i + 1])
            opts.given.add(key)
            i += 2
        else:
            raise UsageError(f"unknown argument: {arg}")
    if bool(opts.shard_manifest) != bool(opts.shard):
        raise PairError("--shard-manifest and --shard must both be given, or neither")
    if opts.shard_manifest:
        for key, flag in zip(SHARD_INCOMPATIBLE, SHARD_INCOMPATIBLE_FLAGS, strict=True):
            if key in opts.given:
                raise UsageError(
                    f"{flag} cannot be combined with --shard-manifest (a leg runs exactly its manifest files)"
                )
    elif opts.also:
        raise UsageError("--also needs --shard-manifest")
    return opts


def js_escape(text: str) -> str:
    """The twin's `escapeRe`: `s.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&")`. `re.escape` escapes more characters and is not interchangeable."""
    return JS_ESCAPE.sub(lambda m: "\\" + m.group(0), text)


def split_leg(ids: list[str]) -> tuple[list[str], list[str], list[str]]:
    """`(plain files, bucket files, bucket greps)` for a leg's unit ids."""
    plain: list[str] = []
    bucket_files: list[str] = []
    bucket_greps: list[str] = []
    for unit in ids:
        rest = unit.removeprefix("e2e-workers:")
        if rest == unit:
            raise UnitIdError(f"shard manifest id '{unit}' is not an e2e-workers unit")
        if "#" in rest:
            file, _, bucket = rest.partition("#")
            pattern = SHARD_GREP_BUCKETS.get(bucket, "")
            if not pattern:
                raise UnitIdError(
                    f"shard manifest bucket '{bucket}' (file {file}) has no entry in E2E_SHARD_GREP_BUCKETS"
                )
            bucket_files.append(file)
            bucket_greps.append(pattern)
        else:
            plain.append(rest)
    return plain, bucket_files, bucket_greps


def combined_grep(plain: list[str], bucket_files: list[str], bucket_greps: list[str]) -> str:
    parts = [js_escape(f) for f in plain]
    parts += [f"{js_escape(f)}.*(?:{g})" for f, g in zip(bucket_files, bucket_greps, strict=True)]
    if not parts:
        raise shard.ShardError("run-e2e.sh: no files resolved for this leg")
    return "|".join(parts)


def build_shard_command(opts: Options, ids: list[str], workers: str, ci: bool) -> list[str]:
    plain, bucket_files, bucket_greps = split_leg(ids)
    if opts.also:
        plain += opts.also.split(",")
    run_opts = [f"--workers={workers}"]
    if ci:
        run_opts.append("--max-failures=3")
    all_files: list[str] = []
    for f in [*plain, *bucket_files]:
        if f not in all_files:
            all_files.append(f)
    return [
        "npx",
        "playwright",
        "test",
        *run_opts,
        "--grep",
        combined_grep(plain, bucket_files, bucket_greps),
        *all_files,
    ]


def build_plain_command(opts: Options, workers: str, ci: bool) -> list[str]:
    cmd = ["npx", "playwright", "test", f"--workers={workers}"]
    if opts.config:
        cmd += ["--config", opts.config]
    if opts.filter:
        cmd += ["--grep", opts.filter]
    if opts.grep_invert:
        cmd += ["--grep-invert", opts.grep_invert]
    cmd += opts.test
    # Fail fast: stop after 3 failures instead of burning an hour on cascading timeouts.
    if ci:
        cmd.append("--max-failures=3")
    for flag in ("headed", "debug", "ui"):
        if getattr(opts, flag):
            cmd.append(f"--{flag}")
    return cmd


SENTINEL = "E2E_SKIPPED="
SENTINEL_COUNT = re.compile(r"E2E_SKIPPED=([0-9]+)")
SKIPPED_LINE = re.compile(r", skipped\)")
SKIPPED_LIST_MAX = 80


@dataclasses.dataclass
class Scan:
    """What the streamed run said about skips."""

    sentinel_seen: bool = False
    skipped: int = 0
    lines: list[str] = dataclasses.field(default_factory=list)

    def feed(self, line: str) -> None:
        if SENTINEL in line:
            self.sentinel_seen = True
        self.skipped += sum(int(n) for n in SENTINEL_COUNT.findall(line))
        if SKIPPED_LINE.search(line) and len(self.lines) < SKIPPED_LIST_MAX:
            self.lines.append(line)


def stream(cmd: list[str], cwd: str) -> tuple[int, Scan]:
    """Run `cmd`, stderr folded into stdout as `2>&1 | tee` did, echoing live and scanning for the skip sentinel."""
    scan = Scan()
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
    except OSError as exc:
        log.error(f"{cmd[0]}: {exc.strerror or exc}")
        return 1, scan
    assert proc.stdout is not None  # noqa: S101 - PIPE was requested above
    for raw in proc.stdout:
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
        scan.feed(raw.decode("utf-8", errors="replace").rstrip("\n"))
    return proc.wait(), scan


def judge_skips(scan: Scan) -> int | None:
    """The zero-skip gate. `None` means it passed."""
    if not scan.sentinel_seen:
        log.error(
            "Zero-skip gate ON but no E2E_SKIPPED sentinel found (TextFileReporter missing?). Failing closed."
        )
        return 1
    if scan.skipped > 0:
        log.error(
            f"Zero-skip gate: {scan.skipped} test(s) were SKIPPED (must be 0). A skipped test is invisible coverage loss."
        )
        log.error(
            "Each E2E job must SELECT only the tests its topology can run (config testMatch/testIgnore), not collect-then-skip."
        )
        print("----- skipped tests -----")
        for line in scan.lines:
            print(line)
        return 1
    log.info("Zero-skip gate: 0 skipped tests")
    return None


def main(argv: list[str]) -> int:
    try:
        opts = parse(argv)
    except UsageError as exc:
        print(f"run-e2e.sh: {exc}", file=sys.stderr)
        if isinstance(exc, PairError):
            return 1
        print(USAGE, file=sys.stderr)
        return 2
    root = paths.repo_root()
    os.chdir(root)
    ci = common.is_ci()
    workers = opts.workers or ("1" if ci else "4")
    log.step(f"Running E2E tests (workers: {workers})...")
    try:
        if opts.shard_manifest:
            cmd = build_shard_command(
                opts, shard.leg_ids(opts.shard_manifest, opts.shard), workers, ci
            )
        else:
            cmd = build_plain_command(opts, workers, ci)
    except shard.ShardError as exc:
        if isinstance(exc, UnitIdError):
            log.error(str(exc))
        else:
            print(exc, file=sys.stderr)
        return 1
    rc, scan = stream(cmd, str(root / E2E_TESTS_DIR))
    if opts.fail_on_skip:
        verdict = judge_skips(scan)
        if verdict is not None:
            return verdict
    if rc == 0:
        log.info("E2E tests passed")
        return 0
    log.error("E2E tests failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
