"""`rediacc_ci.deploy.executor_artifacts` against a fake `aws` on PATH whose bucket is a directory.

Nothing here reaches R2. The fake models `s3api get-object`, `put-object`, `list-objects-v2` and `delete-object`, and answers a missing key with `NoSuchKey` as R2 does.
"""

from __future__ import annotations

import base64
import json
import os
import re
import stat
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_proxy, deploy_record
from rediacc_ci.deploy import executor_artifacts as ea
from rediacc_ci.release import renet_key_gate
from rediacc_ci.well_known import RENET_REPO

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
    (bucket / opt("--key")).unlink(missing_ok=True)
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


PRODUCTION_KEY = base64.b64encode(b"p" * 32).decode()
OTHER_KEY = base64.b64encode(b"o" * 32).decode()
RENET_REVISION = "c" * 40


@pytest.fixture
def real_gate(monkeypatch):
    """Runs the real renet gate: the expected key is bound, and the test supplies a built-info blob."""
    monkeypatch.setenv("ACCOUNT_ED25519_PUBLIC_KEY", PRODUCTION_KEY)


@pytest.fixture(autouse=True)
def renet_gate_off(request, monkeypatch):
    """Most tests here move placeholder bytes, so the gate is off unless a test asks for `real_gate`."""
    if "real_gate" not in request.fixturenames:
        monkeypatch.setattr(ea, "check_renet", lambda *_args, **_kwargs: None, raising=False)


def renet_blob(
    version: str = "1.4.2",
    key: str | None = PRODUCTION_KEY,
    revision: str | None = RENET_REVISION,
    tags: str = "",
    modified: bool = False,
) -> bytes:
    """A binary as Go lays one out: its build info, then the end sentinel, then an embedded asset's stamp that must not be read."""
    ldflags = "-s -w -X main.Version=%s" % version
    if key is not None:
        ldflags += " -X github.com/%s/pkg/license/keys.ProductionPublicKey=%s" % (RENET_REPO, key)
    lines = ["path\tgithub.com/%s/cmd/renet" % RENET_REPO, 'build\t-ldflags="%s"' % ldflags]
    if tags:
        lines.append("build\t-tags=%s" % tags)
    if revision is not None:
        lines += [
            "build\tvcs.revision=%s" % revision,
            "build\tvcs.modified=%s" % ("true" if modified else "false"),
        ]
    return (
        b"\x7fELF"
        + ("\n".join(lines) + "\n").encode()
        + bytes.fromhex("f932433186182072008242104116d8f2")
        + b" -X main.Version=9.9.9 vcs.revision=dddddddd"
    )


