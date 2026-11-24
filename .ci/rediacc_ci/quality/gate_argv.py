"""check:ci-gate-argv -- every quality entry point refuses an argument it does not take.

THE CLASS. `npm run check:ci-record-paths -- --update` exited 0 and did nothing: the entry point read argv by asking about the flags it knew (`"--selftest" in args`) and never looked at what was left. A typo for a real flag (`--write-basline`) does the same, so the gate prints its plain verdict and the caller believes the write happened. PLAN-silent-failure-sweep.md SF1 put `_gate_args.parse` into 147 entry points; this gate keeps it there.

WHAT AN ENTRY POINT MUST BE, read statically from its AST, one of:

  * PARSE: the first statement of its `if __name__ == "__main__":` block is
    `_gate_args.parse("<name>.py", sys.argv[1:], ...)`, every accepted-set keyword a literal tuple (or a module-level name bound to one), so the accepted set is readable without running the script;
  * ARGPARSE: `argparse.ArgumentParser` with `.parse_args(` and no `parse_known_args`, in the entry point or in the `rediacc_ci` module whose `main` the `__main__` block calls;
  * OWN: named in OWN_REFUSAL with its reason, PRINTED every run, and RUN every run with an unknown flag that must exit 2, so the name proves itself rather than being believed.

Anything else is a BYPASS, named with what it does instead: a hand scan (`"--x" in sys.argv`), a `main()` that never receives argv, or no recognisable parse at all.

TWO MORE CHECKS:

  * where no shared parse is the first statement of the `__main__` block, `sys.argv` is read only as `sys.argv[1:]` passed straight into a call. Any other read (`sys.argv[1]`, `len(sys.argv)`, `"--x" in sys.argv`) is a parse the gate cannot see. After a first-statement parse a later read sees an argv the parser already vetted, so it is not flagged there.
  * a PARSE entry point's declared flag must appear as a string somewhere else in the entry point or the module it hands argv to. A declared flag nobody reads is accepted and IGNORED, which is the original failure with a declaration on top. Deliberately loose (any string literal containing the flag counts), because a false positive here would push an author to delete a live flag.

REGISTERED CALLS. Every call that passes arguments to an entry point, in `package.json`, `scripts/ci-runner/manifest.ts`, the workflows and the non-test `.claude` hook sources, is checked against the entry point's declared set, including the `npm run <script> -- <args>` spelling, which appends to the last command of the script. A caller passing an undeclared flag is red here before it is red at run time.

ANTI-VACUITY. Fewer than FLOOR entry points is a refusal: the scan is not seeing the tree. The success line prints the per-form counts and the number of registered calls checked, so a collapse is visible.

SEAMS. GATE_ARGV_SCAN_ROOT points the scan at a fixture tree; OWN_REFUSAL is a parameter of `run` so a test brings its own.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING, TypeGuard

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, controls_first, plant
from rediacc_ci.quality import gate_args, seams

if TYPE_CHECKING:
    from collections.abc import Iterable

ROOT_ENV = "GATE_ARGV_SCAN_ROOT"
QUALITY_REL = ".ci/scripts/quality"
EXTRA_ENTRY_POINTS = ("shape_cluster_diff.py",)
# 175 entry points exist at 2026-11-23; fewer than this and the scan is not seeing the tree.
FLOOR = 150
BOGUS = "--gate-argv-no-such-flag"

# Entry points that refuse an unknown argument through their own code, by name, with why they are not on the shared parser. Each is RUN every gate run with BOGUS and must exit 2, so an entry here that stopped refusing turns red rather than staying exempt.
OWN_REFUSAL = {
    "check_inline_suppressions": (
        "inline_suppressions.argv_refusal takes `--count` with ZERO OR MORE pathspecs and names "
        "the retired --write-baseline and --first-seed by their history; the shared parser's "
        "variadic flag needs at least one value and would lose both messages"
    ),
    "check_scope_mirrors": (
        "`--repin` takes `--all` as its VALUE, and the shared parser refuses a valued flag "
        "whose value starts with `--`, so adopting it would break `--repin --all`"
    ),
}

ACCEPT_KEYWORDS = ("switches", "valued", "equals", "variadic")
CALL_SOURCES = ("package.json", "scripts/ci-runner/manifest.ts")
CALL_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")
HOOK_DIRS = (".claude/hooks", ".claude/rediacc_hooks")
ENTRY_CALL_RE = re.compile(
    r"\.ci/scripts/quality/([A-Za-z0-9_]+)\.py((?:[ \t]+[^ \t\n\"'`;&|)]+)*)"
)
NPM_CALL_RE = re.compile(r"npm run (?:-s |--silent )?([A-Za-z0-9:_-]+) -- ((?:[^\n\"'`;&|)\\]+))")
# A redirection, a shell operator or a comment ends the argument list; `<base-sha>` is a placeholder VALUE, not a redirection.
SHELL_STOP_RE = re.compile(r"^(?:[0-9]?>|<(?![A-Za-z0-9_-]+>)|&&|\|\||[|;&()#])")


@dataclasses.dataclass
class Decl:
    """An entry point's accepted set."""

    switches: tuple[str, ...] = ()
    valued: tuple[str, ...] = ()
    equals: tuple[str, ...] = ()
    variadic: tuple[str, ...] = ()
    positional: str | None = None

    def flags(self) -> tuple[str, ...]:
        return self.switches + self.valued + self.equals + self.variadic


