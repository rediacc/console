"""I7: the on-premise account server against RustFS, with the S3 conformance probe.

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup_onprem [--selftest] [--keep-work]

WHAT IT IS FOR. The backup drill (`rediacc_ci.drills.backup`) drives the dev gateway, which is `src/entry/dev-gateway.ts`. An Elite customer runs `src/entry/on-premise.ts`, a different entry with its own route factory (no admin, no Stripe) and its own boot path (SQLite, a delegation-cert loader, `createBackupPlane` over the bundled RustFS). A backup plane that works under the dev gateway and is absent or misconfigured under the on-premise entry is exactly the defect the dev gateway cannot show, so this variant boots THAT entry and asks it the questions the elite deployment depends on. The result is the `onprem` half of the backup receipt (`backup_check_trigger.record(onprem=...)`).

WHAT IT DOES, one claim per row:
  1. `private/elite/scripts/s3-conformance-probe.sh` passes against the RustFS bucket (presigned round trip, create-only PUT refused with 412, HEAD, batch delete, multipart), and the same probe against a closed port FAILS (the planted control: a probe that cannot fail proves nothing).
  2. `src/entry/on-premise.ts` boots with `ON_PREMISE_MODE=true` and `ACCOUNT_BACKUP_S3_*` pointing at that bucket, over throwaway keys and a throwaway SQLite file, and answers `server-info`.
  3. Its boot log reports the configured chunk store (`Backup chunk storage: <endpoint>/<bucket>`), not `not configured`.
  4. The backup routes are mounted (`GET /backups/usage` without a credential answers 401, never 404 for a missing route and never 503 `BACKUP_NOT_CONFIGURED`).
  5. The on-premise factory still leaves the admin surface out: the dev-only `/test` seam answers 404, and so does `/admin`.

NOT PROVEN HERE, said plainly: a backup session needs a licence from a delegated deployment (a delegation cert from the upstream key), which this drill has no way to mint; the session, grant and restore legs run against the dev gateway in `rediacc_ci.drills.backup`.

NO NEW ENVIRONMENT READS. The child inherits this process's environment (the same one `./run.sh drill` gives the dev gateway); every value it adds is set here, and the store credentials reach it through that environment and never through an argv.
"""

from __future__ import annotations

import contextlib
import http.client
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from typing import TYPE_CHECKING

from rediacc_ci import log
from rediacc_ci.core import account
from rediacc_ci.core import account_lifecycle as lifecycle
from rediacc_ci.drills import backup_check_trigger, lib, wire

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

STEP_LABEL = "I7"
PROBE_SCRIPT = ("private", "elite", "scripts", "s3-conformance-probe.sh")
S3_REGION = "us-east-1"
SERVER_INFO = "/account/api/v1/.well-known/server-info"
USAGE_PATH = "/account/api/v1/backups/usage"
BOOT_TRIES = 90
BOOT_INTERVAL_S = 1.0
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
# Names of the entry's own boot line and the refusal an unconfigured plane gives.
CONFIGURED_PREFIX = "Backup chunk storage: "
NOT_CONFIGURED = "not configured"
NOT_CONFIGURED_CODE = "BACKUP_NOT_CONFIGURED"
# Routes the on-premise factory must not carry, each with the reason it is expected absent.
ABSENT_ROUTES = ("/account/api/v1/test/ensure-login", "/account/api/v1/admin/subscriptions")


