"""Port of `.ci/scripts/test/gates/test-shrink-only-composition.sh`, retired in W7 P5.

Every shrink-only baseline in this repo must enforce shrink-only on the WRITE path, and this file is both the detector and its test: there is no separate `check-*.ts` to shell out to, so porting it means re-expressing the scan in Python. Parity here is therefore a claim about two implementations agreeing on the same tree, which is why the controls matter more than usual.

WHY IT EXISTS. Seven gates freeze a backlog and describe it as shrink-only. All seven enforced that on the READ path only; the drain flag was an unconditional reseed in every one. The difference is not academic:

    as enforced:  the TOTAL cannot grow without someone noticing.
    as promised:  the SET can only lose members.

A reseed that drains thirty findings and absorbs one satisfies the first, violates the second, and prints a SMALLER number while doing it. On 2026-08-20 the guard added to `scripts/gates/check-em-dash-surfaces.ts` refused, on its first real run, a reseed that would have enshrined two em dashes a background naturalization job had introduced minutes earlier.

STRUCTURAL PLUS BEHAVIOURAL, and the split is deliberate. Driving every gate's drain flag for real would mean rewriting live suppression files, and four of the gates do not even accept a `--baseline` override to redirect the write. So the structural half asserts that every CLI offering the flag consumes the shared guard, and the behavioural half proves the guard really refuses, end
to end, on the one gate that CAN be pointed at a copy.

THE CONTROLS PLANT INTO A COPY, NOT INTO THE REAL TREE (agent/plans/PLAN-prepush-full-cpu.md PF15, 2026-10-05). Until then four control cases planted a probe inside the real `scripts/` and `.ci/scripts/quality/` and removed it again, so this module declared `XDIST_GROUP = xdist_groups.REAL_TREE_GROUP` to keep any reader of those directories off other workers mid-plant, and check:ci-pytest held an exclusive `tree:repo` claim for the whole pytest wall because of it (the 2026-09-27 `zz_composition_*_probe` `FileNotFoundError`s under `-n` were two of this module's own plants racing each other's scans). Every scan function now takes the repository it enumerates, and each control plants into `scan_copy()`: a scratch git repository carrying every tracked `.gitignore` of this one, so `git ls-files --cached --others --exclude-standard` applies the same rules to the probe that it would in the real tree. What a control proves is membership of the probe in the enumeration and the classification, and both depend only on the probe's path, its bytes and those ignore rules. The real-tree scans (`test_every_gate_consumes_the_guard` and its siblings) only read, so no group is needed.

THE PROBES ARE PID-KEYED, which the twin's are not. The twin uses fixed names, so two concurrent invocations plant the same path and each cleanup deletes the OTHER run's fixture -- the failure the battery's schedule records for the `.gate-paths-exist` pair. Adding the pid costs nothing and removes a way for this port and its own twin to collide when both are driven from one
parity run.

ANTI-VACUITY. Scanning zero files is a FAILURE, never a pass, and EACH CORPUS IS REFUSED SEPARATELY: with a single summed count the `.py` half could go to zero
while twenty-two TypeScript offerers carried the total past the floor, and the
language this programme is migrating TO would be unchecked.
"""

import ast
import contextlib
import hashlib
import json
import os
import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

ROOT = paths.repo_root()

GUARD = "scripts/lib/shrink-only-baseline.ts"

# THE SUBJECT SCANS FOR THIS STRING, AND THIS FILE IS IN ITS CORPUS. That is the self-scanning trap batch 3's `label-references` port paid for, and this port hit it on 2026-09-09: written out, the flag put THIS module and the `test_gate_language_policy` port on the offender list within minutes, so a literal transcription would have reddened the very check it implements. Split, the
# contiguous string never appears in this file's bytes, and `test_this_module_is_not_itself_an_offender` reds BY NAME if that changes.
FLAG = "--write-" + "baseline"

# Files that name the flag but own no CLI branch of their own. Exempt BY NAME,
# with the reason here in the code, and PRINTED on every run so the debt cannot
# go quiet.
#
#   scripts/lib/shrink-only-baseline.ts  IS the guard; it cannot import itself.
EXEMPT = (GUARD,)

# The guard reaches a file either DIRECTLY or through the P7 choke point.
#
# `packages/www/scripts/lib/p7-backlog.js::writeBacklog` performs the composition check itself and exits non-zero on refusal, which covers its four consumers without any of them importing the guard by name. So a file that imports p7-backlog IS guarded, and asserting otherwise would flag three validators that are in fact protected.
#
# ONE HOP, deliberately, matching the precedent in check-gate-id-convention. A two-hop chain would escape this. No such chain exists today; if one appears, plant it as a control and widen the resolver THEN.
GUARDED_VIA = ("shrink-only-baseline", "p7-backlog")

# Known-unguarded CLIs. This list may only SHRINK. A new offender is not added here, it is fixed: the whole point is that a new gate must not be born with the old shape. EMPTY as of 2026-08-20, when the P7 choke point closed the last three.
PENDING: tuple[str, ...] = ()

# An IMPORT, not a mention. A bare substring match would count a file that merely names the module in a comment as guarded, which is how an over-permissive matcher turns a gate into decoration. Anchored on the `from '...'` specifier.
IMPORT_RE = {route: re.compile(r"from '[^']*%s" % re.escape(route)) for route in GUARDED_VIA}

# THE PYTHON HALF'S SHARED GUARD IS `rediacc_ci.quality.shrink_only`, the decision half of the TypeScript guard ported once. A file may consume it by NAME (`from ... import write_verdict`, or a local `def write_verdict` as the pre-shrink_only ports did) or by MODULE (`from rediacc_ci.quality import shrink_only [as SO]` then `SO.write_verdict(`). Three conditions, because any one alone is
# satisfiable while the write path stays unconditional: the file must BIND `write_verdict` (by name or through a module alias), must CALL it, and must CALL `baseline_additions`. READ FROM THE AST, not the text, so a file that only names them in a comment or a string is not guarded, which the mention control proves.
#
# The name-only reading missed MODULE-STYLE use until 2026-09-25: `check_tree_shape.py` calls `shrink_only.write_verdict(` and was reported unguarded, and so was every file that merely NAMES the flag in a string (`tree_shape.py`'s refusal text, four test modules passing it to a subprocess).
PY_GUARD_MODULE = "shrink_only"
PY_GUARD_FUNCS = ("write_verdict", "baseline_additions")

# THE DEFINITION SITE, exempt BY PATH with its reason, and printed every run. It names the flag in its docstrings and cannot consume itself.
PY_EXEMPT = (".ci/rediacc_ci/quality/shrink_only.py",)


