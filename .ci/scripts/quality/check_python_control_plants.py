#!/usr/bin/env python3
"""check:ci-python-control-plants -- a Python control may not build its mutant by raw substitution.

WHY THIS EXISTS, and it is a defect this repo predicted and then could not see. A control proves a gate can fail by feeding it a MUTATED fixture. If the mutation silently does nothing, the gate is handed the CLEAN input, stays green, and the control reports a pass for an assertion it never made. `check:ci-control-vacuity` catches that -- on the bash side only. Its own comment at
`.ci/scripts/quality/check-control-vacuity.sh:183-193` says, verbatim, that of the 21 Python gates ZERO built a control mutant by substitution, and that "what must not happen is that changing silently".

IT CHANGED, AND IT CHANGED SILENTLY. 21 became 50. The tripwire its author installed was a COUNT PRINTED INSIDE A SUCCESS MESSAGE, which `shadow-gate.ts` classifies as chatter rather than a finding, so nothing ever read the alarm. Measured 2026-09-08: 61 substitution-built plant sites across 11 Python gate modules, three proof assertions between them, and one already-vacuous mutant
sitting in the tree (`review_turn_capacity.py`, `.replace("max_turns=140",
"max_turns=140")`, inside the port of the very gate `control_vacuity` uses as its
own control).

THE CLASS IS: A DISCLOSURE IS NOT A CONTROL.

WHY THIS IS A NEW GATE AND NOT A WIDENED `control_vacuity`. Three reasons in descending force. The live gate there is the BASH twin (`package.json`), and `.ci/rediacc_ci/tests/test_quality_control_vacuity.py:189` requires the two implementations to print identical bytes -- so teaching it Python means writing an AST-equivalent predicate in bash, which with grep is exactly the
false-positive machine that would flag `datetime.replace(tzinfo=...)`. Invariant
5 forbids deleting the twin until W7 P5, so widening would mean MAINTAINING that bash Python-parser. And the question is genuinely different: `control_vacuity` asks "is there a proof?", this asks "did you use the harness?" -- stronger, and
with no false positives by construction.

THE PREDICATE. Inside a CONTROL REGION, a call `X.replace(...)` or `re.sub(..., X)` where `X` is a BARE NAME is a finding. `plant(...)` and `plant_re(...)` are not.

The bare-Name restriction IS the exemption mechanism, and it is why this gate needs no allowlist file. A receiver that is itself a call -- `str(ROOT).lstrip( "/").replace("/", "-")` in `check_resprofile.py`, `match.group(1).replace(" ", "")` in `release_signing_coverage.py`, `(out + "\\n").replace("\\n", " ")` in `drill_verdicts.py` -- is parsing, not planting, and is invisible
here. Measured:
with the restriction 12 files, without it 14, and both extras are false
positives. One AST condition instead of a JSON file nobody drains.

RESOLVING THE NAME, NOT MATCHING THE TOKEN, and this is not theoretical. THREE modules in this tree define a LOCAL `def plant(...)` that is not the harness: `check_plan_record.py` and `cli_doc_coverage.py` did (both since renamed to `expect_finding`), and `test_gate_watchdog_monitor_ordering.py:98` still does. A gate that merely counted `plant(` would read those call sites as
compliant while they use no harness at all -- a FALSE NEGATIVE, which is worse than the blindness this closes. So a module only earns harness credit when it imports `plant` from `rediacc_ci.controls` AND does not shadow it locally.

ANTI-VACUITY, both halves. Discovering zero modules FAILS. Discovering zero `plant()` call sites across the whole corpus also FAILS, with a DIFFERENT message: the day the harness is renamed and this gate is not updated, every module looks compliant and a green here would mean nothing. That is the single most important refusal in the file.

Exit 1 on any finding, 2 on a failed control.

---- gate ----
step: Python control plants
needs: none
lane: quality-static
selftest: true
why: a Python control plant built by raw substitution can silently no-op, handing
     the gate its clean fixture while the control reports a pass; the harness in
     `rediacc_ci.controls` makes that impossible and this gate requires the harness.
---- end gate ----
"""

from __future__ import annotations

import ast
import glob
import os
import pathlib
import sys
import tempfile

import _cipath  # noqa: F401
from rediacc_ci.controls import Controls

SELF = os.path.basename(__file__)

# Both halves of the quality estate. A port landing under the first glob is in scope the MOMENT it exists -- no registration, no baseline row, no hand edit, which is the whole reason this is two globs and not a file list.
SCOPE = (".ci/rediacc_ci/quality/*.py", ".ci/scripts/quality/check_*.py")

