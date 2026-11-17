"""Which pytest files a change can affect, and when that question has no safe answer.

WHAT THIS IS FOR (agent/plans/PLAN-ciquick-cpu.md, Fix B). `check:ci-pytest` ran the whole suite (36k tests, about 18k core-s) on every local ci:quick, the same as CI. The operator ruled that CI stays the full-suite backstop and the local run judges only what the change can reach. This module answers that question, and its main duty is the second half of its title: every
case where the answer could be wrong is a FULL run with the reason printed, never a smaller selection.

THE MAP (B1). `test file -> closure`: the test module, every module it imports, followed transitively, plus the `conftest.py` chain above it. Imports are read with `ast`, nothing is executed. Module names resolve against the pyproject `pythonpath` roots (today `.ci`, `.claude/hooks/stop`, `.claude`), the same rule quick-select's `resolvePy` uses for `rediacc_ci.*` widened to
every root pytest itself puts on sys.path, plus the importing file's own directory (scripts that insert their own directory, and pytest's rootdir insertion for a test directory without `__init__.py`). An import of a name no root holds is third-party or stdlib and is ignored; an import whose TOP name is a local module or package but whose full name resolves nowhere is UNRESOLVED.

DATA READS (B2). Tests also read files they never import: a guard they run as a subprocess, a JSON policy, a fixture. Two sources cover that:

  1. string literals in the test module and in the closure members that live under
     a test root (helpers like hookcases.py): a literal that is a changed file's
     path, a path suffix of it, its basename, its stem (6+ characters), a tracked
     directory above it, or a glob matching it, covers that file. Deliberately
     inclusive: a false cover selects one test file too many, a missed one is
     caught only by CI. Literals in shared library modules are NOT scanned:
     `paths.py` names half the tree, and every test importing it would cover it;
  2. the `reads` table in `.ci/policy/pytest-impact.json`, `{test glob: [path
     globs]}`, for reads no literal names (a directory listed by a computed glob).

SELECTION (B3): the smoke floor, every test file whose closure, literals or `reads` meet the change set since the last push, and every changed test file.

FULL, AND ONLY FULL, WHEN THE ANSWER IS UNKNOWN (B4). Each prints `pytest-impact: FULL (<reason>)`:

  * a pytest-config file changed: any `conftest.py`, `pyproject.toml`, `uv.lock`,
    `pytest.ini`, `setup.cfg`, `tox.ini`, check_pytest.py, this module, or the
    policy file;
  * an UNRESOLVED import in the closure of any test (a deleted module still
    imported is exactly this shape, and so is a closure this map cannot see);
  * a changed file under `.ci/` or `.claude/`, or any changed `.py`, that no
    closure, literal or `reads` entry covers;
  * the selection is above 40% of the test files (the narrowing buys little and
    the risk of a missed edge is not worth it);
  * the map cannot be built (git unreadable, a syntax error in a module), the
    policy is missing or malformed, a smoke file is missing, or no push base
    resolves.

Changed files outside `.ci/`, `.claude/` and `*.py` are not this module's question: check:ci-pytest's declared `paths` already exclude them, so the gate is not selected for them at all. They are listed, not judged.

    pytest_impact.py                 print the selection for the current change set
    pytest_impact.py --json          the same as one JSON object
    pytest_impact.py --base <ref>    diff against <ref>'s merge-base instead of the push base
    pytest_impact.py --write-smoke --junit <junit.xml>
                                     re-derive the smoke floor from measured durations
"""

from __future__ import annotations

import ast
import fnmatch
import hashlib
import json
import os
import pathlib
import sys
import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rediacc_ci import gitx, paths
from rediacc_ci.core import xml_trusted
from rediacc_ci.policy_paths import policy_rel

if TYPE_CHECKING:
    from collections.abc import Iterable

POLICY_RELPATH = policy_rel("pytest-impact.json")
CACHE_RELDIR = ".ci/cache/pytest-impact"
MAP_SCHEMA = 2
MAX_FRACTION = 0.40
# Top-level directories whose files the map judges. Bare names, matched on a path's first component, so no directory literal with a trailing slash sits here for the record-paths derivation to read as a root.
SCOPE_ROOTS = frozenset({".ci", ".claude"})


def _in_scope_dir(rel: str) -> bool:
    return rel.split("/", 1)[0] in SCOPE_ROOTS


FULL_BASENAMES = frozenset(
    {"conftest.py", "pyproject.toml", "uv.lock", "pytest.ini", "setup.cfg", "tox.ini"}
)
FULL_PATHS = frozenset(
    {".ci/rediacc_ci/check_pytest.py", ".ci/rediacc_ci/pytest_impact.py", POLICY_RELPATH}
)
# A stem shorter than this ("core", "log", "run") would cover a file from half the literals in the suite and turn every change into an over-40% FULL.
MIN_STEM = 6