def git(cwd: pathlib.Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(name, None)
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def make_tree(root: pathlib.Path, renet: bytes = b"renet") -> None:
    """A tree stage_local can read: the bundle, the prebuilt renet and the lockfile-pinned natives."""
    (root / "packages/cli/dist").mkdir(parents=True)
    (root / "packages/cli/dist/cli-bundle.cjs").write_text("bundle")
    (root / "packages/cli/package.json").write_text("{}")
    (root / "private/bin").mkdir(parents=True)
    (root / "private/bin/renet-linux-amd64").write_bytes(renet)
    (root / "private/bin/renet-linux-amd64").chmod(0o755)
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


def checked_out_renet(root: pathlib.Path) -> str:
    """private/renet as a checkout with one commit; its HEAD is what the tree builds."""
    renet = root / "private/renet"
    renet.mkdir(parents=True)
    git(renet, "init", "-q")
    git(renet, "commit", "-q", "--allow-empty", "-m", "renet")
    return git(renet, "rev-parse", "HEAD")


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


def test_branch_label_is_accepted_everywhere_and_other_suffixes_are_not():
    """An unreleased build is staged under an honest branch label (operator 2026-10-27), never a bare release number."""
    label = "2.4.0-branch.c0ffbb26fb69"
    for rx in (ea._VERSION_RE, deploy_proxy.VERSION_RE, deploy_record.VERSION_RE):
        assert rx.match(label)
        assert not rx.match("2.4.0-rc.1")
        assert not rx.match("2.4.0-branch.XYZ")
        assert not rx.match("2.4")
    assert ea.check_version(label) == label


def test_branch_label_hex_length_boundaries():
    for rx in (ea._VERSION_RE, deploy_proxy.VERSION_RE, deploy_record.VERSION_RE):
        assert rx.match("2.4.0-branch." + "a" * 7)
        assert rx.match("2.4.0-branch." + "a" * 40)
        assert not rx.match("2.4.0-branch." + "a" * 6)
        assert not rx.match("2.4.0-branch." + "a" * 41)


def test_list_versions_never_returns_a_branch_label(r2, tmp_path):
    """Retention reads list_versions, so a staged branch label must stay out of it and out of any prune."""
    label = "2.4.0-branch.c0ffbb26fb69"
    ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "a"))
    ea.stage(label, "deadbeef", make_sources(tmp_path / "b"))
    assert any(label in str(p) for p in r2.rglob("*"))
    assert ea.list_versions() == ["1.4.2"]
    assert ea.list_versions(complete_only=True) == ["1.4.2"]


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


def test_a_partial_version_takes_no_keep_slot():
    versions = ["1.0.0", "1.0.1", "1.0.2", "1.0.3"]
    doomed = ea.select_prune(
        versions, current="1.0.3", previous="1.0.2", keep=2, complete=["1.0.0", "1.0.1", "1.0.2"]
    )
    assert doomed == ["1.0.0"]
    assert ea.select_prune(versions, current="1.0.3", previous="1.0.2", keep=2) == [
        "1.0.0",
        "1.0.1",
    ]


def test_a_partial_newer_than_every_complete_version_is_protected_as_in_flight():
    versions = ["1.0.0", "1.0.1", "1.0.2", "1.0.3"]
    doomed = ea.select_prune(
        versions, current="1.0.1", previous="1.0.0", keep=1, complete=["1.0.0", "1.0.1", "1.0.2"]
    )
    assert "1.0.3" not in doomed
    assert doomed == []


def test_with_no_complete_version_only_the_newest_partial_is_protected():
    doomed = ea.select_prune(
        ["1.0.0", "1.0.1", "1.0.2"], current="1.0.9", previous="", keep=2, complete=[]
    )
    assert doomed == ["1.0.0", "1.0.1"]


def test_only_the_newest_of_several_newer_partials_is_protected():
    doomed = ea.select_prune(
        ["1.0.0", "1.0.1", "1.0.2", "1.0.3"],
        current="1.0.0",
        previous="",
        keep=1,
        complete=["1.0.0"],
    )
    assert doomed == ["1.0.1", "1.0.2"]


def test_list_versions_complete_only_skips_a_version_without_a_manifest(r2, tmp_path):
    ea.stage("1.4.2", "deadbeef", make_sources(tmp_path / "src"))
    ea.stage("1.4.3", "deadbeef", make_sources(tmp_path / "src"))
    (r2 / ea.key_for("1.4.3", ea.MANIFEST)).unlink()
    assert ea.list_versions() == ["1.4.2", "1.4.3"]
    assert ea.list_versions(complete_only=True) == ["1.4.2"]


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
    with pytest.raises(ea.ArtifactError, match=re.escape(ea.key_for("1.4.2", ea.MANIFEST))):
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
    assert ea.list_versions() == ["1.4.2"]
    monkeypatch.delenv("FAKE_FAIL_KEY")
    ea.delete_version("1.4.2")
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


