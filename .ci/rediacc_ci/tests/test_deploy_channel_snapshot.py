"""Channel snapshots (PLAN-plan-per-pr-loop R2 follow-up, #51ea3682): the release writes `snapshots/v<ver>/`, the promote reads the SELECTED version's copy.

Three writers and readers, each driven against a recording fake (nothing reaches R2 or Cloudflare):
  * `promote_r2_to_stable` with an OLDER selection: metadata and pointers from the snapshot, cli binaries from `cli/v<ver>/`, packages from `<dir>/edge/`, verified before any write (`r2_promote_fake`);
  * `upload_repos_to_r2` and `upload_to_r2` with `SNAPSHOT_VERSION`: the snapshot keys are written with the bytes the channel write used, the marker last;
  * `list_channel_snapshots`: only versions with a `.complete` marker count.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import typing

from rediacc_ci.deploy import channel_snapshot, r2_promote
from rediacc_ci.deploy import promote_r2_to_stable as promote
from rediacc_ci.release import list_channel_snapshots
from rediacc_ci.tests import r2_promote_fake as fake
from rediacc_ci.tests import test_deploy_upload_repos_to_r2 as repos_t
from rediacc_ci.tests import test_deploy_upload_to_r2 as cli_t
from rediacc_ci.well_known import RELEASES_BUCKET, RELEASES_ORIGIN

HOME = os.environ.get("HOME", "/tmp")
B = RELEASES_BUCKET + "/"
MODULE = "rediacc_ci.deploy.promote_r2_to_stable"

PROMOTE_ENV = {
    "AWS_ACCESS_KEY_ID": "akid-fixture",
    "AWS_SECRET_ACCESS_KEY": "secret-fixture",
    "AWS_DEFAULT_REGION": "auto",
    "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
    "EDGE_VERSION": "1.2.2",
    "CLOUDFLARE_ZONE_ID": "zone-fixture",
    "CLOUDFLARE_API_TOKEN": "tok-fixture",
}

# The newest edge is v1.2.3; the selected (older) release is v1.2.2. The channel trees carry v1.2.3's metadata, the snapshot v1.2.2's.
EDGE = {
    "cli/edge/rdc-linux-x64": "rdc 1.2.3 bytes\n",
    "cli/edge/manifest.json": '{"version":"1.2.3"}\n',
    "cli/edge/latest.json": '{"version":"1.2.3"}\n',
    "cli/edge/install.sh": '#!/bin/sh\n# 1.2.3\n: "${REDIACC_CHANNEL:-edge}"\n',
    "cli/edge/install.ps1": '# 1.2.3\n$c = if ($e) { "edge" } else { "edge" }\n',
    "cli/v1.2.3/rdc-linux-x64": "rdc 1.2.3 bytes\n",
    "cli/v1.2.2/rdc-linux-x64": "rdc 1.2.2 bytes\n",
    "cli/v1.2.2/.released": '{"version":"1.2.2"}\n',
    "apt/edge/pool/rdc_1.2.3.deb": "deb 1.2.3\n",
    "apt/edge/pool/rdc_1.2.2.deb": "deb 1.2.2\n",
    "apt/edge/InRelease": "inrelease 1.2.3\n",
    "apt/edge/Packages.gz": "packages 1.2.3\n",
    "rpm/edge/rdc-1.2.3.rpm": "rpm 1.2.3\n",
    "rpm/edge/rdc-1.2.2.rpm": "rpm 1.2.2\n",
    "rpm/edge/repodata/aaa-primary.xml.gz": "primary 1.2.3\n",
    "rpm/edge/repodata/bbb-primary.xml.gz": "primary 1.2.2\n",
    "rpm/edge/repodata/repomd.xml": "repomd 1.2.3\n",
    "rpm/edge/rediacc.repo": "[rediacc]\nbaseurl=" + RELEASES_ORIGIN + "/rpm/edge/\n",
    "apk/edge/rdc-1.2.3.apk": "apk 1.2.3\n",
    "apk/edge/rdc-1.2.2.apk": "apk 1.2.2\n",
    "apk/edge/APKINDEX.tar.gz": "apkindex 1.2.3\n",
    "archlinux/edge/rdc-1.2.3.pkg.tar.zst": "pkg 1.2.3\n",
    "archlinux/edge/rdc-1.2.2.pkg.tar.zst": "pkg 1.2.2\n",
    "archlinux/edge/rediacc.db.tar.gz": "db 1.2.3\n",
    "archlinux/edge/rediacc.conf": "[rediacc]\nServer = " + RELEASES_ORIGIN + "/archlinux/edge/\n",
    # The previous stable, promoted AFTER v1.2.2 was released: the same sizes as the snapshot's files and the same LastModified, which the skip rule would read as "already there".
    "apt/stable/InRelease": "inrelease 1.2.1\n",
    "cli/stable/rdc-linux-x64": "rdc 1.2.1 bytes\n",
}

SNAP_META = {
    "cli/manifest.json": '{"version":"1.2.2"}\n',
    "cli/latest.json": '{"version":"1.2.2"}\n',
    "cli/install.sh": '#!/bin/sh\n# 1.2.2\n: "${REDIACC_CHANNEL:-edge}"\n',
    "cli/install.ps1": '# 1.2.2\n$c = if ($e) { "edge" } else { "edge" }\n',
    "apt/InRelease": "inrelease 1.2.2\n",
    "apt/Packages.gz": "packages 1.2.2\n",
    "rpm/repodata/bbb-primary.xml.gz": "primary 1.2.2\n",
    "rpm/repodata/repomd.xml": "repomd 1.2.2\n",
    "rpm/rediacc.repo": "[rediacc]\nbaseurl=" + RELEASES_ORIGIN + "/rpm/edge/\n",
    "apk/APKINDEX.tar.gz": "apkindex 1.2.2\n",
    "archlinux/rediacc.db.tar.gz": "db 1.2.2\n",
    "archlinux/rediacc.conf": "[rediacc]\nServer = " + RELEASES_ORIGIN + "/archlinux/edge/\n",
}

SNAP_PACKAGES = {
    "apt/pool/rdc_1.2.2.deb": len("deb 1.2.2\n"),
    "rpm/rdc-1.2.2.rpm": len("rpm 1.2.2\n"),
    "apk/rdc-1.2.2.apk": len("apk 1.2.2\n"),
    "archlinux/rdc-1.2.2.pkg.tar.zst": len("pkg 1.2.2\n"),
}


def snapshot_bucket(
    meta: dict[str, str] | None = None,
    packages: dict[str, int] | None = None,
    *,
    marker: bool = True,
) -> dict[str, str]:
    meta = SNAP_META if meta is None else meta
    objects = dict(EDGE)
    objects.update({"snapshots/v1.2.2/" + rel: body for rel, body in meta.items()})
    if marker:
        objects["snapshots/v1.2.2/.complete"] = channel_snapshot.marker_body(
            "1.2.2", list(meta), SNAP_PACKAGES if packages is None else packages
        )
    return objects


def promote_run(tmp_path: pathlib.Path, objects: dict[str, str]):
    root = tmp_path / "fx"
    fake.make_bucket(root, objects)
    proc, records = fake.run_port(root, MODULE, PROMOTE_ENV, HOME)
    return root, proc, records


def writes(records) -> list[dict[str, typing.Any]]:
    return [r for r in records if r.get("op") in ("COPY", "PUT")]


# --------------------------------------------------------------------------- The promote reads the selected version's snapshot ---------------------------------------------------------------------------


def test_an_older_selection_promotes_from_its_snapshot(tmp_path) -> None:
    root, proc, records = promote_run(tmp_path, snapshot_bucket())
    assert proc.returncode == 0, proc.stderr
    stable = fake.bucket_keys(root, B)
    # Metadata: the v1.2.2 snapshot's bytes, never the newest edge's.
    assert stable[B + "cli/stable/manifest.json"] == '{"version":"1.2.2"}\n'
    assert stable[B + "cli/stable/latest.json"] == '{"version":"1.2.2"}\n'
    assert stable[B + "apt/stable/InRelease"] == "inrelease 1.2.2\n"
    assert stable[B + "apt/stable/Packages.gz"] == "packages 1.2.2\n"
    assert stable[B + "rpm/stable/repodata/repomd.xml"] == "repomd 1.2.2\n"
    assert stable[B + "apk/stable/APKINDEX.tar.gz"] == "apkindex 1.2.2\n"
    assert stable[B + "archlinux/stable/rediacc.db.tar.gz"] == "db 1.2.2\n"
    # The cli channel binary: v1.2.2's, from the immutable versioned prefix, and its sentinel stays behind.
    assert stable[B + "cli/stable/rdc-linux-x64"] == "rdc 1.2.2 bytes\n"
    assert B + "cli/stable/.released" not in stable
    # The pointers: the snapshot's, stamped for stable.
    assert "# 1.2.2" in stable[B + "cli/stable/install.sh"]
    assert "REDIACC_CHANNEL:-stable" in stable[B + "cli/stable/install.sh"]
    assert "/rpm/stable/" in stable[B + "rpm/stable/rediacc.repo"]
    # Packages: from the edge trees, the version the metadata hashes among them.
    assert stable[B + "apt/stable/pool/rdc_1.2.2.deb"] == "deb 1.2.2\n"
    srcs = {r["src"] for r in fake.ops(records, "COPY")}
    assert not any(s.startswith(B + "cli/edge/") for s in srcs), srcs
    assert B + "apt/edge/InRelease" not in srcs
    assert B + "snapshots/v1.2.2/apt/InRelease" in srcs
    # Nothing is fetched to the runner but the marker and the snapshot's pointers.
    gets = sorted(r["key"] for r in fake.ops(records, "GET"))
    assert gets == sorted(
        B + "snapshots/v1.2.2/" + rel
        for rel in (
            ".complete",
            "cli/install.sh",
            "cli/install.ps1",
            "rpm/rediacc.repo",
            "archlinux/rediacc.conf",
        )
    )
    assert "Channel snapshot: snapshots/v1.2.2/" in proc.stdout
    assert "R2 promotion complete: edge v1.2.2 -> stable" in proc.stdout


def _snapshot_stable_problems(root) -> list[str]:
    """After promoting v1.2.2 from its snapshot, each stable package tree holds exactly v1.2.2's packages (the marker's) plus the snapshot's metadata for that tree: no v1.2.3 package edge still carries, and nothing older."""
    keys = fake.bucket_keys(root, B)
    problems = []
    for dir_name in r2_promote.PACKAGE_TREES:
        head = B + dir_name + "/stable/"
        held = {k[len(head) :] for k in keys if k.startswith(head)}
        want = {k[len(dir_name) + 1 :] for k in SNAP_PACKAGES if k.startswith(dir_name + "/")}
        want |= {k[len(dir_name) + 1 :] for k in SNAP_META if k.startswith(dir_name + "/")}
        if held != want:
            problems.append(
                "%s: extra %s missing %s" % (head, sorted(held - want), sorted(want - held))
            )
    return problems


