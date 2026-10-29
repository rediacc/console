"""`renet_stamp_key` moves when renet's HEAD moves over an unchanged tree.

A rebase-merge replays renet's commits under new SHAs with byte-identical trees. bin/renet stamps `vcs.revision`, and `npm run vm:check` refuses a binary whose revision is not the checkout (renet-build-mismatch). On 2026-10-23 the stamp held only the tree fingerprint, so `./rdc.sh --version` found it current and never rebuilt, and vm:check refused on every run (c32bb4884efa built, 0a89e786caef checked out).
"""

import pathlib
import subprocess

from rediacc_ci.core import local_common, renet_flavor


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_two_commits_with_one_tree_share_the_fingerprint_but_not_the_key(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "main.go").write_text("package main\n")
    _git(tmp_path, "add", "main.go")
    _git(tmp_path, "commit", "-q", "-m", "one")
    first_head = _git(tmp_path, "rev-parse", "HEAD")
    first_fp = local_common.git_tree_fingerprint(str(tmp_path), ["."])
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "the same tree under a new commit")
    second_head = _git(tmp_path, "rev-parse", "HEAD")
    second_fp = local_common.git_tree_fingerprint(str(tmp_path), ["."])

    # The precondition of the defect: the fingerprint cannot tell the two commits apart.
    assert first_head != second_head
    assert first_fp is not None
    assert first_fp == second_fp

    first = local_common.renet_stamp_key(first_fp, first_head, "nolicense", "")
    second = local_common.renet_stamp_key(second_fp, second_head, "nolicense", "")
    assert first != second


def test_the_key_still_moves_with_source_license_and_key():
    base = local_common.renet_stamp_key("src", "abc", "nolicense", "")
    assert local_common.renet_stamp_key("src2", "abc", "nolicense", "") != base
    assert local_common.renet_stamp_key("src", "abc", "enforce", "") != base
    assert local_common.renet_stamp_key("src", "abc", "nolicense", "k") != base
    assert local_common.renet_stamp_key("src", "abc", "nolicense", "") == base


def test_an_empty_head_keeps_the_key_the_stamp_held_before():
    legacy = local_common._hex_of(b"src=s\nlicense=nolicense\nkey=\n")
    assert local_common.renet_stamp_key("s", "", "nolicense", "") == legacy


def _repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "t")
    (path / "main.go").write_text("package main\n")
    (path / ".gitignore").write_text("bin/\n")  # renet's own checkout ignores its build output
    _git(path, "add", "main.go", ".gitignore")
    _git(path, "commit", "-q", "-m", "one")
    return _git(path, "rev-parse", "HEAD")


def test_renet_head_is_the_commit_of_its_own_checkout(tmp_path):
    head = _repo(tmp_path / "renet")
    assert local_common.renet_head(str(tmp_path / "renet")) == head


def test_renet_head_is_empty_for_a_plain_directory_inside_another_repo(tmp_path):
    _repo(tmp_path)
    (tmp_path / "private" / "renet").mkdir(parents=True)
    assert local_common.renet_head(str(tmp_path / "private" / "renet")) == ""


def test_renet_head_is_empty_outside_any_repo(tmp_path):
    (tmp_path / "renet").mkdir()
    assert local_common.renet_head(str(tmp_path / "renet")) == ""


def test_ensure_renet_built_rebuilds_when_only_head_moves(tmp_path, monkeypatch):
    """The wiring, not just the key: a stamp written for one commit matches it, and an empty commit on top makes ensure_renet_built build."""
    renet = tmp_path / "private" / "renet"
    _repo(renet)
    binary = renet / "bin" / "renet"
    binary.parent.mkdir()
    binary.write_text("binary")
    env = {
        "LOCAL_ROOT_DIR": str(tmp_path),
        "RDC_RENET_LICENSE": "0",
        "ACCOUNT_ED25519_PUBLIC_KEY": "",
        # A keyless build is the CI-only RENET_KEYLESS path since agent/plans/PLAN-production-key-only.md K3; without it the build is refused (or reads Bitwarden).
        "RENET_KEYLESS": "1",
        "GITHUB_ACTIONS": "true",
    }
    monkeypatch.setattr(local_common, "check_go_installed", lambda: None)
    builds = []

    def fake_run(argv, *, cwd=None, **_):
        builds.append((argv, cwd))
        return 1

    monkeypatch.setattr(local_common, "_run", fake_run)

    fingerprint = local_common.git_tree_fingerprint(str(renet), ["."], env)
    assert fingerprint is not None
    source = local_common._subst(fingerprint)
    key = local_common.renet_stamp_key(source, local_common.renet_head(str(renet)), "nolicense", "")
    stamp = renet_flavor.stamp_path(str(renet), "nolicense")
    local_common.write_stamp_hash(
        stamp, "%s\nbin=%s" % (key, local_common.renet_artifact_fp(str(binary)))
    )

    assert local_common.ensure_renet_built(env) is True
    assert builds == []

    _git(renet, "commit", "-q", "--allow-empty", "-m", "the same tree under a new commit")
    assert local_common.ensure_renet_built(env) is False
    assert builds == [(["./build.sh", "dev", "--nolicense"], str(renet))]


