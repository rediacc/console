"""The per-version snapshot of an edge release's channel metadata (PLAN-plan-per-pr-loop R2 follow-up, worklist #51ea3682).

WHY IT EXISTS. `check_soak_period` selects the NEWEST edge release that has soaked, which with a release on every merge is usually OLDER than the newest edge. The channel trees `<dir>/edge/` carry the signed metadata (apt `Release`/`InRelease`/`Release.gpg` and `Packages*`, rpm `repodata/` with `repomd.xml.asc`, `APKINDEX.tar.gz`, the pacman db, `cli/edge/manifest.json` and `latest.json`, the install scripts and repo configs) of the newest edge ONLY, because every release overwrites them. Promoting an older version from those trees would ship the newest edge's packages under the older version's name.
So every edge release also writes its metadata to an immutable per-version prefix, and the promote reads the SELECTED version's copy.

THE LAYOUT: `snapshots/v<ver>/<dir>/<rel>`, where `<dir>/<rel>` is the object's place in the channel tree (`apt/dists/stable/InRelease` is the snapshot of `apt/edge/dists/stable/InRelease`). One prefix per version, named by the version the same way `cli/v<ver>/` is, and kept OUT of `cli/v<ver>/` on purpose: `release-state-validator.sh`'s `rsv_binary_count` counts every object under `cli/v<ver>/` but the `.released` sentinel, so a snapshot there would make a sealed release whose binaries were scrubbed read as healthy (the v1.1.16 `sealed-but-empty` class). Nothing that enumerates `<dir>/` (the
channel and `pr-N` sweeps, `delete_r2_channel`, 8d's `cli/v*` sweep) looks under `snapshots/`.

THE BYTES ARE THE SAME BYTES. The writers (`upload_to_r2`, `upload_repos_to_r2`) upload the same local file (or the same stamped temporary, or the same string) they have just uploaded to `<dir>/edge/`, in the same run; nothing is re-signed, re-generated or re-serialized. The promote copies a snapshot object server-side, exactly as it copies an edge object, and checks it exactly as it checks an edge tree.

WHAT IS METADATA is the promote's own definition: a file `promote_r2_to_stable.META_EXCLUDES` keeps OUT of phase 1. One definition, so the snapshot cannot drift from what the promote reads from it. `cli/manifest.json` and `cli/latest.json` (written by `upload_to_r2`) and the two install scripts (written by `upload_repos_to_r2`) complete it.

THE MARKER `snapshots/v<ver>/.complete` IS WRITTEN LAST, by `upload_repos_to_r2` (the later of the two upload steps), and only after a listing shows the cli part. It is the snapshot's `.released`: a prefix without it is a partial snapshot and is never promoted. Its body is JSON naming the version, every metadata key of the snapshot, and every PACKAGE file the metadata hashes with its size, so the promote can refuse before any write when retention (`upload_repos_to_r2`'s prune keeps only the current build and the packages of promotion candidates' snapshots) has
already removed a package the snapshot's metadata names.

WRITTEN ON EVERY UPLOAD OF THE VERSION, NOT ONCE. A rerun of the same version re-syncs its packages into `<dir>/edge/`, and the snapshot's `Packages`/`repomd.xml` hash those very files, so freezing the snapshot at the first write (or at the `.released` seal, as `write_once_guard` freezes `cli/v<ver>/`) would leave it naming bytes the channel no longer holds. The write-once property is across versions: only version `<ver>`'s own release ever writes `snapshots/v<ver>/`.

RETENTION follows `cli/versions.json`: when `upload_to_r2` prunes `cli/v<ver>/` it prunes `snapshots/v<ver>/` too.
"""

from __future__ import annotations

import json

from rediacc_ci.deploy import r2_promote

SNAPSHOT_ROOT = "snapshots"
MARKER = ".complete"

# The env var both writers read. Set (to the release version) only on an edge upload; `cd-stage.yml` sets it.
VERSION_ENV = "SNAPSHOT_VERSION"

