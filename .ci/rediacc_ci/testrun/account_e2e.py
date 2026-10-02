"""Port of `.ci/scripts/test/run-account-e2e.sh`: start a backend API (SQLite), optionally `stripe listen`, install Playwright browsers, run the account portal suite, prove the `@webauthn` tests ran, and clean up.

Phases and every environment variable handed to the backend are the twin's. The paths come from `paths.repo_root()`, so a fixture tree selected with `$REDIACC_CI_ROOT` exercises the whole script without touching `private/account`.

Deliberate differences from the twin (Rule T), each with a test that fails on the bash behaviour:

  1. UNKNOWN AND MALFORMED ARGUMENTS. The twin's `parse_args` ignored anything it did not know (`--proejcts firefox` ran chromium) and read `--skip-setup <word>` as the value `<word>`, which is not `true`, so setup ran. Unknown flags are refused (exit 2) and `--skip-setup` is a plain switch.
  2. REQUIRED SECRETS ARE CHECKED FIRST. `${ACCOUNT_ED25519_PRIVATE_KEY:?}` and its siblings were expanded only when the backend's environment array was built, AFTER `stripe listen` had been started and the sandbox synced. A missing secret is refused before anything starts. A half-supplied X25519 pair is refused too; the twin died on an unbound variable.
  3. THE BACKEND'S WHOLE PROCESS TREE IS STOPPED. `npx` forks, so `kill $BACKEND_PID` ended the wrapper and left the tsx server holding the port. The backend (and `stripe listen`) lead their own sessions and the group is signalled.
  4. A MISSING `private/account` IS A FAILURE UNDER CI. The twin logged a warning and exited 0, so a job that forgot `submodules: true` passed having run no test. Outside CI it still skips with exit 0.
  5. `stripe listen` PRINTING SEVERAL `whsec_` TOKENS NO LONGER CORRUPTS THE SECRET: the first is taken (the twin kept a multi-line string).
"""

import contextlib
import dataclasses
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from rediacc_ci import log, paths, proc
from rediacc_ci.core import common
from rediacc_ci.testrun import shard

MIN_WEBAUTHN_TESTS = 20
LISTEN_TIMEOUT = 90
DEFAULT_WEBHOOK_FIXTURE = "whsec_e2e_test_webhook_secret_for_simulation_only"
USAGE = 'usage: run-account-e2e.sh [--projects "chromium firefox"] [--grep TAG] [--skip-setup] [--workers N] [--shard-manifest PATH --shard I/N]'
REQUIRED_SECRETS = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_JWT_SECRET",
    "ROOT_EMAIL",
)
X25519_PROGRAM = """
const crypto = require('crypto');
const { privateKey, publicKey } = crypto.generateKeyPairSync('x25519');
console.log(JSON.stringify({
    private: privateKey.export({type:'pkcs8',format:'der'}).toString('base64'),
    public: publicKey.export({type:'spki',format:'der'}).toString('base64')
}));
"""


class UsageError(Exception):
    """Bad command line. Exit 2."""


class RefusedError(Exception):
    """The run cannot proceed; the message is the diagnostic. Exit 1."""


@dataclasses.dataclass
class Options:
    projects: str = "chromium"
    grep: str = ""
    skip_setup: bool = False
    workers: str = "1"
    shard_manifest: str = ""
    shard: str = ""


def parse(argv: list[str]) -> Options:
    opts = Options()
    value_flags = {
        "--projects": "projects",
        "--grep": "grep",
        "--workers": "workers",
        "--shard-manifest": "shard_manifest",
        "--shard": "shard",
    }
    i = 0
    while i < len(argv):
        arg = argv[i]
        flag, eq, inline = arg.partition("=")
        if arg == "--skip-setup":
            opts.skip_setup = True
            i += 1
        elif flag in value_flags:
            if eq:
                value, step = inline, 1
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                value, step = argv[i + 1], 2
            else:
                raise UsageError(f"{flag} needs a value")
            setattr(opts, value_flags[flag], value)
            i += step
        else:
            raise UsageError(f"unknown argument: {arg}")
    if bool(opts.shard_manifest) != bool(opts.shard):
        raise RefusedError("--shard-manifest and --shard must both be given, or neither")
    return opts


def grep_has(path: pathlib.Path, needle: str) -> bool:
    try:
        return needle in path.read_text(errors="replace")
    except OSError:
        return False


def leg_flags(files: list[str], tests_dir: pathlib.Path) -> tuple[bool, bool]:
    """`(has stripe files, has webauthn files)`: everything when unsharded, else derived from the leg's own files."""
    if not files:
        return True, True
    stripe = webauthn = False
    for name in files:
        if name.startswith("10-stripe/") or grep_has(tests_dir / name, "@stripe-e2e"):
            stripe = True
        if grep_has(tests_dir / name, "@webauthn"):
            webauthn = True
    return stripe, webauthn


