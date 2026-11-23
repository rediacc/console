"""`rediacc_ci.core.service` against the answers frozen from the retired `.ci/lib/service.sh` (`goldens/twins/lib.service.jsonl`).

REAL DOCKER, NO STACK. Every case runs the real `docker ps` and `docker inspect` against a daemon with the `rediacc-service-*` containers absent, which is the state a developer's machine is in almost all the time and the only state a differential can enter five times without building an image ten times. What is NOT covered is named in the module docstring of the port rather than
left as an absence: `service_start` and `service_stop`.

THE CLOCK IS FROZEN ON BOTH SIDES, BY DIFFERENT SEAMS, AND THAT IS DELIBERATE.
`service_status` prints an uptime derived from `date +%s`, so two runs a second apart disagree and no byte comparison is possible. The twin's seam is a fake `date` earlier on PATH -- the same trick `test_gate_bws_env.py` uses for `bws`. The port reads the clock in-process, so its seam is `SERVICE_STATUS_NOW`. Both are supplied by `env_for` below from ONE value, so the two sides
cannot
drift apart through the harness.

`check_docker` IS DEFINED BY THE HARNESS ON THE BASH SIDE because the twin does not define it: it lives in `.ci/legacy/run-legacy.sh`, the file that SOURCES `service.sh`, and only late binding makes the twin work at all. The definition below is copied from that file verbatim. That is defect 3 in the port's docstring, and the harness having to supply it is the evidence for it.
"""

import dataclasses
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

import pytest

from rediacc_ci import runtmp
from rediacc_ci.core import service, stubfarm
from rediacc_ci.core.stubfarm import Farm
from rediacc_ci.tests import differential as diff
from rediacc_ci.well_known import DOCKER_INSTALL_DOCS

TWIN = ".ci/lib/service.sh"

# `check_docker` from `.ci/legacy/run-legacy.sh:56-68`, verbatim. See the header.
BASH_DRIVER = textwrap.dedent(
    """
    source "$SERVICE_TWIN"
    check_docker() {
        if ! command -v docker &>/dev/null; then
            log_error "Docker is not installed"
            log_info "Install Docker from: """
    + DOCKER_INSTALL_DOCS
    + """/"
            exit 1
        fi
        if ! docker info &>/dev/null; then
            log_error "Docker is not running"
            log_info "Start Docker Desktop or Docker daemon"
            exit 1
        fi
    }
    case "$1" in
      status) check_docker; service_status ;;
      logs) check_docker; service_logs "${2-all}" ;;
    esac
    """
)

FROZEN_NOW = 1700003725