HARNESS_MODULE = "rediacc_ci.controls"
HARNESS_NAMES = ("plant", "plant_re")
# ONLY `.replace`. For `.sub`/`.subn` the RECEIVER is a compiled regex, not the fixture -- `SPACE_RE.sub("", " \t\n")` exercises the pattern itself and is not a plant at all. Measured: including them produced two false positives in `no_otlp_creds.py` on the first real run. `re.sub(pattern, repl, X)` would need the THIRD ARGUMENT checked, not the receiver; no control region in this
# corpus uses that shape today, so it is deliberately not guessed at.
SUBSTITUTORS = ("replace",)

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"


def control_region_functions(tree: ast.AST) -> set[str]:
    """Functions whose name marks them as a control region.

    Name-based ON PURPOSE. The alternative -- "any function that builds a mutant" -- is the question this gate is asking, so using it to decide scope would be circular.
    """
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and (
            node.name.startswith("selftest") or node.name.startswith("control")
        ):
            out.add(node.name)
    return out


def _annotate(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]


def _enclosing_control(node: ast.AST, regions: set[str]) -> bool:
    cur = getattr(node, "parent", None)
    while cur is not None:
        if isinstance(cur, ast.FunctionDef):
            return cur.name in regions
        cur = getattr(cur, "parent", None)
    return False


def has_harness(tree: ast.AST) -> bool:
    """Does this module import `plant` from the harness AND not shadow it?"""
    imported = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == HARNESS_MODULE
            and any(a.name in HARNESS_NAMES for a in node.names)
        ):
            imported = True
    shadowed = any(
        isinstance(n, ast.FunctionDef) and n.name in HARNESS_NAMES for n in ast.walk(tree)
    )
    return imported and not shadowed


def harness_sites(tree: ast.AST) -> int:
    """Calls to the harness, counted only when the module really imports it."""
    if not has_harness(tree):
        return 0
    return sum(
        1
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in HARNESS_NAMES
    )


def _is_substitution(node: ast.AST):
    """The bare-Name receiver of a substitution call, or None."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr not in SUBSTITUTORS:
        return None
    recv = node.func.value
    return recv if isinstance(recv, ast.Name) else None


def _normalises_a_comparison(node: ast.Call) -> bool:
    """Is this substitution a SIBLING of another, inside one call?

    THE FIRST EXEMPTION, and it is a shape rather than a name. Two substitutions as sibling arguments of one call are normalising BOTH SIDES of a comparison, not building a mutant -- `ctl.check(label, welded.replace("\n", ""), _ARMOR.replace("\n", ""))` in `release_key_canonical.py:650-653` asserts that two texts are equal once a line break is removed from each. A mutant is never
    compared against another mutant of its own shape, so the sibling test separates the two without an allowlist and without dataflow.
    """
    parent = getattr(node, "parent", None)
    if not isinstance(parent, ast.Call):
        return False
    return any(a is not node and _is_substitution(a) is not None for a in parent.args)


def _has_own_vacuity_guard(node: ast.Call) -> bool:
    """Is the result compared back against the text it was built from?

    THE SECOND EXEMPTION, and it deliberately mirrors `control_vacuity`'s own
    `proves_plant_landed`: a plant that checks `mutant == clean` has already made
    the assertion this gate exists to demand, and flagging it would put the two gates in contradiction. `check_plan_record.py:1155-1157` is the live case --
    `drifted = cen.replace(A)`, `if drifted == cen: drifted = cen.replace(B)`,
    then a control asserting `drifted != cen`. That fallback chain is STRONGER
    than `plant()` can be, because `plant()` raises on the first miss and would destroy the second attempt.
    """
    recv = _is_substitution(node)
    assign = getattr(node, "parent", None)
    if recv is None or not isinstance(assign, ast.Assign):
        return False
    targets = {t.id for t in assign.targets if isinstance(t, ast.Name)}
    if not targets:
        return False
    fn = node
    while fn is not None and not isinstance(fn, ast.FunctionDef):
        fn = getattr(fn, "parent", None)
    if fn is None:
        return False
    for cmp_node in ast.walk(fn):
        if not isinstance(cmp_node, ast.Compare):
            continue
        names = {n.id for n in ast.walk(cmp_node) if isinstance(n, ast.Name)}
        if names & targets and recv.id in names:
            return True
    return False


def findings_for(source: str) -> list[str]:
    """Raw substitutions inside a control region. Empty means clean."""
    tree = ast.parse(source)
    _annotate(tree)
    regions = control_region_functions(tree)
    if not regions:
        return []
    out = []
    for node in ast.walk(tree):
        recv = _is_substitution(node)
        if recv is None:
            continue
        if not _enclosing_control(node, regions):
            continue
        if _normalises_a_comparison(node) or _has_own_vacuity_guard(node):
            continue
        out.append(
            "line %d: %s.%s(...) builds a control mutant by raw substitution; use "
            "plant() from rediacc_ci.controls, which refuses a mutation that would "
            "not change the fixture" % (node.lineno, recv.id, node.func.attr)
        )
    return out


def scan(root: pathlib.Path):
    """(modules, sites, findings) over the two globs."""
    modules, sites, findings = 0, 0, []
    for pattern in SCOPE:
        for path in sorted(glob.glob(str(root / pattern))):
            p = pathlib.Path(path)
            if p.name == SELF:
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, OSError):
                continue
            modules += 1
            sites += harness_sites(tree)
            findings.extend(
                "%s: %s" % (os.path.relpath(path, str(root)), f)
                for f in findings_for(p.read_text(encoding="utf-8"))
            )
    return modules, sites, findings


# ---- controls ---------------------------------------------------------------

_CLEAN = """
from rediacc_ci.controls import Controls, plant
_FIX = "a b"
def selftest():
    return plant(_FIX, "a", "z")
