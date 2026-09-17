"""`rediacc_ci.core.dockerx` against fake `docker` binaries, in both directions.

WHAT THIS FILE IS REALLY TESTING. Not "does the wrapper call docker" -- that is
trivially true and worth nothing. It is testing the three-way distinction the
module exists for: a machine with no docker, a machine whose docker cannot reach
an engine, and a command that reached an engine and failed. Every real spelling
in this tree flattens at least two of those together, and the flattening is
invisible because all three exit 1.

THE FAKES ARE DRIVEN BY FROZEN MEASUREMENTS. Every stdout and stderr asserted
below was captured from the real docker 29.7.2 on this host on 2026-09-06, and
the capture command sits beside each one. That matters more here than usual: the
central case is that `docker info` prints a FULL, HEALTHY-LOOKING client report
on stdout while failing, and a hand-invented fixture would never have thought to
do that.

EVERY LOAD-BEARING CASE HAS A CONTROL. Each `_assert_*` helper is called twice:
once against the module as written, and once with a defect planted into it --
the classifier collapsed, the state probe made naive -- which must make the same
assertion fail. Where the naive alternative is a shell one-liner rather than a
Python function, the control RUNS that one-liner against the same fake and
asserts it reaches the wrong conclusion.
"""

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from rediacc_ci import paths, proc
from rediacc_ci.core import dockerx
from rediacc_ci.tests import differential as diff

# --------------------------------------------------------------------------- THE FROZEN MEASUREMENTS, docker 29.7.2, 2026-09-06 ---------------------------------------------------------------------------

# DOCKER_HOST=unix:///nonexistent/docker.sock docker version   -> exit 1
# DOCKER_HOST=unix:///nonexistent/docker.sock docker info      -> exit 1
# DOCKER_HOST=unix:///nonexistent/docker.sock docker ps        -> exit 1
# All three print this identical line on stderr and nothing else.
MEASURED_UNREACHABLE_STDERR = (
    "failed to connect to the docker API at unix:///nonexistent/docker.sock; check if "
    "the path is correct and if the daemon is running: dial unix "
    "/nonexistent/docker.sock: connect: no such file or directory\n"
)

# The stdout of that same failing `docker info`, abridged. THE REAL ONE IS 52 LINES: a complete Client section listing eight cli-plugins with versions and paths, then a blank line, then a bare "Server:" with nothing under it. The shape is what matters and the shape is preserved: plenty of confident output, and the one section that would have said whether an engine exists is empty.
MEASURED_INFO_STDOUT_WHEN_UNREACHABLE = (
    "Client:\n"
    " Version:    29.7.2\n"
    " Context:    default\n"
    " Debug Mode: false\n"
    " Plugins:\n"
    "  buildx: Docker Buildx (Docker Inc.)\n"
    "    Version:  v0.36.1-desktop.1\n"
    "    Path:     /usr/local/lib/docker/cli-plugins/docker-buildx\n"
    "\n"
    "Server:\n"
)

# docker frobnicate  -> exit 1. The engine was never contacted; this is a usage
# error, and it must NOT be classified as "cannot run".
MEASURED_UNKNOWN_VERB_STDERR = (
    "docker: unknown command: docker frobnicate\n\nRun 'docker --help' for more information\n"
)

# docker --version -> exit 0 EVEN WITH NO DAEMON (measured with the same bogus DOCKER_HOST). This is why client_version() uses it.
MEASURED_VERSION_LINE = "Docker version 29.7.2, build a7dcaa6\n"

# The classic socket-permission message, which is the DENIED case. It contains "connect to the Docker daemon socket", so an unreachable-first classifier reads it as a dead engine and tells the operator to start one that is already up.
MEASURED_DENIED_STDERR = (
    "permission denied while trying to connect to the Docker daemon socket at "
    'unix:///var/run/docker.sock: Get "http://%2Fvar%2Frun%2Fdocker.sock/_ping": '
    "dial unix /var/run/docker.sock: connect: permission denied\n"
)

VERSION_OK_STDOUT = (
    "Client: Docker Engine - Community\n Version: 29.7.2\nServer:\n Version: 29.7.2\n"
)


