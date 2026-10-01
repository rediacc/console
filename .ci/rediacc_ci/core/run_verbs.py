"""The verbs `./run.sh` used to serve from `.ci/legacy/run-legacy.sh`, one entry function each.

WHAT THIS REPLACES. `.ci/legacy/run-legacy.sh` was the dispatcher for service, account, rotation, worktree, devbox, drill, quality, fix, clean and help. Each verb here is the same arm in Python, calling the ports that already existed (`core.service`, `core.account`, `core.account_lifecycle`, `core.devbox`, `core.local_common`, `core.toolchain`, `security.shellcheck`, `security.shfmt`,
`quality.submodule_branches`) rather than a second copy of them. `rediacc_ci/__main__.py` names every entry below in its VERBS table; `./run.sh` forwards everything except the two media verbs to it.

EVERY ENTRY TAKES THE VERB'S REMAINING ARGV (verb already removed) and RETURNS AN EXIT STATUS, which is what `__main__` expects. An entry that hands the terminal to a child (`devbox shell`) lets that child own the exit code and the signals, as `exec` did in the router.

WHERE THIS DIFFERS FROM THE BASH ON PURPOSE (Rule T). Each is pinned by `tests/test_core_run_verbs.py`:

  D1. `quality ...`, `fix ...` and `clean` ACT ON THE REPOSITORY ROOT. The bash ran `npm run ...`, `find .ci` and `rm -rf dist/` in the caller's directory, so `cd packages/cli && ./run.sh quality lint` linted one package and `./run.sh clean` from a subdirectory deleted that directory's `dist/` instead of the repository's.
  D2. `quality deps` RUNS THE DEPENDENCY GATE. The bash called `.ci/scripts/quality/check-deps.sh`, a file that does not exist (exit 127, "No such file or directory"); the gate is `scripts/gates/check-deps.ts`, the `check:deps` script.
  D3. `fix shell` FORMATS THE FILES THE GATE CHECKS, through the gate's own enumeration. The bash ran `find .ci -name '*.sh' -exec shfmt -w`, which rewrote third-party scripts unpacked under the gitignored `.ci/cache/`, skipped `.claude/` and `.github/` that `security.shfmt` checks, and so could leave a tree the gate then rejected.
  D4. `help` lists `setup` once. The bash printed it under DEVELOPMENT COMMANDS and again under MAINTENANCE with a description ("Interactive setup: npm deps + native modules + git identity") that no longer matches what `setup` does.
  D5. `quality submodules` runs `rediacc_ci.quality.submodule_branches`, the live port, not the bash twin it was proved against.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.core import account, account_lifecycle, devbox, local_common, service, toolchain
from rediacc_ci.security import shfmt
from rediacc_ci.well_known import DEV_USER_EMAIL, WEB_IMAGE_REPO

if TYPE_CHECKING:  # pragma: no cover - annotations only
    import pathlib

# What a verb hands over to. Every drill and `worktree` are Python (`rediacc_ci.drills`, `rediacc_ci.dev.worktree`). `WORKTREE_SCRIPT` names the bash twin of `worktree`, which nothing executes any more: it stays named only so check:ci-scope-scripts-reachability keeps it reachable as a differential oracle until PLAN-retire-bash-oracles B3 freezes its goldens and deletes it. The drills' bash twins were frozen and deleted there.
DRILL_MODULES = {
    "universe": "rediacc_ci.drills.universe",
    "transfer": "rediacc_ci.drills.transfer",
    "license": "rediacc_ci.drills.license",
    "backup": "rediacc_ci.drills.backup",
}
WORKTREE_SCRIPT = "scripts/dev/worktree.sh"

# `quality <verb>` -> the `scripts/gates` program it runs, and the line it announces first.
QUALITY_TS_GATES = {
    "actions": (
        "scripts/gates/check-actions.ts",
        "Checking GitHub Actions versions...",
    ),
    "suppressions": (
        "scripts/gates/check-suppression-liveness.ts",
        "Checking suppression liveness (are allowlist entries still needed?)...",
    ),
    "dead-bash": (
        "scripts/gates/check-dead-bash.ts",
        "Checking for dead shell functions and orphaned scripts...",
    ),
}

# What `clean` removes, relative to the repository root. `packages/*/dist` is a glob.
CLEAN_PATHS = ("dist", "node_modules/.vite")
CLEAN_GLOB = "packages/*/dist"


def root() -> pathlib.Path:
    return paths.repo_root()


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def _run(argv: list[str], *, cwd: pathlib.Path | None = None) -> int:
    """Run a child with this process's streams; its exit status, or 127 when it cannot be started."""
    _flush()
    try:
        return subprocess.call(argv, cwd=str(cwd or root()))
    except OSError as exc:
        log.error("%s: %s" % (argv[0], exc.strerror or exc))
        return 127


