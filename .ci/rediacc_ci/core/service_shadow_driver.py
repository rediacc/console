#!/usr/bin/env python3
"""Both sides of the `core.service` port differential, in one file.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.service_shadow_driver --side old --twin .ci/lib/service.sh --port .ci/rediacc_ci/core/service.py <scenario>
        drives the BASH: sources `.ci/legacy/run-legacy.sh` (whose prelude sources `.ci/lib/service.sh` and defines the `check_docker` the twin calls) and calls the twin's own function.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.service_shadow_driver --side new --twin .ci/lib/service.sh --port .ci/rediacc_ci/core/service.py <scenario>
        drives the PYTHON: `python3 -m rediacc_ci.core.service <verb>`.

RUN AS A MODULE AND NEVER BY PATH, on the `core/shadow_driver.py` precedent: `PYTHONPATH=.ci` plus `-m` removes the `sys.path` hop `test_canonical_sys_path_hop.py` refuses. ONE FILE for both sides because `dead_python.py` admits a pre-cutover port only when a `.ci/shadow/*.jsonl` record names it, and `--twin` / `--port` are checked to exist so a row can never attest to a file that is not there.

-----------------------------------------------------------------------------
EACH CASE IS ONE PROCESS PER SIDE, AND EACH GETS ITS OWN SANDBOX AND FARM
-----------------------------------------------------------------------------
A case is a verb, its arguments, a stub table, and optionally a seeded state file and extra environment. For every case, on each side, the driver builds a fresh `CONSOLE_ROOT_DIR` and a fresh `core.stubfarm.Farm`, runs the side as a CHILD PROCESS the way `./run.sh service <verb>` really runs, and prints:

    obs <case> rc=<n>
    obs <case> out#<i>| <line>        every stdout line, numbered
    obs <case> err#<i>| <line>        every stderr line, numbered
    obs <case> call#<i>| <argv>       every logged stub call, in order
    obs <case> file <rel> <hex>       every file the case names, or `absent`

NUMBERED because `shadow-gate` compares a finding multiset: without the index, two `sleep 2` calls and three would be the same set, and a port that skipped a probe would compare equal. The sandbox path is replaced by `<root>` on both sides before printing.

The sandbox holds a COPY of `.ci/docker/service/env.sh` (the twin sources it from `$SERVICE_DOCKER_DIR`, which follows `CONSOLE_ROOT_DIR`) and a symlink `.ci/scripts` back to this checkout, because `env.sh` sources `common.sh` relative to itself.

STUBBED: `docker`, `curl`, `sleep`, `ss`, `node`, `openssl` (all logged) and `date` (NOT logged: it is a clock read the port makes in-process through `SERVICE_STATUS_NOW`, and it `exec`s the real `date` for every form but `+%s`). `ss` is how `rediacc_ci.core.ports` decides a port is busy, and it runs on BOTH sides (the twin reaches the same module through `python3 -m`), which makes the free-port search deterministic without holding a single real socket.

-----------------------------------------------------------------------------
THE SIX SCENARIOS
-----------------------------------------------------------------------------
  start       the happy path with key generation, `--no-build` with an explicit port and preset keys, 8080 busy so 8081 wins, a non-numeric port taken verbatim, and two positionals where the last wins.
  start-fail  every free port busy, `compose build` failing, `compose up` failing, `env.sh` failing inside `node`, docker not running, and a 90-second health timeout with `DEBUG=true`.
  stop        every container present, none present, `compose down` failing, docker not running.
  health      healthy at once, healthy after five failures with and without `DEBUG`, a timeout, and an unset versus a set `SERVICE_HTTP_PORT`.
  logs        web, rustfs, all, the empty string, an unknown name, and `docker logs` failing.
  status      running containers with a health answer and without one, a stopped stack, two state-file shapes (the third, a file with no `port=` line, is the one deliberate divergence and lives in `test_core_service.py` rather than in a ledger row, which is a claim of equivalence), and the health probe passing and failing.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import runtmp
from rediacc_ci.core.stubfarm import Farm

EXIT_CANNOT_RUN = 77
FROZEN_NOW = 1700003725
COMPOSE_GLOB = "compose -p rediacc-service -f *"
NOT_RUNNING = "Cannot connect to the Docker daemon"

FN = {
    "start": "service_start",
    "stop": "service_stop",
    "status": "service_status",
    "health": "service_health",
    "logs": "service_logs",
}


@dataclasses.dataclass
class Case:
    name: str
    verb: str
    args: list[str]
    rows: list[dict]
    state: str | None = None
    env: dict[str, str] = dataclasses.field(default_factory=dict)
    files: tuple[str, ...] = (".service-state", ".ci/docker/service/.env")


def row(name: str, glob: str = "*", **kw) -> dict:
    return {"name": name, "glob": glob, **kw}


KEYGEN = [
    row("node", "-e *generateKeyPairSync*", out='{"private":"PRIVKEY","public":"PUBKEY"}\n'),
    row("node", "-e *.private)*", out="PRIVKEY"),
    row("node", "-e *.public)*", out="PUBKEY"),
    row("openssl", "rand -base64 48", out="ab/cd+ef=gh" * 8 + "\n"),
]
PRESET_KEYS = {
    "ACCOUNT_ED25519_PRIVATE_KEY": "preset-priv",
    "ACCOUNT_ED25519_PUBLIC_KEY": "preset-pub",
    "ACCOUNT_SERVER_API_KEY": "preset-api-key",
    "ACCOUNT_JWT_SECRET": "preset-jwt",
}
BUSY = "LISTEN 0 4096 0.0.0.0:%d 0.0.0.0:*\n"


def busy(*ports: int) -> list[dict]:
    return [row("ss", "-tlnH sport = :%d" % p, out=BUSY % p) for p in ports]


def all_busy() -> list[dict]:
    return [row("ss", "-tlnH sport = :*", out="LISTEN 0 1 0.0.0.0:1 0.0.0.0:*\n")]


def curl_fails(times: int | None = None) -> dict:
    return row("curl", "*", rc=7, times=times)


def names(*listed: str) -> str:
    return "".join("%s\n" % n for n in listed)


SCENARIOS: dict[str, list[Case]] = {
    "start": [
        Case("happy-keygen", "start", [], [*KEYGEN, curl_fails(2)]),
        Case("no-build-port", "start", ["9000", "--no-build"], [curl_fails(1)], env=PRESET_KEYS),
        Case("preferred-busy", "start", ["--no-build"], [*busy(8080), *KEYGEN]),
        Case("port-verbatim", "start", ["abc", "--no-build"], [], env=PRESET_KEYS),
        Case("last-positional-wins", "start", ["9000", "9100"], [], env=PRESET_KEYS),
    ],
    "start-fail": [
        Case("every-port-busy", "start", [], [*all_busy(), *KEYGEN]),
        Case(
            "build-fails",
            "start",
            [],
            [row("docker", COMPOSE_GLOB + " build web", rc=17, err="build broke\n")],
            env=PRESET_KEYS,
        ),
        Case(
            "up-fails",
            "start",
            ["--no-build"],
            [row("docker", COMPOSE_GLOB + " up -d", rc=3, out="partial\n")],
            env=PRESET_KEYS,
        ),
        Case("env-sh-fails", "start", [], [row("node", "*", rc=9, err="node: boom\n")]),
        Case(
            "docker-not-running", "start", [], [row("docker", "info", rc=1, err=NOT_RUNNING + "\n")]
        ),
        Case(
            "health-timeout-debug",
            "start",
            ["8123"],
            [curl_fails()],
            env={**PRESET_KEYS, "DEBUG": "true"},
        ),
    ],
    "stop": [
        Case(
            "all-present",
            "stop",
            [],
            [
                row(
                    "docker",
                    "ps -a --format {{.Names}}",
                    out=names(
                        "other",
                        "rediacc-service-web",
                        "rediacc-service-rustfs",
                        "rediacc-service-rustfs-init",
                        "rediacc-service-rustfs-volume-init",
                    ),
                ),
                row("docker", "stop *", out="stopped\n"),
                row("docker", "rm *", out="removed\n"),
            ],
            state="started=1\nport=8080\n",
        ),
        Case(
            "none-present",
            "stop",
            [],
            [row("docker", "ps -a --format {{.Names}}", out=names("rediacc-service-web-2"))],
        ),
        Case(
            "down-fails",
            "stop",
            [],
            [
                row(
                    "docker",
                    COMPOSE_GLOB + " down *",
                    rc=1,
                    out="down-stdout\n",
                    err="down-stderr\n",
                ),
                row(
                    "docker", "ps -a --format {{.Names}}", out=names("rediacc-service-rustfs-init")
                ),
                row("docker", "stop *", rc=1, err="stop refused\n"),
            ],
            state="port=9\n",
        ),
        Case("docker-not-running", "stop", [], [row("docker", "info", rc=1)], state="port=9\n"),
    ],
    "health": [
        Case("healthy-at-once", "health", [], []),
        Case(
            "healthy-after-five", "health", [], [curl_fails(5)], env={"SERVICE_HTTP_PORT": "8555"}
        ),
        Case("healthy-after-five-debug", "health", [], [curl_fails(5)], env={"DEBUG": "true"}),
        Case("timeout", "health", [], [curl_fails()], env={"SERVICE_HTTP_PORT": "9001"}),
        Case("timeout-debug", "health", [], [curl_fails()], env={"DEBUG": "true"}),
    ],
    "logs": [
        Case(
            "web", "logs", ["web"], [row("docker", "logs -f rediacc-service-web", out="web line\n")]
        ),
        Case(
            "rustfs",
            "logs",
            ["rustfs"],
            [row("docker", "logs -f rediacc-service-rustfs", out="rustfs line\n")],
        ),
        Case("all", "logs", ["all"], [row("docker", COMPOSE_GLOB + " logs -f", out="all lines\n")]),
        Case("default", "logs", [], []),
        Case("empty", "logs", [""], []),
        Case("unknown", "logs", ["postgres"], []),
        Case(
            "docker-logs-fails",
            "logs",
            ["web"],
            [row("docker", "logs *", rc=5, err="no such container\n")],
        ),
    ],
    "status": [
        Case(
            "running-healthy",
            "status",
            [],
            [
                row(
                    "docker",
                    "ps --format {{.Names}}",
                    out=names("rediacc-service-web", "rediacc-service-rustfs"),
                ),
                row("docker", "inspect -f {{.State.Status}} *", out="running\n"),
                row(
                    "docker",
                    "inspect -f {{.State.Health.Status}} rediacc-service-web",
                    out="healthy\n",
                ),
                row(
                    "docker",
                    "inspect -f {{.State.Health.Status}} *",
                    rc=1,
                    out="partial",
                    err="no health\n",
                ),
            ],
            state="started=1700000000\nport=9123\n",
        ),
        Case("stopped", "status", [], [curl_fails()]),
        Case(
            "uptime-over-a-day",
            "status",
            [],
            [curl_fails()],
            state="started=1600000000\nport=8080\n",
        ),
        Case(
            "equals-in-port", "status", [], [curl_fails()], state="started=1700000000\nport=a=b\n"
        ),
    ],
}


def build_sandbox(repo: pathlib.Path, work: pathlib.Path, case: Case) -> pathlib.Path:
    root = work / "root"
    service_dir = root / ".ci" / "docker" / "service"
    service_dir.mkdir(parents=True)
    shutil.copy2(repo / ".ci" / "docker" / "service" / "env.sh", service_dir / "env.sh")
    (root / ".ci" / "scripts").symlink_to(repo / ".ci" / "scripts")
    (root / "home").mkdir()
    if case.state is not None:
        (root / ".service-state").write_text(case.state, encoding="utf-8")
    return root


def build_farm(work: pathlib.Path, case: Case) -> Farm:
    farm = Farm(work / "farm")
    farm.stub("docker", "curl", "sleep", "ss", "node", "openssl")
    farm.stub("date", logged=False)
    for spec in case.rows:
        fields = dict(spec)
        farm.respond(fields.pop("name"), fields.pop("glob"), **fields)
    farm.respond("date", "+%s", out="%d\n" % FROZEN_NOW)
    farm.respond("date", "*", sh='exec /usr/bin/date "$@"')
    return farm


def side_env(root: pathlib.Path, farm: Farm, case: Case) -> dict[str, str]:
    base = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(root / "home"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CONSOLE_ROOT_DIR": str(root),
        "SERVICE_STATUS_NOW": str(FROZEN_NOW),
    }
    base.update(case.env)
    return farm.env(base)


def run_side(
    side: str, repo: pathlib.Path, case: Case, env: dict[str, str]
) -> subprocess.CompletedProcess:
    if side == "old":
        argv = [
            "bash",
            "-c",
            'source "$1"; shift; "$@"',
            "service-old",
            str(repo / ".ci" / "legacy" / "run-legacy.sh"),
            FN[case.verb],
            *case.args,
        ]
    else:
        env = dict(env, PYTHONPATH=str(repo / ".ci"))
        argv = ["python3", "-m", "rediacc_ci.core.service", case.verb, *case.args]
    return subprocess.run(
        argv, cwd=repo, env=env, capture_output=True, text=True, check=False, timeout=300
    )


def emit_case(
    case: Case, proc: subprocess.CompletedProcess, farm: Farm, root: pathlib.Path
) -> list[str]:
    def norm(text: str) -> str:
        return text.replace(str(root), "<root>").replace(str(farm.root), "<farm>")

    lines = ["obs %s rc=%d" % (case.name, proc.returncode)]
    lines += [
        "obs %s out#%d| %s" % (case.name, i, norm(t))
        for i, t in enumerate(proc.stdout.splitlines())
    ]
    lines += [
        "obs %s err#%d| %s" % (case.name, i, norm(t))
        for i, t in enumerate(proc.stderr.splitlines())
    ]
    lines += [
        "obs %s call#%d| %s" % (case.name, i, norm(t)) for i, t in enumerate(farm.transcript())
    ]
    for rel in case.files:
        path = root / rel
        body = path.read_bytes().hex() if path.is_file() else "absent"
        lines.append("obs %s file %s %s" % (case.name, rel, body))
    return lines


def observe(side: str, repo: pathlib.Path, case: Case) -> list[str]:
    """Run one case on one side in a fresh sandbox; return its observation lines."""
    work = pathlib.Path(tempfile.mkdtemp(prefix="svc-shadow-", dir=runtmp.shared("shadow-driver-")))
    try:
        root = build_sandbox(repo, work, case)
        farm = build_farm(work, case)
        proc = run_side(side, repo, case, side_env(root, farm, case))
        return emit_case(case, proc, farm, root)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="one side of the core.service differential")
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--twin", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("scenario", choices=sorted(SCENARIOS))
    args = parser.parse_args(argv)
    repo = pathlib.Path.cwd().resolve()
    for label, rel in (("twin", args.twin), ("port", args.port)):
        if not (repo / rel).is_file():
            sys.stderr.write(
                "service_shadow_driver: the %s %s does not exist under %s\n" % (label, rel, repo)
            )
            return EXIT_CANNOT_RUN
    for case in SCENARIOS[args.scenario]:
        for line in observe(args.side, repo, case):
            print(line)
    return 0


if __name__ == "__main__":
    os.environ.setdefault("LC_ALL", "C")
    sys.exit(main(sys.argv[1:]))
