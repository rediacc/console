"""Durable, versioned executor artifacts: what the proxy container image is built from (PLAN-proxy-cd-six-targets, Design item 8, box A1).

    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.executor_artifacts stage --version V --bundle-dir D --renet P (--natives-tar T | --node-modules N)
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.executor_artifacts fetch --version V --dest workers/proxy/stage/
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.executor_artifacts stage-local [--dest workers/proxy/stage/]
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.executor_artifacts retain --current V --previous V [--apply]

THE LAYOUT. `executor/v<V>/` in the releases R2 bucket (`RELEASES_BUCKET`) holds five objects: `cli-bundle.cjs` and `package.json` (the `cli-bundle-<sha>` CI artifact, ci-build-docker.yml), `renet-linux-amd64` (the `renet-binaries-<sha>` artifact), `node-natives-linux-x64.tar` (ssh2 and cpu-features at the lockfile versions) and `manifest.json` (each file's sha256 and size, the version and the git sha). The proxy Dockerfile copies the fetched directory, runs `sha256sum -c` against the manifest and builds nothing from source.

WRITE-ONCE. The manifest is the commit marker and is written LAST, so a run that dies part-way leaves no manifest and the version is simply not staged. A stage whose version already has a manifest compares sha256s: all equal skips (a CD retry is a no-op), any unequal refuses and writes nothing, so a version names one set of bytes for ever.

FETCH VERIFIES. Every file is hashed after download and compared with the manifest's sha256 and size. A mismatch refuses, removes the bad file and leaves the destination without a manifest, so a half-verified directory never looks complete.

U3 (the licence key in the renet artifact). `ci-build-renet.yml` builds renet with `ACCOUNT_ED25519_PUBLIC_KEY` from the bws secret of that name, and `build_renet.py` bakes it through `-ldflags`; `cd-deploy-account.yml` and `cd-deploy-worker.yml` read the same single secret name, so the CI artifact carries the production licence public key and edge and stable verify with it. The artifact lives one day (`retention-days: 1`), so `stage` runs in the same CD pipeline that built it. `stage` takes the renet path as an argument, so a renet built in CD with the key bound through bws drops in with no change here.

RETENTION. `select_prune` keeps the newest `KEEP_RELEASES` versions plus the current and previous production versions, whatever their age, and refuses when the current version is unknown (unknown is never prunable).

ENVIRONMENT. `CLOUDFLARE_R2_ENDPOINT` plus the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` the aws CLI reads, as `promote_r2_to_stable` does. Every call goes through `awscli.run`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import TYPE_CHECKING, cast

from rediacc_ci import paths
from rediacc_ci.core import awscli
from rediacc_ci.release.list_edge_releases import semver
from rediacc_ci.release.retention_contract import KEEP_RELEASES
from rediacc_ci.well_known import RELEASES_BUCKET

if TYPE_CHECKING:
    from collections.abc import Sequence

SELF = "executor_artifacts"
BUCKET = RELEASES_BUCKET
PREFIX = "executor/"

BUNDLE = "cli-bundle.cjs"
PACKAGE_JSON = "package.json"
RENET = "renet-linux-amd64"
NATIVES = "node-natives-linux-x64.tar"
MANIFEST = "manifest.json"
FILES = (BUNDLE, PACKAGE_JSON, RENET, NATIVES)

# The native modules the container needs next to the bundle, at the lockfile's versions.
NATIVE_MODULES = ("ssh2", "cpu-features")

LOCAL_VERSION = "0.0.0-local"
DEFAULT_DEST = "workers/proxy/stage"

_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class ArtifactError(Exception):
    """A refusal. The message is printed by `main` and the exit status is 1."""


def key_for(version: str, name: str) -> str:
    return "%sv%s/%s" % (PREFIX, version, name)


def check_version(version: str, *, local: bool = False) -> str:
    if local and version == LOCAL_VERSION:
        return version
    if not _VERSION_RE.match(version):
        raise ArtifactError(
            "%s: version %r is not a plain release version (X.Y.Z)" % (SELF, version)
        )
    return version


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def endpoint() -> str:
    found = os.environ.get("CLOUDFLARE_R2_ENDPOINT", "")
    if not found:
        raise ArtifactError("%s: CLOUDFLARE_R2_ENDPOINT must be set" % SELF)
    return found


# ---- manifest ---------------------------------------------------------------


def build_manifest(
    version: str, git_sha: str, sources: dict[str, pathlib.Path]
) -> dict[str, object]:
    """The manifest of `sources` (name -> local file). Every name in `FILES` must be present."""
    missing = [name for name in FILES if name not in sources]
    if missing:
        raise ArtifactError("%s: missing source file(s): %s" % (SELF, ", ".join(missing)))
    files = {}
    for name in FILES:
        path = sources[name]
        if not path.is_file():
            raise ArtifactError("%s: %s is not a file: %s" % (SELF, name, path))
        files[name] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    return {"version": version, "git_sha": git_sha, "files": files}


def manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


def parse_manifest(text: str, version: str) -> dict[str, dict[str, object]]:
    """The `files` table of a manifest, validated for shape and for naming `version`."""
    try:
        doc = json.loads(text)
        files = doc["files"]
        named = doc["version"]
        doc["git_sha"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ArtifactError(
            "%s: manifest.json of v%s is malformed (%s)" % (SELF, version, exc)
        ) from exc
    if named != version:
        raise ArtifactError(
            "%s: manifest.json names version %r, expected %r" % (SELF, named, version)
        )
    for name in FILES:
        entry = files.get(name) if isinstance(files, dict) else None
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("sha256"), str)
            or not isinstance(entry.get("size"), int)
        ):
            raise ArtifactError(
                "%s: manifest.json of v%s has no valid entry for %s" % (SELF, version, name)
            )
    return files


# ---- aws --------------------------------------------------------------------


def _aws(
    args: list[str], *, capture: bool = True, outfile: str = ""
) -> subprocess.CompletedProcess[bytes]:
    """One `aws s3api` call. `outfile` is get-object's positional output path, kept last."""
    argv = [awscli.AWS, "s3api", *args, "--bucket", BUCKET, "--endpoint-url", endpoint()]
    if outfile:
        argv.append(outfile)
    return awscli.run(
        argv, stdout=subprocess.PIPE if capture else subprocess.DEVNULL, stderr=subprocess.PIPE
    )


