"""`rediacc_ci.testrun.unit` against its bash twin `.ci/scripts/test/run-unit.sh`, with a FAKE `npm`.

Compared: the ordered npm invocations, stdout, stderr and exit code. INTENTIONAL DELTA: an unknown argument is refused (`test_delta_unknown_argument_is_refused`). `--coverage` is gone (`test_delta_coverage_flag_is_gone`): it ran a `test:coverage` script nothing defines.
"""

from __future__ import annotations

import typing

from rediacc_ci.tests import testrun_support as ts

if typing.TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/test/run-unit.sh"
MODULE = "rediacc_ci.testrun.unit"


def both(
    tmp_path: pathlib.Path, args: list[str], env: dict[str, str] | None = None
) -> tuple[ts.Outcome, ts.Outcome]:
    old = ts.run_side(ts.bash_cmd(TWIN, *args), tmp_path / "bash", ("npm",), env)
    new = ts.run_side(ts.py_cmd(MODULE, *args), tmp_path / "py", ("npm",), ts.py_env(env))
    return old, new


def same(old: ts.Outcome, new: ts.Outcome) -> None:
    assert new.calls == old.calls
    assert (new.code, new.out, new.err) == (old.code, old.out, old.err)


def test_all_suites_pass(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, [])
    assert [c["argv"][-1] for c in old.calls] == [
        "@rediacc/shared",
        "@rediacc/cli",
        "@rediacc/provisioning",
        "@rediacc/e2e-tests",
    ]
    assert old.code == 0
    same(old, new)


def test_delta_coverage_flag_is_gone(tmp_path: pathlib.Path) -> None:
    # The twin ran `npm run test:coverage`, a script nothing defines, and only warned; the port has no such flag and refuses it like any unknown option.
    old, new = both(tmp_path, ["--coverage"])
    assert old.calls[-1]["argv"] == ["run", "test:coverage"]
    assert old.code == 0
    assert new.code == 2
    assert not new.calls


def test_first_failure_stops_the_run(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, [], {"FAKE_RC_NPM": "3"})
    assert (old.code, len(old.calls)) == (1, 1)
    same(old, new)


def test_delta_unknown_argument_is_refused(tmp_path: pathlib.Path) -> None:
    old, new = both(tmp_path, ["--coverge"])
    assert (old.code, len(old.calls)) == (0, 4), (
        "bash ran the suites and exited 0 although coverage was asked for in a typo"
    )
    assert new.code == 2
    assert not new.calls
    assert "Unknown option: --coverge" in new.err
