"""The on-premise stack: RustFS, an account server, a seeded config store, `rdc serve --mode daemon` enrolled against it, and the machines (PLAN-rmcp-executor-hardening.md, Design 15, box EHOP1).

    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_stack up   [--machines container|vm] [--from-source] [--entry on-premise|node] [--account-port N] [--daemon-port N] [--ssh-port N]
    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_stack down
    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_stack status

`up` starts, in order, and records each piece in `.onprem/stack.json` the moment it exists:

  1. RustFS (`account_lifecycle.start_rustfs`), the config blob store. A RustFS that already answers is refused: `down` stops what `up` started, and a store this run did not start is not its to stop.
  2. The account server on the ON-PREMISE entry, as the `rediacc-server-onprem:dev` image (default; `rediacc_ci.ops.build_server onprem` builds it) or from source with `--from-source` (`tsx src/entry/on-premise.ts`, for fast iteration), with `TEST_MODE` on. The on-premise route factory mounts the `/test/*` seams under TEST_MODE (`private/account/src/routes/test-mount.ts`), so step 3 seeds the on-premise entry itself; `--entry node --from-source` runs the full-route entry (`src/entry/node.ts`) instead, for comparing the two. Seeding against a server that 404s a seam (an image built before the seams were mounted) is refused naming the seam.
  3. Seeding through the TEST_MODE seams `start_account` already drives (`/test/ensure-login`, `/test/ensure-subscription`, a minted API token) plus `/test/seed-config-store` with `emptyStore`, which returns the machine secret that enrolls a headless host (D46). Three tokens come out: the daemon's own `proxy:exec` token, an enrolment token, and the `proxy:exec` token of a second org, which the `daemon` suite presents to the daemon to prove the org pin refuses it. The machine secret is written beside them (a suite that needs a second device enrols it with the same secret) and the env file names its id, its file and the state file.
  4. The machines: `--machines container` runs one sshd container (alpine, a throwaway key pair, published on 127.0.0.1 only), `--machines vm` runs `./rdc.sh ops up --basic` and names the bridge address and worker.
  5. The daemon's config: a named local config with the stack's machine added, enrolled with `rdc config remote enable --machine-secret <id>` (the secret travels in `REDIACC_MACHINE_SECRET`, never argv), which seeds the empty store from that config.
  6. `rdc serve --mode daemon` on 127.0.0.1 (Design 9) with the executor token, answering `/v1/server-info` as `daemon`.

`.onprem/stack.env` names every URL, port, file and config name a suite needs, one `KEY=value` per line. It carries no secret: tokens are files under `.onprem/` (mode 0600) and the env file names the paths.

EVERY START IS UNDONE ON FAILURE. A step that raises tears down everything recorded so far (process groups by `killpg`, containers by `docker rm -f`, RustFS by `docker compose stop`) and the failure exits 1; `down` does the same from the state file, so a run killed halfway is still cleaned by the next `down`. `up` over a state file that still records resources refuses and names `down`, and a port that already answers is refused before anything starts, as `start_account` refuses it.
"""

from __future__ import annotations

import contextlib
import dataclasses
import http.client
import json
import os
import pathlib
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse

from rediacc_ci import log, paths
from rediacc_ci.core import account, account_lifecycle
from rediacc_ci.testrun import start_account

SELF = "rediacc_ci.testrun.onprem_stack"
STATE_DIR = ".onprem"
ENV_NAME = "stack.env"
STATE_NAME = "stack.json"
DEFAULT_ACCOUNT_PORT = 4910
DEFAULT_DAEMON_PORT = 8480
DEFAULT_SSH_PORT = 2230
RUSTFS_PORT = account_lifecycle.RUSTFS_PORT
IMAGE = "rediacc-server-onprem:dev"
MACHINE_IMAGE = "alpine:3.20"
ACCOUNT_CONTAINER = "rediacc-onprem-account"
MACHINE_CONTAINER = "rediacc-onprem-machine"
CONFIG_NAME = "onprem-stack"
MACHINE_NAME = "onprem-1"
EMAIL = "onprem-stack@rediacc.io"
OTHER_EMAIL = "onprem-other-org@rediacc.io"
ENTRIES = ("on-premise", "node")
MACHINE_KINDS = ("container", "vm")
HEALTH_TRIES = 60
HEALTH_INTERVAL = 2.0
TERM_WAIT_S = 10.0
USAGE = (
    "usage: PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_stack up [--machines container|vm] [--from-source] "
    "[--entry on-premise|node] [--account-port N] [--daemon-port N] [--ssh-port N] | down | status"
)