def test_a_snapshot_promote_leaves_stable_holding_only_the_selected_version(tmp_path) -> None:
    assert promote.SNAPSHOT_BYTES_ARE_THE_MARKERS_PACKAGES is True
    objects = {**snapshot_bucket(), "rpm/stable/repodata/old-primary.xml.gz": "primary 1.2.0\n"}
    root, proc, _records = promote_run(tmp_path, objects)
    assert proc.returncode == 0, proc.stderr
    assert _snapshot_stable_problems(root) == []


def test_mutation_control_a_snapshot_promote_copying_every_edge_package_is_caught(tmp_path) -> None:
    """PLANT: drop `Sources.only`, so phase 1 copies every package `<dir>/edge/` holds (v1.2.3's too) and the prune keeps them as promoted."""
    planted = fake.plant(tmp_path, "            and (only is None or obj.rel in only)\n", "")
    root = tmp_path / "fx"
    fake.make_bucket(root, snapshot_bucket())
    proc, _records = fake.run_port(root, MODULE, PROMOTE_ENV, HOME, plant=planted)
    assert proc.returncode == 0, proc.stderr
    assert len(_snapshot_stable_problems(root)) == 4


def test_snapshot_metadata_is_copied_even_when_stable_looks_unchanged(tmp_path) -> None:
    """THE SKIP RULE WOULD KEEP THE WRONG VERSION: stable's `InRelease` and `rdc-linux-x64` have the snapshot sources' sizes and LastModified, so `unchanged` reads them as already promoted. A snapshot promote copies them anyway."""
    _root, proc, records = promote_run(tmp_path, snapshot_bucket())
    assert proc.returncode == 0, proc.stderr
    copied = {r["key"] for r in fake.ops(records, "COPY")}
    assert B + "apt/stable/InRelease" in copied
    assert B + "cli/stable/rdc-linux-x64" in copied


