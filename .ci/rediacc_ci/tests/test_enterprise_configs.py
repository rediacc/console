"""enterprise.configs: the company's account and proxy tomls, generated from the two templates and held to `config_refusals` (agent/plans/PLAN-enterprise-isolation.md box N4).

CONTROL FIRST. The unplanted generation must carry no refusal, so a refusal on a plant is the plant's doing; each plant changes ONE thing and must be refused by name. The shared output must stay byte-identical to the committed files, since the route and extra-var placeholders resolve to the old text there.
"""

from __future__ import annotations

import tomllib

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import proxy_configs as pc
from rediacc_ci.enterprise import configs
from rediacc_ci.well_known import PRODUCT_DOMAIN

ROOT = paths.repo_root()
D1_ID = "11111111-2222-3333-4444-555555555555"


def _gen(company="acme", region="eu", **kw):
    return configs.generate(company, region, D1_ID, root=ROOT, **kw)


def test_shared_output_is_byte_identical_to_the_committed_configs():
    for name, text in pc.generate(ROOT).items():
        assert text == (ROOT / "workers" / "proxy" / name).read_text(encoding="utf-8")


def test_company_proxy_has_no_refusal_and_names_its_own_things():
    out = _gen()
    assert configs.proxy_refusals("acme", "eu", out.proxy, root=ROOT) == []
    cfg = tomllib.loads(out.proxy)
    assert cfg["name"] == "proxy-acme"
    assert cfg["routes"] == [
        {"pattern": "acme-proxy.%s/*" % PRODUCT_DOMAIN, "zone_name": PRODUCT_DOMAIN}
    ]
    assert cfg["vars"]["ACCOUNT_URL"] == "https://acme.%s" % PRODUCT_DOMAIN
    assert cfg["vars"]["REGION"] == "eu"
    assert {s["service"] for s in cfg["services"]} == {"account-acme"}
    assert "ALLOW_IPS" not in cfg["vars"]
    assert "@@" not in out.proxy


def test_company_account_has_no_refusal_and_names_its_own_things():
    out = _gen()
    assert configs.account_refusals("acme", "eu", out.account, root=ROOT) == []
    cfg = tomllib.loads(out.account)
    assert cfg["name"] == "account-acme"
    assert cfg["routes"] == [{"pattern": "acme.%s/*" % PRODUCT_DOMAIN, "zone_name": PRODUCT_DOMAIN}]
    assert cfg["d1_databases"][0]["database_name"] == "account-acme"
    assert cfg["d1_databases"][0]["database_id"] == D1_ID
    assert [b["bucket_name"] for b in cfg["r2_buckets"]] == ["configs-acme", "backups-acme"]
    assert cfg["r2_buckets"][0]["jurisdiction"] == "eu"
    assert cfg["services"] == [{"binding": "EXECUTOR", "service": "proxy-acme"}]
    assert cfg["vars"]["WEBAUTHN_RP_ID"] == "acme.%s" % PRODUCT_DOMAIN
    assert "@@" not in out.account


def test_a_region_without_jurisdiction_writes_none():
    cfg = tomllib.loads(_gen(region="us").account)
    assert all("jurisdiction" not in b for b in cfg["r2_buckets"])


def test_allow_ips_is_the_opt_in_var_on_both_workers():
    out = _gen(allow_ips=("203.0.113.0/24", "198.51.100.7"))
    for text in (out.proxy, out.account):
        assert tomllib.loads(text)["vars"]["ALLOW_IPS"] == "203.0.113.0/24,198.51.100.7"
    assert configs.proxy_refusals("acme", "eu", out.proxy, root=ROOT) == []
    assert configs.account_refusals("acme", "eu", out.account, root=ROOT) == []


def test_allow_ips_is_written_without_the_whitespace_it_was_checked_without():
    out = _gen(allow_ips=("10.0.0.1, 10.0.0.2", " 10.0.0.3 "))
    for text in (out.proxy, out.account):
        assert tomllib.loads(text)["vars"]["ALLOW_IPS"] == "10.0.0.1,10.0.0.2,10.0.0.3"


def test_company_proxy_carries_the_executor_caps():
    vars_ = tomllib.loads(_gen().proxy)["vars"]
    assert vars_["EXECUTOR_CAP"] == "25"
    assert vars_["EXECUTOR_HEAVY_CAP"] == "5"


