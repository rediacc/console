"""The proxy Worker routes a real request into its real container under `wrangler dev` (agent/plans/PLAN-cloudflare-proxy.md box A6, missing test 5).

WHY. The Worker half (workers/proxy/src/__tests__) is unit-tested against mocks, and the image half is proven by check:ci-proxy-image-smoke, which boots the executor image with plain `docker run`. Nothing ran the two TOGETHER: the Worker's Durable Object asking the Containers runtime to start the image, and the request it forwards arriving at `rdc serve --mode container` inside it. That seam is where a wrong `defaultPort`, an `envVars` that never reaches the container, or a `[[containers]]` block that no longer builds would show, and before this gate it showed only after a deploy.

WHAT IT DOES. `wrangler dev --config workers/proxy/wrangler.dev.toml --config <scratch>/stub-issuer.toml`, which builds `workers/proxy/Dockerfile` on the local docker host and runs the Worker in workerd next to a STUB ISSUER Worker, with:

  - ACCOUNT_URL pointed at a fake account server this process runs on loopback. wrangler.dev.toml
    carries no `[[services]] ACCOUNT` binding (`rediacc-account-eu` is not resolvable under
    `wrangler dev`), so src/index.ts falls back to `fetch(ACCOUNT_URL)`;
  - the ISSUER binding resolved to the stub issuer, a Worker this process writes into its scratch
    directory per run. Its `ExecutorIssuer` entrypoint carries the account Worker's three RPCs
    (agent/plans/PLAN-console-executor-multi-org.md, Design items 1 and 2): `route(bearer)` asks the
    fake account who the bearer is and answers `{ orgId }` for the caller or a refusal for a
    stranger; `issue(orgId)` answers a random throwaway token, the run's "issued" token, with a
    45-minute expiry; `probe()` answers `{ ok, scopes, ttlMs }` and writes nothing. Route, issue
    and probe are recorded at the fake, so what the Worker asked the issuer is observable. The token
    lives only in the scratch directory, so nothing can be left in the tree. That `wrangler dev`
    with two configs resolves a named-entrypoint binding was measured on 2026-10-25 with wrangler
    4.152.0 (the plan's U5).

and then four requests through the Worker, in this order:

  0. GET /v1/ready, unauthenticated: 200 `{ready: true}` with a non-empty `workerVersion`, after the
     Worker called the stub's `probe()` and asked the fake account for server-info, with no `issue()`
     call (readiness mints nothing) and no container started;
  1. NO BEARER on `GET /v1/server-info`: 401, the account server is never asked, and no container
     is started;
  2. A STRANGER's bearer, which the stub's `route()` is refused by the fake account: 401, the Worker
     DID ask `route()` (so the refusal is the account side's verdict), no token is issued, and no
     container is started;
  3. THE CALLER's bearer, which `route()` answers with the caller's org: 200 with
     `mode: "container"` and a `cliVersion` equal to `node cli-bundle.cjs --version` of the bundle
     staged into the image; then GET /v1/jobs/<id>/events with the same bearer answers 400 (the
     executor authenticated it, then refused the missing `machine` query), which makes the executor
     introspect the caller through the Worker's egress; the stub issuer was asked to `issue()` for that org (the token is keyed by
     org) and the executor's own introspection reached the fake account carrying it, and a
     `workerd-rediacc-proxy-dev-*` container now exists.

The refusals come before the 200, because after it a container exists and "no container was started" could no longer be read. The `cliVersion` equality is what proves the 200 came from the executor inside the image rather than from anything else answering on the port. An introspection that carries anything but the stub's issued token gets 401 from the fake account, and only the stub records route, issue and probe calls, so the observations also prove the ISSUER binding reached the stub.

WHY wrangler.dev.toml IS ALSO CHECKED STATICALLY. A dev config that drifts from the deployed eu config would make this gate prove the wrong Worker. Before any docker work the gate requires the dev config to equal the deployed `wrangler.eu.toml` of the working tree, the compatibility date and flags, `[[containers]]`, the Durable Object bindings and the migrations; to carry exactly one `[[services]]`, ISSUER on the stub issuer's `ExecutorIssuer` entrypoint; to carry the `[version_metadata]` binding `/v1/ready` reads; and to carry no routes.

TEARDOWN, ALWAYS. `wrangler dev` does NOT remove its containers when it exits (measured 2026-10-24, wrangler 4.151.3: both the executor and its `-proxy` sidecar were still up after SIGINT and workerd had exited). So the gate stops wrangler's whole process group, removes every `workerd-rediacc-proxy-dev-*` container that did not exist before the run, removes the dev image tag the build log names, stops the fake server and deletes its temp state, and then LISTS the prefix again: a container that survived teardown is a finding. SIGTERM is turned into an exception for the same reason, so a runner that terminates the gate still reaches the teardown; only SIGKILL can leave a container behind, and the next run names any such leftover loudly before it starts.

THE RENET IT SHIPS. Staged exactly as check:ci-proxy-image-smoke stages it (`proxy_image_smoke._stage_local`, which runs `executor_artifacts stage-local`): an already staged `workers/proxy/stage/manifest.json` is used as is, otherwise the stage is written for the run and removed afterwards.

LOCAL-ONLY AND SLOW. It needs a docker daemon and the Containers runtime of `wrangler dev`, and it builds the executor image (minutes cold, seconds on a warm layer cache). It is registered `local-only` with that BLOCKER in scripts/ci-runner/manifest.ts.

Exit 0 clean, 1 on findings, 2 when the gate's own controls fail, 77 (the pool's CANNOT_RUN, reported `blocked`, never green) when docker or wrangler is absent or no renet can be staged.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import typing
import urllib.error

from rediacc_ci import paths
from rediacc_ci.controls import Checker, controls_first
from rediacc_ci.core import https
from rediacc_ci.deploy import executor_artifacts
from rediacc_ci.quality import proxy_image_smoke
from rediacc_ci.well_known import (
    ACCOUNT_DEFAULT_ORIGIN,
    APEX_DOMAIN,
    PROXY_EU_HOST,
)

WORKER_DIR = ("workers", "proxy")
DEV_CONFIG = "wrangler.dev.toml"
DEPLOY_CONFIG = "wrangler.eu.toml"
WRANGLER_BIN = ("node_modules", ".bin", "wrangler")
# workerd names a dev container `workerd-<worker name>-<class name>-<id>`, and its egress sidecar the same plus `-proxy`. The worker name is wrangler.dev.toml's, which is what scopes this prefix to this gate.
CONTAINER_PREFIX = "workerd-rediacc-proxy-dev-"
INTROSPECT_PATH = "/account/api/v1/proxy/introspect"
PROBE_PATH = "/v1/server-info"
SERVER_INFO_PATH = "/account/api/v1/.well-known/server-info"
# The org the fake account routes the caller to; the stub issuer is asked to issue for exactly this org.
CALLER_ORG = "org-wrangler-dev-e2e"
READY_PATH = "/v1/ready"
# An authenticated executor route that needs no job and no machine: the executor verifies the bearer first, then answers 400 for the missing `machine` query, so a 400 (never a 401) proves the caller was authenticated through the Worker's egress.
AUTH_PATH = "/v1/jobs/wrangler-dev-e2e/events"
AUTH_OK_STATUS = 400
# The stub issuer Worker this gate writes per run, and the one binding wrangler.dev.toml may declare: ISSUER on its ExecutorIssuer entrypoint, as the deployed configs bind the account Worker's.
STUB_ISSUER_NAME = "rediacc-executor-issuer-dev"
ISSUER_BINDING = {"binding": "ISSUER", "service": STUB_ISSUER_NAME, "entrypoint": "ExecutorIssuer"}
VERSION_METADATA_BINDING = "CF_VERSION_METADATA"
STUB_ISSUER_TTL_S = 45 * 60

CANNOT_RUN = 77
READY_TIMEOUT_S = 1800
REQUEST_TIMEOUT_S = 180
SETTLE_S = 3
STOP_GRACE_S = 20

# Keys wrangler.dev.toml must carry exactly as wrangler.toml does, or the gate proves a different Worker.
MIRRORED_KEYS = (
    "main",
    "compatibility_date",
    "compatibility_flags",
    "containers",
    "durable_objects",
    "migrations",
)

_READY_RE = re.compile(r"Ready on (http://[^\s]+)")
_IMAGE_TAG_RE = re.compile(
    r"naming to (?:docker\.io/)?(cloudflare-dev/[a-z0-9._-]+:[A-Za-z0-9._-]+)"
)


# ---------------------------------------------------------------------------------------------
# Pure helpers, exercised by the selftest and by .ci/rediacc_ci/tests/test_proxy_wrangler_dev_e2e.py


def dev_config_findings(dev: dict, deploy: dict) -> list[str]:
    """What is wrong with wrangler.dev.toml (parsed) against wrangler.toml (parsed)."""
    out: list[str] = []
    services = dev.get("services", [])
    if services != [ISSUER_BINDING]:
        out.append(
            "%s declares [[services]] %r; it must declare exactly %r. An ACCOUNT binding is "
            "unresolvable under `wrangler dev` and would stop src/index.ts from using ACCOUNT_URL, "
            "and the ISSUER binding must name the stub issuer this gate runs"
            % (DEV_CONFIG, services, ISSUER_BINDING)
        )
    if dev.get("version_metadata", {}).get("binding") != VERSION_METADATA_BINDING:
        out.append(
            "%s has no [version_metadata] binding = %r; /v1/ready answers 503 without it"
            % (DEV_CONFIG, VERSION_METADATA_BINDING)
        )
    out.extend(
        "%s declares `%s`; a dev config must route nowhere. Delete it" % (DEV_CONFIG, key)
        for key in ("routes", "route")
        if key in dev
    )
    if dev.get("name") == deploy.get("name"):
        out.append(
            "%s reuses the deployed name %r; give it its own, so its containers and images are "
            "never confused with the deployed Worker's" % (DEV_CONFIG, deploy.get("name"))
        )
    elif not CONTAINER_PREFIX.startswith("workerd-%s-" % dev.get("name")):
        out.append(
            "%s is named %r but the gate cleans up containers named %s*; change one to match the other"
            % (DEV_CONFIG, dev.get("name"), CONTAINER_PREFIX)
        )
    out.extend(
        "%s `%s` is %r but %s has %r; copy the deployed value, or this gate proves a different Worker"
        % (DEV_CONFIG, key, dev.get(key), DEPLOY_CONFIG, deploy.get(key))
        for key in MIRRORED_KEYS
        if dev.get(key) != deploy.get(key)
    )
    account = str(dev.get("vars", {}).get("ACCOUNT_URL", ""))
    if APEX_DOMAIN in account:
        out.append(
            "%s vars.ACCOUNT_URL is %r; a hand-run `wrangler dev` would introspect against "
            "production. Point it at loopback" % (DEV_CONFIG, account)
        )
    return out


def dev_image_tags(log: str) -> set[str]:
    """The `cloudflare-dev/<name>:<build id>` tags a wrangler dev build log says it created."""
    return set(_IMAGE_TAG_RE.findall(log))


def ready_url(log: str) -> str | None:
    """The URL from wrangler's `Ready on <url>` line, or None before it is printed."""
    m = _READY_RE.search(log)
    return m.group(1) if m else None


