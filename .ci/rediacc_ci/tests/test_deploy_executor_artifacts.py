"""`rediacc_ci.deploy.executor_artifacts` against a fake `aws` on PATH whose bucket is a directory.

Nothing here reaches R2. The fake models `s3api get-object`, `put-object`, `list-objects-v2` and `delete-object`, and answers a missing key with `NoSuchKey` as R2 does.
"""

from __future__ import annotations

import json
import os
import re
import stat
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.deploy import executor_artifacts as ea

if TYPE_CHECKING:
    import pathlib

FAKE_AWS = r"""#!/usr/bin/env python3
import json, os, pathlib, sys
bucket = pathlib.Path(os.environ["FAKE_BUCKET"])
args = sys.argv[1:]
assert args[0] == "s3api", args
verb = args[1]
def opt(name):
    return args[args.index(name) + 1]
if verb == "get-object":
    src = bucket / opt("--key")
    if not src.is_file():
        sys.stderr.write("An error occurred (NoSuchKey) when calling the GetObject operation: nope\n")
        sys.exit(254)
    pathlib.Path(args[-1]).write_bytes(src.read_bytes())
elif verb == "put-object":
    dst = bucket / opt("--key")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(pathlib.Path(opt("--body")).read_bytes())
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(opt("--key") + "\n")
elif verb == "list-objects-v2":
    prefix = opt("--prefix")
    keys = sorted(str(p.relative_to(bucket)) for p in bucket.rglob("*") if p.is_file())
    print(json.dumps({"Contents": [{"Key": k, "Size": 1} for k in keys if k.startswith(prefix)]}))
elif verb == "delete-object":
    if opt("--key") == os.environ.get("FAKE_FAIL_KEY"):
        sys.exit(1)
    (bucket / opt("--key")).unlink()
else:
    sys.exit(2)
"""


@pytest.fixture
def r2(tmp_path, monkeypatch):
    bucket = tmp_path / "bucket"
    bucket.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "aws"
    fake.write_text(FAKE_AWS)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "puts.log"
    monkeypatch.setenv("PATH", "%s%s%s" % (bin_dir, os.pathsep, os.environ["PATH"]))
    monkeypatch.delenv("AWS_BIN", raising=False)
    monkeypatch.setenv("FAKE_BUCKET", str(bucket))
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("CLOUDFLARE_R2_ENDPOINT", "https://r2.example.invalid")
    return bucket


def make_sources(root: pathlib.Path, tag: str = "a") -> dict[str, pathlib.Path]:
    root.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name in ea.FILES:
        path = root / name
        path.write_bytes(("%s:%s" % (name, tag)).encode())
        sources[name] = path
    return sources


def test_stage_writes_five_objects_and_a_manifest_with_every_field(r2, tmp_path):
    outcome = ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "src"))
    assert outcome == "staged"
    names = sorted(p.name for p in (r2 / "executor" / "v1.4.2").iterdir())
    assert names == sorted([*ea.FILES, ea.MANIFEST])
    manifest = json.loads((r2 / "executor/v1.4.2/manifest.json").read_text())
    assert manifest["version"] == "1.4.2"
    assert manifest["git_sha"] == "deadbeef"
    assert set(manifest["files"]) == set(ea.FILES)
    for name, entry in manifest["files"].items():
        assert entry["sha256"] == ea.sha256_file(tmp_path / "src" / name)
        assert entry["size"] == (tmp_path / "src" / name).stat().st_size


@pytest.mark.usefixtures("r2")
def test_manifest_is_written_last(tmp_path):
    ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "src"))
    puts = (tmp_path / "puts.log").read_text().split()
    assert puts[-1] == "executor/v1.4.2/manifest.json"
    assert len(puts) == 5