def _node_ok() -> bool:
    """`check_node_version`, which logs its own reason. A failure ends the verb with status 1, as errexit ended the bash."""
    return local_common.check_node_version()


def _npm(*args: str) -> int:
    return _run(["npm", *args])


def _tsx(script: str) -> int:
    return _run(["npx", "tsx", str(root() / script)])


Arm = Callable[[list[str]], int]


def usage_line(verb: str, arms: Mapping[str, object], notes: dict[str, str] | None = None) -> str:
    """`Usage: ./run.sh <verb> [a|b|c]`, GENERATED from the dispatch table so the usage line cannot drift from what the verb serves. `notes` appends a spelled-out parameter group to one arm (`url [term|account|db]`)."""
    notes = notes or {}
    return "Usage: ./run.sh %s [%s]" % (verb, "|".join(key + notes.get(key, "") for key in arms))


def dispatch(
    verb: str,
    arms: dict[str, Arm],
    argv: list[str],
    *,
    default: str | None = None,
    notes: dict[str, str] | None = None,
) -> int:
    """Run the arm named by `argv[0]` (or `default` when there is none). An unknown name is `log_error`, a blank line, the generated usage line, exit 1: the shape every arm of the bash dispatcher used."""
    sub = argv[0] if argv else ""
    key = sub or default
    if key is not None and key in arms:
        return arms[key](argv[1:])
    log.error("Unknown %s command: %s" % (verb, sub))
    print()
    print(usage_line(verb, arms, notes))
    return 1


def _entrypoint() -> str:
    return str(root() / "run.sh")


def _with_docker_group(args: list[str]) -> None:
    """`SCRIPT_ENTRYPOINT=run.sh reexec_with_docker_group <args>`. The variable is scoped to the call, as the bash prefix scoped it; on success the process is replaced and never returns."""
    previous = os.environ.get("SCRIPT_ENTRYPOINT")
    os.environ["SCRIPT_ENTRYPOINT"] = _entrypoint()
    try:
        local_common.reexec_with_docker_group(args)
    finally:
        if previous is None:
            os.environ.pop("SCRIPT_ENTRYPOINT", None)
        else:
            os.environ["SCRIPT_ENTRYPOINT"] = previous


# --------------------------------------------------------------------------- help ---------------------------------------------------------------------------