# What makes a name or attribute an argument vector is where it was bound, not how it is spelled: `sys.argv`, a parameter named `argv` or `args`, the result of argparse's `parse_args` / `parse_known_args`, and anything derived from those by assignment, slicing or attribute access. `CompletedProcess.args` is the command a test ran, so a name bound from a subprocess result is not one.
ARGV_PARAMS = frozenset(("argv", "args"))
ARGV_ATTR = "argv"
ARGPARSE_RESULTS = frozenset(("parse_args", "parse_known_args"))
SEQUENCE_WRAPPERS = frozenset(("list", "tuple", "sorted", "set", "frozenset"))
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _own_nodes(scope):
    """Every node of a scope's own body, not descending into the scopes nested in it."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, SCOPE_NODES):
            stack.extend(ast.iter_child_nodes(node))


def _target_names(target) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [n for elt in target.elts for n in _target_names(elt)]
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    return []


def _params(scope) -> list[str]:
    a = getattr(scope, "args", None)
    if not isinstance(a, ast.arguments):
        return []
    names = [x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    names += [x.arg for x in (a.vararg, a.kwarg) if x]
    return names


def argv_asserts(tree) -> set[int]:
    """The ids of the nodes inside every `assert` whose condition reads NO argument vector (see ARGV_PARAMS): those check output, so their comparisons parse nothing."""
    skipped: set[int] = set()

    def reads(expr, tainted) -> bool:
        # A value is an argument vector when any operand it is built from is one: concatenation, unpacking, `or`/`and`, a conditional, a display. A call result is untainted unless it is a sequence wrapper or argparse result, a method called ON a tainted receiver (`sys.argv.copy()`), or a call handed a tainted positional argument that is returned whole by a wrapper; any other call (`build_args()`, `run(argv)`) is untainted by design, because its result is as often the output of a run as an argv and counting it would put every test that passes `argv` on to a subprocess helper on the offender list.
        if isinstance(expr, ast.Name):
            return expr.id in tainted
        if isinstance(expr, ast.Attribute):
            return expr.attr == ARGV_ATTR or reads(expr.value, tainted)
        if isinstance(expr, (ast.Subscript, ast.Starred)):
            return reads(expr.value, tainted)
        if isinstance(expr, ast.BinOp):
            return reads(expr.left, tainted) or reads(expr.right, tainted)
        if isinstance(expr, ast.BoolOp):
            return any(reads(v, tainted) for v in expr.values)
        if isinstance(expr, ast.IfExp):
            return reads(expr.body, tainted) or reads(expr.orelse, tainted)
        if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
            return any(reads(e, tainted) for e in expr.elts)
        if isinstance(expr, ast.Call):
            func = expr.func
            if isinstance(func, ast.Attribute) and func.attr in ARGPARSE_RESULTS:
                return True
            if isinstance(func, ast.Name) and func.id in ARGPARSE_RESULTS:
                return True
            if isinstance(func, ast.Name) and func.id in SEQUENCE_WRAPPERS:
                return any(reads(a, tainted) for a in expr.args)
            if isinstance(func, ast.Attribute):
                return reads(func.value, tainted)
        return False

    def visit(scope, inherited: dict[str, bool]) -> None:
        bound: dict[str, bool] = {n: n in ARGV_PARAMS for n in _params(scope)}
        assignments = []
        for node in _own_nodes(scope):
            if isinstance(node, ast.Assign):
                assignments.append(
                    ([t for tg in node.targets for t in _target_names(tg)], node.value)
                )
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                assignments.append((_target_names(node.target), node.value))
        for names, _ in assignments:
            for n in names:
                bound.setdefault(n, False)
        scoped = {**inherited, **bound}
        # A chain (`a = sys.argv`, `b = a[1:]`) settles in as many passes as it is long.
        for _ in range(len(assignments) + 1):
            changed = False
            for names, value in assignments:
                if reads(value, {n for n, t in scoped.items() if t}):
                    for n in names:
                        if not scoped.get(n):
                            scoped[n] = True
                            changed = True
            if not changed:
                break
        tainted = {n for n, t in scoped.items() if t}
        for node in _own_nodes(scope):
            if isinstance(node, ast.Assert) and not any(
                reads(n, tainted) for n in ast.walk(node.test)
            ):
                skipped.update(id(inner) for inner in ast.walk(node.test))
            if isinstance(node, SCOPE_NODES):
                visit(node, scoped)

    visit(tree, {})
    return skipped


def py_offers_flag(tree) -> bool:
    """True when the module PARSES the flag, not when it merely names it.

    A writer reads the flag off its argument vector: `FLAG in argv` / `FLAG not in args`, `arg == FLAG`, or `parser.add_argument(FLAG, ...)`. A docstring, an error message telling the reader to run it, a test passing it to a subprocess, and an `assert` on a captured stream all name the flag without offering it, and treating those as writers is what put four test modules on the offender list.
    """

    def is_flag(node) -> bool:
        return isinstance(node, ast.Constant) and node.value == FLAG

    # An `assert` whose condition reads no argument vector checks output (a captured stream, a return value); it parses no argv, so its comparisons are skipped. One that does read one (`assert FLAG in sys.argv`) still parses the flag and is NOT skipped.
    asserted = argv_asserts(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and id(node) not in asserted:
            operands = [node.left, *node.comparators]
            for i, op in enumerate(node.ops):
                left, right = operands[i], operands[i + 1]
                if isinstance(op, (ast.In, ast.NotIn)) and is_flag(left):
                    return True
                if isinstance(op, (ast.Eq, ast.NotEq)) and (is_flag(left) or is_flag(right)):
                    return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and any(is_flag(a) for a in node.args)
        ):
            return True
    return False


def py_guard_calls(tree) -> set[str]:
    """Which of `PY_GUARD_FUNCS` the module really CALLS, through a route that reaches the guard."""
    name_of: dict[str, str] = {}  # a bare name bound to a guard function -> that function
    aliases: set[str] = set()  # names bound to the shrink_only module
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in PY_GUARD_FUNCS:
            name_of[node.name] = node.name
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in PY_GUARD_FUNCS:
                    name_of[alias.asname or alias.name] = alias.name
                elif alias.name == PY_GUARD_MODULE:
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[-1] == PY_GUARD_MODULE and alias.asname:
                    aliases.add(alias.asname)
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in name_of:
            called.add(name_of[func.id])
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in PY_GUARD_FUNCS
            and isinstance(func.value, ast.Name)
            and func.value.id in aliases
        ):
            called.add(func.attr)
    return called


# THE TYPESCRIPT HALF READS TOKENS, NOT TEXT, since 2026-10-14. Until then every `.ts`/`.js` file whose bytes held the flag was a writer, so a pin driver building the drain command as a string (`scripts/lib/pins/drivers/docker.ts`) and a selftest asserting that string's suffix (`scripts/lib/pins/drivers/selftest.ts`) were both reported as unguarded baseline writers, and
# the check was red at HEAD for two files that parse no argv at all. The Python half made the same move on 2026-09-25 (see `py_offers_flag`).
#
# A TypeScript file OFFERS the flag when a string literal whose WHOLE value is the flag, outside any comment, sits in an argv-parse position:
#
#   .includes(FLAG) .indexOf(FLAG) .lastIndexOf(FLAG) .has(FLAG)   membership in an argument vector or set
#   x === FLAG, FLAG !== x, and the loose == / !=                  a comparison against one argument
#   case FLAG:                                                     a switch over the arguments
#
# and the same three positions count for a NAME bound to the literal (`const WRITE = FLAG`), so hoisting the flag into a constant does not hide a writer. A literal that only CONTAINS the flag (a drain command, a refusal message) is not the flag, and a literal passed to any other call (`endsWith`, `spawn`, `expect(...).toContain`) inspects a string rather than parsing one.
#
# THE ERROR DIRECTION IS CHOSEN. A false positive here reds the check over a file that is not a writer, which a reader sees at once and can argue with; a false negative lets an unconditional reseed through, which nobody sees. So `.includes(FLAG)` counts whatever its receiver, including a test asserting `stderr.includes(FLAG)`, and a file the lexer cannot read to the
# end (an unterminated string, comment, template or regex) counts as a writer too, as an unparseable Python module does.
TS_PARSE_METHODS = ("includes", "indexOf", "lastIndexOf", "has")
TS_COMPARE_OPS = ("===", "!==", "==", "!=")

# After one of these a `/` starts a regex literal, after anything else it divides. The classic heuristic; it decides only whether a quote inside `/'/` opens a string, which is exactly the mistake that would make the lexer lose its place.
_TS_REGEX_AFTER_WORDS = frozenset(
    ("return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw")
)
_TS_PUNCT = (
    "===",
    "!==",
    "...",
    "=>",
    "==",
    "!=",
    "<=",
    ">=",
    "&&",
    "||",
    "??",
    "?.",
    "++",
    "--",
)
_TS_IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")
_TS_NUMBER_RE = re.compile(r"\d[\w.]*")


class TsLexError(ValueError):
    """The lexer ran off the end of the file inside a string, comment, template or regex."""


def _ts_string(src: str, i: int, quote: str) -> tuple[str, int]:
    """Read a '...' or "..." literal starting at the quote; return (value, index after it)."""
    out = []
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            out.append(src[j : j + 2])
            j += 2
            continue
        if c == quote:
            return "".join(out), j + 1
        if c == "\n":
            break
        out.append(c)
        j += 1
    raise TsLexError("unterminated string at offset %d" % i)


def ts_tokens(src: str) -> list[tuple[str, str]]:
    """The file as `(kind, text)` tokens: `str`, `ident`, `punct`, `num`. Comments vanish, a template literal is one `str` token for its literal parts plus the tokens of every `${...}` inside it, and a regex literal is one `regex` token. Raises `TsLexError` on a file it cannot read to the end."""
    toks: list[tuple[str, str]] = []
    # Brace depth per open `${`: when it returns to zero the template resumes.
    templates: list[int] = []
    i = 0
    n = len(src)

    def regex_allowed() -> bool:
        if not toks:
            return True
        kind, text = toks[-1]
        if kind == "punct":
            return text not in (")", "]", "}", "++", "--")
        return kind == "ident" and text in _TS_REGEX_AFTER_WORDS

    def template_part(j: int) -> int:
        """Read template text from j (just after a backtick or a closing `}`) up to the closing backtick or the next `${`."""
        out = []
        while j < n:
            c = src[j]
            if c == "\\":
                out.append(src[j : j + 2])
                j += 2
                continue
            if c == "`":
                toks.append(("str", "".join(out)))
                return j + 1
            if c == "$" and src.startswith("${", j):
                toks.append(("str", "".join(out)))
                toks.append(("punct", "${"))
                templates.append(0)
                return j + 2
            out.append(c)
            j += 1
        raise TsLexError("unterminated template literal")

    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
        elif src.startswith("//", i):
            end = src.find("\n", i)
            i = n if end < 0 else end
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            if end < 0:
                raise TsLexError("unterminated block comment at offset %d" % i)
            i = end + 2
        elif c in "'\"":
            value, i = _ts_string(src, i, c)
            toks.append(("str", value))
        elif c == "`":
            i = template_part(i + 1)
        elif c == "/" and regex_allowed():
            j = i + 1
            in_class = False
            while j < n and (in_class or src[j] != "/"):
                if src[j] == "\\":
                    j += 1
                elif src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "\n":
                    raise TsLexError("unterminated regex literal at offset %d" % i)
                j += 1
            if j >= n:
                raise TsLexError("unterminated regex literal at offset %d" % i)
            j += 1
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            toks.append(("regex", src[i:j]))
            i = j
        elif c == "{" and templates:
            templates[-1] += 1
            toks.append(("punct", c))
            i += 1
        elif c == "}" and templates:
            if templates[-1] == 0:
                templates.pop()
                toks.append(("punct", "}"))
                i = template_part(i + 1)
            else:
                templates[-1] -= 1
                toks.append(("punct", c))
                i += 1
        elif m := _TS_IDENT_RE.match(src, i):
            toks.append(("ident", m.group()))
            i = m.end()
        elif m := _TS_NUMBER_RE.match(src, i):
            toks.append(("num", m.group()))
            i = m.end()
        else:
            for p in _TS_PUNCT:
                if src.startswith(p, i):
                    toks.append(("punct", p))
                    i += len(p)
                    break
            else:
                toks.append(("punct", c))
                i += 1
    if templates:
        raise TsLexError("unterminated template substitution")
    return toks


def ts_offers_flag(src: str) -> bool:
    """True when the source PARSES the flag off its arguments, by the positions listed above `TS_PARSE_METHODS`. A source the lexer cannot finish counts as a writer."""
    try:
        toks = ts_tokens(src)
    except TsLexError:
        return True

    def is_flag_literal(k: int) -> bool:
        return 0 <= k < len(toks) and toks[k] == ("str", FLAG)

    # Names bound straight to the literal: `const WRITE = FLAG;`.
    names = {
        toks[k - 2][1]
        for k in range(3, len(toks))
        if is_flag_literal(k)
        and toks[k - 1] == ("punct", "=")
        and toks[k - 2][0] == "ident"
        and toks[k - 3] in (("ident", "const"), ("ident", "let"), ("ident", "var"))
        and (k + 1 >= len(toks) or toks[k + 1] in (("punct", ";"), ("punct", ",")))
    }

    def is_flag(k: int) -> bool:
        if is_flag_literal(k):
            return True
        return 0 <= k < len(toks) and toks[k][0] == "ident" and toks[k][1] in names

    for k in range(len(toks)):
        if not is_flag(k):
            continue
        # A bound name at its own declaration is not a use.
        if toks[k][0] == "ident" and k + 1 < len(toks) and toks[k + 1] == ("punct", "="):
            continue
        prev = toks[k - 1] if k >= 1 else ("", "")
        nxt = toks[k + 1] if k + 1 < len(toks) else ("", "")
        if (
            k >= 3
            and prev == ("punct", "(")
            and toks[k - 2][0] == "ident"
            and toks[k - 2][1] in TS_PARSE_METHODS
            and toks[k - 3] in (("punct", "."), ("punct", "?."))
            and nxt in (("punct", ")"), ("punct", ","))
        ):
            return True
        if (prev[0] == "punct" and prev[1] in TS_COMPARE_OPS) or (
            nxt[0] == "punct" and nxt[1] in TS_COMPARE_OPS
        ):
            return True
        if prev == ("ident", "case") and nxt == ("punct", ":"):
            return True
    return False


# Floors, one per corpus. Neither excuses the other; see the docstring. The writer floor is the token reading's own: the text corpus can hold steady while the reading recognises nothing.
TS_FLOOR = 8
TS_WRITER_FLOOR = 8


def git_bin() -> str:
    return harness.require_tool("git", "install git; the corpus comes from `git ls-files`")


def all_offerers(root: pathlib.Path = ROOT) -> list[str]:
    """Every tracked-or-untracked source file whose text names the flag, sorted.

    ENUMERATED FROM `git ls-files` RATHER THAN FROM A ROOT LIST, which is what makes the coverage permanent: a directory created next month is in the corpus the day it exists. The extension filter is a git PATHSPEC rather than a glob applied afterwards, so a filename can never be read as an option.

    TWO BLIND SPOTS THE TWIN CLOSED ON 2026-09-08 AND THIS INHERITS. The old enumerator read only `.ts` and `.js` under `scripts/` and `packages/www/scripts/`, which excluded `.py` AND excluded the whole `.ci/` tree -- and the first Python shrink-only baseline landed outside both filters, freezing 521 paths. The hole was self-declared in that gate's own comment and was still open a
    day later.
    """
    proc = harness.run(
        [
            git_bin(),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "*.ts",
            "*.js",
            "*.py",
        ],
        cwd=root,
        timeout=300,
    )
    if proc.rc != 0:
        raise harness.GateAssertionError(
            "`git ls-files` failed (rc=%d): the corpus could not be enumerated, so every "
            "verdict below would be about nothing. %s" % (proc.rc, proc.err.strip())
        )
    found = []
    for rel in proc.out.split("\0"):
        if not rel:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            # A corpus file can VANISH mid-run: this very detector plants and removes probes inside the scanned tree, and so does its twin. An unreadable neighbour is not this gate's finding.
            continue
        if FLAG in text:
            found.append(rel)
    return sorted(found)


def offerers(root: pathlib.Path = ROOT) -> list[str]:
    return [f for f in all_offerers(root) if f.endswith((".ts", ".js"))]


def offerers_py(root: pathlib.Path = ROOT) -> list[str]:
    return [f for f in all_offerers(root) if f.endswith(".py")]


def py_parse(rel: str, root: pathlib.Path = ROOT):
    """The module's AST, or None when it does not parse. A file that cannot be read as Python cannot be shown to be guarded, so the caller treats None as an offender rather than skipping it."""
    text = (root / rel).read_text(encoding="utf-8", errors="replace")
    try:
        return ast.parse(text, filename=rel)
    except SyntaxError:
        return None


