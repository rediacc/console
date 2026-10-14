"""The paths whose change needs a `npm run vm:check` receipt, and the git arithmetic around them.

This module is the only definition of the trigger. `rediacc_ci.drills.vm_check` imports it, and so does the push guard (through a scoped sys.path insert), so the script and the guard cannot disagree about what counts as touched.

A watched entry has three forms. A path ending in `/` is a directory prefix. A path ending in `_` is a filename prefix (`cmd/renet/sandbox_` matches `cmd/renet/sandbox_exec.go`). Anything else is an exact file. `EXCLUDE` then removes test files, which change neither the deployed renet nor the CLI bundle.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import subprocess
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Iterable, Sequence

CONSOLE_PATHS = (
    "packages/cli/src/remote/",
    "packages/cli/src/services/repo/repo-key-deployment.ts",
    ".ci/rediacc_ci/drills/vm_check.py",
)
# Relative to private/renet.
RENET_PATHS = (
    "cmd/renet/sandbox_",
    "pkg/sandbox/",
    "pkg/orchestration/",
    "pkg/reporuntime/",
)
EXCLUDE_SUFFIXES = ("_test.go",)
EXCLUDE_CONTAINS = ("/__tests__/",)
RENET_SUBMODULE = "private/renet"

Mode = Literal["push", "worktree"]


def watched(path: str, patterns: Iterable[str]) -> bool:
    """True when `path` matches an entry: directory prefix (`/`), filename prefix (`_`) or exact file."""
    for pattern in patterns:
        if pattern.endswith(("/", "_")):
            if path.startswith(pattern):
                return True
        elif path == pattern:
            return True
    return False


def excluded(path: str) -> bool:
    return path.endswith(EXCLUDE_SUFFIXES) or any(frag in f"/{path}" for frag in EXCLUDE_CONTAINS)


def console_hit(path: str) -> bool:
    return watched(path, CONSOLE_PATHS) and not excluded(path)


def renet_hit(path: str) -> bool:
    """`path` is relative to private/renet."""
    return watched(path, RENET_PATHS) and not excluded(path)


@dataclasses.dataclass(frozen=True)
class Changed:
    """`hits` are console-relative paths (renet files carry the `private/renet/` prefix). `unknown` names each renet range that could not be computed, as `<sha>: <why>`; a caller counts it as touched."""

    hits: tuple[str, ...]
    unknown: tuple[str, ...] = ()

    @property
    def touched(self) -> bool:
        return bool(self.hits or self.unknown)


def make_git(cwd: pathlib.Path) -> Callable[[Sequence[str]], str | None]:
    """A runner answering stdout (trailing newline stripped), or None on any failure."""

    def run(args: Sequence[str]) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "-C", str(cwd), "-c", "core.quotePath=false", *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.rstrip("\n")

    return run


def _submodule_git(root: pathlib.Path) -> Callable[[Sequence[str]], str | None] | None:
    """A runner inside the checked-out `private/renet`, or None. An empty directory is not a checkout: git would walk up to the console repository and answer for it."""
    sub = root / RENET_SUBMODULE
    git = make_git(sub)
    if not (sub / ".git").exists() or git(["rev-parse", "--git-dir"]) is None:
        return None
    return git


def _lines(text: str | None) -> list[str]:
    return [ln for ln in (text or "").split("\n") if ln]


def _gitlink(git: Callable[[Sequence[str]], str | None], rev: str) -> str:
    """The `private/renet` gitlink at `rev`, or "" when `rev` has none."""
    return git(["rev-parse", "--verify", "--quiet", f"{rev}:{RENET_SUBMODULE}"]) or ""


def _renet_range(
    root: pathlib.Path, old: str, new: str, mode: Mode
) -> tuple[list[str], str | None]:
    """(changed renet paths, why the range is unknown or None). `new` is ignored in worktree mode."""
    subgit = _submodule_git(root)
    if subgit is None:
        return [], "private/renet is not checked out"
    if not old:
        return [], "the old side has no private/renet gitlink"
    if subgit(["cat-file", "-e", f"{old}^{{commit}}"]) is None:
        return [], "the old gitlink commit is not in the local private/renet"
    if mode == "push":
        if not new:
            return [], "the new side has no private/renet gitlink"
        if subgit(["cat-file", "-e", f"{new}^{{commit}}"]) is None:
            return [], "the new gitlink commit is not in the local private/renet"
        names = subgit(["diff", "--no-renames", "--name-only", old, new])
        if names is None:
            return [], "git diff of the renet range failed"
        return _lines(names), None
    names = subgit(["diff", "--no-renames", "--name-only", old])
    if names is None:
        return [], "git diff of the renet worktree failed"
    found = _lines(names)
    found += _lines(subgit(["ls-files", "--others", "--exclude-standard"]))
    return found, None


def _renet_worktree_moved(root: pathlib.Path, old: str, changed: Sequence[str]) -> bool:
    """True when the submodule HEAD differs from `old`, or its worktree has edits or untracked files."""
    if RENET_SUBMODULE in changed:
        return True
    subgit = _submodule_git(root)
    head = subgit(["rev-parse", "HEAD"]) if subgit else None
    if subgit is None or head is None:
        return False
    return head != old or bool(subgit(["status", "--porcelain"]))


def changed_paths(root: pathlib.Path, base: str, mode: Mode, tip: str = "HEAD") -> Changed:
    """The trigger paths changed between `base` and `tip` (mode `push`) or between `base` and the worktree plus untracked files (mode `worktree`, the rule ci:quick uses).

    When the `private/renet` gitlink differs, the renet range is diffed inside the submodule. A range that cannot be computed (the old commit is missing locally) is reported in `unknown` and never silently dropped.
    """
    git = make_git(root)
    if mode == "push":
        names = git(["diff", "--no-renames", "--name-only", base, tip])
    else:
        names = git(["diff", "--no-renames", "--name-only", base])
    if names is None:
        return Changed(hits=(), unknown=(f"{base}: git diff failed",))
    changed = _lines(names)
    if mode == "worktree":
        changed += _lines(git(["ls-files", "--others", "--exclude-standard"]))
    hits = sorted({p for p in changed if console_hit(p)})
    unknown: list[str] = []
    old = _gitlink(git, base)
    new = _gitlink(git, tip) if mode == "push" else ""
    moved = old != new if mode == "push" else _renet_worktree_moved(root, old, changed)
    if moved:
        paths, why = _renet_range(root, old, new, mode)
        if why is not None:
            unknown.append(f"{old or new or 'none'}: {why}")
        hits += sorted({f"{RENET_SUBMODULE}/{p}" for p in paths if renet_hit(p)})
    return Changed(hits=tuple(hits), unknown=tuple(unknown))


# ----------------------------------------------------------------------------- push base


@dataclasses.dataclass(frozen=True)
class BaseResolution:
    """Port of scripts/ci-runner/quick-select.ts `BaseResolution`."""

    ref: str | None = None
    via: str | None = None
    merge_base: str | None = None
    tried: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def _branch_of_ref(name: str) -> str:
    return name.split("/", 1)[1] if "/" in name else name


def push_base(git: Callable[[Sequence[str]], str | None], branch: str | None) -> BaseResolution:
    """Port of `resolvePushBase` (scripts/ci-runner/quick-select.ts:262-294).

    Tries `@{push}`, `origin/<branch>`, `@{upstream}`, then `origin/main`, and skips a tracking ref named for another branch (an already merged upstream once widened a diff to 244 files). The merge-base with HEAD is the base.
    """
    named = bool(branch)
    candidates: list[tuple[str, str]] = [("@{push}", "@{push}")]
    if named:
        candidates.append((f"origin/{branch}", "origin/<branch>"))
    candidates.append(("@{upstream}", "@{upstream}"))
    candidates.append(("origin/main", "origin/main (never pushed: everything since main)"))
    tried: list[str] = []
    warnings: list[str] = []
    foreign: set[str] = set()
    for ref in ("@{push}", "@{upstream}"):
        if git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]) is None:
            continue
        name = git(["rev-parse", "--abbrev-ref", ref]) or ref
        if named and _branch_of_ref(name) == branch:
            continue
        foreign.add(ref)
        if not any(f" is {name}," in w for w in warnings):
            shown = branch if named else "<branch>"
            warnings.append(f"{ref} is {name}, not origin/{shown}; ignored")
    for ref, via in candidates:
        tried.append(ref)
        if ref in foreign:
            continue
        if git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"]) is None:
            continue
        name = (git(["rev-parse", "--abbrev-ref", ref]) or ref) if ref.startswith("@") else ref
        merge_base = git(["merge-base", "HEAD", ref])
        if not merge_base:
            continue
        return BaseResolution(name, via, merge_base, tuple(tried), tuple(warnings))
    return BaseResolution(tried=tuple(tried), warnings=tuple(warnings))


# ----------------------------------------------------------------------------- inputs digest


def _digest(lines: Iterable[str], pointer: str) -> str:
    body = "\n".join(sorted(lines)) + f"\nprivate/renet {pointer or 'none'}\n"
    return hashlib.sha256(body.encode()).hexdigest()


def _tree_entry_path(line: str) -> str:
    return line.split("\t", 1)[1] if "\t" in line else ""


def inputs_of_tree(root: pathlib.Path, tree: str) -> str | None:
    """sha256 over the sorted `git ls-tree -r <tree>` lines of the console trigger paths (exclusions applied) plus the tree's `private/renet` gitlink. None when git cannot read the tree."""
    git = make_git(root)
    out = git(["ls-tree", "-r", tree, "--", *CONSOLE_PATHS])
    if out is None:
        return None
    lines = [ln for ln in _lines(out) if not excluded(_tree_entry_path(ln))]
    pointer = git(["rev-parse", "--verify", "--quiet", f"{tree}:{RENET_SUBMODULE}"]) or ""
    return _digest(lines, pointer)


