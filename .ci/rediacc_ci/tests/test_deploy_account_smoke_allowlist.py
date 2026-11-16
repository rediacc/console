"""The post-deploy portal smoke on a company whose ALLOW_IPS refuses the deploying machine: no request leaves the process."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from rediacc_ci.deploy import deploy_account as port
from rediacc_ci.ops import portal_captcha as pc
from rediacc_ci.well_known import ACCOUNT_DEFAULT_ORIGIN

if TYPE_CHECKING:
    import pathlib

HOST = urlparse(ACCOUNT_DEFAULT_ORIGIN).netloc
SITEKEY = "0x4AAAAAACfixtureKey0001"
ROUTED = 'routes = [\n  { pattern = "%s", custom_domain = true }\n]\n' % HOST
ALLOWLISTED = ROUTED + '[vars]\nALLOW_IPS = "203.0.113.7"\n'
# workers/proxy/src/ip-allowlist.ts `allowlistRefusal`.
ALLOWLIST_BODY = '{"error":"This address is not on the allowlist."}'


def smoke_answering_403(tmp_path: pathlib.Path, toml: str, body: str) -> tuple[str | None, list]:
    config = tmp_path / "wrangler.eu.toml"
    config.write_text(toml)
    calls: list = []

    def fetch(method, url, _body):
        calls.append((method, url))
        return pc.Reply(403, body)

    refusal = port.portal_smoke(config, {"TURNSTILE_SITE_KEY": SITEKEY}, fetch, lambda _s: None)
    return refusal, calls


def test_the_smoke_is_skipped_when_the_company_allowlist_refuses_this_machine(
    tmp_path: pathlib.Path,
) -> None:
    refusal, calls = smoke_answering_403(tmp_path, ALLOWLISTED, ALLOWLIST_BODY)
    assert refusal is None
    assert calls == [("GET", ACCOUNT_DEFAULT_ORIGIN + "/account/login")]


def test_a_403_without_an_allowlist_in_the_config_is_still_a_refusal(
    tmp_path: pathlib.Path,
) -> None:
    refusal, _calls = smoke_answering_403(tmp_path, ROUTED, ALLOWLIST_BODY)
    assert refusal is not None
    assert "UNKNOWN" in refusal


def test_a_403_with_another_body_is_still_a_refusal_under_an_allowlist(
    tmp_path: pathlib.Path,
) -> None:
    for body in ('{"error":"Forbidden"}', "not json", "[]"):
        refusal, _calls = smoke_answering_403(tmp_path, ALLOWLISTED, body)
        assert refusal is not None, body
        assert "UNKNOWN" in refusal
