"""`./rdc.sh` keeps working while private/renet is mid-cherry-pick (#fd1964b9).

On 2026-11-06 the lead was mid-cherry-pick in private/renet with conflict markers in pkg/i18n/locales/*.go, and every `./rdc.sh` call rebuilt renet from that tree and died on `syntax error: unexpected <<`. `renet_mid_operation` names the state (unmerged paths, or a cherry-pick, merge, revert, rebase or am in progress), and `ensure_renet_built` then hands on the last good binary with one stderr line, or refuses by name when there is none.

Each fixture is a REAL git repository driven into the state, never a mocked git: a cherry-pick that conflicts, a merge that conflicts, and a clean tree as the control. The build itself is stubbed (`_run`), so a test that reaches it records the call.
"""

import subprocess

import pytest

from rediacc_ci.core import local_common

# A syntactically valid ED25519 public key, fixture only.
KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


@pytest.fixture(autouse=True)
def git_env(monkeypatch):
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)


def _git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def _renet(path):
    """A renet checkout on `main` with a locale file, and a branch `other` that edits the same line, so picking or merging it conflicts."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "--initial-branch=main")
    (path / ".gitignore").write_text("bin/\n")
    locale = path / "pkg" / "i18n" / "locales" / "en.go"
    locale.parent.mkdir(parents=True)
    locale.write_text('package locales\n\nconst Hello = "hello"\n')
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "one")
    _git(path, "checkout", "-q", "-b", "other")
    locale.write_text('package locales\n\nconst Hello = "hi"\n')
    _git(path, "commit", "-q", "-am", "other side")
    _git(path, "checkout", "-q", "main")
    locale.write_text('package locales\n\nconst Hello = "hey"\n')
    _git(path, "commit", "-q", "-am", "main side")
    return path


def test_a_clean_checkout_is_not_mid_operation(tmp_path):
    renet = _renet(tmp_path / "renet")
    assert local_common.renet_mid_operation(str(renet)) == ""


def test_a_conflicted_cherry_pick_is_named(tmp_path):
    renet = _renet(tmp_path / "renet")
    assert _git(renet, "cherry-pick", "other", check=False).returncode != 0
    reason = local_common.renet_mid_operation(str(renet))
    assert reason.startswith("1 unmerged path(s) (pkg/i18n/locales/en.go")
    assert "<<<<<<<" in (renet / "pkg" / "i18n" / "locales" / "en.go").read_text()


def test_a_resolved_but_unfinished_cherry_pick_is_named_by_its_marker(tmp_path):
    """No unmerged path left, but CHERRY_PICK_HEAD still says the pick is open."""
    renet = _renet(tmp_path / "renet")
    _git(renet, "cherry-pick", "other", check=False)
    (renet / "pkg" / "i18n" / "locales" / "en.go").write_text(
        'package locales\n\nconst Hello = "hi"\n'
    )
    _git(renet, "add", "pkg/i18n/locales/en.go")
    assert local_common.renet_mid_operation(str(renet)) == (
        "CHERRY_PICK_HEAD is present (an operation is in progress)"
    )


def test_a_conflicted_merge_is_named(tmp_path):
    renet = _renet(tmp_path / "renet")
    assert _git(renet, "merge", "other", check=False).returncode != 0
    assert "unmerged path(s)" in local_common.renet_mid_operation(str(renet))


def test_the_marker_is_read_from_the_linked_tree_it_belongs_to(tmp_path):
    """A lease's renet is a linked tree of the module store: its markers live under its own git dir, and the store's main tree stays clean."""
    renet = _renet(tmp_path / "renet")
    linked = tmp_path / "linked"
    _git(renet, "worktree", "add", "-q", "--detach", str(linked), "main")
    _git(linked, "cherry-pick", "other", check=False)
    assert local_common.renet_mid_operation(str(linked)) != ""
    assert local_common.renet_mid_operation(str(renet)) == ""


def test_a_plain_directory_inside_a_conflicted_repo_is_not_asked(tmp_path):
    """The `renet_head` rule: a plain `private/renet` inside a console mid-cherry-pick answers nothing, because git there would describe the console."""
    console = _renet(tmp_path)
    _git(console, "cherry-pick", "other", check=False)
    (console / "private" / "renet").mkdir(parents=True)
    assert local_common.renet_mid_operation(str(console / "private" / "renet")) == ""


def _world(tmp_path, monkeypatch):
    renet = _renet(tmp_path / "private" / "renet")
    env = {"LOCAL_ROOT_DIR": str(tmp_path), "ACCOUNT_ED25519_PUBLIC_KEY": KEY}
    monkeypatch.setattr(local_common, "check_go_installed", lambda: None)
    builds = []

    def fake_run(argv, *, cwd=None, **_):
        builds.append((argv, cwd))
        return 1

    monkeypatch.setattr(local_common, "_run", fake_run)
    return renet, env, builds


def _good_binary(renet):
    binary = renet / "bin" / "renet"
    binary.parent.mkdir(exist_ok=True)
    binary.write_text("last good build")
    stamp = renet / "bin" / local_common.RENET_STAMP_NAME
    local_common.write_stamp_hash(
        str(stamp), "stale-key\nbin=%s" % local_common.renet_artifact_fp(str(binary))
    )
    return binary


def _gate(gated: list, binary, key) -> None:
    gated.append((binary, key))


def test_mid_cherry_pick_the_last_good_binary_serves_without_a_build(tmp_path, monkeypatch, capsys):
    renet, env, builds = _world(tmp_path, monkeypatch)
    _good_binary(renet)
    gated: list = []
    monkeypatch.setattr(local_common, "renet_key_refusal", lambda b, k: _gate(gated, b, k))
    _git(renet, "cherry-pick", "other", check=False)
    assert local_common.ensure_renet_built(env) is True
    assert gated == [(str(renet / "bin" / "renet"), KEY)]
    assert builds == []
    out, err = capsys.readouterr()
    assert out == ""
    lines = [line for line in err.splitlines() if "renet rebuild skipped" in line]
    assert len(lines) == 1, err
    assert "unmerged path(s)" in lines[0]
    assert "last good" in lines[0]


def test_mid_cherry_pick_a_binary_of_another_account_key_is_not_handed_on(
    tmp_path, monkeypatch, capsys
):
    """Review 520056bf.1: the stamp proves the build, not today's key, so the key gate runs on the fallback too."""
    renet, env, builds = _world(tmp_path, monkeypatch)
    _good_binary(renet)
    monkeypatch.setattr(
        local_common,
        "renet_key_refusal",
        lambda b, _k: "%s does not bake the account key ab:cd" % b,
    )
    _git(renet, "cherry-pick", "other", check=False)
    with pytest.raises(local_common.LocalCommonError):
        local_common.ensure_renet_built(env)
    assert builds == []
    err = capsys.readouterr().err
    assert "not usable" in err
    assert "does not bake the account key" in err


