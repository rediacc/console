"""A fan-out gate driver must let each subject declare its timeout, and must
turn a timeout into a VERDICT rather than a traceback.

THE DEFECT THIS EXISTS TO PREVENT FROM RETURNING, measured 2026-09-07.
`test_twin_parity.py` discovers its subjects by glob -- 98 ported modules and
climbing -- and drove every one of them under a hardcoded `timeout=600`, in two
places. `subprocess.run(timeout=)` RAISES, and nothing caught it, so a subject
slower than the literal produced a `TimeoutExpired` traceback instead of a
verdict about the subject. The visible cost was not a red gate. It was a whole
class of subject silently becoming UNPORTABLE: `test-claude-hooks.sh` runs 2 229
offline cases in 13m31s, hit the wall, and was about to be recorded as a
permanent "standing drop" on the strength of it -- which is how a fixable
constraint turns into folklore that each later batch rediscovers and re-drops.

WHY THE OBVIOUS GATE IS THE WRONG ONE, and it was proposed. "Every
`subprocess.run` with a `timeout=` must have a `try/except TimeoutExpired`"
covers 196 call sites in this tree, and it is wrong at nearly all of them: a
one-shot fixture (`bash -c 'echo x'`, `git --version`, one assert script) that
blows a 120-second limit IS hung, and a traceback is the loudest, most accurate
rendering of that. A gate demanding a handler there buys nothing and would be
suppressed within a day, which is worse than no gate because a suppressed gate
still looks like coverage. So this narrows to the property that actually failed:
a driver running a subject set IT DOES NOT CONTROL.

THE CLASS, stated so membership is checkable rather than asserted. A module here
is a FAN-OUT DRIVER when it discovers its subjects at import time (a `glob` at
module scope) and then runs them through a subprocess. Its timeouts are then a
promise about files nobody has measured -- every future port, not just today's
98 -- and only two things make that promise keepable:

  RULE A  the timeout is DERIVED, never a bare literal, so a subject can declare
          what it costs.
  RULE B  a timeout REACHES A VERDICT: the call sits inside a `try/except
          TimeoutExpired`, or the one function wrapping it is itself only ever
          called from inside one.

Rule B is deliberately ONE HOP and no further. The real shape it must accept is
`test_twin_parity.run_port`, where the `subprocess.run` is in a helper and the
`try` is at the helper's call site; a rule that only looked inside the function
would flag the very code that fixed the bug. Chasing further than one hop needs
a call graph this does not have, and that is a BLIND SPOT stated rather than
papered over: a subject-runner buried two helpers deep would pass here.

ANTI-VACUITY, both halves. An empty member set fails, because the day the glob
stops matching is the day this silently guards nothing. And the analyser itself
is exercised against synthetic sources that violate each rule, so a green here
means the predicates can still discriminate -- not merely that nobody tripped
them. The controls are in-memory strings, never a mutation of a tracked file.

NO `BASH_TWIN`: this is a new gate, not a port of a bash one, so `test_twin_parity`
correctly leaves it alone.
"""

from __future__ import annotations

import ast
import pathlib

from rediacc_ci import paths

HERE = pathlib.Path(__file__).resolve().parent

# The calls that hand work to a subject process. `harness.run` is included
# because it is this tree's own wrapper around `subprocess.run` and forwards
# `timeout` straight through -- gating only the stdlib name would miss every
# gate test in the directory, which is most of them.
RUNNERS = frozenset({"run", "Popen", "check_output", "call"})
RUNNER_OWNERS = frozenset({"subprocess", "harness", "proc"})


def _annotate_parents(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]


