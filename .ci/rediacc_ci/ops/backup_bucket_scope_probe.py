"""Prove one channel's backup key pair is scoped to its own regional backup buckets and nothing else.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile backup-push-<channel> -- \\
      PYTHONPATH=.ci python3 -m rediacc_ci.ops.backup_bucket_scope_probe --channel stable|edge|bench [--region eu|us|asia ...]

WHY IT EXISTS. Each channel's Workers presign backup grants with a key pair minted as Object Read and Write on that channel's backup buckets only (agent/plans/_done/PLAN-backup-credential-isolation.md B5-B8). Nothing proved the scope after minting: a pair minted account-wide would serve every backup flow identically and pass every functional check. This probe asks R2 itself (agent/plans/PLAN-backup-plane-shared-bucket-hardening.md C1).

THE LEGS, PER REGION OF THE CHANNEL (bench has one bucket and no region):

  1. PUT a small random object under `probe/scope-<utc stamp>-<random>/` in the region's own backup bucket. A 2xx passes; anything else contradicts the scope (the pair must write there).
  2. GET it back and compare the bytes. A 2xx with identical bytes passes; a refusal or different bytes contradict the scope.
  3. DELETE it. A 2xx passes. A 403 is reported, not failed, with what a read-only GET ?lifecycle on the bucket answers: the backup buckets carry no lifecycle by design (`r2_lifecycle.PROTECTED_PATTERNS`, the Worker's chunk GC is authoritative), so a refused DELETE leaves the probe object behind.
  4. LIST (ListObjectsV2, max-keys=1) the same channel's config bucket of the region, and the same region's backup bucket of another channel (bench: the stable us backup bucket). Each MUST answer 403; a 2xx is the headline failure (the pair reaches a bucket it was never meant to), and any other status is no verdict.

Bucket names and jurisdictions come from `push_backup_credentials.plan` (regions.json, cross-checked against each Worker's wrangler config) and the endpoint per bucket from `set_account_worker_secrets.apply_jurisdiction`; requests are signed by `drills.wire.sigv4_headers`. Nothing here restates a naming rule.

CREDENTIALS come only from the environment, under the unsuffixed names the `backup-push-<channel>` profile binds (.ci/config/secret-supply.json); a suffixed name present is refused, as `push_backup_credentials` refuses it. Each printed line carries the region, the bucket, the verb and the HTTP status; no key, signature, presigned URL or endpoint host is printed.

Exit 0: every leg of every region passed. Exit 1: a leg contradicted the scope. Exit 2: a usage or configuration error, or a leg with no verdict (a transport error, an unexpected status on a foreign LIST).
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import secrets
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass

from rediacc_ci import paths
from rediacc_ci.deploy import set_account_worker_secrets
from rediacc_ci.drills import wire
from rediacc_ci.ops import push_backup_credentials as pbc

CHANNELS = pbc.TARGETS
# The other channel whose same-region backup bucket a channel's pair must be refused. Bench has no region, so its foreign backup bucket is the stable one of FOREIGN_BENCH_REGION.
OTHER_CHANNEL = {"stable": "edge", "edge": "stable", "bench": "stable"}
FOREIGN_BENCH_REGION = "us"
SIGV4_REGION = "auto"
PREFIX = "probe/scope-"
TIMEOUT = 30.0
CONFIG_BINDING = "CONFIG_BUCKET"

PASS, FAIL, NOTE, UNKNOWN = "PASS", "FAIL", "NOTE", "NO-VERDICT"

# (method, url, body, headers) -> (status, body bytes); raises OSError on a transport failure.
Transport = Callable[[str, str, bytes, dict], tuple[int, bytes]]


class ConfigError(Exception):
    """A usage or configuration problem; printed, and the run exits 2."""


@dataclass(frozen=True)
class Bucket:
    name: str
    jurisdiction: str


@dataclass(frozen=True)
class Target:
    """One region of a channel: its own backup bucket and the buckets its pair must be refused."""

    region: str
    own: Bucket
    foreign: tuple[Bucket, ...]


def _regions(root) -> dict[str, dict]:
    path = root / "regions.json"
    try:
        with open(path, encoding="utf-8") as fh:
            return {r["id"]: r for r in json.load(fh)["regions"]}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ConfigError("%s unreadable: %s" % (path, type(exc).__name__)) from exc


def _bench_config_bucket(root) -> Bucket:
    path = root.joinpath(*pbc.WORKER_DIR) / pbc.BENCH_CONFIG
    try:
        with open(path, "rb") as fh:
            doc = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError("%s unreadable: %s" % (path, type(exc).__name__)) from exc
    for bucket in doc.get("r2_buckets") or []:
        if bucket.get("binding") == CONFIG_BINDING:
            name = bucket.get("bucket_name")
            # An empty name would send the LIST to the account root, where a 403 proves nothing about any bucket.
            if not name:
                raise ConfigError("%s binds %s with no bucket_name" % (path, CONFIG_BINDING))
            return Bucket(name, bucket.get("jurisdiction") or "")
    raise ConfigError("%s binds no %s bucket" % (path, CONFIG_BINDING))


def _own(channel: str, region: str | None, root) -> Bucket:
    try:
        p = pbc.plan(channel, region, root)
    except pbc.PushError as exc:
        raise ConfigError(str(exc)) from exc
    return Bucket(p.bucket, p.jurisdiction)


def targets(channel: str, regions: list[str] | None, root=None) -> list[Target]:
    """The probe targets of one channel. ConfigError on --region with bench, an unknown region, or a tree whose regions.json and wrangler configs disagree."""
    root = paths.repo_root() if root is None else root
    known = _regions(root)
    other = OTHER_CHANNEL[channel]
    if channel == "bench":
        if regions:
            raise ConfigError("bench has one backup bucket and no regions; drop --region")
        return [
            Target(
                "bench",
                _own("bench", None, root),
                (_bench_config_bucket(root), _own(other, FOREIGN_BENCH_REGION, root)),
            )
        ]
    chosen = list(regions) if regions else list(known)
    unknown = [r for r in chosen if r not in known]
    if unknown:
        raise ConfigError(
            "unknown region %s (regions.json has %s)" % (", ".join(unknown), ", ".join(known))
        )
    out = []
    for region in chosen:
        entry = known[region]
        field = "r2" if channel == "stable" else "edgeR2"
        config = entry.get(field)
        if not isinstance(config, dict) or not config.get("name"):
            raise ConfigError("regions.json region %s has no %s.name" % (region, field))
        jurisdiction = entry.get("r2Jurisdiction") or ""
        out.append(
            Target(
                region,
                _own(channel, region, root),
                (Bucket(config["name"], jurisdiction), _own(other, region, root)),
            )
        )
    return out


def read_env() -> dict[str, str]:
    """The bound names, one explicit `os.environ.get` each so the env registry records each read, plus the suffixed names this probe refuses."""
    env = {
        "ACCOUNT_BACKUP_S3_ENDPOINT": os.environ.get("ACCOUNT_BACKUP_S3_ENDPOINT", ""),
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": os.environ.get("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", ""),
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": os.environ.get(
            "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY", ""
        ),
    }
    for name in pbc.SUFFIXED:
        env[name] = os.environ.get(name, "")
    return env


def credentials(channel: str, environ: dict[str, str]) -> tuple[str, str, str]:
    """(endpoint, access key id, secret). ConfigError naming each missing name, or any suffixed name present."""
    stray = [name for name in pbc.SUFFIXED if environ.get(name)]
    if stray:
        raise ConfigError(
            "refusing: %s in the environment; under backup-push-%s only the unsuffixed pair is bound"
            % (", ".join(stray), channel)
        )
    missing = [name for name in pbc.BOUND if not environ.get(name)]
    if missing:
        raise ConfigError(
            "%s unset; run under `bws_env exec --profile backup-push-%s`"
            % (", ".join(missing), channel)
        )
    return (
        environ["ACCOUNT_BACKUP_S3_ENDPOINT"],
        environ["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"],
        environ["ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"],
    )


def default_transport(method: str, url: str, body: bytes, headers: dict) -> tuple[int, bytes]:
    return wire.http_bytes(
        method, url, body if method == "PUT" else None, headers, json_body=False, timeout=TIMEOUT
    )


class Probe:
    """Runs the legs and keeps the verdicts. Prints names, buckets, verbs and statuses only."""

    def __init__(
        self,
        endpoint: str,
        key_id: str,
        secret: str,
        transport: Transport,
        out,
        now: datetime.datetime | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._key_id = key_id
        self._secret = secret
        self._transport = transport
        self._out = out
        self._now = now
        self.verdicts: list[str] = []

    def _url(self, bucket: Bucket, path: str) -> str:
        base = set_account_worker_secrets.apply_jurisdiction(self._endpoint, bucket.jurisdiction)
        return "%s/%s%s" % (base.rstrip("/"), bucket.name, path)

    def _send(self, method: str, bucket: Bucket, path: str, body: bytes = b"") -> tuple[int, bytes]:
        url = self._url(bucket, path)
        headers = wire.sigv4_headers(
            method, url, body, SIGV4_REGION, self._key_id, self._secret, now=self._now
        )
        return self._transport(method, url, body, headers)

    def _line(self, verdict: str, region: str, bucket: Bucket, verb: str, status, note=""):
        if verdict != NOTE:
            self.verdicts.append(verdict)
        where = bucket.name + (" (%s)" % bucket.jurisdiction if bucket.jurisdiction else "")
        print(
            "%-10s %-6s %-34s %-7s %s%s"
            % (verdict, region, where, verb, status, ("  " + note) if note else ""),
            file=self._out,
            flush=True,
        )

    def _call(self, region, bucket, verb, method, path, body=b"", verdict=UNKNOWN):
        """(status, body), or None after printing a line (no-verdict unless `verdict` says otherwise) for a transport error. The error text never carries the URL's query or headers: only the exception class is printed."""
        try:
            return self._send(method, bucket, path, body)
        except OSError as exc:
            self._line(
                verdict, region, bucket, verb, "---", "transport error (%s)" % type(exc).__name__
            )
            return None

    def run_target(self, t: Target) -> None:
        stamp = (self._now or datetime.datetime.now(datetime.UTC)).strftime("%Y%m%dT%H%M%SZ")
        key = "%s%s-%s/object" % (PREFIX, stamp, secrets.token_hex(4))
        payload = secrets.token_bytes(32)
        path = "/" + key
        got = self._call(t.region, t.own, "PUT", "PUT", path, payload)
        put_ok = False
        if got is not None:
            put_ok = 200 <= got[0] < 300
            self._line(PASS if put_ok else FAIL, t.region, t.own, "PUT", got[0], key)
        if put_ok:
            got = self._call(t.region, t.own, "GET", "GET", path)
            if got is not None:
                status, body = got
                if not 200 <= status < 300:
                    self._line(FAIL, t.region, t.own, "GET", status)
                elif body != payload:
                    self._line(FAIL, t.region, t.own, "GET", status, "bytes differ from the PUT")
                else:
                    self._line(PASS, t.region, t.own, "GET", status, "bytes match")
            got = self._call(t.region, t.own, "DELETE", "DELETE", path)
            if got is not None:
                status = got[0]
                if 200 <= status < 300:
                    self._line(PASS, t.region, t.own, "DELETE", status)
                elif status == 403:
                    self._line(
                        NOTE, t.region, t.own, "DELETE", status, "refused; %s left behind" % key
                    )
                    self._lifecycle(t)
                else:
                    self._line(FAIL, t.region, t.own, "DELETE", status)
        for foreign in t.foreign:
            got = self._call(t.region, foreign, "LIST", "GET", "?list-type=2&max-keys=1")
            if got is None:
                continue
            status = got[0]
            if status == 403:
                self._line(
                    PASS, t.region, foreign, "LIST", status, "refused, as the scope requires"
                )
            elif 200 <= status < 300:
                self._line(
                    FAIL, t.region, foreign, "LIST", status, "a FOREIGN bucket answered the pair"
                )
            else:
                self._line(UNKNOWN, t.region, foreign, "LIST", status, "expected 403")

    def _lifecycle(self, t: Target) -> None:
        """Read-only: what GET ?lifecycle answers on the own bucket, so a left-behind probe object is reported with its fate."""
        got = self._call(t.region, t.own, "LIFECYCLE", "GET", "?lifecycle", verdict=NOTE)
        if got is None:
            return
        status, body = got
        if 200 <= status < 300:
            note = "a rule names probe/" if b"probe/" in body else "no rule names probe/"
        elif status == 404:
            note = "no lifecycle configuration"
        else:
            note = "not readable with this pair"
        self._line(NOTE, t.region, t.own, "LIFECYCLE", status, note)

    def exit_code(self) -> int:
        if FAIL in self.verdicts:
            return 1
        if UNKNOWN in self.verdicts or not self.verdicts:
            return 2
        return 0