class StackError(Exception):
    """The stack cannot be brought up or down; the message names why."""


@dataclasses.dataclass
class Options:
    machines: str = "container"
    from_source: bool = False
    entry: str = "on-premise"
    account_port: int = DEFAULT_ACCOUNT_PORT
    daemon_port: int = DEFAULT_DAEMON_PORT
    ssh_port: int = DEFAULT_SSH_PORT


@dataclasses.dataclass(frozen=True)
class Layout:
    """Where the stack keeps its files, under `<root>/.onprem`."""

    root: pathlib.Path

    @property
    def dir(self) -> pathlib.Path:
        return self.root / STATE_DIR

    @property
    def env_file(self) -> pathlib.Path:
        return self.dir / ENV_NAME

    @property
    def state_file(self) -> pathlib.Path:
        return self.dir / STATE_NAME

    @property
    def sqlite(self) -> pathlib.Path:
        return self.dir / "account.db"

    @property
    def daemon_home(self) -> pathlib.Path:
        return self.dir / "daemon-home"

    @property
    def ssh_key(self) -> pathlib.Path:
        return self.dir / "machine_key"

    def token_file(self, name: str) -> pathlib.Path:
        return self.dir / ("%s.token" % name)


class Runtime:
    """Every side effect of the stack, in one place so a test replaces it whole."""

    def __init__(self) -> None:
        # The groups this process started, kept so a leader that exits is reaped rather than left a zombie that still answers `killpg(.., 0)`.
        self._children: dict[int, subprocess.Popen] = {}

    def port_answers(self, port: int) -> bool:
        """True when something accepts a TCP connection on 127.0.0.1:port."""
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            return False

    def spawn_group(
        self, argv: list[str], env: dict[str, str], cwd: pathlib.Path, log_file: pathlib.Path
    ) -> int:
        """Start `argv` as the leader of its own session and return its pid, which is its process group id."""
        with open(log_file, "wb") as sink:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=sink,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._children[proc.pid] = proc
        return proc.pid

    def signal_group(self, pgid: int, sig: int) -> None:
        """Send `sig` to a process group; a group that is gone raises ProcessLookupError."""
        os.killpg(pgid, sig)

    def group_start(self, pgid: int) -> str | None:
        """The start time (clock ticks since boot, /proc field 22) of the process whose pid is `pgid`, or None when it is gone or unreadable. A group started with its own session has its leader's pid as id, so a recycled id shows up as a different start time."""
        try:
            stat = pathlib.Path("/proc/%d/stat" % pgid).read_text(encoding="utf-8")
        except (OSError, ValueError):
            return None
        # The comm field may hold spaces and parentheses; everything after the last `)` is space-separated, with starttime as its 20th field.
        fields = stat.rpartition(")")[2].split()
        return fields[19] if len(fields) > 19 else None

    def kill_group(self, pgid: int) -> None:
        """SIGTERM the group, wait, then SIGKILL what is left; a group that is already gone is done."""
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        child = self._children.get(pgid)
        deadline = time.monotonic() + TERM_WAIT_S
        while time.monotonic() < deadline:
            if child is not None:
                child.poll()
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.2)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)
        if child is not None:
            child.wait(timeout=TERM_WAIT_S)

    def run(
        self,
        argv: list[str],
        env: dict[str, str] | None = None,
        cwd: pathlib.Path | None = None,
        timeout: float = 600,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            env=env,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )

    def http_post(
        self, url: str, body: dict, headers: dict[str, str] | None = None, timeout: float = 60
    ) -> tuple[int, str]:
        """(status, body) of a JSON POST to a loopback URL; a refused connection is (0, ""). The body travels in the request, never on argv."""
        parts = urllib.parse.urlsplit(url)
        connection = http.client.HTTPConnection(
            parts.hostname or "127.0.0.1", parts.port or 80, timeout=timeout
        )
        try:
            connection.request(
                "POST",
                parts.path or "/",
                body=json.dumps(body),
                headers={"content-type": "application/json", **(headers or {})},
            )
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8", errors="replace")
        except (OSError, http.client.HTTPException):
            return 0, ""
        finally:
            connection.close()

    def http_get(
        self, url: str, headers: dict[str, str] | None = None, insecure_tls: bool = False
    ) -> tuple[int, str]:
        """(status, body) of a GET to a loopback URL; a refused connection is (0, ""). `insecure_tls` skips certificate checks for the throwaway pair of a TLS probe."""
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or "127.0.0.1"
        try:
            if parts.scheme == "https":
                context = ssl.create_default_context()
                if insecure_tls:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                connection: http.client.HTTPConnection = http.client.HTTPSConnection(
                    host, parts.port or 443, timeout=5, context=context
                )
            else:
                connection = http.client.HTTPConnection(host, parts.port or 80, timeout=5)
            try:
                connection.request("GET", parts.path or "/", headers=headers or {})
                response = connection.getresponse()
                return response.status, response.read().decode("utf-8", errors="replace")
            finally:
                connection.close()
        except (OSError, http.client.HTTPException):
            return 0, ""

    def exited(self, pgid: int) -> int | None:
        """The exit status of a group leader this process started, or None while it still runs (or is not this process's child)."""
        child = self._children.get(pgid)
        return None if child is None else child.poll()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def seed(self, port: int, email: str, name: str, scopes: list[str]) -> str:
        """The API token of `email` with `scopes`, seeded and minted through the account server's TEST_MODE seams."""
        opts = start_account.Options()
        opts.port = str(port)
        opts.email = email
        opts.name = name
        opts.scopes = ",".join(scopes)
        api = start_account.Api(str(port), "/account/api/v1")
        try:
            token, _ = start_account.seed_and_mint(api, opts)
        except start_account.LegError as exc:
            raise StackError("seeding %s failed: %s" % (email, exc)) from None
        return token

    def seed_store(self, port: int, email: str) -> dict:
        """`/test/seed-config-store` with an empty store; the answer carries the machine secret id and secret."""
        api = start_account.Api(str(port), "/account/api/v1")
        try:
            code, raw = api.call(
                "POST", "/test/seed-config-store", {"email": email, "emptyStore": True}
            )
        except start_account.LegError as exc:
            raise StackError(str(exc)) from None
        if not 200 <= code < 300:
            raise StackError(
                "/test/seed-config-store answered HTTP %d (no config blob store, or no TEST_MODE seam): %s"
                % (code, raw[:200])
            )
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if (
            not isinstance(body, dict)
            or not body.get("machineSecretId")
            or not body.get("machineSecret")
        ):
            raise StackError("/test/seed-config-store returned no machine secret")
        return body

    def rustfs_alive(self, port: int) -> bool:
        return account.rustfs_alive(port)

    def start_rustfs(self) -> None:
        account_lifecycle.start_rustfs()

    def keys(self) -> dict[str, str]:
        try:
            return start_account.server_keys()
        except start_account.LegError as exc:
            raise StackError(str(exc)) from None


