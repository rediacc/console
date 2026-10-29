"""portal_captcha against an injected HTTP function: no request leaves the process."""

from __future__ import annotations

import io
import shlex
import subprocess
from urllib.parse import urlparse

import pytest

from rediacc_ci.ops import portal_captcha as pc
from rediacc_ci.well_known import ACCOUNT_DEFAULT_ORIGIN, BENCH_ORIGIN

REGIONS = pc.portal_health.load_regions()
_BY_ID = {region["id"]: region for region in REGIONS}
EU = urlparse(ACCOUNT_DEFAULT_ORIGIN).netloc
BENCH = urlparse(BENCH_ORIGIN).netloc
# Read with .get so a regions.json without `us` fails the cases that use it, not the collection of every case in this module (review 599bb20a.1).
US = _BY_ID.get("us", {}).get("domain", "")
EDGE_US = _BY_ID.get("us", {}).get("edgeDomain", "")


def _need_us():
    if not (US and EDGE_US):
        pytest.fail("regions.json has no `us` region with a domain and an edgeDomain")


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
    verdict = pc.check(EU, site('a="%s"' % KEY, calls=calls))
    assert verdict.state == pc.OK
    assert all(method == "GET" for method, _, _ in calls)


def test_the_incident_shape_is_broken():
    verdict = pc.check(EU, site('a=""'))
    assert verdict.state == pc.BROKEN
    assert pc.CAPTCHA_REQUIRED in verdict.why


def test_a_keyless_portal_without_enforcement_is_ok():
    assert pc.check(BENCH, site('a=""', login='{"error":"Invalid"}')).state == pc.OK


def test_the_login_post_is_a_dummy_account():
    calls: list = []
    pc.check(EU, site('a=""', calls=calls))
    posts = [c for c in calls if c[0] == "POST"]
    assert posts == [("POST", ACCOUNT_DEFAULT_ORIGIN + pc.LOGIN_API, pc.DUMMY_LOGIN)]
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
    assert pc.check(EU, site(text)).state == pc.BROKEN


def test_an_exact_key_must_match_verbatim():
    other = site('a="0x4AAAAAACanotherKey0002"')
    assert pc.check(EU, other, sitekey=KEY).state == pc.BROKEN
    assert pc.check(EU, other).state == pc.OK


@pytest.mark.parametrize(
    ("fetch", "needle"),
    [
        (lambda _m, _u, _b: pc.Reply(0, error="URLError"), "URLError"),
        (site("", page="<html>no bundle</html>"), "no /account/assets/index-"),
        (lambda _m, u, _b: pc.Reply(200, PAGE) if u.endswith("/login") else pc.Reply(503), "503"),
    ],
)
def test_what_cannot_be_checked_is_unknown_never_ok(fetch, needle):
    verdict = pc.check(EU, fetch)
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
    verdict = pc.check_with_retry(EU, fetch, attempts=5, sleep=slept.append)
    assert verdict.state == pc.OK
    assert len(slept) == 1


def test_fix_commands_name_the_redeploy_and_the_rollback():
    _need_us()
    edge = pc.fix_command(EDGE_US, REGIONS)
    assert "release:local -- --channel edge --workers-only --regions us" in edge
    assert "wrangler rollback" in edge
    assert "wrangler.edge-us.toml" in edge
    stable = pc.fix_command(EU, REGIONS)
    assert "--profile account-secrets-eu-stable" in stable
    assert "VITE_TURNSTILE_SITE_KEY" in stable
    assert "deploy_account --region eu" in stable
    assert "wrangler.eu.toml" in stable
    assert "redeploy other.example" in pc.fix_command("other.example", REGIONS)


def test_run_names_each_red_host_and_its_fix(monkeypatch):
    _need_us()
    monkeypatch.setattr(pc.portal_health, "load_regions", lambda: REGIONS)
    bad = site('a=""')
    good = site('a="%s"' % KEY)

    def fetch(method, url, body):
        return (bad if "//" + US in url else good)(method, url, body)

    out = io.StringIO()
    monkeypatch.setattr(pc.time, "sleep", lambda _s: None)
    rc = pc.run([EU, US], fetch, out)
    text = out.getvalue()
    assert rc == 1
    assert "BROKEN  " + US in text
    assert "fix: " in text
    assert "account-secrets-us-stable" in text
    assert "RED, 2 host(s), 1 red" in text
    assert KEY not in text
    out = io.StringIO()
    assert pc.run([EU], fetch, out) == 0
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


def test_the_stable_fix_command_binds_the_key_without_quote_characters(tmp_path):
    """Review 760ca2d1.1: the printed stable fix runs as written. Its `sh -c` script is run here by a real sh, with `npx` and `python3` stubbed on PATH, and the key `npx vite build` sees must be the bare key, not one wrapped in literal quotes."""
    words = shlex.split(pc.fix_command(EU, REGIONS).split("; or roll back")[0])
    inner = words[words.index("-c") + 1]
    (tmp_path / "private" / "account" / "web").mkdir(parents=True)
    stubs = tmp_path / "bin"
    stubs.mkdir()
    seen = tmp_path / "seen"
    for name in ("npx", "python3"):
        stub = stubs / name
        stub.write_text(
            '#!/bin/sh\nprintf "%%s|%%s\\n" "%s" "$VITE_TURNSTILE_SITE_KEY" >> "%s"\n'
            % (name, seen)
        )
        stub.chmod(0o755)
    env = {"PATH": "%s:/usr/bin:/bin" % stubs, "TURNSTILE_SITE_KEY": KEY, "HOME": str(tmp_path)}
    proc = subprocess.run(
        ["sh", "-c", inner],
        check=False,
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert seen.read_text().splitlines()[0] == "npx|%s" % KEY


def test_a_bundle_with_another_key_is_named_as_such():
    """Review 760ca2d1.2: a bundle carrying a key other than the deployed one is BROKEN under an enforcing Worker, and the line says a different key is there. CONTROL: a keyless bundle keeps the "carries no" line."""
    other = site('a="0x4AAAAAACotherKey99999"')
    verdict = pc.check(EU, other, KEY)
    assert verdict.state == pc.BROKEN
    assert "different Turnstile site key" in verdict.why
    keyless = pc.check(EU, site('a=""'), KEY)
    assert keyless.state == pc.BROKEN
    assert "carries no Turnstile site key" in keyless.why