@pytest.mark.parametrize("bad", ["0.0.0.0/0", "10.0.0.0/33", "not-an-ip", ""])
def test_a_malformed_allow_ips_entry_is_refused_at_generation(bad):
    with pytest.raises(configs.ConfigError):
        _gen(allow_ips=(bad,))


def test_the_plant_of_a_malformed_allow_ips_is_refused():
    out = _gen(allow_ips=("10.0.0.1",))
    text = out.proxy.replace('"10.0.0.1"', '"0.0.0.0/0"')
    assert any("ALLOW_IPS" in r for r in configs.proxy_refusals("acme", "eu", text, root=ROOT))


@pytest.mark.parametrize("bad", ["eu", "acme-proxy", "Acme"])
def test_a_bad_company_name_is_refused(bad):
    with pytest.raises(configs.ConfigError):
        _gen(company=bad)


def test_an_unknown_region_is_refused():
    with pytest.raises(configs.ConfigError):
        _gen(region="mars")


def test_a_bad_d1_id_is_refused():
    with pytest.raises(configs.ConfigError):
        configs.generate("acme", "eu", "not-a-uuid", root=ROOT)


def test_a_company_token_naming_a_channel_is_refused():
    with pytest.raises(configs.ConfigError, match="dev"):
        _gen(company="acme-dev")


@pytest.mark.parametrize(
    ("old", "new", "needle"),
    [
        ('name = "proxy-acme"', 'name = "proxy-other"', "name"),
        ("acme-proxy.", "other-proxy.", "routes"),
        ('service = "account-acme"', 'service = "account-eu"', "service"),
        ('"otlp-eu-logs"', '"otlp-us-logs"', "destination"),
        ('REGION = "eu"', 'REGION = "us"', "REGION"),
    ],
)
def test_proxy_plants_are_refused_by_name(old, new, needle):
    text = _gen().proxy
    assert old in text
    reasons = configs.proxy_refusals("acme", "eu", text.replace(old, new), root=ROOT)
    assert any(needle in r for r in reasons), reasons


def test_a_custom_domain_route_is_refused_for_a_company():
    text = _gen().proxy.replace('zone_name = "%s"' % PRODUCT_DOMAIN, "custom_domain = true")
    assert configs.proxy_refusals("acme", "eu", text, root=ROOT)


@pytest.mark.parametrize(
    ("old", "new", "needle"),
    [
        ('service = "proxy-acme"', 'service = "proxy-eu"', "EXECUTOR"),
        ('database_name = "account-acme"', 'database_name = "account-eu"', "d1"),
        ('bucket_name = "configs-acme"', 'bucket_name = "configs-eu"', "bucket"),
        ('name = "account-acme"', 'name = "account-eu"', "name"),
    ],
)
def test_account_plants_are_refused_by_name(old, new, needle):
    text = _gen().account
    assert old in text
    reasons = configs.account_refusals("acme", "eu", text.replace(old, new, 1), root=ROOT)
    assert any(needle in r for r in reasons), reasons


@pytest.mark.parametrize("name", ["ACCOUNT_ED25519_PRIVATE_KEY", "FREE_LICENSE_HMAC_KEY"])
def test_the_account_config_carries_no_signing_secret_name(name):
    assert name not in _gen().account
    text = _gen().account + "\n" + name + ' = "x"\n'
    assert configs.account_refusals("acme", "eu", text, root=ROOT)


def test_write_lands_under_the_gitignored_enterprise_names(tmp_path):
    for sub in ("proxy", "account"):
        (tmp_path / "workers" / sub).mkdir(parents=True)
    written = configs.write("acme", "eu", D1_ID, root=ROOT, out_root=tmp_path)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in written) == [
        "workers/account/enterprise.acme.toml",
        "workers/proxy/enterprise.acme.toml",
    ]
    # the name escapes the shared config glob, so check:ci-proxy-configs never sees it
    assert not any(p.match(pc.CONFIG_GLOB) for p in written)


def test_the_gitignore_hides_company_tomls_but_not_the_template():
    for sub in ("proxy", "account"):
        text = (ROOT / "workers" / sub / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert "enterprise.*.toml" in text
    assert "!enterprise.template.toml" in (ROOT / "workers/account/.gitignore").read_text()