def verdict(obs: dict) -> list[str]:
    """The findings for one run's observations. Pure, so the controls can drive it."""
    out: list[str] = []

    # 0. Readiness.
    ready = obs.get("ready_info") or {}
    if obs.get("ready_status") != 200:
        out.append(
            "GET %s answered %r, expected 200; body %r"
            % (READY_PATH, obs.get("ready_status"), str(obs.get("ready_body", ""))[:300])
        )
    elif ready.get("ready") is not True or not ready.get("workerVersion"):
        out.append(
            "GET %s answered 200 without ready: true and a workerVersion: %r" % (READY_PATH, ready)
        )
    if not obs.get("ready_probed"):
        out.append(
            "GET %s never called the stub issuer's probe(), so the ISSUER binding is unproven for "
            "readiness" % READY_PATH
        )
    if not obs.get("ready_server_info"):
        out.append("GET %s never asked the account server for server-info" % READY_PATH)
    if obs.get("ready_issues"):
        out.append(
            "GET %s made the stub issuer issue %d token(s); readiness must mint nothing"
            % (READY_PATH, obs["ready_issues"])
        )
    if obs.get("ready_containers"):
        out.append(
            "GET %s started container(s) %s" % (READY_PATH, ", ".join(obs["ready_containers"]))
        )

    # 1. No bearer.
    if obs.get("no_bearer_status") != 401:
        out.append(
            "CONTROL: GET %s with no bearer answered %r, expected 401"
            % (PROBE_PATH, obs.get("no_bearer_status"))
        )
    if obs.get("no_bearer_introspections", 0) != 0:
        out.append("CONTROL: a request with no bearer made the Worker call the account side")
    if obs.get("no_bearer_containers"):
        out.append(
            "CONTROL: a request with no bearer started container(s) %s"
            % ", ".join(obs["no_bearer_containers"])
        )

    # 2. A stranger's bearer, answered inactive.
    if obs.get("stranger_status") != 401:
        out.append(
            "CONTROL: GET %s with an inactive token answered %r, expected 401"
            % (PROBE_PATH, obs.get("stranger_status"))
        )
    if not obs.get("stranger_routed"):
        out.append(
            "CONTROL: the Worker refused the stranger without asking the issuer's route(), "
            "so the refusal was not the account side's verdict"
        )
    if obs.get("stranger_issues"):
        out.append("CONTROL: a stranger's bearer made the issuer issue a token")
    if obs.get("stranger_containers"):
        out.append(
            "CONTROL: an inactive token started container(s) %s"
            % ", ".join(obs["stranger_containers"])
        )

    # 3. The caller.
    info = obs.get("caller_info") or {}
    if obs.get("caller_status") != 200:
        out.append(
            "GET %s with a valid proxy:exec bearer answered %r, expected 200; body %r"
            % (PROBE_PATH, obs.get("caller_status"), str(obs.get("caller_body", ""))[:300])
        )
    elif info.get("mode") != "container":
        out.append(
            "%s through the Worker reports mode %r, expected 'container'"
            % (PROBE_PATH, info.get("mode"))
        )
    # The CLI's own version, not renet's: the two agree only when a release injects one version into both, so a local build (bundle 0.0.0-dev, renet from its tag) would fail a renet comparison while proving nothing more. proxy_image_smoke holds server-info to the bundle the same way.
    elif info.get("cliVersion") != obs.get("bundle_version"):
        out.append(
            "%s reports cliVersion %r but the staged bundle says %r, so the 200 did not come from "
            "the executor image this run built"
            % (PROBE_PATH, info.get("cliVersion"), obs.get("bundle_version"))
        )
    if not obs.get("caller_routed"):
        out.append("the Worker never asked the issuer's route() about the valid bearer")
    if obs.get("caller_auth_status") != AUTH_OK_STATUS:
        out.append(
            "GET %s with the valid bearer answered %r, expected %d (authenticated, then the missing "
            "machine query refused); body %r"
            % (
                AUTH_PATH,
                obs.get("caller_auth_status"),
                AUTH_OK_STATUS,
                str(obs.get("caller_auth_body", ""))[:300],
            )
        )
    if not obs.get("caller_introspected"):
        out.append(
            "the executor never introspected the valid bearer with the issued token through the "
            "Worker's egress"
        )
    if not obs.get("caller_issued_for_org"):
        out.append(
            "the issuer was never asked to issue for the org %s the caller routed to, so the "
            "token is not keyed by org" % CALLER_ORG
        )
    if not obs.get("caller_containers"):
        out.append(
            "the valid bearer started no %s* container, so nothing shows the Worker reached its container"
            % CONTAINER_PREFIX
        )

    # Teardown.
    if obs.get("wrangler_survived"):
        out.append(
            "wrangler (process group %s) was still running after SIGKILL; kill it by hand before the next run"
            % obs["wrangler_survived"]
        )
    if obs.get("left_behind"):
        out.append(
            "teardown left container(s) running: %s; remove them with `docker rm -f %s`"
            % (", ".join(obs["left_behind"]), " ".join(obs["left_behind"]))
        )
    return out


