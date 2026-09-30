#!/usr/bin/env python3
"""Keep the pinned openSUSE Leap 16.0 Ceph build alive after OBS drops it (agent/plans/PLAN-renet-obs-mirror.md, D2).

OBS `filesystems:ceph:squid/16.0` keeps only its latest build, and renet pins one exact EVR. This module captures a build while OBS still serves it: a byte copy of the OBS `repodata/` (so the `repomd.xml` signature still verifies against the key renet embeds, and every gpg check stays on) plus only the RPMs renet installs from that repository, at their original paths. The tree is one uncompressed tar in the private `ghcr.io/rediacc/ci-vm-bake` package, tagged `obs-mirror-v1-opensuse-16.0-<EVR>`, and never overwritten.

Subcommands, one per workflow step, so each `run:` stays one line:

  upstream  fetch the origin `repomd.xml` and its signature, gpgv it with the OBS key (after asserting the key's fingerprint equals cephpkg.go's OBSKeyFingerprint), fetch `primary`, check its checksum, and report the current ceph-common/cephadm EVR (`obs_evr`) beside the tree's pin (`pin`, .ceph-image-pin).
  capture   capture one EVR: stop on an existing tag; download and check the repodata (retried from a fresh repomd on a mid-publish mismatch); refuse an EVR `primary` does not list; derive the package set in an opensuse/leap:16.0 container; download each RPM and check it against `primary`; `rpm -K` with only the OBS key; prove the staged tree with one positive and two negative container checks; push; read back. `--stage-only --out <dir>` does everything but the registry: no tag probe, no push.
  fetch     pull the tag for a pin into a directory and check its signature. A miss is rc 1: CI needs the mirror.
  serve     start a detached `python3 -m http.server` on every interface for the E2E VMs (192.168.111.1 from the fleet).

THE PACKAGE SET is what renet's own two zypper steps (cephpkg's pinned `ceph-common=<EVR> cephadm=<EVR>`, then the profiles' other names, both `--no-recommends`) install from the OBS origin in a fresh container, intersected by (name, EVR, arch) with `primary`. The names are read from pkgset.go's Ceph sets, the union over every profile, so the set grows with renet. The steps run at the EVR being captured rather than through `renet ceph install`, because renet installs only its own pin and the point of capturing OBS's current build is that it may not be the pin yet.

THE CONTAINER CHECKS (plan section 6). Every one runs in a fresh opensuse/leap:16.0 container with download.opensuse.org and downloadcontent.opensuse.org resolved to 127.0.0.1, so OBS is unreachable and the staged tree, bind-mounted read-only at /srv/obs-mirror and addressed as `dir:/srv/obs-mirror`, is the only source of a Ceph package:

  POSITIVE    the package set installs and `rpm -q` equals the EVR; and, when `--renet` is given and the EVR is the tree's pin, `renet ceph install` of every profile installs from the mirror named in /etc/rediacc/ceph-zypper-mirror.
  NEGATIVE 1  the tree minus librados2 must FAIL the install, naming librados2: zypper reads the mirror.
  NEGATIVE 2  a one-byte change to repomd.xml must FAIL `zypper refresh`: repo_gpgcheck is on.

Outputs go to $GITHUB_OUTPUT when it is set and to stdout as KEY=value lines otherwise, so each subcommand can be driven by hand.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import gzip
import hashlib
import json
import lzma
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Self

from rediacc_ci.infra.vm_bake_image import REPOSITORY, BakeImageError, install_oras, tag_exists

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    RunFn = Callable[..., subprocess.CompletedProcess[str]]
    GetFn = Callable[[str], bytes]

ROOT = pathlib.Path(__file__).resolve().parents[3]
RENET_ROOT = ROOT / "private" / "renet"
PIN_FILE = RENET_ROOT / ".ceph-image-pin"
CEPHPKG_GO = RENET_ROOT / "pkg" / "infra" / "cephpkg" / "cephpkg.go"
PKGSET_GO = RENET_ROOT / "pkg" / "infra" / "pkgset" / "pkgset.go"
CEPH_INSTALL_GO = RENET_ROOT / "cmd" / "renet" / "ceph_install.go"
KEY_FILE = RENET_ROOT / "pkg" / "infra" / "cephpkg" / "keys" / "RPM-GPG-KEY-obs-filesystems-ceph"

TARGET = "opensuse-16.0"
# The origin, not the download.opensuse.org redirector: a redirected mirror can lag a publish.
OBS_ORIGIN = "https://downloadcontent.opensuse.org/repositories/filesystems:/ceph:/squid/16.0/"
LEAP_IMAGE = "opensuse/leap:16.0"
ARCHES = ("x86_64", "noarch")
PINNED = ("ceph-common", "cephadm")
# The Ceph sets of pkgset.go whose zypper names `renet ceph install` puts on a host, across every profile.
CEPH_SETS = ("CephClient", "CephAdmin", "CephNode", "ClusterForkDest")

TAG_PREFIX = "obs-mirror-v1-%s-" % TARGET
ARTIFACT_TYPE = "application/vnd.rediacc.obs-mirror.v1"
LAYER_MEDIA_TYPE = "application/vnd.rediacc.obs-mirror.v1.tar"
LAYER_NAME = "obs-mirror.tar"
ANNOTATION = "com.rediacc.obs-mirror."
SOURCE_ANNOTATION = "org.opencontainers.image.source=https://github.com/rediacc/console"

MIRROR_MOUNT = "/srv/obs-mirror"
MIRROR_URL = "dir:%s" % MIRROR_MOUNT
# renet's channel (cephpkg.MirrorConfigPath): `sudo renet` over SSH drops the environment, so the file is what counts.
MIRROR_CONFIG = "/etc/rediacc/ceph-zypper-mirror"
BLOCKED_HOSTS = ("download.opensuse.org", "downloadcontent.opensuse.org")
NEGATIVE_1_PACKAGE = "librados2"
SETUP_MOUNT = "/obs-setup"

# A Leap EVR carries no epoch, and an OCI tag allows neither ':' nor '+' nor '~'.
EVR_RE = re.compile(r"^[0-9][0-9A-Za-z._]*-[0-9A-Za-z._]+$")
METADATA_ATTEMPTS = 3
HTTP_TIMEOUT_S = 120
PULL_TIMEOUT_S = 600
PUSH_TIMEOUT_S = 900
SERVE_PORT = 8089

NS_REPO = "{http://linux.duke.edu/metadata/repo}"
NS_COMMON = "{http://linux.duke.edu/metadata/common}"


class MirrorError(RuntimeError):
    """A capture, fetch or verification step failed in a way the workflow must see."""


# --- renet's own sources: the fingerprint, the repo stanza, the names ---------


def _go_const(text: str, name: str) -> str:
    m = re.search(r'\b%s\s*=\s*"([^"]+)"' % re.escape(name), text)
    if not m:
        raise MirrorError("%s not found in %s" % (name, CEPHPKG_GO))
    return m.group(1)


def obs_fingerprint(cephpkg_go: str) -> str:
    return _go_const(cephpkg_go, "OBSKeyFingerprint")


def repo_id(cephpkg_go: str) -> str:
    return _go_const(cephpkg_go, "RepoName")


def key_path(cephpkg_go: str) -> str:
    return _go_const(cephpkg_go, "obsKeyPath")


# The directives of the .repo file cephpkg's leapPlan writes. test_infra_obs_mirror.py holds each one to the Go source, so a change there reds here instead of the checks proving a repository renet does not write.
def repo_directives(key: str) -> list[str]:
    return [
        "enabled=1",
        "autorefresh=1",
        "type=rpm-md",
        "gpgcheck=1",
        "repo_gpgcheck=1",
        "pkg_gpgcheck=1",
        "gpgkey=file://%s" % key,
        "priority=90",
    ]


def repo_file(rid: str, base: str, key: str) -> str:
    lines = [
        "[%s]" % rid,
        "name=filesystems:ceph:squid (Leap 16.0), obs_mirror",
        "baseurl=%s" % base,
    ]
    return "\n".join(lines + repo_directives(key)) + "\n"


def zypper_names(pkgset_go: str, sets: Sequence[str] = CEPH_SETS) -> list[str]:
    """Every quoted name on the Zypper line of each named pkgset.Set, in first-seen order."""
    out: list[str] = []
    for name in sets:
        m = re.search(
            r"^var %s = Set\{\n(.*?)^\}" % re.escape(name), pkgset_go, re.MULTILINE | re.DOTALL
        )
        if not m:
            raise MirrorError("pkgset.%s not found in %s" % (name, PKGSET_GO))
        line = next((ln for ln in m.group(1).splitlines() if ln.strip().startswith("Zypper:")), "")
        if not line:
            raise MirrorError("pkgset.%s has no Zypper entry" % name)
        out.extend(n for n in re.findall(r'"([^"]+)"', line) if n not in out)
    return out


def ceph_profiles(ceph_install_go: str) -> list[str]:
    names = re.findall(
        r'^\s*profile\w+\s+cephProfileName\s*=\s*"([a-z-]+)"', ceph_install_go, re.MULTILINE
    )
    if not names:
        raise MirrorError("no cephProfileName constants in %s" % CEPH_INSTALL_GO)
    return names


def read_pin(text: str, target: str = TARGET) -> str:
    m = re.search(r"^host\.%s=(\S+)$" % re.escape(target), text, re.MULTILINE)
    if not m:
        raise MirrorError("no host.%s line in %s" % (target, PIN_FILE))
    return m.group(1)


def image_ref(evr: str) -> str:
    if not EVR_RE.match(evr):
        raise MirrorError("not a Leap EVR usable in a tag: %r" % evr)
    return "%s:%s%s" % (REPOSITORY, TAG_PREFIX, evr)


# --- repomd and primary -------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RepoData:
    type: str
    href: str
    checksum_type: str
    checksum: str
    size: int | None


@dataclasses.dataclass(frozen=True)
class Repomd:
    revision: str
    data: tuple[RepoData, ...]

    def get(self, kind: str) -> RepoData:
        for d in self.data:
            if d.type == kind:
                return d
        raise MirrorError("repomd.xml has no %s entry" % kind)


@dataclasses.dataclass(frozen=True)
class Package:
    name: str
    arch: str
    epoch: str
    version: str
    release: str
    href: str
    checksum_type: str
    checksum: str
    size: int

    @property
    def evr(self) -> str:
        vr = "%s-%s" % (self.version, self.release)
        return vr if self.epoch in ("", "0") else "%s:%s" % (self.epoch, vr)

    @property
    def nevra(self) -> str:
        return "%s-%s.%s" % (self.name, self.evr, self.arch)


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _safe_relpath(href: str) -> str:
    p = pathlib.PurePosixPath(href)
    if not href or p.is_absolute() or ".." in p.parts:
        raise MirrorError("unsafe path in the metadata: %r" % href)
    return href


def parse_repomd(data: bytes) -> Repomd:
    try:
        root = ET.fromstring(data)  # noqa: S314 - signature-verified before it is trusted; ElementTree expands no external entities
    except ET.ParseError as exc:
        raise MirrorError("repomd.xml does not parse: %s" % exc) from exc
    entries = []
    for d in root.findall(NS_REPO + "data"):
        cs = d.find(NS_REPO + "checksum")
        loc = d.find(NS_REPO + "location")
        size = _text(d.find(NS_REPO + "size"))
        if cs is None or loc is None or not loc.get("href"):
            raise MirrorError("repomd.xml entry %r has no checksum or location" % d.get("type"))
        entries.append(
            RepoData(
                type=d.get("type", ""),
                href=_safe_relpath(loc.get("href", "")),
                checksum_type=cs.get("type", ""),
                checksum=_text(cs),
                size=int(size) if size else None,
            )
        )
    if not entries:
        raise MirrorError("repomd.xml lists no data")
    return Repomd(revision=_text(root.find(NS_REPO + "revision")), data=tuple(entries))


def _hash(kind: str, data: bytes) -> str:
    algo = {"sha": "sha1", "sha1": "sha1", "sha256": "sha256", "sha512": "sha512"}.get(kind)
    if algo is None:
        raise MirrorError("unsupported checksum type %r" % kind)
    return hashlib.new(algo, data).hexdigest()


class ChecksumMismatchError(MirrorError):
    """A file does not match the checksum or size its metadata states."""


def verify_checksum(
    what: str, data: bytes, kind: str, expected: str, size: int | None = None
) -> None:
    if size is not None and len(data) != size:
        raise ChecksumMismatchError(
            "%s is %d bytes, the metadata says %d" % (what, len(data), size)
        )
    got = _hash(kind, data)
    if got != expected:
        raise ChecksumMismatchError(
            "%s %s mismatch: got %s, expected %s" % (what, kind, got, expected)
        )


def decompress(href: str, data: bytes) -> bytes:
    if href.endswith(".gz"):
        return gzip.decompress(data)
    if href.endswith(".xz"):
        return lzma.decompress(data)
    if href.endswith(".xml"):
        return data
    raise MirrorError("no decompressor for %s" % href)


def parse_primary(xml: bytes) -> list[Package]:
    try:
        root = ET.fromstring(xml)  # noqa: S314 - checksum-verified against the signed repomd first
    except ET.ParseError as exc:
        raise MirrorError("primary does not parse: %s" % exc) from exc
    out = []
    for p in root.findall(NS_COMMON + "package"):
        v = p.find(NS_COMMON + "version")
        cs = p.find(NS_COMMON + "checksum")
        loc = p.find(NS_COMMON + "location")
        size = p.find(NS_COMMON + "size")
        if v is None or cs is None or loc is None or size is None:
            raise MirrorError(
                "primary package %r is missing a field" % _text(p.find(NS_COMMON + "name"))
            )
        out.append(
            Package(
                name=_text(p.find(NS_COMMON + "name")),
                arch=_text(p.find(NS_COMMON + "arch")),
                epoch=v.get("epoch", "0"),
                version=v.get("ver", ""),
                release=v.get("rel", ""),
                href=_safe_relpath(loc.get("href", "")),
                checksum_type=cs.get("type", ""),
                checksum=_text(cs),
                size=int(size.get("package", "0")),
            )
        )
    return out


def _segments(s: str) -> list[str]:
    return re.findall(r"~|\^|[0-9]+|[A-Za-z]+", s)


def rpmvercmp(a: str, b: str) -> int:
    """rpm's version comparison, for picking the newest build `primary` lists."""
    if a == b:
        return 0
    sa, sb = _segments(a), _segments(b)
    while sa or sb:
        x = sa.pop(0) if sa else None
        y = sb.pop(0) if sb else None
        if x == "~" or y == "~":
            if x != y:
                return -1 if x == "~" else 1
            continue
        if x == "^" or y == "^":
            if x is None:
                return -1
            if y is None:
                return 1
            if x != y:
                return 1 if x == "^" else -1
            continue
        if x is None:
            return -1
        if y is None:
            return 1
        if x.isdigit() != y.isdigit():
            return 1 if x.isdigit() else -1
        if x.isdigit():
            xi, yi = int(x), int(y)
            if xi != yi:
                return 1 if xi > yi else -1
        elif x != y:
            return 1 if x > y else -1
    return 0


