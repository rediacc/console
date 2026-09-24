"""The rediacc/web + RustFS local stack, ported from `.ci/lib/service.sh`.

PORTED FROM `.ci/lib/service.sh` (225 lines). The twin still exists and is untouched by this file, and it has exactly ONE sourcer: `.ci/legacy/run-legacy.sh:48`, which is the pre-split body of the repo-root `run.sh`. Re-measured 2026-09-09.

--------------------------------------------------------------------------
THREE DEFECTS THE PORT FOUND, ALL REPRODUCED HERE ON PURPOSE
--------------------------------------------------------------------------
A port that quietly improved any of these would disagree with the live twin on real input, so each is reproduced, each is pinned by a case in `.ci/rediacc_ci/tests/test_core_service.py`, and each is named here so the reader knows it is a decision rather than an oversight. NONE of them is fixed in the bash, because the bash is not this box's to edit.

  1. `service_status` ABORTS SILENTLY, MID-OUTPUT, ON A STATE FILE WITH NO
     `port=` LINE. Measured 2026-09-09. `port=$(grep "^port=" "$STATE" | cut -d=
     -f2)` is a BARE ASSIGNMENT, so it takes the pipeline's exit status; grep
     matching nothing exits 1; `common.sh` has set `pipefail` and `errexit`; the
     function dies there. The user sees the two container lines and then
     NOTHING: no health check, no trailing blank line, no message. The function
     returns 1 and, because errexit is still armed in the sourcing script, takes
     `run-legacy.sh` down with it. `started=` has the identical shape one line
     later. This is the class the worklist already recorded for the gate tests
     ("a bare `VAR=$(... grep ...)` ... grep counting ZERO exits 1"), reached
     here through a library rather than a test.

  2. COLOUR ON STDOUT IS UNCONDITIONAL WHILE COLOUR ON STDERR IS TTY-GATED, IN
     THE SAME FUNCTION. `service_status` writes its container and health lines
     with `${COLOR_GREEN}` / `${COLOR_RED}` from `.ci/config/constants.sh:295-297`,
     which are plain `readonly` assignments with no tty test and no `CI` test at
     all. Its `log_info` lines come from `common.sh`, which empties its colours
     when stderr is not a tty. So piping `service status` into a file gives raw
     ANSI in the DATA stream and clean text in the LOG stream, which is the
     wrong way round. Measured: `^[[0;31mx^[[0m rediacc-service-web (not
     running)` on a pipe.

  3. `check_docker` IS CALLED BY FOUR FUNCTIONS HERE AND DEFINED BY NONE OF
     THEM. It lives in `.ci/legacy/run-legacy.sh`, the file that SOURCES this
     one, and only late binding makes that work. `source .ci/lib/service.sh`
     followed by `service_status` in any other shell dies with `check_docker:
     command not found`. The port defines it, because a module cannot borrow a
     function from its importer, and because the definition is two `command -v`
     probes that belong with the code that needs them.

--------------------------------------------------------------------------
WHAT IS AND IS NOT DIFFERENTIALLY PROVED
--------------------------------------------------------------------------
PROVED, against the live twin, on real `docker`: `service_status` in every shape its state file can take, and `service_logs` refusing an unknown service. Those run without a stack up, which is what makes them cheap enough to record five times.

PROVED BY A STUB-FARM TRANSCRIPT, the lifecycle half (W7P5-b, 2026-09-24): `service_start`, `service_health`, `service_stop` and `service_logs`'s attach. The first slice refused them because driving them for real builds the web image and leaves containers behind. The technique that closes the gap is to run BOTH sides with a directory of stubs first on PATH (`docker`, `curl`, `sleep`, `date`, `ss`, `openssl`), each of which appends its argv to one transcript
and answers from a scripted table. The comparison is then rc, stdout, stderr AND the ordered transcript of every external call, so the port must make the same calls with the same arguments in the same order, which is exactly the claim a lifecycle port makes. `.ci/rediacc_ci/tests/test_core_service.py` drives the live twin that way on every run.

Three consequences of that, stated so a reader does not mistake them for accidents:
  * the port calls `sleep` and `curl` as PROGRAMS rather than `time.sleep` and a
    socket, because the twin does and a transcript that differed there would say nothing about the port;
  * `docker ps -a` runs once PER CONTAINER in `service_stop`, as the twin's loop does, where
    `service_status` above batches it into one call. Status predates the transcript technique and its differential compares output only; stop's is compared call for call;
  * `.ci/docker/service/env.sh` is SOURCED by the twin and cannot be sourced by Python. `source_env_sh` runs it in bash and imports the environment it exports, so its log lines, the `.env` it writes and the variables it sets all land where the twin's do. That file is not one of W7P5-b's libraries and stays bash.

FOUR MORE TWIN BEHAVIOURS, reproduced and pinned:
  4. A FAILING `docker compose build` OR `up -d` ENDS THE PROCESS, it does not return. Both run bare under the errexit every sourcer arms, so the twin never reaches its own "Service failed to become healthy" branch for them. The port raises `SystemExit` with the same status.
  5. `service_stop` SWALLOWS `compose down`'s stderr but NOT its stdout, and the same for `docker stop` / `docker rm`, which print the container name on stdout. So `./run.sh service stop` prints each force-removed container's name twice on stdout, unlabelled.
  6. `service_health` prints its `[DEBUG]` progress only at elapsed multiples of 10, and with a 2-second interval over a 90-second budget that is every fifth probe; the last line it could print is `Waiting... (90s / 90s)`, AFTER which the loop ends and the timeout is reported.
  7. An explicit port argument is taken VERBATIM, never checked for being free or numeric: `service_start abc` exports `SERVICE_HTTP_PORT=abc` and the health probe then polls `http://localhost:abc/health` for 90 seconds.

--------------------------------------------------------------------------
WHY THE LOGGER IS `rediacc_ci.log` AND THE COLOURS ARE NOT
--------------------------------------------------------------------------
`log_info` / `log_error` / `log_step` / `log_debug` here are `common.sh`'s, and `rediacc_ci.log` is already the byte-exact port of those four, tty gating included. Re-deriving them would be the fifth copy of a thing that has one. The `COLOR_*` constants are the OTHER family -- `constants.sh`'s ungated pair -- and they are duplicated below precisely because they are not the same
decision. Collapsing them into `log`'s would fix defect 2 by accident, in a port.
"""

