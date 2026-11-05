"""Check the backup meter against an independent listing of the store: replay a killed snapshot run, or take a census of every lineage.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile backup-push-bench -- \\
      env PYTHONPATH=.ci python3 -m rediacc_ci.ops.backup_meter_replay replay \\
        --config eu-bench --repo <repo> --machine hostinger [--bwlimit 2MB] [--kill-after 50]
    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile backup-push-bench -- \\
      env PYTHONPATH=.ci python3 -m rediacc_ci.ops.backup_meter_replay census --config eu-bench [--apply]

WHY IT EXISTS. agent/plans/PLAN-backup-meter-orphaned-chunks.md L1 and L2 compare `rdc backup usage` with what the store really holds. The earlier records listed the bucket with a throwaway script outside the repository; this module is that listing, kept, plus the sequence around it, so the equality is an oracle with a test rather than a hand count.

THE LISTING. ListObjectsV2 over `t/<subscriptionId>/` (or one lineage's `l/<lineage>/` under it), every page, signed by `drills.wire.sigv4_headers`. A key with a `/c/` segment is a chunk and its size counts; a `/m/` key is a manifest and only its count is kept. The key layout is the account server's (private/account/src/services/backup-chunk-store.ts `backupKeys`): `t/<sub>/l/<lineage>/c/<sha256>` and `t/<sub>/l/<lineage>/m/<snapshotId>`. The bucket and its jurisdiction come from `push_backup_credentials.plan`, the endpoint per bucket from `set_account_worker_secrets.apply_jurisdiction`, and the credentials from `backup_bucket_scope_probe.read_env` (the unsuffixed names the `backup-push-<channel>` profile binds). No key, signature, endpoint host or presigned URL is printed.

A MOVING STORE IS NO VERDICT. Every equality reads the listing, then the meter, then the listing again. Two listings that differ mean an upload or a GC ran in between, and the run exits 2 instead of judging a race.

`replay` (L1), in order:
  1. `backup reconcile <repo>@<machine> --dry-run -o json` names the subscription and the lineage (`--lineage` overrides the lineage, for a lineage the server has no row for yet). No `renet backup snapshot` may already run on the machine: the kill in step 4 matches every one there.
  2. List the lineage: the baseline chunk and manifest counts.
  3. Start `backup snapshot <repo>@<machine> --bwlimit <rate> -o json` and list the lineage every `--poll` seconds.
  4. Once at least `--kill-after` new chunks are listed, SIGKILL `renet backup snapshot` on the machine through `rdc term connect <machine> -c`, the way renet's old execute timeout killed the hostinger run: the journal keeps the snapshot with ManifestCommitted=false, which is what R1's supersede reads. Killing the local client alone only detaches a followed job. A snapshot that finishes before the threshold, or a killed run that committed a manifest, is no verdict (exit 2): the sequence did not happen.
  5. Rerun `backup snapshot <repo>@<machine> -o json`; it must exit 0 and commit one manifest.
  6. Immediately: the lineage's usage row (chunkCount, storedBytes) must equal the lineage listing (count, bytes), and `backup reconcile <repo>@<machine> --check` must exit 0. A window from the kill to the verdict that spans the 03:00 UTC maintenance run is no verdict: the nightly re-bill would heal the meter by itself and hide what the commit did.

`census` (L2), in order:
  1. `backup reconcile --dry-run -o json`: the before figures, printed per lineage.
  2. With `--apply` only: `backup reconcile -o json` applies.
  3. The tenant listing, `backup usage -o json`, the tenant listing again: usage storedBytes and chunkCount must equal the listing's `/c/` byte sum and count, in total and per lineage (manifests are not counted).
  4. A fresh `backup reconcile --dry-run -o json`: per lineage, referenced plus unreferenced chunks and bytes must equal the listing (unreferenced need not be 0; it is billed until GC deletes it after the grace). A lineage the server skipped (leased, unreadable) is no verdict. `--strict-referenced <lineage>` (repeatable) also requires that lineage's stored bytes to equal its referenced bytes.
  5. `backup reconcile --check` must exit 0.

Exit 0: every equality held. Exit 1: a figure disagreed, the rerun failed, or `--check` found drift. Exit 2: a usage or configuration error, or no verdict (a moving store, a sequence that did not happen, a transport error, a listing refused).
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TextIO

from rediacc_ci import paths
from rediacc_ci.deploy import set_account_worker_secrets
from rediacc_ci.drills import wire
from rediacc_ci.ops import backup_bucket_scope_probe as scope
from rediacc_ci.ops import push_backup_credentials as pbc

SIGV4_REGION = "auto"
HTTP_TIMEOUT_S = 60.0
RDC_TIMEOUT_S = 600.0
SNAPSHOT_TIMEOUT_S = 4 * 3600.0
CLIENT_EXIT_WAIT_S = 120.0
MAINTENANCE_HOUR_UTC = 3
PROC_PATTERN = "[r]enet backup snapshot"
RUNNING_COMMAND = "pgrep -f '%s' >/dev/null && echo RUNNING || echo IDLE" % PROC_PATTERN
KILL_COMMAND = (
    "sudo pkill -KILL -f '%s'; sleep 2; pgrep -f '%s' >/dev/null && echo ALIVE || echo GONE"
    % (PROC_PATTERN, PROC_PATTERN)
)

PASS, FAIL, NOTE, UNKNOWN = "PASS", "FAIL", "NOTE", "NO-VERDICT"

# (method, url, body, headers) -> (status, body); raises OSError on a transport failure.
Transport = Callable[[str, str, bytes, dict], tuple[int, bytes]]
# (argv, timeout seconds) -> (returncode, stdout, stderr); a timeout answers rc 124.
Runner = Callable[[Sequence[str], float], "tuple[int, str, str]"]


class Process(Protocol):
    def poll(self) -> int | None: ...
    def wait(self, timeout: float | None = None) -> int: ...
    def kill(self) -> None: ...


# argv -> a running process whose output goes to the two paths.
Spawner = Callable[[Sequence[str], Path, Path], Process]


class ConfigError(Exception):
    """A usage or configuration problem; printed, and the run exits 2."""


class NoVerdictError(Exception):
    """The run cannot judge (a moving store, a sequence that did not happen, a transport error); exit 2."""


# ---------------------------------------------------------------- listing


@dataclass
class LineageCount:
    chunks: int = 0
    chunk_bytes: int = 0
    manifests: int = 0


@dataclass
class Listing:
    lineages: dict[str, LineageCount] = field(default_factory=dict)

    @property
    def chunks(self) -> int:
        return sum(c.chunks for c in self.lineages.values())

    @property
    def chunk_bytes(self) -> int:
        return sum(c.chunk_bytes for c in self.lineages.values())

    def of(self, lineage: str) -> LineageCount:
        return self.lineages.get(lineage, LineageCount())

    def figures(self) -> dict[str, tuple[int, int, int]]:
        return {k: (v.chunks, v.chunk_bytes, v.manifests) for k, v in self.lineages.items()}


_CONTENTS = re.compile(r"<Contents>(.*?)</Contents>", re.DOTALL)
_KEY = re.compile(r"<Key>([^<]*)</Key>")
_SIZE = re.compile(r"<Size>(\d+)</Size>")
_TOKEN = re.compile(r"<NextContinuationToken>([^<]*)</NextContinuationToken>")


def parse_page(xml: str) -> tuple[list[tuple[str, int]], str | None]:
    """The (key, size) pairs of one ListObjectsV2 page, and the continuation token when truncated."""
    objects = []
    for block in _CONTENTS.findall(xml):
        key = _KEY.search(block)
        size = _SIZE.search(block)
        if key is None or size is None:
            raise NoVerdictError("a listing entry carries no Key or no Size")
        objects.append((html.unescape(key.group(1)), int(size.group(1))))
    token = None
    if "<IsTruncated>true</IsTruncated>" in xml:
        found = _TOKEN.search(xml)
        if found is None:
            raise NoVerdictError("a truncated listing page carries no continuation token")
        token = html.unescape(found.group(1))
    return objects, token


def classify(listing: Listing, key: str, size: int) -> None:
    """Fold one key into the listing: `.../l/<lineage>/c/<hash>` is a chunk, `.../l/<lineage>/m/<id>` a manifest; anything else is ignored."""
    parts = key.split("/")
    try:
        at = parts.index("l")
    except ValueError:
        return
    if len(parts) < at + 4:
        return
    lineage, kind = parts[at + 1], parts[at + 2]
    count = listing.lineages.setdefault(lineage, LineageCount())
    if kind == "c":
        count.chunks += 1
        count.chunk_bytes += size
    elif kind == "m":
        count.manifests += 1


def default_transport(method: str, url: str, _body: bytes, headers: dict) -> tuple[int, bytes]:
    return wire.http_bytes(method, url, None, headers, json_body=False, timeout=HTTP_TIMEOUT_S)


class Lister:
    """Lists one bucket's tenant or lineage prefix. Prints nothing secret."""

    def __init__(
        self,
        endpoint: str,
        key_id: str,
        secret: str,
        bucket: scope.Bucket,
        transport: Transport = default_transport,
    ) -> None:
        base = set_account_worker_secrets.apply_jurisdiction(endpoint, bucket.jurisdiction)
        self._base = "%s/%s" % (base.rstrip("/"), bucket.name)
        self._key_id = key_id
        self._secret = secret
        self._transport = transport
        self.bucket = bucket

    def list(self, subscription: str, lineage: str | None = None) -> Listing:
        prefix = "t/%s/" % subscription + ("l/%s/" % lineage if lineage else "")
        listing = Listing()
        token: str | None = None
        while True:
            query = {"list-type": "2", "prefix": prefix}
            if token:
                query["continuation-token"] = token
            url = "%s?%s" % (self._base, urllib.parse.urlencode(sorted(query.items())))
            headers = wire.sigv4_headers("GET", url, b"", SIGV4_REGION, self._key_id, self._secret)
            try:
                status, body = self._transport("GET", url, b"", headers)
            except OSError as exc:
                raise NoVerdictError("listing transport error (%s)" % type(exc).__name__) from exc
            if not 200 <= status < 300:
                raise NoVerdictError("the listing answered HTTP %d" % status)
            objects, token = parse_page(body.decode("utf-8", "replace"))
            for key, size in objects:
                classify(listing, key, size)
            if not token:
                return listing


