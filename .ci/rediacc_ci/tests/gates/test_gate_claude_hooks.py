"""Port of `.ci/scripts/test/gates/test-claude-hooks.sh`.

CI wrapper for the Claude hook harness at `.claude/hooks/test-hooks.sh`.

WHY THE WRAPPER EXISTS AT ALL. The pre-bash hooks carry live PR policy: draft-only
creation, green-gated `gh pr ready`, the `--admin` merge ban, merge-time review
hygiene. The harness (quote-strip evasion, command-position anchoring, prose
false-positive controls) previously ran only when someone remembered to run it, so a
hook regression could never turn CI red. Discovery by the battery is what put it
inside `npm run ci`.

THE TRANSLATION IS THE GATE, and it is the reason this is not just `bash test-hooks.sh`.
The harness speaks `ok [..]` plus a final `PASS=<n> FAIL=<m>` counter, not the
`PASS:` lines the battery counts, so trusting its exit code alone would let a harness
that silently ran ZERO cases report green. The wrapper requires `FAIL=0` AND a nonzero
case count, and the port keeps both halves plus a third the wrapper had implicitly:
the summary line must be PRESENT and parseable, because a harness whose output shape
changed is unchecked rather than fine.

A FLAT TWIN. It declares no `test_*()` functions, so `test_twin_parity.py` compares
against its runtime `PASS:` count (one line) rather than a case set. The port records
four controls against that floor, each naming a different property of the same run.

TWIN_TIMEOUT, AND WHY IT IS DECLARED HERE FIRST. This subject was UNPORTABLE by
construction until the parity driver gained a declarable timeout: 2 229 offline cases
at roughly 13m31s blow straight through the 600s default, `subprocess.run` RAISES on
timeout, and the driver produced a `TimeoutExpired` traceback instead of a verdict --
which reads as a broken harness rather than as a slow subject, and had this subject
one report away from being recorded as a permanent standing drop. 1000s leaves
headroom over the measured wall time without approaching the 1800s cap. If this ever
needs more than the cap, the answer is to SPLIT the harness, not to raise it.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-claude-hooks.sh"

# See the module docstring. Measured at ~811s; the driver caps declarations at 1800.
TWIN_TIMEOUT = 1000

HARNESS = paths.from_root(".claude", "hooks", "test-hooks.sh")
WRAPPER = paths.from_root(".ci", "scripts", "test", "gates", "test-claude-hooks.sh")
MANIFEST = paths.from_root("scripts", "ci-runner", "manifest.ts")

# The registered gate that ACTUALLY executes the harness. This module deliberately
# does not, so this id is the whole reason the omission is safe.
DELEGATE_ID = "gate-test:claude-hooks"
HARNESS_REL = ".claude/hooks/test-hooks.sh"
WRAPPER_REL = ".ci/scripts/test/gates/test-claude-hooks.sh"

# The entry terminator the binder itself relies on (scripts/gate-bind.ts).
ENTRY_END = "  },"


def manifest_entry(source: str, key: str) -> str:
    """The manifest block for `key`, from its `id:` line through its closing `  },`."""
    needle = "id: '%s'," % key
    collected: list[str] = []
    started = False
    for line in source.splitlines():
        if not started and needle in line:
            started = True
        if not started:
            continue
        collected.append(line)
        if line == ENTRY_END:
            break
    return "\n".join(collected)


def delegation_problem(manifest: pathlib.Path, wrapper: pathlib.Path) -> str | None:
    """None when the whole chain holds, else the ONE link that broke.

    RETURNS THE REASON RATHER THAN RAISING so the control can observe a verdict,
    exactly as `test_gate_worklist_hooks.delegation_problem` does. A caught
    exception cannot be distinguished from a bug in the control itself.
    """
    if not HARNESS.is_file():
        return "FAIL: %s does not exist, so nothing runs it anywhere." % HARNESS_REL
    if not wrapper.is_file():
        return (
            "FAIL: %s does not exist, so the harness runs NOWHERE -- this module "
            "stopped running it on the strength of that wrapper." % WRAPPER_REL
        )

    body = wrapper.read_text(encoding="utf-8")
    if HARNESS_REL not in body:
        return (
            "FAIL: %s no longer invokes %s, so the delegate is registered but runs "
            "something else." % (WRAPPER_REL, HARNESS_REL)
        )

    entry = manifest_entry(manifest.read_text(encoding="utf-8"), DELEGATE_ID)
    if not entry:
        return (
            "FAIL: scripts/ci-runner/manifest.ts has no entry with id '%s', so the "
            "wrapper exists but nothing schedules it and the harness is unreachable."
            % DELEGATE_ID
        )
    if "gate: true" not in entry:
        return (
            "FAIL: manifest entry '%s' is not gate: true, so a full run never selects "
            "it and the harness silently stops being checked." % DELEGATE_ID
        )
    if WRAPPER_REL not in entry:
        return (
            "FAIL: manifest entry '%s' no longer names %s, so the parity oracle can no "
            "longer see that this harness is covered." % (DELEGATE_ID, WRAPPER_REL)
        )
    return None


def test_the_harness_is_delegated_to_its_registered_gate(gate):
    """The harness is NOT run here. This proves the thing that does run it still will.

    WHY THIS STOPPED EXECUTING THE HARNESS. `.claude/hooks/test-hooks.sh` measures
    931.14s standalone (PASS=2269, uncontended). It was being executed THREE times per
    CI cycle inside ONE job: by `gate-test:claude-hooks` (the registered gate), by this
    module, and by `test_hooks_delegates.py` re-running the two sub-suites the harness
    already runs itself. `quality-security` caps at `timeout-minutes: 20` (1200s), so
    ~2784s of identical work could never fit and that lane had never once reported in
    four CI runs -- which is precisely why the overrun stayed invisible.

    Re-executing a harness that a registered gate already executes buys no coverage.
    What it DOES buy, and what is kept here, is proof that the delegation is real: a
    delegate that is renamed, de-gated, or quietly stopped pointing at the harness
    looks EXACTLY like a harness that ran and passed. So the chain is asserted link by
    link, and none of it runs anything.
    """
    gate.log_test("the harness is reachable through its registered delegate")
    problem = delegation_problem(MANIFEST, WRAPPER)
    if problem is not None:
        gate.log_fail(problem)
    gate.log_pass(
        "%s exists, %s invokes it, and manifest id '%s' is gate: true and names the "
        "wrapper" % (HARNESS_REL, WRAPPER_REL, DELEGATE_ID)
    )


def test_the_delegation_assertion_fires_when_the_delegate_is_de_gated(gate, tmp_path):
    """CONTROL. An assertion that cannot fail is worth what no assertion is worth.

    The failure guarded against -- a harness that runs nowhere -- looks identical to a
    harness that ran and passed, so the SAME predicate is driven against a manifest
    whose delegate entry has been stripped of `gate: true`. A pass there is itself a
    failure. The doctored copy goes to `tmp_path`; the real manifest is never written,
    which is the seam T-12 exists to require.
    """
    gate.log_test("CONTROL: de-gating the delegate must be caught")
    original = MANIFEST.read_text(encoding="utf-8")
    entry = manifest_entry(original, DELEGATE_ID)
    if not entry or "gate: true" not in entry:
        gate.log_fail(
            "the control could not find a gate: true line in the '%s' manifest entry, "
            "so it would pass for the wrong reason" % DELEGATE_ID
        )
    doctored = tmp_path / "manifest.ts"
    doctored.write_text(
        original.replace(entry, entry.replace("gate: true", "gate: false"), 1),
        encoding="utf-8",
    )

    problem = delegation_problem(doctored, WRAPPER)
    if problem is None:
        gate.log_fail(
            "CONTROL FAILED: the delegation assertion PASSED against a manifest with "
            "'%s' de-gated, so it cannot detect the disappearance it exists to detect. "
            "Nothing this module reports about delegation is meaningful." % DELEGATE_ID
        )
    gate.assert_contains(
        problem,
        "not gate: true",
        "CONTROL FAILED: the assertion fired, but not for the reason planted",
    )
    gate.log_pass("a de-gated delegate is caught")


def test_the_delegation_assertion_fires_when_the_wrapper_stops_invoking_the_harness(
    gate, tmp_path
):
    """CONTROL, the other link. The delegate can stay registered and stop delegating.

    A wrapper that is still `gate: true` but no longer invokes `test-hooks.sh` is the
    quiet version of this failure: CI stays green, the harness runs nowhere, and no
    name changed. Driven against a doctored copy of the wrapper.
    """
    gate.log_test("CONTROL: a wrapper that no longer runs the harness must be caught")
    body = WRAPPER.read_text(encoding="utf-8")
    if HARNESS_REL not in body:
        gate.log_fail(
            "the control could not strip %s from the wrapper because it does not "
            "appear, so it would pass for the wrong reason" % HARNESS_REL
        )
    doctored = tmp_path / "test-claude-hooks.sh"
    doctored.write_text(body.replace(HARNESS_REL, ".claude/hooks/SOME-OTHER.sh"), encoding="utf-8")

    problem = delegation_problem(MANIFEST, doctored)
    if problem is None:
        gate.log_fail(
            "CONTROL FAILED: the assertion PASSED against a wrapper that no longer "
            "invokes the harness, so the delegation claim is unfalsifiable."
        )
    gate.assert_contains(
        problem, "no longer invokes", "CONTROL FAILED: fired for the wrong reason"
    )
    gate.log_pass("a wrapper that stopped invoking the harness is caught")