def test_a_supplied_natives_tar_is_checked_against_the_lockfile(tmp_path):
    modules = tmp_path / "node_modules"
    for package in ea.NATIVE_MODULES:
        (modules / package).mkdir(parents=True)
        (modules / package / "package.json").write_text(json.dumps({"version": "1.0.0"}))
    good = tmp_path / "lock-good.json"
    good.write_text(
        json.dumps(
            {"packages": {"node_modules/%s" % p: {"version": "1.0.0"} for p in ea.NATIVE_MODULES}}
        )
    )
    tar = ea.build_natives_tar(modules, good, tmp_path / "n.tar")
    ea.verify_natives_tar(tar, good)
    bad = tmp_path / "lock-bad.json"
    bad.write_text(
        json.dumps(
            {"packages": {"node_modules/%s" % p: {"version": "9.9.9"} for p in ea.NATIVE_MODULES}}
        )
    )
    with pytest.raises(ea.ArtifactError, match=r"lockfile pins 9\.9\.9"):
        ea.verify_natives_tar(tar, bad)


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
    make_tree(root)
    dest = tmp_path / "stage"
    manifest = ea.stage_local(dest, root, "abc")
    assert manifest["version"] == ea.LOCAL_VERSION
    assert manifest["git_sha"] == "abc"
    # The staged renet is executed from the stage dir by the proxy e2e, so the exec bit must survive the copy.
    assert (dest / ea.RENET).stat().st_mode & 0o111 == 0o111
    files = ea.parse_manifest((dest / ea.MANIFEST).read_text(), ea.LOCAL_VERSION)
    for name in ea.FILES:
        assert files[name]["sha256"] == ea.sha256_file(dest / name)


# ---- the renet gate ---------------------------------------------------------
# 2026-11-04: a bench image's renet replaced hostinger's. Nothing in staging read the renet it shipped.


@pytest.mark.usefixtures("real_gate")
def test_stage_local_passes_a_renet_built_from_this_tree_with_the_key(tmp_path):
    root = tmp_path / "tree"
    make_tree(root)
    head = checked_out_renet(root)
    (root / "private/bin/renet-linux-amd64").write_bytes(renet_blob(revision=head))
    manifest = ea.stage_local(tmp_path / "stage", root, "abc")
    assert manifest["version"] == ea.LOCAL_VERSION


@pytest.mark.usefixtures("real_gate")
def test_stage_local_refuses_a_renet_from_another_revision_and_stages_nothing(tmp_path):
    # The incident's shape: a prebuilt older than the tree it is staged from.
    root = tmp_path / "tree"
    make_tree(root, renet_blob(revision="a" * 40))
    head = checked_out_renet(root)
    dest = tmp_path / "stage"
    with pytest.raises(ea.ArtifactError, match="stale") as caught:
        ea.stage_local(dest, root, "abc")
    assert "a" * 12 in str(caught.value)
    assert head[:12] in str(caught.value)
    assert not (dest / ea.MANIFEST).exists()
    assert not (dest / ea.RENET).exists()


@pytest.mark.usefixtures("real_gate")
def test_stage_local_compares_with_the_gitlink_when_renet_is_not_checked_out(tmp_path):
    root = tmp_path / "tree"
    make_tree(root, renet_blob(revision="a" * 40))
    git(root, "init", "-q")
    git(root, "update-index", "--add", "--cacheinfo", "160000,%s,private/renet" % ("b" * 40))
    git(root, "commit", "-q", "-m", "tree")
    with pytest.raises(ea.ArtifactError, match="stale"):
        ea.stage_local(tmp_path / "stage", root, "abc")
    (root / "private/bin/renet-linux-amd64").write_bytes(renet_blob(revision="b" * 40))
    ea.stage_local(tmp_path / "stage", root, "abc")


@pytest.mark.usefixtures("real_gate")
def test_stage_local_refuses_a_renet_with_no_vcs_stamp(tmp_path):
    root = tmp_path / "tree"
    make_tree(root, renet_blob(revision=None))
    checked_out_renet(root)
    with pytest.raises(ea.ArtifactError, match=r"no vcs\.revision"):
        ea.stage_local(tmp_path / "stage", root, "abc")


