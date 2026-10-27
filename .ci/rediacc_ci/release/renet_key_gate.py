"""Refuse a renet build that does not bake the production licence key.

    PYTHONPATH=.ci python3 -m rediacc_ci.release.renet_key_gate <binary>... [--image <ref>]... [--dev-cache <public-keys.env>]...

The expected key is `ACCOUNT_ED25519_PUBLIC_KEY`, supplied by `bws_env exec` (PLAN-local-release W1-E). Every binary named, and every renet inside each `--image` (`/app/renet` and `/opt/renet/renet-linux-{amd64,arm64}`, copied out through `docker create`/`docker cp`), is read with `go version -m`, and the verdict is taken from its build info:

  * the `-X github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey=` ldflag. Absent or empty means every licence reads as not installed;
  * the DEV key's fingerprint, read from `private/account/.cache/public-keys.env` under this checkout, else from each `--dev-cache` path (the release clone has no cache, so `release:local` names the operator checkout's). `private/renet/build.sh` (`_account_key_ldflags`) bakes it with only a warning when the environment carries no key. With no DEV key readable the run refuses: an `ACCOUNT_ED25519_PUBLIC_KEY` holding the DEV key would then pass every DEV-baked binary as production;
  * `-tags=nolicense`, a build with the licence checks compiled out;
  * any key other than the expected one.

The expected key itself is refused when it is empty, malformed, or the DEV key. Only fingerprints are printed (renet's publicKeyId: the first 8 bytes of SHA-256 over the raw 32-byte key), never a key.

The build-info reader here is the one `testrun/start_backup_plane.py --verify-renet` uses; that module imports it from here.

Exit 0 when every binary passes, 1 when any is refused, 2 on a usage error.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.well_known import RENET_REPO

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

PUBLIC_KEY_ENV = "ACCOUNT_ED25519_PUBLIC_KEY"
# `private/renet/build.sh` `_account_key_ldflags` reads the DEV key from here; it holds public keys only.
DEV_KEY_CACHE = pathlib.Path("private") / "account" / ".cache" / "public-keys.env"
# The linker symbol `build_renet.KEY_SYMBOL` sets. The value may be empty (`-X sym=`), which is matched so it can be named.
BAKED_KEY = re.compile(
    r"github\.com/"
    + re.escape(RENET_REPO)
    + r"/pkg/license/keys\.ProductionPublicKey=([A-Za-z0-9+/=]*)"
)
BAKED_VERSION = re.compile(r"-X main\.Version=([^\s\"]*)")
BUILD_TAGS = re.compile(r"^\s*build\s+-tags=(\S*)\s*$", re.MULTILINE)
# DER header of an SPKI-wrapped ED25519 public key; the raw 32-byte key follows it.
SPKI_ED25519_HEADER = bytes.fromhex("302a300506032b6570032100")
# Where the renet image carries renet (private/renet/Dockerfile `COPY ... /app/renet`, `/opt/renet/...`).
IMAGE_RENETS = ("/app/renet", "/opt/renet/renet-linux-amd64", "/opt/renet/renet-linux-arm64")
USAGE = "usage: PYTHONPATH=.ci python3 -m rediacc_ci.release.renet_key_gate <binary>... [--image <ref>]... [--dev-cache <public-keys.env>]..."


class KeyGateError(Exception):
    """A key or a binary's build info cannot be read."""


@dataclasses.dataclass(frozen=True)
class BuildInfo:
    """What `go version -m` says about a renet binary. `key` is None when no key ldflag is present, "" when it is present and empty."""

    key: str | None
    version: str | None
    tags: tuple[str, ...]


