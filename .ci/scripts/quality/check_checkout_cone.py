#!/usr/bin/env python3
"""check:ci-checkout-cone -- a step may not run a file its job never checked out.

WHY THIS EXISTS, and it cost a CI cycle on 2026-09-03. `Stripe Sandbox` failed with

    .ci/scripts/ci/shadow-compare.sh: No such file or directory

The compare logic used to be 18 inline lines and needed no file on disk. Extracting it to a script -- which check:ci-workflows was right to demand -- silently broke every job whose sparse-checkout cone stopped at `.ci/config`. Three jobs were affected and nothing in the tree could see it: the cone was well-formed, the script existed, the step was correctly written. Each fact was
true and the combination was not.

THAT IS THE CLASS. Existing gates check that a cone is well-formed and that a script exists; none corroborates the static claim ("this job checks out X") against what the job actually RUNS. This one does, and it generalises past shadow-compare to every repo-relative path any `run:` step invokes.

WHAT IT DELIBERATELY DOES NOT DO. It resolves only paths that look like a script INVOCATION at the start of a command or after a pipe/`&&` -- not every string that happens to look like a path. A mention inside an echo, a heredoc, or an argument is not an invocation, and flagging those would produce the kind of noise that gets a gate suppressed. Under-reporting is the safe direction
here: a missed path fails loudly in CI with the exact message above, while a false positive blocks a correct workflow.

THE IMPORT EDGE, added 2026-10-03 after it cost a PR run and a release. Run 37117682295's PR Labels job ran `PYTHONPATH=.ci python3 -m rediacc_ci.review.review_table` and died with `RegistryError: .ci/config/well-known.env is missing`: review_table imports rediacc_ci.well_known, which reads that file AT IMPORT, and the cone was `.ci/rediacc_ci`, `.github/actions`, `agent/reviews`. This gate passed before and after the fix because it never looked past the first token of a `python3 -m` line. The same chain broke the edge smoke and stable verify jobs the same morning (hotfix ca2dabca9). So a `python3 -m rediacc_ci.<mod>` step, and a `python3 <script>.py` step, is now followed STATICALLY (AST, nothing is imported or run) through every `rediacc_ci` import it reaches, transitively, and the step needs: each module file on that chain, each parent package's `__init__.py`, and every data file a module on the chain reads at import time.

WHICH DATA FILES, DERIVED RATHER THAN DECLARED. A module "reads at import" when code that runs at import (module and class bodies, decorators, defaults; not function bodies, not the `__main__` block) reaches a file-read sink (`open`, `.read_text`, `.glob`, `.exists`, ...) directly, through a function of the same module, or through an imported `rediacc_ci` function. Its data paths are the string literals in it that name a real non-Python file in this tree (well_known's `REGISTRY_REL`). A module that reads at import but names no such literal is UNKNOWN, and unknown fails: the fix is to name the path as a module-level constant. Measured 2026-10-03 by importing every non-test module under an audit hook: exactly one module opens a repo file at import, rediacc_ci.well_known, and the static detector agrees (its control below fails if it ever stops seeing it).

Exit 1 on any uncovered invocation, 2 on a failed control.

---- gate ----
kind: step
step: Checkout cone covers what steps run
lane: quality-static
needs-not: node
blocker: BLOCKER: this gate is pure Python and never runs node. `inferredNeeds`
     reads string literals, and the only npx/tsx/node text here is the REGEX
     that DETECTS interpreter invocations in workflow files (INVOKE) plus the
     selftest's INTERPRETER case that exercises it. Measured 2026-09-07:
     without this line the binder refuses with "lane quality-static does not
     provide all of [node, python-yaml]", which is how this file came to be the
     only one of 49 Python gates in this tree with no header at all. Tightening
     the inference instead was REJECTED on measurement: 24 files would lose it
     and at least one, test_gate_policy_path.py, really does execute
     node_modules/.bin/tsx.
why: A step may not run a file its job never checked out.
---- end gate ----
"""

from __future__ import annotations

import ast
import pathlib
import re
import shutil
import sys
import tempfile
from collections import deque

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"
MIN_JOBS = 60
# 251 `python3 -m rediacc_ci.*` sites existed on 2026-10-03. A floor far below that still catches the matcher going blind (a regex edit, a PYTHONPATH spelling change) without churning on every step added or removed.
MIN_PY_STEPS = 100
PKG = "rediacc_ci"

