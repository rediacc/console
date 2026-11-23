#!/usr/bin/env python3
"""Does `machine.run_setup` still reach every phase `phases.PHASES` declares, in that order?

WHAT IS LEFT OF THE PORT CHECK, AND WHY. This gate was written across the bash-to-Python cutover with five clauses. Four of them compared against the bash `setup()` and the shadow ledger the ledger (deleted in commit:936280cd35) (deleted by agent/plans/PLAN-tooling-code-reduction.md CR1; last present at commit:aa829a19dc), and both have been gone since the flip, so those clauses could only ever skip. What stays is the clause that catches the drift that actually happens:

  A1  `phases.PHASE_KEYS` and the order of the same keys inside
      `machine.run_setup`'s SOURCE agree, in both directions and in order.
      Both live in Python and neither is going anywhere. `run_setup` is a
      straight line and a straight line is edited by hand.

ANTI-VACUITY. Two refusals, each returning 77 rather than a verdict:

  * `PHASE_KEYS` is empty, so every set comparison is between two empty sets;
  * `machine.run_setup`'s source could not be read, so A1 compares nothing.

And the success line prints both counts, so a collapse of either is visible.

---- gate ----
id: check:ci-setup-port-parity
step: Setup port parity
needs: none
selftest: true
why: run_setup is a straight line edited by hand, so the order of the phases it reaches has to be re-derived against the declared table on every run
---- end gate ----
"""

from __future__ import annotations

import io
import pathlib
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci import paths
from rediacc_ci.controls import Controls
from rediacc_ci.setup import phases

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CANNOT_RUN = 77

# Phase key -> the `host.py` function that runs it, which is how A1 recognises a ported phase's call in `run_setup`.
PORTED_AS = {
    "setup_node_toolchain": "node_toolchain",
    "setup_system_tools": "system_tools",
    "setup_go_toolchain": "go_toolchain",
    "setup_gh_cli": "gh_cli",
    "setup_docker_probe": "docker_probe",
    "setup_git_identity": "git_identity",
    "setup_git_credentials": "git_credentials",
}


class CannotRunError(Exception):
    """The gate cannot see its subject, so its green would mean nothing."""


@dataclass
class Shape:
    """The numbers printed on a clean run, so a reader can watch one collapse."""

    table: int = 0
    from_run_setup: int = 0


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
    # The three inline phases. `init-submodules.sh` appears as a path fragment in `ctx.run`; the drift check and the account bootstrap are reached through a helper whose name is the phase's own subject, so each is matched by that helper's call.
    if key in ("init-submodules.sh", "check:env-credential-drift"):
        return ('"%s"' % key in line) or ("_credential_drift(" in line and key.startswith("check:"))
    if key == "account-bws-bootstrap":
        return "_account_bws_bootstrap(" in line
    if key == "rdc-tools-install":
        return "_install_tofu(" in line
    if key == "git-hooks-path":
        return "githooks.install(" in line
    return False


# --------------------------------------------------------------------------- the audit ---------------------------------------------------------------------------


def audit(root: pathlib.Path, shape: Shape) -> list[str]:
    """Every finding, as text. Raises CannotRunError when the subject is not visible."""
    findings: list[str] = []
    keys = phases.PHASE_KEYS
    shape.table = len(keys)
    if not keys:
        raise CannotRunError(
            "phases.PHASE_KEYS is EMPTY, so every set comparison below is between "
            "two empty sets and would pass"
        )

    machine_src = _read(root / ".ci" / "rediacc_ci" / "setup" / "machine.py")
    if not machine_src:
        raise CannotRunError("cannot read .ci/rediacc_ci/setup/machine.py, so A1 compares nothing")

    # -- A1 ---------------------------------------------------------------
    order = run_setup_order(machine_src, keys)
    shape.from_run_setup = len(order)
    findings += _compare("A1 run_setup", list(keys), order)

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
    """Both directions on every clause. 13 controls, floor 13."""
    ctl = Controls("setup-port-parity", floor=13, verbose=verbose)

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

    # -- the refusals ------------------------------------------------------
    saved = phases.PHASE_KEYS
    try:
        phases.PHASE_KEYS = ()
        sink = io.StringIO()
        raised = False
        try:
            audit(pathlib.Path("/nonexistent"), Shape())
        except CannotRunError:
            raised = True
        del sink
        ctl.truthy("MUST FIRE: an empty PHASE_KEYS is a REFUSAL, not a pass", raised)
    finally:
        phases.PHASE_KEYS = saved

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
    except CannotRunError as exc:
        print("setup-port-parity: CANNOT RUN: %s" % exc, file=sys.stderr)
        return EXIT_CANNOT_RUN

    if findings:
        for finding in findings:
            print("✗ %s" % finding, file=sys.stderr)
        print("✗ setup port parity: %d finding(s)." % len(findings), file=sys.stderr)
        return EXIT_FINDINGS

    # PRINT THE SHAPE, so a reader sees a collapse of either count.
    print(
        "ok   setup port parity: %d phase(s) in the table, %d reached by run_setup, "
        "controls passed" % (shape.table, shape.from_run_setup)
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
