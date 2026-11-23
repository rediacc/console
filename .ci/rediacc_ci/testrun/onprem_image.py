"""The air-gapped image test of the shipped on-premise server (PLAN-rmcp-executor-hardening.md, Design 18, box EHOP4).

    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_image --airgapped [--no-build] [--window <seconds>]

Builds the shipped image (`rediacc_ci.ops.build_server onprem`, tag `rediacc-server-onprem:dev`, the root `Dockerfile` `--target onprem`; never `private/account/Dockerfile`), then runs it where it has no route out and proves it never tries to leave:

  1. A Docker network created `--internal`: containers on it have no route to the outside, and its DNS cannot resolve an outside name.
  2. A deny-all egress proxy on that network. It answers every request, CONNECT included, with 403 and prints one `EGRESS <method> <target>` line per attempt. The image's containers get `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY` pointing at it, so a client that honours them is LOGGED; a client that ignores them cannot connect and surfaces as a resolution error (`ENOTFOUND`, `EAI_AGAIN`) in its own log, which the audit reads too.
  3. The image's account server on the on-premise entry, reachable from the host only through a forwarder container attached to both networks (an internal network publishes no port). The forwarder is not part of the image under test and is not audited.
  4. A DETECTOR SELF-CHECK before the observation window: a probe container dials a name that cannot exist through the proxy, and the run FAILS unless the proxy log shows that dial. A detector that cannot see a dial would turn every later "no egress" into a claim about nothing.
  5. The observation window (`--window`, default 30 s) with the server's health read through the forwarder, then the verdict: the run fails, listing them, on any `EGRESS` line other than the probe's and on any resolution error in the audited containers' logs.

Everything started here is removed on every exit path, including a failed build step or a failed self-check.

WHAT THIS RUN DOES NOT YET COVER, and why (PLAN-rmcp-executor-hardening.md Design 18 asks for more): the daemon, the container machine and the `smoke`, `daemon` and `remote-mcp` suites do not run inside the network. The daemon must bind a non-loopback host to be reached from another container, which Design 9 allows only with a TLS pair, and the account server reaches a daemon over the pinned CA of Design 19 (box EHOP5); the config blob store the daemon enrols against (RustFS) has to live on the internal network as well. Until those land, the run covers the image's own egress, which is the property the shipped artifact must hold.
"""

from __future__ import annotations

import dataclasses
import os
import re
import sys
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.testrun import onprem_stack

if TYPE_CHECKING:
    import pathlib

SELF = "rediacc_ci.testrun.onprem_image"
IMAGE = onprem_stack.IMAGE
NETWORK = "rediacc-airgap"
PROXY_NAME = "rediacc-airgap-egress"
ACCOUNT_NAME = "rediacc-airgap-account"
FORWARDER_NAME = "rediacc-airgap-forward"
PROXY_IMAGE = "python:3.12-alpine"
FORWARDER_IMAGE = "alpine/socat"
PROXY_PORT = 3128
ACCOUNT_PORT = 4910
PUBLISHED_PORT = 4911
DEFAULT_WINDOW_S = 30
PROBE_HOST = "egress-probe.invalid"
EGRESS_MARK = "EGRESS "
# A client that ignores the proxy variables fails to resolve on an internal network; these are the codes Node and curl-style clients report.
RESOLUTION_ERROR = re.compile(
    r"ENOTFOUND|EAI_AGAIN|Could not resolve host|Name or service not known"
)
BUILD_TIMEOUT_S = 3600
HEALTH_TRIES = 30
USAGE = "usage: PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_image --airgapped [--no-build] [--window <seconds>]"

PROXY_PROGRAM = (
    """
import http.server
def refuse(self):
    print("EGRESS", self.command, self.path, flush=True)
    self.send_response(403)
    self.send_header("Content-Length", "0")
    self.end_headers()
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
for m in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT"):
    setattr(H, "do_" + m, refuse)
http.server.ThreadingHTTPServer(("0.0.0.0", %d), H).serve_forever()
"""
    % PROXY_PORT
)


class ImageTestError(Exception):
    """The image test cannot run or the image failed it; the message says why."""


