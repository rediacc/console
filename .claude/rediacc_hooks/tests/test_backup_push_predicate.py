"""The shared backup-push predicate (`rediacc_hooks.guards._backup_push.admitted`) admits only the real `git`.

Review 2577b833.1: the predicate compared `os.path.basename(run.name)` to `git`, so `./git push gitlab HEAD:refs/backup/...` or `/tmp/x/git push ...`, a program that merely carries the name, was admitted past every push guard. The bare `git` stays admitted (the control).
"""

from __future__ import annotations

import importlib
import os
import subprocess

BP = importlib.import_module("rediacc_hooks.guards._backup_push")


class Ev:
    """The two fields `admitted` reads from a hook event: the project dir and the cwd."""

    def __init__(self, repo: str, cwd: str | None = None) -> None:
        self.repo = repo
        self.cwd = cwd or repo

    def env(self, name: str) -> str:
        return self.repo if name == "CLAUDE_PROJECT_DIR" else ""

    def field(self, name: str) -> str:
        return self.cwd if name == "cwd" else ""


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


# Review 2577b833.3: the other admitted shapes, each with a silent control that is refused.
PRE = "refs/backup/b/pre-rewrite-20261111T1200Z"
REWRITE = "git push --atomic gitlab :refs/backup/b/live HEAD:" + PRE
LEAF = "HEAD:refs/backup/b/live"


def test_the_rewrite_form_delete_is_admitted_only_atomic_and_paired(tmp_path):
    repo = _repo(tmp_path)
    assert BP.admitted(Ev(repo), REWRITE) is True
    assert BP.admitted(Ev(repo), REWRITE.replace("--atomic ", "")) is False
    assert BP.admitted(Ev(repo), "git push --atomic gitlab :refs/backup/b/live") is False
    unpaired = "git push --atomic gitlab :refs/backup/b/daily-2026-11-11 HEAD:" + PRE
    assert BP.admitted(Ev(repo), unpaired) is False


def test_a_dash_c_global_names_the_repository_the_push_runs_in(tmp_path):
    repo = _repo(tmp_path)
    away = str(tmp_path)
    assert BP.admitted(Ev(repo, away), "git -C %s push gitlab %s" % (repo, LEAF)) is True
    assert BP.admitted(Ev(repo, away), "git push gitlab %s" % LEAF) is False


def test_a_cd_before_the_push_places_it_in_this_checkout(tmp_path):
    repo = _repo(tmp_path)
    away = str(tmp_path)
    assert BP.admitted(Ev(repo, away), "cd %s && git push gitlab %s" % (repo, LEAF)) is True
    assert BP.admitted(Ev(repo, away), "cd %s && git push gitlab %s" % (away, LEAF)) is False


def test_a_submodule_backup_push_is_admitted_only_to_its_own_pin(tmp_path):
    repo = _repo(tmp_path)
    sub = os.path.join(repo, "private", "renet")
    os.makedirs(sub)
    ident = ["-c", "user.email=t@t", "-c", "user.name=t"]

    def run(*argv: str) -> str:
        return subprocess.run(argv, check=True, capture_output=True, text=True).stdout.strip()

    run("git", "init", "-q", "-b", "main", sub)
    run("git", "-C", sub, *ident, "commit", "-q", "--allow-empty", "-m", "s")
    head = run("git", "-C", sub, "rev-parse", "HEAD")
    run("git", "-C", repo, "update-index", "--add", "--cacheinfo", "160000,%s,private/renet" % head)
    run("git", "-C", repo, *ident, "commit", "-q", "-m", "pin")
    hooks = BP.githooks()
    pin = "https://%s%s" % (hooks.MIRROR_HOST, hooks.BACKUP_PATHS["private/renet"])
    console_pin = "https://%s%s" % (hooks.MIRROR_HOST, hooks.BACKUP_PATHS[""])
    run("git", "-C", sub, "remote", "add", "gitlab", console_pin)
    cmd = "git -C private/renet push gitlab " + LEAF
    assert BP.admitted(Ev(repo), cmd) is False
    run("git", "-C", sub, "remote", "set-url", "gitlab", pin)
    assert BP.admitted(Ev(repo), cmd) is True