HELP = (
    """Usage: ./run.sh [COMMAND] [OPTIONS]

SERVICE COMMANDS:
  service start [port] [--no-build]  Build and run """
    + WEB_IMAGE_REPO
    + """ (default port: 8080)
  service stop                    Stop service containers
  service status                  Show service status
  service logs [container]        Show logs (web, rustfs, all)

ACCOUNT COMMANDS:
  account dev              Start account dev gateway (API + portal + www on one port)
  account db               Browse the dev database (Drizzle Studio on account.db)
  account test             Run account integration tests (vitest)
  account test e2e [opts]  Run account E2E tests (playwright, with Stripe wiring)
  account stop             Stop account Docker containers
  account reset            Reset .env + database and regenerate
  account seed-demo        Seed a demo partner org end-to-end against the dev gateway (takes <email>)
  account totp [email]     Print the current 2FA code for a dev user (default """
    + DEV_USER_EMAIL
    + """)

ROTATION COMMANDS (private/account/scripts/rotation/):
  rotation init            Bootstrap manifest from current platform state
  rotation list            Show every credential and its current state
  rotation check           Compare manifest to live state (exit 1 on drift)
  rotation rotate <slug>   Mint new credential; old transitions to grace
  rotation deactivate <s>  grace → inactive
  rotation delete <slug>   inactive → deleted (permanent)
  rotation sweep           Run deactivate + delete for everything eligible
  rotation history [<s>]   Show audit history

PROVISION COMMANDS:
  provision start            Provision KVM VMs (bridge + workers)
  provision stop             Destroy all VMs
  provision status           Show VM status

DEVELOPMENT COMMANDS:
  dev                 Start the www (marketing site) development server
  (rdc)               Use ./rdc.sh instead (standalone CLI runner)
  worktree <cmd>      Manage git worktrees (create, switch, prune, list)
  setup [--check]     Prepare this machine: INSTALL the toolchain (node, gcc, Go,
                      gh, jq), set the git identity and credentials, then docker,
                      the devcontainer image, and a browser VS Code for THIS
                      worktree. Idempotent -- a second run installs nothing.
  devbox <cmd>        up | status | url | stop | proxy | remove | shell | exec | doctor | logs

WWW COMMANDS:
  www all [opts]                    Full pipeline for tutorials + team videos

  www tutorials record [name]       Record .cast files inside the bridge VM (auto-provision, change-detected; keeps local ~/.config/rediacc clean)
  www tutorials extract             Sync cast markers to transcripts (preserves text)
  www tutorials scaffold-locales    Sync locale transcripts with English
  www tutorials generate [opts]     Generate TTS audio + timelines (Python venv)
  www tutorials video [name] [--lang <code>] [--jobs N] [--captions-only]  Compile .mp4 from cast+storyboard+timeline+audio
                                     (--jobs N runs N compiles concurrently, default 1; ffmpeg-bound,
                                     safe to raise on a multi-core box -- e.g. --jobs 6 on 20 cores)
                                     (--captions-only recovers scene timing analytically and re-emits
                                     just the vtt/chapters/words.json sidecars, skipping the ffmpeg
                                     re-encode entirely -- use after a --subtitle realignment when the
                                     mp4 itself hasn't changed. Falls back to a full render per-tutorial
                                     if a browser scene's silent-segment cache is cold.)
  www tutorials media [name] [--langs a,b] [--jobs N] [--subtitle] [--force]
                                    Narrate on the GPU and render on the CPU CONCURRENTLY:
                                    each language's videos start rendering as soon as its
                                    narration passes validation, while the next language is
                                    still being narrated. Generates and renders only; never
                                    restores from or uploads to R2.
  www tutorials watch [--jobs N] [--langs a,b] [--poll N] [--once] [--dry-run]
                                    Render each (tutorial, LANGUAGE) PAIR the moment that
                                    pair's narration is final, for narration running in
                                    another shell. Exits once nothing new is ready and no
                                    tutorial_tts.cli is left running. Single instance
                                    (flock on artifacts/tutorial-render-watch/watch.lock);
                                    logs to that same directory. Renders only: never
                                    narrates, never restores from or uploads to R2.
  www tutorials validate            Validate transcripts + audio integrity
  www tutorials all [opts]          Full tutorial pipeline (record -> extract -> generate -> video)


DRILL COMMANDS (scripted walkthroughs; non-zero exit on any failed assertion):
  drill universe      Config isolation, source labels, per-config tokens (headless)
  drill transfer      Config-storage battery vs ./run.sh account dev (headless)
  drill license       Live licensing battery on the ops VMs (declares its VM cost)
  drill backup        Live chunk-store battery: session mint, seed and incremental
                      upload, byte-identical restore, quota refusal (no VMs needed)
  drill <name> --selftest
                      Plant one failing assertion; the run MUST exit non-zero

QUALITY COMMANDS:
  quality lint        Run linting (ESLint + Knip)
  quality format      Check code formatting (Biome)
  quality types       Check TypeScript types
  quality submodules  Check submodule branch alignment
  quality deps        Check for outdated dependencies
  quality actions     Check that the pinned GitHub Actions are current
  quality suppressions  Check that allowlist entries are still needed
  quality dead-bash   Check for dead shell functions and orphaned scripts
  quality audit       Run security audit (npm audit)
  quality shell       Run shellcheck on shell scripts
  quality all         Run all quality checks

FIX COMMANDS:
  fix format          Auto-fix code formatting
  fix lint            Auto-fix linting issues
  fix shell           Auto-fix shell script formatting (shfmt)
  fix all             Auto-fix all issues

MAINTENANCE:
  clean               Clean build artifacts
  help                Show this help message

QUICK START:
  ./run.sh setup          # One-time setup
  ./run.sh dev            # Start www development
  ./rdc.sh --dev subscription login # Run a CLI command against the dev config

REQUIREMENTS:
  Node.js v%(node)s.x (https://nodejs.org/)
  Go (for CLI/renet development)
  Docker (for first-time renet asset extraction)

ENVIRONMENT:
  GITHUB_TOKEN        GitHub personal access token (for ghcr.io auth)
"""
)