def test_a_snapshot_without_its_marker_is_refused_before_any_write(tmp_path) -> None:
    _root, proc, records = promote_run(tmp_path, snapshot_bucket(marker=False))
    assert proc.returncode == 1
    assert "no .complete marker: a partial snapshot, not promoted" in proc.stderr
    assert writes(records) == []
    assert fake.curl_calls(records) == 0


def test_a_package_retention_pruned_is_refused_before_any_write(tmp_path) -> None:
    objects = snapshot_bucket()
    del objects["apt/edge/pool/rdc_1.2.2.deb"]
    _root, proc, records = promote_run(tmp_path, objects)
    assert proc.returncode == 1
    assert "pruned by retention" in proc.stderr
    assert "pool/rdc_1.2.2.deb" in proc.stderr
    assert writes(records) == []


def test_a_marker_naming_an_absent_metadata_key_is_refused(tmp_path) -> None:
    objects = snapshot_bucket()
    del objects["snapshots/v1.2.2/apt/InRelease"]
    _root, proc, records = promote_run(tmp_path, objects)
    assert proc.returncode == 1
    assert "apt/InRelease" in proc.stderr
    assert writes(records) == []


def test_the_newest_edge_without_a_snapshot_still_promotes_from_edge(tmp_path) -> None:
    """A release cut before snapshots existed: the live edge trees, as before."""
    objects = {k: v for k, v in EDGE.items() if "/edge/" in k}
    root = tmp_path / "fx"
    fake.make_bucket(root, objects)
    proc, records = fake.run_port(root, MODULE, {**PROMOTE_ENV, "EDGE_VERSION": "1.2.3"}, HOME)
    assert proc.returncode == 0, proc.stderr
    stable = fake.bucket_keys(root, B)
    assert stable[B + "apt/stable/InRelease"] == "inrelease 1.2.3\n"
    assert stable[B + "cli/stable/manifest.json"] == '{"version":"1.2.3"}\n'
    assert all(r["src"].startswith(B) and "/edge/" in r["src"] for r in fake.ops(records, "COPY"))
    assert "Channel snapshot" not in proc.stdout


