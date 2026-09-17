"""Port of `.ci/scripts/infra/ci-start-account.sh` (157 lines).

Validates the three account-server secrets, sources the CI environment, writes `.ci/docker/ci/.env`, brings up the `account-server` compose service, waits for its health status, and re-checks that it is not in a restart loop.

LIVE CALLER OF THE TWIN, not repointed by this port:
  * `.github/workflows/ci.yml:740` -- `run: bash .ci/scripts/infra/ci-start-account.sh`

WHAT MOVES AND WHAT DOES NOT. `.ci/scripts/infra/ci-env.sh` is SOURCED, not executed, and stays bash: `source_ci_env` (imported from the sibling elite port would create a package import in a file that must run standalone from a fixture, so it is duplicated deliberately -- see PORT NOTES) runs the real file under a real bash and imports its exported environment. Every `docker` call
is shelled out to argument for argument.

PORT NOTES, each driven before it was written down.

`source_ci_env` IS DUPLICATED FROM `ci_start_elite.py` ON PURPOSE. Both modules are executed as plain scripts from a fixture tree that holds only the two subjects (`python3 .ci/rediacc_ci/infra/ci_start_account.py`), with no
`rediacc_ci` package on `sys.path`; an import between them would make the
differential's fixture a package problem instead of a behaviour comparison. The twin has the same duplication in the other direction -- both bash scripts `source` the same file rather than sharing a function.

THE THREE SECRET GUARDS RUN BEFORE ANYTHING ELSE AND BEFORE THE SOURCE (:29-43), which is why the port cannot hoist the `source` for convenience: on a host with no secrets the twin prints two lines and exits 1 having generated no keys, written no `.env` and started no container.

CI-ENV.SH OVERWRITES THE PRODUCTION KEYS AND THE TWIN PUTS THEM BACK. ci-env.sh generates a throwaway Ed25519 pair (:51-62) only when `ACCOUNT_ED25519_PRIVATE_KEY` is empty -- which it never is here, since :29 already refused that case -- but
it unconditionally re-exports `ACCOUNT_SERVER_API_KEY` (:83) from `${VAR:-...}`,
so the value survives. The save/restore on :47-49 and :61-63 is therefore belt-and-braces in the current ci-env.sh and is reproduced exactly rather than
reasoned away: a future ci-env.sh that stops honouring `${VAR:-}` would break
the twin and the port identically.

`CI_DOCKER_DIR` IS READ BACK FROM THE SOURCED ENVIRONMENT, not recomputed. The
twin sets it on :22 and ci-env.sh then `export`s its own on :122; the twin's
`.env` write on :78 uses whichever value is live after the source, which is ci-env.sh's. Both derive from the same `SCRIPT_DIR/../../..`, so they agree
today; taking the sourced one keeps them agreeing if that ever stops being true.

`grep -q "healthy"` MATCHES `unhealthy`, AND THIS PORT REPRODUCES THE MATCH.
:106 pipes `docker inspect --format='{{.State.Health.Status}}'` into
`grep -q "healthy"`, which is a SUBSTRING test: `echo unhealthy | grep -q healthy` succeeds (driven). A container docker has marked UNHEALTHY is therefore announced as "Account server is healthy" and the job proceeds. Whether that is reachable today is an arithmetic question about the compose file and about how long a `docker inspect` takes, not about this script. The measurement
lives in `test_infra_ci_start_account.py::test_unhealthy_is_read_as_healthy`: the last
probe lands around t=191s on this host against an earliest-`unhealthy` of about
t=200s, a nine-second margin a slower daemon erases. Fixing it is a change to a
live CI step's pass/fail behaviour and is out of this port's file ownership; it
is pinned here, not silently corrected.

THE PROGRESS LINE FIRES ON MULTIPLES OF 15 ONLY (:118). With `interval=3` that
is every fifth iteration. `((elapsed % 15 == 0))` returns exit status 1 when the
expression is zero, which under `set -e` would abort -- except that it is the condition of an `if`, which `set -e` exempts. Reproduced as a plain modulo test.

`docker compose ... logs account-server` FAILING ON THE FAILURE PATH SUPPRESSES THE `exit 1`. :128-132 is the command following the final `||`, so `set -e` is not relaxed inside it. Driven:
`bash -c 'set -e; f(){ return 1; }; f || { ./nope.sh; exit 1; }'` exits 127.
Reproduced -- `main` returns the logs command's rc when it is non-zero.

`\t` INSIDE THE TWIN'S DOUBLE QUOTES IS A LITERAL BACKSLASH-T, NOT A TAB, and this port had it wrong until the differential's argv record caught it. Bash does not process `\t` inside `"..."`, so `docker ps --format "table
{{.Names}}\t{{.Status}}\t{{.Ports}}"` passes docker a format string containing
two backslash-t sequences, which docker's own `table` directive then expands. A Python `"\t"` would have handed docker a real tab and quietly changed the column layout of a diagnostic nobody reads closely. The argument is a raw string here for that reason.

THE HEALTH POLL IS A BUDGET, NOT A DEADLINE. Same arithmetic as the twin: 180s divided by a 3s interval is 60 probes, and the wall time the probes themselves consume is not counted against the budget.

Exit: 0 when the account server came up and is still running; the twin's own
non-zero status otherwise.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import time

# The twin's `local timeout=180` / `local interval=3` (:100-102) and the bare
# `sleep 2` on :145. Named rather than inlined so a test can assert the real twin still carries the same three numbers. The differential does NOT shrink them -- it nulls the three `sleep` calls instead, so both sides keep the real arithmetic and still perform all 60 probes.
TIMEOUT_SECONDS = 180
INTERVAL_SECONDS = 3
SETTLE_SECONDS = 2

CONTAINER = "rediacc-account-server"

REQUIRED_SECRETS = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY",
)

_SHELL_PRIVATE = frozenset({"_", "SHLVL", "PWD", "OLDPWD"})


def _console_root() -> pathlib.Path:
    """The twin's `SCRIPT_DIR/../../..`; see `ci_start_elite._console_root`."""
    return pathlib.Path(__file__).resolve().parents[3]


