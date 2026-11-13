"""Inventory, cross-bucket copy and parity check for R2 buckets (PLAN-product-domain-rename W1), and the move of a bucket between jurisdictions (PLAN-d1-eu-jurisdiction W2).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --inventory [--bucket B ...] [--jurisdiction eu]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --copy   --from SRC --to DST [--jurisdiction eu] [--dry-run]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --verify --from SRC --to DST [--jurisdiction eu] [--deep]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --relocate --from B --from-jurisdiction default --to B --to-jurisdiction eu [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.r2_bucket_copy --verify --from B --from-jurisdiction default --to B --to-jurisdiction eu [--deep]

It reuses the `r2_promote` plumbing (listing, retried `aws s3api copy-object`, `check_sizes`) with the bucket made a parameter, so there is one copy path and no rclone.

COPY. Every object moves with one server-side CopyObject and `--metadata-directive COPY`, so content type, cache control and user metadata arrive as the source had them. The run is re-runnable: a key whose destination has the same size and is not older than the source is skipped (`r2_promote.unchanged`), so a second run copies only the delta. That rule sees new keys, size changes and newer sources; a metadata-only change on a source object (same size, same bytes) is NOT detected and is not re-copied. A same-size change of the bytes under an older mtime is caught by the single-part ETag comparison and re-copied. Nothing is deleted from the destination. An object over `COPY_OBJECT_MAX_BYTES` (5 GiB) is refused for the whole run before anything is copied (`check_sizes`); `--inventory` lists each such object so the live inventory shows them first.

VERIFY. Exit 0 only when the destination holds the same key set, the same object count and the same total size as the source, and per key the same size, plus the same ETag where both sides report a single-part one (no `-` in it), which catches same-size content drift. Any difference is printed and exits 1. `--deep` adds a sha256 of every key on both sides (each object is read in full from both endpoints), which catches what a listing cannot: a multipart ETag, or same-size bytes that differ.

JURISDICTION. R2 jurisdiction is set when a bucket is created and `.eu.` is the only endpoint that sees an EU bucket: without `--jurisdiction eu` a default-jurisdiction bucket of the same name appears with no error. The flag rewrites the endpoint host to `<account>.eu.r2.cloudflarestorage.com` and applies to BOTH buckets, because one CopyObject goes to one endpoint; `--copy` between jurisdictions is refused by construction.

RELOCATE (agent/plans/PLAN-d1-eu-jurisdiction.md, Design 4). A same-name bucket can exist once per jurisdiction, so moving `configs-bench` into jurisdiction eu means a second `configs-bench` behind the `.eu.` endpoint and a copy between the two endpoints. One CopyObject cannot span endpoints, so `--relocate` streams each object through a temporary file: `get-object` from the source endpoint, `put-object` to the destination endpoint with the content type, cache control, disposition, encoding, language, expiry and user metadata the GET answered. The delta rule is COPY's, so a re-run moves only what is missing or stale. Bucket settings (CORS, lifecycle rules, event notifications, read and written through the Cloudflare API with the `cf-r2-jurisdiction` header) are copied, then read back and asserted equal; any difference exits 1. Without `--write` it prints the delta and the settings that would change, and changes nothing. `--from-jurisdiction` and `--to-jurisdiction` take `default`, `eu` or `fedramp` and replace `--jurisdiction`; with them `--verify` also asserts the bucket settings equal.

Credentials are the usual aws-cli ones (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), supplied through `bws_env exec`. The endpoint is `--endpoint`, else `CLOUDFLARE_R2_ENDPOINT`, else the default account's. The bucket settings use CLOUDFLARE_API_TOKEN (or the Global API Key pair) and CLOUDFLARE_ACCOUNT_ID.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci import log
from rediacc_ci.core import awscli
from rediacc_ci.deploy import r2_promote, transfer_retry
from rediacc_ci.ops import cf_auth
from rediacc_ci.ops import observability_volume as ov
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

SELF = "r2_bucket_copy"
RETRY_DELAY_S = 5.0
JURISDICTIONS = ("eu", "fedramp")
# `--from-jurisdiction`/`--to-jurisdiction` values: `default` is the bucket with no jurisdiction.
SIDES = ("default", *JURISDICTIONS)
JURISDICTION_HEADER = "cf-r2-jurisdiction"
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
VERSION_SUFFIX_RE = r2_promote.VERSION_SUFFIX_RE
ENDPOINT_HOST_RE = re.compile(r"^(https://[0-9a-f]+)(\.[a-z]+)?(\.r2\.cloudflarestorage\.com.*)$")
# The object headers a GetObject answers and a PutObject takes back, as (reply field, put-object flag).
PUT_FIELDS = (
    ("ContentType", "--content-type"),
    ("CacheControl", "--cache-control"),
    ("ContentDisposition", "--content-disposition"),
    ("ContentEncoding", "--content-encoding"),
    ("ContentLanguage", "--content-language"),
    ("Expires", "--expires"),
)
HASH_CHUNK = 1 << 20
SETTING_KINDS = ("cors", "lifecycle", "notifications")


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
    try:
        reply = json.loads(text)
        return sorted(entry["Name"] for entry in reply.get("Buckets") or [])
    except (ValueError, AttributeError, KeyError, TypeError) as exc:
        raise CopyError("list-buckets returned an unreadable reply: %s" % exc) from exc


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
    """The source objects the destination lacks or holds stale: the delta. The sync skip rule decides, and a key it would skip is still copied when both sides report a single-part ETag and the two differ, so a same-size content change under an older mtime is repaired by a re-run, as VERIFY reports it."""
    have = {o.rel: o for o in dst}
    return [o for o in src if not _skippable(o, have.get(o.rel))]


def _skippable(src: r2_promote.Obj, dst: r2_promote.Obj | None) -> bool:
    if dst is None or not r2_promote.unchanged(src, dst):
        return False
    return not (_single_part(src.etag) and _single_part(dst.etag) and src.etag != dst.etag)


def _single_part(etag: str) -> bool:
    """A non-empty ETag with no `-<parts>` suffix: the MD5 of the bytes, comparable across buckets."""
    return bool(etag) and "-" not in etag


def parity(src: list[r2_promote.Obj], dst: list[r2_promote.Obj]) -> list[str]:
    """Every difference between the two listings as one line each; empty means parity of count, total size, keys, per-key size and, where both sides report a single-part ETag, that ETag."""
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
    se = {o.rel: o.etag for o in src}
    de = {o.rel: o.etag for o in dst}
    problems += [
        "etag differs: %s (source %s, destination %s)" % (k, se[k], de[k])
        for k in sorted(s.keys() & d.keys())
        if s[k] == d[k] and _single_part(se[k]) and _single_part(de[k]) and se[k] != de[k]
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
    risky = [o.rel for o in source if VERSION_SUFFIX_RE.search(o.rel)]
    if risky:
        raise CopyError(
            "key(s) ending in ?versionId=... would be read by aws-cli as a version id: %s"
            % ", ".join(risky[:5])
        )
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


# --- relocate: one bucket name, two endpoints -------------------------------------------------------


def side(value: str) -> str | None:
    """A `--from-jurisdiction`/`--to-jurisdiction` value as `endpoint_for` takes it."""
    return None if value == "default" else value


def get_object_argv(endpoint: str, bucket: str, key: str, path: str) -> list[str]:
    return [
        awscli.AWS,
        "s3api",
        "get-object",
        "--bucket",
        bucket,
        "--key",
        key,
        path,
        *r2_promote.endpoint_args(endpoint),
        "--output",
        "json",
    ]


def put_object_argv(endpoint: str, bucket: str, key: str, path: str, head: dict) -> list[str]:
    """`put-object` carrying every header of `head` (a get-object reply) that PUT_FIELDS names, and its user metadata."""
    argv = [awscli.AWS, "s3api", "put-object", "--bucket", bucket, "--key", key, "--body", path]
    for field, flag in PUT_FIELDS:
        value = head.get(field)
        if isinstance(value, str) and value:
            argv += [flag, value]
    metadata = head.get("Metadata")
    if isinstance(metadata, dict) and metadata:
        argv += ["--metadata", json.dumps(metadata, sort_keys=True, separators=(",", ":"))]
    return [*argv, *r2_promote.endpoint_args(endpoint), "--output", "json"]


def _aws(argv: list[str], what: str) -> str:
    """One retried aws call; its stdout, or CopyError naming the call. Its stderr is forwarded."""
    out: list[bytes] = []

    def run() -> tuple[int, str]:
        proc = awscli.run(argv, capture_output=True)
        if proc.stderr:
            sys.stderr.buffer.write(proc.stderr)
            sys.stderr.flush()
        out[:] = [proc.stdout]
        return proc.returncode, proc.stderr.decode("utf-8", errors="replace")

    sys.stdout.flush()
    sys.stderr.flush()
    status = transfer_retry.retried(run, what, SELF, RETRY_DELAY_S)
    if status:
        raise CopyError("%s failed (exit %d)" % (what, status))
    return out[0].decode("utf-8", errors="replace") if out else ""


def fetch_object(endpoint: str, bucket: str, key: str, path: str) -> dict:
    """Download one object into `path`; returns the get-object reply (its headers and metadata)."""
    what = "get of %s/%s" % (bucket, key)
    try:
        head = json.loads(_aws(get_object_argv(endpoint, bucket, key, path), what))
    except ValueError as exc:
        raise CopyError("%s answered no JSON head" % what) from exc
    if not isinstance(head, dict):
        raise CopyError("%s answered no JSON head" % what)
    return head


def store_object(endpoint: str, bucket: str, key: str, path: str, head: dict) -> None:
    _aws(put_object_argv(endpoint, bucket, key, path, head), "put of %s/%s" % (bucket, key))


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_sha256(endpoint: str, bucket: str, key: str) -> str:
    with tempfile.TemporaryDirectory(prefix="r2-relocate.") as tmp:
        path = os.path.join(tmp, "object")
        fetch_object(endpoint, bucket, key, path)
        return file_sha256(path)


def move_object(src_ep: str, src: str, dst_ep: str, dst: str, key: str) -> None:
    """GetObject from one endpoint, PutObject to the other, through a temporary file."""
    with tempfile.TemporaryDirectory(prefix="r2-relocate.") as tmp:
        path = os.path.join(tmp, "object")
        store_object(dst_ep, dst, key, path, fetch_object(src_ep, src, key, path))


class Settings:
    """A bucket's CORS, lifecycle and event-notification settings over the Cloudflare API, per jurisdiction."""

    def __init__(self, transport: ov.Transport, headers: Mapping[str, str], account: str) -> None:
        self.transport = transport
        self.headers = dict(headers)
        self.account = account

    def _result(
        self, method: str, path: str, jurisdiction: str | None, body: object | None = None
    ) -> object:
        headers = dict(self.headers)
        if jurisdiction:
            headers[JURISDICTION_HEADER] = jurisdiction
        url = "%s/accounts/%s%s" % (CF_API_BASE, self.account, path)
        status, answer = self.transport(method, url, headers, body)
        # A bucket with no CORS or notification configuration answers 404 to the GET, and to the DELETE of that configuration.
        if status == 404 and method in ("GET", "DELETE"):
            return None
        if status != 200 or not isinstance(answer, dict) or not answer.get("success"):
            raise CopyError(
                "Cloudflare API %s %s (jurisdiction %s) answered %s"
                % (method, path, jurisdiction or "default", status or "nothing")
            )
        return answer.get("result")

    def _list(self, path: str, jurisdiction: str | None, key: str) -> list:
        result = self._result("GET", path, jurisdiction)
        return list(result.get(key) or []) if isinstance(result, dict) else []

    def read(self, bucket: str, jurisdiction: str | None) -> dict[str, list]:
        return {
            "cors": self._list("/r2/buckets/%s/cors" % bucket, jurisdiction, "rules"),
            "lifecycle": self._list("/r2/buckets/%s/lifecycle" % bucket, jurisdiction, "rules"),
            "notifications": self._list(
                "/event_notifications/r2/%s/configuration" % bucket, jurisdiction, "queues"
            ),
        }

    def write(self, bucket: str, jurisdiction: str | None, wanted: dict[str, list]) -> None:
        """Make the destination's settings `wanted`: CORS put (or deleted when the source has none), lifecycle put, and one notification configuration per source queue."""
        cors = "/r2/buckets/%s/cors" % bucket
        if wanted["cors"]:
            self._result("PUT", cors, jurisdiction, {"rules": wanted["cors"]})
        else:
            self._result("DELETE", cors, jurisdiction)
        self._result(
            "PUT", "/r2/buckets/%s/lifecycle" % bucket, jurisdiction, {"rules": wanted["lifecycle"]}
        )
        for queue in wanted["notifications"]:
            rules = [
                {k: rule[k] for k in ("prefix", "suffix", "actions", "description") if k in rule}
                for rule in queue.get("rules") or []
            ]
            self._result(
                "PUT",
                "/event_notifications/r2/%s/configuration/queues/%s" % (bucket, queue["queueId"]),
                jurisdiction,
                {"rules": rules},
            )


