"""`rediacc_ci.drills.vm_check_trigger`: the path forms, the sides, the renet and account gitlink ranges, `push_base` against the cases of scripts/ci-runner/quick-select.ts, and the version 2 inputs digest.

Fixture repositories are real: a console repo with `private/renet` and `private/account` gitlinks (`git update-index --cacheinfo 160000`) over real nested repos. Nothing reads the live tree.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.drills import vm_check_trigger as trig

if TYPE_CHECKING:
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
        self.acc = root / "private" / "account"
        self.acc.mkdir(parents=True)
        _git(self.acc, "init", "-q", "-b", "main")
        _write(self.acc, "src/index.ts", "export {};\n")
        _write(self.acc, "README.md", "x\n")
        _git(self.acc, "add", "-A")
        _git(self.acc, "commit", "-q", "-m", "a0")
        self.base = self.commit_pointer("c0")

    def renet_commit(self, files: dict[str, str]) -> str:
        return self.sub_commit(self.sub, files)

    def account_commit(self, files: dict[str, str]) -> str:
        return self.sub_commit(self.acc, files)

    @staticmethod
    def sub_commit(sub: pathlib.Path, files: dict[str, str]) -> str:
        for rel, text in files.items():
            _write(sub, rel, text)
        _git(sub, "add", "-A")
        _git(sub, "commit", "-q", "-m", "r")
        return _git(sub, "rev-parse", "HEAD")

    def commit_pointer(self, msg: str) -> str:
        for name, sub in (("renet", self.sub), ("account", self.acc)):
            sha = _git(sub, "rev-parse", "HEAD")
            _git(self.root, "update-index", "--add", "--cacheinfo", f"160000,{sha},private/{name}")
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
        (".ci/rediacc_ci/drills/lib.py", True),
        (".ci/rediacc_ci/drills/license.py", True),
        (".ci/rediacc_ci/drills/universe.py", True),
        (".ci/rediacc_ci/drills/transfer.py", True),
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
        ("cmd/renet/sandbox.go", True),
        ("cmd/renet/other.go", True),
        ("pkg/sandbox/landlock.go", True),
        ("pkg/sandbox/landlock_test.go", False),
        ("pkg/sandbox/testdata/__tests__/x.go", False),
        ("pkg/x/testdata/y", False),
        ("pkg/license/x.go", True),
        ("pkg/embed/assets/x.bin", True),
        ("pkg/orchestration/compose.go", True),
        ("pkg/reporuntime/run.go", True),
        ("go.mod", True),
        ("go.sum", True),
        ("embed-assets.lock.json", True),
        ("sub/go.mod", False),
        ("README.md", False),
        ("build.sh", False),
        ("Makefile", False),
        ("Dockerfile", False),
        ("pkg", False),
        ("scripts/x.sh", False),
    ],
)
def test_renet_path_forms(path: str, hit: bool) -> None:
    assert trig.renet_hit(path) is hit


@pytest.mark.parametrize(
    ("path", "hit"),
    [
        ("src/index.ts", True),
        ("src/deep/a.ts", True),
        ("src/a.test.ts", False),
        ("src/a.spec.tsx", False),
        ("src/__tests__/a.ts", False),
        ("src/tests/a.ts", False),
        ("web/src/pages/a.tsx", True),
        ("web/e2e/a.ts", False),
        ("web/src/a.test.tsx", False),
        ("drizzle/0001.sql", True),
        ("scripts/seed.ts", True),
        ("package.json", True),
        ("package-lock.json", True),
        ("tsconfig.json", True),
        ("wrangler.toml", True),
        ("dev.defaults.env", True),
        ("docker-compose.yml", True),
        ("Dockerfile", True),
        ("tests/a.ts", False),
        ("e2e/a.ts", False),
        ("docs/a.md", False),
        ("README.md", False),
        ("test-results/a.json", False),
        (".claude/x.md", False),
        ("srcx/a.ts", False),
    ],
)
def test_account_path_forms(path: str, hit: bool) -> None:
    assert trig.account_hit(path) is hit


def test_console_sides_map_each_path_to_its_sides() -> None:
    assert trig.console_sides("packages/cli/src/remote/ssh.ts") == {trig.SIDE_RENET}
    assert trig.console_sides(".ci/rediacc_ci/drills/universe.py") == {trig.SIDE_ACCOUNT}
    assert trig.console_sides(".ci/rediacc_ci/drills/vm_check.py") == {
        trig.SIDE_RENET,
        trig.SIDE_ACCOUNT,
    }
    assert trig.console_sides("docs/a.md") == frozenset()
    assert trig.console_sides("packages/cli/src/remote/__tests__/a.ts") == frozenset()


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
    assert got.sides == {trig.SIDE_RENET}


def test_a_runner_change_gives_both_sides(world: World) -> None:
    _write(world.root, ".ci/rediacc_ci/drills/vm_check.py", "x = 1\n")
    _commit(world.root, "c1")
    assert world.changed().sides == {trig.SIDE_RENET, trig.SIDE_ACCOUNT}


def test_a_license_drill_change_gives_the_account_side_only(world: World) -> None:
    _write(world.root, ".ci/rediacc_ci/drills/license.py", "x = 1\n")
    _commit(world.root, "c1")
    got = world.changed()
    assert got.hits == (".ci/rediacc_ci/drills/license.py",)
    assert got.sides == {trig.SIDE_ACCOUNT}


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
    assert all(not c.endswith(("private/renet", "private/account")) for c in seen)
    assert got.sides == frozenset()


def test_pointer_move_over_sandbox_source_hits(world: World) -> None:
    world.renet_commit({"cmd/renet/sandbox_exec.go": "package main\n"})
    world.commit_pointer("bump")
    got = world.changed()
    assert got.hits == ("private/renet/cmd/renet/sandbox_exec.go",)
    assert got.unknown == ()
    assert got.sides == {trig.SIDE_RENET}


def test_pointer_move_over_wide_renet_source_hits(world: World) -> None:
    world.renet_commit({"pkg/license/x.go": "package license\n", "go.mod": "module x\n"})
    world.commit_pointer("bump")
    got = world.changed()
    assert got.hits == ("private/renet/go.mod", "private/renet/pkg/license/x.go")
    assert got.sides == {trig.SIDE_RENET}


def test_pointer_move_over_renet_testdata_and_docs_does_not_hit(world: World) -> None:
    world.renet_commit({"pkg/x/testdata/y": "d\n", "README.md": "r\n"})
    world.commit_pointer("bump")
    got = world.changed()
    assert not got.touched
    assert got.sides == frozenset()


def test_account_src_pointer_move_gives_the_account_side(world: World) -> None:
    world.account_commit({"src/index.ts": "export const a = 1;\n"})
    world.commit_pointer("bump")
    got = world.changed()
    assert got.hits == ("private/account/src/index.ts",)
    assert got.unknown == ()
    assert got.sides == {trig.SIDE_ACCOUNT}


def test_account_tests_only_pointer_move_gives_nothing(world: World) -> None:
    world.account_commit(
        {"tests/a.ts": "t\n", "src/a.test.ts": "t\n", "e2e/b.ts": "t\n", "docs/c.md": "d\n"}
    )
    world.commit_pointer("bump")
    got = world.changed()
    assert not got.touched
    assert got.sides == frozenset()


def test_both_submodules_moving_give_both_sides(world: World) -> None:
    world.renet_commit({"cmd/renet/a.go": "package main\n"})
    world.account_commit({"web/a.tsx": "x\n"})
    world.commit_pointer("bump")
    got = world.changed()
    assert got.hits == ("private/renet/cmd/renet/a.go", "private/account/web/a.tsx")
    assert got.sides == {trig.SIDE_RENET, trig.SIDE_ACCOUNT}


def test_pointer_move_over_tests_only_does_not_hit(world: World) -> None:
    world.renet_commit({"cmd/renet/sandbox_exec_test.go": "package main\n"})
    world.renet_commit({"pkg/sandbox/x_test.go": "package sandbox\n"})
    world.commit_pointer("bump")
    assert not world.changed().touched


def test_pointer_move_over_unwatched_source_does_not_hit(world: World) -> None:
    world.renet_commit({"scripts/other.sh": "echo changed\n", "build.sh": "x\n"})
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
    assert got.unknown[0].startswith(f"private/renet {ghost}: ")
    assert got.touched
    assert got.sides == {trig.SIDE_RENET}


def test_missing_old_account_gitlink_is_unknown_with_the_account_side(world: World) -> None:
    """The base has no private/account gitlink at all: unknown, and the account side, never a silent pass."""
    _git(world.root, "update-index", "--force-remove", "private/account")
    no_account_base = _commit(world.root, "no account")
    world.commit_pointer("account back")
    got = world.changed(base=no_account_base)
    assert got.hits == ()
    assert len(got.unknown) == 1
    assert got.unknown[0].startswith("private/account ")
    assert "no private/account gitlink" in got.unknown[0]
    assert got.touched
    assert got.sides == {trig.SIDE_ACCOUNT}


def test_missing_old_account_commit_names_the_account_sha(world: World) -> None:
    ghost = "2" * 40
    _git(world.root, "update-index", "--cacheinfo", f"160000,{ghost},private/account")
    ghost_base = _commit(world.root, "ghost")
    world.commit_pointer("back")
    got = world.changed(base=ghost_base)
    assert got.unknown[0].startswith(f"private/account {ghost}: ")
    assert got.sides == {trig.SIDE_ACCOUNT}


def test_submodule_not_checked_out_is_unknown(world: World) -> None:
    world.renet_commit({"pkg/sandbox/a.go": "package sandbox\n"})
    world.commit_pointer("bump")
    (world.sub / ".git").rename(world.sub / ".git-away")
    got = world.changed()
    assert got.unknown
    assert got.unknown[0].startswith("private/renet ")
    assert got.touched


def test_account_not_checked_out_is_unknown(world: World) -> None:
    world.account_commit({"src/a.ts": "x\n"})
    world.commit_pointer("bump")
    (world.acc / ".git").rename(world.acc / ".git-away")
    got = world.changed()
    assert got.unknown
    assert got.unknown[0].startswith("private/account ")
    assert got.sides == {trig.SIDE_ACCOUNT}


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


def test_worktree_mode_sees_a_dirty_account_file(world: World) -> None:
    assert not world.changed(mode="worktree").touched
    _write(world.acc, "src/index.ts", "export const dirty = 1;\n")
    got = world.changed(mode="worktree")
    assert got.hits == ("private/account/src/index.ts",)
    assert got.sides == {trig.SIDE_ACCOUNT}


def test_worktree_mode_sees_an_untracked_account_file_but_not_a_test(world: World) -> None:
    _write(world.acc, "tests/new.ts", "t\n")
    assert not world.changed(mode="worktree").touched
    _write(world.acc, "web/new.tsx", "x\n")
    assert world.changed(mode="worktree").hits == ("private/account/web/new.tsx",)


def test_worktree_mode_sees_a_new_renet_commit_not_yet_bumped(world: World) -> None:
    world.renet_commit({"pkg/reporuntime/a.go": "package reporuntime\n"})
    got = world.changed(mode="worktree")
    assert got.hits == ("private/renet/pkg/reporuntime/a.go",)


def test_failed_console_diff_is_unknown(world: World) -> None:
    got = trig.changed_paths(world.root, "no-such-ref", "push")
    assert got.unknown
    assert got.touched
    assert got.sides == {trig.SIDE_RENET, trig.SIDE_ACCOUNT}


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


def test_digest_changes_with_only_the_account_pointer(world: World) -> None:
    before = trig.inputs(world.root, _tree(world))
    world.account_commit({"src/index.ts": "export const moved = 1;\n"})
    world.commit_pointer("bump account")
    assert trig.inputs(world.root, _tree(world)) != before


def test_digest_pointers_are_not_interchangeable() -> None:
    """The same sha under the renet slot and under the account slot must not collide."""
    assert trig._digest([], "a" * 40, "") != trig._digest([], "", "a" * 40)


def test_a_version_1_digest_never_equals_a_version_2_one() -> None:
    lines = ["100644 blob " + "a" * 40 + "\tpackages/cli/src/remote/a.ts"]
    v1_body = "\n".join(sorted(lines)) + f"\nprivate/renet {'b' * 40}\n"
    v1 = hashlib.sha256(v1_body.encode()).hexdigest()
    assert trig._digest(lines, "b" * 40, "") != v1
    assert trig._digest([], "", "") != hashlib.sha256(b"\nprivate/renet none\n").hexdigest()


def test_worktree_digest_follows_the_account_head(world: World) -> None:
    before = trig.inputs(world.root)
    world.account_commit({"src/index.ts": "export const moved = 1;\n"})
    assert trig.inputs(world.root) != before
    world.commit_pointer("bump account")
    assert trig.inputs(world.root) == trig.inputs(world.root, _tree(world))


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
    (world.acc / ".git").rename(world.acc / ".git-away")
    assert trig.inputs(world.root) == trig._digest([], "", "")
    assert not world.changed(mode="worktree").touched


# ------------------------------------------------------------------ account_modified and account_worktree_digest


def test_account_modified_is_false_on_a_clean_checkout(world: World) -> None:
    assert trig.account_modified(world.root) is False


def test_account_modified_sees_a_dirty_or_untracked_trigger_file(world: World) -> None:
    _write(world.acc, "src/index.ts", "export const dirty = 1;\n")
    assert trig.account_modified(world.root) is True


def test_account_modified_sees_an_untracked_trigger_file(world: World) -> None:
    _write(world.acc, "web/new.tsx", "x\n")
    assert trig.account_modified(world.root) is True


def test_account_modified_ignores_test_and_doc_edits(world: World) -> None:
    _write(world.acc, "tests/a.ts", "t\n")
    _write(world.acc, "src/a.test.ts", "t\n")
    _write(world.acc, "README.md", "changed\n")
    assert trig.account_modified(world.root) is False


def test_account_modified_is_none_when_unreadable(world: World) -> None:
    (world.acc / ".git").rename(world.acc / ".git-away")
    assert trig.account_modified(world.root) is None
    assert trig.account_worktree_digest(world.root) is None


def test_account_worktree_digest_moves_with_a_trigger_edit_only(world: World) -> None:
    clean = trig.account_worktree_digest(world.root)
    assert clean is not None
    _write(world.acc, "tests/a.ts", "t\n")
    _write(world.acc, "README.md", "changed\n")
    assert trig.account_worktree_digest(world.root) == clean
    _write(world.acc, "src/index.ts", "export const one = 1;\n")
    one = trig.account_worktree_digest(world.root)
    assert one not in (None, clean)
    _write(world.acc, "src/index.ts", "export const two = 2;\n")
    assert trig.account_worktree_digest(world.root) not in (None, clean, one)


def test_account_worktree_digest_sees_untracked_and_deleted_files(world: World) -> None:
    clean = trig.account_worktree_digest(world.root)
    _write(world.acc, "web/new.tsx", "x\n")
    added = trig.account_worktree_digest(world.root)
    assert added != clean
    (world.acc / "src/index.ts").unlink()
    assert trig.account_worktree_digest(world.root) not in (clean, added)


def test_account_worktree_digest_is_stable_across_calls(world: World) -> None:
    _write(world.acc, "src/index.ts", "export const one = 1;\n")
    assert trig.account_worktree_digest(world.root) == trig.account_worktree_digest(world.root)


def test_every_drill_module_vm_check_runs_is_a_trigger() -> None:
    """A change to a drill module that vm:check runs needs a vm:check receipt: upgrade_converge.py (U1) and tenant_isolation.py (I1) were missing from the map, so a push touching only them required none (found by the DR writer, 2026-10-24). Every drills/*.py that vm_check.py imports must charge a side."""
    drills = pathlib.Path(trig.__file__).resolve().parent
    tree = ast.parse((drills / "vm_check.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith("drills"):
            imported.update(alias.name for alias in node.names)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("rediacc_ci.drills.")
        ):
            imported.add(node.module.rsplit(".", 1)[1])
    for name in sorted(imported):
        # The receipt and trigger modules judge a run; they change nothing on a VM, so they charge no side by design.
        if (drills / ("%s.py" % name)).is_file() and name not in (
            "vm_check_trigger",
            "vm_check_receipt",
        ):
            path = ".ci/rediacc_ci/drills/%s.py" % name
            assert trig.console_sides(path), "%s is run by vm:check but charges no side" % path
