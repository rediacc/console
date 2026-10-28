"""The deployable surfaces, the paths whose change needs a proof, and the git arithmetic around them.

ONE MAP. `.ci/config/proof-tiers.json` is the only surface map (agent/plans/PLAN-tested-on-bench.md Design item 2), loaded once at import into `MAP`. It replaced the constant tables the vm:check trigger used to carry in code. The push guard `block_vm_unverified_push`, `release:local`'s vm-check gate and `vm:check` itself import it, so they cannot disagree about what a path touches. A map that is empty, unparsable or names an unknown surface raises `MapError` at import: a blind map is never a quiet one.

GLOBS. Every surface glob and exclude is a console-relative glob in the Owns grammar: `wl_planconc.normalize_owns` expands braces, and `wl_planconc.glob_regex` matches one path. The same normaliser feeds `wl_planconc.owns_overlap`, which judges a plan's Owns against the same globs, so a path and a plan header are read by one grammar. A surface with a glob under `private/renet/` or `private/account/` lives in that submodule.

TWO TIERS. A surface may have a VM phase (`tiers.vm.phases`: `renet` covers the renet and cli-remote surfaces, `account` the account surface) and live targets (`surfaces.<name>.live`). `tiers.vm.instrument` lists drill files whose change needs a new VM run though they deploy nothing. `Changed.hits` and `Changed.sides` are the VM tier (the paths that need a vm:check run and the phases they select; `sides` keeps its name because the vm:check receipt records it); `Changed.surfaces` is every surface a change reaches, VM phase or not.

Both submodules are diffed the same way. When a gitlink differs (push mode) or the submodule worktree has moved (worktree mode), the range is diffed inside the submodule. A range that cannot be computed is reported in `Changed.unknown` as `<submodule> <sha>: <why>`, adds every phase and surface living in that submodule, and counts as touched; it is never dropped.

THE INPUTS DIGEST, version 3 (`inputs`): a `v3` line, the sorted `git ls-tree -r` blob lines of the console paths in the given surfaces and instrument globs (the whole tree listed, then filtered here with the map's own globs and excludes), then the gitlink pointer of each submodule a given surface lives in, sorted. With no surfaces given it is the VM tier's digest (every phase surface plus the instrument). A v2 digest never equals a v3 one, because the version line differs.

The renet build identity lives here too: `go_buildinfo` reads `go version -m`, and `renet_identity` captures the pointer, the checkout, the build's `vcs.revision` and `vcs.modified` and the binary's sha256, rebuilding once when the build is not the checkout (the P1 rule of vm_check). It judges nothing; `rediacc_ci.proof.receipt.identity_refusal` does.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import os
import subprocess
from typing import TYPE_CHECKING, Any, Literal

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib
    import re
    from collections.abc import Callable, Collection, Iterable, Sequence

# The Owns glob grammar lives only in the Stop hooks; it is reachable once their directory is on sys.path (the check_plan_deps.py shape). The directory is taken from this checkout's code (paths.CI_DIR), as MAP_PATH is, never from $REDIACC_CI_ROOT: a drill run against a scratch root has no .claude/hooks there and failed with ModuleNotFoundError: wl_planconc.
paths.on_sys_path(paths.hooks_stop_dir(paths.CI_DIR.parent))
wl_planconc = importlib.import_module("wl_planconc")

MAP_PATH = paths.CI_DIR / "config" / "proof-tiers.json"
MAP_SCHEMA = 1
RENET_SUBMODULE = "private/renet"
ACCOUNT_SUBMODULE = "private/account"
SUBMODULES = (RENET_SUBMODULE, ACCOUNT_SUBMODULE)
DIGEST_VERSION = "v3"
RENET_BIN = "bin/renet"

Mode = Literal["push", "worktree"]


class MapError(ValueError):
    """`proof-tiers.json` cannot be read as a surface map."""


@dataclasses.dataclass(frozen=True)
class Surface:
    name: str
    globs: tuple[str, ...]
    live: tuple[str, ...]
    renet_build: bool
    submodules: frozenset[str]


@dataclasses.dataclass(frozen=True)
class ProofMap:
    surfaces: dict[str, Surface]
    exclude: tuple[str, ...]
    phases: dict[str, frozenset[str]]
    instrument: dict[str, frozenset[str]]
    live: dict[str, Any]


def _normalised(globs: object, where: str) -> tuple[str, ...]:
    if not isinstance(globs, list) or not globs or not all(isinstance(g, str) for g in globs):
        raise MapError(f"{where} is not a non-empty list of globs")
    out, problems = wl_planconc.normalize_owns(globs)
    if problems:
        raise MapError(f"{where}: {'; '.join(problems)}")
    if not out:
        raise MapError(f"{where} normalises to no glob")
    return tuple(out)


def _sub_of(glob: str) -> str | None:
    return next((s for s in SUBMODULES if glob.startswith(f"{s}/")), None)


def _parse_surfaces(entries: object) -> dict[str, Surface]:
    if not isinstance(entries, dict) or not entries:
        raise MapError("surfaces is empty: the map is not seeing any deployable code")
    surfaces: dict[str, Surface] = {}
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            raise MapError(f"surfaces.{name} is not an object")
        globs = _normalised(entry.get("globs"), f"surfaces.{name}.globs")
        live = entry.get("live")
        if not isinstance(live, list) or not all(isinstance(t, str) for t in live):
            raise MapError(f"surfaces.{name}.live is not a list of targets")
        if not isinstance(entry.get("renet_build"), bool):
            raise MapError(f"surfaces.{name}.renet_build is not a boolean")
        subs = frozenset(s for s in (_sub_of(g) for g in globs) if s)
        surfaces[name] = Surface(name, globs, tuple(live), entry["renet_build"], subs)
    return surfaces


def _parse_vm(vm: dict[str, Any], surfaces: dict[str, Surface]) -> tuple[dict, dict]:
    phases: dict[str, frozenset[str]] = {}
    for phase, entry in (vm.get("phases") or {}).items():
        names = entry.get("surfaces") if isinstance(entry, dict) else None
        if not isinstance(names, list) or not names:
            raise MapError(f"tiers.vm.phases.{phase}.surfaces is empty")
        unknown = [n for n in names if n not in surfaces]
        if unknown:
            raise MapError(f"tiers.vm.phases.{phase} names unknown surfaces {unknown}")
        phases[phase] = frozenset(names)
    for needed in ("renet", "account"):
        if needed not in phases:
            raise MapError(f"tiers.vm.phases has no {needed} phase")
    instrument: dict[str, frozenset[str]] = {}
    for path, names in (vm.get("instrument") or {}).items():
        if not isinstance(names, list) or not names or any(n not in phases for n in names):
            raise MapError(f"tiers.vm.instrument.{path} names no known phase")
        instrument[path] = frozenset(names)
    return phases, instrument


def parse_map(raw: object) -> ProofMap:
    """The map, or MapError naming the first defect. Zero surfaces, an unknown surface in a phase, a phase-less instrument entry and a missing renet or account phase are all defects."""
    if not isinstance(raw, dict) or raw.get("schema") != MAP_SCHEMA:
        raise MapError(f"the map is not an object of schema {MAP_SCHEMA}")
    if raw.get("submodules") != list(SUBMODULES):
        raise MapError(f"submodules is not {list(SUBMODULES)}")
    surfaces = _parse_surfaces(raw.get("surfaces"))
    exclude = _normalised(raw.get("exclude"), "exclude")
    tiers = raw.get("tiers")
    if not isinstance(tiers, dict) or not isinstance(tiers.get("vm"), dict):
        raise MapError("tiers.vm is missing")
    phases, instrument = _parse_vm(tiers["vm"], surfaces)
    live = tiers.get("live")
    if not isinstance(live, dict):
        raise MapError("tiers.live is missing")
    return ProofMap(surfaces, exclude, phases, instrument, live)


def load(path: pathlib.Path = MAP_PATH) -> ProofMap:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MapError(f"{path} is unreadable: {exc}") from exc
    return parse_map(raw)


MAP = load()
SIDE_RENET = "renet"
SIDE_ACCOUNT = "account"
# The VM phases, in map order. vm_check and the receipt call them sides.
SIDES = tuple(MAP.phases)
SURFACES = tuple(MAP.surfaces)


def _regexes(globs: Iterable[str]) -> list[re.Pattern[str]]:
    return [wl_planconc.glob_regex(g) for g in globs]


_EXCLUDE = _regexes(MAP.exclude)
_SURFACE_RX = {name: _regexes(s.globs) for name, s in MAP.surfaces.items()}
_INSTRUMENT_RX = {path: wl_planconc.glob_regex(path) for path in MAP.instrument}
# The surfaces and phases (sides) that live in each submodule: what an unknown range of it adds.
SUBMODULE_SURFACES = {
    sub: frozenset(n for n, s in MAP.surfaces.items() if sub in s.submodules) for sub in SUBMODULES
}
SUBMODULE_SIDES = {
    sub: frozenset(p for p, names in MAP.phases.items() if names & SUBMODULE_SURFACES[sub])
    for sub in SUBMODULES
}


def matches(path: str, globs: Iterable[str]) -> bool:
    """True when a console-relative `path` matches one of the normalised `globs`."""
    return any(rx.match(path) for rx in _regexes(globs))


def excluded(path: str) -> bool:
    """True for a test file or a document, which changes neither a deployed binary nor served code. Works on console-relative and submodule-relative paths alike."""
    return any(rx.match(path) for rx in _EXCLUDE)


def surfaces_of(path: str) -> frozenset[str]:
    """Every surface a console-relative `path` hits; empty when it hits none or is excluded."""
    if excluded(path):
        return frozenset()
    return frozenset(n for n, rxs in _SURFACE_RX.items() if any(rx.match(path) for rx in rxs))


def phases_for(surfaces: Iterable[str]) -> frozenset[str]:
    """The VM phases that cover any of `surfaces`."""
    wanted = set(surfaces)
    return frozenset(p for p, names in MAP.phases.items() if names & wanted)


def console_sides(path: str) -> frozenset[str]:
    """The VM phases a console-relative `path` selects: through its surfaces, or as an instrument file. Empty when it needs no VM run."""
    if excluded(path):
        return frozenset()
    found = set(phases_for(surfaces_of(path)))
    for p, rx in _INSTRUMENT_RX.items():
        if rx.match(path):
            found |= MAP.instrument[p]
    return frozenset(found)


def console_hit(path: str) -> bool:
    return bool(console_sides(path))


def submodule_hit(sub: str, rel: str) -> bool:
    """`rel` is relative to the submodule `sub`; True when it hits a surface."""
    return bool(surfaces_of(f"{sub}/{rel}"))


def owns_surfaces(globs: Iterable[str]) -> dict[str, list[str]]:
    """`{surface: [Owns glob, ...]}` for every surface a plan's `Owns:` globs hit, in map order, each glob listed once. A glob hits a surface when `wl_planconc.owns_overlap` finds a shared path that the map's excludes do not drop, so `**/*.md` hits nothing. A bare submodule path (`private/renet`) names the gitlink alone and overlaps no surface glob, while `private/renet/` normalises to `private/renet/**` and claims the code. The pre-edit guard `block_plan_without_depends`, the recorder and `check:ci-plan-live-proof` share this one reading."""
    owns = list(globs)
    hits: dict[str, list[str]] = {}
    for name, surface in MAP.surfaces.items():
        for mine, _theirs, witness in wl_planconc.owns_overlap(owns, surface.globs):
            if excluded(witness):
                continue
            found = hits.setdefault(name, [])
            if mine not in found:
                found.append(mine)
    return hits


@dataclasses.dataclass(frozen=True)
class Changed:
    """`hits` are the console-relative paths that need a VM run (submodule files carry the `private/renet/` or `private/account/` prefix), and `sides` the VM phases they and the unknown ranges select. `unknown` names each submodule range that could not be computed, as `<submodule> <sha>: <why>`; a caller counts it as touched. `surfaces` is every surface the change reaches, with a VM phase or not."""

    hits: tuple[str, ...]
    unknown: tuple[str, ...] = ()
    sides: frozenset[str] = frozenset()
    surfaces: frozenset[str] = frozenset()

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


@dataclasses.dataclass
class _Tally:
    hits: list[str] = dataclasses.field(default_factory=list)
    sides: set[str] = dataclasses.field(default_factory=set)
    surfaces: set[str] = dataclasses.field(default_factory=set)

    def add(self, paths_: Iterable[str]) -> None:
        found_hits: set[str] = set()
        for p in paths_:
            self.surfaces |= surfaces_of(p)
            sides = console_sides(p)
            if sides:
                self.sides |= sides
                found_hits.add(p)
        self.hits += sorted(found_hits)


def changed_paths(root: pathlib.Path, base: str, mode: Mode, tip: str = "HEAD") -> Changed:
    """The surface paths changed between `base` and `tip` (mode `push`) or between `base` and the worktree plus untracked files (mode `worktree`, the rule ci:quick uses).

    When a submodule gitlink differs, the range is diffed inside that submodule. A range that cannot be computed (the old commit is missing locally, the old side has no gitlink) is reported in `unknown` and never silently dropped; it adds the submodule's phases and surfaces.
    """
    git = make_git(root)
    if mode == "push":
        names = git(["diff", "--no-renames", "--name-only", "-z", base, tip])
    else:
        names = git(["diff", "--no-renames", "--name-only", "-z", base])
    if names is None:
        return Changed(
            hits=(),
            unknown=(f"{base}: git diff failed",),
            sides=frozenset(SIDES),
            surfaces=frozenset(SURFACES),
        )
    changed = _lines(names)
    if mode == "worktree":
        changed += _lines(git(["ls-files", "-z", "--others", "--exclude-standard"]))
    tally = _Tally()
    tally.add(set(changed))
    unknown: list[str] = []
    for sub in SUBMODULES:
        old = _gitlink(git, base, sub)
        new = _gitlink(git, tip, sub) if mode == "push" else ""
        moved = old != new if mode == "push" else _submodule_worktree_moved(root, sub, old, changed)
        if not moved:
            continue
        rels, why = _submodule_range(root, sub, old, new, mode)
        if why is not None:
            unknown.append(f"{sub} {old or new or 'none'}: {why}")
            tally.sides |= SUBMODULE_SIDES[sub]
            tally.surfaces |= SUBMODULE_SURFACES[sub]
        tally.add({f"{sub}/{rel}" for rel in rels})
    return Changed(
        hits=tuple(tally.hits),
        unknown=tuple(unknown),
        sides=frozenset(tally.sides),
        surfaces=frozenset(tally.surfaces),
    )


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


@dataclasses.dataclass(frozen=True)
class Selection:
    """What one digest covers: the console globs (submodule globs dropped, a pointer covers them), the instrument paths, and the submodules whose pointers join."""

    globs: tuple[str, ...]
    instrument: tuple[str, ...]
    submodules: tuple[str, ...]

    def covers(self, path: str) -> bool:
        if excluded(path):
            return False
        return path in self.instrument or any(rx.match(path) for rx in _regexes(self.globs))


def selection(
    surfaces: Collection[str] | None = None, instrument: Iterable[str] | None = None
) -> Selection:
    """The VM tier (every phase surface plus the instrument) when `surfaces` is None; otherwise those surfaces and `instrument` (default none). KeyError on an unknown surface."""
    if surfaces is None:
        names: set[str] = set().union(*MAP.phases.values())
        inst = tuple(sorted(MAP.instrument if instrument is None else instrument))
    else:
        names = set(surfaces)
        inst = tuple(sorted(instrument or ()))
    globs: list[str] = []
    subs: set[str] = set()
    for name in sorted(names):
        surface = MAP.surfaces[name]
        subs |= surface.submodules
        globs += [g for g in surface.globs if _sub_of(g) is None]
    return Selection(tuple(globs), inst, tuple(s for s in SUBMODULES if s in subs))


def _digest(lines: Iterable[str], pointers: dict[str, str]) -> str:
    """Version 3: a `v3` line, the sorted console blob lines, then `<submodule> <pointer>` per selected submodule, sorted."""
    body = (
        f"{DIGEST_VERSION}\n"
        + "".join(f"{ln}\n" for ln in sorted(lines))
        + "".join(f"{sub} {pointers[sub] or 'none'}\n" for sub in sorted(pointers))
    )
    return hashlib.sha256(body.encode()).hexdigest()


def _tree_entry_path(line: str) -> str:
    return line.split("\t", 1)[1] if "\t" in line else ""


def inputs_of_tree(
    root: pathlib.Path,
    tree: str,
    surfaces: Collection[str] | None = None,
    instrument: Iterable[str] | None = None,
) -> str | None:
    """sha256 (version 3) over the `git ls-tree -r <tree>` blob lines the selection covers plus the tree's gitlinks of the selected submodules. None when git cannot read the tree."""
    sel = selection(surfaces, instrument)
    git = make_git(root)
    out = git(["ls-tree", "-r", "-z", "--full-tree", tree])
    if out is None:
        return None
    lines = [ln for ln in _lines(out) if " blob " in ln and sel.covers(_tree_entry_path(ln))]
    return _digest(lines, {sub: _gitlink(git, tree, sub) for sub in sel.submodules})


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


