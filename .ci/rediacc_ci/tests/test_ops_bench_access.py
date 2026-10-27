"""rediacc_ci.ops.bench_access: the bench IP allowlist as one WAF custom rule, against a fake Cloudflare."""

import datetime
import json
import subprocess
from typing import Any

import pytest

from rediacc_ci.ops import bench_access as ba
from rediacc_ci.ops import cf_auth
from rediacc_ci.well_known import BENCH_ORIGIN, PROXY_BENCH_HOST

BENCH_HOST = BENCH_ORIGIN.removeprefix("https://")
HOSTS = [BENCH_HOST, PROXY_BENCH_HOST]
SECRET = "tok-must-not-be-on-argv"


class FakeCloudflare:
    """The zone's http_request_firewall_custom entrypoint: GET/PUT entrypoint, POST/PATCH/DELETE rules."""

    def __init__(self, other_rules=None):
        self.ruleset: Any = None
        if other_rules:
            self.ruleset = {"id": "rs1", "rules": list(other_rules)}
        self.calls: list[tuple[str, str]] = []
        self.counter = 0

    def _rule(self, body):
        self.counter += 1
        return {**body, "id": "r%d" % self.counter}

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        entry = "/zones/%s/rulesets/phases/%s/entrypoint" % (ba.ZONE_ID, ba.PHASE)
        base = "/zones/%s/rulesets/rs1/rules" % ba.ZONE_ID
        if (method, path) == ("GET", entry):
            if self.ruleset is None:
                return {"success": False, "errors": [{"code": 10003, "message": "no entrypoint"}]}
            return {"success": True, "result": self.ruleset}
        if (method, path) == ("PUT", entry):
            self.ruleset = {"id": "rs1", "rules": [self._rule(r) for r in body["rules"]]}
        elif (method, path) == ("POST", base):
            self.ruleset["rules"].append(self._rule(body))
        elif method == "PATCH" and path.startswith(base + "/"):
            rid = path.rsplit("/", 1)[1]
            rules = self.ruleset["rules"]
            rules[:] = [{**body, "id": rid} if r["id"] == rid else r for r in rules]
        elif method == "DELETE" and path.startswith(base + "/"):
            rid = path.rsplit("/", 1)[1]
            self.ruleset["rules"] = [r for r in self.ruleset["rules"] if r["id"] != rid]
        else:
            return {"success": False, "errors": [{"code": 1, "message": "unexpected call"}]}
        return {"success": True, "result": self.ruleset}

    def mine(self):
        return [
            r
            for r in (self.ruleset or {}).get("rules", [])
            if r["description"].startswith(ba.RULE_DESCRIPTION)
        ]


@pytest.fixture(autouse=True)
def _hosts(monkeypatch):
    monkeypatch.setattr(ba, "bench_hosts", lambda _root=None: HOSTS)


class Clock:
    """A settable UTC clock for `ba.run`."""

    def __init__(self):
        self.now = datetime.datetime(2026, 10, 27, 5, 0, tzinfo=datetime.UTC)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += datetime.timedelta(**kwargs)


CLOCK = Clock()


@pytest.fixture(autouse=True)
def _clock():
    CLOCK.__init__()


def _run(api, command, argument=None, detect=lambda: ["198.51.100.7"]):
    return ba.run(command, argument, api, detect=detect, clock=CLOCK)


def _stored(api):
    return ba.entries_of(api.mine()[0])


def test_first_add_creates_the_rule_holding_the_callers_ip(capsys):
    api = FakeCloudflare()
    assert _run(api, "add-current") == 0
    (rule,) = api.mine()
    assert rule["action"] == "block"
    assert ba.ips_of(rule["expression"]) == ["198.51.100.7"]
    assert "PUT" in [method for method, _ in api.calls]
    assert "198.51.100.7" in capsys.readouterr().out


def test_the_rule_blocks_without_a_custom_response():
    """The Free plan refuses a custom response (live 2026-10-26: `not entitled to use a custom response`), so the rule is a plain block and the hint lives in the tooling."""
    api = FakeCloudflare()
    _run(api, "add-current")
    (rule,) = api.mine()
    assert rule["action"] == "block"
    assert "action_parameters" not in rule
    assert ba.HINT.endswith("bench_access add-current")
    expr = rule["expression"]
    for host in HOSTS:
        assert '"%s"' % host in expr
    # The exemption that keeps telemetry-probe.yml working, and nothing wider.
    assert 'http.request.method eq "GET"' in expr
    assert '"/account/api/v1/health" "/v1/health"' in expr