# --------------------------------------------------------------------------- The fake binary ---------------------------------------------------------------------------


@pytest.fixture
def fake_bin(tmp_path, monkeypatch):
    """A factory that puts an executable of our own making on PATH, alone.

    PATH IS REPLACED, so the ABSENT case is a directory with no `docker` in it
    and no real binary can leak into any case. The fakes are PYTHON scripts with
    an absolute shebang rather than `#!/bin/sh` bodies calling `cat`, because a
    replaced PATH also hides `cat` -- and that failure is silent in the worst
    way: the fake exits 0 having printed nothing, which reads exactly like the
    empty answer these cases exist to tell apart from a real one.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    monkeypatch.setenv("PATH", str(bindir))
    counter = {"n": 0}

    def make(
        name: str = "docker",
        *,
        stdout: str = "",
        stderr: str = "",
        rc: int = 0,
        per_verb: dict | None = None,
    ) -> pathlib.Path:
        """A fake docker.

        `per_verb` maps a matcher string (matched against the joined argv) to a
        (stdout, stderr, rc) triple, which is how one binary can answer
        `docker --version` and `docker version` differently -- the exact
        asymmetry MEASUREMENT 3 in the module is about.
        """
        counter["n"] += 1
        table = {"": (stdout, stderr, rc), **(per_verb or {})}
        payload = tmp_path / ("fake-%d.json" % counter["n"])
        payload.write_text(json.dumps(table), encoding="utf-8")
        path = bindir / name
        path.write_text(
            "#!" + sys.executable + "\n"
            "import json, sys\n"
            "table = json.load(open(" + repr(str(payload)) + ", encoding='utf-8'))\n"
            "joined = ' '.join(sys.argv[1:])\n"
            "chosen = table['']\n"
            "for key in sorted(table, key=len, reverse=True):\n"
            "    if key and key in joined:\n"
            "        chosen = table[key]\n"
            "        break\n"
            "sys.stdout.write(chosen[0])\n"
            "sys.stderr.write(chosen[1])\n"
            "sys.exit(chosen[2])\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    make.bindir = bindir
    make.tmp = tmp_path
    return make


def unreachable(make) -> None:
    """A docker whose CLI works and whose engine does not. The measured shape."""
    make(
        stdout="",
        stderr=MEASURED_UNREACHABLE_STDERR,
        rc=1,
        per_verb={
            "--version": (MEASURED_VERSION_LINE, "", 0),
            "info": (MEASURED_INFO_STDOUT_WHEN_UNREACHABLE, MEASURED_UNREACHABLE_STDERR, 1),
        },
    )


def ready(make, *, ps_body: str = "") -> None:
    """A docker with a live engine."""
    make(
        stdout=VERSION_OK_STDOUT,
        rc=0,
        per_verb={
            "--version": (MEASURED_VERSION_LINE, "", 0),
            "ps": (ps_body, "", 0),
            "version --format": ("29.7.2\n", "", 0),
        },
    )


# --------------------------------------------------------------------------- ANTI-VACUITY ---------------------------------------------------------------------------


def test_the_fake_docker_is_the_one_that_runs(fake_bin):
    ready(fake_bin)
    resolved = dockerx.which_docker()
    assert resolved is not None
    assert resolved.startswith(str(fake_bin.bindir))
    assert dockerx.client_version() == "29.7.2"


@pytest.mark.usefixtures("fake_bin")
def test_an_empty_path_really_does_hide_the_binary():
    assert dockerx.which_docker() is None
    assert dockerx.docker(["version"]).returncode == dockerx.NOT_INSTALLED_RC


def test_the_per_verb_fake_really_distinguishes_verbs(fake_bin):
    """The fixture's own control. Every MEASUREMENT-3 case depends on one binary
    answering two verbs differently, so that mechanism is asserted before it is
    relied on."""
    unreachable(fake_bin)
    assert dockerx.docker(["--version"]).ok is True
    assert dockerx.docker(["version"]).ok is False


# --------------------------------------------------------------------------- The three-way distinction ---------------------------------------------------------------------------


def _assert_the_four_states(fake_bin):
    """Absent, unreachable, denied and ready are four different answers."""
    assert dockerx.state() == dockerx.STATE_ABSENT

    unreachable(fake_bin)
    assert dockerx.state() == dockerx.STATE_UNREACHABLE

    fake_bin(stderr=MEASURED_DENIED_STDERR, rc=1)
    assert dockerx.state() == dockerx.STATE_DENIED

    ready(fake_bin)
    assert dockerx.state() == dockerx.STATE_READY


def test_the_four_states_are_four_answers(fake_bin):
    _assert_the_four_states(fake_bin)


def test_control_collapsing_the_classifier_breaks_the_four_states(fake_bin, monkeypatch):
    """PLANTED DEFECT: `_classify` always says "the command failed", which is what
    every `docker info >/dev/null 2>&1 || return 1` site effectively does. The
    assertion above must stop holding."""

    def collapsed(returncode, stderr, *, timed_out):
        """Every failure is "the command failed", which is what a bare
        `docker info >/dev/null 2>&1 || return 1` amounts to."""
        assert isinstance(returncode, int)
        assert isinstance(stderr, str)
        assert timed_out in (True, False)
        return dockerx.FAILURE_FAILED

    monkeypatch.setattr(dockerx, "_classify", collapsed)
    with pytest.raises(AssertionError):
        _assert_the_four_states(fake_bin)


def test_permission_denied_is_not_reported_as_unreachable(fake_bin):
    """The message contains "connect to the Docker daemon socket", so a classifier
    that tests the unreachable markers first sends the operator to restart an
    engine that is already running."""
    fake_bin(stderr=MEASURED_DENIED_STDERR, rc=1)
    result = dockerx.docker(["ps"])
    assert result.failure == dockerx.FAILURE_DENIED
    with pytest.raises(dockerx.DockerPermissionDeniedError):
        _ = result.stdout


def test_control_removing_the_denied_markers_misfiles_it_as_unreachable(fake_bin, monkeypatch):
    """PLANTED DEFECT that proves the ordering above is load bearing rather than
    incidental: with the DENIED table emptied, the same stderr lands on
    UNREACHABLE, which is the wrong advice."""
    monkeypatch.setattr(dockerx, "_DENIED_MARKERS", ())
    monkeypatch.setattr(dockerx, "_DENIED_WEAK_MARKERS", ())
    monkeypatch.setattr(dockerx, "_UNREACHABLE_MARKERS", ("connect to the docker daemon",))
    fake_bin(stderr=MEASURED_DENIED_STDERR, rc=1)
    assert dockerx.docker(["ps"]).failure == dockerx.FAILURE_UNREACHABLE


def _assert_a_bad_command_is_a_finding_not_a_shrug(fake_bin):
    fake_bin(stderr=MEASURED_UNKNOWN_VERB_STDERR, rc=1)
    result = dockerx.docker(["frobnicate"])
    assert result.failure == dockerx.FAILURE_FAILED
    assert result.cannot_run is False


def test_a_command_that_reached_the_engine_and_failed_is_a_finding(fake_bin):
    """THE LINE THAT MAKES 77 MEAN SOMETHING. `docker frobnicate` exits 1 exactly
    like an unreachable daemon does, and it must not be excused."""
    _assert_a_bad_command_is_a_finding_not_a_shrug(fake_bin)


def test_control_treating_every_failure_as_cannot_run_breaks_that(fake_bin, monkeypatch):
    """PLANTED DEFECT: `cannot_run` made unconditional, which is what a gate that
    exits 77 on any docker failure would do. It converts a red into a shrug, and
    the assertion above must catch it."""
    monkeypatch.setattr(dockerx.DockerResult, "cannot_run", property(lambda self: not self.ok))
    with pytest.raises(AssertionError):
        _assert_a_bad_command_is_a_finding_not_a_shrug(fake_bin)


def test_cannot_run_states_excludes_the_verdicts():
    """Set-based rather than a count: the two failures that ARE verdicts must not
    be in the cannot-run set, whatever else joins it later."""
    assert dockerx.FAILURE_FAILED not in dockerx.CANNOT_RUN_STATES
    assert dockerx.FAILURE_TIMED_OUT not in dockerx.CANNOT_RUN_STATES
    assert {
        dockerx.STATE_ABSENT,
        dockerx.STATE_UNREACHABLE,
        dockerx.STATE_DENIED,
        dockerx.STATE_UNKNOWN,
    } == dockerx.CANNOT_RUN_STATES


def test_an_unclassifiable_failure_is_unknown_and_not_invented(fake_bin):
    fake_bin(stderr="something nobody has ever seen\n", rc=1)
    assert dockerx.state() == dockerx.STATE_UNKNOWN
    reason = dockerx.cannot_run_reason()
    assert reason is not None
    assert "could not classify" in reason


# --------------------------------------------------------------------------- MEASUREMENT 2: docker info lies confidently on stdout ---------------------------------------------------------------------------

# What a probe written as "did it print anything" looks like in shell. Not a strawman: `.ci/scripts/quality/check-setup-idempotency.sh` and several sibling scripts key on docker output, and the only thing keeping them honest is that they happen to test the status too.
NAIVE_OUTPUT_PROBE = "docker info 2>/dev/null | grep -q . && echo HEALTHY || echo DEAD"


def test_the_naive_output_probe_calls_a_dead_engine_healthy(fake_bin):
    """THE CONTROL FOR THE WHOLE MODULE, run rather than described."""
    unreachable(fake_bin)
    rc, out, _err = diff.bash_streams(
        NAIVE_OUTPUT_PROBE,
        env=diff.env_for(PATH="%s:%s" % (fake_bin.bindir, diff.BASE_ENV["PATH"])),
    )
    assert rc == 0
    assert out.strip() == "HEALTHY"


def test_the_module_calls_the_same_engine_unreachable(fake_bin):
    """The other direction, against the identical binary."""
    unreachable(fake_bin)
    assert dockerx.state() == dockerx.STATE_UNREACHABLE
    with pytest.raises(dockerx.DockerUnreachableError):
        _ = dockerx.docker(["info"]).stdout


def test_the_confident_stdout_is_still_reachable_for_diagnosis(fake_bin):
    """`.stdout_raw` keeps the bytes. Refusing to hand them over as an ANSWER is
    not the same as destroying them, and the client report is genuinely useful
    when a human is working out why the socket is missing."""
    unreachable(fake_bin)
    result = dockerx.docker(["info"])
    assert result.stdout_raw.startswith("Client:")
    assert result.stdout_raw.rstrip().endswith("Server:")
    assert result.stderr == MEASURED_UNREACHABLE_STDERR


# --------------------------------------------------------------------------- MEASUREMENT 3: the spelling that forces you to skip the check ---------------------------------------------------------------------------


def test_client_version_works_without_an_engine_and_still_checks_status(fake_bin):
    unreachable(fake_bin)
    assert dockerx.client_version() == "29.7.2"


def test_the_rejected_spelling_really_does_fail_while_printing_the_answer(fake_bin):
    """Why `client_version` does not use `docker version --format ...`.

    The fake reproduces the measured asymmetry: the Client field is printed and
    the call exits non-zero, so the only way to consume it is to ignore the exit
    code. Asserted here so the choice in the module is anchored to a behaviour
    rather than to a preference.
    """
    fake_bin(
        stdout="",
        stderr=MEASURED_UNREACHABLE_STDERR,
        rc=1,
        per_verb={
            "--version": (MEASURED_VERSION_LINE, "", 0),
            "version --format {{.Client.Version}}": ("29.7.2\n", MEASURED_UNREACHABLE_STDERR, 1),
        },
    )
    rejected = dockerx.docker(["version", "--format", "{{.Client.Version}}"])
    assert rejected.ok is False
    assert rejected.stdout_raw.strip() == "29.7.2"
    # And the accepted spelling gets there without breaking the rule.
    assert dockerx.client_version() == "29.7.2"


def test_an_unparseable_version_line_is_refused_rather_than_returned(fake_bin):
    fake_bin(per_verb={"--version": ("Docker version\n", "", 0)}, stdout="", rc=0)
    with pytest.raises(dockerx.DockerBadOutputError, match="cannot read a version"):
        dockerx.client_version()


def test_server_version_raises_instead_of_saying_unknown(fake_bin):
    """`.ci/lib/setup.sh:583` answers "version unknown" here, which is right for a
    log line and wrong for anything a program compares."""
    unreachable(fake_bin)
    with pytest.raises(dockerx.DockerUnreachableError):
        dockerx.server_version()
    ready(fake_bin)
    assert dockerx.server_version() == "29.7.2"


# --------------------------------------------------------------------------- Output that must not be trusted unchecked ---------------------------------------------------------------------------


def test_stdout_raises_on_a_failed_call():
    result = dockerx.DockerResult(["docker", "x"], 1, "looks fine", "boom")
    with pytest.raises(dockerx.DockerError):
        _ = result.stdout
    assert result.stdout_raw == "looks fine"
    assert result.stderr == "boom"


def test_every_output_accessor_routes_through_the_raising_property():
    result = dockerx.DockerResult(["docker", "x"], 1, "{}", "boom")
    accessors = {
        name
        for name in dir(dockerx.DockerResult)
        if not name.startswith("_")
        and name not in set(dockerx.DockerResult.__slots__)
        and name not in {"ok", "failure", "error", "cannot_run"}
    }
    assert accessors == {"stdout", "lines", "value", "json", "json_lines"}
    for name in sorted(accessors):
        attribute = getattr(dockerx.DockerResult, name)
        with pytest.raises(dockerx.DockerError):
            _ = getattr(result, name)() if callable(attribute) else getattr(result, name)


def test_error_refuses_to_describe_a_success():
    result = dockerx.DockerResult(["docker", "x"], 0, "fine", "")
    assert result.failure is None
    with pytest.raises(ValueError, match="successful"):
        result.error()


TWO_CONTAINERS = '{"Names":"beta","ID":"2"}\n{"Names":"alpha","ID":"1"}\n'
ONE_CONTAINER = '{"Names":"solo","ID":"1"}\n'


def test_docker_ps_is_newline_delimited_json_and_is_parsed_as_such(fake_bin):
    ready(fake_bin, ps_body=TWO_CONTAINERS)
    assert dockerx.container_names() == ["alpha", "beta"]


def test_control_the_whole_body_parse_passes_with_one_container_and_fails_with_two(fake_bin):
    """WHY THAT BUG SHIPS. `json.loads(body)` is correct for zero or one
    container and wrong for two, so it passes every hand-run test and fails the
    first time a second container exists. Both halves asserted."""
    ready(fake_bin, ps_body=ONE_CONTAINER)
    assert json.loads(dockerx.docker(["ps", "--format", "{{json .}}"]).stdout_raw) == {
        "Names": "solo",
        "ID": "1",
    }
    ready(fake_bin, ps_body=TWO_CONTAINERS)
    with pytest.raises(json.JSONDecodeError, match="Extra data"):
        json.loads(dockerx.docker(["ps", "--format", "{{json .}}"]).stdout_raw)
    # And the module gets it right on the same bytes.
    assert dockerx.container_names() == ["alpha", "beta"]


def test_containers_raises_when_the_engine_cannot_be_asked(fake_bin):
    unreachable(fake_bin)
    with pytest.raises(dockerx.DockerUnreachableError):
        dockerx.containers()


def test_containers_returns_empty_when_there_are_genuinely_none(fake_bin):
    ready(fake_bin, ps_body="")
    assert dockerx.containers() == []


def test_a_non_object_line_is_refused(fake_bin):
    ready(fake_bin, ps_body='["not","an","object"]\n')
    with pytest.raises(dockerx.DockerBadOutputError, match="object per line"):
        dockerx.containers()


# --------------------------------------------------------------------------- The environment, and DOCKER_HOST scoping ---------------------------------------------------------------------------


def test_the_host_argument_does_not_leak_into_this_process(fake_bin, tmp_path, monkeypatch):
    """Each repo in this product has its own daemon socket. Setting DOCKER_HOST
    for one call must not retarget the next one."""
    bindir = fake_bin.bindir
    env_log = tmp_path / "env.log"
    path = bindir / "docker"
    path.write_text(
        "#!" + sys.executable + "\n"
        "import os, sys\n"
        "open(" + repr(str(env_log)) + ", 'a', encoding='utf-8')"
        ".write(os.environ.get('DOCKER_HOST', '(unset)') + '\\n')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    monkeypatch.delenv("DOCKER_HOST", raising=False)

    dockerx.docker(["ps"], host="unix:///var/run/rediacc/docker-7.sock")
    dockerx.docker(["ps"])
    assert env_log.read_text(encoding="utf-8").splitlines() == [
        "unix:///var/run/rediacc/docker-7.sock",
        "(unset)",
    ]
    assert "DOCKER_HOST" not in os.environ


def test_the_noninteractive_environment_reaches_the_child(fake_bin, tmp_path):
    env_log = tmp_path / "env2.log"
    path = fake_bin.bindir / "docker"
    path.write_text(
        "#!" + sys.executable + "\n"
        "import os, sys\n"
        "open(" + repr(str(env_log)) + ", 'w', encoding='utf-8')"
        ".write('\\n'.join('%s=%s' % kv for kv in os.environ.items()))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    dockerx.docker(["ps"])
    seen = dict(
        line.split("=", 1)
        for line in env_log.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert {k: seen.get(k) for k in dockerx.NONINTERACTIVE} == dockerx.NONINTERACTIVE


def test_retries_follow_the_documented_backoff(fake_bin):
    unreachable(fake_bin)
    slept: list[float] = []
    result = dockerx.docker(["ps"], attempts=3, sleep=slept.append)
    assert slept == proc.backoff_delays(3)
    assert result.failure == dockerx.FAILURE_UNREACHABLE


# --------------------------------------------------------------------------- The 77 contract ---------------------------------------------------------------------------


def test_the_cannot_run_code_agrees_with_every_other_definition_in_the_repo():
    """CORPUS-DERIVED, not hand-typed. 77 is written in four places (pool.ts owns
    it, and three consumers duplicate the literal because they cannot import a
    TypeScript constant). This reads them and asserts they all still agree, so
    the day one of them drifts is the day something says so.
    """
    root = paths.repo_root()
    found = {}
    patterns = {
        "scripts/ci-runner/pool.ts": r"const CANNOT_RUN = (\d+)",
        ".ci/rediacc_ci/check_pytest.py": r"EXIT_CANNOT_RUN = (\d+)",
        ".ci/scripts/security/shfmt.sh": r"^\s*exit (\d+)\s*$",
        ".ci/scripts/quality/check-python-lint.sh": r"^\s*exit (\d+)\s*$",
    }
    for rel, pattern in patterns.items():
        text = (root / rel).read_text(encoding="utf-8")
        matches = {int(m) for m in re.findall(pattern, text, re.MULTILINE)}
        assert matches, "no cannot-run literal found in %s; the pattern has rotted" % rel
        found[rel] = matches
    # The two shell files also `exit 0`/`exit 1` elsewhere, so the assertion is membership rather than equality for those, and equality for the two that name the constant.
    assert found["scripts/ci-runner/pool.ts"] == {dockerx.CANNOT_RUN_RC}
    assert found[".ci/rediacc_ci/check_pytest.py"] == {dockerx.CANNOT_RUN_RC}
    assert dockerx.CANNOT_RUN_RC in found[".ci/scripts/security/shfmt.sh"]
    assert dockerx.CANNOT_RUN_RC in found[".ci/scripts/quality/check-python-lint.sh"]


def _module_run(bindir: pathlib.Path, args: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # PATH IS ONLY THE FAKE DIRECTORY. Appending the real PATH here would make the ABSENT case find the developer's real docker through the tail of the list, and the case would pass by testing something else entirely. Nothing the child needs comes from PATH: the interpreter is an absolute path and `paths.repo_root()` is derived from the package's own location.
    env["PATH"] = str(bindir)
    env["PYTHONPATH"] = str(paths.repo_root() / ".ci")
    return subprocess.run(
        [sys.executable, "-m", "rediacc_ci.core.dockerx", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.repo_root()),
        env=env,
        timeout=60,
    )


def _assert_the_77_mapping(fake_bin):
    """ready -> 0, the three cannot-run states -> 77, a bad command -> never 77."""
    ready(fake_bin)
    assert _module_run(fake_bin.bindir, ["require-ready"]).returncode == 0

    unreachable(fake_bin)
    blocked = _module_run(fake_bin.bindir, ["require-ready"])
    assert blocked.returncode == dockerx.CANNOT_RUN_RC
    assert blocked.stdout == ""
    assert "no engine answered" in blocked.stderr
    assert "NOT skipping" in blocked.stderr

    fake_bin(stderr=MEASURED_DENIED_STDERR, rc=1)
    denied = _module_run(fake_bin.bindir, ["require-ready"])
    assert denied.returncode == dockerx.CANNOT_RUN_RC
    assert "sg docker" in denied.stderr

    # ABSENT: a bin directory with no docker in it at all.
    empty = fake_bin.tmp / "empty-bin"
    empty.mkdir(exist_ok=True)
    absent = _module_run(empty, ["require-ready"])
    assert absent.returncode == dockerx.CANNOT_RUN_RC
    assert "not on PATH" in absent.stderr


def test_the_77_mapping(fake_bin):
    _assert_the_77_mapping(fake_bin)


def test_control_a_docker_that_always_succeeds_breaks_the_77_mapping(fake_bin, monkeypatch):
    """PLANTED DEFECT, and the plant has to reach a CHILD process.

    `python -m rediacc_ci.core.dockerx` runs the module source AGAIN under the
    name `__main__`, so patching `rediacc_ci.core.dockerx.state` in a
    sitecustomize does nothing: the running copy is a different module object
    with its own globals. Learned by watching this control fail to fire, which is
    the whole reason a control exists.

    The plant therefore goes one layer down, at `rediacc_ci.proc.retry_command`,
    which BOTH copies import from the same place. Making it always answer
    "exit 0" is exactly the "assume docker is fine" defect: the unreachable case
    then reports ready and exits 0 where the contract demands 77, and the mapping
    assertion must catch it.
    """
    plant_dir = fake_bin.tmp / "plant"
    plant_dir.mkdir()
    (plant_dir / "sitecustomize.py").write_text(
        "from rediacc_ci import proc\n"
        "def _always_ok(argv, **kwargs):\n"
        "    return proc.Result(list(argv), 0, 'Client:\\nServer:\\n Version: 1\\n', '')\n"
        "proc.retry_command = _always_ok\n",
        encoding="utf-8",
    )

    def planted(bindir, args):
        env_path = "%s%s%s" % (plant_dir, os.pathsep, paths.repo_root() / ".ci")
        return subprocess.run(
            [sys.executable, "-m", "rediacc_ci.core.dockerx", *args],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(paths.repo_root()),
            env={**os.environ, "PATH": str(bindir), "PYTHONPATH": env_path},
            timeout=60,
        )

    # The plant must actually be in force, or this control proves nothing.
    unreachable(fake_bin)
    assert planted(fake_bin.bindir, ["state"]).stdout.strip() == dockerx.STATE_READY

    monkeypatch.setitem(globals(), "_module_run", planted)
    with pytest.raises(AssertionError):
        _assert_the_77_mapping(fake_bin)


def test_the_state_verb_always_exits_zero_and_prints_one_word(fake_bin):
    """A caller that wants to branch in shell needs a value, not an exit code."""
    for setup, expected in (
        (ready, dockerx.STATE_READY),
        (unreachable, dockerx.STATE_UNREACHABLE),
    ):
        setup(fake_bin)
        done = _module_run(fake_bin.bindir, ["state"])
        assert done.returncode == 0
        assert done.stdout.strip() == expected
        assert done.stderr == ""


def test_the_server_version_verb_separates_cannot_run_from_a_finding(fake_bin):
    unreachable(fake_bin)
    blocked = _module_run(fake_bin.bindir, ["server-version"])
    assert blocked.returncode == dockerx.CANNOT_RUN_RC

    # A live engine that answers with nothing is a FINDING, not a shrug.
    fake_bin(
        stdout=VERSION_OK_STDOUT,
        rc=0,
        per_verb={"version --format": ("\n", "", 0)},
    )
    finding = _module_run(fake_bin.bindir, ["server-version"])
    assert finding.returncode == 1
    assert finding.returncode != dockerx.CANNOT_RUN_RC
    assert finding.stdout == ""


def test_an_unknown_verb_is_usage_and_not_cannot_run(fake_bin):
    ready(fake_bin)
    done = _module_run(fake_bin.bindir, ["frobnicate"])
    assert done.returncode == 2
    assert "unknown verb" in done.stderr


# --------------------------------------------------------------------------- Hygiene ---------------------------------------------------------------------------


def test_all_names_in_dunder_all_exist():
    missing = {name for name in dockerx.__all__ if not hasattr(dockerx, name)}
    assert missing == set()


def test_every_cannot_run_state_has_operator_advice():
    """Set-based: a state with no advice would print "unusable" and leave the
    reader with nothing to do, which check-python-lint.sh:170-180 records as
    expensive."""
    assert set(dockerx._ADVICE) == dockerx.CANNOT_RUN_STATES
    for state_name, text in dockerx._ADVICE.items():
        assert text.strip(), state_name


def test_no_em_dashes_in_the_module_or_this_file():
    em_dash = chr(8212)
    for path in (
        paths.repo_root() / ".ci/rediacc_ci/core/dockerx.py",
        pathlib.Path(__file__),
    ):
        assert em_dash not in path.read_text(encoding="utf-8"), path


# A citation whose target this repository deliberately RETIRED, with the reason.
#
# `.ci/lib/setup.sh` is cited here as PROVENANCE, not as a live pointer: this module is the port of it, and each citation records which bash lines a function came from. E1 deleted the original once the port landed, so these citations are history and are kept on purpose. Repointing them at the port would make the module cite itself and destroy
# the only record of what came from where; deleting them would lose it outright.
#
# The reason is mandatory and the entry must still be CITED, so this cannot quietly become a place where a genuinely vanished file hides.
RETIRED_SOURCES = {
    ".ci/lib/setup.sh": (
        "ported into .ci/rediacc_ci/setup/ by E1 and deleted in the same campaign; "
        "the citations are the port's provenance, deliberately kept"
    ),
}


def _cited_paths(text: str) -> set[str]:
    return {
        match.group(1)
        for match in re.finditer(
            r"((?:\.ci|scripts|docs|\.claude)/[\w./-]+\.(?:sh|py|ts|md))", text
        )
    }


def test_every_file_the_module_cites_still_exists():
    text = (paths.repo_root() / ".ci/rediacc_ci/core/dockerx.py").read_text(encoding="utf-8")
    cited = _cited_paths(text)
    assert cited, "the docstring cites no files at all, so this check is vacuous"
    missing = {rel for rel in cited if not (paths.repo_root() / rel).exists()}
    assert missing - set(RETIRED_SOURCES) == set()


def test_retired_sources_are_still_cited_and_carry_a_reason():
    """The exemption cannot outlive its use, and cannot be reasonless.

    An entry nothing cites any more is dead weight that would silence a future
    citation of the same path; an entry with a blank reason is a suppression.
    """
    text = (paths.repo_root() / ".ci/rediacc_ci/core/dockerx.py").read_text(encoding="utf-8")
    cited = _cited_paths(text)
    for rel, reason in RETIRED_SOURCES.items():
        assert rel in cited, "%s is exempted but no longer cited; drop the entry" % rel
        assert reason.strip(), rel


def test_a_vanished_file_that_is_not_retired_still_fails():
    """CONTROL: the exemption is a named list, not a blanket."""
    cited = _cited_paths("see .ci/lib/no-such-file.sh for details")
    assert cited == {".ci/lib/no-such-file.sh"}
    missing = {rel for rel in cited if not (paths.repo_root() / rel).exists()}
    assert missing - set(RETIRED_SOURCES) == {".ci/lib/no-such-file.sh"}
