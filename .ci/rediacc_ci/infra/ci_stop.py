#!/usr/bin/env python3
"""Stop the CI backend services and clean up after them.

PORT OF `.ci/scripts/infra/ci-stop.sh` (ruling 7, W7P6). Behaviour-for-behaviour, including the parts that look like accidents and are not:

  * EVERY message goes to STDOUT, not stderr. The twin uses bare `echo`, and the
    workflow step that runs this reads the log as one stream; splitting them here
    would reorder the transcript against every other step in the job.
  * A FAILED `docker compose down` IS NOT FATAL. The twin catches it with
    `|| { echo ...; }` and falls through to the force-removal loop, which is the
    whole point: teardown that aborts on the first failure leaves exactly the
    containers it was called to remove.
  * `docker stop` AND `docker rm` BOTH SWALLOW THEIR STATUS, and both are called
    even when the first fails. `2>/dev/null || true` in the twin.
  * The container is only touched when `docker ps -a` NAMES IT EXACTLY. The twin
    greps `^<name>$` against `--format '{{.Names}}'`, so `rediacc-account-server-2`
    is a different container and is left alone.

WHY THE PORT IS STDLIB-ONLY. `.ci/scripts/housekeeping/retire-shadowed-secrets.py` set the precedent for a non-gate entry point under `.ci/scripts/`: no `_cipath` hop and no `rediacc_ci` import, because this file runs during TEARDOWN, after a job has already failed as often as not, and a teardown that cannot start because a package import failed is a teardown that leaves the
machine dirty.

WHAT IS DELIBERATELY NOT HERE. No `--dry-run`, no `--force`, no flags at all. The twin takes none, and a port that grows an interface is not a port.
"""

import pathlib
import shutil
import subprocess
import sys

# From `.ci/scripts/infra/`: infra -> scripts -> .ci -> the repository root.
CONSOLE_ROOT = pathlib.Path(__file__).resolve().parents[3]

CI_DOCKER_DIR = CONSOLE_ROOT / ".ci" / "docker" / "ci"
BACKEND_STATE_FILE = CONSOLE_ROOT / ".backend-state"

# rediacc-web is NOT here, and the omission is load-bearing. The `web:` service it named is gone from .ci/docker/ci/docker-compose.yml (issue #533: nothing ever started it, and it named an image CI does not publish). ci-stop-elite keeps its own rediacc-web entry, which is correct -- that one is elite's container.
CONTAINERS = ("rediacc-account-server",)


def docker_missing() -> str | None:
    """A LOUD refusal rather than a FileNotFoundError traceback.

    The twin gets `docker: command not found` from the shell and, under `set -e` inside `( ... )`, prints its fallback line and carries on to a force-removal loop whose every `docker` call also fails silently -- so it exits 0 having removed nothing. That is the vacuous green this file refuses to reproduce: teardown that cannot reach the daemon has not torn anything down.
    """
    if shutil.which("docker"):
        return None
    return (
        "docker is not on PATH, so nothing can be stopped and nothing can be\n"
        "  verified as already stopped. This is a CANNOT RUN, not a clean teardown.\n"
        "  Install docker, or run this on the host that owns the containers."
    )


def running_container_names() -> list[str]:
    """Every container name docker knows about, running or not.

    `docker ps -a` and not `docker ps`: the twin passes `-a` because a container that EXITED still holds its name and still has to be `docker rm`'d.
    """
    proc = subprocess.run(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def compose_down(directory: pathlib.Path) -> bool:
    """`docker compose down` in `directory`. False means it failed."""
    proc = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "down", "--volumes", "--remove-orphans"],
        cwd=str(directory),
        check=False,
    )
    return proc.returncode == 0


def force_remove(name: str) -> None:
    """Stop then remove, each swallowing its own status, exactly like the twin."""
    for verb in ("stop", "rm"):
        subprocess.run(
            ["docker", verb, name],
            stderr=subprocess.DEVNULL,
            check=False,
        )


def main() -> int:
    problem = docker_missing()
    if problem is not None:
        print("✗ CANNOT RUN: %s" % problem, file=sys.stderr)
        return 77

    print("Stopping Rediacc CI services...")

    if CI_DOCKER_DIR.is_dir():
        print("  Stopping Docker Compose services...")
        if not compose_down(CI_DOCKER_DIR):
            print("  Docker compose down failed, forcing container removal")

    known = running_container_names()
    for container in CONTAINERS:
        if container in known:
            print("  Force removing: %s" % container)
            force_remove(container)

    # `missing_ok`, because the twin's `rm -f` is not an error when there is nothing to remove and this is the common case in CI.
    BACKEND_STATE_FILE.unlink(missing_ok=True)

    print("All services stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