"""
_RAW = """
from rediacc_ci.controls import Controls, plant
_FIX = "a b"
def selftest():
    return _FIX.replace("a", "z")
"""
_PARSING_RECEIVER = """
from rediacc_ci.controls import Controls, plant
def selftest():
    return str(ROOT).lstrip("/").replace("/", "-")
"""
_OUTSIDE_REGION = """
_FIX = "a b"
def main():
    return _FIX.replace("a", "z")
"""
_NORMALISER_PAIR = """
from rediacc_ci.controls import Controls, plant
def selftest():
    ctl.check("same once a break is gone", welded.replace("x", ""), _ARMOR.replace("x", ""))
"""
_LONE_SUBSTITUTION_ARG = """
from rediacc_ci.controls import Controls, plant
_FIX = "a b"
def selftest():
    ctl.check("planted", run(_FIX.replace("a", "z")), 1)
"""
_GUARDED_FALLBACK = """
from rediacc_ci.controls import Controls, plant
def selftest():
    drifted = cen.replace("A", "B", 1)
    if drifted == cen:
        drifted = cen.replace("C", "D", 1)
    ck("the perturbation landed", drifted != cen)
"""
_UNGUARDED_ASSIGN = """
from rediacc_ci.controls import Controls, plant
def selftest():
    drifted = cen.replace("A", "B", 1)
    ck("something else entirely", other != thing)
"""

_SHADOWED = """
from rediacc_ci.controls import Controls, plant
def plant(label, text):
    return text
def selftest():
    return plant("x", "y")