def make_lister(
    channel: str, region: str | None, environ: dict[str, str], transport: Transport, root=None
) -> Lister:
    endpoint, key_id, secret = scope.credentials(channel, environ)
    try:
        plan = pbc.plan(channel, region, paths.repo_root() if root is None else root)
    except (pbc.PushError, pbc.UsageError) as exc:
        raise ConfigError(str(exc)) from exc
    return Lister(endpoint, key_id, secret, scope.Bucket(plan.bucket, plan.jurisdiction), transport)


# ---------------------------------------------------------------- rdc


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


def last_object(text: str) -> dict[str, Any] | None:
    """The last top-level JSON object in `text`; rdc output may span lines and follow log lines."""
    decoder = json.JSONDecoder()
    found = None
    i = 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return found
        try:
            value, end = decoder.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        if isinstance(value, dict):
            found = value
        i = end


@dataclass
class Deps:
    runner: Runner = real_runner
    spawner: Spawner = real_spawner
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(datetime.UTC)
    workdir: Path = field(default_factory=lambda: Path("/tmp"))


class Rdc:
    def __init__(self, rdc: str, config: str, deps: Deps) -> None:
        self.rdc = rdc
        self.config = config
        self.deps = deps

    def argv(self, *args: str) -> list[str]:
        return [self.rdc, "--config", self.config, *args]

    def run(self, *args: str, timeout: float = RDC_TIMEOUT_S) -> tuple[int, str, str]:
        return self.deps.runner(self.argv(*args), timeout)

    def json(self, *args: str) -> dict[str, Any]:
        rc, stdout, stderr = self.run("-o", "json", *args)
        doc = last_object(stdout)
        if rc != 0 or doc is None:
            raise NoVerdictError(
                "`rdc %s -o json` rc=%d: %s"
                % (" ".join(args), rc, (stderr or stdout).strip()[-400:])
            )
        return doc

    def usage(self) -> dict[str, Any]:
        return self.json("backup", "usage")

    def reconcile(self, ref: str | None, dry_run: bool) -> dict[str, Any]:
        args = ["backup", "reconcile"] + ([ref] if ref else []) + (["--dry-run"] if dry_run else [])
        return self.json(*args)

    def check(self, ref: str | None) -> int:
        rc, _, _ = self.run("backup", "reconcile", *([ref] if ref else []), "--check")
        return rc

    def on_machine(self, machine: str, command: str) -> str:
        rc, stdout, stderr = self.run("term", "connect", machine, "-c", command)
        if rc != 0:
            raise NoVerdictError(
                "`term connect %s` rc=%d: %s" % (machine, rc, stderr.strip()[-300:])
            )
        return stdout


