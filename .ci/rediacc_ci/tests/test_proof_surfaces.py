"""`rediacc_ci.proof.surfaces`, the vm:check trigger and the surface map: the map loader, the path forms, the VM sides and the surfaces, the renet and account gitlink ranges, `push_base` against the cases of scripts/ci-runner/quick-select.ts, the version 3 inputs digest, and the renet build identity.

Fixture repositories are real: a console repo with `private/renet` and `private/account` gitlinks (`git update-index --cacheinfo 160000`) over real nested repos. Two tests read the live tree on purpose: the drill reach test and the Owns parity test over the plan census, because what they pin is the real map against the real files.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.proof import surfaces as trig

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
        (".ci/rediacc_ci/proof/surfaces.py", False),
        (".ci/rediacc_ci/proof/vm_tier.py", False),
        ("packages/cli/src/commands/repo.ts", False),
        ("packages/shared/src/x.ts", True),
        ("packages/cli/src/remote/README.md", False),
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
        ("build.sh", True),
        ("proxy/docker-compose.yml", True),
        ("proxy/README.md", False),
        ("pkg/locking/README.md", False),
        ("Makefile", False),
        ("Dockerfile", False),
        ("pkg", False),
        ("scripts/x.sh", False),
    ],
)
def test_renet_path_forms(path: str, hit: bool) -> None:
    assert trig.submodule_hit(trig.RENET_SUBMODULE, path) is hit


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
        ("wrangler.bench.toml", True),
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
    assert trig.submodule_hit(trig.ACCOUNT_SUBMODULE, path) is hit


def test_console_sides_map_each_path_to_its_sides() -> None:
    assert trig.console_sides("packages/cli/src/remote/ssh.ts") == {trig.SIDE_RENET}
    assert trig.console_sides(".ci/rediacc_ci/drills/universe.py") == {trig.SIDE_ACCOUNT}
    assert trig.console_sides(".ci/rediacc_ci/drills/vm_check.py") == {
        trig.SIDE_RENET,
        trig.SIDE_ACCOUNT,
    }
    assert trig.console_sides("docs/a.md") == frozenset()
    assert trig.console_sides("packages/cli/src/remote/__tests__/a.ts") == frozenset()


def test_glob_grammar_is_the_owns_grammar() -> None:
    """`**` spans segments, `*` stays inside one, and a literal is exact: the former `/` and `_` prefix forms are gone with the tables."""
    assert trig.matches("private/renet/cmd/renet/sandbox_a.go", ("private/renet/cmd/**",))
    assert trig.matches("private/account/wrangler.bench.toml", ("private/account/wrangler*.toml",))
    assert not trig.matches("private/account/x/wrangler.toml", ("private/account/wrangler*.toml",))
    assert not trig.matches("private/renet/build.sh.bak", ("private/renet/build.sh",))
    assert not trig.matches("private/renet/cmdx/a.go", ("private/renet/cmd/**",))


# ------------------------------------------------------------------ changed_paths


def test_console_change_in_push_mode(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/ssh.ts", "a\n")
    _write(world.root, "docs/a.md", "a\n")
    _commit(world.root, "c1")
    got = world.changed()
    assert got.hits == ("packages/cli/src/remote/ssh.ts",)
    assert got.unknown == ()
    assert got.sides == {trig.SIDE_RENET}
    assert got.surfaces == {"cli", "cli-remote"}


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
    world.renet_commit({"scripts/other.sh": "echo changed\n", "Dockerfile": "x\n"})
    world.commit_pointer("bump")
    got = world.changed()
    assert not got.touched
    assert got.surfaces == frozenset()


@pytest.mark.parametrize("rel", ["proxy/docker-compose.yml", "build.sh"])
def test_a_renet_proxy_or_build_script_move_hits_the_renet_side(world: World, rel: str) -> None:
    """build.sh embeds proxy/docker-compose.yml into the binary through a gitignored copy, so a Traefik pin bump changes what deploys; the former RENET_PATHS (cmd/, pkg/, go.mod, go.sum, embed-assets.lock.json) missed both."""
    world.renet_commit({rel: "changed\n"})
    world.commit_pointer("bump")
    got = world.changed()
    assert got.hits == (f"private/renet/{rel}",)
    assert got.sides == {trig.SIDE_RENET}
    assert got.surfaces == {"renet"}


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


def _pointers(renet: str, account: str) -> dict[str, str]:
    return {trig.RENET_SUBMODULE: renet, trig.ACCOUNT_SUBMODULE: account}


def test_digest_pointers_are_not_interchangeable() -> None:
    """The same sha under the renet slot and under the account slot must not collide."""
    assert trig._digest([], _pointers("a" * 40, "")) != trig._digest([], _pointers("", "a" * 40))


def test_a_version_1_digest_never_equals_a_version_3_one() -> None:
    lines = ["100644 blob " + "a" * 40 + "\tpackages/cli/src/remote/a.ts"]
    v1_body = "\n".join(sorted(lines)) + f"\nprivate/renet {'b' * 40}\n"
    v1 = hashlib.sha256(v1_body.encode()).hexdigest()
    assert trig._digest(lines, _pointers("b" * 40, "")) != v1
    empty = trig._digest([], _pointers("", ""))
    assert empty != hashlib.sha256(b"\nprivate/renet none\n").hexdigest()


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
    assert trig.inputs(world.root) == trig._digest([], _pointers("", ""))
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


def _drill_imports(source: pathlib.Path, drills: pathlib.Path) -> set[str]:
    """The drills/*.py module names `source` imports, in every spelling: `from rediacc_ci.drills import x`, `from rediacc_ci.drills.x import y`, `import rediacc_ci.drills.x`, and the relative forms `from . import x` and `from .x import y`."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("rediacc_ci.drills."):
                    found.add(alias.name.split(".")[2])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 1 or module == "rediacc_ci.drills":
                if module in ("", "rediacc_ci.drills"):
                    found.update(alias.name for alias in node.names)
                else:
                    found.add(module.split(".")[0])
            elif module.startswith("rediacc_ci.drills."):
                found.add(module.split(".")[2])
    return {name for name in found if (drills / ("%s.py" % name)).is_file()}


def test_every_drill_module_vm_check_runs_is_a_trigger() -> None:
    """A change to a drill module that vm:check runs needs a vm:check receipt: upgrade_converge.py (U1) and tenant_isolation.py (I1) were missing from the map, so a push touching only them required none (found by the DR writer, 2026-10-24). Every drills/*.py that vm_check.py reaches, directly or through another drill module, must charge a side."""
    drills = pathlib.Path(trig.__file__).resolve().parent.parent / "drills"
    reached: set[str] = set()
    queue = sorted(_drill_imports(drills / "vm_check.py", drills))
    while queue:
        name = queue.pop()
        if name in reached:
            continue
        reached.add(name)
        queue.extend(_drill_imports(drills / ("%s.py" % name), drills))
    assert "upgrade_converge" in reached, reached
    assert "wire" in reached, reached
    for name in sorted(reached):
        path = ".ci/rediacc_ci/drills/%s.py" % name
        assert trig.console_sides(path), "%s is run by vm:check but charges no side" % path


def test_drill_imports_reads_absolute_relative_and_plain_import_spellings(
    tmp_path: pathlib.Path,
) -> None:
    for name in ("a", "b", "c", "d"):
        (tmp_path / ("%s.py" % name)).write_text("")
    src = tmp_path / "src.py"
    src.write_text(
        "from rediacc_ci.drills import a\n"
        "from .b import x\n"
        "import rediacc_ci.drills.c\n"
        "from . import d\n"
        "from rediacc_ci.drills.missing import z\n"
    )
    assert _drill_imports(src, tmp_path) == {"a", "b", "c", "d"}


# ------------------------------------------------------------------ the surfaces a change reaches


def test_a_cli_change_outside_remote_reaches_the_cli_surface_and_needs_no_vm_run(
    world: World,
) -> None:
    _write(world.root, "packages/cli/src/commands/repo.ts", "export {};\n")
    _commit(world.root, "c1")
    got = world.changed()
    assert got.surfaces == {"cli"}
    assert got.hits == ()
    assert got.sides == frozenset()
    assert not got.touched


def test_a_shared_package_change_hits_the_account_side(world: World) -> None:
    """private/account/package.json depends on packages/shared, so its source is account code; the former trigger never saw it."""
    _write(world.root, "packages/shared/src/x.ts", "export const x = 1;\n")
    _commit(world.root, "c1")
    got = world.changed()
    assert got.hits == ("packages/shared/src/x.ts",)
    assert got.sides == {trig.SIDE_ACCOUNT}
    assert got.surfaces == {"account"}


@pytest.mark.parametrize(
    "path",
    [
        "packages/shared/src/x.test.ts",
        "packages/cli/src/remote/__tests__/a.ts",
        "private/renet/pkg/sandbox/a_test.go",
        "private/account/src/README.md",
        "packages/www/src/content/docs/a.md",
        "workers/proxy/src/a.spec.ts",
    ],
)
def test_a_test_file_or_a_document_hits_nothing(path: str) -> None:
    assert trig.surfaces_of(path) == frozenset()
    assert trig.console_sides(path) == frozenset()


@pytest.mark.parametrize(
    ("path", "surfaces"),
    [
        ("packages/cli/src/remote/ssh.ts", {"cli", "cli-remote"}),
        ("packages/cli/src/services/repo/repo-key-deployment.ts", {"cli", "cli-remote"}),
        ("workers/account/src/index.ts", {"account-worker"}),
        ("workers/proxy/src/index.ts", {"proxy"}),
        ("workers/proxy/wrangler.bench.toml", {"proxy"}),
        ("workers/proxy/package.json", set()),
        ("packages/www/src/pages/index.astro", {"www"}),
        ("workers/www/src/index.ts", {"www"}),
        ("private/renet", set()),
        ("private/account", set()),
        (".ci/rediacc_ci/deploy/deploy_proxy.py", set()),
        (".ci/rediacc_ci/proof/receipt.py", set()),
    ],
)
def test_surfaces_of_a_path(path: str, surfaces: set[str]) -> None:
    """A bare submodule path is the gitlink, not code; deploy and proof tooling are no surface."""
    assert trig.surfaces_of(path) == surfaces


def test_an_unknown_range_adds_the_submodule_surfaces(world: World) -> None:
    world.account_commit({"src/a.ts": "x\n"})
    world.commit_pointer("bump")
    (world.acc / ".git").rename(world.acc / ".git-away")
    got = world.changed()
    assert got.surfaces == {"account"}
    assert got.sides == {trig.SIDE_ACCOUNT}


def test_a_failed_console_diff_reaches_every_surface(world: World) -> None:
    got = trig.changed_paths(world.root, "no-such-ref", "push")
    assert got.surfaces == set(trig.SURFACES)


# ------------------------------------------------------------------ the map


def _map_raw() -> dict[str, Any]:
    return json.loads(trig.MAP_PATH.read_text(encoding="utf-8"))


def test_the_committed_map_parses_with_every_named_surface() -> None:
    assert set(trig.SURFACES) == {
        "renet",
        "cli-remote",
        "cli",
        "account",
        "account-worker",
        "proxy",
        "www",
    }
    assert trig.SIDES == ("renet", "account")
    assert trig.MAP.phases["renet"] == {"renet", "cli-remote"}
    assert trig.MAP.live["baseline_at"] is None
    assert trig.MAP.live["targets"]["hostinger"]["config"] == "eu-bench"


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda m: m.__setitem__("surfaces", {}), "surfaces is empty"),
        (lambda m: m.__setitem__("schema", 2), "schema"),
        (lambda m: m["surfaces"]["renet"].__setitem__("globs", []), "surfaces.renet.globs"),
        (lambda m: m["surfaces"]["renet"].__setitem__("globs", ["/abs/**"]), "absolute"),
        (lambda m: m["surfaces"]["cli"].pop("renet_build"), "renet_build"),
        (lambda m: m["tiers"]["vm"]["phases"]["renet"].__setitem__("surfaces", ["gpu"]), "gpu"),
        (lambda m: m["tiers"]["vm"]["phases"].pop("account"), "no account phase"),
        (
            lambda m: m["tiers"]["vm"]["instrument"].__setitem__("x.py", ["gpu"]),
            "instrument.x.py",
        ),
        (lambda m: m["tiers"].pop("live"), "tiers.live"),
        (lambda m: m.__setitem__("exclude", []), "exclude"),
    ],
)
def test_a_broken_map_is_refused(mutate: Callable[[dict[str, Any]], object], needle: str) -> None:
    raw = _map_raw()
    trig.parse_map(raw)
    mutate(raw)
    with pytest.raises(trig.MapError, match=needle):
        trig.parse_map(raw)


def test_an_unreadable_map_is_refused(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "proof-tiers.json"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(trig.MapError, match="unreadable"):
        trig.load(bad)
    with pytest.raises(trig.MapError, match="unreadable"):
        trig.load(tmp_path / "absent.json")


# ------------------------------------------------------------------ glob parity with owns_overlap over the plan census

# Design item 7 of agent/plans/PLAN-tested-on-bench.md: the census of 2026-10-27, required and exempt alike.
CENSUS = (
    "config-server-key",
    "console-executor-multi-org",
    "telemetry-export",
    "config-sync-hardening",
    "token-ip-rebind",
    "cloudflare-proxy",
    "executor-durable-object-policy",
    "proxy-cd-six-targets",
    "backup-program",
    "config-networkid-discovery",
    "sync-remote-file-ownership",
    "renet-runtime-converge",
    "sandbox-tenant-separation",
    "gpu-device-grants",
    "hostinger-upgrade-followups",
    "backup-toc-exact-opt-in",
    "converge-preflight-and-repo-recovery",
    "renet-fetch-retries",
    "renet-bridge-leftovers",
    "backup-presign-bucket-require-and-wrangler-vars",
    "renet-run-docker-sock-isolation",
    "lessons-registry-followups",
    "agent-tree-lifecycle",
    "ci-quick-cpu-scheduling",
    "cloudflare-spend-guard",
    "deletion-budget",
    "local-release",
    "pin-awscli-toolchain-python-compatible",
    "haiku-model-routing",
    "w7p5a-real-run-dispatch",
    "retired-terms-submodule-scan",
    "retire-bash-oracles",
    "submodule-branch-coordination-guard",
)
REPO = pathlib.Path(trig.__file__).resolve().parents[3]


def _census_owns() -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    plans = REPO / "agent" / "plans"
    for slug in CENSUS:
        for folder in (plans, plans / "_done", plans / "_removed"):
            path = folder / f"PLAN-{slug}.md"
            if not path.is_file():
                continue
            owns = trig.wl_planconc.declared_owns(path.read_text(encoding="utf-8"))
            if owns:
                found[slug] = tuple(owns)
            break
    return found


def _tracked(repo: pathlib.Path) -> list[str]:
    out = trig.make_git(repo)(["ls-files", "-z"])
    files = trig._lines(out)
    for sub in trig.SUBMODULES:
        files += [f"{sub}/{p}" for p in trig._lines(trig.make_git(repo / sub)(["ls-files", "-z"]))]
    return files


def _shared_path(witness: str, owns_glob: str, surface_glob: str) -> bool:
    """True when glob_regex puts `witness` in both globs, or, for the one known difference, `witness/x` (path_intersect lets a trailing `/**` match zero segments, so its witness for `dir/**` can be `dir` itself, which glob_regex's `dir/.*` refuses; the shared FILE is then one segment deeper)."""
    both = (owns_glob, surface_glob)
    if all(trig.matches(witness, (g,)) for g in both):
        return True
    return all(trig.matches(f"{witness}/x", (g,)) for g in both)


def test_shared_path_refuses_a_literal_directory_against_its_tree() -> None:
    """Control for `_shared_path`: a literal `dir` Owns entry and `dir/**` intersect only in the zero-segment reading, and share no file, so the helper must refuse it."""
    witness = trig.wl_planconc.path_intersect("private/renet/cmd", "private/renet/cmd/**")
    assert witness == "private/renet/cmd"
    assert not _shared_path(witness, "private/renet/cmd", "private/renet/cmd/**")
    assert _shared_path("private/renet/cmd", "private/renet/**", "private/renet/cmd/**")


def test_glob_matching_agrees_with_owns_overlap_over_the_census() -> None:
    """The push guard matches a path with glob_regex; the live-proof gate will judge a plan's Owns with owns_overlap. Both read the same normalised globs, so: every overlap witness owns_overlap names is a path glob_regex puts in both globs, and every tracked file glob_regex puts in both an Owns glob and a surface glob is backed by an overlap of that pair."""
    census = _census_owns()
    assert len(census) >= 20, (
        f"the census resolved only {sorted(census)}: the test is not seeing the plans"
    )
    files = _tracked(REPO)
    assert len(files) > 5000, "the tree listing is not seeing the checkout"
    # Each surface glob is materialised once; the census then only intersects sets.
    by_surface_glob = {
        g: set(trig.wl_planconc.materialise([g], files))
        for surface in trig.MAP.surfaces.values()
        for g in surface.globs
    }
    required = 0
    for slug, owns in sorted(census.items()):
        # With the root, a wildcard-free existing directory reads as `dir/**`; without it, a literal `private/account/drizzle` (w7p5a-real-run-dispatch) would overlap `private/account/drizzle/**` only in the zero-segment reading and share no file.
        norm, _problems = trig.wl_planconc.normalize_owns(owns, REPO)
        owned = {g: set(trig.wl_planconc.materialise([g], files)) for g in norm}
        hit_any = False
        for name, surface in trig.MAP.surfaces.items():
            pairs = trig.wl_planconc.owns_overlap(norm, surface.globs)
            for owns_glob, surface_glob, witness in pairs:
                assert _shared_path(witness, owns_glob, surface_glob), (
                    slug,
                    owns_glob,
                    surface_glob,
                    witness,
                )
            overlapping = {(a, b) for a, b, _w in pairs}
            for owns_glob, mine in owned.items():
                for surface_glob in surface.globs:
                    both = mine & by_surface_glob[surface_glob]
                    assert not both or (owns_glob, surface_glob) in overlapping, (
                        slug,
                        name,
                        owns_glob,
                        surface_glob,
                        sorted(both)[:3],
                    )
            hit_any = hit_any or bool(pairs)
        required += hit_any
    assert required >= 10, (
        f"only {required} census plans touch a surface: the map is not seeing the code"
    )


# ------------------------------------------------------------------ the version 3 digest


def _v2(
    root: pathlib.Path,
    tree: str,
    version: str = "v2",
    order: tuple[str, ...] = ("private/renet", "private/account"),
) -> str:
    """The retired version 2 digest, rebuilt from its definition: a `v2` line, the sorted blob lines of the former console trigger paths, then the renet and the account pointer in that order. `version` and `order` exist for the control only."""
    git = trig.make_git(root)
    out = git(["ls-tree", "-r", "-z", tree, "--", "packages/cli/src/remote/"]) or ""
    lines = sorted(trig._lines(out))
    body = (
        f"{version}\n"
        + "".join(f"{ln}\n" for ln in lines)
        + "".join(f"{sub} {trig._gitlink(git, tree, sub) or 'none'}\n" for sub in order)
    )
    return hashlib.sha256(body.encode()).hexdigest()


def test_a_v3_digest_differs_from_the_v2_digest_of_the_same_tree(world: World) -> None:
    _write(world.root, "packages/cli/src/remote/a.ts", "a\n")
    _commit(world.root, "c1")
    tree = _tree(world)
    v3 = trig.inputs(world.root, tree)
    assert v3 is not None
    assert v3 != _v2(world.root, tree)
    # Control: in this fixture both versions list the same blob and both pointers. With the first line swapped to `v3` and the pointers in v3's sorted order, the bodies agree, so the difference above is the version line and the pointer order, not a defect in _v2.
    assert v3 == _v2(world.root, tree, version="v3", order=("private/account", "private/renet"))
    assert v3 != _v2(world.root, tree, version="v3")


def test_a_live_account_digest_ignores_the_renet_pointer(world: World) -> None:
    before = trig.inputs(world.root, _tree(world), {"account"})
    world.renet_commit({"cmd/renet/other.go": "package main // moved\n"})
    world.commit_pointer("bump renet")
    assert trig.inputs(world.root, _tree(world), {"account"}) == before
    # Controls: the VM digest does move with the renet pointer, and the account digest moves with its own pointer and with packages/shared.
    world.account_commit({"src/index.ts": "export const moved = 1;\n"})
    world.commit_pointer("bump account")
    moved = trig.inputs(world.root, _tree(world), {"account"})
    assert moved != before
    _write(world.root, "packages/shared/src/x.ts", "export const x = 1;\n")
    _commit(world.root, "shared")
    assert trig.inputs(world.root, _tree(world), {"account"}) != moved


def test_the_vm_digest_moves_with_the_renet_pointer_the_live_cli_digest_does_not(
    world: World,
) -> None:
    vm = trig.inputs(world.root, _tree(world))
    cli = trig.inputs(world.root, _tree(world), {"cli"})
    world.renet_commit({"cmd/renet/other.go": "package main // moved\n"})
    world.commit_pointer("bump renet")
    assert trig.inputs(world.root, _tree(world)) != vm
    assert trig.inputs(world.root, _tree(world), {"cli"}) == cli


def test_a_live_digest_names_only_its_surfaces(world: World) -> None:
    _write(world.root, "workers/proxy/src/a.ts", "a\n")
    _commit(world.root, "c1")
    proxy = trig.inputs(world.root, _tree(world), {"proxy"})
    www = trig.inputs(world.root, _tree(world), {"www"})
    _write(world.root, "workers/proxy/src/a.ts", "b\n")
    _commit(world.root, "c2")
    assert trig.inputs(world.root, _tree(world), {"proxy"}) != proxy
    assert trig.inputs(world.root, _tree(world), {"www"}) == www
    assert trig.inputs(world.root, None, {"proxy"}) == trig.inputs(
        world.root, _tree(world), {"proxy"}
    )


def test_an_instrument_file_joins_the_vm_digest_only(world: World) -> None:
    vm = trig.inputs(world.root, _tree(world))
    live = trig.inputs(world.root, _tree(world), {"renet", "cli-remote"})
    _write(world.root, ".ci/rediacc_ci/drills/lib.py", "x = 2\n")
    _commit(world.root, "c1")
    assert trig.inputs(world.root, _tree(world)) != vm
    assert trig.inputs(world.root, _tree(world), {"renet", "cli-remote"}) == live


def test_an_unknown_surface_has_no_digest(world: World) -> None:
    with pytest.raises(KeyError):
        trig.inputs(world.root, _tree(world), {"gpu"})


# ------------------------------------------------------------------ worktree state


def test_submodule_state_and_console_dirty(world: World) -> None:
    state = trig.submodule_state(world.root, trig.RENET_SUBMODULE)
    assert state["pointer"] == state["checkout"] != ""
    assert state["modified"] is False
    _write(world.sub, "pkg/a.go", "package a\n")
    assert trig.submodule_state(world.root, trig.RENET_SUBMODULE)["modified"] is True
    assert trig.console_dirty(world.root, {"account"}) is False
    _write(world.root, "packages/shared/src/new.ts", "x\n")
    assert trig.console_dirty(world.root, {"account"}) is True
    assert trig.console_dirty(world.root, {"proxy"}) is False


# ------------------------------------------------------------------ the renet build identity

PTR_FIXTURE = "c" * 40


def test_go_buildinfo_reads_revision_and_modified() -> None:
    text = (
        "bin/renet: go1.24\n\tpath\tx\n\tbuild\tvcs.revision=%s\n\tbuild\tvcs.modified=true\n"
        % PTR_FIXTURE
    )
    assert trig.go_buildinfo(text) == (PTR_FIXTURE, True)
    assert trig.go_buildinfo("") == ("", None)


def _buildinfo(revision: str, modified: str) -> str:
    return (
        f"bin/renet: go1.24\n\tbuild\tvcs.revision={revision}\n\tbuild\tvcs.modified={modified}\n"
    )


def test_renet_identity_reads_the_build_and_hashes_the_binary(world: World) -> None:
    checkout = _git(world.sub, "rev-parse", "HEAD")
    binary = world.sub / "bin" / "renet"
    binary.parent.mkdir()
    binary.write_bytes(b"\x7fELF renet")
    got = trig.renet_identity(world.root, read_build=lambda _p: _buildinfo(checkout, "false"))
    assert got == {
        "pointer": checkout,
        "checkout": checkout,
        "built": checkout,
        "modified": False,
        "sha256": hashlib.sha256(b"\x7fELF renet").hexdigest(),
        "rebuilt": False,
    }


def test_renet_identity_rebuilds_once_when_the_build_is_not_the_checkout(world: World) -> None:
    checkout = _git(world.sub, "rev-parse", "HEAD")
    answers = [_buildinfo("d" * 40, "false"), _buildinfo(checkout, "false")]
    calls: list[str] = []
    got = trig.renet_identity(
        world.root, read_build=lambda _p: answers.pop(0), rebuild=lambda: calls.append("rdc")
    )
    assert calls == ["rdc"]
    assert got["built"] == checkout
    assert got["rebuilt"] is True
    assert got["sha256"] == ""


def test_renet_identity_without_go_reads_no_build(world: World) -> None:
    got = trig.renet_identity(world.root, read_build=lambda _p: None)
    assert got["built"] == ""
    assert got["modified"] is None


# ------------------------------------------------------------------ owns_surfaces: a plan's Owns against the map


@pytest.mark.parametrize(
    ("owns", "expected"),
    [
        (
            ["packages/cli/src/**"],
            {"cli-remote": ["packages/cli/src/**"], "cli": ["packages/cli/src/**"]},
        ),
        (["packages/cli/src/commands/repo.ts"], {"cli": ["packages/cli/src/commands/repo.ts"]}),
        (["private/renet"], {}),
        (["private/account"], {}),
        (["private/renet/"], {"renet": ["private/renet/**"]}),
        (["private/renet/cmd/**/*_test.go", "**/*.md", "docs/**"], {}),
        (["packages/shared/src/x.ts"], {"account": ["packages/shared/src/x.ts"]}),
        (
            ["private/account/{src,web}/**"],
            {"account": ["private/account/src/**", "private/account/web/**"]},
        ),
        ([".ci/rediacc_ci/proof/**", ".ci/rediacc_ci/drills/vm_check.py"], {}),
        (
            ["workers/proxy/src/**", "workers/account/**", "packages/www/src/**"],
            {
                "account-worker": ["workers/account/**"],
                "proxy": ["workers/proxy/src/**"],
                "www": ["packages/www/src/**"],
            },
        ),
    ],
)
def test_owns_surfaces_reads_a_plan_header_like_the_guard(
    owns: list[str], expected: dict[str, list[str]]
) -> None:
    got = trig.owns_surfaces(owns)
    assert got == expected
    assert list(got) == [n for n in trig.SURFACES if n in got], "map order"


def test_owns_surfaces_lists_a_glob_once_per_surface() -> None:
    """`private/renet/**` overlaps every renet glob; it is listed once, where the guard's loop would append it seven times."""
    assert trig.owns_surfaces(["private/renet/**", "private/renet/**"]) == {
        "renet": ["private/renet/**"]
    }


def test_owns_surfaces_drops_an_overlap_whose_witness_is_excluded() -> None:
    """Control first: the raw overlap exists, and only the exclude check drops it."""
    raw = trig.wl_planconc.owns_overlap(["packages/cli/src/**/*.test.ts"], ["packages/cli/src/**"])
    assert raw, "owns_overlap alone sees the test glob inside the cli surface"
    assert trig.owns_surfaces(["packages/cli/src/**/*.test.ts"]) == {}
