"""One capped snapshot of one named repository on one named machine, sampled from outside, with one summary line per run.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.read_cap_seed demo-heartbeat --machine hostinger --config eu-bench
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.read_cap_seed marketing --machine hostinger --config eu-bench --stop-on cpu

WHY IT EXISTS (agent/plans/PLAN-snapshot-read-io-cap.md, L2 and L3; PLAN-backup-program.md, Q11). Those boxes rested on an untracked /tmp/scr/seed.sh that no longer exists. This module is its tracked successor, and the Accept lines read its summary line.

THE VERB. `rdc --config <name> -o json backup snapshot <repo>@<machine> --bwlimit 100Mbps --parallelism 2`. The read cap, the hash workers and the CPU ceiling stay at the verb's defaults, so a flag for any of them here would hide the default under test. The config has no default, because a bare `./rdc.sh` targets production. The only verbs this module can run are the four in `snapshot_argv`, `sample_argv`, `job_list_argv` and `job_cancel_argv`: nothing here deletes or modifies a repository, and `--reseed` is never passed (it re-uploads and re-charges quota).

THE SAMPLES. `SAMPLE_COMMAND` runs through `rdc term connect <machine> -c` and reads only /proc and the cgroup tree. Every figure is a delta between two samples. `load` is the 1-minute load average. `iowait` and `busy` come from the /proc/stat delta, where busy is 100 minus idle (so iowait counts as busy, as the 2026-10-29 ruling and vmstat state it) and is already a share of all cores. `backup` is the snapshot scope's own `usage_usec` delta as a share of all cores: renet wraps the verb in `systemd-run --scope`, so a process running `renet backup snapshot` inside a cgroup named `run-*.scope` is what is measured (never `init.scope` or a login's `session-*.scope`). No such scope reads `none`, which fails the L3 Accept rather than passing it. Kernel threads serving the datastore are not charged to the scope, and `busy` is recorded beside it for that reason. The baseline is 60 s of samples before the snapshot starts, and `baseload` is their mean load. Each sample is an SSH round trip, so the real spacing can exceed `INTERVAL_S`.

THE STOP RULE. `--stop-on load` (the default, as the patched seed.sh did): load at or above baseload + 3.5 for three samples in a row. `--stop-on cpu` (the operator ruling of 2026-10-29 under "CPU ceiling", for L3): busy above 50 for three samples in a row. A sample that could not be read leaves the run of three as it was. Stopping is `rdc job cancel`, retried each tick until it lands: Ctrl-C on a followed job only detaches it (PLAN-detached-jobs section 15), so a killed client would leave the snapshot running. The cancel marker makes the job finalize as cancelled, and a snapshot works on a reflinked copy, so the repository is untouched. The field `loadover8x3` keeps the old script's name because the L2 Accept reads it; it is 1 when the load rule's condition held, whichever rule stops the run, and it is 0 otherwise.

READ EVIDENCE. The record cannot state bytes read, so `read_evidence` derives it. A non-empty `rehashReason` means the image was rehashed (`full-rehash`). Otherwise the cells asked beyond the rolling sample changed, and those were read (`changed-cells`). Neither is `no-change`: the read cap was not exercised, as in the 2026-10-29 L2 record, and `weak=1` says so on the summary line. A weak run does not fail on that account alone. Fewer than three samples is also weak, because the stop rule could not have fired. `readbytes` is a floor, the cells named by the record times their size.

SUMMARY. One line appended to `--summary`, whitespace-separated `key=value` fields after the bare repository name, the shape the L2 Accept's awk reads. `rc` is the driver's exit code and `snapshotrc` the verb's. The verb's stdout and stderr are kept beside it as `<summary>.<repo>.out` and `.err`.

EXIT. The snapshot's rc when it failed. Otherwise 3 when no sample was collected (no baseline means the snapshot never started), 4 when the stop rule fired (even if the snapshot committed before the cancel reached it), 130 on Ctrl-C (the job keeps running, and the commands that find and cancel it are printed), and 2 on bad arguments or an unwritable summary.
"""

from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol, TextIO

