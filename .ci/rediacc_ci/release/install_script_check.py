#!/usr/bin/env python3
"""Port of `.ci/scripts/test/test-install-script.sh` (gate `test:install-script`).

Unit tests for `packages/www/public/install.sh` internals. Sources the script
with `REDIACC_INSTALL_SH_SOURCE_ONLY=1` to skip `main()` and exercises
individual functions against a throwaway HOME.

Covers:
  - detect_platform / detect_arch
  - write_install_config edge cases
  - cleanup_legacy_state migration
  - bin layout structure (no versions/ dir, staged-update cleared)
  - channel resolution (env > rediacc.json::account.updateChannel > 'stable')

REGISTERED CI GATE: `test:install-script`, step "Install-script tests" in `.github/workflows/ci-quality.yml`, job `quality-static`. The twin carries its own `---- gate ----` header because it IS the gate's run target.

WHAT MOVES AND WHAT DOES NOT. Only the HARNESS moves: the fresh HOMEs, the no-jq PATH shim, the assertions, the PASS/FAIL lines and the exit code. The SUBJECT stays bash -- every case still sources the real `install.sh` in a real `bash` and calls the real function -- because a Python reimplementation of the installer would be a second instrument certifying itself.

PORT NOTES, each driven before being written down.

**THE TWIN'S OWN COLOUR CONSTANTS ARE DEAD, AND THIS PORT REPRODUCES THE DEATH RATHER THAN THE INTENT.** `test-install-script.sh:26-33` sets `RED`/`GREEN`/`NC` to ANSI escapes and uses them in `log_pass`/`log_fail`, but every one of those calls happens AFTER a `source "$INSTALL_SH"`, and `install.sh:62-72` reassigns the SAME THREE NAMES -- to the same escapes when `[ -t 1 ]`, and
to EMPTY STRINGS otherwise. Driven both ways: piped to a file
the twin's output is a plain `PASS: ...`; run under a pty it is
`\\033[0;32mPASS:\\033[0m ...`. So the observable rule is install.sh's, not the
twin's, and this port asks `os.isatty(1)` at the same moment. Cosmetic only (a CI log is never a tty, so CI has always seen the uncoloured form), which is why it is reproduced and reported rather than fixed in a file this box does not own.

ONE `bash` PER CASE, NOT ONE FOR THE WHOLE RUN, and the state that leaks in the twin was checked rather than assumed. The twin sources `install.sh` into ONE persistent shell fourteen times, so a variable install.sh sets survives into the
next case; the only one that does is `REDIACC_CHANNEL`, assigned at
`install.sh:44` when a config carries `updateChannel`. It is set by `test_channel_inherits_from_config` and the very next case (`test_channel_env_overrides_config`) opens by assigning it explicitly, so the leak is unobservable. Every other case either unsets it or never reads it.

`set -euo pipefail` IS INHERITED BY EVERY SOURCE in the twin, so each snippet
below sets it too; `install.sh`'s `${VAR:-}` defaults exist precisely because of
`-u` and a port that dropped it would exercise different code.

`local p; p="$(command -v "$t")" && ln -sf ...` DOES NOT ABORT under `set -e`
when the tool is absent, because the assignment is not the last command of the `&&` list. So the no-jq shim is built best-effort and a missing `uuidgen` (this sandbox has none) simply leaves that name unshimmed. Reproduced with `shutil.which() is None -> skip`.

THE `mktemp` NAMES ARE THE ONE THING THIS PORT CANNOT KEEP, and unlike its two sibling ports this twin DOES quote them: the two `cleanup_legacy_state` failure messages embed `$HOME`, which is a `mktemp -d` path. Those lines are normalized in the differential and masked to `<tmp>` by the shadow-gate ledger's own rule.

Exit: 0 when all fourteen cases pass, 1 at the first that does not (the twin's `log_fail` is an immediate `exit 1`).
"""

from __future__ import annotations

import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths

INSTALL_SH_REL = "packages/www/public/install.sh"

# The tools the no-jq shim symlinks, in the twin's own order (`test-install-script.sh:150`). `jq` is deliberately NOT among them: hiding it is the point of the case.
NOJQ_TOOLS = (
    "grep",
    "sed",
    "awk",
    "cat",
    "mktemp",
    "mv",
    "rm",
    "chmod",
    "od",
    "tr",
    "uuidgen",
    "stat",
    "mkdir",
    "head",
    "curl",
    "uname",
    "dirname",
    "basename",
    "env",
)

PRESENT_CONFIG = (
    '{"schemaVersion":3,"id":"11111111-1111-4111-a111-111111111111","version":1,'
    '"encryption":{"mode":"plaintext"},"machines":{"keep":"yes"},"account":{}}'
)