def _evr_cmp(a: Package, b: Package) -> int:
    ea, eb = int(a.epoch or 0), int(b.epoch or 0)
    if ea != eb:
        return 1 if ea > eb else -1
    return rpmvercmp(a.version, b.version) or rpmvercmp(a.release, b.release)


def newest_evr(packages: Sequence[Package], name: str, arches: Sequence[str] = ARCHES) -> str:
    best: Package | None = None
    for p in packages:
        if p.name == name and p.arch in arches and (best is None or _evr_cmp(p, best) > 0):
            best = p
    if best is None:
        raise MirrorError("primary lists no %s for %s" % (name, "/".join(arches)))
    return best.evr


def pinned_packages(packages: Sequence[Package], evr: str) -> list[Package]:
    """ceph-common and cephadm at evr, refused unless primary lists both."""
    found = [p for p in packages if p.name in PINNED and p.arch in ARCHES and p.evr == evr]
    missing = [n for n in PINNED if not any(p.name == n for p in found)]
    if missing:
        raise MirrorError(
            "OBS primary does not list %s at %s; it is gone upstream and cannot be captured any more"
            % (", ".join(missing), evr)
        )
    return found


def intersect(
    installed: Iterable[tuple[str, str, str]], packages: Sequence[Package]
) -> list[Package]:
    """The primary entries an install took: (name, evr, arch) rows `primary` lists. A Leap OSS package never matches, since this repository does not carry its name at its EVR."""
    by_key = {(p.name, p.evr, p.arch): p for p in packages if p.arch in ARCHES}
    out = {by_key[row] for row in installed if row in by_key}
    return sorted(out, key=lambda p: p.href)


