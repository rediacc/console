"""The Python half of `check:ci-gate-tree-writes`: every place a gate module WRITES a path, with the path's origin.

The orchestrator and the policy are in `rediacc_ci.quality.gate_tree_writes`; the TS/JS half is `scripts/lib/tree-write-sites.ts`. Both halves read the same mutator table, `.ci/config/tree-write-mutators.json`, and both implement the same origin lattice, so they cannot disagree about what a write or a tree path is. agent/plans/PLAN-ci-gate-write-taint-scanners.md
section 3 is the design.

WHAT A MODULE MODEL HOLDS, built once per file from `ast`:
  - UNITS: `<top>` (the module body, which runs at import), `<main>` (an `if __name__ == "__main__":` block, which runs only when the file is the entry), and one per top-level function or class. Each unit records the names it references, so reachability is a walk over units rather than over files.
  - IMPORTS: `rediacc_ci.*` resolved to `.ci/rediacc_ci/**` (package `__init__` files included, `tests/` skipped), relative imports, and a bare `import x` that names a sibling file (the `_cipath` shape of `.ci/scripts/quality/`).
  - SPAWN EDGES: a script path literal (`.py/.mjs/.cjs/.js/.ts/.sh`) inside a subprocess call's arguments, or inside a binding those arguments name one hop away. This is the edge that carries `check_lint_rule_liveness.py` to `lint-rule-liveness.mjs`, the file that actually wrote the tree.
  - SITES: `open`/`Path.open` with a write mode, `Path.write_text/write_bytes/touch/mkdir/unlink/rmdir/rename/replace/symlink_to/hardlink_to/chmod`, `shutil.*`, `os.*`, `tempfile.*(dir=...)`, `.extractall`, and subprocess runs of a mutator.

THE ORIGIN LATTICE is the TS half's, rank for rank: TEMP and OUTSIDE beat SCRATCH beats TREE beats UNRESOLVED; a relative literal is neutral inside a join and TREE when it is the whole target (every gate runs from the repo root). The seeds are the idiom, never the name: `tempfile.*`, `rediacc_ci.runtmp`, `$TMPDIR` and a `/tmp/` literal for TEMP; the `rediacc_ci.paths` root helpers, `__file__`,
`os.getcwd()`, `Path.cwd()` and `git rev-parse --show-toplevel` for TREE. `root` bound to `pathlib.Path(tmp)` is TEMP whatever it is called, which is the lesson `pool_writer_safety.py` records for bash.

HOW FAR THE TAINT GOES: flow-insensitive per scope with enclosing-scope lookup, module-local parameter flow to a fixpoint (a parameter takes its arguments' combined origin over every call in the module, the default for an omitted one), module-local return values, and module constants one import hop away. Everything else is UNRESOLVED.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import pathlib
import posixpath
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# --------------------------------------------------------------------------- the lattice

RANK = {"NONE": 0, "REL": 1, "UNRES": 2, "TREE": 3, "SCRATCH": 4, "TEMP": 5, "OUTSIDE": 5}
SCRATCH_PREFIX = ".ci/cache"
MUTATORS_REL = ".ci/config/tree-write-mutators.json"


@dataclasses.dataclass(frozen=True)
class Val:
    """An origin and, when known, the repo-relative path it names."""

    o: str
    rel: str | None = None


NONE = Val("NONE")
UNRES = Val("UNRES")
TEMP = Val("TEMP")
OUTSIDE = Val("OUTSIDE")


def tree_at(rel: str) -> Val:
    """A repo-relative path, classified: `..` leaves the tree, `.ci/cache` is scratch, the rest is tree."""
    n = posixpath.normpath(rel or ".").rstrip("/")
    if n == ".." or n.startswith("../"):
        return OUTSIDE
    r = "" if n == "." else n
    if r == SCRATCH_PREFIX or r.startswith(SCRATCH_PREFIX + "/"):
        return Val("SCRATCH", r)
    return Val("TREE", r)


def combine(a: Val, b: Val) -> Val:
    """The higher-ranked origin; an equal-ranked path is kept only when both sides agree on it."""
    if RANK[a.o] > RANK[b.o]:
        return a
    if RANK[b.o] > RANK[a.o]:
        return b
    if a == b:
        return a
    return Val(a.o)


def combine_all(vals: Iterable[Val]) -> Val:
    out = NONE
    for v in vals:
        out = combine(out, v)
    return out


def literal(s: str) -> Val:
    if s == "/tmp" or s.startswith("/tmp/"):
        return TEMP
    if s.startswith(("/", "~")):
        return OUTSIDE
    if re.match(r"^[a-z][a-z0-9+.-]*:", s, re.IGNORECASE):
        return UNRES
    return Val("REL", s)


def treeish(v: Val) -> bool:
    return v.o in ("TREE", "SCRATCH")


def join_vals(vals: list[Val], resolve: bool = False) -> Val:
    """`os.path.join` / `/` / `joinpath`: the combined origin, carrying the path when a tree base is followed by literals."""
    if not vals:
        return tree_at("") if resolve else NONE
    out = combine_all(vals)
    if out.o == "REL":
        if all(v.rel is not None for v in vals):
            joined = posixpath.join(*[v.rel or "" for v in vals])
            return tree_at(joined) if resolve else Val("REL", joined)
        return Val("TREE") if resolve else Val("REL")
    if not treeish(out):
        return out
    base = max(i for i, v in enumerate(vals) if treeish(v))
    b = vals[base]
    tail = vals[base + 1 :]
    if b.rel is not None and all(v.o == "REL" and v.rel is not None for v in tail):
        return tree_at(posixpath.join(b.rel, *[v.rel or "" for v in tail]))
    return Val(out.o)


def dirname_val(v: Val) -> Val:
    if v.rel is None:
        return v
    if v.o == "REL":
        return Val("REL", posixpath.dirname(v.rel))
    if treeish(v):
        return tree_at(".." if v.rel == "" else posixpath.dirname(v.rel))
    return v


def final_origin(v: Val) -> str:
    """The value at a WRITE. A relative path lands under the gate's cwd, which is the repo root."""
    if v.o == "REL":
        return "SCRATCH" if v.rel is not None and tree_at(v.rel).o == "SCRATCH" else "TREE"
    if v.o in ("NONE", "UNRES"):
        return "UNRESOLVED"
    return v.o


# --------------------------------------------------------------------------- the module model

Clause = list[str]


@dataclasses.dataclass
class Scope:
    id: int
    parent: Scope | None
    names: dict[str, list[Binding]] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Fn:
    id: int
    name: str
    scope: Scope
    params: list[str]
    defaults: dict[str, ast.expr]
    returns: list[tuple[ast.expr, Scope]] = dataclasses.field(default_factory=list)
    # The guard clauses at every reference to this function, with the functions enclosing that reference.
    ref_guards: list[tuple[list[Clause], list[Fn]]] = dataclasses.field(default_factory=list)
    is_method: bool = False
    top_level: bool = False


@dataclasses.dataclass
class Binding:
    kind: str  # expr | elem | unpack | param | import | fn | class | unknown
    expr: ast.expr | None = None
    scope: Scope | None = None
    fn: Fn | None = None
    index: int = -1
    source: str | None = None
    imported: str = ""
    module: str = ""


@dataclasses.dataclass
class Call:
    node: ast.Call
    scope: Scope
    guard: list[Clause] = dataclasses.field(default_factory=list)
    fn_path: list[Fn] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class RawSite:
    line: int
    sink: str
    node: ast.AST
    value: Callable[[Evaluator], Val]
    scope: Scope
    guard: list[Clause]
    fn_path: list[Fn]
    unit: str


@dataclasses.dataclass
class Spawn:
    file: str
    argv: list[str]
    unit: str


@dataclasses.dataclass
class ImportEdge:
    source: str
    locals: dict[str, str]  # local -> imported name ('*' for a module namespace)
    unit: str


@dataclasses.dataclass
class Module:
    file: str
    src: str
    error: str | None
    units: dict[str, set[str]]
    attr_refs: dict[str, set[tuple[str, str]]]
    imports: list[ImportEdge]
    sites: list[RawSite]
    spawns: list[Spawn]
    top: Scope
    fns: list[Fn]
    calls: list[Call]
    flags: dict[str, str]  # argparse attribute -> --flag
    self_attrs: dict[str, list[Binding]] = dataclasses.field(default_factory=dict)
    lambdas: dict[int, Fn] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class Site:
    file: str
    line: int
    sink: str
    target: str
    origin: str
    guard: list[Clause]
    # The functions enclosing the site, until the group walk turns them into guard clauses.
    fn_path: list[Fn] = dataclasses.field(default_factory=list)
    # A context that exists only when another module in the group imports this function by name.
    only_if_requested: str | None = None


