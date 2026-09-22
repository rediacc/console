r"""Port of `.ci/scripts/test/gates/test-autopilot-no-bypass.sh`, retired in W7 P5.

Unit test for `.ci/scripts/quality/check-autopilot-no-bypass.sh`.

THE SUBJECT STAYS BASH. `rediacc_ci.quality.autopilot_no_bypass` exists and is proven equivalent over a K=5 shadow ledger (`.ci/shadow/w7p2-autopilot-no-bypass.observations.jsonl`), but nothing has cut CI over to it: the bash gate is invoked by no `package.json` key, no `manifest.ts` entry and no workflow `run:` line -- its only registration was ever this test, inside the
"Quality-gate unit tests" battery. Retargeting the SUBJECT is a registration decision outside this port's scope, so this file keeps driving the bash script that CI's battery actually ran, exactly as `test_gate_review_status.py` keeps driving bash `review-status.sh` for the identical reason: changing the harness language is not licence to also change what it tests.

WHY THIS TEST EXISTS AT ALL, and it is not "because every gate should have one". The gate's most important assertion cannot be reached by driving the real API.

Measured: console is public, so

    curl https://api.github.com/repos/rediacc/console/rulesets/12344707

answers 200 with NO `bypass_actors` key. A gate that fetched that would look in a list that does not exist, find no autopilot, and report PASS for ever. That is the single most dangerous shape this gate can have.

But the failure is unreachable through `gh`: pointing `GH_CONFIG_DIR` at an empty directory makes `gh api` refuse the request outright, so the gate exits on "could not list rulesets" and the presence assertion never runs. Verified, not assumed -- that exact control was run and it took the wrong branch.

So the payload is planted through a `gh` shim on PATH. The gate under test is the REAL one, unmodified; only its view of the API is synthetic. No test hook, no override env var, nothing a security gate should not have in production.
"""

import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check-autopilot-no-bypass.sh")

FAKE_GH = r"""#!/bin/bash
# args: api <path>
case "$2" in
    */rulesets) echo '[{"id":99,"target":"branch","enforcement":"active"}]' ;;
    */rulesets/*) cat <<'BODY'
%s
BODY
        ;;
    *) exit 1 ;;
esac
"""


def plant(tmp_path, ruleset_json) -> harness.RunResult:
    """Install a `gh` shim serving `ruleset_json` for both the list and the detail call, then run the gate."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    shim = bindir / "gh"
    shim.write_text(FAKE_GH % ruleset_json, encoding="utf-8")
    shim.chmod(0o755)
    return harness.run(
        [str(GATE)],
        env={
            "PATH": "%s%s%s" % (bindir, os.pathsep, os.environ.get("PATH", "")),
            "GITHUB_AUTOPILOT_APP_ID": "4409539",
        },
    )


def test_blind_read_fails_closed(gate, tmp_path):
    # THE WHOLE POINT. 200, plausible-looking, no bypass_actors key.
    result = plant(tmp_path, '{"id":99,"name":"Branch Protection"}')
    gate.assert_eq(result.rc, 1, "a payload with NO bypass_actors field must FAIL, not pass")
    gate.assert_contains(
        result.combined, "BLIND read", "the failure must say it is blind, not merely 'not found'"
    )
    gate.log_pass("PLANTED missing bypass_actors => FAILURE (the public-repo 200 trap)")


def test_bypass_entry_is_caught(gate, tmp_path):
    result = plant(
        tmp_path,
        '{"id":99,"name":"Branch Protection","bypass_actors":[{"actor_id":4409539,'
        '"actor_type":"Integration","bypass_mode":"always"}]}',
    )
    gate.assert_eq(result.rc, 1, "an autopilot bypass entry must FAIL")
    gate.assert_contains(result.combined, "HAS a bypass", "the failure must name the condition")
    gate.log_pass("PLANTED autopilot bypass => FAILURE")


def test_string_actor_id_still_matches(gate, tmp_path):
    # The API has returned actor_id as a number here; a future string form must not silently stop matching. jq's tostring in the gate is what makes this hold.
    result = plant(
        tmp_path,
        '{"id":99,"name":"Branch Protection","bypass_actors":[{"actor_id":"4409539",'
        '"actor_type":"Integration","bypass_mode":"pull_request"}]}',
    )
    gate.assert_eq(result.rc, 1, "a STRING actor_id must match too, or the gate is type-fragile")
    gate.log_pass("PLANTED string-typed actor_id => FAILURE (no type-coercion hole)")


def test_other_actors_are_not_false_positives(gate, tmp_path):
    # Anti-vacuity in the other direction: the gate must not fail on every ruleset that has any bypass at all, or its red would carry no information.
    result = plant(
        tmp_path,
        '{"id":99,"name":"Branch Protection","bypass_actors":['
        '{"actor_id":5,"actor_type":"RepositoryRole","bypass_mode":"always"},'
        '{"actor_id":2772000,"actor_type":"Integration","bypass_mode":"always"}]}',
    )
    gate.assert_eq(result.rc, 0, "the real bypass actors (Admin + rediacc-ci-cd) must still PASS")
    gate.assert_contains(result.combined, "autopilot absent", "a pass must state what it checked")
    gate.log_pass("the two legitimate bypass actors do not trip it (red carries information)")


def test_empty_bypass_list_passes(gate, tmp_path):
    result = plant(tmp_path, '{"id":99,"name":"Branch Protection","bypass_actors":[]}')
    gate.assert_eq(result.rc, 0, "an empty bypass list is the ideal state and must pass")
    gate.log_pass("an explicitly empty bypass_actors list passes")


def test_unset_app_id_fails_rather_than_defaulting(gate):
    env = dict(os.environ)
    env.pop("GITHUB_AUTOPILOT_APP_ID", None)
    result = harness.run([str(GATE)], env=env, env_replace=True)
    gate.assert_eq(
        result.rc, 1, "an unset GITHUB_AUTOPILOT_APP_ID must fail, not silently check nothing"
    )
    gate.log_pass("missing config fails closed instead of passing against no id")