# --------------------------------------------------------------------------- The release writes the snapshot ---------------------------------------------------------------------------

# A fake bucket for `upload_repos_to_r2`: `s3 sync` (with aws's filter rule) and `s3 cp` from the runner into a directory tree, `s3api list-objects-v2` over it, every call one JSON line.
REPOS_FAKE_AWS = r"""#!/usr/bin/python3
import datetime, fnmatch, json, os, shutil, sys

argv = sys.argv[1:]
root = os.environ["FAKE_S3_ROOT"]
log = os.environ["FAKE_CALL_LOG"]


def emit(record):
    with open(log, "a") as fh:
        fh.write(json.dumps(record) + "\n")


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


emit({"argv": argv})
if argv[:2] == ["s3api", "list-objects-v2"]:
    bucket, prefix = opt("--bucket"), opt("--prefix")
    base = os.path.join(root, bucket)
    contents = []
    for dirpath, _d, files in os.walk(base):
        for name in files:
            full = os.path.join(dirpath, name)
            key = os.path.relpath(full, base)
            if key.startswith(prefix):
                contents.append({"Key": key, "Size": os.path.getsize(full),
                                 "LastModified": "2026-10-02T00:00:00.000Z"})
    contents.sort(key=lambda c: c["Key"])
    print(json.dumps({"Contents": contents} if contents else {}))
    sys.exit(0)
if argv[:2] == ["s3", "sync"]:
    src, dst = argv[2], argv[3][5:]
    filters = []
    i = 4
    while i < len(argv):
        if argv[i] in ("--exclude", "--include"):
            filters.append((argv[i], argv[i + 1]))
            i += 2
        elif argv[i] in ("--cache-control", "--endpoint-url"):
            i += 2
        else:
            i += 1
    for dirpath, _d, files in os.walk(src):
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, src)
            keep = True
            for kind, pattern in filters:
                if fnmatch.fnmatchcase(rel, pattern):
                    keep = kind == "--include"
            if keep:
                target = os.path.join(root, dst, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copyfile(full, target)
                emit({"op": "PUT", "key": dst + rel, "content": open(full).read()})
    sys.exit(0)
if argv[:2] == ["s3", "cp"]:
    src, dst = argv[2], argv[3][5:]
    target = os.path.join(root, dst)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(src, target)
    emit({"op": "PUT", "key": dst, "content": open(src).read()})
    sys.exit(0)
sys.stderr.write("fake aws: unmodelled %r\n" % argv)
sys.exit(2)
"""