CONFIG_WITH_EDGE = (
    '{"schemaVersion":3,"id":"11111111-1111-4111-a111-111111111111","version":1,'
    '"encryption":{"mode":"plaintext"},"account":{"accountServer":"https://eu.rediacc.com",'
    '"updateChannel":"edge"}}\n'
)

CONFIG_EDGE_NO_SERVER = (
    '{"schemaVersion":3,"id":"11111111-1111-4111-a111-111111111111","version":1,'
    '"encryption":{"mode":"plaintext"},"account":{"updateChannel":"edge"}}\n'
)

CONFIG_NO_CHANNEL = (
    '{"schemaVersion":3,"id":"11111111-1111-4111-a111-111111111111","version":1,'
    '"encryption":{"mode":"plaintext"},"account":{"accountServer":"https://eu.rediacc.com",'
    '"region":"eu"}}\n'
)


class CaseFailedError(Exception):
    """`log_fail`, which in the twin is an immediate `exit 1`."""


def colours() -> tuple[str, str, str]:
    """RED, GREEN, NC as `install.sh:62-72` sets them: only on a tty.

    Asked at every call rather than cached, because the twin re-evaluates `[ -t 1 ]` on every `source` and a caller may have redirected in between.
    """
    try:
        tty = os.isatty(sys.stdout.fileno())
    except (AttributeError, OSError, ValueError):
        tty = False
    if tty:
        return "\033[0;31m", "\033[0;32m", "\033[0m"
    return "", "", ""


def log_fail(message: str) -> None:
    red, _green, nc = colours()
    print("%sFAIL:%s %s" % (red, nc, message), file=sys.stderr, flush=True)
    raise CaseFailedError


def log_pass(message: str) -> None:
    _red, green, nc = colours()
    print("%sPASS:%s %s" % (green, nc, message), flush=True)


class Shell:
    """`source_install` plus a body, run as one `bash` with the twin's options."""

    def __init__(self, install_sh: pathlib.Path, temp: pathlib.Path) -> None:
        self.install_sh = install_sh
        self.temp = temp

    def fresh_home(self) -> pathlib.Path:
        """`mktemp -d "$TEMP/home.XXXXXX"`."""
        return pathlib.Path(tempfile.mkdtemp(prefix="home.", dir=self.temp))

    def run(self, home: pathlib.Path, body: str, *, prelude: str = "") -> str:
        """`source_install "$home"` then `body`; returns the body's stdout.

        `prelude` holds the assignments the twin makes BEFORE the source
        (`unset REDIACC_CHANNEL`, `REDIACC_CHANNEL=stable`), which is where they
        have to be: `install.sh:40` reads the variable at source time.
        """
        script = (
            "set -euo pipefail\n"
            'export HOME="%s"\n'
            "export REDIACC_INSTALL_SH_SOURCE_ONLY=1\n"
            "unset XDG_CONFIG_HOME\n"
            "%s"
            'source "%s"\n'
            "%s" % (home, prelude, self.install_sh, body)
        )
        completed = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            # `set -e` in the twin: the sourced shell dying takes the run with it, with the child's own diagnostics already on stderr.
            sys.stderr.write(completed.stderr)
            sys.stderr.flush()
            raise CaseFailedError
        return completed.stdout


# --------------------------------------------------------------------------- The fourteen cases, in the twin's order ---------------------------------------------------------------------------


def test_detect_platform(sh: Shell) -> None:
    home = sh.fresh_home()
    got = sh.run(home, "detect_platform\n").rstrip("\n")
    system = platform.uname().system
    if system == "Linux" and got != "linux":
        log_fail("detect_platform: expected linux, got %s" % got)
    if system == "Darwin" and got != "mac":
        log_fail("detect_platform: expected mac, got %s" % got)
    log_pass("detect_platform matches uname")


def test_detect_arch(sh: Shell) -> None:
    home = sh.fresh_home()
    got = sh.run(home, "detect_arch\n").rstrip("\n")
    machine = platform.uname().machine
    if machine in ("x86_64", "amd64") and got != "x64":
        log_fail("detect_arch: expected x64, got %s" % got)
    if machine in ("arm64", "aarch64") and got != "arm64":
        log_fail("detect_arch: expected arm64, got %s" % got)
    log_pass("detect_arch matches uname -m")


def _config(home: pathlib.Path) -> pathlib.Path:
    return home / ".config" / "rediacc" / "rediacc.json"


def test_write_install_config_default_noop(sh: Shell) -> None:
    home = sh.fresh_home()
    sh.run(
        home,
        "CHANNEL=stable SERVER_URL='' RELEASES_URL=https://releases.rediacc.com "
        "write_install_config >/dev/null 2>&1 || true\n",
    )
    config = _config(home)
    if config.is_file():
        log_fail(
            "write_install_config should not write on default channel + no server (wrote: %s)"
            % config.read_text(encoding="utf-8").rstrip("\n")
        )
    log_pass("default channel + no server -> no rediacc.json")


