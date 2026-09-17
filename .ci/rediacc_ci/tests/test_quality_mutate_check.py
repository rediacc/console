"""`rediacc_ci.quality.mutate_check` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-mutate-check.sh` over a fixture with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. The twin has no environment seam -- it resolves its root from
its OWN location, `$(dirname "${BASH_SOURCE[0]}")/../../..` -- so it is copied
into the fixture along with the real mutation runner and its miniature suite. Same recipe as the committed ledger, `.ci/shadow/w7p2-mutate-check.observations.jsonl`.

WHAT THE LEDGER CANNOT SEE, AND THIS FILE CAN. `bad()` prints ` FAIL <label>`
with ONE space, and `scripts/lib/shadow-gate.ts`'s marker needs `FAIL:` or two
spaces, so every per-scenario failure line is CHATTER to the comparator and the only compared finding is the final count. Byte comparison here is therefore strictly stronger than the differential: it pins WHICH scenario failed, not just how many.

EVERY FIXTURE BELOW IS RED ON PURPOSE. A green run prints only `ok` lines, which the comparator reads as chatter, and two implementations that both say nothing have proved nothing about each other.
"""

import pathlib
import re
import shutil
import stat

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import mutate_check as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-mutate-check.sh"
RUNNER = ".ci/scripts/test/mutate-check.sh"
FIXDIR = ".ci/scripts/test/fixtures/mutate-check"
MODULE = "mutate_check"

# A runner collapsed into "always succeed", with and without the reassuring text scenario 1 greps for. Scenario 1 is the ONLY one that may exit 0, so the loud stub passes exactly one scenario and the quiet one passes none.
STUB_LOUD = '#!/usr/bin/env bash\necho "Both directions hold"\nexit 0\n'
STUB_QUIET = "#!/usr/bin/env bash\nexit 0\n"


def build(
    tmp_path: pathlib.Path,
    *,
    runner: str | None = None,
    unindent: bool = False,
    marker: bool = True,
) -> pathlib.Path:
    """A specimen repo holding BOTH implementations, the runner and the suite."""
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "scripts" / "test").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    shutil.copytree(src / FIXDIR, root / FIXDIR)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    target = root / RUNNER
    if runner is None:
        shutil.copy2(src / RUNNER, target)
    else:
        target.write_text(runner, encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    suite = root / FIXDIR / "fixture-suite.sh"
    if unindent:
        # THE SAME RUNTIME OUTPUT, a source text scenario 5's grep no longer matches. Rewriting the echo as a printf is what makes this case test scenario 5 alone rather than breaking the runner's own FAIL matching.
        lines = []
        for line in suite.read_text(encoding="utf-8").split("\n"):
            stripped = line.strip()
            if stripped.startswith(('echo "  PASS: ', 'echo "  FAIL: ')):
                inner = stripped[len('echo "  ') : -1]
                lines.append("    printf '  %s\\n' " + '"' + inner + '"')
            else:
                lines.append(line)
        suite.write_text("\n".join(lines), encoding="utf-8")
    if not marker:
        module = root / FIXDIR / "fixture_mod.py"
        module.write_text(
            "\n".join(
                line
                for line in module.read_text(encoding="utf-8").split("\n")
                if "HARMLESS_MARKER" not in line
            ),
            encoding="utf-8",
        )
    return root


# THE RUNNER NAMES ITS SANDBOX AFTER ITS OWN PID (`mutate-check.$$`), so the two sides quote a different path in the scenario-4 detail block for reasons that have nothing to do with either implementation. That is environment volatility, which `scripts/lib/shadow-gate.ts` handles with its `<tmp>` mask; this file compares raw bytes, so it has to mask the same thing itself. Masked
# NARROWLY -- only the pid -- because masking `/tmp/...` wholesale would also hide a port that quoted the wrong file.
_SANDBOX_PID = re.compile(r"mutate-check\.\d+")


def mask(text: str) -> str:
    return _SANDBOX_PID.sub("mutate-check.<pid>", text)


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=env, cwd=str(root), timeout=180)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.quality.%s" % MODULE, env=env, cwd=str(root), timeout=180
    )
    return old, new


