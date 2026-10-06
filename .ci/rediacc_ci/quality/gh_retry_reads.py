"""check:ci-gh-retry-reads -- every GitHub READ made through `gh` retries a transient fault.

WHY THIS EXISTS. On 2026-10-06 one `gh: Server Error (HTTP 502)` failed CI Complete on PR #597 (run 37507913738), and a read-only audit the same day found 20 modules under `.ci/rediacc_ci` reading GitHub through a bare one-shot `subprocess.run(["gh", ...])`. Three of them were silently WRONG on a single 5xx rather than merely red: `release/resolve_ci_run` fell back to GITHUB_SHA and released the wrong
build, `version/detect_bump_type` read a major label as a patch, `ci/dispatch_release` released a skip-labelled PR (agent/plans/PLAN-gh-retry.md, boxes G0-G8). The fix moved each read onto `rediacc_ci.core.gh_retry`. This gate is box G9: it keeps the next one-shot read from arriving unnoticed.

THE INVARIANT. Every non-test `gh` call site under `.ci/rediacc_ci` and `.ci/scripts` is classified READ, WRITE or LOCAL. A READ must be RETRIED, which here means exactly one of:
  * a call to `gh_retry.gh(...)` / `gh_retry.api_json(...)`;
  * a call to a `ghx` read helper with a constant `attempts=` of 2 or more;
  * a raw spawn that sits inside the retry machinery: lexically inside a lambda handed to `retry_transient(...)`, inside a function whose NAME is handed to `retry_transient(...)`, or inside a `for`/`while` loop that itself consults `is_transient` (the hand loop `ci/scope_reconcile_shadow.read_jobs` keeps);
  * any of the above one level up, through a WRAPPER: a function that spawns `["gh", *param]` is resolved at its in-module call sites, with the caller's argument substituted, to a fixpoint.
Anything else that reads is a FINDING, unless its `<path>::<qualname>` is in `ALLOWED` below with a `BLOCKER:` reason. A WRITE is reported as information and never retried, by design: a retried POST after a lost response creates a second release, run or comment.

DETECTION IS STRUCTURAL, NOT A GREP. The argv is read out of the AST: a list or tuple literal whose first element is `"gh"`, a name assigned one in an enclosing scope (with its `+=` extensions), a `[binary, *argv]` whose `binary` parameter defaults to `"gh"`, or a `list + list`. The CALLEE is deliberately not restricted to `subprocess.*`, because the tree spawns `gh` through `bounded(...)`, `ctx.run(...)`, `_run(...)` and
`proc.run(...)` as well; instead the handful of calls that merely CONSUME an argv (`" ".join`, an exception constructor, a logger) are excluded by name in `_NOT_A_SPAWN`.

READ OR WRITE, from the argv:
  gh api            write when `-X/--method` is POST|PATCH|PUT|DELETE, or when no method is given and `-f/-F/--field/--raw-field/--input` is (gh then defaults to POST);
                    `gh api graphql` is a write only when a token names a `mutation`.
  gh workflow       run|enable|disable are writes.
  gh release        create|delete|delete-asset|upload|edit are writes.
  gh run            rerun|cancel|delete are writes.
  gh pr             edit|merge|ready|create|close|reopen|comment|review|lock|unlock are writes.
  gh label          create|edit|delete|clone are writes.
  gh issue, secret, variable, cache, repo: their mutating verbs are writes.
  gh --version, version, help, completion, auth login|logout|setup-git|switch|token: LOCAL, no GitHub read.
  Everything else is a READ. A verb the AST cannot resolve (the argv tail is computed) is UNRESOLVED and counts as a read: guessing "write" would be the silent direction.

BLIND SPOTS, stated so a green is not read as more than it is:
  * Wrappers are followed within ONE module. A wrapper called from another module is reported at its own spawn as UNRESOLVED, which over-reports rather than hides.
  * `gh` spawned from bash under `.ci/scripts`, and the `.claude` hooks, are out of scope; the language policy ports the first, and the hooks carry their own budget.
  * A retried call is recognised by its SHAPE; whether its failure is then handled correctly is the module's own gate test's business.

ANTI-VACUITY. Zero modules scanned, zero `gh` call sites, zero reads routed through `gh_retry`, or zero writes FAILS: each is the signature of a detector that stopped seeing the tree. Controls run first (`controls_first`), and the real run then plants two defects into REAL module text in memory -- a `gh_retry.gh(` read demoted to a one-shot `ghx.gh(` read, and a guarded raw spawn with its `retry_transient` unhooked -- and refuses
a green unless each plant adds a finding.

ALLOWLIST LIVENESS, in-gate on the `.runner-advice-allowlist` precedent (docs/agent-reference/suppressions.md): an `ALLOWED` entry that excuses no unretried read on the tree is STALE and fails, telling the author to delete it; the oracle IS the comparison this gate already makes. Every excused site is printed on every run, so the exemption cannot be forgotten.

Exit codes: 0 clean, 1 a finding (or a stale/invalid allowlist entry, or a vacuous scan), 2 an instrument control failed.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import functools
import hashlib
import json
import pathlib
import re
import sys

from rediacc_ci import paths
from rediacc_ci.controls import Checker, controls_first, plant
from rediacc_ci.core import allowlist

NAME = "gh retry reads"
SCAN_ROOTS = (".ci/rediacc_ci", ".ci/scripts")
# THE POLICY ITSELF. gh_retry.gh calls ghx.gh with attempts=1 on purpose (each attempt is one call), and ghx IS the one-shot primitive; scanning them would report the retry as its own violation.
IMPLEMENTATION = frozenset({".ci/rediacc_ci/core/gh_retry.py", ".ci/rediacc_ci/core/ghx.py"})
# This gate's own fixtures are string literals, never AST lists, so it cannot report itself; listing it anyway keeps a future fixture refactor from turning the gate on its own source.
SELF_REL = ".ci/rediacc_ci/quality/gh_retry_reads.py"

GHX_READ_HELPERS = frozenset(
    {
        "gh",
        "api_json",
        "pr_list",
        "pr_head_refs",
        "branch_indexes",
        "next_branch_name",
        "secret_names",
    }
)
GH_RETRY_HELPERS = frozenset({"gh", "api_json"})
GHX_MODULE = "rediacc_ci.core.ghx"
GH_RETRY_MODULE = "rediacc_ci.core.gh_retry"

# Calls that take an argv as DATA rather than spawning it. Measured on the tree 2026-10-06: `ci/sibling_runs.py` hands `["gh", "api", "runs"]` to `ghx.GhBadOutputError(...)` and `ci/dispatch_release.py` prints `" ".join(argv)` on its dry-run path; both are an argv that is never run.
_NOT_A_SPAWN = frozenset(
    {
        "join",
        "list2cmdline",
        "quote",
        "print",
        "format",
        "append",
        "extend",
        "debug",
        "info",
        "warn",
        "warning",
        "error",
        "notice",
        "repr",
        "str",
        "len",
    }
)
_ARGV_KEYWORDS = ("args", "argv", "cmd", "command")
_MAY_SPAWN_GH = re.compile(r"""["']gh["']|\bghx\b|\bgh_retry\b""")

WRITE_VERBS: dict[str, frozenset[str]] = {
    "workflow": frozenset({"run", "enable", "disable"}),
    "release": frozenset({"create", "delete", "delete-asset", "upload", "edit"}),
    "run": frozenset({"rerun", "cancel", "delete"}),
    "pr": frozenset(
        {
            "edit",
            "merge",
            "ready",
            "create",
            "close",
            "reopen",
            "comment",
            "review",
            "lock",
            "unlock",
        }
    ),
    "label": frozenset({"create", "edit", "delete", "clone"}),
    "issue": frozenset(
        {
            "create",
            "edit",
            "close",
            "reopen",
            "comment",
            "delete",
            "transfer",
            "pin",
            "unpin",
            "lock",
            "unlock",
        }
    ),
    "secret": frozenset({"set", "delete", "remove"}),
    "variable": frozenset({"set", "delete"}),
    "cache": frozenset({"delete"}),
    "repo": frozenset(
        {"create", "edit", "delete", "fork", "rename", "archive", "unarchive", "sync"}
    ),
}
WRITE_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
_API_BODY_FLAGS = frozenset({"-f", "-F", "--field", "--raw-field", "--input"})
_LOCAL_TOP = frozenset({"--version", "version", "help", "--help", "completion"})
_LOCAL_AUTH = frozenset({"login", "logout", "setup-git", "switch", "token"})

# ---------------------------------------------------------------------------
# ALLOWED: reads that stay one-shot, by <path>::<qualname>, each with its reason.
#
# Every reason was verified against the code on 2026-10-06, not copied from the audit. Keyed by qualified function name rather than by line, so an entry survives a paragraph moving above it and a NEW one-shot read in a different function of an allowlisted module still reds. Do not add an entry to get a red gate green: route the read through `gh_retry.gh` instead.
# ---------------------------------------------------------------------------
ALLOWED: dict[str, str] = {
    # Two copies of `_gh_probe`'s ladder, ported from common.sh: three attempts, sleeping 3 s then 6 s, and a body that must parse as JSON. It retries ANY failure (a 4xx costs nine seconds), which is wasteful but not unsafe; it is the retry this gate asks for, spelled before gh_retry existed.
    ".ci/rediacc_ci/quality/resolved_threads.py::gh_json": "BLOCKER: gh_json carries its own three-attempt ladder (GH_ATTEMPTS=3, sleeper(attempt * GH_SLEEP_FACTOR)), so every read through it already survives a single 5xx; only the backoff policy differs from gh_retry",
    ".ci/rediacc_ci/quality/review_comments.py::gh_json": "BLOCKER: gh_json carries its own three-attempt ladder (GH_ATTEMPTS=3, sleeper(attempt * GH_SLEEP_FACTOR)), so every read through it already survives a single 5xx; only the backoff policy differs from gh_retry",
    # The listing read sits inside `while True`: on `rc != 0` it logs "retrying...", sleeps POLL_INTERVAL and `continue`s until CANCEL_TIMEOUT. A poll loop is a retry, just not one this detector can see by shape.
    ".ci/rediacc_ci/ci/cancel_older_runs.py::main": "BLOCKER: the in-progress listing is re-read every POLL_INTERVAL inside a while-True loop until the timeout, and a failed read logs and continues, so a 5xx costs one poll interval and never ends the run",
    # FAIL CLOSED, verified 2026-10-06: an unreadable branch list returns 0 having done nothing (`if not live_heads`), and an unreadable run list falls back to EMPTY_RUNS, so nothing is rerun. The next nightly is the retry.
    ".ci/rediacc_ci/housekeeping/retry_failed_runs.py::_gh_or_empty": "BLOCKER: both nightly reads fail closed: no branch tips means exit 0 having rerun nothing, and an unreadable run list is the empty list, so a 5xx can only skip one night, never rerun a superseded run",
    # Local operator tooling, never invoked by a workflow (grep of .github and package.json, 2026-10-06).
    ".ci/rediacc_ci/dev/worktree.py::pr_merged_at_tip": "BLOCKER: a local worktree tool no workflow runs; a failed read returns False (not merged), which keeps the worktree, and the only other prune reason is a git-only no-commits check",
    ".ci/rediacc_ci/setup/host.py::_try_gh_credential": "BLOCKER: interactive host setup run by the operator, never in CI; a failed `gh auth status` falls through to the stored-token path, which asks the operator, so nothing is decided wrongly on a 5xx",
}

# ---------------------------------------------------------------------------
# The argv model.
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Param:
    """A token that is a parameter of `owner` (a FunctionDef). `star` means it stands for zero or more tokens."""

    owner: int  # id() of the defining FunctionDef node
    name: str
    star: bool
    # `binary: str = "gh"`: the value a caller gets when it does not pass this parameter. A caller that DOES pass it (resolved_threads' selftest hands `binary="gh-does-not-exist-zzz"`) is not spawning gh at all.
    default: str | None = None


@dataclasses.dataclass(frozen=True)
class Choice:
    """One token assigned different constant strings on different branches (`method = "PATCH"` / `"POST"`)."""

    values: frozenset[str]


class _Dyn:
    """One token whose value the AST cannot know."""

    def __repr__(self) -> str:
        return "?"


class _Star:
    """Zero or more tokens whose values the AST cannot know."""

    def __repr__(self) -> str:
        return "*?"


DYN = _Dyn()
STAR = _Star()
Token = str | Param | Choice | _Dyn | _Star


@dataclasses.dataclass
class Site:
    """One `gh` call site and its verdict."""

    path: str
    line: int
    qualname: str
    kind: str  # read | write | local | unresolved
    verb: str
    route: str  # gh_retry | ghx-retry | guarded | one-shot | ghx-one-shot | ghx-by-reference
    # The function holding the RAW spawn. Equal to `qualname` unless the site was resolved through a wrapper, in which case an ALLOWED entry may name the wrapper (resolved_threads' `gh_json`, which carries its own retry) and so excuse only the reads that go through it.
    via: str = ""
    # The literal argv text, computed tokens shown as `?`. Part of the baseline id, so two reads in one function stay distinct while a line number never enters it.
    argv: str = ""

    @property
    def key(self) -> str:
        return "%s::%s" % (self.path, self.qualname)

    @property
    def via_key(self) -> str:
        return "%s::%s" % (self.path, self.via or self.qualname)

    @property
    def stable_id(self) -> str:
        text = f"{self.path}|{self.qualname}|{self.via}|{self.verb}|{self.argv}"
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]

    @property
    def retried(self) -> bool:
        return self.route in ("gh_retry", "ghx-retry", "guarded")

    @property
    def needs_retry(self) -> bool:
        return self.kind in ("read", "unresolved") and not self.retried


