"""Pack, sign and publish a detector model bundle to the public-data bucket (PLAN-forensics-detection D8, D9, D11).

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile public-data --profile model-signing -- \\
        env PYTHONPATH=.ci python3 -m rediacc_ci.ops.publish_models --channel edge --percent 10 [--version N] [--seq N]
    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile public-data --profile model-signing -- \\
        env PYTHONPATH=.ci python3 -m rediacc_ci.ops.publish_models --channel stable --promote
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.publish_models --dry-run --channel edge

PUBLISH (`--channel edge|stable` without `--promote`). `renet models pack` builds `objects/<sha256>` and the unsigned manifest from `private/renet/models/`; `cmd/modelsign` (never shipped) signs the manifest and writes the channel pointer with its `.sig`. The upload order is objects, manifest and its signature, and the pointer last (its signature lands just before it), so a machine that reads the new pointer always finds everything it names.

PROMOTE (`--promote`, stable only). The current edge pointer is read from the bucket, its manifest and signature are downloaded from the origin, the signature stays as downloaded (`modelsign pointer` verifies it against the model key before signing), and a stable pointer for the same manifest is signed at 100 percent. Nothing is repacked and no object is uploaded again.

HEADERS (D8). Objects and manifests carry `public, max-age=31536000, immutable`; a pointer carries `public, max-age=60`, which the Cache Rule honours as an origin TTL.

SEQUENCE. `--seq` is the pointer sequence; without it the run reads the channel's current pointer from the bucket (the origin caches it for 60 seconds) and takes the next number (a missing pointer counts as 0). Machines refuse a pointer whose `seq` is not above the last one they saw.

`--dry-run` prints every command it would run and touches neither the network nor the bucket. The model key (`MODEL_ED25519_PRIVATE_KEY`) and the bucket credentials (`R2_PUBLIC_DATA_ACCESS_KEY_ID`, `R2_PUBLIC_DATA_SECRET_ACCESS_KEY`) come from the two Bitwarden profiles and only ever sit in a child environment.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.error
from typing import TYPE_CHECKING, NamedTuple

from rediacc_ci import log, paths
from rediacc_ci.core import awscli, https
from rediacc_ci.ops import cf_auth
from rediacc_ci.well_known import PUBLIC_DATA_BUCKET, PUBLIC_DATA_ORIGIN

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

SELF = "publish_models"
CHANNELS = ("edge", "stable")
PREFIX = "models"
IMMUTABLE = "public, max-age=31536000, immutable"
POINTER_CACHE = "public, max-age=60"
FETCH_TIMEOUT_S = 30
SECRET_NAMES = (
    "MODEL_ED25519_PRIVATE_KEY",
    "R2_PUBLIC_DATA_ACCESS_KEY_ID",
    "R2_PUBLIC_DATA_SECRET_ACCESS_KEY",
)

type Runner = Callable[[list[str], Mapping[str, str], pathlib.Path | None], int]
type Fetcher = Callable[[str], bytes | None]


class PublishError(Exception):
    """A refusal or a failed step; `main` prints it and exits 1."""


class Step(NamedTuple):
    """One command (`argv`, run in `cwd`) or, when `argv` is empty, an upload of `upload` (a file or a directory under the work dir)."""

    label: str
    argv: list[str]
    cwd: pathlib.Path | None = None
    upload: str = ""
    cache: str = ""


def renet_dir() -> pathlib.Path:
    return paths.repo_root() / "private" / "renet"


def modelsign_argv(*args: str) -> list[str]:
    return ["go", "run", "./cmd/modelsign", *args]


def default_endpoint() -> str:
    return "https://%s.r2.cloudflarestorage.com" % cf_auth.DEFAULT_ACCOUNT_ID


def upload_argv(local: pathlib.Path, key: str, cache: str, endpoint: str) -> list[str]:
    """`aws s3 cp` of one file to `models/<key>`: signatures and objects are opaque bytes, the manifest and pointer JSON."""
    opaque = key.endswith(".sig") or key.startswith("objects/")
    return [
        awscli.AWS,
        "s3",
        "cp",
        str(local),
        "s3://%s/%s/%s" % (PUBLIC_DATA_BUCKET, PREFIX, key),
        "--endpoint-url",
        endpoint,
        "--cache-control",
        cache,
        "--content-type",
        "application/octet-stream" if opaque else "application/json",
        "--no-progress",
    ]


def pointer_key(channel: str) -> str:
    return "%s/channels/%s.json" % (PREFIX, channel)


def bucket_reader(env: Mapping[str, str], endpoint: str) -> Fetcher:
    """A fetcher of `key` read straight from the bucket with the write credentials: the public origin caches a pointer for 60 seconds, so a sequence or an edge version read through it can be a minute stale."""

    def read(key: str) -> bytes | None:
        argv = [
            awscli.AWS,
            "s3",
            "cp",
            "s3://%s/%s" % (PUBLIC_DATA_BUCKET, key),
            "-",
            "--endpoint-url",
            endpoint,
            "--no-progress",
        ]
        done = awscli.run(argv, env=dict(env), capture_output=True, check=False)
        if done.returncode == 0:
            return bytes(done.stdout)
        err = bytes(done.stderr)
        if b"404" in err or b"NoSuchKey" in err or b"Not Found" in err:
            return None
        raise PublishError(
            "reading %s from the bucket failed: %s" % (key, err.decode(errors="replace").strip())
        )

    return read


def fetch(url: str) -> bytes | None:
    """The body at `url`, or None for a 404."""
    try:
        with https.urlopen(url, timeout=FETCH_TIMEOUT_S) as reply:
            return reply.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise PublishError("GET %s answered %d" % (url, exc.code)) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise PublishError("GET %s failed: %s" % (url, exc)) from exc


def current_seq(channel: str, read: Fetcher) -> int:
    """The channel pointer's `seq` as the bucket holds it (see `bucket_reader`), 0 when there is no pointer."""
    body = read(pointer_key(channel))
    if body is None:
        return 0
    try:
        return int(json.loads(body)["seq"])
    except (ValueError, KeyError, TypeError) as exc:
        raise PublishError(
            "the %s pointer at the origin is not a pointer: %s" % (channel, exc)
        ) from exc


