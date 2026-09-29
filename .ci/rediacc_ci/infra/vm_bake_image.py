#!/usr/bin/env python3
"""Publish and fetch the pre-baked E2E VM images (PLAN-ci-prebaked-vm-images.md, boxes B4 and B5).

One private GHCR package, `ghcr.io/rediacc/ci-vm-bake`, holds every baked image as a single-layer OCI artifact tagged by its bake key (`rediacc_ci.infra.vm_bake_key`, `vm-bake-v1-<distro>-<YYYY-MM>-<sha256[:16]>`). The key names the distro, so one package serves all five; its layer is the qcow2 `renet ops image build` wrote, under the base image's own URL basename, which is the name `renet ops up` looks up in its disks cache.

Subcommands, one per workflow step, so each `run:` stays one line:

  install-oras   download the pinned oras release, verify its sha256, put it on GITHUB_PATH.
  probe          (ci-vm-bake.yml) compute the key and report whether the tag already exists.
                 A registry "not found" is a miss; any other oras failure is an error, so a
                 broken login cannot pass for a missing image and trigger a pointless rebake.
  build          (ci-vm-bake.yml) run `renet ops image build --bake-key` on its own NAT network.
  publish        (ci-vm-bake.yml) push the built image under the key, then read the tag back.
  fetch          (ct-tests.yml, E2E Workers) install oras when it is not on PATH, then pull the
                 image for this tree's key into a separate disks directory. On a hit it exports
                 REDIACC_OPS_DISKS_PATH, BAKED_IMAGE_KEY and RENET_SETUP_OFFLINE=1 and sets output
                 hit=true. Every failure, "not found" included, is a miss (hit=false, exit 0): the
                 leg then runs the stock image exactly as before.

Outputs go to $GITHUB_OUTPUT and exports to $GITHUB_ENV when those are set, and to stdout as KEY=value lines otherwise, so each subcommand can be driven by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from typing import TYPE_CHECKING

from rediacc_ci.infra import vm_bake_key

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    RunFn = Callable[..., subprocess.CompletedProcess[str]]

REPOSITORY = "ghcr.io/rediacc/ci-vm-bake"
ARTIFACT_TYPE = "application/vnd.rediacc.vm-bake.v1"
LAYER_MEDIA_TYPE = "application/vnd.rediacc.vm-image.qcow2"
SOURCE_ANNOTATION = "org.opencontainers.image.source=https://github.com/rediacc/console"

ORAS_VERSION = "1.3.4"
ORAS_SHA256_LINUX_AMD64 = "f27adb935022d94df8dc77719c322dda592c78a0d57a6f7dcdd8d900b248c454"
ORAS_URL = (
    "https://github.com/oras-project/oras/releases/download/v%s/oras_%s_linux_amd64.tar.gz"
    % (ORAS_VERSION, ORAS_VERSION)
)

# The build VM gets its own libvirt NAT network rather than libvirt's "default", which a host without libvirt-daemon-config-network lacks; 192.168.150.0/24 stays clear of the ops fleet (192.168.111.0/24) and of libvirt's default (192.168.122.0/24).
BAKE_NETWORK = "rediacc-bake"
BAKE_NETWORK_XML = (
    """<network>
  <name>%s</name>
  <forward mode='nat'/>
  <ip address='192.168.150.1' netmask='255.255.255.0'>
    <dhcp><range start='192.168.150.10' end='192.168.150.200'/></dhcp>
  </ip>
