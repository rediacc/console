"""The paths whose change needs a `npm run vm:check` receipt, and the git arithmetic around them.

This module is the only definition of the trigger. `rediacc_ci.drills.vm_check` imports it, and so does the push guard (through a scoped sys.path insert), so the script and the guard cannot disagree about what counts as touched.

There are two SIDES, and a change is charged to the side it can break. `SIDE_RENET` is the deployed renet binary and the CLI remote paths that drive it. `SIDE_ACCOUNT` is private/account, the gateway and web app the account drills run against. `Changed.sides` names every side a change reaches, and a receipt must cover each of them.

A watched entry has three forms. A path ending in `/` is a directory prefix. A path ending in `_` is a filename prefix (`cmd/renet/sandbox_` matches `cmd/renet/sandbox_exec.go`). Anything else is an exact file. `EXCLUDE_SUFFIXES` and `EXCLUDE_CONTAINS` then remove test files, which change neither the deployed binary nor the served code.

Three sets of paths feed the sides. `CONSOLE_PATHS` maps a console-relative path to the sides it selects. `RENET_PATHS` is relative to private/renet and is every input of the deployed binary: cmd/, pkg/, go.mod, go.sum and embed-assets.lock.json. `ACCOUNT_PATHS` is relative to private/account and is the code the gateway serves.

Both submodules are diffed the same way. When a gitlink differs (push mode) or the submodule worktree has moved (worktree mode), the range is diffed inside the submodule. A range that cannot be computed is reported in `Changed.unknown` as `<submodule> <sha>: <why>`, adds that submodule's side, and counts as touched; it is never dropped.

The receipt key is the inputs digest, version 2: a `v2` line, the sorted console trigger blob lines, then both submodule pointers. The version line keeps a version 1 digest from ever matching a version 2 one.
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

SIDE_RENET = "renet"
SIDE_ACCOUNT = "account"
SIDES = (SIDE_RENET, SIDE_ACCOUNT)

# Console-relative path -> the sides a change to it selects.
CONSOLE_PATHS: dict[str, frozenset[str]] = {
    "packages/cli/src/remote/": frozenset({SIDE_RENET}),
    "packages/cli/src/services/repo/repo-key-deployment.ts": frozenset({SIDE_RENET}),
    ".ci/rediacc_ci/drills/license.py": frozenset({SIDE_ACCOUNT}),
    ".ci/rediacc_ci/drills/universe.py": frozenset({SIDE_ACCOUNT}),
    ".ci/rediacc_ci/drills/transfer.py": frozenset({SIDE_ACCOUNT}),
    ".ci/rediacc_ci/drills/vm_check.py": frozenset({SIDE_RENET, SIDE_ACCOUNT}),
    ".ci/rediacc_ci/drills/lib.py": frozenset({SIDE_RENET, SIDE_ACCOUNT}),
    ".ci/rediacc_ci/drills/upgrade_converge.py": frozenset({SIDE_RENET}),
    ".ci/rediacc_ci/drills/tenant_isolation.py": frozenset({SIDE_RENET}),
    ".ci/rediacc_ci/drills/session_teardown.py": frozenset({SIDE_RENET}),
    ".ci/rediacc_ci/drills/converge_preflight.py": frozenset({SIDE_RENET}),
    ".ci/rediacc_ci/drills/gpu_grants.py": frozenset({SIDE_RENET}),
    ".ci/rediacc_ci/drills/vm_ssh.py": frozenset({SIDE_RENET, SIDE_ACCOUNT}),
    ".ci/rediacc_ci/drills/wire.py": frozenset({SIDE_RENET, SIDE_ACCOUNT}),
}
# Relative to private/renet: every input of the binary `./rdc.sh` deploys.
RENET_PATHS = (
    "cmd/",
    "pkg/",
    "go.mod",
    "go.sum",
    "embed-assets.lock.json",
)
# Relative to private/account: the code the dev gateway and web app serve.
ACCOUNT_PATHS = (
    "src/",
    "web/",
    "drizzle/",
    "scripts/",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "wrangler.toml",
    "dev.defaults.env",
    "docker-compose.yml",
    "Dockerfile",
)
EXCLUDE_SUFFIXES = ("_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
EXCLUDE_CONTAINS = ("/__tests__/", "/testdata/", "/tests/", "/e2e/")
RENET_SUBMODULE = "private/renet"
ACCOUNT_SUBMODULE = "private/account"
SUBMODULE_SIDES = {RENET_SUBMODULE: SIDE_RENET, ACCOUNT_SUBMODULE: SIDE_ACCOUNT}
DIGEST_VERSION = "v2"

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


def console_sides(path: str) -> frozenset[str]:
    """The sides a console-relative `path` selects: empty when it is not a trigger path or is excluded."""
    if excluded(path):
        return frozenset()
    found: set[str] = set()
    for pattern, sides in CONSOLE_PATHS.items():
        if watched(path, (pattern,)):
            found |= sides
    return frozenset(found)


def console_hit(path: str) -> bool:
    return bool(console_sides(path))


def renet_hit(path: str) -> bool:
    """`path` is relative to private/renet."""
    return watched(path, RENET_PATHS) and not excluded(path)


def account_hit(path: str) -> bool:
    """`path` is relative to private/account."""
    return watched(path, ACCOUNT_PATHS) and not excluded(path)


_SUBMODULE_HIT = {RENET_SUBMODULE: renet_hit, ACCOUNT_SUBMODULE: account_hit}


@dataclasses.dataclass(frozen=True)
class Changed:
    """`hits` are console-relative paths (submodule files carry the `private/renet/` or `private/account/` prefix). `unknown` names each submodule range that could not be computed, as `<submodule> <sha>: <why>`; a caller counts it as touched. `sides` is every side the hits and unknown ranges reach."""

    hits: tuple[str, ...]
    unknown: tuple[str, ...] = ()
    sides: frozenset[str] = frozenset()

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


def _submodule_git(
    root: pathlib.Path, sub: str = RENET_SUBMODULE
) -> Callable[[Sequence[str]], str | None] | None:
    """A runner inside the checked-out submodule `sub`, or None."""
    # An empty directory is not a checkout: git would walk up to the console repository and answer for it.
    path = root / sub
    git = make_git(path)
    if not (path / ".git").exists() or git(["rev-parse", "--git-dir"]) is None:
        return None
    return git


def _lines(text: str | None) -> list[str]:
    """The entries of NUL-terminated git output (`-z`), which never quotes a name."""
    return [ln for ln in (text or "").split("\0") if ln]


def _gitlink(git: Callable[[Sequence[str]], str | None], rev: str, sub: str) -> str:
    """The `sub` gitlink at `rev`, or "" when `rev` has none."""
    return git(["rev-parse", "--verify", "--quiet", f"{rev}:{sub}"]) or ""


def _submodule_range(
    root: pathlib.Path, sub: str, old: str, new: str, mode: Mode
) -> tuple[list[str], str | None]:
    """(changed paths inside `sub`, why the range is unknown or None). `new` is ignored in worktree mode."""
    subgit = _submodule_git(root, sub)
    if subgit is None:
        return [], f"{sub} is not checked out"
    if not old:
        return [], f"the old side has no {sub} gitlink"
    if subgit(["cat-file", "-e", f"{old}^{{commit}}"]) is None:
        return [], f"the old gitlink commit is not in the local {sub}"
    if mode == "push":
        if not new:
            return [], f"the new side has no {sub} gitlink"
        if subgit(["cat-file", "-e", f"{new}^{{commit}}"]) is None:
            return [], f"the new gitlink commit is not in the local {sub}"
        names = subgit(["diff", "--no-renames", "--name-only", "-z", old, new])
        if names is None:
            return [], f"git diff of the {sub} range failed"
        return _lines(names), None
    names = subgit(["diff", "--no-renames", "--name-only", "-z", old])
    if names is None:
        return [], f"git diff of the {sub} worktree failed"
    found = _lines(names)
    found += _lines(subgit(["ls-files", "-z", "--others", "--exclude-standard"]))
    return found, None


def _submodule_worktree_moved(
    root: pathlib.Path, sub: str, old: str, changed: Sequence[str]
) -> bool:
    """True when the `sub` HEAD differs from `old`, or its worktree has edits or untracked files."""
    if sub in changed:
        return True
    subgit = _submodule_git(root, sub)
    head = subgit(["rev-parse", "HEAD"]) if subgit else None
    if subgit is None or head is None:
        return False
    return head != old or bool(subgit(["status", "--porcelain"]))


def changed_paths(root: pathlib.Path, base: str, mode: Mode, tip: str = "HEAD") -> Changed:
    """The trigger paths changed between `base` and `tip` (mode `push`) or between `base` and the worktree plus untracked files (mode `worktree`, the rule ci:quick uses).

    When a submodule gitlink differs, the range is diffed inside that submodule. A range that cannot be computed (the old commit is missing locally, the old side has no gitlink) is reported in `unknown` and never silently dropped; it adds the submodule's side.
    """
    git = make_git(root)
    if mode == "push":
        names = git(["diff", "--no-renames", "--name-only", "-z", base, tip])
    else:
        names = git(["diff", "--no-renames", "--name-only", "-z", base])
    if names is None:
        return Changed(hits=(), unknown=(f"{base}: git diff failed",), sides=frozenset(SIDES))
    changed = _lines(names)
    if mode == "worktree":
        changed += _lines(git(["ls-files", "-z", "--others", "--exclude-standard"]))
    hits = sorted({p for p in changed if console_hit(p)})
    sides: set[str] = set()
    for p in hits:
        sides |= console_sides(p)
    unknown: list[str] = []
    for sub, side in SUBMODULE_SIDES.items():
        old = _gitlink(git, base, sub)
        new = _gitlink(git, tip, sub) if mode == "push" else ""
        moved = old != new if mode == "push" else _submodule_worktree_moved(root, sub, old, changed)
        if not moved:
            continue
        paths, why = _submodule_range(root, sub, old, new, mode)
        if why is not None:
            unknown.append(f"{sub} {old or new or 'none'}: {why}")
            sides.add(side)
        found = sorted({f"{sub}/{p}" for p in paths if _SUBMODULE_HIT[sub](p)})
        if found:
            sides.add(side)
        hits += found
    return Changed(hits=tuple(hits), unknown=tuple(unknown), sides=frozenset(sides))


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


def _digest(lines: Iterable[str], renet: str, account: str) -> str:
    """Version 2: a `v2` line, the sorted console blob lines, then both submodule pointers."""
    body = (
        f"{DIGEST_VERSION}\n"
        + "".join(f"{ln}\n" for ln in sorted(lines))
        + f"{RENET_SUBMODULE} {renet or 'none'}\n"
        + f"{ACCOUNT_SUBMODULE} {account or 'none'}\n"
    )
    return hashlib.sha256(body.encode()).hexdigest()


def _tree_entry_path(line: str) -> str:
    return line.split("\t", 1)[1] if "\t" in line else ""


def inputs_of_tree(root: pathlib.Path, tree: str) -> str | None:
    """sha256 (version 2) over the sorted `git ls-tree -r <tree>` lines of the console trigger paths (exclusions applied) plus the tree's `private/renet` and `private/account` gitlinks. None when git cannot read the tree."""
    git = make_git(root)
    out = git(["ls-tree", "-r", "-z", tree, "--", *CONSOLE_PATHS])
    if out is None:
        return None
    lines = [ln for ln in _lines(out) if not excluded(_tree_entry_path(ln))]
    renet = _gitlink(git, tree, RENET_SUBMODULE)
    account = _gitlink(git, tree, ACCOUNT_SUBMODULE)
    return _digest(lines, renet, account)