def help_text() -> str:
    """The `show_help` text with the pinned Node major filled in."""
    try:
        major = toolchain.node_major()
    except toolchain.PinError:
        major = "?"
    return HELP % {"node": major}


def help_main(argv: list[str]) -> int:
    """`./run.sh help`, `--help`, `-h` and no verb at all."""
    del argv
    sys.stdout.write(help_text())
    return 0


def unknown_main(argv: list[str]) -> int:
    """An unrecognised top-level verb (`argv[0]`): the error, a blank line, the whole help, exit 1."""
    log.error("Unknown command: %s" % argv[0])
    print()
    sys.stdout.write(help_text())
    return 1


# --------------------------------------------------------------------------- service, account, rotation ---------------------------------------------------------------------------


SERVICE_ARMS: dict[str, Arm] = {
    "start": lambda rest: service.main(["start", *rest]),
    "stop": lambda rest: service.main(["stop", *rest]),
    "status": lambda rest: service.main(["status", *rest]),
    "logs": lambda rest: service.main(["logs", *rest]),
}


def service_main(argv: list[str]) -> int:
    return dispatch("service", SERVICE_ARMS, argv)


ACCOUNT_ARMS: dict[str, Arm] = {
    "dev": lambda _rest: account_lifecycle.main(["dev"]),
    "db": lambda rest: account.db(rest),  # noqa: PLW0108 -- late binding, so a substituted `account.db` is the one called
    "test": lambda rest: account_lifecycle.main(["test", *rest]),
    "stop": lambda _rest: account.stop(),
    "reset": lambda _rest: account_lifecycle.main(["reset"]),
    "seed-demo": lambda rest: account_lifecycle.main(["seed-demo", *rest]),
    "totp": lambda rest: account.totp(rest[0] if rest else None),
}


def account_main(argv: list[str]) -> int:
    return dispatch("account", ACCOUNT_ARMS, argv)


def rotation_main(argv: list[str]) -> int:
    return account.rotation(argv)


# --------------------------------------------------------------------------- worktree, drill ---------------------------------------------------------------------------


def worktree_main(argv: list[str]) -> int:
    _flush()
    return importlib.import_module("rediacc_ci.dev.worktree").main(argv)


def _module_arm(module: str) -> Arm:
    """A drill ported to Python: import it now and run its `main` with the drill's own argv."""

    def arm(rest: list[str]) -> int:
        _flush()
        return importlib.import_module(module).main(rest)

    return arm


# The usage line lists the drills in this order, as the bash dispatcher did.
DRILL_ARMS: dict[str, Arm] = {
    "universe": _module_arm(DRILL_MODULES["universe"]),
    "transfer": _module_arm(DRILL_MODULES["transfer"]),
    "license": _module_arm(DRILL_MODULES["license"]),
    "backup": _module_arm(DRILL_MODULES["backup"]),
}


def drill_main(argv: list[str]) -> int:
    sub = argv[0] if argv else ""
    if sub in DRILL_ARMS:
        return DRILL_ARMS[sub](argv[1:])
    log.error("Unknown drill: %s" % sub)
    print()
    print(usage_line("drill", DRILL_ARMS) + " [--selftest]")
    return 1


# --------------------------------------------------------------------------- devbox ---------------------------------------------------------------------------


def _devbox_proxy(box: devbox.Devbox, argv: list[str]) -> int:
    sub = argv[0] if argv else "status"
    if sub == "up":
        return box.invoke("devbox_proxy_ensure")
    if sub == "stop":
        return box.invoke("devbox_proxy_stop")
    if sub == "status":
        if box.invoke("devbox_proxy_running") == 0:
            box.log("info", "Proxy running on :%d" % devbox.DEVBOX_PROXY_PORT)
            return 0
        box.log("warn", "Proxy is not running")
        return 1
    box.log("error", "Unknown devbox proxy command: %s" % sub)
    return 1


def _devbox_exec(box: devbox.Devbox, rest: list[str]) -> int:
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if not rest:
        box.log("error", "devbox exec needs a command: ./run.sh devbox exec -- <cmd>")
        return 1
    return box.invoke("devbox_exec", rest)