def free_port() -> int:
    """A port nothing listens on right now (bound and released; the window before the server takes it is the same one every dev tool lives with)."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def onprem_overrides(
    *,
    port: int,
    db_path: str,
    endpoint: str,
    bucket: str,
    access_key: str,
    secret_key: str,
    keys: dict[str, str],
) -> dict[str, str]:
    """What this drill sets on top of the inherited environment for `src/entry/on-premise.ts`.

    `ON_PREMISE_MODE` selects the on-premise behavior; the five `ACCOUNT_*` key fields and the two secrets are the fields `envSchema` requires (throwaway values); the SMTP transport is the one the on-premise entry documents and is never contacted at boot; `BACKUP_MAINTENANCE_INTERVAL_MS=0` keeps the GC timer off. Everything a dev environment could pre-set that would redirect the store (`CONFIG_R2_*`, `UPSTREAM_*`) is blanked so the process under test reads only what this dict says.
    """
    return {
        "ON_PREMISE_MODE": "true",
        "PORT": str(port),
        "DATABASE_PATH": db_path,
        "ACCOUNT_ED25519_PRIVATE_KEY": keys["ed25519_priv"],
        "ACCOUNT_ED25519_PUBLIC_KEY": keys["ed25519_pub"],
        "ACCOUNT_X25519_PRIVATE_KEY": keys["x25519_priv"],
        "ACCOUNT_X25519_PUBLIC_KEY": keys["x25519_pub"],
        "ACCOUNT_SERVER_API_KEY": keys["api_key"],
        "ACCOUNT_JWT_SECRET": keys["jwt"],
        "EMAIL_TRANSPORT": "smtp",
        "SMTP_HOST": "127.0.0.1",
        "SMTP_FROM": "onprem-drill@rediacc.invalid",
        "ACCOUNT_BACKUP_S3_ENDPOINT": endpoint,
        "ACCOUNT_BACKUP_S3_BUCKET": bucket,
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": access_key,
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": secret_key,
        "BACKUP_MAINTENANCE_INTERVAL_MS": "0",
        "TEST_MODE": "",
        "UPSTREAM_API_KEY": "",
        "UPSTREAM_PUBLIC_KEY": "",
        "UPSTREAM_URL": "",
        "CONFIG_R2_ENDPOINT": "",
        "CONFIG_R2_BUCKET": "",
        "CONFIG_R2_ACCESS_KEY_ID": "",
        "CONFIG_R2_SECRET_ACCESS_KEY": "",
    }


def probe_env(endpoint: str, bucket: str, access_key: str, secret_key: str) -> dict[str, str]:
    """The environment the conformance probe reads (`S3_*`), so no credential is on its argv."""
    return {
        "S3_ENDPOINT": endpoint,
        "S3_BUCKET": bucket,
        "S3_ACCESS_KEY_ID": access_key,
        "S3_SECRET_ACCESS_KEY": secret_key,
        "S3_REGION": S3_REGION,
    }


def boot_line(log_text: str) -> str:
    """The entry's `Backup chunk storage:` line, or the empty string when it never printed one."""
    for line in log_text.splitlines():
        if line.startswith(CONFIGURED_PREFIX):
            return line
    return ""


def plane_configured(line: str, endpoint: str, bucket: str) -> bool:
    """True when the boot line names this run's store, which is what separates a configured plane from `not configured (ACCOUNT_BACKUP_S3_* unset)`."""
    return bool(line) and NOT_CONFIGURED not in line and "%s/%s" % (endpoint, bucket) in line


def route_verdict(status: int, body: str) -> str:
    """`mounted`, `missing` or `unconfigured` for an unauthenticated GET on a backup route. A mounted route refuses the missing credential (401); a missing one answers 404; an unconfigured plane answers `BACKUP_NOT_CONFIGURED`."""
    if NOT_CONFIGURED_CODE in body:
        return "unconfigured"
    if status == HTTP_UNAUTHORIZED:
        return "mounted"
    if status == HTTP_NOT_FOUND:
        return "missing"
    return "other-%d" % status