def test_add_past_the_limit_evicts_the_oldest():
    api = FakeCloudflare()
    for n in range(1, 8):
        _run(api, "add", "203.0.113.%d" % n)
    (rule,) = api.mine()
    assert ba.ips_of(rule["expression"]) == ["203.0.113.%d" % n for n in range(3, 8)]
    assert len(ba.ips_of(rule["expression"])) == ba.MAX_IPS


def test_readding_an_ip_moves_it_to_the_end_without_eviction():
    api = FakeCloudflare()
    for n in range(1, 6):
        _run(api, "add", "203.0.113.%d" % n)
    _run(api, "add", "203.0.113.1")
    (rule,) = api.mine()
    assert ba.ips_of(rule["expression"]) == [
        "203.0.113.2",
        "203.0.113.3",
        "203.0.113.4",
        "203.0.113.5",
        "203.0.113.1",
    ]


def test_list_remove_and_clear(capsys):
    api = FakeCloudflare()
    _run(api, "add", "203.0.113.1")
    _run(api, "add", "2001:db8::1")
    capsys.readouterr()
    _run(api, "list")
    out = capsys.readouterr().out
    assert "203.0.113.1" in out
    assert "2001:db8::/64" in out
    _run(api, "remove", "203.0.113.1")
    assert ba.ips_of(api.mine()[0]["expression"]) == ["2001:db8::/64"]
    with pytest.raises(ba.AccessError, match="not in the allowlist"):
        _run(api, "remove", "203.0.113.1")
    _run(api, "clear")
    (rule,) = api.mine()
    assert ba.ips_of(rule["expression"]) == []
    assert "ip.src" not in rule["expression"]
    capsys.readouterr()
    _run(api, "list")
    assert "every IP but the health paths is blocked" in capsys.readouterr().out


def test_clear_without_a_rule_does_not_create_one():
    api = FakeCloudflare()
    with pytest.raises(ba.AccessError, match="nothing to clear"):
        _run(api, "clear")
    assert api.ruleset is None


def test_list_without_a_rule_says_bench_is_open(capsys):
    _run(FakeCloudflare(), "list")
    assert "bench is open to every IP" in capsys.readouterr().out


def test_disable_deletes_only_our_rule():
    other = {"id": "keep", "description": "someone else's rule", "action": "block"}
    api = FakeCloudflare(other_rules=[other])
    _run(api, "add", "203.0.113.1")
    assert len(api.ruleset["rules"]) == 2
    _run(api, "disable")
    assert api.ruleset["rules"] == [other]
    _run(api, "disable")  # no rule: a no-op


def test_add_current_uses_the_detected_addresses():
    api = FakeCloudflare()
    _run(api, "add-current", detect=lambda: ["198.51.100.7", "2001:db8::7"])
    assert ba.ips_of(api.mine()[0]["expression"]) == ["198.51.100.7", "2001:db8::/64"]


def test_detect_reads_each_family_and_skips_one_that_fails():
    def fetch(url):
        if "1.1.1.1" in url:
            return "fl=1\nip=198.51.100.7\nloc=XX\n"
        raise OSError("no v6")

    assert ba.detect_public_ips(fetch) == ["198.51.100.7"]


def test_detect_names_the_failure_when_no_family_answers():
    def fetch(_url):
        raise OSError("down")

    with pytest.raises(ba.AccessError, match="could not read this machine's public IP"):
        ba.detect_public_ips(fetch)


def test_a_cidr_or_garbage_is_not_an_address():
    for bad in ("not-an-ip", "1.2.3", "2001:db8::/zz"):
        with pytest.raises(ba.AccessError, match="not a single IP address"):
            ba.normalize_ip(bad)
    assert ba.normalize_ip("203.0.113.9/32") == "203.0.113.9"
    assert ba.normalize_ip(" 2001:0db8:0:0:0:0:0:1 ") == "2001:db8::/64"


def test_a_cloudflare_refusal_is_a_named_error():
    class Refusing(FakeCloudflare):
        def request(self, method, path, body=None):
            if method == "GET":
                return {"success": False, "errors": [{"code": 9109, "message": "Unauthorized"}]}
            return super().request(method, path, body)

    with pytest.raises(ba.AccessError, match="Unauthorized"):
        _run(Refusing(), "list")


def test_hosts_come_from_the_bench_wrangler_configs():
    found = ba.bench_hosts()
    assert BENCH_HOST in found
    assert PROXY_BENCH_HOST in found


