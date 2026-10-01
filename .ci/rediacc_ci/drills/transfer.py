"""Port of `scripts/drills/transfer.sh` (402 lines): the config-storage ("transfer") battery, scripted.

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.transfer [--selftest] [--no-restart] [--keep-work]

WHAT IT PROVES. Config storage holds the only copy of an operator's universe, so the interesting cases are the ones where the server is NOT there: (1) SEED ON ENABLE, enrolling against an empty store pushes the local config as version 1 and says so; (2) OFFLINE READ, with the server unreachable reads still succeed from the encrypted local cache, the staleness warning goes to STDERR and stdout stays clean; (3) FAIL-CLOSED WRITE, an offline write refuses with the exact message and exit code and the cache is byte-identical afterwards; (4) SECOND DEVICE, a second box enrolls headlessly through the password slot, does not re-seed, and pulls what the first pushed, its account login going through the real two-factor challenge.

COST. Headless: no VMs. It needs `./run.sh account dev` including its Docker side (the store is backed by RustFS); without it the store cannot be seeded and the drill fails fast saying so. Offline is simulated with the in-process shim in `rediacc_ci.drills.lib` rather than by stopping the gateway, because a restart may move the gateway to another port and strand the configs.

TWO WORKAROUNDS FOR DEFECTS FOUND WHILE WRITING THE DRILL, kept and still reported: (a) `rdc config init <name> --server <url>` does not record that server's E2E public key, so the first tunnelled request encrypts with the production key and fails as a bare `Error: Decryption failed`; `rdc config current` syncs it, so it runs once right after init. (b) An API token binds to the client IP on FIRST use and a request through the E2E tunnel presents a different IP than a direct one, so nothing may touch the account token directly before the CLI does: tokens are minted over the session API only and the CLI is the token's first user.

PREFLIGHT KEYRING. Every phase enrolls a device and enrollment stores its slot secret in the OS keyring (`keyctl @u`); a runner without one fails four assertions deep, blaming the store. The preflight does the write AND the read back. Absent with `DRILL_EXPECT_NO_KEYRING=<why>` is a loud declared skip (exit 0, SKIPPED); absent without it is a red.

The Rule T differences from the bash twin are in `rediacc_ci.drills.lib` (the gateway does not inherit the sandbox `XDG_CONFIG_HOME`; secrets in a command's environment stay out of the failure report) plus two here: (1) the offline write is expected to exit 6, the CLI's NETWORK_ERROR code, where the bash expected 1 and so failed assertion 19 on every live run; (2) `init_config` no longer discards its output, so a failing `config init` or warm-up prints both streams and aborts with exit 2 instead of dying under `set -e` with nothing said.
"""

from __future__ import annotations

import http.cookiejar
import os
import shutil
import subprocess
import sys
import time

from rediacc_ci import log
from rediacc_ci.drills import lib

DRILL_PASSWORD = "DrillTransfer123!"  # noqa: S105 -- a throwaway dev-gateway login
STORE_PASSWORD = "DrillStore123!"  # noqa: S105 -- constant by necessity: a re-seed cannot re-wrap the CEK without it
CONFIG_NAME = "drill-transfer"
USAGE = "Usage: ./run.sh drill transfer [--selftest] [--no-restart] [--keep-work]"
# `RemoteUnreachableError` maps to NETWORK_ERROR, which `packages/cli/src/types/index.ts` defines as exit 6 (`EXIT_CODES.NETWORK_ERROR`). The bash asserted exit 1 and failed on every live run (2026-10-01: "expected exit 1, got 6", assertion 19); a test pins this constant to the CLI's own table.
OFFLINE_WRITE_EXIT = 6
KEYRING_PROBE_KEY = "rediacc-drill-keyring-probe"