def http_status(port: int, method: str, path: str) -> tuple[int, str]:
    """(status, body) of one request to the local server; (0, error) when nothing answered."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path)
        response = conn.getresponse()
        return response.status, response.read().decode("utf-8", errors="replace")
    except (OSError, http.client.HTTPException) as exc:
        return 0, str(exc)
    finally:
        conn.close()


class OnPrem:
    """One run. `spawn` and `probe` are the seams: the real ones start processes, the tests' do not."""

    def __init__(
        self,
        drill: lib.Drill,
        *,
        spawn: Callable[..., subprocess.Popen] | None = None,
        runner: Callable[..., subprocess.CompletedProcess] | None = None,
    ) -> None:
        self.d = drill
        self.root = drill.root
        self.spawn = spawn or subprocess.Popen
        self.runner = runner or subprocess.run
        self.port = 0
        self.server: subprocess.Popen | None = None
        self.bucket = "rediacc-onprem-probe-%s" % uuid.uuid4().hex[:8]
        self.endpoint = "http://127.0.0.1:%d" % lifecycle.RUSTFS_PORT
        self.access_key = os.environ.get("CONFIG_R2_ACCESS_KEY_ID") or "configadmin"
        self.secret_key = os.environ.get("CONFIG_R2_SECRET_ACCESS_KEY") or "configadmin"
        self.server_log: pathlib.Path | None = None

    @property
    def work(self) -> pathlib.Path:
        if self.d.work is None:
            raise RuntimeError("Drill.init() must run first")
        return self.d.work

    # ------------------------------------------------------------------ preflight and setup

    def preflight(self) -> None:
        d = self.d
        d.step("%s preflight: the entry file, the probe script and the tools" % STEP_LABEL)
        entry = self.root / "private" / "account" / "src" / "entry" / "on-premise.ts"
        probe = self.root.joinpath(*PROBE_SCRIPT)
        problems = []
        if not entry.is_file():
            problems.append("%s is missing (private/account is not checked out)" % entry)
        if not probe.is_file():
            problems.append("%s is missing" % probe)
        problems.extend(
            "%s is not on PATH" % tool
            for tool in ("npx", "curl", "openssl")
            if not shutil.which(tool)
        )
        if problems:
            for line in problems:
                log.error(line)
            raise SystemExit(1)

    def setup_store(self) -> None:
        """RustFS on the account-dev port (reused when it already serves, started through the same compose service when it does not) and a bucket of this run's own."""
        d = self.d
        d.step("%s setup: RustFS and a bucket of its own" % STEP_LABEL)
        if not account.rustfs_alive(lifecycle.RUSTFS_PORT):
            lifecycle.start_rustfs()
        if not account.rustfs_alive(lifecycle.RUSTFS_PORT):
            log.error(
                "RustFS does not answer on :%d; start it with ./run.sh account dev (or docker)."
                % lifecycle.RUSTFS_PORT
            )
            raise SystemExit(1)
        url = "%s/%s" % (self.endpoint, self.bucket)
        headers = wire.sigv4_headers("PUT", url, b"", S3_REGION, self.access_key, self.secret_key)
        code, _ = wire.http_call("PUT", url, b"", headers, json_body=False)
        if code != HTTP_OK:
            log.error("creating bucket %s failed (HTTP %d)" % (self.bucket, code))
            raise SystemExit(1)
        d.note("bucket ready: %s" % url)

    # ------------------------------------------------------------------ the rows

    def probe_row(self) -> None:
        d = self.d
        d.step("%s: the S3 conformance probe, against the bucket and against nothing" % STEP_LABEL)
        script = str(self.root.joinpath(*PROBE_SCRIPT))
        good = probe_env(self.endpoint, self.bucket, self.access_key, self.secret_key)
        d.run(["bash", script], env={**os.environ, **good})
        d.assert_exit(0, "the conformance probe passes against RustFS")
        dead = probe_env(
            "http://127.0.0.1:%d" % free_port(), self.bucket, self.access_key, self.secret_key
        )
        d.run(["bash", script], env={**os.environ, **dead})
        d.assert_not_equal(
            "0",
            str(d.code),
            "planted control: the same probe against a closed port FAILS, so a pass above can be a fail",
        )

    def start_server(self) -> bool:
        d = self.d
        d.step("%s: boot src/entry/on-premise.ts against that bucket" % STEP_LABEL)
        self.port = free_port()
        keys = account.generate_crypto_keys(strict=True)
        overrides = onprem_overrides(
            port=self.port,
            db_path=str(self.work / "onprem-account.db"),
            endpoint=self.endpoint,
            bucket=self.bucket,
            access_key=self.access_key,
            secret_key=self.secret_key,
            keys={
                "ed25519_priv": keys.ed25519_priv,
                "ed25519_pub": keys.ed25519_pub,
                "x25519_priv": keys.x25519_priv,
                "x25519_pub": keys.x25519_pub,
                "api_key": keys.api_key,
                "jwt": keys.jwt,
            },
        )
        self.server_log = self.work / "onprem-server.log"
        with self.server_log.open("wb") as sink:
            self.server = self.spawn(
                ["npx", "tsx", "src/entry/on-premise.ts"],
                cwd=str(self.root / "private" / "account"),
                env={**os.environ, **overrides},
                stdin=subprocess.DEVNULL,
                stdout=sink,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        for _ in range(BOOT_TRIES):
            if self.server.poll() is not None:
                break
            if http_status(self.port, "GET", SERVER_INFO)[0] == HTTP_OK:
                d.last_cmd = "GET %s" % SERVER_INFO
                d.assert_equal("200", "200", "the on-premise entry boots and answers server-info")
                return True
            time.sleep(BOOT_INTERVAL_S)
        d.last_cmd = "wait for %s" % SERVER_INFO
        d.assert_equal("200", "0", "the on-premise entry boots and answers server-info")
        log.error(self.log_tail())
        return False

    def log_text(self) -> str:
        if self.server_log is None:
            return ""
        try:
            return self.server_log.read_text(errors="replace")
        except OSError:
            return ""

    def log_tail(self, count: int = 30) -> str:
        return "\n".join(self.log_text().splitlines()[-count:])

    def server_rows(self) -> None:
        d = self.d
        line = boot_line(self.log_text())
        d.last_cmd = "the entry's boot log"
        d.assert_equal(
            "True",
            str(plane_configured(line, self.endpoint, self.bucket)),
            "the boot line reports the configured chunk store (%s)" % (line or "no such line"),
        )
        status, body = http_status(self.port, "GET", USAGE_PATH)
        d.last_cmd = "GET %s (no credential)" % USAGE_PATH
        d.assert_equal(
            "mounted",
            route_verdict(status, body),
            "the backup routes are mounted: a missing credential is refused 401, not 404 or BACKUP_NOT_CONFIGURED",
        )
        for path in ABSENT_ROUTES:
            status, _ = http_status(self.port, "POST", path)
            d.last_cmd = "POST %s" % path
            d.assert_equal(
                str(HTTP_NOT_FOUND),
                str(status),
                "the on-premise factory leaves %s out" % path.rsplit("/account/api/v1", 1)[-1],
            )

    # ------------------------------------------------------------------ main

    def stop_server(self) -> None:
        server = self.server
        if server is None or server.poll() is not None:
            return
        with contextlib.suppress(OSError, ProcessLookupError):
            os.killpg(server.pid, 15)
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError, ProcessLookupError):
                os.killpg(server.pid, 9)

    def run_all(self) -> int:
        d = self.d
        d.selftest_probe()
        if d.selftest:
            d.note("selftest mode: stopping before any server or store work")
            return d.summary()
        self.preflight()
        self.setup_store()
        try:
            self.probe_row()
            if self.start_server():
                self.server_rows()
        finally:
            self.stop_server()
        return d.summary()


def main(argv: list[str]) -> int:
    selftest, keep_work, rest = lib.parse_common_args(argv)
    if rest:
        log.error("Unknown option: %s" % rest[0])
        print("Usage: ./run.sh drill backup-onprem [--selftest] [--keep-work]", file=sys.stderr)
        return 2
    drill = lib.Drill("backup-onprem", selftest=selftest, keep_work=keep_work)
    drill.init()
    rc = 1
    try:
        rc = OnPrem(drill).run_all()
    except SystemExit as exc:
        rc = int(exc.code) if isinstance(exc.code, int) else 1
    except OSError as exc:
        log.error(str(exc))
        rc = 1
    finally:
        drill.teardown()
    # The on-premise half of the backup receipt (box J4).
    backup_check_trigger.record_drill(drill, backup_check_trigger.ONPREM_HALF, rc)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
