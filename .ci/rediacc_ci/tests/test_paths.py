"""Controls for rediacc_ci.paths.

EVERY ASSERTION HERE IS A PAIR, which is the house style of the five control
files this package is replacing and is not a formality. A resolver that returned
the same constant for every input would satisfy "the override is honoured" on its
own; the paired control is that WITHOUT the override the answer is different. The
same shape covers the nested-repo case, the `.git`-as-a-file case and the
idempotence of the sys.path hop.

The two facts pinned here that cost something to learn elsewhere in this tree:

  * `.git` IS A FILE in a git worktree, and every session in this repo works in
    one. An `is_dir()` marker test reports "not a repository" in the commonest
    case there is. `test_looks_like_repo_root_accepts_a_worktree_git_file` is the
    control for that, paired with the ordinary `.git` directory.
  * A REPOSITORY INSIDE A REPOSITORY is normal here (`private/renet` is a
    submodule, `private/growth` a gitignored sibling checkout), and an upward
    walk from a path under one of them answers with the INNER repo. The Stop
    hook has the receipt: a session on branch 0804-1 was told to bootstrap
    `agent/main/` because private/growth happened to be on main.
    `test_find_repo_root_stops_at_the_inner_repo` pins that behaviour so the
    docstring's warning is a measured fact rather than a caution.
"""

import os
import pathlib
import sys

import pytest

from rediacc_ci import paths


