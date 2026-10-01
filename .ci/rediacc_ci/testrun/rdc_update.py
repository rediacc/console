"""Port of `.ci/scripts/test/test-rdc-update.sh`: seven `rdc update` / `install.sh` lifecycle scenarios against a local fixture server.

`RDC_BINARY` names the real `rdc` executable under test; each scenario isolates `HOME` in a throwaway directory, installs through the real `packages/www/public/install.sh` against the fixture, and drives the installed `rdc`. The fixture tree layout (`cli/<channel>/manifest.json|latest.json|<binary>|<binary>.sha256`, plus `cli/v<version>/` for stable and edge), the manifest shape and every assertion are the twin's.

Deliberate differences from the twin (Rule T), each with a test that fails on the bash behaviour:

  1. A FAILING PREREQUISITE LEAKED. Under `set -e` a failed install, fixture start or `prep_fixture` ended the whole script before `stop_fixture` and `rm -rf`, leaving the fixture server and the temporary tree behind (the twin's own comment records 254 orphaned servers). Every scenario cleans up in a `finally`, and a failed prerequisite fails only that scenario, with the installer's output tail attached (the twin discarded it).
  2. THE FIXTURE SERVER IS IN-PROCESS. No `python3 -m http.server` subprocess, no readiness poll loop, no port chosen by bind-and-close (a race between choosing and binding).
  3. `sha256-mismatch` AND `rollback-empty` ACCEPTED ANY FAILURE. A refused update because the fixture server was unreachable passed as "sha mismatch aborts update". The output must carry the product's own reason: `failed checksum verification` and `No previous version found` respectively.
  4. UNKNOWN SCENARIO NAMES ARE REFUSED UP FRONT. The twin ran the scenarios before the bad name and only then exited 2. The usage text also promised `up-to-date`, `force`, `stage-apply` and `concurrent`, which never existed; it lists the seven real ones.
  5. `reinstall` RAN `install.sh` WITH THE HOST'S XDG_* VARIABLES, unlike `fresh_install`. A runner with `XDG_DATA_HOME` set would migrate the wrong directory. Both paths now share one environment.
  6. COLOUR ONLY ON A TTY: the twin printed escape sequences into captured logs.
"""

import dataclasses
import functools
import hashlib
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import typing

from rediacc_ci import log, paths
from rediacc_ci.core import platform

SCENARIOS = (
    "happy",
    "check-only",
    "sha256-mismatch",
    "rollback",
    "rollback-empty",
    "channel-switch",
    "reinstall",
)
USAGE = (
    "usage: RDC_BINARY=/path/to/rdc test-rdc-update.sh [scenario ...]\n"
    f"  scenarios: {', '.join(SCENARIOS)}, all (default)"
)
BOGUS_SHA = "f" * 64
XDG_NAMES = ("XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME")
UPDATE_DISABLING = ("CI", "GITHUB_ACTIONS", "GITHUB_RUN_ID", "RUNNER_OS")
INSTALL_TAIL_LINES = 20