def py_is_writer(rel: str, root: pathlib.Path = ROOT) -> bool:
    """A Python file in the text corpus that really OFFERS the flag. Unparseable counts as a writer, so a syntax error cannot hide one."""
    tree = py_parse(rel, root)
    return tree is None or py_offers_flag(tree)


def py_reaches_guard(rel: str, root: pathlib.Path = ROOT) -> bool:
    """All three conditions, or the Python writer is unguarded."""
    tree = py_parse(rel, root)
    return tree is not None and py_guard_calls(tree) == set(PY_GUARD_FUNCS)


def unguarded_py(root: pathlib.Path = ROOT) -> list[str]:
    return [
        f
        for f in offerers_py(root)
        if f not in PY_EXEMPT and py_is_writer(f, root) and not py_reaches_guard(f, root)
    ]


def ts_is_writer(rel: str, root: pathlib.Path = ROOT) -> bool:
    """A TypeScript/JavaScript file in the text corpus that really OFFERS the flag."""
    return ts_offers_flag((root / rel).read_text(encoding="utf-8", errors="replace"))


def ts_writers(root: pathlib.Path = ROOT) -> list[str]:
    """The non-exempt TypeScript/JavaScript files that parse the flag."""
    return [f for f in offerers(root) if f not in EXEMPT and ts_is_writer(f, root)]