def _worktree_entry(root: pathlib.Path, rel: str) -> str | None:
    """`<mode> blob <sha>\t<rel>` for the file at `root/rel`, hashed by the repository at `root`."""
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


def _submodule_head(root: pathlib.Path, sub: str) -> str:
    subgit = _submodule_git(root, sub)
    return (subgit(["rev-parse", "HEAD"]) if subgit else None) or ""


def inputs_of_worktree(root: pathlib.Path) -> str | None:
    """The same digest computed from worktree blobs (`git hash-object` per file) and each submodule's HEAD, so what ran and what is pushed compare on equal terms."""
    git = make_git(root)
    tracked = git(
        ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *CONSOLE_PATHS]
    )
    if tracked is None:
        return None
    lines: list[str] = []
    for rel in sorted(set(_lines(tracked))):
        if excluded(rel):
            continue
        entry = _worktree_entry(root, rel)
        if entry is not None:
            lines.append(entry)
    return _digest(
        lines, _submodule_head(root, RENET_SUBMODULE), _submodule_head(root, ACCOUNT_SUBMODULE)
    )


def inputs(root: pathlib.Path, tree: str | None = None) -> str | None:
    """The receipt key: the digest of `tree`, or of the worktree when `tree` is None."""
    return inputs_of_worktree(root) if tree is None else inputs_of_tree(root, tree)