HEALTHY: dict = {
    "ready_status": 200,
    "ready_body": '{"ready":true,"workerVersion":"v-1"}',
    "ready_info": {"ready": True, "workerVersion": "v-1"},
    "ready_probed": True,
    "ready_server_info": True,
    "ready_issues": 0,
    "ready_containers": [],
    "no_bearer_status": 401,
    "no_bearer_introspections": 0,
    "no_bearer_containers": [],
    "stranger_status": 401,
    "stranger_routed": True,
    "stranger_issues": 0,
    "stranger_containers": [],
    "caller_status": 200,
    "caller_body": '{"mode":"container","cliVersion":"1.2.3"}',
    "caller_info": {"mode": "container", "cliVersion": "1.2.3"},
    "renet_version": "1.2.3",
    "bundle_version": "1.2.3",
    "caller_routed": True,
    "caller_auth_status": 400,
    "caller_introspected": True,
    "caller_issued_for_org": True,
    "caller_containers": [CONTAINER_PREFIX + "OrgExecutor-abc"],
    "left_behind": [],
}

# Each must turn a healthy run into EXACTLY one finding.
PLANTS: tuple[tuple[str, dict], ...] = (
    ("a 503 readiness is a finding", {"ready_status": 503}),
    ("a readiness without a workerVersion is a finding", {"ready_info": {"ready": True}}),
    ("a readiness that never probed the issuer is a finding", {"ready_probed": False}),
    ("a readiness that never asked server-info is a finding", {"ready_server_info": False}),
    ("a readiness that mints is a finding", {"ready_issues": 1}),
    ("a readiness that starts a container is a finding", {"ready_containers": ["c1"]}),
    ("a tokenless request admitted is a finding", {"no_bearer_status": 200}),
    ("a tokenless request introspected is a finding", {"no_bearer_introspections": 1}),
    ("a tokenless request that starts a container is a finding", {"no_bearer_containers": ["c1"]}),
    ("an inactive token admitted is a finding", {"stranger_status": 200}),
    ("a stranger refused without asking route() is a finding", {"stranger_routed": False}),
    ("a stranger that makes the issuer issue is a finding", {"stranger_issues": 1}),
    ("an inactive token that starts a container is a finding", {"stranger_containers": ["c1"]}),
    ("a refused caller is a finding", {"caller_status": 401}),
    (
        "a daemon-mode answer is a finding",
        {"caller_info": {"mode": "daemon", "cliVersion": "1.2.3"}},
    ),
    (
        "a cliVersion that is not the staged bundle's is a finding",
        {"caller_info": {"mode": "container", "cliVersion": "0.0.0-dev"}},
    ),
    ("a caller never routed is a finding", {"caller_routed": False}),
    ("an authenticated route refusing the caller is a finding", {"caller_auth_status": 401}),
    ("a caller never introspected is a finding", {"caller_introspected": False}),
    ("a token not issued for the caller's org is a finding", {"caller_issued_for_org": False}),
    ("a 200 with no container behind it is a finding", {"caller_containers": []}),
    ("a container surviving teardown is a finding", {"left_behind": ["c1"]}),
)


