"""The hook suite's autouse `_no_ambient_git_config` (conftest.py) holds: git reads no global or system config here.

A git that ignored `GIT_CONFIG_GLOBAL` (older than 2.32) would list the operator's or the CI runner's global entries below, so this fails loudly instead of the fixture becoming a silent no-op (review 25d2271c.2)."""

from __future__ import annotations

import os
import subprocess


def _listed(scope: str, cwd=None) -> str:
    argv = ["git", "config", *([scope] if scope else []), "--list"]
    done = subprocess.run(argv, capture_output=True, text=True, check=False, cwd=cwd)
    return done.stdout.strip()


def test_git_reads_no_global_or_system_entries(tmp_path):
    """`git config --list` outside a repository is every entry git reads implicitly: with the system file skipped and the global file empty, nothing."""
    assert os.environ.get("GIT_CONFIG_NOSYSTEM") == "1"
    assert _listed("--global") == ""
    assert _listed("", cwd=tmp_path) == ""


def test_control_git_honours_the_global_file_it_is_pointed_at(tmp_path, monkeypatch):
    """The control: an entry in the file `GIT_CONFIG_GLOBAL` names is listed, so the empty listing above is the fixture's doing and not a git that reads nothing."""
    own = tmp_path / "gitconfig"
    own.write_text('[url "https://example.org/"]\n\tinsteadOf = x:\n', encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(own))
    assert "insteadof" in _listed("--global").lower()