def normalized_settings(settings: dict[str, list]) -> dict[str, list[str]]:
    """Settings in a form two buckets compare by: notification rules without their server-made `ruleId`/`createdAt` and with sorted actions, every list sorted."""

    def canon(items: list) -> list[str]:
        return sorted(json.dumps(i, sort_keys=True) for i in items)

    queues = []
    for queue in settings.get("notifications") or []:
        rules = []
        for rule in queue.get("rules") or []:
            kept = {k: v for k, v in rule.items() if k not in ("ruleId", "createdAt")}
            if isinstance(kept.get("actions"), list):
                kept["actions"] = sorted(kept["actions"])
            rules.append(kept)
        queues.append({"queueId": queue.get("queueId"), "rules": canon(rules)})
    return {
        "cors": canon(settings.get("cors") or []),
        "lifecycle": canon(settings.get("lifecycle") or []),
        "notifications": canon(queues),
    }


def settings_differences(src: dict[str, list], dst: dict[str, list]) -> list[str]:
    a, b = normalized_settings(src), normalized_settings(dst)
    return [
        "bucket settings differ: %s (source %d, destination %d)"
        % (kind, len(src.get(kind) or []), len(dst.get(kind) or []))
        for kind in SETTING_KINDS
        if a[kind] != b[kind]
    ]