# A path at the start of a command, or right after a pipe / && / ; / `then`.
INVOKE = re.compile(
    # INTERPRETERS COUNT, and leaving them out was a hole in this gate's first version: `python3 .ci/scripts/x.py` is every bit an invocation as `./x.sh`, and 3 of the repo's shadow-carrying steps invoke a checker exactly that way. A cone gate that only sees shell scripts is anchored to the paths its author expected rather than to the invocation sites that exist.
    r"(?:^|\||&&|;|\bthen\b|\bdo\b|\bexec\b|\bbash\b|\bsh\b|\bsudo\b"
    r"|\bpython3?\b|\bnode\b|\bnpx\b|\btsx\b|\bgo\s+run\b|\bruby\b)\s*"
    r"((?:\./)?(?:\.ci|scripts|\.github)/[\w./-]+\.(?:sh|py|cjs|mjs|js|ts))",
    re.MULTILINE,
)
# `[PYTHONPATH=<dir>] python3 [-P -u ...] -m <module>`. The PYTHONPATH group says WHERE the package is imported from: only `.ci` (the job's own root checkout) is followed; anything else (claude-review imports a second checkout under `path:`) is counted and named as not followed.
PY_MODULE = re.compile(
    r"(?:\bPYTHONPATH=(\"[^\"]*\"|'[^']*'|\S+)\s+)?"
    r"\bpython3?(?:\s+-[A-Za-z]+)*\s+-m\s+(" + PKG + r"(?:\.\w+)*)(?![\w.])"
)
PKG_ROOT_PYTHONPATHS = {".ci", "./.ci", "$GITHUB_WORKSPACE/.ci", "${GITHUB_WORKSPACE}/.ci"}

# Calls that RAISE when the path is absent, which is the crash this class produces (`RegistryError`, `FileNotFoundError` at import). Existence probes (`exists`, `is_dir`, `stat`) and `glob`/`walk` are deliberately NOT sinks: on a missing path they return False or nothing rather than raising, and counting them flagged paths.repo_root(), whose only probe is an `is_dir()` on an `$REDIACC_CI_ROOT` override, as a data reader. Measured 2026-10-03: with them in, 3 of 4 hits were false; without them, the static set equals the audit-hook set.
READ_ATTRS = frozenset({"read_text", "read_bytes", "open", "iterdir", "listdir", "scandir"})
READ_NAMES = frozenset({"open"})


# ---------------------------------------------------------------------------
# the cone
# ---------------------------------------------------------------------------


def cone_of(job: dict) -> list[list[str] | None]:
    """The cone in effect after each step, in order. None means a FULL checkout.

    A checkout with a `path:` other than the workspace root puts its files somewhere ELSE, so it does not widen the root cone. Counting it did, and that was a false-cover hole: a sparse `.ci` under `path: other` made `.ci/...` look present at the root.
    """
    out: list[list[str] | None] = []
    cur: list[str] | None = []  # nothing checked out yet
    for st in job.get("steps") or []:
        if isinstance(st, dict) and "actions/checkout@" in (st.get("uses") or ""):
            w = st.get("with") or {}
            if str(w.get("path") or ".").strip().rstrip("/") in ("", "."):
                sc = w.get("sparse-checkout")
                if sc is None:
                    cur = None  # full checkout: everything is present
                else:
                    add = [
                        ln.strip()
                        for ln in str(sc).splitlines()
                        if ln.strip() and not ln.strip().startswith("#")
                    ]
                    cur = None if cur is None else sorted(set(cur) | set(add))
        out.append(cur)
    return out


def covered(path: str, cone: list[str] | None) -> bool:
    if cone is None:
        return True
    # removeprefix, NOT lstrip: lstrip takes a CHARACTER SET, so ".ci/scripts/x.sh".lstrip("./") is "ci/scripts/x.sh" -- the leading dot is eaten and every cone comparison then fails. This gate's own control caught
    # it on the first run, which is the entire argument for writing controls first;
    # the same mistake in a resolver that reports LESS would have been silent.
    p = path.removeprefix("./")
    return any(p == c or p.startswith(c.rstrip("/") + "/") for c in cone)


# ---------------------------------------------------------------------------
# the import graph (static: nothing here imports or runs the code it reads)
# ---------------------------------------------------------------------------


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _is_main_guard(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in test.comparators)
    )