def unguarded(root: pathlib.Path = ROOT) -> list[str]:
    """Files that parse the flag, are not exempt, and reach the guard by no route."""
    out = []
    for rel in ts_writers(root):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        if not any(pattern.search(text) for pattern in IMPORT_RE.values()):
            out.append(rel)
    return out


@contextlib.contextmanager
def scan_copy():
    """A scratch git repository the enumerator sees exactly as it sees this one, for a probe to be planted in. Removed on the way out.

    WHY A COPY OF THE IGNORE RULES AND NOT OF THE TREE. Each control asks whether a probe at a given path, with given bytes, is in the enumeration and how it is classified. `git ls-files --cached --others --exclude-standard` decides the first from the path and the `.gitignore` files above it, so those are what is copied, every tracked one; a probe the real tree would ignore is ignored here too, and the control still fails for the reason it would have failed in place. The second depends only on the probe's bytes. Copying the whole tree would add tens of thousands of files and no evidence.

    NOT THE REAL TREE (PF15): a probe there is visible, for its lifetime, to every concurrent reader of `scripts/` and `.ci/scripts/`, which is what this module's xdist group and the pytest lane's `tree:repo` claim used to buy off.
    """
    git = git_bin()
    listed = harness.run(
        [git, "ls-files", "-z", "--", ".gitignore", ":(glob)**/.gitignore"], cwd=ROOT, timeout=120
    )
    if listed.rc != 0:
        raise harness.GateAssertionError(
            "`git ls-files` could not list the ignore files (rc=%d): %s"
            % (listed.rc, listed.err.strip())
        )
    ignores = [rel for rel in listed.out.split("\0") if rel]
    if ".gitignore" not in ignores:
        raise harness.GateAssertionError(
            "the root .gitignore is not tracked, so the copy would enumerate a different set"
        )
    with harness.temp_dir() as tmp:
        root = tmp / "repo"
        root.mkdir()
        init = harness.run([git, "init", "-q", str(root)], cwd=tmp, timeout=60)
        if init.rc != 0:
            raise harness.GateAssertionError("git init failed (rc=%d): %s" % (init.rc, init.err))
        for rel in ignores:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes((ROOT / rel).read_bytes())
        yield root


@contextlib.contextmanager
def probe(rel_dir: str, stem: str, suffix: str, body: str):
    """Plant one probe in a `scan_copy()` repository, yield `(root, repo-relative path)`, and remove both whatever happens.

    The copy is a git repository the enumerator really runs in, so a probe outside its scope is still invisible and the control still fails, which is the property a plant-based control exists for. The probe name is still pid-keyed, which costs nothing.
    """
    name = "%s_%d%s" % (stem, os.getpid(), suffix)
    rel = "%s/%s" % (rel_dir, name)
    with scan_copy() as root:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        try:
            yield root, rel
        finally:
            path.unlink(missing_ok=True)


# EVERY PROBE BODY IS RENDERED THROUGH `%s`, for the reason FLAG is split: a body written out would make this module a corpus member and an offender in its own scan. The probes still carry the real flag on DISK, which is the only place it has to appear for the controls to mean anything.
UNGUARDED_PY_BODY = '''#!/usr/bin/env python3
"""Temporary control fixture. Offers %s with no composition guard."""

import sys

if "%s" in sys.argv:
    print("unconditional reseed")
''' % (FLAG, FLAG)

MENTION_PY_BODY = (
    '''#!/usr/bin/env python3
"""Temporary control fixture. Names the guard's function names in PROSE only."""

import sys

# write_verdict( and baseline_additions( appear here and nowhere else.
if "%s" in sys.argv:
    print("unconditional reseed")
'''
    % FLAG
)

GUARDED_PY_BODY = (
    '''#!/usr/bin/env python3
"""Temporary control fixture. Actually consumes the ported decision half."""

import sys


def baseline_additions(old, new):
    known = set(old)
    return [x for x in new if x not in known]


def write_verdict(*, baseline_exists, first_seed, additions):
    if not baseline_exists and not first_seed:
        return "missing-baseline"
    return "would-grow" if additions else None


if "%s" in sys.argv:
    added = baseline_additions([], [])
    if write_verdict(baseline_exists=True, first_seed=False, additions=added):
        sys.exit(1)
'''
    % FLAG
)

GUARDED_MODULE_PY_BODY = (
    '''#!/usr/bin/env python3
"""Temporary control fixture. Consumes the shared guard MODULE-STYLE, through an alias."""

import sys

from rediacc_ci.quality import shrink_only as SO

if "%s" in sys.argv:
    added = SO.baseline_additions([], [])
    if SO.write_verdict(baseline_exists=True, first_seed=False, additions=added):
        sys.exit(1)
'''
    % FLAG
)

IMPORT_ONLY_PY_BODY = (
    '''#!/usr/bin/env python3
"""Temporary control fixture. Imports the shared guard module and never calls it."""

import sys

from rediacc_ci.quality import shrink_only  # noqa: F401

# shrink_only.write_verdict( and shrink_only.baseline_additions( appear only here.
if "%s" in sys.argv:
    print("unconditional reseed")
'''
    % FLAG
)

STRING_ONLY_PY_BODY = '''#!/usr/bin/env python3
"""Temporary control fixture shaped like a TEST: it names %s in prose and passes it to a subprocess, and parses no argv."""

import subprocess
import sys


def test_the_flag_refuses():
    proc = subprocess.run(
        [sys.executable, "gate.py", "%s"], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 1, "run it again with %s --first-seed"
    assert "%s" not in proc.stderr
''' % (FLAG, FLAG, FLAG, FLAG)

