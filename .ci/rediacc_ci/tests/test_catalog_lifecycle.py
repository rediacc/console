"""`rediacc_ci.catalog.lifecycle`, the port of `packages/json/test-templates.sh`.

THE BASH TWIN WAS RETIRED WITH THIS FILE (PLAN-retire-bash-oracles B5, W10). Before it went, both were driven side by side against the recording `docker` stub below and fixture Rediaccfiles: the stderr transcript, the stdout, the exit status, the recorded docker argv and the results JSON agreed for `--skip`, `--category --verbose`, `--template --no-cleanup`, `--help` and an unknown option, with a failing `up()`, a failing `down()` and a health failure in the run. They differed only where a deliberate delta (Rule T) says so, and each of those has a test here that fails on the bash behaviour.

THE SUBJECT NEEDS DOCKER AND A LICENSED REPO TO DO ITS REAL JOB (see the module docstring), so docker is a stub on PATH; the Rediaccfiles are real bash.
"""

from __future__ import annotations

import json
import os
import stat
import time
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.catalog import lifecycle

if TYPE_CHECKING:
    import pathlib

DOCKER_STUB = """#!/bin/bash
echo "docker $*" >> "$DOCKER_LOG"
case "$1 $2" in
  "network inspect") exit 1 ;;
  "compose config") printf 'web\\n'; exit 0 ;;
  "compose ps")
    if [ "$3" = "--format" ]; then
      case "$PWD" in
        *badhealth*) cat "$PS_BAD" ;;
        *) cat "$PS_OK" ;;
      esac
    fi
    exit 0 ;;
esac
exit 0
"""

PS_OK = '{"Name":"w","Status":"Up 1 second","State":"running","Health":"healthy","ExitCode":0}\n'
PS_STARTING = (
    '{"Name":"w","Status":"Up 1 second","State":"running","Health":"starting","ExitCode":0}\n'
)
COMPOSE = 'services:\n  web:\n    image: "redis:7"\n    healthcheck:\n      test: ["CMD","true"]\n'
GOOD = "up() { true; }\ndown() { true; }\n"


