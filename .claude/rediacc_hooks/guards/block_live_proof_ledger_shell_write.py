"""Refuse a Bash command that writes the live-proof ledger, `agent/ledgers/live-proof.jsonl`, by any route but the recorder.

WHY. The pre-bash half of `block_live_proof_ledger_write` (agent/plans/PLAN-tested-on-bench.md box V10): the Edit/Write tools are refused there, so the same hand write through the shell is refused here. The one sanctioned writer is `python3 -m rediacc_ci.ops.live_proof record --write`, a module run whose words name no ledger path, so it passes without an exception list; a redirect
added to that same command is still refused.

WHAT COUNTS AS A WRITE, read by the lexer (`shellscan`) and never by a regex over the raw text, so `cat`, `jq`, `grep`, `git diff`, `git add` and a commit message naming the ledger all pass:
  - an output redirection (`>`, `>>`, `>|`) whose target lands on the ledger, as typed and as bash expands it;
  - `tee`, an in-place `sed`/`perl`, `truncate`, `dd of=` or `rm` naming it, and a copier (`cp`, `mv`, `install`, `rsync`, `ln`) whose destination lands on it (`shellscan.copy_landings`, so a copy into `agent/ledgers/` of a file named `live-proof.jsonl` counts);
  - any other command's output word (`shellscan.output_landings`): an output option of a listed reader (`sort -o`), or any word of a command that table does not list as a reader (`touch`, `rm`);
  - interpreter code: a Python program whose write targets, or whose appending calls (`append_lines`, `.write`, `json.dump`), name the ledger, a call of `ledger_path`, or the `LEDGER` constant; other interpreters, and Python that does not parse, by a line that names the ledger beside write code. A program that imports the recorder and passes `write=True`,
    or calls its `_judge_and_write`, is refused too: an in-process `record(..., world=World(run=<fake>))` would append a VERIFIED row for steps that never ran.

WHERE A WORD LANDS is read on disk as well as in text: each word is joined to the directory its run executes in (`shellscan.write_directory`) and resolved through symlinks, and a word with a glob is expanded there, so `cd agent/ledgers && echo x >> live-proof.jsonl`, `echo x >> agent/ledgers/live-pr*.jsonl` and a link to the ledger are each the ledger.

SEARCHED TEXT IS NOT A PATH (worklist #4e20f8c5, 2026-10-28). A heredoc that read `agent/plans/PLAN-backup-program.md`, replaced an Owns line naming the ledger and wrote the PLAN back was refused: the replaced string ended in the ledger's name, so `s = s.replace(old, new)` bound `s` to "the ledger", and the next `s.replace(...)` read as a write into it. Two readings changed. The text a call SEARCHES FOR (`str.replace`'s first argument, `removeprefix`/`removesuffix`'s, `re.sub`'s pattern) is removed from the result, so it never makes a name the ledger; the replacement and the receiver still do, so `Path(t.replace('X', '<ledger>')).write_text(...)` is refused. And `str.replace(old, new)`, `removeprefix` and `removesuffix` are string methods, not file writes, so their receiver is not a write target (Path's one-argument `replace` still is).

A READ IS NOT A PATH (worklist #9efac135, 2026-11-08). Bindings are read without scope, so `lines = Path(<ledger>).read_text()` in one function marked `lines` as the ledger, every name built from it followed, and an `out.append(...)` growing an unrelated list of the same name in another function read as a ledger write: every command running a changed `check_plan_citations.py` (its receipt-id read) was refused, `sed -i` on a PLAN chained before it included. A read's value (`read_text`, `read`, `readlines`, `json.load`, `exists`, a read-only `open`) now carries the rows, never the path; an `open` in a write mode, or with a mode in a variable, still carries it. And a stdin program is every heredoc body of the command joined (`shellscan.interpreter_program`), so a `cat > msg <<'EOF'` beside a Python heredoc never parsed and fell to the line reading: a PLAN write whose content named the ledger was refused, and a heredoc writing the ledger through a name bound on an earlier line was allowed. When the joined text does not parse, each body is judged on its own (`_programs`).

A NAME IS ITS OWN SCOPE'S (worklist #b4bb4a4e, 2026-11-09). #9efac135 kept a read from carrying the path, but bindings were still read without scope: in `test-block_vm_unverified_push.py` one function bound `path = Path(root) / LEDGER` and only read it, `transcript()` wrote its own local `path`, and every run of that harness was refused. A name now resolves the way the compiler resolves it (`_Scopes`): a scope is the module, a function or lambda, a class body or a comprehension; a name a scope binds (assignment, walrus, `for`/`with`/`except`/`import` target, parameter, `def`/`class` name) is local to it unless declared `global` or `nonlocal`; a use reads the nearest scope outward that holds it, class bodies skipped, the module last. A ledger binding written in the same function, a module binding written inside a function, a closure's, a `global`'s and a `nonlocal`'s are still the ledger, and a parameter's default is now its value, so `def f(p='<ledger>')` writing `p` is refused where it was allowed.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_live_proof_ledger_shell_write.py` beside it and against its own DEFECT, never against a golden.
"""

