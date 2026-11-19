"""pytest_impact on a REAL repository: `select_for_tree`'s own fallbacks, and the leaf control through git (PLAN-ciquick-cpu W4.1).

test_pytest_impact.py drives `select` with a map built from a dict. That proves the decision; it does not prove the inputs reach it. Each FULL here starts from what the real tree can do wrong (no repository, no pyproject, no policy file, no push base, a config file or an uncovered file in the diff), and the control proves the same repository with a leaf edit narrows to its importer plus the smoke floor, so a function that always answered FULL fails it.
"""

import json
import pathlib
import subprocess

import pytest

from rediacc_ci import pytest_impact as pi

PYPROJECT = """[tool.pytest.ini_options]
testpaths = [".ci/rediacc_ci/tests"]
pythonpath = [".ci"]
"""
SMOKE = ".ci/rediacc_ci/tests/test_smoke.py"
FILES = {
    "pyproject.toml": PYPROJECT,
    ".gitignore": ".ci/cache/\n",
    ".ci/rediacc_ci/__init__.py": "",
    ".ci/rediacc_ci/leaf.py": "X = 1\n",
    ".ci/rediacc_ci/mid.py": "from rediacc_ci import leaf\n",
    ".ci/rediacc_ci/other.py": "Y = 2\n",
    ".ci/rediacc_ci/tests/__init__.py": "",
    ".ci/rediacc_ci/tests/conftest.py": "",
    ".ci/rediacc_ci/tests/test_mid.py": "from rediacc_ci import mid\n\ndef test_a():\n    assert mid\n",
    ".ci/rediacc_ci/tests/test_other.py": "from rediacc_ci import other\n\ndef test_b():\n    assert other\n",
    SMOKE: "def test_s():\n    assert True\n",
    pi.POLICY_RELPATH: json.dumps({"smoke": {"files": [SMOKE]}, "reads": {}}),
}
for _i in range(4):
    FILES[".ci/rediacc_ci/tests/test_filler%d.py" % _i] = "def test_f():\n    assert True\n"


def git(root: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.invalid")
    git(root, "config", "user.name", "t")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base", "--no-verify")
    # The push base: origin/main at the commit everything above is in.
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def test_control_a_leaf_edit_through_git_selects_its_importer_plus_smoke(repo):
    (repo / ".ci/rediacc_ci/leaf.py").write_text("X = 2\n", encoding="utf-8")
    sel = pi.select_for_tree(repo)
    assert sel.scope == "impact", sel.line()
    assert sel.files == [".ci/rediacc_ci/tests/test_mid.py", SMOKE], sel.files
    assert sel.why[".ci/rediacc_ci/tests/test_mid.py"] == "imports .ci/rediacc_ci/leaf.py"


def test_control_an_untouched_tree_selects_only_smoke(repo):
    sel = pi.select_for_tree(repo)
    assert sel.scope == "impact", sel.line()
    assert (repo / pi.CACHE_RELDIR / "map.json").is_file(), "the run wrote no map cache to leak"
    assert sel.files == [SMOKE], "the map cache under .ci/cache leaked into the change set"


def test_full_when_the_root_is_not_a_repository(tmp_path, monkeypatch):
    bare = tmp_path / "not-a-repo"
    bare.mkdir()
    # A temp directory under a checkout would let git find that repository above it.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    sel = pi.select_for_tree(bare)
    assert sel.scope == "full", sel.line()
    assert "git ls-files failed" in sel.reason


def test_full_when_the_map_cannot_be_built(repo):
    (repo / "pyproject.toml").unlink()
    sel = pi.select_for_tree(repo)
    assert sel.scope == "full", sel.line()
    assert sel.reason.startswith("missing map"), sel.line()


def test_full_when_the_policy_file_is_gone(repo):
    (repo / pi.POLICY_RELPATH).unlink()
    sel = pi.select_for_tree(repo)
    assert sel.scope == "full", sel.line()
    assert "pytest-impact.json" in sel.reason, sel.line()


def test_full_when_the_policy_file_is_malformed(repo):
    (repo / pi.POLICY_RELPATH).write_text("{", encoding="utf-8")
    sel = pi.select_for_tree(repo)
    assert sel.scope == "full", sel.line()
    assert "not valid JSON" in sel.reason, sel.line()


def test_full_when_no_push_base_resolves(repo):
    git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    sel = pi.select_for_tree(repo)
    assert sel.scope == "full", sel.line()
    assert "push base" in sel.reason, sel.line()


def test_full_when_a_named_base_does_not_resolve(repo):
    sel = pi.select_for_tree(repo, "no-such-ref")
    assert sel.scope == "full", sel.line()
    assert "push base" in sel.reason, sel.line()


def test_full_when_a_conftest_changes_through_git(repo):
    (repo / ".ci/rediacc_ci/tests/conftest.py").write_text("X = 1\n", encoding="utf-8")
    sel = pi.select_for_tree(repo)
    assert sel.line() == "pytest-impact: FULL (.ci/rediacc_ci/tests/conftest.py changed)"


def test_full_when_an_untracked_file_no_test_covers_appears(repo):
    (repo / ".ci/rediacc_ci/stray_data.json").write_text("{}", encoding="utf-8")
    sel = pi.select_for_tree(repo)
    assert sel.scope == "full", sel.line()
    assert ".ci/rediacc_ci/stray_data.json changed" in sel.reason, sel.line()


def test_full_when_a_committed_import_no_longer_resolves(repo):
    (repo / ".ci/rediacc_ci/mid.py").write_text("import rediacc_ci.gone\n", encoding="utf-8")
    git(repo, "commit", "-qam", "break", "--no-verify")
    sel = pi.select_for_tree(repo)
    assert sel.scope == "full", sel.line()
    assert "unresolved import" in sel.reason, sel.line()


def test_full_when_a_module_a_from_import_names_is_deleted(repo):
    """`from pkg import name` may name a symbol, so the map does not call it unresolved; the deletion itself is what forces the full run, as a changed file no closure holds any more."""
    (repo / ".ci/rediacc_ci/gone.py").write_text("Z = 1\n", encoding="utf-8")
    (repo / ".ci/rediacc_ci/mid.py").write_text("from rediacc_ci import gone\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "gone", "--no-verify")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    (repo / ".ci/rediacc_ci/gone.py").unlink()
    sel = pi.select_for_tree(repo)
    assert sel.scope == "full", sel.line()
    assert ".ci/rediacc_ci/gone.py changed" in sel.reason, sel.line()