# A test asserting on the command a subprocess ran (`CompletedProcess.args`): it parses no argv.
COMPLETED_ARGS_PY_BODY = """import subprocess
import sys


def test_the_command_that_ran():
    proc = subprocess.run([sys.executable, "gate.py", "%s"], capture_output=True, check=False)
    assert "%s" in proc.args
""" % (FLAG, FLAG)

# A test asserting on a local named `args` that was bound from a subprocess result: a name spelled like an argument vector, bound from `CompletedProcess.args`, parses no argv.
BOUND_FROM_PROC_PY_BODY = """import subprocess
import sys


def test_the_command_that_ran():
    proc = subprocess.run([sys.executable, "gate.py", "%s"], capture_output=True, check=False)
    args = proc.args
    assert "%s" in args
""" % (FLAG, FLAG)

# Writers whose only argv parse is an `assert` condition. Skipping every assert would drop both off the offender list; reading argv is what makes them parses.
ASSERT_ARGV_PY_BODIES = {
    "assert FLAG in sys.argv": """import sys

assert "%s" in sys.argv, "refusing to run without the drain flag"
print("unconditional reseed")
"""
    % FLAG,
    "assert FLAG in ctx.args (parse_args result)": """import argparse

ctx = argparse.ArgumentParser().parse_args()
assert "%s" in ctx.args
print("unconditional reseed")
"""
    % FLAG,
    "assert FLAG in namespace.args (parse_known_args result)": """import argparse

namespace, rest = argparse.ArgumentParser().parse_known_args()
assert "%s" in namespace.args
print("unconditional reseed")
"""
    % FLAG,
    "assert FLAG in args (a parameter)": """def main(args):
    assert "%s" in args
    print("unconditional reseed")
"""
    % FLAG,
    "assert FLAG in (argv = sys.argv + extra)": """import sys

argv = sys.argv + ["--extra"]
assert "%s" in argv
print("unconditional reseed")
"""
    % FLAG,
    "assert FLAG in (args = [*sys.argv])": """import sys

args = [*sys.argv]
assert "%s" in args
print("unconditional reseed")
"""
    % FLAG,
    "assert FLAG in (args = sys.argv or [])": """import sys

args = sys.argv or []
assert "%s" in args
print("unconditional reseed")
"""
    % FLAG,
    "assert FLAG in (args = sys.argv.copy())": """import sys

args = sys.argv.copy()
assert "%s" in args
print("unconditional reseed")
"""
    % FLAG,
    "assert any(a == FLAG for a in args)": """import sys

args = sys.argv[1:]
assert any(a == "%s" for a in args)
print("unconditional reseed")
"""
    % FLAG,
}

UNGUARDED_TS_BODY = """// Temporary control fixture. Offers %s with no composition guard.
if (process.argv.includes('%s')) {
  console.log('unconditional reseed');
}
""" % (FLAG, FLAG)

MENTION_TS_BODY = """// Temporary control fixture. Mentions p7-backlog and shrink-only-baseline in PROSE
// only, imports neither, and offers %s with no guard at all.
if (process.argv.includes('%s')) {
  console.log('unconditional reseed');
}
""" % (FLAG, FLAG)

# Shaped like `scripts/lib/pins/drivers/docker.ts` and its selftest: the flag in a comment that READS like an argv parse, in a block comment, inside a longer drain command, as an `endsWith` argument, in template text and as a bare literal. The regex literal holding a quote comes first, so a lexer that read it as a string would lose its place for everything below.
STRING_ONLY_TS_BODY = """// Temporary control fixture. process.argv.includes('%s') in a comment parses nothing.
/* if (argv.includes('%s')) { reseed(); } */
const quote = /'/g;
const steps = [{ run: 'npx tsx scripts/gates/check-x.ts %s' }];
const ok = steps[0]?.run.endsWith('%s') && `${steps.length} %s`.length > 0;
console.log(ok, quote, `drain with %s`, '%s'.length);
""" % (FLAG, FLAG, FLAG, FLAG, FLAG, FLAG, FLAG)

# Every argv-parse position the token reading names, one body each, none guarded. The first carries the regex-with-a-quote trap BEFORE its parse, the fifth hides its parse behind nested template substitutions, and the last is cut off mid-string, which must count as a writer rather than as nothing.
WRITER_TS_BODIES = {
    "indexOf after a regex holding a quote": """const args = process.argv.slice(2);
const q = /'/g;
if (args.indexOf('%s') >= 0 && q) {
  console.log('unconditional reseed');
}
"""
    % FLAG,
    "strict equality": """for (const a of process.argv) {
  if (a === '%s') console.log('unconditional reseed');
}
"""
    % FLAG,
    "switch case": """switch (process.argv[2]) {
  case "%s":
    console.log('unconditional reseed');
}
"""
    % FLAG,
    "a named constant in a Set": """const WRITE = '%s';
if (new Set(process.argv).has(WRITE)) {
  console.log(`unconditional reseed ${WRITE}`);
}
"""
    % FLAG,
    "after nested template substitutions": """const msg = `run ${['a'].map((x) => `${x}{`).join('')}`;
if (process.argv?.includes(`%s`)) {
  console.log(msg);
}
"""
    % FLAG,
    "an unterminated string": """if (process.argv.includes('%s)) {
  console.log('unconditional reseed');
}
"""
    % FLAG,
}

GUARDED_TS_BODY = """// Temporary control fixture. Parses %s and consumes the shared guard.
import { writeBaselineVerdict } from '../lib/shrink-only-baseline.ts';
if (process.argv.includes('%s')) {
  writeBaselineVerdict();
}
""" % (FLAG, FLAG)


# ---------------------------------------------------------------------------


def test_guard_module_exists(gate):
    if not (ROOT / GUARD).is_file():
        gate.log_fail("the shared guard is missing at %s" % GUARD)
    gate.log_pass("the shared composition guard exists at %s" % GUARD)


def test_scan_is_not_vacuous(gate):
    """EACH CORPUS IS REFUSED SEPARATELY. See the docstring."""
    n = len(offerers())
    m = len(offerers_py())
    if n < TS_FLOOR:
        gate.log_fail(
            "only %d TypeScript/JavaScript file(s) offer %s; the scan is not seeing the "
            "tree, so its green would mean nothing" % (n, FLAG)
        )
    if m == 0:
        gate.log_fail(
            "ZERO Python file(s) offer %s. One did on 2026-09-07 "
            "(check_language_policy.py, 521 paths). Zero means the enumerator stopped "
            "seeing .py, not that the debt went away -- and this half of the gate would "
            "be asserting nothing." % FLAG
        )
    gate.log_pass("scan sees %d ts/js and %d python file(s) offering %s" % (n, m, FLAG))


