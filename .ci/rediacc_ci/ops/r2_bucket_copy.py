"""Inventory, cross-bucket copy and parity check for R2 buckets (PLAN-product-domain-rename W1).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --inventory [--bucket B ...] [--jurisdiction eu]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --copy   --from SRC --to DST [--jurisdiction eu] [--dry-run]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --verify --from SRC --to DST [--jurisdiction eu]

It reuses the `r2_promote` plumbing (listing, retried `aws s3api copy-object`, `check_sizes`) with the bucket made a parameter, so there is one copy path and no rclone.

COPY. Every object moves with one server-side CopyObject and `--metadata-directive COPY`, so content type, cache control and user metadata arrive as the source had them. The run is re-runnable: a key whose destination has the same size and is not older than the source is skipped (`r2_promote.unchanged`), so a second run copies only the delta. Nothing is deleted from the destination. An object over `COPY_OBJECT_MAX_BYTES` (5 GiB) is refused for the whole run before anything is copied (`check_sizes`); `--inventory` lists each such object so the live inventory shows them first.

VERIFY. Exit 0 only when the destination holds the same key set, the same object count and the same total size as the source, and per key the same size. Any difference is printed and exits 1.

JURISDICTION. R2 jurisdiction is set when a bucket is created and `.eu.` is the only endpoint that sees an EU bucket: without `--jurisdiction eu` a default-jurisdiction bucket of the same name appears with no error. The flag rewrites the endpoint host to `<account>.eu.r2.cloudflarestorage.com` and applies to BOTH buckets, because one CopyObject goes to one endpoint; a copy between jurisdictions is refused by construction.

Credentials are the usual aws-cli ones (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), supplied through `bws_env exec`. The endpoint is `--endpoint`, else `CLOUDFLARE_R2_ENDPOINT`, else the default account's.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING

from rediacc_ci import log
from rediacc_ci.core import awscli
from rediacc_ci.deploy import r2_promote
from rediacc_ci.ops import cf_auth

if TYPE_CHECKING:
    from collections.abc import Sequence

SELF = "r2_bucket_copy"
RETRY_DELAY_S = 5.0
JURISDICTIONS = ("eu", "fedramp")
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
ENDPOINT_HOST_RE = re.compile(r"^(https://[0-9a-f]+)(\.[a-z]+)?(\.r2\.cloudflarestorage\.com.*)$")


class CopyError(Exception):
    """A refusal; the message is the whole explanation."""


def default_endpoint() -> str:
    return "https://%s.r2.cloudflarestorage.com" % cf_auth.DEFAULT_ACCOUNT_ID


def endpoint_for(base: str, jurisdiction: str | None) -> str:
    """`base` with the jurisdiction segment inserted (`https://<acct>.eu.r2.cloudflarestorage.com`). `None` returns `base` unchanged. A base that already names a jurisdiction, or is not an R2 S3 host, is refused when one is requested."""
    if jurisdiction is None:
        return base
    if jurisdiction not in JURISDICTIONS:
        raise CopyError(
            "unknown jurisdiction %r (one of %s)" % (jurisdiction, ", ".join(JURISDICTIONS))
        )
    match = ENDPOINT_HOST_RE.match(base)
    if not match or match.group(2):
        raise CopyError(
            "cannot apply --jurisdiction %s to endpoint %s: expected https://<account>.r2.cloudflarestorage.com"
            % (jurisdiction, base)
        )
    return "%s.%s%s" % (match.group(1), jurisdiction, match.group(3))


def check_bucket(name: str) -> str:
    if not BUCKET_RE.match(name):
        raise CopyError("not a bucket name: %r" % name)
    return name


def parse_buckets(text: str) -> list[str]:
    """The names of a `list-buckets` JSON reply, sorted."""
    if not text.strip():
        return []
    return sorted(entry["Name"] for entry in json.loads(text).get("Buckets") or [])


def list_buckets(endpoint: str) -> list[str]:
    argv = [
        awscli.AWS,
        "s3api",
        "list-buckets",
        *r2_promote.endpoint_args(endpoint),
        "--output",
        "json",
    ]
    proc = awscli.run(argv, capture_output=True)
    if proc.returncode:
        raise CopyError(
            "list-buckets failed: %s" % proc.stderr.decode("utf-8", errors="replace").strip()
        )
    return parse_buckets(proc.stdout.decode("utf-8"))


def summarize(bucket: str, objs: list[r2_promote.Obj]) -> dict[str, object]:
    """Count, total bytes, the largest object, and every object over the single-CopyObject limit."""
    over = [o for o in objs if o.size > r2_promote.COPY_OBJECT_MAX_BYTES]
    largest = max(objs, key=lambda o: o.size, default=None)
    return {
        "bucket": bucket,
        "objects": len(objs),
        "bytes": sum(o.size for o in objs),
        "largest": None if largest is None else {"key": largest.rel, "bytes": largest.size},
        "over_copy_limit": [{"key": o.rel, "bytes": o.size} for o in over],
    }


def inventory(endpoint: str, buckets: Sequence[str] | None) -> list[dict[str, object]]:
    """Read-only: one summary per bucket (every bucket of the endpoint's jurisdiction when none is named)."""
    names = list(buckets) if buckets else list_buckets(endpoint)
    out = []
    for name in names:
        run = r2_promote.Transfers(SELF, endpoint, RETRY_DELAY_S, bucket=name)
        out.append(summarize(name, run.list_tree("")))
    return out


def plan_copy(src: list[r2_promote.Obj], dst: list[r2_promote.Obj]) -> list[r2_promote.Obj]:
    """The source objects the destination lacks or holds stale (the sync skip rule): the delta."""
    have = {o.rel: o for o in dst}
    return [o for o in src if not r2_promote.unchanged(o, have.get(o.rel))]


def parity(src: list[r2_promote.Obj], dst: list[r2_promote.Obj]) -> list[str]:
    """Every difference between the two listings as one line each; empty means parity of count, total size and keys (with per-key size)."""
    problems = []
    if len(src) != len(dst):
        problems.append("object count: source %d, destination %d" % (len(src), len(dst)))
    src_bytes, dst_bytes = sum(o.size for o in src), sum(o.size for o in dst)
    if src_bytes != dst_bytes:
        problems.append(
            "total size: source %d bytes, destination %d bytes" % (src_bytes, dst_bytes)
        )
    s = {o.rel: o.size for o in src}
    d = {o.rel: o.size for o in dst}
    problems += ["missing in destination: %s" % k for k in sorted(s.keys() - d.keys())]
    problems += ["extra in destination: %s" % k for k in sorted(d.keys() - s.keys())]
    problems += [
        "size differs: %s (source %d, destination %d)" % (k, s[k], d[k])
        for k in sorted(s.keys() & d.keys())
        if s[k] != d[k]
    ]
    return problems


def _pair(endpoint: str, src: str, dst: str) -> tuple[r2_promote.Transfers, r2_promote.Transfers]:
    if src == dst:
        raise CopyError("source and destination are the same bucket: %s" % src)
    reader = r2_promote.Transfers(SELF, endpoint, RETRY_DELAY_S, bucket=src)
    writer = r2_promote.Transfers(
        SELF, endpoint, RETRY_DELAY_S, bucket=dst, src_bucket=src, preserve_metadata=True
    )
    return reader, writer


def copy(endpoint: str, src: str, dst: str, dry_run: bool = False) -> int:
    """Copy the delta of `src` into `dst`, then verify parity. Returns the exit status."""
    reader, writer = _pair(endpoint, src, dst)
    source = reader.list_tree("")
    if not source:
        raise CopyError(
            "VACUOUS: %s lists 0 objects; refusing to report a copy that moved nothing" % src
        )
    r2_promote.check_sizes("%s/" % src, source, SELF)
    todo = plan_copy(source, writer.list_tree(""))
    print(
        "%s: %d of %d object(s) to copy, %d bytes"
        % (SELF, len(todo), len(source), sum(o.size for o in todo))
    )
    if dry_run:
        for obj in todo:
            print("would copy %s" % obj.rel)
        return 0
    writer.copy_all([(o.rel, o.rel) for o in todo])
    return verify(endpoint, src, dst)


def verify(endpoint: str, src: str, dst: str) -> int:
    reader, writer = _pair(endpoint, src, dst)
    source, dest = reader.list_tree(""), writer.list_tree("")
    problems = parity(source, dest)
    for line in problems[:50]:
        print("%s: %s" % (SELF, line), file=sys.stderr)
    if problems:
        print(
            "%s: %d difference(s) between %s and %s" % (SELF, len(problems), src, dst),
            file=sys.stderr,
        )
        return 1
    print(
        "%s: parity %s -> %s: %d object(s), %d bytes"
        % (SELF, src, dst, len(source), sum(o.size for o in source))
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=SELF, description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--copy", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--from", dest="src")
    parser.add_argument("--to", dest="dst")
    parser.add_argument(
        "--bucket", action="append", help="inventory only these buckets (repeatable)"
    )
    parser.add_argument("--jurisdiction", choices=JURISDICTIONS)
    parser.add_argument("--endpoint")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not args.inventory and not (args.src and args.dst):
        parser.error("--copy and --verify need --from and --to")
    try:
        base = args.endpoint or os.environ.get("CLOUDFLARE_R2_ENDPOINT") or default_endpoint()
        endpoint = endpoint_for(base, args.jurisdiction)
        if args.inventory:
            report = inventory(endpoint, [check_bucket(b) for b in args.bucket or []])
            print(json.dumps({"endpoint": endpoint, "buckets": report}, indent=2))
            return 0
        src, dst = check_bucket(args.src), check_bucket(args.dst)
        if args.copy:
            return copy(endpoint, src, dst, args.dry_run)
        return verify(endpoint, src, dst)
    except CopyError as exc:
        log.error(str(exc))
        return 1
    except r2_promote.PromoteError as exc:
        return exc.status or 1
    except (awscli.AwsCliMissingError, subprocess.SubprocessError, OSError) as exc:
        log.error(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
