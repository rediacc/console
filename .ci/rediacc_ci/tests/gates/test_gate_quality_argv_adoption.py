"""Every `.ci/scripts/quality/check_*.py` entry point refuses an argument it does not take, with exit 2.

THE FAILURE THIS GUARDS. `npm run check:ci-record-paths -- --update` exited 0 having done nothing, and 138 sibling entry points read `sys.argv` the same way (and 18 more read none at all). `_gate_args.parse` is adopted in each of them; this file runs EVERY entry point, for real, with `--definitely-not-a-flag` and demands rc 2 naming the argument. It is the control the adoption itself cannot be: a script that lost its `_gate_args.parse` call in a merge, kept a hand-rolled parse, or gained a code path ahead of the parse would exit 0 or 1 here.

THE SET IS EVERY `check_*.py`, MINUS TWO NAMED EXEMPTIONS, not "the scripts that carry the call". A set derived from the call would silently shrink the day someone deleted the call, which is the exact failure to catch. So the target list is the directory, and what stays out is spelled below with its reason:

  * FIXED_ELSEWHERE: check_record_paths.py carries its own `parse_args` from commit 45da438dd0, which this tree's tip does not hold yet.
  * PENDING: entry points whose batch has not landed. The set only shrinks, and a member that already carries the parse is refused.

The entry points that already refused before this change (REFUSES_ITSELF: 7 hand-written, 11 argparse) are in the set and are only RUN, so the claim "every entry point refuses" is one assertion and not two.
"""

import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

QUALITY = paths.repo_root() / ".ci" / "scripts" / "quality"
BOGUS = "--definitely-not-a-flag"
CALL = "_gate_args.parse("

FIXED_ELSEWHERE = {
    "check_record_paths": "parse_args landed in 45da438dd0, which this tip does not hold yet",
}
# Shrink-only: each adoption batch deletes its scripts from this set, and the control below refuses a member that already carries the parse.
PENDING = {
    "check_agent_hint_liveness": "adoption batch not landed yet",
    "check_agent_model_roster": "adoption batch not landed yet",
    "check_ci_gate_prerequisites": "adoption batch not landed yet",
    "check_docker_npm_pins": "adoption batch not landed yet",
    "check_durable_paths_tracked": "adoption batch not landed yet",
    "check_e2e_case_blind_assertions": "adoption batch not landed yet",
    "check_environment_names": "adoption batch not landed yet",
    "check_gate_reachability_coverage": "adoption batch not landed yet",
    "check_hint_corpus": "adoption batch not landed yet",
    "check_plan_record": "adoption batch not landed yet",
    "check_plant_proofs": "adoption batch not landed yet",
    "check_policy_inventory": "adoption batch not landed yet",
    "check_pool_writer_safety": "adoption batch not landed yet",
    "check_portal_sitekey_guard": "adoption batch not landed yet",
    "check_pr_description": "adoption batch not landed yet",
    "check_pr_head_ref_completeness": "adoption batch not landed yet",
    "check_probe_parity": "adoption batch not landed yet",
    "check_profiler_coverage": "adoption batch not landed yet",
    "check_prose_style": "adoption batch not landed yet",
    "check_proxy_cost_guard": "adoption batch not landed yet",
    "check_proxy_deploy_dry_run": "adoption batch not landed yet",
    "check_proxy_image_smoke": "adoption batch not landed yet",
    "check_proxy_wrangler_dev_e2e": "adoption batch not landed yet",
    "check_python_control_plants": "adoption batch not landed yet",
    "check_python_env_registry": "adoption batch not landed yet",
    "check_python_gate_deps": "adoption batch not landed yet",
    "check_python_lint": "adoption batch not landed yet",
    "check_rdc_native": "adoption batch not landed yet",
    "check_regions_sync": "adoption batch not landed yet",
    "check_release_bump_skip": "adoption batch not landed yet",
    "check_release_key_canonical": "adoption batch not landed yet",
    "check_release_signing_coverage": "adoption batch not landed yet",
    "check_release_state": "adoption batch not landed yet",
    "check_renet_tier_map": "adoption batch not landed yet",
    "check_renet_types": "adoption batch not landed yet",
    "check_resolved_threads": "adoption batch not landed yet",
    "check_resprofile": "adoption batch not landed yet",
    "check_retired_terms": "adoption batch not landed yet",
    "check_review_comments": "adoption batch not landed yet",
    "check_review_resolutions": "adoption batch not landed yet",
    "check_rubric_calibration": "adoption batch not landed yet",
    "check_schema_call_sites": "adoption batch not landed yet",
    "check_scope_scripts_reachability": "adoption batch not landed yet",
    "check_script_exec_bit": "adoption batch not landed yet",
    "check_secret_supply": "adoption batch not landed yet",
    "check_setup_idempotency": "adoption batch not landed yet",
    "check_shell_size": "adoption batch not landed yet",
    "check_submodule_branches": "adoption batch not landed yet",
    "check_subscription_schema": "adoption batch not landed yet",
    "check_syncpack_sources": "adoption batch not landed yet",
    "check_test_file_orphans": "adoption batch not landed yet",
    "check_tmpfs_health": "adoption batch not landed yet",
    "check_toolchain_env_dockerfile_sync": "adoption batch not landed yet",
    "check_toolchain_pins": "adoption batch not landed yet",
    "check_tracked_sidecars": "adoption batch not landed yet",
    "check_trap_registry": "adoption batch not landed yet",
    "check_tree_shape": "adoption batch not landed yet",
    "check_turnstile_drift": "adoption batch not landed yet",
    "check_tutorial_cli_validity": "adoption batch not landed yet",
    "check_tutorial_healthcheck_headroom": "adoption batch not landed yet",
    "check_tutorial_no_skips": "adoption batch not landed yet",
    "check_vendored_blocker_derivation": "adoption batch not landed yet",
    "check_workflow_env_provision": "adoption batch not landed yet",
    "check_workflow_submodule_deps": "adoption batch not landed yet",
    "check_workflows": "adoption batch not landed yet",
    "check_worklist_env_registry": "adoption batch not landed yet",
    "check_www_build_token": "adoption batch not landed yet",
}
MIN_SCRIPTS = 174


