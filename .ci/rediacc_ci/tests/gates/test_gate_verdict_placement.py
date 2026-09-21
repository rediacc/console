"""A control written below its own suite's exit verdict asserts nothing.

THE DEFECT, TWICE. The script-style suites under `.claude/hooks/stop/` count assertions on a `Tally` and end with

    if Tally.fails:
        print("FAIL: ...", file=sys.stderr)
        sys.exit(1)
    print(f"{Tally.count} control(s) passed")

Anything appended BELOW that verdict still runs and still prints ` FAIL`, but nothing reads `Tally.fails` again, so the process exits 0. And the delegate table in `.claude/rediacc_hooks/tests/test_hooks_delegates.py` scores these files by their EXIT CODE -- `assert done.returncode == 0` -- so it takes the success branch, scrapes the
"N control(s) passed" line, and reports `ok`. The controls are decorative: they can print a failure and change nothing. THE READER MOVED, THE HAZARD DID NOT: the same scoring lived in `.claude/hooks/test-hooks.sh` until it was ported, and an exit code is an exit code in either language.

It has happened twice. Two blocks were stranded in `test-judge-schema.py` on 2026-09-04 and stayed unfalsifiable until somebody noticed the control COUNT had not moved. On 2026-09-08 a second author appended seven more to the same file -- in a session spent hunting vacuous controls, into the one file whose own comment warns about this in capitals. Reading the warning is evidently
not enough, which is the argument for a gate rather than a louder comment.

WHY THE EXIT CODE CANNOT CATCH IT, and why this gate is structural rather than behavioural: a stranded control produces exactly the same exit code as a healthy one. There is no run you can perform that distinguishes the two states, so the only evidence is the SHAPE of the file. That is what this reads.

WHAT IT DOES NOT CLAIM. It does not check that a control is correct, or that the suite is complete, or that the verdict is reached -- only that no `control(...)` call sits after the verdict that decides the exit code. A file with no verdict at all is out of scope: pytest modules fail on assertion rather than on a tally, and demanding this idiom of them would be a rule about a
convention they do not use.

NO `BASH_TWIN`: this gate is new, not a port, so `test_twin_parity` leaves it be.
"""

from __future__ import annotations

import ast

from rediacc_ci import paths

SUITE_GLOB = ".claude/hooks/stop/test-*.py"
PYTEST_GLOB = ".ci/rediacc_ci/tests/**/*.py"
TALLY = "Tally"
FAILS = "fails"
CONTROL = "control"


def _verdict_end(tree: ast.AST) -> int | None:
    """Line of the last statement of the `if Tally.fails: ... sys.exit(...)` block.

    KEYED ON THE STATEMENT, NEVER ON THE TEXT. `grep -n 'if Tally.fails:'` finds the file's own COMMENT quoting it in backticks before it finds the code -- that mis-anchoring produced a wrong count during the manual sweep this gate replaces, and a gate repeating it would be worse than none.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (
            isinstance(test, ast.Attribute)
            and test.attr == FAILS
            and isinstance(test.value, ast.Name)
            and test.value.id == TALLY
        ):
            continue
        exits = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "exit"
            for n in ast.walk(node)
        )
        if exits:
            return node.end_lineno
    return None


def stranded_controls(source: str) -> list[int]:
    """Lines of `control(...)` calls that sit AFTER the exit verdict."""
    tree = ast.parse(source)
    end = _verdict_end(tree)
    if end is None:
        return []
    return sorted(
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == CONTROL
        and n.lineno > end
    )


def has_verdict(source: str) -> bool:
    return _verdict_end(ast.parse(source)) is not None


# ---- the synthetic corpus, by construction rather than by mutating a real file --

_CLEAN = """
def control(label, got, want): pass
control("counted", 1, 1)
if Tally.fails:
    sys.exit(1)
print("done")
"""
_STRANDED = """
def control(label, got, want): pass
control("counted", 1, 1)
if Tally.fails:
    sys.exit(1)
control("decorative -- prints FAIL and changes nothing", 1, 2)
"""
_NO_VERDICT = """
def control(label, got, want): pass
control("a suite with no tally verdict at all", 1, 1)
"""
_IF_WITHOUT_EXIT = """
def control(label, got, want): pass
if Tally.fails:
    print("noting it")