class PyIndex:
    """The `rediacc_ci` package under `<root>/.ci`, read as source.

    `root` is a parameter so the selftest can point it at a fixture tree; the gate points it at the real one.
    """

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.base = root / ".ci"
        self._trees: dict[str, ast.Module | None] = {}
        self._imports: dict[str, list[str]] = {}
        self._reads: dict[str, list[tuple[int, str]]] = {}

    # -- names and files --------------------------------------------------
    def file_of(self, mod: str) -> str | None:
        """Repo-relative source file of `mod`, or None if no such module exists."""
        rel = pathlib.Path(*mod.split("."))
        for cand in (rel.with_suffix(".py"), rel / "__init__.py"):
            if (self.base / cand).is_file():
                return (pathlib.Path(".ci") / cand).as_posix()
        return None

    def is_package(self, mod: str) -> bool:
        f = self.file_of(mod)
        return bool(f and f.endswith("/__init__.py"))

    def tree(self, mod: str) -> ast.Module | None:
        if mod not in self._trees:
            f = self.file_of(mod)
            try:
                self._trees[mod] = (
                    ast.parse((self.root / f).read_text(encoding="utf-8")) if f else None
                )
            except (OSError, SyntaxError, ValueError):
                self._trees[mod] = None
        return self._trees[mod]

    # -- edges ------------------------------------------------------------
    def _resolve_from(self, mod: str, node: ast.ImportFrom) -> list[str]:
        if node.level:
            pkg = mod if self.is_package(mod) else mod.rpartition(".")[0]
            parts = pkg.split(".")
            if node.level - 1 > len(parts):
                return []
            parts = parts[: len(parts) - (node.level - 1)]
            base = ".".join(parts + ([node.module] if node.module else []))
        else:
            base = node.module or ""
        if base != PKG and not base.startswith(PKG + "."):
            return []
        out = [base] if self.file_of(base) else []
        for a in node.names:
            sub = "%s.%s" % (base, a.name)
            if a.name != "*" and self.file_of(sub):
                out.append(sub)  # `from pkg import submodule`
        return out

    @staticmethod
    def _walk_skipping_type_checking(tree: ast.AST):
        stack = [tree]
        while stack:
            n = stack.pop()
            yield n
            for c in ast.iter_child_nodes(n):
                if isinstance(c, ast.If) and _is_type_checking(c.test):
                    stack.extend(c.orelse)  # the `else:` of `if TYPE_CHECKING` does run
                    continue
                stack.append(c)

    def imports(self, mod: str) -> list[str]:
        """Every `rediacc_ci` module `mod` imports, ANYWHERE in the file (a function-level import runs when the entry point's main() reaches it, which for a `-m` step is the point), except under `if TYPE_CHECKING:`. Importing `a.b.c` also runs `a/__init__` and `a/b/__init__`, so parents are edges too."""
        if mod in self._imports:
            return self._imports[mod]
        found: list[str] = []
        t = self.tree(mod)
        if t is not None:
            for n in self._walk_skipping_type_checking(t):
                if isinstance(n, ast.Import):
                    found.extend(
                        a.name
                        for a in n.names
                        if (a.name == PKG or a.name.startswith(PKG + ".")) and self.file_of(a.name)
                    )
                elif isinstance(n, ast.ImportFrom):
                    found.extend(self._resolve_from(mod, n))
        parts = mod.split(".")
        found.extend(".".join(parts[:i]) for i in range(1, len(parts)))
        out = sorted({m for m in found if m != mod and self.file_of(m)})
        self._imports[mod] = out
        return out

    def closure(self, entries: list[str]) -> dict[str, str | None]:
        """module -> the module that first imported it (None for an entry). BFS, so a chain read back through it is a SHORTEST chain."""
        parent: dict[str, str | None] = {}
        q: deque[str] = deque()
        for e in entries:
            if e not in parent and self.file_of(e):
                parent[e] = None
                q.append(e)
        while q:
            m = q.popleft()
            for d in self.imports(m):
                if d not in parent:
                    parent[d] = m
                    q.append(d)
        return parent

    @staticmethod
    def chain(parent: dict[str, str | None], mod: str) -> list[str]:
        out = [mod]
        while parent.get(out[-1]) is not None:
            out.append(parent[out[-1]])  # type: ignore[arg-type]
        return out[::-1]

    # -- import-time reads -------------------------------------------------
    def _defs(self, mod: str) -> dict[str, ast.AST]:
        t = self.tree(mod)
        out: dict[str, ast.AST] = {}
        for n in t.body if t else []:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out[n.name] = n
        return out

    def _bindings(self, mod: str) -> dict[str, tuple[str, str | None]]:
        """local name -> (rediacc_ci module, attribute or None for the module itself)."""
        t = self.tree(mod)
        out: dict[str, tuple[str, str | None]] = {}
        for n in t.body if t else []:
            if isinstance(n, ast.Import):
                for a in n.names:
                    if a.name.startswith(PKG) and self.file_of(a.name):
                        out[a.asname or a.name.split(".")[0]] = (
                            (a.name, None) if a.asname else (a.name.split(".")[0], None)
                        )
            elif isinstance(n, ast.ImportFrom):
                mods = self._resolve_from(mod, n)
                if not mods:
                    continue
                base = mods[0] if self.file_of(mods[0]) else None
                for a in n.names:
                    sub = "%s.%s" % (base, a.name) if base else None
                    if sub and self.file_of(sub):
                        out[a.asname or a.name] = (sub, None)
                    elif base:
                        out[a.asname or a.name] = (base, a.name)
        return out

    @staticmethod
    def _import_time_nodes(body: list[ast.stmt]):
        """Nodes that EXECUTE when the module body runs: not function bodies (only their decorators and defaults), not the `__main__` guard, not `if TYPE_CHECKING`."""
        stack: list[ast.AST] = list(body)
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                stack.extend(n.decorator_list)
                stack.extend(n.args.defaults)
                stack.extend(d for d in n.args.kw_defaults if d is not None)
                continue
            if isinstance(n, ast.Lambda):
                continue
            if isinstance(n, ast.If) and (_is_main_guard(n.test) or _is_type_checking(n.test)):
                stack.extend(n.orelse)
                continue
            yield n
            stack.extend(ast.iter_child_nodes(n))

    def _sinks_in(self, mod: str, nodes, seen: set[tuple[str, str]]) -> list[tuple[int, str]]:
        hits: list[tuple[int, str]] = []
        defs = self._defs(mod)
        binds = self._bindings(mod)
        for n in nodes:
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            if isinstance(f, ast.Name) and f.id in READ_NAMES and f.id not in defs:
                hits.append((n.lineno, "%s()" % f.id))
            elif isinstance(f, ast.Attribute) and f.attr in READ_ATTRS:
                hits.append((n.lineno, ".%s()" % f.attr))
            # follow a call into the function it names, here or in another rediacc_ci module
            target: tuple[str, str] | None = None
            if isinstance(f, ast.Name):
                if f.id in defs:
                    target = (mod, f.id)
                elif f.id in binds and binds[f.id][1]:
                    target = (binds[f.id][0], binds[f.id][1])  # type: ignore[assignment]
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                b = binds.get(f.value.id)
                if b and b[1] is None:
                    target = (b[0], f.attr)
            if target and target not in seen:
                seen.add(target)
                d = self._defs(target[0]).get(target[1])
                if isinstance(d, ast.ClassDef):
                    body = [
                        x
                        for x in d.body
                        if isinstance(x, ast.FunctionDef)
                        and x.name in ("__init__", "__post_init__", "__new__")
                    ]
                    sub = [y for x in body for y in ast.walk(x)]
                elif isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # What the CALL runs: the body, minus nested defs and lambdas, which only run if something calls them later (run_verbs builds a table of `lambda: quality_ts_gate(name)` at import and reads nothing).
                    sub = list(self._import_time_nodes(d.body))
                else:
                    sub = []
                if self._sinks_in(target[0], sub, seen):
                    hits.append((n.lineno, "%s() reads a file" % ".".join(target)))
        return hits

    def import_time_reads(self, mod: str) -> list[tuple[int, str]]:
        """(line, what) for each place `mod`'s import-time code reaches a file read. Empty means it reads nothing at import."""
        if mod not in self._reads:
            t = self.tree(mod)
            self._reads[mod] = (
                sorted(set(self._sinks_in(mod, self._import_time_nodes(t.body), set())))
                if t
                else []
            )
        return self._reads[mod]

    def data_paths(self, mod: str) -> list[str]:
        """The repo files `mod` names as string literals, excluding Python sources. For a module that reads at import, these are what it needs from the cone."""
        t = self.tree(mod)
        out: set[str] = set()
        for n in ast.walk(t) if t else []:
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                v = n.value.strip().removeprefix("./")
                if (
                    v
                    and "\n" not in v
                    and len(v) < 200
                    and "/" in v
                    and not v.endswith(".py")
                    and not v.startswith("/")  # `root / "/dev/stdout"` IS /dev/stdout, a file
                    and (self.root / v).is_file()
                ):
                    out.add(v)
        return sorted(out)