def probe(
    channel: str,
    found: list[Target],
    environ: dict[str, str],
    transport: Transport = default_transport,
    out=None,
    now: datetime.datetime | None = None,
) -> int:
    out = sys.stdout if out is None else out
    endpoint, key_id, secret = credentials(channel, environ)
    runner = Probe(endpoint, key_id, secret, transport, out, now)
    print("backup bucket scope probe: channel %s" % channel, file=out, flush=True)
    for t in found:
        runner.run_target(t)
    rc = runner.exit_code()
    summary = {0: "every leg passed", 1: "the scope is CONTRADICTED", 2: "no verdict on a leg"}
    print("backup bucket scope probe: %s (exit %d)" % (summary[rc], rc), file=out, flush=True)
    return rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rediacc_ci.ops.backup_bucket_scope_probe",
        description=(__doc__ or "").splitlines()[0],
    )
    parser.add_argument("--channel", required=True, choices=CHANNELS)
    parser.add_argument(
        "--region",
        action="append",
        default=None,
        help="a regions.json id (repeatable; stable and edge)",
    )
    return parser


def main(
    argv: list[str] | None = None, transport: Transport = default_transport, environ=None
) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        found = targets(args.channel, args.region)
        return probe(args.channel, found, read_env() if environ is None else environ, transport)
    except ConfigError as exc:
        print("backup bucket scope probe: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
