"""The shared backup-push predicate (`rediacc_hooks.guards._backup_push.admitted`) admits only the real `git`.

Review 2577b833.1: the predicate compared `os.path.basename(run.name)` to `git`, so `./git push gitlab HEAD:refs/backup/...` or `/tmp/x/git push ...`, a program that merely carries the name, was admitted past every push guard. The bare `git` stays admitted (the control).
"""

from __future__ import annotations

import importlib
import subprocess

BP = importlib.import_module("rediacc_hooks.guards._backup_push")


class Ev:
    """The two fields `admitted` reads from a hook event: the project dir and the cwd."""

    def __init__(self, repo: str) -> None:
        self.repo = repo

    def env(self, name: str) -> str:
        return self.repo if name == "CLAUDE_PROJECT_DIR" else ""

    def field(self, name: str) -> str:
        return self.repo if name == "cwd" else ""


def _repo(tmp_path) -> str:
    repo = tmp_path / "console"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return BP.plant(repo)


def test_the_bare_git_push_to_the_pin_is_admitted(tmp_path):
    repo = _repo(tmp_path)
    assert BP.admitted(Ev(repo), BP.BACKUP_PUSH) is True


def test_a_program_named_git_by_a_relative_path_is_not_git(tmp_path):
    repo = _repo(tmp_path)
    assert BP.admitted(Ev(repo), "./" + BP.BACKUP_PUSH) is False


def test_a_program_named_git_by_an_absolute_path_is_not_git(tmp_path):
    repo = _repo(tmp_path)
    assert BP.admitted(Ev(repo), "/tmp/x/" + BP.BACKUP_PUSH) is False