@pytest.mark.parametrize(
    ("kwargs", "failures"),
    [
        pytest.param({"unindent": True}, 1, id="only-scenario-5-fails"),
        pytest.param({"unindent": True, "marker": False}, 2, id="scenario-3-and-5"),
        pytest.param({"runner": STUB_LOUD}, 3, id="a-runner-that-always-succeeds-loudly"),
        pytest.param({"runner": STUB_QUIET}, 4, id="a-runner-that-always-succeeds-silently"),
        pytest.param({"runner": STUB_QUIET, "unindent": True}, 5, id="everything-fails"),
    ],
)
def test_port_and_twin_agree_byte_for_byte(
    tmp_path: pathlib.Path, kwargs: dict, failures: int
) -> None:
    root = build(tmp_path, **kwargs)
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert old_exit == 1
    assert new_exit == old_exit
    assert mask(new_out) == mask(old_out)
    assert mask(new_err) == mask(old_err)
    assert "%d mutate-check.sh self-test(s) failed" % failures in old_out
    assert old_out.strip() != ""


def test_the_control_case_is_green_on_both_sides(tmp_path: pathlib.Path) -> None:
    """Scenario 1 is the ONLY one that may exit 0, so an untouched fixture is green.

    This is the mirror the parametrized cases above need: a gate that reported failures for everything would satisfy all five of them.
    """
    root = build(tmp_path)
    (old_exit, old_out, _), (new_exit, new_out, _) = run_both(root)
    assert old_exit == 0
    assert new_exit == 0
    assert new_out == old_out
    assert "produces the right verdict in all four outcomes" in old_out


def test_a_missing_runner_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    root = build(tmp_path)
    (root / RUNNER).unlink()
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root)
    assert (old_exit, new_exit) == (1, 1)
    assert "check-mutate-check: missing" in old_err
    assert new_err == old_err


# --------------------------------------------------------------------------- The decision functions, driven directly. Both directions for every rule. ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "rc", "ok"),
    [
        pytest.param(gate.RC_ZERO, 0, True, id="zero-hits"),
        pytest.param(gate.RC_ZERO, 1, False, id="zero-misses"),
        pytest.param(gate.RC_NONZERO, 1, True, id="nonzero-hits"),
        pytest.param(gate.RC_NONZERO, 0, False, id="nonzero-misses"),
        pytest.param(gate.RC_TWO, 2, True, id="two-hits"),
        pytest.param(gate.RC_TWO, 1, False, id="two-is-not-any-nonzero"),
    ],
)
def test_rc_ok(mode: str, rc: int, ok: bool) -> None:
    assert gate.rc_ok(mode, rc) is ok


def test_an_unknown_rc_mode_raises_rather_than_answering_false() -> None:
    with pytest.raises(ValueError, match="unknown rc mode"):
        gate.rc_ok("nope", 0)


@pytest.mark.parametrize(
    ("text", "indented"),
    [
        pytest.param('    echo "  PASS: 900 x"\n', True, id="pass-line"),
        pytest.param('    echo "  FAIL: 900 x"\n', True, id="fail-line"),
        pytest.param('echo "  PASS: 900 x"\n', False, id="flush-left"),
        pytest.param('    echo "PASS: 900 x"\n', False, id="wrong-inner-spacing"),
        pytest.param("", False, id="empty"),
    ],
)
def test_indented_result_lines(text: str, indented: bool) -> None:
    assert gate.indented_result_lines(text) is indented


def test_the_needle_is_a_fixed_string_not_a_pattern() -> None:
    """`grep -qF`. A metacharacter in the needle is literal in both directions."""
    assert gate.scenario_passed(gate.RC_NONZERO, 1, "a.c", "a.c") is True
    assert gate.scenario_passed(gate.RC_NONZERO, 1, "abc", "a.c") is False


def test_the_real_fixture_suite_still_indents() -> None:
    """Scenario 5 over the LIVE fixture: the reason it indents must not be lost."""
    suite = paths.from_root(FIXDIR, "fixture-suite.sh")
    assert gate.indented_result_lines(suite.read_text(encoding="utf-8"))


def test_selftest_passes_and_is_not_vacuous(capsys) -> None:
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert "control(s) passed" in out
    assert int(out.strip().split("\n")[-1].split()[0]) >= 18
