"""`rediacc_ci.core.curl_stdin`, and every Cloudflare or Linode curl call site that routes through it: a credential header reaches curl on stdin and never on argv (worklist #a2d19f74).

The call-site cases replace each module's `subprocess.run` with a recorder, drive the one function that starts curl with a SENTINEL credential, and assert the sentinel is in no argv and is in the recorded stdin. Nothing reaches a network: the one real curl case talks to a loopback server this test starts.
"""

from __future__ import annotations

import contextlib
import http.server
import shutil
import subprocess
import threading
import types
import typing

import pytest

from rediacc_ci.core import curl_stdin
from rediacc_ci.deploy import cf_purge_urls, purge_media_cache
from rediacc_ci.housekeeping import cleanup_cf_preview, cleanup_versions
from rediacc_ci.ops import apply_cf_redirect_rules, cf_auth, linode_cluster_validation

SENTINEL = "SENTINEL-credential-5e7a"
BEARER = ["-H", "Authorization: Bearer %s" % SENTINEL]


def test_credential_headers_move_to_one_stdin_config() -> None:
    argv = [
        "curl",
        "-s",
        "-H",
        "X-Auth-Email: e@x",
        "-H",
        'X-Auth-Key: k"\\',
        "-H",
        "Accept: a",
        "u",
    ]
    out, config = curl_stdin.stdin_headers(argv)
    assert out == ["curl", "-s", "-K", "-", "-H", "Accept: a", "u"]
    assert config == 'header = "X-Auth-Email: e@x"\nheader = "X-Auth-Key: k\\"\\\\"\n'
    assert curl_stdin.argv_with_config(out, config) == argv, "the inverse restores the request"


def test_an_argv_without_a_credential_is_unchanged() -> None:
    argv = ["curl", "-sI", "https://example.invalid/", "-H", "Accept: a"]
    assert curl_stdin.stdin_headers(argv) == (argv, None)
    assert curl_stdin.argv_with_config(argv, "") == argv


def test_an_argv_that_already_reads_stdin_is_refused() -> None:
    with pytest.raises(ValueError, match="already reads stdin"):
        curl_stdin.stdin_headers(["curl", *BEARER, "--data", "@-", "u"])


@pytest.mark.skipif(shutil.which("curl") is None, reason="curl is not installed")
def test_real_curl_sends_the_header_from_its_stdin_config() -> None:
    """The mechanism itself, against real curl and a loopback server: the header named in the `-K -` config arrives, byte for byte, and the argv curl ran with never held it."""
    seen: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append(self.headers.get("Authorization", ""))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    try:
        url = "http://127.0.0.1:%d/" % server.server_address[1]
        argv, config = curl_stdin.stdin_headers(["curl", "-sS", *BEARER, url])
        assert not any(SENTINEL in arg for arg in argv)
        proc = subprocess.run(
            argv, input=config, capture_output=True, text=True, check=False, timeout=30
        )
        thread.join(timeout=30)
    finally:
        server.server_close()
    assert proc.returncode == 0, proc.stderr
    assert seen == ["Bearer %s" % SENTINEL]


class _Recorder:
    def __init__(self, stdout: str | bytes) -> None:
        self.stdout = stdout
        self.calls: list[tuple[list[str], object]] = []

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw.get("input")))
        return subprocess.CompletedProcess(argv, 0, stdout=self.stdout, stderr="")


def _drive(module, monkeypatch: pytest.MonkeyPatch, call, stdout: str | bytes = "{}") -> _Recorder:
    recorder = _Recorder(stdout)
    monkeypatch.setattr(module.subprocess, "run", recorder)
    # The recorded argv is the subject; a parse failure on the fake answer is not.
    with contextlib.suppress(Exception):
        call()
    return recorder


CALL_SITES: dict[str, tuple[types.ModuleType, typing.Callable[[], object], str | bytes]] = {
    "cf_purge_urls": (
        cf_purge_urls,
        lambda: cf_purge_urls._curl(cf_purge_urls.curl_argv("zone", BEARER, "{}")),
        "{}",
    ),
    "purge_media_cache": (
        purge_media_cache,
        lambda: purge_media_cache._curl(purge_media_cache.curl_argv(BEARER)),
        "{}",
    ),
    "cleanup_cf_preview": (
        cleanup_cf_preview,
        lambda: cleanup_cf_preview._substitution(
            cleanup_cf_preview.curl_argv("GET", "/x", SENTINEL), "{}"
        ),
        "{}",
    ),
    "apply_cf_redirect_rules": (
        apply_cf_redirect_rules,
        lambda: apply_cf_redirect_rules._api(BEARER, "GET", "https://api.example.invalid/x"),
        '{"success": true}',
    ),
    "cf_auth": (
        cf_auth,
        lambda: cf_auth.curl_json("GET", "https://api.example.invalid/x", BEARER),
        "{}",
    ),
    "linode_cluster_validation": (
        linode_cluster_validation,
        lambda: linode_cluster_validation.Validation._api_page(
            typing.cast(
                "linode_cluster_validation.Validation", types.SimpleNamespace(token=SENTINEL)
            ),
            "/x",
        ),
        "{}",
    ),
    "cleanup_versions": (
        cleanup_versions,
        lambda: cleanup_versions.Housekeeping.cf_api(
            typing.cast("cleanup_versions.Housekeeping", None), "GET", "/x"
        ),
        b"{}",
    ),
}


@pytest.mark.parametrize("site", sorted(CALL_SITES))
def test_no_call_site_puts_a_credential_on_curl_argv(
    site: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    module, call, stdout = CALL_SITES[site]
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", SENTINEL)
    recorder = _drive(module, monkeypatch, call, stdout)
    curls = [(argv, stdin) for argv, stdin in recorder.calls if argv and argv[0] == "curl"]
    assert curls, "%s started no curl" % site
    for argv, stdin in curls:
        assert not any(SENTINEL in arg for arg in argv), "%s: the credential is on argv" % site
        text = stdin.decode() if isinstance(stdin, bytes) else str(stdin)
        assert SENTINEL in text, "%s: the credential never reached curl's stdin" % site