# ---------------------------------------------------------------- verdicts


class Report:
    def __init__(self, out: TextIO) -> None:
        self.out = out
        self.verdicts: list[str] = []

    def line(self, verdict: str, what: str, detail: str = "") -> None:
        if verdict != NOTE:
            self.verdicts.append(verdict)
        print("%-10s %-28s %s" % (verdict, what, detail), file=self.out, flush=True)

    def equal(self, what: str, metered: int, listed: int) -> None:
        verdict = PASS if metered == listed else FAIL
        self.line(verdict, what, "meter %d, listing %d" % (metered, listed))

    def exit_code(self) -> int:
        if FAIL in self.verdicts:
            return 1
        if UNKNOWN in self.verdicts or not self.verdicts:
            return 2
        return 0


def stable_listing(read: Callable[[], Listing], between: Callable[[], Any]) -> tuple[Listing, Any]:
    """Listing, `between()`, listing again; NoVerdictError when the two listings differ."""
    first = read()
    value = between()
    second = read()
    if first.figures() != second.figures():
        raise NoVerdictError(
            "the store moved during the read (%d chunks, then %d): an upload or GC is running"
            % (first.chunks, second.chunks)
        )
    return second, value


def crosses_maintenance(start: datetime.datetime, end: datetime.datetime) -> bool:
    """True when [start, end] contains a 03:00 UTC instant (the nightly re-bill)."""
    mark = start.replace(hour=MAINTENANCE_HOUR_UTC, minute=0, second=0, microsecond=0)
    if mark < start:
        mark += datetime.timedelta(days=1)
    return mark <= end