BWLIMIT = "100Mbps"
PARALLELISM = "2"
INTERVAL_S = 10.0
BASELINE_S = 60.0
LOAD_MARGIN = 3.5
CPU_BOUND = 50.0
STREAK = 3
SAMPLE_TIMEOUT_S = 60.0
RDC_TIMEOUT_S = 120.0
STOP_GRACE_S = 300.0
DETACH_GRACE_S = 30.0
DEFAULT_CELL_BYTES = 4_194_304
DEFAULT_SUMMARY = "/tmp/seed/summary.log"

EXIT_USAGE = 2
EXIT_NO_SAMPLES = 3
EXIT_STOPPED = 4
EXIT_INTERRUPTED = 130

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(:[A-Za-z0-9._-]+)?")

# One shell line with no redirect. `[r]enet` keeps this shell's own command line out of pgrep's matches, and sudo's parent process carries the same words but sits outside any `run-*.scope`.
SAMPLE_COMMAND = (
    'echo "uptime $(cat /proc/uptime)"; '
    'echo "load $(cat /proc/loadavg)"; '
    "head -n 1 /proc/stat; "
    'echo "nproc $(nproc)"; '
    "for p in $(pgrep -f '[r]enet backup snapshot'); do sed -n 's/^0:://p' /proc/$p/cgroup; done "
    '| sort -u | while read -r c; do case "$c" in */run-*.scope) '
    "echo \"scope $c $(sed -n 's/^usage_usec //p' /sys/fs/cgroup$c/cpu.stat)\";; esac; done"
)


@dataclass(frozen=True)
class Sample:
    uptime: float
    load: float
    cpu_total: int
    cpu_idle: int
    cpu_iowait: int
    cores: int
    scopes: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Figures:
    load: float
    busy: float
    iowait: float
    backup: float | None
    # Taken after the snapshot's client had exited, so no backup scope could exist; not a measured sample.
    postexit: bool = False


@dataclass(frozen=True)
class ReadEvidence:
    kind: str
    bytes: int


@dataclass(frozen=True)
class RunResult:
    repo: str
    rc: int
    snapshot_rc: int | None
    baseload: float | None
    figures: tuple[Figures, ...] = ()
    failed_samples: int = 0
    stopped: str = "none"
    cancelled: bool = False
    record: dict[str, Any] | None = None


class Process(Protocol):
    def wait(self, timeout: float | None = None) -> int: ...
    def send_signal(self, sig: int) -> None: ...
    def kill(self) -> None: ...


# (argv, timeout seconds) -> (returncode, stdout, stderr); a timeout answers rc 124.
Runner = Callable[[Sequence[str], float], "tuple[int, str, str]"]
# (argv, stdout path, stderr path) -> the running snapshot.
Spawner = Callable[[Sequence[str], Path, Path], Process]


def real_runner(argv: Sequence[str], timeout: float) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %.0f s" % timeout
    return proc.returncode, proc.stdout, proc.stderr


def real_spawner(argv: Sequence[str], out_path: Path, err_path: Path) -> Process:
    with out_path.open("w", encoding="utf-8") as out, err_path.open("w", encoding="utf-8") as err:
        return subprocess.Popen(list(argv), stdin=subprocess.DEVNULL, stdout=out, stderr=err)


@dataclass
class Deps:
    runner: Runner = real_runner
    spawner: Spawner = real_spawner
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


def repo_ref(repo: str, machine: str) -> str:
    return "%s@%s" % (repo, machine)


def snapshot_argv(rdc: str, config: str, repo: str, machine: str) -> list[str]:
    return [
        rdc,
        "--config",
        config,
        "-o",
        "json",
        "backup",
        "snapshot",
        repo_ref(repo, machine),
        "--bwlimit",
        BWLIMIT,
        "--parallelism",
        PARALLELISM,
    ]


def sample_argv(rdc: str, config: str, machine: str) -> list[str]:
    return [rdc, "--config", config, "term", "connect", machine, "-c", SAMPLE_COMMAND]


def job_list_argv(rdc: str, config: str) -> list[str]:
    return [rdc, "--config", config, "-o", "json", "job", "list"]