# Each arm takes the Devbox and the arguments after the subcommand. `up` forwards its remaining args so --no-rehost reaches devbox_up; `url` forwards its suffix to the other routes (`url term`, `url account`, `url db`).
DEVBOX_ARMS: dict[str, Callable[[devbox.Devbox, list[str]], int]] = {
    "up": lambda box, rest: box.invoke("devbox_up", ["false", rest[0] if rest else ""]),
    "status": lambda box, _rest: box.invoke("devbox_status"),
    "url": lambda box, rest: box.invoke("devbox_url", [rest[0] if rest else ""]),
    "stop": lambda box, _rest: box.invoke("devbox_stop"),
    "proxy": _devbox_proxy,
    "remove": lambda box, _rest: box.invoke("devbox_remove"),
    "shell": lambda box, _rest: box.invoke("devbox_shell"),
    "exec": _devbox_exec,
    "doctor": lambda box, _rest: box.invoke("devbox_doctor"),
    "logs": lambda box, rest: box.invoke("devbox_logs", rest),
}
DEVBOX_NOTES = {"url": " [term|account|db]"}


def devbox_main(argv: list[str]) -> int:
    _with_docker_group(["devbox", *argv])
    box = devbox.Devbox()
    sub = argv[0] if argv else "status"
    if sub in DEVBOX_ARMS:
        return DEVBOX_ARMS[sub](box, argv[1:])
    box.log("error", "Unknown devbox command: %s" % sub)
    box.log("info", usage_line("devbox", DEVBOX_ARMS, DEVBOX_NOTES))
    return 1


# --------------------------------------------------------------------------- quality ---------------------------------------------------------------------------


def quality_lint() -> int:
    if not _node_ok():
        return 1
    log.step("Running lint checks")
    rc = _npm("run", "lint", "--", "--max-warnings", "0")
    return rc if rc != 0 else _npm("run", "lint:unused")


def quality_format() -> int:
    if not _node_ok():
        return 1
    log.step("Checking code formatting")
    return _npm("run", "check:format")


def quality_types() -> int:
    if not _node_ok():
        return 1
    log.step("Checking TypeScript types")
    return _npm("run", "typecheck")


def quality_deps() -> int:
    if not _node_ok():
        return 1
    return _tsx("scripts/gates/check-deps.ts")


def quality_ts_gate(name: str) -> int:
    script, announcement = QUALITY_TS_GATES[name]
    if not _node_ok():
        return 1
    log.step(announcement)
    return _tsx(script)


def quality_audit() -> int:
    if not _node_ok():
        return 1
    return _run([sys.executable, "-m", "rediacc_ci.security.audit"])


def quality_shell() -> int:
    rc = _run([sys.executable, "-m", "rediacc_ci.security.shellcheck"])
    return rc if rc != 0 else _run([sys.executable, "-m", "rediacc_ci.security.shfmt"])


def quality_submodules() -> int:
    log.step("Checking submodule branch alignment")
    # Lazy: the gate's imports are not needed by any other verb.
    from rediacc_ci.quality import submodule_branches  # noqa: PLC0415

    _flush()
    return submodule_branches.main([])


def quality_all() -> int:
    if not _node_ok():
        return 1
    log.step("Running all quality checks")
    rc = _npm("run", "quality")
    if rc != 0:
        return rc
    # A shell gate that cannot run is a failure, never a skipped step: on a host without the pinned shfmt this used to report green having run no shell gate at all.
    verdict = toolchain.check("shfmt")
    if verdict.ok:
        return quality_shell()
    log.error("shell gates cannot run here:")
    for message in verdict.messages:
        print("    %s" % message, file=sys.stderr)
    log.info("Run them in the devbox instead: ./run.sh devbox exec -- ./run.sh quality shell")
    log.info("Or see what every lane has: .ci/scripts/lib/toolchain.sh --report")
    return 1


def _ts_gate_arm(name: str) -> Arm:
    return lambda _rest: quality_ts_gate(name)


QUALITY_ARMS: dict[str, Arm] = {
    "lint": lambda _rest: quality_lint(),
    "format": lambda _rest: quality_format(),
    "types": lambda _rest: quality_types(),
    "submodules": lambda _rest: quality_submodules(),
    "deps": lambda _rest: quality_deps(),
    **{name: _ts_gate_arm(name) for name in QUALITY_TS_GATES},
    "audit": lambda _rest: quality_audit(),
    "shell": lambda _rest: quality_shell(),
    "all": lambda _rest: quality_all(),
}


