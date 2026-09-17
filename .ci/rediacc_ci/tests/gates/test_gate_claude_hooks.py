"""Port of `.ci/scripts/test/gates/test-claude-hooks.sh`.

CI wrapper for the Claude hook harness at `.claude/hooks/test-hooks.sh`.

WHY THE WRAPPER EXISTS AT ALL. The pre-bash hooks carry live PR policy: draft-only creation, green-gated `gh pr ready`, the `--admin` merge ban, merge-time review hygiene. The harness (quote-strip evasion, command-position anchoring, prose false-positive controls) previously ran only when someone remembered to run it, so a hook regression could never turn CI red. Discovery by the
battery is what put it inside `npm run ci`.

THIS MODULE NO LONGER RUNS THE HARNESS, and that is the point of it now.

The wrapper's own translation logic -- `FAIL=0`, a nonzero case count, and a summary
line that is PRESENT and parseable -- still matters, and it still runs: it lives in `.ci/scripts/test/gates/test-claude-hooks.sh`, registered as `gate-test:claude-hooks`. This module used to reimplement all three assertions and re-execute the harness to check them, which bought no coverage and cost 931s.

WHY THAT WAS INTOLERABLE RATHER THAN MERELY WASTEFUL. The harness was executed THREE times per CI cycle inside ONE job: by the registered gate, by this module, and by `test_hooks_delegates.py` re-running the two sub-suites the harness already runs. `quality-security` caps at `timeout-minutes: 20` (1200s) and carries both `Python
package tests` and `Quality-gate unit tests`, so ~2784s of identical work could never
fit. That lane had never once reported across four CI runs, which is exactly why the overrun stayed invisible: a job that cannot finish hides everything inside it.

WHAT IS KEPT. Delegation is a claim that can rot silently -- a delegate renamed, de-gated, or quietly no longer invoking the harness looks IDENTICAL to a harness that ran and passed. So the chain is asserted link by link, with two controls that plant each break against a doctored copy in `tmp_path`.

A FLAT TWIN. It declares no `test_*()` functions, so `test_twin_parity.py` compares against its runtime `PASS:` count (one line) rather than a case set.

TWIN_TIMEOUT IS STILL DECLARED, and still load-bearing, but for the PARITY DRIVER rather than for anything here. `test_twin_parity` drives this flat twin to count its runtime `PASS:` lines, so it is the thing that now pays the harness's wall time. The 600s default is not enough -- `subprocess.run` RAISES on timeout and the driver emitted a `TimeoutExpired` traceback instead of a
verdict, which reads as a broken harness rather than a slow subject.

The number, re-measured 2026-09-14 rather than inherited: the harness takes 931.14s
standalone and uncontended (PASS=2269, rc=0), and it is SERIAL -- 478 sub-suites one
after another, no worker pool -- so more cores cannot help it and CI's slower per-core `ubuntu-latest` makes it worse. 1000s therefore leaves 6.9% headroom, which is thin. If this ever needs more than the 1800s cap the answer is to SHARD the harness, not to raise it; that is tracked as O-3 in docs/ci-overhaul/07-tooling-decisions.md with the measurements attached.
"""

import pathlib

from rediacc_ci import paths

BASH_TWIN = ".ci/scripts/test/gates/test-claude-hooks.sh"

# See the module docstring. Measured at ~811s; the driver caps declarations at 1800.
TWIN_TIMEOUT = 1000

HARNESS = paths.from_root(".claude", "hooks", "test-hooks.sh")
WRAPPER = paths.from_root(".ci", "scripts", "test", "gates", "test-claude-hooks.sh")
MANIFEST = paths.from_root("scripts", "ci-runner", "manifest.ts")

# The registered gate that ACTUALLY executes the harness. This module deliberately does not, so this id is the whole reason the omission is safe.
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

    RETURNS THE REASON RATHER THAN RAISING so the control can observe a verdict, exactly as `test_gate_worklist_hooks.delegation_problem` does. A caught exception cannot be distinguished from a bug in the control itself.
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
            "wrapper exists but nothing schedules it and the harness is unreachable." % DELEGATE_ID
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
    CI cycle inside ONE job: by `gate-test:claude-hooks` (the registered gate), by this module, and by `test_hooks_delegates.py` re-running the two sub-suites the harness already runs itself. `quality-security` caps at `timeout-minutes: 20` (1200s), so ~2784s of identical work could never fit and that lane had never once reported in four CI runs -- which is precisely why the
    overrun stayed invisible.

    Re-executing a harness that a registered gate already executes buys no coverage. What it DOES buy, and what is kept here, is proof that the delegation is real: a delegate that is renamed, de-gated, or quietly stopped pointing at the harness looks EXACTLY like a harness that ran and passed. So the chain is asserted link by link, and none of it runs anything.
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

    The failure guarded against -- a harness that runs nowhere -- looks identical to a harness that ran and passed, so the SAME predicate is driven against a manifest whose delegate entry has been stripped of `gate: true`. A pass there is itself a failure. The doctored copy goes to `tmp_path`; the real manifest is never written, which is the seam T-12 exists to require.
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


def test_the_delegation_assertion_fires_when_the_wrapper_stops_invoking_the_harness(gate, tmp_path):
    """CONTROL, the other link. The delegate can stay registered and stop delegating.

    A wrapper that is still `gate: true` but no longer invokes `test-hooks.sh` is the quiet version of this failure: CI stays green, the harness runs nowhere, and no name changed. Driven against a doctored copy of the wrapper.
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
    gate.assert_contains(problem, "no longer invokes", "CONTROL FAILED: fired for the wrong reason")
    gate.log_pass("a wrapper that stopped invoking the harness is caught")
