"""The differential's repository identity does not depend on where the checkout was cloned from."""

import subprocess

from rediacc_hooks import shellscan
from rediacc_hooks.tests import test_shellscan_differential as differential


def _git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True)


def test_a_shared_clone_resolves_to_the_hosted_identity(tmp_path):
    upstream = tmp_path / "upstream"
    clone = tmp_path / "clone"
    _git("init", "-q", str(upstream))
    _git("-C", str(upstream), "remote", "add", "origin", "https://github.com/rediacc/console.git")
    _git("init", "-q", str(clone))
    _git("-C", str(clone), "remote", "add", "origin", str(upstream))
    # What a local-path origin yields unfixed: the clone's own origin names a directory.
    assert shellscan.target_repo("", "", str(clone)) == "%s/upstream" % tmp_path.name
    root = differential.identity_root(clone)
    assert root == upstream
    assert shellscan.target_repo("", "", str(root)) == "rediacc/console"


def test_a_url_origin_is_its_own_identity_root(tmp_path):
    repo = tmp_path / "repo"
    _git("init", "-q", str(repo))
    _git("-C", str(repo), "remote", "add", "origin", "https://github.com/rediacc/console.git")
    assert differential.identity_root(repo) == repo


def test_an_origin_cycle_terminates(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    _git("init", "-q", str(a))
    _git("init", "-q", str(b))
    _git("-C", str(a), "remote", "add", "origin", str(b))
    _git("-C", str(b), "remote", "add", "origin", str(a))
    assert differential.identity_root(a) in (a, b)


def test_a_file_url_and_a_relative_origin_are_followed_like_a_path(tmp_path):
    """Review 878aa247.3: git clones from `file://<path>` and from a relative path too, and both are local origins."""
    upstream = tmp_path / "upstream"
    _git("init", "-q", str(upstream))
    _git("-C", str(upstream), "remote", "add", "origin", "https://github.com/rediacc/console.git")
    for name, origin in (("by-url", "file://%s" % upstream), ("by-relative", "../upstream")):
        clone = tmp_path / name
        _git("init", "-q", str(clone))
        _git("-C", str(clone), "remote", "add", "origin", origin)
        root = differential.identity_root(clone)
        assert root.resolve() == upstream.resolve(), (name, root)
        assert shellscan.target_repo("", "", str(root)) == "rediacc/console", name


def test_a_windows_drive_origin_is_local_and_a_hosted_one_is_not(tmp_path):
    assert differential._local_origin(tmp_path, "C:\\src\\console") is not None
    assert differential._local_origin(tmp_path, "D:/src/console") is not None
    for hosted in (
        "https://github.com/rediacc/console.git",
        "ssh://git@github.com/rediacc/console.git",
        "git@github.com:rediacc/console.git",
        "",
    ):
        assert differential._local_origin(tmp_path, hosted) is None, hosted


def test_ci_never_takes_the_submodule_exemption(monkeypatch):
    """Review 878aa247.1: the exemption exists for a scratch clone, and CI checks the submodules out, so under CI a case whose root field cannot resolve is compared and fails rather than skipping."""
    want = {"troot": differential.REPO_TOKEN + "/private/zz-absent-submodule/x"}
    monkeypatch.delenv("CI", raising=False)
    assert differential.root_exemption(want) == "private/zz-absent-submodule"
    monkeypatch.setenv("CI", "true")
    assert differential.root_exemption(want) is None
