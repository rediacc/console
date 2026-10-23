"""telemetry_delivery against fake HTTP servers on loopback: hosts and Grafana."""

from __future__ import annotations

import io
import json
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.ops import telemetry_delivery as td

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

TOKEN = "glsa_SECRET_TOKEN_VALUE"


class Fake:
    """One loopback server playing every account host (by path prefix) and Grafana."""

    def __init__(
        self,
        silent: AbstractSet[tuple[str, str]] = frozenset(),
        down: AbstractSet[str] = frozenset(),
    ):
        self.silent = silent  # (host, signal)
        self.down = down
        self.probes: dict[str, str] = {}  # probe id -> host
        self.auth: list[str] = []
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=b"{}"):
                self.send_response(code)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                qs = urllib.parse.parse_qs(parts.query)
                if parts.path.startswith("/host/"):
                    host = parts.path.split("/")[2]
                    if host in fake.down:
                        return self._send(503)
                    fake.probes[self.headers[td.PROBE_HEADER] or ""] = host
                    return self._send(200, b'{"status":"ok"}')
                fake.auth.append(self.headers.get("Authorization", ""))
                if "/uid/tempo/" in parts.path:
                    pid = qs["tags"][0].split("=", 1)[1]
                    seen_host = fake.probes.get(pid)
                    if seen_host and (seen_host, "traces") not in fake.silent:
                        return self._send(200, b'{"traces":[{"traceID":"a"}]}')
                    return self._send(200, b'{"traces":[]}')
                if "/uid/loki/" in parts.path:
                    pid = qs["query"][0].split('"')[-2]
                    seen_host = fake.probes.get(pid)
                    if seen_host and (seen_host, "logs") not in fake.silent:
                        body = {"status": "success", "data": {"result": [{"values": [["1", "x"]]}]}}
                    else:
                        body = {"status": "success", "data": {"result": []}}
                    return self._send(200, json.dumps(body).encode())
                return self._send(404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.origin = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


HOSTS = ["eu.example", "bench.example"]


def drive(fake: Fake, hosts=HOSTS, timeout_s=0.3):
    out = io.StringIO()
    rc = td.run(
        hosts,
        td.make_get("loopback"),
        fake.origin,
        TOKEN,
        timeout_s=timeout_s,
        interval_s=0.05,
        base_for=lambda h: "%s/host/%s" % (fake.origin, h),
        out=out,
    )
    return rc, out.getvalue()


@pytest.fixture
def make_fake():
    made: list[Fake] = []

    def make(**kw):
        f = Fake(**kw)
        made.append(f)
        return f

    yield make
    for f in made:
        f.close()


def test_every_signal_delivered_passes(make_fake):
    rc, text = drive(make_fake())
    assert rc == 0, text
    assert text.splitlines()[:4] == [
        "PASS eu.example traces",
        "PASS eu.example logs",
        "PASS bench.example traces",
        "PASS bench.example logs",
    ]
    assert "SILENT" not in text


def test_missing_trace_is_silent_and_exits_1(make_fake):
    rc, text = drive(make_fake(silent={("bench.example", "traces")}))
    assert rc == 1
    assert "SILENT bench.example traces" in text
    assert "PASS bench.example logs" in text
    assert "PASS eu.example traces" in text


def test_missing_log_is_silent_and_exits_1(make_fake):
    rc, text = drive(make_fake(silent={("eu.example", "logs")}))
    assert rc == 1
    assert "SILENT eu.example logs" in text
    assert "PASS eu.example traces" in text


def test_unanswered_probe_makes_both_signals_silent(make_fake):
    rc, text = drive(make_fake(down={"eu.example"}))
    assert rc == 1
    assert "SILENT eu.example traces (probe answered 503)" in text
    assert "SILENT eu.example logs (probe answered 503)" in text


def test_token_is_a_header_only_and_never_printed(make_fake):
    fake = make_fake()
    rc, text = drive(fake)
    assert rc == 0, text
    assert TOKEN not in text
    assert fake.auth
    assert all(a == "Bearer %s" % TOKEN for a in fake.auth)
    assert all(TOKEN not in a for a in sys.argv)


def test_main_without_token_exits_2_and_prints_no_secret(monkeypatch, capsys):
    monkeypatch.delenv(td.READ_CREDENTIAL_ENV, raising=False)
    assert td.main([]) == 2
    assert td.READ_CREDENTIAL_ENV in capsys.readouterr().err


def test_main_never_echoes_token_even_when_hosts_fail(monkeypatch, capsys):
    monkeypatch.setenv(td.READ_CREDENTIAL_ENV, TOKEN)
    monkeypatch.setattr(td, "all_hosts", lambda: (_ for _ in ()).throw(ValueError(TOKEN)))
    assert td.main([]) == 2
    cap = capsys.readouterr()
    assert TOKEN not in cap.out + cap.err


def test_all_hosts_is_stable_edge_and_bench():
    regions = [
        {"id": "eu", "domain": "eu.d", "edgeDomain": "edge-eu.d"},
        {"id": "us", "domain": "us.d", "edgeDomain": "edge-us.d"},
    ]
    hosts = td.all_hosts(regions)
    assert hosts[:4] == ["eu.d", "us.d", "edge-eu.d", "edge-us.d"]
    assert len(hosts) == 5
    assert hosts[4].startswith("bench")


def test_loki_and_tempo_need_real_results():
    assert not td.tempo_has(td.Reply(200, b'{"traces":[]}'))
    assert not td.tempo_has(td.Reply(500, b'{"traces":[1]}'))
    assert not td.loki_has(td.Reply(200, b"not json"))
    assert not td.loki_has(td.Reply(200, b'{"status":"success","data":{"result":[{"values":[]}]}}'))


def test_unanswered_probe_is_not_polled(make_fake):
    fake = make_fake(down={"eu.example"})
    rc, _ = drive(fake, hosts=["eu.example"])
    assert rc == 1
    assert fake.auth == []