def inputs_of_worktree(
    root: pathlib.Path,
    surfaces: Collection[str] | None = None,
    instrument: Iterable[str] | None = None,
) -> str | None:
    """The same digest computed from worktree blobs (`git hash-object` per file) and each selected submodule's HEAD, so what ran and what is pushed compare on equal terms."""
    sel = selection(surfaces, instrument)
    git = make_git(root)
    tracked = git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    if tracked is None:
        return None
    lines: list[str] = []
    for rel in sorted(set(_lines(tracked))):
        if not sel.covers(rel):
            continue
        entry = _worktree_entry(root, rel)
        if entry is not None:
            lines.append(entry)
    return _digest(lines, {sub: _submodule_head(root, sub) for sub in sel.submodules})


def inputs(
    root: pathlib.Path,
    tree: str | None = None,
    surfaces: Collection[str] | None = None,
    instrument: Iterable[str] | None = None,
) -> str | None:
    """The receipt key: the digest of `tree`, or of the worktree when `tree` is None. `surfaces` None is the VM tier; the live tier passes the plan's touched surfaces."""
    if tree is None:
        return inputs_of_worktree(root, surfaces, instrument)
    return inputs_of_tree(root, tree, surfaces, instrument)


# ----------------------------------------------------------------------------- worktree state