def _is_runner_call(node: ast.AST) -> bool:
    """`<owner>.<runner>(...)` where both halves are ours."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    owner = node.func.value
    return node.func.attr in RUNNERS and isinstance(owner, ast.Name) and owner.id in RUNNER_OWNERS


def _timeout_kw(node: ast.Call) -> ast.keyword | None:
    for kw in node.keywords:
        if kw.arg == "timeout":
            return kw
    return None


def _ancestors(node: ast.AST):
    cur = getattr(node, "parent", None)
    while cur is not None:
        yield cur
        cur = getattr(cur, "parent", None)


def _catches_timeout(handler: ast.ExceptHandler) -> bool:
    """Does this handler name `TimeoutExpired`, bare or in a tuple?"""
    caught = handler.type
    if caught is None:
        return False
    names = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    for name in names:
        if isinstance(name, ast.Attribute) and name.attr == "TimeoutExpired":
            return True
        if isinstance(name, ast.Name) and name.id == "TimeoutExpired":
            return True
    return False


def _inside_guarded_try(node: ast.AST) -> bool:
    """Is `node` lexically inside a `try` whose handler catches a timeout?

    The BODY is what a `try` protects, so a call sitting in the handler or the
    `finally` of such a statement does not count -- checking `try` ancestry
    alone would admit exactly that.
    """
    child = node
    for parent in _ancestors(node):
        if (
            isinstance(parent, ast.Try)
            and any(_catches_timeout(h) for h in parent.handlers)
            and any(child is stmt or child in ast.walk(stmt) for stmt in parent.body)
        ):
            return True
        child = parent
    return False


def _enclosing_function(node: ast.AST) -> ast.FunctionDef | None:
    for parent in _ancestors(node):
        if isinstance(parent, ast.FunctionDef):
            return parent
    return None


def _all_call_sites_guarded(tree: ast.AST, func_name: str) -> bool:
    """Every call to `func_name` in this module is inside a guarded `try`.

    ALL, not any, and at least one: a helper reached from one guarded site and
    one bare site is unguarded in practice, and a helper nothing calls proves
    nothing at all.
    """
    sites = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == func_name
    ]
    return bool(sites) and all(_inside_guarded_try(s) for s in sites)


def _functions_containing_a_glob(tree: ast.AST) -> set[str]:
    named = set()
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef):
            continue
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "glob"
            ):
                named.add(func.name)
                break
    return named


def _module_level_discovered_names(tree: ast.Module) -> set[str]:
    """Names bound AT IMPORT TIME from a glob, directly or one hop through a helper.

    ONE HOP matters and is not generality for its own sake: the real member spells
    it `MODULES = ported_modules()`, with the glob inside that function, so a
    direct-only rule would miss the single case this gate exists for.
    """
    glob_funcs = _functions_containing_a_glob(tree)
    found = set()
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        value = stmt.value
        direct = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "glob"
            for n in ast.walk(value)
        )
        one_hop = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in glob_funcs
            for n in ast.walk(value)
        )
        if direct or one_hop:
            found.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
    return found


def is_fanout_driver(source: str) -> bool:
    """Does this module DISCOVER its subjects at IMPORT TIME rather than list them?

    IMPORT TIME IS THE WHOLE DISCRIMINATOR, and the looser reading cost a false
    positive on the first run of this gate. `test_gate_media_docs.py` globs
    `.ci/media/*.sh` and runs subprocesses with literal timeouts, so "has a glob
    and runs a subject" flagged it -- wrongly. Its globs are inside test bodies
    and produce DATA (which media modules exist, for a coverage assertion); the
    things it actually runs are fixed module-level constants whose cost its
    author measured. Nothing there can grow behind the author's back, which is
    the only reason a literal timeout is ever a problem.

    So the rule is: a module-level name bound from a glob, referenced elsewhere
    in the module, in a module that runs a subject with a timeout. A hand-written
    tuple of subjects is out of class for the same reason.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    _annotate_parents(tree)
    discovered = _module_level_discovered_names(tree)
    if not discovered:
        return False
    used = {
        n.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in discovered
    }
    return bool(used) and _runs_a_subject(tree)


def _runs_a_subject(tree: ast.AST) -> bool:
    return any(_is_runner_call(n) and _timeout_kw(n) for n in ast.walk(tree))


def problems(source: str) -> list[str]:
    """Every rule this module source breaks, as sentences. Empty means clean."""
    found: list[str] = []
    tree = ast.parse(source)
    _annotate_parents(tree)
    for node in ast.walk(tree):
        if not _is_runner_call(node):
            continue
        kw = _timeout_kw(node)
        if kw is None:
            continue
        where = "line %d" % node.lineno
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
            found.append(
                "%s: timeout=%r is a bare literal in a driver whose subject set is "
                "discovered, so no subject can declare what it costs (RULE A)"
                % (where, kw.value.value)
            )
        if not _inside_guarded_try(node):
            enclosing = _enclosing_function(node)
            if enclosing is None or not _all_call_sites_guarded(tree, enclosing.name):
                found.append(
                    "%s: a timeout here escapes as a TimeoutExpired traceback instead "
                    "of a verdict about the subject (RULE B)" % where
                )
    return found


