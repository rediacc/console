"""The `npm run pins` core (scripts/pins/pins.ts), driven through its fixture selftest.

The pins command writes pinned versions across the console and its submodules, so its safety properties are the whole of its value: a pin whose sites do not all match is refused whole, a site file holding another session's changes is refused by name, every write is journaled, and a failed run restores only the files that still hold the bytes it wrote. `--selftest` builds a throwaway fixture tree per case under PINS_ROOT and PINS_FIXTURE, with the releases, the clock and a stub runner for every command, so nothing here touches the network or the tracked tree.

THE MUTANTS ARE THE POINT. Each PINS_MUTANT disables one safety property (skip-site, ignore-soak, no-canonical, partial-write, no-dirty-check, no-restore, blind-restore, first-eligible, no-resync, all-gates). The selftest proves each one turns its own case red in-process: `selftestCases` runs the target case once per mutant and fails the whole selftest on a mutant that left it green, and `test_selftest_is_green` reads one `MUTANT <m> turns the` line per mutant, so a case that stopped failing cannot stay green.

ONE MUTANT FROM OUTSIDE, NOT TEN (PLAN-ciquick-cpu.md W16). This file used to rerun the whole selftest once per mutant through PINS_MUTANT and read the exit code. Each of those reruns built the same cases the in-process loop had already built with the same mutant, through the same `CASES[target](mutant)` call; the only claim they added was that the selftest honours the PINS_MUTANT variable at all. One rerun proves that, and a second proves a name outside the list is refused rather than read as no mutant.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

SUBJECT = paths.from_root("scripts", "pins", "pins.ts")
MUTANTS = (
    "skip-site",
    "ignore-soak",
    "no-canonical",
    "partial-write",
    "no-dirty-check",
    "no-restore",
    "blind-restore",
    "first-eligible",
    "no-resync",
    "all-gates",
)


def _selftest(env: dict[str, str] | None = None) -> harness.RunResult:
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(SUBJECT), "--selftest"], cwd=paths.repo_root(), env=env)


def test_selftest_is_green():
    """Every fixture case passes, and the in-process mutant controls each turn their case red."""
    r = _selftest()
    assert r.rc == 0, harness.render_output(r)
    for mutant in MUTANTS:
        assert f"MUTANT {mutant} turns the" in r.out, harness.render_output(r)


def test_the_selftest_honours_pins_mutant_from_outside():
    """With one safety property disabled through the environment, the selftest exits 1 and names the failing case; every other mutant's red is proved by the in-process loop `test_selftest_is_green` reads."""
    r = _selftest({"PINS_MUTANT": "no-restore"})
    assert r.rc == 1, harness.render_output(r)
    assert "FAIL" in r.out + r.err, harness.render_output(r)


def test_an_unknown_mutant_is_refused_not_ignored():
    """CONTROL for the case above: a name outside the list exits 2, so an env var the selftest stopped reading cannot pass as a mutant that went red."""
    r = _selftest({"PINS_MUTANT": "no-such-mutant"})
    assert r.rc == 2, harness.render_output(r)
    assert "is not one of" in r.err, harness.render_output(r)