def job_cancel_argv(rdc: str, config: str, job_id: str, machine: str) -> list[str]:
    return [rdc, "--config", config, "-y", "job", "cancel", job_id, "-m", machine]


def parse_sample(text: str) -> Sample | None:
    """A Sample from SAMPLE_COMMAND's stdout, or None when any required line is missing or malformed."""
    values: dict[str, str] = {}
    scopes: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in {"uptime", "load", "cpu", "nproc"}:
            values[parts[0]] = " ".join(parts[1:])
        elif len(parts) == 3 and parts[0] == "scope" and parts[2].isdigit():
            scopes[parts[1]] = int(parts[2])
    if set(values) != {"uptime", "load", "cpu", "nproc"}:
        return None
    try:
        jiffies = [int(v) for v in values["cpu"].split()]
        if len(jiffies) < 8:
            return None
        cores = int(values["nproc"])
        if cores < 1:
            return None
        return Sample(
            uptime=float(values["uptime"].split()[0]),
            load=float(values["load"].split()[0]),
            # The first eight columns: guest time is already inside user and nice.
            cpu_total=sum(jiffies[:8]),
            cpu_idle=jiffies[3],
            cpu_iowait=jiffies[4],
            cores=cores,
            scopes=scopes,
        )
    except (ValueError, IndexError):
        return None


def interval_figures(prev: Sample, cur: Sample) -> Figures | None:
    """The figures between two samples, or None when no time or no CPU tick separates them."""
    ticks = cur.cpu_total - prev.cpu_total
    seconds = cur.uptime - prev.uptime
    if ticks <= 0 or seconds <= 0:
        return None
    backup = None
    if cur.scopes:
        # A scope absent from `prev` was born inside the interval, and its counter started at zero.
        used = sum(max(0, u - prev.scopes.get(path, 0)) for path, u in cur.scopes.items())
        backup = 100.0 * used / (seconds * 1_000_000 * cur.cores)
    return Figures(
        load=cur.load,
        busy=100.0 - 100.0 * (cur.cpu_idle - prev.cpu_idle) / ticks,
        iowait=100.0 * (cur.cpu_iowait - prev.cpu_iowait) / ticks,
        backup=backup,
    )


def load_over(figure: Figures, baseload: float) -> bool:
    return figure.load >= baseload + LOAD_MARGIN


def busy_over(figure: Figures) -> bool:
    return figure.busy > CPU_BOUND


def streak_fired(flags: Iterable[bool], need: int = STREAK) -> bool:
    """True when `need` consecutive flags are set anywhere in `flags`."""
    run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        if run >= need:
            return True
    return False


def rule_fired(rule: str, figures: Sequence[Figures], baseload: float) -> bool:
    if rule == "cpu":
        return streak_fired(busy_over(f) for f in figures)
    return streak_fired(load_over(f, baseload) for f in figures)


def json_objects(text: str) -> list[dict[str, Any]]:
    """Every top-level JSON object in `text`. The output of rdc spans several lines, and a log line may precede it."""
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    index = text.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict):
            found.append(value)
        index = text.find("{", end)
    return found


def _payloads(text: str) -> list[Any]:
    """Each object's envelope `data` where it carries one, else the object."""
    return [obj.get("data", obj) for obj in json_objects(text)]


def parse_record(text: str) -> dict[str, Any] | None:
    """The last snapshot record in the verb's stdout, envelope or bare; None when there is none."""
    found = None
    for payload in _payloads(text):
        if isinstance(payload, dict) and "status" in payload:
            found = payload
    return found


def _bare_name(repo: str) -> str:
    return repo.removesuffix(":latest")


def find_job_id(text: str, repo: str, machine: str) -> str | None:
    """The newest live `backup snapshot` ticket of this repository and machine in `rdc -o json job list`."""
    for payload in _payloads(text):
        if not isinstance(payload, list):
            continue
        for row in payload:
            if (
                isinstance(row, dict)
                and row.get("verb") == "backup snapshot"
                and row.get("machine") == machine
                and _bare_name(str(row.get("repo"))) == _bare_name(repo)
                and row.get("state") in {"starting", "running"}
                and row.get("id")
            ):
                return str(row["id"])
    return None


