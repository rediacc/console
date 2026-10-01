"""`rediacc_ci.quality.bash_lib_migration_complete` (check:ci-bash-lib-ported) on built trees and on the real one.

The gate's selftest covers `unported` in memory. These cover what only a tree can show: the table checks, the zero-functions retirement finding, and that the REAL tree is green while scanning a non-trivial number of functions, so a collapse of that count reads as a failure rather than a pass.
"""

import pathlib

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import bash_lib_migration_complete as g


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


@pytest.fixture
def one_lib(monkeypatch: pytest.MonkeyPatch) -> str:
    lib = ".ci/lib/service.sh"
    monkeypatch.setattr(g, "LIBS", {lib: ("service.py",)})
    monkeypatch.setattr(g, "ALIASES", {lib: {"_service_compose": "service.py:compose_argv"}})
    return lib


def test_selftest_controls_pass() -> None:
    assert g.selftest() is False


def test_real_tree_is_green_and_scans_every_library() -> None:
    found, scanned, aliased = g.scan(paths.repo_root())
    assert found == []
    # 189 on 2026-10-01. A floor, not an equality, so a ported-and-deleted function does not redden this; a collapse to a handful means the gate stopped seeing the libraries.
    assert scanned >= 150
    assert 0 < aliased < scanned


def test_ported_tree_is_clean(tmp_path: pathlib.Path, one_lib: str) -> None:
    _write(tmp_path, one_lib, "service_start() {\n:\n}\n_service_compose() {\n:\n}\n")
    _write(
        tmp_path,
        g.CORE_DIR + "/service.py",
        "def compose_argv(a):\n    pass\nclass S:\n    def start(self):\n        pass\n",
    )
    assert g.scan(tmp_path) == ([], 2, 1)


def test_unported_method_is_flagged(tmp_path: pathlib.Path, one_lib: str) -> None:
    _write(
        tmp_path,
        one_lib,
        "service_start() {\n:\n}\nservice_stop() {\n:\n}\n_service_compose() {\n:\n}\n",
    )
    _write(
        tmp_path,
        g.CORE_DIR + "/service.py",
        "def compose_argv():\n    pass\nclass S:\n    def start(self):\n        pass\n",
    )
    found, _, _ = g.scan(tmp_path)
    assert len(found) == 1
    assert "service_stop() has no Python twin in service.py" in found[0]


def test_missing_module_and_stale_alias_are_findings(tmp_path: pathlib.Path, one_lib: str) -> None:
    _write(tmp_path, one_lib, "service_start() {\n:\n}\n")
    found, _, _ = g.scan(tmp_path)
    assert any("LIBS names service.py, which does not exist" in f for f in found)
    assert any("_service_compose() no longer exists in the library" in f for f in found)


def test_unlisted_library_is_a_finding(tmp_path: pathlib.Path, one_lib: str) -> None:
    _write(tmp_path, one_lib, "_service_compose() {\n:\n}\n")
    _write(tmp_path, g.CORE_DIR + "/service.py", "def compose_argv():\n    pass\n")
    _write(tmp_path, ".ci/scripts/lib/new.sh", "new_fn() {\n:\n}\n")
    found, _, _ = g.scan(tmp_path)
    assert found == [
        ".ci/scripts/lib/new.sh is not in LIBS: name its Python modules, or port and delete it"
    ]


@pytest.mark.usefixtures("one_lib")
def test_deleted_library_must_leave_libs(tmp_path: pathlib.Path) -> None:
    found, scanned, _ = g.scan(tmp_path)
    assert scanned == 0
    assert any("the library is gone; drop its LIBS row" in f for f in found)


def test_zero_functions_scanned_says_retire(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(g, "LIBS", {})
    monkeypatch.setattr(g, "ALIASES", {})
    found, scanned, _ = g.scan(tmp_path)
    assert scanned == 0
    assert len(found) == 1
    assert "this gate checks nothing. Retire it" in found[0]


def test_main_exit_codes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert g.main([]) == 0
    assert "bash function(s): every one has a Python twin" in capsys.readouterr().out
    monkeypatch.setattr(g, "LIBS", {})
    monkeypatch.setattr(g, "ALIASES", {})
    monkeypatch.setattr(g.paths, "repo_root", lambda: tmp_path)
    assert g.main([]) == 1
    assert "Retire it" in capsys.readouterr().err
