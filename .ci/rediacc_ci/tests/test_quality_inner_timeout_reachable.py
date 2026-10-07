"""`.ci/scripts/quality/check_inner_timeout_reachable.py`, driven in-process and as the real entry point.

The in-process half runs the gate's own controls. The entry-point half builds a miniature repository in a temporary directory -- the gate script and `_cipath.py` copied in, `.ci/rediacc_ci` linked to the real package -- because the gate finds its tree from its own file's location, and a fixture tree is the only way to watch the WHOLE invocation go red on a planted step module and green on its clean twin, without touching the working tree.
"""

import importlib.util
import pathlib
import shutil
import subprocess
import sys
import types

import pytest

from rediacc_ci import paths

QUALITY = paths.from_root(".ci", "scripts", "quality")
GATE = QUALITY / "check_inner_timeout_reachable.py"
CI_PKG = paths.from_root(".ci", "rediacc_ci")


def _load() -> types.ModuleType:
    sys.path.insert(0, str(QUALITY))
    try:
        spec = importlib.util.spec_from_file_location("check_inner_timeout_reachable", GATE)
        assert spec
        assert spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(QUALITY))


gate = _load()


def test_selftest_passes() -> None:
    """The gate's own controls, both directions, in-process."""
    assert gate.selftest() is True


def test_bare_container_timeout_is_seen_in_seconds() -> None:
    """The name the `_S`-only pattern missed."""
    assert gate.inner_timers("CONTAINER_TIMEOUT = 1800\n", "m.py") == [("CONTAINER_TIMEOUT", 1800)]


def test_regex_named_timeout_is_not_a_timer() -> None:
    assert gate.inner_timers('_TIMEOUT = re.compile(r"[0-9]+")\n', "m.py") == []


def test_step_ceiling_is_the_smaller_of_step_and_job() -> None:
    wf = (
        "jobs:\n"
        "  j:\n"
        "    timeout-minutes: 20\n"
        "    steps:\n"
        "      - name: a\n"
        "        timeout-minutes: 3\n"
        "        run: python3 tools/a.py\n"
    )
    scan = gate.scan_steps({"w.yml": wf}, {"tools/a.py": "A_TIMEOUT = 200\n"}.get)
    assert [k[3] for k in scan.subjects] == [3]
    assert len(gate.step_findings(scan, {"tools/a.py": "A_TIMEOUT = 200\n"}.get)) == 1


# ---------------------------------------------------------------------------
# The real entry point over a miniature tree.
# ---------------------------------------------------------------------------

_LOCK = (
    '[{"id": "check:x", "leaves": ["tools/gate.py"], '
    '"ci": {"kind": "step", "workflow": ".github/workflows/w.yml", "job": "j", "step": "g"}}]'
)

# `create_e2e_env` is named so the gate's `DECLARED_UNITS` entry is live in this tree too; it resolves through the link to the real package.
_WORKFLOW = """\
name: w
on: push
jobs:
  j:
    timeout-minutes: 20 # budget cap
    steps:
      - name: g
        run: python3 tools/gate.py
      - name: install
        run: |
          python3 tools/slow.py \\
            --method dnf
      - name: e2e env
        run: PYTHONPATH=.ci python3 -m rediacc_ci.env.create_e2e_env
"""


def _tree(tmp_path: pathlib.Path, slow_source: str, workflow: str = _WORKFLOW) -> pathlib.Path:
    quality = tmp_path / ".ci" / "scripts" / "quality"
    quality.mkdir(parents=True)
    shutil.copy(GATE, quality / GATE.name)
    shutil.copy(QUALITY / "_cipath.py", quality / "_cipath.py")
    (tmp_path / ".ci" / "rediacc_ci").symlink_to(CI_PKG)
    (tmp_path / "scripts" / "ci-runner").mkdir(parents=True)
    (tmp_path / "scripts" / "ci-runner" / "gates.lock.json").write_text(_LOCK)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "w.yml").write_text(workflow)
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "gate.py").write_text("RUN_TIMEOUT_S = 600\n")
    (tmp_path / "tools" / "slow.py").write_text(slow_source)
    return quality / GATE.name


def _run(script: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=120, check=False
    )


def test_clean_tree_is_green_and_prints_its_shape(tmp_path: pathlib.Path) -> None:
    result = _run(_tree(tmp_path, "CONTAINER_TIMEOUT = 360\n"))
    assert result.returncode == 0, result.stderr
    assert "3 module(s) resolved from 3 step(s) in 1 workflow(s)" in result.stdout


def test_planted_container_timeout_goes_red(tmp_path: pathlib.Path) -> None:
    """THE INCIDENT: a step module's bare CONTAINER_TIMEOUT above its 20-minute job."""
    result = _run(_tree(tmp_path, "CONTAINER_TIMEOUT = 1800\n"))
    assert result.returncode == 1
    assert "tools/slow.py" in result.stderr
    assert "CONTAINER_TIMEOUT=1800s is at or above its ceiling of 1200s" in result.stderr


def test_unfoldable_timer_goes_red(tmp_path: pathlib.Path) -> None:
    result = _run(_tree(tmp_path, "CONTAINER_TIMEOUT = compute()\n"))
    assert result.returncode == 1
    assert "cannot fold" in result.stderr


@pytest.mark.parametrize(
    "workflow",
    [
        # no step runs any Python module: the step half would check nothing
        "name: w\non: push\njobs:\n  j:\n    timeout-minutes: 20\n    steps:\n      - run: echo hi\n",
    ],
)
def test_zero_step_modules_is_refused(tmp_path: pathlib.Path, workflow: str) -> None:
    result = _run(_tree(tmp_path, "CONTAINER_TIMEOUT = 360\n", workflow))
    assert result.returncode == 1
    assert "resolved NO Python module a step" in result.stderr
