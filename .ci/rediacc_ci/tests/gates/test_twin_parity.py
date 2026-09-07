"""Every ported gate test and its bash twin must reach the SAME VERDICT on THIS tree.

WHY THIS FILE IS THE POINT OF THE PORT. A migration that changes a verdict is not a
migration, it is a regression wearing one. The only way to know a port still says
what the original said is to run BOTH, on the same tree, in the same run -- which is
also why invariant 5 forbids deleting a twin in the change that ports it. A twin kept
but never driven is a twin that quietly rots; a twin driven on every run is a
control.

WHAT IS COMPARED, and why it is not "did they both exit 0".

  1. THE VERDICT. Both green, or both red. A port that goes green where the twin
     goes red has stopped asserting something; a port that goes red where the twin
     goes green has invented a finding. Either is a defect in the port, and the
     message says which direction it went.

  2. THE CASE SET, which is SET-BASED and therefore cannot be satisfied by a count.
     Every `test_*()` function the twin DECLARES AND CALLS must have a same-named
     `def test_*` in the port. Dropping one case while keeping the others is exactly
     the failure a count of tests would let through -- delete a case, add a case, the
     total is unchanged and the composition is not. (The port may ADD cases; several
     do, to prove a reader the twin implemented in awk and the port reimplemented in
     Python agree.)

  3. FOR A FLAT TWIN, which declares no functions at all, there is no case set to
     compare, so the floor falls back to the twin's own `PASS:` line count MEASURED
     AT RUNTIME. Still corpus-derived -- it moves when the twin moves -- and never
     typed here.

THE CONTROL COUNTS COME FROM A LEDGER, not from parsing pytest's output. The port
runs in a subprocess with `$GATE_HARNESS_LEDGER` pointing at a scratch file, and
`Harness` appends one JSON row per recorded control. Parsing "N passed" would count
TEST FUNCTIONS, which is the number that says nothing about whether they asserted.

ANTI-VACUITY. Discovering zero ported modules is a FAILURE, not an empty parametrize
that reports green having compared nothing. `test_the_registry_is_not_empty` is that
refusal, and it prints the shape so a collapse is visible rather than silent.
"""

import importlib
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from rediacc_ci import paths, xdist_groups
from rediacc_ci.tests.gates import harness

HERE = pathlib.Path(__file__).resolve().parent

# A ported module is one whose name starts `test_gate_` AND that declares a
# `BASH_TWIN`. Both halves matter: the prefix keeps this file and the harness's own
# controls out of the set, and the attribute is what makes membership a DECLARATION
# rather than a guess about a filename.
MODULE_GLOB = "test_gate_*.py"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
BASH_FN_RE = re.compile(r"^(test_[A-Za-z0-9_]+)\(\)\s*\{", re.MULTILINE)
PY_FN_RE = re.compile(r"^def (test_[A-Za-z0-9_]+)\s*\(", re.MULTILINE)
PASS_LINE_RE = re.compile(r"^PASS:", re.MULTILINE)


def ported_modules() -> list[tuple[str, pathlib.Path, str]]:
    """(module name, module path, twin repo-relative path), sorted."""
    found = []
    for path in sorted(HERE.glob(MODULE_GLOB)):
        module = importlib.import_module("rediacc_ci.tests.gates." + path.stem)
        twin = getattr(module, "BASH_TWIN", None)
        if isinstance(twin, str) and twin:
            found.append((path.stem, path, twin))
    return found


MODULES = ported_modules()


def real_tree_tests() -> set[str]:
    """Gate tests that touch the REAL tree while they run, from both sources.

    WHY THIS EXISTS, and it is the constraint the remaining batches will hit. Driving
    a bash twin from inside `check:ci-pytest` makes that gate a participant in the
    battery's isolation contract WITHOUT declaring anything to either scheduler. Four
    of the 148 write into the real tree (one of them rewrites CLAUDE.md and
    scripts/data/doc-registry.md and restores them) and about twenty read it; a
    parity run overlapping one of those is the `cp: cannot stat` / grep-exit-2 flake
    that run-all.sh's W/S/T schedule exists to prevent, and it would be blamed on the
    port.

    THE UNION ITSELF NOW LIVES IN `rediacc_ci.xdist_groups`, and this is a call into
    it rather than a copy of it. The parallel scheduler asks the SAME question this
    test asks -- which twins may not run beside another -- and two implementations of
    one question is two answers, the expensive half being that both look right. The
    reasons for the two sources, and for the anti-vacuity refusal on their union, are
    written there.
    """
    return xdist_groups.real_tree_twins(xdist_groups.lock_path())


