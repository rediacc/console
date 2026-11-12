"""`commit_policy.push_elsewhere` and its fail-closed arms (review 3f1e18bf.1).

The function answers True only for a push whose every destination is a repository this checkout's policy does not read. Each doubt answers False. The control row is the plain scratch push to a local bare remote, which answers True, so a False below is the arm's doing and not a broken setup.
"""

from __future__ import annotations

import importlib
import subprocess

import pytest

CP = importlib.import_module("rediacc_hooks.commit_policy")
SS = importlib.import_module("rediacc_hooks.shellscan")
WK = importlib.import_module("rediacc_hooks.wellknown")
OWN_URL = "%s/%s.git" % (WK.GH_ORIGIN, WK.GH_REPO)


def _git(directory, *args) -> None:
    subprocess.run(["git", "-C", str(directory), *args], check=True, capture_output=True)


@pytest.fixture
def world(tmp_path):
    """A console stand-in (`root`), a scratch repository with a local bare `origin`, and the bare repository."""
    root = tmp_path / "console"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    subprocess.run(["git", "init", "-q", str(scratch)], check=True)
    _git(scratch, "remote", "add", "origin", str(bare))
    return {"root": root, "bare": bare, "scratch": scratch, "tmp": tmp_path}


def _judge(world, cmd: str, directory=None) -> bool:
    run = next(r for r in SS.every_run(cmd) if r.name.rsplit("/", 1)[-1] == "git")
    return CP.push_elsewhere(run, str(directory or world["scratch"]), str(world["root"]), cmd=cmd)


def test_control_a_local_bare_remote_outside_the_checkout_is_elsewhere(world):
    assert _judge(world, "git push origin main") is True


def test_a_file_url_and_a_plain_path_outside_the_checkout_are_elsewhere(world):
    assert _judge(world, "git push file://%s main" % world["bare"]) is True
    assert _judge(world, "git push %s main" % world["bare"]) is True


def test_a_path_inside_the_checkout_is_not_elsewhere(world):
    inside = world["root"] / "sub"
    inside.mkdir()
    assert _judge(world, "git push %s main" % inside) is False
    assert _judge(world, "git push file://%s main" % inside) is False


def test_a_repository_sharing_the_checkouts_store_is_not_elsewhere(world):
    """A directory outside the tree whose `.git` file names this checkout's store."""
    common = CP.common_dir(str(world["root"]))
    twin = world["tmp"] / "twin"
    twin.mkdir()
    (twin / ".git").write_text("gitdir: %s\n" % common, encoding="utf-8")
    assert _judge(world, "git push %s main" % twin) is False


def test_a_network_url_is_elsewhere_unless_it_is_the_consoles_own(world):
    assert _judge(world, "git push https://example.org/someone/else.git main") is True
    assert _judge(world, "git push %s main" % OWN_URL) is False
    assert _judge(world, "git push git@github.com:%s main" % WK.GH_REPO) is False


def test_a_pushurl_set_on_the_command_line_is_a_doubt(world):
    cmd = "git -c remote.origin.pushurl=%s push origin main" % OWN_URL
    assert _judge(world, cmd) is False


def test_a_remote_edited_in_the_same_command_is_a_doubt(world):
    for edit in (
        "git remote set-url origin %s" % OWN_URL,
        "git config remote.origin.pushurl %s" % OWN_URL,
    ):
        assert _judge(world, "%s && git push origin main" % edit) is False


def test_an_insteadof_rewrite_is_a_doubt(world):
    _git(
        world["scratch"],
        "config",
        "url.%s/%s.git.insteadOf" % (WK.GH_ORIGIN, WK.GH_REPO),
        str(world["bare"]),
    )
    assert _judge(world, "git push origin main") is False


def test_a_remote_whose_push_url_git_cannot_read_is_a_doubt(world, monkeypatch):
    """Git answers for every remote a real repository can configure, so the failure is stood in for: `remote get-url` answers nothing."""
    assert _judge(world, "git push origin main") is True
    real = CP.git

    def silent(args, **kwargs):
        return None if list(args[:2]) == ["remote", "get-url"] else real(args, **kwargs)

    monkeypatch.setattr(CP, "git", silent)
    assert _judge(world, "git push origin main") is False


def test_a_global_option_but_c_is_a_doubt(world):
    assert _judge(world, "git --no-pager push origin main") is False
    assert _judge(world, "git -C %s push origin main" % world["scratch"]) is True