@dataclasses.dataclass
class GroupResult:
    modules: list[str]
    spawns: list[tuple[str, list[str]]]
    sites: list[Site]
    errors: list[str]


# Families: which stdlib names a canonical dotted call is spelled in.
STDLIB = {
    "os",
    "os.path",
    "shutil",
    "pathlib",
    "subprocess",
    "tempfile",
    "io",
    "tarfile",
    "zipfile",
    "sys",
    "codecs",
    "runpy",
}

OS_ONE = {
    "remove",
    "unlink",
    "rmdir",
    "removedirs",
    "mkdir",
    "makedirs",
    "chmod",
    "lchmod",
    "truncate",
    "utime",
    "chown",
}
OS_TWO = {"rename", "replace", "renames"}
OS_LINK = {"symlink", "link"}
SHUTIL_DEST = {"copy", "copy2", "copyfile", "copytree", "copymode", "copystat"}
PATH_METHODS_SELF = {
    "write_text",
    "write_bytes",
    "touch",
    "mkdir",
    "unlink",
    "rmdir",
    "symlink_to",
    "hardlink_to",
}
SUBPROCESS = {"run", "call", "check_call", "check_output", "Popen"}
TEMPFILE_FNS = {
    "mkdtemp",
    "mkstemp",
    "TemporaryDirectory",
    "NamedTemporaryFile",
    "TemporaryFile",
    "SpooledTemporaryFile",
    "gettempdir",
}
RUNTMP_FNS = {"run_dir", "shared", "shell_mktemp"}
# Environment variables that name a place: the temp dir, and the user's home (outside the tree).
ENV_SEEDS = {"TMPDIR": TEMP, "HOME": OUTSIDE}
# The `rediacc_ci.paths` root helpers and the repo-root finders, and the path each names.
ROOT_SEEDS = {
    "repo_root": "",
    "get_repo_root": "",
    "find_repo_root": "",
    "_repo_root": "",
    "ci_dir": ".ci",
    "quality_dir": ".ci/scripts/quality",
    "hooks_stop_dir": ".claude/hooks/stop",
    "from_root": "",
}
STRING_METHODS = {
    "replace",
    "strip",
    "rstrip",
    "lstrip",
    "format",
    "as_posix",
    "resolve",
    "absolute",
    "expanduser",
    "lower",
}
SCRIPT_EXT = re.compile(r"\.(py|mjs|cjs|js|ts|sh)$")
WRITE_MODE = re.compile(r"[wax+]")


def _const_str(e: ast.AST | None) -> str | None:
    if isinstance(e, ast.Constant) and isinstance(e.value, str):
        return e.value
    return None


def _kw(call: ast.Call, name: str) -> ast.expr | None:
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def _arg(call: ast.Call, i: int, kw: str | None = None) -> ast.expr | None:
    if kw is not None:
        v = _kw(call, kw)
        if v is not None:
            return v
    if i < len(call.args) and not isinstance(call.args[i], ast.Starred):
        return call.args[i]
    return None


class Analyzer:
    """Module models for one tree, cached, plus the per-group reachability walk."""

    def __init__(self, root: pathlib.Path, mutators: dict) -> None:
        self.root = root
        self.mutators = mutators
        self._cache: dict[str, Module] = {}
        self._finished: dict[str, list[tuple[str, Site]]] = {}
        self._evaluators: dict[str, Evaluator] = {}
        self._seq = 0

    def next_id(self) -> int:
        self._seq += 1
        return self._seq

    def is_file(self, rel: str) -> bool:
        return (self.root / rel).is_file()

    # ---------------------------------------------------------- resolution

    def resolve_module(self, dotted: str, from_rel: str, level: int = 0) -> str | None:
        """A dotted module name to a repo-relative `.py`; None for the stdlib, a package outside the tree, or `tests/`."""
        if level > 0:
            base = posixpath.dirname(from_rel)
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            parts = [base, *dotted.split(".")] if dotted else [base]
            cand = posixpath.join(*parts)
        elif dotted == "rediacc_ci" or dotted.startswith("rediacc_ci."):
            cand = posixpath.join(".ci", *dotted.split("."))
        else:
            cand = posixpath.join(posixpath.dirname(from_rel), *dotted.split("."))
        if "/tests/" in cand + "/" and cand.startswith(".ci/rediacc_ci"):
            return None
        for c in (cand + ".py", cand + "/__init__.py"):
            if self.is_file(c):
                return c
        return None

    def package_inits(self, rel: str) -> list[str]:
        """The `__init__.py` files a submodule import also runs."""
        out: list[str] = []
        parts = rel.split("/")
        for i in range(2, len(parts)):
            init = "/".join([*parts[:i], "__init__.py"])
            if init != rel and init.startswith(".ci/rediacc_ci") and self.is_file(init):
                out.append(init)
        return out

    def resolve_script(self, from_rel: str, name: str) -> str | None:
        if not SCRIPT_EXT.search(name):
            return None
        cands = (
            [name]
            if name.startswith("/")
            else [
                posixpath.normpath(posixpath.join(posixpath.dirname(from_rel), name)),
                posixpath.normpath(name),
            ]
        )
        for c in cands:
            p = pathlib.Path(c) if c.startswith("/") else self.root / c
            try:
                if p.is_file():
                    return p.resolve().relative_to(self.root.resolve()).as_posix()
            except (OSError, ValueError):
                continue
        return None

    def module(self, rel: str) -> Module:
        hit = self._cache.get(rel)
        if hit is not None:
            return hit
        m = Module(
            rel,
            "",
            None,
            {"<top>": set(), "<main>": set()},
            {},
            [],
            [],
            [],
            Scope(self.next_id(), None),
            [],
            [],
            {},
        )
        self._cache[rel] = m
        try:
            m.src = (self.root / rel).read_text(encoding="utf-8")
            tree = ast.parse(m.src, filename=rel)
        except (OSError, SyntaxError, ValueError) as exc:
            m.error = "%s: %s" % (type(exc).__name__, exc)
            return m
        Walker(self, m).walk(tree)
        return m

    def sites_of(self, m: Module) -> list[tuple[str, Site]]:
        """Every site of a module, ONE PER CALLING CONTEXT of its innermost function.

        A write whose target is a parameter is judged per call: `write_baseline(root)` called with a temp root from the selftest and with the repo root under a reseed flag is a TEMP write that always runs plus a TREE write that is mode-gated, not one TREE write that always runs. A reference that is not a call (a dispatch table, an import from another module) keeps the combined, context-free verdict.
        """
        hit = self._finished.get(m.file)
        if hit is not None:
            return hit
        ev = self.evaluator(m)
        out: list[tuple[str, Site]] = []
        lines = m.src.split("\n")
        for raw in m.sites:
            line_text = lines[raw.line - 1].strip() if 0 < raw.line <= len(lines) else ""
            target = re.sub(r"\s+", " ", ast.get_source_segment(m.src, raw.node) or line_text)[:100]
            local = ev.resolve_guard(raw.guard)
            seen: set[str] = set()

            def emit(
                origin: str,
                guard: list[Clause],
                fn_path: list[Fn],
                only_if: str | None,
                raw: RawSite = raw,
                target: str = target,
                seen: set[str] = seen,
            ) -> None:
                key = json.dumps([origin, guard, [f.id for f in fn_path], only_if])
                if key not in seen:
                    seen.add(key)
                    out.append(
                        (
                            raw.unit,
                            Site(
                                m.file, raw.line, raw.sink, target, origin, guard, fn_path, only_if
                            ),
                        )
                    )

            inner = raw.fn_path[-1] if raw.fn_path else None
            calls = ev.calls_of(inner) if inner is not None and inner.params else []
            if not calls:
                emit(final_origin(raw.value(ev)), local, list(raw.fn_path), None)
                continue
            for call in calls:
                cev = Evaluator(self, m, {inner.id: call}) if inner is not None else ev
                emit(
                    final_origin(raw.value(cev)),
                    local + ev.resolve_guard(call.guard),
                    raw.fn_path[:-1] + call.fn_path,
                    None,
                )
            if inner is not None and len(inner.ref_guards) > len(calls):
                emit(final_origin(raw.value(ev)), local, list(raw.fn_path), None)
            elif inner is not None and inner.top_level:
                emit(final_origin(raw.value(ev)), local, raw.fn_path[:-1], inner.name)
        self._finished[m.file] = out
        return out

    # ---------------------------------------------------------- groups

    def analyze_group(self, entries: list[str]) -> GroupResult:
        """Closure, reachability, live sites and foreign spawns of one group of Python entry files."""
        live: dict[str, set[str]] = {}
        seen_req: set[tuple[str, str | None]] = set()
        queue: list[tuple[str, str | None]] = []
        loaded: list[str] = []
        errors: list[str] = []
        entry_set = set(entries)
        # Names another module in this group imports: a function reachable from outside is not guarded by its module-local calls.
        requested: dict[str, set[str]] = {}

        def enter(file: str, name: str | None) -> None:
            if name is not None:
                requested.setdefault(file, set()).add(name)
            if (file, name) not in seen_req:
                seen_req.add((file, name))
                queue.append((file, name))

        def mark(m: Module, unit: str, work: list[str]) -> None:
            s = live.setdefault(m.file, set())
            if unit not in s and (unit in m.units):
                s.add(unit)
                work.append(unit)

        for e in entries:
            enter(e, None)
        while queue:
            file, name = queue.pop(0)
            m = self.module(file)
            if file not in loaded:
                loaded.append(file)
                if m.error:
                    errors.append("%s: %s" % (file, m.error))
                for init in self.package_inits(file):
                    enter(init, None)
            work: list[str] = []
            mark(m, "<top>", work)
            if file in entry_set:
                mark(m, "<main>", work)
            if name == "*":
                for u in m.units:
                    if u != "<main>":
                        mark(m, u, work)
            elif name is not None:
                if name in m.units:
                    mark(m, name, work)
                for b in m.top.names.get(name, []):
                    if b.kind == "import" and b.source:
                        enter(b.source, b.imported)
            while work:
                unit = work.pop()
                refs = m.units.get(unit, set())
                for r in refs:
                    if r in m.units and r not in ("<top>", "<main>"):
                        mark(m, r, work)
                attrs = m.attr_refs.get(unit, set())
                for edge in m.imports:
                    if edge.unit == unit:
                        enter(edge.source, None)
                    for local, imported in edge.locals.items():
                        if imported == "*":
                            used = {a for (b, a) in attrs if b == local}
                            for a in sorted(used):
                                enter(edge.source, a)
                        elif local in refs:
                            enter(edge.source, imported)
        sites: list[Site] = []
        spawns: list[tuple[str, list[str]]] = []
        for file in sorted(loaded):
            m = self.module(file)
            units = live.get(file, set())
            for sp in m.spawns:
                if sp.unit in units and all(sp.file != f for f, _ in spawns):
                    spawns.append((sp.file, sp.argv))
            ev = self.evaluator(m)
            for unit, site in self.sites_of(m):
                req = requested.get(file, set())
                if unit in units and (
                    site.only_if_requested is None or site.only_if_requested in req or "*" in req
                ):
                    fn_clauses = ev.fn_guard(site.fn_path, req, set())
                    sites.append(
                        dataclasses.replace(
                            site, guard=site.guard + fn_clauses, fn_path=[], only_if_requested=None
                        )
                    )
        return GroupResult(sorted(loaded), spawns, sites, errors)

    def evaluator(self, m: Module) -> Evaluator:
        ev = self._evaluators.get(m.file)
        if ev is None:
            ev = Evaluator(self, m)
            self._evaluators[m.file] = ev
        return ev


