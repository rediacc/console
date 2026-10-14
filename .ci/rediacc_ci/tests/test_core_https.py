"""`rediacc_ci.core.https`: the scheme check that stands in for a per-call S310 marker.

Every case drives the real `check_url`, `build_request` and `urlopen`. The open case talks to a real loopback server this file starts, so a `urlopen` that skipped the check, or that always refused, fails here.
"""

from __future__ import annotations

import http.server
import threading
import urllib.error

import pytest

from rediacc_ci.core import https
from rediacc_ci.drills import wire


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com",
        "//example.com/x",
        "https:///nohost",
    ],
)
def test_a_scheme_that_is_not_http_or_https_is_refused_in_every_mode(url):
    for mode in ("never", "loopback", "any"):
        with pytest.raises(urllib.error.URLError):
            https.check_url(url, http=mode)


def test_https_is_always_admitted():
    assert https.check_url("https://example.com/a?b=1") == "https://example.com/a?b=1"


@pytest.mark.parametrize(
    ("url", "mode", "admitted"),
    [
        ("http://example.com/", "never", False),
        ("http://example.com/", "loopback", False),
        ("http://example.com/", "any", True),
        ("http://127.0.0.1:8080/", "never", False),
        ("http://127.0.0.1:8080/", "loopback", True),
        ("http://localhost/", "loopback", True),
        ("http://[::1]:9/", "loopback", True),
        ("http://127.0.0.1.evil.example/", "loopback", False),
    ],
)
def test_plain_http_follows_the_mode(url, mode, admitted):
    if admitted:
        assert https.check_url(url, http=mode) == url
    else:
        with pytest.raises(urllib.error.URLError):
            https.check_url(url, http=mode)


def test_build_request_carries_data_headers_and_method_after_the_check():
    request = https.build_request(
        "https://example.com/x", data=b"{}", headers={"X-A": "1"}, method="POST"
    )
    assert request.full_url == "https://example.com/x"
    assert request.data == b"{}"
    assert request.get_method() == "POST"
    assert request.get_header("X-a") == "1"
    with pytest.raises(urllib.error.URLError):
        https.build_request("file:///etc/passwd")


def test_urlopen_reads_a_loopback_server_only_when_the_mode_allows_it():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"pong")

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = "http://127.0.0.1:%d/" % server.server_address[1]
        with pytest.raises(urllib.error.URLError, match="may not open"):
            https.urlopen(url, timeout=5)
        with https.urlopen(url, timeout=5, http="loopback") as response:
            assert response.read() == b"pong"
        request = https.build_request(url, http="loopback")
        with https.urlopen(request, timeout=5, http="loopback") as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_redirect_is_followed_only_to_a_url_the_same_mode_admits():
    """Review 1bf85a71.1: the first URL passed the check, and urllib's default handler then followed a 3xx to `http://` or `ftp://` unchecked."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            targets = {
                "/to-plain-http": "http://example.invalid/x",
                "/to-ftp": "ftp://example.invalid/x",
                "/to-loopback": "/final",
            }
            if self.path in targets:
                self.send_response(302)
                self.send_header("Location", targets[self.path])
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"final")

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = "http://127.0.0.1:%d" % server.server_address[1]
        for path in ("/to-plain-http", "/to-ftp"):
            with pytest.raises(urllib.error.URLError, match="may not open"):
                https.urlopen(base + path, timeout=5, http="loopback")
        # CONTROL: a redirect the mode admits is still followed.
        with https.urlopen(base + "/to-loopback", timeout=5, http="loopback") as response:
            assert response.read() == b"final"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_a_drill_request_does_not_follow_a_redirect_to_ftp():
    """Review 1bf85a71.2: `wire.http_bytes` and the drill client built their own opener, so only the first URL was checked; both now open through `https.build_opener`."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/to-ftp":
                self.send_response(302)
                self.send_header("Location", "ftp://example.invalid/x")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = "http://127.0.0.1:%d" % server.server_address[1]
        with pytest.raises(OSError, match="may not open"):
            wire.http_bytes("GET", base + "/to-ftp")
        # CONTROL: a plain request through the same function still answers.
        assert wire.http_bytes("GET", base + "/") == (200, b"ok")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
