"""What a green `rediacc_ci.deploy.deploy_proxy` smoke does not prove: no executor container started.

Measured on edge v3.0.0 on 2026-11-03: the smoke passed and `cold_start_ms` read normal while every org start was stalled. Both probes below hold that claim to the code, so a smoke that gains a real start probe has to change them and the module docstring together.
"""

from __future__ import annotations

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_proxy as port

URL = "https://proxy.test.example/v1/ready"
CREDENTIAL_FLAGS = {"-H", "--header", "-u", "--user", "--oauth2-bearer"}


def test_the_smoke_sends_no_credential() -> None:
    """Every proxy route past /v1/health and /v1/ready needs a caller's bearer (workers/proxy/src/index.ts `resolveTenant`), so a request with no header stops at a 401 before any pin."""
    for argv in (port.curl_argv(URL), port.curl_body_argv(URL)):
        assert not CREDENTIAL_FLAGS & set(argv), argv


def test_the_ready_route_never_reaches_an_executor() -> None:
    """`/v1/ready` asks the issuer, the account Worker and the cap coordinator. Control: index.ts, which does pin, names the binding this assertion looks for."""
    source = paths.repo_root() / "workers" / "proxy" / "src"
    assert "ORG_EXECUTOR" in (source / "index.ts").read_text()
    assert "ORG_EXECUTOR" not in (source / "ready.ts").read_text()


def test_the_module_says_so() -> None:
    assert "starts no executor container" in (port.__doc__ or "")