def script_imports(index: PyIndex, script: str) -> list[str]:
    """The `rediacc_ci` modules a `.py` script imports (absolute imports only; a script has no package to be relative to)."""
    try:
        t = ast.parse((index.root / script).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return []
    out: set[str] = set()
    for n in PyIndex._walk_skipping_type_checking(t):
        if isinstance(n, ast.Import):
            out.update(a.name for a in n.names if a.name.startswith(PKG))
        elif isinstance(n, ast.ImportFrom) and not n.level and (n.module or "").startswith(PKG):
            out.add(n.module)  # type: ignore[arg-type]
            out.update("%s.%s" % (n.module, a.name) for a in n.names)
    return sorted(m for m in out if index.file_of(m))


def entries_for_module(index: PyIndex, mod: str) -> list[str]:
    """What `python3 -m <mod>` executes: the module, or a package's `__main__`."""
    return [mod, mod + ".__main__"] if index.is_package(mod) else [mod]


# ---------------------------------------------------------------------------
# the verdict
# ---------------------------------------------------------------------------


class Stats:
    def __init__(self):
        self.jobs = 0
        self.py_steps = 0
        self.not_followed: list[str] = []
        self.modules: set[str] = set()
        self.readers: dict[str, list[str]] = {}


def requirements(
    index: PyIndex, entries: list[str], stats: Stats
) -> tuple[list[tuple[str, str, list[str], str]], list[str]]:
    """What a step that executes `entries` needs from its cone.

    Returns (needs, unknowns). `needs` holds (path, kind, chain, why); `unknowns` names modules that read at import but name no data path, which is a failure because the gate cannot say what they need.
    """
    parent = index.closure(entries)
    stats.modules.update(parent)
    needs: list[tuple[str, str, list[str], str]] = []
    unknowns: list[str] = []
    for m in sorted(parent):
        f = index.file_of(m)
        if f:
            needs.append((f, "module", index.chain(parent, m), ""))
        reads = index.import_time_reads(m)
        if not reads:
            continue
        paths = index.data_paths(m)
        stats.readers[m] = paths
        if not paths:
            unknowns.append(
                "%s reads a file at import (%s) but names no repo data file as a string "
                "literal, so the gate cannot say what it needs. Name the path as a module-level "
                "constant (well_known's REGISTRY_REL is the model)."
                % (m, ", ".join("line %d %s" % r for r in reads[:3]))
            )
        why = "%s:%d %s" % (f, reads[0][0], reads[0][1])
        needs.extend((p, "data", index.chain(parent, m), why) for p in paths)
    return needs, unknowns


def job_findings(
    wf_name: str, jn: str, job: dict, index: PyIndex, stats: Stats, root: pathlib.Path = ROOT
) -> list[str]:
    probs: list[str] = []
    cones = cone_of(job)
    for i, st in enumerate(job.get("steps") or []):
        if not isinstance(st, dict):
            continue
        run = st.get("run")
        if not isinstance(run, str):
            continue
        sname = st.get("name") or "step %d" % (i + 1)
        cone = cones[i]
        cone_txt = ", ".join(cone) if cone else ("nothing" if cone is not None else "full")
        # 1. scripts invoked by path (the original check)
        entries: list[tuple[str, list[str]]] = []
        for m in INVOKE.findall(run):
            if not (root / m.removeprefix("./")).is_file():
                continue  # not a real path in this tree; not this gate's business
            if not covered(m, cone):
                probs.append(
                    "%s: job `%s` runs `%s`, which its checkout cone does not "
                    "include (%s). The step is correct, the script exists, and "
                    "the file will still be missing at runtime." % (wf_name, jn, m, cone_txt)
                )
            if m.endswith(".py"):
                mods = script_imports(index, m.removeprefix("./"))
                if mods:
                    stats.py_steps += 1
                    entries.append(("python3 %s" % m, mods))
        # 2. `python3 -m rediacc_ci.<mod>`
        for raw_pp, mod in PY_MODULE.findall(run):
            pp = raw_pp.strip("\"'")
            if pp and pp not in PKG_ROOT_PYTHONPATHS:
                stats.not_followed.append("%s/%s/%s (PYTHONPATH=%s)" % (wf_name, jn, sname, pp))
                continue
            stats.py_steps += 1
            if not index.file_of(mod):
                probs.append(
                    "%s: job `%s` step `%s` runs `python3 -m %s`, and no such module exists "
                    "under .ci/. It will fail with ModuleNotFoundError." % (wf_name, jn, sname, mod)
                )
                continue
            entries.append(("python3 -m %s" % mod, entries_for_module(index, mod)))
        for label, ents in entries:
            needs, unknowns = requirements(index, ents, stats)
            probs.extend(
                "%s: job `%s` step `%s` (%s): %s" % (wf_name, jn, sname, label, u) for u in unknowns
            )
            missing_mod = [n for n in needs if n[1] == "module" and not covered(n[0], cone)]
            missing_dat = [n for n in needs if n[1] == "data" and not covered(n[0], cone)]
            if missing_mod:
                first = missing_mod[0]
                probs.append(
                    "%s: job `%s` step `%s` runs `%s`, whose import chain needs %d module "
                    "file(s) the cone does not include (%s), first `%s` via %s. It will fail "
                    "with ModuleNotFoundError. Fix: add `.ci/%s` to that job's sparse-checkout."
                    % (
                        wf_name,
                        jn,
                        sname,
                        label,
                        len(missing_mod),
                        cone_txt,
                        first[0],
                        " -> ".join(first[2]),
                        PKG,
                    )
                )
            for path, _k, ch, why in sorted({(n[0], n[1], tuple(n[2]), n[3]) for n in missing_dat}):
                probs.append(
                    "%s: job `%s` step `%s` runs `%s`; import chain %s reads `%s` at import "
                    "(%s), which the cone does not include (%s). Fix: add `%s` to that job's "
                    "sparse-checkout."
                    % (wf_name, jn, sname, label, " -> ".join(ch), path, why, cone_txt, path)
                )
    return probs


def findings(wf_dir: pathlib.Path = WF, root: pathlib.Path = ROOT) -> tuple[list[str], Stats]:
    probs: list[str] = []
    stats = Stats()
    index = PyIndex(root)
    for f in sorted(wf_dir.glob("*.yml")):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(doc, dict):
            continue
        for jn, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict) or not job.get("steps"):
                continue
            stats.jobs += 1
            probs.extend(job_findings(f.name, jn, job, index, stats, root))
    return probs, stats