def quality_main(argv: list[str]) -> int:
    # Only GATE verbs route into the devbox lane: the container's toolchain matches CI's and the host's generally does not. The lane probe talks to docker, so the group is applied first, and the answer is asked BEFORE anything runs so a gate that failed in the devbox never falls through to the host.
    _with_docker_group(["quality", *argv])
    route = local_common.gate_lane_should_route()
    if route == 0:
        return local_common.gate_lane_run(["quality", *argv])
    if route == 2:
        return 2
    return dispatch("quality", QUALITY_ARMS, argv, default="all")


# --------------------------------------------------------------------------- fix ---------------------------------------------------------------------------


def fix_shell() -> int:
    """`shfmt -i 4 -ci -w` over exactly the files `security.shfmt` checks, with the same pinned binary."""
    log.step("Auto-fixing shell script formatting")
    binary, messages = toolchain.acquire("shfmt")
    for line in messages:
        print(line, file=sys.stderr)
    if binary is None:
        log.error("shfmt is unusable, so formatting would not match the gate")
        log.info("Every lane's toolchain: .ci/scripts/lib/toolchain.sh --report")
        return 1
    base = root()
    targets: list[str] = []
    for scope in (".ci", ".claude", *shfmt.OPTIONAL_SCOPES):
        directory = base / scope
        if directory.is_dir():
            targets.extend(shfmt.shell_files(directory))
    targets.append(str(base / "run.sh"))
    write_flags = [flag if flag != "-d" else "-w" for flag in shfmt.SHFMT_OPTS]
    rc = _run([binary, *write_flags, *targets])
    if rc == 0:
        log.info("Shell scripts formatted")
    return rc


def _fix_npm(script: str, announcement: str) -> int:
    if not _node_ok():
        return 1
    log.step(announcement)
    return _npm("run", script)


FIX_ARMS: dict[str, Arm] = {
    "format": lambda _rest: _fix_npm("fix:format", "Auto-fixing code formatting"),
    "lint": lambda _rest: _fix_npm("fix:lint", "Auto-fixing linting issues"),
    "shell": lambda _rest: fix_shell(),
    "all": lambda _rest: _fix_npm("fix:all", "Auto-fixing all issues"),
}


def fix_main(argv: list[str]) -> int:
    return dispatch("fix", FIX_ARMS, argv, default="all")


# --------------------------------------------------------------------------- clean ---------------------------------------------------------------------------


def clean_main(argv: list[str]) -> int:
    del argv
    log.step("Cleaning build artifacts")
    base = root()
    victims = [base / name for name in CLEAN_PATHS]
    victims.extend(sorted(base.glob(CLEAN_GLOB)))
    for victim in victims:
        if victim.is_symlink() or victim.is_file():
            victim.unlink()
        elif victim.is_dir():
            shutil.rmtree(victim, ignore_errors=True)
    log.info("Build artifacts cleaned")
    return 0


# --------------------------------------------------------------------------- introspection ---------------------------------------------------------------------------

# The verbs that own a second level, and the table that dispatches it. `worktree`, `rotation` and `drill`'s scripts own their own subcommands.
SUBCOMMAND_TABLES: dict[str, Mapping[str, object]] = {
    "service": SERVICE_ARMS,
    "account": ACCOUNT_ARMS,
    "devbox": DEVBOX_ARMS,
    "drill": DRILL_ARMS,
    "quality": QUALITY_ARMS,
    "fix": FIX_ARMS,
}


def arms(table: tuple | None = None) -> list[str]:
    """What this package dispatches, as sorted `TOP <verb>` and `SUB <verb>/<sub>` lines: every row of the VERBS table, then every key of the tables above. The gate test compares this inventory with the one `help` documents."""
    # Lazy: `__main__` imports nothing at module scope, and its handlers import this module.
    from rediacc_ci import __main__ as entry  # noqa: PLC0415

    lines = {"TOP " + name for name in entry.names(table)}
    for verb, arm_table in SUBCOMMAND_TABLES.items():
        lines.update("SUB %s/%s" % (verb, sub) for sub in arm_table)
    return sorted(lines)


if __name__ == "__main__":
    if sys.argv[1:] == ["arms"]:
        print("\n".join(arms()))
    elif sys.argv[1:] == ["help"]:
        sys.stdout.write(help_text())
    else:
        print("usage: python3 -m rediacc_ci.core.run_verbs arms|help", file=sys.stderr)
        sys.exit(2)