def _absent(stderr: str) -> bool:
    return "NoSuchKey" in stderr or "Not Found" in stderr or "(404)" in stderr


def get_object(key: str, dest: pathlib.Path) -> bool:
    """Download `key` to `dest`. False when the key does not exist; any other failure refuses."""
    proc = _aws(["get-object", "--key", key], capture=False, outfile=str(dest))
    if proc.returncode == 0:
        return True
    err = proc.stderr.decode("utf-8", errors="replace")
    if _absent(err):
        return False
    raise ArtifactError(
        "%s: aws get-object %s failed (rc %d): %s" % (SELF, key, proc.returncode, err.strip())
    )


def put_object(key: str, source: pathlib.Path, content_type: str) -> None:
    proc = _aws(
        [
            "put-object",
            "--key",
            key,
            "--body",
            str(source),
            "--content-type",
            content_type,
            "--cache-control",
            "public, max-age=31536000, immutable",
        ],
        capture=False,
    )
    if proc.returncode != 0:
        raise ArtifactError(
            "%s: aws put-object %s failed (rc %d): %s"
            % (SELF, key, proc.returncode, proc.stderr.decode("utf-8", errors="replace").strip())
        )


def list_versions() -> list[str]:
    """Every staged version (a `executor/v<V>/` directory holding a manifest)."""
    proc = _aws(["list-objects-v2", "--prefix", PREFIX, "--output", "json"])
    if proc.returncode != 0:
        raise ArtifactError(
            "%s: aws list-objects-v2 failed (rc %d): %s"
            % (SELF, proc.returncode, proc.stderr.decode("utf-8", errors="replace").strip())
        )
    text = proc.stdout.decode()
    contents = json.loads(text).get("Contents") or [] if text.strip() else []
    found = set()
    for entry in contents:
        match = re.match(
            r"^executor/v([0-9]+\.[0-9]+\.[0-9]+)/%s$" % re.escape(MANIFEST), entry["Key"]
        )
        if match:
            found.add(match.group(1))
    return sorted(found, key=lambda v: semver(v) or (0, 0, 0))


def delete_version(version: str) -> None:
    """Delete one version's objects, manifest FIRST so a half-deleted version never reads as staged."""
    failed: list[str] = []
    for name in (MANIFEST, *FILES):
        proc = _aws(["delete-object", "--key", key_for(version, name)], capture=False)
        if proc.returncode != 0:
            failed.append("%s (rc %d)" % (key_for(version, name), proc.returncode))
    if failed:
        # Every object is attempted, so one failure strands only itself; the manifest is gone first, so a later `retain` no longer lists the version and these keys need a manual delete.
        raise ArtifactError("%s: aws delete-object failed for %s" % (SELF, ", ".join(failed)))


# ---- stage / fetch ----------------------------------------------------------


