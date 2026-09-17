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

NOT PORTED AT ALL, and said out loud rather than left as an absence: `service_start` and `service_stop`. THERE IS NO `service_start` OR `service_stop` FUNCTION BELOW. `service_start` builds an image, sources `.ci/docker/service/env.sh` (which MINTS CREDENTIALS and writes a `.env`), and
polls a health endpoint for up to 90 seconds; `service_stop` tears down a compose
project and removes containers by name. Driving either twice per observation, five times over, would build the web image ten times and would leave real containers behind if a comparison were interrupted, so neither could be proved here, and a port nobody can compare is a second implementation rather than a replacement.

What IS here from those two is the set of pieces that are decidable without Docker and are therefore assertable: `parse_start_args` (the argument loop), `compose_argv` (`_service_compose`), `docker_available` / `check_docker`, `health_ok` (the poll's single probe) and `uptime_line`. THE LIFECYCLE BODIES ARE AN HONEST GAP, and whoever closes it owns finding a way to compare them.

--------------------------------------------------------------------------
WHY THE LOGGER IS `rediacc_ci.log` AND THE COLOURS ARE NOT
--------------------------------------------------------------------------
`log_info` / `log_error` / `log_step` / `log_debug` here are `common.sh`'s, and `rediacc_ci.log` is already the byte-exact port of those four, tty gating included. Re-deriving them would be the fifth copy of a thing that has one. The `COLOR_*` constants are the OTHER family -- `constants.sh`'s ungated pair -- and they are duplicated below precisely because they are not the same
decision. Collapsing them into `log`'s would fix defect 2 by accident, in a port.
"""

import os
import shutil
import subprocess
import sys
import time

from rediacc_ci import log, paths

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

USAGE = """service -- `.ci/lib/service.sh`, without the Docker lifecycle verbs.

  python3 -m rediacc_ci.core.service status
  python3 -m rediacc_ci.core.service logs <web|rustfs|all>

`status` is the twin's `service_status`, byte for byte, colour included.
`logs` reproduces only the DISPATCH, including the refusal; it never attaches to
a container, because a differential cannot compare two streams that do not end.
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
    implementations; that is preserved rather than fixed for the same reason.
    On several matches grep emits several lines and `cut` several fields, and the twin then assigns the whole multi-line string -- also preserved.
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

    Returns (ok, lines-to-log). The twin `exit 1`s; returning lets the caller
    decide, and the two call shapes are proved to agree in the tests rather than assumed.
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
    """`docker ps --format "{{.Names}}"`, as a set.

    ONE `docker ps` FOR THE WHOLE STATUS, where the twin runs one per container. That is the single behavioural liberty taken here and it is invisible in the output: the twin greps the same list twice. It is called out because a reader diffing the two will notice the missing second call.
    """
    probe = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return {line for line in probe.stdout.splitlines() if line}


def inspect(container: str, template: str, default: str | None = None) -> str:
    """`docker inspect -f <tpl> <c>`, with the twin's `|| echo "N/A"` fallback."""
    probe = subprocess.run(
        ["docker", "inspect", "-f", template, container],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        if default is None:
            raise StatusAbortedError("docker inspect %s failed" % container)
        return default
    return probe.stdout.strip()


def health_ok(port: int | str, timeout: float = 5) -> bool:
    """`curl -sf "http://localhost:<port>/health" &>/dev/null`.

    `curl` AND NOT `urllib`, deliberately. `-f` makes a 4xx a non-zero exit,
    `-s` silences the progress meter, and both streams go to /dev/null; matching
    that with urllib means matching curl's redirect policy, its proxy environment handling and its idea of a connection failure. The twin's behaviour IS curl's behaviour, so the port runs curl.
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

    `now` is injectable ONLY so the uptime line can be asserted exactly; the
    default is the wall clock, which is what the twin's `date +%s` reads.
    """
    stream = sys.stdout if out is None else out
    log.info("Service Status")
    log.info("==============")
    print(file=stream)

    running = running_containers()
    for container in STATUS_CONTAINERS:
        if container in running:
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


def main(argv: list[str]) -> int:
    if not argv or "--help" in argv or "-h" in argv:
        print(USAGE)
        return 0 if argv else 2
    verb, rest = argv[0], argv[1:]
    if verb == "status":
        check_docker()
        # THE HARNESS SEAM FOR `now`, AND WHY IT IS AN ENVIRONMENT VARIABLE. `service_status` prints an uptime derived from the wall clock, so two runs a second apart disagree and no byte comparison against the twin is possible without freezing it on BOTH sides. The twin's seam is a fake `date` earlier on PATH, which is how `test-bws-env.sh` already fakes
        # `bws`; this is the same trick spelled for a process that reads the
        # clock directly. UNSET IN EVERY REAL RUN, so the default is the wall clock and nothing about production behaviour depends on it.
        pinned = os.environ.get("SERVICE_STATUS_NOW", "")
        try:
            return service_status(now=int(pinned) if pinned else None)
        except StatusAbortedError as aborted:
            # THE TWIN PRINTS NOTHING HERE AND NEITHER DOES THIS, on stdout. The reason goes to stderr because a port that reproduced a silent death WITHOUT saying why would be reproducing the defect and hiding the discovery of it at the same time. Exit 1 either way, so the observable contract a caller branches on is unchanged.
            print("service: %s" % aborted, file=sys.stderr)
            return 1
    if verb == "logs":
        check_docker()
        return service_logs(rest[0] if rest else "all", attach=False)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
