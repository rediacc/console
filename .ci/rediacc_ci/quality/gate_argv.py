"""check:ci-gate-argv -- every quality entry point refuses an argument it does not take.

THE CLASS. `npm run check:ci-record-paths -- --update` exited 0 and did nothing: the entry point read argv by asking about the flags it knew (`"--selftest" in args`) and never looked at what was left. A typo for a real flag (`--write-basline`) does the same, so the gate prints its plain verdict and the caller believes the write happened. PLAN-silent-failure-sweep.md SF1 put `_gate_args.parse` into 147 entry points; this gate keeps it there.

WHICH ENTRY POINTS. The ones the registry really runs. Every `run` in `scripts/ci-runner/gates.lock.json` is expanded through the `npm run <script>` it names (recursively, through package.json), and every Python entry the expansion reaches is judged in the form it is invoked:

  * MODULE: `python3 -m rediacc_ci.<pkg>.<name>`, judged on `.ci/rediacc_ci/<pkg>/<name>.py`;
  * SHIM: `.ci/scripts/quality/check_<name>.py`, judged on the shim;
  * SCRIPT: any other `.ci/**.py` run by path, judged on that file.

Every `.ci/scripts/quality/check_*.py` shim is judged as well, whether or not the lock runs it, because a human can still call it. Until 2026-11-27 ONLY the shims were judged, while CI and the runner called most gates as modules: `python3 -m rediacc_ci.setup.port_parity --gate-argv-no-such-flag` exited 0 with the shim scan green (finding #d78d1ae3).

WHAT AN ENTRY POINT MUST BE, read statically from its AST, one of:

  * PARSE: the first statement of its `if __name__ == "__main__":` block, after any imports, is
    `_gate_args.parse("<name>.py", sys.argv[1:], ...)` (a shim) or `gate_args.parse(...)` (a module), every accepted-set keyword a literal tuple (or a module-level name bound to one), so the accepted set is readable without running the script;
  * ARGPARSE: `argparse.ArgumentParser` with `.parse_args(` and no `parse_known_args`, in the entry point or in the `rediacc_ci` module whose `main` the `__main__` block calls;
  * OWN: named in OWN_REFUSAL with its reason, PRINTED every run, and RUN every run with an unknown flag that must exit 2, so the name proves itself rather than being believed.

Anything else is a BYPASS, named with what it does instead: a hand scan (`"--x" in sys.argv`), a `main()` that never receives argv, or no recognisable parse at all.

KNOWN BYPASS DEBT. KNOWN_BYPASS names, with a `BLOCKER:` reason each, the lock-run entries that were bypasses when the module scan was introduced and lie outside the change that introduced it. It is SHRINK-ONLY: an entry is PRINTED every run, a NEW bypass is red (do not add it to the list; give the entry a parse), and an entry that stops being a bypass is red too, telling the author to delete its line, so the list can only drain.

TWO MORE CHECKS:

  * where no shared parse is the first statement of the `__main__` block, `sys.argv` is read only as `sys.argv[1:]` passed straight into a call. Any other read (`sys.argv[1]`, `len(sys.argv)`, `"--x" in sys.argv`) is a parse the gate cannot see. After a first-statement parse a later read sees an argv the parser already vetted, so it is not flagged there.
  * a PARSE entry point's declared flag must appear as a string somewhere else in the entry point or the module it hands argv to. A declared flag nobody reads is accepted and IGNORED, which is the original failure with a declaration on top. Deliberately loose (any string literal containing the flag counts), because a false positive here would push an author to delete a live flag.

REGISTERED CALLS. Every call that passes arguments to an entry point, in `package.json`, `scripts/ci-runner/manifest.ts`, the workflows and the non-test `.claude` hook sources, is checked against the entry point's declared set, including the `npm run <script> -- <args>` spelling, which appends to the last command of the script. A caller passing an undeclared flag is red here before it is red at run time.

ANTI-VACUITY. An unreadable lock, or fewer than FLOOR entry points the lock runs, is a refusal: the scan is not seeing the tree. A lock entry naming a file that does not exist is a finding. The success line prints the per-kind and per-form counts and the number of registered calls checked, so a collapse is visible.

SEAMS. GATE_ARGV_SCAN_ROOT points the scan at a fixture tree; OWN_REFUSAL and KNOWN_BYPASS are parameters of `run` so a test brings its own.
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import io
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
LOCK_REL = "scripts/ci-runner/gates.lock.json"
EXTRA_ENTRY_POINTS = ("shape_cluster_diff.py",)
# The FLOOR counts the distinct entry points the LOCK runs (modules, shims and scripts), not the shim directory: CI runs the lock, and the unreferenced shims are being retired (CL-GA2), which cannot move this count. Measured 2026-11-27: 206 (190 module, 10 shim, 6 script). The floor sits about 12% under that, the margin the old shim-only floor kept (150 against 172). Fewer than this and the scan is not seeing the tree.
FLOOR = 180
BOGUS = "--gate-argv-no-such-flag"

INLINE_SUPPRESSIONS_WHY = (
    "inline_suppressions.argv_refusal takes `--count` with ZERO OR MORE pathspecs and names "
    "the retired --write-baseline and --first-seed by their history; the shared parser's "
    "variadic flag needs at least one value and would lose both messages"
)
SCOPE_MIRRORS_WHY = (
    "`--repin` takes `--all` as its VALUE, and the shared parser refuses a valued flag "
    "whose value starts with `--`, so adopting it would break `--repin --all`"
)

# Entry points that refuse an unknown argument through their own code, by name (a shim's stem or a module's dotted name), with why they are not on the shared parser. Each is RUN every gate run with BOGUS and must exit 2, so an entry here that stopped refusing turns red rather than staying exempt.
OWN_REFUSAL = {
    "check_inline_suppressions": INLINE_SUPPRESSIONS_WHY,
    "check_scope_mirrors": SCOPE_MIRRORS_WHY,
    "rediacc_ci.quality.inline_suppressions": INLINE_SUPPRESSIONS_WHY,
    "rediacc_ci.quality.scope_mirrors": SCOPE_MIRRORS_WHY,
    "rediacc_ci.quality.cli_contract": (
        "its `main` refuses anything but `--selftest` and `--no-build` with exit 2 by hand; "
        "BLOCKER: outside #d78d1ae3's file set, so it is proved by running it rather than moved "
        "onto the shared parser here"
    ),
    "rediacc_ci.quality.python_types": (
        "its `main` refuses anything but `--selftest`, `--write-baseline` and `--first-seed` "
        "with exit 2 by hand; BLOCKER: the file is CL-CR2C's this round, so it is proved by "
        "running it rather than moved onto the shared parser here"
    ),
    "rediacc_ci.quality.env_register": (
        "`parse_args` raises RefusalError on any malformed argument and `main` maps it to "
        "exit 2; its grouped `<module> <names...> --class ... ++` grammar is not one the "
        "shared parser can declare"
    ),
    "rediacc_ci.quality.region_consistency": (
        "its `main` reads `--root DIR` and `--live` by hand and refuses whatever is left with "
        "exit 2; BLOCKER: outside #d78d1ae3's file set, so it is proved by running it rather "
        "than moved onto the shared parser here"
    ),
    ".ci/rediacc_ci/core_lease.py": (
        "argparse refuses an unknown argument with exit 2 (`parse_args(None)` reads the command "
        "line itself, which the static form cannot see), and its one other `sys.argv` read records "
        "the command line in the lease sidecar rather than parsing it"
    ),
    "rediacc_ci.ops.login_bench": (
        "`parse_target` raises LoginError(rc=2) on any unexpected argument before a credential "
        "is read; the mail-token mode takes two or three bare positionals, which the shared "
        "parser cannot tell from a typo"
    ),
}

# SHRINK-ONLY: lock-run entries that were bypasses when the module scan arrived (2026-11-27) and lie outside #d78d1ae3's file set. Each is PRINTED every run; a new bypass is red (do not add it here, give the entry a parse) and an entry that stops being a bypass is red until its line is deleted.
_DEBT_WHY = "BLOCKER: outside #d78d1ae3's file set; %s"
KNOWN_BYPASS = {
    ".ci/rediacc_ci/check_pytest.py": _DEBT_WHY
    % "`unknown_args` refuses an unread argument before anything runs, but with exit 1, not the contract's 2",
    ".ci/rediacc_ci/deploy/write_once_guard_check.py": _DEBT_WHY % "`main(_argv)` never reads argv",
    ".ci/rediacc_ci/release/install_script_check.py": _DEBT_WHY % "`main(_argv)` never reads argv",
    ".ci/rediacc_ci/security/ci_workflow_invariants.py": _DEBT_WHY % "`main` does `del argv`",
    ".ci/scripts/security/check_workflow_gates.py": _DEBT_WHY
    % "it hands argv to `workflow_gates.main`, which does `del argv`",
    "rediacc_ci.private.run_account": _DEBT_WHY
    % "`stage_of` reads `$1` and ignores `$2` onward, by its own docstring",
    "rediacc_ci.proxies.unit_tests": _DEBT_WHY
    % "`main` reads `argv[0]` and `argv[1]` as positionals and ignores the rest, so a flag becomes the workspace",
    "rediacc_ci.private.run_renet": _DEBT_WHY
    % "`parse_argv` drops every argument after the stage it does not recognise, by its own docstring",
    "rediacc_ci.proxies.cli_manifest": _DEBT_WHY
    % "`main` reads only `argv[0] == --selftest` and runs the proxy on anything else",
    "rediacc_ci.proxies.docker_prepull": _DEBT_WHY
    % "`main` reads only `argv[0] == --selftest` and runs the proxy on anything else",
    "rediacc_ci.proxies.ensure_nfpm": _DEBT_WHY
    % "`main` reads only `argv[0] == --selftest` and runs the proxy on anything else",
    "rediacc_ci.proxies.go_unit": _DEBT_WHY
    % "`main` reads only `argv[0] == --selftest` and runs the proxy on anything else",
    "rediacc_ci.proxies.license_e2e": _DEBT_WHY
    % "`main` reads only `argv[0] == --selftest` and runs the proxy on anything else",
    "rediacc_ci.proxies.linux_packages": _DEBT_WHY
    % "`main` reads only `argv[0] == --selftest` and runs the proxy on anything else",
    "rediacc_ci.proxies.ops_host_check": _DEBT_WHY
    % "`main` reads only `argv[0] == --selftest` and runs the proxy on anything else",
    "rediacc_ci.proxies.rdc_update": _DEBT_WHY
    % "`main` reads only `argv[0] == --selftest` and runs the proxy on anything else",
    "rediacc_ci.security.actionlint": _DEBT_WHY % "`main` does `del argv`",
    "rediacc_ci.security.audit": _DEBT_WHY % "`main` does `del argv`",
    "rediacc_ci.security.check_commands": _DEBT_WHY % "`main` does `del argv`",
    "rediacc_ci.security.shellcheck": _DEBT_WHY % "`main` does `del argv`",
    "rediacc_ci.security.shfmt": _DEBT_WHY % "`main` does `del argv`",
    "rediacc_ci.setup.tools": _DEBT_WHY
    % "`main` tests `--selftest`, `--report` and `--install-plan` by membership and ignores the rest",
    "rediacc_ci.testrun.onprem_lane": _DEBT_WHY
    % "`main` hands argv to the scenarios runner only after the stack has started",
}

ACCEPT_KEYWORDS = ("switches", "valued", "equals", "variadic")
CALL_SOURCES = ("package.json", "scripts/ci-runner/manifest.ts")
CALL_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")
HOOK_DIRS = (".claude/hooks", ".claude/rediacc_hooks")
ENTRY_CALL_RE = re.compile(
    r"\.ci/scripts/quality/([A-Za-z0-9_]+)\.py((?:[ \t]+[^ \t\n\"'`;&|)]+)*)"
)
# `python3 -m rediacc_ci.<pkg>.<name> <args>`: the module form CI and the runner use.
MODULE_CALL_RE = re.compile(
    r"(?:^|[\s\"'`(])-m[ \t]+(rediacc_ci(?:\.[A-Za-z0-9_]+)+)((?:[ \t]+[^ \t\n\"'`;&|)]+)*)"
)
# Any `.ci/**.py` run by path; one under QUALITY_REL is a shim, anything else a script.
SCRIPT_RE = re.compile(r"(?<![A-Za-z0-9_/.-])(\.ci/[A-Za-z0-9_/.-]+\.py)")
NPM_RUN_RE = re.compile(r"npm run (?:-s |--silent )?([A-Za-z0-9:_-]+)")
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

    stem: (
        str  # the entry's key: a shim's stem, a module's dotted name, a script's repo-relative path
    )
    form: str  # parse | argparse | own | debt | bypass
    decl: Decl | None
    problems: list[str]


@dataclasses.dataclass(frozen=True)
class Target:
    """One Python entry point and how it is invoked."""

    key: str
    kind: str  # module | shim | script
    path: pathlib.Path


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


# A shim imports the parser as `_gate_args` (the `.ci/scripts/quality/_gate_args.py` re-export); a module imports `rediacc_ci.quality.gate_args` itself.
PARSER_NAMES = ("_gate_args", "gate_args")


def _is_parse_call(node: ast.AST | None) -> TypeGuard[ast.Call]:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "parse"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in PARSER_NAMES
    )


def _first_work(block: ast.If) -> ast.stmt | None:
    """The first statement of the `__main__` block that is not an import: a module imports the parser inside the block, and an import does no work an unknown argument could ride."""
    for stmt in block.body:
        if not isinstance(stmt, (ast.Import, ast.ImportFrom)):
            return stmt
    return None


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
    first = _first_work(block) if block is not None else None
    return first is not None and _is_parse_call(_statement_call(first))


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


def analyse(
    path: pathlib.Path,
    root: pathlib.Path,
    own: dict[str, str],
    key: str | None = None,
    debt: dict[str, str] | None = None,
) -> Entry:
    stem = path.stem if key is None else key
    if stem in own or stem in (debt or {}):
        # Proved by RUNNING it (own) or listed as debt: the static problems are what the name already admits, so they are not reported twice. The form is still read, so an entry that would now pass on its own is returned as such and `run` names its line as stale.
        inner = analyse(path, root, {}, key=stem)
        if inner.form in ("parse", "argparse") and not inner.problems:
            return inner
        return Entry(stem, "own" if stem in own else "debt", None, [])
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
    first_stmt = _first_work(block)
    first = _statement_call(first_stmt) if first_stmt is not None else None
    if parse_calls:
        call = parse_calls[0]
        if first is not call:
            problems.append(
                "the shared parse is not the first statement of the `__main__` block, so work "
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
            "%s. Make the shared parse (`_gate_args.parse(...)` in a shim, `gate_args.parse(...)` "
            "in a module) the first statement of the `__main__` block" % why,
        ],
    )


# -- the population ------------------------------------------------------------


def entry_points(root: pathlib.Path) -> list[pathlib.Path]:
    """Every shim in QUALITY_REL, run by the lock or not."""
    base = root / QUALITY_REL
    found = sorted(base.glob("check_*.py"))
    found += [base / name for name in EXTRA_ENTRY_POINTS if (base / name).is_file()]
    return found


def expand_npm(command: str, scripts: dict[str, str], depth: int = 6) -> str:
    """`command` with every `npm run <script>` it names replaced by the script's body, recursively; a name package.json lacks, or a cycle, stays as written."""
    out = command
    seen: set[str] = set()
    for _ in range(depth):
        changed = False
        for m in list(NPM_RUN_RE.finditer(out)):
            name = m.group(1)
            if name in scripts and name not in seen:
                seen.add(name)
                out = out[: m.start()] + "( " + scripts[name] + " )" + out[m.end() :]
                changed = True
                break
        if not changed:
            break
    return out