import contextlib
import os
import shutil
import subprocess
import sys
import time

from rediacc_ci import log, paths
from rediacc_ci.core import ports

# `.ci/config/constants.sh:295-297`, verbatim. UNCONDITIONAL, with no tty test: see defect 2 in the module docstring. Named `COLOR_` rather than reusing `log.RED` so a reader grepping either file finds the same spelling.
COLOR_RED = "\033[0;31m"
COLOR_GREEN = "\033[0;32m"
COLOR_NC = "\033[0m"

# `docker compose -p <this>`. The project name is what makes `service_stop` able to tear down a stack it did not start in this process.
PROJECT = "rediacc-service"

# The two containers `service_status` reports on, in order. `service_stop`'s force-remove list is longer (it includes the two init containers) and is kept separate below for the same reason the twin keeps them separate: one is a status surface and the other is a cleanup surface.
STATUS_CONTAINERS = ("rediacc-service-web", "rediacc-service-rustfs")
STOP_CONTAINERS = (
    "rediacc-service-web",
    "rediacc-service-rustfs",
    "rediacc-service-rustfs-init",
    "rediacc-service-rustfs-volume-init",
)

DEFAULT_PORT = 8080
# `find_preferred_port 8080 8081 8199` in the twin: prefer 8080, else scan.
PREFERRED_PORT = 8080
SCAN_LOW = 8081
SCAN_HIGH = 8199

HEALTH_TIMEOUT_S = 90
HEALTH_INTERVAL_S = 2

