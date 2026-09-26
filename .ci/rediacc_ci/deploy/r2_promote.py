"""The server-side edge -> stable copy both release promotes use (operator ruling 2026-09-26, "Server-side copy").

WHY. Both promotes used to download each `<dir>/edge/` tree (about 67 GB of release history across the five trees on 2026-09-25) to the runner and upload it again to `<dir>/stable/`. That took 4+ hours and could outlive the job's minted R2 token. Here the bytes never leave R2: every object is copied with one CopyObject inside the bucket, and the runner moves only JSON listings and the four small channel-pointer files.

WHY `aws s3api copy-object` AND NOT `aws s3 cp/sync s3://... s3://...`. R2 does not implement the object-tagging surface, and aws-cli v2's high-level s3-to-s3 copy reaches for it under every `--copy-props` value: `default` calls GetObjectTagging on a multipart copy, and `none` / `metadata-directive` send `x-amz-tagging-directive: REPLACE`, which R2 answers with `NotImplemented` on every object. That was measured in CI (run 32465461193) and is recorded in `.ci/scripts/deploy/simulate-promotion.sh`, which has promoted server-side with this exact `copy-object` shape since then. `copy-object` sends only the parameters named.

THE METADATA IS THE SAME AS THE OLD UPLOAD'S. `--metadata-directive REPLACE` with `--cache-control no-cache` and `--content-type` from `mimetypes.guess_type(key)`, which is how `aws s3 cp <local> s3://...` chose the content type when the promotes uploaded from the runner. A key with no guessable type gets no `--content-type`, again as the upload did.

R2 LIMITS. A single CopyObject is capped at 5 GiB (R2's single-part object limit); a bigger object needs a multipart UploadPartCopy, which is not implemented here. `check_sizes` refuses such a tree BEFORE anything is copied, rather than failing half-way. Every release object today is well under that (the largest are ~400 MB packages).

THE PLAN PER TREE (`promote_tree`):
  1. List `<dir>/edge/` and `<dir>/stable/` (ListObjectsV2, JSON: exact keys, sizes, LastModified). An empty edge tree is refused (`VACUOUS:`) before anything else.
  2. Fetch the tree's channel pointers from edge (`channel_stamp.REWRITES`: `cli/install.sh`, `cli/install.ps1`, `rpm/rediacc.repo`, `archlinux/rediacc.conf`) and stamp them for stable locally. A stamp that does not take refuses here, before any write to stable. These are the ONLY objects the runner downloads.
  3. Copy the rest, phase by phase, server-side. The pointers are EXCLUDED from every phase whatever its filters say, so an edge-defaulted installer never reaches `stable/`, not even for the seconds between a copy and a rewrite. Each phase finishes before the next starts. A key whose stable copy already has the same size and is not older is skipped (the rule `aws s3 sync` applied to the old upload).
  4. Upload the stamped pointers LAST. See `POINTERS_GO_LAST`.
  5. List `<dir>/stable/` again. Every promoted key must be there, or the run refuses (`INCOMPLETE:`) and purges nothing. The purge URLs are the promoted keys confirmed by that listing, in listing order.
"""

from __future__ import annotations

import datetime
import fnmatch
import json
import mimetypes
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from rediacc_ci.deploy import channel_stamp, transfer_retry

BUCKET = "rediacc-releases"
PUBLIC_HOST = "https://releases.rediacc.com"
CC_MUTABLE = "no-cache"

# R2's single-part object limit, which bounds one CopyObject. 5 GiB, taken as 5 * 10^9 to stay clear of the edge.
COPY_OBJECT_MAX_BYTES = 5 * 1000**3

# Parallel CopyObject calls. The copies are independent and server-side, so the width bounds request concurrency, not bandwidth. Same width as `simulate_promotion.COPY_WIDTH`.
COPY_WIDTH = 8

# THE ORDER THAT KEEPS A CLIENT CONSISTENT. A pointer is the ENTRY point a client reads first (`install.sh` -> manifest -> binaries; `rediacc.repo` -> repomd -> rpms; `rediacc.conf` -> the pacman db). Written LAST, a client that sees the new pointer finds everything it names already in stable; until then the previous pointer, itself stable-stamped by the previous promote, stays in place and still names objects that exist. Written first, a new installer could name a manifest or package not copied yet. A run that dies part-way leaves the previous pointer, never an edge one.
POINTERS_GO_LAST = True
BULK_IS_SERVER_SIDE = True


class PromoteError(Exception):
    """A refusal or a failed transfer. The message has already been printed; `status` is the exit code."""

    def __init__(self, status: int) -> None:
        super().__init__("exit %d" % status)
        self.status = status


@dataclass(frozen=True)
class Obj:
    """One listed object, keyed relative to its tree prefix."""

    rel: str
    size: int
    modified: datetime.datetime


def endpoint_args(endpoint: str) -> list[str]:
    """`--endpoint-url <endpoint>`, word-split the way both bash twins split their unquoted `$EP`."""
    return ("--endpoint-url %s" % endpoint).split()


