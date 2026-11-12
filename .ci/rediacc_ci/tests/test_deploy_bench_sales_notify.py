"""The bench secret document carries SALES_NOTIFY_EMAIL, the optional sales digest recipient the deploy-bench profile binds: a profile entry with no key in the pushed document (or the reverse) fails here."""

import json

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import deploy_bench


def _profile_names() -> set[str]:
    supply = json.loads(
        paths.repo_root().joinpath(".ci/config/secret-supply.json").read_text("utf-8")
    )
    profile = supply["consumers"]["deploy-bench"]
    return set(profile["required"]) | set(profile["optional"])


def _seed(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "ACCOUNT_ED25519_PRIVATE_KEY",
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_X25519_PRIVATE_KEY",
        "ACCOUNT_X25519_PUBLIC_KEY",
        "ACCOUNT_SERVER_API_KEY",
        "ACCOUNT_JWT_SECRET",
        "FREE_LICENSE_HMAC_KEY",
        "ACCOUNT_AE_READ_TOKEN",
        "ACCOUNT_CONFIG_SERVER_KEY",
        "ACCOUNT_BACKUP_STORE_KEK",
    ):
        monkeypatch.setenv(name, "v-" + name)
    monkeypatch.setenv("ROOT_EMAIL", "root@example.invalid")
    monkeypatch.setenv("AWS_SES_ACCESS_KEY_ID", "id")
    monkeypatch.setenv("AWS_SES_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setenv("CLOUDFLARE_TURNSTILE_SECRET_KEY", "turn")
    monkeypatch.setenv("ACCOUNT_BACKUP_S3_ENDPOINT", "https://r2.invalid")
    monkeypatch.setenv("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID", "bench-id")
    monkeypatch.setenv("ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY", "bench-secret")
    monkeypatch.setenv("OBS_OTLP_CREDENTIALS", json.dumps({"user": "u", "pass": "p"}))
    monkeypatch.delenv("ACCOUNT_BACKUP_S3_BUCKET", raising=False)
    monkeypatch.setenv("STRIPE_SANDBOX_SECRET_KEY", "")
    monkeypatch.setenv("STRIPE_SANDBOX_WEBHOOK_SECRET", "")


def test_the_profile_binds_sales_notify_email_and_the_document_carries_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(monkeypatch)
    monkeypatch.setenv("SALES_NOTIFY_EMAIL", "sales@example.invalid")
    assert "SALES_NOTIFY_EMAIL" in _profile_names()
    assert deploy_bench.secrets_payload()["SALES_NOTIFY_EMAIL"] == "sales@example.invalid"


def test_an_unset_sales_notify_email_is_pushed_empty_which_the_worker_reads_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed(monkeypatch)
    monkeypatch.delenv("SALES_NOTIFY_EMAIL", raising=False)
    assert deploy_bench.secrets_payload()["SALES_NOTIFY_EMAIL"] == ""