def source_ci_env(ci_env_sh: pathlib.Path) -> tuple[int, dict[str, str]]:
    """Run the real bash `ci-env.sh` and return `(rc, exported environment)`.

    stdout and stderr are INHERITED so ci-env.sh's `::add-mask::` directives and its three-line summary land on this process's real streams in order.
    """
    with tempfile.TemporaryDirectory() as td:
        dump = pathlib.Path(td) / "env.0"
        rc = subprocess.run(
            [
                "bash",
                "-c",
                'set -e\n. "$1"\nenv -0 >"$2"\n',
                "bash",
                str(ci_env_sh),
                str(dump),
            ],
            check=False,
        ).returncode
        if rc != 0:
            return rc, {}
        raw = dump.read_bytes()

    exported: dict[str, str] = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        name, sep, value = entry.partition(b"=")
        if not sep:
            continue
        key = name.decode("utf-8", "replace")
        if key in _SHELL_PRIVATE:
            continue
        exported[key] = value.decode("utf-8", "replace")
    return 0, exported


def env_file_body(env: dict[str, str]) -> str:
    """The exact 8 lines the twin's `{ ... } >"$CI_DOCKER_DIR/.env"` writes (:69-78).

    Four of the seven values use `${VAR:-}` in the twin and three do not; with
    `set -e` and no `set -u` both spellings yield the empty string for an unset name, so the distinction is cosmetic and `dict.get(..., "")` covers both.
    """
    return "".join(
        "%s\n" % line
        for line in (
            "# Auto-generated by ci-start-account.sh -- do not edit",
            "ACCOUNT_ED25519_PRIVATE_KEY=%s" % env.get("ACCOUNT_ED25519_PRIVATE_KEY", ""),
            "ACCOUNT_ED25519_PUBLIC_KEY=%s" % env.get("ACCOUNT_ED25519_PUBLIC_KEY", ""),
            "ACCOUNT_X25519_PRIVATE_KEY=%s" % env.get("ACCOUNT_X25519_PRIVATE_KEY", ""),
            "ACCOUNT_X25519_PUBLIC_KEY=%s" % env.get("ACCOUNT_X25519_PUBLIC_KEY", ""),
            "ACCOUNT_SERVER_API_KEY=%s" % env.get("ACCOUNT_SERVER_API_KEY", ""),
            "STRIPE_WEBHOOK_SECRET=%s" % env.get("STRIPE_WEBHOOK_SECRET", ""),
            "ACCOUNT_JWT_SECRET=%s" % env.get("ACCOUNT_JWT_SECRET", ""),
        )
    )


