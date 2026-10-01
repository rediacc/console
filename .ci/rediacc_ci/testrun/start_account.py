"""Port of `.ci/scripts/test/start-account-for-e2e.sh`: start a throwaway account server for an E2E leg and mint the API token that leg's suite needs.

Prints, and under Actions appends to `$GITHUB_ENV`, `REDIACC_ACCOUNT_SERVER` and `E2E_ACCOUNT_API_TOKEN`. The two ordering rules of the twin are kept and are why this is not a plain HTTP helper: the CLI must be the token's FIRST user (so it is minted over the cookie session and never presented again here), and the server must outlive the step (own session, listener pid recorded from the LISTENING SOCKET, never from the `npx` wrapper).

Deliberate differences from the twin (Rule T), each with a test that fails on the bash behaviour:

  1. `curl -sS` with no `-f` let an HTTP 4xx/5xx from `/test/ensure-login` or `/test/ensure-subscription` pass as success, so a TEST_MODE-less server was found out three calls later through a confusing jq failure. A non-2xx answer fails at the call that got it.
  2. A leg that failed after the server had started left the server running (and the port bound) on any local run. The server's process group is terminated on every failure path; on success it is deliberately left alive.
  3. A stale server already answering `/health` on the port made the twin seed and mint against THAT server, whose keys it had never seen. A port that already answers is refused before anything starts.
  4. `--port` with no value was a raw bash `parameter null or not set` diagnostic and exit 1; it is a usage error, exit 2, like the unknown option next to it.
  5. The throwaway secrets come from `secrets.token_hex` instead of `openssl rand -hex 32`, whose silent failure left them empty in the sibling `ci-env.sh` (see `infra/ci_env.py`). Same shape, 64 hex characters.
  6. The cookie jar lives in memory; the twin wrote and removed `account-for-e2e-cookies.txt`.
"""

import contextlib
import http.client
import json
import os
import pathlib
import secrets
import shutil
import signal
import subprocess
import sys
import time

from rediacc_ci import log, paths

LOGIN_PHRASE = "E2eClusterLicensing123!"
HEALTH_TRIES = 60
HEALTH_INTERVAL = 2.0
KEYGEN_PROGRAM = """
const crypto = require("crypto");
const ed = crypto.generateKeyPairSync("ed25519");
const x = crypto.generateKeyPairSync("x25519");
const der = (k, t) => k.export({ type: t, format: "der" }).toString("base64");
console.log(JSON.stringify({
  edPriv: der(ed.privateKey, "pkcs8"),
  edPub: der(ed.publicKey, "spki"),
  xPriv: der(x.privateKey, "pkcs8"),
  xPub: der(x.publicKey, "spki"),
}));
"""
SCOPES = ["license:read", "license:activate", "subscription:read"]
USAGE = (
    "usage: start-account-for-e2e.sh [--port <n>] [--email <addr>] [--plan <code>] [--name <label>]"
)


class LegError(Exception):
    """The leg cannot continue. `show_log` attaches the server log tail."""

    def __init__(self, message: str, show_log: bool = True) -> None:
        super().__init__(message)
        self.show_log = show_log


class Options:
    def __init__(self) -> None:
        self.port = os.environ.get("ACCOUNT_API_PORT") or "4900"
        self.email = "e2e-cluster-licensing@rediacc.io"
        self.plan = "PROFESSIONAL"
        self.name = "e2e-cluster-licensing"


def parse(argv: list[str]) -> Options:
    opts = Options()
    names = {"--port": "port", "--email": "email", "--plan": "plan", "--name": "name"}
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag not in names:
            raise ValueError(f"Unknown option: {flag}")
        if i + 1 >= len(argv) or argv[i + 1] == "":
            raise ValueError(f"{flag} needs a value")
        setattr(opts, names[flag], argv[i + 1])
        i += 2
    return opts