import ast
import glob
import os
import re

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import block_live_proof_ledger_write as EDIT

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 65

# The landing test is the whole guard: with it gone no word is ever the ledger.
DEFECT = ("    if not word:\n        return False", "    if True:\n        return False")

LEDGER_REL = EDIT.LEDGER_REL
LEDGER_PATH = EDIT.LEDGER_PATH
LEDGER_NAME = "live-proof.jsonl"
INTERPRETERS = shellscan.INTERPRETER_NAMES
_PATH_MAX = 4096
_GLOB = frozenset("*?[")

# Code that opens a file for writing, appends to one, replaces or removes one (the review-file guard's reading plus the append verbs this ledger is written with).
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|\.open\(\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|O_WRONLY|O_RDWR|O_APPEND|O_CREAT|O_TRUNC"
    r"|write_text|write_bytes|append_lines|os\.replace|os\.rename|shutil\.(copy|move)|unlink|writeFileSync|appendFileSync|>>"
)
# A Python call whose name says it writes; one whose argument holds the ledger is a write to it. `dumps` (`json.dumps`, `pickle.dumps`) returns text and writes nothing, so it is not one (review 22b7a40c.3).
_WRITE_CALL = re.compile(
    r"(?i)(write|append|dump(?!s)|save|copy|move|replace|rename|unlink|remove|truncate)"
)
_PATH_KEYWORDS = frozenset(("path", "file", "dst", "dest", "target", "filename"))
_TWO_PATH_CALLS = frozenset(
    (
        "replace",
        "rename",
        "renames",
        "move",
        "copy",
        "copy2",
        "copyfile",
        "copytree",
        "link",
        "symlink",
    )
)
# Driving the recorder in-process with its write switch on, or its writing step directly.
RECORDER_MODULE = re.compile(r"\blive_proof\b")
RECORDER_WRITE = re.compile(r"\bwrite\s*=\s*True\b|_judge_and_write|\bjsonl_append\b")

MESSAGE = (
    "BLOCKED: this command writes the live-proof ledger by hand (%s).\n"
    "\n"
    "CI trusts agent/ledgers/live-proof.jsonl without re-running anything, so a row is written\n"
    "only by the recorder, after the live run it describes; a hand-written row with a recomputed\n"
    "id is the forgery this guard exists to stop.\n"
    "\n"
    "  record a receipt:  " + EDIT.RECORDER + "\n"
    "  judge the ledger:  PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify\n"
)

EDGE_CASES = [
    ("append a row", "echo '{}' >> " + LEDGER_REL),
    # #4e20f8c5: the refused PLAN edit. The ledger's path is text being replaced inside the PLAN, and the PLAN is the file written.
    (
        "python edits a PLAN line naming the ledger",
        "python3 - <<'PY'\nimport pathlib\np = pathlib.Path('agent/plans/PLAN-backup-program.md')\n"
        "s = p.read_text()\ns = s.replace('Owns: x, "
        + LEDGER_REL
        + "', 'Owns: x')\np.write_text(s)\nPY",
    ),
    ("the recorder", "PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --write"),
    ("read the ledger", "jq . " + LEDGER_REL),
    ("tee the ledger", "printf x | tee -a " + LEDGER_REL),
    ("stage the ledger", "git add -- " + LEDGER_REL),
]


