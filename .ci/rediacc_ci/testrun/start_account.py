"""Port of `.ci/scripts/test/start-account-for-e2e.sh`: start a throwaway account server for an E2E leg and mint the API token that leg's suite needs.

Prints, and under Actions appends to `$GITHUB_ENV`, `REDIACC_ACCOUNT_SERVER`, `ACCOUNT_ED25519_PUBLIC_KEY` (the signer's public half, see delta 7) and `E2E_ACCOUNT_API_TOKEN`. The two ordering rules of the twin are kept and are why this is not a plain HTTP helper: the CLI must be the token's FIRST user (so it is minted over the cookie session and never presented again here), and the server must outlive the step (own session, listener pid recorded from the LISTENING SOCKET, never from the `npx` wrapper).

Deliberate differences from the twin (Rule T), each with a test that fails on the bash behaviour:

  1. `curl -sS` with no `-f` let an HTTP 4xx/5xx from `/test/ensure-login` or `/test/ensure-subscription` pass as success, so a TEST_MODE-less server was found out three calls later through a confusing jq failure. A non-2xx answer fails at the call that got it.
  2. A leg that failed after the server had started left the server running (and the port bound) on any local run. The server's process group is terminated on every failure path; on success it is deliberately left alive.
  3. A stale server already answering `/health` on the port made the twin seed and mint against THAT server, whose keys it had never seen. A port that already answers is refused before anything starts.
  4. `--port` with no value was a raw bash `parameter null or not set` diagnostic and exit 1; it is a usage error, exit 2, like the unknown option next to it.
  5. The throwaway secrets come from `secrets.token_hex` instead of `openssl rand -hex 32`, whose silent failure left them empty in the retired `ci-env.sh` (see `infra/ci_env.py`). Same shape, 64 hex characters.
  6. The cookie jar lives in memory; the twin wrote and removed `account-for-e2e-cookies.txt`.
  7. The ED25519 signing pair is taken from the environment when BOTH `ACCOUNT_ED25519_PRIVATE_KEY` and `ACCOUNT_ED25519_PUBLIC_KEY` are set (the twin always minted its own), and the PUBLIC half is published as `ACCOUNT_ED25519_PUBLIC_KEY` next to `REDIACC_ACCOUNT_SERVER`. A renet build has to bake the signer's public key, or every licence this server signs is filed under a fingerprint renet never looks up (`start_backup_plane`). The private half is never printed or written.
  8. A CI leg signs with a pair minted here, per run (agent/plans/PLAN-production-key-only.md D6): the production private key never reaches a CI job. The leg builds renet AFTER this step, with the public half this step publishes, so every licence the server signs is filed under the fingerprint that renet looks up. `--require-env-pair`, which demanded the production pair from Bitwarden for the run's one shared production-keyed renet, is gone, and passing it is a usage error. `--emit-pair` mints a pair for a caller that starts its own server (rediacc_ci.testrun.account_e2e) and prints it as two `export` lines for that step's `eval`; nothing starts and nothing is written.
  9. `ACCOUNT_SERVER_API_KEY` is taken from the environment when set (the twin always minted it), so a caller that drives the server's X-API-Key routes, such as renet's subscription system tests, holds the key without this leg ever printing it.
  10. `ACCOUNT_CONFIG_SERVER_KEY` is taken from the environment when set, else minted like the JWT secret. The node entry refuses to boot when `CONFIG_R2_*` is set without it, and the backup plane's RustFS step exports `CONFIG_R2_*` into this server's environment.
"""

import contextlib
import http.client
import json
import os
import pathlib
import secrets
import shlex
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
DERIVE_PUBLIC_PROGRAM = """
const crypto = require("crypto");
const priv = crypto.createPrivateKey({ key: Buffer.from(process.env.ACCOUNT_ED25519_PRIVATE_KEY, "base64"), format: "der", type: "pkcs8" });
process.stdout.write(crypto.createPublicKey(priv).export({ type: "spki", format: "der" }).toString("base64"));
"""
SCOPES = ["license:read", "license:activate", "subscription:read"]
USAGE = "usage: PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_account [--port <n>] [--email <addr>] [--plan <code>] [--name <label>] [--scopes <a,b>] [--advertise-host <ip>] | --emit-pair"


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
        self.scopes = ",".join(SCOPES)
        # The host the published account server URL names; the server itself is always probed and seeded on 127.0.0.1.
        self.advertise_host = "127.0.0.1"
        # Delta 8: print a freshly minted ED25519 pair as `export` lines and start nothing.
        self.emit_pair = False