@dataclasses.dataclass
class Entry:
    """What one entry point is, and what is wrong with it."""

    stem: str
    form: str  # parse | argparse | own | bypass
    decl: Decl | None
    problems: list[str]


# -- AST helpers -------------------------------------------------------------


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    out: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _is_sys_argv(node: ast.AST) -> TypeGuard[ast.Attribute]:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "argv"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def _is_argv_tail(node: ast.AST) -> bool:
    """`sys.argv[1:]` exactly."""
    if not (isinstance(node, ast.Subscript) and _is_sys_argv(node.value)):
        return False
    sl = node.slice
    return (
        isinstance(sl, ast.Slice)
        and isinstance(sl.lower, ast.Constant)
        and sl.lower.value == 1
        and sl.upper is None
        and sl.step is None
    )


def stray_argv_reads(tree: ast.AST) -> list[int]:
    """Lines reading `sys.argv` other than as `sys.argv[1:]` passed straight into a call."""
    parents = _parents(tree)
    bad: list[int] = []
    for node in ast.walk(tree):
        if not _is_sys_argv(node):
            continue
        sub = parents.get(node)
        call = parents.get(sub) if sub is not None else None
        if (
            sub is not None
            and _is_argv_tail(sub)
            and isinstance(call, ast.Call)
            and sub in call.args
        ):
            continue
        bad.append(node.lineno)
    return bad


def hand_scans(tree: ast.AST) -> list[int]:
    """Lines testing a flag's membership in argv by hand: `"--x" in sys.argv` / `in argv` / `in args`."""
    out: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        if not any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops):
            continue
        left = node.left
        if not (
            isinstance(left, ast.Constant)
            and isinstance(left.value, str)
            and left.value.startswith("-")
        ):
            continue
        if any(
            _is_sys_argv(comp) or (isinstance(comp, ast.Name) and comp.id in ("argv", "args"))
            for comp in node.comparators
        ):
            out.append(node.lineno)
    return out


def main_block(tree: ast.Module) -> ast.If | None:
    for node in tree.body:
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        ):
            return node
    return None


def _is_parse_call(node: ast.AST | None) -> TypeGuard[ast.Call]:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "parse"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "_gate_args"
    )


def _statement_call(stmt: ast.stmt) -> ast.AST | None:
    if isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign)):
        return stmt.value
    return None