def parse_rpm_qa(stdout: str) -> list[tuple[str, str, str]]:
    """RPM_QA rows as (name, evr, arch)."""
    rows = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        name, epoch, ver, rel, arch = parts
        vr = "%s-%s" % (ver, rel)
        rows.append((name, vr if epoch in ("(none)", "0") else "%s:%s" % (epoch, vr), arch))
    return rows


# --- gpg ------------------------------------------------------------------------


def _run(argv: Sequence[str], **kw: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), text=True, check=False, **kw)  # type: ignore[call-overload,no-any-return]


def key_fingerprints(key: pathlib.Path, home: pathlib.Path, run: RunFn = _run) -> list[str]:
    """The primary-key fingerprints key holds (subkeys excluded)."""
    res = run(
        ["gpg", "--homedir", str(home), "--batch", "--with-colons", "--show-keys", str(key)],
        capture_output=True,
    )
    if res.returncode != 0:
        raise MirrorError("gpg --show-keys %s failed: %s" % (key, (res.stderr or "").strip()))
    fprs: list[str] = []
    last = ""
    for line in (res.stdout or "").splitlines():
        fields = line.split(":")
        if fields[0] in ("pub", "sub"):
            last = fields[0]
        elif fields[0] == "fpr" and last == "pub" and len(fields) > 9:
            fprs.append(fields[9])
            last = ""
    return fprs