def bash_cases(twin_source: str) -> set[str]:
    """Function names the twin both DECLARES and CALLS.

    Declared-but-never-called is dead code in a shell script, and pinning a port
    against a case the twin does not run would demand coverage of something nothing
    covers. Requiring both halves is also how this notices a twin whose bottom-of-file
    call list lost an entry.

    A CALL IS NOT ALWAYS A BARE NAME ON ITS OWN LINE, and requiring that was a hole
    that failed OPEN. This predicate was a bare-name-on-its-own-line match, so a twin invoking its cases
    as `test_mapping_form_is_caught "$D/mapping"` or `with_temp_dir test_flags_runner`
    matched nothing at all. Measured 2026-09-07 across the 130 twins that declare
    cases: 43 had at least one case invisible here, and 16 saw ZERO. A twin seeing
    zero does not fail; it falls through to the flat-twin floor (the twin's runtime
    `PASS:` count), so the SET comparison this module exists to perform silently did
    not happen for those 16, `test-ci-parity.sh` (22 cases) among them.

    The two error directions are not symmetric, which is why widening is right.
    Over-admitting demands the port cover a case the twin does not run: noisy, and it
    fails CLOSED. Under-admitting drops the set check entirely and fails OPEN. So a
    name is called when it appears as a WORD on any line that is neither its own
    declaration nor a whole-line comment.

    Widening was checked against the ports before landing: it adds zero newly-required
    cases that any of the 53 current ports lacks, so it strengthens the check without
    reclassifying existing work.
    """
    declared = set(BASH_FN_RE.findall(twin_source))
    lines = twin_source.splitlines()
    called = set()
    for name in declared:
        declaration = re.compile(r"^\s*%s\(\)" % re.escape(name))
        word = re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(name))
        for line in lines:
            if declaration.match(line) or re.match(r"^\s*#", line):
                continue
            if word.search(line):
                called.add(name)
                break
    return called


