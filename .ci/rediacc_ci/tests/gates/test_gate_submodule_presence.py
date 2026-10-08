"""Both arms of the absent-submodule guard, driven through each gate's real npm script (#11bcecca).

THE DEFECT. These gates read files under `private/<submodule>/` and used to print a skip line and exit 0 when the files were absent. Locally that is right; in CI it is a gate that cannot fail, because a workflow checkout that lost `submodules: true` turns each of them into a green tick over nothing. `scripts/lib/submodule-presence.ts` is the shared guard: absent under `CI=true` is exit 1 with the fix named, absent outside CI is a loud skip and exit 0.

THE SEAM. `SUBMODULE_PRESENCE_ROOT` relocates every `private/...` path the guard is asked about, so pointing it at a directory that does not exist makes every submodule absent without touching the real tree. The three gates that already had a test file (`embed-arch-parity`, `embed-credits`, `unverified-downloads`) carry their controls there instead; this file covers the gates that had none.

BOTH DIRECTIONS FOR EACH GATE. The CI arm proves the refusal fires; the local arm proves the same plant is a skip and not a crash, which is also the evidence that the CI arm's red is the guard's and not an unrelated error. The partial-scope gates (`aws-credential-bridge`) keep scanning the present tree after naming what is missing, so their local arm also proves the rest of the real tree is still green.
"""

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

PACKAGE_JSON = paths.from_root("package.json")

# npm script -> the gate file it runs. Read against package.json below, so a renamed script fails here loudly instead of `npm run` exiting 1 with nothing on either stream.
GATES = {
    "check:ci-i18n-completeness": "scripts/gates/check-translation-completeness.ts",
    "check:ci-i18n-placeholders": "scripts/gates/check-i18n-placeholders.ts",
    "check:ci-embed-asset-versions": "scripts/gates/check-embed-asset-versions.ts",
    "check:ci-recovery-context": "scripts/gates/check-recovery-context.ts",
    "check:ci-i18n-account-email-templates": "scripts/gates/check-account-email-templates.ts",
    "check:ci-aws-credential-bridge": "scripts/gates/check-aws-credential-bridge.ts",
}


def run_script(gate, script: str, env: dict[str, str]) -> harness.RunResult:
    text = PACKAGE_JSON.read_text(encoding="utf-8")
    if '"%s":' % script not in text or GATES[script] not in text:
        gate.log_fail(
            "package.json has no %r running %s; the control would drive nothing"
            % (script, GATES[script])
        )
    npm = harness.require_tool("npm", "install node; the subjects are npm scripts running tsx")
    return harness.run(
        [npm, "run", "--silent", script], cwd=paths.repo_root(), env=env, timeout=900
    )


@pytest.mark.parametrize("script", sorted(GATES))
def test_absent_submodule_fails_under_ci(gate, tmp_path, script):
    result = run_script(
        gate,
        script,
        {"SUBMODULE_PRESENCE_ROOT": str(tmp_path / "absent"), "CI": "true", "GITHUB_ACTIONS": ""},
    )
    gate.assert_exit(1, result, "%s: an absent submodule under CI=true is a refusal" % script)
    gate.assert_contains(
        result.combined,
        "required in CI but missing",
        "%s: the refusal names what is missing" % script,
    )
    gate.log_pass("%s refuses an absent submodule under CI" % script)


@pytest.mark.parametrize("script", sorted(GATES))
def test_absent_submodule_skips_outside_ci(gate, tmp_path, script):
    result = run_script(
        gate,
        script,
        {"SUBMODULE_PRESENCE_ROOT": str(tmp_path / "absent"), "CI": "", "GITHUB_ACTIONS": ""},
    )
    gate.assert_exit(0, result, "%s: an absent submodule outside CI is a skip" % script)
    gate.assert_contains(
        result.combined,
        "under CI this is a hard failure",
        "%s: the skip says it would fail in CI" % script,
    )
    gate.log_pass("%s skips an absent submodule loudly outside CI" % script)
