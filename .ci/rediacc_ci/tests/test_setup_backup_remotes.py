"""The backup-remote step of the `git-hooks-path` setup phase (box G4 of agent/plans/PLAN-local-first-delivery.md), against a synthetic console with real nested repositories.

THE PINS COME FROM THE HOOK. Every expected URL is computed from `githooks.BACKUP_PATHS` and `MIRROR_HOST` in .claude/rediacc_hooks/git/githooks.py, so a test that typed the URLs could not drift from the hook unnoticed. And the URL written is then fed to the hook's own `backup_url_refusal`, which must admit it.

BOTH DIRECTIONS. A missing remote is added (with no fetch refspec, so nothing can land in `refs/remotes/gitlab/*`); a second run changes nothing and says nothing; a remote at another URL is reported and left byte-for-byte alone. The control for the idempotency case is the first run, which must have said something and changed the config.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

from rediacc_ci.setup import backup_remotes as br
from rediacc_ci.setup import githooks as setup_githooks

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
ENV_GIT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def _load_hooks():
    name = "githooks_backup_remotes_test"
    spec = importlib.util.spec_from_file_location(name, br.HOOKS_FILE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GH = _load_hooks()


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", *ENV_GIT, "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _console(tmp_path: pathlib.Path, subs=("private/renet", "private/account")) -> pathlib.Path:
    root = tmp_path / "console"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    for rel in subs:
        sub = root / rel
        sub.mkdir(parents=True)
        _git(sub, "init", "-q", "-b", "main")
    return root


def _config(repo: pathlib.Path) -> str:
    return (repo / ".git" / "config").read_text(encoding="utf-8")


def test_the_pins_are_the_hooks_own():
    want = {
        rel: "https://%s%s" % (GH.MIRROR_HOST, path) for rel, path in GH.BACKUP_PATHS.items() if rel
    }
    assert br.pins() == want
    assert set(want) == {"private/renet", "private/account", "private/elite"}


def test_missing_remotes_are_added_and_a_second_run_changes_nothing(tmp_path):
    root = _console(tmp_path)
    said: list[str] = []
    assert br.install(root, say=said.append) == 0
    assert len(said) == 2  # control: the first run did something
    for rel in ("private/renet", "private/account"):
        repo = root / rel
        url = _git(repo, "remote", "get-url", "--push", "gitlab")
        assert url == br.pins()[rel]
        assert (
            subprocess.run(
                ["git", "-C", str(repo), "config", "--get-all", "remote.gitlab.fetch"],
                capture_output=True,
                check=False,
            ).returncode
            == 1
        ), "a fetch refspec would write refs/remotes/gitlab/*"
        assert _git(repo, "config", "remote.gitlab.skipFetchAll") == "true"
        assert _git(repo, "config", "remote.gitlab.tagOpt") == "--no-tags"
    before = {rel: _config(root / rel) for rel in ("private/renet", "private/account")}
    said.clear()
    assert br.install(root, say=said.append) == 0
    assert said == []
    assert {rel: _config(root / rel) for rel in before} == before
    assert br.check_row(root)[1] is False


def test_a_remote_at_another_url_is_reported_and_left_alone(tmp_path):
    root = _console(tmp_path, subs=("private/renet",))
    repo = root / "private" / "renet"
    _git(repo, "remote", "add", "gitlab", "https://user:secret@example.invalid/x/renet.git")
    before = _config(repo)
    said: list[str] = []
    assert br.install(root, say=said.append) == 0
    assert _config(repo) == before
    assert len(said) == 1
    assert "left alone" in said[0]
    assert "secret" not in said[0]
    assert br.check_row(root)[1] is False


def test_a_submodule_not_checked_out_is_skipped(tmp_path):
    root = _console(tmp_path, subs=())
    said: list[str] = []
    assert br.install(root, say=said.append) == 0
    assert said == []


def test_check_row_names_a_missing_remote(tmp_path):
    root = _console(tmp_path, subs=("private/elite",))
    row, pending = br.check_row(root)
    assert pending is True
    assert "private/elite" in row


def test_the_added_url_is_admitted_by_the_pre_push_hook(tmp_path):
    root = _console(tmp_path, subs=("private/renet",))
    assert br.install(root, say=lambda _s: None) == 0
    repo = root / "private" / "renet"
    url = _git(repo, "remote", "get-url", "--push", "gitlab")
    head = None
    (repo / "f").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    head = _git(repo, "rev-parse", "HEAD")
    _git(root, "update-index", "--add", "--cacheinfo", "160000,%s,private/renet" % head)
    _git(root, "commit", "-q", "-m", "pin")
    assert GH.backup_url_refusal(str(repo), url) == ""
    assert GH.backup_url_refusal(str(repo), br.pins()["private/account"]) != ""


def test_the_setup_phase_runs_the_step(tmp_path):
    root = _console(tmp_path, subs=("private/renet",))
    hooks = setup_githooks.hooks_dir(root)
    hooks.mkdir(parents=True)
    for name in setup_githooks.HOOK_NAMES:
        (hooks / name).write_text("#!/bin/sh\n", encoding="utf-8")
        (hooks / name).chmod(0o755)
    (root / ".gitmodules").write_text('[submodule "r"]\n\tpath = private/renet\n', encoding="utf-8")
    said: list[str] = []
    assert setup_githooks.install(root, say=said.append) == 0
    assert (
        _git(root / "private" / "renet", "remote", "get-url", "gitlab")
        == br.pins()["private/renet"]
    )
    assert any("backup remotes" in line for line in said)


def _failing(monkeypatch, needle: str):
    """`br._git` that fails any command containing `needle` and runs the rest for real."""
    real = br._git

    def fake(repo, *args):
        if needle in args:
            return subprocess.CompletedProcess(args, 1, "", "injected failure")
        return real(repo, *args)

    monkeypatch.setattr(br, "_git", fake)


def test_a_step_that_fails_after_the_add_returns_1_and_the_next_run_finishes_it(
    tmp_path, monkeypatch
):
    """The half-done remote (added, refspec still there) must not read as done on the next run (3cbc97c3.1, .2)."""
    root = _console(tmp_path, subs=("private/renet",))
    repo = root / "private" / "renet"
    with monkeypatch.context() as m:
        _failing(m, "--unset-all")
        said: list[str] = []
        assert br.install(root, say=said.append) == 1
        assert any("failed" in line for line in said)
    # The state the review feared: the remote exists with its default refspec.
    assert "refs/remotes/gitlab" in _config(repo)
    assert br.fetchable(repo)
    assert br.install(root, say=lambda _line: None) == 0
    assert not br.fetchable(repo)
    assert "refs/remotes/gitlab" not in _config(repo)
    assert "skipFetchAll = true" in _config(repo)


def test_a_remote_left_with_its_default_refspec_is_repaired(tmp_path):
    root = _console(tmp_path, subs=("private/renet",))
    repo = root / "private" / "renet"
    _git(repo, "remote", "add", "gitlab", br.pins()["private/renet"])
    assert "refs/remotes/gitlab" in _config(repo)
    assert br.install(root, say=lambda _line: None) == 0
    assert "refs/remotes/gitlab" not in _config(repo)
    assert not br.fetchable(repo)


def test_a_failed_remote_add_returns_1(tmp_path, monkeypatch):
    root = _console(tmp_path, subs=("private/renet",))
    _failing(monkeypatch, "add")
    assert br.install(root, say=lambda _line: None) == 1
    assert br.current(root / "private" / "renet") == ""


def test_check_row_reports_a_remote_that_kept_its_refspec_as_pending(tmp_path):
    root = _console(tmp_path, subs=("private/renet",))
    _git(root / "private" / "renet", "remote", "add", "gitlab", br.pins()["private/renet"])
    row, pending = br.check_row(root)
    assert pending
    assert "fetch refspec" in row
    br.install(root, say=lambda _line: None)
    assert br.check_row(root)[1] is False


def test_check_row_names_both_the_unlocked_and_the_missing_repositories(tmp_path):
    """18716f60.2: a mixed run shows the refspec row and the repositories that have no remote at all."""
    root = _console(tmp_path)
    _git(root / "private" / "renet", "remote", "add", "gitlab", br.pins()["private/renet"])
    row, pending = br.check_row(root)
    assert pending
    assert "fetch refspec in private/renet" in row
    assert "NOT added in private/account" in row
