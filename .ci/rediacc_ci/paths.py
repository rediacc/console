"""Where the repository is, and how a module reaches its neighbours.

WHY THIS IS THE FIRST MODULE IN THE PACKAGE. Every Python program in this tree
begins by answering the same two questions -- "where is the repo root" and "how
do I import the module next door" -- and today they are answered 33 times, in
five different spellings, none of which agree about what happens when they are
wrong. Measured 2026-09-06 across `.ci`, `.claude` and `scripts`:

  Path(__file__).resolve().parents[3]                     10 gates
  os.path.abspath(os.path.join(dirname(__file__), "..", "..", ".."))
                                                           4 gates and wl_classsweep
  Path(os.environ.get("<GATE>_ROOT") or parents[3])        8 gates, 8 DIFFERENT
                                                           environment variable names
  wl_core.hook_repo_root()                                 the Stop hook program
  33 x sys.path.insert(0, ...)                             every cross-directory import

Four of those spellings are not merely inconsistent, they are differently WRONG:

  * `parents[3]` is a DEPTH, and depth is invisible at the call site. Move the
    file one directory and the constant still resolves -- to the wrong tree,
    silently, and every subsequent read finds nothing rather than erroring.
  * The `os.path.join` form does not resolve symlinks, so the same repo reached
    through a symlinked worktree yields a path that compares unequal to the
    pathlib form. Two gates in one run then disagree about what "inside the
    repo" means.
  * Eight per-gate `*_ROOT` environment variables mean a harness that wants to
    point ALL gates at a fixture has to know all eight names, and learns about
    the ninth when a new gate ignores it.
  * `wl_resprofile.repo_root()` returns `Path | None` and `wl_core.hook_repo_root()`
    returns `Path | None`, while every `ROOT = ...` constant returns a Path that
    is never None but may be nonsense. Callers cannot be written once for both.

Phase 4 sweeps those call sites onto this module. This phase provides it and
proves it.

WHAT IT RESOLVES, AND IN WHAT ORDER. `repo_root()` has two rungs and no cwd:

  1. $REDIACC_CI_ROOT, when set. ONE name for the whole program, replacing the
     eight. An unusable value RAISES rather than falling through -- a harness
     that set the variable meant it, and silently ignoring it would run the gate
     against the real tree while the operator read a fixture's verdict.
  2. The package's own location. This file is <root>/.ci/rediacc_ci/paths.py, so
     the root is two directories up, resolved.

cwd IS NEVER A RUNG, and that is the one thing in here worth arguing for. This
tree contains repositories INSIDE the repository: `private/renet` is a submodule
and `private/growth` is a gitignored sibling checkout. Resolving upward from cwd
walks into one of them, and the Stop hook has the receipt -- a session on branch
0804-1 was told to bootstrap `agent/main/` because private/growth happened to be
on main, confirmed twice (see wl_core.project_start). `find_repo_root()` below
exists for callers that genuinely have only a path to start from, and its
docstring repeats the warning at the point of use.

NO `.git` MARKER CHECK IN `repo_root()`, deliberately. It would be the obvious
validation and it would break the anti-vacuity harness:
`.ci/scripts/test/gates/test-gate-anti-vacuity.sh` builds a fixture tree by
copying `scripts`, `.ci/scripts`, `.ci/config` and `.ci/rediacc_ci` into a
tempdir with no `.git` in it, then runs gates there and requires
`import rediacc_ci` to work. A marker check would make every gate importing this
module refuse inside the fixture, and the red would name neither the gate nor
the reason. `looks_like_repo_root()` is offered separately for callers that want
to ASK; the resolver does not decide for them.
"""

import os
import pathlib
import sys
from collections.abc import Iterable, Iterator

# The single environment override for the whole package. Named once, here, so a
# harness pointing the program at a fixture sets one variable rather than
# discovering a ninth per-gate name the day a gate ignores it.
ROOT_ENV = "REDIACC_CI_ROOT"

# <root>/.ci/rediacc_ci/paths.py -> the package, .ci, the root. Written as three
# named steps rather than `parents[2]` because the number is the part that goes
# wrong when a file moves, and a name cannot be off by one silently.
PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
CI_DIR = PACKAGE_DIR.parent
_STATIC_ROOT = CI_DIR.parent