@dataclasses.dataclass
class Seeded:
    """What seeding produced: the three tokens, and the machine secret that enrolls the daemon's host."""

    executor: str
    enroll: str
    other: str
    machine_secret_id: str
    machine_secret: str


class Stack:
    def __init__(self, layout: Layout, runtime: Runtime | None = None) -> None:
        self.layout = layout
        self.rt = runtime or Runtime()
        self.state: dict[str, list] = {"groups": [], "containers": [], "compose": [], "vms": []}

    # ── state file ──────────────────────────────────────────────────────────

    def save(self) -> None:
        self.layout.dir.mkdir(parents=True, exist_ok=True)
        self.layout.state_file.write_text(json.dumps(self.state, indent=2) + "\n", encoding="utf-8")

    def load(self) -> bool:
        """True when a state file exists and was read into `self.state`."""
        try:
            data = json.loads(self.layout.state_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return False
        except (OSError, ValueError) as exc:
            raise StackError("%s cannot be read: %s" % (self.layout.state_file, exc)) from None
        for key in self.state:
            self.state[key] = list(data.get(key, []))
        return True

    def recorded(self) -> bool:
        return any(self.state[key] for key in self.state)

    def record_group(self, name: str, pgid: int) -> None:
        """Record a started group with its leader's start time. A leader already unreadable here (`start` None) has exited, so only its surviving members remain, and teardown signals the group without the recycled-id check: the id stays reserved while any member lives, and a recycled leader pid cannot be told apart without a start time to compare."""
        self.state["groups"].append(
            {"name": name, "pgid": pgid, "start": self.rt.group_start(pgid)}
        )
        self.save()

    def record_container(self, name: str) -> None:
        self.state["containers"].append(name)
        self.save()

    def record_vms(self) -> None:
        """The ops VMs `--machines vm` brings up, so a failed step or `down` undoes them too."""
        self.state["vms"].append("ops-basic")
        self.save()

    def record_compose(self, services: list[str]) -> None:
        self.state["compose"].append(services)
        self.save()

    # ── teardown ────────────────────────────────────────────────────────────

    def teardown(self) -> list[str]:
        """Stop everything recorded, newest first, and return the failures; one that fails does not stop the rest.

        The state keeps only the pieces that failed to stop, so a later `down` retries exactly those instead of forgetting them."""
        failures: list[str] = []
        left_groups: list[dict] = []
        for entry in reversed(self.state["groups"]):
            # A leader start time that differs from the recorded one means the id was recycled: signalling it would hit an unrelated process. A leader that has exited (None) is not proof of recycling: the group id stays reserved while any member lives, so the survivors are still signalled (finding c49521fb.1).
            recorded_start = entry.get("start")
            current_start = (
                self.rt.group_start(int(entry["pgid"])) if recorded_start is not None else None
            )
            if current_start is not None and current_start != recorded_start:
                continue
            try:
                self.rt.kill_group(int(entry["pgid"]))
            except ProcessLookupError:
                pass
            except (OSError, subprocess.TimeoutExpired) as exc:
                failures.append("process group %s (%s): %s" % (entry["pgid"], entry["name"], exc))
                left_groups.insert(0, entry)
        left_containers: list[str] = []
        for name in reversed(self.state["containers"]):
            done = self.rt.run(["docker", "rm", "-f", name])
            if done.returncode != 0 and "No such container" not in done.stderr:
                failures.append("container %s: %s" % (name, done.stderr.strip()))
                left_containers.insert(0, name)
        left_compose: list[list[str]] = []
        for services in reversed(self.state["compose"]):
            done = self.rt.run(
                ["docker", "compose", "stop", *services],
                cwd=self.layout.root / "private" / "account",
            )
            if done.returncode != 0:
                failures.append("compose %s: %s" % (" ".join(services), done.stderr.strip()))
                left_compose.insert(0, services)
        left_vms: list[str] = []
        for name in reversed(self.state["vms"]):
            done = self.rt.run([str(self.layout.root / "rdc.sh"), "ops", "down"], timeout=1800)
            if done.returncode != 0:
                failures.append("ops VMs: %s" % done.stderr.strip()[-300:])
                left_vms.insert(0, name)
        self.state["groups"], self.state["containers"], self.state["compose"] = (
            left_groups,
            left_containers,
            left_compose,
        )
        self.state["vms"] = left_vms
        return failures

    def forget_or_keep(self, failures: list[str]) -> None:
        """Remove the state and env files after a clean teardown; keep the state (now only what failed to stop) after a failed one, so `down` can retry it."""
        if failures:
            self.save()
            log.error(
                "%s keeps %d piece(s) that did not stop; run `%s down` again"
                % (self.layout.state_file, len(failures), SELF)
            )
            return
        self.layout.state_file.unlink(missing_ok=True)
        self.layout.env_file.unlink(missing_ok=True)

    def down(self) -> int:
        had = self.load()
        failures = self.teardown() if had else []
        self.forget_or_keep(failures)
        if failures:
            for line in failures:
                log.error("down: " + line)
            return 1
        log.info("stack down" if had else "no stack recorded; nothing to stop")
        return 0

    # ── up ──────────────────────────────────────────────────────────────────

    def up(self, opts: Options) -> int:
        if self.load() and self.recorded():
            raise StackError(
                "%s records a running stack; run `%s down` first" % (self.layout.state_file, SELF)
            )
        busy = [
            p
            for p in (opts.account_port, opts.daemon_port, opts.ssh_port)
            if self.rt.port_answers(p)
        ]
        if self.rt.port_answers(RUSTFS_PORT) or self.rt.rustfs_alive(RUSTFS_PORT):
            busy.append(RUSTFS_PORT)
        if busy:
            raise StackError(
                "port(s) %s already answer; refusing to start a stack over a listener this run did not start"
                % ", ".join(str(p) for p in busy)
            )
        self.layout.dir.mkdir(parents=True, exist_ok=True)
        try:
            env = self.start_all(opts)
        except BaseException:
            failures = self.teardown()
            for line in failures:
                log.error("teardown after a failed up: " + line)
            self.forget_or_keep(failures)
            raise
        self.write_env(env)
        log.info("stack up; env file %s" % self.layout.env_file)
        return 0

    def start_all(self, opts: Options) -> dict[str, str]:
        self.start_rustfs()
        account_url = self.start_account(opts)
        seeded = self.seed(opts)
        machine = self.start_machine(opts)
        self.enroll(account_url, seeded, machine)
        daemon_url = self.start_daemon(opts, account_url, seeded.executor)
        return {
            "ONPREM_ACCOUNT_URL": account_url,
            "ONPREM_ACCOUNT_PORT": str(opts.account_port),
            "ONPREM_ACCOUNT_SQLITE": str(self.layout.sqlite),
            "ONPREM_ACCOUNT_ENTRY": opts.entry,
            "ONPREM_DAEMON_URL": daemon_url,
            "ONPREM_DAEMON_PORT": str(opts.daemon_port),
            "ONPREM_DAEMON_HOME": str(self.layout.daemon_home),
            "ONPREM_CONFIG_NAME": CONFIG_NAME,
            "ONPREM_USER_EMAIL": EMAIL,
            "ONPREM_OTHER_EMAIL": OTHER_EMAIL,
            "ONPREM_EXECUTOR_TOKEN_FILE": str(self.layout.token_file("executor")),
            "ONPREM_ENROLL_TOKEN_FILE": str(self.layout.token_file("enroll")),
            "ONPREM_OTHER_TOKEN_FILE": str(self.layout.token_file("other")),
            "ONPREM_MACHINE_SECRET_ID": seeded.machine_secret_id,
            "ONPREM_MACHINE_SECRET_FILE": str(self.layout.token_file("machine-secret")),
            "ONPREM_RECOVERY_CODE_FILE": str(self.layout.token_file("recovery-code")),
            "ONPREM_STATE_FILE": str(self.layout.state_file),
            "ONPREM_MACHINES": opts.machines,
            "ONPREM_MACHINE_NAME": MACHINE_NAME,
            **machine,
        }

    def start_rustfs(self) -> None:
        log.step("Starting RustFS...")
        self.record_compose(["config-rustfs", "config-rustfs-init"])
        self.rt.start_rustfs()
        if not self.rt.rustfs_alive(RUSTFS_PORT):
            raise StackError("RustFS did not answer on port %d" % RUSTFS_PORT)

    def account_env(self, opts: Options) -> dict[str, str]:
        keys = self.rt.keys()
        for stale in self.layout.dir.glob("account.db*"):
            stale.unlink()
        env = {
            **os.environ,
            "ACCOUNT_ED25519_PRIVATE_KEY": keys["edPriv"],
            "ACCOUNT_ED25519_PUBLIC_KEY": keys["edPub"],
            "ACCOUNT_X25519_PRIVATE_KEY": keys["xPriv"],
            "ACCOUNT_X25519_PUBLIC_KEY": keys["xPub"],
            "ACCOUNT_SERVER_API_KEY": secrets.token_hex(32),
            "ACCOUNT_JWT_SECRET": secrets.token_hex(32),
            "ACCOUNT_CONFIG_SERVER_KEY": secrets.token_hex(32),
            "ROOT_EMAIL": "root@rediacc.invalid",
            "PORT": str(opts.account_port),
            "TEST_MODE": "true",
            "DATABASE_PATH": str(self.layout.sqlite),
            # The single-org fallback of the per-org executor resolver: a revoked agent grant is pushed to this daemon (PLAN-rmcp-agent-grants.md Design 8).
            "EXECUTOR_URL": "http://127.0.0.1:%d" % opts.daemon_port,
        }
        if opts.entry == "on-premise":
            env["ON_PREMISE_MODE"] = "true"
        return env

    def start_account(self, opts: Options) -> str:
        log.step("Starting the account server (%s entry)..." % opts.entry)
        env = self.account_env(opts)
        log_file = self.layout.dir / "account.log"
        if opts.from_source:
            pgid = self.rt.spawn_group(
                ["npx", "--no-install", "tsx", "src/entry/%s.ts" % opts.entry],
                env,
                self.layout.root / "private" / "account",
                log_file,
            )
            self.record_group("account", pgid)
        else:
            if opts.entry != "on-premise":
                raise StackError(
                    "--entry node needs --from-source: the image bundles the on-premise entry"
                )
            self.record_container(ACCOUNT_CONTAINER)
            # `-e NAME` with no value: docker copies NAME from its own environment, so no key sits on argv.
            passthrough = [
                n
                for n in env
                if (n.startswith(("ACCOUNT_", "CONFIG_R2_")) and n != "CONFIG_R2_ENDPOINT")
                or n in {"ROOT_EMAIL", "PORT", "TEST_MODE", "ON_PREMISE_MODE", "EXECUTOR_URL"}
            ]
            # The port is PUBLISHED on loopback rather than sharing the host network: on Docker Desktop a host-network container binds inside the VM, so the stack's own health check never reached it (measured 2026-11-24, `curl 127.0.0.1:4910` refused while the server answered inside the container). The blob store lives on the host, so the container reaches it as host.docker.internal.
            port = opts.account_port
            argv = ["docker", "run", "-d", "--name", ACCOUNT_CONTAINER]
            argv += ["-p", "127.0.0.1:%d:%d" % (port, port)]
            argv += ["--add-host", "host.docker.internal:host-gateway"]
            argv += ["-v", "%s:/data" % self.layout.dir, "-e", "DATABASE_PATH=/data/account.db"]
            endpoint = env.get("CONFIG_R2_ENDPOINT", "")
            if endpoint:
                argv += [
                    "-e",
                    "CONFIG_R2_ENDPOINT=" + endpoint.replace("127.0.0.1", "host.docker.internal"),
                ]
            for name in passthrough:
                argv += ["-e", name]
            argv.append(IMAGE)
            done = self.rt.run(argv, env=env)
            if done.returncode != 0:
                raise StackError("docker run %s failed: %s" % (IMAGE, done.stderr.strip()))
        url = "http://127.0.0.1:%d" % opts.account_port
        self.wait_http(url + "/health", "the account server")
        return url

    def wait_http(self, url: str, what: str, accept: str | None = None) -> str:
        """The body of the first 2xx answer of `url` (containing `accept` when given); refused after the health window."""
        for _ in range(HEALTH_TRIES):
            code, body = self.rt.http_get(url)
            if 200 <= code < 300 and (accept is None or accept in body):
                return body
            self.rt.sleep(HEALTH_INTERVAL)
        raise StackError(
            "%s never answered %s within %ds" % (what, url, int(HEALTH_TRIES * HEALTH_INTERVAL))
        )

    def write_token(self, name: str, token: str) -> None:
        fd = os.open(self.layout.token_file(name), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")

    def seed(self, opts: Options) -> Seeded:
        log.step("Seeding the account server...")
        port = opts.account_port
        executor = self.rt.seed(port, EMAIL, "onprem-executor", ["proxy:exec"])
        enroll = self.rt.seed(port, EMAIL, "onprem-enroll", ["config:enroll"])
        other = self.rt.seed(port, OTHER_EMAIL, "onprem-other", ["proxy:exec"])
        store = self.rt.seed_store(port, EMAIL)
        # A suite that needs a second device enrols it with the same machine secret, so it is a file like the tokens.
        for name, token in (
            ("executor", executor),
            ("enroll", enroll),
            ("other", other),
            ("machine-secret", str(store["machineSecret"])),
        ):
            self.write_token(name, token)
        # The owner's recovery code opens the store's CEK for the `grants` suite's seeded grants.
        if store.get("recoveryCode"):
            self.write_token("recovery-code", str(store["recoveryCode"]))
        return Seeded(
            executor, enroll, other, str(store["machineSecretId"]), str(store["machineSecret"])
        )

    def start_machine(self, opts: Options) -> dict[str, str]:
        if opts.machines == "vm":
            log.step("Bringing up the ops VMs (./rdc.sh ops up --basic)...")
            rdc = str(self.layout.root / "rdc.sh")
            self.record_vms()
            done = self.rt.run([rdc, "ops", "up", "--basic"], timeout=3600)
            if done.returncode != 0:
                raise StackError(
                    "ops up --basic exited %d: %s" % (done.returncode, done.stderr.strip()[-300:])
                )
            return {
                "ONPREM_MACHINE_IP": "192.168.111.11",
                "ONPREM_MACHINE_PORT": "22",
                "ONPREM_MACHINE_USER": "root",
            }
        log.step("Starting the container machine...")
        key = self.layout.ssh_key
        pub = pathlib.Path(str(key) + ".pub")
        key.unlink(missing_ok=True)
        pub.unlink(missing_ok=True)
        done = self.rt.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)])
        if done.returncode != 0:
            raise StackError("ssh-keygen failed: %s" % done.stderr.strip())
        script = (
            "apk add --no-cache openssh >/dev/null && ssh-keygen -A >/dev/null && "
            "sed -i 's/^root:!:/root:*:/' /etc/shadow && mkdir -p /root/.ssh && "
            'echo "$AUTHORIZED_KEY" > /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys && '
            "exec /usr/sbin/sshd -D -e"
        )
        self.record_container(MACHINE_CONTAINER)
        done = self.rt.run(
            [
                "docker", "run", "-d", "--name", MACHINE_CONTAINER,
                "-p", "127.0.0.1:%d:22" % opts.ssh_port,
                "-e", "AUTHORIZED_KEY=" + pub.read_text(encoding="utf-8").strip(),
                MACHINE_IMAGE, "sh", "-c", script,
            ]
        )  # fmt: skip
        if done.returncode != 0:
            raise StackError("docker run %s failed: %s" % (MACHINE_IMAGE, done.stderr.strip()))
        for _ in range(HEALTH_TRIES):
            if self.rt.port_answers(opts.ssh_port):
                break
            self.rt.sleep(HEALTH_INTERVAL)
        else:
            raise StackError("the container machine never answered on port %d" % opts.ssh_port)
        return {
            "ONPREM_MACHINE_IP": "127.0.0.1",
            "ONPREM_MACHINE_PORT": str(opts.ssh_port),
            "ONPREM_MACHINE_USER": "root",
            "ONPREM_MACHINE_KEY": str(key),
        }

    def cli_env(self, account_url: str, token: str) -> dict[str, str]:
        self.layout.daemon_home.mkdir(parents=True, exist_ok=True)
        return {
            **os.environ,
            "XDG_CONFIG_HOME": str(self.layout.daemon_home),
            "REDIACC_ACCOUNT_SERVER": account_url,
            "REDIACC_TOKEN": token,
        }

    def rdc(self, env: dict[str, str], *args: str) -> None:
        argv = [str(self.layout.root / "rdc.sh"), *args]
        done = self.rt.run(argv, env=env, cwd=self.layout.root)
        if done.returncode != 0:
            raise StackError(
                "rdc %s exited %d: %s"
                % (" ".join(args[:3]), done.returncode, done.stderr.strip()[-300:])
            )

    def enroll(self, account_url: str, seeded: Seeded, machine: dict[str, str]) -> None:
        log.step("Enrolling the daemon's config...")
        # A config left by an earlier `up` makes `config init` refuse, so every start begins from an empty config home, as it begins from an empty account database.
        shutil.rmtree(self.layout.daemon_home, ignore_errors=True)
        env = self.cli_env(account_url, seeded.enroll)
        self.rdc(env, "config", "init", CONFIG_NAME)
        self.rdc(
            env, "--config", CONFIG_NAME, "machine", "add", MACHINE_NAME,
            "--ip", machine["ONPREM_MACHINE_IP"],
            "--user", machine["ONPREM_MACHINE_USER"],
            "--port", machine["ONPREM_MACHINE_PORT"],
        )  # fmt: skip
        if machine.get("ONPREM_MACHINE_KEY"):
            # The machine's throwaway key is the only one its sshd accepts; without it the CLI answers SSH_AUTH_FAILED.
            self.rdc(
                env, "--config", CONFIG_NAME, "config", "ssh", "set",
                "--key", machine["ONPREM_MACHINE_KEY"],
            )  # fmt: skip
        # The secret reaches the CLI through its environment, never argv.
        self.rdc(
            {**env, "REDIACC_MACHINE_SECRET": seeded.machine_secret},
            "--config", CONFIG_NAME, "config", "remote", "enable",
            "--machine-secret", seeded.machine_secret_id,
            "--api-url", account_url,
        )  # fmt: skip

    def start_daemon(self, opts: Options, account_url: str, executor_token: str) -> str:
        log.step("Starting the daemon executor...")
        argv = [
            str(self.layout.root / "rdc.sh"), "--config", CONFIG_NAME,
            "serve", "--mode", "daemon", "--host", "127.0.0.1", "--port", str(opts.daemon_port),
        ]  # fmt: skip
        pgid = self.rt.spawn_group(
            argv,
            self.cli_env(account_url, executor_token),
            self.layout.root,
            self.layout.dir / "daemon.log",
        )
        self.record_group("daemon", pgid)
        url = "http://127.0.0.1:%d" % opts.daemon_port
        body = self.wait_http(url + "/v1/server-info", "the daemon", accept="daemon")
        try:
            mode = json.loads(body).get("mode")
        except (ValueError, AttributeError):
            mode = None
        if mode != "daemon":
            raise StackError("the executor answered /v1/server-info as %r, not 'daemon'" % mode)
        return url

    def write_env(self, values: dict[str, str]) -> None:
        text = "".join("%s=%s\n" % (k, v) for k, v in values.items())
        self.layout.env_file.write_text(text, encoding="utf-8")

    def status(self) -> int:
        if not self.load() or not self.recorded():
            log.info("no stack recorded")
            return 1
        for entry in self.state["groups"]:
            try:
                os.killpg(int(entry["pgid"]), 0)
                alive = "running"
            except ProcessLookupError:
                alive = "gone"
            log.info("group %s pgid %s %s" % (entry["name"], entry["pgid"], alive))
        for name in self.state["containers"]:
            log.info("container %s" % name)
        return 0