def submodule_modified(root: pathlib.Path, sub: str) -> bool | None:
    """True when `sub` has a non-excluded modified, staged or untracked surface path; False when clean; None when the submodule is not checked out or git cannot answer."""
    subgit = _submodule_git(root, sub)
    if subgit is None:
        return None
    out = subgit(["status", "--porcelain", "-z", "--no-renames", "--untracked-files=all"])
    if out is None:
        return None
    return any(submodule_hit(sub, entry[3:]) for entry in _lines(out))


def account_modified(root: pathlib.Path) -> bool | None:
    return submodule_modified(root, ACCOUNT_SUBMODULE)


def submodule_state(root: pathlib.Path, sub: str, rev: str = "HEAD") -> dict[str, Any]:
    """`{pointer, checkout, modified}` of `sub`: the gitlink of `rev`, the submodule HEAD ("" when not checked out) and `submodule_modified`."""
    return {
        "pointer": _gitlink(make_git(root), rev, sub),
        "checkout": _submodule_head(root, sub),
        "modified": submodule_modified(root, sub),
    }


def console_dirty(root: pathlib.Path, surfaces: Collection[str]) -> bool | None:
    """True when the console worktree has a modified, staged or untracked path the console globs of `surfaces` cover (submodule internals are `submodule_modified`'s); None when git cannot answer."""
    sel = selection(surfaces)
    out = make_git(root)(["status", "--porcelain", "-z", "--no-renames", "--untracked-files=all"])
    if out is None:
        return None
    return any(sel.covers(entry[3:]) for entry in _lines(out))


