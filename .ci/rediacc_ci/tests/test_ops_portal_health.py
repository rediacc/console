"""`rediacc_ci.ops.portal_health` against a fake HTTP layer: no request leaves the process.

Each case hands `run` a `fetch` that answers from a dict keyed by URL, so the verdict, the printed lines and the exit code are asserted without the network. The cases that must go RED are the point: a probe that cannot fail is not a probe.
"""

from __future__ import annotations

import io
import json

import pytest

from rediacc_ci.ops import portal_health as ph
from rediacc_ci.well_known import ACCOUNT_DEFAULT_ORIGIN

LOGIN_HTML = (
    b"<!doctype html><html><head>"
    b'<script type="module" crossorigin src="/account/assets/index-AbC123.js"></script>'
    b'<link rel="stylesheet" crossorigin href="/account/assets/index-Def456.css">'
    b'<link rel="modulepreload" href="/account/assets/index-AbC123.js">'
    b'<link rel="icon" href="/account/favicon.svg">'
    b"</head><body><div id=root></div></body></html>"
)
REGIONS = [
    {"id": "eu", "domain": "eu.example.test", "edgeDomain": "edge-eu.example.test"},
    {"id": "us", "domain": "us.example.test", "edgeDomain": "edge-us.example.test"},
]


def _site(host: str, **override: ph.Response) -> dict[str, ph.Response]:
    base = "https://%s" % host
    site = {
        base + "/account/login": ph.Response(200, "text/html; charset=utf-8", LOGIN_HTML),
        base + "/account/assets/index-AbC123.js": ph.Response(200, "text/javascript"),
        base + "/account/assets/index-Def456.css": ph.Response(200, "text/css"),
        base + "/account/api/v1/health": ph.Response(
            200, "application/json", json.dumps({"status": "ok", "timestamp": "t"}).encode()
        ),
    }
    for path, response in override.items():
        site[base + path] = response
    return site


def _fetcher(site: dict[str, ph.Response], seen: list[str]):
    def fetch(url: str) -> ph.Response:
        seen.append(url)
        return site.get(url, ph.Response(404, "text/html"))

    return fetch


def _check(host: str, site: dict[str, ph.Response]) -> tuple[list[ph.Probe], list[str]]:
    seen: list[str] = []
    return ph.check_host(host, _fetcher(site, seen)), seen


def test_a_healthy_portal_is_green_and_every_referenced_asset_is_fetched_once() -> None:
    probes, seen = _check("eu.example.test", _site("eu.example.test"))
    assert all(p.ok for p in probes), probes
    assert seen == [
        "https://eu.example.test/account/login",
        "https://eu.example.test/account/assets/index-AbC123.js",
        "https://eu.example.test/account/assets/index-Def456.css",
        "https://eu.example.test/account/api/v1/health",
    ]


def test_the_favicon_is_not_an_asset() -> None:
    assert ph.asset_paths(LOGIN_HTML.decode()) == [
        "/account/assets/index-AbC123.js",
        "/account/assets/index-Def456.css",
    ]


@pytest.mark.parametrize(
    ("path", "response", "why"),
    [
        ("/account/login", ph.Response(503, "text/html"), "expected 200"),
        ("/account/login", ph.Response(200, "application/json", b"{}"), "not HTML"),
        ("/account/assets/index-Def456.css", ph.Response(404, "text/html"), "expected 200"),
        ("/account/api/v1/health", ph.Response(500, "application/json"), "expected 200"),
        (
            "/account/api/v1/health",
            ph.Response(200, "application/json", b'{"status":"degraded"}'),
            "status is not ok",
        ),
        ("/account/api/v1/health", ph.Response(200, "text/html", b"<html>"), "status is not ok"),
        ("/account/api/v1/health", ph.Response(0, error="URLError"), "URLError"),
    ],
)
def test_each_broken_piece_is_red(path: str, response: ph.Response, why: str) -> None:
    probes, _ = _check("eu.example.test", _site("eu.example.test", **{path: response}))
    red = [p for p in probes if not p.ok]
    assert red, "a broken %s was reported green" % path
    assert any(p.url.endswith(path) and p.why == why for p in red), red


def test_a_login_page_with_no_asset_is_red_not_vacuously_green() -> None:
    bare = ph.Response(200, "text/html", b"<html><body>maintenance</body></html>")
    probes, _ = _check("eu.example.test", _site("eu.example.test", **{"/account/login": bare}))
    assert any(not p.ok and "references no" in p.why for p in probes)


def test_hosts_by_target_and_region() -> None:
    assert ph.hosts("stable", None, REGIONS) == ["eu.example.test", "us.example.test"]
    assert ph.hosts("edge", "us", REGIONS) == ["edge-us.example.test"]
    assert ph.hosts("bench", None) == [ph.BENCH_ORIGIN.removeprefix("https://").rstrip("/")]
    with pytest.raises(ValueError, match="no regions"):
        ph.hosts("bench", "eu")
    with pytest.raises(ValueError, match="unknown region"):
        ph.hosts("stable", "mars", REGIONS)


def test_the_real_regions_file_gives_three_hosts_per_channel() -> None:
    assert len(ph.hosts("stable", None)) == 3
    assert len(ph.hosts("edge", None)) == 3
    assert ph.hosts("stable", "eu") == [ACCOUNT_DEFAULT_ORIGIN.split("://", 1)[1]]


def test_run_prints_url_and_status_only_and_exits_by_verdict() -> None:
    host = ph.hosts("bench", None)[0]
    secret_body = b'{"status":"ok","token":"SENTINEL-must-not-print"}'
    site = _site(
        host, **{"/account/api/v1/health": ph.Response(200, "application/json", secret_body)}
    )
    buf = io.StringIO()
    assert ph.run("bench", None, fetch=_fetcher(site, []), out=buf) == 0
    text = buf.getvalue()
    assert "SENTINEL" not in text
    assert "GREEN, 1 host(s), 4 URL(s), 0 red" in text
    assert "  ok  200  https://%s/account/login" % host in text

    site["https://%s/account/assets/index-AbC123.js" % host] = ph.Response(404)
    buf = io.StringIO()
    assert ph.run("bench", None, fetch=_fetcher(site, []), out=buf) == 1
    assert "RED, 1 host(s), 4 URL(s), 1 red" in buf.getvalue()


def test_main_usage_errors_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert ph.main(["--target", "bench", "--region", "eu"]) == 2
    assert "no regions" in capsys.readouterr().err