def tree(dir_name: str, channel: str) -> str:
    return "%s/%s/" % (dir_name, channel)


def channel_url(dir_name: str, rel: str) -> str:
    """`https://releases.rediacc.com/<dir>/stable/<rel>`."""
    return "%s/%s/stable/%s" % (PUBLIC_HOST, dir_name, rel)


def pointers(dir_name: str) -> tuple[str, ...]:
    """The channel-pointer files of `dir_name`, relative to its tree. Empty for `apt` and `apk`."""
    return tuple(name for name, _ in channel_stamp.REWRITES.get(dir_name, ()))


def list_argv(prefix: str, endpoint: str) -> list[str]:
    """`aws s3api list-objects-v2`: exact keys (no whitespace re-splitting), sizes and LastModified; aws-cli follows the pagination itself."""
    return [
        "aws",
        "s3api",
        "list-objects-v2",
        "--bucket",
        BUCKET,
        "--prefix",
        prefix,
        *endpoint_args(endpoint),
        "--output",
        "json",
    ]


def copy_argv(src_key: str, dst_key: str, endpoint: str) -> list[str]:
    """One server-side `aws s3api copy-object`. No `--tagging-directive`: see the module docstring."""
    argv = [
        "aws",
        "s3api",
        "copy-object",
        "--bucket",
        BUCKET,
        "--key",
        dst_key,
        "--copy-source",
        "%s/%s" % (BUCKET, src_key),
        "--metadata-directive",
        "REPLACE",
        "--cache-control",
        CC_MUTABLE,
    ]
    content_type = mimetypes.guess_type(dst_key)[0]
    if content_type:
        argv += ["--content-type", content_type]
    return [*argv, *endpoint_args(endpoint)]


def get_argv(key: str, target: str, endpoint: str) -> list[str]:
    """Fetch ONE object to the runner. Used for the channel pointers only."""
    return [
        "aws",
        "s3",
        "cp",
        "s3://%s/%s" % (BUCKET, key),
        target,
        *endpoint_args(endpoint),
        "--only-show-errors",
    ]


def put_argv(source: str, key: str, endpoint: str) -> list[str]:
    """Upload ONE stamped pointer, `no-cache` like everything under a channel path."""
    return [
        "aws",
        "s3",
        "cp",
        source,
        "s3://%s/%s" % (BUCKET, key),
        *endpoint_args(endpoint),
        "--only-show-errors",
        "--cache-control",
        CC_MUTABLE,
    ]


def keep(rel: str, filters: tuple[str, ...]) -> bool:
    """aws-cli's `--exclude`/`--include` rule on a key relative to the source prefix: patterns are fnmatch'd in order, the LAST match wins, and the default is include. `*` crosses `/`, as it does in aws-cli."""
    verdict = True
    for i in range(0, len(filters) - 1, 2):
        if fnmatch.fnmatchcase(rel, filters[i + 1]):
            verdict = filters[i] == "--include"
    return verdict


def unchanged(src: Obj, dst: Obj | None) -> bool:
    """`aws s3 sync`'s skip rule: same size, and the destination is not older than the source."""
    return dst is not None and dst.size == src.size and dst.modified >= src.modified


def parse_listing(text: str, prefix: str) -> list[Obj]:
    """The objects of a `list-objects-v2` JSON reply, relative to `prefix`, in key order. An empty reply, or one with no `Contents`, is an empty tree."""
    if not text.strip():
        return []
    objs = []
    for entry in json.loads(text).get("Contents") or []:
        key = entry["Key"]
        if not key.startswith(prefix) or key == prefix or key.endswith("/"):
            continue
        stamp = datetime.datetime.fromisoformat(entry["LastModified"])
        objs.append(Obj(key[len(prefix) :], int(entry["Size"]), stamp))
    return sorted(objs, key=lambda obj: obj.rel)


def _run_quiet(argv: list[str]) -> tuple[int, str]:
    """Run `argv` with stdout DISCARDED (copy-object prints a JSON receipt per object) and stderr captured and forwarded."""
    proc = subprocess.run(argv, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)
        sys.stderr.flush()
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