# The well-known directories below are FUNCTIONS, not constants computed at
# import time. A constant would be captured before $REDIACC_CI_ROOT could be
# read, so a harness pointing the program at a fixture would get the fixture's
# root and the real tree's subdirectories -- the exact half-applied override the
# eight per-gate `*_ROOT` variables already produce today.


class RootError(RuntimeError):
    """$REDIACC_CI_ROOT names something that is not a directory.

    A distinct type rather than a bare RuntimeError so a harness can tell "you
    pointed me at a path that is not there" from any other failure, and so the
    gate's own controls can assert on it without matching a message string.
    """


def repo_root() -> pathlib.Path:
    """The repository root. Always a Path, never None, never cwd-derived.

    Raises RootError when $REDIACC_CI_ROOT is set to something unusable. That is
    the whole reason this returns a Path instead of `Path | None`: the two
    outcomes a caller must distinguish are "here it is" and "your override is
    wrong", and `None` collapses both into a value that reads as a missing repo.
    """
    override = os.environ.get(ROOT_ENV)
    if override:
        candidate = pathlib.Path(override).expanduser().resolve()
        if not candidate.is_dir():
            raise RootError(
                "%s=%s is not a directory. Unset it or point it at a repository; "
                "ignoring it would judge the real tree while you read a fixture's verdict."
                % (ROOT_ENV, override)
            )
        return candidate
    return _STATIC_ROOT


def ci_dir(root: pathlib.Path | None = None) -> pathlib.Path:
    """`<root>/.ci` -- the directory that must be on sys.path to import this package."""
    return (root or repo_root()) / ".ci"


def hooks_stop_dir(root: pathlib.Path | None = None) -> pathlib.Path:
    """`<root>/.claude/hooks/stop`.

    Named here because it is the single most common target of the 33 sys.path
    hops: five test files, `ci-trace.py`, `check_plan_boxes.py`,
    `check_resprofile.py`, `check_agent_hint_liveness.py` and
    `check_gate_reachability_coverage.py` all reach into it. Phase 5 moves that
    program to `.claude/rediacc_hooks`; this function is where the one-line
    change lands when it does, instead of in nine call sites.
    """
    return (root or repo_root()) / ".claude" / "hooks" / "stop"


def quality_dir(root: pathlib.Path | None = None) -> pathlib.Path:
    """`<root>/.ci/scripts/quality` -- where the `check_*.py` gates live."""
    return ci_dir(root) / "scripts" / "quality"


def from_root(*parts: str, root: pathlib.Path | None = None) -> pathlib.Path:
    """`<root>/a/b/c`. The reason a gate never needs to write `ROOT / ...` itself."""
    return (root or repo_root()).joinpath(*parts)


def relative_to_root(path: os.PathLike[str] | str, root: pathlib.Path | None = None) -> str:
    """A repo-relative string for MESSAGES, falling back to the absolute path.

    Gates print paths at humans, and an absolute path in a finding is noise that
    differs per machine. The fallback matters as much as the happy path: a file
    genuinely outside the repo -- a tempdir fixture, a submodule reached by
    symlink -- must still be printable rather than raising ValueError in the
    middle of a failure report, which is where a crash is least welcome.
    """
    base = root or repo_root()
    resolved = pathlib.Path(path).resolve()
    try:
        return str(resolved.relative_to(base))
    except ValueError:
        return str(resolved)


def looks_like_repo_root(path: os.PathLike[str] | str) -> bool:
    """Does `path` carry this repository's markers?

    Offered SEPARATELY from `repo_root()` on purpose -- see this module's
    docstring for why the resolver must not apply it. A caller that genuinely
    needs to know (a harness validating an override, a walker deciding where to
    stop) asks; a gate that just needs its root does not pay for a check that
    the anti-vacuity fixture cannot satisfy.

    `.git` is checked with `exists()`, not `is_dir()`: in a git WORKTREE -- which
    is how every session in this repo works -- `.git` is a FILE containing a
    gitdir pointer, and an `is_dir()` test says "not a repository" in the one
    place it is asked most.
    """
    p = pathlib.Path(path)
    return (p / ".git").exists() and (p / ".ci").is_dir() and (p / "package.json").is_file()