def stage(version: str, git_sha: str, sources: dict[str, pathlib.Path]) -> str:
    """Write `executor/v<version>/` once. Returns `staged` or `skipped`; refuses when the version exists with other bytes."""
    check_version(version)
    manifest = build_manifest(version, git_sha, sources)
    with tempfile.TemporaryDirectory(prefix="executor-stage-") as tmp:
        existing = pathlib.Path(tmp) / MANIFEST
        if get_object(key_for(version, MANIFEST), existing):
            files = parse_manifest(existing.read_text(), version)
            new_files = cast("dict[str, dict[str, object]]", manifest["files"])
            unequal = [name for name in FILES if files[name]["sha256"] != new_files[name]["sha256"]]
            if unequal:
                raise ArtifactError(
                    "%s: v%s is already staged with different bytes (%s); a staged version is write-once, so cut a new version"
                    % (SELF, version, ", ".join(unequal))
                )
            return "skipped"
        for name in FILES:
            put_object(key_for(version, name), sources[name], "application/octet-stream")
        out = pathlib.Path(tmp) / "manifest.out.json"
        out.write_bytes(manifest_bytes(manifest))
        put_object(key_for(version, MANIFEST), out, "application/json")
    return "staged"


def fetch(version: str, dest: pathlib.Path) -> dict[str, dict[str, object]]:
    """Download and verify `executor/v<version>/` into `dest`. Refuses on any sha256 or size mismatch."""
    check_version(version)
    dest.mkdir(parents=True, exist_ok=True)
    manifest_path = dest / MANIFEST
    manifest_path.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="executor-fetch-") as tmp:
        staged_manifest = pathlib.Path(tmp) / MANIFEST
        if not get_object(key_for(version, MANIFEST), staged_manifest):
            raise ArtifactError(
                "%s: v%s is not staged (no %s)" % (SELF, version, key_for(version, MANIFEST))
            )
        files = parse_manifest(staged_manifest.read_text(), version)
        for name in FILES:
            target = dest / name
            if not get_object(key_for(version, name), target):
                raise ArtifactError(
                    "%s: v%s lists %s but the object is missing" % (SELF, version, name)
                )
            verify_file(target, files[name], version)
        shutil.copyfile(staged_manifest, manifest_path)
    return files


def verify_file(path: pathlib.Path, entry: dict[str, object], version: str) -> None:
    got = sha256_file(path)
    if got != entry["sha256"] or path.stat().st_size != entry["size"]:
        path.unlink(missing_ok=True)
        raise ArtifactError(
            "%s: %s of v%s does not match its manifest (sha256 %s, expected %s)"
            % (SELF, path.name, version, got, entry["sha256"])
        )


# ---- natives, local ---------------------------------------------------------


def locked_version(lockfile: pathlib.Path, package: str) -> str:
    doc = json.loads(lockfile.read_text())
    entry = doc.get("packages", {}).get("node_modules/%s" % package)
    if not entry or "version" not in entry:
        raise ArtifactError("%s: %s is not in %s" % (SELF, package, lockfile))
    return str(entry["version"])


def build_natives_tar(
    node_modules: pathlib.Path, lockfile: pathlib.Path, out: pathlib.Path
) -> pathlib.Path:
    """A tar of `node_modules/{ssh2,cpu-features}` (entries named `node_modules/<pkg>/...`), refused unless each installed version equals the lockfile's.

    Entries are sorted with zeroed owner and mtime, so equal trees give equal bytes.
    """
    with tarfile.open(out, "w") as tar:
        for package in NATIVE_MODULES:
            root = node_modules / package
            manifest = root / "package.json"
            if not manifest.is_file():
                raise ArtifactError(
                    "%s: %s is not installed under %s (run npm ci and npm run install:natives)"
                    % (SELF, package, node_modules)
                )
            installed = json.loads(manifest.read_text()).get("version")
            wanted = locked_version(lockfile, package)
            if installed != wanted:
                raise ArtifactError(
                    "%s: %s is installed at %s but the lockfile pins %s"
                    % (SELF, package, installed, wanted)
                )
            members = sorted(p for p in root.rglob("*") if not p.is_dir() or p.is_symlink())
            for path in members:
                info = tar.gettarinfo(
                    str(path),
                    arcname="node_modules/%s/%s" % (package, path.relative_to(root).as_posix()),
                )
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = 0
                if info.isfile():
                    with path.open("rb") as handle:
                        tar.addfile(info, handle)
                else:
                    tar.addfile(info)
    return out


def git_head() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=paths.repo_root(),
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def stage_local(dest: pathlib.Path, root: pathlib.Path, git_sha: str) -> dict[str, object]:
    """Bench and local runs: the same directory `fetch` produces, from a tree build (no R2)."""
    cli = root / "packages" / "cli"
    sources = {
        BUNDLE: cli / "dist" / "cli-bundle.cjs",
        PACKAGE_JSON: cli / "package.json",
        RENET: root / "private" / "bin" / RENET,
    }
    absent = [str(p) for p in sources.values() if not p.is_file()]
    if absent:
        raise ArtifactError("%s: tree build output missing: %s" % (SELF, ", ".join(absent)))
    dest.mkdir(parents=True, exist_ok=True)
    (dest / MANIFEST).unlink(missing_ok=True)
    for name, source in sources.items():
        shutil.copyfile(source, dest / name)
    build_natives_tar(root / "node_modules", root / "package-lock.json", dest / NATIVES)
    manifest = build_manifest(LOCAL_VERSION, git_sha, {name: dest / name for name in FILES})
    (dest / MANIFEST).write_bytes(manifest_bytes(manifest))
    return manifest


