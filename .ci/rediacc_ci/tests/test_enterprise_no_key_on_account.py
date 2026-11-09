"""No account Worker holds the licence private key (agent/plans/PLAN-enterprise-isolation.md, S4).

The shared tier signs through its `LICENSE_SIGNER` service binding to the regional signer, and only a signer profile carries the key. Each assertion reads the file that would put the key on an account Worker: the pusher's list, the bench payload, the profiles that feed them, the Wrangler configs and rotation's consumers.
"""

from __future__ import annotations

import json
import pathlib
import tomllib

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import set_account_worker_secrets as pusher
from rediacc_ci.ops import deploy_bench
from rediacc_ci.tests.test_ops_deploy_bench import _bench_env

REPO = pathlib.Path(paths.repo_root())
KEY = "ACCOUNT_ED25519_PRIVATE_KEY"
PUBLIC = "ACCOUNT_ED25519_PUBLIC_KEY"
BINDING = "LICENSE_SIGNER"
ACCOUNT_DIR = REPO / "workers" / "account"
# Account Worker config -> (signer Worker it binds, region its props carry).
CONFIGS = {
    "eu": ("signer-eu", "eu"),
    "us": ("signer-us", "us"),
    "asia": ("signer-asia", "asia"),
    "bench": ("signer-bench-eu", "eu"),
}
SUPPLY = json.loads((REPO / ".ci" / "config" / "secret-supply.json").read_text(encoding="utf-8"))[
    "consumers"
]
ACCOUNT_PROFILES = (
    "account-secrets-eu",
    "account-secrets-us",
    "account-secrets-asia",
    "deploy-bench",
)


def test_the_pusher_lists_neither_push_nor_require_the_key():
    assert KEY not in [worker_key for worker_key, _, _ in pusher.KEYS]
    assert KEY not in [read for _, _, read in pusher.KEYS]
    assert KEY not in pusher.REQUIRED_NONEMPTY
    assert PUBLIC in [worker_key for worker_key, _, _ in pusher.KEYS]


def test_the_pusher_source_never_names_the_key():
    source = (REPO / ".ci" / "rediacc_ci" / "deploy" / "set_account_worker_secrets.py").read_text(
        encoding="utf-8"
    )
    assert KEY not in source


def test_the_bench_payload_omits_the_key_even_when_the_environment_has_it(monkeypatch):
    _bench_env(monkeypatch)
    monkeypatch.setenv(KEY, "leaked-private-value")
    payload = deploy_bench.secrets_payload()
    assert KEY not in payload
    assert "leaked-private-value" not in payload.values()
    assert PUBLIC in payload


def test_the_bench_payload_does_not_require_the_key(monkeypatch):
    _bench_env(monkeypatch)
    monkeypatch.delenv(KEY, raising=False)
    assert PUBLIC in deploy_bench.secrets_payload()


@pytest.mark.parametrize("profile", ACCOUNT_PROFILES)
def test_no_account_profile_binds_the_key(profile):
    consumer = SUPPLY[profile]
    assert KEY not in consumer["required"] + consumer.get("optional", [])


def test_the_signer_profile_carries_the_pair():
    assert {KEY, PUBLIC, "CLOUDFLARE_API_TOKEN"} <= set(SUPPLY["deploy-signer"]["required"])


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_each_account_config_binds_its_signer(name):
    doc = tomllib.loads((ACCOUNT_DIR / f"wrangler.{name}.toml").read_text(encoding="utf-8"))
    bound = [s for s in doc["services"] if s["binding"] == BINDING]
    service, region = CONFIGS[name]
    assert bound == [
        {
            "binding": BINDING,
            "service": service,
            "entrypoint": "LicenseSigner",
            "props": {"tier": "shared", "region": region},
        }
    ]


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_no_account_config_names_the_key(name):
    assert KEY not in (ACCOUNT_DIR / f"wrangler.{name}.toml").read_text(encoding="utf-8")


def test_rotation_has_no_account_worker_consumer_for_the_key():
    """Rotation does not rotate the licence key, and its manifest and consumers never name it for a Worker."""
    roots = [
        REPO / "private" / "account" / "rotation-manifest.json",
        REPO / "private" / "account" / "scripts" / "rotation",
    ]
    files = [roots[0], *sorted(p for p in roots[1].rglob("*.ts"))]
    offenders = [str(p) for p in files if KEY in p.read_text(encoding="utf-8")]
    assert offenders == []