@pytest.mark.usefixtures("r2")
def test_second_stage_with_equal_bytes_skips_and_writes_nothing(tmp_path):
    sources = make_sources(tmp_path / "src")
    ea.stage("1.4.2", "deadbeef", sources)
    (tmp_path / "puts.log").unlink()
    assert ea.stage("1.4.2", "cafef00d", sources) == "skipped"
    assert not (tmp_path / "puts.log").exists()


def test_second_stage_with_unequal_bytes_refuses_and_leaves_the_first(r2, tmp_path):
    ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "src"))
    before = (r2 / "executor/v1.4.2/renet-linux-amd64").read_bytes()
    with pytest.raises(ea.ArtifactError, match="write-once"):
        ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "other", tag="b"))
    assert (r2 / "executor/v1.4.2/renet-linux-amd64").read_bytes() == before


@pytest.mark.usefixtures("r2")
def test_stage_refuses_a_non_release_version(tmp_path):
    with pytest.raises(ea.ArtifactError, match="not a plain release version"):
        ea.stage("1.4", "x", make_sources(tmp_path / "src"))


@pytest.mark.usefixtures("r2")
def test_fetch_round_trips_and_verifies(tmp_path):
    sources = make_sources(tmp_path / "src")
    ea.stage("1.4.2", "deadbeef", sources)
    dest = tmp_path / "stage"
    ea.fetch("1.4.2", dest)
    for name in ea.FILES:
        assert (dest / name).read_bytes() == sources[name].read_bytes()
    assert (dest / ea.MANIFEST).is_file()


def test_fetch_with_one_flipped_byte_refuses_and_leaves_no_manifest(r2, tmp_path):
    ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "src"))
    victim = r2 / "executor/v1.4.2/renet-linux-amd64"
    data = bytearray(victim.read_bytes())
    data[0] ^= 0x01
    victim.write_bytes(bytes(data))
    dest = tmp_path / "stage"
    with pytest.raises(ea.ArtifactError, match="does not match its manifest"):
        ea.fetch("1.4.2", dest)
    assert not (dest / ea.MANIFEST).exists()
    assert not (dest / "renet-linux-amd64").exists()


@pytest.mark.usefixtures("r2")
def test_fetch_of_an_unstaged_version_refuses(tmp_path):
    with pytest.raises(ea.ArtifactError, match="not staged"):
        ea.fetch("9.9.9", tmp_path / "stage")


def test_retention_never_selects_current_or_previous_and_keeps_the_newest():
    versions = ["1.0.%d" % n for n in range(10)]
    doomed = ea.select_prune(versions, current="1.0.1", previous="1.0.0", keep=3)
    assert "1.0.1" not in doomed
    assert "1.0.0" not in doomed
    assert doomed == ["1.0.2", "1.0.3", "1.0.4", "1.0.5", "1.0.6"]


def test_retention_orders_by_semver_not_text():
    doomed = ea.select_prune(
        ["1.9.0", "1.10.0", "1.2.0"], current="1.10.0", previous="1.9.0", keep=1
    )
    assert doomed == ["1.2.0"]


def test_retention_refuses_an_unknown_current():
    with pytest.raises(ea.ArtifactError, match="unknown"):
        ea.select_prune(["1.0.0"], current="", previous="")


def test_retain_apply_deletes_only_what_retention_releases(r2, tmp_path):
    for patch in range(4):
        ea.stage(
            "1.0.%d" % patch,
            "sha%d" % patch,
            make_sources(tmp_path / ("s%d" % patch), tag=str(patch)),
        )
    rc = ea.main(["retain", "--current", "1.0.1", "--previous", "1.0.0", "--keep", "1", "--apply"])
    assert rc == 0
    left = sorted(p.name for p in (r2 / "executor").iterdir() if any(p.iterdir()))
    assert left == ["v1.0.0", "v1.0.1", "v1.0.3"]