def usage_lineage(usage: dict[str, Any], lineage: str) -> dict[str, Any] | None:
    for row in usage.get("lineages") or []:
        if row.get("lineageGuid") == lineage:
            return row
    return None


# ---------------------------------------------------------------- replay


@dataclass
class ReplayArgs:
    repo: str
    machine: str
    bwlimit: str
    kill_after: int
    poll: float
    lineage: str | None
    snapshot_timeout: float = SNAPSHOT_TIMEOUT_S


def replay(rdc: Rdc, lister: Lister, a: ReplayArgs, report: Report) -> None:
    deps = rdc.deps
    ref = "%s@%s" % (a.repo, a.machine)
    before = rdc.reconcile(ref, dry_run=True)
    subscription = before.get("subscriptionId") or ""
    lineage = a.lineage or next(
        (row.get("lineageGuid") for row in before.get("lineages") or [] if row.get("lineageGuid")),
        None,
    )
    if not subscription or not lineage:
        raise NoVerdictError(
            "the reconcile dry run named no subscription or no lineage for %s; pass --lineage" % ref
        )
    report.line(
        NOTE,
        "target",
        "subscription %s, lineage %s, bucket %s" % (subscription, lineage, lister.bucket.name),
    )
    if "RUNNING" in rdc.on_machine(a.machine, RUNNING_COMMAND):
        raise NoVerdictError(
            "a renet backup snapshot already runs on %s; the kill would hit it" % a.machine
        )

    base = lister.list(subscription, lineage).of(lineage)
    report.line(NOTE, "baseline", "%d chunks, %d manifests" % (base.chunks, base.manifests))

    stamp = deps.now().strftime("%Y%m%dT%H%M%SZ")
    out_path = deps.workdir / ("backup-meter-replay-%s.out" % stamp)
    err_path = deps.workdir / ("backup-meter-replay-%s.err" % stamp)
    proc = deps.spawner(
        rdc.argv("-o", "json", "backup", "snapshot", ref, "--bwlimit", a.bwlimit),
        out_path,
        err_path,
    )
    started = deps.clock()
    uploaded = 0
    while True:
        deps.sleep(a.poll)
        uploaded = lister.list(subscription, lineage).of(lineage).chunks - base.chunks
        if uploaded >= a.kill_after:
            break
        if proc.poll() is not None:
            raise NoVerdictError(
                "the throttled snapshot ended (rc=%s) after %d new chunks, before %d: use a lineage "
                "with more unuploaded data or a lower --bwlimit (output in %s)"
                % (proc.poll(), uploaded, a.kill_after, err_path)
            )
        if deps.clock() - started > a.snapshot_timeout:
            proc.kill()
            raise NoVerdictError(
                "no %d new chunks within %.0f s" % (a.kill_after, a.snapshot_timeout)
            )
    killed_at = deps.now()
    answer = rdc.on_machine(a.machine, KILL_COMMAND)
    if "GONE" not in answer:
        proc.kill()
        raise NoVerdictError("renet backup snapshot still runs on %s after SIGKILL" % a.machine)
    try:
        client_rc: int | None = proc.wait(timeout=CLIENT_EXIT_WAIT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        client_rc = None
    after_kill = lister.list(subscription, lineage).of(lineage)
    report.line(
        NOTE,
        "killed run",
        "SIGKILL at %d new chunks (%d listed after the kill), client rc=%s"
        % (uploaded, after_kill.chunks - base.chunks, client_rc),
    )
    if client_rc == 0 or after_kill.manifests != base.manifests:
        raise NoVerdictError(
            "the killed run committed (client rc=%s, manifests %d -> %d): the kill came too late"
            % (client_rc, base.manifests, after_kill.manifests)
        )

    rc, stdout, stderr = rdc.run(
        "-o", "json", "backup", "snapshot", ref, timeout=a.snapshot_timeout
    )
    record = last_object(stdout) or {}
    if rc != 0:
        report.line(FAIL, "rerun", "rc=%d: %s" % (rc, (stderr or stdout).strip()[-400:]))
        return
    report.line(
        PASS,
        "rerun",
        "rc=0, snapshot %s, chunksUploaded %s"
        % (record.get("snapshotId", "?"), record.get("chunksUploaded", "?")),
    )
    if record.get("lineage") and record["lineage"] != lineage:
        raise NoVerdictError(
            "the rerun committed to lineage %s, not %s" % (record["lineage"], lineage)
        )

    listing, usage = stable_listing(lambda: lister.list(subscription, lineage), rdc.usage)
    got = listing.of(lineage)
    if got.manifests != base.manifests + 1:
        report.line(
            FAIL,
            "rerun manifest",
            "manifests %d -> %d, expected +1" % (base.manifests, got.manifests),
        )
    row = usage_lineage(usage, lineage)
    if row is None:
        report.line(FAIL, "usage lineage row", "backup usage has no row for %s" % lineage)
    else:
        report.equal("lineage chunkCount", int(row.get("chunkCount", -1)), got.chunks)
        report.equal("lineage storedBytes", int(row.get("storedBytes", -1)), got.chunk_bytes)
    check_rc = rdc.check(ref)
    report.line(
        PASS if check_rc == 0 else FAIL if check_rc == 1 else UNKNOWN,
        "reconcile --check",
        "rc=%d" % check_rc,
    )
    if crosses_maintenance(killed_at, deps.now()):
        report.line(
            UNKNOWN,
            "window",
            "the run spans 03:00 UTC: the nightly re-bill may have healed the meter",
        )


# ---------------------------------------------------------------- census


def _lineage_rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in doc.get("lineages") or [] if row.get("lineageGuid")]


