"""`rediacc_ci.drills.vm_check_trigger`: the path forms, the renet gitlink range, `push_base` against the cases of scripts/ci-runner/quick-select.ts, and the inputs digest.

Fixture repositories are real: a console repo with a `private/renet` gitlink (`git update-index --cacheinfo 160000`) over a real nested renet repo. Nothing reads the live tree.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.drills import vm_check_trigger as trig

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Sequence

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
    "HOME": "/nonexistent",
}


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=ENV
    ).stdout.strip()


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _commit(root: pathlib.Path, msg: str) -> str:
    _git(root, "add", "-A", "--", ".", ":!private")
    _git(root, "commit", "-q", "--allow-empty", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


class World:
    """A console repo whose private/renet is a nested repo, with the gitlink recorded by hand."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        root.mkdir()
        _git(root, "init", "-q", "-b", "main")
        _write(root, "README.md", "x\n")
        self.sub = root / "private" / "renet"
        self.sub.mkdir(parents=True)
        _git(self.sub, "init", "-q", "-b", "main")
        _write(self.sub, "cmd/renet/other.go", "package main\n")
        _git(self.sub, "add", "-A")
        _git(self.sub, "commit", "-q", "-m", "r0")
        self.base = self.commit_pointer("c0")

    def renet_commit(self, files: dict[str, str]) -> str:
        for rel, text in files.items():
            _write(self.sub, rel, text)
        _git(self.sub, "add", "-A")
        _git(self.sub, "commit", "-q", "-m", "r")
        return _git(self.sub, "rev-parse", "HEAD")

    def commit_pointer(self, msg: str) -> str:
        sha = _git(self.sub, "rev-parse", "HEAD")
        _git(self.root, "update-index", "--add", "--cacheinfo", f"160000,{sha},private/renet")
        return _commit(self.root, msg)

    def changed(self, mode: trig.Mode = "push", base: str | None = None) -> trig.Changed:
        return trig.changed_paths(self.root, base or self.base, mode)


@pytest.fixture
def world(tmp_path: pathlib.Path) -> World:
    return World(tmp_path / "console")


# ------------------------------------------------------------------ path forms


@pytest.mark.parametrize(
    ("path", "hit"),
    [
        ("packages/cli/src/remote/ssh.ts", True),
        ("packages/cli/src/remote/msys2/setup.ts", True),
        ("packages/cli/src/remote/__tests__/ssh.test.ts", False),
        ("packages/cli/src/remote-extra/ssh.ts", False),
        ("packages/cli/src/remotely.ts", False),
        ("packages/cli/src/services/repo/repo-key-deployment.ts", True),
        ("packages/cli/src/services/repo/repo-key-deployment.test.ts", False),
        ("packages/cli/src/services/repo/repo-key-deployment.ts.bak", False),
        (".ci/rediacc_ci/drills/vm_check.py", True),
        (".ci/rediacc_ci/drills/vm_check_trigger.py", False),
        ("docs/readme.md", False),
    ],
)
def test_console_path_forms(path: str, hit: bool) -> None:
    assert trig.console_hit(path) is hit


@pytest.mark.parametrize(
    ("path", "hit"),
    [
        ("cmd/renet/sandbox_exec.go", True),
        ("cmd/renet/sandbox_exec_test.go", False),
        ("cmd/renet/sandbox.go", False),
        ("cmd/renet/sandboxed_exec.go", False),
        ("cmd/renet/other.go", False),
        ("pkg/sandbox/landlock.go", True),
        ("pkg/sandbox/landlock_test.go", False),
        ("pkg/sandbox/testdata/__tests__/x.go", False),
        ("pkg/sandboxes/x.go", False),
        ("pkg/orchestration/compose.go", True),
        ("pkg/reporuntime/run.go", True),
        ("pkg/reporuntime", False),
    ],
)
def test_renet_path_forms(path: str, hit: bool) -> None:
    assert trig.renet_hit(path) is hit