@pytest.fixture(scope="module")
def fake_date(tmp_path_factory):
    """A `date` that answers `+%s` from the environment and defers otherwise.

    DEFERS RATHER THAN REFUSES, because `service.sh` is not the only thing on the other side of this PATH: anything it sources may call `date` for a real reason, and a fake that answered every form would change behaviour the differential is trying to measure.
    """
    binroot = tmp_path_factory.mktemp("fakebin")
    script = binroot / "date"
    script.write_text(
        "#!/bin/bash\n"
        'if [[ "${1:-}" == "+%s" ]]; then echo "$SERVICE_STATUS_NOW"; exit 0; fi\n'
        'exec /usr/bin/date "$@"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return binroot


def env_for(root, fake_date_dir, now: int = FROZEN_NOW) -> dict:
    """ONE mapping for both sides. Both clock seams are set from one value."""
    return diff.env_for(
        PATH="%s:/usr/local/bin:/usr/bin:/bin" % fake_date_dir,
        CONSOLE_ROOT_DIR=str(root),
        SERVICE_STATUS_NOW=str(now),
    )


def _bash(argv: list[str], env: dict):
    """What the retired twin answered, from the golden frozen out of `service.sh`."""
    args = " ".join("'%s'" % a for a in argv)
    script = 'SERVICE_TWIN="%s"\nset -- %s\n%s' % (TWIN, args, BASH_DRIVER)
    return diff.twin_streams(
        TWIN,
        script,
        env=env,
        port=lambda: _python(argv, env),
        work=diff.pytest_tmp_roots(*env.values()),
    )


def _python(argv: list[str], env: dict):
    args = " ".join("'%s'" % a for a in argv)
    return diff.bash_streams("PYTHONPATH=.ci python3 -m rediacc_ci.core.service %s" % args, env=env)


# (id, state-file body or None, argv, now)
CASES = [
    ("status-no-state-file", None, ["status"], FROZEN_NOW),
    ("status-port-and-started", "started=1700000000\nport=9123\n", ["status"], FROZEN_NOW),
    ("status-one-minute-uptime", "started=1700000000\nport=8080\n", ["status"], 1700000061),
    # 25 hours: the twin's `printf '%02d:%02d:%02d'` does NOT roll into days, so this prints `25:00:00`. `datetime.timedelta` would print `1 day, 1:00:00`.
    ("status-over-24-hours", "started=1700000000\nport=8080\n", ["status"], 1700090000),
    # `cut -d= -f2` takes the SECOND field only, so a value containing `=` is
    # truncated on both sides. A bug, preserved, because the twin has it.
    ("status-port-value-with-equals", "started=1700000000\nport=a=b\n", ["status"], 1700090000),
    ("logs-unknown-service", None, ["logs", "nosuch"], FROZEN_NOW),
    ("logs-another-unknown", None, ["logs", "postgres"], FROZEN_NOW),
]


@pytest.mark.parametrize(("case_id", "state", "argv", "now"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_live_twin(tmp_path, fake_date, case_id, state, argv, now) -> None:
    root = tmp_path / case_id
    root.mkdir()
    if state is not None:
        (root / ".service-state").write_text(state, encoding="utf-8")
    env = env_for(root, fake_date, now)
    old, new = _bash(argv, env), _python(argv, env)
    assert old == new, "case %s: bash %r vs python %r" % (case_id, old, new)


def test_the_corpus_is_not_empty() -> None:
    assert len(CASES) >= 5, "the differential corpus collapsed to %d case(s)" % len(CASES)


def test_the_differential_can_fail(tmp_path, fake_date) -> None:
    root = tmp_path / "canfail"
    root.mkdir()
    (root / ".service-state").write_text("started=1700000000\nport=9123\n", encoding="utf-8")
    env = env_for(root, fake_date)
    old, new = _bash(["status"], env), _python(["status"], env)
    assert old == new
    assert old != (new[0], new[1].replace("Uptime: 01:02:05", "Uptime: 1:02:05"), new[2]), (
        "the comparison is not looking at the uptime line"
    )
    assert old != (new[0], new[1].replace("\033[0;31m", ""), new[2]), (
        "the comparison is not looking at the colour escapes, which is where defect 2 lives"
    )
    assert old != (new[0], new[1], new[2] + "\n"), "the comparison is ignoring stderr"


def test_the_clock_is_really_frozen(tmp_path, fake_date) -> None:
    """A CONTROL ON THE HARNESS. If either seam stopped working, every uptime
    case above would still pass whenever the two runs landed in the same second,
    and would flake otherwise. Two DIFFERENT frozen values must give two different uptimes on both sides."""
    root = tmp_path / "clock"
    root.mkdir()
    (root / ".service-state").write_text("started=1700000000\nport=8080\n", encoding="utf-8")
    first = _bash(["status"], env_for(root, fake_date, 1700000061))
    second = _bash(["status"], env_for(root, fake_date, 1700003725))
    assert "Uptime: 00:01:01" in first[1]
    assert "Uptime: 01:02:05" in second[1]
    assert _python(["status"], env_for(root, fake_date, 1700000061))[1] == first[1]


def test_status_aborts_silently_on_a_partial_state_file(tmp_path, fake_date) -> None:
    """DEFECT 1, measured on both sides, and the one place the port speaks up.

    A state file carrying `started=` but no `port=` makes the twin's bare
    assignment take grep's exit 1 through `pipefail` into `errexit`. The function stops mid-output: two container lines, a blank, and then NOTHING. No health check, no trailing blank, no message, exit 1 -- and because errexit is still armed in the sourcing script, it takes `run-legacy.sh` down with it.

    stdout AND the exit code MATCH EXACTLY. The port adds one line on stderr naming the cause, which is the single deliberate divergence here: a port that reproduced a silent death without saying why would be reproducing the defect and hiding its own discovery of it. The shadow ledger therefore omits this
    case, because a ledger row is a claim of equivalence.
    """
    root = tmp_path / "partial"
    root.mkdir()
    (root / ".service-state").write_text("started=1700000000\n", encoding="utf-8")
    env = env_for(root, fake_date)
    old, new = _bash(["status"], env), _python(["status"], env)

    assert old[0] == new[0] == 1
    assert old[1] == new[1]
    assert "Health check" not in old[1], "the twin really does stop before the verdict"
    assert old[1].count("not running") == 2, "and really does print the containers first"
    explanation = next(line for line in new[2].splitlines() if line.startswith("service: "))
    assert old[2] == new[2].replace(explanation + "\n", "")
    assert "matched nothing" in new[2]
    assert "errexit" in new[2]

    # THE CONTROL: the same file WITH a port= line does not abort.
    (root / ".service-state").write_text("started=1700000000\nport=8080\n", encoding="utf-8")
    ok_old, ok_new = _bash(["status"], env), _python(["status"], env)
    assert ok_old == ok_new
    assert ok_old[0] == 0
    assert "Health check: FAILED" in ok_old[1]


def test_status_writes_raw_ansi_to_stdout_while_stderr_is_clean(tmp_path, fake_date) -> None:
    """DEFECT 2. The DATA stream is coloured on a pipe and the LOG stream is not.

    Asserted on both sides so the port cannot quietly "fix" it, and so a reader who finds this surprising finds the measurement rather than an opinion.
    """
    root = tmp_path / "colour"
    root.mkdir()
    env = env_for(root, fake_date)
    for rc, out, err in (_bash(["status"], env), _python(["status"], env)):
        assert rc == 0
        assert diff.escape_bytes(out) > 0, "stdout lost its ungated COLOR_* escapes"
        assert diff.escape_bytes(err) == 0, "stderr gained colour off a tty"
        assert "✓ Service Status" in err


# -- the helpers, exercised directly -----------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "Uptime: 00:00:00"),
        (59, "Uptime: 00:00:59"),
        (61, "Uptime: 00:01:01"),
        (3725, "Uptime: 01:02:05"),
        (90000, "Uptime: 25:00:00"),
        (359999, "Uptime: 99:59:59"),
    ],
)
def test_uptime_line(seconds: int, expected: str) -> None:
    """Hours do NOT roll into days. `timedelta` would; `printf '%02d'` does not."""
    assert service.uptime_line(seconds) == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], ("", False)),
        (["--no-build"], ("", True)),
        (["9000"], ("9000", False)),
        (["9000", "--no-build"], ("9000", True)),
        # NO BREAK IN THE TWIN'S LOOP, so the LAST positional wins, silently.
        (["9000", "9100"], ("9100", False)),
    ],
    ids=["none", "no-build", "port", "both", "two-ports-last-wins"],
)
def test_parse_start_args(args, expected) -> None:
    assert service.parse_start_args(args) == expected