# ---------------------------------------------------------------------------------------------
# The fake account server


class FakeAccount:
    """The account side on loopback: introspection for the executor, plus the endpoints the STUB ISSUER calls.

    `POST /account/api/v1/proxy/introspect` refuses any caller not presenting the issued token (401), answers the CALLER token active with an orgId and `proxy:exec`, and every other token inactive. `GET /account/api/v1/.well-known/server-info` answers 200 (what `/v1/ready` asks over ACCOUNT). `POST /stub/route`, `/stub/issue` and `/stub/probe` are what the stub issuer's `route(bearer)`, `issue(orgId)` and `probe()` call, so the fake is the authority on who is a caller (`route` answers `{ orgId }` for the CALLER token and `{ refused }` for a stranger) and records every call. `plant` exists for controls only: `active-all` routes and introspects every token as the caller (so the stranger control must go red), `inactive-all` refuses and deactivates every token (so the caller probe must go red). Every introspection is recorded as (authorization header, token).
    """

    def __init__(self, executor_token: str, caller_token: str, plant: str | None = None) -> None:
        if plant not in (None, "active-all", "inactive-all"):
            raise ValueError("unknown plant %r" % plant)
        self.executor_token = executor_token
        self.caller_token = caller_token
        self.plant = plant
        self.seen: list[tuple[str, str]] = []
        self.stub_calls: list[tuple[str, dict]] = []
        self.server_info_gets = 0
        self._lock = threading.Lock()
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                return

            def _send(self, status: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(length) if length else b""
                auth = self.headers.get("authorization") or ""
                try:
                    body = json.loads(raw or b"{}")
                    if not isinstance(body, dict):
                        body = {}
                except ValueError:
                    body = {}
                if self.path.startswith("/stub/"):
                    kind = self.path.removeprefix("/stub/")
                    with fake._lock:
                        fake.stub_calls.append((kind, body))
                    if kind == "route":
                        return self._send(200, fake.route(str(body.get("bearer", ""))))
                    return self._send(200, {})
                token = str(body.get("token", ""))
                with fake._lock:
                    fake.seen.append((auth, token))
                if self.path != INTROSPECT_PATH:
                    return self._send(404, {})
                if auth != "Bearer " + fake.executor_token:
                    return self._send(401, {"error": "bad executor token"})
                return self._send(200, fake.identity(token))

            def do_GET(self) -> None:
                if self.path != SERVER_INFO_PATH:
                    return self._send(404, {})
                with fake._lock:
                    fake.server_info_gets += 1
                return self._send(200, {"version": "wrangler-dev-e2e"})

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def identity(self, token: str) -> dict:
        active = (
            token == self.caller_token and self.plant != "inactive-all"
        ) or self.plant == "active-all"
        if not active:
            return {"active": False}
        return {
            "active": True,
            "scopes": ["proxy:exec"],
            "orgId": CALLER_ORG,
            "teamId": None,
            "tokenId": "tok-wrangler-dev-e2e",
            "createdByUserId": "user-wrangler-dev-e2e",
            "userEmail": "wrangler-dev-e2e@example.invalid",
        }

    def route(self, bearer: str) -> dict:
        """The stub issuer's `route(bearer)`: the caller's org, or a refusal."""
        if self.plant == "inactive-all":
            return {"refused": "route-refused"}
        if bearer == self.caller_token or self.plant == "active-all":
            # placement is required since E7: resolveTenant answers 503 for a route without one.
            return {"orgId": CALLER_ORG, "placement": 0}
        return {"refused": "route-refused"}

    @property
    def url(self) -> str:
        return "http://127.0.0.1:%d" % self._server.server_address[1]

    def asked_with_executor_token(self, token: str) -> bool:
        with self._lock:
            return ("Bearer " + self.executor_token, token) in self.seen

    def asked_route(self, bearer: str) -> bool:
        """Whether the stub issuer's route() was asked about this bearer."""
        with self._lock:
            return ("route", {"bearer": bearer}) in self.stub_calls

    def stub_count(self, kind: str) -> int:
        with self._lock:
            return sum(1 for k, _ in self.stub_calls if k == kind)

    def issued_orgs(self) -> list[str]:
        """The orgs the stub issuer was asked to issue for, in order."""
        with self._lock:
            return [str(p.get("orgId")) for k, p in self.stub_calls if k == "issue"]

    def count(self) -> int:
        """Every request of any kind that reached the account side."""
        with self._lock:
            return len(self.seen) + len(self.stub_calls) + self.server_info_gets

    def __enter__(self) -> typing.Self:
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()


def mint_tokens() -> dict[str, str]:
    """Throwaway bearer tokens for one run; they authenticate against nothing but FakeAccount. `executor` is the token the stub issuer issues."""
    return {
        name: "rdt_wrangler_dev_e2e_%s_%s" % (name, secrets.token_hex(8))
        for name in ("executor", "caller", "stranger")
    }


def http_get(
    url: str, token: str = "", timeout: float = REQUEST_TIMEOUT_S
) -> tuple[int | None, str]:
    """(status, body) for a loopback GET; (None, error text) when nothing answered."""
    headers = {"authorization": "Bearer " + token} if token else {}
    req = https.build_request(url, headers=headers, method="GET", http="loopback")
    try:
        with https.urlopen(req, timeout=timeout, http="loopback") as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # An HTTPError holds the response open; closing it is what keeps a 401 from leaking a file.
        with e:
            return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        return None, str(e)


def stub_issuer_files(issued: str, fake_url: str) -> dict[str, str]:
    """The stub issuer Worker's files, {name: text}: an `ExecutorIssuer` entrypoint with the account Worker's three RPCs.

    `route(bearer)` and the records of `issue(orgId)` and `probe()` go to the fake account at `fake_url`, which is the authority on who the caller is; `issue()` answers `issued` with an expiry STUB_ISSUER_TTL_S from the call, and `probe()` answers `{ ok: true, scopes, ttlMs }`, the contract of the real entrypoint.
    """
    script = (
        "import { WorkerEntrypoint } from 'cloudflare:workers';\n"
        "const FAKE = %s;\n"
        "async function tell(kind, payload) {\n"
        "  const r = await fetch(FAKE + '/stub/' + kind, { method: 'POST', body: JSON.stringify(payload) });\n"
        "  return r.json();\n"
        "}\n"
        "export class ExecutorIssuer extends WorkerEntrypoint {\n"
        "  async route(bearer) {\n"
        "    return tell('route', { bearer });\n"
        "  }\n"
        "  async issue(orgId) {\n"
        "    await tell('issue', { orgId });\n"
        "    return { token: %s, expiresAt: new Date(Date.now() + %d * 1000).toISOString() };\n"
        "  }\n"
        "  async probe() {\n"
        "    await tell('probe', {});\n"
        "    return { ok: true, scopes: ['proxy:exec', 'audit:write'], ttlMs: %d * 1000 };\n"
        "  }\n"
        "}\n"
        "export default { fetch() { return new Response('stub issuer: RPC only', { status: 404 }); } };\n"
    ) % (json.dumps(fake_url), json.dumps(issued), STUB_ISSUER_TTL_S, STUB_ISSUER_TTL_S)
    config = (
        "# Written per run by the proxy wrangler-dev e2e gate; never deployed.\n"
        'name = "%s"\nmain = "stub-issuer.js"\ncompatibility_date = "2026-01-20"\n'
    ) % STUB_ISSUER_NAME
    return {"stub-issuer.js": script, "stub-issuer.toml": config}


def _post(url: str, body: dict) -> dict:
    """POST JSON to the fake on loopback and answer its JSON."""
    req = https.build_request(
        url,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
        http="loopback",
    )
    with https.urlopen(req, timeout=5, http="loopback") as r:
        return json.loads(r.read())


def _fake_account_controls(check: Checker) -> None:
    tokens = mint_tokens()

    def ask(fake: FakeAccount, executor: str, token: str) -> tuple[int | None, dict]:
        req = https.build_request(
            fake.url + INTROSPECT_PATH,
            data=json.dumps({"token": token}).encode(),
            headers={"authorization": "Bearer " + executor, "content-type": "application/json"},
            method="POST",
            http="loopback",
        )
        try:
            with https.urlopen(req, timeout=5, http="loopback") as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, {}

    with FakeAccount(tokens["executor"], tokens["caller"]) as fake:
        status, body = ask(fake, tokens["executor"], tokens["caller"])
        check(
            "fake account: the caller is active, in an org, with proxy:exec",
            status == 200
            and body.get("active") is True
            and body.get("orgId")
            and "proxy:exec" in body.get("scopes", []),
        )
        check(
            "fake account: the stranger is inactive",
            ask(fake, tokens["executor"], tokens["stranger"])[1] == {"active": False},
        )
        check(
            "fake account: a wrong executor token is refused 401",
            ask(fake, "not-it", tokens["caller"])[0] == 401,
        )
        check(
            "fake account: it records who asked with which executor token",
            fake.asked_with_executor_token(tokens["caller"]) and fake.count() == 3,
        )
        check(
            "fake account: route() answers the caller's org and refuses a stranger",
            fake.route(tokens["caller"]) == {"orgId": CALLER_ORG, "placement": 0}
            and "refused" in fake.route(tokens["stranger"]),
        )
        _post(fake.url + "/stub/route", {"bearer": tokens["stranger"]})
        _post(fake.url + "/stub/issue", {"orgId": CALLER_ORG})
        _post(fake.url + "/stub/probe", {})
        check(
            "fake account: it records the stub's route, issue and probe calls",
            fake.asked_route(tokens["stranger"])
            and not fake.asked_route(tokens["caller"])
            and fake.issued_orgs() == [CALLER_ORG]
            and fake.stub_count("probe") == 1,
        )
        check("fake account: no server-info asked yet", fake.server_info_gets == 0)
        status, _ = http_get(fake.url + SERVER_INFO_PATH)
        check(
            "fake account: server-info answers 200 and is counted",
            status == 200 and fake.server_info_gets == 1,
        )
        check("fake account: an unknown GET is 404", http_get(fake.url + "/nope")[0] == 404)
    with FakeAccount(tokens["executor"], tokens["caller"], plant="active-all") as fake:
        check(
            "fake account plant active-all: the stranger turns active",
            ask(fake, tokens["executor"], tokens["stranger"])[1].get("active") is True,
        )
        check(
            "fake account plant active-all: route() admits the stranger",
            "orgId" in fake.route(tokens["stranger"]),
        )
    with FakeAccount(tokens["executor"], tokens["caller"], plant="inactive-all") as fake:
        check(
            "fake account plant inactive-all: route() refuses the caller",
            "refused" in fake.route(tokens["caller"]),
        )
        check(
            "fake account plant inactive-all: the caller turns inactive",
            ask(fake, tokens["executor"], tokens["caller"])[1] == {"active": False},
        )


def selftest() -> bool:
    """True when a control FAILED."""
    check = Checker()
    deploy = {
        "name": "rediacc-proxy-eu",
        "main": "src/index.ts",
        "compatibility_date": "2026-01-20",
        "compatibility_flags": ["nodejs_compat"],
        "routes": [{"pattern": PROXY_EU_HOST}],
        "vars": {"ACCOUNT_URL": ACCOUNT_DEFAULT_ORIGIN},
        "services": [
            {
                "binding": "ACCOUNT",
                "service": "rediacc-account-eu",
                "entrypoint": "CloudflareInternal",
            },
            {"binding": "ISSUER", "service": "rediacc-account-eu", "entrypoint": "ExecutorIssuer"},
        ],
        "version_metadata": {"binding": VERSION_METADATA_BINDING},
        "containers": [
            {
                "class_name": "OrgExecutor",
                "scheduling_policy": "durable_object",
                "images": {"executor": {"dockerfile": "./Dockerfile", "build_context": "../.."}},
            },
        ],
        "durable_objects": {
            "bindings": [
                {"name": "ORG_EXECUTOR", "class_name": "OrgExecutor"},
                {"name": "EXECUTOR_CAPACITY", "class_name": "ExecutorCapacity"},
            ]
        },
        "migrations": [
            {"tag": "v1", "new_sqlite_classes": ["ExecutorContainer"]},
            {"tag": "v2", "new_sqlite_classes": ["OrgExecutor", "ExecutorCapacity"]},
            {"tag": "v3", "deleted_classes": ["ExecutorContainer"]},
        ],
    }
    dev = {k: v for k, v in deploy.items() if k not in ("routes", "services")}
    dev = {
        **dev,
        "name": "rediacc-proxy-dev",
        "vars": {"ACCOUNT_URL": "http://127.0.0.1:9"},
        "services": [ISSUER_BINDING],
    }
    check("a faithful dev config has no findings", dev_config_findings(dev, deploy) == [])
    for label, patch in (
        (
            "a dev config with the deployed [[services]] is a finding",
            {"services": deploy["services"]},
        ),
        (
            "a dev config adding an ACCOUNT binding is a finding",
            {"services": [ISSUER_BINDING, {"binding": "ACCOUNT", "service": "rediacc-account-eu"}]},
        ),
        ("a dev config without the ISSUER binding is a finding", {"services": []}),
        (
            "a dev config binding ISSUER to a real account Worker is a finding",
            {"services": [{**ISSUER_BINDING, "service": "rediacc-account-eu"}]},
        ),
        ("a dev config without [version_metadata] is a finding", {"version_metadata": {}}),
        ("a dev config with routes is a finding", {"routes": deploy["routes"]}),
        ("a dev config reusing the deployed name is a finding", {"name": "rediacc-proxy-eu"}),
        ("a dev config named off the cleanup prefix is a finding", {"name": "something-else"}),
        ("a drifted compatibility_date is a finding", {"compatibility_date": "2025-01-01"}),
        (
            "a drifted [[containers]] is a finding",
            {"containers": [{"class_name": "Other", "image": "./Dockerfile"}]},
        ),
        (
            "a production ACCOUNT_URL is a finding",
            {"vars": {"ACCOUNT_URL": ACCOUNT_DEFAULT_ORIGIN}},
        ),
    ):
        check(label, len(dev_config_findings({**dev, **patch}, deploy)) == 1)

    log = (
        "#28 naming to docker.io/cloudflare-dev/orgexecutor:1008f582 0.0s done\n"
        "#28 unpacking to docker.io/cloudflare-dev/orgexecutor:1008f582 2.6s done\n"
        "[wrangler:info] Ready on http://127.0.0.1:18932\n"
    )
    check(
        "the dev image tag is read from the build log",
        dev_image_tags(log) == {"cloudflare-dev/orgexecutor:1008f582"},
    )
    check(
        "a log naming no dev image yields no tag",
        dev_image_tags("naming to docker.io/library/node:24") == set(),
    )
    check("the Ready line is read", ready_url(log) == "http://127.0.0.1:18932")
    check("no Ready line reads as not ready", ready_url("Building image...") is None)
    stub = stub_issuer_files("rdt_issued_x", "http://127.0.0.1:1")
    check(
        "the stub issuer exports ExecutorIssuer with route(), issue() and probe()",
        "export class ExecutorIssuer extends WorkerEntrypoint" in stub["stub-issuer.js"]
        and all("async %s(" % rpc in stub["stub-issuer.js"] for rpc in ("route", "issue", "probe"))
        and '"rdt_issued_x"' in stub["stub-issuer.js"]
        and '"http://127.0.0.1:1"' in stub["stub-issuer.js"],
    )
    check(
        "the stub issuer is named as the dev ISSUER binding names it",
        tomllib.loads(stub["stub-issuer.toml"]).get("name") == ISSUER_BINDING["service"],
    )

    check("a healthy run has no findings", verdict(HEALTHY) == [])
    check("an empty observation is not a pass", len(verdict({})) >= 5)
    for label, patch in PLANTS:
        check(label, len(verdict({**HEALTHY, **patch})) == 1)
    _fake_account_controls(check)
    print("  %d control(s)" % check.count)
    return not check.ok


# ---------------------------------------------------------------------------------------------
# The real run


class _TerminatedError(Exception):
    pass


_SIGTERM_SEEN = [False]


def _on_sigterm(_signum: int, _frame: object) -> None:
    """The first SIGTERM unwinds into the `finally` teardown; any later one is ignored, or it would raise inside that teardown and skip the removals still to run."""
    if _SIGTERM_SEEN[0]:
        return
    _SIGTERM_SEEN[0] = True
    raise _TerminatedError("SIGTERM")


def _docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )


def prefixed_containers() -> set[str]:
    r = _docker("ps", "-a", "--filter", "name=" + CONTAINER_PREFIX, "--format", "{{.Names}}")
    return {n for n in r.stdout.split() if n.startswith(CONTAINER_PREFIX)}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tail(path: pathlib.Path, n: int = 3000) -> str:
    try:
        return path.read_text(errors="replace")[-n:]
    except OSError:
        return ""


def _stop(proc: subprocess.Popen) -> bool:
    """Stop wrangler and every child it spawned (npm, workerd): they share its session. False when the group still ran after SIGKILL, which the caller reports as a leftover."""
    if proc.poll() is not None:
        return True
    for sig, grace in ((signal.SIGINT, STOP_GRACE_S), (signal.SIGKILL, 10)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return True
        try:
            proc.wait(timeout=grace)
            return True
        except subprocess.TimeoutExpired:
            continue
    return False


def observe(root: pathlib.Path, renet_version: str, plant: str | None = None) -> tuple[dict, dict]:
    """Run the Worker under `wrangler dev` and collect what verdict() judges.

    Returns (observations, shape) where shape counts what the run built and removed. `plant` is passed to FakeAccount, for the scratch controls only.
    """
    worker = root.joinpath(*WORKER_DIR)
    tokens = mint_tokens()
    obs: dict = {"renet_version": renet_version}
    shape: dict = {"removed_containers": 0, "removed_images": 0}
    before = prefixed_containers()
    if before:
        print(
            "  NOTE  %d %s* container(s) predate this run and are left alone (a killed run, or a "
            "concurrent one): %s" % (len(before), CONTAINER_PREFIX, ", ".join(sorted(before))),
            file=sys.stderr,
        )
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="rediacc-wrangler-dev-e2e-"))
    log_path = scratch / "wrangler-dev.log"
    proc: subprocess.Popen | None = None
    with FakeAccount(tokens["executor"], tokens["caller"], plant=plant) as fake:
        for name, text in stub_issuer_files(tokens["executor"], fake.url).items():
            (scratch / name).write_text(text)
        try:
            port = _free_port()
            cmd = [
                str(worker.joinpath(*WRANGLER_BIN)), "dev",
                "--config", DEV_CONFIG,
                "--config", str(scratch / "stub-issuer.toml"),
                "--ip", "127.0.0.1", "--port", str(port),
                "--inspector-port", str(_free_port()),
                "--var", "ACCOUNT_URL:" + fake.url,
                "--persist-to", str(scratch / "state"),
                "--show-interactive-dev-session=false",
            ]  # fmt: skip
            env = {
                **os.environ,
                "WRANGLER_SEND_METRICS": "false",
                "NO_COLOR": "1",
                "FORCE_COLOR": "0",
                "CI": "true",
            }
            with log_path.open("w") as log:
                proc = subprocess.Popen(
                    cmd, cwd=worker, env=env, stdout=log, stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL, start_new_session=True,
                )  # fmt: skip
            print("  wrangler dev building the executor image and starting (slow when cold)...")
            started = time.monotonic()
            base = None
            while time.monotonic() - started < READY_TIMEOUT_S:
                base = ready_url(_tail(log_path, 10**7))
                if base or proc.poll() is not None:
                    break
                time.sleep(2)
            if not base:
                why = (
                    "exited %s" % proc.returncode
                    if proc.poll() is not None
                    else "timed out after %ds" % READY_TIMEOUT_S
                )
                obs["startup_failure"] = "wrangler dev never became ready (%s); its log:\n%s" % (
                    why,
                    _tail(log_path),
                )
                return obs, shape
            shape["ready_s"] = round(time.monotonic() - started)
            url = "http://127.0.0.1:%d%s" % (port, PROBE_PATH)

            obs["ready_status"], obs["ready_body"] = http_get(
                "http://127.0.0.1:%d%s" % (port, READY_PATH)
            )
            try:
                obs["ready_info"] = json.loads(obs["ready_body"] or "{}")
            except json.JSONDecodeError:
                obs["ready_info"] = {}
            obs["ready_probed"] = fake.stub_count("probe") > 0
            obs["ready_server_info"] = fake.server_info_gets > 0
            obs["ready_issues"] = len(fake.issued_orgs())
            time.sleep(SETTLE_S)
            obs["ready_containers"] = sorted(prefixed_containers() - before)

            asked = fake.count()
            obs["no_bearer_status"], _ = http_get(url)
            time.sleep(SETTLE_S)
            obs["no_bearer_introspections"] = fake.count() - asked
            obs["no_bearer_containers"] = sorted(prefixed_containers() - before)

            obs["stranger_status"], _ = http_get(url, tokens["stranger"])
            time.sleep(SETTLE_S)
            obs["stranger_routed"] = fake.asked_route(tokens["stranger"])
            obs["stranger_issues"] = len(fake.issued_orgs())
            obs["stranger_containers"] = sorted(prefixed_containers() - before)

            obs["caller_status"], obs["caller_body"] = http_get(url, tokens["caller"])
            try:
                obs["caller_info"] = json.loads(obs["caller_body"] or "{}")
            except json.JSONDecodeError:
                obs["caller_info"] = {}
            obs["caller_auth_status"], obs["caller_auth_body"] = http_get(
                "http://127.0.0.1:%d%s" % (port, AUTH_PATH), tokens["caller"]
            )
            obs["caller_routed"] = fake.asked_route(tokens["caller"])
            obs["caller_introspected"] = fake.asked_with_executor_token(tokens["caller"])
            obs["caller_issued_for_org"] = CALLER_ORG in fake.issued_orgs()
            obs["caller_containers"] = sorted(prefixed_containers() - before)
        finally:
            survivor = proc is not None and not _stop(proc)
            ours = prefixed_containers() - before
            if ours:
                _docker("rm", "-f", *sorted(ours))
                shape["removed_containers"] = len(ours)
            for tag in sorted(dev_image_tags(_tail(log_path, 10**7))):
                if _docker("rmi", tag).returncode == 0:
                    shape["removed_images"] += 1
            obs["left_behind"] = sorted(prefixed_containers() - before)
            if survivor and proc is not None:
                obs["wrangler_survived"] = proc.pid
            shutil.rmtree(scratch, ignore_errors=True)
    return obs, shape