def _docker(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    """`docker <args>`, treating a missing binary as bash's 127 rather than raising.

    The twin never probes for the binary; a missing one just makes every call
    fail with bash's own "command not found", caught by the same guards that catch a real failure.
    """
    try:
        return subprocess.run(["docker", *args], check=False, **kwargs)  # type: ignore[arg-type]
    except FileNotFoundError:
        return subprocess.CompletedProcess(["docker", *args], 127, stdout="", stderr="")


def _load_diagnostic() -> str:
    """The twin's `:123` load line, with both of its `|| echo` fallbacks."""
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


def health_status_says_healthy(inspect_stdout: str) -> bool:
    """`grep -q "healthy"` over `docker inspect --format='{{.State.Health.Status}}'`.

    SUBSTRING, NOT EQUALITY, and deliberately so: this is the twin's behaviour. `"unhealthy"` contains `"healthy"` and therefore returns True here, exactly as it does in bash. See the module docstring.
    """
    return any("healthy" in line for line in inspect_stdout.splitlines())


def wait_for_account_server() -> bool:
    """The twin's `wait_for_account_server` (:99-126). True on healthy."""
    elapsed = 0
    print("  Waiting for account-server...", flush=True)
    while elapsed < TIMEOUT_SECONDS:
        inspect = _docker(
            ["inspect", CONTAINER, "--format={{.State.Health.Status}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if health_status_says_healthy(inspect.stdout):
            print("  Account server is healthy", flush=True)
            return True
        # stdout is piped into the `grep -q` equivalent below; stderr is NOT
        # redirected in the twin, so it stays on this process's stderr.
        ps = _docker(["ps", "--format", "{{.Names}}"], stdout=subprocess.PIPE, text=True)
        if CONTAINER not in ps.stdout.splitlines():
            print("  Account server container stopped unexpectedly", flush=True)
            _docker(["logs", CONTAINER, "--tail", "50"])
            return False
        time.sleep(INTERVAL_SECONDS)
        elapsed += INTERVAL_SECONDS
        if elapsed % 15 == 0:
            print("    Still waiting... (%ds / %ds)" % (elapsed, TIMEOUT_SECONDS), flush=True)
    print(
        "  Account server failed to become healthy within %ds" % TIMEOUT_SECONDS,
        flush=True,
    )
    print(_load_diagnostic(), flush=True)
    _docker(["logs", CONTAINER, "--tail", "100"])
    return False


def main(argv: list[str]) -> int:
    del argv  # the twin takes no arguments
    console_root = _console_root()
    script_dir = console_root / ".ci" / "scripts" / "infra"

    print("Starting Rediacc Account Server CI services...", flush=True)

    for name in REQUIRED_SECRETS:
        if os.environ.get(name, "") == "":
            print("ERROR: %s is not set" % name, flush=True)
            print("This must be configured as a GitHub secret", flush=True)
            return 1

    saved = {name: os.environ[name] for name in REQUIRED_SECRETS}

    rc, env = source_ci_env(script_dir / "ci-env.sh")
    if rc != 0:
        return rc
    os.environ.update(env)
    os.environ.update(saved)

    ci_docker_dir = pathlib.Path(
        os.environ.get("CI_DOCKER_DIR") or str(console_root / ".ci" / "docker" / "ci")
    )

    print("Writing .env to %s..." % ci_docker_dir, flush=True)
    try:
        (ci_docker_dir / ".env").write_text(env_file_body(dict(os.environ)), encoding="utf-8")
    except OSError as exc:
        # The twin dies here too, rc=1, with bash's own `line 78:` diagnostic,
        # which this port does not forge. See `ci_start_elite.py` for the same named divergence and the reason a hard-coded line number is refused.
        print("%s/.env: %s" % (ci_docker_dir, exc.strerror), file=sys.stderr, flush=True)
        return 1

    print("Starting Account Server Docker Compose services...", flush=True)

    up = _docker(
        ["compose", "-f", "docker-compose.yml", "up", "-d", "account-server"],
        cwd=str(ci_docker_dir),
    )
    if up.returncode != 0:
        # `set -e` (:17) with no guard on :87.
        return up.returncode

    print("Waiting for Account Server to be ready...", flush=True)

    if not wait_for_account_server():
        print("Account server startup failed", flush=True)
        logs = _docker(
            ["compose", "-f", "docker-compose.yml", "logs", "account-server"],
            cwd=str(ci_docker_dir),
        )
        # :131's `exit 1` is unreachable when this command fails; see docstring.
        return logs.returncode if logs.returncode != 0 else 1

    print(flush=True)  # the twin's bare `echo ""`
    print("Account server is ready!", flush=True)

    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output != "":
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write("account_server_url=http://localhost:3000\n")

    time.sleep(SETTLE_SECONDS)
    status = _docker(
        ["inspect", CONTAINER, "--format={{.State.Status}}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    # `$(docker inspect ... || echo "missing")` -- command substitution strips trailing newlines, and the fallback replaces the whole value.
    container_status = status.stdout.rstrip("\n") if status.returncode == 0 else "missing"
    if container_status != "running":
        print("Account server container is not running (status: %s)" % container_status, flush=True)
        print("Container logs:", flush=True)
        # `2>&1` on :150, unlike the two `docker logs` calls inside the wait loop, which leave stderr on stderr.
        _docker(["logs", CONTAINER, "--tail", "50"], stderr=subprocess.STDOUT)
        return 1

    print(flush=True)  # the twin's bare `echo ""`
    print("Running containers:", flush=True)

    ps: subprocess.Popen[bytes] | None
    try:
        ps = subprocess.Popen(
            ["docker", "ps", "--format", r"table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
            stdout=subprocess.PIPE,
        )
    except FileNotFoundError:
        # bash still runs the right-hand side of the pipe when the left-hand command does not exist.
        ps = None
    subprocess.run(
        ["grep", "-E", "(NAME|account)"],
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