REPOS_TREE = {
    "dist/repos/apt/pool/main/rdc_1.2.3_amd64.deb": "deb bytes\n",
    "dist/repos/apt/gpg.key": "key\n",
    "dist/repos/apt/dists/stable/InRelease": "signed inrelease\n",
    "dist/repos/apt/dists/stable/Release.gpg": "detached signature\n",
    "dist/repos/apt/dists/stable/main/binary-amd64/Packages.gz": "packages\n",
    "dist/repos/rpm/rdc-1.2.3-1.x86_64.rpm": "rpm bytes\n",
    "dist/repos/rpm/repodata/abc-primary.xml.gz": "primary\n",
    "dist/repos/rpm/repodata/repomd.xml": "repomd\n",
    "dist/repos/rpm/repodata/repomd.xml.asc": "repomd signature\n",
    "dist/repos/rpm/rediacc.repo": "[rediacc]\n",
    "dist/pages/install.sh": '#!/bin/sh\n: "${REDIACC_CHANNEL:-stable}"\n',
    "dist/pages/install.ps1": '$c = if ($e) { "edge" } else { "stable" }\n',
}

CLI_PART = {
    "snapshots/v1.2.3/cli/manifest.json": '{"version":"1.2.3"}\n',
    "snapshots/v1.2.3/cli/latest.json": '{"version":"1.2.3"}\n',
}


def repos_run(tmp_path: pathlib.Path, *, seed: dict[str, str] | None = None, **extra: str):
    root = repos_t.fixture(tmp_path, REPOS_TREE)
    s3 = tmp_path / "s3"
    for key, body in (CLI_PART if seed is None else seed).items():
        target = s3 / RELEASES_BUCKET / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    env: dict[str, typing.Any] = {"FAKE_S3_ROOT": str(s3), **extra}
    proc, log = repos_t._run(root, "new", aws_body=REPOS_FAKE_AWS, **env)
    records = [json.loads(line) for line in log.splitlines() if line.startswith("{")]
    return root, s3, proc, records