def test_the_token_reaches_curl_on_stdin_never_argv(monkeypatch):
    seen: list[tuple[list[str], str | None]] = []

    def fake_run(argv, **kwargs):
        seen.append((argv, kwargs.get("input")))
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"success": True}), stderr="")

    monkeypatch.setattr(cf_auth.subprocess, "run", fake_run)
    api = ba.CloudflareApi(cf_auth.Auth(token=SECRET), sleep=lambda _s: None)
    assert api.request("GET", "/zones/z/rulesets")["success"] is True
    argv, stdin = seen[0]
    assert all(SECRET not in arg for arg in argv)
    assert SECRET in (stdin or "")


def test_a_fresh_token_is_retried_while_cloudflare_propagates(monkeypatch):
    answers = [
        {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]},
        {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]},
        {"success": True, "result": {}},
    ]
    monkeypatch.setattr(cf_auth, "curl_json", lambda *_a, **_k: answers.pop(0))
    slept: list[float] = []
    api = ba.CloudflareApi(cf_auth.Auth(token="t"), sleep=slept.append)
    assert api.request("GET", "/x")["success"] is True
    assert slept == [ba.AUTH_RETRY_S, ba.AUTH_RETRY_S]


def test_main_rejects_unknown_verbs_and_wrong_arity():
    assert ba.main([]) == 2
    assert ba.main(["frobnicate"]) == 2
    assert ba.main(["add"]) == 2
    assert ba.main(["list", "extra"]) == 2


def test_main_mints_a_zone_scoped_token_and_destroys_it(monkeypatch):
    events: list[str] = []
    auth = cf_auth.Auth(token="t", created=True)
    monkeypatch.setenv("CF_MANAGEMENT_TOKEN", "x")

    def resolve(purpose, _account_id=cf_auth.DEFAULT_ACCOUNT_ID, zone_id=None):
        events.append("resolve %s %s" % (purpose, zone_id))
        return auth

    monkeypatch.setattr(cf_auth, "resolve_scoped", resolve)
    monkeypatch.setattr(cf_auth, "await_propagation", lambda _a: 0.0)
    monkeypatch.setattr(cf_auth, "self_destruct", lambda _a: events.append("destroy"))
    monkeypatch.setattr(ba, "run", lambda *_a, **_k: 0)
    assert ba.main(["list"]) == 0
    assert events == ["resolve bench-access %s" % ba.ZONE_ID, "destroy"]


def test_cf_auth_mints_the_zone_waf_group_on_the_zone_only(monkeypatch):
    posted: list[dict] = []

    def curl_json(_method, url, _headers, body=None, **_k):
        if url.endswith("/user"):
            return {"result": {"id": "u1"}}
        if url.endswith("/permission_groups"):
            return {
                "result": [
                    {"name": "Zone WAF Write", "id": "waf", "scopes": [cf_auth.ZONE_SCOPE]},
                    {"name": "API Tokens Write", "id": "ignored", "scopes": ["x"]},
                ]
            }
        posted.append(json.loads(body))
        return {"result": {"value": "minted"}}

    monkeypatch.setattr(cf_auth, "curl_json", curl_json)
    auth = cf_auth.create_scoped_token("k", "e@x", "bench-access", zone_id="zone9")
    policies = posted[0]["policies"]
    assert policies[0]["resources"] == {"%s.zone9" % cf_auth.ZONE_SCOPE: "*"}
    assert policies[0]["permission_groups"] == [{"id": "waf"}]
    assert len(policies) == 2  # the zone policy and the user-scoped self-destruct pair
    assert auth.token == "minted"
    with pytest.raises(cf_auth.CfAuthError, match="needs a zone id"):
        cf_auth.create_scoped_token("k", "e@x", "bench-access")


def test_each_ip_carries_its_add_time_in_the_rule_description():
    api = FakeCloudflare()
    _run(api, "add", "203.0.113.1")
    CLOCK.advance(hours=3)
    _run(api, "add", "203.0.113.2")
    (rule,) = api.mine()
    assert rule["description"] == (
        ba.RULE_DESCRIPTION
        + " | added 203.0.113.1=2026-10-27T05:00:00Z 203.0.113.2=2026-10-27T08:00:00Z"
    )
    assert [ip for ip, _ in _stored(api)] == ["203.0.113.1", "203.0.113.2"]


def test_an_ip_older_than_seven_days_is_dropped_before_adding():
    api = FakeCloudflare()
    _run(api, "add", "203.0.113.1")
    CLOCK.advance(days=6, hours=23)
    _run(api, "add", "203.0.113.2")
    assert [ip for ip, _ in _stored(api)] == ["203.0.113.1", "203.0.113.2"]
    CLOCK.advance(hours=2)  # .1 is now 7d 1h old, .2 is 2h old
    _run(api, "add", "203.0.113.3")
    assert [ip for ip, _ in _stored(api)] == ["203.0.113.2", "203.0.113.3"]