def account_worktree_digest(root: pathlib.Path) -> str | None:
    """The gateway freshness key: sha256 over `git ls-files -s` of the account surface paths plus a blob hash of every modified or untracked surface file (a deleted one is named as deleted). None when the submodule is not checked out or git cannot answer."""
    subgit = _submodule_git(root, ACCOUNT_SUBMODULE)
    if subgit is None:
        return None
    staged = subgit(["ls-files", "-s", "-z"])
    dirty = subgit(["ls-files", "-z", "--modified", "--others", "--exclude-standard"])
    if staged is None or dirty is None:
        return None
    sub_root = root / ACCOUNT_SUBMODULE
    lines = [ln for ln in _lines(staged) if submodule_hit(ACCOUNT_SUBMODULE, _tree_entry_path(ln))]
    for rel in sorted(set(_lines(dirty))):
        if not submodule_hit(ACCOUNT_SUBMODULE, rel):
            continue
        entry = _worktree_entry(sub_root, rel)
        lines.append(entry if entry is not None else f"deleted\t{rel}")
    body = "".join(f"{ln}\n" for ln in sorted(lines))
    return hashlib.sha256(body.encode()).hexdigest()


# ----------------------------------------------------------------------------- renet build identity


def go_buildinfo(text: str) -> tuple[str, bool | None]:
    """(vcs.revision, vcs.modified) of `go version -m`; ("", None) for what it does not carry."""
    revision = ""
    modified: bool | None = None
    for line in text.splitlines():
        field = line.strip().split("\t")[-1].strip()
        if field.startswith("vcs.revision="):
            revision = field.split("=", 1)[1]
        elif field.startswith("vcs.modified="):
            modified = field.split("=", 1)[1] == "true"
    return revision, modified


