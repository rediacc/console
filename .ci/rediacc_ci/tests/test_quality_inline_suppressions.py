"""`rediacc_ci.quality.inline_suppressions`: the controls the in-module selftest cannot reach from a pure function.

The selftest proves the scanner and the set arithmetic. What it cannot prove is that the gate REFUSES when its tree is not the tree: a scan over a near-empty root, a submodule missing on a CI runner, a baseline write that would grow. Each of those is a way for the gate to print a tick over nothing, so each one is driven here against a real temporary git repository.

Marker fixtures are assembled from halves, so this file never holds a literal marker and the gate it tests has nothing to find here.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.core import common
from rediacc_ci.quality import inline_suppressions as gate

if TYPE_CHECKING:
    import pathlib

NQ = "# noq" + "a"


def _repo(root: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def test_selftest_passes() -> None:
    assert gate.selftest(quiet=True) == 0


def test_scan_repo_reads_code_and_skips_prose(tmp_path: pathlib.Path) -> None:
    root = _repo(
        tmp_path,
        {
            "a.py": "x = 1  %s: B010\n" % NQ,
            "bin/tool": "#!/usr/bin/env python3\ny = 2  %s: F401\n" % NQ,
            "docs/a.md": "Never write `%s: B010`.\n" % NQ,
            "b.py": '"""Mentions %s: B010 in a docstring."""\n' % NQ,
        },
    )
    scan = gate.Scan()
    gate.scan_repo(root, "console", "", scan)
    assert gate.flatten(scan.counts) == {"a.py": {"noqa B010": 1}, "bin/tool": {"noqa F401": 1}}
    # CONTROL: the docstring file and the Markdown were READ or skipped, never counted.
    assert scan.files_by_language["py"] == 3


def test_a_near_empty_root_is_vacuous_not_clean(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    rc = gate.main([], root=root)
    assert rc == 1
    assert "VACUOUS" in capsys.readouterr().err


def test_a_missing_submodule_refuses_in_ci(tmp_path: pathlib.Path) -> None:
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    with pytest.raises(common.RefusalError):
        gate.scan_tree(root, env={"CI": "true"})


def test_a_missing_submodule_is_not_checked_locally(tmp_path: pathlib.Path) -> None:
    root = _repo(tmp_path, {"a.py": "x = 1  %s: E402\n" % NQ})
    scan = gate.scan_tree(root, env={})
    assert scan.not_checked == ["private/renet", "private/account"]
    # CONTROL: console itself was still read.
    assert gate.flatten(scan.counts) == {"a.py": {"noqa E402": 1}}


def test_write_baseline_refuses_growth_and_allows_a_drain(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "baseline.json"
    two = {"a.py": gate.count_markers("x = 1  %s: F401\ny = 2  %s: F401\n" % (NQ, NQ), "py")}
    one = {"a.py": gate.count_markers("x = 1  %s: F401\n" % NQ, "py")}
    swapped = {"a.py": gate.count_markers("x = 1  %s: B010\n" % NQ, "py")}

    assert gate.write_baseline(path, two, first_seed=False) == 1, "no file, no --first-seed"
    assert not path.exists()
    assert gate.write_baseline(path, two, first_seed=True) == 0
    assert gate.write_baseline(path, one, first_seed=False) == 0, "a drain is allowed"
    before = path.read_text(encoding="utf-8")
    # The composition trap: one F401 drained and one B010 added keeps the TOTAL at one.
    assert gate.write_baseline(path, swapped, first_seed=False) == 1
    assert path.read_text(encoding="utf-8") == before
    assert json.loads(before)["counts"] == {"a.py": {"noqa F401": 1}}