def test_expiry_applies_to_remove_and_clear_runs_too():
    api = FakeCloudflare()
    _run(api, "add", "203.0.113.1")
    _run(api, "add", "203.0.113.2")
    CLOCK.advance(days=8)
    with pytest.raises(ba.AccessError, match="not in the allowlist"):
        _run(api, "remove", "203.0.113.1")  # already expired, so not live
    _run(api, "clear")
    assert _stored(api) == []


def test_readding_a_live_ip_refreshes_its_stamp():
    api = FakeCloudflare()
    _run(api, "add", "203.0.113.1")
    CLOCK.advance(days=5)
    _run(api, "add", "203.0.113.1")
    CLOCK.advance(days=5)  # 10 days after the first add, 5 after the refresh
    _run(api, "add", "203.0.113.2")
    stored = dict(_stored(api))
    assert set(stored) == {"203.0.113.1", "203.0.113.2"}
    assert stored["203.0.113.1"] == CLOCK.now - datetime.timedelta(days=5)


def test_the_cap_counts_after_expiry():
    api = FakeCloudflare()
    for n in range(1, 6):
        _run(api, "add", "203.0.113.%d" % n)
        CLOCK.advance(days=1)
    CLOCK.advance(days=2)  # .1 is 7d old and .2 is 6d old at the next run: .1 expires
    _run(api, "add", "203.0.113.9")
    ips = [ip for ip, _ in _stored(api)]
    assert ips == ["203.0.113.%d" % n for n in (2, 3, 4, 5, 9)]  # five, none evicted
    _run(api, "add", "203.0.113.10")
    ips = [ip for ip, _ in _stored(api)]
    assert ips == ["203.0.113.%d" % n for n in (3, 4, 5, 9, 10)]  # now the cap evicts the oldest


def test_a_legacy_ip_with_no_stamp_is_expired(capsys):
    legacy = {
        "id": "old",
        "description": ba.RULE_DESCRIPTION,
        "action": "block",
        "expression": ba.expression(HOSTS, ["192.0.2.1", "192.0.2.2"]),
    }
    api = FakeCloudflare(other_rules=[legacy])
    _run(api, "list")
    assert "no add time" in capsys.readouterr().out
    _run(api, "add", "203.0.113.1")
    assert [ip for ip, _ in _stored(api)] == ["203.0.113.1"]
    assert "192.0.2" not in api.mine()[0]["expression"]


def test_a_partly_stamped_description_expires_only_the_unstamped():
    api = FakeCloudflare()
    _run(api, "add", "203.0.113.1")
    rule = api.mine()[0]
    rule["expression"] = ba.expression(HOSTS, ["203.0.113.1", "192.0.2.5"])
    _run(api, "add", "203.0.113.2")
    assert [ip for ip, _ in _stored(api)] == ["203.0.113.1", "203.0.113.2"]


def test_a_clock_with_microseconds_still_reads_back_equal():
    api = FakeCloudflare()
    CLOCK.now = CLOCK.now.replace(microsecond=506870)
    assert _run(api, "add", "203.0.113.1") == 0
    assert _stored(api)[0][1] == CLOCK.now.replace(microsecond=0)


def test_an_ipv6_address_is_stored_as_its_slash_64_in_the_cloudflare_set():
    api = FakeCloudflare()
    _run(api, "add", "2001:a61:50d0:3b01:ccbd:c78c:8df7:242c")
    (rule,) = api.mine()
    assert "ip.src in {2001:a61:50d0:3b01::/64}" in rule["expression"]
    assert "=2026-10-27T05:00:00Z" in rule["description"]
    assert [ip for ip, _ in _stored(api)] == ["2001:a61:50d0:3b01::/64"]


def test_readding_inside_a_slash_64_refreshes_that_one_entry():
    api = FakeCloudflare()
    _run(api, "add", "2001:db8:1:2:aaaa::1")
    _run(api, "add", "203.0.113.1")
    CLOCK.advance(days=3)
    _run(api, "add", "2001:db8:1:2:bbbb::2")
    stored = dict(_stored(api))
    assert list(stored) == ["203.0.113.1", "2001:db8:1:2::/64"]
    assert stored["2001:db8:1:2::/64"] == CLOCK.now


def test_remove_by_address_removes_its_slash_64():
    api = FakeCloudflare()
    _run(api, "add", "2001:db8:1:2:aaaa::1")
    _run(api, "remove", "2001:db8:1:2:cccc::9")
    assert _stored(api) == []