class Fixture:
    """A throwaway tree served over HTTP on 127.0.0.1, shaped like releases.rediacc.com."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        handler = functools.partial(_QuietHandler, directory=str(root))
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def prep(
        self,
        channel: str,
        version: str,
        platform_key: str,
        binary_name: str,
        rdc_binary: pathlib.Path,
        override_sha: str = "",
    ) -> None:
        """Write manifest.json, latest.json, the binary and its sha256 sidecar for one channel (the twin's `prep_fixture`)."""
        sha = hashlib.sha256(rdc_binary.read_bytes()).hexdigest()
        channel_dir = self.root / "cli" / channel
        channel_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(rdc_binary, channel_dir / binary_name)
        (channel_dir / f"{binary_name}.sha256").write_text(f"{sha}  {binary_name}\n")
        versioned = channel in ("stable", "edge")
        if versioned:
            version_dir = self.root / "cli" / f"v{version}"
            version_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(rdc_binary, version_dir / binary_name)
            (version_dir / f"{binary_name}.sha256").write_text(f"{sha}  {binary_name}\n")
        url = (
            f"{self.url}/cli/v{version}/{binary_name}"
            if versioned
            else f"{self.url}/cli/{channel}/{binary_name}"
        )
        manifest = {
            "version": version,
            "releaseNotesUrl": f"https://example.invalid/notes/v{version}",
            "binaries": {
                platform_key: {
                    "url": url,
                    "sha256": override_sha or sha,
                    "size": rdc_binary.stat().st_size,
                }
            },
        }
        (channel_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (channel_dir / "latest.json").write_text(
            json.dumps({"version": version}, separators=(",", ":")) + "\n"
        )

    def drop(self, channel: str, version: str) -> None:
        shutil.rmtree(self.root / "cli" / channel, ignore_errors=True)
        shutil.rmtree(self.root / "cli" / f"v{version}", ignore_errors=True)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return


def platform_key() -> str:
    """`linux-x64`, `mac-arm64`: the keys of the manifest's `binaries` map."""
    return f"{platform.os_for('sea')}-{platform.arch_for('node')}"


def binary_name_for(key: str, musl: bool) -> str:
    os_name, _, arch = key.partition("-")
    if os_name == "linux":
        return f"rdc-linux-musl-{arch}" if musl else f"rdc-linux-{arch}"
    if os_name == "mac":
        return f"rdc-mac-{arch}"
    raise platform.UnsupportedPlatformError(f"unsupported {os_name}")


def host_is_musl() -> bool:
    done = subprocess.run(["ldd", "--version"], capture_output=True, text=True, check=False)
    return "musl" in (done.stdout + done.stderr).lower()


@dataclasses.dataclass
class Context:
    rdc_binary: pathlib.Path
    install_sh: pathlib.Path
    key: str
    binary_name: str
    failures: list[str] = dataclasses.field(default_factory=list)

    def fail(self, message: str) -> None:
        self.failures.append(message)
        _emit("FAIL:", message, sys.stderr, "\033[0;31m")


def _emit(label: str, message: str, stream: typing.TextIO, colour: str) -> None:
    if log.colour_allowed(stream):
        stream.write(f"{colour}{label}\033[0m {message}\n")
    else:
        stream.write(f"{label} {message}\n")
    stream.flush()


def _env(
    home: pathlib.Path, base: dict[str, str] | None = None, drop: tuple[str, ...] = ()
) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in XDG_NAMES and k not in drop}
    env["HOME"] = str(home)
    env.update(base or {})
    return env


def fresh_install(ctx: Context, home: pathlib.Path, fixture: Fixture, channel: str) -> bool:
    """Run the real install.sh against the fixture into an isolated HOME. False when the installer failed."""
    home.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        ["bash", str(ctx.install_sh)],
        env=_env(home, {"REDIACC_RELEASES_URL": fixture.url, "REDIACC_CHANNEL": channel}),
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if done.returncode != 0:
        tail = "\n".join((done.stdout + done.stderr).splitlines()[-INSTALL_TAIL_LINES:])
        ctx.fail(f"install.sh exited {done.returncode}; last output:\n{tail}")
        return False
    if not (home / ".local/bin/rdc").is_symlink():
        ctx.fail("fresh_install: symlink missing")
    if not os.access(home / ".local/share/rediacc/bin/rdc", os.X_OK):
        ctx.fail("fresh_install: binary missing")
    return True


def run_rdc(home: pathlib.Path, fixture: Fixture, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the installed rdc with the fixture as its releases URL. CI markers are removed so the updater is not auto-disabled; XDG_* are removed so config, state and cache resolve under the isolated HOME."""
    return subprocess.run(
        [str(home / ".local/bin/rdc"), *args],
        env=_env(
            home,
            {
                "REDIACC_RELEASES_URL": fixture.url,
                "REDIACC_DISABLE_AUTOUPDATE": "0",
                "REDIACC_TELEMETRY_DISABLED": "1",
            },
            UPDATE_DISABLING,
        ),
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
    )


def combined(done: subprocess.CompletedProcess[str]) -> str:
    return done.stdout + done.stderr


class Scenario:
    """The shared setup and teardown: a temp tree, a fixture server, edge 1.0.3 prepped."""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="rdc-update-"))
        self.home = self.tmp / "home"
        self.fixture: Fixture | None = None

    def start(self, *prepped: tuple[str, str]) -> Fixture:
        self.fixture = Fixture(self.tmp / "fixture")
        for channel, version in prepped:
            self.fixture.prep(
                channel, version, self.ctx.key, self.ctx.binary_name, self.ctx.rdc_binary
            )
        return self.fixture

    def close(self) -> None:
        if self.fixture is not None:
            self.fixture.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def newer(self, version: str = "1.0.4", override_sha: str = "") -> None:
        assert self.fixture is not None  # noqa: S101 - set by start()
        self.fixture.drop("edge", "1.0.3")
        self.fixture.prep(
            "edge", version, self.ctx.key, self.ctx.binary_name, self.ctx.rdc_binary, override_sha
        )

    @property
    def bin_dir(self) -> pathlib.Path:
        return self.home / ".local/share/rediacc/bin"


def expect_file(ctx: Context, path: pathlib.Path) -> None:
    if not path.is_file():
        ctx.fail(f"expected file: {path}")


def expect_absent(ctx: Context, path: pathlib.Path) -> None:
    if path.exists() or path.is_symlink():
        ctx.fail(f"unexpected file: {path}")


def expect_symlink(ctx: Context, path: pathlib.Path) -> None:
    if not path.is_symlink():
        ctx.fail(f"expected symlink: {path}")


def pending_update_cleared(state: pathlib.Path) -> bool:
    try:
        return json.loads(state.read_text()).get("pendingUpdate") is None
    except (OSError, ValueError):
        return False


def scenario_happy(s: Scenario) -> str:
    ctx = s.ctx
    log.step("scenario: happy-path update")
    fixture = s.start(("edge", "1.0.3"))
    if not fresh_install(ctx, s.home, fixture, "edge"):
        return ""
    s.newer()
    # --force bypasses the compareVersions short-circuit: the binary under test often carries a baked-in version at or above the fixture's, and this scenario exercises swap mechanics, not version comparison.
    done = run_rdc(s.home, fixture, "update", "--force")
    if done.returncode != 0:
        ctx.fail(f"rdc update non-zero exit: {combined(done)}")
    expect_file(ctx, s.bin_dir / "rdc")
    expect_file(ctx, s.bin_dir / "rdc.old")
    expect_symlink(ctx, s.home / ".local/bin/rdc")
    state = s.home / ".local/state/rediacc/update-state.json"
    if state.is_file() and not pending_update_cleared(state):
        ctx.fail("state file pendingUpdate not cleared after update")
    return "happy-path update"


def scenario_check_only(s: Scenario) -> str:
    ctx = s.ctx
    log.step("scenario: check-only")
    fixture = s.start(("edge", "1.0.3"))
    if not fresh_install(ctx, s.home, fixture, "edge"):
        return ""
    s.newer()
    if run_rdc(s.home, fixture, "update", "--check-only").returncode != 0:
        ctx.fail("--check-only non-zero")
    expect_absent(ctx, s.bin_dir / "rdc.old")
    return "check-only does not swap"


def scenario_sha256_mismatch(s: Scenario) -> str:
    ctx = s.ctx
    log.step("scenario: sha256 mismatch")
    fixture = s.start(("edge", "1.0.3"))
    if not fresh_install(ctx, s.home, fixture, "edge"):
        return ""
    s.newer(override_sha=BOGUS_SHA)
    done = run_rdc(s.home, fixture, "update", "--force")
    if done.returncode == 0:
        ctx.fail("sha mismatch should have failed update")
    elif "failed checksum verification" not in combined(done):
        ctx.fail(f"update failed, but not for the checksum: {combined(done).strip()}")
    expect_absent(ctx, s.bin_dir / "rdc.old")
    return "sha256 mismatch aborts update"


def scenario_rollback(s: Scenario) -> str:
    ctx = s.ctx
    log.step("scenario: rollback")
    fixture = s.start(("edge", "1.0.3"))
    if not fresh_install(ctx, s.home, fixture, "edge"):
        return ""
    s.newer()
    update = run_rdc(s.home, fixture, "update", "--force")
    if update.returncode != 0:
        ctx.fail(f"update prerequisite failed: {combined(update)}")
    expect_file(ctx, s.bin_dir / "rdc.old")
    rollback = run_rdc(s.home, fixture, "update", "--rollback")
    if rollback.returncode != 0:
        ctx.fail(f"rollback non-zero: {combined(rollback)}")
    expect_absent(ctx, s.bin_dir / "rdc.old")
    return "rollback restores previous binary and consumes .old"


def scenario_rollback_empty(s: Scenario) -> str:
    ctx = s.ctx
    log.step("scenario: rollback without backup")
    fixture = s.start(("edge", "1.0.3"))
    if not fresh_install(ctx, s.home, fixture, "edge"):
        return ""
    done = run_rdc(s.home, fixture, "update", "--rollback")
    if done.returncode == 0:
        ctx.fail("rollback without .old should have failed")
    elif "No previous version found" not in combined(done):
        ctx.fail(f"rollback failed, but not for a missing backup: {combined(done).strip()}")
    return "rollback without backup exits non-zero"


def scenario_reinstall(s: Scenario) -> str:
    ctx = s.ctx
    log.step("scenario: re-install preserves layout, cleans staged-update")
    fixture = s.start(("edge", "1.0.3"))
    if not fresh_install(ctx, s.home, fixture, "edge"):
        return ""
    legacy = s.home / ".local/share/rediacc/versions/1.0.0"
    legacy.mkdir(parents=True)
    (legacy / "rdc").touch()
    (legacy / "rdc.old").touch()
    staged = s.home / ".cache/rediacc/staged-update"
    staged.mkdir(parents=True)
    (staged / "rdc-99.99.99").touch()
    if not fresh_install(ctx, s.home, fixture, "edge"):
        return ""
    expect_absent(ctx, s.home / ".local/share/rediacc/versions")
    expect_absent(ctx, s.home / ".cache/rediacc/staged-update")
    expect_file(ctx, s.bin_dir / "rdc")
    expect_symlink(ctx, s.home / ".local/bin/rdc")
    return "re-install migrates legacy layout + clears staged-update"


def scenario_channel_switch(s: Scenario) -> str:
    ctx = s.ctx
    log.step("scenario: channel switch persists to rediacc.json")
    fixture = s.start(("stable", "1.0.3"), ("edge", "1.0.3"))
    if not fresh_install(ctx, s.home, fixture, "stable"):
        return ""
    # `rdc update --channel edge` writes account.updateChannel into the default config, creating it when absent.
    if run_rdc(s.home, fixture, "update", "--channel", "edge", "--check-only").returncode != 0:
        ctx.fail("--channel edge --check-only non-zero")
    config = s.home / ".config/rediacc/rediacc.json"
    expect_file(ctx, config)
    try:
        channel = json.loads(config.read_text()).get("account", {}).get("updateChannel")
    except (OSError, ValueError):
        channel = None
    if channel != "edge":
        ctx.fail("rediacc.json did not record account.updateChannel=edge")
    return "channel switch writes rediacc.json"


HANDLERS: dict[str, typing.Callable[[Scenario], str]] = {
    "happy": scenario_happy,
    "check-only": scenario_check_only,
    "sha256-mismatch": scenario_sha256_mismatch,
    "rollback": scenario_rollback,
    "rollback-empty": scenario_rollback_empty,
    "channel-switch": scenario_channel_switch,
    "reinstall": scenario_reinstall,
}


def run_scenario(ctx: Context, name: str) -> bool:
    before = len(ctx.failures)
    scenario = Scenario(ctx)
    passed_text = ""
    try:
        passed_text = HANDLERS[name](scenario)
    finally:
        scenario.close()
    ok = len(ctx.failures) == before
    if ok and passed_text:
        _emit("PASS:", passed_text, sys.stdout, "\033[0;32m")
    return ok


def main(argv: list[str]) -> int:
    # Children inherit stdout: line buffering keeps this process's lines in order with theirs when stdout is a pipe.
    if (reconfigure := getattr(sys.stdout, "reconfigure", None)) is not None:
        reconfigure(line_buffering=True)
    selected = argv or ["all"]
    if selected[0] == "all":
        selected = list(SCENARIOS)
    for name in selected:
        if name not in HANDLERS:
            print(f"unknown scenario: {name}", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 2
    binary = os.environ.get("RDC_BINARY")
    if not binary:
        print("error: RDC_BINARY env var must point to an rdc executable", file=sys.stderr)
        return 2
    if not os.access(binary, os.X_OK) or not os.path.isfile(binary):
        print(f"error: RDC_BINARY={binary} is not executable", file=sys.stderr)
        return 2
    rdc_binary = pathlib.Path(binary).resolve()
    try:
        key = platform_key()
        name = binary_name_for(key, host_is_musl())
    except platform.PlatformError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    ctx = Context(
        rdc_binary, paths.repo_root() / "packages" / "www" / "public" / "install.sh", key, name
    )
    failed = [n for n in selected if not run_scenario(ctx, n)]
    print()
    if failed:
        _emit("FAILED:", " ".join(failed), sys.stderr, "\033[0;31m")
        return 1
    text = "ALL SCENARIOS PASSED"
    print(f"\033[0;32m{text}\033[0m" if log.colour_allowed(sys.stdout) else text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