@pytest.mark.usefixtures("real_gate")
def test_stage_local_names_a_build_from_a_modified_tree_and_lets_it_through(tmp_path, capsys):
    root = tmp_path / "tree"
    make_tree(root)
    head = checked_out_renet(root)
    (root / "private/bin/renet-linux-amd64").write_bytes(renet_blob(revision=head, modified=True))
    ea.stage_local(tmp_path / "stage", root, "abc")
    assert "vcs.modified=true" in capsys.readouterr().err


@pytest.mark.usefixtures("real_gate")
@pytest.mark.parametrize(
    ("blob", "reason"),
    [
        (renet_blob(key=OTHER_KEY), "not the production key"),
        (renet_blob(key=None), "no key ldflag"),
        (renet_blob(key=""), "empty key"),
        (renet_blob(tags="nolicense"), "tags=nolicense"),
    ],
)
def test_stage_local_refuses_a_wrongly_keyed_renet(tmp_path, blob, reason):
    root = tmp_path / "tree"
    make_tree(root, blob)
    checked_out_renet(root)
    dest = tmp_path / "stage"
    with pytest.raises(ea.ArtifactError, match=reason):
        ea.stage_local(dest, root, "abc")
    assert not (dest / ea.MANIFEST).exists()


def test_stage_local_refuses_with_no_expected_key(tmp_path, monkeypatch, real_gate):
    del real_gate
    monkeypatch.delenv("ACCOUNT_ED25519_PUBLIC_KEY")
    root = tmp_path / "tree"
    make_tree(root, renet_blob())
    with pytest.raises(ea.ArtifactError, match="ACCOUNT_ED25519_PUBLIC_KEY is not set"):
        ea.stage_local(tmp_path / "stage", root, "abc")


@pytest.mark.usefixtures("real_gate")
def test_stage_local_refuses_bytes_that_are_not_a_renet_build(tmp_path):
    root = tmp_path / "tree"
    make_tree(root, b"not go")
    with pytest.raises(ea.ArtifactError, match="not a renet build"):
        ea.stage_local(tmp_path / "stage", root, "abc")


def test_stage_local_for_the_image_smoke_runs_no_renet_gate(tmp_path, monkeypatch, real_gate):
    # The CI smoke job holds no key and no submodule, and what it stages never leaves the job.
    del real_gate
    monkeypatch.delenv("ACCOUNT_ED25519_PUBLIC_KEY")
    root = tmp_path / "tree"
    make_tree(root, b"not go")
    manifest = ea.stage_local(tmp_path / "stage", root, "abc", image_smoke_only=True)
    assert manifest["version"] == ea.LOCAL_VERSION


def test_a_bare_stage_local_is_gated_and_the_smoke_flag_is_spelled_out(tmp_path, monkeypatch):
    seen = {}

    def fake(_dest, _root, _sha, *, image_smoke_only=False):
        seen["smoke"] = image_smoke_only
        return {"version": ea.LOCAL_VERSION}

    monkeypatch.setattr(ea, "stage_local", fake)
    assert ea.main(["stage-local", "--dest", str(tmp_path), "--git-sha", "x"]) == 0
    assert seen["smoke"] is False
    assert (
        ea.main(["stage-local", "--image-smoke-only", "--dest", str(tmp_path), "--git-sha", "x"])
        == 0
    )
    assert seen["smoke"] is True


def staged_with_renet(r2: pathlib.Path, tmp_path: pathlib.Path, blob: bytes) -> dict[str, object]:
    """v1.4.2 in the bucket holding `blob` as its renet, written past `stage`'s own version check."""
    sources = make_sources(tmp_path / "src")
    sources[ea.RENET].write_bytes(blob)
    manifest = ea.build_manifest("1.4.2", "deadbeef", sources)
    prefix = r2 / "executor" / "v1.4.2"
    prefix.mkdir(parents=True)
    for name in ea.FILES:
        (prefix / name).write_bytes(sources[name].read_bytes())
    (prefix / ea.MANIFEST).write_bytes(ea.manifest_bytes(manifest))
    return manifest