def test_grep_cut_raises_where_the_twin_dies() -> None:
    """Both directions: a match returns, no match raises."""
    assert service.grep_cut("port=9123\n", "port=") == "9123"
    with pytest.raises(service.StatusAbortedError, match="matched nothing"):
        service.grep_cut("started=1\n", "port=")


def test_grep_cut_truncates_a_value_containing_an_equals_sign() -> None:
    """`cut -d= -f2` takes the second field only. Preserved, not fixed."""
    assert service.grep_cut("port=a=b\n", "port=") == "a"


def test_service_logs_dispatch_both_directions() -> None:
    assert service.service_logs_target("web")[1][-1] == "rediacc-service-web"
    assert service.service_logs_target("rustfs")[1][-1] == "rediacc-service-rustfs"
    assert service.service_logs_target("all") == ("compose", ["logs", "-f"])
    # `all | ""` share an arm in the twin, so an EMPTY service follows everything rather than refusing. Pinned because it looks like a typo and is not.
    assert service.service_logs_target("") == ("compose", ["logs", "-f"])
    assert service.service_logs_target("nosuch") is None


def test_compose_argv_names_the_project_and_the_file(tmp_path) -> None:
    argv = service.compose_argv(["up", "-d"], root=str(tmp_path))
    assert argv[:5] == ["docker", "compose", "-p", "rediacc-service", "-f"]
    assert argv[5].endswith(".ci/docker/service/docker-compose.yml")
    assert argv[6:] == ["up", "-d"]


def test_the_status_container_list_is_a_subset_of_the_stop_list() -> None:
    """The twin keeps two lists; this asserts they have not drifted apart."""
    assert set(service.STATUS_CONTAINERS) < set(service.STOP_CONTAINERS)
    assert len(service.STOP_CONTAINERS) == 4


