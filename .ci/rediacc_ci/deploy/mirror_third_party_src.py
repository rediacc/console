#!/usr/bin/env python3
"""Mirror the exact-version source of every third-party binary renet embeds to R2, write-once.

    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.mirror_third_party_src [--dry-run] [--lock PATH] [--dockerfile PATH] [--dpkg-manifest PATH]

(PLAN-release-credits-compliance.md, M1.) `private/renet/embed-assets.lock.json` is the inventory; the written offer in `rdc credits` promises each component's source at `https://releases.rediacc.com/third-party-src/<name>-<ver>.tar.gz`, and this module makes the promise true.

WHAT IT UPLOADS, all under `third-party-src/` in the `releases` bucket:

  * each component's source archive (`upstreamSourceUrl`), under the basename of the component's mirror URL (`mirrorUrl`, or `plannedMirrorUrl` until the lockfile rename lands).
  * for the binaries Rediacc compiles (CRIU, rsync), the build recipe: the Dockerfile's builder stages for that component, extracted verbatim, as `<name>-<ver>-build.txt`.
  * for the static rsync, the source packages of every statically linked library, at the exact versions the builder stage installed. The stage records them in a `dpkg-query` manifest (`--dpkg-manifest`, one `<binary-package>\\t<version>\\t<source-package>\\t<source-version>` line per package); each source package is fetched with `apt-get source --download-only` and its files are uploaded under `<name>-<ver>-libsrc/`. Without the manifest this part is skipped with a warning.

THE REFUSALS, each BEFORE any upload that could be wrong:

  * A component with no recorded sha256 (`sourceSha256`, or the tarball `source.sha256` rsync already carries) is refused: nothing is mirrored whose bytes are not pinned.
  * A download whose sha256 differs from the recorded one is refused, and every download is checked before the first upload of the run.
  * An object that already exists is never overwritten: with the same sha256 (kept in the object's `sha256` metadata) it is skipped, with a different one or with none the run fails. Every HEAD is answered before the first write.

`--dry-run` downloads and verifies, then prints what it would upload and makes no `aws` call.

THE LIVE STEP needs `CLOUDFLARE_R2_ENDPOINT`, `CLOUDFLARE_R2_ACCESS_KEY_ID` and `CLOUDFLARE_R2_SECRET_ACCESS_KEY` (the `r2-artifacts` profile), `curl`, network access to each upstream, and for the static libraries an apt source index (`apt-get source`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

from rediacc_ci import log, paths
from rediacc_ci.core import awscli, common
from rediacc_ci.well_known import RELEASES_BUCKET

PREFIX = "third-party-src/"
LOCK_REL = "private/renet/embed-assets.lock.json"
DOCKERFILE_REL = "private/renet/Dockerfile"

# Components Rediacc compiles itself, and the Dockerfile stage-name prefixes whose recipe conveys them.
RECIPE_STAGES = {"criu": ("criu-",), "rsync": ("rsync-builder-",)}
# The one component that links static libraries whose sources travel with its binary.
STATIC_LIB_COMPONENT = "rsync"

_BANNER = re.compile(r"^# =+\s*$")
_FROM_AS = re.compile(r"^FROM\s+\S+\s+AS\s+(\S+)", re.IGNORECASE | re.MULTILINE)


class MirrorError(Exception):
    """A refusal; the message is the whole report."""


@dataclass
class Item:
    key: str
    path: pathlib.Path
    sha256: str
    origin: str


@dataclass
class Plan:
    items: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, dest: pathlib.Path) -> None:
    """Download `url` to `dest` with curl. The one network seam of the module; tests replace it."""
    proc = subprocess.run(
        ["curl", "-fsSL", "--retry", "3", "-o", str(dest), url],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise MirrorError(
            "download %s failed (curl rc %d): %s" % (url, proc.returncode, proc.stderr.strip())
        )


def fetch_debian_source(source: str, version: str, dest_dir: pathlib.Path) -> list[pathlib.Path]:
    """`apt-get source --download-only <source>=<version>` into `dest_dir`; the files it left. The second network seam."""
    proc = subprocess.run(
        ["apt-get", "source", "--download-only", "%s=%s" % (source, version)],
        cwd=dest_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise MirrorError(
            "apt-get source %s=%s failed: %s" % (source, version, proc.stderr.strip())
        )
    files = sorted(p for p in dest_dir.iterdir() if p.is_file())
    if not files:
        raise MirrorError("apt-get source %s=%s produced no files" % (source, version))
    return files


def mirror_key(component: dict) -> str:
    url = component.get("mirrorUrl") or component.get("plannedMirrorUrl") or ""
    name = url.rsplit("/", 1)[-1]
    if not name:
        raise MirrorError("%s has no mirrorUrl" % component.get("name", "?"))
    return PREFIX + name


def expected_sha(component: dict) -> str:
    sha = component.get("sourceSha256")
    if not sha and (component.get("source") or {}).get("kind") == "tarball":
        sha = component["source"].get("sha256")
    if not sha:
        raise MirrorError(
            "%s %s records no sourceSha256 in the lockfile: nothing is mirrored whose bytes are not pinned"
            % (component.get("name", "?"), component.get("version", "?"))
        )
    return str(sha).lower()


def extract_recipe(dockerfile_text: str, prefixes: tuple[str, ...]) -> str:
    """The Dockerfile blocks (banner to next banner) whose stage name starts with a prefix, verbatim."""
    lines = dockerfile_text.splitlines(keepends=True)
    starts = [
        i
        for i, line in enumerate(lines)
        if _BANNER.match(line) and i + 1 < len(lines) and lines[i + 1].startswith("# Stage")
    ]
    blocks = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        body = "".join(lines[start:end])
        match = _FROM_AS.search(body)
        if match and match.group(1).startswith(prefixes):
            blocks.append(body)
    if not blocks:
        raise MirrorError("no Dockerfile stage starts with %s" % ", ".join(prefixes))
    return "".join(blocks)


def parse_dpkg_manifest(text: str) -> list[tuple[str, str]]:
    """Distinct (source-package, source-version) pairs from the manifest lines."""
    pairs: dict[tuple[str, str], None] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        cols = raw.split("\t")
        if len(cols) != 4 or not all(c.strip() for c in cols):
            raise MirrorError("malformed dpkg manifest line: %r" % raw)
        pairs[(cols[2].strip(), cols[3].strip())] = None
    return list(pairs)


def build_plan(
    lock: dict,
    dockerfile_text: str,
    manifest_text: str | None,
    workdir: pathlib.Path,
) -> Plan:
    """Download and verify everything; no upload happens here, so a bad download stops the run first."""
    plan = Plan()
    seen_keys: set[str] = set()
    for cid, component in lock["components"].items():
        want = expected_sha(component)
        key = mirror_key(component)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        name = key.rsplit("/", 1)[-1]
        dest = workdir / ("src-%s-%s" % (cid, name))
        url = component["upstreamSourceUrl"]
        fetch(url, dest)
        got = sha256_file(dest)
        if got != want:
            raise MirrorError(
                "%s: sha256 of %s is %s, the lockfile records %s" % (cid, url, got, want)
            )
        plan.items.append(Item(key, dest, got, url))

        stem = name.removesuffix(".tar.gz")
        if cid in RECIPE_STAGES:
            recipe = workdir / ("recipe-%s.txt" % cid)
            recipe.write_text(extract_recipe(dockerfile_text, RECIPE_STAGES[cid]), encoding="utf-8")
            plan.items.append(
                Item("%s%s-build.txt" % (PREFIX, stem), recipe, sha256_file(recipe), DOCKERFILE_REL)
            )
        if cid == STATIC_LIB_COMPONENT:
            if manifest_text is None:
                plan.warnings.append(
                    "no --dpkg-manifest: the static-library source packages of %s are NOT mirrored"
                    % cid
                )
                continue
            for source, version in parse_dpkg_manifest(manifest_text):
                sub = workdir / ("libsrc-%s-%s" % (source, version.replace(":", "_")))
                sub.mkdir()
                for file in fetch_debian_source(source, version, sub):
                    plan.items.append(
                        Item(
                            "%s%s-libsrc/%s" % (PREFIX, stem, file.name),
                            file,
                            sha256_file(file),
                            "%s=%s" % (source, version),
                        )
                    )
    return plan


def _aws(args: list[str], endpoint: str) -> subprocess.CompletedProcess[str]:
    return awscli.run(
        [awscli.AWS, *args, "--endpoint-url", endpoint], capture_output=True, text=True
    )


def remote_sha(key: str, endpoint: str) -> str | bool | None:
    """The `sha256` metadata of an existing object, `False` when it exists without one, `None` when absent."""
    proc = _aws(["s3api", "head-object", "--bucket", RELEASES_BUCKET, "--key", key], endpoint)
    if proc.returncode != 0:
        detail = (proc.stderr or "") + (proc.stdout or "")
        if "404" in detail or "Not Found" in detail or "NoSuchKey" in detail:
            return None
        raise MirrorError("HEAD %s failed (rc %d): %s" % (key, proc.returncode, detail.strip()))
    try:
        meta = json.loads(proc.stdout or "{}").get("Metadata") or {}
    except json.JSONDecodeError:
        meta = {}
    return meta.get("sha256") or False


def upload(plan: Plan, endpoint: str, dry_run: bool) -> tuple[int, int]:
    """Write-once upload: every HEAD is answered before the first write. Returns (uploaded, skipped)."""
    todo: list[Item] = []
    skipped = 0
    for item in plan.items:
        if dry_run:
            log.info("would upload %s (sha256 %s, from %s)" % (item.key, item.sha256, item.origin))
            todo.append(item)
            continue
        have = remote_sha(item.key, endpoint)
        if have is None:
            todo.append(item)
        elif have == item.sha256:
            log.info("skip %s: already mirrored with the same sha256" % item.key)
            skipped += 1
        elif have is False:
            raise MirrorError(
                "%s exists without a recorded sha256; write-once, refusing to overwrite" % item.key
            )
        else:
            raise MirrorError(
                "%s exists with sha256 %s, this run has %s; write-once, refusing to overwrite"
                % (item.key, have, item.sha256)
            )
    if dry_run:
        return len(todo), skipped
    for item in todo:
        proc = _aws(
            [
                "s3",
                "cp",
                str(item.path),
                "s3://%s/%s" % (RELEASES_BUCKET, item.key),
                "--metadata",
                "sha256=%s" % item.sha256,
                "--only-show-errors",
            ],
            endpoint,
        )
        if proc.returncode != 0:
            raise MirrorError(
                "upload %s failed (rc %d): %s"
                % (item.key, proc.returncode, (proc.stderr or "").strip())
            )
        log.info("uploaded %s" % item.key)
    return len(todo), skipped


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="mirror_third_party_src")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--lock", default=None)
    parser.add_argument("--dockerfile", default=None)
    parser.add_argument("--dpkg-manifest", default=None)
    args = parser.parse_args(argv)
    root = paths.repo_root()

    try:
        endpoint = ""
        if not args.dry_run:
            awscli.require()
            endpoint = common.require_var("CLOUDFLARE_R2_ENDPOINT")
            os.environ["AWS_ACCESS_KEY_ID"] = common.require_var("CLOUDFLARE_R2_ACCESS_KEY_ID")
            os.environ["AWS_SECRET_ACCESS_KEY"] = common.require_var(
                "CLOUDFLARE_R2_SECRET_ACCESS_KEY"
            )
        lock = json.loads(pathlib.Path(args.lock or root / LOCK_REL).read_text(encoding="utf-8"))
        dockerfile = pathlib.Path(args.dockerfile or root / DOCKERFILE_REL).read_text(
            encoding="utf-8"
        )
        manifest = (
            pathlib.Path(args.dpkg_manifest).read_text(encoding="utf-8")
            if args.dpkg_manifest
            else None
        )
        with tempfile.TemporaryDirectory(prefix="mirror-third-party-src-") as tmp:
            plan = build_plan(lock, dockerfile, manifest, pathlib.Path(tmp))
            for warning in plan.warnings:
                log.warn(warning)
            uploaded, skipped = upload(plan, endpoint, args.dry_run)
    except common.RefusalError as refusal:
        refusal.report()
        return refusal.code
    except MirrorError as err:
        log.error(str(err))
        return 1
    log.info(
        "%s %d object(s), skipped %d"
        % ("would upload" if args.dry_run else "uploaded", uploaded, skipped)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
