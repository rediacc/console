"""`check:ci-config-server-key-constant` (`.ci/scripts/quality/check_config_server_key_constant.py`): the layer-3 dev key stays a TEST_MODE-only constant in `private/account/src/services/config-server-key.ts` (agent/plans/PLAN-config-server-key.md K6).

CONTROL FIRST, AND NEVER ON THE REAL TREE. Every case builds a scratch git repository under `tmp_path` and points the gate at it with `--root`; the unplanted fixture must pass first, so a red on a plant is the plant's doing. The real tree is only read by the gate's own run, never written here.

THE PLANTED DEFECTS: the constant in another account source file, the constant exported, a return of it outside the TEST_MODE guard, and a tree with nothing to scan (CANNOT RUN, exit 77, never a pass). The negative controls: a copy under a `tests` directory, which is exempt and printed, and a markdown mention, which is not source.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

GATE = paths.repo_root() / ".ci" / "scripts" / "quality" / "check_config_server_key_constant.py"
CONSTANT = "rediacc-config-server-" + "dev-key"
HOME = "private/account/src/services/config-server-key.ts"


def _load():
    # The gate imports its sibling `_cipath` shim, which a script run finds beside itself; an in-process load needs the gate's directory on the path, or the file only passes when an earlier test happened to put it there.
    paths.on_sys_path(GATE.parent)
    spec = importlib.util.spec_from_file_location("check_config_server_key_constant", GATE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gate = _load()


def _tree(
    tmp_path: pathlib.Path, extra: dict[str, str] | None = None, home: str | None = None
) -> pathlib.Path:
    files = {
        HOME: gate.HEALTHY_HOME if home is None else home,
        "private/account/src/services/config.service.ts": "export const x = 1;\n",
        "packages/cli/src/index.ts": "export {};\n",
        **(extra or {}),
    }
    for rel, body in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    return tmp_path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), *args], capture_output=True, text=True, check=False
    )


def test_selftest_passes() -> None:
    proc = _run("--selftest")
    assert proc.returncode == 0, proc.stderr
    assert "every plant fired" in proc.stdout


def test_a_healthy_tree_passes_and_prints_its_corpus(tmp_path) -> None:
    proc = _run("--root", str(_tree(tmp_path)))
    assert proc.returncode == 0, proc.stderr
    assert "3 source file(s)" in proc.stdout
    assert "1 TEST_MODE-guarded return" in proc.stdout
    assert proc.stderr == ""


def test_the_constant_in_another_source_file_fails_naming_file_and_line(tmp_path) -> None:
    root = _tree(
        tmp_path, {"private/account/src/services/legacy.ts": "// x\nconst K = '%s';\n" % CONSTANT}
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 1
    assert "private/account/src/services/legacy.ts:2:" in proc.stderr
    assert "there is no fallback key" in proc.stderr


def test_a_tests_directory_is_exempt_and_printed(tmp_path) -> None:
    root = _tree(
        tmp_path,
        {
            "private/account/tests/unit/k.test.ts": "const K = '%s';\n" % CONSTANT,
            "docs/DESIGN.md": "The old key was `%s`.\n" % CONSTANT,
        },
    )
    proc = _run("--root", str(root))
    assert proc.returncode == 0, proc.stderr
    assert "exempt (tests directory): private/account/tests/unit/k.test.ts" in proc.stdout
    assert "1 test file(s) exempt" in proc.stdout


def test_an_exported_constant_fails(tmp_path) -> None:
    home = gate.HEALTHY_HOME.replace("const TEST_MODE_DEV_KEY", "export const TEST_MODE_DEV_KEY")
    proc = _run("--root", str(_tree(tmp_path, home=home)))
    assert proc.returncode == 1
    assert "is exported" in proc.stderr


def test_a_return_outside_the_test_mode_guard_fails(tmp_path) -> None:
    home = gate.HEALTHY_HOME.replace(
        "  throw new Error('missing');\n", "  return TEST_MODE_DEV_KEY;\n"
    )
    proc = _run("--root", str(_tree(tmp_path, home=home)))
    assert proc.returncode == 1
    assert "%s:6: TEST_MODE_DEV_KEY is used outside" % HOME in proc.stderr


def test_nothing_to_scan_cannot_run(tmp_path) -> None:
    (tmp_path / "README.md").write_text("nothing\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    proc = _run("--root", str(tmp_path))
    assert proc.returncode == 77
    assert "CANNOT RUN" in proc.stderr


def test_the_real_floors_refuse_a_fixture_sized_corpus(tmp_path) -> None:
    """The default (no --root) run scans at MIN_SOURCES and MIN_ACCOUNT_SRC; a fixture tree that passes at floor 1 must be refused at those, or the real floors would be decoration."""
    root = _tree(tmp_path)
    assert gate.scan(str(root), 1, 1)["sources"] == 3
    with pytest.raises(gate.CannotRunError, match="VACUOUS"):
        gate.scan(str(root), gate.MIN_SOURCES, gate.MIN_ACCOUNT_SRC)


def test_home_findings_accepts_the_live_shape() -> None:
    """The real config-server-key.ts, read not written: its shape is the one the gate expects."""
    text = (paths.repo_root() / HOME).read_text(encoding="utf-8")
    assert gate.home_findings(text) == ([], 1)