def _mode(config: pathlib.Path) -> str:
    """`stat -c '%a'` / `stat -f '%A'`: octal access rights, unpadded."""
    return "%o" % (config.stat().st_mode & 0o7777)


def test_write_install_config_channel_only(sh: Shell) -> None:
    home = sh.fresh_home()
    sh.run(
        home,
        "CHANNEL=edge SERVER_URL='' RELEASES_URL=https://releases.rediacc.com "
        "write_install_config >/dev/null 2>&1\n",
    )
    config = _config(home)
    if not config.is_file():
        log_fail("write_install_config should write rediacc.json when channel != stable")
    body = config.read_text(encoding="utf-8").rstrip("\n")
    if '"updateChannel":"edge"' not in body:
        log_fail("updateChannel field not edge: %s" % body)
    if '"accountServer":"https://www.rediacc.com"' not in body:
        log_fail("accountServer should default to production: %s" % body)
    # The absent-file branch must produce a valid minimal v3 config, not a bare account blob -- the CLI parses this file directly.
    if '"schemaVersion":3' not in body:
        log_fail("minimal config must carry schemaVersion 3: %s" % body)
    if '"encryption":{"mode":"plaintext"}' not in body:
        log_fail("minimal config must be plaintext: %s" % body)
    perms = _mode(config)
    if perms != "600":
        log_fail("rediacc.json mode must be 600 (got %s)" % perms)
    log_pass("non-default channel writes rediacc.json with correct fields and mode")


def test_write_install_config_custom_releases(sh: Shell) -> None:
    home = sh.fresh_home()
    sh.run(
        home,
        "CHANNEL=stable SERVER_URL=https://custom.example RELEASES_URL=https://my.r2.example "
        "write_install_config >/dev/null 2>&1 || true\n",
    )
    config = _config(home)
    if not config.is_file():
        log_fail("write_install_config should write when SERVER_URL is set")
    body = config.read_text(encoding="utf-8").rstrip("\n")
    if '"releasesUrl":"https://my.r2.example"' not in body:
        log_fail("releasesUrl must persist: %s" % body)
    log_pass("custom releases URL persists in rediacc.json")


def build_nojq_shim(temp: pathlib.Path) -> pathlib.Path:
    """`mktemp -d "$TEMP/nojq.XXXXXX"` + the twin's best-effort symlink loop."""
    shim = pathlib.Path(tempfile.mkdtemp(prefix="nojq.", dir=temp))
    for tool in NOJQ_TOOLS:
        found = shutil.which(tool)
        if found is None:
            continue  # `command -v` failed: the `&& ln -sf` simply does not run
        link = shim / tool
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(found)
    return shim


def test_write_install_config_present_no_jq_untouched(sh: Shell) -> None:
    """Present config + no jq: the config is user data and must not be rewritten."""
    home = sh.fresh_home()
    config = _config(home)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(PRESENT_CONFIG, encoding="utf-8")
    before = config.read_text(encoding="utf-8")
    shim = build_nojq_shim(sh.temp)
    out = sh.run(
        home,
        'out="$(PATH="%s" CHANNEL=edge SERVER_URL="" '
        'RELEASES_URL=https://releases.rediacc.com write_install_config 2>&1 || true)"\n'
        "printf '%%s' \"$out\"\n" % shim,
    )
    after = config.read_text(encoding="utf-8")
    if before != after:
        log_fail(
            "no-jq path must not modify the live config (before=%s after=%s)" % (before, after)
        )
    if "rdc update --channel edge" not in out:
        log_fail("no-jq path must print the follow-up command: %s" % out)
    log_pass("present config + no jq -> untouched, prints follow-up command")


def test_cleanup_legacy_state_removes_versions_dir(sh: Shell) -> None:
    home = sh.fresh_home()
    legacy = home / ".local" / "share" / "rediacc" / "versions"
    (legacy / "1.0.3").mkdir(parents=True, exist_ok=True)
    (legacy / "1.0.3" / "rdc").touch()
    (legacy / "1.0.3" / "rdc.old").touch()
    sh.run(home, "cleanup_legacy_state >/dev/null 2>&1\n")
    if legacy.is_dir():
        log_fail("cleanup_legacy_state must remove %s" % legacy)
    log_pass("cleanup_legacy_state removes legacy versions/ dir")