class Transfer:
    def __init__(self, drill: lib.Drill, restart_gateway: bool) -> None:
        self.d = drill
        self.restart = restart_gateway
        self.rdc = str(drill.root / "rdc.sh")
        # A fresh dev user, and so a fresh store, on every run: a second run's `config remote enable --password` against the store the first left behind dies with a raw WebCrypto OperationError.
        self.email = "drill-transfer-%d@rediacc.io" % int(time.time())
        self.device1 = ""
        self.device2 = ""
        self.server_url = ""
        self.minted_token = ""

    def cli(self, home: str, *args: str, **env: str) -> None:
        self.d.run_with([self.rdc, *args], XDG_CONFIG_HOME=home, **env)

    def preflight_keyring(self) -> bool:
        """True when the keyring round-trips; False after a declared skip (the caller exits 0). A missing keyring without a declaration exits 1."""
        d = self.d
        d.step("Preflight: an OS keyring the CLI can actually write to")
        # ROUND TRIP, not just a write: a GitHub runner lets `keyctl add` succeed and then denies the read, so mirror the two calls secure-storage.ts makes on the read path.
        if shutil.which("keyctl"):
            added = subprocess.run(
                ["keyctl", "add", "user", KEYRING_PROBE_KEY, "probe-ok", "@u"],
                capture_output=True,
                check=False,
            )
            if added.returncode == 0:
                found = subprocess.run(
                    ["keyctl", "search", "@u", "user", KEYRING_PROBE_KEY],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
                value = ""
                if found:
                    value = subprocess.run(
                        ["keyctl", "pipe", found], capture_output=True, text=True, check=False
                    ).stdout
                subprocess.run(
                    ["keyctl", "purge", "user", KEYRING_PROBE_KEY], capture_output=True, check=False
                )
                if value == "probe-ok":
                    d.note("keyring usable (keyctl @u write+read round trip)")
                    return True
                d.note(
                    "keyctl add succeeded but the read back did not, so the keyring is treated as unusable"
                )
        declared = os.environ.get("DRILL_EXPECT_NO_KEYRING")
        if declared:
            print()
            log.warn("config-storage enrollment: SKIPPED BY DECLARATION")
            log.warn("  reason (DRILL_EXPECT_NO_KEYRING): %s" % declared)
            log.warn("  every phase of this drill enrolls a device, and enrollment needs the")
            log.warn("  OS keyring (keyctl @u) that this environment does not provide.")
            print()
            return False
        log.error("No usable OS keyring: the write+read round trip against @u did not complete.")
        log.error("Enrollment stores its slot secret there (secure-storage.ts), so every")
        log.error("phase of this drill would fail four assertions deep, blaming the store.")
        log.error("On a machine that genuinely has no keyring, declare it:")
        log.error("  DRILL_EXPECT_NO_KEYRING='<why>' ./run.sh drill transfer")
        raise SystemExit(1)

    def setup_sandbox(self) -> None:
        d = self.d
        d.step("Setup: two isolated config directories (device 1 and device 2)")
        assert d.work is not None  # noqa: S101
        self.device1 = str(d.work / "device1")
        self.device2 = str(d.work / "device2")
        for home in (self.device1, self.device2):
            os.makedirs(os.path.join(home, "rediacc"), exist_ok=True)
        # Without pinning the format a drill measures the json surface while describing the human one, because stdout is not a TTY.
        d.extra_env["REDIACC_DEFAULT_OUTPUT"] = "table"
        d.extra_env["XDG_CONFIG_HOME"] = self.device1
        d.note("device 1: %s" % self.device1)
        d.note("device 2: %s" % self.device2)
        # Two keys: the online write in phase 2 sets the first, the refused offline write in phase 3 tries the second; re-setting the SAME key could be a no-op that never reaches the save path.
        for suffix, name in (("", "a"), ("_b", "b")):
            proc = subprocess.run(
                [
                    "ssh-keygen",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-q",
                    "-C",
                    "drill-transfer-%s" % name,
                    "-f",
                    str(d.work / ("id_ed25519%s" % suffix)),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                log.error("ssh-keygen failed: %s" % proc.stderr.strip())
                raise SystemExit(2)

    def setup_gateway(self) -> None:
        d = self.d
        if self.restart:
            d.restart_gateway()
        else:
            d.step("Reusing the running dev gateway (--no-restart)")
            if not d.gateway_alive():
                log.error("No healthy dev gateway. Start one: ./run.sh account dev")
                raise SystemExit(1)
            d.gateway_port_cached = d.gateway_port()
        d.start_shim()
        self.server_url = d.shim_url()

    def setup_store(self) -> None:
        d = self.d
        d.step("Setup: dev user, subscription and a password-unlockable config store")
        d.account_ensure_login(self.email, DRILL_PASSWORD)
        d.account_ensure_subscription(self.email, "PROFESSIONAL")
        seed = d.api_post(
            "/test/seed-config-store", {"email": self.email, "password": STORE_PASSWORD}
        )
        store_id = lib.json_get(seed, "storeId")
        if not store_id:
            log.error("Could not seed a config store: %s" % seed)
            log.error(
                "Config storage needs the RustFS container from ./run.sh account dev (Docker)."
            )
            raise SystemExit(1)
        d.note("store %s seeded, password slot provisioned" % store_id)

    def mint_token(self, name: str) -> None:
        """A fresh account token minted over the SESSION api only; nothing else may use it before the CLI does (workaround b)."""
        d = self.d
        assert d.work is not None  # noqa: S101
        jar = http.cookiejar.MozillaCookieJar(str(d.work / ("cookies-%s.txt" % name)))
        if not d.account_session(self.email, DRILL_PASSWORD, jar):
            raise SystemExit(1)
        sub = d.account_subscription_id(jar)
        self.minted_token = d.account_mint_token(
            jar, sub, name, ["license:read", "subscription:read", "config:enroll"]
        )

    def init_config(self, home: str, name: str) -> None:
        """Create a config and warm it up (workaround a); a failure prints both streams and aborts with exit 2."""
        self.cli(home, "config", "init", name, "--server", self.server_url)
        self._must_succeed("config init %s" % name)
        self.cli(home, "config", "current", "-o", "json", REDIACC_CONFIG=name)
        self._must_succeed("config current warm-up for %s" % name)

    def _must_succeed(self, what: str) -> None:
        if self.d.code != 0:
            log.error("%s failed (exit %d): %s" % (what, self.d.code, self.d.last_cmd))
            sys.stderr.write(self.d.stdout_text())
            sys.stderr.write(self.d.stderr_text())
            raise SystemExit(2)

    def md5(self, path: str) -> str:
        return lib.md5(path)

    def phase_seed_on_enable(self) -> None:
        d = self.d
        d.step("Phase 1: enrolling against an empty store seeds it at version 1")
        self.init_config(self.device1, CONFIG_NAME)
        self.mint_token("drill-transfer-d1")
        self.cli(
            self.device1,
            "config",
            "remote",
            "enable",
            "--password",
            "--api-url",
            self.server_url,
            REDIACC_CONFIG=CONFIG_NAME,
            REDIACC_TOKEN=self.minted_token,
            REDIACC_CONFIG_PASSWORD=STORE_PASSWORD,
            REDIACC_DEFAULT_OUTPUT="table",
        )
        d.assert_exit(0, "headless password enrollment succeeds with no browser")
        d.assert_stderr_contains(
            "Store was empty; pushed the local config as version 1.",
            "the empty store was seeded, and the CLI said so",
        )
        d.assert_stderr_contains("Remote config enabled.", "enrollment reported success")
        d.assert_stdout_empty("enable writes nothing to stdout")
        self.cli(
            self.device1, "config", "remote", "status", "-o", "json", REDIACC_CONFIG=CONFIG_NAME
        )
        d.assert_exit(0, "config remote status succeeds")
        d.assert_stdout_json("data.status", "connected", "the config reports status=connected")
        d.assert_stdout_json("data.cachedVersion", "1", "the cached version is 1 (the seed)")
        d.assert_stdout_json(
            "data.apiUrl", self.server_url, "and it is bound to the drill's server"
        )

    def phase_offline_read(self) -> None:
        d = self.d
        assert d.work is not None  # noqa: S101
        d.step("Phase 2: an online write pushes, then reads survive the server going away")
        # An online write first, so the cache holds something the server produced (version 2) rather than only the seed. `config ssh set` changes the config and touches nothing outside it; `machine add` would also write an SSH alias into the user's real home.
        self.cli(
            self.device1,
            "config",
            "ssh",
            "set",
            "--key",
            str(d.work / "id_ed25519"),
            REDIACC_CONFIG=CONFIG_NAME,
            REDIACC_DEFAULT_OUTPUT="table",
        )
        d.assert_exit(0, "a write succeeds while the server is reachable")
        self.cli(
            self.device1, "config", "remote", "status", "-o", "json", REDIACC_CONFIG=CONFIG_NAME
        )
        d.assert_stdout_json(
            "data.cachedVersion",
            "2",
            "the write went to the server: the cached version advanced to 2",
        )
        d.stop_shim()
        d.note("offline shim stopped; the config's server is now refusing connections")
        self.cli(
            self.device1,
            "machine",
            "list",
            REDIACC_CONFIG=CONFIG_NAME,
            REDIACC_DEFAULT_OUTPUT="table",
        )
        d.assert_exit(0, "a read still succeeds while the server is unreachable")
        d.assert_stderr_contains(
            "is unreachable; serving config", "the staleness warning names the unreachable server"
        )
        d.assert_stderr_contains(
            "from the offline cache", "and says the answer came from the cache"
        )
        d.assert_stderr_contains(
            "Changes cannot be saved until the server is reachable.",
            "and warns that writes will not work",
        )
        d.assert_stdout_not_contains(
            "offline cache", "the warning stays on stderr and does not corrupt stdout"
        )
        # The json path, on a command that emits an envelope: the cached state is served intact with the server gone.
        self.cli(
            self.device1, "config", "remote", "status", "-o", "json", REDIACC_CONFIG=CONFIG_NAME
        )
        d.assert_exit(0, "the json read also succeeds offline")
        d.assert_stdout_json("success", "true", "the envelope reports success")
        d.assert_stdout_json(
            "data.cachedVersion", "2", "and still reports version 2, served from the cache"
        )

    def phase_fail_closed_write(self) -> None:
        d = self.d
        assert d.work is not None  # noqa: S101
        d.step("Phase 3: while offline, a write refuses instead of saving locally")
        config_file = os.path.join(self.device1, "rediacc", "%s.json" % CONFIG_NAME)
        before = self.md5(config_file)
        self.cli(
            self.device1,
            "config",
            "ssh",
            "set",
            "--key",
            str(d.work / "id_ed25519_b"),
            REDIACC_CONFIG=CONFIG_NAME,
            REDIACC_DEFAULT_OUTPUT="table",
        )
        d.assert_exit(
            OFFLINE_WRITE_EXIT,
            "the write fails with the network exit code (%d)" % OFFLINE_WRITE_EXIT,
        )
        d.assert_stderr_contains(
            "Cannot save: config", "the refusal names the config and the server"
        )
        d.assert_stderr_contains(
            "The change was NOT saved.", "and states plainly that nothing was written"
        )
        d.assert_equal(
            before,
            self.md5(config_file),
            "the cached config file is byte-identical (no torn or partial write)",
        )

    def phase_second_device(self) -> None:
        d = self.d
        d.step("Phase 4: a second device enrolls headlessly and pulls, without re-seeding")
        d.start_shim()
        d.note("server reachable again")
        # Prove the read path recovered before drawing conclusions from device 2.
        self.cli(
            self.device1,
            "machine",
            "list",
            REDIACC_CONFIG=CONFIG_NAME,
            REDIACC_DEFAULT_OUTPUT="table",
        )
        d.assert_exit(0, "device 1 reads again once the server is back")
        d.assert_stderr_not_contains(
            "from the offline cache", "and no longer warns about the cache"
        )
        self.init_config(self.device2, CONFIG_NAME)
        self.mint_token("drill-transfer-d2")
        d.last_cmd = "POST /auth/login + /auth/2fa/verify for %s" % self.email
        d.assert_equal(
            "1",
            "1" if d.twofa_used else "0",
            "the second device's account login went through the two-factor challenge",
        )
        self.cli(
            self.device2,
            "config",
            "remote",
            "enable",
            "--password",
            "--api-url",
            self.server_url,
            REDIACC_CONFIG=CONFIG_NAME,
            REDIACC_TOKEN=self.minted_token,
            REDIACC_CONFIG_PASSWORD=STORE_PASSWORD,
            REDIACC_DEFAULT_OUTPUT="table",
        )
        d.assert_exit(0, "the second device enrolls with the same password slot")
        d.assert_stderr_not_contains(
            "Store was empty", "and does NOT re-seed: the store already holds this config"
        )
        d.assert_stderr_contains("Remote config enabled.", "enrollment reported success")
        self.cli(
            self.device2, "config", "remote", "status", "-o", "json", REDIACC_CONFIG=CONFIG_NAME
        )
        d.assert_exit(0, "device 2 reports its remote status")
        d.assert_stdout_json("data.status", "connected", "device 2 is connected")
        d.assert_stdout_json(
            "data.cachedVersion",
            "2",
            "device 2 pulled version 2, the version device 1's write produced",
        )
        d2_store = lib.json_get(d.stdout_text(), "data.storeId")
        d2_config = lib.json_get(d.stdout_text(), "data.configId")
        d1 = subprocess.run(
            [self.rdc, "config", "remote", "status", "-o", "json"],
            capture_output=True,
            text=True,
            env={**d.cli_env(), "XDG_CONFIG_HOME": self.device1, "REDIACC_CONFIG": CONFIG_NAME},
            check=False,
        ).stdout
        d.assert_equal(
            lib.json_get(d1, "data.storeId"), d2_store, "both devices point at the same store"
        )
        d.assert_equal(
            lib.json_get(d1, "data.configId"),
            d2_config,
            "and at the same config inside it (device 2 joined, it did not fork a new one)",
        )


def main(argv: list[str]) -> int:
    selftest, keep_work, rest = lib.parse_common_args(argv)
    restart = True
    for arg in rest:
        if arg == "--no-restart":
            restart = False
        else:
            log.error("Unknown option: %s" % arg)
            print(USAGE, file=sys.stderr)
            return 2
    drill = lib.Drill("transfer", selftest=selftest, keep_work=keep_work)
    drill.init()
    rc = 1
    try:
        transfer = Transfer(drill, restart)
        transfer.setup_sandbox()
        drill.selftest_probe()
        if selftest:
            drill.note("selftest mode: skipping the live phases")
            return drill.summary()
        # After the selftest gate: --selftest proves the harness without touching a gateway or a keyring, so it stays runnable where enrollment cannot be.
        if not transfer.preflight_keyring():
            drill.summary()
            return 0
        transfer.setup_gateway()
        transfer.setup_store()
        transfer.phase_seed_on_enable()
        transfer.phase_offline_read()
        transfer.phase_fail_closed_write()
        transfer.phase_second_device()
        rc = drill.summary()
    except SystemExit as exc:
        rc = int(exc.code) if isinstance(exc.code, int) else 1
    except (lib.GatewayError, OSError) as exc:
        log.error(str(exc))
        rc = 1
    finally:
        drill.teardown()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
