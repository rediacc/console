"""The differential's repository identity does not depend on where the checkout was cloned from."""

import pathlib
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


def test_origin_spellings_follow_git_on_posix(tmp_path):
    """Review fb481875.2, .3, .5: a bare relative origin is a path, and a colon before the first slash is git's scp form, a drive letter included."""
    for local, want in (
        ("upstream", tmp_path / "upstream"),
        ("../up", tmp_path / "../up"),
        ("/abs/console", pathlib.Path("/abs/console")),
        ("file:///abs/my%20console", pathlib.Path("/abs/my console")),
        ("dir/with:colon", tmp_path / "dir/with:colon"),
    ):
        assert differential._local_origin(tmp_path, local) == want, local
    for hosted in (
        "https://github.com/rediacc/console.git",
        "ssh://git@github.com/rediacc/console.git",
        "git@github.com:rediacc/console.git",
        "C:/src/console",
        "C:\\src\\console",
        "",
    ):
        assert differential._local_origin(tmp_path, hosted) is None, hosted


def test_a_bare_relative_origin_resolves_to_the_hosted_identity(tmp_path):
    upstream = tmp_path / "upstream"
    clone = tmp_path / "clone"
    _git("init", "-q", str(upstream))
    _git("-C", str(upstream), "remote", "add", "origin", "https://github.com/rediacc/console.git")
    _git("init", "-q", str(clone))
    _git("-C", str(clone), "remote", "add", "origin", "../upstream")
    sub = clone / "upstream"
    assert differential.identity_root(clone).resolve() == upstream.resolve()
    assert not sub.exists()


def test_ci_never_takes_the_submodule_exemption(monkeypatch):
    """Review 878aa247.1: the exemption exists for a scratch clone, and CI checks the submodules out, so under CI a case whose root field cannot resolve is compared and fails rather than skipping."""
    want = {"troot": differential.REPO_TOKEN + "/private/zz-absent-submodule/x"}
    monkeypatch.delenv("CI", raising=False)
    assert differential.root_exemption(want) == "private/zz-absent-submodule"
    for value in ("true", ""):
        monkeypatch.setenv("CI", value)
        assert differential.root_exemption(want) is None, value
