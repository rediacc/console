"""`renet_stamp_key` moves when renet's HEAD moves over an unchanged tree.

A rebase-merge replays renet's commits under new SHAs with byte-identical trees. bin/renet stamps `vcs.revision`, and `npm run vm:check` refuses a binary whose revision is not the checkout (renet-build-mismatch). On 2026-10-23 the stamp held only the tree fingerprint, so `./rdc.sh --version` found it current and never rebuilt, and vm:check refused on every run (c32bb4884efa built, 0a89e786caef checked out).
"""

import subprocess

from rediacc_ci.core import local_common


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
    _git(path, "add", "main.go")
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
    }
    monkeypatch.setattr(local_common, "check_go_installed", lambda: None)
    builds = []

    def fake_run(argv, *, cwd=None, **_):
        builds.append((argv, cwd))
        return 1

    monkeypatch.setattr(local_common, "_run", fake_run)

    source = local_common._subst(local_common.git_tree_fingerprint(str(renet), ["."], env))
    key = local_common.renet_stamp_key(source, local_common.renet_head(str(renet)), "nolicense", "")
    stamp = tmp_path / ".ci" / "cache" / "build-renet.stamp"
    stamp.parent.mkdir(parents=True)
    local_common.write_stamp_hash(
        str(stamp), "%s\nbin=%s" % (key, local_common.renet_artifact_fp(str(binary)))
    )

    assert local_common.ensure_renet_built(env) is True
    assert builds == []

    _git(renet, "commit", "-q", "--allow-empty", "-m", "the same tree under a new commit")
    assert local_common.ensure_renet_built(env) is False
    assert builds == [(["./build.sh", "dev"], str(renet))]