</network>
"""
    % BAKE_NETWORK
)

FETCH_TIMEOUT_S = 480
PUSH_TIMEOUT_S = 600


class BakeImageError(RuntimeError):
    """A bake-side step failed in a way the workflow must see."""


def image_ref(key: str) -> str:
    if not vm_bake_key.KEY_RE.match(key):
        raise BakeImageError("not a bake key: %r" % key)
    return "%s:%s" % (REPOSITORY, key)


def _emit(kind: str, pairs: dict[str, str]) -> None:
    """Append KEY=value lines to $GITHUB_OUTPUT (kind 'output') or $GITHUB_ENV ('env'), else print them."""
    target = (
        os.environ.get("GITHUB_OUTPUT", "")
        if kind == "output"
        else os.environ.get("GITHUB_ENV", "")
    )
    lines = "".join("%s=%s\n" % (k, v) for k, v in pairs.items())
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(lines)
    else:
        sys.stdout.write(lines)


def _run(argv: Sequence[str], **kw: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), text=True, check=False, **kw)  # type: ignore[call-overload,no-any-return]


# --- install-oras ------------------------------------------------------------


def _download(url: str, dest: pathlib.Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as out:  # noqa: S310 - a pinned https URL
        shutil.copyfileobj(resp, out)


def install_oras(
    dest: pathlib.Path, download: Callable[[str, pathlib.Path], None] = _download
) -> pathlib.Path:
    """Download the pinned oras, refuse it unless its sha256 matches the pin, and install it as dest/oras."""
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise BakeImageError(
            "oras is pinned for linux/amd64 only, not %s/%s"
            % (platform.system(), platform.machine())
        )
    dest.mkdir(parents=True, exist_ok=True)
    binary = dest / "oras"
    with tempfile.TemporaryDirectory() as tmp:
        archive = pathlib.Path(tmp) / "oras.tar.gz"
        download(ORAS_URL, archive)
        got = hashlib.sha256(archive.read_bytes()).hexdigest()
        if got != ORAS_SHA256_LINUX_AMD64:
            raise BakeImageError(
                "oras %s sha256 mismatch: got %s, pinned %s"
                % (ORAS_VERSION, got, ORAS_SHA256_LINUX_AMD64)
            )
        try:
            with tarfile.open(archive) as tar:
                src = tar.extractfile(tar.getmember("oras"))
                if src is None:
                    raise BakeImageError("the oras archive's oras member is not a regular file")
                binary.write_bytes(src.read())
        except (KeyError, tarfile.TarError) as exc:
            raise BakeImageError("the oras archive is unreadable or has no oras: %s" % exc) from exc
    binary.chmod(0o755)
    return binary


# --- probe -------------------------------------------------------------------


def tag_exists(ref: str, run: RunFn = _run) -> bool:
    """True when the tag resolves, False on a registry "not found", BakeImageError on anything else."""
    res = run(["oras", "manifest", "fetch", "--descriptor", ref], capture_output=True, timeout=120)
    if res.returncode == 0:
        return True
    if "not found" in (res.stderr or "").lower():
        return False
    raise BakeImageError(
        "oras manifest fetch %s failed (rc=%d): %s"
        % (ref, res.returncode, (res.stderr or "").strip())
    )


# --- build -------------------------------------------------------------------


def ensure_network(run: RunFn = _run) -> None:
    """Define BAKE_NETWORK unless libvirt already knows it; the builder starts it."""
    if run(["sudo", "virsh", "net-info", BAKE_NETWORK], capture_output=True).returncode == 0:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as fh:
        fh.write(BAKE_NETWORK_XML)
        xml = fh.name
    try:
        res = run(["sudo", "virsh", "net-define", xml], capture_output=True)
    finally:
        os.unlink(xml)
    if res.returncode != 0:
        raise BakeImageError(
            "virsh net-define %s failed: %s"
            % (BAKE_NETWORK, (res.stderr or res.stdout or "").strip())
        )


def build(
    distro: str, key: str, out_dir: pathlib.Path, renet: str = "renet", run: RunFn = _run
) -> pathlib.Path:
    """Bake one distro into out_dir and return the image path renet printed."""
    image_ref(key)
    ensure_network(run)
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = [
        renet,
        "ops",
        "image",
        "build",
        "--os",
        distro,
        "--output",
        str(out_dir),
        "--bake-key",
        key,
        "--network",
        BAKE_NETWORK,
    ]
    print("+ %s" % " ".join(argv), flush=True)
    # renet logs to stderr, which streams into the job log; stdout carries only the output path.
    res = run(argv, stdout=subprocess.PIPE)
    if res.returncode != 0:
        raise BakeImageError("renet ops image build exited %d" % res.returncode)
    lines = [ln.strip() for ln in (res.stdout or "").splitlines() if ln.strip()]
    image = pathlib.Path(lines[-1]) if lines else None
    if image is None or not image.is_file() or image.stat().st_size == 0:
        raise BakeImageError(
            "renet ops image build printed no usable image path: %r" % (res.stdout or "")
        )
    return image


# --- publish -----------------------------------------------------------------


def publish(image: pathlib.Path, key: str, distro: str, run: RunFn = _run) -> str:
    """Push image under the key's tag, then prove the tag resolves."""
    ref = image_ref(key)
    if not image.is_file() or image.stat().st_size == 0:
        raise BakeImageError("no image to publish at %s" % image)
    argv = [
        "oras",
        "push",
        ref,
        "%s:%s" % (image.name, LAYER_MEDIA_TYPE),
        "--artifact-type",
        ARTIFACT_TYPE,
        "--annotation",
        SOURCE_ANNOTATION,
        "--annotation",
        "com.rediacc.vm-bake.distro=%s" % distro,
        "--annotation",
        "com.rediacc.vm-bake.key=%s" % key,
    ]
    # oras refuses an absolute layer path, so it runs beside the image.
    res = run(argv, cwd=str(image.parent), timeout=PUSH_TIMEOUT_S)
    if res.returncode != 0:
        raise BakeImageError("oras push %s exited %d" % (ref, res.returncode))
    if not tag_exists(ref, run):
        raise BakeImageError("oras push reported success but %s does not resolve" % ref)
    return ref