def _module_constants(tree: ast.Module) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            out[node.targets[0].id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            out[node.target.id] = node.value
    return out


def _literal(node: ast.AST, consts: dict[str, ast.AST]) -> object:
    """A literal value, following one module-level name. Raises ValueError when it is not literal."""
    if isinstance(node, ast.Name) and node.id in consts:
        node = consts[node.id]
    return ast.literal_eval(node)


def _parse_first(tree: ast.Module) -> bool:
    block = main_block(tree)
    return bool(block and block.body and _is_parse_call(_statement_call(block.body[0])))


def decl_of_parse(call: ast.Call, consts: dict[str, ast.AST]) -> tuple[Decl | None, list[str]]:
    problems: list[str] = []
    if len(call.args) < 2 or not _is_argv_tail(call.args[1]):
        problems.append(
            "the parse is not handed `sys.argv[1:]`, so it parses something other than the command line"
        )
    decl = Decl()
    for kw in call.keywords:
        try:
            value = _literal(kw.value, consts)
        except ValueError:
            problems.append(
                "`%s=` is not a literal (or a module-level name bound to one), so the accepted set "
                "cannot be read without running the script" % kw.arg
            )
            continue
        if kw.arg in ACCEPT_KEYWORDS:
            if not (isinstance(value, tuple) and all(isinstance(v, str) for v in value)):
                problems.append("`%s=` must be a tuple of strings" % kw.arg)
                continue
            setattr(decl, kw.arg, value)
        elif kw.arg == "positional":
            decl.positional = value if isinstance(value, str) else None
        else:
            problems.append("`%s=` is not a parse keyword" % kw.arg)
    return (None if problems else decl), problems


def delegate_module(tree: ast.Module, block: ast.If, root: pathlib.Path) -> pathlib.Path | None:
    """The `rediacc_ci` module whose attribute the `__main__` block calls (`X.main(...)`), if any."""
    imported: dict[str, str] = {}
    for item in tree.body:
        if (
            isinstance(item, ast.ImportFrom)
            and item.module
            and item.module.startswith("rediacc_ci")
        ):
            for alias in item.names:
                imported[alias.asname or alias.name] = "%s.%s" % (item.module, alias.name)
    # The `__main__` block, plus one hop into a module-level function it calls (`main(sys.argv[1:])` whose body calls `X.main(rest)`).
    local = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    scopes: list[ast.AST] = [block]
    scopes += [
        local[node.func.id]
        for node in ast.walk(block)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in local
    ]
    for node in (n for scope in scopes for n in ast.walk(scope)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id in imported:
                rel = imported[owner.id].replace(".", "/") + ".py"
                path = root / ".ci" / rel
                if path.is_file():
                    return path
    return None


def argparse_decl(src: str) -> Decl | None:
    """The accepted set of an argparse parser in `src`, or None when `src` holds no refusing argparse."""
    if "ArgumentParser(" not in src or ".parse_args(" not in src or "parse_known_args" in src:
        return None
    tree = ast.parse(src)
    decl = Decl(switches=("-h", "--help"))
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ):
            continue
        names = [
            a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        if not names:
            continue
        if not names[0].startswith("-"):
            decl.positional = "<%s>" % names[0]
            continue
        kws = {kw.arg: kw.value for kw in node.keywords}
        action = kws.get("action")
        nargs = kws.get("nargs")
        action_v = action.value if isinstance(action, ast.Constant) else None
        nargs_v = nargs.value if isinstance(nargs, ast.Constant) else None
        if action_v in ("store_true", "store_false", "count", "help", "version", "store_const"):
            decl.switches += tuple(names)
        elif nargs_v in ("*", "+"):
            decl.variadic += tuple(names)
        else:
            decl.valued += tuple(names)
    return decl


def _strings(tree: ast.AST, skip: ast.AST | None = None) -> list[str]:
    skipped = set(ast.walk(skip)) if skip is not None else set()
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n not in skipped
    ]


def analyse(path: pathlib.Path, root: pathlib.Path, own: dict[str, str]) -> Entry:
    stem = path.stem
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        return Entry(stem, "bypass", None, ["cannot be read or parsed (%s)" % exc])
    problems: list[str] = []
    # A stray read AFTER a first-statement parse reads an argv the parser already vetted, so it can neither see nor ignore an unknown argument; it matters only where no shared parse runs first.
    stray = [] if _parse_first(tree) else stray_argv_reads(tree)
    if stray:
        problems.append(
            "reads `sys.argv` at line(s) %s other than as `sys.argv[1:]` handed to a call; "
            "a parse the gate cannot see is a parse that can ignore an argument"
            % ", ".join(map(str, stray))
        )
    block = main_block(tree)
    if block is None:
        return Entry(stem, "bypass", None, [*problems, 'has no `if __name__ == "__main__":` block'])
    consts = _module_constants(tree)
    parse_calls = [n for n in ast.walk(tree) if _is_parse_call(n)]
    first = _statement_call(block.body[0])
    if parse_calls:
        call = parse_calls[0]
        if first is not call:
            problems.append(
                "`_gate_args.parse` is not the first statement of the `__main__` block, so work "
                "runs before an unknown argument is refused"
            )
        decl, decl_problems = decl_of_parse(call, consts)
        problems += decl_problems
        if decl is not None:
            delegate = delegate_module(tree, block, root)
            seen = _strings(tree, skip=call)
            if delegate is not None:
                seen += _strings(ast.parse(delegate.read_text(encoding="utf-8")))
            for flag in decl.flags():
                if flag in ("-h", "--help"):
                    continue
                if not any(flag in s for s in seen):
                    problems.append(
                        "declares %s, which nothing in the entry point or %s reads: it would be "
                        "accepted and ignored. Read it, or drop it from the declaration"
                        % (flag, delegate.relative_to(root) if delegate else "its module")
                    )
        return Entry(stem, "parse", decl, problems)
    if stem in own:
        return Entry(stem, "own", None, problems)
    decl = argparse_decl(src)
    if decl is None:
        delegate = delegate_module(tree, block, root)
        if delegate is not None:
            decl = argparse_decl(delegate.read_text(encoding="utf-8"))
    if decl is not None:
        return Entry(stem, "argparse", decl, problems)
    if "parse_known_args" in src:
        why = "uses `parse_known_args`, which hands an unknown argument back instead of refusing it"
    elif hand_scans(tree):
        why = "scans argv by hand (line %s) and never refuses what is left" % ", ".join(
            map(str, hand_scans(tree))
        )
    elif not any(_is_argv_tail(n) for n in ast.walk(block)):
        why = "its `__main__` block never hands argv to anything, so every argument is dropped"
    else:
        why = "reaches neither `_gate_args.parse` nor a refusing argparse"
    return Entry(
        stem,
        "bypass",
        None,
        [
            *problems,
            "%s. Make `_gate_args.parse(...)` the first statement of the `__main__` block" % why,
        ],
    )


# -- registered calls ----------------------------------------------------------


def entry_points(root: pathlib.Path) -> list[pathlib.Path]:
    base = root / QUALITY_REL
    found = sorted(base.glob("check_*.py"))
    found += [base / name for name in EXTRA_ENTRY_POINTS if (base / name).is_file()]
    return found


def _tokens(text: str) -> list[str]:
    try:
        raw = shlex.split(text, posix=True)
    except ValueError:
        raw = text.split()
    out: list[str] = []
    for tok in raw:
        if SHELL_STOP_RE.match(tok):
            break
        out.append(tok)
    return out


def _call_files(root: pathlib.Path) -> list[pathlib.Path]:
    files = [root / rel for rel in CALL_SOURCES if (root / rel).is_file()]
    for pattern in CALL_GLOBS:
        files += sorted(root.glob(pattern))
    for rel in HOOK_DIRS:
        base = root / rel
        if base.is_dir():
            files += sorted(
                p
                for p in base.rglob("*.py")
                if not p.name.startswith("test") and "tests" not in p.relative_to(base).parts
            )
    return files


def npm_scripts(root: pathlib.Path) -> dict[str, str]:
    pkg = root / "package.json"
    if not pkg.is_file():
        return {}
    data = json.loads(pkg.read_text(encoding="utf-8"))
    return dict(data.get("scripts", {}))


def registered_calls(root: pathlib.Path) -> list[tuple[str, str, list[str]]]:
    """(where, entry stem, argv) for every call that passes arguments to an entry point."""
    calls: list[tuple[str, str, list[str]]] = []
    scripts = npm_scripts(root)
    for path in _call_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(root))
        for m in ENTRY_CALL_RE.finditer(text):
            args = _tokens(m.group(2))
            # Only an argument list that opens with a flag is a call; prose that names an entry point ("check_x.py holds in place.") is not.
            if args and args[0].startswith("-"):
                line = text.count("\n", 0, m.start()) + 1
                calls.append(("%s:%d" % (rel, line), m.group(1), args))
        for m in NPM_CALL_RE.finditer(text):
            target = scripts.get(m.group(1), "")
            last = target.split("&&")[-1]
            hit = ENTRY_CALL_RE.search(last)
            extra = _tokens(m.group(2))
            if hit and extra and extra[0].startswith("-"):
                line = text.count("\n", 0, m.start()) + 1
                calls.append(("%s:%d" % (rel, line), hit.group(1), _tokens(hit.group(2)) + extra))
    return calls