def verify_signature(
    data: pathlib.Path, sig: pathlib.Path, key: pathlib.Path, fingerprint: str, run: RunFn = _run
) -> None:
    """gpgv data against sig with key as the only keyring, after asserting key holds exactly fingerprint."""
    with tempfile.TemporaryDirectory(prefix="obs-mirror-gpg-") as tmp:
        home = pathlib.Path(tmp)
        home.chmod(0o700)
        fprs = key_fingerprints(key, home, run)
        if fprs != [fingerprint]:
            raise MirrorError(
                "%s holds %s, expected exactly %s" % (key, fprs or "no key", fingerprint)
            )
        keyring = home / "obs.gpg"
        res = run(
            [
                "gpg",
                "--homedir",
                str(home),
                "--batch",
                "--yes",
                "--dearmor",
                "-o",
                str(keyring),
                str(key),
            ],
            capture_output=True,
        )
        if res.returncode != 0:
            raise MirrorError("gpg --dearmor %s failed: %s" % (key, (res.stderr or "").strip()))
        res = run(
            [
                "gpgv",
                "--homedir",
                str(home),
                "--status-fd",
                "1",
                "--keyring",
                str(keyring),
                str(sig),
                str(data),
            ],
            capture_output=True,
        )
        valid = [
            ln.split()
            for ln in (res.stdout or "").splitlines()
            if ln.startswith("[GNUPG:] VALIDSIG ")
        ]
        if res.returncode != 0 or not valid or valid[0][-1] != fingerprint:
            raise MirrorError(
                "gpgv refused %s (rc=%d): %s"
                % (
                    data.name,
                    res.returncode,
                    ((res.stderr or "") + (res.stdout or "")).strip()[-600:],
                )
            )


# --- the metadata --------------------------------------------------------------


def http_get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as resp:  # noqa: S310 - https URLs built from OBS_ORIGIN
        data: bytes = resp.read()
        return data


@dataclasses.dataclass
class Metadata:
    repomd: Repomd
    files: dict[str, bytes]  # relative path -> bytes: repomd.xml, .asc, .key and every href
    packages: list[Package]

    @property
    def repomd_sha256(self) -> str:
        return hashlib.sha256(self.files["repodata/repomd.xml"]).hexdigest()


def fetch_metadata(
    origin: str,
    key: pathlib.Path,
    fingerprint: str,
    get: GetFn = http_get,
    run: RunFn = _run,
    attempts: int = METADATA_ATTEMPTS,
) -> Metadata:
    """The signed repomd and every file it lists, checksummed. A mismatch (OBS publishing mid-fetch) retries from a fresh repomd, up to attempts times; any other failure raises at once."""
    last: ChecksumMismatchError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return _fetch_metadata_once(origin, key, fingerprint, get, run)
        except ChecksumMismatchError as exc:
            last = exc
            print("::warning::metadata attempt %d/%d: %s" % (attempt, attempts, exc), flush=True)
    raise MirrorError("the OBS metadata never settled after %d attempts: %s" % (attempts, last))


def _fetch_metadata_once(
    origin: str, key: pathlib.Path, fingerprint: str, get: GetFn, run: RunFn
) -> Metadata:
    files: dict[str, bytes] = {}
    for name in ("repomd.xml", "repomd.xml.asc", "repomd.xml.key"):
        files["repodata/" + name] = get(origin + "repodata/" + name)
    with tempfile.TemporaryDirectory(prefix="obs-mirror-md-") as tmp:
        d = pathlib.Path(tmp)
        (d / "repomd.xml").write_bytes(files["repodata/repomd.xml"])
        (d / "repomd.xml.asc").write_bytes(files["repodata/repomd.xml.asc"])
        verify_signature(d / "repomd.xml", d / "repomd.xml.asc", key, fingerprint, run)
    repomd = parse_repomd(files["repodata/repomd.xml"])
    for entry in repomd.data:
        data = get(origin + entry.href)
        verify_checksum(entry.href, data, entry.checksum_type, entry.checksum, entry.size)
        files[entry.href] = data
    primary = repomd.get("primary")
    packages = parse_primary(decompress(primary.href, files[primary.href]))
    return Metadata(repomd=repomd, files=files, packages=packages)


def verify_tree(
    tree: pathlib.Path, key: pathlib.Path, fingerprint: str, run: RunFn = _run
) -> Repomd:
    """A staged or fetched tree: repomd signed by the OBS key, every repodata file matching it."""
    md = tree / "repodata" / "repomd.xml"
    sig = tree / "repodata" / "repomd.xml.asc"
    if not md.is_file() or not sig.is_file():
        raise MirrorError("%s has no repodata/repomd.xml and .asc" % tree)
    verify_signature(md, sig, key, fingerprint, run)
    repomd = parse_repomd(md.read_bytes())
    for entry in repomd.data:
        path = tree / entry.href
        if not path.is_file():
            raise MirrorError("%s lists %s, which the tree lacks" % (md, entry.href))
        verify_checksum(
            entry.href, path.read_bytes(), entry.checksum_type, entry.checksum, entry.size
        )
    return repomd


# --- the containers --------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Verdict:
    name: str
    ok: bool
    detail: str


@dataclasses.dataclass(frozen=True)
class Ctx:
    """What every container needs: the OBS key, renet's repo id and key path, the EVR and the profiles' other names."""

    key: pathlib.Path
    rid: str
    key_path: str
    evr: str
    extras: tuple[str, ...]


class Container:
    """One opensuse/leap:16.0 container, removed on exit."""

    def __init__(
        self,
        label: str,
        mounts: Sequence[tuple[pathlib.Path, str]] = (),
        block_obs: bool = False,
        run: RunFn = _run,
    ) -> None:
        self.name = "obs-mirror-%s-%s" % (label, uuid.uuid4().hex[:8])
        self.run = run
        argv = ["docker", "run", "-d", "--name", self.name]
        if block_obs:
            for host in BLOCKED_HOSTS:
                argv += ["--add-host", "%s:127.0.0.1" % host]
        for src, dst in mounts:
            argv += ["-v", "%s:%s:ro" % (src, dst)]
        self.argv = [*argv, LEAP_IMAGE, "sleep", "infinity"]

    def __enter__(self) -> Self:
        res = self.run(self.argv, capture_output=True)
        if res.returncode != 0:
            raise MirrorError("docker run %s failed: %s" % (LEAP_IMAGE, (res.stderr or "").strip()))
        return self

    def __exit__(self, *_: object) -> None:
        self.run(["docker", "rm", "-f", self.name], capture_output=True)

    def sh(self, script: str) -> subprocess.CompletedProcess[str]:
        print("+ [%s] %s" % (self.name, script), flush=True)
        return self.run(["docker", "exec", self.name, "sh", "-c", script], capture_output=True)


def _tail(res: subprocess.CompletedProcess[str], n: int = 25) -> str:
    return "\n".join(((res.stdout or "") + (res.stderr or "")).strip().splitlines()[-n:])


def _setup_dir(ctx: Ctx, base: str, into: pathlib.Path) -> pathlib.Path:
    into.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ctx.key, into / "obs.key")
    (into / "ceph.repo").write_text(repo_file(ctx.rid, base, ctx.key_path), encoding="utf-8")
    return into


