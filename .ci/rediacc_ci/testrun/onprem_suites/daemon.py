"""The `daemon` suite: the daemon executor of the stack (PLAN-rmcp-executor-hardening.md, Designs 9 and 16).

It answers `/v1/server-info` as `daemon`, runs `repo list` and a config-writing command for its enrolled config, refuses the token of another org, and keeps the Design 9 bind rules: loopback by default, a non-loopback `--host` refused without TLS and served over HTTPS with a pair. Every scenario here needs the daemon, so none names `bench`.
"""

from __future__ import annotations

import ipaddress
import pathlib
from typing import TYPE_CHECKING

from rediacc_ci.testrun.onprem_suites import Result, failed, passed, scenario

if TYPE_CHECKING:
    from rediacc_ci.testrun.onprem_scenarios import Context

# Ports beside the daemon's own for the bind probes; the runner refuses one that already answers.
REFUSAL_PORT_OFFSET = 11
TLS_PORT_OFFSET = 12
REFUSAL_WAIT_S = 20.0
TLS_POLLS = 60
# The wildcard address, the non-loopback `--host` of the Design 9 probes.
ALL_INTERFACES = str(ipaddress.IPv4Address(0))
EXTRA_MACHINE = "scenario-extra"


def _daemon_url(ctx: Context) -> str:
    return ctx.value("ONPREM_DAEMON_URL")


def _probe_port(ctx: Context, offset: int) -> int | str:
    """The probe port, or the failure text when something already answers there."""
    port = int(ctx.value("ONPREM_DAEMON_PORT")) + offset
    if ctx.port_answers(port):
        return "port %d already answers; the probe needs it free" % port
    return port


@scenario("daemon", "server_info_is_daemon")
def server_info_is_daemon(ctx: Context) -> Result:
    code, body = ctx.http_get(_daemon_url(ctx) + "/v1/server-info")
    if code != 200:
        return failed("GET /v1/server-info answered %d" % code, code)
    if '"mode":"daemon"' not in body.replace(" ", ""):
        return failed("server-info does not name mode daemon: %s" % body[:120], code)
    return passed(code=code)


@scenario("daemon", "repo_list_through_daemon")
def repo_list_through_daemon(ctx: Context) -> Result:
    done = ctx.rdc("repo", "list", token=ctx.token("executor"), proxy=_daemon_url(ctx))
    if done.returncode != 0:
        return failed(
            "proxied repo list exited %d: %s" % (done.returncode, done.stderr.strip()[-200:]),
            done.returncode,
        )
    return passed(code=done.returncode)


@scenario("daemon", "config_write_through_daemon")
def config_write_through_daemon(ctx: Context) -> Result:
    token, proxy = ctx.token("executor"), _daemon_url(ctx)
    added = ctx.rdc(
        "machine",
        "add",
        EXTRA_MACHINE,
        "--ip",
        "127.0.0.1",
        "--user",
        "root",
        token=token,
        proxy=proxy,
    )
    if added.returncode != 0:
        return failed(
            "proxied machine add exited %d: %s" % (added.returncode, added.stderr.strip()[-200:]),
            added.returncode,
        )
    listed = ctx.rdc("--output", "json", "machine", "list", token=token, proxy=proxy)
    removed = ctx.rdc("machine", "remove", EXTRA_MACHINE, "--yes", token=token, proxy=proxy)
    if listed.returncode != 0 or EXTRA_MACHINE not in listed.stdout:
        return failed(
            "the written machine is not in the next proxied machine list", listed.returncode
        )
    if removed.returncode != 0:
        return failed(
            "proxied machine remove exited %d: %s"
            % (removed.returncode, removed.stderr.strip()[-200:]),
            removed.returncode,
        )
    return passed(code=0)


@scenario("daemon", "other_org_token_refused")
def other_org_token_refused(ctx: Context) -> Result:
    proxy = _daemon_url(ctx)
    own = ctx.rdc("repo", "list", token=ctx.token("executor"), proxy=proxy)
    if own.returncode != 0:
        return failed(
            "the control (own org) exited %d, so a refusal below proves nothing" % own.returncode,
            own.returncode,
        )
    other = ctx.rdc("repo", "list", token=ctx.token("other"), proxy=proxy)
    if other.returncode == 0:
        return failed("the token of another org was served", other.returncode)
    return passed("refused with exit %d" % other.returncode, other.returncode)


@scenario("daemon", "default_bind_is_loopback")
def default_bind_is_loopback(ctx: Context) -> Result:
    port = ctx.value("ONPREM_DAEMON_PORT")
    done = ctx.exec(["lsof", "-nP", "-iTCP:%s" % port, "-sTCP:LISTEN"])
    if done.returncode != 0:
        return failed(
            "lsof found no listener on port %s: %s" % (port, done.stderr.strip()[-120:]),
            done.returncode,
        )
    if "127.0.0.1:%s" % port not in done.stdout or "*:%s" % port in done.stdout:
        return failed(
            "the daemon does not listen on 127.0.0.1 only: %s" % done.stdout.strip()[-200:],
            done.returncode,
        )
    return passed(code=done.returncode)


@scenario("daemon", "non_loopback_host_without_tls_refused")
def non_loopback_host_without_tls_refused(ctx: Context) -> Result:
    port = _probe_port(ctx, REFUSAL_PORT_OFFSET)
    if isinstance(port, str):
        return failed(port)
    code, pgid = ctx.serve_probe(
        ["--mode", "daemon", "--host", ALL_INTERFACES, "--port", str(port)],
        ctx.token("executor"),
        REFUSAL_WAIT_S,
    )
    if code is None:
        ctx.stop(pgid)
        return failed("--host 0.0.0.0 without TLS kept serving instead of refusing")
    if code == 0:
        return failed("--host 0.0.0.0 without TLS exited 0", code)
    return passed("refused with exit %d" % code, code)


@scenario("daemon", "non_loopback_host_with_tls_serves_https")
def non_loopback_host_with_tls_serves_https(ctx: Context) -> Result:
    port = _probe_port(ctx, TLS_PORT_OFFSET)
    if isinstance(port, str):
        return failed(port)
    directory = pathlib.Path(ctx.value("ONPREM_DAEMON_HOME"))
    cert, key = directory / "probe-cert.pem", directory / "probe-key.pem"
    made = ctx.exec(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ]
    )
    if made.returncode != 0:
        return failed(
            "openssl could not make the throwaway pair: %s" % made.stderr.strip()[-120:],
            made.returncode,
        )
    code, pgid = ctx.serve_probe(
        [
            "--mode",
            "daemon",
            "--host",
            ALL_INTERFACES,
            "--port",
            str(port),
            "--tls-cert",
            str(cert),
            "--tls-key",
            str(key),
        ],
        ctx.token("executor"),
        1.0,
    )
    try:
        for _ in range(TLS_POLLS):
            if code is not None:
                return failed(
                    "the daemon with a TLS pair exited %d instead of serving" % code, code
                )
            status, body = ctx.http_get(
                "https://127.0.0.1:%d/v1/server-info" % port, insecure_tls=True
            )
            if status == 200:
                if "daemon" not in body:
                    return failed(
                        "HTTPS server-info does not name the daemon: %s" % body[:120], status
                    )
                plain, _ = ctx.http_get("http://127.0.0.1:%d/v1/server-info" % port)
                if plain == 200:
                    return failed("the TLS port also answered plain HTTP", plain)
                return passed(code=status)
            ctx.sleep(1.0)
            code = ctx.exited(pgid)
        return failed("the TLS daemon never answered over HTTPS on port %d" % port)
    finally:
        ctx.stop(pgid)