@pytest.fixture
def env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A package directory, a stub docker first on PATH, and instant sleeps."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker = bindir / "docker"
    docker.write_text(DOCKER_STUB, encoding="utf-8")
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "ps_ok.json").write_text(PS_OK, encoding="utf-8")
    (tmp_path / "ps_bad.json").write_text(PS_STARTING, encoding="utf-8")
    monkeypatch.setenv("PATH", "%s:/usr/local/bin:/usr/bin:/bin" % bindir)
    monkeypatch.setenv("DOCKER_LOG", str(tmp_path / "docker.log"))
    monkeypatch.setenv("PS_OK", str(tmp_path / "ps_ok.json"))
    monkeypatch.setenv("PS_BAD", str(tmp_path / "ps_bad.json"))
    monkeypatch.setenv("TEST_TIMEOUT", "20")
    monkeypatch.setenv("HEALTH_CHECK_TIMEOUT", "5")
    for name in ("REPOSITORY_NETWORK_MODE", "RESULTS_FILE", "ARTIFACTS_DIR", "VERBOSE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(lifecycle, "sleep", lambda _s: None)
    pkg = tmp_path / "pkg"
    (pkg / "templates").mkdir(parents=True)
    return pkg


def _template(
    pkg: pathlib.Path, rel: str, rediaccfile: str = GOOD, compose: str = COMPOSE
) -> pathlib.Path:
    directory = pkg / "templates" / rel
    directory.mkdir(parents=True)
    (directory / "Rediaccfile").write_text(rediaccfile, encoding="utf-8")
    if compose:
        (directory / "docker-compose.yaml").write_text(compose, encoding="utf-8")
    return directory


def _results(pkg: pathlib.Path, name: str = "test-results.json") -> dict:
    return json.loads((pkg / name).read_text(encoding="utf-8"))


def _by_name(results: dict) -> dict[str, dict]:
    return {r["name"]: r for r in results["results"]}


def _docker_log(pkg: pathlib.Path) -> list[str]:
    log = pkg.parent / "docker.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


# ---------------------------------------------------------------------------- the run


def test_a_passing_template(env: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    _template(env, "cat1/good")
    rc = lifecycle.main([], package_dir=env)
    err = capsys.readouterr().err
    assert rc == 0
    results = _results(env)
    assert results["summary"]["total"] == 1
    assert results["summary"]["passed"] == 1
    assert results["summary"]["failed"] == 0
    row = _by_name(results)["cat1/good"]
    assert row["category"] == "cat1"
    assert row["overall"] == "passed"
    assert row["error"] is None
    assert [k for k in row if k in ("up", "health", "down", "cleanup")] == [
        "up",
        "health",
        "down",
        "cleanup",
    ]
    assert "All tests passed!" in err
    log = _docker_log(env)
    assert "docker network create rediacc_cat1_good" in log
    assert "docker network rm rediacc_cat1_good" in log
    assert "docker rmi -f redis:7" in log
    assert "docker volume prune -f" in log


def test_failing_up_skips_health_and_blames_up(env: pathlib.Path) -> None:
    _template(env, "cat1/badup", "up() { return 3; }\ndown() { true; }\n")
    assert lifecycle.main([], package_dir=env) == 1
    row = _by_name(_results(env))["cat1/badup"]
    assert row["up"]["status"] == "failed"
    assert row["up"]["error"] == "up function failed"
    assert "health" not in row
    assert row["down"]["status"] == "passed"
    assert row["error"] == "up() failed"
    stages = [
        p.name.split("_", 1)[1]
        for p in (env / "test-artifacts" / "cat1__badup").iterdir()
        if p.is_dir()
    ]
    assert stages == ["up"]


def test_failing_down_and_failing_health(env: pathlib.Path) -> None:
    _template(env, "cat2/baddown", "up() { true; }\ndown() { return 1; }\n")
    _template(env, "cat2/badhealth")
    assert lifecycle.main([], package_dir=env) == 1
    rows = _by_name(_results(env))
    assert rows["cat2/baddown"]["down"]["error"] == "down function failed"
    assert rows["cat2/baddown"]["error"] == "down() failed"
    health = rows["cat2/badhealth"]
    assert health["health"]["status"] == "failed"
    assert health["error"] == "Health check failed"


def test_an_up_that_times_out_is_reported_as_a_timeout(
    env: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TEST_TIMEOUT", "1")
    _template(env, "cat1/slow", "up() { sleep 30; }\ndown() { true; }\n")
    assert lifecycle.main([], package_dir=env) == 1
    row = _by_name(_results(env))["cat1/slow"]
    assert row["up"]["error"] == "up function timed out after 1s"


def test_report_layout_and_counters(env: pathlib.Path) -> None:
    _template(env, "a/one")
    _template(env, "a/two")
    _template(env, "b/three")
    lifecycle.main(["--skip", "b/three"], package_dir=env)
    text = (env / "test-results.json").read_text(encoding="utf-8")
    assert text.startswith('{\n  "summary": {\n    "total": 2,')
    assert '"skipped": 1' in text
    assert '    {"name":"a/one"' in text
    assert '},\n    {"name":"a/two"' in text.replace("}\n,\n    {", "},\n    {")
    assert text.endswith("\n  ]\n}\n")


def test_filters(env: pathlib.Path) -> None:
    for rel in ("a/one", "a/two", "b/three"):
        _template(env, rel)
    lifecycle.main(["--category", "a", "--template", "a/two"], package_dir=env)
    assert [r["name"] for r in _results(env)["results"]] == ["a/two"]
    lifecycle.main(["--category", "b"], package_dir=env)
    assert [r["name"] for r in _results(env)["results"]] == ["b/three"]


def test_no_cleanup_leaves_images_alone(env: pathlib.Path) -> None:
    _template(env, "a/one")
    lifecycle.main(["--no-cleanup"], package_dir=env)
    assert not any(line.startswith("docker rmi") for line in _docker_log(env))


# ---------------------------------------------------------------------------- deliberate deltas


def test_a_template_that_cannot_start_does_not_end_the_run(
    env: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: the bash `return 1`ed from `test_template`, and `set -e` in main's loop ended the run with no report."""
    _template(env, "a/nosource", "return 1\nup() { true; }\n")
    _template(env, "b/good")
    (env / "templates" / "c" / "norediaccfile").mkdir(parents=True)
    rc = lifecycle.main([], package_dir=env)
    assert rc == 1
    rows = _by_name(_results(env))
    assert rows["a/nosource"]["error"] == "Failed to source Rediaccfile"
    assert rows["a/nosource"]["duration"] == "0s"
    assert rows["b/good"]["overall"] == "passed"
    assert _results(env)["summary"]["failed"] == 1
    assert "Failed to source Rediaccfile" in capsys.readouterr().err


def test_a_vanished_template_directory_is_recorded_and_the_run_continues(
    env: pathlib.Path,
) -> None:
    _template(env, "b/good")
    suite = lifecycle.Suite(env)
    suite.total = 2
    suite.test_template("a/gone")
    suite.test_template("b/good")
    suite.generate_report()
    rows = _by_name(_results(env))
    assert rows["a/gone"]["error"] == "Directory not found"
    assert rows["b/good"]["overall"] == "passed"


def test_no_templates_found_exits_one_with_the_message(
    env: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: the bash died on `discovery_output[0]: unbound variable` after wiping the artifacts."""
    rc = lifecycle.main(["--template", "nope/x"], package_dir=env)
    err = capsys.readouterr().err
    assert rc == 1
    assert "No templates found matching criteria" in err
    assert "unbound variable" not in err
    assert not (env / "test-results.json").exists()


def test_a_relative_output_is_relative_to_where_the_command_ran(
    env: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule T: the bash cd'ed around and wrote the report wherever the last cd left it."""
    _template(env, "a/one")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert lifecycle.main(["--output", "out.json"], package_dir=env) == 0
    assert (elsewhere / "out.json").is_file()
    assert not (env / "test-results.json").exists()
    assert not any((env / "templates").rglob("out.json"))


def test_default_report_is_in_the_package_directory(
    env: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _template(env, "a/one")
    monkeypatch.chdir(tmp_path)
    assert lifecycle.main([], package_dir=env) == 0
    assert (env / "test-results.json").is_file()


def test_one_templates_shell_state_does_not_leak_into_the_next(env: pathlib.Path) -> None:
    """Rule T: the bash sourced each Rediaccfile into its own process, so `leak` was still defined for the next template."""
    _template(env, "a/first", "leak() { :; }\nup() { true; }\ndown() { true; }\n")
    _template(env, "b/second", "up() { ! declare -F leak >/dev/null; }\ndown() { true; }\n")
    assert lifecycle.main([], package_dir=env) == 0
    assert _by_name(_results(env))["b/second"]["overall"] == "passed"


def test_compose_ps_json_array_shape_is_read() -> None:
    """Rule T: the bash passed an array through `jq .Name`, which failed."""
    array = '[{"Name":"a","Status":"Up 2 seconds","State":"running"},{"Name":"b","State":"exited"}]'
    lines = lifecycle.Suite.parse_ps(array)
    assert [c["Name"] for c in lines] == ["a", "b"]
    objects = '{"Name":"a"}\n{"Name":"b"}\n'
    assert [c["Name"] for c in lifecycle.Suite.parse_ps(objects)] == ["a", "b"]
    assert lifecycle.Suite.parse_ps("not json\n") == []


def test_missing_option_value_is_a_named_error(
    env: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rule T: the bash read `$2` unbound."""
    assert lifecycle.main(["--skip"], package_dir=env) == 1
    err = capsys.readouterr().err
    assert "--skip requires a value" in err
    assert "unbound" not in err


def test_the_process_group_dies_with_a_timed_out_up(
    env: pathlib.Path, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Rule T: only the shell was killed, so a backgrounded compose child outlived the timeout."""
    marker = tmp_path / "survivor"
    monkeypatch.setenv("TEST_TIMEOUT", "1")
    _template(
        env,
        "a/orphan",
        "up() { ( sleep 3; touch %s ) & wait; }\ndown() { true; }\n" % marker,
    )
    lifecycle.main([], package_dir=env)
    time.sleep(4)
    assert not marker.exists()


# ---------------------------------------------------------------------------- helpers


def test_help_text_and_unknown_option(
    env: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lifecycle.main(["--help"], package_dir=env) == 0
    assert capsys.readouterr().out == lifecycle.HELP
    assert lifecycle.main(["--bogus"], package_dir=env) == 1
    captured = capsys.readouterr()
    assert "Unknown option: --bogus" in captured.err
    assert captured.out == lifecycle.HELP


def test_results_file_env_and_option_precedence(
    env: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _template(env, "a/one")
    monkeypatch.setenv("RESULTS_FILE", str(tmp_path / "from-env.json"))
    lifecycle.main([], package_dir=env)
    assert (tmp_path / "from-env.json").is_file()
    lifecycle.main(["--output", str(tmp_path / "from-flag.json")], package_dir=env)
    assert (tmp_path / "from-flag.json").is_file()


def test_validate_all_containers_counts(env: pathlib.Path, tmp_path: pathlib.Path) -> None:
    directory = _template(env, "a/one")
    suite = lifecycle.Suite(env)
    assert suite.validate_all_containers(directory, True, True) is True
    (tmp_path / "ps_ok.json").write_text(
        '{"Name":"w","Status":"Exited (1) 2 seconds ago","State":"exited","ExitCode":1}\n',
        encoding="utf-8",
    )
    assert suite.validate_all_containers(directory, False, True) is False
    (tmp_path / "ps_ok.json").write_text("", encoding="utf-8")
    assert suite.validate_all_containers(directory, False, True) is False


def test_cleanup_images_strips_variables_and_quotes(env: pathlib.Path) -> None:
    directory = _template(
        env,
        "a/one",
        compose="services:\n  a:\n    image: 'nginx:1'\n  b:\n    image: ${REG}/x:2\n  c:\n    image: \"${A:-b}c\"\n  d:\n    image: plain # note\n",
    )
    suite = lifecycle.Suite(env)
    suite.cleanup_images(directory)
    rmi = [line for line in _docker_log(env) if line.startswith("docker rmi")]
    assert rmi == [
        "docker rmi -f nginx:1",
        "docker rmi -f /x:2",
        "docker rmi -f c",
        "docker rmi -f plain",
    ]


def test_cleanup_directories_removes_data_dirs_only(env: pathlib.Path) -> None:
    directory = _template(env, "a/one")
    (directory / "data").mkdir()
    (directory / "data-extra").mkdir()
    (directory / "database").mkdir()
    (directory / "keep").mkdir()
    (directory / "datafile.txt").write_text("x", encoding="utf-8")
    lifecycle.Suite(env).cleanup_directories(directory)
    assert sorted(p.name for p in directory.iterdir()) == [
        "Rediaccfile",
        "datafile.txt",
        "docker-compose.yaml",
        "keep",
    ]


def test_original_network_mode_is_kept(env: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _template(env, "a/one", 'up() { [ "$REPOSITORY_NETWORK_MODE" = mine ]; }\ndown() { true; }\n')
    monkeypatch.setenv("REPOSITORY_NETWORK_MODE", "mine")
    assert lifecycle.main([], package_dir=env) == 0
    assert not any(line.startswith("docker network") for line in _docker_log(env))
    assert os.environ["REPOSITORY_NETWORK_MODE"] == "mine"