def _setup_script(ctx: Ctx) -> str:
    m, k = SETUP_MOUNT, ctx.key_path
    return (
        f"install -D -m644 {m}/obs.key {k} && rpm --import {k} && "
        f"install -D -m644 {m}/ceph.repo /etc/zypp/repos.d/{ctx.rid}.repo && zypper -n refresh"
    )


def _install_scripts(ctx: Ctx) -> list[str]:
    """renet's two zypper steps: the pinned pair (cephpkg.Install), then the profiles' other names (installArgv)."""
    pinned = " ".join("%s=%s" % (n, ctx.evr) for n in PINNED)
    return [
        "zypper -n install --no-recommends %s" % pinned,
        "zypper -n install --no-recommends %s" % " ".join(ctx.extras),
    ]


RPM_QA = "rpm -qa --qf '%{NAME} %{EPOCH} %{VERSION} %{RELEASE} %{ARCH}\\n'"
RPM_Q_PINNED = "rpm -q --qf '%%{NAME} %%{VERSION}-%%{RELEASE}\\n' %s" % " ".join(PINNED)


def derive_installed(
    ctx: Ctx, scratch: pathlib.Path, run: RunFn = _run
) -> list[tuple[str, str, str]]:
    """Install the package set from the OBS origin in a fresh container and return what rpm -qa holds after."""
    setup = _setup_dir(ctx, OBS_ORIGIN, scratch / "setup-origin")
    with Container("derive", [(setup, SETUP_MOUNT)], run=run) as c:
        for script in [_setup_script(ctx), *_install_scripts(ctx)]:
            res = c.sh(script)
            if res.returncode != 0:
                raise MirrorError(
                    "derivation: `%s` exited %d\n%s" % (script, res.returncode, _tail(res))
                )
        res = c.sh(RPM_QA)
        if res.returncode != 0:
            raise MirrorError("derivation: rpm -qa exited %d" % res.returncode)
        return parse_rpm_qa(res.stdout or "")


def check_rpm_signatures(ctx: Ctx, stage: pathlib.Path, run: RunFn = _run) -> Verdict:
    """`rpm -K` over every staged RPM with a keyring that holds only the OBS key. Measured control: the same call over an empty keyring prints `digests SIGNATURES NOT OK` and exits non-zero."""
    setup = _setup_dir(ctx, MIRROR_URL, stage.parent / "setup-mirror")
    # The Leap image has neither find nor xargs; the tree is two levels deep (x86_64/, noarch/).
    script = (
        "set -e; rpm --dbpath /tmp/obs-only --initdb; rpmkeys --dbpath /tmp/obs-only --import %s/obs.key; "
        "rpmkeys --dbpath /tmp/obs-only -K %s/*/*.rpm"
    ) % (SETUP_MOUNT, MIRROR_MOUNT)
    with Container("rpmk", [(setup, SETUP_MOUNT), (stage, MIRROR_MOUNT)], run=run) as c:
        res = c.sh(script)
    lines = [ln for ln in (res.stdout or "").splitlines() if ln.strip()]
    bad = [ln for ln in lines if not ln.rstrip().endswith("digests signatures OK")]
    count = len(list(stage.rglob("*.rpm")))
    ok = res.returncode == 0 and not bad and len(lines) == count
    detail = "%d/%d: digests signatures OK" % (len(lines), count) if ok else _tail(res)
    return Verdict("rpm -K, OBS key only", ok, detail)


def _installed_evr(stdout: str) -> dict[str, str]:
    return dict(tuple(ln.split(None, 1)) for ln in stdout.splitlines() if len(ln.split()) == 2)  # type: ignore[misc]


def check_positive(ctx: Ctx, stage: pathlib.Path, run: RunFn = _run) -> Verdict:
    name = "POSITIVE: the package set installs from %s" % MIRROR_URL
    setup = _setup_dir(ctx, MIRROR_URL, stage.parent / "setup-mirror")
    with Container(
        "positive", [(setup, SETUP_MOUNT), (stage, MIRROR_MOUNT)], block_obs=True, run=run
    ) as c:
        for script in [_setup_script(ctx), *_install_scripts(ctx)]:
            res = c.sh(script)
            if res.returncode != 0:
                return Verdict(
                    name, False, "`%s` exited %d\n%s" % (script, res.returncode, _tail(res))
                )
        res = c.sh(RPM_Q_PINNED)
    got = _installed_evr(res.stdout or "")
    bad = {n: got.get(n, "not installed") for n in PINNED if got.get(n) != ctx.evr}
    if bad:
        return Verdict(name, False, "installed %s, expected %s" % (bad, ctx.evr))
    return Verdict(name, True, "rpm -q: %s" % ", ".join("%s %s" % (n, got[n]) for n in PINNED))


def check_renet_profile(
    ctx: Ctx, stage: pathlib.Path, renet: pathlib.Path, profile: str, run: RunFn = _run
) -> Verdict:
    """`renet ceph install --profile <profile>` with the mirror named ONLY in the file, OBS unreachable."""
    name = "POSITIVE: renet ceph install --profile %s from the mirror" % profile
    mounts = [(stage, MIRROR_MOUNT), (renet, "/usr/local/bin/renet")]
    with Container("renet-" + profile, mounts, block_obs=True, run=run) as c:
        res = c.sh(
            "mkdir -p %s && echo %s > %s"
            % (os.path.dirname(MIRROR_CONFIG), MIRROR_URL, MIRROR_CONFIG)
        )
        if res.returncode != 0:
            return Verdict(name, False, "writing %s failed\n%s" % (MIRROR_CONFIG, _tail(res)))
        res = c.sh("renet ceph install --profile %s" % profile)
        if res.returncode != 0:
            return Verdict(name, False, "exited %d\n%s" % (res.returncode, _tail(res)))
        repo = c.sh("cat /etc/zypp/repos.d/%s.repo" % ctx.rid)
        if "baseurl=%s" % MIRROR_URL not in (repo.stdout or "").splitlines():
            return Verdict(
                name, False, "renet did not use the mirror:\n%s" % (repo.stdout or "").strip()
            )
        res = c.sh(RPM_Q_PINNED)
    got = _installed_evr(res.stdout or "")
    if got.get("ceph-common") != ctx.evr:
        return Verdict(
            name, False, "ceph-common %s, expected %s" % (got.get("ceph-common"), ctx.evr)
        )
    return Verdict(name, True, "baseurl=%s, ceph-common %s" % (MIRROR_URL, got["ceph-common"]))