def read_evidence(record: dict[str, Any] | None) -> ReadEvidence:
    """What the record shows about bytes read; see READ EVIDENCE in the module docstring."""
    if record is None:
        return ReadEvidence("no-record", 0)
    asked = max(0, int(record.get("chunksAsked") or 0) - int(record.get("chunksSampled") or 0))
    cell = int(record.get("cellBytes") or DEFAULT_CELL_BYTES)
    if record.get("rehashReason"):
        return ReadEvidence("full-rehash", asked * cell)
    if asked:
        return ReadEvidence("changed-cells", asked * cell)
    return ReadEvidence("no-change", 0)


def weak_reasons(evidence: ReadEvidence, sample_count: int) -> list[str]:
    reasons = []
    if evidence.kind in {"no-change", "no-record"}:
        reasons.append(evidence.kind)
    if sample_count < STREAK:
        reasons.append("few-samples")
    return reasons


def final_rc(snapshot_rc: int | None, sample_count: int, stopped: str) -> int:
    """See EXIT in the module docstring."""
    if snapshot_rc:
        return snapshot_rc
    if sample_count == 0:
        return EXIT_NO_SAMPLES
    if stopped != "none":
        return EXIT_STOPPED
    return 0


def _num(value: float | None) -> str:
    return "none" if value is None else "%.2f" % value