def _gate_args_module():
    """The shared parser itself, so a registered call is judged by the exact code that will judge it at run time: `.ci/scripts/quality/_gate_args.py` only re-exports `rediacc_ci.quality.gate_args`, so the package module is that code."""
    return gate_args


def call_problem(decl: Decl, argv: list[str]) -> str:
    # A shell variable stands for a value the gate cannot see: it stays in place as a bare value, so a valued flag still consumes it and a stray one is still a positional.
    argv = ["shell-value" if a.startswith("$") else a for a in argv]
    return _gate_args_module().problem(
        argv,
        switches=decl.switches,
        valued=decl.valued,
        equals=decl.equals,
        positional=decl.positional,
        variadic=decl.variadic,
    )


# -- the run -----------------------------------------------------------------


def own_refuses(root: pathlib.Path, stem: str) -> str:
    """'' when the named script exits 2 on BOGUS; else what it did."""
    script = root / QUALITY_REL / (stem + ".py")
    try:
        proc = subprocess.run(
            [sys.executable, str(script), BOGUS],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "could not be run (%s)" % exc
    if proc.returncode != 2:
        return "exited %d on %s, not 2" % (proc.returncode, BOGUS)
    return ""


def run(root: pathlib.Path, own: dict[str, str] | None = None, floor: int = FLOOR) -> int:
    own = OWN_REFUSAL if own is None else own
    files = entry_points(root)
    if len(files) < floor:
        log.error(
            "gate-argv: %d entry point(s) under %s, floor %d: the scan is not seeing the tree, "
            "so its green would mean nothing" % (len(files), root / QUALITY_REL, floor)
        )
        return 1
    entries = [analyse(p, root, own) for p in files]
    by_stem = {e.stem: e for e in entries}
    findings: list[str] = []
    for e in entries:
        findings += ["%s/%s.py: %s" % (QUALITY_REL, e.stem, problem) for problem in e.problems]
        if e.form == "bypass" and not e.problems:
            findings.append("%s/%s.py: bypasses the parser" % (QUALITY_REL, e.stem))
    for stem in sorted(own):
        if stem not in by_stem:
            findings.append(
                "OWN_REFUSAL names %s, which is not an entry point: delete the entry" % stem
            )
            continue
        if by_stem[stem].form != "own":
            findings.append(
                "OWN_REFUSAL names %s, which now carries `_gate_args.parse`: delete the entry"
                % stem
            )
            continue
        issue = own_refuses(root, stem)
        if issue:
            findings.append("%s/%s.py (OWN_REFUSAL): %s" % (QUALITY_REL, stem, issue))
    calls = registered_calls(root)
    checked = 0
    for where, stem, argv in calls:
        entry = by_stem.get(stem)
        if entry is None or entry.decl is None:
            continue
        checked += 1
        issue = call_problem(entry.decl, argv)
        if issue:
            findings.append(
                "%s: calls %s.py with %r, which it refuses (%s). Fix the caller or declare the flag "
                "the module really reads" % (where, stem, " ".join(argv), issue)
            )
    counts = {
        form: sum(1 for e in entries if e.form == form)
        for form in ("parse", "argparse", "own", "bypass")
    }
    shape = (
        "%d entry points: %d shared parse, %d argparse, %d own refusal, %d bypass; %d registered call(s) checked"
        % (
            len(entries),
            counts["parse"],
            counts["argparse"],
            counts["own"],
            counts["bypass"],
            checked,
        )
    )
    for stem in sorted(own):
        if stem in by_stem:
            print(
                "  own refusal (exempt by name, run with %s): %s -- %s" % (BOGUS, stem, own[stem])
            )
    if findings:
        for f in findings:
            log.error(f)
        log.error("gate-argv: %d finding(s). %s" % (len(findings), shape))
        return 1
    log.info("gate-argv: OK. %s" % shape)
    return 0


def scan_root() -> pathlib.Path:
    return seams.scratch_root(ROOT_ENV, os.environ.get(ROOT_ENV, "")) or paths.repo_root()


# -- selftest ------------------------------------------------------------------

SHIM = (
    "import sys\nimport _cipath\nimport _gate_args\n\n"
    'if __name__ == "__main__":\n'
    '    _gate_args.parse("%s.py", sys.argv[1:], switches=("--selftest",))\n'
    "    raise SystemExit(main(sys.argv[1:]))\n\n"
    'def main(argv):\n    return 1 if "--selftest" in argv else 0\n'
)


def _entry_of(text: str, own: dict[str, str] | None = None, stem: str = "check_x") -> Entry:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / QUALITY_REL).mkdir(parents=True)
        path = root / QUALITY_REL / (stem + ".py")
        path.write_text(text, encoding="utf-8")
        return analyse(path, root, own or {})