class Transfers:
    """The retried aws calls of one run, carrying the caller's name for messages and its retry delay."""

    def __init__(self, self_name: str, endpoint: str, delay_s: float) -> None:
        self.self_name = self_name
        self.endpoint = endpoint
        self.delay_s = delay_s

    def _retried(self, argv: list[str], what: str) -> int:
        sys.stdout.flush()
        sys.stderr.flush()
        return transfer_retry.retried(lambda: _run_quiet(argv), what, self.self_name, self.delay_s)

    def list_tree(self, prefix: str) -> list[Obj]:
        """List one tree, retried like any transfer. Raises on a listing that failed."""
        out: list[bytes] = []

        def run() -> tuple[int, str]:
            proc = subprocess.run(
                list_argv(prefix, self.endpoint), check=False, capture_output=True
            )
            if proc.stderr:
                sys.stderr.buffer.write(proc.stderr)
                sys.stderr.flush()
            out[:] = [proc.stdout]
            return proc.returncode, proc.stderr.decode("utf-8", errors="replace")

        sys.stdout.flush()
        sys.stderr.flush()
        status = transfer_retry.retried(run, "listing of %s" % prefix, self.self_name, self.delay_s)
        if status:
            raise PromoteError(status)
        return parse_listing(out[0].decode("utf-8") if out else "", prefix)

    def get(self, key: str, target: str) -> None:
        status = self._retried(get_argv(key, target, self.endpoint), "fetch of %s" % key)
        if status:
            raise PromoteError(status)

    def put(self, source: str, key: str) -> None:
        status = self._retried(put_argv(source, key, self.endpoint), "put of %s" % key)
        if status:
            raise PromoteError(status)

    def copy_all(self, pairs: list[tuple[str, str]]) -> None:
        """Server-side copy every `(src_key, dst_key)`, COPY_WIDTH at a time. The first failure stops new copies from starting; the ones in flight finish. Raises with the first failure's status."""
        failed: list[int] = []
        lock = threading.Lock()

        def one(pair: tuple[str, str]) -> None:
            with lock:
                if failed:
                    return
            status = self._retried(
                copy_argv(pair[0], pair[1], self.endpoint), "copy of %s" % pair[0]
            )
            if status:
                with lock:
                    failed.append(status)

        with ThreadPoolExecutor(max_workers=COPY_WIDTH) as pool:
            list(pool.map(one, pairs))
        if failed:
            raise PromoteError(failed[0])


def check_sizes(dir_name: str, objs: list[Obj], self_name: str) -> None:
    """Refuse a tree holding an object one CopyObject cannot copy, before anything is copied."""
    big = [obj for obj in objs if obj.size > COPY_OBJECT_MAX_BYTES]
    if big:
        for obj in big:
            print(
                "%s: %s%s is %d bytes, over the %d-byte single CopyObject limit; a multipart UploadPartCopy "
                "is not implemented, so nothing was promoted"
                % (self_name, tree(dir_name, "edge"), obj.rel, obj.size, COPY_OBJECT_MAX_BYTES),
                file=sys.stderr,
            )
        raise PromoteError(1)


def stage_pointers(dir_name: str, edge: list[Obj], stage: str, run: Transfers) -> list[str]:
    """Fetch the tree's pointers from edge into `stage` and stamp them for stable. Returns the ones present. An absent pointer is skipped, as both bash twins skip it (`[[ -f "$f" ]]`)."""
    present = {obj.rel for obj in edge}
    names = [name for name in pointers(dir_name) if name in present]
    os.makedirs(stage, exist_ok=True)
    for name in names:
        run.get(tree(dir_name, "edge") + name, os.path.join(stage, name))
    try:
        channel_stamp.stamp_stable(dir_name, stage)
    except channel_stamp.StampError as exc:
        print("%s: %s" % (run.self_name, exc), file=sys.stderr)
        raise PromoteError(exc.status) from exc
    return names


def promote_tree(
    dir_name: str, phases: tuple[tuple[str, ...], ...], stage_root: str, run: Transfers
) -> list[str]:
    """Promote one `<dir>/edge/` to `<dir>/stable/` per the module docstring's plan. Returns the purge URLs. `phases` are aws-style filter tails; `((),)` is one phase of everything."""
    edge = run.list_tree(tree(dir_name, "edge"))
    if not edge:
        print(
            "VACUOUS: %s/edge/ lists 0 object(s) for promotion; refusing to report a promotion that "
            "moved nothing" % dir_name,
            file=sys.stderr,
        )
        raise PromoteError(1)
    check_sizes(dir_name, edge, run.self_name)
    stage = os.path.join(stage_root, dir_name)
    staged = stage_pointers(dir_name, edge, stage, run)
    before = {obj.rel: obj for obj in run.list_tree(tree(dir_name, "stable"))}

    excluded = set(pointers(dir_name))
    selected: set[str] = set()
    for filters in phases:
        batch = [
            obj
            for obj in edge
            if obj.rel not in excluded and obj.rel not in selected and keep(obj.rel, filters)
        ]
        selected.update(obj.rel for obj in batch)
        run.copy_all(
            [
                (tree(dir_name, "edge") + obj.rel, tree(dir_name, "stable") + obj.rel)
                for obj in batch
                if not unchanged(obj, before.get(obj.rel))
            ]
        )

    # POINTERS_GO_LAST.
    for name in staged:
        run.put(os.path.join(stage, name), tree(dir_name, "stable") + name)

    promoted = [obj.rel for obj in edge if obj.rel in selected or obj.rel in staged]
    landed = {obj.rel for obj in run.list_tree(tree(dir_name, "stable"))}
    missing = [rel for rel in promoted if rel not in landed]
    if missing:
        print(
            "INCOMPLETE: %d promoted object(s) are not listed under %s after the copy, so nothing is "
            "purged: %s" % (len(missing), tree(dir_name, "stable"), ", ".join(missing[:10])),
            file=sys.stderr,
        )
        raise PromoteError(1)
    return [channel_url(dir_name, rel) for rel in promoted]