def _peak(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return max(present) if present else None


def _token(value: Any) -> str:
    """A record value as one awk field: no whitespace, and no `=` to cut it short."""
    return "none" if value is None else re.sub(r"[\s=]+", "_", str(value))


def summary_line(result: RunResult) -> str:
    """One run's line. The first five fields after the name are what the L2 Accept's awk reads."""
    figures = result.figures
    record = result.record or {}
    evidence = read_evidence(result.record)
    measured = [f for f in figures if not f.postexit]
    reasons = weak_reasons(evidence, len(measured))
    backups = [f.backup for f in figures]
    fields = {
        "rc": result.rc,
        "peakload": _num(_peak(f.load for f in figures)),
        "baseload": _num(result.baseload),
        "peakwa": _num(_peak(f.iowait for f in figures)),
        "loadover8x3": int(
            result.baseload is not None and rule_fired("load", figures, result.baseload)
        ),
        "cpuover50x3": int(rule_fired("cpu", figures, 0.0)),
        "snapshotrc": _token(result.snapshot_rc),
        "stopped": result.stopped,
        "cancelled": int(result.cancelled),
        "samples": len(measured),
        "postexit": len(figures) - len(measured),
        "failedsamples": result.failed_samples,
        "readkind": evidence.kind,
        "readbytes": evidence.bytes,
        "weak": int(bool(reasons)),
        "weakreason": ",".join(reasons) or "none",
        "cpuQuota": _token(record.get("cpuQuota")),
        "cpuLimitPercent": _token(record.get("cpuLimitPercent")),
        "readCapBps": _token(record.get("readCapBps")),
        "hashWorkers": _token(record.get("hashWorkers")),
        "bytesUploaded": _token(record.get("bytesUploaded")),
        "durationMs": _token(record.get("durationMs")),
        "snapshotId": _token(record.get("snapshotId")),
        "peakbusycpu": _num(_peak(f.busy for f in figures)),
        "peakbackupcpu": _num(_peak(backups)),
        "backupcpun": sum(b is not None for b in backups),
        "backupcpuover50": sum(b is not None and b > CPU_BOUND for b in backups),
        "backupcpu": ",".join(_num(b) for b in backups) or "none",
        "busycpu": ",".join(_num(f.busy) for f in figures) or "none",
    }
    return " ".join([result.repo, *("%s=%s" % kv for kv in fields.items())])


def _take_sample(deps: Deps, rdc: str, config: str, machine: str, out: TextIO) -> Sample | None:
    rc, stdout, stderr = deps.runner(sample_argv(rdc, config, machine), SAMPLE_TIMEOUT_S)
    sample = parse_sample(stdout) if rc == 0 else None
    if sample is None:
        tail = " | ".join(stderr.strip().splitlines()[-2:])
        print("sample failed: rc=%d %s" % (rc, tail), file=out, flush=True)
    return sample


def take_baseline(
    deps: Deps, rdc: str, config: str, machine: str, out: TextIO
) -> tuple[float | None, Sample | None]:
    """(mean load, last sample) over BASELINE_S at INTERVAL_S; (None, None) when no sample was read."""
    began = deps.clock()
    loads: list[float] = []
    last: Sample | None = None
    tick = 0
    while True:
        sample = _take_sample(deps, rdc, config, machine, out)
        if sample is not None:
            loads.append(sample.load)
            last = sample
        tick += 1
        due = began + tick * INTERVAL_S
        if due - began > BASELINE_S:
            break
        deps.sleep(max(0.0, due - deps.clock()))
    if not loads:
        return None, None
    return sum(loads) / len(loads), last


def _wait(proc: Process, seconds: float) -> int | None:
    try:
        return proc.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        return None


def _shell_rc(rc: int) -> int:
    """A process killed by a signal reports -N; the shell's form is 128+N."""
    return 128 - rc if rc < 0 else rc


def _cancel_job(deps: Deps, rdc: str, config: str, repo: str, machine: str, out: TextIO) -> bool:
    rc, stdout, stderr = deps.runner(job_list_argv(rdc, config), RDC_TIMEOUT_S)
    job_id = find_job_id(stdout, repo, machine) if rc == 0 else None
    if job_id is None:
        print("stop: no live job found yet (job list rc=%d) %s" % (rc, stderr.strip()), file=out)
        return False
    rc, _, stderr = deps.runner(job_cancel_argv(rdc, config, job_id, machine), RDC_TIMEOUT_S)
    print("stop: job cancel %s rc=%d %s" % (job_id, rc, stderr.strip()), file=out, flush=True)
    return rc == 0


def _print_sample(index: int, figure: Figures, out: TextIO) -> None:
    print(
        "sample %d load=%.2f busy=%.1f iowait=%.1f backup=%s"
        % (index, figure.load, figure.busy, figure.iowait, _num(figure.backup)),
        file=out,
        flush=True,
    )


def _finish_stop(proc: Process) -> int:
    """The cancel landed and the client still follows: detach it, then kill it, without touching the job."""
    proc.send_signal(signal.SIGINT)
    rc = _wait(proc, DETACH_GRACE_S)
    if rc is None:
        proc.kill()
        rc = proc.wait()
    return rc


@dataclass
class _Watch:
    figures: list[Figures] = field(default_factory=list)
    failed: int = 0
    stopped: str = "none"
    cancelled: bool = False
    stop_at: float | None = None


def watch_snapshot(
    deps: Deps,
    proc: Process,
    start: Sample,
    baseload: float,
    args: argparse.Namespace,
    out: TextIO,
    watch: _Watch,
) -> int:
    """Sample until the snapshot's client exits, stopping the job once the rule fires. Returns its raw rc."""
    prev = start
    due = deps.clock() + INTERVAL_S
    while True:
        rc = _wait(proc, max(0.0, due - deps.clock()))
        if rc is not None:
            return rc
        due = max(due + INTERVAL_S, deps.clock())
        sample = _take_sample(deps, args.rdc, args.config, args.machine, out)
        figure = interval_figures(prev, sample) if sample is not None else None
        if sample is None or figure is None:
            watch.failed += 1
        else:
            prev = sample
            if figure.backup is None and _wait(proc, 0) is not None:
                figure = replace(figure, postexit=True)
            watch.figures.append(figure)
            _print_sample(len(watch.figures), figure, out)
        if watch.stopped == "none" and rule_fired(args.stop_on, watch.figures, baseload):
            watch.stopped = args.stop_on
            watch.stop_at = deps.clock()
            print("stop: the %s rule fired" % args.stop_on, file=out, flush=True)
        if watch.stopped != "none" and not watch.cancelled:
            watch.cancelled = _cancel_job(deps, args.rdc, args.config, args.repo, args.machine, out)
            if watch.cancelled:
                watch.stop_at = deps.clock()
        if watch.cancelled and deps.clock() - (watch.stop_at or 0.0) > STOP_GRACE_S:
            return _finish_stop(proc)


def _print_read_verdict(result: RunResult, out: TextIO) -> None:
    evidence = read_evidence(result.record)
    if evidence.kind in {"no-change", "no-record"}:
        print(
            "read: NO BYTES SHOWN READ (%s): the read cap was not exercised, a weak pass at best"
            % evidence.kind,
            file=out,
        )
    else:
        reason = (result.record or {}).get("rehashReason") or "changed cells"
        print(
            "read: at least %d bytes (%s; %s)" % (evidence.bytes, evidence.kind, reason), file=out
        )


def _append_summary(path: Path, result: RunResult, out: TextIO) -> None:
    line = summary_line(result)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line, file=out, flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="read_cap_seed", description=__doc__.split("\n")[0])
    parser.add_argument("repo", help="repository name, name:tag for a fork")
    parser.add_argument("--machine", required=True)
    parser.add_argument(
        "--config", required=True, help="the config to run under; there is no default"
    )
    parser.add_argument("--stop-on", choices=("load", "cpu"), default="load")
    parser.add_argument("--rdc", default="./rdc.sh")
    parser.add_argument("--summary", default=DEFAULT_SUMMARY, type=Path)
    return parser