def go_version_m(binary: pathlib.Path) -> str | None:
    """`go version -m <binary>` stdout, or None when go is missing or refuses the file."""
    try:
        proc = subprocess.run(
            ["go", "version", "-m", str(binary)], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def sha256_file(path: pathlib.Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def renet_identity(
    root: pathlib.Path,
    tree: str = "HEAD",
    *,
    read_build: Callable[[pathlib.Path], str | None] = go_version_m,
    rebuild: Callable[[], object] | None = None,
) -> dict[str, Any]:
    """`{pointer, checkout, built, modified, sha256, rebuilt}` of `private/renet/bin/renet`.

    `pointer` is the renet gitlink of `tree`, `checkout` the submodule HEAD, `built` and `modified` the binary's `vcs.revision` and `vcs.modified`, `sha256` the binary's bytes ("" when absent). When `rebuild` is given and the build is not the checkout or is modified (vm_check's P1 rule), it is called once (`./rdc.sh --version` in practice) and the build is read again. Nothing is judged here; `receipt.identity_refusal` judges.
    """
    pointer = _gitlink(make_git(root), tree, RENET_SUBMODULE)
    checkout = _submodule_head(root, RENET_SUBMODULE)
    binary = root / RENET_SUBMODULE / RENET_BIN

    def read() -> tuple[str, bool | None]:
        return go_buildinfo(read_build(binary) or "")

    built, modified = read()
    rebuilt = False
    if rebuild is not None and (not checkout or built != checkout or modified is not False):
        rebuild()
        built, modified = read()
        rebuilt = True
    return {
        "pointer": pointer,
        "checkout": checkout,
        "built": built,
        "modified": modified,
        "sha256": sha256_file(binary),
        "rebuilt": rebuilt,
    }
