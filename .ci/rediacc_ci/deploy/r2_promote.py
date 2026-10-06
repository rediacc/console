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

  6. PRUNE (package trees only: `PACKAGE_TREES`). Every `<dir>/stable/` object the run did not promote is deleted, AFTER step 5 has confirmed every promoted key is listed: copy first, delete second, so the stable index never names a file that is missing. Stable then holds exactly what the promote copied, nothing older (operator ruling 2026-10-06, "Current version only"). `cli/stable/` is never pruned here: it carries the pinned
     channel binaries and pointers, outside this rule. See `prune_tree` and `PRUNE_IS_COPY_THEN_DELETE`.

TWO SOURCES, FOR A CHANNEL SNAPSHOT (PLAN-plan-per-pr-loop R2 follow-up). By default one tree, `<dir>/edge/`, feeds every phase. `Sources` splits it: phase 1 (the bytes) reads `bytes_prefix`, every later phase and the pointers read `metadata_prefix`, which is `channel_snapshot`'s per-version copy of the signed metadata. A snapshot promote ALWAYS copies its metadata and, with `copy_bytes_always`, its bytes too, never applying the skip rule of step 3: a channel name such as `dists/stable/InRelease` or `rdc-linux-x64`
is reused by every version, and a stable copy promoted LATER from an OLDER release can have the same size and a newer LastModified than the snapshot object, so the skip rule would keep the wrong version's file. `Sources.only` narrows the bytes phase to the package files the snapshot's marker names, so a snapshot promote copies the selected version's packages and not every version edge still holds for other promotion candidates.

