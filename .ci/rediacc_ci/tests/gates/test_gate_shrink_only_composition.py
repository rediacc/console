"""Port of `.ci/scripts/test/gates/test-shrink-only-composition.sh`, retired in W7 P5.

Every shrink-only baseline in this repo must enforce shrink-only on the WRITE path, and this file is both the detector and its test: there is no separate `check-*.ts` to shell out to, so porting it means re-expressing the scan in Python. Parity here is therefore a claim about two implementations agreeing on the same tree, which is why the controls matter more than usual.

WHY IT EXISTS. Seven gates freeze a backlog and describe it as shrink-only. All seven enforced that on the READ path only; the drain flag was an unconditional reseed in every one. The difference is not academic:

    as enforced:  the TOTAL cannot grow without someone noticing.
    as promised:  the SET can only lose members.

A reseed that drains thirty findings and absorbs one satisfies the first, violates the second, and prints a SMALLER number while doing it. On 2026-08-20 the guard added to `scripts/gates/check-em-dash-surfaces.ts` refused, on its first real run, a reseed that would have enshrined two em dashes a background naturalization job had introduced minutes earlier.

STRUCTURAL PLUS BEHAVIOURAL, and the split is deliberate. Driving every gate's drain flag for real would mean rewriting live suppression files, and four of the gates do not even accept a `--baseline` override to redirect the write. So the structural half asserts that every CLI offering the flag consumes the shared guard, and the behavioural half proves the guard really refuses, end
to end, on the one gate that CAN be pointed at a copy.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. The scan enumerates the working tree through `git ls-files --cached --others`, and four control cases PLANT a probe file inside `scripts/` and `.ci/scripts/quality/` and remove it again -- the lock records `mutex: ["tree:repo"]` for `gate-test:shrink-only-composition`
for exactly that reason. A battery step reading either directory mid-plant is the
flake that would be blamed on this port. `REAL_TREE_TWIN = True` buys the
serialisation, and it is honoured only because this module declares no `XDIST_GROUP` of its own.

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

# Four control cases plant a probe inside the scanned tree. See the docstring.
REAL_TREE_TWIN = True

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


def py_offers_flag(tree) -> bool:
    """True when the module PARSES the flag, not when it merely names it.

    A writer reads the flag off its argument vector: `FLAG in argv` / `FLAG not in args`, `arg == FLAG`, or `parser.add_argument(FLAG, ...)`. A docstring, an error message telling the reader to run it, and a test passing it to a subprocess all name the flag without offering it, and treating those as writers is what put four test modules on the offender list.
    """

    def is_flag(node) -> bool:
        return isinstance(node, ast.Constant) and node.value == FLAG

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
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


# Floors, one per corpus. Neither excuses the other; see the docstring.
TS_FLOOR = 8


def git_bin() -> str:
    return harness.require_tool("git", "install git; the corpus comes from `git ls-files`")


def all_offerers() -> list[str]:
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
        cwd=ROOT,
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
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            # A corpus file can VANISH mid-run: this very detector plants and removes probes inside the scanned tree, and so does its twin. An unreadable neighbour is not this gate's finding.
            continue
        if FLAG in text:
            found.append(rel)
    return sorted(found)


def offerers() -> list[str]:
    return [f for f in all_offerers() if f.endswith((".ts", ".js"))]


def offerers_py() -> list[str]:
    return [f for f in all_offerers() if f.endswith(".py")]


def py_parse(rel: str):
    """The module's AST, or None when it does not parse. A file that cannot be read as Python cannot be shown to be guarded, so the caller treats None as an offender rather than skipping it."""
    text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    try:
        return ast.parse(text, filename=rel)
    except SyntaxError:
        return None


def py_is_writer(rel: str) -> bool:
    """A Python file in the text corpus that really OFFERS the flag. Unparseable counts as a writer, so a syntax error cannot hide one."""
    tree = py_parse(rel)
    return tree is None or py_offers_flag(tree)