def puts(records) -> list[tuple[str, str]]:
    return [(r["key"], r["content"]) for r in records if r.get("op") == "PUT"]


def test_the_release_writes_the_snapshot_with_the_channel_bytes_and_the_marker_last(
    tmp_path,
) -> None:
    _root, _s3, proc, records = repos_run(tmp_path, SNAPSHOT_VERSION="1.2.3")
    assert proc.returncode == 0, proc.stderr
    written = puts(records)
    keys = [k for k, _c in written]
    channel = {k[len(B + "apt/edge/") :]: c for k, c in written if k.startswith(B + "apt/edge/")}
    snap = {
        k[len(B + "snapshots/v1.2.3/apt/") :]: c
        for k, c in written
        if k.startswith(B + "snapshots/v1.2.3/apt/")
    }
    # The metadata, byte for byte what the channel received; never a package, never the static key.
    assert snap == {rel: channel[rel] for rel in channel if rel.startswith("dists/")}
    assert B + "snapshots/v1.2.3/rpm/repodata/repomd.xml.asc" in keys
    assert B + "snapshots/v1.2.3/rpm/rediacc.repo" in keys
    assert not any(k.endswith((".deb", ".rpm", "gpg.key")) and "/snapshots/" in k for k in keys)
    # The install scripts: the same stamped bytes as the channel copy.
    by_key = dict(written)
    for name in ("install.sh", "install.ps1"):
        assert by_key[B + "snapshots/v1.2.3/cli/" + name] == by_key[B + "cli/edge/" + name]
    assert "REDIACC_CHANNEL:-edge" in by_key[B + "snapshots/v1.2.3/cli/install.sh"]
    # The marker last, naming every metadata key and every package with its size.
    assert keys[-1] == B + "snapshots/v1.2.3/.complete"
    marker = json.loads(by_key[B + "snapshots/v1.2.3/.complete"])
    assert marker["version"] == "1.2.3"
    assert "apt/dists/stable/InRelease" in marker["metadata"]
    assert "cli/manifest.json" in marker["metadata"]
    assert "cli/install.sh" in marker["metadata"]
    assert marker["packages"]["apt/pool/main/rdc_1.2.3_amd64.deb"] == len("deb bytes\n")
    assert "apt/gpg.key" in marker["packages"]
    assert "Channel snapshot sealed: snapshots/v1.2.3/" in proc.stdout