def _run(argv: list[str], env: Mapping[str, str], cwd: pathlib.Path | None) -> int:
    if argv[0] == awscli.AWS:
        return awscli.run(argv, env=dict(env), cwd=cwd).returncode
    return subprocess.run(argv, env=dict(env), cwd=cwd, check=False).returncode


def child_env(source: Mapping[str, str]) -> dict[str, str]:
    """`source` with the bucket credentials under the names the aws CLI reads."""
    env = dict(source)
    env["AWS_ACCESS_KEY_ID"] = source.get("R2_PUBLIC_DATA_ACCESS_KEY_ID", "")
    env["AWS_SECRET_ACCESS_KEY"] = source.get("R2_PUBLIC_DATA_SECRET_ACCESS_KEY", "")
    return env


def require_secrets(source: Mapping[str, str]) -> None:
    missing = [name for name in SECRET_NAMES if not source.get(name)]
    if missing:
        raise PublishError(
            "missing %s: run under `bws_env exec --profile public-data --profile model-signing`"
            % ", ".join(missing)
        )


def build_steps(
    args: argparse.Namespace,
    work: pathlib.Path,
    seq: int | str,
    version: int | str,
    renet: str,
) -> list[Step]:
    """The ordered steps of one publish or promote run."""
    channel = args.channel
    manifest = work / "manifests" / ("%s.json" % version)
    steps: list[Step] = []
    if not args.promote:
        steps.append(
            Step(
                "pack",
                [
                    renet,
                    "models",
                    "pack",
                    "--src",
                    str(renet_dir() / "models"),
                    "--out",
                    str(work),
                    "--version",
                    str(version),
                    "--min-renet",
                    args.min_renet,
                ],
            )
        )
    if not args.promote:
        # A promote keeps the edge signature it downloaded: signing the downloaded bytes here would put the model key under whatever the bucket held, and `modelsign pointer` verifies that signature against the key before it signs a pointer.
        steps.append(Step("sign manifest", modelsign_argv("sign", str(manifest)), renet_dir()))
    pointer = [
        "pointer",
        "-channel",
        channel,
        "-seq",
        str(seq),
        "-manifest",
        str(manifest),
        "-percent",
        str(100 if args.promote else args.percent),
        "-out",
        str(work / "channels" / ("%s.json" % channel)),
    ]
    if args.rollback:
        pointer.append("-rollback")
    steps.append(Step("sign pointer", modelsign_argv(*pointer), renet_dir()))
    if not args.promote:
        steps.append(Step("upload objects", [], upload="objects", cache=IMMUTABLE))
        steps.append(Step("upload manifest", [], upload="manifests", cache=IMMUTABLE))
    steps.append(
        Step("upload pointer", [], upload="channels/%s.json" % channel, cache=POINTER_CACHE)
    )
    return steps


