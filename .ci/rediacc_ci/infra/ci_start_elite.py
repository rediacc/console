"""Port of `.ci/scripts/infra/ci-start-elite.sh` (120 lines).

Starts the Elite on-premise Docker Compose stack through the operator entry point (`private/elite/run.sh up`), writes the `.env` that entry point reads, waits for the web health endpoint, and prints the surviving containers.

LIVE CALLERS, one repointed at this module by W7P4-b and one still on the twin:
  * `.github/workflows/ci.yml` -- `run: PYTHONPATH=.ci python3 -m rediacc_ci.infra.ci_start_elite`,
    licensed by `.ci/shadow/w7p4b-ci-start-elite.observations.jsonl` (seven rows,
    `--assert --k 5` green). The recording fixture supplies `private/elite/run.sh`
    itself: the submodule is not part of a scratch tree, and what the ledger attests
    to is this script's contract WITH that entry point -- the argv it passes and the
    `.env` it leaves for it to read, both of which the stub echoes back.
  * `.ci/breakpoint/scripts/start-origin.sh:88,92,111` -- the breakpoint
    `--services onprem` hook, which reads the twin's path from a variable. Left on
    the bash twin, which stays on disk.

WHAT MOVES AND WHAT DOES NOT. The orchestration moves to Python: the `.env` write, the poll loop, the diagnostics, the exit codes.

  * THE CI ENVIRONMENT IS `rediacc_ci.infra.ci_env.apply()`, called in-process
    (W7P5-c). Until then this module ran the sourced-only `ci-env.sh` under a
    real bash and read its exported set back through `env -0`; that twin is
    deleted, its answers are frozen in `goldens/twins/infra.ci-env.jsonl`, and
    the cutover itself is licensed by
    `.ci/shadow/w7p5c-ci-start-elite-cutover.observations.jsonl` (old side: this
    module as it was, sourcing the bash; new side: this module).
  * `private/elite/run.sh` is a submodule's operator entry point and is invoked
    as a subprocess, argument for argument.

PORT NOTES, each driven before it was written down.

ONLY THE EXPORTED SET IS MERGED BACK, which is what the `source` delivered. `ci_env.configure()` returns exactly the names the sourced bash left exported (its `WORKFLOW_*`, `KEYS` and `PERSISTED_ENV` were plain shell variables and never reached the caller). The four names the twin interpolates into `.env` (`DOCKER_REGISTRY`, `TAG`, `WEB_TAG`, `SYSTEM_DOMAIN`) are all among them.

ONE NAME FAMILY NO LONGER ARRIVES, ON PURPOSE: `WK_*`. The sourced bash ran `well_known_load`, which exported the well-known registry into the caller as a side effect, and `env -0` carried it into this process and on to `./run.sh up`. Nothing on that path reads a `WK_*` name (`grep -rl WK_ private/elite .ci/docker/ci` finds none), and the port reads the registry through `rediacc_ci.well_known` instead. The cutover ledger compares the children's environment with `WK_*` filtered on both sides for that reason, and every other name is compared.

A FAILING CI ENVIRONMENT KILLS THE SCRIPT WITH THE TOOL'S OWN STATUS. ci-env.sh ran `set -e`, so a failing `node` or `jq` inside it exited the whole script with that status; `ci_env.ToolFailedError` carries the same code and `main` returns it unchanged. The one addition is a `ci_env: <tool> exited <n>` line on stderr, because a missing binary is 127 with no message from Python where bash printed `command not found`.

THE `.env` REDIRECT IS THE FIRST THING THAT CAN DIE ON A HOST WITHOUT THE
SUBMODULE. `{ ... } >"$ELITE_DIR/.env"` (:36-45) fails when `private/elite` is
absent, and under `set -e` bash exits 1 after printing its own diagnostic: `ci-start-elite.sh: line 45: <path>/.env: No such file or directory`. Driven. This port exits 1 with a message naming the same path, and DOES NOT forge bash's `line 45` prefix -- a hard-coded line number in a port goes stale the first time the twin gains a comment. `test_infra_ci_start_elite.py` pins this as
a named, deliberate divergence rather than letting it pass unnoticed.

`./run.sh logs web` FAILING ON THE FAILURE PATH SUPPRESSES THE `exit 1`. The recovery block (:106-112) is the command following the final `||`, so `set -e` is NOT relaxed inside it: if `./run.sh logs web` fails, bash exits with THAT status and :111's `exit 1` never runs. Driven:
`bash -c 'set -e; f(){ return 1; }; f || { ./nope.sh; exit 1; }'` exits 127.
Reproduced exactly -- `main` returns the logs command's rc when it is non-zero, 1 otherwise.

THE HEALTH POLL IS A BUDGET, NOT A DEADLINE, on both sides. The twin adds `interval` to `elapsed` after each sleep and re-tests `elapsed < timeout`, so a
180s/2s budget performs 90 probes and the last one starts at t=178s; the wall
clock the probes themselves consume is not counted. Reproduced with the same arithmetic rather than with a monotonic deadline, because a deadline would change the probe COUNT on a slow host and the probe count is what a differential against a scripted fake `curl` can see.

`\t` INSIDE THE TWIN'S DOUBLE QUOTES IS A LITERAL BACKSLASH-T, NOT A TAB, and this port had it wrong until the differential's argv record caught it. Bash does not process `\t` inside `"..."`, so `docker ps --format "table
{{.Names}}\t{{.Status}}\t{{.Ports}}"` passes docker a format string containing
two backslash-t sequences, which docker's own `table` directive then expands. A Python `"\t"` would have handed docker a real tab and quietly changed the column layout of a diagnostic nobody reads closely. The argument is a raw string here for that reason.

`curl` MISSING IS A FAILED PROBE, NOT A CRASH. The twin never checks for the binary; bash turns a missing one into 127 which the `if` treats as "not ready". `subprocess.run` raises `FileNotFoundError` for that case, so it is caught and folded into the same "not ready" arm.

Exit: 0 when the web service came up; the twin's own non-zero status otherwise.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

from rediacc_ci.infra import ci_env

# The twin's `local timeout=180` / `local interval=2` (:85-87). Named rather than
# inlined so a test can assert the real file still carries the values the twin does. The differential does NOT shrink them -- it nulls the `sleep` call instead, so both sides keep the real arithmetic and still perform all 90 probes.
TIMEOUT_SECONDS = 180
INTERVAL_SECONDS = 2


def _console_root() -> pathlib.Path:
    """The twin's `SCRIPT_DIR/../../..` from `.ci/scripts/infra/`.

    This module sits one directory deeper (`.ci/rediacc_ci/infra/`), so the same repository root is `parents[3]` here where the twin's is `parents[2]` of its own directory. `rediacc_ci.paths.repo_root()` is deliberately not used: it honours $REDIACC_CI_ROOT and the twin has no such override, so a fixture pointing one at a tree and not the other would diverge silently.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def configure_ci_env(console_root: pathlib.Path) -> tuple[int, dict[str, str]]:
    """`ci_env.apply()` against this tree: `(rc, exported environment)`.

    The `::add-mask::` directives and the three summary lines go to this process's stdout, in the order the sourced bash printed them, and the `.env` under `.ci/docker/ci` and the `$GITHUB_ENV` append happen exactly as they did. `console_root` is passed explicitly so the writes land in the tree this module sits in, never in whichever checkout `rediacc_ci` was imported from.
    """
    try:
        config = ci_env.apply(dict(os.environ), console_root)
    except ci_env.ToolFailedError as failed:
        print("ci_env: %s" % failed, file=sys.stderr, flush=True)
        return failed.code, {}
    return 0, dict(config.exported)