def test_every_gate_consumes_the_guard(gate):
    bad = [f for f in unguarded() if f not in PENDING]
    if bad:
        for f in bad:
            gate.log_error("  %s offers %s and does NOT consume %s" % (f, FLAG, GUARD))
        gate.log_error("")
        gate.log_error(
            "  A shrink-only baseline that reseeds unconditionally can drain thirty findings,"
        )
        gate.log_error("  absorb one brand new one, and print a smaller number while doing it.")
        gate.log_error(
            "  Import { writeBaselineVerdict, renderRefusal } from '%s' and refuse" % GUARD
        )
        gate.log_error("  before writing. Do NOT add the file to PENDING in this gate.")
        gate.log_fail("at least one baseline writer bypasses the composition guard")
    named = offerers()
    writers = ts_writers()
    if len(writers) < TS_WRITER_FLOOR:
        gate.log_fail(
            "only %d of the %d TypeScript/JavaScript file(s) naming %s are read as WRITERS. "
            "Eighteen were on 2026-10-14; a collapse means the token reading stopped "
            "recognising the argv parse, and the guard verdict above is about nothing."
            % (len(writers), len(named), FLAG)
        )
    gate.log_pass(
        "every non-exempt TypeScript baseline writer consumes the guard (%d writer(s) among "
        "%d file(s) naming the flag)" % (len(writers), len(named))
    )
    # VISIBLE EVERY RUN, so neither the exemption nor the mention-only set can go quiet.
    for f in EXEMPT:
        gate.log_info("EXEMPT (the shared guard itself): %s" % f)
    for f in named:
        if f not in EXEMPT and f not in writers:
            gate.log_info("NAMES THE FLAG, PARSES NO ARGV FOR IT (not a writer): %s" % f)


def test_pending_set_only_shrinks(gate):
    """The PENDING set may only shrink, and it is EMPTY. Kept as a live check rather than deleted, because the next unguarded writer must land in the failure above, never here."""
    if not PENDING:
        gate.log_pass("no known-unguarded baseline writers remain (PENDING is empty)")
        return
    for f in PENDING:
        if not (ROOT / f).is_file():
            gate.log_fail("PENDING names %s, which no longer exists; remove the line" % f)
        text = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in IMPORT_RE.values()):
            gate.log_fail("%s now reaches the guard; DELETE it from PENDING" % f)
        # Visible every run, on purpose. A quiet exemption is how a gate stops meaning its name.
        gate.log_info("STILL UNGUARDED: %s" % f)
    gate.log_pass("the unguarded set has not grown (%d known)" % len(PENDING))


def test_every_python_writer_consumes_the_guard(gate):
    """The Python writers, against the ported guard. Separate from the TypeScript check because the ROUTES are different, not because the rule is."""
    bad = unguarded_py()
    if bad:
        for f in bad:
            gate.log_error(
                "  %s offers %s and consumes neither a shared guard nor the ported one" % (f, FLAG)
            )
        gate.log_error("")
        gate.log_error(
            "  A shrink-only baseline that reseeds unconditionally can drain thirty findings,"
        )
        gate.log_error("  absorb one brand new one, and print a smaller number while doing it.")
        gate.log_error(
            "  Port the decision half of %s the way check_language_policy.py did:" % GUARD
        )
        gate.log_error("  baseline_additions() for the diff, write_verdict() before the write.")
        gate.log_fail("at least one Python baseline writer bypasses the composition guard")
    py = offerers_py()
    writers = [f for f in py if f not in PY_EXEMPT and py_is_writer(f)]
    if not writers:
        gate.log_fail(
            "ZERO of the %d Python file(s) naming %s is read as a WRITER. Six were on "
            "2026-09-25; zero means the AST reading stopped recognising the argv parse, and "
            "every guard verdict above is about nothing." % (len(py), FLAG)
        )
    gate.log_pass(
        "every Python baseline writer consumes the guard (%d writer(s) among %d file(s) "
        "naming the flag)" % (len(writers), len(py))
    )
    # VISIBLE EVERY RUN, so neither the exemption nor the mention-only set can go quiet.
    for f in PY_EXEMPT:
        if not (ROOT / f).is_file():
            gate.log_fail("PY_EXEMPT names %s, which no longer exists; remove the entry" % f)
        gate.log_info("EXEMPT (the shared guard's definition site): %s" % f)
    for f in py:
        if f not in PY_EXEMPT and f not in writers:
            gate.log_info("NAMES THE FLAG, PARSES NO ARGV FOR IT (not a writer): %s" % f)


def test_control_unguarded_python_reseed_is_detected(gate):
    """CONTROL. Plant an unguarded PYTHON writer where the OLD enumerator could not look -- under `.ci/`, with a `.py` suffix -- and require detection. Run against the previous enumerator it detects nothing at all, because neither the extension nor the directory was in scope."""
    with probe(
        ".ci/scripts/quality", "zz_composition_control_probe_port", ".py", UNGUARDED_PY_BODY
    ) as (root, rel):
        seen = rel in offerers_py(root)
        detected = rel in unguarded_py(root)
    if (root / rel).exists():
        gate.log_fail("python control probe was not removed")
    if not seen:
        gate.log_fail(
            "CONTROL FAILED: the enumerator did not even SEE a .py offerer under .ci/, so "
            "the widening is not in effect"
        )
    if not detected:
        gate.log_fail(
            "CONTROL FAILED: an unguarded Python reseed was NOT detected, so this half cannot fail"
        )
    gate.log_pass("CONTROL: a planted unguarded Python reseed under .ci/ is seen and detected")


def test_control_python_mention_is_not_a_guard(gate):
    """CONTROL, the other direction. A Python file that only MENTIONS the ported guard in prose must NOT count as guarded, and one that genuinely consumes it MUST. Both answers come from the same scanner on the same run."""
    with probe(
        ".ci/scripts/quality", "zz_composition_mention_probe_port", ".py", MENTION_PY_BODY
    ) as (root, rel):
        mentioned = rel in unguarded_py(root)
        (root / rel).write_text(GUARDED_PY_BODY, encoding="utf-8")
        guarded = rel not in unguarded_py(root)
    if (root / rel).exists():
        gate.log_fail("python mention probe was not removed")
    if not mentioned:
        gate.log_fail(
            "CONTROL FAILED: a prose mention of write_verdict was accepted as a guard route"
        )
    if not guarded:
        gate.log_fail(
            "CONTROL FAILED: a writer that really consumes the ported guard was reported "
            "unguarded, so this check flags correct work"
        )
    gate.log_pass("CONTROL: naming the ported guard in a comment does not count, consuming it does")


def test_control_python_module_style_guard_is_recognised(gate):
    """CONTROL. A writer that consumes `shrink_only` through a MODULE ALIAS (`SO.write_verdict(`) is guarded, and one that only IMPORTS the module and reseeds unconditionally is not. Without the first half this check flags correct work, which is what reddened `check_tree_shape.py` until 2026-09-25; without the second an import alone would pass."""
    with probe(
        ".ci/scripts/quality", "zz_composition_module_probe_port", ".py", GUARDED_MODULE_PY_BODY
    ) as (root, rel):
        writer = py_is_writer(rel, root)
        guarded = rel not in unguarded_py(root)
        (root / rel).write_text(IMPORT_ONLY_PY_BODY, encoding="utf-8")
        import_only_caught = rel in unguarded_py(root)
    if (root / rel).exists():
        gate.log_fail("python module-style probe was not removed")
    if not writer:
        gate.log_fail(
            "CONTROL FAILED: a file parsing the flag off sys.argv was not read as a writer"
        )
    if not guarded:
        gate.log_fail(
            "CONTROL FAILED: a writer calling SO.write_verdict and SO.baseline_additions was "
            "reported unguarded, so module-style consumption is not recognised"
        )
    if not import_only_caught:
        gate.log_fail(
            "CONTROL FAILED: importing shrink_only without calling it was accepted as a guard"
        )
    gate.log_pass(
        "CONTROL: module-style consumption of shrink_only counts, a bare import of it does not"
    )


