"""The control for `rediacc_ci.pytest_conftest_rebind`: a directory pytest collects twice still sees its conftest's fixtures.

THE ORDER THAT BROKE (worklist #6b5becd7, two writers on 2026-10-07). `gates/x.py tests/y.py gates/z.py` in one invocation: the file directly under `tests/` makes pytest re-collect `<Package tests>`, the third argument then walks into a NEW `<Package gates>` object, and pytest 9.1.1 binds a conftest's fixtures to the first collector object only. Every test in `gates/z.py` failed setup with
"fixture 'gate' not found" while any pair of the three passed. The module docstring carries the pytest line numbers.

Every case drives a REAL child pytest. `--setup-plan` resolves every fixture exactly as a run does but executes no test body, so the real-tree case costs under a second and cannot be reddened by an unrelated failure inside the three files.

BOTH DIRECTIONS, AND THE PLANT IS PERMANENT. Each order is also run with the plugin BLOCKED (`-p no:`), which must still show the error: that proves the case reaches the defect rather than an order pytest happens to collect cleanly, and the day an upgraded pytest fixes it upstream, the blocked case goes red and says to delete the plugin.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

CI_DIR = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = "rediacc_ci.pytest_conftest_rebind"
MISSING = "fixture 'gate' not found"
TIMEOUT = 300

# The exact order the defect was reported with, relative to `.ci`.
REAL_ORDER = (
    "rediacc_ci/tests/gates/test_gate_plan_folders.py",
    "rediacc_ci/tests/test_quality_plan_lifecycle.py",
    "rediacc_ci/tests/gates/test_gate_plan_citations.py",
)


def _run(argv: list[str], cwd: pathlib.Path, *, pythonpath: str | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath
    # The parent run's tree tripwire already covers this process tree; a nested one would judge the parent's writes as its own.
    env["TREE_SNAPSHOT"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *argv],
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _scratch_tree(root: pathlib.Path) -> None:
    """The real shape in miniature: a package `t`, a subpackage `t/gates` whose conftest owns `gate`, one test file in each."""
    files = {
        "pytest.ini": "[pytest]\n",
        "t/__init__.py": "",
        "t/gates/__init__.py": "",
        "t/gates/conftest.py": (
            "import pytest\n\n\n@pytest.fixture\ndef gate():\n    return 'bound'\n"
        ),
        "t/gates/test_a.py": "def test_a(gate):\n    assert gate == 'bound'\n",
        "t/test_b.py": "def test_b():\n    assert True\n",
        "t/gates/test_c.py": "def test_c(gate):\n    assert gate == 'bound'\n",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _scratch(tmp_path: pathlib.Path, *, plugin: bool) -> tuple[int, str]:
    _scratch_tree(tmp_path)
    argv = ["-q", "-p", "no:cacheprovider", "-p", "no:xdist", "--rootdir", str(tmp_path)]
    argv += ["-c", str(tmp_path / "pytest.ini")]
    argv += ["-p", PLUGIN] if plugin else ["-p", "no:" + PLUGIN]
    argv += ["t/gates/test_a.py", "t/test_b.py", "t/gates/test_c.py"]
    # The scratch tree has no `pythonpath` ini key, so the plugin's package is put on the path here.
    return _run(argv, tmp_path, pythonpath=str(CI_DIR))


def test_the_scratch_order_passes_with_the_plugin(tmp_path):
    rc, out = _scratch(tmp_path, plugin=True)
    assert rc == 0, "gates/a, b, gates/c failed with the plugin loaded (rc=%d):\n%s" % (rc, out)
    assert "3 passed" in out, "expected all 3 scratch tests to run and pass:\n%s" % out
    assert MISSING not in out


def test_the_scratch_order_reaches_the_defect_without_the_plugin(tmp_path):
    rc, out = _scratch(tmp_path, plugin=False)
    if rc == 0 or MISSING not in out:
        pytest.fail(
            "with %s BLOCKED the scratch order passed (rc=%d). Either this case no longer reaches "
            "the defect, or pytest fixed it upstream: re-check _pytest/fixtures.py's conftest "
            "binding and, if fixed, delete the plugin, its pytest_plugins entry in the root "
            "conftest.py, and this file.\n%s" % (PLUGIN, rc, out)
        )
    assert "2 passed" in out, (
        "test_a and test_b must still pass; only test_c loses `gate`:\n%s" % out
    )


def _real(*, plugin: bool) -> tuple[int, str]:
    for rel in REAL_ORDER:
        assert (CI_DIR / rel).is_file(), (
            "%s is gone; pick another gates/x, tests/y, gates/z triple for REAL_ORDER" % rel
        )
    # The real ini is in force here: `--strict-config` refuses `cache_dir` without the cacheprovider and `addopts`' `--dist` without xdist, so neither is blocked.
    argv = ["--setup-plan"]
    if not plugin:
        argv += ["-p", "no:" + PLUGIN]
    return _run([*argv, *REAL_ORDER], CI_DIR)


def test_the_reported_real_tree_order_resolves_gate():
    rc, out = _real(plugin=True)
    if rc != 0 or MISSING in out:
        pytest.fail("the reported order still loses `gate` (rc=%d):\n%s" % (rc, out[-4000:]))
    # Non-vacuity: `gate` was actually set up for the LAST file, the one that used to lose it.
    citations = [line for line in out.splitlines() if "test_gate_plan_citations.py::" in line]
    setups = out.split("test_gate_plan_citations.py::", 1)[-1].count("SETUP    F gate")
    if not citations or setups == 0:
        pytest.fail(
            "no `gate` setup was planned for test_gate_plan_citations.py, so this case proved "
            "nothing:\n%s" % out[-4000:]
        )


def test_the_reported_real_tree_order_reaches_the_defect_without_the_plugin():
    rc, out = _real(plugin=False)
    if rc == 0 or MISSING not in out:
        pytest.fail(
            "with %s BLOCKED the reported order resolved `gate` (rc=%d). If pytest fixed the "
            "defect upstream, delete the plugin, its pytest_plugins entry and this file.\n%s"
            % (PLUGIN, rc, out[-4000:])
        )