def test_underscore_entry_is_a_filename_prefix_not_a_directory() -> None:
    assert trig.watched("cmd/renet/sandbox_a", ("cmd/renet/sandbox_",))
    assert not trig.watched("cmd/renet/sandbox", ("cmd/renet/sandbox_",))
    assert not trig.watched("cmd/renet/sandbox_a", ("cmd/renet/sandbox_a/",))


# ------------------------------------------------------------------ changed_paths


def test_console_change_in_push_mode(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/ssh.ts", "a\n")
    _write(world.root, "docs/a.md", "a\n")
    _commit(world.root, "c1")
    got = world.changed()
    assert got.hits == ("packages/cli/src/remote/ssh.ts",)
    assert got.unknown == ()


def test_docs_only_push_is_untouched_and_does_no_submodule_work(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(world.root, "docs/a.md", "a\n")
    _commit(world.root, "c1")
    seen: list[str] = []
    real = trig.make_git

    def spy(cwd: pathlib.Path) -> Callable[[Sequence[str]], str | None]:
        seen.append(str(cwd))
        return real(cwd)

    monkeypatch.setattr(trig, "make_git", spy)
    got = world.changed()
    assert not got.touched
    assert seen
    assert all(not c.endswith("private/renet") for c in seen)


def test_pointer_move_over_sandbox_source_hits(world: World) -> None:
    world.renet_commit({"cmd/renet/sandbox_exec.go": "package main\n"})
    world.commit_pointer("bump")
    got = world.changed()
    assert got.hits == ("private/renet/cmd/renet/sandbox_exec.go",)
    assert got.unknown == ()


def test_pointer_move_over_tests_only_does_not_hit(world: World) -> None:
    world.renet_commit({"cmd/renet/sandbox_exec_test.go": "package main\n"})
    world.renet_commit({"pkg/sandbox/x_test.go": "package sandbox\n"})
    world.commit_pointer("bump")
    assert not world.changed().touched


def test_pointer_move_over_unwatched_source_does_not_hit(world: World) -> None:
    world.renet_commit({"cmd/renet/other.go": "package main // changed\n"})
    world.commit_pointer("bump")
    assert not world.changed().touched


def test_missing_old_gitlink_object_is_unknown_with_the_sha(world: World) -> None:
    world.renet_commit({"pkg/sandbox/a.go": "package sandbox\n"})
    world.commit_pointer("bump")
    ghost = "1" * 40
    _git(world.root, "update-index", "--cacheinfo", f"160000,{ghost},private/renet")
    ghost_base = _commit(world.root, "ghost")
    world.commit_pointer("back")
    got = world.changed(base=ghost_base)
    assert got.hits == ()
    assert len(got.unknown) == 1
    assert got.unknown[0].startswith(ghost)
    assert got.touched


def test_submodule_not_checked_out_is_unknown(world: World) -> None:
    world.renet_commit({"pkg/sandbox/a.go": "package sandbox\n"})
    world.commit_pointer("bump")
    (world.sub / ".git").rename(world.sub / ".git-away")
    got = world.changed()
    assert got.unknown
    assert got.touched


def test_worktree_mode_reads_tracked_edits_and_untracked_files(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/new.ts", "a\n")
    _write(world.root, "docs/b.md", "b\n")
    got = world.changed(mode="worktree")
    assert got.hits == ("packages/cli/src/remote/new.ts",)
    _commit(world.root, "c1")
    _write(world.root, "packages/cli/src/remote/new.ts", "edited\n")
    assert world.changed(mode="worktree", base=world.base).hits == (
        "packages/cli/src/remote/new.ts",
    )


def test_worktree_mode_sees_renet_worktree_edits(world: World) -> None:
    assert not world.changed(mode="worktree").touched
    _write(world.sub, "pkg/sandbox/dirty.go", "package sandbox\n")
    got = world.changed(mode="worktree")
    assert got.hits == ("private/renet/pkg/sandbox/dirty.go",)


def test_worktree_mode_sees_a_new_renet_commit_not_yet_bumped(world: World) -> None:
    world.renet_commit({"pkg/reporuntime/a.go": "package reporuntime\n"})
    got = world.changed(mode="worktree")
    assert got.hits == ("private/renet/pkg/reporuntime/a.go",)


def test_failed_console_diff_is_unknown(world: World) -> None:
    got = trig.changed_paths(world.root, "no-such-ref", "push")
    assert got.unknown
    assert got.touched


# ------------------------------------------------------------------ push_base (scripts/ci-runner/quick-select.ts:445-490)


def _answers(ok: dict[str, str]) -> Callable[[Sequence[str]], str | None]:
    """The fake runner of quick-select.ts: `ok` maps a ref to its sha, `name:<ref>` to its abbreviated name."""

    def git(args: Sequence[str]) -> str | None:
        if args[0] == "rev-parse" and args[1] == "--verify":
            return ok.get(args[3].replace("^{commit}", ""))
        if args[0] == "merge-base":
            return None if args[2] not in ok else f"mb-{args[2]}"
        if args[0] == "rev-parse" and args[1] == "--abbrev-ref":
            return ok.get(f"name:{args[2]}", "origin/b")
        return None

    return git


def test_push_wins_when_it_resolves() -> None:
    got = trig.push_base(_answers({"@{push}": "x", "origin/main": "y"}), "b")
    assert got.via == "@{push}"


def test_falls_back_to_origin_main() -> None:
    got = trig.push_base(_answers({"origin/main": "y"}), "b")
    assert got.merge_base == "mb-origin/main"


def test_foreign_upstream_loses_to_origin_branch_with_a_warning() -> None:
    got = trig.push_base(
        _answers(
            {
                "@{upstream}": "x",
                "name:@{upstream}": "origin/0930-1",
                "origin/b": "z",
                "origin/main": "y",
            }
        ),
        "b",
    )
    assert got.via == "origin/<branch>"
    assert any("origin/0930-1" in w for w in got.warnings)


def test_foreign_upstream_without_origin_branch_falls_to_main_with_the_warning() -> None:
    got = trig.push_base(
        _answers({"@{upstream}": "x", "name:@{upstream}": "origin/0930-1", "origin/main": "y"}),
        "b",
    )
    assert got.ref == "origin/main"
    assert any("origin/0930-1" in w for w in got.warnings)


def test_own_upstream_wins_with_no_warning() -> None:
    got = trig.push_base(
        _answers({"@{upstream}": "x", "name:@{upstream}": "origin/b", "origin/main": "y"}), "b"
    )
    assert got.via == "@{upstream}"
    assert got.warnings == ()


def test_nothing_resolvable_names_all_four_refs() -> None:
    got = trig.push_base(_answers({}), "b")
    assert got.merge_base is None
    assert len(got.tried) == 4


def test_push_base_against_a_real_repository(world: World, tmp_path: pathlib.Path) -> None:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=ENV)
    _git(world.root, "remote", "add", "origin", str(bare))
    _git(world.root, "push", "-q", "origin", "main")
    _git(world.root, "checkout", "-q", "-b", "feat")
    _write(world.root, "docs/a.md", "a\n")
    tip = _commit(world.root, "c1")
    got = trig.push_base(trig.make_git(world.root), "feat")
    assert got.ref == "origin/main"
    assert got.merge_base == world.base
    assert got.merge_base != tip


# ------------------------------------------------------------------ inputs digest


def _tree(world: World) -> str:
    return _git(world.root, "rev-parse", "HEAD^{tree}")


def test_digest_survives_a_docs_only_commit(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/a.ts", "a\n")
    _commit(world.root, "c1")
    before = trig.inputs(world.root, _tree(world))
    _write(world.root, "docs/a.md", "docs\n")
    _commit(world.root, "c2")
    assert before is not None
    assert trig.inputs(world.root, _tree(world)) == before


def test_digest_changes_with_a_trigger_blob(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/a.ts", "a\n")
    _commit(world.root, "c1")
    before = trig.inputs(world.root, _tree(world))
    _write(world.root, "packages/cli/src/remote/a.ts", "b\n")
    _commit(world.root, "c2")
    assert trig.inputs(world.root, _tree(world)) != before


def test_digest_changes_with_the_renet_pointer(world: World) -> None:
    before = trig.inputs(world.root, _tree(world))
    world.renet_commit({"cmd/renet/other.go": "package main // moved\n"})
    world.commit_pointer("bump")
    assert trig.inputs(world.root, _tree(world)) != before


def test_digest_ignores_excluded_trigger_files(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/a.ts", "a\n")
    _commit(world.root, "c1")
    before = trig.inputs(world.root, _tree(world))
    _write(world.root, "packages/cli/src/remote/__tests__/a.test.ts", "t\n")
    _commit(world.root, "c2")
    assert trig.inputs(world.root, _tree(world)) == before


def test_worktree_digest_equals_the_tree_digest_of_the_same_state(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/a.ts", "a\n")
    _write(world.root, ".ci/rediacc_ci/drills/vm_check.py", "x = 1\n")
    _commit(world.root, "c1")
    assert trig.inputs(world.root) == trig.inputs(world.root, _tree(world))
    _write(world.root, "packages/cli/src/remote/a.ts", "edited\n")
    assert trig.inputs(world.root) != trig.inputs(world.root, _tree(world))
    _commit(world.root, "c2")
    assert trig.inputs(world.root) == trig.inputs(world.root, _tree(world))


def test_unreadable_tree_has_no_digest(world: World) -> None:
    assert trig.inputs(world.root, "f" * 40) is None


def test_a_watched_renet_file_moved_out_of_the_trigger_still_hits(world: World) -> None:
    """A rename is a deletion of the watched path: with rename detection on, the diff names only the new, unwatched path and the move would pass unchecked."""
    world.renet_commit({"pkg/sandbox/a.go": "package sandbox\n// body\n"})
    base = world.commit_pointer("watched file in place")
    (world.sub / "pkg/other").mkdir(parents=True, exist_ok=True)
    _git(world.sub, "mv", "pkg/sandbox/a.go", "pkg/other/a.go")
    _git(world.sub, "commit", "-q", "-m", "move")
    world.commit_pointer("move out")
    got = world.changed(base=base)
    assert "private/renet/pkg/sandbox/a.go" in got.hits


def test_a_watched_console_file_moved_out_of_the_trigger_still_hits(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/sync/x.ts", "export const x = 1;\n// body\n")
    base = _commit(world.root, "watched console file")
    (world.root / "packages/cli/src/moved").mkdir(parents=True)
    _git(world.root, "mv", "packages/cli/src/remote/sync/x.ts", "packages/cli/src/moved/x.ts")
    _commit(world.root, "move out")
    got = world.changed(base=base)
    assert "packages/cli/src/remote/sync/x.ts" in got.hits


def test_non_ascii_watched_path_is_not_quoted_away(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/é.ts", "a\n")
    assert world.changed(mode="worktree").hits == ("packages/cli/src/remote/é.ts",)
    _commit(world.root, "c1")
    assert world.changed().hits == ("packages/cli/src/remote/é.ts",)
    assert trig.inputs(world.root, _tree(world)) == trig.inputs(world.root)


def test_a_watched_path_with_quote_or_tab_is_not_quoted_away(world: World) -> None:
    name = 'packages/cli/src/remote/a"b\tc.ts'
    _write(world.root, name, "a\n")
    assert world.changed(mode="worktree").hits == (name,)
    _commit(world.root, "c1")
    assert world.changed().hits == (name,)
    assert trig.inputs(world.root, _tree(world)) == trig.inputs(world.root)


def test_directory_without_its_own_repository_has_no_pointer(world: World) -> None:
    (world.sub / ".git").rename(world.sub / ".git-away")
    assert trig.inputs(world.root) == trig._digest([], "")
    assert not world.changed(mode="worktree").touched
