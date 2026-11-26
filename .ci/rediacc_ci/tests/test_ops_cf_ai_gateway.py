"""`cf_ai_gateway` against a recorded AI Gateway API fixture (agent/plans/PLAN-console-ai-credits.md AC8).

`cf_auth.curl_json` is replaced by an in-memory account that answers the list, create and update calls in the shape the API returned when recorded, and keeps every request.
"""

from __future__ import annotations

import io
import json
import pathlib

import pytest

from rediacc_ci.ops import cf_ai_gateway, cf_auth

ACCT = cf_auth.DEFAULT_ACCOUNT_ID
REAL_CONFIG = pathlib.Path(__file__).resolve().parents[2] / "config" / "ai-gateway.json"

KEYS = {
    "collect_logs",
    "cache_ttl",
    "cache_invalidate_on_update",
    "rate_limiting_interval",
    "rate_limiting_limit",
    "rate_limiting_technique",
    "authentication",
}

RECORDED_GATEWAY = {
    "id": "rediacc-eu",
    "account_id": ACCT,
    "created_at": "2026-11-20 10:00:00",
    "modified_at": "2026-11-20 10:00:00",
    "collect_logs": True,
    "cache_ttl": None,
    "cache_invalidate_on_update": False,
    "rate_limiting_interval": 60,
    "rate_limiting_limit": 600,
    "rate_limiting_technique": "sliding",
    "authentication": True,
}


class FakeAccount:
    def __init__(self, gateways: list[dict]):
        self.gateways = {g["id"]: dict(g) for g in gateways}
        self.calls: list[tuple[str, str, dict | None]] = []
        self.sent: list[tuple[list[str], dict]] = []

    def __call__(self, method, url, headers, body=None, **options):
        self.sent.append((headers, options))
        doc = json.loads(body) if body else None
        self.calls.append((method, url, doc))
        if method == "GET":
            return {"success": True, "result": list(self.gateways.values())}
        # A write always carries its body, in the tool and in this fake.
        if method == "POST":
            assert doc is not None, method
            self.gateways[doc["id"]] = doc
            return {"success": True, "result": doc}
        if method == "PUT":
            assert doc is not None, method
            self.gateways[doc["id"]] = {**self.gateways[doc["id"]], **doc}
            return {"success": True, "result": doc}
        return {"success": False, "errors": [{"code": 1, "message": "no fake route"}]}

    def writes(self) -> list[tuple[str, str, dict | None]]:
        return [c for c in self.calls if c[0] != "GET"]


@pytest.fixture
def wanted() -> dict[str, dict]:
    return {"rediacc-eu": {k: v for k, v in RECORDED_GATEWAY.items() if k in KEYS}}


def make_api(monkeypatch, gateways: list[dict]) -> tuple[cf_ai_gateway.Api, FakeAccount]:
    fake = FakeAccount(gateways)
    monkeypatch.setattr(cf_auth, "curl_json", fake)
    return cf_ai_gateway.Api(cf_auth.Auth(token="T"), ACCT), fake


def test_matching_gateway_is_left_alone(monkeypatch, wanted):
    api, fake = make_api(monkeypatch, [RECORDED_GATEWAY])
    out = io.StringIO()
    assert cf_ai_gateway.run(api, wanted, check=False, out=out) == 0
    assert "UNCHANGED rediacc-eu" in out.getvalue()
    assert "0 change(s)" in out.getvalue()
    assert fake.writes() == []
    assert fake.sent[0][0] == ["-H", "Authorization: Bearer T"]


def test_missing_gateway_is_created_then_second_run_writes_nothing(monkeypatch, wanted):
    api, fake = make_api(monkeypatch, [])
    assert cf_ai_gateway.run(api, wanted, check=False, out=io.StringIO()) == 0
    assert [c[0] for c in fake.writes()] == ["POST"]
    first = fake.writes()[0][2]
    assert first is not None
    assert first["id"] == "rediacc-eu"
    before = len(fake.writes())
    out = io.StringIO()
    assert cf_ai_gateway.run(api, wanted, check=False, out=out) == 0
    assert len(fake.writes()) == before
    assert "0 change(s)" in out.getvalue()


