"""Port of `scripts/drills/universe.sh` (307 lines): the config-as-a-universe battery, scripted.

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.universe [--selftest] [--no-restart] [--keep-work]

WHAT IT PROVES. A config is a whole universe: its own account server, keys, machines, and its own API token beside it as `api-token-<name>.json`. The four properties asserted rather than assumed: (1) SOURCE LABELS, `rdc config current` reports where each resolved value came from (env > config > built-in default); (2) SELECTION PRECEDENCE, `--config` beats `REDIACC_CONFIG` beats the built-in name; (3) ISOLATION, work on one config leaves another's file byte-identical (md5 before and after); (4) PER-CONFIG TOKENS, a login creates that config's token file and no other's, and a logout removes it.

COST. Headless: no VMs, no Docker, no privileged operations. It drives a real `./run.sh account dev` gateway because the token-file assertions need a real login. Everything runs under a throwaway `XDG_CONFIG_HOME`, and `REDIACC_DEFAULT_OUTPUT=table` is pinned so the drill measures the operator's surface and asks for JSON explicitly where it parses it. `--selftest` plants one assertion that cannot pass and skips the live phases; the run must exit non-zero.

The Rule T differences from the bash twin are listed in `rediacc_ci.drills.lib` (the gateway no longer inherits the sandbox `XDG_CONFIG_HOME`, which made the twin die in gateway startup).
"""

from __future__ import annotations

import http.cookiejar
import pathlib
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.drills import lib

EMAIL = "drill-universe@rediacc.io"
PASSWORD = "DrillUniverse123!"  # noqa: S105 -- a throwaway dev-gateway login, chosen by the drill
USAGE = "Usage: ./run.sh drill universe [--selftest] [--no-restart] [--keep-work]"


