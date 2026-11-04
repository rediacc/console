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