@dataclasses.dataclass
class Options:
    build: bool = True
    window_s: int = DEFAULT_WINDOW_S


def find_egress(proxy_log: str) -> list[str]:
    """The `EGRESS` lines of the proxy log that are not the detector probe's."""
    return [
        line.strip()
        for line in proxy_log.splitlines()
        if line.startswith(EGRESS_MARK) and PROBE_HOST not in line
    ]


def probe_seen(proxy_log: str) -> bool:
    return any(
        line.startswith(EGRESS_MARK) and PROBE_HOST in line for line in proxy_log.splitlines()
    )


def find_resolution_errors(container: str, logs: str) -> list[str]:
    return [
        "%s: %s" % (container, line.strip())
        for line in logs.splitlines()
        if RESOLUTION_ERROR.search(line)
    ]


class AirgapRun:
    def __init__(self, root: pathlib.Path, runtime: onprem_stack.Runtime | None = None) -> None:
        self.root = root
        self.rt = runtime or onprem_stack.Runtime()
        self.containers: list[str] = []
        self.network = False

    def docker(self, *args: str, env: dict[str, str] | None = None, timeout: float = 600) -> str:
        done = self.rt.run(["docker", *args], env=env, timeout=timeout)
        if done.returncode != 0:
            raise ImageTestError(
                "docker %s exited %d: %s"
                % (" ".join(args[:2]), done.returncode, done.stderr.strip()[-300:])
            )
        return done.stdout

    def logs(self, name: str) -> str:
        done = self.rt.run(["docker", "logs", name])
        # docker logs writes the container's stderr to its own stderr, so both streams are the log.
        return done.stdout + done.stderr

    # ── steps ───────────────────────────────────────────────────────────────

    def build(self) -> None:
        log.step("Building the on-premise image...")
        env = {**os.environ, "PYTHONPATH": str(self.root / ".ci")}
        done = self.rt.run(
            [sys.executable, "-m", "rediacc_ci.ops.build_server", "onprem"],
            env=env,
            cwd=self.root,
            timeout=BUILD_TIMEOUT_S,
        )
        if done.returncode != 0:
            raise ImageTestError(
                "build_server onprem exited %d: %s" % (done.returncode, done.stderr.strip()[-300:])
            )

    def create_network(self) -> None:
        log.step("Creating the internal network and the deny-all egress proxy...")
        self.network = True
        self.docker("network", "create", "--internal", NETWORK)
        self.containers.append(PROXY_NAME)
        self.docker(
            "run",
            "-d",
            "--name",
            PROXY_NAME,
            "--network",
            NETWORK,
            PROXY_IMAGE,
            "python3",
            "-c",
            PROXY_PROGRAM,
        )

    def detector_self_check(self) -> None:
        """A probe dials through the proxy; the proxy log must show it."""
        log.step("Checking that the egress detector sees a dial...")
        proxy = "http://%s:%d" % (PROXY_NAME, PROXY_PORT)
        # The probe container is not left behind and its own result is irrelevant: the proxy answers 403.
        self.rt.run(
            ["docker", "run", "--rm", "--network", NETWORK, "-e", "http_proxy=" + proxy, PROXY_IMAGE, "python3", "-c",
             "import urllib.request as u; u.build_opener(u.ProxyHandler({'http': '%s'})).open('http://%s/', timeout=10)" % (proxy, PROBE_HOST)],
            timeout=120,
        )  # fmt: skip
        for _ in range(10):
            if probe_seen(self.logs(PROXY_NAME)):
                return
            self.rt.sleep(1.0)
        raise ImageTestError(
            "the egress detector did not see a probe dial; a clean window would prove nothing"
        )

    def start_account(self, stack: onprem_stack.Stack) -> None:
        log.step("Starting the image's account server on the internal network...")
        opts = onprem_stack.Options(account_port=ACCOUNT_PORT)
        env = stack.account_env(opts)
        proxy = "http://%s:%d" % (PROXY_NAME, PROXY_PORT)
        names = [
            n
            for n in env
            if n.startswith("ACCOUNT_")
            or n in {"ROOT_EMAIL", "PORT", "TEST_MODE", "ON_PREMISE_MODE"}
        ]
        argv = ["run", "-d", "--name", ACCOUNT_NAME, "--network", NETWORK, "--tmpfs", "/data"]
        argv += ["-e", "DATABASE_PATH=/data/account.db"]
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            argv += ["-e", "%s=%s" % (var, proxy)]
        argv += ["-e", "NO_PROXY=%s,localhost,127.0.0.1" % ACCOUNT_NAME]
        for name in names:
            argv += [
                "-e",
                name,
            ]  # by name: docker copies the value from its own environment, so no key sits on argv
        argv.append(IMAGE)
        self.containers.append(ACCOUNT_NAME)
        self.docker(*argv, env=env)

    def start_forwarder(self) -> None:
        self.containers.append(FORWARDER_NAME)
        self.docker("run", "-d", "--name", FORWARDER_NAME, "-p", "127.0.0.1:%d:%d" % (PUBLISHED_PORT, ACCOUNT_PORT),
                    FORWARDER_IMAGE, "TCP-LISTEN:%d,fork" % ACCOUNT_PORT, "TCP:%s:%d" % (ACCOUNT_NAME, ACCOUNT_PORT))  # fmt: skip
        self.docker("network", "connect", NETWORK, FORWARDER_NAME)

    def wait_healthy(self) -> None:
        url = "http://127.0.0.1:%d/health" % PUBLISHED_PORT
        for _ in range(HEALTH_TRIES):
            code, _body = self.rt.http_get(url)
            if code == 200:
                return
            self.rt.sleep(2.0)
        raise ImageTestError(
            "the image's account server never answered /health through the forwarder"
        )

    def verdict(self) -> list[str]:
        findings = [
            ("egress attempt through the proxy: " + line)
            for line in find_egress(self.logs(PROXY_NAME))
        ]
        findings += find_resolution_errors(ACCOUNT_NAME, self.logs(ACCOUNT_NAME))
        return findings

    def teardown(self) -> list[str]:
        failures = []
        for name in reversed(self.containers):
            done = self.rt.run(["docker", "rm", "-f", name])
            if done.returncode != 0 and "No such container" not in done.stderr:
                failures.append("container %s: %s" % (name, done.stderr.strip()))
        if self.network:
            done = self.rt.run(["docker", "network", "rm", NETWORK])
            if done.returncode != 0 and "not found" not in done.stderr:
                failures.append("network %s: %s" % (NETWORK, done.stderr.strip()))
        return failures

    def run(self, opts: Options) -> int:
        stack = onprem_stack.Stack(onprem_stack.Layout(self.root), self.rt)
        try:
            if opts.build:
                self.build()
            self.create_network()
            self.detector_self_check()
            self.start_account(stack)
            self.start_forwarder()
            self.wait_healthy()
            log.step("Observing for %d s..." % opts.window_s)
            waited = 0
            while waited < opts.window_s:
                self.rt.sleep(1.0)
                waited += 1
            findings = self.verdict()
        finally:
            for line in self.teardown():
                log.error("teardown: " + line)
        if findings:
            for line in findings:
                log.error(line)
            log.error(
                "the image tried to reach outside its network (%d finding(s))" % len(findings)
            )
            return 1
        log.info("no egress attempt in %d s: the image ran air-gapped" % opts.window_s)
        return 0


def parse(argv: list[str]) -> Options:
    if "--airgapped" not in argv:
        raise ValueError(USAGE)
    opts = Options()
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--airgapped":
            i += 1
        elif flag == "--no-build":
            opts.build = False
            i += 1
        elif flag == "--window":
            if i + 1 >= len(argv) or not argv[i + 1].isdigit():
                raise ValueError("--window needs a number of seconds")
            opts.window_s = int(argv[i + 1])
            i += 2
        else:
            raise ValueError("Unknown option: %s\n%s" % (flag, USAGE))
    return opts


def main(
    argv: list[str], runtime: onprem_stack.Runtime | None = None, root: pathlib.Path | None = None
) -> int:
    try:
        opts = parse(argv)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        return AirgapRun(root or paths.repo_root(), runtime).run(opts)
    except (ImageTestError, onprem_stack.StackError) as exc:
        log.error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
