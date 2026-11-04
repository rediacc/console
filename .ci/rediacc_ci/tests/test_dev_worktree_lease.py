"""`./run.sh worktree lease` in throwaway repositories (PLAN-worktree-lease W2).

Nothing here touches a real checkout: `$REDIACC_CI_ROOT` points the verb at a fixture from W0's `worktree_spike.build_fixture`, whose submodule gitlink sits on a commit no remote holds. The code under test, `lease-seed.ts` and `tsx` still come from this checkout, so the seed is the real one.
"""

from __future__ import annotations

import json
import os
import pathlib
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