# --- fetch -------------------------------------------------------------------


def fetch(key: str, dest: pathlib.Path, run: RunFn = _run) -> tuple[pathlib.Path | None, str]:
    """(image, "") on a hit; (None, reason) on any miss. A registry or pull failure is a miss, never an exception."""
    ref = image_ref(key)
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    try:
        res = run(
            ["oras", "pull", ref, "--output", str(dest)],
            capture_output=True,
            timeout=FETCH_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        return None, "oras pull %s did not complete: %s" % (ref, exc)
    if res.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        err = (res.stderr or "").strip()
        if "not found" in err.lower():
            return None, "no baked image published for %s" % key
        return None, "oras pull %s failed (rc=%d): %s" % (ref, res.returncode, err)
    files = [p for p in dest.iterdir() if p.is_file()]
    if len(files) != 1 or files[0].stat().st_size == 0:
        shutil.rmtree(dest, ignore_errors=True)
        return None, "%s pulled %d file(s), expected one non-empty image" % (ref, len(files))
    return files[0], ""


# --- CLI ---------------------------------------------------------------------


def _key(distro: str) -> str:
    return vm_bake_key.compute_key(vm_bake_key.default_renet_root(), distro)


def _default_oras_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / "oras-bin"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m rediacc_ci.infra.vm_bake_image",
        description="Publish and fetch the pre-baked E2E VM images.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("install-oras")
    p.add_argument("--dest", type=pathlib.Path, default=_default_oras_dir())
    p = sub.add_parser("probe")
    p.add_argument("--distro", required=True)
    p = sub.add_parser("build")
    p.add_argument("--distro", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    p.add_argument("--renet", default="renet")
    p = sub.add_parser("publish")
    p.add_argument("--distro", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--image", type=pathlib.Path, required=True)
    p = sub.add_parser("fetch")
    p.add_argument("--distro", required=True)
    p.add_argument("--dest", type=pathlib.Path, required=True)
    p.add_argument("--oras-dir", type=pathlib.Path, default=_default_oras_dir())
    return parser


def _cmd_fetch(distro: str, dest: pathlib.Path, oras_dir: pathlib.Path) -> int:
    """Every failure here is a miss, and a miss is the stock image: always exit 0, so the step needs no continue-on-error."""
    try:
        key = _key(distro)
        if shutil.which("oras") is None:
            install_oras(oras_dir)
            os.environ["PATH"] = "%s%s%s" % (oras_dir, os.pathsep, os.environ.get("PATH", ""))
        image, reason = fetch(key, dest)
    except (BakeImageError, vm_bake_key.BakeKeyError, OSError) as exc:
        print("::warning::no baked image, using the stock image: %s" % exc)
        _emit("output", {"hit": "false"})
        return 0
    if image is None:
        level = "notice" if reason.startswith("no baked image") else "warning"
        print("::%s::%s; using the stock image" % (level, reason))
        _emit("output", {"hit": "false", "key": key})
        return 0
    _emit(
        "env",
        {"REDIACC_OPS_DISKS_PATH": str(dest), "BAKED_IMAGE_KEY": key, "RENET_SETUP_OFFLINE": "1"},
    )
    _emit("output", {"hit": "true", "key": key})
    print("baked image %s (%d bytes) from %s" % (image.name, image.stat().st_size, image_ref(key)))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "install-oras":
            binary = install_oras(args.dest)
            print("oras %s installed at %s" % (ORAS_VERSION, binary))
            path_file = os.environ.get("GITHUB_PATH", "")
            if path_file:
                with open(path_file, "a", encoding="utf-8") as handle:
                    handle.write("%s\n" % args.dest)
            return 0
        if args.cmd == "probe":
            key = _key(args.distro)
            exists = tag_exists(image_ref(key))
            print(
                "%s %s"
                % (image_ref(key), "exists; nothing to bake" if exists else "is missing; baking")
            )
            _emit("output", {"key": key, "exists": "true" if exists else "false"})
            return 0
        if args.cmd == "build":
            image = build(args.distro, args.key, args.output, args.renet)
            print("built %s (%d bytes)" % (image, image.stat().st_size))
            _emit("output", {"image": str(image)})
            return 0
        if args.cmd == "publish":
            print("published %s" % publish(args.image, args.key, args.distro))
            return 0
        return _cmd_fetch(args.distro, args.dest, args.oras_dir)
    except (BakeImageError, vm_bake_key.BakeKeyError) as exc:
        print("vm_bake_image: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