def env_file_body(env: dict[str, str]) -> str:
    """The exact 8 lines the twin's `{ ... } >"$ELITE_DIR/.env"` block writes.

    Unset names expand to the empty string: the twin runs `set -e` only, never
    `set -u`, so `${DOCKER_REGISTRY}` on a host where the CI environment somehow did not
    export it produces `DOCKER_REGISTRY=` rather than an error.
    """
    return "".join(
        "%s\n" % line
        for line in (
            "# Auto-generated by ci-start-elite.sh -- do not edit",
            "DOCKER_REGISTRY=%s" % env.get("DOCKER_REGISTRY", ""),
            "TAG=%s" % env.get("TAG", ""),
            "WEB_TAG=%s" % env.get("WEB_TAG", ""),
            "SYSTEM_DOMAIN=%s" % env.get("SYSTEM_DOMAIN", ""),
            "HTTP_PORT=%s" % env.get("HTTP_PORT", ""),
            "HTTPS_PORT=%s" % env.get("HTTPS_PORT", ""),
            "ENABLE_HTTPS=%s" % env.get("ENABLE_HTTPS", ""),
        )
    )


def _load_diagnostic() -> str:
    """The twin's `:102` load line, with both of its `|| echo` fallbacks."""
    try:
        fields = pathlib.Path("/proc/loadavg").read_text(encoding="utf-8").split(" ")
        load = " ".join(fields[:3])
    except OSError:
        load = "unavailable"
    try:
        nproc = subprocess.run(["nproc"], check=False, capture_output=True, text=True)
        cores = nproc.stdout.strip() if nproc.returncode == 0 else "unknown"
    except FileNotFoundError:
        cores = "unknown"
    return "  load average (1m 5m 15m): %s, cores: %s" % (load, cores)