# ----------------------------------------------------------------------------- account worktree


def account_modified(root: pathlib.Path) -> bool | None:
    """True when private/account has a non-excluded modified, staged or untracked trigger path; False when clean; None when the submodule is not checked out or git cannot answer."""
    subgit = _submodule_git(root, ACCOUNT_SUBMODULE)
    if subgit is None:
        return None
    out = subgit(
        [
            "status",
            "--porcelain",
            "-z",
            "--no-renames",
            "--untracked-files=all",
            "--",
            *ACCOUNT_PATHS,
        ]
    )
    if out is None:
        return None
    return any(account_hit(entry[3:]) for entry in _lines(out))


def account_worktree_digest(root: pathlib.Path) -> str | None:
    """The gateway freshness key: sha256 over `git ls-files -s` of the account trigger paths plus a blob hash of every modified or untracked trigger file (a deleted one is named as deleted). None when the submodule is not checked out or git cannot answer."""
    subgit = _submodule_git(root, ACCOUNT_SUBMODULE)
    if subgit is None:
        return None
    staged = subgit(["ls-files", "-s", "-z", "--", *ACCOUNT_PATHS])
    dirty = subgit(
        ["ls-files", "-z", "--modified", "--others", "--exclude-standard", "--", *ACCOUNT_PATHS]
    )
    if staged is None or dirty is None:
        return None
    sub_root = root / ACCOUNT_SUBMODULE
    lines = [ln for ln in _lines(staged) if not excluded(_tree_entry_path(ln))]
    for rel in sorted(set(_lines(dirty))):
        if excluded(rel):
            continue
        entry = _worktree_entry(sub_root, rel)
        lines.append(entry if entry is not None else f"deleted\t{rel}")
    body = "".join(f"{ln}\n" for ln in sorted(lines))
    return hashlib.sha256(body.encode()).hexdigest()