def _usable_args(args: argparse.Namespace, out: TextIO) -> bool:
    if not REPO.fullmatch(args.repo) or not NAME.fullmatch(args.machine):
        print("bad repository or machine name", file=out)
        return False
    if not NAME.fullmatch(args.config):
        print("bad config name", file=out)
        return False
    try:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.open("a", encoding="utf-8").close()
    except OSError as exc:
        print("summary not writable: %s" % exc, file=out)
        return False
    return True


def main(
    argv: Sequence[str] | None = None, deps: Deps | None = None, out: TextIO | None = None
) -> int:
    out = sys.stdout if out is None else out
    deps = Deps() if deps is None else deps
    args = _parser().parse_args(argv)
    if not _usable_args(args, out):
        return EXIT_USAGE

    baseload, start = take_baseline(deps, args.rdc, args.config, args.machine, out)
    if baseload is None or start is None:
        print("no baseline sample: the snapshot was not started", file=out)
        result = RunResult(args.repo, EXIT_NO_SAMPLES, None, None)
        _append_summary(args.summary, result, out)
        return EXIT_NO_SAMPLES
    print("baseload %.2f" % baseload, file=out, flush=True)

    stem = "%s.%s" % (args.summary, args.repo.replace(":", "_"))
    out_path, err_path = Path(stem + ".out"), Path(stem + ".err")
    proc = deps.spawner(
        snapshot_argv(args.rdc, args.config, args.repo, args.machine), out_path, err_path
    )
    watch = _Watch()
    interrupted = False
    try:
        snapshot_rc = _shell_rc(watch_snapshot(deps, proc, start, baseload, args, out, watch))
    except KeyboardInterrupt:
        interrupted = True
        snapshot_rc = None
        print(
            "interrupted: the job keeps running; find its id with `%s`, stop it with `%s`"
            % (
                " ".join(job_list_argv(args.rdc, args.config)),
                " ".join(job_cancel_argv(args.rdc, args.config, "<job-id>", args.machine)),
            ),
            file=out,
        )

    rc = (
        EXIT_INTERRUPTED
        if interrupted
        else final_rc(snapshot_rc, len(watch.figures), watch.stopped)
    )
    result = RunResult(
        repo=args.repo,
        rc=rc,
        snapshot_rc=snapshot_rc,
        baseload=baseload,
        figures=tuple(watch.figures),
        failed_samples=watch.failed,
        stopped="interrupted" if interrupted else watch.stopped,
        cancelled=watch.cancelled,
        record=parse_record(out_path.read_text(encoding="utf-8", errors="replace")),
    )
    _print_read_verdict(result, out)
    _append_summary(args.summary, result, out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