def test_control_python_string_mention_is_not_a_writer(gate):
    """CONTROL. A test-shaped file that names the flag in a docstring, a subprocess argument and an assertion message parses no argv, so it is NOT a writer and is not reported. The corpus still SEES it, which keeps this a statement about the writer reading rather than about the enumerator."""
    with probe(
        ".ci/scripts/quality", "zz_composition_string_probe_port", ".py", STRING_ONLY_PY_BODY
    ) as (root, rel):
        seen = rel in offerers_py(root)
        writer = py_is_writer(rel, root)
        reported = rel in unguarded_py(root)
    if (root / rel).exists():
        gate.log_fail("python string-mention probe was not removed")
    if not seen:
        gate.log_fail("CONTROL FAILED: the string-mention probe was not even in the corpus")
    if writer or reported:
        gate.log_fail(
            "CONTROL FAILED: a file that only names the flag in strings was read as a writer "
            "(writer=%s, reported=%s)" % (writer, reported)
        )
    gate.log_pass("CONTROL: naming the flag in strings, with no argv parse, is not a writer")


def test_control_python_exemption_is_the_definition_site(gate):
    """CONTROL. `PY_EXEMPT` holds exactly the shared guard's home, which must exist, must define both functions, and must NOT itself parse the flag -- an exemption that covered a real writer would be a hole with a reason attached."""
    gate.assert_eq(PY_EXEMPT, (".ci/rediacc_ci/quality/shrink_only.py",), "PY_EXEMPT is one path")
    (home,) = PY_EXEMPT
    tree = py_parse(home)
    if tree is None:
        gate.log_fail("%s does not parse" % home)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    if not set(PY_GUARD_FUNCS) <= defined:
        gate.log_fail("%s no longer defines %s" % (home, ", ".join(PY_GUARD_FUNCS)))
    if py_offers_flag(tree):
        gate.log_fail("%s now PARSES the flag, so its exemption hides a writer" % home)
    gate.log_pass("CONTROL: the one Python exemption is the guard's definition site, not a writer")


def test_control_unguarded_reseed_is_detected(gate):
    """CONTROL. Plant a file with the OLD unconditional shape and require detection. Without this, `unguarded()` returning nothing proves nothing about the scanner."""
    with probe("scripts", "zz-composition-control-probe-port", ".ts", UNGUARDED_TS_BODY) as (
        root,
        rel,
    ):
        detected = rel in unguarded(root)
    if (root / rel).exists():
        gate.log_fail("control probe was not removed")
    if not detected:
        gate.log_fail(
            "CONTROL FAILED: an unguarded reseed was NOT detected, so this gate cannot fail"
        )
    gate.log_pass("CONTROL: a planted unguarded reseed is detected")


def test_control_mention_is_not_an_import(gate):
    """CONTROL. A file that only MENTIONS the choke point in prose must NOT count as guarded. Without this, the transitive route above is a substring match masquerading as a check."""
    with probe("scripts", "zz-composition-mention-probe-port", ".ts", MENTION_TS_BODY) as (
        root,
        rel,
    ):
        detected = rel in unguarded(root)
    if (root / rel).exists():
        gate.log_fail("mention probe was not removed")
    if not detected:
        gate.log_fail("CONTROL FAILED: a prose mention was accepted as a guard route")
    gate.log_pass("CONTROL: naming the guard in a comment does not count as consuming it")


def test_control_ts_string_mention_is_not_a_writer(gate):
    """CONTROL. A TypeScript file shaped like the pin driver and its selftest names the flag in comments, a drain command, an `endsWith` argument and template text, and parses no argv, so it is NOT a writer and is not reported. The corpus still SEES it, which keeps this a statement about the token reading rather than about the enumerator."""
    with probe("scripts", "zz-composition-string-probe-port", ".ts", STRING_ONLY_TS_BODY) as (
        root,
        rel,
    ):
        seen = rel in offerers(root)
        writer = ts_is_writer(rel, root)
        reported = rel in unguarded(root)
    if (root / rel).exists():
        gate.log_fail("ts string-mention probe was not removed")
    if not seen:
        gate.log_fail("CONTROL FAILED: the ts string-mention probe was not even in the corpus")
    if writer or reported:
        gate.log_fail(
            "CONTROL FAILED: a TypeScript file that only names the flag in comments and "
            "strings was read as a writer (writer=%s, reported=%s)" % (writer, reported)
        )
    gate.log_pass("CONTROL: naming the flag in TypeScript comments and strings is not a writer")


def test_control_ts_writer_shapes_are_detected(gate):
    """CONTROL, the other direction. Every argv-parse position the token reading claims to recognise, planted unguarded, is read as a writer AND reported. Without this the mention control above is satisfied by a reading that recognises nothing."""
    missed = []
    for label, body in WRITER_TS_BODIES.items():
        with probe("scripts", "zz-composition-writer-probe-port", ".ts", body) as (root, rel):
            if not (ts_is_writer(rel, root) and rel in unguarded(root)):
                missed.append(label)
        if (root / rel).exists():
            gate.log_fail("ts writer probe (%s) was not removed" % label)
    if missed:
        gate.log_fail(
            "CONTROL FAILED: an unguarded TypeScript reseed was NOT detected for: %s"
            % "; ".join(missed)
        )
    gate.log_pass(
        "CONTROL: %d unguarded TypeScript writer shapes are each detected" % len(WRITER_TS_BODIES)
    )


def test_control_ts_guarded_writer_is_not_reported(gate):
    """CONTROL. A TypeScript writer that imports the shared guard is a writer and is NOT reported, so the token reading did not turn the check into one that flags correct work."""
    with probe("scripts", "zz-composition-guarded-probe-port", ".ts", GUARDED_TS_BODY) as (
        root,
        rel,
    ):
        writer = ts_is_writer(rel, root)
        reported = rel in unguarded(root)
    if (root / rel).exists():
        gate.log_fail("ts guarded probe was not removed")
    if not writer:
        gate.log_fail("CONTROL FAILED: a file parsing the flag off process.argv is not a writer")
    if reported:
        gate.log_fail(
            "CONTROL FAILED: a TypeScript writer importing the guard was reported unguarded"
        )
    gate.log_pass("CONTROL: a guarded TypeScript writer is a writer and is not reported")


def test_refusal_end_to_end(gate):
    """BEHAVIOURAL. The one gate that accepts `--baseline`, so the write can be aimed at a copy and the live suppression file is never touched. Proven both directions, and the live file's digest is compared before and after."""
    npx = harness.require_tool("npx", "install node (the lane's setup-workspace step provides it)")
    subject = ROOT / "scripts" / "gates" / "check-em-dash-surfaces.ts"
    live = ROOT / "scripts" / "data" / "em-dash-surfaces-baseline.json"
    if not live.is_file():
        gate.log_fail("%s is missing" % paths.relative_to_root(live))
    before = hashlib.sha256(live.read_bytes()).hexdigest()

    with harness.temp_dir() as tmp:
        snapshot = tmp / "live.json"
        seed = harness.run(
            [
                npx,
                "tsx",
                str(subject),
                FLAG,
                "--baseline",
                str(snapshot),
                "--first-seed",
                "--skip-control",
            ],
            cwd=ROOT,
            timeout=600,
        )
        if seed.rc != 0 or not snapshot.is_file():
            gate.log_fail(
                "could not snapshot the live id set (rc=%d): %s"
                % (seed.rc, seed.err.strip() or seed.out.strip())
            )
        ids = json.loads(snapshot.read_text(encoding="utf-8"))
        if len(ids) < 2:
            gate.log_fail(
                "the snapshot holds %d id(s); the GROWTH fixture below drops one and would "
                "then be indistinguishable from an empty baseline" % len(ids)
            )

        # GROWTH: drop one id from the OLD copy so a real live finding reads as new.
        grow = tmp / "grow.json"
        grow.write_text(json.dumps(ids[1:], indent=2) + "\n", encoding="utf-8")
        rc = harness.run(
            [npx, "tsx", str(subject), FLAG, "--baseline", str(grow), "--skip-control"],
            cwd=ROOT,
            timeout=600,
        ).rc
        gate.assert_eq(rc, 1, "a reseed that would GAIN an id exits non-zero")

        # SHRINK: old copy is a strict superset, so the write is a genuine drain.
        shrink = tmp / "shrink.json"
        shrink.write_text(
            json.dumps(sorted([*ids, "zz/synthetic.json:already.fixed"]), indent=2) + "\n",
            encoding="utf-8",
        )
        rc = harness.run(
            [npx, "tsx", str(subject), FLAG, "--baseline", str(shrink), "--skip-control"],
            cwd=ROOT,
            timeout=600,
        ).rc
        gate.assert_eq(rc, 0, "a genuine shrink is still allowed")

        # MISSING: deleting the baseline must not be a way to switch the rule off.
        absent = tmp / "absent.json"
        rc = harness.run(
            [npx, "tsx", str(subject), FLAG, "--baseline", str(absent), "--skip-control"],
            cwd=ROOT,
            timeout=600,
        ).rc
        gate.assert_eq(rc, 1, "a missing baseline is refused without --first-seed")
        if absent.exists():
            gate.log_fail("the refused run created the baseline anyway")

    after = hashlib.sha256(live.read_bytes()).hexdigest()
    gate.assert_eq(after, before, "the LIVE baseline was never rewritten by this test")
    gate.log_pass("refusal proven end to end; live baseline byte-identical (%s)" % before[:16])