control("still counted, because nothing exited above", 1, 1)
"""


def test_the_detector_still_discriminates(gate):
    """CONTROL-FIRST. Each rule shown firing and NOT firing."""
    gate.assert_eq(stranded_controls(_CLEAN), [], "a control above the verdict is fine")
    gate.ok("clean: every control precedes the verdict")

    gate.assert_eq(len(stranded_controls(_STRANDED)), 1, "a control below it is stranded")
    gate.ok("control: a control after the verdict is reported")

    gate.assert_eq(stranded_controls(_NO_VERDICT), [], "no verdict, no rule to break")
    gate.ok("control: a suite with no tally verdict is out of scope")

    # THE ONE A TEXT MATCH WOULD GET WRONG. `if Tally.fails:` that does not exit decides nothing, so what follows it is still counted and still fails the run.
    gate.assert_eq(
        stranded_controls(_IF_WITHOUT_EXIT), [], "an if that does not exit strands nothing"
    )
    gate.ok("control: the rule keys on the EXIT, not on the `if`")

    gate.assert_eq(has_verdict(_CLEAN), True, "the verdict is found where it exists")
    gate.assert_eq(has_verdict(_NO_VERDICT), False, "and not invented where it does not")
    gate.ok("control: verdict detection separates the two shapes")

    gate.tally_finish("verdict-placement detector")


def test_no_suite_strands_a_control_below_its_verdict(gate):
    """The real scan. Anti-vacuity first: discovering no suite is a FAILURE."""
    suites = sorted(paths.repo_root().glob(SUITE_GLOB))
    if not suites:
        gate.log_fail(
            "no suite matched %s, so the scan below compared nothing and its silence "
            "means nothing. Either the glob stopped matching or the suites moved; fix "
            "the reader before trusting a green here." % SUITE_GLOB
        )

    with_verdict = 0
    problems = []
    for path in suites:
        source = path.read_text(encoding="utf-8")
        if not has_verdict(source):
            continue
        with_verdict += 1
        stranded = stranded_controls(source)
        if stranded:
            problems.append(
                "%s: %d control(s) after the exit verdict, first at line %d"
                % (paths.relative_to_root(path), len(stranded), stranded[0])
            )

    # THE SECOND REFUSAL, and it is the one this gate most needs. If the idiom is ever renamed, every file reads as "no verdict", every file is skipped, and a green here would mean the gate found nothing to check rather than nothing wrong. Six suites carry it today.
    if with_verdict == 0:
        gate.log_fail(
            "scanned %d suite(s) and NONE carries an `if Tally.fails: ... sys.exit()` "
            "verdict. The idiom has been renamed and this gate is now checking nothing, "
            "which is exactly the failure it exists to catch." % len(suites)
        )

    if problems:
        gate.log_fail(
            "%d suite(s) strand controls below their own exit verdict:\n  %s\n"
            "Such a control still prints `  FAIL` and the process still exits 0, and "
            "`.claude/rediacc_hooks/tests/test_hooks_delegates.py` scores these files by "
            "EXIT CODE -- so the delegate reports `ok`. Move them ABOVE the verdict."
            % (len(problems), "\n  ".join(problems))
        )

    gate.log_pass(
        "%d of %d suite(s) carry the tally verdict and none strands a control below it"
        % (with_verdict, len(suites))
    )


# ---- the same defect in the pytest tree, which has a DIFFERENT mechanism ------
#
# THE SCRIPT-SUITE RULE DOES NOT TRANSFER, and measuring that was the point. A control placed below `gate.tally_finish()` in a pytest module is NOT stranded: planted as `gate.log_fail(...)` after the verdict in `test_gate_positional_detector.py` it raised `GateAssertionError` and the test went red. There is no exit code to take the success branch of, so that half of the class
# cannot exist here and a rule about it would be a rule with no failure mode.
#
# WHAT CAN HAPPEN HERE is plain unreachability: a `return` or `pytest.skip()` above the controls. Planted as a bare `return` before `tally_finish` in that same file, the ENTIRE verdict and every control below it became dead and `pytest` reported `1 passed`. `ruff` did not flag it either, despite
# `select = ["ALL"]` -- measured 2026-09-08. So the shape is real, silent, and
# ungated, which is what earns a rule rather than a comment.
#
# ZERO TODAY. A sweep of all 212 files under `.ci/rediacc_ci/tests` found none, so this lands as a ratchet rather than a cleanup.

_TERMINAL = frozenset(
    {"sys.exit", "pytest.skip", "pytest.fail", "pytest.xfail", "pytest.exit", "os._exit"}
)


def _dotted(func: ast.expr) -> str:
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return "%s.%s" % (func.value.id, func.attr)
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_terminator(node: ast.stmt) -> bool:
    """A statement after which nothing in the SAME block can run.

    THE NAME ALONE IS NOT ENOUGH, and keying on it produced a false positive on the first sweep: `c.fail("d")` in `test_controls.py` is a `Controls` method RECORDING a failure, not an exit, and the assertion after it is the test's whole point. So the call must be dotted and in `_TERMINAL`.
    """
    if isinstance(node, (ast.Return, ast.Raise)):
        return True
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and _dotted(node.value.func) in _TERMINAL
    )


def _counts_as_control(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return True
    return isinstance(node, ast.Call) and _dotted(node.func).startswith(
        ("gate.assert", "gate.log_fail", "gate.ok", "gate.no", "gate.check", "gate.tally")
    )


def unreachable_controls(source: str) -> list[int]:
    """Lines where a control sits after a terminator in the same block."""
    tree = ast.parse(source)
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for holder in ast.walk(fn):
            for field in ("body", "orelse", "finalbody"):
                block = getattr(holder, field, None)
                if not isinstance(block, list):
                    continue
                for i, stmt in enumerate(block):
                    if not (_is_terminator(stmt) and i + 1 < len(block)):
                        continue
                    dead = block[i + 1 :]
                    if any(_counts_as_control(n) for st in dead for n in ast.walk(st)):
                        found.append(dead[0].lineno)
    return sorted(found)


_PY_CLEAN = """
def test_one(gate):
    gate.ok("counted")
    gate.tally_finish("x")