def selftest(verbose: bool = True) -> int:
    ctl = Controls("gate-argv", floor=14, verbose=verbose)
    ctl.check(
        "CONTROL: the shared parse as the first statement is accepted",
        _entry_of(SHIM % "check_x").problems,
        [],
    )
    ctl.check(
        "CONTROL: ...and classified as the parse form", _entry_of(SHIM % "check_x").form, "parse"
    )
    ctl.check(
        'PLANT: `if "--x" in sys.argv` is a bypass',
        _entry_of(
            'import sys\nif __name__ == "__main__":\n    if "--x" in sys.argv:\n        pass\n'
        ).form,
        "bypass",
    )
    ctl.truthy(
        "PLANT: ...and names the stray sys.argv read",
        any(
            "reads `sys.argv`" in p
            for p in _entry_of(
                'import sys\nif __name__ == "__main__":\n    if "--x" in sys.argv:\n        pass\n'
            ).problems
        ),
    )
    never = _entry_of(
        'def main():\n    return 0\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
    )
    ctl.check("PLANT: a main() that never reads argv is a bypass", never.form, "bypass")
    ctl.truthy(
        "PLANT: ...named as dropping every argument",
        any("never hands argv" in p for p in never.problems),
    )
    known = _entry_of(
        'import argparse, sys\ndef main():\n    p = argparse.ArgumentParser()\n    p.add_argument("--x")\n'
        '    a, rest = p.parse_known_args()\n    return 0\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
    )
    ctl.check("PLANT: parse_known_args is a bypass", known.form, "bypass")
    plain = _entry_of(
        'import argparse, sys\ndef main():\n    p = argparse.ArgumentParser()\n    p.add_argument("--x")\n'
        '    p.add_argument("--y", action="store_true")\n    p.parse_args()\n    return 0\n\n'
        'if __name__ == "__main__":\n    raise SystemExit(main())\n'
    )
    ctl.check("CONTROL: plain argparse is accepted", (plain.form, plain.problems), ("argparse", []))
    plain_decl = plain.decl or Decl()
    ctl.check(
        "CONTROL: ...with --x valued and --y a switch",
        (plain_decl.valued, "--y" in plain_decl.switches),
        (("--x",), True),
    )
    late = _entry_of(
        plant(SHIM, "    _gate_args.parse", "    print(1)\n    _gate_args.parse") % "check_x"
    )
    ctl.truthy(
        "PLANT: a parse after other work is named",
        any("not the first statement" in p for p in late.problems),
    )
    unread = _entry_of(plant(SHIM, '("--selftest",)', '("--selftest", "--update")') % "check_x")
    ctl.truthy(
        "PLANT: a declared flag nothing reads is named",
        any("declares --update" in p for p in unread.problems),
    )
    dyn = _entry_of(plant(SHIM, '("--selftest",)', 'tuple(x for x in ["--selftest"])') % "check_x")
    ctl.truthy(
        "PLANT: a non-literal accepted set is named",
        any("not a literal" in p for p in dyn.problems),
    )
    ctl.check(
        "CONTROL: an OWN_REFUSAL name is classified own, not bypass",
        _entry_of(
            'import sys\nif __name__ == "__main__":\n    raise SystemExit(m.main(sys.argv[1:]))\n',
            own={"check_x": "r"},
        ).form,
        "own",
    )
    decl = Decl(switches=("--selftest",), valued=("--root",))
    ctl.truthy(
        "PLANT: a registered call with an undeclared flag is refused",
        call_problem(decl, ["--update"]),
    )
    ctl.check(
        "CONTROL: a registered call with declared flags passes",
        call_problem(decl, ["--selftest", "--root", "x"]),
        "",
    )
    ctl.check(
        "CONTROL: a shell redirection ends the argument list",
        _tokens("--selftest 2>&1 | tee x"),
        ["--selftest"],
    )
    return 0 if ctl.report() else 1


def main(argv: Iterable[str] | None = None) -> int:
    args = list(argv or [])
    if args == ["--selftest"]:
        return selftest()
    # Controls first, every run: the registry runs the bare path, so a `--selftest &&` leg is not where the controls live.
    refusal = controls_first("gate argv", lambda: selftest(verbose=False))
    if refusal:
        return refusal
    return run(scan_root())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
