"""The T8 drivers of `npm run pins` (actions, go-mod, os-ceph-host, ceph-image, real-provider, docker), driven through their fixture selftest.

The drivers decide WHAT a bump may take and what it writes, so each safety refusal is the point: a pin whose registry site no longer matches is refused whole, a Go major is refused whatever `--major` says, a Leap EVR with no obs-mirror tag or of another Ceph series is refused, a release inside the window is its own deferred group, and the UPLOAD_ARTIFACT_PIN constant moves with the `uses:` pins. `selftest.ts --selftest` runs every case over fixture trees and stub answers (no network, no tracked file written) and proves in-process that each mutant turns a case red.

The parametrized case proves it again from outside: with one PINS_T8_MUTANT set, the selftest's own controls must exit 1, so a selftest that stopped honouring a mutant, or whose cases stopped failing, cannot stay green.
"""

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

SUBJECT = paths.from_root("scripts", "lib", "pins", "drivers", "selftest.ts")
MUTANTS = (
    "actions-skip-sites",
    "actions-no-defer",
    "actions-skip-gate-bind",
    "go-allow-major",
    "go-no-mirror",
    "os-ignore-tag",
    "os-ignore-series",
    "ceph-ignore-host",
    "docker-no-drain",
    "docker-keep-digest",
    "docker-skip-redigest",
)


def _selftest(env: dict[str, str] | None = None) -> harness.RunResult:
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(SUBJECT), "--selftest"], cwd=paths.repo_root(), env=env)


def test_selftest_is_green():
    """Every fixture case passes, and each in-process mutant turns at least one of them red."""
    r = _selftest()
    assert r.rc == 0, harness.render_output(r)
    for mutant in MUTANTS:
        assert f"MUTANT {mutant} turns" in r.out, harness.render_output(r)


@pytest.mark.parametrize("mutant", MUTANTS)
def test_each_mutant_is_red(mutant):
    """With one safety property disabled, the selftest exits 1."""
    r = _selftest({"PINS_T8_MUTANT": mutant})
    assert r.rc == 1, harness.render_output(r)


def test_an_unknown_mutant_is_refused():
    """A typo in the mutant name must not read as a green run of the unmutated selftest."""
    r = _selftest({"PINS_T8_MUTANT": "no-such-mutant"})
    assert r.rc == 2, harness.render_output(r)