@pytest.mark.usefixtures("real_gate")
def test_fetch_passes_a_keyed_renet_of_the_named_version(r2, tmp_path):
    staged_with_renet(r2, tmp_path, renet_blob(version="1.4.2"))
    dest = tmp_path / "stage"
    ea.fetch("1.4.2", dest)
    assert (dest / ea.MANIFEST).is_file()


@pytest.mark.usefixtures("real_gate")
def test_fetch_refuses_a_renet_of_another_version_and_leaves_no_manifest(r2, tmp_path):
    staged_with_renet(r2, tmp_path, renet_blob(version="1.4.1"))
    dest = tmp_path / "stage"
    with pytest.raises(ea.ArtifactError, match="stale") as caught:
        ea.fetch("1.4.2", dest)
    assert "1.4.1" in str(caught.value)
    assert not (dest / ea.MANIFEST).exists()
    assert not (dest / ea.RENET).exists()


@pytest.mark.usefixtures("real_gate")
def test_fetch_refuses_a_wrongly_keyed_renet_and_leaves_no_manifest(r2, tmp_path):
    staged_with_renet(r2, tmp_path, renet_blob(version="1.4.2", key=OTHER_KEY))
    dest = tmp_path / "stage"
    with pytest.raises(ea.ArtifactError, match="not the production key"):
        ea.fetch("1.4.2", dest)
    assert not (dest / ea.MANIFEST).exists()
    assert not (dest / ea.RENET).exists()


def test_a_refusal_never_carries_the_key(r2, tmp_path, real_gate):
    del real_gate
    staged_with_renet(r2, tmp_path, renet_blob(version="1.4.2", key=OTHER_KEY))
    with pytest.raises(ea.ArtifactError) as caught:
        ea.fetch("1.4.2", tmp_path / "stage")
    assert OTHER_KEY not in str(caught.value)
    assert PRODUCTION_KEY not in str(caught.value)


def test_stage_refuses_a_renet_of_another_version_before_any_write(
    r2, tmp_path, monkeypatch, real_gate
):
    # stage's CD job binds no key, so it checks the version; fetch checks both before an image is built.
    del real_gate
    monkeypatch.delenv("ACCOUNT_ED25519_PUBLIC_KEY")
    sources = make_sources(tmp_path / "src")
    sources[ea.RENET].write_bytes(renet_blob(version="1.4.1"))
    with pytest.raises(ea.ArtifactError, match="stale"):
        ea.stage("1.4.2", "deadbeef", sources)
    assert not list(r2.rglob("*.json"))
    assert not (r2 / "executor").exists()


def test_stage_refuses_a_wrongly_keyed_renet_when_a_key_is_bound(r2, tmp_path, real_gate):
    # With the expected key bound, a wrongly keyed renet must not reach the write-once objects.
    del real_gate
    sources = make_sources(tmp_path / "src")
    sources[ea.RENET].write_bytes(renet_blob(version="1.4.2", key=OTHER_KEY))
    with pytest.raises(ea.ArtifactError, match="refused"):
        ea.stage("1.4.2", "deadbeef", sources)
    assert not (r2 / "executor").exists()


def test_the_build_info_reader_finds_a_real_go_binary():
    # A real binary when the tree has one. Its build info is what `go version -m` prints.
    binary = paths.repo_root() / "private" / "bin" / ea.RENET
    if not binary.is_file():
        pytest.skip("no prebuilt renet in this tree")
    text = ea.renet_build_text(binary)
    assert renet_key_gate.parse_build_info(text).version
    assert re.search(r"vcs\.revision=[0-9a-f]{40}", text)