# ---- the synthetic corpus the analyser is judged against --------------------
#
# BY CONSTRUCTION, never by mutating a tracked file: these prove the predicates
# still discriminate, which is the only thing that makes the real scan's silence
# mean anything.

_CLEAN_DIRECT = """
import subprocess
SUBJECTS = [p for p in HERE.glob("test_*.py")]
def drive(subject, limit):
    try:
        return subprocess.run(["bash", subject], timeout=limit)
    except subprocess.TimeoutExpired:
        gate.log_fail("timed out")
def test_it():
    drive(SUBJECTS[0], LIMIT)
"""

_CLEAN_ONE_HOP = """
import subprocess
SUBJECTS = [p for p in HERE.glob("test_*.py")]
def run_port(subject, limit):
    return subprocess.run(["pytest", subject], timeout=limit)
def test_it(gate):
    try:
        run_port(SUBJECTS[0], LIMIT)
    except subprocess.TimeoutExpired:
        gate.log_fail("timed out")
"""

_BARE_LITERAL = """
import subprocess
SUBJECTS = [p for p in HERE.glob("test_*.py")]
def drive(subject):
    try:
        return subprocess.run(["bash", subject], timeout=600)
    except subprocess.TimeoutExpired:
        gate.log_fail("timed out")
"""

_UNGUARDED = """
import subprocess
SUBJECTS = [p for p in HERE.glob("test_*.py")]
def drive(subject, limit):
    return subprocess.run(["bash", subject], timeout=limit)
def test_it():
    drive(SUBJECTS[0], LIMIT)
"""

_GUARDED_ONLY_IN_HANDLER = """
import subprocess
SUBJECTS = [p for p in HERE.glob("test_*.py")]
def drive(subject, limit):
    try:
        pass
    except subprocess.TimeoutExpired:
        subprocess.run(["bash", subject], timeout=limit)
"""

_PARTIALLY_GUARDED = """
import subprocess
SUBJECTS = [p for p in HERE.glob("test_*.py")]
def run_port(subject, limit):
    return subprocess.run(["pytest", subject], timeout=limit)
def test_one(gate):
    try:
        run_port(SUBJECTS[0], LIMIT)
    except subprocess.TimeoutExpired:
        gate.log_fail("timed out")
def test_two():
    run_port(SUBJECTS[1], LIMIT)
"""

_NOT_A_FANOUT = """
import subprocess
SUBJECTS = ("cuda.sh", "venv.sh")
def drive(subject):
    return subprocess.run(["bash", subject], timeout=600)
"""

# THE FALSE POSITIVE THIS GATE ACTUALLY PRODUCED ON ITS FIRST RUN, kept as a
# control so it cannot come back. This is the shape of `test_gate_media_docs.py`:
# it globs at TEST time, and what it globs is DATA (which media modules exist,
# for a coverage assertion) rather than the thing it runs; its subjects are fixed
# module-level constants whose cost its author measured. The first membership
# rule here asked only "has a glob and runs a subject with a timeout" and flagged
# it, which would have demanded a declarable timeout from a module whose subject
# set cannot grow behind anyone's back.
_GLOBS_DATA_RUNS_FIXED_SUBJECTS = """
import subprocess
COVERAGE = ROOT / "coverage.sh"
def test_every_module_is_covered(gate):
    for module in sorted((ROOT / "media").glob("*.sh")):
        gate.ok(module.name)
    result = subprocess.run([str(COVERAGE), "--only", "r2"], timeout=600)
    gate.assert_eq(result.rc, 0, "probe ran")
"""

# ONE HOP, which is the real member's spelling: the glob sits inside a helper the
# module body calls. A direct-only membership rule would miss the single case
# this gate exists for.
_DISCOVERED_VIA_HELPER = """
import subprocess
def ported():
    return sorted(HERE.glob("test_gate_*.py"))
MODULES = ported()
def drive(subject, limit):
    try:
        return subprocess.run(["pytest", subject], timeout=limit)
    except subprocess.TimeoutExpired:
        gate.log_fail("timed out")
def test_it():
    drive(MODULES[0], LIMIT)
"""