def _stem_is_name(stem: str) -> bool:
    """A bare stem covers a file only when it is shaped like a name (`block_vm_unverified_push`, `ci-stop-elite`), never a plain word: `terminal` in a fixture list covered `.claude/skills/rdc/terminal.md` for every test in `.ci/rediacc_ci/tests`."""
    return len(stem) >= MIN_STEM and ("_" in stem or "-" in stem)


# Literals longer than this are prose or embedded fixtures, not names.
MAX_LITERAL = 300


# --------------------------------------------------------------------------- the map


def pythonpath_roots(root: pathlib.Path) -> list[str]:
    """`[tool.pytest.ini_options].pythonpath`, repo-relative, read rather than restated."""
    with (root / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    ini = cfg.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return [str(pathlib.PurePosixPath(p)) for p in ini.get("pythonpath", [])]


def testpath_roots(root: pathlib.Path) -> list[str]:
    with (root / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    ini = cfg.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return [str(pathlib.PurePosixPath(p)).rstrip("/") for p in ini.get("testpaths", [])]


def is_test_file(rel: str, test_roots: Iterable[str]) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if not (name.startswith("test_") and name.endswith(".py")):
        return False
    return any(rel.startswith(r + "/") for r in test_roots)


def module_index(py_files: Iterable[str], roots: Iterable[str]) -> dict[str, list[str]]:
    """Dotted module name -> the files that define it, under every root. A file can carry several names (`.claude/hooks/stop/wl_git.py` is `wl_git` under one root and `hooks.stop.wl_git` under another), and a name can map to several files across roots; both are kept, which over-counts a closure rather than missing an edge."""
    index: dict[str, list[str]] = {}
    roots = [r.rstrip("/") for r in roots]
    for rel in py_files:
        for r in roots:
            prefix = "" if r in ("", ".") else r + "/"
            if not rel.startswith(prefix):
                continue
            parts = rel[len(prefix) :][: -len(".py")].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            if not parts or not all(p.isidentifier() for p in parts):
                continue
            index.setdefault(".".join(parts), []).append(rel)
    return index


def _package_of(rel: str) -> list[str]:
    """The directory parts a relative import starts from."""
    return rel.split("/")[:-1]


@dataclass
class ModuleFacts:
    imports: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    syntax_error: str | None = None


def _dir_index(directory: str, all_py: frozenset[str]) -> dict[str, list[str]]:
    """Modules importable by bare name from one directory (a script's own sys.path[0])."""
    out: dict[str, list[str]] = {}
    prefix = directory + "/" if directory else ""
    for rel in all_py:
        if not rel.startswith(prefix):
            continue
        rest = rel[len(prefix) :]
        if "/" in rest:
            head, tail = rest.split("/", 1)
            if tail == "__init__.py" and head.isidentifier():
                out.setdefault(head, []).append(rel)
            continue
        stem = rest[: -len(".py")]
        if stem.isidentifier():
            out.setdefault(stem, []).append(rel)
    return out


def module_facts(
    rel: str,
    source: str,
    index: dict[str, list[str]],
    all_py: frozenset[str],
    *,
    want_literals: bool,
    local_tops: frozenset[str] | None = None,
    dir_indexes: dict[str, dict[str, list[str]]] | None = None,
) -> ModuleFacts:
    """What one module imports (as files), what it fails to import, and its string literals. `local_tops` and `dir_indexes` are caches a whole-map build passes in; a single call computes them."""
    facts = ModuleFacts()
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        facts.syntax_error = "%s:%s: %s" % (rel, exc.lineno, exc.msg)
        return facts
    if local_tops is None:
        local_tops = frozenset(name.split(".", 1)[0] for name in index)
    directory = "/".join(_package_of(rel))
    if dir_indexes is None:
        dir_indexes = {}
    own_dir = dir_indexes.get(directory)
    if own_dir is None:
        own_dir = dir_indexes[directory] = _dir_index(directory, all_py)
    hits: set[str] = set()

    def resolve_abs(mod: str) -> list[str] | None:
        parts = mod.split(".")
        found: list[str] = []
        whole = False
        for i in range(1, len(parts) + 1):
            name = ".".join(parts[:i])
            files = index.get(name)
            if files:
                found.extend(files)
                whole = i == len(parts)
        if not found and parts[0] in own_dir:
            found.extend(own_dir[parts[0]])
            whole = len(parts) == 1
            if not whole:
                sub = "/".join(_package_of(rel) + parts)
                for t in (sub + ".py", sub + "/__init__.py"):
                    if t in all_py:
                        found.append(t)
                        whole = True
        if found and whole:
            return found
        if parts[0] in local_tops or parts[0] in own_dir:
            return None
        return []

    def resolve_rel(level: int, mod: str | None) -> list[str] | None:
        base = _package_of(rel)
        for _ in range(level - 1):
            if not base:
                return None
            base = base[:-1]
        parts = base + (mod.split(".") if mod else [])
        found: list[str] = []
        for i in range(len(base), len(parts) + 1):
            stem = "/".join(parts[:i])
            found.extend(t for t in (stem + ".py", stem + "/__init__.py") if t in all_py)
        whole = "/".join(parts)
        if whole + ".py" in all_py or whole + "/__init__.py" in all_py:
            return found
        return None

    # Docstrings are prose about the code, not names the code reads. One walk: ast.walk is breadth-first, so a module, class or function is visited before its docstring constant and has recorded it by then.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
        if isinstance(node, ast.Import):
            for alias in node.names:
                got = resolve_abs(alias.name)
                if got is None:
                    facts.unresolved.append(alias.name)
                else:
                    hits.update(got)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                got = resolve_rel(node.level, node.module)
                label = "." * node.level + (node.module or "")
                if got is None:
                    facts.unresolved.append(label)
                    continue
                hits.update(got)
                for alias in node.names:
                    sub = resolve_rel(
                        node.level, ((node.module + ".") if node.module else "") + alias.name
                    )
                    if sub:
                        hits.update(sub)
            elif node.module:
                got = resolve_abs(node.module)
                if got is None:
                    facts.unresolved.append(node.module)
                    continue
                hits.update(got)
                # `from rediacc_ci.quality import foo` may name a MODULE foo, not a symbol.
                for alias in node.names:
                    sub = index.get(node.module + "." + alias.name)
                    if sub:
                        hits.update(sub)
        elif (
            isinstance(node, ast.Call)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")
                or (
                    isinstance(node.func, ast.Name)
                    and node.func.id in ("__import__", "import_module")
                )
            )
        ):
            got = resolve_abs(node.args[0].value)
            if got:
                hits.update(got)
        if (
            want_literals
            and isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            facts.literals.extend(literal_tokens(node.value))
    hits.discard(rel)
    facts.imports = sorted(hits)
    facts.literals = sorted(set(facts.literals))
    return facts


# Characters that wrap a path inside prose or a command line: quotes, backticks, brackets and trailing punctuation.
_WRAP_CHARS = "'\"`()[]{},;:<>"


def literal_tokens(text: str) -> list[str]:
    """The path-shaped words of one string constant. A constant is split on whitespace because a command line (`python3 .claude/hooks/stop/worklist.py --roundlog x`) names its script as one word among several, and a sentence in a docstring is harmless once split: its words are not paths and match nothing."""
    out = []
    for word in text.split():
        tok = word.strip(_WRAP_CHARS).rstrip(".")
        if 2 <= len(tok) <= MAX_LITERAL and any(ch in tok for ch in "/._-*"):
            out.append(tok)
    return out


def conftest_chain(rel: str, all_py: frozenset[str]) -> list[str]:
    parts = rel.split("/")[:-1]
    out = []
    for i in range(len(parts), -1, -1):
        cand = "/".join([*parts[:i], "conftest.py"])
        if cand in all_py:
            out.append(cand)
    return out


def build_map(
    root: pathlib.Path,
    py_files: list[str],
    roots: list[str],
    test_roots: list[str],
    read=None,
    facts_cache: dict | None = None,
) -> dict:
    """The whole map from file contents. `read(rel) -> str` is injectable so a test can build a map from a dict.

    `facts_cache` (`{rel: {sha, want, imports, unresolved, literals, error}}`) is read and updated in place: a module whose content hash and literal mode match its entry is not parsed again. Its caller keys the whole cache by the SET of Python files, because resolution depends on which modules exist; an edit keeps every other file's entry, an added or deleted module discards them all."""
    if read is None:

        def read(rel: str) -> str:
            return (root / rel).read_text(encoding="utf-8", errors="replace")

    all_py = frozenset(py_files)
    index = module_index(py_files, roots)
    facts: dict[str, ModuleFacts] = {}
    errors = []
    local_tops = frozenset(name.split(".", 1)[0] for name in index)
    dir_indexes: dict[str, dict[str, list[str]]] = {}

    def facts_of(rel: str) -> ModuleFacts:
        got = facts.get(rel)
        if got is None:
            in_tests = any(rel.startswith(r + "/") for r in test_roots)
            text = read(rel)
            sha = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
            hit = facts_cache.get(rel) if facts_cache is not None else None
            if hit and hit.get("sha") == sha and hit.get("want") == in_tests:
                got = ModuleFacts(
                    imports=list(hit["imports"]),
                    unresolved=list(hit["unresolved"]),
                    literals=list(hit["literals"]),
                    syntax_error=hit["error"],
                )
            else:
                got = module_facts(
                    rel,
                    text,
                    index,
                    all_py,
                    want_literals=in_tests,
                    local_tops=local_tops,
                    dir_indexes=dir_indexes,
                )
                if facts_cache is not None:
                    facts_cache[rel] = {
                        "sha": sha,
                        "want": in_tests,
                        "imports": got.imports,
                        "unresolved": got.unresolved,
                        "literals": got.literals,
                        "error": got.syntax_error,
                    }
            if got.syntax_error:
                errors.append(got.syntax_error)
            facts[rel] = got
        return got

    tests: dict[str, dict] = {}
    for test in sorted(p for p in py_files if is_test_file(p, test_roots)):
        closure: set[str] = set()
        queue = [test, *conftest_chain(test, all_py)]
        unresolved: set[str] = set()
        literals: set[str] = set()
        while queue:
            rel = queue.pop()
            if rel in closure:
                continue
            closure.add(rel)
            f = facts_of(rel)
            unresolved.update("%s: %s" % (rel, u) for u in f.unresolved)
            literals.update(f.literals)
            queue.extend(i for i in f.imports if i not in closure)
            # The conftest chain of every closure member under a test root is collected too.
            if any(rel.startswith(r + "/") for r in test_roots):
                queue.extend(c for c in conftest_chain(rel, all_py) if c not in closure)
        tests[test] = {
            "closure": sorted(closure),
            "unresolved": sorted(unresolved),
            "literals": sorted(literals),
        }
    return {"schema": MAP_SCHEMA, "tests": tests, "errors": sorted(set(errors))}


# --------------------------------------------------------------------------- reads and coverage


def _normal_literal(literal: str) -> str:
    lit = literal.strip()
    while lit.startswith("./"):
        lit = lit[2:]
    return lit


def _is_glob(lit: str) -> bool:
    return any(ch in lit for ch in "*?[")


def literal_covers(literal: str, rel: str, tracked_dirs: frozenset[str]) -> bool:
    """Whether one string literal names `rel` (a repo-relative path). Inclusive by design; see the module docstring. The reference form of `LiteralIndex.covers`, which a control holds equal to it."""
    lit = _normal_literal(literal)
    if not lit or lit in ("*", "**", "/", "."):
        return False
    base = rel.rsplit("/", 1)[-1]
    if _is_glob(lit):
        if "/" in lit:
            return fnmatch.fnmatchcase(rel, lit) or fnmatch.fnmatchcase(rel, "*/" + lit)
        # A bare-extension glob ("*.py", "*.json") names a kind of file, not a file.
        if lit.startswith("*.") and not _is_glob(lit[2:]):
            return False
        return fnmatch.fnmatchcase(base, lit)
    if lit == rel or rel.endswith("/" + lit):
        return True
    if "/" in lit:
        d = lit.rstrip("/")
        return d in tracked_dirs and rel.startswith(d + "/")
    stem = base.rsplit(".", 1)[0]
    return _stem_is_name(stem) and lit == stem


def broad_globs(
    literals: Iterable[str], files: Iterable[str], tracked_dirs: frozenset[str]
) -> frozenset[str]:
    """The glob literals that match more than MAX_DIR_FILES of `files`. Such a glob names a tree, not an input, for the same reason a broad directory does: `***`, `*?` and `*[!0-9]*` appear as literals in the suite and matched every path, so they covered every change and the uncovered FULL could never fire (a planted untracked file under .ci/ came back IMPACT)."""
    files = list(files)
    out = set()
    seen = set()
    for raw in literals:
        lit = _normal_literal(raw)
        if not _is_glob(lit) or lit in seen:
            continue
        seen.add(lit)
        hits = 0
        for rel in files:
            if literal_covers(lit, rel, tracked_dirs):
                hits += 1
                if hits > MAX_DIR_FILES:
                    out.add(lit)
                    break
    return frozenset(out)


class LiteralIndex:
    """One test's literals, indexed so a file is checked by set lookups instead of a scan. Same verdict as `literal_covers` over every literal."""

    def __init__(self, literals: Iterable[str], broad: frozenset[str] = frozenset()):
        self.exact: set[str] = set()
        self.globs: list[str] = []
        for raw in literals:
            lit = _normal_literal(raw)
            if not lit or lit in ("*", "**", "/", "."):
                continue
            if _is_glob(lit):
                if lit not in broad:
                    self.globs.append(lit)
            else:
                self.exact.add(lit)
                if "/" in lit and lit.endswith("/"):
                    self.exact.add(lit.rstrip("/"))

    def covers(self, rel: str, tracked_dirs: frozenset[str]) -> bool:
        parts = rel.split("/")
        # Every path suffix: rel itself, "b/c", "c".
        for i in range(len(parts)):
            if "/".join(parts[i:]) in self.exact:
                return True
        # Every tracked directory above it, named in full.
        for i in range(2, len(parts)):
            d = "/".join(parts[:i])
            if d in tracked_dirs and d in self.exact:
                return True
        stem = parts[-1].rsplit(".", 1)[0]
        if _stem_is_name(stem) and stem in self.exact:
            return True
        return any(literal_covers(g, rel, tracked_dirs) for g in self.globs)


def reads_cover(reads: dict[str, list[str]], test: str, rel: str) -> bool:
    for test_glob, path_globs in reads.items():
        if fnmatch.fnmatchcase(test, test_glob) and any(
            fnmatch.fnmatchcase(rel, g) for g in path_globs
        ):
            return True
    return False


# A directory literal holding more files than this names a TREE, not an input. Such a directory, and every test root with its ancestors, is left out of `tracked_dirs`, so its literal covers nothing: `.ci/rediacc_ci/tests/__init__.py` names `.claude/rediacc_hooks/tests` and that one literal covered every file under it for all 911 test files. A file only such a literal would have covered falls through to the uncovered FULL, the safe side.
MAX_DIR_FILES = 200


def tracked_dirs_of(files: Iterable[str], test_roots: Iterable[str] = ()) -> frozenset[str]:
    """Every directory of two or more segments with at most MAX_DIR_FILES files below it, minus the test roots and their ancestors."""
    counts: dict[str, int] = {}
    for rel in files:
        parts = rel.split("/")[:-1]
        for i in range(2, len(parts) + 1):
            d = "/".join(parts[:i])
            counts[d] = counts.get(d, 0) + 1
    banned = set()
    for r in test_roots:
        parts = r.split("/")
        for i in range(1, len(parts) + 1):
            banned.add("/".join(parts[:i]))
    return frozenset(d for d, n in counts.items() if n <= MAX_DIR_FILES and d not in banned)


# --------------------------------------------------------------------------- selection


@dataclass
class Selection:
    scope: str  # "impact" or "full"
    reason: str
    files: list[str] = field(default_factory=list)
    total: int = 0
    smoke: int = 0
    digest: str = ""
    why: dict[str, str] = field(default_factory=dict)
    outside: list[str] = field(default_factory=list)

    def line(self) -> str:
        if self.scope == "full":
            return "pytest-impact: FULL (%s)" % self.reason
        return "pytest-impact: IMPACT %d of %d test file(s) (%d smoke), map %s" % (
            len(self.files),
            self.total,
            self.smoke,
            self.digest[:12],
        )

    def as_json(self) -> dict:
        return {
            "pytestScope": self.scope,
            "reason": self.reason,
            "selected": len(self.files) if self.scope == "impact" else self.total,
            "total": self.total,
            "smoke": self.smoke,
            "mapDigest": self.digest,
            "files": self.files,
            "why": self.why,
            "outside": self.outside,
        }


def full(reason: str, *, total: int = 0, digest: str = "") -> Selection:
    return Selection("full", reason, total=total, digest=digest)


def load_policy(text: str) -> tuple[dict | None, str | None]:
    """(policy, None) or (None, why it is unusable)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, "%s is not valid JSON: %s" % (POLICY_RELPATH, exc)
    if not isinstance(data, dict):
        return None, "%s is not an object" % POLICY_RELPATH
    smoke = data.get("smoke", {}).get("files") if isinstance(data.get("smoke"), dict) else None
    reads = data.get("reads")
    if not isinstance(smoke, list) or not smoke or not all(isinstance(s, str) for s in smoke):
        return None, "%s has no non-empty smoke.files list" % POLICY_RELPATH
    if not isinstance(reads, dict) or not all(
        isinstance(k, str) and isinstance(v, list) and all(isinstance(g, str) for g in v)
        for k, v in reads.items()
    ):
        return None, "%s has no {test glob: [path globs]} reads table" % POLICY_RELPATH
    return data, None


def select(
    changed: list[str] | None,
    impact_map: dict | None,
    policy: dict | None,
    *,
    existing: frozenset[str],
    test_roots: list[str],
    digest: str = "",
) -> Selection:
    """The pure decision. `changed` None means no push base resolved; `impact_map`/`policy` None mean they could not be built or read. `existing` is every tracked-or-untracked path present on disk."""
    if impact_map is None:
        return full("missing map", digest=digest)
    tests = impact_map["tests"]
    total = len(tests)
    if total == 0:
        return full("the map holds no test files", digest=digest)
    if impact_map.get("errors"):
        return full(
            "the map could not parse %s" % impact_map["errors"][0], total=total, digest=digest
        )
    if policy is None:
        return full("missing or malformed %s" % POLICY_RELPATH, total=total, digest=digest)
    if changed is None:
        return full(
            "no push base resolved, so the change set is unknown", total=total, digest=digest
        )
    smoke = list(policy["smoke"]["files"])
    missing_smoke = [s for s in smoke if s not in tests]
    if missing_smoke:
        return full(
            "smoke floor names %s, which is not a test file in the tree" % missing_smoke[0],
            total=total,
            digest=digest,
        )
    for rel in changed:
        if rel.rsplit("/", 1)[-1] in FULL_BASENAMES or rel in FULL_PATHS:
            return full("%s changed" % rel, total=total, digest=digest)
    for test, entry in tests.items():
        if entry["unresolved"]:
            return full(
                "unresolved import in the closure of %s (%s)" % (test, entry["unresolved"][0]),
                total=total,
                digest=digest,
            )
    reads = policy["reads"]
    tracked_dirs = tracked_dirs_of(existing, test_roots)
    in_scope_files = [p for p in existing if _in_scope_dir(p) or p.endswith(".py")]
    # Only a glob that covers some changed file can matter, so only those are measured against the tree: measuring every glob literal in the suite took 31 s on the real tree.
    judged = [rel for rel in changed if _in_scope_dir(rel) or rel.endswith(".py")]
    relevant = {
        lit
        for entry in tests.values()
        for lit in entry["literals"]
        if _is_glob(_normal_literal(lit))
        and any(literal_covers(lit, rel, tracked_dirs) for rel in judged)
    }
    broad = broad_globs(relevant, in_scope_files, tracked_dirs)
    indexes = {test: LiteralIndex(entry["literals"], broad) for test, entry in tests.items()}
    closures = {test: frozenset(entry["closure"]) for test, entry in tests.items()}
    selected: dict[str, str] = dict.fromkeys(smoke, "smoke")
    outside = []
    for rel in changed:
        if is_test_file(rel, test_roots):
            if rel in tests:
                selected.setdefault(rel, "changed test")
            continue
        in_scope = _in_scope_dir(rel) or rel.endswith(".py")
        if not in_scope:
            outside.append(rel)
            continue
        hit = False
        for test in tests:
            why = None
            if rel in closures[test]:
                why = "imports %s" % rel
            elif reads_cover(reads, test, rel):
                why = "reads %s (policy)" % rel
            elif indexes[test].covers(rel, tracked_dirs):
                why = "names %s" % rel
            if why:
                hit = True
                if selected.get(test) in (None, "smoke"):
                    selected[test] = why
        if not hit:
            return full(
                "%s changed and no test imports it, names it, or lists it in reads" % rel,
                total=total,
                digest=digest,
            )
    if len(selected) > MAX_FRACTION * total:
        return full(
            "%d of %d test files selected, above %d%%" % (len(selected), total, MAX_FRACTION * 100),
            total=total,
            digest=digest,
        )
    files = sorted(selected)
    return Selection(
        "impact",
        "%d changed file(s)" % len(changed),
        files=files,
        total=total,
        smoke=len(smoke),
        digest=digest,
        why={f: selected[f] for f in files},
        outside=outside,
    )


# --------------------------------------------------------------------------- the smoke floor

# A smoke file's slowest test must finish under this, so the floor stays a floor and not a second suite.
SMOKE_PER_TEST_MAX_S = 1.0
SMOKE_UNIT_ROOTS = (".ci/rediacc_ci", ".claude/rediacc_hooks")
SMOKE_FLAT_UNITS = (".claude/hooks/stop",)


def unit_of(rel: str, test_roots: Iterable[str]) -> str | None:
    """The top-level package (or flat module directory) a non-test file belongs to; None for a test-root file or one outside the unit roots."""
    if any(rel.startswith(r + "/") for r in test_roots):
        return None
    for flat in SMOKE_FLAT_UNITS:
        if rel.startswith(flat + "/") and "/" not in rel[len(flat) + 1 :]:
            return flat
    for r in SMOKE_UNIT_ROOTS:
        if rel.startswith(r + "/"):
            head = rel[len(r) + 1 :].split("/", 1)[0]
            if head == "__init__.py":
                return None
            return r + "/" + (head.removesuffix(".py"))
    return None


def junit_file_times(
    junit_text: str, test_files: Iterable[str]
) -> dict[str, tuple[int, float, float]]:
    """`{test file: (tests, total s, slowest s)}` from a junit report. A classname is the dotted path (`.ci.rediacc_ci.tests.test_x`, a class name possibly appended); the longest prefix naming a known test file wins."""
    by_dotted = {f[: -len(".py")].replace("/", "."): f for f in test_files}
    out: dict[str, list[float]] = {}
    for tc in xml_trusted.fromstring(junit_text).iter("testcase"):
        parts = (tc.get("classname") or "").split(".")
        hit = None
        for i in range(len(parts), 0, -1):
            hit = by_dotted.get(".".join(parts[:i]))
            if hit:
                break
        if hit is None:
            continue
        out.setdefault(hit, []).append(float(tc.get("time") or 0.0))
    return {f: (len(v), sum(v), max(v)) for f, v in out.items()}


def derive_smoke(
    impact_map: dict, times: dict[str, tuple[int, float, float]], test_roots: list[str]
) -> tuple[list[str], list[str]]:
    """(smoke files, units no fast file reaches). A greedy set cover over top-level units, most new units per test-second first, drawing only on files whose slowest test is under SMOKE_PER_TEST_MAX_S."""
    reach: dict[str, set[str]] = {}
    universe: set[str] = set()
    for test, entry in impact_map["tests"].items():
        units = {u for u in (unit_of(c, test_roots) for c in entry["closure"]) if u}
        universe |= units
        if test in times and times[test][2] < SMOKE_PER_TEST_MAX_S:
            reach[test] = units
    covered: set[str] = set()
    chosen: list[str] = []
    while True:
        best, best_score = None, 0.0
        for test in sorted(reach):
            new = len(reach[test] - covered)
            if not new:
                continue
            score = new / max(times[test][1], 0.05)
            if score > best_score:
                best, best_score = test, score
        if best is None:
            break
        chosen.append(best)
        covered |= reach[best]
    return sorted(chosen), sorted(universe - covered)


# --------------------------------------------------------------------------- the real tree


def _git_lines(root: pathlib.Path, args: list[str]) -> list[str] | None:
    res = gitx.git(args, root=root)
    if res.returncode != 0:
        return None
    return [ln for ln in res.stdout.split("\0" if "-z" in args else "\n") if ln]


def present_files(root: pathlib.Path) -> list[str] | None:
    listed = _git_lines(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    if listed is None:
        return None
    return sorted({p for p in listed if (root / p).is_file()})


def branch_of_ref(name: str) -> str:
    for prefix in ("refs/remotes/origin/", "origin/", "refs/heads/"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def resolve_push_base(git, branch: str | None) -> str | None:
    """The merge-base quick-select's `resolvePushBase` returns, in the same order: `@{push}`, `origin/<branch>`, `@{upstream}`, `origin/main`, skipping a tracking ref that names another branch. `git(args) -> str | None`."""
    named = bool(branch)
    foreign = set()
    for ref in ("@{push}", "@{upstream}"):
        if git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"]) is None:
            continue
        name = git(["rev-parse", "--abbrev-ref", ref]) or ref
        if not (named and branch_of_ref(name) == branch):
            foreign.add(ref)
    candidates = [
        "@{push}",
        *([f"origin/{branch}"] if branch else []),
        "@{upstream}",
        "origin/main",
    ]
    for ref in candidates:
        if ref in foreign:
            continue
        if git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"]) is None:
            continue
        mb = git(["merge-base", "HEAD", ref])
        if mb:
            return mb
    return None


def change_set(root: pathlib.Path, base: str | None = None) -> list[str] | None:
    """Files changed since the last push (or since `base`'s merge-base), uncommitted edits and untracked files included. None when no base resolves; a `base` that does not resolve is None too, never a silent fall back to the push base."""

    def git(args: list[str]) -> str | None:
        res = gitx.git(args, root=root)
        return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else None

    mb = git(["merge-base", "HEAD", base]) if base else resolve_push_base(git, gitx.branch(root))
    if not mb:
        return None
    diffed = _git_lines(root, ["diff", "-z", "--name-only", "--no-renames", mb])
    untracked = _git_lines(root, ["ls-files", "-z", "--others", "--exclude-standard"])
    if diffed is None or untracked is None:
        return None
    return sorted(set(diffed) | set(untracked))


def content_digest(root: pathlib.Path, files: list[str], extra: bytes = b"") -> str:
    h = hashlib.sha256()
    h.update(b"pytest-impact-map-%d\0" % MAP_SCHEMA)
    h.update(extra)
    for rel in files:
        h.update(rel.encode() + b"\0")
        h.update(hashlib.sha256((root / rel).read_bytes()).digest())
    return h.hexdigest()


def load_or_build_map(root: pathlib.Path, present: list[str]) -> tuple[dict, str]:
    """The map for this tree's Python content, from the cache when its digest matches."""
    py_files = [p for p in present if p.endswith(".py")]
    roots = pythonpath_roots(root)
    test_roots = testpath_roots(root)
    pyproject = (root / "pyproject.toml").read_bytes()
    digest = content_digest(root, py_files, extra=hashlib.sha256(pyproject).digest())
    # Literal joins, so check:ci-gate-tree-writes resolves every write here to the `.ci/cache` scratch root. ONE map file, overwritten: the digest inside says which tree it describes, so nothing accumulates and nothing is pruned.
    cache_dir = root / ".ci" / "cache" / "pytest-impact"
    cached = root / ".ci" / "cache" / "pytest-impact" / "map.json"
    try:
        data = json.loads(cached.read_text(encoding="utf-8"))
        if data.get("schema") == MAP_SCHEMA and data.get("digest") == digest:
            return data, digest
    except (OSError, ValueError):
        pass
    # The per-module facts survive an edit; the file SET (and the pythonpath that resolves it) keys them all.
    fileset = hashlib.sha256(
        ("%d\n%s\n%s" % (MAP_SCHEMA, "\n".join(roots), "\n".join(py_files))).encode()
    ).hexdigest()
    facts_path = root / ".ci" / "cache" / "pytest-impact" / "facts.json"
    try:
        stored = json.loads(facts_path.read_text(encoding="utf-8"))
        facts_cache = stored["entries"] if stored.get("fileset") == fileset else {}
    except (OSError, ValueError, KeyError, TypeError):
        facts_cache = {}
    data = build_map(root, py_files, roots, test_roots, facts_cache=facts_cache)
    data["digest"] = digest
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".tmp%d" % os.getpid())
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    tmp.replace(cached)
    live = set(py_files)
    tmp = facts_path.with_suffix(".tmp%d" % os.getpid())
    tmp.write_text(
        json.dumps(
            {"fileset": fileset, "entries": {k: v for k, v in facts_cache.items() if k in live}},
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    tmp.replace(facts_path)
    return data, digest


def select_for_tree(root: pathlib.Path, base: str | None = None) -> Selection:
    """Every input read from the real tree; any failure to read one is a FULL with its reason."""
    present = present_files(root)
    if present is None:
        return full("git ls-files failed, so the tree is unreadable")
    try:
        impact_map, digest = load_or_build_map(root, present)
    except (OSError, ValueError) as exc:
        return full("missing map: %s" % exc)
    try:
        policy, problem = load_policy((root / POLICY_RELPATH).read_text(encoding="utf-8"))
    except OSError as exc:
        policy, problem = None, str(exc)
    if problem:
        return full(problem, total=len(impact_map["tests"]), digest=digest)
    policy_digest = hashlib.sha256((root / POLICY_RELPATH).read_bytes()).hexdigest()
    digest = hashlib.sha256((digest + policy_digest).encode()).hexdigest()
    return select(
        change_set(root, base),
        impact_map,
        policy,
        existing=frozenset(present),
        test_roots=testpath_roots(root),
        digest=digest,
    )


def write_smoke(root: pathlib.Path, junit: pathlib.Path) -> int:
    """Rewrite `smoke` in the policy from a junit report, keeping `reads` as it is."""
    present = present_files(root)
    if present is None:
        print("git ls-files failed", file=sys.stderr)
        return 1
    impact_map, _ = load_or_build_map(root, present)
    times = junit_file_times(junit.read_text(encoding="utf-8"), impact_map["tests"])
    if not times:
        print(
            "%s names none of the %d test files; refusing to write an empty floor"
            % (junit, len(impact_map["tests"])),
            file=sys.stderr,
        )
        return 1
    files, unreached = derive_smoke(impact_map, times, testpath_roots(root))
    if not files:
        print("no test file is fast enough to seed the smoke floor", file=sys.stderr)
        return 1
    policy_path = root / POLICY_RELPATH
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        policy = {}
    tests_n = sum(times[f][0] for f in files)
    secs = sum(times[f][1] for f in files)
    policy["smoke"] = {
        "derivedBy": "PYTHONPATH=.ci python3 -m rediacc_ci.pytest_impact --write-smoke --junit <junit.xml>",
        "tests": tests_n,
        "seconds": round(secs, 1),
        "unreached": unreached,
        "files": files,
    }
    policy.setdefault("reads", {})
    policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    print(
        "smoke floor: %d file(s), %d test(s), %.1f test-s, %d unit(s) no fast file reaches%s"
        % (
            len(files),
            tests_n,
            secs,
            len(unreached),
            (": " + ", ".join(unreached)) if unreached else "",
        )
    )
    return 0


def main(argv: list[str]) -> int:
    root = paths.repo_root()
    if "--write-smoke" in argv:
        if "--junit" not in argv or argv.index("--junit") + 1 >= len(argv):
            print("--write-smoke needs --junit <junit.xml>", file=sys.stderr)
            return 2
        return write_smoke(root, pathlib.Path(argv[argv.index("--junit") + 1]))
    base = None
    if "--base" in argv:
        i = argv.index("--base")
        if i + 1 >= len(argv):
            print("--base needs a ref", file=sys.stderr)
            return 2
        base = argv[i + 1]
    sel = select_for_tree(root, base)
    if "--json" in argv:
        print(json.dumps(sel.as_json(), indent=1))
        return 0
    print(sel.line())
    for f in sel.files:
        print("  %s  (%s)" % (f, sel.why.get(f, "")))
    if sel.outside:
        print("  outside check:ci-pytest's paths, not judged: %s" % ", ".join(sel.outside[:10]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