def test_the_two_corpora_do_not_overlap_or_lose_a_file(gate):
    """ADDED BY THE PORT, and it is a claim about the SPLIT rather than about either half. `offerers()` and `offerers_py()` partition `all_offerers()`, and the two floors above are read as covering the whole scan. A pathspec that started admitting a fourth extension, or a suffix test that stopped matching, would leave files in neither half -- unchecked, while both floors stayed
    comfortably green."""
    everything = all_offerers()
    ts, py = offerers(), offerers_py()
    overlap = sorted(set(ts) & set(py))
    lost = sorted(set(everything) - set(ts) - set(py))
    if overlap:
        gate.log_fail("%d file(s) are in BOTH corpora: %s" % (len(overlap), ", ".join(overlap)))
    if lost:
        gate.log_fail(
            "%d offerer(s) are in NEITHER corpus, so no floor and no guard check covers "
            "them: %s" % (len(lost), ", ".join(lost))
        )
    gate.log_pass(
        "the %d offerer(s) partition exactly into %d ts/js and %d python"
        % (len(everything), len(ts), len(py))
    )


def test_this_module_is_not_itself_an_offender(gate):
    """THE SELF-SCANNING CONTROL, which the twin does not need and this port does.

    The twin is a `.sh` file and the corpus is `.ts`/`.js`/`.py`, so the twin is outside its own scan for free. This module is a `.py` file whose whole subject is that flag, and it is outside the scan only because `FLAG` is split and every probe body is rendered -- something a later editor would undo without connecting the two. Nothing in `unguarded_py()` excludes a port BY NAME,
    so the moment the contiguous literal reappears here this file becomes an "unguarded Python baseline writer" and this gate reds tree-wide over its own source.

    MEASURED, not hypothetical. On 2026-09-09 the first cut of this port and of `test_gate_language_policy.py` both landed on the offender list minutes after being written, which is how the rule was rediscovered.
    """
    own = paths.relative_to_root(pathlib.Path(__file__))
    corpus = all_offerers()
    if own in corpus:
        gate.log_fail(
            "%s is in its OWN offender corpus, so this gate now reports its own source. "
            "Keep the flag split (FLAG) and every probe body rendered through %%s." % own
        )
    # AND THE SPLIT MUST STILL PRODUCE THE REAL FLAG. A control that only checks for absence is satisfied by a typo, and a typo would make every probe below invisible to the scan while all four controls kept passing. CHECKED AGAINST THE GUARD, which implements the flag and therefore carries it whole; a literal written here would either be a tautology or a second thing to keep
    # rendered. The oracle was the bash twin until W7 P5 retired it, and the guard is the stronger choice anyway: it proves the rendered flag is the real string AND that the corpus scan above can see it in the subject.
    if GUARD not in corpus:
        gate.log_fail(
            "the rendered flag %r does not appear in %s, so it is a typo -- the probes "
            "below would be invisible to the scan and all four controls would still pass"
            % (FLAG, GUARD)
        )
    gate.assert_eq(
        FLAG in UNGUARDED_PY_BODY and FLAG in UNGUARDED_TS_BODY,
        True,
        "the probe bodies must carry the real flag on disk, or no probe is ever seen",
    )
    gate.log_pass(
        "the flag is rendered (%r), so this port is not in its own %d-file corpus"
        % (FLAG, len(corpus))
    )


def test_control_python_assert_on_argv_is_a_writer(gate):
    """CONTROL. An `assert` that reads the argument vector still parses the flag, so a writer whose only parse sits in one is detected and reported, while the stream asserts of the string-only fixture stay exempt."""
    missed = []
    for label, body in ASSERT_ARGV_PY_BODIES.items():
        with probe(".ci/scripts/quality", "zz_composition_assert_probe_port", ".py", body) as (
            root,
            rel,
        ):
            if not (py_is_writer(rel, root) and rel in unguarded_py(root)):
                missed.append(label)
        if (root / rel).exists():
            gate.log_fail("python assert probe (%s) was not removed" % label)
    if missed:
        gate.log_fail(
            "CONTROL FAILED: a writer parsing the flag inside an assert was NOT detected for: %s"
            % "; ".join(missed)
        )
    if py_offers_flag(ast.parse(STRING_ONLY_PY_BODY)):
        gate.log_fail("CONTROL FAILED: an assert on a captured stream was read as an argv parse")
    if py_offers_flag(ast.parse(COMPLETED_ARGS_PY_BODY)):
        gate.log_fail(
            "CONTROL FAILED: an assert on CompletedProcess.args was read as an argv parse"
        )
    if py_offers_flag(ast.parse(BOUND_FROM_PROC_PY_BODY)):
        gate.log_fail(
            "CONTROL FAILED: an assert on a name bound from CompletedProcess.args was read as an argv parse"
        )
    gate.log_pass(
        "CONTROL: %d assert-on-argv writers are detected; an assert on a stream is not a parse"
        % len(ASSERT_ARGV_PY_BODIES)
    )


def test_string_only_fixture_captures_what_it_asserts_on(gate):
    """The string-only fixture must be a coherent test, not only scannable text: every `subprocess.run` whose result's `.stderr` or `.stdout` it reads captures that stream, or the fixture asserts on None and models a test that could never run."""
    tree = ast.parse(STRING_ONLY_PY_BODY)
    runs = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "run"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "subprocess"
    ]
    read = {
        n.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute) and n.attr in ("stderr", "stdout")
    }
    if not runs:
        gate.log_fail("the string-only fixture no longer calls subprocess.run; update this check")
    for call in runs:
        kw = {k.arg: k.value for k in call.keywords}
        cap = kw.get("capture_output")
        captured = isinstance(cap, ast.Constant) and cap.value is True
        missing = sorted(s for s in read if not captured and s not in kw)
        if missing:
            gate.log_fail(
                "the string-only fixture reads proc.%s from a subprocess.run that does not "
                "capture it, so the stream is None" % "/".join(missing)
            )
    gate.log_pass(
        "the string-only fixture captures every stream it asserts on (%d run call(s))" % len(runs)
    )