def run_port(module_path: pathlib.Path, ledger: pathlib.Path):
    """(returncode, control count) for the ported module, run on its own.

    A SUBPROCESS and not an in-process re-run: the module is already being collected
    by the outer session, and re-entering it here would double every side effect and
    make the ledger a sum of two runs.

    NO `-p no:cacheprovider`, and the reason is a trap worth writing down. Disabling
    that plugin UNREGISTERS the `cache_dir` ini key, and this repo's pyproject sets
    both `cache_dir` and `--strict-config`; the nested pytest then exits 4 with
    "Unknown config option: cache_dir" and collects nothing. It was found by this
    very test refusing to call that a pass, which is the whole argument for comparing
    verdicts rather than trusting a green. The nested run therefore shares the
    outer run's cache directory, which is gitignored and per-worktree already.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(module_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.repo_root()),
        env={**os.environ, harness.LEDGER_ENV: str(ledger)},
        timeout=600,
    )
    rows = []
    if ledger.is_file():
        rows = [
            json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line
        ]
    return proc, len([r for r in rows if r.get("event") == "pass"])


def test_the_registry_is_not_empty(gate):
    """ANTI-VACUITY. Zero ported modules means the parametrize below compared
    nothing, and an empty parametrize is green."""
    if not MODULES:
        gate.log_fail(
            "no ported gate module under %s declares a BASH_TWIN. Either the glob %r "
            "stopped matching or the ports were removed; either way the parity "
            "comparison below ran against nothing and its green means nothing."
            % (paths.relative_to_root(HERE), MODULE_GLOB)
        )
    for _name, _path, twin in MODULES:
        if not paths.from_root(*twin.split("/")).is_file():
            gate.log_fail("BASH_TWIN %s does not exist; the parity claim cannot be made" % twin)
    gate.log_pass(
        "%d ported module(s) declare a twin, and every twin file exists: %s"
        % (len(MODULES), ", ".join(name for name, _, _ in MODULES))
    )


def test_no_ported_twin_is_a_real_tree_writer_or_scanner(gate):
    """A twin driven from here must be fixture-isolated. See `real_tree_tests`."""
    unsafe = real_tree_tests()
    # ANTI-VACUITY, and it is the whole check: an empty set would make the loop
    # below pass for every module forever. Both sources going quiet at once is
    # exactly the state this refusal must not be satisfied by.
    if not unsafe:
        gate.log_fail(
            "neither gates.lock.json nor run-all.sh's *_FALLBACK arrays name a single "
            "real-tree test, so the refusal below would admit every twin including the "
            "four that rewrite tracked files. Fix the reader before trusting this."
        )
    offenders = sorted(name for name, _, twin in MODULES if os.path.basename(twin) in unsafe)
    if offenders:
        gate.log_fail(
            "%d ported module(s) drive a twin that touches the real tree: %s. "
            "check:ci-pytest declares no isolation to either scheduler, so a parity "
            "run overlapping the battery is a flake nobody can reproduce. Port those "
            "twins without the parity driver, or land the `tree:` declarations first."
            % (len(offenders), ", ".join(offenders))
        )
    gate.log_pass(
        "none of the %d ported twins is among the %d real-tree test(s) known to the "
        "lock and to run-all.sh" % (len(MODULES), len(unsafe))
    )


@pytest.mark.parametrize(("name", "module_path", "twin"), MODULES, ids=[m[0] for m in MODULES])
def test_port_and_twin_agree(gate, tmp_path, name, module_path, twin):
    twin_path = paths.from_root(*twin.split("/"))
    twin_run = harness.run(["bash", str(twin_path)], timeout=600)
    twin_passes = len(PASS_LINE_RE.findall(ANSI_RE.sub("", twin_run.out)))

    port_proc, port_controls = run_port(module_path, tmp_path / "ledger.jsonl")

    twin_green = twin_run.rc == 0
    port_green = port_proc.returncode == 0
    if twin_green != port_green:
        gate.log_fail(
            "VERDICT DIVERGED for %s: the twin %s (rc=%d) and the port %s (rc=%d) on the "
            "same tree. A port that changes a verdict is a regression, not a migration.\n"
            "--- twin stdout ---\n%s\n--- twin stderr ---\n%s\n"
            "--- port stdout ---\n%s\n--- port stderr ---\n%s"
            % (
                name,
                "passed" if twin_green else "FAILED",
                twin_run.rc,
                "passed" if port_green else "FAILED",
                port_proc.returncode,
                twin_run.out,
                twin_run.err,
                port_proc.stdout,
                port_proc.stderr,
            )
        )
    gate.log_pass("%s: twin and port agree (both %s)" % (name, "green" if twin_green else "red"))

    cases = bash_cases(twin_path.read_text(encoding="utf-8"))
    ported = set(PY_FN_RE.findall(module_path.read_text(encoding="utf-8")))
    if cases:
        missing = sorted(cases - ported)
        if missing:
            gate.log_fail(
                "%s dropped %d case(s) the twin runs: %s. Port them or say in the module "
                "docstring why the case cannot exist in Python; do not let the total "
                "hide the composition." % (name, len(missing), ", ".join(missing))
            )
        gate.log_pass(
            "%s: all %d twin case(s) are present in the port (%d test(s) total)"
            % (name, len(cases), len(ported))
        )
    else:
        # A FLAT TWIN has no case set, so the floor is its runtime PASS count.
        if port_controls < twin_passes:
            gate.log_fail(
                "%s is a flat twin printing %d PASS line(s), but the port recorded only "
                "%d control(s). A flat script has no case names to compare, so the only "
                "floor available is the twin's own output, and the port is under it."
                % (name, twin_passes, port_controls)
            )
        gate.log_pass(
            "%s: flat twin printed %d PASS line(s); the port recorded %d control(s)"
            % (name, twin_passes, port_controls)
        )

    # The shape, printed on every run so a collapse is visible rather than silent.
    gate.log_info(
        "%s: twin rc=%d passes=%d | port rc=%d controls=%d tests=%d"
        % (name, twin_run.rc, twin_passes, port_proc.returncode, port_controls, len(ported))
    )