def test_without_snapshot_version_no_snapshot_is_written(tmp_path) -> None:
    _root, _s3, proc, records = repos_run(tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert not any("snapshots/" in k for k, _c in puts(records))
    # No seal: the snapshot of a version is never listed. The prune's read of `snapshots/` (other versions' markers, `upload_repos_to_r2`'s KEEP SET) is not a snapshot write.
    sealed = [
        r["argv"]
        for r in records
        if "list-objects-v2" in r.get("argv", [])
        and r["argv"][r["argv"].index("--prefix") + 1].startswith("snapshots/v")
    ]
    assert sealed == []


def test_a_snapshot_missing_its_cli_part_gets_no_marker(tmp_path) -> None:
    _root, _s3, proc, records = repos_run(tmp_path, seed={}, SNAPSHOT_VERSION="1.2.3")
    assert proc.returncode == 1
    assert "is incomplete, so no .complete marker is written" in proc.stderr
    assert "cli/manifest.json" in proc.stderr
    assert not any(k.endswith(".complete") for k, _c in puts(records))


def test_a_snapshot_is_refused_on_a_non_edge_channel(tmp_path) -> None:
    _root, _s3, proc, records = repos_run(tmp_path, SNAPSHOT_VERSION="1.2.3", CHANNEL="stable")
    assert proc.returncode == 1
    assert "only an edge upload writes" in proc.stderr
    assert puts(records) == []


def test_the_cli_upload_writes_its_part_with_the_same_bytes(tmp_path) -> None:
    root = cli_t.fixture(tmp_path)
    proc, calls = cli_t._run(root, "new", SNAPSHOT_VERSION="1.2.3")
    assert proc.returncode == 0, proc.stderr
    manifest = str(root / "dist" / "cli" / "manifest.json")
    edge_cp = cli_t._cp(manifest, "cli/edge/manifest.json", "no-cache")
    snap_cp = cli_t._cp(manifest, "snapshots/v1.2.3/cli/manifest.json", "no-cache")
    assert edge_cp in calls
    assert snap_cp in calls
    assert calls.index(snap_cp) > calls.index(edge_cp)
    latest = "\t".join(["aws", "s3", "cp", "-", "s3://%ssnapshots/v1.2.3/cli/latest.json" % B])
    at = calls.index(latest)
    assert calls[at:].split("\n")[1] == 'STDIN<<<{"version":"1.2.3"}'


def test_the_cli_upload_refuses_a_snapshot_of_another_version(tmp_path) -> None:
    root = cli_t.fixture(tmp_path)
    proc, calls = cli_t._run(root, "new", SNAPSHOT_VERSION="1.2.2")
    assert proc.returncode == 1
    assert "only an edge upload of that same version writes" in proc.stderr
    assert calls == ""


def test_pruning_a_version_prunes_its_snapshot(tmp_path) -> None:
    tracker = "[%s]" % ",".join('"9.9.%d"' % index for index in range(22))
    root = cli_t.fixture(tmp_path)
    proc, calls = cli_t._run(
        root,
        "new",
        SNAPSHOT_VERSION="1.2.3",
        FAKE_TRACKER=tracker,
        FAKE_STABLE_MANIFEST='{"version":"9.9.21"}',
    )
    assert proc.returncode == 0, proc.stderr
    for ver in ("9.9.19", "9.9.20", "9.9.21"):
        assert "aws\ts3\trm\ts3://%ssnapshots/v%s/\t--recursive" % (B, ver) in calls


# --------------------------------------------------------------------------- The listing check_soak_period reads ---------------------------------------------------------------------------


def _listing(*keys: str) -> str:
    return json.dumps(
        {
            "Contents": [
                {"Key": k, "Size": 1, "LastModified": "2026-10-02T00:00:00.000Z"} for k in keys
            ]
        }
    )


def test_only_a_marked_snapshot_is_listed() -> None:
    text = _listing(
        "snapshots/v1.4.1/.complete",
        "snapshots/v1.4.1/apt/InRelease",
        "snapshots/v1.4.2/apt/InRelease",
        "snapshots/v1.10.0/.complete",
        "snapshots/vbogus/.complete",
        "snapshots/v1.4.3/cli/.complete",
    )
    assert list_channel_snapshots.versions(text) == ["1.10.0", "1.4.1"]
    assert list_channel_snapshots.versions("") == []


def test_a_failed_listing_is_a_failure_not_an_empty_answer(tmp_path) -> None:
    stub = tmp_path / "bin"
    stub.mkdir()
    aws = stub / "aws"
    aws.write_text(
        "#!/bin/sh\necho 'An error occurred (AccessDenied)' >&2\nexit 254\n", encoding="utf-8"
    )
    aws.chmod(0o755)
    out = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.release.list_channel_snapshots"],
        env={
            "PATH": "%s:%s" % (stub, os.environ.get("PATH", "")),
            "PYTHONPATH": str(pathlib.Path(promote.__file__).resolve().parents[2]),
            "GITHUB_OUTPUT": str(out),
            "CLOUDFLARE_R2_ENDPOINT": "https://r2.example.invalid",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "not evidence that no snapshot exists" in proc.stderr
    assert not out.exists()