def _clone_tree(src: pathlib.Path, dst: pathlib.Path, skip: Sequence[str] = ()) -> None:
    """Hard-link src into dst (a copy across devices), leaving out the relative paths in skip."""
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src).as_posix()
        if path.is_dir() or rel in skip:
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, target)
        except OSError:
            shutil.copyfile(path, target)


def tamper_repomd(data: bytes) -> bytes:
    """One byte of the <revision> changed: the XML still parses and every checksum still matches, so only the signature can refuse it."""
    m = re.search(rb"<revision>(\d)", data)
    if not m:
        raise MirrorError("repomd.xml has no numeric <revision> to tamper with")
    digit = m.group(1)[0] - ord("0")
    return data[: m.start(1)] + bytes([ord("0") + (digit + 1) % 10]) + data[m.end(1) :]


def check_negative_missing(
    ctx: Ctx, stage: pathlib.Path, package: Package, run: RunFn = _run
) -> Verdict:
    name = "NEGATIVE 1: the tree minus %s must fail the install" % package.name
    tree = stage.parent / "negative-missing"
    shutil.rmtree(tree, ignore_errors=True)
    _clone_tree(stage, tree, skip=[package.href])
    setup = _setup_dir(ctx, MIRROR_URL, stage.parent / "setup-mirror")
    try:
        with Container(
            "neg-missing", [(setup, SETUP_MOUNT), (tree, MIRROR_MOUNT)], block_obs=True, run=run
        ) as c:
            res = c.sh(_setup_script(ctx))
            if res.returncode != 0:
                return Verdict(
                    name, False, "the setup failed before the install could\n%s" % _tail(res)
                )
            res = c.sh(_install_scripts(ctx)[0])
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    out = (res.stdout or "") + (res.stderr or "")
    if res.returncode == 0:
        return Verdict(
            name,
            False,
            "the install SUCCEEDED without %s: zypper did not read the mirror" % package.href,
        )
    if package.name not in out:
        return Verdict(
            name,
            False,
            "failed (rc=%d) but not over %s\n%s" % (res.returncode, package.name, _tail(res)),
        )
    line = next(
        (ln for ln in out.splitlines() if package.name in ln and "not found" in ln.lower()), ""
    )
    line = line or next(ln for ln in out.splitlines() if package.name in ln)
    return Verdict(name, True, "rc=%d: %s" % (res.returncode, line.strip()))


def check_negative_tampered(ctx: Ctx, stage: pathlib.Path, run: RunFn = _run) -> Verdict:
    name = "NEGATIVE 2: a one-byte change to repomd.xml must fail zypper refresh"
    tree = stage.parent / "negative-tampered"
    shutil.rmtree(tree, ignore_errors=True)
    _clone_tree(stage, tree, skip=["repodata/repomd.xml"])
    (tree / "repodata" / "repomd.xml").write_bytes(
        tamper_repomd((stage / "repodata" / "repomd.xml").read_bytes())
    )
    setup = _setup_dir(ctx, MIRROR_URL, stage.parent / "setup-mirror")
    try:
        with Container(
            "neg-tamper", [(setup, SETUP_MOUNT), (tree, MIRROR_MOUNT)], block_obs=True, run=run
        ) as c:
            res = c.sh(_setup_script(ctx))
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    out = (res.stdout or "") + (res.stderr or "")
    if res.returncode == 0:
        return Verdict(
            name, False, "zypper refresh ACCEPTED a tampered repomd.xml: repo_gpgcheck is off"
        )
    if "signature" not in out.lower():
        return Verdict(
            name,
            False,
            "failed (rc=%d) but not on the signature\n%s" % (res.returncode, _tail(res)),
        )
    lines = [ln for ln in out.splitlines() if "signature" in ln.lower()]
    line = next((ln for ln in lines if "verification failed" in ln.lower()), lines[0])
    return Verdict(name, True, "rc=%d: %s" % (res.returncode, line.strip()))


def container_checks(
    ctx: Ctx,
    stage: pathlib.Path,
    packages: Sequence[Package],
    renet: pathlib.Path | None,
    pin: str,
    run: RunFn = _run,
) -> list[Verdict]:
    out = [_said(check_rpm_signatures(ctx, stage, run)), _said(check_positive(ctx, stage, run))]
    if renet is None:
        print("::notice::no --renet: the renet-level positive check is skipped", flush=True)
    elif ctx.evr != pin:
        print(
            "::notice::%s is not the tree's pin %s and renet installs only its pin: the renet-level positive check "
            "is skipped" % (ctx.evr, pin),
            flush=True,
        )
    else:
        out += [
            _said(check_renet_profile(ctx, stage, renet, p, run))
            for p in ceph_profiles(_read(CEPH_INSTALL_GO))
        ]
    victim = next((p for p in packages if p.name == NEGATIVE_1_PACKAGE and p.arch in ARCHES), None)
    if victim is None:
        out.append(
            Verdict(
                "NEGATIVE 1",
                False,
                "%s is not in the package set; nothing to take out" % NEGATIVE_1_PACKAGE,
            )
        )
    else:
        out.append(_said(check_negative_missing(ctx, stage, victim, run)))
    out.append(_said(check_negative_tampered(ctx, stage, run)))
    return out


def _said(v: Verdict) -> Verdict:
    """Print a verdict the moment it lands, so a later check that raises cannot hide it."""
    print("[%s] %s: %s" % ("PASS" if v.ok else "FAIL", v.name, v.detail), flush=True)
    return v


# --- capture -------------------------------------------------------------------------