def census(rdc: Rdc, lister: Lister, apply: bool, strict: Sequence[str], report: Report) -> None:
    before = rdc.reconcile(None, dry_run=True)
    subscription = before.get("subscriptionId") or ""
    if not subscription:
        raise NoVerdictError("the reconcile dry run named no subscription")
    report.line(
        NOTE,
        "before",
        "ledger %s B / %s chunks, bucket %s B / %s chunks, drift %s B"
        % (
            before.get("ledgerBytes"),
            before.get("ledgerChunkCount"),
            before.get("bucketChunkBytes"),
            before.get("bucketChunkCount"),
            before.get("driftBytes"),
        ),
    )
    for row in _lineage_rows(before):
        report.line(
            NOTE,
            "before " + row["lineageGuid"][:8],
            "ledger %s/%s observed %s/%s"
            % (
                row.get("ledgerBytesBefore"),
                row.get("ledgerChunksBefore"),
                row.get("observedBytes"),
                row.get("observedChunks"),
            ),
        )
    if apply:
        applied = rdc.reconcile(None, dry_run=False)
        n = sum(1 for row in _lineage_rows(applied) if row.get("applied"))
        report.line(NOTE, "apply", "%d lineage(s) applied" % n)

    listing, usage = stable_listing(lambda: lister.list(subscription), rdc.usage)
    report.equal("total chunkCount", int(usage.get("chunkCount", -1)), listing.chunks)
    report.equal("total storedBytes", int(usage.get("storedBytes", -1)), listing.chunk_bytes)
    metered = {
        row["lineageGuid"]: row for row in usage.get("lineages") or [] if row.get("lineageGuid")
    }
    for lineage in sorted(set(metered) | set(listing.lineages)):
        got = listing.of(lineage)
        row = metered.get(lineage, {})
        report.equal(lineage[:8] + " chunkCount", int(row.get("chunkCount", 0)), got.chunks)
        report.equal(lineage[:8] + " storedBytes", int(row.get("storedBytes", 0)), got.chunk_bytes)

    after = rdc.reconcile(None, dry_run=True)
    seen = set()
    for row in _lineage_rows(after):
        lineage = row["lineageGuid"]
        seen.add(lineage)
        got = listing.of(lineage)
        if row.get("skipped"):
            report.line(
                UNKNOWN, lineage[:8] + " refset", "skipped by the server (%s)" % row["skipped"]
            )
            continue
        ref_c, unref_c = int(row.get("referencedChunks", 0)), int(row.get("unreferencedChunks", 0))
        ref_b, unref_b = int(row.get("referencedBytes", 0)), int(row.get("unreferencedBytes", 0))
        report.equal(lineage[:8] + " ref+unref chunks", ref_c + unref_c, got.chunks)
        report.equal(lineage[:8] + " ref+unref bytes", ref_b + unref_b, got.chunk_bytes)
        report.line(
            NOTE,
            lineage[:8] + " unreferenced",
            "%d chunks, %d B, %s past grace"
            % (unref_c, unref_b, row.get("unreferencedPastGraceChunks", "?")),
        )
        if lineage in strict:
            report.equal(lineage[:8] + " stored=referenced", got.chunk_bytes, ref_b)
    for lineage in sorted(set(listing.lineages) - seen):
        if listing.of(lineage).chunks:
            report.line(
                FAIL,
                lineage[:8] + " refset",
                "listed chunks, but the reconcile names no such lineage",
            )
    for lineage in strict:
        if lineage not in seen:
            report.line(
                UNKNOWN, lineage[:8] + " stored=referenced", "the reconcile names no such lineage"
            )
    check_rc = rdc.check(None)
    report.line(
        PASS if check_rc == 0 else FAIL if check_rc == 1 else UNKNOWN,
        "reconcile --check",
        "rc=%d" % check_rc,
    )


