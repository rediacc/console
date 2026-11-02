"""`wl_renettests`, the Stop hook's renet advisory (agent/plans/PLAN-renet-change-test-triggers.md, box M4): it names the exact test command when renet changed since the last receipt, and stays silent once a receipt covers the working files.

REAL REPOSITORIES: a console checkout whose `origin/main` pins renet commit A, a private/renet clone holding A, the map in `.ci/config/renet-test-map.json`, and receipts in a per-test `RENET_TEST_RECEIPT_DIR`. Each fire case has a silent twin differing by one planted fact.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TYPE_CHECKING

import wl_renettests as wr

if TYPE_CHECKING:
    import pathlib

MAP = {
    "schema": 1,
    "module": "github.com/rediacc/renet",
    "whole": [{"glob": "go.mod", "why": "the module graph reaches every package"}],
    "always": [{"package": "pkg/i18n", "why": "scans every source"}],
    "console": [
        {
            "glob": "packages/shared/schema.json",
            "why": "read by pkg/license",
            "packages": ["pkg/license"],
        }
    ],
    "retired": [{"glob": "pkg/gone/**", "why": "deleted"}],
    "outside": [{"glob": "tests/system/**", "why": "e2e"}],
    "entries": [
        {"glob": "cmd/renet/**", "packages": ["cmd/renet"], "dependents": []},
        {"glob": "pkg/i18n/**", "packages": ["pkg/i18n"], "dependents": []},
        {
            "glob": "pkg/license/**",
            "packages": ["pkg/license"],
            "dependents": ["cmd/renet"],
        },
    ],
}
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(cwd, *argv):
    out = subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env=dict(os.environ, **GIT_ENV),
    )
    return out.stdout.strip()


def _world(tmp_path: pathlib.Path):
    """(console root, renet path, receipt env)."""
    root = tmp_path / "console"
    renet = root / "private" / "renet"
    renet.mkdir(parents=True)
    _git(renet, "init", "-q", "--initial-branch=main")
    for rel, text in (
        ("go.mod", "module github.com/rediacc/renet\n"),
        ("pkg/license/store.go", "package license\n"),
        ("README.md", "renet\n"),
    ):
        (renet / rel).parent.mkdir(parents=True, exist_ok=True)
        (renet / rel).write_text(text, encoding="utf-8")
    _git(renet, "add", "-A")
    _git(renet, "commit", "-q", "-m", "A")
    _git(root, "init", "-q", "--initial-branch=main")
    (root / ".ci" / "config").mkdir(parents=True)
    (root / wr.MAP_REL).write_text(json.dumps(MAP), encoding="utf-8")
    (root / ".gitignore").write_text(".ci/cache/\n", encoding="utf-8")
    _git(root, "add", ".gitignore", wr.MAP_REL, "private/renet")
    _git(root, "commit", "-q", "-m", "seed")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    env = {"RENET_TEST_RECEIPT_DIR": str(tmp_path / "receipts")}
    return root, renet, env


def _receipt(env, tree, packages, every=False):
    d = wr.receipt_dir(env)
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema": 1,
        "renetTree": tree,
        "renetHead": "",
        "dirty": True,
        "all": every,
        "packages": packages,
        "consoleTrees": [],
        "base": "",
        "passed": 1,
        "finishedAt": "x",
    }
    (d / ("%s.json" % tree)).write_text(json.dumps(doc), encoding="utf-8")


def test_silent_when_renet_is_unchanged(tmp_path):
    root, _renet, env = _world(tmp_path)
    assert wr.advisory(root, env) is None


def test_fires_on_a_planted_untested_go_change_and_names_the_command(tmp_path):
    root, renet, env = _world(tmp_path)
    (renet / "pkg/license/store.go").write_text(
        "package license\n\nconst Planted = 1\n", encoding="utf-8"
    )
    text = wr.advisory(root, env)
    assert text is not None, "a renet Go change with no receipt raised no advisory"
    assert wr.COMMAND in text
    assert "3 package(s)" in text, text  # pkg/license, its dependent cmd/renet, the always pkg/i18n
    assert "no receipt" in text


def test_silent_after_a_receipt_covers_the_working_files(tmp_path):
    root, renet, env = _world(tmp_path)
    (renet / "pkg/license/store.go").write_text(
        "package license\n\nconst Planted = 1\n", encoding="utf-8"
    )
    tree, dirty = wr.working_tree(renet)
    assert tree
    assert dirty
    _receipt(env, tree, ["cmd/renet", "pkg/i18n", "pkg/license"])
    assert wr.advisory(root, env) is None
    # The throwaway index left the real one alone: the change is still unstaged.
    assert _git(renet, "diff", "--cached", "--name-only") == ""


def test_a_receipt_missing_a_dependent_still_fires_and_names_it(tmp_path):
    root, renet, env = _world(tmp_path)
    (renet / "pkg/license/store.go").write_text(
        "package license\n\nconst Planted = 1\n", encoding="utf-8"
    )
    tree, _ = wr.working_tree(renet)
    _receipt(env, tree, ["pkg/license", "pkg/i18n"])
    text = wr.advisory(root, env)
    assert text is not None
    assert "cmd/renet" in text


def test_a_receipt_for_another_tree_does_not_silence_it(tmp_path):
    root, renet, env = _world(tmp_path)
    old_tree, _ = wr.working_tree(renet)
    _receipt(env, old_tree, [], every=True)
    (renet / "pkg/license/store.go").write_text(
        "package license\n\nconst Planted = 1\n", encoding="utf-8"
    )
    assert wr.advisory(root, env) is not None


def test_silent_on_a_docs_only_renet_change(tmp_path):
    root, renet, env = _world(tmp_path)
    (renet / "README.md").write_text("renet, edited\n", encoding="utf-8")
    assert wr.advisory(root, env) is None


def test_an_unmapped_go_file_selects_every_package(tmp_path):
    root, renet, env = _world(tmp_path)
    (renet / "pkg/brandnew").mkdir()
    (renet / "pkg/brandnew/x.go").write_text("package brandnew\n", encoding="utf-8")
    text = wr.advisory(root, env)
    assert text is not None
    assert "every package" in text
    tree, _ = wr.working_tree(renet)
    _receipt(env, tree, ["cmd/renet", "pkg/i18n", "pkg/license"])
    assert "every package" in (wr.advisory(root, env) or ""), (
        "a partial receipt silenced an all-package selection"
    )
    _receipt(env, tree, [], every=True)
    assert wr.advisory(root, env) is None


def test_a_broken_world_is_silence_not_a_crash(tmp_path):
    assert wr.advisory(tmp_path / "nowhere", {"RENET_TEST_RECEIPT_DIR": str(tmp_path)}) is None


def test_a_console_only_change_fires_for_the_packages_that_read_it(tmp_path):
    root, renet, env = _world(tmp_path)
    assert wr.advisory(root, env) is None
    (root / "packages" / "shared").mkdir(parents=True)
    (root / "packages/shared/schema.json").write_text("{}\n", encoding="utf-8")
    text = wr.advisory(root, env)
    assert text is not None, "a console file renet tests read changed and nothing fired"
    assert "1 package(s)" in text, text  # pkg/license alone: no dependents, no always set
    tree, _ = wr.working_tree(renet)
    _receipt(env, tree, ["pkg/license"])
    assert wr.advisory(root, env) is None
    # Twin: a console file no row names stays silent.
    (root / "packages/shared/unrelated.json").write_text("{}\n", encoding="utf-8")
    assert wr.advisory(root, env) is None


def test_a_deleted_retired_package_selects_only_the_always_set(tmp_path):
    root, renet, env = _world(tmp_path)
    (renet / "pkg/gone").mkdir()
    (renet / "pkg/gone/x.go").write_text("package gone\n", encoding="utf-8")
    _git(renet, "add", "-A")
    _git(renet, "commit", "-q", "-m", "B")
    _git(root, "add", "private/renet")
    _git(root, "commit", "-q", "-m", "pin B")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    (renet / "pkg/gone/x.go").unlink()
    text = wr.advisory(root, env)
    assert text is not None
    assert "1 package(s)" in text, text  # pkg/i18n only; not every package
    assert "every package" not in text


def test_an_outside_go_path_selects_nothing(tmp_path):
    root, renet, env = _world(tmp_path)
    (renet / "tests/system").mkdir(parents=True)
    (renet / "tests/system/a_e2e_test.go").write_text("package system\n", encoding="utf-8")
    assert wr.advisory(root, env) is None


def test_an_unreadable_console_diff_selects_every_package_not_none(tmp_path, monkeypatch):
    """Review 22db9729.4: a failed console `git diff` is unknown, and unknown is every package, never "no console read rows"."""
    root, _renet, env = _world(tmp_path)
    (root / "packages" / "shared").mkdir(parents=True)
    (root / "packages/shared/schema.json").write_text("{}\n", encoding="utf-8")
    assert wr.console_changed_since(root) == ["packages/shared/schema.json"]
    real = wr._git

    def failing(cwd, *argv, **kw):
        if argv[:1] == ("diff",) and str(cwd) == str(root):
            return None
        return real(cwd, *argv, **kw)

    monkeypatch.setattr(wr, "_git", failing)
    assert wr.console_changed_since(root) is None
    text = wr.advisory(root, env)
    assert text is not None, "an unreadable console diff silenced the advisory"
    assert "every package" in text, text


def test_a_missing_merge_base_selects_every_package_not_none(tmp_path):
    """Review 28139d6b.5: with no origin/main the console merge-base is absent, which is unknown, and unknown is every package."""
    root, renet, env = _world(tmp_path)
    (renet / "README.md").write_text("renet changed\n", encoding="utf-8")
    assert wr.advisory(root, env) is None, "control: a docs-only change with origin/main present"
    _git(root, "update-ref", "-d", "refs/remotes/origin/main")
    assert wr.console_changed_since(root) is None
    text = wr.advisory(root, env)
    assert text is not None, "a missing merge-base silenced the advisory"
    assert "every package" in text, text