class Universe:
    def __init__(self, drill: lib.Drill, restart_gateway: bool) -> None:
        self.d = drill
        self.restart = restart_gateway
        self.rdc = str(drill.root / "rdc.sh")
        self.config_dir = pathlib.Path()
        self.server_url = ""
        self.api_token = ""

    def cli(self, *args: str, **env: str) -> None:
        """Run `rdc <args>` with per-command environment overrides (the bash `env K=V rdc ...`)."""
        self.d.run_with([self.rdc, *args], **env)

    def setup_sandbox(self) -> None:
        d = self.d
        d.step("Setup: isolated config directory")
        assert d.work is not None  # noqa: S101
        xdg = d.work / "xdg"
        self.config_dir = xdg / "rediacc"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        d.extra_env["XDG_CONFIG_HOME"] = str(xdg)
        d.note("XDG_CONFIG_HOME=%s" % xdg)
        # Pin the output format: the CLI auto-selects json whenever stdout is not a TTY, which a drill's never is, so without this every assertion would describe the machine-readable path while claiming to describe what an operator sees.
        d.extra_env["REDIACC_DEFAULT_OUTPUT"] = "table"
        key = d.work / "id_ed25519"
        proc = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-N", "", "-q", "-C", "drill-universe", "-f", str(key)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            log.error("ssh-keygen failed: %s" % proc.stderr.strip())
            raise SystemExit(2)

    def setup_account(self) -> None:
        d = self.d
        if self.restart:
            d.restart_gateway()
        else:
            d.step("Reusing the running dev gateway (--no-restart)")
            if not d.gateway_alive():
                log.error("No healthy dev gateway. Start one: ./run.sh account dev")
                raise SystemExit(1)
            d.gateway_port_cached = d.gateway_port()
        self.server_url = d.server_url()
        d.step("Setup: dev login, subscription and API token on %s" % self.server_url)
        d.account_ensure_login(EMAIL, PASSWORD)
        d.account_ensure_subscription(EMAIL, "PROFESSIONAL")
        assert d.work is not None  # noqa: S101
        jar = http.cookiejar.MozillaCookieJar(str(d.work / "cookies.txt"))
        if not d.account_session(EMAIL, PASSWORD, jar):
            raise SystemExit(1)
        sub = d.account_subscription_id(jar)
        self.api_token = d.account_mint_token(
            jar, sub, "drill-universe", ["license:read", "subscription:read"]
        )
        d.note("subscription %s, token %s..." % (sub, self.api_token[:12]))

    def md5(self, name: str) -> str:
        return lib.md5(self.config_dir / name)

    def phase_default_config(self) -> None:
        d = self.d
        d.step("Phase 1: the default config is created on first use, with labelled sources")
        self.cli("config", "current", "-o", "json")
        d.assert_exit(0, "config current succeeds on a cold config directory")
        d.assert_stdout_json("data.name", "rediacc", "default config is named rediacc")
        d.assert_stdout_json("data.fileExists", "true", "its file was created automatically")
        d.assert_stdout_json(
            "data.accountServerSource",
            "default",
            "accountServer is labelled as coming from the built-in default",
        )
        d.assert_stdout_json(
            "data.updateChannelSource",
            "default",
            "updateChannel is labelled as coming from the built-in default",
        )
        d.assert_stdout_json("data.tokenState", "missing", "no token yet")
        token_file = lib.json_get(d.stdout_text(), "data.tokenFile")
        d.assert_equal(
            "%s/api-token-rediacc.json" % self.config_dir,
            token_file,
            "the default config's token path is api-token-rediacc.json beside it",
        )

    def phase_named_configs(self) -> None:
        d = self.d
        d.step("Phase 2: two named configs, each a self-contained universe")
        self.cli("config", "init", "drill-a", "--server", self.server_url)
        d.assert_exit(0, "config init drill-a succeeds")
        d.assert_stdout_empty("config init writes nothing to stdout (the success line is stderr)")
        d.assert_stderr_contains(
            'Config "drill-a" initialized', "config init reports success on stderr"
        )
        d.assert_file_exists(self.config_dir / "drill-a.json", "drill-a.json was written")
        # The same failure told twice: the two renderings are different code paths, and only one is what a pipeline consumes.
        self.cli("config", "init", "drill-a", "--server", self.server_url)
        d.assert_exit(2, "re-initializing an existing config is a validation error (exit 2)")
        d.assert_stderr_contains("already exists", "text mode puts the reason on stderr")
        d.assert_stdout_empty("text mode leaves stdout clean on failure")
        self.cli("-o", "json", "config", "init", "drill-a", "--server", self.server_url)
        d.assert_exit(2, "the json rendering keeps the same exit code")
        d.assert_stdout_json("success", "false", "json mode reports success=false on stdout")
        d.assert_stdout_json(
            "errors[0].code", "VALIDATION_ERROR", "and classifies it as a validation error"
        )
        self.cli("config", "init", "drill-b", "--server", self.server_url)
        d.assert_exit(0, "config init drill-b succeeds")
        d.assert_file_exists(self.config_dir / "drill-b.json", "drill-b.json was written")

    def phase_precedence(self) -> None:
        d = self.d
        d.step("Phase 3: source labels and --config / REDIACC_CONFIG precedence")
        self.cli("config", "current", "-o", "json", REDIACC_CONFIG="drill-a")
        d.assert_exit(0, "REDIACC_CONFIG selects a config")
        d.assert_stdout_json("data.name", "drill-a", "REDIACC_CONFIG=drill-a selects drill-a")
        d.assert_stdout_json(
            "data.accountServerSource",
            "config",
            "a server stored in the config file is labelled source=config",
        )
        d.assert_stdout_json(
            "data.accountServer", self.server_url, "and the value is the one config init stored"
        )
        self.cli(
            "config",
            "current",
            "-o",
            "json",
            REDIACC_CONFIG="drill-a",
            REDIACC_ACCOUNT_SERVER="http://127.0.0.1:1",
        )
        d.assert_stdout_json(
            "data.accountServerSource",
            "env REDIACC_ACCOUNT_SERVER",
            "REDIACC_ACCOUNT_SERVER overrides the config file and is labelled as env",
        )
        d.assert_stdout_json(
            "data.accountServer", "http://127.0.0.1:1", "and the env value is the one that wins"
        )
        # The three-way case: the flag must beat an env var that is also set.
        self.cli("--config", "drill-b", "config", "current", "-o", "json", REDIACC_CONFIG="drill-a")
        d.assert_stdout_json(
            "data.name", "drill-b", "--config beats REDIACC_CONFIG when both name a config"
        )
        self.cli("config", "current", "-o", "json")
        d.assert_stdout_json(
            "data.name", "rediacc", "with neither flag nor env, the built-in default name applies"
        )

    def phase_isolation(self) -> None:
        d = self.d
        d.step("Phase 4: operating on one config leaves the others byte-identical")
        a_before = self.md5("drill-a.json")
        b_before = self.md5("drill-b.json")
        d.note("md5 drill-a=%s drill-b=%s" % (a_before, b_before))
        assert d.work is not None  # noqa: S101
        # A real mutation of drill-b: `config ssh set` writes credentials into the config file and touches no network.
        self.cli(
            "config", "ssh", "set", "--key", str(d.work / "id_ed25519"), REDIACC_CONFIG="drill-b"
        )
        d.assert_exit(0, "config ssh set mutates drill-b")
        b_after = self.md5("drill-b.json")
        a_after = self.md5("drill-a.json")
        d.assert_not_equal(b_before, b_after, "drill-b.json changed (the write landed)")
        d.assert_equal(a_before, a_after, "drill-a.json is byte-identical after work on drill-b")
        d.assert_equal(
            "absent", self.md5("api-token-drill-a.json"), "no token file appeared for drill-a"
        )

    def phase_tokens(self) -> None:
        d = self.d
        d.step("Phase 5: per-config token files")
        a_before = self.md5("drill-a.json")
        b_before = self.md5("drill-b.json")
        self.cli(
            "subscription",
            "login",
            "--token",
            self.api_token,
            "--server",
            self.server_url,
            REDIACC_CONFIG="drill-a",
        )
        d.assert_exit(0, "subscription login --token succeeds against the dev gateway")
        d.assert_file_exists(
            self.config_dir / "api-token-drill-a.json", "the login wrote api-token-drill-a.json"
        )
        d.assert_file_absent(
            self.config_dir / "api-token-drill-b.json", "and did NOT write a token for drill-b"
        )
        d.assert_file_absent(
            self.config_dir / "api-token-rediacc.json", "nor for the default config"
        )
        try:
            stored = lib.json_get(
                (self.config_dir / "api-token-drill-a.json").read_text(), "serverUrl"
            )
        except OSError:
            stored = ""
        d.assert_equal(
            self.server_url, stored, "the token file records the server it was validated against"
        )
        self.cli("config", "current", "-o", "json", REDIACC_CONFIG="drill-a")
        d.assert_stdout_json("data.tokenState", "ready", "drill-a reports tokenState=ready")
        self.cli("config", "current", "-o", "json", REDIACC_CONFIG="drill-b")
        d.assert_stdout_json(
            "data.tokenState",
            "missing",
            "drill-b still reports tokenState=missing (tokens do not leak across configs)",
        )
        d.assert_equal(
            b_before,
            self.md5("drill-b.json"),
            "drill-b.json is byte-identical after drill-a logged in",
        )
        d.assert_not_equal(
            a_before, self.md5("drill-a.json"), "drill-a.json recorded its server identity"
        )
        self.cli("subscription", "logout", REDIACC_CONFIG="drill-a")
        d.assert_exit(0, "subscription logout succeeds")
        d.assert_file_absent(
            self.config_dir / "api-token-drill-a.json", "logout removed drill-a's token file"
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
    drill = lib.Drill("universe", selftest=selftest, keep_work=keep_work)
    drill.init()
    rc = 1
    try:
        universe = Universe(drill, restart)
        universe.setup_sandbox()
        drill.selftest_probe()
        if selftest:
            # The selftest proves the accounting; making it wait a minute for a server it never queries would be a reason not to run it.
            drill.note("selftest mode: skipping the live phases")
            return drill.summary()
        universe.setup_account()
        universe.phase_default_config()
        universe.phase_named_configs()
        universe.phase_precedence()
        universe.phase_isolation()
        universe.phase_tokens()
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