def find_repo_root(start: os.PathLike[str] | str) -> pathlib.Path | None:
    """Walk UP from `start` to the nearest directory with this repo's markers.

    RETURNS THE NEAREST, WHICH MAY NOT BE THE ONE YOU WANT. This tree contains
    repositories inside the repository (`private/renet` is a submodule,
    `private/growth` a gitignored sibling checkout), so a `start` under one of
    them answers with that inner repo -- correctly, and not usefully. Prefer
    `repo_root()`, which is derived from this file's own location and is immune
    to where the caller happens to be standing. Use this only when a path is
    genuinely all you have.

    `None` rather than a guess when nothing matches, because a guess here
    produces a root that reads as valid and finds nothing in it.
    """
    here = pathlib.Path(start).resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if looks_like_repo_root(candidate):
            return candidate
    return None


def on_sys_path(directory: os.PathLike[str] | str) -> str:
    """Put `directory` at the FRONT of sys.path, once. Returns the string used.

    THE REPLACEMENT FOR 33 HAND-WRITTEN HOPS, and it differs from them in one
    way that matters: it is idempotent. `sys.path.insert(0, d)` run twice -- a
    module imported once as `__main__` and once by name, which is what happens
    when a gate imports another gate -- leaves two copies of the directory on the
    path. Harmless until a later hop tries to shadow it and finds an older copy
    still ahead.

    FRONT, not append, because that is what every existing call site does and the
    intent is real: these directories hold modules whose names (`paths`,
    `output`, `worklist`) can collide with site-packages, and first-party must
    win. Deliberately not sorted or de-duplicated beyond this entry: reordering
    someone else's sys.path is not this function's business.
    """
    text = str(pathlib.Path(directory).resolve())
    if text in sys.path:
        return text
    sys.path.insert(0, text)
    return text


# Directory names no corpus walk in this package may descend into, at any depth.
#
# `.git` and `node_modules` are here because every gate in this package scans
# TRACKED SOURCE, and both are invisible to `git ls-files`. A gate that reads
# them is judging content CI will never see.
#
# `.worktrees` is the same argument for a directory that holds whole CHECKOUTS:
# `scripts/dev/worktree.sh` puts them at `$ROOT_DIR/.worktrees` and `.gitignore:146`
# excludes them.
PRUNED_DIR_NAMES = (".git", "node_modules", ".worktrees")

# Pruned as a (parent, name) PAIR rather than by name alone. `worktrees` is far
# too common a word to prune wherever it appears -- doing so would silently drop
# a real `docs/worktrees/` or `scripts/worktrees/` from a gate's corpus, which is
# the same class of invisible-corpus-loss this module exists to prevent. Only
# `.claude/worktrees` is a checkout holder.
PRUNED_DIR_PAIRS = ((".claude", "worktrees"),)


