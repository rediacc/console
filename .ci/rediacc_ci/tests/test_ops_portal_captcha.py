"""portal_captcha against an injected HTTP function: no request leaves the process."""

from __future__ import annotations

import io

import pytest

from rediacc_ci.ops import portal_captcha as pc

REGIONS = [
    {"id": "eu", "domain": "eu.rediacc.com", "edgeDomain": "edge-eu.rediacc.com"},
    {"id": "us", "domain": "us.rediacc.com", "edgeDomain": "edge-us.rediacc.com"},
    {"id": "asia", "domain": "asia.rediacc.com", "edgeDomain": "edge-asia.rediacc.com"},
]
KEY = "0x4AAAAAACfixtureKey0001"
PAGE = '<link rel="stylesheet" href="/account/assets/index-x.css"><script src="/account/assets/index-Ab1.js"></script>'
ENFORCED = '{"error":"Captcha verification required"}'


def site(bundle: str, login: str = ENFORCED, page: str = PAGE, calls: list | None = None):
    def fetch(method, url, body):
        if calls is not None:
            calls.append((method, url, body))
        if url.endswith("/account/login"):
            return pc.Reply(200, page)
        if url.endswith("/account/assets/index-Ab1.js"):
            return pc.Reply(200, bundle)
        if url.endswith(pc.LOGIN_API):
            return pc.Reply(400, login)
        return pc.Reply(404)

    return fetch


def test_a_keyed_bundle_is_ok_and_posts_nothing():
    calls: list = []
    verdict = pc.check("eu.rediacc.com", site('a="%s"' % KEY, calls=calls))
    assert verdict.state == pc.OK
    assert all(method == "GET" for method, _, _ in calls)


def test_the_incident_shape_is_broken():
    verdict = pc.check("eu.rediacc.com", site('a=""'))
    assert verdict.state == pc.BROKEN
    assert pc.CAPTCHA_REQUIRED in verdict.why


def test_a_keyless_portal_without_enforcement_is_ok():
    assert pc.check("bench.rediacc.com", site('a=""', login='{"error":"Invalid"}')).state == pc.OK


def test_the_login_post_is_a_dummy_account():
    calls: list = []
    pc.check("eu.rediacc.com", site('a=""', calls=calls))
    posts = [c for c in calls if c[0] == "POST"]
    assert posts == [("POST", "https://eu.rediacc.com" + pc.LOGIN_API, pc.DUMMY_LOGIN)]
    assert pc.DUMMY_LOGIN["email"].endswith(".invalid")


@pytest.mark.parametrize(
    "text",
    [
        # Hex constants of bundled crypto code: never a site key.
        "x=0xffffffffffffffffffff;",
        "x=0x6a09e667f3bcc908b2fb1366;",
        # The Turnstile always-pass TEST key is not a production key.
        "k='1x00000000000000000000AA'",
    ],
)
def test_the_shape_match_ignores_what_is_not_a_turnstile_key(text):
    assert pc.check("eu.rediacc.com", site(text)).state == pc.BROKEN


def test_an_exact_key_must_match_verbatim():
    other = site('a="0x4AAAAAACanotherKey0002"')
    assert pc.check("eu.rediacc.com", other, sitekey=KEY).state == pc.BROKEN
    assert pc.check("eu.rediacc.com", other).state == pc.OK


@pytest.mark.parametrize(
    ("fetch", "needle"),
    [
        (lambda _m, _u, _b: pc.Reply(0, error="URLError"), "URLError"),
        (site("", page="<html>no bundle</html>"), "no /account/assets/index-"),
        (lambda _m, u, _b: pc.Reply(200, PAGE) if u.endswith("/login") else pc.Reply(503), "503"),
    ],
)
def test_what_cannot_be_checked_is_unknown_never_ok(fetch, needle):
    verdict = pc.check("eu.rediacc.com", fetch)
    assert verdict.state == pc.UNKNOWN
    assert needle in verdict.why


def test_retry_stops_at_the_first_ok_and_sleeps_between():
    answers = iter([pc.Reply(0, error="URLError"), pc.Reply(200, PAGE)])
    good = site('a="%s"' % KEY)

    def fetch(method, url, body):
        if url.endswith("/account/login"):
            return next(answers)
        return good(method, url, body)

    slept: list = []
    verdict = pc.check_with_retry("eu.rediacc.com", fetch, attempts=5, sleep=slept.append)
    assert verdict.state == pc.OK
    assert len(slept) == 1


def test_fix_commands_name_the_redeploy_and_the_rollback():
    edge = pc.fix_command("edge-us.rediacc.com", REGIONS)
    assert "release:local -- --channel edge --workers-only --regions us" in edge
    assert "wrangler rollback" in edge
    assert "wrangler.edge-us.toml" in edge
    stable = pc.fix_command("eu.rediacc.com", REGIONS)
    assert "--profile account-secrets-eu-stable" in stable
    assert "VITE_TURNSTILE_SITE_KEY" in stable
    assert "deploy_account --region eu" in stable
    assert "wrangler.eu.toml" in stable
    assert "redeploy other.example" in pc.fix_command("other.example", REGIONS)


def test_run_names_each_red_host_and_its_fix(monkeypatch):
    monkeypatch.setattr(pc.portal_health, "load_regions", lambda: REGIONS)
    bad = site('a=""')
    good = site('a="%s"' % KEY)

    def fetch(method, url, body):
        return (bad if "//us." in url else good)(method, url, body)

    out = io.StringIO()
    monkeypatch.setattr(pc.time, "sleep", lambda _s: None)
    rc = pc.run(["eu.rediacc.com", "us.rediacc.com"], fetch, out)
    text = out.getvalue()
    assert rc == 1
    assert "BROKEN  us.rediacc.com" in text
    assert "fix: " in text
    assert "account-secrets-us-stable" in text
    assert "RED, 2 host(s), 1 red" in text
    assert KEY not in text
    out = io.StringIO()
    assert pc.run(["eu.rediacc.com"], fetch, out) == 0
    assert "GREEN, 1 host(s), 0 red" in out.getvalue()


def test_zero_hosts_is_red():
    out = io.StringIO()
    assert pc.run([], site(""), out) == 1


def test_the_default_hosts_are_the_six_stable_and_edge_hosts():
    assert sorted(pc.default_hosts()) == sorted(
        "%s%s.rediacc.com" % (prefix, region)
        for prefix in ("", "edge-")
        for region in ("eu", "us", "asia")
    )


def test_a_flag_is_a_usage_error():
    assert pc.main(["--bogus"]) == 2