# ---------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rediacc_ci.ops.backup_meter_replay", description=(__doc__ or "").splitlines()[0]
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("replay", "census"):
        p = sub.add_parser(name)
        p.add_argument(
            "--config", required=True, help="the rdc config (no default: bare targets production)"
        )
        p.add_argument(
            "--channel", default="bench", choices=pbc.TARGETS, help="whose backup bucket to list"
        )
        p.add_argument("--region", default=None, help="a regions.json id (stable and edge)")
        p.add_argument("--rdc", default=str(paths.repo_root() / "rdc.sh"))
        if name == "replay":
            p.add_argument("--repo", required=True)
            p.add_argument("--machine", required=True)
            p.add_argument(
                "--bwlimit", default="2MB", help="the throttle of the run that is killed"
            )
            p.add_argument(
                "--kill-after", type=int, default=50, help="new chunks listed before the kill"
            )
            p.add_argument("--poll", type=float, default=5.0, help="seconds between listings")
            p.add_argument("--lineage", default=None, help="override the lineage the dry run names")
        else:
            p.add_argument("--apply", action="store_true", help="apply the reconcile (step 2)")
            p.add_argument("--strict-referenced", action="append", default=[], metavar="LINEAGE")
    return parser


def main(
    argv: list[str] | None = None,
    transport: Transport = default_transport,
    environ: dict[str, str] | None = None,
    deps: Deps | None = None,
    out: TextIO | None = None,
) -> int:
    out = sys.stdout if out is None else out
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    report = Report(out)
    try:
        if args.cmd == "replay" and args.kill_after < 1:
            raise ConfigError("--kill-after must be at least 1")
        lister = make_lister(
            args.channel, args.region, scope.read_env() if environ is None else environ, transport
        )
        rdc = Rdc(args.rdc, args.config, deps or Deps())
        if args.cmd == "replay":
            replay(
                rdc,
                lister,
                ReplayArgs(
                    args.repo, args.machine, args.bwlimit, args.kill_after, args.poll, args.lineage
                ),
                report,
            )
        else:
            census(rdc, lister, args.apply, args.strict_referenced, report)
    except (ConfigError, scope.ConfigError) as exc:
        print("backup meter %s: %s" % (args.cmd, exc), file=sys.stderr)
        return 2
    except NoVerdictError as exc:
        report.line(UNKNOWN, args.cmd, str(exc))
    rc = report.exit_code()
    summary = {
        0: "the meter equals the store",
        1: "the meter DISAGREES with the store",
        2: "no verdict",
    }
    print("backup meter %s: %s (exit %d)" % (args.cmd, summary[rc], rc), file=out, flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