def webauthn_report(report: dict) -> tuple[dict[str, int], list[str]]:
    """Count `@webauthn` chromium tests by status, the twin's embedded node program as Python."""
    counts = {"expected": 0, "skipped": 0, "other": 0}
    bad: list[str] = []

    def walk(suite: dict, trail: list[str]) -> None:
        here = [*trail, suite["title"]] if suite.get("title") else trail
        for spec in suite.get("specs") or []:
            title = " > ".join([*here, spec.get("title", "")])
            tagged = "@webauthn" in title or any(
                str(t).lstrip("@") == "webauthn" for t in spec.get("tags") or []
            )
            if not tagged:
                continue
            for test in spec.get("tests") or []:
                if test.get("projectName") != "chromium":
                    continue
                status = test.get("status")
                if status == "expected":
                    counts["expected"] += 1
                else:
                    counts["skipped" if status == "skipped" else "other"] += 1
                    bad.append(f"{status}: {title}")
        for child in suite.get("suites") or []:
            walk(child, here)

    for suite in report.get("suites") or []:
        walk(suite, [])
    return counts, bad


def check_webauthn(results_json: pathlib.Path, floor: int) -> bool:
    if not results_json.exists():
        print(f"no Playwright JSON report at {results_json}", file=sys.stderr)
        return False
    counts, bad = webauthn_report(json.loads(results_json.read_text(encoding="utf-8")))
    print(
        f"@webauthn chromium tests: {counts['expected']} expected, {counts['skipped']} skipped, {counts['other']} other"
    )
    for line in bad:
        print(f"  {line}", file=sys.stderr)
    if counts["skipped"] > 0 or counts["other"] > 0 or counts["expected"] < floor:
        print(f"need >= {floor} expected and none skipped or failed", file=sys.stderr)
        return False
    return True


