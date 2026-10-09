"""The one divergence between a deploy port and its deleted bash twin's frozen golden: the name a diagnostic starts with.

A golden holds the twin's bytes, which begin `cf-purge-urls.sh: ...`; the port begins `rediacc_ci.deploy.cf_purge_urls: ...`, the module name that runs it (`python3 -m`). `as_twin` rewrites the port's name back to the twin's, so a differential still compares every OTHER byte, and each test file pins the port's own prefix against a literal on the side that is not compared.
"""

from __future__ import annotations

_PORTS = (
    "promote_r2_to_stable_hotfix",
    "promote_r2_to_stable",
    "set_account_worker_secrets",
    "set_preview_worker_secrets",
    "set_www_worker_secrets",
    "upload_repos_to_r2",
    "simulate_promotion",
    "test_d1_migrations",
    "deploy_account",
    "deploy_proxy",
    "deploy_www",
    "cf_purge_urls",
    "clone_d1",
)

# Ports outside deploy/: module (after `rediacc_ci.`) -> the twin's script name, where it is not the module's stem hyphenated plus `.sh`.
_ELSEWHERE = {
    "ci.profiler_sampler_linux": "sampler-linux.sh",
    "ci.profiler_panel": "panel.sh",
    "ci.dispatch_watchdog": None,
    "ci.detect_pointer_bump": None,
    "ci.generate_tag": None,
    "ci.record_e2e_probe_outcome": None,
    "ci_signal.create_complete": None,
    "version.inject_env": None,
    "version.resolve_version": None,
    "build.build_linux_packages": None,
    "build.canonicalise_gpg_key": "canonicalise-gpg-key",
    "env.create_e2e_env": None,
    "housekeeping.cleanup_cf_preview": None,
    "housekeeping.cleanup_github_deployments": None,
    "housekeeping.cleanup_pr_environments": None,
    "infra.docker_pull_ghcr": None,
    "infra.verify_ssh": None,
    "infra.wait_for_vm_ssh": None,
    "pr.sync_epic_block": None,
    "proxies.unit_tests": "proxy-unit-tests.sh",
    "testrun.e2e": "run-e2e.sh",
    "testrun.account_e2e": "run-account-e2e.sh",
    "testrun.install_methods": "test-install-methods.sh",
    "testrun.linux_packages": "test-linux-packages.sh",
    "testrun.rdc_update": "test-rdc-update.sh",
    "testrun.seed_smoke": "seed-smoke-test.sh",
    "testrun.start_account": "start-account-for-e2e.sh",
    "deploy.resolve_account_deploy_config": None,
    "deploy.resolve_www_deploy_target": None,
    "deploy.verify_edge_endpoints": None,
    "deploy.wait_for_preview_worker": None,
    "release.advance_contract_floor": None,
    "release.assert_artifact_version": None,
    "release.assert_edge_tag_exists": None,
    "release.backfill_write_sentinel": None,
    "release.check_edge_manifest": None,
    "release.check_existing_release": None,
    "release.check_soak_period": None,
    "release.check_stable_manifest": None,
    "release.cleanup_channel_docker_tags": None,
    "release.create_github_release": None,
    "release.decide_release_mode": None,
    "release.deployment_summary": None,
    "release.list_channel_snapshots": None,
    "release.list_edge_releases": None,
    "release.reprobe_r2_sentinel": None,
    "release.resolve_backfill_commit": None,
    "release.resolve_ci_run": None,
    "release.tag_submodules": None,
    "release.validate_stage_artifacts": None,
    "release.verify_artifact_attestation": None,
    "release.verify_release_assets": None,
}


def _twin_of(module, twin):
    return twin or "%s.sh" % module.rsplit(".", 1)[-1].replace("_", "-")


_MODULES = tuple(("rediacc_ci.deploy.%s" % stem, _twin_of(stem, None)) for stem in _PORTS) + tuple(
    ("rediacc_ci.%s" % mod, _twin_of(mod, twin)) for mod, twin in _ELSEWHERE.items()
)

# A name a port prints for ANOTHER deleted script, rewritten to the name the golden holds.
_REFERENCES = (("npm run check:ci-release-signing-coverage", "check-release-signing-coverage.sh"),)

# Longest module name first (one module name can prefix another), and the `python3 -m <module>` usage spelling before the bare name.
_PAIRS = _REFERENCES + tuple(
    pair
    for module, twin in sorted(_MODULES, key=lambda item: -len(item[0]))
    for pair in (("python3 -m %s" % module, twin), (module, twin))
)


def as_twin(value):
    """`value` with every port module name replaced by its twin's script name; a list or tuple is mapped element-wise, anything else is returned as it came."""
    if isinstance(value, str):
        for port, twin in _PAIRS:
            value = value.replace(port, twin)
        return value
    if isinstance(value, (list, tuple)):
        return type(value)(as_twin(item) for item in value)
    return value
