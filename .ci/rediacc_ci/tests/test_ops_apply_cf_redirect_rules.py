"""`rediacc_ci.ops.apply_cf_redirect_rules` against its bash twin `scripts/ops/apply-cf-redirect-rules.sh`, on the sealed fake-binary PATH of `ops_cf_harness`.

The differential cases compare stdout, stderr, exit code and the (method, URL) sequence of every `curl`. A `test_delta_*` case pins one deliberate Rule T difference and asserts the bash behaviour first (the control).
"""

from __future__ import annotations

import json
import typing

import pytest

from rediacc_ci.tests import ops_cf_harness as h

if typing.TYPE_CHECKING:
    import pathlib

APEX_EXPR = '(http.request.full_uri wildcard r"https://rediacc.com/*")'
RULE = {
    "id": "rule-apex",
    "expression": APEX_EXPR,
    "action": "redirect",
    "action_parameters": {"from_value": {"status_code": 301}},
}
ENV = {"CLOUDFLARE_API_TOKEN": "tok"}


def routes(rules: list[dict], extra: tuple[dict, ...] = ()) -> list[dict]:
    return [
        *extra,
        {
            "method": "GET",
            "match": "/rulesets/RS1",
            "body": {"success": True, "result": {"rules": rules}},
        },
        {
            "method": "GET",
            "match": "/rulesets",
            "body": {
                "success": True,
                "result": [
                    {"id": "RS1", "phase": "http_request_dynamic_redirect"},
                    {"id": "OTHER", "phase": "other"},
                ],
            },
        },
        {
            "method": "GET",
            "match": "/dns_records",
            "body": {
                "success": True,
                "result": [{"content": "rediacc.github.io", "proxied": False}],
            },
        },
        {
            "method": "GET",
            "match": "https://rediacc.com/",
            "raw": "HTTP/2 301 \r\nlocation: https://www.rediacc.com/solutions/backup-verification/\r\n\r\n",
        },
    ]


@pytest.fixture
def world(tmp_path: pathlib.Path) -> h.World:
    return h.World(tmp_path)


def _urls(world: h.World) -> list[tuple[str, str]]:
    return [(c["method"], c["url"]) for c in world.calls() if c["tool"] == "curl"]


def test_present_rule_matches_bash(world: h.World) -> None:
    world.set_routes(routes([RULE]))
    env = world.env(**ENV)
    rc_b, out_b, err_b = world.bash("scripts/ops/apply-cf-redirect-rules.sh", [], env)
    calls_b = _urls(world)
    world.reset_log()
    rc_p, out_p, err_p = world.port("rediacc_ci.ops.apply_cf_redirect_rules", [], env)
    assert rc_b == rc_p == 0
    assert out_b == out_p
    assert err_b == err_p
    # The bash probes the smoke URL twice (status, then Location); the port makes one request (delta 3).
    assert [c for i, c in enumerate(calls_b) if i == 0 or c != calls_b[i - 1]] == _urls(world)
    assert calls_b.count(("GET", "https://rediacc.com/solutions/backup-verification/")) == 2
    assert "[OK]   apex redirect rule present (id=rule-apex)" in out_p
    assert "console.rediacc.com -> rediacc.github.io proxied=false" in out_p


def test_missing_rule_dry_run_matches_bash(world: h.World) -> None:
    world.set_routes(routes([]))
    env = world.env(**ENV)
    rc_b, out_b, _ = world.bash("scripts/ops/apply-cf-redirect-rules.sh", ["--dry-run"], env)
    calls_b = _urls(world)
    world.reset_log()
    rc_p, out_p, _ = world.port("rediacc_ci.ops.apply_cf_redirect_rules", ["--dry-run"], env)
    assert rc_b == rc_p == 0
    assert out_b == out_p
    assert calls_b == _urls(world)
    assert all(m == "GET" for m, _ in calls_b)


