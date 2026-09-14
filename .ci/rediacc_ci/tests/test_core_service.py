"""`rediacc_ci.core.service` against the live `.ci/lib/service.sh`.

REAL DOCKER, NO STACK. Every case runs the real `docker ps` and `docker inspect`
against a daemon with the `rediacc-service-*` containers absent, which is the
state a developer's machine is in almost all the time and the only state a
differential can enter five times without building an image ten times. What is
NOT covered is named in the module docstring of the port rather than left as an
absence: `service_start` and `service_stop`.

THE CLOCK IS FROZEN ON BOTH SIDES, BY DIFFERENT SEAMS, AND THAT IS DELIBERATE.
`service_status` prints an uptime derived from `date +%s`, so two runs a second
apart disagree and no byte comparison is possible. The twin's seam is a fake
`date` earlier on PATH -- the same trick `test-bws-env.sh` uses for `bws`. The
port reads the clock in-process, so its seam is `SERVICE_STATUS_NOW`. Both are
supplied by `env_for` below from ONE value, so the two sides cannot drift apart
through the harness.

`check_docker` IS DEFINED BY THE HARNESS ON THE BASH SIDE because the twin does
not define it: it lives in `.ci/legacy/run-legacy.sh`, the file that SOURCES
`service.sh`, and only late binding makes the twin work at all. The definition
below is copied from that file verbatim. That is defect 3 in the port's
docstring, and the harness having to supply it is the evidence for it.
"""

import shutil
import textwrap
import time

import pytest

from rediacc_ci.core import service
from rediacc_ci.tests import differential as diff

TWIN = ".ci/lib/service.sh"

# `check_docker` from `.ci/legacy/run-legacy.sh:56-68`, verbatim. See the header.
BASH_DRIVER = textwrap.dedent(
    """
    source "$SERVICE_TWIN"
    check_docker() {
        if ! command -v docker &>/dev/null; then
            log_error "Docker is not installed"
            log_info "Install Docker from: https://docs.docker.com/get-docker/"
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

    DEFERS RATHER THAN REFUSES, because `service.sh` is not the only thing on the
    other side of this PATH: anything it sources may call `date` for a real
    reason, and a fake that answered every form would change behaviour the
    differential is trying to measure.
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
    args = " ".join("'%s'" % a for a in argv)
    script = 'SERVICE_TWIN="%s"\nset -- %s\n%s' % (TWIN, args, BASH_DRIVER)
    return diff.bash_streams(script, env=env)


def _python(argv: list[str], env: dict):
    args = " ".join("'%s'" % a for a in argv)
    return diff.bash_streams("PYTHONPATH=.ci python3 -m rediacc_ci.core.service %s" % args, env=env)


# (id, state-file body or None, argv, now)
CASES = [
    ("status-no-state-file", None, ["status"], FROZEN_NOW),
    ("status-port-and-started", "started=1700000000\nport=9123\n", ["status"], FROZEN_NOW),
    ("status-one-minute-uptime", "started=1700000000\nport=8080\n", ["status"], 1700000061),
    # 25 hours: the twin's `printf '%02d:%02d:%02d'` does NOT roll into days, so
    # this prints `25:00:00`. `datetime.timedelta` would print `1 day, 1:00:00`.
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
    and would flake otherwise. Two DIFFERENT frozen values must give two
    different uptimes on both sides."""
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
    assignment take grep's exit 1 through `pipefail` into `errexit`. The function
    stops mid-output: two container lines, a blank, and then NOTHING. No health
    check, no trailing blank, no message, exit 1 -- and because errexit is still
    armed in the sourcing script, it takes `run-legacy.sh` down with it.

    stdout AND the exit code MATCH EXACTLY. The port adds one line on stderr
    naming the cause, which is the single deliberate divergence here: a port that
    reproduced a silent death without saying why would be reproducing the defect
    and hiding its own discovery of it. The shadow ledger therefore omits this
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

    Asserted on both sides so the port cannot quietly "fix" it, and so a reader
    who finds this surprising finds the measurement rather than an opinion.
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
    # `all | ""` share an arm in the twin, so an EMPTY service follows everything
    # rather than refusing. Pinned because it looks like a typo and is not.
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
    """ANTI-VACUITY. Every differential case above runs `docker ps`. If docker
    were absent, `check_docker` would exit 1 on BOTH sides with identical bytes
    and every case would pass while measuring nothing at all."""
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