"""
_PY_AFTER_RETURN = """
def test_one(gate):
    return
    gate.ok("dead")
    gate.tally_finish("x")
"""
_PY_AFTER_SKIP = """
def test_one(gate):
    pytest.skip("not here")
    gate.ok("dead")
"""
_PY_GUARD_CLAUSE = """
def test_one(gate):
    if not ready():
        return
    gate.ok("still reached on the other path")
    gate.tally_finish("x")
"""
_PY_RECORDING_FAIL = """
def test_one(gate):
    c.fail("d")
    assert c.count == 4
"""


def test_the_unreachable_detector_still_discriminates(gate):
    """CONTROL-FIRST, including the two shapes that must NOT fire."""
    gate.assert_eq(unreachable_controls(_PY_CLEAN), [], "a live test is left alone")
    gate.ok("clean: controls above every terminator")

    gate.assert_eq(len(unreachable_controls(_PY_AFTER_RETURN)), 1, "a bare return strands them")
    gate.ok("control: controls below a `return` are reported")

    gate.assert_eq(len(unreachable_controls(_PY_AFTER_SKIP)), 1, "so does pytest.skip()")
    gate.ok("control: pytest.skip() is a terminator too")

    # THE GUARD CLAUSE. `if cond: return` ends only its own branch, and a rule that read it as ending the function would fire on most of this tree.
    gate.assert_eq(unreachable_controls(_PY_GUARD_CLAUSE), [], "a guard clause strands nothing")
    gate.ok("control: the rule is per-BLOCK, not per-function")

    # THE FALSE POSITIVE THE FIRST SWEEP ACTUALLY PRODUCED.
    gate.assert_eq(unreachable_controls(_PY_RECORDING_FAIL), [], "c.fail() records, not exits")
    gate.ok("control: a method named fail() is not pytest.fail()")

    gate.tally_finish("unreachable-control detector")


def test_no_pytest_module_strands_a_control_below_a_terminator(gate):
    """The real scan. Anti-vacuity first: finding no module is a FAILURE."""
    modules = sorted(paths.repo_root().glob(PYTEST_GLOB))
    if not modules:
        gate.log_fail(
            "no module matched %s, so the scan below compared nothing. Fix the reader "
            "before trusting a green here." % PYTEST_GLOB
        )

    with_tests = 0
    problems = []
    for path in modules:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        if any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
            for n in ast.walk(tree)
        ):
            with_tests += 1
        dead = unreachable_controls(source)
        if dead:
            problems.append(
                "%s: %d control(s) below a terminator, first at line %d"
                % (paths.relative_to_root(path), len(dead), dead[0])
            )

    # THE SECOND REFUSAL. If the glob ever stops reaching test modules every file is trivially clean and the green means nothing.
    if with_tests == 0:
        gate.log_fail(
            "scanned %d module(s) under %s and NONE defines a `test_` function. The tree "
            "has moved and this gate is now checking nothing." % (len(modules), PYTEST_GLOB)
        )

    if problems:
        gate.log_fail(
            "%d module(s) place a control where it cannot run:\n  %s\n"
            "`pytest` reports such a module as PASSED -- measured by planting a bare "
            "`return` above a gate's verdict -- and `ruff` does not flag it under "
            '`select = ["ALL"]`. Move the controls above the terminator.'
            % (len(problems), "\n  ".join(problems))
        )

    gate.log_pass(
        "%d of %d pytest module(s) define controls and none sits below a terminator"
        % (with_tests, len(modules))
    )