def expand_upload(step: Step, work: pathlib.Path, endpoint: str) -> list[list[str]]:
    """One `aws s3 cp` per file under the step's path, each file with its `.sig` for a single named file."""
    target = work / step.upload
    if target.is_dir():
        files = sorted(p for p in target.rglob("*") if p.is_file())
    else:
        # The signature first: the pointer is the last object to land, so a machine that reads it finds its signature already there.
        files = [target.with_name(target.name + ".sig"), target]
    return [upload_argv(p, p.relative_to(work).as_posix(), step.cache, endpoint) for p in files]


def fetch_promote_inputs(work: pathlib.Path, get: Fetcher, read: Fetcher) -> int:
    """Download the edge pointer's manifest and signature into `work`; return the manifest version."""
    body = read(pointer_key("edge"))
    if body is None:
        raise PublishError("there is no edge pointer at the origin to promote")
    try:
        version = int(json.loads(body)["version"])
    except (ValueError, KeyError, TypeError) as exc:
        raise PublishError("the edge pointer at the origin is not a pointer: %s" % exc) from exc
    for suffix in ("", ".sig"):
        name = "manifests/%d.json%s" % (version, suffix)
        data = get("%s/%s/%s" % (PUBLIC_DATA_ORIGIN, PREFIX, name))
        if data is None:
            raise PublishError("the edge manifest %s is missing at the origin" % name)
        target = work / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return version


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=SELF, description="Pack, sign and publish a detector model bundle."
    )
    parser.add_argument("--channel", choices=CHANNELS, required=True)
    parser.add_argument(
        "--percent",
        type=int,
        default=100,
        help="rollout percent of the pointer, 0-100 (publish only)",
    )
    parser.add_argument(
        "--version",
        type=int,
        default=0,
        help="bundle version (default: the current UTC time in seconds)",
    )
    parser.add_argument(
        "--seq",
        type=int,
        default=0,
        help="pointer sequence (default: the origin's current one plus 1)",
    )
    parser.add_argument("--min-renet", default="0.0.0")
    parser.add_argument(
        "--rollback", action="store_true", help="let machines on a newer version move to this one"
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="re-sign the edge bundle as the stable pointer at 100 percent",
    )
    parser.add_argument("--renet", default="", help="renet binary (default bin/renet)")
    parser.add_argument("--endpoint", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv))
    if not 0 <= args.percent <= 100:
        parser.error("--percent must be 0-100")
    if args.promote and args.channel != "stable":
        parser.error("--promote publishes the stable channel")
    if args.promote and (args.version or args.rollback):
        parser.error("--promote takes the edge pointer's version and never rolls back")
    return args


def run(
    args: argparse.Namespace,
    source: Mapping[str, str],
    *,
    runner: Runner = _run,
    get: Fetcher = fetch,
    read_bucket: Fetcher | None = None,
) -> int:
    endpoint = args.endpoint or default_endpoint()
    renet = args.renet or str(paths.repo_root() / "bin" / "renet")
    if args.dry_run:
        version: int | str = (
            "<edge version>" if args.promote else (args.version or int(time.time()))
        )
        steps = build_steps(args, pathlib.Path("<work>"), args.seq or "<current+1>", version, renet)
        for step in steps:
            what = (
                " ".join(step.argv)
                if step.argv
                else "aws s3 cp <work>/%s -> s3://%s/%s/ (%s)"
                % (step.upload, PUBLIC_DATA_BUCKET, PREFIX, step.cache)
            )
            log.info("DRY-RUN %s: %s" % (step.label, what))
        return 0
    require_secrets(source)
    env = child_env(source)
    read = read_bucket or bucket_reader(env, endpoint)
    with tempfile.TemporaryDirectory(prefix="publish-models-") as tmp:
        work = pathlib.Path(tmp)
        (work / "channels").mkdir()
        version = (
            fetch_promote_inputs(work, get, read)
            if args.promote
            else (args.version or int(time.time()))
        )
        seq = args.seq or current_seq(args.channel, read) + 1
        # Upload steps list the files the earlier steps wrote, so each expands only when it is reached.
        for step in build_steps(args, work, seq, version, renet):
            commands = [step.argv] if step.argv else expand_upload(step, work, endpoint)
            for argv in commands:
                log.info("%s: %s" % (step.label, " ".join(argv[:4])))
                code = runner(argv, env, step.cwd)
                if code != 0:
                    raise PublishError("step %r exited %d" % (step.label, code))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run(args, os.environ)
    except PublishError as exc:
        log.error("%s: %s" % (SELF, exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