VALID_LOG_SERVICES = ("web", "rustfs", "all")

USAGE = """service -- `.ci/lib/service.sh`, every function.

  python3 -m rediacc_ci.core.service start [port] [--no-build]
  python3 -m rediacc_ci.core.service stop
  python3 -m rediacc_ci.core.service status
  python3 -m rediacc_ci.core.service health
  python3 -m rediacc_ci.core.service logs [web|rustfs|all]

Each verb is the twin's function of the same name, byte for byte, colour included.
`logs` attaches (`-f`) exactly as the twin does; an unknown service is refused.
"""


class StatusAbortedError(Exception):
    """`service_status` died where the twin's errexit kills it. See defect 1.

    An exception rather than a return code because the twin does not RETURN there -- `set -e` unwinds it, and everything after the failing line, health check included, never runs. Modelling that as a code would let a caller print the rest.
    """


def state_path(root: str | None = None) -> str:
    """`$SERVICE_STATE_FILE` -- `<CONSOLE_ROOT_DIR>/.service-state`."""
    if root is None:
        root = os.environ.get("CONSOLE_ROOT_DIR", "")
    if not root:
        root = str(paths.repo_root())
    return os.path.join(root, ".service-state")


def grep_cut(text: str, prefix: str) -> str:
    """`grep "^<prefix>" | cut -d= -f2`, raising where the pipeline exits 1.

    THE RAISE IS THE PORT OF `pipefail` + `errexit`, not an editorial choice.
    Zero matches is grep's exit 1, and the twin dies on it. `cut -d= -f2` takes
    the SECOND field only, so a value containing `=` is truncated in both
    implementations; that is preserved rather than fixed for the same reason. On several matches grep emits several lines and `cut` several fields, and the twin then assigns the whole multi-line string -- also preserved.
    """
    hits = [line for line in text.splitlines() if line.startswith(prefix)]
    if not hits:
        raise StatusAbortedError(
            '`grep "^%s" %s` matched nothing, so the twin\'s bare assignment took '
            "grep's exit 1 through pipefail into errexit and service_status stopped "
            "here, silently." % (prefix, ".service-state")
        )
    return "\n".join(line.split("=")[1] if "=" in line else "" for line in hits)