# ---------------------------------------------------------------------------
# controls
# ---------------------------------------------------------------------------

FIXTURE = {
    ".ci/rediacc_ci/__init__.py": "",
    ".ci/rediacc_ci/registry.py": (
        'import pathlib\nREL = ".ci/config/fixture.env"\n'
        "def load():\n    return (pathlib.Path(__file__).parent.parent / 'config' / 'fixture.env').read_text()\n"
        "VALUES = load()\n"
    ),
    ".ci/rediacc_ci/lazy.py": (
        'REL = ".ci/config/fixture.env"\n'
        "def later():\n    return open(REL).read()\n"
        'if __name__ == "__main__":\n    later()\n'
    ),
    ".ci/rediacc_ci/sub/__init__.py": "",
    ".ci/rediacc_ci/sub/uses_registry.py": "from .. import registry\n",
    ".ci/rediacc_ci/sub/entry.py": (
        "from typing import TYPE_CHECKING\nfrom rediacc_ci.sub import uses_registry\n"
        "if TYPE_CHECKING:\n    from rediacc_ci import typed_only\n"
    ),
    ".ci/rediacc_ci/typed_only.py": "from rediacc_ci import registry\n",
    ".ci/rediacc_ci/clean.py": "from rediacc_ci import lazy\n",
    ".ci/rediacc_ci/via_call.py": "from rediacc_ci.registry import load\nX = load()\n",
    ".ci/rediacc_ci/blind.py": "import os\nX = os.listdir(os.environ.get('D', '.'))\n",
    ".ci/rediacc_ci/factory.py": (
        "def arm(n):\n    return lambda: open(n).read()\nARMS = {'a': arm('x')}\nOUT = '/dev/stdout'\n"
    ),
    ".ci/rediacc_ci/probe.py": (
        "import pathlib\nHERE = pathlib.Path('.ci/config/fixture.env').exists()\n"
    ),
    ".ci/config/fixture.env": "K=v\n",
}