def parse(argv: list[str]) -> Options:
    opts = Options()
    names = {
        "--port": "port",
        "--email": "email",
        "--plan": "plan",
        "--name": "name",
        "--scopes": "scopes",
        "--advertise-host": "advertise_host",
    }
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--emit-pair":
            opts.emit_pair = True
            i += 1
            continue
        if flag not in names:
            raise ValueError(f"Unknown option: {flag}")
        if i + 1 >= len(argv) or argv[i + 1] == "":
            raise ValueError(f"{flag} needs a value")
        setattr(opts, names[flag], argv[i + 1])
        i += 2
    if not token_scopes(opts):
        raise ValueError("--scopes needs at least one scope")
    return opts


def token_scopes(opts: Options) -> list[str]:
    """The comma-separated `--scopes` value as the list the mint request carries."""
    return [scope.strip() for scope in opts.scopes.split(",") if scope.strip()]


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


def server_keys() -> dict[str, str]:
    """The throwaway key set, with the ED25519 signing pair taken from the environment when BOTH halves are there.

    The normal case, and every CI leg's (delta 8), is a pair minted here: the leg builds renet afterwards with the public half `publish` exports. A caller that bakes the public half into a renet build BEFORE this server starts (`start_backup_plane`) hands its own pair in through the environment instead, and a pair whose halves do not match is refused, because the server would sign licences that do not verify under the key the renet bakes. Half a pair is ignored: a lone public key would sign nothing, and a lone private key has no matching public half to publish. The private half is passed to the server through its environment only, never printed or written.
    """
    private = os.environ.get("ACCOUNT_ED25519_PRIVATE_KEY", "").strip()
    public = os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", "").strip()
    keys = generate_keys()
    if private and public:
        if derived_public_key() != public:
            raise LegError(
                "ACCOUNT_ED25519_PRIVATE_KEY and ACCOUNT_ED25519_PUBLIC_KEY are not one pair: the server would sign licences that do not verify under the published key",
                show_log=False,
            )
        log.info("signing with the ACCOUNT_ED25519_* pair from the environment")
        keys = {**keys, "edPriv": private, "edPub": public}
    return keys


