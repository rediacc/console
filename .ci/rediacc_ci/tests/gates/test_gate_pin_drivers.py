"""The embed, devcontainer and toolchain pin drivers, driven through their selftests.

Each selftest builds a throwaway console from copies of the live pin files, answers every upstream request from a URL map, and plans a bump with the real driver. Nothing reaches the network or the tracked tree. What the controls prove: an embed bump moves the Dockerfile, the lockfile, the Go constants, the unit goldens and the credits inventories in one transaction with check:ci-embed-credits green; the vendored CRD claim moves only with a re-vendor or a byte-identity proof and is refused with neither; a hashed pin moves only with every hash; a Go bump leaves check:ci-toolchain-env-dockerfile-sync green; an npm bump canonicalises every lockfile under the new pinned npm.

THE MUTANTS ARE THE POINT. Each driver names the refusals it relies on (blind-commit, skip-crd, claim-without-proof, lone-sibling, half-hash, ambient-npm). The selftest proves in-process that each turns a control red; the parametrized case below proves it again through the exit code, so a selftest that stopped honouring a mutant, or whose controls stopped failing, cannot stay green.
"""

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

DRIVERS = {
    "embed": ("blind-commit", "skip-crd", "claim-without-proof", "lone-sibling"),
    "devcontainer": ("half-hash",),
    "toolchain": ("half-hash", "ambient-npm"),
}


def _run(driver: str, *args: str) -> harness.RunResult:
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    subject = paths.from_root("scripts", "lib", "pins", "drivers", f"{driver}-selftest.ts")
    return harness.run([npx, "tsx", str(subject), *args], cwd=paths.repo_root())


@pytest.mark.parametrize("driver", sorted(DRIVERS))
def test_selftest_is_green(driver):
    """Every control passes, and each mutant turns a control red in-process."""
    r = _run(driver)
    assert r.rc == 0, harness.render_output(r)
    for mutant in DRIVERS[driver]:
        assert f"MUTANT {mutant}: red as it must be" in r.out, harness.render_output(r)


@pytest.mark.parametrize(
    ("driver", "mutant"), [(d, m) for d, ms in sorted(DRIVERS.items()) for m in ms]
)
def test_each_mutant_is_red(driver, mutant):
    """With one refusal disabled, the selftest exits 1."""
    r = _run(driver, "--mutant", mutant)
    assert r.rc == 1, harness.render_output(r)