def test_mid_cherry_pick_with_no_binary_refuses_by_name(tmp_path, monkeypatch, capsys):
    renet, env, builds = _world(tmp_path, monkeypatch)
    _git(renet, "cherry-pick", "other", check=False)
    with pytest.raises(local_common.LocalCommonError):
        local_common.ensure_renet_built(env)
    assert builds == []
    err = capsys.readouterr().err
    assert "cannot be built" in err
    assert "no last good renet" in err


def test_mid_cherry_pick_an_unstamped_binary_is_not_last_good(tmp_path, monkeypatch, capsys):
    """A binary the key gate refused carries no stamp: it is not handed on."""
    renet, env, builds = _world(tmp_path, monkeypatch)
    binary = _good_binary(renet)
    (renet / "bin" / local_common.RENET_STAMP_NAME).unlink()
    assert binary.is_file()
    _git(renet, "cherry-pick", "other", check=False)
    with pytest.raises(local_common.LocalCommonError):
        local_common.ensure_renet_built(env)
    assert builds == []
    assert "no last good renet" in capsys.readouterr().err


def test_control_a_clean_tree_with_a_stale_stamp_still_builds(tmp_path, monkeypatch):
    """CONTROL: the skip is the operation's, not the binary's: with no operation open, the same stale stamp reaches the build."""
    renet, env, builds = _world(tmp_path, monkeypatch)
    _good_binary(renet)
    assert local_common.ensure_renet_built(env) is False
    assert builds == [(["./build.sh", "dev"], str(renet))]


def test_an_old_git_without_path_format_still_names_the_marker(tmp_path, monkeypatch):
    """A git older than 2.31 refuses `--path-format`; the marker check must not fall back to "nothing in progress"."""
    renet = _renet(tmp_path / "renet")
    _git(renet, "cherry-pick", "other", check=False)
    (renet / "pkg" / "i18n" / "locales" / "en.go").write_text(
        'package locales\n\nconst Hello = "hi"\n'
    )
    _git(renet, "add", "pkg/i18n/locales/en.go")
    real = local_common._capture

    def old_git(argv, **kw):
        if any(a.startswith("--path-format") for a in argv):
            return subprocess.CompletedProcess(argv, 129, "", "")
        return real(argv, **kw)

    monkeypatch.setattr(local_common, "_capture", old_git)
    assert local_common.renet_mid_operation(str(renet)) == (
        "CHERRY_PICK_HEAD is present (an operation is in progress)"
    )