def derived_public_key() -> str:
    """The SPKI base64 public half of ACCOUNT_ED25519_PRIVATE_KEY (PKCS8 base64), derived by node from the ENVIRONMENT so the private key never reaches argv. A node that cannot run, or cannot parse the key, is a LegError naming node's own error, so it is never misreported as a mismatched pair."""
    try:
        done = subprocess.run(
            ["node", "-e", DERIVE_PUBLIC_PROGRAM],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise LegError(
            f"node could not run to check the signing pair: {exc}", show_log=False
        ) from exc
    if done.returncode != 0:
        raise LegError(
            f"node could not derive the public half of ACCOUNT_ED25519_PRIVATE_KEY: {done.stderr.strip()}",
            show_log=False,
        )
    return done.stdout.strip()


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


def reap_recorded(port: str, pid_file: pathlib.Path, wait_s: float = 10.0) -> bool:
    """Stop the server an earlier run of this tool left on `port`: only when `pid_file` names the pid that still listens there.

    A successful run leaves its server running on purpose (the suite that follows needs it), so the next run is where it is stopped; a listener this tool did not record is never touched and the caller still refuses it. True once the port is free: `/health` no longer answers AND nothing listens there, since a server can stop answering while it still holds the socket, and the next server would fail to bind. A pid file names whichever run wrote it last, so two live runs on one port and one temp directory are not told apart; the second stops the first's server instead of being refused, which is why each CI job has its own runner and its own `RUNNER_TEMP`.
    """
    try:
        recorded = pid_file.read_text().strip()
    except OSError:
        return False
    if not recorded.isdigit() or listener_pid(port) != recorded:
        return False
    try:
        os.kill(int(recorded), signal.SIGTERM)
    except OSError:
        return False
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        if not healthy(port) and not listener_pid(port):
            pid_file.unlink(missing_ok=True)
            return True
        time.sleep(0.25)
    return False


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
        # Delta 9: a caller that drives the X-API-Key routes (renet's subscription system tests, agent/plans/PLAN-free-license.md F2) supplies its own key in the environment, never printed here.
        "ACCOUNT_SERVER_API_KEY": os.environ.get("ACCOUNT_SERVER_API_KEY") or secrets.token_hex(32),
        "ACCOUNT_JWT_SECRET": secrets.token_hex(32),
        # Delta 10: the node entry refuses to boot with CONFIG_R2_* set and no ACCOUNT_CONFIG_SERVER_KEY (private/account/src/entry/node.ts), and `start_backup_plane` starts RustFS, which exports CONFIG_R2_*, before this server. A throwaway per-run key (or the caller's) keeps that refusal intact and gives the config routes a key.
        "ACCOUNT_CONFIG_SERVER_KEY": os.environ.get("ACCOUNT_CONFIG_SERVER_KEY")
        or secrets.token_hex(32),
        "ROOT_EMAIL": "root@rediacc.invalid",
        "DATABASE_PATH": str(db_path),
        "PORT": opts.port,
        "TEST_MODE": "true",
    }
    with open(log_file, "wb") as sink:
        return subprocess.Popen(
            ["npx", "--no-install", "tsx", "src/entry/node.ts"],
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
        occupied = healthy(opts.port)
        if occupied and reap_recorded(opts.port, pid_file):
            log.info(
                f"stopped the account server an earlier run left on port {opts.port} (pid recorded in {pid_file})"
            )
            occupied = False
        if occupied:
            raise LegError(
                f"Something already answers /health on port {opts.port}; refusing to seed a server this run did not start.",
                show_log=False,
            )
        log.step("Generating throwaway server keys...")
        keys = server_keys()
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

    server_url = f"http://{opts.advertise_host}:{opts.port}"
    log.info(f"subscription {subscription_id}, token {token[:12]}...")
    publish(server_url, token, keys["edPub"])
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
        {"subscriptionId": subscription_id, "name": opts.name, "scopes": token_scopes(opts)},
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


def publish(server_url: str, token: str, public_key: str) -> None:
    """The server URL, the token and the PUBLIC signing key (unmasked: it is public, and a renet build bakes it). The private half never reaches this function."""
    # In-process, so a follow-on command exec'd by `start_backup_plane -- <cmd>` inherits them (a local run has no $GITHUB_ENV).
    os.environ.update(
        REDIACC_ACCOUNT_SERVER=server_url,
        ACCOUNT_ED25519_PUBLIC_KEY=public_key,
        E2E_ACCOUNT_API_TOKEN=token,
    )
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        # Not a `secrets.*` value, so Actions would not mask it on its own. Off Actions the line is a workflow command nobody consumes,
        # only the token in plain text in a terminal or a captured log (the start_backup_plane.export_credentials rule).
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::add-mask::{token}")
        with open(github_env, "a", encoding="utf-8") as handle:
            handle.write(
                f"REDIACC_ACCOUNT_SERVER={server_url}\n"
                f"ACCOUNT_ED25519_PUBLIC_KEY={public_key}\n"
                f"E2E_ACCOUNT_API_TOKEN={token}\n"
            )
        log.info(
            "exported REDIACC_ACCOUNT_SERVER, ACCOUNT_ED25519_PUBLIC_KEY and E2E_ACCOUNT_API_TOKEN to $GITHUB_ENV"
        )
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"server-url={server_url}\n")
    # Bare stdout for a local caller: `eval "$(... | tail -2)"` (the public key line sits above the two the twin printed, so `tail -2` still reads them).
    print(f"ACCOUNT_ED25519_PUBLIC_KEY={public_key}")
    print(f"REDIACC_ACCOUNT_SERVER={server_url}")
    print(f"E2E_ACCOUNT_API_TOKEN={token}", flush=True)


def emit_pair() -> int:
    """Delta 8: a fresh ED25519 pair as two shell `export` lines on stdout, for `pair="$(... --emit-pair)"` then `eval "$pair"` in the one step that starts its own server. The pair is throwaway and verifies nothing outside that step; the assignment form keeps a failed mint fatal under `bash -e`, where a bare `eval "$(...)"` would swallow it."""
    try:
        keys = generate_keys()
    except LegError as exc:
        log.error(str(exc))
        return 1
    print(f"export ACCOUNT_ED25519_PRIVATE_KEY={shlex.quote(keys['edPriv'])}")
    print(f"export ACCOUNT_ED25519_PUBLIC_KEY={shlex.quote(keys['edPub'])}", flush=True)
    return 0


def main(argv: list[str]) -> int:
    try:
        opts = parse(argv)
    except ValueError as exc:
        log.error(str(exc))
        print(USAGE, file=sys.stderr)
        return 2
    if opts.emit_pair:
        return emit_pair()
    return run(opts)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