def targets_of(command: str, root: pathlib.Path) -> list[Target]:
    """Every Python entry point one expanded command invokes, in the form it invokes it."""
    found: list[Target] = []
    for m in MODULE_CALL_RE.finditer(command):
        dotted = m.group(1)
        found.append(Target(dotted, "module", root / ".ci" / (dotted.replace(".", "/") + ".py")))
    for m in SCRIPT_RE.finditer(command):
        rel = m.group(1)
        if rel.startswith(QUALITY_REL + "/"):
            found.append(Target(pathlib.PurePosixPath(rel).stem, "shim", root / rel))
        else:
            found.append(Target(rel, "script", root / rel))
    return found


def lock_targets(root: pathlib.Path) -> list[Target] | None:
    """The distinct entry points the lock runs, or None when the lock cannot be read."""
    try:
        gates = json.loads((root / LOCK_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(gates, list):
        return None
    scripts = npm_scripts(root)
    out: dict[str, Target] = {}
    for gate in gates:
        run_field = gate.get("run", "") if isinstance(gate, dict) else ""
        for target in targets_of(expand_npm(str(run_field), scripts), root):
            out.setdefault(target.key, target)
    return sorted(out.values(), key=lambda t: (t.kind, t.key))


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


# -- registered calls ----------------------------------------------------------


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


def _in_comment(text: str, pos: int) -> bool:
    """Whether the line holding `pos` is a comment line (`#`, `//` or a block-comment `*`) before it."""
    start = text.rfind("\n", 0, pos) + 1
    return text[start:pos].lstrip().startswith(("#", "//", "* ", "/*"))


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
    """(where, entry key, argv) for every call that passes arguments to an entry point: a shim by its stem, a module by its dotted name."""
    calls: list[tuple[str, str, list[str]]] = []
    scripts = npm_scripts(root)
    for path in _call_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = str(path.relative_to(root))
        for m in ENTRY_CALL_RE.finditer(text):
            args = _tokens(m.group(2))
            # Only an argument list that carries a flag is a call; prose that names an entry point ("check_x.py holds in place.") carries none. A comment line is prose whatever dash token ends it ("# see check_x.py for details -h"), so it is never judged (per-commit review 8dee6a3b.1).
            if _in_comment(text, m.start()):
                continue
            if any(a.startswith("-") for a in args):
                line = text.count("\n", 0, m.start()) + 1
                calls.append(("%s:%d" % (rel, line), m.group(1), args))
        for m in MODULE_CALL_RE.finditer(text):
            if _in_comment(text, m.start()):
                continue
            args = _tokens(m.group(2))
            if any(a.startswith("-") for a in args):
                line = text.count("\n", 0, m.start()) + 1
                calls.append(("%s:%d" % (rel, line), m.group(1), args))
        for m in NPM_CALL_RE.finditer(text):
            target = scripts.get(m.group(1), "")
            last = target.split("&&")[-1]
            hit = ENTRY_CALL_RE.search(last) or MODULE_CALL_RE.search(last)
            extra = _tokens(m.group(2))
            if hit and any(a.startswith("-") for a in extra):
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


def own_refuses(root: pathlib.Path, target: Target) -> str:
    """'' when the entry, invoked in its own form, exits 2 on BOGUS; else what it did."""
    if target.kind == "module":
        argv = [sys.executable, "-m", target.key, BOGUS]
        env = dict(os.environ, PYTHONPATH=str(root / ".ci"))
    else:
        argv = [sys.executable, str(target.path), BOGUS]
        env = None
    try:
        proc = subprocess.run(
            argv,
            cwd=str(root),
            env=env,
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


def _call_name(target: Target) -> str:
    """How a call names the entry: a shim by its file name, a module by its dotted name, a script by its path."""
    return target.key + ".py" if target.kind == "shim" else target.key


def _where(root: pathlib.Path, target: Target) -> str:
    if target.kind == "module":
        return "%s (python3 -m %s)" % (_rel(root, target.path), target.key)
    return _rel(root, target.path)


def population(
    root: pathlib.Path,
) -> tuple[list[Target] | None, list[Target]]:
    """(the entries the lock runs or None, every entry judged: those plus the shims the lock does not run)."""
    from_lock = lock_targets(root)
    judged: dict[str, Target] = {t.key: t for t in from_lock or []}
    for path in entry_points(root):
        judged.setdefault(path.stem, Target(path.stem, "shim", path))
    return from_lock, sorted(judged.values(), key=lambda t: (t.kind, t.key))


def run(
    root: pathlib.Path,
    own: dict[str, str] | None = None,
    floor: int = FLOOR,
    debt: dict[str, str] | None = None,
) -> int:
    own = OWN_REFUSAL if own is None else own
    debt = KNOWN_BYPASS if debt is None else debt
    from_lock, targets = population(root)
    if from_lock is None:
        log.error(
            "gate-argv: cannot read %s as a list of gates: the scan is not seeing the tree, so "
            "its green would mean nothing" % (root / LOCK_REL)
        )
        return 1
    if len(from_lock) < floor:
        log.error(
            "gate-argv: %d entry point(s) run by %s, floor %d: the scan is not seeing the tree, "
            "so its green would mean nothing" % (len(from_lock), root / LOCK_REL, floor)
        )
        return 1
    findings: list[str] = []
    present = [t for t in targets if t.path.is_file()]
    findings += [
        "%s: the lock runs it as %s, and the file does not exist" % (_rel(root, t.path), t.kind)
        for t in targets
        if not t.path.is_file()
    ]
    entries = [analyse(t.path, root, own, key=t.key, debt=debt) for t in present]
    by_key = {e.stem: e for e in entries}
    target_of = {t.key: t for t in present}
    for e in entries:
        where = _where(root, target_of[e.stem])
        findings += ["%s: %s" % (where, problem) for problem in e.problems]
        if e.form == "bypass" and not e.problems:
            findings.append("%s: bypasses the parser" % where)
    for key in sorted(own):
        if key not in by_key:
            findings.append(
                "OWN_REFUSAL names %s, which is not an entry point: delete the entry" % key
            )
            continue
        if by_key[key].form != "own":
            findings.append(
                "OWN_REFUSAL names %s, which now passes on its own (shared parse or argparse): delete the entry"
                % key
            )
            continue
        issue = own_refuses(root, target_of[key])
        if issue:
            findings.append("%s (OWN_REFUSAL): %s" % (_where(root, target_of[key]), issue))
    for key in sorted(debt):
        if key not in by_key:
            findings.append(
                "KNOWN_BYPASS names %s, which is not an entry point any more: delete its line" % key
            )
        elif by_key[key].form != "debt":
            findings.append(
                "KNOWN_BYPASS names %s, which now refuses an unknown argument (%s): delete its line "
                "so the debt list keeps shrinking" % (key, by_key[key].form)
            )
    calls = registered_calls(root)
    checked = 0
    for where, key, argv in calls:
        entry = by_key.get(key)
        if entry is None or entry.decl is None:
            continue
        checked += 1
        issue = call_problem(entry.decl, argv)
        if issue:
            findings.append(
                "%s: calls %s with %r, which it refuses (%s). Fix the caller or declare the flag "
                "the module really reads"
                % (where, _call_name(target_of[key]), " ".join(argv), issue)
            )
    counts = {
        form: sum(1 for e in entries if e.form == form)
        for form in ("parse", "argparse", "own", "debt", "bypass")
    }
    kinds = {
        kind: sum(1 for t in from_lock if t.kind == kind) for kind in ("module", "shim", "script")
    }
    lock_keys = {t.key for t in from_lock}
    shape = (
        "%d entry points (%d the lock runs: %d module, %d shim, %d script; %d shim(s) the lock does "
        "not run): %d shared parse, %d argparse, %d own refusal, %d known-bypass debt, %d bypass; "
        "%d registered call(s) checked"
        % (
            len(entries),
            len(from_lock),
            kinds["module"],
            kinds["shim"],
            kinds["script"],
            sum(1 for t in targets if t.key not in lock_keys),
            counts["parse"],
            counts["argparse"],
            counts["own"],
            counts["debt"],
            counts["bypass"],
            checked,
        )
    )
    for key in sorted(own):
        if key in by_key:
            print("  own refusal (exempt by name, run with %s): %s -- %s" % (BOGUS, key, own[key]))
    for key in sorted(debt):
        if key in by_key and by_key[key].form == "debt":
            print(
                "  known bypass (shrink-only debt; give it a parse and delete its line): %s -- %s"
                % (key, debt[key])
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


# A module that reads `--selftest` by position and runs on anything else: the shape `setup.port_parity` had, which the shim-only scan never saw.
MODULE_IGNORES = (
    "import sys\n\n"
    'def main(argv):\n    return 1 if argv and argv[0] == "--selftest" else 0\n\n'
    'if __name__ == "__main__":\n    raise SystemExit(main(sys.argv[1:]))\n'
)
MODULE_REFUSES = MODULE_IGNORES.replace(
    'if __name__ == "__main__":\n',
    'if __name__ == "__main__":\n    from rediacc_ci.quality import gate_args\n\n'
    '    gate_args.parse("x.py", sys.argv[1:], switches=("--selftest",))\n',
)
MODULE_KEY = "rediacc_ci.quality.gate_argv_fixture"


def fixture_tree(
    root: pathlib.Path, module_text: str, run_field: str | None = None
) -> pathlib.Path:
    """A scan root whose lock runs one module by `python3 -m`, and which holds no shim at all."""
    module = root / ".ci" / (MODULE_KEY.replace(".", "/") + ".py")
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_text(module_text, encoding="utf-8")
    (root / QUALITY_REL).mkdir(parents=True, exist_ok=True)
    lock = root / LOCK_REL
    lock.parent.mkdir(parents=True, exist_ok=True)
    run_field = run_field or "PYTHONPATH=.ci python3 -m %s" % MODULE_KEY
    lock.write_text(json.dumps([{"id": "check:ci-x", "run": run_field}]), encoding="utf-8")
    return root


def _quiet_run(root: pathlib.Path) -> int:
    """`run` over a fixture, its report swallowed: the verdict is what the control reads."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return run(root, own={}, floor=1, debt={})


def selftest(verbose: bool = True) -> int:
    ctl = Controls("gate-argv", floor=22, verbose=verbose)
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
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture_tree(pathlib.Path(tmp), MODULE_IGNORES)
        path = root / ".ci" / (MODULE_KEY.replace(".", "/") + ".py")
        ctl.check(
            "PLANT: a module the lock runs that ignores an unknown flag is a bypass",
            analyse(path, root, {}, key=MODULE_KEY).form,
            "bypass",
        )
        ctl.check("PLANT: ...and the run over a lock that runs it is red", _quiet_run(root), 1)
        ctl.check(
            "CONTROL: ...the shim-only population it replaces holds nothing here",
            entry_points(root),
            [],
        )
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture_tree(pathlib.Path(tmp), MODULE_REFUSES)
        path = root / ".ci" / (MODULE_KEY.replace(".", "/") + ".py")
        refusing = analyse(path, root, {}, key=MODULE_KEY)
        ctl.check(
            "CONTROL: a module whose block imports the parser then parses first is accepted",
            (refusing.form, refusing.problems),
            ("parse", []),
        )
        ctl.check("CONTROL: ...and the run is green", _quiet_run(root), 0)
    scripts = {
        "check:ci-y": "PYTHONPATH=.ci python3 -m rediacc_ci.quality.gate_argv --selftest && "
        "python3 .ci/scripts/quality/check_z.py",
        "outer": "npm run check:ci-y",
    }
    ctl.check(
        "CONTROL: `npm run` expands through package.json to every form it reaches",
        [
            (t.key, t.kind)
            for t in targets_of(expand_npm("npm run outer", scripts), pathlib.Path("/r"))
        ],
        [("rediacc_ci.quality.gate_argv", "module"), ("check_z", "shim")],
    )
    ctl.check(
        "CONTROL: a self-referencing npm script expands once, not forever",
        expand_npm("npm run a", {"a": "npm run a"}),
        "( npm run a )",
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture_tree(pathlib.Path(tmp), MODULE_REFUSES)
        (root / LOCK_REL).unlink()
        ctl.check("PLANT: no readable lock is a refusal, never a pass", _quiet_run(root), 1)
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
    gate_args.parse("check_gate_argv.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(main(sys.argv[1:]))