def _probe_web() -> bool:
    """`curl -sf http://localhost/health &>/dev/null`, both streams discarded."""
    try:
        return (
            subprocess.run(
                ["curl", "-sf", "http://localhost/health"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
    except FileNotFoundError:
        return False


def wait_for_web() -> bool:
    """The twin's `wait_for_web` (:84-104). True on ready, False on timeout."""
    elapsed = 0
    print("  Waiting for Web (nginx)...", flush=True)
    while elapsed < TIMEOUT_SECONDS:
        if _probe_web():
            print("  Web is ready", flush=True)
            return True
        time.sleep(INTERVAL_SECONDS)
        elapsed += INTERVAL_SECONDS
    print("  Web failed to start within %ds" % TIMEOUT_SECONDS, flush=True)
    print(_load_diagnostic(), flush=True)
    return False


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments
    console_root = _console_root()
    elite_dir = console_root / "private" / "elite"

    print("Starting Rediacc Elite CI services...", flush=True)

    rc, env = configure_ci_env(console_root)
    if rc != 0:
        return rc
    os.environ.update(env)

    # The twin's :28-30, AFTER the CI environment, so its own
    # `ENABLE_HTTPS=${ENABLE_HTTPS:-false}` heredoc line has already been resolved
    # with ENABLE_HTTPS unset.
    os.environ["ENABLE_HTTPS"] = "false"
    os.environ["HTTP_PORT"] = "80"
    os.environ["HTTPS_PORT"] = "443"

    print("Writing .env to %s..." % elite_dir, flush=True)
    try:
        (elite_dir / ".env").write_text(env_file_body(dict(os.environ)), encoding="utf-8")
    except OSError as exc:
        # The twin dies here too, rc=1, with bash's own diagnostic. See the
        # module docstring: the line-number prefix is not forged.
        print("%s/.env: %s" % (elite_dir, exc.strerror), file=sys.stderr, flush=True)
        return 1

    print("Starting Elite services via ./run.sh up (the operator entry point)...", flush=True)

    up = subprocess.run(["./run.sh", "up"], check=False, cwd=str(elite_dir))
    if up.returncode != 0:
        # `set -e` (:9) with no guard on :68.
        return up.returncode

    print("Waiting for Elite web service to be ready...", flush=True)

    if not wait_for_web():
        print("Elite startup failed: Web", flush=True)
        logs = subprocess.run(["./run.sh", "logs", "web"], check=False, cwd=str(elite_dir))
        # THE `exit 1` ON :111 IS UNREACHABLE WHEN THIS COMMAND FAILS. See the module docstring; `set -e` is not relaxed inside the `||` group.
        return logs.returncode if logs.returncode != 0 else 1

    print(flush=True)  # the twin's bare `echo ""`
    print("All Elite services are ready!", flush=True)
    print(flush=True)  # the twin's bare `echo ""`
    print("Running containers:", flush=True)

    # `docker ps ... | grep -E "(NAME|rediacc)" || true`. The pipeline is reproduced with a real `grep` rather than with a Python filter so the differential's argv record shows the same two processes the twin spawns, and so ugrep-vs-GNU-grep differences (this repo runs ugrep 7.5.0) land on both sides identically instead of on the bash side only.
    ps: subprocess.Popen[bytes] | None
    try:
        ps = subprocess.Popen(
            ["docker", "ps", "--format", r"table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
            stdout=subprocess.PIPE,
        )
    except FileNotFoundError:
        # bash still runs the RIGHT-HAND side of the pipe when the left-hand command does not exist: grep reads EOF, exits 1, and `|| true` eats it. Returning early here would drop a process the twin spawns.
        ps = None
    subprocess.run(
        ["grep", "-E", "(NAME|rediacc)"],
        check=False,
        stdin=ps.stdout if ps is not None else subprocess.DEVNULL,
    )
    if ps is not None:
        if ps.stdout is not None:
            ps.stdout.close()
        ps.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