def everything() -> list[str]:
    return sorted(p.stem for p in QUALITY.glob("check_*.py"))


def targets() -> list[str]:
    return [s for s in everything() if s not in FIXED_ELSEWHERE and s not in PENDING]


def test_the_scan_sees_the_entry_points(gate):
    every = everything()
    gate.log_info(
        "%d entry points, %d run here, %d carry the shared parse, %d pending, %d fixed elsewhere"
        % (
            len(every),
            len(targets()),
            sum(1 for s in every if CALL in (QUALITY / (s + ".py")).read_text()),
            len(PENDING),
            len(FIXED_ELSEWHERE),
        )
    )
    if len(every) < MIN_SCRIPTS:
        gate.log_fail(
            "only %d check_*.py under %s, floor %d: the scan is not seeing the tree"
            % (len(every), QUALITY, MIN_SCRIPTS)
        )
    for stem in list(PENDING) + list(FIXED_ELSEWHERE):
        gate.assert_eq((QUALITY / (stem + ".py")).is_file(), True, "%s exists" % stem)
    gate.assert_eq(sorted(set(PENDING) & set(FIXED_ELSEWHERE)), [], "an exemption is named once")
    for stem in PENDING:
        text = (QUALITY / (stem + ".py")).read_text()
        gate.assert_eq(CALL in text, False, "%s is pending yet already carries the parse" % stem)
    gate.log_pass("%d entry points enumerated, every exemption names a real file" % len(every))


@pytest.mark.parametrize("stem", targets())
def test_an_unknown_flag_exits_2_naming_it(gate, stem):
    script = QUALITY / (stem + ".py")
    result = harness.run([sys.executable, str(script), BOGUS], cwd=paths.repo_root(), timeout=120)
    gate.assert_exit_code(2, result.rc, "%s must refuse %s" % (stem, BOGUS))
    if CALL in script.read_text():
        gate.assert_contains(result.combined, BOGUS, "%s names the argument it refused" % stem)
        gate.assert_contains(
            result.err,
            "%s.py: unknown argument '%s'" % (stem, BOGUS),
            "%s refuses on stderr in the shared format" % stem,
        )
        gate.assert_eq(result.out, "", "%s printed nothing on stdout before refusing" % stem)
    gate.log_pass("%s refuses %s with rc 2" % (stem, BOGUS))


def test_a_declared_flag_is_still_taken(gate):
    """The accepting side: `check_ops_health.py` takes -h, so the refusal is not a blanket one."""
    script = QUALITY / "check_ops_health.py"
    helped = harness.run([sys.executable, str(script), "-h"], cwd=paths.repo_root())
    gate.assert_exit_code(0, helped.rc, "-h is a declared switch and prints the usage")
    stray = harness.run([sys.executable, str(script), "-h", BOGUS], cwd=paths.repo_root())
    gate.assert_exit_code(2, stray.rc, "an unknown flag beside a declared one is still refused")
    gate.log_pass("a declared flag parses and an undeclared neighbour is refused")