THE PRUNE IS A LIST-DIFF-DELETE, NOT `aws s3 sync --delete`. `sync --delete` decides what to delete and deletes it in the same pass as the uploads, with no ordering guarantee between a delete and an upload (aws-cli schedules both as transfer tasks on one pool), and it would see only the local tree, never the extra keep set a snapshot promotion candidate needs. Here the deletes are planned from a listing taken AFTER the writes, the keep set is explicit, and nothing is deleted when the listing does not show every file the run just wrote.
One `aws s3api delete-objects` per `DELETE_BATCH` keys, `Quiet`, with its `Errors` read back: delete-objects exits 0 even when individual keys fail.
"""

from __future__ import annotations

import datetime
import fnmatch
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from rediacc_ci.deploy import channel_stamp, transfer_retry
from rediacc_ci.well_known import RELEASES_BUCKET, RELEASES_ORIGIN

BUCKET = RELEASES_BUCKET
PUBLIC_HOST = RELEASES_ORIGIN
CC_MUTABLE = "no-cache"

# R2's single-part object limit, which bounds one CopyObject. 5 GiB, taken as 5 * 10^9 to stay clear of the edge.
COPY_OBJECT_MAX_BYTES = 5 * 1000**3

# Parallel CopyObject calls. The copies are independent and server-side, so the width bounds request concurrency, not bandwidth. Same width as `simulate_promotion.COPY_WIDTH`.
COPY_WIDTH = 8

# THE ORDER THAT KEEPS A CLIENT CONSISTENT. A pointer is the ENTRY point a client reads first (`install.sh` -> manifest -> binaries; `rediacc.repo` -> repomd -> rpms; `rediacc.conf` -> the pacman db). Written LAST, a client that sees the new pointer finds everything it names already in stable; until then the previous pointer, itself stable-stamped by the previous promote, stays in place and still names objects that exist. Written first, a new installer could name a manifest or package not copied yet. A run that dies part-way leaves the previous pointer, never an edge one.
POINTERS_GO_LAST = True
BULK_IS_SERVER_SIDE = True

# The four Linux package trees, the only trees a prune may touch (operator ruling 2026-10-06). `cli/` (pinned binaries, pointers), `npm/`, the install scripts and `snapshots/` are never pruned by this module.
PACKAGE_TREES = ("apt", "rpm", "apk", "archlinux")

# Keys per `delete-objects` call. S3 allows 1000; 250 keeps the inline `--delete` JSON well under Linux's 128 KiB single-argument limit (MAX_ARG_STRLEN) for the longest rpm repodata keys.
DELETE_BATCH = 250

# A channel name a prune accepts: one path segment, so `<dir>/<channel>/` can never reach outside its own tree.
CHANNEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Named order of a prune: the new files are written and LISTED first, the stale ones deleted second.
PRUNE_IS_COPY_THEN_DELETE = True


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


@dataclass(frozen=True)
class Sources:
    """Where a snapshot promote reads from; see TWO SOURCES in the module docstring. `ignore` names rels of the bytes tree that are never promoted (the `.released` sentinel of `cli/v<ver>/`)."""

    bytes_prefix: str
    metadata_prefix: str
    ignore: frozenset[str] = frozenset()
    copy_bytes_always: bool = False
    # When set, the bytes phase copies only these rels of `bytes_prefix` (a snapshot's marker packages); None copies the whole tree.
    only: frozenset[str] | None = None


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


def delete_argv(keys: list[str], endpoint: str) -> list[str]:
    """One `aws s3api delete-objects` for up to `DELETE_BATCH` keys, `Quiet` so the reply names only the keys that failed."""
    payload = json.dumps({"Objects": [{"Key": key} for key in keys], "Quiet": True})
    return [
        "aws",
        "s3api",
        "delete-objects",
        "--bucket",
        BUCKET,
        "--delete",
        payload,
        *endpoint_args(endpoint),
        "--output",
        "json",
    ]


def delete_errors(text: str) -> list[str]:
    """The `Errors` of a delete-objects reply, as `key: code message` lines. An empty reply is no error (a `Quiet` delete with nothing failed prints nothing)."""
    if not text.strip():
        return []
    try:
        reply = json.loads(text)
    except ValueError:
        return ["unparseable delete-objects reply: %r" % text[:200]]
    return [
        "%s: %s %s" % (err.get("Key", "?"), err.get("Code", "?"), err.get("Message", ""))
        for err in (reply.get("Errors") or [])
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

    def delete_keys(self, keys: list[str]) -> None:
        """Delete `keys`, `DELETE_BATCH` per call, each call retried like any transfer. A key the reply reports as failed fails the run."""
        for start in range(0, len(keys), DELETE_BATCH):
            self._delete_batch(keys[start : start + DELETE_BATCH])

    def _delete_batch(self, batch: list[str]) -> None:
        out: list[bytes] = []

        def run() -> tuple[int, str]:
            proc = subprocess.run(
                delete_argv(batch, self.endpoint), check=False, capture_output=True
            )
            if proc.stderr:
                sys.stderr.buffer.write(proc.stderr)
                sys.stderr.flush()
            out[:] = [proc.stdout]
            return proc.returncode, proc.stderr.decode("utf-8", errors="replace")

        sys.stdout.flush()
        sys.stderr.flush()
        status = transfer_retry.retried(
            run, "delete of %d object(s)" % len(batch), self.self_name, self.delay_s
        )
        if status:
            raise PromoteError(status)
        errors = delete_errors(out[0].decode("utf-8", errors="replace") if out else "")
        if errors:
            for line in errors[:10]:
                print("%s: delete failed: %s" % (self.self_name, line), file=sys.stderr)
            print(
                "%s: %d of %d delete(s) failed" % (self.self_name, len(errors), len(batch)),
                file=sys.stderr,
            )
            raise PromoteError(1)

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


def check_sizes(prefix: str, objs: list[Obj], self_name: str) -> None:
    """Refuse a tree holding an object one CopyObject cannot copy, before anything is copied."""
    big = [obj for obj in objs if obj.size > COPY_OBJECT_MAX_BYTES]
    if big:
        for obj in big:
            print(
                "%s: %s%s is %d bytes, over the %d-byte single CopyObject limit; a multipart UploadPartCopy "
                "is not implemented, so nothing was promoted"
                % (self_name, prefix, obj.rel, obj.size, COPY_OBJECT_MAX_BYTES),
                file=sys.stderr,
            )
        raise PromoteError(1)


def stage_pointers(
    dir_name: str, edge: list[Obj], stage: str, run: Transfers, prefix: str | None = None
) -> list[str]:
    """Fetch the tree's pointers from `prefix` (default `<dir>/edge/`) into `stage` and stamp them for stable. Returns the ones present. An absent pointer is skipped, as both bash twins skip it (`[[ -f "$f" ]]`)."""
    source = tree(dir_name, "edge") if prefix is None else prefix
    present = {obj.rel for obj in edge}
    names = [name for name in pointers(dir_name) if name in present]
    os.makedirs(stage, exist_ok=True)
    for name in names:
        run.get(source + name, os.path.join(stage, name))
    try:
        channel_stamp.stamp_stable(dir_name, stage)
    except channel_stamp.StampError as exc:
        print("%s: %s" % (run.self_name, exc), file=sys.stderr)
        raise PromoteError(exc.status) from exc
    return names


def _listed(prefix: str, run: Transfers, ignore: frozenset[str] = frozenset()) -> list[Obj]:
    """One tree's listing, refused as `VACUOUS:` when it is empty."""
    objs = [obj for obj in run.list_tree(prefix) if obj.rel not in ignore]
    if not objs:
        print(
            "VACUOUS: %s lists 0 object(s) for promotion; refusing to report a promotion that "
            "moved nothing" % prefix,
            file=sys.stderr,
        )
        raise PromoteError(1)
    return objs