def _fake_build_env(tmp_path, monkeypatch):
    """A renet checkout whose `./build.sh dev <flag>` is recorded and writes `<flag>` into the flavor directory build.sh would use."""
    renet = tmp_path / "private" / "renet"
    _repo(renet)
    monkeypatch.setattr(local_common, "check_go_installed", lambda: None)
    builds = []

    def fake_run(argv, **_):
        builds.append(argv[-1])
        flavor = "enforce" if argv[-1] == "--license" else "nolicense"
        out = pathlib.Path(renet_flavor.binary(str(renet), flavor))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(argv[-1])
        return 0

    monkeypatch.setattr(local_common, "_run", fake_run)
    return renet, builds


def _env(tmp_path, license_env):
    return {
        "LOCAL_ROOT_DIR": str(tmp_path),
        "RDC_RENET_LICENSE": license_env,
        "ACCOUNT_ED25519_PUBLIC_KEY": "",
        # A keyless build is the CI-only RENET_KEYLESS path since agent/plans/PLAN-production-key-only.md K3; without it the build is refused (or reads Bitwarden).
        "RENET_KEYLESS": "1",
        "GITHUB_ACTIONS": "true",
    }


def _snapshot(renet, flavor):
    binary = pathlib.Path(renet_flavor.binary(str(renet), flavor))
    stamp = pathlib.Path(renet_flavor.stamp_path(str(renet), flavor))
    return (
        binary.read_text(),
        binary.stat().st_mtime_ns,
        stamp.read_text(),
        stamp.stat().st_mtime_ns,
    )


def test_a_plain_build_leaves_the_enforcing_binary_and_stamp_untouched(tmp_path, monkeypatch):
    renet, builds = _fake_build_env(tmp_path, monkeypatch)

    assert local_common.ensure_renet_built(_env(tmp_path, "1")) is True
    enforcing = _snapshot(renet, "enforce")
    assert enforcing[0] == "--license"

    assert local_common.ensure_renet_built(_env(tmp_path, "0")) is True
    assert _snapshot(renet, "enforce") == enforcing
    assert pathlib.Path(renet_flavor.binary(str(renet), "nolicense")).read_text() == "--nolicense"

    assert local_common.ensure_renet_built(_env(tmp_path, "1")) is True
    assert builds == ["--license", "--nolicense"]


def test_the_sequence_is_red_when_both_flavors_share_one_directory(tmp_path, monkeypatch):
    """Mutant: with SUBDIR mapping both flavors to bin, the plain build overwrites the enforcing binary, and the third call has to rebuild."""
    monkeypatch.setitem(renet_flavor.SUBDIR, "enforce", "bin")
    _renet, builds = _fake_build_env(tmp_path, monkeypatch)

    local_common.ensure_renet_built(_env(tmp_path, "1"))
    local_common.ensure_renet_built(_env(tmp_path, "0"))
    local_common.ensure_renet_built(_env(tmp_path, "1"))

    assert builds != ["--license", "--nolicense"]


def test_the_flavor_stamps_are_distinct_files(tmp_path, monkeypatch):
    renet, _ = _fake_build_env(tmp_path, monkeypatch)
    local_common.ensure_renet_built(_env(tmp_path, "1"))
    local_common.ensure_renet_built(_env(tmp_path, "0"))
    plain = renet_flavor.stamp_path(str(renet), "nolicense")
    enforce = renet_flavor.stamp_path(str(renet), "enforce")
    assert plain != enforce
    assert pathlib.Path(plain).is_file()
    assert pathlib.Path(enforce).is_file()
    assert not (tmp_path / ".ci" / "cache" / "build-renet.stamp").exists()