def selftest() -> int:
    bad = 0

    def check(name, ok, detail=""):
        nonlocal bad
        print(
            "  %s  %s%s"
            % ("PASS" if ok else "FAIL", name, "\n        " + detail if detail and not ok else "")
        )
        if not ok:
            bad += 1

    # THE PLANT is the historical defect: a cone that stops at .ci/config, and a step that runs .ci/scripts/ci/shadow-compare.sh.
    check(
        "PLANT: a cone stopping at .ci/config does NOT cover .ci/scripts/ci/x.sh",
        not covered(".ci/scripts/ci/shadow-compare.sh", [".github/actions", ".ci/config"]),
    )
    check(
        "CONTROL: adding .ci/scripts covers it",
        covered(
            ".ci/scripts/ci/shadow-compare.sh", [".github/actions", ".ci/config", ".ci/scripts"]
        ),
    )
    check("CONTROL: a FULL checkout covers everything", covered("anything/at/all.sh", None))
    check(
        "CONTROL: a sibling prefix is not a cone match (.ci/script must not cover .ci/scripts)",
        not covered(".ci/scripts/x.sh", [".ci/script"]),
    )
    # The matcher: an invocation is a command, not a mention.
    check(
        "an invocation at the start of a line is found",
        INVOKE.findall(".ci/scripts/ci/shadow-compare.sh") == [".ci/scripts/ci/shadow-compare.sh"],
    )
    check(
        "and after a pipe or &&",
        len(INVOKE.findall("true && .ci/scripts/a.sh | scripts/b.py")) == 2,
    )
    check(
        "an INTERPRETER invocation counts (python3 x.py, node y.cjs, npx tsx z.ts)",
        INVOKE.findall("python3 .ci/scripts/a.py") == [".ci/scripts/a.py"]
        and INVOKE.findall("node scripts/b.cjs") == ["scripts/b.cjs"]
        and INVOKE.findall("npx tsx scripts/c.ts") == ["scripts/c.ts"],
    )
    check(
        "CONTROL: a MENTION inside an echo is not an invocation",
        not INVOKE.findall('echo "see .ci/scripts/ci/shadow-compare.sh for details"'),
    )
    # `python3 -m` matcher
    check(
        "`PYTHONPATH=.ci python3 -m rediacc_ci.a.b` is a module invocation from .ci",
        PY_MODULE.findall("PYTHONPATH=.ci python3 -m rediacc_ci.a.b --x")
        == [(".ci", "rediacc_ci.a.b")],
    )
    check(
        "interpreter flags before -m are allowed, and a foreign PYTHONPATH is captured",
        PY_MODULE.findall('PYTHONPATH="$T/x/.ci" python3 -P -m rediacc_ci.r')
        == [('"$T/x/.ci"', "rediacc_ci.r")],
    )
    check(
        "CONTROL: a backticked mention `python3 -m rediacc_ci.*` in a comment is not a module",
        not PY_MODULE.findall("# runs `python3 -m rediacc_ci.*` here"),
    )
    check(
        "CONTROL: a `path:` checkout does not widen the ROOT cone",
        cone_of(
            {
                "steps": [
                    {"uses": "actions/checkout@x", "with": {"sparse-checkout": ".github"}},
                    {"uses": "actions/checkout@x", "with": {"path": "o", "sparse-checkout": ".ci"}},
                ]
            }
        )[-1]
        == [".github"],
    )

    # The import edge, on a FIXTURE tree so these controls do not move when the real package does.
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="cone-selftest-"))
    try:
        for rel, body in FIXTURE.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_text(body, encoding="utf-8")
        ix = PyIndex(tmp)
        par = ix.closure(["rediacc_ci.sub.entry"])
        check(
            "the import graph follows `from pkg import submodule` and RELATIVE imports transitively",
            ix.chain(par, "rediacc_ci.registry")
            == ["rediacc_ci.sub.entry", "rediacc_ci.sub.uses_registry", "rediacc_ci.registry"],
            repr(par),
        )
        check(
            "parent packages are edges (importing a.b.c runs a/__init__ and a/b/__init__)",
            "rediacc_ci" in par and "rediacc_ci.sub" in par,
        )
        check(
            "CONTROL: an import under `if TYPE_CHECKING:` is not an edge",
            "rediacc_ci.typed_only" not in par,
        )
        check(
            "a module-level call to a local function that reads a file IS an import-time read",
            bool(ix.import_time_reads("rediacc_ci.registry")),
        )
        check(
            "a module-level call to an IMPORTED rediacc_ci function that reads is one too",
            bool(ix.import_time_reads("rediacc_ci.via_call")),
        )
        check(
            "CONTROL: a read inside a function only the __main__ guard calls is NOT import-time",
            not ix.import_time_reads("rediacc_ci.lazy"),
            repr(ix.import_time_reads("rediacc_ci.lazy")),
        )
        check(
            "the data path is DERIVED from the module's literal",
            ix.data_paths("rediacc_ci.registry") == [".ci/config/fixture.env"],
        )
        check(
            "CONTROL: calling a factory that RETURNS a reading lambda is not an import-time read",
            not ix.import_time_reads("rediacc_ci.factory"),
            repr(ix.import_time_reads("rediacc_ci.factory")),
        )
        check(
            "CONTROL: an existence probe is not a read (a missing file returns False, it does not raise)",
            not ix.import_time_reads("rediacc_ci.probe"),
        )
        check(
            "CONTROL: an absolute literal (/dev/stdout) is never a repo data path",
            ix.data_paths("rediacc_ci.factory") == [],
            repr(ix.data_paths("rediacc_ci.factory")),
        )
        st = Stats()
        plant_job = {
            "steps": [
                {
                    "uses": "actions/checkout@x",
                    "with": {"sparse-checkout": ".ci/rediacc_ci\n.github/actions\n"},
                },
                {"name": "Run it", "run": "PYTHONPATH=.ci python3 -m rediacc_ci.sub.entry"},
            ]
        }
        got = job_findings("fx.yml", "fx-job", plant_job, ix, st, tmp)
        check(
            "PLANT: a cone without the data file reds, naming job, step, chain and file",
            len(got) == 1
            and all(
                s in got[0]
                for s in (
                    "`fx-job`",
                    "`Run it`",
                    "rediacc_ci.sub.entry -> rediacc_ci.sub.uses_registry -> rediacc_ci.registry",
                    "`.ci/config/fixture.env`",
                )
            ),
            repr(got),
        )
        plant_job["steps"][0]["with"]["sparse-checkout"] += ".ci/config/fixture.env\n"
        check(
            "CONTROL: the same cone WITH the data file is green",
            not job_findings("fx.yml", "fx-job", plant_job, ix, Stats(), tmp),
        )
        clean_job = {
            "steps": [
                {"uses": "actions/checkout@x", "with": {"sparse-checkout": ".ci/rediacc_ci"}},
                {"name": "Clean", "run": "PYTHONPATH=.ci python3 -m rediacc_ci.clean"},
            ]
        }
        check(
            "CONTROL: a chain that never reads at import needs only the package",
            not job_findings("fx.yml", "j", clean_job, ix, Stats(), tmp),
        )
        clean_job["steps"][0]["with"]["sparse-checkout"] = ".ci/rediacc_ci/sub"
        check(
            "PLANT: a cone missing the package itself reds with ModuleNotFoundError",
            any(
                "ModuleNotFoundError" in p
                for p in job_findings("fx.yml", "j", clean_job, ix, Stats(), tmp)
            ),
        )
        blind_job = {
            "steps": [
                {"uses": "actions/checkout@x", "with": {"sparse-checkout": ".ci/rediacc_ci"}},
                {"name": "Blind", "run": "PYTHONPATH=.ci python3 -m rediacc_ci.blind"},
            ]
        }
        check(
            "UNKNOWN fails: an import-time read naming no data literal is a finding, not a pass",
            any(
                "cannot say what it needs" in p
                for p in job_findings("fx.yml", "j", blind_job, ix, Stats(), tmp)
            ),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # The REAL tree: the detector must still see the module that caused this edge to exist.
    real = PyIndex(ROOT)
    check(
        "REAL: rediacc_ci.well_known reads at import, and its derived data path is its REGISTRY_REL",
        bool(real.import_time_reads("rediacc_ci.well_known"))
        and real.data_paths("rediacc_ci.well_known") == [_well_known_registry_rel()],
        "reads=%r paths=%r"
        % (
            real.import_time_reads("rediacc_ci.well_known"),
            real.data_paths("rediacc_ci.well_known"),
        ),
    )
    pr = real.closure(["rediacc_ci.review.review_table"])
    check(
        "REAL: review_table's chain reaches rediacc_ci.well_known (the run 37117682295 chain)",
        "rediacc_ci.well_known" in pr,
    )
    return bad


def _well_known_registry_rel() -> str:
    """well_known's REGISTRY_REL, read from its AST, so the control compares two facts from the code rather than one fact against this file's memory of it."""
    t = ast.parse((ROOT / ".ci/rediacc_ci/well_known.py").read_text(encoding="utf-8"))
    for n in t.body:
        if (
            isinstance(n, ast.Assign)
            and any(isinstance(x, ast.Name) and x.id == "REGISTRY_REL" for x in n.targets)
            and isinstance(n.value, ast.Constant)
        ):
            return str(n.value.value)
    return "<REGISTRY_REL not found in well_known.py>"


def main(argv: list[str]) -> int:
    wf_dir = WF
    if "--workflows" in argv:
        # A directory of workflow files to judge instead of .github/workflows, against the REAL package. This is how a plant is run on real inputs without touching the tree: copy the workflows, break one cone, point the gate at the copy.
        wf_dir = pathlib.Path(argv[argv.index("--workflows") + 1]).resolve()
    print("checkout cone: controls first, then the verdict")
    if selftest():
        print(
            "✗ instrument control failed; every verdict below would be meaningless", file=sys.stderr
        )
        return 2
    if "--selftest" in argv:
        return 0
    probs, st = findings(wf_dir)
    if st.jobs < MIN_JOBS or st.py_steps < MIN_PY_STEPS:
        print(
            "VACUOUS INPUT: %d job(s) parsed (floor %d), %d python step(s) followed (floor %d). "
            "The enumeration lost the corpus." % (st.jobs, MIN_JOBS, st.py_steps, MIN_PY_STEPS),
            file=sys.stderr,
        )
        return 1
    if probs:
        print("✗ checkout cone (%d finding(s)):" % len(probs), file=sys.stderr)
        for p in probs:
            print("    %s" % p, file=sys.stderr)
        print("  Fix: add the named path to that job's sparse-checkout.", file=sys.stderr)
        return 1
    readers = "; ".join("%s -> %s" % (m, ", ".join(p)) for m, p in sorted(st.readers.items()))
    print(
        "✓ checkout cone: %d job(s); every script a step runs is inside its own checkout, and "
        "%d python step(s) were followed through %d rediacc_ci module(s) with every module and "
        "import-time data file inside the cone" % (st.jobs, st.py_steps, len(st.modules))
    )
    print("  import-time data readers reached: %s" % (readers or "none"))
    print(
        "  not followed (%d, package imported from outside the root checkout): %s"
        % (len(st.not_followed), "; ".join(st.not_followed) or "none")
    )
    print("  Blind spot: only paths that look like an INVOCATION are resolved -- a script")
    print("  reached through a variable or a wrapper is not seen, and a data file read at")
    print("  RUNTIME (inside a function) rather than at import is not modelled. Under-reporting")
    print("  is the safe direction: a miss fails loudly in CI, a false positive blocks a good job.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