def _base(where, cwd):
    """The absolute directory a run in `where` (`shellscan.write_directory`'s answer) executes in, or None when the hook's own directory is not an absolute path."""
    if not cwd or not os.path.isabs(str(cwd)):
        return None
    return os.path.join(str(cwd), str(where)) if where else str(cwd)


def _is_ledger(word, base=None):
    """Does `word`, as text or resolved on disk from the absolute directory `base` (symlinks followed, a glob expanded), land on the live-proof ledger?"""
    if not word:
        return False
    if len(word) > _PATH_MAX or "\n" in word or "\0" in word:
        return False
    if LEDGER_PATH.search(word.replace("\\", "/")):
        return True
    if not base:
        return False
    joined = os.path.join(base, word)
    try:
        candidates = glob.glob(joined) if _GLOB & set(word) else [joined]
        landed = [os.path.realpath(c) for c in candidates]
    except (OSError, ValueError, RecursionError):
        return False
    return any(LEDGER_PATH.search(p.replace("\\", "/")) for p in landed)


def _operands(argv):
    return [a for a in argv if not (a.startswith("-") and len(a) > 1)]


def _operand_write(run, name, argv, base):
    """A description of the ledger write `run` makes through one of its own operands (tee, sed/perl -i, truncate, dd of=, rm), or ""."""
    operands = shellscan.xargs_fed_operands(run, _operands(argv))
    if name == "tee" and any(_is_ledger(a, base) for a in operands):
        return "tee into the ledger"
    edit = shellscan.in_place_edit(run)
    if edit is not None and any(_is_ledger(f, base) for f in [*edit[1], *operands]):
        return "%s -i on the ledger" % name
    if name == "truncate" and any(_is_ledger(a, base) for a in operands):
        return "truncate of the ledger"
    if name == "dd" and any(a.startswith("of=") and _is_ledger(a[3:], base) for a in argv):
        return "dd of= the ledger"
    if name in ("rm", "unlink", "shred") and any(_is_ledger(a, base) for a in operands):
        return "%s of the ledger" % name
    return ""