def deep_differences(
    src_ep: str, src: str, dst_ep: str, dst: str, keys: Sequence[str]
) -> list[str]:
    return [
        "sha256 differs: %s" % key
        for key in keys
        if object_sha256(src_ep, src, key) != object_sha256(dst_ep, dst, key)
    ]


def _sides(
    src_ep: str, src: str, dst_ep: str, dst: str
) -> tuple[r2_promote.Transfers, r2_promote.Transfers]:
    if src_ep == dst_ep and src == dst:
        raise CopyError("source and destination are the same bucket: %s" % src)
    return (
        r2_promote.Transfers(SELF, src_ep, RETRY_DELAY_S, bucket=src),
        r2_promote.Transfers(SELF, dst_ep, RETRY_DELAY_S, bucket=dst),
    )


def relocate(
    src_ep: str,
    src: str,
    dst_ep: str,
    dst: str,
    settings: Settings,
    jurisdictions: tuple[str | None, str | None],
    *,
    write: bool = False,
) -> int:
    """Stream the delta of `src` (at `src_ep`) into `dst` (at `dst_ep`), copy the bucket settings, then verify both. Returns the exit status."""
    src_j, dst_j = jurisdictions
    reader, writer = _sides(src_ep, src, dst_ep, dst)
    source = reader.list_tree("")
    r2_promote.check_sizes("%s/" % src, source, SELF)
    todo = plan_copy(source, writer.list_tree(""))
    print(
        "%s: %d of %d object(s) to move %s -> %s, %d bytes"
        % (SELF, len(todo), len(source), src_ep, dst_ep, sum(o.size for o in todo))
    )
    wanted = settings.read(src, src_j)
    changes = settings_differences(wanted, settings.read(dst, dst_j))
    for line in changes:
        print("%s: %s" % (SELF, line))
    if not write:
        for obj in todo:
            print("would move %s" % obj.rel)
        if changes:
            print("%s: would copy the bucket settings" % SELF)
        print("%s: dry run, nothing written (pass --write to relocate)" % SELF)
        return 0
    for obj in todo:
        move_object(src_ep, src, dst_ep, dst, obj.rel)
    if changes:
        settings.write(dst, dst_j, wanted)
    return verify_across(src_ep, src, dst_ep, dst, settings, jurisdictions, deep=False)