def make_repo(root: pathlib.Path, *, git_as_file: bool = False) -> pathlib.Path:
    """The three markers `looks_like_repo_root` asks for, and nothing else."""
    root.mkdir(parents=True, exist_ok=True)
    (root / ".ci").mkdir(exist_ok=True)
    (root / "package.json").write_text("{}\n", encoding="utf-8")
    if git_as_file:
        # Exactly what `git worktree add` writes: a pointer, not a directory.
        (root / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
    else:
        (root / ".git").mkdir(exist_ok=True)
    return root


# --------------------------------------------------------------------------- 1. repo_root: the static derivation ---------------------------------------------------------------------------


def test_repo_root_is_the_tree_this_file_lives_in():
    root = paths.repo_root()
    assert (root / ".ci" / "rediacc_ci" / "paths.py").is_file()


def test_repo_root_is_absolute_and_resolved():
    root = paths.repo_root()
    assert root.is_absolute()
    # CONTROL for the `os.path.join(dirname, "..", "..", "..")` idiom this module replaces: that form leaves the `..` segments in the string, so the result compares unequal to the pathlib form for the very same directory.
    assert ".." not in root.parts
    assert root == root.resolve()


def test_package_dir_and_ci_dir_agree_with_the_root():
    assert paths.PACKAGE_DIR.name == "rediacc_ci"
    assert paths.CI_DIR.name == ".ci"
    assert paths.PACKAGE_DIR.parent == paths.CI_DIR
    assert paths.CI_DIR.parent == paths.repo_root()


# --------------------------------------------------------------------------- 2. repo_root: the one environment override ---------------------------------------------------------------------------


def test_root_env_override_is_honoured(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert paths.repo_root() == tmp_path.resolve()


def test_without_the_override_the_answer_is_different(tmp_path, monkeypatch):
    """CONTROL for the test above.

    Without this, a `repo_root` hard-wired to return its argument -- or one that
    ignored the environment entirely while the test happened to run inside
    tmp_path -- would pass the override assertion while resolving nothing.
    """
    monkeypatch.delenv(paths.ROOT_ENV, raising=False)
    assert paths.repo_root() != tmp_path.resolve()


def test_an_override_that_is_not_a_directory_raises(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path / "no-such-tree"))
    with pytest.raises(paths.RootError):
        paths.repo_root()


def test_an_override_pointing_at_a_file_raises(tmp_path, monkeypatch):
    target = tmp_path / "a-file"
    target.write_text("", encoding="utf-8")
    monkeypatch.setenv(paths.ROOT_ENV, str(target))
    with pytest.raises(paths.RootError):
        paths.repo_root()


def test_the_raise_names_the_variable_so_the_operator_can_act():
    """The message is the fix. A RootError that does not say which variable is
    wrong sends the reader hunting through eight per-gate names.
    """
    err = paths.RootError("%s=/nope is not a directory" % paths.ROOT_ENV)
    assert paths.ROOT_ENV in str(err)


def test_an_empty_override_falls_back_rather_than_raising(monkeypatch):
    """`FOO= ./gate` is how a shell UNSETS a variable for one command in
    practice, and treating that as "you pointed me at nothing" would refuse every
    such invocation. Empty is absent.
    """
    monkeypatch.setenv(paths.ROOT_ENV, "")
    assert paths.repo_root() == paths.CI_DIR.parent


# --------------------------------------------------------------------------- 3. The derived directories follow the override, because they are functions ---------------------------------------------------------------------------


def test_derived_directories_follow_the_override(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    assert paths.ci_dir() == tmp_path.resolve() / ".ci"
    assert paths.quality_dir() == tmp_path.resolve() / ".ci" / "scripts" / "quality"
    assert paths.hooks_stop_dir() == tmp_path.resolve() / ".claude" / "hooks" / "stop"


def test_derived_directories_exist_in_the_real_tree(monkeypatch):
    """CONTROL: the paths above are not merely well-formed strings.

    A typo in any of the three joins produces a perfectly valid Path that names
    nothing, and the override test cannot see that because its fixture has no
    subdirectories either.
    """
    monkeypatch.delenv(paths.ROOT_ENV, raising=False)
    assert paths.ci_dir().is_dir()
    assert paths.quality_dir().is_dir()
    assert paths.hooks_stop_dir().is_dir()


def test_an_explicit_root_argument_beats_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    other = tmp_path / "other"
    other.mkdir()
    assert paths.ci_dir(other) == other / ".ci"


def test_from_root_joins_under_the_root():
    assert paths.from_root("a", "b") == paths.repo_root() / "a" / "b"


def test_from_root_with_no_parts_is_the_root():
    assert paths.from_root() == paths.repo_root()


# --------------------------------------------------------------------------- 4. relative_to_root: the fallback matters as much as the happy path ---------------------------------------------------------------------------


def test_relative_to_root_shortens_an_in_repo_path():
    # Compared through pathlib rather than against a "/"-joined literal, so this asserts the SHAPE on every platform instead of asserting the separator.
    want = str(pathlib.Path(".ci") / "rediacc_ci" / "paths.py")
    assert paths.relative_to_root(paths.PACKAGE_DIR / "paths.py") == want


def test_relative_to_root_returns_a_repo_relative_string_not_a_path():
    got = paths.relative_to_root(paths.PACKAGE_DIR / "paths.py")
    assert isinstance(got, str)
    assert not pathlib.Path(got).is_absolute()


def test_relative_to_root_falls_back_instead_of_raising(tmp_path):
    """A path outside the repo must PRINT, not raise.

    This is called from inside failure reports, which is the least useful place
    for a ValueError: the gate would die formatting the message that says what
    is wrong instead of showing it.
    """
    outside = tmp_path / "elsewhere.txt"
    outside.write_text("", encoding="utf-8")
    assert paths.relative_to_root(outside) == str(outside.resolve())


def test_relative_to_root_accepts_a_plain_string():
    assert paths.relative_to_root(str(paths.PACKAGE_DIR)) == str(pathlib.Path(".ci") / "rediacc_ci")


# --------------------------------------------------------------------------- 5. looks_like_repo_root, and the worktree case that breaks the obvious test ---------------------------------------------------------------------------


def test_looks_like_repo_root_accepts_the_real_tree():
    assert paths.looks_like_repo_root(paths.repo_root())


def test_looks_like_repo_root_rejects_a_bare_directory(tmp_path):
    assert not paths.looks_like_repo_root(tmp_path)


def test_looks_like_repo_root_accepts_a_worktree_git_file(tmp_path):
    """THE CASE AN `is_dir()` MARKER GETS WRONG.

    `git worktree add` writes `.git` as a FILE holding a gitdir pointer. Every
    session in this repo works in a worktree, so this is not the exotic case, it
    is the normal one.
    """
    assert paths.looks_like_repo_root(make_repo(tmp_path / "wt", git_as_file=True))


def test_looks_like_repo_root_accepts_an_ordinary_git_directory(tmp_path):
    assert paths.looks_like_repo_root(make_repo(tmp_path / "plain"))


def test_looks_like_repo_root_needs_all_three_markers(tmp_path):
    """CONTROL: any ONE marker alone must not be enough.

    Without this the function could be `(p / ".git").exists()` and every test
    above would still pass, while `find_repo_root` would stop at the first
    checkout of anything it met on the way up.
    """
    root = make_repo(tmp_path / "partial")
    (root / "package.json").unlink()
    assert not paths.looks_like_repo_root(root)


def test_the_anti_vacuity_fixture_shape_is_not_a_repo_root(tmp_path):
    """WHY repo_root() DOES NOT VALIDATE MARKERS.

    test-gate-anti-vacuity.sh copies `.ci/rediacc_ci` into a tempdir with no
    `.git` and no package.json, then requires gates to run there. This asserts
    that such a tree really does fail the marker test, which is the measurement
    behind the resolver's decision not to apply one.
    """
    fixture = tmp_path / "fixture"
    (fixture / ".ci" / "rediacc_ci").mkdir(parents=True)
    assert not paths.looks_like_repo_root(fixture)


# --------------------------------------------------------------------------- 6. find_repo_root: the upward walk, and the nested-repo trap ---------------------------------------------------------------------------


def test_find_repo_root_walks_up_to_the_marked_directory(tmp_path):
    root = make_repo(tmp_path / "outer")
    deep = root / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert paths.find_repo_root(deep) == root.resolve()


def test_find_repo_root_accepts_a_file_and_starts_from_its_directory(tmp_path):
    root = make_repo(tmp_path / "outer")
    f = root / "a" / "thing.py"
    f.parent.mkdir(parents=True)
    f.write_text("", encoding="utf-8")
    assert paths.find_repo_root(f) == root.resolve()


def test_find_repo_root_stops_at_the_inner_repo(tmp_path):
    """THE NESTED-REPO TRAP, pinned as behaviour rather than left as a warning.

    `private/renet` is a submodule and `private/growth` a gitignored sibling
    checkout, so a start path under either answers with the inner tree. That is
    correct for "the nearest repository" and wrong for "this repository", which
    is exactly why repo_root() does not walk.
    """
    outer = make_repo(tmp_path / "outer")
    inner = make_repo(outer / "private" / "inner")
    assert paths.find_repo_root(inner / "src") == inner.resolve()
    # CONTROL: the same walk from a sibling directory that is NOT inside the inner repo lands on the outer one, so the assertion above is about nesting and not about make_repo returning its own argument.
    (outer / "packages").mkdir()
    assert paths.find_repo_root(outer / "packages") == outer.resolve()


def test_find_repo_root_returns_none_when_nothing_matches(tmp_path):
    """None, not a guess. A guessed root reads as valid and finds nothing in it."""
    bare = tmp_path / "nowhere" / "deep"
    bare.mkdir(parents=True)
    assert paths.find_repo_root(bare) is None


def test_find_repo_root_finds_the_real_tree_from_this_test_file():
    assert paths.find_repo_root(__file__) == paths.repo_root()


# --------------------------------------------------------------------------- 7. on_sys_path: the replacement for 33 hand-written hops ---------------------------------------------------------------------------


def test_on_sys_path_puts_the_directory_first(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    got = paths.on_sys_path(tmp_path)
    assert sys.path[0] == got == str(tmp_path.resolve())


def test_on_sys_path_is_idempotent(tmp_path, monkeypatch):
    """THE ONE BEHAVIOURAL DIFFERENCE FROM THE HOPS IT REPLACES.

    `sys.path.insert(0, d)` in a module imported twice -- once as `__main__` and
    once by name, which is what happens when one gate imports another -- leaves
    two copies of the directory on the path.
    """
    monkeypatch.setattr(sys, "path", list(sys.path))
    paths.on_sys_path(tmp_path)
    paths.on_sys_path(tmp_path)
    assert sys.path.count(str(tmp_path.resolve())) == 1


def test_on_sys_path_does_not_disturb_the_rest_of_the_path(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    before = list(sys.path)
    paths.on_sys_path(tmp_path)
    assert sys.path[1:] == before


def test_ensure_importable_returns_the_ci_directory(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv(paths.ROOT_ENV, raising=False)
    assert paths.ensure_importable() == str(paths.CI_DIR)
    assert str(paths.CI_DIR) in sys.path


def test_ensure_importable_actually_makes_the_package_importable(monkeypatch):
    """CONTROL: the returned directory is the one `import rediacc_ci` needs.

    A path that merely looks right proves nothing; this asserts the package file
    is really under it.
    """
    monkeypatch.delenv(paths.ROOT_ENV, raising=False)
    assert (pathlib.Path(paths.ensure_importable()) / "rediacc_ci" / "__init__.py").is_file()


# --------------------------------------------------------------------------- 8. walk_tree: the peer-checkout prune, and what must still be collected ---------------------------------------------------------------------------


def collect(root: pathlib.Path, **kwargs) -> set[str]:
    """Every file `walk_tree` reaches under `root`, as root-relative posix strings."""
    found: set[str] = set()
    for dirpath, _dirnames, filenames in paths.walk_tree(root, **kwargs):
        for name in filenames:
            found.add((pathlib.Path(dirpath) / name).relative_to(root).as_posix())
    return found


def make_corpus(root: pathlib.Path) -> pathlib.Path:
    """One real file, and its identical twin inside a fake peer worktree.

    The two files are BYTE-IDENTICAL and differ only in where they sit, which is
    the whole point: the 2026-09-13 incident was one real file scanned twice, and
    a fixture whose copies differed would let a gate pass by telling them apart on
    content rather than on location.
    """
    body = "replace github.com/rediacc/renet => ../../private/renet\n"
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "go.mod").write_text(body, encoding="utf-8")
    peer = root / ".claude" / "worktrees" / "agent-deadbeef" / "pkg"
    peer.mkdir(parents=True, exist_ok=True)
    (peer / "go.mod").write_text(body, encoding="utf-8")
    return root


def test_a_file_inside_claude_worktrees_is_not_collected(tmp_path):
    """THE DEFECT THIS HELPER EXISTS FOR.

    `.claude/worktrees/` holds sibling checkouts of this same repository for
    isolated sub-agent sessions. `.git/info/exclude:11` hides them from
    `git ls-files` and from every CI checkout, so a gate that walks the raw
    filesystem judges a peer's tree and nobody else can reproduce the verdict.
    """
    assert "\n".join(sorted(collect(make_corpus(tmp_path)))) == "pkg/go.mod"


def test_the_identical_file_outside_that_path_is_collected(tmp_path):
    """THE OTHER HALF, and without it the test above passes on a helper that
    returns the empty set for everything.

    Asserted as an equality rather than a membership, so a prune that took the
    whole tree with it fails here instead of quietly widening.
    """
    root = make_corpus(tmp_path)
    assert collect(root) == {"pkg/go.mod"}
    assert (root / ".claude" / "worktrees" / "agent-deadbeef" / "pkg" / "go.mod").is_file()


def test_a_root_inside_a_worktrees_path_still_walks(tmp_path):
    """THE CASE A NAIVE PRUNE TURNS INTO A FALSE GREEN.

    Every isolated sub-agent in this repo has a repo root of
    `<main>/.claude/worktrees/agent-xxxx`, so a prune written as "reject any path
    containing .claude/worktrees" would make every gate in such a session scan
    NOTHING and exit 0. Pruning descendants only is what keeps that from
    happening, and this pins it.
    """
    root = tmp_path / ".claude" / "worktrees" / "agent-self"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("", encoding="utf-8")
    assert collect(root) == {"src/a.py"}


def test_a_nested_peer_worktree_is_still_pruned_from_such_a_root(tmp_path):
    """CONTROL for the test above: walking from inside a worktree must not switch
    the prune off wholesale. A sub-agent's own tree can hold a peer of its own.
    """
    root = tmp_path / ".claude" / "worktrees" / "agent-self"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("", encoding="utf-8")
    nested = root / ".claude" / "worktrees" / "agent-peer"
    nested.mkdir(parents=True)
    (nested / "b.py").write_text("", encoding="utf-8")
    assert collect(root) == {"src/a.py"}


def test_a_root_with_a_trailing_separator_still_prunes(tmp_path):
    """`os.path.basename(".claude/")` IS THE EMPTY STRING.

    The pair prune matches on the parent directory's NAME, so a root handed in
    with a trailing separator would miss the match at the top level, which is
    exactly the level a caller walking `.claude` prunes from. Passed as a raw
    string rather than a Path because pathlib normalises the separator away and
    would make this control pass without the fix.
    """
    (tmp_path / ".claude" / "worktrees" / "peer").mkdir(parents=True)
    (tmp_path / ".claude" / "worktrees" / "peer" / "x.sh").write_text("", encoding="utf-8")
    (tmp_path / ".claude" / "keep.sh").write_text("", encoding="utf-8")
    root = str(tmp_path / ".claude") + os.sep
    found = {
        os.path.relpath(os.path.join(d, n), root)
        for d, _dirs, files in paths.walk_tree(root)
        for n in files
    }
    assert found == {"keep.sh"}


def test_git_and_node_modules_are_pruned_too(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("", encoding="utf-8")
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "index.js").write_text("", encoding="utf-8")
    (tmp_path / "keep.js").write_text("", encoding="utf-8")
    assert collect(tmp_path) == {"keep.js"}


def test_a_directory_merely_named_worktrees_is_kept(tmp_path):
    """`worktrees` IS PRUNED ONLY UNDER `.claude`, and that is not pedantry.

    Pruning the bare name at any depth would silently drop a real
    `docs/worktrees/` from a gate's corpus, which is the same invisible
    corpus-loss the helper exists to prevent, pointed the other way.
    """
    (tmp_path / "docs" / "worktrees").mkdir(parents=True)
    (tmp_path / "docs" / "worktrees" / "guide.md").write_text("", encoding="utf-8")
    assert collect(tmp_path) == {"docs/worktrees/guide.md"}


def test_a_dot_worktrees_directory_is_pruned(tmp_path):
    """`scripts/dev/worktree.sh` puts checkouts at `$ROOT_DIR/.worktrees` and
    `.gitignore:146` excludes them. Same bug, second spelling.
    """
    (tmp_path / ".worktrees" / "0824-1").mkdir(parents=True)
    (tmp_path / ".worktrees" / "0824-1" / "go.mod").write_text("", encoding="utf-8")
    (tmp_path / "go.mod").write_text("", encoding="utf-8")
    assert collect(tmp_path) == {"go.mod"}


def test_exclude_dirs_adds_to_the_standing_prune_rather_than_replacing_it(tmp_path):
    """A caller passing its own exclusion must not switch the built-in one off.

    `dead_python` passes `__pycache__` and `agent_browser_exit` passes `dist`;
    if either replaced the defaults, this whole fix would be off for those two.
    """
    make_corpus(tmp_path)
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "bundle.js").write_text("", encoding="utf-8")
    assert collect(tmp_path, exclude_dirs=("dist",)) == {"pkg/go.mod"}


def test_the_yielded_dirnames_list_is_mutated_in_place(tmp_path):
    """CALL SITES SORT `dirnames` TO STEER THE WALK, and that only works because
    the helper mutates the list `os.walk` still holds rather than handing back a
    new one. `no_app_admin_perm`, `agent_browser_exit` and `e2e_coverage` all do
    it for deterministic output.
    """
    for name in ("b", "a", "node_modules"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "f.txt").write_text("", encoding="utf-8")
    order: list[str] = []
    for dirpath, dirnames, _filenames in paths.walk_tree(tmp_path):
        dirnames.sort()
        if dirpath != str(tmp_path):
            order.append(pathlib.Path(dirpath).name)
    assert order == ["a", "b"]


def test_walk_tree_does_not_follow_directory_symlinks(tmp_path):
    """`grep -r` (not `-R`) and `find -P` semantics, which the ports depend on."""
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "f.txt").write_text("", encoding="utf-8")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    assert collect(tmp_path) == {"real/f.txt"}


def test_a_missing_root_yields_nothing_rather_than_raising(tmp_path):
    """Several callers rely on this to match a twin's `2>/dev/null`. It is NOT a
    vacuity hole being blessed: the anti-vacuity floor is per gate, because only
    the caller knows how big its corpus has to be. See the helper's docstring.
    """
    assert collect(tmp_path / "no-such-dir") == set()


def test_the_real_tree_walk_is_not_trivially_empty():
    """ANTI-VACUITY FOR THIS CONTROL FILE ITSELF.

    Every assertion above runs on a tmp_path fixture, and all of them would pass
    against a helper that yielded nothing on a real tree. This is the one that
    would not.
    """
    root = paths.repo_root()
    dirs = [dirpath for dirpath, _d, _f in paths.walk_tree(root)]
    assert len(dirs) > 100, "walk_tree saw %d directories in the real tree" % len(dirs)
    # And nothing it reached is inside a peer checkout. Compared on the path RELATIVE TO ROOT, because this very session's root is itself `<main>/.claude/worktrees/agent-xxxx`: an absolute-path test would match the root on every directory and pass for entirely the wrong reason.
    inside = [
        d
        for d in dirs
        for parts in [pathlib.Path(d).relative_to(root).parts]
        if any(parts[i : i + 2] == (".claude", "worktrees") for i in range(len(parts)))
    ]
    assert inside == []


# --------------------------------------------------------------------------- 9. The exported surface ---------------------------------------------------------------------------


def test_everything_in_dunder_all_exists():
    """An `__all__` naming something that was renamed is a broken star-import
    that nothing else in this repo would notice.
    """
    missing = [name for name in paths.__all__ if not hasattr(paths, name)]
    assert missing == []


def test_dunder_all_is_not_empty():
    """CONTROL for the test above, which passes trivially over an empty list."""
    assert len(paths.__all__) >= 10
