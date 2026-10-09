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

# Longest module name first, and the `python3 -m <module>` usage spelling before the bare name.
_PAIRS = tuple(
    pair
    for stem in _PORTS
    for pair in (
        ("python3 -m rediacc_ci.deploy.%s" % stem, "%s.sh" % stem.replace("_", "-")),
        ("rediacc_ci.deploy.%s" % stem, "%s.sh" % stem.replace("_", "-")),
    )
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