def stage_tree(
    md: Metadata, packages: Sequence[Package], stage: pathlib.Path, get: GetFn = http_get
) -> None:
    shutil.rmtree(stage, ignore_errors=True)
    for rel, data in md.files.items():
        path = stage / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    for p in packages:
        data = get(OBS_ORIGIN + p.href)
        verify_checksum(p.href, data, p.checksum_type, p.checksum, p.size)
        path = stage / p.href
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def write_tar(stage: pathlib.Path, dest: pathlib.Path, mtime: int) -> None:
    """One uncompressed tar whose root is the baseurl, byte-stable for one tree."""
    with tarfile.open(dest, "w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(stage.rglob("*")):
            info = tar.gettarinfo(str(path), arcname=path.relative_to(stage).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = mtime
            info.mode = 0o755 if path.is_dir() else 0o644
            if path.is_dir():
                tar.addfile(info)
            else:
                with open(path, "rb") as fh:
                    tar.addfile(info, fh)


def manifest_annotations(
    md: Metadata, packages: Sequence[Package], captured_at: str
) -> dict[str, str]:
    return {
        ANNOTATION + "repomd-sha256": md.repomd_sha256,
        ANNOTATION + "repomd-revision": md.repomd.revision,
        ANNOTATION + "captured-at": captured_at,
        ANNOTATION + "obs-origin": OBS_ORIGIN,
        ANNOTATION + "packages": ",".join(p.nevra for p in packages),
    }


def push(ref: str, tar: pathlib.Path, notes: dict[str, str], run: RunFn = _run) -> None:
    argv = [
        "oras",
        "push",
        ref,
        "%s:%s" % (tar.name, LAYER_MEDIA_TYPE),
        "--artifact-type",
        ARTIFACT_TYPE,
    ]
    argv += ["--annotation", SOURCE_ANNOTATION]
    for k, v in notes.items():
        argv += ["--annotation", "%s=%s" % (k, v)]
    # oras refuses an absolute layer path, so it runs beside the tar.
    res = run(argv, cwd=str(tar.parent), timeout=PUSH_TIMEOUT_S)
    if res.returncode != 0:
        raise MirrorError("oras push %s exited %d" % (ref, res.returncode))
    if not tag_exists(ref, run):
        raise MirrorError("oras push reported success but %s does not resolve" % ref)


def stored_repomd_sha256(ref: str, run: RunFn = _run) -> str:
    res = run(["oras", "manifest", "fetch", ref], capture_output=True, timeout=120)
    if res.returncode != 0:
        return ""
    try:
        notes = json.loads(res.stdout or "{}").get("annotations", {})
    except ValueError:
        return ""
    return str(notes.get(ANNOTATION + "repomd-sha256", ""))


@dataclasses.dataclass
class CaptureResult:
    ref: str
    pushed: bool
    packages: list[Package] = dataclasses.field(default_factory=list)
    verdicts: list[Verdict] = dataclasses.field(default_factory=list)
    tar: pathlib.Path | None = None


@dataclasses.dataclass
class Deps:
    """The seams: tests swap the network, the registry and the containers."""

    get: GetFn
    run: RunFn
    derive: Callable[[Ctx, pathlib.Path], list[tuple[str, str, str]]]
    checks: Callable[[Ctx, pathlib.Path, list[Package]], list[Verdict]]


def capture(
    evr: str, out: pathlib.Path, stage_only: bool, ctx: Ctx, fingerprint: str, deps: Deps
) -> CaptureResult:
    ref = image_ref(evr)
    if not stage_only and tag_exists(ref, deps.run):
        md = fetch_metadata(OBS_ORIGIN, ctx.key, fingerprint, deps.get, deps.run)
        stored = stored_repomd_sha256(ref, deps.run)
        if stored and stored != md.repomd_sha256:
            print(
                "::warning::%s exists and OBS now publishes a different repomd.xml (%s, captured %s); the first copy "
                "is kept" % (ref, md.repomd_sha256[:16], stored[:16]),
                flush=True,
            )
        print("%s exists; nothing to capture" % ref, flush=True)
        return CaptureResult(ref=ref, pushed=False)
    md = fetch_metadata(OBS_ORIGIN, ctx.key, fingerprint, deps.get, deps.run)
    pinned_packages(md.packages, evr)
    out.mkdir(parents=True, exist_ok=True)
    packages = intersect(deps.derive(ctx, out), md.packages)
    missing = [n for n in PINNED if not any(p.name == n and p.evr == evr for p in packages)]
    if missing:
        raise MirrorError(
            "the derivation installed no %s at %s from this repository" % (", ".join(missing), evr)
        )
    stage = out / "stage"
    stage_tree(md, packages, stage, deps.get)
    verify_tree(stage, ctx.key, fingerprint, deps.run)
    verdicts = deps.checks(ctx, stage, packages)
    result = CaptureResult(ref=ref, pushed=False, packages=packages, verdicts=verdicts)
    failed = [v for v in verdicts if not v.ok]
    if failed:
        for v in failed:
            print("::error::%s: %s" % (v.name, v.detail), flush=True)
        raise MirrorError(
            "%d container check(s) failed: %s" % (len(failed), "; ".join(v.name for v in failed))
        )
    tar = out / LAYER_NAME
    write_tar(stage, tar, int(md.repomd.revision) if md.repomd.revision.isdigit() else 0)
    result.tar = tar
    if stage_only:
        return result
    captured_at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    push(ref, tar, manifest_annotations(md, packages, captured_at), deps.run)
    result.pushed = True
    return result


# --- fetch and serve ------------------------------------------------------------------


def fetch(
    pin: str, dest: pathlib.Path, fingerprint: str, run: RunFn = _run, key: pathlib.Path = KEY_FILE
) -> Repomd:
    """Pull the tag for pin, unpack it into dest and verify it. Every failure raises: CI needs the mirror."""
    ref = image_ref(pin)
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="obs-mirror-pull-") as tmp:
        try:
            res = run(
                ["oras", "pull", ref, "--output", tmp], capture_output=True, timeout=PULL_TIMEOUT_S
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MirrorError("oras pull %s did not complete: %s" % (ref, exc)) from exc
        if res.returncode != 0:
            err = (res.stderr or "").strip()
            if "not found" in err.lower():
                raise MirrorError(
                    "no OBS mirror for the pin %s: dispatch .github/workflows/ci-obs-mirror.yml with evr=%s while OBS "
                    "still serves it, or move the pin to a captured build" % (pin, pin)
                )
            raise MirrorError("oras pull %s failed (rc=%d): %s" % (ref, res.returncode, err))
        tar = pathlib.Path(tmp) / LAYER_NAME
        if not tar.is_file():
            raise MirrorError("%s pulled no %s" % (ref, LAYER_NAME))
        try:
            with tarfile.open(tar) as t:
                t.extractall(dest, filter="data")
        except (tarfile.TarError, OSError) as exc:
            raise MirrorError("%s: %s does not unpack: %s" % (ref, LAYER_NAME, exc)) from exc
    return verify_tree(dest, key, fingerprint, run)


def serve(directory: pathlib.Path, port: int, probe: Callable[[str], bytes] = http_get) -> int:
    """Start a detached http.server on every interface at port over directory and return its pid once it answers."""
    if not (directory / "repodata" / "repomd.xml").is_file():
        raise MirrorError("%s is not a mirror tree (no repodata/repomd.xml)" % directory)
    log_path = directory.parent / ("obs-mirror-serve-%d.log" % port)
    # No --bind: http.server's default is every interface (dual-stack), which the E2E VMs need, since they reach the runner over the fleet bridge at 192.168.111.1.
    argv = [sys.executable, "-m", "http.server", "--directory", str(directory), str(port)]
    with open(log_path, "ab") as log:
        proc = subprocess.Popen(
            argv, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True
        )
    url = "http://127.0.0.1:%d/repodata/repomd.xml" % port
    for _ in range(50):
        if proc.poll() is not None:
            raise MirrorError("http.server exited %s; see %s" % (proc.returncode, log_path))
        try:
            probe(url)
            return proc.pid
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    proc.kill()
    raise MirrorError("http.server never answered %s" % url)


# --- CLI ----------------------------------------------------------------------------------


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def make_ctx(evr: str) -> Ctx:
    go = _read(CEPHPKG_GO)
    names = zypper_names(_read(PKGSET_GO))
    return Ctx(
        key=KEY_FILE,
        rid=repo_id(go),
        key_path=key_path(go),
        evr=evr,
        extras=tuple(n for n in names if n not in PINNED),
    )


def _emit(pairs: dict[str, str]) -> None:
    lines = "".join("%s=%s\n" % (k, v) for k, v in pairs.items())
    target = os.environ.get("GITHUB_OUTPUT", "")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(lines)
    else:
        sys.stdout.write(lines)


def _summary(text: str) -> None:
    target = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text)


def _default_dir(name: str) -> pathlib.Path:
    return pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / name


def _ensure_oras() -> None:
    if shutil.which("oras") is None:
        oras_dir = _default_dir("oras-bin")
        install_oras(oras_dir)
        os.environ["PATH"] = "%s%s%s" % (oras_dir, os.pathsep, os.environ.get("PATH", ""))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m rediacc_ci.infra.obs_mirror",
        description="Capture, fetch and serve the OBS Ceph mirror for openSUSE Leap 16.0.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("upstream")
    p = sub.add_parser("capture")
    p.add_argument("--evr", required=True)
    p.add_argument("--out", type=pathlib.Path, default=None)
    p.add_argument(
        "--stage-only", action="store_true", help="everything but the tag probe and the push"
    )
    p.add_argument(
        "--renet", type=pathlib.Path, default=None, help="renet binary for the renet-level positive"
    )
    p = sub.add_parser("fetch")
    p.add_argument("--pin", required=True)
    p.add_argument("--dest", type=pathlib.Path, required=True)
    p = sub.add_parser("serve")
    p.add_argument("--dir", type=pathlib.Path, required=True)
    p.add_argument("--port", type=int, default=SERVE_PORT)
    return parser


def _cmd_upstream(fingerprint: str) -> int:
    md = fetch_metadata(OBS_ORIGIN, KEY_FILE, fingerprint)
    evr = newest_evr(md.packages, "ceph-common")
    pinned_packages(md.packages, evr)
    pin = read_pin(_read(PIN_FILE))
    print(
        "OBS serves ceph-common/cephadm %s (repomd revision %s); the tree pins %s"
        % (evr, md.repomd.revision, pin)
    )
    if evr != pin:
        print("::notice::OBS serves %s, the tree pins %s" % (evr, pin))
    _emit({"obs_evr": evr, "pin": pin})
    return 0


def _cmd_capture(args: argparse.Namespace, fingerprint: str) -> int:
    out = args.out or _default_dir("obs-mirror-%s" % args.evr)
    if not args.stage_only:
        _ensure_oras()
    renet = args.renet.resolve() if args.renet else None
    if renet is not None and not renet.is_file():
        raise MirrorError("renet binary not found: %s" % renet)
    ctx = make_ctx(args.evr)
    pin = read_pin(_read(PIN_FILE))
    deps = Deps(
        get=http_get,
        run=_run,
        derive=derive_installed,
        checks=lambda c, s, p: container_checks(c, s, p, renet, pin),
    )
    result = capture(args.evr, out, args.stage_only, ctx, fingerprint, deps)
    if not result.packages:
        _summary("- `%s`: already captured\n" % result.ref)
        return 0
    total = sum(p.size for p in result.packages)
    print("package set: %d packages, %d bytes" % (len(result.packages), total))
    for p in result.packages:
        print("  %s %d" % (p.href, p.size))
    for v in result.verdicts:
        print(
            "[%s] %s: %s"
            % ("PASS" if v.ok else "FAIL", v.name, v.detail.splitlines()[0] if v.detail else "")
        )
    tar_size = result.tar.stat().st_size if result.tar else 0
    print(
        "%s %s: %s (%d bytes)"
        % ("pushed" if result.pushed else "staged, not pushed:", result.ref, result.tar, tar_size)
    )
    _summary(
        "- `%s`: %s, %d packages, %d-byte tar, %d/%d checks passed\n"
        % (
            result.ref,
            "pushed" if result.pushed else "staged",
            len(result.packages),
            tar_size,
            sum(v.ok for v in result.verdicts),
            len(result.verdicts),
        )
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        fingerprint = obs_fingerprint(_read(CEPHPKG_GO))
        if args.cmd == "upstream":
            return _cmd_upstream(fingerprint)
        if args.cmd == "capture":
            return _cmd_capture(args, fingerprint)
        if args.cmd == "fetch":
            _ensure_oras()
            repomd = fetch(args.pin, args.dest, fingerprint)
            print(
                "OBS mirror %s (repomd revision %s) at %s"
                % (image_ref(args.pin), repomd.revision, args.dest)
            )
            _emit({"dir": str(args.dest)})
            return 0
        pid = serve(args.dir.resolve(), args.port)
        print("serving %s on every interface, port %d (pid %d)" % (args.dir, args.port, pid))
        _emit({"pid": str(pid)})
        return 0
    except (MirrorError, BakeImageError, OSError, urllib.error.URLError) as exc:
        print("::error::obs_mirror: %s" % exc, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