def verify_across(
    src_ep: str,
    src: str,
    dst_ep: str,
    dst: str,
    settings: Settings | None,
    jurisdictions: tuple[str | None, str | None],
    *,
    deep: bool,
) -> int:
    """Listing parity, then (with `deep`) a sha256 per key, then (with `settings`) the bucket settings equal."""
    reader, writer = _sides(src_ep, src, dst_ep, dst)
    source, dest = reader.list_tree(""), writer.list_tree("")
    problems = parity(source, dest)
    if deep and not problems:
        problems += deep_differences(src_ep, src, dst_ep, dst, [o.rel for o in source])
    if settings is not None:
        problems += settings_differences(
            settings.read(src, jurisdictions[0]), settings.read(dst, jurisdictions[1])
        )
    for line in problems[:50]:
        print("%s: %s" % (SELF, line), file=sys.stderr)
    if problems:
        print(
            "%s: %d difference(s) between %s and %s" % (SELF, len(problems), src, dst),
            file=sys.stderr,
        )
        return 1
    print(
        "%s: parity %s -> %s: %d object(s), %d bytes%s%s"
        % (
            SELF,
            src,
            dst,
            len(source),
            sum(o.size for o in source),
            ", sha256 equal per key" if deep else "",
            ", bucket settings equal" if settings is not None else "",
        )
    )
    return 0