def test_a_broad_ipv6_prefix_or_an_ipv4_range_is_refused():
    for bad in ("2001:db8::/32", "2001:db8:1:2::/63", "2001:db8::/1", "203.0.113.0/24"):
        with pytest.raises(ba.AccessError, match="refusing"):
            ba.normalize_ip(bad)
    assert ba.normalize_ip("2001:db8:1:2::5/128") == "2001:db8:1:2::5/128"
    assert ba.normalize_ip("2001:db8:1:2:3::/80") == "2001:db8:1:2:3::/80"
    assert ba.normalize_ip("2001:db8:1:2:9::7/64") == "2001:db8:1:2::/64"


def test_a_bare_ipv6_in_an_existing_rule_reads_as_its_slash_64():
    legacy = {
        "id": "old",
        "description": ba.RULE_DESCRIPTION + " | added 2001:db8::1=2026-10-27T04:00:00Z",
        "action": "block",
        "expression": ba.expression(HOSTS, ["2001:db8::1"]),
    }
    api = FakeCloudflare(other_rules=[legacy])
    _run(api, "add", "2001:db8::77")
    assert [ip for ip, _ in _stored(api)] == ["2001:db8::/64"]


def test_host_detection_needs_wsl_and_asks_each_family(capsys):
    asked: list[str] = []

    def powershell(command):
        asked.append(command)
        if "api64" in command:
            return "2001:a61:50d0:3b01:ccbd:c78c:8df7:242c\r\n"
        raise OSError("no v4")

    assert ba.detect_host_ips(powershell, wsl=False) == []
    assert asked == []
    assert ba.detect_host_ips(powershell, wsl=True) == ["2001:a61:50d0:3b01:ccbd:c78c:8df7:242c"]
    assert len(asked) == 2
    assert "api.ipify.org; skipped" in capsys.readouterr().out


def test_wsl_is_detected_from_the_interop_marker_or_the_distro_name(monkeypatch):
    monkeypatch.setattr(ba.os.path, "exists", lambda _p: False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    assert ba.in_wsl() is False
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    assert ba.in_wsl() is True
    monkeypatch.delenv("WSL_DISTRO_NAME")
    monkeypatch.setattr(ba.os.path, "exists", lambda p: p == ba.WSL_MARKER)
    assert ba.in_wsl() is True


def test_detect_current_merges_the_host_and_survives_a_dead_trace():
    both = ba.detect_current(lambda: ["62.0.0.1"], lambda: ["62.0.0.1", "2001:db8:1:2::9"])
    assert both == ["62.0.0.1", "2001:db8:1:2::9"]

    def dead():
        raise ba.AccessError("down")

    assert ba.detect_current(dead, lambda: ["2001:db8:1:2::9"]) == ["2001:db8:1:2::9"]
    with pytest.raises(ba.AccessError):
        ba.detect_current(dead, list)


def test_preflight_skips_when_bench_already_answers(capsys):
    added: list[int] = []
    rc = ba.preflight(
        probes=(lambda: 302, lambda: 200), add=lambda: added.append(1) or 0, environ={}
    )
    assert rc == 0
    assert added == []
    assert "reachable (302, 200)" in capsys.readouterr().out


def test_preflight_adds_on_a_403_from_any_egress():
    added: list[int] = []
    rc = ba.preflight(
        probes=(lambda: 302, lambda: 403), add=lambda: added.append(1) or 0, environ={}
    )
    assert rc == 0
    assert added == [1]


def test_preflight_does_nothing_under_ci(capsys):
    def boom():
        raise AssertionError("probed under CI")

    assert ba.preflight(probes=(boom,), add=boom, environ={"CI": "true"}) == 0
    assert "skipped under CI" in capsys.readouterr().out


def test_preflight_never_fails(capsys):
    def offline():
        raise OSError("offline")

    def bad_add():
        raise ba.AccessError("cloudflare said no")

    assert ba.preflight(probes=(offline,), add=lambda: 1, environ={}) == 0
    assert ba.preflight(probes=(lambda: 403,), add=bad_add, environ={}) == 0
    assert ba.preflight(probes=(lambda: 403,), add=lambda: 1, environ={}) == 0
    out = capsys.readouterr().out
    assert "skipped (OSError: offline)" in out
    assert "cloudflare said no" in out
    assert "add-current exited 1" in out


def test_main_preflight_returns_zero_without_credentials(monkeypatch):
    monkeypatch.setenv("CI", "true")
    assert ba.main(["preflight"]) == 0