def _searched_text(node):
    """The arguments of a string call that are SEARCHED FOR and removed, never carried into its result: `str.replace`'s old text (two or more arguments; Path's `replace` takes one), `removeprefix`/`removesuffix`'s affix, and `re.sub`/`re.subn`'s pattern."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or not node.args:
        return ()
    attr = node.func.attr
    if attr == "replace" and len(node.args) >= 2:
        return (node.args[0],)
    if attr in ("removeprefix", "removesuffix"):
        return (node.args[0],)
    module = node.func.value
    if attr in ("sub", "subn") and isinstance(module, ast.Name) and module.id == "re":
        return (node.args[0],)
    return ()


# Calls whose value is what a file HOLDS, or a fact about it, never a handle that writes it (#9efac135).
_READ_CALLS = frozenset(
    (
        "read_text",
        "read_bytes",
        "read",
        "readline",
        "readlines",
        "exists",
        "is_file",
        "is_dir",
        "stat",
        "getsize",
        "load",
        "loads",
    )
)


def _read_only_open(call):
    """An `open` (builtin, `io.open`, `Path.open`) whose mode is a constant naming no write (`w`, `a`, `x`, `+`), or absent. `os.open(path, flags)` and a mode held in a variable are not."""
    func = call.func
    if _call_name(func) != "open":
        return False
    if (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "os"
    ):
        return False
    path_method = isinstance(func, ast.Attribute) and not (
        isinstance(func.value, ast.Name) and func.value.id in ("io", "builtins", "codecs")
    )
    position = 0 if path_method else 1
    if any(k.arg is None for k in call.keywords):
        return False  # `**kwargs` may carry a write mode (review 9d3a7308.2)
    mode = next((k.value for k in call.keywords if k.arg == "mode"), None)
    if mode is None and len(call.args) > position:
        mode = call.args[position]
    if mode is None:
        return True
    return (
        isinstance(mode, ast.Constant)
        and isinstance(mode.value, str)
        and not set(mode.value) & set("wax+")
    )


def _read_value(node):
    """Is `node` a call whose value is content read from a file (`_READ_CALLS`, a read-only `open`)? Its path stays behind: `lines = Path(<ledger>).read_text()` binds `lines` to the rows, so `out.append(line)` later is a list growing, not a ledger write (#9efac135: every command running a changed `check_plan_citations.py` was refused for its receipt-id read)."""
    return isinstance(node, ast.Call) and (
        _call_name(node.func) in _READ_CALLS or _read_only_open(node)
    )


def _flow(expr):
    """`ast.walk`, minus the subtrees a call searches for (`_searched_text`) and the path inside a read (`_read_value`): text that cannot reach the expression's value as a path."""
    stack = [expr]
    while stack:
        node = stack.pop()
        yield node
        if _read_value(node):
            # The path inside a read stays behind, but a write-capable open nested in it,
            # as in `open(<ledger>, 'a').read()`, is still walked (review 9d3a7308.1).
            stack.extend(
                c
                for c in ast.walk(node)
                if c is not node
                and isinstance(c, ast.Call)
                and _call_name(c.func) == "open"
                and not _read_only_open(c)
            )
            continue
        skip = _searched_text(node)
        stack.extend(c for c in ast.iter_child_nodes(node) if not any(c is s for s in skip))


def _string_edit(call):
    """A string method whose name merely sounds like a file write: `str.replace(old, new)` (Path's `replace` takes one argument), `removeprefix`, `removesuffix`. Its receiver is text being edited, not a write target."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if isinstance(func.value, ast.Name) and func.value.id in ("os", "shutil"):
        return False
    return (func.attr == "replace" and len(call.args) + len(call.keywords) >= 2) or func.attr in (
        "removeprefix",
        "removesuffix",
    )


_FUNCTION_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _names_in(target):
    """The Name nodes of an assignment target, never those inside a lambda or comprehension nested in it (they belong to that scope)."""
    stack = [target]
    while stack:
        node = stack.pop()
        if isinstance(node, ast.Name):
            yield node
        elif not isinstance(node, (*_FUNCTION_SCOPES, *_COMPREHENSIONS)):
            stack.extend(ast.iter_child_nodes(node))


class _Scopes:
    """Where each Python name is bound, read the way the compiler reads it (#b4bb4a4e).

    A scope is the module, a function or lambda, a class body or a comprehension. A name is local to a scope when the scope binds it (an assignment or walrus target, a `for`/`with`/`except`/`import` name, a parameter, a `def`/`class` name) and does not declare it `global` or `nonlocal`; a use resolves to the nearest scope, outward, that holds it locally, skipping class bodies the way a method does, and to the module when none does. `key(name)` is `(scope, identifier)`, so `path` in one function and `path` in another are two names.
    """

    def __init__(self, tree):
        self.parent = {0: None}
        self.is_class = {0: False}
        self.is_comp = {0: False}
        self.local: dict = {0: set()}
        self.globals: dict = {0: set()}
        self.nonlocals: dict = {0: set()}
        self.scope_of: dict = {}
        self.bindings: list = []  # (scope, identifier, value expression or None)
        self._next = 1
        self._visit(tree, 0)

    def _new(self, parent, is_class=False, is_comp=False):
        scope = self._next
        self._next += 1
        self.parent[scope] = parent
        self.is_class[scope] = is_class
        self.is_comp[scope] = is_comp
        self.local[scope] = set()
        self.globals[scope] = set()
        self.nonlocals[scope] = set()
        return scope

    def _bind(self, scope, name, value):
        self.local[scope].add(name)
        self.bindings.append((scope, name, value))

    def _target(self, target, scope, value):
        """Each name a target stores binds `value` in `scope`; a name it only reads (`d[k] = v`'s `d` and `k`) is a container receiving the value, so it is tainted where it resolves, and stays non-local."""
        for n in _names_in(target):
            self.scope_of[id(n)] = scope
            if isinstance(n.ctx, ast.Store):
                self._bind(scope, n.id, value)
            else:
                self.bindings.append((None, n, value))
        self._visit_children(target, scope, skip_names=True)

    def _visit_children(self, node, scope, skip_names=False):
        for child in ast.iter_child_nodes(node):
            if skip_names and isinstance(child, ast.Name):
                continue
            self._visit(child, scope)

    def _function(self, node, scope):
        args = node.args
        decorators = getattr(node, "decorator_list", [])
        for d in [*decorators, *args.defaults, *(d for d in args.kw_defaults if d)]:
            self._visit(d, scope)
        if not isinstance(node, ast.Lambda):
            for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
                if a is not None and a.annotation is not None:
                    self._visit(a.annotation, scope)
            if node.returns is not None:
                self._visit(node.returns, scope)
            self._bind(scope, node.name, None)
        inner = self._new(scope)
        positional = [*args.posonlyargs, *args.args]
        defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
        pairs = [
            *zip(positional, defaults, strict=True),
            *zip(args.kwonlyargs, args.kw_defaults, strict=True),
        ]
        for a, d in pairs:
            self._bind(inner, a.arg, d)
        for a in (args.vararg, args.kwarg):
            if a is not None:
                self._bind(inner, a.arg, None)
        body = [node.body] if isinstance(node, ast.Lambda) else node.body
        for stmt in body:
            self._visit(stmt, inner)

    def _comprehension(self, node, scope):
        """The first iterable is evaluated outside (`[... for p in X]`'s `X`); the targets, the conditions, the later iterables and the element inside."""
        inner = self._new(scope, is_comp=True)
        for i, gen in enumerate(node.generators):
            self._visit(gen.iter, scope if i == 0 else inner)
            self._target(gen.target, inner, gen.iter)
            for cond in gen.ifs:
                self._visit(cond, inner)
        elements = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        for e in elements:
            self._visit(e, inner)

    def _walrus_scope(self, scope):
        """A walrus inside a comprehension binds in the nearest enclosing scope that is not one (PEP 572)."""
        while self.is_comp[scope] and self.parent[scope] is not None:
            scope = self.parent[scope]
        return scope

    def _visit(self, node, scope):
        if isinstance(node, _FUNCTION_SCOPES):
            self._function(node, scope)
        elif isinstance(node, ast.ClassDef):
            for d in [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]:
                self._visit(d, scope)
            self._bind(scope, node.name, None)
            inner = self._new(scope, is_class=True)
            for stmt in node.body:
                self._visit(stmt, inner)
        elif isinstance(node, _COMPREHENSIONS):
            self._comprehension(node, scope)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if node.value is not None:
                self._visit(node.value, scope)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if node.value is None:
                    self._visit(t, scope)
                else:
                    self._target(t, scope, node.value)
            if isinstance(node, ast.AnnAssign):
                self._visit(node.annotation, scope)
        elif isinstance(node, ast.NamedExpr):
            self._visit(node.value, scope)
            owner = self._walrus_scope(scope)
            self.scope_of[id(node.target)] = owner
            self._bind(owner, node.target.id, node.value)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self._visit(node.iter, scope)
            self._target(node.target, scope, node.iter)
            for stmt in [*node.body, *node.orelse]:
                self._visit(stmt, scope)
        elif isinstance(node, ast.withitem):
            self._visit(node.context_expr, scope)
            if node.optional_vars is not None:
                self._target(node.optional_vars, scope, node.context_expr)
        elif isinstance(node, ast.ExceptHandler):
            if node.type is not None:
                self._visit(node.type, scope)
            if node.name:
                self._bind(scope, node.name, None)
            for stmt in node.body:
                self._visit(stmt, scope)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name != "*":
                    self._bind(scope, (a.asname or a.name).split(".")[0], None)
        elif isinstance(node, ast.Global):
            self.globals[scope].update(node.names)
        elif isinstance(node, ast.Nonlocal):
            self.nonlocals[scope].update(node.names)
        else:
            if isinstance(node, ast.Name):
                self.scope_of[id(node)] = scope
            self._visit_children(node, scope)

    def _enclosing(self, scope):
        """The scopes a free name in `scope` is looked up in next: outward, class bodies skipped."""
        scope = self.parent[scope]
        while scope is not None and self.is_class[scope]:
            scope = self.parent[scope]
        return scope

    def resolve(self, scope, name):
        """The scope whose binding of `name` a use in `scope` reads: a `global` declaration answers the module, a `nonlocal` one the nearest enclosing function holding it, a local binding the scope itself, and otherwise the enclosing scopes outward, the module last."""
        if scope is None or name in self.globals[scope]:
            return 0
        if name in self.nonlocals[scope]:
            scope = self._enclosing(scope)
            while scope not in (None, 0) and name not in self.local[scope]:
                scope = self._enclosing(scope)
            return scope or 0
        if name in self.local[scope]:
            return scope
        scope = self._enclosing(scope)
        while scope is not None:
            if name in self.local[scope]:
                return scope
            scope = self._enclosing(scope)
        return 0

    def key(self, node):
        """`(scope, identifier)` of the binding a Name node reads or stores; a node this walk never placed (none should exist) resolves from the module."""
        return (self.resolve(self.scope_of.get(id(node), 0), node.id), node.id)

    def bound(self):
        """`{(scope, identifier): [value expression, ...]}`, each binding's value under the scope that holds it (a `global`/`nonlocal` declaration moves it outward)."""
        out: dict = {}
        for scope, name, value in self.bindings:
            # A scope of None is a name a target reads: the container receiving the value.
            k = self.key(name) if scope is None else (self.resolve(scope, name), name)
            if value is not None:
                out.setdefault(k, []).append(value)
            else:
                out.setdefault(k, [])
        return out


_FOLD_DEPTH = 32


def _fold(node, consts, depth=0, key=None):
    """The string a Python expression evaluates to when it is built only from string constants, `+`, an f-string of those, and names bound once to such an expression (`consts`); None otherwise. `'agent/ledgers/live-proof' + '.jsonl'` names the ledger as surely as the one literal does (review 22b7a40c.2)."""
    if depth > _FOLD_DEPTH:
        return None
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _fold(node.left, consts, depth + 1, key)
        right = _fold(node.right, consts, depth + 1, key) if left is not None else None
        return None if right is None else left + right
    if isinstance(node, ast.JoinedStr):
        out = []
        for v in node.values:
            inner = v.value if isinstance(v, ast.FormattedValue) else v
            if isinstance(v, ast.FormattedValue) and (
                v.format_spec or v.conversion not in (-1, 115)
            ):
                return None
            piece = _fold(inner, consts, depth + 1, key)
            if piece is None:
                return None
            out.append(piece)
        return "".join(out)
    if isinstance(node, ast.Name):
        return consts.get(key(node) if key else node.id)
    return None


def _string_constants(bound, key=None):
    """`{name: text}` for each name (a `_Scopes.key` when `key` is given) bound exactly once, to an expression `_fold` reduces to a string."""
    consts: dict = {}
    changed = True
    while changed:
        changed = False
        for name, values in bound.items():
            if name in consts or len(values) != 1:
                continue
            text = _fold(values[0], consts, key=key)
            if text is not None:
                consts[name] = text
                changed = True
    return consts


def _names_ledger(text):
    return isinstance(text, str) and text.rstrip("/").endswith(LEDGER_NAME)


def _holds_ledger(expr, names, consts=None, key=None):
    """Whether a Python expression carries the ledger: a string naming it (or its file name), constant or folded from constant pieces (`_fold`), a name bound to one, a `ledger_path(...)` call, or the `LEDGER` constant. Searched text (`_flow`) is not carried. With `key` (`_Scopes.key`), `names` holds scoped keys and a Name is the ledger only when the binding it resolves to is."""
    for n in _flow(expr):
        constant = (isinstance(n, ast.Constant) and _names_ledger(n.value)) or (
            isinstance(n, (ast.BinOp, ast.JoinedStr))
            and _names_ledger(_fold(n, consts or {}, key=key))
        )
        name = isinstance(n, ast.Name) and ((key(n) if key else n.id) in names or n.id == "LEDGER")
        attribute = isinstance(n, ast.Attribute) and n.attr in ("LEDGER", "ledger_path")
        if constant or name or attribute:
            return True
    return False


def _call_name(func):
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _python_writes_ledger(program):
    """True or False for a Python program that parses; None when it does not, so the line reading answers."""
    try:
        tree = ast.parse(program)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    # Bindings are read per scope (#b4bb4a4e): `path` bound to the ledger in one function is a different name from `path` written in another, while a closure, a module binding read in a function, a `global` and a `nonlocal` still reach it.
    scopes = _Scopes(tree)
    key = scopes.key
    bound = scopes.bound()
    consts = _string_constants(bound, key)
    names: set = {n for n, text in consts.items() if _names_ledger(text)}
    changed = True
    while changed:
        changed = False
        for name, values in bound.items():
            if name not in names and any(_holds_ledger(v, names, consts, key) for v in values):
                names.add(name)
                changed = True
    imports = shellscan.python_imports(tree)
    if any(
        _holds_ledger(t, names, consts, key) for t in shellscan.python_write_targets(tree, imports)
    ):
        return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _WRITE_CALL.search(_call_name(node.func)):
            continue
        # Where the call writes, not what. A METHOD on an object writes into its receiver, so only the receiver is judged: `fh.write(row)` with `fh` the ledger is a write, and `bad.append(Finding(..., rel))` with `rel` the ledger's name is a list growing (V6 writer, 2026-10-28: `check_plan_live_proof.py --selftest` was refused for exactly that). A FUNCTION, bare or a module's
        # (`append_lines(path, ...)`, `jsonl_append.append_lines(...)`), takes its destination first, so its first argument and a path-named keyword are judged. Written CONTENT that names the ledger is data either way.
        func = node.func
        on_module = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in imports
        )
        # A module's `replace` (`os.replace(a, b)`, an aliased `import os as o`) is a file move and is judged below; a string's is an edit of text.
        if not on_module and _string_edit(node):
            continue
        if isinstance(func, ast.Attribute) and not on_module:
            parts = [func.value]
        else:
            parts = [*node.args[:1], *(k.value for k in node.keywords if k.arg in _PATH_KEYWORDS)]
            # A two-path call takes its DESTINATION second (`os.replace(src, dst)`, `shutil.copy(src, dst)`), and `shellscan.python_write_targets` reads that only on a module spelled `os` or `shutil`, so an aliased `import os as o; o.replace(forged, <ledger>)` reached nothing (found with #4e20f8c5).
            if _call_name(func) in _TWO_PATH_CALLS:
                parts.extend(node.args[1:2])
        if any(_holds_ledger(p, names, consts, key) for p in parts):
            return True
    return False


_RECORDER_MODULE = "rediacc_ci.ops.live_proof"


def _python_drives_recorder(program):
    """True or False for a Python program that parses: does it import the recorder and call something with `write=True`, or call its `_judge_and_write`? None when it does not parse.

    Read from the tree, not the text, so a program that only QUOTES such a line (this guard's own test, a plan being written) is not refused for it.
    """
    try:
        tree = ast.parse(program)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    imports = shellscan.python_imports(tree)
    if not any(
        v == _RECORDER_MODULE or v.startswith(_RECORDER_MODULE + ".") for v in imports.values()
    ):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) == "_judge_and_write":
            return True
        for kw in node.keywords:
            if kw.arg == "write" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _code_writes_ledger(code, program):
    """Interpreter code that writes the ledger: the recorder driven in-process with its write on, a Python program by its targets, else a line naming the ledger beside write code."""
    drives = _python_drives_recorder(program) if program is not None else None
    if drives is None:
        drives = any(
            RECORDER_MODULE.search(line) and RECORDER_WRITE.search(line)
            for line in code.splitlines()
        )
    if drives:
        return "code that drives the recorder in-process with its write on"
    # A Python program is judged by its tree whatever its text says, so a name built by concatenation (`'live-proof' + '.jsonl'`) is read (review 22b7a40c.2); the text precheck stays for code no tree reads.
    verdict = _python_writes_ledger(program) if program is not None else None
    if (
        verdict is None
        and LEDGER_NAME not in code
        and "ledger_path" not in code
        and "LEDGER" not in code
    ):
        return ""
    if verdict is None:
        verdict = any(
            (LEDGER_NAME in line or "ledger_path" in line) and WRITE_CODE.search(line)
            for line in code.splitlines()
        )
    return "code that writes the ledger" if verdict else ""


def _offending(cmd, cwd):
    """A short description of the first hand write to the ledger in `cmd`, or ""."""
    root = _base(None, cwd)
    hits = [t for t in shellscan.write_targets(cmd) if _is_ledger(t, root)]
    if hits:
        return "redirect into %s" % hits[0]
    for run in shellscan.every_run(cmd):
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        base = _base(shellscan.write_directory(run.cwd, cwd), cwd)
        for target in shellscan.redirect_targets(run):
            if _is_ledger(target, base):
                return "redirect into %s" % target
        variants = [argv]
        if run.xargv is not None and list(run.xargv) != argv:
            variants.append(list(run.xargv))
        for words in variants:
            what = _operand_write(run, name, words, base)
            if what:
                return what
            # `copy_landings` answers absolute paths already joined to the run's own `cd`, so "/" resolves each on disk as it stands (`cd agent/ledgers && cp f live-proof.jsonl` is pinned by the tests, review 22b7a40c.1).
            if any(
                _is_ledger(p, "/") for p, _into in shellscan.copy_landings(run, cwd, argv=words)
            ):
                return "%s onto the ledger" % name
            for word, how in shellscan.output_landings(run, words, cwd):
                if _is_ledger(word, base):
                    return (
                        "%s writing %s through its own output option" % (name, word)
                        if how == "option"
                        else "%s naming %s, and %s is not a command this guard reads as a reader"
                        % (name, word, name)
                    )
        shebang = shellscan.shebang_interpreter(run, cwd)
        if shebang and shebang.startswith(INTERPRETERS) and not name.startswith(INTERPRETERS):
            name = shebang
        if not name.startswith(INTERPRETERS):
            continue
        text, kind = shellscan.interpreter_program(run, cmd, cwd)
        if kind == "unjudgeable":
            body = " ".join(argv)
            if LEDGER_NAME in body or "ledger" in cmd:
                return "%s code this hook cannot read (%s)" % (name, shellscan.UNJUDGEABLE_REASON)
            continue
        python = kind is not None and re.match(r"^python[0-9.]*$", name)
        for body in _programs(cmd, text, kind, python):
            code = " ".join(argv)
            if kind in ("stdin", "file"):
                code += "\n" + (body or "")
            what = _code_writes_ledger(code, body if python else None)
            if what:
                return "%s %s" % (name, what)
    return ""


def _parses(text):
    try:
        ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False
    return True


def _programs(cmd, text, kind, python):
    """The program text(s) to judge for one interpreter run. `interpreter_program` hands a stdin run EVERY heredoc body of the command joined, so a Python heredoc beside a `cat > msg <<'EOF'` body never parses and fell to the line reading, which refused a PLAN write whose CONTENT named the ledger (#9efac135). When the joined text does not parse, each body is judged on its own: one that parses by its tree, one that does not by its lines."""
    if kind != "stdin" or not python or text is None or _parses(text):
        return [text]
    bodies = shellscan.heredoc_bodies(cmd)
    return bodies if len(bodies) > 1 else [text]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if not cmd:
        return hookio.ALLOW
    try:
        cwd = ev.default(("cwd",), str(hookio.repo_root()))
    except RuntimeError:
        cwd = ev.cwd
    what = _offending(cmd, cwd)
    if not what:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % what)
    return hookio.DENY