def test_a_failed_manifest_delete_leaves_every_file_behind_it(r2, tmp_path, monkeypatch):
    ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "src"))
    monkeypatch.setenv("FAKE_FAIL_KEY", ea.key_for("1.4.2", ea.MANIFEST))
    with pytest.raises(ea.ArtifactError, match="manifest|%s" % re.escape(ea.MANIFEST)):
        ea.delete_version("1.4.2")
    for name in (ea.MANIFEST, *ea.FILES):
        assert (r2 / ea.key_for("1.4.2", name)).is_file(), name
    assert ea.list_versions() == ["1.4.2"]


def test_a_failed_file_delete_still_attempts_the_rest_and_names_the_key(r2, tmp_path, monkeypatch):
    ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "src"))
    stuck = ea.key_for("1.4.2", ea.FILES[0])
    monkeypatch.setenv("FAKE_FAIL_KEY", stuck)
    with pytest.raises(ea.ArtifactError, match=re.escape(stuck)):
        ea.delete_version("1.4.2")
    for name in ea.FILES[1:]:
        assert not (r2 / ea.key_for("1.4.2", name)).exists(), name
    assert ea.list_versions() == []


def test_natives_tar_refuses_a_version_the_lockfile_does_not_pin(tmp_path):
    modules = tmp_path / "node_modules"
    for package in ea.NATIVE_MODULES:
        (modules / package).mkdir(parents=True)
        (modules / package / "package.json").write_text(json.dumps({"version": "1.0.0"}))
    lock = tmp_path / "package-lock.json"
    lock.write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/ssh2": {"version": "1.0.0"},
                    "node_modules/cpu-features": {"version": "2.0.0"},
                }
            }
        )
    )
    with pytest.raises(ea.ArtifactError, match=r"lockfile pins 2\.0\.0"):
        ea.build_natives_tar(modules, lock, tmp_path / "n.tar")


def test_natives_tar_is_deterministic(tmp_path):
    modules = tmp_path / "node_modules"
    for package in ea.NATIVE_MODULES:
        (modules / package / "build").mkdir(parents=True)
        (modules / package / "package.json").write_text(json.dumps({"version": "1.0.0"}))
        (modules / package / "build" / "x.node").write_bytes(b"\x7fELF")
    lock = tmp_path / "package-lock.json"
    lock.write_text(
        json.dumps(
            {"packages": {"node_modules/%s" % p: {"version": "1.0.0"} for p in ea.NATIVE_MODULES}}
        )
    )
    one = ea.build_natives_tar(modules, lock, tmp_path / "one.tar")
    two = ea.build_natives_tar(modules, lock, tmp_path / "two.tar")
    assert ea.sha256_file(one) == ea.sha256_file(two)


def test_stage_local_matches_the_fetch_layout(tmp_path):
    root = tmp_path / "tree"
    (root / "packages/cli/dist").mkdir(parents=True)
    (root / "packages/cli/dist/cli-bundle.cjs").write_text("bundle")
    (root / "packages/cli/package.json").write_text("{}")
    (root / "private/bin").mkdir(parents=True)
    (root / "private/bin/renet-linux-amd64").write_bytes(b"renet")
    for package in ea.NATIVE_MODULES:
        (root / "node_modules" / package).mkdir(parents=True)
        (root / "node_modules" / package / "package.json").write_text(
            json.dumps({"version": "1.0.0"})
        )
    (root / "package-lock.json").write_text(
        json.dumps(
            {"packages": {"node_modules/%s" % p: {"version": "1.0.0"} for p in ea.NATIVE_MODULES}}
        )
    )
    dest = tmp_path / "stage"
    manifest = ea.stage_local(dest, root, "abc")
    assert manifest["version"] == ea.LOCAL_VERSION
    assert manifest["git_sha"] == "abc"
    files = ea.parse_manifest((dest / ea.MANIFEST).read_text(), ea.LOCAL_VERSION)
    for name in ea.FILES:
        assert files[name]["sha256"] == ea.sha256_file(dest / name)