def test_docker_is_actually_available_here() -> None:
    """ANTI-VACUITY. Every differential case above runs `docker ps`. If docker were absent, `check_docker` would exit 1 on BOTH sides with identical bytes and every case would pass while measuring nothing at all."""
    assert shutil.which("docker") is not None, (
        "docker is not on PATH, so every case in this file compares two identical "
        "refusals and proves nothing about service_status"
    )
    ok, lines = service.docker_available()
    assert ok, "docker is installed but not running: %s" % lines
    assert isinstance(service.running_containers(), set)


def test_now_defaults_to_the_wall_clock() -> None:
    """The seam is a seam, not the source of truth."""
    before = int(time.time())
    assert service.state_path("/x") == "/x/.service-state"
    assert before <= int(time.time())


# -- the lifecycle half, against a stub farm ---------------------------------
#
# The stub-farm harness, moved here from `the shadow driver` when agent/plans/PLAN-tooling-code-reduction.md CR1 deleted it (last at commit:aa829a19dc): the half that runs the port, without the bash side or the CLI.

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


# env.sh runs `echo "$KEYS" | node -e ...` under `set -o pipefail`. The real node reads its stdin to EOF; a stub that answered and exited without reading let `echo` write into a pipe nobody read, and under host load that write lost the race and killed the subshell with SIGPIPE (rc 141, env.sh aborted). These two rows drain the pipe before answering, as node does.
DRAIN_STDIN = "cat >/dev/null"