def classify(tokens: list[Token]) -> tuple[str, str]:
    """(kind, verb) for an argv whose first token is "gh". Pure, so the selftest drives it directly."""
    sub = tokens[1:]

    def word(i: int) -> str | None:
        tok = sub[i] if i < len(sub) else None
        return tok if isinstance(tok, str) else None

    top = word(0)
    if top is None:
        return "unresolved", "?"
    if top in _LOCAL_TOP:
        return "local", top
    if top == "auth":
        second = word(1)
        if second in _LOCAL_AUTH:
            return "local", "auth %s" % second
        return "read", "auth %s" % (second or "?")
    if top == "api":
        return _classify_api(sub[1:])
    second = word(1)
    writes = WRITE_VERBS.get(top)
    if writes is not None and second is None and len(sub) > 1:
        return "unresolved", "%s ?" % top
    if writes is not None and second in writes:
        return "write", "%s %s" % (top, second)
    return "read", ("%s %s" % (top, second)) if second else top


def _classify_api(rest: list[Token]) -> tuple[str, str]:
    endpoint = next((t for t in rest if isinstance(t, str) and not t.startswith("-")), None)
    if endpoint == "graphql":
        mutation = any(isinstance(t, str) and "mutation" in t for t in rest)
        return ("write", "api graphql mutation") if mutation else ("read", "api graphql")
    method: str | None = None
    method_unknown = False
    body = False
    for i, tok in enumerate(rest):
        if not isinstance(tok, str):
            continue
        if tok in ("-X", "--method"):
            nxt = rest[i + 1] if i + 1 < len(rest) else None
            if isinstance(nxt, str):
                method = nxt.upper()
            elif isinstance(nxt, Choice) and all(v.upper() in WRITE_METHODS for v in nxt.values):
                method = "|".join(sorted(v.upper() for v in nxt.values))
                return "write", "api %s" % method
            elif isinstance(nxt, Choice) and not any(
                v.upper() in WRITE_METHODS for v in nxt.values
            ):
                method = "GET"
            else:
                method_unknown = True
        elif tok.startswith("--method="):
            method = tok.split("=", 1)[1].upper()
        elif tok.startswith("-X") and len(tok) > 2:
            method = tok[2:].upper()
        elif tok in _API_BODY_FLAGS or tok.startswith(("--field=", "--raw-field=", "--input=")):
            body = True
    if method is not None:
        return ("write" if method in WRITE_METHODS else "read"), "api %s" % method
    if method_unknown:
        return "unresolved", "api -X ?"
    if body:
        return "write", "api POST (implied by a body flag)"
    return "read", "api GET"