def test_arguments_and_auth_match_bash(world: h.World) -> None:
    world.set_routes(routes([RULE]))
    for args, env, want in (
        (["--bogus"], world.env(**ENV), 2),
        ([], world.env(), 1),
    ):
        rc_b, _, err_b = world.bash("scripts/ops/apply-cf-redirect-rules.sh", args, env)
        rc_p, _, err_p = world.port("rediacc_ci.ops.apply_cf_redirect_rules", args, env)
        assert rc_b == rc_p == want
        assert err_b.strip() == err_p.strip()


def test_global_key_auth_headers_match_bash(world: h.World) -> None:
    world.set_routes(routes([RULE]))
    env = world.env(CF_GLOBAL_API_KEY="gk", CF_EMAIL="e@x")
    world.bash("scripts/ops/apply-cf-redirect-rules.sh", ["--dry-run"], env)
    heads_b = [
        c["headers"] for c in world.calls() if c["tool"] == "curl" and "api.cloudflare" in c["url"]
    ]
    world.reset_log()
    world.port("rediacc_ci.ops.apply_cf_redirect_rules", ["--dry-run"], env)
    heads_p = [
        c["headers"] for c in world.calls() if c["tool"] == "curl" and "api.cloudflare" in c["url"]
    ]
    assert heads_b == heads_p
    assert heads_p[0] == ["X-Auth-Email: e@x", "X-Auth-Key: gk"]


def test_delta_the_create_request_is_a_single_rule_object(world: h.World) -> None:
    created = {
        "method": "POST",
        "match": "/rulesets/RS1/rules",
        "body": {"success": True, "result": {"rules": [{"id": "new-id"}]}},
    }
    world.set_routes(routes([], (created,)))
    env = world.env(**ENV)
    rc_b, _, _ = world.bash("scripts/ops/apply-cf-redirect-rules.sh", [], env)
    post_b = next(c for c in world.calls() if c["method"] == "POST")["body"]
    assert rc_b == 0
    assert list(json.loads(post_b)) == ["rules"]
    world.reset_log()
    rc_p, out_p, _ = world.port("rediacc_ci.ops.apply_cf_redirect_rules", [], env)
    post_p = json.loads(next(c for c in world.calls() if c["method"] == "POST")["body"])
    assert rc_p == 0
    assert "created apex redirect rule id=new-id" in out_p
    assert "rules" not in post_p
    assert post_p["action"] == "redirect"
    assert post_p["action_parameters"]["from_value"]["status_code"] == 301
    assert post_p["action_parameters"]["from_value"]["preserve_query_string"] is True
    assert post_p["expression"] == APEX_EXPR
    assert post_p["description"] == "Redirect from root to WWW"


def test_delta_a_refusal_shows_cloudflares_message(world: h.World) -> None:
    denied = {
        "method": "GET",
        "match": "/rulesets",
        "body": {"success": False, "errors": [{"message": "Authentication error"}]},
    }
    world.set_routes([denied])
    rc_p, _, err_p = world.port("rediacc_ci.ops.apply_cf_redirect_rules", [], world.env(**ENV))
    assert rc_p == 1
    assert "Authentication error" in err_p


def test_delta_a_failing_advisory_does_not_fail_the_run(world: h.World) -> None:
    broken = {"method": "GET", "match": "/dns_records", "rc": 22}
    world.set_routes(routes([RULE], (broken,)))
    env = world.env(**ENV)
    rc_b, _, _ = world.bash("scripts/ops/apply-cf-redirect-rules.sh", [], env)
    assert rc_b == 22  # the control
    rc_p, out_p, _ = world.port("rediacc_ci.ops.apply_cf_redirect_rules", [], env)
    assert rc_p == 0
    assert "console.rediacc.com -> lookup failed" in out_p


def test_delta_two_matching_rulesets_are_refused(world: h.World) -> None:
    two = {
        "method": "GET",
        "match": "/rulesets",
        "body": {
            "success": True,
            "result": [
                {"id": "A", "phase": "http_request_dynamic_redirect"},
                {"id": "B", "phase": "http_request_dynamic_redirect"},
            ],
        },
    }
    world.set_routes([two])
    rc_p, _, err_p = world.port("rediacc_ci.ops.apply_cf_redirect_rules", [], world.env(**ENV))
    assert rc_p == 1
    assert "more than one http_request_dynamic_redirect ruleset" in err_p