def static_findings(root: pathlib.Path) -> list[str]:
    worker = root.joinpath(*WORKER_DIR)
    try:
        dev = tomllib.loads((worker / DEV_CONFIG).read_text())
        deploy = tomllib.loads((worker / DEPLOY_CONFIG).read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        return ["cannot read %s or %s: %s" % (DEV_CONFIG, DEPLOY_CONFIG, e)]
    return dev_config_findings(dev, deploy)


def cannot_run(root: pathlib.Path) -> str | None:
    """Why this host cannot run the gate, with the fix, or None."""
    if shutil.which("docker") is None or _docker("version").returncode != 0:
        return "docker is not available here (no `docker` on PATH, or its daemon does not answer `docker version`); start docker, then rerun"
    # Docker Desktop's host-gateway (192.168.65.254) cannot reach workerd's egress listener, which falls back to loopback, so every interceptOutboundHttp call fails with "fetch failed" (measured 2026-10-31: the egress sidecar logs `dialing gateway: dial tcp 192.168.65.254:<port>: connect: connection refused`). CI's Linux runners bind it on the docker0 bridge.
    if _docker("info", "--format", "{{.OperatingSystem}}").stdout.strip() == "Docker Desktop":
        return "Docker Desktop's host-gateway cannot reach workerd's egress listener, so the container's intercepted egress never arrives; run the gate on a native-Linux docker host (CI does)"
    wrangler = root.joinpath(*WORKER_DIR, *WRANGLER_BIN)
    if not wrangler.exists():
        return "%s is missing; run `cd workers/proxy && npm ci`" % wrangler.relative_to(root)
    return None


def run(root: pathlib.Path, plant: str | None = None) -> int:
    """The real-tree run after the controls. Separate from main() so a scratch control can pass `plant`."""
    found = static_findings(root)
    if found:
        print("✗ %d finding(s) in workers/proxy/%s:" % (len(found), DEV_CONFIG), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    why = cannot_run(root)
    if why:
        print("✗ CANNOT RUN: %s. Nothing was checked." % why, file=sys.stderr)
        return CANNOT_RUN

    staged_here = False
    if root.joinpath(*proxy_image_smoke.STAGE_DIR, executor_artifacts.MANIFEST).is_file():
        how = "already staged (left in place)"
    else:
        staged_here = True
        ok, how = proxy_image_smoke._stage_local(root)
        if not ok:
            proxy_image_smoke._unstage(root)
            print(
                "✗ CANNOT RUN: no renet to ship in the image (%s). Nothing was checked." % how,
                file=sys.stderr,
            )
            return CANNOT_RUN
    staged = root.joinpath(*proxy_image_smoke.STAGE_DIR, executor_artifacts.RENET)
    try:
        try:
            out = subprocess.run(
                [str(staged), "version"], capture_output=True, text=True, timeout=30, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(
                "✗ CANNOT RUN: the staged renet %s cannot be executed (%s). Nothing was checked."
                % (staged, exc),
                file=sys.stderr,
            )
            return CANNOT_RUN
        renet_version = proxy_image_smoke.parse_renet_version(out.stdout + out.stderr)
        if renet_version is None:
            print(
                "✗ the staged renet does not report a version: %r"
                % (out.stdout + out.stderr)[-300:],
                file=sys.stderr,
            )
            return 1
        bundle = root.joinpath(*proxy_image_smoke.STAGE_DIR, executor_artifacts.BUNDLE)
        try:
            bout = subprocess.run(
                ["node", str(bundle), "--version"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(
                "✗ CANNOT RUN: node cannot run the staged bundle %s (%s). Nothing was checked."
                % (bundle, exc),
                file=sys.stderr,
            )
            return CANNOT_RUN
        bundle_version = bout.stdout.strip()
        if bout.returncode != 0 or not bundle_version:
            print(
                "✗ the staged bundle does not report a version (rc %d): %r"
                % (bout.returncode, (bout.stdout + bout.stderr)[-300:]),
                file=sys.stderr,
            )
            return 1
        print("  renet %s and bundle %s for the image: %s" % (renet_version, bundle_version, how))
        obs, shape = observe(root, renet_version, plant=plant)
        obs["bundle_version"] = bundle_version
    finally:
        if staged_here:
            proxy_image_smoke._unstage(root)

    if "startup_failure" in obs:
        print("✗ %s" % obs["startup_failure"], file=sys.stderr)
        if obs.get("left_behind"):
            print(
                "✗ teardown left container(s): %s" % ", ".join(obs["left_behind"]), file=sys.stderr
            )
        return 1
    found = verdict(obs)
    teardown = "teardown removed %d container(s) and %d dev image(s), %d left" % (
        shape["removed_containers"], shape["removed_images"], len(obs.get("left_behind", [])),
    )  # fmt: skip
    if found:
        print("✗ %d proxy wrangler-dev finding(s) (%s):" % (len(found), teardown), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    print(
        "✓ the proxy Worker under `wrangler dev` (ready in %ds) answered /v1/ready 200 after "
        "probing the stub issuer and server-info, refused 2 of 3 requests with 401 "
        "(no bearer: 0 account-side calls; stranger: route() asked and refused, no token issued) and started 0 containers for them, "
        "then answered a proxy:exec bearer with 200, mode \"container\" and cliVersion %s from %d new "
        "container(s); %s" % (
            shape.get("ready_s", -1), obs["bundle_version"], len(obs["caller_containers"]), teardown,
        )
    )  # fmt: skip
    return 0


def main(argv: list[str]) -> int:
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(line_buffering=True)
    rc = controls_first("proxy wrangler dev e2e", selftest)
    if rc or "--selftest" in argv:
        return rc
    _SIGTERM_SEEN[0] = False
    previous = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return run(paths.repo_root())
    except _TerminatedError:
        print("✗ terminated; teardown ran", file=sys.stderr)
        return 143
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