def parse(argv: list[str]) -> tuple[str, Options]:
    if not argv or argv[0] not in ("up", "down", "status"):
        raise ValueError(USAGE)
    action, rest = argv[0], argv[1:]
    opts = Options()
    values = {
        "--machines": "machines",
        "--entry": "entry",
        "--account-port": "account_port",
        "--daemon-port": "daemon_port",
        "--ssh-port": "ssh_port",
    }
    i = 0
    while i < len(rest):
        flag = rest[i]
        if flag == "--from-source" and action == "up":
            opts.from_source = True
            i += 1
            continue
        if action != "up" or flag not in values:
            raise ValueError("Unknown option: %s\n%s" % (flag, USAGE))
        if i + 1 >= len(rest) or not rest[i + 1]:
            raise ValueError("%s needs a value" % flag)
        value: str | int = rest[i + 1]
        if values[flag].endswith("_port"):
            if not str(value).isdigit() or not 0 < int(value) < 65536:
                raise ValueError("%s needs a port number" % flag)
            value = int(value)
        setattr(opts, values[flag], value)
        i += 2
    if opts.machines not in MACHINE_KINDS:
        raise ValueError("--machines is one of %s" % ", ".join(MACHINE_KINDS))
    if opts.entry not in ENTRIES:
        raise ValueError("--entry is one of %s" % ", ".join(ENTRIES))
    return action, opts


def main(argv: list[str], runtime: Runtime | None = None, root: pathlib.Path | None = None) -> int:
    try:
        action, opts = parse(argv)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if runtime is None and action == "up" and shutil.which("docker") is None:
        log.error("docker is not on PATH; the stack needs it for RustFS and the machine")
        return 1
    stack = Stack(Layout(root or paths.repo_root()), runtime)
    try:
        if action == "up":
            return stack.up(opts)
        if action == "down":
            return stack.down()
        return stack.status()
    except StackError as exc:
        log.error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
