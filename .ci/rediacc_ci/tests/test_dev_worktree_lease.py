"""`./run.sh worktree lease` in throwaway repositories (PLAN-worktree-lease W2).

Nothing here touches a real checkout: `$REDIACC_CI_ROOT` points the verb at a fixture from W0's `worktree_spike.build_fixture`, whose submodule gitlink sits on a commit no remote holds. The code under test, `lease-seed.ts` and `tsx` still come from this checkout, so the seed is the real one.
"""

from __future__ import annotations

import json
import os
import pathlib
import shlex
import subprocess
import sys
from typing import NamedTuple

import pytest

from rediacc_ci import paths
from rediacc_ci.dev import worktree_lease as lease
from rediacc_ci.dev import worktree_spike as spike

SUB = "private/sub"
BRANCH = "0101-1"
LIVE_ONLY = "live-only"
ROOT_LOCK = {"packages": {"": {}, "node_modules/dep": {"version": "1.0.0"}}}
SUB_LOCK = {"packages": {"node_modules/z": {"version": "1.0.0"}}}
EMPTY_LOCK = {
    "name": "fx",
    "version": "1.0.0",
    "lockfileVersion": 3,
    "requires": True,
    "packages": {"": {"name": "fx", "version": "1.0.0"}},
}
BUILD_JS = (
    "const fs = require('fs');\n"
    "fs.mkdirSync('dist', { recursive: true });\n"
    "fs.writeFileSync('dist/built.txt', 'built\\n');\n"
)


def write_json(path, value):
    spike.write(path, json.dumps(value) + "\n")


def make_repo(base, *, live_branch=True, plant=False):
    """A console and submodule with tracked manifests, a live install, build output, caches and an e2e credential."""
    repo = spike.build_fixture(base, plant=plant)
    if plant:
        return repo
    root, live_sub = repo.root, repo.root / SUB
    write_json(live_sub / "package.json", {"name": "sub", "version": "1.0.0"})
    write_json(live_sub / "package-lock.json", SUB_LOCK)
    spike.commit_all(live_sub, "sub: manifest")
    write_json(live_sub / "node_modules" / ".package-lock.json", SUB_LOCK)

    ignore = root / ".gitignore"
    spike.write(ignore, ignore.read_text(encoding="utf-8") + "dist/\n.env*\n.venv/\n.ci/cache/\n")
    write_json(root / "package.json", {"name": "fx", "version": "1.0.0"})
    write_json(root / "package-lock.json", ROOT_LOCK)
    shared = root / "packages" / "shared"
    write_json(
        shared / "package.json",
        {
            "name": "@x/shared",
            "version": "1.0.0",
            "main": "index.js",
            "scripts": {"build": "node build.js"},
        },
    )
    spike.write(shared / "index.js", "module.exports = 'committed';\n")
    spike.write(shared / "build.js", BUILD_JS)
    spike.commit_all(root, "console: manifests")
    if live_branch:
        spike.must(root, "switch", "-q", "-c", BRANCH)
        spike.write(root / "second.txt", "on the live branch\n")
        spike.commit_all(root, "console: on the live branch")

    modules = root / "node_modules"
    spike.write(modules / "dep" / "index.js", "module.exports = 'dep';\n")
    write_json(modules / ".package-lock.json", {"packages": dict(ROOT_LOCK["packages"])})
    (modules / "@x").mkdir()
    (modules / "@x" / "shared").symlink_to("../../packages/shared")
    spike.write(shared / "dist" / "built.txt", "live\n")
    spike.write(root / ".venv" / "marker", "venv\n")
    spike.write(root / ".ci" / "cache" / "toolchain" / "marker", "tool\n")
    spike.write(root / "private" / "bin" / "tool", "binary\n")
    env_file = root / "packages" / "e2e-tests" / ".env"
    spike.write(env_file, "SECRET=1\n")
    env_file.chmod(0o600)
    return repo