def test_cleanup_legacy_state_removes_staged_update(sh: Shell) -> None:
    home = sh.fresh_home()
    staged = home / ".cache" / "rediacc" / "staged-update"
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "rdc-1.0.5").touch()
    sh.run(home, "cleanup_legacy_state >/dev/null 2>&1\n")
    if staged.is_dir():
        log_fail("cleanup_legacy_state must remove %s" % staged)
    log_pass("cleanup_legacy_state removes staged-update/ dir")


def test_no_versions_constant(sh: Shell) -> None:
    """The dead "5 versions retained" feature must be gone entirely."""
    home = sh.fresh_home()
    got = sh.run(
        home,
        "set +u\n"
        'if [[ -n "${VERSIONS_DIR+defined}" || -n "${MAX_VERSIONS+defined}" ]]; then\n'
        "    printf 'defined\\n'\n"
        "else\n"
        "    printf 'absent\\n'\n"
        "fi\n",
    ).rstrip("\n")
    if got != "absent":
        log_fail("VERSIONS_DIR / MAX_VERSIONS must not be defined under the new layout")
    log_pass("legacy VERSIONS_DIR / MAX_VERSIONS constants removed")


# Channel resolution (env > rediacc.json::account.updateChannel > 'stable'). Asymmetry between install.sh defaulting to stable and `rdc update` reading the config caused a real user-visible bug: stable install followed by an immediate "update" jumping to edge. These four cases pin the unified contract.


def _channel(sh: Shell, home: pathlib.Path, prelude: str) -> str:
    return sh.run(home, "printf '%s\\n' \"$CHANNEL\"\n", prelude=prelude).rstrip("\n")


def test_channel_default_stable_when_unset(sh: Shell) -> None:
    home = sh.fresh_home()
    channel = _channel(sh, home, "unset REDIACC_CHANNEL\n")
    if channel != "stable":
        log_fail("no env, no config -> CHANNEL must be stable, got: %s" % channel)
    log_pass("no env, no config -> stable")


def test_channel_inherits_from_config(sh: Shell) -> None:
    home = sh.fresh_home()
    config = _config(home)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(CONFIG_WITH_EDGE, encoding="utf-8")
    channel = _channel(sh, home, "unset REDIACC_CHANNEL\n")
    if channel != "edge":
        log_fail("config account.updateChannel=edge must be inherited, got: %s" % channel)
    log_pass("no env + config account.updateChannel=edge -> edge")


def test_channel_env_overrides_config(sh: Shell) -> None:
    home = sh.fresh_home()
    config = _config(home)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(CONFIG_EDGE_NO_SERVER, encoding="utf-8")
    channel = _channel(sh, home, "REDIACC_CHANNEL=stable\n")
    if channel != "stable":
        log_fail("REDIACC_CHANNEL=stable must override config edge, got: %s" % channel)
    log_pass("env REDIACC_CHANNEL=stable overrides config edge")


def test_channel_malformed_config_falls_back(sh: Shell) -> None:
    home = sh.fresh_home()
    config = _config(home)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("not even valid json {{{", encoding="utf-8")
    channel = _channel(sh, home, "unset REDIACC_CHANNEL\n")
    if channel != "stable":
        log_fail("malformed config must fall back to stable, got: %s" % channel)
    log_pass("malformed config -> stable fallback")


def test_channel_config_without_updateChannel(sh: Shell) -> None:  # noqa: N802 -- the twin's name
    home = sh.fresh_home()
    config = _config(home)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(CONFIG_NO_CHANNEL, encoding="utf-8")
    channel = _channel(sh, home, "unset REDIACC_CHANNEL\n")
    if channel != "stable":
        log_fail("config without updateChannel must default to stable, got: %s" % channel)
    log_pass("config without updateChannel -> stable")


CASES = (
    test_detect_platform,
    test_detect_arch,
    test_write_install_config_default_noop,
    test_write_install_config_channel_only,
    test_write_install_config_custom_releases,
    test_write_install_config_present_no_jq_untouched,
    test_cleanup_legacy_state_removes_versions_dir,
    test_cleanup_legacy_state_removes_staged_update,
    test_no_versions_constant,
    test_channel_default_stable_when_unset,
    test_channel_inherits_from_config,
    test_channel_env_overrides_config,
    test_channel_malformed_config_falls_back,
    test_channel_config_without_updateChannel,
)


def main(argv: list[str]) -> int:  # noqa: ARG001 -- the twin takes no arguments
    install_sh = paths.repo_root() / INSTALL_SH_REL
    temp = pathlib.Path(tempfile.mkdtemp())
    try:
        sh = Shell(install_sh, temp)
        for case in CASES:
            case(sh)
        print(flush=True)  # the twin's bare `echo ""`
        log_pass("all install.sh unit cases")
        return 0
    except CaseFailedError:
        return 1
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
