"""`renet_stamp_key` moves when renet's HEAD moves over an unchanged tree.

A rebase-merge replays renet's commits under new SHAs with byte-identical trees. bin/renet stamps `vcs.revision`, and `npm run vm:check` refuses a binary whose revision is not the checkout (renet-build-mismatch). On 2026-10-23 the stamp held only the tree fingerprint, so `./rdc.sh --version` found it current and never rebuilt, and vm:check refused on every run (c32bb4884efa built, 0a89e786caef checked out).
"""

import subprocess

import pytest

from rediacc_ci.core import local_common

# A syntactically valid ED25519 public key, fixture only.
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


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

    first = local_common.renet_stamp_key(first_fp, first_head, "")
    second = local_common.renet_stamp_key(second_fp, second_head, "")
    assert first != second


def test_the_key_still_moves_with_source_and_key():
    base = local_common.renet_stamp_key("src", "abc", "")
    assert local_common.renet_stamp_key("src2", "abc", "") != base
    assert local_common.renet_stamp_key("src", "abc", "k") != base
    assert local_common.renet_stamp_key("src", "abc", "") == base


def test_an_empty_head_leaves_the_head_line_out():
    assert local_common.renet_stamp_key("s", "", "k") == local_common._hex_of(b"src=s\nkey=k\n")


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
    env = {"LOCAL_ROOT_DIR": str(tmp_path), "ACCOUNT_ED25519_PUBLIC_KEY": KEY}
    monkeypatch.setattr(local_common, "check_go_installed", lambda: None)
    builds = []

    def fake_run(argv, *, cwd=None, **_):
        builds.append((argv, cwd))
        return 1

    monkeypatch.setattr(local_common, "_run", fake_run)

    fingerprint = local_common.git_tree_fingerprint(str(renet), ["."], env)
    assert fingerprint is not None
    source = local_common._subst(fingerprint)
    key = local_common.renet_stamp_key(source, local_common.renet_head(str(renet)), KEY)
    stamp = renet / "bin" / local_common.RENET_STAMP_NAME
    local_common.write_stamp_hash(
        str(stamp), "%s\nbin=%s" % (key, local_common.renet_artifact_fp(str(binary)))
    )

    assert local_common.ensure_renet_built(env) is True
    assert builds == []

    _git(renet, "commit", "-q", "--allow-empty", "-m", "the same tree under a new commit")
    assert local_common.ensure_renet_built(env) is False
    assert builds == [(["./build.sh", "dev"], str(renet))]


def _fake_build_env(tmp_path, monkeypatch, refusal=None):
    """A renet checkout whose `./build.sh dev` is recorded and writes `bin/renet`, with the key gate answering `refusal`."""
    renet = tmp_path / "private" / "renet"
    _repo(renet)
    monkeypatch.setattr(local_common, "check_go_installed", lambda: None)
    builds = []
    gated = []

    def fake_run(argv, **_):
        builds.append(argv)
        out = renet / "bin" / "renet"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("built")
        return 0

    def fake_gate(binary, key):
        gated.append((binary, key))
        return refusal

    monkeypatch.setattr(local_common, "_run", fake_run)
    monkeypatch.setattr(local_common, "renet_key_refusal", fake_gate)
    return renet, builds, gated


def _env(tmp_path):
    return {"LOCAL_ROOT_DIR": str(tmp_path), "ACCOUNT_ED25519_PUBLIC_KEY": KEY}


def test_every_build_is_key_gated_and_stamped_in_bin(tmp_path, monkeypatch):
    renet, builds, gated = _fake_build_env(tmp_path, monkeypatch)
    assert local_common.ensure_renet_built(_env(tmp_path)) is True
    assert builds == [["./build.sh", "dev"]]
    assert gated == [(str(renet / "bin" / "renet"), KEY)]
    assert (renet / "bin" / local_common.RENET_STAMP_NAME).is_file()
    assert not (renet / "bin" / "enforce").exists()
    # The stamp matches now, so neither a build nor the gate runs again.
    assert local_common.ensure_renet_built(_env(tmp_path)) is True
    assert len(builds) == 1
    assert len(gated) == 1


def test_a_refused_build_raises_and_leaves_no_stamp(tmp_path, monkeypatch):
    renet, builds, _ = _fake_build_env(tmp_path, monkeypatch, refusal="baked key differs")
    with pytest.raises(local_common.LocalCommonError):
        local_common.ensure_renet_built(_env(tmp_path))
    assert builds == [["./build.sh", "dev"]]
    assert not (renet / "bin" / local_common.RENET_STAMP_NAME).exists()
    # The next run rebuilds rather than trusting the refused binary.
    with pytest.raises(local_common.LocalCommonError):
        local_common.ensure_renet_built(_env(tmp_path))
    assert len(builds) == 2