def py_reaches_guard(rel: str) -> bool:
    """All three conditions, or the Python writer is unguarded."""
    tree = py_parse(rel)
    return tree is not None and py_guard_calls(tree) == set(PY_GUARD_FUNCS)


def unguarded_py() -> list[str]:
    return [
        f
        for f in offerers_py()
        if f not in PY_EXEMPT and py_is_writer(f) and not py_reaches_guard(f)
    ]


def unguarded() -> list[str]:
    """Files that offer the flag, are not exempt, and reach the guard by no route."""
    out = []
    for rel in offerers():
        if rel in EXEMPT:
            continue
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if not any(pattern.search(text) for pattern in IMPORT_RE.values()):
            out.append(rel)
    return out


@contextlib.contextmanager
def probe(rel_dir: str, stem: str, suffix: str, body: str):
    """Plant one probe inside the SCANNED tree, yield its repo-relative path, and remove it whatever happens.

    NOT A TEMP DIR. The corpus is `git ls-files` over this repository, so a probe outside it is invisible and the control silently stops firing -- which is the failure a plant-based control exists to rule out, not to reproduce. The removal is in a `finally` so a killed run cannot leave a synthetic offerer in a tracked directory, where the next reader would investigate a finding
    nobody introduced.
    """
    name = "%s_%d%s" % (stem, os.getpid(), suffix)
    rel = "%s/%s" % (rel_dir, name)
    path = ROOT / rel
    path.write_text(body, encoding="utf-8")
    try:
        yield rel
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
    proc = subprocess.run([sys.executable, "gate.py", "%s"], check=False)
    assert proc.returncode == 1, "run it again with %s --first-seed"
''' % (FLAG, FLAG, FLAG)

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
    gate.log_pass(
        "every non-exempt baseline writer consumes the guard (%d offerer(s) scanned)"
        % len(offerers())
    )


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
    ) as rel:
        seen = rel in offerers_py()
        detected = rel in unguarded_py()
    if (ROOT / rel).exists():
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
    ) as rel:
        mentioned = rel in unguarded_py()
        (ROOT / rel).write_text(GUARDED_PY_BODY, encoding="utf-8")
        guarded = rel not in unguarded_py()
    if (ROOT / rel).exists():
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
    ) as rel:
        writer = py_is_writer(rel)
        guarded = rel not in unguarded_py()
        (ROOT / rel).write_text(IMPORT_ONLY_PY_BODY, encoding="utf-8")
        import_only_caught = rel in unguarded_py()
    if (ROOT / rel).exists():
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
    ) as rel:
        seen = rel in offerers_py()
        writer = py_is_writer(rel)
        reported = rel in unguarded_py()
    if (ROOT / rel).exists():
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
    with probe("scripts", "zz-composition-control-probe-port", ".ts", UNGUARDED_TS_BODY) as rel:
        detected = rel in unguarded()
    if (ROOT / rel).exists():
        gate.log_fail("control probe was not removed")
    if not detected:
        gate.log_fail(
            "CONTROL FAILED: an unguarded reseed was NOT detected, so this gate cannot fail"
        )
    gate.log_pass("CONTROL: a planted unguarded reseed is detected")


def test_control_mention_is_not_an_import(gate):
    """CONTROL. A file that only MENTIONS the choke point in prose must NOT count as guarded. Without this, the transitive route above is a substring match masquerading as a check."""
    with probe("scripts", "zz-composition-mention-probe-port", ".ts", MENTION_TS_BODY) as rel:
        detected = rel in unguarded()
    if (ROOT / rel).exists():
        gate.log_fail("mention probe was not removed")
    if not detected:
        gate.log_fail("CONTROL FAILED: a prose mention was accepted as a guard route")
    gate.log_pass("CONTROL: naming the guard in a comment does not count as consuming it")


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