"""


def selftest(verbose: bool = False) -> int:
    c = Controls("check_python_control_plants", floor=19, verbose=verbose)
    c.check("a plant() mutant in a control region is clean", findings_for(_CLEAN), [])
    c.check("a RAW substitution in a control region is a finding", len(findings_for(_RAW)), 1)
    c.check(
        "...and it names the rule",
        "raw substitution" in (findings_for(_RAW) or [""])[0],
        True,
    )
    c.check(
        "a call-expression receiver is parsing, not planting",
        findings_for(_PARSING_RECEIVER),
        [],
    )
    c.check(
        "a substitution OUTSIDE a control region is not a finding",
        findings_for(_OUTSIDE_REGION),
        [],
    )
    c.check("the clean module earns harness credit", harness_sites(ast.parse(_CLEAN)), 1)
    # THE FALSE NEGATIVE THIS GATE WOULD OTHERWISE HAVE. A module with its own `def plant` calls something that is not the harness; counting the token would score it as compliant.
    c.check("a LOCAL def plant earns no harness credit", harness_sites(ast.parse(_SHADOWED)), 0)
    c.check("...because the import is shadowed", has_harness(ast.parse(_SHADOWED)), False)
    c.check("...while the unshadowed import counts", has_harness(ast.parse(_CLEAN)), True)

    # THE TWO EXEMPTIONS, each with its MIRROR. An exemption that always fires is the blanket refusal inverted, and would be worse than no gate at all.
    c.check(
        "two substitutions as siblings in one call are normalisation",
        findings_for(_NORMALISER_PAIR),
        [],
    )
    c.check(
        "MIRROR: a LONE substitution argument is still a finding",
        len(findings_for(_LONE_SUBSTITUTION_ARG)),
        1,
    )
    c.check(
        "a substitution compared back against its own source is guarded",
        findings_for(_GUARDED_FALLBACK),
        [],
    )
    c.check(
        "MIRROR: the same assignment with no such comparison is a finding",
        len(findings_for(_UNGUARDED_ASSIGN)),
        1,
    )
    # THE TWO REFUSALS, driven against real starved trees rather than asserted. `test-gate-anti-vacuity.sh` cannot reach these: its fixture copies `.ci/rediacc_ci` wholesale, so it hands this gate its real inputs and the gate correctly exits 0. Claiming a diagnostic there that cannot fire would be a false entry in a hand-verified registry, so the coverage lives here.
    with tempfile.TemporaryDirectory() as tmp:
        empty = pathlib.Path(tmp)
        mods, sites, _ = scan(empty)
        c.check("an empty tree discovers no module", mods, 0)
        c.check("...and no plant site", sites, 0)
        c.check("...and main() refuses on the MODULE arm", main_against(empty), "modules")

        # A tree with modules but no harness use: the rename case, and the one a token-counting gate would pass.
        (empty / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
        (empty / ".ci" / "rediacc_ci" / "quality" / "m.py").write_text("x = 1\n")
        mods2, sites2, _ = scan(empty)
        c.check("a module with no harness use is discovered", mods2, 1)
        c.check("...but contributes no plant site", sites2, 0)
        c.check(
            "...and main() refuses on the SITE arm, not the module arm",
            main_against(empty),
            "sites",
        )

    return 0 if c.report() else 2


def main_against(root: pathlib.Path) -> str:
    """WHICH refusal fires against an explicit root: "modules", "sites", "findings" or "".

    IT RETURNS THE REASON, NOT AN EXIT CODE, and that is the whole point. The two refusals overlap -- an empty tree has no modules AND no sites -- so a control
    asserting only `== 1` passes whichever arm is deleted, which is an assertion
    re-asking a question the next branch already answers. Found by planting: removing the module arm left the suite green until this returned the reason.
    """
    prev = os.environ.get("PY_CONTROL_PLANTS_ROOT")
    os.environ["PY_CONTROL_PLANTS_ROOT"] = str(root)
    try:
        modules, sites, findings = scan(_root())
        if modules == 0:
            return "modules"
        if sites == 0:
            return "sites"
        if findings:
            return "findings"
        return ""
    finally:
        if prev is None:
            os.environ.pop("PY_CONTROL_PLANTS_ROOT", None)
        else:
            os.environ["PY_CONTROL_PLANTS_ROOT"] = prev


def _root() -> pathlib.Path:
    """Resolved at CALL time, not import time.

    THE ANTI-VACUITY REFUSALS ARE UNTESTABLE OTHERWISE, and untested refusals are the thing this gate exists to object to. A module-level constant cannot be pointed at a starved tree from a control, so the two refusals below would have been asserted by nothing -- exactly the shape `.ci/scripts/test/gates/ test-gate-anti-vacuity.sh` looks for, and it cannot reach them itself because
    its fixture copies `.ci/rediacc_ci` wholesale and therefore feeds this gate its real inputs.
    """
    env = os.environ.get("PY_CONTROL_PLANTS_ROOT")
    if env:
        return pathlib.Path(env)
    return pathlib.Path(__file__).resolve().parents[2].parent


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    # CONTROLS FIRST, ALWAYS, not only under --selftest: a gate whose controls run only when asked is a gate whose controls do not run in CI.
    rc = selftest(verbose)
    if rc != 0:
        return rc
    if "--selftest" in argv:
        return 0

    modules, sites, findings = scan(_root())

    if modules == 0:
        print(
            "%s✗%s no Python gate module found under %s. The globs stopped matching, so "
            "the scan below compared nothing and its silence would mean nothing."
            % (RED, NC, " or ".join(SCOPE)),
            file=sys.stderr,
        )
        return 1
    if sites == 0:
        print(
            "%s✗%s scanned %d module(s) and found ZERO plant() call sites. Either the "
            "harness in %s was renamed and this gate was not updated, or every control "
            "stopped planting. Both make a green here meaningless, which is why this is "
            "a refusal and not a note." % (RED, NC, modules, HARNESS_MODULE),
            file=sys.stderr,
        )
        return 1
    if findings:
        print(
            "%s✗%s %d control plant(s) built by raw substitution:" % (RED, NC, len(findings)),
            file=sys.stderr,
        )
        for f in findings:
            print("    %s" % f, file=sys.stderr)
        print(
            "\n  A raw substitution that matches nothing hands the gate its CLEAN fixture "
            "and the control reports a pass for an assertion it never made. plant() "
            "refuses that at construction time.",
            file=sys.stderr,
        )
        return 1

    print(
        "%s✓%s %d Python gate module(s) scanned, %d plant() call site(s), no control "
        "mutant built by raw substitution" % (GREEN, NC, modules, sites)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
