"""The `commit-msg` Release-Note refusal (box RN2 of agent/plans/PLAN-release-notes.md): `githooks.release_note_refusal`.

Real `git commit` runs in a console fixture and in a `private/account` submodule fixture. Each repo's `core.hooksPath` holds one `commit-msg` that execs the live shim, so only this hook's commit-msg half runs, with the staged paths git hands it, as in the live repos.

THE CONTROL is the old hook: with a pass-through commit-msg hook the trailerless `feat:` commit lands (test_control_without_the_refusal_the_trailerless_commit_lands).
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SHIM = REPO_ROOT / ".claude" / "rediacc_hooks" / "git" / "commit-msg"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "protocol.file.allow",
    "GIT_CONFIG_VALUE_0": "always",
}
STRIP = ("COMMIT_POLICY_OK", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")
NOTE = "Release-Note: Backups now resume after a dropped connection"


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in STRIP}
    env.update(GIT_ENV)
    return env


def _git(cwd: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check, env=_env()
    )


def _hooked(repo: pathlib.Path, hooks: pathlib.Path, body: str | None = None) -> None:
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "commit-msg"
    hook.write_text(body or '#!/bin/sh\nexec python3 "%s" "$@"\n' % SHIM, encoding="utf-8")
    hook.chmod(0o755)
    _git(repo, "config", "core.hooksPath", str(hooks))


def _write(repo: pathlib.Path, rel: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    _git(repo, "add", "--", rel)


def _commit(repo: pathlib.Path, subject: str, *trailers: str) -> subprocess.CompletedProcess[str]:
    msg = subject + ("\n\n" + "\n".join(trailers) if trailers else "") + "\n"
    return _git(repo, "commit", "-q", "-m", msg, check=False)


def _seeded(path: pathlib.Path) -> pathlib.Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "0101-1")
    _git(path, "commit", "-q", "--allow-empty", "-m", "seed")
    return path


@pytest.fixture
def console(tmp_path):
    root = _seeded(tmp_path / "console")
    _hooked(root, tmp_path / "hooks-console")
    return root


@pytest.fixture
def submodule(tmp_path):
    """A console fixture holding `private/account` as a real submodule; returns (console, submodule)."""
    origin = _seeded(tmp_path / "origin")
    root = _seeded(tmp_path / "console")
    _git(root, "submodule", "add", "-q", str(origin), "private/account")
    _git(root, "commit", "-q", "-m", "chore: add the submodule")
    sub = root / "private" / "account"
    _hooked(sub, tmp_path / "hooks-account")
    _hooked(root, tmp_path / "hooks-console")
    return root, sub


def test_console_feat_on_a_customer_path_without_the_trailer_is_refused(console):
    _write(console, "packages/cli/src/x.ts")
    done = _commit(console, "feat(cli): resume backups")
    assert done.returncode != 0
    assert "Release-Note:" in done.stderr
    assert _git(console, "rev-list", "--count", "HEAD").stdout.strip() == "1"


def test_console_feat_with_the_trailer_commits(console):
    _write(console, "packages/cli/src/x.ts")
    done = _commit(console, "feat(cli): resume backups", NOTE)
    assert done.returncode == 0, done.stderr
    assert _git(console, "log", "-1", "--format=%s").stdout.strip() == "feat(cli): resume backups"


def test_console_bare_none_is_refused_and_none_with_a_reason_commits(console):
    _write(console, "packages/cli/src/x.ts")
    bad = _commit(console, "fix(cli): x", "Release-Note: none -- n/a")
    assert bad.returncode != 0
    assert "Release-Note" in bad.stderr
    good = _commit(
        console, "fix(cli): x", "Release-Note: none -- internal rename, no visible change"
    )
    assert good.returncode == 0, good.stderr


def test_console_exempt_commits_land_without_a_trailer(console):
    _write(console, "packages/cli/src/y.ts")
    assert _commit(console, "chore: tidy").returncode == 0
    _write(console, "agent/reviews/0101-1/clean.jsonl")
    assert _commit(console, "feat(reviews): a record commit").returncode == 0
    _write(console, ".github/workflows/x.yml")
    assert _commit(console, "fix(ci): a workflow").returncode == 0


def test_submodule_feat_without_the_trailer_is_refused_and_with_it_commits(submodule):
    _root, sub = submodule
    _write(sub, "src/billing.ts")
    done = _commit(sub, "feat(billing): invoices export")
    assert done.returncode != 0
    assert "Release-Note:" in done.stderr
    ok = _commit(sub, "feat(billing): invoices export", NOTE)
    assert ok.returncode == 0, ok.stderr


def test_submodule_test_paths_and_console_gitlink_bump_need_none(submodule):
    root, sub = submodule
    _write(sub, "tests/billing.test.ts")
    assert _commit(sub, "fix(billing): a test-only change").returncode == 0
    _git(root, "add", "--", "private/account")
    done = _commit(root, "feat(submodules): bump account")
    assert done.returncode == 0, done.stderr


def test_control_without_the_refusal_the_trailerless_commit_lands(console, tmp_path):
    """The old hook: the message refused above is admitted when the hook has no Release-Note branch."""
    _hooked(console, tmp_path / "hooks-old", "#!/bin/sh\nexit 0\n")
    _write(console, "packages/cli/src/x.ts")
    assert _commit(console, "feat(cli): resume backups").returncode == 0