# --------------------------------------------------------------------------- the walk


class Walker:
    """One pass over a module's AST: scopes, bindings, units, imports, calls, sites, spawns, guards."""

    def __init__(self, a: Analyzer, m: Module) -> None:
        self.a = a
        self.m = m
        self.unit = "<top>"
        self.pending: list[tuple[Scope, str, Binding]] = []
        self.fn_refs: list[tuple[str, Scope, list[Clause], list[Fn], bool]] = []

    # ---------------------------------------------------------- bindings

    def declare(self, scope: Scope, name: str, b: Binding) -> None:
        scope.names.setdefault(name, []).append(b)

    def bind_target(self, scope: Scope, target: ast.expr, b: Binding) -> None:
        if isinstance(target, ast.Name):
            self.declare(scope, target.id, b)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self.bind_target(scope, elt.value if isinstance(elt, ast.Starred) else elt, b)

    def ref(self, name: str) -> None:
        self.m.units.setdefault(self.unit, set()).add(name)

    def attr_ref(self, base: str, attr: str) -> None:
        self.m.attr_refs.setdefault(self.unit, set()).add((base, attr))

    # ---------------------------------------------------------- imports

    def do_import(self, node: ast.Import | ast.ImportFrom, scope: Scope) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                rel = self.a.resolve_module(alias.name, self.m.file)
                if alias.asname:
                    local, target = alias.asname, rel
                else:
                    local = alias.name.split(".")[0]
                    target = self.a.resolve_module(local, self.m.file)
                    if rel and rel != target:
                        # `import rediacc_ci.quality.x` loads x; the local name is the package.
                        self.m.imports.append(ImportEdge(rel, {}, self.unit))
                self.declare(
                    scope,
                    local,
                    Binding(
                        "import",
                        source=target,
                        imported="*",
                        module=alias.name if alias.asname else local,
                    ),
                )
                if target:
                    self.m.imports.append(ImportEdge(target, {local: "*"}, self.unit))
            return
        mod = node.module or ""
        src = self.a.resolve_module(mod, self.m.file, node.level) if (mod or node.level) else None
        locals_: dict[str, str] = {}
        for alias in node.names:
            local = alias.asname or alias.name
            sub = (
                self.a.resolve_module(
                    (mod + "." if mod else "") + alias.name, self.m.file, node.level
                )
                if (mod or node.level)
                else None
            )
            if sub and sub != src:
                self.declare(
                    scope,
                    local,
                    Binding("import", source=sub, imported="*", module="%s.%s" % (mod, alias.name)),
                )
                self.m.imports.append(ImportEdge(sub, {local: "*"}, self.unit))
                continue
            self.declare(
                scope,
                local,
                Binding(
                    "import",
                    source=src,
                    imported=alias.name,
                    module="%s.%s" % (mod, alias.name) if mod else alias.name,
                ),
            )
            if src:
                locals_[local] = alias.name
        if src:
            self.m.imports.append(ImportEdge(src, locals_, self.unit))

    # ---------------------------------------------------------- statements

    def walk(self, tree: ast.Module) -> None:
        for st in tree.body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.m.units.setdefault(st.name, set())
        self.collect_argparse(tree)
        for st in tree.body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.unit = st.name
                self.statement(st, self.m.top, [], [], top_level=True)
                self.unit = "<top>"
            elif self.is_main_guard(st):
                self.unit = "<main>"
                self.statement(st, self.m.top, [], [])
                self.unit = "<top>"
            else:
                self.statement(st, self.m.top, [], [])
        for scope, name, b in self.pending:
            s: Scope | None = scope
            while s is not None and name not in s.names:
                s = s.parent
            self.declare(s or scope, name, b)
        # References are resolved AFTER the walk: a function defined below its caller is not yet bound when the caller is walked.
        for name, scope, guard, fn_path, is_attr in self.fn_refs:
            targets = (
                [fn for fn in self.m.fns if fn.is_method and fn.name == name]
                if is_attr
                else self.lookup_fns(name, scope)
            )
            for fn in targets:
                fn.ref_guards.append((guard, fn_path))

    @staticmethod
    def is_main_guard(st: ast.stmt) -> bool:
        if not isinstance(st, ast.If) or not isinstance(st.test, ast.Compare):
            return False
        left = st.test.left
        return (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and any(_const_str(c) == "__main__" for c in st.test.comparators)
        )

    def collect_argparse(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                continue
            flag = next(
                (s for s in (_const_str(a) for a in node.args) if s and s.startswith("--")), None
            )
            action = _const_str(_kw(node, "action"))
            if flag is None or action not in ("store_true", "count"):
                continue
            dest = _const_str(_kw(node, "dest")) or flag.lstrip("-").replace("-", "_")
            self.m.flags[dest] = flag

    def statements(
        self, body: list[ast.stmt], scope: Scope, guard: list[Clause], fn_path: list[Fn]
    ) -> None:
        g = guard
        for st in body:
            self.statement(st, scope, g, fn_path)
            if isinstance(st, ast.If) and not st.orelse and st.body and self.exits(st.body[-1]):
                g = g + Evaluator(self.a, self.m).test_clauses(st.test, scope)[1]

    @staticmethod
    def exits(st: ast.stmt) -> bool:
        if isinstance(st, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
            return True
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            f = st.value.func
            name = (
                f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
            )
            return name in ("exit", "_exit")
        return False

    def function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
        scope: Scope,
        fn_path: list[Fn],
        name: str,
        is_method: bool,
        top_level: bool,
        guard: list[Clause] | None = None,
    ) -> Fn:
        """A body starts under the guard at its DEFINITION: a closure defined inside `if write:` cannot run unless that branch did."""
        guard = guard or []
        inner = Scope(self.a.next_id(), scope)
        args = node.args
        positional = [*args.posonlyargs, *args.args]
        params = [a.arg for a in positional]
        defaults: dict[str, ast.expr] = {}
        for a, d in zip(
            positional[len(positional) - len(args.defaults) :], args.defaults, strict=False
        ):
            defaults[a.arg] = d
        for kw, kd in zip(args.kwonlyargs, args.kw_defaults, strict=False):
            params.append(kw.arg)
            if kd is not None:
                defaults[kw.arg] = kd
        fn = Fn(
            self.a.next_id(),
            name,
            inner,
            params,
            defaults,
            is_method=is_method,
            top_level=top_level,
        )
        self.m.fns.append(fn)
        path2 = [*fn_path, fn]
        for i, p in enumerate(params):
            if is_method and i == 0:
                self.declare(inner, p, Binding("unknown"))
                continue
            self.declare(
                inner, p, Binding("param", fn=fn, index=i, expr=defaults.get(p), scope=scope)
            )
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                self.declare(inner, extra.arg, Binding("unknown"))
        for d in [*args.defaults, *[x for x in args.kw_defaults if x is not None]]:
            self.expr(d, scope, [], fn_path)
        if isinstance(node, ast.Lambda):
            self.m.lambdas[id(node)] = fn
            fn.returns.append((node.body, inner))
            self.expr(node.body, inner, guard, path2)
        else:
            for dec in node.decorator_list:
                self.expr(dec, scope, [], fn_path)
            self.statements(node.body, inner, guard, path2)
        return fn

    def statement(
        self,
        st: ast.stmt,
        scope: Scope,
        guard: list[Clause],
        fn_path: list[Fn],
        top_level: bool = False,
    ) -> None:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn = self.function(
                st, scope, fn_path, st.name, is_method=False, top_level=top_level, guard=guard
            )
            self.declare(scope, st.name, Binding("fn", fn=fn))
            return
        if isinstance(st, ast.ClassDef):
            for b in st.bases:
                self.expr(b, scope, guard, fn_path)
            init: Fn | None = None
            for inner in st.body:
                if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fn = self.function(
                        inner,
                        scope,
                        fn_path,
                        inner.name,
                        is_method=not any(
                            isinstance(d, ast.Name) and d.id == "staticmethod"
                            for d in inner.decorator_list
                        ),
                        top_level=False,
                        guard=guard,
                    )
                    fn.ref_guards.append(
                        ([], [])
                    )  # a method is reachable through its instance; never guard-derived
                    if inner.name == "__init__":
                        init = fn
                else:
                    self.statement(inner, scope, guard, fn_path)
            # `Harness(tmp)` calls `__init__(self, tmp)`, so `self.temp = temp` takes the argument's origin.
            self.declare(scope, st.name, Binding("class", fn=init))
            return
        if isinstance(st, (ast.Import, ast.ImportFrom)):
            self.do_import(st, scope)
            return
        if isinstance(st, ast.If):
            self.expr(st.test, scope, guard, fn_path)
            t, f = Evaluator(self.a, self.m).test_clauses(st.test, scope)
            self.statements(st.body, scope, guard + t, fn_path)
            self.statements(st.orelse, scope, guard + f, fn_path)
            return
        if isinstance(st, ast.Assign):
            for tg in st.targets:
                self.target(tg, scope, st.value, guard, fn_path)
            self.expr(st.value, scope, guard, fn_path)
            return
        if isinstance(st, (ast.AnnAssign, ast.AugAssign)):
            if st.value is not None:
                self.target(st.target, scope, st.value, guard, fn_path)
                self.expr(st.value, scope, guard, fn_path)
            return
        if isinstance(st, (ast.For, ast.AsyncFor)):
            self.expr(st.iter, scope, guard, fn_path)
            self.bind_target(scope, st.target, Binding("elem", expr=st.iter, scope=scope))
            self.statements(st.body, scope, guard, fn_path)
            self.statements(st.orelse, scope, guard, fn_path)
            return
        if isinstance(st, (ast.With, ast.AsyncWith)):
            for item in st.items:
                self.expr(item.context_expr, scope, guard, fn_path)
                if item.optional_vars is not None:
                    self.bind_target(
                        scope,
                        item.optional_vars,
                        Binding("expr", expr=item.context_expr, scope=scope),
                    )
            self.statements(st.body, scope, guard, fn_path)
            return
        if isinstance(st, ast.Return):
            if st.value is not None:
                if fn_path:
                    fn_path[-1].returns.append((st.value, scope))
                self.expr(st.value, scope, guard, fn_path)
            return
        if isinstance(st, (ast.Try, ast.TryStar)):
            self.statements(st.body, scope, guard, fn_path)
            for h in st.handlers:
                if h.name:
                    self.declare(scope, h.name, Binding("unknown"))
                self.statements(h.body, scope, guard, fn_path)
            self.statements(st.orelse, scope, guard, fn_path)
            self.statements(st.finalbody, scope, guard, fn_path)
            return
        if isinstance(st, ast.While):
            self.expr(st.test, scope, guard, fn_path)
            self.statements(st.body, scope, guard, fn_path)
            self.statements(st.orelse, scope, guard, fn_path)
            return
        if isinstance(st, ast.Match):
            self.expr(st.subject, scope, guard, fn_path)
            for case in st.cases:
                self.statements(case.body, scope, guard, fn_path)
            return
        for child in ast.iter_child_nodes(st):
            if isinstance(child, ast.expr):
                self.expr(child, scope, guard, fn_path)
            elif isinstance(child, ast.stmt):
                self.statement(child, scope, guard, fn_path)

    def target(
        self, tg: ast.expr, scope: Scope, value: ast.expr, guard: list[Clause], fn_path: list[Fn]
    ) -> None:
        if (
            isinstance(tg, (ast.Tuple, ast.List))
            and isinstance(value, (ast.Tuple, ast.List))
            and len(tg.elts) == len(value.elts)
        ):
            for t, v in zip(tg.elts, value.elts, strict=True):
                self.target(t, scope, v, guard, fn_path)
            return
        if isinstance(tg, (ast.Tuple, ast.List)):
            # `root, rel = build_fixture(td)`: element i of what the call returns.
            for i, elt in enumerate(tg.elts):
                if isinstance(elt, ast.Name):
                    self.declare(scope, elt.id, Binding("unpack", expr=value, scope=scope, index=i))
            return
        if isinstance(tg, ast.Name):
            self.bind_target(scope, tg, Binding("expr", expr=value, scope=scope))
            return
        if (
            isinstance(tg, ast.Attribute)
            and isinstance(tg.value, ast.Name)
            and tg.value.id in ("self", "cls")
        ):
            # `self.temp = tempfile.mkdtemp()`: every `self.temp` in the module takes that origin.
            self.m.self_attrs.setdefault(tg.attr, []).append(
                Binding("expr", expr=value, scope=scope)
            )
        self.expr(tg, scope, guard, fn_path)

    # ---------------------------------------------------------- expressions

    def lookup_fns(self, name: str, scope: Scope) -> list[Fn]:
        s: Scope | None = scope
        while s is not None:
            if name in s.names:
                return [b.fn for b in s.names[name] if b.kind == "fn" and b.fn is not None]
            s = s.parent
        return []

    def expr(self, e: ast.expr, scope: Scope, guard: list[Clause], fn_path: list[Fn]) -> None:
        if isinstance(e, ast.Name):
            if isinstance(e.ctx, ast.Load):
                self.ref(e.id)
                self.fn_refs.append((e.id, scope, guard, fn_path, False))
            return
        if isinstance(e, ast.Attribute):
            if isinstance(e.value, ast.Name):
                self.attr_ref(e.value.id, e.attr)
            self.fn_refs.append((e.attr, scope, guard, fn_path, True))
            self.expr(e.value, scope, guard, fn_path)
            return
        if isinstance(e, ast.Lambda):
            self.function(
                e, scope, fn_path, "<lambda>", is_method=False, top_level=False, guard=guard
            )
            return
        if isinstance(e, ast.NamedExpr):
            self.pending.append((scope, e.target.id, Binding("expr", expr=e.value, scope=scope)))
            self.expr(e.value, scope, guard, fn_path)
            return
        if isinstance(e, ast.IfExp):
            self.expr(e.test, scope, guard, fn_path)
            t, f = Evaluator(self.a, self.m).test_clauses(e.test, scope)
            self.expr(e.body, scope, guard + t, fn_path)
            self.expr(e.orelse, scope, guard + f, fn_path)
            return
        if isinstance(e, ast.BoolOp) and isinstance(e.op, ast.And):
            g = guard
            for v in e.values:
                self.expr(v, scope, g, fn_path)
                g = g + Evaluator(self.a, self.m).test_clauses(v, scope)[0]
            return
        if isinstance(e, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            for gen in e.generators:
                self.expr(gen.iter, scope, guard, fn_path)
                self.bind_target(scope, gen.target, Binding("elem", expr=gen.iter, scope=scope))
                for cond in gen.ifs:
                    self.expr(cond, scope, guard, fn_path)
        if isinstance(e, ast.Call):
            self.call(e, scope, guard, fn_path)
        for child in ast.iter_child_nodes(e):
            if isinstance(child, ast.expr):
                if isinstance(
                    e, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)
                ) and any(child is g.iter for g in e.generators):
                    continue
                self.expr(child, scope, guard, fn_path)

    # ---------------------------------------------------------- calls: sinks and spawns

    def call(self, e: ast.Call, scope: Scope, guard: list[Clause], fn_path: list[Fn]) -> None:
        self.m.calls.append(Call(e, scope, guard, fn_path))
        f = e.func
        if (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and f.attr in ("append", "add", "insert", "extend")
        ):
            # `xs.append(v)` is a binding of `xs`: a later `for x in xs` takes v's origin.
            for a in e.args[-1:]:
                kind = "elem" if f.attr == "extend" else "expr"
                self.pending.append((scope, f.value.id, Binding(kind, expr=a, scope=scope)))
        ev = Evaluator(self.a, self.m)
        canon = ev.canonical(e.func, scope)
        unit = self.unit

        def add(sink: str, node: ast.AST, value: Callable[[Evaluator], Val]) -> None:
            self.m.sites.append(RawSite(e.lineno, sink, node, value, scope, guard, fn_path, unit))

        def at(x: ast.expr | None, fallback: Val = UNRES) -> Callable[[Evaluator], Val]:
            return lambda v: v.ev(x, scope) if x is not None else fallback

        if canon in ("open", "io.open", "codecs.open", "builtins.open"):
            mode = _const_str(_arg(e, 1, "mode")) or "r"
            target = _arg(e, 0, "file")
            if WRITE_MODE.search(mode) and target is not None:
                add("open", target, at(target))
            return
        if canon.startswith("os.") and canon.count(".") == 1:
            self.os_sink(e, canon[3:], add, at)
            return
        if canon.startswith("shutil."):
            fn = canon[7:]
            if fn in SHUTIL_DEST:
                add("shutil." + fn, e, at(_arg(e, 1, "dst")))
            elif fn == "move":
                add("shutil.move", e, at(_arg(e, 0, "src")))
                add("shutil.move", e, at(_arg(e, 1, "dst")))
            elif fn == "rmtree":
                add("shutil.rmtree", e, at(_arg(e, 0, "path")))
            return
        if canon.startswith("tempfile.") and canon[9:] in TEMPFILE_FNS:
            d = _kw(e, "dir")
            if d is not None:
                add(canon, d, at(d))
            return
        if canon in ("tarfile.open", "zipfile.ZipFile"):
            mode = _const_str(_arg(e, 1, "mode")) or "r"
            target = _arg(e, 0, "name" if canon == "tarfile.open" else "file")
            if WRITE_MODE.search(mode) and target is not None:
                add(canon, target, at(target))
            return
        if (
            (canon.startswith("subprocess.") and canon[11:] in SUBPROCESS)
            or canon == "os.system"
            or re.match(r"^os\.(exec|spawn)", canon)
        ):
            self.subprocess(e, scope, add)
            return
        if isinstance(e.func, ast.Attribute) and not ev.is_module(e.func.value, scope):
            self.method_sink(e, add, at)

    def os_sink(
        self,
        e: ast.Call,
        fn: str,
        add: Callable[..., None],
        at: Callable[..., Callable[[Evaluator], Val]],
    ) -> None:
        if fn in OS_ONE:
            add("os." + fn, e, at(_arg(e, 0, "path")))
        elif fn in OS_TWO:
            add("os." + fn, e, at(_arg(e, 0, "src")))
            add("os." + fn, e, at(_arg(e, 1, "dst")))
        elif fn in OS_LINK:
            add("os." + fn, e, at(_arg(e, 1, "dst")))
        elif fn == "open":
            flags = ast.get_source_segment(self.m.src, e.args[1]) if len(e.args) > 1 else ""
            if flags and re.search(r"O_(WRONLY|RDWR|CREAT|TRUNC|APPEND)", flags):
                add("os.open", e, at(_arg(e, 0, "path")))

    def method_sink(
        self, e: ast.Call, add: Callable[..., None], at: Callable[..., Callable[[Evaluator], Val]]
    ) -> None:
        func = e.func
        if not isinstance(func, ast.Attribute):
            return
        obj = func.value
        name = func.attr
        npos = len(e.args)
        # The arity is what tells a Path method from a same-named str/dict one: `s.replace(a, b)` takes two.
        self_target = (
            (name in ("write_text", "write_bytes") and npos + len(e.keywords) >= 1)
            or (name in ("touch", "unlink", "rmdir", "mkdir") and npos == 0)
            or (name in ("symlink_to", "hardlink_to", "chmod") and npos == 1)
        )
        if self_target:
            add("Path." + name, obj, at(obj))
        elif name in ("rename", "replace") and npos == 1 and not e.keywords:
            add("Path." + name, obj, at(obj))
            add("Path." + name, e.args[0], at(e.args[0]))
        elif name == "open":
            mode = _const_str(_arg(e, 0, "mode")) or "r"
            if WRITE_MODE.search(mode):
                add("Path.open", obj, at(obj))
        elif name == "extractall":
            target = _arg(e, 0, "path")
            add("extractall", e, at(target, tree_at("")))

    def subprocess(self, e: ast.Call, scope: Scope, add: Callable[..., None]) -> None:
        self.spawn_edges(e, scope)
        ev = Evaluator(self.a, self.m)
        words = ev.words(_arg(e, 0, "args"), scope)
        cwd_node = _kw(e, "cwd")

        def cwd(v: Evaluator) -> Val:
            return v.ev(cwd_node, scope) if cwd_node is not None else tree_at("")

        for prog, value in mutator_targets(self.a.mutators, words, cwd):
            add("exec:" + prog, e, value)

    def spawn_edges(self, e: ast.Call, scope: Scope) -> None:
        strings: list[str] = []
        flags: list[str] = []
        seen: set[int] = set()

        def collect(n: ast.AST, depth: int) -> None:
            if id(n) in seen:
                return
            seen.add(id(n))
            s = _const_str(n)
            if s is not None:
                strings.append(s)
                if s.startswith("--"):
                    flags.append(s)
            elif isinstance(n, ast.Name) and depth < 2:
                sc: Scope | None = scope
                while sc is not None and n.id not in sc.names:
                    sc = sc.parent
                for b in sc.names.get(n.id, []) if sc is not None else []:
                    if b.kind == "expr" and b.expr is not None:
                        collect(b.expr, depth + 1)
                if sc is None:
                    for b in self.m.top.names.get(n.id, []):
                        if b.kind == "expr" and b.expr is not None:
                            collect(b.expr, depth + 1)
            for child in ast.iter_child_nodes(n):
                collect(child, depth)

        for a in [*e.args, *[k.value for k in e.keywords]]:
            collect(a, 0)
        for s in strings:
            for tok in s.split():
                f = self.a.resolve_script(self.m.file, tok.strip("'\""))
                if f and f != self.m.file:
                    self.m.spawns.append(Spawn(f, flags, self.unit))


# --------------------------------------------------------------------------- evaluation


class Evaluator:
    """Origins of expressions and guard clauses of tests, over one module's model."""

    def __init__(self, a: Analyzer, m: Module, ctx: dict[int, Call] | None = None) -> None:
        self.a = a
        self.m = m
        # One call pinned per function: the parameter values of THAT call, for a per-call verdict.
        self.ctx: dict[int, Call] = ctx or {}
        self.memo: dict[tuple[int, int], Val] = {}
        self.busy: set[tuple[int, int]] = set()

    def lookup(self, name: str, scope: Scope) -> list[Binding] | None:
        s: Scope | None = scope
        while s is not None:
            if name in s.names:
                return s.names[name]
            s = s.parent
        return None

    def import_of(self, name: str, scope: Scope) -> Binding | None:
        for b in self.lookup(name, scope) or []:
            if b.kind == "import":
                return b
        return None

    def is_module(self, e: ast.expr, scope: Scope) -> bool:
        if isinstance(e, ast.Name):
            b = self.import_of(e.id, scope)
            return b is not None and b.imported == "*"
        if isinstance(e, ast.Attribute):
            return self.canonical(e, scope) in STDLIB
        return False

    def canonical(self, func: ast.expr, scope: Scope) -> str:
        parts: list[str] = []
        x: ast.expr = func
        while isinstance(x, ast.Attribute):
            parts.insert(0, x.attr)
            x = x.value
        if not isinstance(x, ast.Name):
            return ""
        b = self.import_of(x.id, scope)
        head = b.module if b is not None else x.id
        return ".".join([head, *parts])

    # ---------------------------------------------------------- values

    def binding_val(self, b: Binding) -> Val:
        if b.kind == "expr" and b.expr is not None and b.scope is not None:
            return self.ev(b.expr, b.scope)
        if b.kind == "elem" and b.expr is not None and b.scope is not None:
            it = b.expr
            if isinstance(it, (ast.List, ast.Tuple, ast.Set)):
                return combine_all(self.ev(x, b.scope) for x in it.elts)
            return self.ev(it, b.scope)
        if b.kind == "param" and b.fn is not None:
            return self.param_val(b.fn, b.index, b.expr, b.scope)
        if b.kind == "import":
            return self.import_val(b.source, b.imported, 0)
        if b.kind == "unpack" and b.expr is not None and b.scope is not None:
            return self.unpack_val(b.expr, b.index, b.scope)
        if b.kind == "fn":
            return NONE
        return UNRES

    def unpack_val(self, value: ast.expr, index: int, scope: Scope) -> Val:
        def pick(e: ast.expr, s: Scope) -> Val:
            if isinstance(e, (ast.Tuple, ast.List)) and 0 <= index < len(e.elts):
                return self.ev(e.elts[index], s)
            return self.ev(e, s)

        if isinstance(value, ast.Call):
            targets = self.call_targets(value, scope)
            if targets:
                out = combine_all(pick(r, s) for f in targets for r, s in f.returns)
                return UNRES if out.o == "NONE" else out
        return pick(value, scope)

    def import_val(self, source: str | None, name: str, depth: int) -> Val:
        if source is None or depth > 1 or name == "*":
            return UNRES
        m = self.a.module(source)
        if m.error:
            return UNRES
        bs = m.top.names.get(name)
        if not bs:
            return UNRES
        sub = Evaluator(self.a, m)
        return combine_all(
            sub.import_val(b.source, b.imported, depth + 1)
            if b.kind == "import"
            else sub.binding_val(b)
            for b in bs
        )

    def call_targets(self, call: ast.Call, scope: Scope) -> list[Fn]:
        f = call.func
        if isinstance(f, ast.Name):
            return self.callable_fns(f, scope, 0)
        if isinstance(f, ast.Attribute) and not self.is_module(f.value, scope):
            # `self.run(...)` and `sh.run(...)` alike: the module's methods of that name.
            return [fn for fn in self.m.fns if fn.is_method and fn.name == f.attr]
        return []

    def callable_fns(self, e: ast.expr, scope: Scope, depth: int) -> list[Fn]:
        """The module-local functions a callable expression names: a def, a class (its `__init__`), a lambda, or a name bound to one -- including one unpacked from what a function returns (`legacy, g_arg = g_subject(...)` then `g_arg("x")`)."""
        if depth > 3:
            return []
        if isinstance(e, ast.Lambda):
            fn = self.m.lambdas.get(id(e))
            return [fn] if fn is not None else []
        if not isinstance(e, ast.Name):
            return []
        out: list[Fn] = []
        for b in self.lookup(e.id, scope) or []:
            if b.kind in ("fn", "class") and b.fn is not None:
                out.append(b.fn)
            elif b.kind == "expr" and b.expr is not None and b.scope is not None:
                out.extend(self.callable_fns(b.expr, b.scope, depth + 1))
            elif b.kind == "unpack" and isinstance(b.expr, ast.Call) and b.scope is not None:
                for f in self.call_targets(b.expr, b.scope):
                    for r, rs in f.returns:
                        if isinstance(r, (ast.Tuple, ast.List)) and 0 <= b.index < len(r.elts):
                            out.extend(self.callable_fns(r.elts[b.index], rs, depth + 1))
        return out

    def arg_for(self, call: ast.Call, fn: Fn, index: int) -> ast.expr | None:
        name = fn.params[index] if index < len(fn.params) else ""
        for k in call.keywords:
            if k.arg == name:
                return k.value
        pos = index - (1 if fn.is_method else 0)
        if 0 <= pos < len(call.args) and not any(
            isinstance(a, ast.Starred) for a in call.args[: pos + 1]
        ):
            return call.args[pos]
        return None

    def calls_of(self, fn: Fn) -> list[Call]:
        """Every module-local call of `fn`: direct, and as a CALLBACK -- `_quiet(fn, root)` is taken to call `fn(root)` with the arguments after it."""
        out: list[Call] = []
        for call in self.m.calls:
            if fn in self.call_targets(call.node, call.scope):
                out.append(call)
            for k, a in enumerate(call.node.args):
                if not isinstance(a, ast.Name):
                    continue
                if any(b.kind == "fn" and b.fn is fn for b in self.lookup(a.id, call.scope) or []):
                    pseudo = ast.Call(
                        func=ast.Name(id=fn.name, ctx=ast.Load()),
                        args=call.node.args[k + 1 :],
                        keywords=call.node.keywords,
                    )
                    out.append(Call(pseudo, call.scope, call.guard, call.fn_path))
        return out

    def param_val(self, fn: Fn, index: int, dflt: ast.expr | None, dscope: Scope | None) -> Val:
        """A parameter's origin. Under a CONTEXT (one call pinned) it is that call's argument; otherwise it is combined over every call, and ANY tree argument makes it TREE (PLAN section 3.4 step 2) -- the join lattice's "temp wins" is for the components of ONE path, not for the alternatives of many calls."""
        pinned = self.ctx.get(fn.id)
        calls = [pinned] if pinned is not None else self.calls_of(fn)
        vals: list[Val] = []
        for call in calls:
            arg = self.arg_for(call.node, fn, index)
            if arg is None:
                vals.append(
                    self.ev(dflt, dscope) if dflt is not None and dscope is not None else NONE
                )
            else:
                vals.append(self.ev(arg, call.scope))
        if not vals:
            base = self.ev(dflt, dscope) if dflt is not None and dscope is not None else NONE
            return combine(UNRES, base)
        tree = [v for v in vals if final_origin(v) == "TREE" and v.o != "NONE"]
        if tree:
            return tree[0] if len(tree) == 1 else Val("TREE")
        out = combine_all(vals)
        return UNRES if out.o == "NONE" else out

    def ev(self, e: ast.expr, scope: Scope) -> Val:
        key = (id(e), scope.id)
        hit = self.memo.get(key)
        if hit is not None:
            return hit
        if key in self.busy:
            return NONE
        self.busy.add(key)
        v = self.ev0(e, scope)
        self.busy.discard(key)
        self.memo[key] = v
        return v

    def ev0(self, e: ast.expr, scope: Scope) -> Val:
        s = _const_str(e)
        if s is not None:
            return literal(s)
        if isinstance(e, ast.JoinedStr):
            return self.concat(e.values, scope)
        if isinstance(e, ast.FormattedValue):
            return self.ev(e.value, scope)
        if isinstance(e, ast.BinOp):
            if isinstance(e.op, ast.Div):
                return join_vals([self.ev(e.left, scope), self.ev(e.right, scope)])
            if isinstance(e.op, ast.Add):
                return self.concat([e.left, e.right], scope)
            return NONE
        if isinstance(e, ast.Name):
            return self.name_val(e.id, scope)
        if isinstance(e, ast.BoolOp):
            return combine_all(self.ev(v, scope) for v in e.values)
        if isinstance(e, ast.IfExp):
            return combine(self.ev(e.body, scope), self.ev(e.orelse, scope))
        if isinstance(e, ast.Attribute):
            return self.attr_val(e, scope)
        if isinstance(e, ast.Subscript):
            return self.subscript_val(e, scope)
        if isinstance(e, ast.Call):
            return self.call_val(e, scope)
        if isinstance(e, ast.Await):
            return self.ev(e.value, scope)
        if isinstance(e, ast.Starred):
            return self.ev(e.value, scope)
        return UNRES

    def name_val(self, name: str, scope: Scope) -> Val:
        if name == "__file__":
            return tree_at(self.m.file)
        bs = self.lookup(name, scope)
        if bs is None:
            return UNRES
        return combine_all(self.binding_val(b) for b in bs)

    def attr_val(self, e: ast.Attribute, scope: Scope) -> Val:
        if e.attr == "parent":
            return dirname_val(self.ev(e.value, scope))
        if e.attr in ("name", "stem", "suffix"):
            # `NamedTemporaryFile(...).name` is the full temp path; `Path.name` is a basename.
            obj = self.ev(e.value, scope)
            return obj if e.attr == "name" and obj.o in ("TEMP", "OUTSIDE") else Val("REL")
        if e.attr in self.m.self_attrs and not self.is_module(e.value, scope):
            # `self.temp`, and `sh.temp` on an instance of the same module's class: field-name sensitivity, module-wide.
            return combine_all(self.binding_val(b) for b in self.m.self_attrs[e.attr])
        canon = self.canonical(e, scope)
        if canon == "tempfile.tempdir":
            return TEMP
        if isinstance(e.value, ast.Name):
            b = self.import_of(e.value.id, scope)
            if b is not None and b.imported == "*" and b.source is not None:
                return self.import_val(b.source, e.attr, 0)
        return UNRES

    def subscript_val(self, e: ast.Subscript, scope: Scope) -> Val:
        base = (
            self.canonical(e.value, scope) if isinstance(e.value, (ast.Attribute, ast.Name)) else ""
        )
        if base == "os.environ":
            return ENV_SEEDS.get(_const_str(e.slice) or "", UNRES)
        table = self.dict_node(e.value, scope, 0)
        if table is not None:
            # A table of paths: `DIRS["client"]` is that value, `DIRS[k]` any of them.
            key = _const_str(e.slice)
            vals = [
                v
                for k, v in zip(table[0].keys, table[0].values, strict=True)
                if key is None or _const_str(k) == key
            ]
            if vals:
                return combine_all(self.ev(v, table[1]) for v in vals)
        if (
            isinstance(e.value, ast.Attribute)
            and e.value.attr == "parents"
            and isinstance(e.slice, ast.Constant)
            and isinstance(e.slice.value, int)
        ):
            v = self.ev(e.value.value, scope)
            for _ in range(e.slice.value + 1):
                v = dirname_val(v)
            return v
        return UNRES

    def concat(self, parts: list[ast.expr], scope: Scope) -> Val:
        lits = [_const_str(p) for p in parts]
        nodes = [p for p, s in zip(parts, lits, strict=True) if s is None]
        if not nodes:
            return literal("".join(s or "" for s in lits))
        out = combine_all(self.ev(n, scope) for n in nodes)
        first = next((s for s in lits if s != ""), None) if lits[0] is not None else None
        if first is not None and lits[0] is not None and lits[0] != "":
            out = combine(out, literal(lits[0]))
        if lits[0] is None and len(nodes) == 1 and treeish(out):
            base = self.ev(nodes[0], scope)
            tail = "".join(s or "" for s in lits[1:])
            if treeish(base) and base.rel is not None:
                return tree_at(posixpath.join(base.rel, tail.lstrip("/")))
        return Val(out.o) if out.o in ("TREE", "SCRATCH", "REL") else out

    def call_val(self, e: ast.Call, scope: Scope) -> Val:
        canon = self.canonical(e.func, scope)
        last = canon.rsplit(".", 1)[-1] if canon else ""
        args = [a for a in e.args if not isinstance(a, ast.Starred)]
        a0 = self.ev(args[0], scope) if args else NONE
        if canon in (
            "pathlib.Path",
            "pathlib.PurePath",
            "pathlib.PosixPath",
            "pathlib.PurePosixPath",
        ):
            return join_vals([self.ev(a, scope) for a in args]) if args else tree_at("")
        if canon in ("pathlib.Path.cwd", "os.getcwd"):
            return tree_at("")
        if canon == "pathlib.Path.home":
            return OUTSIDE
        if canon == "os.path.join":
            return join_vals([self.ev(a, scope) for a in args])
        if canon in ("os.path.abspath", "os.path.realpath"):
            return (
                tree_at(a0.rel)
                if a0.o == "REL" and a0.rel is not None
                else (Val("TREE") if a0.o == "REL" else a0)
            )
        if canon in ("os.path.normpath", "os.path.expanduser", "os.fspath", "str"):
            return a0
        if canon == "os.path.dirname":
            return dirname_val(a0)
        if canon in ("os.path.basename", "os.path.relpath"):
            return Val("REL")
        if canon == "os.path.expanduser":
            return OUTSIDE
        if canon.startswith("tempfile.") and last in TEMPFILE_FNS:
            d = _kw(e, "dir")
            if d is not None:
                v = self.ev(d, scope)
                return (
                    Val(v.o)
                    if treeish(v) or v.o == "REL"
                    else TEMP
                    if v.o in ("TEMP", "OUTSIDE")
                    else v
                )
            return TEMP
        if ("runtmp." in canon and last in RUNTMP_FNS) or canon in RUNTMP_FNS:
            return TEMP
        if canon in ("os.environ.get", "os.getenv"):
            seed = ENV_SEEDS.get(_const_str(args[0] if args else None) or "")
            return seed if seed is not None else self.env_default(e, scope)
        if last in ROOT_SEEDS:
            return self.root_seed(e, last, scope)
        if canon in (
            "sorted",
            "list",
            "reversed",
            "set",
            "tuple",
            "os.walk",
            "os.scandir",
            "os.listdir",
        ):
            return a0 if canon != "os.listdir" else Val("REL")
        if canon.startswith("subprocess.") and any(
            _const_str(n) == "--show-toplevel" for n in ast.walk(e)
        ):
            return tree_at("")
        func = e.func
        if isinstance(func, ast.Attribute) and not self.is_module(func.value, scope):
            obj = self.ev(func.value, scope)
            if func.attr == "joinpath":
                return join_vals([obj, *[self.ev(a, scope) for a in args]])
            if func.attr in ("glob", "rglob", "iterdir", "walk"):
                return Val(obj.o) if obj.o in ("TREE", "SCRATCH", "REL") else obj
            if func.attr in ("with_suffix", "with_name", "with_stem"):
                return Val(obj.o) if obj.o in ("TREE", "SCRATCH", "REL") else obj
            if func.attr in STRING_METHODS:
                return (
                    tree_at(obj.rel)
                    if func.attr in ("resolve", "absolute")
                    and obj.o == "REL"
                    and obj.rel is not None
                    else obj
                )
            if func.attr == "relative_to":
                return Val("REL")
        targets = self.call_targets(e, scope)
        if targets:
            out = combine_all(self.ev(r, s) for f in targets for r, s in f.returns)
            return UNRES if out.o == "NONE" else out
        # A helper from another module handed a temp root builds a temp path (`policy_path(name, tmp)`): the one cross-module inference, in the safe-for-temp direction only.
        if any(self.ev(a, scope).o == "TEMP" for a in [*args, *[k.value for k in e.keywords]]):
            return TEMP
        return UNRES

    def dict_node(self, e: ast.expr, scope: Scope, depth: int) -> tuple[ast.Dict, Scope] | None:
        """The dict literal an expression names: a name bound once to one, or the literal itself."""
        if depth > 3:
            return None
        if isinstance(e, ast.Dict):
            return e, scope
        if isinstance(e, ast.Name):
            bs = self.lookup(e.id, scope) or []
            if (
                len(bs) == 1
                and bs[0].kind == "expr"
                and bs[0].expr is not None
                and bs[0].scope is not None
            ):
                return self.dict_node(bs[0].expr, bs[0].scope, depth + 1)
        return None

    def env_default(self, e: ast.Call, scope: Scope) -> Val:
        dflt = e.args[1] if len(e.args) > 1 else None
        return combine(UNRES, self.ev(dflt, scope)) if dflt is not None else UNRES

    def root_seed(self, e: ast.Call, last: str, scope: Scope) -> Val:
        rel = ROOT_SEEDS[last]
        root_arg = _kw(e, "root")
        if last in ("ci_dir", "quality_dir", "hooks_stop_dir") and root_arg is None and e.args:
            root_arg = e.args[0]
        base = (
            combine(tree_at(""), self.ev(root_arg, scope)) if root_arg is not None else tree_at("")
        )
        if last == "find_repo_root":
            return tree_at("")
        if last == "from_root":
            return join_vals([base, *[self.ev(a, scope) for a in e.args]])
        return join_vals([base, Val("REL", rel)]) if rel else base

    # ---------------------------------------------------------- subprocess words

    def words(
        self, e: ast.expr | None, scope: Scope
    ) -> list[tuple[str | None, Callable[[Evaluator], Val]]]:
        """A command (list literal, a name bound once to one, or a string) as (literal text | None, value) words."""
        if e is None:
            return []
        if isinstance(e, ast.Name):
            bs = self.lookup(e.id, scope) or []
            if (
                len(bs) == 1
                and bs[0].kind == "expr"
                and bs[0].expr is not None
                and bs[0].scope is not None
            ):
                return self.words(bs[0].expr, bs[0].scope)
            return []
        if isinstance(e, (ast.List, ast.Tuple)):
            out: list[tuple[str | None, Callable[[Evaluator], Val]]] = []
            for x in e.elts:
                if isinstance(x, ast.Starred):
                    out.extend(self.words(x.value, scope))
                    continue
                s = _const_str(x)
                out.append((s, _val_of(x, scope)))
            return out
        if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
            return self.words(e.left, scope) + self.words(e.right, scope)
        s = _const_str(e)
        if s is not None:
            return [(w, _const_val(literal(w))) for w in s.split()]
        return []

    # ---------------------------------------------------------- guards

    def test_clauses(
        self, e: ast.expr | None, scope: Scope, depth: int = 0
    ) -> tuple[list[Clause], list[Clause]]:
        """The flag clauses under which a test is TRUE and FALSE. A clause holds when ANY flag in it is passed."""
        none: tuple[list[Clause], list[Clause]] = ([], [])
        if e is None or depth > 3:
            return none
        if isinstance(e, ast.UnaryOp) and isinstance(e.op, ast.Not):
            t, f = self.test_clauses(e.operand, scope, depth + 1)
            return f, t
        if isinstance(e, ast.Compare) and len(e.ops) == 1:
            op = e.ops[0]
            left = _const_str(e.left)
            right = _const_str(e.comparators[0])
            if isinstance(op, (ast.In, ast.NotIn)) and left and left.startswith("-"):
                pos, neg = [[left]], [["!" + left]]
                return (pos, neg) if isinstance(op, ast.In) else (neg, pos)
            flag = (
                left
                if left and left.startswith("--")
                else right
                if right and right.startswith("--")
                else None
            )
            if flag and isinstance(op, ast.Eq):
                return [[flag]], [["!" + flag]]
            if flag and isinstance(op, ast.NotEq):
                return [["!" + flag]], [[flag]]
            return none
        if isinstance(e, ast.BoolOp):
            parts = [self.test_clauses(v, scope, depth + 1) for v in e.values]
            if isinstance(e.op, ast.And):
                t = [c for p in parts for c in p[0]]
                f = (
                    [[x for p in parts for x in p[1][0]]]
                    if all(len(p[1]) == 1 for p in parts)
                    else []
                )
                return t, f
            t = [[x for p in parts for x in p[0][0]]] if all(len(p[0]) == 1 for p in parts) else []
            return t, [c for p in parts for c in p[1]]
        if isinstance(e, ast.Attribute) and e.attr in self.m.flags:
            flag = self.m.flags[e.attr]
            return [[flag]], [["!" + flag]]
        if (
            isinstance(e, ast.Call)
            and isinstance(e.func, ast.Name)
            and e.func.id == "bool"
            and e.args
        ):
            return self.test_clauses(e.args[0], scope, depth + 1)
        if isinstance(e, ast.Name):
            bs = self.lookup(e.id, scope) or []
            if len(bs) != 1:
                return none
            b = bs[0]
            if b.kind == "expr" and b.expr is not None and b.scope is not None:
                return self.test_clauses(b.expr, b.scope, depth + 1)
            if b.kind == "param" and b.fn is not None:
                return [["@param:%d:%d" % (b.fn.id, b.index)]], []
        return none

    def resolve_guard(self, guard: list[Clause]) -> list[Clause]:
        """`@param` placeholders resolved: gated when EVERY module-local call passes a flag-derived (or literal False) value."""
        out: list[Clause] = []
        for clause in guard:
            flags = self._resolve_clause(clause)
            if flags:
                out.append(sorted(set(flags)))
        return out

    def _resolve_clause(self, clause: Clause) -> list[str] | None:
        flags: list[str] = []
        for f in clause:
            m = re.match(r"^@param:(\d+):(\d+)$", f)
            if not m:
                flags.append(f)
                continue
            fn = next((x for x in self.m.fns if x.id == int(m.group(1))), None)
            idx = int(m.group(2))
            calls = [
                c
                for c in self.m.calls
                if fn is not None and fn in self.call_targets(c.node, c.scope)
            ]
            if fn is None or not calls:
                return None
            for c in calls:
                arg = self.arg_for(c.node, fn, idx)
                if arg is None:
                    dflt = fn.defaults.get(fn.params[idx]) if idx < len(fn.params) else None
                    if isinstance(dflt, ast.Constant) and dflt.value is False:
                        flags.append("<never>")
                        continue
                    return None
                if isinstance(arg, ast.Constant) and arg.value is False:
                    flags.append("<never>")
                    continue
                t, _f = self.test_clauses(arg, c.scope)
                if len(t) != 1:
                    return None
                flags.extend(t[0])
        return flags

    def fn_guard(self, fn_path: list[Fn], requested: set[str], visiting: set[int]) -> list[Clause]:
        """The clauses a function's REFERENCES impose on everything inside it.

        A function runs when ANY reference to it runs, and a reference runs when ALL its clauses hold, so the function's own guard is an OR of ANDs, turned back into clauses by distribution (bounded; past the bound it is taken as unguarded, the safe direction). TRANSITIVE: a reference inside another function carries that function's guard, so `main` gating `refresh()` gates what `refresh` calls. GROUP-AWARE: a top-level
        function another module in the group imports by name (`requested`) is reachable from outside and is not guarded by its module-local calls.
        """
        out: list[Clause] = []
        for fn in fn_path:
            out.extend(self._one_fn_guard(fn, requested, visiting))
        return out

    def _one_fn_guard(self, fn: Fn, requested: set[str], visiting: set[int]) -> list[Clause]:
        if fn.top_level and (fn.name in requested or "*" in requested):
            return []
        if not fn.ref_guards or fn.id in visiting:
            return []
        visiting = visiting | {fn.id}
        per_ref: list[list[Clause]] = []
        for guard, path in fn.ref_guards:
            clauses = self.resolve_guard(guard) + self.fn_guard(path, requested, visiting)
            if not clauses:
                return []
            per_ref.append(clauses)
        return distribute(per_ref)


def distribute(per_ref: list[list[Clause]], bound: int = 64) -> list[Clause]:
    """OR over references of (AND of clauses), as AND of clauses. Empty (unguarded) past `bound`."""
    out: list[Clause] = [[]]
    for clauses in per_ref:
        if len(out) * len(clauses) > bound:
            return []
        out = [sorted(set(a) | set(c)) for a in out for c in clauses]
    return [c for c in out if c]


def _val_of(x: ast.expr, scope: Scope) -> Callable[[Evaluator], Val]:
    return lambda v: v.ev(x, scope)


def _const_val(val: Val) -> Callable[[Evaluator], Val]:
    return lambda _v: val


# --------------------------------------------------------------------------- mutators


def mutator_targets(
    mt: dict,
    words0: list[tuple[str | None, Callable[[Evaluator], Val]]],
    cwd: Callable[[Evaluator], Val],
) -> list[tuple[str, Callable[[Evaluator], Val]]]:
    """The written words of a command, by the shared table. `cwd` is the directory it runs in."""
    words = list(words0)

    def text(i: int) -> str:
        return (words[i][0] or "") if 0 <= i < len(words) else ""

    if not words:
        return []
    prog = posixpath.basename(text(0))
    if prog in ("python3", "python", "node", "bash", "sh", "tsx") and len(words) > 1:
        return []
    if prog == "npx" and text(1) not in mt["install"].get("npx", []):
        words = words[1:]
        while words and (words[0][0] or "").startswith("-"):
            words = words[1:]
        prog = posixpath.basename(text(0))
    if not prog:
        return []
    rest = words[1:]
    rtext = [(w[0] or "") for w in rest]
    nonflag = [w for w in rest if w[0] is None or not w[0].startswith("-")]
    last = rest[-1] if rest else None
    if prog == "git":
        i = 0
        target = cwd
        while i < len(rest):
            t = rtext[i]
            if t == "-C" and i + 1 < len(rest):
                target = rest[i + 1][1]
                i += 2
            elif t == "-c":
                i += 2
            elif t.startswith("-"):
                i += 1
            else:
                break
        sub = rtext[i] if i < len(rest) else ""
        return [("git " + sub, target)] if sub in mt["git"]["subcommands"] else []
    if (
        prog in mt["in_place"]
        and any(re.match(r"^-[A-Za-z]*i", t) for t in rtext)
        and last is not None
    ):
        return [(prog, last[1])]
    if prog in mt["pair"] and len(nonflag) >= 2 and last is not None:
        return [(prog, last[1])]
    if prog in mt["list"]:
        return [(prog, w[1]) for w in nonflag]
    of = mt["output_flag"].get(prog)
    if of and rtext[:1] == [of["subcommand"]]:
        if of["flag"] in rtext:
            i = rtext.index(of["flag"])
            if i + 1 < len(rest):
                return [("%s %s" % (prog, of["subcommand"]), rest[i + 1][1])]
        return []
    if rtext[:1] and rtext[0] in mt["install"].get(prog, []):
        return [("%s %s" % (prog, rtext[0]), cwd)]
    wf = mt["write_flag"].get(prog)
    if wf and any(t.split("=")[0] in wf for t in rtext):
        return [(prog, cwd)]
    ex = mt["extract"].get(prog)
    if ex and any(not t.startswith("--") and re.match(r"^-?[A-Za-z]*x", t) for t in rtext):
        if ex["dest"] in rtext:
            i = rtext.index(ex["dest"])
            if i + 1 < len(rest):
                return [(prog, rest[i + 1][1])]
        return [(prog, cwd)]
    return []


def load_mutators(root: pathlib.Path, fallback: pathlib.Path) -> dict:
    path = root / MUTATORS_REL
    if not path.is_file():
        path = fallback / MUTATORS_REL
    return json.loads(path.read_text(encoding="utf-8"))