def uptime_line(seconds: int) -> str:
    """`Uptime: HH:MM:SS` from a second count. `printf '%02d:%02d:%02d'`.

    NOT `datetime.timedelta`, which prints `1:02:05` for the same input and rolls over into days past 24 hours. The twin's arithmetic is
    `h=$((u/3600)) m=$((u%3600/60)) s=$((u%60))`, so 25 hours prints as `25:00:00`
    and stays on one field. A negative count (a state file written by a machine whose clock later moved back) formats with a minus sign in both languages, which is ugly and is what the twin does.
    """
    return "Uptime: %02d:%02d:%02d" % (seconds // 3600, seconds % 3600 // 60, seconds % 60)


def parse_start_args(args: list[str]) -> tuple[str, bool]:
    """`service_start`'s loop: (port, skip_build). LAST positional wins.

    The twin's `for arg in "$@"; do case ... *) port="$arg" ;; esac done` has no
    break, so `service_start 9000 9100` ends with 9100 and no complaint. Kept, and stated, because "the last one wins" and "the first one wins" are both plausible readings of a shell loop and only one of them is this file's.
    """
    port = ""
    skip_build = False
    for arg in args:
        if arg == "--no-build":
            skip_build = True
        else:
            port = arg
    return port, skip_build


def docker_available() -> tuple[bool, list[str]]:
    """`check_docker`, as `.ci/legacy/run-legacy.sh` defines it. See defect 3.

    Returns (ok, lines-to-log). The twin `exit 1`s; returning lets the caller decide, and the two call shapes are proved to agree in the tests rather than assumed.
    """
    if shutil.which("docker") is None:
        return False, [
            "Docker is not installed",
            "Install Docker from: https://docs.docker.com/get-docker/",
        ]
    probe = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        return False, ["Docker is not running", "Start Docker Desktop or Docker daemon"]
    return True, []


def check_docker() -> None:
    """`check_docker`'s exact behaviour: two log lines then `exit 1`."""
    ok, lines = docker_available()
    if ok:
        return
    log.error(lines[0])
    log.info(lines[1])
    sys.exit(1)


def running_containers() -> set[str]:
    """`docker ps --format "{{.Names}}"`, as a set, in one call.

    NOT what `service_status` uses any more. The twin runs one `docker ps` PER CONTAINER, and since the lifecycle half is compared call for call against a stub transcript, status makes the same calls too (`_container_listed`). This batched form stays as the cheap probe `test_docker_is_actually_available_here` uses to prove a real daemon answers.
    """
    probe = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {line for line in probe.stdout.splitlines() if line}


def inspect(container: str, template: str, default: str | None = None) -> str:
    """`docker inspect -f <tpl> <c>`, as the twin's two assignments spell it.

    `default is None` is `status=$(docker inspect ...)`: stderr passes through and a failure is the twin's errexit death. Otherwise it is `health=$(docker inspect ... 2>/dev/null || echo "N/A")`: stderr is swallowed, and on failure the value is whatever docker DID print followed by `N/A`, because `||` appends to the substitution rather than replacing it. `$(...)` strips trailing newlines only, never leading or inner whitespace.
    """
    _flush()
    probe = subprocess.run(
        ["docker", "inspect", "-f", template, container],
        stdout=subprocess.PIPE,
        stderr=None if default is None else subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        if default is None:
            raise StatusAbortedError("docker inspect %s failed" % container)
        return (probe.stdout + default + "\n").rstrip("\n")
    return probe.stdout.rstrip("\n")


def health_ok(port: int | str, timeout: float = 5) -> bool:
    """`curl -sf "http://localhost:<port>/health" &>/dev/null`.

    `curl` AND NOT `urllib`, deliberately. `-f` makes a 4xx a non-zero exit, `-s` silences the progress meter, and both streams go to /dev/null; matching that with urllib means matching curl's redirect policy, its proxy environment handling and its idea of a connection failure. The twin's behaviour IS curl's behaviour, so the port runs curl.
    """
    if shutil.which("curl") is None:
        raise StatusAbortedError(
            "curl is not on PATH, and `service_status` decides its health verdict "
            "with `curl -sf`. Without it this port would print FAILED for a healthy "
            "service, which is a wrong answer dressed as a measurement."
        )
    probe = subprocess.run(
        ["curl", "-sf", "http://localhost:%s/health" % port],
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    return probe.returncode == 0


def service_status(*, root: str | None = None, now: int | None = None, out=None) -> int:
    """`service_status`. Returns 0, or raises `StatusAbortedError` where the twin dies.

    `now` is injectable ONLY so the uptime line can be asserted exactly; the default is the wall clock, which is what the twin's `date +%s` reads.
    """
    stream = sys.stdout if out is None else out
    log.info("Service Status")
    log.info("==============")
    print(file=stream)

    for container in STATUS_CONTAINERS:
        if _container_listed(container, all_states=False):
            status = inspect(container, "{{.State.Status}}")
            health = inspect(container, "{{.State.Health.Status}}", default="N/A")
            print(
                "%s+%s %s (status: %s, health: %s)"
                % (COLOR_GREEN, COLOR_NC, container, status, health),
                file=stream,
            )
        else:
            print(
                "%sx%s %s (not running)" % (COLOR_RED, COLOR_NC, container),
                file=stream,
            )

    print(file=stream)

    port: str = str(DEFAULT_PORT)
    path = state_path(root)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        port = grep_cut(body, "port=") or str(DEFAULT_PORT)
        started = grep_cut(body, "started=")
        if started:
            moment = int(time.time()) if now is None else now
            print(uptime_line(moment - int(started)), file=stream)

    if health_ok(port):
        print(
            "%s+%s Health check: PASSED (http://localhost:%s)" % (COLOR_GREEN, COLOR_NC, port),
            file=stream,
        )
    else:
        print("%sx%s Health check: FAILED" % (COLOR_RED, COLOR_NC), file=stream)
    print(file=stream)
    return 0


def service_logs_target(service: str) -> tuple[str, list[str]] | None:
    """`service_logs`'s case arms, WITHOUT attaching. None means unknown.

    Split out from the attach because a differential cannot compare two `-f` streams that never end, and because the dispatch is the part with a bug surface: `all` and `""` share an arm, so `service_logs ""` follows every container rather than refusing.
    """
    if service == "web":
        return "docker", ["docker", "logs", "-f", "rediacc-service-web"]
    if service == "rustfs":
        return "docker", ["docker", "logs", "-f", "rediacc-service-rustfs"]
    if service in ("all", ""):
        return "compose", ["logs", "-f"]
    return None


def service_logs(service: str = "all", *, attach: bool = True) -> int:
    """`service_logs`. Unknown service: two log lines and 1, as the twin does."""
    target = service_logs_target(service)
    if target is None:
        log.error("Unknown service: %s" % service)
        log.info("Valid services: web, rustfs, all")
        return 1
    if not attach:
        return 0
    kind, argv = target
    _flush()
    if kind == "docker":
        return subprocess.run(argv, check=False).returncode
    return subprocess.run(compose_argv(argv), check=False).returncode


def compose_argv(args: list[str], root: str | None = None) -> list[str]:
    """`_service_compose`: `docker compose -p <p> -f <compose.yml> "$@"`."""
    if root is None:
        root = os.environ.get("CONSOLE_ROOT_DIR", "")
    if not root:
        root = str(paths.repo_root())
    compose = os.path.join(root, ".ci", "docker", "service", "docker-compose.yml")
    return ["docker", "compose", "-p", PROJECT, "-f", compose, *args]


def _flush() -> None:
    """Flush both of this process's streams before a child writes to them.

    A child inherits the file descriptors, not Python's buffers, so without this a line printed before `docker compose up` could reach the pipe AFTER compose's own output, and the order the twin has would be lost in the port for a reason that is not the port's logic.
    """
    sys.stdout.flush()
    sys.stderr.flush()


def _call(argv: list[str], *, quiet_err: bool = False, quiet_out: bool = False) -> int:
    """Run a program the way the twin's bare command line does, streams inherited."""
    _flush()
    return subprocess.run(
        argv,
        check=False,
        stdout=subprocess.DEVNULL if quiet_out else None,
        stderr=subprocess.DEVNULL if quiet_err else None,
    ).returncode


def _errexit(argv: list[str]) -> None:
    """A bare command under the twin's `errexit`: a non-zero status ends the PROCESS. Defect 4."""
    status = _call(argv)
    if status != 0:
        raise SystemExit(status)


def docker_dir(root: str | None = None) -> str:
    """`$SERVICE_DOCKER_DIR` -- `<CONSOLE_ROOT_DIR>/.ci/docker/service`."""
    if root is None:
        root = os.environ.get("CONSOLE_ROOT_DIR", "")
    if not root:
        root = str(paths.repo_root())
    return os.path.join(root, ".ci", "docker", "service")


# Variables bash itself sets or moves for every process, which `env -0` reports and which say nothing about what `env.sh` exported.
_BASH_NOISE = frozenset({"_", "SHLVL", "PWD", "OLDPWD"})


def source_env_sh(path: str) -> None:
    """`source "$SERVICE_DOCKER_DIR/env.sh"`, from Python.

    The twin sources the file into its own shell, so every `export` it makes is visible to the rest of `service_start`. Python cannot source bash, so the file runs in a bash child with the same shell options the twin's sourcing shell has, its log lines going to this process's stderr exactly where the twin's go, and the environment it ends with is read back through an inherited pipe and applied here. A variable whose value did not change is left alone.

    A failure inside `env.sh` ends the twin's whole process through errexit (the file itself also says `set -e`), so it ends this one too, with the same status.
    """
    read_fd, write_fd = os.pipe()
    _flush()
    try:
        proc = subprocess.Popen(
            [
                "bash",
                "-c",
                'set -euo pipefail; source "$1"; env -0 >&"$2"',
                "service-env",
                path,
                str(write_fd),
            ],
            pass_fds=(write_fd,),
            env={**os.environ, "BASH_ENV": ""},
        )
    finally:
        os.close(write_fd)
    with os.fdopen(read_fd, "rb") as reader:
        blob = reader.read()
    status = proc.wait()
    if status != 0:
        raise SystemExit(status)
    before = dict(os.environ)
    changed = {}
    for record in blob.split(b"\0"):
        if not record or b"=" not in record:
            continue
        key, _, value = record.decode("utf-8", "surrogateescape").partition("=")
        if key not in _BASH_NOISE and before.get(key) != value:
            changed[key] = value
    os.environ.update(changed)


def service_health() -> int:
    """`service_health`: poll `/health` every 2 seconds for 90. Defect 6.

    `curl` and `sleep` run as programs, for the reason the module docstring gives.
    """
    port = os.environ.get("SERVICE_HTTP_PORT") or str(DEFAULT_PORT)
    timeout, elapsed, interval = HEALTH_TIMEOUT_S, 0, HEALTH_INTERVAL_S
    log.step("Waiting for service health check (timeout: %ds)" % timeout)
    while elapsed < timeout:
        probe = _call(
            [
                "curl",
                "-sf",
                "--connect-timeout",
                "2",
                "--max-time",
                "5",
                "http://localhost:%s/health" % port,
            ],
            quiet_err=True,
            quiet_out=True,
        )
        if probe == 0:
            log.info("Service is healthy")
            return 0
        _errexit(["sleep", str(interval)])
        elapsed += interval
        if elapsed % 10 == 0:
            log.debug("Waiting... (%ds / %ds)" % (elapsed, timeout))
    log.error("Service health check timed out after %ds" % timeout)
    return 1


def _clock_now() -> int:
    """`date +%s`. `SERVICE_STATUS_NOW` is the same frozen-clock seam `status` reads."""
    pinned = os.environ.get("SERVICE_STATUS_NOW", "")
    return int(pinned) if pinned else int(time.time())


def service_start(args: list[str]) -> int:
    """`service_start [port] [--no-build]`. Defects 4 and 7."""
    check_docker()
    port, skip_build = parse_start_args(args)

    if not port:
        # The twin probes for `python3` before asking `rediacc_ci.core.ports`; this IS python, so that refusal cannot fire here, and the module is asked in process. Its `ss` / `lsof` probes are the same programs either way, which is what the transcript compares.
        found = ports.find_preferred_port(PREFERRED_PORT, SCAN_LOW, SCAN_HIGH)
        if found is None:
            log.error("No free port in 8080-8199 for the service")
            return 1
        port = str(found)

    os.environ["SERVICE_HTTP_PORT"] = port
    log.step("Starting rediacc/web service (port: %s)" % port)

    source_env_sh(os.path.join(docker_dir(), "env.sh"))

    if skip_build:
        log.info("Skipping build (--no-build)")
    else:
        log.step("Building rediacc/web:%s image..." % os.environ.get("SERVICE_TAG", ""))
        _errexit(compose_argv(["build", "web"]))

    log.step("Starting services...")
    _errexit(compose_argv(["up", "-d"]))

    if service_health() != 0:
        log.error("Service failed to become healthy")
        log.info("Check logs with: ./run.sh service logs")
        return 1

    with open(state_path(), "w", encoding="utf-8") as handle:
        handle.write("started=%d\n" % _clock_now())
    with open(state_path(), "a", encoding="utf-8") as handle:
        handle.write("port=%s\n" % port)

    http = os.environ.get("SERVICE_HTTP_PORT", "")
    for line in (
        "",
        "Service is running!",
        "",
        "  URLs:",
        "    Web:            http://localhost:%s" % http,
        "    Console:        http://localhost:%s/console/" % http,
        "    Account portal: http://localhost:%s/account/" % http,
        "    RustFS Console: http://localhost:%s"
        % os.environ.get("SERVICE_RUSTFS_CONSOLE_PORT", ""),
        "",
        "  Account portal (register to create admin):",
        "    Admin email: %s" % os.environ.get("ROOT_EMAIL", ""),
        "",
        "  Credentials:",
        "    RustFS:  %s / %s"
        % (os.environ.get("RUSTFS_ACCESS_KEY", ""), os.environ.get("RUSTFS_SECRET_KEY", "")),
        "    API Key: %s" % os.environ.get("ACCOUNT_SERVER_API_KEY", ""),
        "",
        "Stop with: ./run.sh service stop",
    ):
        log.info(line)
    return 0


def _container_listed(name: str, *, all_states: bool) -> bool:
    """`[ -n "$(docker ps [-a] --format "{{.Names}}" [2>/dev/null] | grep "^<name>$")" ]`.

    ONE `docker ps` PER CALL, as the twin's loops do. `service_stop` spells it `ps -a ... 2>/dev/null`; `service_status` spells it `ps` with stderr passing through, and `all_states` carries both differences because they always travel together in the twin. `grep "^<name>$"` is a regex, and every name in this file is `[a-z0-9-]`, where a regex and a literal agree.
    """
    argv = ["docker", "ps", "-a"] if all_states else ["docker", "ps"]
    _flush()
    probe = subprocess.run(
        [*argv, "--format", "{{.Names}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL if all_states else None,
        text=True,
        check=False,
    )
    return name in probe.stdout.splitlines()


def service_stop() -> int:
    """`service_stop`: compose down, then force-remove by name. Defect 5."""
    check_docker()
    log.step("Stopping service")
    _call(compose_argv(["down", "--volumes", "--remove-orphans"]), quiet_err=True)
    for container in STOP_CONTAINERS:
        if _container_listed(container, all_states=True):
            _call(["docker", "stop", container], quiet_err=True)
            _call(["docker", "rm", container], quiet_err=True)
    with contextlib.suppress(OSError):
        os.remove(state_path())
    log.info("Service stopped")
    return 0


def main(argv: list[str]) -> int:
    if not argv or "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0 if argv else 2
    verb, rest = argv[0], argv[1:]
    if verb == "status":
        check_docker()
        # THE HARNESS SEAM FOR `now`, AND WHY IT IS AN ENVIRONMENT VARIABLE. `service_status` prints an uptime derived from the wall clock, so two runs a second apart disagree and no byte comparison against the twin is possible without freezing it on BOTH sides. The twin's seam is a fake `date` earlier on PATH, which is how `test_gate_bws_env.py` already fakes `bws`; this is
        # the same
        # trick spelled for a process that reads the clock directly. UNSET IN EVERY REAL RUN, so the default is the wall clock and nothing about production behaviour depends on it.
        pinned = os.environ.get("SERVICE_STATUS_NOW", "")
        try:
            return service_status(now=int(pinned) if pinned else None)
        except StatusAbortedError as aborted:
            # THE TWIN PRINTS NOTHING HERE AND NEITHER DOES THIS, on stdout. The reason goes to stderr because a port that reproduced a silent death WITHOUT saying why would be reproducing the defect and hiding the discovery of it at the same time. Exit 1 either way, so the observable contract a caller branches on is unchanged.
            print("service: %s" % aborted, file=sys.stderr)
            return 1
    if verb == "logs":
        check_docker()
        return service_logs(rest[0] if rest else "all")
    if verb == "start":
        return service_start(rest)
    if verb == "stop":
        return service_stop()
    if verb == "health":
        return service_health()
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