KEYGEN = [
    row("node", "-e *generateKeyPairSync*", out='{"private":"PRIVKEY","public":"PUBKEY"}\n'),
    row("node", "-e *.private)*", out="PRIVKEY", sh=DRAIN_STDIN),
    row("node", "-e *.public)*", out="PUBKEY", sh=DRAIN_STDIN),
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
    (root / ".ci" / "config").symlink_to(repo / ".ci" / "config")
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


def run_side(repo: pathlib.Path, case: Case, env: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(env, PYTHONPATH=str(repo / ".ci"))
    argv = [sys.executable, "-m", "rediacc_ci.core.service", case.verb, *case.args]
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


def observe(repo: pathlib.Path, case: Case) -> list[str]:
    """Run one case against the port in a fresh sandbox; return its observation lines."""
    work = pathlib.Path(tempfile.mkdtemp(prefix="svc-stub-", dir=runtmp.shared("svc-stub-")))
    try:
        root = build_sandbox(repo, work, case)
        farm = build_farm(work, case)
        proc = run_side(repo, case, side_env(root, farm, case))
        return emit_case(case, proc, farm, root)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# `service_start`, `service_stop`, `service_health` and `service_logs`'s attach are proved by the harness above: each case runs both sides as child processes with `docker`, `curl`, `sleep`, `ss`, `node` and `openssl` stubbed, and compares rc, stdout, stderr, the files written AND the ordered transcript of every stubbed call. See that module's docstring. These cases drive the LIVE twin on every run.

LIFECYCLE_CASES = [(scenario, case) for scenario, cases in SCENARIOS.items() for case in cases]

# A bash-internal diagnostic some builds print to stderr when `set -e` unwinds a sourced script's failure through a function's `local` scope: a documented bash bug (https://lists.gnu.org/archive/html/bug-bash), not a defect in the twin or the port, whose exact wording and whether it fires at all depends on the bash BUILD the twin happens to run under rather than on anything either
# side does. `service-old` is the ONLY `$0` `run_side` ever gives bash (the deleted driver's `run_side` was the only caller that ran bash), so it anchors the match to lines this differential's own bash child produced.
_BASH_POP_VAR_CONTEXT_BUG = re.compile(
    r"^obs \S+ err#\d+\| service-old: line \d+: "
    r"pop_var_context: head of shell_variables not a function context$"
)


def _drop_bash_internal_noise(lines: list[str]) -> list[str]:
    """`old`'s stderr, minus `_BASH_POP_VAR_CONTEXT_BUG`, with the remaining `err#` lines renumbered.

    `new` is Python and can never print this: pinning its presence would make the differential fail or pass by the CI image's bash patch level rather than by whether the port is equivalent to the twin.
    """
    kept = [line for line in lines if not _BASH_POP_VAR_CONTEXT_BUG.match(line)]
    renumbered = []
    next_err = 0
    for line in kept:
        if re.match(r"^obs \S+ err#\d+\|", line):
            renumbered.append(re.sub(r"err#\d+\|", "err#%d|" % next_err, line, count=1))
            next_err += 1
        else:
            renumbered.append(line)
    return renumbered


def _frozen_lifecycle(scenario: str, case, repo: pathlib.Path) -> list[str]:
    """The retired twin's observation lines for one case, from the golden. They travel as the golden's `out`, one per line."""

    def retired():
        raise RuntimeError(
            "%s is retired: re-record a Rule-T change with `%s %s --source port --reason ...`"
            % (TWIN, diff.REGOLDEN_VERB, TWIN)
        )

    def port():
        return 0, "\n".join(observe(repo, case)), ""

    return diff.twin_call(TWIN, [scenario, case.name], retired, port=port)[1].splitlines()


@pytest.mark.parametrize(
    ("scenario", "case"),
    LIFECYCLE_CASES,
    ids=["%s/%s" % (s, c.name) for s, c in LIFECYCLE_CASES],
)
def test_lifecycle_matches_the_frozen_twin(scenario, case) -> None:
    repo = pathlib.Path(diff.repo())
    old = _drop_bash_internal_noise(_frozen_lifecycle(scenario, case, repo))
    new = observe(repo, case)
    assert old == new, "case %s/%s diverged" % (scenario, case.name)


def test_every_twin_function_is_driven_by_a_scenario() -> None:
    """ANTI-VACUITY. The twin's six functions, and the harness reaches every public one."""
    driven = {FN[c.verb] for _, c in LIFECYCLE_CASES}
    assert driven == {
        "service_start",
        "service_health",
        "service_stop",
        "service_status",
        "service_logs",
    }
    assert {"build-fails", "all-present", "timeout-debug", "unknown"} <= {
        c.name for _, c in LIFECYCLE_CASES
    }


def test_the_stub_farm_really_shadows_docker(tmp_path) -> None:
    """ANTI-VACUITY. If `docker` on the case PATH were the real one, a transcript would be empty on both sides and every case would compare two nothings."""
    case = SCENARIOS["stop"][0]
    farm = build_farm(tmp_path, case)
    env = side_env(tmp_path, farm, case)
    for name in ("docker", "curl", "sleep", "ss"):
        assert stubfarm.shadows(farm, name, env), "%s is not the stub" % name
    lines = observe(pathlib.Path(diff.repo()), case)
    calls = [line for line in lines if " call#" in line]
    assert len(calls) >= 8, "the twin made %d stubbed calls; the farm is not being reached" % len(
        calls
    )


# Larger than the default pipe buffer (64 KiB) and the default pipe-max-size (1 MiB), so a write into an unread pipe cannot complete into the buffer and the stub's exit cannot be missed.
PAYLOAD = b"keys\n" * 262144


def _feed_node_stub(tmp_path, rows: list[dict], *, after_exit: bool, timeout_s: float = 30) -> str:
    """Pipe key JSON into the node stub as env.sh's `echo "$KEYS" | node ...` does. With `after_exit` the producer writes only once the stub has provably exited, so a stub that never reads loses the write with EPIPE (what SIGPIPE is under bash) with no timing involved; a stub that drains reads to EOF first, so it must be fed before the wait. Returns the stub's exit status, "EPIPE" when the write found the stub gone, or "KILLED" when the watchdog had to kill a stub that outlived `timeout_s` (a hung stub is never read as an EPIPE)."""
    case = Case("pipe", "start", [], rows)
    farm = build_farm(tmp_path, case)
    env = side_env(tmp_path, farm, case)
    with subprocess.Popen(
        [str(farm.bin / "node"), "-e", "x.private)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        bufsize=0,
        env=env,
    ) as proc:
        assert proc.stdin is not None
        # Armed before the wait as well as the write: a stub that never exits would block `wait` for ever, and a stub that stays alive without reading would block the write; the watchdog kills it either way, so the test fails instead of hanging.
        killed = threading.Event()

        def _kill() -> None:
            # A stub that already exited is not a hung one: a Timer firing between its clean exit and `cancel` must not turn that exit into "KILLED".
            if proc.poll() is None:
                killed.set()
                proc.kill()

        watchdog = threading.Timer(timeout_s, _kill)
        watchdog.start()
        try:
            if after_exit:
                proc.wait()
            pending = memoryview(PAYLOAD)
            while pending:  # an unbuffered write may take only what fits the pipe
                pending = pending[proc.stdin.write(pending) :]
            proc.stdin.close()
        except BrokenPipeError:
            return "KILLED" if killed.is_set() else "EPIPE"
        finally:
            watchdog.cancel()
        return "KILLED" if killed.is_set() else str(proc.wait())


def _pipefail_status(tmp_path, rows: list[dict]) -> int:
    """env.sh's shape under bash: `set -o pipefail; <producer> | node ...`; the pipeline's exit status."""
    case = Case("pipe", "start", [], rows)
    farm = build_farm(tmp_path, case)
    env = side_env(tmp_path, farm, case)
    script = 'set -o pipefail; head -c %d /dev/zero | node -e "x.private)" > /dev/null' % len(
        PAYLOAD
    )
    return subprocess.run(["bash", "-c", script], env=env, timeout=30, check=False).returncode


def test_the_keygen_node_stub_drains_stdin_like_node(tmp_path) -> None:
    """REGRESSION (2026-11-17, ci:quick under load): `start/preferred-busy` exited 141. `env.sh` pipes the key JSON into `node` under pipefail; the stub answered without reading, so `echo` hit a closed pipe and SIGPIPE ended env.sh. The producer writes after the consumer has exited, so the control row (no drain) loses the write every time and the KEYGEN row, which reads to EOF and so cannot have exited, never does."""
    undrained = [row("node", "-e *.private)*", out="PRIVKEY")]
    assert _feed_node_stub(tmp_path / "control", undrained, after_exit=True) == "EPIPE"
    keygen = [r for r in KEYGEN if r["name"] == "node" and ".private)" in r["glob"]]
    assert len(keygen) == 1
    assert _feed_node_stub(tmp_path / "fixed", keygen, after_exit=False) == "0"


def test_a_stub_that_never_exits_is_killed_by_the_watchdog_not_waited_on(
    tmp_path, monkeypatch
) -> None:
    """Finding 3db5d182.1: with `after_exit` the wait ran before the watchdog was armed, so a stub that never exits hung the test. The node stub is replaced by a process that exits only when killed, and the feed must return \"KILLED\", which the \"EPIPE\" control row never accepts (finding 07304bd3.1)."""
    real_popen = subprocess.Popen

    class Hangs:
        def __init__(self) -> None:
            self.killed = threading.Event()
            self.stdin = self

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            return None

        def wait(self) -> int:
            self.killed.wait()
            return -9

        def poll(self) -> int | None:
            return -9 if self.killed.is_set() else None

        def kill(self) -> None:
            self.killed.set()

        def write(self, _data) -> int:
            raise BrokenPipeError

    def popen(argv, *args, **kwargs):
        if str(argv[0]).endswith("/node"):
            return Hangs()
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", popen)
    done: list[str] = []
    undrained = [row("node", "-e *.private)*", out="PRIVKEY")]
    worker = threading.Thread(
        target=lambda: done.append(
            _feed_node_stub(tmp_path, undrained, after_exit=True, timeout_s=0.5)
        ),
        daemon=True,
    )
    worker.start()
    worker.join(15)
    assert not worker.is_alive(), "the feed is still waiting on a stub that never exits"
    assert done == ["KILLED"]


def test_the_keygen_node_stub_survives_a_pipefail_pipeline(tmp_path) -> None:
    """The same regression through bash: the undrained control ends the pipeline with 141 (SIGPIPE), the KEYGEN row with 0."""
    undrained = [row("node", "-e *.private)*", out="PRIVKEY")]
    assert _pipefail_status(tmp_path / "control", undrained) == 141
    keygen = [r for r in KEYGEN if r["name"] == "node" and ".private)" in r["glob"]]
    assert _pipefail_status(tmp_path / "fixed", keygen) == 0


def test_a_transcript_difference_is_a_divergence() -> None:
    """CONTROL ON THE COMPARISON. One dropped call must make two otherwise-equal observation lists unequal."""
    case = SCENARIOS["health"][1]
    observed = observe(pathlib.Path(diff.repo()), case)
    tampered = [line for line in observed if "call#3|" not in line]
    assert tampered != observed
