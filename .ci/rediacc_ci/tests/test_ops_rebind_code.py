"""rediacc_ci.ops.rebind_code: the program `REDIACC_IP_REBIND_CODE_COMMAND` names for a bench config. With the bench's login profile bound it prints the current code of BENCH_ROOT_TOTP_SEED on stdout and nothing else; an unknown config, a missing or placeholder seed and a foreign bench profile are named refusals (rc 2) with nothing on stdout; and an unbound run re-executes once under the region's profile."""

from __future__ import annotations

import os
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import rebind_code, totp

SEED = "JBSWY3DPEHPK3PXP"
CLOCK = 1_700_000_010.0  # the start of a 30 s step


def _freeze(monkeypatch, start: float) -> list[float]:
    clock = [start]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(rebind_code, "_clock", lambda: (lambda: clock[0], sleep))
    return slept


def _never_run(argv, _env):
    raise AssertionError("no child may run: %r" % (argv,))


@pytest.fixture
def bound_eu(monkeypatch):
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "bench-login-eu")
    monkeypatch.setenv(rebind_code.SEED_ENV, SEED)


@pytest.mark.usefixtures("bound_eu")
@pytest.mark.parametrize("config", ["eu-bench", "bench"])
def test_prints_the_current_code_and_nothing_else(monkeypatch, capsys, config):
    _freeze(monkeypatch, CLOCK)

    rc = rebind_code.main([config], run=_never_run)

    out, err = capsys.readouterr()
    assert rc == 0
    assert out == totp.code(SEED, at=CLOCK) + "\n"
    assert SEED not in out + err
    assert totp.code(SEED, at=CLOCK) not in err


@pytest.mark.usefixtures("bound_eu")
def test_waits_for_the_next_step_near_its_end(monkeypatch, capsys):
    slept = _freeze(monkeypatch, CLOCK + 28)

    assert rebind_code.main(["eu-bench"], run=_never_run) == 0

    assert slept
    assert slept[0] == pytest.approx(2.5)
    assert capsys.readouterr().out == totp.code(SEED, at=CLOCK + 30.5) + "\n"


@pytest.mark.parametrize("args", [[], ["eu-remote"], ["rediacc"], ["eu-bench", "extra"]])
def test_refuses_an_unmapped_config_before_any_vault_read(capsys, args):
    rc = rebind_code.main(args, run=_never_run)

    out, err = capsys.readouterr()
    assert rc == 2
    assert out == ""
    assert "rebind_code" in err


@pytest.mark.parametrize("value", ["", rebind_code.PLACEHOLDER, "not base32 !!"])
def test_refuses_a_missing_placeholder_or_bad_seed(monkeypatch, capsys, value):
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "bench-login-eu")
    monkeypatch.setenv(rebind_code.SEED_ENV, value)

    rc = rebind_code.main(["eu-bench"], run=_never_run)

    out, err = capsys.readouterr()
    assert rc == 2
    assert out == ""
    assert "BENCH_ROOT_TOTP_SEED_EU" in err


def test_refuses_another_benchs_profile(monkeypatch, capsys):
    monkeypatch.setenv("REDIACC_BWS_PROFILES", "bench-login-us")
    monkeypatch.setenv(rebind_code.SEED_ENV, SEED)

    rc = rebind_code.main(["eu-bench"], run=_never_run)

    out, err = capsys.readouterr()
    assert rc == 2
    assert out == ""
    assert "bench-login-us" in err


def test_unbound_reexecutes_once_under_the_regions_profile(monkeypatch):
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    monkeypatch.delenv(rebind_code.SEED_ENV, raising=False)
    calls: list[list[str]] = []

    def run(argv, env):
        calls.append(list(argv))
        assert rebind_code.SEED_ENV not in env
        return 7

    assert rebind_code.main(["us-bench"], run=run) == 7
    assert len(calls) == 1
    argv = calls[0]
    assert argv[argv.index("--profile") + 1] == "bench-login-us"
    assert argv[-2:] == ["rediacc_ci.ops.rebind_code", "us-bench"]


def test_rdc_sh_exports_the_program_for_exactly_the_mapped_configs():
    """rdc.sh's bench `case` arm names the same configs rebind_code maps and points at this module's own executable path, with no bash wrapper between."""
    line = next(
        ln
        for ln in paths.from_root("rdc.sh").read_text(encoding="utf-8").splitlines()
        if "REDIACC_IP_REBIND_CODE_COMMAND=" in ln
    )
    arm = line.split(" in ", 1)[1].split(")", 1)[0]
    assert {c.strip() for c in arm.split("|")} == set(rebind_code.CONFIG_REGIONS)
    assert "$ROOT_DIR/.ci/rediacc_ci/ops/rebind_code.py}" in line
    program = paths.from_root(".ci", "rediacc_ci", "ops", "rebind_code.py")
    assert program.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")
    assert os.access(program, os.X_OK)


def test_the_program_runs_by_path_with_no_pythonpath():
    """The CLI spawns the path itself, with no shell and no PYTHONPATH: the module's own hop must resolve `rediacc_ci`. An unknown config is refused (rc 2) before any vault read, so this needs no secret."""
    program = paths.from_root(".ci", "rediacc_ci", "ops", "rebind_code.py")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", rebind_code.SEED_ENV)}
    done = subprocess.run(
        [str(program), "not-a-bench"],
        env=env,
        cwd="/",
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert done.returncode == 2, done.stderr
    assert done.stdout == ""
    assert "no vault seed is mapped" in done.stderr
    assert "ModuleNotFoundError" not in done.stderr