def generate_keys() -> dict[str, str]:
    done = subprocess.run(
        ["node", "-e", KEYGEN_PROGRAM],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if done.returncode != 0:
        raise LegError(
            f"node could not generate the throwaway keys: {done.stderr.strip()}", show_log=False
        )
    return json.loads(done.stdout)


class Api:
    """The account API over HTTP with one cookie session (a name=value jar; the twin used curl's cookie file)."""

    def __init__(self, port: str, prefix: str) -> None:
        self.port = int(port)
        self.prefix = prefix
        self.cookies: dict[str, str] = {}

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, str]:
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, self.prefix + path, body=payload, headers=headers)
            response = connection.getresponse()
            text = response.read().decode("utf-8", errors="replace")
            for header in response.headers.get_all("Set-Cookie") or []:
                name, _, rest = header.partition("=")
                self.cookies[name.strip()] = rest.partition(";")[0]
            return response.status, text
        except (OSError, http.client.HTTPException) as exc:
            raise LegError(f"{method} {path} failed: {exc}") from exc
        finally:
            connection.close()


def healthy(port: str) -> bool:
    try:
        connection = http.client.HTTPConnection("127.0.0.1", int(port), timeout=2)
        try:
            connection.request("GET", "/health")
            return 200 <= connection.getresponse().status < 300
        finally:
            connection.close()
    except (OSError, ValueError, http.client.HTTPException):
        return False


def listener_pid(port: str) -> str:
    if not shutil.which("lsof"):
        return ""
    done = subprocess.run(
        ["lsof", f"-ti:{port}", "-sTCP:LISTEN"], capture_output=True, text=True, check=False
    )
    lines = done.stdout.split()
    return lines[0] if lines else ""


def tail(path: pathlib.Path, count: int = 40) -> str:
    try:
        return "\n".join(path.read_text(errors="replace").splitlines()[-count:])
    except OSError:
        return ""


