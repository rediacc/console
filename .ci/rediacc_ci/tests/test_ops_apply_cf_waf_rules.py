"""`rediacc_ci.ops.apply_cf_waf_rules`: the Free License rate rule (agent/plans/PLAN-free-license.md F8) against a recorded fake transport and the real config and Worker files."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import apply_cf_waf_rules as w

if TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
CONFIG = json.loads((ROOT / w.CONFIG_REL).read_text(encoding="utf-8"))
ZONE = CONFIG["zones"][0]
ENTRY = "/zones/%s/rulesets/phases/http_ratelimit/entrypoint" % ZONE["zoneId"]


class FakeCloudflare:
    """A transport that answers from a scripted entrypoint and records every call."""

    def __init__(self, entrypoint: dict | None) -> None:
        self.entrypoint = entrypoint
        self.calls: list[tuple[str, str, dict | None]] = []

    def __call__(self, method: str, url: str, body: dict | None) -> tuple[int, dict]:
        self.calls.append((method, url.removeprefix(w.CF_API_BASE), body))
        if method == "GET":
            if self.entrypoint is None:
                return 404, {"success": False, "errors": [{"message": "not found"}]}
            return 200, {"success": True, "result": self.entrypoint}
        return 200, {"success": True, "result": {}}

    def writes(self) -> list[tuple[str, str, dict | None]]:
        return [c for c in self.calls if c[0] != "GET"]


def wanted() -> dict:
    return w.rule_body(CONFIG["rules"][0], w.account_hosts(ROOT))


def test_the_rule_matches_the_plan_numbers() -> None:
    rule = wanted()
    assert rule["ref"] == "free-license-rate"
    assert rule["action"] == "block"
    assert rule["ratelimit"] == {
        "characteristics": ["cf.colo.id", "ip.src"],
        "period": 600,
        "requests_per_period": 20,
        "mitigation_timeout": 3600,
    }
    assert 'http.request.uri.path eq "/account/api/v1/licenses/free"' in rule["expression"]
    assert 'http.request.method eq "POST"' in rule["expression"]


def test_hosts_come_from_every_account_worker_config() -> None:
    hosts = w.account_hosts(ROOT)
    for host in ("bench.rediacc.com", "eu.rediacc.com", "us.rediacc.com", "asia.rediacc.com"):
        assert host in hosts
    for region in ("eu", "us", "asia"):
        assert "edge-%s.rediacc.com" % region in hosts
    for host in hosts:
        assert '"%s"' % host in wanted()["expression"]


def test_the_route_path_is_the_one_the_cli_calls() -> None:
    cli = (ROOT / "packages/cli/src/services/account/free-license.ts").read_text(encoding="utf-8")
    assert "'%s'" % CONFIG["rules"][0]["path"] in cli


def test_dry_run_without_credentials_prints_one_plan_per_zone_and_rule(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("CLOUDFLARE_API_TOKEN", "CF_GLOBAL_API_KEY", "CF_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    assert w.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    plans = [line for line in out.splitlines() if line.startswith("[PLAN]")]
    assert len(plans) == len(CONFIG["zones"]) * len(CONFIG["rules"])
    assert "free-license-rate" in plans[0]


def test_apply_without_credentials_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("CLOUDFLARE_API_TOKEN", "CF_GLOBAL_API_KEY", "CF_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    assert w.main([]) == 1
    assert "CLOUDFLARE_API_TOKEN" in capsys.readouterr().err


def test_a_zone_with_no_entrypoint_gets_one_holding_the_rule() -> None:
    fake = FakeCloudflare(None)
    assert w.run(False, ROOT, fake) == 0
    assert fake.writes() == [("PUT", ENTRY, {"rules": [wanted()]})]


def test_dry_run_against_a_zone_with_no_entrypoint_writes_nothing() -> None:
    fake = FakeCloudflare(None)
    assert w.run(True, ROOT, fake) == 0
    assert fake.writes() == []


def test_a_missing_rule_is_appended_and_foreign_rules_are_left_alone() -> None:
    foreign = {"id": "r-other", "ref": "someone-else", "expression": "true", "action": "log"}
    fake = FakeCloudflare({"id": "RS1", "rules": [foreign]})
    assert w.run(False, ROOT, fake) == 0
    rules_url = "/zones/%s/rulesets/RS1/rules" % ZONE["zoneId"]
    assert fake.writes() == [("POST", rules_url, wanted())]


def test_an_unchanged_rule_writes_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    current = {**wanted(), "id": "r1", "version": "3", "last_updated": "2026-10-30T00:00:00Z"}
    fake = FakeCloudflare({"id": "RS1", "rules": [current]})
    assert w.run(False, ROOT, fake) == 0
    assert fake.writes() == []
    assert "unchanged" in capsys.readouterr().out


def test_a_drifted_rule_is_patched_in_place() -> None:
    current = copy.deepcopy(wanted())
    current["id"] = "r1"
    current["ratelimit"]["requests_per_period"] = 1000
    fake = FakeCloudflare({"id": "RS1", "rules": [current]})
    assert w.run(False, ROOT, fake) == 0
    url = "/zones/%s/rulesets/RS1/rules/r1" % ZONE["zoneId"]
    assert fake.writes() == [("PATCH", url, wanted())]


def test_dry_run_reports_drift_without_writing(capsys: pytest.CaptureFixture[str]) -> None:
    current = {**wanted(), "id": "r1", "action": "log"}
    fake = FakeCloudflare({"id": "RS1", "rules": [current]})
    assert w.run(True, ROOT, fake) == 0
    assert fake.writes() == []
    assert "[DIFF]" in capsys.readouterr().out


def test_two_rules_with_one_ref_are_refused() -> None:
    dup = {**wanted(), "id": "r1"}
    fake = FakeCloudflare({"id": "RS1", "rules": [dup, {**dup, "id": "r2"}]})
    with pytest.raises(w.ApplyError, match="2 rules carry ref free-license-rate"):
        w.run(False, ROOT, fake)
    assert fake.writes() == []


def test_a_cloudflare_refusal_shows_its_message() -> None:
    def refusing(method: str, _url: str, _body: dict | None) -> tuple[int, dict]:
        if method == "GET":
            return 200, {"success": True, "result": {"id": "RS1", "rules": []}}
        return 400, {"success": False, "errors": [{"message": "period not allowed on this plan"}]}

    with pytest.raises(w.ApplyError, match="period not allowed on this plan"):
        w.run(False, ROOT, refusing)


def test_a_config_with_duplicate_refs_is_refused(tmp_path: pathlib.Path) -> None:
    cfg = copy.deepcopy(CONFIG)
    cfg["rules"].append(copy.deepcopy(cfg["rules"][0]))
    (tmp_path / ".ci" / "config").mkdir(parents=True)
    (tmp_path / w.CONFIG_REL).write_text(json.dumps(cfg), encoding="utf-8")
    with pytest.raises(w.ApplyError, match="unique"):
        w.load_config(tmp_path)


def test_no_worker_config_is_refused(tmp_path: pathlib.Path) -> None:
    (tmp_path / "workers" / "account").mkdir(parents=True)
    with pytest.raises(w.ApplyError, match="no account hostnames"):
        w.account_hosts(tmp_path)
