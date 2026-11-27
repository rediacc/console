"""The Windows lane's bake inputs and golden image in the private bucket, and their record (agent/plans/PLAN-windows-lane.md D12).

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile windows-image -- \\
        env PYTHONPATH=.ci python3 -m rediacc_ci.ops.windows_image <verb> [--dry-run]

    upload-inputs <iso> <virtio-iso> [--build B]   hash both, upload them, write `inputs` in the record
    pack [--golden DIR] [--out FILE]               golden qcow2, OVMF VARS and swtpm state into one zstd tar, with its sha256
    publish [<tar>]                                upload the packed image, then write `image` in the record
    fetch                                          download the image, verify its sha256, unpack it into $RENET_DATA_DIR/images/
    fetch --inputs                                 download both ISOs to $RENET_DATA_DIR/images/{win11-eval,virtio-win}.iso and verify them
    rebake                                         fetch --inputs, `renet ops windows bake`, pack, publish
    probe                                          the token reaches its bucket, not the public-data bucket, and an anonymous GET is refused

THE BUCKET IS PRIVATE. It holds the evaluation ISO, the virtio ISO and an installed image whose registry carries the autologon password in clear text (D3 revised), so it is never the public-data bucket, which is public by policy (`.ci/docs/r2-media-setup.md` section 10). The module refuses that bucket as a target BY NAME, whatever the record or `--bucket` says, before any request.

THE RECORD is `.ci/config/windows-image.json` (`RECORD_REL`): the bucket, `warn_days`, the `rebake` command, and `inputs` and `image`, each `null` until its first upload. The bucket layout is content-addressed: `inputs/win11-eval/<sha256>.iso`, `inputs/virtio-win/<sha256>.iso` and `images/win11/<build>-<installed date>/golden.tar.zst`. An image names the inputs it was baked from (`iso_sha256`, `virtio_iso_sha256`), and `publish` refuses one whose hashes differ from the recorded `inputs`. `check:ci-windows-image-expiry` reads the same file.

THE EVALUATION LABEL. `upload-inputs` reads the ISO 9660 volume label at byte 0x8028 and refuses an ISO that is not an evaluation edition: the evaluation media is labelled `<edition>_<arch>FREE_<lang>_DV9` and the retail media `<edition>_<arch>FRE_<lang>_DV9`. Measured 2026-11-27 on this host: the 26300.9457 Enterprise Evaluation ISO reads `CENA_X64FREE_EN-US_DV9`, and `Windows11_Client_x64_en-us_26300_9457.iso` (not the evaluation image) reads `CCCOMA_X64FRE_EN-US_DV9`.

LOCAL OVERRIDES. `WINDOWS_ISO` or `VIRTIO_ISO`, when set, names a local copy that `fetch --inputs` uses instead of downloading that ISO (it is still hashed against the record when the record has inputs).

THE GOLDEN DIRECTORY that `pack` reads (`--golden`, default `$RENET_DATA_DIR/images/win11-golden`) holds `golden.qcow2`, `OVMF_VARS.fd`, the swtpm state directory `tpm/` and `rediacc-image.json`, the host copy of the guest's `C:\\rediacc-image.json` with `build`, `installed_at` and `expires_at` (from `slmgr /xpr`). `pack` writes the tar and a `<tar>.json` sidecar with its sha256, size and that metadata; `publish` reads the sidecar.

`--dry-run` prints every command and request it would make and touches neither the network nor the bucket nor the record. Transfers run through the pinned `aws` CLI (`rediacc_ci.core.awscli`) against the R2 S3 endpoint; the probe signs its own requests. The bucket credentials (`R2_WINDOWS_IMAGE_ACCESS_KEY_ID`, `R2_WINDOWS_IMAGE_SECRET_ACCESS_KEY`) come from the `windows-image` profile and only ever sit in a child environment; no key, signature or presigned URL is printed.

Exit 0: done. Exit 1: a refusal or a failed step, printed on stderr.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
from typing import TYPE_CHECKING, Any

from rediacc_ci import paths
from rediacc_ci.core import awscli
from rediacc_ci.drills import wire
from rediacc_ci.ops import cf_auth
from rediacc_ci.well_known import PUBLIC_DATA_BUCKET

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

SELF = "windows_image"
RECORD_REL = ".ci/config/windows-image.json"
SCHEMA = 1
# Refused by name even if the well-known value were ever renamed: the literal is the bucket the plan names as public by policy.
PUBLIC_BUCKETS = frozenset({PUBLIC_DATA_BUCKET, "rediacc-public-data"})
SECRET_NAMES = ("R2_WINDOWS_IMAGE_ACCESS_KEY_ID", "R2_WINDOWS_IMAGE_SECRET_ACCESS_KEY")
PROFILE = "windows-image"
ISO_NAME = "win11-eval.iso"
VIRTIO_NAME = "virtio-win.iso"
GOLDEN_DIR = "win11-golden"
GOLDEN_FILES = ("golden.qcow2", "OVMF_VARS.fd", "tpm", "rediacc-image.json")
GUEST_META = "rediacc-image.json"
TAR_NAME = "golden.tar.zst"
VIRTIO_SOURCE = "fedorapeople stable-virtio"
EXPIRY_SOURCE = "slmgr /xpr"
SIGV4_REGION = "auto"
TIMEOUT = 30.0
CHUNK = 1 << 20

# ISO 9660: the primary volume descriptor sits at sector 16 (byte 0x8000); its type byte is 1, then "CD001", and the volume identifier is bytes 40-71 of it.
PVD_OFFSET = 0x8000
LABEL_SLICE = slice(40, 72)
EVAL_LABEL = re.compile(r"^[A-Z0-9]+_(?:X64|A64|X86)FREE_[A-Z]{2}-[A-Z]{2}_DV\d+$")
FILE_BUILD = re.compile(r"^(\d{5}\.\d+)\.")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
GO_HEX = re.compile(r'"([0-9a-f]{64})"')

type Runner = Callable[[list[str], Mapping[str, str]], int]
# (method, url, headers) -> status; raises OSError on a transport failure.
type Transport = Callable[[str, str, dict[str, str]], int]


class ImageError(Exception):
    """A refusal or a failed step; `main` prints it and exits 1."""


# ---- the record ------------------------------------------------------------


def record_path(root: pathlib.Path | None = None) -> pathlib.Path:
    return pathlib.Path(root or paths.repo_root()) / RECORD_REL


def load_record(path: pathlib.Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ImageError("cannot read %s (%s)" % (path, exc)) from exc
    except ValueError as exc:
        raise ImageError("%s is not JSON (%s)" % (path, exc)) from exc
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ImageError("%s is not a schema %d record" % (path, SCHEMA))
    refuse_public(str(doc.get("bucket", "")))
    return doc


def save_record(path: pathlib.Path, doc: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def refuse_public(bucket: str) -> str:
    """`bucket`, or ImageError when it is empty or the public-data bucket."""
    if not bucket:
        raise ImageError("the record names no bucket")
    if bucket in PUBLIC_BUCKETS:
        raise ImageError(
            "refusing bucket %s: it is public by policy, and the Windows inputs and image are private (D12)"
            % bucket
        )
    return bucket


def input_mismatch(doc: Mapping[str, Any], iso_sha: str, virtio_sha: str) -> list[str]:
    """The ways an image's input hashes differ from the record's `inputs` (empty when they agree)."""
    inputs = doc.get("inputs")
    if not isinstance(inputs, dict):
        return ["the record has no inputs, so the image cannot name what it was baked from"]
    out = []
    for label, have, want in (
        ("iso", iso_sha, (inputs.get("iso") or {}).get("sha256")),
        ("virtio", virtio_sha, (inputs.get("virtio") or {}).get("sha256")),
    ):
        if have != want:
            out.append("%s sha256 %s differs from inputs.%s.sha256 %s" % (label, have, label, want))
    return out


def go_pins(path: pathlib.Path) -> set[str] | None:
    """The 64-hex string literals of `opsconfig/windows.go` (WL3's pinned ISO hashes), or None when the file does not exist yet."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return set(GO_HEX.findall(text))


# ---- local files -----------------------------------------------------------


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def volume_label(path: pathlib.Path) -> str:
    """The ISO 9660 volume identifier, or ImageError when there is no primary volume descriptor."""
    try:
        with path.open("rb") as fh:
            fh.seek(PVD_OFFSET)
            pvd = fh.read(72)
    except OSError as exc:
        raise ImageError("cannot read %s (%s)" % (path, exc)) from exc
    if len(pvd) < 72 or pvd[0] != 1 or pvd[1:6] != b"CD001":
        raise ImageError("%s has no ISO 9660 primary volume descriptor" % path)
    return pvd[LABEL_SLICE].decode("ascii", errors="replace").strip()


def data_dir(env: Mapping[str, str]) -> pathlib.Path:
    raw = env.get("RENET_DATA_DIR", "")
    if not raw:
        raise ImageError(
            "RENET_DATA_DIR is unset; it names the renet data directory images live under"
        )
    return pathlib.Path(raw)


def parse_instant(value: object, field: str) -> datetime.datetime:
    if not isinstance(value, str):
        raise ImageError("%s is missing" % field)
    try:
        moment = datetime.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ImageError("%s %r is not an ISO 8601 instant" % (field, value)) from exc
    if moment.tzinfo is None:
        raise ImageError("%s %r carries no UTC offset" % (field, value))
    return moment


# ---- the bucket ------------------------------------------------------------


def default_endpoint() -> str:
    return "https://%s.r2.cloudflarestorage.com" % cf_auth.DEFAULT_ACCOUNT_ID


def child_env(source: Mapping[str, str]) -> dict[str, str]:
    """`source` with the bucket credentials under the names the aws CLI reads."""
    env = dict(source)
    env["AWS_ACCESS_KEY_ID"] = source.get(SECRET_NAMES[0], "")
    env["AWS_SECRET_ACCESS_KEY"] = source.get(SECRET_NAMES[1], "")
    return env


def require_secrets(source: Mapping[str, str]) -> None:
    missing = [name for name in SECRET_NAMES if not source.get(name)]
    if missing:
        raise ImageError(
            "missing %s: run under `bws_env exec --profile %s`" % (", ".join(missing), PROFILE)
        )


def cp_argv(src: str, dst: str, endpoint: str) -> list[str]:
    return [awscli.AWS, "s3", "cp", src, dst, "--endpoint-url", endpoint, "--no-progress"]


def s3_url(bucket: str, key: str) -> str:
    return "s3://%s/%s" % (refuse_public(bucket), key)


def _run(argv: list[str], env: Mapping[str, str]) -> int:
    if argv[0] == awscli.AWS:
        return awscli.run(argv, env=dict(env)).returncode
    return subprocess.run(argv, env=dict(env), check=False).returncode


def _transport(method: str, url: str, headers: dict[str, str]) -> int:
    status, _ = wire.http_bytes(method, url, None, headers, json_body=False, timeout=TIMEOUT)
    return status


class Ctx:
    """One run: the record, the environment, the seams, and whether anything may happen."""

    def __init__(
        self,
        args: argparse.Namespace,
        env: Mapping[str, str],
        runner: Runner,
        transport: Transport,
        out,
    ) -> None:
        self.args = args
        self.env = env
        self.runner = runner
        self.transport = transport
        self.out = out
        self.dry = bool(args.dry_run)
        self.record = pathlib.Path(args.record) if args.record else record_path()
        self.doc = load_record(self.record)
        self.bucket = refuse_public(args.bucket or str(self.doc.get("bucket", "")))
        self.endpoint = args.endpoint or default_endpoint()

    def say(self, line: str) -> None:
        print(line, file=self.out, flush=True)

    def need_secrets(self) -> None:
        if not self.dry:
            require_secrets(self.env)

    def run(self, argv: list[str], label: str) -> None:
        if self.dry:
            self.say("DRY-RUN %s: %s" % (label, shlex.join(argv)))
            return
        self.say("%s: %s" % (label, shlex.join(argv)))
        rc = self.runner(argv, child_env(self.env))
        if rc != 0:
            raise ImageError("%s failed with exit %d" % (label, rc))

    def upload(self, local: pathlib.Path, key: str) -> None:
        self.run(cp_argv(str(local), s3_url(self.bucket, key), self.endpoint), "upload %s" % key)

    def download(self, key: str, local: pathlib.Path) -> None:
        self.run(cp_argv(s3_url(self.bucket, key), str(local), self.endpoint), "download %s" % key)

    def save(self) -> None:
        if self.dry:
            self.say("DRY-RUN write %s" % self.record)
            return
        save_record(self.record, self.doc)
        self.say("wrote %s" % self.record)


def verify(path: pathlib.Path, want: str, what: str) -> None:
    """Refuse and delete `path` when its sha256 is not `want`."""
    have = sha256_file(path)
    if have != want:
        path.unlink(missing_ok=True)
        raise ImageError(
            "sha256 mismatch on %s: got %s, the record pins %s; the download was deleted"
            % (what, have, want)
        )


# ---- the verbs -------------------------------------------------------------


def cmd_upload_inputs(ctx: Ctx) -> None:
    iso = pathlib.Path(ctx.args.iso)
    virtio = pathlib.Path(ctx.args.virtio_iso)
    label = volume_label(iso)
    if not EVAL_LABEL.match(label):
        raise ImageError(
            "refusing %s: its volume label %r is not an evaluation edition (expected <edition>_<arch>FREE_<lang>_DV<n>)"
            % (iso, label)
        )
    virtio_label = volume_label(virtio)
    build = ctx.args.build
    if not build:
        found = FILE_BUILD.match(iso.name)
        if not found:
            raise ImageError("%s names no build; pass --build <major.minor>" % iso.name)
        build = found.group(1)
    ctx.need_secrets()
    iso_sha = sha256_file(iso)
    virtio_sha = sha256_file(virtio)
    entries = {
        "iso": {
            "key": "inputs/win11-eval/%s.iso" % iso_sha,
            "sha256": iso_sha,
            "bytes": iso.stat().st_size,
            "file": iso.name,
            "edition": label,
            "build": build,
        },
        "virtio": {
            "key": "inputs/virtio-win/%s.iso" % virtio_sha,
            "sha256": virtio_sha,
            "bytes": virtio.stat().st_size,
            "source": "%s (%s)" % (VIRTIO_SOURCE, virtio_label),
        },
    }
    ctx.upload(iso, entries["iso"]["key"])
    ctx.upload(virtio, entries["virtio"]["key"])
    ctx.doc["inputs"] = entries
    ctx.save()


def cmd_pack(ctx: Ctx) -> pathlib.Path:
    golden = (
        pathlib.Path(ctx.args.golden)
        if ctx.args.golden
        else data_dir(ctx.env) / "images" / GOLDEN_DIR
    )
    out = pathlib.Path(ctx.args.out) if ctx.args.out else golden.parent / TAR_NAME
    missing = [name for name in GOLDEN_FILES if not (golden / name).exists()]
    if missing and ctx.dry:
        # A dry run before the first bake has no golden directory to read; print the commands it would run.
        ctx.run(["tar", "--zstd", "-cf", str(out), "-C", str(golden.parent), golden.name], "pack")
        ctx.say("DRY-RUN write %s.json (%s lacks %s)" % (out, golden, ", ".join(missing)))
        return out
    if missing:
        raise ImageError("%s lacks %s" % (golden, ", ".join(missing)))
    try:
        meta = json.loads((golden / GUEST_META).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ImageError("cannot read %s (%s)" % (golden / GUEST_META, exc)) from exc
    installed = parse_instant(meta.get("installed_at"), "installed_at")
    expires = parse_instant(meta.get("expires_at"), "expires_at")
    if expires <= installed:
        raise ImageError("expires_at %s is not after installed_at %s" % (expires, installed))
    iso_sha = ctx.args.iso_sha256 or meta.get("iso_sha256", "")
    virtio_sha = ctx.args.virtio_iso_sha256 or meta.get("virtio_iso_sha256", "")
    for name, value in (("iso_sha256", iso_sha), ("virtio_iso_sha256", virtio_sha)):
        if not SHA256_HEX.match(str(value)):
            raise ImageError("%s is missing or not a sha256; the image must name its inputs" % name)
    argv = [
        "tar",
        "--zstd",
        "-cf",
        str(out),
        "-C",
        str(golden.parent),
        *("%s/%s" % (golden.name, n) for n in GOLDEN_FILES),
    ]
    ctx.run(argv, "pack")
    sidecar = {
        "build": str(meta.get("build", "")),
        "edition": str(
            meta.get("edition", (ctx.doc.get("inputs") or {}).get("iso", {}).get("edition", ""))
        ),
        "installed_at": meta["installed_at"],
        "expires_at": meta["expires_at"],
        "expiry_source": str(meta.get("expiry_source", EXPIRY_SOURCE)),
        "iso_sha256": iso_sha,
        "virtio_iso_sha256": virtio_sha,
    }
    if ctx.dry:
        ctx.say("DRY-RUN write %s.json" % out)
        return out
    sidecar["sha256"] = sha256_file(out)
    sidecar["bytes"] = out.stat().st_size
    pathlib.Path("%s.json" % out).write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
    ctx.say("packed %s sha256 %s" % (out, sidecar["sha256"]))
    return out


def cmd_publish(ctx: Ctx, tar: pathlib.Path | None = None) -> None:
    if tar is None:
        tar = (
            pathlib.Path(ctx.args.tar) if ctx.args.tar else data_dir(ctx.env) / "images" / TAR_NAME
        )
    side_path = pathlib.Path("%s.json" % tar)
    if ctx.dry and not side_path.is_file():
        # `pack --dry-run` writes no sidecar, so a dry rebake has nothing to read here.
        ctx.say("DRY-RUN publish %s: no sidecar %s yet, `pack` writes it" % (tar, side_path))
        return
    try:
        side = json.loads(side_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ImageError(
            "cannot read %s, the sidecar `pack` writes (%s)" % (side_path, exc)
        ) from exc
    problems = input_mismatch(
        ctx.doc, str(side.get("iso_sha256")), str(side.get("virtio_iso_sha256"))
    )
    if problems:
        raise ImageError("refusing to publish %s: %s" % (tar, "; ".join(problems)))
    if not build_ok(side.get("build")):
        raise ImageError("the sidecar names no build")
    installed = parse_instant(side.get("installed_at"), "installed_at")
    parse_instant(side.get("expires_at"), "expires_at")
    if not ctx.dry:
        if not SHA256_HEX.match(str(side.get("sha256", ""))):
            raise ImageError("the sidecar carries no sha256")
        verify(tar, str(side["sha256"]), str(tar))
    ctx.need_secrets()
    key = "images/win11/%s-%s/%s" % (side["build"], installed.date().isoformat(), TAR_NAME)
    ctx.upload(tar, key)
    ctx.doc["image"] = {
        "key": key,
        "sha256": side.get("sha256", ""),
        "bytes": side.get("bytes", 0),
        "edition": side.get("edition", ""),
        "build": side["build"],
        "iso_sha256": side["iso_sha256"],
        "virtio_iso_sha256": side["virtio_iso_sha256"],
        "installed_at": side["installed_at"],
        "expires_at": side["expires_at"],
        "expiry_source": side.get("expiry_source", EXPIRY_SOURCE),
    }
    ctx.save()


def build_ok(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def cmd_fetch(ctx: Ctx) -> None:
    image = ctx.doc.get("image")
    if not isinstance(image, dict):
        raise ImageError("the record holds no image; `publish` one first, or bake from the inputs")
    ctx.need_secrets()
    images = data_dir(ctx.env) / "images"
    part = images / ("%s.part" % TAR_NAME)
    if not ctx.dry:
        images.mkdir(parents=True, exist_ok=True)
    try:
        ctx.download(str(image["key"]), part)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    if not ctx.dry:
        verify(part, str(image["sha256"]), str(image["key"]))
    ctx.run(["tar", "--zstd", "-xf", str(part), "-C", str(images)], "unpack")
    if not ctx.dry:
        part.unlink(missing_ok=True)
        ctx.say("fetched %s into %s" % (image["key"], images / GOLDEN_DIR))


def cmd_fetch_inputs(ctx: Ctx) -> dict[str, pathlib.Path]:
    """Both ISOs at the paths renet reads; a set `WINDOWS_ISO` or `VIRTIO_ISO` wins and skips that download."""
    inputs = ctx.doc.get("inputs")
    images = data_dir(ctx.env) / "images"
    got: dict[str, pathlib.Path] = {}
    for label, override, name in (
        ("iso", "WINDOWS_ISO", ISO_NAME),
        ("virtio", "VIRTIO_ISO", VIRTIO_NAME),
    ):
        entry = inputs.get(label) if isinstance(inputs, dict) else None
        local = ctx.env.get(override, "")
        if local:
            path = pathlib.Path(local)
            if not path.is_file():
                raise ImageError("%s=%s is not a file" % (override, local))
            if isinstance(entry, dict) and not ctx.dry and sha256_file(path) != entry["sha256"]:
                raise ImageError(
                    "%s=%s does not hash to the recorded inputs.%s.sha256 %s"
                    % (override, local, label, entry["sha256"])
                )
            ctx.say("%s: %s=%s, no download" % (label, override, local))
            got[label] = path
            continue
        if not isinstance(entry, dict):
            raise ImageError(
                "the record holds no inputs.%s; run `upload-inputs` first or set %s"
                % (label, override)
            )
        ctx.need_secrets()
        final = images / name
        part = images / ("%s.part" % name)
        if not ctx.dry:
            images.mkdir(parents=True, exist_ok=True)
        ctx.download(str(entry["key"]), part)
        if not ctx.dry:
            verify(part, str(entry["sha256"]), str(entry["key"]))
            part.replace(final)
            ctx.say("%s: %s verified" % (label, final))
        got[label] = final
    return got


def cmd_rebake(ctx: Ctx) -> None:
    inputs = ctx.doc.get("inputs")
    if not isinstance(inputs, dict):
        raise ImageError(
            "the record holds no inputs; `upload-inputs` must run once before a rebake"
        )
    got = cmd_fetch_inputs(ctx)
    ctx.run(
        [
            ctx.args.renet,
            "ops",
            "windows",
            "bake",
            "--iso",
            str(got["iso"]),
            "--virtio-iso",
            str(got["virtio"]),
        ],
        "bake",
    )
    ctx.args.iso_sha256 = inputs["iso"]["sha256"]
    ctx.args.virtio_iso_sha256 = inputs["virtio"]["sha256"]
    tar = cmd_pack(ctx)
    cmd_publish(ctx, tar)


def cmd_probe(ctx: Ctx) -> None:
    """A signed LIST of the bucket answers 200, a signed LIST of the public-data bucket 403, and an unsigned GET of the bucket is refused."""
    legs = (
        ("signed list", ctx.bucket, True, lambda s: s == 200),
        ("signed list", PUBLIC_DATA_BUCKET, True, lambda s: s == 403),
        ("anonymous get", ctx.bucket, False, lambda s: s in (400, 401, 403)),
    )
    ctx.need_secrets()
    failed = []
    for verb, bucket, signed, ok in legs:
        url = "%s/%s?list-type=2&max-keys=1" % (ctx.endpoint.rstrip("/"), bucket)
        if ctx.dry:
            ctx.say("DRY-RUN %s %s" % (verb, bucket))
            continue
        headers = (
            wire.sigv4_headers(
                "GET", url, b"", SIGV4_REGION, ctx.env[SECRET_NAMES[0]], ctx.env[SECRET_NAMES[1]]
            )
            if signed
            else {}
        )
        try:
            status = ctx.transport("GET", url, headers)
            shown, passed = str(status), ok(status)
        except OSError as exc:
            shown, passed = "transport error (%s)" % type(exc).__name__, False
        verdict = "PASS" if passed else "FAIL"
        ctx.say("%-5s %-14s %-24s %s" % (verdict, verb, bucket, shown))
        if verdict == "FAIL":
            failed.append("%s %s" % (verb, bucket))
    if failed:
        raise ImageError("probe failed: %s" % ", ".join(failed))


# ---- the entry -------------------------------------------------------------


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    top = argparse.ArgumentParser(
        prog="python3 -m rediacc_ci.ops.windows_image", description=__doc__.splitlines()[0]
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dry-run", action="store_true", help="print every step, touch nothing")
    common.add_argument("--record", default="", help=argparse.SUPPRESS)
    common.add_argument(
        "--bucket", default="", help="override the record's bucket (never the public-data bucket)"
    )
    common.add_argument(
        "--endpoint", default="", help="the R2 S3 endpoint (default: the account's)"
    )
    verbs = top.add_subparsers(dest="verb", required=True)
    up = verbs.add_parser("upload-inputs", parents=[common])
    up.add_argument("iso")
    up.add_argument("virtio_iso")
    up.add_argument("--build", default="")
    for name in ("pack", "rebake"):
        p = verbs.add_parser(name, parents=[common])
        p.add_argument("--golden", default="")
        p.add_argument("--out", default="")
        p.add_argument("--iso-sha256", default="")
        p.add_argument("--virtio-iso-sha256", default="")
        if name == "rebake":
            p.add_argument("--renet", default="renet")
    pub = verbs.add_parser("publish", parents=[common])
    pub.add_argument("tar", nargs="?", default="")
    fetch = verbs.add_parser("fetch", parents=[common])
    fetch.add_argument(
        "--inputs", action="store_true", help="fetch the two ISOs instead of the image"
    )
    verbs.add_parser("probe", parents=[common])
    return top.parse_args(list(argv))


def run(
    argv: Sequence[str],
    env: Mapping[str, str],
    runner: Runner = _run,
    transport: Transport = _transport,
    out=None,
) -> int:
    args = parse_args(argv)
    out = out or sys.stdout
    try:
        ctx = Ctx(args, env, runner, transport, out)
        if args.verb == "upload-inputs":
            cmd_upload_inputs(ctx)
        elif args.verb == "pack":
            cmd_pack(ctx)
        elif args.verb == "publish":
            cmd_publish(ctx)
        elif args.verb == "fetch" and args.inputs:
            cmd_fetch_inputs(ctx)
        elif args.verb == "fetch":
            cmd_fetch(ctx)
        elif args.verb == "rebake":
            cmd_rebake(ctx)
        else:
            cmd_probe(ctx)
    except ImageError as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(sys.argv[1:] if argv is None else argv, os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