# The keys the cli part must hold before the marker may be written.
CLI_REQUIRED = ("cli/manifest.json", "cli/latest.json")

# `release-state-validator.sh`'s RSV_SENTINEL_KEY: never promoted from `cli/v<ver>/`.
SENTINEL = ".released"


class SnapshotError(Exception):
    """A snapshot that is absent, partial or names bytes the bucket no longer holds. The message is the reason."""


def prefix(version: str) -> str:
    """`snapshots/v<ver>/`."""
    return "%s/v%s/" % (SNAPSHOT_ROOT, version)


def tree(version: str, dir_name: str) -> str:
    """`snapshots/v<ver>/<dir>/`, the snapshot of `<dir>/edge/`."""
    return "%s%s/" % (prefix(version), dir_name)


def marker_key(version: str) -> str:
    return prefix(version) + MARKER


def is_metadata(rel: str, excludes: tuple[str, ...]) -> bool:
    """True when the promote's phase 1 (`excludes`, `promote_r2_to_stable.META_EXCLUDES`) keeps `rel` out, i.e. a later phase or the pointer step reads it."""
    return not r2_promote.keep(rel, excludes)


def include_filters(excludes: tuple[str, ...]) -> tuple[str, ...]:
    """The aws-cli filter tail selecting exactly what `is_metadata` accepts: `--exclude '*'`, then every pattern of `excludes` as an `--include`. Last match wins in both, so the two agree on every key."""
    out: list[str] = ["--exclude", "*"]
    for i in range(0, len(excludes) - 1, 2):
        out += ["--include", excludes[i + 1]]
    return tuple(out)


def marker_body(version: str, metadata: list[str], packages: dict[str, int]) -> str:
    """The marker's JSON. `metadata` are snapshot-relative keys (`apt/dists/stable/InRelease`); `packages` maps channel-relative package keys (`apt/pool/...deb`) to their sizes."""
    return (
        json.dumps(
            {
                "version": version,
                "metadata": sorted(metadata),
                "packages": dict(sorted(packages.items())),
            },
            indent=2,
        )
        + "\n"
    )


def parse_marker(text: str, version: str) -> tuple[list[str], dict[str, int]]:
    """The marker's `(metadata, packages)`. Raises SnapshotError on anything that is not a marker for `version`."""
    try:
        body = json.loads(text)
    except ValueError as exc:
        raise SnapshotError("%s is not JSON (%s)" % (marker_key(version), exc)) from exc
    if not isinstance(body, dict) or body.get("version") != version:
        raise SnapshotError(
            "%s names version %r, not %r"
            % (
                marker_key(version),
                body.get("version") if isinstance(body, dict) else None,
                version,
            )
        )
    metadata = body.get("metadata")
    packages = body.get("packages")
    if not isinstance(metadata, list) or not all(isinstance(k, str) for k in metadata):
        raise SnapshotError("%s has no metadata list" % marker_key(version))
    if not isinstance(packages, dict) or not all(
        isinstance(k, str) and isinstance(v, int) for k, v in packages.items()
    ):
        raise SnapshotError("%s has no package map" % marker_key(version))
    return list(metadata), dict(packages)


def sources(version: str, dir_name: str) -> r2_promote.Sources:
    """Where a snapshot promote of `dir_name` reads. The metadata is the snapshot. The bytes are `<dir>/edge/`, whose package names carry the version, except for `cli`, whose channel binaries (`cli/edge/rdc-*`) are overwritten by every release: those come from the immutable `cli/v<ver>/`, which holds the same names, and are always copied."""
    if dir_name == "cli":
        return r2_promote.Sources(
            bytes_prefix="cli/v%s/" % version,
            metadata_prefix=tree(version, dir_name),
            ignore=frozenset({SENTINEL}),
            copy_bytes_always=True,
        )
    return r2_promote.Sources(
        bytes_prefix=r2_promote.tree(dir_name, "edge"), metadata_prefix=tree(version, dir_name)
    )
