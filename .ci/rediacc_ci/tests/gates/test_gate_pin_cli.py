"""The `npm run pins` core (scripts/pins/pins.ts), driven through its fixture selftest.

The pins command writes pinned versions across the console and its submodules, so its safety properties are the whole of its value: a pin whose sites do not all match is refused whole, a site file holding another session's changes is refused by name, every write is journaled, and a failed run restores only the files that still hold the bytes it wrote. `--selftest` builds a throwaway fixture tree per case under PINS_ROOT and PINS_FIXTURE, with the releases, the clock and a stub runner for every command, so nothing here touches the network or the tracked tree.

THE MUTANTS ARE THE POINT. Each PINS_MUTANT disables one safety property (skip-site, ignore-soak, no-canonical, partial-write, no-dirty-check, no-restore, blind-restore, first-eligible, no-resync, all-gates). The selftest already proves each one turns its own case red in-process; the parametrized case below proves it again from outside, through the process exit code, so a selftest that stopped honouring PINS_MUTANT, or one whose cases stopped failing, cannot stay green.
"""

import pytest

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


@pytest.mark.parametrize("mutant", MUTANTS)
def test_each_mutant_is_red(mutant):
    """With one safety property disabled, the selftest exits 1."""
    r = _selftest({"PINS_MUTANT": mutant})
    assert r.rc == 1, harness.render_output(r)