# ---- retention --------------------------------------------------------------


def select_prune(
    versions: Sequence[str], current: str, previous: str, keep: int = KEEP_RELEASES
) -> list[str]:
    """The staged versions that may be deleted: everything outside the newest `keep`, except the current and previous production versions.

    Refuses an empty `current` (unknown is never prunable) and a version that is not X.Y.Z.
    """
    if not current:
        raise ArtifactError(
            "%s: the current production version is unknown, so nothing is prunable" % SELF
        )
    ordered = []
    for version in versions:
        triple = semver(version)
        if triple is None:
            raise ArtifactError("%s: %r is not a plain release version" % (SELF, version))
        ordered.append((triple, version))
    ordered.sort(reverse=True)
    protected = {version for _, version in ordered[: max(keep, 0)]}
    protected.update(v for v in (current, previous) if v)
    return sorted(
        (v for _, v in ordered if v not in protected), key=lambda v: semver(v) or (0, 0, 0)
    )


# ---- CLI --------------------------------------------------------------------


def _sources_from_args(args: argparse.Namespace, scratch: pathlib.Path) -> dict[str, pathlib.Path]:
    bundle = pathlib.Path(args.bundle_dir)
    sources = {
        BUNDLE: bundle / BUNDLE,
        PACKAGE_JSON: bundle / PACKAGE_JSON,
        RENET: pathlib.Path(args.renet),
    }
    if args.natives_tar:
        sources[NATIVES] = pathlib.Path(args.natives_tar)
    elif args.node_modules:
        root = paths.repo_root()
        sources[NATIVES] = build_natives_tar(
            pathlib.Path(args.node_modules), root / "package-lock.json", scratch / NATIVES
        )
    else:
        raise ArtifactError("%s: stage needs --natives-tar or --node-modules" % SELF)
    return sources


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description=__doc__.split("\n", 1)[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    st = sub.add_parser("stage", help="write executor/v<V>/ once")
    st.add_argument("--version", required=True)
    st.add_argument(
        "--bundle-dir",
        required=True,
        help="directory holding cli-bundle.cjs and package.json (the cli-bundle artifact)",
    )
    st.add_argument(
        "--renet", required=True, help="the renet-linux-amd64 binary (the renet-binaries artifact)"
    )
    st.add_argument("--natives-tar")
    st.add_argument("--node-modules")
    st.add_argument("--git-sha", default="")
    fe = sub.add_parser("fetch", help="download and verify executor/v<V>/")
    fe.add_argument("--version", required=True)
    fe.add_argument("--dest", default=DEFAULT_DEST)
    sl = sub.add_parser(
        "stage-local", help="the same directory from a tree build, for bench and local runs"
    )
    sl.add_argument("--dest", default=DEFAULT_DEST)
    sl.add_argument("--git-sha", default="")
    rt = sub.add_parser(
        "retain", help="list (and with --apply delete) the versions retention releases"
    )
    rt.add_argument("--current", required=True)
    rt.add_argument("--previous", default="")
    rt.add_argument("--keep", type=int, default=KEEP_RELEASES)
    rt.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verb == "stage":
            with tempfile.TemporaryDirectory(prefix="executor-natives-") as scratch:
                sources = _sources_from_args(args, pathlib.Path(scratch))
                outcome = stage(args.version, args.git_sha or git_head(), sources)
            print("%s: v%s %s" % (SELF, args.version, outcome))
        elif args.verb == "fetch":
            files = fetch(args.version, pathlib.Path(args.dest))
            print(
                "%s: v%s verified into %s (%d files)" % (SELF, args.version, args.dest, len(files))
            )
        elif args.verb == "stage-local":
            manifest = stage_local(
                pathlib.Path(args.dest), paths.repo_root(), args.git_sha or git_head()
            )
            print("%s: local build staged into %s (%s)" % (SELF, args.dest, manifest["version"]))
        else:
            doomed = select_prune(list_versions(), args.current, args.previous, args.keep)
            for version in doomed:
                print("%s: %s v%s" % (SELF, "deleting" if args.apply else "would delete", version))
                if args.apply:
                    delete_version(version)
            if not doomed:
                print("%s: nothing to prune" % SELF)
    except ArtifactError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