# ---------------------------------------------------------------------------
# The per-module walk.
# ---------------------------------------------------------------------------

_Func = ast.FunctionDef | ast.AsyncFunctionDef


def _callee_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _is_not_a_spawn(call: ast.Call) -> bool:
    name = _callee_name(call)
    if name is None:
        return False
    return name in _NOT_A_SPAWN or name.endswith(("Error", "Exception"))


class _Module:
    def __init__(self, rel: str, src: str) -> None:
        self.rel = rel
        self.tree = ast.parse(src)
        # ONE walk, reused by every pass below and by scan_source: re-walking the tree per pass (and per wrapper) was most of a 12 s profile (2026-10-06).
        self.nodes: list[ast.AST] = list(ast.walk(self.tree))
        self.parent: dict[int, ast.AST] = {}
        for node in self.nodes:
            for child in ast.iter_child_nodes(node):
                self.parent[id(child)] = node
        self.qualnames: dict[int, str] = {}
        self._name_scopes(self.tree, [])
        self.funcs_by_name: dict[str, list[_Func]] = {}
        for node in self.nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.funcs_by_name.setdefault(node.name, []).append(node)
        self._assign_cache: dict[int, dict[str, list[ast.expr]]] = {}
        self.retry_targets = self._retry_targets()
        self.aliases = self._aliases()

    # -- scopes ------------------------------------------------------------
    def _name_scopes(self, node: ast.AST, stack: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = [*stack, child.name]
                self.qualnames[id(child)] = ".".join(q)
                self._name_scopes(child, q)
            else:
                self._name_scopes(child, stack)

    def ancestors(self, node: ast.AST):
        cur = self.parent.get(id(node))
        while cur is not None:
            yield cur
            cur = self.parent.get(id(cur))

    def enclosing_funcs(self, node: ast.AST) -> list[_Func]:
        return [
            a
            for a in self.ancestors(node)
            if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]

    def qualname_of(self, node: ast.AST) -> str:
        for a in self.ancestors(node):
            if isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return self.qualnames[id(a)]
        return "<module>"

    # -- imports -----------------------------------------------------------
    def _aliases(self) -> dict[str, str]:
        """local name -> 'ghx' | 'gh_retry' | 'ghx.<fn>' | 'gh_retry.<fn>'."""
        out: dict[str, str] = {}
        for node in self.nodes:
            if isinstance(node, ast.ImportFrom) and node.module:
                for a in node.names:
                    full = "%s.%s" % (node.module, a.name)
                    local = a.asname or a.name
                    if full == GHX_MODULE:
                        out[local] = "ghx"
                    elif full == GH_RETRY_MODULE:
                        out[local] = "gh_retry"
                    elif node.module == GHX_MODULE:
                        out[local] = "ghx.%s" % a.name
                    elif node.module == GH_RETRY_MODULE:
                        out[local] = "gh_retry.%s" % a.name
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.name in (GHX_MODULE, GH_RETRY_MODULE) and a.asname:
                        out[a.asname] = "ghx" if a.name == GHX_MODULE else "gh_retry"
        return out

    def _api_of(self, node: ast.AST) -> str | None:
        """'ghx.<fn>' / 'gh_retry.<fn>' when `node` names a helper of either module."""
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            mod = self.aliases.get(node.value.id)
            if mod in ("ghx", "gh_retry"):
                return "%s.%s" % (mod, node.attr)
        if isinstance(node, ast.Name):
            mapped = self.aliases.get(node.id)
            if mapped and "." in mapped:
                return mapped
        return None

    # -- retry recognition -------------------------------------------------
    def _retry_targets(self) -> set[str]:
        """Function names handed to `retry_transient(...)` anywhere in the module."""
        out: set[str] = set()
        for node in self.nodes:
            if isinstance(node, ast.Call) and _callee_name(node) == "retry_transient":
                cands = list(node.args[:1]) + [k.value for k in node.keywords if k.arg == "call"]
                for c in cands:
                    if isinstance(c, ast.Name):
                        out.add(c.id)
                    elif isinstance(c, ast.Attribute):
                        out.add(c.attr)
        return out

    def is_guarded(self, node: ast.AST) -> bool:
        for a in self.ancestors(node):
            if isinstance(a, ast.Lambda):
                p = self.parent.get(id(a))
                if isinstance(p, ast.Call) and _callee_name(p) == "retry_transient":
                    return True
            elif isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if a.name in self.retry_targets:
                    return True
            elif isinstance(a, (ast.For, ast.AsyncFor, ast.While)):
                for sub in ast.walk(a):
                    if (isinstance(sub, ast.Attribute) and sub.attr == "is_transient") or (
                        isinstance(sub, ast.Name) and sub.id == "is_transient"
                    ):
                        return True
        return False

    # -- argv resolution -----------------------------------------------------
    def _param_of(
        self, name: str, scopes: list[_Func]
    ) -> tuple[_Func, ast.arg, ast.expr | None] | None:
        for fn in scopes:
            a = fn.args
            positional = a.posonlyargs + a.args
            defaults: list[ast.expr | None] = [None] * (len(positional) - len(a.defaults)) + list(
                a.defaults
            )
            for arg, default in zip(positional, defaults, strict=True):
                if arg.arg == name:
                    return fn, arg, default
            for arg, kw_default in zip(a.kwonlyargs, a.kw_defaults, strict=True):
                if arg.arg == name:
                    return fn, arg, kw_default
            if a.vararg is not None and a.vararg.arg == name:
                return fn, a.vararg, None
            if self._assigns(name, fn):
                return None
        return None

    def _assigns(self, name: str, fn: ast.AST) -> list[ast.expr]:
        """Values assigned to `name` directly in `fn` (nested defs excluded), in source order; `+=` values come back wrapped as AugAssign.

        INDEXED once per scope. The first version re-walked the scope for every lookup, and a lookup happens for every Name argument of every call, against the MODULE scope too: quadratic in module size, and one gate run took over 20 s across 554 modules (measured 2026-10-06).
        """
        index = self._assign_cache.get(id(fn))
        if index is None:
            index = self._index_scope(fn)
            self._assign_cache[id(fn)] = index
        return index.get(name, [])

    @staticmethod
    def _index_scope(fn: ast.AST) -> dict[str, list[ast.expr]]:
        found: dict[str, list[tuple[int, ast.expr]]] = {}

        def add(name: str, line: int, value: ast.expr) -> None:
            found.setdefault(name, []).append((line, value))

        stack = list(ast.iter_child_nodes(fn))
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        add(t.id, n.lineno, n.value)
                    elif (
                        isinstance(t, ast.Tuple)
                        and isinstance(n.value, ast.Tuple)
                        and len(t.elts) == len(n.value.elts)
                    ):
                        # `method, path, body = ("PATCH", ...)`: publish_ci_verdict.upsert picks its verb this way.
                        for te, ve in zip(t.elts, n.value.elts, strict=True):
                            if isinstance(te, ast.Name):
                                add(te.id, n.lineno, ve)
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value:
                add(n.target.id, n.lineno, n.value)
            elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name):
                add(n.target.id, n.lineno, n)  # type: ignore[arg-type]
            stack.extend(ast.iter_child_nodes(n))
        return {k: [v for _, v in sorted(rows, key=lambda r: r[0])] for k, rows in found.items()}

    def tokens(self, expr: ast.AST, at: ast.AST, depth: int = 0) -> list[Token] | None:
        """The argv `expr` denotes at node `at`, or None when it is not a list-shaped expression."""
        if depth > 8:
            return None
        if isinstance(expr, (ast.List, ast.Tuple)):
            out: list[Token] = []
            for elt in expr.elts:
                if isinstance(elt, ast.Starred):
                    inner = self.tokens(elt.value, at, depth + 1)
                    if inner is not None:
                        out.extend(inner)
                    else:
                        out.append(self._param_token(elt.value, at, star=True) or STAR)
                else:
                    out.append(self._scalar(elt, at))
            return out
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            left = self.tokens(expr.left, at, depth + 1)
            if left is None:
                return None
            right = self.tokens(expr.right, at, depth + 1)
            if right is None:
                right = [self._param_token(expr.right, at, star=True) or STAR]
            return left + right
        if isinstance(expr, ast.Name):
            scopes = self.enclosing_funcs(at)
            for scope in [*scopes, self.tree]:
                values = self._assigns(expr.id, scope)
                if not values:
                    if scope is not self.tree and self._param_of(expr.id, [scope]):  # type: ignore[list-item]
                        return None
                    continue
                base: list[Token] | None = None
                for v in values:
                    if isinstance(v, ast.AugAssign):
                        if base is None:
                            continue
                        more = self.tokens(v.value, at, depth + 1)
                        base = base + (more if more is not None else [STAR])
                    elif base is None:
                        base = self.tokens(v, at, depth + 1)
                return base
        return None

    def _scalar(self, elt: ast.expr, at: ast.AST) -> Token:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            return elt.value
        # A TEMPLATE is kept as its literal text: `"repos/%s/pulls" % repo` and `f"repos/{repo}/pulls"` both read `repos/%s/pulls`. Without this every formatted endpoint was `?`, so two different reads in one function shared a baseline id and the id could not tell a rewritten endpoint from the old one.
        if (
            isinstance(elt, ast.BinOp)
            and isinstance(elt.op, ast.Mod)
            and isinstance(elt.left, ast.Constant)
            and isinstance(elt.left.value, str)
        ):
            return elt.left.value
        if isinstance(elt, ast.JoinedStr):
            return "".join(
                v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "%s"
                for v in elt.values
            )
        if isinstance(elt, ast.Name):
            hit = self._param_of(elt.id, self.enclosing_funcs(at))
            if hit is not None:
                fn, _arg, default = hit
                if isinstance(default, ast.Constant) and isinstance(default.value, str):
                    return Param(id(fn), elt.id, False, default.value)
                return self._param_token(elt, at, star=False) or DYN
            for scope in [*self.enclosing_funcs(at), self.tree]:
                values = self._assigns(elt.id, scope)
                if values:
                    consts = [
                        v.value
                        for v in values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    ]
                    if len(consts) != len(values):
                        return DYN
                    if len(set(consts)) == 1:
                        return consts[0]
                    return Choice(frozenset(consts))
        return DYN

    def _param_token(self, expr: ast.AST, at: ast.AST, *, star: bool) -> Param | None:
        if not isinstance(expr, ast.Name):
            return None
        hit = self._param_of(expr.id, self.enclosing_funcs(at))
        if hit is None:
            return None
        fn, arg, _default = hit
        is_vararg = fn.args.vararg is arg
        return Param(id(fn), expr.id, star or is_vararg)

    def gh_argv_of(self, call: ast.Call) -> list[Token] | None:
        if _is_not_a_spawn(call):
            return None
        cands = list(call.args) + [k.value for k in call.keywords if k.arg in _ARGV_KEYWORDS]
        for c in cands:
            toks = self.tokens(c, call)
            if toks and _head(toks) == "gh":
                return toks
        return None