class Run:
    """One invocation: the processes it owns and the cleanup that stops them."""

    def __init__(self, opts: Options) -> None:
        self.opts = opts
        self.backend: subprocess.Popen | None = None
        self.stripe: subprocess.Popen | None = None
        self.tmp: str | None = None
        root = paths.repo_root()
        self.root = root
        self.account_dir = root / "private" / "account"
        self.e2e_dir = self.account_dir / "e2e"
        self.api_port = os.environ.get("ACCOUNT_API_PORT") or "3001"
        self.e2e_port = os.environ.get("E2E_PORT") or "5173"

    @staticmethod
    def _stop(process: subprocess.Popen) -> None:
        with contextlib.suppress(OSError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGKILL)

    def cleanup(self) -> None:
        log.step("Cleaning up...")
        if self.stripe is not None and self.stripe.poll() is None:
            log.info(f"Stopping stripe listen (PID {self.stripe.pid})")
            self._stop(self.stripe)
        if self.backend is not None and self.backend.poll() is None:
            log.info(f"Stopping backend API (PID {self.backend.pid})")
            self._stop(self.backend)
        db = self.account_dir / "e2e-account.db"
        if not self.opts.skip_setup and db.is_file():
            log.info("Removing E2E database...")
            for suffix in ("", "-wal", "-shm"):
                pathlib.Path(str(db) + suffix).unlink(missing_ok=True)
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)
        log.info("Cleanup complete")

    def install_dependencies(self) -> None:
        log.step("Installing account dependencies...")
        for directory in (self.account_dir, self.account_dir / "web", self.e2e_dir):
            if (
                not (directory / "node_modules").is_dir()
                and subprocess.run(["npm", "ci"], cwd=directory, check=False).returncode != 0
            ):
                raise RefusedError(f"npm ci failed in {directory}")

    def start_stripe_listen(self, secret_key: str) -> str:
        log.step("Syncing Stripe products/prices to sandbox...")
        subprocess.run(
            ["npx", "tsx", "scripts/stripe-sync.ts"],
            cwd=self.account_dir,
            env={**os.environ, "STRIPE_SECRET_KEY": secret_key},
            stderr=subprocess.STDOUT,
            check=False,
        )
        log.step("Starting stripe listen for real Stripe webhook forwarding...")
        # A pid-stamped directory removed by cleanup: the log carries the webhook signing secret.
        namespace = "0"
        with contextlib.suppress(OSError):
            namespace = str(os.stat("/proc/self/ns/pid").st_ino)
        self.tmp = tempfile.mkdtemp(
            prefix=f"rediacc-sh-{os.getpid()}-n{namespace}-account-e2e-",
            dir=os.environ.get("TMPDIR") or "/tmp",
        )
        listen_log = pathlib.Path(self.tmp) / "stripe-listen.log"
        with open(listen_log, "wb") as sink:
            self.stripe = subprocess.Popen(
                # The key goes in STRIPE_API_KEY, which the Stripe CLI reads, not `--api-key`: an argument is visible to every user through `ps` for as long as `stripe listen` runs.
                [
                    "stripe",
                    "listen",
                    "--forward-to",
                    f"http://localhost:{self.api_port}/account/api/v1/webhooks/stripe",
                    "--all-snapshot",
                ],
                stdout=sink,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ, "STRIPE_API_KEY": secret_key},
            )
        secret = ""
        for _ in range(LISTEN_TIMEOUT):
            # Whether it exited is read BEFORE the log, so output written just before an exit is never missed.
            exited = self.stripe.poll() is not None
            match = re.search(r"whsec_\S+", listen_log.read_text(errors="replace"))
            if match:
                secret = match.group(0)
                break
            if exited:
                break
            time.sleep(1)
        if not secret:
            log.error(
                f"stripe listen produced no webhook secret within {LISTEN_TIMEOUT}s; the real-Stripe e2e tests need its forwarding. Its output:"
            )
            sys.stderr.write(listen_log.read_text(errors="replace"))
            self._stop(self.stripe)
            self.stripe = None
            raise RefusedError("")
        log.info("stripe listen ready (webhook secret captured)")
        return secret

    def x25519_pair(self) -> tuple[str, str]:
        private = os.environ.get("ACCOUNT_X25519_PRIVATE_KEY") or ""
        public = os.environ.get("ACCOUNT_X25519_PUBLIC_KEY") or ""
        if private and public:
            return private, public
        if private or public:
            raise RefusedError(
                "ACCOUNT_X25519_PRIVATE_KEY and ACCOUNT_X25519_PUBLIC_KEY must be set together, or neither"
            )
        done = subprocess.run(
            ["node", "-e", X25519_PROGRAM],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if done.returncode != 0:
            raise RefusedError(f"node could not generate the X25519 keys: {done.stderr.strip()}")
        pair = json.loads(done.stdout)
        return pair["private"], pair["public"]

    def start_backend(self, listen_secret: str) -> None:
        x_private, x_public = self.x25519_pair()
        log.step(f"Starting backend API on port {self.api_port}...")
        env = {
            **os.environ,
            "ACCOUNT_ED25519_PRIVATE_KEY": os.environ.get("ACCOUNT_ED25519_PRIVATE_KEY", ""),
            "ACCOUNT_ED25519_PUBLIC_KEY": os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", ""),
            "ACCOUNT_X25519_PRIVATE_KEY": x_private,
            "ACCOUNT_X25519_PUBLIC_KEY": x_public,
            "ACCOUNT_SERVER_API_KEY": os.environ.get("ACCOUNT_SERVER_API_KEY", ""),
            "ACCOUNT_JWT_SECRET": os.environ.get("ACCOUNT_JWT_SECRET", ""),
            "ROOT_EMAIL": os.environ.get("ROOT_EMAIL", ""),
            "DATABASE_PATH": "e2e-account.db",
            "PUBLIC_SITE_URL": f"http://localhost:{self.e2e_port}",
            # WebAuthn/passkey ceremonies: the origin must equal the BROWSER origin (the Vite e2e port) or the ceremony's origin check fails.
            "WEBAUTHN_RP_ID": "localhost",
            "WEBAUTHN_RP_NAME": "Rediacc",
            "WEBAUTHN_ORIGIN": f"http://localhost:{self.e2e_port}",
            "PORT": self.api_port,
            # TEST_MODE is the only opener for the /test/* seed and email-capture routes; deployed Workers never set it.
            "TEST_MODE": "true",
        }
        if listen_secret:
            env["STRIPE_WEBHOOK_SECRET"] = listen_secret
        # The server verifies against the same fixture the signer uses; the NAME is a runtime slot, the VALUE a fixture.
        env["STRIPE_SANDBOX_WEBHOOK_SECRET"] = (
            os.environ.get("STRIPE_E2E_WEBHOOK_SECRET") or DEFAULT_WEBHOOK_FIXTURE
        )
        sandbox_key = os.environ.get("STRIPE_SANDBOX_SECRET_KEY")
        if sandbox_key:
            env["STRIPE_SANDBOX_SECRET_KEY"] = sandbox_key
        self.backend = subprocess.Popen(
            ["npx", "tsx", "src/entry/node.ts"],
            cwd=self.account_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(2)
        if self.backend.poll() is not None:
            raise RefusedError(f"Backend API process exited immediately (PID {self.backend.pid})")
        log.step("Waiting for the backend API...")
        outcome = proc.retry_with_backoff(
            self.healthy,
            attempts=6,
            delay=2,
            on_retry=lambda attempt, attempts, pause, _r: log.warn(
                f"Attempt {attempt}/{attempts} failed, retrying in {int(pause)}s..."
            ),
        )
        if not outcome.ok:
            log.error("Command failed after 6 attempts")
            raise RefusedError(f"Backend API failed to start on port {self.api_port}")
        log.info("Backend API is healthy")

    def healthy(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"http://localhost:{self.api_port}/health", timeout=5
            ) as response:
                return 200 <= response.status < 300
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def install_browsers(self, projects: list[str]) -> None:
        log.step(f"Installing Playwright browsers: {self.opts.projects}")
        for browser in projects:
            if (
                subprocess.run(
                    ["npx", "playwright", "install", browser], cwd=self.e2e_dir, check=False
                ).returncode
                != 0
            ):
                raise RefusedError(f"npx playwright install {browser} failed")
            if common.is_ci():
                subprocess.run(
                    ["npx", "playwright", "install-deps", browser],
                    cwd=self.e2e_dir,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )

    def run_tests(self, projects: list[str], files: list[str]) -> bool:
        log.step("Running Account Portal E2E tests...")
        cmd = [
            "npx",
            "playwright",
            "test",
            *[f"--project={p}" for p in projects],
            f"--workers={self.opts.workers}",
            "--timeout=60000",
        ]
        if self.opts.grep:
            cmd += ["--grep", self.opts.grep]
        cmd += files
        # The signer uses the FIXTURE, not a stored credential: the tests sign a simulated webhook and the server verifies it, so a stored secret that had expired would pass exactly as well.
        env = {
            **os.environ,
            "VITE_API_URL": f"http://localhost:{self.api_port}",
            "E2E_WEBHOOK_SECRET": os.environ.get("STRIPE_E2E_WEBHOOK_SECRET")
            or DEFAULT_WEBHOOK_FIXTURE,
        }
        return subprocess.run(cmd, cwd=self.e2e_dir, env=env, check=False).returncode == 0


def main(argv: list[str]) -> int:
    try:
        opts = parse(argv)
    except UsageError as exc:
        log.error(str(exc))
        print(USAGE, file=sys.stderr)
        return 2
    except RefusedError as exc:
        log.error(str(exc))
        return 1

    run = Run(opts)
    files: list[str] = []
    if opts.shard_manifest:
        try:
            for unit in shard.leg_ids(opts.shard_manifest, opts.shard):
                name = unit.removeprefix("account-e2e:")
                if name == unit:
                    log.error(f"shard manifest id '{unit}' is not an account-e2e unit")
                    return 1
                files.append(name)
        except shard.ShardError as exc:
            print(exc, file=sys.stderr)
            return 1
    has_stripe, has_webauthn = leg_flags(files, run.e2e_dir / "tests")

    if not (run.account_dir / "package.json").is_file():
        if common.is_ci():
            log.error(
                "Account submodule not available; the job must check out with submodules: true"
            )
            return 1
        log.warn("Account submodule not available, skipping E2E tests")
        return 0
    if not run.e2e_dir.is_dir():
        log.warn("Account E2E directory not found, skipping")
        return 0

    projects = opts.projects.split()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        os.chdir(run.root)
        if not opts.skip_setup:
            missing = [name for name in REQUIRED_SECRETS if not os.environ.get(name)]
            if missing:
                raise RefusedError(f"{', '.join(missing)} must be set")
        run.install_dependencies()
        if not opts.skip_setup:
            sandbox_key = os.environ.get("STRIPE_SANDBOX_SECRET_KEY")
            listen_secret = ""
            if sandbox_key and shutil.which("stripe") and has_stripe:
                listen_secret = run.start_stripe_listen(sandbox_key)
            run.start_backend(listen_secret)
        run.install_browsers(projects)
        if not run.run_tests(projects, files):
            log.error("Account Portal E2E tests failed")
            return 1
        log.info("Account Portal E2E tests passed")
        # Phase 5: prove the WebAuthn virtual-authenticator tests RAN. They skip on any browser but Chromium, so a green run is no evidence on its own.
        if "chromium" in projects and (not opts.grep or "webauthn" in opts.grep) and has_webauthn:
            results = run.e2e_dir / "reports" / "e2e" / "results.json"
            log.step(f"Checking @webauthn coverage in {results} (floor: {MIN_WEBAUTHN_TESTS})")
            if not check_webauthn(results, MIN_WEBAUTHN_TESTS):
                log.error("WebAuthn virtual-authenticator coverage check failed")
                return 1
            log.info("WebAuthn virtual-authenticator tests ran")
        return 0
    except RefusedError as exc:
        if str(exc):
            log.error(str(exc))
        return 1
    finally:
        run.cleanup()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
