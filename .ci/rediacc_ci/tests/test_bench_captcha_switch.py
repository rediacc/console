"""Bench alone carries the captcha-off and email-capture switches; no production account worker config may."""

from __future__ import annotations

import json
import tomllib
import typing
from pathlib import Path

from rediacc_ci.ops import deploy_bench

if typing.TYPE_CHECKING:
    import pytest

ROOT = Path(__file__).resolve().parents[3]
CONFIGS = sorted((ROOT / "workers" / "account").glob("wrangler*.toml"))
SWITCHES = ("TURNSTILE_ENABLED", "CI_MODE", "TEST_MODE", "EMAIL_CAPTURE_D1")


def _vars(path: Path) -> dict:
    return tomllib.loads(path.read_text()).get("vars", {})


def _every_vars_table(path: Path) -> dict[str, dict]:
    """`{where: vars}` for the top-level [vars] and every [env.<name>.vars] of a wrangler config. An environment table deploys with `--env <name>`, so a switch set there reaches a worker as surely as a top-level one."""
    doc = tomllib.loads(path.read_text())
    tables = {"vars": doc.get("vars", {})}
    for name, env in (doc.get("env") or {}).items():
        tables[f"env.{name}.vars"] = env.get("vars", {})
    return tables


def test_bench_disables_turnstile():
    assert _vars(ROOT / "workers/account/wrangler.bench.toml")["TURNSTILE_ENABLED"] == "false"
    assert deploy_bench.TURNSTILE_SITEKEY == ""


def test_bench_captures_outgoing_email_and_names_itself_bench():
    bench = _vars(ROOT / "workers/account/wrangler.bench.toml")
    assert bench["EMAIL_CAPTURE_D1"] == "true"
    # The account server admits the switch only when ENVIRONMENT is "bench".
    assert bench["ENVIRONMENT"] == "bench"


def test_no_other_config_carries_a_captcha_or_test_switch():
    others = [p for p in CONFIGS if p.name != "wrangler.bench.toml"]
    assert len(others) >= 6
    for path in others:
        found = [
            "%s:%s" % (where, k)
            for where, table in _every_vars_table(path).items()
            for k in SWITCHES
            if k in table
        ]
        assert not found, "%s sets %s" % (path.name, found)


def test_the_sweep_reads_environment_tables_too(tmp_path: Path) -> None:
    # Control for the sweep above: a switch under [env.<name>.vars] is found, so the sweep is not blind to it.
    config = tmp_path / "wrangler.test.toml"
    config.write_text('[vars]\nA = "1"\n\n[env.prod.vars]\nEMAIL_CAPTURE_D1 = "true"\n')
    tables = _every_vars_table(config)
    assert tables["env.prod.vars"]["EMAIL_CAPTURE_D1"] == "true"
    assert "EMAIL_CAPTURE_D1" not in tables["vars"]


def test_bench_does_not_enable_the_test_surface():
    assert not {"TEST_MODE", "CI_MODE"} & set(_vars(ROOT / "workers/account/wrangler.bench.toml"))


def test_deploy_secrets_never_push_the_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    """The payload `wrangler secret bulk` receives, built with every switch present in the environment, carries none of them."""
    for name in (
        "ACCOUNT_ED25519_PRIVATE_KEY",
        "ACCOUNT_ED25519_PUBLIC_KEY",
        "ACCOUNT_X25519_PRIVATE_KEY",
        "ACCOUNT_X25519_PUBLIC_KEY",
        "ACCOUNT_SERVER_API_KEY",
        "ACCOUNT_JWT_SECRET",
        "ACCOUNT_CONFIG_SERVER_KEY",
        "FREE_LICENSE_HMAC_KEY",
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
    for switch in SWITCHES:
        monkeypatch.setenv(switch, "true")
    payload = deploy_bench.secrets_payload()
    assert not set(SWITCHES) & set(payload)