def _head(tokens: list[Token]) -> str | None:
    h = tokens[0]
    if isinstance(h, Param):
        return h.default
    return h if isinstance(h, str) else None


def _settle(tokens: list[Token]) -> list[Token]:
    """Unbound parameters at an emitted site: a defaulted one takes its default, the rest are unknown."""
    out: list[Token] = []
    for t in tokens:
        if isinstance(t, Param):
            out.append(t.default if t.default is not None else (STAR if t.star else DYN))
        else:
            out.append(t)
    return out


@dataclasses.dataclass
class _Wrapper:
    fn: _Func
    template: list[Token]
    guarded: bool


def _bind(wrapper: _Wrapper, call: ast.Call, mod: _Module) -> list[Token]:
    """The wrapper's argv with its parameters replaced by what `call` passes."""
    fn = wrapper.fn
    positional = [a.arg for a in fn.args.posonlyargs + fn.args.args]
    if positional and positional[0] in ("self", "cls") and isinstance(call.func, ast.Attribute):
        positional = positional[1:]
    kw = {k.arg: k.value for k in call.keywords if k.arg}
    out: list[Token] = []
    for tok in wrapper.template:
        if not (isinstance(tok, Param) and tok.owner == id(fn)):
            out.append(tok)
            continue
        if fn.args.vararg is not None and tok.name == fn.args.vararg.arg:
            for a in call.args[len(positional) :]:
                if isinstance(a, ast.Starred):
                    inner = mod.tokens(a.value, call)
                    out.extend(
                        inner
                        if inner is not None
                        else [mod._param_token(a.value, call, star=True) or STAR]
                    )
                else:
                    out.append(mod._scalar(a, call))
            continue
        value: ast.expr | None = None
        if tok.name in positional:
            i = positional.index(tok.name)
            if i < len(call.args) and not any(
                isinstance(a, ast.Starred) for a in call.args[: i + 1]
            ):
                value = call.args[i]
        if value is None:
            value = kw.get(tok.name)
        if value is None:
            out.append(tok.default if tok.default is not None else (STAR if tok.star else DYN))
        elif tok.star:
            inner = mod.tokens(value, call)
            out.extend(
                inner if inner is not None else [mod._param_token(value, call, star=True) or STAR]
            )
        else:
            out.append(mod._scalar(value, call))
    return out