def test_apply_puts_a_drifted_gateway(monkeypatch, wanted):
    api, fake = make_api(monkeypatch, [{**RECORDED_GATEWAY, "cache_ttl": 300}])
    out = io.StringIO()
    assert cf_ai_gateway.run(api, wanted, check=False, out=out) == 0
    assert [c[0] for c in fake.writes()] == ["PUT"]
    assert fake.writes()[0][1].endswith("/gateways/rediacc-eu")
    assert fake.gateways["rediacc-eu"]["cache_ttl"] is None
    assert "cache_ttl 300 -> None" in out.getvalue()


def test_check_exits_1_on_a_hand_changed_setting_and_writes_nothing(monkeypatch, wanted):
    api, fake = make_api(monkeypatch, [{**RECORDED_GATEWAY, "collect_logs": False}])
    out = io.StringIO()
    assert cf_ai_gateway.run(api, wanted, check=True, out=out) == 1
    assert "DRIFT rediacc-eu" in out.getvalue()
    assert "collect_logs False -> True" in out.getvalue()
    assert fake.writes() == []


def test_check_exits_0_when_the_account_matches(monkeypatch, wanted):
    api, fake = make_api(monkeypatch, [RECORDED_GATEWAY])
    assert cf_ai_gateway.run(api, wanted, check=True, out=io.StringIO()) == 0
    assert fake.writes() == []


def test_check_exits_1_on_a_missing_gateway(monkeypatch, wanted):
    api, fake = make_api(monkeypatch, [])
    out = io.StringIO()
    assert cf_ai_gateway.run(api, wanted, check=True, out=out) == 1
    assert "MISSING rediacc-eu" in out.getvalue()
    assert fake.writes() == []


def test_a_refused_write_raises_with_cloudflare_text(monkeypatch, wanted):
    api, _ = make_api(monkeypatch, [])

    def refuse(method, *_args, **_options):
        if method == "GET":
            return {"success": True, "result": []}
        return {"success": False, "errors": [{"code": 7003, "message": "denied"}]}

    monkeypatch.setattr(cf_auth, "curl_json", refuse)
    with pytest.raises(cf_ai_gateway.GatewayError, match="denied"):
        cf_ai_gateway.run(api, wanted, check=False, out=io.StringIO())


def test_committed_config_merges_defaults_for_every_region():
    want = cf_ai_gateway.load_config(REAL_CONFIG)
    assert sorted(want) == ["rediacc-asia", "rediacc-eu", "rediacc-us"]
    for settings in want.values():
        assert settings["collect_logs"] is True
        assert settings["cache_ttl"] is None
        assert set(settings) == KEYS


def test_dry_run_reads_no_secret_and_makes_no_request(monkeypatch, capsys):
    monkeypatch.delenv("CF_MANAGEMENT_TOKEN", raising=False)
    monkeypatch.delenv("CF_GLOBAL_API_KEY", raising=False)

    def boom(*_args, **_options):
        raise AssertionError("dry run made a request")

    monkeypatch.setattr(cf_auth, "curl_json", boom)
    assert cf_ai_gateway.main(["--dry-run", "--config", str(REAL_CONFIG)]) == 0
    out = capsys.readouterr().out
    assert "WOULD SET rediacc-eu" in out
    assert "3 gateway(s) configured" in out


def test_check_without_a_token_fails_before_any_request(monkeypatch, capsys):
    monkeypatch.delenv("CF_MANAGEMENT_TOKEN", raising=False)
    assert cf_ai_gateway.main(["--check", "--config", str(REAL_CONFIG)]) == 1
    assert "CF_MANAGEMENT_TOKEN" in capsys.readouterr().err


def test_config_without_gateways_is_refused(tmp_path):
    bad = tmp_path / "c.json"
    bad.write_text('{"settings_defaults": {}, "gateways": {}}')
    with pytest.raises(cf_ai_gateway.GatewayError):
        cf_ai_gateway.load_config(bad)