def _worktree_entry(root: pathlib.Path, rel: str) -> str | None:
    full = root / rel
    if full.is_symlink():
        data = os.readlink(full).encode()
        mode = "120000"
    elif full.is_file():
        data = full.read_bytes()
        mode = "100755" if os.access(full, os.X_OK) else "100644"
    else:
        return None
    blob = subprocess.run(
        ["git", "-C", str(root), "hash-object", "--stdin"],
        input=data,
        capture_output=True,
        check=False,
    )
    if blob.returncode != 0:
        return None
    return f"{mode} blob {blob.stdout.decode().strip()}\t{rel}"


def inputs_of_worktree(root: pathlib.Path) -> str | None:
    """The same digest computed from worktree blobs (`git hash-object` per file) and the submodule HEAD, so what ran and what is pushed compare on equal terms."""
    git = make_git(root)
    tracked = git(["ls-files", "--cached", "--others", "--exclude-standard", "--", *CONSOLE_PATHS])
    if tracked is None:
        return None
    lines: list[str] = []
    for rel in sorted(set(_lines(tracked))):
        if excluded(rel):
            continue
        entry = _worktree_entry(root, rel)
        if entry is not None:
            lines.append(entry)
    subgit = _submodule_git(root)
    pointer = (subgit(["rev-parse", "HEAD"]) if subgit else None) or ""
    return _digest(lines, pointer)


def inputs(root: pathlib.Path, tree: str | None = None) -> str | None:
    """The receipt key: the digest of `tree`, or of the worktree when `tree` is None."""
    return inputs_of_worktree(root) if tree is None else inputs_of_tree(root, tree)
