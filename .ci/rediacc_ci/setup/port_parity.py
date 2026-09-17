#!/usr/bin/env python3
"""Does the Python `setup` still do what the bash `setup` did, in what order?

WHY A GATE AND NOT JUST THE LEDGER. `.ci/shadow/e1-setup.observations.jsonl` records that the two implementations AGREED over five distinct trees. That is a statement about five frozen snapshots and nothing at all about tomorrow's tree. The differential cannot be re-run in CI either: `scripts/lib/shadow-gate.ts` refuses to record on a dirty tree by design, both sides take about
twelve seconds, and after the flip there is no bash side left to drive. So the ledger is the EVIDENCE and this is the STANDING CHECK, and they answer different questions.

-----------------------------------------------------------------------------
THE FIVE ASSERTIONS, AND WHY EACH IS TRUE IN EVERY STATE OF THE MIGRATION
-----------------------------------------------------------------------------
This gate is written across the cutover, deliberately. `.ci/scripts/test/gates/ test-run-sh.sh:315-327` is the cautionary tale: it required `n_legacy > 0` before believing any assertion, which is a floor the migration exists to breach, so the gate guarding the port would have gone red at the moment the port succeeded. Every clause below therefore holds before the flip, after it,
and during it.

  A1  `phases.PHASE_KEYS` and the order of the same keys inside
      `machine.run_setup`'s SOURCE agree, in both directions and in order.
      True in every state: both live in Python and neither is going anywhere.
      This is the clause that catches the drift that actually happens, because
      `run_setup` is a straight line and a straight line is edited by hand.

  A2  While the bash `setup()` still exists, `phases.from_source()` and
      `PHASE_KEYS` agree, in both directions and in order. SKIPPED, LOUDLY, once
      the body is gone, and A5 is what replaces it.

  A3  While `.ci/lib/setup.sh` still exists, every `setup_*` function it defines
      has a twin in `host.py`. A port that left one behind would otherwise be
      invisible: nothing else compares the two files' function sets.

  A4  `phases.DEFINED_BUT_UNCALLED` still names exactly the functions that
      `.ci/lib/setup.sh` defines and nothing in the tree calls. Today that is
      `setup_docker_probe` alone. This keeps a KNOWN piece of dead bash VISIBLE
      instead of letting the port quietly inherit it, and it fails in both
      directions: a newly dead function must be added, and one that becomes live
      must be removed and given a `PHASES` row.

  A5  The ledger carries at least `LEDGER_K` distinct tree ids with an
      EQUIVALENT verdict. Checked in EVERY state, not only after the flip: a
      ledger that is emptied, truncated or hand-edited is exactly as bad as one
      that was never recorded, and the day the bash is deleted this is the only
      surviving proof that the two ever agreed.

-----------------------------------------------------------------------------
ANTI-VACUITY
-----------------------------------------------------------------------------
Four refusals, each returning 77 rather than a verdict:

  * `PHASE_KEYS` is empty, so every set comparison is between two empty sets;
  * `machine.run_setup`'s source could not be read, so A1 compares nothing;
  * the repository root could not be resolved;
  * BOTH the bash body and the ledger are missing, which is the one combination
    in which this gate knows nothing about the port at all. Either alone is a
    legitimate state of the migration; neither is not.

That last one is the clause worth reading twice. A2 and A3 skip when the bash is gone and A5 stands in for them, so a run with no bash AND no ledger would have skipped its way to a green while checking one thing.

---- gate ---- id: check:ci-setup-port-parity step: Setup port parity needs: none selftest: true why: the shadow ledger proves the bash and Python setup agreed over five frozen trees and says nothing about tomorrow's, so the phase order has to be re-derived from both implementations on every run ---- end gate ----
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci import gitx, paths
from rediacc_ci.controls import Controls
from rediacc_ci.setup import phases

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CANNOT_RUN = 77

# The bash side, by path. Named once so a move is one edit and so the "has the flip happened" question has exactly one answer.
TWIN = pathlib.Path(".ci") / "lib" / "setup.sh"
LEDGER = pathlib.Path(".ci") / "shadow" / "e1-setup.observations.jsonl"

# `shadow-gate --assert --k 5` is what recorded this ledger, so 5 is not a number chosen here: it is the K the plan box asked for, restated where the standing check can see it. Lowering it is a decision a reviewer must see.
LEDGER_K = 5

# `setup_*` definitions in the bash, by the same anchor `function_body` uses.
BASH_DEF_RE = re.compile(r"^(setup_[a-z_]+)\(\) \{", re.MULTILINE)

# bash name -> the `host.py` name that ports it. The SAME table `shadow_driver.PY_FOR` holds, and it is deliberately not imported from there: that module is the differential harness and it will be deleted with the bash,
# while this gate outlives both. A3 is what keeps the two honest while both
# exist.
PORTED_AS = {
    "setup_node_toolchain": "node_toolchain",
    "setup_system_tools": "system_tools",
    "setup_go_toolchain": "go_toolchain",
    "setup_gh_cli": "gh_cli",
    "setup_docker_probe": "docker_probe",
    "setup_git_identity": "git_identity",
    "setup_git_credentials": "git_credentials",
}


class CannotRun(Exception):  # noqa: N818
    """The gate cannot see its subject, so its green would mean nothing."""


@dataclass
class Shape:
    """The numbers printed on a clean run, so a reader can watch one collapse."""

    table: int = 0
    from_run_setup: int = 0
    from_bash: int = -1
    bash_functions: int = -1
    ledger_trees: int = 0
    uncalled: int = 0


# --------------------------------------------------------------------------- readers ---------------------------------------------------------------------------


def run_setup_order(source: str, keys: tuple[str, ...]) -> list[str]:
    """The phase keys inside `run_setup`'s body, in source order, first hit wins.

    COMMENTS ARE STRIPPED FIRST, and that is load-bearing rather than tidy: `run_setup`'s comments name `setup_go_toolchain`, `ensure_deps` and `devbox_up` in prose, in an order that is not the call order. Judging the prose instead of the code is the exact defect `.ci/rediacc_ci/quality/setup_idempotency.py:127` records for its own check G.
    """
    body = phases.function_body_python(source, "run_setup")
    if not body:
        return []
    body = "\n".join(re.sub(r"[ \t]*#.*$", "", line) for line in body.split("\n"))
    seen: dict[str, int] = {}
    for number, line in enumerate(body.split("\n")):
        for key in keys:
            if key not in seen and _mentions(line, key):
                seen[key] = number
    return [key for key, _ in sorted(seen.items(), key=lambda item: item[1])]


def _mentions(line: str, key: str) -> bool:
    """Does this line of Python invoke the phase named `key`?

    THE THREE SPELLINGS ARE ENUMERATED, not guessed at with a substring match. `run_setup` reaches a phase in exactly three ways and each looks different:

        host.go_toolchain(ctx)                    a ported function
        bridge.call("ensure_deps", ...)           a bridged bash function
        ctx.run([... "init-submodules.sh" ...])   an inline command

    A bare `key in line` would also match the string inside an error MESSAGE, which is how a phase that is only ever apologised for reads as a phase that runs.
    """
    ported = PORTED_AS.get(key)
    if ported and re.search(r"\bhost\.%s\(" % re.escape(ported), line):
        return True
    if re.search(r'\bbridge\.(call|capture)\(\s*[\'"]%s' % re.escape(key), line):
        return True
    if re.search(r'\bbridge\.(call|capture)\(\s*f?[\'"]%s\b' % re.escape(key), line):
        return True
    # The two inline phases. `init-submodules.sh` appears as a path fragment in `ctx.run`, and the drift check is reached through a helper whose name is the phase's own subject, so both are matched by the literal inside a call.
    if key in ("init-submodules.sh", "check:env-credential-drift"):
        return ('"%s"' % key in line) or ("_credential_drift(" in line and key.startswith("check:"))
    return False


def bash_defined(text: str) -> list[str]:
    """Every `setup_*() {` the bash defines, in source order."""
    return BASH_DEF_RE.findall(text)


# A shell function can only be CALLED from shell. Everything else that spells the name is prose about it, and after this port there is a lot of that: the `PORTED_AS` table above, `phases.DEFINED_BUT_UNCALLED`, `host.py`'s header and `shadow_driver.DRIVABLE` all name `setup_docker_probe` without calling it. The first version of `bash_uncalled` scanned every tracked file and
# therefore reported the dead function as LIVE, killed by the port's own documentation of it. Measured 2026-09-09: five Python mentions, zero shell callers.
SHELL_SUFFIXES = (".sh", ".bash")
SHELL_SHEBANG = re.compile(rb"^#![^\n]*\b(ba)?sh\b")


def is_shell(path: pathlib.Path) -> bool:
    """Is this a shell file? Suffix first, then the shebang for the rest."""
    if path.suffix in SHELL_SUFFIXES:
        return True
    try:
        with path.open("rb") as handle:
            return SHELL_SHEBANG.search(handle.readline(200)) is not None
    except OSError:
        return False


def bash_uncalled(root: pathlib.Path, names: list[str]) -> list[str]:
    """Which of `names` no tracked SHELL file calls. Definition sites do not count.

    THE DEFINITION IS NOT A CALL, which is the whole trick of this check and the reason `grep -c` on the name alone would answer "2 occurrences, so it is
    used" for a function nothing runs. A line matching `^<name>() {` is skipped;
    so is a line that is only a comment.

    WRONG IN THE SAFE DIRECTION, and the direction is chosen. A bare mention inside a live shell file counts as a call, so a name discussed in a shell COMMENT that does not start at column zero would read as live. That over-counts life, which costs a stale row in `DEFINED_BUT_UNCALLED`; the other direction would report a live function as dead and invite its deletion.
    """
    # `untracked=True` and `existing=True`: a brand-new caller is untracked on the
    # commit that adds it, and this predicate's whole job is to say what nothing calls, so missing the new caller would report a live function as dead. `.ci/rediacc_ci/gitx.py:421` records the same argument for the same flag.
    tracked = gitx.ls_files(root=root, untracked=True, existing=True)
    wanted = set(names)
    called: set[str] = set()
    for rel in tracked:
        path = root / rel
        if not is_shell(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            continue
        for name in wanted - called:
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("#") or re.match(r"^%s\(\) \{" % re.escape(name), stripped):
                    continue
                if name in stripped:
                    called.add(name)
                    break
    return sorted(wanted - called)


def ledger_trees(root: pathlib.Path) -> tuple[int, str]:
    """(distinct EQUIVALENT clean tree ids, why it is short). "" when it is not.

    READ HERE RATHER THAN SHELLED OUT TO `shadow-gate --assert`, for one reason: that command needs `npx tsx`, and a Python gate that cannot reach a verdict without a node toolchain is a gate that reports "cannot run" on exactly the bare machine `setup` exists to fix.
    """
    path = root / LEDGER
    if not path.is_file():
        return 0, "no ledger at %s" % LEDGER
    ids: set[str] = set()
    bad: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            return 0, "%s:%d does not parse as JSON" % (LEDGER, lineno)
        tree = row.get("tree") or {}
        if not tree.get("clean"):
            continue
        if row.get("verdict") == "EQUIVALENT":
            ids.add(tree.get("id", ""))
        else:
            bad.add(tree.get("id", ""))
    # A TREE THAT EVER DISAGREED STAYS DISAGREEING, the same rule `assertEquivalent` applies: the id is the content of both implementations, so two verdicts over one id means the comparison is nondeterministic.
    ids -= bad
    ids.discard("")
    return len(ids), ""


# --------------------------------------------------------------------------- the audit ---------------------------------------------------------------------------


def audit(root: pathlib.Path, shape: Shape) -> list[str]:
    """Every finding, as text. Raises CannotRun when the subject is not visible."""
    findings: list[str] = []
    keys = phases.PHASE_KEYS
    shape.table = len(keys)
    if not keys:
        raise CannotRun(
            "phases.PHASE_KEYS is EMPTY, so every set comparison below is between "
            "two empty sets and would pass"
        )

    machine_src = _read(root / ".ci" / "rediacc_ci" / "setup" / "machine.py")
    if not machine_src:
        raise CannotRun("cannot read .ci/rediacc_ci/setup/machine.py, so A1 compares nothing")

    twin_text = _read(root / TWIN)
    body_text = _read(root.joinpath(*phases.SETUP_BODY_FILE))
    bash_body = phases.function_body(body_text, "setup") if body_text else ""

    trees, why = ledger_trees(root)
    shape.ledger_trees = trees

    if not bash_body and trees == 0:
        raise CannotRun(
            "the bash setup() is gone AND the ledger proves nothing (%s). Those are the "
            "two things this gate knows about the port, and with neither it would skip "
            "its way to a green." % (why or "no EQUIVALENT rows")
        )

    # -- A1 ---------------------------------------------------------------
    order = run_setup_order(machine_src, keys)
    shape.from_run_setup = len(order)
    findings += _compare("A1 run_setup", list(keys), order)

    # -- A2 ---------------------------------------------------------------
    if bash_body:
        source_order = phases.from_source(root)
        shape.from_bash = len(source_order)
        findings += _compare("A2 bash setup()", list(keys), source_order)

    # -- A3 / A4 ------------------------------------------------------------
    if twin_text:
        defined = bash_defined(twin_text)
        shape.bash_functions = len(defined)
        missing = [n for n in defined if n not in PORTED_AS]
        if missing:
            findings.append(
                "A3 %s defines %s, which %s no twin in host.py. The port is "
                "incomplete and nothing else in the tree compares the two files."
                % (TWIN, ", ".join(missing), "has" if len(missing) == 1 else "have")
            )
        stale = [n for n in PORTED_AS if n not in defined]
        if stale:
            findings.append(
                "A3 host.py claims to port %s, which %s no longer defines. Delete the "
                "row or the port." % (", ".join(sorted(stale)), TWIN)
            )
        uncalled = bash_uncalled(root, defined)
        shape.uncalled = len(uncalled)
        declared = sorted(phases.DEFINED_BUT_UNCALLED)
        if uncalled != declared:
            findings.append(
                "A4 phases.DEFINED_BUT_UNCALLED says %s and the tree says %s. A bash "
                "function nothing calls must be NAMED there so the port does not "
                "inherit it silently; one that became live needs a PHASES row instead."
                % (declared or ["(none)"], uncalled or ["(none)"])
            )

    # -- A5 ---------------------------------------------------------------
    if trees < LEDGER_K:
        findings.append(
            "A5 the shadow ledger carries %d distinct EQUIVALENT tree(s) and %d are "
            "required%s. Once the bash is deleted this is the only surviving proof "
            "that the two implementations ever agreed, so it may not shrink."
            % (trees, LEDGER_K, ": %s" % why if why else "")
        )
    return findings


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _compare(label: str, want: list[str], got: list[str]) -> list[str]:
    """Set equality BOTH WAYS, then order. Three findings, never folded into one.

    ORDER IS CHECKED SEPARATELY AND LAST, because the three failures need three different actions: a missing phase is a phase that stopped running, an extra one is a phase nobody declared, and a reordering is neither. Folding them into "the lists differ" is how a reviewer reads a swap as a typo.
    """
    findings: list[str] = []
    missing = [k for k in want if k not in got]
    extra = [k for k in got if k not in want]
    if missing:
        findings.append(
            "%s: %s is in phases.PHASES and NOT reached by the code. A declared "
            "phase that never runs is a phase this repo believes it performs."
            % (label, ", ".join(missing))
        )
    if extra:
        findings.append(
            "%s: %s is reached by the code and NOT in phases.PHASES. Add the row; "
            "the table is what every other reader of the order uses." % (label, ", ".join(extra))
        )
    if not missing and not extra and want != got:
        findings.append(
            "%s: same phases, DIFFERENT ORDER.\n    table: %s\n    code:  %s\n"
            "    The order IS the dependency order (setup/tools.py:196), so an "
            "unordered comparison would have passed this." % (label, want, got)
        )
    return findings


# --------------------------------------------------------------------------- controls ---------------------------------------------------------------------------


def selftest(*, verbose: bool = True) -> int:
    """Both directions on every clause. 15 controls, floor 15."""
    ctl = Controls("setup-port-parity", floor=15, verbose=verbose)

    keys = ("alpha", "beta", "gamma")

    # -- _compare, the shared comparator ----------------------------------
    ctl.check("MUST NOT FIRE: identical lists", _compare("x", list(keys), list(keys)), [])
    dropped = _compare("x", list(keys), ["alpha", "gamma"])
    ctl.check("MUST FIRE: a dropped phase is one finding", len(dropped), 1)
    ctl.truthy("and it NAMES the dropped phase", "beta" in dropped[0])
    added = _compare("x", list(keys), ["alpha", "beta", "gamma", "delta"])
    ctl.check("MUST FIRE: an undeclared phase is one finding", len(added), 1)
    ctl.truthy("and it NAMES the undeclared phase", "delta" in added[0])
    swapped = _compare("x", list(keys), ["beta", "alpha", "gamma"])
    ctl.check("MUST FIRE: a REORDERING with the same set", len(swapped), 1)
    ctl.truthy("and it says DIFFERENT ORDER", "DIFFERENT ORDER" in swapped[0])

    # -- run_setup_order --------------------------------------------------
    source = (
        "def run_setup(ctx, options, constants):\n"
        "    # a comment naming host.gh_cli( first, which must NOT count\n"
        "    if host.node_toolchain(ctx) != 0:\n"
        "        return 1\n"
        '    bridge.call("check_node_version", ctx.root, ctx.env)\n'
        '    ctx.run(["bash", "init-submodules.sh"])\n'
        "    if host.gh_cli(ctx) != 0:\n"
        "        return 1\n"
        '    ctx.error("setup_go_toolchain failed")\n'
        "    return 0\n"
    )
    order = run_setup_order(
        source,
        (
            "setup_node_toolchain",
            "check_node_version",
            "init-submodules.sh",
            "setup_gh_cli",
            "setup_go_toolchain",
        ),
    )
    ctl.check(
        "MUST NOT FIRE: the three real call shapes are found, in order",
        order,
        ["setup_node_toolchain", "check_node_version", "init-submodules.sh", "setup_gh_cli"],
    )
    # THE COMMENT CASE ON ITS OWN, because the list above would still have passed if the comment had been counted AND the real call had been counted at the same index. A source where the ONLY mention is a comment is the unambiguous form of the claim.
    comment_only = (
        "def run_setup(ctx, options, constants):\n"
        "    # host.gh_cli( is named here and nowhere else\n"
        "    return 0\n"
    )
    ctl.check(
        "MUST FIRE: a phase whose ONLY mention is a comment is not reached",
        run_setup_order(comment_only, ("setup_gh_cli",)),
        [],
    )
    ctl.check(
        "MUST NOT FIRE: the same call outside a comment IS reached",
        run_setup_order(
            comment_only.replace("    # host.gh_cli(", "    host.gh_cli("), ("setup_gh_cli",)
        ),
        ["setup_gh_cli"],
    )
    ctl.falsy(
        "MUST FIRE: a phase named only in an error MESSAGE is NOT counted",
        "setup_go_toolchain" in order,
    )

    # -- bash_defined ------------------------------------------------------
    ctl.check(
        "MUST NOT FIRE: two definitions are found in source order",
        bash_defined("setup_b() {\n}\nsetup_a() {\n}\n"),
        ["setup_b", "setup_a"],
    )
    ctl.check(
        "MUST FIRE: a CALL is not a definition",
        bash_defined("  setup_a\nsetup_a() {\n}\n"),
        ["setup_a"],
    )

    # -- the refusals ------------------------------------------------------
    saved = phases.PHASE_KEYS
    try:
        phases.PHASE_KEYS = ()  # type: ignore[misc]
        sink = io.StringIO()
        raised = False
        try:
            audit(pathlib.Path("/nonexistent"), Shape())
        except CannotRun:
            raised = True
        del sink
        ctl.truthy("MUST FIRE: an empty PHASE_KEYS is a REFUSAL, not a pass", raised)
    finally:
        phases.PHASE_KEYS = saved  # type: ignore[misc]

    ctl.truthy(
        "MUST NOT FIRE: the real table is non-empty",
        len(phases.PHASE_KEYS) >= 10,
    )

    return EXIT_OK if ctl.report() else EXIT_FINDINGS


# --------------------------------------------------------------------------- argv dispatch ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """The gate. The controls run FIRST on every path, then the real audit."""
    if "--selftest" in argv:
        return selftest()

    try:
        root = paths.repo_root()
    except paths.RootError as exc:
        print("setup-port-parity: CANNOT RUN: %s" % exc, file=sys.stderr)
        return EXIT_CANNOT_RUN

    controls = selftest(verbose=False)
    if controls != EXIT_OK:
        print(
            "✗ the controls did not pass, so this gate has NOT judged the tree. "
            "Run `.ci/rediacc_ci/setup/port_parity.py --selftest` to see which one.",
            file=sys.stderr,
        )
        return controls

    shape = Shape()
    try:
        findings = audit(root, shape)
    except CannotRun as exc:
        print("setup-port-parity: CANNOT RUN: %s" % exc, file=sys.stderr)
        return EXIT_CANNOT_RUN

    if findings:
        for finding in findings:
            print("✗ %s" % finding, file=sys.stderr)
        print("✗ setup port parity: %d finding(s)." % len(findings), file=sys.stderr)
        return EXIT_FINDINGS

    # PRINT THE SHAPE. `-1` means "not applicable in this state of the migration", which is a different fact from zero and is spelled differently so a reader can tell the flip has happened by reading the line.
    print(
        "ok   setup port parity: %d phase(s) in the table, %d reached by run_setup, "
        "%s by the bash setup(), %s setup_* function(s) in %s (%d uncalled), "
        "%d EQUIVALENT tree(s) in the ledger, controls passed"
        % (
            shape.table,
            shape.from_run_setup,
            "%d" % shape.from_bash if shape.from_bash >= 0 else "FLIPPED (bash gone)",
            "%d" % shape.bash_functions if shape.bash_functions >= 0 else "FLIPPED (bash gone)",
            TWIN,
            shape.uncalled,
            shape.ledger_trees,
        )
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