def settings_from_env(env: Mapping[str, str], transport: ov.Transport) -> Settings:
    try:
        headers = ov.cf_headers(env)
    except ov.VolumeError as exc:
        raise CopyError(str(exc)) from exc
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or cf_auth.DEFAULT_ACCOUNT_ID
    return Settings(transport, headers, account)


def main(
    argv: list[str],
    env: Mapping[str, str] | None = None,
    transport: ov.Transport | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog=SELF, description=__doc__.split("\n", 1)[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inventory", action="store_true")
    mode.add_argument("--copy", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--relocate", action="store_true")
    parser.add_argument("--from", dest="src")
    parser.add_argument("--to", dest="dst")
    parser.add_argument(
        "--bucket", action="append", help="inventory only these buckets (repeatable)"
    )
    parser.add_argument("--jurisdiction", choices=JURISDICTIONS)
    parser.add_argument("--from-jurisdiction", choices=SIDES)
    parser.add_argument("--to-jurisdiction", choices=SIDES)
    parser.add_argument("--endpoint")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true", help="--relocate: write (default: print)")
    parser.add_argument("--deep", action="store_true", help="--verify: sha256 every key")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env
    if not args.inventory and not (args.src and args.dst):
        parser.error("--copy, --verify and --relocate need --from and --to")
    across = args.from_jurisdiction is not None or args.to_jurisdiction is not None
    if across and (args.jurisdiction or None in (args.from_jurisdiction, args.to_jurisdiction)):
        parser.error(
            "--from-jurisdiction and --to-jurisdiction go together, without --jurisdiction"
        )
    if args.relocate and not across:
        parser.error("--relocate needs --from-jurisdiction and --to-jurisdiction")
    if across and not (args.relocate or args.verify):
        parser.error("--from-jurisdiction and --to-jurisdiction apply to --relocate and --verify")
    try:
        base = args.endpoint or os.environ.get("CLOUDFLARE_R2_ENDPOINT") or default_endpoint()
        if args.inventory:
            endpoint = endpoint_for(base, args.jurisdiction)
            report = inventory(endpoint, [check_bucket(b) for b in args.bucket or []])
            print(json.dumps({"endpoint": endpoint, "buckets": report}, indent=2))
            return 0
        src, dst = check_bucket(args.src), check_bucket(args.dst)
        if across:
            sides = (side(args.from_jurisdiction), side(args.to_jurisdiction))
            src_ep, dst_ep = endpoint_for(base, sides[0]), endpoint_for(base, sides[1])
            settings = settings_from_env(env, transport or ov.real_transport)
            if args.relocate:
                return relocate(src_ep, src, dst_ep, dst, settings, sides, write=args.write)
            return verify_across(src_ep, src, dst_ep, dst, settings, sides, deep=args.deep)
        endpoint = endpoint_for(base, args.jurisdiction)
        if args.copy:
            return copy(endpoint, src, dst, args.dry_run)
        if args.deep:
            if src == dst:
                raise CopyError("source and destination are the same bucket: %s" % src)
            return verify_across(endpoint, src, endpoint, dst, None, (None, None), deep=True)
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