def start_server(
    opts: Options,
    account_dir: pathlib.Path,
    log_file: pathlib.Path,
    db_path: pathlib.Path,
    keys: dict[str, str],
) -> subprocess.Popen:
    for suffix in ("", "-wal", "-shm"):
        pathlib.Path(str(db_path) + suffix).unlink(missing_ok=True)
    env = {
        **os.environ,
        "ACCOUNT_ED25519_PRIVATE_KEY": keys["edPriv"],
        "ACCOUNT_ED25519_PUBLIC_KEY": keys["edPub"],
        "ACCOUNT_X25519_PRIVATE_KEY": keys["xPriv"],
        "ACCOUNT_X25519_PUBLIC_KEY": keys["xPub"],
        # envSchema requires >= 32 characters for both; random 64-hex satisfies it without inventing a secret.
        "ACCOUNT_SERVER_API_KEY": secrets.token_hex(32),
        "ACCOUNT_JWT_SECRET": secrets.token_hex(32),
        "ROOT_EMAIL": "root@rediacc.invalid",
        "DATABASE_PATH": str(db_path),
        "PORT": opts.port,
        "TEST_MODE": "true",
    }
    with open(log_file, "wb") as sink:
        return subprocess.Popen(
            ["npx", "tsx", "src/entry/node.ts"],
            cwd=account_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def run(opts: Options) -> int:
    root = paths.repo_root()
    account_dir = root / "private" / "account"
    temp = os.environ.get("RUNNER_TEMP") or "/tmp"
    log_file = pathlib.Path(temp) / "account-for-e2e.log"
    pid_file = pathlib.Path(temp) / "account-for-e2e.pid"
    if not (account_dir / "package.json").is_file():
        log.error("private/account is not checked out; this leg cannot start an account server.")
        log.error("The job must check out with submodules: true.")
        return 1

    server: subprocess.Popen | None = None
    try:
        if healthy(opts.port):
            raise LegError(
                f"Something already answers /health on port {opts.port}; refusing to seed a server this run did not start.",
                show_log=False,
            )
        log.step("Generating throwaway server keys...")
        keys = generate_keys()
        log.step(f"Starting account server on port {opts.port}...")
        db_path = pathlib.Path(temp) / f"e2e-account-{os.getpid()}.db"
        try:
            server = start_server(opts, account_dir, log_file, db_path, keys)
        except OSError as exc:
            raise LegError(f"npx could not start: {exc.strerror or exc}", show_log=False) from exc
        log.info(f"account server starting, log {log_file}")

        # The readiness test is the PORT, not a pid: `npx` forks, so the launched pid is the wrapper and the server is its grandchild.
        log.step("Waiting for the account server to answer /health...")
        for _ in range(HEALTH_TRIES):
            if healthy(opts.port):
                break
            time.sleep(HEALTH_INTERVAL)
        else:
            raise LegError(
                f"The account server never became healthy on port {opts.port} within {int(HEALTH_TRIES * HEALTH_INTERVAL)}s."
            )

        pid = listener_pid(opts.port)
        if pid:
            pid_file.write_text(pid + "\n")
            log.info(f"account server healthy, listener pid {pid} (recorded in {pid_file})")
        else:
            log.info("account server healthy (no pid resolved; lsof unavailable)")

        token, subscription_id = seed_and_mint(Api(opts.port, "/account/api/v1"), opts)
    except LegError as exc:
        log.error(str(exc))
        if exc.show_log and log_file.exists():
            log.error(f"Last 40 lines of {log_file}:")
            print(tail(log_file), file=sys.stderr)
        if server is not None:
            terminate(server)
        return 1

    server_url = f"http://127.0.0.1:{opts.port}"
    log.info(f"subscription {subscription_id}, token {token[:12]}...")
    publish(server_url, token)
    return 0


def seed_and_mint(api: Api, opts: Options) -> tuple[str, str]:
    """Seed a subscribed user, then mint its token over the cookie session. The token is never presented again here."""
    log.step(f"Seeding a {opts.plan} subscription for {opts.email}...")
    credentials = {"email": opts.email, "password": LOGIN_PHRASE}
    code, _ = api.call("POST", "/test/ensure-login", credentials)
    if not 200 <= code < 300:
        raise LegError(f"/test/ensure-login failed with HTTP {code} (is TEST_MODE on?)")
    code, _ = api.call(
        "POST", "/test/ensure-subscription", {"email": opts.email, "planCode": opts.plan}
    )
    if not 200 <= code < 300:
        raise LegError(f"/test/ensure-subscription failed with HTTP {code}")

    _, login = api.call("POST", "/auth/login", credentials)
    if not _json_get(login, "user", "id"):
        log.error(f"Headless login failed: {login}")
        raise LegError(f"could not open a session for {opts.email}")
    _, subscription = api.call("GET", "/portal/subscription")
    subscription_id = _json_get(subscription, "id") or ""
    if not subscription_id:
        raise LegError(f"no subscription id for {opts.email} after seeding")
    _, minted = api.call(
        "POST",
        "/api-tokens",
        {"subscriptionId": subscription_id, "name": opts.name, "scopes": SCOPES},
    )
    token = _json_get(minted, "token") or ""
    if not token:
        log.error(f"API token mint failed: {minted}")
        raise LegError("could not mint an API token")
    return str(token), str(subscription_id)


def _json_get(text: str, *keys: str) -> object:
    """`jq -r '.a.b // empty'`: the value, or None for absent, null or false."""
    try:
        value: object = json.loads(text)
    except ValueError:
        return None
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value or None


def terminate(server: subprocess.Popen) -> None:
    """Stop the server and everything it forked (it leads its own session)."""
    try:
        os.killpg(server.pid, signal.SIGTERM)
    except OSError:
        return
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(server.pid, signal.SIGKILL)


def publish(server_url: str, token: str) -> None:
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        # Not a `secrets.*` value, so Actions would not mask it on its own.
        print(f"::add-mask::{token}")
        with open(github_env, "a", encoding="utf-8") as handle:
            handle.write(f"REDIACC_ACCOUNT_SERVER={server_url}\nE2E_ACCOUNT_API_TOKEN={token}\n")
        log.info("exported REDIACC_ACCOUNT_SERVER and E2E_ACCOUNT_API_TOKEN to $GITHUB_ENV")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"server-url={server_url}\n")
    # Bare stdout for a local caller: `eval "$(... | tail -2)"`.
    print(f"REDIACC_ACCOUNT_SERVER={server_url}")
    print(f"E2E_ACCOUNT_API_TOKEN={token}", flush=True)


def main(argv: list[str]) -> int:
    try:
        opts = parse(argv)
    except ValueError as exc:
        log.error(str(exc))
        print(USAGE, file=sys.stderr)
        return 2
    return run(opts)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
