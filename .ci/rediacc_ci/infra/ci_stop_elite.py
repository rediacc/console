"""Port of `.ci/scripts/infra/ci-stop-elite.sh`.

Stops the Elite on-premise Docker Compose stack (`private/elite`) and force removes the one container name the twin still checks by hand, `rediacc-web`. The twin runs `set -e` but every command that can fail is guarded with
`|| { ... }` or `|| true`, so in practice the script never exits non-zero: this
is a best-effort teardown for a CI/breakpoint job that is already finishing, never a validation, and the port preserves that -- it always returns 0.

WHY THE TWO STEPS ARE UNCONDITIONAL ON EACH OTHER. The bash does not `exit` or `return` after a failed `docker compose ... down`; it prints one extra line and falls through to the force-removal loop regardless. A port that turned that warning into an early return would leave `rediacc-web` running whenever compose had already failed -- exactly the case force removal exists for.

CONSOLE ROOT IS DERIVED FROM THIS FILE'S OWN LOCATION, matching the twin's `SCRIPT_DIR/../../..` (from `.ci/scripts/infra/`). This module lives one directory deeper (`.ci/rediacc_ci/infra/`), so it is `parents[3]` here where the twin's is `parents[2]` of ITS directory -- both land on the repository root. `rediacc_ci.paths.repo_root()` is deliberately not used: that resolver honours
$REDIACC_CI_ROOT, and the twin has no such override, so a test pointing one at a fixture and not the other would silently diverge. The port stays on the same single input (the file's own path) as the twin (`BASH_SOURCE[0]`).

EVERY `print()` HERE PASSES `flush=True`, and it is load-bearing, not style. A
child docker process inherits this process's real stdout fd and writes to it directly, while Python's own `print()` fully buffers when stdout is a pipe (the case under a subprocess-based differential and under a captured CI step alike). Without an explicit flush, every line this script prints itself arrives AFTER every line a child process wrote, regardless of the order the two
happened in real time -- reproduced by the differential before this was added: `docker stop`/`docker rm`'s own stdout (they echo the name back) landed before all of this module's own text instead of interleaved with it.

DOCKER CALLS ARE SHELLED OUT TO, NEVER REIMPLEMENTED, mirroring the twin argument for argument: `docker compose -f docker-compose.yml -f docker-compose.standalone.yml down --volumes --remove-orphans`, then
`docker ps -a --format "{{.Names}}"`, then (only on an exact name match)
`docker stop <name>` and `docker rm <name>`. The differential test records the argv sequence, not just stdout, on the `test_infra_ci_stop.py` precedent: two implementations can print the same text while calling different commands, and
for a teardown script the commands are the behaviour.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def _docker(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """`subprocess.run(["docker", *args], ...)`, treating a missing binary as
    bash's exit 127 rather than raising.

    The twin never checks `command -v docker` first; a missing binary just makes every `docker ...` invocation fail with bash's own "command not found" (127),
    caught by the same `|| { ... }` / `|| true` guards that catch a real failure.
    `subprocess.run` raises `FileNotFoundError` for the same case instead of returning a completed process, so without this the port would crash where the twin degrades.
    """
    try:
        return subprocess.run(["docker", *args], check=False, **kwargs)  # type: ignore[arg-type]
    except FileNotFoundError:
        return subprocess.CompletedProcess(["docker", *args], 127, stdout="", stderr="")


# Kept in sync with the twin's `CONTAINERS=(rediacc-web)` array. A second entry
# there without one here is exactly the drift a differential across BOTH containers (not just the one currently listed) would catch; today there is only the one.
CONTAINERS = ("rediacc-web",)


def _console_root() -> pathlib.Path:
    # This file: <root>/.ci/rediacc_ci/infra/ci_stop_elite.py
    return pathlib.Path(__file__).resolve().parents[3]


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments
    console_root = _console_root()
    elite_dir = console_root / "private" / "elite"

    print("Stopping Rediacc Elite CI services...", flush=True)

    if elite_dir.is_dir():
        print("  Stopping Elite Docker Compose services...", flush=True)
        result = _docker(
            [
                "compose",
                "-f",
                "docker-compose.yml",
                "-f",
                "docker-compose.standalone.yml",
                "down",
                "--volumes",
                "--remove-orphans",
            ],
            cwd=str(elite_dir),
        )
        if result.returncode != 0:
            print("  Docker compose down failed, forcing container removal", flush=True)

    ps = _docker(
        ["ps", "-a", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    # `2>/dev/null` in the twin: a failing `docker ps` is treated as "no names", not as an error worth surfacing here.
    names = set(ps.stdout.splitlines()) if ps.returncode == 0 else set()

    for container in CONTAINERS:
        if container not in names:
            continue
        print(f"  Force removing: {container}", flush=True)
        # `2>/dev/null` in the twin, stdout NOT redirected: docker's own stdout (it echoes the container name back on both verbs) reaches the real
        # stdout, same as the twin. `capture_output=True` here would silently
        # swallow it -- a real divergence this port had until the differential's fake docker was taught to reproduce the echo and catch it.
        _docker(["stop", container], stderr=subprocess.DEVNULL)
        _docker(["rm", container], stderr=subprocess.DEVNULL)

    print("All Elite services stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
