"""The git-level `pre-commit` lint of the staged Python (`python_lint_pre_commit` in `.claude/rediacc_hooks/git/githooks.py`).

WHY IT EXISTS. 66f44dddd landed ruff I001 in `.ci/rediacc_ci/core/devbox.py` and I001 plus a format difference in `.ci/rediacc_ci/tests/test_core_devbox.py`; only `ci:quick`, about 25 minutes later, caught them, twice. The hook runs `ruff check` and `ruff format --check` on the commit's staged `.py` blobs.

WHAT IS PROVED, with REAL git and the REAL ruff in a throwaway repository whose `core.hooksPath` points at the hooks: an unsorted import and an unformatted file are refused naming the exact fix command; a clean file is admitted with the hook's own clean line; an unstaged bad edit over a clean staged blob is admitted, and an unstaged clean edit over a bad staged blob is refused (the commit's blobs decide, never the working tree); an import of an UNSTAGED first-party package sorts as first-party (the scratch tree mirrors the index's layout); an absent ruff fails open with a note; a commit with no staged `.py` never starts ruff; a ruff that errors is refused as UNCHECKED; a repository without a `[tool.ruff]` config is left alone.

THE CONTROL. Every case whose verdict depends on ruff having run also runs against a copy of the hooks whose `python_lint_pre_commit` is planted to return 0 at once, where it must FAIL. A case that passes against a hook that never lints proves nothing about the hook, which is why the admitted cases assert on the hook's clean line and not only on the exit code.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS_REL = ".claude/rediacc_hooks/git"
BRANCH = "0101-1"
LABEL = "python-lint pre-commit"
CLEAN = "clean under ruff check and ruff format"

PLANT_OLD = "def python_lint_pre_commit() -> int:\n"
PLANT_NEW = PLANT_OLD + "    return 0\n"

PYPROJECT = '[tool.ruff]\nline-length = 100\n\n[tool.ruff.lint]\nselect = ["I", "F"]\n'
UNSORTED = "import sys\nimport os\n\nprint(os, sys)\n"
SORTED = "import os\nimport sys\n\nprint(os, sys)\n"
UNFORMATTED = "x = ( 1 )\n"
# Three sections only when `pkg` is first-party: were the scratch tree to hold the staged file alone, ruff would class `pkg` as third-party, want it beside `requests`, and refuse this clean file with I001.
FIRST_PARTY_USER = (
    "import json\n\nimport requests\n\nimport pkg.mod\n\nprint(json, requests, pkg.mod)\n"
)


def _ruff() -> str:
    for candidate in (
        os.environ.get("RUFF_BIN") or "",
        str(REPO_ROOT / ".ci/cache/toolchain/uv-tools/bin/ruff"),
        shutil.which("ruff") or "",
    ):
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    pytest.fail("no ruff: set RUFF_BIN, run .ci/bootstrap.sh, or put ruff on PATH (CI installs it)")
    return ""


def _env(**extra: str) -> dict[str, str]:
    drop = {"COMMIT_POLICY_OK", "GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE", "RUFF_BIN"}
    env = {k: v for k, v in os.environ.items() if k not in drop}
    env.update(
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_SYSTEM="/dev/null",
        RUFF_BIN=_ruff(),
    )
    env.update(extra)
    return env


def _git(repo: pathlib.Path, *args: str, env: dict | None = None, check: bool = True):
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env or _env(),
        check=False,
        timeout=120,
    )
    if check and proc.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(args), proc.stderr.strip()))
    return proc


@pytest.fixture(scope="module")
def planted_hooks(tmp_path_factory) -> pathlib.Path:
    """A copy of the hooks whose lint returns 0 before it runs anything. The plant must apply exactly once."""
    dest = tmp_path_factory.mktemp("planted") / "git"
    shutil.copytree(REPO_ROOT / HOOKS_REL, dest, ignore=shutil.ignore_patterns("__pycache__"))
    target = dest / "githooks.py"
    text = target.read_text(encoding="utf-8")
    assert text.count(PLANT_OLD) == 1, "the never-lint plant no longer applies"
    target.write_text(text.replace(PLANT_OLD, PLANT_NEW), encoding="utf-8")
    return dest


class Repo:
    def __init__(self, base: pathlib.Path, hooks: pathlib.Path, pyproject: str = PYPROJECT):
        self.root = base / "repo"
        _git(base, "init", "-q", "-b", BRANCH, str(self.root))
        self.write("pyproject.toml", pyproject)
        self.write("pkg/__init__.py", "")
        self.write("pkg/mod.py", "VALUE = 1\n")
        self.write("a.txt", "a\n")
        _git(self.root, "add", "--", "pyproject.toml", "pkg", "a.txt")
        _git(self.root, "commit", "-q", "-m", "base", env=_env(COMMIT_POLICY_OK="1"))
        _git(self.root, "config", "core.hooksPath", str(hooks))
        self.msg = base / "msg"
        self.msg.write_text("test(fixture): python lint\n", encoding="utf-8")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def stage(self, *rels: str) -> None:
        _git(self.root, "add", "--", *rels)

    def commit(self, *paths: str, **extra: str) -> subprocess.CompletedProcess:
        """`git commit -F <msg> -- <paths>` (the pathspec form), or a plain commit of the index when no path is named."""
        tail = ["--", *paths] if paths else []
        return _git(self.root, "commit", "-F", str(self.msg), *tail, env=_env(**extra), check=False)


def _verdict(cond: bool, proc: subprocess.CompletedProcess) -> tuple[bool, str]:
    return cond, "rc=%d\nstderr:\n%s" % (proc.returncode, proc.stderr)


# Each case returns (passed, detail) instead of asserting, so the same case runs against the planted hooks and must FAIL there.


def case_unsorted_import_refused(base: pathlib.Path, hooks: pathlib.Path) -> tuple[bool, str]:
    r = Repo(base, hooks)
    r.write("pkg/bad.py", UNSORTED)
    r.stage("pkg/bad.py")
    proc = r.commit("pkg/bad.py")
    return _verdict(
        proc.returncode == 1
        and "I001" in proc.stderr
        and "check --fix -- pkg/bad.py" in proc.stderr
        and "git add -- pkg/bad.py" in proc.stderr,
        proc,
    )


def case_unformatted_refused(base: pathlib.Path, hooks: pathlib.Path) -> tuple[bool, str]:
    r = Repo(base, hooks)
    r.write("pkg/fmt.py", UNFORMATTED)
    r.stage("pkg/fmt.py")
    proc = r.commit("pkg/fmt.py")
    return _verdict(
        proc.returncode == 1
        and " format -- pkg/fmt.py" in proc.stderr
        and "check --fix" not in proc.stderr,
        proc,
    )


def case_clean_admitted(base: pathlib.Path, hooks: pathlib.Path) -> tuple[bool, str]:
    r = Repo(base, hooks)
    r.write("pkg/good.py", SORTED)
    r.stage("pkg/good.py")
    proc = r.commit("pkg/good.py")
    return _verdict(proc.returncode == 0 and "1 staged .py file(s) %s" % CLEAN in proc.stderr, proc)


def case_unstaged_bad_over_clean_blob_admitted(
    base: pathlib.Path, hooks: pathlib.Path
) -> tuple[bool, str]:
    r = Repo(base, hooks)
    r.write("pkg/good.py", SORTED)
    r.stage("pkg/good.py")
    r.write("pkg/good.py", UNSORTED + UNFORMATTED)
    proc = r.commit()
    return _verdict(proc.returncode == 0 and CLEAN in proc.stderr, proc)


def case_unstaged_clean_over_bad_blob_refused(
    base: pathlib.Path, hooks: pathlib.Path
) -> tuple[bool, str]:
    r = Repo(base, hooks)
    r.write("pkg/bad.py", UNSORTED)
    r.stage("pkg/bad.py")
    r.write("pkg/bad.py", SORTED)
    proc = r.commit()
    return _verdict(proc.returncode == 1 and "I001" in proc.stderr, proc)


def case_unstaged_first_party_package_sorts_first_party(
    base: pathlib.Path, hooks: pathlib.Path
) -> tuple[bool, str]:
    r = Repo(base, hooks)
    r.write("tool/user.py", FIRST_PARTY_USER)
    r.stage("tool/user.py")
    proc = r.commit("tool/user.py")
    return _verdict(proc.returncode == 0 and CLEAN in proc.stderr, proc)


def case_ruff_error_refused_unchecked(base: pathlib.Path, hooks: pathlib.Path) -> tuple[bool, str]:
    r = Repo(base, hooks)
    fake = base / "ruff-broken"
    fake.write_text("#!/bin/sh\necho 'ruff: config parse error' >&2\nexit 2\n", encoding="utf-8")
    fake.chmod(0o755)
    r.write("pkg/good.py", SORTED)
    r.stage("pkg/good.py")
    proc = r.commit("pkg/good.py", RUFF_BIN=str(fake))
    return _verdict(
        proc.returncode == 1
        and "UNCHECKED: `ruff check` exited 2" in proc.stderr
        and "config parse error" in proc.stderr,
        proc,
    )


CASES = [
    case_unsorted_import_refused,
    case_unformatted_refused,
    case_clean_admitted,
    case_unstaged_bad_over_clean_blob_admitted,
    case_unstaged_clean_over_bad_blob_refused,
    case_unstaged_first_party_package_sorts_first_party,
    case_ruff_error_refused_unchecked,
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.__name__.removeprefix("case_"))
def test_case_against_the_real_hook(tmp_path, case):
    ok, detail = case(tmp_path, REPO_ROOT / HOOKS_REL)
    assert ok, detail


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.__name__.removeprefix("case_"))
def test_case_fails_against_a_never_lint_hook(tmp_path, planted_hooks, case):
    ok, detail = case(tmp_path, planted_hooks)
    assert not ok, (
        "the case PASSED against a hook that never lints, so it cannot detect one:\n%s" % (detail)
    )


def test_an_absent_ruff_fails_open_with_a_note(tmp_path):
    r = Repo(tmp_path, REPO_ROOT / HOOKS_REL)
    r.write("pkg/bad.py", UNSORTED)
    r.stage("pkg/bad.py")
    proc = r.commit("pkg/bad.py", RUFF_BIN=str(tmp_path / "no-such-ruff"))
    assert proc.returncode == 0, proc.stderr
    assert "%s: ruff not found" % LABEL in proc.stderr, proc.stderr
    assert "1 staged .py file(s) NOT linted" in proc.stderr, proc.stderr


def _marker_ruff(tmp_path: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    marker = tmp_path / "ruff-ran"
    fake = tmp_path / "ruff-marker"
    fake.write_text("#!/bin/sh\ntouch '%s'\nexit 0\n" % marker, encoding="utf-8")
    fake.chmod(0o755)
    return fake, marker


def test_no_staged_python_never_starts_ruff(tmp_path):
    """The marker ruff writes a file when it runs: asserted by its ABSENCE, never by timing. Its positive control is the second commit."""
    r = Repo(tmp_path, REPO_ROOT / HOOKS_REL)
    fake, marker = _marker_ruff(tmp_path)
    r.write("a.txt", "b\n")
    proc = r.commit("a.txt", RUFF_BIN=str(fake))
    assert proc.returncode == 0, proc.stderr
    assert not marker.exists(), "ruff ran for a commit that stages no .py"
    assert LABEL not in proc.stderr, proc.stderr
    r.write("pkg/good.py", SORTED)
    r.stage("pkg/good.py")
    proc = r.commit("pkg/good.py", RUFF_BIN=str(fake))
    assert proc.returncode == 0, proc.stderr
    assert marker.exists(), "control: the marker ruff did not run for a staged .py"


def test_a_repository_without_a_ruff_config_is_left_alone(tmp_path):
    r = Repo(tmp_path, REPO_ROOT / HOOKS_REL, pyproject='[project]\nname = "x"\n')
    fake, marker = _marker_ruff(tmp_path)
    r.write("pkg/bad.py", UNSORTED)
    r.stage("pkg/bad.py")
    proc = r.commit("pkg/bad.py", RUFF_BIN=str(fake))
    assert proc.returncode == 0, proc.stderr
    assert not marker.exists(), "ruff ran in a repository with no [tool.ruff] config"
