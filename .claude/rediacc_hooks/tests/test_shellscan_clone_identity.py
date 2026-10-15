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