def key_fingerprint(public_key: str) -> str:
    """renet's publicKeyId (pkg/subscription/fingerprint.go): the first 8 bytes of SHA-256 over the raw 32-byte key, in hex. Takes the raw key or its SPKI wrapping, base64. The error never carries the key."""
    try:
        der = base64.b64decode(public_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise KeyGateError(f"not a base64 ED25519 public key: {exc}") from exc
    if len(der) == len(SPKI_ED25519_HEADER) + 32 and der.startswith(SPKI_ED25519_HEADER):
        der = der[len(SPKI_ED25519_HEADER) :]
    if len(der) != 32:
        raise KeyGateError(f"not an ED25519 public key ({len(der)} bytes after decoding)")
    return hashlib.sha256(der).hexdigest()[:16]


def go_version_m(
    binary: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> str:
    """The build info `go version -m <binary>` prints."""
    try:
        done = run(
            ["go", "version", "-m", binary],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise KeyGateError(f"cannot run `go version -m {binary}`: {exc}") from exc
    if done.returncode != 0 or not done.stdout:
        raise KeyGateError(
            f"cannot read the build info of {binary} (missing, or not a Go binary): {(done.stderr or '').strip()}"
        )
    return done.stdout


def parse_build_info(text: str) -> BuildInfo:
    """The key, version and tags out of `go version -m` text. With the symbol set twice the linker keeps the last, so the last match wins."""
    keys = BAKED_KEY.findall(text)
    versions = BAKED_VERSION.findall(text)
    tags: list[str] = []
    for found in BUILD_TAGS.findall(text):
        tags.extend(t for t in found.split(",") if t)
    return BuildInfo(
        key=keys[-1] if keys else None,
        version=versions[-1] if versions else None,
        tags=tuple(tags),
    )


def baked_public_key(
    binary: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> str:
    """The key `-X .../keys.ProductionPublicKey=` baked into `binary`; refuses a binary that bakes none."""
    key = parse_build_info(go_version_m(binary, run)).key
    if not key:
        raise KeyGateError(
            f"{binary} bakes no licence key (its build info carries no keys.ProductionPublicKey ldflag): every repository licence reads as not installed. Rebuild with {PUBLIC_KEY_ENV} exported."
        )
    return key


def dev_fingerprint(root: pathlib.Path) -> str | None:
    """The DEV key's fingerprint from the public-key cache, or None when there is no cache or no readable key in it."""
    return dev_fingerprint_at(root / DEV_KEY_CACHE)


def dev_fingerprint_at(cache: pathlib.Path) -> str | None:
    """The DEV key's fingerprint from the public-key cache file `cache`, or None when it is absent or carries no readable key."""
    try:
        text = cache.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith(PUBLIC_KEY_ENV + "="):
            value = line[len(PUBLIC_KEY_ENV) + 1 :].strip().strip("'\"")
            try:
                return key_fingerprint(value) if value else None
            except KeyGateError:
                return None
    return None


def refusals(info: BuildInfo, want: str, dev: str | None) -> tuple[list[str], str | None]:
    """Every reason `info` is refused, and the baked key's fingerprint (None when there is none to print)."""
    reasons: list[str] = []
    have: str | None = None
    if not info.key:
        reasons.append("empty key" if info.key == "" else "no key ldflag")
    else:
        try:
            have = key_fingerprint(info.key)
        except KeyGateError as exc:
            reasons.append(f"baked key unreadable ({exc})")
    if have is not None and dev is not None and have == dev:
        reasons.append("DEV key")
    elif have is not None and have != want:
        reasons.append(f"key {have} is not the production key {want}")
    if "nolicense" in info.tags:
        reasons.append("tags=nolicense")
    return reasons, have


def check_binary(
    binary: str,
    want: str,
    dev: str | None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    label: str | None = None,
) -> bool:
    """One verdict line for `binary`; True when it passes."""
    name = label or binary
    try:
        info = parse_build_info(go_version_m(binary, run))
    except KeyGateError as exc:
        print(f"REFUSED {name}: {exc}", flush=True)
        return False
    reasons, have = refusals(info, want, dev)
    version = info.version or "unset"
    if reasons:
        print(
            f"REFUSED {name}: {'; '.join(reasons)} (baked {have or 'none'}, version {version})",
            flush=True,
        )
        return False
    print(f"ok      {name}: production key {have}, version {version}", flush=True)
    return True


def _docker(
    argv: list[str], run: Callable[..., subprocess.CompletedProcess]
) -> subprocess.CompletedProcess:
    try:
        return run(
            ["docker", *argv], capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL
        )
    except OSError as exc:
        raise KeyGateError(f"cannot run docker: {exc}") from exc


def check_image(
    image: str,
    want: str,
    dev: str | None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    """Copy every renet out of `image` and check each one. A renet the image does not carry is refused, never skipped."""
    try:
        created = _docker(["create", image], run)
    except KeyGateError as exc:
        print(f"REFUSED {image}: {exc}", flush=True)
        return False
    if created.returncode != 0 or not created.stdout.strip():
        print(
            f"REFUSED {image}: docker create failed: {(created.stderr or '').strip()}", flush=True
        )
        return False
    container = created.stdout.strip()
    ok = True
    try:
        with tempfile.TemporaryDirectory(prefix="renet-key-gate-") as scratch:
            for inside in IMAGE_RENETS:
                local = os.path.join(scratch, inside.strip("/").replace("/", "_"))
                label = f"{image}:{inside}"
                try:
                    copied = _docker(["cp", f"{container}:{inside}", local], run)
                except KeyGateError as exc:
                    print(f"REFUSED {label}: {exc}", flush=True)
                    ok = False
                    continue
                if copied.returncode != 0:
                    print(
                        f"REFUSED {label}: not in the image ({(copied.stderr or '').strip()})",
                        flush=True,
                    )
                    ok = False
                    continue
                ok = check_binary(local, want, dev, run, label=label) and ok
    finally:
        try:
            _docker(["rm", container], run)
        except KeyGateError as exc:
            print(f"renet_key_gate: container {container} not removed: {exc}", file=sys.stderr)
    return ok


def parse(argv: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
    binaries: list[str] = []
    images: list[str] = []
    caches: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--image", "--dev-cache"):
            if i + 1 >= len(argv) or not argv[i + 1]:
                raise ValueError(f"{arg} needs a value")
            (images if arg == "--image" else caches).append(argv[i + 1])
            i += 2
            continue
        if arg.startswith("-"):
            raise ValueError(f"Unknown option: {arg}")
        binaries.append(arg)
        i += 1
    if not binaries and not images:
        raise ValueError("name at least one renet binary or --image")
    return binaries, images, caches


def expected_fingerprint(key: str, dev: str | None) -> str:
    """The expected key's fingerprint; refuses an empty, malformed or DEV expected key."""
    if not key:
        raise KeyGateError(
            f"{PUBLIC_KEY_ENV} is not set: run this under `bws_env exec` with the production key"
        )
    want = key_fingerprint(key)
    if dev is not None and want == dev:
        raise KeyGateError(
            f"{PUBLIC_KEY_ENV} is the DEV key ({want}): the gate compares against the production key"
        )
    return want


def main(
    argv: Sequence[str], run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> int:
    try:
        binaries, images, caches = parse(argv)
    except ValueError as exc:
        print(f"renet_key_gate: {exc}\n{USAGE}", file=sys.stderr)
        return 2
    dev = dev_fingerprint(paths.repo_root())
    for cache in caches:
        dev = dev or dev_fingerprint_at(pathlib.Path(cache))
    if dev is None:
        print(
            f"renet_key_gate: the DEV key is unknown (no readable {DEV_KEY_CACHE} here or at any --dev-cache), "
            f"so a {PUBLIC_KEY_ENV} holding it could not be told from the production key; refusing",
            file=sys.stderr,
        )
        return 1
    try:
        want = expected_fingerprint(os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", ""), dev)
    except KeyGateError as exc:
        print(f"renet_key_gate: {exc}", file=sys.stderr)
        return 1
    print(
        f"renet_key_gate: expected production key {want}; DEV key {dev}",
        flush=True,
    )
    ok = True
    for binary in binaries:
        ok = check_binary(binary, want, dev, run) and ok
    for image in images:
        ok = check_image(image, want, dev, run) and ok
    if not ok:
        print("renet_key_gate: REFUSED", file=sys.stderr)
        return 1
    print("renet_key_gate: every renet bakes the production key", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