def test_the_analyser_still_discriminates(gate):
    """CONTROL-FIRST. Each predicate is shown firing and NOT firing."""
    gate.assert_eq(problems(_CLEAN_DIRECT), [], "a guarded, derived timeout is clean")
    gate.ok("clean: guarded in place with a derived timeout")

    gate.assert_eq(problems(_CLEAN_ONE_HOP), [], "the one-hop helper shape is accepted")
    gate.ok("clean: helper runs the subject, the try sits at its only call site")

    bare = problems(_BARE_LITERAL)
    gate.assert_eq(len(bare), 1, "exactly the literal is reported: %s" % bare)
    gate.assert_contains(bare[0], "RULE A", "and it is named as rule A")
    gate.ok("control: a bare `timeout=600` in a fan-out driver is refused")

    loose = problems(_UNGUARDED)
    gate.assert_eq(len(loose), 1, "exactly the escape is reported: %s" % loose)
    gate.assert_contains(loose[0], "RULE B", "and it is named as rule B")
    gate.ok("control: an unguarded subject runner is refused")

    # THE SUBTLE ONE. `try` ancestry alone would call this guarded; it is not,
    # because the call lives in the handler, which nothing protects.
    handler = problems(_GUARDED_ONLY_IN_HANDLER)
    gate.assert_contains(
        " ".join(handler), "RULE B", "a runner inside the HANDLER is not protected by it"
    )
    gate.ok("control: sitting in the except block does not count as guarded")

    partial = problems(_PARTIALLY_GUARDED)
    gate.assert_contains(
        " ".join(partial), "RULE B", "one guarded call site does not cover a bare one"
    )
    gate.ok("control: ALL call sites must be guarded, not merely one")

    gate.assert_eq(
        is_fanout_driver(_NOT_A_FANOUT), False, "a hand-written subject tuple is out of class"
    )
    gate.assert_eq(is_fanout_driver(_CLEAN_DIRECT), True, "a glob-discovered set is in class")
    gate.ok("control: membership separates a discovered set from a listed one")

    gate.assert_eq(
        is_fanout_driver(_GLOBS_DATA_RUNS_FIXED_SUBJECTS),
        False,
        "globbing DATA at test time while running fixed subjects is out of class",
    )
    gate.ok("control: the media-docs false positive stays out of class")

    gate.assert_eq(
        is_fanout_driver(_DISCOVERED_VIA_HELPER), True, "one hop through a helper still counts"
    )
    gate.assert_eq(problems(_DISCOVERED_VIA_HELPER), [], "and that shape is clean")
    gate.ok("control: import-time discovery via a helper is in class, and passes")

    gate.tally_finish("fan-out timeout analyser")


def test_every_fanout_driver_lets_its_subjects_declare_a_timeout(gate):
    """The real scan. Anti-vacuity first: an empty class is a FAILURE."""
    modules = sorted(HERE.glob("test_gate_*.py")) + sorted(HERE.glob("*.py"))
    seen: set[pathlib.Path] = set()
    drivers: list[tuple[pathlib.Path, str]] = []
    for path in modules:
        if path in seen:
            continue
        seen.add(path)
        source = path.read_text(encoding="utf-8")
        if is_fanout_driver(source):
            drivers.append((path, source))

    if not drivers:
        gate.log_fail(
            "no fan-out driver found under %s, so the scan below compared nothing and "
            "its silence means nothing. `test_twin_parity.py` is the known member; if it "
            "was renamed or stopped globbing its subjects, fix this detector before "
            "trusting a green here." % paths.relative_to_root(HERE)
        )

    for path, source in drivers:
        broken = problems(source)
        if broken:
            gate.log_fail(
                "%s discovers its subjects but does not keep the promise that implies:\n  %s\n"
                "A subject must be able to declare what it costs (`TWIN_TIMEOUT` is the "
                "existing spelling), and a timeout must arrive as a verdict about the "
                "subject, never as a traceback about the harness."
                % (paths.relative_to_root(path), "\n  ".join(broken))
            )
        gate.ok(
            "%s: subjects declare their own timeout and a timeout is a verdict"
            % paths.relative_to_root(path)
        )

    gate.log_info("fan-out drivers scanned: %d" % len(drivers))
    gate.tally_finish("fan-out timeout declarability")