def prune_tree(
    dir_name: str, channel: str, keep_rels: set[str], listed: list[Obj], run: Transfers
) -> int:
    """Delete every object of `<dir_name>/<channel>/` in `listed` whose rel is not in `keep_rels`. Returns how many. The caller has already written and LISTED everything in `keep_rels` it wrote (`PRUNE_IS_COPY_THEN_DELETE`), and `listed` is that listing.

    THE FLOORS. Only a `PACKAGE_TREES` directory and a one-segment channel are accepted, so no key outside `<dir>/<channel>/` can be named. An empty `keep_rels` refuses (`VACUOUS:`) with nothing deleted, because an empty keep set would delete the whole tree. Every key is rebuilt as the tree prefix plus a listed rel, never taken from anywhere else."""
    if dir_name not in PACKAGE_TREES or not CHANNEL_RE.match(channel):
        print(
            "%s: refusing to prune %s/%s/: only %s under a one-segment channel may be pruned"
            % (run.self_name, dir_name, channel, ", ".join(PACKAGE_TREES)),
            file=sys.stderr,
        )
        raise PromoteError(1)
    prefix = tree(dir_name, channel)
    if not keep_rels:
        print(
            "VACUOUS: the keep set for %s is empty; refusing to prune a tree down to nothing"
            % prefix,
            file=sys.stderr,
        )
        raise PromoteError(1)
    stale = sorted(obj.rel for obj in listed if obj.rel not in keep_rels)
    run.delete_keys([prefix + rel for rel in stale])
    print(
        "Pruned %s: %d stale object(s) deleted, %d kept"
        % (prefix, len(stale), len(listed) - len(stale))
    )
    return len(stale)


def promote_tree(
    dir_name: str,
    phases: tuple[tuple[str, ...], ...],
    stage_root: str,
    run: Transfers,
    sources: Sources | None = None,
) -> list[str]:
    """Promote one `<dir>/edge/` to `<dir>/stable/` per the module docstring's plan. Returns the purge URLs. `phases` are aws-style filter tails; `((),)` is one phase of everything. `sources` splits the bytes and the metadata between two trees (TWO SOURCES in the module docstring)."""
    split = sources is not None
    bytes_prefix = sources.bytes_prefix if sources is not None else tree(dir_name, "edge")
    meta_prefix = sources.metadata_prefix if sources is not None else bytes_prefix
    edge = _listed(bytes_prefix, run, sources.ignore if sources is not None else frozenset())
    meta = _listed(meta_prefix, run) if split else edge
    check_sizes(bytes_prefix, edge, run.self_name)
    if split:
        check_sizes(meta_prefix, meta, run.self_name)
    stage = os.path.join(stage_root, dir_name)
    staged = stage_pointers(dir_name, meta, stage, run, meta_prefix)
    before = {obj.rel: obj for obj in run.list_tree(tree(dir_name, "stable"))}

    excluded = set(pointers(dir_name))
    selected: set[str] = set()
    for index, filters in enumerate(phases):
        is_bytes = index == 0
        source, prefix = (edge, bytes_prefix) if is_bytes else (meta, meta_prefix)
        # A snapshot promote never skips its metadata, nor (cli) its bytes; see TWO SOURCES.
        skippable = not split or (
            is_bytes and sources is not None and not sources.copy_bytes_always
        )
        only = sources.only if (is_bytes and sources is not None) else None
        batch = [
            obj
            for obj in source
            if obj.rel not in excluded
            and obj.rel not in selected
            and keep(obj.rel, filters)
            and (only is None or obj.rel in only)
        ]
        selected.update(obj.rel for obj in batch)
        run.copy_all(
            [
                (prefix + obj.rel, tree(dir_name, "stable") + obj.rel)
                for obj in batch
                if not (skippable and unchanged(obj, before.get(obj.rel)))
            ]
        )

    # POINTERS_GO_LAST.
    for name in staged:
        run.put(os.path.join(stage, name), tree(dir_name, "stable") + name)

    in_edge = {obj.rel for obj in edge}
    order = edge if not split else edge + [obj for obj in meta if obj.rel not in in_edge]
    promoted = [obj.rel for obj in order if obj.rel in selected or obj.rel in staged]
    after = run.list_tree(tree(dir_name, "stable"))
    landed = {obj.rel for obj in after}
    missing = [rel for rel in promoted if rel not in landed]
    if missing:
        print(
            "INCOMPLETE: %d promoted object(s) are not listed under %s after the copy, so nothing is "
            "purged or pruned: %s"
            % (len(missing), tree(dir_name, "stable"), ", ".join(missing[:10])),
            file=sys.stderr,
        )
        raise PromoteError(1)
    # Step 6, PRUNE: only after the listing above has shown every promoted key.
    if dir_name in PACKAGE_TREES:
        prune_tree(dir_name, "stable", set(promoted), after, run)
    return [channel_url(dir_name, rel) for rel in promoted]