def walk_tree(
    root: os.PathLike[str] | str,
    *,
    exclude_dirs: Iterable[str] = (),
    follow_symlinks: bool = False,
) -> Iterator[tuple[str, list[str], list[str]]]:
    """`os.walk` with this repository's non-source directories pruned.

    A DROP-IN REPLACEMENT, yielding the same `(dirpath, dirnames, filenames)`
    triple, so a call site swaps `os.walk(x)` for `paths.walk_tree(x)` and keeps
    every downstream behaviour it already had. That is deliberate: the callers are
    PORTS whose finding text, path spelling and sort order are compared against a
    bash twin, and a helper that returned a tidy `list[Path]` would have forced
    seventeen behaviour changes to fix one bug.

    THE BUG THIS EXISTS FOR, because it is not the obvious one. `.claude/worktrees/`
    holds sibling CHECKOUTS OF THIS SAME REPOSITORY, created for isolated sub-agent
    sessions. It is excluded via `.git/info/exclude`, so `git ls-files` and every CI
    checkout are blind to it -- but a raw `os.walk` over the filesystem is not. On
    2026-09-13 a colleague's stale worktree carrying a copy of
    `.ci/scripts/private/license-mint` turned three gates red
    (`test_quality_go_module_sync`, `test_security_shfmt`,
    `test_gate_vacuity_floors::test_shfmt_accepts_the_real_corpus`): the SAME real
    file, scanned twice, failing only in the copy, whose relative
    `../../../../private/renet` could not resolve from the nested location. Every
    local verdict was silently conditional on whether a peer happened to have a
    worktree open, which does not teach people to fix gates, it teaches them to
    ignore local reds.

    PRUNED IN PLACE, NOT FILTERED AFTERWARDS. `dirnames[:] = ...` is the documented
    `os.walk` idiom and it means the subtree is never ENTERED. Filtering results
    after the fact would still pay to stat a peer checkout of the whole monorepo,
    and would still be wrong for any caller that inspects `dirnames` itself.

    THE LIST OBJECT IS MUTATED, NOT REPLACED, so a caller that then does
    `dirnames.sort()` on the yielded list still steers the walk exactly as it did
    under `os.walk`. Several call sites rely on that for deterministic output.

    A ROOT THAT IS ITSELF INSIDE A PRUNED DIRECTORY STILL WALKS, and this is load
    bearing rather than an accident of the implementation. Pruning applies only to
    DESCENDANTS of `root`, so a session whose own repo root is
    `<main>/.claude/worktrees/agent-xxxx` -- which is how every isolated sub-agent
    runs -- scans its own tree normally. A prune written as "is this path under a
    worktrees directory" would instead make every gate in such a session scan
    nothing and exit 0, replacing a false red with a false green.

    `follow_symlinks` DEFAULTS TO FALSE, matching `grep -r` (as opposed to `-R`)
    and `find -P`, which is what the twins these callers replace actually do. It is
    named and passed explicitly rather than left to `os.walk`'s default, because a
    default that happens to agree is one refactor away from not agreeing.

    NO ANTI-VACUITY FLOOR HERE, ON PURPOSE. A missing or empty `root` yields
    nothing, because several callers treat that as an empty corpus to match a
    twin's `2>/dev/null`, and because the meaningful floor is per gate: only the
    caller knows how many files its corpus must contain before a green means
    something. Enforcing a count here would either break those callers or install
    a floor too low to catch anything.
    """
    extra = frozenset(exclude_dirs)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        # `normpath` BEFORE `basename`, because `os.path.basename(".claude/")` is
        # the EMPTY STRING. A caller that passes a root with a trailing separator
        # would otherwise fail to match the `.claude`/`worktrees` pair at the top
        # level, which is precisely the level `shfmt`-shaped callers walk from,
        # and the prune would silently not happen for the one directory it was
        # written for.
        parent = os.path.basename(os.path.normpath(dirpath))
        dirnames[:] = [
            name
            for name in dirnames
            if name not in PRUNED_DIR_NAMES
            and name not in extra
            and (parent, name) not in PRUNED_DIR_PAIRS
        ]
        yield dirpath, dirnames, filenames


def ensure_importable(root: pathlib.Path | None = None) -> str:
    """Make `import rediacc_ci` work from a plain script. Returns the `.ci` path.

    The bootstrap problem, stated plainly: a script that wants this package has
    to put `.ci` on sys.path BEFORE it can import the module that would do it for
    it. So a caller outside the package still writes the hop by hand once, and
    everything after that -- including every other directory it needs -- comes
    from here. The pytest suite does not need this at all; `pythonpath = [".ci"]`
    in the root pyproject.toml is the same answer expressed in the ini file.
    """
    return on_sys_path(ci_dir(root))


__all__ = [
    "CI_DIR",
    "PACKAGE_DIR",
    "PRUNED_DIR_NAMES",
    "PRUNED_DIR_PAIRS",
    "ROOT_ENV",
    "RootError",
    "ci_dir",
    "ensure_importable",
    "find_repo_root",
    "from_root",
    "hooks_stop_dir",
    "looks_like_repo_root",
    "on_sys_path",
    "quality_dir",
    "relative_to_root",
    "repo_root",
    "walk_tree",
]