def _calls_to(mod: _Module, fn: _Func) -> list[ast.Call]:
    """In-module calls of `fn`, by the spelling that can reach it.

    A METHOD is reached as `<obj>.name(...)`, a module-level or nested function as a bare `name(...)`; matching either spelling for both bound `GitHub.write(method, path, body)` to every `out.write("...")` in publish_ci_verdict (measured 2026-10-06), so the call must also FIT the signature. A function injected as a parameter default (`def apply(..., gh=_gh)`, pr_labels and review_table) is reached as a call through a parameter of that name.
    """
    is_method = isinstance(mod.parent.get(id(fn)), ast.ClassDef)
    injected: list[tuple[_Func, str]] = []
    for other in mod.nodes:
        if not isinstance(other, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        a = other.args
        positional = a.posonlyargs + a.args
        defaults = [None] * (len(positional) - len(a.defaults)) + list(a.defaults)
        pairs = list(zip(positional, defaults, strict=True)) + list(
            zip(a.kwonlyargs, a.kw_defaults, strict=True)
        )
        for arg, default in pairs:
            if isinstance(default, ast.Name) and default.id == fn.name:
                injected.append((other, arg.arg))
    out = []
    for node in mod.nodes:
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        hit = False
        if (is_method and isinstance(f, ast.Attribute) and f.attr == fn.name) or (
            not is_method and isinstance(f, ast.Name) and f.id == fn.name
        ):
            hit = True
        elif isinstance(f, ast.Name) and f.id in {pname for _owner, pname in injected}:
            # The injected runner is THREADED: review_table's `publish(..., gh=_gh)` hands `gh` on to `pr_commits(repo, pr, gh)`, which has no default of its own. So a call through a same-named PARAMETER of any enclosing function counts, not only inside the function that declared the default.
            hit = mod._param_of(f.id, mod.enclosing_funcs(node)) is not None
        if not hit or not _fits(fn, node, drop_self=is_method):
            continue
        if len(mod.funcs_by_name.get(fn.name, [])) > 1 and not _encloses_same_class(mod, node, fn):
            continue
        out.append(node)
    return out


def _fits(fn: _Func, call: ast.Call, *, drop_self: bool) -> bool:
    if any(isinstance(a, ast.Starred) for a in call.args) or any(
        k.arg is None for k in call.keywords
    ):
        return True
    a = fn.args
    positional = [x.arg for x in a.posonlyargs + a.args]
    n_defaults = len(a.defaults)
    if drop_self and positional:
        positional = positional[1:]
    required = positional[: len(positional) - n_defaults] if n_defaults else positional
    if len(call.args) > len(positional) and a.vararg is None:
        return False
    given = set(positional[: len(call.args)]) | {k.arg for k in call.keywords}
    if not all(r in given for r in required):
        return False
    required_kw = [k.arg for k, d in zip(a.kwonlyargs, a.kw_defaults, strict=True) if d is None]
    return all(r in given for r in required_kw)


def _encloses_same_class(mod: _Module, call: ast.Call, fn: _Func) -> bool:
    """For a name defined twice in one module, match a call only to the definition in its own class or scope."""
    fn_owner = mod.parent.get(id(fn))
    return any(a is fn_owner for a in mod.ancestors(call))


def _has_param(tokens: list[Token]) -> Param | None:
    return next((t for t in tokens if isinstance(t, Param)), None)


def scan_source(rel: str, src: str) -> list[Site]:
    """Every `gh` call site in one module. Pure: the selftest and the gate tests drive it with fixture text."""
    if not _MAY_SPAWN_GH.search(src):
        # Nothing this detector can resolve to a gh argv exists without the literal "gh" or a ghx/gh_retry reference, so the parse is skipped. Measured 2026-10-06: 554 modules scanned, 60 survive this filter, and the site count is identical with and without it (174).
        return []
    mod = _Module(
        rel, src
    )  # a SyntaxError propagates: `judge` reports the module as UNPARSEABLE rather than as clean
    sites: list[Site] = []
    funcs: dict[int, _Func] = {
        id(n): n for n in mod.nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def emit(node: ast.AST, tokens: list[Token], route: str, via: str = "") -> None:
        tokens = _settle(tokens)
        if tokens[0] != "gh":
            return  # a caller overrode a defaulted binary: this call does not spawn gh
        kind, verb = classify(tokens)
        qual = mod.qualname_of(node)
        argv = " ".join(t if isinstance(t, str) else "?" for t in tokens)
        sites.append(
            Site(rel, getattr(node, "lineno", 0), qual, kind, verb, route, via or qual, argv)
        )

    # 1. raw spawns: sites, or wrapper seeds.
    pending: list[tuple[ast.Call, list[Token], bool, str]] = []
    for node in mod.nodes:
        if not isinstance(node, ast.Call):
            continue
        api = mod._api_of(node.func)
        if api is not None:
            continue
        toks = mod.gh_argv_of(node)
        if toks is None:
            continue
        pending.append((node, toks, mod.is_guarded(node), mod.qualname_of(node)))

    # 2. the fixpoint: a spawn whose argv still holds a parameter makes its owner a wrapper; every in-module call of that wrapper is resolved in turn.
    # Keyed by (spawn, call), NOT by owning function: one function may hold two parameterised spawns with different verbs, and merging them dropped the second template (caught writing this gate, before any tree run).
    seen: set[tuple[int, int]] = set()
    for _round in range(12):
        nxt: list[tuple[ast.Call, list[Token], bool, str]] = []
        for call, toks, guarded, via in pending:
            p = _has_param(toks)
            if p is None:
                emit(call, toks, "guarded" if guarded else "one-shot", via)
                continue
            w = _Wrapper(funcs[p.owner], toks, guarded)
            callers = [c for c in _calls_to(mod, w.fn) if (id(call), id(c)) not in seen]
            if not callers:
                # A wrapper nothing in this module calls: its verb is unknowable here, so it is reported at its own spawn rather than dropped.
                emit(call, toks, "guarded" if guarded else "one-shot", via)
                continue
            for c in callers:
                seen.add((id(call), id(c)))
                nxt.append((c, _bind(w, c, mod), guarded or mod.is_guarded(c), via))
        if not nxt:
            break
        pending = nxt
    else:
        raise RecursionError("%s: wrapper resolution did not converge in 12 rounds" % rel)

    # 3. the two retry-owning modules, by API.
    for node in mod.nodes:
        api = mod._api_of(node)
        if api is None:
            continue
        modname, fn = api.split(".", 1)
        parent = mod.parent.get(id(node))
        api_call = parent if isinstance(parent, ast.Call) and parent.func is node else None
        if modname == "gh_retry":
            if fn in GH_RETRY_HELPERS and api_call is not None:
                emit(api_call, _api_argv(fn, api_call, mod), "gh_retry")
            continue
        if fn not in GHX_READ_HELPERS:
            continue
        if api_call is None:
            # `runner=ghx.gh` handed to gh_retry is how gh_retry is MEANT to be fed: each attempt is one call.
            if isinstance(parent, ast.keyword) and parent.arg == "runner":
                continue
            emit(node, _api_argv(fn, None, mod), "ghx-by-reference")
            continue
        attempts = next((k.value for k in api_call.keywords if k.arg == "attempts"), None)
        retried = (
            isinstance(attempts, ast.Constant)
            and isinstance(attempts.value, int)
            and attempts.value >= 2
        )
        emit(api_call, _api_argv(fn, api_call, mod), "ghx-retry" if retried else "ghx-one-shot")
    sites.sort(key=lambda s: (s.line, s.verb))
    return sites


@functools.cache
def _scan_memo(rel: str, src: str) -> tuple[Site, ...]:
    """`scan_source`, memoised on the TEXT, so the real-tree plants re-parse only the one module they mutate (5.4 s -> under 2 s per run, 2026-10-06). A tuple, so no caller can mutate a cached result."""
    return tuple(scan_source(rel, src))


def _api_argv(fn: str, call: ast.Call | None, mod: _Module) -> list[Token]:
    if fn == "gh" and call is not None and call.args:
        tail = mod.tokens(call.args[0], call)
        return ["gh", *(tail if tail is not None else [STAR])]
    if fn == "api_json":
        return ["gh", "api", DYN]
    if fn == "secret_names":
        return ["gh", "secret", "list"]
    return ["gh", "pr", "list"]


# ---------------------------------------------------------------------------
# The tree walk and the verdict.
# ---------------------------------------------------------------------------

# THE DEBT, frozen. On 2026-10-06 this gate found ~90 one-shot reads OUTSIDE the plan's twenty modules (the audit's grep missed every `["gh", *args]` wrapper and every multi-line `capture_quiet([` argv). Fixing them is the plan's work, not this gate's, so they are baselined here and the gate fails on GROWTH. Ids hash the site's TEXT (path, function, spawning function, verb, literal argv), never its line, so a move keeps its id
# and a rewrite gets a new one, which is exactly when a human should look again.
BASELINE_REL = ".ci/config/gh-retry-reads-baseline.json"
BASELINE_FORMAT = 1


def is_test_path(rel: str) -> bool:
    parts = rel.split("/")
    name = parts[-1]
    return (
        "tests" in parts[:-1]
        or "test" in parts[:-1]
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def corpus(root: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for scan in SCAN_ROOTS:
        base = root / scan
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            rel = p.relative_to(root).as_posix()
            if (
                "__pycache__" in rel
                or is_test_path(rel)
                or rel in IMPLEMENTATION
                or rel == SELF_REL
            ):
                continue
            out[rel] = p.read_text(encoding="utf-8", errors="replace")
    return out


def load_baseline(path: pathlib.Path) -> dict[str, dict]:
    """id -> {"site": str, "count": int}. A missing or malformed file RAISES: an absent baseline read as empty would turn every frozen debt into a "new" finding, and one read as anything else would excuse what it should not."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("format") != BASELINE_FORMAT
        or not isinstance(data.get("entries"), list)
    ):
        raise ValueError('%s: expected {"format": %d, "entries": [...]}' % (path, BASELINE_FORMAT))
    out: dict[str, dict] = {}
    for e in data["entries"]:
        if not (
            isinstance(e, dict)
            and isinstance(e.get("id"), str)
            and isinstance(e.get("count"), int)
            and e["count"] > 0
        ):
            raise ValueError("%s: malformed entry %r" % (path, e))
        if e["id"] in out:
            raise ValueError("%s: duplicate id %s" % (path, e["id"]))
        out[e["id"]] = {"site": str(e.get("site", "")), "count": e["count"]}
    return out


def baseline_of(sites: list[Site]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for s in sites:
        row = out.setdefault(
            s.stable_id,
            {"site": "%s :: %s via %s :: gh %s" % (s.path, s.qualname, s.via, s.argv), "count": 0},
        )
        row["count"] += 1
    return out


def render_baseline(entries: dict[str, dict]) -> str:
    rows = [
        {"id": k, "site": v["site"], "count": v["count"]}
        for k, v in sorted(entries.items(), key=lambda kv: kv[1]["site"])
    ]
    return json.dumps({"format": BASELINE_FORMAT, "entries": rows}, indent=2) + "\n"


@dataclasses.dataclass
class Verdict:
    modules: int
    sites: list[Site]
    new: list[Site]  # unretried, not allowlisted, not covered by the baseline
    debt: list[Site]  # unretried, covered by the baseline
    excused: list[Site]  # unretried, allowlisted
    drained: list[str]  # baseline rows the tree no longer fills
    problems: list[str]

    def count(self, pred) -> int:
        return sum(1 for s in self.sites if pred(s))


def judge(
    files: dict[str, str], allowed: dict[str, str], baseline: dict[str, dict] | None = None
) -> Verdict:
    baseline = baseline or {}
    sites: list[Site] = []
    problems: list[str] = []
    for rel, src in sorted(files.items()):
        try:
            sites.extend(_scan_memo(rel, src))
        except (SyntaxError, RecursionError) as exc:
            problems.append(
                "UNPARSEABLE %s: %s; its gh calls cannot be judged, so this is not a pass"
                % (rel, exc)
            )
    for key, reason in sorted(allowed.items()):
        if not reason.startswith("BLOCKER:"):
            problems.append("ALLOWED[%r]: the reason must start with 'BLOCKER:'" % key)
            continue
        rejection = allowlist.validate_reason(
            key, reason[len("BLOCKER:") :], "gh_retry_reads.ALLOWED"
        )
        if rejection is not None:
            problems.append(rejection.message)
    unretried = [s for s in sites if s.needs_retry]
    excused = [s for s in unretried if s.key in allowed or s.via_key in allowed]
    live = {k for s in excused for k in (s.key, s.via_key) if k in allowed}
    problems.extend(
        "STALE ALLOWED entry %s: it excuses no unretried gh read on this tree (the read was routed, "
        "moved or deleted). Delete the entry from ALLOWED in %s." % (key, SELF_REL)
        for key in sorted(allowed)
        if key not in live
    )
    rest = [s for s in unretried if s not in excused]
    budget = {k: v["count"] for k, v in baseline.items()}
    new: list[Site] = []
    debt: list[Site] = []
    for s in rest:
        if budget.get(s.stable_id, 0) > 0:
            budget[s.stable_id] -= 1
            debt.append(s)
        else:
            new.append(s)
    drained = sorted("%s (%s)" % (baseline[k]["site"], k) for k, left in budget.items() if left > 0)
    if not files:
        problems.append(
            "VACUOUS: zero modules scanned under %s; the gate is not seeing the tree."
            % ", ".join(SCAN_ROOTS)
        )
    elif not sites:
        problems.append(
            "VACUOUS: zero gh call sites found in %d module(s); the detector is not seeing the spawns."
            % len(files)
        )
    else:
        if not any(s.route == "gh_retry" for s in sites):
            problems.append(
                "VACUOUS: zero reads routed through gh_retry were recognised; the routing detector has rotted."
            )
        if not any(s.kind == "write" for s in sites):
            problems.append(
                "VACUOUS: zero writes classified; the read/write classifier has rotted."
            )
    return Verdict(len(files), sites, new, debt, excused, drained, problems)


FIX = (
    "route it through rediacc_ci.core.gh_retry.gh([...]) (or wrap the spawn in gh_retry.retry_transient), "
    "so a single 5xx is retried and a 4xx still fails at once. Do not add it to the baseline, and do not "
    "add it to ALLOWED unless the read genuinely cannot be retried, and then say why as a BLOCKER."
)


def _describe(s: Site) -> str:
    how = {
        "one-shot": "a one-shot gh %s (no retry)",
        "ghx-one-shot": "a one-shot ghx call, gh %s (attempts defaults to 1)",
        "ghx-by-reference": "a ghx read helper passed by reference, gh %s (it runs with attempts=1)",
    }.get(s.route, "gh %s")
    what = how % s.verb
    if s.via and s.via != s.qualname:
        what += " through %s" % s.via
    if s.kind == "unresolved":
        what += "; the verb is computed, so it is counted as a read"
    return what


# ---------------------------------------------------------------------------
# Controls.
# ---------------------------------------------------------------------------

_FIX_CLEAN = """import subprocess
from rediacc_ci.core import gh_retry, ghx


def labels(sha):
    return gh_retry.gh(["api", "repos/o/r/commits/%s/pulls" % sha]).json()


def tags():
    argv = ["gh", "api", "repos/o/r/tags"]
    return gh_retry.retry_transient(
        lambda: subprocess.run(argv, capture_output=True, check=False),
        lambda r: None if r.returncode == 0 else "x",
    )


def dispatch():
    return subprocess.run(["gh", "workflow", "run", "cd.yml", "-f", "a=b"], check=False)


def cancel(run_id):
    return subprocess.run(["gh", "api", "-X", "POST", "repos/o/r/actions/runs/%s/cancel" % run_id], check=False)


def version():
    return subprocess.run(["gh", "--version"], check=False)
"""

_FIX_WRAPPER = """import subprocess
from rediacc_ci.core import gh_retry


def _gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, check=False)


def _once(args):
    return subprocess.run(["gh", "api", *args], capture_output=True, check=False)


def guarded(path):
    return gh_retry.retry_transient(lambda: _once([path]), lambda r: None)


def read_pr(n):
    return _gh("pr", "view", n, "--json", "labels")


def edit_pr(n):
    return _gh("pr", "edit", n, "--add-label", "x")
"""

_FIX_LOOP = """import subprocess
from rediacc_ci.core import gh_retry


def jobs(run_id):
    for attempt in range(3):
        r = subprocess.run(["gh", "api", "runs/%s/jobs" % run_id], capture_output=True, check=False)
        if r.returncode == 0 or not gh_retry.is_transient(r.stderr):
            return r
    return r
"""

_FIX_BINARY = """import subprocess


def gh_json(argv, binary="gh"):
    return subprocess.run([binary, *argv], capture_output=True, check=False)


def comments(pr):
    return gh_json(["api", "repos/o/r/pulls/%s/comments" % pr])
"""


def _routes(sites: list[Site]) -> list[tuple[str, str, str]]:
    return [(s.qualname, s.kind, s.route) for s in sites]


def selftest() -> bool:
    """True when a control FAILED (the `controls_first` contract)."""
    check = Checker()
    rel = ".ci/rediacc_ci/ci/fixture.py"

    clean = scan_source(rel, _FIX_CLEAN)
    check(
        "CONTROL: a read through gh_retry.gh is routed",
        ("labels", "read", "gh_retry") in _routes(clean),
    )
    check(
        "CONTROL: a raw read inside a retry_transient lambda is guarded",
        ("tags", "read", "guarded") in _routes(clean),
    )
    check(
        "CONTROL: `gh workflow run` is a write", ("dispatch", "write", "one-shot") in _routes(clean)
    )
    check("CONTROL: `gh api -X POST` is a write", ("cancel", "write", "one-shot") in _routes(clean))
    check("CONTROL: `gh --version` is local", ("version", "local", "one-shot") in _routes(clean))
    check("CONTROL: the clean fixture has no finding", not any(s.needs_retry for s in clean))

    oneshot = plant(_FIX_CLEAN, 'return gh_retry.gh(["api",', 'return subprocess.run(["gh", "api",')
    check(
        'PLANT: a one-shot subprocess.run(["gh", "api", ...]) read is a finding',
        [s.qualname for s in scan_source(rel, oneshot) if s.needs_retry] == ["labels"],
    )
    viaghx = plant(_FIX_CLEAN, "return gh_retry.gh(", "return ghx.gh(")
    check(
        "PLANT: a ghx.gh read with attempts defaulting to 1 is a finding",
        [(s.qualname, s.route) for s in scan_source(rel, viaghx) if s.needs_retry]
        == [("labels", "ghx-one-shot")],
    )
    retried_ghx = plant(viaghx, "% sha])", "% sha], attempts=3)")
    check(
        "CONTROL: the same ghx.gh read WITH attempts=3 is routed",
        not any(s.needs_retry for s in scan_source(rel, retried_ghx)),
    )
    unhooked = plant(_FIX_CLEAN, "gh_retry.retry_transient(", "run_once(")
    check(
        "PLANT: the guarded read with retry_transient removed is a finding",
        [s.qualname for s in scan_source(rel, unhooked) if s.needs_retry] == ["tags"],
    )
    write_get = plant(_FIX_CLEAN, '"-X", "POST"', '"-X", "GET"')
    check(
        "PLANT: the POST turned into an explicit GET is a read finding",
        [s.qualname for s in scan_source(rel, write_get) if s.needs_retry] == ["cancel"],
    )

    wrapped = scan_source(rel, _FIX_WRAPPER)
    check(
        "CONTROL: a *args wrapper resolves `pr view` at its caller as a read",
        ("read_pr", "read", "one-shot") in _routes(wrapped),
    )
    check(
        "CONTROL: a *args wrapper resolves `pr edit` at its caller as a write",
        ("edit_pr", "write", "one-shot") in _routes(wrapped),
    )
    check(
        "CONTROL: a wrapper called inside a retry_transient lambda is guarded",
        ("guarded", "read", "guarded") in _routes(wrapped),
    )
    check(
        "CONTROL: the wrapper fixture has exactly one finding, read_pr",
        [s.qualname for s in wrapped if s.needs_retry] == ["read_pr"],
    )

    loop = scan_source(rel, _FIX_LOOP)
    check(
        "CONTROL: a hand loop that consults is_transient is guarded",
        _routes(loop) == [("jobs", "read", "guarded")],
    )
    noloop = plant(_FIX_LOOP, "gh_retry.is_transient(r.stderr)", "False")
    check(
        "PLANT: the same loop without is_transient is a finding",
        [s.qualname for s in scan_source(rel, noloop) if s.needs_retry] == ["jobs"],
    )

    binary = scan_source(rel, _FIX_BINARY)
    check(
        'CONTROL: a `[binary, *argv]` spawn with binary defaulting to "gh" is seen',
        _routes(binary) == [("comments", "read", "one-shot")],
    )

    check(
        "CLASSIFY: gh api with -f and no method is a write",
        classify(["gh", "api", "x", "-f", "a=b"])[0] == "write",
    )
    check(
        "CLASSIFY: gh api -X GET with -f is a read",
        classify(["gh", "api", "-X", "GET", "x", "-f", "a=b"])[0] == "read",
    )
    check(
        "CLASSIFY: gh api graphql with a query is a read",
        classify(["gh", "api", "graphql", "-f", "query=query{a}"])[0] == "read",
    )
    check(
        "CLASSIFY: gh api graphql with a mutation is a write",
        classify(["gh", "api", "graphql", "-f", "query=mutation{a}"])[0] == "write",
    )
    check(
        "CLASSIFY: gh release view is a read",
        classify(["gh", "release", "view", "v1"]) == ("read", "release view"),
    )
    check(
        "CLASSIFY: gh release upload is a write",
        classify(["gh", "release", "upload", "v1"])[0] == "write",
    )
    check(
        "CLASSIFY: gh label create is a write",
        classify(["gh", "label", "create", "x"])[0] == "write",
    )
    check("CLASSIFY: gh run rerun is a write", classify(["gh", "run", "rerun", "1"])[0] == "write")
    check("CLASSIFY: gh pr merge is a write", classify(["gh", "pr", "merge", "1"])[0] == "write")
    check(
        "CLASSIFY: a computed verb is unresolved, never a write",
        classify(["gh", STAR])[0] == "unresolved",
    )
    check(
        "CLASSIFY: a computed -X method is unresolved",
        classify(["gh", "api", "-X", DYN, "x"])[0] == "unresolved",
    )

    stale = judge(
        {rel: _FIX_CLEAN},
        {rel + "::nothing": "BLOCKER: a reason long enough to pass the thirty character floor"},
    )
    check(
        "LIVENESS: an ALLOWED entry that excuses nothing is STALE",
        any("STALE" in p for p in stale.problems),
    )
    lazy = judge({rel: oneshot}, {rel + "::labels": "BLOCKER: tbd"})
    check("ALLOWED: a low-effort BLOCKER reason is rejected", bool(lazy.problems))
    excused = judge(
        {rel: oneshot},
        {rel + "::labels": "BLOCKER: a fixture read that stands for a verified fail-closed caller"},
    )
    check(
        "ALLOWED: a reasoned entry excuses its site and stays visible",
        not excused.new and len(excused.excused) == 1,
    )
    by_wrapper = judge(
        {rel: _FIX_WRAPPER},
        {
            rel
            + "::_gh": "BLOCKER: a fixture wrapper standing for one that carries its own retry loop"
        },
    )
    check(
        "ALLOWED: an entry naming the spawning WRAPPER excuses the reads routed through it",
        not by_wrapper.new and [x.qualname for x in by_wrapper.excused] == ["read_pr"],
    )
    check(
        "VACUITY: zero modules is a problem",
        any("zero modules" in p for p in judge({}, {}).problems),
    )
    check(
        "VACUITY: zero call sites is a problem",
        any("zero gh call sites" in p for p in judge({rel: "x = 1\n"}, {}).problems),
    )
    check(
        "VACUITY: an unparseable module is a problem, never a clean module",
        any(
            "UNPARSEABLE" in p
            for p in judge({rel: 'def (:\n    argv = ["gh", "api"]\n'}, {}).problems
        ),
    )

    # The shrink-only baseline, both directions, and the id's two promises.
    frozen = baseline_of([x for x in scan_source(rel, oneshot) if x.needs_retry])
    check("BASELINE: a frozen finding is debt, not new", not judge({rel: oneshot}, {}, frozen).new)
    grown = plant(
        oneshot,
        "def tags():",
        'def more():\n    return subprocess.run(["gh", "api", "repos/o/r/branches"])\n\n\ndef tags():',
    )
    check(
        "BASELINE: a SECOND one-shot read beside the frozen one is new",
        [x.qualname for x in judge({rel: grown}, {}, frozen).new] == ["more"],
    )
    check(
        "BASELINE: a frozen finding that was fixed is reported as drained",
        bool(judge({rel: _FIX_CLEAN}, {}, frozen).drained),
    )
    moved = plant(oneshot, "import subprocess\n", "import subprocess\n\n\nPADDING = 1\n")
    check(
        "BASELINE: the id survives the site moving down the file",
        not judge({rel: moved}, {}, frozen).new,
    )
    rewritten = plant(oneshot, "/commits/%s/pulls", "/commits/%s/check-runs")
    check(
        "BASELINE: the id does NOT survive the argv being rewritten",
        bool(judge({rel: rewritten}, {}, frozen).new),
    )
    check(
        "BASELINE: --write-baseline refuses an addition",
        bool(
            baseline_additions(
                frozen,
                baseline_of(
                    judge({rel: grown}, {}, frozen).new + judge({rel: grown}, {}, frozen).debt
                ),
            )
        ),
    )

    if check.count < 40:
        print("  FAIL  only %d selftest control(s) ran" % check.count, file=sys.stderr)
        return True
    return not check.ok


def baseline_additions(old: dict[str, dict], new: dict[str, dict]) -> list[str]:
    """Rows in `new` that `old` does not cover. A drain must leave this EMPTY: a shrinking total says nothing about composition, and a fresh violation enshrined by a drain that also removed thirty old ones still prints a smaller number."""
    out = []
    for k, v in sorted(new.items()):
        before = old.get(k, {}).get("count", 0)
        if v["count"] > before:
            out.append("%s (%s): %d -> %d" % (v["site"], k, before, v["count"]))
    return out


def real_tree_plants(
    files: dict[str, str], allowed: dict[str, str], baseline: dict[str, dict], clean_new: int
) -> list[str]:
    """Plant into REAL module text, in memory, and demand each plant add a NEW finding. Returns failures."""
    failures: list[str] = []
    routed = next((r for r, s in sorted(files.items()) if "gh_retry.gh([" in s), None)
    guarded = next(
        (
            r
            for r, s in sorted(files.items())
            if "gh_retry.retry_transient(\n        lambda: subprocess.run(" in s
        ),
        None,
    )
    for label, rel, old, new in (
        # A raw spawn and not `ghx.gh(`: a module that never imports ghx would leave `ghx.gh` unresolvable (and a NameError at run time), so that plant fails to fire for a reason that has nothing to do with the gate. Measured 2026-10-06 on ci/detect_pointer_bump.py.
        (
            "a gh_retry.gh read demoted to a one-shot subprocess.run",
            routed,
            "gh_retry.gh([",
            'subprocess.run(["gh", ',
        ),
        (
            "a guarded raw spawn with retry_transient unhooked",
            guarded,
            "gh_retry.retry_transient(\n        lambda: subprocess.run(",
            "run_once(\n        lambda: subprocess.run(",
        ),
    ):
        if rel is None:
            failures.append(
                "REAL-TREE PLANT could not find a module to plant %s into; the corpus no longer has the shape"
                % label
            )
            continue
        mutated = dict(files)
        mutated[rel] = plant(files[rel], old, new, count=1)
        got = len(judge(mutated, allowed, baseline).new)
        if got <= clean_new:
            failures.append(
                "REAL-TREE PLANT did not red: %s in %s left %d new finding(s)" % (label, rel, got)
            )
        else:
            print("  plant fired: %s in %s (%d -> %d new findings)" % (label, rel, clean_new, got))
    return failures


def _shape(v: Verdict) -> str:
    return (
        "%d module(s), %d gh call site(s): %d read(s) [%d gh_retry, %d ghx retry, %d retry-guarded raw, %d unresolved], "
        "%d write(s), %d local; unretried: %d allowlisted in %d entr%s, %d baselined debt, %d new"
        % (
            v.modules,
            len(v.sites),
            v.count(lambda s: s.kind in ("read", "unresolved")),
            v.count(lambda s: s.route == "gh_retry" and s.kind != "write"),
            v.count(lambda s: s.route == "ghx-retry"),
            v.count(lambda s: s.route == "guarded" and s.kind != "write"),
            v.count(lambda s: s.kind == "unresolved"),
            v.count(lambda s: s.kind == "write"),
            v.count(lambda s: s.kind == "local"),
            len(v.excused),
            len(ALLOWED),
            "y" if len(ALLOWED) == 1 else "ies",
            len(v.debt),
            len(v.new),
        )
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="check_gh_retry_reads.py", description=__doc__.splitlines()[0]
    )
    ap.add_argument("--selftest", action="store_true", help="run the controls only")
    ap.add_argument(
        "--root", default=None, help="scan this tree instead of the repository (gate tests)"
    )
    ap.add_argument("--quiet-writes", action="store_true", help="omit the per-site write lines")
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="DRAIN the baseline to the current debt; refuses any addition",
    )
    ap.add_argument(
        "--init-baseline", action="store_true", help="create the baseline when none exists (once)"
    )
    args = ap.parse_args(argv)

    rc = controls_first(NAME, selftest)
    if rc:
        return rc
    if args.selftest:
        print("selftest: every control passed")
        return 0

    root = pathlib.Path(args.root).resolve() if args.root else paths.repo_root()
    files = corpus(root)
    baseline_path = root / BASELINE_REL

    if args.init_baseline or args.write_baseline:
        return _write_baseline(files, baseline_path, init=args.init_baseline)

    try:
        baseline = load_baseline(baseline_path)
    except (OSError, ValueError) as exc:
        print(
            "✗ cannot read the baseline %s: %s. It must exist (an empty `entries` list when the debt is drained)."
            % (BASELINE_REL, exc),
            file=sys.stderr,
        )
        return 1
    v = judge(files, ALLOWED, baseline)

    if files and v.sites:
        plant_failures = real_tree_plants(files, ALLOWED, baseline, len(v.new))
        if plant_failures:
            for f in plant_failures:
                print("✗ %s" % f, file=sys.stderr)
            return 2

    if not args.quiet_writes:
        for s in v.sites:
            if s.kind == "write":
                print(
                    "  info: write  %s:%d %s: gh %s (never retried, by design)"
                    % (s.path, s.line, s.qualname, s.verb)
                )
    for s in v.excused:
        reason = ALLOWED.get(s.key) or ALLOWED[s.via_key]
        print("  EXEMPT %s:%d %s: %s -- %s" % (s.path, s.line, s.qualname, _describe(s), reason))
    per_module: dict[str, int] = {}
    for s in v.debt:
        per_module[s.path] = per_module.get(s.path, 0) + 1
    for path, n in sorted(per_module.items()):
        print("  DEBT   %s: %d one-shot read(s) frozen in %s" % (path, n, BASELINE_REL))

    for s in v.new:
        print(
            "%s:%d: %s: %s. Fix: %s" % (s.path, s.line, s.qualname, _describe(s), FIX),
            file=sys.stderr,
        )
    for d in v.drained:
        print(
            "✗ DRAINED baseline row, the read is gone or retried now: %s. Run `%s --write-baseline` to shrink the baseline."
            % (d, "check_gh_retry_reads.py"),
            file=sys.stderr,
        )
    for p in v.problems:
        print("✗ %s" % p, file=sys.stderr)
    shape = _shape(v)
    if v.new or v.drained or v.problems:
        print("✗ %s" % shape, file=sys.stderr)
        return 1
    print("✓ %s" % shape)
    return 0


def _write_baseline(files: dict[str, str], path: pathlib.Path, *, init: bool) -> int:
    if init and path.exists():
        print(
            "✗ %s exists; --init-baseline creates it once. Drain with --write-baseline." % path,
            file=sys.stderr,
        )
        return 1
    old: dict[str, dict] = {}
    if not init:
        try:
            old = load_baseline(path)
        except (OSError, ValueError) as exc:
            print("✗ cannot read %s: %s" % (path, exc), file=sys.stderr)
            return 1
    v = judge(files, ALLOWED, old)
    if v.problems:
        for p in v.problems:
            print("✗ %s" % p, file=sys.stderr)
        print("✗ refusing to write a baseline over a tree with problems", file=sys.stderr)
        return 1
    new = baseline_of(v.new + v.debt)
    if not init:
        added = baseline_additions(old, new)
        if added:
            for a in added:
                print("✗ ADDED %s" % a, file=sys.stderr)
            print(
                "✗ refusing: a drain may only REMOVE rows. Fix the %d read(s) above (route them through gh_retry); "
                "do not add them to the baseline." % len(added),
                file=sys.stderr,
            )
            return 1
    removed = sorted(set(old) - set(new)) + sorted(
        k for k in new if k in old and new[k]["count"] < old[k]["count"]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_baseline(new), encoding="utf-8")
    print(
        "✓ wrote %s: %d row(s), %d site(s); ADDED 0, REMOVED/SHRUNK %d"
        % (path, len(new), sum(r["count"] for r in new.values()), len(removed) if not init else 0)
    )
    for k in removed:
        print("  removed %s" % old[k]["site"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