def run_lease(root, *args, **extra):
    env = {
        **os.environ,
        "PYTHONPATH": str(paths.CI_DIR),
        paths.ROOT_ENV: str(root),
        **extra,
    }
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.dev.worktree", "lease", *args],
        cwd=str(paths.CI_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def shared_state(repo):
    """Everything a lease must leave alone in the main checkout. `info/exclude` is out: the box adds its three lines there on purpose."""
    store = repo.store(SUB)
    return {
        "console config": (repo.root / ".git" / "config").read_bytes(),
        "store config": (store / "config").read_bytes(),
        "console heads": spike.out(repo.root, "for-each-ref", "refs/heads"),
        "store heads": spike.out(store, "for-each-ref", "refs/heads"),
        "live status": spike.out(repo.root, "status", "--porcelain"),
        "live sub head": spike.out(repo.root / SUB, "rev-parse", "HEAD"),
    }


def holder_names(repo):
    return lease.trees_on_disk(repo.holder)


def leaves_nothing(repo, name):
    assert name not in holder_names(repo)
    assert not (repo.root / ".git" / lease.RECORD_DIR / ("%s.json" % name)).exists()
    assert spike.listed_trees(repo.root / ".git") == {str(repo.root)}
    store = repo.store(SUB)
    assert not [p for p in spike.listed_trees(store) if str(repo.holder) in p]


def locked_reason(store, tree):
    """The `locked` line of `tree` in `worktree list --porcelain`, or empty."""
    blocks = spike.out(store, "worktree", "list", "--porcelain").split("\n\n")
    for block in blocks:
        lines = block.splitlines()
        if lines and lines[0] == "worktree %s" % tree:
            return next((x for x in lines if x.startswith("locked")), "")
    return ""


def node_print(cwd, expression):
    return subprocess.run(
        ["node", "-p", expression],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


class Done(NamedTuple):
    repo: spike.Repo
    tree: pathlib.Path
    tip: str
    gitlink: str
    before: dict
    after: dict
    stdout: str


@pytest.fixture(scope="module", autouse=True)
def hermetic_git(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    identity = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.test",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.test",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "HOME": str(tmp_path_factory.mktemp("home")),
        "WORKLIST_SESSION_ID": "feedface99",
    }
    for key, value in identity.items():
        patch.setenv(key, value)
    patch.delenv("COMMIT_POLICY_OK", raising=False)
    yield
    patch.undo()


@pytest.fixture(scope="module")
def done(tmp_path_factory):
    """One lease from a dirty live tree, read by every test that only looks at it."""
    repo = make_repo(tmp_path_factory.mktemp("done").resolve())
    spike.write(repo.root / "code.txt", "UNCOMMITTED\n")
    before = shared_state(repo)
    tip = spike.must(repo.root, "rev-parse", "HEAD")
    result = run_lease(repo.root, "--name", "proof")
    assert result.returncode == 0, result.stderr
    return Done(
        repo=repo,
        tree=pathlib.Path(result.stdout.splitlines()[-1]),
        tip=tip,
        gitlink=spike.must(repo.root, "rev-parse", "HEAD:%s" % SUB),
        before=before,
        after=shared_state(repo),
        stdout=result.stdout,
    )


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path.resolve())


def test_lease_head_is_detached_at_the_live_tip(done):
    assert spike.must(done.tree, "rev-parse", "HEAD") == done.tip
    assert spike.git(done.tree, "symbolic-ref", "-q", "HEAD").returncode != 0
    assert spike.out(done.tree, "branch", "--show-current") == ""


def test_lease_submodule_sits_at_a_gitlink_no_remote_holds(done):
    store = done.repo.store(SUB)
    held = spike.out(store, "for-each-ref", "--contains", done.gitlink, "refs/remotes")
    assert not held, "fixture control: this gitlink must be local-only"
    sub = done.tree / SUB
    assert spike.must(sub, "rev-parse", "HEAD") == done.gitlink
    assert spike.git(sub, "symbolic-ref", "-q", "HEAD").returncode != 0
    assert spike.must(sub, "rev-parse", "--show-toplevel") == str(sub)
    status = spike.must(done.tree, "submodule", "status", "--", SUB)
    assert status.split()[:2] == [done.gitlink, SUB]


def test_lease_shared_config_stays_byte_identical(done):
    for key in ("console config", "store config"):
        assert done.after[key] == done.before[key], key


def test_lease_config_control_a_shared_write_from_the_lease_goes_red(done):
    """Quick-clone's `git config submodule.<name>.url`, run in a lease, rewrites the live config: the reason the check above can fail."""
    config = done.repo.root / ".git" / "config"
    saved = config.read_bytes()
    try:
        spike.must(done.tree, "config", "submodule.%s.url" % SUB, "/somewhere")
        assert config.read_bytes() != saved
    finally:
        config.write_bytes(saved)


def test_lease_status_is_empty_with_every_seed_in_place(done):
    assert spike.git(done.tree, "status", "--porcelain").stdout == ""
    assert spike.git(done.tree / SUB, "status", "--porcelain").stdout == ""
    assert (done.tree / ".venv").is_symlink(), "the link only the exclude line hides"
    assert (done.repo.root / ".gitignore").read_text(encoding="utf-8").count(".venv/") == 1


def test_lease_leaves_refs_and_the_live_tree_alone(done):
    for key in ("console heads", "store heads", "live status", "live sub head"):
        assert done.after[key] == done.before[key], key
    assert (done.repo.root / "code.txt").read_text(encoding="utf-8") == "UNCOMMITTED\n"
    assert (done.tree / "code.txt").read_text(encoding="utf-8") == "console\n"


def test_lease_workspace_package_resolves_inside_the_tree(done):
    result = node_print(done.tree, "require.resolve('@x/shared')")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(done.tree / "packages" / "shared" / "index.js")


def test_lease_seed_links_copies_and_hard_links_by_kind(done):
    root, tree = done.repo.root, done.tree
    for rel in ("node_modules/dep/index.js", "private/bin/tool", f"{SUB}/node_modules/z/c.js"):
        assert (tree / rel).stat().st_ino == (root / rel).stat().st_ino, rel
    assert not (tree / "node_modules").is_symlink()
    assert os.readlink(tree / ".venv") == str(root / ".venv")
    assert os.readlink(tree / ".ci" / "cache" / "toolchain") == str(
        root / ".ci" / "cache" / "toolchain"
    )
    built = pathlib.PurePath("packages", "shared", "dist", "built.txt")
    assert (tree / built).read_text(encoding="utf-8") == "live\n"
    assert (tree / built).stat().st_ino != (root / built).stat().st_ino
    copied = tree / "packages" / "e2e-tests" / ".env"
    assert copied.read_text(encoding="utf-8") == "SECRET=1\n"
    assert copied.stat().st_mode & 0o777 == 0o600
    assert (tree / "node_modules" / "node_modules").exists() is False


def test_lease_seed_state_files_do_not_outlive_the_seed(done):
    assert sorted(p.name for p in done.repo.holder.iterdir()) == ["proof"]


def test_lease_last_stdout_line_is_the_only_line_and_a_normalized_path(done):
    lines = done.stdout.splitlines()
    assert lines == [str(done.tree)]
    assert done.tree.is_absolute()
    assert str(done.tree) == os.path.realpath(done.tree)
    assert done.tree.parent == done.repo.holder


def test_lease_is_locked_in_both_stores(done):
    wanted = "locked lease:proof"
    assert locked_reason(done.repo.root / ".git", done.tree) == wanted
    assert locked_reason(done.repo.store(SUB), done.tree / SUB) == wanted


def test_lease_record_names_owner_and_every_base(done):
    path = done.repo.root / ".git" / lease.RECORD_DIR / "proof.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["id"] == "proof"
    assert record["path"] == str(done.tree)
    assert record["owner"] == "feedface"
    assert record["agent"] == ""
    assert record["base"] == {".": done.tip, SUB: done.gitlink}
    assert record["created_at"].endswith("Z")


def test_lease_refuses_an_id_that_exists_and_keeps_the_tree(done):
    result = run_lease(done.repo.root, "--name", "proof")
    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert result.stdout == ""
    assert spike.must(done.tree, "rev-parse", "HEAD") == done.tip


def test_lease_refuses_to_run_from_a_lease(done):
    result = run_lease(done.tree, "--name", "nested")
    assert result.returncode == 1
    assert "not a main checkout" in result.stderr
    assert not (done.tree / ".claude" / "worktrees").exists()


def test_lease_help_touches_nothing(done):
    before = sorted(p.name for p in done.repo.holder.iterdir())
    state = shared_state(done.repo)
    for flag in ("--help", "-h"):
        for root in (done.repo.root, done.repo.root / "no-such-directory"):
            result = run_lease(root, flag)
            assert result.returncode == 0
            assert result.stdout.startswith("Usage: ./run.sh worktree lease")
            assert result.stderr == ""
    assert sorted(p.name for p in done.repo.holder.iterdir()) == before
    assert shared_state(done.repo) == state


@pytest.mark.parametrize(
    "args",
    [
        ["--bogus"],
        ["surplus"],
        ["--name"],
        ["--name", "../x"],
        ["--name", "a/b"],
        ["--name", ".hidden"],
        ["--name", "spike-x"],
        ["--owner", "a/b"],
    ],
)
def test_lease_refuses_a_bad_argument_before_any_git(tmp_path, args):
    missing = tmp_path / "not-a-repository"
    missing.mkdir()
    result = run_lease(missing, *args)
    assert result.returncode == 1
    assert result.stdout == ""
    assert list(missing.iterdir()) == []


def test_lease_writer_cap_refuses_the_second_tree(repo):
    spike.write(
        repo.root / "agent" / "plans" / "QUEUE.md",
        "## Settings\n\n```stop-hook\nwriter_cap: 1 -- fixture\n```\n",
    )
    first = run_lease(repo.root, "--name", "one")
    assert first.returncode == 0, first.stderr
    second = run_lease(repo.root, "--name", "two")
    assert second.returncode == 1
    assert "writer_cap 1" in second.stderr
    assert "./run.sh worktree gc" in second.stderr
    assert second.stdout == ""
    assert holder_names(repo) == ["one"]


def test_lease_generated_ids_count_up_and_exclude_lines_land_once(repo):
    first = run_lease(repo.root, "--owner", "abcd1234")
    second = run_lease(repo.root, "--owner", "abcd1234")
    third = run_lease(repo.root)
    assert first.returncode == second.returncode == third.returncode == 0, third.stderr
    assert holder_names(repo) == ["abcd1234-1", "abcd1234-2", "feedface-1"]
    lines = (repo.root / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    for line in lease.EXCLUDE_LINES:
        assert lines.count(line) == 1, line


def test_lease_on_main_with_one_live_branch_takes_that_branchs_tip(repo):
    tip = spike.must(repo.root, "rev-parse", "HEAD")
    spike.must(repo.root, "switch", "-q", "main")
    assert spike.must(repo.root, "rev-parse", "HEAD") != tip, "fixture control"
    result = run_lease(repo.root, "--name", "t")
    assert result.returncode == 0, result.stderr
    assert spike.must(result.stdout.strip(), "rev-parse", "HEAD") == tip


def test_lease_between_branches_takes_main(tmp_path):
    repo = make_repo(tmp_path.resolve(), live_branch=False)
    result = run_lease(repo.root, "--name", "t")
    assert result.returncode == 0, result.stderr
    head = spike.must(result.stdout.strip(), "rev-parse", "HEAD")
    assert head == spike.must(repo.root, "rev-parse", "refs/heads/main")


def test_lease_dirty_shared_source_builds_in_the_tree_instead_of_copying(repo):
    shared = repo.root / "packages" / "shared"
    spike.write(shared / "index.js", "module.exports = 'DIRTY';\n")
    result = run_lease(repo.root, "--name", "t")
    assert result.returncode == 0, result.stderr
    tree = pathlib.Path(result.stdout.strip())
    assert (tree / "packages" / "shared" / "dist" / "built.txt").read_text(
        encoding="utf-8"
    ) == "built\n"
    assert (shared / "dist" / "built.txt").read_text(encoding="utf-8") == "live\n"


def test_lease_package_absent_from_the_tree_is_refused_not_read_from_live(repo):
    """The lockfile at the tip no longer holds what the live root has installed, so the real install leaves packages out and only the upward walk would find them."""
    root = repo.root
    write_json(root / "package-lock.json", EMPTY_LOCK)
    spike.commit_all(root, "console: lockfile moved past the live install")
    modules = root / "node_modules"
    spike.write(modules / LIVE_ONLY / "index.js", "module.exports = 'live';\n")
    hidden = {
        "packages": {**ROOT_LOCK["packages"], "node_modules/%s" % LIVE_ONLY: {"version": "1"}}
    }
    write_json(modules / ".package-lock.json", hidden)

    probe = repo.holder / "probe"
    probe.mkdir(parents=True)
    walked = node_print(probe, "require.resolve('%s')" % LIVE_ONLY)
    probe.rmdir()
    assert walked.stdout.strip() == str(modules / LIVE_ONLY / "index.js"), (
        "control: the upward walk reaches the live node_modules, so the refusal guards something"
    )

    before = shared_state(repo)
    result = run_lease(root, "--name", "t")
    assert result.returncode == 1, result.stdout
    assert "resolve upward" in result.stderr
    assert LIVE_ONLY in result.stderr
    assert result.stdout == ""
    leaves_nothing(repo, "t")
    assert shared_state(repo) == before


def test_lease_missing_gitlink_commit_is_refused_and_leaves_nothing(tmp_path):
    repo = make_repo(tmp_path.resolve(), plant=True)
    before = shared_state(repo)
    result = run_lease(repo.root, "--name", "t")
    assert result.returncode == 1, result.stdout
    assert spike.MISSING_SHA in result.stderr
    assert result.stdout == ""
    leaves_nothing(repo, "t")
    assert shared_state(repo) == before


# --------------------------------------------------------------------------- pins (W4) ---------------------------------------------------------------------------
#
# These run the repository's real hook directory, as `core.hooksPath` does on a real checkout, so a pin that moves came through the real `post-commit` shim and every other real hook admitted the commit.

HOOKS = paths.CI_DIR.parent / ".claude" / "rediacc_hooks" / "git"
PIN_ID = "p"
PIN_REF = spike.PIN_SPACE + PIN_ID


class Pinned(NamedTuple):
    repo: spike.Repo
    tree: pathlib.Path


def real_hooks(repo):
    for checkout in (repo.root, repo.root / SUB):
        spike.must(checkout, "config", "core.hooksPath", str(HOOKS))


def run_worktree_hook(root, verb, payload):
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.dev.worktree", verb],
        cwd=str(paths.CI_DIR),
        env=gc_env(root),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )


def test_lease_hook_prints_the_tree_and_records_the_agent(repo):
    done = run_worktree_hook(
        repo.root, "lease-hook", {"name": "agent-a123", "session_id": "abcd1234ffff"}
    )
    assert done.returncode == 0, done.stderr
    tree = pathlib.Path(done.stdout.strip().splitlines()[-1])
    assert tree == repo.root / spike.HOLDER / "agent-a123"
    assert spike.out(tree, "branch", "--show-current") == ""
    record = json.loads((repo.root / ".git" / lease.RECORD_DIR / "agent-a123.json").read_text())
    assert (record["owner"], record["agent"]) == ("abcd1234", "a123")


def test_lease_hook_over_the_cap_exits_non_zero_with_the_message(repo):
    spike.write(
        repo.root / "agent" / "plans" / "QUEUE.md",
        "## Settings\n\n```stop-hook\nwriter_cap: 1 -- fixture\n```\n",
    )
    make_tree(repo, "first")
    done = run_worktree_hook(repo.root, "lease-hook", {"name": "agent-b", "session_id": "abcd1234"})
    assert done.returncode != 0
    assert "writer_cap 1" in done.stderr
    assert done.stdout == ""


def test_gc_hook_on_a_dirty_tree_exits_non_zero_with_the_tree_intact(repo):
    tree = make_tree(repo, "dirty-hook")
    spike.write(tree / "scratch.txt", "work\n")
    done = run_worktree_hook(repo.root, "gc-hook", {"worktree_path": str(tree)})
    assert done.returncode != 0
    assert (tree / "scratch.txt").is_file()


def test_gc_hook_on_a_clean_tree_exits_zero_with_the_tree_gone(repo):
    made = run_lease(repo.root, "--name", "clean-hook", "--owner", "cli")
    assert made.returncode == 0, made.stderr
    tree = pathlib.Path(made.stdout.strip())
    done = run_worktree_hook(repo.root, "gc-hook", {"worktree_path": str(tree)})
    assert done.returncode == 0, done.stderr
    assert not tree.exists()


def test_gc_hook_refuses_a_path_outside_the_holder(repo):
    done = run_worktree_hook(repo.root, "gc-hook", {"worktree_path": str(repo.root / "docs")})
    assert done.returncode != 0
    assert "no lease tree" in done.stderr


def make_tree(repo, name):
    result = run_lease(repo.root, "--name", name)
    assert result.returncode == 0, result.stderr
    return pathlib.Path(result.stdout.strip())


def commit_file(tree, name, *, env=None):
    """Commit one new file in `tree`. Returns the finished `git commit`, with its hooks' stderr."""
    spike.write(tree / name, "%s\n" % name)
    spike.must(tree, "add", "--", name)
    return spike.git(
        tree,
        *("commit", "--no-gpg-sign", "-m", "feat: %s\n\nPR-TASK: 1f877343\n" % name),
        env=env,
    )


def committed(tree, name):
    done = commit_file(tree, name)
    assert done.returncode == 0, done.stderr
    assert "pin not moved" not in done.stderr, done.stderr
    return spike.must(tree, "rev-parse", "HEAD")


def pin_at(cwd, ref=PIN_REF):
    return spike.out(cwd, "rev-parse", "--verify", "-q", ref)


def run_pin_verb(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.dev.worktree_lease", "pin", *args],
        cwd=str(cwd),
        env={**os.environ, "PYTHONPATH": str(paths.CI_DIR)},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def pinned(tmp_path):
    repo = make_repo(tmp_path.resolve())
    real_hooks(repo)
    return Pinned(repo, make_tree(repo, PIN_ID))


def test_pin_shim_is_an_executable_copy_of_its_siblings():
    shim = HOOKS / "post-commit"
    assert os.access(shim, os.X_OK)
    assert shim.read_bytes() == (HOOKS / "pre-push").read_bytes()


def test_pin_commit_moves_it_and_main_and_another_lease_see_it(pinned):
    repo, tree = pinned
    other = make_tree(repo, "other")
    assert pin_at(repo.root) == "", "fixture control: making a lease pins nothing"
    first = committed(tree, "one.txt")
    assert pin_at(repo.root) == first
    assert pin_at(other) == first
    second = committed(tree, "two.txt")
    assert second != first
    assert pin_at(repo.root) == second
    assert pin_at(other) == second


def test_pin_control_a_commit_with_no_post_commit_hook_moves_nothing(tmp_path):
    """The fixture's own hook directory holds only `pre-commit`, so the moves above are the shim's work."""
    repo = make_repo(tmp_path.resolve())
    tree = make_tree(repo, PIN_ID)
    committed(tree, "one.txt")
    assert pin_at(repo.root) == ""


def test_pin_singular_spelling_is_invisible_from_main_the_reason_for_the_plural(pinned):
    repo, tree = pinned
    other = make_tree(repo, "other")
    singular = "refs/worktree/%s" % PIN_ID
    sha = spike.must(tree, "rev-parse", "HEAD")
    spike.must(tree, "update-ref", singular, sha)
    assert pin_at(tree, singular) == sha
    assert pin_at(repo.root, singular) == ""
    assert pin_at(other, singular) == ""


def test_pin_keeps_the_commit_through_tree_removal_and_gc(pinned):
    repo, tree = pinned
    sha = committed(tree, "kept.txt")
    blob = spike.must(tree, "rev-parse", "HEAD:kept.txt")
    unpinned = spike.must(repo.root, "commit-tree", "HEAD^{tree}", "-m", "control")
    spike.must(repo.root, "worktree", "unlock", str(tree))
    spike.must(repo.root, "worktree", "remove", "--force", str(tree))
    assert not tree.exists()
    assert str(tree) not in spike.listed_trees(repo.root / ".git")
    spike.must(repo.root, "gc", "--prune=now", "--quiet")
    assert pin_at(repo.root) == sha
    for held in (sha, blob):
        assert spike.git(repo.root, "cat-file", "-e", held).returncode == 0, held
    assert spike.git(repo.root, "cat-file", "-e", unpinned).returncode != 0, (
        "control: gc must collect an unreferenced commit, or this test proves nothing"
    )


def test_pin_reference_transaction_admits_it_with_the_hook_live(pinned):
    repo, tree = pinned
    sha = spike.must(tree, "rev-parse", "HEAD")
    moved = spike.git(tree, "update-ref", PIN_REF, sha)
    assert moved.returncode == 0, moved.stderr
    assert pin_at(repo.root) == sha
    refused = spike.git(tree, "branch", "second")
    assert refused.returncode != 0, "control: the hook is live, and it refuses a second branch"
    assert "commit-policy" in refused.stderr
    assert spike.out(repo.root, "rev-parse", "--verify", "-q", "refs/heads/second") == ""


def test_pin_commit_in_the_main_checkout_moves_nothing(pinned):
    repo, tree = pinned
    held = committed(tree, "lease.txt")
    live_sub = repo.root / SUB
    refs_of = "--format=%(refname) %(objectname)"
    console = spike.must(repo.root, "for-each-ref", refs_of, spike.PIN_SPACE)
    assert console == "%s %s" % (PIN_REF, held)
    committed(repo.root, "main.txt")
    spike.must(live_sub, "switch", "-q", "-c", BRANCH)
    committed(live_sub, "main-sub.txt")
    assert spike.must(repo.root, "for-each-ref", refs_of, spike.PIN_SPACE) == console
    assert spike.must(live_sub, "for-each-ref", refs_of, spike.PIN_SPACE) == ""


def test_pin_stays_when_head_does_not_descend_from_it(pinned):
    repo, tree = pinned
    base = spike.must(tree, "rev-parse", "HEAD")
    held = committed(tree, "held.txt")
    spike.must(tree, "reset", "-q", "--hard", base)
    done = commit_file(tree, "other.txt")
    assert done.returncode == 0, done.stderr
    head = spike.must(tree, "rev-parse", "HEAD")
    assert head != held
    assert spike.git(tree, "merge-base", "--is-ancestor", held, head).returncode != 0
    assert pin_at(repo.root) == held
    assert "stays at %s" % held in done.stderr
    assert "pin not moved" not in done.stderr


def test_pin_only_blob_is_in_log_all_and_not_reachable_in_a_clone(pinned, tmp_path):
    """The limit Design 3 writes down: a `git log --all` reader finds a blob cited only from an unlanded commit, and a clone does not, because no `refs/worktrees/*` crosses.

    `--local` hard-links the whole object directory, so the blob's bytes do arrive there, unreachable: `cat-file` answers and `log --all` does not. A transport clone, the shape of CI's checkout, lacks the bytes as well.
    """
    repo, tree = pinned
    sha = committed(tree, "only-here.txt")
    blob = spike.must(tree, "rev-parse", "HEAD:only-here.txt")
    finder = ("log", "--all", "--format=%H", "--find-object=%s" % blob)
    assert spike.must(repo.root, *finder) == sha
    local, transport = tmp_path / "local", tmp_path / "transport"
    spike.must(tmp_path, "clone", "-q", "--local", str(repo.root), str(local))
    spike.must(tmp_path, "clone", "-q", "--no-local", str(repo.root), str(transport))
    for clone in (local, transport):
        assert spike.must(clone, *finder) == "", clone
        assert spike.must(clone, "for-each-ref", spike.PIN_SPACE) == "", clone
        assert spike.git(clone, "rev-parse", "--verify", "-q", PIN_REF).returncode != 0, clone
    assert spike.git(local, "cat-file", "-e", blob).returncode == 0
    assert spike.git(transport, "cat-file", "-e", blob).returncode != 0


def test_pin_of_a_submodule_tree_lands_in_its_module_store(pinned):
    repo, tree = pinned
    sha = committed(tree / SUB, "sub.txt")
    assert pin_at(repo.store(SUB)) == sha
    assert pin_at(repo.root / SUB) == sha
    assert pin_at(repo.root) == "", "the console's own pin is the console tree's"
    console = committed(tree, "console.txt")
    assert pin_at(repo.root) == console
    assert pin_at(repo.store(SUB)) == sha


def test_pin_moves_under_the_operators_override(pinned):
    repo, tree = pinned
    done = commit_file(tree, "over.txt", env={"COMMIT_POLICY_OK": "1"})
    assert done.returncode == 0, done.stderr
    assert pin_at(repo.root) == spike.must(tree, "rev-parse", "HEAD")


def test_pin_verb_from_a_subdirectory_moves_it_and_a_repeat_changes_nothing(pinned):
    repo, tree = pinned
    head = spike.must(tree, "rev-parse", "HEAD")
    deeper = tree / "packages" / "shared"
    for _ in range(2):
        result = run_pin_verb(deeper)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ""
        assert result.stderr == ""
        assert pin_at(repo.root) == head


@pytest.mark.parametrize("args", [(), ("surplus",)])
def test_pin_verb_refuses_outside_a_lease_or_with_an_argument(pinned, args):
    repo, tree = pinned
    where = repo.root if not args else tree
    result = run_pin_verb(where, *args)
    assert result.returncode == 1
    assert result.stdout == ""
    assert pin_at(repo.root) == ""


LAND_ID = "ld"


class Landing(NamedTuple):
    repo: spike.Repo
    tree: pathlib.Path
    sub_sha: str
    console_sha: str


def run_land(root, *args):
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.dev.worktree", "land", *args],
        cwd=str(paths.CI_DIR),
        env={**os.environ, "PYTHONPATH": str(paths.CI_DIR), paths.ROOT_ENV: str(root)},
        capture_output=True,
        text=True,
        check=False,
    )


def run_printed(root, lines, tmp_path):
    """Run each printed line as printed, with `<msg>` standing for a message file. Returns the finished runs."""
    message = tmp_path / "gitlink-msg.txt"
    message.write_text("chore: bump the gitlink\n\nPR-TASK: 1f877343\n", encoding="utf-8")
    runs = []
    for line in lines:
        words = [str(message) if w == "<msg>" else w for w in shlex.split(line)]
        assert words[0] == "git", line
        runs.append(spike.git(root, *words[1:]))
    return runs


def sub_commit(tree, name):
    sub = tree / SUB
    spike.write(sub / name, "%s\n" % name)
    spike.must(sub, "add", "--", name)
    spike.must(sub, "commit", "--no-gpg-sign", "-m", "sub: %s\n\nPR-TASK: 1f877343\n" % name)
    return spike.must(sub, "rev-parse", "HEAD")


def unlanded_in(repo, tree, key=".", pin=""):
    """What the lease tool reads as unlanded for one repo of lease LAND_ID."""
    live = repo.root if key == "." else repo.root / key
    where = tree if key == "." else tree / key
    tip = spike.must(live, "rev-parse", "HEAD")
    head = spike.must(where, "rev-parse", "HEAD")
    return lease.unlanded(where, head, pin, tip, "")


@pytest.fixture
def landing(tmp_path):
    repo = make_repo(tmp_path.resolve())
    tree = make_tree(repo, LAND_ID)
    sub_sha = sub_commit(tree, "sub-new.txt")
    committed(tree, "feat.txt")
    return Landing(repo, tree, sub_sha, spike.must(tree, "rev-parse", "HEAD"))


def test_land_printed_lines_run_as_printed_land_the_submodule_first_and_rebump(landing, tmp_path):
    repo, _tree, sub_sha, console_sha = landing
    before = spike.must(repo.root, "rev-parse", "HEAD")
    result = run_land(repo.root, LAND_ID)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines == [
        "git -C %s cherry-pick -x %s" % (SUB, sub_sha),
        "git add -- %s" % SUB,
        "git commit -F <msg> -- %s" % SUB,
        "git cherry-pick -x %s" % console_sha,
    ]
    assert spike.must(repo.root, "rev-parse", "HEAD") == before
    for finished in run_printed(repo.root, lines, tmp_path):
        assert finished.returncode == 0, finished.stderr
    live_sub = spike.must(repo.root / SUB, "rev-parse", "HEAD")
    assert live_sub != sub_sha
    bump = spike.must(repo.root, "rev-parse", "HEAD~1:%s" % SUB)
    assert bump == live_sub
    assert (repo.root / "feat.txt").is_file()
    assert (repo.root / SUB / "sub-new.txt").is_file()


def test_land_source_sha_reads_landed_afterwards_by_patch_id(landing, tmp_path):
    repo, tree, sub_sha, console_sha = landing
    assert unlanded_in(repo, tree) == [console_sha]
    assert unlanded_in(repo, tree, SUB) == [sub_sha]
    lines = run_land(repo.root, LAND_ID).stdout.splitlines()
    for finished in run_printed(repo.root, lines, tmp_path):
        assert finished.returncode == 0, finished.stderr
    tip = spike.must(repo.root, "rev-parse", "HEAD")
    assert spike.out(tree, "cherry", tip, console_sha).startswith("- ")
    assert unlanded_in(repo, tree) == []
    assert unlanded_in(repo, tree, SUB) == []
    again = run_land(repo.root, LAND_ID)
    assert again.returncode == 0
    assert again.stdout == ""


def conflicted(landing):
    """A lease commit and a live commit both rewriting second.txt, so the pick stops and the resolution differs from the source patch."""
    repo, tree, _, _ = landing
    spike.write(tree / "second.txt", "lease version\n")
    spike.must(tree, "add", "--", "second.txt")
    spike.must(tree, "commit", "--no-gpg-sign", "-m", "feat: edit\n\nPR-TASK: 1f877343\n")
    source = spike.must(tree, "rev-parse", "HEAD")
    spike.write(repo.root / "second.txt", "live version\n")
    spike.commit_all(repo.root, "console: live edit")
    return source


def pick_with_resolution(repo, source):
    stopped = spike.git(repo.root, "cherry-pick", "-x", source)
    assert stopped.returncode != 0
    spike.write(repo.root / "second.txt", "resolved by hand\n")
    spike.must(repo.root, "add", "--", "second.txt")
    return spike.git(repo.root, "-c", "core.editor=true", "cherry-pick", "--continue")


def test_land_conflict_resolved_pick_reads_landed_by_its_x_line_not_by_patch_id(landing):
    repo, tree, _, _ = landing
    source = conflicted(landing)
    done = pick_with_resolution(repo, source)
    assert done.returncode == 0, done.stderr
    tip = spike.must(repo.root, "rev-parse", "HEAD")
    assert "(cherry picked from commit %s)" % source in spike.must(
        repo.root, "log", "-1", "--format=%B"
    )
    assert "+ %s" % source in spike.out(tree, "cherry", tip, source)
    assert source not in unlanded_in(repo, tree)


def test_land_control_without_the_x_reader_the_resolved_pick_reads_unlanded(landing, monkeypatch):
    repo, tree, _, _ = landing
    source = conflicted(landing)
    assert pick_with_resolution(repo, source).returncode == 0
    monkeypatch.setattr(lease._hook_module("wl_worktrees"), "PICKED_LINE", "(no such line %s)")
    assert source in unlanded_in(repo, tree)


def test_land_without_x_the_resolved_pick_reads_unlanded_the_reason_for_the_flag(landing):
    repo, tree, _, _ = landing
    source = conflicted(landing)
    stopped = spike.git(repo.root, "cherry-pick", source)
    assert stopped.returncode != 0
    spike.write(repo.root / "second.txt", "resolved by hand\n")
    spike.must(repo.root, "add", "--", "second.txt")
    assert (
        spike.git(repo.root, "-c", "core.editor=true", "cherry-pick", "--continue").returncode == 0
    )
    assert source in unlanded_in(repo, tree)


def test_land_commit_without_a_pr_task_trailer_exits_1_with_no_lines(landing):
    repo, tree, _, _ = landing
    spike.write(tree / "bare.txt", "bare\n")
    spike.must(tree, "add", "--", "bare.txt")
    spike.must(tree, "commit", "--no-gpg-sign", "-m", "feat: no trailer")
    bare = spike.must(tree, "rev-parse", "HEAD")
    result = run_land(repo.root, LAND_ID)
    assert result.returncode == 1
    assert result.stdout == ""
    assert bare[:12] in result.stderr
    assert "PR-TASK" in result.stderr


def test_land_pr_task_trailer_stays_parseable_after_x(landing, tmp_path):
    repo, _, _, console_sha = landing
    lines = run_land(repo.root, LAND_ID).stdout.splitlines()
    for finished in run_printed(repo.root, lines, tmp_path):
        assert finished.returncode == 0, finished.stderr
    message = spike.must(repo.root, "log", "-1", "--format=%B")
    assert "(cherry picked from commit %s)" % console_sha in message
    parsed = subprocess.run(
        ["git", "interpret-trailers", "--parse"],
        input=message,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "PR-TASK: 1f877343" in parsed.splitlines()


def test_land_peer_staged_path_makes_the_pick_refuse_with_the_path_unmoved(landing):
    repo, _, _, console_sha = landing
    spike.write(repo.root / "peer.txt", "peer work\n")
    spike.must(repo.root, "add", "--", "peer.txt")
    head = spike.must(repo.root, "rev-parse", "HEAD")
    refused = spike.git(repo.root, "cherry-pick", "-x", console_sha)
    assert refused.returncode != 0
    assert spike.must(repo.root, "rev-parse", "HEAD") == head
    assert spike.must(repo.root, "diff", "--cached", "--name-only") == "peer.txt"
    assert (repo.root / "peer.txt").read_text(encoding="utf-8") == "peer work\n"
    assert not (repo.root / "feat.txt").exists()


def test_land_rebase_of_the_live_branch_keeps_the_source_landed(landing):
    repo, tree, _, _ = landing
    source = conflicted(landing)
    assert pick_with_resolution(repo, source).returncode == 0
    spike.must(repo.root, "switch", "-q", "main")
    spike.write(repo.root / "main-only.txt", "moved main\n")
    spike.commit_all(repo.root, "console: main moved")
    spike.must(repo.root, "switch", "-q", BRANCH)
    spike.must(repo.root, "rebase", "main")
    assert (repo.root / "main-only.txt").is_file()
    assert source not in unlanded_in(repo, tree)


def test_land_refuses_a_merge_commit(landing):
    repo, tree, _, _ = landing
    base = spike.must(tree, "rev-parse", "HEAD~1")
    side = spike.must(tree, "rev-parse", "HEAD")
    spike.must(tree, "checkout", "-q", "--detach", base)
    committed(tree, "side.txt")
    spike.must(
        tree, "merge", "--no-gpg-sign", "--no-ff", "-q", "-m", "m\n\nPR-TASK: 1f877343\n", side
    )
    result = run_land(repo.root, LAND_ID)
    assert result.returncode == 1
    assert result.stdout == ""
    assert "is a merge" in result.stderr


def test_land_detached_submodule_gets_the_console_branch_first(landing, tmp_path):
    repo, _tree, sub_sha, _console_sha = landing
    sub = repo.root / SUB
    branch = spike.must(repo.root, "symbolic-ref", "--short", "HEAD")
    spike.must(sub, "checkout", "-q", "--detach")
    lines = run_land(repo.root, LAND_ID).stdout.splitlines()
    assert lines[:2] == [
        "git -C %s switch -c %s" % (SUB, branch),
        "git -C %s cherry-pick -x %s" % (SUB, sub_sha),
    ]
    for finished in run_printed(repo.root, lines, tmp_path):
        assert finished.returncode == 0, finished.stderr
    assert spike.must(sub, "symbolic-ref", "--short", "HEAD") == branch


@pytest.mark.parametrize("kind", ["gitlink", "agent"])
def test_land_refuses_a_commit_touching_a_gitlink_or_agent_path(landing, kind):
    repo, tree, _, _ = landing
    if kind == "gitlink":
        sub_commit(tree, "moved.txt")
        spike.must(tree, "add", "--", SUB)
        needle = "gitlink"
    else:
        spike.write(tree / "agent" / "note.md", "note\n")
        spike.must(tree, "add", "--", "agent/note.md")
        needle = "agent/note.md"
    spike.must(tree, "commit", "--no-gpg-sign", "-m", "feat: bad\n\nPR-TASK: 1f877343\n")
    result = run_land(repo.root, LAND_ID)
    assert result.returncode == 1
    assert result.stdout == ""
    assert needle in result.stderr


def test_land_unknown_lease_and_bad_arguments_exit_1(landing):
    repo = landing.repo
    for args in ((), ("a", "b"), ("--x",), ("missing",)):
        result = run_land(repo.root, *args)
        assert result.returncode == 1
        assert result.stdout == ""


# --------------------------------------------------------------------------- gc (W10) ---------------------------------------------------------------------------
#
# One real tree per keep rule, with a clean control deleted in the same run, so a rule that stopped reading anything cannot pass. The hook modules read the fixture's own worklist and transcripts, which `gc_env` points them at.

GC_SESSION = "feedface99"
CAP_40 = "## Settings\n\n```stop-hook\nwriter_cap: 40 -- fixture\n```\n"
WORKLIST = paths.CI_DIR.parent / ".claude" / "hooks" / "stop" / "worklist.py"
IN_FLIGHT = {
    "type": "assistant",
    "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]},
}
DAY_S = 86400


def gc_env(root):
    base = root.parent
    (base / "gc-tmp").mkdir(exist_ok=True)
    return {
        **os.environ,
        "PYTHONPATH": str(paths.CI_DIR),
        paths.ROOT_ENV: str(root),
        "CLAUDE_PROJECT_DIR": str(root),
        "CLAUDE_CONFIG_DIR": str(base / "claude-config"),
        "TMPDIR": str(base / "gc-tmp"),
    }


def run_verb(root, verb, *args):
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.dev.worktree", verb, *args],
        cwd=str(paths.CI_DIR),
        env=gc_env(root),
        capture_output=True,
        text=True,
        check=False,
    )


def run_gc(root, *args):
    return run_verb(root, "gc", *args)


def row_of(stdout, name):
    """The listing row of `name`: its verdict and its reasons."""
    for line in stdout.splitlines():
        words = line.split()
        if line.startswith("  ") and len(words) > 1 and words[1] == name:
            return line
    return ""


def kept_by(stdout, name, rule):
    row = row_of(stdout, name)
    assert row.split()[:1] == ["KEEP"], row or stdout
    assert "%s:" % rule in row, row


def project_dir(root):
    munged = "".join(c if c.isalnum() and c.isascii() else "-" for c in str(root))
    return root.parent / "claude-config" / "projects" / munged


def plant_session(root, session=GC_SESSION):
    """The transcript a session with no agents has, which makes its owner known and its roster an honest zero."""
    spike.write(project_dir(root) / ("%s.jsonl" % session), "{}\n")


def plant_agent(root, agent, *, tree="", prompt="brief", session=GC_SESSION):
    """One agent of `session` as the harness lays it out, working: its last record is a tool call in flight. Returns its transcript."""
    subagents = project_dir(root) / session / "subagents"
    meta = {"agentType": "general-purpose", "description": "d", "worktreePath": str(tree)}
    spike.write(subagents / ("agent-%s.meta.json" % agent), json.dumps(meta))
    first = {"type": "user", "message": {"content": prompt}}
    jsonl = subagents / ("agent-%s.jsonl" % agent)
    spike.write(jsonl, "%s\n%s\n" % (json.dumps(first), json.dumps(IN_FLIGHT)))
    return jsonl


def plant_leased_item(root, text):
    """A live `[>]` item, through the store's real verbs."""

    def verb(*args):
        done = subprocess.run(
            [sys.executable, str(WORKLIST), *args],
            env={**gc_env(root), "WORKLIST_SESSION_ID": GC_SESSION},
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        return done.stdout

    added = verb("--add", GC_SESSION[:8], text)
    item = added.split("#", 1)[1].split()[0].strip(":,.)")
    verb("--lease", GC_SESSION[:8], item, "+60", "worker:abc123")


def gc_commit(tree, name):
    """A commit in `tree`, pinned the way the post-commit shim does. The fixture's hook directory has no such shim."""
    sha = committed(tree, name)
    pinned = run_pin_verb(tree)
    assert pinned.returncode == 0, pinned.stderr
    return sha


def land(repo, sha, key="."):
    spike.must(repo.root if key == "." else repo.root / key, "cherry-pick", "-x", sha)


def pin_of(cwd, name):
    return pin_at(cwd, spike.PIN_SPACE + name)


def snapshot(top):
    """Every entry below `top`, the `.git` file included: mode, mtime, inode, and content or link target. Symlinks are read, never followed. The link count is out: a removed sibling tree lowers it on purpose."""
    top = pathlib.Path(top)
    found = {}
    stack = [top]
    while stack:
        here = stack.pop()
        st = os.lstat(here)
        key = str(here.relative_to(top))
        if here.is_symlink():
            found[key] = (st.st_mode, os.readlink(here))
        elif here.is_dir():
            found[key] = (st.st_mode, st.st_mtime_ns)
            stack.extend(here.iterdir())
        else:
            found[key] = (st.st_mode, st.st_mtime_ns, st.st_ino, here.read_bytes())
    return found


def add_detached(root, tree):
    spike.must(root, "worktree", "add", "--detach", "--lock", str(tree), "HEAD")


def remove_by_hand(repo, tree):
    """A tree gone while its pin and record stay, as a removal by the harness leaves them."""
    store = repo.store(SUB)
    for where, target in ((store, tree / SUB), (repo.root, tree)):
        spike.must(where, "worktree", "unlock", str(target))
        spike.must(where, "worktree", "remove", "--force", str(target))
    assert not tree.exists()


def gone_everywhere(repo, name):
    """Nothing of lease `name` is left: no directory, record, pin, or admin entry in either store."""
    tree = repo.holder / name
    assert not os.path.lexists(tree)
    assert not (repo.root / ".git" / lease.RECORD_DIR / ("%s.json" % name)).exists()
    assert pin_of(repo.root, name) == ""
    store = repo.store(SUB)
    assert pin_of(store, name) == ""
    for where in (repo.root / ".git", store):
        assert not [p for p in spike.listed_trees(where) if p.startswith(str(tree))]


def admin_entries(store):
    admin = store / "worktrees"
    return sorted(p.name for p in admin.iterdir()) if admin.is_dir() else []


class Kept(NamedTuple):
    repo: spike.Repo
    trees: dict
    before: dict
    listing: subprocess.CompletedProcess
    written: subprocess.CompletedProcess


# (the tree's row name, the rule that keeps it)
KEPT_RULES = [
    ("dirty", "rule 3"),
    ("dirtysub", "rule 3"),
    ("untracked", "rule 3"),
    ("unlanded", "rule 4"),
    ("unlandedsub", "rule 4"),
    ("writer", "rule 2"),
    ("item", "rule 2"),
    ("cwd", "rule 2"),
    ("outside", "rule 1"),
    ("link", "rule 1"),
    ("0101-2", "rule 1"),
]


@pytest.fixture(scope="module")
def kept(tmp_path_factory):
    repo = make_repo(tmp_path_factory.mktemp("kept").resolve())
    root = repo.root
    spike.write(root / "agent" / "plans" / "QUEUE.md", CAP_40)
    plant_session(root)
    names = ("clean", "dirty", "dirtysub", "untracked", "unlanded", "unlandedsub", "writer")
    trees = {name: make_tree(repo, name) for name in (*names, "item", "cwd")}
    spike.write(trees["dirty"] / "code.txt", "edited\n")
    spike.write(trees["dirtysub"] / SUB / "code.txt", "edited\n")
    spike.write(trees["untracked"] / "new.txt", "new\n")
    gc_commit(trees["unlanded"], "only-here.txt")
    gc_commit(trees["unlandedsub"] / SUB, "only-here.txt")
    plant_agent(root, "aaaa1111", tree=trees["writer"])
    plant_leased_item(root, "gc fixture holds the tree named item")

    outside = root.parent / "elsewhere"
    add_detached(root, outside)
    lease._write_record(root, {"id": "outside", "path": str(outside), "owner": "feedface"})
    trees["outside"] = outside
    target = root.parent / "link-target"
    spike.write(target / "held.txt", "held\n")
    trees["link"] = repo.holder / "link"
    trees["link"].symlink_to(target)
    operator = root / ".worktrees" / "0101-2"
    add_detached(root, operator)
    trees["0101-2"] = operator

    before = {name: snapshot(tree) for name, tree in trees.items()}
    before["link-target"] = snapshot(target)
    occupant = subprocess.Popen(["sleep", "300"], cwd=str(trees["cwd"]))
    try:
        listing = run_gc(root)
        unmoved = {name: snapshot(tree) for name, tree in trees.items()}
        assert {name: unmoved[name] for name in trees} == {name: before[name] for name in trees}
        written = run_gc(root, "--write")
    finally:
        occupant.kill()
        occupant.wait()
    return Kept(repo, trees, before, listing, written)


@pytest.mark.parametrize(("name", "rule"), KEPT_RULES)
def test_gc_keeps_the_tree_by_its_rule_and_leaves_it_byte_identical(kept, name, rule):
    assert kept.listing.returncode == 0, kept.listing.stderr
    assert kept.written.returncode == 0, kept.written.stderr
    kept_by(kept.listing.stdout, name, rule)
    kept_by(kept.written.stdout, name, rule)
    assert snapshot(kept.trees[name]) == kept.before[name]


def test_gc_control_the_clean_tree_of_the_same_run_is_listed_and_then_deleted(kept):
    assert row_of(kept.listing.stdout, "clean").split()[0] == "DELETE"
    assert row_of(kept.written.stdout, "clean").split()[0] == "DELETE"
    assert not kept.trees["clean"].exists()
    assert "deleted 1" in kept.written.stdout.splitlines()[-1]


def test_gc_symlink_target_outlives_the_run(kept):
    target = kept.repo.root.parent / "link-target"
    assert snapshot(target) == kept.before["link-target"]
    assert kept.trees["link"].is_symlink()


def test_gc_kept_trees_keep_lock_pin_and_record(kept):
    root = kept.repo.root
    tree = kept.trees["unlanded"]
    assert locked_reason(root / ".git", tree) == "locked lease:unlanded"
    assert pin_of(root, "unlanded") == spike.must(tree, "rev-parse", "HEAD")
    assert (root / ".git" / lease.RECORD_DIR / "unlanded.json").is_file()
    sub_tree = kept.trees["unlandedsub"] / SUB
    assert pin_of(kept.repo.store(SUB), "unlandedsub") == spike.must(sub_tree, "rev-parse", "HEAD")


@pytest.fixture
def gc_repo(tmp_path):
    repo = make_repo(tmp_path.resolve())
    plant_session(repo.root)
    return repo


def test_gc_sc_gitlink_row_passes_and_only_write_deletes(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "sc")
    sha = gc_commit(tree / SUB, "landed.txt")
    land(repo, sha, SUB)
    status = spike.must(tree, "status", "--porcelain=v2")
    assert status.split()[:3] == ["1", ".M", "SC.."], "fixture control: %s" % status
    store = repo.store(SUB)
    before, admin = snapshot(tree), admin_entries(store)
    assert len(admin) == 1

    listing = run_gc(repo.root)
    assert listing.returncode == 0, listing.stderr
    assert row_of(listing.stdout, "sc").split()[0] == "DELETE", listing.stdout
    assert "listing only" in listing.stdout.splitlines()[-1]
    assert snapshot(tree) == before
    assert pin_of(store, "sc") == sha
    assert locked_reason(repo.root / ".git", tree) == "locked lease:sc"

    written = run_gc(repo.root, "--write")
    assert written.returncode == 0, written.stderr
    gone_everywhere(repo, "sc")
    assert admin_entries(store) == [], "the submodule's admin entry goes with its tree"
    assert spike.git(repo.root / SUB, "fsck", "--connectivity-only").returncode == 0


def test_gc_control_a_staged_gitlink_is_no_sc_row_and_keeps_the_tree(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "staged")
    land(repo, gc_commit(tree / SUB, "landed.txt"), SUB)
    spike.must(tree, "add", "--", SUB)
    kept_by(run_gc(repo.root).stdout, "staged", "rule 3")


def test_gc_control_a_staged_gitlink_moved_again_reads_sc_and_still_keeps_the_tree(gc_repo):
    """The field alone would excuse this row: `MM SC..` carries a staged change the `SC..` says nothing about."""
    repo = gc_repo
    tree = make_tree(repo, "mm")
    land(repo, gc_commit(tree / SUB, "first.txt"), SUB)
    spike.must(tree, "add", "--", SUB)
    land(repo, gc_commit(tree / SUB, "second.txt"), SUB)
    status = spike.must(tree, "status", "--porcelain=v2")
    assert status.split()[:3] == ["1", "MM", "SC.."], "fixture control: %s" % status
    kept_by(run_gc(repo.root, "--write").stdout, "mm", "rule 3")
    assert tree.is_dir()


def test_gc_submodule_commit_only_its_reflog_holds_keeps_the_tree(gc_repo):
    """Neither its pin nor HEAD reaches this commit, so only reading the submodule tree itself can see it."""
    repo = gc_repo
    tree = make_tree(repo, "sr")
    sub = tree / SUB
    base = spike.must(sub, "rev-parse", "HEAD")
    hidden = committed(sub, "hidden.txt")
    spike.must(sub, "reset", "-q", "--hard", base)
    row = row_of(run_gc(repo.root, "--write").stdout, "sr")
    assert row.split()[0] == "KEEP", row
    assert hidden[:12] in row
    assert tree.is_dir()


def test_gc_ignored_file_does_not_keep_a_tree_and_the_summary_says_so(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "ign")
    ignored = tree / "packages" / "shared" / "dist" / "own.log"
    spike.write(ignored, "a writer's own output\n")
    assert spike.out(tree, "status", "--porcelain") == "", "fixture control: the file is ignored"
    listing = run_gc(repo.root)
    assert row_of(listing.stdout, "ign").split()[0] == "DELETE", listing.stdout
    assert "ignored files do not keep a tree" in listing.stdout.splitlines()[-1]
    assert ignored.is_file()
    assert run_gc(repo.root, "--write").returncode == 0
    gone_everywhere(repo, "ign")


def test_gc_pin_of_a_removed_tree_goes_when_landed_and_stays_when_unlanded(gc_repo):
    repo = gc_repo
    spike.write(repo.root / "agent" / "plans" / "QUEUE.md", CAP_40)
    landed_tree, unlanded_tree = make_tree(repo, "pl"), make_tree(repo, "pu")
    landed = gc_commit(landed_tree, "landed.txt")
    land(repo, landed)
    held = gc_commit(unlanded_tree, "held.txt")
    remove_by_hand(repo, landed_tree)
    remove_by_hand(repo, unlanded_tree)

    listing = run_gc(repo.root)
    assert row_of(listing.stdout, "pl").split()[0] == "DELETE", listing.stdout
    kept_by(listing.stdout, "pu", "rule 4")
    assert held[:12] in row_of(listing.stdout, "pu")
    assert pin_of(repo.root, "pl") == landed, "a listing deletes nothing"

    written = run_gc(repo.root, "--write")
    assert written.returncode == 0, written.stderr
    gone_everywhere(repo, "pl")
    kept_by(written.stdout, "pu", "rule 4")
    assert pin_of(repo.root, "pu") == held
    assert spike.git(repo.root, "cat-file", "-e", held).returncode == 0
    assert (repo.root / ".git" / lease.RECORD_DIR / "pu.json").is_file()


def test_gc_pin_with_no_record_and_no_tree_is_judged_the_same(gc_repo):
    repo = gc_repo
    spike.write(repo.root / "agent" / "plans" / "QUEUE.md", CAP_40)
    a_tree, b_tree = make_tree(repo, "pa"), make_tree(repo, "pb")
    landed = gc_commit(a_tree, "landed.txt")
    land(repo, landed)
    sub_held = gc_commit(b_tree / SUB, "held.txt")
    for name, tree in (("pa", a_tree), ("pb", b_tree)):
        remove_by_hand(repo, tree)
        (repo.root / ".git" / lease.RECORD_DIR / ("%s.json" % name)).unlink()
    written = run_gc(repo.root, "--write")
    assert written.returncode == 0, written.stderr
    gone_everywhere(repo, "pa")
    kept_by(written.stdout, "pb", "rule 4")
    assert pin_of(repo.store(SUB), "pb") == sub_held


def test_gc_hard_link_in_the_main_tree_keeps_content_and_count_through_removal(gc_repo):
    repo = gc_repo
    live = repo.root / "node_modules" / "dep" / "index.js"
    content, inode, links = live.read_bytes(), live.stat().st_ino, live.stat().st_nlink
    tree = make_tree(repo, "hl")
    linked = tree / "node_modules" / "dep" / "index.js"
    assert linked.stat().st_ino == inode, "fixture control: the seed hard-linked it"
    assert live.stat().st_nlink == links + 1
    assert run_gc(repo.root, "--write", "--id", "hl").returncode == 0
    assert not tree.exists()
    assert live.read_bytes() == content
    assert live.stat().st_ino == inode
    assert live.stat().st_nlink == links


def diverged(repo, name):
    """A tree rewritten once: its pin holds the first commit and HEAD the second, on separate tips."""
    tree = make_tree(repo, name)
    base = spike.must(tree, "rev-parse", "HEAD")
    first = gc_commit(tree, "first.txt")
    spike.must(tree, "reset", "-q", "--hard", base)
    second = committed(tree, "second-attempt.txt")
    assert pin_of(repo.root, name) == first
    assert spike.git(tree, "merge-base", "--is-ancestor", first, second).returncode != 0
    return tree, first, second


def test_gc_diverged_head_and_pin_are_both_judged_while_either_is_unlanded(gc_repo):
    repo = gc_repo
    tree, first, second = diverged(repo, "dv")
    before = snapshot(tree)
    row = row_of(run_gc(repo.root, "--write").stdout, "dv")
    assert row.split()[0] == "KEEP", row
    assert first[:12] in row
    assert second[:12] in row
    assert "2 unlanded commit(s)" in row
    assert "does not descend" in row

    land(repo, second)
    row = row_of(run_gc(repo.root, "--write").stdout, "dv")
    assert row.split()[0] == "KEEP", "the pin's tip is unlanded: %s" % row
    assert "1 unlanded commit(s): %s" % first[:12] in row
    assert snapshot(tree) == before
    assert pin_of(repo.root, "dv") == first

    land(repo, first)
    assert row_of(run_gc(repo.root).stdout, "dv").split()[0] == "DELETE"
    assert run_gc(repo.root, "--write").returncode == 0
    gone_everywhere(repo, "dv")


def test_gc_diverged_with_only_the_pin_landed_keeps_heads_tip(gc_repo):
    repo = gc_repo
    _tree, first, second = diverged(repo, "dh")
    land(repo, first)
    row = row_of(run_gc(repo.root, "--write").stdout, "dh")
    assert row.split()[0] == "KEEP", row
    assert "1 unlanded commit(s): %s" % second[:12] in row


def test_gc_commit_only_the_reflog_holds_keeps_the_tree(gc_repo):
    repo = gc_repo
    tree, first, second = diverged(repo, "rl")
    base = spike.must(tree, "rev-parse", "HEAD~1")
    spike.must(tree, "reset", "-q", "--hard", base)
    third = committed(tree, "third-attempt.txt")
    land(repo, first)
    land(repo, third)
    row = row_of(run_gc(repo.root, "--write").stdout, "rl")
    assert row.split()[0] == "KEEP", row
    assert second[:12] in row
    land(repo, second)
    assert row_of(run_gc(repo.root).stdout, "rl").split()[0] == "DELETE"


def test_gc_merge_keeps_the_tree_though_its_parents_read_landed(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "mg")
    base = spike.must(tree, "rev-parse", "HEAD")
    one = committed(tree, "one.txt")
    spike.must(tree, "checkout", "-q", "--detach", base)
    other = committed(tree, "other.txt")
    spike.must(tree, "merge", "--no-gpg-sign", "--no-ff", "-q", "-m", "m", one)
    land(repo, one)
    land(repo, other)
    row = row_of(run_gc(repo.root, "--write").stdout, "mg")
    assert row.split()[0] == "KEEP", row
    assert "merge" in row


def test_gc_gitlink_directory_with_files_and_no_git_keeps_the_tree(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "ng")
    (tree / SUB / ".git").unlink()
    spike.write(tree / SUB / "invisible.txt", "written by hand\n")
    kept_by(run_gc(repo.root, "--write").stdout, "ng", "rule 3")
    assert (tree / SUB / "invisible.txt").is_file()


def test_gc_live_writer_named_only_by_its_first_prompt_holds_the_tree(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "pr")
    plant_agent(repo.root, "bbbb2222", prompt="Your tree is %s, commit there." % tree)
    row = row_of(run_gc(repo.root, "--write").stdout, "pr")
    assert "the live writer bbbb2222" in row, row
    assert tree.is_dir()


def test_gc_control_a_finished_writer_holds_nothing(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "fw")
    jsonl = plant_agent(repo.root, "cccc3333", tree=tree)
    stale = jsonl.stat().st_mtime - DAY_S
    os.utime(jsonl, (stale, stale))
    assert row_of(run_gc(repo.root).stdout, "fw").split()[0] == "DELETE"


def test_gc_owner_nothing_can_vouch_for_keeps_the_tree_and_a_cli_owner_does_not(gc_repo):
    repo = gc_repo
    spike.write(repo.root / "agent" / "plans" / "QUEUE.md", CAP_40)
    assert run_lease(repo.root, "--name", "gh", "--owner", "ghost123").returncode == 0
    assert run_lease(repo.root, "--name", "op", "--owner", lease.DEFAULT_OWNER).returncode == 0
    listing = run_gc(repo.root).stdout
    kept_by(listing, "gh", "rule 2")
    assert "ghost123" in row_of(listing, "gh")
    assert row_of(listing, "op").split()[0] == "DELETE", listing


def test_gc_directory_with_no_record_may_be_a_lease_being_made(gc_repo):
    repo = gc_repo
    empty = repo.holder / "making"
    empty.mkdir(parents=True)
    written = run_gc(repo.root, "--write").stdout
    kept_by(written, "making", "rule 2")
    assert "no record" in row_of(written, "making")
    assert empty.is_dir()


def test_gc_unreadable_record_and_broken_git_file_keep_the_tree(gc_repo):
    repo = gc_repo
    spike.write(repo.root / "agent" / "plans" / "QUEUE.md", CAP_40)
    bad_record, bad_git = make_tree(repo, "br"), make_tree(repo, "bg")
    (repo.root / ".git" / lease.RECORD_DIR / "br.json").write_text("{not json", encoding="utf-8")
    (bad_git / ".git").write_text("gitdir: /no/such/place\n", encoding="utf-8")
    written = run_gc(repo.root, "--write").stdout
    kept_by(written, "br", "rule 2")
    kept_by(written, "bg", "rule 1")
    assert bad_record.is_dir()
    assert bad_git.is_dir()


def test_gc_record_naming_another_path_is_never_followed(gc_repo):
    repo = gc_repo
    victim = repo.root.parent / "victim"
    spike.write(victim / "kept.txt", "kept\n")
    (repo.root / ".git" / lease.RECORD_DIR).mkdir(exist_ok=True)
    lease._write_record(repo.root, {"id": "far", "path": str(victim), "owner": "feedface"})
    kept_by(run_gc(repo.root, "--write").stdout, "far", "rule 1")
    assert (victim / "kept.txt").is_file()


def test_gc_id_narrows_the_run_and_exits_1_when_that_lease_was_kept(gc_repo):
    repo = gc_repo
    spike.write(repo.root / "agent" / "plans" / "QUEUE.md", CAP_40)
    clean, dirty = make_tree(repo, "ca"), make_tree(repo, "db")
    spike.write(dirty / "code.txt", "edited\n")

    narrowed = run_gc(repo.root, "--id", "ca")
    assert narrowed.returncode == 0
    assert row_of(narrowed.stdout, "db") == ""

    refused = run_gc(repo.root, "--id", "db", "--write")
    assert refused.returncode == 1
    kept_by(refused.stdout, "db", "rule 3")
    assert clean.is_dir(), "`--id` names one lease"

    assert run_gc(repo.root, "--write", "--id", "ca").returncode == 0
    gone_everywhere(repo, "ca")
    assert dirty.is_dir()


@pytest.mark.parametrize(
    "args", [("--bogus",), ("surplus",), ("--id",), ("--id", "../x"), ("--id", "missing")]
)
def test_gc_bad_argument_exits_1_and_lists_nothing(gc_repo, args):
    tree = make_tree(gc_repo, "ba")
    before = snapshot(tree)
    result = run_gc(gc_repo.root, *args, "--write")
    assert result.returncode == 1
    assert result.stdout == ""
    assert snapshot(tree) == before


def test_gc_refuses_from_a_lease_and_with_a_symlinked_holder(gc_repo, tmp_path):
    repo = gc_repo
    tree = make_tree(repo, "ro")
    from_lease = run_gc(tree)
    assert from_lease.returncode == 1
    assert "not a main checkout" in from_lease.stderr

    other = tmp_path / "other-holder"
    moved = repo.holder.rename(other)
    repo.holder.symlink_to(moved)
    refused = run_gc(repo.root, "--write")
    assert refused.returncode == 1
    assert "symlink" in refused.stderr
    assert (other / "ro").is_dir()


def test_gc_several_live_branches_refuse_the_whole_run(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "lb")
    spike.must(repo.root, "switch", "-q", "main")
    spike.must(repo.root, "branch", "0101-2", BRANCH)
    result = run_gc(repo.root, "--write")
    assert result.returncode == 1, result.stdout
    assert "several live branches" in result.stderr
    assert tree.is_dir()


def test_gc_help_and_listing_of_nothing_touch_nothing(gc_repo):
    repo = gc_repo
    for flag in ("--help", "-h"):
        shown = run_gc(repo.root, flag)
        assert shown.returncode == 0
        assert shown.stdout.startswith("Usage: ./run.sh worktree gc")
    assert not repo.holder.exists() or list(repo.holder.iterdir()) == []
    empty = run_gc(repo.root)
    assert empty.returncode == 0
    assert empty.stdout.startswith("0 row(s)")
    for verb in ("land", "leases", "gc"):
        assert verb in run_verb(repo.root, "help").stdout


# --------------------------------------------------------------------------- leases ---------------------------------------------------------------------------


def test_leases_json_names_owner_base_dirty_and_unlanded_per_repo(gc_repo):
    repo = gc_repo
    tree = make_tree(repo, "ls")
    console = gc_commit(tree, "held.txt")
    sub = gc_commit(tree / SUB, "held-sub.txt")
    spike.write(tree / "code.txt", "edited\n")
    spike.write(tree / SUB / "code.txt", "edited\n")
    before = snapshot(tree)

    result = run_verb(repo.root, "leases", "--json")
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert [row["id"] for row in rows] == ["ls"]
    row = rows[0]
    assert row["owner"] == "feedface"
    assert row["path"] == str(tree)
    assert row["exists"] is True
    assert row["base"]["."] == spike.must(tree, "rev-parse", "HEAD~1")
    assert row["unlanded"] == {".": [console], SUB: [sub]}
    assert row["dirty"] == 3, "one console path, one submodule path, and the gitlink's own row"
    assert snapshot(tree) == before


def test_leases_text_has_one_line_per_lease_and_says_when_the_tree_is_gone(gc_repo):
    repo = gc_repo
    spike.write(repo.root / "agent" / "plans" / "QUEUE.md", CAP_40)
    assert run_verb(repo.root, "leases").stdout == "no leases\n"
    tree = make_tree(repo, "lt")
    held = gc_commit(tree, "held.txt")
    make_tree(repo, "lu")
    remove_by_hand(repo, tree)
    result = run_verb(repo.root, "leases")
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert len(lines) == 2
    assert lines[0].split()[0] == "lt"
    assert "owner feedface" in lines[0]
    assert ". 1 (%s)" % held[:12] in lines[0]
    assert "no tree on disk" in lines[0]
    assert "unlanded: none" in lines[1]


def test_leases_refuses_an_unknown_option(gc_repo):
    result = run_verb(gc_repo.root, "leases", "--bogus")
    assert result.returncode == 1
    assert result.stdout == ""


# --------------------------------------------------------------------------- review findings of `make_lease` ---------------------------------------------------------------------------


def test_lease_submodule_with_no_module_store_is_refused_and_leaves_nothing(repo):
    """Review d52243fa.2: the help promises each submodule at its gitlink, so an empty directory is a refusal."""
    store = repo.store(SUB)
    spike.must(repo.root, "submodule", "deinit", "-q", "-f", "--", SUB)
    spike.remove_dir(store, repo.root / ".git")
    assert (repo.root / SUB).is_dir()
    assert list((repo.root / SUB).iterdir()) == [], "fixture control: an uninitialized submodule"
    result = run_lease(repo.root, "--name", "t")
    assert result.returncode == 1, result.stdout
    assert "no module store for %s" % SUB in result.stderr
    assert "git submodule update --init" in result.stderr
    assert result.stdout == ""
    assert holder_names(repo) == []
    assert not (repo.root / ".git" / lease.RECORD_DIR / "t.json").exists()


def test_lease_exclude_failure_leaves_no_directory_holding_a_slot(repo):
    """Review d52243fa.4: the reservation's last step is the directory, so a failure before it reserves nothing."""
    exclude = repo.root / ".git" / "info" / "exclude"
    exclude.unlink()
    exclude.mkdir()
    result = run_lease(repo.root, "--name", "t")
    assert result.returncode == 1, result.stdout
    assert "refused" in result.stderr
    assert holder_names(repo) == []


@pytest.mark.parametrize("session", ["../evil1", "a/b/c/d/", ".hidden1", "spike-x1"])
def test_lease_session_id_that_is_no_path_component_is_refused(repo, session):
    """Review d52243fa.5: the default owner names a directory exactly as `--owner` does."""
    result = run_lease(repo.root, WORKLIST_SESSION_ID=session)
    assert result.returncode == 1, result.stdout
    assert "--owner" in result.stderr
    assert result.stdout == ""
    assert holder_names(repo) == []
    assert not (repo.root / ".claude" / "evil1-1").exists()
    named = run_lease(repo.root, "--owner", "abcd1234", WORKLIST_SESSION_ID=session)
    assert named.returncode == 0, named.stderr
