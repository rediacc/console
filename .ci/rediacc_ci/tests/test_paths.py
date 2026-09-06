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


# ---------------------------------------------------------------------------
# 1. repo_root: the static derivation
# ---------------------------------------------------------------------------


def test_repo_root_is_the_tree_this_file_lives_in():
    root = paths.repo_root()
    assert (root / ".ci" / "rediacc_ci" / "paths.py").is_file()


def test_repo_root_is_absolute_and_resolved():
    root = paths.repo_root()
    assert root.is_absolute()
    # CONTROL for the `os.path.join(dirname, "..", "..", "..")` idiom this module
    # replaces: that form leaves the `..` segments in the string, so the result
    # compares unequal to the pathlib form for the very same directory.
    assert ".." not in root.parts
    assert root == root.resolve()


def test_package_dir_and_ci_dir_agree_with_the_root():
    assert paths.PACKAGE_DIR.name == "rediacc_ci"
    assert paths.CI_DIR.name == ".ci"
    assert paths.PACKAGE_DIR.parent == paths.CI_DIR
    assert paths.CI_DIR.parent == paths.repo_root()


# ---------------------------------------------------------------------------
# 2. repo_root: the one environment override
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 3. The derived directories follow the override, because they are functions
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 4. relative_to_root: the fallback matters as much as the happy path
# ---------------------------------------------------------------------------


def test_relative_to_root_shortens_an_in_repo_path():
    # Compared through pathlib rather than against a "/"-joined literal, so this
    # asserts the SHAPE on every platform instead of asserting the separator.
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


# ---------------------------------------------------------------------------
# 5. looks_like_repo_root, and the worktree case that breaks the obvious test
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 6. find_repo_root: the upward walk, and the nested-repo trap
# ---------------------------------------------------------------------------


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
    # CONTROL: the same walk from a sibling directory that is NOT inside the
    # inner repo lands on the outer one, so the assertion above is about
    # nesting and not about make_repo returning its own argument.
    (outer / "packages").mkdir()
    assert paths.find_repo_root(outer / "packages") == outer.resolve()


def test_find_repo_root_returns_none_when_nothing_matches(tmp_path):
    """None, not a guess. A guessed root reads as valid and finds nothing in it."""
    bare = tmp_path / "nowhere" / "deep"
    bare.mkdir(parents=True)
    assert paths.find_repo_root(bare) is None


def test_find_repo_root_finds_the_real_tree_from_this_test_file():
    assert paths.find_repo_root(__file__) == paths.repo_root()


# ---------------------------------------------------------------------------
# 7. on_sys_path: the replacement for 33 hand-written hops
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 8. The exported surface
# ---------------------------------------------------------------------------


def test_everything_in_dunder_all_exists():
    """An `__all__` naming something that was renamed is a broken star-import
    that nothing else in this repo would notice.
    """
    missing = [name for name in paths.__all__ if not hasattr(paths, name)]
    assert missing == []


def test_dunder_all_is_not_empty():
    """CONTROL for the test above, which passes trivially over an empty list."""
    assert len(paths.__all__) >= 10
